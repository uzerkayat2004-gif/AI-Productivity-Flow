"""Bounded, Voice-only native Gemini keep-alive transport."""

from __future__ import annotations

import hashlib
import http.client
import json
import socket
import threading
import time
from collections import OrderedDict
from typing import Any
from urllib.parse import quote


_MAX_SESSIONS = 3
_sessions_lock = threading.Lock()
_sessions: "OrderedDict[tuple[str, str], _GeminiSession]" = OrderedDict()
_warm_lock = threading.Lock()
_warm_connection: tuple[http.client.HTTPSConnection, float] | None = None
_WARM_TTL_SECONDS = 30.0
_diagnostic_lock = threading.Lock()
_thread_diagnostic = threading.local()
_last_diagnostic: dict[str, object] = {"status": "not_attempted", "duration_seconds": 0.0}


def _thinking_level_for(model: str, speed_mode: object = "balanced") -> str | None:
    """Map Voice Flow's polish speed mode to Gemini 3 reasoning tiers."""
    name = str(model or "").casefold()
    if not name.startswith("gemini-3"):
        return None
    if "flash-lite-image" in name:
        return None
    mode = str(speed_mode or "balanced").strip().lower()
    if mode == "quality":
        return "high"
    if mode == "fast":
        if any(token in name for token in ("3-pro-preview", "3.1-pro", "3.7-flash", "3.8-flash")):
            return "low"
        return "minimal"
    # Cleanup does not need default dynamic reasoning. Low is supported by
    # Gemini 3 text models, including 3.7/3.8 which reject minimal.
    return "low"


def _record_diagnostic(status: str, started_at: float) -> None:
    # Keep this deliberately non-sensitive: it helps distinguish provider
    # latency from a transport failure without retaining dictated content or
    # credentials in application memory/logs.
    with _diagnostic_lock:
        _last_diagnostic.update({
            "status": status,
            "duration_seconds": round(max(0.0, time.monotonic() - started_at), 4),
        })
        _thread_diagnostic.value = dict(_last_diagnostic)


def last_transport_diagnostic() -> dict[str, object]:
    """Return the most recent safe outcome summary for latency diagnostics."""
    with _diagnostic_lock:
        return dict(getattr(_thread_diagnostic, "value", _last_diagnostic))


def _take_warm_connection() -> http.client.HTTPSConnection | None:
    """Adopt a recent completed warm socket without ever waiting for TLS."""
    global _warm_connection
    if not _warm_lock.acquire(blocking=False):
        return None
    try:
        warm, _warm_connection = _warm_connection, None
        if warm is None:
            return None
        connection, completed_at = warm
        if time.monotonic() - completed_at <= _WARM_TTL_SECONDS:
            return connection
        connection.close()
        return None
    finally:
        _warm_lock.release()


class _GeminiSession:
    def __init__(self, host: str, api_key: str) -> None:
        self.host = host
        self.api_key = api_key
        self.connection: http.client.HTTPSConnection | None = None
        self.lock = threading.Lock()

    def close(self) -> None:
        if self.connection is not None:
            try:
                self.connection.close()
            except OSError:
                pass
        self.connection = None

    def request_locked(self, model: str, prompt: str, timeout_seconds: float, speed_mode: object = "balanced") -> str | None:
        """Run while the cache lease (``lock``) is held by the caller."""
        started_at = time.monotonic()
        status = "network_error"
        deadline = time.monotonic() + timeout_seconds

        def set_remaining_timeout() -> None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Gemini voice request deadline expired")
            if self.connection is not None:
                # ``HTTPConnection.request`` reconnects lazily when an idle
                # keep-alive socket has been closed by the peer.  Update the
                # connection-level timeout as well as a live socket so that
                # lazy reconnect still observes this request's deadline,
                # rather than the timeout from the request that created the
                # cached session.
                self.connection.timeout = remaining
                if self.connection.sock is not None:
                    self.connection.sock.settimeout(remaining)

        try:
            if self.connection is None:
                self.connection = http.client.HTTPSConnection(self.host, timeout=timeout_seconds)
                # Connect before writing so all later socket operations get
                # only the remaining absolute request budget.
                self.connection.connect()
            set_remaining_timeout()
            generation_config: dict[str, Any] = {
                "temperature": 0.0,
                # Preserve the established fidelity allowance.  A word-based
                # cap is unsafe for CJK text, source code, URLs, and other
                # content whose model token count diverges from split words.
                "maxOutputTokens": 4096,
            }
            thinking_level = _thinking_level_for(model, speed_mode)
            if thinking_level is not None:
                generation_config["thinkingConfig"] = {
                    "thinkingLevel": thinking_level
                }
            body = json.dumps({
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": generation_config,
            }).encode("utf-8")
            path = "/v1beta/models/" + quote(model, safe="/-_.") + ":generateContent"
            set_remaining_timeout()
            self.connection.request("POST", path, body=body, headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "VoiceFlow/2.0",
            })
            set_remaining_timeout()
            response = self.connection.getresponse()
            set_remaining_timeout()
            raw = response.read()
            if response.status != 200:
                status = f"http_{response.status}"
                self.close()
                return None
            payload = json.loads(raw.decode("utf-8"))
            if payload["candidates"][0].get("finishReason") in {"MAX_TOKENS", "SAFETY", "RECITATION"}:
                status = "truncated"
                return None
            parts = payload["candidates"][0]["content"]["parts"]
            text = "".join(
                str(part.get("text") or "")
                for part in parts
                if isinstance(part, dict) and not part.get("thought")
            ).strip()
            status = "ok" if text else "empty_response"
            return text or None
        except (TimeoutError, socket.timeout):
            status = "timeout"
            self.close()
            return None
        except (json.JSONDecodeError, KeyError, IndexError, ValueError):
            status = "invalid_response"
            self.close()
            return None
        except (OSError, http.client.HTTPException):
            status = "network_error"
            self.close()
            return None
        finally:
            _record_diagnostic(status, started_at)
            self.lock.release()


def request_gemini_polish(
    *, api_key: str, model: str, prompt: str, timeout_seconds: float, speed_mode: object = "balanced"
) -> str | None:
    """Use a connection keyed by the exact selected credential and model."""
    if not api_key or not model or timeout_seconds <= 0:
        _record_diagnostic("invalid_request", time.monotonic())
        return None
    key = (hashlib.sha256(api_key.encode("utf-8")).hexdigest(), model)
    with _sessions_lock:
        session = _sessions.pop(key, None)
        if session is not None and not session.lock.acquire(blocking=False):
            # Never queue a dictation behind an in-flight provider read.
            _sessions[key] = session
            _record_diagnostic("busy", time.monotonic())
            return None
        if session is None:
            while len(_sessions) >= _MAX_SESSIONS:
                evicted_key = None
                for candidate_key, candidate in _sessions.items():
                    if candidate.lock.acquire(blocking=False):
                        evicted_key = candidate_key
                        break
                if evicted_key is None:
                    # Every cached connection is in use. Do not create an
                    # unbounded extra lane or close an active connection.
                    _record_diagnostic("busy", time.monotonic())
                    return None
                evicted = _sessions.pop(evicted_key)
                try:
                    evicted.close()
                finally:
                    evicted.lock.release()
            session = _GeminiSession("generativelanguage.googleapis.com", api_key)
            session.lock.acquire()
        _sessions[key] = session
    # Do not take the warm lock while holding the session cache lock: a TLS
    # handshake is allowed to continue in the background, never to delay a
    # release request. A previously timed-out session can adopt fresh TLS too.
    if session.connection is None:
        session.connection = _take_warm_connection()
    return session.request_locked(model, prompt, timeout_seconds, speed_mode)


def warm_gemini_connection(timeout_seconds: float = 0.75) -> None:
    """Preconnect TLS only; no credential, transcript, or model request is sent."""
    global _warm_connection
    if timeout_seconds <= 0 or not _warm_lock.acquire(blocking=False):
        return
    try:
        if _warm_connection is not None:
            connection, completed_at = _warm_connection
            if time.monotonic() - completed_at <= _WARM_TTL_SECONDS:
                return
            connection.close()
            _warm_connection = None
        connection = http.client.HTTPSConnection("generativelanguage.googleapis.com", timeout=timeout_seconds)
        connection.connect()
        _warm_connection = (connection, time.monotonic())
    except (OSError, http.client.HTTPException):
        try:
            connection.close()
        except (UnboundLocalError, OSError):
            pass
        return
    finally:
        _warm_lock.release()

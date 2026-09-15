"""Small reusable HTTP connections for interactive Voice Flow requests only."""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import http.client
import json
import socket
import threading
import time
from urllib.parse import urlsplit

_lock = threading.Lock()
_sessions: OrderedDict[tuple, _Connection] = OrderedDict()
_MAX_SESSIONS = 4
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class _Connection:
    def __init__(self):
        self.lock = threading.Lock()
        self.http = None

    def close(self):
        if self.http is not None:
            self.http.close()
        self.http = None


def request_json(endpoint: str, headers: dict, body: dict, timeout_seconds: float) -> tuple[dict | None, str]:
    """One request, no retry sleeps or process startup; never wait for a busy lane."""
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    url = urlsplit(endpoint)
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
        return None, "invalid_endpoint"
    credential = hashlib.sha256(json.dumps(headers, sort_keys=True).encode()).hexdigest()
    key = (url.scheme, url.hostname, url.port, credential)
    with _lock:
        session = _sessions.get(key)
        if session is not None:
            if not session.lock.acquire(blocking=False):
                return None, "busy"
            _sessions.move_to_end(key)
        else:
            if len(_sessions) >= _MAX_SESSIONS:
                for old_key, old in list(_sessions.items()):
                    if old.lock.acquire(blocking=False):
                        try:
                            old.close()
                            del _sessions[old_key]
                        finally:
                            old.lock.release()
                        break
                else:
                    return None, "busy"
            session = _Connection()
            session.lock.acquire()
            _sessions[key] = session

    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError("Voice provider request deadline expired")
        if session.http is not None:
            session.http.timeout = value
            if session.http.sock is not None:
                session.http.sock.settimeout(value)
        return value

    try:
        if session.http is None:
            cls = http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
            session.http = cls(url.hostname, port=url.port, timeout=remaining())
            session.http.connect()
        path = url.path or "/"
        if url.query:
            path += "?" + url.query
        remaining()
        session.http.request("POST", path, json.dumps(body).encode("utf-8"), headers=headers)
        remaining()
        response = session.http.getresponse()
        if response.status != 200:
            session.close()
            return None, f"http_{response.status}"
        pieces = []
        size = 0
        while True:
            remaining()
            chunk = response.read1(64 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > _MAX_RESPONSE_BYTES:
                session.close()
                return None, "response_too_large"
            pieces.append(chunk)
        result = json.loads(b"".join(pieces).decode("utf-8"))
        if not isinstance(result, dict):
            raise ValueError("Expected a JSON object")
        return result, "ok"
    except (TimeoutError, socket.timeout):
        session.close()
        return None, "timeout"
    except (OSError, http.client.HTTPException):
        session.close()
        return None, "network_error"
    except (ValueError, TypeError):
        session.close()
        return None, "invalid_response"
    finally:
        session.lock.release()


def request_chat(*, endpoint: str, api_key: str, model: str, messages: list,
                 timeout_seconds: float, max_tokens: int = 4096) -> tuple[str | None, str]:
    """Same Chat Completions payload as the gateway, with a Voice-only lifetime."""
    body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
    name = model.lower().rsplit("/", 1)[-1]
    if name.startswith(("gpt-5", "o1", "o3", "o4")):
        body.pop("temperature")
        body["max_completion_tokens"] = body.pop("max_tokens")
    payload, status = request_json(endpoint, {
        "Content-Type": "application/json", "Authorization": f"Bearer {api_key}",
        "User-Agent": "VoiceFlow/2.0",
    }, body, timeout_seconds)
    if payload is None:
        return None, status
    try:
        choice = payload["choices"][0]
        if choice.get("finish_reason") in {"length", "content_filter"}:
            return None, "truncated"
        content = choice["message"]["content"]
        if isinstance(content, list):
            content = "".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
        if not isinstance(content, str) or not content.strip():
            return None, "empty_response"
        return content.strip(), "ok"
    except (KeyError, IndexError, TypeError):
        return None, "invalid_response"

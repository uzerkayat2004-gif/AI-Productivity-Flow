"""NotebookLM-backed, source-grounded audio summaries for Audio Flow.

This module deliberately uses the existing Video Flow NotebookLM provider for
profile resolution, authentication and CLI invocation.  It is a separate
service because Audio Flow needs a playable downloaded artifact, not text that
is handed back to the local speech engine.
"""

from __future__ import annotations

import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from voice_flow.paths import data_dir
from voice_flow.video_flow_engine.notebooklm.models import (
    TERMINAL_FAILURE,
    TERMINAL_SUCCESS,
    NotebookLMVideoError,
)
from voice_flow.video_flow_engine.notebooklm.provider import NotebookLMVideoProvider

logger = logging.getLogger(__name__)


_DEPTHS = {
    "short": ("brief", "short"),
    "balanced": ("deep-dive", "default"),
    "deep": ("deep-dive", "long"),
}
_DEPTH_ALIASES = {
    "brief": "short",
    "quick": "short",
    "standard": "balanced",
    "detailed": "deep",
    "deep-dive": "deep",
    "deep dive": "deep",
}
_SAFE_ERROR = re.compile(r"[\r\n\t]+")
_SECRET_VALUE = re.compile(
    r"(?ix)(?P<prefix>\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|token|cookie|authorization|sid|psid(?:ts)?)\b\s*(?:=|:|\bis\b)\s*)(?P<secret>[^\s,;]+)"
)
_BEARER_VALUE = re.compile(r"(?i)(\bbearer\s+)[^\s,;]+")
_QUERY_SECRET = re.compile(r"(?ix)([?&](?:api[_-]?key|token|access[_-]?token|cookie|sid|psid(?:ts)?)=)[^&#\s]+")
MAX_SOURCE_TEXT_BYTES = 100_000
AUTH_EXPIRED_MESSAGE = "Google account login expired. Please sign in to NotebookLM in Video Flow settings."


class NotebookLMAudioSummaryError(RuntimeError):
    """A safe, typed error raised by the NotebookLM Audio Flow seam."""

    def __init__(self, code: str, message: str, *, payload: Any = None) -> None:
        self.code = str(code or "NOTEBOOKLM_AUDIO_ERROR")
        self.error_code = self.code
        self.message = _safe_error(message)
        self.payload = _safe_payload(payload)
        super().__init__(f"{self.code}: {self.message}")


def _safe_error(message: Any) -> str:
    clean = _SAFE_ERROR.sub(" ", str(message or "NotebookLM audio summary failed")).strip()
    clean = _BEARER_VALUE.sub(r"\1[REDACTED]", clean)
    clean = _SECRET_VALUE.sub(r"\g<prefix>[REDACTED]", clean)
    clean = _QUERY_SECRET.sub(r"\1[REDACTED]", clean)
    return clean[:600] or "NotebookLM audio summary failed"


def _safe_payload(payload: Any) -> Any:
    """Keep structured diagnostics useful without retaining credential values."""
    if isinstance(payload, Mapping):
        return {str(key): _safe_payload(value) for key, value in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [_safe_payload(value) for value in payload]
    if isinstance(payload, str):
        return _safe_error(payload)
    if payload is None or isinstance(payload, (bool, int, float)):
        return payload
    return _safe_error(payload)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def normalize_audio_depth(depth: str | None) -> str:
    """Map UI and legacy labels to one of short, balanced, or deep."""
    value = str(depth or "balanced").strip().casefold().replace("_", "-")
    value = _DEPTH_ALIASES.get(value, value)
    if value not in _DEPTHS:
        raise NotebookLMAudioSummaryError(
            "VALIDATION", "Summary depth must be short, balanced, or deep dive."
        )
    return value


def _prompt_for_depth(depth: str) -> str:
    """Make duration and editorial depth explicit for the cloud artifact."""
    shared = (
        "Create a spoken audio overview grounded only in the supplied source. "
        "Do not add outside facts, citations, URLs, or a preamble about the task. "
        "Use clear natural speech and preserve the source's meaning. "
    )
    if depth == "short":
        return shared + (
            "Make a concise 2 to 4 minute briefing. Cover the central claim, "
            "the most important supporting points, and one practical takeaway."
        )
    if depth == "deep":
        return shared + (
            "Make a thorough 12 to 20 minute deep dive. Explain the core ideas, "
            "reasoning, important details, relationships, examples found in the source, "
            "limitations, and a clear conclusion. Do not rush or merely list headings."
        )
    return shared + (
        "Make a balanced 6 to 10 minute overview. Explain the central ideas and "
        "key supporting details in a logical order, then finish with the main takeaways."
    )


class NotebookLMAudioSummaryService:
    """Create one NotebookLM audio overview and download it to Audio Flow storage."""

    def __init__(
        self,
        *,
        root_dir: Path | str | None = None,
        cli_path: Path | str | None = None,
        profile: str | None = None,
        poll_interval_seconds: float = 3.0,
        poll_timeout_seconds: float = 1_200.0,
        provider_factory: Callable[..., Any] = NotebookLMVideoProvider,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.root_dir = Path(root_dir or (data_dir() / "audio_summaries")).expanduser()
        self.cli_path = Path(cli_path) if cli_path else None
        self.profile = profile
        self.poll_interval_seconds = max(1.0, float(poll_interval_seconds))
        self.poll_timeout_seconds = max(1.0, float(poll_timeout_seconds))
        self.provider_factory = provider_factory
        self.sleep = sleep
        self.monotonic = monotonic

    def _cancelled(self, cancelled: Any) -> bool:
        if cancelled is None:
            return False
        try:
            if callable(cancelled):
                return bool(cancelled())
            if hasattr(cancelled, "is_set"):
                return bool(cancelled.is_set())
            return bool(cancelled)
        except Exception:
            return False

    def _check_cancelled(self, cancelled: Any) -> None:
        if self._cancelled(cancelled):
            raise NotebookLMAudioSummaryError("cancelled", "Audio summary generation was cancelled.")

    @staticmethod
    def _emit(callback: Callable[[Mapping[str, Any]], None] | None, state: str, **data: Any) -> None:
        if callback is None:
            return
        try:
            callback({"provider": "notebooklm", "state": state, **data})
        except NotebookLMAudioSummaryError:
            raise
        except Exception as exc:
            # Progress is frequently wired to a cancellation-aware UI queue.
            # Continuing after it fails could submit cloud work the caller has
            # already abandoned, so fail closed instead of swallowing it.
            raise NotebookLMAudioSummaryError("CALLBACK_FAILED", _safe_error(exc)) from exc

    def _bridge(self) -> Any:
        kwargs: dict[str, Any] = {
            "workdir": self.root_dir,
            "poll_interval_seconds": self.poll_interval_seconds,
        }
        if self.cli_path is not None:
            kwargs["cli_path"] = self.cli_path
        if self.profile:
            kwargs["profile"] = self.profile
        return self.provider_factory(**kwargs)

    def _poll(
        self,
        bridge: Any,
        notebook_id: str,
        task_id: str,
        *,
        cancelled: Any,
        on_progress: Callable[[Mapping[str, Any]], None] | None,
    ) -> str:
        started = self.monotonic()
        while True:
            self._check_cancelled(cancelled)
            data = _mapping(bridge._invoke(("artifact", "poll", task_id, "--notebook", notebook_id), timeout=90))
            status = _text(data.get("status"), data.get("status_label"), "unknown").casefold()
            artifact_id = _text(data.get("artifact_id"), data.get("id"), task_id)
            self._emit(
                on_progress,
                "audio_poll",
                phase="cloud_synthesis",
                notebook_id=notebook_id,
                task_id=task_id,
                status=status,
                elapsed=round(max(0.0, self.monotonic() - started), 2),
            )
            if status in TERMINAL_SUCCESS:
                return artifact_id
            if status in TERMINAL_FAILURE:
                raise NotebookLMAudioSummaryError(
                    "ARTIFACT_FAILED",
                    _text(data.get("error"), data.get("message"), f"Audio artifact status is {status}."),
                    payload=data,
                )
            elapsed = self.monotonic() - started
            if elapsed >= self.poll_timeout_seconds:
                raise NotebookLMAudioSummaryError(
                    "TIMEOUT", f"NotebookLM audio overview did not complete within {int(self.poll_timeout_seconds)} seconds."
                )
            self.sleep(min(self.poll_interval_seconds, max(0.1, self.poll_timeout_seconds - elapsed)))

    def generate(
        self,
        text: str,
        depth: str = "balanced",
        *,
        cancelled: Any = None,
        on_progress: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> dict[str, str]:
        """Generate a downloadable, source-grounded NotebookLM audio overview.

        No local model or TTS fallback is attempted.  The caller either gets a
        durable local audio file or a typed error it can safely surface.
        """
        if not isinstance(text, str) or not text.strip():
            raise NotebookLMAudioSummaryError("VALIDATION", "Select text before requesting a summary.")
        if len(text.encode("utf-8")) > MAX_SOURCE_TEXT_BYTES:
            raise NotebookLMAudioSummaryError(
                "VALIDATION", "Selected text is too large for a NotebookLM audio summary (maximum 100,000 bytes)."
            )
        canonical_depth = normalize_audio_depth(depth)
        self._check_cancelled(cancelled)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        request_id = uuid.uuid4().hex
        bridge = self._bridge()
        from voice_flow.video_flow_engine.notebooklm.config import resolve_notebooklm_profile
        effective_profile = getattr(bridge, "profile", None) or (resolve_notebooklm_profile(self.profile) if self.profile else resolve_notebooklm_profile())

        def _try_heal() -> bool:
            allow_heal = not os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("VOICE_FLOW_TEST_AUTO_HEAL")
            if not allow_heal:
                return False
            try:
                from voice_flow.video_flow_engine.notebooklm.login_flow import self_heal
                heal = self_heal(profile=effective_profile)
                if heal.get("ok"):
                    if hasattr(bridge, "sync_storage_state"):
                        bridge.sync_storage_state(force=True)
                    return True
            except Exception as h_err:
                logger.debug("Audio summary self_heal attempt failed: %s", h_err)
            try:
                from voice_flow.video_flow_engine.notebooklm.browser_sync import auto_sync_from_browser
                sync_res = auto_sync_from_browser(profile=effective_profile)
                if sync_res.get("success"):
                    if hasattr(bridge, "sync_storage_state"):
                        bridge.sync_storage_state(force=True)
                    try:
                        verified = bridge.check_auth(raise_on_error=True)
                        if getattr(verified, "authenticated", True):
                            return True
                    except Exception as verify_err:
                        logger.debug("Audio summary auth verification failed after auto_sync_from_browser: %s", verify_err)
            except Exception as b_err:
                logger.debug("Audio summary auto_sync_from_browser attempt failed: %s", b_err)
            allow_pw = not os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("VOICE_FLOW_TEST_PLAYWRIGHT_HEAL")
            if allow_pw:
                try:
                    from voice_flow.video_flow_engine.notebooklm.browser_sync import sync_cookies_with_playwright
                    pw_sync = sync_cookies_with_playwright(profile=effective_profile, headless=True, timeout_seconds=35)
                    if pw_sync.get("success"):
                        if hasattr(bridge, "sync_storage_state"):
                            bridge.sync_storage_state(force=True)
                        try:
                            verified = bridge.check_auth(raise_on_error=True)
                            if getattr(verified, "authenticated", True):
                                return True
                        except Exception as verify_err:
                            logger.debug("Audio summary auth verification failed after playwright sync: %s", verify_err)
                except Exception as pw_err:
                    logger.debug("Audio summary sync_cookies_with_playwright attempt failed: %s", pw_err)
            return False

        def _is_auth_error(exc: Exception) -> bool:
            try:
                from voice_flow.video_flow_engine.notebooklm.provider import _is_auth_expired_error
                code = getattr(exc, "code", None)
                msg = str(getattr(exc, "message", None) or str(exc))
                if _is_auth_expired_error(code, msg):
                    return True
            except Exception:
                pass
            code_s = str(getattr(exc, "code", "") or "").lower()
            msg_s = str(getattr(exc, "message", None) or str(exc)).lower()
            return (
                code_s in ("auth_expired", "auth", "cli_error", "unauthenticated", "unauthorized")
                or any(ind in msg_s for ind in (
                    "auth", "expired", "token", "login", "psidts", "re-authenticate", "401", "unauthorized", "unauthenticated"
                ))
            )

        # Proactively refresh sliding cookies if session is near expiry
        allow_heal = not os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("VOICE_FLOW_TEST_AUTO_HEAL")
        if allow_heal:
            try:
                from voice_flow.video_flow_engine.notebooklm.config import is_session_near_expiry
                if is_session_near_expiry(effective_profile, threshold_seconds=86400.0):
                    _try_heal()
            except Exception:
                pass

        try:
            auth = bridge.check_auth(raise_on_error=True)
        except Exception as auth_exc:
            if _is_auth_error(auth_exc) and _try_heal():
                try:
                    auth = bridge.check_auth(raise_on_error=True)
                except Exception as retry_exc:
                    if isinstance(retry_exc, NotebookLMVideoError):
                        err_code = "auth_expired" if _is_auth_error(retry_exc) else retry_exc.code
                        err_msg = (
                            AUTH_EXPIRED_MESSAGE
                            if err_code == "auth_expired"
                            else retry_exc.message
                        )
                        raise NotebookLMAudioSummaryError(err_code, err_msg, payload=retry_exc.payload) from retry_exc
                    if _is_auth_error(retry_exc):
                        raise NotebookLMAudioSummaryError("auth_expired", AUTH_EXPIRED_MESSAGE) from retry_exc
                    raise
            else:
                if isinstance(auth_exc, NotebookLMVideoError):
                    err_code = "auth_expired" if _is_auth_error(auth_exc) else auth_exc.code
                    err_msg = (
                        AUTH_EXPIRED_MESSAGE
                        if err_code == "auth_expired"
                        else auth_exc.message
                    )
                    raise NotebookLMAudioSummaryError(err_code, err_msg, payload=auth_exc.payload) from auth_exc
                if _is_auth_error(auth_exc):
                    raise NotebookLMAudioSummaryError("auth_expired", AUTH_EXPIRED_MESSAGE) from auth_exc
                raise

        if not getattr(auth, "authenticated", True):
            if _try_heal():
                try:
                    auth = bridge.check_auth(raise_on_error=True)
                except Exception as post_heal_exc:
                    if _is_auth_error(post_heal_exc):
                        raise NotebookLMAudioSummaryError("auth_expired", AUTH_EXPIRED_MESSAGE) from post_heal_exc
                    raise
            if not getattr(auth, "authenticated", True):
                raise NotebookLMAudioSummaryError("auth_expired", AUTH_EXPIRED_MESSAGE)

        for attempt in range(2):
            try:
                self._check_cancelled(cancelled)
                self._emit(on_progress, "notebook_create", phase="notebook_setup")
                notebook = bridge.create_notebook(f"Voice Flow Audio Summary {request_id[:8]}")
                notebook_id = str(notebook.notebook_id)
                self._check_cancelled(cancelled)
                self._emit(on_progress, "source_add", phase="source_ingest", notebook_id=notebook_id)
                source = bridge.add_source(
                    notebook_id,
                    source_text=text.strip(),
                    title=f"Selected text {request_id[:8]}",
                )
                self._check_cancelled(cancelled)
                source_status = str(getattr(source, "status", "ready")).strip().casefold()
                if source_status not in {"ready", "completed"}:
                    raise NotebookLMAudioSummaryError("SOURCE_NOT_READY", "NotebookLM source did not finish processing.")
                self._emit(on_progress, "source_ready", phase="source_ingest", notebook_id=notebook_id, source_id=source.source_id)
                prompt_path = self.root_dir / f"{request_id}-prompt.txt"
                prompt_path.write_text(_prompt_for_depth(canonical_depth), encoding="utf-8")
                audio_format, audio_length = _DEPTHS[canonical_depth]
                self._emit(on_progress, "audio_start", phase="cloud_synthesis", notebook_id=notebook_id, depth=canonical_depth)
                started = _mapping(bridge._invoke((
                    "generate", "audio", "--notebook", notebook_id, "--source", source.source_id,
                    "--format", audio_format, "--length", audio_length,
                    "--prompt-file", str(prompt_path),
                ), timeout=120))
                task_id = _text(started.get("task_id"), started.get("artifact_id"), started.get("id"))
                if not task_id:
                    raise NotebookLMAudioSummaryError("INVALID_RESPONSE", "NotebookLM did not return an audio task ID.", payload=started)
                artifact_id = self._poll(bridge, notebook_id, task_id, cancelled=cancelled, on_progress=on_progress)
                self._check_cancelled(cancelled)
                target = (self.root_dir / f"{request_id}.m4a").resolve()
                self._emit(on_progress, "audio_download", phase="download", notebook_id=notebook_id, artifact_id=artifact_id)
                bridge._invoke((
                    "download", "audio", str(target), "--notebook", notebook_id,
                    "--artifact", artifact_id, "--force",
                ), timeout=300)
                if not target.is_file() or target.stat().st_size <= 0:
                    raise NotebookLMAudioSummaryError("DOWNLOAD_FAILED", "NotebookLM did not download a playable audio file.")
                self._check_cancelled(cancelled)
                # Ensure companion MP3 exists immediately for pure-audio downloads
                try:
                    from voice_flow.audio_summary_player import ensure_mp3_audio
                    ensure_mp3_audio(target)
                except Exception:
                    pass
                return {
                    "audio_path": str(target),
                    "notebook_id": notebook_id,
                    "artifact_id": artifact_id,
                    "depth": canonical_depth,
                }
            except NotebookLMAudioSummaryError:
                raise
            except Exception as exc:
                if attempt == 0 and _is_auth_error(exc) and _try_heal():
                    logger.info("Auto-healed NotebookLM session after generation failure (%s); retrying audio summary", exc)
                    bridge = self._bridge()
                    continue
                if isinstance(exc, NotebookLMVideoError):
                    err_code = "auth_expired" if _is_auth_error(exc) else exc.code
                    err_msg = (
                        AUTH_EXPIRED_MESSAGE
                        if err_code == "auth_expired"
                        else exc.message
                    )
                    raise NotebookLMAudioSummaryError(err_code, err_msg, payload=exc.payload) from exc
                if _is_auth_error(exc):
                    raise NotebookLMAudioSummaryError("auth_expired", AUTH_EXPIRED_MESSAGE) from exc
                if isinstance(exc, (OSError, ValueError)):
                    raise NotebookLMAudioSummaryError("NOTEBOOKLM_AUDIO_ERROR", _safe_error(exc)) from exc
                raise


def check_notebooklm_auth_status(profile: str | None = None) -> dict[str, Any]:
    """Check NotebookLM authentication status safely for Audio Flow."""
    try:
        from voice_flow.video_flow_engine.notebooklm import login_flow
        state = login_flow.get_login_state(profile=profile)
        logged_in = bool(state.get("logged_in") or state.get("authenticated"))
        return {
            "authenticated": logged_in,
            "email": str(state.get("email") or ""),
            "profile": str(state.get("profile") or ""),
            "status": "connected" if logged_in else "auth_expired",
        }
    except Exception as exc:
        return {
            "authenticated": False,
            "email": "",
            "profile": "",
            "status": "error",
            "error": str(exc),
        }


def start_notebooklm_login(profile: str | None = None) -> dict[str, Any]:
    """Trigger the official NotebookLM sign-in flow for Audio Flow."""
    try:
        from voice_flow.video_flow_engine.notebooklm import login_flow
        return login_flow.start_login(profile=profile)
    except Exception as exc:
        return {"launched": False, "error": str(exc)}


audio_notebooklm_service = NotebookLMAudioSummaryService()


__all__ = [
    "NotebookLMAudioSummaryError",
    "NotebookLMAudioSummaryService",
    "audio_notebooklm_service",
    "normalize_audio_depth",
    "MAX_SOURCE_TEXT_BYTES",
    "check_notebooklm_auth_status",
    "start_notebooklm_login",
]

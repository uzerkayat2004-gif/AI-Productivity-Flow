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
import threading
import time
import uuid
from math import ceil
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


_DEPTHS = frozenset({"short", "balanced", "deep"})
_DEPTH_ALIASES = {
    "brief": "short",
    "quick": "short",
    "standard": "balanced",
    "detailed": "deep",
    "deep-dive": "deep",
    "deep dive": "deep",
}
_SUMMARY_STYLES = {"single", "podcast"}
_ONE_PAGE_WORDS = 650
_TINY_SOURCE_WORDS = 35
_SPOKEN_WORDS_PER_MINUTE = 130
_SAFE_ERROR = re.compile(r"[\r\n\t]+")
_SECRET_VALUE = re.compile(
    r"(?ix)(?P<prefix>\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|token|cookie|authorization|sid|psid(?:ts)?)\b\s*(?:=|:|\bis\b)\s*)(?P<secret>[^\s,;]+)"
)
_BEARER_VALUE = re.compile(r"(?i)(\bbearer\s+)[^\s,;]+")
_QUERY_SECRET = re.compile(r"(?ix)([?&](?:api[_-]?key|token|access[_-]?token|cookie|sid|psid(?:ts)?)=)[^&#\s]+")
MAX_SOURCE_TEXT_BYTES = 100_000
AUTH_EXPIRED_MESSAGE = "Google account login expired. Please sign in to NotebookLM in Video Flow settings."


def _log_resource_snapshot(stage: str) -> None:
    """Log one best-effort process sample without retaining job data.

    These are stage samples, not continuous peak-memory telemetry.  Keeping
    this helper synchronous and stateless makes it useful when diagnosing a
    later real job without adding a sampler thread or retaining media/source
    content in this service.
    """
    sample: dict[str, int | str | None] = {
        "stage": stage,
        "pid": os.getpid(),
        "private_bytes": None,
        "working_set_bytes": None,
        "thread_count": None,
    }
    try:
        import psutil

        process = psutil.Process()
        memory = process.memory_info()
        private = getattr(memory, "private", None)
        if private is None:
            private = getattr(memory, "private_usage", None)
        sample["private_bytes"] = int(private) if private is not None else None
        sample["working_set_bytes"] = int(getattr(memory, "rss", 0))
        sample["thread_count"] = int(process.num_threads())
    except Exception:
        # psutil is optional at this diagnostic seam; resource logging must
        # never affect NotebookLM auth, cloud generation, or downloads.
        pass
    try:
        logger.info("[AUDIO FLOW RESOURCES] %s", sample)
    except Exception:
        pass


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


def normalize_audio_summary_style(style: str | None) -> str:
    """Return the persisted Audio Flow summary delivery style."""
    value = str(style or "single").strip().casefold()
    if value not in _SUMMARY_STYLES:
        raise NotebookLMAudioSummaryError("VALIDATION", "Summary style must be single or podcast.")
    return value


def _source_word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def podcast_audio_length(depth: str, source_words: int) -> str:
    """Choose NotebookLM's coarse duration control from the planned podcast size."""
    target_minutes = podcast_audio_target_words(depth, source_words) / _SPOKEN_WORDS_PER_MINUTE
    if target_minutes <= 4:
        return "short"
    if target_minutes <= 10:
        return "default"
    return "long"


def podcast_audio_target_words(depth: str, source_words: int) -> int:
    """Return a source-bounded spoken-word target for a Deep Dive podcast.

    NotebookLM ultimately controls the exact runtime.  This target gives its
    prompt and coarse length flag a consistent, source-proportional signal
    without asking a tiny source to be padded.
    """
    source_words = max(1, int(source_words))
    ratio, minimum, cap = {
        "short": (0.22, 60, 180),
        "balanced": (0.55, 90, 1_000),
        "deep": (0.80, 120, 2_000),
    }[depth]
    if source_words <= _TINY_SOURCE_WORDS:
        return source_words
    return min(cap, max(minimum, round(source_words * ratio)))


def podcast_duration_budget(depth: str, source_words: int) -> dict[str, int | str]:
    """Return the podcast-only word and runtime limits sent to NotebookLM.

    The native length selector remains deliberately coarse.  The runtime
    ceiling is the verification contract for the downloaded Deep Dive.
    """
    target_words = podcast_audio_target_words(depth, source_words)
    target_seconds = ceil(target_words / _SPOKEN_WORDS_PER_MINUTE * 60)
    minimum, maximum = {
        "short": (60, 120),
        "balanced": (90, 660),
        "deep": (120, 1320),
    }[depth]
    maximum_seconds = min(maximum, max(minimum, ceil(target_seconds * 1.4 + 10)))
    return {
        "target_words": target_words,
        "target_seconds": target_seconds,
        "maximum_seconds": maximum_seconds,
        "audio_length": podcast_audio_length(depth, source_words),
    }


def m4a_duration_seconds(path: Path | str) -> float:
    """Read an M4A duration from ``moov/mvhd`` without decoding the audio.

    Only ISO-BMFF headers and the tiny mvhd payload are read.  Every declared
    box is bounded by the actual file size so corrupt metadata cannot cause
    unbounded seeks or reads.
    """
    file_path = Path(path)
    try:
        file_size = file_path.stat().st_size
        if file_size < 8:
            raise ValueError("file is too small")
        with file_path.open("rb") as handle:
            def boxes(start: int, end: int):
                cursor = start
                count = 0
                while cursor + 8 <= end and count < 10_000:
                    handle.seek(cursor)
                    header = handle.read(8)
                    if len(header) != 8:
                        raise ValueError("truncated box header")
                    size = int.from_bytes(header[:4], "big")
                    kind = header[4:8]
                    header_size = 8
                    if size == 1:
                        extended = handle.read(8)
                        if len(extended) != 8:
                            raise ValueError("truncated extended box size")
                        size = int.from_bytes(extended, "big")
                        header_size = 16
                    elif size == 0:
                        size = end - cursor
                    if size < header_size or cursor + size > end:
                        raise ValueError("invalid box size")
                    yield kind, cursor + header_size, cursor + size
                    cursor += size
                    count += 1
                if cursor != end and cursor + 8 > end:
                    raise ValueError("trailing truncated box")

            for kind, payload_start, box_end in boxes(0, file_size):
                if kind != b"moov":
                    continue
                for child_kind, child_start, child_end in boxes(payload_start, box_end):
                    if child_kind != b"mvhd":
                        continue
                    handle.seek(child_start)
                    payload = handle.read(min(32, child_end - child_start))
                    if len(payload) < 20:
                        raise ValueError("truncated mvhd")
                    version = payload[0]
                    if version == 0:
                        if len(payload) < 20:
                            raise ValueError("truncated version 0 mvhd")
                        timescale = int.from_bytes(payload[12:16], "big")
                        duration = int.from_bytes(payload[16:20], "big")
                    elif version == 1:
                        if len(payload) < 32:
                            raise ValueError("truncated version 1 mvhd")
                        timescale = int.from_bytes(payload[20:24], "big")
                        duration = int.from_bytes(payload[24:32], "big")
                    else:
                        raise ValueError("unsupported mvhd version")
                    if not timescale or not duration:
                        raise ValueError("invalid mvhd duration")
                    return duration / float(timescale)
        raise ValueError("moov/mvhd metadata was not found")
    except (OSError, ValueError) as exc:
        raise NotebookLMAudioSummaryError(
            "AUDIO_METADATA_INVALID", "Downloaded podcast audio has unreadable duration metadata."
        ) from exc


def _single_audio_length(depth: str, source_words: int) -> str:
    """Scale native Brief's coarse control by source size and selected depth."""
    if depth == "short":
        return "short"
    if depth == "balanced":
        return "short" if source_words <= 250 else "default"
    if source_words <= 100:
        return "short"
    if source_words <= 350:
        return "default"
    return "long"


def _native_audio_prompt(style: str, depth: str, source_words: int, *, corrective: str = "") -> str:
    editorial = {
        "short": "Give the central claim, the most important supporting points, and one practical takeaway.",
        "balanced": "Explain the central ideas and their key supporting details in a clear logical order.",
        "deep": "Explore the core ideas, reasoning, important details, relationships, examples, limitations, and conclusion.",
    }[depth]
    delivery = "Use one clear narrator" if style == "single" else "Use a natural two-host discussion"
    prompt = (
        "Create a source-grounded audio overview using only the selected source. "
        f"{delivery}. {editorial} Preserve its key points and avoid outside facts, citations, URLs, and filler. "
    )
    if style == "single":
        if source_words <= _TINY_SOURCE_WORDS:
            return prompt + " Keep this native Brief brief and proportionate to this small source; do not pad it."
        if depth == "short":
            return prompt + " Keep this native Brief concise and proportionate to the selected source."
        return prompt + " Use the available native Brief time appropriate for this source and selected depth; retain as many important source points as fit."
    budget = podcast_duration_budget(depth, source_words)
    exchanges = {"short": "4 to 6", "balanced": "6 to 12", "deep": "10 to 20"}[depth]
    briefing = "Use a condensed, rapid briefing." if depth == "short" else "Keep each exchange purposeful and compact."
    return prompt + (
        f" Across both hosts, speak no more than {budget['target_words']} words and finish within {budget['maximum_seconds']} seconds. "
        f"Use at most {exchanges} exchanges. {briefing} Preserve the key source points, then stop once they are covered; never pad to fill time. "
        "No greetings, chitchat, long introduction, repeated recap, promotion, or outside examples. "
        + corrective
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
        # NotebookLM bridge setup can spawn/attach heavyweight browser and CLI
        # resources. Only one Audio Flow request may enter it at a time.
        self._generation_lock = threading.Lock()

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
        timeout_seconds: float | None = None,
    ) -> str:
        started = self.monotonic()
        timeout = self.poll_timeout_seconds if timeout_seconds is None else max(0.0, timeout_seconds)
        if timeout <= 0:
            raise NotebookLMAudioSummaryError(
                "TIMEOUT", f"NotebookLM audio overview did not complete within {int(self.poll_timeout_seconds)} seconds."
            )
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
            if elapsed >= timeout:
                raise NotebookLMAudioSummaryError(
                    "TIMEOUT", f"NotebookLM audio overview did not complete within {int(self.poll_timeout_seconds)} seconds."
                )
            self.sleep(min(self.poll_interval_seconds, max(0.1, timeout - elapsed)))

    def generate(
        self,
        text: str,
        depth: str = "balanced",
        *,
        style: str = "single",
        cancelled: Any = None,
        on_progress: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Serialize expensive bridge setup while allowing stale callers to leave."""
        while not self._generation_lock.acquire(timeout=0.05):
            self._check_cancelled(cancelled)
        try:
            return self._generate_locked(
                text, depth, style=style, cancelled=cancelled, on_progress=on_progress
            )
        finally:
            self._generation_lock.release()

    def _generate_locked(
        self,
        text: str,
        depth: str = "balanced",
        *,
        style: str = "single",
        cancelled: Any = None,
        on_progress: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
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
        canonical_style = normalize_audio_summary_style(style)
        source_words = _source_word_count(text)
        self._check_cancelled(cancelled)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        request_id = uuid.uuid4().hex
        _log_resource_snapshot("start")
        bridge = self._bridge()
        started_at = self.monotonic()
        stage_timings: dict[str, float] = {
            "auth": 0.0,
            "notebook_setup": 0.0,
            "source_indexing": 0.0,
            "generation_submit": 0.0,
            "cloud_wait": 0.0,
            "download": 0.0,
        }
        from voice_flow.video_flow_engine.notebooklm.config import resolve_notebooklm_profile
        effective_profile = getattr(bridge, "profile", None) or (resolve_notebooklm_profile(self.profile) if self.profile else resolve_notebooklm_profile())

        def _timings() -> dict[str, float]:
            timings = {name: round(max(0.0, value), 4) for name, value in stage_timings.items()}
            timings["total"] = round(max(0.0, self.monotonic() - started_at), 4)
            return timings

        def _auth_check(active_bridge: Any) -> Any:
            """Prefer the provider's safe local-session fast path when available."""
            try:
                return active_bridge.check_auth(raise_on_error=True, fast_valid_session=True)
            except TypeError as exc:
                # Keep third-party/test bridge compatibility.  Only retry when
                # the bridge has not adopted the optional keyword yet.
                if "fast_valid_session" not in str(exc):
                    raise
                return active_bridge.check_auth(raise_on_error=True)

        def _try_heal() -> bool:
            heal_started = self.monotonic()
            try:
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
                            verified = _auth_check(bridge)
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
                                verified = _auth_check(bridge)
                                if getattr(verified, "authenticated", True):
                                    return True
                            except Exception as verify_err:
                                logger.debug("Audio summary auth verification failed after playwright sync: %s", verify_err)
                    except Exception as pw_err:
                        logger.debug("Audio summary sync_cookies_with_playwright attempt failed: %s", pw_err)
                return False
            finally:
                # Recovery is part of auth latency and is often its slowest path.
                stage_timings["auth"] += self.monotonic() - heal_started

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
                code_s in ("auth_expired", "auth", "unauthenticated", "unauthorized")
                or any(ind in msg_s for ind in (
                    "auth", "expired", "token", "login", "psidts", "re-authenticate", "401", "unauthorized", "unauthenticated"
                ))
            )

        try:
            stage_started = self.monotonic()
            try:
                auth = _auth_check(bridge)
            finally:
                stage_timings["auth"] += self.monotonic() - stage_started
        except Exception as auth_exc:
            if _is_auth_error(auth_exc) and _try_heal():
                try:
                    stage_started = self.monotonic()
                    try:
                        auth = _auth_check(bridge)
                    finally:
                        stage_timings["auth"] += self.monotonic() - stage_started
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
                    stage_started = self.monotonic()
                    try:
                        auth = _auth_check(bridge)
                    finally:
                        stage_timings["auth"] += self.monotonic() - stage_started
                except Exception as post_heal_exc:
                    if _is_auth_error(post_heal_exc):
                        raise NotebookLMAudioSummaryError("auth_expired", AUTH_EXPIRED_MESSAGE) from post_heal_exc
                    raise
            if not getattr(auth, "authenticated", True):
                raise NotebookLMAudioSummaryError("auth_expired", AUTH_EXPIRED_MESSAGE)

        prompt_path: Path | None = None
        for attempt in range(2):
            try:
                self._check_cancelled(cancelled)
                self._emit(on_progress, "notebook_create", phase="notebook_setup")
                stage_started = self.monotonic()
                try:
                    notebook = bridge.create_notebook(f"Voice Flow Audio Summary {request_id[:8]}")
                finally:
                    stage_timings["notebook_setup"] += self.monotonic() - stage_started
                notebook_id = str(notebook.notebook_id)
                self._check_cancelled(cancelled)
                self._emit(on_progress, "source_add", phase="source_ingest", notebook_id=notebook_id)
                stage_started = self.monotonic()
                try:
                    source = bridge.add_source(
                        notebook_id,
                        source_text=text.strip(),
                        title=f"Selected text {request_id[:8]}",
                    )
                finally:
                    stage_timings["source_indexing"] += self.monotonic() - stage_started
                self._check_cancelled(cancelled)
                source_status = str(getattr(source, "status", "ready")).strip().casefold()
                if source_status not in {"ready", "completed"}:
                    raise NotebookLMAudioSummaryError("SOURCE_NOT_READY", "NotebookLM source did not finish processing.")
                self._emit(on_progress, "source_ready", phase="source_ingest", notebook_id=notebook_id, source_id=source.source_id)
                budget = podcast_duration_budget(canonical_depth, source_words) if canonical_style == "podcast" else None
                audio_length = (
                    _single_audio_length(canonical_depth, source_words)
                    if canonical_style == "single"
                    else str(budget["audio_length"])
                )
                target = (self.root_dir / f"{request_id}.m4a").resolve()
                for audio_attempt in range(2):
                    self._check_cancelled(cancelled)
                    corrective = ""
                    if audio_attempt:
                        if self.poll_timeout_seconds - stage_timings["cloud_wait"] <= 0:
                            raise NotebookLMAudioSummaryError(
                                "TIMEOUT",
                                f"NotebookLM audio overview did not complete within {int(self.poll_timeout_seconds)} seconds.",
                            )
                        self._emit(
                            on_progress, "audio_retry", phase="cloud_synthesis", notebook_id=notebook_id,
                            message="Shortening podcast summary",
                        )
                        corrective = (
                            f"The prior attempt ran for {previous_duration:.1f} seconds and exceeded the ceiling. "
                            "Be substantially shorter and end immediately after the essential source points."
                        )
                    prompt_path = self.root_dir / f"{request_id}-prompt.txt"
                    prompt_path.write_text(
                        _native_audio_prompt(canonical_style, canonical_depth, source_words, corrective=corrective),
                        encoding="utf-8",
                    )
                    # A retry progress callback can invalidate the request;
                    # never submit a second cloud job after that cancellation.
                    if audio_attempt:
                        self._check_cancelled(cancelled)
                    self._emit(on_progress, "audio_start", phase="cloud_synthesis", notebook_id=notebook_id, depth=canonical_depth)
                    if audio_attempt:
                        self._check_cancelled(cancelled)
                    stage_started = self.monotonic()
                    try:
                        started = _mapping(bridge._invoke((
                            "generate", "audio", "--notebook", notebook_id, "--source", source.source_id,
                            "--format", "brief" if canonical_style == "single" else "deep-dive", "--length", audio_length,
                            "--prompt-file", str(prompt_path),
                        ), timeout=120))
                    finally:
                        stage_timings["generation_submit"] += self.monotonic() - stage_started
                    task_id = _text(started.get("task_id"), started.get("artifact_id"), started.get("id"))
                    if not task_id:
                        raise NotebookLMAudioSummaryError("INVALID_RESPONSE", "NotebookLM did not return an audio task ID.", payload=started)
                    stage_started = self.monotonic()
                    try:
                        # A podcast shortening retry shares the original cloud
                        # wait allowance. Existing single-narrator and auth
                        # retry behavior retains its per-attempt timeout.
                        remaining_wait = (
                            self.poll_timeout_seconds - stage_timings["cloud_wait"]
                            if budget is not None
                            else self.poll_timeout_seconds
                        )
                        artifact_id = self._poll(
                            bridge, notebook_id, task_id, cancelled=cancelled,
                            on_progress=on_progress, timeout_seconds=remaining_wait,
                        )
                    finally:
                        stage_timings["cloud_wait"] += self.monotonic() - stage_started
                        _log_resource_snapshot("after_generation_wait")
                    self._check_cancelled(cancelled)
                    self._emit(on_progress, "audio_download", phase="download", notebook_id=notebook_id, artifact_id=artifact_id)
                    stage_started = self.monotonic()
                    try:
                        bridge._invoke(("download", "audio", str(target), "--notebook", notebook_id, "--artifact", artifact_id, "--force"), timeout=300)
                    finally:
                        stage_timings["download"] += self.monotonic() - stage_started
                        _log_resource_snapshot("after_download")
                    if not target.is_file() or target.stat().st_size <= 0:
                        raise NotebookLMAudioSummaryError("DOWNLOAD_FAILED", "NotebookLM did not download a playable audio file.")
                    self._check_cancelled(cancelled)
                    duration_sec: float | None = None
                    if budget is not None:
                        duration_sec = m4a_duration_seconds(target)
                        if duration_sec > float(budget["maximum_seconds"]):
                            previous_duration = duration_sec
                            if audio_attempt == 0:
                                continue
                            raise NotebookLMAudioSummaryError(
                                "PODCAST_TOO_LONG",
                                "NotebookLM could not fit this podcast summary within its duration limit after one shortening retry.",
                                payload={"duration_sec": duration_sec, "budget": budget},
                            )
                    timings = _timings()
                    logger.info("NotebookLM Audio Flow completed in %.2fs (auth=%.2fs setup=%.2fs index=%.2fs submit=%.2fs wait=%.2fs download=%.2fs)", timings["total"], timings["auth"], timings["notebook_setup"], timings["source_indexing"], timings["generation_submit"], timings["cloud_wait"], timings["download"])
                    _log_resource_snapshot("finish")
                    result = {"audio_path": str(target), "notebook_id": notebook_id, "artifact_id": artifact_id, "depth": canonical_depth, "style": canonical_style, "timings_seconds": timings}
                    if budget is not None:
                        result.update({"duration_sec": duration_sec, "duration_budget": budget})
                    return result
            except NotebookLMAudioSummaryError:
                raise
            except Exception as exc:
                if attempt == 0 and _is_auth_error(exc) and _try_heal():
                    logger.info("Auto-healed NotebookLM session after generation failure (%s); retrying audio summary", _safe_error(exc))
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
            finally:
                if prompt_path is not None:
                    try:
                        prompt_path.unlink(missing_ok=True)
                    except OSError:
                        pass


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
    "normalize_audio_summary_style",
    "podcast_audio_length",
    "podcast_audio_target_words",
    "podcast_duration_budget",
    "m4a_duration_seconds",
    "MAX_SOURCE_TEXT_BYTES",
    "check_notebooklm_auth_status",
    "start_notebooklm_login",
]

"""Main Application Orchestrator for Voice Flow.
Integrates Audio Recording, Whisper STT, Dictionary Biasing, Active Window Style Engine,
SQLite Storage, Multi-API Key Polishing, Clipboard Injection, and Desktop GUI.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import io
import logging
import os
import re
import string
import subprocess
import sys
import threading
import time
from typing import Any
from pathlib import Path
import ctypes
from voice_flow.platform.wincompat import wintypes, windll, IS_WINDOWS
from voice_flow.platform.macos_app import configure_macos_app

configure_macos_app("engine", apply_policy=False)

if sys.stdout is None:
    class DummyWriter:
        encoding = "utf-8"
        errors = "replace"
        def write(self, x): pass
        def flush(self): pass
        def isatty(self): return False
    sys.stdout = DummyWriter()
    sys.stderr = DummyWriter()

from voice_flow.audio import AudioRecorder
from voice_flow.config import config
from voice_flow.dictionary import dictionary_engine
from voice_flow.effective_style import apply_persistent_change, resolve_effective_style
from voice_flow.hotkeys import InputTriggerListener
from voice_flow.injector import ClipboardInjector, get_active_window_title, get_window_class_name
from voice_flow.overlay import FloatingOverlayBar
from voice_flow.polisher import polisher, AI_POLISH_DETERMINISTIC_RESERVE_SECONDS
from voice_flow.storage import storage
from voice_flow.style_engine import get_window_title_for_hwnd, style_engine
from voice_flow.text_processing import apply_spoken_punctuation, cleanup_text, format_dictated_email, smart_format, split_press_enter
from voice_flow.stream_stt import StreamTranscriber
from voice_flow.transcriber import Transcriber
from voice_flow.voice_commands import detect_voice_command
from voice_flow.correction_learning import extract_correction_pairs
from voice_flow.recovery import AudioArchive, AUDIO_RETENTION_SECONDS, MIN_RETRY_SECONDS

# Hide console window on Windows immediately so the application runs silently in the background
if sys.platform == "win32":
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            if "--show-console" not in sys.argv:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # 0 = SW_HIDE
    except Exception:
        pass

# Fix UTF-8 encoding on Windows console. Only rewrap streams that are real
# non-UTF-8 consoles: wrapping a redirected stream (pytest capture, pipes)
# takes ownership of its buffer and closes it on GC, poisoning the host.
if sys.platform == "win32":
    try:
        for _name in ("stdout", "stderr"):
            _stream = getattr(sys, _name)
            _encoding = (_stream.encoding or "").lower().replace("-", "") if getattr(_stream, "encoding", None) else ""
            if hasattr(_stream, "buffer") and _encoding not in ("utf-8", "utf8"):
                setattr(sys, _name, io.TextIOWrapper(_stream.buffer, encoding="utf-8", errors="backslashreplace"))
    except Exception:
        pass

log_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "voice_flow_debug.log"))
try:
    from voice_flow import runtime_env as _runtime_env

    if _runtime_env.is_installed():
        from voice_flow.paths import data_dir as _data_dir

        _log_dir = _data_dir() / "logs"
        _log_dir.mkdir(parents=True, exist_ok=True)
        log_file_path = str(_log_dir / "voice_flow_debug.log")
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file_path, mode="a", encoding="utf-8")
    ],
)

log = logging.getLogger("voice_flow.main")

try:
    from voice_flow.crash_reporting import init_crash_reporting
    init_crash_reporting()
except Exception:
    pass
_AUDIO_FLOW_JOBS_INIT_LOCK = threading.Lock()


class DictationState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    ERROR = "error"


# The release-to-paste target bounds only optional streaming harvest.  It is
# never a deadline for the complete recording: throwing away spoken words to
# meet a stopwatch is worse than waiting for the bounded STT provider once.
# Individual provider calls retain their own duration-aware limits.
# Sized for the local-Nemotron case: minus the 1.0s recovery reserve and the
# 0.3s injection reserve this leaves ~2.7s of harvest, enough for one 8s tail
# chunk (~1.5-1.8s) plus in-flight chunks to drain instead of being discarded.
POST_RELEASE_WORK_BUDGET_SECONDS = 4.0
INJECTION_RESERVE_SECONDS = 0.3
# Cloud transcription keeps the full recovery window, while optional cleanup
# shares a separate two-second interactive release target.
CLOUD_INTERACTIVE_TARGET_SECONDS = 2.0
# Streaming is an optimization. Always preserve a fixed slice of the shared
# budget for one complete-recording recovery attempt before injection.
WHOLE_BUFFER_RECOVERY_RESERVE_SECONDS = 1.0


def _complete_recording_budget_seconds(duration: float) -> float:
    """Bound one full-recording recovery by audio length, never by UI target."""
    return min(30.0, max(6.0, 4.0 + max(0.0, duration) * 0.25))


def _normalize_polish_speed_mode(mode: str | None) -> str:
    """Normalize polish speed mode to one of 'fast', 'balanced', or 'quality'.

    Persisted settings use the canonical lower-case identifiers. Display
    labels and unknown inputs cleanly map to 'balanced'.
    """
    normalized = str(mode or "").strip().lower()
    if normalized in ("fast", "balanced", "quality"):
        return normalized
    return "balanced"


def _polish_budget_seconds(mode_or_words: Any = "balanced", word_count: int | None = None) -> float:
    """Return the maximum interactive cleanup allowance for the selected mode.

    Recognition keeps its complete-recording recovery window. Polishing gets
    a fresh allowance and returns immediately when its provider is ready.
    Supports both (mode, word_count) and (word_count) signatures.
    """
    if word_count is None:
        if isinstance(mode_or_words, (int, float)):
            words = max(0, int(mode_or_words))
            try:
                mode = storage.get_setting("voice_flow_polish_speed_mode", "balanced")
            except Exception:
                mode = "balanced"
        elif isinstance(mode_or_words, str) and mode_or_words.strip().isdigit():
            words = max(0, int(mode_or_words.strip()))
            try:
                mode = storage.get_setting("voice_flow_polish_speed_mode", "balanced")
            except Exception:
                mode = "balanced"
        else:
            mode = str(mode_or_words or "balanced")
            words = 0
    else:
        mode = str(mode_or_words or "balanced")
        try:
            words = max(0, int(word_count))
        except (TypeError, ValueError):
            words = 0

    mode = _normalize_polish_speed_mode(mode)

    # Ceilings, never sleeps: the old sub-second limit cancelled healthy AI.
    base = {"fast": 3.0, "balanced": 5.0, "quality": 8.0}[mode]
    return base + min(4.0, max(0, words - 80) / 100.0)


def _is_cloud_stt_model(model_ref: object) -> bool:
    """Whether a session model is a remotely executed STT provider."""
    value = str(model_ref or "").strip()
    return bool(value and not value.lower().startswith("local/"))


def _polish_deadline(
    post_release_deadline: float,
    speed_mode: str | None,
    word_count: int,
    *,
    cloud_stt: bool,
    requires_ai: bool = False,
    polish_model_ref: str | None = None,
) -> float:
    """Give local and cloud transcripts a fresh, model-aware polishing attempt.

    The allowance is a *ceiling*, never a delay: the polisher returns as soon
    as the provider answers.  A per-model latency profile (see
    ``polish_latency``) means a model that has answered in 900 ms is not given
    an arbitrary 5 s window, while a slower model is not cancelled mid-answer.
    """
    try:
        from voice_flow.polish_latency import ceiling_for

        budget = ceiling_for(
            polish_model_ref,
            mode=_normalize_polish_speed_mode(speed_mode),
            word_count=word_count,
        )
    except Exception:
        budget = _polish_budget_seconds(speed_mode, word_count)
    if requires_ai:
        budget = max(budget, 6.0)
    return time.monotonic() + budget


def _polishing_enabled() -> bool:
    """Read the persisted switch without treating legacy string values as true."""
    try:
        value = storage.get_setting("polishing_enabled", True)
    except Exception:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    return value == 1


def _warm_voice_gemini_transport(model_ref: object) -> None:
    """Warm only the selected remote Gemini transport after capture is live."""
    try:
        if not _polishing_enabled():
            return
        selected = str(model_ref or "").strip()
        if selected.lower().startswith("gemini/"):
            from voice_flow.voice_gemini_transport import warm_gemini_connection
            threading.Thread(target=warm_gemini_connection, name="voice-gemini-prewarm", daemon=True).start()
            return
    except Exception:
        return


def _capture_transition(method):
    """Serialize mic ownership changes, without blocking provider workers."""
    from functools import wraps

    @wraps(method)
    def call(self, *args, **kwargs):
        with self._state_lock:
            lock = getattr(self, "_capture_transition_lock", None)
            if lock is None:
                lock = self._capture_transition_lock = threading.RLock()
        with lock:
            return method(self, *args, **kwargs)
    return call


def _call_with_optional_deadline(func, *args, deadline: float | None = None, **kwargs):
    """Call a provider with the new deadline kwarg, retaining old fakes.

    The transcriber/polisher APIs are implemented by optional integrations and
    a number of tests provide one-argument fakes.  Retry without the kwarg only
    when Python rejected that kwarg; an unrelated TypeError must still surface
    to the caller instead of being hidden as a compatibility fallback.
    """
    call_kwargs = dict(kwargs)
    if deadline is not None:
        call_kwargs["deadline"] = deadline
    while True:
        try:
            return func(*args, **call_kwargs)
        except TypeError as exc:
            message = str(exc).lower()
            unsupported = next(
                (key for key in ("model_ref", "deadline", "overlap_prefix_seconds", "task", "overrides", "speed_mode", "outcome_callback") if key in call_kwargs and key in message and "keyword" in message),
                None,
            )
            if unsupported is None:
                raise
            call_kwargs.pop(unsupported)


@dataclass(frozen=True)
class DictationSession:
    """Immutable target and style snapshot for one dictation session."""

    target_hwnd: int | None
    app_title: str
    app_category: str
    style_id: str
    started_at: float
    cleanup_level: str = "cleanup_light"
    cursor_context: Any = None
    press_enter_enabled: bool = False
    resolved_style: Any = None
    stt_model_ref: str | None = None
    polish_model_ref: str | None = None
    polish_speed_mode: str | None = None
    model_resource_lease: Any = None


from voice_flow.tts_engine import tts_engine
from voice_flow.audio_flow_widget import audio_flow_widget
from voice_flow.video_flow_widget import video_flow_widget

_MODULE_SETTINGS_CACHE: dict[str, tuple[float, Any]] = {}
_MODULE_SETTINGS_CACHE_LOCK = threading.Lock()


def get_cached_setting(key: str, default: Any = None, ttl: float = 5.0) -> Any:
    """Read a setting from storage with an in-memory TTL cache to avoid SQLite thrash."""
    now = time.monotonic()
    with _MODULE_SETTINGS_CACHE_LOCK:
        cached = _MODULE_SETTINGS_CACHE.get(key)
        if cached is not None:
            cached_time, val = cached
            if now - cached_time < ttl:
                return val
    try:
        val = storage.get_setting(key, default)
    except Exception:
        val = default
    with _MODULE_SETTINGS_CACHE_LOCK:
        _MODULE_SETTINGS_CACHE[key] = (now, val)
    return val


def _polish_outcome_label(outcome: str) -> str:
    """Describe delivery without claiming a failed AI pass was successful."""
    return {
        "ai_accepted": "AI polished",
        "local": "Cleaned locally",
        "local_model": "Cleaned locally (offline model)",
        "local_format": "Formatted locally",
        "local_rewrite": "Rewritten locally",
        "local_paragraphs": "Paragraphs added locally",
        "local_preserved": "Wording preserved locally",
        "disabled": "Basic cleanup applied",
        "timeout": "AI timed out — basic cleanup applied",
        "provider_failure": "AI unavailable — basic cleanup applied",
        "fidelity_reject": "AI output rejected — basic cleanup applied",
        "command_unfulfilled": "Voice command could not be completed — basic cleanup applied",
    }.get(str(outcome or ""), "AI unavailable — basic cleanup applied")


_LOCAL_BULLET_BREAK_RE = re.compile(
    r"(?:\n+|;\s*|(?:,\s+(?:and\s+)?|(?<=[.!?])\s+)(?=(?:we\s+)?(?:need\s+to\s+)?"
    r"(?:send|review|schedule|prepare|draft|share|confirm|call|follow\s+up)\b))",
    re.IGNORECASE,
)


def _format_dictated_bullets(text: str) -> str | None:
    """Add bullets only around explicit dictated list items; never re-author."""
    from voice_flow.text_processing import _PROTECTED_CLEANUP_SPAN_RE
    pieces = [""]
    for index, span in enumerate(_PROTECTED_CLEANUP_SPAN_RE.split(text or "")):
        if index % 2:
            pieces[-1] += span
        else:
            chunks = _LOCAL_BULLET_BREAK_RE.split(span)
            pieces[-1] += chunks[0]
            pieces.extend(chunks[1:])
    pieces = [piece.strip(" ,;\t") for piece in pieces]
    pieces = [piece for piece in pieces if piece]
    if len(pieces) < 2:
        return None
    return "\n".join(f"- {piece}" for piece in pieces)


def _format_dictated_prompt(text: str) -> str | None:
    """Give a request a safe prompt wrapper without inventing requirements."""
    body = (text or "").strip()
    return f"Task:\n{body}" if body else None


_PARAGRAPH_MARKER_RE = re.compile(
    r"\s+((?:and\s+also|and\s+first\s+of\s+all|and\s+another\s+thing|and\s+finally|"
    r"also|first\s+of\s+all|another\s+thing|"
    r"on\s+top\s+of\s+that|finally)\b)",
    re.IGNORECASE,
)
_PARAGRAPH_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _format_safe_paragraphs(text: str) -> str:
    """Add readable paragraphs to long plain dictation without changing words."""
    source = text or ""
    if (
        len(source.split()) < 35
        or "\n" in source
        or "`" in source
        or re.search(r"[\"“”][^\"“”]{2,}[\"“”]", source)
    ):
        return source
    marked = _PARAGRAPH_MARKER_RE.sub(lambda match: "\n\n" + match.group(1), source)
    if marked != source:
        return marked
    sentences = _PARAGRAPH_SENTENCE_RE.split(source)
    return "\n\n".join(part.strip() for part in sentences) if len(sentences) >= 3 else source


def _processing_metadata(
    *,
    polish_outcome: str,
    polish_elapsed: float,
    resolved_style: Any,
    effective_style: Any,
    command: Any,
    polishing_enabled: bool,
    dictionary_trace: list[dict[str, str]] | None = None,
    polish_attempt_outcome: str | None = None,
) -> dict[str, Any]:
    """Build the stable, user-readable record of one dictation's outcome."""
    outcome = str(polish_outcome or "provider_failure")
    style_applied = outcome in {"ai_accepted", "local", "local_model", "local_format", "local_rewrite", "local_preserved"}
    command_label = ""
    if command is not None:
        try:
            command_label = str(command.label() or "")
        except Exception:
            command_label = ""
    if not polishing_enabled:
        command_status = "disabled"
    elif command is None:
        command_status = "not_detected"
    elif style_applied:
        command_status = "applied"
    else:
        command_status = "not_applied"

    base_style_id = getattr(resolved_style, "style_id", "") or ""
    effective_style_id = getattr(effective_style, "style_id", None) or base_style_id
    effective_label = getattr(effective_style, "label", "") or ""
    trace = [
        {"from": str(item.get("from", "")), "to": str(item.get("to", ""))}
        for item in (dictionary_trace or [])
        if isinstance(item, dict) and item.get("from") and item.get("to")
    ]
    return {
        "schema_version": 1,
        "polish": {
            "outcome": outcome,
            "display": _polish_outcome_label(outcome),
            "duration_ms": max(0, round(float(polish_elapsed) * 1000)),
            **({"attempt_outcome": str(polish_attempt_outcome)} if polish_attempt_outcome else {}),
        },
        "style": {
            "requested_id": str(base_style_id),
            "effective_id": str(effective_style_id),
            "label": str(effective_label),
            "applied": style_applied,
        },
        "command": {
            "label": command_label,
            "status": command_status,
        },
        "dictionary": {"count": len(trace), "replacements": trace},
    }


def _command_only_processing_metadata(
    *, resolved_style: Any, command: Any, status: str, display: str
) -> dict[str, Any]:
    """Persist command-only outcomes without claiming text was polished."""
    style_id = getattr(resolved_style, "style_id", "") or ""
    command_label = ""
    try:
        command_label = str(command.label() or "")
    except Exception:
        pass
    return {
        "schema_version": 1,
        "polish": {"outcome": "command_only", "display": str(display), "duration_ms": 0},
        "style": {"requested_id": str(style_id), "effective_id": str(style_id), "label": "", "applied": False},
        "command": {"label": command_label, "status": status},
        "dictionary": {"count": 0, "replacements": []},
    }


class VoiceFlowApp:
    """Core Coordinator for Voice Flow Dictation System."""

    def __init__(self) -> None:
        log.info("Starting Voice Flow System Engine...")
        self._state_lock = threading.RLock()
        self._settings_cache: dict[str, tuple[float, Any]] = {}
        self._settings_cache_lock = threading.Lock()
        self.state = DictationState.IDLE
        self.last_successful_transcript: str | None = None
        self.recent_dictations: set[str] = set()
        self._record_watchdog: threading.Timer | None = None
        self._selection_generation = 0
        self.archive = AudioArchive()
        self.archive.purge_expired()

        self.overlay = FloatingOverlayBar()
        try:
            self.overlay.load_saved_position()
        except Exception as _pos_err:
            log.debug("Could not load saved overlay position: %s", _pos_err)
        self.overlay._main_thread_id = threading.get_ident()
        try:
            self.overlay._create_window()
        except Exception as _tk_err:
            log.debug("Early overlay window creation skipped: %s", _tk_err)
        self.injector = ClipboardInjector()
        self.processing_lock = threading.Lock()
        self._audio_summary_generation = 0
        self._active_summary_player_token: str | None = None
        self._read_generation = 0
        self._read_generation_lock = threading.RLock()
        self._audio_summary_launch_reservation: str | None = None
        self._read_active = False
        self._read_pending = False
        self._audio_summary_payloads: dict[str, dict[str, str]] = {}
        self._audio_flow_jobs = None
        self._audio_flow_jobs_lock = threading.Lock()
        self.video_stage = ""

        # Ensure local REST API server is always active in background immediately for UI & signaling
        self._api_server_thread: threading.Thread | None = None
        try:
            from voice_flow.gui.api_server import start_api_server, register_runtime_controller
            register_runtime_controller(self)
            self._api_server_thread = threading.Thread(target=start_api_server, daemon=True, name="VoiceFlowApiServer")
            self._api_server_thread.start()
        except Exception as exc:
            log.warning("Could not start embedded API server: %s", exc)

        # Load SQLite dictation history into recent_dictations to prevent Audio Flow from ever reading dictations
        try:
            for r in storage.get_recent_history():
                raw = r.get("raw_text")
                pol = r.get("polished_text")
                if raw and raw.strip():
                    self.recent_dictations.add(raw.strip())
                if pol and pol.strip():
                    self.recent_dictations.add(pol.strip())
        except Exception:
            pass

        # Start NotebookLM keepalive daemon in background so Google cookies stay fresh
        try:
            from voice_flow.video_flow_engine.notebooklm import start_keepalive_daemon
            start_keepalive_daemon()
        except Exception as kexc:
            log.debug("Keepalive daemon init skipped: %s", kexc)

        # Availability is resolved when capture starts. Keep disconnected picks
        # so reconnect/restart cannot silently replace the user's microphone.
        from voice_flow.microphone_devices import load_microphone_preference
        config.selected_mic_device = load_microphone_preference(storage)
        self._runtime_preferences_token = (id(storage), getattr(storage, "db_path", None))
        self.transcriber = Transcriber()
        self.audio = AudioRecorder()
        # Streaming dictation: transcribe silence-delimited chunks while the
        # user still speaks; on release only the tail chunk remains.
        self._stream_stt = StreamTranscriber(self.transcriber)
        self.audio.on_chunk_closed = self._on_stream_chunk_closed
        # Voice Flow command layer: a scope="next" command ("make what I say
        # next an email") waits here for the following dictation.
        self._pending_command = None
        # Learned-vocabulary bridge: old Auto-Captured words become approvable
        # suggestions once; Voice Flow sound-alike corrections get seeded.
        try:
            migrated = storage.migrate_learned_vocabulary()
            if migrated:
                log.info("[LEARNING] promoted %d auto-captured terms to suggestions", migrated)
        except Exception:
            log.exception("[LEARNING] vocabulary migration failed")
        self._selection_generation = 0

        # Start NotebookLM background keepalive & silent session auto-refresh daemon
        try:
            from voice_flow.video_flow_engine.notebooklm import start_keepalive_daemon, trigger_keepalive_now
            start_keepalive_daemon()
            trigger_keepalive_now(force=False, background=True)
        except Exception as exc:
            log.debug("NotebookLM keepalive __init__ startup trigger: %s", exc)

        # Connect Input Trigger Listener with expanded actions
        self.hotkeys = InputTriggerListener(
            on_start=self._on_dictation_start,
            on_finish=self._on_dictation_finish,
            on_cancel=self._on_dictation_cancel,
            on_paste_last=self._paste_last_transcript,
            on_copy_last=self._copy_last_transcript,
            on_audio_flow=self._process_audio_flow_pipeline,
            on_mouse_release=self._on_mouse_release,
            has_pending_deferred_paste=lambda: self.has_pending_deferred_paste,
        )

        # Connect Overlay Action Buttons
        self.overlay.on_start_click = self._on_dictation_start
        self.overlay.on_finish_click = self._on_dictation_finish
        self.overlay.on_cancel_click = self._on_dictation_cancel
        self.overlay.on_listen_selected = lambda text: self._process_audio_flow_pipeline(text_override=text, mode="default")
        self.overlay.on_video_flow = lambda text: self._process_video_flow_pipeline("summary", text)
        self.overlay.on_video_ready = lambda video_id: video_flow_widget.open_player(video_id)
        self.overlay.on_video_cancel = self._cancel_video_from_screen
        self.overlay.on_audio_pause_toggle = self._toggle_audio_flow_pause
        self.overlay.on_audio_stop = self._stop_audio_flow_pipeline
        self.overlay.on_audio_summary_cancel = self.cancel_audio_summary_job
        self.overlay.on_audio_summary_ready = self.open_audio_summary_job
        self.overlay.on_open_settings = self._open_audio_flow_settings

        # Connect Audio Flow Floating Widget
        audio_flow_widget.on_trigger = lambda text, mode="full", summary_depth=None: self._process_audio_flow_pipeline(text_override=text, mode=mode, summary_depth=summary_depth)
        audio_flow_widget.on_stop = lambda: self._stop_audio_flow_pipeline()
        # Read playback deliberately has a stop-only control. Generated summaries
        # use their own seekable HTML audio player.
        audio_flow_widget.on_pause_toggle = lambda: self._stop_audio_flow_pipeline()
        audio_flow_widget.on_speed_change = lambda speed: (tts_engine.set_speed(speed), self.overlay.refresh() if hasattr(self.overlay, "refresh") else None)
        audio_flow_widget.on_voice_change = lambda v: storage.save_setting("exec_audio_policy_model", v)
        video_flow_widget.on_generate = self._queue_video_from_screen

    @property
    def has_pending_deferred_paste(self) -> bool:
        return bool(getattr(self, "_pending_deferred_transcript", None))

    def _get_cached_setting(self, key: str, default: Any = None, ttl: float = 5.0) -> Any:
        """Fetch setting from memory cache with a TTL (default 5s) to avoid SQLite contention."""
        cache = getattr(self, "_settings_cache", None)
        if cache is None:
            cache = self._settings_cache = {}
        lock = getattr(self, "_settings_cache_lock", None)
        if lock is None:
            lock = self._settings_cache_lock = threading.Lock()

        now = time.monotonic()
        token = (id(storage), getattr(storage, "db_path", None))
        with lock:
            revisions = getattr(self, "_settings_cache_revisions", None)
            if revisions is None:
                revisions = self._settings_cache_revisions = {}
            revision = revisions.get(key, 0)
            if getattr(self, "_settings_cache_token", None) != token:
                cache.clear()
                self._settings_cache_token = token
            cached = cache.get(key)
            if cached is not None:
                cached_time, val = cached
                if now - cached_time < ttl:
                    return val

        try:
            val = storage.get_setting(key, default)
        except Exception:
            val = default

        with lock:
            if (token == (id(storage), getattr(storage, "db_path", None))
                    and getattr(self, "_settings_cache_token", None) == token
                    and revisions.get(key, 0) == revision):
                cache[key] = (now, val)
        return val

    def invalidate_cached_setting(self, key: str) -> None:
        """Make an explicitly saved preference visible on its next runtime read."""
        lock = getattr(self, "_settings_cache_lock", None)
        if lock is None:
            return
        with lock:
            getattr(self, "_settings_cache", {}).pop(key, None)
            revisions = getattr(self, "_settings_cache_revisions", None)
            if revisions is None:
                revisions = self._settings_cache_revisions = {}
            # A read begun before this save must not restore the stale value.
            revisions[key] = revisions.get(key, 0) + 1

    get_setting_cached = _get_cached_setting

    @property
    def is_recording(self) -> bool:
        with self._state_lock:
            return self.state == DictationState.RECORDING

    def set_flow_bar_visible(self, visible: bool) -> bool:
        """Runtime hook for the Hub; hiding the bar deliberately leaves hotkeys live."""
        return self.overlay.set_visible(visible)

    def set_flow_bar_dock(self, dock: str) -> bool:
        """Runtime hook for the Hub's persisted Flow Bar location."""
        return self.overlay.set_dock(dock)

    def sync_runtime_preferences(self) -> None:
        """Apply the active account's next-session preferences without opening devices."""
        with self._state_lock:
            if self.state != DictationState.IDLE:
                raise RuntimeError("Runtime preferences require an idle dictation session")
            from voice_flow.microphone_devices import load_microphone_preference
            preference = load_microphone_preference(storage)
            token = (id(storage), getattr(storage, "db_path", None))
            lock = getattr(self, "_settings_cache_lock", None)
            if lock is None:
                lock = self._settings_cache_lock = threading.Lock()
            with lock:
                self._settings_cache = {}
                self._settings_cache_token = token
            config.selected_mic_device = preference
            hotkeys = getattr(self, "hotkeys", None)
            if callable(getattr(hotkeys, "reload_config", None)):
                hotkeys.reload_config()
            overlay = getattr(self, "overlay", None)
            if overlay is not None:
                if callable(getattr(overlay, "load_saved_position", None)):
                    # A new account with no saved position must not inherit
                    # another account's dragged anchor.
                    overlay._user_pos = None
                    overlay.load_saved_position()
                if callable(getattr(overlay, "refresh", None)):
                    overlay.refresh()
            self._runtime_preferences_token = token

    def reload_hotkeys(self, settings: dict[str, Any] | None = None) -> None:
        """Live reload hotkeys listener with updated user settings."""
        if hasattr(self, "hotkeys") and self.hotkeys is not None:
            self.hotkeys.reload_config(settings)

    def _is_internal_window(self, hwnd: int | None) -> bool:
        """Check if hwnd belongs to Voice Flow / AI Productivity Flow itself (overlay bar, main window, settings)."""
        overlay_id = None
        overlay_win = getattr(getattr(self, "overlay", None), "win", None)
        if overlay_win:
            try:
                overlay_id = overlay_win.winfo_id()
            except Exception:
                pass
        from voice_flow.injector import is_internal_window
        return is_internal_window(hwnd, overlay_hwnd=overlay_id)

    def _get_current_external_window(self) -> int | None:
        """Retrieve the currently focused foreground window if it is a valid external user app."""
        if sys.platform != "win32":
            return None
        try:
            fg = ctypes.windll.user32.GetForegroundWindow()
            if not fg or not ctypes.windll.user32.IsWindow(fg):
                return None
            if self._is_internal_window(fg):
                return None
            return fg
        except Exception:
            return None

    def _get_effective_destination_hwnd(self, session, fallback_hwnd: int | None = None) -> int | None:
        """Dynamically resolve the intended destination window for injection.

        Prioritizes the active external window where the user is currently focused or working,
        falling back to the session target or last known external window if Voice Flow's overlay
        is focused. Refuses to return any internal application window.
        """
        current_ext = self._get_current_external_window()
        if current_ext:
            self._last_target_hwnd = current_ext
            return current_ext
        if not IS_WINDOWS:
            return None
        user32 = windll.user32
        last_known = getattr(self, "_last_target_hwnd", None)
        if last_known and user32.IsWindow(last_known) and not self._is_internal_window(last_known):
            return last_known
        session_target = getattr(session, "target_hwnd", None) or (session.get("hwnd") if isinstance(session, dict) else None)
        if session_target and user32.IsWindow(session_target) and not self._is_internal_window(session_target):
            return session_target
        if fallback_hwnd and user32.IsWindow(fallback_hwnd) and not self._is_internal_window(fallback_hwnd):
            return fallback_hwnd
        return None

    def _start_window_tracker(self, session) -> None:
        """Background tracker to record active external window changes while user dictates."""
        def _tracker():
            while self.state == DictationState.RECORDING and getattr(self, "session", None) is session:
                try:
                    ext = self._get_current_external_window()
                    if ext:
                        self._last_target_hwnd = ext
                except Exception:
                    pass
                time.sleep(0.1)
        threading.Thread(target=_tracker, name="voice-window-tracker", daemon=True).start()

    def _capture_target_hwnd(self) -> int | None:
        """Freeze the destination before recording UI can change focus."""
        hwnd = None
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
        except Exception:
            hwnd = None

        # If foreground is the overlay bar or an internal app window, fall back to last known external app
        if self._is_internal_window(hwnd):
            hwnd = getattr(self, "_last_target_hwnd", None)
            if self._is_internal_window(hwnd):
                hwnd = None
        elif hwnd:
            self._last_target_hwnd = hwnd

        return hwnd

    def _capture_session(self) -> DictationSession:
        """Resolve advisory context after capture, using its frozen destination."""
        pending = getattr(self, "session", None)
        if self.state == DictationState.RECORDING and isinstance(pending, DictationSession):
            hwnd = pending.target_hwnd
        else:
            hwnd = self._capture_target_hwnd()

        title = (get_window_title_for_hwnd(hwnd) if hwnd else None) or get_active_window_title() or "General App"
        try:
            resolved = style_engine.resolve_for_target(hwnd) if hwnd else None
        except Exception as exc:
            # Target metadata is advisory.  A transient Win32/style lookup
            # failure must never prevent the microphone from starting.
            log.warning("Could not resolve target style: %s", exc)
            resolved = None
        app_name = resolved.app_name if resolved else "General App"
        app_category = resolved.category if resolved else "smart_clean"
        style_id = resolved.style_id if resolved else "smart_clean"

        try:
            press_enter_enabled = storage.get_setting("press_enter_enabled", False)
        except Exception as exc:
            log.warning("Could not read press-enter setting; using disabled: %s", exc)
            press_enter_enabled = False
        try:
            cleanup_level = str(storage.get_setting("style_autocleanup", "cleanup_light"))
        except Exception as exc:
            log.warning("Could not read cleanup setting; using light cleanup: %s", exc)
            cleanup_level = "cleanup_light"
        try:
            stt_model_ref = str(storage.get_setting("voice_flow_stt_model", "local/faster-whisper-base.en") or "")
            polish_model_ref = str(storage.get_setting("voice_flow_polish_model", "local/deterministic") or "")
            print(f"[SESSION] Snapshotted STT model='{stt_model_ref}' polish='{polish_model_ref}' for app='{app_name}'")
        except Exception as exc:
            log.warning("Could not snapshot dictation models; using provider defaults: %s", exc)
            stt_model_ref = ""
            polish_model_ref = ""
        try:
            polish_speed_mode = _normalize_polish_speed_mode(storage.get_setting("voice_flow_polish_speed_mode", "balanced"))
        except Exception:
            polish_speed_mode = "balanced"
        return DictationSession(
            target_hwnd=hwnd,
            app_title=app_name,
            app_category=app_category,
            style_id=style_id,
            started_at=time.time(),
            cleanup_level=cleanup_level if cleanup_level.startswith("cleanup_") else "cleanup_light",
            press_enter_enabled=bool(press_enter_enabled),
            resolved_style=resolved,
            stt_model_ref=stt_model_ref or None,
            polish_model_ref=polish_model_ref or None,
            polish_speed_mode=polish_speed_mode,
        )

    def _streaming_stt_enabled(self) -> bool:
        if os.environ.get("VOICE_FLOW_STREAMING_STT", "").strip().lower() in {"0", "false", "no", "off"}:
            return False
        try:
            return bool(storage.get_setting("voice_flow_streaming_stt", True))
        except Exception:
            return True

    def _set_session_model_resource_lease(self, session: Any, lease: Any) -> Any:
        """Attach one speech-demand lease without losing immutable session data."""
        if session is None:
            release = getattr(lease, "release", None)
            if callable(release):
                release()
            raise RuntimeError("Cannot attach model demand to a missing dictation session")
        if hasattr(session, "__dataclass_fields__"):
            try:
                owned = replace(session, model_resource_lease=lease)
                if getattr(owned, "model_resource_lease", None) is lease:
                    return owned
            except (TypeError, ValueError):
                pass
        if isinstance(session, dict):
            session["model_resource_lease"] = lease
            if session.get("model_resource_lease") is lease:
                return session
        else:
            try:
                setattr(session, "model_resource_lease", lease)
                if getattr(session, "model_resource_lease", None) is lease:
                    return session
            except Exception:
                pass
        release = getattr(lease, "release", None)
        if callable(release):
            release()
        raise RuntimeError("Dictation session cannot own its speech-model demand")

    @staticmethod
    def _release_session_model_resource(session: Any) -> None:
        """Idempotently end one session's model demand, including test/plugin sessions."""
        if session is None:
            return
        lease = (
            session.get("model_resource_lease")
            if isinstance(session, dict)
            else getattr(session, "model_resource_lease", None)
        )
        release = getattr(lease, "release", None)
        if callable(release):
            try:
                release()
            except Exception:
                log.debug("Could not release session model demand", exc_info=True)
        if isinstance(session, dict):
            session["model_resource_lease"] = None
        else:
            try:
                setattr(session, "model_resource_lease", None)
            except Exception:
                # Frozen dataclasses retain the already-released idempotent
                # token so dataclasses.replace continues to preserve ownership.
                pass

    def _on_stream_chunk_closed(self, chunk: Any, native_sr: int, *, overlap_prefix_seconds: float = 0.0) -> None:
        """Audio-callback thread -> background transcription of a closed chunk."""
        try:
            _call_with_optional_deadline(
                self._stream_stt.submit_native,
                chunk,
                native_sr,
                overlap_prefix_seconds=max(0.0, float(overlap_prefix_seconds or 0.0)),
            )
        except Exception as exc:
            log.debug("[STREAM STT] submit failed: %s", exc)

    def _start_stream_for_session(self, session) -> None:
        from voice_flow.flux_stream import FluxStreamTranscriber, NovaStreamTranscriber
        from voice_flow.nemotron_engine import NemotronStreamTranscriber, is_nemotron_model

        model_ref = getattr(session, "stt_model_ref", None)
        self.audio.on_audio_frame = None
        is_cloud = bool(model_ref and not str(model_ref).lower().startswith("local/"))
        if is_cloud:
            try:
                from voice_flow import stt_engines
                stt_engines.prewarm_cloud_stt(model_ref, force=True)
            except Exception:
                pass
            self.audio.split_silence_seconds = 0.28
            self.audio.max_chunk_seconds = 4.0
        else:
            self.audio.split_silence_seconds = 0.35
            self.audio.max_chunk_seconds = 8.0
        if not self._streaming_stt_enabled():
            return
        if str(model_ref or "").lower().startswith("deepgram/flux-"):
            self._stream_stt = FluxStreamTranscriber()
            self.audio.on_audio_frame = self._stream_stt.submit_frame
        elif str(model_ref or "").lower().startswith("deepgram/nova-3"):
            self._stream_stt = NovaStreamTranscriber()
            self.audio.on_audio_frame = self._stream_stt.submit_frame
        elif is_nemotron_model(model_ref):
            self._stream_stt = NemotronStreamTranscriber()
            self.audio.on_audio_frame = self._stream_stt.submit_frame
        elif isinstance(self._stream_stt, (FluxStreamTranscriber, NovaStreamTranscriber, NemotronStreamTranscriber)):
            self._stream_stt = StreamTranscriber(self.transcriber)
        _call_with_optional_deadline(self._stream_stt.start_session, model_ref=model_ref)
        self._stream_session_owner = session

    def _set_hotkeys_recording_state(self, recording: bool) -> None:
        """Best-effort hotkey synchronization; never mask pipeline cleanup."""
        try:
            hotkeys = getattr(self, "hotkeys", None)
            if hotkeys is not None:
                hotkeys.set_recording_state(recording)
        except Exception as exc:
            log.warning("Could not synchronize hotkey recording state: %s", exc)

    def _reset_to_idle(self, session: Any = None) -> bool:
        """Reset one session without clobbering a newer dictation."""
        with self._state_lock:
            if session is not None and getattr(self, "session", None) is not session:
                return False
            self.state = DictationState.IDLE
            self.session = None
            self._processing_start_time = 0.0
        self._set_hotkeys_recording_state(False)
        if hasattr(self, "audio") and self.audio is not None:
            self.audio.split_silence_seconds = 0.35
            self.audio.max_chunk_seconds = 8.0
        return True

    def _session_was_cancelled(self, session: Any) -> bool:
        return id(session) in getattr(self, "_cancelled_session_ids", set())

    def _end_stream_session(self, discard: bool = False, owner: Any = None) -> None:
        """Close streaming STT safely on every finish, error, and cancel path."""
        if owner is not None and getattr(self, "_stream_session_owner", owner) is not owner:
            return
        stream = getattr(self, "_stream_stt", None)
        if stream is None:
            return
        try:
            stream.end_session()
        except Exception as exc:
            log.debug("[STREAM STT] end_session cleanup failed: %s", exc)
        if discard:
            try:
                stream.discard()
            except Exception as exc:
                log.debug("[STREAM STT] discard cleanup failed: %s", exc)

    @staticmethod
    def _stream_had_failures(stream: Any) -> bool:
        """Return whether a stream result is unsafe to use as a full transcript.

        New stream workers expose ``had_failures()`` (or a complete-success
        probe) so a terminal failed chunk cannot be mistaken for a complete
        result merely because ``pending_count()`` reached zero.  Older workers
        have no probe and retain the historical behavior.
        """
        failure_probe = getattr(stream, "had_failures", None)
        if callable(failure_probe):
            try:
                if bool(failure_probe()):
                    return True
            except Exception as exc:
                log.warning("[STREAM STT] failure probe failed: %s", exc)
                return True
        pending_probe = getattr(stream, "pending_count", None)
        if callable(pending_probe):
            try:
                if pending_probe() > 0:
                    return False  # In progress is not a failed completion.
            except Exception:
                return True
        for probe_name in ("complete_success", "is_complete_success", "completed_successfully"):
            success_probe = getattr(stream, probe_name, None)
            if not callable(success_probe):
                continue
            try:
                result = success_probe()
            except Exception as exc:
                log.warning("[STREAM STT] %s probe failed: %s", probe_name, exc)
                return True
            if result is False:
                return True
        return False

    def _overlay_call(self, method: str, *args: Any, **kwargs: Any) -> None:
        """UI feedback is non-critical and must not corrupt dictation state."""
        try:
            callback = getattr(getattr(self, "overlay", None), method, None)
            if callback is not None:
                callback(*args, **kwargs)
        except Exception as exc:
            log.warning("Overlay %s failed: %s", method, exc)

    @_capture_transition
    def _on_dictation_start(self, mode: str = "ptt") -> bool:
        token = (id(storage), getattr(storage, "db_path", None))
        if getattr(self, "state", None) == DictationState.IDLE and getattr(self, "_runtime_preferences_token", None) != token:
            try:
                self.sync_runtime_preferences()
            except Exception as exc:
                log.warning("Could not sync active account preferences: %s", exc)
                self._set_hotkeys_recording_state(False)
                return False
        try:
            enabled = storage.get_setting("voice_flow_enabled", True)
        except Exception as exc:
            log.warning("Could not read Voice Flow feature toggle; keeping it enabled: %s", exc)
            enabled = True
        if not enabled:
            log.info("Voice Flow dictation is disabled via the feature toggle.")
            self._set_hotkeys_recording_state(False)
            return False

        target_hwnd = self._capture_target_hwnd()

        # Invalidate any pending text selection checks so Audio Flow cannot pop up
        # or inject Ctrl+C during dictation
        self._selection_generation = getattr(self, "_selection_generation", 0) + 1

        # Serialize the read stop and Voice ownership transition against a
        # background Read worker or summary autoplay launch.
        with self._get_read_generation_lock():
            try:
                audio_flow_widget.hide()
                self._stop_audio_flow_pipeline()
            except Exception as _af_err:
                log.debug("Audio flow suppression on dictation start skipped: %s", _af_err)

            with self._state_lock:
                if self.state == DictationState.PROCESSING:
                    proc_start = getattr(self, "_processing_start_time", 0.0)
                    elapsed = time.monotonic() - proc_start if proc_start > 0 else 999.0
                    if elapsed < 15.0:
                        log.info("Refusing new dictation start: active session is currently PROCESSING (elapsed %.2fs < 15.0s)", elapsed)
                        self._set_hotkeys_recording_state(False)
                        return False
                    log.warning("Cancelling genuinely stale PROCESSING session (elapsed %.2fs >= 15.0s) to service new dictation request.", elapsed)
                    self._on_dictation_cancel()
                elif self.state == DictationState.ERROR:
                    self._reset_to_idle()

                if self.state != DictationState.IDLE:
                    log.info("Refusing start dictation while in state %s", self.state)
                    self._set_hotkeys_recording_state(False)
                    return False
                session = DictationSession(
                    target_hwnd, "General App", "smart_clean", "smart_clean", time.time()
                )
                self.session = session
                self.state = DictationState.RECORDING

        hwnd = getattr(session, "target_hwnd", None) or (session.get("hwnd") if isinstance(session, dict) else None)
        app_title = getattr(session, "app_title", "General App") or (session.get("app_title") if isinstance(session, dict) else "General App")
        log.info("[RECORDING] Dictation triggered for target hwnd %s (%s)", hwnd, app_title)

        audio_started = False
        try:
            self._set_hotkeys_recording_state(True)

            # Start capture before provider/model preparation. The recorder
            # holds initial frames and closed chunks until the stream is armed.
            begin_buffering = getattr(self.audio, "begin_stream_input_buffering", None)
            if callable(begin_buffering):
                begin_buffering()
            audio_started = bool(self.audio.start())
            with self._state_lock:
                if getattr(self, "session", None) is not session or self.state != DictationState.RECORDING:
                    return False
            if not audio_started:
                watchdog = getattr(self, "_record_watchdog", None)
                if watchdog:
                    watchdog.cancel()
                self._record_watchdog = None
                discard_buffer = getattr(self.audio, "discard_stream_input_buffer", None)
                if callable(discard_buffer):
                    discard_buffer()
                self._end_stream_session(discard=True, owner=session)
                self._reset_to_idle(session)
                self._overlay_call("show_error", getattr(self.audio, "last_device_error", None) or "Microphone hardware failed to open")
                return False

            with self._state_lock:
                if getattr(self, "session", None) is not session or self.state != DictationState.RECORDING:
                    return False
                # Capture is now receiving words; context and provider startup
                # must not delay the user's recording feedback.
                self._overlay_call("show_recording", level_provider=lambda: self.audio.level)

            contextual_session = self._capture_session()
            with self._state_lock:
                if getattr(self, "session", None) is not session or self.state != DictationState.RECORDING:
                    return False
                self.session = contextual_session
                session = contextual_session

            from voice_flow.local_model_resources import acquire_model_use
            lease = acquire_model_use("speech")
            owned_session = self._set_session_model_resource_lease(session, lease)
            with self._state_lock:
                if getattr(self, "session", None) is session and self.state == DictationState.RECORDING:
                    self.session = owned_session
                    session = owned_session
                else:
                    # Capture ownership changed while the device was opening.
                    # End only this stale demand; a newer session may already
                    # own the shared recorder and hotkey state.
                    self._release_session_model_resource(owned_session)
                    return False

            prepare_model = getattr(getattr(self, "transcriber", None), "prepare_model_async", None)
            if callable(prepare_model):
                prepare_model(
                    getattr(session, "stt_model_ref", None)
                    or (session.get("stt_model_ref") if isinstance(session, dict) else None),
                    lease=lease,
                )

            # The timer carries the final immutable session (including its
            # lease), so a later recording cannot be finished by a stale timer.
            watchdog = getattr(self, "_record_watchdog", None)
            if watchdog:
                watchdog.cancel()
            self._record_watchdog = threading.Timer(20 * 60, self._finish_if_current, args=(session,))
            self._record_watchdog.daemon = True
            self._record_watchdog.start()

            self._start_stream_for_session(session)
            flush_buffer = getattr(self.audio, "flush_stream_input_buffer", None)
            if callable(flush_buffer):
                flush_buffer()
            # Polishing warm-up is advisory: do it after capture is live.
            threading.Thread(
                target=_warm_voice_gemini_transport,
                args=(getattr(session, "polish_model_ref", None),),
                name="voice-polish-warmup",
                daemon=True,
            ).start()
            # Track active external window switches during recording
            self._start_window_tracker(session)

            return True
        except Exception as exc:
            # Never leave a half-started session: reset watchdog, mic, hotkeys,
            # and state so the engine cannot get stuck in RECORDING.
            log.error("[START ERROR] %s", exc, exc_info=True)
            with self._state_lock:
                still_owned = getattr(self, "session", None) is session
            if not still_owned:
                self._release_session_model_resource(session)
                return False
            watchdog = getattr(self, "_record_watchdog", None)
            if watchdog:
                watchdog.cancel()
                self._record_watchdog = None
            if audio_started:
                try:
                    self.audio.stop()
                except Exception:
                    pass
            self._release_session_model_resource(session)
            discard_buffer = getattr(self.audio, "discard_stream_input_buffer", None)
            if callable(discard_buffer):
                discard_buffer()
            self._end_stream_session(discard=True, owner=session)
            self._reset_to_idle(session)
            self._overlay_call("show_error", f"Dictation could not start: {exc}"[:90])
            return False

    def _finish_if_current(self, session) -> None:
        with self._state_lock:
            if session is None or getattr(self, "session", None) is not session or self.state != DictationState.RECORDING:
                return
        self._on_dictation_finish()

    @_capture_transition
    def _on_dictation_finish(self) -> bool:
        session = None
        streaming = False
        post_release_deadline: float | None = None
        try:
            with self._state_lock:
                if self.state != DictationState.RECORDING:
                    return False
                session = getattr(self, "session", None)
                self.state = DictationState.PROCESSING
                self._processing_start_time = time.monotonic()
                self._release_started_at = time.perf_counter()

            # Resolve active external window at the instant dictation finishes
            current_ext = self._get_current_external_window()
            if current_ext:
                self._last_target_hwnd = current_ext
                dest_hwnd = current_ext
            else:
                last_k = getattr(self, "_last_target_hwnd", None)
                if last_k and not self._is_internal_window(last_k):
                    dest_hwnd = last_k
                else:
                    sess_t = getattr(session, "target_hwnd", None) if session else None
                    if sess_t and not self._is_internal_window(sess_t):
                        dest_hwnd = sess_t
                    else:
                        dest_hwnd = None

            if session and dest_hwnd and getattr(session, "target_hwnd", None) != dest_hwnd:
                new_style = None
                try:
                    new_style = style_engine.resolve_for_target(dest_hwnd)
                except Exception:
                    pass
                if hasattr(session, "__dataclass_fields__"):
                    try:
                        kwargs = {"target_hwnd": dest_hwnd}
                        if new_style:
                            kwargs["resolved_style"] = new_style
                            kwargs["app_title"] = new_style.app_name
                            kwargs["app_category"] = new_style.category
                            kwargs["style_id"] = new_style.style_id
                        session = replace(session, **kwargs)
                        self.session = session
                    except Exception:
                        pass
                elif isinstance(session, dict):
                    session["target_hwnd"] = dest_hwnd
                    if new_style:
                        session["resolved_style"] = new_style
                        session["app_title"] = new_style.app_name
                        session["app_category"] = new_style.category
                        session["style_id"] = new_style.style_id
            # Capture this once at release so the tail worker, stream harvest,
            # whole-buffer fallback, and polish all share one absolute clock.
            post_release_deadline = time.monotonic() + POST_RELEASE_WORK_BUDGET_SECONDS
            self._post_release_deadline = post_release_deadline
            watchdog = getattr(self, "_record_watchdog", None)
            if watchdog:
                watchdog.cancel()
                self._record_watchdog = None
            self._set_hotkeys_recording_state(False)

            streaming = self._streaming_stt_enabled()
            audio_buffer = None
            if streaming:
                # A short dictation that never closed a background chunk is
                # already available in full from audio.stop(). Submitting the
                # same tail to a worker would duplicate transcription and can
                # hold the local-model lock until the shared deadline expires.
                # If an older/custom stream cannot report this count, retain
                # the historical tail behavior to avoid risking lost words.
                accepted_background_chunks = 1
                try:
                    accepted_probe = getattr(self._stream_stt, "accepted_count", None)
                    if callable(accepted_probe):
                        accepted_background_chunks = max(0, int(accepted_probe()))
                except Exception as exc:
                    log.debug("[STREAM STT] accepted-count probe failed: %s", exc)
                # Quiesce the device before copying the tail.  Taking it
                # while callbacks are still live can omit final frames or
                # duplicate a callback dispatch at the release boundary.
                try:
                    stop_with_tail = getattr(self.audio, "stop_and_take_open_chunk", None)
                    if callable(stop_with_tail):
                        audio_buffer, tail, tail_overlap = stop_with_tail()
                    else:
                        # Compatibility for custom recorders used by plugins
                        # and older tests.  Built-in AudioRecorder always uses
                        # the quiescent path above.
                        tail = self.audio.take_open_chunk()
                        tail_overlap = 0.0
                    if accepted_background_chunks > 0 and tail is not None and tail.size > 0:
                        _call_with_optional_deadline(
                            self._stream_stt.submit_native,
                            tail,
                            self.audio._native_sr,
                            deadline=post_release_deadline,
                            force=True,
                            overlap_prefix_seconds=tail_overlap,
                        )
                except Exception as exc:
                    log.debug("[STREAM STT] tail submit failed: %s", exc)
                try:
                    _call_with_optional_deadline(
                        self._stream_stt.end_session,
                        deadline=post_release_deadline,
                    )
                except Exception as exc:
                    log.debug("[STREAM STT] end_session failed: %s", exc)

            if audio_buffer is None:
                audio_buffer = self.audio.stop()
            audio_size = int(getattr(audio_buffer, "size", 0) or 0)
            duration = len(audio_buffer) / config.sample_rate if audio_size > 0 else 0.0
            app_title = getattr(session, "app_title", "General App") or (session.get("app_title") if isinstance(session, dict) else "General App")
            category = getattr(session, "app_category", "smart_clean") or (session.get("category") if isinstance(session, dict) else "smart_clean")
            if duration < 0.3 or audio_size == 0:
                # A rejected capture still has a terminal outcome.  Record it
                # asynchronously so history never has unexplained gaps, while
                # avoiding an empty WAV archive.
                recovery = {"audio_path": None, "done": threading.Event()}
                recovery["done"].set()
                self._defer_history_insert(
                    recovery,
                    session,
                    duration,
                    status="transcription_failed",
                    error_message="No usable audio was captured",
                    insertion_status="not_attempted",
                )
                self._release_session_model_resource(session)
                self._reset_to_idle(session)
                self._overlay_call("show_error", "No usable audio was captured")
                return False
            # Keep the complete recording in memory for transcription and
            # archive it concurrently for recovery.  Neither disk nor SQLite
            # work is allowed between release and the first paste attempt.
            recovery = {"audio_path": None, "done": threading.Event(), "audio_buffer": audio_buffer, "archive_started": True}
            pending_recovery = getattr(self, "_pending_recovery", None)
            if pending_recovery is None:
                pending_recovery = self._pending_recovery = {}
            pending_recovery[id(session)] = recovery
            self._overlay_call("show_processing")
            self._release_timing_session = session
            threading.Thread(
                target=self._process_dictation_pipeline,
                args=(session, audio_buffer, duration, None),
                kwargs={"use_streaming": streaming},
                daemon=True,
            ).start()
            self._start_recovery_archive(audio_buffer, recovery)
            return True

        except Exception as e:
            log.error("[FINISH ERROR] %s", e, exc_info=True)
            self._end_stream_session(discard=True)
            self._release_session_model_resource(session)
            if getattr(self, "_post_release_deadline", None) == post_release_deadline:
                self._post_release_deadline = None
            self._reset_to_idle(session)
            self._overlay_call("show_ready")
            return False

    @_capture_transition
    def _on_dictation_cancel(self) -> bool:
        watchdog = getattr(self, "_record_watchdog", None)
        if watchdog:
            watchdog.cancel()
            self._record_watchdog = None

        with self._state_lock:
            if self.state not in (DictationState.RECORDING, DictationState.PROCESSING):
                return False
            session = getattr(self, "session", None)
            if getattr(self, "_delivery_session", None) is session and session is not None:
                return False  # Delivery has already committed; cancellation is too late.
            was_processing = self.state == DictationState.PROCESSING
            cancelled = getattr(self, "_cancelled_session_ids", None)
            if cancelled is None:
                cancelled = self._cancelled_session_ids = set()
            if session is not None:
                cancelled.add(id(session))
            self.state = DictationState.IDLE
            self.session = None

        log.info("[CANCELLED] Dictation cancelled by user.")
        self._set_hotkeys_recording_state(False)

        pending = getattr(self, "_pending_recovery", {})
        recovery = pending.get(id(session)) if session is not None else None
        audio_buffer = recovery.get("audio_buffer") if recovery is not None else None
        if not was_processing:
            try:
                audio_buffer = self.audio.stop()
            except Exception as exc:
                log.debug("[CANCELLED] audio stop failed: %s", exc)
        self._end_stream_session(discard=True, owner=session)
        self._release_session_model_resource(session)

        # Cancellation is terminal user-visible work too.  Archive and
        # history stay off the hotkey path, but retain the recording and its
        # outcome for the same recovery/audit guarantees as a failed STT.
        # A zero-length capture still receives a history row; it explains why
        # no transcript was produced and prevents ambiguous missing entries.
        try:
            audio_size = int(getattr(audio_buffer, "size", 0) or 0)
            duration = len(audio_buffer) / config.sample_rate if audio_size else 0.0
            if recovery is None:
                recovery = {"audio_path": None, "done": threading.Event(), "audio_buffer": audio_buffer}
            if audio_size and not recovery.get("archive_started"):
                recovery["archive_started"] = True
                self._start_recovery_archive(audio_buffer, recovery)
            elif not audio_size:
                recovery["done"].set()
            if session is not None:
                self._defer_history_insert(
                    recovery,
                    session,
                    duration,
                    status="cancelled",
                    error_message="Cancelled by user",
                    insertion_status="not_attempted",
                )
        except Exception as exc:
            log.warning("[CANCELLED] could not schedule cancellation history: %s", exc)
        self._overlay_call("show_ready")
        if not was_processing and session is not None:
            cancelled.discard(id(session))
        return True

    def _copy_last_transcript(self) -> bool:
        if not self.last_successful_transcript:
            log.info("No last transcript available to copy.")
            return False
        try:
            import pyperclip
            pyperclip.copy(self.last_successful_transcript)
            log.info("Last transcript copied to clipboard!")
            return True
        except Exception as exc:
            log.error("Could not copy last transcript: %s", exc)
            return False

    def _paste_last_transcript(self) -> bool:
        # Check if deferred click-to-paste is pending
        pending = getattr(self, "_pending_deferred_transcript", None)
        text_to_paste = pending or self.last_successful_transcript
        if not text_to_paste:
            log.debug("No transcript available to paste.")
            return False
        # Clear the pending deferred trigger once consumed so normal right-clicks function normally
        self._pending_deferred_transcript = None
        try:
            hwnd = self._get_effective_destination_hwnd(None)
        except Exception:
            hwnd = None
        success = self.injector.paste_text(text_to_paste, hwnd)
        if success:
            log.info("[DEFERRED PASTE] Successfully pasted transcript into target hwnd %s", hwnd)
            self._overlay_call("show_done", f"Pasted: {text_to_paste[:60]}")
        else:
            log.error("Could not paste last transcript; it remains on the clipboard.")
        return success

    def _history_update(self, record_id: int | None, **fields) -> None:
        updater = getattr(storage, "update_dictation", None)
        if record_id is not None and callable(updater):
            try:
                updater(record_id, **fields)
            except Exception as exc:
                # History is observability/retry metadata.  It is never a
                # reason to lose a valid transcript or strand PROCESSING.
                log.warning("Could not update dictation history for %s: %s", record_id, exc)

    def _start_recovery_archive(self, audio_buffer: Any, recovery: dict[str, Any] | None = None) -> dict[str, Any]:
        """Archive audio concurrently, without delaying release or paste.

        The in-memory buffer remains the source for the active transcription;
        this background copy makes a failed or interrupted session recoverable
        without introducing synchronous disk I/O on the hotkey release path.
        """
        recovery = recovery or {"audio_path": None, "done": threading.Event()}

        def _archive() -> None:
            try:
                recovery["audio_path"] = self.archive.save(audio_buffer)
            except Exception as exc:
                log.warning("Could not archive recording; history will have no retry audio: %s", exc)
            finally:
                recovery["done"].set()

        threading.Thread(target=_archive, args=(), kwargs={}, daemon=True).start()
        return recovery

    def _defer_history_insert(
        self,
        recovery: dict[str, Any] | None,
        session: Any,
        duration: float,
        *,
        raw_text: str = "",
        polished_text: str = "",
        status: str,
        error_message: str | None = None,
        insertion_status: str = "not_attempted",
        processing_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Write one accurate history row after the user-facing outcome.

        History must describe an insertion result, never hold the clipboard
        hostage.  The archive worker is allowed a bounded background wait so
        recovery audio is linked when available without blocking dictation.
        """
        if recovery is not None:
            with self._state_lock:
                if recovery.get("existing_record_id") is not None or recovery.get("history_claimed"):
                    return
                recovery["history_claimed"] = True
        def _write() -> None:
            try:
                # Re-point to the active account database (login/logout may have
                # happened since this process started) so dictation history lands
                # in the SAME database the GUI Insights dashboard reads.
                try:
                    storage.repoint_if_needed()
                except Exception:
                    log.debug("Could not re-point storage before history write", exc_info=True)
                if recovery is not None:
                    done = recovery.get("done")
                    if done is not None:
                        done.wait(timeout=15.0)
                    audio_path = recovery.get("audio_path")
                else:
                    audio_path = None
                app_title = getattr(session, "app_title", "General App") or (session.get("app_title") if isinstance(session, dict) else "General App")
                category = getattr(session, "app_category", "smart_clean") or (session.get("category") if isinstance(session, dict) else "smart_clean")
                record = storage.add_dictation(
                    raw_text, polished_text, app_title, duration, category,
                    status=status, audio_path=audio_path,
                    error_message=error_message, insertion_status=insertion_status,
                    processing_metadata=processing_metadata,
                )
                # Count corrections against the saved, successfully delivered
                # dictation. Rewrites and commands are not spelling evidence.
                metadata = processing_metadata if isinstance(processing_metadata, dict) else {}
                polish = metadata.get("polish") or {}
                command = metadata.get("command") or {}
                record_id = getattr(record, "id", None)
                if (
                    status == "success"
                    and insertion_status == "pasted"
                    and isinstance(record_id, int)
                    and record_id > 0
                    and isinstance(polish, dict)
                    and polish.get("outcome") in {"ai_accepted", "local_model"}
                    and isinstance(command, dict)
                    and command.get("status") == "not_detected"
                    and not command.get("label")
                ):
                    try:
                        for term, variant in extract_correction_pairs(raw_text, polished_text):
                            storage.record_lexicon_candidate(term, variant, history_id=record_id)
                    except Exception:
                        log.exception("[LEARNING] correction capture failed")
            except Exception as exc:
                log.warning("Could not persist dictation history: %s", exc)

        threading.Thread(target=_write, args=(), kwargs={}, daemon=True).start()

    def _finalize_text(
        self,
        raw_action_text: str,
        session: Any,
        resolved_style: Any = None,
        effective: Any = None,
        deadline: float | None = None,
        command: Any = None,
        outcome_callback: Any = None,
        speed_mode: str | None = None,
        dictionary_trace: list[dict[str, str]] | None = None,
        attempt_outcome_callback: Any = None,
    ) -> str:
        """Fidelity-first order: polish (AI pool or deterministic) -> style."""
        level = getattr(session, "cleanup_level", None) or (session.get("cleanup_level") if isinstance(session, dict) else "cleanup_light")
        style = getattr(session, "style_id", None) or (session.get("style_id") if isinstance(session, dict) else "smart_clean")
        context = getattr(session, "cursor_context", None) or (session.get("cursor_context") if isinstance(session, dict) else None)
        # The polisher owns the AI pass, deterministic cleanup, and the
        # dictionary vocabulary pass; smart formatting runs once afterwards.
        # An effective style (command layer) replaces the plain style
        # instruction and forces the AI pass when a transformation is required.
        if effective is not None:
            style_instruction = effective.instruction
            post_style_id = effective.style_id or style
            force_ai = bool(effective.requires_ai)
            task = getattr(effective, "task", "rewrite")
            command_overrides = getattr(command, "overrides", {}) or {}
        else:
            style_instruction = resolved_style or style
            post_style_id = style
            force_ai = False
            task = "cleanup"
            command_overrides = {}
        observed_outcome: dict[str, str | None] = {"value": None}
        # Freeze the engine and snapshot its per-invocation attempt marker in
        # the outcome callback; another job must not affect fallback eligibility.
        polish_engine = polisher
        attempt_info = {"lfm_bridge_attempted": False}

        def _notify_outcome(outcome: str) -> None:
            observed_outcome["value"] = str(outcome)
            attempt_info["lfm_bridge_attempted"] = bool(getattr(polish_engine, "_last_lfm_bridge_attempted", False))
            if attempt_outcome_callback is not None:
                attempt_outcome_callback(str(outcome))

        def _emit_final_outcome() -> None:
            if outcome_callback is not None and observed_outcome["value"] is not None:
                outcome_callback(observed_outcome["value"])

        # "Keep my wording" with no companion transformation is a request to
        # preserve content, not to re-author it. For an LFM selection, take
        # the deterministic lane immediately: it performs the normal local
        # cleanup and dictionary pass without paying model latency or risking
        # a rewrite. The privacy switch remains authoritative.
        selected_model = getattr(session, "polish_model_ref", None) or (
            session.get("polish_model_ref") if isinstance(session, dict) else None
        )
        selected_lfm = False
        try:
            from voice_flow.lfm_engine import is_lfm_model_ref
            selected_lfm = is_lfm_model_ref(selected_model)
        except Exception:
            pass
        command_format = getattr(command, "format", None) if command is not None else None
        command_context = getattr(command, "context_reference", None) if command is not None else None
        command_operation = getattr(command, "operation", "rewrite") if command is not None else ""
        pure_keep_wording = (
            selected_lfm
            and command is not None
            and bool(getattr(command, "preserve_wording", False))
            and command_format is None
            and command_context is None
            and command_operation == "rewrite"
            and not command_overrides
        )
        simple_format = False
        if (
            selected_lfm and effective is not None and command is not None
            and command_format == "bullet_list"
            and getattr(effective, "format", None) == command_format
            and str(getattr(effective, "style_id", "") or "").endswith(("_formal", "_casual"))
            and command_operation == "rewrite" and command_context is None
            and not command_overrides and not getattr(command, "persistent_change", False)
            and not getattr(command, "preserve_wording", False) and level != "cleanup_none"
        ):
            # Only the standard saved register plus a format instruction is
            # structural. Custom standing instructions still require AI.
            try:
                from voice_flow.effective_style import FORMAT_INSTRUCTIONS
                from voice_flow.style_engine import STYLE_INSTRUCTIONS
                expected_instruction = " ".join((
                    STYLE_INSTRUCTIONS[effective.style_id], FORMAT_INSTRUCTIONS[command_format],
                ))
                formatter = format_dictated_email if command_format == "email" else _format_dictated_bullets
                simple_format = (
                    style_instruction == expected_instruction
                    and formatter(raw_action_text) is not None
                )
            except (KeyError, AttributeError, TypeError):
                pass
        polishing_enabled = _polishing_enabled() if pure_keep_wording or simple_format or selected_lfm else False
        deterministic_preserve = pure_keep_wording and polishing_enabled
        deterministic_format = simple_format and polishing_enabled
        deterministic_local_rewrite = False
        if (
            selected_lfm and polishing_enabled and effective is not None and command is not None and force_ai
            and level != "cleanup_none" and not getattr(command, "preserve_wording", False)
            and not getattr(command, "persistent_change", False) and not getattr(command, "ambiguous", False)
            and command_context is None
            and (deadline is None or deadline - time.monotonic() > AI_POLISH_DETERMINISTIC_RESERVE_SECONDS)
        ):
            # The selected tiny model cannot reliably author these requests.
            # Probe only finite, guarded patterns with pure local cleanup. The
            # dictionary still belongs to the one real polish pass below.
            from voice_flow.command_rewrites import try_local_command_rewrite
            preview = polish_engine._deterministic_cleanup(raw_action_text, "", level)
            deterministic_local_rewrite = try_local_command_rewrite(
                preview, task=task, command_format=command_format, style_id=str(post_style_id),
                instruction=str(style_instruction), overrides=command_overrides,
            ) is not None
        deterministic_request = deterministic_preserve or deterministic_format or deterministic_local_rewrite

        polished = _call_with_optional_deadline(
            polish_engine.polish,
            raw_action_text,
            deadline=deadline,
            model_ref="local/deterministic" if deterministic_request else selected_model,
            style_instruction=style_instruction,
            cleanup_level=level,
            force_ai=False if deterministic_request else force_ai,
            task="cleanup" if deterministic_request else task,
            overrides=command_overrides,
            command_format=command_format,
            outcome_callback=_notify_outcome,
            dictionary_trace=dictionary_trace,
            speed_mode=_normalize_polish_speed_mode(speed_mode or getattr(session, "polish_speed_mode", None) or (session.get("polish_speed_mode") if isinstance(session, dict) else None)),
        )
        if deterministic_preserve and observed_outcome["value"] == "local":
            observed_outcome["value"] = "local_preserved"
        if deterministic_local_rewrite and observed_outcome["value"] == "local":
            # Privacy can change during preflight. Validate the actual cleaned,
            # dictionary-aware payload again, without another polish/rule pass.
            local_rewrite = None
            if _polishing_enabled():
                local_rewrite = try_local_command_rewrite(
                    polished, task=task, command_format=command_format, style_id=str(post_style_id),
                    instruction=str(style_instruction), overrides=command_overrides,
                )
            if local_rewrite is not None:
                observed_outcome["value"] = "local_rewrite"
                _emit_final_outcome()
                return local_rewrite
            observed_outcome["value"] = "command_unfulfilled" if _polishing_enabled() else "disabled"
            _emit_final_outcome()
            return polished
        # After the selected provider's failed attempt, a finite English edit
        # can fulfill recognizable dictation. The polisher's safe payload has
        # already received grammar cleanup and its single dictionary pass.
        # Never edit the rejected model candidate or enter this lane while OFF.
        local_attempt_failed = observed_outcome["value"] in {"provider_failure", "fidelity_reject", "command_unfulfilled"} or (
            observed_outcome["value"] == "timeout" and attempt_info["lfm_bridge_attempted"]
        )
        if (
            local_attempt_failed and _polishing_enabled() and not deterministic_request
            and effective is not None and command is not None and force_ai
            and level != "cleanup_none" and selected_model != "local/deterministic"
            and not getattr(command, "preserve_wording", False)
            and not getattr(command, "persistent_change", False)
            and not getattr(command, "ambiguous", False) and command_context is None
        ):
            from voice_flow.command_rewrites import try_local_command_rewrite
            local_rewrite = try_local_command_rewrite(
                polished, task=task, command_format=command_format,
                style_id=str(post_style_id), instruction=str(style_instruction), overrides=command_overrides,
            )
            if local_rewrite is not None:
                # Preserve literals and dictionary spelling; do not run another
                # rewriting formatter or dictionary replacement pass afterwards.
                observed_outcome["value"] = "local_rewrite"
                _emit_final_outcome()
                return local_rewrite
        # The polisher's deterministic fallback has already applied safe
        # cleanup and dictionary replacements. Do not run style formatting
        # after a disabled/failed AI attempt, because a style or command did
        # not actually run; do deliver the safe fallback instead of throwing
        # it away and pasting the raw transcript.
        if deterministic_format or observed_outcome["value"] in {"timeout", "provider_failure", "fidelity_reject", "command_unfulfilled", "disabled"}:
            overrides = command_overrides if isinstance(command_overrides, dict) else {}
            supported_email_overrides = set(overrides).issubset({"tone", "formality"})
            can_use_local_structure = (
                observed_outcome["value"] != "disabled"
                and level != "cleanup_none"
                and effective is not None
                and task in {"rewrite", "format"}
            )
            effective_format = getattr(effective, "format", None) if effective is not None else None
            if can_use_local_structure and effective_format == "email" and supported_email_overrides:
                locally_formatted = format_dictated_email(polished)
                if locally_formatted is not None:
                    # The content and layout are already fixed above; apply
                    # only the user's selected deterministic register so this
                    # fallback honours their saved email style without asking
                    # a model to invent a subject, sign-off, or new facts.
                    locally_formatted = smart_format(locally_formatted, post_style_id, context)
                    try:
                        locally_formatted = dictionary_engine.restore_dictionary_spelling(locally_formatted)
                    except Exception:
                        log.debug("[DICTIONARY] local email vocabulary guard failed", exc_info=True)
                    observed_outcome["value"] = "local_format"
                    _emit_final_outcome()
                    return locally_formatted
            if can_use_local_structure and effective_format == "bullet_list" and not overrides:
                locally_formatted = _format_dictated_bullets(polished)
                if locally_formatted is not None:
                    try:
                        locally_formatted = dictionary_engine.restore_dictionary_spelling(locally_formatted)
                    except Exception:
                        log.debug("[DICTIONARY] local bullet vocabulary guard failed", exc_info=True)
                    observed_outcome["value"] = "local_format"
                    _emit_final_outcome()
                    return locally_formatted
            # Plain polishing may fail or time out on a long run-on
            # dictation.  While polishing is ON, adding paragraph boundaries
            # around explicit discourse markers is safe and useful; it never
            # deletes or rewrites a word.  Do not relabel a failed command as
            # successful local formatting.
            if command is None and observed_outcome["value"] != "disabled":
                paragraph_formatted = _format_safe_paragraphs(polished)
                if paragraph_formatted != polished:
                    observed_outcome["value"] = "local_paragraphs"
                    _emit_final_outcome()
                    return paragraph_formatted
            _emit_final_outcome()
            return polished
        formatted = smart_format(polished, post_style_id, context)
        # Style formatters may lowercase casual text after the polisher has
        # restored canonical vocabulary. Restore casing only; running the
        # correction rules again could turn an earlier replacement into a
        # new trigger and change the user's meaning.
        try:
            formatted = dictionary_engine.restore_dictionary_spelling(formatted)
        except Exception:
            log.debug("[DICTIONARY] final vocabulary guard failed", exc_info=True)
        # When ON polishing successfully returns a long single block, keep the
        # accepted wording but add only safe paragraph boundaries.  This is
        # deliberately restricted to ordinary dictation: a command's result
        # already has its own required structure and must retain its outcome.
        if command is None:
            formatted = _format_safe_paragraphs(formatted)
        _emit_final_outcome()
        return formatted

    def _process_dictation_pipeline(self, session: Any, audio_buffer: Any, duration: float, record_id: int | None = None, use_streaming: bool = False, recovery: dict[str, Any] | None = None) -> None:
        if recovery is None:
            recovery = getattr(self, "_pending_recovery", {}).get(id(session))
        if record_id is not None:
            recovery = recovery or {}
            recovery["existing_record_id"] = record_id
        lock = getattr(self, "processing_lock", None)
        if lock is None:
            lock = threading.Lock()
        with lock:
            pipeline_started = time.perf_counter()
            release_started = (
                getattr(self, "_release_started_at", pipeline_started)
                if getattr(self, "_release_timing_session", None) is session
                else pipeline_started
            )
            # Streaming has a short release target. Complete audio recovery
            # and requested AI transformations have their own bounded budgets;
            # missing the streaming target must not truncate either operation.
            post_release_deadline = getattr(self, "_post_release_deadline", None)
            if post_release_deadline is None:
                post_release_deadline = time.monotonic() + POST_RELEASE_WORK_BUDGET_SECONDS
            complete_recording_deadline = time.monotonic() + _complete_recording_budget_seconds(duration)
            stream_closed = False
            try:
                # App/style context belongs to the session, never current foreground.
                with self._state_lock:
                    if self._session_was_cancelled(session) or getattr(self, "session", None) is not session or self.state != DictationState.PROCESSING:
                        log.info("Ignoring stale dictation processing session.")
                        return

                target_h = getattr(session, "target_hwnd", None) or (session.get("hwnd") if isinstance(session, dict) else None)
                resolved_style = (
                    getattr(session, "resolved_style", None)
                    or getattr(session, "style", None)
                    or (session.get("resolved_style") if isinstance(session, dict) else None)
                    or (session.get("style") if isinstance(session, dict) else None)
                    or style_engine.resolve_for_target(target_h)
                )
                log.info("Detected active app: '%s' (%s style - %s)", resolved_style.app_name, resolved_style.category, resolved_style.style_id)

                # Transcribe: prefer chunks already completed in the
                # background, but only accept the joined result once every
                # chunk is quiescent.  ``StreamTranscriber.collect`` clears
                # returned results even when a worker is still pending; using
                # that partial result would both lose words and allow a later
                # chunk to be joined out of order.  A non-quiescent harvest is
                # therefore discarded and the complete whole-buffer path owns
                # the transcript.
                stt_started = time.perf_counter()
                raw_transcript = ""
                used_stream_text = False
                failure: Exception | None = None
                part = ""
                stream_input_incomplete = False
                if use_streaming:
                    try:
                        recorder = getattr(self, "audio", None)
                        stream_input_incomplete = bool(
                            getattr(recorder, "stream_input_incomplete", False)
                        )
                    except Exception as exc:
                        # If the recorder cannot establish completeness, use
                        # the archived full recording as the safe source.
                        log.warning(
                            "[STREAM STT] recorder completeness probe failed (%s); using whole-buffer transcription.",
                            exc,
                        )
                        stream_input_incomplete = True
                    if stream_input_incomplete:
                        log.warning(
                            "[STREAM STT] recorder reports incomplete stream input; using whole-buffer transcription."
                        )
                        # Stop work on known-incomplete audio before recovery
                        # starts competing for the same CPU. Keep the original
                        # use_streaming flag so the finally path remains the
                        # fallback cleanup if this call ever raises.
                        self._end_stream_session(discard=True, owner=session)
                        stream_closed = True

                if use_streaming and not stream_input_incomplete and self._stream_had_failures(self._stream_stt):
                    self._end_stream_session(discard=True, owner=session)
                    stream_closed = True
                    stream_input_incomplete = True

                if use_streaming and not stream_input_incomplete:
                    # A full-frame WebSocket session is one coherent provider
                    # request. It cannot return an out-of-order chunk prefix,
                    # so let its finalization use the whole release window
                    # (apart from injection). Chunked batch streaming retains
                    # a recovery slice because later chunks can still be in
                    # flight when its collector returns.
                    if bool(getattr(self._stream_stt, "live_frames", False)):
                        recovery_reserve = INJECTION_RESERVE_SECONDS
                    else:
                        recovery_reserve = WHOLE_BUFFER_RECOVERY_RESERVE_SECONDS + INJECTION_RESERVE_SECONDS
                    harvest_deadline = post_release_deadline - recovery_reserve
                    remaining = max(0.0, harvest_deadline - time.monotonic())
                    if remaining > 0.0:
                        try:
                            part = _call_with_optional_deadline(
                                self._stream_stt.collect,
                                deadline=harvest_deadline,
                                timeout=remaining,
                            )
                        except Exception as exc:
                            log.warning("[STREAM STT] collect failed (%s); using whole-buffer transcription.", exc)
                            part = ""
                        stream_had_failures = self._stream_had_failures(self._stream_stt)
                        try:
                            still_pending = self._stream_stt.pending_count()
                        except Exception as exc:
                            log.warning("[STREAM STT] pending probe failed (%s); using whole-buffer transcription.", exc)
                            still_pending = 1

                        if still_pending > 0 and not stream_had_failures:
                            drain_deadline = min(post_release_deadline - INJECTION_RESERVE_SECONDS, time.monotonic() + 0.85)
                            remaining_drain = max(0.0, drain_deadline - time.monotonic())
                            if remaining_drain > 0.0:
                                try:
                                    drain_part = _call_with_optional_deadline(
                                        self._stream_stt.collect,
                                        deadline=drain_deadline,
                                        timeout=remaining_drain,
                                    )
                                    if drain_part:
                                        part = f"{part} {drain_part}".strip() if part else str(drain_part).strip()
                                except Exception:
                                    pass
                            try:
                                still_pending = self._stream_stt.pending_count()
                            except Exception:
                                still_pending = 1
                            stream_had_failures = self._stream_had_failures(self._stream_stt)

                        if part and still_pending <= 0 and not stream_had_failures:
                            raw_transcript = str(part).strip()
                            used_stream_text = True
                            log.info("[STREAM STT] %d chars assembled from quiescent chunks.", len(raw_transcript))
                        elif part:
                            log.warning(
                                "[STREAM STT] discarded %d streamed chars; pending=%d failures=%s.",
                                len(str(part)),
                                still_pending,
                                stream_had_failures,
                            )
                # A complete-recording attempt is the correctness path.  Its
                # provider owns a duration-aware bound; the short streaming
                # target above must never turn into a transcription cutoff.
                for attempt in range(1):
                    if raw_transcript.strip():
                        break
                    try:
                        self.transcriber.category_hint = getattr(resolved_style, "category", None)
                        raw_transcript = _call_with_optional_deadline(
                            self.transcriber.transcribe,
                            audio_buffer,
                            deadline=complete_recording_deadline,
                            model_ref=getattr(session, "stt_model_ref", None) or (session.get("stt_model_ref") if isinstance(session, dict) else None),
                        ) or ""
                        if raw_transcript.strip():
                            break
                        failure = RuntimeError("No text was transcribed")
                    except Exception as exc:
                        failure = exc
                stt_elapsed = time.perf_counter() - stt_started
                # Streaming harvest and complete-buffer fallback are finished.
                # End speech-model demand before any local polish inference.
                self._release_session_model_resource(session)
                if self._session_was_cancelled(session):
                    return
                # A rejected stream is known incomplete. Never paste its prefix
                # as successful recovery when the complete decode fails.

                if not raw_transcript.strip():
                    reason = str(failure or "No text was transcribed")
                    self._history_update(record_id, status="transcription_failed", error_message=reason, insertion_status="not_attempted")
                    self._defer_history_insert(recovery, session, duration, status="transcription_failed", error_message=reason)
                    self._reset_to_idle(session)
                    self._overlay_call("show_error", reason[:90])
                    return

                # Voice commands are an AI-polishing feature.  With polishing
                # disabled, preserve the entire utterance literally and clear
                # any previously armed command so it cannot affect a later run.
                # A settings read failure is deliberately fail-closed here.
                polishing_enabled = _polishing_enabled()
                command = None
                command_content = raw_transcript
                if polishing_enabled:
                    # Deterministic wake-phrase command detection. The raw
                    # transcript is first repaired for known mis-hearings.
                    try:
                        detection = detect_voice_command(dictionary_engine.repair_wake_term(raw_transcript))
                        command_content = detection.content or ""
                        command = detection.command
                    except Exception:
                        log.exception("[COMMAND] detection failed; using plain dictation")
                else:
                    self._pending_command = None

                # A persistent command is a settings action, even when it has
                # no dictated content. Apply it before deciding whether to arm
                # the next dictation.
                persistent_applied = None
                if command is not None and command.persistent_change:
                    try:
                        persistent_applied = apply_persistent_change(command)
                        if persistent_applied:
                            log.info("[COMMAND] persistent change applied: %s", persistent_applied)
                    except Exception:
                        log.exception("[COMMAND] persistent change failed")

                # A command with no dictated content is ambiguous.
                #
                #  * A saved preference ("always use my email style") is applied
                #    and never armed, so the next ordinary dictation is not
                #    silently rewritten.
                #  * A "make THIS ..." command (scope "current") means the text
                #    the user has selected in the active app, so capture that
                #    selection and transform it in place. That is what the user
                #    expects from "make this a good prompt" with nothing else
                #    dictated.
                #  * Only when there is no selection — or the command explicitly
                #    refers to the next dictation ("what I say next") — do we arm
                #    it for the following utterance.
                if command is not None and not command_content.strip():
                    if command.persistent_change:
                        self._pending_command = None
                        if not persistent_applied:
                            detail = "Could not save this voice preference. Please try again."
                            command_metadata = _command_only_processing_metadata(resolved_style=resolved_style, command=command, status="not_applied", display=detail)
                            self._history_update(record_id, raw_text=raw_transcript, polished_text="", status="success", error_message=detail, insertion_status="not_attempted", processing_metadata=command_metadata)
                            self._defer_history_insert(recovery, session, duration, raw_text=raw_transcript, status="success", error_message=detail, processing_metadata=command_metadata)
                            self._reset_to_idle(session)
                            self._overlay_call("show_error", detail)
                            return
                        detail = persistent_applied
                        command_metadata = _command_only_processing_metadata(resolved_style=resolved_style, command=command, status="saved", display=f"Voice preference saved: {detail}")
                        self._history_update(record_id, raw_text=raw_transcript, polished_text="", status="success", error_message=f"Persistent command saved: {detail}", insertion_status="not_attempted", processing_metadata=command_metadata)
                        self._defer_history_insert(recovery, session, duration, raw_text=raw_transcript, status="success", error_message=f"Persistent command saved: {detail}", processing_metadata=command_metadata)
                        self._reset_to_idle(session)
                        self._overlay_call("show_done", f"Voice Flow: {detail}")
                        return

                    selected_text = ""
                    if getattr(command, "scope", "current") != "next":
                        try:
                            selected_text = self.injector.get_selected_text_strict(
                                target_hwnd=getattr(session, "target_hwnd", None),
                            ) or ""
                        except Exception:
                            log.exception("[COMMAND] Could not capture selected text")
                            selected_text = ""

                    if selected_text.strip():
                        # Transform the selection and replace it in place.
                        command_content = selected_text
                        self._pending_command = None
                        log.info(
                            "[COMMAND] %s — applying to %d selected characters in place.",
                            command.label(), len(selected_text),
                        )
                        self._overlay_call("show_processing")
                    else:
                        self._pending_command = command
                        log.info("[COMMAND] %s — no content yet; armed for the next dictation.", command.label())
                        command_metadata = _command_only_processing_metadata(resolved_style=resolved_style, command=command, status="armed", display=f"Voice command ready: {command.label()}")
                        self._history_update(record_id, raw_text=raw_transcript, polished_text="", status="success", error_message=f"Command armed: {command.label()}", insertion_status="not_attempted", processing_metadata=command_metadata)
                        self._defer_history_insert(recovery, session, duration, raw_text=raw_transcript, status="success", error_message=f"Command armed: {command.label()}", processing_metadata=command_metadata)
                        self._reset_to_idle(session)
                        self._overlay_call("show_done", f"Voice Flow: {command.label()} — dictate the content next")
                        return
                if not polishing_enabled:
                    self._pending_command = None
                elif command is None:
                    pending = getattr(self, "_pending_command", None)
                    if pending is not None:
                        self._pending_command = None
                        command = pending
                        log.info("[COMMAND] applying armed command: %s", command.label())
                else:
                    self._pending_command = None

                # Effective style: deterministic merge of Auto Context base,
                # saved profile, format command, and temporary overrides.
                effective = None
                try:
                    effective = resolve_effective_style(resolved_style, command)
                except Exception:
                    log.exception("[COMMAND] effective style resolution failed; using base style")

                # Check opt-in Press Enter action, then polish.
                press_enter_enabled = getattr(session, "press_enter_enabled", False) or (session.get("press_enter_enabled", False) if isinstance(session, dict) else False)
                split_res = split_press_enter(command_content, bool(press_enter_enabled))
                text_to_polish = apply_spoken_punctuation(split_res.text)
                should_press_enter = split_res.press_enter

                # The polisher owns the deterministic vocabulary pass; smart
                # formatting runs once afterwards.
                polish_started = time.perf_counter()
                speed_mode = getattr(session, "polish_speed_mode", None) or (session.get("polish_speed_mode") if isinstance(session, dict) else None)
                if not speed_mode:
                    try:
                        speed_mode = storage.get_setting("voice_flow_polish_speed_mode", "balanced")
                    except Exception:
                        speed_mode = "balanced"
                stt_model_ref = getattr(session, "stt_model_ref", None) or (session.get("stt_model_ref") if isinstance(session, dict) else None)
                polish_deadline = _polish_deadline(
                    post_release_deadline,
                    speed_mode,
                    len(text_to_polish.split()),
                    cloud_stt=_is_cloud_stt_model(stt_model_ref),
                    requires_ai=bool(effective and effective.requires_ai),
                    polish_model_ref=getattr(session, "polish_model_ref", None) or (session.get("polish_model_ref") if isinstance(session, dict) else None),
                )
                polish_outcome: dict[str, str] = {"value": "provider_failure"}
                polish_attempt_outcome: dict[str, str] = {}

                def _record_polish_outcome(outcome: str) -> None:
                    # This closure is scoped to this pipeline invocation.
                    polish_outcome["value"] = str(outcome)

                dictionary_trace: list[dict[str, str]] = []
                polished_text = self._finalize_text(
                    text_to_polish,
                    session,
                    resolved_style,
                    effective=effective,
                    # Cleanup has its own small mode-aware budget. It starts
                    # after STT because cleanup is optional and has a local
                    # deterministic fallback; STT owns the full recording.
                    deadline=polish_deadline,
                    command=command,
                    outcome_callback=_record_polish_outcome,
                    speed_mode=speed_mode,
                    dictionary_trace=dictionary_trace,
                    attempt_outcome_callback=lambda outcome: polish_attempt_outcome.update(value=str(outcome)),
                )
                polish_elapsed = time.perf_counter() - polish_started
                processing_metadata = _processing_metadata(
                    polish_outcome=polish_outcome["value"],
                    polish_elapsed=polish_elapsed,
                    resolved_style=resolved_style,
                    effective_style=effective,
                    command=command,
                    polishing_enabled=polishing_enabled,
                    dictionary_trace=dictionary_trace,
                    polish_attempt_outcome=polish_attempt_outcome.get("value"),
                )
                polished_words = len(polished_text.split()) if polished_text else 0
                log.info("Pipeline complete (%d words -> %d words, polish=%s): '%s'", len(raw_transcript.split()), polished_words, polish_outcome["value"], polished_text)

                if not polished_text and not should_press_enter:
                    self._history_update(record_id, raw_text=raw_transcript, status="transcription_failed", error_message="Text cleanup returned no usable transcript", insertion_status="not_attempted")
                    self._defer_history_insert(recovery, session, duration, raw_text=raw_transcript, status="transcription_failed", error_message="Text cleanup returned no usable transcript")
                    self._reset_to_idle(session)
                    self._overlay_call("show_error", "Text cleanup returned no usable transcript")
                    return

                with self._state_lock:
                    if self._session_was_cancelled(session) or getattr(self, "session", None) is not session or self.state != DictationState.PROCESSING:
                        log.info("Discarding stale transcript before persistence/paste.")
                        return
                    self._delivery_session = session

                outcome_note = None if polish_outcome["value"] == "ai_accepted" else f"Polish fallback: {polish_outcome['value']}"
                self._history_update(record_id, raw_text=raw_transcript, polished_text=polished_text, status="success", error_message=outcome_note, insertion_status="not_attempted", processing_metadata=processing_metadata)

                # Check if Deferred Click-to-Paste mode is enabled
                click_to_paste = False
                try:
                    click_to_paste = bool(self._get_cached_setting("click_to_paste_enabled", False))
                except Exception:
                    click_to_paste = False

                if click_to_paste and polished_text.strip():
                    # Deferred Mode: Place transcript on clipboard, store as pending, and wait for Right-Click / Paste trigger
                    self.last_successful_transcript = polished_text
                    self._pending_deferred_transcript = polished_text
                    try:
                        import pyperclip
                        pyperclip.copy(polished_text)
                    except Exception:
                        pass
                    self._history_update(record_id, insertion_status="ready_to_paste")
                    self._defer_history_insert(recovery, session, duration, raw_text=raw_transcript, polished_text=polished_text, status="success", error_message=outcome_note, insertion_status="ready_to_paste", processing_metadata=processing_metadata)
                    self._reset_to_idle(session)
                    prefix = _polish_outcome_label(polish_outcome["value"])
                    self._overlay_call("show_done", f"{prefix} — Ready to Paste")
                    log.info("[CLICK-TO-PASTE] Transcript held on clipboard. Right-click anywhere to paste.")
                    return

                # Inject polished text into the resolved target window.
                with self._state_lock:
                    if self._session_was_cancelled(session) or getattr(self, "session", None) is not session or self.state != DictationState.PROCESSING:
                        log.info("Discarding cancelled transcript before paste.")
                        return

                # Dynamically resolve effective destination window right before injection.
                # If the user switched to another app (e.g. from Twitter to Antigravity),
                # paste into the active window without stealing focus back to the previous app.
                effective_target = self._get_effective_destination_hwnd(session, fallback_hwnd=target_h)
                if effective_target and effective_target != target_h:
                    log.info("[TARGET WINDOW] Active window switched from hwnd %s to %s; pasting into active window.", target_h, effective_target)
                    target_h = effective_target
                    self._last_target_hwnd = effective_target
                elif effective_target is None and target_h and self._is_internal_window(target_h):
                    target_h = None

                injection_started = time.perf_counter()
                success = self.injector.paste_text(polished_text, target_h, press_enter=should_press_enter)
                injection_elapsed = time.perf_counter() - injection_started
                log.info(
                    "[VOICE LATENCY] stt_ms=%.0f polish_ms=%.0f injection_ms=%.0f total_ms=%.0f stream=%s release_to_paste_ms=%.0f",
                    stt_elapsed * 1000,
                    polish_elapsed * 1000,
                    injection_elapsed * 1000,
                    (time.perf_counter() - pipeline_started) * 1000,
                    "yes" if used_stream_text else "no",
                    (time.perf_counter() - release_started) * 1000,
                )

                # Accepted transcript state is updated only after a successful paste.
                # An action-only Enter must not erase the prior copy-last transcript.
                if success and polished_text.strip():
                    self.last_successful_transcript = polished_text
                    recent = getattr(self, "recent_dictations", None)
                    if recent is not None:
                        recent.add(polished_text.strip())
                        if raw_transcript and raw_transcript.strip():
                            recent.add(raw_transcript.strip())
                        if len(recent) > 100:
                            self.recent_dictations = set(list(recent)[-50:])
                    self._history_update(record_id, insertion_status="pasted")
                elif not success:
                    self._history_update(record_id, status="paste_failed", error_message="Could not paste transcript into the original target; retrieve the text from history.", insertion_status="failed")

                self._defer_history_insert(
                    recovery, session, duration, raw_text=raw_transcript,
                    polished_text=polished_text,
                    status="success" if success else "paste_failed",
                    error_message=outcome_note if success else "Could not paste transcript into the original target; retrieve the text from history.",
                    insertion_status="pasted" if success else "failed",
                    processing_metadata=processing_metadata,
                )

                self._reset_to_idle(session)

                if success:
                    polishing_enabled = _polishing_enabled()
                    if effective is not None and effective.requires_ai and polish_outcome["value"] not in {"ai_accepted", "local_model", "local_format", "local_rewrite", "local_preserved"}:
                        # Spec §50: never silently pretend a transformation ran.
                        label = f" — {effective.label}" if effective.label else ""
                        detail = (
                            "Turn on AI polishing to run this command"
                            if polish_outcome["value"] == "disabled"
                            else _polish_outcome_label(polish_outcome["value"])
                        )
                        self._overlay_call("show_error", f"{detail}{label}")
                    elif effective is not None and effective.label and polish_outcome["value"] == "local_model":
                        self._overlay_call("show_done", f"Local model polished — {effective.label}")
                    elif effective is not None and effective.label and polish_outcome["value"] == "ai_accepted":
                        self._overlay_call("show_done", f"AI polished — {effective.label}")
                    else:
                        prefix = _polish_outcome_label(polish_outcome["value"])
                        self._overlay_call("show_done", prefix)
                else:
                    self._overlay_call("show_error", "Paste failed — retrieve text from history")

            except Exception as e:
                if self._session_was_cancelled(session):
                    return
                log.error("Error processing dictation: %s", e, exc_info=True)
                self._history_update(record_id, status="transcription_failed", error_message=str(e), insertion_status="not_attempted")
                self._defer_history_insert(recovery, session, duration, status="transcription_failed", error_message=str(e))
                self._reset_to_idle(session)
                self._overlay_call("show_ready")
            finally:
                # Every return/exception path closes the stream epoch and
                # releases the processing state.  ``discard`` also fences off
                # a late worker result from the next dictation.
                if use_streaming and not stream_closed:
                    self._end_stream_session(discard=True, owner=session)
                self._release_session_model_resource(session)
                pending = getattr(self, "_pending_recovery", None)
                if isinstance(pending, dict):
                    pending.pop(id(session), None)
                cancelled = getattr(self, "_cancelled_session_ids", None)
                if isinstance(cancelled, set):
                    cancelled.discard(id(session))
                if getattr(self, "_delivery_session", None) is session:
                    self._delivery_session = None
                if getattr(self, "_post_release_deadline", None) == post_release_deadline:
                    self._post_release_deadline = None
                self._reset_to_idle(session)

    def retry_history(self, record_id: int) -> tuple[bool, str]:
        """Retry archived audio without injecting into whichever app is focused now."""
        try:
            row = storage.get_history_record(record_id)
        except Exception as exc:
            log.warning("[RETRY] Could not read history record %s: %s", record_id, exc)
            return False, "History is temporarily unavailable"
        if not row:
            return False, "History item not found"
        if float(row.get("duration_sec") or 0) < MIN_RETRY_SECONDS:
            return False, "Only recordings of at least 5 seconds can be retried"
        try:
            path = self.archive.resolve(row.get("audio_path"))
            available = self.archive.available(row.get("audio_path")) if path else False
        except Exception as exc:
            log.warning("[RETRY] Could not resolve history audio %s: %s", record_id, exc)
            return False, "Audio is no longer available"
        if not path or not available:
            return False, "Audio is no longer available"
        with self._state_lock:
            if self.state != DictationState.IDLE:
                return False, "Finish the current dictation before retrying"
            self.state = DictationState.PROCESSING
        try:
            storage.update_dictation(record_id, status="processing", error_message=None, retry_count=int(row.get("retry_count") or 0) + 1)
            self._overlay_call("show_processing")
            threading.Thread(target=self._retry_history_worker, args=(record_id, str(path)), daemon=True).start()
        except Exception as exc:
            log.error("[RETRY] Could not start retry for record %s: %s", record_id, exc)
            self._reset_to_idle()
            try:
                self._history_update(record_id, status="transcription_failed", error_message=str(exc), insertion_status="not_attempted")
            except Exception:
                log.exception("[RETRY] could not record retry startup failure for %s", record_id)
            self._overlay_call("show_error", f"History retry failed: {exc}"[:90])
            return False, "Retry could not be started"
        return True, "Retry started"

    def _retry_history_worker(self, record_id: int, path: str) -> None:
        lease = None
        try:
            from voice_flow.local_model_resources import acquire_model_use
            lease = acquire_model_use("speech")
            import wave, numpy as np
            with wave.open(path, "rb") as wf:
                audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32767.0
            # History retry is an explicit recovery operation, not the
            # interactive release path.  Preserve its prior completeness
            # semantics for long archived recordings instead of truncating it
            # to the 2.7s dictation deadline.
            raw = self.transcriber.transcribe(audio) or ""
            if not raw.strip():
                raise RuntimeError("No text was transcribed")
            # Retried history deliberately uses the stored style-independent
            # recovery path: it never focuses or pastes into the current app.
            text = smart_format(dictionary_engine.apply_dictionary_post_processing(cleanup_text(raw, "cleanup_light")), "smart_clean")
            self._history_update(record_id, raw_text=raw, polished_text=text, status="success", error_message=None, insertion_status="not_attempted")
            self.last_successful_transcript = text
            self._overlay_call("show_done", text)
            self._reset_to_idle()
        except Exception as exc:
            self._history_update(record_id, status="transcription_failed", error_message=str(exc), insertion_status="not_attempted")
            self._reset_to_idle()
            self._overlay_call("show_error", f"History retry failed: {exc}"[:90])
        finally:
            release = getattr(lease, "release", None)
            if callable(release):
                release()

    def _on_mouse_release(self, x: int, y: int, drag_distance: float = 0.0, start_x: int = 0, start_y: int = 0) -> None:
        """Capture selected text and expose its actions on the persistent bar."""
        self._selection_generation = getattr(self, "_selection_generation", 0) + 1
        selection_generation = self._selection_generation
        audio_enabled = self._get_cached_setting("audio_flow_enabled", True)
        video_enabled = self._get_cached_setting("video_flow_enabled", True)
        if (not audio_enabled and not video_enabled) or getattr(self, "state", DictationState.IDLE) != DictationState.IDLE or self.is_recording:
            self.overlay.clear_selected_text()
            audio_flow_widget.hide()
            return

        # Distinguish intentional text selection drags (>= 16px) from normal clicks
        # or micro-movement click jitter (< 16px). Normal clicks never capture text.
        if drag_distance < 16.0:
            is_on_overlay = hasattr(self.overlay, "contains_point") and self.overlay.contains_point(x, y)
            is_on_audio = hasattr(audio_flow_widget, "contains_point") and audio_flow_widget.contains_point(x, y)
            if not is_on_overlay and not is_on_audio:
                self.overlay.clear_selected_text()
                audio_flow_widget.hide()
            return

        def _check():
            try:
                # If dictation recording or processing started in the meantime, abort text capture
                if getattr(self, "state", DictationState.IDLE) != DictationState.IDLE or self.is_recording:
                    return

                # Always use the CURRENT foreground window — never a stale target_hwnd
                # from a previous dictation session (which may point to the terminal).
                target_hwnd = ctypes.windll.user32.GetForegroundWindow()
                if not target_hwnd:
                    return

                # Never capture text or send synthetic Ctrl+C to Voice Flow's own windows
                try:
                    pid = wintypes.DWORD()
                    ctypes.windll.user32.GetWindowThreadProcessId(target_hwnd, ctypes.byref(pid))
                    if pid.value == os.getpid():
                        return
                except Exception:
                    pass

                # Skip system/utility windows that produce mouse drags but are NOT
                # real text selection sources (Snipping Tool, screenshot tools, etc.)
                try:
                    title_len = ctypes.windll.user32.GetWindowTextLengthW(target_hwnd)
                    title_buf = ctypes.create_unicode_buffer(title_len + 1)
                    ctypes.windll.user32.GetWindowTextW(target_hwnd, title_buf, title_len + 1)
                    fg_title = title_buf.value.lower()
                    class_buf = ctypes.create_unicode_buffer(256)
                    ctypes.windll.user32.GetClassNameW(target_hwnd, class_buf, 256)
                    fg_class = class_buf.value.lower()

                    skip_titles = [
                        "snipping", "screen snip", "screen sketch",
                        "screenshot", "screen clip", "capture",
                        "magnifier", "recorder", "xbox game bar",
                    ]
                    skip_classes = ["xellashwin", "applicationsnaphost"]
                    if any(kw in fg_title for kw in skip_titles):
                        return
                    if any(kw in fg_class for kw in skip_classes):
                        return
                except Exception:
                    pass

                selected = self.injector.get_selected_text_strict(target_hwnd=target_hwnd)
                # The hook advances its lightweight epoch as soon as each
                # release arrives.  This prevents a blocked clipboard read
                # from publishing an older drag while a newer drag is merely
                # pending in the bounded selection worker.
                from voice_flow.mouse_hook import selection_event_is_current
                if (
                    selection_generation != self._selection_generation
                    or not selection_event_is_current()
                    or getattr(self, "state", DictationState.IDLE) != DictationState.IDLE
                    or self.is_recording
                ):
                    return
                if selected and len(selected.strip()) > 1:
                    self.overlay.set_selected_text(selected, timeout_ms=6000)
                    audio_flow_widget.show_at(x, y, selected)
                else:
                    self.overlay.clear_selected_text()
                    audio_flow_widget.hide()
            except Exception:
                from voice_flow.mouse_hook import selection_event_is_current
                if (
                    selection_generation == self._selection_generation
                    and selection_event_is_current()
                    and getattr(self, "state", DictationState.IDLE) == DictationState.IDLE
                ):
                    self.overlay.clear_selected_text()
                    audio_flow_widget.hide()

        # Win32MouseHook already serializes this callback on its bounded
        # selection worker.  Starting another thread here used to create one
        # thread per drag under load.  Direct callers (including alternate
        # input integrations) retain the asynchronous behavior.
        if threading.current_thread().name == "Win32MouseHookSelectionWorker":
            _check()
        else:
            threading.Thread(target=_check, daemon=True).start()

    def _normalize_for_comparison(self, s: str) -> str:
        if not s:
            return ""
        # Lowercase & remove all punctuation & collapse whitespace
        s = s.lower().translate(str.maketrans("", "", string.punctuation))
        return " ".join(s.split())

    def _is_voice_flow_dictation(self, text: str) -> bool:
        """Strict normalized check & word-overlap filter to prevent Audio Flow from ever reading Voice Flow dictations."""
        if not text or not text.strip():
            return False

        norm_text = self._normalize_for_comparison(text)
        if not norm_text:
            return False

        # Check last transcript
        if self.last_successful_transcript:
            norm_last = self._normalize_for_comparison(self.last_successful_transcript)
            if norm_last and (norm_text == norm_last or norm_text in norm_last or norm_last in norm_text):
                return True

        # Check all recent dictations in history
        for recent in list(self.recent_dictations):
            norm_rec = self._normalize_for_comparison(recent)
            if not norm_rec:
                continue
            if norm_text == norm_rec or norm_text in norm_rec or norm_rec in norm_text:
                return True

            # Require substantial overlap before treating selected text as a
            # recent Voice Flow transcript; common words alone must not block TTS.
            words_text = set(norm_text.split())
            words_rec = set(norm_rec.split())
            if len(words_text) >= 2 and len(words_rec) >= 2:
                overlap = words_text.intersection(words_rec)
                if len(overlap) / float(len(words_text)) >= 0.65:
                    return True

        return False

    def _process_audio_flow_pipeline(
        self,
        text_override: str | None = None,
        model_override: str | None = None,
        mode: str = "full",
        summary_depth: str | None = None,
    ) -> None:
        """Start an independent summary job or foreground Read request."""
        effective_mode = (mode or "read").lower().strip()
        if effective_mode == "default":
            effective_mode = str(storage.get_setting("exec_audio_flow_default_mode", "read") or "read").lower().strip()
        if effective_mode == "explain":
            effective_mode = "read"
        is_summary = effective_mode == "summary"

        if not is_summary and not text_override:
            with self._get_read_generation_lock():
                player_active = bool(getattr(self, "_active_summary_player_token", None))
                if player_active or tts_engine.is_speaking():
                    self._stop_audio_flow_pipeline()
                    return

        if not storage.get_setting("audio_flow_enabled", True):
            if not is_summary or (self.state == DictationState.IDLE and not getattr(self, "_read_active", False)):
                audio_flow_widget.set_playing(False)
                self.overlay.show_error("Audio Flow is disabled")
            return

        explicit_selection = bool(text_override and str(text_override).strip())
        text_to_read = text_override
        if not text_to_read:
            target_hwnd = getattr(self, "target_hwnd", None)
            text_to_read = self.injector.get_selected_text(target_hwnd=target_hwnd)
        if not text_to_read or not text_to_read.strip():
            if not is_summary or (self.state == DictationState.IDLE and not getattr(self, "_read_active", False)):
                audio_flow_widget.set_playing(False)
                self.overlay.show_error("Select text to listen")
            return
        if not explicit_selection and self._is_voice_flow_dictation(text_to_read):
            log.info("[AUDIO FLOW] Refusing to read text that matches Voice Flow dictation transcript.")
            audio_flow_widget.set_playing(False)
            self.overlay.show_error("Voice Flow dictation skipped")
            return

        text_to_read = str(text_to_read).strip()
        snippet = text_to_read[:35] + "…" if len(text_to_read) > 35 else text_to_read
        if is_summary:
            audio_flow_widget.hide()
            self._submit_audio_summary(text_to_read, summary_depth)
            return

        read_lock = self._get_read_generation_lock()
        with read_lock:
            player_active = bool(getattr(self, "_active_summary_player_token", None))
            if player_active or tts_engine.is_speaking():
                self._stop_audio_flow_pipeline()
            if self.state != DictationState.IDLE:
                return
            generation = getattr(self, "_read_generation", 0) + 1
            self._read_generation = generation
            self._read_active = False
            self._read_pending = True
            self._active_read_text = text_to_read
        audio_flow_widget.hide()

        def _on_start() -> None:
            with read_lock:
                if getattr(self, "_read_generation", 0) != generation or self.state != DictationState.IDLE:
                    return
                self._read_pending = False
                self._read_active = True
                audio_flow_widget.set_playing(True)
                audio_flow_widget.hide()
                self.overlay.show_reading(snippet)

        def _on_done() -> None:
            with read_lock:
                if getattr(self, "_read_generation", 0) != generation:
                    return
                self._read_active = False
                self._read_pending = False
                audio_flow_widget.set_playing(False)
                audio_flow_widget.hide()
                self.overlay.clear_selected_text()
                if self.state == DictationState.IDLE:
                    self.overlay.show_ready()

        def _on_error(err_msg: str) -> None:
            with read_lock:
                if getattr(self, "_read_generation", 0) != generation:
                    return
                self._read_active = False
                self._read_pending = False
                audio_flow_widget.set_playing(False)
                audio_flow_widget.hide()
                self.overlay.clear_selected_text()
                if self.state == DictationState.IDLE:
                    self.overlay.show_error(f"Audio Flow: {err_msg}"[:90])
            log.warning("Audio Flow synthesis error: %s", err_msg)

        speak_kwargs = {"on_start": _on_start, "on_done": _on_done, "on_error": _on_error}
        if model_override is not None:
            speak_kwargs["model_override"] = model_override

        read_mode_setting = str(storage.get_setting("audio_flow_read_mode", "explanatory") or "explanatory").lower().strip()
        if read_mode_setting == "verbatim" or mode == "read_verbatim":
            log.info("Audio Flow reading selected text (Verbatim Read): '%s'", snippet)
            with read_lock:
                if self.state != DictationState.IDLE or self._read_generation != generation:
                    return
                self.overlay.show_generating_audio()
                tts_engine.speak(text_to_read, **speak_kwargs)
            return

        log.info("Audio Flow reading selected text (Human Explanatory Narration): '%s'", snippet)
        with read_lock:
            if self.state != DictationState.IDLE or self._read_generation != generation:
                return
            self.overlay.show_generating_audio("Preparing explanation...")

        def _explanatory_read_worker() -> None:
            narrated = text_to_read
            try:
                from voice_flow.audio_explainer import audio_explainer
                candidate = audio_explainer.transform_for_human_reading(text_to_read)
                if isinstance(candidate, str) and candidate.strip():
                    narrated = candidate.strip()
            except Exception as err:
                log.warning("Audio explainer transform failed (%s); falling back to direct TTS", err)
            with read_lock:
                if getattr(self, "_read_generation", 0) != generation:
                    return
                if self.state != DictationState.IDLE:
                    self._read_pending = False
                    return
                try:
                    tts_engine.speak(narrated, **speak_kwargs)
                except Exception as err:
                    if getattr(self, "_read_generation", 0) == generation:
                        _on_error(str(err))

        threading.Thread(
            target=_explanatory_read_worker,
            name="AudioFlowExplanatoryRead",
            daemon=True,
        ).start()

    def _get_audio_flow_jobs(self):
        jobs = getattr(self, "_audio_flow_jobs", None)
        if jobs is None:
            init_lock = getattr(self, "_audio_flow_jobs_lock", _AUDIO_FLOW_JOBS_INIT_LOCK)
            with init_lock:
                jobs = getattr(self, "_audio_flow_jobs", None)
                if jobs is None:
                    from voice_flow.audio_flow_jobs import AudioFlowJobs
                    jobs = self._audio_flow_jobs = AudioFlowJobs(
                        max_workers=2,
                        on_change=self._on_audio_summary_job_changed,
                        on_evict=self._clear_audio_summary_status,
                        max_queued=6,
                        retained_terminal=4,
                    )
        return jobs

    def _submit_audio_summary(self, text: str, summary_depth: str | None) -> str:
        import uuid

        depth = (summary_depth or "balanced").lower().strip()
        depth = {"quick": "short", "standard": "balanced", "detailed": "deep_dive"}.get(depth, depth)
        if depth not in {"short", "balanced", "deep_dive"}:
            depth = "balanced"
        style = str(storage.get_setting("audio_flow_summary_style", "single") or "single").strip().lower()
        if style not in {"single", "podcast"}:
            style = "single"
        job_id = f"ash_{uuid.uuid4().hex[:12]}"
        title = storage._derive_audio_title(text)
        payload = {"text": text, "title": title, "depth": depth, "style": style}
        payloads = getattr(self, "_audio_summary_payloads", None)
        if payloads is None:
            payloads = self._audio_summary_payloads = {}
        payloads[job_id] = payload
        def persist_initial() -> None:
            storage.add_audio_summary_history(
                text=text,
                depth=depth,
                audio_path="",
                duration_sec=0.0,
                item_id=job_id,
                title=title,
                status="in_progress",
                progress=0,
            )

        def run(job):
            from voice_flow.audio_notebooklm import audio_notebooklm_service
            retrying_podcast = False

            def progress(event):
                nonlocal retrying_podcast
                percent, stage = self._audio_summary_progress(event, retrying_podcast=retrying_podcast)
                if isinstance(event, dict) and event.get("state") == "audio_retry":
                    retrying_podcast = True
                self._get_audio_flow_jobs().update_progress(job, percent, stage)

            result = audio_notebooklm_service.generate(
                text,
                depth=depth,
                style=style,
                cancelled=job.is_cancelled,
                on_progress=progress,
            )
            if job.is_cancelled():
                raise RuntimeError("Audio summary cancelled")
            audio_path = str((result or {}).get("audio_path") or "")
            if not audio_path:
                raise RuntimeError("NotebookLM did not return summary audio.")
            duration = float((result or {}).get("duration_sec") or 0.0)
            if not duration:
                try:
                    import wave
                    with wave.open(audio_path, "rb") as audio_file:
                        duration = audio_file.getnframes() / float(audio_file.getframerate())
                except Exception:
                    try:
                        duration = max(10.0, Path(audio_path).stat().st_size / 16000.0)
                    except Exception:
                        duration = 0.0
            return {"audio_path": audio_path, "duration_sec": duration}

        try:
            if len(text.encode("utf-8")) > 100_000:
                payloads.pop(job_id, None)
                raise ValueError("Selected text is too long for an Audio Summary. Shorten the selection and try again.")
            self._get_audio_flow_jobs().submit(
                job_id=job_id,
                text=text,
                depth=depth,
                style=style,
                title=title,
                run=run,
                before_enqueue=persist_initial,
            )
        except Exception as exc:
            payloads.pop(job_id, None)
            if isinstance(exc, RuntimeError) and "queue is full" in str(exc).lower():
                if self.state == DictationState.IDLE and not getattr(self, "_read_active", False):
                    self.overlay.show_error(str(exc))
            elif isinstance(exc, ValueError) and "too long" in str(exc).lower():
                if self.state == DictationState.IDLE and not getattr(self, "_read_active", False):
                    self.overlay.show_error(str(exc))
            raise
        return job_id

    def _get_read_generation_lock(self):
        lock = getattr(self, "_read_generation_lock", None)
        if lock is None:
            lock = self._read_generation_lock = threading.RLock()
        return lock

    @staticmethod
    def _audio_summary_progress(event, *, retrying_podcast: bool = False) -> tuple[int, str]:
        if isinstance(event, dict):
            state = str(event.get("state") or "")
            elapsed = float(event.get("elapsed") or 0.0)
            if state == "notebook_create":
                return 15, "Setting up notebook"
            if state == "source_add":
                return 30, "Adding source text"
            if state == "source_ready":
                return 40, "Source text ready"
            if state == "audio_start":
                if retrying_podcast:
                    return 88, "Shortening podcast summary"
                return 50, "Starting audio generation"
            if state == "audio_retry":
                return 88, "Shortening podcast summary"
            if state == "audio_poll":
                if retrying_podcast:
                    return 88, f"Shortening podcast summary ({int(elapsed)}s)"
                return min(88, 50 + int(elapsed * 0.8)), f"Synthesizing audio ({int(elapsed)}s)"
            if state == "audio_download":
                return 92, "Downloading summary audio"
            msg = event.get("message") or event.get("stage") or event.get("status")
            return int(event.get("progress") or 25), str(msg or "Preparing summary")[:44]
        if isinstance(event, (int, float)):
            return max(0, min(99, int(event))), "Preparing summary"
        if isinstance(event, str):
            return 25, event[:44]
        return 5, "Preparing summary"

    def _on_audio_summary_job_changed(self, job) -> None:
        payloads = getattr(self, "_audio_summary_payloads", {})
        payload = payloads.get(job.job_id, {})
        try:
            if job.status in {"queued", "running"}:
                self._show_audio_summary_progress(job.progress, job.stage, job.job_id, "Audio Flow")
                try:
                    storage.update_audio_summary_history(job.job_id, status="in_progress", progress=job.progress)
                except Exception:
                    pass
                return

            if job.status == "ready":
                result = job.result or {}
                audio_path = str(result.get("audio_path") or "")
                duration = float(result.get("duration_sec") or 0.0)
                title = str(payload.get("title") or job.title or "Audio Summary")
                text = str(payload.get("text") or "")
                try:
                    storage.update_audio_summary_history(
                        job.job_id, status="ready", progress=100, audio_path=audio_path,
                        duration_sec=duration, title=title,
                    )
                    storage.record_audio_summary_to_history(
                        audio_id=job.job_id, title=title, text_snippet=text,
                        audio_path=audio_path, duration_sec=duration, status="success",
                    )
                    from voice_flow.gui.api_server import invalidate_history_cache
                    invalidate_history_cache()
                except Exception as exc:
                    log.debug("Failed to persist completed audio summary: %s", exc)
                # Matching Video Flow: do not automatically pop up or auto-play.
                # The user clicks the floating bar ready row to open and play on demand.
                threading.Thread(
                    target=self._export_audio_summary_copy,
                    args=(job.job_id, title, audio_path),
                    name=f"AudioSummaryExport-{job.job_id[-6:]}",
                    daemon=True,
                ).start()
                self._show_audio_summary_ready(job.job_id, "Audio ready")
            elif job.status == "failed":
                message = str(job.error or "Audio summary failed")
                try:
                    storage.update_audio_summary_history(job.job_id, status="failed", error=message)
                    storage.record_audio_summary_to_history(
                        audio_id=job.job_id, title=job.title,
                        text_snippet=str(payload.get("text") or ""), status="failed", error_message=message,
                    )
                    from voice_flow.gui.api_server import invalidate_history_cache
                    invalidate_history_cache()
                except Exception:
                    pass
                self._show_audio_summary_failed(job.job_id, message)
            elif job.status == "cancelled":
                try:
                    storage.update_audio_summary_history(job.job_id, status="cancelled", progress=0, error="Cancelled by user")
                    storage.record_audio_summary_to_history(
                        audio_id=job.job_id, title=job.title,
                        text_snippet=str(payload.get("text") or ""), status="cancelled", error_message="Cancelled by user",
                    )
                    from voice_flow.gui.api_server import invalidate_history_cache
                    invalidate_history_cache()
                except Exception:
                    pass
                self._clear_audio_summary_status(job.job_id)
        finally:
            if job.status in {"ready", "failed", "cancelled"}:
                payloads.pop(job.job_id, None)
                job.text = ""
                job.run = lambda _job: None

    def _export_audio_summary_copy(self, job_id: str, title: str, audio_path: str) -> None:
        try:
            from voice_flow.audio_summary_player import save_media_to_downloads, safe_media_filename
            suffix = f"_{job_id}"
            bounded_title = (title or "Audio Summary")[:70]
            clean_name = safe_media_filename(
                f"{bounded_title}{suffix}",
                default="Audio_Summary",
                ext=Path(audio_path).suffix or ".m4a",
                max_length=105,
            )
            saved_path, _ = save_media_to_downloads(audio_path, clean_name, copy_to_media_folder=True)
            if saved_path and saved_path.is_file():
                storage.update_audio_summary_history(job_id, downloaded=1)
        except Exception as exc:
            log.debug("Optional audio summary export failed: %s", exc)

    def _show_audio_summary_progress(self, progress: int, stage: str, job_id: str, title: str) -> None:
        callback = getattr(self.overlay, "show_audio_summary_progress", None)
        if not callable(callback):
            return
        try:
            callback(progress, stage, job_id=job_id, title=title)
        except Exception:
            log.debug("Could not update Audio Summary progress row %s", job_id, exc_info=True)

    def _show_audio_summary_ready(self, job_id: str, stage: str) -> None:
        callback = getattr(self.overlay, "show_audio_summary_ready", None)
        try:
            if callable(callback):
                callback(job_id, stage=stage)
            elif hasattr(self.overlay, "show_audio_summary_progress"):
                self._show_audio_summary_progress(100, stage, job_id, "Audio Flow")
        except Exception:
            log.debug("Could not show ready Audio Summary row %s", job_id, exc_info=True)

    def _show_audio_summary_failed(self, job_id: str, message: str) -> None:
        callback = getattr(self.overlay, "show_audio_summary_failed", None)
        try:
            if callable(callback):
                callback(job_id, message)
            else:
                self._show_audio_summary_progress(0, message[:44], job_id, "Audio Flow")
        except Exception:
            log.debug("Could not show failed Audio Summary row %s", job_id, exc_info=True)

    def _clear_audio_summary_status(self, job_id: str) -> None:
        callback = getattr(self.overlay, "clear_audio_summary_status", None)
        if callable(callback):
            try:
                callback(job_id)
            except Exception:
                log.debug("Could not clear Audio Summary row %s", job_id, exc_info=True)

    def _try_open_audio_summary_job(self, job_id: str, *, automatic: bool) -> bool:
        lock = self._get_read_generation_lock()
        with lock:
            if self.state != DictationState.IDLE or getattr(self, "_read_active", False) or getattr(self, "_read_pending", False):
                return False
            try:
                if tts_engine.is_speaking():
                    return False
            except Exception:
                pass
            if getattr(self, "_audio_summary_launch_reservation", None):
                return False
            current = getattr(self, "_active_summary_player_token", None)
            if automatic and current:
                return False
            jobs = getattr(self, "_audio_flow_jobs", None)
            if automatic and jobs is not None and any(
                job.job_id != job_id and job.status in {"queued", "running"}
                for job in jobs.snapshot()
            ):
                return False
            self._audio_summary_launch_reservation = job_id
        try:
            jobs = getattr(self, "_audio_flow_jobs", None)
            job = jobs.get(job_id) if jobs is not None else None
            if job is None or job.status != "ready" or not job.result:
                self._clear_audio_summary_launch_reservation(job_id)
                return False
            if current:
                from voice_flow.audio_summary_player import close_summary_audio_player
                close_summary_audio_player(current)
            from voice_flow.audio_summary_player import launch_summary_audio_player
            player_token = launch_summary_audio_player(
                str(job.result.get("audio_path") or ""),
                depth=job.depth,
                title=job.title,
                token=job.job_id,
                style=job.style,
                close_existing=False,
            )
        except Exception as exc:
            self._clear_audio_summary_launch_reservation(job_id)
            log.warning("Could not open ready audio summary %s: %s", job_id, exc)
            return False
        with lock:
            if (
                getattr(self, "_audio_summary_launch_reservation", None) != job_id
                or self.state != DictationState.IDLE
                or getattr(self, "_read_active", False)
                or getattr(self, "_read_pending", False)
            ):
                stale = True
            else:
                self._active_summary_player_token = player_token
                self._audio_summary_launch_reservation = None
                stale = False
        if stale:
            from voice_flow.audio_summary_player import close_summary_audio_player
            close_summary_audio_player(player_token)
            return False
        return True

    def _clear_audio_summary_launch_reservation(self, job_id: str) -> None:
        with self._get_read_generation_lock():
            if getattr(self, "_audio_summary_launch_reservation", None) == job_id:
                self._audio_summary_launch_reservation = None

    def cancel_audio_summary_job(self, job_id: str) -> bool:
        jobs = getattr(self, "_audio_flow_jobs", None)
        if jobs is None:
            return False
        return jobs.cancel(str(job_id or ""))

    def open_audio_summary_job(self, job_id: str) -> bool:
        return self._try_open_audio_summary_job(job_id, automatic=False)
    def _process_video_flow_pipeline(self, mode: str, text_override: str | None = None) -> None:
        """Open the primary system-wide composer for selected text."""
        if not storage.get_setting("video_flow_enabled", True):
            self.overlay.show_error("Video Flow is disabled")
            return
        text = (text_override or "").strip()
        if not text:
            text = self._capture_selected_text_for_video()
        target_mode = "full" if mode == "full" else "summary"
        video_flow_widget.show_composer(text or "", target_mode, anchor_bar=self.overlay)

    def _capture_selected_text_for_video(self) -> str:
        """Copy foreground selection swiftly without hanging UI or destroying clipboard.

        The previous clipboard content is restored only when it is plain text so
        image/file clipboards are never destroyed by a stray restore.
        Performs a swift non-blocking capture with max 50ms deadline.
        """
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return ""

            # Safeguard 1: Do not send synthetic Ctrl+C to the floating overlay itself
            overlay_win = getattr(self.overlay, "win", None)
            if overlay_win:
                try:
                    if hwnd == overlay_win.winfo_id():
                        return ""
                except Exception:
                    pass

            # Safeguard 2: Do not send synthetic Ctrl+C to console/terminal windows
            is_windows_terminal = False
            try:
                from voice_flow.injector import get_window_class_name, get_active_window_title
                active_title = get_active_window_title() or ""
                active_class = get_window_class_name(hwnd) if hwnd else ""
                is_windows_terminal = (
                    active_class == "CASCADIA_HOSTING_WINDOW_CLASS"
                    or "windows terminal" in active_title.lower()
                )
                is_other_console = (
                    not is_windows_terminal
                    and (
                        active_class in ("ConsoleWindowClass", "mintty", "PuTTY", "VirtualConsoleClass")
                        or any(kw in active_title.lower() for kw in ["cmd", "powershell", "terminal", "bash", "ubuntu", "command prompt", "putty", "mintty", "pwsh", "codex", "claude"])
                    )
                )
                if is_other_console:
                    return ""
            except Exception:
                is_windows_terminal = False

            import pyperclip
            try:
                from voice_flow.injector import focus_target_window
                focus_target_window(hwnd)
            except Exception:
                pass
            try:
                previous = pyperclip.paste()
            except Exception:
                previous = None
            marker = f"__voice_flow_selection_{time.time_ns()}__"
            try:
                pyperclip.copy(marker)
                if is_windows_terminal:
                    # Windows Terminal uses Ctrl+Shift+C to copy without sending SIGINT
                    user32.keybd_event(0x11, 0, 0, 0)
                    user32.keybd_event(0x10, 0, 0, 0)
                    user32.keybd_event(0x43, 0, 0, 0)
                    time.sleep(0.01)
                    user32.keybd_event(0x43, 0, 0x0002, 0)
                    user32.keybd_event(0x10, 0, 0x0002, 0)
                    user32.keybd_event(0x11, 0, 0x0002, 0)
                else:
                    user32.keybd_event(0x11, 0, 0, 0); user32.keybd_event(0x43, 0, 0, 0)
                    user32.keybd_event(0x43, 0, 0x0002, 0); user32.keybd_event(0x11, 0, 0x0002, 0)
                deadline = time.monotonic() + 0.35  # robust capture: max 350ms for Win32 clipboard sync
                while time.monotonic() < deadline:
                    copied = pyperclip.paste()
                    if copied != marker:
                        return str(copied or "").strip()
                    time.sleep(0.005)
                return ""
            finally:
                # Only restore text clipboards; pyperclip.copy(None) raises and
                # non-text (image/file) clipboards cannot be restored via text.
                if isinstance(previous, str):
                    try:
                        pyperclip.copy(previous)
                    except Exception:
                        pass
        except Exception:
            log.warning("Could not capture selected text for Video Flow", exc_info=True)
            return ""

    def _queue_video_from_screen(self, payload: dict) -> dict:
        """Queue a system-wide composer request and mirror progress on the bar."""
        from voice_flow.video_flow_service import get_video_flow_service

        payload["allow_local_fallback"] = True
        provider = str(payload.get("provider") or payload.get("video_engine") or "notebooklm").strip() or "notebooklm"
        video_engine = str(payload.get("video_engine") or payload.get("provider") or "notebooklm").strip() or "notebooklm"

        options = dict(payload)
        for k in ["source_text", "mode", "title", "source_name", "model_ref", "theme", "visual_direction", "allow_external_ai", "video_engine", "provider", "allow_local_fallback"]:
            options.pop(k, None)

        job = get_video_flow_service().queue(
            source_text=str(payload.get("source_text", "")),
            mode=str(payload.get("mode", "summary")),
            title=str(payload.get("title", "")),
            source_name=payload.get("source_name") or "",
            model_ref=str(payload.get("model_ref", "") or "") or None,
            theme=payload.get("theme", "auto"),
            visual_direction=str(payload.get("visual_direction", "")),
            allow_external_ai=bool(payload.get("allow_external_ai", False)),
            allow_local_fallback=True,
            provider=provider,
            video_engine=video_engine,
            **options,
        )
        video_id = job.job_id
        self.video_stage = "Queued"
        self.overlay.show_video_progress(video_id, 0, "Queued")
        threading.Thread(
            target=self._monitor_video_flow_job,
            args=(video_id,),
            daemon=True,
            name=f"video-flow-monitor-{video_id[:8]}",
        ).start()
        log.info("[VIDEO FLOW] Queued screen video %s.", video_id)
        return {"id": video_id}

    def _cancel_video_from_screen(self, video_id: str) -> None:
        """Stop a Video Flow job without interrupting Voice or Audio Flow."""
        from voice_flow.video_flow_service import get_video_flow_service

        if get_video_flow_service().cancel(video_id):
            log.info("[VIDEO FLOW] Cancelled screen video %s.", video_id)
        self.video_stage = ""
        self.overlay.clear_video_status(video_id)

    def _monitor_video_flow_job(self, video_id: str) -> None:
        """Keep the bar sidecar synchronized until the player is ready."""
        from voice_flow.video_flow_service import get_video_flow_service

        service = get_video_flow_service()
        while video_id:
            job = service.get(video_id)
            if job is None:
                self.video_stage = "Video job disappeared"
                self.overlay.show_video_failed(video_id, "Video job disappeared")
                return
            state = str(job.state)
            if state == "complete" or job.progress >= 100.0:
                self.video_stage = "Video ready"
                self.overlay.show_video_ready(video_id)
                return
            if state == "failed":
                reason = str(job.meta.get("error_message") or job.message or job.meta.get("error_code") or "Video generation failed")
                self.video_stage = reason
                self.overlay.show_video_failed(video_id, reason)
                return
            if state == "cancelled":
                self.video_stage = ""
                self.overlay.clear_video_status(video_id)
                return
            stage_text = str(job.message or state or "Creating video")
            self.video_stage = stage_text
            self.overlay.show_video_progress(
                video_id,
                job.progress,
                stage_text,
            )
            time.sleep(0.4)
    def _stop_audio_flow_pipeline(self) -> None:
        """Stop foreground Read and an explicitly tracked summary player only."""
        with self._get_read_generation_lock():
            self._read_generation = getattr(self, "_read_generation", 0) + 1
            self._read_active = False
            self._read_pending = False
            self._audio_summary_launch_reservation = None
            player_token = getattr(self, "_active_summary_player_token", None)
            if player_token:
                try:
                    from voice_flow.audio_summary_player import close_summary_audio_player
                    close_summary_audio_player(player_token)
                except Exception:
                    pass
                self._active_summary_player_token = None
            tts_engine.stop()
        audio_flow_widget.set_playing(False)
        if self.state == DictationState.IDLE:
            self.overlay.show_ready()
    def _toggle_audio_flow_pause(self) -> None:
        """Stop verbatim Read playback. Read is intentionally not resumable."""
        if tts_engine.is_speaking():
            self._stop_audio_flow_pipeline()
        audio_flow_widget.set_paused(False)
        if getattr(self, "overlay", None) and getattr(self.overlay, "state", None) == "READING":
            self.overlay.refresh()

    def _open_audio_flow_settings(self) -> None:
        """Open the complete on-screen Voice Model Catalog & Speed Settings dialog."""
        from voice_flow.audio_flow_dialog import open_audio_flow_settings
        open_audio_flow_settings(
            parent=getattr(self, "overlay", None),
            on_speed_change=lambda spd: (
                tts_engine.set_speed(spd),
                self.overlay.show_reading("Audio Flow") if (getattr(self, "overlay", None) and self.overlay.state == "READING") else (self.overlay.refresh() if getattr(self, "overlay", None) else None),
                audio_flow_widget._draw()
            ),
            on_voice_change=lambda v: (
                storage.save_setting("exec_audio_policy_model", v),
                audio_flow_widget._draw()
            ),
        )
    def _watch_gui_state_file(self) -> None:
        """Monitor ~/.voice_flow/recording_state.json for recording toggle events from GUI."""
        import json
        import os
        from voice_flow.paths import data_dir
        from voice_flow.storage import storage as _gui_storage
        state_file = str(data_dir() / "recording_state.json")

        try:
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            with open(state_file, "w") as f:
                json.dump({"recording": False}, f)
        except Exception:
            pass

        last_mtime = os.path.getmtime(state_file) if os.path.exists(state_file) else 0

        last_gui_recording = False
        while True:
            time.sleep(1.0)
            try:
                # The GUI toggles hands-free dictation through the 'recording'
                # setting (app.js -> /api/record), not through the state file.
                try:
                    _rec_setting = bool(_gui_storage.get_setting("recording", False))
                except Exception as exc:
                    # A failed read is not a user-requested stop. Preserve the
                    # last observed setting and wait for a successful read.
                    _rec_setting = last_gui_recording
                    log.debug("GUI recording setting read error: %s", exc)
                if _rec_setting != last_gui_recording:
                    last_gui_recording = _rec_setting
                    if _rec_setting:
                        threading.Thread(target=self._on_dictation_start, daemon=True).start()
                    else:
                        threading.Thread(target=self._on_dictation_finish, daemon=True).start()
                if os.path.exists(state_file):
                    mtime = os.path.getmtime(state_file)
                    if mtime > last_mtime:
                        last_mtime = mtime
                        with open(state_file, "r") as f:
                            data = json.load(f)
                        gui_recording = data.get("recording", False)
                        if gui_recording and not self.is_recording:
                            self._on_dictation_start()
                        elif not gui_recording and self.is_recording:
                            self._on_dictation_finish()
            except Exception as e:
                log.debug("GUI state file watcher error: %s", e)

    def run(self) -> None:
        log.info("Starting input trigger hooks...")
        # Sync this engine to the active account database (and consolidate any
        # legacy fragmentation) before accepting dictations.
        try:
            storage.repoint_if_needed()
            from voice_flow.consolidate import consolidate_engine
            consolidate_engine(storage, dry_run=False)
        except Exception as exc:
            log.warning("Could not prepare active database at startup: %s", exc)
        self.hotkeys.start()

        # Start GUI recording state watcher
        threading.Thread(target=self._watch_gui_state_file, daemon=True).start()

        # Ensure embedded API server thread is running
        try:
            from voice_flow.gui.api_server import start_api_server, register_runtime_controller
            register_runtime_controller(self)
            if not getattr(self, "_api_server_thread", None) or not self._api_server_thread.is_alive():
                self._api_server_thread = threading.Thread(target=start_api_server, daemon=True, name="VoiceFlowApiServer")
                self._api_server_thread.start()
        except Exception as exc:
            log.warning("Could not start embedded API server in run(): %s", exc)

        # Start NotebookLM background keepalive & silent session auto-refresh daemon
        try:
            from voice_flow.video_flow_engine.notebooklm import start_keepalive_daemon, trigger_keepalive_now
            start_keepalive_daemon()
            trigger_keepalive_now(force=False, background=True)
        except Exception as exc:
            log.debug("NotebookLM keepalive startup trigger: %s", exc)

        # Launch Desktop UI Window silently in a dedicated process if not already open
        try:
            args = getattr(self, "args", None)
            headless = getattr(args, "headless", False) if args else False
            no_gui = getattr(args, "no_gui", False) if args else False
            if not headless and not no_gui:
                window_open = False
                try:
                    from voice_flow.gui.desktop_launcher import _focus_existing_window
                    window_open = _focus_existing_window()
                except Exception:
                    window_open = False

                if not window_open:
                    from voice_flow.watchdog import get_pythonw_executable, get_pythonw_env, get_silent_windows_spawn_kwargs
                    pythonw_exe = get_pythonw_executable()
                    src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                    env = get_pythonw_env()
                    spawn_kwargs = get_silent_windows_spawn_kwargs()

                    subprocess.Popen(
                        [pythonw_exe, "-m", "voice_flow.gui.desktop_launcher"],
                        cwd=src_dir,
                        env=env,
                        close_fds=True,
                        **spawn_kwargs,
                    )
        except Exception as e:
            log.warning("Could not launch Desktop GUI: %s", e)

        log.info("==========================================================")
        log.info(" VOICE FLOW READY! ")
        log.info(" - System-wide floating bar active on your screen")
        from voice_flow.hotkeys import platform_input_defaults
        log.info(" - %s", platform_input_defaults()["ready_line"])
        log.info(" - Release to transcribe, clean up, and auto-paste!")
        log.info("==========================================================")

        # Run Tkinter Floating Overlay Bar on the MAIN THREAD
        while not getattr(self, "_shutdown_requested", False):
            try:
                self.overlay.run_loop()
                break
            except Exception as e:
                log.error("Overlay main loop error: %s", e)
                time.sleep(1.0)

    def reset_state_and_refresh(self) -> None:
        """Reset dictation/audio state, cancel any in-flight/stuck recordings, and restart/refresh overlay."""
        try:
            with self._state_lock:
                self.state = DictationState.IDLE
                self._pending_command = None
                if hasattr(self, "audio") and hasattr(self.audio, "cancel"):
                    try:
                        self.audio.cancel()
                    except Exception:
                        pass
        except Exception as e:
            log.debug("State lock error during reset_state_and_refresh: %s", e)

        try:
            if hasattr(self, "overlay") and self.overlay:
                if hasattr(self.overlay, "restart_and_refresh"):
                    self.overlay.restart_and_refresh()
                elif hasattr(self.overlay, "show"):
                    self.overlay.show()
        except Exception as e:
            log.debug("Overlay restart error during reset_state_and_refresh: %s", e)
    def stop(self) -> None:
        jobs = getattr(self, "_audio_flow_jobs", None)
        if jobs is not None:
            jobs.shutdown(timeout=2.0)
        try:
            from voice_flow.video_flow_engine.notebooklm import stop_keepalive_daemon
            stop_keepalive_daemon()
        except Exception:
            pass
        self.hotkeys.stop()
        self.audio.stop()
        self.audio.close()


VoiceFlowController = VoiceFlowApp


_ENGINE_MUTEX_HANDLE = None


def main() -> None:
    if "--test-crash-reporting" in sys.argv:
        from voice_flow._version import VERSION
        from voice_flow.crash_reporting import is_crash_reporting_enabled, capture_test_crash_report
        if is_crash_reporting_enabled():
            success = capture_test_crash_report()
            if success:
                print(f"Test crash report from AI Productivity Flow v{VERSION} sent successfully.")
            else:
                print("Failed to send test crash report.")
            sys.exit(0)
        else:
            print("Crash reporting is currently disabled (opt-in only). Enable it in Settings to test.")
            sys.exit(0)

    try:
        from voice_flow.crash_reporting import init_crash_reporting
        init_crash_reporting()
    except Exception:
        pass

    global _ENGINE_MUTEX_HANDLE
    # Single-instance enforcement: prevent multiple background engine processes from running concurrently
    if sys.platform == "win32" and "pytest" not in sys.modules:
        try:
            ERROR_ALREADY_EXISTS = 183
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            _ENGINE_MUTEX_HANDLE = kernel32.CreateMutexW(None, False, "Local\\VoiceFlowMainEngineMutex_v1")
            last_err = ctypes.get_last_error()
            if _ENGINE_MUTEX_HANDLE and last_err == ERROR_ALREADY_EXISTS:
                log.info("Another instance of Voice Flow main engine is already running. Signaling running instance to restore & refresh.")
                try:
                    from voice_flow.single_instance import signal_running_instance_to_restore
                    signal_running_instance_to_restore()
                except Exception as exc:
                    log.debug("Signaling running instance error: %s", exc)
                return
        except Exception:
            pass

    app: VoiceFlowApp | None = None
    try:
        from voice_flow.gui.api_server import PORT
        from voice_flow.runtime_guard import prepare_runtime_port

        runtime_port = prepare_runtime_port(port=PORT, require_engine=True)
        if runtime_port.status == "occupied":
            log.warning("Port 8991 is currently occupied by another listener.")
            return
        app = VoiceFlowApp()
        app.run()
    except KeyboardInterrupt:
        log.info("Shutting down Voice Flow.")
        if app is not None:
            app.stop()
        return
    except Exception as exc:
        import traceback
        log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "crash_log.txt"))
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n[UNCAUGHT ERROR] {exc}\n")
            f.write(traceback.format_exc())
            f.write("\n" + "="*50 + "\n")


if __name__ == "__main__":
    main()

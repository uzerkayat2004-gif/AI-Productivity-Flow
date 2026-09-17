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
import ctypes
from voice_flow.platform.wincompat import wintypes, windll, IS_WINDOWS

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
from voice_flow.polisher import polisher
from voice_flow.storage import storage
from voice_flow.style_engine import get_window_title_for_hwnd, style_engine
from voice_flow.text_processing import apply_spoken_punctuation, cleanup_text, smart_format, split_press_enter
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



def _warm_voice_gemini_transport(model_ref: object) -> None:
    """Hide native Gemini TLS setup under recording without delaying capture."""
    if not str(model_ref or "").strip().lower().startswith("gemini/"):
        return
    try:
        if not storage.get_setting("polishing_enabled", True):
            return
        from voice_flow.voice_gemini_transport import warm_gemini_connection
        threading.Thread(target=warm_gemini_connection, name="voice-gemini-prewarm", daemon=True).start()
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
    """Describe a polish result without claiming a failed AI pass was local."""
    return {
        "ai_accepted": "AI polished",
        "local": "Cleaned locally",
        "local_model": "Cleaned locally (offline model)",
        "disabled": "Transcribed",
        "timeout": "AI timed out — original text kept",
        "provider_failure": "AI unavailable — original text kept",
        "fidelity_reject": "AI unavailable — original text kept",
    }.get(str(outcome or ""), "AI unavailable — original text kept")


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

        # Load saved microphone preference if available
        saved_mic = storage.get_setting("selected_mic_device", None)
        if saved_mic is None:
            # Older builds saved the GUI mic pick under "selected_microphone"
            # (a key the engine never read) — honor an earlier pick instead of
            # silently dropping it.
            saved_mic = storage.get_setting("selected_microphone", None)
        if saved_mic not in (None, ""):
            config.selected_mic_device = saved_mic
            log.info("Loaded saved microphone preference: %s", saved_mic)
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
        self.overlay = FloatingOverlayBar()
        self.injector = ClipboardInjector()
        self.processing_lock = threading.Lock()
        self._audio_summary_generation = 0
        self._active_summary_player_token: str | None = None
        self.video_stage = ""

        # Ensure local REST API server is always active in background for video playback and UI
        self._api_server_thread: threading.Thread | None = None
        try:
            from voice_flow.gui.api_server import start_api_server, register_runtime_controller
            register_runtime_controller(self)
            self._api_server_thread = threading.Thread(target=start_api_server, daemon=True, name="VoiceFlowApiServer")
            self._api_server_thread.start()
        except Exception as exc:
            log.warning("Could not start embedded API server: %s", exc)

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
        with lock:
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
            cache[key] = (now, val)
        return val

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

    def _capture_session(self) -> DictationSession:
        """Read foreground app context once, before recording changes the UI."""
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
            self._stream_stt = FluxStreamTranscriber(
                dictionary_engine.get_stt_hint_terms(getattr(session, "app_category", None))
            )
            self.audio.on_audio_frame = self._stream_stt.submit_frame
        elif str(model_ref or "").lower().startswith("deepgram/nova-3"):
            self._stream_stt = NovaStreamTranscriber(
                dictionary_engine.get_stt_hint_terms(getattr(session, "app_category", None))
            )
            self.audio.on_audio_frame = self._stream_stt.submit_frame
        elif is_nemotron_model(model_ref):
            self._stream_stt = NemotronStreamTranscriber(
                dictionary_engine.get_stt_hint_terms(getattr(session, "app_category", None))
            )
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
        try:
            enabled = storage.get_setting("voice_flow_enabled", True)
        except Exception as exc:
            log.warning("Could not read Voice Flow feature toggle; keeping it enabled: %s", exc)
            enabled = True
        if not enabled:
            log.info("Voice Flow dictation is disabled via the feature toggle.")
            return False

        if self.state == DictationState.PROCESSING:
            log.info("Cancelling stale PROCESSING session to service new dictation request.")
            self._on_dictation_cancel()
        elif self.state == DictationState.ERROR:
            self._reset_to_idle()

        with self._state_lock:
            if self.state != DictationState.IDLE:
                log.info("Refusing start dictation while in state %s", self.state)
                return False
            try:
                session = self._capture_session()
            except Exception as exc:
                log.error("[START ERROR] Could not capture dictation context: %s", exc, exc_info=True)
                return False
            self.session = session
            self.state = DictationState.RECORDING

        hwnd = getattr(session, "target_hwnd", None) or (session.get("hwnd") if isinstance(session, dict) else None)
        app_title = getattr(session, "app_title", "General App") or (session.get("app_title") if isinstance(session, dict) else "General App")
        log.info("[RECORDING] Dictation triggered for target hwnd %s (%s)", hwnd, app_title)

        audio_started = False
        try:
            self._set_hotkeys_recording_state(True)

            watchdog = getattr(self, "_record_watchdog", None)
            if watchdog:
                watchdog.cancel()
                self._record_watchdog = None

            # The timer carries this immutable session so a later recording cannot
            # be finished by a stale twenty-minute watchdog.
            self._record_watchdog = threading.Timer(20 * 60, self._finish_if_current, args=(self.session,))
            self._record_watchdog.daemon = True
            self._record_watchdog.start()

            # Start capture before provider/model preparation. The recorder
            # holds initial frames and closed chunks until the stream is armed.
            begin_buffering = getattr(self.audio, "begin_stream_input_buffering", None)
            if callable(begin_buffering):
                begin_buffering()
            audio_started = bool(self.audio.start())
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
                self._overlay_call("show_error", "Microphone hardware failed to open")
                return False

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

            # Show 'recording' only once the microphone can receive words.
            self._overlay_call("show_recording", level_provider=lambda: self.audio.level)
            return True
        except Exception as exc:
            # Never leave a half-started session: reset watchdog, mic, hotkeys,
            # and state so the engine cannot get stuck in RECORDING.
            log.error("[START ERROR] %s", exc, exc_info=True)
            watchdog = getattr(self, "_record_watchdog", None)
            if watchdog:
                watchdog.cancel()
                self._record_watchdog = None
            if audio_started:
                try:
                    self.audio.stop()
                except Exception:
                    pass
            discard_buffer = getattr(self.audio, "discard_stream_input_buffer", None)
            if callable(discard_buffer):
                discard_buffer()
            self._end_stream_session(discard=True)
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
                storage.add_dictation(
                    raw_text, polished_text, app_title, duration, category,
                    status=status, audio_path=audio_path,
                    error_message=error_message, insertion_status=insertion_status,
                )
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

        def _notify_outcome(outcome: str) -> None:
            observed_outcome["value"] = str(outcome)
            if outcome_callback is not None:
                outcome_callback(outcome)

        polished = _call_with_optional_deadline(
            polisher.polish,
            raw_action_text,
            deadline=deadline,
            model_ref=getattr(session, "polish_model_ref", None) or (session.get("polish_model_ref") if isinstance(session, dict) else None),
            style_instruction=style_instruction,
            cleanup_level=level,
            force_ai=force_ai,
            task=task,
            overrides=command_overrides,
            outcome_callback=_notify_outcome,
            speed_mode=_normalize_polish_speed_mode(speed_mode or getattr(session, "polish_speed_mode", None) or (session.get("polish_speed_mode") if isinstance(session, dict) else None)),
        )
        # A timeout/failure must not be followed by style formatting that
        # changes wording while the UI says the original was kept.
        if observed_outcome["value"] in {"timeout", "provider_failure", "fidelity_reject", "disabled"}:
            return raw_action_text
        formatted = smart_format(polished, post_style_id, context)
        # Style formatters may lowercase casual text after the polisher has
        # restored canonical vocabulary. Restore casing only; running the
        # correction rules again could turn an earlier replacement into a
        # new trigger and change the user's meaning.
        try:
            return dictionary_engine.restore_dictionary_spelling(formatted)
        except Exception:
            log.debug("[DICTIONARY] final vocabulary guard failed", exc_info=True)
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
            # Streaming has a short release target. Complete audio recovery
            # and requested AI transformations have their own bounded budgets;
            # missing the streaming target must not truncate either operation.
            post_release_deadline = getattr(self, "_post_release_deadline", None)
            if post_release_deadline is None:
                post_release_deadline = time.monotonic() + POST_RELEASE_WORK_BUDGET_SECONDS
            complete_recording_deadline = time.monotonic() + _complete_recording_budget_seconds(duration)
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
                if use_streaming:
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

                # Voice Flow command layer: deterministic wake-phrase command
                # detection. The raw transcript is first repaired for known
                # mis-hearings of the wake term ("Wiseflow" -> "Voice Flow");
                # any failure here falls back to plain dictation — the user's
                # words are never lost (spec §49).
                command = None
                command_content = raw_transcript
                try:
                    detection = detect_voice_command(dictionary_engine.repair_wake_term(raw_transcript))
                    command_content = detection.content or ""
                    command = detection.command
                except Exception:
                    log.exception("[COMMAND] detection failed; using plain dictation")

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
                            self._history_update(record_id, raw_text=raw_transcript, polished_text="", status="success", error_message=detail, insertion_status="not_attempted")
                            self._defer_history_insert(recovery, session, duration, raw_text=raw_transcript, status="success", error_message=detail)
                            self._reset_to_idle(session)
                            self._overlay_call("show_error", detail)
                            return
                        detail = persistent_applied
                        self._history_update(record_id, raw_text=raw_transcript, polished_text="", status="success", error_message=f"Persistent command saved: {detail}", insertion_status="not_attempted")
                        self._defer_history_insert(recovery, session, duration, raw_text=raw_transcript, status="success", error_message=f"Persistent command saved: {detail}")
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
                        self._history_update(record_id, raw_text=raw_transcript, polished_text="", status="success", error_message=f"Command armed: {command.label()}", insertion_status="not_attempted")
                        self._defer_history_insert(recovery, session, duration, raw_text=raw_transcript, status="success", error_message=f"Command armed: {command.label()}")
                        self._reset_to_idle(session)
                        self._overlay_call("show_done", f"Voice Flow: {command.label()} — dictate the content next")
                        return
                if command is None:
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

                def _record_polish_outcome(outcome: str) -> None:
                    # This closure is scoped to this pipeline invocation.
                    polish_outcome["value"] = str(outcome)

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
                )
                polish_elapsed = time.perf_counter() - polish_started
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
                self._history_update(record_id, raw_text=raw_transcript, polished_text=polished_text, status="success", error_message=outcome_note, insertion_status="not_attempted")

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
                    self._defer_history_insert(recovery, session, duration, raw_text=raw_transcript, polished_text=polished_text, status="success", error_message=outcome_note, insertion_status="ready_to_paste")
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
                    "[VOICE LATENCY] stt_ms=%.0f polish_ms=%.0f injection_ms=%.0f total_ms=%.0f stream=%s",
                    stt_elapsed * 1000,
                    polish_elapsed * 1000,
                    injection_elapsed * 1000,
                    (time.perf_counter() - pipeline_started) * 1000,
                    "yes" if used_stream_text else "no",
                )

                # Accepted transcript state is updated only after a successful paste.
                # An action-only Enter must not erase the prior copy-last transcript.
                if success and polished_text.strip():
                    # Correction learning (spec §35/§41): cheap diff of raw vs
                    # final text, recorded asynchronously so insertion never
                    # waits on it.
                    try:
                        import threading as _th

                        def _learn_corrections(raw_txt=raw_transcript, final_txt=polished_text):
                            try:
                                for term, variant in extract_correction_pairs(raw_txt, final_txt):
                                    storage.record_lexicon_candidate(term, variant)
                            except Exception:
                                log.exception("[LEARNING] correction capture failed")

                        _th.Thread(target=_learn_corrections, daemon=True).start()
                    except Exception:
                        pass
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
                )

                self._reset_to_idle(session)

                if success:
                    try:
                        polishing_enabled = storage.get_setting("polishing_enabled", True)
                    except Exception:
                        polishing_enabled = True
                    if effective is not None and effective.requires_ai and polish_outcome["value"] != "ai_accepted":
                        # Spec §50: never silently pretend a transformation ran.
                        label = f" — {effective.label}" if effective.label else ""
                        detail = (
                            "Turn on text cleanup to run this command"
                            if polish_outcome["value"] == "disabled"
                            else _polish_outcome_label(polish_outcome["value"])
                        )
                        self._overlay_call("show_error", f"{detail}{label}")
                    elif effective is not None and effective.label:
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
                if use_streaming:
                    self._end_stream_session(discard=True, owner=session)
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
        try:
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

    def _on_mouse_release(self, x: int, y: int, drag_distance: float = 0.0, start_x: int = 0, start_y: int = 0) -> None:
        """Capture selected text and expose its actions on the persistent bar."""
        self._selection_generation = getattr(self, "_selection_generation", 0) + 1
        selection_generation = self._selection_generation
        audio_enabled = self._get_cached_setting("audio_flow_enabled", True)
        video_enabled = self._get_cached_setting("video_flow_enabled", True)
        if (not audio_enabled and not video_enabled) or self.is_recording:
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
                # If dictation recording started in the meantime, abort text capture
                if self.is_recording:
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
                if selection_generation != self._selection_generation:
                    return
                if selected and len(selected.strip()) > 1:
                    self.overlay.set_selected_text(selected, timeout_ms=6000)
                    audio_flow_widget.show_at(x, y, selected)
                else:
                    self.overlay.clear_selected_text()
                    audio_flow_widget.hide()
            except Exception:
                if selection_generation == self._selection_generation:
                    self.overlay.clear_selected_text()
                    audio_flow_widget.hide()

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
        """Capture selected text and read aloud via Audio Flow TTS Engine or Audio Summary."""
        self._audio_summary_generation = getattr(self, "_audio_summary_generation", 0) + 1
        gen_token = self._audio_summary_generation
        try:
            from voice_flow.audio_summary_player import close_summary_audio_player
            close_summary_audio_player(getattr(self, "_active_summary_player_token", None))
            self._active_summary_player_token = None
        except Exception:
            pass

        if tts_engine.is_speaking():
            self._stop_audio_flow_pipeline()
            # A bare hotkey remains a stop toggle. A selection action replaces
            # the old read immediately, so Summary never requires a second click.
            if not text_override:
                return
            self._audio_summary_generation += 1
            gen_token = self._audio_summary_generation

        if not storage.get_setting("audio_flow_enabled", True):
            audio_flow_widget.set_playing(False)
            self.overlay.show_error("Audio Flow is disabled")
            return

        explicit_selection = bool(text_override and str(text_override).strip())
        text_to_read = text_override
        if not text_to_read:
            target_hwnd = getattr(self, "target_hwnd", None)
            text_to_read = self.injector.get_selected_text(target_hwnd=target_hwnd)

        if not text_to_read or not text_to_read.strip():
            audio_flow_widget.set_playing(False)
            self.overlay.show_error("Select text to listen")
            return

        if not explicit_selection and self._is_voice_flow_dictation(text_to_read):
            log.info("[AUDIO FLOW] Refusing to read text that matches Voice Flow dictation transcript.")
            audio_flow_widget.set_playing(False)
            self.overlay.show_error("Voice Flow dictation skipped")
            return

        snippet = text_to_read[:35] + "…" if len(text_to_read) > 35 else text_to_read
        audio_flow_widget.hide()

        def _on_start():
            if self._audio_summary_generation == gen_token:
                audio_flow_widget.set_playing(True)
                audio_flow_widget.hide()
                self.overlay.show_reading(snippet)

        def _on_done():
            audio_flow_widget.set_playing(False)
            audio_flow_widget.hide()
            self.overlay.clear_selected_text()
            self.overlay.show_ready()

        def _on_error(err_msg: str):
            audio_flow_widget.set_playing(False)
            audio_flow_widget.hide()
            self.overlay.clear_selected_text()
            self.overlay.show_error(f"Audio Flow: {err_msg}"[:90])
            log.warning("Audio Flow synthesis error: %s", err_msg)

        speak_kwargs = {
            "on_start": _on_start,
            "on_done": _on_done,
            "on_error": _on_error,
        }
        if model_override is not None:
            speak_kwargs["model_override"] = model_override

        effective_mode = (mode or "read").lower().strip()
        if effective_mode == "default":
            # Existing installations may retain the retired "explain" setting.
            # Default behavior is now always verbatim Read, never an AI rewrite.
            effective_mode = str(storage.get_setting("exec_audio_flow_default_mode", "read") or "read").lower().strip()
        if effective_mode == "explain":
            effective_mode = "read"
        if effective_mode == "summary":
            import uuid
            depth = (summary_depth or "balanced").lower().strip()
            depth = {"quick": "short", "standard": "balanced", "detailed": "deep_dive"}.get(depth, depth)
            if depth not in {"short", "balanced", "deep_dive"}:
                depth = "balanced"
            history_id = f"ash_{uuid.uuid4().hex[:12]}"
            summary_title = storage._derive_audio_title(text_to_read)
            log.info("Audio Flow generating summary (%s depth) for text: '%s'", depth, snippet)
            try:
                storage.add_audio_summary_history(
                    text=text_to_read,
                    depth=depth,
                    audio_path="",
                    duration_sec=0.0,
                    item_id=history_id,
                    title=summary_title,
                    status="in_progress",
                    progress=0,
                )
            except Exception as hexc:
                log.debug("Failed to record audio summary history init: %s", hexc)

            if hasattr(self.overlay, "show_audio_summary_progress"):
                self.overlay.show_audio_summary_progress(0, f"Preparing {depth} summary")
            audio_flow_widget.hide()

            def _on_cancel():
                self._audio_summary_generation += 1
                try:
                    storage.update_audio_summary_history(
                        history_id,
                        status="cancelled",
                        progress=0,
                    )
                except Exception as cexc:
                    log.debug("Failed to update cancelled status: %s", cexc)
                if hasattr(self.overlay, "clear_audio_summary_status"):
                    self.overlay.clear_audio_summary_status()
                if hasattr(self.overlay, "show_ready"):
                    self.overlay.show_ready()
            if hasattr(self.overlay, "on_audio_summary_cancel"):
                self.overlay.on_audio_summary_cancel = _on_cancel

            def _summary_worker():
                def _progress(event):
                    if self._audio_summary_generation != gen_token:
                        return
                    progress_pct = 5
                    stage_msg = "Preparing summary"
                    if isinstance(event, dict):
                        state = str(event.get("state") or "")
                        elapsed = float(event.get("elapsed") or 0.0)
                        if state == "notebook_create":
                            progress_pct = 15
                            stage_msg = "Setting up notebook"
                        elif state == "source_add":
                            progress_pct = 30
                            stage_msg = "Adding source text"
                        elif state == "source_ready":
                            progress_pct = 40
                            stage_msg = "Source text ready"
                        elif state == "audio_start":
                            progress_pct = 50
                            stage_msg = "Starting audio generation"
                        elif state == "audio_poll":
                            progress_pct = min(88, 50 + int(elapsed * 0.8))
                            stage_msg = f"Synthesizing audio ({int(elapsed)}s)"
                        elif state == "audio_download":
                            progress_pct = 92
                            stage_msg = "Downloading summary audio"
                        else:
                            msg = event.get("message") or event.get("stage") or event.get("status")
                            if msg:
                                stage_msg = str(msg)[:44]
                            progress_pct = int(event.get("progress") or 25)
                    elif isinstance(event, (int, float)):
                        progress_pct = int(event)
                    elif isinstance(event, str):
                        stage_msg = event[:44]
                    if hasattr(self.overlay, "show_audio_summary_progress"):
                        self.overlay.show_audio_summary_progress(progress_pct, stage_msg)
                    try:
                        storage.update_audio_summary_history(history_id, progress=progress_pct)
                    except Exception:
                        pass

                try:
                    from voice_flow.audio_notebooklm import audio_notebooklm_service
                    result = audio_notebooklm_service.generate(
                        text_to_read,
                        depth=depth,
                        cancelled=lambda: self._audio_summary_generation != gen_token,
                        on_progress=_progress,
                    )
                    if self._audio_summary_generation != gen_token:
                        log.info("Audio summary generation token %d invalidated", gen_token)
                        if hasattr(self.overlay, "clear_audio_summary_status"):
                            self.overlay.clear_audio_summary_status()
                        return
                    audio_path = str((result or {}).get("audio_path") or "")
                    if not audio_path:
                        raise RuntimeError("NotebookLM did not return summary audio.")
                    from voice_flow.audio_summary_player import launch_summary_audio_player
                    if self._audio_summary_generation != gen_token:
                        if hasattr(self.overlay, "clear_audio_summary_status"):
                            self.overlay.clear_audio_summary_status()
                        return

                    # Compute or estimate duration
                    duration_sec = 0.0
                    try:
                        import wave
                        with wave.open(audio_path, "rb") as wf:
                            duration_sec = wf.getnframes() / float(wf.getframerate())
                    except Exception:
                        try:
                            sz = Path(audio_path).stat().st_size
                            duration_sec = max(10.0, sz / 16000.0)
                        except Exception:
                            duration_sec = 0.0

                    title_param = summary_title or (snippet[:40] if snippet else "Audio Summary")
                    self._active_summary_player_token = launch_summary_audio_player(
                        audio_path,
                        depth=depth,
                        title=title_param,
                        token=history_id,
                    )
                    try:
                        storage.update_audio_summary_history(
                            history_id,
                            status="ready",
                            progress=100,
                            audio_path=audio_path,
                            duration_sec=duration_sec,
                            title=title_param,
                        )
                        storage.record_audio_summary_to_history(
                            audio_id=history_id,
                            title=title_param,
                            text_snippet=text_to_read,
                            audio_path=audio_path,
                            duration_sec=duration_sec,
                            status="success",
                        )
                    except Exception as hexc:
                        log.debug("Failed to update audio summary history: %s", hexc)

                    if self._audio_summary_generation != gen_token:
                        from voice_flow.audio_summary_player import close_summary_audio_player
                        close_summary_audio_player(self._active_summary_player_token)
                        self._active_summary_player_token = None
                        if hasattr(self.overlay, "clear_audio_summary_status"):
                            self.overlay.clear_audio_summary_status()
                        return
                    if hasattr(self.overlay, "show_audio_summary_progress"):
                        self.overlay.show_audio_summary_progress(100, "Audio ready")
                    if hasattr(self.overlay, "clear_audio_summary_status"):
                        self.overlay.clear_audio_summary_status()
                    if hasattr(self.overlay, "show_ready"):
                        self.overlay.show_ready()
                except Exception as exc:
                    try:
                        storage.update_audio_summary_history(history_id, status="failed", error=str(exc))
                        storage.record_audio_summary_to_history(
                            audio_id=history_id,
                            title=summary_title,
                            text_snippet=text_to_read,
                            status="error",
                            error_message=str(exc),
                        )
                    except Exception:
                        pass
                    if self._audio_summary_generation != gen_token:
                        if hasattr(self.overlay, "clear_audio_summary_status"):
                            self.overlay.clear_audio_summary_status()
                        return
                    if hasattr(self.overlay, "clear_audio_summary_status"):
                        self.overlay.clear_audio_summary_status()
                    audio_flow_widget.set_playing(False)
                    audio_flow_widget.hide()
                    if hasattr(self.overlay, "clear_selected_text"):
                        self.overlay.clear_selected_text()
                    if hasattr(self.overlay, "show_error"):
                        self.overlay.show_error(f"NotebookLM summary: {exc}"[:90])
                    log.warning("Audio summary unexpected error: %s", exc)

            threading.Thread(target=_summary_worker, daemon=True).start()
        else:
            read_mode_setting = str(storage.get_setting("audio_flow_read_mode", "explanatory") or "explanatory").lower().strip()
            if read_mode_setting == "verbatim" or mode == "read_verbatim":
                log.info("Audio Flow reading selected text (Verbatim Read): '%s'", snippet)
                self.overlay.show_generating_audio()
                tts_engine.speak(text_to_read, **speak_kwargs)
            else:
                log.info("Audio Flow reading selected text (Human Explanatory Narration): '%s'", snippet)
                self.overlay.show_generating_audio()
                from voice_flow.audio_explainer import audio_explainer
                try:
                    narrated = audio_explainer.transform_for_human_reading(text_to_read)
                except Exception as err:
                    log.warning("Audio explainer transform failed (%s); falling back to direct TTS", err)
                    narrated = text_to_read

                tts_engine.speak(narrated, **speak_kwargs)

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
        self.overlay.clear_video_status()

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
                self.overlay.clear_video_status()
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
        """Stop active Audio Flow TTS playback and invalidate in-flight summary generation."""
        self._audio_summary_generation = getattr(self, "_audio_summary_generation", 0) + 1
        try:
            from voice_flow.audio_summary_player import close_summary_audio_player
            close_summary_audio_player(getattr(self, "_active_summary_player_token", None))
            self._active_summary_player_token = None
        except Exception:
            pass
        tts_engine.stop()
        audio_flow_widget.set_playing(False)
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
                except Exception:
                    _rec_setting = False
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
        log.info(" - Hold MOUSE SCROLL BUTTON (Middle Click) or CTRL + WIN to speak")
        log.info(" - Release to transcribe, clean up, and auto-paste!")
        log.info("==========================================================")

        # Run Tkinter Floating Overlay Bar on the MAIN THREAD
        try:
            self.overlay.run_loop()
        except Exception as e:
            log.error("Overlay main loop error: %s", e)
            while True:
                time.sleep(1.0)

    def stop(self) -> None:
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
    global _ENGINE_MUTEX_HANDLE
    # Single-instance enforcement: prevent multiple background engine processes from running concurrently
    if sys.platform == "win32" and "pytest" not in sys.modules:
        try:
            ERROR_ALREADY_EXISTS = 183
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            _ENGINE_MUTEX_HANDLE = kernel32.CreateMutexW(None, False, "Local\\VoiceFlowMainEngineMutex_v1")
            last_err = ctypes.get_last_error()
            if _ENGINE_MUTEX_HANDLE and last_err == ERROR_ALREADY_EXISTS:
                log.info("Another instance of Voice Flow main engine is already running. Exiting duplicate instance.")
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

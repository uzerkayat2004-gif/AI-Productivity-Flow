"""Main Application Orchestrator for Voice Flow.
Integrates Audio Recording, Whisper STT, Dictionary Biasing, Active Window Style Engine,
SQLite Storage, Multi-API Key Polishing, Clipboard Injection, and Desktop GUI.
"""

from __future__ import annotations
from dataclasses import dataclass
import re
import string

import ctypes
from enum import Enum
import io
import logging
import os
import subprocess
import sys
import threading
import time

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
from voice_flow.hotkeys import InputTriggerListener
from voice_flow.injector import ClipboardInjector, get_active_window_title
from voice_flow.overlay import FloatingOverlayBar
from voice_flow.polisher import polisher
from voice_flow.storage import storage
from voice_flow.style_engine import get_window_title_for_hwnd, style_engine
from voice_flow.text_processing import apply_spoken_punctuation, cleanup_text, smart_format, split_press_enter
from voice_flow.transcriber import Transcriber
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


from voice_flow.tts_engine import tts_engine
from voice_flow.audio_flow_widget import audio_flow_widget
from voice_flow.video_flow_widget import video_flow_widget


class VoiceFlowApp:
    """Core Coordinator for Voice Flow Dictation System."""

    def __init__(self) -> None:
        log.info("Starting Voice Flow System Engine...")
        self._state_lock = threading.RLock()
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

        # Load saved microphone preference if available
        saved_mic = storage.get_setting("selected_mic_device", None)
        if saved_mic is not None:
            config.selected_mic_device = saved_mic
            log.info("Loaded saved microphone preference: %s", saved_mic)

        self.transcriber = Transcriber()
        self.audio = AudioRecorder()
        self.overlay = FloatingOverlayBar()
        self.injector = ClipboardInjector()
        self.processing_lock = threading.Lock()
        self._audio_summary_generation = 0

        # Connect Input Trigger Listener with expanded actions
        self.hotkeys = InputTriggerListener(
            on_start=self._on_dictation_start,
            on_finish=self._on_dictation_finish,
            on_cancel=self._on_dictation_cancel,
            on_paste_last=self._paste_last_transcript,
            on_copy_last=self._copy_last_transcript,
            on_audio_flow=self._process_audio_flow_pipeline,
            on_mouse_release=self._on_mouse_release,
        )

        # Connect Overlay Action Buttons
        self.overlay.on_start_click = self._on_dictation_start
        self.overlay.on_finish_click = self._on_dictation_finish
        self.overlay.on_cancel_click = self._on_dictation_cancel
        self.overlay.on_listen_selected = lambda text: self._process_audio_flow_pipeline(text_override=text, mode="full")
        self.overlay.on_video_flow = lambda text: self._process_video_flow_pipeline("summary", text)
        self.overlay.on_video_ready = lambda video_id: video_flow_widget.open_player(video_id)
        self.overlay.on_video_cancel = self._cancel_video_from_screen

        # Connect Audio Flow Floating Widget
        audio_flow_widget.on_trigger = lambda text, mode="full", summary_depth=None: self._process_audio_flow_pipeline(text_override=text, mode=mode, summary_depth=summary_depth)
        audio_flow_widget.on_stop = lambda: self._stop_audio_flow_pipeline()
        audio_flow_widget.on_pause_toggle = lambda: self._toggle_audio_flow_pause()
        video_flow_widget.on_generate = self._queue_video_from_screen

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

    def _capture_session(self) -> DictationSession | None:
        """Read foreground app context once, before recording changes the UI."""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
        except Exception:
            hwnd = None
        if not hwnd:
            return None
        title = get_window_title_for_hwnd(hwnd) or get_active_window_title()
        if "voice flow" in title.lower() or "tk" in title.lower():
            return None
        resolved = style_engine.resolve_for_target(hwnd)
        press_enter_enabled = storage.get_setting("press_enter_enabled", False)
        cleanup_level = str(storage.get_setting("style_autocleanup", "cleanup_light"))
        return DictationSession(
            target_hwnd=hwnd,
            app_title=resolved.app_name,
            app_category=resolved.category,
            style_id=resolved.style_id,
            started_at=time.time(),
            cleanup_level=cleanup_level if cleanup_level.startswith("cleanup_") else "cleanup_light",
            press_enter_enabled=bool(press_enter_enabled),
        )

    def _on_dictation_start(self, mode: str = "ptt") -> bool:
        if not storage.get_setting("voice_flow_enabled", True):
            log.info("Voice Flow dictation is disabled via the feature toggle.")
            return False
        with self._state_lock:
            if self.state != DictationState.IDLE:
                log.info("Refusing start dictation while in state %s", self.state)
                return False
            session = self._capture_session()
            if session is None:
                self.state = DictationState.ERROR
                self.last_error = "Focus a text field first"
                self.hotkeys.set_recording_state(False)
                self.overlay.show_error(self.last_error)
                return False
            self.session = session
            self.state = DictationState.RECORDING

        hwnd = getattr(session, "target_hwnd", None) or (session.get("hwnd") if isinstance(session, dict) else None)
        app_title = getattr(session, "app_title", "General App") or (session.get("app_title") if isinstance(session, dict) else "General App")
        log.info("[RECORDING] Dictation triggered for target hwnd %s (%s)", hwnd, app_title)
        self.hotkeys.set_recording_state(True)

        watchdog = getattr(self, "_record_watchdog", None)
        if watchdog:
            watchdog.cancel()
            self._record_watchdog = None

        # The timer carries this immutable session so a later recording cannot
        # be finished by a stale twenty-minute watchdog.
        self._record_watchdog = threading.Timer(20 * 60, self._finish_if_current, args=(self.session,))
        self._record_watchdog.daemon = True
        self._record_watchdog.start()

        # Start audio capture stream
        started = self.audio.start()
        if not started:
            watchdog = getattr(self, "_record_watchdog", None)
            if watchdog:
                watchdog.cancel()
                self._record_watchdog = None
            with self._state_lock:
                self.state = DictationState.IDLE
                self.session = None
            self.hotkeys.set_recording_state(False)
            self.overlay.show_error("Microphone hardware failed to open")
            return False

        # Show Floating Waveform Bar with live volume callback
        self.overlay.show_recording(level_provider=lambda: self.audio.level)
        return True

    def _finish_if_current(self, session) -> None:
        with self._state_lock:
            if session is None or getattr(self, "session", None) is not session or self.state != DictationState.RECORDING:
                return
        self._on_dictation_finish()

    def _on_dictation_finish(self) -> bool:
        try:
            with self._state_lock:
                if self.state != DictationState.RECORDING:
                    return False
                session = getattr(self, "session", None)
                self.state = DictationState.PROCESSING
            watchdog = getattr(self, "_record_watchdog", None)
            if watchdog:
                watchdog.cancel()
                self._record_watchdog = None
            self.hotkeys.set_recording_state(False)

            audio_buffer = self.audio.stop()
            duration = len(audio_buffer) / config.sample_rate if audio_buffer.size > 0 else 0.0
            app_title = getattr(session, "app_title", "General App") or (session.get("app_title") if isinstance(session, dict) else "General App")
            category = getattr(session, "app_category", "smart_clean") or (session.get("category") if isinstance(session, dict) else "smart_clean")
            if duration < 0.3 or audio_buffer.size == 0:
                storage.add_dictation("", "", app_title, duration, category, status="transcription_failed", error_message="No usable audio was captured", insertion_status="not_attempted")
                with self._state_lock:
                    self.state = DictationState.IDLE
                    self.session = None
                self.overlay.show_error("No usable audio was captured")
                return False
            try:
                audio_path = self.archive.save(audio_buffer)
            except Exception as exc:
                storage.add_dictation("", "", app_title, duration, category, status="transcription_failed", error_message=f"Could not archive recording: {exc}", insertion_status="not_attempted")
                with self._state_lock:
                    self.state = DictationState.IDLE
                    self.session = None
                self.overlay.show_error(f"Could not archive recording: {exc}")
                return False
            record = storage.add_dictation("", "", app_title, duration, category,
                status="processing", audio_path=audio_path, insertion_status="not_attempted")
            self.overlay.show_processing()
            threading.Thread(
                target=self._process_dictation_pipeline,
                args=(session, audio_buffer, duration, record.id),
                daemon=True,
            ).start()
            return True

        except Exception as e:
            log.error("[FINISH ERROR] %s", e, exc_info=True)
            with self._state_lock:
                self.state = DictationState.IDLE
                self.session = None
            self.overlay.show_ready()
            return False

    def _on_dictation_cancel(self) -> bool:
        watchdog = getattr(self, "_record_watchdog", None)
        if watchdog:
            watchdog.cancel()
            self._record_watchdog = None

        with self._state_lock:
            if self.state != DictationState.RECORDING:
                return False
            self.state = DictationState.IDLE
            self.session = None

        log.info("[CANCELLED] Dictation cancelled by user.")
        self.hotkeys.set_recording_state(False)
        self.audio.stop()
        self.overlay.show_ready()
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
        if not self.last_successful_transcript:
            log.info("No last transcript available to paste.")
            return False
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
        except Exception:
            hwnd = None
        success = self.injector.paste_text(self.last_successful_transcript, hwnd)
        if not success:
            log.error("Could not paste last transcript; it remains on the clipboard.")
        return success

    def _history_update(self, record_id: int | None, **fields) -> None:
        updater = getattr(storage, "update_dictation", None)
        if record_id is not None and callable(updater):
            updater(record_id, **fields)

    def _finalize_text(self, raw_action_text: str, session: Any, resolved_style: Any = None) -> str:
        """Fidelity-first order: polish (AI pool or deterministic) -> style."""
        level = getattr(session, "cleanup_level", None) or (session.get("cleanup_level") if isinstance(session, dict) else "cleanup_light")
        style = getattr(session, "style_id", None) or (session.get("style_id") if isinstance(session, dict) else "smart_clean")
        context = getattr(session, "cursor_context", None) or (session.get("cursor_context") if isinstance(session, dict) else None)
        # The polisher owns the AI pass, deterministic cleanup, and the
        # dictionary vocabulary pass; smart formatting runs once afterwards.
        polished = polisher.polish(raw_action_text, style_instruction=resolved_style or style, cleanup_level=level)
        return smart_format(polished, style, context)

    def _process_dictation_pipeline(self, session: Any, audio_buffer: Any, duration: float, record_id: int | None = None) -> None:
        lock = getattr(self, "processing_lock", None)
        if lock is None:
            lock = threading.Lock()
        with lock:
            try:
                # App/style context belongs to the session, never current foreground.
                with self._state_lock:
                    if getattr(self, "session", None) is not session or self.state != DictationState.PROCESSING:
                        log.info("Ignoring stale dictation processing session.")
                        return

                target_h = getattr(session, "target_hwnd", None) or (session.get("hwnd") if isinstance(session, dict) else None)
                resolved_style = getattr(session, "style", None) or (session.get("style") if isinstance(session, dict) else None) or style_engine.resolve_for_target(target_h)
                log.info("Detected active app: '%s' (%s style - %s)", resolved_style.app_name, resolved_style.category, resolved_style.style_id)

                # Transcribe speech with dictionary prompt biasing; one bounded retry.
                raw_transcript = ""
                failure: Exception | None = None
                for attempt in range(2):
                    try:
                        raw_transcript = self.transcriber.transcribe(audio_buffer) or ""
                        if raw_transcript.strip():
                            break
                        failure = RuntimeError("No text was transcribed")
                    except Exception as exc:
                        failure = exc
                    if attempt == 0:
                        self._history_update(record_id, retry_count=1, status="processing", error_message="Automatic transcription retry")
                if not raw_transcript.strip():
                    reason = str(failure or "No text was transcribed")
                    self._history_update(record_id, status="transcription_failed", error_message=reason, insertion_status="not_attempted")
                    with self._state_lock:
                        self.state = DictationState.IDLE
                        self.session = None
                    self.overlay.show_error(reason[:90])
                    return

                # Check opt-in Press Enter action, then polish.
                press_enter_enabled = getattr(session, "press_enter_enabled", False) or (session.get("press_enter_enabled", False) if isinstance(session, dict) else False)
                split_res = split_press_enter(raw_transcript, bool(press_enter_enabled))
                text_to_polish = apply_spoken_punctuation(split_res.text)
                should_press_enter = split_res.press_enter

                # The polisher owns the deterministic vocabulary pass; smart
                # formatting runs once afterwards.
                polished_text = self._finalize_text(text_to_polish, session, resolved_style)
                polished_words = len(polished_text.split()) if polished_text else 0
                log.info("Pipeline complete (%d words -> %d words): '%s'", len(raw_transcript.split()), polished_words, polished_text)

                if not polished_text and not should_press_enter:
                    self._history_update(record_id, raw_text=raw_transcript, status="transcription_failed", error_message="Text cleanup returned no usable transcript", insertion_status="not_attempted")
                    with self._state_lock:
                        self.state = DictationState.IDLE
                        self.session = None
                    self.overlay.show_error("Text cleanup returned no usable transcript")
                    return

                with self._state_lock:
                    if getattr(self, "session", None) is not session or self.state != DictationState.PROCESSING:
                        log.info("Discarding stale transcript before persistence/paste.")
                        return

                if record_id is None:
                    # Compatibility for callers/tests that process supplied audio
                    # rather than a completed recorder session.
                    legacy = storage.add_dictation(raw_text=raw_transcript, polished_text=polished_text, app_name=resolved_style.app_name, duration_sec=duration, style_mode=resolved_style.category)
                    record_id = legacy.id
                self._history_update(record_id, raw_text=raw_transcript, polished_text=polished_text, status="success", error_message=None, insertion_status="not_attempted")

                # Inject polished text into the captured target window only.
                success = self.injector.paste_text(polished_text, target_h, press_enter=should_press_enter)

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
                    self._history_update(record_id, status="paste_failed", error_message="Could not paste transcript into the original target; it remains on the clipboard.", insertion_status="failed")

                with self._state_lock:
                    self.state = DictationState.IDLE
                    self.session = None

                if success:
                    self.overlay.show_done(polished_text)
                else:
                    self.overlay.show_error("Paste failed — text on clipboard")

            except Exception as e:
                log.error("Error processing dictation: %s", e, exc_info=True)
                self._history_update(record_id, status="transcription_failed", error_message=str(e), insertion_status="not_attempted")
                with self._state_lock:
                    self.state = DictationState.IDLE
                    self.session = None
                self.overlay.show_ready()

    def retry_history(self, record_id: int) -> tuple[bool, str]:
        """Retry archived audio without injecting into whichever app is focused now."""
        row = storage.get_history_record(record_id)
        if not row:
            return False, "History item not found"
        if float(row.get("duration_sec") or 0) < MIN_RETRY_SECONDS:
            return False, "Only recordings of at least 5 seconds can be retried"
        path = self.archive.resolve(row.get("audio_path"))
        if not path or not self.archive.available(row.get("audio_path")):
            return False, "Audio is no longer available"
        with self._state_lock:
            if self.state != DictationState.IDLE:
                return False, "Finish the current dictation before retrying"
            self.state = DictationState.PROCESSING
        storage.update_dictation(record_id, status="processing", error_message=None, retry_count=int(row.get("retry_count") or 0) + 1)
        self.overlay.show_processing()
        threading.Thread(target=self._retry_history_worker, args=(record_id, str(path)), daemon=True).start()
        return True, "Retry started"

    def _retry_history_worker(self, record_id: int, path: str) -> None:
        try:
            import wave, numpy as np
            with wave.open(path, "rb") as wf:
                audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32767.0
            raw = self.transcriber.transcribe(audio) or ""
            if not raw.strip():
                raise RuntimeError("No text was transcribed")
            # Retried history deliberately uses the stored style-independent
            # recovery path: it never focuses or pastes into the current app.
            text = smart_format(dictionary_engine.apply_dictionary_post_processing(cleanup_text(raw, "cleanup_light")), "smart_clean")
            storage.update_dictation(record_id, raw_text=raw, polished_text=text, status="success", error_message=None, insertion_status="not_attempted")
            self.last_successful_transcript = text
            self.overlay.show_done(text)
            with self._state_lock:
                self.state = DictationState.IDLE
        except Exception as exc:
            storage.update_dictation(record_id, status="transcription_failed", error_message=str(exc), insertion_status="not_attempted")
            with self._state_lock:
                self.state = DictationState.IDLE
            self.overlay.show_error(f"History retry failed: {exc}"[:90])

    def _on_mouse_release(self, x: int, y: int, drag_distance: float = 0.0, start_x: int = 0, start_y: int = 0) -> None:
        """Capture selected text and expose its actions on the persistent bar."""
        self._selection_generation = getattr(self, "_selection_generation", 0) + 1
        self._audio_summary_generation = getattr(self, "_audio_summary_generation", 0) + 1
        selection_generation = self._selection_generation
        audio_enabled = storage.get_setting("audio_flow_enabled", True)
        video_enabled = storage.get_setting("video_flow_enabled", True)
        if (not audio_enabled and not video_enabled) or self.is_recording:
            self.overlay.clear_selected_text()
            audio_flow_widget.hide()
            return

        if drag_distance < 2.0:
            self.overlay.clear_selected_text()
            audio_flow_widget.hide()
            return

        def _check():
            try:
                # Always use the CURRENT foreground window — never a stale target_hwnd
                # from a previous dictation session (which may point to the terminal).
                target_hwnd = ctypes.windll.user32.GetForegroundWindow()
                if not target_hwnd:
                    return

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
                    self.overlay.set_selected_text(selected)
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

        if tts_engine.is_speaking():
            tts_engine.stop()
            audio_flow_widget.set_playing(False)
            self.overlay.show_ready()
            return

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

        def _on_start():
            if self._audio_summary_generation == gen_token:
                audio_flow_widget.set_playing(True)
                self.overlay.show_reading(snippet)

        def _on_done():
            if self._audio_summary_generation == gen_token:
                audio_flow_widget.set_playing(False)
                self.overlay.clear_selected_text()
                self.overlay.show_ready()

        def _on_error(err_msg: str):
            if self._audio_summary_generation == gen_token:
                audio_flow_widget.set_playing(False)
                log.warning("Audio Flow synthesis error: %s", err_msg)
                self.overlay.show_error("Audio generation failed")

        speak_kwargs = {
            "on_start": _on_start,
            "on_done": _on_done,
            "on_error": _on_error,
        }
        if model_override is not None:
            speak_kwargs["model_override"] = model_override

        if mode == "summary":
            depth = (summary_depth or "standard").lower().strip()
            log.info("Audio Flow generating summary (%s depth) for text: '%s'", depth, snippet)
            self.overlay.show_summarizing(depth.capitalize())

            def _summary_worker():
                try:
                    from voice_flow.audio_summary import AudioSummaryError, audio_summary_service
                    summary_text = audio_summary_service.summarize(
                        text=text_to_read,
                        depth=depth,
                    )
                    if self._audio_summary_generation != gen_token:
                        log.info("Audio summary generation token %d invalidated", gen_token)
                        return
                    self.overlay.show_generating_audio()
                    tts_engine.speak(summary_text, **speak_kwargs)
                except PermissionError as perm_err:
                    if self._audio_summary_generation == gen_token:
                        audio_flow_widget.set_playing(False)
                        self.overlay.show_error("External AI permission required")
                        log.warning("Audio summary permission error: %s", perm_err)
                except AudioSummaryError as sum_err:
                    if self._audio_summary_generation == gen_token:
                        audio_flow_widget.set_playing(False)
                        self.overlay.show_error("Select Summary LLM in settings")
                        log.warning("Audio summary service error: %s", sum_err)
                except Exception as exc:
                    if self._audio_summary_generation == gen_token:
                        audio_flow_widget.set_playing(False)
                        self.overlay.show_error("Summary failed")
                        log.warning("Audio summary unexpected error: %s", exc)

            threading.Thread(target=_summary_worker, daemon=True).start()
        else:
            log.info("Audio Flow reading selected text (Full Audio): '%s'", snippet)
            self.overlay.show_generating_audio()
            tts_engine.speak(text_to_read, **speak_kwargs)

    def _process_video_flow_pipeline(self, mode: str, text_override: str | None = None) -> None:
        """Open the primary system-wide composer for selected text."""
        if not storage.get_setting("video_flow_enabled", True):
            self.overlay.show_error("Video Flow is disabled")
            return
        text = (text_override or "").strip()
        if not text:
            text = self._capture_selected_text_for_video()
        if not text:
            self.overlay.show_error("Select text to make a video")
            return
        if mode == "full":
            video_flow_widget.show_composer(text, "full")
        else:
            video_flow_widget.show_composer(text, "summary")

    def _capture_selected_text_for_video(self) -> str:
        """Copy foreground selection without injecting text or retaining clipboard changes.

        The previous clipboard content is restored only when it is plain text so
        image/file clipboards are never destroyed by a stray restore.
        """
        try:
            import pyperclip
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return ""
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
                user32.keybd_event(0x11, 0, 0, 0); user32.keybd_event(0x43, 0, 0, 0)
                user32.keybd_event(0x43, 0, 0x0002, 0); user32.keybd_event(0x11, 0, 0x0002, 0)
                deadline = time.monotonic() + 0.5
                while time.monotonic() < deadline:
                    copied = pyperclip.paste()
                    if copied != marker:
                        return str(copied or "").strip()
                    time.sleep(0.02)
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

        job = get_video_flow_service().queue(
            source_text=str(payload.get("source_text", "")),
            mode=str(payload.get("mode", "summary")),
            title=str(payload.get("title", "")),
            model_ref=str(payload.get("model_ref", "") or "") or None,
            theme=payload.get("theme", "auto"),
            visual_direction=str(payload.get("visual_direction", "")),
            allow_external_ai=bool(payload.get("allow_external_ai", False)),
        )
        video_id = job.job_id
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
        self.overlay.clear_video_status()

    def _monitor_video_flow_job(self, video_id: str) -> None:
        """Keep the bar sidecar synchronized until the player is ready."""
        from voice_flow.video_flow_service import get_video_flow_service

        service = get_video_flow_service()
        while video_id:
            job = service.get(video_id)
            if job is None:
                self.overlay.show_video_failed(video_id, "Video job disappeared")
                return
            state = str(job.state)
            if state == "complete" or job.progress >= 100.0:
                self.overlay.show_video_ready(video_id)
                return
            if state == "failed":
                reason = str(job.meta.get("error_message") or job.message or job.meta.get("error_code") or "Video generation failed")
                self.overlay.show_video_failed(video_id, reason)
                return
            if state == "cancelled":
                self.overlay.clear_video_status()
                return
            self.overlay.show_video_progress(
                video_id,
                int(job.progress),
                str(job.message or state or "Creating video"),
            )
            time.sleep(1.1)
    def _stop_audio_flow_pipeline(self) -> None:
        """Stop active Audio Flow TTS playback and invalidate in-flight summary generation."""
        self._audio_summary_generation = getattr(self, "_audio_summary_generation", 0) + 1
        tts_engine.stop()
        audio_flow_widget.set_playing(False)
        self.overlay.show_ready()
    def _toggle_audio_flow_pause(self) -> None:
        """Suspend or reinstate Audio Flow TTS playback from the widget control bar."""
        if tts_engine.is_speaking():
            if tts_engine.is_paused():
                tts_engine.resume()
            else:
                tts_engine.pause()
        audio_flow_widget.set_paused(tts_engine.is_paused())
    def _watch_gui_state_file(self) -> None:
        """Monitor ~/.voice_flow/recording_state.json for recording toggle events from GUI."""
        import json
        import os
        from voice_flow.paths import data_dir
        state_file = str(data_dir() / "recording_state.json")

        try:
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            with open(state_file, "w") as f:
                json.dump({"recording": False}, f)
        except Exception:
            pass

        last_mtime = os.path.getmtime(state_file) if os.path.exists(state_file) else 0

        while True:
            time.sleep(0.2)
            try:
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
        self.hotkeys.start()

        # Start GUI recording state watcher
        threading.Thread(target=self._watch_gui_state_file, daemon=True).start()

        # Start local REST API server
        try:
            from voice_flow.gui.api_server import start_api_server, register_runtime_controller
            register_runtime_controller(self)
            threading.Thread(target=start_api_server, daemon=True).start()
        except Exception as e:
            log.warning("Could not start API server: %s", e)

        log.info("==========================================================")
        log.info(" VOICE FLOW READY! ")
        log.info(" - System-wide floating bar active on your screen")
        log.info(" - Hold MOUSE SCROLL BUTTON (Middle Click) or CTRL + WIN to speak")
        log.info(" - Release to transcribe, clean up, and auto-paste!")
        log.info("==========================================================")

        # Launch Desktop UI Window silently in a dedicated process to prevent COM thread deadlocks with Tkinter
        try:
            python_exe = sys.executable
            # Prefer pythonw.exe if available so no console window is ever shown
            pyw_candidate = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
            if os.path.exists(pyw_candidate):
                python_exe = pyw_candidate
            src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

            subprocess.Popen(
                [python_exe, "-m", "voice_flow.gui.desktop_launcher"],
                cwd=src_dir,
                creationflags=creation_flags,
            )
        except Exception as e:
            log.warning("Could not launch Desktop GUI process: %s", e)

        # Run Tkinter Floating Overlay Bar on the MAIN THREAD
        try:
            self.overlay.run_loop()
        except Exception as e:
            log.error("Overlay main loop error: %s", e)
            while True:
                time.sleep(1.0)

    def stop(self) -> None:
        self.hotkeys.stop()
        self.audio.stop()


def main() -> None:
    app: VoiceFlowApp | None = None
    try:
        from voice_flow.gui.api_server import PORT
        from voice_flow.runtime_guard import prepare_runtime_port

        runtime_port = prepare_runtime_port(port=PORT)
        if runtime_port.status == "compatible":
            python_exe = sys.executable
            pyw_candidate = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
            if os.path.exists(pyw_candidate):
                python_exe = pyw_candidate
            subprocess.Popen(
                [python_exe, "-m", "voice_flow.gui.desktop_launcher"],
                cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0,
            )
            return
        if runtime_port.status == "occupied":
            raise RuntimeError("Port 8991 is owned by a non-Voice-Flow process and cannot be replaced safely.")
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

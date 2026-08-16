"""Main Application Orchestrator for Voice Flow.
Integrates Audio Recording, Whisper STT, Dictionary Biasing, Active Window Style Engine,
SQLite Storage, Multi-API Key Polishing, Clipboard Injection, and Desktop GUI.
"""

from __future__ import annotations
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
from voice_flow.style_engine import style_engine
from voice_flow.text_processing import apply_spoken_punctuation, split_press_enter
from voice_flow.transcriber import Transcriber

# Hide console window on Windows immediately so the application runs silently in the background
if sys.platform == "win32":
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            if "--show-console" not in sys.argv:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # 0 = SW_HIDE
    except Exception:
        pass

# Fix UTF-8 encoding on Windows console (only if stdout has a buffer)
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="backslashreplace")
    except AttributeError:
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


from voice_flow.tts_engine import tts_engine
from voice_flow.video_flow import video_flow_service
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

    def _on_dictation_start(self, mode: str = "ptt") -> bool:
        if not storage.get_setting("voice_flow_enabled", True):
            log.info("Voice Flow dictation is disabled via the feature toggle.")
            return False
        with self._state_lock:
            if self.state != DictationState.IDLE:
                log.info("Refusing start dictation while in state %s", self.state)
                return False
            self.state = DictationState.RECORDING

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd:
            title = get_active_window_title()
            if "voice flow" not in title.lower() and "tk" not in title.lower():
                self.target_hwnd = hwnd

        log.info("[RECORDING] Dictation triggered for target hwnd %s!", getattr(self, "target_hwnd", None))
        self.hotkeys.set_recording_state(True)

        if self._record_watchdog:
            self._record_watchdog.cancel()
            self._record_watchdog = None

        self._record_watchdog = threading.Timer(20 * 60, self._on_dictation_finish)
        self._record_watchdog.daemon = True
        self._record_watchdog.start()

        # Start audio capture stream
        started = self.audio.start()
        if not started:
            if self._record_watchdog:
                self._record_watchdog.cancel()
                self._record_watchdog = None
            with self._state_lock:
                self.state = DictationState.IDLE
            self.hotkeys.set_recording_state(False)
            self.overlay.show_error("Microphone hardware failed to open")
            return False

        # Show Floating Waveform Bar with live volume callback
        self.overlay.show_recording(level_provider=lambda: self.audio.level)
        return True

    def _on_dictation_finish(self) -> bool:
        with self._state_lock:
            if self.state != DictationState.RECORDING:
                return False
            self.state = DictationState.PROCESSING

        if self._record_watchdog:
            self._record_watchdog.cancel()
            self._record_watchdog = None

        try:
            self.hotkeys.set_recording_state(False)
            log.info("[PROCESSING] Dictation finished, stopping recording stream...")

            # Stop audio recording stream & fetch float32 numpy audio buffer
            audio_buffer = self.audio.stop()
            duration = len(audio_buffer) / config.sample_rate if audio_buffer.size > 0 else 0.0
            log.info("[AUDIO] Got %d samples (%.2fs), peak=%.4f", audio_buffer.size, duration, float(max(abs(audio_buffer))) if audio_buffer.size > 0 else 0.0)

            if duration < 0.3 or audio_buffer.size == 0:
                log.info("Recording too short (%.2fs), ignoring.", duration)
                with self._state_lock:
                    self.state = DictationState.IDLE
                self.overlay.show_ready()
                return True

            # Show Processing state on floating bar
            self.overlay.show_processing()

            # Dispatch speech transcription & AI polish asynchronously
            threading.Thread(
                target=self._process_dictation_pipeline,
                args=(audio_buffer, duration),
                daemon=True,
            ).start()
            return True

        except Exception as e:
            log.error("[FINISH ERROR] %s", e, exc_info=True)
            with self._state_lock:
                self.state = DictationState.IDLE
            self.overlay.show_ready()
            return False

    def _on_dictation_cancel(self) -> bool:
        if self._record_watchdog:
            self._record_watchdog.cancel()
            self._record_watchdog = None

        with self._state_lock:
            if self.state != DictationState.RECORDING:
                return False
            self.state = DictationState.IDLE

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

    def _process_dictation_pipeline(self, audio_buffer, duration: float) -> None:
        with self.processing_lock:
            try:
                target_h = getattr(self, "target_hwnd", None)

                # Step 1: Detect active foreground app window & resolve style
                resolved_style = style_engine.resolve_for_target(target_h)
                log.info("Detected active app: '%s' (%s style - %s)", resolved_style.app_name, resolved_style.category, resolved_style.style_id)

                # Step 2: Transcribe speech with dictionary prompt biasing
                t0 = time.time()
                raw_transcript = self.transcriber.transcribe(audio_buffer)
                t_stt = time.time() - t0
                raw_words = len(raw_transcript.split()) if raw_transcript else 0
                log.info("STT completed in %.3fs (%d words): '%s'", t_stt, raw_words, raw_transcript)

                if not raw_transcript.strip():
                    log.info("No text transcribed.")
                    with self._state_lock:
                        self.state = DictationState.IDLE
                    self.overlay.show_ready()
                    return

                # Step 3: Check opt-in Press Enter action
                press_enter_enabled = storage.get_setting("press_enter_enabled", False)
                split_res = split_press_enter(raw_transcript, press_enter_enabled)
                text_to_polish = apply_spoken_punctuation(split_res.text)
                should_press_enter = split_res.press_enter

                # Step 4: The polisher owns the single deterministic vocabulary pass.
                polished_text = polisher.polish(text_to_polish, resolved_style)
                polished_words = len(polished_text.split()) if polished_text else 0
                log.info("Pipeline complete (%d words -> %d words): '%s'", raw_words, polished_words, polished_text)

                # Step 6: Inject polished text into target application active input field
                success = self.injector.paste_text(polished_text, target_h, press_enter=should_press_enter)

                # Accepted transcript state is updated only after a successful paste.
                # An action-only Enter must not erase the prior copy-last transcript.
                if success and polished_text.strip():
                    self.last_successful_transcript = polished_text
                    self.recent_dictations.add(polished_text.strip())
                    if raw_transcript and raw_transcript.strip():
                        self.recent_dictations.add(raw_transcript.strip())
                    if len(self.recent_dictations) > 100:
                        self.recent_dictations = set(list(self.recent_dictations)[-50:])

                # Step 7: Record Insights ONLY after successful paste into active window input field!
                if success:
                    try:
                        record = storage.add_dictation(
                            raw_text=raw_transcript,
                            polished_text=polished_text,
                            app_name=resolved_style.app_name,
                            duration_sec=duration,
                            style_mode=resolved_style.style_id,
                        )
                        log.info("Saved dictation record #%d into SQLite history database", record.id)
                    except Exception as db_err:
                        log.warning("[STORAGE] Could not persist dictation history: %s", db_err)
                else:
                    log.warning("[INSIGHTS SKIPPED] Text paste failed; app not logged in Insights.")

                with self._state_lock:
                    self.state = DictationState.IDLE

                if success:
                    self.overlay.show_done(polished_text)
                else:
                    self.overlay.show_error("Paste failed — text on clipboard")

            except Exception as e:
                log.error("Error processing dictation: %s", e, exc_info=True)
                with self._state_lock:
                    self.state = DictationState.IDLE
                self.overlay.show_ready()

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
        if mode == "full":
            video_flow_widget.show_composer(text, "full")
        else:
            video_flow_widget.show_composer(text, "summary")

    def _queue_video_from_screen(self, payload: dict) -> dict:
        """Queue a system-wide composer request and mirror progress on the bar."""
        video = video_flow_service.queue(
            source_text=str(payload.get("source_text", "")),
            mode=str(payload.get("mode", "summary")),
            title=str(payload.get("title", "")),
            source_name=str(payload.get("source_name", "")),
            model_ref=str(payload.get("model_ref", "")),
            theme=str(payload.get("theme", "auto")),
            visual_direction=str(payload.get("visual_direction", "")),
            allow_external_ai=bool(payload.get("allow_external_ai", False)),
        )
        video_id = str(video.get("id", ""))
        self.overlay.show_video_progress(video_id, 0, "Queued")
        threading.Thread(
            target=self._monitor_video_flow_job,
            args=(video_id,),
            daemon=True,
            name=f"video-flow-monitor-{video_id[:8]}",
        ).start()
        log.info("[VIDEO FLOW] Queued screen video %s.", video_id)
        return video

    def _cancel_video_from_screen(self, video_id: str) -> None:
        """Stop a Video Flow job without interrupting Voice or Audio Flow."""
        if video_flow_service.cancel(video_id):
            log.info("[VIDEO FLOW] Cancelled screen video %s.", video_id)
        self.overlay.clear_video_status()

    def _monitor_video_flow_job(self, video_id: str) -> None:
        """Keep the bar sidecar synchronized until the player is ready."""
        while video_id:
            video = video_flow_service.store.get_video(video_id)
            if not video:
                self.overlay.show_video_failed(video_id, "Video job disappeared")
                return
            status = str(video.get("status", ""))
            if status == "completed":
                self.overlay.show_video_ready(video_id)
                return
            if status == "failed":
                self.overlay.show_video_failed(video_id, str(video.get("error") or "Video generation failed"))
                return
            if status == "cancelled":
                self.overlay.clear_video_status()
                return
            self.overlay.show_video_progress(
                video_id,
                int(video.get("progress", 0) or 0),
                str(video.get("stage") or status or "Creating video"),
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
        state_file = os.path.join(os.path.expanduser("~"), ".voice_flow", "recording_state.json")

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

"""Main Application Orchestrator for Voice Flow.
Integrates Audio Recording, Whisper STT, Dictionary Biasing, Active Window Style Engine,
SQLite Storage, Multi-API Key Polishing, Clipboard Injection, and Desktop GUI.
"""

from __future__ import annotations

import ctypes
import io
import logging
import os
import subprocess
import sys
import threading
import time

from voice_flow.audio import AudioRecorder
from voice_flow.config import config
from voice_flow.dictionary import dictionary_engine
from voice_flow.hotkeys import InputTriggerListener
from voice_flow.injector import ClipboardInjector, get_active_window_title
from voice_flow.overlay import FloatingOverlayBar
from voice_flow.polisher import polisher
from voice_flow.storage import storage
from voice_flow.style_engine import style_engine
from voice_flow.transcriber import Transcriber

# Fix UTF-8 encoding on Windows console (only if stdout has a buffer)
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="backslashreplace")
    except AttributeError:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger("voice_flow.main")


class VoiceFlowApp:
    """Core Coordinator for Voice Flow Dictation System."""

    def __init__(self) -> None:
        log.info("Starting Voice Flow System Engine...")
        # Load saved microphone preference if available
        saved_mic = storage.get_setting("selected_mic_device", None)
        if saved_mic is not None:
            config.selected_mic_device = saved_mic
            log.info("Loaded saved microphone preference: %s", saved_mic)

        self.transcriber = Transcriber()
        self.audio = AudioRecorder()
        self.overlay = FloatingOverlayBar()
        self.injector = ClipboardInjector()
        self.is_recording = False
        self.processing_lock = threading.Lock()

        # Connect Input Trigger Listener
        self.hotkeys = InputTriggerListener(
            on_start=self._on_dictation_start,
            on_finish=self._on_dictation_finish,
            on_cancel=self._on_dictation_cancel,
        )

        # Connect Overlay Action Buttons
        self.overlay.on_start_click = self._on_dictation_start
        self.overlay.on_finish_click = self._on_dictation_finish
        self.overlay.on_cancel_click = self._on_dictation_cancel

    def _on_dictation_start(self) -> None:
        if self.is_recording:
            return

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd:
            title = get_active_window_title()
            if "voice flow" not in title.lower() and "tk" not in title.lower():
                self.target_hwnd = hwnd

        log.info("[RECORDING] Dictation triggered for target hwnd %s!", getattr(self, "target_hwnd", None))
        self.is_recording = True
        self.hotkeys.set_recording_state(True)

        # Clear audio buffer & start audio capture stream
        self.audio.start()

        # Show Floating Waveform Bar with live volume callback
        self.overlay.show_recording(level_provider=lambda: self.audio.level)

    def _on_dictation_finish(self) -> None:
        try:
            if not self.is_recording:
                return

            self.is_recording = False
            self.hotkeys.set_recording_state(False)
            log.info("[PROCESSING] Dictation finished, stopping recording stream...")

            # Stop audio recording stream & fetch float32 numpy audio buffer
            audio_buffer = self.audio.stop()
            duration = len(audio_buffer) / config.sample_rate if audio_buffer.size > 0 else 0.0
            log.info("[AUDIO] Got %d samples (%.2fs), peak=%.4f", audio_buffer.size, duration, float(max(abs(audio_buffer))) if audio_buffer.size > 0 else 0.0)

            if duration < 0.3 or audio_buffer.size == 0:
                log.info("Recording too short (%.2fs), ignoring.", duration)
                self.overlay.show_ready()
                return

            # Show Processing state on floating bar
            self.overlay.show_processing()

            # Dispatch speech transcription & AI polish asynchronously
            threading.Thread(
                target=self._process_dictation_pipeline,
                args=(audio_buffer, duration),
                daemon=True,
            ).start()
        except Exception as e:
            log.error("[FINISH ERROR] %s", e, exc_info=True)
            self.overlay.show_ready()

    def _on_dictation_cancel(self) -> None:
        if not self.is_recording:
            self.overlay.show_ready()
            return

        log.info("[CANCELLED] Dictation cancelled by user.")
        self.is_recording = False
        self.hotkeys.set_recording_state(False)
        self.audio.stop()
        self.overlay.show_ready()

    def _process_dictation_pipeline(self, audio_buffer, duration: float) -> None:
        with self.processing_lock:
            try:
                # Step 1: Detect active foreground app window & style category
                app_title, app_category, style_preset = style_engine.get_style_for_current_app()
                log.info("Detected active app: '%s' (%s style)", app_title, app_category)

                # Step 2: Transcribe speech with dictionary prompt biasing
                t0 = time.time()
                raw_transcript = self.transcriber.transcribe(audio_buffer)
                t_stt = time.time() - t0
                log.info("STT completed in %.3fs: '%s'", t_stt, raw_transcript)

                if not raw_transcript.strip():
                    log.info("No text transcribed.")
                    self.overlay.show_ready()
                    return

                # Step 3: Polish text with AI engine & custom dictionary fuzzy matching
                style_instruction = style_preset.get("prompt_instruction", str(style_preset)) if isinstance(style_preset, dict) else str(style_preset)
                polished_text = polisher.polish(raw_transcript, style_instruction)
                polished_text = dictionary_engine.apply_dictionary_post_processing(polished_text)

                # Step 4: Save record to SQLite database for Home History & Insights
                record = storage.add_dictation(
                    raw_text=raw_transcript,
                    polished_text=polished_text,
                    app_name=app_title,
                    duration_sec=duration,
                    style_mode=app_category,
                )
                log.info("Saved dictation record #%d into SQLite history database", record.id)

                # Step 5: Show Done state on floating bar
                self.overlay.show_done(polished_text)

                # Step 6: Inject polished text into target application active input field
                target_h = getattr(self, "target_hwnd", None)
                self.injector.paste_text(polished_text, target_h)

            except Exception as e:
                log.error("Error processing dictation: %s", e, exc_info=True)
                self.overlay.show_ready()

    def _watch_gui_state_file(self) -> None:
        """Monitor ~/.voice_flow/recording_state.json for recording toggle events from GUI."""
        import json
        import os
        state_file = os.path.join(os.path.expanduser("~"), ".voice_flow", "recording_state.json")

        # Ensure state file exists and is reset to false on startup
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
            from voice_flow.gui.api_server import start_api_server
            threading.Thread(target=start_api_server, daemon=True).start()
        except Exception as e:
            log.warning("Could not start API server: %s", e)

        log.info("==========================================================")
        log.info(" VOICE FLOW READY! ")
        log.info(" - System-wide floating bar active on your screen")
        log.info(" - Hold MOUSE SCROLL BUTTON (Middle Click) or CTRL + WIN to speak")
        log.info(" - Release to transcribe, clean up, and auto-paste!")
        log.info("==========================================================")

        # Launch Desktop UI Window in a dedicated process to prevent COM thread deadlocks with Tkinter
        try:
            python_exe = sys.executable
            if "pythonw.exe" in python_exe.lower():
                alt_exe = os.path.join(os.path.dirname(python_exe), "python.exe")
                if os.path.exists(alt_exe):
                    python_exe = alt_exe
            src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            import subprocess
            subprocess.Popen(
                [python_exe, "-m", "voice_flow.gui.desktop_launcher"],
                cwd=src_dir,
            )
        except Exception as e:
            log.warning("Could not launch Desktop GUI process: %s", e)

        # Run Tkinter Floating Overlay Bar on the MAIN THREAD
        try:
            self.overlay.show_ready()
            self.overlay.run_loop()
        except Exception as e:
            log.error("Overlay main loop error: %s", e)
            import time
            while True:
                time.sleep(1.0)

    def stop(self) -> None:
        self.hotkeys.stop()
        self.audio.stop()


def main() -> None:
    app = VoiceFlowApp()
    try:
        app.run()
    except KeyboardInterrupt:
        log.info("Shutting down Voice Flow.")
        app.stop()


if __name__ == "__main__":
    main()

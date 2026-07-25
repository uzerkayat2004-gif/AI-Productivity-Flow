"""Main Application Orchestrator for Voice Flow.
Integrates Audio Recording, Whisper STT, Dictionary Biasing, Active Window Style Engine,
SQLite Storage, Multi-API Key Polishing, Clipboard Injection, and Desktop GUI.
"""

from __future__ import annotations

import io
import logging
import sys
import threading
import time

from voice_flow.audio import AudioRecorder
from voice_flow.config import config
from voice_flow.dictionary import dictionary_engine
from voice_flow.hotkeys import InputTriggerListener
from voice_flow.injector import ClipboardInjector
from voice_flow.overlay import FloatingOverlayBar
from voice_flow.polisher import polisher
from voice_flow.storage import storage
from voice_flow.style_engine import style_engine
from voice_flow.transcriber import Transcriber

# Fix UTF-8 encoding on Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="backslashreplace")

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
        self.overlay.on_finish_click = self._on_dictation_finish
        self.overlay.on_cancel_click = self._on_dictation_cancel

    def _on_dictation_start(self) -> None:
        if self.is_recording:
            return

        log.info("[RECORDING] Dictation triggered!")
        self.is_recording = True

        # Clear audio buffer & start audio capture stream
        self.audio.start()

        # Show Floating Waveform Bar with live volume callback
        self.overlay.show_recording(level_provider=self.audio.get_rms_level)

    def _on_dictation_finish(self) -> None:
        if not self.is_recording:
            return

        log.info("[PROCESSING] Dictation finished, stopping recording stream...")
        self.is_recording = False

        # Stop audio recording stream & fetch float32 numpy audio buffer
        audio_buffer, duration = self.audio.stop()

        if duration < 0.3 or audio_buffer.size == 0:
            log.info("Recording too short (%.2fs), ignoring.", duration)
            self.overlay.hide()
            return

        # Show Processing state on floating bar
        self.overlay.show_processing()

        # Dispatch speech transcription & AI polish asynchronously
        threading.Thread(
            target=self._process_dictation_pipeline,
            args=(audio_buffer, duration),
            daemon=True,
        ).start()

    def _on_dictation_cancel(self) -> None:
        if not self.is_recording:
            self.overlay.hide()
            return

        log.info("[CANCELLED] Dictation cancelled by user.")
        self.is_recording = False
        self.audio.stop()
        self.overlay.hide()

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
                    self.overlay.hide()
                    return

                # Step 3: Polish text with AI engine & custom dictionary fuzzy matching
                polished_text = polisher.polish(raw_transcript, style_preset["prompt_instruction"])

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
                self.injector.paste_text(polished_text)

            except Exception as e:
                log.error("Error processing dictation: %s", e, exc_info=True)
                self.overlay.hide()

    def run(self) -> None:
        log.info("Starting input trigger hooks...")
        self.hotkeys.start()

        log.info("==========================================================")
        log.info(" VOICE FLOW READY! ")
        log.info(" - Hold MOUSE SCROLL BUTTON (Middle Click) or CTRL + WIN to speak")
        log.info(" - Release to transcribe, clean up, and auto-paste!")
        log.info("==========================================================")

        # Start Tkinter main event loop for floating overlay bar
        self.overlay.run_loop()

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

"""Main application entry point for Voice Flow."""

from __future__ import annotations

import logging
import sys
import threading
import tkinter as tk

from voice_flow.audio import AudioRecorder
from voice_flow.config import config
from voice_flow.hotkeys import InputTriggerListener
from voice_flow.injector import inject_text
from voice_flow.overlay import FloatingOverlayBar
from voice_flow.transcriber import Transcriber

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("voice_flow")


class VoiceFlowApp:
    """Core application coordinator."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()  # hide main root window

        self.audio = AudioRecorder()
        self.transcriber = Transcriber()

        self.overlay = FloatingOverlayBar(
            root=self.root,
            on_cancel=self.cancel_recording,
            on_finish=self.finish_recording,
            get_audio_level=lambda: self.audio.level,
        )

        self.listener = InputTriggerListener(
            on_start=self.start_recording,
            on_finish=self.finish_recording,
            on_cancel=self.cancel_recording,
        )

    def run(self) -> None:
        """Start the Voice Flow application."""
        log.info("Starting Voice Flow...")
        log.info("Trigger methods enabled:")
        log.info("  1. Press & hold Mouse Scroll Button (Middle Click)")
        log.info("  2. Press Win + Ctrl keyboard combination")

        # Start input listeners
        self.listener.start()

        # Pre-warm transcriber model in background thread
        threading.Thread(target=self._preload_model, daemon=True).start()

        # Run tkinter event loop
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.shutdown()

    def _preload_model(self) -> None:
        """Pre-load Whisper model so first transcription is fast."""
        try:
            self.transcriber.load_model()
        except Exception:
            log.exception("Failed to preload Whisper model.")

    # -- State Transitions (called from input listeners / overlay buttons) --

    def start_recording(self) -> None:
        """Start recording audio and show overlay bar."""
        # Ensure UI updates happen on tkinter thread
        self.root.after(0, self._do_start_recording)

    def _do_start_recording(self) -> None:
        if self.audio.is_recording:
            return

        log.info("Recording started.")
        self.audio.start()
        self.listener.set_recording_state(True)
        self.overlay.show_recording()

    def finish_recording(self) -> None:
        """Stop recording, transcribe, and inject text."""
        self.root.after(0, self._do_finish_recording)

    def _do_finish_recording(self) -> None:
        if not self.audio.is_recording:
            return

        log.info("Recording finished. Processing...")
        self.listener.set_recording_state(False)
        audio_data = self.audio.stop()
        self.overlay.show_processing()

        # Transcribe and inject in background worker thread
        threading.Thread(
            target=self._process_and_inject, args=(audio_data,), daemon=True
        ).start()

    def cancel_recording(self) -> None:
        """Cancel recording and discard audio."""
        self.root.after(0, self._do_cancel_recording)

    def _do_cancel_recording(self) -> None:
        if self.audio.is_recording:
            log.info("Recording cancelled.")
            self.audio.cancel()
            self.listener.set_recording_state(False)

        self.overlay.hide()

    def _process_and_inject(self, audio_data: object) -> None:
        """Worker thread function: transcribes audio and injects text."""
        try:
            text = self.transcriber.transcribe(audio_data)
            if text:
                inject_text(text)
                self.root.after(0, self.overlay.show_done)
            else:
                log.info("No speech detected.")
                self.root.after(0, self.overlay.hide)
        except Exception:
            log.exception("Error during transcription / injection.")
            self.root.after(0, self.overlay.hide)

    def shutdown(self) -> None:
        """Clean shutdown."""
        log.info("Shutting down Voice Flow...")
        self.listener.stop()
        if self.audio.is_recording:
            self.audio.cancel()
        self.root.quit()


def main() -> None:
    app = VoiceFlowApp()
    app.run()


if __name__ == "__main__":
    main()

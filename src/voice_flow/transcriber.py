"""Ultra-fast local transcription module using faster-whisper (tiny.en model).

Pre-loads model at startup so transcription takes under 0.4 seconds!
"""

from __future__ import annotations

import logging

from faster_whisper import WhisperModel
import numpy as np
from numpy.typing import NDArray

from voice_flow.config import config

log = logging.getLogger(__name__)


class Transcriber:
    """Pre-loaded faster-whisper model for near-instant local transcription."""

    def __init__(self) -> None:
        log.info("⚡ Loading local AI speech model ('tiny.en')...")
        # Pre-load tiny.en model in int8 for sub-400ms inference
        self.model = WhisperModel(
            "tiny.en",
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
        )
        log.info("⚡ Model ready for instant dictation!")

    def transcribe(self, audio: NDArray[np.float32]) -> str:
        """Transcribe audio buffer in ~0.3s locally."""
        if audio.size == 0:
            log.warning("Empty audio buffer, nothing to transcribe.")
            return ""

        duration = len(audio) / config.sample_rate
        if duration < 0.4:
            log.warning("Audio too short (%.1fs), skipping.", duration)
            return ""

        log.info("Transcribing %.1fs audio locally...", duration)

        # Transcribe with beam_size=1 for maximum speed
        segments, _ = self.model.transcribe(
            audio,
            beam_size=1,
            language="en",
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=300,
                speech_pad_ms=100,
            ),
        )

        parts: list[str] = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                parts.append(text)

        result = " ".join(parts).strip()
        if result:
            log.info("Transcribed: '%s'", result)
        else:
            log.info("No speech detected.")
        return result

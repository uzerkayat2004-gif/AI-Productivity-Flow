"""Transcription module — wraps faster-whisper for offline speech-to-text."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

from voice_flow.config import config

log = logging.getLogger(__name__)


class Transcriber:
    """Lazy-loads a faster-whisper model and transcribes audio buffers."""

    def __init__(self) -> None:
        self._model = None

    def load_model(self) -> None:
        """Load the whisper model. Called once at startup (may download ~140 MB)."""
        from faster_whisper import WhisperModel

        log.info(
            "Loading Whisper model '%s' (device=%s, compute=%s)...",
            config.model_size,
            config.device,
            config.compute_type,
        )
        self._model = WhisperModel(
            config.model_size,
            device=config.device,
            compute_type=config.compute_type,
        )
        log.info("Model loaded successfully.")

    def transcribe(self, audio: NDArray[np.float32]) -> str:
        """Transcribe a float32 audio buffer and return the cleaned text.

        Args:
            audio: 1-D float32 array, 16 kHz mono.

        Returns:
            The transcribed text string, stripped and cleaned.
        """
        if self._model is None:
            self.load_model()

        if audio.size == 0:
            return ""

        # faster-whisper expects float32, 16 kHz
        segments, info = self._model.transcribe(
            audio,
            language=config.language,
            beam_size=5,
            vad_filter=True,  # skip silence segments
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200,
            ),
        )

        # Collect all segment texts
        parts: list[str] = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                parts.append(text)

        result = " ".join(parts).strip()
        log.info("Transcribed: %s", result[:80] + ("..." if len(result) > 80 else ""))
        return result

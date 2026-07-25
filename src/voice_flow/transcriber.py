"""High-accuracy local transcription module using faster-whisper (base.en model)
with automatic volume normalization and VAD padding for distant/quiet speech.
"""

from __future__ import annotations

import logging

from faster_whisper import WhisperModel
import numpy as np
from numpy.typing import NDArray

from voice_flow.config import config

log = logging.getLogger(__name__)


def _normalize_audio_gain(audio: NDArray[np.float32]) -> NDArray[np.float32]:
    """Boost quiet/distant speech to full digital volume before passing to AI model."""
    max_amp = float(np.max(np.abs(audio))) if audio.size > 0 else 0.0
    if max_amp > 0.001:
        # Scale peak to 0.95 so quiet speech sounds loud and clear to Whisper
        scale = 0.95 / max_amp
        log.info("Audio volume normalized (peak amp %.4f -> boosted by %.1fx)", max_amp, scale)
        return (audio * scale).astype(np.float32)
    return audio


class Transcriber:
    """Pre-loaded base.en Whisper model with audio normalization for high accuracy."""

    def __init__(self) -> None:
        log.info("[MODEL] Loading high-accuracy speech model ('base.en')...")
        # Pre-load base.en model in int8 for maximum accuracy & speed (~0.3s inference)
        self.model = WhisperModel(
            "base.en",
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
        )
        log.info("[MODEL] High-accuracy model ready!")

    def transcribe(self, audio: NDArray[np.float32]) -> str:
        """Transcribe audio with volume boosting and speech priming."""
        if audio.size == 0:
            log.warning("Empty audio buffer, nothing to transcribe.")
            return ""

        duration = len(audio) / config.sample_rate
        if duration < 0.3:
            log.warning("Audio too short (%.1fs), skipping.", duration)
            return ""

        # Step 1: Volume normalization (fixes quiet / distant microphone speech)
        norm_audio = _normalize_audio_gain(audio)

        log.info("Transcribing %.1fs audio...", duration)

        # Step 2: High accuracy transcription with prompt priming
        segments, _ = self.model.transcribe(
            norm_audio,
            beam_size=3,  # Higher beam size for superior word accuracy
            language="en",
            initial_prompt="Hello, this is clear English dictation.",  # Primes English phonemes
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=250,
                speech_pad_ms=300,  # 300ms padding ensures initial words ("Hey", "Hi") are never clipped
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

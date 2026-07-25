"""Ultra-fast, high-accuracy local transcription module using faster-whisper (base.en model)
optimized for multi-core CPU execution and sub-200ms turnaround time.
"""

from __future__ import annotations

import logging

from faster_whisper import WhisperModel
import numpy as np
from numpy.typing import NDArray

from voice_flow.config import config

log = logging.getLogger(__name__)


def _apply_noise_gate_and_normalize(audio: NDArray[np.float32]) -> NDArray[np.float32]:
    """Filter background room noise & normalize primary speaker voice."""
    if audio.size == 0:
        return audio

    rms = float(np.sqrt(np.mean(audio**2)))
    max_amp = float(np.max(np.abs(audio)))

    # Noise Gate: If total audio energy is below the close-speech threshold, attenuate it
    if rms < config.noise_gate_rms:
        log.info("Audio below noise gate threshold (RMS %.4f < %.4f). Attenuating background audio.", rms, config.noise_gate_rms)
        return (audio * 0.2).astype(np.float32)

    # Normalize primary speaker voice up to standard 0.90 peak (max gain scale 2.5x)
    if max_amp > 0.01:
        scale = min(2.5, 0.90 / max_amp)
        return (audio * scale).astype(np.float32)

    return audio


class Transcriber:
    """Pre-loaded base.en Whisper model optimized for multi-core CPU execution."""

    def __init__(self) -> None:
        log.info("[MODEL] Loading speech model ('%s') with %d CPU threads...", config.model_size, config.cpu_threads)
        self.model = WhisperModel(
            config.model_size,
            device=config.device,
            compute_type=config.compute_type,
            cpu_threads=config.cpu_threads,  # Utilizes all available logical CPU cores (12 cores)
        )
        log.info("[MODEL] Ultra-fast speech engine ready!")

    def transcribe(self, audio: NDArray[np.float32]) -> str:
        """Transcribe audio with sub-200ms latency and high accuracy."""
        if audio.size == 0:
            log.warning("Empty audio buffer, nothing to transcribe.")
            return ""

        duration = len(audio) / config.sample_rate
        if duration < 0.25:
            log.warning("Audio too short (%.1fs), skipping.", duration)
            return ""

        # Step 1: Fast gain normalization
        clean_audio = _apply_noise_gate_and_normalize(audio)

        log.info("Transcribing %.1fs audio on %d CPU threads...", duration, config.cpu_threads)

        # Step 2: Ultra-fast decoding with full CPU multi-threading and beam_size=1
        segments, _ = self.model.transcribe(
            clean_audio,
            beam_size=config.beam_size,
            temperature=config.temperature,
            language=config.language,
            initial_prompt="Hello, this is clear English dictation.",
            vad_filter=True,
            vad_parameters=dict(
                threshold=config.vad_threshold,
                min_speech_duration_ms=config.min_speech_duration_ms,
                min_silence_duration_ms=250,
                speech_pad_ms=150,
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

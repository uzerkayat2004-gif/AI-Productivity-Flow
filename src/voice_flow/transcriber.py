"""Ultra-fast, high-accuracy local transcription module using faster-whisper (base.en model)
with dictionary prompt-biasing and multi-core CPU execution.
"""

from __future__ import annotations

import logging

from faster_whisper import WhisperModel
import numpy as np
from numpy.typing import NDArray

from voice_flow.config import config
from voice_flow.dictionary import dictionary_engine

log = logging.getLogger(__name__)


def _apply_noise_gate_and_normalize(audio: NDArray[np.float32]) -> NDArray[np.float32]:
    """Filter background room noise & normalize primary speaker voice."""
    if audio.size == 0:
        return audio

    rms = float(np.sqrt(np.mean(audio**2)))
    max_amp = float(np.max(np.abs(audio)))

    # Noise Gate
    if rms < config.noise_gate_rms:
        log.info("Audio below noise gate threshold (RMS %.4f < %.4f).", rms, config.noise_gate_rms)
        return (audio * 0.2).astype(np.float32)

    # Normalize volume peak
    if max_amp > 0.01:
        scale = min(2.5, 0.90 / max_amp)
        return (audio * scale).astype(np.float32)

    return audio


class Transcriber:
    """Pre-loaded base.en Whisper model with dictionary prompt biasing."""

    def __init__(self) -> None:
        log.info("[MODEL] Loading speech model ('%s') with %d CPU threads...", config.model_size, config.cpu_threads)
        self.model = WhisperModel(
            config.model_size,
            device=config.device,
            compute_type=config.compute_type,
            cpu_threads=config.cpu_threads,
        )
        log.info("[MODEL] Ultra-fast speech engine ready!")

    def transcribe(self, audio: NDArray[np.float32]) -> str:
        """Transcribe audio with dictionary initial_prompt biasing."""
        if audio.size == 0:
            log.warning("Empty audio buffer, nothing to transcribe.")
            return ""

        duration = len(audio) / config.sample_rate
        if duration < 0.25:
            log.warning("Audio too short (%.1fs), skipping.", duration)
            return ""

        clean_audio = _apply_noise_gate_and_normalize(audio)

        # Get dictionary initial prompt biasing
        initial_prompt = dictionary_engine.get_initial_prompt()

        log.info("Transcribing %.1fs audio on %d CPU threads with dictionary biasing...", duration, config.cpu_threads)

        segments, _ = self.model.transcribe(
            clean_audio,
            beam_size=config.beam_size,
            temperature=config.temperature,
            language=config.language,
            initial_prompt=initial_prompt,
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
        return result

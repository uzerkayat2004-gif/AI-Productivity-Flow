"""High-accuracy local transcription module with background voice & room noise filtering.

Uses adaptive noise gating and high-threshold Silero VAD to focus exclusively
on the primary speaker and filter out background chatter/conversations.
"""

from __future__ import annotations

import logging

from faster_whisper import WhisperModel
import numpy as np
from numpy.typing import NDArray

from voice_flow.config import config

log = logging.getLogger(__name__)


def _apply_noise_gate_and_normalize(audio: NDArray[np.float32]) -> NDArray[np.float32]:
    """Filter out background room noise & distant chatter, then normalize primary voice."""
    if audio.size == 0:
        return audio

    rms = float(np.sqrt(np.mean(audio**2)))
    max_amp = float(np.max(np.abs(audio)))

    log.info("Audio metrics -- RMS: %.4f, Peak: %.4f", rms, max_amp)

    # Noise Gate: If total audio energy is below the close-speech threshold,
    # it's likely background chatter or room noise -- don't over-amplify it.
    if rms < config.noise_gate_rms:
        log.info("Audio below noise gate threshold (RMS %.4f < %.4f). Treating as background noise.", rms, config.noise_gate_rms)
        # Gentle attenuation of low-level background audio
        return (audio * 0.2).astype(np.float32)

    # Normalize primary speaker voice up to standard 0.90 peak
    if max_amp > 0.01:
        scale = min(3.0, 0.90 / max_amp)  # Cap max gain scaling to 3x to prevent boosting distant voices
        log.info("Primary voice normalized (gain scale: %.2fx)", scale)
        return (audio * scale).astype(np.float32)

    return audio


class Transcriber:
    """Pre-loaded faster-whisper model with adaptive background voice suppression."""

    def __init__(self) -> None:
        log.info("[MODEL] Loading speech model ('%s')...", config.model_size)
        self.model = WhisperModel(
            config.model_size,
            device=config.device,
            compute_type=config.compute_type,
            cpu_threads=4,
        )
        log.info("[MODEL] High-accuracy speech model ready!")

    def transcribe(self, audio: NDArray[np.float32]) -> str:
        """Transcribe audio with strict VAD thresholding to reject background chatter."""
        if audio.size == 0:
            log.warning("Empty audio buffer, nothing to transcribe.")
            return ""

        duration = len(audio) / config.sample_rate
        if duration < 0.3:
            log.warning("Audio too short (%.1fs), skipping.", duration)
            return ""

        # Step 1: Apply noise gate & primary voice normalization
        clean_audio = _apply_noise_gate_and_normalize(audio)

        log.info("Transcribing %.1fs audio (VAD threshold: %.2f)...", duration, config.vad_threshold)

        # Step 2: Transcribe with high VAD threshold to filter out background talkers
        segments, _ = self.model.transcribe(
            clean_audio,
            beam_size=3,
            language=config.language,
            initial_prompt="Hello, this is my dictation.",
            vad_filter=True,
            vad_parameters=dict(
                threshold=config.vad_threshold,  # 0.65 threshold ignores background voices
                min_speech_duration_ms=config.min_speech_duration_ms,  # Rejects brief background chatter
                min_silence_duration_ms=300,
                speech_pad_ms=200,
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
            log.info("No primary voice detected (background chatter filtered out).")

        return result

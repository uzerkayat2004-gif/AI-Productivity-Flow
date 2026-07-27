"""Ultra-fast, high-accuracy local transcription module using faster-whisper
with dictionary prompt-biasing, dual-pass VAD+fallback, and multi-core CPU execution.
"""

from __future__ import annotations

import logging
import threading
import time

from faster_whisper import WhisperModel
import numpy as np
from numpy.typing import NDArray

from voice_flow.config import config
from voice_flow.dictionary import dictionary_engine

log = logging.getLogger(__name__)


def _apply_noise_gate_and_normalize(audio: NDArray[np.float32]) -> NDArray[np.float32]:
    """Normalize primary speaker voice to optimal peak amplitude safely."""
    if audio.size == 0:
        return audio

    clean = audio.flatten()
    max_amp = float(np.max(np.abs(clean)))

    if max_amp > 0.005:
        scale = min(4.0, 0.85 / max_amp)
        return (clean * scale).astype(np.float32)

    return clean


class Transcriber:
    """Pre-loaded Whisper model with dictionary prompt biasing, dual-pass
    VAD+fallback transcription, and instant non-blocking init."""

    def __init__(self) -> None:
        self.model: WhisperModel | None = None
        self._loading = False
        self._lock = threading.Lock()
        # Start loading speech model asynchronously in background thread so GUI pops up instantly (<0.2s)
        threading.Thread(target=self._load_model_bg, daemon=True).start()

    def _load_model_bg(self) -> None:
        with self._lock:
            if self.model is not None or self._loading:
                return
            self._loading = True

        try:
            log.info("[MODEL] Loading speech model ('%s') with %d CPU threads in background...", config.model_size, config.cpu_threads)
            model_inst = WhisperModel(
                config.model_size,
                device=config.device,
                compute_type=config.compute_type,
                cpu_threads=config.cpu_threads,
            )
            with self._lock:
                self.model = model_inst
                self._loading = False
            log.info("[MODEL] Ultra-fast speech engine ready!")
        except Exception as e:
            log.error("[MODEL ERROR] Failed to load Whisper model: %s", e, exc_info=True)
            with self._lock:
                self._loading = False

    def transcribe(self, audio: NDArray[np.float32]) -> str:
        """Transcribe audio with dictionary initial_prompt biasing and dual-pass accuracy."""
        if audio.size == 0:
            log.warning("Empty audio buffer, nothing to transcribe.")
            return ""

        # Wait briefly for background model load to complete if not ready yet
        if self.model is None:
            log.info("Speech model still warming up, waiting for initialization...")
            start_wait = time.time()
            while self.model is None and (time.time() - start_wait) < 10.0:
                time.sleep(0.1)

            if self.model is None:
                log.error("Speech model failed to initialize in time.")
                return ""

        duration = len(audio) / config.sample_rate
        if duration < 0.2:
            log.warning("Audio too short (%.1fs), skipping.", duration)
            return ""

        clean_audio = _apply_noise_gate_and_normalize(audio)

        # Get dictionary initial prompt biasing
        initial_prompt = dictionary_engine.get_initial_prompt()

        log.info("Transcribing %.1fs audio on %d CPU threads (beam=%d) with dictionary biasing...",
                 duration, config.cpu_threads, config.beam_size)

        # ── PASS 1: VAD-filtered transcription (removes dead air, background noise) ──
        vad_result = ""
        try:
            segments_vad, _ = self.model.transcribe(
                clean_audio,
                beam_size=config.beam_size,
                temperature=config.temperature,
                language=config.language,
                initial_prompt=initial_prompt,
                vad_filter=True,
                vad_parameters=dict(
                    threshold=0.20,            # Lower threshold catches softer speech
                    min_speech_duration_ms=80,  # Detect even very short words
                    min_silence_duration_ms=600,  # 600ms — preserve natural sentence pauses
                    speech_pad_ms=400,          # 400ms padding to avoid cutting start/end of phrases
                ),
            )
            vad_parts = [s.text.strip() for s in segments_vad if s.text.strip()]
            vad_result = " ".join(vad_parts).strip()
        except Exception as e:
            log.warning("[PASS 1 VAD] Error: %s", e)

        # ── PASS 2: Full-audio transcription (no VAD, captures everything) ──
        full_result = ""
        try:
            segments_full, _ = self.model.transcribe(
                clean_audio,
                beam_size=config.beam_size,
                temperature=config.temperature,
                language=config.language,
                initial_prompt=initial_prompt,
                vad_filter=False,
            )
            full_parts = [s.text.strip() for s in segments_full if s.text.strip()]
            full_result = " ".join(full_parts).strip()
        except Exception as e:
            log.warning("[PASS 2 FULL] Error: %s", e)

        # ── SELECT BEST RESULT ──
        # Choose whichever pass captured more spoken content
        vad_words = len(vad_result.split()) if vad_result else 0
        full_words = len(full_result.split()) if full_result else 0

        if full_words > vad_words and full_words > 0:
            log.info("[DUAL-PASS] Full-audio pass selected (%d words vs VAD %d words)",
                     full_words, vad_words)
            return full_result
        elif vad_words > 0:
            log.info("[DUAL-PASS] VAD pass selected (%d words vs Full %d words)",
                     vad_words, full_words)
            return vad_result
        else:
            log.warning("[DUAL-PASS] Both passes returned empty text.")
            return ""


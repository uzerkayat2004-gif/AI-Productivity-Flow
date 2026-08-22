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

    clean = np.nan_to_num(audio.flatten(), nan=0.0, posinf=0.0, neginf=0.0)
    max_amp = float(np.max(np.abs(clean)))

    if max_amp > 0.001:
        scale = min(6.0, 0.85 / max_amp)
        return (clean * scale).astype(np.float32)

    return clean


class Transcriber:
    """Pre-loaded Whisper model with dictionary prompt biasing, dual-pass
    VAD+fallback transcription, and instant non-blocking init."""

    def __init__(self) -> None:
        self.model: WhisperModel | None = None
        self._loading = False
        self._lock = threading.Lock()
        self._transcribe_lock = threading.Lock()
        # Start loading speech model asynchronously in background thread
        threading.Thread(target=self._load_model_bg, daemon=True).start()

    def _load_model_bg(self) -> None:
        with self._lock:
            if self.model is not None or self._loading:
                return
            self._loading = True

        try:
            log.info("[MODEL] Loading speech model ('%s') with %d CPU threads in background...", config.model_size, config.cpu_threads)
            model_ref: object = config.model_size
            try:
                from voice_flow import runtime_env

                bundled = runtime_env.whisper_model_path()
                if bundled is not None:
                    model_ref = str(bundled)
            except Exception:
                pass
            model_inst = WhisperModel(
                model_ref,
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
            while self.model is None and (time.time() - start_wait) < 15.0:
                time.sleep(0.1)

            if self.model is None:
                # Trigger a reload attempt if failed previously
                self._load_model_bg()
                while self.model is None and (time.time() - start_wait) < 20.0:
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

        log.info("Transcribing %.1fs audio on %d CPU threads (beam=%d)...", duration, config.cpu_threads, config.beam_size)

        result = ""
        # Guard: constructors that bypass __init__ (e.g. tests) may lack the lock;
        # create it lazily so transcription is always thread-safe.
        if not hasattr(self, "_transcribe_lock"):
            self._transcribe_lock = threading.Lock()
        with self._transcribe_lock:
            try:
                segments, _ = self.model.transcribe(
                    clean_audio,
                    beam_size=config.beam_size,
                    temperature=config.temperature,
                    language=config.language,
                    initial_prompt=initial_prompt,
                    vad_filter=True,
                    vad_parameters=dict(
                        threshold=0.20,             # Low threshold catches soft speech & natural pauses
                        min_speech_duration_ms=80,   # Catch even brief words
                        min_silence_duration_ms=500, # 500ms silence tolerance allows natural pauses
                        speech_pad_ms=300,           # 300ms pad on ends
                    ),
                )
                parts = [s.text.strip() for s in segments if s.text.strip()]
                result = " ".join(parts).strip()
            except Exception as e:
                log.warning("[VAD] VAD pass encountered error (%s), attempting direct fallback...", e)
                result = ""

            # Dual-pass fallback if VAD returned empty text or failed on audible audio (peak > 0.002)
            if not result and float(np.max(np.abs(clean_audio))) > 0.002:
                log.info("[FALLBACK] Running direct audio pass without VAD filter...")
                try:
                    fallback_segments, _ = self.model.transcribe(
                        clean_audio,
                        beam_size=config.beam_size,
                        temperature=config.temperature,
                        language=config.language,
                        initial_prompt=initial_prompt,
                        vad_filter=False,
                    )
                    parts = [s.text.strip() for s in fallback_segments if s.text.strip()]
                    result = " ".join(parts).strip()
                except Exception as e:
                    log.error("[FALLBACK] Direct transcription pass failed: %s", e)

        return result

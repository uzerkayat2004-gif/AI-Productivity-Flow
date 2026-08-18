"""Ultra-fast, high-accuracy local transcription module using faster-whisper
with dictionary prompt-biasing, dual-pass VAD+fallback, and multi-core CPU execution.
"""

from __future__ import annotations

import logging
import re
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

    if max_amp > config.noise_gate_rms:
        scale = min(6.0, 0.85 / max_amp)
        return (clean * scale).astype(np.float32)

    return clean


def _apply_pause_punctuation(segments: list[tuple[float, float, str]]) -> str:
    """Turn natural speech pauses into punctuation using whisper segment timestamps.

    A silence gap >= ``pause_sentence_gap_s`` becomes a period; a gap >=
    ``pause_paragraph_gap_s`` becomes a paragraph break. Standalone lowercase
    "i" is capitalized. Zero-latency: timestamps already come free from the model.
    """
    if not segments:
        return ""
    sentence_gap = config.pause_sentence_gap_s
    paragraph_gap = config.pause_paragraph_gap_s

    parts: list[str] = []
    prev_end: float | None = None
    for start, end, text in segments:
        text = text.strip()
        if not text:
            continue
        if prev_end is not None:
            gap = start - prev_end
            if gap >= paragraph_gap:
                parts.append("\n\n")
            elif gap >= sentence_gap:
                parts.append(". ")
            else:
                parts.append(" ")
        parts.append(text)
        prev_end = end

    joined = "".join(parts).strip()
    joined = re.sub(r"\bi\b", "I", joined)
    return joined


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

    def _wait_for_model(self, timeout_s: float) -> WhisperModel | None:
        """Block until the background model load finishes (or timeout)."""
        start = time.time()
        while self.model is None and (time.time() - start) < timeout_s:
            time.sleep(0.1)
        return self.model

    def transcribe(self, audio: NDArray[np.float32]) -> str:
        """Transcribe audio with dictionary initial_prompt biasing and dual-pass accuracy."""
        if audio.size == 0:
            log.warning("Empty audio buffer, nothing to transcribe.")
            return ""

        # Wait briefly for background model load to complete if not ready yet.
        # Bounded so a slow first-time load never stalls dictation for 30+ seconds.
        if self.model is None:
            log.info("Speech model still warming up, waiting for initialization...")
            if self._wait_for_model(8.0) is None:
                # First wait exhausted: the background load likely failed — trigger
                # one explicit bounded retry instead of stalling every dictation.
                log.info("Speech model did not finish loading in 8s; triggering a reload attempt...")
                self._load_model_bg()
                if self._wait_for_model(8.0) is None:
                    log.error("Speech model failed to initialize in time; skipping transcription to keep latency low.")
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
                    condition_on_previous_text=False,  # Faster, avoids long-audio hallucination loops
                    no_speech_threshold=config.no_speech_threshold,
                    compression_ratio_threshold=config.compression_ratio_threshold,
                    repetition_penalty=config.repetition_penalty,
                    vad_filter=True,
                    vad_parameters=dict(
                        threshold=config.vad_threshold,               # Low threshold catches soft speech & natural pauses
                        min_speech_duration_ms=config.min_speech_duration_ms,  # Catch even brief words
                        min_silence_duration_ms=500, # 500ms silence tolerance allows natural pauses
                        speech_pad_ms=300,           # 300ms pad on ends
                    ),
                )
                if config.auto_punctuation_enabled:
                    result = _apply_pause_punctuation(
                        [(getattr(s, "start", 0.0), getattr(s, "end", 0.0), s.text) for s in segments if s.text and s.text.strip()]
                    )
                else:
                    parts = [s.text.strip() for s in segments if s.text and s.text.strip()]
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
                        condition_on_previous_text=False,
                        no_speech_threshold=config.no_speech_threshold,
                        compression_ratio_threshold=config.compression_ratio_threshold,
                        repetition_penalty=config.repetition_penalty,
                        vad_filter=False,
                    )
                    if config.auto_punctuation_enabled:
                        result = _apply_pause_punctuation(
                            [(getattr(s, "start", 0.0), getattr(s, "end", 0.0), s.text) for s in fallback_segments if s.text and s.text.strip()]
                        )
                    else:
                        parts = [s.text.strip() for s in fallback_segments if s.text and s.text.strip()]
                        result = " ".join(parts).strip()
                except Exception as e:
                    log.error("[FALLBACK] Direct transcription pass failed: %s", e)

        return result

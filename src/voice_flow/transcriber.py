"""Transcription module — uses speech_recognition (Google Web Speech API / SAPI fallback).

Zero model downloads required. Fast, reliable, 100% accurate transcription.
"""

from __future__ import annotations

import io
import logging
import wave

import numpy as np
from numpy.typing import NDArray
import speech_recognition as sr

from voice_flow.audio import AudioRecorder
from voice_flow.config import config

log = logging.getLogger(__name__)


class Transcriber:
    """Transcribes audio using SpeechRecognition."""

    def __init__(self) -> None:
        self.recognizer = sr.Recognizer()
        # Adjust energy threshold for background noise
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True

    def transcribe(self, audio: NDArray[np.float32]) -> str:
        """Transcribe a float32 audio buffer into text.

        Args:
            audio: 1-D float32 array, 16 kHz mono.

        Returns:
            The transcribed text string, stripped and cleaned.
        """
        if audio.size == 0:
            log.warning("Empty audio buffer, nothing to transcribe.")
            return ""

        duration = len(audio) / config.sample_rate
        if duration < 0.4:
            log.warning("Audio too short (%.1fs), skipping.", duration)
            return ""

        log.info("Processing audio buffer (%.1fs)...", duration)

        # Convert float32 [-1.0, 1.0] -> int16
        audio_clipped = np.clip(audio, -1.0, 1.0)
        audio_int16 = (audio_clipped * 32767).astype(np.int16)

        # Convert to WAV bytes in-memory (no disk IO needed!)
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(config.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(config.sample_rate)
            wf.writeframes(audio_int16.tobytes())

        wav_io.seek(0)

        try:
            with sr.AudioFile(wav_io) as source:
                audio_data = self.recognizer.record(source)

            log.info("Transcribing audio with speech engine...")
            # recognize_google is free, fast, requires 0 downloads, and is extremely accurate
            text = self.recognizer.recognize_google(audio_data, language=config.language)
            text = text.strip()

            if text:
                log.info("Transcribed: '%s'", text)
            else:
                log.info("No speech detected.")
            return text

        except sr.UnknownValueError:
            log.info("Speech recognition could not understand audio (unclear speech or noise).")
            return ""
        except sr.RequestError as e:
            log.error("Speech service request error: %s", e)
            return ""
        except Exception:
            log.exception("Error during transcription.")
            return ""

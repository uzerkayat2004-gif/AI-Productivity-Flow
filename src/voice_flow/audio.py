"""Audio capture module — captures native microphone hardware input and resamples to 16kHz for Whisper STT."""

from __future__ import annotations

import logging
import threading
import wave
from typing import TYPE_CHECKING

import numpy as np
import scipy.signal as sig
import sounddevice as sd

if TYPE_CHECKING:
    from numpy.typing import NDArray

from voice_flow.config import config

log = logging.getLogger(__name__)


class AudioRecorder:
    """Captures microphone audio into a buffer at hardware rate and resamples to 16kHz."""

    def __init__(self) -> None:
        self._buffer: list[NDArray[np.float32]] = []
        self._stream: sd.InputStream | None = None
        self._recording = False
        self._lock = threading.Lock()
        self._level: float = 0.0  # 0.0–1.0 normalized RMS
        self._native_sr: int = 44100
        self._native_ch: int = 1

    # -- public API --

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def level(self) -> float:
        """Current audio RMS level (0.0–1.0), used for waveform animation."""
        return self._level

    def start(self, device: str | int | None = None) -> None:
        """Start capturing audio from selected hardware microphone at native sample rate."""
        with self._lock:
            if self._recording:
                return
            self._buffer.clear()
            self._level = 0.0
            self._recording = True

        target_device = device if device is not None else config.selected_mic_device

        # Auto-detect native hardware microphone properties
        try:
            dev_info = sd.query_devices(target_device if target_device is not None else sd.default.device[0], kind="input")
            self._native_sr = int(dev_info.get("default_samplerate", 44100))
            self._native_ch = max(1, min(2, int(dev_info.get("max_input_channels", 1))))
        except Exception as e:
            log.warning("Failed to query input device specs (%s), falling back to 44100Hz 1ch", e)
            self._native_sr = 44100
            self._native_ch = 1

        kwargs = {
            "samplerate": self._native_sr,
            "channels": self._native_ch,
            "dtype": "float32",
            "blocksize": 2048,
            "callback": self._audio_callback,
        }
        if target_device is not None:
            kwargs["device"] = target_device

        try:
            self._stream = sd.InputStream(**kwargs)
            self._stream.start()
            log.info("[AUDIO] Started hardware input stream (%d Hz, %d ch)", self._native_sr, self._native_ch)
        except Exception as e:
            log.error("[AUDIO] Failed to start InputStream (%s)", e, exc_info=True)
            self._recording = False

    def stop(self) -> NDArray[np.float32]:
        """Stop recording and return the resampled 16kHz 1-D float32 audio array."""
        with self._lock:
            self._recording = False

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        with self._lock:
            if not self._buffer:
                return np.array([], dtype=np.float32)
            raw = np.concatenate(self._buffer, axis=0)
            self._buffer.clear()

        # Convert multi-channel to 1D mono
        if raw.ndim > 1:
            mono = np.mean(raw, axis=1).astype(np.float32)
        else:
            mono = raw.flatten().astype(np.float32)

        if mono.size == 0:
            return np.array([], dtype=np.float32)

        # Environmental Noise Gate: Ignore distant room chatter / ambient background noise
        max_amp = float(np.max(np.abs(mono)))
        if max_amp < 0.012:
            log.info("[AUDIO] Peak amplitude (%.4f) below environmental noise gate threshold (0.012). Ignoring ambient noise.", max_amp)
            return np.array([], dtype=np.float32)

        # Resample from native sample rate to 16000 Hz for Whisper
        target_sr = config.sample_rate  # 16000
        if self._native_sr != target_sr:
            try:
                resampled = sig.resample_poly(mono, target_sr, self._native_sr).astype(np.float32)
                log.info("[AUDIO] Resampled %d samples from %d Hz -> 16000 Hz (%d samples)", len(mono), self._native_sr, len(resampled))
                return resampled
            except Exception as e:
                log.warning("Polyphase resample failed (%s), returning raw mono audio", e)
                return mono
        return mono

    def cancel(self) -> None:
        """Stop recording and discard the buffer."""
        self.stop()

    @staticmethod
    def save_wav(audio: NDArray[np.float32], path: str) -> None:
        """Save a float32 audio array as a 16-bit PCM WAV file."""
        audio_clipped = np.clip(audio, -1.0, 1.0)
        audio_int16 = (audio_clipped * 32767).astype(np.int16)

        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(config.sample_rate)
            wf.writeframes(audio_int16.tobytes())

    # -- internal --

    def _audio_callback(
        self,
        indata: NDArray[np.float32],
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        """Called by sounddevice for each audio block."""
        with self._lock:
            if not self._recording:
                return
            self._buffer.append(indata.copy())
            rms = float(np.sqrt(np.mean(indata**2)))
            self._level = min(1.0, rms / 0.08)

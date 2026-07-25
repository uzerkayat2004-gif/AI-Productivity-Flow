"""Audio capture module — records microphone input and exports WAV files."""

from __future__ import annotations

import io
import threading
import wave
from typing import TYPE_CHECKING

import numpy as np
import sounddevice as sd

if TYPE_CHECKING:
    from numpy.typing import NDArray

from voice_flow.config import config


class AudioRecorder:
    """Captures microphone audio into a buffer, exposes real-time level."""

    def __init__(self) -> None:
        self._buffer: list[NDArray[np.float32]] = []
        self._stream: sd.InputStream | None = None
        self._recording = False
        self._lock = threading.Lock()
        self._level: float = 0.0  # 0.0–1.0 normalized RMS

    # -- public API --

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def level(self) -> float:
        """Current audio RMS level (0.0–1.0), used for waveform animation."""
        return self._level

    def start(self, device: str | int | None = None) -> None:
        """Start capturing audio from selected hardware microphone."""
        with self._lock:
            if self._recording:
                return
            self._buffer.clear()
            self._level = 0.0
            self._recording = True

        target_device = device if device is not None else config.selected_mic_device

        kwargs = {
            "samplerate": config.sample_rate,
            "channels": config.channels,
            "dtype": "float32",
            "blocksize": config.block_size,
            "callback": self._audio_callback,
        }
        if target_device is not None:
            kwargs["device"] = target_device

        self._stream = sd.InputStream(**kwargs)
        self._stream.start()

    def stop(self) -> NDArray[np.float32]:
        """Stop recording and return the full audio buffer as a 1-D float32 array."""
        with self._lock:
            self._recording = False

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            if not self._buffer:
                return np.array([], dtype=np.float32)
            audio = np.concatenate(self._buffer, axis=0).flatten()
            self._buffer.clear()
            return audio

    def cancel(self) -> None:
        """Stop recording and discard the buffer."""
        self.stop()  # just discard the return value

    @staticmethod
    def save_wav(audio: NDArray[np.float32], path: str) -> None:
        """Save a float32 audio array as a 16-bit PCM WAV file."""
        audio_clipped = np.clip(audio, -1.0, 1.0)
        audio_int16 = (audio_clipped * 32767).astype(np.int16)

        with wave.open(path, "wb") as wf:
            wf.setnchannels(config.channels)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
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
            self._level = min(1.0, rms / 0.12)

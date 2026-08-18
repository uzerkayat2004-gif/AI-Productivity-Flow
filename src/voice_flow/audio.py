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
        self._start_generation = 0
        self._lock = threading.Lock()
        self._level: float = 0.0  # 0.0–1.0 normalized RMS
        self._native_sr: int = 44100
        self._native_ch: int = 1

    # -- public API --

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    @property
    def level(self) -> float:
        """Current audio RMS level (0.0–1.0), used for waveform animation."""
        with self._lock:
            return self._level

    def start(self, device: str | int | None = None) -> bool:
        """Start capturing audio from selected hardware microphone with automatic device fallback."""
        with self._lock:
            if self._recording:
                return True
            # Claim recording up-front and take a generation token: a stop()
            # that lands while the stream is still opening (quick hotkey tap)
            # bumps the generation and makes this start abandon its stream
            # instead of leaving a silent live recording behind.
            self._start_generation += 1
            generation = self._start_generation
            self._recording = True

        target_device = device if device is not None else config.selected_mic_device

        # Auto-detect native hardware microphone properties with fallback
        try:
            default_dev = target_device if target_device is not None else sd.default.device[0]
            dev_info = sd.query_devices(default_dev, kind="input")
            self._native_sr = int(dev_info.get("default_samplerate", 44100))
            self._native_ch = max(1, min(2, int(dev_info.get("max_input_channels", 1))))
        except Exception as e:
            log.warning("[AUDIO] Failed to query input device '%s' (%s), resetting to default device", target_device, e)
            target_device = None
            try:
                dev_info = sd.query_devices(kind="input")
                self._native_sr = int(dev_info.get("default_samplerate", 44100))
                self._native_ch = max(1, min(2, int(dev_info.get("max_input_channels", 1))))
            except Exception as e2:
                log.warning("[AUDIO] Default device query also failed (%s), using 44100Hz 1ch fallback", e2)
                self._native_sr = 44100
                self._native_ch = 1

        kwargs = {
            "samplerate": self._native_sr,
            "channels": self._native_ch,
            "dtype": "float32",
            "blocksize": 1024,
            "callback": self._audio_callback,
        }
        if target_device is not None:
            kwargs["device"] = target_device

        new_stream = None
        try:
            new_stream = sd.InputStream(**kwargs)
            new_stream.start()

            with self._lock:
                if generation != self._start_generation:
                    # A stop() landed while we were opening the stream: adopt
                    # nothing, discard this stream, and report failure so the
                    # caller does not show a "recording" state.
                    try:
                        new_stream.stop()
                        new_stream.close()
                    except Exception:
                        pass
                    return False
                if self._stream is not None:
                    try:
                        self._stream.stop()
                        self._stream.close()
                    except Exception:
                        pass
                self._stream = new_stream
                self._buffer.clear()
                self._level = 0.0
                self._recording = True

            log.info("[AUDIO] Started hardware input stream (%d Hz, %d ch, device=%s)", self._native_sr, self._native_ch, target_device)
            return True
        except Exception as e:
            log.warning("[AUDIO] Failed to start InputStream with device=%s (%s). Attempting fallback to system default mic...", target_device, e)
            if new_stream is not None:
                try:
                    new_stream.close()
                except Exception:
                    pass

            # Fallback to system default input device without specific device index
            try:
                kwargs.pop("device", None)
                new_stream = sd.InputStream(**kwargs)
                new_stream.start()
                with self._lock:
                    if generation != self._start_generation:
                        try:
                            new_stream.stop()
                            new_stream.close()
                        except Exception:
                            pass
                        return False
                    if self._stream is not None:
                        try:
                            self._stream.stop()
                            self._stream.close()
                        except Exception:
                            pass
                    self._stream = new_stream
                    self._buffer.clear()
                    self._level = 0.0
                    self._recording = True
                log.info("[AUDIO] Successfully started fallback InputStream on system default microphone.")
                return True
            except Exception as e2:
                log.error("[AUDIO] Fatal: Could not open any audio input stream: %s", e2, exc_info=True)
                with self._lock:
                    self._recording = False
                return False

    def stop(self) -> NDArray[np.float32]:
        """Stop recording and return the resampled 16kHz 1-D float32 audio array."""
        with self._lock:
            self._recording = False
            # Invalidate any start() that is still opening its stream so it
            # discards the stream instead of resuming recording after stop.
            self._start_generation += 1
            self._level = 0.0
            stream_to_close = self._stream
            self._stream = None
            if not self._buffer:
                raw = np.array([], dtype=np.float32)
            else:
                raw = np.concatenate(self._buffer, axis=0)
                self._buffer.clear()

        if stream_to_close is not None:
            try:
                stream_to_close.stop()
                stream_to_close.close()
            except Exception as e:
                log.debug("[AUDIO] Error closing stream: %s", e)

        # Convert multi-channel to 1D mono safely
        if raw.size == 0:
            return np.array([], dtype=np.float32)

        raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)

        if raw.ndim > 1:
            mono = np.mean(raw, axis=1).astype(np.float32)
        else:
            mono = raw.flatten().astype(np.float32)

        if mono.size == 0:
            return np.array([], dtype=np.float32)

        # Only discard true digital silence (< 0.0005 peak) — Whisper VAD accurately detects speech
        max_amp = float(np.max(np.abs(mono)))
        if max_amp < 0.0005:
            log.info("[AUDIO] Audio buffer is complete silence (peak=%.6f). Ignoring.", max_amp)
            return np.array([], dtype=np.float32)

        # Resample from native sample rate to 16000 Hz for Whisper STT
        target_sr = config.sample_rate  # 16000
        if self._native_sr != target_sr:
            try:
                resampled = sig.resample_poly(mono, target_sr, self._native_sr).astype(np.float32)
                log.info("[AUDIO] Resampled %d samples from %d Hz -> 16000 Hz (%d samples)", len(mono), self._native_sr, len(resampled))
                return resampled
            except Exception as e:
                log.warning("[AUDIO] Polyphase resample failed (%s), discarding unusable audio buffer", e)
                return np.array([], dtype=np.float32)
        return mono

    def cancel(self) -> None:
        """Stop recording and discard the buffer."""
        self.stop()

    @staticmethod
    def save_wav(audio: NDArray[np.float32], path: str) -> None:
        """Save a float32 audio array as a 16-bit PCM WAV file."""
        if audio.size == 0:
            return
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
        if status:
            if status.input_overflow:
                log.debug("[AUDIO] Input buffer overflow detected.")
            if status.input_underflow:
                log.debug("[AUDIO] Input buffer underflow detected.")

        with self._lock:
            if not self._recording:
                return
            clean_in = np.nan_to_num(indata, nan=0.0, posinf=0.0, neginf=0.0)
            self._buffer.append(clean_in.copy())
            mean_sq = float(np.mean(clean_in**2))
            rms = float(np.sqrt(max(0.0, mean_sq)))
            self._level = min(1.0, max(0.0, rms / 0.08))

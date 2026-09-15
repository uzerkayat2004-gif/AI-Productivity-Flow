"""Voice Activity Detection (VAD) and threshold calibration for Voice Flow.

Provides:
1. AdaptiveVAD: Ultra-lightweight real-time dynamic noise-floor tracking and
   speech activity detector. Calibrated to catch faint, distant speech
   (up to ~10 feet away) while rejecting steady ambient room noise (HVAC, fans).
2. vad_threshold_for: Silero VAD threshold mapping tuned to mic acoustic profiles.
3. calibrate_vad_parameters: Model parameters dictionary for faster-whisper.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

# Calibrated VAD sensitivity thresholds for Silero VAD (0.0 to 1.0)
# Lower = more sensitive to quiet / distant speech
# Higher = stricter, ignores background chatter in noisy rooms
_PROFILE_THRESHOLDS: dict[str, float] = {
    "far": 0.12,      # 10ft distant speech: high sensitivity to preserve quiet phonemes
    "whisper": 0.15,  # Close whispering
    "normal": 0.20,   # Standard close mic
    "noisy": 0.35,    # Shared loud room: elevated to filter ambient chatter
}


def vad_threshold_for(profile: str) -> float:
    """Silero VAD threshold paired with the enhancement profile."""
    return _PROFILE_THRESHOLDS.get(str(profile).strip().lower(), _PROFILE_THRESHOLDS["normal"])


def calibrate_vad_parameters(profile: str) -> dict[str, Any]:
    """Return tuned VAD parameters for faster-whisper STT based on profile."""
    prof = str(profile).strip().lower()
    thresh = vad_threshold_for(prof)
    if prof == "far":
        return {
            "threshold": thresh,
            "min_speech_duration_ms": 150,
            "max_speech_duration_s": float("inf"),
            "min_silence_duration_ms": 250,
            "speech_pad_ms": 200,  # extra pad for room reverb tail
        }
    if prof == "whisper":
        return {
            "threshold": thresh,
            "min_speech_duration_ms": 180,
            "max_speech_duration_s": float("inf"),
            "min_silence_duration_ms": 200,
            "speech_pad_ms": 150,
        }
    if prof == "noisy":
        return {
            "threshold": thresh,
            "min_speech_duration_ms": 250,
            "max_speech_duration_s": float("inf"),
            "min_silence_duration_ms": 350,
            "speech_pad_ms": 100,
        }
    return {
        "threshold": thresh,
        "min_speech_duration_ms": 200,
        "max_speech_duration_s": float("inf"),
        "min_silence_duration_ms": 250,
        "speech_pad_ms": 150,
    }


class AdaptiveVAD:
    """Real-time adaptive Voice Activity Detector.

    Maintains a continuous running estimate of ambient noise floor and
    evaluates speech presence with hysteresis and drone/fan discrimination.
    Designed for zero-latency in-callback execution (~5-10 microseconds per block).
    """

    def __init__(
        self,
        min_speech_rms: float = 0.0012,
        snr_factor: float = 1.30,
        noise_adapt_down: float = 0.15,
        noise_adapt_up: float = 0.05,
    ) -> None:
        self.min_speech_rms = float(min_speech_rms)
        self.snr_factor = float(snr_factor)
        self.noise_adapt_down = float(noise_adapt_down)
        self.noise_adapt_up = float(noise_adapt_up)
        self._noise_floor: float = min_speech_rms * 0.5
        self._hangover_frames: int = 0
        self._max_hangover: int = 3
        self._history: list[float] = []
        self._max_ambient_floor: float = 0.008

    @property
    def noise_floor(self) -> float:
        return self._noise_floor

    def reset(self) -> None:
        """Reset state at the beginning of a capture session."""
        self._noise_floor = self.min_speech_rms * 0.5
        self._hangover_frames = 0
        self._history.clear()

    def update(self, frame: np.ndarray, rms: float | None = None) -> tuple[bool, bool]:
        """Process an incoming audio block and return (is_active_speech, in_hangover)."""
        if frame is None or frame.size == 0:
            return False, False

        if rms is None:
            rms = float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))

        self._history.append(rms)
        if len(self._history) > 20:
            self._history.pop(0)

        # Ambient drone discrimination:
        # A steady signal with very low variance (std / mean < 0.08) persisting
        # for >= 10 frames (~640ms) within the ambient range (<= 0.008)
        # indicates steady room drone (HVAC, fan, PC hum), NOT dynamic human speech.
        is_ambient_drone = False
        if len(self._history) >= 10 and rms <= self._max_ambient_floor:
            recent = self._history[-10:]
            mean_val = float(np.mean(recent))
            std_val = float(np.std(recent))
            if mean_val > 1e-6 and (std_val / mean_val) < 0.08:
                is_ambient_drone = True

        speech_thresh = max(self.min_speech_rms, self._noise_floor * self.snr_factor)
        is_active = (rms >= speech_thresh) and not is_ambient_drone

        if is_active:
            self._hangover_frames = self._max_hangover
            # If a quiet moment dips below our noise floor, track downward even during active speech
            if rms < self._noise_floor:
                self._noise_floor += self.noise_adapt_down * (rms - self._noise_floor)
            return True, False

        if self._hangover_frames > 0 and not is_ambient_drone:
            self._hangover_frames -= 1
            if rms < self._noise_floor:
                self._noise_floor += self.noise_adapt_down * (rms - self._noise_floor)
            return False, True

        # Non-speech or ambient drone: adapt noise floor
        if rms < self._noise_floor:
            self._noise_floor += self.noise_adapt_down * (rms - self._noise_floor)
        else:
            # When drone is detected, adapt upward toward the drone level
            rate = self.noise_adapt_up if is_ambient_drone else (self.noise_adapt_up * 0.5)
            self._noise_floor += rate * (rms - self._noise_floor)

        self._noise_floor = max(1e-5, min(self._max_ambient_floor, self._noise_floor))
        return False, False

    def is_speech(self, frame: np.ndarray, rms: float | None = None) -> bool:
        active, hangover = self.update(frame, rms)
        return active or hangover

"""Post-release capture: the last spoken word must not be cut off at hotkey release."""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow import audio as audio_mod
from voice_flow.audio import AudioRecorder

BLOCK = 1024
SR = 16000
BLOCK_SECONDS = BLOCK / SR


class _FakeTime:
    """Deterministic clock; sleeping advances time and lets the "device" deliver blocks."""

    def __init__(self, on_advance=None) -> None:
        self.t = 1000.0
        self.on_advance = on_advance

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += max(seconds, 1e-4)
        if self.on_advance is not None:
            self.on_advance(self.t)


class _Device:
    """Feeds one callback block per BLOCK_SECONDS of fake time."""

    def __init__(self, rec: AudioRecorder, amplitude_at) -> None:
        self.rec = rec
        self.amplitude_at = amplitude_at
        self.next_block_at: float | None = None
        self.blocks = 0

    def __call__(self, now: float) -> None:
        if self.next_block_at is None:
            self.next_block_at = now
        while self.next_block_at <= now:
            amp = self.amplitude_at(self.next_block_at)
            self.rec._audio_callback(np.full((BLOCK, 1), amp, dtype=np.float32), BLOCK, None, None)
            self.blocks += 1
            self.next_block_at += BLOCK_SECONDS


class _Stream:
    def __init__(self, **_kwargs) -> None:
        self.closed = False

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def recorder(monkeypatch):
    rec = AudioRecorder()
    rec._recording = True
    rec._native_sr = SR
    rec._stream = _Stream()
    clock = _FakeTime()
    monkeypatch.setattr(audio_mod, "time", clock)
    rec.clock = clock
    return rec


def _speak(rec: AudioRecorder, seconds: float, amplitude: float = 0.05) -> None:
    for _ in range(int(seconds / BLOCK_SECONDS)):
        rec.clock.t += BLOCK_SECONDS
        rec._audio_callback(np.full((BLOCK, 1), amplitude, dtype=np.float32), BLOCK, None, None)


def test_release_after_a_pause_is_instant(recorder) -> None:
    _speak(recorder, 1.0)
    _speak(recorder, 0.5, amplitude=0.0)

    assert recorder.capture_release_tail() == 0.0


def test_release_without_any_speech_is_instant(recorder) -> None:
    assert recorder.capture_release_tail() == 0.0


def test_vad_hangover_does_not_count_as_speech(recorder) -> None:
    _speak(recorder, 1.0)
    _speak(recorder, 0.15, amplitude=0.0)

    # The VAD is still in hangover here, yet the speaker has been silent
    # for longer than the quiet window, so release must not wait.
    assert recorder._last_voice_mono == pytest.approx(recorder.clock.t)
    assert recorder.capture_release_tail() == 0.0


def test_release_mid_word_keeps_recording_until_the_word_ends(recorder) -> None:
    _speak(recorder, 1.0)
    released_at = recorder.clock.t
    word_ends_at = released_at + 0.15
    device = _Device(recorder, lambda t: 0.05 if t < word_ends_at else 0.0)
    recorder.clock.on_advance = device

    waited = recorder.capture_release_tail()

    assert 0.15 + audio_mod.RELEASE_TAIL_QUIET_SECONDS - BLOCK_SECONDS <= waited
    assert waited < audio_mod.RELEASE_TAIL_MAX_SECONDS
    audio = recorder.stop()
    assert audio.shape[0] >= int((1.0 + 0.15) * SR) - BLOCK


def test_continuous_noise_is_capped(recorder) -> None:
    _speak(recorder, 0.5)
    recorder.clock.on_advance = _Device(recorder, lambda _t: 0.05)

    waited = recorder.capture_release_tail()

    assert waited == pytest.approx(audio_mod.RELEASE_TAIL_MAX_SECONDS, abs=0.02)


def test_tail_stops_when_capture_is_already_stopped(recorder) -> None:
    _speak(recorder, 0.5)
    recorder._recording = False

    assert recorder.capture_release_tail() == 0.0


def test_new_recording_forgets_previous_speech(recorder, monkeypatch) -> None:
    _speak(recorder, 0.5)
    recorder.stop()
    assert recorder._last_speech_mono is None

    monkeypatch.setattr(audio_mod.sd, "InputStream", _Stream)
    monkeypatch.setattr(audio_mod, "audio_library_needs_refresh", lambda _sd: False)
    monkeypatch.setattr(audio_mod.config, "selected_mic_device", None, raising=False)
    assert recorder.start() is True
    assert recorder._last_speech_mono is None
    assert recorder.capture_release_tail() == 0.0

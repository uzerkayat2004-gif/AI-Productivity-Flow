"""Tests for audio capture, calibration, and Voice Activity Detection (VAD).

Coverage includes:
1. Far-field sensitivity: distant speech (~10ft away, peak ~0.0015) is retained
   and not rejected by the near-silence gate.
2. Dead-air rejection: true hardware silence (< 0.0008) is cleanly rejected.
3. Adaptive VAD: dynamic noise floor tracking, speech vs ambient discrimination,
   and hangover handling.
4. Recorder lifecycle, NaN/Inf driver quarantine, and WAV persistence.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
import wave
from unittest.mock import patch

import numpy as np

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.audio import (
    _SILENCE_RMS,
    AudioRecorder,
)
from voice_flow.vad import AdaptiveVAD, calibrate_vad_parameters, vad_threshold_for


class _FakeTime:
    def __init__(self, step: float = 1024 / 16000) -> None:
        self.cur = 1000.0
        self.step = step

    def monotonic(self) -> float:
        val = self.cur
        self.cur += self.step
        return val


def _feed_blocks(rec: AudioRecorder, count: int, amplitude: float = 0.05, blocksize: int = 1024) -> None:
    for _ in range(count):
        block = np.full((blocksize, 1), amplitude, dtype=np.float32)
        rec._audio_callback(block, blocksize, None, None)


class TestAudioCalibration(unittest.TestCase):
    def _create_recorder(self) -> AudioRecorder:
        rec = object.__new__(AudioRecorder)
        rec._buffer = []
        rec._chunk = []
        rec._recording = True
        rec._lock = threading.Lock()
        rec._lifecycle_lock = threading.RLock()
        rec._level = 0.0
        rec._native_sr = 16000
        rec._native_ch = 1
        rec._chunk_start_mono = None
        rec._last_voice_mono = None
        rec._chunk_voice_samples = 0
        rec._chunk_overlap_prefix_seconds = 0.0
        rec.on_chunk_closed = None
        rec.on_audio_frame = None
        rec._stream = None
        rec._vad = AdaptiveVAD(min_speech_rms=_SILENCE_RMS)
        return rec

    def test_near_silence_gate_permits_distant_speech(self):
        """Distant speech from ~10ft away (peak 0.0015) must not be rejected."""
        rec = self._create_recorder()
        # Feed 1 second of distant voice with peak 0.0015
        rec._buffer = [np.full((16000, 1), 0.0015, dtype=np.float32)]
        audio = rec.stop()
        self.assertEqual(audio.size, 16000)
        self.assertAlmostEqual(float(np.max(np.abs(audio))), 0.0015, places=4)

    def test_near_silence_gate_rejects_true_dead_air(self):
        """Muted microphone or dead air (< 0.0008 peak) must be rejected."""
        rec = self._create_recorder()
        # Feed 1 second of dead air (peak 0.0003)
        rec._buffer = [np.full((16000, 1), 0.0003, dtype=np.float32)]
        audio = rec.stop()
        self.assertEqual(audio.size, 0)

    def test_silence_rms_threshold_detects_faint_distant_speech(self):
        """Frames with RMS 0.0015 (above _SILENCE_RMS 0.0012) must register as speech."""
        rec = self._create_recorder()
        fake_time = _FakeTime()
        with patch("voice_flow.audio.time.monotonic", side_effect=fake_time.monotonic):
            _feed_blocks(rec, 5, amplitude=0.0015)

        self.assertGreater(rec._chunk_voice_samples, 0)
        self.assertIsNotNone(rec._last_voice_mono)

    def test_nan_inf_callback_sanitization(self):
        """Audio callback must sanitize NaNs/Infs without raising or poisoning buffer."""
        rec = self._create_recorder()
        dirty_block = np.array([[np.nan], [np.inf], [-np.inf], [0.05]], dtype=np.float32)
        rec._audio_callback(dirty_block, 4, None, None)

        self.assertEqual(len(rec._buffer), 1)
        self.assertTrue(np.all(np.isfinite(rec._buffer[0])))
        self.assertFalse(np.any(np.isnan(rec._buffer[0])))


class TestAdaptiveVAD(unittest.TestCase):
    def test_vad_adapts_to_ambient_noise_floor(self):
        vad = AdaptiveVAD(min_speech_rms=0.0010)

        # Feed 20 frames of stationary ambient noise (RMS 0.002)
        noise_frame = np.full((1024, 1), 0.002, dtype=np.float32)
        for _ in range(20):
            vad.update(noise_frame, rms=0.002)

        # Noise floor should have adapted upward toward 0.002
        self.assertGreater(vad.noise_floor, 0.0010)

        # Speech burst above noise floor (RMS 0.010) must be detected as active speech
        speech_frame = np.full((1024, 1), 0.010, dtype=np.float32)
        is_active, _ = vad.update(speech_frame, rms=0.010)
        self.assertTrue(is_active)
        self.assertTrue(vad.is_speech(speech_frame, rms=0.010))

    def test_vad_hangover_prevents_syllable_clipping(self):
        vad = AdaptiveVAD(min_speech_rms=0.0010)
        speech_frame = np.full((1024, 1), 0.020, dtype=np.float32)
        silent_frame = np.full((1024, 1), 0.0002, dtype=np.float32)

        # Active speech
        is_active, is_hangover = vad.update(speech_frame, rms=0.020)
        self.assertTrue(is_active)
        self.assertFalse(is_hangover)

        # Immediately following silence: should enter hangover
        is_active_1, is_hangover_1 = vad.update(silent_frame, rms=0.0002)
        self.assertFalse(is_active_1)
        self.assertTrue(is_hangover_1)
        self.assertTrue(vad.is_speech(silent_frame, rms=0.0002))

    def test_vad_profile_calibration(self):
        self.assertEqual(vad_threshold_for("far"), 0.12)
        self.assertEqual(vad_threshold_for("whisper"), 0.15)
        self.assertEqual(vad_threshold_for("noisy"), 0.35)
        self.assertEqual(vad_threshold_for("normal"), 0.20)

        far_params = calibrate_vad_parameters("far")
        self.assertEqual(far_params["threshold"], 0.12)
        self.assertEqual(far_params["speech_pad_ms"], 200)

        noisy_params = calibrate_vad_parameters("noisy")
        self.assertEqual(noisy_params["threshold"], 0.35)
        self.assertEqual(noisy_params["min_silence_duration_ms"], 350)

    def test_sustained_vowel_not_suppressed_by_vad(self):
        """Sustained vowel (>500ms, 8 frames) from 10ft away must remain active without noise floor climbing."""
        vad = AdaptiveVAD(min_speech_rms=0.0012)
        initial_floor = vad.noise_floor
        vowel_frame = np.full((1024, 1), 0.0050, dtype=np.float32)

        results = []
        for _ in range(8):  # 8 * 64ms = 512ms
            active, hangover = vad.update(vowel_frame, rms=0.0050)
            results.append((active, hangover))

        # All 8 frames must register as active speech
        self.assertTrue(all(r[0] for r in results))
        # Noise floor must not have climbed to swallow the vowel
        self.assertAlmostEqual(vad.noise_floor, initial_floor, places=4)

    def test_noisy_room_silence_detection(self):
        """In a noisy room with 0.0020 RMS fan drone, drone is detected as non-speech and speech is detected."""
        vad = AdaptiveVAD(min_speech_rms=0.0010)
        drone_frame = np.full((1024, 1), 0.0020, dtype=np.float32)

        # Feed 20 frames of stationary fan drone
        for _ in range(20):
            vad.update(drone_frame, rms=0.0020)

        # Fan drone should now be classified as non-speech
        active, hangover = vad.update(drone_frame, rms=0.0020)
        self.assertFalse(active)
        self.assertFalse(hangover)

        # Speech above the drone must be detected as active
        speech_frame = np.full((1024, 1), 0.0060, dtype=np.float32)
        is_speech, _ = vad.update(speech_frame, rms=0.0060)
        self.assertTrue(is_speech)


class TestAudioPersistence(unittest.TestCase):
    def test_save_wav_creates_valid_pcm16_file(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            tone = (0.5 * np.sin(np.linspace(0, 100, 16000))).astype(np.float32)
            AudioRecorder.save_wav(tone, tmp_path)

            self.assertTrue(os.path.exists(tmp_path))
            self.assertGreater(os.path.getsize(tmp_path), 44)

            with wave.open(tmp_path, "rb") as wf:
                self.assertEqual(wf.getnchannels(), 1)
                self.assertEqual(wf.getsampwidth(), 2)
                self.assertEqual(wf.getframerate(), 16000)
                self.assertEqual(wf.getnframes(), 16000)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


class TestAudioStreamLifecycle(unittest.TestCase):
    def test_stream_closed_and_freed_on_stop(self):
        from unittest.mock import MagicMock
        rec = AudioRecorder()
        mock_stream = MagicMock()
        mock_stream.active = True
        rec._stream = mock_stream
        rec._recording = True
        rec._level = 0.5
        rec._buffer = [np.full((1024, 1), 0.05, dtype=np.float32)]

        rec.stop()

        self.assertFalse(rec.is_recording)
        self.assertEqual(rec.level, 0.0)
        self.assertIsNone(rec._stream)
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()

    def test_stream_closed_and_freed_on_stop_and_take_open_chunk(self):
        from unittest.mock import MagicMock
        rec = AudioRecorder()
        mock_stream = MagicMock()
        mock_stream.active = True
        rec._stream = mock_stream
        rec._recording = True
        rec._buffer = [np.full((1024, 1), 0.05, dtype=np.float32)]

        rec.stop_and_take_open_chunk()

        self.assertFalse(rec.is_recording)
        self.assertIsNone(rec._stream)
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()

    def test_stream_closed_and_freed_on_cancel(self):
        from unittest.mock import MagicMock
        rec = AudioRecorder()
        mock_stream = MagicMock()
        mock_stream.active = True
        rec._stream = mock_stream
        rec._recording = True

        rec.cancel()

        self.assertFalse(rec.is_recording)
        self.assertIsNone(rec._stream)
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()

    def test_start_cleans_up_stale_stream_before_opening_new(self):
        from unittest.mock import MagicMock, patch
        rec = AudioRecorder()
        old_stream = MagicMock()
        rec._stream = old_stream

        new_stream = MagicMock()
        with patch("voice_flow.audio.sd.InputStream", return_value=new_stream):
            started = rec.start()

        self.assertTrue(started)
        old_stream.stop.assert_called_once()
        old_stream.close.assert_called_once()
        self.assertIs(rec._stream, new_stream)
        new_stream.start.assert_called_once()

        # When stopped, new_stream must be closed too
        rec.stop()
        new_stream.stop.assert_called_once()
        new_stream.close.assert_called_once()
        self.assertIsNone(rec._stream)


if __name__ == "__main__":
    unittest.main()


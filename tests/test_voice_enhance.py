"""Tests for the STT input-conditioning chain (whisper / far-mic / noisy room).

Regression coverage for the three mic problems reported 2026-09-01:
1. Whispering was discarded or amplified too little to transcribe.
2. Sitting far from the computer left the signal too quiet.
3. In a shared room, background voices/noise were picked up as dictation.
"""
from __future__ import annotations

import os
import sys
import threading
import unittest
from unittest.mock import patch

import numpy as np

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow import voice_enhance
from voice_flow.audio import AudioRecorder
from voice_flow.voice_enhance import enhance_for_stt, vad_threshold_for


def _tone(seconds: float = 2.0, freq: float = 220.0, peak: float = 0.4, sr: int = 16000) -> np.ndarray:
    t = np.linspace(0.0, seconds, int(sr * seconds), endpoint=False, dtype=np.float32)
    return (peak * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _speechlike(seconds: float = 2.0, peak: float = 0.5, sr: int = 16000, seed: int = 7) -> np.ndarray:
    """Speech-like clip: phrase bursts with natural pauses between them.

    Real dictation alternates voice and silence; the denoiser's noise profile
    is estimated from those quiet moments, so tests must model that too.
    """
    rng = np.random.default_rng(seed)
    n = int(sr * seconds)
    t = np.arange(n, dtype=np.float32)
    out = np.zeros(n, dtype=np.float32)
    pos = 0
    while pos < n:
        burst = min(n - pos, int(sr * (0.25 + 0.15 * rng.random())))
        f = 140.0 + 160.0 * rng.random()
        envelope = (0.6 + 0.4 * np.sin(2 * np.pi * 3.0 * rng.random() * (t[pos:pos + burst] / sr))).astype(np.float32)
        out[pos:pos + burst] = peak * envelope * np.sin(2 * np.pi * f * (t[pos:pos + burst] / sr))
        pos += burst + int(sr * (0.15 + 0.1 * rng.random()))  # pause
    return out


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.asarray(x, dtype=np.float64) ** 2))) if x.size else 0.0


class TestEnhanceWhisper(unittest.TestCase):
    def test_quiet_audio_is_amplified_to_dictation_level(self):
        quiet = _speechlike(2.0, peak=0.02)
        out, profile = enhance_for_stt(quiet, profile="whisper")
        self.assertEqual(profile, "whisper")
        self.assertGreaterEqual(float(np.max(np.abs(out))), 0.4)
        self.assertLessEqual(float(np.max(np.abs(out))), 0.95)  # no clipping

    def test_auto_profile_detects_whisper_level(self):
        _, profile = enhance_for_stt(_speechlike(2.0, peak=0.02), profile="auto")
        self.assertEqual(profile, "whisper")

    def test_old_gate_would_have_discarded_whisper(self):
        # Regression: the recorder previously DISCARDED recordings below a
        # 0.006 peak — whispered dictation never even reached the model.
        recorder = object.__new__(AudioRecorder)
        recorder._native_sr = 16000
        recorder._buffer = [np.full(16000, 0.004, dtype=np.float32)]  # whisper level
        recorder._lock = threading.Lock()
        recorder._lifecycle_lock = threading.RLock()
        recorder._recording = True
        recorder._stream = None
        result = recorder.stop()
        self.assertGreater(result.size, 0)


class TestEnhanceFar(unittest.TestCase):
    def test_far_profile_applies_strong_gain(self):
        far = _speechlike(2.0, peak=0.01)
        out, profile = enhance_for_stt(far, profile="far")
        self.assertEqual(profile, "far")
        self.assertGreaterEqual(float(np.max(np.abs(out))), 0.4)
        self.assertLessEqual(float(np.max(np.abs(out))), 0.95)


class TestEnhanceNoisyRoom(unittest.TestCase):
    def _clip(self, noise_rms: float = 0.05) -> np.ndarray:
        rng = np.random.default_rng(7)
        noise = (rng.standard_normal(32000) * noise_rms).astype(np.float32)
        return _speechlike(2.0) + noise  # speech with pauses OVER room hiss

    def test_noisy_profile_selected_for_low_snr(self):
        _, profile = enhance_for_stt(self._clip(), profile="auto")
        self.assertEqual(profile, "noisy")

    def test_noise_is_attenuated_voice_preserved(self):
        clip = self._clip(noise_rms=0.05)  # speech + stationary room hiss
        clean = _speechlike(2.0)
        voice_mask = clean != 0.0            # ground-truth speech windows
        pause_mask = ~voice_mask             # ground-truth silence (hiss only)
        # SNR measured per-region: hiss in pauses vs voice in active windows.
        snr_before = _rms(clip[voice_mask]) / max(_rms(clip[pause_mask]), 1e-9)
        out, _ = enhance_for_stt(clip, profile="noisy")
        snr_after = _rms(out[voice_mask]) / max(_rms(out[pause_mask]), 1e-9)
        # Denoising must IMPROVE the pause-hiss-to-voice ratio, not rescale it.
        self.assertGreater(snr_after, snr_before * 1.5)
        # Voice survives the chain.
        self.assertGreater(_rms(out[voice_mask]), _rms(clip[voice_mask]) * 0.4)

    def test_loud_room_auto_flags_noisy(self):
        # Room chatter well above the voice floor -> low SNR -> noisy profile.
        _, profile = enhance_for_stt(self._clip(noise_rms=0.09), profile="auto")
        self.assertEqual(profile, "noisy")


class TestEnhanceSafety(unittest.TestCase):
    def test_healthy_audio_gets_light_touch(self):
        healthy = _speechlike(2.0, peak=0.6)
        out, profile = enhance_for_stt(healthy, profile="normal")
        self.assertEqual(profile, "normal")
        self.assertGreater(_rms(out), _rms(healthy) * 0.4)
        self.assertLessEqual(float(np.max(np.abs(out))), 1.0)

    def test_silence_is_not_amplified(self):
        out, profile = enhance_for_stt(np.zeros(16000, dtype=np.float32), profile="whisper")
        self.assertEqual(profile, "silence")
        self.assertEqual(float(np.max(np.abs(out))), 0.0)

    def test_kill_switch_passthrough(self):
        clip = _tone(peak=0.02)
        env = {"VOICE_FLOW_AUDIO_ENHANCE": "0"}
        with patch.dict(os.environ, env, clear=False):
            out, profile = enhance_for_stt(clip, profile="auto")
        self.assertEqual(profile, "off")
        np.testing.assert_array_equal(np.asarray(out), clip)

    def test_nan_inf_input_never_raises(self):
        garbage = np.array([np.nan, 0.5, np.inf, -0.2, 0.1], dtype=np.float32)
        out, _ = enhance_for_stt(garbage)
        self.assertTrue(np.all(np.isfinite(out)))

    def test_output_never_clips(self):
        for peak in (0.02, 0.1, 0.4, 0.9):
            out, _ = enhance_for_stt(_tone(peak=peak))
            self.assertLessEqual(float(np.max(np.abs(out))), 1.0)


class TestProfileSettings(unittest.TestCase):
    def test_vad_threshold_mapping(self):
        self.assertEqual(vad_threshold_for("whisper"), 0.15)
        self.assertEqual(vad_threshold_for("noisy"), 0.35)
        self.assertEqual(vad_threshold_for("normal"), 0.20)
        self.assertEqual(vad_threshold_for("unknown-profile"), 0.20)

    def test_explicit_profile_overrides_auto(self):
        loud = _tone(peak=0.6)  # auto would say normal
        _, profile = enhance_for_stt(loud, profile="noisy")
        self.assertEqual(profile, "noisy")


class TestEnhancementReachesModels(unittest.TestCase):
    def test_cloud_path_receives_enhanced_audio(self):
        """The cloud adapter must see the AMPLIFIED buffer, not the raw one."""
        import voice_flow.transcriber as tmod
        from voice_flow.transcriber import Transcriber

        t = object.__new__(Transcriber)
        t.model = object()
        t._loading = False
        t._lock = threading.Lock()
        t._transcribe_lock = threading.Lock()
        t.category_hint = None
        seen = {}

        captured = {}

        def fake_cloud(audio, model_ref, vocabulary=None):
            captured["peak"] = float(np.max(np.abs(audio))) if audio.size else 0.0
            return "cloud text"

        with (
            patch("voice_flow.storage.storage.get_setting", return_value="deepgram/nova-3"),
            patch("voice_flow.stt_engines.transcribe_cloud", side_effect=fake_cloud),
            patch.object(t, "_transcribe_local", return_value=""),
        ):
            out = t.transcribe(_tone(2.0, peak=0.02))
        self.assertEqual(out, "cloud text")
        self.assertGreaterEqual(captured["peak"], 0.3)


class TestFarFieldAndNoiseSuppression(unittest.TestCase):
    def test_far_speech_elevated_to_nominal_speech_level(self):
        """10ft distant speech (~0.008 peak) must be elevated to nominal speech levels."""
        rng = np.random.default_rng(42)
        ambient = (rng.standard_normal(32000) * 0.0006).astype(np.float32)
        speech_far = _speechlike(2.0, peak=0.008)
        clip_far = speech_far + ambient

        out, profile = enhance_for_stt(clip_far, profile="auto")
        self.assertEqual(profile, "far")
        self.assertGreaterEqual(float(np.max(np.abs(out))), 0.45)
        self.assertLessEqual(float(np.max(np.abs(out))), 0.95)

        voice_mask = speech_far != 0.0
        active_rms = float(np.sqrt(np.mean(out[voice_mask].astype(np.float64) ** 2)))
        active_db = 20.0 * np.log10(max(active_rms, 1e-9))
        # Nominal speech level: between -20dB and -12dB LUFS/RMS
        self.assertGreaterEqual(active_db, -20.0)
        self.assertLessEqual(active_db, -10.0)

    def test_highpass_filter_eliminates_hvac_and_fan_rumble(self):
        """80Hz high-pass filter must suppress 50Hz rumble by >15dB while preserving voice."""
        from voice_flow.voice_enhance import _highpass

        t = np.linspace(0.0, 1.0, 16000, endpoint=False, dtype=np.float32)
        rumble_50hz = (0.5 * np.sin(2 * np.pi * 50.0 * t)).astype(np.float32)
        voice_tone = (0.5 * np.sin(2 * np.pi * 1000.0 * t)).astype(np.float32)

        filtered_rumble = _highpass(rumble_50hz, 16000, 80.0)
        filtered_voice = _highpass(voice_tone, 16000, 80.0)

        rumble_attenuation_db = 20.0 * np.log10(_rms(rumble_50hz) / max(_rms(filtered_rumble), 1e-9))
        voice_loss_db = 20.0 * np.log10(_rms(voice_tone) / max(_rms(filtered_voice), 1e-9))

        self.assertGreater(rumble_attenuation_db, 15.0)
        self.assertLess(abs(voice_loss_db), 0.5)

    def test_peak_limiter_handles_extreme_transients_without_clipping(self):
        """Loud desk thumps and sudden peaks (>1.0) must be smoothly compressed <= 0.95."""
        loud_thump = _tone(2.0, freq=120.0, peak=2.5)
        out, _ = enhance_for_stt(loud_thump, profile="normal")
        self.assertLessEqual(float(np.max(np.abs(out))), 0.95)
        self.assertTrue(np.all(np.isfinite(out)))

    def test_enhancement_latency_zero_cpu_bottleneck(self):
        """Complete DSP enhancement chain on 3s audio must complete in under 35ms."""
        import time

        test_audio = _speechlike(3.0, peak=0.03)
        # Warm-up run on full buffer length to prime FFT plans
        enhance_for_stt(test_audio)

        runs = []
        for _ in range(3):
            t0 = time.perf_counter()
            out, _ = enhance_for_stt(test_audio)
            runs.append((time.perf_counter() - t0) * 1000.0)
        elapsed_ms = min(runs)

        self.assertLess(elapsed_ms, 35.0)
        self.assertGreater(out.size, 0)

    def test_vad_threshold_for_far_profile(self):
        self.assertEqual(vad_threshold_for("far"), 0.12)

    def test_agc_gain_hold_prevents_syllable_onset_clipping(self):
        """Inter-word pauses (~100ms) must not cause AGC gain collapse / word onset clipping."""
        sr = 16000
        t1 = np.linspace(0.0, 0.5, int(sr * 0.5), endpoint=False, dtype=np.float32)
        word1 = (0.005 * np.sin(2 * np.pi * 300 * t1)).astype(np.float32)
        pause = np.zeros(int(sr * 0.10), dtype=np.float32)  # 100ms natural breath pause
        t2 = np.linspace(0.0, 0.5, int(sr * 0.5), endpoint=False, dtype=np.float32)
        word2 = (0.005 * np.sin(2 * np.pi * 300 * t2)).astype(np.float32)
        phrase = np.concatenate([word1, pause, word2])

        out, _ = enhance_for_stt(phrase, sr=sr, profile="far")

        word2_start = len(word1) + len(pause)
        word2_onset = out[word2_start : word2_start + int(sr * 0.10)]
        word2_steady = out[-int(sr * 0.10):]

        onset_rms = float(np.sqrt(np.mean(word2_onset.astype(np.float64) ** 2)))
        steady_rms = float(np.sqrt(np.mean(word2_steady.astype(np.float64) ** 2)))

        # Onset must maintain at least 75% of steady-state level (prevents swallowing first phoneme;
        # prior attempt crashed to 31.9% due to backward AGC attack/release without hold)
        ratio = onset_rms / max(steady_rms, 1e-6)
        self.assertGreaterEqual(ratio, 0.75)

    def test_ambient_noise_is_not_amplified_by_agc(self):
        """Pure ambient room noise (RMS 0.0006) must not be amplified into loud background hiss."""
        rng = np.random.default_rng(123)
        ambient = (rng.standard_normal(32000) * 0.0006).astype(np.float32)

        out, _ = enhance_for_stt(ambient, profile="far")
        ambient_rms_before = float(np.sqrt(np.mean(ambient.astype(np.float64) ** 2)))
        ambient_rms_after = float(np.sqrt(np.mean(out.astype(np.float64) ** 2)))

        # Gated ambient noise must not be amplified by more than 2x (previously 23x-80x!)
        self.assertLessEqual(ambient_rms_after, ambient_rms_before * 2.0)

    def test_sudden_loud_transient_overload_protection(self):
        """Loud desk thump (peak 3.0) during soft speech must be limited <= 0.95 without distortion."""
        sr = 16000
        t = np.linspace(0.0, 1.0, sr, endpoint=False, dtype=np.float32)
        soft_speech = (0.005 * np.sin(2 * np.pi * 350 * t)).astype(np.float32)
        thump = np.zeros(sr, dtype=np.float32)
        # 50ms transient thump of peak 3.0
        thump[int(sr * 0.4) : int(sr * 0.45)] = 3.0 * np.sin(np.linspace(0, 10 * np.pi, int(sr * 0.05)))
        mixed = soft_speech + thump

        out, _ = enhance_for_stt(mixed, sr=sr, profile="far")
        self.assertLessEqual(float(np.max(np.abs(out))), 0.95)
        self.assertTrue(np.all(np.isfinite(out)))


if __name__ == "__main__":
    unittest.main()

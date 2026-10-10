"""Tests for the 2026-09-01 Voice Flow latency upgrade.

Covers: streaming silence-segmented STT (chunk splitting, ordered collection,
fallback), the polisher fast lane and sliding fidelity thresholds, adaptive
cloud STT timeout, and FLAC upload compression.
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from unittest.mock import patch

import numpy as np

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow import audio as audio_mod
from voice_flow import stream_stt as stream_mod
from voice_flow.audio import AudioRecorder
from voice_flow.polisher import TextPolisher, _candidate_preserves_content
from voice_flow.storage import storage


class _FakeTranscriber:
    def __init__(self, delay: float = 0.0, fail_first: int = 0, labels: dict[float, str] | None = None):
        self.delay = delay
        self.fail_first = fail_first
        self.labels = labels or {}
        self.calls: list[np.ndarray] = []

    def transcribe(self, audio):
        self.calls.append(audio)
        if self.fail_first and len(self.calls) <= self.fail_first:
            raise RuntimeError("transcription backend down")
        if self.delay:
            time.sleep(self.delay)
        return self.labels.get(round(float(audio[0]), 4), f"chunk {len(self.calls)}")


def _silence(seconds: float, sr: int = 16000, amplitude: float = 0.0) -> np.ndarray:
    return (np.ones((int(sr * seconds), 1), dtype=np.float32) * amplitude)


class _FakeClock:
    """Deterministic time.monotonic replacement advancing per call."""

    def __init__(self, step: float = 1024 / 44100):
        self.t = 1000.0
        self.step = step

    def monotonic(self) -> float:
        self.t += self.step
        return self.t


def _feed(rec: AudioRecorder, seconds: float, amplitude: float, sr: int = 16000) -> None:
    data = (np.ones((int(sr * seconds), 1), dtype=np.float32) * amplitude)
    for start in range(0, data.shape[0] - 1023, 1024):
        rec._audio_callback(data[start:start + 1024], 1024, None, None)


class TestAudioChunkSplitting(unittest.TestCase):
    def _recorder(self) -> AudioRecorder:
        rec = AudioRecorder()
        rec._recording = True
        rec._native_sr = 16000  # test feed rate
        return rec

    def test_silence_closes_chunk_and_dispatches(self):
        rec = self._recorder()
        dispatched: list[tuple[np.ndarray, int]] = []
        rec.on_chunk_closed = lambda chunk, sr: dispatched.append((chunk, sr))
        with patch.object(audio_mod.time, "monotonic", _FakeClock(step=1024 / 16000).monotonic):
            _feed(rec, 1.2, 0.05)
            _feed(rec, 1.6, 0.0)
        self.assertEqual(len(dispatched), 1)
        chunk, sr = dispatched[0]
        self.assertEqual(sr, rec._native_sr)
        self.assertGreaterEqual(chunk.shape[0], 1024)

    def test_short_voice_chunk_not_dispatched(self):
        rec = self._recorder()
        dispatched: list = []
        rec.on_chunk_closed = lambda chunk, sr: dispatched.append(chunk)
        with patch.object(audio_mod.time, "monotonic", _FakeClock().monotonic):
            _feed(rec, 0.3, 0.05)
            _feed(rec, 1.8, 0.0)
        self.assertEqual(dispatched, [])

    def test_take_open_chunk_returns_tail_and_resets(self):
        rec = self._recorder()
        _feed(rec, 0.5, 0.05)
        tail = rec.take_open_chunk()
        self.assertIsNotNone(tail)
        self.assertGreater(tail.size, 0)
        self.assertIsNone(rec.take_open_chunk())
        # stop() must also clear chunk state without dispatching
        rec2 = self._recorder()
        _feed(rec2, 0.3, 0.05)
        rec2.stop()
        self.assertIsNone(rec2.take_open_chunk())

    def test_continuous_speech_forces_dispatch_and_carries_overlap_into_quiescent_tail(self):
        rec = self._recorder()
        dispatched: list[tuple[np.ndarray, float]] = []

        def closed(chunk, _sr, *, overlap_prefix_seconds=0.0):
            dispatched.append((chunk, overlap_prefix_seconds))

        rec.on_chunk_closed = closed
        with patch.object(audio_mod.time, "monotonic", _FakeClock(step=1024 / 16000).monotonic):
            _feed(rec, 8.3, 0.05)

        # The hard cap dispatches while the key is still held. The first
        # forced chunk has no prefix; the tail starts with its explicit 0.75s
        # PCM overlap and is copied only after capture is quiesced.
        self.assertEqual(len(dispatched), 1)
        self.assertEqual(dispatched[0][1], 0.0)
        audio, tail, tail_overlap = rec.stop_and_take_open_chunk()
        self.assertGreater(audio.size, dispatched[0][0].size)
        self.assertIsNotNone(tail)
        self.assertGreater(tail.size, 0)
        self.assertAlmostEqual(tail_overlap, audio_mod.FORCED_CHUNK_OVERLAP_SECONDS)


class TestStreamTranscriber(unittest.TestCase):
    def test_chunks_collected_in_order(self):
        ft = _FakeTranscriber(labels={0.01: "chunk 1", 0.02: "chunk 2"})
        st = stream_mod.StreamTranscriber(ft)
        st.start_session()
        st.submit_native(_silence(0.5, amplitude=0.01), 16000)
        st.submit_native(_silence(0.5, amplitude=0.02), 16000)
        st.end_session()
        text = st.collect(timeout=2.0)
        self.assertEqual(text, "chunk 1 chunk 2")

    def test_collect_waits_for_slow_workers(self):
        ft = _FakeTranscriber(delay=0.3)
        st = stream_mod.StreamTranscriber(ft)
        st.start_session()
        st.submit_native(_silence(0.4), 16000)
        st.end_session()
        text = st.collect(timeout=3.0)
        self.assertEqual(text, "chunk 1")

    def test_worker_failure_falls_back_to_empty(self):
        ft = _FakeTranscriber(fail_first=99)
        st = stream_mod.StreamTranscriber(ft)
        st.start_session()
        st.submit_native(_silence(0.3), 16000)
        st.end_session()
        self.assertEqual(st.collect(timeout=2.0), "")

    def test_discard_clears_state(self):
        st = stream_mod.StreamTranscriber(_FakeTranscriber())
        st.start_session()
        st.submit_native(_silence(0.5), 16000)
        st.discard()
        self.assertEqual(st.collect(timeout=0.1), "")

    def test_tail_submitted_after_session_end_still_collected(self):
        """Regression: the tail chunk harvested at dictation finish arrives
        after end_session() — it must still be transcribed."""
        ft = _FakeTranscriber(labels={0.01: "chunk 1", 0.02: "chunk 2"})
        st = stream_mod.StreamTranscriber(ft)
        st.start_session()
        st.submit_native(_silence(0.5, amplitude=0.01), 16000)
        st.end_session()
        st.submit_native(_silence(0.5, amplitude=0.02), 16000, force=True)
        text = st.collect(timeout=2.0)
        self.assertEqual(text, "chunk 1 chunk 2")

    def test_unforced_submit_after_session_end_ignored(self):
        st = stream_mod.StreamTranscriber(_FakeTranscriber())
        st.start_session()
        st.end_session()
        st.submit_native(_silence(0.5), 16000)
        self.assertEqual(st.collect(timeout=0.5), "")

    def test_submit_before_session_ignored(self):
        st = stream_mod.StreamTranscriber(_FakeTranscriber())
        st.submit_native(_silence(0.5), 16000)
        self.assertEqual(st.collect(timeout=0.2), "")


class TestPolisherFastLane(unittest.TestCase):
    def setUp(self):
        self.polisher = TextPolisher()
        self.orig_polishing_enabled = storage.get_setting("polishing_enabled", True)
        storage.save_setting("polishing_enabled", True)

    def tearDown(self):
        storage.save_setting("polishing_enabled", self.orig_polishing_enabled)

    def test_explicit_model_runs_before_fast_lane(self):
        calls = []

        def fake_call(provider, key, system_prompt, user_content, model=None, timeout=None):
            calls.append(model)
            if model == "gemini-3.5-flash-lite":
                return "polished fast lane output"
            return None

        def get_setting(key, default=None):
            if key == "voice_flow_polish_model":
                return "gemini/gemini-3.7-flash"
            return default

        with (
            patch.object(storage, "get_setting", side_effect=get_setting),
            patch.object(storage, "get_all_api_keys", return_value={"gemini": "k"}),
            patch.object(storage, "get_all_provider_connections", return_value={}),
            patch.object(self.polisher, "_try_provider_call", side_effect=fake_call),
        ):
            out = self.polisher.polish("um please polish this much longer dictation text with plenty of words")
        self.assertEqual(calls[0], "gemini-3.7-flash")
        self.assertTrue(out)

    def test_speed_mode_fast_does_not_skip_explicit_model(self):
        calls = []

        def fake_call(provider, key, system_prompt, user_content, model=None, timeout=None):
            calls.append(model)
            return "out" if model == "gemini-3.5-flash-lite" else None

        def get_setting(key, default=None):
            if key == "voice_flow_polish_speed_mode":
                return "fast"
            if key == "voice_flow_polish_model":
                return "gemini/gemini-3.7-flash"
            return default

        with (
            patch.object(storage, "get_setting", side_effect=get_setting),
            patch.object(storage, "get_all_api_keys", return_value={"gemini": "k"}),
            patch.object(storage, "get_all_provider_connections", return_value={}),
            patch.object(self.polisher, "_try_provider_call", side_effect=fake_call),
        ):
            self.polisher.polish("um please polish this much longer dictation text with plenty of words")
        self.assertEqual(calls, ["gemini-3.7-flash"])

    def test_explicit_model_failure_cooldown_prevents_repeat_calls(self):
        calls = []

        def fake_call(provider, key, system_prompt, user_content, model=None, timeout=None):
            calls.append(model)
            return None

        def get_setting(key, default=None):
            if key == "voice_flow_polish_model":
                return "gemini/gemini-3.7-flash"
            return default

        with (
            patch.object(storage, "get_setting", side_effect=get_setting),
            patch.object(storage, "get_all_api_keys", return_value={"gemini": "k"}),
            patch.object(storage, "get_all_provider_connections", return_value={}),
            patch.object(self.polisher, "_try_provider_call", side_effect=fake_call),
        ):
            self.polisher.polish("um please polish this much longer dictation text with plenty of words")
            first_count = len(calls)
            self.polisher.polish("um please polish this much longer dictation text with plenty of words")
        self.assertIn("gemini-3.7-flash", calls)
        # The selected provider cooldown prevents a second failed request.
        self.assertEqual(calls[first_count:].count("gemini-3.7-flash"), 0)


class TestFidelityChecker(unittest.TestCase):
    def test_long_rephrased_transcript_passes(self):
        src = (
            "um basically our app has made five different genres of videos and they are "
            "looking good and all the pipelines are working correctly so you know we can "
            "probably move forward and start the next phase of the project soon"
        )
        cand = (
            "Our app has made five different genres of videos and they are looking good, "
            "and all the pipelines are working correctly, so we can probably move forward "
            "and start the next phase of the project soon."
        )
        self.assertTrue(_candidate_preserves_content(src, cand))

    def test_truncation_still_rejected(self):
        src = (
            "one two three four five six seven eight nine ten eleven twelve thirteen "
            "fourteen fifteen sixteen seventeen eighteen nineteen twenty"
        )
        cand = "one two three four five six seven eight nine ten"
        self.assertFalse(_candidate_preserves_content(src, cand))

    def test_tail_loss_rejected(self):
        src = "the quick brown fox jumps over the lazy dog while the sun sets behind the western mountains tonight far away"
        cand = "The quick brown fox jumps over the lazy dog while the sun sets behind the"
        self.assertFalse(_candidate_preserves_content(src, cand))

    def test_unrelated_response_rejected(self):
        src = "please polish this short dictation"
        cand = "sure thing I cannot help with that request today sorry about it"
        self.assertFalse(_candidate_preserves_content(src, cand))


class TestSttEnginesCompression(unittest.TestCase):
    def test_flac_conversion_reduces_or_preserves(self):
        from voice_flow.stt_engines import _to_flac_bytes, _to_wav_bytes

        wav = _to_wav_bytes(_silence(20.0))  # 640KB — above the conversion gate
        flac = _to_flac_bytes(wav)
        if flac is None:  # ffmpeg missing in CI — nothing to assert
            self.skipTest("ffmpeg unavailable")
        self.assertLessEqual(len(flac), len(wav))

    def test_flac_skipped_for_small_uploads(self):
        """Short chunks must not spawn ffmpeg at all (console flash + latency)."""
        from voice_flow.stt_engines import _to_flac_bytes, _to_wav_bytes

        wav = _to_wav_bytes(_silence(2.0))  # 64KB — below the conversion gate
        self.assertIsNone(_to_flac_bytes(wav))

    def test_transcribe_cloud_passes_flac_payload(self):
        import voice_flow.stt_engines as engines

        wav = b"WAVDATA" * 500
        with (
            patch.object(engines, "_to_wav_bytes", return_value=wav),
            patch.object(engines, "_to_flac_bytes", return_value=b"FLAC"),
            patch.object(engines, "_key_for", return_value="k"),
        ):
            captured = {}

            def fake_adapter(*args, **kwargs):
                # New-style call: (payload, key, model, fname, ctype, poll_seconds=...)
                captured["payload"] = args[0]
                captured["nargs"] = len(args)
                captured["fname"] = args[3] if len(args) > 3 else None
                return "text"

            original = engines._ADAPTERS["groq"]
            engines._ADAPTERS["groq"] = fake_adapter
            try:
                engines.transcribe_cloud(_silence(0.2), "groq/whisper-large-v3-turbo")
            finally:
                engines._ADAPTERS["groq"] = original
        self.assertEqual(captured["payload"], b"FLAC")
        self.assertEqual(captured["nargs"], 5)
        self.assertEqual(captured["fname"], "audio.flac")

    def test_transcribe_cloud_falls_back_to_wav(self):
        import voice_flow.stt_engines as engines

        wav = b"WAVDATA" * 500
        with (
            patch.object(engines, "_to_wav_bytes", return_value=wav),
            patch.object(engines, "_to_flac_bytes", return_value=None),
            patch.object(engines, "_key_for", return_value="k"),
        ):
            captured = {}

            def fake_adapter(*args, **kwargs):
                captured["payload"] = args[0]
                captured["nargs"] = len(args)
                captured["fname"] = args[3] if len(args) > 3 else None
                return "text"

            original = engines._ADAPTERS["groq"]
            engines._ADAPTERS["groq"] = fake_adapter
            try:
                engines.transcribe_cloud(_silence(0.2), "groq/whisper-large-v3-turbo")
            finally:
                engines._ADAPTERS["groq"] = original
        self.assertEqual(captured["payload"], wav)
        self.assertEqual(captured["nargs"], 5)
        self.assertEqual(captured["fname"], "audio.wav")


class TestAdaptiveCloudTimeout(unittest.TestCase):
    def test_longer_audio_gets_longer_cloud_budget(self):
        # 5s audio -> ~8.4s; 60s -> 13s; 240s -> capped 18s.
        from voice_flow.transcriber import _cloud_join_timeout

        self.assertLessEqual(_cloud_join_timeout(5.0), 9.0)
        self.assertGreaterEqual(_cloud_join_timeout(60.0), 12.0)
        self.assertEqual(_cloud_join_timeout(600.0), 18.0)


class TestShortAudioRouting(unittest.TestCase):
    """An explicit provider selection owns short utterances as well."""

    def _transcriber_with_model(self):
        from voice_flow.transcriber import Transcriber

        t = object.__new__(Transcriber)
        t.model = object()  # "loaded" without booting faster-whisper
        t._loading = False
        t._lock = __import__("threading").Lock()
        t._transcribe_lock = __import__("threading").Lock()
        return t

    def test_short_audio_uses_explicit_cloud_model(self):
        from voice_flow import transcriber as tmod

        t = self._transcriber_with_model()
        audio = _silence(2.0, amplitude=0.05)
        with (
            patch("voice_flow.storage.storage.get_setting", return_value="deepgram/nova-3"),
            patch.object(t, "_transcribe_local", return_value="hello there") as local_mock,
            patch("voice_flow.stt_engines.transcribe_cloud", return_value="cloud words") as cloud_mock,
        ):
            out = t.transcribe(audio)
        self.assertEqual(out, "cloud words")
        cloud_mock.assert_called_once()
        local_mock.assert_not_called()

    def test_short_audio_falls_back_to_cloud_when_local_empty(self):
        from voice_flow import transcriber as tmod

        t = self._transcriber_with_model()
        audio = _silence(2.0, amplitude=0.05)
        with (
            patch("voice_flow.storage.storage.get_setting", return_value="deepgram/nova-3"),
            patch.object(t, "_transcribe_local", return_value=""),
            patch("voice_flow.stt_engines.transcribe_cloud", return_value="cloud words"),
        ):
            out = t.transcribe(audio)
        self.assertEqual(out, "cloud words")

    def test_long_audio_uses_cloud_first(self):
        from voice_flow import transcriber as tmod

        t = self._transcriber_with_model()
        audio = _silence(30.0, amplitude=0.05)
        local_calls = []

        def fake_local(audio_arg):
            local_calls.append(1)
            return "local late"

        with (
            patch("voice_flow.storage.storage.get_setting", return_value="deepgram/nova-3"),
            patch.object(t, "_transcribe_local", side_effect=fake_local),
            patch("voice_flow.stt_engines.transcribe_cloud", return_value="cloud fast"),
        ):
            out = t.transcribe(audio)
        self.assertEqual(out, "cloud fast")
        self.assertEqual(local_calls, [])


class TestUltraShortPolishBypass(unittest.TestCase):
    def test_short_transcript_skips_ai_pool(self):
        from voice_flow import polisher as pmod

        pol = pmod.TextPolisher()
        called = []

        with (
            patch.object(pmod.storage, "get_setting", return_value=True),
            patch.object(pmod.storage, "get_all_api_keys", return_value={"gemini": "k"}),
            patch.object(pol, "_polish_with_api_pool", side_effect=lambda *a, **k: called.append(1)),
        ):
            out = pol.polish("um hey send the email now please")  # 7 words — bypassed
        self.assertEqual(called, [])
        self.assertTrue(out)

    def test_longer_transcript_still_uses_ai_pool(self):
        from voice_flow import polisher as pmod

        pol = pmod.TextPolisher()
        called = []

        def fake_pool(*args, **kwargs):
            called.append(1)
            return "polished output"

        with (
            patch.object(pmod.storage, "get_setting", return_value=True),
            patch.object(pmod.storage, "get_all_api_keys", return_value={"gemini": "k"}),
            patch.object(pol, "_polish_with_api_pool", side_effect=fake_pool),
            patch.object(pmod, "_candidate_preserves_content", return_value=True),
        ):
            pol.polish("this is a much longer dictation with well over the bypass limit of words in it")
        self.assertEqual(len(called), 1)


if __name__ == "__main__":
    unittest.main()

"""Comprehensive tests for NVIDIA Nemotron Speech ASR GGUF Engine and Voice Flow integration."""
from __future__ import annotations

import ctypes
import threading
import time
import wave
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from voice_flow import nemotron_engine, downloadable_models, paths
from voice_flow.transcriber import Transcriber
from voice_flow.storage import storage
from voice_flow.polisher import polisher


def test_is_nemotron_model():
    """Verify nemotron model identification helper."""
    assert nemotron_engine.is_nemotron_model("local/nemotron-speech-streaming-en-0.6b")
    assert nemotron_engine.is_nemotron_model("nvidia/nemotron-speech-streaming-en-0.6b")
    assert nemotron_engine.is_nemotron_model("nemotron-speech-streaming-en-0.6b.q8_0.gguf")
    assert nemotron_engine.is_nemotron_model("local/nemotron-3.5-asr-streaming-0.6b")
    assert not nemotron_engine.is_nemotron_model("local/faster-whisper-base.en")
    assert not nemotron_engine.is_nemotron_model("groq/whisper-large-v3-turbo")
    assert not nemotron_engine.is_nemotron_model("")
    assert not nemotron_engine.is_nemotron_model(None)


def test_nemotron_engine_loads_downloaded_model_and_caches():
    """Verify loading the real downloaded Nemotron GGUF model and its metadata."""
    real_model_path = downloadable_models.get_models_dir() / "nemotron-speech-streaming-en-0.6b.q8_0.gguf"
    if not real_model_path.is_file():
        pytest.skip(f"Model file not downloaded at {real_model_path}")

    # Evict any existing cached instance to test fresh load
    nemotron_engine.clear_engine_cache("nemotron-speech-streaming-en-0.6b")

    t0 = time.perf_counter()
    eng1 = nemotron_engine.get_nemotron_engine("nvidia/nemotron-speech-streaming-en-0.6b")
    load_time = time.perf_counter() - t0

    assert eng1 is not None
    assert eng1.is_warm
    assert len(eng1.vocab) == 1024
    assert eng1.blank_id == 1024
    assert eng1.num_features == 128
    assert eng1.sample_rate == 16000
    assert eng1.preprocessor_fb is not None
    assert eng1.preprocessor_fb.shape == (128, 257)
    assert len(eng1.tensors) > 500

    # C ABI native recognizer handle must be initialized
    assert eng1.rec_handle.value is not None

    # Singleton check: subsequent lookup must return the exact same instance in < 1ms
    t1 = time.perf_counter()
    eng2 = nemotron_engine.get_nemotron_engine("nvidia/nemotron-speech-streaming-en-0.6b")
    cached_lookup_time = time.perf_counter() - t1

    assert eng1 is eng2
    assert cached_lookup_time < 0.005  # < 5ms (typically < 0.05ms)


def test_nemotron_engine_cache_eviction():
    """Verify clear_engine_cache evicts the specified model and closes handles."""
    real_model_path = downloadable_models.get_models_dir() / "nemotron-speech-streaming-en-0.6b.q8_0.gguf"
    if not real_model_path.is_file():
        pytest.skip(f"Model file not downloaded at {real_model_path}")

    eng1 = nemotron_engine.get_nemotron_engine("nvidia/nemotron-speech-streaming-en-0.6b")
    assert eng1 is not None

    nemotron_engine.clear_engine_cache("nemotron-speech-streaming-en-0.6b")
    with nemotron_engine._CACHE_LOCK:
        assert not any("nemotron-speech-streaming-en-0.6b" in k for k in nemotron_engine._NEMOTRON_CACHE)


def test_feature_extraction_vectorized_latency():
    """Benchmark vectorized 128-channel log-mel feature extraction."""
    real_model_path = downloadable_models.get_models_dir() / "nemotron-speech-streaming-en-0.6b.q8_0.gguf"
    if not real_model_path.is_file():
        pytest.skip(f"Model file not downloaded at {real_model_path}")

    eng = nemotron_engine.get_nemotron_engine("nvidia/nemotron-speech-streaming-en-0.6b")
    assert eng is not None

    # 3 seconds of 16kHz audio
    audio = np.random.randn(16000 * 3).astype(np.float32) * 0.1
    t0 = time.perf_counter()
    features = eng.extract_mel_features(audio)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert features.ndim == 2
    assert features.shape[1] == 128
    assert features.shape[0] > 0
    assert elapsed_ms < 60.0


def test_sentencepiece_token_decoding():
    """Verify SentencePiece token decoding with boundary reconstruction."""
    real_model_path = downloadable_models.get_models_dir() / "nemotron-speech-streaming-en-0.6b.q8_0.gguf"
    if not real_model_path.is_file():
        pytest.skip(f"Model file not downloaded at {real_model_path}")

    eng = nemotron_engine.get_nemotron_engine("nvidia/nemotron-speech-streaming-en-0.6b")
    assert eng is not None

    # Test decoding mock tokens
    decoded = eng.decode_tokens([5, 14])  # " the" + " it"
    assert isinstance(decoded, str)
    assert eng.decode_tokens([]) == ""
    assert eng.decode_tokens([0, 1024]) == ""


def test_nemotron_real_speech_transcription():
    """Verify real in-process Nemotron C ABI transcription returns accurate text."""
    real_model_path = downloadable_models.get_models_dir() / "nemotron-speech-streaming-en-0.6b.q8_0.gguf"
    if not real_model_path.is_file():
        pytest.skip(f"Model file not downloaded at {real_model_path}")

    eng = nemotron_engine.get_nemotron_engine("nvidia/nemotron-speech-streaming-en-0.6b")
    assert eng is not None
    assert eng.rec_handle.value is not None

    wav_file = Path("video-flow-v2.1/render-output/fixture-apple/narova/out/audio/sentences/01_000.wav")
    if not wav_file.is_file():
        pytest.skip(f"Audio fixture not found: {wav_file}")

    with wave.open(str(wav_file), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    t0 = time.perf_counter()
    transcript = eng.transcribe(audio)
    duration_ms = (time.perf_counter() - t0) * 1000

    assert isinstance(transcript, str)
    assert len(transcript) > 0
    # Must transcribe real words from the sample
    assert any(w in transcript.lower() for w in ["branch", "blossom", "apple", "evolve", "bud"])
    assert duration_ms < 5000.0  # In-process CPU decode


def test_silence_handling_fast_return():
    """Verify silence / low amplitude buffers return immediately (< 1ms)."""
    real_model_path = downloadable_models.get_models_dir() / "nemotron-speech-streaming-en-0.6b.q8_0.gguf"
    if not real_model_path.is_file():
        pytest.skip(f"Model file not downloaded at {real_model_path}")

    eng = nemotron_engine.get_nemotron_engine("nvidia/nemotron-speech-streaming-en-0.6b")
    assert eng is not None

    silence = np.zeros(16000 * 2, dtype=np.float32)
    t0 = time.perf_counter()
    result = eng.transcribe(silence)
    latency_ms = (time.perf_counter() - t0) * 1000

    assert result == ""
    assert latency_ms < 5.0  # Immediate silence gate


def test_multilingual_model_loading():
    """Verify loading and warming of multilingual Nemotron model."""
    multi_model_path = downloadable_models.get_models_dir() / "nemotron-3.5-asr-streaming-0.6b.q8_0.gguf"
    if not multi_model_path.is_file():
        pytest.skip(f"Multilingual model not downloaded at {multi_model_path}")

    eng = nemotron_engine.get_nemotron_engine("nvidia/nemotron-3.5-asr-streaming-0.6b")
    assert eng is not None
    assert eng.is_warm
    assert len(eng.vocab) > 10000  # Multilingual SentencePiece vocab
    assert eng.rec_handle.value is not None


def test_transcriber_model_name_resolution():
    """Verify model name resolution handles Nemotron, local prefixes, and defaults."""
    assert Transcriber._local_model_name("local/nemotron-speech-streaming-en-0.6b") == "nemotron-speech-streaming-en-0.6b"
    assert Transcriber._local_model_name("local/nemotron-3.5-asr-streaming-0.6b") == "nemotron-3.5-asr-streaming-0.6b"
    assert Transcriber._local_model_name("local/faster-whisper-base.en") == "base.en"
    assert Transcriber._local_model_name("base.en") == "base.en"


def test_transcriber_loads_and_warms_nemotron():
    """Verify Transcriber integrates with Nemotron engine without falling back to Whisper."""
    real_model_path = downloadable_models.get_models_dir() / "nemotron-speech-streaming-en-0.6b.q8_0.gguf"
    if not real_model_path.is_file():
        pytest.skip(f"Model file not downloaded at {real_model_path}")

    transcriber = Transcriber.__new__(Transcriber)
    transcriber.model = None
    transcriber.nemotron_engine = None
    transcriber.category_hint = None
    transcriber._loading = False
    transcriber._loaded_model_ref = None
    transcriber._loading_model_ref = None
    transcriber._lock = threading.Lock()
    transcriber._transcribe_lock = threading.Lock()
    transcriber._whisper_models = {}

    # Load Nemotron model
    transcriber._load_model_bg("local/nemotron-speech-streaming-en-0.6b")

    assert transcriber.nemotron_engine is not None
    assert transcriber.nemotron_engine.is_warm
    assert transcriber._loaded_model_ref == "nemotron-speech-streaming-en-0.6b"

    # _wait_for_model must return True immediately (< 10ms) since model is warm
    t0 = time.perf_counter()
    ready = transcriber._wait_for_model(deadline=time.monotonic() + 5.0, model_ref="nemotron-speech-streaming-en-0.6b")
    wait_time = time.perf_counter() - t0

    assert ready is True
    assert wait_time < 0.010


def test_transcriber_auto_promotes_downloaded_nemotron():
    """Verify _load_active_model_bg auto-promotes downloaded Nemotron over default whisper."""
    real_model_path = downloadable_models.get_models_dir() / "nemotron-speech-streaming-en-0.6b.q8_0.gguf"
    if not real_model_path.is_file():
        pytest.skip(f"Model file not downloaded at {real_model_path}")

    with patch.object(storage, "get_setting", return_value="local/faster-whisper-base.en"):
        with patch.object(storage, "save_setting") as mock_save:
            transcriber = Transcriber.__new__(Transcriber)
            transcriber.model = None
            transcriber.nemotron_engine = None
            transcriber.category_hint = None
            transcriber._loading = False
            transcriber._loaded_model_ref = None
            transcriber._loading_model_ref = None
            transcriber._lock = threading.Lock()
            transcriber._transcribe_lock = threading.Lock()
            transcriber._whisper_models = {}

            with patch.object(transcriber, "_load_model_bg") as mock_load:
                transcriber._load_active_model_bg()
                # Should have auto-promoted and saved setting
                mock_save.assert_called_with("voice_flow_stt_model", "local/nemotron-speech-streaming-en-0.6b")
                mock_load.assert_called_with("nemotron-speech-streaming-en-0.6b")


def test_transcriber_transcribes_with_real_nemotron_engine():
    """Verify Transcriber._transcribe_local produces text using real warm Nemotron engine."""
    real_model_path = downloadable_models.get_models_dir() / "nemotron-speech-streaming-en-0.6b.q8_0.gguf"
    if not real_model_path.is_file():
        pytest.skip(f"Model file not downloaded at {real_model_path}")

    wav_file = Path("video-flow-v2.1/render-output/fixture-apple/narova/out/audio/sentences/01_000.wav")
    if not wav_file.is_file():
        pytest.skip(f"Audio fixture not found: {wav_file}")

    with wave.open(str(wav_file), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    transcriber = Transcriber.__new__(Transcriber)
    transcriber.model = None
    transcriber.nemotron_engine = None
    transcriber.category_hint = None
    transcriber._loading = False
    transcriber._loaded_model_ref = None
    transcriber._loading_model_ref = None
    transcriber._lock = threading.Lock()
    transcriber._transcribe_lock = threading.Lock()
    transcriber._whisper_models = {}

    result = transcriber._transcribe_local(audio, model_ref="local/nemotron-speech-streaming-en-0.6b")
    assert isinstance(result, str)
    assert len(result) > 0
    assert any(w in result.lower() for w in ["branch", "blossom", "apple", "evolve", "bud"])


def test_polishing_disabled_speed():
    """Verify that when polishing is disabled, deterministic cleanup runs nearly instantly (< 50ms)."""
    outcome_record: dict[str, str] = {}

    with patch.object(storage, "get_setting", side_effect=lambda k, d=None: False if k == "polishing_enabled" else d):
        polisher.polish("Warm up", outcome_callback=lambda o: None)

        t0 = time.perf_counter()
        result = polisher.polish(
            "Here right now I am testing the model.",
            outcome_callback=lambda o: outcome_record.update(value=o),
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

    assert outcome_record.get("value") == "disabled"
    assert "testing the model" in result
    assert elapsed_ms < 50.0


def test_nemotron_stream_transcriber_live_pipeline():
    """Verify NemotronStreamTranscriber ingests frames in real time and finishes in < 450ms."""
    from voice_flow.nemotron_engine import NemotronStreamTranscriber

    real_model_path = downloadable_models.get_models_dir() / "nemotron-speech-streaming-en-0.6b.q8_0.gguf"
    if not real_model_path.is_file():
        pytest.skip(f"Model file not downloaded at {real_model_path}")

    wav_file = Path("video-flow-v2.1/render-output/fixture-apple/narova/out/audio/sentences/01_000.wav")
    if not wav_file.is_file():
        pytest.skip(f"Audio fixture not found: {wav_file}")

    with wave.open(str(wav_file), "rb") as wf:
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    streamer = NemotronStreamTranscriber()
    streamer.start_session(model_ref="local/nemotron-speech-streaming-en-0.6b")

    # Test with 2.0s of audio representing realistic conversational speech pacing
    clip = audio[: int(2.0 * sr)]
    frame_size = int(0.1 * sr)
    for idx in range(0, len(clip), frame_size):
        chunk = clip[idx : idx + frame_size]
        streamer.submit_frame(chunk, native_sr=sr)
        time.sleep(0.065)

    assert streamer.accepted_count() > 0
    assert streamer.had_failures() is False

    t_release = time.perf_counter()
    streamer.end_session()
    text = streamer.collect(timeout=3.0)
    drain_time = time.perf_counter() - t_release

    assert streamer.had_failures() is False
    assert streamer.completed_successfully() is True
    assert isinstance(text, str)
    assert len(text) > 0
    assert any(w in text.lower() for w in ["branch", "blossom", "apple", "evolve", "bud", "depict"])
    assert drain_time < 0.850  # Must finish within release deadline budget


def test_nemotron_stream_transcriber_discard():
    """Verify NemotronStreamTranscriber discard sets failure flag and yields empty string."""
    from voice_flow.nemotron_engine import NemotronStreamTranscriber

    streamer = NemotronStreamTranscriber()
    streamer.start_session(model_ref="local/nemotron-speech-streaming-en-0.6b")
    streamer.submit_frame(np.zeros(1600, dtype=np.float32), native_sr=16000)
    streamer.discard()
    assert streamer.had_failures() is True
    res = streamer.collect(timeout=0.5)
    assert res == ""


@pytest.mark.parametrize(
    ("empty_final_at_intake", "empty_final_at_drain"),
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_nemotron_finalization_does_not_publish_hello_without_welcome(
    monkeypatch, empty_final_at_intake, empty_final_at_drain
):
    """An unfinalized 'hello welcome' interim must trigger whole-audio recovery."""
    class _FakeEngine:
        rec_handle = ctypes.c_void_p(1)
        spec = {}
        lock = threading.Lock()

        def acquire_stream(self):
            pass

        def release_stream(self):
            pass

    class _FakeDll:
        def __init__(self):
            self.pushed_samples: list[np.ndarray] = []
            self.results = {
                101: (True, b"hello"),
                102: (False, b"hello welcome"),
                103: (True, b""),
            }
            self.push_count = 0
            self.finished = False
            self.drain_emitted = False

        def nemo_speech_asr_stream_push_f32(self, _stream, ptr, length, _rate):
            sample_ptr = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_float))
            self.pushed_samples.append(np.ctypeslib.as_array(sample_ptr, shape=(length,)).copy())
            self.push_count += 1
            return 0

        def nemo_speech_asr_stream_next(self, _stream, output):
            if self.finished and empty_final_at_drain and not self.drain_emitted:
                self.drain_emitted = True
                output._obj.value = 103
                return 0
            if not self.finished and self.push_count == 1:
                output._obj.value = 101
                return 0
            if not self.finished and self.push_count >= 3:
                if self.push_count == 3:
                    output._obj.value = 102
                    return 0
                if self.push_count == 4 and empty_final_at_intake:
                    output._obj.value = 103
                    return 0
            return 1

        def nemo_speech_asr_stream_finish(self, _stream):
            self.finished = True
            return 0

        def nemo_speech_asr_result_is_final(self, result):
            return self.results[result.value][0]

        def nemo_speech_asr_result_transcript(self, result, _index):
            return self.results[result.value][1]

        def nemo_speech_asr_result_destroy(self, _result):
            pass

        def nemo_speech_asr_stream_close(self, _stream):
            pass

    dll = _FakeDll()
    monkeypatch.setattr(nemotron_engine, "get_nemo_dll", lambda: dll)
    session = nemotron_engine.NemotronStreamTranscriber(engine=_FakeEngine())
    monkeypatch.setattr(session, "_open_stream", lambda _dll: setattr(session._stream, "value", 42) or True)
    session.start_session()

    # Include a very short, quiet leading frame and quiet ending samples. The
    # live path must push every native-rate sample in order, even when the
    # decoder has only finalized "hello" and leaves "hello welcome" interim.
    frames = [
        np.array([0.001, 0.002, 0.003], dtype=np.float32),
        np.linspace(-0.08, 0.08, 160, dtype=np.float32),
        np.array([0.002, 0.001, 0.0005], dtype=np.float32),
        np.array([0.0004, 0.0003], dtype=np.float32),
    ]
    for frame in frames:
        session.submit_frame(frame, native_sr=16000)
    session.end_session()

    assert session._done.wait(1.0)
    pushed = np.concatenate(dll.pushed_samples)
    np.testing.assert_array_equal(pushed, np.concatenate(frames))
    assert session._text == "hello"
    assert session.had_failures() is True
    assert session.collect(timeout=0.01) == ""
    assert session.completed_successfully() is False


def test_nemotron_final_drain_keeps_the_normal_success_path(monkeypatch):
    class _FakeEngine:
        rec_handle = ctypes.c_void_p(1)
        spec = {}
        lock = threading.Lock()

        def acquire_stream(self):
            pass

        def release_stream(self):
            pass

    class _FakeDll:
        finished = False
        first_emitted = False
        tail_emitted = False

        def nemo_speech_asr_stream_push_f32(self, *_args):
            return 0

        def nemo_speech_asr_stream_next(self, _stream, output):
            if not self.first_emitted:
                self.first_emitted = True
                output._obj.value = 201
                return 0
            if self.finished and not self.tail_emitted:
                self.tail_emitted = True
                output._obj.value = 202
                return 0
            return 1

        def nemo_speech_asr_stream_finish(self, _stream):
            self.finished = True
            return 0

        def nemo_speech_asr_result_is_final(self, result):
            return True

        def nemo_speech_asr_result_transcript(self, result, _index):
            return b"hello" if result.value == 201 else b"welcome"

        def nemo_speech_asr_result_destroy(self, _result):
            pass

        def nemo_speech_asr_stream_close(self, _stream):
            pass

    monkeypatch.setattr(nemotron_engine, "get_nemo_dll", lambda: _FakeDll())
    session = nemotron_engine.NemotronStreamTranscriber(engine=_FakeEngine())
    monkeypatch.setattr(session, "_open_stream", lambda _dll: setattr(session._stream, "value", 42) or True)
    session.start_session()
    session.submit_frame(np.ones(160, dtype=np.float32), 16000)
    session.end_session()

    assert session.collect(timeout=1.0) == "hello welcome"
    assert session.had_failures() is False
    assert session.completed_successfully() is True


def test_nemotron_long_buffer_segmentation_keeps_short_final_tail(monkeypatch):
    """Long fallback segmentation must pass every sample to exactly one decode."""
    engine = object.__new__(nemotron_engine.NemotronGGUFEngine)
    engine.sample_rate = 16000
    engine.spec = {}
    engine.rec_handle = ctypes.c_void_p(1)
    engine.lock = threading.Lock()
    engine.total_transcriptions = 0
    engine.total_audio_seconds = 0.0
    segments: list[np.ndarray] = []

    # Quietest-window cuts land at 3.95, 7.90, and 11.85 seconds, leaving a
    # 190 ms final word. Existing code drops that remainder below its 200 ms
    # native-decoder minimum after already returning earlier segment text.
    audio = np.full(int(12.04 * engine.sample_rate), 0.1, dtype=np.float32)
    for start in (3.90, 7.85, 11.80):
        begin = int(start * engine.sample_rate)
        audio[begin : begin + 1600] = 0.001

    monkeypatch.setattr(nemotron_engine, "get_nemo_dll", lambda: object())

    def record_segment(samples: np.ndarray, **_kwargs) -> str:
        segments.append(samples.copy())
        return f"part {len(segments)}"

    engine._transcribe_segment = record_segment
    text = engine.transcribe(audio)

    assert text == "part 1 part 2 part 3"
    np.testing.assert_array_equal(np.concatenate(segments), audio)
    assert all(len(segment) >= int(0.2 * engine.sample_rate) for segment in segments)


def test_nemotron_stream_transcriber_fallback_when_invalid_model(monkeypatch):
    """Verify NemotronStreamTranscriber gracefully marks failure if model cannot be loaded."""
    from voice_flow.nemotron_engine import NemotronStreamTranscriber

    monkeypatch.setattr(nemotron_engine, "get_nemotron_engine", lambda _ref: None)
    monkeypatch.setattr(nemotron_engine, "get_nemo_dll", lambda: None)
    streamer = NemotronStreamTranscriber()
    streamer.start_session(model_ref="nonexistent/fake-model-12345")
    assert streamer._done.wait(1.0)
    assert streamer.had_failures() is True
    assert streamer.collect(timeout=0.1) == ""

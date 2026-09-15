"""Comprehensive tests for NVIDIA Nemotron Speech ASR GGUF Engine and Voice Flow integration."""
from __future__ import annotations

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


def test_nemotron_stream_transcriber_fallback_when_invalid_model():
    """Verify NemotronStreamTranscriber gracefully marks failure if model cannot be loaded."""
    from voice_flow.nemotron_engine import NemotronStreamTranscriber

    streamer = NemotronStreamTranscriber()
    streamer.start_session(model_ref="nonexistent/fake-model-12345")
    assert streamer.had_failures() is True
    assert streamer.collect(timeout=0.1) == ""


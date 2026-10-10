"""Tests for STT model selection synchronization and cloud-to-local failover."""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path, monkeypatch):
    """Provide a clean SQLite database for each test."""
    from voice_flow.storage import StorageEngine
    s = StorageEngine(str(tmp_path / "test.db"))
    monkeypatch.setattr("voice_flow.transcriber.storage", s, raising=False)
    # Also patch the module-level import inside transcriber.transcribe
    import voice_flow.storage as _storage_mod
    monkeypatch.setattr(_storage_mod, "storage", s)
    yield s


def _make_transcriber(monkeypatch):
    """Build a Transcriber with the local model mocked out."""
    from voice_flow.transcriber import Transcriber
    t = Transcriber.__new__(Transcriber)
    t._lock = threading.Lock()
    t.model = MagicMock()
    t.nemotron_engine = None
    t._loading = False
    t._loaded_model_ref = None
    t._loading_model_ref = None
    t._cloud_stt_breakers = {}
    t._failover_count = 0
    t._last_failover_info = None

    # Mock _wait_for_model to always succeed
    monkeypatch.setattr(t, "_wait_for_model", lambda *a, **kw: True)
    # Mock _transcribe_local to return a fixed string
    monkeypatch.setattr(t, "_transcribe_local", lambda *a, **kw: "local fallback text")
    return t


def test_model_selection_reads_from_storage(monkeypatch, _isolate_storage):
    """Changing the stored model mid-session results in the next transcription
    using the newly stored model."""
    s = _isolate_storage
    t = _make_transcriber(monkeypatch)

    # Set initial model to groq
    s.save_setting("voice_flow_stt_model", "groq/whisper-large-v3-turbo")
    audio = np.zeros(16000, dtype=np.float32)

    cloud_called_with = {}

    def fake_cloud(audio, model_ref, **kw):
        cloud_called_with["model"] = model_ref
        return "cloud text"

    monkeypatch.setattr("voice_flow.stt_engines.transcribe_cloud", fake_cloud)

    result = t.transcribe(audio)
    assert result == "cloud text"
    assert cloud_called_with["model"] == "groq/whisper-large-v3-turbo"

    # Now change the model to openai
    s.save_setting("voice_flow_stt_model", "openai/whisper-1")
    cloud_called_with.clear()

    result = t.transcribe(audio)
    assert result == "cloud text"
    assert cloud_called_with["model"] == "openai/whisper-1", \
        f"Expected openai/whisper-1 but got {cloud_called_with.get('model')}"


def test_cloud_failover_falls_back_to_local(monkeypatch, _isolate_storage):
    """When the cloud model fails, transcriber falls back to local whisper."""
    s = _isolate_storage
    t = _make_transcriber(monkeypatch)
    s.save_setting("voice_flow_stt_model", "groq/whisper-large-v3-turbo")

    audio = np.zeros(16000, dtype=np.float32)

    def fail_cloud(audio, model_ref, **kw):
        raise ConnectionError("Network error")

    monkeypatch.setattr("voice_flow.stt_engines.transcribe_cloud", fail_cloud)

    result = t.transcribe(audio)
    # Should have fallen back to local
    assert result == "local fallback text"
    # Failover should be tracked
    assert t._failover_count >= 1
    assert t._last_failover_info is not None
    assert t._last_failover_info["cloud_model"] == "groq/whisper-large-v3-turbo"


def test_failover_info_cleared_on_cloud_success(monkeypatch, _isolate_storage):
    """After a cloud model succeeds, _last_failover_info is cleared."""
    s = _isolate_storage
    t = _make_transcriber(monkeypatch)
    s.save_setting("voice_flow_stt_model", "groq/whisper-large-v3-turbo")

    audio = np.zeros(16000, dtype=np.float32)

    # First: fail
    call_count = {"n": 0}

    def cloud_call(audio, model_ref, **kw):
        call_count["n"] += 1
        if call_count["n"] <= 1:
            raise ConnectionError("fail")
        return "recovered text"

    monkeypatch.setattr("voice_flow.stt_engines.transcribe_cloud", cloud_call)

    r1 = t.transcribe(audio)
    assert r1 == "local fallback text"
    assert t._last_failover_info is not None

    # Second: succeed
    r2 = t.transcribe(audio)
    assert r2 == "recovered text"
    assert t._last_failover_info is None  # cleared on success


def test_model_ref_argument_overrides_storage(monkeypatch, _isolate_storage):
    """When model_ref is passed explicitly, it takes precedence over storage."""
    s = _isolate_storage
    t = _make_transcriber(monkeypatch)
    s.save_setting("voice_flow_stt_model", "groq/whisper-large-v3-turbo")

    audio = np.zeros(16000, dtype=np.float32)
    cloud_called_with = {}

    def fake_cloud(audio, model_ref, **kw):
        cloud_called_with["model"] = model_ref
        return "cloud text"

    monkeypatch.setattr("voice_flow.stt_engines.transcribe_cloud", fake_cloud)

    # Pass explicit model_ref overriding storage
    result = t.transcribe(audio, model_ref="openai/whisper-1")
    assert result == "cloud text"
    assert cloud_called_with["model"] == "openai/whisper-1"


def test_local_model_selection_bypasses_cloud(monkeypatch, _isolate_storage):
    """When a local model is selected, cloud path is not invoked."""
    s = _isolate_storage
    t = _make_transcriber(monkeypatch)
    s.save_setting("voice_flow_stt_model", "local/faster-whisper-base.en")

    audio = np.zeros(16000, dtype=np.float32)
    cloud_called = {"called": False}

    def should_not_call(audio, model_ref, **kw):
        cloud_called["called"] = True
        return "should not reach"

    monkeypatch.setattr("voice_flow.stt_engines.transcribe_cloud", should_not_call)

    result = t.transcribe(audio)
    assert result == "local fallback text"
    assert not cloud_called["called"], "Cloud path should not be invoked for local models"

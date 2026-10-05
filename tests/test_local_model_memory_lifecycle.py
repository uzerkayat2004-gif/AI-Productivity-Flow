"""Fake-native lifecycle regressions for resident local model memory."""

from __future__ import annotations

import sys
import ctypes
import threading
from pathlib import Path
from types import SimpleNamespace

from voice_flow import lfm_engine, nemotron_engine


def test_lfm_path_switch_explicitly_releases_replaced_native_model(tmp_path: Path, monkeypatch) -> None:
    first, second = tmp_path / "first.gguf", tmp_path / "second.gguf"
    first.write_bytes(b"x")
    second.write_bytes(b"x")
    created = []

    class FakeLlama:
        def __init__(self, **_kwargs):
            self.closed = 0
            created.append(self)

        def close(self):
            self.closed += 1

    paths = iter((first, second))
    monkeypatch.setattr(lfm_engine, "get_lfm_model_path", lambda: next(paths))
    monkeypatch.setattr(lfm_engine, "is_lfm_runtime_available", lambda: True)
    monkeypatch.setitem(sys.modules, "llama_cpp", SimpleNamespace(Llama=FakeLlama))
    monkeypatch.delattr(lfm_engine.polish_with_lfm, "_cached_llm", raising=False)
    monkeypatch.delattr(lfm_engine.polish_with_lfm, "_cached_llm_path", raising=False)

    assert lfm_engine.warm_lfm_model()
    assert lfm_engine.warm_lfm_model()
    assert created[0].closed == 1


def test_nemotron_model_switch_evicts_inactive_native_engine(tmp_path: Path, monkeypatch) -> None:
    first, second = tmp_path / "first.gguf", tmp_path / "second.gguf"
    first.write_bytes(b"x")
    second.write_bytes(b"x")
    created = []

    class FakeEngine:
        def __init__(self, path, spec=None):
            self.model_path = Path(path)
            self.spec = spec
            self.is_warm = True
            self.closed = 0
            created.append(self)

        def close(self):
            self.closed += 1
            self.is_warm = False

    nemotron_engine.clear_engine_cache()
    monkeypatch.setattr(nemotron_engine, "NemotronGGUFEngine", FakeEngine)
    assert nemotron_engine.get_nemotron_engine(first) is created[0]
    assert nemotron_engine.get_nemotron_engine(second) is created[1]
    assert created[0].closed == 1
    nemotron_engine.clear_engine_cache()


def test_active_nemotron_lease_defers_destroy_until_stream_finalizes() -> None:
    destroyed = []

    class Dll:
        def nemo_speech_asr_destroy(self, handle):
            destroyed.append(handle.value)

    engine = object.__new__(nemotron_engine.NemotronGGUFEngine)
    engine.lock = threading.RLock()
    engine.rec_handle = ctypes.c_void_p(99)
    engine._is_warm = True
    engine._active_streams = 0
    engine._evict_when_idle = False
    original = nemotron_engine.get_nemo_dll
    nemotron_engine.get_nemo_dll = lambda: Dll()
    try:
        engine.acquire_stream()
        engine.close()
        assert destroyed == []
        assert engine.rec_handle.value == 99
        engine.release_stream()
        assert destroyed == [99]
        assert not engine.rec_handle.value
    finally:
        nemotron_engine.get_nemo_dll = original


def test_failed_replacement_keeps_old_nemotron_cache_entry(tmp_path: Path, monkeypatch) -> None:
    first, second = tmp_path / "first.gguf", tmp_path / "second.gguf"
    first.write_bytes(b"x"); second.write_bytes(b"x")
    class Engine:
        def __init__(self, path, spec=None):
            if Path(path) == second:
                raise RuntimeError("load failed")
            self.is_warm = True
            self.closed = 0
        def close(self): self.closed += 1
    nemotron_engine.clear_engine_cache()
    monkeypatch.setattr(nemotron_engine, "NemotronGGUFEngine", Engine)
    previous = nemotron_engine.get_nemotron_engine(first)
    assert previous is not None
    assert nemotron_engine.get_nemotron_engine(second) is None
    assert nemotron_engine.get_nemotron_engine(first) is previous
    assert previous.closed == 0
    nemotron_engine.clear_engine_cache()


def _stream_engine():
    engine = SimpleNamespace(
        lock=threading.RLock(), rec_handle=ctypes.c_void_p(42), spec={}, leases=0, releases=0,
    )
    engine.acquire_stream = lambda: setattr(engine, "leases", engine.leases + 1)
    engine.release_stream = lambda: setattr(engine, "releases", engine.releases + 1)
    return engine


def test_stream_open_failure_closes_partial_native_handle_and_releases_lease(monkeypatch) -> None:
    engine = _stream_engine()
    class Dll:
        closed = 0
        def nemo_speech_asr_recognition_options_default(self): return nemotron_engine._RecognitionOptions()
        def nemo_speech_asr_streaming_recognize(self, _handle, _opts, output): output._obj.value = 77; return 1
        def nemo_speech_asr_last_error(self): return b"open failed"
        def nemo_speech_asr_stream_close(self, _stream): self.closed += 1
    dll = Dll()
    monkeypatch.setattr(nemotron_engine, "get_nemo_dll", lambda: dll)
    stream = nemotron_engine.NemotronStreamTranscriber(engine=engine)
    stream.start_session()
    assert stream._done.wait(1.0)
    assert dll.closed == 1 and engine.leases == engine.releases == 1
    assert stream._done.is_set() and stream.had_failures()


def test_worker_start_failure_closes_native_stream_and_releases_lease(monkeypatch) -> None:
    engine = _stream_engine()
    class Dll:
        closed = 0
        def nemo_speech_asr_recognition_options_default(self): return nemotron_engine._RecognitionOptions()
        def nemo_speech_asr_streaming_recognize(self, _handle, _opts, output): output._obj.value = 88; return 0
        def nemo_speech_asr_stream_close(self, _stream): self.closed += 1
    dll = Dll()
    monkeypatch.setattr(nemotron_engine, "get_nemo_dll", lambda: dll)
    monkeypatch.setattr(threading.Thread, "start", lambda _self: (_ for _ in ()).throw(RuntimeError("no worker")))
    stream = nemotron_engine.NemotronStreamTranscriber(engine=engine)
    stream.start_session()
    assert dll.closed == 0 and engine.leases == engine.releases == 0
    assert stream._done.is_set() and stream.had_failures()

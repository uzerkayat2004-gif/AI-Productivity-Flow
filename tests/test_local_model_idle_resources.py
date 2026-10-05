"""Idle eviction must free native memory while leaving active models intact."""
from __future__ import annotations

import ctypes
import gc
import threading
import weakref
from types import SimpleNamespace

from voice_flow import lfm_engine, local_model_resources, nemotron_engine


def _native_engine():
    engine = object.__new__(nemotron_engine.NemotronGGUFEngine)
    engine.lock = threading.RLock()
    engine.rec_handle = ctypes.c_void_p(99)
    engine._is_warm = True
    engine._active_streams = 0
    engine._evict_when_idle = False
    engine._last_used = 10.0
    return engine


def test_idle_native_cache_releases_actual_recognizer_handle(monkeypatch):
    destroyed = []
    engine = _native_engine()
    monkeypatch.setattr(nemotron_engine, "get_nemo_dll", lambda: SimpleNamespace(
        nemo_speech_asr_destroy=lambda handle: destroyed.append(handle.value)))
    monkeypatch.setattr(nemotron_engine, "_NEMOTRON_CACHE", {"offline": engine})
    nemotron_engine._evict_idle_engines(10.0 + local_model_resources.LOCAL_MODEL_IDLE_SECONDS - 1)
    assert engine.is_warm
    nemotron_engine._evict_idle_engines(10.0 + local_model_resources.LOCAL_MODEL_IDLE_SECONDS)
    assert destroyed == [99]
    assert not engine.is_warm
    assert not nemotron_engine._NEMOTRON_CACHE


def test_idle_cleanup_preserves_active_recording_and_resets_idle_clock(monkeypatch):
    destroyed = []
    clock = [20.0]
    engine = _native_engine()
    monkeypatch.setattr(nemotron_engine, "get_nemo_dll", lambda: SimpleNamespace(
        nemo_speech_asr_destroy=lambda handle: destroyed.append(handle.value)))
    monkeypatch.setattr(nemotron_engine.time, "monotonic", lambda: clock[0])
    engine.acquire_stream()
    assert not engine.release_if_idle(1_000.0)
    clock[0] = 1_000.0
    engine.release_stream()
    assert not engine.release_if_idle(1_001.0)
    assert engine.release_if_idle(1_000.0 + local_model_resources.LOCAL_MODEL_IDLE_SECONDS)
    assert destroyed == [99]


def test_next_request_reloads_a_model_after_idle_cleanup(monkeypatch, tmp_path):
    model_path = tmp_path / "offline.gguf"
    model_path.write_bytes(b"fake model used only for path validation")
    old_engine = _native_engine()
    replacement = _native_engine()
    constructed = []
    destroyed = []
    monkeypatch.setattr(nemotron_engine, "get_nemo_dll", lambda: SimpleNamespace(
        nemo_speech_asr_destroy=lambda handle: destroyed.append(handle.value)))
    monkeypatch.setattr(nemotron_engine, "_NEMOTRON_CACHE", {str(model_path.resolve()): old_engine})
    monkeypatch.setattr(nemotron_engine, "register_idle_cleanup", lambda *_args, **_kwargs: None)

    def construct(path, *, spec):
        constructed.append(path)
        return replacement

    monkeypatch.setattr(nemotron_engine, "NemotronGGUFEngine", construct)
    try:
        nemotron_engine._evict_idle_engines(10.0 + local_model_resources.LOCAL_MODEL_IDLE_SECONDS)
        assert not old_engine.is_warm
        assert destroyed == [99]
        loaded = nemotron_engine.get_nemotron_engine(model_path)
        assert loaded is replacement
        assert loaded.is_warm
        assert constructed == [model_path]
        assert nemotron_engine.get_nemotron_engine(model_path) is replacement
        assert len(constructed) == 1
    finally:
        # Never let a fabricated handle outlive the fake native DLL.
        old_engine.close()
        replacement.close()


def test_idle_native_cleanup_never_waits_for_active_synchronous_decode(monkeypatch):
    engine = _native_engine()
    held = threading.Event()
    release = threading.Event()

    def decoding():
        with engine.lock:
            held.set()
            release.wait(1.0)

    worker = threading.Thread(target=decoding)
    worker.start()
    assert held.wait(1.0)
    try:
        assert not engine.release_if_idle(1_000.0)
        assert engine.is_warm
    finally:
        release.set()
        worker.join(timeout=1.0)
        # Avoid a real native destructor for this fabricated handle.
        engine.rec_handle = ctypes.c_void_p()


def test_idle_lfm_closes_model_and_clears_cached_path(monkeypatch):
    released = []
    model = SimpleNamespace(close=lambda: released.append(True))
    monkeypatch.setattr(lfm_engine.polish_with_lfm, "_cached_llm", model, raising=False)
    monkeypatch.setattr(lfm_engine.polish_with_lfm, "_cached_llm_path", "offline.gguf", raising=False)
    monkeypatch.setattr(lfm_engine.polish_with_lfm, "_last_used", 10.0, raising=False)
    with lfm_engine._LLM_LOCK:
        lfm_engine._release_idle_lfm(1_000.0)
        assert released == []
    lfm_engine._release_idle_lfm(10.0 + local_model_resources.LOCAL_MODEL_IDLE_SECONDS)
    assert released == [True]
    assert lfm_engine.polish_with_lfm._cached_llm is None
    assert lfm_engine.polish_with_lfm._cached_llm_path is None


def test_shared_cleanup_continues_if_one_callback_fails(monkeypatch):
    called = []

    def failed(_now):
        raise RuntimeError("metrics unavailable")

    monkeypatch.setattr(local_model_resources, "_callbacks", {"failed": failed, "working": called.append})
    local_model_resources.cleanup_idle_models(15.0)
    assert called == [15.0]


def test_idle_whisper_releases_cached_model_and_allows_reload():
    from voice_flow.transcriber import Transcriber
    transcriber = object.__new__(Transcriber)
    transcriber._lock = threading.Lock()
    transcriber._transcribe_lock = threading.Lock()
    transcriber._loading = False
    transcriber.nemotron_engine = None
    transcriber._loaded_model_ref = "small.en"
    transcriber._last_whisper_use = 10.0

    class Model:
        pass

    model = Model()
    reference = weakref.ref(model)
    transcriber.model = model
    transcriber._whisper_models = {"small.en": model}
    del model
    with transcriber._transcribe_lock:
        transcriber._release_idle_whisper(1_000.0)
        assert reference() is not None
    transcriber._release_idle_whisper(10.0 + local_model_resources.LOCAL_MODEL_IDLE_SECONDS)
    assert reference() is None
    assert transcriber._loaded_model_ref is None
    assert transcriber.model is None


def test_cleanup_uses_one_worker_and_weakly_registers_instance_callbacks(monkeypatch):
    workers = []

    class Thread:
        def __init__(self, **_kwargs):
            workers.append(self)
            self.started = False

        def is_alive(self):
            return self.started

        def start(self):
            self.started = True

    class Owner:
        def cleanup(self, _now):
            pass

    monkeypatch.setattr(local_model_resources, "_callbacks", {})
    monkeypatch.setattr(local_model_resources, "_worker", None)
    monkeypatch.setattr(local_model_resources.threading, "Thread", Thread)
    owner = Owner()
    reference = weakref.ref(owner)
    local_model_resources.register_idle_cleanup("one", owner.cleanup)
    local_model_resources.register_idle_cleanup("two", lambda _now: None)
    assert len(workers) == 1
    del owner
    gc.collect()
    assert reference() is None
    local_model_resources.cleanup_idle_models(100.0)
    assert "one" not in local_model_resources._callbacks

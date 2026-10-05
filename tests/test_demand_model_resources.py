"""Demand-scoped local model residency."""
from __future__ import annotations

import ctypes
import threading
import time

import numpy as np
import pytest

from voice_flow import local_model_resources
from voice_flow import lfm_engine
from voice_flow import nemotron_engine
from voice_flow import transcriber as transcriber_module


@pytest.fixture(autouse=True)
def _clean_demand_registry(monkeypatch):
    _isolated_registry(monkeypatch)
    monkeypatch.setattr(local_model_resources, "_ensure_worker", lambda: None)


def _isolated_registry(monkeypatch):
    monkeypatch.setattr(local_model_resources, "_callbacks", {})
    monkeypatch.setattr(local_model_resources, "_active_uses", {"speech": 0, "polish": 0})
    monkeypatch.setattr(local_model_resources, "_cleanup_requested", set())


def test_last_speech_lease_requests_prompt_cleanup(monkeypatch):
    calls = []
    local_model_resources.register_idle_cleanup(
        "speech-test", lambda now: calls.append(now) or True, kind="speech"
    )

    first = local_model_resources.acquire_model_use("speech")
    second = local_model_resources.acquire_model_use("speech")
    first.release()
    local_model_resources.cleanup_idle_models(10.0)
    assert calls == []

    second.release()
    second.release()  # A lease can safely be released by two teardown paths.
    local_model_resources.cleanup_idle_models(11.0)
    assert calls == [11.0]


def test_busy_cleanup_request_persists_until_engine_notifies(monkeypatch):
    attempts = []

    def cleanup(_now):
        attempts.append(True)
        return len(attempts) > 1

    local_model_resources.register_idle_cleanup(
        "polish-test", cleanup, kind="polish"
    )

    lease = local_model_resources.acquire_model_use("polish")
    lease.release()
    local_model_resources.cleanup_idle_models(20.0)
    assert len(attempts) == 1
    assert "polish" in local_model_resources._cleanup_requested

    local_model_resources.notify_models_available("polish")
    local_model_resources.cleanup_idle_models(21.0)
    assert len(attempts) == 2
    assert "polish" not in local_model_resources._cleanup_requested


def test_cleanup_request_reaches_every_callback_in_model_family():
    calls = []
    local_model_resources.register_idle_cleanup(
        "empty-whisper", lambda _now: calls.append("whisper") or True, kind="speech"
    )

    def release_native(_now):
        assert local_model_resources.cleanup_is_forced("speech")
        calls.append("native")
        return True

    local_model_resources.register_idle_cleanup("native", release_native, kind="speech")
    lease = local_model_resources.acquire_model_use("speech")
    lease.release()
    local_model_resources.cleanup_idle_models(30.0)
    assert calls == ["whisper", "native"]
    assert "speech" not in local_model_resources._cleanup_requested


def test_transcriber_startup_does_not_allocate_or_prewarm_models(monkeypatch):
    started = []
    monkeypatch.setattr(transcriber_module, "register_idle_cleanup", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(transcriber_module.threading.Thread, "start", lambda self: started.append(self))
    transcriber = transcriber_module.Transcriber()
    assert started == []
    assert transcriber.model is None
    assert transcriber.nemotron_engine is None


def test_cloud_capture_prepare_does_not_load_local_fallback(monkeypatch):
    transcriber = object.__new__(transcriber_module.Transcriber)
    started = []
    monkeypatch.setattr(transcriber_module.threading.Thread, "start", lambda self: started.append(self))
    lease = transcriber.prepare_model_async("deepgram/nova-3")
    try:
        assert started == []
    finally:
        lease.release()


def test_prepare_worker_never_releases_callers_session_lease(monkeypatch):
    finished = threading.Event()

    class Lease:
        released = 0

        def release(self):
            self.released += 1

    transcriber = object.__new__(transcriber_module.Transcriber)
    monkeypatch.setattr(
        transcriber,
        "_load_model_bg_impl",
        lambda *_args, **_kwargs: finished.set(),
    )
    lease = Lease()
    returned = transcriber.prepare_model_async("local/base.en", lease=lease)
    assert finished.wait(1.0)
    assert returned is lease
    assert lease.released == 0
    lease.release()
    assert lease.released == 1


def test_prepare_worker_keeps_own_lease_after_session_cancels(monkeypatch):
    entered = threading.Event()
    unblock = threading.Event()

    def load(*_args, **_kwargs):
        entered.set()
        assert unblock.wait(1.0)

    transcriber = object.__new__(transcriber_module.Transcriber)
    monkeypatch.setattr(transcriber, "_load_model_bg_impl", load)
    session_lease = local_model_resources.acquire_model_use("speech")
    transcriber.prepare_model_async("local/base.en", lease=session_lease)
    assert entered.wait(0.5)
    session_lease.release()
    assert local_model_resources.has_active_model_use("speech")
    unblock.set()
    deadline = time.monotonic() + 1.0
    while local_model_resources.has_active_model_use("speech") and time.monotonic() < deadline:
        time.sleep(0.005)
    assert not local_model_resources.has_active_model_use("speech")
    assert local_model_resources.cleanup_requested("speech")


def test_lfm_releases_polish_lease_when_inference_fails(monkeypatch):
    released = []

    class Lease:
        def release(self):
            released.append(True)

    monkeypatch.setattr(lfm_engine, "acquire_model_use", lambda kind: Lease())
    monkeypatch.setattr(lfm_engine, "_polish_with_lfm_impl", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("failed")))
    with pytest.raises(RuntimeError, match="failed"):
        lfm_engine.polish_with_lfm("hello")
    assert released == [True]


class _StreamEngine:
    def __init__(self):
        self.rec_handle = ctypes.c_void_p(7)
        self.lock = threading.RLock()
        self.spec = {}
        self.acquired = 0

    def acquire_stream(self):
        self.acquired += 1

    def release_stream(self):
        self.acquired -= 1


class _StreamDll:
    def __init__(self):
        self.pushed = []

    def nemo_speech_asr_stream_push_f32(self, _stream, _ptr, length, rate):
        self.pushed.append((length, rate))
        return 0

    def nemo_speech_asr_stream_next(self, _stream, _result):
        return 1

    def nemo_speech_asr_stream_finish(self, _stream):
        return 0

    def nemo_speech_asr_stream_close(self, _stream):
        return None


def test_native_stream_start_returns_while_model_loads_and_buffers_audio(monkeypatch):
    entered = threading.Event()
    unblock = threading.Event()
    engine = _StreamEngine()
    dll = _StreamDll()

    def load(_ref):
        entered.set()
        assert unblock.wait(1.0)
        return engine

    monkeypatch.setattr(nemotron_engine, "get_nemotron_engine", load)
    monkeypatch.setattr(nemotron_engine, "get_nemo_dll", lambda: dll)
    session = nemotron_engine.NemotronStreamTranscriber()
    monkeypatch.setattr(session, "_open_stream", lambda _dll: setattr(session._stream, "value", 42) or True)

    started = time.perf_counter()
    session.start_session("local.gguf")
    assert time.perf_counter() - started < 0.1
    assert entered.wait(0.5)
    session.submit_frame(np.ones(160, dtype=np.float32), 16000)
    session.submit_frame(np.full(320, 2.0, dtype=np.float32), 16000)
    session.end_session()
    unblock.set()
    assert session._done.wait(1.0)
    assert dll.pushed == [(160, 16000), (320, 16000)]
    assert engine.acquired == 0
    assert not session.had_failures()


def test_cancel_during_native_model_load_never_opens_or_retains_stream(monkeypatch):
    entered = threading.Event()
    unblock = threading.Event()
    engine = _StreamEngine()
    opened = []

    def load(_ref):
        entered.set()
        assert unblock.wait(1.0)
        return engine

    monkeypatch.setattr(nemotron_engine, "get_nemotron_engine", load)
    monkeypatch.setattr(nemotron_engine, "get_nemo_dll", lambda: _StreamDll())
    session = nemotron_engine.NemotronStreamTranscriber()
    monkeypatch.setattr(session, "_open_stream", lambda _dll: opened.append(True) or True)
    session.start_session("local.gguf")
    assert entered.wait(0.5)
    session.discard()
    unblock.set()
    assert session._done.wait(1.0)
    assert opened == []
    assert engine.acquired == 0
    assert session._model_lease is None
    assert session.had_failures()


def test_concurrent_native_getters_construct_one_engine(monkeypatch, tmp_path):
    model_path = tmp_path / "native.gguf"
    model_path.write_bytes(b"model")
    entered = threading.Event()
    unblock = threading.Event()
    constructed = []
    engine = _StreamEngine()
    engine.is_warm = True
    engine.close = lambda: None
    engine.touch = lambda: None

    def construct(_path, *, spec):
        constructed.append(spec)
        entered.set()
        assert unblock.wait(1.0)
        return engine

    monkeypatch.setattr(nemotron_engine, "_NEMOTRON_CACHE", {})
    monkeypatch.setattr(nemotron_engine, "NemotronGGUFEngine", construct)
    monkeypatch.setattr(nemotron_engine, "register_idle_cleanup", lambda *_args, **_kwargs: None)
    results = []
    first = threading.Thread(target=lambda: results.append(nemotron_engine.get_nemotron_engine(model_path)), daemon=True)
    second = threading.Thread(target=lambda: results.append(nemotron_engine.get_nemotron_engine(model_path)), daemon=True)
    first.start()
    assert entered.wait(0.5)
    second.start()
    time.sleep(0.05)
    constructions_while_blocked = len(constructed)
    unblock.set()
    first.join(1.0)
    second.join(1.0)
    assert results == [engine, engine]
    assert constructions_while_blocked == 1
    assert len(constructed) == 1


def test_native_drain_deadline_keeps_partial_text_only_for_diagnostics(monkeypatch):
    engine = _StreamEngine()
    session = nemotron_engine.NemotronStreamTranscriber(engine=engine)

    class Dll(_StreamDll):
        def __init__(self):
            super().__init__()
            self.finished = False
            self.returned = False

        def nemo_speech_asr_stream_finish(self, _stream):
            self.finished = True
            return 0

        def nemo_speech_asr_stream_next(self, _stream, output):
            if self.finished and not self.returned:
                self.returned = True
                output._obj.value = 55
                return 0
            return 1

        def nemo_speech_asr_result_transcript(self, _result, _index):
            session._deadline = 0.0
            return b"partial opening"

        def nemo_speech_asr_result_destroy(self, _result):
            return None

    dll = Dll()
    monkeypatch.setattr(nemotron_engine, "get_nemo_dll", lambda: dll)
    monkeypatch.setattr(session, "_open_stream", lambda _dll: setattr(session._stream, "value", 42) or True)
    session.start_session()
    session.submit_frame(np.ones(160, dtype=np.float32), 16000)
    session.end_session()
    assert session._done.wait(1.0)
    assert session._text == "partial opening"
    assert session.had_failures()
    assert not session.completed_successfully()
    assert session.collect() == ""

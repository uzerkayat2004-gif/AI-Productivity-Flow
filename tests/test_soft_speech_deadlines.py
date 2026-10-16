"""Optional re-decode timeouts and stream cancels never kill the speech worker (B2, M-V-1).

Uses a synthetic worker process (tests/fixtures/slow_speech_worker.py) that
speaks the real NativeASRClient pipe protocol; no native library is loaded.
"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow import nemotron_engine
from voice_flow import nemotron_worker_client as transport

FIXTURE = Path(__file__).parent / "fixtures" / "slow_speech_worker.py"


def _engine(monkeypatch, *, recognize_seconds=0.4, push_seconds=0.002, open_seconds=0.0):
    monkeypatch.setattr(transport, "WORKER_SCRIPT", FIXTURE)
    monkeypatch.setenv("SLOW_WORKER_OPEN_SECONDS", str(open_seconds))
    monkeypatch.setenv("SLOW_WORKER_RECOGNIZE_SECONDS", str(recognize_seconds))
    monkeypatch.setenv("SLOW_WORKER_PUSH_SECONDS", str(push_seconds))
    monkeypatch.setattr(nemotron_engine, "notify_models_available", lambda *_a: None)
    monkeypatch.setattr(nemotron_engine, "LiveSpeechEnhancer",
                        lambda **_k: SimpleNamespace(process=lambda audio, _rate: audio))
    engine = object.__new__(nemotron_engine.NemotronGGUFEngine)
    engine._native = transport.NativeASRClient("unused-synthetic-path")
    engine.fatal_error = None
    engine.rec_handle = ctypes.c_void_p(1)
    engine.model_path = Path("synthetic-soft-deadline.gguf").resolve()
    engine.spec = {"default_language": "en"}
    engine.metadata = {}
    engine.sample_rate = 16000
    engine._is_warm = True
    engine.lock = threading.RLock()
    engine._streams_idle = threading.Event()
    engine._streams_idle.set()
    engine._active_streams = 0
    engine._evict_when_idle = False
    engine._last_used = time.monotonic()
    engine.last_latency_ms = 0.0
    engine.total_transcriptions = 0
    engine.total_audio_seconds = 0.0
    engine.total_decode_seconds = 0.0
    return engine


def _close(engine):
    try:
        engine._native.close()
    except Exception:
        pass


def _speech(seconds=1.0):
    t = np.arange(int(seconds * 16000), dtype=np.float32) / 16000
    return (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _stream_dictation(engine, audio, *, frames=10):
    stream = nemotron_engine.NemotronStreamTranscriber(engine=engine)
    stream.start_session(model_ref="synthetic", deadline=time.monotonic() + 10)
    for frame in np.array_split(audio, frames):
        stream.submit_frame(frame, 16000)
    stream.end_session(deadline=time.monotonic() + 10)
    return stream


def test_twenty_back_to_back_dictations_with_timed_out_redecode_never_fail(monkeypatch):
    from voice_flow import main as main_module

    engine = _engine(monkeypatch, recognize_seconds=0.8)
    try:
        pid = engine._native._process.pid
        transcriber = SimpleNamespace(
            nemotron_engine=engine,
            transcribe=lambda audio, deadline=None, model_ref=None: engine.transcribe(audio, deadline=deadline),
        )
        app = object.__new__(main_module.VoiceFlowApp)
        app.transcriber = transcriber
        monkeypatch.setattr(main_module, "_polishing_enabled", lambda: True)
        monkeypatch.setattr(nemotron_engine, "is_nemotron_model", lambda _ref: True)
        # Budget far below the worker's decode time: every re-decode that is
        # attempted must time out softly.
        monkeypatch.setattr(main_module, "FULL_REDECODE_BUDGET_SECONDS", 0.3)
        monkeypatch.setattr(main_module, "FULL_REDECODE_DEFAULT_RTF", 0.01)
        session = SimpleNamespace(stt_model_ref="local/nemotron-speech-streaming-en-0.6b")
        audio = _speech(1.0)
        failures, texts, attempted = 0, [], 0
        for _ in range(20):
            stream = _stream_dictation(engine, audio)
            text = stream.collect(timeout=5)
            if not text or stream.had_failures() or stream.fatal_error is not None:
                failures += 1
            texts.append(text)
            # Forget the learned speed so every dictation really attempts the
            # re-decode and leaves it running into the next dictation.
            app._redecode_rtf_floor = 0.0
            redecoded = app._full_redecode_short_recording(session, audio, 1.0, time.monotonic() + 4.0)
            assert redecoded == ""  # soft timeout -> keep the stream text
            if app._redecode_rtf_floor > 0.15:
                attempted += 1
            time.sleep(0.05)  # next dictation starts while the decode still runs
        assert failures == 0, texts
        assert all(t == "stream text." for t in texts)
        assert engine.fatal_error is None and engine._native.error is None
        assert engine._native._process.pid == pid and engine._native._process.poll() is None
        with nemotron_engine._FAILURE_LOCK:
            assert str(engine.model_path) not in nemotron_engine._FAILED_MODELS
        # Every re-decode timed out softly (and taught the speed floor).
        assert attempted == 20
    finally:
        _close(engine)


def test_redecode_skipped_when_clip_cannot_fit_budget(monkeypatch):
    from voice_flow import main as main_module

    calls = []
    app = object.__new__(main_module.VoiceFlowApp)
    app.transcriber = SimpleNamespace(
        nemotron_engine=SimpleNamespace(realtime_factor=lambda: 0.8),
        transcribe=lambda *a, **k: calls.append(1) or "text",
    )
    monkeypatch.setattr(main_module, "_polishing_enabled", lambda: True)
    monkeypatch.setattr(nemotron_engine, "is_nemotron_model", lambda _ref: True)
    session = SimpleNamespace(stt_model_ref="local/nemotron-speech-streaming-en-0.6b")
    # 10 s at RTF 0.8 needs ~8.4 s; the 2.5 s budget cannot hold it.
    assert app._full_redecode_short_recording(session, _speech(0.5), 10.0, time.monotonic() + 4.0) == ""
    assert calls == []
    # A 1 s clip at the same speed fits and runs.
    assert app._full_redecode_short_recording(session, _speech(0.5), 1.0, time.monotonic() + 4.0) == "text"
    assert calls == [1]


def test_discarded_stream_keeps_worker_and_fallback_decode_succeeds(monkeypatch):
    # Slow pushes guarantee a native call is in flight when the stream is
    # discarded (recorder overflow / queue overflow / user cancel paths).
    engine = _engine(monkeypatch, recognize_seconds=0.05, push_seconds=0.05)
    try:
        pid = engine._native._process.pid
        audio = _speech(1.0)
        stream = nemotron_engine.NemotronStreamTranscriber(engine=engine)
        stream.start_session(model_ref="synthetic", deadline=time.monotonic() + 10)
        for frame in np.array_split(audio, 40):
            stream.submit_frame(frame, 16000)
        time.sleep(0.12)
        stream.discard()
        assert stream._done.wait(3)
        assert stream.had_failures() is True
        assert stream.fatal_error is None  # a cancel is not a dead worker
        assert engine.fatal_error is None and engine._native.error is None
        assert engine._native._process.pid == pid and engine._native._process.poll() is None
        # Whole-recording recovery runs on the same live worker.
        text = engine.transcribe(audio, deadline=time.monotonic() + 5)
        assert text == "whole recording text."
    finally:
        _close(engine)


def test_queue_overflow_cancel_keeps_worker_alive(monkeypatch):
    engine = _engine(monkeypatch, recognize_seconds=0.05, push_seconds=0.02)
    try:
        stream = nemotron_engine.NemotronStreamTranscriber(engine=engine)
        stream._queue = __import__("queue").Queue(maxsize=4)
        stream.start_session(model_ref="synthetic", deadline=time.monotonic() + 10)
        for frame in np.array_split(_speech(1.0), 60):
            stream.submit_frame(frame, 16000)
        assert stream._done.wait(3)
        assert stream.had_failures() is True
        assert stream.fatal_error is None
        assert engine._native.error is None and engine._native._process.poll() is None
        assert engine.transcribe(_speech(1.0), deadline=time.monotonic() + 5) == "whole recording text."
    finally:
        _close(engine)


def test_pipeline_fallback_runs_after_discarded_stream(monkeypatch):
    """main treats a stream without a dead-worker error as recoverable."""
    from voice_flow import main as main_module
    import inspect

    source = inspect.getsource(main_module.VoiceFlowApp._process_dictation_pipeline)
    # The fallback is skipped only for a recorded native failure, and a soft
    # cancel never records one (fatal_error stays None).
    assert "native_failure" in source
    engine = _engine(monkeypatch, recognize_seconds=0.05, push_seconds=0.05)
    try:
        stream = _stream_dictation(engine, _speech(1.0), frames=30)
        stream.discard()
        assert stream._done.wait(3)
        assert getattr(stream, "fatal_error", None) is None
    finally:
        _close(engine)


def test_abandoned_stream_open_does_not_leak_a_busy_native_stream(monkeypatch):
    engine = _engine(monkeypatch, open_seconds=0.3)
    try:
        client = engine._native
        with pytest.raises(transport.NativeASRAbandonedError):
            client.call("stream_open", handle=1, deadline=time.monotonic() + 0.05)
        # The orphaned stream is closed by the RPC thread, so the recognizer
        # is free for the next dictation instead of reporting busy forever.
        reply = client.call("stream_open", handle=1, timeout=5)
        assert reply["status"] == 0 and reply["handle"]
        client.call("stream_close", handle=reply["handle"], timeout=2)
        assert engine.transcribe(_speech(1.0), deadline=time.monotonic() + 5) == "whole recording text."
        assert client.error is None
    finally:
        _close(engine)


def test_abandoned_stream_close_still_runs(monkeypatch):
    engine = _engine(monkeypatch)
    try:
        client = engine._native
        opened = client.call("stream_open", handle=1, timeout=5)
        # A slow request ahead of the close makes the close wait in the queue;
        # its caller gives up, but the close must still reach the worker.
        slow = threading.Thread(target=lambda: client.call("sleep", seconds=0.3, timeout=5))
        slow.start()
        time.sleep(0.05)
        with pytest.raises(transport.NativeASRAbandonedError):
            client.call("stream_close", handle=opened["handle"], deadline=time.monotonic() + 0.05)
        slow.join(3)
        reply = client.call("stream_open", handle=1, timeout=5)
        assert reply["status"] == 0 and reply["handle"]
        assert client.error is None
    finally:
        _close(engine)

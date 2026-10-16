"""Synthetic process-boundary proofs; never loads a native speech library."""
import ast
import ctypes
import importlib.util
from pathlib import Path
import threading
import time
import types
import sys
import __future__
import logging
import struct
from dataclasses import dataclass

import numpy as np
import pytest
from voice_flow import nemotron_engine as engine_module
from voice_flow import nemotron_worker_client as transport


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(transport, "WORKER_SCRIPT", Path(__file__).parent / "fixtures" / "synthetic_native_worker.py")
    value = transport.NativeASRClient("unused-synthetic-path")
    yield value
    value.close()


def test_abrupt_native_death_is_typed_and_parent_survives(client):
    engine = engine_module.NemotronGGUFEngine.__new__(engine_module.NemotronGGUFEngine)
    engine._native, engine.fatal_error = client, None
    engine.rec_handle = ctypes.c_void_p(1)
    engine.model_path = Path("synthetic.gguf").resolve()
    engine.spec, engine.metadata, engine.sample_rate = {"default_language": "en"}, {}, 16000
    engine._is_warm = True
    start = time.monotonic()
    with pytest.raises(transport.NativeASRWorkerError):
        engine._transcribe_segment(np.zeros(160, dtype=np.float32), language="en")
    assert time.monotonic() - start < 2.0
    assert client._process.poll() == 73
    assert engine.fatal_error is client.error
    assert not engine.is_warm and not engine.rec_handle.value
    with pytest.raises(transport.NativeASRWorkerError) as caught:
        client.call("echo")
    assert caught.value is client.error
    assert client._process.poll() == 73


def test_dynamic_deadline_tightens_already_waiting_call(client):
    client.call("echo")
    limit = [time.monotonic() + 5]
    caught = []
    started = threading.Event()
    original_send = client._connection.send
    def send(value):
        original_send(value)
        started.set()
    client._connection.send = send
    def call():
        try:
            client.call("hang", deadline=lambda: limit[0])
        except transport.NativeASRBusyError as exc:
            caught.append(exc)
    thread = threading.Thread(target=call)
    thread.start()
    assert started.wait(2)
    limit[0] = time.monotonic() + 0.06
    thread.join(1)
    # A soft deadline abandons the reply; it never kills the shared worker.
    assert not thread.is_alive() and caught
    assert isinstance(caught[0], transport.NativeASRAbandonedError)
    assert client.error is None and client._process.poll() is None


def test_parent_lifetime_eof_reaps_worker_even_during_hung_call(client):
    sent, errors = threading.Event(), []
    original = client._connection.send
    def send(value):
        original(value)
        sent.set()
    client._connection.send = send
    def call():
        try:
            client.call("hang", timeout=5)
        except transport.NativeASRWorkerError as exc:
            errors.append(exc)
    thread = threading.Thread(target=call)
    thread.start()
    assert sent.wait(1)
    client._lifetime_writer.close()
    thread.join(1)
    assert not thread.is_alive() and errors
    assert client._process.poll() == 0
    client.close()
    assert client._lifetime_writer.closed and client._connection.closed
    assert not client._thread.is_alive()


def test_blocked_pipe_write_does_not_block_caller_deadline(client):
    client.call("stop_reading")
    start = time.monotonic()
    with pytest.raises(transport.NativeASRBusyError):
        client.call("echo", audio=b"\0" * (8 * 1024 * 1024), deadline=time.monotonic() + 0.1, timeout=0.4)
    assert time.monotonic() - start < 1
    # The wedged request outlives its hard timeout: the next caller detects
    # the stall and poisons the generation instead of waiting forever.
    with pytest.raises(transport.NativeASRWorkerError):
        client.call("echo", timeout=5)
    assert time.monotonic() - start < 2
    assert client._process.poll() is not None


def test_cancel_before_enqueue_never_sends_request(client):
    sent = []
    original = client._connection.send
    client._connection.send = lambda value: sent.append(value) or original(value)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(transport.NativeASRBusyError):
        client.call("echo", cancelled=cancel)
    assert sent == []
    assert client.error is None and client._process.poll() is None
    assert client.call("echo", audio=b"")["audio"] == b""


def test_expired_before_enqueue_preserves_healthy_worker(client):
    with pytest.raises(transport.NativeASRBusyError):
        client.call("echo", deadline=time.monotonic() - 1)
    assert client.error is None and client._process.poll() is None
    assert client.call("echo", audio=b"")["audio"] == b""


def test_cancel_after_submission_abandons_without_killing_worker(client):
    sent = threading.Event()
    cancel = threading.Event()
    original = client._connection.send
    def send(value):
        original(value)
        sent.set()
    client._connection.send = send
    errors = []
    def call():
        try:
            client.call("hang", cancelled=cancel, timeout=0.5)
        except transport.NativeASRBusyError as exc:
            errors.append(exc)
    thread = threading.Thread(target=call)
    thread.start()
    assert sent.wait(1)
    cancel.set()
    thread.join(1)
    assert not thread.is_alive() and len(errors) == 1
    assert isinstance(errors[0], transport.NativeASRAbandonedError)
    assert client.error is None and client._process.poll() is None
    # The abandoned native call is genuinely hung: once it outlives its own
    # hard timeout, the next caller poisons the generation.
    with pytest.raises(transport.NativeASRWorkerError):
        client.call("echo", timeout=5)
    assert client._process.poll() is not None


def test_late_response_after_soft_deadline_is_discarded_and_worker_survives(client):
    process = client._process.pid
    with pytest.raises(transport.NativeASRAbandonedError):
        client.call("late", deadline=time.monotonic() + 0.05)
    assert client.error is None
    # The next call queues behind the late reply, which is dropped; its own
    # reply is matched by id and returned intact.
    assert client.call("echo", audio=b"after", timeout=2)["audio"] == b"after"
    assert client._process.pid == process and client._process.poll() is None


def test_abandoned_request_never_reaches_the_worker(client):
    sent = []
    original = client._connection.send
    client._connection.send = lambda value: sent.append(value["op"]) or original(value)
    blocker = threading.Thread(target=lambda: client.call("late", timeout=2))
    blocker.start()
    end = time.monotonic() + 1
    while "late" not in sent and time.monotonic() < end:
        time.sleep(0.005)
    with pytest.raises(transport.NativeASRAbandonedError):
        client.call("echo", audio=b"skip", deadline=time.monotonic() + 0.05)
    blocker.join(2)
    assert client.call("echo", audio=b"ok", timeout=2)["audio"] == b"ok"
    assert sent.count("echo") == 1


def test_warm_client_is_persistent_and_float32_payload_exact(client):
    process = client._process.pid
    audio = np.arange(320, dtype=np.float32).tobytes()
    for _ in range(3):
        assert client.call("echo", audio=audio, count=320, rate=16000)["audio"] == audio
        assert client._process.pid == process


def test_background_fatal_load_does_not_wait_or_start_fallback():
    path = Path(engine_module.__file__).with_name("transcriber.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Transcriber")
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "_wait_for_model")
    module = ast.Module(body=[method], type_ignores=[])
    space = {"nemotron_engine": engine_module, "time": time, "threading": threading}
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), space)
    error = transport.NativeASRWorkerError("synthetic load failure")
    instance = types.SimpleNamespace(_local_model_name=lambda ref: ref,
                                     _native_load_errors={"nvidia/nemotron-test": error})
    start = time.monotonic()
    with pytest.raises(transport.NativeASRWorkerError) as caught:
        space["_wait_for_model"](instance, model_ref="nvidia/nemotron-test")
    assert caught.value is error
    assert time.monotonic() - start < 0.1


def test_waiting_construction_rechecks_failed_owner(monkeypatch, tmp_path):
    model = tmp_path / "synthetic.gguf"
    model.write_bytes(b"x")
    downloads = types.ModuleType("voice_flow.downloadable_models")
    downloads.get_model_spec = lambda _: None
    monkeypatch.setitem(sys.modules, downloads.__name__, downloads)
    entered, release = threading.Event(), threading.Event()
    calls, errors = [], []
    def construct(*args, **kwargs):
        calls.append(1)
        entered.set()
        assert release.wait(1)
        raise transport.NativeASRWorkerError("synthetic allocation abort")
    monkeypatch.setattr(engine_module, "NemotronGGUFEngine", construct)
    def get():
        try:
            engine_module.get_nemotron_engine(str(model))
        except transport.NativeASRWorkerError as exc:
            errors.append(exc)
    first, second = threading.Thread(target=get), threading.Thread(target=get)
    first.start()
    assert entered.wait(1)
    second.start()
    release.set()
    first.join(1)
    second.join(1)
    assert not first.is_alive() and not second.is_alive()
    assert len(calls) == 1 and len(errors) == 2


def test_construction_lock_observes_tightened_deadline():
    lock = threading.Lock()
    lock.acquire()
    limit, errors = [time.monotonic() + 5], []
    def wait():
        try:
            with engine_module._bounded_lock(lock, lambda: limit[0]):
                raise AssertionError("blocked lock unexpectedly acquired")
        except transport.NativeASRBusyError as exc:
            errors.append(exc)
    thread = threading.Thread(target=wait)
    thread.start()
    limit[0] = time.monotonic() + 0.05
    thread.join(1)
    lock.release()
    assert not thread.is_alive() and errors


@pytest.mark.parametrize("getter_name", ["get_cached_nemotron_engine", "get_nemotron_engine"])
def test_warm_cache_touch_does_not_wait_for_native_engine_lock(monkeypatch, tmp_path, getter_name):
    model = tmp_path / "synthetic-warm-lock.gguf"
    model.write_bytes(b"x")
    downloads = types.ModuleType("voice_flow.downloadable_models")
    downloads.get_model_spec = lambda _: None
    monkeypatch.setitem(sys.modules, downloads.__name__, downloads)
    engine = engine_module.NemotronGGUFEngine.__new__(engine_module.NemotronGGUFEngine)
    engine.lock = threading.Lock()
    engine._is_warm, engine.fatal_error = True, None
    engine._last_used = 0
    monkeypatch.setitem(engine_module._NEMOTRON_CACHE, str(model.resolve()), engine)
    monkeypatch.setattr(engine_module, "NativeASRClient", lambda *args: pytest.fail("Warm lookup must not spawn"))
    held, release, returned = threading.Event(), threading.Event(), threading.Event()
    values, errors = [], []
    def own_native():
        with engine.lock:
            held.set()
            release.wait(2)
    owner = threading.Thread(target=own_native)
    owner.start()
    assert held.wait(1)
    cancel = threading.Event()
    limit = [time.monotonic() + 5]
    def get():
        try:
            getter = getattr(engine_module, getter_name)
            kwargs = {"deadline": lambda: limit[0], "cancelled": cancel} if getter_name == "get_nemotron_engine" else {}
            values.append(getter(str(model), **kwargs))
        except Exception as exc:
            errors.append(exc)
        finally:
            returned.set()
    waiter = threading.Thread(target=get)
    waiter.start()
    limit[0] = time.monotonic() + 0.02
    cancel.set()
    try:
        assert returned.wait(0.2), "Warm cache touch blocked behind native engine lock"
        assert engine_module._CACHE_LOCK.acquire(timeout=0.1), "Warm lookup retained global cache lock"
        engine_module._CACHE_LOCK.release()
        assert errors == [] and values == [engine]
        assert engine._last_used > 0
    finally:
        release.set()
        owner.join(1)
        waiter.join(1)
    assert not owner.is_alive() and not waiter.is_alive()


def test_new_explicit_action_can_reset_after_cooldown_only_once(monkeypatch, tmp_path):
    model = tmp_path / "synthetic-retry.gguf"
    key = str(model.resolve())
    downloads = types.ModuleType("voice_flow.downloadable_models")
    downloads.get_model_spec = lambda _: None
    monkeypatch.setitem(sys.modules, downloads.__name__, downloads)
    error = transport.NativeASRWorkerError("synthetic failure")
    engine_module._FAILED_MODELS[key] = error
    engine_module._FAILED_AT[key] = time.monotonic()
    first_action = object()
    with pytest.raises(transport.NativeASRWorkerError):
        engine_module.retry_failed_model(str(model), first_action)
    assert engine_module._FAILED_MODELS[key] is error
    engine_module._FAILED_AT[key] -= 6
    assert not engine_module.retry_failed_model(str(model), first_action)
    assert key in engine_module._FAILED_MODELS
    old_session = types.SimpleNamespace(fatal_error=error)
    second_action = object()
    assert engine_module.retry_failed_model(str(model), second_action)
    assert key not in engine_module._FAILED_MODELS
    assert old_session.fatal_error is error
    engine_module._FAILED_MODELS[key] = error
    engine_module._FAILED_AT[key] = time.monotonic() - 6
    assert not engine_module.retry_failed_model(str(model), second_action)
    assert key in engine_module._FAILED_MODELS


def test_child_rejects_recognize_until_close_and_owns_results():
    path = Path(engine_module.__file__).with_name("nemotron_native_worker.py")
    spec = importlib.util.spec_from_file_location("synthetic_owner_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    events = []
    class Stub:
        def nemo_speech_asr_recognition_options_default(self):
            options = module.abi._RecognitionOptions()
            options.size = ctypes.sizeof(options)
            return options
        def nemo_speech_asr_streaming_recognize(self, rec, options, out):
            assert not options._obj.interim_results
            events.append("open")
            out._obj.value = 22
            return 0
        def nemo_speech_asr_stream_close(self, stream):
            events.append("close")
        def nemo_speech_asr_recognize_f32(self, rec, options, audio, count, rate, out):
            events.append("recognize")
            out._obj.value = 33
            return 0
        def nemo_speech_asr_result_transcript(self, result, index):
            events.append("copy")
            return b"synthetic"
        def nemo_speech_asr_result_destroy(self, result):
            events.append("destroy_result")
        def nemo_speech_asr_destroy(self, rec):
            events.append("destroy_recognizer")
    owner = module.NativeOwner()
    owner.dll = Stub()
    owner.recognizers[10] = ctypes.c_void_p(11)
    opened = owner.dispatch("stream_open", {"handle": 10, "streaming": True})
    values = {"handle": 10, "audio": b"\0" * 16, "count": 4, "rate": 16000}
    assert owner.dispatch("recognize", values)["busy"]
    assert events == ["open"]
    owner.dispatch("stream_close", {"handle": opened["handle"]})
    response = owner.dispatch("recognize", values)
    assert response["result"]["text"] == b"synthetic"
    assert events == ["open", "close", "recognize", "copy", "destroy_result"]
    owner.dispatch("stream_open", {"handle": 10, "streaming": True})
    owner.dispatch("recognizer_close", {"handle": 10})
    assert events[-2:] == ["close", "destroy_recognizer"]
    assert not owner.streams and not owner.recognizers


@pytest.mark.parametrize("operation", ["stream_open", "warm"])
def test_child_closes_partial_stream_on_setup_failure_exactly_once(operation):
    path = Path(engine_module.__file__).with_name("nemotron_native_worker.py")
    spec = importlib.util.spec_from_file_location("synthetic_partial_stream_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    closed, retained = [], []
    class Stub:
        def nemo_speech_asr_recognition_options_default(self):
            options = module.abi._RecognitionOptions()
            options.size = ctypes.sizeof(options)
            return options
        def nemo_speech_asr_streaming_recognize(self, rec, options, out):
            retained.append(options._obj)
            out._obj.value = 77
            return 7
        def nemo_speech_asr_stream_close(self, stream):
            assert retained[0].language_code == b"en"
            closed.append(stream.value)
    owner = module.NativeOwner()
    owner.dll = Stub()
    owner.recognizers[10] = ctypes.c_void_p(11)
    response = owner.dispatch(operation, {"handle": 10, "language": "en", "streaming": True})
    assert response["status"] == 7
    assert response.get("handle", 0) == 0
    assert closed == [77] and owner.streams == {}
    owner.dispatch("stream_close", {"handle": 77})
    assert closed == [77]


def test_queue_saturation_wakes_concurrent_callers_without_respawn(client):
    client.call("echo")
    import queue
    client._requests = queue.Queue(maxsize=1)
    sent, errors = threading.Event(), []
    original = client._connection.send
    def send(value):
        original(value)
        sent.set()
    client._connection.send = send
    def call(op):
        try:
            client.call(op, timeout=0.5, audio=b"1234")
        except transport.NativeASRWorkerError as exc:
            errors.append(exc)
    first = threading.Thread(target=call, args=("hang",))
    first.start()
    assert sent.wait(1)
    second = threading.Thread(target=call, args=("echo",))
    second.start()
    end = time.monotonic() + 1
    while client._requests.empty() and time.monotonic() < end:
        time.sleep(0.005)
    assert not client._requests.empty()
    # A full request queue is back-pressure, not a dead worker.
    with pytest.raises(transport.NativeASRBusyError):
        client.call("echo", audio=b"1234")
    assert client.error is None
    first.join(1)
    second.join(1)
    assert not first.is_alive() and not second.is_alive()
    assert len(errors) == 2 and client._process.poll() is not None

    client._thread.join(timeout=1)
    assert client._audio_bytes == 0


@pytest.mark.parametrize("incomplete,collect_failure,already_closed", [(True, False, False), (False, False, False), (False, True, False), (True, False, True)])
def test_actual_pipeline_retains_recording_and_skips_fatal_fallback(incomplete, collect_failure, already_closed):
    path = Path(engine_module.__file__).with_name("main.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "VoiceFlowApp")
    names = {"_process_dictation_pipeline", "_end_stream_session", "_reset_to_idle"}
    methods = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    state = types.SimpleNamespace(PROCESSING="processing", IDLE="idle")
    session_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "DictationSession")
    space = {"time": time, "threading": threading, "dataclass": dataclass, "log": logging.getLogger("synthetic"),
             "DictationState": state, "POST_RELEASE_WORK_BUDGET_SECONDS": 3,
             "INJECTION_RESERVE_SECONDS": 0.1, "WHOLE_BUFFER_RECOVERY_RESERVE_SECONDS": 0.1,
             "_complete_recording_budget_seconds": lambda duration: 5,
             "_call_with_optional_deadline": lambda fn, *args, **kwargs: fn(*args, **kwargs)}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[session_class, *methods], type_ignores=[])), str(path), "exec",
                 flags=__future__.annotations.compiler_flag), space)
    App = type("App", (), {name: space[name] for name in names})
    app = App()
    error = transport.NativeASRWorkerError("synthetic native worker exit")
    style = types.SimpleNamespace(app_name="fixture", category="fixture", style_id="fixture")
    session = space["DictationSession"](1, "fixture", "fixture", "fixture", time.monotonic(), resolved_style=style)
    stream = types.SimpleNamespace(fatal_error=None if collect_failure else error, live_frames=True,
                                   pending_count=lambda: 0)
    stream.end_session = lambda: None
    stream.discard = lambda: setattr(stream, "fatal_error", None)
    def collect(**kwargs):
        raise error
    stream.collect = collect
    app._stream_stt, app._stream_session_owner = stream, session
    app.session, app.state = session, state.PROCESSING
    app._state_lock, app.processing_lock = threading.RLock(), threading.Lock()
    app._session_was_cancelled = lambda session: False
    app._stream_had_failures = lambda stream: stream.fatal_error is not None
    app._set_hotkeys_recording_state = lambda recording: None
    app.audio = types.SimpleNamespace(stream_input_incomplete=incomplete)
    app._release_session_model_resource = lambda session: None
    history, deferred, fallbacks = [], [], []
    app._history_update = lambda record, **values: history.append(values)
    app._defer_history_insert = lambda recovery, *args, **values: deferred.append((recovery, values))
    app._overlay_call = lambda *args: None
    app._stop_audio_flow_pipeline = lambda: pytest.fail("Audio owner must remain untouched")
    app._cancel_video_from_screen = lambda *args: pytest.fail("Video owner must remain untouched")
    app.transcriber = types.SimpleNamespace(transcribe=lambda *args, **kwargs: fallbacks.append(1) or "wrong")
    recording = np.ones(320, dtype=np.float32)
    recovery = {"audio_buffer": recording, "audio_path": "synthetic.wav"}
    if already_closed:
        app._end_stream_session(discard=True, owner=session)
        assert app._native_session_failures[id(session)] == (session, error)
        assert stream.fatal_error is None
        app._stream_stt = None
    app._process_dictation_pipeline(session, recording, 0.02, use_streaming=True, recovery=recovery)
    assert fallbacks == []
    assert history[-1]["status"] == "transcription_failed"
    assert history[-1]["insertion_status"] == "not_attempted"
    assert deferred[-1][0] is recovery and recovery["audio_buffer"] is recording
    assert recovery["audio_path"] == "synthetic.wav"
    assert app.state == state.IDLE and app.session is None
    assert getattr(app, "_native_session_failures", {}) == {}


@pytest.mark.parametrize("processing", [False, True])
def test_actual_cancel_preserves_archive_and_cleans_recording_failure_marker(processing):
    path = Path(engine_module.__file__).with_name("main.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "VoiceFlowApp")
    session_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "DictationSession")
    transition = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_capture_transition")
    names = {"_on_dictation_cancel", "_end_stream_session"}
    methods = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    state = types.SimpleNamespace(RECORDING="recording", PROCESSING="processing", IDLE="idle")
    space = {"time": time, "threading": threading, "dataclass": dataclass,
             "log": logging.getLogger("synthetic"), "DictationState": state,
             "config": types.SimpleNamespace(sample_rate=16000)}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[transition, session_class, *methods], type_ignores=[])),
                 str(path), "exec", flags=__future__.annotations.compiler_flag), space)
    app = type("App", (), {name: space[name] for name in names})()
    session = space["DictationSession"](1, "fixture", "fixture", "fixture", time.monotonic())
    app.session, app.state = session, state.PROCESSING if processing else state.RECORDING
    app._state_lock = threading.RLock()
    recording = np.ones(320, dtype=np.float32)
    error = transport.NativeASRWorkerError("synthetic native death")
    stream = types.SimpleNamespace(fatal_error=error, end_session=lambda: None)
    stream.discard = lambda: setattr(stream, "fatal_error", None)
    app._stream_stt, app._stream_session_owner = stream, session
    app.audio = types.SimpleNamespace(stop=lambda: recording)
    app._pending_recovery = ({id(session): {"audio_buffer": recording, "done": threading.Event()}}
                             if processing else {})
    archived, history = [], []
    app._start_recovery_archive = lambda audio, recovery: archived.append((audio, recovery))
    app._defer_history_insert = lambda recovery, owner, duration, **values: history.append((recovery, owner, values))
    app._release_session_model_resource = lambda owner: None
    app._set_hotkeys_recording_state = lambda value: None
    app._overlay_call = lambda *args: None
    app._stop_audio_flow_pipeline = lambda: pytest.fail("Audio owner must remain untouched")
    app._cancel_video_from_screen = lambda *args: pytest.fail("Video owner must remain untouched")
    assert app._on_dictation_cancel()
    assert archived[0][0] is recording
    assert history[0][0] is archived[0][1] and history[0][1] is session
    assert history[0][2]["status"] == "cancelled"
    assert history[0][2]["insertion_status"] == "not_attempted"
    assert app.session is None and app.state == state.IDLE
    if processing:
        assert app._native_session_failures[id(session)] == (session, error)
    else:
        assert app._native_session_failures == {}


def test_synthetic_warm_ipc_benchmark(client):
    client.call("echo")
    timings = []
    audio = np.ones(2560, dtype=np.float32).tobytes()
    for _ in range(30):
        start = time.perf_counter()
        assert client.call("echo", audio=audio)["audio"] == audio
        timings.append((time.perf_counter() - start) * 1000)
    print("synthetic_ipc_frame_bytes=10240 median_ms=%.3f p95_ms=%.3f" %
          (np.median(timings), np.percentile(timings, 95)))
    timings = []
    audio = np.ones(16000 * 30, dtype=np.float32).tobytes()
    for _ in range(10):
        start = time.perf_counter()
        assert client.call("echo", audio=audio)["audio"] == audio
        timings.append((time.perf_counter() - start) * 1000)
    print("synthetic_ipc_recording_bytes=1920000 median_ms=%.3f p95_ms=%.3f" %
          (np.median(timings), np.percentile(timings, 95)))


def test_failed_create_status_is_not_marked_warm_or_fallback(monkeypatch, tmp_path):
    model = tmp_path / "synthetic-create.gguf"
    model.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 0, 0) + b"\0" * (1024 * 1024))
    closed = []
    class Client:
        def __init__(self, *args):
            pass
        def call(self, op, **values):
            assert op == "create"
            return {"status": 7, "handle": 0}
        def close(self):
            closed.append(True)
    monkeypatch.setattr(engine_module, "NativeASRClient", Client)
    monkeypatch.setattr(engine_module, "_ensure_nemo_speech_binaries", lambda: tmp_path / "unused.dll")
    with pytest.raises(transport.NativeASRWorkerError) as caught:
        engine_module.NemotronGGUFEngine(model)
    assert "status 7" in str(caught.value)
    assert closed == [True]
    key = str(model.resolve())
    assert engine_module._FAILED_MODELS[key] is caught.value
    assert key in engine_module._FAILED_AT and key not in engine_module._NEMOTRON_CACHE


@pytest.mark.parametrize("operation", ["echo", "crash", "hang"])
def test_audio_budget_releases_after_success_failure_and_timeout(client, monkeypatch, operation):
    monkeypatch.setattr(transport, "MAX_AUDIO_BYTES", 8)
    if operation == "echo":
        assert client.call(operation, audio=b"12345678")["audio"] == b"12345678"
    else:
        with pytest.raises(transport.NativeASRWorkerError):
            client.call(operation, audio=b"12345678", timeout=0.1)
    client._thread.join(timeout=1.0) if operation != "echo" else None
    assert client._audio_bytes == 0


def test_audio_budget_rejects_queued_audio_without_poisoning_owner(client, monkeypatch):
    monkeypatch.setattr(transport, "MAX_AUDIO_BYTES", 8)
    results = []
    first = threading.Thread(target=lambda: results.append(client.call("late", audio=b"12345678")))
    first.start()
    end = time.monotonic() + 1
    while client._audio_bytes != 8 and time.monotonic() < end:
        time.sleep(0.002)
    assert client._audio_bytes == 8
    with pytest.raises(transport.NativeASRBusyError):
        client.call("echo", audio=b"x")
    assert client.error is None
    first.join(timeout=2)
    assert len(results) == 1
    assert client._audio_bytes == 0
    assert client.call("echo", audio=b"next")["audio"] == b"next"


def test_audio_budget_releases_cancelled_and_drained_requests(client, monkeypatch):
    monkeypatch.setattr(transport, "MAX_AUDIO_BYTES", 8)
    cancelled = threading.Event()
    errors = []
    def invoke(op, audio, cancel=None):
        try:
            client.call(op, audio=audio, cancelled=cancel, timeout=0.5)
        except (transport.NativeASRWorkerError, transport.NativeASRBusyError) as exc:
            errors.append(exc)
    first = threading.Thread(target=invoke, args=("hang", b"1234", cancelled))
    second = threading.Thread(target=invoke, args=("echo", b"5678"))
    first.start()
    second.start()
    end = time.monotonic() + 1
    while client._audio_bytes != 8 and time.monotonic() < end:
        time.sleep(0.002)
    assert client._audio_bytes == 8
    cancelled.set()
    first.join(timeout=2)
    second.join(timeout=2)
    client._thread.join(timeout=2)
    assert len(errors) == 2
    assert client._audio_bytes == 0


def test_explicit_retry_never_waits_for_busy_engine_lock(monkeypatch, tmp_path):
    key = str((tmp_path / "nemotron-busy.gguf").resolve())
    downloads = types.ModuleType("voice_flow.downloadable_models")
    downloads.get_model_spec = lambda _: None
    monkeypatch.setitem(sys.modules, downloads.__name__, downloads)
    error = transport.NativeASRWorkerError("synthetic failure")
    monkeypatch.setitem(engine_module._FAILED_MODELS, key, error)
    monkeypatch.setitem(engine_module._FAILED_AT, key, time.monotonic() - 6)
    locked = threading.Event()
    release = threading.Event()
    lock = threading.RLock()
    def hold():
        with lock:
            locked.set()
            release.wait(2)
    holder = threading.Thread(target=hold)
    holder.start()
    assert locked.wait(1)
    stale = types.SimpleNamespace(lock=lock, _active_streams=0,
                                 close=lambda: pytest.fail("must not close busy owner"))
    monkeypatch.setitem(engine_module._NEMOTRON_CACHE, key, stale)
    try:
        started = time.monotonic()
        with pytest.raises(transport.NativeASRBusyError):
            engine_module.retry_failed_model(key, object())
        assert time.monotonic() - started < 0.2
        assert engine_module._FAILED_MODELS[key] is error
        assert engine_module._NEMOTRON_CACHE[key] is stale
        source = Path(engine_module.__file__).with_name("transcriber.py")
        tree = ast.parse(source.read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Transcriber")
        methods = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                   and node.name in ("begin_native_retry", "prepare_model_async")]
        namespace = {"nemotron_engine": engine_module, "threading": types.SimpleNamespace(
            Thread=lambda *args, **kwargs: pytest.fail("busy retry must not create a loader"))}
        exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec",
                     flags=__future__.annotations.compiler_flag), namespace)
        transcriber_type = type("RetryTranscriber", (), {
            name: namespace[name] for name in ("begin_native_retry", "prepare_model_async")})
        transcriber = transcriber_type()
        transcriber._local_model_name = lambda model: key
        transcriber._lock = threading.Lock()
        demand = object()
        started = time.monotonic()
        assert transcriber.prepare_model_async(key, lease=demand) is demand
        assert time.monotonic() - started < 0.2
        assert isinstance(transcriber._native_load_errors[key], transport.NativeASRBusyError)
    finally:
        release.set()
        holder.join(timeout=1)


@pytest.mark.parametrize("failure_type", [RuntimeError, MemoryError])
def test_rpc_thread_start_failure_reaps_child_and_closes_handles(monkeypatch, failure_type):
    monkeypatch.setattr(transport, "WORKER_SCRIPT", Path(__file__).parent / "fixtures" / "synthetic_native_worker.py")
    children = []
    popen = transport.subprocess.Popen
    def capture_child(*args, **kwargs):
        process = popen(*args, **kwargs)
        children.append(process)
        return process
    monkeypatch.setattr(transport.subprocess, "Popen", capture_child)
    start = threading.Thread.start
    def fail_rpc_thread(thread):
        if thread.name == "native-asr-rpc":
            raise failure_type("synthetic thread resource failure")
        return start(thread)
    monkeypatch.setattr(threading.Thread, "start", fail_rpc_thread)
    client = transport.NativeASRClient.__new__(transport.NativeASRClient)
    with pytest.raises(transport.NativeASRWorkerError) as caught:
        client.__init__("unused-synthetic-path")
    assert isinstance(caught.value.__cause__, failure_type)
    assert len(children) == 1 and children[0].poll() is not None
    assert client._closed.is_set()
    assert client._lifetime_writer.closed
    assert client._connection.closed
    assert not client._thread.is_alive()
    assert client.error is caught.value


@pytest.mark.parametrize("operation", ["send", "recv"])
def test_ipc_memory_error_is_typed_and_releases_audio_budget(client, monkeypatch, operation):
    def exhaust_memory(*args, **kwargs):
        raise MemoryError("synthetic IPC allocation failure")
    monkeypatch.setattr(client._connection, operation, exhaust_memory)
    with pytest.raises(transport.NativeASRWorkerError) as caught:
        client.call("echo", audio=b"12345678", timeout=1)
    client._thread.join(timeout=1)
    assert client._audio_bytes == 0
    assert client._process.poll() is not None
    assert client._connection.closed and client._lifetime_writer.closed
    assert client.error is caught.value
    with pytest.raises(transport.NativeASRWorkerError) as repeated:
        client.call("echo")
    assert repeated.value is caught.value



def test_failed_warm_status_closes_owner_and_never_publishes_warm(monkeypatch, tmp_path):
    model = tmp_path / "synthetic-warm.gguf"
    model.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 0, 0) + b"\0" * (1024 * 1024))
    closed, calls = [], []
    class Client:
        def __init__(self, *args):
            pass
        def call(self, op, **values):
            calls.append(op)
            if op == "create":
                return {"status": 0, "handle": 42}
            assert op == "warm"
            assert values["handle"] == 42 and values["streaming"] is True
            return {"status": 7}
        def close(self):
            closed.append(True)
    monkeypatch.setattr(engine_module, "NativeASRClient", Client)
    monkeypatch.setattr(engine_module, "_ensure_nemo_speech_binaries", lambda: tmp_path / "unused.dll")
    instance = engine_module.NemotronGGUFEngine.__new__(engine_module.NemotronGGUFEngine)
    with pytest.raises(transport.NativeASRWorkerError) as caught:
        instance.__init__(model)
    assert "status 7" in str(caught.value) and "recording retained" in str(caught.value)
    assert calls == ["create", "warm"] and closed == [True]
    assert instance._native is None and not instance._is_warm and not instance.is_warm
    assert not instance.rec_handle.value and instance.fatal_error is caught.value
    key = str(model.resolve())
    assert engine_module._FAILED_MODELS[key] is caught.value
    assert key in engine_module._FAILED_AT and key not in engine_module._NEMOTRON_CACHE
    downloads = types.ModuleType("voice_flow.downloadable_models")
    downloads.get_model_spec = lambda _: None
    monkeypatch.setitem(sys.modules, downloads.__name__, downloads)
    with pytest.raises(transport.NativeASRWorkerError) as repeated:
        engine_module.get_nemotron_engine(model)
    assert repeated.value is caught.value
    instance.close()
    assert closed == [True]

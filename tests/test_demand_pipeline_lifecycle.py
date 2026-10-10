"""Demand-driven model lifetime regressions at the dictation coordinator seam."""
from __future__ import annotations

import threading
import json
from types import SimpleNamespace
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np

import voice_flow.main as main
from voice_flow.main import DictationSession, DictationState, VoiceFlowApp


class _Lease:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.released = False

    def release(self) -> None:
        if not self.released:
            self.released = True
            self.events.append("release")


def _recording_app(session, events: list[str], lease: _Lease) -> VoiceFlowApp:
    app = object.__new__(VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = DictationState.IDLE
    app.session = None
    app._record_watchdog = None
    app._capture_session = lambda: session
    app.audio = SimpleNamespace(
        begin_stream_input_buffering=lambda: events.append("buffer"),
        start=lambda: events.append("audio") or True,
        flush_stream_input_buffer=lambda: events.append("flush"),
        discard_stream_input_buffer=lambda: events.append("discard"),
        stop=lambda: np.ones(160, dtype=np.float32),
        level=0.0,
    )
    app.transcriber = SimpleNamespace(
        prepare_model_async=lambda model_ref, *, lease: events.append(f"prepare:{model_ref}") or lease,
    )
    app.hotkeys = SimpleNamespace(set_recording_state=lambda *_args: None)
    app.overlay = SimpleNamespace(show_recording=lambda **_kw: None, show_error=lambda *_args: None)
    app._start_stream_for_session = lambda _session: events.append("stream")
    app._start_window_tracker = lambda _session: None
    return app


def test_capture_starts_before_selected_stt_prepare_and_session_owns_lease(monkeypatch) -> None:
    events: list[str] = []
    lease = _Lease(events)
    session = DictationSession(
        123, "Editor", "smart_clean", "smart_clean", 0.0,
        stt_model_ref="local/faster-whisper-base.en",
    )
    app = _recording_app(session, events, lease)
    timers = []

    class Timer:
        def __init__(self, interval, function, args=()):
            self.interval = interval
            self.function = function
            self.args = args
            self.daemon = False
            self.started = False
            timers.append(self)

        def start(self):
            self.started = True

        def cancel(self):
            pass

    monkeypatch.setattr(main.storage, "get_setting", lambda key, default=None: True if key == "voice_flow_enabled" else default)
    monkeypatch.setattr("voice_flow.local_model_resources.acquire_model_use", lambda kind: lease)
    monkeypatch.setattr(main.threading, "Timer", Timer)

    assert app._on_dictation_start() is True
    assert events[:4] == ["buffer", "audio", "prepare:local/faster-whisper-base.en", "stream"]
    assert app.session.model_resource_lease is lease
    assert len(timers) == 1
    assert timers[0].started
    assert timers[0].args == (app.session,)


def test_unattachable_custom_session_releases_new_lease(monkeypatch) -> None:
    events: list[str] = []
    lease = _Lease(events)

    class FixedSession:
        __slots__ = ("target_hwnd", "app_title", "stt_model_ref")

        def __init__(self):
            self.target_hwnd = 123
            self.app_title = "Editor"
            self.stt_model_ref = "local/faster-whisper-base.en"

    app = _recording_app(FixedSession(), events, lease)
    monkeypatch.setattr(main.storage, "get_setting", lambda key, default=None: True if key == "voice_flow_enabled" else default)
    monkeypatch.setattr("voice_flow.local_model_resources.acquire_model_use", lambda kind: lease)

    assert app._on_dictation_start() is False
    assert lease.released
    assert app.state == DictationState.IDLE
    assert app.session is None


def test_replaced_session_during_audio_start_aborts_without_touching_new_capture(monkeypatch) -> None:
    events: list[str] = []
    lease = _Lease(events)
    old_session = DictationSession(1, "Old", "smart_clean", "smart_clean", 0.0)
    new_session = DictationSession(2, "New", "smart_clean", "smart_clean", 1.0)
    app = _recording_app(old_session, events, lease)
    timers: list[object] = []

    def replace_during_start():
        events.append("audio")
        app.session = new_session
        app.state = DictationState.RECORDING
        return True

    app.audio.start = replace_during_start
    app.audio.stop = lambda: events.append("stop")
    app.audio.discard_stream_input_buffer = lambda: events.append("discard")
    monkeypatch.setattr(main.storage, "get_setting", lambda key, default=None: True if key == "voice_flow_enabled" else default)
    monkeypatch.setattr("voice_flow.local_model_resources.acquire_model_use", lambda kind: lease)
    monkeypatch.setattr(main.threading, "Timer", lambda *_args, **_kwargs: timers.append(object()))

    assert app._on_dictation_start() is False
    assert lease.released
    assert not any(event.startswith("prepare:") for event in events)
    assert "stream" not in events
    assert "stop" not in events
    assert "discard" not in events
    assert timers == []
    assert app.session is new_session
    assert app.state == DictationState.RECORDING


def test_both_polishing_off_endpoints_request_polish_cleanup(monkeypatch) -> None:
    from voice_flow.gui import api_server
    from voice_flow import local_model_resources

    saved: dict[str, object] = {}
    cleanup_kinds: list[str] = []
    monkeypatch.setattr(
        api_server,
        "storage",
        SimpleNamespace(
            save_setting=lambda key, value: saved.__setitem__(key, value) or True,
            get_setting=lambda key, default=None: saved.get(key, default),
        ),
    )
    monkeypatch.setattr(local_model_resources, "request_model_cleanup", cleanup_kinds.append)
    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def post(path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Connection": "close"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        assert post("/api/settings/update", {"key": "polishing_enabled", "value": False})["success"]
        assert post("/api/voice-flow-polish/update", {"polishing_enabled": False})["success"]
    finally:
        server.shutdown()
        server.server_close()

    assert cleanup_kinds == ["polish", "polish"]


def test_pipeline_releases_speech_before_polishing(monkeypatch) -> None:
    events: list[str] = []
    lease = _Lease(events)
    session = DictationSession(
        123, "Editor", "smart_clean", "smart_clean", 0.0,
        resolved_style=SimpleNamespace(app_name="Editor", category="smart_clean", style_id="smart_clean", instruction="clean"),
        stt_model_ref="local/faster-whisper-base.en",
        model_resource_lease=lease,
    )
    app = object.__new__(VoiceFlowApp)
    app.processing_lock = threading.Lock()
    app._state_lock = threading.RLock()
    app.state = DictationState.PROCESSING
    app.session = session
    app.transcriber = SimpleNamespace(transcribe=lambda *_args, **_kwargs: events.append("transcribe") or "hello world")
    app.injector = SimpleNamespace(paste_text=lambda *_args, **_kwargs: True)
    app.overlay = SimpleNamespace(show_error=lambda *_args: None, show_done=lambda *_args: None, show_ready=lambda: None)
    app.hotkeys = SimpleNamespace(set_recording_state=lambda *_args: None)
    app.recent_dictations = set()
    app.last_successful_transcript = None
    app._finalize_text = lambda text, *_args, **_kwargs: events.append("polish") or text
    monkeypatch.setattr(main.storage, "update_dictation", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main, "detect_voice_command", lambda text: SimpleNamespace(command=None, content=text))

    app._process_dictation_pipeline(session, np.ones(16000, dtype=np.float32), 1.0)

    assert events.index("transcribe") < events.index("release") < events.index("polish")


def test_tiny_recording_releases_speech_lease(monkeypatch) -> None:
    events: list[str] = []
    lease = _Lease(events)
    session = DictationSession(123, "Editor", "smart_clean", "smart_clean", 0.0, model_resource_lease=lease)
    app = _recording_app(session, events, lease)
    app.state = DictationState.RECORDING
    app.session = session
    app.audio.stop = lambda: np.ones(10, dtype=np.float32)
    app._get_current_external_window = lambda: None
    app._is_internal_window = lambda _hwnd: False
    app._streaming_stt_enabled = lambda: False
    app._defer_history_insert = lambda *_args, **_kwargs: None

    assert app._on_dictation_finish() is False
    assert lease.released


def test_retired_pipeline_releases_only_its_lease_without_dropping_new_capture() -> None:
    old_events: list[str] = []
    new_events: list[str] = []
    old_lease = _Lease(old_events)
    new_lease = _Lease(new_events)
    old_session = DictationSession(1, "Old", "smart_clean", "smart_clean", 0.0, model_resource_lease=old_lease)
    new_session = DictationSession(2, "New", "smart_clean", "smart_clean", 1.0, model_resource_lease=new_lease)
    app = object.__new__(VoiceFlowApp)
    app.processing_lock = threading.Lock()
    app._state_lock = threading.RLock()
    app.state = DictationState.RECORDING
    app.session = new_session
    app.hotkeys = SimpleNamespace(set_recording_state=lambda *_args: None)

    app._process_dictation_pipeline(old_session, np.ones(16000, dtype=np.float32), 1.0)

    assert old_lease.released
    assert not new_lease.released
    assert app.state == DictationState.RECORDING
    assert app.session is new_session

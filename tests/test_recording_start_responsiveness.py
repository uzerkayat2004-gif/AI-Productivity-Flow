"""Event-controlled startup checks; no microphone, model, or desktop access."""
import threading

import pytest

import voice_flow.main as main
from voice_flow.main import DictationSession
from voice_flow.main import DictationState
from tests.test_demand_pipeline_lifecycle import _Lease, _recording_app


@pytest.mark.parametrize("dependency", ["context", "setting", "provider"])
def test_capture_and_recording_feedback_precede_advisory_startup(monkeypatch, dependency):
    events = []
    lease = _Lease(events)
    app = _recording_app(DictationSession(123, "Editor", "smart_clean", "smart_clean", 0.0), events, lease)
    app._capture_target_hwnd = lambda: 123
    entered = threading.Event()
    release = threading.Event()
    capture_ready = threading.Event()
    feedback_ready = threading.Event()
    failures = []
    original_context = (
        main.VoiceFlowApp._capture_session.__get__(app)
        if dependency == "setting" else app._capture_session
    )

    def blocked_context():
        entered.set()
        assert release.wait(5), "test did not release context"
        return original_context()

    def blocked_provider(_session):
        entered.set()
        assert release.wait(5), "test did not release provider"

    def get_setting(key, default=None):
        if dependency == "setting" and key == "style_autocleanup":
            entered.set()
            assert release.wait(5), "test did not release setting"
        return default

    app.audio.start = lambda: capture_ready.set() or True
    app.overlay.show_recording = lambda **_kw: feedback_ready.set()
    app._start_window_tracker = lambda _session: None
    app._capture_session = blocked_context if dependency == "context" else original_context
    app._start_stream_for_session = blocked_provider if dependency == "provider" else lambda _session: None
    monkeypatch.setattr(main.storage, "get_setting", get_setting)
    monkeypatch.setattr(main, "get_window_title_for_hwnd", lambda hwnd: "Editor")
    monkeypatch.setattr(main.style_engine, "resolve_for_target", lambda hwnd: None)
    monkeypatch.setattr("voice_flow.local_model_resources.acquire_model_use", lambda kind: lease)
    monkeypatch.setattr(main, "_warm_voice_gemini_transport", lambda *_args: None)
    monkeypatch.setattr(main.audio_flow_widget, "hide", lambda: None)
    app._stop_audio_flow_pipeline = lambda: None

    def start():
        try:
            app._on_dictation_start()
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=start, daemon=True)
    worker.start()
    try:
        assert entered.wait(5), "startup did not reach controlled dependency"
        assert capture_ready.is_set(), "advisory context blocked microphone capture"
        assert feedback_ready.is_set(), "advisory startup blocked recording feedback"
    finally:
        release.set()
        worker.join(5)
        if app._record_watchdog:
            app._record_watchdog.cancel()
    assert not worker.is_alive()
    assert not failures


def test_cancelled_device_open_never_shows_recording(monkeypatch):
    events = []
    lease = _Lease(events)
    app = _recording_app(DictationSession(123, "Editor", "smart_clean", "smart_clean", 0.0), events, lease)
    app._capture_target_hwnd = lambda: 123

    def cancelled_open():
        app.session = None
        app.state = DictationState.IDLE
        return True

    app.audio.start = cancelled_open
    app.overlay.show_recording = lambda **_kw: events.append("recording")
    app._stop_audio_flow_pipeline = lambda: None
    monkeypatch.setattr(main.audio_flow_widget, "hide", lambda: None)
    monkeypatch.setattr(main.storage, "get_setting", lambda key, default=None: default)
    monkeypatch.setattr("voice_flow.local_model_resources.acquire_model_use", lambda kind: lease)
    assert app._on_dictation_start() is False
    assert "recording" not in events


def test_context_keeps_destination_frozen_before_recording_ui(monkeypatch):
    events = []
    lease = _Lease(events)
    app = _recording_app(DictationSession(123, "Editor", "smart_clean", "smart_clean", 0.0), events, lease)
    foreground = {"hwnd": 123}
    app._capture_target_hwnd = lambda: foreground["hwnd"]
    app._capture_session = main.VoiceFlowApp._capture_session.__get__(app)
    resolved_targets = []
    app.overlay.show_recording = lambda **_kw: foreground.update(hwnd=999)
    app._stop_audio_flow_pipeline = lambda: None
    monkeypatch.setattr(main.audio_flow_widget, "hide", lambda: foreground.update(hwnd=777))
    monkeypatch.setattr(main.storage, "get_setting", lambda key, default=None: default)
    monkeypatch.setattr(main, "get_window_title_for_hwnd", lambda hwnd: "Editor")
    monkeypatch.setattr(main.style_engine, "resolve_for_target", lambda hwnd: resolved_targets.append(hwnd))
    monkeypatch.setattr("voice_flow.local_model_resources.acquire_model_use", lambda kind: lease)
    monkeypatch.setattr(main, "_warm_voice_gemini_transport", lambda *_args: None)
    try:
        assert app._on_dictation_start() is True
        assert resolved_targets == [123]
        assert app.session.target_hwnd == 123
        assert app.session.model_resource_lease is lease
    finally:
        if app._record_watchdog:
            app._record_watchdog.cancel()


def test_failed_device_open_never_shows_recording(monkeypatch):
    events = []
    lease = _Lease(events)
    app = _recording_app(DictationSession(123, "Editor", "smart_clean", "smart_clean", 0.0), events, lease)
    app._capture_target_hwnd = lambda: 123
    app.audio.start = lambda: False
    app.overlay.show_recording = lambda **_kw: events.append("recording")
    app.overlay.show_error = lambda *_args: events.append("error")
    app._stop_audio_flow_pipeline = lambda: None
    monkeypatch.setattr(main.audio_flow_widget, "hide", lambda: None)
    monkeypatch.setattr(main.storage, "get_setting", lambda key, default=None: default)
    assert app._on_dictation_start() is False
    assert "recording" not in events
    assert "error" in events
    assert app.state == DictationState.IDLE
    assert app.session is None


@pytest.mark.parametrize("replace_owner", [False, True])
def test_context_failure_cleans_only_owned_capture(monkeypatch, replace_owner):
    events = []
    lease = _Lease(events)
    app = _recording_app(DictationSession(123, "Editor", "smart_clean", "smart_clean", 0.0), events, lease)
    app._capture_target_hwnd = lambda: 123
    successor = DictationSession(456, "New", "smart_clean", "smart_clean", 1.0)

    def failed_context():
        if replace_owner:
            app.session = successor
        raise RuntimeError("advisory context failed")

    app._capture_session = failed_context
    app.audio.stop = lambda: events.append("stop")
    app.overlay.show_error = lambda *_args: events.append("error")
    app._stop_audio_flow_pipeline = lambda: None
    monkeypatch.setattr(main.audio_flow_widget, "hide", lambda: None)
    monkeypatch.setattr(main.storage, "get_setting", lambda key, default=None: default)
    assert app._on_dictation_start() is False
    if replace_owner:
        assert app.session is successor
        assert "stop" not in events
        assert "discard" not in events
        assert "error" not in events
    else:
        assert app.session is None
        assert app.state == DictationState.IDLE
        assert "stop" in events
        assert "discard" in events
        assert "error" in events


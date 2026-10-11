"""Tests for Desktop Launcher fast launch, single-instance restoration, and floating bar reset."""

from __future__ import annotations

import io
import json
import threading
from unittest.mock import MagicMock, patch
import pytest

from voice_flow.gui import desktop_launcher
from voice_flow.gui import api_server
from voice_flow.main import VoiceFlowApp, DictationState


class _StatefulRecordingOverlay:
    """Minimal overlay double that exposes destructive foreground resets."""

    def __init__(self, refreshed: threading.Event | None = None) -> None:
        self.state = "RECORDING"
        self.rows = {"audio:active": ("processing", 42)}
        self.show_count = 0
        self.refresh_count = 0
        self.restart_count = 0
        self._refreshed = refreshed

    def show(self) -> None:
        self.show_count += 1

    def refresh(self) -> None:
        self.refresh_count += 1
        if self._refreshed is not None:
            self._refreshed.set()

    def restart_and_refresh(self) -> None:
        self.restart_count += 1
        self.state = "READY"
        self.rows.clear()
        if self._refreshed is not None:
            self._refreshed.set()


def test_duplicate_launch_wait_is_bounded() -> None:
    """Ensure duplicate launch wait time is fast and never stalls the user for 60 seconds."""
    assert desktop_launcher._DUPLICATE_LAUNCH_WAIT_SECONDS <= 5.0
    assert desktop_launcher._DUPLICATE_LAUNCH_POLL_INTERVAL <= 0.2


def test_poke_overlay_show_prefers_restore_and_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    requested_endpoints: list[str] = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=1.0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        for ep in ("/api/app/restore-and-refresh", "/api/overlay/reset-and-refresh", "/api/overlay/show"):
            if ep in url:
                requested_endpoints.append(ep)
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    desktop_launcher._poke_overlay_show()

    assert len(requested_endpoints) >= 1
    assert requested_endpoints[0] == "/api/app/restore-and-refresh"


def test_poke_overlay_show_fallback_never_requests_explicit_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    requested_endpoints: list[str] = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=1.0):
        endpoint = req.full_url.split(f"127.0.0.1:{desktop_launcher.PORT}", 1)[1]
        requested_endpoints.append(endpoint)
        if endpoint == "/api/app/restore-and-refresh":
            raise TimeoutError("restore request timed out")
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    desktop_launcher._poke_overlay_show()

    assert requested_endpoints == ["/api/app/restore-and-refresh", "/api/overlay/show"]
    assert "/api/overlay/reset-and-refresh" not in requested_endpoints


def test_restore_and_refresh_resets_state_and_overlay() -> None:
    app = VoiceFlowApp.__new__(VoiceFlowApp)
    import threading
    app._state_lock = threading.RLock()
    app.state = DictationState.RECORDING
    app._pending_command = "test"
    app.audio = MagicMock()
    app.overlay = MagicMock()

    app.reset_state_and_refresh()

    assert app.state == DictationState.IDLE
    assert app._pending_command is None
    app.audio.cancel.assert_called_once()
    app.overlay.restart_and_refresh.assert_called_once()


def test_api_server_get_restore_and_refresh_preserves_runtime_state() -> None:
    mock_ctrl = MagicMock()
    mock_overlay = _StatefulRecordingOverlay()
    mock_ctrl.overlay = mock_overlay

    api_server.register_runtime_controller(mock_ctrl)

    handler = api_server.VoiceFlowApiHandler.__new__(api_server.VoiceFlowApiHandler)
    handler.directory = api_server.GUI_DIR
    handler.path = "/api/app/restore-and-refresh"
    handler.send_json_response = MagicMock()
    handler.do_GET()

    mock_ctrl.reset_state_and_refresh.assert_not_called()
    assert mock_overlay.restart_count == 0
    assert mock_overlay.show_count == 1
    assert mock_overlay.refresh_count == 1
    assert mock_overlay.state == "RECORDING"
    assert mock_overlay.rows == {"audio:active": ("processing", 42)}

    handler.send_json_response.assert_called_once()
    call_args = handler.send_json_response.call_args[0][0]
    assert call_args["success"] is True
    assert "generation" in call_args


@pytest.mark.parametrize(
    ("path", "expected_overlay_action"),
    [
        ("/api/overlay/show", "show"),
        ("/api/overlay/refresh", "refresh"),
        ("/api/overlay/reset-position", "reset_position"),
        ("/api/app/restore-and-refresh", "refresh"),
    ],
)
def test_get_presentation_actions_preserve_active_recording(
    path: str,
    expected_overlay_action: str,
) -> None:
    """Displaying or repainting the overlay must not cancel the microphone."""
    class RecordingController:
        def __init__(self) -> None:
            self.state = DictationState.RECORDING
            self.audio = MagicMock()
            self.overlay = MagicMock()

        def reset_state_and_refresh(self) -> None:
            self.state = DictationState.IDLE
            self.audio.cancel()

    controller = RecordingController()
    api_server.register_runtime_controller(controller)

    handler = api_server.VoiceFlowApiHandler.__new__(api_server.VoiceFlowApiHandler)
    handler.directory = api_server.GUI_DIR
    handler.path = path
    handler.send_json_response = MagicMock()
    handler.do_GET()

    assert controller.state == DictationState.RECORDING
    controller.audio.cancel.assert_not_called()
    getattr(controller.overlay, expected_overlay_action).assert_called_once()


def test_get_explicit_reset_action_still_resets_active_recording() -> None:
    controller = MagicMock()
    controller.overlay = MagicMock()
    api_server.register_runtime_controller(controller)

    handler = api_server.VoiceFlowApiHandler.__new__(api_server.VoiceFlowApiHandler)
    handler.directory = api_server.GUI_DIR
    handler.path = "/api/overlay/reset-and-refresh"
    handler.send_json_response = MagicMock()
    handler.do_GET()

    controller.reset_state_and_refresh.assert_called_once()


def test_post_restore_and_refresh_preserves_active_recording() -> None:
    overlay_refreshed = threading.Event()

    class RecordingController:
        def __init__(self) -> None:
            self.state = DictationState.RECORDING
            self.audio = MagicMock()
            self.overlay = _StatefulRecordingOverlay(overlay_refreshed)

        def reset_state_and_refresh(self) -> None:
            self.state = DictationState.IDLE
            self.audio.cancel()

    controller = RecordingController()
    api_server.register_runtime_controller(controller)

    handler = api_server.VoiceFlowApiHandler.__new__(api_server.VoiceFlowApiHandler)
    handler.directory = api_server.GUI_DIR
    handler.path = "/api/app/restore-and-refresh"
    handler.headers = {"Content-Length": "2"}
    handler.rfile = io.BytesIO(b"{}")
    handler._host_is_allowed = lambda: True
    handler.send_json_response = MagicMock()
    handler.do_POST()

    assert overlay_refreshed.wait(0.5)
    assert controller.state == DictationState.RECORDING
    controller.audio.cancel.assert_not_called()
    assert controller.overlay.restart_count == 0
    assert controller.overlay.show_count == 1
    assert controller.overlay.refresh_count == 1
    assert controller.overlay.state == "RECORDING"
    assert controller.overlay.rows == {"audio:active": ("processing", 42)}


def test_post_explicit_reset_action_still_resets_active_recording(monkeypatch) -> None:
    class ImmediateThread:
        def __init__(self, *, target, daemon):
            self._target = target

        def start(self) -> None:
            self._target()

    monkeypatch.setattr(api_server.threading, "Thread", ImmediateThread)
    controller = MagicMock()
    controller.overlay = MagicMock()
    api_server.register_runtime_controller(controller)

    handler = api_server.VoiceFlowApiHandler.__new__(api_server.VoiceFlowApiHandler)
    handler.directory = api_server.GUI_DIR
    handler.path = "/api/overlay/reset-and-refresh"
    handler.headers = {"Content-Length": "2"}
    handler.rfile = io.BytesIO(b"{}")
    handler._host_is_allowed = lambda: True
    handler.send_json_response = MagicMock()
    handler.do_POST()

    controller.reset_state_and_refresh.assert_called_once()


def test_launch_desktop_gui_fast_path_when_api_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop_launcher, "set_windows_auto_startup", lambda enable: None)
    monkeypatch.setattr(desktop_launcher, "is_api_server_ready", lambda timeout=0.15: True)

    mock_ensure = MagicMock()
    monkeypatch.setattr(desktop_launcher, "ensure_backend_running", mock_ensure)

    mock_poke = MagicMock()
    monkeypatch.setattr(desktop_launcher, "_poke_overlay_show", mock_poke)

    mock_webview = MagicMock()
    mock_window = MagicMock()
    mock_webview.create_window.return_value = mock_window
    monkeypatch.setattr(desktop_launcher, "webview", mock_webview)

    desktop_launcher.launch_desktop_gui()

    # Fast-path: When API server is already ready, ensure_backend_running must NOT be called
    mock_ensure.assert_not_called()
    mock_webview.create_window.assert_called_once()
    mock_webview.start.assert_called_once()


def test_focus_existing_window_handles_minimized_window(monkeypatch: pytest.MonkeyPatch) -> None:
    with patch("voice_flow.gui.desktop_launcher.sys.platform", "win32"):
        with patch("ctypes.windll.user32.FindWindowW", return_value=54321):
            with patch("ctypes.windll.user32.IsWindow", return_value=True):
                with patch("ctypes.windll.user32.IsIconic", return_value=True):
                    with patch("ctypes.windll.user32.ShowWindow") as mock_show:
                        with patch("ctypes.windll.user32.IsWindowVisible", return_value=True):
                            with patch("ctypes.windll.user32.SetForegroundWindow") as mock_set_fg:
                                res = desktop_launcher._focus_existing_window()
                                assert res is True
                                mock_show.assert_called_with(54321, 9)
                                mock_set_fg.assert_called_once_with(54321)

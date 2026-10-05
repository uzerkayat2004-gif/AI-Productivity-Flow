"""Tests for Desktop Launcher fast launch, single-instance restoration, and floating bar reset."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest

from voice_flow.gui import desktop_launcher
from voice_flow.gui import api_server
from voice_flow.main import VoiceFlowApp, DictationState


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


def test_api_server_restore_and_refresh_endpoint() -> None:
    mock_ctrl = MagicMock()
    mock_overlay = MagicMock()
    mock_ctrl.overlay = mock_overlay

    api_server.register_runtime_controller(mock_ctrl)

    handler = api_server.VoiceFlowApiHandler.__new__(api_server.VoiceFlowApiHandler)
    handler.directory = api_server.GUI_DIR
    handler.path = "/api/app/restore-and-refresh"
    handler.send_json_response = MagicMock()
    handler.do_GET()

    mock_ctrl.reset_state_and_refresh.assert_called_once()
    mock_overlay.show.assert_called()
    mock_overlay.reset_position.assert_not_called()  # saved position is preserved

    handler.send_json_response.assert_called_once()
    call_args = handler.send_json_response.call_args[0][0]
    assert call_args["success"] is True
    assert "generation" in call_args


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

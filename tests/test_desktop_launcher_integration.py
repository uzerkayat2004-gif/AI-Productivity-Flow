"""Integration tests for desktop launcher, main process lifecycle, and floating bar coexistence."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from voice_flow.gui import desktop_launcher
from voice_flow.main import VoiceFlowApp, main


@pytest.fixture(autouse=True)
def _never_start_live_backend(monkeypatch: pytest.MonkeyPatch):
    """Desktop launcher tests must never spawn the user's live Voice Flow."""
    monkeypatch.setattr(desktop_launcher, "ensure_backend_running", lambda: None)


def test_desktop_launcher_is_api_server_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop_launcher, "runtime_is_compatible", lambda **kwargs: True)
    assert desktop_launcher.is_api_server_ready() is True

    monkeypatch.setattr(desktop_launcher, "runtime_is_compatible", lambda **kwargs: False)
    assert desktop_launcher.is_api_server_ready() is False


def test_desktop_launcher_gui_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop_launcher, "set_windows_auto_startup", lambda enable: None)
    monkeypatch.setattr(desktop_launcher, "is_api_server_ready", lambda timeout=0.2: True)
    monkeypatch.setattr(desktop_launcher, "_focus_existing_window", lambda: False)

    mock_webview = MagicMock()
    mock_window = MagicMock()
    mock_webview.create_window.return_value = mock_window
    monkeypatch.setattr(desktop_launcher, "webview", mock_webview)

    desktop_launcher.launch_desktop_gui()

    mock_webview.create_window.assert_called_once()
    args, kwargs = mock_webview.create_window.call_args
    assert "AI Productivity Flow" in kwargs["title"]
    assert f"http://127.0.0.1:{desktop_launcher.PORT}/index.html" in kwargs["url"]
    mock_webview.start.assert_called_once()


def test_desktop_launcher_does_not_bind_fallback_api_while_engine_is_cold(monkeypatch: pytest.MonkeyPatch) -> None:
    from voice_flow.storage import storage

    targets: list[object] = []

    class FakeThread:
        def __init__(self, *, target, **_kwargs):
            targets.append(target)

        def start(self) -> None:
            return None

    monkeypatch.setattr(storage, "get_setting", lambda _key, default=None: True)
    monkeypatch.setattr(desktop_launcher, "set_windows_auto_startup", lambda _enable: None)
    monkeypatch.setattr(desktop_launcher, "ensure_backend_running", lambda: None)
    monkeypatch.setattr(desktop_launcher, "is_api_server_ready", lambda timeout=0.2: False)
    monkeypatch.setattr(desktop_launcher, "_is_backend_running", lambda: True)
    monkeypatch.setattr(desktop_launcher.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(desktop_launcher.threading, "Thread", FakeThread)
    fallback = MagicMock()
    monkeypatch.setattr(desktop_launcher, "_fallback_to_browser", fallback)

    desktop_launcher.launch_desktop_gui(fallback_keep_alive=False)

    assert desktop_launcher.start_api_server not in targets
    fallback.assert_called_once()


def test_desktop_launcher_focus_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    with patch("voice_flow.gui.desktop_launcher.sys.platform", "win32"):
        with patch("ctypes.windll.user32.FindWindowW", return_value=12345):
            with patch("ctypes.windll.user32.IsWindow", return_value=True):
                with patch("ctypes.windll.user32.IsIconic", return_value=False):
                    with patch("ctypes.windll.user32.IsWindowVisible", return_value=True):
                        with patch("ctypes.windll.user32.SetForegroundWindow") as mock_set_fg:
                            assert desktop_launcher._focus_existing_window() is True
                            mock_set_fg.assert_called_once_with(12345)


def test_desktop_launcher_focus_existing_restores_minimized(monkeypatch: pytest.MonkeyPatch) -> None:
    with patch("voice_flow.gui.desktop_launcher.sys.platform", "win32"):
        with patch("ctypes.windll.user32.FindWindowW", return_value=12345):
            with patch("ctypes.windll.user32.IsWindow", return_value=True):
                with patch("ctypes.windll.user32.IsIconic", return_value=True):
                    with patch("ctypes.windll.user32.ShowWindow") as mock_show:
                        with patch("ctypes.windll.user32.IsWindowVisible", return_value=True):
                            with patch("ctypes.windll.user32.SetForegroundWindow") as mock_set_fg:
                                assert desktop_launcher._focus_existing_window() is True
                                mock_show.assert_called_with(12345, 9)
                                mock_set_fg.assert_called_once_with(12345)


def test_desktop_launcher_focus_existing_stale_window_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    with patch("voice_flow.gui.desktop_launcher.sys.platform", "win32"):
        with patch("ctypes.windll.user32.FindWindowW", return_value=12345):
            with patch("ctypes.windll.user32.IsWindow", return_value=True):
                with patch("ctypes.windll.user32.IsIconic", return_value=False):
                    # Window is not visible and ShowWindow cannot make it visible (stale / zombie)
                    with patch("ctypes.windll.user32.ShowWindow") as mock_show:
                        with patch("ctypes.windll.user32.IsWindowVisible", return_value=False):
                            assert desktop_launcher._focus_existing_window() is False
                            mock_show.assert_called_with(12345, 9)


def test_desktop_launcher_gui_launch_fallback_on_webview_create_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop_launcher, "set_windows_auto_startup", lambda enable: None)
    monkeypatch.setattr(desktop_launcher, "is_api_server_ready", lambda timeout=0.2: True)

    mock_webview = MagicMock()
    mock_webview.create_window.side_effect = Exception("Edge Chromium initialization failed")
    monkeypatch.setattr(desktop_launcher, "webview", mock_webview)

    mock_fallback = MagicMock()
    monkeypatch.setattr(desktop_launcher, "_fallback_to_browser", mock_fallback)

    desktop_launcher.launch_desktop_gui(fallback_keep_alive=False)

    mock_fallback.assert_called_once()
    args, kwargs = mock_fallback.call_args
    assert f"http://127.0.0.1:{desktop_launcher.PORT}/index.html" in args[0]


def test_desktop_launcher_gui_launch_fallback_on_webview_start_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop_launcher, "set_windows_auto_startup", lambda enable: None)
    monkeypatch.setattr(desktop_launcher, "is_api_server_ready", lambda timeout=0.2: True)

    mock_webview = MagicMock()
    mock_window = MagicMock()
    mock_webview.create_window.return_value = mock_window
    mock_webview.start.side_effect = Exception("Failed to start webview main loop")
    monkeypatch.setattr(desktop_launcher, "webview", mock_webview)

    mock_fallback = MagicMock()
    monkeypatch.setattr(desktop_launcher, "_fallback_to_browser", mock_fallback)

    desktop_launcher.launch_desktop_gui(fallback_keep_alive=False)

    mock_fallback.assert_called_once()


def test_desktop_launcher_fallback_to_browser_helper() -> None:
    with patch("webbrowser.open") as mock_open:
        quit_cb = MagicMock()
        desktop_launcher._fallback_to_browser("http://127.0.0.1:8991/index.html", on_quit_callback=quit_cb, keep_alive=False)
        mock_open.assert_called_once_with("http://127.0.0.1:8991/index.html")
        quit_cb.assert_called_once()


def test_voice_flow_app_launches_desktop_launcher_and_overlay(monkeypatch: pytest.MonkeyPatch) -> None:
    app = VoiceFlowApp.__new__(VoiceFlowApp)
    app.hotkeys = MagicMock()
    app.audio = MagicMock()
    app.overlay = MagicMock()
    app.polisher = MagicMock()
    app.storage = MagicMock()
    app._watch_gui_state_file = MagicMock()

    from voice_flow.gui import api_server
    monkeypatch.setattr(api_server, "start_api_server", lambda *args, **kwargs: None)
    monkeypatch.setattr(api_server, "register_runtime_controller", lambda *args, **kwargs: None)

    mock_popen = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    app.run()

    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    cmd = args[0]
    assert "-m" in cmd
    assert "voice_flow.gui.desktop_launcher" in cmd

    app.overlay.run_loop.assert_called_once()


def test_main_handles_occupied_port(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from voice_flow import runtime_guard
    from voice_flow.runtime_guard import RuntimePortResult

    calls: list[tuple[int, bool]] = []
    monkeypatch.setattr(
        runtime_guard,
        "prepare_runtime_port",
        lambda *, port, require_engine=False: calls.append((port, require_engine)) or RuntimePortResult(status="occupied"),
    )

    mock_app_cls = MagicMock()
    monkeypatch.setattr("voice_flow.main.VoiceFlowApp", mock_app_cls)

    main()
    mock_app_cls.assert_not_called()
    assert calls == [(8991, True)]

    # App should NOT be initialized if port is occupied by foreign process
    mock_app_cls.assert_not_called()


def test_main_starts_app_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    from voice_flow import runtime_guard
    from voice_flow.runtime_guard import RuntimePortResult

    calls: list[tuple[int, bool]] = []
    monkeypatch.setattr(
        runtime_guard,
        "prepare_runtime_port",
        lambda *, port, require_engine=False: calls.append((port, require_engine)) or RuntimePortResult(status="available"),
    )

    mock_app_instance = MagicMock()
    mock_app_cls = MagicMock(return_value=mock_app_instance)
    monkeypatch.setattr("voice_flow.main.VoiceFlowApp", mock_app_cls)

    main()

    mock_app_cls.assert_called_once()
    mock_app_instance.run.assert_called_once()
    assert calls == [(8991, True)]


def test_desktop_launcher_pokes_overlay_on_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop_launcher, "set_windows_auto_startup", lambda enable: None)
    monkeypatch.setattr(desktop_launcher, "is_api_server_ready", lambda timeout=0.2: True)
    monkeypatch.setattr(desktop_launcher, "ensure_backend_running", lambda: None)

    mock_poke = MagicMock()
    monkeypatch.setattr(desktop_launcher, "_poke_overlay_show", mock_poke)

    mock_webview = MagicMock()
    mock_window = MagicMock()
    mock_webview.create_window.return_value = mock_window
    monkeypatch.setattr(desktop_launcher, "webview", mock_webview)

    desktop_launcher.launch_desktop_gui()

    # Verify _poke_overlay_show was called to guarantee floating bar is visible
    import time
    time.sleep(0.05)
    mock_poke.assert_called()


def test_api_server_overlay_show_get_and_post() -> None:
    from voice_flow.gui import api_server
    mock_overlay = MagicMock()
    mock_ctrl = MagicMock()
    mock_ctrl.overlay = mock_overlay

    api_server.register_runtime_controller(mock_ctrl)

    # Test GET /api/overlay/show
    handler = api_server.VoiceFlowApiHandler.__new__(api_server.VoiceFlowApiHandler)
    handler.directory = api_server.GUI_DIR
    handler.path = "/api/overlay/show"
    handler.send_json_response = MagicMock()
    handler.do_GET()

    mock_overlay.show.assert_called()
    mock_overlay.reset_position.assert_called()
    handler.send_json_response.assert_called_once()


def test_terminate_voice_flow_listeners_never_kills_desktop_launcher(monkeypatch: pytest.MonkeyPatch) -> None:
    from voice_flow import runtime_guard
    import psutil

    mock_proc = MagicMock()
    mock_proc.pid = 9999
    mock_proc.cmdline.return_value = ["python.exe", "-m", "voice_flow.gui.desktop_launcher"]
    mock_proc.children.return_value = []

    mock_engine = MagicMock()
    mock_engine.pid = 8888
    mock_engine.cmdline.return_value = ["python.exe", "-m", "voice_flow.main"]
    mock_engine.children.return_value = []

    def fake_process(pid):
        if pid == 9999:
            return mock_proc
        if pid == 8888:
            return mock_engine
        raise psutil.NoSuchProcess(pid)

    monkeypatch.setattr(psutil, "Process", fake_process)
    monkeypatch.setattr(runtime_guard, "_is_voice_flow_process", lambda proc: True)
    monkeypatch.setattr(psutil, "wait_procs", lambda *args, **kwargs: None)

    terminated = runtime_guard.terminate_voice_flow_listeners([9999, 8888])

    # desktop_launcher (9999) must NOT be terminated
    mock_proc.terminate.assert_not_called()
    # engine listener (8888) must be terminated
    mock_engine.terminate.assert_called_once()
    assert 9999 not in terminated
    assert 8888 in terminated


def test_main_launches_desktop_launcher_even_if_gui_started_in_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_FLOW_GUI_STARTED", "1")

    app = VoiceFlowApp.__new__(VoiceFlowApp)
    app.hotkeys = MagicMock()
    app.audio = MagicMock()
    app.overlay = MagicMock()
    app.polisher = MagicMock()
    app.storage = MagicMock()
    app._watch_gui_state_file = MagicMock()

    from voice_flow.gui import api_server
    monkeypatch.setattr(api_server, "start_api_server", lambda *args, **kwargs: None)
    monkeypatch.setattr(api_server, "register_runtime_controller", lambda *args, **kwargs: None)

    # Window is not open
    monkeypatch.setattr("voice_flow.gui.desktop_launcher._focus_existing_window", lambda: False)

    mock_popen = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    app.run()

    # Even with VOICE_FLOW_GUI_STARTED=1, if no window is open, it MUST spawn desktop_launcher
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    cmd = args[0]
    assert "voice_flow.gui.desktop_launcher" in cmd


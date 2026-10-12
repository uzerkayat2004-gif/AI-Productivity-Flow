"""Launcher startup decisions when the API is alive without the dictation engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from voice_flow.gui import desktop_launcher


def _mock_watchdog_spawn(monkeypatch, *, data_dir: Path) -> MagicMock:
    from voice_flow import watchdog
    import psutil

    monkeypatch.setattr(desktop_launcher, "_get_pythonw_executable", lambda: "pythonw.exe")
    monkeypatch.setattr(watchdog, "get_pythonw_env", lambda **_kwargs: {})
    monkeypatch.setattr(watchdog, "get_silent_windows_spawn_kwargs", lambda: {})
    monkeypatch.setattr("voice_flow.paths.data_dir", lambda: data_dir)
    monkeypatch.setattr(psutil, "process_iter", lambda *_args, **_kwargs: [])
    popen = MagicMock()
    monkeypatch.setattr(desktop_launcher.subprocess, "Popen", popen)
    return popen


def test_compatible_api_without_engine_spawns_watchdog(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(desktop_launcher, "is_api_server_ready", lambda **_kwargs: True)
    monkeypatch.setattr(desktop_launcher, "is_engine_ready", lambda **_kwargs: False, raising=False)
    monkeypatch.setattr(desktop_launcher, "_is_pid_alive", lambda _pid: False)
    popen = _mock_watchdog_spawn(monkeypatch, data_dir=tmp_path)

    assert desktop_launcher.ensure_backend_running() is True

    popen.assert_called_once()
    assert "voice_flow.watchdog" in popen.call_args.args[0]


def test_ready_engine_does_not_spawn_watchdog(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(desktop_launcher, "is_api_server_ready", lambda **_kwargs: True)
    monkeypatch.setattr(desktop_launcher, "is_engine_ready", lambda **_kwargs: True, raising=False)
    popen = _mock_watchdog_spawn(monkeypatch, data_dir=tmp_path)

    assert desktop_launcher.ensure_backend_running() is False

    popen.assert_not_called()


def test_cold_watchdog_does_not_spawn_duplicate(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "watchdog.lock").write_text("4321", encoding="utf-8")
    monkeypatch.setattr(desktop_launcher, "is_api_server_ready", lambda **_kwargs: False)
    monkeypatch.setattr(desktop_launcher, "is_engine_ready", lambda **_kwargs: False, raising=False)
    monkeypatch.setattr(desktop_launcher, "_is_pid_alive", lambda pid: pid == 4321)
    popen = _mock_watchdog_spawn(monkeypatch, data_dir=tmp_path)

    assert desktop_launcher.ensure_backend_running() is False

    popen.assert_not_called()


def test_launcher_waits_for_engine_before_opening_gui_on_api_only_listener(monkeypatch) -> None:
    from voice_flow.storage import storage

    monkeypatch.setattr(desktop_launcher, "set_windows_auto_startup", lambda _enable: None)
    monkeypatch.setattr(storage, "get_setting", lambda _key, default=None: True)
    monkeypatch.setattr(desktop_launcher, "is_api_server_ready", lambda **_kwargs: True)
    engine_state = {"ready": False, "probes": 0}

    def engine_ready(**_kwargs):
        engine_state["probes"] += 1
        if engine_state["probes"] >= 4:
            engine_state["ready"] = True
        return engine_state["ready"]

    monkeypatch.setattr(desktop_launcher, "is_engine_ready", engine_ready)
    spawn = MagicMock(return_value=True)
    monkeypatch.setattr(desktop_launcher, "ensure_backend_running", spawn)
    monkeypatch.setattr(desktop_launcher, "_poke_overlay_show", MagicMock())
    monkeypatch.setattr(desktop_launcher.time, "sleep", lambda _seconds: None)
    webview = MagicMock()
    window = MagicMock()

    def create_window(**_kwargs):
        assert engine_state["ready"], "GUI opened before engine readiness"
        return window

    webview.create_window.side_effect = create_window
    monkeypatch.setattr(desktop_launcher, "webview", webview)

    desktop_launcher.launch_desktop_gui()

    spawn.assert_called_once()
    assert engine_state["probes"] == 4
    webview.create_window.assert_called_once()
    webview.start.assert_called_once()


def test_launcher_opens_gui_after_bounded_engine_startup_timeout(monkeypatch) -> None:
    from voice_flow.storage import storage

    monkeypatch.setattr(desktop_launcher, "set_windows_auto_startup", lambda _enable: None)
    monkeypatch.setattr(storage, "get_setting", lambda _key, default=None: True)
    monkeypatch.setattr(desktop_launcher, "is_api_server_ready", lambda **_kwargs: True)
    monkeypatch.setattr(desktop_launcher, "is_engine_ready", lambda **_kwargs: False)
    monkeypatch.setattr(desktop_launcher, "ensure_backend_running", lambda: True)
    monkeypatch.setattr(desktop_launcher, "_poke_overlay_show", MagicMock())
    sleeps: list[float] = []
    monkeypatch.setattr(desktop_launcher.time, "sleep", sleeps.append)
    webview = MagicMock()
    webview.create_window.return_value = MagicMock()
    monkeypatch.setattr(desktop_launcher, "webview", webview)

    desktop_launcher.launch_desktop_gui()

    assert len(sleeps) == 200
    webview.create_window.assert_called_once()

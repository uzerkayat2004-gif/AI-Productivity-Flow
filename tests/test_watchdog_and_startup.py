"""Tests for Voice Flow Watchdog Supervisor and Windows Auto-Startup Installer."""

from __future__ import annotations

import collections
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from voice_flow import watchdog
from voice_flow.watchdog import WatchdogSupervisor, get_pythonw_executable, get_src_dir
from voice_flow import installer


def test_get_src_dir_returns_valid_path() -> None:
    src = get_src_dir()
    assert isinstance(src, Path)
    assert src.exists()
    assert (src / "voice_flow").is_dir()


def test_get_pythonw_executable_returns_string() -> None:
    pyw = get_pythonw_executable()
    assert isinstance(pyw, str)
    assert len(pyw) > 0
    assert "pythonw" in pyw.lower()


def test_watchdog_lock_acquire_and_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(watchdog, "data_dir", lambda: tmp_path)
    supervisor = WatchdogSupervisor()

    # Initial lock should succeed
    assert supervisor.acquire_lock() is True
    lock_file = tmp_path / "watchdog.lock"
    assert lock_file.exists()
    assert lock_file.read_text().strip() == str(os.getpid())

    # Acquiring again with same PID should still be valid
    assert supervisor.acquire_lock() is True

    # Release lock
    supervisor.release_lock()
    assert not lock_file.exists()


def test_watchdog_lock_detects_foreign_alive_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(watchdog, "data_dir", lambda: tmp_path)
    lock_file = tmp_path / "watchdog.lock"
    lock_file.write_text("999999")

    supervisor = WatchdogSupervisor()
    monkeypatch.setattr(supervisor, "_is_pid_alive", lambda pid: True if pid == 999999 else False)
    monkeypatch.setattr(supervisor, "_ensure_gui_open", lambda: None)

    # Should detect foreign running process and refuse lock
    assert supervisor.acquire_lock() is False


def test_watchdog_lock_cleans_stale_dead_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(watchdog, "data_dir", lambda: tmp_path)
    lock_file = tmp_path / "watchdog.lock"
    lock_file.write_text("888888")

    supervisor = WatchdogSupervisor()
    monkeypatch.setattr(supervisor, "_is_pid_alive", lambda pid: False)

    # Should detect dead foreign PID, overwrite lock file, and succeed
    assert supervisor.acquire_lock() is True
    assert lock_file.read_text().strip() == str(os.getpid())


def test_watchdog_crash_throttle_and_backoff() -> None:
    supervisor = WatchdogSupervisor(max_rapid_crashes=3, crash_window_seconds=10.0)

    # First 3 crashes within window should have minimal backoff (0.5s)
    b1 = supervisor.record_crash()
    assert b1 == 0.5
    b2 = supervisor.record_crash()
    assert b2 == 0.5
    b3 = supervisor.record_crash()
    assert b3 == 0.5

    # 4th crash (> max_rapid_crashes 3) should trigger exponential backoff: 2.0 ** (4 - 3) = 2.0s
    b4 = supervisor.record_crash()
    assert b4 == 2.0

    # 5th crash: 2.0 ** (5 - 3) = 4.0s
    b5 = supervisor.record_crash()
    assert b5 == 4.0

    # 6th crash: 2.0 ** (6 - 3) = 8.0s
    b6 = supervisor.record_crash()
    assert b6 == 8.0


def test_watchdog_shutdown_signals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(watchdog, "data_dir", lambda: tmp_path)
    supervisor = WatchdogSupervisor()

    assert supervisor.is_shutdown_requested() is False
    supervisor.request_shutdown()
    assert supervisor.is_shutdown_requested() is True
    supervisor.clear_shutdown_flag()
    assert supervisor.is_shutdown_requested() is False


def test_watchdog_health_check_with_child_process() -> None:
    supervisor = WatchdogSupervisor()

    # Mock running child process
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # None indicates still running
    mock_proc.pid = 1234
    supervisor.child_process = mock_proc

    assert supervisor.check_health() is True

    # Mock terminated child process
    mock_proc.poll.return_value = -1  # Exited abnormally
    assert supervisor.check_health() is False
    assert supervisor.child_process is None


def test_watchdog_health_check_requires_a_ready_dictation_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    supervisor = WatchdogSupervisor()
    supervisor.child_process = None

    monkeypatch.setattr(watchdog, "runtime_is_engine_ready", lambda **_: False, raising=False)
    assert supervisor.check_health() is False

    monkeypatch.setattr(watchdog, "runtime_is_engine_ready", lambda **_: True, raising=False)
    assert supervisor.check_health() is True


def test_watchdog_spawn_voice_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    supervisor = WatchdogSupervisor()
    mock_popen = MagicMock()
    mock_proc = MagicMock()
    mock_proc.pid = 4567
    mock_proc.poll.return_value = None
    mock_popen.return_value = mock_proc

    from voice_flow.runtime_guard import RuntimePortResult
    prepare_calls: list[tuple[int, bool]] = []

    def fake_prepare(*, port=8991, require_engine=False):
        prepare_calls.append((port, require_engine))
        return RuntimePortResult(status="available")

    monkeypatch.setattr(watchdog, "prepare_runtime_port", fake_prepare)
    monkeypatch.setattr(watchdog.subprocess, "Popen", mock_popen)
    assert supervisor.spawn_voice_flow() is True
    assert supervisor.child_process is mock_proc
    assert supervisor.child_pid == 4567

    # Verify Popen called with pythonw and -m voice_flow.main
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    cmd = args[0]
    assert "-m" in cmd
    assert "voice_flow.main" in cmd
    assert "PYTHONPATH" in kwargs["env"]
    assert prepare_calls == [(8991, True)]


def test_watchdog_stop_cleans_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(watchdog, "data_dir", lambda: tmp_path)
    supervisor = WatchdogSupervisor()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    supervisor.child_process = mock_proc

    supervisor.stop()
    assert supervisor.running is False
    mock_proc.terminate.assert_called_once()
    assert supervisor.is_shutdown_requested() is True


def test_installer_paths() -> None:
    root = installer.get_project_root()
    assert root.exists()
    vbs = installer.get_vbs_launcher_path()
    assert vbs.name == "VoiceFlowLauncher.vbs"
    icon = installer.get_icon_path()
    assert icon.name == "icon.ico"
    startup_dir = installer.get_startup_dir()
    assert "Startup" in str(startup_dir)


def test_vbs_launcher_silent_syntax() -> None:
    vbs_path = installer.get_vbs_launcher_path()
    assert vbs_path.exists()
    content = vbs_path.read_text(encoding="utf-8")
    assert "WScript.Shell" in content
    # python.exe (console auto-hidden by "Run ..., 0" and by the launcher
    # itself) is required: pythonw breaks WebView2 window creation, leaving a
    # permanently minimized off-screen ghost window.
    assert "python.exe" in content
    assert '"""" & strPython & """ -m voice_flow.gui.desktop_launcher", 0, False' in content
    assert ", 0, False" in content


def test_bat_launcher_script() -> None:
    bat_path = installer.get_project_root() / "run_voice_flow.bat"
    assert bat_path.exists()
    content = bat_path.read_text(encoding="utf-8")
    assert "VoiceFlowLauncher.vbs" in content
    assert "voice_flow.gui.desktop_launcher" in content


def test_installer_desktop_and_start_menu_dirs() -> None:
    desktop_dirs = installer.get_desktop_dirs()
    assert len(desktop_dirs) >= 1
    # Check that paths point to Desktop locations
    for dt in desktop_dirs:
        assert "Desktop" in str(dt)

    sm_dir = installer.get_start_menu_programs_dir()
    assert "Programs" in str(sm_dir)


def test_installer_registry_autorun_logic(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_key = MagicMock()
    mock_open_key = MagicMock(return_value=mock_key)
    mock_key.__enter__.return_value = mock_key
    mock_set_val = MagicMock()
    mock_query_val = MagicMock(return_value=('wscript.exe "C:\\fake\\VoiceFlowLauncher.vbs"', 1))

    monkeypatch.setattr(installer.winreg, "OpenKey", mock_open_key)
    monkeypatch.setattr(installer.winreg, "SetValueEx", mock_set_val)
    monkeypatch.setattr(installer.winreg, "QueryValueEx", mock_query_val)
    monkeypatch.setattr(installer, "_installed_watchdog_command", lambda: None)
    monkeypatch.setattr(installer, "get_vbs_launcher_path", lambda: Path("C:/fake/VoiceFlowLauncher.vbs"))

    with patch.object(Path, "exists", return_value=True):
        ok = installer.register_registry_autorun()
        assert ok is True
        mock_set_val.assert_called_once()


def test_watchdog_supervisor_aliases() -> None:
    supervisor = WatchdogSupervisor()
    assert supervisor._acquire_lock == supervisor.acquire_lock
    assert supervisor._release_lock == supervisor.release_lock
    assert supervisor._spawn_voice_flow == supervisor.spawn_voice_flow


def test_watchdog_ensure_gui_open(monkeypatch: pytest.MonkeyPatch) -> None:
    supervisor = WatchdogSupervisor()
    mock_popen = MagicMock()
    monkeypatch.setattr(watchdog.subprocess, "Popen", mock_popen)

    # Make the Win32 window probe hermetic: no "Voice Flow"/"AI Productivity
    # Flow" window is found, so the launcher spawn path is taken. Without this
    # the test fails on machines where the real app window is open.
    import ctypes

    class FakeUser32:
        def FindWindowW(self, *args):
            return 0

        def IsWindow(self, hwnd):
            return 0

        def ShowWindow(self, *args):
            return 0

        def SetForegroundWindow(self, *args):
            return 0

    class FakeWindll:
        user32 = FakeUser32()

    monkeypatch.setattr(ctypes, "windll", FakeWindll())

    supervisor._ensure_gui_open()

    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    cmd = args[0]
    assert "-m" in cmd
    assert "voice_flow.gui.desktop_launcher" in cmd
    assert "PYTHONPATH" in kwargs["env"]
    assert kwargs["stdout"] == watchdog.subprocess.DEVNULL
    assert kwargs["stderr"] == watchdog.subprocess.DEVNULL


def test_watchdog_get_src_dir_with_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_root = tmp_path / "custom_project"
    fake_src = fake_root / "src"
    fake_pkg = fake_src / "voice_flow"
    fake_pkg.mkdir(parents=True)

    monkeypatch.setenv("AI_PRODUCTIVITY_FLOW_ROOT", str(fake_root))
    assert get_src_dir() == fake_src


def test_watchdog_spawn_voice_flow_port_reclamation(monkeypatch: pytest.MonkeyPatch) -> None:
    supervisor = WatchdogSupervisor()
    mock_popen = MagicMock()
    mock_proc = MagicMock()
    mock_proc.pid = 9876
    mock_proc.poll.return_value = None
    mock_popen.return_value = mock_proc
    monkeypatch.setattr(watchdog.subprocess, "Popen", mock_popen)

    reclaim_called = []
    from voice_flow.runtime_guard import RuntimePortResult

    def fake_prepare(*, port=8991, require_engine=False):
        reclaim_called.append((port, require_engine))
        return RuntimePortResult(status="reclaimed", terminated_pids=(1111,))

    monkeypatch.setattr(watchdog, "prepare_runtime_port", fake_prepare)

    res = supervisor.spawn_voice_flow()
    assert res is True
    assert reclaim_called == [(8991, True)]


def test_watchdog_fresh_shutdown_flag_stops_supervision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A fresh (<120s) shutdown flag means an active stop/restart: honor it."""
    monkeypatch.setattr(watchdog, "data_dir", lambda: tmp_path)
    supervisor = WatchdogSupervisor()

    assert supervisor.should_stop_for_shutdown() is False

    supervisor.request_shutdown()
    assert supervisor.should_stop_for_shutdown() is True
    # The flag stays in place for an active request (nothing deleted it).
    assert (tmp_path / "watchdog_shutdown.flag").exists()


def test_watchdog_stale_shutdown_flag_is_recovered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A flag older than 120s is debris from a stalled restart: delete it and
    resume supervision so the app self-heals instead of staying down."""
    monkeypatch.setattr(watchdog, "data_dir", lambda: tmp_path)
    supervisor = WatchdogSupervisor()

    flag = tmp_path / "watchdog_shutdown.flag"
    flag.write_text("restart at sometime", encoding="utf-8")
    old = time.time() - (watchdog.WATCHDOG_STALE_FLAG_SECONDS + 600)
    os.utime(flag, (old, old))

    assert supervisor.is_shutdown_requested() is True
    assert supervisor.shutdown_flag_age() > watchdog.WATCHDOG_STALE_FLAG_SECONDS
    # Stale -> not a stop request; the flag is deleted so supervision resumes.
    assert supervisor.should_stop_for_shutdown() is False
    assert not flag.exists()

    # Supervision then treats the engine as unhealthy and restarts it as usual.
    monkeypatch.setattr(supervisor, "check_health", lambda: False)
    spawned = []
    monkeypatch.setattr(supervisor, "spawn_voice_flow", lambda: spawned.append(1))
    assert supervisor.check_health() is False
    supervisor.spawn_voice_flow()
    assert spawned == [1]

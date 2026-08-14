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
from voice_flow.watchdog import WatchdogSupervisor, get_pythonw_executable
from voice_flow import installer


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

    # Should detect foreign running process and refuse lock
    assert supervisor.acquire_lock() is False


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


def test_watchdog_health_check_with_runtime_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    supervisor = WatchdogSupervisor()
    supervisor.child_process = None

    monkeypatch.setattr(watchdog, "runtime_is_compatible", lambda **_: True)
    assert supervisor.check_health() is True

    monkeypatch.setattr(watchdog, "runtime_is_compatible", lambda **_: False)
    assert supervisor.check_health() is False


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
    assert "pythonw" in content
    assert "-m voice_flow.watchdog" in content
    # Window style 0 ensures silent zero console popup
    assert ", 0, False" in content

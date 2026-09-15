"""Regression tests for the crash-proof restart sequence.

Covers the 2026-09-10/11 stalls where execute_restart_sequence died inside
terminate_suite_processes after writing watchdog_shutdown.flag, leaving the
app fully down with the flag blocking watchdog recovery:

- the sequence must always reach relaunch_suite() even when earlier steps raise
- watchdog_shutdown.flag must be removed in a finally block (and by the
  relaunch safety net) so a stalled sequence can never wedge recovery
- prepare_runtime_port failures are non-fatal
- a double restart must not double-spawn the suite (restart lock)
- the terminate sweep must exclude the sequencer's own process tree
- clean_runtime_artifacts only removes watchdog.lock/watchdog_shutdown.flag
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from voice_flow import lifecycle, runtime_guard, watchdog
from voice_flow.lifecycle import (
    clean_runtime_artifacts,
    execute_restart_sequence,
    relaunch_suite,
    restart_suite,
    terminate_suite_processes,
    try_acquire_restart_lock,
)


@pytest.fixture
def fake_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point lifecycle's data_dir at a temp dir and disable sleeping."""
    monkeypatch.setattr(lifecycle, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    return tmp_path


def _read_debug_log(tmp_path: Path) -> str:
    log = tmp_path / "restart_debug.log"
    return log.read_text(encoding="utf-8") if log.exists() else ""


def test_sequence_proceeds_to_relaunch_when_terminate_raises(
    fake_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The terminate step failing must never prevent the relaunch."""
    def boom(*_a, **_k):
        raise RuntimeError("simulated terminate crash")

    monkeypatch.setattr(lifecycle, "terminate_suite_processes", boom)
    relaunch_mock = MagicMock(return_value=True)
    monkeypatch.setattr(lifecycle, "relaunch_suite", relaunch_mock)

    execute_restart_sequence(delay_seconds=0)

    relaunch_mock.assert_called_once()
    # Flag gone (finally), restart lock released.
    assert not (fake_data_dir / "watchdog_shutdown.flag").exists()
    assert not (fake_data_dir / "restart_sequence.lock").exists()
    # Step outcomes are logged.
    log = _read_debug_log(fake_data_dir)
    assert "step=terminate_suite_processes outcome=error" in log
    assert "step=relaunch_suite outcome=ok" in log
    assert "Finished execute_restart_sequence" in log


def test_shutdown_flag_removed_in_finally_even_when_relaunch_raises(
    fake_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even a failing relaunch must leave no shutdown flag / lock behind."""
    monkeypatch.setattr(lifecycle, "clean_runtime_artifacts", lambda: None)
    relaunch_mock = MagicMock(side_effect=RuntimeError("spawn failed"))
    monkeypatch.setattr(lifecycle, "relaunch_suite", relaunch_mock)

    execute_restart_sequence(delay_seconds=0)  # must not raise

    # Initial attempt + one retry.
    assert relaunch_mock.call_count == 2
    assert not (fake_data_dir / "watchdog_shutdown.flag").exists()
    assert not (fake_data_dir / "restart_sequence.lock").exists()


def test_prepare_runtime_port_failure_is_non_fatal(
    fake_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def bad_prepare(*_a, **_k):
        raise RuntimeError("port probe exploded")

    monkeypatch.setattr(runtime_guard, "prepare_runtime_port", bad_prepare)
    relaunch_mock = MagicMock(return_value=True)
    monkeypatch.setattr(lifecycle, "relaunch_suite", relaunch_mock)

    execute_restart_sequence(delay_seconds=0)

    relaunch_mock.assert_called_once()
    log = _read_debug_log(fake_data_dir)
    assert "step=prepare_runtime_port outcome=error" in log
    assert "step=relaunch_suite outcome=ok" in log


def test_double_restart_does_not_double_spawn(
    fake_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second restart while one is in flight must be refused."""
    popen_mock = MagicMock()
    monkeypatch.setattr(lifecycle.subprocess, "Popen", popen_mock)
    monkeypatch.setattr(watchdog, "get_pythonw_executable", lambda: "pythonw.exe")
    monkeypatch.setattr(watchdog, "get_pythonw_env", lambda extra=None: {})
    monkeypatch.setattr(watchdog, "get_silent_windows_spawn_kwargs", lambda: {})

    first = restart_suite(None)
    second = restart_suite(None)

    assert first is True
    assert second is False
    assert popen_mock.call_count == 1

    # Once the running sequence releases the lock, restarts work again.
    from voice_flow.lifecycle import release_restart_lock
    release_restart_lock()
    assert restart_suite(None) is True
    assert popen_mock.call_count == 2


def test_restart_lock_stale_or_dead_owner_allows_takeover(
    fake_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crashed sequencer must never wedge future restarts."""
    popen_mock = MagicMock()
    monkeypatch.setattr(lifecycle.subprocess, "Popen", popen_mock)
    monkeypatch.setattr(watchdog, "get_pythonw_executable", lambda: "pythonw.exe")
    monkeypatch.setattr(watchdog, "get_pythonw_env", lambda extra=None: {})
    monkeypatch.setattr(watchdog, "get_silent_windows_spawn_kwargs", lambda: {})

    # Stale lock (old timestamp, dead pid) must be taken over.
    lock = fake_data_dir / "restart_sequence.lock"
    lock.write_text(f"999999 {time.time() - 3600}", encoding="utf-8")
    assert try_acquire_restart_lock() is True

    # Dead but fresh owner must also be taken over.
    lock.unlink(missing_ok=True)
    lock.write_text(f"999999 {time.time()}", encoding="utf-8")
    assert restart_suite(None) is True
    assert popen_mock.call_count == 1


def test_relaunch_suite_removes_shutdown_flag_as_safety_net(
    fake_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """relaunch_suite must delete a lingering watchdog_shutdown.flag after spawning."""
    from voice_flow import installer

    flag = fake_data_dir / "watchdog_shutdown.flag"
    flag.write_text("restart at 1", encoding="utf-8")

    monkeypatch.setattr(installer, "get_vbs_launcher_path", lambda: fake_data_dir / "missing.vbs")
    monkeypatch.setattr(lifecycle, "_get_python_exe", lambda: "pythonw.exe")
    popen_mock = MagicMock()
    monkeypatch.setattr(lifecycle.subprocess, "Popen", popen_mock)

    assert relaunch_suite() is True
    assert popen_mock.call_count == 1
    assert not flag.exists()


def test_clean_runtime_artifacts_only_removes_watchdog_files(
    fake_data_dir: Path,
) -> None:
    """Cleanup must touch ONLY watchdog.lock/watchdog_shutdown.flag (never e.g.
    credentials dirs like ~/.notebooklm, which live outside the data dir)."""
    lock = fake_data_dir / "watchdog.lock"
    flag = fake_data_dir / "watchdog_shutdown.flag"
    keep_file = fake_data_dir / "recordings.db"
    keep_sub = fake_data_dir / "settings"
    lock.write_text("123", encoding="utf-8")
    flag.write_text("restart at 1", encoding="utf-8")
    keep_file.write_text("data", encoding="utf-8")
    keep_sub.mkdir()
    (keep_sub / "x.json").write_text("{}", encoding="utf-8")

    clean_runtime_artifacts()

    assert not lock.exists()
    assert not flag.exists()
    assert keep_file.exists()
    assert (keep_sub / "x.json").exists()


def _fake_user32() -> SimpleNamespace:
    return SimpleNamespace(
        FindWindowW=lambda *a: 0,
        IsWindow=lambda hwnd: 0,
        PostMessageW=lambda *a: 1,
    )


def test_terminate_suite_processes_excludes_worker_and_ancestors(
    fake_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sweep must never target the sequencer, its ancestors, or non-suite
    processes; the sequencer was historically killed by its own sweep."""
    class FakeProc:
        def __init__(self, pid, name, cmdline, children=None):
            self.pid = pid
            self.info = {"pid": pid, "name": name, "cmdline": cmdline}
            self._children = children or []
            self.terminated = False

        def children(self, recursive=False):
            if not recursive:
                return list(self._children)
            out = list(self._children)
            for child in self._children:
                out.extend(child.children(recursive=True))
            return out

        def terminate(self):
            self.terminated = True

    webview_child = FakeProc(301, "msedgewebview2.exe", ["msedgewebview2.exe"])
    watchdog_proc = FakeProc(300, "pythonw.exe", ["pythonw.exe", "-m", "voice_flow.watchdog"], children=[webview_child])
    worker_proc = FakeProc(401, "pythonw.exe", ["pythonw.exe", "-m", "voice_flow.lifecycle", "--execute-restart"])
    foreign_proc = FakeProc(500, "chrome.exe", ["chrome.exe", "--dark"])

    fake_psutil = SimpleNamespace(
        process_iter=lambda attrs=None: iter([watchdog_proc, worker_proc, foreign_proc]),
        wait_procs=lambda procs, timeout=None: ([], []),
        NoSuchProcess=Exception,
        AccessDenied=Exception,
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    # Never post WM_CLOSE to real windows during tests.
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=_fake_user32()))
    # The sequencer's real ancestor chain (pytest's parents) mapped onto fake
    # suite pids: both must be excluded even though 100 matches a marker.
    monkeypatch.setattr(lifecycle, "_ancestor_pids", lambda max_levels=16: [200, 100])
    monkeypatch.setattr(runtime_guard, "listener_pids", lambda host, port: [])

    terminated = terminate_suite_processes(exclude_pids=[200, 100])

    assert watchdog_proc.terminated is True
    assert webview_child.terminated is True
    # The lifecycle worker itself is never a target.
    assert worker_proc.terminated is False
    # Foreign processes are never targets.
    assert foreign_proc.terminated is False
    assert sorted(terminated) == [300, 301]

    tlog = (fake_data_dir / "terminate_debug.log").read_text(encoding="utf-8")
    assert "ancestors_excluded=[200, 100]" in tlog


def test_terminate_ancestors_skips_non_suite_processes(
    fake_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Post-relaunch ancestor cleanup must only touch suite-looking processes."""
    class FakePsutilProc:
        def __init__(self, pid, name, cmdline):
            self.info = {"pid": pid, "name": name, "cmdline": cmdline}
            self.pid = pid
            self.terminated = False

        def cmdline(self):
            return list(self.info["cmdline"])

        def name(self):
            return self.info["name"]

        def terminate(self):
            self.terminated = True

    suite_ancestor = FakePsutilProc(200, "python.exe", ["python.exe", "-m", "voice_flow.gui.desktop_launcher"])
    foreign_ancestor = FakePsutilProc(900, "explorer.exe", ["C:\\Windows\\explorer.exe"])

    def fake_process(pid):
        return {200: suite_ancestor, 900: foreign_ancestor}[pid]

    fake_psutil = SimpleNamespace(Process=fake_process)
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    lifecycle._terminate_ancestors([200, 900])

    assert suite_ancestor.terminated is True
    assert foreign_ancestor.terminated is False

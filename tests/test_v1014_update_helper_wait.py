"""v1.0.14: the update helper really waits for the app before swapping files."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from voice_flow import app_updater as au


def test_pid_alive_tracks_a_real_process():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert au._pid_alive(proc.pid) is True
    finally:
        proc.kill()
        proc.wait()
    assert au._pid_alive(proc.pid) is False
    assert au._pid_alive(0) is False


def test_wait_for_pid_blocks_until_exit():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.5)"])
    t0 = time.monotonic()
    au._wait_for_pid(proc.pid, timeout=20)
    waited = time.monotonic() - t0
    proc.wait()
    assert waited >= 1.0, waited


def test_wait_never_uses_os_kill_probe():
    src = Path(au.__file__).read_text(encoding="utf-8")
    body = src[src.index("def _wait_for_pid"):src.index("_SUITE_MARKERS")]
    assert "os.kill" not in body


def test_rename_retries_until_the_lock_goes(tmp_path, monkeypatch):
    src_dir = tmp_path / "a"
    src_dir.mkdir()
    dest = tmp_path / "b"
    real = os.rename
    calls = {"n": 0}

    def flaky(a, b):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(5, "Access is denied")
        return real(a, b)

    monkeypatch.setattr(au.os, "rename", flaky)
    au._rename_with_retry(src_dir, dest, timeout=10)
    assert dest.is_dir() and calls["n"] == 3


def test_rename_gives_up_after_the_timeout(tmp_path, monkeypatch):
    def always(a, b):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(au.os, "rename", always)
    try:
        au._rename_with_retry(tmp_path / "x", tmp_path / "y", timeout=0.6)
    except PermissionError:
        return
    raise AssertionError("expected PermissionError")


def test_helper_waits_for_the_whole_app_before_swapping():
    src = Path(au.__file__).read_text(encoding="utf-8")
    body = src[src.index("def run_pending_update"):src.index("def _spawn(")]
    assert "_wait_for_suite_exit()" in body
    assert body.index("_wait_for_suite_exit()") < body.index("apply_staged_package(")

from __future__ import annotations

import subprocess
import sys

from voice_flow.video_flow_engine.process_manager import ProcessManager


def test_cancel_job_terminates_registered_process_tree() -> None:
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    manager = ProcessManager()
    try:
        manager.register("cancel-me", process)
        manager.cancel_job("cancel-me")
        process.wait(timeout=8)
        assert process.poll() is not None
        assert manager.is_cancelled("cancel-me")
    finally:
        if process.poll() is None:
            process.kill()


def test_register_replaces_stale_process_without_leak() -> None:
    import time

    first = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    second = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    manager = ProcessManager()
    try:
        manager.register("dup-job", first)
        manager.register("dup-job", second)
        # The orphaned first handle must have been reaped on replacement.
        assert first.poll() is not None
        assert second.poll() is None
    finally:
        for proc in (first, second):
            if proc.poll() is None:
                proc.kill()
        manager.cancel_job("dup-job")


def test_terminate_never_raises_on_dead_process() -> None:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait(timeout=8)
    manager = ProcessManager()
    manager._terminate(process)

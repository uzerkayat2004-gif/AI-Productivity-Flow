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

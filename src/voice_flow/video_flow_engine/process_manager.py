"""Thread-safe tracking and cancellation of generation subprocess trees."""

from __future__ import annotations

import os
import subprocess
import threading
from typing import Any


class ProcessManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen[Any]] = {}
        self._cancelled: set[str] = set()

    def register(self, job_id: str, process: subprocess.Popen[Any]) -> None:
        with self._lock:
            if job_id in self._cancelled:
                self._terminate(process)
                raise RuntimeError("cancelled: job was cancelled")
            self._processes[job_id] = process

    def unregister(self, job_id: str, process: subprocess.Popen[Any] | None = None) -> None:
        with self._lock:
            current = self._processes.get(job_id)
            if process is None or current is process:
                self._processes.pop(job_id, None)

    def cancel_job(self, job_id: str) -> None:
        with self._lock:
            self._cancelled.add(job_id)
            process = self._processes.pop(job_id, None)
        if process is not None:
            self._terminate(process)

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancelled

    def clear(self, job_id: str) -> None:
        with self._lock:
            self._cancelled.discard(job_id)

    def raise_if_cancelled(self, job_id: str) -> None:
        if self.is_cancelled(job_id):
            raise RuntimeError("cancelled: job was cancelled")

    @staticmethod
    def _terminate(process: subprocess.Popen[Any]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        else:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)

"""Thread-safe tracking and cancellation of generation subprocess trees."""

from __future__ import annotations

import os
import subprocess
import threading
from typing import Any

# The app runs windowless (pythonw); without these flags every Windows
# subprocess spawn flashes a console window. Mirrors main.py's convention.
_WINDOWS_HIDE_FLAGS = 0
_WINDOWS_STARTUPINFO = None
if os.name == "nt":
    _WINDOWS_HIDE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    _WINDOWS_STARTUPINFO = subprocess.STARTUPINFO()
    _WINDOWS_STARTUPINFO.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
    _WINDOWS_STARTUPINFO.wShowWindow = getattr(subprocess, "SW_HIDE", 0)


def hidden_window_kwargs() -> dict[str, Any]:
    """Popen/run kwargs that keep spawned consoles off screen on Windows."""
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = _WINDOWS_HIDE_FLAGS
        kwargs["startupinfo"] = _WINDOWS_STARTUPINFO
    return kwargs


class ProcessManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        # One tracked process per job: concurrent planners/runners for the
        # same job share the slot, so registration explicitly replaces (and
        # terminates, if cancelled) the prior handle instead of orphaning it.
        self._processes: dict[str, subprocess.Popen[Any]] = {}
        self._cancelled: set[str] = set()

    def register(self, job_id: str, process: subprocess.Popen[Any]) -> None:
        with self._lock:
            cancelled = job_id in self._cancelled
            previous = self._processes.get(job_id)
            self._processes[job_id] = process
        if previous is not None and previous is not process:
            # A second stage registered before the first unregistered: the
            # old handle is no longer reachable for cancel/timeout, so reap
            # it now instead of leaking a live child.
            self._terminate(previous)
        if cancelled:
            self._terminate(process)
            raise RuntimeError("cancelled: job was cancelled")

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

    def terminate_job(self, job_id: str) -> None:
        """Kill the job's process tree WITHOUT marking the job cancelled (timeouts)."""
        with self._lock:
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
        try:
            if process.poll() is not None:
                return
        except Exception:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
                **hidden_window_kwargs(),
            )
        else:
            try:
                process.terminate()
            except Exception:
                return
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except Exception:
                return
            try:
                process.wait(timeout=3)
            except Exception:
                return
        except Exception:
            return

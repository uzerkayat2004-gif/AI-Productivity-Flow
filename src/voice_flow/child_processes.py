"""Tie helper subprocesses (llama-server, Video Flow node/Chromium/code2video)
to the lifetime of the app process.

* Every tracked child is killed together with its process tree when the app
  exits normally (``atexit``) or receives SIGTERM/SIGHUP (POSIX).
* On Windows every tracked child is also assigned to one Job Object created
  with ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``. The job handle is owned by this
  process and never closed, so when the app dies for any reason (crash, Task
  Manager "End task", ``TerminateProcess``) Windows kills the whole job,
  including grandchildren such as Chromium started by node.
* On POSIX children are started in their own session (``start_new_session``)
  so the whole tree can be killed with ``killpg``. Surviving a ``kill -9`` of
  the parent needs cooperation from the child side; llama-server gets a small
  ``sh`` guard for that (see ``vf1_engine``).
"""
from __future__ import annotations

import atexit
import logging
import os
import signal
import subprocess
import sys
import threading
from typing import Any

log = logging.getLogger(__name__)

_lock = threading.RLock()
_tracked: dict[int, tuple[subprocess.Popen[Any], str]] = {}
_handlers_lock = threading.Lock()
_atexit_registered = False
_signals_installed = False

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
_job_handle: Any = None
_job_failed = False


def new_tree_popen_kwargs() -> dict[str, Any]:
    """Popen kwargs that put a child in its own killable process group (POSIX)."""
    return {} if os.name == "nt" else {"start_new_session": True}


# --------------------------------------------------------------------------
# Windows Job Object
# --------------------------------------------------------------------------

def _load_kernel32() -> Any:  # pragma: no cover - patched in tests / Windows only
    import ctypes

    return ctypes.WinDLL("kernel32", use_last_error=True)


def _create_kill_on_close_job(kernel32: Any) -> Any:
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(f"CreateJobObjectW failed: {ctypes.get_last_error()}")
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = kernel32.SetInformationJobObject(
        job,
        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )
    if not ok:
        err = ctypes.get_last_error()
        kernel32.CloseHandle(job)
        raise OSError(f"SetInformationJobObject failed: {err}")
    return job


def _get_job(kernel32: Any) -> Any:
    global _job_handle, _job_failed
    with _lock:
        if _job_handle is None and not _job_failed:
            try:
                _job_handle = _create_kill_on_close_job(kernel32)
            except Exception as exc:
                _job_failed = True
                log.warning("Could not create kill-on-close job object: %s", exc)
        return _job_handle


def assign_to_kill_on_close_job(process: subprocess.Popen[Any]) -> bool:
    """Windows: put *process* in the app's kill-on-close job. No-op elsewhere."""
    if sys.platform != "win32":
        return False
    try:
        kernel32 = _load_kernel32()
        job = _get_job(kernel32)
        if not job:
            return False
        handle = getattr(process, "_handle", None)
        opened = None
        if handle is None:
            PROCESS_SET_QUOTA, PROCESS_TERMINATE = 0x0100, 0x0001
            opened = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, int(process.pid))
            handle = opened
        if not handle:
            return False
        try:
            ok = bool(kernel32.AssignProcessToJobObject(job, int(handle)))
        finally:
            if opened:
                kernel32.CloseHandle(opened)
        if not ok:
            log.warning("AssignProcessToJobObject failed for pid %s", process.pid)
        return ok
    except Exception as exc:
        log.warning("Could not assign pid %s to job object: %s", getattr(process, "pid", "?"), exc)
        return False


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

def track(process: subprocess.Popen[Any], name: str = "") -> subprocess.Popen[Any]:
    """Remember *process* so it is killed (with its tree) when the app exits."""
    try:
        pid = int(process.pid)
    except Exception:
        return process  # test doubles without a real pid
    with _lock:
        _tracked[pid] = (process, name)
    assign_to_kill_on_close_job(process)
    install_exit_handlers()
    return process


def untrack(process: subprocess.Popen[Any] | None) -> None:
    if process is None:
        return
    try:
        pid = int(process.pid)
    except Exception:
        return
    with _lock:
        current = _tracked.get(pid)
        if current is not None and current[0] is process:
            _tracked.pop(pid, None)


def tracked() -> list[subprocess.Popen[Any]]:
    with _lock:
        return [proc for proc, _name in _tracked.values()]


def _owns_group(process: subprocess.Popen[Any]) -> bool:
    try:
        pid = int(process.pid)
        return os.getpgid(pid) == pid != os.getpgid(0)
    except Exception:
        return False


def kill_tree(process: subprocess.Popen[Any], timeout: float = 3.0) -> None:
    """Terminate *process* and every process it started; never raises."""
    try:
        if process.poll() is not None:
            return
    except Exception:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=5,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass
        try:
            process.wait(timeout=timeout)
            return
        except Exception:
            pass
        try:
            process.kill()
            process.wait(timeout=timeout)
        except Exception:
            pass
        return

    group = _owns_group(process)
    try:
        if group:
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except Exception:
        pass
    try:
        process.wait(timeout=timeout)
    except Exception:
        pass
    # The leader may be gone while group members (Chromium, sleep) linger.
    try:
        if group:
            os.killpg(process.pid, signal.SIGKILL)
        elif process.poll() is None:
            process.kill()
    except Exception:
        pass
    try:
        process.wait(timeout=timeout)
    except Exception:
        pass


def kill_all(timeout: float = 3.0) -> None:
    """Kill every tracked child tree (app shutdown)."""
    with _lock:
        entries = list(_tracked.values())
        _tracked.clear()
    for process, name in entries:
        try:
            if process.poll() is None:
                log.info("Stopping child process %s (pid %s) at app exit", name or "?", process.pid)
        except Exception:
            pass
        kill_tree(process, timeout=timeout)


_exit_callbacks: list[Any] = []


def register_exit_callback(callback: Any) -> None:
    """Run *callback* (no args) before tracked children are killed at exit."""
    with _lock:
        if callback not in _exit_callbacks:
            _exit_callbacks.append(callback)


def shutdown() -> None:
    """App-exit hook: run exit callbacks, then kill every tracked child tree."""
    with _lock:
        callbacks = list(_exit_callbacks)
    for callback in callbacks:
        try:
            callback()
        except Exception:
            log.debug("child-process exit callback failed", exc_info=True)
    kill_all()


def _make_signal_handler(previous: Any):
    def _handler(signum, frame):
        try:
            shutdown()
        finally:
            if callable(previous):
                previous(signum, frame)
            else:
                # Restore default disposition and re-deliver so the process
                # exits exactly as it would have without this hook.
                signal.signal(signum, signal.SIG_DFL)
                os.kill(os.getpid(), signum)

    _handler._voice_flow_child_cleanup = True  # type: ignore[attr-defined]
    return _handler


def install_exit_handlers() -> None:
    """Register atexit + (POSIX, main thread only) SIGTERM/SIGHUP cleanup."""
    global _atexit_registered, _signals_installed
    with _handlers_lock:
        if not _atexit_registered:
            atexit.register(shutdown)
            _atexit_registered = True
        if _signals_installed or os.name == "nt":
            return
        if threading.current_thread() is not threading.main_thread():
            return
        if "pytest" in sys.modules and not os.environ.get("VOICE_FLOW_TEST_SIGNAL_HOOKS"):
            # Never hijack the test runner's own signal handling.
            _signals_installed = True
            return
        for name in ("SIGTERM", "SIGHUP"):
            sig = getattr(signal, name, None)
            if sig is None:
                continue
            try:
                previous = signal.getsignal(sig)
                if previous == signal.SIG_IGN or getattr(previous, "_voice_flow_child_cleanup", False):
                    continue
                signal.signal(sig, _make_signal_handler(previous if callable(previous) else None))
            except (ValueError, OSError):
                continue
        _signals_installed = True

"""CPU priority for startup and one-time background work.

The dictation engine imports a large stack (numpy, scipy, faster-whisper,
Tk, the API server) when it starts. On a 4-core laptop, right after an
install, that ran at normal priority next to the WebView2 window, the
launcher and Windows Defender scanning every new file, and the whole PC
lagged. The engine now starts at below-normal priority and returns to normal
once it is ready, so the window and the user's other apps stay responsive.
One-time background downloads run at idle priority.

Standard library only: the watchdog imports this before anything heavy.
"""

from __future__ import annotations

import os
import sys
import time

BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
NORMAL_PRIORITY_CLASS = 0x00000020
IDLE_PRIORITY_CLASS = 0x00000040

# Set VOICE_FLOW_STARTUP_PRIORITY=normal to start the engine at normal priority.
_OPT_OUT_ENV = "VOICE_FLOW_STARTUP_PRIORITY"


def _is_windows() -> bool:
    return sys.platform == "win32"


def lowered_startup_enabled() -> bool:
    return os.environ.get(_OPT_OUT_ENV, "").strip().lower() not in ("normal", "0", "off", "false")


def engine_startup_creationflags() -> int:
    """Extra Popen creationflags for spawning the engine (Windows only)."""
    if _is_windows() and lowered_startup_enabled():
        return BELOW_NORMAL_PRIORITY_CLASS
    return 0


def background_creationflags() -> int:
    """Popen creationflags for one-time background helpers: idle priority, no console."""
    if not _is_windows():
        return 0
    return IDLE_PRIORITY_CLASS | 0x08000000  # CREATE_NO_WINDOW


def background_preexec():
    """POSIX preexec_fn that lowers a background helper's priority (None on Windows)."""
    if _is_windows():
        return None

    def _lower() -> None:
        try:
            os.nice(10)
        except Exception:
            pass

    return _lower


def _kernel32():
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetPriorityClass.argtypes = [wintypes.HANDLE]
    kernel32.GetPriorityClass.restype = wintypes.DWORD
    kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.SetPriorityClass.restype = wintypes.BOOL
    return kernel32


def current_priority_class() -> int | None:
    if not _is_windows():
        return None
    try:
        kernel32 = _kernel32()
        return int(kernel32.GetPriorityClass(kernel32.GetCurrentProcess())) or None
    except Exception:
        return None


def restore_normal_priority(kernel32=None) -> bool:
    """Raise this process back to normal priority after startup.

    Only a process that is below normal (as the watchdog starts the engine) is
    changed; a priority the user set by hand (high, realtime) is left alone.
    Returns True when the priority was changed. Never raises.
    """
    if not _is_windows() and kernel32 is None:
        return False
    try:
        kernel32 = kernel32 or _kernel32()
        handle = kernel32.GetCurrentProcess()
        current = int(kernel32.GetPriorityClass(handle))
        if current not in (BELOW_NORMAL_PRIORITY_CLASS, IDLE_PRIORITY_CLASS):
            return False
        return bool(kernel32.SetPriorityClass(handle, NORMAL_PRIORITY_CLASS))
    except Exception:
        return False


def process_age_seconds() -> float | None:
    """Seconds since this process was created, or None when unknown."""
    try:
        import psutil

        return max(0.0, time.time() - psutil.Process(os.getpid()).create_time())
    except Exception:
        return None

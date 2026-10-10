"""Voice Flow Single-Instance Signaling and GUI Window Restoration.

Provides fast, lightweight IPC signaling between Voice Flow processes on Windows:
1. Signals running background engine via local loopback API to reset and refresh the floating bar.
2. Restores and brings the native Desktop App window to front with foreground priority.
3. If the Desktop App window was closed, launches it fresh silently and immediately.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
import urllib.request
import urllib.error

PORT = 8991


def _focus_and_restore_gui_window() -> bool:
    """Find and bring the active Voice Flow GUI window to foreground on Windows."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "AI Productivity Flow") or user32.FindWindowW(None, "Voice Flow")
        if not hwnd or not user32.IsWindow(hwnd):
            return False

        # If minimized, restore it first
        if hasattr(user32, "IsIconic") and user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # 9 = SW_RESTORE

        # If hidden, show it
        if hasattr(user32, "IsWindowVisible") and not user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, 9)

        if hasattr(user32, "IsWindowVisible") and not user32.IsWindowVisible(hwnd):
            return False

        # Reject dead zombie windows: only if NOT iconic and collapsed offscreen
        try:
            import ctypes.wintypes as _wt
            rect = _wt.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                is_iconic = hasattr(user32, "IsIconic") and user32.IsIconic(hwnd)
                if not is_iconic and (rect.left <= -20000 or rect.top <= -20000 or width < 100 or height < 50):
                    return False
        except Exception:
            pass

        # Acquire foreground priority
        try:
            user32.AllowSetForegroundWindow(-1)
        except Exception:
            pass

        try:
            kernel32 = ctypes.windll.kernel32
            fg_hwnd = user32.GetForegroundWindow()
            fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
            cur_tid = kernel32.GetCurrentThreadId()
            target_tid = user32.GetWindowThreadProcessId(hwnd, None)
            if fg_tid and fg_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, fg_tid, True)
                if target_tid and target_tid != cur_tid:
                    user32.AttachThreadInput(cur_tid, target_tid, True)
                user32.BringWindowToTop(hwnd)
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
                if target_tid and target_tid != cur_tid:
                    user32.AttachThreadInput(cur_tid, target_tid, False)
                user32.AttachThreadInput(cur_tid, fg_tid, False)
            else:
                user32.BringWindowToTop(hwnd)
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
        except Exception:
            if hasattr(user32, "SetForegroundWindow"):
                user32.SetForegroundWindow(hwnd)

        return True
    except Exception:
        return False


def _launch_desktop_gui_silently() -> bool:
    """Launch Desktop GUI launcher silently in a separate process."""
    try:
        from voice_flow.watchdog import (
            get_pythonw_executable,
            get_pythonw_env,
            get_silent_windows_spawn_kwargs,
            get_src_dir,
        )
        pyw = get_pythonw_executable()
        src_dir = str(get_src_dir())
        env = get_pythonw_env()
        spawn_kwargs = get_silent_windows_spawn_kwargs()

        subprocess.Popen(
            [pyw, "-m", "voice_flow.gui.desktop_launcher"],
            cwd=src_dir,
            env=env,
            close_fds=True,
            **spawn_kwargs,
        )
        return True
    except Exception:
        return False


def signal_running_instance_to_restore(host: str = "127.0.0.1", port: int = PORT) -> bool:
    """Signal the active Voice Flow instance to refresh floating bar and restore GUI window."""
    signaled = False
    for endpoint in ("/api/app/restore-and-refresh", "/api/overlay/reset-and-refresh", "/api/overlay/show"):
        try:
            req = urllib.request.Request(
                f"http://{host}:{port}{endpoint}",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=1.0) as res:
                if res.status == 200:
                    signaled = True
                    break
        except Exception:
            continue

    # Restore existing window or launch a fresh GUI window
    window_focused = _focus_and_restore_gui_window()
    if not window_focused:
        _launch_desktop_gui_silently()

    return signaled or window_focused

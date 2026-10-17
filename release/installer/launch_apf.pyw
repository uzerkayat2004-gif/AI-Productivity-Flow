"""Desktop shortcut entry for the installed Windows app.

Shows a window before Voice Flow imports, and a second launch focuses the
window that is already starting instead of opening another one.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time

MUTEX_NAME = "Local\\VoiceFlowDesktopLauncherMutex_v1"
WINDOW_TITLE = "AI Productivity Flow"


def _install_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _load_early_splash():
    root = _install_root()
    candidates = [
        os.path.join(root, "runtime", "python", "Lib", "site-packages", "voice_flow", "gui", "early_splash.py"),
        os.path.join(root, "src", "voice_flow", "gui", "early_splash.py"),
        os.path.join(os.path.dirname(root), "src", "voice_flow", "gui", "early_splash.py"),
    ]
    here = os.path.dirname(os.path.abspath(__file__))
    # Source checkouts keep this file under release/installer/.
    candidates.append(os.path.join(os.path.dirname(os.path.dirname(here)), "src", "voice_flow", "gui", "early_splash.py"))
    for path in candidates:
        if os.path.isfile(path):
            spec = importlib.util.spec_from_file_location("apf_early_splash", path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
    return None


def _focus_existing() -> bool:
    if not sys.platform.startswith("win"):
        return False
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return True


def _acquire_mutex():
    if not sys.platform.startswith("win"):
        return 1
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if handle and ctypes.get_last_error() == 183:
        kernel32.CloseHandle(handle)
        return None
    return handle


def _prepare_import_path() -> None:
    root = _install_root()
    for path in (
        os.path.join(root, "runtime", "python", "Lib", "site-packages"),
        os.path.join(root, "src"),
        os.path.join(os.path.dirname(os.path.dirname(root)), "src"),
    ):
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)


def main() -> None:
    splash = _load_early_splash()
    if sys.platform.startswith("win"):
        handle = _acquire_mutex()
        if handle is None:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if _focus_existing():
                    return
                time.sleep(0.1)
            _focus_existing()
            return
        os.environ["VOICE_FLOW_LAUNCHER_MUTEX_HANDLE"] = str(int(handle))
        if splash is not None:
            splash.show_early_splash()
    _prepare_import_path()
    from voice_flow.gui.desktop_launcher import _run_desktop_launcher

    _run_desktop_launcher()


if __name__ == "__main__":
    main()

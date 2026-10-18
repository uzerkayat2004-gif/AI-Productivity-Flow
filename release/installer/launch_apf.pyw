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
APP_WINDOW_TITLES = ("AI Productivity Flow", "Voice Flow")
SPLASH_CLASS_NAME = "APFEarlySplash"
SPLASH_WINDOW_TITLES = ("AI Productivity Flow (starting)", "APFEarlySplash")


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


def _launch_log(message: str) -> None:
    try:
        home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        folder = os.path.join(home, ".voice_flow", "logs")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "launch.log"), "a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")
    except Exception:
        pass


def _window_text(user32, hwnd, getter_name: str) -> str:
    import ctypes
    getter = getattr(user32, getter_name)
    getter.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    getter.restype = ctypes.c_int
    buf = ctypes.create_unicode_buffer(512)
    if not getter(hwnd, buf, len(buf)):
        return ""
    return buf.value or ""


def _is_splash(hwnd, user32, splash) -> bool:
    try:
        title = _window_text(user32, hwnd, "GetWindowTextW")
        class_name = _window_text(user32, hwnd, "GetClassNameW")
    except Exception:
        return False
    if splash is not None:
        try:
            return bool(splash.is_startup_splash(title, class_name))
        except Exception:
            pass
    return class_name == SPLASH_CLASS_NAME or title in SPLASH_WINDOW_TITLES


def _focus_existing(splash=None) -> bool:
    """Focus the real main window. The startup splash is not that window."""
    if not sys.platform.startswith("win"):
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    hwnd = None
    for title in APP_WINDOW_TITLES:
        candidate = user32.FindWindowW(None, title)
        if candidate and not _is_splash(candidate, user32, splash):
            hwnd = candidate
            break
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
                if _focus_existing(splash):
                    return
                time.sleep(0.1)
            _focus_existing(splash)
            return
        os.environ["VOICE_FLOW_LAUNCHER_MUTEX_HANDLE"] = str(int(handle))
        # The handle is only valid in this process; children must not reuse it.
        os.environ["VOICE_FLOW_LAUNCHER_MUTEX_PID"] = str(os.getpid())
        if splash is not None:
            try:
                splash.show_early_splash()
            except Exception as exc:
                _launch_log(f"splash failed: {exc}")
    _prepare_import_path()
    from voice_flow.gui import desktop_launcher

    log_phase = getattr(desktop_launcher, "_log_launch_phase", None)
    if log_phase is not None:
        log_phase("launcher imports finished")
    desktop_launcher._run_desktop_launcher()


if __name__ == "__main__":
    main()

"""Windows launch smoke: the startup splash must stay responsive.

The unfixed splash window procedure calls DefWindowProcW without a pointer-sized
LPARAM. On 64-bit Windows that raises OverflowError inside the callback, the
window stops answering, and the rest of startup never runs. This file is part
of the Windows CI job. The child process clears CI so the splash is actually
created.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPLASH = ROOT / "src" / "voice_flow" / "gui" / "early_splash.py"
WINDOWS = sys.platform.startswith("win")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.skipif(not WINDOWS, reason="64-bit DefWindowProcW only exists on Windows")
def test_def_window_proc_accepts_pointer_sized_lparam():
    import importlib.util

    spec = importlib.util.spec_from_file_location("apf_early_splash_types", SPLASH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.def_window_proc(0, 1, 0, 1 << 42)


@pytest.mark.skipif(not WINDOWS, reason="splash message loop is a Windows window")
def test_splash_stays_responsive_while_the_app_starts():
    port = _free_port()
    child = textwrap.dedent(
        f"""
        import importlib.util
        import os
        import sys
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        os.environ.pop("CI", None)
        path = sys.argv[1]
        spec = importlib.util.spec_from_file_location("apf_early_splash", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        hwnd = module.show_early_splash()
        print(f"SPLASH_HWND={{int(hwnd or 0)}}", flush=True)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b"ok"
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, format, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", {port}), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        threading.Event().wait(90)
        """
    )
    env = os.environ.copy()
    env.pop("CI", None)
    process = subprocess.Popen(
        [sys.executable, "-c", child, str(SPLASH)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        hwnd_line = ""
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and process.poll() is None:
            line = process.stdout.readline() if process.stdout else ""
            if line.startswith("SPLASH_HWND="):
                hwnd_line = line.strip()
                break
        assert hwnd_line.startswith("SPLASH_HWND="), process.stderr.read() if process.stderr else "no splash handle"
        hwnd = int(hwnd_line.split("=", 1)[1])
        assert hwnd, "startup splash was not created"

        import urllib.request

        health = ""
        health_deadline = time.monotonic() + 60
        while time.monotonic() < health_deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                    health = response.read().decode("ascii", "replace")
                    if response.status == 200:
                        break
            except Exception:
                health = ""
            time.sleep(0.2)
        assert health == "ok"

        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowW.restype = wintypes.HWND
        user32.IsHungAppWindow.argtypes = [wintypes.HWND]
        user32.IsHungAppWindow.restype = wintypes.BOOL
        user32.SendMessageTimeoutW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
            wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
        ]
        user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
        found = user32.FindWindowW("APFEarlySplash", None)
        assert int(found or 0), "splash window class was not found"
        user32.GetWindowTextW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(found, title, len(title))
        assert title.value != "AI Productivity Flow"
        assert title.value == "AI Productivity Flow (starting)"
        # A normal window since v1.0.7: not topmost, has a taskbar button.
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        ex_style = int(user32.GetWindowLongPtrW(found, -20))  # GWL_EXSTYLE
        assert not ex_style & 0x00000008  # WS_EX_TOPMOST
        assert not ex_style & 0x00000080  # WS_EX_TOOLWINDOW
        assert ex_style & 0x00040000  # WS_EX_APPWINDOW
        assert int(user32.IsHungAppWindow(hwnd)) == 0
        result = ctypes.c_size_t()
        replied = user32.SendMessageTimeoutW(hwnd, 0, 0, 0, 0x0002, 2000, ctypes.byref(result))
        assert int(replied) != 0
    finally:
        process.kill()
        process.wait(timeout=10)

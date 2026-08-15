"""Voice Flow Desktop App Launcher.
Launches local REST API server, system-wide floating overlay bar, and native Desktop UI window.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import winreg
import webview
import pystray
from PIL import Image

# Hide console window on Windows immediately so the GUI runs silently
if sys.platform == "win32":
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            if "--show-console" not in sys.argv:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # 0 = SW_HIDE
    except Exception:
        pass

if sys.stdout is None:
    class DummyWriter:
        encoding = "utf-8"
        errors = "replace"
        def write(self, x): pass
        def flush(self): pass
        def isatty(self): return False
    sys.stdout = DummyWriter()
    sys.stderr = DummyWriter()

from voice_flow.gui.api_server import start_api_server, PORT
from voice_flow.runtime_guard import runtime_is_compatible


def set_windows_auto_startup(enable: bool = True) -> None:
    """Configure single-point Windows Registry auto-launch at login via silent VBS launcher."""
    try:
        from voice_flow.installer import register_registry_autorun, unregister_registry_autorun, unregister_startup_folder
        if enable:
            register_registry_autorun()
            unregister_startup_folder()  # Clean any legacy startup folder shortcut to prevent double-launching
        else:
            unregister_registry_autorun()
            unregister_startup_folder()
    except Exception as e:
        pass


def is_api_server_ready(timeout: float = 0.2) -> bool:
    return runtime_is_compatible(port=PORT, timeout=timeout)


def launch_desktop_gui(on_quit_callback=None) -> None:
    """Launch API server, system auto-startup configuration, and native desktop window."""
    # Ensure Windows startup registry entry exists
    set_windows_auto_startup(True)

    # Start local REST API server if not already active
    if not is_api_server_ready():
        server_thread = threading.Thread(target=start_api_server, daemon=True)
        server_thread.start()

    # Poll up to 3 seconds until API server responds cleanly
    for _ in range(30):
        if is_api_server_ready():
            break
        time.sleep(0.1)

    if not is_api_server_ready(timeout=0.5):
        raise RuntimeError(
            "Voice Flow could not start its current backend. Port 8991 is still owned by an incompatible process."
        )

    url = f"http://127.0.0.1:{PORT}/index.html"
    print(f"[GUI] Opening Voice Flow Desktop App window at {url}...")

    # Icon path
    ico_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets", "icon.ico"))

    # Create native desktop window matching desktop application layout
    create_kwargs = {
        "title": "Voice Flow - AI Speech Desktop App",
        "url": url,
        "width": 1160,
        "height": 760,
        "resizable": True,
        "min_size": (900, 600),
        "background_color": "#0b0c16",
    }

    # Set Windows AppUserModelID so taskbar groups properly and uses our icon
    try:
        import ctypes
        myappid = 'antigravity.voiceflow.desktop.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    window = webview.create_window(**create_kwargs)

    def on_closed():
        if on_quit_callback:
            on_quit_callback()

    window.events.closed += on_closed

    # Start pywebview loop with custom icon
    webview.start(icon=ico_path)

if __name__ == "__main__":
    launch_desktop_gui()

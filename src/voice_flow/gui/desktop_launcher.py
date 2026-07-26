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

if sys.stdout is None:
    class DummyWriter:
        def write(self, x): pass
        def flush(self): pass
    sys.stdout = DummyWriter()
    sys.stderr = DummyWriter()

from voice_flow.gui.api_server import start_api_server, PORT


def set_windows_auto_startup(enable: bool = True) -> None:
    """Configure Windows Registry auto-launch at login via silent VBS launcher."""
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        vbs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "VoiceFlowLauncher.vbs"))
        cmd = f'wscript.exe "{vbs_path}"' if os.path.exists(vbs_path) else f'"{sys.executable}" -m voice_flow.main'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS) as key:
            if enable:
                winreg.SetValueEx(key, "VoiceFlow", 0, winreg.REG_SZ, cmd)
                print("[SYSTEM] Enabled Windows silent auto-startup at login.")
            else:
                try:
                    winreg.DeleteValue(key, "VoiceFlow")
                    print("[SYSTEM] Disabled Windows auto-startup at login.")
                except FileNotFoundError:
                    pass
    except Exception as e:
        print(f"[SYSTEM WARNING] Could not modify Windows startup registry: {e}")


def launch_desktop_gui(on_quit_callback=None) -> None:
    """Launch API server, system auto-startup configuration, and native desktop window."""
    # Ensure Windows startup registry entry exists
    set_windows_auto_startup(True)

    # Start local REST API server
    server_thread = threading.Thread(target=start_api_server, daemon=True)
    server_thread.start()
    time.sleep(0.4)

    url = f"http://127.0.0.1:{PORT}/index.html"
    print(f"[GUI] Opening Voice Flow Desktop App window at {url}...")

    # Icon path
    ico_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets", "icon.ico"))

    import ctypes
    try:
        user32 = ctypes.windll.user32
        screen_width = user32.GetSystemMetrics(0)
        screen_height = user32.GetSystemMetrics(1)
    except Exception:
        screen_width, screen_height = 1920, 1080

    win_width = 480
    win_height = max(600, screen_height - 60)
    win_x = max(0, screen_width - win_width - 15)
    win_y = 25

    # Create native desktop window positioned on right side of screen
    create_kwargs = {
        "title": "voiceFlow",
        "url": url,
        "width": win_width,
        "height": win_height,
        "x": win_x,
        "y": win_y,
        "resizable": True,
        "min_size": (380, 500),
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
        os._exit(0)

    window.events.closed += on_closed

    # Start pywebview loop with custom icon
    webview.start(icon=ico_path)

if __name__ == "__main__":
    launch_desktop_gui()

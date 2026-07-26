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

from voice_flow.gui.api_server import start_api_server, PORT


def set_windows_auto_startup(enable: bool = True) -> None:
    """Configure Windows Registry auto-launch at login via silent VBS launcher."""
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        vbs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "VoiceFlowLauncher.vbs"))
        cmd = f'wscript.exe "{vbs_path}"' if os.path.exists(vbs_path) else f'"{sys.executable}" -m voice_flow.gui.desktop_launcher'
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


def launch_desktop_gui() -> None:
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

    window = webview.create_window(**create_kwargs)
    webview.start()


if __name__ == "__main__":
    launch_desktop_gui()

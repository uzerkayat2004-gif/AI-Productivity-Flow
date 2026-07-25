"""Voice Flow Desktop App Launcher.
Launches local REST API server and native Desktop UI window.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webview

from voice_flow.gui.api_server import start_api_server, PORT


def launch_desktop_gui() -> None:
    """Launch API server and native desktop window."""
    # Start local REST API server
    server_thread = threading.Thread(target=start_api_server, daemon=True)
    server_thread.start()
    time.sleep(0.4)

    url = f"http://127.0.0.1:{PORT}/index.html"
    print(f"[GUI] Opening Voice Flow Desktop App window at {url}...")

    # Create native desktop window matching desktop application layout
    window = webview.create_window(
        title="Voice Flow - AI Speech Desktop App",
        url=url,
        width=1120,
        height=740,
        resizable=True,
        min_size=(900, 600),
        background_color="#FCFCFD",
    )

    webview.start()


if __name__ == "__main__":
    launch_desktop_gui()

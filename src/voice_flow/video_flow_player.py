"""Launch a small resizable, always-on-top Video Flow player window."""

from __future__ import annotations

import sys
import urllib.parse


class PlayerApi:
    def __init__(self) -> None:
        self.window = None

    def toggle_fullscreen(self) -> bool:
        if not self.window:
            return False
        self.window.toggle_fullscreen()
        return True

    def close(self) -> bool:
        if not self.window:
            return False
        self.window.destroy()
        return True


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        return
    import webview

    video_id = sys.argv[1].strip()
    api = PlayerApi()
    url = "http://127.0.0.1:8991/video-player.html?id=" + urllib.parse.quote(video_id)
    api.window = webview.create_window(
        "Video Flow",
        url=url,
        width=720,
        height=480,
        min_size=(420, 280),
        resizable=True,
        on_top=True,
        js_api=api,
    )
    webview.start(debug=False, private_mode=False)


if __name__ == "__main__":
    main()

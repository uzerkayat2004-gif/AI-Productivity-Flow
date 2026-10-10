"""Launch a small resizable, always-on-top Video Flow player window."""

from __future__ import annotations

import re
import sys
import urllib.parse

_SAFE_VIDEO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_RESERVED_WINDOWS = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def _sanitize_video_id(raw: str) -> str | None:
    video_id = (raw or "").strip()
    if not video_id or not _SAFE_VIDEO_ID.fullmatch(video_id):
        return None
    if video_id.split(".")[0].lower() in _RESERVED_WINDOWS:
        return None
    return video_id


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

    import os
    import webbrowser
    from pathlib import Path

    video_id = _sanitize_video_id(sys.argv[1]) if len(sys.argv) >= 2 else None
    if not video_id:
        return
    url = "http://127.0.0.1:8991/video-player.html?id=" + urllib.parse.quote(video_id)

    # Try launching standalone lightweight webview player
    try:
        import webview
        api = PlayerApi()
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
        return
    except Exception as e:
        print(f"[Video Flow Player] Pywebview failed ({e}), trying fallback player...")

    # Fallback 1: Open player web page in browser
    try:
        webbrowser.open(url)
        return
    except Exception:
        pass

    # Fallback 2: Direct OS video file launch
    try:
        from voice_flow.paths import data_dir
        root = data_dir().resolve()
        for cand in [
            root / "v3_projects" / video_id / "video.mp4",
            root / "notebooklm" / "videos" / f"{video_id}.mp4",
        ]:
            resolved = cand.resolve()
            if resolved != root and root not in resolved.parents:
                continue
            if resolved.is_file():
                if os.name == "nt":
                    os.startfile(str(resolved))
                return
    except Exception:
        pass


if __name__ == "__main__":
    main()

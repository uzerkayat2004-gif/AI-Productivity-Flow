"""Where Video Flow can run.

Video Flow's render pipeline (ffmpeg, node, the Narova renderer) ships only in
the Windows build for now, so macOS presents the feature as "coming soon"
instead of letting a click reach Windows-only code. Checked at call time so
tests can monkeypatch ``sys.platform``.
"""

from __future__ import annotations

import sys

VIDEO_FLOW_MAC_NOTE = "Video Flow is coming to Mac soon, available on Windows now"


def video_flow_supported() -> bool:
    """False on macOS, where the Video Flow render toolchain is not bundled yet."""
    return sys.platform != "darwin"


def video_flow_unsupported_payload() -> dict:
    """JSON body for a Video Flow request refused on macOS."""
    return {
        "success": False,
        "unsupported": True,
        "platform": "macos",
        "error_code": "video_flow_unsupported_on_macos",
        "error": VIDEO_FLOW_MAC_NOTE,
    }

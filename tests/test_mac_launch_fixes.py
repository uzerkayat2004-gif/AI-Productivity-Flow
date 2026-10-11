"""Regression checks for the macOS launch fixes found by the rc3 walkthrough."""
from __future__ import annotations

import re
from pathlib import Path

GUI = Path(__file__).resolve().parents[1] / "src" / "voice_flow" / "gui"


def _read(name: str) -> str:
    return (GUI / name).read_text(encoding="utf-8")


def test_video_flow_selected_style_is_declared_before_use():
    source = _read("video-flow.js")
    declaration = re.search(r'^let vfSelectedStyle\s*=\s*"auto";', source, re.MULTILINE)
    assert declaration, "vfSelectedStyle must be declared at top level (Create threw ReferenceError)"
    first_use = source.index("vfSelectedStyle || ")
    assert declaration.start() < first_use


def test_microphone_and_home_wording_is_platform_aware():
    source = _read("app.js")
    assert source.count('"Windows default microphone"') == 1, "only vfDefaultMicLabel may hard-code the Windows label"
    assert 'vfIsMacPlatform() ? "System default microphone" : "Windows default microphone"' in source
    assert "${vfIsMacPlatform() ? \"Hold <strong>Cmd + Option</strong>" in source
    # The helper must not depend on /api/platform/info having answered.
    helper = source[source.index("function vfIsMacPlatform()"):source.index("function vfDefaultMicLabel()")]
    assert "Macintosh" in helper and "window.vfPlatformInfo" in helper
    assert 'id="mic-dialog-subtitle"' in _read("index.html")


def test_time_wait_port_without_live_listener_is_available(monkeypatch):
    """macOS relaunch: bind probe fails (TIME_WAIT) but nothing is listening."""
    import errno
    import socket as real_socket
    from voice_flow import runtime_guard

    class FakeSocket:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def bind(self, address):
            raise OSError(errno.EADDRINUSE, "Address already in use")
        def settimeout(self, value):
            pass
        def connect_ex(self, address):
            return errno.ECONNREFUSED

    monkeypatch.setattr(runtime_guard.socket, "socket", FakeSocket)
    result = runtime_guard._unprivileged_port_result("127.0.0.1", 8991, settle_seconds=0.0)
    assert result.status == "available"


def test_live_foreign_listener_is_still_occupied():
    import socket
    from voice_flow import runtime_guard

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        port = server.getsockname()[1]
        result = runtime_guard._unprivileged_port_result("127.0.0.1", port, settle_seconds=0.3)
        assert result.status == "occupied"
    finally:
        server.close()

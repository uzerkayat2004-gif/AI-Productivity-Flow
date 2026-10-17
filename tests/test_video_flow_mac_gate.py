"""Video Flow is Windows-only for now: on macOS every entry point says so.

The Mac build bundles no ffmpeg/node/Narova, so with ``sys.platform`` set to
``darwin`` the render endpoints refuse, the bar's Video button and the native
composer stop before Windows-only code, and the remaining ``ctypes.windll``
call sites return quietly instead of raising.
"""

from __future__ import annotations

import ctypes
import inspect
import json
import re
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

# Import under the real platform: monkeypatching sys.platform to "darwin"
# before third-party imports (scipy reads sysconfig) breaks them on Linux CI.
from voice_flow import main as vf_main
from voice_flow import video_flow_platform as vfp
from voice_flow import video_flow_providers
from voice_flow.gui import api_server
from voice_flow.hotkeys import InputTriggerListener
from voice_flow.video_flow_contracts import JobV3
from voice_flow.video_flow_engine.notebooklm import login_flow
from voice_flow.video_flow_widget import VideoFlowScreenWidget

ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "src" / "voice_flow" / "gui"
MAC_NOTE = "Video Flow is coming to Mac soon, available on Windows now"


class _ExplodingWinDLL:
    """Any touch of ctypes.windll fails the test."""

    def __getattr__(self, name: str):
        raise AssertionError(f"ctypes.windll.{name} reached on macOS")


@pytest.fixture
def on_mac(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(ctypes, "windll", _ExplodingWinDLL(), raising=False)
    yield


def _post(url: str, body: dict):
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        return urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as exc:
        return exc


def test_platform_helper_matches_sys_platform(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert vfp.video_flow_supported() is False
    payload = vfp.video_flow_unsupported_payload()
    assert payload["success"] is False and payload["unsupported"] is True
    assert payload["error"] == MAC_NOTE
    monkeypatch.setattr(sys, "platform", "win32")
    assert vfp.video_flow_supported() is True


def test_render_endpoints_return_unsupported_on_mac(monkeypatch, on_mac) -> None:
    def _never():
        raise AssertionError("Video Flow service reached on macOS")

    monkeypatch.setattr(api_server, "get_video_flow_service", _never)
    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert "/api/video-flow/generate" in api_server.VIDEO_FLOW_RENDER_POST_PATHS
        for path in sorted(api_server.VIDEO_FLOW_RENDER_POST_PATHS):
            response = _post(base + path, {"source_text": "Explain this.", "id": "vf-test"})
            assert response.status == 501, path
            data = json.loads(response.read().decode("utf-8"))
            assert data["unsupported"] is True, path
            assert data["error"] == MAC_NOTE, path
    finally:
        server.shutdown()
        server.server_close()


def test_render_endpoint_still_queues_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    queued: dict = {}

    class _Service:
        def queue(self, **kwargs):
            queued.update(kwargs)
            return JobV3("vf-win", meta={"output_path": "unused"})

    monkeypatch.setattr(api_server, "get_video_flow_service", lambda: _Service())
    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = _post(f"http://127.0.0.1:{server.server_port}/api/video-flow/generate",
                         {"source_text": "Explain this.", "title": "Demo"})
        assert response.status == 202
        assert queued.get("source_text") == "Explain this."
    finally:
        server.shutdown()
        server.server_close()


def test_no_video_hotkey_is_registered() -> None:
    """Video Flow has no global hotkey; the listener takes no video callback."""
    params = inspect.signature(InputTriggerListener.__init__).parameters
    assert not [name for name in params if "video" in name.lower()]
    main_src = (ROOT / "src" / "voice_flow" / "main.py").read_text(encoding="utf-8")
    call = re.search(r"self\.hotkeys = InputTriggerListener\((.*?)\n        \)", main_src, re.S)
    assert call and "video" not in call.group(1).lower()


def test_bar_video_button_shows_note_on_mac(monkeypatch, on_mac) -> None:
    shown: list[str] = []
    opened: list[object] = []
    monkeypatch.setattr(vf_main.video_flow_widget, "show_composer", lambda *a, **k: opened.append(a))
    fake = SimpleNamespace(overlay=SimpleNamespace(show_error=shown.append))
    vf_main.VoiceFlowApp._process_video_flow_pipeline(fake, "summary", "some selected text")
    assert shown == [MAC_NOTE]
    assert opened == []

    with pytest.raises(RuntimeError, match="coming to Mac soon"):
        vf_main.VoiceFlowApp._queue_video_from_screen(fake, {"source_text": "x"})


def test_composer_launcher_is_inert_on_mac(monkeypatch, on_mac) -> None:
    widget = VideoFlowScreenWidget()
    calls: list[object] = []
    monkeypatch.setattr(widget, "_run_on_ui", lambda fn: calls.append(fn))
    widget.show_composer("text", "summary")
    widget.launch("text", "summary")
    assert calls == []


def test_windll_call_sites_do_not_raise_on_mac(on_mac) -> None:
    assert video_flow_providers._file_description(Path("Antigravity.exe")) == ""
    assert login_flow._visible_top_level_windows() == []
    assert login_flow._bring_hwnd_forward(1234) is False
    api_server._focus_app_window()

    fake = SimpleNamespace(win=SimpleNamespace(winfo_screenwidth=lambda: 1440, winfo_screenheight=lambda: 900))
    assert VideoFlowScreenWidget._composer_work_area(fake, 400, 300, 10, 10) == (0, 0, 1440, 900)


def test_ui_carries_the_mac_gate_note() -> None:
    app_js = (GUI / "app.js").read_text(encoding="utf-8")
    vf_js = (GUI / "video-flow.js").read_text(encoding="utf-8")
    assert f'const VF_MAC_GATE_NOTE = "{MAC_NOTE}";' in app_js
    assert "function vfApplyMacVideoFlowGate()" in app_js
    # nav entry, automatic guide, manual guide and feature toggle all gate
    assert 'pageId === "videoflow" && typeof vfVideoFlowGatedOnMac' in app_js
    assert 'if (feature === "video" && typeof vfVideoFlowGatedOnMac' in app_js
    start_guide = app_js[app_js.index("function startVideoFlowGuide("):][:400]  # v1.0.3: takes an optional resume step
    assert "vfVideoFlowGatedOnMac()" in start_guide
    generate = vf_js[vf_js.index("async function generateVideoFlow() {"):][:300]
    assert "vfVideoFlowGatedOnMac()" in generate and MAC_NOTE in generate
    assert "works anywhere across your Mac" not in app_js


def test_vf_guide_timelines_no_longer_claim_mac_support() -> None:
    raw = (GUI / "assets" / "onboarding" / "vf_guide_timelines.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert "works anywhere across your Mac" not in raw
    # v1.0.3: there is no Video Flow guide on Mac at all, so no Mac cut exists.
    assert "step4_mac" not in data
    assert not (GUI / "assets" / "onboarding" / "vf_guide_step4_mac_mixed.mp3").exists()
    assert data["step4"][0]["text"] == "Finally, Video Flow works anywhere in Windows."

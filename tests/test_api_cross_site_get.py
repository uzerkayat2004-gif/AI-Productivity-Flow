"""A web page must not be able to trigger local /api/ GET actions cross-site."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from voice_flow.gui import api_server
from voice_flow.storage import StorageEngine


@pytest.fixture
def base_url(monkeypatch, tmp_path):
    test_storage = StorageEngine(str(tmp_path / "cross_site.db"))
    monkeypatch.setattr(api_server, "storage", test_storage)
    monkeypatch.setattr("voice_flow.storage.storage", test_storage)
    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.1)
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _get(url: str, **headers: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={"Connection": "close", **headers})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_cross_site_api_get_is_refused_before_it_runs(base_url, monkeypatch):
    calls = []
    from voice_flow import audio_summary

    monkeypatch.setattr(audio_summary.audio_summary_service, "summarize", lambda **kw: calls.append(kw) or "x")
    status, body = _get(base_url + "/api/audio-summary/test?text=hello&model=openai/gpt-4o", **{"Sec-Fetch-Site": "cross-site"})
    assert status == 403
    assert body["success"] is False
    assert calls == []


@pytest.mark.parametrize("site", ["same-origin", "same-site", "none", None])
def test_own_pages_and_non_browser_clients_still_work(base_url, site):
    headers = {"Sec-Fetch-Site": site} if site else {}
    status, body = _get(base_url + "/api/version", **headers)
    assert status == 200
    assert body["success"] is True


def test_oauth_callbacks_are_not_blocked(base_url):
    handler = api_server.VoiceFlowApiHandler.__new__(api_server.VoiceFlowApiHandler)
    handler.headers = {"Sec-Fetch-Site": "cross-site"}
    assert handler._is_cross_site_api_get("/callback") is False
    assert handler._is_cross_site_api_get("/auth/google/callback") is False
    assert handler._is_cross_site_api_get("/api/video-flow/providers/oauth/callback") is False
    assert handler._is_cross_site_api_get("/api/settings/get") is True


def test_v3_audio_is_not_shared_with_every_origin():
    source = (api_server.Path(api_server.GUI_DIR) / "api_server.py").read_text(encoding="utf-8")
    start = source.index('elif path == "/api/video-flow/v3/audio":')
    end = source.index("elif path in (", start)
    assert "Access-Control-Allow-Origin" not in source[start:end]

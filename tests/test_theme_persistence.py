from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from voice_flow.gui import api_server
from voice_flow.storage import StorageEngine


def _request(url: str, *, method: str = "GET", body: dict | None = None):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    return urllib.request.urlopen(request, timeout=10)


def _start_server(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        api_server, "storage",
        StorageEngine(str(tmp_path / "voice-flow.db")),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_port}", server


def test_theme_preference_round_trips_through_backend(monkeypatch, tmp_path: Path) -> None:
    base, server = _start_server(monkeypatch, tmp_path)
    try:
        default_theme = json.loads(_request(base + "/api/settings/theme").read())
        assert default_theme == {"success": True, "theme": "light"}

        saved = json.loads(_request(
            base + "/api/settings/theme", method="POST", body={"theme": "dark"},
        ).read())
        assert saved == {"success": True, "theme": "dark"}

        reloaded = json.loads(_request(base + "/api/settings/theme").read())
        assert reloaded == {"success": True, "theme": "dark"}

        saved = json.loads(_request(
            base + "/api/settings/theme", method="POST", body={"theme": "light"},
        ).read())
        assert saved == {"success": True, "theme": "light"}
        reloaded = json.loads(_request(base + "/api/settings/theme").read())
        assert reloaded == {"success": True, "theme": "light"}
    finally:
        server.shutdown()


def test_theme_preference_rejects_invalid_values(monkeypatch, tmp_path: Path) -> None:
    base, server = _start_server(monkeypatch, tmp_path)
    try:
        raised = False
        try:
            _request(base + "/api/settings/theme", method="POST", body={"theme": "blue"})
        except urllib.error.HTTPError as exc:
            raised = exc.code == 400
        assert raised, "invalid theme value must be rejected with HTTP 400"
    finally:
        server.shutdown()


def test_stt_model_update_accepts_model_id_field(monkeypatch, tmp_path: Path) -> None:
    """The dashboard sends {model_id: ...}; the endpoint must accept it."""
    base, server = _start_server(monkeypatch, tmp_path)
    try:
        saved = json.loads(_request(
            base + "/api/voice-flow-stt/update",
            method="POST",
            body={"model_id": "gemini/gemini-2.5-flash"},
        ).read())
        assert saved == {"success": True, "active_model": "gemini/gemini-2.5-flash"}

        catalog = json.loads(_request(base + "/api/voice-flow-stt/get").read())
        assert catalog["active_model"] == "gemini/gemini-2.5-flash"
    finally:
        server.shutdown()

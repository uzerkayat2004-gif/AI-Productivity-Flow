"""Regression coverage for the persisted AI-polishing switch."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from voice_flow.gui import api_server
from voice_flow.storage import StorageEngine


@contextmanager
def polish_api(store: StorageEngine, monkeypatch):
    monkeypatch.setattr(api_server, "storage", store)
    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def post(url: str, path: str, body: dict) -> tuple[int, dict]:
    request = Request(
        url + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Connection": "close"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        with error:
            return error.code, json.load(error)


def get(url: str, path: str) -> tuple[int, dict]:
    try:
        with urlopen(url + path, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        with error:
            return error.code, json.load(error)


def test_polish_endpoint_requires_a_json_boolean_and_persists_off(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "polish.db"
    store = StorageEngine(str(db_path))
    with polish_api(store, monkeypatch) as url:
        status, rejected = post(url, "/api/voice-flow-polish/update", {"enabled": "false"})
        assert status == 400
        assert rejected["success"] is False

        status, saved = post(url, "/api/voice-flow-polish/update", {"enabled": False})
        assert status == 200
        assert saved["polishing_enabled"] is False
        _, loaded = get(url, "/api/voice-flow-polish/get")
        assert loaded["polishing_enabled"] is False

    # A new storage instance models a restart, not just a warm in-memory read.
    assert StorageEngine(str(db_path)).get_setting("polishing_enabled", True) is False


def test_generic_polish_setting_rejects_non_boolean_and_reports_save_failure(tmp_path: Path, monkeypatch):
    store = StorageEngine(str(tmp_path / "polish.db"))
    with polish_api(store, monkeypatch) as url:
        status, rejected = post(url, "/api/settings/update", {"key": "polishing_enabled", "value": "false"})
        assert status == 400
        assert rejected["success"] is False

    monkeypatch.setattr(store, "save_setting", lambda *_args, **_kwargs: False)
    with polish_api(store, monkeypatch) as url:
        status, failed = post(url, "/api/settings/update", {"key": "polishing_enabled", "value": False})
        assert status == 500
        assert failed["success"] is False

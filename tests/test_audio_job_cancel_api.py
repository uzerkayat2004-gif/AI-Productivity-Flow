from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from voice_flow.gui import api_server
from voice_flow.storage import StorageEngine


@pytest.fixture
def audio_api(tmp_path, monkeypatch):
    store = StorageEngine(str(tmp_path / "audio-cancel.db"))
    monkeypatch.setattr(api_server, "storage", store)
    api_server.register_runtime_controller(None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    yield store, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()
    api_server.register_runtime_controller(None)


def _post(base_url: str, path: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        base_url + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Connection": "close"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _seed(store: StorageEngine, item_id: str, status: str) -> None:
    store.add_audio_summary_history(
        text=f"Source for {item_id}",
        depth="balanced",
        title=item_id,
        item_id=item_id,
        status=status,
        progress=25 if status == "in_progress" else 100,
    )


def test_cancel_routes_only_active_job_and_preserves_final_rows(audio_api):
    store, base_url = audio_api
    _seed(store, "active-a", "in_progress")
    _seed(store, "active-b", "in_progress")
    _seed(store, "ready", "ready")
    cancelled: list[str] = []

    def cancel(item_id: str) -> bool:
        cancelled.append(item_id)
        store.update_audio_summary_history(item_id, status="cancelled", progress=0, error="Cancelled by user")
        return True

    api_server.register_runtime_controller(SimpleNamespace(cancel_audio_summary_job=cancel))

    code, payload = _post(base_url, "/api/audio-flow/cancel", {"id": "active-a"})
    assert code == 200
    assert payload["success"] is True
    assert cancelled == ["active-a"]
    assert store.get_audio_summary_history_by_id("active-a")["status"] == "cancelled"
    assert store.get_audio_summary_history_by_id("active-b")["status"] == "in_progress"

    code, payload = _post(base_url, "/api/audio-flow/cancel", {"id": "ready"})
    assert code == 409
    assert payload["code"] == "not_active"
    assert store.get_audio_summary_history_by_id("ready")["status"] == "ready"
    assert cancelled == ["active-a"]

    code, payload = _post(base_url, "/api/audio-flow/history/cancel", {"id": "missing"})
    assert code == 404
    assert payload["code"] == "not_found"


def test_persisted_active_row_without_runtime_is_reported_uncancelled(audio_api):
    store, base_url = audio_api
    _seed(store, "stale", "in_progress")
    code, payload = _post(base_url, "/api/audio-flow/cancel", {"id": "stale"})
    assert code == 503
    assert payload["code"] == "unable_to_cancel"
    assert store.get_audio_summary_history_by_id("stale")["status"] == "in_progress"


def test_rejected_runtime_cancel_does_not_overwrite_or_delete_history(audio_api):
    store, base_url = audio_api
    _seed(store, "active", "in_progress")
    api_server.register_runtime_controller(SimpleNamespace(cancel_audio_summary_job=lambda _id: False))

    code, payload = _post(base_url, "/api/audio-flow/cancel", {"id": "active"})
    assert code == 409
    assert payload["code"] == "unable_to_cancel"
    assert store.get_audio_summary_history_by_id("active")["status"] == "in_progress"

    code, payload = _post(base_url, "/api/audio-flow/history/delete", {"id": "active"})
    assert code == 409
    assert payload["success"] is False
    assert store.get_audio_summary_history_by_id("active") is not None

    def finish_during_cancel(_item_id: str) -> bool:
        store.update_audio_summary_history("active", status="ready", progress=100)
        return False

    api_server.register_runtime_controller(SimpleNamespace(cancel_audio_summary_job=finish_during_cancel))
    code, payload = _post(base_url, "/api/audio-flow/cancel", {"id": "active"})
    assert code == 409
    assert payload["code"] == "not_active"
    assert store.get_audio_summary_history_by_id("active")["status"] == "ready"


def test_delete_cancels_requested_active_job_before_removing_history(audio_api):
    store, base_url = audio_api
    _seed(store, "to-delete", "in_progress")
    _seed(store, "keep-active", "in_progress")
    cancelled: list[str] = []

    def cancel(item_id: str) -> bool:
        cancelled.append(item_id)
        store.update_audio_summary_history(item_id, status="cancelled", progress=0)
        return True

    api_server.register_runtime_controller(SimpleNamespace(cancel_audio_summary_job=cancel))
    code, payload = _post(base_url, "/api/audio-flow/history/delete", {"id": "to-delete"})
    assert code == 200
    assert payload["success"] is True
    assert cancelled == ["to-delete"]
    assert store.get_audio_summary_history_by_id("to-delete") is None
    assert store.get_audio_summary_history_by_id("keep-active")["status"] == "in_progress"

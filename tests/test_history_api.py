from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from voice_flow.gui import api_server
from voice_flow.storage import StorageEngine


def _request(url: str, *, method: str = "GET", body: dict | None = None, headers: dict[str, str] | None = None):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        method=method,
        headers=headers or ({"Content-Type": "application/json"} if body is not None else {}),
    )
    try:
        return urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as exc:
        return exc


def test_history_insights_pin_delete_api(monkeypatch, tmp_path: Path) -> None:
    db_path = str(tmp_path / "voice_flow.db")
    test_storage = StorageEngine(db_path)
    monkeypatch.setattr(api_server, "storage", test_storage)

    # Seed records
    rec1 = test_storage.add_dictation("first test raw", "First test polished.", "VS Code", 2.5)
    rec2 = test_storage.add_dictation("second test raw", "Second test polished.", "Chrome", 3.0)

    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. GET /api/history
        resp = _request(f"{base_url}/api/history")
        assert resp.status == 200
        history_data = json.loads(resp.read().decode("utf-8"))
        assert len(history_data) == 2
        assert history_data[0]["id"] == rec2.id
        assert history_data[1]["id"] == rec1.id

        # 2. GET /api/insights
        resp_ins = _request(f"{base_url}/api/insights")
        assert resp_ins.status == 200
        ins_data = json.loads(resp_ins.read().decode("utf-8"))
        assert ins_data["total_words"] == 6
        assert ins_data["dictation_count"] == 2
        assert "streak" in ins_data
        assert "avg_wpm" in ins_data

        # 3. POST /api/history/pin (Pin rec1)
        resp_pin = _request(f"{base_url}/api/history/pin", method="POST", body={"id": rec1.id})
        assert resp_pin.status == 200
        pin_data = json.loads(resp_pin.read().decode("utf-8"))
        assert pin_data["success"] is True
        assert pin_data["is_pinned"] is True

        # Re-fetch history to verify pinned item sorts first
        resp_hist2 = _request(f"{base_url}/api/history")
        hist_data2 = json.loads(resp_hist2.read().decode("utf-8"))
        assert hist_data2[0]["id"] == rec1.id
        assert hist_data2[0]["is_pinned"] == 1

        # 4. POST /api/history/pin (Unpin rec1)
        resp_unpin = _request(f"{base_url}/api/history/pin", method="POST", body={"id": rec1.id})
        assert resp_unpin.status == 200
        unpin_data = json.loads(resp_unpin.read().decode("utf-8"))
        assert unpin_data["success"] is True
        assert unpin_data["is_pinned"] is False

        # 5. POST /api/history/delete (Delete rec2)
        resp_del = _request(f"{base_url}/api/history/delete", method="POST", body={"id": rec2.id})
        assert resp_del.status == 200
        del_data = json.loads(resp_del.read().decode("utf-8"))
        assert del_data["success"] is True

        # Verify history length is now 1
        resp_hist3 = _request(f"{base_url}/api/history")
        hist_data3 = json.loads(resp_hist3.read().decode("utf-8"))
        assert len(hist_data3) == 1
        assert hist_data3[0]["id"] == rec1.id

    finally:
        server.shutdown()
        server.server_close()

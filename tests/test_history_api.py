from __future__ import annotations

import json
import subprocess
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
    metadata = {
        "schema_version": 1,
        "polish": {"outcome": "provider_failure", "display": "AI unavailable — basic cleanup applied", "duration_ms": 42},
        "style": {"requested_id": "work_formal", "effective_id": "email_formal", "label": "Email", "applied": False},
        "command": {"label": "Email", "status": "not_applied"},
        "dictionary": {"count": 1, "replacements": [{"from": "voice flow", "to": "VoiceFlow"}]},
    }
    rec1 = test_storage.add_dictation("first test raw", "First test polished.", "VS Code", 2.5, processing_metadata=metadata)
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
        # History must expose a structured, readable outcome; it cannot turn a
        # fallback into an indistinguishable generic success in the UI.
        assert history_data[1]["processing_metadata"] == metadata

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


def test_history_renderer_exposes_fallback_and_structured_outcome() -> None:
    """The real card renderer must never hide an AI fallback as generic success."""
    app_js = Path(__file__).parents[1] / "src" / "voice_flow" / "gui" / "app.js"
    script = f"""
const fs = require('fs');
const source = fs.readFileSync({json.dumps(str(app_js))}, 'utf8');
const start = source.indexOf('function historyProcessingMetadata');
const end = source.indexOf('function renderHistoryFeed', start);
if (start < 0 || end < 0) throw new Error('History rendering seam missing');
global.escapeHtml = value => String(value ?? '').replace(/[&<>\"']/g, char => ({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}}[char]));
global.escapeJs = value => String(value ?? '');
eval(source.slice(start, end));
const html = renderDictationCardHtml({{
  id: 7, timestamp: '2026-09-22 10:30:00', app_name: 'Editor', word_count: 3, wpm_speed: 80,
  status: 'success', error_message: 'Polish fallback: provider_failure',
  raw_text: 'voice flow make this formal hello team', polished_text: 'Hello team.',
  processing_metadata: {{
    schema_version: 1,
    polish: {{outcome: 'provider_failure', display: 'AI unavailable — basic cleanup applied', duration_ms: 42}},
    style: {{requested_id: 'work_formal', effective_id: 'email_formal', label: 'Email', applied: false}},
    command: {{label: 'Email', status: 'not_applied'}},
    dictionary: {{count: 1, replacements: [{{from: 'voice flow', to: 'VoiceFlow'}}]}},
  }},
}});
for (const expected of ['AI unavailable', 'Not applied', 'Email', 'voice flow', 'VoiceFlow', 'Heard', 'Delivered']) {{
  if (!html.includes(expected)) throw new Error(`missing rendered outcome: ${{expected}}`);
}}
"""
    completed = subprocess.run(["node", "-e", script], check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_history_dedup_keeps_nonempty_outcome_metadata(tmp_path: Path) -> None:
    """A legacy duplicate with `{}` must not erase a newer visible outcome."""
    store = StorageEngine(str(tmp_path / "history.db"))
    metadata = {"schema_version": 1, "polish": {"outcome": "local", "display": "Cleaned locally", "duration_ms": 1}}
    first = store.add_dictation("voice flow", "VoiceFlow", processing_metadata=metadata)
    with store._get_conn() as conn:
        conn.execute(
            """
            INSERT INTO history (timestamp, raw_text, polished_text, app_name, duration_sec, word_count, wpm_speed, style_mode, status, error_message, audio_path, insertion_status, updated_at, retry_count, processing_metadata)
            SELECT timestamp, raw_text, polished_text, app_name, duration_sec, word_count, wpm_speed, style_mode, status, error_message, audio_path, insertion_status, updated_at, retry_count, '{}'
            FROM history WHERE id = ?
            """,
            (first.id,),
        )
    history = store.get_recent_history()
    assert len(history) == 1
    assert history[0]["processing_metadata"] == metadata

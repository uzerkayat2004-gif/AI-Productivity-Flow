import json
import os
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from voice_flow.gui.api_server import VoiceFlowApiHandler
from voice_flow.storage import StorageEngine
from voice_flow.video_flow_contracts import JobV3
from voice_flow.video_flow_service import VideoFlowStore, VideoFlowService


def test_video_flow_rolling_cap_at_50(tmp_path: Path):
    """Verify Video Flow rolling FIFO cap keeps exactly 50 videos and prunes oldest when a new video is made."""
    db_file = tmp_path / "video_flow.db"
    store = VideoFlowStore(db_file)
    service = VideoFlowService(store=store)

    # Seed 60 video jobs
    for i in range(60):
        job = JobV3(
            job_id=f"vf_test_{i:03d}",
            state="complete",
            progress=100.0,
            message="Ready",
            meta={"title": f"Video #{i}"},
        )
        store.create(job)

    # Total jobs should be capped at 50
    all_store_jobs = store.list()
    assert len(all_store_jobs) == 50
    # Newest job (first in DESC) should be #59
    assert all_store_jobs[0].job_id == "vf_test_059"
    # Oldest remaining job (last in DESC) should be #10 (0..9 were auto-deleted)
    assert all_store_jobs[-1].job_id == "vf_test_010"

    all_service_jobs = service.list()
    assert len(all_service_jobs) == 50

    # Specific limit works cleanly
    limited_jobs = service.list(limit=15)
    assert len(limited_jobs) == 15

    # Direct delete test
    del_ok = service.delete("vf_test_059")
    assert del_ok is True
    assert len(service.list()) == 49


def test_audio_flow_rolling_cap_at_50(tmp_path: Path):
    """Verify Audio Flow rolling FIFO cap keeps exactly 50 audios and prunes oldest when a new audio is made."""
    db_file = tmp_path / "voice_flow.db"
    storage = StorageEngine(str(db_file))

    # Seed 65 audio summaries
    for i in range(65):
        storage.add_audio_summary_history(
            text=f"Full text content for summary #{i}",
            depth="balanced",
            title=f"Audio Summary #{i}",
            item_id=f"af_summary_{i:03d}",
            duration_sec=30.0 + i,
            status="ready",
        )

    # Total summaries should be capped at 50
    all_summaries = storage.get_audio_summary_history()
    assert len(all_summaries) == 50
    # Newest summary is #64
    assert all_summaries[0]["id"] == "af_summary_064"
    # Oldest remaining summary is #15 (0..14 were auto-deleted)
    assert all_summaries[-1]["id"] == "af_summary_015"

    # Specific limit works cleanly
    limited_summaries = storage.get_audio_summary_history(limit=15)
    assert len(limited_summaries) == 15


def test_audio_summary_cancellation_preservation(tmp_path: Path):
    """Verify Audio Flow records and preserves cancelled status in both audio_summary_history and unified history."""
    db_file = tmp_path / "voice_flow.db"
    storage = StorageEngine(str(db_file))

    # Add an audio summary in_progress
    storage.add_audio_summary_history(
        text="Sample text for cancellation",
        depth="concise",
        title="Cancelling Audio",
        item_id="ash_cancel_1",
        status="in_progress",
        progress=25,
    )

    # Update to cancelled
    storage.update_audio_summary_history(
        "ash_cancel_1",
        status="cancelled",
        progress=0,
        error="Cancelled by user",
    )
    storage.record_audio_summary_to_history(
        audio_id="ash_cancel_1",
        title="Cancelling Audio",
        text_snippet="Sample text for cancellation",
        status="cancelled",
        error_message="Cancelled by user",
    )

    retrieved = storage.get_audio_summary_history_by_id("ash_cancel_1")
    assert retrieved is not None
    assert retrieved["status"] == "cancelled"
    assert retrieved["error"] == "Cancelled by user"

    recent = storage.get_recent_history()
    matched = next((r for r in recent if r.get("insertion_status") == "ash_cancel_1"), None)
    assert matched is not None
    assert matched["status"] == "cancelled"


def test_api_history_endpoints_and_cancel_route(tmp_path: Path):
    """Verify HTTP API endpoints for /api/video-flow/history, /api/audio-flow/history, /api/audio-flow/cancel, and /api/history."""
    db_file = tmp_path / "voice_flow.db"
    storage = StorageEngine(str(db_file))

    # 1. Seed 45 audio summaries in storage
    for i in range(45):
        storage.add_audio_summary_history(
            text=f"Full text #{i}",
            depth="concise",
            title=f"Audio #{i}",
            item_id=f"ash_{i:03d}",
            duration_sec=20.0,
            status="ready",
        )

    # 2. Add one in_progress summary to cancel
    storage.add_audio_summary_history(
        text="In progress audio to cancel",
        depth="balanced",
        title="To Cancel",
        item_id="ash_to_cancel",
        status="in_progress",
        progress=50,
    )

    # 3. Create mock VideoFlowService with 40 jobs
    mock_jobs = [
        JobV3(
            job_id=f"vf_job_{i:03d}",
            state="complete",
            progress=100.0,
            meta={"title": f"Video Project #{i}"},
        )
        for i in range(40)
    ]
    mock_vf_service = MagicMock()
    mock_vf_service.list.side_effect = lambda limit=None: mock_jobs[:limit] if limit else mock_jobs
    mock_runtime_controller = MagicMock()
    def cancel_audio_summary_job(summary_id):
        if summary_id != "ash_to_cancel":
            return False
        storage.update_audio_summary_history(summary_id, status="cancelled", progress=0, error="Cancelled by user")
        return True
    mock_runtime_controller.cancel_audio_summary_job.side_effect = cancel_audio_summary_job

    with patch("voice_flow.storage.storage", storage), \
         patch("voice_flow.gui.api_server.storage", storage), \
         patch("voice_flow.gui.api_server.runtime_controller", mock_runtime_controller), \
         patch("voice_flow.gui.api_server.get_video_flow_service", return_value=mock_vf_service):

        server = HTTPServer(("127.0.0.1", 0), VoiceFlowApiHandler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        time.sleep(0.1)
        port = server.server_address[1]
        base_url = f"http://127.0.0.1:{port}"

        try:
            # 1. Test /api/video-flow/history
            req_vf = urllib.request.Request(f"{base_url}/api/video-flow/history")
            with urllib.request.urlopen(req_vf, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                assert "videos" in data
                assert len(data["videos"]) == 40

            # 2. Test /api/audio-flow/history
            req_af = urllib.request.Request(f"{base_url}/api/audio-flow/history")
            with urllib.request.urlopen(req_af, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                assert data["success"] is True
                assert len(data["summaries"]) == 46  # 45 ready + 1 in_progress

            # 3. Test POST /api/audio-flow/cancel
            cancel_body = json.dumps({"id": "ash_to_cancel"}).encode("utf-8")
            cancel_req = urllib.request.Request(
                f"{base_url}/api/audio-flow/cancel",
                data=cancel_body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(cancel_req, timeout=5) as resp:
                cancel_resp = json.loads(resp.read().decode("utf-8"))
                assert cancel_resp["success"] is True
                assert cancel_resp["status"] == "cancelled"

            # Check that /api/audio-flow/history shows it with cancelled status
            with urllib.request.urlopen(req_af, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                cancelled_item = next(s for s in data["summaries"] if s["id"] == "ash_to_cancel")
                assert cancelled_item["status"] == "cancelled"

            # 4. Test /api/history returns unified records
            req_hist = urllib.request.Request(f"{base_url}/api/history")
            with urllib.request.urlopen(req_hist, timeout=5) as resp:
                hist_records = json.loads(resp.read().decode("utf-8"))
                assert isinstance(hist_records, list)
                assert len(hist_records) >= 46

        finally:
            server.shutdown()


def test_unpruned_database_auto_prunes_on_startup_and_list(tmp_path: Path):
    """Verify that an existing unpruned database (e.g. 111 videos and 80 audios) is automatically pruned to 50 on startup and access."""
    import sqlite3
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE video_flow_jobs (
            job_id TEXT PRIMARY KEY NOT NULL,
            state TEXT NOT NULL,
            progress REAL NOT NULL DEFAULT 0,
            message TEXT NOT NULL DEFAULT '',
            meta_json TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE audio_summary_history (
            id TEXT PRIMARY KEY NOT NULL,
            title TEXT,
            text_snippet TEXT NOT NULL,
            full_text TEXT,
            depth TEXT NOT NULL,
            audio_path TEXT NOT NULL,
            duration_sec REAL DEFAULT 0,
            status TEXT DEFAULT 'ready',
            error TEXT,
            progress INTEGER DEFAULT 100,
            created_at TEXT NOT NULL,
            downloaded INTEGER DEFAULT 0
        )
        """
    )
    for i in range(111):
        conn.execute(
            "INSERT INTO video_flow_jobs VALUES (?, 'complete', 100.0, 'Ready', '{}', ?, ?)",
            (f"raw_vf_{i:03d}", float(1000 + i), float(1000 + i)),
        )
    for i in range(80):
        conn.execute(
            "INSERT INTO audio_summary_history VALUES (?, ?, ?, ?, 'balanced', '', 30.0, 'ready', NULL, 100, ?, 0)",
            (f"raw_af_{i:03d}", f"Audio #{i}", f"Snippet #{i}", f"Text #{i}", f"2026-09-01T{i:02d}:00:00"),
        )
    conn.commit()
    conn.close()

    store = VideoFlowStore(db_file)
    videos = store.list()
    assert len(videos) == 50
    assert videos[0].job_id == "raw_vf_110"
    assert videos[-1].job_id == "raw_vf_061"

    storage = StorageEngine(str(db_file))
    audios = storage.get_audio_summary_history()
    assert len(audios) == 50

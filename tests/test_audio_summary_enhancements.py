"""Unit and integration tests for Audio Flow summary enhancements.

Tests:
1. Floating bar progressive bar for Audio Flow summary generation.
2. Short document / text notice and Switch-to-Read action in AudioFlowFloatingWidget.
3. Audio summary history persistence, retrieval, and API endpoints.
4. Player icon and resolution mechanics.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from http.server import HTTPServer
from pathlib import Path
import pytest


def test_overlay_audio_summary_progress_bar():
    """Verify FloatingOverlayBar displays and manages the Audio Flow progressive bar."""
    from voice_flow.overlay import FloatingOverlayBar

    overlay = FloatingOverlayBar.__new__(FloatingOverlayBar)
    overlay.root = None
    overlay.win = None
    overlay.canvas = None
    overlay.width = 48
    overlay.height = 10
    overlay.idle_width = 48
    overlay.idle_height = 10
    overlay.ready_actions_width = 248
    overlay.video_action_width = 66
    overlay.settings_action_width = 26
    overlay.hover_height = 28
    overlay.video_progress_width = 280
    overlay.video_progress_height = 26
    overlay.video_progress_hover_height = 26
    overlay.audio_summary_progress_width = 280
    overlay.audio_summary_progress_height = 26
    overlay.audio_summary_progress_hover_height = 26
    overlay.recording_width = 192
    overlay.working_width = 250
    overlay.working_height = 28
    overlay.audio_playback_width = 272
    overlay.expanded_width = 144
    overlay.done_label = "Done"
    overlay.state = "READY"
    overlay.video_status = ""
    overlay.video_progress = 0
    overlay.video_stage = ""
    overlay.video_job_id = ""
    overlay.selected_text = ""
    overlay._selection_generation = 0
    overlay.error_message = ""
    overlay._anim_phase = 0.0
    overlay._hover_zone = None
    overlay._is_mouse_over = False
    overlay._selection_expanded = False
    overlay._last_drawn_width = 280
    overlay.GRIP_W = 14
    overlay.audio_summary_status = ""
    overlay.audio_summary_progress = 0
    overlay.audio_summary_stage = ""
    overlay._audio_summary_animation_generation = 0
    overlay.on_audio_summary_cancel = None

    # Helper to mock _run_on_ui
    def _run_on_ui(fn):
        fn()
    overlay._run_on_ui = _run_on_ui
    overlay._draw = lambda: None

    # 1. Initially idle
    assert overlay._target_size() == (48, 10)

    # 2. Progress activated
    overlay.show_audio_summary_progress(45, "Synthesizing audio")
    assert overlay.audio_summary_status == "processing"
    assert overlay.audio_summary_progress == 45
    assert overlay.audio_summary_stage == "Synthesizing audio"
    assert overlay._target_size() == (280, 26)

    # 3. Expanded / hovered size stacks actions below progress strip
    overlay._is_mouse_over = True
    assert overlay._target_size() == (280, 28 + 26 + 4)
    overlay._is_mouse_over = False

    # 4. Cancel button zone detection
    # Bar width = 280, grip_left = 280 - 14 = 266, cancel button is 248..266
    zone = overlay._get_zone(255, 13)
    assert zone == "audio_summary_cancel"

    # 5. Cancel callback triggers and clears status
    cancelled = []
    overlay.on_audio_summary_cancel = lambda: cancelled.append(True)
    class FakeEvent:
        x = 255
        y = 13
    overlay.show_ready = lambda: setattr(overlay, "state", "READY")
    overlay._on_press(FakeEvent())
    assert cancelled == [True]
    assert overlay.audio_summary_status == ""
    assert overlay.audio_summary_progress == 0


def test_audio_flow_widget_short_text_notice():
    """Verify AudioFlowFloatingWidget displays notice for short text and switches to Read or proceeds to depth select."""
    from voice_flow.audio_flow_widget import (
        AudioFlowFloatingWidget,
        _is_short_text,
    )

    # 1. Short text detection
    assert _is_short_text("") is False
    assert _is_short_text("   ") is False
    short_sample = "Artificial intelligence is transforming how we read and summarize content."
    assert _is_short_text(short_sample) is True
    # ~2 pages of text (over 400 words and 2000 chars)
    long_sample = ("Voice Flow provides seamless transcription and audio features for Windows desktop. " * 40)
    assert len(long_sample) > 1800
    assert len(long_sample.split()) > 350
    assert _is_short_text(long_sample) is False

    # 2. Clicking Summary with short text triggers STAGE_SHORT_WARNING popup
    widget = AudioFlowFloatingWidget()
    widget._current_text = short_sample
    widget._stage = widget.STAGE_MODE_SELECT

    class FakeSummaryClick:
        x = 150
        y = 15

    widget._on_click(FakeSummaryClick())
    assert widget._stage == widget.STAGE_SHORT_WARNING
    assert widget._get_current_dimensions() == (384, 96)

    # 3. In STAGE_SHORT_WARNING: hover and click handling
    assert widget._hover_index(80, 65) == 0   # "⚡ Use Read" button
    assert widget._hover_index(220, 65) == 1  # "Make Anyway" button

    # Click on "Use Read" triggers Read mode
    triggers = []
    widget.on_trigger = lambda text, mode="read", summary_depth=None: triggers.append((text, mode, summary_depth))
    widget.hide = lambda: None

    class FakeReadClick:
        x = 80
        y = 65
    widget._on_click(FakeReadClick())
    assert len(triggers) == 1
    assert triggers[0] == (short_sample, "read", None)

    # Click on "Make Anyway" transitions to STAGE_DEPTH_SELECT
    widget._stage = widget.STAGE_SHORT_WARNING
    class FakeMakeAnywayClick:
        x = 220
        y = 65
    widget._on_click(FakeMakeAnywayClick())
    assert widget._stage == widget.STAGE_DEPTH_SELECT
    assert widget._get_current_dimensions() == (265, 32)

    # Now in STAGE_DEPTH_SELECT, picking depth triggers Summary
    triggers.clear()
    class FakePillClick:
        x = 120
        y = 15
    widget._on_click(FakePillClick())
    assert len(triggers) == 1
    assert triggers[0] == (short_sample, "summary", "balanced")

    # 4. Clicking Summary with long text directly transitions to STAGE_DEPTH_SELECT
    widget._current_text = long_sample
    widget._stage = widget.STAGE_MODE_SELECT
    widget._on_click(FakeSummaryClick())
    assert widget._stage == widget.STAGE_DEPTH_SELECT
    assert widget._get_current_dimensions() == (265, 32)


def test_audio_summary_history_persistence_and_api(tmp_path):
    """Verify SQLite persistence for audio summaries and REST API endpoints."""
    from voice_flow.storage import StorageEngine
    from voice_flow.gui.api_server import VoiceFlowApiHandler

    db_path = str(tmp_path / "voice_flow_test.db")
    storage_engine = StorageEngine(db_path=db_path)

    # 1. Add records
    rec1 = storage_engine.add_audio_summary_history(
        text="First summary text snippet covering key features.",
        depth="short",
        audio_path="C:/dummy/audio1.m4a",
        duration_sec=42.5,
        item_id="ash_test1",
    )
    rec2 = storage_engine.add_audio_summary_history(
        text="Second summary text snippet with in-depth analysis of results.",
        depth="deep_dive",
        audio_path="C:/dummy/audio2.m4a",
        duration_sec=180.0,
        item_id="ash_test2",
    )
    assert rec1["id"] == "ash_test1"
    assert rec2["id"] == "ash_test2"

    # 2. Retrieve history list
    items = storage_engine.get_audio_summary_history(limit=10)
    assert len(items) == 2
    assert items[0]["id"] == "ash_test2"  # ordered DESC by created_at
    assert items[1]["id"] == "ash_test1"

    # 3. Lookup by ID
    looked_up = storage_engine.get_audio_summary_history_by_id("ash_test1")
    assert looked_up is not None
    assert looked_up["depth"] == "short"
    assert looked_up["duration_sec"] == 42.5

    # 4. REST API: GET /api/audio-flow/history and POST /api/audio-flow/history/delete
    from unittest.mock import patch
    with patch("voice_flow.storage.storage", storage_engine), \
         patch("voice_flow.gui.api_server.storage", storage_engine):

        server = HTTPServer(("127.0.0.1", 0), VoiceFlowApiHandler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        time.sleep(0.1)
        port = server.server_address[1]
        base_url = f"http://127.0.0.1:{port}"

        try:
            # GET /api/audio-flow/history
            req = urllib.request.Request(f"{base_url}/api/audio-flow/history")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                assert data["success"] is True
                assert len(data["summaries"]) == 2
                first = data["summaries"][0]
                assert "media_url" in first
                assert "download_url" in first

            # POST /api/audio-flow/history/delete
            del_body = json.dumps({"id": "ash_test1"}).encode("utf-8")
            del_req = urllib.request.Request(
                f"{base_url}/api/audio-flow/history/delete",
                data=del_body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(del_req, timeout=5) as resp:
                del_data = json.loads(resp.read().decode("utf-8"))
                assert del_data["success"] is True

            # Verify item was deleted
            items_after = storage_engine.get_audio_summary_history(limit=10)
            assert len(items_after) == 1
            assert items_after[0]["id"] == "ash_test2"
        finally:
            server.shutdown()


def test_audio_summary_player_enhancements():
    """Verify player icon setup, compact geometry, drag API, and HTML structure."""
    from voice_flow.audio_summary_player import (
        AudioSummaryPlayerApi,
        PLAYER_HTML,
        _apply_player_icon,
        _get_player_hwnd,
    )

    # 1. Player HTML contains branding, app logo, and history elements
    assert "AUDIO FLOW" in PLAYER_HTML
    assert "/assets/logo.png" in PLAYER_HTML
    assert "history-drawer" in PLAYER_HTML
    assert "start_drag" in PLAYER_HTML
    assert "waveform-visualizer" in PLAYER_HTML

    # 2. Player API and start_drag safety
    api = AudioSummaryPlayerApi(window=None)
    # When no HWND or window is present, safely returns False without raising
    assert api.start_drag() in (True, False)

    # 3. _apply_player_icon safely handles None window without raising
    _apply_player_icon(None)


def test_audio_summary_history_lifecycle_and_migration(tmp_path):
    """Verify legacy migration and full lifecycle updates (in_progress -> progress -> ready / cancelled / failed)."""
    import sqlite3
    from voice_flow.storage import StorageEngine

    db_path = str(tmp_path / "legacy_test.db")

    # Create an old schema table missing title, status, error, progress
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE audio_summary_history (
                id TEXT PRIMARY KEY,
                text_snippet TEXT NOT NULL,
                full_text TEXT NOT NULL,
                depth TEXT NOT NULL,
                audio_path TEXT,
                duration_sec REAL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO audio_summary_history VALUES
            ('ash_old1', 'Old snippet', 'Old full text', 'short', 'C:/old.mp3', 15.0, '2026-09-01T00:00:00Z')
        """)
        conn.commit()

    # Initializing StorageEngine runs _migrate_audio_summary_history
    engine = StorageEngine(db_path=db_path)

    # 1. Verify old record was migrated with defaults
    old_item = engine.get_audio_summary_history_by_id("ash_old1")
    assert old_item is not None
    assert old_item["title"] == "Old snippet"
    assert old_item["status"] == "ready"
    assert old_item["progress"] == 100
    assert old_item["error"] is None

    # 2. Title derivation
    derived = engine._derive_audio_title("Quantum computing principles revolutionize encryption and algorithmic performance across modern secure infrastructure.")
    assert "Quantum computing principles" in derived

    # 3. Add in_progress item
    new_item = engine.add_audio_summary_history(
        text="Deep learning models for protein folding and genomic analysis.",
        depth="deep_dive",
        item_id="ash_lifecycle_1",
        status="in_progress",
        progress=0,
    )
    assert new_item["status"] == "in_progress"
    assert new_item["progress"] == 0
    assert "Deep learning" in new_item["title"]

    # 4. Update progress
    assert engine.update_audio_summary_history("ash_lifecycle_1", progress=55) is True
    updated = engine.get_audio_summary_history_by_id("ash_lifecycle_1")
    assert updated["progress"] == 55
    assert updated["status"] == "in_progress"

    # 5. Complete with ready status and audio path
    assert engine.update_audio_summary_history(
        "ash_lifecycle_1",
        status="ready",
        progress=100,
        audio_path="C:/audio/summary1.mp3",
        duration_sec=78.2,
    ) is True
    ready_item = engine.get_audio_summary_history_by_id("ash_lifecycle_1")
    assert ready_item["status"] == "ready"
    assert ready_item["progress"] == 100
    assert ready_item["duration_sec"] == 78.2
    assert ready_item["audio_path"] == "C:/audio/summary1.mp3"

    # 6. Cancelled item
    engine.add_audio_summary_history(
        text="Text for cancelled summary",
        depth="short",
        item_id="ash_cancelled",
        status="in_progress",
        progress=20,
    )
    assert engine.update_audio_summary_history("ash_cancelled", status="cancelled", progress=0) is True
    cancelled_item = engine.get_audio_summary_history_by_id("ash_cancelled")
    assert cancelled_item["status"] == "cancelled"

    # 7. Failed item with error
    engine.add_audio_summary_history(
        text="Text for failed summary",
        depth="balanced",
        item_id="ash_failed",
        status="in_progress",
        progress=30,
    )
    assert engine.update_audio_summary_history("ash_failed", status="failed", error="API connection timeout") is True
    failed_item = engine.get_audio_summary_history_by_id("ash_failed")
    assert failed_item["status"] == "failed"
    assert failed_item["error"] == "API connection timeout"


def test_audio_flow_history_play_endpoint_and_media_download(tmp_path):
    """Verify POST /api/audio-flow/history/play and GET /api/audio-flow/summary/media with download."""
    from unittest.mock import patch
    from voice_flow.storage import StorageEngine
    from voice_flow.gui.api_server import VoiceFlowApiHandler

    # Create dummy audio file inside audio_summaries
    from voice_flow.paths import data_dir
    media_dir = (data_dir() / "audio_summaries")
    media_dir.mkdir(parents=True, exist_ok=True)
    audio_file = media_dir / "test_summary_audio.m4a"
    audio_file.write_bytes(b"\x00\x00\x00\x1cftypM4A \x00\x00\x02\x00isomiso2" + b"AUDIO_DATA" * 50)

    db_path = str(tmp_path / "play_test.db")
    storage_engine = StorageEngine(db_path=db_path)
    storage_engine.add_audio_summary_history(
        text="Sample text for play test",
        depth="short",
        audio_path=str(audio_file),
        duration_sec=15.0,
        item_id="ash_play_test_1",
    )

    with patch("voice_flow.storage.storage", storage_engine), \
         patch("voice_flow.gui.api_server.storage", storage_engine):

        server = HTTPServer(("127.0.0.1", 0), VoiceFlowApiHandler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        time.sleep(0.1)
        port = server.server_address[1]
        base_url = f"http://127.0.0.1:{port}"

        try:
            # 1. Test POST /api/audio-flow/history/play
            post_body = json.dumps({"id": "ash_play_test_1", "title": "Play Title", "depth": "short"}).encode("utf-8")
            play_req = urllib.request.Request(
                f"{base_url}/api/audio-flow/history/play",
                data=post_body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(play_req, timeout=5) as resp:
                play_res = json.loads(resp.read().decode("utf-8"))
                assert play_res["success"] is True
                assert play_res["mode"] == "native_window"
                assert play_res["token"] == "ash_play_test_1"
                assert f"http://127.0.0.1:{port}" in play_res["player_url"]

            # 2. Test GET /api/audio-flow/summary/media?id=...&download=1 (Exact title and MP3 enforcement)
            dl_req = urllib.request.Request(
                f"{base_url}/api/audio-flow/summary/media?id=ash_play_test_1&download=1"
            )
            with urllib.request.urlopen(dl_req, timeout=5) as resp:
                assert resp.status == 200
                disposition = resp.headers.get("Content-Disposition", "")
                assert "attachment" in disposition
                assert "Sample text for play test.mp3" in disposition
                assert "test_summary_audio.m4a" not in disposition
                assert int(resp.headers.get("Content-Length", 0)) > 0
                assert "Content-Disposition" in resp.headers.get("Access-Control-Expose-Headers", "")

            # 2b. Test explicit title parameter in GET /api/audio-flow/summary/media
            dl_req_title = urllib.request.Request(
                f"{base_url}/api/audio-flow/summary/media?id=ash_play_test_1&download=1&title=Quantum+Computing+Explained"
            )
            with urllib.request.urlopen(dl_req_title, timeout=5) as resp:
                assert resp.status == 200
                disposition = resp.headers.get("Content-Disposition", "")
                assert "attachment" in disposition
                assert "Quantum Computing Explained.mp3" in disposition
                assert not disposition.lower().endswith(".mp4")

            # 3. Test Invalid ID
            invalid_req = urllib.request.Request(
                f"{base_url}/api/audio-flow/history/play",
                data=json.dumps({"id": "non_existent_id"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(invalid_req, timeout=5) as resp:
                    pass
            except urllib.error.HTTPError as err:
                assert err.code == 404

        finally:
            server.shutdown()
            if audio_file.exists():
                try:
                    audio_file.unlink()
                except OSError:
                    pass


def test_video_flow_download_exact_title_and_mp4_enforcement(tmp_path):
    """Verify Video Flow downloads enforce .mp4 extension, video/mp4 MIME, and exact app title."""
    from http.server import HTTPServer
    import json
    import threading
    import time
    import urllib.parse
    import urllib.request
    from unittest.mock import patch, MagicMock
    from voice_flow.gui.api_server import VoiceFlowApiHandler
    from voice_flow.paths import data_dir
    from voice_flow.video_flow_contracts import JobV3

    # Setup dummy video file
    job_id = "vf_title_test_1"
    proj_dir = data_dir() / "v3_projects" / job_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    video_file = proj_dir / "video.mp4"
    video_file.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42" + b"MP4_DATA" * 50)

    mock_job = JobV3(
        job_id=job_id,
        state="complete",
        progress=100.0,
        meta={"title": "Quantum Odyssey: Inside Future AI", "output_path": str(video_file)},
    )
    mock_service = MagicMock()
    mock_service.get.return_value = mock_job

    with patch("voice_flow.gui.api_server.get_video_flow_service", return_value=mock_service):
        server = HTTPServer(("127.0.0.1", 0), VoiceFlowApiHandler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        time.sleep(0.1)
        port = server.server_address[1]
        base_url = f"http://127.0.0.1:{port}"

        try:
            # 1. Download without explicit title in query: picks up job.meta["title"]
            dl_req = urllib.request.Request(
                f"{base_url}/api/video-flow/videos/file?id={job_id}&download=1"
            )
            with urllib.request.urlopen(dl_req, timeout=5) as resp:
                assert resp.status == 200
                assert resp.headers.get("Content-Type") == "video/mp4"
                disposition = resp.headers.get("Content-Disposition", "")
                assert "attachment" in disposition
                assert "Quantum Odyssey Inside Future AI.mp4" in disposition
                assert not disposition.lower().endswith(".mp3")
                assert not disposition.lower().endswith(".m4a")

            # 2. Download with explicit title param in query
            explicit_req = urllib.request.Request(
                f"{base_url}/api/video-flow/videos/file?id={job_id}&download=1&title=Special+Deep+Dive+Edition"
            )
            with urllib.request.urlopen(explicit_req, timeout=5) as resp:
                assert resp.status == 200
                assert resp.headers.get("Content-Type") == "video/mp4"
                disposition = resp.headers.get("Content-Disposition", "")
                assert "attachment" in disposition
                assert "Special Deep Dive Edition.mp4" in disposition

        finally:
            server.shutdown()
            if video_file.exists():
                try:
                    video_file.unlink()
                except OSError:
                    pass
            if proj_dir.exists():
                try:
                    proj_dir.rmdir()
                except OSError:
                    pass


import os
import shutil
import tempfile
from pathlib import Path
import pytest

from voice_flow.audio_summary_player import (
    safe_media_filename,
    save_media_to_downloads,
    get_user_downloads_dir,
    resolve_summary_audio,
)


def test_safe_media_filename_exact_titles():
    name = safe_media_filename("My Super Cool Audio Summary", ext=".mp3")
    assert name == "My Super Cool Audio Summary.mp3"

    name2 = safe_media_filename("Report: AI Alignment - Analysis (2026)", ext=".mp4")
    assert name2 == "Report AI Alignment - Analysis (2026).mp4"

    name3 = safe_media_filename('Title with / and : and "quotes" and ? question', ext=".mp3")
    assert name3 == "Title with and and quotes and question.mp3"


def test_save_media_to_downloads_collision_and_exact_naming(tmp_path, monkeypatch):
    dl_dir = tmp_path / "Downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("voice_flow.audio_summary_player.get_user_downloads_dir", lambda: dl_dir)

    src_file = tmp_path / "sample.mp3"
    src_file.write_bytes(b"TEST_AUDIO_CONTENT_12345")

    saved_p, final_name = save_media_to_downloads(src_file, "Audio Summary Title.mp3")
    assert saved_p.is_file()
    assert saved_p.read_bytes() == b"TEST_AUDIO_CONTENT_12345"
    assert final_name == "Audio Summary Title.mp3"

    saved_p2, final_name2 = save_media_to_downloads(src_file, "Audio Summary Title.mp3")
    assert final_name2 == "Audio Summary Title.mp3"

    src_file_diff = tmp_path / "sample_diff.mp3"
    src_file_diff.write_bytes(b"DIFFERENT_CONTENT_67890")
    saved_p3, final_name3 = save_media_to_downloads(src_file_diff, "Audio Summary Title.mp3")
    assert final_name3 == "Audio Summary Title (1).mp3"
    assert saved_p3.is_file()
    assert saved_p3.read_bytes() == b"DIFFERENT_CONTENT_67890"


def test_no_webbrowser_open_in_player_source():
    player_file = Path(__file__).resolve().parent.parent / "src" / "voice_flow" / "audio_summary_player.py"
    content = player_file.read_text(encoding="utf-8")
    assert "webbrowser.open" not in content, "audio_summary_player.py must not call webbrowser.open"


def test_no_window_open_in_app_js_play():
    app_js = Path(__file__).resolve().parent.parent / "src" / "voice_flow" / "gui" / "app.js"
    content = app_js.read_text(encoding="utf-8")
    play_fn_start = content.find("async function playAudioSummary(")
    play_fn_end = content.find("function afSafeMediaFilename(", play_fn_start)
    play_fn_body = content[play_fn_start:play_fn_end]
    assert "window.open" not in play_fn_body, "playAudioSummary must not fallback to window.open"


def test_safe_media_filename_truncation_and_replacement_recovery():
    raw_title = "AI Productivity Flow \ufffd Transform Information Without Leav..."
    source = "AI Productivity Flow \ufffd Transform Information Without Leaving Your Workflow\n\nWe use AI every day."
    filename = safe_media_filename(raw_title, ext=".mp4", source_text=source)
    assert filename == "AI Productivity Flow - Transform Information Without Leaving Your Workflow.mp4"

    # Also test without source recovery: replacement char is cleanly converted to dash
    filename_direct = safe_media_filename("My File \ufffd Part 1...", ext=".mp3")
    assert filename_direct == "My File - Part 1.mp3"


def test_audio_summary_history_downloaded_persistence():
    from voice_flow.storage import storage
    item = storage.add_audio_summary_history(
        text="Test text for download persistence test",
        depth="balanced",
        title="Persistence Test Summary",
    )
    assert item["downloaded"] is False

    retrieved = storage.get_audio_summary_history_by_id(item["id"])
    assert retrieved is not None
    assert retrieved["downloaded"] is False

    success = storage.update_audio_summary_history(item["id"], downloaded=1)
    assert success is True

    updated = storage.get_audio_summary_history_by_id(item["id"])
    assert updated is not None
    assert updated["downloaded"] is True


def test_on_screen_ui_settings_toggle_structure():
    index_html = Path(__file__).resolve().parent.parent / "src" / "voice_flow" / "gui" / "index.html"
    content = index_html.read_text(encoding="utf-8")
    assert 'id="toggle-on-screen-ui-theme"' in content
    assert 'id="on-screen-ui-theme-label"' in content
    assert "toggleOnScreenUITheme(this.checked)" in content

    app_js = Path(__file__).resolve().parent.parent / "src" / "voice_flow" / "gui" / "app.js"
    js_content = app_js.read_text(encoding="utf-8")
    assert "function toggleOnScreenUITheme(" in js_content
    assert "toggle.checked = isDark;" in js_content


def test_get_user_videos_and_music_dir():
    from voice_flow.audio_summary_player import get_user_videos_dir, get_user_music_dir
    v_dir = get_user_videos_dir()
    m_dir = get_user_music_dir()
    assert isinstance(v_dir, Path)
    assert isinstance(m_dir, Path)
    assert v_dir.is_dir()
    assert m_dir.is_dir()


def test_save_media_to_downloads_copies_to_media_folder(tmp_path, monkeypatch):
    from voice_flow.audio_summary_player import (
        save_media_to_downloads,
        get_user_downloads_dir,
        get_user_videos_dir,
        get_user_music_dir,
    )
    dl_dir = tmp_path / "Downloads"
    vid_dir = tmp_path / "Videos"
    mus_dir = tmp_path / "Music"
    dl_dir.mkdir(parents=True, exist_ok=True)
    vid_dir.mkdir(parents=True, exist_ok=True)
    mus_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("voice_flow.audio_summary_player.get_user_downloads_dir", lambda: dl_dir)
    monkeypatch.setattr("voice_flow.audio_summary_player.get_user_videos_dir", lambda: vid_dir)
    monkeypatch.setattr("voice_flow.audio_summary_player.get_user_music_dir", lambda: mus_dir)

    # 1. Test video file
    vid_src = tmp_path / "input_video.mp4"
    vid_src.write_bytes(b"VIDEO_CONTENT_12345")
    saved_p, final_name = save_media_to_downloads(vid_src, "My Project Video.mp4")
    assert saved_p.parent == dl_dir
    assert final_name == "My Project Video.mp4"
    # Verify copied to user's Videos folder
    vid_target = vid_dir / "My Project Video.mp4"
    assert vid_target.is_file()
    assert vid_target.read_bytes() == b"VIDEO_CONTENT_12345"

    # 2. Test audio file
    aud_src = tmp_path / "input_audio.mp3"
    aud_src.write_bytes(b"AUDIO_CONTENT_67890")
    saved_a, final_a_name = save_media_to_downloads(aud_src, "My Audio Podcast.mp3")
    assert saved_a.parent == dl_dir
    assert final_a_name == "My Audio Podcast.mp3"
    # Verify copied to user's Music folder
    mus_target = mus_dir / "My Audio Podcast.mp3"
    assert mus_target.is_file()
    assert mus_target.read_bytes() == b"AUDIO_CONTENT_67890"


def test_storage_record_video_and_audio_to_history(tmp_path):
    from voice_flow.storage import StorageEngine
    db_file = tmp_path / "test_storage.db"
    store = StorageEngine(str(db_file))

    # Record video
    v_id = store.record_video_history(
        job_id="vf-test12345",
        title="Autonomous Driving Demo",
        prompt="A car driving smoothly through town",
        output_path="C:/videos/test.mp4",
        duration_sec=15.0,
        status="success",
    )
    assert v_id is not None

    recent = store.get_recent_history(limit=10)
    video_entries = [r for r in recent if r["app_name"] == "Video Flow"]
    assert len(video_entries) == 1
    assert video_entries[0]["polished_text"] == "Autonomous Driving Demo"
    assert video_entries[0]["style_mode"] == "video_flow"
    assert video_entries[0]["duration_sec"] == 15.0

    # Record audio
    a_id = store.record_audio_summary_to_history(
        audio_id="ash_test999",
        title="Weekly Summary",
        text_snippet="Here is what happened this week in tech",
        audio_path="C:/audio/summary.mp3",
        duration_sec=30.0,
        status="success",
    )
    assert a_id is not None

    recent = store.get_recent_history(limit=10)
    audio_entries = [r for r in recent if r["app_name"] == "Audio Flow"]
    assert len(audio_entries) == 1
    assert audio_entries[0]["polished_text"] == "Weekly Summary"
    assert audio_entries[0]["style_mode"] == "audio_flow"


def test_storage_sync_media_to_history(tmp_path):
    import sqlite3, json
    from voice_flow.storage import StorageEngine
    from voice_flow.video_flow_service import VideoFlowStore, JobV3

    db_file = tmp_path / "test_sync.db"
    store = StorageEngine(str(db_file))
    vf_store = VideoFlowStore(db_file)

    # Insert video jobs
    job1 = JobV3(
        job_id="vf-sync1",
        state="complete",
        progress=100.0,
        message="Done",
        meta={"title": "Synced Video 1", "prompt": "Prompt 1", "output_path": "path1.mp4", "duration": 12.0},
    )
    vf_store.create(job1)

    # Insert audio summary history directly
    with store._get_conn() as conn:
        conn.execute(
            """
            INSERT INTO audio_summary_history (id, text_snippet, full_text, depth, audio_path, duration_sec, created_at, title, status, error, progress, downloaded)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ash_sync1", "Snippet 1", "Full text 1", "balanced", "path1.m4a", 20.0, "2026-09-17 12:00:00", "Synced Audio 1", "ready", None, 100, 0),
        )
        conn.commit()

    # Call sync_media_to_history
    res = store.sync_media_to_history()
    assert res["videos"] >= 1
    assert res["audios"] >= 1

    recent = store.get_recent_history(limit=20)
    vf_items = [r for r in recent if r["app_name"] == "Video Flow" and r["insertion_status"] == "vf-sync1"]
    af_items = [r for r in recent if r["app_name"] == "Audio Flow" and r["insertion_status"] == "ash_sync1"]
    assert len(vf_items) == 1
    assert vf_items[0]["polished_text"] == "Synced Video 1"
    assert len(af_items) == 1
    assert af_items[0]["polished_text"] == "Synced Audio 1"


def test_vf_history_body_no_inline_display_none():
    index_html = Path(__file__).resolve().parent.parent / "src" / "voice_flow" / "gui" / "index.html"
    content = index_html.read_text(encoding="utf-8")
    assert '<div id="vf-history-body" style="display: none;">' not in content
    assert '<div id="vf-history-body">' in content



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


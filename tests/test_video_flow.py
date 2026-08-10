from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from voice_flow.video_flow import (
    PERMANENT_DELETE_CONFIRMATION,
    VideoFlowPlanner,
    VideoFlowStore,
)


def test_full_explanation_preserves_every_source_character() -> None:
    source = "First paragraph keeps punctuation.\n\nSecond paragraph keeps 100% of the source."

    plan = VideoFlowPlanner().build(source, mode="full", title="Exact source")

    assert "".join(scene["narration"] for scene in plan["scenes"]) == source
    assert plan["coverage"]["source_characters"] == len(source)
    assert plan["coverage"]["narrated_characters"] == len(source)
    assert plan["coverage"]["complete"] is True


def test_summary_mode_is_shorter_and_marks_itself_as_summary() -> None:
    source = " ".join(
        f"Sentence {index} explains a different part of the research in useful detail."
        for index in range(1, 21)
    )

    plan = VideoFlowPlanner().build(source, mode="summary", title="Research summary")
    narration = " ".join(scene["narration"] for scene in plan["scenes"])

    assert len(narration) < len(source)
    assert plan["mode"] == "summary"
    assert plan["coverage"]["complete"] is False


def test_store_persists_history_and_combo_order() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        store = VideoFlowStore(
            db_path=os.path.join(temp_dir, "voice-flow.db"),
            output_root=os.path.join(temp_dir, "videos"),
        )
        video = store.create_video(
            title="My explanation",
            mode="full",
            source_text="hello world",
            model_ref="combo:reliable",
        )
        combo = store.create_combo(
            "reliable",
            ["gemini/gemini-2.5-flash", "openai/gpt-4o-mini"],
            strategy="fallback",
        )

        assert store.list_videos()[0]["id"] == video["id"]
        assert combo["models"] == [
            "gemini/gemini-2.5-flash",
            "openai/gpt-4o-mini",
        ]
        assert store.list_combos()[0]["name"] == "reliable"


def test_permanent_delete_requires_confirmation_and_removes_project_files() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        store = VideoFlowStore(
            db_path=os.path.join(temp_dir, "voice-flow.db"),
            output_root=os.path.join(temp_dir, "videos"),
        )
        video = store.create_video(
            title="Delete me",
            mode="summary",
            source_text="temporary",
            model_ref="local/deterministic",
        )
        project_dir = Path(video["project_dir"])
        output_path = project_dir / "output.mp4"
        output_path.write_bytes(b"video")
        store.update_video(video["id"], output_path=str(output_path), status="completed")

        with pytest.raises(PermissionError):
            store.delete_video(video["id"], confirmation="yes")

        assert output_path.exists()
        assert store.delete_video(video["id"], confirmation=PERMANENT_DELETE_CONFIRMATION)
        assert not project_dir.exists()
        assert store.get_video(video["id"]) is None

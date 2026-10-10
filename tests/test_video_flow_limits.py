from __future__ import annotations

from pathlib import Path

import pytest

from voice_flow.video_flow_engine.bridge import build_narova_production
from voice_flow.video_flow_engine.engine import VideoFlowEngine


class _MustNotRun:
    def plan(self, source_text: str, **options: object) -> dict:
        raise AssertionError("planner must not run for oversized source")

    def render(self, production: dict, project_dir: Path, **options: object) -> Path:
        raise AssertionError("renderer must not run for oversized source")


def test_source_text_limit_prevents_unbounded_planning_cost(tmp_path: Path) -> None:
    dependency = _MustNotRun()
    result = VideoFlowEngine(planner=dependency, renderer=dependency).run(
        "oversized-source",
        projects_root=tmp_path,
        source_text="x" * 100_001,
    )

    assert result["state"] == "failed"
    assert result["error_code"] == "planning_failed"


def test_storyboard_scene_limit_prevents_unbounded_render_cost() -> None:
    sections = [
        {"id": f"scene_{index}", "title": "Scene", "lecture_lines": ["Line"], "animations": ["Reveal"]}
        for index in range(25)
    ]
    with pytest.raises(ValueError, match="24-scene limit"):
        build_narova_production({"topic": "Too large", "sections": sections})

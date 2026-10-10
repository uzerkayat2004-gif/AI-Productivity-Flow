"""Creative Director + scene authoring + engine fallback tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from voice_flow.video_flow_engine import scene_author
from voice_flow.video_flow_engine.bridge import build_directed_production, build_narova_production
from voice_flow.video_flow_engine.creative_director import (
    MAX_CONSECUTIVE,
    TREATMENTS,
    DirectorError,
    direct,
)
from voice_flow.video_flow_engine.engine import VideoFlowEngine
from voice_flow.video_flow_engine.sandbox import EngineError


def _storyboard(count: int = 4) -> dict[str, Any]:
    return {
        "topic": "Why is the sky blue?",
        "sections": [
            {
                "id": f"scene_{i}",
                "title": f"Concept {i}",
                "learning_goal": "understand",
                "lecture_lines": [f"Teaching line {i} about the concept.", "Second supporting line."],
                "animations": [],
            }
            for i in range(1, count + 1)
        ],
    }


class _FakeGateway:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def request_isolated(self, **kwargs: Any) -> str:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_deterministic_direction_without_gateway() -> None:
    direction = direct(_storyboard(4), None)
    assert {entry["index"] for entry in direction["scenes"]} == {1, 2, 3, 4}
    treatments = [entry["treatment"] for entry in direction["scenes"]]
    assert all(t in TREATMENTS for t in treatments)
    assert treatments[0] == "hero-title"
    assert treatments[-1] == "recap-mosaic"


def test_direction_diversity_limits_repetition() -> None:
    storyboard = _storyboard(6)
    direction = direct(storyboard, None)
    treatments = [entry["treatment"] for entry in direction["scenes"]]
    for treatment in set(treatments):
        assert treatments.count(treatment) <= max(2, int(0.45 * len(treatments) + 0.999)) or treatment in ("hero-title", "recap-mosaic")
    run = 1
    for previous, current in zip(treatments, treatments[1:]):
        run = run + 1 if current == previous else 1
        assert run <= MAX_CONSECUTIVE


def test_model_direction_parses_fenced_json_and_sanitizes() -> None:
    payload = {
        "brief": {"motion": "flowing", "background": "grid", "accent_shift": 1},
        "scenes": [
            {
                "index": 1,
                "treatment": "wave-demo",
                "title_label": "Light is a spectrum of waves",
                "labels": ["short blue waves", "long red waves", "scattering", "everywhere in the sky at once"],
                "svg_paths": ["M0 0 L100 100", "javascript:alert(1)"],
                "count_to": "not-a-number",
                "transition": "zoom",
            },
            {
                "index": 2,
                "treatment": "orbit-3d",
                "title_label": "Molecules in the air",
                "labels": [],
                "three_hint": "orbit",
            },
        ],
    }
    gateway = _FakeGateway("Here you go:\n```json\n" + json.dumps(payload) + "\n```\nThanks!")
    direction = direct(_storyboard(2), gateway)
    first = direction["scenes"][0]
    assert first["treatment"] == "wave-demo"
    assert first["svg_paths"] == ["M0 0 L100 100"]  # dangerous path dropped
    assert "count_to" not in first  # non-numeric value dropped
    assert len(first["labels"]) == 4
    assert direction["scenes"][1]["three_hint"] == "orbit"
    assert direction["brief"]["motion"] == "flowing"


def test_model_direction_falls_back_on_garbage() -> None:
    gateway = _FakeGateway("I cannot answer that in JSON, sorry!")
    direction = direct(_storyboard(3), gateway)
    assert direction["scenes"][0]["treatment"] == "hero-title"


def test_every_treatment_authors_a_script_free_scene() -> None:
    design = scene_author.resolve_design({"brief": {}}, None)
    for index, treatment in enumerate(TREATMENTS, start=1):
        entry = {"index": index, "treatment": treatment, "title_label": "Title", "labels": ["One", "Two words"], "transition": "fade"}
        if treatment in ("counter-stats", "chart-growth", "scale-comparison"):
            entry["count_to"] = 42
        if treatment in ("particle-field", "orbit-3d", "cutaway-3d"):
            entry["three_hint"] = treatment.replace("-3d", "").replace("field", "particles") if treatment != "cutaway-3d" else "layers"
        scene = scene_author.author_scene({"id": f"s{index}", "lecture_lines": ["Narration line."]}, entry, design, index)
        assert scene["body"], treatment
        assert "<script" not in scene["body"]
        assert "javascript:" not in scene["body"]
        assert scene["vo"][0]["text"]


def test_build_directed_production_shape_and_security() -> None:
    direction = direct(_storyboard(3), None)
    production = build_directed_production(_storyboard(3), direction, title="T", mode="summary")
    assert production["renderer"] == "hyperframes"
    assert production["theme"]["css"] == "theme.css"
    assert "theme.css" in production["_files"]
    assert len(production["scenes"]) == 3
    joined = json.dumps(production)
    assert "<script" not in joined and "eval(" not in joined


def test_build_directed_production_rejects_empty_storyboard() -> None:
    with pytest.raises(ValueError):
        build_directed_production({"sections": []}, {"brief": {}, "scenes": []})


def test_runner_writes_auxiliary_files_safely(tmp_path: Path) -> None:
    from voice_flow.video_flow_engine.narova_runner import NarovaRunner

    production = {
        "title": "X",
        "renderer": "hyperframes",
        "scenes": [{"id": "a", "dur": 2, "body": "<p>hi</p>"}],
        "_files": {
            "theme.css": "body{}",
            "../escape.txt": "nope",
            "C:/abs.txt": "nope",
            "deep/dir/scene.css": ".a{}",
        },
    }
    narova_dir = NarovaRunner()._write_project(production, tmp_path)
    assert (narova_dir / "theme.css").is_file()
    assert (narova_dir / "deep" / "dir" / "scene.css").is_file()
    assert not (narova_dir / ".." / "escape.txt").exists()
    assert "deep/dir/scene.css" not in (narova_dir / "reel.config.json").read_text(encoding="utf-8")


class _FakeRenderer:
    def __init__(self) -> None:
        self.productions: list[dict[str, Any]] = []
        self.fail_hyperframes = True

    def render(self, production: dict[str, Any], project_dir: Path, **kwargs: Any) -> Path:
        self.productions.append(production)
        if self.fail_hyperframes and production.get("renderer") == "hyperframes":
            raise EngineError("render_failed", "browser unavailable")
        target = Path(project_dir) / "video.mp4"
        target.write_bytes(b"video")
        return target


class _FakePlanner:
    def plan(self, source_text: str, **kwargs: Any) -> dict[str, Any]:
        return _storyboard(2)


def test_engine_falls_back_to_portable_renderer(tmp_path: Path) -> None:
    renderer = _FakeRenderer()
    engine = VideoFlowEngine(planner=_FakePlanner(), renderer=renderer)
    result = engine.run(
        "vf-test-fallback",
        source_text="Why is the sky blue?",
        project_dir=tmp_path / "vf-test-fallback",
        projects_root=tmp_path,
        progress_callback=lambda event: None,
        job=None,
    )
    assert result["state"] == "complete", result
    assert renderer.productions[0]["renderer"] == "hyperframes"
    assert renderer.productions[1]["renderer"] == "no-browser"


def test_engine_prefers_directed_production_when_browser_works(tmp_path: Path) -> None:
    renderer = _FakeRenderer()
    renderer.fail_hyperframes = False
    engine = VideoFlowEngine(planner=_FakePlanner(), renderer=renderer)
    result = engine.run(
        "vf-test-directed",
        source_text="Why is the sky blue?",
        project_dir=tmp_path / "vf-test-directed",
        projects_root=tmp_path,
        progress_callback=lambda event: None,
        job=None,
    )
    assert result["state"] == "complete", result
    assert len(renderer.productions) == 1
    assert renderer.productions[0]["renderer"] == "hyperframes"


def test_legacy_bridge_still_available() -> None:
    production = build_narova_production(_storyboard(2), title="L", mode="summary")
    assert production["renderer"] == "no-browser"
    assert production["scenes"][0]["visual"]


# Narova's declarative three.js whitelist (renderers/visual.js PRIMITIVE_TYPES).
_NAROVA_THREE_TYPES = {
    "cube", "sphere", "cylinder", "plane", "torus", "cone", "ring",
    "icosahedron", "dodecahedron", "octahedron", "tetrahedron", "torusKnot",
    "model", "group", "particles",
}


def test_three_configs_match_narova_schema() -> None:
    """Regression: `points`/`box` types and scalar spreads fail `narova check`."""
    design = scene_author.resolve_design({"brief": {}}, None)
    for treatment in ("particle-field", "orbit-3d", "cutaway-3d"):
        entry = {"index": 1, "treatment": treatment, "title_label": "T", "labels": ["A", "B"], "transition": "fade"}
        scene = scene_author.author_scene({"id": "s1", "lecture_lines": ["Line."]}, entry, design, 1)
        three = scene.get("three")
        assert three, treatment
        for obj in three.get("objects", []):
            assert obj["type"] in _NAROVA_THREE_TYPES, (treatment, obj["type"])
            if obj["type"] == "particles":
                spread = obj.get("spread")
                assert isinstance(spread, list) and len(spread) == 3

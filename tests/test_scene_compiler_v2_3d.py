"""Safety and compatibility tests for the declarative Visual V2 3D compiler."""
from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from voice_flow import runtime_env as _runtime_env
from voice_flow.video_flow_engine.scene_compiler_v2 import SceneCompilerV2Error, compile_visual_plan_v2
from voice_flow.video_flow_engine.visual_plan_v2 import parse_video_visual_plan_v2

_ANIMATION_PROPERTIES = {"position.x", "position.y", "position.z", "rotation.x", "rotation.y", "rotation.z", "scale.x", "scale.y", "scale.z", "scale", "opacity"}
_PRIMITIVES = {"cube", "sphere", "cylinder", "plane", "torus", "cone", "icosahedron", "particles"}
_LIGHTS = {"ambient", "directional", "point", "spot", "hemisphere"}


def _design_bible() -> dict[str, Any]:
    return {
        "visual_character": "technical spatial systems", "surface_mode": "metallic",
        "palette_intent": {"dominant": "near-black", "contrast": "very-high", "accent_family": "signal-red", "secondary_family": "hard-white", "temperature": "neutral", "saturation": "selective"},
        "typography_character": "technical", "shape_language": "architectural", "background_character": "solid",
        "motion_character": "technical", "transition_character": "fade", "camera_character": "orbit", "caption_integration": "reserved-bottom",
    }


def _storyboard(count: int = 4) -> dict[str, Any]:
    return {"topic": "Semantic spatial mechanisms", "sections": [{"id": f"section_{index}", "lecture_lines": [f"Explain semantic object {index}."]} for index in range(1, count + 1)]}


def _scene(index: int, object_type: str) -> dict[str, Any]:
    object_id = f"object_{index}"
    return {
        "scene_id": f"scene_{index}", "storyboard_section_id": f"section_{index}",
        "learning_goal": "Explain the spatial object.", "visual_thesis": "A spatial object reveals structure.",
        "visual_mode": "spatial", "objects": [{"id": object_id, "type": object_type, "label": f"{object_type} label", "role": "primary", "region": "center"}],
        "relationships": [], "beats": [{"order": 1, "phase": "build", "action": "rotate", "object_id": object_id, "reason": "Show spatial structure."}],
        "continuity": {"carry_forward": []}, "camera_intent": "orbit",
    }


def _payload(types: tuple[str, ...] = ("particle_group", "mesh", "light", "camera_target")) -> tuple[dict[str, Any], dict[str, Any]]:
    storyboard = _storyboard(len(types))
    return storyboard, {"version": "2.0", "design_bible": _design_bible(), "scenes": [_scene(index, kind) for index, kind in enumerate(types, start=1)]}


def _compile(types: tuple[str, ...] = ("particle_group", "mesh", "light", "camera_target")) -> Any:
    storyboard, payload = _payload(types)
    plan = parse_video_visual_plan_v2(payload, storyboard=storyboard)
    return compile_visual_plan_v2(storyboard, plan)


def _finite(value: Any) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_finite(item) for item in value)
    if isinstance(value, dict):
        return all(_finite(item) for item in value.values())
    return True


def test_all_semantic_3d_types_compile_to_declarative_narova_scenes() -> None:
    compiled = _compile()
    scenes = compiled.production["scenes"]
    assert len(scenes) == 4
    assert all("three" in scene for scene in scenes)
    assert all('v2-stage v2-clear' in scene["body"] for scene in scenes)
    assert all("<script" not in scene["body"].lower() for scene in scenes)


def test_three_configs_use_only_finite_whitelisted_data_without_loops() -> None:
    compiled = _compile()
    for scene in compiled.production["scenes"]:
        three = scene["three"]
        assert set(three) == {"camera", "toneMapping", "background", "lights", "objects"}
        assert set(three["camera"]) == {"position", "lookAt", "fov", "near", "far"}
        assert _finite(three)
        for light in three["lights"]:
            assert light["type"] in _LIGHTS
        for obj in three["objects"]:
            assert obj["type"] in _PRIMITIVES
            assert obj.get("loop") is None
            if obj["type"] == "particles":
                assert obj["animated"] is False
            if "animate" in obj:
                animation = obj["animate"]
                assert animation["property"] in _ANIMATION_PROPERTIES
                assert 0 < animation["duration"] <= 2.8
                assert "loop" not in animation
    serialized = json.dumps(compiled.production).lower()
    assert "threemodule" not in serialized
    assert "<script" not in serialized


def test_three_compilation_is_deterministic_and_2d_scenes_remain_2d() -> None:
    first = _compile(("mesh",))
    second = _compile(("mesh",))
    assert first.production == second.production
    storyboard, payload = _payload(("mesh",))
    two_d_payload = deepcopy(payload)
    two_d_payload["scenes"][0]["objects"][0]["type"] = "node"
    two_d_plan = parse_video_visual_plan_v2(two_d_payload, storyboard=storyboard)
    two_d = compile_visual_plan_v2(storyboard, two_d_plan)
    assert "three" not in two_d.production["scenes"][0]
    assert "v2-stage v2-clear" not in two_d.production["scenes"][0]["body"]


def test_compiler_rejects_more_than_twelve_semantic_3d_scenes() -> None:
    types = tuple("mesh" for _ in range(13))
    storyboard, payload = _payload(types)
    plan = parse_video_visual_plan_v2(payload, storyboard=storyboard)
    with pytest.raises(SceneCompilerV2Error, match="at most 12"):
        compile_visual_plan_v2(storyboard, plan)


@pytest.mark.skipif(not (_runtime_env.narova_tool_root() and (_runtime_env.narova_tool_root() / "tool" / "bin" / "narova.js").is_file()), reason="vendored Narova tool not present")
def test_semantic_three_fixture_passes_vendored_narova_check(tmp_path: Path) -> None:
    from voice_flow.video_flow_engine.narova_runner import NarovaRunner
    compiled = _compile(("mesh", "particle_group"))
    config_path = NarovaRunner().check(compiled.production, tmp_path, job_id="v2-three-check")
    assert config_path.is_file()

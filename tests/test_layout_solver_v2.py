from __future__ import annotations

import pytest

from voice_flow.video_flow_engine.layout_solver import LayoutV2Error, layout_video_plan
from voice_flow.video_flow_engine.visual_plan_v2 import parse_video_visual_plan_v2


def _design() -> dict:
    return {
        "visual_character": "technical systems",
        "surface_mode": "technical",
        "palette_intent": {
            "dominant": "near-black",
            "contrast": "very-high",
            "accent_family": "signal-red",
            "secondary_family": "hard-white",
            "temperature": "neutral",
            "saturation": "selective",
        },
        "typography_character": "technical",
        "shape_language": "diagrammatic",
        "background_character": "grid",
        "motion_character": "technical",
        "transition_character": "fade",
        "camera_character": "focus",
        "caption_integration": "reserved-bottom",
    }


def _object(object_id: str, region: str = "foreground") -> dict:
    return {"id": object_id, "type": "node", "label": object_id.replace("_", " "), "role": "primary", "region": region}


def _scene(scene_id: str, section_id: str, objects: list[dict], *, relationships: list[dict] | None = None, carry_forward: list[str] | None = None) -> dict:
    return {
        "scene_id": scene_id,
        "storyboard_section_id": section_id,
        "learning_goal": "Explain the relationship.",
        "visual_thesis": "Objects appear and reveal their relationship.",
        "visual_mode": "mechanism",
        "objects": objects,
        "relationships": relationships or [],
        "beats": [{"order": 1, "phase": "intro", "action": "reveal", "object_id": objects[0]["id"], "reason": "Focus attention."}],
        "continuity": {"carry_forward": carry_forward or []},
    }


def _plan(scenes: list[dict]):
    storyboard = {"sections": [{"id": scene["storyboard_section_id"], "title": scene["scene_id"]} for scene in scenes]}
    return parse_video_visual_plan_v2({"version": "2.0", "design_bible": _design(), "scenes": scenes}, storyboard=storyboard)


def _overlaps(first, second) -> bool:
    return first.x < second.right and second.x < first.right and first.y < second.bottom and second.y < first.bottom


def test_default_layout_is_deterministic_hd_and_caption_safe() -> None:
    plan = _plan([_scene("mechanism", "section_1", [_object("input"), _object("transform"), _object("result")], relationships=[{"source": "input", "target": "transform", "kind": "flows_to"}, {"source": "transform", "target": "result", "kind": "connects_to"}])])
    first = layout_video_plan(plan)
    second = layout_video_plan(plan)
    assert first.to_dict() == second.to_dict()
    assert (first.width, first.height, first.caption_safe_bottom) == (1920, 1080, 170)
    objects = first.scenes[0].objects
    for item in objects:
        assert item.box.x >= 0 and item.box.y >= 0
        assert item.box.right <= 1920
        assert item.box.bottom <= 1080 - 170
        assert item.box.width >= 200
        assert item.box.height >= 120
    assert not any(_overlaps(one.box, two.box) for index, one in enumerate(objects) for two in objects[index + 1 :])


def test_regions_and_semantic_constraints_are_honored() -> None:
    plan = _plan([_scene("arrangement", "section_1", [_object("left", "left"), _object("center", "center"), _object("right", "right"), _object("top", "top"), _object("bottom", "bottom")], relationships=[{"source": "left", "target": "center", "kind": "left_of"}, {"source": "right", "target": "center", "kind": "right_of"}, {"source": "top", "target": "bottom", "kind": "above"}])])
    objects = {item.id: item for item in layout_video_plan(plan).scenes[0].objects}
    center_x = lambda item: item.box.x + item.box.width // 2
    center_y = lambda item: item.box.y + item.box.height // 2
    assert center_x(objects["left"]) < center_x(objects["center"]) < center_x(objects["right"])
    assert center_y(objects["top"]) < center_y(objects["bottom"])


def test_simple_flow_is_layered_left_to_right() -> None:
    plan = _plan([_scene("flow", "section_1", [_object("source"), _object("middle"), _object("target")], relationships=[{"source": "source", "target": "middle", "kind": "flows_to"}, {"source": "middle", "target": "target", "kind": "connects_to"}])])
    objects = {item.id: item for item in layout_video_plan(plan).scenes[0].objects}
    assert objects["source"].box.x < objects["middle"].box.x < objects["target"].box.x


def test_carry_forward_preserves_stable_geometry() -> None:
    first = _scene("first", "section_1", [_object("origin", "left")])
    second = _scene("second", "section_2", [_object("result", "right")], relationships=[{"source": "origin", "target": "result", "kind": "flows_to"}], carry_forward=["origin"])
    video = layout_video_plan(_plan([first, second]))
    origin = video.scenes[0].objects[0]
    carried = video.scenes[1].objects[0]
    assert carried.id == "origin"
    assert carried.carried is True
    assert carried.box == origin.box


def test_contradictory_semantic_constraints_raise_typed_error() -> None:
    plan = _plan([_scene("contradiction", "section_1", [_object("a"), _object("b")], relationships=[{"source": "a", "target": "b", "kind": "left_of"}, {"source": "b", "target": "a", "kind": "left_of"}])])
    with pytest.raises(LayoutV2Error):
        layout_video_plan(plan)

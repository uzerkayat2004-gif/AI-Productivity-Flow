"""Trusted 2D Scene Compiler V2 contract tests.

The fixtures are parsed, semantic V2 plans: no test feeds model-authored
markup, geometry, styles, or renderer configuration to the compiler.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as element_tree
from copy import deepcopy
from typing import Any

import pytest

from voice_flow.video_flow_engine.scene_compiler_v2 import (
    CompiledVisualV2,
    SceneCompilerV2Error,
    compile_visual_plan_v2,
)
from voice_flow.video_flow_engine.visual_plan_v2 import (
    VisualPlanV2Error,
    parse_video_visual_plan_v2,
)


CUSTOM_VOICE = "elevenlabs/21m00Tcm4TlvDq8ikWAM"
STORYBOARD = {
    "topic": "Mechanisms across mathematics and biology",
    "sections": [
        {
            "id": "residual-storyboard",
            "title": "Residual connection",
            "lecture_lines": ["Input travels through F.", "A shortcut preserves the original signal."],
        },
        {
            "id": "pythagoras-storyboard",
            "title": "Pythagorean construction",
            "lecture_lines": ["Squares grow on each side of the triangle.", "Their areas reveal the equation."],
        },
        {
            "id": "xylem-storyboard",
            "title": "Xylem flow",
            "lecture_lines": ["Evaporation pulls water upward.", "The water column rises from roots to leaves."],
        },
    ],
}


def _scene(
    scene_id: str,
    storyboard_section_id: str,
    learning_goal: str,
    visual_thesis: str,
    visual_mode: str,
    objects: list[dict[str, str]],
    relationships: list[dict[str, str]],
    beats: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "scene_id": scene_id,
        "storyboard_section_id": storyboard_section_id,
        "learning_goal": learning_goal,
        "visual_thesis": visual_thesis,
        "visual_mode": visual_mode,
        "objects": objects,
        "relationships": relationships,
        "beats": beats,
        "continuity": {"carry_forward": []},
    }


def _plan_dict() -> dict[str, Any]:
    return {
        "version": "2.0",
        "design_bible": {
            "visual_character": "technical paper mechanisms",
            "surface_mode": "paper",
            "palette_intent": {
                "dominant": "paper",
                "contrast": "very-high",
                "accent_family": "signal-red",
                "secondary_family": "black",
                "temperature": "neutral",
                "saturation": "selective",
            },
            "typography_character": "technical",
            "shape_language": "diagrammatic",
            "background_character": "paper",
            "motion_character": "technical",
            "transition_character": "fade",
            "camera_character": "focus",
            "caption_integration": "reserved-bottom",
        },
        "scenes": [
            _scene(
                "residual-block",
                "residual-storyboard",
                "Explain a residual shortcut.",
                "An input takes transform and bypass branches before one merge.",
                "mechanism",
                [
                    {"id": "input_x", "type": "node", "label": "Input & signal", "role": "primary", "region": "left"},
                    {"id": "transform_f", "type": "operator", "label": "F(x)", "role": "secondary", "region": "center"},
                    {"id": "shortcut", "type": "curve", "label": "Shortcut", "role": "support", "region": "top"},
                    {"id": "sum", "type": "operator", "label": "+", "role": "primary", "region": "right"},
                ],
                [
                    {"source": "input_x", "target": "transform_f", "kind": "flows_to"},
                    {"source": "input_x", "target": "shortcut", "kind": "bypasses"},
                    {"source": "transform_f", "target": "sum", "kind": "merges_into"},
                    {"source": "shortcut", "target": "sum", "kind": "merges_into"},
                ],
                [
                    {"order": 1, "phase": "intro", "action": "create", "object_id": "input_x", "reason": "Start with the signal."},
                    {"order": 2, "phase": "build", "action": "connect", "object_id": "transform_f", "reason": "Build the transform branch."},
                    {"order": 3, "phase": "build", "action": "draw", "object_id": "shortcut", "reason": "Draw the bypass."},
                    {"order": 4, "phase": "resolve", "action": "merge", "object_id": "sum", "reason": "Merge the two paths."},
                ],
            ),
            _scene(
                "pythagoras-construction",
                "pythagoras-storyboard",
                "Show why the Pythagorean relation holds.",
                "Squares build around a triangle and connect their areas.",
                "construction",
                [
                    {"id": "triangle", "type": "shape", "label": "Right triangle", "role": "primary", "region": "center"},
                    {"id": "small_square", "type": "shape", "label": "a²", "role": "secondary", "region": "left"},
                    {"id": "large_square", "type": "shape", "label": "c²", "role": "primary", "region": "right"},
                ],
                [
                    {"source": "triangle", "target": "small_square", "kind": "supports"},
                    {"source": "small_square", "target": "large_square", "kind": "compares_with"},
                ],
                [
                    {"order": 1, "phase": "setup", "action": "create", "object_id": "triangle", "reason": "Build the triangle."},
                    {"order": 2, "phase": "build", "action": "reveal", "object_id": "small_square", "reason": "Add a square."},
                    {"order": 3, "phase": "resolve", "action": "measure", "object_id": "large_square", "reason": "Compare the areas."},
                ],
            ),
            _scene(
                "xylem-flow",
                "xylem-storyboard",
                "Explain transpiration pull.",
                "Water rises from roots to leaves as evaporation creates tension.",
                "mechanism",
                [
                    {"id": "roots", "type": "container", "label": "Roots", "role": "container", "region": "bottom"},
                    {"id": "water_column", "type": "wave", "label": "Water column", "role": "primary", "region": "center"},
                    {"id": "leaf", "type": "shape", "label": "Leaf", "role": "primary", "region": "top"},
                ],
                [
                    {"source": "roots", "target": "water_column", "kind": "feeds"},
                    {"source": "water_column", "target": "leaf", "kind": "flows_to"},
                ],
                [
                    {"order": 1, "phase": "setup", "action": "create", "object_id": "roots", "reason": "Place the roots."},
                    {"order": 2, "phase": "build", "action": "flow", "object_id": "water_column", "reason": "Move water upward."},
                    {"order": 3, "phase": "explain", "action": "highlight", "object_id": "leaf", "reason": "Focus evaporation."},
                ],
            ),
        ],
    }


def _plan() -> Any:
    return parse_video_visual_plan_v2(_plan_dict(), storyboard=STORYBOARD)


def _compile(**kwargs: Any) -> CompiledVisualV2:
    return compile_visual_plan_v2(
        STORYBOARD,
        _plan(),
        title="Semantic Mechanisms",
        mode="full",
        theme={"mode": "light", "accent": "#123456"},
        voice=CUSTOM_VOICE,
        **kwargs,
    )


def test_compiler_preserves_the_existing_narova_envelope_and_request_controls() -> None:
    compiled = _compile()
    production = compiled.production

    assert production["title"] == "Semantic Mechanisms"
    assert production["size"] == "16:9"
    assert production["renderer"] == "hyperframes"
    assert production["voices"]["narrator"] == {
        "backend": "voiceflow",
        "speaker": CUSTOM_VOICE,
        "label": "Narrator",
        "color": production["voices"]["narrator"]["color"],
    }
    assert production["theme"]["mode"] == "light"
    assert production["safeLayout"] is True
    assert production["chrome"] is False
    assert production["captions"] == {"preset": "rise"}
    assert production["timing"]["tempo"] == 1.05
    assert set(production["_files"]) == {"theme.css"}


def test_compiler_emits_one_ordered_scene_per_storyboard_section_with_exact_narration() -> None:
    compiled = _compile()
    scenes = compiled.production["scenes"]

    assert [scene["id"] for scene in scenes] == [
        "residual-block",
        "pythagoras-construction",
        "xylem-flow",
    ]
    assert [scene["vo"][0]["text"] for scene in scenes] == [
        " ".join(section["lecture_lines"]) for section in STORYBOARD["sections"]
    ]


def test_compiler_owns_markup_escapes_labels_and_generates_parseable_safe_svg() -> None:
    compiled = _compile()
    body = compiled.production["scenes"][0]["body"]
    lowered = body.lower()

    assert "Input &amp; signal" in body
    assert "Input & signal" not in body
    assert "<script" not in lowered
    assert "<iframe" not in lowered
    assert "javascript:" not in lowered
    assert "data-cue=" in body
    assert "data-delay=" in body
    assert "data-draw" in body
    assert "<path" in body
    svg = re.search(r"<svg\b[^>]*>.*?</svg>", body, re.DOTALL)
    assert svg is not None
    element_tree.fromstring(svg.group(0))


def test_scene_ir_boxes_are_inside_the_caption_safe_frame() -> None:
    compiled = _compile()
    assert [scene.scene_id for scene in compiled.scene_ir.scenes] == [
        "residual-block",
        "pythagoras-construction",
        "xylem-flow",
    ]

    for scene in compiled.scene_ir.scenes:
        assert scene.objects
        for obj in scene.objects:
            box = obj.box
            assert box.x >= 0 and box.y >= 0
            assert box.width > 0 and box.height > 0
            assert box.x + box.width <= 1920
            assert box.y + box.height <= 880


def test_compiler_outputs_resolved_safe_tokens_and_non_glassy_css() -> None:
    compiled = _compile()
    tokens = compiled.design_tokens.to_dict()
    css = compiled.production["_files"]["theme.css"].lower()

    for token in ("background", "foreground", "accent", "secondary", "surface", "edge"):
        assert re.fullmatch(r"#[0-9a-f]{6}", tokens[token], re.IGNORECASE)
    assert "backdrop-filter" not in css
    assert "infinite" not in css
    assert "linear-gradient" not in css


def test_compilation_and_debug_artifacts_are_deterministic_and_json_serializable() -> None:
    first = _compile()
    second = _compile()

    assert first.production == second.production
    assert first.design_tokens.to_dict() == second.design_tokens.to_dict()
    assert first.to_artifacts() == second.to_artifacts()
    assert set(first.to_artifacts()) == {
        "resolved-design.json",
        "scene-ir/index.json",
        "scene-ir/residual-block.json",
        "scene-ir/pythagoras-construction.json",
        "scene-ir/xylem-flow.json",
    }
    for artifact in first.to_artifacts().values():
        json.dumps(artifact)



@pytest.mark.parametrize(
    "field,value",
    [
        ("svg", "<svg><path /></svg>"),
        ("css", "body { color: red; }"),
        ("three", {"objects": []}),
    ],
)
def test_raw_model_renderer_payloads_are_rejected_before_compilation(field: str, value: Any) -> None:
    payload = _plan_dict()
    payload["scenes"][0][field] = value

    with pytest.raises(VisualPlanV2Error):
        parse_video_visual_plan_v2(payload, storyboard=STORYBOARD)

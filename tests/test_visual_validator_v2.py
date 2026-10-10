from __future__ import annotations

from dataclasses import replace

import pytest

from voice_flow.video_flow_engine.scene_compiler_v2 import compile_visual_plan_v2
from voice_flow.video_flow_engine.scene_ir import Box
from voice_flow.video_flow_engine.visual_plan_v2 import parse_video_visual_plan_v2
from voice_flow.video_flow_engine.visual_validator import VisualValidationV2Error, validate_compiled_visual_v2

STORYBOARD = {"topic": "Signal flow", "sections": [{"id": "signal-flow", "title": "Signal flow", "lecture_lines": ["A signal moves from input through a transform to a result."]}]}


def _compiled():
    plan = parse_video_visual_plan_v2({
        "version": "2.0",
        "design_bible": {
            "visual_character": "technical systems", "surface_mode": "technical",
            "palette_intent": {"dominant": "near-black", "contrast": "very-high", "accent_family": "signal-red", "secondary_family": "hard-white", "temperature": "neutral", "saturation": "selective"},
            "typography_character": "technical", "shape_language": "diagrammatic", "background_character": "grid",
            "motion_character": "technical", "transition_character": "fade", "camera_character": "focus", "caption_integration": "reserved-bottom",
        },
        "scenes": [{
            "scene_id": "signal-flow-scene", "storyboard_section_id": "signal-flow",
            "learning_goal": "Explain signal flow.", "visual_thesis": "Input connects to transform before reaching the result.", "visual_mode": "mechanism",
            "objects": [
                {"id": "input", "type": "node", "label": "Input", "role": "primary", "region": "left"},
                {"id": "transform", "type": "operator", "label": "Transform", "role": "secondary", "region": "center"},
                {"id": "result", "type": "node", "label": "Result", "role": "primary", "region": "right"},
            ],
            "relationships": [{"source": "input", "target": "transform", "kind": "flows_to"}, {"source": "transform", "target": "result", "kind": "connects_to"}],
            "beats": [
                {"order": 1, "phase": "intro", "action": "create", "object_id": "input", "reason": "Show the input."},
                {"order": 2, "phase": "build", "action": "connect", "object_id": "transform", "reason": "Show the transform."},
                {"order": 3, "phase": "resolve", "action": "reveal", "object_id": "result", "reason": "Show the result."},
            ],
            "continuity": {"carry_forward": []},
        }],
    }, storyboard=STORYBOARD)
    return compile_visual_plan_v2(STORYBOARD, plan)


def _production_with(compiled, **scene_updates):
    production = dict(compiled.production)
    scene = dict(production["scenes"][0])
    scene.update(scene_updates)
    production["scenes"] = [scene]
    return replace(compiled, production=production)


def _codes(exc: pytest.ExceptionInfo[VisualValidationV2Error]) -> set[str]:
    return {item.code for item in exc.value.report.findings}


def test_valid_2d_compilation_reports_deterministic_metrics() -> None:
    first = validate_compiled_visual_v2(_compiled())
    second = validate_compiled_visual_v2(_compiled())
    assert first.valid is True
    assert first.findings == ()
    assert first.to_dict() == second.to_dict()
    assert first.metrics["scene_count"] == 1
    assert first.metrics["local_object_count"] == 3


@pytest.mark.parametrize("box", [Box(-1, 20, 120, 80), Box(20, 900, 120, 80)])
def test_offscreen_or_caption_boxes_fail(box: Box) -> None:
    compiled = _compiled()
    scene = compiled.scene_ir.scenes[0]
    object0 = replace(scene.objects[0], box=box)
    video_ir = replace(compiled.scene_ir, scenes=(replace(scene, objects=(object0, *scene.objects[1:])),))
    with pytest.raises(VisualValidationV2Error) as exc:
        validate_compiled_visual_v2(replace(compiled, scene_ir=video_ir))
    assert "invalid_box" in _codes(exc)


def test_local_overlap_fails() -> None:
    compiled = _compiled()
    scene = compiled.scene_ir.scenes[0]
    object1 = replace(scene.objects[1], box=scene.objects[0].box)
    video_ir = replace(compiled.scene_ir, scenes=(replace(scene, objects=(scene.objects[0], object1, scene.objects[2])),))
    with pytest.raises(VisualValidationV2Error) as exc:
        validate_compiled_visual_v2(replace(compiled, scene_ir=video_ir))
    assert "local_overlap" in _codes(exc)


def test_low_contrast_fails() -> None:
    compiled = _compiled()
    tokens = replace(compiled.design_tokens, foreground="#111111", background="#101010", surface="#101010")
    with pytest.raises(VisualValidationV2Error) as exc:
        validate_compiled_visual_v2(replace(compiled, design_tokens=tokens))
    assert {"low_background_contrast", "low_surface_contrast"} <= _codes(exc)


def test_unsafe_markup_and_empty_body_or_narration_fail() -> None:
    with pytest.raises(VisualValidationV2Error) as unsafe:
        validate_compiled_visual_v2(_production_with(_compiled(), body='<script src="https://bad.example/x.js"></script>'))
    assert "unsafe_markup" in _codes(unsafe)
    with pytest.raises(VisualValidationV2Error) as empty:
        validate_compiled_visual_v2(_production_with(_compiled(), body="", vo=[{"who": "narrator", "text": ""}]))
    assert {"empty_body", "empty_narration"} <= _codes(empty)


@pytest.mark.parametrize(("updates", "expected"), [
    ({"transition": "spin"}, "invalid_transition"),
    ({"body": '<svg><path d="not a valid path!"/></svg>'}, "invalid_svg_path"),
    ({"body": '<div data-delay="NaN"></div>'}, "invalid_animation_number"),
    ({"three": {"objects": [{"type": "arbitrary"}]}}, "invalid_three_object"),
])
def test_invalid_transition_svg_animation_and_three_config_fail(updates, expected: str) -> None:
    with pytest.raises(VisualValidationV2Error) as exc:
        validate_compiled_visual_v2(_production_with(_compiled(), **updates))
    assert expected in _codes(exc)

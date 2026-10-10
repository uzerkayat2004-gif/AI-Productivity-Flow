"""Geometric primitive-form tests for Video Flow Visual V2."""
from __future__ import annotations

from typing import Any

import pytest

from voice_flow.video_flow_engine.scene_compiler_v2 import compile_visual_plan_v2
from voice_flow.video_flow_engine.visual_director_v2 import _build_prompt
from voice_flow.video_flow_engine.visual_plan_v2 import OBJECT_FORMS, VisualPlanV2Error, parse_video_visual_plan_v2

EXPECTED_FORMS = {"auto", "circle", "ellipse", "rectangle", "square", "triangle", "line", "arc", "curve", "bar", "area", "marker"}


def _storyboard() -> dict[str, Any]:
    return {"topic": "Semantic visual forms", "sections": [{"id": "form-section", "title": "A form", "lecture_lines": ["The form appears."]}]}


def _payload(form: str, *, object_type: str = "shape", label: str = "Input & signal") -> dict[str, Any]:
    return {
        "version": "2.0",
        "design_bible": {
            "visual_character": "technical teaching form", "surface_mode": "paper",
            "palette_intent": {"dominant": "paper", "contrast": "very-high", "accent_family": "signal-red", "secondary_family": "black", "temperature": "neutral", "saturation": "selective"},
            "typography_character": "technical", "shape_language": "diagrammatic", "background_character": "paper",
            "motion_character": "technical", "transition_character": "fade", "camera_character": "focus", "caption_integration": "reserved-bottom",
        },
        "scenes": [{
            "scene_id": "form-scene", "storyboard_section_id": "form-section",
            "learning_goal": "Show a semantic visual form.", "visual_thesis": "A form appears to support the explanation.", "visual_mode": "diagram",
            "objects": [{"id": "subject", "type": object_type, "form": form, "label": label, "role": "primary", "region": "center"}],
            "relationships": [],
            "beats": [{"order": 1, "phase": "intro", "action": "create", "object_id": "subject", "reason": "Reveal the form."}],
            "continuity": {"carry_forward": []},
        }],
    }


def _plan(form: str, *, object_type: str = "shape", label: str = "Input & signal"):
    return parse_video_visual_plan_v2(_payload(form, object_type=object_type, label=label), storyboard=_storyboard())


def test_object_form_enum_is_exactly_the_compact_geometric_vocabulary() -> None:
    assert OBJECT_FORMS == EXPECTED_FORMS


@pytest.mark.parametrize("object_type,form", [
    ("node", "auto"), ("node", "circle"), ("shape", "triangle"), ("shape", "square"),
    ("shape", "area"), ("line", "line"), ("line", "curve"), ("wave", "arc"),
    ("axis", "line"), ("chart", "bar"), ("chart", "area"), ("label", "auto"),
    ("operator", "auto"), ("mesh", "rectangle"), ("container", "marker"),
])
def test_supported_object_type_and_form_pairs_are_accepted(object_type: str, form: str) -> None:
    plan = _plan(form, object_type=object_type)
    assert plan.scenes[0].objects[0].form == form
    assert compile_visual_plan_v2(_storyboard(), plan).scene_ir.scenes[0].objects[0].form == form


@pytest.mark.parametrize("object_type,form", [
    ("node", "bar"), ("shape", "bar"), ("chart", "curve"), ("line", "area"),
    ("operator", "circle"), ("label", "marker"), ("particle_group", "circle"), ("mesh", "curve"),
])
def test_incompatible_object_type_and_form_pairs_are_rejected(object_type: str, form: str) -> None:
    with pytest.raises(VisualPlanV2Error):
        _plan(form, object_type=object_type)


@pytest.mark.parametrize("form", ["octagon", "triangle x=437", "M0 0 L100 100", "<svg><path/></svg>"])
def test_unknown_coordinate_and_raw_svg_forms_are_rejected(form: str) -> None:
    with pytest.raises(VisualPlanV2Error):
        _plan(form)


@pytest.mark.parametrize("object_type,form,required_markup", [
    ("shape", "triangle", "v2-form-triangle"), ("shape", "circle", "v2-form-circle"),
    ("shape", "ellipse", "v2-form-ellipse"), ("shape", "area", "v2-form-area"),
    ("shape", "marker", "v2-form-marker"), ("line", "curve", "<path"),
    ("chart", "bar", "data-grow"), ("chart", "area", "v2-chart-area"),
])
def test_trusted_compiler_emits_distinct_form_markup(object_type: str, form: str, required_markup: str) -> None:
    body = compile_visual_plan_v2(_storyboard(), _plan(form, object_type=object_type)).production["scenes"][0]["body"]
    assert required_markup in body
    assert "<script" not in body.lower()
    assert "javascript:" not in body.lower()


def test_different_forms_compile_to_different_bodies_and_escape_labels() -> None:
    triangle = compile_visual_plan_v2(_storyboard(), _plan("triangle"))
    rectangle = compile_visual_plan_v2(_storyboard(), _plan("rectangle"))
    assert triangle.production["scenes"][0]["body"] != rectangle.production["scenes"][0]["body"]
    assert "Input &amp; signal" in triangle.production["scenes"][0]["body"]
    assert "Input & signal" not in triangle.production["scenes"][0]["body"]


def test_form_aware_mesh_compiles_only_to_whitelisted_declarative_primitive() -> None:
    compiled = compile_visual_plan_v2(_storyboard(), _plan("triangle", object_type="mesh"))
    objects = compiled.production["scenes"][0]["three"]["objects"]
    assert objects and {item["type"] for item in objects} <= {"cube", "sphere", "cylinder", "plane", "torus", "cone", "icosahedron", "particles"}
    assert all("script" not in str(item).lower() and "javascript" not in str(item).lower() for item in objects)


def _benchmark_plan(objects: list[dict[str, str]]) -> Any:
    payload = _payload("auto")
    payload["scenes"][0]["objects"] = objects
    payload["scenes"][0]["beats"] = [{"order": index, "phase": "build", "action": "reveal", "object_id": item["id"], "reason": "Build the primitive."} for index, item in enumerate(objects, start=1)]
    return parse_video_visual_plan_v2(payload, storyboard=_storyboard())


@pytest.mark.parametrize("objects", [
    [{"id": "triangle", "type": "shape", "form": "triangle", "label": "Triangle", "role": "primary", "region": "center"}, {"id": "square", "type": "shape", "form": "square", "label": "Square", "role": "secondary", "region": "left"}, {"id": "area", "type": "shape", "form": "area", "label": "Area", "role": "annotation", "region": "right"}],
    [{"id": "input", "type": "node", "form": "auto", "label": "Input", "role": "primary", "region": "left"}, {"id": "shortcut", "type": "line", "form": "curve", "label": "Shortcut", "role": "support", "region": "top"}, {"id": "sum", "type": "operator", "form": "auto", "label": "+", "role": "primary", "region": "right"}],
    [{"id": "column", "type": "wave", "form": "curve", "label": "Water", "role": "primary", "region": "center"}, {"id": "stem", "type": "line", "form": "line", "label": "Stem", "role": "support", "region": "center"}, {"id": "leaf", "type": "shape", "form": "ellipse", "label": "Leaf", "role": "primary", "region": "top"}, {"id": "evaporation", "type": "shape", "form": "marker", "label": "Evaporation", "role": "annotation", "region": "top-third"}],
    [{"id": "bars", "type": "chart", "form": "bar", "label": "Capacity", "role": "primary", "region": "left"}, {"id": "area", "type": "chart", "form": "area", "label": "Demand", "role": "secondary", "region": "right"}],
], ids=["pythagoras", "resnet", "xylem", "data"])
def test_benchmark_topics_are_composable_from_safe_primitives(objects: list[dict[str, str]]) -> None:
    plan = _benchmark_plan(objects)
    assert [item.form for item in plan.scenes[0].objects] == [item["form"] for item in objects]


def test_director_contract_prompt_lists_form_enum() -> None:
    prompt = _build_prompt(_storyboard(), visual_direction="", theme=None, recent_signatures=[])
    for form in EXPECTED_FORMS:
        assert form in prompt

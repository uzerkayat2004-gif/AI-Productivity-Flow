"""Contract tests for the Video Flow semantic visual plan V2.

These tests deliberately use static in-memory plans.  They establish the
untrusted-model-data boundary before the director, renderer, or filesystem are
wired into the V2 path.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from voice_flow.video_flow_engine.visual_plan_v2 import (
    V2_PLAN_VERSION,
    VisualPlanV2Error,
    parse_video_visual_plan_v2,
)


STORYBOARD = {
    "sections": [
        {"id": "residual-storyboard", "title": "Residual connection"},
        {"id": "result-storyboard", "title": "Why shortcuts help"},
    ]
}


def _residual_scene() -> dict:
    return {
        "scene_id": "residual-block",
        "storyboard_section_id": "residual-storyboard",
        "learning_goal": "Explain how the shortcut preserves the input signal.",
        "visual_thesis": "The input travels through a transform and a bypass before both paths merge.",
        "visual_mode": "mechanism",
        "objects": [
            {"id": "input_x", "type": "node", "label": "Input x", "role": "primary", "region": "left"},
            {"id": "transform_f", "type": "operator", "label": "F(x)", "role": "secondary", "region": "center"},
            {"id": "shortcut", "type": "curve", "label": "Shortcut", "role": "support", "region": "top"},
            {"id": "sum", "type": "operator", "label": "+", "role": "primary", "region": "right"},
        ],
        "relationships": [
            {"source": "input_x", "target": "transform_f", "kind": "flows_to"},
            {"source": "input_x", "target": "shortcut", "kind": "bypasses"},
            {"source": "transform_f", "target": "sum", "kind": "merges_into"},
            {"source": "shortcut", "target": "sum", "kind": "merges_into"},
        ],
        "beats": [
            {"order": 1, "phase": "intro", "action": "create", "object_id": "input_x", "reason": "Show the input signal."},
            {"order": 2, "phase": "build", "action": "connect", "object_id": "transform_f", "reason": "Start the transform branch."},
            {"order": 3, "phase": "build", "action": "draw", "object_id": "shortcut", "reason": "Reveal the bypass path."},
            {"order": 4, "phase": "resolve", "action": "merge", "object_id": "sum", "reason": "Show both signals combining."},
        ],
        "continuity": {"carry_forward": []},
    }


def _result_scene() -> dict:
    return {
        "scene_id": "residual-result",
        "storyboard_section_id": "result-storyboard",
        "learning_goal": "Show the residual result.",
        "visual_thesis": "The merged result is expressed as F(x) + x.",
        "visual_mode": "equation",
        "objects": [
            {"id": "result_equation", "type": "equation", "label": "F(x) + x", "role": "primary", "region": "center"},
        ],
        "relationships": [],
        "beats": [
            {"order": 1, "phase": "conclude", "action": "reveal", "object_id": "result_equation", "reason": "Name the merged result."},
        ],
        "continuity": {"carry_forward": ["sum"]},
    }


def valid_plan() -> dict:
    return {
        "version": V2_PLAN_VERSION,
        "design_bible": {
            "visual_character": "industrial technical systems",
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
        },
        "scenes": [_residual_scene(), _result_scene()],
    }


def _parse(payload: dict):
    return parse_video_visual_plan_v2(payload, storyboard=STORYBOARD)


def _reject(mutator) -> None:
    payload = valid_plan()
    mutator(payload)
    with pytest.raises(VisualPlanV2Error):
        _parse(payload)


def test_valid_residual_plan_is_accepted_and_to_dict_is_deterministic() -> None:
    first = _parse(valid_plan())
    second = _parse(valid_plan())

    assert first.to_dict() == second.to_dict()
    assert first.to_dict()["version"] == V2_PLAN_VERSION
    assert [scene["scene_id"] for scene in first.to_dict()["scenes"]] == [
        "residual-block",
        "residual-result",
    ]
    assert first.to_dict()["scenes"][1]["continuity"] == {"carry_forward": ["sum"]}


def test_invalid_version_is_rejected() -> None:
    _reject(lambda plan: plan.__setitem__("version", "v1"))


def test_duplicate_object_id_is_rejected_within_a_scene() -> None:
    _reject(lambda plan: plan["scenes"][0]["objects"].append(deepcopy(plan["scenes"][0]["objects"][0])))


def test_relationship_target_must_exist_in_its_scene() -> None:
    _reject(lambda plan: plan["scenes"][0]["relationships"][0].__setitem__("target", "missing-node"))


def test_unsupported_animation_action_is_rejected() -> None:
    _reject(lambda plan: plan["scenes"][0]["beats"][0].__setitem__("action", "teleport"))


def test_unsupported_surface_mode_is_rejected() -> None:
    _reject(lambda plan: plan["design_bible"].__setitem__("surface_mode", "holographic-candy"))


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "<ScRiPt>alert(1)</ScRiPt>",
        "JaVaScRiPt:alert(1)",
        "ImPoRt os",
        "SuBpRoCeSs.run(['bad'])",
        "EXEC('bad')",
        "FuNcTiOn('bad')",
        "<img ONERROR=alert(1)>",
    ],
)
def test_executable_looking_content_is_rejected_case_insensitively(unsafe_value: str) -> None:
    _reject(lambda plan: plan["scenes"][0].__setitem__("visual_thesis", unsafe_value))


@pytest.mark.parametrize(
    "location,key,value",
    [
        ("plan", "unexpected", "value"),
        ("scene", "html", "<div>model-authored</div>"),
        ("scene", "raw_code", "const pwned = true"),
        ("scene", "renderer", "hyperframes"),
        ("object", "x", 437),
        ("object", "coordinates", [437, 291]),
        ("object", "svg_path", "M0 0 L1 1"),
    ],
)
def test_unknown_coordinate_and_raw_code_keys_are_rejected(location: str, key: str, value: object) -> None:
    def mutate(plan: dict) -> None:
        targets = {
            "plan": plan,
            "scene": plan["scenes"][0],
            "object": plan["scenes"][0]["objects"][0],
        }
        targets[location][key] = value

    _reject(mutate)


def test_first_scene_cannot_carry_forward_its_own_object() -> None:
    _reject(lambda plan: plan["scenes"][0]["continuity"].__setitem__("carry_forward", ["input_x"]))


def test_carried_object_id_cannot_be_redeclared_locally() -> None:
    payload = valid_plan()
    payload["scenes"][1]["objects"].append(
        {"id": "sum", "type": "operator", "label": "+", "role": "secondary", "region": "left"}
    )
    with pytest.raises(VisualPlanV2Error):
        _parse(payload)


def test_duplicate_relationship_is_rejected() -> None:
    _reject(lambda plan: plan["scenes"][0]["relationships"].append(deepcopy(plan["scenes"][0]["relationships"][0])))

def test_duplicate_scene_id_is_rejected() -> None:
    _reject(lambda plan: plan["scenes"][1].__setitem__("scene_id", "residual-block"))


@pytest.mark.parametrize("orders", [[1, 3, 4, 5], [1, 2, 2, 4]], ids=["noncontiguous", "duplicate"])
def test_beat_orders_must_be_unique_and_contiguous(orders: list[int]) -> None:
    def mutate(plan: dict) -> None:
        for beat, order in zip(plan["scenes"][0]["beats"], orders):
            beat["order"] = order

    _reject(mutate)


def test_beat_object_reference_must_exist_in_its_scene() -> None:
    _reject(lambda plan: plan["scenes"][0]["beats"][0].__setitem__("object_id", "missing-node"))

def test_malformed_continuity_is_rejected() -> None:
    _reject(lambda plan: plan["scenes"][1].__setitem__("continuity", ["sum"]))


def test_continuity_can_only_reference_an_object_from_an_earlier_scene() -> None:
    _reject(lambda plan: plan["scenes"][1]["continuity"].__setitem__("carry_forward", ["result_equation"]))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda plan: plan["scenes"][0].__setitem__("storyboard_section_id", "unknown-storyboard"),
        lambda plan: plan["scenes"][0].pop("storyboard_section_id"),
        lambda plan: plan["scenes"][1].__setitem__("storyboard_section_id", "residual-storyboard"),
    ],
    ids=["unknown", "missing", "duplicate"],
)
def test_storyboard_scene_references_must_be_known_present_and_unique(mutate) -> None:
    _reject(mutate)


def test_storyboard_sections_without_ids_use_deterministic_fallback_ids() -> None:
    storyboard = {"sections": [{"title": "One"}, {"title": "Two"}]}
    payload = valid_plan()
    payload["scenes"][0]["storyboard_section_id"] = "section_1"
    payload["scenes"][1]["storyboard_section_id"] = "section_2"
    assert parse_video_visual_plan_v2(payload, storyboard=storyboard).scenes[1].storyboard_section_id == "section_2"

def test_scene_order_must_match_the_storyboard_order() -> None:
    def mutate(plan: dict) -> None:
        plan["scenes"].reverse()
        plan["scenes"][0]["continuity"] = {"carry_forward": []}

    _reject(mutate)

def test_label_limit_is_enforced() -> None:
    _reject(lambda plan: plan["scenes"][0]["objects"][0].__setitem__("label", "x" * 10_001))


@pytest.mark.parametrize("equation", ["x = 2", "y = mx + b", "a² + b² = c²", "A => B"])
def test_equation_labels_are_inert_semantic_text(equation: str) -> None:
    payload = valid_plan()
    payload["scenes"][1]["objects"][0]["label"] = equation
    assert _parse(payload).scenes[1].objects[0].label == equation


def test_label_cannot_exceed_seven_words() -> None:
    _reject(lambda plan: plan["scenes"][0]["objects"][0].__setitem__("label", "one two three four five six seven eight"))

@pytest.mark.parametrize("field", ["learning_goal", "visual_thesis"])
def test_scene_text_limits_are_enforced(field: str) -> None:
    _reject(lambda plan: plan["scenes"][0].__setitem__(field, "x" * 10_001))


def test_object_limit_is_enforced() -> None:
    def mutate(plan: dict) -> None:
        plan["scenes"][0]["objects"] = [
            {"id": f"node_{index}", "type": "node", "label": "Node", "role": "secondary", "region": "center"}
            for index in range(17)
        ]
        plan["scenes"][0]["relationships"] = []
        plan["scenes"][0]["beats"] = [
            {"order": 1, "phase": "intro", "action": "reveal", "object_id": "node_0", "reason": "Focus attention."}
        ]

    _reject(mutate)


def test_beat_limit_is_enforced() -> None:
    def mutate(plan: dict) -> None:
        plan["scenes"][0]["beats"] = [
            {"order": index + 1, "phase": "explain", "action": "reveal", "object_id": "input_x", "reason": "Focus attention."}
            for index in range(1_000)
        ]

    _reject(mutate)


@pytest.mark.parametrize("unsafe_value", ["#A1B2C3", "rgb(1, 2, 3)", "C:\\temp\\scene", "../escape"])
def test_raw_colours_and_paths_are_rejected(unsafe_value: str) -> None:
    _reject(lambda plan: plan["scenes"][0].__setitem__("visual_thesis", unsafe_value))

@pytest.mark.parametrize(
    "unsafe_value",
    ["java\u2060script :alert(1)", "onerror\n=alert(1)", "import\nos", "e\u200bval (1)", "< script >"],
)
def test_unicode_and_whitespace_executable_smuggling_is_rejected(unsafe_value: str) -> None:
    _reject(lambda plan: plan["scenes"][0].__setitem__("visual_thesis", unsafe_value))

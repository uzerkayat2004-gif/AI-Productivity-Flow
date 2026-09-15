"""Regression tests for the Visual V2.1 fallback review fixes.

Covers: validator executable-code gaps, render crashes on edge inputs,
deterministic cue assignment, bounded sampling, and UTF-8 handling.
"""

from __future__ import annotations

import pytest

from voice_flow.video_flow_engine import scene_author as scene_author_module
from voice_flow.video_flow_engine import visual_validator as visual_validator_module
from voice_flow.video_flow_engine.creative_director import DirectorError, direct
from voice_flow.video_flow_engine.scene_author import author_scene, resolve_design
from voice_flow.video_flow_engine.scene_evaluator_v21 import check_cue_spread, evaluate_scene_v21
from voice_flow.video_flow_engine.scene_state import (
    ObjectState,
    SceneState,
    evaluate_event,
    event_qa_metrics,
    sample_event,
)
from voice_flow.video_flow_engine.visual_validator import (
    VisualValidationV21Error,
    validate_compiled_visual_program_v21,
)
from voice_flow.video_flow_engine.scene_compiler_v2 import (
    CompiledVisualProgramV21,
    compile_visual_program_v21,
)
from voice_flow.video_flow_engine.visual_program_v21 import parse_video_visual_program_v21


class _Program:
    def __init__(self, scene_id="s1"):
        self.scene_id = scene_id
        self.subjects = []
        self.relationships = []


def _design():
    return resolve_design({"brief": {}}, None)


# --- Security: validator must flag executable markup variants ---


@pytest.mark.parametrize(
    "body",
    [
        '<object data="x"></object>',
        '<embed src="x">',
        '<form action="x"><input></form>',
        "<IMG SRC=x ONERROR=alert(1)>",
        '<svg><path d="M0 0 L10 10" onmouseover = "alert(1)"/></svg>',
    ],
)
def test_validate_markup_flags_embedded_executable_tags(body):
    findings: list = []
    visual_validator_module._validate_markup(body, "s1", findings)
    assert any(item.code == "unsafe_markup" for item in findings)


def test_validate_three_rejects_non_hex_light_colours():
    findings: list = []
    visual_validator_module._validate_three(
        {
            "camera": {"position": [0, 0, 5], "lookAt": [0, 0, 0], "fov": 50, "near": 0.1, "far": 40},
            "lights": [{"type": "directional", "color": "javascript:alert(1)", "intensity": 1}],
        },
        "s1",
        findings,
    )
    assert any(item.code == "invalid_three_lights" for item in findings)


# --- Reliability: edge inputs must not crash the render path ---


def test_author_counter_stats_survives_garbage_counts():
    design = _design()
    scene = author_scene(
        {"id": "s1", "lecture_lines": ["hello"]},
        {"treatment": "counter-stats", "title_label": "T", "labels": ["a"], "count_to": "lots",
         "count_suffix": "%", "transition": "fade"},
        design,
        1,
    )
    assert 'data-count="95"' in scene["body"]


def test_author_scale_comparison_survives_garbage_counts():
    scene = author_scene(
        {"id": "s1", "lecture_lines": ["hello"]},
        {"treatment": "scale-comparison", "title_label": "T", "labels": ["a"], "count_to": "big"},
        _design(),
        1,
    )
    assert "<svg" in scene["body"]


def test_direct_rejects_non_dict_storyboard():
    with pytest.raises(DirectorError):
        direct("not a dict", None)


def test_evaluator_survives_non_mapping_scene_and_body():
    result = evaluate_scene_v21(_Program(), "notadict")  # type: ignore[arg-type]
    assert result.cue_spread == 0.0
    result = evaluate_scene_v21(_Program(), {"body": 123})  # type: ignore[dict-item]
    assert result.cue_spread == 0.0
    assert check_cue_spread(None) == (0.0, 0, 0, False)  # type: ignore[arg-type]


def test_sample_event_bounds_hostile_counts():
    state = SceneState(objects={"a": ObjectState(id="a")})
    # Hostile counts clamp to the bounded range instead of allocating memory.
    assert len(sample_event(state, {"type": "EMPHASIZE", "subject": "a"}, samples=10**9)) == 64  # type: ignore[arg-type]
    # Bounded QA clamps hostile counts instead of allocating unbounded memory.
    metrics = event_qa_metrics(
        state, {"type": "EMPHASIZE", "subject": "a"}, samples=10**9  # type: ignore[arg-type]
    )
    assert metrics.sample_count == 64


def test_single_eval_matches_sampled_eval():
    state = SceneState(
        objects={"o0": ObjectState(id="o0", position=(0.0, 0.0, 0.0))}
    )
    event = {"type": "TRANSFER", "carrier": "o0", "source": [0, 0, 0], "destination": [1, 0, 0]}
    single = evaluate_event(state, event, 1.0)
    sampled = sample_event(state, event, samples=5)[-1]
    assert single.object("o0").position == sampled.object("o0").position


def test_validator_rejects_malformed_motion_qa_entries():
    compiled = _compiled_with_motion_qa(["not-an-object"])
    with pytest.raises(VisualValidationV21Error) as excinfo:
        validate_compiled_visual_program_v21(compiled)
    assert any(item.code == "invalid_motion_qa" for item in excinfo.value.report.findings)


def test_validator_rejects_non_numeric_radius_error():
    compiled = _compiled_with_motion_qa(
        [{"event_type": "TRANSFER", "observed": True, "path_radius_error": "bogus",
          "event_id": "e", "scene_id": "s"}]
    )
    with pytest.raises(VisualValidationV21Error) as excinfo:
        validate_compiled_visual_program_v21(excinfo.value if False else compiled)
    assert any(item.code == "invalid_motion_qa" for item in excinfo.value.report.findings)


def _compiled_with_motion_qa(motion_qa):
    """Compile a minimal real V2.1 program, then swap in hostile motion QA."""
    storyboard = {
        "topic": "t",
        "sections": [{"id": "section", "lecture_lines": ["A subject changes state."]}],
    }
    payload = {
        "version": "2.1",
        "content_intent": "DEMONSTRATE",
        "design_bible": {
            "surface": "paper",
            "palette": {"dominant": "paper", "accent_family": "green"},
            "typography": "editorial",
            "shape_language": "organic",
            "background": "paper",
            "motion": "flowing",
            "caption_safe": "reserved_bottom",
        },
        "scenes": [{
            "scene_id": "scene",
            "storyboard_section_id": "section",
            "purpose": "Show the subject.",
            "representation_strategy": ["DIRECT_DEPICTION"],
            "world": {"description": "A bounded world"},
            "subjects": [{"id": "source", "semantic_name": "source",
                           "structural_family": "network"}],
            "events": [{"id": "grow", "type": "GROW", "subject": "source",
                         "from_state": "initial", "to_state": "expanded",
                         "duration": 1, "narration_anchor": "a0"}],
            "shot": {"mode": "focus", "framing": "hero", "subject": "source"},
            "narration_anchors": [{"id": "a0", "cue_index": 0, "event_ids": ["grow"]}],
        }],
    }
    program = parse_video_visual_program_v21(payload, storyboard=storyboard)
    compiled = compile_visual_program_v21(storyboard, program)
    assert isinstance(compiled, CompiledVisualProgramV21)
    import dataclasses

    return dataclasses.replace(compiled, motion_qa=tuple(motion_qa))


def test_authored_three_scenes_pass_three_validation():
    design = _design()
    for treatment in ("particle-field", "orbit-3d", "cutaway-3d"):
        scene = author_scene(
            {"id": "s1", "lecture_lines": ["hello"]},
            {"treatment": treatment, "title_label": "T", "labels": ["a"], "transition": "fade"},
            design,
            1,
        )
        findings: list = []
        visual_validator_module._validate_three(scene["three"], "s1", findings)
        assert findings == [], (treatment, findings)


def test_utf8_labels_survive_author_and_evaluator():
    design = _design()
    label = "caf\u00e9 \u4e2d\u6587 \U0001f600"
    scene = author_scene(
        {"id": "s1", "lecture_lines": [label]},
        {"treatment": "labeled-diagram", "title_label": label, "labels": [label]},
        design,
        1,
    )
    assert label in scene["body"]
    spread, _, _, _ = check_cue_spread(scene["body"])
    assert spread >= 0.0

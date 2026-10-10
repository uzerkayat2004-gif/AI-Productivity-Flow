from __future__ import annotations

from dataclasses import replace

import pytest

from voice_flow.video_flow_engine.scene_compiler_v2 import compile_visual_program_v21
from voice_flow.video_flow_engine.visual_validator import VisualValidationV21Error, validate_compiled_visual_program_v21
from voice_flow.video_flow_engine.visual_program_v21 import parse_video_visual_program_v21


def _compiled():
    storyboard = {"topic": "Growth", "sections": [{"id": "s", "lecture_lines": ["A bud grows."]}]}
    payload = {"version": "2.1", "content_intent": "DEMONSTRATE", "design_bible": {"surface": "paper", "palette": {"dominant": "paper", "accent_family": "green"}, "typography": "editorial", "shape_language": "organic", "background": "paper", "motion": "flowing", "caption_safe": "reserved_bottom"}, "scenes": [{"scene_id": "scene", "storyboard_section_id": "s", "purpose": "Show growth", "representation_strategy": ["DIRECT_DEPICTION", "STATE_EVOLUTION"], "world": {"description": "garden"}, "subjects": [{"id": "plant", "semantic_name": "apple tree", "structural_family": "organic_branching"}], "relationships": [], "initial_state": {"objects": {"plant": {}}}, "events": [{"id": "grow", "type": "GROW", "subject": "plant", "from_state": "bud", "to_state": "flower", "duration": 2}], "shot": {"mode": "focus", "framing": "hero", "subject": "plant"}}]}
    return compile_visual_program_v21(storyboard, parse_video_visual_program_v21(payload, storyboard=storyboard))


def test_gate_b_accepts_safe_geometry_local_contrast_and_motion():
    report = validate_compiled_visual_program_v21(_compiled())
    assert report.valid
    assert report.metrics["local_object_count"] == 1


def test_gate_b_rejects_low_local_contrast():
    compiled = _compiled()
    tokens = replace(compiled.design_tokens, foreground="#111111", background="#101010", surface="#101010")
    with pytest.raises(VisualValidationV21Error) as exc:
        validate_compiled_visual_program_v21(replace(compiled, design_tokens=tokens))
    assert "local_contrast" in {finding.code for finding in exc.value.report.findings}


def test_gate_b_rejects_unsafe_group_children():
    compiled = _compiled()
    production = dict(compiled.production)
    scene = dict(production["scenes"][0])
    scene["three"] = {"camera": {"position": [0, 0, 4], "lookAt": [0, 0, 0], "fov": 48, "near": 0.1, "far": 40}, "objects": [{"type": "group", "children": [{"type": "cube", "modelMarkup": "<script>bad</script>"}]}]}
    production["scenes"] = [scene]
    with pytest.raises(VisualValidationV21Error) as exc:
        validate_compiled_visual_program_v21(replace(compiled, production=production))
    assert "invalid_three_object" in {finding.code for finding in exc.value.report.findings}

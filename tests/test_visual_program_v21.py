from __future__ import annotations

from copy import deepcopy
import json

import pytest

from voice_flow.video_flow_engine.visual_program_v21 import (
    VisualProgramV21Error,
    parse_video_visual_program_v21,
)


def _program() -> dict:
    return {
        "version": "2.1",
        "content_intent": "DEMONSTRATE",
        "design_bible": {
            "surface": "paper",
            "palette": {"dominant": "paper", "accent_family": "green", "contrast": "high"},
            "typography": "technical",
            "shape_language": "organic",
            "background": "negative-space",
            "motion": "flowing",
            "caption_safe": "reserved-bottom",
            "direction": "botanical field illustration",
        },
        "scenes": [
            {
                "scene_id": "growth",
                "storyboard_section_id": "growth",
                "purpose": "Show a plant developing from bud to fruit.",
                "representation_strategy": ["DIRECT_DEPICTION", "STATE_EVOLUTION"],
                "world": {"description": "A small garden", "setting": "morning", "scale": "plant-scale"},
                "subjects": [
                    {
                        "id": "plant",
                        "semantic_name": "apple tree",
                        "structural_family": "organic_branching",
                        "parts": [{"id": "stem", "semantic_name": "stem", "state": {"stage": "young"}}],
                        "state": {"stage": "bud", "visible": True},
                        "render_strategy": "procedural",
                    },
                    {"id": "sun", "semantic_name": "sun", "structural_family": "celestial_body", "state": {"visible": True}},
                ],
                "relationships": [{"source": "sun", "target": "plant", "kind": "supports"}],
                "initial_state": {"objects": {"plant": {"stage": "bud"}, "sun": {"visible": True}}},
                "events": [
                    {"id": "grow-1", "type": "GROW", "subject": "plant", "from_state": "bud", "to_state": "flower", "duration": 2, "narration_anchor": "line-1"},
                    {"id": "transfer-1", "type": "TRANSFER", "source": "sun", "destination": "plant", "carrier": "sun", "duration": 1},
                ],
                "shot": {"mode": "focus", "subject": "plant", "framing": "hero"},
                "narration_anchors": [{"id": "line-1", "cue_index": 0, "event_ids": ["grow-1"]}],
                "data_series": [{"id": "growth-data", "values": [1, 2, 3], "categories": ["bud", "flower", "fruit"]}],
                "continuity": {"carry_forward": []},
            }
        ],
        "duration_seconds": 8,
    }


def test_parser_builds_immutable_semantic_program_and_one_to_one_storyboard_mapping() -> None:
    payload = _program()
    parsed = parse_video_visual_program_v21(payload, storyboard={"sections": [{"id": "growth"}]})
    assert parsed.version == "2.1"
    assert parsed.content_intent == "DEMONSTRATE"
    assert parsed.scenes[0].representation == ("DIRECT_DEPICTION", "STATE_EVOLUTION")
    assert parsed.scenes[0].subjects[0].parts[0].id == "stem"
    assert parsed.scenes[0].events[0].event_type == "GROW"
    assert parsed.scenes[0].events[1].type == "TRANSFER"
    assert parsed.storyboard_mapping == {"growth": "growth"}
    assert parsed.scenes[0].shot.focus_subject == "plant"
    assert json.loads(json.dumps(parsed.to_dict()))["version"] == "2.1"


def test_parser_rejects_unsupported_fields_and_dead_renderer_payloads() -> None:
    payload = _program()
    payload["design_bible"]["camera_character"] = "orbit"
    with pytest.raises(VisualProgramV21Error):
        parse_video_visual_program_v21(payload)

    payload = _program()
    payload["scenes"][0]["html"] = "<script>alert(1)</script>"
    with pytest.raises(VisualProgramV21Error):
        parse_video_visual_program_v21(payload)


def test_parser_rejects_bad_references_and_storyboard_mismatch() -> None:
    payload = _program()
    payload["scenes"][0]["events"][0]["subject"] = "missing"
    with pytest.raises(VisualProgramV21Error):
        parse_video_visual_program_v21(payload)

    payload = _program()
    with pytest.raises(VisualProgramV21Error):
        parse_video_visual_program_v21(payload, storyboard={"sections": [{"id": "other"}]})


@pytest.mark.parametrize(
    ("event",),
    [
        ({"id": "move", "type": "PATH_MOTION", "subject": "plant", "path": [[0, 0]]},),
        ({"id": "bad", "type": "GROW", "subject": "plant", "from_state": "bud"},),
        ({"id": "bad", "type": "ORBIT_AROUND", "subject": "plant", "center": "sun"},),
    ],
)
def test_event_requirements_are_enforced(event: dict) -> None:
    payload = _program()
    payload["scenes"][0]["events"] = [event]
    with pytest.raises(VisualProgramV21Error):
        parse_video_visual_program_v21(payload)


def test_path_motion_uses_semantic_subject_routes_or_orbit_radius() -> None:
    payload = _program()
    payload["scenes"][0]["events"] = [{"id": "route", "type": "PATH_MOTION", "subject": "plant", "source": "sun", "destination": "plant", "duration": 2}]
    payload["scenes"][0]["narration_anchors"] = []
    parsed = parse_video_visual_program_v21(payload)
    assert parsed.scenes[0].events[0].path == ()

    payload = _program()
    payload["scenes"][0]["events"] = [{"id": "orbit", "type": "PATH_MOTION", "subject": "plant", "center": "sun", "radius": 3, "mode": "orbit", "duration": 2}]
    payload["scenes"][0]["narration_anchors"] = []
    parsed = parse_video_visual_program_v21(payload)
    assert parsed.scenes[0].events[0].radius == 3


def test_camera_requires_bounded_mode_and_semantic_target() -> None:
    payload = _program()
    payload["scenes"][0]["events"] = [{"id": "camera", "type": "CAMERA", "mode": "focus", "target": "plant"}]
    payload["scenes"][0]["narration_anchors"] = []
    assert parse_video_visual_program_v21(payload).scenes[0].events[0].target == "plant"

    for bad in (
        {"id": "camera", "type": "CAMERA", "mode": "focus", "parameters": {"position": [0, 0, 1]}},
        {"id": "camera", "type": "CAMERA", "mode": "focus"},
    ):
        payload = _program()
        payload["scenes"][0]["events"] = [bad]
        payload["scenes"][0]["narration_anchors"] = []
        with pytest.raises(VisualProgramV21Error):
            parse_video_visual_program_v21(payload)


@pytest.mark.parametrize("unsafe_key", ["position", "rotation", "x", "y", "z", "coordinates", "pixel", "SVG", "Three", "renderer_config"])
def test_renderer_owned_state_keys_are_rejected_recursively(unsafe_key: str) -> None:
    payload = _program()
    payload["scenes"][0]["initial_state"]["objects"]["plant"] = {"nested": {unsafe_key: [1, 2, 3]}}
    with pytest.raises(VisualProgramV21Error):
        parse_video_visual_program_v21(payload)


def test_numeric_data_series_and_semantic_radius_duration_remain_supported() -> None:
    payload = _program()
    payload["scenes"][0]["events"] = [{"id": "orbit", "type": "ORBIT_AROUND", "subject": "plant", "center": "sun", "radius": 4.5, "duration": 3.25}]
    payload["scenes"][0]["narration_anchors"] = []
    parsed = parse_video_visual_program_v21(payload)
    event = parsed.scenes[0].events[0]
    assert event.radius == 4.5
    assert event.duration == 3.25
    assert parsed.scenes[0].data_series[0].values == (1.0, 2.0, 3.0)

def test_merge_accepts_sources_and_validates_persistent_ids() -> None:
    payload = _program()
    payload["scenes"][0]["subjects"].append({"id": "result", "semantic_name": "fruit", "structural_family": "organic_body"})
    payload["scenes"][0]["events"] = [{"id": "merge", "type": "MERGE", "sources": ["plant", "sun"], "target": "result"}]
    payload["scenes"][0]["narration_anchors"] = []
    parsed = parse_video_visual_program_v21(payload)
    assert parsed.scenes[0].events[0].sources == ("plant", "sun")


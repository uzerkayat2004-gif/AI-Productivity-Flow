from __future__ import annotations

from voice_flow.video_flow_engine.scene_compiler_v2 import CompiledVisualProgramV21, compile_visual_program_v21
from voice_flow.video_flow_engine.visual_program_v21 import parse_video_visual_program_v21


def _base(subjects, events, relationships=(), *, strategy=("DIRECT_DEPICTION",), render="procedural_2d", shot=None):
    events = [dict(event, narration_anchor=f"a{index}") for index, event in enumerate(events)]
    anchors = [{"id": f"a{index}", "cue_index": index, "event_ids": [event["id"]]} for index, event in enumerate(events)]
    return {"version": "2.1", "content_intent": "DEMONSTRATE", "design_bible": {"surface": "paper", "palette": {"dominant": "paper", "accent_family": "green"}, "typography": "editorial", "shape_language": "organic", "background": "paper", "motion": "flowing", "caption_safe": "reserved_bottom"}, "scenes": [{"scene_id": "scene", "storyboard_section_id": "section", "purpose": "Show the subject.", "representation_strategy": list(strategy), "world": {"description": "A bounded world"}, "subjects": [{"id": item, "semantic_name": item.replace("_", " "), "structural_family": family, "render_strategy": render} for item, family in subjects], "relationships": list(relationships), "initial_state": {"objects": {item: {} for item, _ in subjects}}, "events": events, "shot": shot or {"mode": "focus", "framing": "hero", "subject": subjects[0][0]}, "narration_anchors": anchors}]}


def _storyboard():
    return {"topic": "Semantic visuals", "sections": [{"id": "section", "lecture_lines": ["A subject changes state and a carrier moves."]}]}


def test_compile_v21_uses_canonical_space_persistent_motion_and_cue_anchors():
    payload = _base([( "source", "network"), ("destination", "network"), ("carrier", "particle_system")], [{"id": "grow", "type": "GROW", "subject": "source", "from_state": "initial", "to_state": "expanded", "duration": 1}, {"id": "transfer", "type": "TRANSFER", "source": "source", "destination": "destination", "carrier": "carrier", "duration": 2}], [{"source": "source", "target": "destination", "kind": "flows_to", "carrier": "carrier"}])
    program = parse_video_visual_program_v21(payload, storyboard=_storyboard())
    compiled = compile_visual_program_v21(_storyboard(), program, duration_seconds=8)
    assert isinstance(compiled, CompiledVisualProgramV21)
    assert (compiled.scene_ir.space.logical_width, compiled.scene_ir.space.logical_height) == (1280, 720)
    assert all(0 <= item.box.x <= 1 and item.box.right <= 1 for item in compiled.scene_ir.scenes[0].objects)
    body = compiled.production["scenes"][0]["body"]
    assert 'data-cue="0"' in body and 'data-cue="1"' in body
    assert "<script" not in body.lower() and "threemodule" not in body.lower()
    assert {item["event_type"] for item in compiled.motion_qa} == {"GROW", "TRANSFER"}
    assert sum(scene["dur"] for scene in compiled.production["scenes"]) == 8
    assert all("duration" not in scene for scene in compiled.production["scenes"])
    assert compiled.production["timing"]["scene_durations"] == [8.0]
    carrier = next(item for item in compiled.production["scenes"][0]["three"]["objects"] if item["id"].endswith("carrier-group"))
    transfer_x = next(item for item in carrier["animate"] if item["property"] == "position.x")
    assert transfer_x["from"] != transfer_x["to"]


def test_compile_v21_orbit_is_group_offset_rotation_and_camera_animation():
    storyboard = _storyboard()
    payload = _base([( "star", "celestial_body"), ("ship", "rigid_assembly")], [{"id": "orbit", "type": "ORBIT_AROUND", "subject": "ship", "center": "star", "radius": 1.2, "duration": 4}], [{"source": "ship", "target": "star", "kind": "orbits"}], strategy=("SPATIAL",), render="semantic_3d", shot={"mode": "orbit", "framing": "hero", "subject": "ship", "center": "star"})
    program = parse_video_visual_program_v21(payload, storyboard=storyboard)
    compiled = compile_visual_program_v21(storyboard, program)
    three = compiled.production["scenes"][0]["three"]
    ship = next(item for item in three["objects"] if item["id"].endswith("ship-group"))
    assert ship["type"] == "group"
    assert ship["children"][0]["position"] != [0.0, 0.0, 0.0]
    assert ship["animate"][0]["property"] == "rotation.y"
    assert "animations" not in ship
    assert "groups" not in three
    assert "aspect" not in three["camera"]
    assert all(child["type"] not in {"group", "model", "particles"} for child in ship["children"])
    assert three["cameraAnimate"]
    assert all(set(animation) <= {"property", "from", "to", "by", "duration", "ease", "at", "wait"} for animation in three["cameraAnimate"])
    assert all(isinstance(animation["property"], str) and not isinstance(animation.get("from"), dict) for animation in three["cameraAnimate"])


def test_explicit_duration_changes_safe_tempo_but_omitted_duration_uses_mode_default():
    program = parse_video_visual_program_v21(_base([( "plant", "organic_branching")], []), storyboard=_storyboard())
    thirty = compile_visual_program_v21(_storyboard(), program, duration_seconds=30, mode="summary")
    sixty = compile_visual_program_v21(_storyboard(), program, duration_seconds=60, mode="summary")
    default = compile_visual_program_v21(_storyboard(), program, mode="summary")
    assert thirty.production["timing"]["tempo"] != sixty.production["timing"]["tempo"]
    assert 0.7 <= thirty.production["timing"]["tempo"] <= 1.3
    assert 0.7 <= sixty.production["timing"]["tempo"] <= 1.3
    assert default.production["timing"]["tempo"] == 1.12
    assert thirty.production["duration_is_target"] is True
    assert default.production["duration_is_target"] is False

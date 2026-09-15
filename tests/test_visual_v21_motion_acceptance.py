from __future__ import annotations

import math
import runpy
from pathlib import Path

from voice_flow.video_flow_engine.scene_state import evaluate_event, sample_event
from voice_flow.video_flow_engine.visual_program_v21 import parse_video_visual_program_v21


BENCHMARK = runpy.run_path(str(Path(__file__).parents[1] / "video-flow-v2.1" / "benchmark_v21.py"))


def _program(slug: str):
    record = next(item for item in BENCHMARK["fixture_records"]() if item["slug"] == slug)
    return parse_video_visual_program_v21(record["program"], storyboard=record["storyboard"])


def test_transfer_has_observable_carrier_displacement() -> None:
    program = _program("heart")
    state, events = BENCHMARK["_state_from_program"](program)
    transfer = next(event for event in events if event.id == "heart_to_lungs")
    metrics = BENCHMARK["event_qa_metrics"](state, transfer.to_dict())
    assert metrics.observed
    assert metrics.max_displacement > 0
    assert metrics.endpoint_distance == 0


def test_grow_changes_scale_and_geometry_not_only_visibility() -> None:
    program = _program("apple")
    state, events = BENCHMARK["_state_from_program"](program)
    grow = next(event for event in events if event.id == "apple_ripe")
    before = state.object("fruit")
    after = evaluate_event(state, grow.to_dict(), grow.duration).object("fruit")
    assert after.scale[0] > before.scale[0]
    assert after.geometry["growth"] > before.geometry.get("growth", 0.0)


def test_merge_converges_sources_and_reveals_result() -> None:
    program = _program("resnet")
    state, events = BENCHMARK["_state_from_program"](program)
    merge = next(event for event in events if event.id == "residual_merge")
    snapshots = sample_event(state, merge.to_dict(), samples=3)
    assert snapshots[0].object("token_main").position != snapshots[-1].object("token_main").position
    assert snapshots[0].object("token_shortcut").position != snapshots[-1].object("token_shortcut").position
    final = snapshots[-1]
    assert final.object("token_main").opacity == 0
    assert final.object("token_shortcut").opacity == 0
    assert final.object("sum").visible


def test_orbit_uses_semantic_center_radius_and_group_offset_motion() -> None:
    from voice_flow.video_flow_engine.scene_compiler_v2 import compile_visual_program_v21

    record = next(item for item in BENCHMARK["fixture_records"]() if item["slug"] == "mars")
    program = _program("mars")
    orbit = next(event for event in program.scenes[0].events if event.id == "mars_orbit")
    assert orbit.path == ()
    assert orbit.center == "mars"
    assert orbit.radius == 3.0
    assert orbit.mode == "orbit"
    compiled = compile_visual_program_v21(record["storyboard"], program)
    three = compiled.production["scenes"][0]["three"]
    group = next(item for item in three["objects"] if str(item["id"]).endswith("spacecraft-group"))
    assert group["children"][0]["position"] != [0.0, 0.0, 0.0]
    animate = group.get("animate")
    animations = [animate] if isinstance(animate, dict) else animate
    assert isinstance(animations, list)
    assert any(isinstance(item, dict) and item.get("property") == "rotation.y" for item in animations)
    assert three["cameraAnimate"]

def test_engine_state_descriptors_cover_piston_and_valves() -> None:
    scene = _program("engine").scenes[0]
    descriptor = {
        event.parameters["phase"]: (event.from_state, event.to_state)
        for event in scene.events
        if "phase" in event.parameters and event.subject in {"piston", "intake_valve", "exhaust_valve"}
    }
    assert {"intake", "compression", "power", "exhaust"} <= set(descriptor)
    assert all(pair[0] is not None and pair[1] is not None for pair in descriptor.values())


def test_scene_space_bounds_are_safe_for_every_fixture_layout() -> None:
    for result in BENCHMARK["run_benchmarks"]():
        layout = result["layout"]
        assert layout["status"] == "compiled"
        assert layout["space"]["svg_viewBox"] == "0 0 1280 720"
        assert layout["space"]["pixel_target"] == {"width": 1920, "height": 1080}








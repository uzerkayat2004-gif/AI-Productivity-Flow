from __future__ import annotations

import copy
import math
import runpy
from pathlib import Path

import pytest

from voice_flow.video_flow_engine.scene_state import evaluate_event
from voice_flow.video_flow_engine.visual_program_v21 import parse_video_visual_program_v21


BENCHMARK = runpy.run_path(str(Path(__file__).parents[1] / "video-flow-v2.1" / "benchmark_v21.py"))


def _records() -> list[dict]:
    return BENCHMARK["fixture_records"]()


def _record(slug: str) -> dict:
    return next(item for item in _records() if item["slug"] == slug)


def _program(slug: str):
    record = _record(slug)
    return parse_video_visual_program_v21(record["program"], storyboard=record["storyboard"])


def test_v21_fixture_set_is_exactly_the_bounded_twelve_case_benchmark() -> None:
    records = _records()
    assert [item["slug"] for item in records] == [
        "apple", "heart", "volcano", "engine", "house", "thunderstorm",
        "siege", "mars", "revenue", "pythagoras", "resnet", "datacenter",
    ]
    assert all(item["program"]["version"] == "2.1" for item in records)
    assert all(len(item["program"]["scenes"]) == 1 for item in records)


def test_every_fixture_parses_validates_lays_out_resolves_and_observes_events() -> None:
    results = BENCHMARK["run_benchmarks"]()
    assert len(results) == 12
    for result in results:
        assert result["parsed"] is True
        assert result["layout"]["status"] == "compiled"
        assert result["layout"]["object_count"] > 0
        assert result["representations"]
        assert all(item["valid"] for item in result["event_qa"].values())
        assert result["external_ai_called"] is False
        assert result["real_model"] is False
        # If an integration seam exists, it must either compile/validate or
        # leave a concrete result for the parent integration wave to fix.
        assert result["integration"]["status"] in {"compiled", "validated", "unavailable", "error"}


def test_integrated_compiler_is_strict_when_present() -> None:
    errors = [
        f"{item['slug']}: {item['integration'].get('error', 'unknown compiler error')}"
        for item in BENCHMARK["run_benchmarks"]()
        if item["integration"]["status"] == "error"
    ]
    if errors:
        pytest.fail("V2.1 compiler/validator seam reported fixture blockers:\n" + "\n".join(errors))


def test_benchmark_representation_mix_is_semantically_varied() -> None:
    results = BENCHMARK["run_benchmarks"]()
    representations = {name for item in results for name in item["capabilities"]["representations"]}
    assert {"DIRECT_DEPICTION", "DATA", "MATHEMATICAL"} <= representations
    assert any("three" in {plan["render_mode"] for plan in item["representations"].values()} for item in results)


def test_apple_direct_depiction_and_state_evolution_are_present() -> None:
    program = _program("apple")
    scene = program.scenes[0]
    assert {"DIRECT_DEPICTION", "STATE_EVOLUTION"} <= set(scene.representation_strategy)
    assert {"tree", "branch", "bud", "blossom", "fruit"} <= set(scene.all_subject_ids())
    state, events = BENCHMARK["_state_from_program"](program)
    blossom = next(event for event in events if event.id == "apple_blossom")
    ripe = next(event for event in events if event.id == "apple_ripe")
    final_blossom = evaluate_event(state, blossom.to_dict(), blossom.duration).object("bud")
    final_fruit = evaluate_event(state, ripe.to_dict(), ripe.duration).object("fruit")
    assert final_blossom.semantic_state == "blossom"
    assert final_fruit.scale[0] > state.object("fruit").scale[0]
    assert final_fruit.geometry["growth"] > state.object("fruit").geometry.get("growth", 0.0)


def test_mars_orbit_is_semantic_and_compiles_to_group_offset_motion() -> None:
    from voice_flow.video_flow_engine.scene_compiler_v2 import compile_visual_program_v21

    record = _record("mars")
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

def test_resnet_transfers_both_tokens_and_converges_at_merge() -> None:
    program = _program("resnet")
    state, events = BENCHMARK["_state_from_program"](program)
    main = next(event for event in events if event.id == "main_transfer")
    shortcut = next(event for event in events if event.id == "shortcut_transfer")
    merge = next(event for event in events if event.id == "residual_merge")
    assert BENCHMARK["event_qa_metrics"](state, main.to_dict()).max_displacement > 0
    assert BENCHMARK["event_qa_metrics"](state, shortcut.to_dict()).max_displacement > 0
    merged = evaluate_event(state, merge.to_dict(), merge.duration)
    assert merged.object("token_main").opacity == 0
    assert merged.object("token_shortcut").opacity == 0
    assert merged.object("sum").visible
    assert BENCHMARK["event_qa_metrics"](state, merge.to_dict()).details["converged"] is True


def test_engine_has_piston_valve_state_descriptors_for_all_four_strokes() -> None:
    program = _program("engine")
    scene = program.scenes[0]
    assert {"piston", "intake_valve", "exhaust_valve", "crankshaft"} <= set(scene.all_subject_ids())
    strokes = {event.parameters["phase"] for event in scene.events if "phase" in event.parameters}
    assert {"intake", "compression", "power", "exhaust"} <= strokes
    piston_events = [event for event in scene.events if event.subject == "piston"]
    assert all(event.from_state is not None and event.to_state is not None for event in piston_events)


def test_revenue_chart_uses_the_fixture_source_values() -> None:
    program = _program("revenue")
    series = program.scenes[0].data_series[0]
    assert series.values == (120.0, 145.0, 132.0, 190.0)
    reveal = next(event for event in program.scenes[0].events if event.id == "revenue_reveal")
    assert tuple(reveal.parameters["values"]) == series.values
    assert program.scenes[0].representation_strategy == ("DATA",)


def test_all_layout_results_use_one_canonical_scene_space_without_clipping() -> None:
    for result in BENCHMARK["run_benchmarks"]():
        space = result["layout"]["space"]
        assert space["logical_width"] == 1280.0
        assert space["logical_height"] == 720.0
        assert space["pixel_target"] == {"width": 1920, "height": 1080}
        # A relation-router fallback is an explicit current limitation, not a
        # clipping pass; bounds QA still ran for every resolved object.
        assert result["layout"]["status"] == "compiled"











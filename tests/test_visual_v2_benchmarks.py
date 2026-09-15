from __future__ import annotations

import runpy
from pathlib import Path

from voice_flow.video_flow_engine.scene_compiler_v2 import compile_visual_plan_v2
from voice_flow.video_flow_engine.visual_plan_v2 import parse_video_visual_plan_v2


BENCHMARK = runpy.run_path(str(Path(__file__).parents[1] / "video-flow-visual-v2" / "benchmark_v2.py"))


def test_all_seven_benchmarks_compile_validate_and_preserve_v1() -> None:
    results = BENCHMARK["run_benchmarks"]()
    assert len(results) == 7
    assert all(item["v1_result"] == "compiled" for item in results)
    assert all(item["v2_result"] == "validated" for item in results)
    assert all(item["validation"]["valid"] is True for item in results)
    assert all(item["fallback_used"] is False for item in results)


def test_unrelated_topics_have_distinct_non_sensitive_visual_signatures() -> None:
    results = BENCHMARK["run_benchmarks"]()
    signatures = {tuple(sorted(item["v2_signature"].items())) for item in results}
    assert len(signatures) == 7
    assert all(set(item["v2_signature"]) == {"surface_mode", "palette_family", "background_family", "typography_family", "motion_profile", "camera_profile", "depth_profile", "scene_density", "usage_3d"} for item in results)


def test_benchmarks_exercise_content_specific_mechanisms() -> None:
    results = {item["slug"]: item for item in BENCHMARK["run_benchmarks"]()}
    assert {"triangle", "square", "area"} <= set(results["pythagoras"]["v2_forms"])
    assert {"bypasses", "merges_into"} <= set(results["resnet"]["v2_relationships"])
    assert {"flow", "propagate"} <= set(results["xylem"]["v2_actions"])
    assert results["orbit"]["v2_signature"]["usage_3d"] is True
    assert {"bar", "area"} <= set(results["datacenter"]["v2_forms"])
    history = next(item for item in BENCHMARK["benchmark_cases"]() if item["slug"] == "history")
    assert {"map", "timeline"} <= {scene["visual_mode"] for scene in history["plan"]["scenes"]}
    assert {"scale", "propagate"} <= set(results["compound"]["v2_actions"])


def test_v2_bodies_are_not_one_repeated_template_and_design_is_coherent_within_case() -> None:
    bodies = []
    for item in BENCHMARK["benchmark_cases"]():
        plan = parse_video_visual_plan_v2(item["plan"], storyboard=item["storyboard"])
        compiled = compile_visual_plan_v2(item["storyboard"], plan)
        assert len(compiled.production["scenes"]) == 2
        assert compiled.design_tokens.surface_mode == plan.design_bible.surface_mode
        bodies.append(tuple(scene["body"] for scene in compiled.production["scenes"]))
    assert len(set(bodies)) == 7

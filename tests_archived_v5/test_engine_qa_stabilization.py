from __future__ import annotations

from voice_flow.video_flow_engine.director import VisualDirector
from voice_flow.video_flow_engine.quality import PreviewQA


def _generated_scene(**overrides):
    scene = {
        "id": "scene-1",
        "narration": "The 3D assembly exposes layers.",
        "duration": 6,
        "semanticTimings": [{"startRatio": 0, "endRatio": 1, "label": "assemble"}],
        "motionEvents": [{"action": "assemble", "purpose": "show spatial depth"}],
        "renderClass": "3d",
        "evidenceRefs": ["claim-1"],
        "viewerQuestion": "How does it assemble?",
    }
    scene.update(overrides)
    return scene


def test_director_normalizes_duration_timing_and_render_aliases_before_qa():
    director = VisualDirector(
        lambda _context: {
            "treatment": {"visual_world": "assembly"},
            "scenes": [_generated_scene()],
        }
    )
    package = director.create(
        {"claims": [{"id": "claim-1", "text": "The 3D assembly exposes layers."}]},
        request={"visual_direction": "Use a 3D cutaway"},
    )

    scene = package["scenes"][0]
    assert scene["duration_seconds"] == 6.0
    assert scene["render_class"] == "webgl-3d"
    assert scene["semantic_timings"][0]["end_seconds"] == 6.0


def test_explicit_spatial_depth_requires_a_real_three_scene():
    qa = PreviewQA()
    report = qa.inspect(
        {
            "spatial_depth_required": True,
            "scenes": [
                {
                    "id": "scene-1",
                    "narration": "A grounded claim.",
                    "duration": 4,
                    "semanticTimings": [{"startRatio": 0, "endRatio": 1}],
                    "motionEvents": [{"action": "reveal", "purpose": "show change"}],
                    "evidenceRefs": ["claim-1"],
                    "viewerQuestion": "What changes?",
                    "renderClass": "motion-island",
                }
            ],
        },
        evidence={"claims": [{"id": "claim-1"}]},
    )

    assert any(issue["code"] == "spatial-depth-missing" for issue in report["issues"])


def test_repair_failure_has_stable_actionable_diagnostics():
    director = VisualDirector(lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("offline")))
    package = director.repair(
        {"scenes": [{"id": "scene-1", "narration": "Keep this.", "evidence_refs": ["claim-1"]}]},
        {"repair_instructions": [{"scene_id": "scene-1", "action": "re-author motion"}]},
    )

    diagnostics = package["repair_diagnostics"]
    assert diagnostics["failed_scene_ids"] == ["scene-1"]
    assert diagnostics["deterministic_fallback"] is True
    assert "re-author only the failed scene contracts" in diagnostics["actionable_message"]

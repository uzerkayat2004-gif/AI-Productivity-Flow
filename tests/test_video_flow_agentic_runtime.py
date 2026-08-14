from __future__ import annotations

from typing import Any

from voice_flow.video_flow import VideoFlowService, VideoFlowStore


class LegacyVisualEngine:
    def build(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "version": 2,
            "title": "Legacy storyboard",
            "scenes": [{"id": "scene-1", "narration": "This must never render."}],
        }


def test_service_refuses_a_legacy_visual_manifest_before_rendering(tmp_path) -> None:
    store = VideoFlowStore(
        db_path=str(tmp_path / "voice-flow.db"),
        output_root=tmp_path / "videos",
    )
    service = VideoFlowService(store, visual_engine=LegacyVisualEngine())
    video = store.create_video(
        title="Agentic runtime contract",
        mode="summary",
        source_text="A harmless source used to verify the runtime contract.",
        model_ref="fake/model",
        external_ai_allowed=False,
    )

    service.run(video["id"])

    result = store.get_video(video["id"])
    assert result is not None
    assert result["status"] == "failed"
    assert "agentic-visual.v1" in result["error"]
    assert result["engine_version"] == ""


def test_catalog_does_not_advertise_the_retired_template_planner(tmp_path) -> None:
    store = VideoFlowStore(
        db_path=str(tmp_path / "voice-flow.db"),
        output_root=tmp_path / "videos",
    )
    service = VideoFlowService(store)

    model_refs = {item["full_id"] for item in service.catalog()["models"]}

    assert "local/deterministic" not in model_refs


def test_service_never_completes_without_a_rendered_video(tmp_path) -> None:
    class ValidAgenticVisualEngine:
        def build(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {
                "engineVersion": "agentic-visual.v1",
                "title": "Agentic output check",
                "fps": 24,
                "width": 1920,
                "height": 1080,
                "creativeTreatment": {"genre": "technical"},
                "creativeFingerprint": {"signature": "render-output-contract"},
                "diversityReport": {"accepted": True},
                "scenes": [
                    {
                        "id": "scene-1",
                        "title": "One scene",
                        "narration": "This render must exist before the job is complete.",
                        "durationSeconds": 3.0,
                        "durationInFrames": 72,
                        "fps": 24,
                        "width": 1920,
                        "height": 1080,
                        "renderClass": "motion-island",
                        "root": {
                            "id": "root",
                            "type": "group",
                            "layout": {"mode": "absolute", "width": 1920, "height": 1080},
                            "children": [],
                        },
                    }
                ],
            }

    store = VideoFlowStore(
        db_path=str(tmp_path / "voice-flow.db"),
        output_root=tmp_path / "videos",
    )
    service = VideoFlowService(store, visual_engine=ValidAgenticVisualEngine())
    service._synthesize = lambda *_args: {"durationSeconds": 3.0, "wordTimings": []}
    service._render = lambda *_args, **_kwargs: None
    video = store.create_video(
        title="Render contract",
        mode="summary",
        source_text="A harmless source.",
        model_ref="fake/model",
    )

    service.run(video["id"])

    result = store.get_video(video["id"])
    assert result is not None
    assert result["status"] == "failed"
    assert result["error"] == "The renderer did not produce a usable MP4."

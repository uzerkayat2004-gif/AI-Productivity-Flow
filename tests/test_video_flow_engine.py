from __future__ import annotations

from pathlib import Path

from voice_flow.video_flow_engine.engine import VideoFlowEngine


class _Planner:
    def plan(self, source_text: str, **_: object) -> dict:
        assert source_text
        return {
            "topic": "End-to-end autonomous driving",
            "target_audience": "general learners",
            "sections": [
                {
                    "id": "section_1",
                    "title": "From modules to one learned system",
                    "lecture_lines": [
                        "Traditional systems split perception, planning, and control.",
                        "End-to-end systems learn camera input to driving action.",
                    ],
                    "animations": [
                        "Compare the modular pipeline with one learned model.",
                        "Flow from camera frames to steering and braking.",
                    ],
                }
            ],
        }


class _Renderer:
    def render(self, production: dict, project_dir: Path, **_: object) -> Path:
        assert production["scenes"]
        output = project_dir / "video.mp4"
        output.write_bytes(b"test-mp4")
        return output


def test_run_completes_and_reports_pipeline_progress(tmp_path: Path) -> None:
    progress: list[dict] = []
    engine = VideoFlowEngine(planner=_Planner(), renderer=_Renderer())

    result = engine.run(
        "job-1",
        projects_root=tmp_path,
        project_dir=tmp_path / "job-1",
        source_text="We're moving toward end-to-end neural networks for autonomous driving.",
        progress_callback=progress.append,
    )

    assert result["state"] == "complete"
    assert Path(result["video_path"]).read_bytes() == b"test-mp4"
    assert [event["progress"] for event in progress] == sorted(event["progress"] for event in progress)
    assert progress[-1] == {"progress": 100.0, "message": "Ready", "state": "complete"}



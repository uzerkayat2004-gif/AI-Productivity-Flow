from __future__ import annotations

from pathlib import Path

from voice_flow.video_flow_engine.engine import VideoFlowEngine


class _ShouldNotRun:
    def plan(self, source_text: str, **_: object) -> dict:
        raise AssertionError("planner must not run for an unsafe job id")

    def render(self, production: dict, project_dir: Path, **_: object) -> Path:
        raise AssertionError("renderer must not run for an unsafe job id")


def test_run_rejects_job_id_path_traversal(tmp_path: Path) -> None:
    dependency = _ShouldNotRun()
    engine = VideoFlowEngine(planner=dependency, renderer=dependency)

    result = engine.run(
        "../escape",
        projects_root=tmp_path,
        source_text="Safe source text",
    )

    assert result["state"] == "failed"
    assert result["error_code"] == "invalid_job_id"
    assert not (tmp_path.parent / "escape").exists()

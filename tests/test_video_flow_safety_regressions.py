from __future__ import annotations

from pathlib import Path

import pytest

from voice_flow.video_flow_engine.code2video_runner import Code2VideoRunner
from voice_flow.video_flow_engine.engine import VideoFlowEngine
from voice_flow.video_flow_engine.process_manager import ProcessManager
from voice_flow.video_flow_engine.sandbox import EngineError


class _Planner:
    def __init__(self, storyboard: dict | None = None) -> None:
        self.called = False
        self.storyboard = storyboard or {
            "topic": "Safe",
            "sections": [{"id": "safe", "title": "Safe", "lecture_lines": ["Safe line."], "animations": ["Reveal safely."]}],
        }

    def plan(self, source_text: str, **_: object) -> dict:
        self.called = True
        return self.storyboard


class _Renderer:
    def render(self, production: dict, project_dir: Path, **_: object) -> Path:
        output = project_dir / "video.mp4"
        output.write_bytes(b"mp4")
        return output


def test_progress_callback_failure_never_escapes(tmp_path: Path) -> None:
    def broken_callback(event: dict) -> None:
        raise RuntimeError("host callback failed")

    result = VideoFlowEngine(planner=_Planner(), renderer=_Renderer()).run(
        "callback-safe",
        projects_root=tmp_path,
        source_text="Safe source",
        progress_callback=broken_callback,
    )

    assert result["state"] == "complete"


def test_cancellation_before_run_is_preserved(tmp_path: Path) -> None:
    manager = ProcessManager()
    manager.cancel_job("already-cancelled")
    planner = _Planner()

    result = VideoFlowEngine(process_manager=manager, planner=planner, renderer=_Renderer()).run(
        "already-cancelled",
        projects_root=tmp_path,
        source_text="Safe source",
    )

    assert result["state"] == "cancelled"
    assert not planner.called


def test_explicit_project_directory_must_stay_inside_projects_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-projects" / "escape-job"
    result = VideoFlowEngine(planner=_Planner(), renderer=_Renderer()).run(
        "escape-job",
        projects_root=tmp_path,
        project_dir=outside,
        source_text="Safe source",
    )

    assert result["state"] == "failed"
    assert result["error_code"] == "invalid_project_dir"
    assert not outside.exists()


def test_bridge_validation_maps_to_bridge_failed(tmp_path: Path) -> None:
    planner = _Planner(
        {
            "topic": "unsafe",
            "sections": [{"id": "unsafe", "title": "unsafe", "lecture_lines": ["<script>bad</script>"], "animations": ["bad"]}],
        }
    )
    result = VideoFlowEngine(planner=planner, renderer=_Renderer()).run(
        "bridge-failure",
        projects_root=tmp_path,
        source_text="Safe source",
    )

    assert result["state"] == "failed"
    assert result["error_code"] == "bridge_failed"


def test_injected_gateway_requires_external_ai_consent(tmp_path: Path) -> None:
    calls: list[str] = []

    def gateway(prompt: str, **_: object) -> str:
        calls.append(prompt)
        return "{}"

    runner = Code2VideoRunner(gateway=gateway)
    with pytest.raises(EngineError) as exc_info:
        runner.plan("private source", project_dir=tmp_path, allow_external_ai=False)

    assert exc_info.value.code == "provider_error"
    assert calls == []

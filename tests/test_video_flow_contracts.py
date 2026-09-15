from __future__ import annotations

from pathlib import Path

import pytest

from voice_flow.video_flow_engine import VideoFlowEngine
from voice_flow.video_flow_engine.bridge import build_narova_production
from voice_flow.video_flow_contracts import JobV3


class _Planner:
    def plan(self, source_text: str, **_: object) -> dict:
        return {
            "topic": "Safe topic",
            "sections": [
                {
                    "id": "safe",
                    "title": "Safe scene",
                    "lecture_lines": ["A safe teaching line."],
                    "animations": ["Reveal a safe diagram."],
                }
            ],
        }


class _Renderer:
    def render(self, production: dict, project_dir: Path, **_: object) -> Path:
        output = project_dir / "video.mp4"
        output.write_bytes(b"mp4")
        return output


def test_engine_updates_retained_job_contract(tmp_path: Path) -> None:
    job = JobV3("job-progress")
    result = VideoFlowEngine(planner=_Planner(), renderer=_Renderer()).run(
        job.job_id,
        projects_root=tmp_path,
        project_dir=tmp_path / job.job_id,
        source_text="Safe source",
        job=job,
    )

    assert result["state"] == "complete"
    assert job.state == "complete"
    assert job.progress == 100.0
    assert job.message == "Ready"
    assert (tmp_path / job.job_id / "logs" / "job.log").is_file()


def test_bridge_rejects_model_authored_executable_payload() -> None:
    with pytest.raises(ValueError, match="Security Boundary Violation"):
        build_narova_production(
            {
                "topic": "unsafe",
                "sections": [
                    {
                        "id": "unsafe",
                        "title": "unsafe",
                        "lecture_lines": ["<script>alert('no')</script>"],
                        "animations": ["unsafe"],
                    }
                ],
            }
        )






def test_validator_is_case_insensitive() -> None:
    from voice_flow.video_flow_contracts import validate_no_executable_code

    for payload in (
        "<ScRiPt>alert(1)</ScRiPt>",
        "please EVAL(1) now",
        "run SUBPROCESS now",
        {"scene": "call Child_Process today"},
    ):
        with pytest.raises(ValueError, match="Security Boundary Violation"):
            validate_no_executable_code(payload)
    # Ordinary narration still passes.
    validate_no_executable_code({"line": "Import grows as we process results."})


def test_validator_rejects_new_token_classes() -> None:
    from voice_flow.video_flow_contracts import validate_no_executable_code

    for payload in (
        "<iframe src='x'></iframe>",
        "steal document.cookie now",
        "eval via new Function('x')",
        "spawn('calc')",
    ):
        with pytest.raises(ValueError, match="Security Boundary Violation"):
            validate_no_executable_code(payload)


def test_validator_handles_unserializable_and_circular_payloads() -> None:
    from voice_flow.video_flow_contracts import validate_no_executable_code

    validate_no_executable_code({"tags": {"a", "b"}, "pair": (1, 2)})
    circular: dict = {}
    circular["self"] = circular
    validate_no_executable_code(circular)
    evil: dict = {}
    evil["self"] = evil
    evil["code"] = "<script>alert(1)</script>"
    with pytest.raises(ValueError, match="Security Boundary Violation"):
        validate_no_executable_code(evil)

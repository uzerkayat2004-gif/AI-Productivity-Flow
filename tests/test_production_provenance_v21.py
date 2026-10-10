from __future__ import annotations

import json
from pathlib import Path

import pytest

from voice_flow.video_flow_engine.production_provenance import (
    ProductionProvenanceError,
    cancelled_provenance,
    fallback_provenance,
    failed_terminal_provenance,
    provenance_from_dict,
    read_provenance_json,
    safe_job_relative_path,
    successful_provenance,
    write_provenance_json,
)


def test_successful_v21_provenance_marks_final_engine_and_artifact_status(tmp_path: Path) -> None:
    provenance = successful_provenance().with_attempt_artifact("attempt/plan.json").with_final_artifact("final/video.mp4", kind="video")
    assert provenance.final_engine == "visual-v2.1"
    assert provenance.fallback_used is False
    assert provenance.attempt_artifacts[0].status == "attempted"
    assert provenance.final_artifacts[0].status == "final"
    path = write_provenance_json(tmp_path, provenance)
    assert path.is_relative_to(tmp_path)
    assert read_provenance_json(tmp_path) == provenance
    assert json.loads(path.read_text(encoding="utf-8"))["final_engine"] == "visual-v2.1"


def test_fallback_and_cancellation_are_unambiguous() -> None:
    fallback = fallback_provenance(fallback_stage="capability_validation", fallback_reason="unsupported_event")
    assert fallback.final_engine == "visual-v1"
    assert fallback.fallback_used is True
    assert fallback.attempt_status == "failed"
    assert fallback.final_status == "final"

    cancelled = cancelled_provenance()
    assert cancelled.final_engine is None
    assert cancelled.final_status == "cancelled"
    assert cancelled.fallback_used is False


def test_failed_fallback_becomes_terminal_without_a_false_final_engine() -> None:
    fallback = fallback_provenance(fallback_stage="render", fallback_reason="v1_selected")
    failed = failed_terminal_provenance(fallback, stage="render", reason="fallback_renderer_failed")
    assert failed.final_status == "failed"
    assert failed.attempt_status == "failed"
    assert failed.final_engine is None
    assert failed.fallback_used is True
    assert failed.final_artifacts == ()


def test_failed_terminal_transition_cannot_follow_cancellation() -> None:
    with pytest.raises(ProductionProvenanceError):
        cancelled_provenance().fail_terminal()

@pytest.mark.parametrize("path", ["../escape.json", "/tmp/escape.json", "C:/escape.json", "\\\\server\\escape.json", "a/../../escape.json"])
def test_artifacts_cannot_escape_job_root(tmp_path: Path, path: str) -> None:
    with pytest.raises(ProductionProvenanceError):
        safe_job_relative_path(tmp_path, path)


def test_provenance_parser_rejects_stale_or_inconsistent_markers() -> None:
    payload = successful_provenance().to_dict()
    payload["final_engine"] = "visual-v1"
    with pytest.raises(ProductionProvenanceError):
        provenance_from_dict(payload)

    payload = successful_provenance().to_dict()
    payload["final_status"] = "cancelled"
    with pytest.raises(ProductionProvenanceError):
        provenance_from_dict(payload)


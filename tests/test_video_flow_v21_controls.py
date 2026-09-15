from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from voice_flow.gui.api_server import _shim_video
from voice_flow.video_flow_service import VideoFlowService, VideoFlowStore


class _Engine:
    def __init__(self): self.calls = []
    def run(self, job_id, **kwargs):
        self.calls.append(kwargs)
        output = Path(kwargs["project_dir"]) / "video.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"mp4")
        return {"state": "complete", "video_path": str(output), "duration_seconds": kwargs.get("duration_seconds"), "provenance": {"requested_engine": "visual-v2.1", "final_engine": "visual-v2.1", "fallback_used": False}}
    def cancel(self, *_): pass


def _wait(service, job_id):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = service.get(job_id)
        if job and job.state in {"complete", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_service_preserves_duration_and_voice_request_lineage(tmp_path: Path):
    engine = _Engine()
    service = VideoFlowService(store=VideoFlowStore(tmp_path / "jobs.db"), projects_root=tmp_path / "projects", engine_factory=lambda **_: engine, reconcile_orphans=False)
    queued = service.queue("Show a tree.", duration_seconds=42, voice="edge/en-US-AvaNeural")
    job = _wait(service, queued.job_id)
    assert job.state == "complete"
    assert engine.calls[0]["duration_seconds"] == 42
    assert engine.calls[0]["voice"] == "edge/en-US-AvaNeural"
    assert job.meta["duration_seconds"] == 42
    assert job.meta["provenance"]["final_engine"] == "visual-v2.1"


def test_history_shim_uses_final_engine_and_exposes_provenance():
    job = SimpleNamespace(job_id="vf", state="complete", progress=100, message="Ready", meta={"title": "Tree", "provenance": {"final_engine": "portable-v1", "fallback_used": True}})
    public = _shim_video(job)
    assert public["engine_version"] == "portable-v1"
    assert public["provenance"]["fallback_used"] is True


@pytest.mark.parametrize("duration", [9.99, 300.01])
def test_service_rejects_duration_outside_planner_bounds(tmp_path: Path, duration: float):
    service = VideoFlowService(store=VideoFlowStore(tmp_path / "jobs.db"), projects_root=tmp_path / "projects", reconcile_orphans=False)
    with pytest.raises(ValueError, match="between 10 and 300"):
        service.queue("Show a tree.", duration_seconds=duration)

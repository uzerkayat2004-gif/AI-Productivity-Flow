from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from voice_flow.video_flow_service import ProviderModelGateway, VideoFlowService, VideoFlowStore


class _Storage:
    def get_setting(self, *_): return "groq/llama-3.3-70b-versatile"
    def get_provider_connections(self, *_): return [{"is_active": 1, "api_key": "secret"}]
    def get_provider_models(self, *_): return []


def test_external_ai_consent_must_be_literal_bool(tmp_path: Path) -> None:
    service = VideoFlowService(store=VideoFlowStore(tmp_path / "jobs.db"), projects_root=tmp_path / "projects")
    with pytest.raises(ValueError, match="boolean"):
        service.queue("text", allow_external_ai="false")


def test_groq_model_selection_honors_current_ids_and_rejects_unknown() -> None:
    assert ProviderModelGateway.from_storage(_Storage(), "groq/openai/gpt-oss-20b")._model_id == "openai/gpt-oss-20b"
    assert ProviderModelGateway.from_storage(_Storage(), "groq/llama-3.3-70b-versatile")._model_id == "openai/gpt-oss-120b"
    with pytest.raises(RuntimeError, match="Unsupported"):
        ProviderModelGateway.from_storage(_Storage(), "groq/not-a-model")


def test_cancel_during_blocked_factory_never_runs_engine(tmp_path: Path) -> None:
    entered, release = threading.Event(), threading.Event()
    class Engine:
        ran = False
        cancelled = False
        def cancel(self, *_): self.cancelled = True
        def run(self, *_args, **_kwargs): self.ran = True; return {"state": "failed"}
    engine = Engine()
    def factory(**_):
        entered.set(); release.wait(1); return engine
    service = VideoFlowService(store=VideoFlowStore(tmp_path / "jobs.db"), projects_root=tmp_path / "projects", engine_factory=factory)
    queued = service.queue("text")
    assert entered.wait(1)
    service.cancel(queued.job_id); release.set()
    deadline = __import__("time").monotonic() + 1
    while __import__("time").monotonic() < deadline and not engine.cancelled: __import__("time").sleep(.01)
    assert engine.cancelled and not engine.ran


def test_gateway_logs_sanitized_jsonl(monkeypatch, tmp_path: Path) -> None:
    class Process:
        returncode = 0
        def communicate(self, *_args, **_kwargs): return json.dumps({"ok": True, "content": "response", "http_status": 200}), None
    class Manager:
        def register(self, *_): pass
        def unregister(self, *_): pass
        def cancel_job(self, *_): pass
    monkeypatch.setattr("voice_flow.video_flow_service.data_dir", lambda: tmp_path)
    monkeypatch.setattr("voice_flow.video_flow_service.subprocess.Popen", lambda *_a, **_k: Process())
    ProviderModelGateway(api_key="secret", provider="groq", model_id="openai/gpt-oss-120b").request_isolated(prompt="secret prompt", model_ref=None, max_tokens=1, timeout_seconds=1, job_id="vf-log", process_manager=Manager())
    line = (tmp_path / "v3_projects" / "vf-log" / "logs" / "code2video.log").read_text()
    assert '"status": "success"' in line and "secret prompt" not in line and "secret\"" not in line

def test_queue_accepts_and_threads_target_duration_seconds(tmp_path: Path) -> None:
    captured: dict = {}

    class _Engine:
        def run(self, job_id: str, **kwargs: object) -> dict:
            captured.update(kwargs)
            output = Path(kwargs["project_dir"]) / "video.mp4"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"mp4")
            return {"state": "complete", "video_path": str(output)}

        def cancel(self, job_id: str) -> None:
            pass

    service = VideoFlowService(
        store=VideoFlowStore(tmp_path / "jobs.db"),
        projects_root=tmp_path / "projects",
        engine_factory=lambda **_: _Engine(),
    )
    queued = service.queue("Some text", target_duration_seconds=150)
    deadline = __import__("time").monotonic() + 3
    while __import__("time").monotonic() < deadline and service.get(queued.job_id).state not in {"complete", "failed", "cancelled"}:
        __import__("time").sleep(0.01)

    assert queued.meta["target_duration_seconds"] == 150
    assert captured["target_duration_seconds"] == 150


def test_queue_rejects_out_of_range_target_duration(tmp_path: Path) -> None:
    import pytest as _pytest

    service = VideoFlowService(store=VideoFlowStore(tmp_path / "jobs.db"), projects_root=tmp_path / "projects")
    with _pytest.raises(ValueError, match="between 10 and 300"):
        service.queue("text", target_duration_seconds=999)


def test_request_from_meta_preserves_document_profile(tmp_path: Path) -> None:
    service = VideoFlowService(store=VideoFlowStore(tmp_path / "jobs.db"), projects_root=tmp_path / "projects", reconcile_orphans=False)
    profile = {"target_duration_seconds": 120, "recommended_format": "brief"}
    request = service._request_from_meta({"source_text": "hi", "title": "t", "document_profile": profile})
    assert request["document_profile"] == profile


def test_request_from_meta_includes_target_duration(tmp_path: Path) -> None:
    service = VideoFlowService(store=VideoFlowStore(tmp_path / "jobs.db"), projects_root=tmp_path / "projects", reconcile_orphans=False)
    request = service._request_from_meta({"source_text": "hi", "title": "t", "target_duration_seconds": 150})
    assert request["target_duration_seconds"] == 150


def test_cancel_also_cancels_pending_retry_timer(tmp_path: Path) -> None:
    service = VideoFlowService(store=VideoFlowStore(tmp_path / "jobs.db"), projects_root=tmp_path / "projects", reconcile_orphans=False)
    queued = service.queue("Some longer text for retry cancel")
    service._schedule_rate_limit_retry(queued.job_id, {"source_text": "hi"}, __import__("datetime").datetime.now() + __import__("datetime").timedelta(seconds=3600))
    assert queued.job_id in service._retry_timers
    service.cancel(queued.job_id)
    assert queued.job_id not in service._retry_timers
    assert service.get(queued.job_id).state == "cancelled"

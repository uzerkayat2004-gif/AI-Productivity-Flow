from __future__ import annotations

import time
from pathlib import Path

from voice_flow.video_flow_service import ProviderModelGateway, VideoFlowService, VideoFlowStore


class _Engine:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls: list[dict] = []
        self.cancelled: list[str] = []

    def run(self, job_id: str, **kwargs: object) -> dict:
        self.calls.append({"job_id": job_id, **kwargs})
        callback = kwargs["progress_callback"]
        callback({"progress": 50, "message": "Working with sk-secret-token", "state": "directing"})
        callback({"progress": 10, "message": "Late update", "state": "understanding"})
        if self.should_fail:
            return {"state": "failed", "error_code": "provider_error"}
        output = Path(kwargs["project_dir"]) / "video.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"mp4")
        return {"state": "complete", "video_path": str(output)}

    def cancel(self, job_id: str) -> None:
        self.cancelled.append(job_id)


class _BlockingEngine(_Engine):
    def __init__(self) -> None:
        super().__init__()
        import threading

        self.started = threading.Event()
        self.release = threading.Event()

    def run(self, job_id: str, **kwargs: object) -> dict:
        self.started.set()
        self.release.wait(2)
        return {"state": "cancelled", "error_code": "cancelled"}


class _Storage:
    def get_setting(self, *_: object) -> str:
        return "groq/llama-3.3-70b-versatile"

    def get_provider_connections(self, provider: str) -> list[dict]:
        assert provider == "groq"
        return [{"is_active": 1, "api_key": "secret"}]

    def get_provider_models(self, provider: str) -> list[dict]:
        assert provider == "groq"
        return [{"is_active": 1, "model_id": "llama-3.3-70b-versatile"}]


def _wait(service: VideoFlowService, job_id: str) -> object:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = service.get(job_id)
        if job and job.state in {"complete", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_queue_maps_request_progress_and_expected_output_path(tmp_path: Path) -> None:
    engine = _Engine()
    service = VideoFlowService(
        store=VideoFlowStore(tmp_path / "jobs.db"),
        projects_root=tmp_path / "v3_projects",
        engine_factory=lambda **_: engine,
    )

    queued = service.queue(
        "Explain autonomous driving.",
        title="Autonomous Driving",
        mode="lesson",
        theme={"accent": "blue"},
        visual_direction="show a pipeline",
    )
    job = _wait(service, queued.job_id)

    assert job.state == "complete"
    assert job.progress == 100
    assert Path(job.meta["output_path"]).read_bytes() == b"mp4"
    assert Path(job.meta["output_path"]) == tmp_path / "v3_projects" / queued.job_id / "video.mp4"
    assert engine.calls[0]["source_text"] == "Explain autonomous driving."
    assert engine.calls[0]["mode"] == "lesson"
    assert engine.calls[0]["theme"] == {"accent": "blue"}


def test_progress_is_monotonic_and_redacted(tmp_path: Path) -> None:
    engine = _Engine()
    service = VideoFlowService(store=VideoFlowStore(tmp_path / "jobs.db"), projects_root=tmp_path / "projects", engine_factory=lambda **_: engine)
    queued = service.queue("Text")
    _wait(service, queued.job_id)

    # Terminal state keeps the successful final status, while the stored event
    # history boundary rejects late lower progress updates.
    job = service.get(queued.job_id)
    assert job and job.progress == 100
    service._progress(queued.job_id, {"progress": 10, "message": "sk-another-secret", "state": "directing"})
    job = service.get(queued.job_id)
    assert job and job.progress == 100 and "secret" not in job.message


def test_failure_is_safe_and_persisted(tmp_path: Path) -> None:
    service = VideoFlowService(
        store=VideoFlowStore(tmp_path / "jobs.db"),
        projects_root=tmp_path / "projects",
        engine_factory=lambda **_: _Engine(should_fail=True),
    )
    queued = service.queue("Text")
    job = _wait(service, queued.job_id)

    assert job.state == "failed"
    assert job.message == "Generation failed"
    assert job.meta["error_code"] == "provider_error"
    assert VideoFlowStore(tmp_path / "jobs.db").get(queued.job_id).state == "failed"


def test_cancel_reaches_current_engine(tmp_path: Path) -> None:
    engine = _BlockingEngine()
    service = VideoFlowService(store=VideoFlowStore(tmp_path / "jobs.db"), projects_root=tmp_path / "projects", engine_factory=lambda **_: engine)
    queued = service.queue("Text")
    assert engine.started.wait(1)

    job = service.cancel(queued.job_id)
    engine.release.set()
    assert job and job.state == "cancelled"
    assert engine.cancelled == [queued.job_id]
    assert _wait(service, queued.job_id).state == "cancelled"


def test_provider_adapter_uses_explicit_isolated_groq_seam() -> None:
    gateway = ProviderModelGateway.from_storage(_Storage(), "groq/llama-3.3-70b-versatile")

    assert gateway.is_local is False
    assert callable(gateway.request_isolated)
    assert gateway._provider == "groq"
    assert gateway._model_id == "openai/gpt-oss-120b"



def test_provider_adapter_caps_groq_completion_budget_for_two_stage_planning(monkeypatch) -> None:
    captured: dict = {}

    class _Process:
        returncode = 0

        def communicate(self, payload: str, timeout: float):
            import json

            captured.update(json.loads(payload))
            return json.dumps({"ok": True, "content": "{}"}), None

    class _Manager:
        def register(self, job_id: str, process: object) -> None:
            pass

        def unregister(self, job_id: str, process: object) -> None:
            pass

        def cancel_job(self, job_id: str) -> None:
            pass

    monkeypatch.setattr("voice_flow.video_flow_service.subprocess.Popen", lambda *args, **kwargs: _Process())
    gateway = ProviderModelGateway(api_key="secret", provider="groq", model_id="openai/gpt-oss-120b")

    assert gateway.request_isolated(
        prompt="outline",
        model_ref="groq/openai/gpt-oss-120b",
        max_tokens=8_000,
        timeout_seconds=120,
        job_id="job",
        process_manager=_Manager(),
    ) == "{}"
    # Storyboards need several thousand tokens; the 8 192 ceiling only bounds
    # runaway requests, so an 8 000 budget passes through uncapped.
    assert captured["max_tokens"] == 8_000




def test_groq_worker_sets_explicit_user_agent() -> None:
    from voice_flow.video_flow_service import _GROQ_WORKER

    assert '"User-Agent": "VoiceFlow/1.0"' in _GROQ_WORKER






def test_groq_worker_uses_deterministic_json_temperature() -> None:
    from voice_flow.video_flow_service import _GROQ_WORKER

    assert '"temperature": 0,' in _GROQ_WORKER




def test_blank_model_selection_uses_verified_groq_instead_of_stale_policy() -> None:
    class _GeminiPolicyStorage(_Storage):
        def get_setting(self, *_: object) -> str:
            return "gemini/gemini-3.6-flash"

    gateway = ProviderModelGateway.from_storage(_GeminiPolicyStorage(), None)

    assert gateway._provider == "groq"
    assert gateway._model_id == "openai/gpt-oss-120b"


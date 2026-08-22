from __future__ import annotations

from dataclasses import dataclass

import pytest

from voice_flow.video_flow_player import launch_video_player, player_url, validate_job_id, video_url
from voice_flow.video_flow_widget import VideoFlowWidget


class _Value:
    def __init__(self, value: object = "") -> None:
        self.value = value

    def get(self) -> object:
        return self.value

    def set(self, value: object) -> None:
        self.value = value


class _Text:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self, *_: object) -> str:
        return self.value


class _Button:
    def __init__(self) -> None:
        self.state = "normal"

    def configure(self, **kwargs: object) -> None:
        self.state = str(kwargs.get("state", self.state))


@dataclass
class _Job:
    job_id: str = "vf-widget-test"
    state: str = "queued"
    progress: float = 0
    message: str = "Queued"


class _Service:
    def __init__(self) -> None:
        self.job = _Job()
        self.request: tuple[object, dict[str, object]] | None = None
        self.cancelled: list[str] = []

    def queue(self, source_text: str, **kwargs: object) -> _Job:
        self.request = (source_text, kwargs)
        return self.job

    def get(self, job_id: str) -> _Job | None:
        return self.job if job_id == self.job.job_id else None

    def cancel(self, job_id: str) -> _Job:
        self.cancelled.append(job_id)
        self.job.state = "cancelled"
        self.job.message = "Cancelled"
        return self.job


def _widget(service: _Service, launches: list[str]) -> VideoFlowWidget:
    widget = object.__new__(VideoFlowWidget)
    widget._service = service
    widget._player_launcher = launches.append
    widget._poll_interval_ms = 100
    widget._active_job_id = None
    widget._poll_scheduled = False
    widget._player_job_id = None
    widget._source_text = _Text("Selected text")
    widget._visual_direction = _Text("show a flow")
    widget.mode_var = _Value("lesson")
    widget.title_var = _Value("Demo")
    widget.model_ref_var = _Value("groq/openai/gpt-oss-120b")
    widget.theme_var = _Value("dark")
    widget.allow_external_ai_var = _Value(True)
    widget.status_var = _Value()
    widget.progress_var = _Value(0)
    widget._generate_button = _Button()
    widget._cancel_button = _Button()
    widget.after = lambda *_: None
    return widget


def test_widget_queues_selected_text_and_polls_progress() -> None:
    service, launches = _Service(), []
    widget = _widget(service, launches)

    job = widget.submit()

    assert job is service.job
    assert service.request == (
        "Selected text",
        {"mode": "lesson", "title": "Demo", "model_ref": "groq/openai/gpt-oss-120b", "theme": "dark", "visual_direction": "show a flow", "allow_external_ai": True},
    )
    assert widget._generate_button.state == "disabled"
    service.job.state, service.job.progress, service.job.message = "rendering", 67, "Rendering"
    widget._poll()
    assert widget.progress_var.value == 67
    assert widget.status_var.value == "Rendering"
    assert launches == []


def test_widget_cancels_and_opens_player_only_once_when_complete() -> None:
    service, launches = _Service(), []
    widget = _widget(service, launches)
    widget.submit()
    widget.cancel()
    assert service.cancelled == ["vf-widget-test"]

    widget._active_job_id = service.job.job_id
    service.job.state, service.job.progress, service.job.message = "complete", 100, "Ready"
    widget._poll()
    widget._active_job_id = service.job.job_id
    widget._poll()
    assert launches == ["vf-widget-test"]
    assert widget._cancel_button.state == "disabled"


@pytest.mark.parametrize("job_id", ["", "../bad", "vf bad", "vf/test", "x" * 129])
def test_player_rejects_invalid_job_ids(job_id: str) -> None:
    with pytest.raises(ValueError):
        validate_job_id(job_id)


def test_player_urls_and_child_process_are_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Process:
        pass

    def fake_popen(command: list[str], **kwargs: object) -> _Process:
        captured["command"], captured["kwargs"] = command, kwargs
        return _Process()

    monkeypatch.setattr("voice_flow.video_flow_player.subprocess.Popen", fake_popen)
    assert video_url("vf-demo") == "http://127.0.0.1:8991/api/video/jobs/vf-demo/video"
    assert player_url("vf-demo") == "http://127.0.0.1:8991/video-player.html?job_id=vf-demo"
    assert isinstance(launch_video_player("vf-demo"), _Process)
    assert captured["command"][1:3] == ["-m", "voice_flow.video_flow_player"]
    assert captured["command"][3] == "vf-demo"
    assert captured["kwargs"]["close_fds"] is True

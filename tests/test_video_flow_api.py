from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from voice_flow.gui import api_server
from voice_flow.video_flow_contracts import JobV3


class _Service:
    def __init__(self) -> None:
        self.job = JobV3("vf-test", meta={"output_path": "unused"})
        self.queued: dict[str, object] | None = None

    def queue(self, **kwargs: object) -> JobV3:
        self.queued = kwargs
        return self.job

    def get(self, job_id: str) -> JobV3 | None:
        return self.job if job_id == self.job.job_id else None

    def list(self) -> list[JobV3]:
        return [self.job]

    def cancel(self, job_id: str) -> JobV3 | None:
        job = self.get(job_id)
        if job:
            job.state = "cancelled"
        return job


def _request(url: str, *, method: str = "GET", body: dict | None = None, headers: dict[str, str] | None = None):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        method=method,
        headers=headers or ({"Content-Type": "application/json"} if body is not None else {}),
    )
    try:
        return urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as exc:
        return exc


def test_video_routes_queue_status_and_stream_range(monkeypatch, tmp_path: Path) -> None:
    video = tmp_path / "v3_projects" / "vf-test" / "video.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"0123456789")

    service = _Service()
    service.job = JobV3("vf-test", meta={
        "output_path": str(video),
        "title": "Demo",
        "timings": {"t_auth": 0.01, "t_cloud": 12.0, "total": 15.0},
    })
    monkeypatch.setattr(api_server, "get_video_flow_service", lambda: service)
    monkeypatch.setattr(api_server, "data_dir", lambda: tmp_path)

    from voice_flow.video_flow_engine.notebooklm.models import AuthStatus
    fake_auth = AuthStatus(status="ok", profile="default", authenticated=True, message="Authenticated")
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.NotebookLMVideoProvider.check_auth", lambda self, *a, **k: fake_auth)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.resolve_notebooklm_cli", lambda *a, **k: tmp_path / "notebooklm.exe")
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: None)

    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        generated = _request(base + "/api/video-flow/generate", method="POST", body={
            "source_text": "Explain this.", "mode": "lesson", "title": "Demo",
            "model_ref": "groq/openai/gpt-oss-120b", "theme": {"accent": "blue"},
            "visual_direction": "show the flow", "allow_external_ai": True,
        })
        assert generated.status == 202
        body = json.loads(generated.read())
        assert body["success"] is True and body["job_id"] == "vf-test"
        assert service.queued and service.queued["source_text"] == "Explain this."
        assert service.queued["allow_external_ai"] is True

        status = _request(base + "/api/video-flow/jobs/status?id=vf-test")
        assert status.status == 200
        status_data = json.loads(status.read())
        assert status_data["video"]["id"] == "vf-test"
        assert status_data["timings"]["t_cloud"] == 12.0
        assert status_data["video"]["timings"]["t_cloud"] == 12.0

        # Also verify /api/video-flow/status endpoint alias
        status_alias = _request(base + "/api/video-flow/status?id=vf-test")
        assert status_alias.status == 200
        alias_data = json.loads(status_alias.read())
        assert alias_data["video"]["id"] == "vf-test"
        assert alias_data["timings"]["t_cloud"] == 12.0

        # Verify /api/video-flow/history contains video with timings
        history = _request(base + "/api/video-flow/history")
        assert history.status == 200
        history_data = json.loads(history.read())
        assert len(history_data["videos"]) > 0
        assert history_data["videos"][0]["timings"]["t_cloud"] == 12.0

        ranged = _request(base + "/api/video-flow/videos/file?id=vf-test", headers={"Range": "bytes=2-5"})
        assert ranged.status == 206
        assert ranged.headers["Content-Range"] == "bytes 2-5/10"
        assert ranged.read() == b"2345"

        missing = _request(base + "/api/video-flow/jobs/status?id=vf-missing")
        assert missing.status == 404

        # Test /api/video-flow/generate with unspecified provider defaults to notebooklm
        generated_nlm = _request(base + "/api/video-flow/generate", method="POST", body={
            "source_text": "Explain quantum entanglement.",
            "title": "Quantum",
            "format": "cinematic",
            "style": "anime",
        })
        assert generated_nlm.status == 202
        assert service.queued["provider"] == "notebooklm"
        assert service.queued["video_engine"] == "notebooklm"
        assert service.queued["format"] == "cinematic"
        assert service.queued["style"] == "anime"

        # Test NotebookLM endpoints
        nlm_status = _request(base + "/api/video-flow/notebooklm/status")
        assert nlm_status.status == 200
        nlm_status_data = json.loads(nlm_status.read())
        assert nlm_status_data["success"] is True

        nlm_check = _request(base + "/api/video-flow/notebooklm/auth/check", method="POST", body={})
        assert nlm_check.status in (200, 400)

        nlm_start = _request(base + "/api/video-flow/notebooklm/auth/start", method="POST", body={})
        assert nlm_start.status in (200, 400)

        # Test Overlay endpoints (fallback when controller not registered)
        api_server.register_runtime_controller(None)
        overlay_status = _request(base + "/api/overlay/status")
        assert overlay_status.status == 200
        overlay_data = json.loads(overlay_status.read())
        assert overlay_data["active"] is True
        assert overlay_data["state"] == "READY"
        assert overlay_data["dock"] == "bottom"

        overlay_show = _request(base + "/api/overlay/show", method="POST", body={})
        assert overlay_show.status == 200
        show_data = json.loads(overlay_show.read())
        assert show_data["success"] is True

        overlay_reset = _request(base + "/api/overlay/reset-position", method="POST", body={})
        assert overlay_reset.status == 200
        reset_data = json.loads(overlay_reset.read())
        assert reset_data["success"] is True

        # Test Overlay endpoints with mock controller registered
        class _MockOverlay:
            def __init__(self):
                self.visible = True
                self.state = "READY"
                self.dock = "bottom"
                self.shown = False
                self.reset_called = False

            def show(self):
                self.shown = True

            def reset_position(self):
                self.reset_called = True

        class _MockController:
            def __init__(self):
                self.overlay = _MockOverlay()

        mock_ctrl = _MockController()
        api_server.register_runtime_controller(mock_ctrl)

        overlay_status2 = _request(base + "/api/overlay/status")
        assert overlay_status2.status == 200
        data2 = json.loads(overlay_status2.read())
        assert data2 == {"active": True, "state": "READY", "dock": "bottom"}

        overlay_show2 = _request(base + "/api/overlay/show", method="POST")
        assert overlay_show2.status == 200
        assert mock_ctrl.overlay.shown is True
        assert mock_ctrl.overlay.reset_called is True

        mock_ctrl.overlay.reset_called = False
        overlay_reset2 = _request(base + "/api/overlay/reset-position", method="POST")
        assert overlay_reset2.status == 200
        assert mock_ctrl.overlay.reset_called is True

        api_server.register_runtime_controller(None)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

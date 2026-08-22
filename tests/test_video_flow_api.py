from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from voice_flow.gui import api_server
from voice_flow.video_flow_v3.scheduler.job import JobV3


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
        return urllib.request.urlopen(request, timeout=2)
    except urllib.error.HTTPError as exc:
        return exc


def test_video_routes_queue_status_and_stream_range(monkeypatch, tmp_path: Path) -> None:
    video = tmp_path / "v3_projects" / "vf-test" / "video.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"0123456789")

    service = _Service()
    service.job = JobV3("vf-test", meta={"output_path": str(video), "title": "Demo"})
    monkeypatch.setattr(api_server, "get_video_flow_service", lambda: service)
    monkeypatch.setattr(api_server, "data_dir", lambda: tmp_path)

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
        assert json.loads(status.read())["video"]["id"] == "vf-test"

        ranged = _request(base + "/api/video-flow/videos/file?id=vf-test", headers={"Range": "bytes=2-5"})
        assert ranged.status == 206
        assert ranged.headers["Content-Range"] == "bytes 2-5/10"
        assert ranged.read() == b"2345"

        missing = _request(base + "/api/video-flow/jobs/status?id=vf-missing")
        assert missing.status == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

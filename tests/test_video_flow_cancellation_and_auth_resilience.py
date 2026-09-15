from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from voice_flow.gui import api_server
from voice_flow.video_flow_contracts import JobV3


ROOT = Path(__file__).resolve().parents[1]


class _MockCancelService:
    def __init__(self) -> None:
        self.jobs: dict[str, JobV3] = {
            "active-1": JobV3("active-1", state="generating", meta={"output_path": "out1.mp4"}),
            "completed-1": JobV3("completed-1", state="complete", meta={"output_path": "out2.mp4"}),
        }
        self.cancelled_ids: list[str] = []

    def get(self, job_id: str) -> JobV3 | None:
        return self.jobs.get(job_id)

    def list(self, limit: int = 100) -> list[JobV3]:
        return list(self.jobs.values())

    def cancel(self, job_id: str) -> JobV3 | None:
        self.cancelled_ids.append(job_id)
        job = self.jobs.get(job_id)
        if job:
            job.state = "cancelled"
        return job


def _post_json(url: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_video_flow_cancel_api_endpoints(monkeypatch, tmp_path: Path):
    """Test /api/video-flow/cancel with explicit ID, aliases, and auto-detecting active job."""
    service = _MockCancelService()
    monkeypatch.setattr(api_server, "get_video_flow_service", lambda: service)
    monkeypatch.setattr(api_server, "data_dir", lambda: tmp_path)

    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    try:
        # 1. Cancel with explicit ID
        code, data = _post_json(f"{base}/api/video-flow/cancel", {"id": "active-1"})
        assert code == 200
        assert data["success"] is True
        assert data["id"] == "active-1"
        assert data["status"] == "cancelled"
        assert "active-1" in service.cancelled_ids

        # 2. Cancel alias /api/video-flow/videos/cancel with video_id
        service.jobs["active-2"] = JobV3("active-2", state="processing")
        code, data = _post_json(f"{base}/api/video-flow/videos/cancel", {"video_id": "active-2"})
        assert code == 200
        assert data["id"] == "active-2"
        assert "active-2" in service.cancelled_ids

        # 3. Auto-detect active job when ID is omitted
        service.jobs["active-3"] = JobV3("active-3", state="rendering")
        code, data = _post_json(f"{base}/api/video-flow/cancel", {})
        assert code == 200
        assert data["id"] == "active-3"
        assert "active-3" in service.cancelled_ids

        # 4. Error when no active job exists and no ID provided
        service.jobs.clear()
        code, data = _post_json(f"{base}/api/video-flow/cancel", {})
        assert code == 400
        assert data["success"] is False
        assert "No active video job to cancel" in data["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_storage_state_read_resilience_and_lock_retry(monkeypatch, tmp_path: Path):
    """Test that _read_notebooklm_storage_state handles sharing violations and parses cookies."""
    profile_name = "test-isolated-resilience-profile"
    storage_dir = tmp_path / ".notebooklm" / "profiles" / profile_name
    storage_dir.mkdir(parents=True)
    storage_file = storage_dir / "storage_state.json"

    valid_payload = {
        "cookies": [
            {"name": "SID", "value": "test_sid_val", "expires": time.time() + 3600},
            {"name": "HSID", "value": "test_hsid_val", "expires": time.time() + 3600},
        ],
        "notebooklm": {"account": {"email": "user@example.com"}},
    }
    storage_file.write_text(json.dumps(valid_payload), encoding="utf-8")

    monkeypatch.setenv("NOTEBOOKLM_HOME", str(tmp_path / ".notebooklm"))
    with patch("pathlib.Path.home", return_value=tmp_path):
        auth, email, path, details = api_server._read_notebooklm_storage_state(profile_name)
        assert auth is True
        assert email == "user@example.com"
        assert details["cookies_count"] == 2


def test_storage_state_backup_fallback(monkeypatch, tmp_path: Path):
    """Test fallback to storage_state.backup.json when primary is empty or corrupted."""
    profile_name = "test-isolated-backup-profile"
    storage_dir = tmp_path / ".notebooklm" / "profiles" / profile_name
    storage_dir.mkdir(parents=True)
    primary = storage_dir / "storage_state.json"
    backup = storage_dir / "storage_state.backup.json"

    # Corrupted primary
    primary.write_text("{ corrupt json ...", encoding="utf-8")

    # Valid backup
    backup_payload = {
        "cookies": [
            {"name": "SID", "value": "backup_sid", "expires": time.time() + 3600},
        ],
        "account": {"email": "backup@example.com"},
    }
    backup.write_text(json.dumps(backup_payload), encoding="utf-8")

    monkeypatch.setenv("NOTEBOOKLM_HOME", str(tmp_path / ".notebooklm"))
    with patch("pathlib.Path.home", return_value=tmp_path):
        auth, email, path, details = api_server._read_notebooklm_storage_state(profile_name)
        assert auth is True
        assert email == "backup@example.com"


def test_verify_online_network_error_does_not_revoke_cookies(monkeypatch, tmp_path: Path):
    """Test that online verification errors (timeouts, network hiccups) do not mark valid local session unauthenticated."""
    from voice_flow.video_flow_engine.notebooklm import login_flow

    monkeypatch.setattr(
        api_server,
        "_read_notebooklm_storage_state",
        lambda profile: (True, "test@example.com", str(tmp_path / "storage_state.json"), {"cookies_count": 5}),
    )
    monkeypatch.setattr(
        login_flow,
        "verify_online",
        lambda profile=None, force=False: {"authenticated": False, "status": "error", "message": "Connection timed out"},
    )
    monkeypatch.setattr(login_flow, "master_token_present", lambda profile: True)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.resolve_notebooklm_cli", lambda *a, **k: tmp_path / "cli.exe")

    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    try:
        req = urllib.request.Request(f"{base}/api/video-flow/notebooklm/status?verify=1")
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode("utf-8"))
            # Local session is valid, online check had network error -> authenticated MUST stay True!
            assert data["authenticated"] is True
            assert data["status"] == "ok"
            # Non-definitive network error must NOT report online_verified as False
            assert data.get("online_verified") is None
    finally:
        server.shutdown()
        server.server_close()


def test_login_flow_singleton_locks_cleanup(tmp_path: Path):
    """Test that _terminate_stale_login_processes removes Chrome Singleton lock files."""
    from voice_flow.video_flow_engine.notebooklm import login_flow

    b_dir = tmp_path / "browser_profile"
    b_dir.mkdir(parents=True)
    (b_dir / "SingletonLock").write_text("lock", encoding="utf-8")
    (b_dir / "SingletonCookie").write_text("cookie", encoding="utf-8")
    (b_dir / "SingletonSocket").write_text("sock", encoding="utf-8")

    log_file = tmp_path / "login.log"
    log_file.write_text("", encoding="utf-8")

    with patch.object(login_flow, "_profile_browser_dir", return_value=b_dir):
        login_flow._terminate_stale_login_processes("test", log_file)

    assert not (b_dir / "SingletonLock").exists()
    assert not (b_dir / "SingletonCookie").exists()
    assert not (b_dir / "SingletonSocket").exists()


def test_notebooklm_provider_cancel_support(tmp_path: Path):
    """Verify NotebookLMVideoProvider implements cancel() and notifies process manager."""
    from voice_flow.video_flow_engine.notebooklm import NotebookLMVideoProvider
    from voice_flow.video_flow_engine.process_manager import ProcessManager

    pm = ProcessManager()
    provider = NotebookLMVideoProvider(workdir=tmp_path, process_manager=pm)
    assert hasattr(provider, "cancel")

    provider._active_job_id = "job-nlm-cancel-1"
    provider.cancel("job-nlm-cancel-1")
    assert pm.is_cancelled("job-nlm-cancel-1")


def test_notebooklm_cancelled_job_aborts_without_local_fallback(tmp_path: Path):
    """Verify that a cancelled NotebookLM job aborts immediately without triggering local fallback."""
    from voice_flow.video_flow_engine.notebooklm import NotebookLMVideoProvider, VideoRequest, NotebookLMVideoError
    from voice_flow.video_flow_engine.process_manager import ProcessManager

    pm = ProcessManager()
    pm.cancel_job("job-cancel-test")

    mock_engine_run = MagicMock()
    with patch("voice_flow.video_flow_engine.engine.VideoFlowEngine.run", mock_engine_run):
        provider = NotebookLMVideoProvider(
            workdir=tmp_path,
            process_manager=pm,
            allow_local_fallback=True,
            runner=lambda cmd, timeout: MagicMock(returncode=0, stdout='{"status": "ok"}', stderr=""),
        )
        req = VideoRequest(
            title="Test Cancel",
            prompt="Explain cancellation",
            source_text="Test cancellation source text",
            output_path=tmp_path / "out.mp4",
            job_id="job-cancel-test",
        )
        with pytest.raises(NotebookLMVideoError) as exc_info:
            provider.generate(req)

        assert exc_info.value.code == "cancelled"
        # Local engine run MUST NOT be invoked on a cancelled job!
        mock_engine_run.assert_not_called()


def test_ui_contract_and_stepper_integrity():
    """Verify HTML and JS contracts for in-app cancel button and no false-positive auth expired resurrection."""
    html = (ROOT / "src" / "voice_flow" / "gui" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "src" / "voice_flow" / "gui" / "video-flow.js").read_text(encoding="utf-8")
    css = (ROOT / "src" / "voice_flow" / "gui" / "video-flow.css").read_text(encoding="utf-8")

    # In-app cancel buttons in HTML
    assert 'id="vf-stepper-cancel-btn"' in html
    assert 'onclick="cancelActiveVideoGeneration()"' in html
    assert 'id="vf-cancel-generation-btn"' in html

    # Cancel styles in CSS
    assert ".vf-stepper-cancel-btn" in css
    assert ".vf-cancel-generation-btn" in css

    # Cancel logic and tracking in JS
    assert "cancelActiveVideoGeneration" in js
    assert "vfSetCancelButtonVisibility" in js
    assert "vfActiveVideoId" in js
    assert "/api/video-flow/cancel" in js

    # Ensure the buggy resurrection line 'latestFailedAuth' is removed from video-flow.js!
    assert "latestFailedAuth" not in js

    # Ensure isAuth does not mistakenly overwrite authenticated state on transient network error
    assert "data.authenticated !== undefined ? Boolean(data.authenticated)" in js


def test_verify_online_real_auth_expiry_revokes_auth_and_returns_unauthenticated(monkeypatch, tmp_path: Path):
    """Test that online verification correctly revokes auth when Google session has expired."""
    from voice_flow.video_flow_engine.notebooklm import login_flow

    monkeypatch.setattr(
        api_server,
        "_read_notebooklm_storage_state",
        lambda profile: (True, "test@example.com", str(tmp_path / "storage_state.json"), {"cookies_count": 5}),
    )
    monkeypatch.setattr(
        login_flow,
        "verify_online",
        lambda profile=None, force=False: {
            "authenticated": False,
            "status": "error",
            "message": "Google session is no longer valid — sign in again",
            "details_message": "Token fetch failed: Authentication expired or invalid.",
        },
    )
    monkeypatch.setattr(login_flow, "master_token_present", lambda profile: False)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.resolve_notebooklm_cli", lambda *a, **k: tmp_path / "cli.exe")

    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    try:
        req = urllib.request.Request(f"{base}/api/video-flow/notebooklm/status?verify=1")
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode("utf-8"))
            assert data["authenticated"] is False
            assert data["online_verified"] is False
            assert data["status"] == "unauthenticated"
    finally:
        server.shutdown()
        server.server_close()


def test_engine_run_cancelled_job_returns_state_cancelled_without_fallback(tmp_path: Path):
    """Verify VideoFlowEngine.run returns state='cancelled' and does not fall back when cancelled."""
    from voice_flow.video_flow_engine.engine import VideoFlowEngine
    from voice_flow.video_flow_engine.process_manager import ProcessManager

    pm = ProcessManager()
    pm.cancel_job("engine-cancel-test")

    engine = VideoFlowEngine(process_manager=pm)
    project_dir = tmp_path / "proj"
    project_dir.mkdir(parents=True)

    result = engine.run(
        "engine-cancel-test",
        project_dir=project_dir,
        source_text="Sample text",
        title="Test Title",
        video_engine="visual-v2.1",
    )

    assert result["state"] == "cancelled"
    assert result["error_code"] == "cancelled"


def test_wait_for_artifact_reraises_cancelled_immediately(tmp_path: Path):
    """Verify wait_for_artifact aborts immediately when cancellation occurs."""
    from voice_flow.video_flow_engine.notebooklm import NotebookLMVideoProvider, NotebookLMVideoError
    from voice_flow.video_flow_engine.process_manager import ProcessManager

    pm = ProcessManager()
    pm.cancel_job("artifact-cancel-job")

    provider = NotebookLMVideoProvider(workdir=tmp_path, process_manager=pm)

    with pytest.raises(NotebookLMVideoError) as exc_info:
        provider.wait_for_artifact("nb-1", "task-1", job_id="artifact-cancel-job")

    assert exc_info.value.code == "cancelled"


def test_video_flow_service_run_exception_handles_cancellation(tmp_path: Path):
    """Verify that video_flow_service._run marks jobs as cancelled on cancellation exception."""
    from voice_flow.video_flow_service import VideoFlowService, VideoFlowStore
    from voice_flow.video_flow_engine.process_manager import ProcessManager

    store = VideoFlowStore(db_path=tmp_path / "vf.db")
    svc = VideoFlowService(store=store, projects_root=tmp_path / "projects", reconcile_orphans=False)
    job = svc.queue(source_text="hello world", title="Cancel Test")

    pm = ProcessManager()
    pm.cancel_job(job.job_id)

    mock_engine = MagicMock()
    mock_engine.process_manager = pm
    mock_engine.run.side_effect = RuntimeError("cancelled: job was cancelled")

    svc._engine_factory = lambda **kwargs: mock_engine
    svc._run(job.job_id, {"source_text": "hello", "title": "test"})

    updated_job = svc.get(job.job_id)
    assert updated_job is not None
    assert updated_job.state == "cancelled"


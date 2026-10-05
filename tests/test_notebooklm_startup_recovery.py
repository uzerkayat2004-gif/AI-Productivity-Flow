"""API regressions for silent NotebookLM startup session recovery."""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from voice_flow.gui import api_server
from voice_flow.video_flow_engine import notebooklm
from voice_flow.video_flow_engine.notebooklm import login_flow


@pytest.fixture
def status_server(monkeypatch, tmp_path):
    cli = tmp_path / "notebooklm.exe"
    cli.touch()
    monkeypatch.setattr(notebooklm, "resolve_notebooklm_cli", lambda explicit=None: cli)
    monkeypatch.setattr(notebooklm, "resolve_notebooklm_mcp", lambda: None)
    monkeypatch.setattr(notebooklm, "resolve_notebooklm_profile", lambda profile=None: profile or "video-flow-experiment")
    monkeypatch.setattr(
        api_server,
        "_read_notebooklm_storage_state",
        lambda profile: (True, "saved@example.com", str(tmp_path / "storage_state.json"), {"cookies_count": 40}),
    )
    monkeypatch.setattr(login_flow, "master_token_present", lambda profile: False)
    monkeypatch.setattr(notebooklm, "get_keepalive_status", lambda profile=None: {"running": True})

    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def _get(base: str, suffix: str = "") -> dict:
    with urllib.request.urlopen(f"{base}/api/video-flow/notebooklm/status{suffix}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def test_saved_session_dispatches_one_silent_startup_recovery(monkeypatch, status_server):
    calls: list[dict] = []
    monkeypatch.setattr(notebooklm, "get_session_refresh_state", lambda profile=None: {"state": "idle", "in_progress": False})
    monkeypatch.setattr(
        notebooklm,
        "request_session_refresh",
        lambda profile=None, **kwargs: calls.append({"profile": profile, **kwargs}) or {
            "state": "restoring", "in_progress": True, "dispatched": True, "coalesced": False
        },
    )
    monkeypatch.setattr(login_flow, "verify_online", lambda **kwargs: pytest.fail("startup recovery should precede expiry verification"))

    body = _get(status_server)

    assert body["status"] == "restoring"
    assert body["recovery_state"] == "restoring"
    assert body["online_verified"] is None
    assert body["account_saved"] is True
    assert calls == [{"profile": "video-flow-experiment", "background": True, "force": False}]


def test_in_progress_recovery_is_reported_without_duplicate_dispatch(monkeypatch, status_server):
    monkeypatch.setattr(
        notebooklm,
        "get_session_refresh_state",
        lambda profile=None: {"state": "restoring", "in_progress": True, "dispatched": True},
    )
    monkeypatch.setattr(notebooklm, "request_session_refresh", lambda **kwargs: pytest.fail("must not redispatch"))
    monkeypatch.setattr(login_flow, "verify_online", lambda **kwargs: pytest.fail("must not race the recovery worker"))

    body = _get(status_server)

    assert body["status"] == "restoring"
    assert body["recovery_in_progress"] is True
    assert body["authenticated"] is False


def test_transient_recovery_failure_keeps_saved_account_retryable(monkeypatch, status_server):
    monkeypatch.setattr(
        notebooklm,
        "get_session_refresh_state",
        lambda profile=None: {
            "state": "transient_error", "in_progress": False, "message": "Google DNS unavailable"
        },
    )
    monkeypatch.setattr(notebooklm, "request_session_refresh", lambda **kwargs: pytest.fail("poll must not loop jobs"))
    monkeypatch.setattr(login_flow, "verify_online", lambda **kwargs: pytest.fail("stable recovery result is authoritative"))

    body = _get(status_server)

    assert body["status"] == "transient_error"
    assert body["verification_unavailable"] is True
    assert body["online_verified"] is None
    assert body["account_saved"] is True
    assert "reconnect" not in body["message"].lower()


def test_explicit_retry_forces_one_coalesced_recovery(monkeypatch, status_server):
    calls: list[dict] = []
    monkeypatch.setattr(
        notebooklm,
        "get_session_refresh_state",
        lambda profile=None: {"state": "transient_error", "in_progress": False},
    )
    monkeypatch.setattr(
        notebooklm,
        "request_session_refresh",
        lambda profile=None, **kwargs: calls.append({"profile": profile, **kwargs}) or {
            "state": "refreshing", "in_progress": True, "dispatched": True, "coalesced": False
        },
    )
    monkeypatch.setattr(login_flow, "verify_online", lambda **kwargs: pytest.fail("retry must use renewal helper"))

    body = _get(status_server, "?force=1")

    assert body["status"] == "restoring"
    assert body["recovery_in_progress"] is True
    assert body["cookie_health"]["status"] == "refreshing"
    assert calls == [{"profile": "video-flow-experiment", "background": True, "force": True}]


def test_genuine_sign_in_required_is_reported_only_after_recovery_finishes(monkeypatch, status_server):
    monkeypatch.setattr(
        notebooklm,
        "get_session_refresh_state",
        lambda profile=None: {"state": "sign_in_required", "in_progress": False, "definitive": True},
    )
    monkeypatch.setattr(notebooklm, "request_session_refresh", lambda **kwargs: pytest.fail("completed result must not redispatch"))
    monkeypatch.setattr(login_flow, "verify_online", lambda **kwargs: pytest.fail("completed recovery result is authoritative"))

    body = _get(status_server)

    assert body["status"] == "sign_in_required"
    assert body["online_verified"] is False
    assert body["recovery_in_progress"] is False
    assert body["account_saved"] is True

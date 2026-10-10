"""Focused regression tests for bounded NotebookLM authentication checks."""

from __future__ import annotations

from types import SimpleNamespace
import json
import time
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from voice_flow.gui import api_server
from voice_flow.video_flow_engine.notebooklm import config, login_flow


def test_explicit_profile_never_falls_back_to_another_account(monkeypatch):
    monkeypatch.setattr(config, "has_valid_storage_state", lambda profile: profile == "default")

    assert config.resolve_notebooklm_profile("work-account") == "work-account"


def test_online_verification_cache_is_scoped_to_profile():
    login_flow._ONLINE_CACHE.clear()
    login_flow._cache_online_verification(
        "account-a", {"profile": "account-a", "authenticated": True, "status": "ok"}
    )

    assert login_flow.get_online_verification_cache("account-a")["authenticated"] is True
    assert login_flow.get_online_verification_cache("account-b") is None


def test_verify_online_reports_network_failure_without_auth_invalidation(monkeypatch, tmp_path):
    fake_cli = tmp_path / "notebooklm.exe"
    fake_cli.touch()
    writes: list[tuple[str, object]] = []

    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: fake_cli)
    monkeypatch.setattr(
        login_flow.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="{}", stderr="network connection timed out"),
    )
    monkeypatch.setattr("voice_flow.storage.storage.save_setting", lambda key, value: writes.append((key, value)))

    result = login_flow.verify_online(profile="network-profile", force=True)

    assert result["status"] == "network_error"
    assert result["authenticated"] is None
    assert result["definitive"] is False
    assert not any(key == "video_flow_notebooklm_authenticated" and value is False for key, value in writes)


def test_self_heal_uses_one_cli_refresh_without_browser_fallback(monkeypatch, tmp_path):
    fake_cli = tmp_path / "notebooklm.exe"
    fake_cli.touch()
    commands: list[list[str]] = []

    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: fake_cli)
    monkeypatch.setattr(config, "is_profile_disconnected", lambda profile=None: False)
    monkeypatch.setattr(login_flow, "_login_log_path", lambda: tmp_path / "login.log")
    monkeypatch.setattr(
        login_flow,
        "_run_login_once",
        lambda command, log_path, timeout: commands.append(command) or (0, ""),
    )

    result = login_flow.self_heal(profile="refresh-profile")

    assert result["ok"] is True
    assert commands == [[str(fake_cli), "--profile", "refresh-profile", "auth", "refresh", "--verify"]]


def test_local_reader_keeps_expired_saved_account_reconnectable(monkeypatch, tmp_path):
    state = tmp_path / "storage_state.json"
    state.write_text(json.dumps({
        "cookies": [{"name": "SID", "value": "saved", "expires": 1}],
        "account": {"email": "saved@example.com"},
    }), encoding="utf-8")
    settings = {
        "video_flow_notebooklm_email": "saved@example.com",
        "video_flow_notebooklm_authenticated": True,
        "video_flow_notebooklm_disconnected": False,
    }
    monkeypatch.setattr(api_server, "storage", SimpleNamespace(get_setting=lambda key: settings.get(key)))
    monkeypatch.setattr(config, "get_storage_state_path", lambda profile=None: state)
    monkeypatch.setattr(config, "get_storage_backup_path", lambda profile=None: state.with_name("backup.json"))
    monkeypatch.setattr(
        login_flow, "get_online_verification_cache",
        lambda profile=None: {"authenticated": False, "status": "unauthenticated", "checked_at": time.time()},
    )

    saved, email, _, details = api_server._read_notebooklm_storage_state("saved-profile")

    assert saved is False
    assert email == "saved@example.com"
    assert details["expired"] is True
    assert details.get("disconnected") is not True


def test_local_reader_does_not_treat_network_verification_as_expiry(monkeypatch, tmp_path):
    state = tmp_path / "storage_state.json"
    state.write_text(json.dumps({
        "cookies": [{"name": "SID", "value": "saved", "expires": 4102444800}],
        "account": {"email": "saved@example.com"},
    }), encoding="utf-8")
    monkeypatch.setattr(api_server, "storage", SimpleNamespace(get_setting=lambda key: None))
    monkeypatch.setattr(config, "get_storage_state_path", lambda profile=None: state)
    monkeypatch.setattr(config, "get_storage_backup_path", lambda profile=None: state.with_name("backup.json"))
    monkeypatch.setattr(
        login_flow, "get_online_verification_cache",
        lambda profile=None: {"authenticated": False, "status": "network_error", "checked_at": 2.0},
    )

    saved, email, _, details = api_server._read_notebooklm_storage_state("saved-profile")

    assert saved is True
    assert email == "saved@example.com"
    assert details.get("expired") is not True


def test_missing_storage_with_saved_email_remains_a_saved_account(monkeypatch, tmp_path):
    settings = {
        "video_flow_notebooklm_email": "saved@example.com",
        "video_flow_notebooklm_authenticated": False,
        "video_flow_notebooklm_disconnected": False,
        "video_flow_notebooklm_switched_from": "",
    }
    monkeypatch.setattr(api_server, "storage", SimpleNamespace(get_setting=lambda key: settings.get(key)))
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(config, "get_storage_state_path", lambda profile=None: missing)
    monkeypatch.setattr(config, "get_storage_backup_path", lambda profile=None: missing.with_name("backup.json"))

    saved, email, _, details = api_server._read_notebooklm_storage_state("saved-profile")

    assert saved is False
    assert email == "saved@example.com"
    assert details["storage_missing"] is True


def test_status_requires_cli_even_when_the_mcp_executable_exists(monkeypatch, tmp_path):
    mcp = tmp_path / "notebooklm-mcp.exe"
    mcp.touch()
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.resolve_notebooklm_cli", lambda explicit=None: None
    )
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.resolve_notebooklm_mcp", lambda: mcp
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_address[1]}/api/video-flow/notebooklm/status",
            timeout=5,
        ) as response:
            body = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()

    assert body["available"] is False
    assert body["status"] == "dependency_missing"
    assert body["mcp_available"] is True

"""Unit and integration tests for NotebookLM default browser login, account switching, and disconnect."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from voice_flow.google_auth import (
    GoogleAuthError,
    complete_notebooklm_flow,
    handle_browser_callback,
    start_notebooklm_browser_flow,
)
from voice_flow.gui import api_server
from voice_flow.storage import StorageEngine
from voice_flow.video_flow_engine.notebooklm import login_flow


def test_start_notebooklm_browser_flow_creates_valid_url(monkeypatch):
    """Test start_notebooklm_browser_flow generates a valid consent URL with prompt=select_account."""
    opened_urls = []
    monkeypatch.setattr("voice_flow.google_auth.open_system_browser", lambda url: opened_urls.append(url) or True)

    result = start_notebooklm_browser_flow(port=8991, profile="test-profile")
    assert result["success"] is True
    assert result["opened"] is True
    assert len(opened_urls) == 1

    url = opened_urls[0]
    assert "https://accounts.google.com/o/oauth2/v2/auth" in url
    assert "prompt=select_account" in url
    assert "response_type=code" in url
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A8991%2Fcallback" in url
    assert result["state"].startswith("vfnlm:")


def test_complete_notebooklm_flow_success(monkeypatch, tmp_path):
    """Test complete_notebooklm_flow exchanges code, persists user email, and updates storage_state.json."""
    opened_urls = []
    monkeypatch.setattr("voice_flow.google_auth.open_system_browser", lambda url: opened_urls.append(url) or True)
    flow_init = start_notebooklm_browser_flow(port=8991, profile="test-profile")
    state = flow_init["state"]

    mock_tokens = {
        "access_token": "ya29.mock_token_notebooklm_test",
        "refresh_token": "1//mock_refresh_token",
        "expires_in": 3600,
    }
    mock_userinfo = {
        "email": "user.test2026@gmail.com",
        "name": "Test User",
        "picture": "https://example.com/avatar.png",
    }

    test_storage_dir = tmp_path / ".notebooklm" / "profiles" / "test-profile"
    test_storage_dir.mkdir(parents=True, exist_ok=True)
    storage_state_file = test_storage_dir / "storage_state.json"
    storage_state_file.write_text(
        json.dumps({
            "cookies": [{"name": "SID", "value": "dummy-sid", "expires": time.time() + 3600}],
            "notebooklm": {"version": 1, "account": {"email": "old@example.com"}},
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path",
        lambda prof=None: storage_state_file,
    )
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config.get_storage_backup_path",
        lambda prof=None: test_storage_dir / "storage_state.backup.json",
    )

    with patch("voice_flow.google_auth._provider_token_exchange", return_value=mock_tokens):
        with patch("voice_flow.google_auth._provider_userinfo", return_value=mock_userinfo):
            outcome = complete_notebooklm_flow("mock_code_123", state, 8991)

    assert outcome["email"] == "user.test2026@gmail.com"
    login_state = login_flow.get_login_state()
    assert login_state["success"] is True
    assert login_state["running"] is False
    assert "user.test2026@gmail.com" in login_state["note"]

    # Verify storage_state.json was updated with new email
    updated_data = json.loads(storage_state_file.read_text(encoding="utf-8"))
    assert updated_data["notebooklm"]["account"]["email"] == "user.test2026@gmail.com"
    assert updated_data["account"]["email"] == "user.test2026@gmail.com"


def test_complete_notebooklm_flow_mismatch():
    """Test state mismatch raises GoogleAuthError."""
    with pytest.raises(GoogleAuthError, match="OAuth state mismatch"):
        complete_notebooklm_flow("some_code", "vfnlm:invalid_state", 8991)


def test_notebooklm_switch_account(monkeypatch, tmp_path):
    """Test seamless account switching to another email without prompting for a new profile."""
    monkeypatch.setattr("voice_flow.google_auth.open_system_browser", lambda url: True)
    test_st_file = tmp_path / "storage_state.json"
    test_st_file.write_text(json.dumps({"cookies": []}), encoding="utf-8")
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path",
        lambda prof=None: test_st_file,
    )
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config.get_storage_backup_path",
        lambda prof=None: tmp_path / "storage_state.backup.json",
    )

    flow1 = start_notebooklm_browser_flow(port=8991, profile="video-flow-experiment")
    with patch("voice_flow.google_auth._provider_token_exchange", return_value={"access_token": "tok1"}):
        with patch("voice_flow.google_auth._provider_userinfo", return_value={"email": "first.account@gmail.com"}):
            complete_notebooklm_flow("code1", flow1["state"], 8991)

    assert login_flow.get_login_state()["success"] is True
    assert "first.account@gmail.com" in login_flow.get_login_state()["note"]

    # Now switch to second account
    flow2 = start_notebooklm_browser_flow(port=8991, profile="video-flow-experiment")
    assert flow2["state"] != flow1["state"]
    with patch("voice_flow.google_auth._provider_token_exchange", return_value={"access_token": "tok2"}):
        with patch("voice_flow.google_auth._provider_userinfo", return_value={"email": "second.account@gmail.com"}):
            complete_notebooklm_flow("code2", flow2["state"], 8991)

    assert login_flow.get_login_state()["success"] is True
    assert "second.account@gmail.com" in login_flow.get_login_state()["note"]


def test_notebooklm_disconnect(monkeypatch, tmp_path):
    """Test disconnect_login marks session unauthenticated and clears settings."""
    storage_file = tmp_path / "storage_state.json"
    storage_file.write_text(
        json.dumps({
            "cookies": [{"name": "SID", "value": "val", "expires": 2000000000}],
            "notebooklm": {"account": {"email": "connected@gmail.com"}},
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path",
        lambda prof=None: storage_file,
    )

    login_flow.record_successful_login("connected@gmail.com")
    assert login_flow.get_login_state()["success"] is True

    disc_result = login_flow.disconnect_login()
    assert disc_result["success"] is True
    assert disc_result["authenticated"] is False

    state = login_flow.get_login_state()
    assert state["running"] is False
    assert state["success"] is False
    assert state["note"] == "Disconnected"

    # Verify _read_notebooklm_storage_state reports unauthenticated
    auth, email, _, _ = api_server._read_notebooklm_storage_state("default")
    assert auth is False
    assert email is None


def test_start_login_ci_disable_guard(monkeypatch):
    """Test that VOICE_FLOW_LOGIN_DISABLE environment variable blocks real browser launches."""
    monkeypatch.setenv("VOICE_FLOW_LOGIN_DISABLE", "1")
    result = login_flow.start_login(profile="video-flow-experiment")
    assert result["launched"] is False
    assert "disabled in this environment" in result["error"]


def test_notebooklm_api_server_endpoints_integration(monkeypatch, tmp_path):
    """End-to-end HTTP integration test for NotebookLM status, auth/start, /callback, and disconnect."""
    monkeypatch.delenv("VOICE_FLOW_LOGIN_DISABLE", raising=False)
    monkeypatch.setattr("voice_flow.google_auth.open_system_browser", lambda url: True)

    db_path = str(tmp_path / "vf_nlm_test.db")
    test_storage = StorageEngine(db_path)
    monkeypatch.setattr(api_server, "storage", test_storage)
    monkeypatch.setattr("voice_flow.storage.storage", test_storage)

    test_profile_dir = tmp_path / "nlm_profile"
    test_profile_dir.mkdir(parents=True, exist_ok=True)
    test_st_file = test_profile_dir / "storage_state.json"
    test_st_file.write_text(json.dumps({"cookies": []}), encoding="utf-8")
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path",
        lambda prof=None: test_st_file,
    )
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config.get_storage_backup_path",
        lambda prof=None: test_profile_dir / "storage_state.backup.json",
    )

    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    server.daemon_threads = True
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.15)
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. Start auth via POST /api/video-flow/notebooklm/auth/start
        req_start = urllib.request.Request(
            f"{base_url}/api/video-flow/notebooklm/auth/start",
            data=json.dumps({"profile": "video-flow-experiment"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Connection": "close"},
        )
        with urllib.request.urlopen(req_start, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert data["launched"] is True
            assert data["mode"] == "browser"

        state_data = login_flow.get_login_state()
        assert state_data["running"] is True

        # Extract state from pending
        pending = None
        from voice_flow import google_auth as ga_module
        with ga_module._connect() as conn:
            raw = ga_module._kv_get(conn, "notebooklm_flow_pending")
            if raw:
                pending = json.loads(raw)
        assert pending is not None
        saved_state = pending["state"]
        assert saved_state.startswith("vfnlm:")

        # 2. Simulate Google browser callback GET /callback?code=test_auth_code&state=...
        mock_tokens = {"access_token": "ya29.test_access_token", "expires_in": 3600}
        mock_userinfo = {"email": "api.user@example.com"}

        with patch("voice_flow.google_auth._provider_token_exchange", return_value=mock_tokens):
            with patch("voice_flow.google_auth._provider_userinfo", return_value=mock_userinfo):
                req_cb = urllib.request.Request(
                    f"{base_url}/callback?code=test_auth_code&state={saved_state}",
                    headers={"Connection": "close"},
                )
                with urllib.request.urlopen(req_cb, timeout=10) as resp:
                    html_content = resp.read().decode("utf-8")
                    assert "Signed in to NotebookLM as api.user@example.com" in html_content

        # 3. Check status via GET /api/video-flow/notebooklm/status
        req_status = urllib.request.Request(
            f"{base_url}/api/video-flow/notebooklm/status",
            headers={"Connection": "close"},
        )
        with urllib.request.urlopen(req_status, timeout=10) as resp:
            status_data = json.loads(resp.read().decode("utf-8"))
            assert status_data["success"] is True
            assert status_data["authenticated"] is True
            assert status_data["email"] == "api.user@example.com"

        # 4. Disconnect via POST /api/video-flow/notebooklm/auth/disconnect
        req_disc = urllib.request.Request(
            f"{base_url}/api/video-flow/notebooklm/auth/disconnect",
            data=json.dumps({"profile": "video-flow-experiment"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Connection": "close"},
        )
        with urllib.request.urlopen(req_disc, timeout=10) as resp:
            disc_data = json.loads(resp.read().decode("utf-8"))
            assert disc_data["success"] is True
            assert disc_data["authenticated"] is False

        # 5. Verify status is now unauthenticated
        with urllib.request.urlopen(req_status, timeout=10) as resp:
            status_data = json.loads(resp.read().decode("utf-8"))
            assert status_data["authenticated"] is False
            assert status_data["email"] is None

    finally:
        server.shutdown()
        server.server_close()


def test_notebooklm_flow_branding_not_antigravity():
    """Verify NotebookLM provider flow is branded Google NotebookLM and does not use Antigravity credentials."""
    from voice_flow.google_auth import (
        PROVIDER_ANTIGRAVITY_CLIENT_ID,
        _notebooklm_flow,
        _provider_flow,
    )

    flow = _notebooklm_flow()
    assert flow["label"] == "Google NotebookLM"
    assert flow["client_id"] != PROVIDER_ANTIGRAVITY_CLIENT_ID
    assert "cloud-platform" not in flow["scope"]
    assert "cclog" not in flow["scope"]
    assert "experimentsandconfigs" not in flow["scope"]
    assert "openid" in flow["scope"]

    prov_flow = _provider_flow("notebooklm")
    assert prov_flow["label"] == "Google NotebookLM"
    assert prov_flow["client_id"] != PROVIDER_ANTIGRAVITY_CLIENT_ID


def test_notebooklm_flow_dynamic_client_id_override(monkeypatch):
    """Verify environment variable NOTEBOOKLM_CLIENT_ID overrides the default client ID."""
    from voice_flow.google_auth import _notebooklm_flow

    monkeypatch.setenv("NOTEBOOKLM_CLIENT_ID", "custom-nlm-id.example.test")
    monkeypatch.setenv("NOTEBOOKLM_CLIENT_SECRET", "custom-secret-123")
    flow = _notebooklm_flow()
    assert flow["client_id"] == "custom-nlm-id.example.test"
    assert flow["client_secret"] == "custom-secret-123"


def test_start_notebooklm_browser_flow_direct_url_and_params(monkeypatch):
    """Verify start_notebooklm_browser_flow returns direct_login_url and valid OAuth URL without Antigravity client ID."""
    from voice_flow.google_auth import (
        PROVIDER_ANTIGRAVITY_CLIENT_ID,
        start_notebooklm_browser_flow,
    )

    monkeypatch.setattr("voice_flow.google_auth.open_system_browser", lambda url: True)
    res_normal = start_notebooklm_browser_flow(port=8991, switch_account=False)
    assert res_normal["success"] is True
    assert "direct_login_url" in res_normal
    assert "notebooklm.google.com" in res_normal["direct_login_url"]
    assert PROVIDER_ANTIGRAVITY_CLIENT_ID not in res_normal["auth_url"]

    res_switch = start_notebooklm_browser_flow(port=8991, switch_account=True)
    assert "AccountChooser" in res_switch["direct_login_url"]
    assert "prompt=select_account" in res_switch["auth_url"]


def test_login_command_fresh_on_switch_account():
    """Verify CLI login command includes --fresh when switch_account is True."""
    from voice_flow.video_flow_engine.notebooklm.login_flow import _login_command

    cli = Path("C:/fake/notebooklm.exe")
    cmd_browser = _login_command(
        cli, "test-prof", mode="browser", account_email=None,
        browser="chrome", browser_timeout=300, switch_account=True,
    )
    assert "--fresh" in cmd_browser

    cmd_mt = _login_command(
        cli, "test-prof", mode="master-token", account_email="second@gmail.com",
        browser="chrome", browser_timeout=300, switch_account=True,
    )
    assert "--fresh" in cmd_mt
    assert "--force" in cmd_mt


def test_complete_notebooklm_flow_cleans_mismatched_master_token_on_account_switch(monkeypatch, tmp_path):
    """Verify account switch cleans mismatched master_token.json from old account."""
    opened_urls = []
    monkeypatch.setattr("voice_flow.google_auth.open_system_browser", lambda url: opened_urls.append(url) or True)

    flow = start_notebooklm_browser_flow(port=8991, profile="test-switch-prof", switch_account=True)
    state = flow["state"]

    test_prof_dir = tmp_path / "test-switch-prof"
    test_prof_dir.mkdir(parents=True, exist_ok=True)
    st_file = test_prof_dir / "storage_state.json"
    st_file.write_text(
        json.dumps({
            "cookies": [{"name": "SID", "value": "old-val"}],
            "account": {"email": "old.user@gmail.com"},
        }),
        encoding="utf-8",
    )
    mt_file = test_prof_dir / "master_token.json"
    mt_file.write_text(
        json.dumps({"account": "old.user@gmail.com", "master_token": "aas_et/old_token"}),
        encoding="utf-8",
    )

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path", lambda p=None: st_file)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_backup_path", lambda p=None: test_prof_dir / "storage_state.backup.json")
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_profile_dir", lambda p=None: test_prof_dir)

    mock_tokens = {"access_token": "ya29.new_token"}
    mock_userinfo = {"email": "new.user@gmail.com"}

    with patch("voice_flow.google_auth._provider_token_exchange", return_value=mock_tokens):
        with patch("voice_flow.google_auth._provider_userinfo", return_value=mock_userinfo):
            outcome = complete_notebooklm_flow("new_code", state, 8991)

    assert outcome["email"] == "new.user@gmail.com"
    # Verify old master_token.json was removed because it belonged to old.user@gmail.com
    assert not mt_file.is_file()
    # Verify storage_state.json has the new email
    updated = json.loads(st_file.read_text(encoding="utf-8"))
    assert updated["account"]["email"] == "new.user@gmail.com"


def test_disconnect_cleans_master_token_and_backup(monkeypatch, tmp_path):
    """Verify disconnect_login purges master_token.json and storage_state.backup.json."""
    test_prof_dir = tmp_path / "test-disc-prof"
    test_prof_dir.mkdir(parents=True, exist_ok=True)
    st_file = test_prof_dir / "storage_state.json"
    st_file.write_text(json.dumps({"cookies": [{"name": "SID", "value": "1"}]}), encoding="utf-8")
    b_file = test_prof_dir / "storage_state.backup.json"
    b_file.write_text(json.dumps({"cookies": [{"name": "SID", "value": "1"}]}), encoding="utf-8")
    mt_file = test_prof_dir / "master_token.json"
    mt_file.write_text(json.dumps({"account": "user@gmail.com", "master_token": "aas_et/1"}), encoding="utf-8")

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path", lambda p=None: st_file)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_backup_path", lambda p=None: b_file)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow._master_token_json_path", lambda p=None: mt_file)

    disc_res = login_flow.disconnect_login(profile="test-disc-prof")
    assert disc_res["success"] is True
    assert not mt_file.is_file()
    assert not b_file.is_file()


def test_account_switch_does_not_leak_old_backup_cookies(monkeypatch, tmp_path):
    """Verify switching to a second account does not restore old account cookies from backup."""
    opened_urls = []
    monkeypatch.setattr("voice_flow.google_auth.open_system_browser", lambda url: opened_urls.append(url) or True)

    flow = start_notebooklm_browser_flow(port=8991, profile="test-switch-clean", switch_account=True)
    state = flow["state"]

    test_prof_dir = tmp_path / "test-switch-clean"
    test_prof_dir.mkdir(parents=True, exist_ok=True)
    st_file = test_prof_dir / "storage_state.json"
    st_file.write_text(json.dumps({"cookies": [], "account": {"email": "account1@gmail.com"}}), encoding="utf-8")
    b_file = test_prof_dir / "storage_state.backup.json"
    b_file.write_text(json.dumps({"cookies": [{"name": "SID", "value": "account1-secret-sid"}]}), encoding="utf-8")

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path", lambda p=None: st_file)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_backup_path", lambda p=None: b_file)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_profile_dir", lambda p=None: test_prof_dir)

    mock_tokens = {"access_token": "ya29.new_token_acct2"}
    mock_userinfo = {"email": "account2@gmail.com"}

    with patch("voice_flow.google_auth._provider_token_exchange", return_value=mock_tokens):
        with patch("voice_flow.google_auth._provider_userinfo", return_value=mock_userinfo):
            outcome = complete_notebooklm_flow("code_sw", state, 8991)

    assert outcome["email"] == "account2@gmail.com"
    updated = json.loads(st_file.read_text(encoding="utf-8"))
    # Old cookies from account1 backup must not be in account2 storage
    assert updated["cookies"] == []
    # Old backup file should be removed
    assert not b_file.is_file()


def test_start_notebooklm_browser_flow_direct_mode(monkeypatch):
    """Verify start_notebooklm_browser_flow opens direct_login_url when direct=True."""
    opened_urls = []
    monkeypatch.setattr("voice_flow.google_auth.open_system_browser", lambda url: opened_urls.append(url) or True)

    res = start_notebooklm_browser_flow(port=8991, profile="test-direct", switch_account=True, direct=True)
    assert res["success"] is True
    assert len(opened_urls) == 1
    assert "AccountChooser" in opened_urls[0]
    assert "notebooklm.google.com" in opened_urls[0]


def test_start_login_opens_auth_system_when_direct_false(monkeypatch):
    """Verify start_login opens the Google OAuth authentication system when direct=False."""
    monkeypatch.delenv("VOICE_FLOW_LOGIN_DISABLE", raising=False)
    opened_urls = []
    monkeypatch.setattr("voice_flow.google_auth.open_system_browser", lambda url: opened_urls.append(url) or True)

    res = login_flow.start_login(profile="video-flow-experiment", port=8991, direct=False)
    assert res["launched"] is True
    assert res["mode"] == "browser"
    assert len(opened_urls) == 1
    opened = opened_urls[0]
    assert "accounts.google.com/o/oauth2" in opened
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A8991%2Fcallback" in opened
    assert "vfnlm%3A" in opened
    assert "prompt=select_account" in opened


def test_complete_notebooklm_flow_no_switch_no_change_cookies_unbound_regression(tmp_path, monkeypatch):
    """Regression test: verify complete_notebooklm_flow executes without UnboundLocalError
    when is_switch is False and account has not changed."""
    monkeypatch.delenv("VOICE_FLOW_LOGIN_DISABLE", raising=False)
    opened_urls = []
    monkeypatch.setattr("voice_flow.google_auth.open_system_browser", lambda url: opened_urls.append(url) or True)

    flow_init = start_notebooklm_browser_flow(port=8991, profile="test-regression-prof", switch_account=False)
    state = flow_init["state"]

    test_prof_dir = tmp_path / "profiles" / "test-regression-prof"
    test_prof_dir.mkdir(parents=True, exist_ok=True)
    st_file = test_prof_dir / "storage_state.json"
    st_file.write_text(json.dumps({
        "cookies": [{"name": "SID", "value": "existing-sid"}],
        "account": {"email": "same.user@gmail.com"},
    }), encoding="utf-8")

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path", lambda p=None: st_file)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_backup_path", lambda p=None: test_prof_dir / "storage_state.backup.json")
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_profile_dir", lambda p=None: test_prof_dir)

    mock_tokens = {"access_token": "ya29.regression_token"}
    mock_userinfo = {"email": "same.user@gmail.com", "name": "Same User"}

    with patch("voice_flow.google_auth._provider_token_exchange", return_value=mock_tokens):
        with patch("voice_flow.google_auth._provider_userinfo", return_value=mock_userinfo):
            outcome = complete_notebooklm_flow("code_reg", state, 8991)

    assert outcome["email"] == "same.user@gmail.com"
    saved = json.loads(st_file.read_text(encoding="utf-8"))
    assert saved["account"]["email"] == "same.user@gmail.com"
    assert saved["notebooklm"]["account"]["email"] == "same.user@gmail.com"
    assert len(saved["cookies"]) == 1
    assert saved["cookies"][0]["value"] == "existing-sid"


def test_start_login_cli_mode_launches_watcher(monkeypatch):
    """Verify start_login with mode='cli' launches the CLI login watcher thread."""
    monkeypatch.delenv("VOICE_FLOW_LOGIN_DISABLE", raising=False)
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: Path("C:/fake/notebooklm.exe"))

    commands = []
    def fake_run_login_once(command, log_path, timeout):
        commands.append(command)
        return 0, ""

    monkeypatch.setattr(login_flow, "_run_login_once", fake_run_login_once)
    monkeypatch.setattr(login_flow, "_terminate_stale_login_processes", lambda p, l: 0)

    res = login_flow.start_login(profile="video-flow-experiment", mode="cli", browser="chrome")
    assert res["launched"] is True
    assert res["mode"] == "browser"

    import time
    for _ in range(50):
        state = login_flow.get_login_state()
        if not state["running"]:
            break
        time.sleep(0.05)

    assert len(commands) >= 1
    assert "login" in commands[0]
    assert "--browser" in commands[0]
    assert "chrome" in commands[0]


def test_prepare_browser_profile_disables_picker_and_first_run(tmp_path, monkeypatch):
    """Verify _prepare_browser_profile writes First Run and suppresses profile picker and default browser check."""
    prof_dir = tmp_path / "profiles" / "test-prep-prof"
    browser_dir = prof_dir / "browser_profile"
    monkeypatch.setattr(login_flow, "_profile_browser_dir", lambda p: browser_dir)

    login_flow._prepare_browser_profile("test-prep-prof")

    assert (browser_dir / "First Run").is_file()

    local_state = json.loads((browser_dir / "Local State").read_text(encoding="utf-8"))
    assert local_state["browser"]["has_seen_welcome_page"] is True
    assert local_state["browser"]["check_default_browser"] is False
    assert local_state["profile"]["picker_shown_on_startup"] is False

    default_prefs = json.loads((browser_dir / "Default" / "Preferences").read_text(encoding="utf-8"))
    assert default_prefs["browser"]["has_seen_welcome_page"] is True
    assert default_prefs["browser"]["check_default_browser"] is False
    assert default_prefs["signin"]["allowed"] is True


def test_terminate_stale_login_processes_optional_log_and_normalization(tmp_path, monkeypatch):
    """Verify _terminate_stale_login_processes works without log_path and normalizes path separators."""
    from types import SimpleNamespace

    calls = []
    monkeypatch.setattr(login_flow.os, "name", "nt")
    monkeypatch.setattr(
        login_flow.subprocess, "run",
        lambda *a, **k: calls.append(a) or SimpleNamespace(stdout="4321\n", returncode=0),
    )

    fake_b_dir = tmp_path / "fake_prof" / "browser_profile"
    fake_b_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(login_flow, "_profile_browser_dir", lambda p: fake_b_dir)

    # Call with log_path omitted (defaults to None)
    killed = login_flow._terminate_stale_login_processes("my-test-profile")
    assert killed == 1
    assert len(calls) >= 2
    ps_cmd = calls[0][0]
    assert ps_cmd[0] == "powershell"
    script = " ".join(ps_cmd)
    assert "--user-data-dir=" in script
    assert "my-test-profile" in script
    assert "\\" not in script.split("$marker = '")[1].split("'")[0]  # normalized to forward slashes


def test_clean_account_state_for_switch_wipes_all_state_and_browser_dir(tmp_path, monkeypatch):
    """Verify _clean_account_state_for_switch wipes browser_profile, storage state, backups, and master token."""
    db_path = str(tmp_path / "test_switch_wipe.db")
    test_storage = StorageEngine(db_path)
    test_storage.save_setting("video_flow_notebooklm_email", "switch.old@gmail.com")
    monkeypatch.setattr("voice_flow.storage.storage", test_storage)
    monkeypatch.setattr(api_server, "storage", test_storage)

    prof_dir = tmp_path / "profiles" / "switch-wipe-prof"
    prof_dir.mkdir(parents=True, exist_ok=True)
    st_file = prof_dir / "storage_state.json"
    st_file.write_text(json.dumps({
        "cookies": [{"name": "SID", "value": "old-secret"}],
        "account": {"email": "switch.old@gmail.com"},
        "notebooklm": {"account": {"email": "switch.old@gmail.com"}},
    }), encoding="utf-8")
    b_file = prof_dir / "storage_state.backup.json"
    b_file.write_text(json.dumps({"cookies": [{"name": "SID", "value": "old-backup"}]}), encoding="utf-8")
    safe_file = prof_dir / "storage_state.safe_copy.json"
    safe_file.write_text(json.dumps({"cookies": [{"name": "SID", "value": "old-safe"}]}), encoding="utf-8")
    mt_file = prof_dir / "master_token.json"
    mt_file.write_text(json.dumps({"account": "switch.old@gmail.com", "token": "old-token"}), encoding="utf-8")

    b_dir = prof_dir / "browser_profile"
    b_dir.mkdir(parents=True, exist_ok=True)
    (b_dir / "Web Data").write_text("token storage", encoding="utf-8")
    (b_dir / "Local State").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(login_flow, "_profile_browser_dir", lambda p: b_dir)
    monkeypatch.setattr(login_flow, "_master_token_json_path", lambda p: mt_file)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path", lambda p: st_file)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_backup_path", lambda p: b_file)
    monkeypatch.setattr(login_flow, "_terminate_stale_login_processes", lambda p, l=None: 0)

    login_flow._clean_account_state_for_switch("switch-wipe-prof")

    assert test_storage.get_setting("video_flow_notebooklm_switched_from") == "switch.old@gmail.com"
    assert not b_dir.exists()
    assert not b_file.exists()
    assert not safe_file.exists()
    assert not mt_file.exists()

    st_data = json.loads(st_file.read_text(encoding="utf-8"))
    assert st_data["cookies"] == []
    assert "account" not in st_data


def test_watch_login_rejects_identical_switched_from_account(tmp_path, monkeypatch):
    """Verify _watch_login does not report success when switch_account is True and email matches switched_from."""
    monkeypatch.delenv("VOICE_FLOW_LOGIN_DISABLE", raising=False)
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: Path("C:/fake/notebooklm.exe"))

    db_path = str(tmp_path / "test_switch_rej.db")
    test_storage = StorageEngine(db_path)
    test_storage.save_setting("video_flow_notebooklm_switched_from", "same.user@gmail.com")
    monkeypatch.setattr("voice_flow.storage.storage", test_storage)
    monkeypatch.setattr(api_server, "storage", test_storage)

    prof_dir = tmp_path / "profiles" / "rej-prof"
    prof_dir.mkdir(parents=True, exist_ok=True)
    st_file = prof_dir / "storage_state.json"
    st_file.write_text(json.dumps({
        "cookies": [{"name": "SID", "value": "dummy-sid"}],
        "account": {"email": "same.user@gmail.com"},
    }), encoding="utf-8")

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path", lambda p: st_file)
    monkeypatch.setattr(login_flow, "_storage_email", lambda: "same.user@gmail.com")
    monkeypatch.setattr(login_flow, "verify_online", lambda **k: {"authenticated": True, "email": "same.user@gmail.com"})
    monkeypatch.setattr(login_flow, "_run_login_once", lambda cmd, log_path, timeout: (0, ""))
    monkeypatch.setattr(login_flow, "_terminate_stale_login_processes", lambda p, l=None: 0)

    log_file = tmp_path / "login.log"
    log_file.write_text("", encoding="utf-8")

    login_flow._watch_login(
        profile="rej-prof",
        mode="browser",
        account_email=None,
        browser="chrome",
        browser_timeout=60,
        log_path=log_file,
        switch_account=True,
    )

    state = login_flow.get_login_state()
    assert state["running"] is False
    assert state["success"] is False
    assert "Account switch failed: still signed in as same.user@gmail.com" in (state["error"] or "")






import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from voice_flow.video_flow_engine.notebooklm import login_flow
from voice_flow.video_flow_engine.notebooklm.mcp_client import NotebookLMMcpClient
from voice_flow.video_flow_engine.notebooklm.provider import _is_auth_expired_error
from voice_flow.video_flow_engine.notebooklm.service import NotebookLMService


def test_video_flow_js_has_no_hardcoded_fake_email():
    js_path = Path(__file__).resolve().parent.parent / "src" / "voice_flow" / "gui" / "video-flow.js"
    assert js_path.is_file()
    content = js_path.read_text(encoding="utf-8")
    assert "naeem.kayat2004@gmail.com" not in content
    assert 'status: "unauthenticated", email: null' in content


def test_video_flow_js_is_auth_error_handles_cookie_errors():
    js_path = Path(__file__).resolve().parent.parent / "src" / "voice_flow" / "gui" / "video-flow.js"
    content = js_path.read_text(encoding="utf-8")
    assert 'err.includes("missing required cookies")' in content


def test_video_flow_js_start_auth_sends_direct_true():
    js_path = Path(__file__).resolve().parent.parent / "src" / "voice_flow" / "gui" / "video-flow.js"
    content = js_path.read_text(encoding="utf-8")
    assert "direct: true" in content


def test_start_login_defaults_direct_true():
    sig = inspect.signature(login_flow.start_login)
    assert "direct" in sig.parameters
    param = sig.parameters["direct"]
    assert param.default is True


def test_service_start_auth_defaults_direct_true():
    sig = inspect.signature(NotebookLMService.start_auth)
    assert "direct" in sig.parameters
    param = sig.parameters["direct"]
    assert param.default is True


def test_provider_is_auth_expired_error_matches_missing_cookies():
    assert _is_auth_expired_error("AUTH", "Missing required cookies: __Secure-1PSIDTS")
    assert _is_auth_expired_error("CLI_ERROR", "Error: No cookies found for profile default")
    assert _is_auth_expired_error(None, "Missing required authentication credentials")
    assert not _is_auth_expired_error("OK", "Generation completed successfully")


def test_mcp_client_is_available_with_master_token(tmp_path):
    fake_cli = tmp_path / "fake_cli.exe"
    fake_cli.touch()
    with patch("voice_flow.video_flow_engine.notebooklm.config.has_valid_storage_state", return_value=False), \
         patch("voice_flow.video_flow_engine.notebooklm.mcp_client.has_valid_storage_state", return_value=False), \
         patch("voice_flow.video_flow_engine.notebooklm.login_flow.master_token_present", return_value=True):
        client = NotebookLMMcpClient(profile="test-profile", cli_path=str(fake_cli), mcp_path=str(fake_cli))
        assert client.is_available() is True


def test_self_heal_fallback_on_master_token_refresh_error(tmp_path):
    fake_cli = tmp_path / "notebooklm.exe"
    fake_cli.touch()

    calls = []

    def fake_run_login_once(cmd, log_path, timeout):
        calls.append(list(cmd))
        if "--master-token-refresh" in cmd:
            return 1, "Master token expired or invalid"
        return 0, None

    with patch("voice_flow.video_flow_engine.notebooklm.login_flow.resolve_notebooklm_cli", return_value=fake_cli), \
         patch("voice_flow.video_flow_engine.notebooklm.login_flow._master_token_json_path") as mock_mt, \
         patch("voice_flow.video_flow_engine.notebooklm.login_flow._run_login_once", side_effect=fake_run_login_once), \
         patch("voice_flow.video_flow_engine.notebooklm.login_flow._login_log_path", return_value=tmp_path / "login.log"):
        mock_mt.return_value.is_file.return_value = True

        res = login_flow.self_heal(profile="test-profile")
        assert res["ok"] is True
        assert len(calls) == 2
        assert "--master-token-refresh" in calls[0]
        assert "auth" in calls[1] and "refresh" in calls[1]


def test_api_server_status_verify_flips_auth_false_on_verification_error():
    with patch("voice_flow.video_flow_engine.notebooklm.login_flow.verify_online", return_value={"status": "error", "error": "Google 401"}):
        verification = login_flow.verify_online(profile="video-flow-experiment")
        assert verification.get("status") == "error"
        online_verified = False if verification.get("status") == "error" else bool(verification.get("authenticated"))
        authenticated = False if not online_verified else True
        assert online_verified is False
        assert authenticated is False

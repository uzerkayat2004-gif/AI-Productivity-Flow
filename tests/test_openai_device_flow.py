"""Tests for OpenAI Codex / ChatGPT Device Authorization Flow.

Validates:
- start_openai_device_flow()
- poll_openai_device_flow()
- video_flow_provider_service.start_oauth("openai_codex")
- video_flow_provider_service.poll_device_flow("openai_codex")
- API Server endpoints /api/video-flow/oauth/start and /api/video-flow/oauth/device-poll
"""

import io
import json
import os
import urllib.error
from unittest.mock import MagicMock, patch
import pytest

from voice_flow.video_flow_oauth import (
    OAuthError,
    OPENAI_DEVICE_CLIENT_ID,
    OPENAI_DEVICE_USERCODE_URL,
    OPENAI_DEVICE_TOKEN_URL,
    OPENAI_DEVICE_OAUTH_TOKEN_URL,
    OPENAI_DEVICE_VERIFICATION_URL,
    start_openai_device_flow,
    poll_openai_device_flow,
    refresh_connection_tokens,
)
from voice_flow.video_flow_providers import video_flow_provider_service
from voice_flow.gui.api_server import VoiceFlowApiHandler


class MockHTTPResponse:
    def __init__(self, data: dict, status: int = 200):
        self._content = json.dumps(data).encode("utf-8")
        self.status = status

    def read(self):
        return self._content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockApiHandler(VoiceFlowApiHandler):
    def __init__(self, path: str, body: dict):
        encoded = json.dumps(body).encode("utf-8")
        self.path = path
        self.headers = {
            "Host": "127.0.0.1:8991",
            "Content-Type": "application/json",
            "Content-Length": str(len(encoded)),
        }
        self.rfile = io.BytesIO(encoded)
        self.wfile = io.BytesIO()
        self.status_code = 0
        self.resp_headers = {}

    def send_response(self, code):
        self.status_code = code

    def send_header(self, k, v):
        self.resp_headers[k] = v

    def end_headers(self):
        pass

    def _server_port(self):
        return 8991


def test_start_openai_device_flow_success():
    mock_resp = MockHTTPResponse({
        "user_code": "WDJB-MJTF",
        "device_auth_id": "devauth_123456",
        "interval": 5,
    })
    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        res = start_openai_device_flow()
        assert res["flow"] == "device"
        assert res["user_code"] == "WDJB-MJTF"
        assert res["device_auth_id"] == "devauth_123456"
        assert res["verification_url"] == OPENAI_DEVICE_VERIFICATION_URL
        assert res["interval"] == 5
        assert res["expires_in"] == 900

        # Verify request parameters
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert req.full_url == OPENAI_DEVICE_USERCODE_URL
        body = json.loads(req.data.decode("utf-8"))
        assert body["client_id"] == OPENAI_DEVICE_CLIENT_ID


def test_start_openai_device_flow_custom_client():
    mock_resp = MockHTTPResponse({
        "user_code": "CUSTOM-CODE",
        "device_auth_id": "devauth_custom",
        "interval": 10,
    })
    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        res = start_openai_device_flow(client_id="my_custom_client")
        assert res["user_code"] == "CUSTOM-CODE"
        assert res["interval"] == 10
        call_args = mock_urlopen.call_args
        body = json.loads(call_args[0][0].data.decode("utf-8"))
        assert body["client_id"] == "my_custom_client"


def test_start_openai_device_flow_missing_fields_raises_oauth_error():
    mock_resp = MockHTTPResponse({"user_code": "WDJB-MJTF"})  # missing device_auth_id
    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(OAuthError, match="missing user_code or device_auth_id"):
            start_openai_device_flow()


def test_start_openai_device_flow_http_failure_raises_oauth_error():
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        with pytest.raises(OAuthError, match="Failed to initiate OpenAI device authorization"):
            start_openai_device_flow()


def test_poll_openai_device_flow_pending_on_http_403_404():
    err_403 = urllib.error.HTTPError("http://example.com", 403, "Forbidden", {}, None)
    with patch("urllib.request.urlopen", side_effect=err_403):
        res = poll_openai_device_flow("devauth_123", "CODE-123")
        assert res == {"status": "pending"}

    err_404 = urllib.error.HTTPError("http://example.com", 404, "Not Found", {}, None)
    with patch("urllib.request.urlopen", side_effect=err_404):
        res = poll_openai_device_flow("devauth_123", "CODE-123")
        assert res == {"status": "pending"}


def test_poll_openai_device_flow_pending_when_code_not_ready():
    mock_resp = MockHTTPResponse({"status": "waiting"})  # missing authorization_code
    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = poll_openai_device_flow("devauth_123", "CODE-123")
        assert res == {"status": "pending"}


def test_poll_openai_device_flow_approved_exchanges_token():
    device_resp = MockHTTPResponse({
        "authorization_code": "auth_code_xyz",
        "code_verifier": "verifier_abc",
    })
    # Payload with email in JWT
    dummy_jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiAiMSIsICJlbWFpbCI6ICJ1c2VyQGNoYXRncHQuY29tIn0.sig"
    oauth_resp = MockHTTPResponse({
        "access_token": dummy_jwt,
        "refresh_token": "refresh_xyz_123",
        "expires_in": 3600,
        "token_type": "Bearer",
    })

    with patch("urllib.request.urlopen", side_effect=[device_resp, oauth_resp]):
        res = poll_openai_device_flow("devauth_123", "CODE-123")
        assert res["status"] == "approved"
        assert res["access_token"] == dummy_jwt
        assert res["refresh_token"] == "refresh_xyz_123"
        assert res["account_id"] == "user@chatgpt.com"
        assert res["token_type"] == "Bearer"
        assert int(res["expires_at"]) > 0


def test_poll_openai_device_flow_error_reporting():
    fp = io.BytesIO(b'{"error": {"message": "Invalid code expired"}}')
    err_400 = urllib.error.HTTPError("http://example.com", 400, "Bad Request", {}, fp)
    with patch("urllib.request.urlopen", side_effect=err_400):
        res = poll_openai_device_flow("devauth_123", "CODE-123")
        assert res["status"] == "error"
        assert "Invalid code expired" in res["error"]


def test_video_flow_provider_service_start_oauth_openai_codex():
    os.environ["VOICE_FLOW_NO_BROWSER_POPUP"] = "1"
    mock_device = {
        "flow": "device",
        "user_code": "S65Q-4VO2H",
        "device_auth_id": "dev_test_id",
        "verification_url": "https://auth.openai.com/codex/device",
        "interval": 5,
        "expires_in": 900,
    }
    try:
        with patch("voice_flow.video_flow_oauth.start_openai_device_flow", return_value=mock_device):
            res = video_flow_provider_service.start_oauth("openai_codex")
            assert res["success"] is True
            assert res["flow"] == "device"
            assert res["user_code"] == "S65Q-4VO2H"
            assert res["device_auth_id"] == "dev_test_id"
            assert res["verification_url"] == "https://auth.openai.com/codex/device"
            assert res["interval"] == 5
            assert res["opened"] is False
    finally:
        os.environ.pop("VOICE_FLOW_NO_BROWSER_POPUP", None)


def test_video_flow_provider_service_poll_device_flow_approved():
    approved_payload = {
        "status": "approved",
        "access_token": "token_device_abc",
        "refresh_token": "refresh_device_xyz",
        "account_id": "device_user@openai.com",
        "expires_at": "1800000000",
    }
    with patch("voice_flow.video_flow_oauth.poll_openai_device_flow", return_value=approved_payload):
        res = video_flow_provider_service.poll_device_flow(
            "openai_codex",
            device_auth_id="dev_123",
            user_code="USER-CODE",
        )
        assert res["status"] == "approved"
        assert res["account"] == "device_user@openai.com"
        assert "connection" in res
        conn = res["connection"]
        assert conn["account_id"] == "device_user@openai.com"
        assert conn["provider"] == "openai_codex"


def test_video_flow_provider_service_poll_device_flow_unsupported_provider():
    res = video_flow_provider_service.poll_device_flow("unsupported_provider")
    assert res["status"] == "error"
    assert "not supported" in res["error"]


def test_api_handler_device_poll_endpoint():
    approved_result = {
        "status": "approved",
        "account": "test_subscriber@openai.com",
        "connection": {"id": 999, "status": "active"},
    }
    with patch.object(video_flow_provider_service, "poll_device_flow", return_value=approved_result):
        handler = MockApiHandler(
            "/api/video-flow/oauth/device-poll",
            {"provider": "openai_codex", "device_auth_id": "dev_id", "user_code": "CODE-1"},
        )
        handler.do_POST()
        assert handler.status_code == 200
        data = json.loads(handler.wfile.getvalue().decode("utf-8"))
        assert data["success"] is True
        assert data["status"] == "approved"
        assert data["account"] == "test_subscriber@openai.com"


def test_api_handler_device_poll_missing_provider():
    handler = MockApiHandler(
        "/api/video-flow/oauth/device-poll",
        {"device_auth_id": "dev_id", "user_code": "CODE-1"},
    )
    handler.do_POST()
    assert handler.status_code == 400
    data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert data["success"] is False
    assert "provider is required" in data["error"]


def test_api_handler_start_oauth_device_flow():
    device_start = {
        "success": True,
        "flow": "device",
        "user_code": "CODE-999",
        "device_auth_id": "dev_999",
        "verification_url": "https://auth.openai.com/codex/device",
        "interval": 5,
        "expires_in": 900,
    }
    with patch.object(video_flow_provider_service, "start_oauth", return_value=device_start):
        handler = MockApiHandler(
            "/api/video-flow/oauth/start",
            {"provider": "openai_codex"},
        )
        handler.do_POST()
        assert handler.status_code == 200
        data = json.loads(handler.wfile.getvalue().decode("utf-8"))
        assert data["success"] is True
        assert data["flow"] == "device"
        assert data["user_code"] == "CODE-999"


def test_poll_openai_device_flow_pending_on_http_400_authorization_pending():
    fp = io.BytesIO(b'{"error": "authorization_pending"}')
    err_400 = urllib.error.HTTPError("http://example.com", 400, "Bad Request", {}, fp)
    with patch("urllib.request.urlopen", side_effect=err_400):
        res = poll_openai_device_flow("devauth_123", "CODE-123")
        assert res == {"status": "pending"}


def test_poll_openai_device_flow_pending_on_response_body_error():
    mock_resp = MockHTTPResponse({"error": "authorization_pending"})
    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = poll_openai_device_flow("devauth_123", "CODE-123")
        assert res == {"status": "pending"}


def test_poll_openai_device_flow_extracts_email_from_id_token():
    device_resp = MockHTTPResponse({
        "authorization_code": "auth_code_123",
        "code_verifier": "verifier_123",
    })
    # id_token has email claim, access_token is opaque
    dummy_id_token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiAiNDU2IiwgImVtYWlsIjogImlkX3Rva2VuX3VzZXJAZXhhbXBsZS5jb20ifQ.sig"
    oauth_resp = MockHTTPResponse({
        "access_token": "opaque_access_token_xyz",
        "id_token": dummy_id_token,
        "refresh_token": "refresh_123",
        "expires_in": 3600,
    })
    with patch("urllib.request.urlopen", side_effect=[device_resp, oauth_resp]):
        res = poll_openai_device_flow("devauth_123", "CODE-123")
        assert res["status"] == "approved"
        assert res["account_id"] == "id_token_user@example.com"
        assert res["access_token"] == "opaque_access_token_xyz"


def test_poll_openai_device_flow_generic_fallback_without_personal_email():
    device_resp = MockHTTPResponse({
        "authorization_code": "auth_code_123",
        "code_verifier": "verifier_123",
    })
    # Tokens with no email claims
    oauth_resp = MockHTTPResponse({
        "access_token": "opaque_access_token_xyz",
        "refresh_token": "refresh_123",
        "expires_in": 3600,
    })
    with patch("urllib.request.urlopen", side_effect=[device_resp, oauth_resp]):
        res = poll_openai_device_flow("devauth_123", "CODE-123")
        assert res["status"] == "approved"
        # Must not contain any hardcoded personal email address
        assert res["account_id"] == "ChatGPT Account"
        assert "naeemkayat" not in res["account_id"]


def test_refresh_connection_tokens_openai_codex_device_flow(tmp_path):
    from voice_flow.video_flow_providers import VideoFlowProviderService
    from voice_flow.video_flow_oauth import encrypt_token

    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    raw_conn = service.add_connection(
        "openai_codex",
        name="ChatGPT User",
        secret=encrypt_token(service, "old_access_token"),
        account_id="subscriber@openai.com",
        refresh_token=encrypt_token(service, "valid_refresh_token"),
        metadata={"source": "device_code"},
    )
    conn_full = service.get_connection(int(raw_conn["id"]), public=False)

    fake_refresh_resp = {
        "access_token": "new_refreshed_access_token",
        "refresh_token": "new_refreshed_refresh_token",
        "expires_in": 3600,
    }
    with patch("voice_flow.video_flow_oauth._http_json", return_value=fake_refresh_resp) as mock_http:
        refreshed = refresh_connection_tokens(service, conn_full)
        assert refreshed["access_token"] == "new_refreshed_access_token"
        assert refreshed["refresh_token"] == "new_refreshed_refresh_token"
        assert int(refreshed["expires_at"]) > 0

        # Verify call arguments target OpenAI OAuth token URL
        mock_http.assert_called_once()
        call_url = mock_http.call_args[0][0]
        call_data = mock_http.call_args[1]["data"]
        assert call_url == OPENAI_DEVICE_OAUTH_TOKEN_URL
        assert call_data["grant_type"] == "refresh_token"
        assert call_data["refresh_token"] == "valid_refresh_token"


def test_api_handler_device_poll_reports_failure_when_status_is_error():
    error_result = {
        "status": "error",
        "error": "Device authorization expired",
    }
    with patch.object(video_flow_provider_service, "poll_device_flow", return_value=error_result):
        handler = MockApiHandler(
            "/api/video-flow/oauth/device-poll",
            {"provider": "openai_codex", "device_auth_id": "dev_id", "user_code": "CODE-1"},
        )
        handler.do_POST()
        assert handler.status_code == 200
        data = json.loads(handler.wfile.getvalue().decode("utf-8"))
        assert data["success"] is False
        assert data["status"] == "error"
        assert "Device authorization expired" in data["error"]

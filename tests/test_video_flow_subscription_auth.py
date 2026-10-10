"""Test suite verifying Video Flow subscription authentication providers (Antigravity & ChatGPT/OpenAI)."""

import io
import json
import os
import time
import pytest
from pathlib import Path
from voice_flow.video_flow_oauth import (
    launch_system_browser,
    oauth_config,
    start_pkce_flow,
    complete_pkce_flow,
    import_cli_session,
    _extract_jwt_claim,
)
from voice_flow.video_flow_providers import VideoFlowProviderService, video_flow_provider_service
from voice_flow.video_flow_service import _PLANNING_ENDPOINTS
from voice_flow.gui.api_server import VoiceFlowApiHandler


def test_launch_system_browser_with_empty_url():
    assert launch_system_browser("") is False


def test_extract_jwt_claim():
    dummy_jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiAiMTIzIiwgImVtYWlsIjogInRlc3RAZXhhbXBsZS5jb20ifQ.sig"
    assert _extract_jwt_claim(dummy_jwt, "email") == "test@example.com"
    assert _extract_jwt_claim("invalid.jwt", "email") == ""


def test_oauth_config_openai_codex_and_antigravity():
    anti_cfg = oauth_config("antigravity")
    assert anti_cfg.flow == "pkce"
    assert "https://accounts.google.com" in anti_cfg.auth_url
    assert "1071006060591" in anti_cfg.client_id

    codex_cfg = oauth_config("openai_codex")
    assert codex_cfg.flow == "hybrid"
    assert codex_cfg.pkce is True
    assert "~/.codex/auth.json" in codex_cfg.cli_files


def test_antigravity_start_oauth_generates_google_consent_url(tmp_path):
    os.environ["VOICE_FLOW_NO_BROWSER_POPUP"] = "1"
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    try:
        res = service.start_oauth("antigravity")
        assert res["success"] is True
        assert res["flow"] == "web"
        assert "accounts.google.com" in res["authUrl"]
        assert "prompt=select_account+consent" in res["authUrl"]
        assert "http%3A%2F%2F127.0.0.1%3A8991%2Fcallback" in res["authUrl"]
    finally:
        os.environ.pop("VOICE_FLOW_NO_BROWSER_POPUP", None)


from unittest.mock import patch


def test_openai_codex_start_oauth_device_flow(tmp_path):
    os.environ["VOICE_FLOW_NO_BROWSER_POPUP"] = "1"
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    mock_dev = {
        "flow": "device",
        "user_code": "WDJB-MJTF",
        "device_auth_id": "devauth_test_123",
        "verification_url": "https://auth.openai.com/codex/device",
        "interval": 5,
        "expires_in": 900,
    }
    try:
        with patch("voice_flow.video_flow_oauth.start_openai_device_flow", return_value=mock_dev):
            res = service.start_oauth("openai_codex")
            assert res["success"] is True
            assert res["flow"] == "device"
            assert res["user_code"] == "WDJB-MJTF"
            assert res["device_auth_id"] == "devauth_test_123"
            assert "auth.openai.com" in res["verification_url"]
    finally:
        os.environ.pop("VOICE_FLOW_NO_BROWSER_POPUP", None)


def test_openai_codex_start_oauth_imports_active_session(tmp_path):
    os.environ["VOICE_FLOW_NO_BROWSER_POPUP"] = "1"
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    fake_session = {
        "access_token": "imported_access_token_xyz",
        "refresh_token": "imported_refresh_token_xyz",
        "account_id": "cli_subscriber@openai.com",
        "email": "cli_subscriber@openai.com",
        "chatgpt_account_id": "acc-cli-123",
        "chatgpt_plan_type": "plus",
        "source": "cli_session",
    }
    try:
        with patch("voice_flow.video_flow_oauth.start_openai_device_flow", side_effect=Exception("network offline")), \
             patch("voice_flow.video_flow_oauth.import_cli_session", return_value=fake_session):
            res = service.start_oauth("openai_codex")
            assert res["success"] is True
            assert res["flow"] == "cli"
            assert res["imported"] is True
            assert "cli_subscriber@openai.com" in res.get("account", "")
            active = [c for c in service.list_connections("openai_codex") if c["is_active"]]
            assert len(active) > 0
            latest = active[-1]
            assert latest["status"] == "active"
            assert latest["account_id"] == "cli_subscriber@openai.com"
            test_res = service.test_connection(int(latest["id"]))
            assert test_res["success"] is True
            assert test_res["status"] == "active"
    finally:
        os.environ.pop("VOICE_FLOW_NO_BROWSER_POPUP", None)


def test_resolve_connection_secret_recovers_masked_dictionary(tmp_path):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    service.add_connection("antigravity", name="Antigravity Test", secret="ya29.test_token_secret_1234567890")
    active = [c for c in service.list_connections("antigravity") if c["is_active"]]
    assert len(active) > 0
    masked = active[0]
    assert "secret" not in masked
    secret = service.resolve_connection_secret(masked)
    assert len(secret) > 20
    assert secret.startswith("ya29.")


def test_video_flow_service_planning_endpoints_has_codex():
    assert "openai_codex" in _PLANNING_ENDPOINTS
    assert _PLANNING_ENDPOINTS["openai_codex"] == "https://chatgpt.com/backend-api/codex/responses"
    assert "codex" in _PLANNING_ENDPOINTS
    assert _PLANNING_ENDPOINTS["codex"] == "https://chatgpt.com/backend-api/codex/responses"


class DummyHandler(VoiceFlowApiHandler):
    def __init__(self, path, body):
        self.path = path
        self.headers = {'Host': '127.0.0.1:8991', 'Content-Type': 'application/json', 'Content-Length': str(len(body))}
        self.rfile = io.BytesIO(body.encode('utf-8'))
        self.wfile = io.BytesIO()
        self.status = 0
        self.resp_headers = {}
    def send_response(self, code):
        self.status = code
    def send_header(self, k, v):
        self.resp_headers[k] = v
    def end_headers(self):
        pass
    def _server_port(self):
        return 8991


def test_api_server_model_test_endpoint_for_subscriptions(monkeypatch, tmp_path):
    test_service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    test_service.add_connection(
        "openai_codex",
        name="ChatGPT Test",
        account_id="subscriber@openai.com",
        secret="dummy_token",
        metadata={"chatgpt_account_id": "acc-12345", "chatgpt_plan_type": "plus"}
    )
    import voice_flow.gui.api_server as api_server
    monkeypatch.setattr(api_server, "video_flow_provider_service", test_service)

    mock_usage = {
        "plan_type": "plus",
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": {"used_percent": 10, "reset_at": 1789189480}
        }
    }
    mock_models = {"models": [{"slug": "gpt-5.6-terra", "visibility": "list"}]}

    with patch("urllib.request.urlopen") as mock_urlopen:
        def fake_urlopen(req, timeout=10):
            url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
            class FakeResp:
                def read(self):
                    if "wham/usage" in url:
                        return json.dumps(mock_usage).encode("utf-8")
                    return json.dumps(mock_models).encode("utf-8")
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
            return FakeResp()
        mock_urlopen.side_effect = fake_urlopen

        # Test with codex alias and codex/ prefix
        h_codex = DummyHandler('/api/video-flow/providers/models/test', json.dumps({'provider': 'codex', 'model_id': 'codex/gpt-5.6-terra'}))
        h_codex.do_POST()
        data = json.loads(h_codex.wfile.getvalue().decode('utf-8'))
        assert data["success"] is True
        assert data["remaining_pct"] == 90
        assert "ChatGPT Plus subscription active" in data["message"]

    # Test when quota is reached
    mock_quota_reached = {
        "plan_type": "free",
        "rate_limit": {
            "allowed": False,
            "limit_reached": True,
            "primary_window": {"used_percent": 100, "reset_at": 1789189480}
        }
    }
    with patch("urllib.request.urlopen") as mock_urlopen:
        def fake_urlopen_exhausted(req, timeout=10):
            class FakeResp:
                def read(self):
                    if "wham/usage" in (req.full_url if hasattr(req, "full_url") else req.get_full_url()):
                        return json.dumps(mock_quota_reached).encode("utf-8")
                    return json.dumps(mock_models).encode("utf-8")
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
            return FakeResp()
        mock_urlopen.side_effect = fake_urlopen_exhausted

        h_free = DummyHandler('/api/providers/models/test', json.dumps({'provider': 'openai_codex', 'model_id': 'gpt-5.6-terra'}))
        h_free.do_POST()
        data_free = json.loads(h_free.wfile.getvalue().decode('utf-8'))
        assert data_free["success"] is False
        assert data_free["remaining_pct"] == 0
        assert "quota limit reached" in data_free["error"]


def test_extract_jwt_claim_dual_namespace_no_short_circuit():
    import base64
    payload = {
        "sub": "user_123",
        "https://api.openai.com/profile": {
            "email": "subscriber@openai.com",
            "chatgpt_account_id": "",
            "chatgpt_plan_type": "   ",
        },
        "https://api.openai.com/auth": {
            "chatgpt_account_id": "acc-real-456",
            "chatgpt_plan_type": "plus",
        },
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")
    dummy_jwt = f"eyJhbGciOiJIUzI1NiJ9.{encoded}.sig"

    assert _extract_jwt_claim(dummy_jwt, "chatgpt_account_id") == "acc-real-456"
    assert _extract_jwt_claim(dummy_jwt, "chatgpt_plan_type") == "plus"
    assert _extract_jwt_claim(dummy_jwt, "email") == "subscriber@openai.com"


def test_add_connection_and_model_with_codex_alias(tmp_path):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    conn = service.add_connection("codex", name="Codex User", secret="test_secret_123")
    assert conn["provider"] == "openai_codex"
    active = service.active_connections("openai_codex")
    assert len(active) == 1
    assert active[0]["provider"] == "openai_codex"

    model = service.add_model("codex", "codex/custom-model", "Custom Model", ["reasoning"])
    assert model["provider"] == "openai_codex"
    assert model["model_id"] == "custom-model"
    models = service.list_models("openai_codex")
    assert any(m["model_id"] == "custom-model" for m in models)


def test_api_server_model_test_invalid_model_lists_supported(monkeypatch, tmp_path):
    test_service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    test_service.add_connection("openai_codex", name="ChatGPT Test", secret="dummy_tok")
    import voice_flow.gui.api_server as api_server
    monkeypatch.setattr(api_server, "video_flow_provider_service", test_service)

    mock_usage = {
        "plan_type": "plus",
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": {"used_percent": 10, "reset_at": 1789189480}
        }
    }
    with patch("urllib.request.urlopen") as mock_urlopen:
        class FakeResp:
            def read(self):
                return json.dumps(mock_usage).encode("utf-8")
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        mock_urlopen.return_value = FakeResp()

        h = DummyHandler('/api/providers/models/test', json.dumps({'provider': 'openai_codex', 'model_id': 'gpt-unknown-fake'}))
        h.do_POST()
        data = json.loads(h.wfile.getvalue().decode('utf-8'))
        assert data["success"] is False
        assert "not available in the ChatGPT Codex distribution" in data["error"]
        assert "gpt-5.6-terra" in data["error"]


def test_codex_worker_sse_parsing():
    import http.server, subprocess, sys, threading
    from voice_flow.video_flow_service import _CODEX_WORKER

    class MockSSEHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b": ping\n\n")
            self.wfile.write(b"data: {\"type\": \"response.output_text.delta\", \"delta\": \"Hello \"}\n\n")
            self.wfile.write(b"data:{\"type\": \"response.output_text.delta\", \"delta\": \"world!\"}\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        def log_message(self, *args): pass

    server = http.server.HTTPServer(("127.0.0.1", 0), MockSSEHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    port = server.server_address[1]

    payload = {
        "api_key": "test_tok",
        "endpoint": f"http://127.0.0.1:{port}/responses",
        "model": "gpt-5.6-terra",
        "prompt": "Say hi",
        "account_id": "acc-123",
    }
    proc = subprocess.Popen(
        [sys.executable, "-c", _CODEX_WORKER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8"
    )
    out, _ = proc.communicate(json.dumps(payload), timeout=25)
    server.shutdown()
    server.server_close()

    assert proc.returncode == 0
    data = json.loads(out)
    assert data["ok"] is True
    assert data["content"] == "Hello world!"


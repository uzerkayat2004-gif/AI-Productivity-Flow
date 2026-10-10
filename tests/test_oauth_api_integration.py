import json
import threading
import time
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import pytest
from voice_flow.gui import api_server
from voice_flow.storage import StorageEngine


def test_oauth_api_start_and_complete_endpoints(monkeypatch, tmp_path):
    db_path = str(tmp_path / "voice_flow_oauth_test.db")
    test_storage = StorageEngine(db_path)
    monkeypatch.setattr(api_server, "storage", test_storage)

    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    server.daemon_threads = True
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.15)
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. Test GET /api/providers/oauth/start?provider=antigravity
        req_start = urllib.request.Request(f"{base_url}/api/providers/oauth/start?provider=antigravity", headers={"Connection": "close"})
        with urllib.request.urlopen(req_start, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert "auth_url" in data
            assert "accounts.google.com" in data["auth_url"]
            state = data["state"]
            assert state is not None

        # 2. Test POST /api/providers/oauth/complete with mock token exchange
        with patch("voice_flow.video_flow_oauth._http_json") as mock_http:
            mock_http.return_value = {
                "access_token": "ya29.live_user_access_token_abc",
                "refresh_token": "1//refresh_token_xyz",
                "expires_in": 3600,
                "id_token": "eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6Im5hZWVtLmtheWF0MjAwNEBnbWFpbC5jb20ifQ.sig",
            }

            payload = json.dumps({
                "provider": "antigravity",
                "code": "4/test_code_12345",
                "state": state,
            }).encode("utf-8")

            req_comp = urllib.request.Request(
                f"{base_url}/api/providers/oauth/complete",
                data=payload,
                headers={"Content-Type": "application/json", "Connection": "close"},
            )
            with urllib.request.urlopen(req_comp, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                assert data["success"] is True
                assert data["email"] == "naeem.kayat2004@gmail.com"

        # 3. Test POST /api/providers/oauth/complete with full pasted callback URL
        with patch("voice_flow.video_flow_oauth._http_json") as mock_http:
            mock_http.return_value = {
                "access_token": "ya29.live_user_access_token_second",
                "expires_in": 3600,
                "id_token": "eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6InJlaGFuYWtheWF0MkBnbWFpbC5jb20ifQ.sig",
            }

            pasted_url = f"http://localhost:8991/?code=4/second_code_678&state={state}"
            payload_url = json.dumps({
                "provider": "antigravity",
                "callback_url": pasted_url,
            }).encode("utf-8")

            req_comp_url = urllib.request.Request(
                f"{base_url}/api/providers/oauth/complete",
                data=payload_url,
                headers={"Content-Type": "application/json", "Connection": "close"},
            )
            with urllib.request.urlopen(req_comp_url, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                assert data["success"] is True
                assert data["email"] == "rehanakayat2@gmail.com"

        # 4. Verify both connections exist in storage
        conns = test_storage.get_provider_connections("antigravity")
        assert len(conns) == 2
        emails = {c["email"] for c in conns}
        assert "naeem.kayat2004@gmail.com" in emails
        assert "rehanakayat2@gmail.com" in emails

    finally:
        server.shutdown()
        server.server_close()

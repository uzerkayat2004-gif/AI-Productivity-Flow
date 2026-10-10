"""Tests for the 9Router-style Video Flow OAuth API.

Covers /api/video-flow/oauth/authorize + /api/video-flow/oauth/exchange
(client_secret Google flow, NO PKCE for antigravity) and proves the old
/api/video-flow/providers/oauth/* endpoints stay deleted. Google sign-in is
covered separately in tests/test_google_auth.py.
"""

from __future__ import annotations

import base64
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import voice_flow.video_flow_oauth as oauth_module
from voice_flow.gui import api_server
from voice_flow.storage import StorageEngine
from voice_flow.video_flow_providers import VideoFlowProviderService
from voice_flow.video_flow_oauth import ANTIGRAVITY_CLIENT_ID, ANTIGRAVITY_CLIENT_SECRET


@pytest.fixture
def oauth_server(monkeypatch, tmp_path):
    db_path = str(tmp_path / "voice_flow_oauth_api_test.db")
    test_storage = StorageEngine(db_path)
    test_service = VideoFlowProviderService(str(tmp_path / "video_flow_providers.db"))
    monkeypatch.setattr(api_server, "storage", test_storage)
    monkeypatch.setattr(api_server, "video_flow_provider_service", test_service)

    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.15)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    yield {"base_url": base_url, "storage": test_storage, "service": test_service}

    server.shutdown()
    server.server_close()


def _get(url: str):
    req = urllib.request.Request(url, headers={"Connection": "close"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _post(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", "Connection": "close"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_authorize_builds_reference_antigravity_url_and_pending_session(oauth_server):
    base = oauth_server["base_url"]
    status, body = _get(base + "/api/video-flow/oauth/authorize?provider=antigravity&redirect_uri=http://127.0.0.1:8991/callback")

    assert status == 200
    assert body["success"] is True
    assert body["redirectUri"] == "http://127.0.0.1:8991/callback"
    params = {
        key: values[0]
        for key, values in urllib.parse.parse_qs(urllib.parse.urlparse(body["authUrl"]).query).items()
    }
    assert body["authUrl"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    # The reference Antigravity client — 9Router parity.
    assert params["client_id"] == ANTIGRAVITY_CLIENT_ID
    assert params["response_type"] == "code"
    assert params["redirect_uri"] == "http://127.0.0.1:8991/callback"
    assert params["access_type"] == "offline"
    assert params["prompt"] == "select_account consent"
    # Client-secret flow: the reference client sends NO PKCE challenge.
    assert "code_challenge" not in params
    assert "code_challenge_method" not in params
    for scope in (
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/cclog",
        "https://www.googleapis.com/auth/experimentsandconfigs",
    ):
        assert scope in params["scope"]
    # state = 32 url-safe random bytes.
    assert len(base64.urlsafe_b64decode(body["state"] + "=" * (-len(body["state"]) % 4))) == 32
    pending = oauth_server["service"].get_setting("oauth_pending:antigravity", None)
    assert pending["state"] == body["state"]
    assert pending["redirect_uri"] == "http://127.0.0.1:8991/callback"
    assert pending["provider"] == "antigravity"


def test_exchange_rejects_wrong_state(oauth_server):
    base = oauth_server["base_url"]
    status, body = _post(base + "/api/video-flow/oauth/exchange", {
        "provider": "antigravity", "code": "4/code", "state": "wrong-state",
    })
    assert status == 400
    assert body["success"] is False
    assert "state mismatch" in body["error"]


def test_exchange_stores_active_connection_like_9router(oauth_server, monkeypatch):
    base = oauth_server["base_url"]
    service = oauth_server["service"]

    _, auth = _get(base + "/api/video-flow/oauth/authorize?provider=antigravity&redirect_uri=http://127.0.0.1:8991/callback")
    state = auth["state"]

    calls: list[dict] = []

    def fake_http_json(url, *, data=None, headers=None, timeout=15.0):
        calls.append({"url": url, "data": data, "headers": headers})
        if url.startswith("https://oauth2.googleapis.com/token"):
            return {"access_token": "at-live", "refresh_token": "rt-live", "expires_in": 3600}
        assert url.startswith("https://www.googleapis.com/oauth2/v1/userinfo")
        assert headers["Authorization"] == "Bearer at-live"
        return {"email": "me@example.com"}

    monkeypatch.setattr(api_server, "_http_json", fake_http_json)
    lca_calls: list[str] = []
    monkeypatch.setattr(api_server, "load_code_assist_project", lambda token: lca_calls.append(token) or "proj-77")

    status, body = _post(base + "/api/video-flow/oauth/exchange", {
        "provider": "antigravity", "code": "4/live-code", "state": state,
        "redirect_uri": "http://127.0.0.1:8991/callback",
    })

    assert status == 200
    assert body["success"] is True
    assert body["email"] == "me@example.com"

    # Token endpoint call: client_secret flow, grant_type authorization_code, no PKCE.
    token_call = next(call for call in calls if call["url"].startswith("https://oauth2.googleapis.com/token"))
    assert token_call["data"]["grant_type"] == "authorization_code"
    assert token_call["data"]["client_id"] == ANTIGRAVITY_CLIENT_ID
    assert token_call["data"]["client_secret"] == ANTIGRAVITY_CLIENT_SECRET
    assert token_call["data"]["redirect_uri"] == "http://127.0.0.1:8991/callback"
    assert "code_verifier" not in token_call["data"]
    assert "code_challenge" not in token_call["data"]

    # loadCodeAssist ran best-effort with the access token.
    assert lca_calls == ["at-live"]

    connection = body["connection"]
    assert connection["status"] == "active"
    assert connection["account_id"] == "me@example.com"
    assert connection["name"].startswith("Antigravity ")
    assert connection["metadata"]["source"] == "oauth"
    assert connection["metadata"]["project_id"] == "proj-77"

    private = service.get_connection(int(connection["id"]), public=False)
    from voice_flow.video_flow_oauth import decrypt_token
    assert decrypt_token(service, private["secret"]) == "at-live"
    assert decrypt_token(service, private["refresh_token"]) == "rt-live"
    assert 0 < float(private["expires_at"]) <= time.time() + 3600

    # Pending session cleared after a successful exchange.
    cleared = service.get_setting("oauth_pending:antigravity", None)
    assert cleared is None or cleared.get("state") != state

    # The account now reports connected through the connection-based status.
    status_now = service.oauth_status("antigravity", refresh=True)
    assert status_now["connected"] is True


def test_old_video_flow_oauth_endpoints_stay_deleted(oauth_server):
    base = oauth_server["base_url"]
    for method, url in (
        ("POST", base + "/api/video-flow/providers/oauth/start"),
        ("POST", base + "/api/video-flow/providers/oauth/exchange"),
        ("POST", base + "/api/video-flow/providers/oauth/complete-callback"),
        ("POST", base + "/api/video-flow/providers/oauth/open-browser-unused"),
    ):
        status, body = _post(url, {"provider": "antigravity", "code": "x", "state": "y"})
        assert status == 404, (url, status, body)
        assert body.get("success") is False


def test_three_oauth_providers_are_in_the_catalog(oauth_server):
    status, body = _get(oauth_server["base_url"] + "/api/video-flow/catalog")
    assert status == 200
    groups = body.get("provider_groups") or {}
    oauth_ids = [p["id"] for p in (groups.get("oauth") or [])]
    assert oauth_ids == ["claude_code", "antigravity", "openai_codex"]

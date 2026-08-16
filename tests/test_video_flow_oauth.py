"""OAuth workflow engine tests: cipher, PKCE, device flow, CLI import,
refresh scheduling, health selection, and gateway 401/429 failover."""

from __future__ import annotations

import base64
import hashlib
import json
import time
import urllib.error
from pathlib import Path

import pytest

import voice_flow.video_flow_oauth as oauth_module
import voice_flow.video_flow_providers as providers_module
from voice_flow.video_flow_oauth import (
    OAuthError,
    connections_due_for_refresh,
    decrypt_token,
    encrypt_token,
    generate_pkce_pair,
    import_cli_session,
    jwt_expiry,
    refresh_and_store,
    start_refresh_scheduler,
)
from voice_flow.video_flow_providers import VideoFlowProviderService


# ---------------------------------------------------------------------------
# Token encryption
# ---------------------------------------------------------------------------

def test_encrypted_tokens_round_trip_and_are_not_plaintext(tmp_path):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    encrypted = encrypt_token(service, "sk-live-12345")
    assert "sk-live-12345" not in encrypted
    assert decrypt_token(service, encrypted) == "sk-live-12345"
    with service._connection() as conn:
        row = conn.execute(
            "SELECT value FROM video_flow_provider_settings WHERE key = 'oauth_master_key'"
        ).fetchone()
    assert row is not None
    assert decrypt_token(service, "plain-secret") == "plain-secret"


def test_connection_public_views_hide_refresh_token(tmp_path):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    connection = service.add_connection(
        "copilot", name="Copilot GitHub", secret=encrypt_token(service, "jwt-1"),
        refresh_token=encrypt_token(service, "gh-token-1"), account_id="github-copilot",
    )
    assert "refresh_token" not in connection
    assert "secret" not in connection
    private = service.get_connection(int(connection["id"]), public=False)
    assert private["refresh_token"].startswith("gAAAA")


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def test_pkce_pair_generates_valid_s256_challenge():
    verifier, challenge = generate_pkce_pair()
    assert 43 <= len(verifier) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    assert challenge == expected


def test_jwt_expiry_extracts_exp_claim():
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode("ascii")
    payload = base64.urlsafe_b64encode(json.dumps({"exp": 1700000000}).encode()).rstrip(b"=").decode("ascii")
    assert jwt_expiry(f"{header}.{payload}.sig") == "1700000000"
    assert jwt_expiry("not-a-jwt") == ""


# ---------------------------------------------------------------------------
# CLI session import
# ---------------------------------------------------------------------------

def test_codex_cli_import_reads_auth_json(tmp_path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({
        "auth_mode": "oauth",
        "tokens": {
            "access_token": "ck-abc",
            "refresh_token": "ck-refresh",
            "account_id": "user-42",
        },
        "last_refresh": "2026-08-16T10:00:00Z",
    }), encoding="utf-8")
    monkeypatch.setattr(oauth_module, "oauth_config", lambda _pid: oauth_module.OAuthConfig(
        flow="cli", cli_files=(str(auth),), refresh_mode="cli",
    ))
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    imported = import_cli_session(service, "openai_codex")
    assert imported["access_token"] == "ck-abc"
    assert imported["refresh_token"] == "ck-refresh"
    assert imported["account_id"] == "user-42"


def test_cli_import_missing_file_raises(tmp_path):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    with pytest.raises(OAuthError, match="not found"):
        import_cli_session(service, "cursor")


def test_oauth_import_creates_active_connection(tmp_path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"tokens": {"access_token": "ck-abc", "account_id": "me"}}), encoding="utf-8")
    monkeypatch.setattr(oauth_module, "oauth_config", lambda _pid: oauth_module.OAuthConfig(
        flow="cli", cli_files=(str(auth),), refresh_mode="cli",
    ))
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    connection = service.oauth_import("openai_codex")
    assert connection["status"] == "active"
    private = service.get_connection(int(connection["id"]), public=False)
    assert decrypt_token(service, private["secret"]) == "ck-abc"


# ---------------------------------------------------------------------------
# Health selection
# ---------------------------------------------------------------------------

def test_pick_best_connection_skips_expired_and_rate_limited(tmp_path):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    expired = service.add_connection("openai", name="expired", secret="k1")
    service.update_connection(int(expired["id"]), status="expired")
    cooldown = service.add_connection("openai", name="cooldown", secret="k2")
    service.update_connection(int(cooldown["id"]), status="rate_limited", cooldown_until=str(int(time.time()) + 120))
    fast = service.add_connection("openai", name="fast", secret="k3")
    service.update_connection(int(fast["id"]), status="connected", last_latency_ms=5)
    slow = service.add_connection("openai", name="slow", secret="k4")
    service.update_connection(int(slow["id"]), status="connected", last_latency_ms=500)

    best = service.pick_best_connection("openai")
    assert best["name"] == "fast"

    now = int(time.time())
    service.update_connection(int(fast["id"]), expires_at=str(now - 5))
    assert service.pick_best_connection("openai")["name"] == "slow"
    service.update_connection(int(slow["id"]), status="rate_limited", cooldown_until=str(now - 1))
    assert service.pick_best_connection("openai") is None


def test_connections_due_for_refresh_only_returns_expiring_active(tmp_path):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    due = service.add_connection("copilot", name="due", secret="s1", expires_at=str(int(time.time()) + 60))
    service.update_connection(int(due["id"]), status="active")
    far = service.add_connection("copilot", name="far", secret="s2", expires_at=str(int(time.time()) + 3600))
    service.update_connection(int(far["id"]), status="active")
    no_expiry = service.add_connection("openai_codex", name="cli", secret="s3")
    service.update_connection(int(no_expiry["id"]), status="active")

    due_ids = {int(item["id"]) for item in connections_due_for_refresh(service)}
    assert due_ids == {int(due["id"])}


def test_refresh_scheduler_is_idempotent_and_daemon(tmp_path):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    first = start_refresh_scheduler(service)
    second = start_refresh_scheduler(service)
    assert first is second
    assert first.daemon is True


def test_cli_refresh_rotates_secret(tmp_path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"tokens": {"access_token": "fresh-token", "account_id": "me"}}), encoding="utf-8")
    monkeypatch.setattr(oauth_module, "oauth_config", lambda _pid: oauth_module.OAuthConfig(
        flow="cli", cli_files=(str(auth),), refresh_mode="cli",
    ))
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    connection = service.oauth_import("openai_codex")
    refresh_and_store(service, service.get_connection(int(connection["id"]), public=False))
    private = service.get_connection(int(connection["id"]), public=False)
    assert decrypt_token(service, private["secret"]) == "fresh-token"


# ---------------------------------------------------------------------------
# Device-code flow (Copilot)
# ---------------------------------------------------------------------------

def test_device_flow_start_and_poll(tmp_path, monkeypatch):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    calls: list[dict] = []

    def fake_http_json(url, *, data=None, headers=None, timeout=15.0):
        calls.append({"url": url, "data": data})
        if url.endswith("/device/code"):
            return {"device_code": "dc-1", "user_code": "ABCD-1234", "verification_uri": "https://github.com/login/device", "interval": 5}
        return {"access_token": "gh-token", "refresh_token": "gh-refresh", "expires_in": 28800}

    monkeypatch.setattr(oauth_module, "_http_json", fake_http_json)
    monkeypatch.setattr(providers_module, "_http_json", fake_http_json)
    monkeypatch.setattr(oauth_module, "exchange_copilot_token", lambda _s, token: {
        "access_token": "copilot-jwt",
        "expires_at": str(int(time.time()) + 1800),
    })
    monkeypatch.setattr(providers_module, "exchange_copilot_token", lambda _s, token: {
        "access_token": "copilot-jwt",
        "expires_at": str(int(time.time()) + 1800),
    })

    info = service.start_oauth("copilot")
    assert info["flow"] == "device"
    assert info["device"]["user_code"] == "ABCD-1234"

    result = service.oauth_poll("copilot")
    assert result["status"] == "connected"
    private = service.get_connection(int(result["connection"]["id"]), public=False)
    assert decrypt_token(service, private["secret"]) == "copilot-jwt"
    assert decrypt_token(service, private["refresh_token"]) == "gh-token"


def test_device_flow_pending_polls_without_creating_connection(tmp_path, monkeypatch):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    monkeypatch.setattr(oauth_module, "_http_json", lambda *a, **k: {"error": "authorization_pending"})
    monkeypatch.setattr(providers_module, "_http_json", lambda *a, **k: {"error": "authorization_pending"})
    service.set_setting("oauth_pending:copilot", {"flow": "device", "device_code": "dc-1", "interval": 5})
    assert service.oauth_poll("copilot")["status"] == "pending"
    assert service.list_connections("copilot") == []


def test_pkce_exchange_creates_connection(tmp_path, monkeypatch):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    verifier, _ = generate_pkce_pair()
    state = "state-1"
    service.set_setting("oauth_pending:antigravity", {
        "flow": "pkce", "state": state, "code_verifier": verifier,
        "redirect_uri": "http://127.0.0.1:8991/",
    })
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode("ascii")
    payload = base64.urlsafe_b64encode(json.dumps({"email": "me@example.com"}).encode()).rstrip(b"=").decode("ascii")
    responses = [{
        "access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600,
        "id_token": f"{header}.{payload}.sig",
    }]

    def fake_http_json(url, *, data=None, headers=None, timeout=15.0):
        assert data["grant_type"] == "authorization_code"
        assert data["code_verifier"] == verifier
        assert data["client_secret"]
        return responses.pop(0)

    monkeypatch.setattr(oauth_module, "_http_json", fake_http_json)
    monkeypatch.setattr(providers_module, "_http_json", fake_http_json)

    connection = service.oauth_exchange("antigravity", "code-1", state)
    assert connection["status"] == "active"
    assert connection["account_id"] == "me@example.com"
    private = service.get_connection(int(connection["id"]), public=False)
    assert decrypt_token(service, private["secret"]) == "at-1"
    assert decrypt_token(service, private["refresh_token"]) == "rt-1"
    assert service.get_setting("oauth_pending:antigravity", None) is None or "cleared" in service.get_setting("oauth_pending:antigravity")


def test_pkce_exchange_rejects_wrong_state(tmp_path, monkeypatch):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    service.set_setting("oauth_pending:antigravity", {
        "flow": "pkce", "state": "expected", "code_verifier": "verifier",
        "redirect_uri": "http://127.0.0.1:8991/",
    })
    with pytest.raises(OAuthError, match="state mismatch"):
        service.oauth_exchange("antigravity", "code-1", "wrong")
    assert service.list_connections("antigravity") == []


# ---------------------------------------------------------------------------
# Gateway failover (401 → refresh+retry, 429 → cooldown)
# ---------------------------------------------------------------------------

class StubService:
    def __init__(self, connections):
        self.connections = connections
        self.refreshed = 0
        self.cooldowns = []
        self.latencies = []

    def active_connections(self, provider):
        return [dict(item) for item in self.connections if item.get("provider") == provider]

    def connection_is_healthy(self, connection):
        return connection.get("status") not in {"expired", "rate_limited"}

    def get_setting(self, key, default=None):
        return default

    def set_setting(self, key, value):
        pass

    def resolve_connection_secret(self, connection):
        return str(connection.get("secret", ""))

    def oauth_refresh(self, connection_id):
        self.refreshed += 1
        for connection in self.connections:
            if connection["id"] == connection_id:
                connection["secret"] = "refreshed-secret"
                return connection
        raise ValueError("missing")

    def mark_cooldown(self, connection_id, seconds=60):
        self.cooldowns.append(connection_id)

    def update_connection(self, connection_id, **changes):
        self.latencies.append(connection_id)

    def get_connection(self, connection_id, *, public=True):
        for connection in self.connections:
            if connection["id"] == connection_id:
                if not public:
                    return dict(connection)
                return {key: value for key, value in connection.items() if key != "secret"}
        return None


def _gateway(stub):
    import voice_flow.video_flow_models as models_module
    gateway = models_module.VideoModelGateway.__new__(models_module.VideoModelGateway)
    gateway.store = None
    gateway.planner = None
    models_module.video_flow_provider_service = stub
    return gateway


def _raise_http(code):
    raise urllib.error.HTTPError("https://api.example/v1/chat/completions", code, "error", {}, None)


def test_gateway_401_refreshes_then_retries(tmp_path, monkeypatch):
    import voice_flow.video_flow_models as models_module
    stub = StubService([{"id": 1, "provider": "openai", "secret": "stale", "status": "connected"}])
    gateway = _gateway(stub)
    attempts = {"calls": 0}

    def fake_call(self, provider, model_id, key, prompt):
        attempts["calls"] += 1
        if key == "stale":
            _raise_http(401)
        return {"scenes": [{"narration": "ok"}]}

    monkeypatch.setattr(models_module.VideoModelGateway, "_call_openai_compatible", fake_call)
    result = gateway._request_plan("source", "summary", "title", "openai/gpt-5.6-sol")
    assert stub.refreshed == 1
    assert attempts["calls"] == 2
    assert result["scenes"][0]["narration"] == "ok"
    assert stub.latencies == [1]


def test_gateway_429_marks_cooldown_and_fails_over(tmp_path, monkeypatch):
    import voice_flow.video_flow_models as models_module
    stub = StubService([
        {"id": 1, "provider": "openai", "secret": "k1", "status": "connected"},
        {"id": 2, "provider": "openai", "secret": "k2", "status": "connected"},
    ])
    gateway = _gateway(stub)

    def fake_call(self, provider, model_id, key, prompt):
        if key == "k1":
            _raise_http(429)
        return {"scenes": [{"narration": "fallback ok"}]}

    monkeypatch.setattr(models_module.VideoModelGateway, "_call_openai_compatible", fake_call)
    result = gateway._request_plan("source", "summary", "title", "openai/gpt-5.6-sol")
    assert stub.cooldowns == [1]
    assert stub.latencies == [2]
    assert result["scenes"][0]["narration"] == "fallback ok"


def test_gateway_refresh_failure_moves_to_next_connection(tmp_path, monkeypatch):
    import voice_flow.video_flow_models as models_module
    stub = StubService([
        {"id": 1, "provider": "openai", "secret": "stale", "status": "connected"},
        {"id": 2, "provider": "openai", "secret": "good", "status": "connected"},
    ])
    gateway = _gateway(stub)

    def fake_refresh(self, connection_id):
        raise OAuthError("no refresh handler")

    def fake_call(self, provider, model_id, key, prompt):
        if key == "stale":
            _raise_http(401)
        return {"scenes": [{"narration": "good"}]}

    monkeypatch.setattr(stub, "oauth_refresh", fake_refresh)
    monkeypatch.setattr(models_module.VideoModelGateway, "_call_openai_compatible", fake_call)
    result = gateway._request_plan("source", "summary", "title", "openai/gpt-5.6-sol")
    assert result["scenes"][0]["narration"] == "good"

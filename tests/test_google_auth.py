"""Hermetic tests for the Google sign-in system (Video Flow auth section).

Covers the spec's build order: /auth/google lands on Google's account chooser
(prompt=select_account) with a state cookie; the callback validates state,
exchanges the code server-side, upserts the user, and issues the app's own
signed httpOnly session cookie; /api/me and /auth/logout complete the loop;
the desktop pairing flow bridges the system browser to the WebView cookie jar.

All network calls and the database are monkeypatched — nothing touches the
user's real ~/.voice_flow data or Google.
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

import voice_flow.google_auth as google_auth
from voice_flow.gui import api_server


# ---------------------------------------------------------------------------
# Fixtures and HTTP helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_env(monkeypatch, tmp_path):
    """Isolated database, .env directory, and Google credentials."""
    db_path = str(tmp_path / "google_auth_test.db")
    monkeypatch.setattr(google_auth, "DB_PATH", db_path)
    monkeypatch.setenv("VOICE_FLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.example.test")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(google_auth, "_ENV_CACHE", None)
    google_auth._pairings.clear()
    return {"db_path": db_path, "tmp_path": tmp_path}


@pytest.fixture
def oauth_handler_server(auth_env):
    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.15)
    yield {"base_url": f"http://127.0.0.1:{server.server_address[1]}"}
    server.shutdown()
    server.server_close()


def _id_token(sub: str = "google-sub-1", email: str = "me@example.com",
              name: str = "Test User", picture: str = "https://example.com/pic.png") -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode("ascii")
    payload = base64.urlsafe_b64encode(json.dumps({
        "sub": sub, "email": email, "name": name, "picture": picture,
    }).encode()).rstrip(b"=").decode("ascii")
    return f"{header}.{payload}.signature"


def _request(url: str, method: str = "GET", payload: dict | None = None,
             cookies: dict[str, str] | None = None, follow_redirects: bool = False):
    headers = {"Connection": "close"}
    if cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    openers = [NoRedirect()] if not follow_redirects else []
    try:
        with urllib.request.build_opener(*openers).open(req, timeout=10) as resp:
            return resp.status, resp.headers, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read().decode("utf-8")


def _cookies_from(headers) -> dict[str, str]:
    cookies: dict[str, str] = {}
    raw_values = headers.get_all("Set-Cookie") if hasattr(headers, "get_all") else [headers.get("Set-Cookie", "")]
    for raw in raw_values or []:
        if not raw:
            continue
        first = raw.split(";", 1)[0]
        name, _, value = first.partition("=")
        cookies[name.strip()] = value.strip()
    return cookies


# ---------------------------------------------------------------------------
# Session token primitives
# ---------------------------------------------------------------------------

def test_sign_and_read_session_round_trip(auth_env):
    secret = google_auth._session_secret()
    token = google_auth.sign_session(secret, 42)
    data = google_auth.read_session(secret, token)
    assert data == {"uid": 42, "exp": data["exp"]}
    assert data["exp"] > time.time()


def test_tampered_or_expired_sessions_are_rejected(auth_env):
    secret = google_auth._session_secret()
    token = google_auth.sign_session(secret, 7)
    assert google_auth.read_session(secret, token[:-2] + "zz") is None
    assert google_auth.read_session("another-secret", token) is None
    expired = google_auth.sign_session(secret, 7, ttl=-10)
    assert google_auth.read_session(secret, expired) is None


def test_session_secret_is_persisted_and_stable(auth_env):
    first = google_auth._session_secret()
    assert google_auth._session_secret() == first
    assert len(first) >= 32


# ---------------------------------------------------------------------------
# Users table
# ---------------------------------------------------------------------------

def test_upsert_creates_then_updates_the_same_user(auth_env):
    created = google_auth.upsert_google_user("sub-1", "me@example.com", "Old Name", "")
    updated = google_auth.upsert_google_user("sub-1", "me@example.com", "New Name", "pic.png")
    assert created["id"] == updated["id"]
    assert updated["name"] == "New Name"
    fetched = google_auth.get_user_by_id(int(updated["id"]))
    assert fetched == updated
    import sqlite3
    with sqlite3.connect(auth_env["db_path"]) as conn:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert count == 1


# ---------------------------------------------------------------------------
# .env configuration loading
# ---------------------------------------------------------------------------

def test_env_file_provides_google_credentials(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "GOOGLE_CLIENT_ID=env-file-id\nGOOGLE_CLIENT_SECRET=env-file-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VOICE_FLOW_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(google_auth, "_ENV_CACHE", None)
    assert google_auth.google_auth_configured() is True
    config = google_auth.google_client_config()
    assert config["client_id"] == "env-file-id"
    assert config["client_secret"] == "env-file-secret"


def test_not_configured_without_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_FLOW_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(google_auth, "_ENV_CACHE", None)
    assert google_auth.google_auth_configured() is False


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------

def test_signin_redirects_to_account_chooser_with_state_cookie(oauth_handler_server):
    base = oauth_handler_server["base_url"]
    status, headers, body = _request(base + "/auth/google")

    assert status == 302
    location = headers.get("Location", "")
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    params = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(location).query).items()}
    assert params["client_id"] == "test-client-id.example.test"
    assert params["response_type"] == "code"
    assert params["scope"] == "openid email profile"
    assert params["prompt"] == "select_account"
    assert params["redirect_uri"].startswith("http://127.0.0.1:")
    assert params["redirect_uri"].endswith("/auth/google/callback")
    assert len(params["state"]) >= 32

    set_cookies = _cookies_from(headers)
    assert set_cookies["vf_oauth_state"] == params["state"]
    cookie_header = [raw for raw in headers.get_all("Set-Cookie") if raw.startswith("vf_oauth_state=")][0]
    assert "HttpOnly" in cookie_header
    assert "SameSite=Lax" in cookie_header
    assert "Path=/" in cookie_header


def test_callback_rejects_state_mismatch(oauth_handler_server, monkeypatch):
    base = oauth_handler_server["base_url"]
    monkeypatch.setattr(google_auth, "exchange_code", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("token endpoint must not be called on state mismatch")))
    status, headers, body = _request(
        base + "/auth/google/callback?code=abc&state=attacker-state",
        cookies={"vf_oauth_state": "legitimate-state"},
    )
    assert status == 400
    assert "Sign-in failed" in body


def test_callback_rejects_missing_code(oauth_handler_server):
    base = oauth_handler_server["base_url"]
    status, headers, body = _request(base + "/auth/google/callback?state=x")
    assert status == 400
    assert "Sign-in failed" in body


def test_callback_reports_access_blocked_for_test_users(oauth_handler_server):
    base = oauth_handler_server["base_url"]
    status, headers, body = _request(base + "/auth/google/callback?error=access_denied&state=x")
    assert status == 400
    assert "Test user" in body


def test_full_signin_loop_issues_session_and_profile(oauth_handler_server, monkeypatch):
    base = oauth_handler_server["base_url"]

    # 1. Start: capture the state cookie from the account-chooser redirect.
    status, headers, _ = _request(base + "/auth/google")
    cookies = _cookies_from(headers)
    assert "vf_oauth_state" in cookies

    # 2. Callback with the matching state; token exchange is stubbed.
    state = cookies["vf_oauth_state"]

    def fake_exchange(code, redirect_uri):
        assert code == "live-code"
        assert redirect_uri.endswith("/auth/google/callback")
        return {"access_token": "google-access", "id_token": _id_token()}

    monkeypatch.setattr(google_auth, "exchange_code", fake_exchange)
    status, headers, body = _request(
        base + f"/auth/google/callback?code=live-code&state={state}", cookies=cookies,
    )
    assert status == 302
    assert headers.get("Location") == "/"
    session_cookies = _cookies_from(headers)
    assert "vf_session" in session_cookies
    session_cookie_line = [raw for raw in headers.get_all("Set-Cookie") if raw.startswith("vf_session=")][0]
    assert "HttpOnly" in session_cookie_line
    assert "SameSite=Lax" in session_cookie_line

    # 3. /api/me with the session cookie returns the profile.
    status, _, body = _request(base + "/api/me", cookies=session_cookies)
    assert status == 200
    profile = json.loads(body)
    assert profile["authenticated"] is True
    assert profile["user"]["email"] == "me@example.com"
    assert profile["user"]["name"] == "Test User"
    assert profile["user"]["picture"] == "https://example.com/pic.png"
    assert profile["user"]["google_id"] == "google-sub-1"

    # 4. Logout clears the cookie; /api/me is 401 afterwards.
    status, headers, body = _request(base + "/auth/logout", method="POST", payload={})
    assert status == 200
    cleared = _cookies_from(headers)
    assert cleared.get("vf_session") == ""
    status, _, body = _request(base + "/api/me", cookies={"vf_session": "garbage"})
    assert status == 401


def test_api_me_returns_401_without_session(oauth_handler_server):
    base = oauth_handler_server["base_url"]
    status, _, body = _request(base + "/api/me")
    assert status == 401
    assert json.loads(body)["error"] == "not_authenticated"


def test_desktop_pairing_flow_bridges_system_browser_session(oauth_handler_server, monkeypatch):
    base = oauth_handler_server["base_url"]
    opened: list[str] = []
    monkeypatch.setattr("os.startfile", lambda url: opened.append(url), raising=False)

    # 1. The app asks for a system-browser sign-in.
    status, _, body = _request(base + "/auth/google/open", method="POST", payload={})
    assert status == 200
    data = json.loads(body)
    assert data["success"] is True
    assert data["pair_token"]
    assert opened and opened[0].startswith(f"{base}/auth/google?pair=")

    pair_token = data["pair_token"]

    # 2. Polling before completion says not ready.
    status, _, _ = _request(base + "/auth/desktop/session", method="POST", payload={"pair_token": pair_token})
    assert status == 401

    # 3. System browser completes sign-in with the pairing cookie.
    status, headers, _ = _request(base + f"/auth/google?pair={pair_token}")
    cookies = _cookies_from(headers)
    state = cookies["vf_oauth_state"]
    assert cookies["vf_oauth_pair"] == pair_token
    monkeypatch.setattr(google_auth, "exchange_code", lambda *a, **k: {
        "access_token": "google-access", "id_token": _id_token(sub="desktop-sub", email="desk@example.com"),
    })
    status, headers, body = _request(
        base + f"/auth/google/callback?code=live&state={state}", cookies=cookies,
    )
    assert status == 200
    assert "Signed in as desk@example.com" in body

    # 4. The app claims the pairing and receives the session cookie.
    status, headers, body = _request(
        base + "/auth/desktop/session", method="POST", payload={"pair_token": pair_token},
    )
    assert status == 200
    session_cookies = _cookies_from(headers)
    assert session_cookies.get("vf_session")
    status, _, body = _request(base + "/api/me", cookies=session_cookies)
    profile = json.loads(body)
    assert profile["user"]["email"] == "desk@example.com"

    # 5. A pairing token is single-use.
    status, _, _ = _request(base + "/auth/desktop/session", method="POST", payload={"pair_token": pair_token})
    assert status == 401


def test_signin_without_configuration_shows_clear_error(oauth_handler_server, monkeypatch, tmp_path):
    base = oauth_handler_server["base_url"]
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(google_auth, "_ENV_CACHE", None)
    status, _, body = _request(base + "/auth/google")
    assert status == 400
    assert "GOOGLE_CLIENT_ID" in body


def test_desktop_open_without_configuration_fails_cleanly(oauth_handler_server, monkeypatch, tmp_path):
    base = oauth_handler_server["base_url"]
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(google_auth, "_ENV_CACHE", None)
    status, _, body = _request(base + "/auth/google/open", method="POST", payload={})
    assert status == 200
    data = json.loads(body)
    assert data["success"] is False
    assert ".env" in data["error"]

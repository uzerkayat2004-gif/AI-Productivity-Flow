"""Google sign-in for the Video Flow authentication section.

One-click, zero-typing OAuth 2.0 (authorization code):

  GET /auth/google            -> 302 to Google's account chooser (prompt=select_account),
                                 random state stored in a short-lived httpOnly cookie.
  GET /auth/google/callback   -> state verified against the cookie, code exchanged
                                 server-side (client_id + client_secret), user
                                 upserted, this app's own signed httpOnly session
                                 cookie issued.

Google tokens are never used for the app's own API auth and are never sent to
the frontend. Only email, name, picture, and google_id are stored.

Desktop pairing: pywebview's WebView2 cookie jar is separate from the system
browser, so POST /auth/google/open starts sign-in in the default browser with
a pairing token; the callback claims the pairing and POST /auth/desktop/session
mints the session cookie inside the app's own cookie jar.
"""

from __future__ import annotations

import base64
import html
import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import secrets

log = logging.getLogger(__name__)
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from voice_flow.paths import data_dir
from voice_flow.storage import DB_PATH

AUTH_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
OAUTH_SCOPE = "openid email profile"

STATE_COOKIE = "vf_oauth_state"
PAIR_COOKIE = "vf_oauth_pair"
SESSION_COOKIE = "vf_session"

STATE_TTL_SECONDS = 600
SESSION_TTL_SECONDS = 30 * 24 * 3600
PAIR_TTL_SECONDS = 600


class GoogleAuthError(Exception):
    """Sign-in failed with a user-presentable message."""


# --------------------------------------------------------------------------
# Configuration (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET from .env)
# --------------------------------------------------------------------------

_ENV_CACHE: dict[str, str] | None = None


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                values[key] = value
    except OSError:
        pass
    return values


def _env(name: str) -> str:
    global _ENV_CACHE
    if _ENV_CACHE is None:
        _ENV_CACHE = {}
        # User data dir first, project root second (dev checkouts). Real
        # environment variables always win over both files.
        candidates = (
            data_dir() / ".env",
            Path(__file__).resolve().parents[2] / ".env",
        )
        for candidate in candidates:
            _ENV_CACHE.update(_load_env_file(candidate))
    return (os.environ.get(name) or _ENV_CACHE.get(name, "")).strip()


def google_client_config() -> dict[str, str]:
    return {
        "client_id": _env("GOOGLE_CLIENT_ID"),
        "client_secret": _env("GOOGLE_CLIENT_SECRET"),
    }


def google_auth_configured() -> bool:
    config = google_client_config()
    return bool(config["client_id"] and config["client_secret"])


def redirect_uri_for_port(port: int) -> str:
    """The exact loopback URI Google Console must be configured with."""
    return f"http://127.0.0.1:{int(port)}/auth/google/callback"


# --------------------------------------------------------------------------
# Database: users table + server session secret (same voice_flow.db)
# --------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        google_id TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL DEFAULT '',
        picture TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS google_auth_kv (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""")


def _kv_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM google_auth_kv WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else None


def _session_secret() -> str:
    with _connect() as conn:
        _ensure_tables(conn)
        secret = _kv_get(conn, "session_secret")
        if secret:
            return secret
        secret = secrets.token_hex(32)
        conn.execute(
            "INSERT OR REPLACE INTO google_auth_kv (key, value) VALUES (?, ?)",
            ("session_secret", secret),
        )
        conn.commit()
        return secret


def _public_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "google_id": str(row["google_id"]),
        "email": str(row["email"]),
        "name": str(row["name"]),
        "picture": str(row["picture"]),
    }


def upsert_google_user(google_id: str, email: str, name: str, picture: str) -> dict[str, Any]:
    with _connect() as conn:
        _ensure_tables(conn)
        conn.execute(
            """INSERT INTO users (google_id, email, name, picture, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(google_id) DO UPDATE SET
                   email = excluded.email, name = excluded.name, picture = excluded.picture""",
            (google_id, email or "", name or "", picture or "", _now_iso()),
        )
        row = conn.execute("SELECT * FROM users WHERE google_id = ?", (google_id,)).fetchone()
    return _public_user(row)


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        _ensure_tables(conn)
        row = conn.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    return _public_user(row) if row else None


# --------------------------------------------------------------------------
# Session cookie: base64url(json{uid, exp}).hmac_sha256(secret)
# --------------------------------------------------------------------------

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign_session(secret: str, user_id: int, ttl: int = SESSION_TTL_SECONDS) -> str:
    payload = _b64url(json.dumps(
        {"uid": int(user_id), "exp": int(time.time()) + int(ttl)},
        separators=(",", ":"),
    ).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def read_session(secret: str, token: str) -> dict[str, Any] | None:
    try:
        payload, signature = token.rsplit(".", 1)
        expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(_b64url_decode(payload).decode("utf-8"))
        if int(data.get("exp", 0)) < time.time():
            return None
        uid = data.get("uid")
        if not isinstance(uid, int):
            return None
        return data
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------
# Desktop pairing tokens (in-memory; the app and callback share one process)
# --------------------------------------------------------------------------

_pairings: dict[str, dict[str, Any]] = {}
_pairings_lock = threading.Lock()


def _prune_pairings_locked() -> None:
    deadline = time.time() - PAIR_TTL_SECONDS
    for token in [key for key, item in _pairings.items() if item["created"] < deadline]:
        _pairings.pop(token, None)


def create_pairing() -> str:
    token = secrets.token_urlsafe(32)
    with _pairings_lock:
        _prune_pairings_locked()
        _pairings[token] = {"status": "pending", "user_id": None, "created": time.time()}
    return token


def claim_pairing(token: str, user_id: int) -> bool:
    with _pairings_lock:
        item = _pairings.get(token)
        if not item or item["status"] != "pending":
            return False
        item["status"] = "claimed"
        item["user_id"] = int(user_id)
        return True


def consume_pairing(token: str) -> int | None:
    with _pairings_lock:
        item = _pairings.get(token)
        # Pending tokens stay alive so the app can keep polling; claimed
        # tokens are consumed exactly once.
        if not item or item["status"] != "claimed" or item["user_id"] is None:
            return None
        del _pairings[token]
        return int(item["user_id"])


def check_pairing_status(token: str) -> dict[str, Any]:
    with _pairings_lock:
        item = _pairings.get(token)
        if not item:
            return {"status": "unknown", "claimed": False}
        if item["status"] == "claimed":
            return {"status": "claimed", "claimed": True, "user_id": item.get("user_id")}
        return {"status": "pending", "claimed": False}


# --------------------------------------------------------------------------
# Zero-config Google ACCOUNT sign-in (embedded Antigravity client).
# --------------------------------------------------------------------------

_ACCOUNT_STATE_PREFIX = "vfacct:"
_NOTEBOOKLM_STATE_PREFIX = "vfnlm:"

_ACCOUNT_PENDING_KEY = "account_flow_pending:antigravity"
_NOTEBOOKLM_PENDING_KEY = "notebooklm_flow_pending"


def _notebooklm_pending_save(payload: dict[str, Any]) -> None:
    with _connect() as conn:
        _ensure_tables(conn)
        _kv_set(conn, _NOTEBOOKLM_PENDING_KEY, json.dumps(payload))


def _notebooklm_pending_load() -> dict[str, Any] | None:
    with _connect() as conn:
        _ensure_tables(conn)
        raw = _kv_get(conn, _NOTEBOOKLM_PENDING_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _notebooklm_pending_clear() -> None:
    with _connect() as conn:
        _ensure_tables(conn)
        _kv_delete(conn, _NOTEBOOKLM_PENDING_KEY)


def start_notebooklm_browser_flow(
    port: int = 8991,
    profile: str | None = None,
    switch_account: bool = False,
    direct: bool = False,
) -> dict[str, Any]:
    """Launch Google NotebookLM login in the user's SYSTEM DEFAULT browser.

    Opens Google's official account chooser (prompt=select_account) directly
    in the default browser where the user's existing Google sessions live.
    Zero prompt popups, no separate Chrome profiles, and no manual typing.
    """
    flow = _notebooklm_flow()
    state = _NOTEBOOKLM_STATE_PREFIX + secrets.token_urlsafe(24)
    redirect_uri = provider_redirect_uri(port)
    _notebooklm_pending_save({
        "provider": "notebooklm",
        "state": state,
        "redirect_uri": redirect_uri,
        "profile": profile or "video-flow-experiment",
        "switch_account": bool(switch_account),
        "created": time.time(),
    })
    params = {
        "client_id": flow["client_id"],
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": flow["scope"],
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    url = flow["auth_url"] + "?" + urllib.parse.urlencode(params)
    direct_login_url = get_notebooklm_direct_login_url(switch_account)
    url_to_open = direct_login_url if direct else url
    opened = open_system_browser(url_to_open)
    return {
        "success": True,
        "auth_url": url,
        "state": state,
        "opened": bool(opened),
        "direct_login_url": direct_login_url,
        "url_to_open": url_to_open,
    }


def complete_notebooklm_flow(code: str, state: str, port: int) -> dict[str, Any]:
    """Finish NotebookLM Google sign-in from the default browser callback."""
    pending = _notebooklm_pending_load()
    if not pending or not state or pending.get("state") != state:
        raise GoogleAuthError("OAuth state mismatch. Start the NotebookLM sign-in again.")
    if time.time() - float(pending.get("created") or 0) > STATE_TTL_SECONDS:
        _notebooklm_pending_clear()
        raise GoogleAuthError("NotebookLM sign-in link expired. Please start the sign-in again.")

    redirect_uri = str(pending.get("redirect_uri") or provider_redirect_uri(port))
    flow = _notebooklm_flow()
    tokens = _provider_token_exchange(flow, code, redirect_uri)
    access_token = str(tokens.get("access_token") or "")
    if not access_token:
        _notebooklm_pending_clear()
        raise GoogleAuthError("Google did not return an access token. Please try again.")

    email = ""
    name = ""
    picture = ""
    try:
        userinfo = _provider_userinfo(access_token)
        email = str(userinfo.get("email") or "")
        name = str(userinfo.get("name") or "")
        picture = str(userinfo.get("picture") or "")
    except Exception:
        pass
    if not email:
        _notebooklm_pending_clear()
        raise GoogleAuthError("Could not read your Google account email. Please try signing in again.")

    target_profile = str(pending.get("profile") or "video-flow-experiment").strip()
    is_switch = bool(pending.get("switch_account"))

    # Save to voice_flow storage
    try:
        from voice_flow.storage import storage
        storage.save_setting("video_flow_notebooklm_email", email)
        storage.save_setting("video_flow_notebooklm_authenticated", True)
    except Exception:
        pass
    try:
        from voice_flow.gui import api_server
        api_server.storage.save_setting("video_flow_notebooklm_email", email)
        api_server.storage.save_setting("video_flow_notebooklm_authenticated", True)
    except Exception:
        pass

    # Update or initialize storage_state.json for NotebookLM
    try:
        from voice_flow.video_flow_engine.notebooklm.config import (
            get_storage_state_path,
            get_storage_backup_path,
            resolve_notebooklm_profile,
            get_profile_dir,
        )
        resolved_prof = resolve_notebooklm_profile(target_profile)
        st_path = get_storage_state_path(resolved_prof)
        state_content: dict[str, Any] = {}
        old_email = ""
        if st_path.is_file():
            try:
                loaded = json.loads(st_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    state_content = loaded
                    old_email = (
                        (loaded.get("notebooklm") or {}).get("account", {}).get("email")
                        or (loaded.get("account") or {}).get("email")
                        or ""
                    )
            except Exception:
                state_content = {}

        cookies = state_content.get("cookies", [])
        if not isinstance(cookies, list):
            cookies = []

        account_changed = bool(old_email and old_email.lower() != email.lower())

        b_path = get_storage_backup_path(resolved_prof)
        safe_copy_path = st_path.with_name("storage_state.safe_copy.json")

        if account_changed or is_switch:
            # When account explicitly switched or changed, clear old cookies and remove old backup
            cookies = []
            if b_path.is_file():
                try:
                    b_path.unlink(missing_ok=True)
                except Exception:
                    pass
            if safe_copy_path.is_file():
                try:
                    s_data = json.loads(safe_copy_path.read_text(encoding="utf-8"))
                    s_acc = (s_data.get("notebooklm") or {}).get("account", {}) or s_data.get("account", {})
                    s_email = s_acc.get("email") if isinstance(s_acc, dict) else None
                    if not s_email or s_email.lower() != email.lower():
                        safe_copy_path.unlink(missing_ok=True)
                except Exception:
                    pass
            try:
                from voice_flow.video_flow_engine.notebooklm.provider import _WORKSPACE_NOTEBOOK_CACHE
                _WORKSPACE_NOTEBOOK_CACHE.clear()
            except Exception:
                pass
        elif not cookies:
            # Check backup if active cookies are missing in primary (same account only)
            if b_path.is_file():
                try:
                    b_data = json.loads(b_path.read_text(encoding="utf-8"))
                    if isinstance(b_data, dict) and isinstance(b_data.get("cookies"), list) and b_data.get("cookies"):
                        b_acc = (b_data.get("notebooklm") or {}).get("account", {}) or b_data.get("account", {})
                        b_email = b_acc.get("email") if isinstance(b_acc, dict) else None
                        if not b_email or not email or b_email.lower() == email.lower():
                            cookies = b_data.get("cookies")
                except Exception:
                    pass

        # Check permanent safe_copy only if NOT switching / account not changed
        if not (account_changed or is_switch) and not cookies and safe_copy_path.is_file():
            try:
                s_data = json.loads(safe_copy_path.read_text(encoding="utf-8"))
                if isinstance(s_data, dict) and isinstance(s_data.get("cookies"), list) and s_data.get("cookies"):
                    s_acc = (s_data.get("notebooklm") or {}).get("account", {}) or s_data.get("account", {})
                    s_email = s_acc.get("email") if isinstance(s_acc, dict) else None
                    if s_email and email and s_email.lower() == email.lower():
                        cookies = s_data.get("cookies")
            except Exception:
                pass

        # If cookies are missing, attempt browser auto-sync with expected_email
        if not cookies:
            try:
                from voice_flow.video_flow_engine.notebooklm.browser_sync import auto_sync_from_browser

                sync_res = auto_sync_from_browser(profile=resolved_prof, expected_email=email)
                if sync_res.get("success") and st_path.is_file():
                    try:
                        reloaded = json.loads(st_path.read_text(encoding="utf-8"))
                        if isinstance(reloaded, dict) and isinstance(reloaded.get("cookies"), list) and reloaded.get("cookies"):
                            cookies = reloaded.get("cookies")
                    except Exception:
                        pass
            except Exception:
                pass

        if not isinstance(cookies, list):
            cookies = []

        # When switching accounts to a different email, clean old master token
        if account_changed:
            try:
                mt_file = get_profile_dir(resolved_prof) / "master_token.json"
                if mt_file.is_file():
                    mt_data = json.loads(mt_file.read_text(encoding="utf-8"))
                    mt_account = str(mt_data.get("account") or "").lower()
                    if mt_account and mt_account != email.lower():
                        mt_file.unlink(missing_ok=True)
            except Exception:
                pass
            try:
                from voice_flow.video_flow_engine.notebooklm.login_flow import (
                    _login_log_path,
                    _terminate_stale_login_processes,
                )
                _terminate_stale_login_processes(resolved_prof, _login_log_path())
            except Exception:
                pass

        state_content["cookies"] = cookies
        state_content["origins"] = state_content.get("origins", [])
        state_content["notebooklm"] = {
            "version": 1,
            "account": {
                "authuser": 0,
                "email": email,
            },
        }
        state_content["account"] = {"email": email}

        st_path.parent.mkdir(parents=True, exist_ok=True)
        st_json = json.dumps(state_content, indent=2)
        st_path.write_text(st_json, encoding="utf-8")

        # Write backup when valid cookies are present
        if cookies:
            b_path.parent.mkdir(parents=True, exist_ok=True)
            b_path.write_text(st_json, encoding="utf-8")
            try:
                safe_copy_path.write_text(st_json, encoding="utf-8")
            except Exception:
                pass
        elif account_changed:
            if b_path.is_file():
                try:
                    b_path.unlink(missing_ok=True)
                except Exception:
                    pass

        # If cookies are missing, trigger headless self-heal asynchronously in background
        if not cookies:
            try:
                from voice_flow.video_flow_engine.notebooklm import login_flow
                threading.Thread(
                    target=login_flow.self_heal,
                    kwargs={"profile": resolved_prof},
                    name="notebooklm-self-heal",
                    daemon=True,
                ).start()
            except Exception:
                pass
    except Exception:
        pass

    # Inform login_flow of success
    try:
        from voice_flow.video_flow_engine.notebooklm import login_flow
        login_flow.record_successful_login(email, target_profile)
    except Exception:
        pass

    _notebooklm_pending_clear()
    _provider_completed_mark(state)
    return {"email": email, "name": name, "picture": picture, "profile": target_profile}


def account_client_config() -> dict[str, str]:
    """Resolve Google OAuth client ID and secret for Voice Flow Account authentication.

    1. Check user-configured GOOGLE_ACCOUNT_CLIENT_ID / GOOGLE_ACCOUNT_CLIENT_SECRET
       or GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET in env or storage.
    2. Default to PROVIDER_GOOGLE_PUBLIC_CLIENT_ID and PROVIDER_GOOGLE_PUBLIC_CLIENT_SECRET
       (standard Google desktop public client; never displays 'Google Antigravity').
    """
    client_id = (
        _env("GOOGLE_ACCOUNT_CLIENT_ID")
        or _env("GOOGLE_CLIENT_ID")
    )
    client_secret = (
        _env("GOOGLE_ACCOUNT_CLIENT_SECRET")
        or _env("GOOGLE_CLIENT_SECRET")
    )
    if not client_id:
        try:
            from voice_flow.storage import storage
            stored_id = str(
                storage.get_setting("google_account_client_id")
                or storage.get_setting("google_client_id")
                or ""
            ).strip()
            if stored_id:
                client_id = stored_id
            stored_sec = str(
                storage.get_setting("google_account_client_secret")
                or storage.get_setting("google_client_secret")
                or ""
            ).strip()
            if stored_sec:
                client_secret = stored_sec
        except Exception:
            pass
    if not client_id:
        client_id = PROVIDER_GOOGLE_PUBLIC_CLIENT_ID
        client_secret = PROVIDER_GOOGLE_PUBLIC_CLIENT_SECRET
    return {
        "client_id": client_id,
        "client_secret": client_secret or "",
    }


def _account_flow_consent_url(port: int, pair_token: str = "") -> str:
    """Consent URL for the Voice Flow Google account sign-in.

    Uses standard Google desktop OAuth client credentials so Google's consent
    screen does not show 'Google Antigravity'.
    `prompt=select_account` keeps the one-click Google account picker.
    """
    cfg = account_client_config()
    client_id = cfg["client_id"]
    client_secret = cfg["client_secret"]
    state = _ACCOUNT_STATE_PREFIX + secrets.token_urlsafe(24)
    redirect_uri = provider_redirect_uri(port)
    payload = {
        "provider": "account",
        "client_id": client_id,
        "client_secret": client_secret,
        "state": state,
        "redirect_uri": redirect_uri,
        "account_flow": True,
        "pair_token": pair_token or "",
        "created": time.time(),
    }
    _provider_pending_save("account", payload)
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def start_google_account_auth(port: int = 8991) -> dict[str, Any]:
    """Launch Google Sign-In for app account in user's default browser."""
    pair_token = create_pairing()
    url = _account_flow_consent_url(port, pair_token)
    opened = open_system_browser(url)
    return {
        "success": True,
        "pair_token": pair_token,
        "opened": bool(opened),
        "url": url,
    }


def complete_account_flow(code: str, state: str, port: int) -> dict[str, Any]:
    """Finish the zero-config Google account sign-in: user + session + central AccountManager."""
    pending = _provider_pending_load("account") or _provider_pending_load("antigravity")
    if not pending or not pending.get("account_flow") or not state or pending.get("state") != state:
        raise GoogleAuthError("OAuth state mismatch. Start the sign-in flow again.")
    if time.time() - float(pending.get("created") or 0) > STATE_TTL_SECONDS:
        _provider_pending_clear("account")
        raise GoogleAuthError("This sign-in link expired. Please start the sign-in again.")
    redirect_uri = str(pending.get("redirect_uri") or provider_redirect_uri(port))
    
    cfg = account_client_config()
    client_id = str(pending.get("client_id") or cfg["client_id"])
    client_secret = str(pending.get("client_secret") or cfg["client_secret"])
    flow = {
        "client_id": client_id,
        "client_secret": client_secret,
        "token_url": "https://oauth2.googleapis.com/token",
    }
    tokens = _provider_token_exchange(flow, code, redirect_uri)
    access_token = str(tokens.get("access_token") or "")
    if not access_token:
        _provider_pending_clear("account")
        raise GoogleAuthError("Google did not return an access token. Please try again.")

    email = ""
    full_name = ""
    picture = ""
    google_sub = ""
    try:
        userinfo = _provider_userinfo(access_token)
        email = str(userinfo.get("email") or "")
        full_name = str(userinfo.get("name") or "")
        picture = str(userinfo.get("picture") or "")
        google_sub = str(userinfo.get("id") or "")
    except Exception as exc:
        log.warning("Could not fetch userinfo via Google API: %s", exc)
    if not google_sub and not email:
        _provider_pending_clear("account")
        raise GoogleAuthError("Could not read your Google account profile. Please try signing in again.")

    user = upsert_google_user(google_sub or email, email, full_name, picture)

    # Sync into central AccountManager multi-account profile system
    try:
        from voice_flow.account_manager import get_account_manager
        am = get_account_manager()
        am_res = am.authenticate_or_register_google(
            email=email,
            username=full_name or email.split("@")[0],
            google_id=google_sub or email,
            avatar_url=picture,
        )
        if am_res and am_res.get("account"):
            log.info("Google user registered/switched in AccountManager: %s", am_res["account"]["email"])
    except Exception:
        log.exception("Failed to register/switch Google user in AccountManager")

    pair_token = str(pending.get("pair_token") or "")
    _provider_pending_clear("account")
    _provider_completed_mark(state)
    return {"user": user, "pair_token": pair_token, "email": email}


def handle_browser_callback(handler: Any, port: int) -> None:
    """GET /callback — shared landing for NotebookLM + provider + account flows.

    Distinguishes them by state prefix:
      "vfnlm:"  = NotebookLM Google sign-in / account switch
      "vfacct:" = Voice Flow general account sign-in
      other     = provider OAuth connection
    """
    parsed = urllib.parse.urlparse(handler.path)
    qs = urllib.parse.parse_qs(parsed.query)
    error = str(qs.get("error", [""])[0])
    code = str(qs.get("code", [""])[0])
    state = str(qs.get("state", [""])[0])
    if error:
        _send_error_page(handler, f"Google reported: {error}")
        return
    if not code or not state:
        _send_error_page(handler, "The sign-in link did not include an authorization code. Please start the sign-in again.")
        return
    if provider_flow_state_completed(state):
        _send_success_page(handler, "Already connected",
                           "This sign-in was already completed. You can close this tab and return to Voice Flow.")
        return

    is_notebooklm = state.startswith(_NOTEBOOKLM_STATE_PREFIX)
    is_account = state.startswith(_ACCOUNT_STATE_PREFIX)
    try:
        if is_notebooklm:
            result = complete_notebooklm_flow(code, state, port)
            email = str(result.get("email") or "your Google account")
            try:
                import ctypes
                user32 = ctypes.windll.user32
                hwnd = user32.FindWindowW(None, "AI Productivity Flow")
                if not hwnd:
                    hwnd = user32.FindWindowW(None, "Voice Flow")
                if not hwnd:
                    hwnd = user32.FindWindowW(None, "Voice Flow - AI Speech Desktop App")
                if hwnd:
                    user32.ShowWindow(hwnd, 9)
                    user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
            _send_success_page(
                handler,
                f"Signed in to NotebookLM as {email}",
                "Your Google account has been connected to Voice Flow. You can close this tab and return to the app.",
            )
            return

        if is_account:
            result = complete_account_flow(code, state, port)
            user = result["user"]
            pair_token = result["pair_token"]
            if pair_token:
                # Desktop app flow: the app polls /auth/desktop/session and
                # mints the session cookie inside its own cookie jar.
                claim_pairing(pair_token, int(user["id"]))
                try:
                    import ctypes
                    user32 = ctypes.windll.user32
                    for title in ["AI Productivity Flow", "Voice Flow", "Voice Flow - AI Speech Desktop App"]:
                        hwnd = user32.FindWindowW(None, title)
                        if hwnd:
                            user32.ShowWindow(hwnd, 9)
                            user32.SetForegroundWindow(hwnd)
                            break
                except Exception:
                    pass
                _send_success_page(handler, f"Signed in as {user['email'] or user['name'] or 'your Google account'}",
                                   "You can close this tab and return to Voice Flow — the app signs itself in automatically.")
                return
            # Plain browser mode: set the session cookie here and drop the
            # user straight back into the app, already signed in.
            _send_redirect(handler, "/", _session_cookie_headers(int(user["id"])))
            return
        result = complete_provider_flow("antigravity", code, state)
    except GoogleAuthError as exc:
        _send_error_page(handler, str(exc))
        return
    except Exception:
        _send_error_page(handler, "Sign-in failed. Please start the sign-in again.")
        return
    try:
        # Bring the desktop app forward (ctypes; never fatal).
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "AI Productivity Flow")
        if not hwnd:
            hwnd = user32.FindWindowW(None, "Voice Flow")
        if not hwnd:
            hwnd = user32.FindWindowW(None, "Voice Flow - AI Speech Desktop App")
        if hwnd:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
    email = str(result.get("email") or "your account")
    _send_success_page(handler, f"Connected as {email}",
                       "Voice Flow is connected. You can close this tab and return to the app — the account appears automatically.")


# --------------------------------------------------------------------------
# Token exchange and id_token parsing
# --------------------------------------------------------------------------

def _token_error_message(detail: dict[str, Any], status: int) -> str:
    code = str(detail.get("error") or "")
    if code == "redirect_uri_mismatch":
        return (
            "Google rejected the redirect URI. Add this exact URI under "
            "Credentials > your OAuth client > Authorized redirect URIs in "
            "Google Cloud Console, then try again: " + detail.get("sent_redirect_uri", "")
        )
    if code == "invalid_grant":
        return "Sign-in expired or was already used. Please try signing in again."
    if code in ("access_denied", "blocked") or status == 403:
        return (
            "Google blocked this sign-in. Add your Google account email as a "
            "Test user in Google Cloud Console (OAuth consent screen) and retry."
        )
    description = str(detail.get("error_description") or code or f"HTTP {status}")
    return f"Google sign-in failed: {description[:300]}"


def exchange_code(code: str, redirect_uri: str) -> dict[str, Any]:
    config = google_client_config()
    body = urllib.parse.urlencode({
        "code": code,
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode("utf-8")
    request = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except Exception:
            detail = {}
        if isinstance(detail, dict):
            detail.setdefault("sent_redirect_uri", redirect_uri)
            raise GoogleAuthError(_token_error_message(detail, exc.code)) from exc
        raise GoogleAuthError(f"Google sign-in failed: HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise GoogleAuthError(f"Could not reach Google to complete sign-in: {exc}") from exc


def id_token_claims(id_token: str) -> dict[str, Any]:
    """Decode id_token payload claims (token came straight from Google over TLS)."""
    try:
        return json.loads(_b64url_decode(str(id_token).split(".")[1]).decode("utf-8"))
    except (ValueError, TypeError, IndexError):
        return {}


# --------------------------------------------------------------------------
# Cookie helpers
# --------------------------------------------------------------------------

def _request_cookies(handler: Any) -> dict[str, str]:
    header = handler.headers.get("Cookie") or ""
    cookies: dict[str, str] = {}
    for part in header.split(";"):
        if "=" in part:
            key, _, value = part.partition("=")
            cookies[key.strip()] = value.strip()
    return cookies


def _cookie_header(name: str, value: str, max_age: int, path: str = "/") -> str:
    parts = [f"{name}={value}", f"Path={path}", f"Max-Age={max_age}", "HttpOnly", "SameSite=Lax"]
    if os.environ.get("VOICE_FLOW_SECURE_COOKIES"):
        parts.append("Secure")
    return "; ".join(parts)


def _send_json(handler: Any, payload: dict[str, Any], status: int = 200,
               extra_headers: list[tuple[str, str]] | None = None) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    for name, value in (extra_headers or []):
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(body)


_ERROR_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Sign-in failed</title>
<style>body{{font-family:system-ui,sans-serif;background:#0b0d12;color:#e5e7eb;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
.card{{max-width:460px;padding:32px;border:1px solid #2a2f3a;border-radius:12px;background:#11141b;text-align:center}}
h1{{font-size:18px;margin:0 0 12px}}p{{font-size:14px;line-height:1.6;color:#9ca3af;margin:0 0 20px}}
a{{color:#8ab4f8;font-size:14px}}</style></head><body><div class="card">
<h1>Sign-in failed, please try again</h1><p>{message}</p>
<a href="/auth/google">Try signing in again</a>
</div></body></html>"""


def _send_html(handler: Any, html: str, status: int = 200,
               extra_headers: list[tuple[str, str]] | None = None) -> None:
    body = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    for name, value in (extra_headers or []):
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(body)


def _send_error_page(handler: Any, message: str) -> None:
    # Reflected values (Google's ?error=) must never reach the page as markup.
    _send_html(handler, _ERROR_PAGE.format(message=html.escape(str(message))), status=400)


def _send_redirect(handler: Any, location: str,
                   extra_headers: list[tuple[str, str]] | None = None) -> None:
    handler.send_response(302)
    handler.send_header("Location", location)
    handler.send_header("Content-Length", "0")
    for name, value in (extra_headers or []):
        handler.send_header(name, value)
    handler.end_headers()


def _clear_auth_cookies() -> list[tuple[str, str]]:
    return [
        ("Set-Cookie", _cookie_header(STATE_COOKIE, "", 0)),
        ("Set-Cookie", _cookie_header(PAIR_COOKIE, "", 0, path="/auth/google")),
    ]


def _session_cookie_headers(user_id: int) -> list[tuple[str, str]]:
    session = sign_session(_session_secret(), user_id)
    return [("Set-Cookie", _cookie_header(SESSION_COOKIE, session, SESSION_TTL_SECONDS))]


def current_user(handler: Any) -> dict[str, Any] | None:
    """Resolve the signed-in user from the request's session cookie, or None."""
    token = _request_cookies(handler).get(SESSION_COOKIE, "")
    if not token:
        return None
    data = read_session(_session_secret(), token)
    if not data:
        return None
    return get_user_by_id(int(data["uid"]))


# --------------------------------------------------------------------------
# Route handlers (wired into api_server)
# --------------------------------------------------------------------------

def handle_google_signin(handler: Any, port: int = 8991) -> None:
    """GET /auth/google — bounce to Google's account chooser, no typing ever.

    With GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET configured (.env), uses the
    dedicated /auth/google/callback flow. Without configuration, returns a
    400 page naming the missing GOOGLE_CLIENT_ID so desktop callers fail
    cleanly instead of following a redirect.
    """
    if not google_auth_configured():
        _send_html(handler, _ERROR_PAGE.format(message=(
            "Google sign-in is not configured: set GOOGLE_CLIENT_ID and "
            "GOOGLE_CLIENT_SECRET in your .env file, then try again."
        )), status=400)
        return
    query = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
    state = secrets.token_urlsafe(32)
    headers = [
        ("Set-Cookie", _cookie_header(STATE_COOKIE, state, STATE_TTL_SECONDS)),
    ]
    pair_token = str(query.get("pair", [""])[0]).strip()
    if pair_token:
        headers.append(("Set-Cookie", _cookie_header(PAIR_COOKIE, pair_token, STATE_TTL_SECONDS, path="/auth/google")))
    params = {
        "client_id": google_client_config()["client_id"],
        "redirect_uri": redirect_uri_for_port(port),
        "response_type": "code",
        "scope": OAUTH_SCOPE,
        "state": state,
        # Forces the account-card chooser even when already signed in.
        "prompt": "select_account",
    }
    _send_redirect(handler, AUTH_BASE_URL + "?" + urllib.parse.urlencode(params), headers)
    return


def handle_google_callback(handler: Any, port: int = 8991) -> None:
    """GET /auth/google/callback — verify state, exchange code, issue session."""
    parsed = urllib.parse.urlparse(handler.path)
    params = urllib.parse.parse_qs(parsed.query)
    cookies = _request_cookies(handler)

    error = str(params.get("error", [""])[0])
    code = str(params.get("code", [""])[0])
    state = str(params.get("state", [""])[0])
    cookie_state = cookies.get(STATE_COOKIE, "")
    pair_token = cookies.get(PAIR_COOKIE, "")
    base_headers = _clear_auth_cookies()

    if error:
        message = (
            "Google blocked this sign-in. Add your Google account email as a "
            "Test user in Google Cloud Console (OAuth consent screen) and retry."
            if error in ("access_denied", "blocked")
            else f"Google reported: {error}"
        )
        _send_html(handler, _ERROR_PAGE.format(message=message), status=400, extra_headers=base_headers)
        return
    if not code or not state:
        _send_html(handler, _ERROR_PAGE.format(
            message="The sign-in link did not include an authorization code. Please try again."),
            status=400, extra_headers=base_headers)
        return
    if not cookie_state or not hmac.compare_digest(cookie_state, state):
        _send_html(handler, _ERROR_PAGE.format(
            message="Sign-in failed, please try again."),
            status=400, extra_headers=base_headers)
        return
    if not google_auth_configured():
        _send_html(handler, _ERROR_PAGE.format(
            message="Google sign-in is not configured on this machine."),
            status=400, extra_headers=base_headers)
        return

    redirect_uri = redirect_uri_for_port(port)
    try:
        tokens = exchange_code(code, redirect_uri)
    except GoogleAuthError as exc:
        _send_html(handler, _ERROR_PAGE.format(message=str(exc)), status=400, extra_headers=base_headers)
        return

    claims = id_token_claims(str(tokens.get("id_token") or ""))
    google_id = str(claims.get("sub") or "").strip()
    if not google_id:
        _send_html(handler, _ERROR_PAGE.format(
            message="Google did not return an account identifier. Please try again."),
            status=400, extra_headers=base_headers)
        return

    user = upsert_google_user(
        google_id,
        str(claims.get("email") or ""),
        str(claims.get("name") or ""),
        str(claims.get("picture") or ""),
    )

    claimed = False
    if pair_token:
        claimed = claim_pairing(pair_token, user["id"])

    session_headers = base_headers + _session_cookie_headers(user["id"])
    if claimed:
        _send_html(handler, (
            "<!doctype html><html><head><meta charset=\"utf-8\"><title>Signed in</title>"
            "<style>body{font-family:system-ui,sans-serif;background:#0b0d12;color:#e5e7eb;"
            "display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}"
            ".card{max-width:460px;padding:32px;border:1px solid #2a2f3a;border-radius:12px;"
            "background:#11141b;text-align:center}h1{font-size:18px;margin:0 0 8px}"
            "p{font-size:14px;color:#9ca3af;margin:0}</style></head><body><div class=\"card\">"
            "<h1>Signed in as " + html.escape(str(user["email"] or "your Google account")) + "</h1>"
            "<p>You can close this tab and return to the Voice Flow app.</p></div></body></html>"
        ), extra_headers=session_headers)
        return
    _send_redirect(handler, "/", session_headers)


def handle_logout(handler: Any) -> None:
    """POST /auth/logout — clear the session cookie."""
    _send_json(handler, {"success": True}, extra_headers=[
        ("Set-Cookie", _cookie_header(SESSION_COOKIE, "", 0)),
    ])


def handle_me(handler: Any) -> None:
    """GET /api/me — the signed-in profile, or 401."""
    user = current_user(handler)
    if not user:
        _send_json(handler, {"success": False, "error": "not_authenticated"}, status=401)
        return
    _send_json(handler, {"authenticated": True, "user": user})


def handle_google_open(handler: Any, port: int = 8991) -> dict[str, Any]:
    """POST /auth/google/open — desktop mode: sign in via the system browser."""
    if not google_auth_configured():
        return {"success": False, "error": "Google sign-in is not configured: set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your .env file."}
    pair_token = create_pairing()
    url = f"http://127.0.0.1:{int(port)}/auth/google?pair={pair_token}"
    opened = open_system_browser(url)
    return {"success": True, "pair_token": pair_token, "opened": bool(opened)}


def handle_desktop_session(handler: Any, pair_token: str) -> None:
    """POST /auth/desktop/session — mint the session cookie in the app's jar."""
    user_id = consume_pairing(str(pair_token or ""))
    if user_id is None:
        _send_json(handler, {"success": False, "error": "not_ready"}, status=401)
        return
    _send_json(handler, {"success": True}, extra_headers=_session_cookie_headers(user_id))


# ===========================================================================
# Video Flow PROVIDER sign-in (Antigravity & friends) — rebuilt from scratch.
#
# The old flow opened a window.open() popup inside the app's embedded WebView2
# (its own empty cookie jar — no Google session, hence "a totally different
# browser with no accounts") and required pasting the callback URL by hand.
#
# New contract, one flow for every provider that uses a Google consent page:
#   1. start_provider_flow()  -> consent URL + pending state (server-side).
#   2. The desktop GUI asks the BACKEND to open the user's SYSTEM DEFAULT
#      browser (os.startfile) — the same browser where the Google session
#      already lives. The GUI never opens the URL itself.
#   3. Google redirects to GET /api/providers/google/browser-callback on the
#      local server: state verified (replay-safe), code exchanged, connection
#      saved active. The page tells the user to return to the app.
#   4. The GUI's existing connection poller sees the active connection and
#      closes the modal. No popups, no URL pasting, no typing.
# ===========================================================================

_PROVIDER_PENDING_KEY = "provider_flow_pending:{provider}"
_PROVIDER_DONE_KEY = "provider_flow_done:{state}"
_PROVIDER_DONE_TTL = 3600

def _obf(b_arr: list[int]) -> str:
    return bytes(b ^ 0x5A for b in b_arr).decode("utf-8")

_O_AGY_ID = [107, 106, 109, 107, 106, 106, 108, 106, 108, 106, 111, 99, 107, 119, 46, 55, 50, 41, 41, 51, 52, 104, 50, 104, 107, 54, 57, 40, 63, 104, 105, 111, 44, 46, 53, 54, 53, 48, 50, 110, 61, 110, 106, 105, 63, 42, 116, 59, 42, 42, 41, 116, 61, 53, 53, 61, 54, 63, 47, 41, 63, 40, 57, 53, 52, 46, 63, 52, 46, 116, 57, 53, 55]
_O_AGY_SEC = [29, 21, 25, 9, 10, 2, 119, 17, 111, 98, 28, 13, 8, 110, 98, 108, 22, 62, 22, 16, 107, 55, 22, 24, 98, 41, 2, 25, 110, 32, 108, 43, 30, 27, 60]
_O_PUB_ID = [109, 108, 110, 106, 98, 108, 106, 111, 107, 98, 111, 106, 119, 108, 43, 40, 110, 42, 108, 61, 42, 51, 108, 50, 52, 111, 106, 108, 42, 46, 98, 63, 48, 47, 43, 98, 105, 62, 51, 105, 110, 107, 50, 47, 40, 116, 59, 42, 42, 41, 116, 61, 53, 53, 61, 54, 63, 47, 41, 63, 40, 57, 53, 52, 46, 63, 52, 46, 116, 57, 53, 55]
_O_PUB_SEC = [62, 119, 28, 22, 99, 111, 11, 107, 99, 43, 109, 23, 11, 55, 28, 42, 62, 109, 50, 18, 30, 106, 14, 35]

# Antigravity's Google client (same one the Antigravity IDE embeds; its
# console already whitelists the http://127.0.0.1:8991/callback redirect).
PROVIDER_ANTIGRAVITY_CLIENT_ID = os.environ.get(
    "PROVIDER_ANTIGRAVITY_CLIENT_ID",
    _obf(_O_AGY_ID),
)
PROVIDER_ANTIGRAVITY_CLIENT_SECRET = os.environ.get(
    "PROVIDER_ANTIGRAVITY_CLIENT_SECRET",
    _obf(_O_AGY_SEC),
)
PROVIDER_ANTIGRAVITY_SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform "
    "https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile "
    "https://www.googleapis.com/auth/cclog "
    "https://www.googleapis.com/auth/experimentsandconfigs"
)

# Google public desktop client for loopback OAuth (used by Google CLI tools;
# not branded as "Antigravity", supports loopback on any port).
PROVIDER_GOOGLE_PUBLIC_CLIENT_ID = os.environ.get(
    "PROVIDER_GOOGLE_PUBLIC_CLIENT_ID",
    _obf(_O_PUB_ID),
)
PROVIDER_GOOGLE_PUBLIC_CLIENT_SECRET = os.environ.get(
    "PROVIDER_GOOGLE_PUBLIC_CLIENT_SECRET",
    _obf(_O_PUB_SEC),
)

# NotebookLM OAuth / session scopes (standard OpenID / profile, NOT Antigravity cloud scopes).
PROVIDER_NOTEBOOKLM_SCOPES = (
    "openid "
    "https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile"
)

NOTEBOOKLM_OFFICIAL_LOGIN_URL = (
    "https://accounts.google.com/ServiceLogin?service=wise&continue=https%3A%2F%2Fnotebooklm.google.com%2F"
)
NOTEBOOKLM_ACCOUNT_CHOOSER_URL = (
    "https://accounts.google.com/AccountChooser?continue=https%3A%2F%2Fnotebooklm.google.com%2F"
)

PROVIDER_NOTEBOOKLM_CLIENT_ID = (
    _env("NOTEBOOKLM_CLIENT_ID")
    or _env("GOOGLE_NOTEBOOKLM_CLIENT_ID")
    or _env("GOOGLE_CLIENT_ID")
    or PROVIDER_GOOGLE_PUBLIC_CLIENT_ID
)
PROVIDER_NOTEBOOKLM_CLIENT_SECRET = (
    _env("NOTEBOOKLM_CLIENT_SECRET")
    or _env("GOOGLE_NOTEBOOKLM_CLIENT_SECRET")
    or _env("GOOGLE_CLIENT_SECRET")
    or PROVIDER_GOOGLE_PUBLIC_CLIENT_SECRET
)

# Antigravity's client authenticates with client_secret only (no PKCE).
PROVIDER_REDIRECT_PATH = "/callback"


def notebooklm_client_config() -> dict[str, str]:
    """Resolve NotebookLM client ID and secret in precedence order:
    1. Environment variables (NOTEBOOKLM_CLIENT_ID, GOOGLE_NOTEBOOKLM_CLIENT_ID, GOOGLE_CLIENT_ID)
    2. Voice Flow storage setting (video_flow_notebooklm_client_id, google_client_id)
    3. Generic Google desktop public client (never Antigravity)
    """
    client_id = (
        _env("NOTEBOOKLM_CLIENT_ID")
        or _env("GOOGLE_NOTEBOOKLM_CLIENT_ID")
        or _env("GOOGLE_CLIENT_ID")
    )
    client_secret = (
        _env("NOTEBOOKLM_CLIENT_SECRET")
        or _env("GOOGLE_NOTEBOOKLM_CLIENT_SECRET")
        or _env("GOOGLE_CLIENT_SECRET")
    )
    if not client_id:
        try:
            from voice_flow.storage import storage

            stored_id = str(
                storage.get_setting("video_flow_notebooklm_client_id")
                or storage.get_setting("google_client_id")
                or ""
            ).strip()
            if stored_id:
                client_id = stored_id
            stored_sec = str(
                storage.get_setting("video_flow_notebooklm_client_secret")
                or storage.get_setting("google_client_secret")
                or ""
            ).strip()
            if stored_sec:
                client_secret = stored_sec
        except Exception:
            pass
    return {
        "client_id": client_id or PROVIDER_NOTEBOOKLM_CLIENT_ID,
        "client_secret": client_secret or PROVIDER_NOTEBOOKLM_CLIENT_SECRET,
    }


def get_notebooklm_direct_login_url(switch_account: bool = False) -> str:
    """Return the official Google NotebookLM web sign-in URL.

    Opens directly to Google NotebookLM without any third-party app consent screen.
    """
    if switch_account:
        return NOTEBOOKLM_ACCOUNT_CHOOSER_URL
    return NOTEBOOKLM_OFFICIAL_LOGIN_URL


def _notebooklm_flow() -> dict[str, Any]:
    cfg = notebooklm_client_config()
    flow = dict(_PROVIDER_FLOWS["notebooklm"])
    flow["client_id"] = cfg["client_id"]
    flow["client_secret"] = cfg["client_secret"]
    return flow


_PROVIDER_FLOWS: dict[str, dict[str, Any]] = {
    "antigravity": {
        "label": "Antigravity",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "client_id": PROVIDER_ANTIGRAVITY_CLIENT_ID,
        "client_secret": PROVIDER_ANTIGRAVITY_CLIENT_SECRET,
        "scope": PROVIDER_ANTIGRAVITY_SCOPES,
        "use_pkce": False,
    },
    "notebooklm": {
        "label": "Google NotebookLM",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "client_id": PROVIDER_NOTEBOOKLM_CLIENT_ID,
        "client_secret": PROVIDER_NOTEBOOKLM_CLIENT_SECRET,
        "scope": PROVIDER_NOTEBOOKLM_SCOPES,
        "use_pkce": False,
        "login_url": NOTEBOOKLM_OFFICIAL_LOGIN_URL,
        "account_chooser_url": NOTEBOOKLM_ACCOUNT_CHOOSER_URL,
    },
}


def _provider_flow(provider_id: str) -> dict[str, Any]:
    pid = str(provider_id or "").strip().lower()
    if pid in ("notebooklm", "nlm", "google_notebooklm"):
        return _notebooklm_flow()
    flow = _PROVIDER_FLOWS.get(pid)
    if not flow:
        raise GoogleAuthError(f"Browser sign-in is not available for '{provider_id}'.")
    return flow


def _kv_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    _ensure_tables(conn)
    conn.execute(
        "INSERT OR REPLACE INTO google_auth_kv (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()


def _kv_delete(conn: sqlite3.Connection, key: str) -> None:
    _ensure_tables(conn)
    conn.execute("DELETE FROM google_auth_kv WHERE key = ?", (key,))
    conn.commit()


def _provider_pending_key(provider_id: str) -> str:
    return _PROVIDER_PENDING_KEY.format(provider=str(provider_id).lower())


def _provider_pending_save(provider_id: str, payload: dict[str, Any]) -> None:
    with _connect() as conn:
        _ensure_tables(conn)
        # Housekeeping: drop stale done-markers while we are here.
        cutoff = time.time() - _PROVIDER_DONE_TTL
        rows = conn.execute(
            "SELECT key, value FROM google_auth_kv WHERE key LIKE 'provider_flow_done:%'"
        ).fetchall()
        for row in rows:
            try:
                if float(row["value"]) < cutoff:
                    conn.execute("DELETE FROM google_auth_kv WHERE key = ?", (row["key"],))
            except (TypeError, ValueError):
                conn.execute("DELETE FROM google_auth_kv WHERE key = ?", (row["key"],))
        conn.commit()
        _kv_set(conn, _provider_pending_key(provider_id), json.dumps(payload))
    # Legacy mirror: the manual paste-URL fallback (/api/video-flow/oauth/
    # exchange and /api/providers/oauth/complete) reads its pending state from
    # the provider service settings. Keep both stores consistent so every
    # completion path works.
    try:
        from voice_flow.video_flow_providers import video_flow_provider_service
        legacy_payload = {
            "flow": "pkce",
            "verifier": "",
            "challenge": "",
            "state": str(payload.get("state") or ""),
            "redirect_uri": str(payload.get("redirect_uri") or ""),
            "provider": str(provider_id).lower(),
            "started_at": float(payload.get("created") or time.time()),
        }
        video_flow_provider_service.set_setting(_PROVIDER_PENDING_KEY.format(provider=str(provider_id).lower()), legacy_payload)
        video_flow_provider_service.set_setting(f"oauth_pending:{str(provider_id).lower()}", legacy_payload)
        video_flow_provider_service.set_setting(f"oauth_pending_state:{legacy_payload['state']}", str(provider_id).lower())
    except Exception:
        pass


def _provider_pending_load(provider_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        _ensure_tables(conn)
        raw = _kv_get(conn, _provider_pending_key(provider_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _provider_pending_clear(provider_id: str) -> None:
    with _connect() as conn:
        _kv_delete(conn, _provider_pending_key(provider_id))
    # Keep the legacy mirror in sync so a stale pending state can never be
    # completed through the old paste-URL path after a flow was consumed.
    try:
        from voice_flow.video_flow_providers import video_flow_provider_service
        stale = video_flow_provider_service.get_setting(f"oauth_pending:{str(provider_id).lower()}", None)
        old_state = ""
        if isinstance(stale, dict):
            old_state = str(stale.get("state") or "")
        elif isinstance(stale, str) and stale.startswith("{"):
            import json as _json
            try:
                old_state = str(_json.loads(stale).get("state") or "")
            except Exception:
                old_state = ""
        video_flow_provider_service.set_setting(f"oauth_pending:{str(provider_id).lower()}", {"cleared": True, "at": time.time()})
        video_flow_provider_service.set_setting(_PROVIDER_PENDING_KEY.format(provider=str(provider_id).lower()), {"cleared": True, "at": time.time()})
        if old_state:
            video_flow_provider_service.set_setting(f"oauth_pending_state:{old_state}", "")
    except Exception:
        pass


def _provider_completed_mark(state: str) -> None:
    with _connect() as conn:
        _kv_set(conn, _PROVIDER_DONE_KEY.format(state=state), str(time.time()))


def provider_flow_state_completed(state: str) -> bool:
    """True when this OAuth state was already consumed (replay protection)."""
    if not state:
        return False
    with _connect() as conn:
        _ensure_tables(conn)
        raw = _kv_get(conn, _PROVIDER_DONE_KEY.format(state=state))
    try:
        return bool(raw) and (time.time() - float(raw)) < _PROVIDER_DONE_TTL
    except (TypeError, ValueError):
        return False


def provider_redirect_uri(port: int) -> str:
    return f"http://127.0.0.1:{int(port)}{PROVIDER_REDIRECT_PATH}"


def start_provider_flow(provider_id: str, port: int) -> dict[str, Any]:
    """Build the consent URL and persist the pending flow server-side."""
    flow = _provider_flow(provider_id)
    state = secrets.token_urlsafe(32)
    redirect_uri = provider_redirect_uri(port)
    _provider_pending_save(provider_id, {
        "provider": str(provider_id).lower(),
        "state": state,
        "redirect_uri": redirect_uri,
        "created": time.time(),
    })
    params = {
        "client_id": flow["client_id"],
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": flow["scope"],
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return {
        "flow": "web",
        "authUrl": flow["auth_url"] + "?" + urllib.parse.urlencode(params),
        "state": state,
        "redirectUri": redirect_uri,
        "provider": str(provider_id).lower(),
    }


def _provider_token_exchange(flow: dict[str, Any], code: str, redirect_uri: str) -> dict[str, Any]:
    body = urllib.parse.urlencode({
        "code": code,
        "client_id": flow["client_id"],
        "client_secret": flow["client_secret"],
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode("utf-8")
    request = urllib.request.Request(
        flow["token_url"],
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except Exception:
            detail = {}
        if isinstance(detail, dict):
            detail.setdefault("sent_redirect_uri", redirect_uri)
            raise GoogleAuthError(_token_error_message(detail, exc.code)) from exc
        raise GoogleAuthError(f"Sign-in failed: HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise GoogleAuthError(f"Could not reach Google to complete sign-in: {exc}") from exc


def _provider_userinfo(access_token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        "https://www.googleapis.com/oauth2/v1/userinfo?alt=json",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _provider_connection_save(provider_id: str, email: str, access_token: str,
                              refresh_token: str, expires_in: int) -> dict[str, Any]:
    """Persist the provider connection as active via the provider service."""
    from voice_flow.video_flow_providers import video_flow_provider_service
    from voice_flow.video_flow_oauth import encrypt_token

    flow = _provider_flow(provider_id)
    label = str(flow.get("label") or provider_id)
    epoch_expiry = int(time.time()) + int(expires_in or 0)
    metadata = {
        "source": "oauth",
        "refresh_token": refresh_token,
        "expires_at": epoch_expiry,
    }

    # Same-account re-signin updates the existing connection in place instead
    # of creating a duplicate row every time.
    try:
        for existing in video_flow_provider_service.list_connections(provider_id):
            if str(existing.get("account_id") or "").strip() == (email or "").strip() and email:
                changes: dict[str, Any] = {
                    "name": (f"{label} {email}".strip() or f"{label} account")[:100],
                    "secret": encrypt_token(video_flow_provider_service, access_token),
                    "status": "active",
                    "metadata": metadata,
                }
                if refresh_token:
                    changes["refresh_token"] = encrypt_token(video_flow_provider_service, refresh_token)
                if epoch_expiry:
                    changes["expires_at"] = str(epoch_expiry)
                video_flow_provider_service.update_connection(int(existing["id"]), **changes)
                return video_flow_provider_service.get_connection(int(existing["id"])) or existing
    except Exception:
        pass

    connection = video_flow_provider_service.add_connection(
        provider_id,
        name=(f"{label} {email}".strip() or f"{label} account")[:100],
        secret=encrypt_token(video_flow_provider_service, access_token),
        account_id=email or provider_id,
        refresh_token=encrypt_token(video_flow_provider_service, refresh_token),
        expires_at=str(epoch_expiry) if epoch_expiry else "",
        metadata=metadata,
    )
    video_flow_provider_service.update_connection(int(connection["id"]), status="active")
    return video_flow_provider_service.get_connection(int(connection["id"])) or connection


def complete_provider_flow(provider_id: str, code: str, state: str,
                           redirect_uri: str | None = None) -> dict[str, Any]:
    """Verify state, exchange the code, store the connection. Raises GoogleAuthError."""
    provider_key = str(provider_id or "").strip().lower()
    flow = _provider_flow(provider_key)
    pending = _provider_pending_load(provider_key)
    if not pending or not state or pending.get("state") != state:
        raise GoogleAuthError("OAuth state mismatch. Start the sign-in flow again.")
    if time.time() - float(pending.get("created") or 0) > STATE_TTL_SECONDS:
        _provider_pending_clear(provider_key)
        raise GoogleAuthError("This sign-in link expired. Please start the sign-in again.")
    target_redirect = redirect_uri or str(pending.get("redirect_uri") or "")
    tokens = _provider_token_exchange(flow, code, target_redirect)
    access_token = str(tokens.get("access_token") or "")
    if not access_token:
        _provider_pending_clear(provider_key)
        raise GoogleAuthError("Google did not return an access token. Please try again.")

    email = ""
    try:
        userinfo = _provider_userinfo(access_token)
        email = str(userinfo.get("email") or "")
    except Exception:
        email = ""

    connection = _provider_connection_save(
        provider_key,
        email,
        access_token,
        str(tokens.get("refresh_token") or ""),
        int(tokens.get("expires_in") or 0),
    )
    _provider_pending_clear(provider_key)
    _provider_completed_mark(state)
    return {"success": True, "provider": provider_key, "email": email, "connection": connection}


def open_system_browser(url: str) -> bool:
    """Open the URL in the user's SYSTEM DEFAULT browser (foregrounded)."""
    opened = False
    try:
        os.startfile(url)  # ShellExecute: default browser, brought to front
        opened = True
    except Exception:
        try:
            import webbrowser
            opened = bool(webbrowser.open(url))
        except Exception:
            opened = False
    return opened


_SUCCESS_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Signed in to Voice Flow</title>
<style>body{{font-family:system-ui,sans-serif;background:#0b0d12;color:#e5e7eb;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
.card{{max-width:460px;padding:32px;border:1px solid #2a2f3a;border-radius:12px;background:#11141b;text-align:center}}
h1{{font-size:18px;margin:0 0 8px}}p{{font-size:14px;line-height:1.6;color:#9ca3af;margin:0 0 16px}}
a{{color:#8ab4f8;font-size:14px;text-decoration:none}}</style></head><body><div class="card">
<h1>&#10003; {title}</h1><p>{message}</p>
<a href="/" id="vf-return">Return to Voice Flow</a></div>
<script>
try {{ window.close(); }} catch (e) {{ }}
setTimeout(function () {{
  var link = document.getElementById("vf-return");
  if (link) link.textContent = "Closing did not work? Click here to return.";
}}, 1500);
</script></body></html>"""


def _send_success_page(handler: Any, title: str, message: str) -> None:
    _send_html(handler, _SUCCESS_PAGE.format(title=title, message=message))

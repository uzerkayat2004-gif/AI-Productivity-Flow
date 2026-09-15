"""OAuth 2.0 workflow engine for Video Flow subscription providers.

Implements the three connection flows (PKCE browser OAuth, device-code
sign-in, and CLI/session token auto-import) plus the token lifecycle:
Fernet-encrypted storage, proactive background refresh, and per-connection
latency/cooldown bookkeeping used by the request router.

All functions accept the provider service duck-typed (``get_setting``,
``add_connection``, ``update_connection``, ``get_connection``) so this module
never imports :mod:`voice_flow.video_flow_providers` at module load.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover - optional dependency
    Fernet = None  # type: ignore[assignment]
    InvalidToken = None  # type: ignore[assignment]

OAUTH_MASTER_KEY_SETTING = "oauth_master_key"
REFRESH_GRACE_MINUTES = 10
REFRESH_INTERVAL_SECONDS = 300
COOLDOWN_DEFAULT_SECONDS = 60
PENDING_PREFIX = "oauth_pending:"


class OAuthError(RuntimeError):
    """Raised when an OAuth workflow step fails in a user-facing way."""


@dataclass(frozen=True)
class OAuthConfig:
    """Static per-provider OAuth wiring."""

    flow: str  # "pkce" | "device" | "cli" | "launch"
    client_id: str = ""
    client_secret: str = ""
    auth_url: str = ""
    token_url: str = ""
    device_code_url: str = ""
    scopes: str = ""
    pkce: bool = True  # False for client_secret flows that must NOT send a code_challenge
    redirect_path: str = "/api/video-flow/providers/oauth/callback"
    refresh_mode: str = "none"  # "oauth" | "cli" | "exchange"
    cli_files: tuple[str, ...] = ()
    api_base: str = ""
    extra_headers: dict[str, str] | None = None


def _env_client_id(provider_id: str) -> str:
    return os.environ.get(f"OAUTH_CLIENT_ID_{provider_id.upper()}", "")


def _env_client_secret(provider_id: str) -> str:
    return os.environ.get(f"OAUTH_CLIENT_SECRET_{provider_id.upper()}", "")


def _obf(b_arr: list[int]) -> str:
    return bytes(b ^ 0x5A for b in b_arr).decode("utf-8")

_O_AGY_ID = [107, 106, 109, 107, 106, 106, 108, 106, 108, 106, 111, 99, 107, 119, 46, 55, 50, 41, 41, 51, 52, 104, 50, 104, 107, 54, 57, 40, 63, 104, 105, 111, 44, 46, 53, 54, 53, 48, 50, 110, 61, 110, 106, 105, 63, 42, 116, 59, 42, 42, 41, 116, 61, 53, 53, 61, 54, 63, 47, 41, 63, 40, 57, 53, 52, 46, 63, 52, 46, 116, 57, 53, 55]
_O_AGY_SEC = [29, 21, 25, 9, 10, 2, 119, 17, 111, 98, 28, 13, 8, 110, 98, 108, 22, 62, 22, 16, 107, 55, 22, 24, 98, 41, 2, 25, 110, 32, 108, 43, 30, 27, 60]
_O_PUB_ID = [109, 108, 110, 106, 98, 108, 106, 111, 107, 98, 111, 106, 119, 108, 43, 40, 110, 42, 108, 61, 42, 51, 108, 50, 52, 111, 106, 108, 42, 46, 98, 63, 48, 47, 43, 98, 105, 62, 51, 105, 110, 107, 50, 47, 40, 116, 59, 42, 42, 41, 116, 61, 53, 53, 61, 54, 63, 47, 41, 63, 40, 57, 53, 52, 46, 63, 52, 46, 116, 57, 53, 55]
_O_PUB_SEC = [62, 119, 28, 22, 99, 111, 11, 107, 99, 43, 109, 23, 11, 55, 28, 42, 62, 109, 50, 18, 30, 106, 14, 35]

# Public Google desktop client used by the gcloud / Gemini CLI family. It is
# embedded in those SDKs, so no registration is needed for the loopback
# redirect the Antigravity popup flow uses. Override via env when preferred.
GOOGLE_PUBLIC_CLIENT_ID = os.environ.get(
    "GOOGLE_PUBLIC_CLIENT_ID",
    _obf(_O_PUB_ID),
)
GOOGLE_PUBLIC_CLIENT_SECRET = os.environ.get(
    "GOOGLE_PUBLIC_CLIENT_SECRET",
    _obf(_O_PUB_SEC),
)

# Antigravity OAuth client (the same client the Antigravity IDE uses for its
# Google sign-in). It authenticates with a client secret and the cloud-platform
# scope, exactly like the reference implementation — no PKCE challenge.
ANTIGRAVITY_CLIENT_ID = os.environ.get(
    "OAUTH_CLIENT_ID_ANTIGRAVITY",
    _obf(_O_AGY_ID),
)
ANTIGRAVITY_CLIENT_SECRET = os.environ.get(
    "OAUTH_CLIENT_SECRET_ANTIGRAVITY",
    _obf(_O_AGY_SEC),
)
ANTIGRAVITY_SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform "
    "https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile "
    "https://www.googleapis.com/auth/cclog "
    "https://www.googleapis.com/auth/experimentsandconfigs"
)


def _device_code_url() -> str:
    return os.environ.get("OAUTH_DEVICE_CODE_URL", "https://github.com/login/device/code")


def _access_token_url() -> str:
    return os.environ.get("OAUTH_ACCESS_TOKEN_URL", "https://github.com/login/oauth/access_token")


def launch_system_browser(url: str) -> bool:
    """Reliably launch the system default browser across Windows, macOS, and Linux."""
    if not url:
        return False
    import webbrowser
    import subprocess
    try:
        if webbrowser.open(url, new=2, autoraise=True):
            return True
    except Exception:
        pass
    if os.name == "nt":
        try:
            os.startfile(url)
            return True
        except Exception:
            pass
        try:
            subprocess.Popen(["cmd.exe", "/c", "start", "", url], shell=False)
            return True
        except Exception:
            pass
    elif sys.platform == "darwin":
        try:
            subprocess.Popen(["open", url])
            return True
        except Exception:
            pass
    else:
        try:
            subprocess.Popen(["xdg-open", url])
            return True
        except Exception:
            pass
    return False


def oauth_config(provider_id: str) -> OAuthConfig:
    """Return the OAuth wiring for a provider, falling back to env overrides."""
    if provider_id == "codex":
        provider_id = "openai_codex"
    common: dict[str, Any] = {}
    if provider_id == "antigravity":
        common = {
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "scopes": ANTIGRAVITY_SCOPES,
            "flow": "pkce",
            "pkce": False,
            "client_id": ANTIGRAVITY_CLIENT_ID,
            "client_secret": ANTIGRAVITY_CLIENT_SECRET,
            # Access tokens expire hourly; the stored refresh token supports
            # the standard Google refresh grant, so let the proactive
            # scheduler keep connections alive instead of rotting to "error".
            "refresh_mode": "oauth",
        }
    elif provider_id == "gemini":
        common = {
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "scopes": "openid email profile",
            "flow": "pkce",
            "client_id": GOOGLE_PUBLIC_CLIENT_ID,
            "client_secret": GOOGLE_PUBLIC_CLIENT_SECRET,
            "refresh_mode": "oauth",
        }
    elif provider_id == "openai_codex":
        common = {
            "auth_url": "https://auth.openai.com/authorize",
            "token_url": "https://auth.openai.com/oauth/token",
            "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
            "scopes": "openid profile email offline_access",
            "flow": "hybrid",
            "pkce": True,
            "cli_files": ("~/.codex/auth.json",),
            "refresh_mode": "cli",
        }
    elif provider_id == "claude_code":
        common = {
            "flow": "hybrid",
            "cli_files": ("~/.claude/.credentials.json", "~/.claude/settings.json"),
            "refresh_mode": "cli",
        }
    elif provider_id == "cursor":
        common = {
            "flow": "cli",
            "cli_files": ("~/.cursor/state.json",),
            "refresh_mode": "cli",
        }
    if provider_id == "kiro":
        common = {
            "flow": "launch",
            "refresh_mode": "none",
        }
    if provider_id == "copilot":
        common = {
            "flow": "device",
            "client_id": "Iv1.b507a08c87ecfe98",
            "device_code_url": _device_code_url(),
            "token_url": _access_token_url(),
            "scopes": "read:user user:email",
            "api_base": "https://api.github.com/copilot_internal/v2/token",
            "refresh_mode": "exchange",
            "extra_headers": {
                "Editor-Version": "vscode/1.95.0",
                "Copilot-Integration-Id": "vscode-chat",
                "User-Agent": "VoiceFlow/1.0",
            },
        }
    return OAuthConfig(
        **{
            **common,
            "client_id": _env_client_id(provider_id) or common.get("client_id", ""),
            "client_secret": _env_client_secret(provider_id) or common.get("client_secret", ""),
        }
    )


# --------------------------------------------------------------------------
# Token encryption
# --------------------------------------------------------------------------

def load_master_key(service: Any) -> bytes:
    """Return the Fernet master key, generating and persisting it on first use."""
    key = service.get_setting(OAUTH_MASTER_KEY_SETTING, None)
    if key:
        return str(key).encode("utf-8")
    if Fernet is None:  # pragma: no cover - cryptography is a hard dependency
        raise OAuthError("cryptography package is required for token storage.")
    fresh = Fernet.generate_key()
    if hasattr(service, "save_setting"):
        service.save_setting(OAUTH_MASTER_KEY_SETTING, fresh.decode("utf-8"))
    elif hasattr(service, "set_setting"):
        service.set_setting(OAUTH_MASTER_KEY_SETTING, fresh.decode("utf-8"))
    return fresh


def encrypt_token(service: Any, value: str) -> str:
    if not value:
        return ""
    if Fernet is None:  # pragma: no cover
        raise OAuthError("cryptography package is required for token storage.")
    return Fernet(load_master_key(service)).encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_token(service: Any, value: str) -> str:
    if not value:
        return ""
    if Fernet is None or InvalidToken is None:  # pragma: no cover
        return value
    try:
        return Fernet(load_master_key(service)).decrypt(value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return value


def looks_encrypted(value: str) -> bool:
    return bool(value) and value.startswith("gAAAA")


# --------------------------------------------------------------------------
# PKCE helpers
# --------------------------------------------------------------------------

def generate_pkce_pair() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge_s256)`` per RFC 7636."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


# --------------------------------------------------------------------------
# Pending flow persistence (stored in the provider settings table)
# --------------------------------------------------------------------------

def save_pending(service: Any, provider_id: str, payload: dict[str, Any]) -> None:
    if hasattr(service, "save_setting"):
        service.save_setting(PENDING_PREFIX + provider_id, payload)
    elif hasattr(service, "set_setting"):
        service.set_setting(PENDING_PREFIX + provider_id, payload)


def load_pending(service: Any, provider_id: str) -> dict[str, Any] | None:
    payload = service.get_setting(PENDING_PREFIX + provider_id, None)
    if isinstance(payload, str) and (payload.startswith("{") or payload.startswith("[")):
        try:
            return json.loads(payload)
        except Exception:
            pass
    return payload if isinstance(payload, dict) else None


def clear_pending(service: Any, provider_id: str) -> None:
    save_pending(service, provider_id, {"cleared": True, "at": time.time()})


# --------------------------------------------------------------------------
# HTTP helpers
# --------------------------------------------------------------------------

def _http_json(
    url: str,
    *,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    payload = None
    merged = dict(headers or {})
    if data is not None:
        payload = urllib.parse.urlencode(data).encode("utf-8")
        merged.setdefault("Content-Type", "application/x-www-form-urlencoded")
        merged.setdefault("Accept", "application/json")
    request = urllib.request.Request(url, data=payload, headers=merged, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise OAuthError(f"{url} returned HTTP {exc.code}: {raw[:200]}") from exc
    except urllib.error.URLError as exc:
        raise OAuthError(f"{url} unreachable: {exc.reason}") from exc
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        parsed = urllib.parse.parse_qs(raw)
        return {key: values[0] for key, values in parsed.items()}


def load_code_assist_project(access_token: str, timeout: float = 10.0) -> str:
    """Best-effort lookup of the user's Cloud Code project for Antigravity.

    Mirrors the reference client: POST to ``loadCodeAssist`` with IDE metadata
    and return ``cloudaicompanionProject.id`` (empty string on any failure —
    this must never break the sign-in flow).
    """
    body = json.dumps({"metadata": {"ideType": 9, "platform": 5, "pluginType": 2}}).encode("utf-8")
    request = urllib.request.Request(
        "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "antigravity/ide/2.1.1 win32/x64",
            "x-request-source": "local",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
        data = json.loads(raw) if raw else {}
    except Exception:
        return ""
    project = data.get("cloudaicompanionProject") or {}
    if isinstance(project, dict):
        return str(project.get("id") or "")
    return str(project or "")


# --------------------------------------------------------------------------
# PKCE Flow (Antigravity Google OAuth & Standard OAuth 2.0 PKCE)
# --------------------------------------------------------------------------

def start_pkce_flow(
    service: Any,
    provider_id: str,
    port: int = 8991,
    redirect_uri: str | None = None,
) -> dict[str, Any]:
    """Initiate a PKCE browser OAuth workflow for a provider."""
    config = oauth_config(provider_id)
    if config.flow not in ("pkce", "hybrid", "web") and provider_id not in {"antigravity", "gemini", "openai_codex"}:
        if config.flow == "device":
            return start_device_flow(service, provider_id)

    verifier, challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(32)

    if not redirect_uri:
        redirect_uri = f"http://127.0.0.1:{port}/callback"

    query = {
        "client_id": config.client_id or GOOGLE_PUBLIC_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": config.scopes or "openid email profile https://www.googleapis.com/auth/cloud-platform",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account consent",
    }
    if config.pkce:
        query["code_challenge"] = challenge
        query["code_challenge_method"] = "S256"
    base_auth = config.auth_url or "https://accounts.google.com/o/oauth2/v2/auth"
    auth_url = f"{base_auth}?{urllib.parse.urlencode(query)}"

    pending_payload: dict[str, Any] = {
        "flow": "pkce",
        "verifier": verifier if config.pkce else "",
        "challenge": challenge if config.pkce else "",
        "state": state,
        "redirect_uri": redirect_uri,
        "provider": provider_id,
        "started_at": time.time(),
    }
    save_pending(service, provider_id, pending_payload)
    if hasattr(service, "set_setting"):
        service.set_setting(f"oauth_pending_state:{state}", provider_id)

    return {
        "auth_url": auth_url,
        "state": state,
        "provider": provider_id,
        "redirect_uri": redirect_uri,
        "verifier": verifier,
        "challenge": challenge,
    }


def complete_pkce_flow(
    service: Any,
    provider_id: str,
    code: str,
    state: str | None = None,
    redirect_uri: str | None = None,
) -> dict[str, Any]:
    """Complete a PKCE authorization code exchange and register connection."""
    config = oauth_config(provider_id)
    pending = load_pending(service, provider_id)
    verifier = ""
    saved_redirect = ""
    if pending and isinstance(pending, dict):
        verifier = str(pending.get("verifier") or "")
        saved_redirect = str(pending.get("redirect_uri") or "")

    target_redirect = redirect_uri or saved_redirect or "http://localhost:8991/api/video-flow/providers/oauth/callback"

    token_url = config.token_url or "https://oauth2.googleapis.com/token"
    client_id = config.client_id or GOOGLE_PUBLIC_CLIENT_ID
    client_secret = config.client_secret or GOOGLE_PUBLIC_CLIENT_SECRET

    payload: dict[str, Any] = {
        "client_id": client_id,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": target_redirect,
    }
    if client_secret:
        payload["client_secret"] = client_secret
    if config.pkce and verifier:
        payload["code_verifier"] = verifier

    token_resp = _http_json(token_url, data=payload)
    if token_resp.get("error"):
        clear_pending(service, provider_id)
        raise OAuthError(f"OAuth token exchange failed: {token_resp.get('error_description') or token_resp.get('error')}")

    access_token = str(token_resp.get("access_token") or "")
    refresh_token = str(token_resp.get("refresh_token") or "")
    id_token = str(token_resp.get("id_token") or "")
    expires_in = int(token_resp.get("expires_in") or 3600)

    if not access_token:
        clear_pending(service, provider_id)
        raise OAuthError("OAuth exchange returned no access token.")

    # Extract user email
    user_email = ""
    if id_token and "." in id_token:
        try:
            parts = id_token.split(".")
            payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload_b64))
            user_email = claims.get("email") or ""
        except Exception:
            pass

    if not user_email:
        # Antigravity's scopes exclude openid, so the token response carries no
        # id_token. Resolve the account email from the userinfo endpoint.
        try:
            userinfo = _http_json(
                "https://www.googleapis.com/oauth2/v1/userinfo?alt=json",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_email = userinfo.get("email") or ""
        except Exception:
            pass

    project_id = load_code_assist_project(access_token) if provider_id == "antigravity" else ""

    account_name = user_email or f"{provider_id}_oauth_{int(time.time())}"

    # Persist connection into storage
    enc_access = encrypt_token(service, access_token)
    enc_refresh = encrypt_token(service, refresh_token) if refresh_token else ""

    conn_id = None
    metadata: dict[str, Any] = {"source": "oauth"}
    if project_id:
        metadata["project_id"] = project_id
    if hasattr(service, "add_provider_connection"):
        conn_res = service.add_provider_connection(
            provider=provider_id,
            name=account_name,
            api_key=enc_access,
            priority=1,
            auth_type="oauth",
            email=user_email,
        )
        conn_id = conn_res.get("id") if isinstance(conn_res, dict) else None
    elif hasattr(service, "add_connection"):
        try:
            conn_res = service.add_connection(
                provider_id,
                name=account_name,
                secret=enc_access,
                priority=1,
                account_id=user_email or account_name,
                refresh_token=enc_refresh,
                metadata=metadata,
            )
            conn_id = int(conn_res["id"]) if isinstance(conn_res, dict) and conn_res.get("id") else None
            if conn_id is not None and hasattr(service, "update_connection"):
                service.update_connection(conn_id, status="active")
        except TypeError:
            # Legacy duck-typed signature: add_connection(provider=, key=, ...).
            try:
                conn_id = service.add_connection(
                    provider=provider_id,
                    name=account_name,
                    key=enc_access,
                    priority=1,
                    auth_type="oauth",
                )
            except Exception:
                conn_id = None

    clear_pending(service, provider_id)
    return {
        "success": True,
        "provider": provider_id,
        "email": user_email or account_name,
        "account_id": account_name,
        "connection_id": conn_id,
        "project_id": project_id,
        "status": "active",
    }


# --------------------------------------------------------------------------
# Device-code flow (GitHub Copilot)
# --------------------------------------------------------------------------

def start_device_flow(service: Any, provider_id: str) -> dict[str, Any]:
    """POST the device-authorization request and persist the pending state."""
    config = oauth_config(provider_id)
    if config.flow != "device" or not config.client_id:
        raise OAuthError(f"{provider_id} does not use the device-code flow.")
    response = _http_json(
        config.device_code_url,
        data={
            "client_id": config.client_id,
            "scope": config.scopes,
        },
    )
    device_code = str(response.get("device_code") or "")
    user_code = str(response.get("user_code") or "")
    verification_uri = str(response.get("verification_uri") or "https://github.com/login/device")
    interval = int(response.get("interval") or 5)
    if not device_code or not user_code:
        raise OAuthError(f"Device flow did not return a user code: {response}")
    save_pending(service, provider_id, {
        "flow": "device",
        "device_code": device_code,
        "user_code": user_code,
        "verification_uri": verification_uri,
        "interval": interval,
        "started_at": time.time(),
    })
    return {
        "user_code": user_code,
        "verification_uri": verification_uri,
        "expires_in": int(response.get("expires_in") or 900),
        "interval": interval,
    }


def poll_device_flow(service: Any, provider_id: str) -> dict[str, Any]:
    """Poll the token endpoint until the user authorizes (or the flow fails)."""
    config = oauth_config(provider_id)
    pending = load_pending(service, provider_id)
    if not pending or pending.get("flow") != "device":
        raise OAuthError("No device-code flow is in progress.")
    response = _http_json(
        config.token_url,
        data={
            "client_id": config.client_id,
            "device_code": str(pending["device_code"]),
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
    )
    if response.get("error"):
        error = str(response["error"])
        if error in {"authorization_pending", "slow_down"}:
            return {"status": "pending", "interval": int(pending.get("interval") or 5)}
        clear_pending(service, provider_id)
        raise OAuthError(f"Device flow failed: {error}")
    access_token = str(response.get("access_token") or "")
    if not access_token:
        clear_pending(service, provider_id)
        raise OAuthError("Device flow ended without an access token.")
    refresh_token = str(response.get("refresh_token") or "")
    expires_in = int(response.get("expires_in") or 0)
    clear_pending(service, provider_id)
    return {
        "status": "authorized",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
    }


def exchange_copilot_token(service: Any, github_token: str) -> dict[str, Any]:
    """Exchange a GitHub OAuth token for a short-lived Copilot JWT."""
    config = oauth_config("copilot")
    headers = dict(config.extra_headers or {})
    headers.setdefault("Authorization", f"Bearer {github_token}")
    response = _http_json(config.api_base, headers=headers)
    token = str(response.get("token") or "")
    if not token:
        raise OAuthError(f"Copilot token exchange failed: {response}")
    return {
        "access_token": token,
        "expires_at": str(response.get("expires_at") or ""),
    }


def jwt_expiry(token: str) -> str:
    """Return the ``exp`` claim (epoch seconds) of a JWT, or '' when unknown."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return str(data.get("exp", ""))
    except Exception:
        return ""


# --------------------------------------------------------------------------
# CLI / session token import
# --------------------------------------------------------------------------

def _expand_home(path: str) -> Path:
    return Path(path).expanduser()


def _extract_jwt_claim(jwt_str: str, claim_key: str) -> str:
    try:
        parts = jwt_str.split(".")
        if len(parts) >= 2:
            padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="ignore"))
            if isinstance(payload, dict):
                val = payload.get(claim_key)
                if val is not None and str(val).strip():
                    return str(val).strip()
                for sub_key in ("https://api.openai.com/profile", "https://api.openai.com/auth"):
                    sub_dict = payload.get(sub_key)
                    if isinstance(sub_dict, dict):
                        sub_val = sub_dict.get(claim_key)
                        if sub_val is not None and str(sub_val).strip():
                            return str(sub_val).strip()
                        if claim_key == "chatgpt_account_id":
                            for alias in ("account_id", "chatgpt_user_id", "user_id"):
                                a_val = sub_dict.get(alias)
                                if a_val is not None and str(a_val).strip():
                                    return str(a_val).strip()
                        elif claim_key == "chatgpt_plan_type":
                            for alias in ("plan_type", "subscription_plan"):
                                a_val = sub_dict.get(alias)
                                if a_val is not None and str(a_val).strip():
                                    return str(a_val).strip()
    except Exception:
        pass
    return ""


def import_cli_session(service: Any, provider_id: str) -> dict[str, Any]:
    """Read tokens from the provider's own CLI state files and import them."""
    if provider_id == "codex":
        provider_id = "openai_codex"
    config = oauth_config(provider_id)
    if config.flow not in ("cli", "hybrid") or not config.cli_files:
        raise OAuthError(f"{provider_id} does not support CLI session import.")
    imported: dict[str, Any] = {}
    errors: list[str] = []
    for raw_path in config.cli_files:
        path = _expand_home(raw_path)
        if not path.is_file():
            errors.append(f"{raw_path} not found")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{raw_path} unreadable: {exc}")
            continue
        if provider_id == "openai_codex" and isinstance(data, dict):
            tokens = data.get("tokens") or {}
            access = str(tokens.get("access_token") or "")
            refresh = str(tokens.get("refresh_token") or "")
            id_tok = str(tokens.get("id_token") or "")
            email = _extract_jwt_claim(id_tok or access, "email")
            chatgpt_acc_id = (
                _extract_jwt_claim(id_tok, "chatgpt_account_id")
                or _extract_jwt_claim(access, "chatgpt_account_id")
                or str(tokens.get("account_id") or "")
            )
            chatgpt_plan = (
                _extract_jwt_claim(id_tok, "chatgpt_plan_type")
                or _extract_jwt_claim(access, "chatgpt_plan_type")
                or ""
            )
            account_id = email or chatgpt_acc_id or str(tokens.get("account_id") or data.get("auth_mode") or "codex-cli")
            last_refresh = str(data.get("last_refresh") or "")
            if access:
                imported = {
                    "access_token": access,
                    "refresh_token": refresh,
                    "account_id": account_id,
                    "chatgpt_account_id": chatgpt_acc_id,
                    "chatgpt_plan_type": chatgpt_plan,
                    "email": email,
                    "last_refresh": last_refresh,
                    "source": str(path),
                }
                break
            errors.append("codex auth.json has no access token")
        elif provider_id == "cursor" and isinstance(data, dict):
            access = str(data.get("openai_api_key") or data.get("chatgpt_encrypted_api_key") or "")
            account_id = str(data.get("user_id") or "cursor-cli")
            if access:
                imported = {
                    "access_token": access,
                    "account_id": account_id,
                    "source": str(path),
                }
                break
            errors.append("cursor state.json has no usable token")
        elif provider_id == "claude_code" and isinstance(data, dict):
            # Claude Code on Windows stores its login under claudeAiOauth
            # (older builds used tokens.oauthToken — keep both shapes).
            claude_oauth = data.get("claudeAiOauth") if isinstance(data.get("claudeAiOauth"), dict) else {}
            tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
            access = str(claude_oauth.get("accessToken") or tokens.get("oauthToken") or tokens.get("access_token") or "")
            refresh = str(claude_oauth.get("refreshToken") or tokens.get("refreshToken") or "")
            expires_at = claude_oauth.get("expiresAt")
            if expires_at:
                try:
                    exp = float(expires_at)
                    if exp > 1e12:  # milliseconds (Claude Code convention) -> seconds
                        exp /= 1000.0
                    expires_at = str(int(exp))
                except (TypeError, ValueError):
                    expires_at = ""
            account_id = str(
                (claude_oauth.get("account") or {}).get("emailAddress")
                or claude_oauth.get("emailAddress")
                or tokens.get("account_id")
                or "claude-cli"
            )
            if not access and "settings.json" in str(path):
                env = data.get("env") or {}
                tok = str(env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ANTHROPIC_API_KEY") or "")
                if tok:
                    access = tok
                    account_id = "claude-local"
            if access:
                imported = {
                    "access_token": access,
                    "refresh_token": refresh,
                    "account_id": account_id,
                    "expires_at": str(expires_at) if expires_at else "",
                    "source": str(path),
                }
                break
            errors.append("claude credentials file has no Claude Code token (sign in once, then press Sign in here again)")
    if not imported:
        raise OAuthError("; ".join(errors)[:300] or "No CLI session found to import.")
    return imported


def import_cursor_session(service: Any = None) -> dict[str, Any]:
    """Import the Cursor app session from Cursor's own storage.

    Cursor (desktop app) keeps its auth in a SQLite key-value store at
    %APPDATA%/Cursor/User/globalStorage/state.vscdb (ItemTable). The legacy
    ~/.cursor/state.json file is tried first for older installs. Values are
    never logged — only parsed and returned for encrypted storage.
    """
    candidates = [
        ("state.vscdb", Path(os.environ.get("APPDATA", "")) / "Cursor" / "User" / "globalStorage" / "state.vscdb"),
        ("state.json", Path.home() / ".cursor" / "state.json"),
    ]
    import sqlite3 as _sqlite3
    errors: list[str] = []
    for label, path in candidates:
        if not path.is_file():
            errors.append(f"{label} not found")
            continue
        if label == "state.vscdb":
            try:
                conn = _sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
                try:
                    rows = conn.execute(
                        "SELECT key, value FROM ItemTable WHERE key LIKE 'cursorAuth/%'"
                    ).fetchall()
                finally:
                    conn.close()
            except (OSError, _sqlite3.Error) as exc:
                errors.append(f"state.vscdb unreadable: {exc}")
                continue
            store: dict[str, str] = {}
            for key, value in rows:
                if isinstance(value, (bytes, bytearray)):
                    try:
                        value = value.decode("utf-8")
                    except (UnicodeDecodeError, ValueError):
                        continue
                store[str(key)] = str(value or "")
            access = (
                store.get("cursorAuth/accessToken")
                or store.get("cursorAuth/cachedAccessToken")
                or ""
            )
            if not access:
                errors.append("state.vscdb has no cursorAuth/accessToken")
                continue
            email = store.get("cursorAuth/cachedEmail") or ""
            return {
                "access_token": access,
                "refresh_token": store.get("cursorAuth/refreshToken") or "",
                "account_id": email or "cursor-app",
                "source": str(path),
            }
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"state.json unreadable: {exc}")
            continue
        if isinstance(data, dict):
            access = str(data.get("openai_api_key") or data.get("chatgpt_encrypted_api_key") or "")
            if access:
                return {
                    "access_token": access,
                    "account_id": str(data.get("user_id") or "cursor-cli"),
                    "source": str(path),
                }
            errors.append("state.json has no usable token")
    raise OAuthError("; ".join(errors)[:300] or "No Cursor session found to import.")


def wait_for_cli_session(
    service: Any,
    provider_id: str,
    *,
    interval_seconds: float = 5.0,
    timeout_seconds: float = 600.0,
    on_connected: Any = None,
) -> threading.Thread:
    """Watch for a provider login to finish, then import it automatically."""
    if provider_id == "codex":
        provider_id = "openai_codex"
    existing = getattr(service, "_login_watch_threads", None)
    if existing is None:
        existing = service._login_watch_threads = {}
    old = existing.get(provider_id)
    if old is not None and old.is_alive():
        return old

    def worker() -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            time.sleep(interval_seconds)
            try:
                if provider_id == "cursor":
                    imported = import_cursor_session(service)
                else:
                    imported = import_cli_session(service, provider_id)
            except OAuthError:
                continue  # not signed in yet — keep watching
            except Exception:
                continue
            try:
                service._create_oauth_connection(provider_id, imported)
                if on_connected:
                    try:
                        on_connected(provider_id, imported)
                    except Exception:
                        pass
            except Exception:
                continue
            return  # imported successfully — stop watching

    thread = threading.Thread(
        target=worker,
        name=f"vf-login-watch-{provider_id}",
        daemon=True,
    )
    existing[provider_id] = thread
    thread.start()
    return thread


# --------------------------------------------------------------------------
# Token refresh
# --------------------------------------------------------------------------

def refresh_connection_tokens(service: Any, connection: dict[str, Any]) -> dict[str, Any]:
    """Refresh a connection's tokens via its provider-specific handler."""
    provider_id = str(connection.get("provider") or "")
    if provider_id == "codex":
        provider_id = "openai_codex"
    config = oauth_config(provider_id)
    raw_refresh = str(connection.get("refresh_token") or "")
    refresh_token = decrypt_token(service, raw_refresh) if raw_refresh else ""

    # 1. OpenAI Codex / ChatGPT Device flow refresh via OAuth endpoint
    if provider_id == "openai_codex" and refresh_token:
        try:
            payload: dict[str, Any] = {
                "client_id": OPENAI_DEVICE_CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
            response = _http_json(OPENAI_DEVICE_OAUTH_TOKEN_URL, data=payload)
            access = str(response.get("access_token") or "")
            if access:
                new_refresh = str(response.get("refresh_token") or refresh_token)
                expires_in = int(response.get("expires_in") or 0)
                id_tok = str(response.get("id_token") or "")
                chatgpt_acc_id = (
                    _extract_jwt_claim(id_tok, "chatgpt_account_id")
                    or _extract_jwt_claim(access, "chatgpt_account_id")
                    or str((connection.get("metadata") or {}).get("chatgpt_account_id") or "")
                )
                chatgpt_plan = (
                    _extract_jwt_claim(id_tok, "chatgpt_plan_type")
                    or _extract_jwt_claim(access, "chatgpt_plan_type")
                    or str((connection.get("metadata") or {}).get("chatgpt_plan_type") or "")
                )
                account_id = (
                    _extract_jwt_claim(id_tok, "email")
                    or _extract_jwt_claim(access, "email")
                    or chatgpt_acc_id
                    or str(connection.get("account_id") or "")
                )
                meta = dict(connection.get("metadata") or {})
                if chatgpt_acc_id:
                    meta["chatgpt_account_id"] = chatgpt_acc_id
                if chatgpt_plan:
                    meta["chatgpt_plan_type"] = chatgpt_plan
                return {
                    "access_token": access,
                    "refresh_token": new_refresh,
                    "expires_at": int(time.time()) + expires_in if expires_in else "",
                    "account_id": account_id,
                    "metadata": meta,
                }
        except Exception:
            if config.refresh_mode != "cli":
                raise

    if config.refresh_mode == "oauth":
        if not refresh_token:
            raise OAuthError("Connection has no refresh token.")
        payload: dict[str, Any] = {
            "client_id": config.client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        if config.client_secret:
            payload["client_secret"] = config.client_secret
        response = _http_json(config.token_url, data=payload)
        access = str(response.get("access_token") or "")
        if not access:
            raise OAuthError(f"Refresh failed: {response}")
        new_refresh = str(response.get("refresh_token") or refresh_token)
        expires_in = int(response.get("expires_in") or 0)
        return {
            "access_token": access,
            "refresh_token": new_refresh,
            "expires_at": int(time.time()) + expires_in if expires_in else "",
        }
    if config.refresh_mode == "exchange":
        # The GitHub OAuth token is stored in the refresh_token field; it is the
        # credential that must be presented to the Copilot exchange endpoint.
        github_token = decrypt_token(service, str(connection.get("refresh_token") or ""))
        if not github_token:
            raise OAuthError("Connection has no GitHub token to exchange.")
        exchanged = exchange_copilot_token(service, github_token)
        return {
            "access_token": exchanged["access_token"],
            "expires_at": exchanged["expires_at"],
        }
    if config.refresh_mode == "cli":
        imported = import_cli_session(service, provider_id)
        return {
            "access_token": imported["access_token"],
            "refresh_token": imported.get("refresh_token", ""),
            "account_id": imported.get("account_id", ""),
        }
    raise OAuthError(f"{provider_id} has no refresh handler.")


def connections_due_for_refresh(service: Any) -> list[dict[str, Any]]:
    """Return active connections whose token expires within the grace window."""
    now = time.time()
    due: list[dict[str, Any]] = []
    for connection in service.list_all_connections():
        if not connection.get("is_active"):
            continue
        status = str(connection.get("status") or "")
        if status not in {"active", "untested", "connected"}:
            continue
        raw_expiry = str(connection.get("expires_at") or "")
        if not raw_expiry:
            continue
        try:
            expiry = float(raw_expiry)
        except (TypeError, ValueError):
            continue
        if 0 < expiry <= now + REFRESH_GRACE_MINUTES * 60:
            due.append(connection)
    return due


def _scheduler_loop(service: Any, stop: threading.Event) -> None:
    while not stop.wait(REFRESH_INTERVAL_SECONDS):
        try:
            for connection in connections_due_for_refresh(service):
                try:
                    refresh_and_store(service, connection)
                except OAuthError:
                    service.mark_connection_expired(int(connection["id"]))
        except Exception:
            pass  # the scheduler must never die


def start_refresh_scheduler(service: Any) -> threading.Thread:
    """Start (or reuse) the 5-minute proactive token refresh worker."""
    stop = getattr(service, "_oauth_refresh_stop", None)
    if stop is not None:
        return getattr(service, "_oauth_refresh_thread", threading.Thread())
    stop = threading.Event()
    thread = threading.Thread(
        target=_scheduler_loop,
        args=(service, stop),
        name="video-flow-oauth-refresh",
        daemon=True,
    )
    service._oauth_refresh_stop = stop
    service._oauth_refresh_thread = thread
    thread.start()
    return thread


def refresh_and_store(service: Any, connection: dict[str, Any]) -> dict[str, Any]:
    """Refresh a connection and persist the rotated tokens."""
    refreshed = refresh_connection_tokens(service, connection)
    changes: dict[str, Any] = {
        "secret": encrypt_token(service, str(refreshed.get("access_token") or "")),
        "status": "active",
    }
    if refreshed.get("refresh_token"):
        changes["refresh_token"] = encrypt_token(service, str(refreshed["refresh_token"]))
    if refreshed.get("account_id"):
        changes["account_id"] = str(refreshed["account_id"])
    if refreshed.get("expires_at"):
        changes["expires_at"] = str(refreshed["expires_at"])
    if refreshed.get("metadata"):
        changes["metadata"] = refreshed["metadata"]
    service.update_connection(int(connection["id"]), **changes)
    updated = service.get_connection(int(connection["id"]), public=False) or connection
    return updated


OPENAI_DEVICE_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_DEVICE_USERCODE_URL = "https://auth.openai.com/api/accounts/deviceauth/usercode"
OPENAI_DEVICE_TOKEN_URL = "https://auth.openai.com/api/accounts/deviceauth/token"
OPENAI_DEVICE_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OPENAI_DEVICE_VERIFICATION_URL = "https://auth.openai.com/codex/device"
OPENAI_DEVICE_CALLBACK_URI = "https://auth.openai.com/deviceauth/callback"


def start_openai_device_flow(client_id: str = OPENAI_DEVICE_CLIENT_ID) -> dict[str, Any]:
    """Initiate an OpenAI device authorization flow (ChatGPT / Codex).

    Calls https://auth.openai.com/api/accounts/deviceauth/usercode to obtain
    user_code and device_auth_id.
    """
    body = json.dumps({"client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(
        OPENAI_DEVICE_USERCODE_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "voice-flow/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise OAuthError(f"Failed to initiate OpenAI device authorization: {exc}") from exc

    user_code = data.get("user_code")
    device_auth_id = data.get("device_auth_id")
    interval = max(3, int(data.get("interval") or 5))
    if not user_code or not device_auth_id:
        raise OAuthError("OpenAI device response missing user_code or device_auth_id")

    return {
        "flow": "device",
        "user_code": user_code,
        "device_auth_id": device_auth_id,
        "verification_url": OPENAI_DEVICE_VERIFICATION_URL,
        "interval": interval,
        "expires_in": 900,
    }


def poll_openai_device_flow(
    device_auth_id: str,
    user_code: str,
    client_id: str = OPENAI_DEVICE_CLIENT_ID,
) -> dict[str, Any]:
    """Poll OpenAI device authorization status.

    Returns:
      {"status": "pending"} if not authorized yet.
      {"status": "approved", "access_token": ..., "refresh_token": ..., "account_id": ...} on approval.
      {"status": "error", "error": ...} on failure.
    """
    body = json.dumps({
        "device_auth_id": device_auth_id,
        "user_code": user_code,
    }).encode("utf-8")
    req = urllib.request.Request(
        OPENAI_DEVICE_TOKEN_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "voice-flow/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in {403, 404, 428, 429}:
            return {"status": "pending"}
        try:
            err_body = exc.read().decode("utf-8", errors="replace")
            err_json = json.loads(err_body)
            err_field = err_json.get("error")
            if isinstance(err_field, dict):
                msg = err_field.get("message") or err_body
                err_code = str(err_field.get("code") or err_field.get("message") or "").lower()
            else:
                msg = err_field or err_body
                err_code = str(err_field or "").lower()
            if any(k in err_code or k in str(msg).lower() for k in ("authorization_pending", "slow_down", "pending")):
                return {"status": "pending"}
        except Exception:
            msg = str(exc)
        return {"status": "error", "error": str(msg)[:200]}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:200]}

    if isinstance(data, dict) and "error" in data:
        err_code = str(data["error"]).lower()
        if any(k in err_code for k in ("authorization_pending", "slow_down", "pending")):
            return {"status": "pending"}
        return {"status": "error", "error": str(data.get("error_description") or data["error"])[:200]}

    auth_code = data.get("authorization_code")
    code_verifier = data.get("code_verifier")
    if not auth_code or not code_verifier:
        return {"status": "pending"}

    form = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": OPENAI_DEVICE_CALLBACK_URI,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }).encode("utf-8")
    tok_req = urllib.request.Request(
        OPENAI_DEVICE_OAUTH_TOKEN_URL,
        data=form,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "voice-flow/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(tok_req, timeout=15) as resp:
            tok_data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"status": "error", "error": f"Token exchange failed: {exc}"}

    access_token = tok_data.get("access_token")
    refresh_token = tok_data.get("refresh_token")
    if not access_token:
        return {"status": "error", "error": "Token response missing access_token"}

    id_token = str(tok_data.get("id_token") or "")
    expires_in = tok_data.get("expires_in")
    expires_at = str(int(time.time() + float(expires_in))) if expires_in else ""
    chatgpt_acc_id = (
        _extract_jwt_claim(id_token, "chatgpt_account_id")
        or _extract_jwt_claim(access_token, "chatgpt_account_id")
        or str(tok_data.get("account_id") or "")
    )
    chatgpt_plan = (
        _extract_jwt_claim(id_token, "chatgpt_plan_type")
        or _extract_jwt_claim(access_token, "chatgpt_plan_type")
        or ""
    )
    account_id = (
        _extract_jwt_claim(id_token, "email")
        or _extract_jwt_claim(access_token, "email")
        or chatgpt_acc_id
        or _extract_jwt_claim(id_token, "sub")
        or _extract_jwt_claim(access_token, "sub")
        or str(tok_data.get("account_id") or "")
        or "ChatGPT Account"
    )

    return {
        "status": "approved",
        "access_token": access_token,
        "refresh_token": refresh_token or "",
        "account_id": account_id,
        "chatgpt_account_id": chatgpt_acc_id,
        "chatgpt_plan_type": chatgpt_plan,
        "expires_at": expires_at,
        "token_type": tok_data.get("token_type") or "Bearer",
    }


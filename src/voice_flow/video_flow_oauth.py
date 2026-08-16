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
    redirect_path: str = "/api/video-flow/providers/oauth/callback"
    refresh_mode: str = "none"  # "oauth" | "cli" | "exchange"
    cli_files: tuple[str, ...] = ()
    api_base: str = ""
    extra_headers: dict[str, str] | None = None


def _env_client_id(provider_id: str) -> str:
    return os.environ.get(f"OAUTH_CLIENT_ID_{provider_id.upper()}", "")


def _env_client_secret(provider_id: str) -> str:
    return os.environ.get(f"OAUTH_CLIENT_SECRET_{provider_id.upper()}", "")


# Public Google desktop client used by the gcloud / Gemini CLI family. It is
# embedded in those SDKs, so no registration is needed for the loopback
# redirect the Antigravity popup flow uses. Override via env when preferred.
GOOGLE_PUBLIC_CLIENT_ID = "764086051850-6qr4p6gpi6hn506pt8ejuq83di341hur.apps.googleusercontent.com"
GOOGLE_PUBLIC_CLIENT_SECRET = "d-FL95Q19q7MQmFpd7hHD0Ty"


def _device_code_url() -> str:
    return os.environ.get("OAUTH_DEVICE_CODE_URL", "https://github.com/login/device/code")


def _access_token_url() -> str:
    return os.environ.get("OAUTH_ACCESS_TOKEN_URL", "https://github.com/login/oauth/access_token")


def oauth_config(provider_id: str) -> OAuthConfig:
    """Return the OAuth wiring for a provider, falling back to env overrides."""
    common: dict[str, str] = {}
    if provider_id in {"antigravity", "gemini"}:
        common = {
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "scopes": "openid email profile",
            "flow": "pkce",
            "client_id": GOOGLE_PUBLIC_CLIENT_ID,
            "client_secret": GOOGLE_PUBLIC_CLIENT_SECRET,
        }
    if provider_id == "openai_codex":
        common = {
            "flow": "cli",
            "cli_files": ("~/.codex/auth.json",),
            "refresh_mode": "cli",
        }
    if provider_id == "claude_code":
        common = {
            "flow": "launch",
            "cli_files": ("~/.claude/.credentials.json",),
            "refresh_mode": "cli",
        }
    if provider_id == "cursor":
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
    service.set_setting(PENDING_PREFIX + provider_id, payload)


def load_pending(service: Any, provider_id: str) -> dict[str, Any] | None:
    payload = service.get_setting(PENDING_PREFIX + provider_id, None)
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


def import_cli_session(service: Any, provider_id: str) -> dict[str, Any]:
    """Read tokens from the provider's own CLI state files and import them."""
    config = oauth_config(provider_id)
    if config.flow != "cli" or not config.cli_files:
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
            account_id = str(tokens.get("account_id") or data.get("auth_mode") or "codex-cli")
            last_refresh = str(data.get("last_refresh") or "")
            if access:
                imported = {
                    "access_token": access,
                    "refresh_token": refresh,
                    "account_id": account_id,
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
            tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
            access = str(tokens.get("oauthToken") or tokens.get("access_token") or "")
            account_id = str(tokens.get("account_id") or "claude-cli")
            if access:
                imported = {
                    "access_token": access,
                    "account_id": account_id,
                    "source": str(path),
                }
                break
            errors.append("claude credentials file has no token")
    if not imported:
        raise OAuthError("; ".join(errors)[:300] or "No CLI session found to import.")
    return imported


# --------------------------------------------------------------------------
# Token refresh
# --------------------------------------------------------------------------

def refresh_connection_tokens(service: Any, connection: dict[str, Any]) -> dict[str, Any]:
    """Refresh a connection's tokens via its provider-specific handler."""
    provider_id = str(connection.get("provider") or "")
    config = oauth_config(provider_id)
    if config.refresh_mode == "oauth":
        refresh_token = decrypt_token(service, str(connection.get("refresh_token") or ""))
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
    service.update_connection(int(connection["id"]), **changes)
    updated = service.get_connection(int(connection["id"]), public=False) or connection
    return updated

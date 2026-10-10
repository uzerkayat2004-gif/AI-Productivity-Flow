"""Key Validation Probe & Failover Execution Engine for AI Provider System."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from voice_flow.provider_registry import get_provider_spec, ProviderSpec
from voice_flow.storage import storage

log = logging.getLogger(__name__)


def validate_provider_key(
    provider_id: str,
    api_key: str,
    base_url_override: str | None = None,
) -> tuple[bool, str | None]:
    """Execute real-time validation probe for an API key.

    Returns:
        (is_valid: bool, last_error: str | None)
    """
    clean_key = api_key.strip()
    if not clean_key:
        return (False, "API key cannot be empty")

    spec = get_provider_spec(provider_id)
    if not spec:
        if provider_id.startswith("custom-"):
            cp_entry = None
            for getter in (
                getattr(storage, "get_voice_flow_custom_providers", None),
                getattr(storage, "get_video_flow_custom_providers", None),
                getattr(storage, "get_audio_flow_custom_providers", None),
            ):
                if callable(getter):
                    try:
                        for cp in getter():
                            if cp.get("id") == provider_id:
                                cp_entry = cp
                                break
                    except Exception:
                        pass
                if cp_entry:
                    break
            if cp_entry:
                base_url = (base_url_override or cp_entry.get("base_url") or "").rstrip("/")
                custom_headers = cp_entry.get("headers") if isinstance(cp_entry.get("headers"), dict) else {}
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VoiceFlow/2.0",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {clean_key}",
                    **custom_headers,
                }
                api_fmt = str(cp_entry.get("api_format") or "openai")
                if api_fmt == "anthropic":
                    headers["x-api-key"] = clean_key
                    headers["anthropic-version"] = "2023-06-01"
                elif api_fmt == "elevenlabs":
                    headers["xi-api-key"] = clean_key
                    try:
                        req = urllib.request.Request(f"{base_url}/v1/voices", headers=headers, method="GET")
                        with urllib.request.urlopen(req, timeout=10.0) as resp:
                            if resp.status in (200, 201):
                                return (True, None)
                    except Exception as probe_err:
                        return (False, str(probe_err)[:200])
                elif api_fmt == "gemini":
                    headers["x-goog-api-key"] = clean_key
                    try:
                        delimiter = "&" if "?" in base_url else "?"
                        req = urllib.request.Request(f"{base_url}/models{delimiter}key={clean_key}", headers=headers, method="GET")
                        with urllib.request.urlopen(req, timeout=10.0) as resp:
                            if resp.status in (200, 201):
                                return (True, None)
                    except Exception:
                        pass
                try:
                    req = urllib.request.Request(f"{base_url}/models", headers=headers, method="GET")
                    with urllib.request.urlopen(req, timeout=10.0) as resp:
                        if resp.status in (200, 201):
                            return (True, None)
                except Exception:
                    try:
                        first_model = ((cp_entry.get("models") or [{}])[0].get("model_id") or "test")
                        payload = json.dumps({
                            "model": first_model,
                            "messages": [{"role": "user", "content": "ping"}],
                            "max_tokens": 1,
                        }).encode("utf-8")
                        req = urllib.request.Request(f"{base_url}/chat/completions", data=payload, headers=headers, method="POST")
                        with urllib.request.urlopen(req, timeout=10.0) as resp:
                            if resp.status in (200, 201):
                                return (True, None)
                    except Exception as probe_err:
                        return (False, str(probe_err)[:200])
        return (False, f"Unknown provider '{provider_id}'")

    validate_url = spec.transport.validate_url
    auth_header = spec.transport.auth_header
    format_type = spec.transport.format
    effective_base_url = base_url_override or spec.transport.base_url

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VoiceFlow/2.0",
        "Content-Type": "application/json",
    }

    if auth_header == "bearer":
        headers["Authorization"] = f"Bearer {clean_key}"
    elif auth_header == "x-api-key":
        headers["x-api-key"] = clean_key
        headers["anthropic-version"] = "2023-06-01"

    try:
        if validate_url:
            target_url = validate_url
            if auth_header == "key-query":
                sep = "&" if "?" in target_url else "?"
                target_url = f"{target_url}{sep}key={urllib.parse.quote(clean_key, safe='')}"

            req = urllib.request.Request(target_url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                if resp.status in (200, 201):
                    return (True, None)
        else:
            # Fallback to Minimal Chat Completion Probe
            target_url = effective_base_url
            if auth_header == "key-query":
                sep = "&" if "?" in target_url else "?"
                target_url = f"{target_url}{sep}key={urllib.parse.quote(clean_key, safe='')}"

            default_model = spec.models[0].id if spec.models else "gpt-4o-mini"
            if format_type == "anthropic":
                payload = json.dumps({
                    "model": default_model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                }).encode("utf-8")
            else:
                payload = json.dumps({
                    "model": default_model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                }).encode("utf-8")

            req = urllib.request.Request(target_url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                if resp.status in (200, 201):
                    return (True, None)
                return (False, f"Unexpected response status: {resp.status}")

        return (False, "Validation probe failed to receive a valid response")

    except urllib.error.HTTPError as e:
        status_code = e.code
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        log.warning("[VALIDATION PROBE - %s] HTTP %d: %s (body=%s)", provider_id, status_code, e.reason, err_body)

        if status_code in (200, 201):
            return (True, None)
        elif status_code in (401, 403):
            return (False, f"Invalid API key or access denied (HTTP {status_code})")
        elif status_code == 400:
            if "API_KEY_INVALID" in err_body or "invalid_api_key" in err_body or "key" in err_body.lower():
                return (False, "Invalid API key — please check key in provider dashboard")
            return (False, f"Bad request / Invalid configuration (HTTP 400): {err_body[:120] or e.reason}")
        elif status_code == 422:
            return (False, f"Unprocessable request / Invalid payload (HTTP 422): {err_body[:120] or e.reason}")
        elif status_code in (429, 402):
            return (False, f"Quota exhausted or rate limit reached (HTTP {status_code})")
        elif status_code == 404:
            return (False, f"Endpoint or model not found (HTTP 404)")
        elif status_code >= 500:
            return (False, f"Provider server error (HTTP {status_code})")
        else:
            return (False, f"HTTP Error {status_code}: {e.reason}")

    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log.warning("[VALIDATION PROBE TIMEOUT/NETWORK - %s] %s", provider_id, e)
        return (False, f"Network unreachable - key not verified ({e})")
    except Exception as e:
        log.error("[VALIDATION PROBE ERROR - %s] %s", provider_id, e)
        return (False, str(e))


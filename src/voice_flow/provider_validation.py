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
            with urllib.request.urlopen(req, timeout=8.0) as resp:
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
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                if resp.status in (200, 201):
                    return (True, None)

        return (True, None)

    except urllib.error.HTTPError as e:
        status_code = e.code
        log.warning("[VALIDATION PROBE - %s] HTTP %d: %s", provider_id, status_code, e.reason)

        if status_code in (200, 201):
            return (True, None)
        elif status_code in (400, 422):
            # Payload error proves auth succeeded
            return (True, None)
        elif status_code in (401, 403):
            return (False, "Invalid API key or access denied")
        elif status_code in (429, 402):
            return (True, "Credit limit or rate limit reached")
        elif status_code >= 500:
            return (True, f"Server error ({status_code}) - Retaining valid state")
        else:
            return (False, f"HTTP Error {status_code}: {e.reason}")

    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log.warning("[VALIDATION PROBE TIMEOUT/NETWORK - %s] %s", provider_id, e)
        return (True, "Network timeout or connection error - Retaining state")
    except Exception as e:
        log.error("[VALIDATION PROBE ERROR - %s] %s", provider_id, e)
        return (False, str(e))

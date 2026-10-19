"""Nebius Token Factory provider and NVIDIA Nemotron model routing.

Token Factory speaks the OpenAI Chat Completions protocol, so requests ride
the same adapters as the other OpenAI-compatible providers. This module only
owns the parts that are specific to Nebius:

* where the key comes from (a saved Video Flow connection, else the
  ``NEBIUS_API_KEY`` environment variable),
* which Nemotron model serves which job (the *fast* tier for Voice Flow
  polishing / voice commands and Audio Flow summaries, the *reasoning* tier
  for Video Flow planning, creative direction and scene authoring),
* checking those model ids against ``GET /v1/models`` at runtime and falling
  back gracefully when an id is not served by the account.

No key means no network call: every function that would talk to Nebius
returns early when it has no key.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Iterable

log = logging.getLogger(__name__)

PROVIDER_ID = "nebius"
BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
CHAT_COMPLETIONS_URL = BASE_URL + "chat/completions"
MODELS_URL = BASE_URL + "models"
ENV_KEY = "NEBIUS_API_KEY"
API_KEY_URL = "https://tokenfactory.nebius.com/"

TIER_FAST = "fast"
TIER_REASONING = "reasoning"
TIERS = (TIER_FAST, TIER_REASONING)

# Model ids as listed for Nebius Token Factory on models.dev (checked
# 2026-10-19). They are only defaults: every request validates them against
# the account's own /v1/models list first.
FAST_LIGHTNING = "nvidia/Nemotron-3_5-Lightning"
FAST_SUPER = "nvidia/nemotron-3-super-120b-a12b"
REASONING_ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"

DEFAULT_TIER_MODELS: dict[str, tuple[str, ...]] = {
    # Lightning (30B total / 3B active) answers fastest; Super is the
    # stronger fallback when Lightning is not served.
    TIER_FAST: (FAST_LIGHTNING, FAST_SUPER),
    # Ultra does the heavy planning; Super is the fallback.
    TIER_REASONING: (REASONING_ULTRA, FAST_SUPER),
}

# Picker entries that mean "let the router choose for this tier".
TIER_MODEL_ALIASES: dict[str, str] = {
    "": "",
    "auto": "",
    "nemotron-fast": TIER_FAST,
    "nemotron-reasoning": TIER_REASONING,
}

SETTING_KEYS: dict[str, str] = {
    TIER_FAST: "nebius_model_fast",
    TIER_REASONING: "nebius_model_reasoning",
}

_TIER_HINTS: dict[str, tuple[str, ...]] = {
    TIER_FAST: ("lightning", "nano", "super"),
    TIER_REASONING: ("ultra", "super"),
}

MODEL_CACHE_TTL_SECONDS = 600.0
_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9@._:/-]{1,200}$")

_cache_lock = threading.Lock()
_model_cache: dict[str, tuple[float, list[str]]] = {}
_warming: set[str] = set()


def _cache_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:24]


def clear_model_cache() -> None:
    with _cache_lock:
        _model_cache.clear()
        _warming.clear()


def _provider_service():
    from voice_flow.video_flow_providers import video_flow_provider_service

    return video_flow_provider_service


def env_api_key() -> str:
    return str(os.environ.get(ENV_KEY) or "").strip()


def resolve_api_key(service: Any = None) -> str:
    """Return the first healthy saved Nebius key, else ``NEBIUS_API_KEY``."""
    try:
        svc = service or _provider_service()
        for connection in svc.active_connections(PROVIDER_ID):
            if not svc.connection_is_healthy(connection):
                continue
            secret = svc.resolve_connection_secret(connection)
            if secret:
                return str(secret).strip()
    except Exception:
        pass
    return env_api_key()


def has_api_key(service: Any = None) -> bool:
    return bool(resolve_api_key(service))


def _parse_model_ids(body: Any) -> list[str]:
    items: Iterable[Any] = []
    if isinstance(body, dict):
        items = body.get("data") or body.get("models") or []
    elif isinstance(body, list):
        items = body
    ids: list[str] = []
    for item in items:
        mid = item.get("id") if isinstance(item, dict) else item
        if isinstance(mid, str) and mid.strip():
            ids.append(mid.strip())
    return ids


def request_model_ids(api_key: str, *, timeout: float = 8.0) -> list[str]:
    """``GET /v1/models``. Raises ``urllib.error`` exceptions on failure."""
    request = urllib.request.Request(
        MODELS_URL,
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json", "User-Agent": "VoiceFlow/2.0"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("Nebius returned an unreadable model list") from exc
    ids = _parse_model_ids(body)
    with _cache_lock:
        _model_cache[_cache_key(api_key)] = (time.monotonic(), ids)
    return ids


def cached_model_ids(api_key: str) -> list[str] | None:
    if not api_key:
        return None
    with _cache_lock:
        hit = _model_cache.get(_cache_key(api_key))
    if not hit:
        return None
    stamp, ids = hit
    if time.monotonic() - stamp > MODEL_CACHE_TTL_SECONDS:
        return None
    return list(ids)


def fetch_model_ids(api_key: str, *, timeout: float = 8.0, blocking: bool = True) -> list[str] | None:
    """Return the account's served model ids, or ``None`` when unknown.

    ``blocking=False`` never waits on the network: it returns the cached list
    (or ``None``) and refreshes the cache in the background. Voice polishing
    uses that mode so a cold cache cannot eat its latency budget.
    """
    if not api_key:
        return None
    cached = cached_model_ids(api_key)
    if cached is not None:
        return cached
    if not blocking:
        warm_model_cache_async(api_key, timeout=timeout)
        return None
    try:
        return request_model_ids(api_key, timeout=timeout)
    except Exception as exc:
        log.info("Nebius model list unavailable (%s); using configured Nemotron ids as-is", exc.__class__.__name__)
        return None


def warm_model_cache_async(api_key: str, *, timeout: float = 8.0) -> None:
    if not api_key:
        return
    key = _cache_key(api_key)
    with _cache_lock:
        if key in _warming:
            return
        _warming.add(key)

    def worker() -> None:
        try:
            request_model_ids(api_key, timeout=timeout)
        except Exception:
            pass
        finally:
            with _cache_lock:
                _warming.discard(key)

    threading.Thread(target=worker, name="nebius-models-warm", daemon=True).start()


def _clean_override(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower().startswith(PROVIDER_ID + "/"):
        text = text[len(PROVIDER_ID) + 1:]
    return text if _MODEL_ID_RE.fullmatch(text or "") else ""


def tier_override(tier: str, settings_getter: Callable[[str, Any], Any] | None = None) -> str:
    """The user's per-tier model override, if one is saved."""
    key = SETTING_KEYS.get(tier)
    if not key:
        return ""
    try:
        getter = settings_getter or _provider_service().get_setting
        return _clean_override(getter(key, ""))
    except Exception:
        return ""


def set_tier_override(tier: str, model_id: str, service: Any = None) -> str:
    if tier not in SETTING_KEYS:
        raise ValueError(f"Unknown Nemotron tier: {tier}")
    raw = str(model_id or "").strip()
    clean = _clean_override(raw)
    if raw and not clean:
        raise ValueError("Enter only the model ID, for example nvidia/Nemotron-3_5-Lightning.")
    (service or _provider_service()).set_setting(SETTING_KEYS[tier], clean)
    return clean


def choose_model(tier: str, available: list[str] | None, preferred: Iterable[str] = ()) -> str:
    """Pick the model id for *tier*.

    Candidates are tried in order: ``preferred`` (an explicit pick, then the
    tier override), then the tier defaults. When the served list is unknown
    the first candidate is used unchanged. When none of the candidates is
    served, another served Nemotron model that suits the tier is used, and
    only then any served model, so a renamed id never breaks the request.
    """
    tier = tier if tier in DEFAULT_TIER_MODELS else TIER_FAST
    candidates: list[str] = []
    for item in [*preferred, *DEFAULT_TIER_MODELS[tier]]:
        clean = _clean_override(item)
        if clean and clean not in candidates:
            candidates.append(clean)
    if not available:
        return candidates[0]
    exact = set(available)
    folded = {mid.casefold(): mid for mid in available}
    for candidate in candidates:
        if candidate in exact:
            return candidate
        if candidate.casefold() in folded:
            return folded[candidate.casefold()]
    nemotron = [mid for mid in available if "nemotron" in mid.casefold()]
    for hint in _TIER_HINTS[tier]:
        for mid in nemotron:
            low = mid.casefold()
            # Vision-language and speech variants are not chat planners.
            if hint in low and not any(tag in low for tag in ("-vl", "asr", "speech", "embed", "rerank", "safety", "guard")):
                log.warning("Nebius: %s not served; using %s for the %s tier", candidates[0], mid, tier)
                return mid
    if nemotron:
        log.warning("Nebius: %s not served; using %s for the %s tier", candidates[0], nemotron[0], tier)
        return nemotron[0]
    log.warning("Nebius: no Nemotron model served; using %s for the %s tier", available[0], tier)
    return available[0]


def split_requested_model(model_id: str | None, default_tier: str) -> tuple[str, str]:
    """Return ``(tier, explicit_model)`` for a picker model id."""
    raw = str(model_id or "").strip()
    if raw.lower().startswith(PROVIDER_ID + "/"):
        raw = raw[len(PROVIDER_ID) + 1:]
    alias = raw.lower()
    if alias in TIER_MODEL_ALIASES:
        return (TIER_MODEL_ALIASES[alias] or default_tier), ""
    return default_tier, raw


def resolve_model(
    model_id: str | None,
    *,
    default_tier: str,
    api_key: str,
    settings_getter: Callable[[str, Any], Any] | None = None,
    blocking: bool = True,
    timeout: float = 8.0,
) -> str:
    """Resolve the model id a Nebius request should actually send."""
    tier, explicit = split_requested_model(model_id, default_tier)
    preferred = [explicit, tier_override(tier, settings_getter)]
    available = fetch_model_ids(api_key, timeout=timeout, blocking=blocking) if api_key else None
    return choose_model(tier, available, preferred)


def routing_summary(api_key: str | None = None, *, service: Any = None) -> dict[str, Any]:
    """Secret-free summary for the provider page (never calls the network)."""
    key = api_key if api_key is not None else resolve_api_key(service)
    getter = (service.get_setting if service is not None else None)
    available = cached_model_ids(key) if key else None
    tiers = {}
    for tier in TIERS:
        override = tier_override(tier, getter)
        tiers[tier] = {
            "override": override,
            "defaults": list(DEFAULT_TIER_MODELS[tier]),
            "resolved": choose_model(tier, available, [override]),
        }
    return {
        "has_key": bool(key),
        "env_key": bool(env_api_key()),
        "validated": available is not None,
        "served_nemotron_models": sorted(m for m in (available or []) if "nemotron" in m.casefold()),
        "tiers": tiers,
    }


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str | None) -> str | None:
    """Drop a ``<think>…</think>`` block a reasoning model may put in content."""
    if text is None:
        return None
    cleaned = _THINK_BLOCK.sub("", str(text))
    if re.search(r"<think>", cleaned, re.IGNORECASE) and not re.search(r"</think>", cleaned, re.IGNORECASE):
        # An unterminated block means the answer was cut off mid-reasoning.
        cleaned = re.split(r"<think>", cleaned, flags=re.IGNORECASE)[0]
    return cleaned.strip()


def check_connection(api_key: str, *, timeout: float = 15.0) -> dict[str, Any]:
    """Settings "Test" button: ``GET /v1/models`` and report the routing."""
    if not api_key:
        return {"success": False, "status": "error", "error": "No Nebius API key saved."}
    started = time.monotonic()
    ids = request_model_ids(api_key, timeout=timeout)
    latency_ms = int((time.monotonic() - started) * 1000)
    return {
        "success": True,
        "status": "connected",
        "latency_ms": latency_ms,
        "model_count": len(ids),
        "nemotron_models": sorted(m for m in ids if "nemotron" in m.casefold()),
        "routing": {tier: choose_model(tier, ids, [tier_override(tier)]) for tier in TIERS},
    }


__all__ = [
    "API_KEY_URL",
    "BASE_URL",
    "CHAT_COMPLETIONS_URL",
    "DEFAULT_TIER_MODELS",
    "ENV_KEY",
    "FAST_LIGHTNING",
    "FAST_SUPER",
    "MODELS_URL",
    "PROVIDER_ID",
    "REASONING_ULTRA",
    "SETTING_KEYS",
    "TIER_FAST",
    "TIER_REASONING",
    "cached_model_ids",
    "choose_model",
    "clear_model_cache",
    "fetch_model_ids",
    "has_api_key",
    "resolve_api_key",
    "resolve_model",
    "routing_summary",
    "set_tier_override",
    "split_requested_model",
    "strip_reasoning",
    "check_connection",
    "tier_override",
]

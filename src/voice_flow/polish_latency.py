"""Per-model polishing latency memory.

A single fixed deadline cannot serve every provider.  A fast model answers in
~300 ms while a cold frontier model may legitimately need several seconds; the
old 3/5/8-second ceilings therefore either cancelled healthy requests or made
every dictation wait the full allowance.

This module keeps a small, persisted, exponentially weighted latency estimate
per ``provider/model`` and turns it into a *ceiling* for the next request.  The
ceiling only ever bounds how long the app is willing to wait; a provider that
answers sooner returns immediately, so a fast model is never slowed down.

Cold start is deliberately generous: the first request for an unknown model
gets room to succeed, and only after real measurements does the ceiling tighten
toward that model's actual speed.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

log = logging.getLogger(__name__)

# Absolute bounds for any ceiling.  The floor keeps a single lucky-fast sample
# from cancelling the next request; the cap keeps one pathological model from
# stalling dictation indefinitely.
MIN_CEILING_SECONDS = 2.0
MAX_CEILING_SECONDS = 12.0
# Cold-start ceiling for a model we have never measured, per speed mode.  These
# match the historical mode budgets so an unmeasured model behaves exactly as
# before; the profile only ever adapts from there.
COLD_START_BY_MODE = {"fast": 3.0, "balanced": 5.0, "quality": 8.0}
COLD_START_CEILING_SECONDS = COLD_START_BY_MODE["balanced"]
# How much headroom above the observed latency a model is allowed.  A slow
# outlier must not become the new normal, so the estimate is weighted toward
# recent successes and the ceiling stays a bounded multiple of it.
CEILING_HEADROOM = 1.6
# EWMA weight for the newest sample.
SAMPLE_WEIGHT = 0.35
# When a model exceeds its ceiling, its estimate is raised so the next request
# gives it more room. This is what lets a genuinely slow model eventually
# succeed instead of being cancelled at the same ceiling forever.
TIMEOUT_GROWTH = 1.5
_MAX_TRACKED = 40
# The profile is kept in its own small JSON sidecar, NOT in the settings table.
# Every polishing timeout records here, and writing that into the shared SQLite
# database contended with the app's own writes for the same rows; sidecar
# storage keeps this telemetry off the user's database entirely.
_PROFILE_FILENAME = "polish_latency_profile.json"

_LOCK = threading.Lock()
_CACHE: dict[str, float] | None = None
_CACHE_STAMP = 0.0
_CACHE_TTL = 30.0


def _profile_path():
    from pathlib import Path

    from voice_flow import paths

    return Path(paths.data_dir()) / _PROFILE_FILENAME


def _load_profile() -> dict[str, float]:
    global _CACHE, _CACHE_STAMP
    now = time.monotonic()
    with _LOCK:
        if _CACHE is not None and (now - _CACHE_STAMP) < _CACHE_TTL:
            return dict(_CACHE)
    profile: dict[str, float] = {}
    try:
        target = _profile_path()
        if target.is_file():
            parsed = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    try:
                        seconds = float(value)
                    except (TypeError, ValueError):
                        continue
                    if seconds > 0:
                        profile[str(key)] = seconds
    except Exception:
        profile = {}
    with _LOCK:
        _CACHE = dict(profile)
        _CACHE_STAMP = now
    return profile


def _save_profile(profile: dict[str, float]) -> None:
    """Persist the sidecar atomically so a crash cannot leave a partial file."""
    try:
        target = _profile_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(profile, separators=(",", ":")), encoding="utf-8")
        tmp.replace(target)
    except Exception as exc:
        log.debug("[POLISH LATENCY] Could not persist latency profile: %s", exc)


def normalize_model_key(model_ref: Any) -> str:
    """Canonical profile key for a provider/model reference."""
    value = str(model_ref or "").strip().lower()
    return value


def record_latency(model_ref: Any, seconds: float) -> None:
    """Record one successful polishing latency for ``model_ref``."""
    key = normalize_model_key(model_ref)
    if not key or key == "local/deterministic":
        return
    try:
        sample = float(seconds)
    except (TypeError, ValueError):
        return
    if sample <= 0 or sample > MAX_CEILING_SECONDS * 4:
        return
    global _CACHE, _CACHE_STAMP
    with _LOCK:
        profile = dict(_CACHE) if _CACHE is not None else None
    if profile is None:
        profile = _load_profile()
    previous = profile.get(key)
    if previous is None:
        profile[key] = sample
    else:
        profile[key] = (SAMPLE_WEIGHT * sample) + ((1.0 - SAMPLE_WEIGHT) * previous)
    # Bound the stored profile so a long-lived install cannot grow it forever.
    if len(profile) > _MAX_TRACKED:
        ordered = sorted(profile.items(), key=lambda item: item[1])
        profile = dict(ordered[-_MAX_TRACKED:])
    with _LOCK:
        _CACHE = dict(profile)
        _CACHE_STAMP = time.monotonic()
    _save_profile(profile)


def record_timeout(model_ref: Any, *, elapsed: float = 0.0, mode: str = "balanced") -> None:
    """Record that ``model_ref`` exceeded its ceiling.

    The observed latency is raised (never lowered) so the next request gives
    this model a real chance instead of cancelling it at the same ceiling
    forever.  A model that is merely slow is therefore *learned*, not benched;
    a provider that is actually broken fails with a non-timeout error.
    """
    key = normalize_model_key(model_ref)
    if not key or key == "local/deterministic":
        return
    global _CACHE, _CACHE_STAMP
    with _LOCK:
        profile = dict(_CACHE) if _CACHE is not None else None
    if profile is None:
        profile = _load_profile()
    current = profile.get(key)
    if current is None:
        current = COLD_START_BY_MODE.get(str(mode or "balanced").strip().lower(), COLD_START_CEILING_SECONDS)
    candidate = max(float(elapsed or 0.0), current * TIMEOUT_GROWTH)
    profile[key] = min(MAX_CEILING_SECONDS, candidate)
    if len(profile) > _MAX_TRACKED:
        ordered = sorted(profile.items(), key=lambda item: item[1])
        profile = dict(ordered[-_MAX_TRACKED:])
    with _LOCK:
        _CACHE = dict(profile)
        _CACHE_STAMP = time.monotonic()
    _save_profile(profile)


def observed_latency(model_ref: Any) -> float | None:
    """Return the learned latency estimate for ``model_ref``, if any."""
    key = normalize_model_key(model_ref)
    if not key:
        return None
    return _load_profile().get(key)


def ceiling_for(
    model_ref: Any,
    *,
    mode: str = "balanced",
    word_count: int = 0,
) -> float:
    """Return the maximum time to wait for ``model_ref`` on the next request.

    The result is a *ceiling*, never a sleep: the caller returns as soon as the
    provider answers.  An unmeasured model gets the historical mode budget, so
    behaviour is unchanged until real measurements exist; from then on the
    ceiling tracks what this specific model actually needs.
    """
    mode_key = str(mode or "balanced").strip().lower()
    if mode_key not in COLD_START_BY_MODE:
        mode_key = "balanced"
    observed = observed_latency(model_ref)
    if observed is None:
        ceiling = COLD_START_BY_MODE[mode_key]
    else:
        ceiling = observed * CEILING_HEADROOM

    # Long transcripts legitimately take longer to process.
    words = max(0, int(word_count or 0))
    if words > 80:
        ceiling += min(3.0, (words - 80) / 100.0)

    return max(MIN_CEILING_SECONDS, min(MAX_CEILING_SECONDS, ceiling))


def reset_profile() -> None:
    """Clear the in-memory cache (used by tests)."""
    global _CACHE, _CACHE_STAMP
    with _LOCK:
        _CACHE = None
        _CACHE_STAMP = 0.0

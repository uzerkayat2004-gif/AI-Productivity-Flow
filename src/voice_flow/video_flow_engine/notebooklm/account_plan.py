"""Which Google AI plan the signed-in NotebookLM account has.

Cinematic videos need Google AI Ultra. NotebookLM reports the plan in its
user settings (``GET_USER_SETTINGS`` limits[4]), which notebooklm-py exposes
as ``AccountLimits.tier``. The enum is opaque, not a rank:
1 = Free, 2 = Pro, 4 = Plus, 3 and 6 = Ultra, 5 = Workspace "Expanded".

Only a confirmed Ultra tier unlocks the Normal / Cinematic choice. Anything
else, including "could not tell", makes a Normal video with no question.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ULTRA_TIERS = frozenset({3, 6})
PLAN_NAMES = {1: "free", 2: "pro", 3: "ultra", 4: "plus", 5: "expanded", 6: "ultra"}
CACHE_TTL_SECONDS = 6 * 3600
FAILED_RETRY_SECONDS = 10 * 60

_lock = threading.Lock()
_cache: dict[str, dict[str, Any]] = {}

_PROBE = (
    "import asyncio,json,sys\n"
    "async def main():\n"
    "    from notebooklm.client import NotebookLMClient\n"
    "    async with NotebookLMClient.from_storage(path=sys.argv[1], profile=sys.argv[2]) as c:\n"
    "        limits = await c.settings.get_account_limits()\n"
    "        return getattr(limits, 'tier', None)\n"
    "print(json.dumps({'tier': asyncio.run(main())}))\n"
)


def plan_from_tier(tier: Any) -> dict[str, Any]:
    value = tier if isinstance(tier, int) and not isinstance(tier, bool) and tier > 0 else None
    return {
        "tier": value,
        "plan": PLAN_NAMES.get(value, "unknown") if value is not None else "unknown",
        "is_ultra": value in ULTRA_TIERS,
        "cinematic_available": value in ULTRA_TIERS,
    }


def _probe_interpreter() -> Path | None:
    try:
        from voice_flow.video_flow_engine.notebooklm.config import resolve_notebooklm_cli
        from voice_flow.video_flow_engine.notebooklm.login_flow import _console_interpreter_for_cli

        cli = resolve_notebooklm_cli()
        if cli:
            found = _console_interpreter_for_cli(Path(cli))
            if found is not None:
                return found
    except Exception:
        log.debug("NotebookLM CLI interpreter lookup failed", exc_info=True)
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        console = exe.with_name("python.exe")
        if console.is_file():
            return console
    return exe if exe.is_file() else None


def _run_probe(profile: str, timeout: float) -> int | None:
    from voice_flow.video_flow_engine.notebooklm.config import get_storage_state_path

    storage = get_storage_state_path(profile)
    if not storage.is_file():
        return None
    interpreter = _probe_interpreter()
    if interpreter is None:
        return None
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        [str(interpreter), "-c", _PROBE, str(storage), profile],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        **kwargs,
    )
    for line in reversed((proc.stdout or "").splitlines()):
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if isinstance(payload, dict) and "tier" in payload:
            tier = payload.get("tier")
            return tier if isinstance(tier, int) and not isinstance(tier, bool) else None
    log.info("NotebookLM plan probe gave no tier (rc=%s)", proc.returncode)
    return None


def _generation(profile: str) -> int:
    try:
        from voice_flow.video_flow_engine.notebooklm.login_flow import get_session_generation

        return int(get_session_generation(profile))
    except Exception:
        return 0


def _profile_name(profile: str | None) -> str:
    from voice_flow.video_flow_engine.notebooklm.config import DEFAULT_PROFILE

    try:
        from voice_flow.video_flow_engine.notebooklm.config import resolve_notebooklm_profile

        return resolve_notebooklm_profile(profile) or DEFAULT_PROFILE
    except Exception:
        return (profile or DEFAULT_PROFILE).strip() or DEFAULT_PROFILE


def get_account_plan(profile: str | None = None, *, refresh: bool = False, timeout: float = 25.0) -> dict[str, Any]:
    """Plan for ``profile``; cached for six hours and reset by a new sign-in."""
    name = _profile_name(profile)
    now = time.time()
    generation = _generation(name)
    with _lock:
        cached = _cache.get(name)
    if cached and not refresh and cached.get("generation") == generation:
        ttl = CACHE_TTL_SECONDS if cached.get("tier") is not None else FAILED_RETRY_SECONDS
        if now - float(cached.get("checked_at") or 0) < ttl:
            return dict(cached)
    try:
        tier = _run_probe(name, timeout)
    except Exception as exc:  # timeout, missing runtime, expired session
        log.info("NotebookLM plan probe failed: %s", type(exc).__name__)
        tier = None
    result = {**plan_from_tier(tier), "profile": name, "checked_at": now, "generation": generation}
    with _lock:
        _cache[name] = result
    return dict(result)


def cinematic_allowed(profile: str | None = None) -> bool:
    try:
        return bool(get_account_plan(profile).get("is_ultra"))
    except Exception:
        return False


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def cached_plan(profile: str | None = None) -> dict[str, Any] | None:
    """The last known plan without any network call, or None."""
    name = _profile_name(profile)
    with _lock:
        cached = _cache.get(name)
    if not cached or cached.get("generation") != _generation(name):
        return None
    return dict(cached)


def cinematic_allowed_now(profile: str | None = None) -> bool:
    """Non-blocking check for UI threads: True only for a cached Ultra plan.

    A cold cache starts a background check for next time and answers False,
    so the user gets a Normal video instead of a frozen bar.
    """
    plan = cached_plan(profile)
    if plan is None:
        prewarm(profile)
        return False
    return bool(plan.get("is_ultra"))


def prewarm(profile: str | None = None) -> None:
    def _work() -> None:
        try:
            get_account_plan(profile)
        except Exception:
            pass

    threading.Thread(target=_work, daemon=True, name="notebooklm-plan-check").start()

"""Safe, lightweight update checker for AI Productivity Flow.

Queries GitHub Releases for the latest stable (non-prerelease) release.
Never downloads or executes binaries automatically.
Never blocks startup or ongoing workflows.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any
import urllib.request
import json

from voice_flow._version import VERSION

log = logging.getLogger("voice_flow.update_checker")

GITHUB_LATEST_RELEASE_URL = "https://api.github.com/repos/uzerkayat2004-gif/AI-Productivity-Flow/releases/latest"
CHECK_TIMEOUT_SECONDS = 5.0
DEFAULT_CACHE_TTL = 3600  # 1 hour

_cache: dict[str, Any] = {
    "timestamp": 0.0,
    "data": None,
}


def parse_semver(version_str: str) -> tuple[int, int, int]:
    """Parse a semantic version string (e.g. 'v1.0.1' or '1.0.0') into (major, minor, patch)."""
    cleaned = version_str.strip().lstrip("v").split("-")[0].split("+")[0]
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", cleaned)
    if not match:
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def is_version_newer(current: str, remote: str) -> bool:
    """Return True if remote semantic version is strictly greater than current."""
    curr_parsed = parse_semver(current)
    rem_parsed = parse_semver(remote)
    return rem_parsed > curr_parsed


def check_for_updates(force: bool = False, timeout: float = CHECK_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Check GitHub Releases for an update to AI Productivity Flow.

    Returns a dict with:
        current_version: str
        latest_version: str | None
        update_available: bool
        release_name: str | None
        release_url: str | None
        published_at: str | None
        checked: bool
        error: str | None
    """
    now = time.time()
    if not force and _cache["data"] is not None and (now - _cache["timestamp"] < DEFAULT_CACHE_TTL):
        return dict(_cache["data"])

    fallback_result: dict[str, Any] = {
        "current_version": VERSION,
        "latest_version": None,
        "update_available": False,
        "release_name": None,
        "release_url": None,
        "published_at": None,
        "checked": False,
        "error": None,
    }

    try:
        req = urllib.request.Request(
            GITHUB_LATEST_RELEASE_URL,
            headers={
                "User-Agent": f"AI-Productivity-Flow/{VERSION} (update-check)",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                fallback_result["error"] = f"HTTP {resp.status}"
                return fallback_result
            payload = json.loads(resp.read().decode("utf-8"))

        # Never treat prereleases as the latest stable update
        if payload.get("prerelease", False):
            fallback_result["checked"] = True
            return fallback_result

        tag_name = payload.get("tag_name", "")
        remote_version = tag_name.lstrip("v").strip()
        update_available = is_version_newer(VERSION, remote_version)

        result: dict[str, Any] = {
            "current_version": VERSION,
            "latest_version": remote_version,
            "update_available": update_available,
            "release_name": payload.get("name") or tag_name,
            "release_url": payload.get("html_url") or f"https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases/tag/{tag_name}",
            "published_at": payload.get("published_at"),
            "checked": True,
            "error": None,
        }

        _cache["timestamp"] = now
        _cache["data"] = result
        return result

    except Exception as exc:
        log.debug("Update check non-fatal error: %s", exc)
        fallback_result["error"] = str(exc)
        return fallback_result

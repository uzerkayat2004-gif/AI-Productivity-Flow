"""Configuration and executable path resolution for NotebookLM provider."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

DEFAULT_PROFILE = "video-flow-experiment"
FALLBACK_PROFILE = "default"
NOTEBOOKLM_ROOT = Path(os.environ.get("NOTEBOOKLM_HOME", Path.home() / ".notebooklm"))
PROFILES_ROOT = NOTEBOOKLM_ROOT / "profiles"
CANONICAL_EXPERIMENT_STORAGE = PROFILES_ROOT / "video-flow-experiment" / "storage_state.json"
ISOLATED_EXPERIMENT_DIR = Path(os.environ.get("NOTEBOOKLM_EXPERIMENT_DIR", Path.home() / "notebooklm-experiment"))
ISOLATED_CLI_PATH = ISOLATED_EXPERIMENT_DIR / ".venv" / "Scripts" / "notebooklm.exe"
ISOLATED_MCP_PATH = ISOLATED_EXPERIMENT_DIR / ".venv" / "Scripts" / "notebooklm-mcp.exe"
DEFAULT_MCP_CONFIG_PATH = ISOLATED_EXPERIMENT_DIR / "notebooklm-mcp-config.json"
REQUIRED_SESSION_COOKIES: tuple[str, ...] = (
    "__Secure-1PSID",
    "SID",
)


def get_profiles_dir() -> Path:
    """Return the root directory for NotebookLM profiles.

    Additive env override: NOTEBOOKLM_HOME may override the profiles root.
    When unset, resolution and defaults are byte-identical to prior behavior.
    """
    env_dir = os.environ.get("NOTEBOOKLM_PROFILES_DIR")
    if env_dir:
        resolved = Path(env_dir).expanduser().resolve()
        logger.debug("NotebookLM profiles root (NOTEBOOKLM_PROFILES_DIR): %s", resolved)
        return resolved
    env_home = os.environ.get("NOTEBOOKLM_HOME")
    if env_home:
        resolved = Path(env_home).expanduser().resolve() / "profiles"
        logger.debug("NotebookLM profiles root (NOTEBOOKLM_HOME): %s", resolved)
        return resolved
    logger.debug("NotebookLM profiles root (default): %s", PROFILES_ROOT)
    return PROFILES_ROOT


def get_profile_dir(profile: str | None = None) -> Path:
    """Return the directory path for a specific profile."""
    name = (profile or DEFAULT_PROFILE).strip()
    primary = get_profiles_dir() / name
    if primary.is_dir():
        return primary
    user_home_dir = Path.home() / ".notebooklm" / "profiles" / name
    if user_home_dir.is_dir():
        return user_home_dir
    return primary


def get_storage_state_path(profile: str | None = None) -> Path:
    """Return the storage_state.json path for a profile."""
    name = (profile or DEFAULT_PROFILE).strip()
    primary = get_profile_dir(name) / "storage_state.json"
    if primary.is_file():
        return primary
    if name == DEFAULT_PROFILE and CANONICAL_EXPERIMENT_STORAGE.is_file():
        return CANONICAL_EXPERIMENT_STORAGE
    canonical_home = Path.home() / ".notebooklm" / "profiles" / name / "storage_state.json"
    if canonical_home.is_file():
        return canonical_home
    return primary


def get_storage_backup_path(profile: str | None = None) -> Path:
    """Return the storage_state.backup.json path for a profile."""
    name = (profile or DEFAULT_PROFILE).strip()
    storage_path = get_storage_state_path(name)
    backup_path = storage_path.with_name("storage_state.backup.json")
    if backup_path.is_file():
        return backup_path
    canonical_dir = Path.home() / ".notebooklm"
    is_canonical = False
    try:
        is_canonical = canonical_dir in storage_path.parents
    except Exception:
        pass
    if is_canonical:
        canonical_backup = canonical_dir / "profiles" / name / "storage_state.backup.json"
        if canonical_backup.is_file():
            return canonical_backup
    return backup_path


# --------------------------------------------------------------------------
# Storage-state write guards (defense in depth against empty-cookie exports)
#
# Incident this guards against: a session-less browser context (or a metadata
# -only save path) exports {"cookies": []} and overwrites a valid
# storage_state.json; the empty export then propagates to backup + safe_copy,
# destroying the session AND the safety net, so the user must re-login after
# every app restart.
# --------------------------------------------------------------------------

PLACEHOLDER_EMAILS = frozenset({"your google account"})
GUARD_REJECTED_DIRNAME = "rejected"


def is_placeholder_email(email: str | None) -> bool:
    """True for known non-account placeholder emails (and empty values) that must never be persisted."""
    value = str(email or "").strip().lower()
    return (not value) or value in PLACEHOLDER_EMAILS


def load_json_object(path: Path | str) -> dict[str, Any] | None:
    """Best-effort read of a JSON file; returns None when missing or invalid."""
    try:
        p = Path(path)
        if not p.is_file() or p.stat().st_size == 0:
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def count_valid_cookies(data: Any) -> int:
    """Count cookies that carry a non-empty name and value.

    Accepts a parsed storage-state dict, a raw cookie list, or a JSON string of
    either. Unparseable input counts as 0 (the conservative reading used by the
    write guards).
    """
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return 0
    if isinstance(data, dict):
        data = data.get("cookies")
    if not isinstance(data, list):
        return 0
    count = 0
    for c in data:
        if isinstance(c, dict):
            name = str(c.get("name") or "").strip()
            val = str(c.get("value") or "").strip()
            if name and val:
                count += 1
    return count


def storage_file_cookie_count(path: Path | str) -> int:
    """Return the number of valid cookies stored in a storage-state file (0 when missing/invalid)."""
    return count_valid_cookies(load_json_object(path))


def has_nonempty_cookies(path: Path | str) -> bool:
    """True when the storage-state file contains at least one named, non-empty cookie."""
    return storage_file_cookie_count(path) > 0


def is_pytest_real_home_path(path: Path | str) -> bool:
    """True when running under pytest and *path* resolves inside the real ~/.notebooklm.

    The test suite must never read or write the user's live NotebookLM profiles
    (a test run once propagated test-fixture metadata into the real profile and
    destroyed the live session). Tests that exercise real code paths should
    monkeypatch the config path getters or set NOTEBOOKLM_HOME/PROFILES_DIR.
    """
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    try:
        resolved = Path(path).expanduser().resolve()
        real_home = (Path.home() / ".notebooklm").resolve()
        if resolved == real_home or real_home in resolved.parents:
            return True
    except Exception:
        return False
    return False


def atomic_write_text(target: Path | str, content: str) -> None:
    """Write via temp file + os.replace so a concurrent reader never sees a torn file."""
    t = Path(target)
    t.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=t.name + ".", suffix=".tmp", dir=str(t.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_name, str(t))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _rejected_copy_path(target: Path) -> Path:
    """Path where refused writes are archived (never auto-loaded by the app)."""
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return target.parent / GUARD_REJECTED_DIRNAME / f"{target.name}.{timestamp}.json"


def write_storage_state_guarded(
    target: Path | str,
    content: str,
    *,
    source: str,
) -> dict[str, Any]:
    """Atomically write a storage-state file, refusing empty-cookie exports.

    If *target* currently contains >=1 valid cookie and *content* contains 0,
    the write is refused: *content* is archived under ``rejected/`` and a loud
    warning is logged (cookie values are never logged). Returns a dict with
    ``written`` and, on refusal, ``reason``/``rejected_path``.
    """
    t = Path(target)
    new_count = count_valid_cookies(content)
    existing_count = storage_file_cookie_count(t)
    if existing_count > 0 and new_count == 0:
        rejected_path = _rejected_copy_path(t)
        try:
            atomic_write_text(rejected_path, content)
        except Exception:
            rejected_path = None
        logger.warning(
            "Refused to overwrite storage state %s (holds %d cookie(s)) with an empty-cookie "
            "export from %s; rejected export archived at %s",
            t, existing_count, source, rejected_path,
        )
        return {
            "written": False,
            "reason": "empty_cookie_export_rejected",
            "existing_cookies": existing_count,
            "rejected_path": str(rejected_path) if rejected_path else None,
        }
    atomic_write_text(t, content)
    return {"written": True, "existing_cookies": existing_count, "new_cookies": new_count}


def mirror_storage_state_guarded(
    content: str,
    storage_path: Path | str,
    targets: Sequence[Path | str],
    *,
    source: str,
) -> dict[str, Any]:
    """Mirror *content* to backup/safe-copy targets, never emptying a good mirror.

    A mirror target that currently holds >=1 valid cookie is never overwritten
    with a 0-cookie payload; skipped targets are reported in the result. Use
    this for backup rotation so the last KNOWN-GOOD state always survives.
    """
    new_count = count_valid_cookies(content)
    written: list[str] = []
    skipped: list[dict[str, Any]] = []
    for target in targets:
        t = Path(target)
        existing_count = storage_file_cookie_count(t)
        if existing_count > 0 and new_count == 0:
            logger.warning(
                "Refused to mirror empty-cookie state from %s over non-empty %s (%d cookie(s)) "
                "triggered by %s; last known-good backup preserved",
                storage_path, t, existing_count, source,
            )
            skipped.append({"path": str(t), "existing_cookies": existing_count})
            continue
        try:
            atomic_write_text(t, content)
            written.append(str(t))
        except Exception as exc:
            logger.warning("Could not mirror storage state to %s: %s", t, exc)
            skipped.append({"path": str(t), "error": str(exc)[:200]})
    return {"written": written, "skipped": skipped, "new_cookies": new_count}


def has_valid_storage_state(profile: str | None = None) -> bool:
    """Check if a profile has a valid, non-empty storage state file (or backup) with active cookies."""
    import json
    import time

    targets: list[Path] = []
    st_p = get_storage_state_path(profile)
    if st_p and st_p not in targets:
        targets.append(st_p)
    b_p = get_storage_backup_path(profile)
    if b_p and b_p not in targets:
        targets.append(b_p)
    if st_p:
        safe_p = st_p.with_name("storage_state.safe_copy.json")
        if safe_p not in targets:
            targets.append(safe_p)

    for target in targets:
        if target.is_file() and target.stat().st_size > 0:
            try:
                data = json.loads(target.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                cookies = data.get("cookies")
                if not isinstance(cookies, list) or not cookies:
                    continue

                # Validate active cookies: check non-empty values and no expired session tokens
                now = time.time()
                has_active = False
                expired = False
                for c in cookies:
                    if not isinstance(c, dict):
                        continue
                    name = str(c.get("name") or "").strip()
                    val = str(c.get("value") or "").strip()
                    if name and val:
                        has_active = True
                    expires = c.get("expires")
                    if expires is not None:
                        try:
                            exp_ts = float(expires)
                            if 0 < exp_ts <= now:
                                # Only the core long-lived session cookies (__Secure-1PSID / SID)
                                # invalidate the session when expired. Short-lived timestamp cookies
                                # (__Secure-1PSIDTS) rotate frequently and must not cause false auth expiration.
                                if name in {
                                    "SID",
                                    "__Secure-1PSID",
                                }:
                                    expired = True
                                    break
                        except (ValueError, TypeError):
                            pass
                if has_active and not expired:
                    return True
            except Exception:
                continue
    return False


def resolve_notebooklm_cli(explicit_path: Path | str | None = None) -> Path | None:
    r"""Resolve the NotebookLM executable path in strict precedence order.
    
    1. Explicit path argument
    2. Application setting (video_flow_notebooklm_cli)
    3. Environment variable (NOTEBOOKLM_CLI)
    4. Isolated experiment path (%USERPROFILE%\notebooklm-experiment\.venv\Scripts\notebooklm.exe)
    """
    if explicit_path:
        path = Path(explicit_path).expanduser().resolve()
        if path.is_file():
            return path

    try:
        from voice_flow.storage import StorageEngine
        storage = StorageEngine()
        stored = storage.get_setting("video_flow_notebooklm_cli")
        if stored:
            path = Path(stored).expanduser().resolve()
            if path.is_file():
                return path
    except Exception:
        pass

    env_path = os.environ.get("NOTEBOOKLM_CLI")
    if env_path:
        path = Path(env_path).expanduser().resolve()
        if path.is_file():
            return path

    if ISOLATED_CLI_PATH.is_file():
        return ISOLATED_CLI_PATH

    return None


def resolve_notebooklm_profile(explicit_profile: str | None = None) -> str:
    """Resolve the NotebookLM profile name with credential-aware fallback.
    
    Precedence:
    1. Explicit profile argument
    2. Application setting (video_flow_notebooklm_profile)
    3. Environment variable (NOTEBOOKLM_PROFILE)
    4. Default 'video-flow-experiment'
    
    Fallback behavior:
    If the candidate profile has no valid storage_state.json, check if
    'video-flow-experiment' or 'default' has valid credentials and alias/fallback seamlessly.
    """
    candidate: str | None = None

    if explicit_profile and str(explicit_profile).strip():
        candidate = str(explicit_profile).strip()
    else:
        try:
            from voice_flow.storage import StorageEngine
            storage = StorageEngine()
            stored = storage.get_setting("video_flow_notebooklm_profile")
            if stored and str(stored).strip():
                candidate = str(stored).strip()
        except Exception:
            pass

        if not candidate:
            env_profile = os.environ.get("NOTEBOOKLM_PROFILE")
            if env_profile and str(env_profile).strip():
                candidate = str(env_profile).strip()

    if not candidate:
        candidate = DEFAULT_PROFILE

    # If the candidate has valid credentials, use it directly
    if has_valid_storage_state(candidate):
        return candidate

    # Seamless alias/fallback check:
    # 1. Try canonical DEFAULT_PROFILE ("video-flow-experiment") if different from candidate
    if candidate != DEFAULT_PROFILE and has_valid_storage_state(DEFAULT_PROFILE):
        return DEFAULT_PROFILE

    # 2. Try FALLBACK_PROFILE ("default") if different from candidate and not DEFAULT_PROFILE
    if candidate != FALLBACK_PROFILE and candidate != DEFAULT_PROFILE and has_valid_storage_state(FALLBACK_PROFILE):
        return FALLBACK_PROFILE

    # If neither fallback has credentials, return the candidate
    return candidate


def resolve_notebooklm_mcp(explicit_path: Path | str | None = None) -> Path | None:
    r"""Resolve the NotebookLM MCP server executable path in strict precedence order.
    
    1. Explicit path argument
    2. Application setting (video_flow_notebooklm_mcp)
    3. Environment variable (NOTEBOOKLM_MCP)
    4. Isolated experiment path (%USERPROFILE%\notebooklm-experiment\.venv\Scripts\notebooklm-mcp.exe)
    5. Sibling of resolved CLI path
    6. System PATH lookup (shutil.which)
    """
    if explicit_path:
        path = Path(explicit_path).expanduser().resolve()
        if path.is_file():
            return path

    try:
        from voice_flow.storage import StorageEngine
        storage = StorageEngine()
        stored = storage.get_setting("video_flow_notebooklm_mcp")
        if stored:
            path = Path(stored).expanduser().resolve()
            if path.is_file():
                return path
    except Exception:
        pass

    env_path = os.environ.get("NOTEBOOKLM_MCP")
    if env_path:
        path = Path(env_path).expanduser().resolve()
        if path.is_file():
            return path

    if ISOLATED_MCP_PATH.is_file():
        return ISOLATED_MCP_PATH

    cli_path = resolve_notebooklm_cli()
    if cli_path is not None:
        sibling = cli_path.with_name("notebooklm-mcp.exe")
        if sibling.is_file():
            return sibling
        sibling_no_ext = cli_path.with_name("notebooklm-mcp")
        if sibling_no_ext.is_file():
            return sibling_no_ext

    import shutil
    which_path = shutil.which("notebooklm-mcp")
    if which_path:
        w_p = Path(which_path).expanduser().resolve()
        if w_p.is_file():
            return w_p

    return None


def get_master_token_path(profile: str | None = None) -> Path:
    """Return the master_token.json path for a profile."""
    name = (profile or DEFAULT_PROFILE).strip()
    return get_profile_dir(name) / "master_token.json"


def is_session_near_expiry(profile: str | None = None, *, threshold_seconds: float = 86400.0) -> bool:
    """Check whether the active Google session cookies are near expiration or expired.

    Inspects both __Secure-1PSIDTS and SID/Secure-1PSID. If __Secure-1PSIDTS is older than
    Google's rolling validity window or nearing threshold_seconds, returns True so that
    a background keepalive/refresh can be triggered ahead of time.
    """
    import json
    import time
    st_path = get_storage_state_path(profile)
    if not st_path.is_file() or st_path.stat().st_size == 0:
        return True
    try:
        data = json.loads(st_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return True
        cookies = data.get("cookies", [])
        if not isinstance(cookies, list) or not cookies:
            return True
        now = time.time()
        has_sid = False
        has_psidts = False
        for c in cookies:
            if not isinstance(c, dict):
                continue
            name = str(c.get("name") or "").strip()
            val = str(c.get("value") or "").strip()
            if not name or not val:
                continue
            if name in ("SID", "__Secure-1PSID"):
                has_sid = True
                exp = c.get("expires")
                if exp is not None:
                    try:
                        exp_ts = float(exp)
                        if 0 < exp_ts <= (now + 3600):
                            return True
                    except (ValueError, TypeError):
                        pass
            elif name in ("__Secure-1PSIDTS", "__Secure-3PSIDTS"):
                has_psidts = True
                exp = c.get("expires")
                if exp is not None:
                    try:
                        exp_ts = float(exp)
                        if 0 < exp_ts <= (now + threshold_seconds):
                            return True
                    except (ValueError, TypeError):
                        pass
        if not has_sid or not has_psidts:
            return True

        # Check storage state file modification age: Google rotates and invalidates
        # __Secure-1PSIDTS within 24 to 72 hours of inactivity, regardless of nominal
        # cookie header expiry. If the file hasn't been updated within threshold_seconds,
        # session is near or past sliding window expiry and must be refreshed.
        try:
            mtime = st_path.stat().st_mtime
            if mtime > 0 and (now - mtime) >= threshold_seconds:
                return True
        except Exception:
            pass

        return False
    except Exception:
        return True


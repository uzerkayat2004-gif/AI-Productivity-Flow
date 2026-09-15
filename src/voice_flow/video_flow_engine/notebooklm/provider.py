"""Deep NotebookLM Video Overview provider implementing the Video Flow provider seam."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse

from .config import (
    CANONICAL_EXPERIMENT_STORAGE,
    DEFAULT_PROFILE,
    get_storage_state_path,
    resolve_notebooklm_cli,
    resolve_notebooklm_profile,
)
from .models import (
    TERMINAL_FAILURE,
    TERMINAL_SUCCESS,
    VIDEO_FORMATS,
    VIDEO_STYLES,
    AuthStatus,
    NotebookLMVideoError,
    NotebookRef,
    SourceRef,
    VideoArtifact,
    VideoRequest,
)
from .document_profiler import (
    analyze_document_source,
    generate_cinematic_pacing_directive,
)
from .provenance import probe_media_file, write_notebooklm_provenance

logger = logging.getLogger(__name__)
SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")
Runner = Callable[[Sequence[str], float | None], Any]
ProgressCallback = Callable[[Mapping[str, Any]], None]

AUTH_EXPIRED_MESSAGE = "Google account login expired. Please sign in to NotebookLM in Video Flow settings."

RATE_LIMITED_MESSAGE = (
    "NotebookLM's usage limit is reached for this Google account. "
    "Your allowance refreshes about every 5 hours — try again then, "
    "switch to another Google account, or upgrade the NotebookLM plan. "
    "The sign-in itself is fine and stays connected."
)

ADAPTIVE_MARKER = "[Adaptive Video Directives]"
STYLE_MARKER = "[Visual Style]"
DEPTH_MARKER = "[Content Depth & Key Points]"
_SECTION_MARKERS = (ADAPTIVE_MARKER, STYLE_MARKER, DEPTH_MARKER)

# Source-file suffixes considered safe to read as text for section extraction.
_TEXT_SOURCE_SUFFIXES = frozenset({".txt", ".md", ".csv", ".json", ".html", ".xml", ".rtf"})


def _normalize_error_code(code: Any) -> str:
    return str(code or "").strip().lower().replace("-", "_")


def _is_rate_limited_error(code: str | None, message: str | None) -> bool:
    if _normalize_error_code(code) in {"rate_limited", "ratelimited"}:
        return True
    lowered = str(message or "").lower()
    return any(
        marker in lowered
        for marker in ("rate limited", "quota exceeded", "resource_exhausted", "too many requests")
    )


def _may_local_fallback(err: BaseException) -> bool:
    """Only TIMEOUT/network/generation errors may fall back to the local engine.

    Auth, rate-limit, and validation errors must surface to the caller.
    """
    code = getattr(err, "code", None)
    message = str(getattr(err, "message", None) or err or "")
    if _is_auth_expired_error(code, message):
        return False
    if _is_rate_limited_error(code, message):
        return False
    if _normalize_error_code(code) == "validation":
        return False
    return True


def _strip_marker_sections(prompt: Any, markers: Sequence[str] = _SECTION_MARKERS) -> str:
    """Deterministically remove injected directive sections headed by the given markers.

    Each section spans from its marker through (but excluding) the next marker
    or the end of the prompt, so generate() re-entry never duplicates blocks or
    keeps stale ones.
    """
    text = str(prompt or "")
    wanted = tuple(markers or ())
    if not text or not wanted:
        return text
    stripped_any = False
    while True:
        positions = [(text.find(marker), marker) for marker in wanted]
        positions = [(pos, marker) for pos, marker in positions if pos >= 0]
        if not positions:
            break
        stripped_any = True
        start = min(pos for pos, _ in positions)
        first_marker = next(marker for pos, marker in positions if pos == start)
        search_from = start + len(first_marker)
        later = [text.find(marker, search_from) for marker in wanted]
        later = [pos for pos in later if pos >= 0]
        end = min(later) if later else len(text)
        text = text[:start] + text[end:]
    return text.strip() if stripped_any else text


def _duration_undershoot(target_seconds: Any, actual_seconds: Any) -> bool:
    """Pure helper: True when the rendered media is under 50% of the target duration."""
    try:
        if target_seconds is None or actual_seconds is None:
            return False
        target = float(target_seconds)
        actual = float(actual_seconds)
    except (TypeError, ValueError):
        return False
    if target <= 0:
        return False
    return actual < 0.5 * target


def _assemble_prompt(
    base_prompt: Any,
    *,
    directive: Any = "",
    format_name: str = "",
    style: str | None = "auto",
    style_prompt: str | None = None,
    sections: Sequence[Mapping[str, Any]] | None = None,
    doc_profile: Mapping[str, Any] | None = None,
) -> str:
    """Rebuild the effective prompt deterministically: strip, then re-append.

    Idempotent by construction — feeding the output back in yields the same
    prompt with each marker appearing exactly once.
    """
    effective = _strip_marker_sections(base_prompt)
    clean_directive = str(directive or "").strip()
    if clean_directive:
        adaptive_block = f"{ADAPTIVE_MARKER}\n{clean_directive}"
        effective = f"{effective}\n\n{adaptive_block}".strip() if effective else adaptive_block

    style_name = str(style or "auto").strip()
    if str(format_name or "") in {"cinematic", "short"} and style_name and style_name != "auto":
        if style_name == "custom" and str(style_prompt or "").strip():
            style_desc = str(style_prompt).strip()
        else:
            style_desc = f"{style_name} visual aesthetic"
        style_block = f"{STYLE_MARKER}\nVisual Style: Render all visuals in a distinct {style_desc}."
        effective = f"{effective}\n\n{style_block}".strip() if effective else style_block

    depth_lines = [
        DEPTH_MARKER,
        "Ensure thorough, comprehensive coverage of the source document's substantive core.",
        "- Do not merely display or read out section titles or superficial headings. Thoroughly explain what each section means, why it matters, and its key arguments/findings.",
        "- Preserve essential context, mechanisms, and key takeaways for every topic so no crucial details are skipped.",
    ]
    section_list = [s for s in (sections or [])]
    if section_list and len(section_list) > 1:
        depth_lines.append("- Section-by-section outline to cover in detail:")
        for idx, sec in enumerate(section_list[:24], 1):
            entry = sec if isinstance(sec, Mapping) else {}
            stitle = str(entry.get("title") or f"Section {idx}")
            skp = str(entry.get("key_point") or "")
            depth_lines.append(f"  {idx}. {stitle}: {skp}" if skp else f"  {idx}. {stitle}")
    elif (
        isinstance(doc_profile, Mapping)
        and isinstance(doc_profile.get("substantive_concepts"), Sequence)
        and not isinstance(doc_profile.get("substantive_concepts"), (str, bytes))
        and len(doc_profile.get("substantive_concepts") or []) >= 2
    ):
        depth_lines.append("- Core conceptual propositions to unpack and thoroughly explain (explain how each works, its context, and real-world implications):")
        for idx, concept in enumerate(list(doc_profile.get("substantive_concepts") or [])[:12], 1):
            depth_lines.append(f"  {idx}. {concept}")
    elif section_list and len(section_list) == 1:
        entry = section_list[0] if isinstance(section_list[0], Mapping) else {}
        stitle = str(entry.get("title") or "Core Content")
        skp = str(entry.get("key_point") or "")
        depth_lines.append(f"- Key topic to cover in depth: {stitle} — {skp}" if skp else f"- Key topic to cover in depth: {stitle}")

    try:
        density = float(doc_profile.get("density_score", 1.0)) if isinstance(doc_profile, Mapping) else 1.0
    except (TypeError, ValueError):
        density = 1.0
    if density >= 1.35:
        depth_lines.append("- High Semantic Density Notice: This document contains dense, highly informative propositions. Devote dedicated narrative focus and distinct visuals to every proposition; avoid rapid superficial skimming. Provide comprehensive explanatory depth across the full video duration.")
    depth_block = "\n".join(depth_lines)
    effective = f"{effective}\n\n{depth_block}".strip() if effective else depth_block
    return effective


def _model_kwargs(cls: Any, kwargs: Mapping[str, Any]) -> dict[str, Any]:
    """Filter kwargs to fields the model class supports (defensive across versions)."""
    fields = getattr(cls, "__dataclass_fields__", None) or {}
    return {k: v for k, v in dict(kwargs).items() if k in fields}


def _with_provenance(artifact: Any, provenance_path: Any) -> Any:
    """Return an artifact copy carrying provenance_path, preserving non-field flags.

    Defensive across VideoArtifact versions: constructor-incompatible extra
    attributes (e.g. fallback/provider on older models) are re-applied via
    object.__setattr__ instead of the constructor.
    """
    cls = type(artifact)
    fields = set(getattr(cls, "__dataclass_fields__", {}) or {})
    state = dict(vars(artifact))
    kwargs = {k: v for k, v in state.items() if k in fields}
    kwargs["provenance_path"] = str(provenance_path)
    final = cls(**kwargs)
    for key, value in state.items():
        if key not in fields:
            try:
                object.__setattr__(final, key, value)
            except Exception:
                pass
    return final


def _mark_fallback_artifact(artifact: Any) -> Any:
    """Flag a local-fallback artifact even if the model class lacks the new fields."""
    for key, value in (("fallback", True), ("provider", "local-fallback")):
        try:
            object.__setattr__(artifact, key, value)
        except Exception:
            pass
    return artifact


def _is_auth_expired_error(code: str | None, message: str | None) -> bool:
    c = str(code or "").strip().lower()
    m = str(message or "").strip().lower()
    if c in {"auth_expired", "auth-expired", "session_expired"}:
        return True
    auth_expired_indicators = (
        "authentication expired",
        "auth expired",
        "expired or invalid",
        "login expired",
        "session expired",
        "re-authenticate",
        "run 'notebooklm login'",
        "accounts.google.com",
        "psidts_expired",
        "psidts expired",
        "missing required cookies",
        "no cookies found",
        "missing required authentication",
        "token expired",
        "token expire",
        "token is expired",
        "token invalid",
        "invalid token",
        "401 unauthorized",
        "401 client error",
        "failed to fetch authentication token",
        "could not fetch authentication token",
        "failed to authenticate",
    )
    return any(ind in m for ind in auth_expired_indicators)


_WORKSPACE_NOTEBOOK_CACHE: dict[tuple[str, str], str] = {}



def _atomic_write_text(target, content: str) -> None:
    """Write via temp file + os.replace so a concurrent reader never sees a torn file."""
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(str(tmp), str(target))
def _run_command(command: Sequence[str], timeout: float | None) -> Any:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "check": False,
        "shell": False,
        "close_fds": True,
    }
    if os.name == "nt" or sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = startupinfo
    return subprocess.run(list(command), **kwargs)


_ORIGINAL_RUN_COMMAND = _run_command


def _inspect_cookies(
    cookies: Sequence[Mapping[str, Any]],
    *,
    current_time: float | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Inspect and validate cookies list for required Google session tokens and PSIDTS expiration."""
    now = time.time() if current_time is None else float(current_time)

    cookie_map: dict[str, list[Mapping[str, Any]]] = {}
    for c in cookies:
        if isinstance(c, Mapping):
            name = str(c.get("name") or "").strip()
            if name:
                cookie_map.setdefault(name, []).append(c)

    cookie_names = set(cookie_map.keys())

    # Required Google session cookies: SID, HSID, SSID, __Secure-1PSID, __Secure-1PSIDTS, OSID
    missing: list[str] = []
    for req in ("__Secure-1PSID", "SID"):
        if req not in cookie_names or not any(str(c.get("value") or "").strip() for c in cookie_map[req]):
            missing.append(req)

    if missing:
        return False, f"Missing required authentication cookies: {', '.join(sorted(missing))}", {
            "cookies_found": sorted(cookie_names),
            "missing_cookies": sorted(missing),
        }

    # Check core session cookie expiration (__Secure-1PSID / SID)
    session_cookies: list[Mapping[str, Any]] = []
    for k in ("__Secure-1PSID", "SID"):
        session_cookies.extend(cookie_map.get(k, []))

    for c in session_cookies:
        expires = c.get("expires")
        if expires is not None:
            try:
                exp_ts = float(expires)
                if 0 < exp_ts <= now:
                    exp_dt = datetime.fromtimestamp(exp_ts, timezone.utc).isoformat()
                    return False, f"NotebookLM session expired: {c.get('name', 'session cookie')} expired at {exp_dt}", {
                        "cookies_found": sorted(cookie_names),
                        "session_expired": True,
                        "expires_at": exp_dt,
                        "psidts_expired": False,
                    }
            except (ValueError, TypeError, OSError):
                pass

    # Check sliding timestamp cookies (__Secure-1PSIDTS / __Secure-3PSIDTS)
    psidts_expired = False
    expired_psidts_name = None
    for k in ("__Secure-1PSIDTS", "__Secure-3PSIDTS"):
        for c in cookie_map.get(k, []):
            expires = c.get("expires")
            if expires is not None:
                try:
                    exp_ts = float(expires)
                    if 0 < exp_ts <= now:
                        psidts_expired = True
                        expired_psidts_name = str(c.get("name") or k)
                        break
                except (ValueError, TypeError, OSError):
                    pass
        if psidts_expired:
            break

    details: dict[str, Any] = {
        "cookies_found": sorted(cookie_names),
        "cookie_count": len(cookies),
        "psidts_expired": psidts_expired,
    }
    if psidts_expired and expired_psidts_name:
        details["expired_cookie"] = expired_psidts_name

    return True, "Valid session cookies", details


def _validate_storage_file(
    storage_file: Path,
    backup_file: Path | None = None,
    *,
    auto_restore: bool = True,
    current_time: float | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Fast offline validation of storage_state.json credentials with automatic backup recovery."""
    target = Path(storage_file).expanduser().resolve()
    candidate_backups: list[Path] = []
    if backup_file:
        candidate_backups.append(Path(backup_file).expanduser().resolve())
    primary_backup = target.with_name("storage_state.backup.json")
    if primary_backup not in candidate_backups:
        candidate_backups.append(primary_backup)
    safe_copy = target.with_name("storage_state.safe_copy.json")
    if safe_copy not in candidate_backups:
        candidate_backups.append(safe_copy)

    try:
        if target.is_relative_to((Path.home() / ".notebooklm").resolve()):
            home_nlm = Path.home() / ".notebooklm"
            # Cross-profile borrowing of default is strictly forbidden when targeting another profile
            if target.parent.name == "default":
                for fb_name in (
                    home_nlm / "storage_state.safe_copy.json",
                    home_nlm / "storage_state.backup.json",
                    home_nlm / "storage_state.json",
                ):
                    if fb_name not in candidate_backups:
                        candidate_backups.append(fb_name)
    except Exception:
        pass

    backup = candidate_backups[0] if candidate_backups else primary_backup

    # If storage_file is missing, empty, or corrupt, try auto-restore from backup candidates
    needs_restore = not target.is_file() or target.stat().st_size == 0

    if not needs_restore:
        try:
            content = target.read_text(encoding="utf-8")
            if not content.strip():
                needs_restore = True
            else:
                data = json.loads(content)
                if not isinstance(data, dict):
                    needs_restore = True
        except Exception:
            needs_restore = True

    switched_from = None
    try:
        from voice_flow.storage import storage
        switched_from = storage.get_setting("video_flow_notebooklm_switched_from")
        if switched_from:
            switched_from = str(switched_from).strip().lower()
    except Exception:
        pass

    if needs_restore and auto_restore:
        for cand in candidate_backups:
            if cand.is_file() and cand.stat().st_size > 0:
                try:
                    b_content = cand.read_text(encoding="utf-8")
                    b_data = json.loads(b_content)
                    if isinstance(b_data, dict) and isinstance(b_data.get("cookies"), list) and b_data.get("cookies"):
                        b_acc = (b_data.get("notebooklm") or {}).get("account", {}) or b_data.get("account", {})
                        b_email = (b_acc.get("email") if isinstance(b_acc, dict) else None) or b_data.get("email")
                        if switched_from and b_email and str(b_email).strip().lower() == switched_from:
                            continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        _atomic_write_text(target, b_content)
                        logger.info(f"Restored NotebookLM credentials from backup {cand} to {target}")
                        needs_restore = False
                        backup = cand
                        break
                except Exception as exc:
                    logger.warning(f"Failed to restore from backup {cand}: {exc}")

    if not target.is_file():
        return False, f"Storage file not found at {target}", {}

    try:
        content = target.read_text(encoding="utf-8")
        if not content.strip():
            return False, f"Storage file is empty at {target}", {}
        data = json.loads(content)
    except Exception as exc:
        return False, f"Failed to read or parse storage file {target}: {exc}", {}

    if not isinstance(data, dict):
        return False, f"Invalid storage state format in {target}", {}

    cookies = data.get("cookies", [])
    if not isinstance(cookies, list) or not cookies:
        # Check backup candidates before declaring failure
        if auto_restore:
            for cand in candidate_backups:
                if cand.is_file() and cand != target and cand.stat().st_size > 0:
                    try:
                        b_content = cand.read_text(encoding="utf-8")
                        b_data = json.loads(b_content)
                        if isinstance(b_data, dict):
                            b_acc = (b_data.get("notebooklm") or {}).get("account", {}) or b_data.get("account", {})
                            b_email = (b_acc.get("email") if isinstance(b_acc, dict) else None) or b_data.get("email")
                            if switched_from and b_email and str(b_email).strip().lower() == switched_from:
                                continue
                            b_cookies = b_data.get("cookies", [])
                            b_valid, _, _ = _inspect_cookies(b_cookies, current_time=current_time)
                            if b_valid:
                                _atomic_write_text(target, b_content)
                                logger.info(f"Populated empty storage state from valid backup {cand}")
                                data = b_data
                                cookies = b_cookies
                                backup = cand
                                break
                    except Exception:
                        pass
        if not isinstance(cookies, list) or not cookies:
            return False, f"No cookies found in storage file: {target}", data

    is_valid, msg, cookie_details = _inspect_cookies(cookies, current_time=current_time)
    if not is_valid:
        # If target has invalid/expired cookies, but a candidate backup is valid, attempt restore
        if auto_restore:
            for cand in candidate_backups:
                if cand.is_file() and cand != target:
                    try:
                        b_content = cand.read_text(encoding="utf-8")
                        b_data = json.loads(b_content)
                        if isinstance(b_data, dict):
                            b_cookies = b_data.get("cookies", [])
                            # Skip backup candidate if it holds identical core cookies to the invalid target
                            target_core = {
                                (str(c.get("name")), str(c.get("value")))
                                for c in cookies
                                if isinstance(c, dict) and c.get("name") in ("__Secure-1PSID", "SID", "__Secure-1PSIDTS")
                            }
                            cand_core = {
                                (str(c.get("name")), str(c.get("value")))
                                for c in b_cookies
                                if isinstance(c, dict) and c.get("name") in ("__Secure-1PSID", "SID", "__Secure-1PSIDTS")
                            }
                            if target_core and cand_core and (cand_core == target_core or cand_core.issubset(target_core)):
                                continue
                            b_valid, b_msg, b_details = _inspect_cookies(b_cookies, current_time=current_time)
                            if b_valid:
                                _atomic_write_text(target, b_content)
                                logger.info(f"Replaced invalid storage state with valid backup from {cand}")
                                data = b_data
                                cookies = b_cookies
                                cookie_details = b_details
                                is_valid = True
                                msg = "Authenticated successfully (restored from backup)"
                                backup = cand
                                break
                    except Exception:
                        pass
        elif auto_restore and cookie_details.get("psidts_expired"):
            # If target has valid core cookies but an expired PSIDTS, try restoring a fresh backup
            for cand in candidate_backups:
                if cand.is_file() and cand != target and cand.stat().st_size > 0:
                    try:
                        b_content = cand.read_text(encoding="utf-8")
                        b_data = json.loads(b_content)
                        if isinstance(b_data, dict):
                            b_cookies = b_data.get("cookies", [])
                            b_valid, b_msg, b_details = _inspect_cookies(b_cookies, current_time=current_time)
                            if b_valid and not b_details.get("psidts_expired"):
                                _atomic_write_text(target, b_content)
                                logger.info(f"Replaced storage state containing expired PSIDTS with fresh backup from {cand}")
                                data = b_data
                                cookies = b_cookies
                                cookie_details = b_details
                                msg = "Authenticated successfully (restored fresh PSIDTS from backup)"
                                backup = cand
                                break
                    except Exception:
                        pass

    if not is_valid:
        return False, msg, {**cookie_details, "storage_path": str(target)}

    # Auto-save valid credentials to backup and safe copy. Mirroring is guarded:
    # a stale backup is refreshed, but a mirror that already holds cookies is
    # never overwritten with a 0-cookie payload (last known-good state survives).
    if target.is_file() and target.stat().st_size > 0:
        from .config import mirror_storage_state_guarded

        stale_dests: list[Path] = []
        for backup_dest in (primary_backup, safe_copy):
            try:
                if not backup_dest.is_file() or backup_dest.stat().st_mtime < target.stat().st_mtime:
                    stale_dests.append(backup_dest)
            except Exception as exc:
                logger.debug(f"Could not auto-backup storage state to {backup_dest}: {exc}")
        if stale_dests:
            mirror_storage_state_guarded(content, target, stale_dests, source="provider._validate_storage_file")

    account_info = data.get("notebooklm", {}).get("account") if isinstance(data.get("notebooklm"), dict) else None
    details: dict[str, Any] = {
        "status": "ok",
        "storage_path": str(target),
        "backup_path": str(backup),
        **cookie_details,
    }
    if account_info:
        details["account"] = account_info

    return True, "Authenticated successfully (offline validation)", details


def _safe_id(value: str) -> str:
    cleaned = SAFE_ID.sub("-", str(value or "")).strip("-.")
    return cleaned[:120] or "notebooklm-video"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _nested(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    child = value.get(key)
    return child if isinstance(child, Mapping) else {}


def _text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _decode_json(raw: str) -> Any:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
        if not starts:
            raise NotebookLMVideoError("INVALID_RESPONSE", "NotebookLM CLI returned no JSON")
        try:
            return json.loads(text[min(starts) :])
        except json.JSONDecodeError as exc:
            raise NotebookLMVideoError("INVALID_RESPONSE", f"Malformed CLI JSON: {exc}") from exc


def _build_timings(
    *,
    t_auth: float = 0.0,
    t_notebook: float = 0.0,
    t_source: float = 0.0,
    t_cloud: float = 0.0,
    t_download: float = 0.0,
    t_probe: float = 0.0,
    t_total: float = 0.0,
) -> dict[str, float]:
    """Map high-resolution phase durations to telemetry dictionaries."""
    return {
        "auth": round(float(t_auth), 4),
        "t_auth": round(float(t_auth), 4),
        "auth_seconds": round(float(t_auth), 4),
        "notebook_setup": round(float(t_notebook), 4),
        "t_notebook": round(float(t_notebook), 4),
        "notebook_seconds": round(float(t_notebook), 4),
        "source_ingest": round(float(t_source), 4),
        "t_source": round(float(t_source), 4),
        "source_seconds": round(float(t_source), 4),
        "cloud_synthesis": round(float(t_cloud), 4),
        "t_cloud": round(float(t_cloud), 4),
        "cloud_seconds": round(float(t_cloud), 4),
        "download": round(float(t_download), 4),
        "t_download": round(float(t_download), 4),
        "download_seconds": round(float(t_download), 4),
        "probe": round(float(t_probe), 4),
        "t_probe": round(float(t_probe), 4),
        "probe_seconds": round(float(t_probe), 4),
        "total": round(float(t_total), 4),
        "t_total": round(float(t_total), 4),
        "total_seconds": round(float(t_total), 4),
    }


class NotebookLMVideoProvider:
    """Production provider wrapper hiding NotebookLM CLI execution, polling, and downloading."""

    def __init__(
        self,
        *,
        cli_path: Path | str | None = None,
        profile: str | None = None,
        workdir: Path | str | None = None,
        poll_interval_seconds: float = 5.0,
        runner: Runner | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        progress_callback: ProgressCallback | None = None,
        process_manager: Any = None,
        reuse_workspace: bool = False,
        cached_notebook_id: str | None = None,
        allow_local_fallback: bool = True,
    ) -> None:
        self.cli_path = Path(cli_path) if cli_path else resolve_notebooklm_cli()
        self.profile = resolve_notebooklm_profile(profile)
        self.workdir = Path(workdir) if workdir else Path.cwd()
        self.poll_interval_seconds = max(1.0, float(poll_interval_seconds))
        self.runner = runner or _run_command
        self.sleep = sleep
        self.monotonic = monotonic
        self.progress = progress_callback or (lambda _event: None)
        self.process_manager = process_manager
        self.reuse_workspace = bool(reuse_workspace)
        self._cached_notebook_id = str(cached_notebook_id).strip() if cached_notebook_id else None
        self.allow_local_fallback = bool(allow_local_fallback)
        self._active_job_id: str | None = None
        self._active_proc: Any = None
        self._proc_lock = threading.Lock()
        self._last_storage_sync_at: float = 0.0
        self._last_storage_sync_valid: bool = False
        self.sync_storage_state()

    def cancel(self, job_id: str | None = None) -> None:
        """Cancel running generation, terminate active CLI subprocess, and notify process manager."""
        target_id = job_id or getattr(self, "_active_job_id", None)
        if target_id and self.process_manager and hasattr(self.process_manager, "cancel_job"):
            self.process_manager.cancel_job(target_id)
        with self._proc_lock:
            proc = getattr(self, "_active_proc", None)
            if proc is not None and getattr(proc, "poll", None) is not None and proc.poll() is None:
                try:
                    if os.name == "nt" or sys.platform == "win32":
                        subprocess.run(
                            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                            capture_output=True,
                            text=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
                        )
                    else:
                        proc.terminate()
                except Exception:
                    pass

    def _now_monotonic(self) -> float:
        try:
            return float(self.monotonic())
        except (StopIteration, TypeError, ValueError):
            return 0.0

    def get_cached_notebook_id(self) -> str | None:
        """Retrieve cached notebook ID for the current workspace/workdir."""
        if self._cached_notebook_id:
            return self._cached_notebook_id
        try:
            key = (str(self.workdir.resolve()), self.profile)
        except Exception:
            key = (str(self.workdir), self.profile)
        if key in _WORKSPACE_NOTEBOOK_CACHE:
            cached = _WORKSPACE_NOTEBOOK_CACHE[key]
            if cached:
                self._cached_notebook_id = cached
                return cached
        # Check disk cache files in workdir
        for candidate_name in (".notebook_id", ".notebooklm_workspace.json"):
            cache_file = self.workdir / candidate_name
            if cache_file.is_file():
                try:
                    content = cache_file.read_text(encoding="utf-8").strip()
                    if content:
                        if candidate_name.endswith(".json"):
                            data = json.loads(content)
                            if isinstance(data, dict):
                                val = str(data.get("notebook_id") or data.get("id") or "").strip()
                                if val:
                                    self._cached_notebook_id = val
                                    _WORKSPACE_NOTEBOOK_CACHE[key] = val
                                    return val
                        else:
                            self._cached_notebook_id = content
                            _WORKSPACE_NOTEBOOK_CACHE[key] = content
                            return content
                except Exception as exc:
                    logger.debug("Failed reading notebook cache %s: %s", cache_file, exc)
        return None

    def save_cached_notebook_id(self, notebook_id: str) -> None:
        """Cache notebook ID in memory and write to workdir/.notebook_id."""
        nb_id = str(notebook_id or "").strip()
        if not nb_id:
            return
        self._cached_notebook_id = nb_id
        try:
            key = (str(self.workdir.resolve()), self.profile)
        except Exception:
            key = (str(self.workdir), self.profile)
        _WORKSPACE_NOTEBOOK_CACHE[key] = nb_id
        try:
            cache_file = self.workdir / ".notebook_id"
            cache_file.write_text(nb_id, encoding="utf-8")
        except Exception as exc:
            logger.debug("Failed writing notebook cache to %s: %s", self.workdir, exc)

    def clear_cached_notebook_id(self) -> None:
        """Clear cached notebook ID from memory and disk."""
        self._cached_notebook_id = None
        try:
            key = (str(self.workdir.resolve()), self.profile)
        except Exception:
            key = (str(self.workdir), self.profile)
        _WORKSPACE_NOTEBOOK_CACHE.pop(key, None)
        try:
            cache_file = self.workdir / ".notebook_id"
            if cache_file.is_file():
                cache_file.unlink()
        except Exception:
            pass

    def is_reuse_workspace_enabled(self, request: VideoRequest | None = None) -> bool:
        """Check if notebook reuse for the workspace is enabled."""
        if request is not None and getattr(request, "reuse_workspace", False):
            return True
        if self.reuse_workspace:
            return True
        env_flag = os.environ.get("NOTEBOOKLM_REUSE_WORKSPACE", "").strip().lower()
        if env_flag in {"1", "true", "yes", "on"}:
            return True
        try:
            from voice_flow.storage import StorageEngine
            storage = StorageEngine()
            if storage.get_setting("video_flow_notebooklm_reuse_workspace"):
                return True
        except Exception:
            pass
        return False

    def is_local_fallback_enabled(self, request: VideoRequest | None = None) -> bool:
        """Check if local fallback to Visual V2.1 is enabled.

        Defaults to True across the Video Flow engine stack unless explicitly
        disabled (allow_local_fallback=False in request, provider, or environment).
        """
        if request is not None and getattr(request, "allow_local_fallback", None) is False:
            return False
        if not self.allow_local_fallback:
            return False
        env_flag = os.environ.get("VIDEO_FLOW_ALLOW_LOCAL_FALLBACK", os.environ.get("NOTEBOOKLM_ALLOW_LOCAL_FALLBACK", "")).strip().lower()
        if env_flag in {"0", "false", "no", "off", "disable", "disabled"}:
            return False
        if env_flag in {"1", "true", "yes", "on", "enable", "enabled"}:
            return True
        try:
            from voice_flow.storage import StorageEngine
            storage = StorageEngine()
            val = storage.get_setting("video_flow_allow_local_fallback", None)
            if val is not None and not bool(val):
                return False
            val2 = storage.get_setting("video_flow_notebooklm_local_fallback", None)
            if val2 is not None and not bool(val2):
                return False
        except Exception:
            pass
        return True

    def _emit(self, state: str, **details: Any) -> None:
        try:
            self.progress({"provider": "notebooklm", "state": state, **details})
        except Exception:
            pass

    def _verify_duration(
        self,
        doc_profile: Any,
        actual_seconds: Any,
        *,
        job_id: str | None = None,
    ) -> bool:
        """Flag severe duration undershoot additively on the document profile.

        Returns True when actual < 50% of the target duration. Never raises.
        """
        try:
            if isinstance(doc_profile, Mapping):
                target = doc_profile.get("target_duration_seconds")
            else:
                target = getattr(doc_profile, "target_duration_seconds", None)
        except Exception:
            target = None
        if not _duration_undershoot(target, actual_seconds):
            return False
        try:
            actual = float(actual_seconds)  # type: ignore[arg-type]
            target_f = float(target)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        logger.warning(
            "Duration undershoot for job %s: rendered %.1fs vs target %.1fs (<50%%); check pacing/format selection.",
            job_id,
            actual,
            target_f,
        )
        self._emit(
            "duration_undershoot",
            job_id=job_id,
            target_duration_seconds=target_f,
            duration_actual_seconds=actual,
        )
        try:
            if isinstance(doc_profile, Mapping):
                try:
                    doc_profile["duration_actual_seconds"] = actual  # type: ignore[index]
                    doc_profile["duration_undershoot"] = True  # type: ignore[index]
                except Exception:
                    pass
            else:
                try:
                    object.__setattr__(doc_profile, "duration_actual_seconds", actual)
                    object.__setattr__(doc_profile, "duration_undershoot", True)
                except Exception:
                    pass
        except Exception:
            pass
        return True

    def _check_cancelled(self, job_id: str | None) -> None:
        if job_id and self.process_manager:
            if hasattr(self.process_manager, "is_cancelled") and self.process_manager.is_cancelled(job_id):
                raise NotebookLMVideoError("cancelled", f"Job {job_id} was cancelled")
            if hasattr(self.process_manager, "raise_if_cancelled"):
                self.process_manager.raise_if_cancelled(job_id)

    def _invoke(
        self,
        args: Sequence[str],
        *,
        timeout: float | None = None,
        retry_on_auth_expired: bool = True,
    ) -> Any:
        if not self.cli_path or not self.cli_path.is_file():
            raise NotebookLMVideoError(
                "DEPENDENCY_MISSING",
                f"NotebookLM CLI executable not found: {self.cli_path or 'None'}. "
                "Please configure video_flow_notebooklm_cli setting or NOTEBOOKLM_CLI environment variable."
            )
        self._check_cancelled(self._active_job_id)
        self.sync_storage_state()
        command = [str(self.cli_path), "--profile", self.profile, *map(str, args), "--json"]
        try:
            if self.runner is _ORIGINAL_RUN_COMMAND and _run_command is _ORIGINAL_RUN_COMMAND:
                kwargs: dict[str, Any] = {
                    "stdout": subprocess.PIPE,
                    "stderr": subprocess.PIPE,
                    "text": True,
                    "encoding": "utf-8",
                    "errors": "replace",
                    "shell": False,
                }
                if os.name == "nt" or sys.platform == "win32":
                    kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
                    startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
                    kwargs["startupinfo"] = startupinfo
                proc = subprocess.Popen(list(command), **kwargs)
                with self._proc_lock:
                    self._active_proc = proc
                if self._active_job_id and self.process_manager and hasattr(self.process_manager, "register"):
                    try:
                        self.process_manager.register(self._active_job_id, proc)
                    except Exception:
                        pass
                try:
                    stdout, stderr = proc.communicate(timeout=timeout)
                    result = subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)
                except subprocess.TimeoutExpired as exc:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        pass
                    with self._proc_lock:
                        if self._active_proc is proc:
                            self._active_proc = None
                    raise NotebookLMVideoError("TIMEOUT", "NotebookLM CLI command timed out") from exc
                finally:
                    if self._active_job_id and self.process_manager and hasattr(self.process_manager, "unregister"):
                        try:
                            self.process_manager.unregister(self._active_job_id, proc)
                        except Exception:
                            pass
                    with self._proc_lock:
                        if self._active_proc is proc:
                            self._active_proc = None
            else:
                result = self.runner(command, timeout)
        except subprocess.TimeoutExpired as exc:
            # Runner path: no live subprocess handle to terminate.
            raise NotebookLMVideoError("TIMEOUT", "NotebookLM CLI command timed out") from exc
        except OSError as exc:
            raise NotebookLMVideoError("DEPENDENCY", f"Unable to start NotebookLM CLI: {exc}") from exc

        self._check_cancelled(self._active_job_id)

        code = int(getattr(result, "returncode", 0) or 0)
        stdout = str(getattr(result, "stdout", "") or "")
        stderr = str(getattr(result, "stderr", "") or "")
        try:
            payload = _decode_json(stdout)
        except NotebookLMVideoError:
            if code:
                raw_err = stderr.strip() or stdout.strip() or "CLI failed"
                if _is_auth_expired_error("CLI_ERROR", raw_err):
                    if retry_on_auth_expired:
                        try:
                            from .login_flow import self_heal
                            heal = self_heal(profile=self.profile)
                            if not heal.get("ok") and not os.environ.get("PYTEST_CURRENT_TEST"):
                                from .browser_sync import sync_cookies_with_playwright
                                pw_sync = sync_cookies_with_playwright(profile=self.profile, headless=True, timeout_seconds=35)
                                if pw_sync.get("success"):
                                    heal = {"ok": True}
                            if heal.get("ok"):
                                self.sync_storage_state(force=True)
                                return self._invoke(args, timeout=timeout, retry_on_auth_expired=False)
                        except Exception:
                            pass
                    raise NotebookLMVideoError("auth_expired", AUTH_EXPIRED_MESSAGE, payload={"stderr": stderr, "stdout": stdout})
                raise NotebookLMVideoError("CLI_ERROR", raw_err)
            raise
        if code:
            data = _mapping(payload)
            nested_error = _nested(data, "error")
            message = _text(
                data.get("message"),
                nested_error.get("message"),
                data.get("error"),
                stderr,
                "NotebookLM CLI failed",
            )
            error_code = _text(
                data.get("code"),
                nested_error.get("code"),
                data.get("error_code"),
                "CLI_ERROR",
            )
            if _is_auth_expired_error(error_code, message):
                if retry_on_auth_expired:
                    try:
                        from .login_flow import self_heal
                        heal = self_heal(profile=self.profile)
                        if not heal.get("ok") and not os.environ.get("PYTEST_CURRENT_TEST"):
                            from .browser_sync import sync_cookies_with_playwright
                            pw_sync = sync_cookies_with_playwright(profile=self.profile, headless=True, timeout_seconds=35)
                            if pw_sync.get("success"):
                                heal = {"ok": True}
                        if heal.get("ok"):
                            self.sync_storage_state(force=True)
                            return self._invoke(args, timeout=timeout, retry_on_auth_expired=False)
                    except Exception:
                        pass
                raise NotebookLMVideoError(
                    "auth_expired",
                    AUTH_EXPIRED_MESSAGE,
                    payload=payload or {"stderr": stderr, "stdout": stdout, "raw_message": message},
                )
            _norm_code = _normalize_error_code(error_code)
            if _norm_code in {"rate_limited", "ratelimited"} or any(
                marker in message.lower() for marker in ("rate limited", "quota exceeded", "resource_exhausted", "too many requests")
            ):
                # Google's NotebookLM caps usage per account; since 2026-09-02
                # the allowance refreshes on a ~5-hour rolling window. Say so
                # plainly — "Rate limited." alone sent the user hunting for a
                # nonexistent app bug.
                message = RATE_LIMITED_MESSAGE
                error_code = "rate_limited"
            raise NotebookLMVideoError(error_code, message, payload=payload)
        return payload

    def get_storage_path(self) -> Path:
        """Resolve the path to storage_state.json for the current profile."""
        candidates = [
            self.workdir / ".notebooklm" / "profiles" / self.profile / "storage_state.json",
            self.workdir / "storage_state.json",
            self.workdir / ".notebooklm" / "storage_state.json",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        profile_path = get_storage_state_path(self.profile)
        if profile_path.is_file():
            return profile_path
        if self.profile == DEFAULT_PROFILE and CANONICAL_EXPERIMENT_STORAGE.is_file():
            return CANONICAL_EXPERIMENT_STORAGE
        return profile_path

    def get_backup_path(self) -> Path:
        """Resolve the path to storage_state.backup.json for the current profile."""
        storage = self.get_storage_path()
        return storage.with_name("storage_state.backup.json")

    def sync_storage_state(self, *, force: bool = False) -> dict[str, Any]:
        """Validate, auto-restore, and auto-backup the profile storage state.

        Successful validations are cached for 60s so hot paths (e.g. _invoke)
        skip redundant file I/O.
        """
        now = time.monotonic()
        if (
            not force
            and getattr(self, "_last_storage_sync_valid", False)
            and (now - getattr(self, "_last_storage_sync_at", 0.0)) < 60.0
        ):
            return {"valid": True, "message": "Authenticated successfully (cached validation)", "details": {"cached": True}}
        storage = self.get_storage_path()
        backup = self.get_backup_path()
        valid, msg, details = _validate_storage_file(storage, backup, auto_restore=True)
        if valid:
            self._last_storage_sync_at = now
            self._last_storage_sync_valid = True
        else:
            # Cache failures only briefly so recovery is re-attempted soon.
            self._last_storage_sync_at = now
            self._last_storage_sync_valid = False
        return {"valid": valid, "message": msg, "details": details}

    def backup_storage_state(self) -> Path | None:
        """Explicitly backup valid storage_state.json to storage_state.backup.json."""
        storage = self.get_storage_path()
        backup = self.get_backup_path()
        if storage.is_file() and storage.stat().st_size > 0:
            try:
                valid, _, _ = _validate_storage_file(storage, backup, auto_restore=False)
                if valid:
                    from .config import mirror_storage_state_guarded

                    mirror_storage_state_guarded(
                        storage.read_text(encoding="utf-8"),
                        storage,
                        [backup],
                        source="provider.backup_storage_state",
                    )
                    return backup
            except Exception as exc:
                logger.warning(f"Failed to backup storage state: {exc}")
        return None

    def restore_storage_state_from_backup(self) -> bool:
        """Explicitly restore storage_state.json from storage_state.backup.json.

        Guarded: refuses to overwrite a cookie-bearing storage_state.json with a
        0-cookie backup (the would-be backup content is archived under rejected/).
        """
        storage = self.get_storage_path()
        backup = self.get_backup_path()
        if backup.is_file() and backup.stat().st_size > 0:
            try:
                from .config import write_storage_state_guarded

                res = write_storage_state_guarded(
                    storage,
                    backup.read_text(encoding="utf-8"),
                    source="provider.restore_storage_state_from_backup",
                )
                return bool(res.get("written"))
            except Exception as exc:
                logger.warning(f"Failed to restore storage state from backup: {exc}")
        return False

    def inspect_session(self) -> dict[str, Any]:
        """Inspect and report detailed session health and cookie status."""
        storage = self.get_storage_path()
        backup = self.get_backup_path()
        valid, msg, details = _validate_storage_file(storage, backup, auto_restore=False)
        return {
            "profile": self.profile,
            "valid": valid,
            "message": msg,
            "storage_path": str(storage),
            "backup_path": str(backup),
            "backup_exists": backup.is_file(),
            **details,
        }

    def check_auth(
        self,
        *,
        raise_on_error: bool = True,
        online: bool = False,
        test_network: bool = False,
    ) -> AuthStatus:
        """Verify local Google authentication profile status.
        
        By default (online=False, test_network=False), performs fast offline
        credential validation on storage_state.json to prevent browser popups.
        If online=True or test_network=True is explicitly set, invokes CLI 'auth check'.
        """
        self._emit("auth_check", phase="auth", elapsed=0.0, elapsed_seconds=0.0)
        self.sync_storage_state()

        if online or test_network:
            try:
                cmd = ["auth", "check"]
                if test_network:
                    cmd.append("--test")
                data = _mapping(self._invoke(cmd, timeout=60))
                is_ok = _text(data.get("status")).casefold() == "ok"
                if not is_ok:
                    raw_msg = _text(data.get("message"), "NotebookLM profile is not authenticated")
                    if _is_auth_expired_error("AUTH", raw_msg):
                        if raise_on_error:
                            raise NotebookLMVideoError("auth_expired", AUTH_EXPIRED_MESSAGE, payload=data)
                        return AuthStatus(
                            status="unauthenticated",
                            profile=self.profile,
                            storage_path=data.get("storage_path"),
                            authenticated=False,
                            message=AUTH_EXPIRED_MESSAGE,
                            details=data,
                        )
                    if raise_on_error:
                        raise NotebookLMVideoError(
                            "AUTH",
                            raw_msg,
                            payload=data,
                        )
                    return AuthStatus(
                        status="unauthenticated",
                        profile=self.profile,
                        storage_path=data.get("storage_path"),
                        authenticated=False,
                        message=raw_msg,
                        details=data,
                    )
                self.backup_storage_state()
                return AuthStatus(
                    status="ok",
                    profile=self.profile,
                    storage_path=data.get("storage_path"),
                    authenticated=True,
                    message="Authenticated successfully",
                    details=data,
                )
            except NotebookLMVideoError as exc:
                if exc.code in {"AUTH", "auth_expired"} and not raise_on_error:
                    return AuthStatus(
                        status="unauthenticated",
                        profile=self.profile,
                        authenticated=False,
                        message=AUTH_EXPIRED_MESSAGE if exc.code == "auth_expired" else str(exc),
                    )
                raise

        # Fast offline credential validation on storage_state.json
        storage_path = self.get_storage_path()
        backup_path = self.get_backup_path()
        valid, msg, details = _validate_storage_file(storage_path, backup_path, auto_restore=True)
        from .config import is_session_near_expiry
        near_expiry = is_session_near_expiry(self.profile, threshold_seconds=86400.0)
        if not valid or details.get("psidts_expired") or near_expiry:
            # Auto-recovery layer 1: attempt zero-interaction browser sync / backup restore
            try:
                from .browser_sync import auto_sync_from_browser

                sync_res = auto_sync_from_browser(profile=self.profile)
                if sync_res.get("success"):
                    valid, msg, details = _validate_storage_file(storage_path, backup_path, auto_restore=True)
            except Exception:
                pass

            # Auto-recovery layer 2: headless self-heal (master token refresh / live session rotation)
            if not valid or details.get("psidts_expired") or is_session_near_expiry(self.profile, threshold_seconds=86400.0):
                try:
                    from .login_flow import self_heal

                    heal_res = self_heal(profile=self.profile)
                    if heal_res.get("ok"):
                        valid, msg, details = _validate_storage_file(storage_path, backup_path, auto_restore=True)
                except Exception:
                    pass

            # Auto-recovery layer 3: headless Playwright live session rotation
            if (not valid or details.get("psidts_expired") or is_session_near_expiry(self.profile, threshold_seconds=86400.0)) and not os.environ.get("PYTEST_CURRENT_TEST"):
                try:
                    from .browser_sync import sync_cookies_with_playwright

                    pw_res = sync_cookies_with_playwright(profile=self.profile, headless=True, timeout_seconds=35)
                    if pw_res.get("success"):
                        valid, msg, details = _validate_storage_file(storage_path, backup_path, auto_restore=True)
                except Exception:
                    pass

        if not valid:
            if _is_auth_expired_error("AUTH", msg) or details.get("psidts_expired"):
                if raise_on_error:
                    raise NotebookLMVideoError(
                        "auth_expired",
                        AUTH_EXPIRED_MESSAGE,
                        payload={"storage_path": str(storage_path), "message": msg, **details},
                    )
                return AuthStatus(
                    status="unauthenticated",
                    profile=self.profile,
                    storage_path=str(storage_path),
                    authenticated=False,
                    message=AUTH_EXPIRED_MESSAGE,
                    details=details,
                )
            if raise_on_error:
                raise NotebookLMVideoError(
                    "auth_expired",
                    "Google account login expired. Please sign in to NotebookLM in Video Flow settings.",
                    payload={"storage_path": str(storage_path), "message": msg, **details},
                )
            return AuthStatus(
                status="unauthenticated",
                profile=self.profile,
                storage_path=str(storage_path),
                authenticated=False,
                message=msg,
                details=details,
            )

        return AuthStatus(
            status="ok",
            profile=self.profile,
            storage_path=str(storage_path),
            authenticated=True,
            message=msg,
            details=details,
        )

    def create_notebook(self, title: str) -> NotebookRef:
        self._emit("notebook_create", phase="notebook_setup", title=title)
        data = _mapping(self._invoke(("create", title), timeout=60))
        notebook = _nested(data, "notebook")
        notebook_id = _text(notebook.get("id"), data.get("notebook_id"), data.get("id"))
        if not notebook_id:
            raise NotebookLMVideoError("INVALID_RESPONSE", "Notebook creation returned no ID", payload=data)
        return NotebookRef(notebook_id, _text(notebook.get("title"), title))

    def add_source(
        self,
        notebook_id: str,
        *,
        source_file: Path | None = None,
        source_url: str | None = None,
        source_text: str | None = None,
        title: str = "Article",
        source_id: str | None = None,
    ) -> SourceRef:
        new_inputs: dict[str, Any] = {}
        if source_file is not None:
            new_inputs["source_file"] = source_file
        if source_url:
            new_inputs["source_url"] = source_url
        if source_text is not None:
            new_inputs["source_text"] = source_text
        if source_id and new_inputs:
            # A caller-supplied source body supersedes a cached source_id: the
            # old id belongs to a different notebook content, so waiting on it
            # would index stale material. Re-add and warn instead.
            logger.warning(
                "add_source ignoring stale source_id %s for notebook %s: new source inputs provided; re-adding.",
                source_id,
                notebook_id,
            )
            source_id = None
        if source_id:
            return self.wait_for_source(notebook_id, source_id, title=title)
        choices = [source_file is not None, bool(source_url), source_text is not None]
        if sum(choices) != 1:
            raise NotebookLMVideoError("VALIDATION", "Provide exactly one source_file, source_url, or source_text")

        source_type = "file"
        if source_file is not None:
            path = Path(source_file).expanduser().resolve()
            if not path.is_file():
                raise NotebookLMVideoError("SOURCE_NOT_FOUND", f"Source file does not exist: {path}")
            content = str(path)
            source_args = (content, "--notebook", notebook_id, "--type", "file", "--title", title)
            source_type = "file"
        elif source_url is not None:
            if not _is_url(source_url):
                raise NotebookLMVideoError("VALIDATION", f"Invalid source URL: {source_url}")
            source_args = (source_url, "--notebook", notebook_id, "--type", "url", "--title", title)
            source_type = "url"
        else:
            content_text = str(source_text or "")
            if not content_text.strip():
                raise NotebookLMVideoError("VALIDATION", "source_text cannot be empty")
            source_dir = self.workdir / "sources"
            source_dir.mkdir(parents=True, exist_ok=True)
            path = source_dir / f"{_safe_id(title)}.txt"
            path.write_text(content_text, encoding="utf-8")
            source_args = (str(path), "--notebook", notebook_id, "--type", "file", "--title", title)
            source_type = "text"

        self._emit("source_add", phase="source_ingest", notebook_id=notebook_id)
        data = _mapping(self._invoke(("source", "add", *source_args), timeout=120))
        source = _nested(data, "source")
        resolved_id = _text(source.get("id"), data.get("source_id"), data.get("id"))
        if not resolved_id:
            raise NotebookLMVideoError("INVALID_RESPONSE", "Source upload returned no ID", payload=data)
        return self.wait_for_source(notebook_id, resolved_id, title=_text(source.get("title"), title), source_type=source_type)

    def wait_for_source(
        self,
        notebook_id: str,
        source_id: str,
        *,
        title: str = "Article",
        timeout_seconds: int = 120,
        source_type: str = "text",
    ) -> SourceRef:
        self._emit("source_wait", phase="source_ingest", notebook_id=notebook_id, source_id=source_id)
        data = _mapping(
            self._invoke(
                ("source", "wait", source_id, "--notebook", notebook_id, "--timeout", str(timeout_seconds)),
                timeout=timeout_seconds + 30,
            )
        )
        status = _text(data.get("status"), data.get("status_label"), "unknown").casefold()
        if status not in {"ready", "completed"}:
            raise NotebookLMVideoError("SOURCE_FAILED", f"Source status is {status}", payload=data)
        return SourceRef(source_id, _text(data.get("title"), title), status, source_type=source_type)

    def start_video(self, request: VideoRequest, notebook_id: str, source_id: str) -> tuple[str, str | None]:
        request.validate()
        prompt_dir = self.workdir / "prompts"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = prompt_dir / f"{_safe_id(request.job_id)}.txt"
        effective_prompt = request.prompt
        if request.document_profile and isinstance(request.document_profile, Mapping):
            directive = str(request.document_profile.get("adaptive_prompt_directive") or "").strip()
            if directive:
                # Deterministic rebuild: strip any stale injected sections, then
                # re-append the current directive (no exact-substring guard, so
                # re-entry never duplicates or keeps a stale block).
                effective_prompt = _strip_marker_sections(effective_prompt, (ADAPTIVE_MARKER,))
                adaptive_block = f"{ADAPTIVE_MARKER}\n{directive}"
                effective_prompt = (
                    f"{effective_prompt}\n\n{adaptive_block}".strip()
                    if str(effective_prompt or "").strip()
                    else adaptive_block
                )
        prompt_file.write_text(effective_prompt, encoding="utf-8")
        args: list[str] = [
            "generate",
            "video",
            "--notebook",
            notebook_id,
            "--source",
            source_id,
            "--format",
            request.format,
            "--prompt-file",
            str(prompt_file),
        ]
        if request.language:
            args.extend(("--language", request.language))
        if request.format not in {"cinematic", "short"}:
            args.extend(("--style", request.style))
            if request.style == "custom" and request.style_prompt:
                args.extend(("--style-prompt", request.style_prompt))
        self._emit("video_start", phase="cloud_synthesis", notebook_id=notebook_id, source_id=source_id, format=request.format)
        data = _mapping(self._invoke(args, timeout=120))
        task_id = _text(data.get("task_id"), data.get("artifact_id"), data.get("id"))
        if not task_id:
            raise NotebookLMVideoError("INVALID_RESPONSE", "Video generation returned no task ID", payload=data)
        return task_id, _text(data.get("url")) or None

    def wait_for_artifact(
        self,
        notebook_id: str,
        task_id: str,
        *,
        timeout_seconds: int = 1_800,
        job_id: str | None = None,
    ) -> tuple[str, str | None]:
        started = self._now_monotonic()
        self._check_cancelled(job_id)
        self._emit(
            "video_poll",
            phase="cloud_synthesis",
            elapsed=0.0,
            elapsed_seconds=0.0,
            notebook_id=notebook_id,
            task_id=task_id,
            status="generating",
        )

        # 1. Primary fast path: In-process CLI keep-alive wait (single process invocation)
        try:
            wait_timeout = max(30, int(timeout_seconds))
            wait_cmd = (
                "artifact",
                "wait",
                task_id,
                "--notebook",
                notebook_id,
                "--interval",
                "3",
                "--timeout",
                str(wait_timeout),
            )
            data = _mapping(self._invoke(wait_cmd, timeout=wait_timeout + 30))
            status = _text(data.get("status"), "unknown").casefold()
            artifact_url = _text(data.get("url")) or None
            elapsed_sec = round(self._now_monotonic() - started, 2)
            if status in TERMINAL_SUCCESS:
                self._emit(
                    "video_poll",
                    phase="cloud_synthesis",
                    elapsed=elapsed_sec,
                    elapsed_seconds=elapsed_sec,
                    notebook_id=notebook_id,
                    task_id=task_id,
                    status=status,
                )
                return status, artifact_url
            if status in TERMINAL_FAILURE:
                self._emit(
                    "video_poll",
                    phase="cloud_synthesis",
                    elapsed=elapsed_sec,
                    elapsed_seconds=elapsed_sec,
                    notebook_id=notebook_id,
                    task_id=task_id,
                    status=status,
                )
                raise NotebookLMVideoError(
                    "ARTIFACT_FAILED",
                    _text(data.get("error"), data.get("message"), f"Artifact status: {status}"),
                    payload=data,
                )
            logger.info("artifact wait returned non-terminal status '%s'; falling back to adaptive polling", status)
        except NotebookLMVideoError as exc:
            if exc.code in ("ARTIFACT_FAILED", "cancelled"):
                raise
            if exc.code == "TIMEOUT" and (self._now_monotonic() - started) >= timeout_seconds:
                raise
            logger.warning("CLI artifact wait did not reach terminal state (%s); falling back to adaptive polling", exc)
        except Exception as exc:
            self._check_cancelled(job_id)
            logger.warning("CLI artifact wait failed (%s); falling back to adaptive polling", exc)

        # 2. Fallback: Adaptive polling loop (with bounded retries on transient errors)
        poll_delay = min(2.0, self.poll_interval_seconds)
        max_delay = min(10.0, max(5.0, self.poll_interval_seconds))
        transient_retries = 0
        while True:
            self._check_cancelled(job_id)
            try:
                data = _mapping(
                    self._invoke(("artifact", "poll", task_id, "--notebook", notebook_id), timeout=90)
                )
            except NotebookLMVideoError as exc:
                self._check_cancelled(job_id)
                if exc.code in TERMINAL_FAILURE or _is_auth_expired_error(exc.code, str(exc)) or _is_rate_limited_error(exc.code, str(exc)):
                    raise
                if transient_retries >= 4:
                    raise
                transient_retries += 1
                self._emit(
                    "video_poll_retry",
                    phase="cloud_synthesis",
                    notebook_id=notebook_id,
                    task_id=task_id,
                    attempt=transient_retries,
                    code=exc.code,
                )
                self.sleep(min(max_delay, poll_delay * (2 ** (transient_retries - 1))))
                continue
            except Exception as exc:
                self._check_cancelled(job_id)
                message = str(exc or "").lower()
                if "cancel" in message:
                    raise
                if transient_retries >= 4:
                    raise NotebookLMVideoError("DEPENDENCY", f"Artifact polling failed: {exc}") from exc
                transient_retries += 1
                self._emit(
                    "video_poll_retry",
                    phase="cloud_synthesis",
                    notebook_id=notebook_id,
                    task_id=task_id,
                    attempt=transient_retries,
                )
                self.sleep(min(max_delay, poll_delay * (2 ** (transient_retries - 1))))
                continue
            transient_retries = 0
            status = _text(data.get("status"), "unknown").casefold()
            artifact_url = _text(data.get("url")) or None
            elapsed_sec = round(self._now_monotonic() - started, 2)
            self._emit(
                "video_poll",
                phase="cloud_synthesis",
                elapsed=elapsed_sec,
                elapsed_seconds=elapsed_sec,
                notebook_id=notebook_id,
                task_id=task_id,
                status=status,
            )
            if status in TERMINAL_SUCCESS:
                return status, artifact_url
            if status in TERMINAL_FAILURE:
                raise NotebookLMVideoError(
                    "ARTIFACT_FAILED",
                    _text(data.get("error"), data.get("message"), f"Artifact status: {status}"),
                    payload=data,
                )
            elapsed = self._now_monotonic() - started
            if elapsed >= timeout_seconds:
                raise NotebookLMVideoError("TIMEOUT", f"Artifact did not complete within {timeout_seconds}s", payload=data)
            self.sleep(min(poll_delay, max(0.1, timeout_seconds - elapsed)))
            poll_delay = min(max_delay, poll_delay * 1.5)

    def download_video(self, notebook_id: str, artifact_id: str, output_path: Path) -> Path:
        target = Path(output_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        self._emit("video_download", phase="download", notebook_id=notebook_id, artifact_id=artifact_id, output_path=str(target))
        self._invoke(
            ("download", "video", "--notebook", notebook_id, "--artifact", artifact_id, "--force", str(target)),
            timeout=300,
        )
        if not target.is_file() or target.stat().st_size <= 0:
            raise NotebookLMVideoError("DOWNLOAD_FAILED", f"No non-empty MP4 at {target}")
        return target

    def generate(self, request: VideoRequest) -> VideoArtifact:
        """Execute full end-to-end NotebookLM video generation pipeline with phase telemetry."""
        t0 = time.perf_counter()
        t_auth = 0.0
        t_notebook = 0.0
        t_source = 0.0
        t_cloud = 0.0
        t_download = 0.0
        t_probe = 0.0
        t_total = 0.0

        # Automatic document profiling & adaptive prompt directive injection
        original_prompt = request.prompt
        request_target_duration = getattr(request, "target_duration_seconds", None)
        doc_profile = request.document_profile
        if doc_profile is None:
            source_text = request.source_text
            source_file = request.source_file
            if source_text or source_file:
                profile_obj = analyze_document_source(
                    text=source_text,
                    source_path=source_file,
                    requested_format=request.format,
                    target_duration_seconds=request_target_duration,
                    task=request.prompt,
                    title=request.title,
                    focus=request.prompt,
                )
            else:
                profile_obj = analyze_document_source(
                    text=request.source_url or request.prompt or request.title,
                    requested_format=request.format,
                    target_duration_seconds=request_target_duration,
                    task=request.prompt,
                    title=request.title,
                    focus=request.prompt,
                )
            doc_profile = profile_obj.to_dict()
        elif hasattr(doc_profile, "to_dict"):
            doc_profile = doc_profile.to_dict()
        else:
            doc_profile = dict(doc_profile)

        # Align document profile directive and recommendation to the concrete request.format.
        # With a real live source (text/file/url), recompute the directive for the
        # new format — including format-switches on a supplied document_profile.
        # Only when NO live source is available do we skip the dummy '"word "*N'
        # rebuild and instead retarget format + duration display while
        # preserving the existing sections and directive.
        if request.format in VIDEO_FORMATS and doc_profile.get("recommended_format") != request.format:
            has_live_source = bool(
                request.source_text
                or (request.source_file and Path(request.source_file).is_file())
                or request.source_url
            )
            if not has_live_source:
                doc_profile["recommended_format"] = request.format
                try:
                    from .document_profiler import format_duration_display
                    doc_profile["target_duration_display"] = format_duration_display(
                        int(doc_profile.get("target_duration_seconds") or 0)
                    )
                except Exception:
                    pass
            else:
                if request.source_text:
                    sample_text = request.source_text
                    source_p = None
                elif request.source_file and Path(request.source_file).is_file():
                    sample_text = None
                    source_p = request.source_file
                else:
                    sample_text = request.source_url or request.prompt or request.title or "topic overview"
                    source_p = None

                recomputed = analyze_document_source(
                    text=sample_text,
                    source_path=source_p,
                    requested_format=request.format,
                    task=request.prompt,
                    title=request.title,
                    focus=request.prompt,
                )
                doc_profile["recommended_format"] = request.format
                doc_profile["target_duration_seconds"] = recomputed.target_duration_seconds
                doc_profile["target_duration_display"] = recomputed.target_duration_display
                doc_profile["pacing_style"] = recomputed.pacing_style
                doc_profile["chapter_breakdown"] = list(recomputed.chapter_breakdown)
                doc_profile["adaptive_prompt_directive"] = recomputed.adaptive_prompt_directive
                if recomputed.sections:
                    doc_profile["sections"] = list(recomputed.sections)
                    doc_profile["section_count"] = recomputed.section_count
                doc_profile["density_score"] = recomputed.density_score
                doc_profile["content_value_rating"] = recomputed.content_value_rating
                doc_profile["concept_count"] = recomputed.concept_count
                doc_profile["effective_word_count"] = recomputed.effective_word_count
                doc_profile["redundancy_score"] = recomputed.redundancy_score
                doc_profile["substantive_concepts"] = list(recomputed.substantive_concepts)

        # For cinematic videos, ensure strict target duration constraint is explicitly passed
        directive = str(doc_profile.get("adaptive_prompt_directive") or "")
        if request.format == "cinematic":
            duration_disp = doc_profile.get("target_duration_display")
            pacing = doc_profile.get("pacing_style", "measured")
            if not duration_disp:
                duration_disp = "~2m 00s"
            cinematic_constraint = generate_cinematic_pacing_directive(duration_disp, pacing)
            if "STRICT DURATION CONSTRAINT" not in directive:
                directive = f"{cinematic_constraint} {directive}".strip()
                doc_profile["adaptive_prompt_directive"] = directive

        # Resolve the sections feeding the depth block. Prefer the profile's own
        # sections; only read the source file for text-like suffixes.
        resolved_sections = doc_profile.get("sections") if isinstance(doc_profile, Mapping) else None
        if not resolved_sections:
            from .document_profiler import extract_document_sections
            if request.source_text:
                resolved_sections = extract_document_sections(request.source_text)
            elif request.source_file:
                try:
                    suffix = Path(request.source_file).suffix.lower()
                except Exception:
                    suffix = ""
                if suffix in _TEXT_SOURCE_SUFFIXES:
                    p = Path(request.source_file)
                    if p.is_file():
                        try:
                            resolved_sections = extract_document_sections(
                                p.read_text(encoding="utf-8", errors="replace")
                            )
                        except Exception:
                            resolved_sections = None

        effective_prompt = _assemble_prompt(
            original_prompt,
            directive=directive,
            format_name=request.format,
            style=getattr(request, "style", "auto"),
            style_prompt=getattr(request, "style_prompt", None),
            sections=resolved_sections,
            doc_profile=doc_profile,
        )

        request = VideoRequest(
            **_model_kwargs(
                VideoRequest,
                {
                    "title": request.title,
                    "prompt": effective_prompt,
                    "output_path": request.output_path,
                    "source_file": request.source_file,
                    "source_url": request.source_url,
                    "source_text": request.source_text,
                    "notebook_id": request.notebook_id,
                    "source_id": request.source_id,
                    "task_id": request.task_id,
                    "format": request.format,
                    "style": request.style,
                    "style_prompt": request.style_prompt,
                    "language": request.language,
                    "job_id": request.job_id,
                    "timeout_seconds": request.timeout_seconds,
                    "profile": request.profile,
                    "retain_notebook": request.retain_notebook,
                    "reuse_workspace": request.reuse_workspace,
                    "allow_local_fallback": getattr(request, "allow_local_fallback", True),
                    "timings": request.timings,
                    "document_profile": doc_profile,
                    "target_duration_seconds": request_target_duration,
                },
            )
        )

        started_at = _now()
        notebook_id = request.notebook_id
        if not notebook_id and self.is_reuse_workspace_enabled(request):
            notebook_id = self.get_cached_notebook_id()
            if notebook_id:
                logger.info("Reusing cached workspace notebook: %s", notebook_id)

        source: SourceRef | None = None
        task_id: str | None = request.task_id
        artifact_url: str | None = None
        self._active_job_id = request.job_id
        self._check_cancelled(request.job_id)

        try:
            # 1. Auth verification phase
            t_auth_start = time.perf_counter()
            self._emit("auth_check", phase="auth", elapsed=round(time.perf_counter() - t0, 4), elapsed_seconds=round(time.perf_counter() - t0, 4))
            auth = self.check_auth()
            t_auth = time.perf_counter() - t_auth_start
            self._emit(
                "auth_complete",
                phase="auth",
                elapsed=round(time.perf_counter() - t0, 4),
                elapsed_seconds=round(time.perf_counter() - t0, 4),
                duration=round(t_auth, 4),
                t_auth=round(t_auth, 4),
            )
            if not auth.authenticated:
                err_code = "auth_expired" if _is_auth_expired_error(auth.status, auth.message) else "AUTH"
                err_msg = AUTH_EXPIRED_MESSAGE if err_code == "auth_expired" else (auth.message or "NotebookLM profile is not authenticated")
                raise NotebookLMVideoError(err_code, err_msg)

            # 2. Notebook creation/resolution phase
            t_notebook_start = time.perf_counter()
            self._emit("notebook_setup_start", phase="notebook_setup", elapsed=round(time.perf_counter() - t0, 4), elapsed_seconds=round(time.perf_counter() - t0, 4))
            self._check_cancelled(request.job_id)
            if not notebook_id:
                created = self.create_notebook(request.title)
                notebook_id = created.notebook_id
                self.save_cached_notebook_id(notebook_id)
            else:
                self.save_cached_notebook_id(notebook_id)
            t_notebook = time.perf_counter() - t_notebook_start
            self._emit(
                "notebook_setup_complete",
                phase="notebook_setup",
                elapsed=round(time.perf_counter() - t0, 4),
                elapsed_seconds=round(time.perf_counter() - t0, 4),
                duration=round(t_notebook, 4),
                t_notebook=round(t_notebook, 4),
            )

            # 3. Source addition & indexing wait phase
            t_source_start = time.perf_counter()
            self._emit("source_ingest_start", phase="source_ingest", elapsed=round(time.perf_counter() - t0, 4), elapsed_seconds=round(time.perf_counter() - t0, 4))
            self._check_cancelled(request.job_id)
            source = self.add_source(
                notebook_id,
                source_file=request.source_file,
                source_url=request.source_url,
                source_text=request.source_text,
                title=request.title,
                source_id=request.source_id,
            )
            t_source = time.perf_counter() - t_source_start
            self._emit(
                "source_ingest_complete",
                phase="source_ingest",
                elapsed=round(time.perf_counter() - t0, 4),
                elapsed_seconds=round(time.perf_counter() - t0, 4),
                duration=round(t_source, 4),
                t_source=round(t_source, 4),
            )

            # 4. Cloud video synthesis phase
            t_cloud_start = time.perf_counter()
            self._emit("cloud_synthesis_start", phase="cloud_synthesis", elapsed=round(time.perf_counter() - t0, 4), elapsed_seconds=round(time.perf_counter() - t0, 4))
            self._check_cancelled(request.job_id)
            if not task_id:
                task_id, artifact_url = self.start_video(request, notebook_id, source.source_id)

            status, polled_url = self.wait_for_artifact(
                notebook_id, task_id, timeout_seconds=request.timeout_seconds, job_id=request.job_id
            )
            artifact_url = polled_url or artifact_url
            t_cloud = time.perf_counter() - t_cloud_start
            self._emit(
                "cloud_synthesis_complete",
                phase="cloud_synthesis",
                elapsed=round(time.perf_counter() - t0, 4),
                elapsed_seconds=round(time.perf_counter() - t0, 4),
                duration=round(t_cloud, 4),
                t_cloud=round(t_cloud, 4),
            )

            # 5. Download MP4 artifact phase
            t_download_start = time.perf_counter()
            self._emit("download_start", phase="download", elapsed=round(time.perf_counter() - t0, 4), elapsed_seconds=round(time.perf_counter() - t0, 4))
            self._check_cancelled(request.job_id)
            output = self.download_video(notebook_id, task_id, request.output_path)
            t_download = time.perf_counter() - t_download_start
            self._emit(
                "download_complete",
                phase="download",
                elapsed=round(time.perf_counter() - t0, 4),
                elapsed_seconds=round(time.perf_counter() - t0, 4),
                duration=round(t_download, 4),
                t_download=round(t_download, 4),
            )

            # 6. Technical ffprobe media inspection phase
            t_probe_start = time.perf_counter()
            self._emit("probe_start", phase="probe", elapsed=round(time.perf_counter() - t0, 4), elapsed_seconds=round(time.perf_counter() - t0, 4))
            media_info = probe_media_file(output)
            t_probe = time.perf_counter() - t_probe_start
            self._verify_duration(doc_profile, media_info.get("duration_seconds"), job_id=request.job_id)
            self._emit(
                "probe_complete",
                phase="probe",
                elapsed=round(time.perf_counter() - t0, 4),
                elapsed_seconds=round(time.perf_counter() - t0, 4),
                duration=round(t_probe, 4),
                t_probe=round(t_probe, 4),
            )

            # 7. Total elapsed duration
            t_total = time.perf_counter() - t0
            timings = _build_timings(
                t_auth=t_auth,
                t_notebook=t_notebook,
                t_source=t_source,
                t_cloud=t_cloud,
                t_download=t_download,
                t_probe=t_probe,
                t_total=t_total,
            )
            self._emit(
                "completed",
                phase="total",
                elapsed=round(t_total, 4),
                elapsed_seconds=round(t_total, 4),
                duration=round(t_total, 4),
                timings=timings,
            )

            artifact = VideoArtifact(
                **_model_kwargs(
                    VideoArtifact,
                    {
                        "notebook_id": notebook_id,
                        "task_id": task_id,
                        "artifact_id": task_id,
                        "status": status,
                        "output_path": str(output),
                        "artifact_url": artifact_url,
                        "format": request.format,
                        "style": None if request.format in {"cinematic", "short"} else request.style,
                        "profile": self.profile,
                        "duration_seconds": media_info.get("duration_seconds"),
                        "width": media_info.get("width"),
                        "height": media_info.get("height"),
                        "video_codec": media_info.get("video_codec"),
                        "audio_codec": media_info.get("audio_codec"),
                        "timings": timings,
                        "document_profile": doc_profile,
                        "fallback": False,
                        "target_duration_seconds": request_target_duration
                        if request_target_duration is not None
                        else (doc_profile.get("target_duration_seconds") if isinstance(doc_profile, Mapping) else None),
                    },
                )
            )

            prov_path = write_notebooklm_provenance(
                project_dir=Path(request.output_path).parent,
                request=request,
                artifact=artifact,
                source=source,
                started_at=started_at,
                timings=timings,
                document_profile=doc_profile,
            )
            return VideoArtifact(**{**artifact.__dict__, "provenance_path": str(prov_path)})

        except Exception as exc:
            t_total = time.perf_counter() - t0
            is_cancelled = (
                "cancelled" in str(exc).lower()
                or (self.process_manager and request.job_id and hasattr(self.process_manager, "is_cancelled") and self.process_manager.is_cancelled(request.job_id))
            )
            if is_cancelled:
                logger.info("NotebookLM video generation cancelled for %s; skipping fallback", request.job_id)
                self._emit("cancelled", phase="total", elapsed=round(t_total, 4), elapsed_seconds=round(t_total, 4))
                raise NotebookLMVideoError("cancelled", "Video generation cancelled") from exc

            err_timings = _build_timings(
                t_auth=t_auth,
                t_notebook=t_notebook,
                t_source=t_source,
                t_cloud=t_cloud,
                t_download=t_download,
                t_probe=t_probe,
                t_total=t_total,
            )
            err = exc if isinstance(exc, NotebookLMVideoError) else NotebookLMVideoError("PROVIDER_ERROR", str(exc))
            if _is_auth_expired_error(err.code, str(err)):
                err = NotebookLMVideoError("auth_expired", AUTH_EXPIRED_MESSAGE, payload=getattr(err, "payload", None))
            if _is_rate_limited_error(getattr(err, "code", None), str(err)):
                err = NotebookLMVideoError("rate_limited", RATE_LIMITED_MESSAGE, payload=getattr(err, "payload", None))

            # Fallback safety: auth, rate-limit, and validation errors surface
            # directly with clear messages. Only TIMEOUT/network/generation
            # errors may fall back to the local engine.
            if self.is_local_fallback_enabled(request) and _may_local_fallback(err):
                logger.warning(
                    "NotebookLM video generation encountered an issue (%s); executing automatic zero-failure fallback to local VideoFlowEngine motion graphics (Visual V2.1)",
                    err,
                )
                self._emit(
                    "fallback_local",
                    phase="fallback",
                    message="NotebookLM unavailable — automatically generating motion graphics with local engine",
                    error_code=err.code,
                )
                try:
                    from voice_flow.video_flow_engine.engine import VideoFlowEngine
                    local_engine = VideoFlowEngine(process_manager=self.process_manager)
                    source_txt = request.source_text
                    if not source_txt and request.source_file and Path(request.source_file).is_file():
                        try:
                            source_txt = Path(request.source_file).read_text(encoding="utf-8")
                        except Exception:
                            pass
                    if not source_txt:
                        source_txt = request.source_url or request.title or "Video Overview"

                    # Local fallback uses the ORIGINAL user prompt, never the
                    # injected NotebookLM prompt with cloud directives.
                    fallback_direction = original_prompt if "original_prompt" in locals() else request.prompt
                    local_res = local_engine.run(
                        video_id=request.job_id,
                        source_text=source_txt,
                        title=request.title,
                        visual_direction=fallback_direction,
                        output_path=str(request.output_path),
                        project_dir=Path(request.output_path).parent,
                        projects_root=Path(request.output_path).parent.parent,
                        format=request.format,
                        style=request.style,
                        style_prompt=request.style_prompt,
                        provider="visual-v2.1",
                        video_engine="visual-v2.1",
                    )
                    if local_res.get("state") in {"complete", "ready"}:
                        out_path = Path(local_res.get("video_path") or request.output_path)
                        if out_path.is_file() and not Path(request.output_path).is_file():
                            try:
                                import shutil
                                Path(request.output_path).parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(out_path, request.output_path)
                                out_path = Path(request.output_path)
                            except Exception:
                                pass
                        media_info = probe_media_file(out_path)
                        fallback_profile = doc_profile if "doc_profile" in locals() else None
                        self._verify_duration(fallback_profile, media_info.get("duration_seconds"), job_id=request.job_id)
                        fallback_timings = _build_timings(t_auth=t_auth, t_total=time.perf_counter() - t0)
                        artifact = VideoArtifact(
                            **_model_kwargs(
                                VideoArtifact,
                                {
                                    "notebook_id": "local-fallback",
                                    "task_id": "local-fallback",
                                    "artifact_id": "local-fallback",
                                    "status": "completed",
                                    "output_path": str(out_path),
                                    "format": request.format,
                                    "style": request.style,
                                    "profile": self.profile,
                                    "duration_seconds": media_info.get("duration_seconds"),
                                    "width": media_info.get("width"),
                                    "height": media_info.get("height"),
                                    "video_codec": media_info.get("video_codec"),
                                    "audio_codec": media_info.get("audio_codec"),
                                    "timings": fallback_timings,
                                    "document_profile": fallback_profile,
                                    "fallback": True,
                                    "provider": "local-fallback",
                                    "target_duration_seconds": request_target_duration
                                    if "request_target_duration" in locals() and request_target_duration is not None
                                    else (fallback_profile.get("target_duration_seconds") if isinstance(fallback_profile, Mapping) else None),
                                },
                            )
                        )
                        _mark_fallback_artifact(artifact)
                        prov_path = write_notebooklm_provenance(
                            project_dir=Path(request.output_path).parent,
                            request=request,
                            artifact=artifact,
                            source=source,
                            started_at=started_at,
                            timings=fallback_timings,
                            document_profile=doc_profile if "doc_profile" in locals() else None,
                        )
                        return _with_provenance(artifact, prov_path)
                except Exception as fb_exc:
                    logger.warning("Local fallback to VideoFlowEngine failed: %s", fb_exc)

            write_notebooklm_provenance(
                project_dir=Path(request.output_path).parent,
                request=request,
                artifact=None,
                source=source,
                started_at=started_at,
                error=err,
                timings=err_timings,
                document_profile=doc_profile if "doc_profile" in locals() else None,
            )
            self._emit(
                "failed",
                phase="total",
                elapsed=round(t_total, 4),
                elapsed_seconds=round(t_total, 4),
                timings=err_timings,
                code=err.code,
                message=str(err),
            )
            raise err
        finally:
            self._active_job_id = None

    def resume_and_download(
        self,
        *,
        notebook_id: str,
        task_id: str,
        output_path: Path,
        title: str = "Resumed NotebookLM video",
        format: str = "explainer",
        style: str | None = None,
        timeout_seconds: int = 1_800,
        job_id: str = "notebooklm-resume",
    ) -> VideoArtifact:
        """Resume polling an existing task and download when complete with timing telemetry."""
        t0 = time.perf_counter()
        t_auth_start = time.perf_counter()
        self.check_auth()
        t_auth = time.perf_counter() - t_auth_start
        self.save_cached_notebook_id(notebook_id)
        started_at = _now()

        t_cloud_start = time.perf_counter()
        status, artifact_url = self.wait_for_artifact(notebook_id, task_id, timeout_seconds=timeout_seconds, job_id=job_id)
        t_cloud = time.perf_counter() - t_cloud_start

        t_download_start = time.perf_counter()
        output = self.download_video(notebook_id, task_id, output_path)
        t_download = time.perf_counter() - t_download_start

        t_probe_start = time.perf_counter()
        media_info = probe_media_file(output)
        t_probe = time.perf_counter() - t_probe_start

        t_total = time.perf_counter() - t0
        timings = _build_timings(
            t_auth=t_auth,
            t_notebook=0.0,
            t_source=0.0,
            t_cloud=t_cloud,
            t_download=t_download,
            t_probe=t_probe,
            t_total=t_total,
        )

        artifact = VideoArtifact(
            notebook_id=notebook_id,
            task_id=task_id,
            artifact_id=task_id,
            status=status,
            output_path=str(output),
            artifact_url=artifact_url,
            format=format,
            style=style,
            profile=self.profile,
            duration_seconds=media_info.get("duration_seconds"),
            width=media_info.get("width"),
            height=media_info.get("height"),
            video_codec=media_info.get("video_codec"),
            audio_codec=media_info.get("audio_codec"),
            timings=timings,
        )
        request = VideoRequest(
            title=title,
            prompt="",
            output_path=Path(output_path),
            notebook_id=notebook_id,
            task_id=task_id,
            format=format,
            style=style or "auto",
            job_id=job_id,
            timeout_seconds=timeout_seconds,
            timings=timings,
        )
        prov_path = write_notebooklm_provenance(
            project_dir=Path(output_path).parent,
            request=request,
            artifact=artifact,
            source=None,
            started_at=started_at,
            timings=timings,
        )
        return VideoArtifact(**{**artifact.__dict__, "provenance_path": str(prov_path)})

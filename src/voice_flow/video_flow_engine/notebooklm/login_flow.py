"""NotebookLM sign-in orchestration for the Video Flow GUI.

What changed and why: the previous system launched OUR OWN Chrome with a CDP
debug port, attached a Playwright driver, and tried to scrape Google's
single-use ``oauth_token`` cookie ourselves. On this machine that design failed
in every way it can fail — Chrome singleton races killed the window mid-launch,
the debugged browser died with TargetClosedError storms, and Google refused to
issue the token inside a debugging-enabled browser (the user saw a stuck blue
page). Every attempt then silently fell back to the cookies-only plain login,
and cookies alone are rotated server-side within hours — which is exactly why
sign-in was needed over and over.

The default design has one moving part: the NotebookLM CLI's interactive
``login`` command. It owns the browser and stores its own profile session. A
Google browser session can still expire; periodic ``auth refresh --verify``
keeps it active while the app runs, but it must never be presented as permanent.

Subprocesses are spawned with console windows hidden; the sign-in window the
CLI opens is a visible GUI window by design.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Sequence

from .config import (
    get_profile_dir,
    resolve_notebooklm_cli,
    resolve_notebooklm_profile,
)

logger = logging.getLogger(__name__)

_LOGIN_TIMEOUT_SECONDS = 300
_ONLINE_CHECK_TIMEOUT_SECONDS = 75
_ONLINE_CACHE_SECONDS = 120.0
# The check right after a CLI sign-in starts a cold python.exe, imports the
# CLI, and makes a network round-trip; 15 s was not always enough on Windows.
_POST_LOGIN_VERIFY_TIMEOUT_SECONDS = 45.0
_POST_LOGIN_VERIFY_RETRY_DELAY_SECONDS = 2.0
_HIDE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
# Keep the real Popen class. Tests replace subprocess.Popen with a lambda, and
# isinstance() against that attribute then raises TypeError.
_REAL_POPEN = subprocess.Popen

# Reentrant: start_login's already-running branch reads state while holding
# the lock, and get_login_state() re-acquires it.
_STATE_LOCK = threading.RLock()
_STATE: dict[str, Any] = {
    "running": False,
    "mode": None,
    "started_at": None,
    "finished_at": None,
    "success": None,
    "error": None,
    "note": None,
    "durable": None,
    "log_path": None,
    "exit_code": None,
    "window_opened": None,
    "cancelled": False,
    "browser": None,
}
# Verdicts are scoped to the exact CLI profile.  A Google account switch must
# never inherit another profile's cached green status.
_ONLINE_CACHE: dict[str, dict[str, Any]] = {}
_SESSION_GENERATION: dict[str, int] = {}
_SELF_HEAL_LOCKS: dict[str, threading.Lock] = {}
_SELF_HEAL_RESULTS: dict[str, dict[str, Any]] = {}
_LOGIN_BROWSER_HANDOFF_SECONDS = 20.0
_LOGIN_MAX_CREDENTIAL_WATCH_SECONDS = 300.0
_LOGIN_WINDOW_POLL_SECONDS = 0.2
_LOGIN_CREDENTIAL_POLL_SECONDS = 0.5
# A pip console-script shim that dies in init_sys_streams does so well under a second.
# Anything still running after this opened a browser or is waiting on one.
_LOGIN_FAST_FAIL_SECONDS = 2.5
_LOGIN_OUTPUT_LIMIT = 32_000
_ACTIVE_LOGIN_PROCESS: subprocess.Popen | None = None
_ACTIVE_LOGIN_PROFILE: str | None = None
_LOGIN_CANCEL = threading.Event()
_RICH_TAG = re.compile(r"\[/?[a-zA-Z][a-zA-Z0-9 _#.=:,+-]*\]")
# The last CLI run's detail is kept per thread. A background refresh that
# finishes while an interactive login is running must not overwrite the login's
# exit code, cancel flag or output (it used to share one function attribute).
_LOGIN_DETAIL_LOCAL = threading.local()
# Non-interactive CLI runs (auth refresh) that are still in flight, by pid.
# A sign-in stops them first: a refresh that finishes after the new sign-in
# would rewrite storage_state.json with the old, broken session.
_BACKGROUND_CLI_LOCK = threading.Lock()
_BACKGROUND_CLI_PROCESSES: dict[int, tuple[str | None, Any]] = {}
# Profiles whose last sign-in ended without a usable session. The next click
# starts from a clean browser profile instead of reusing the same state.
_FRESH_NEXT: dict[str, str] = {}
# Old sessions moved aside by a fresh sign-in; keep only the newest few.
_STALE_SESSION_KEEP = 2
_STALE_SESSION_DIRNAME = "stale-sessions"
_MAC_QUARANTINE_DONE = False
# Where Playwright's "chrome"/"msedge" channels look on macOS, and the xattr tool.
_MAC_APPLICATIONS_DIR = Path("/Applications")
_MAC_XATTR = Path("/usr/bin/xattr")


def _cache_online_verification(profile: str, result: dict[str, Any], checked_at: float | None = None) -> None:
    _ONLINE_CACHE[profile] = {
        "checked_at": time.time() if checked_at is None else checked_at,
        "result": dict(result),
    }


def note_session_refreshed(profile: str | None = None) -> int:
    """Invalidate passive checks started before a login or refresh completed."""
    target = resolve_notebooklm_profile(profile)
    with _STATE_LOCK:
        generation = _SESSION_GENERATION.get(target, 0) + 1
        _SESSION_GENERATION[target] = generation
        _ONLINE_CACHE.pop(target, None)
        return generation


def get_session_generation(profile: str | None = None) -> int:
    """Return the profile generation used to fence stale auth operations."""
    target = resolve_notebooklm_profile(profile)
    with _STATE_LOCK:
        return _SESSION_GENERATION.get(target, 0)


def _master_token_json_path(profile: str | None = None) -> Path:
    """Durable aas_et/ master token record stored beside storage_state.json."""
    from .config import get_storage_state_path
    return get_storage_state_path(profile).with_name("master_token.json")


def master_token_present(profile: str | None = None) -> bool:
    """Return whether this profile has a stored CLI master-token record."""
    try:
        return _master_token_json_path(profile).is_file()
    except Exception:
        return False


def _self_heal_once(*, profile: str | None = None, timeout: int = 240) -> dict[str, Any]:
    """Run one bounded CLI refresh without interactive sign-in."""
    profile = resolve_notebooklm_profile(profile)
    operation_generation = get_session_generation(profile)
    deadline = time.monotonic() + min(110.0, max(8.0, float(timeout) + 65.0))
    try:
        from .config import is_profile_disconnected
        if is_profile_disconnected(profile):
            return {"ok": False, "error": "explicit_disconnected", "profile": profile,
                    "classification": "disconnected", "definitive": True}
    except Exception:
        pass
    cli_path = resolve_notebooklm_cli()
    if cli_path is None:
        return {"ok": False, "error": "cli_missing", "profile": profile,
                "classification": "transient_error", "definitive": False}
    command = [
        str(cli_path), "--profile", profile,
        "auth", "refresh", "--verify",
    ]
    if profile == "video-flow-experiment":
        command.append("--allow-headless")
    log_path = _login_log_path()
    try:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] [self-heal: refreshing the session without a window]\n"
            )
        code, err = _run_login_once(command, log_path, min(45, max(8, int(deadline - time.monotonic()))))
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200], "profile": profile,
                "classification": "transient_error", "definitive": False}
    recovery: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    if code != 0:
        # A failed refresh process is not itself proof that the saved account
        # expired. Classify with a passive check before changing auth state.
        remaining = deadline - time.monotonic()
        if remaining < 8.0:
            return {"ok": False, "error": "refresh_timeout", "profile": profile,
                    "classification": "transient_error", "definitive": False}
        with _STATE_LOCK:
            if _SESSION_GENERATION.get(profile, 0) != operation_generation:
                return {"ok": False, "error": "stale_operation", "profile": profile,
                        "classification": "transient_error", "definitive": False, "stale": True}
        verification = verify_online(profile=profile, force=True, timeout=min(15.0, remaining))
        if verification.get("authenticated") is True:
            code, err = 0, ""
        else:
            verification_error = str(
                verification.get("details_message") or verification.get("message") or ""
            ).strip()
            if verification_error:
                # Preserve the specific URL-redacted diagnosis instead of the
                # CLI's often-unhelpful exit code.
                err = verification_error[:300]
        if verification.get("authenticated") is not True and (
            (verification.get("definitive") and verification.get("failure_kind") == "auth")
            or verification.get("failure_kind") == "token_extraction"
        ):
            with _STATE_LOCK:
                if _SESSION_GENERATION.get(profile, 0) != operation_generation:
                    return {"ok": False, "error": "stale_operation", "profile": profile,
                            "classification": "transient_error", "definitive": False, "stale": True}
            expected_email = _storage_email(profile)
            if expected_email:
                try:
                    from .config import is_profile_disconnected
                    if is_profile_disconnected(profile):
                        return {"ok": False, "error": "explicit_disconnected", "profile": profile,
                                "classification": "disconnected", "definitive": True}
                    from .browser_sync import refresh_from_persistent_browser
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return {"ok": False, "error": "refresh_timeout", "profile": profile,
                                "classification": "transient_error", "definitive": False}
                    recovery = refresh_from_persistent_browser(
                        profile=profile, expected_email=expected_email,
                        timeout_seconds=max(0, min(35, int(remaining)))
                    )
                except Exception as exc:
                    recovery = {"success": False, "reason": "browser_recovery_failed", "error": str(exc)[:200]}
                if recovery.get("success"):
                    remaining = deadline - time.monotonic()
                    if remaining < 8.0:
                        return {"ok": False, "error": "refresh_timeout", "profile": profile,
                                "classification": "transient_error", "definitive": False}
                    verification = verify_online(
                        profile=profile, force=True,
                        timeout=min(15.0, remaining),
                    )
                    if verification.get("authenticated") is True:
                        code, err = 0, ""
                    else:
                        verification_error = str(
                            verification.get("details_message") or verification.get("message") or ""
                        ).strip()
                        if verification_error:
                            err = verification_error[:300]
    try:
        from .config import is_profile_disconnected
        if is_profile_disconnected(profile):
            return {"ok": False, "error": "explicit_disconnected", "profile": profile,
                    "classification": "disconnected", "definitive": True}
    except Exception:
        pass
    if code == 0:
        # A refresh may have changed server-side session state.  Do not retain
        # a stale negative verdict until the normal cache interval elapses.
        _STATE_LOCK.acquire()
        if _SESSION_GENERATION.get(profile, 0) != operation_generation:
            _STATE_LOCK.release()
            return {"ok": False, "error": "stale_operation", "profile": profile,
                    "classification": "transient_error", "definitive": False, "stale": True}
        operation_generation = note_session_refreshed(profile)
        try:
            from .config import (
                get_storage_backup_path,
                get_storage_state_path,
                has_nonempty_cookies,
                is_placeholder_email,
                is_pytest_real_home_path,
                mirror_storage_state_guarded,
            )
            st = get_storage_state_path(profile)
            b_st = get_storage_backup_path(profile)
            if is_pytest_real_home_path(st):
                logger.warning(
                    "self-heal: pytest isolation — skipping backup mirror and settings update for real-home path %s", st
                )
            elif st.is_file() and st.stat().st_size > 0:
                if not has_nonempty_cookies(st):
                    # Never mirror a 0-cookie state over the last known-good backup:
                    # an empty main file must not destroy the safety net. (This exact
                    # propagation is what emptied storage_state.backup.json and
                    # storage_state.safe_copy.json on the live profile.)
                    logger.warning(
                        "self-heal: %s holds 0 cookies after refresh; keeping existing backup/safe_copy untouched", st
                    )
                else:
                    st_text = st.read_text(encoding="utf-8")
                    mirror_storage_state_guarded(
                        st_text,
                        st,
                        [b_st, st.with_name("storage_state.safe_copy.json")],
                        source="login_flow.self_heal",
                    )
                    try:
                        data = json.loads(st_text)
                        email = (
                            (data.get("notebooklm") or {}).get("account", {}).get("email")
                            or (data.get("account") or {}).get("email")
                        )
                        if email and not is_placeholder_email(email):
                            _save_email(email)
                            from .config import _app_settings_storage
                            app_storage = _app_settings_storage()
                            app_storage.save_setting("video_flow_notebooklm_email", email)
                            app_storage.save_setting("video_flow_notebooklm_authenticated", True)
                            app_storage.save_setting("video_flow_notebooklm_auth_error", "")
                            app_storage.save_setting("video_flow_notebooklm_disconnected", False)
                    except Exception:
                        pass
            else:
                logger.warning(
                    "self-heal: %s missing or empty after refresh; keeping existing backup/safe_copy untouched", st
                )
        except Exception:
            pass
        finally:
            _STATE_LOCK.release()
    terminal_recovery_reasons = {"needs_signin", "email_mismatch", "missing_profile"}
    recovery_retryable = bool(recovery and not recovery.get("success") and (
        recovery.get("transient") is True or recovery.get("reason") not in terminal_recovery_reasons
    ))
    token_extraction_unresolved = bool(
        verification and verification.get("failure_kind") == "token_extraction"
    )
    classification = "authenticated" if code == 0 else (
        "sign_in_required"
        if verification and verification.get("definitive") and not recovery_retryable and not token_extraction_unresolved
        else "transient_error"
    )
    return {"ok": code == 0, "error": None if code == 0 else (err or f"exit {code}"),
            "profile": profile, "classification": classification, "verification": verification,
            "browser_recovery": recovery}


def self_heal(*, profile: str | None = None, timeout: int = 240) -> dict[str, Any]:
    """Coalesce all direct refresh callers onto one bounded per-profile attempt."""
    target = resolve_notebooklm_profile(profile)
    with _STATE_LOCK:
        lock = _SELF_HEAL_LOCKS.setdefault(target, threading.Lock())
    if not lock.acquire(blocking=False):
        if not lock.acquire(timeout=min(120.0, max(1.0, float(timeout)))):
            return {"ok": False, "profile": target, "classification": "transient_error",
                    "definitive": False, "error": "refresh_in_progress", "coalesced": True}
        try:
            with _STATE_LOCK:
                prior = dict(_SELF_HEAL_RESULTS.get(target) or {})
            if prior:
                prior["coalesced"] = True
                return prior
            return {"ok": False, "profile": target, "classification": "transient_error",
                    "definitive": False, "error": "refresh_result_unavailable", "coalesced": True}
        finally:
            lock.release()
    try:
        result = _self_heal_once(profile=target, timeout=timeout)
        with _STATE_LOCK:
            _SELF_HEAL_RESULTS[target] = dict(result)
        return result
    finally:
        lock.release()


def ensure_fresh_session(
    *,
    profile: str | None = None,
    force: bool = False,
    max_age_seconds: float = 86400.0,
) -> dict[str, Any]:
    """Ensure the profile's Google session cookies are valid and not nearing expiration.

    Inspects timestamped cookies (__Secure-1PSIDTS). If missing, expired, or nearing
    the 2-3 day Google expiration window, runs one bounded headless refresh check.
    """
    from .config import is_session_near_expiry
    target_prof = resolve_notebooklm_profile(profile)
    if not force and not is_session_near_expiry(target_prof, threshold_seconds=max_age_seconds):
        return {"ok": True, "refreshed": False, "profile": target_prof}

    heal_res = self_heal(profile=target_prof)
    heal_res["refreshed"] = bool(heal_res.get("ok"))
    return heal_res


def _set_note(note: str | None) -> None:
    with _STATE_LOCK:
        _STATE["note"] = note


def _login_log_path() -> Path:
    env_override = os.environ.get("VOICE_FLOW_LOGIN_LOG")
    if env_override:
        return Path(env_override)
    try:
        from voice_flow.paths import data_dir

        log_dir = data_dir() / "logs"
    except Exception:
        log_dir = Path(os.environ.get("VOICE_FLOW_DATA_DIR") or Path.home() / ".voice_flow") / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "notebooklm-login.log"


def _storage_email(*args, **kwargs) -> str | None:
    profile = args[0] if args else kwargs.get("profile")
    # The storage state belongs to this exact NotebookLM profile. Prefer its
    # persisted identity so a stale app-wide setting cannot redirect recovery
    # or account matching to another Google account.
    try:
        from .config import get_storage_state_path
        st_p = get_storage_state_path(profile)
        if st_p.is_file():
            st_data = json.loads(st_p.read_text(encoding="utf-8"))
            if isinstance(st_data, dict):
                notebooklm = st_data.get("notebooklm")
                notebooklm = notebooklm if isinstance(notebooklm, dict) else {}
                notebooklm_account = notebooklm.get("account")
                notebooklm_account = notebooklm_account if isinstance(notebooklm_account, dict) else {}
                account = st_data.get("account")
                account = account if isinstance(account, dict) else {}
                for value in (
                    notebooklm_account.get("email"),
                    account.get("email"),
                    st_data.get("email"),
                ):
                    email = str(value or "").strip()
                    if email and not _is_placeholder(email):
                        return email
    except Exception:
        pass

    try:
        from .config import _app_settings_storage

        email = str(_app_settings_storage().get_setting("video_flow_notebooklm_email") or "").strip()
        if email and not _is_placeholder(email):
            return email
    except Exception:
        pass

    return None


def _save_email(email: str) -> None:
    try:
        from .config import _app_settings_storage

        _app_settings_storage().save_setting("video_flow_notebooklm_email", email)
    except Exception:
        pass


def _is_placeholder(email: str | None) -> bool:
    """True for display placeholders ("your Google account") that must never be persisted."""
    try:
        from .config import is_placeholder_email

        return is_placeholder_email(email)
    except Exception:
        return str(email or "").strip().lower() in {"your google account"}


def is_token_extraction_error(message: object) -> bool:
    """Recognize known page-token extraction failures, not auth/network gates."""
    details_lower = str(message or "").casefold()
    if not details_lower:
        return False
    if any(word in details_lower for word in (
        "timeout", "timed out", "connection", "network", "socket", "unreachable",
        "getaddrinfo", "dns", "temporarily unavailable", "service unavailable",
    )):
        return False
    if any(phrase in details_lower for phrase in (
        "access denied", "access restricted", "not authorized", "permission denied",
        "not available for this account", "notebooklm is unavailable", "notebooklm is not available",
        "captcha", "forbidden", "http 403", "status code 403", "region blocked", "region restricted",
        "not available in this region", "not supported in this region", "not available in your country",
        "not supported in your country", "region is not supported",
        "automated requests", "automated traffic", "unusual traffic", "unusual activity",
        "verify you are human", "too many requests", "rate limit",
    )):
        return False
    return any(marker in details_lower for marker in (
        "csrf token not found", "session token not found", "session id not found",
        "session id is missing", "could not find session id", "wiz token not found", "wiz field not found",
        "missing wiz", "wiz not found", "snlm0e token not found", "snlm0e field not found",
        "missing snlm0e", "snlm0e not found", "token extraction failed", "failed to extract token",
        "failed to extract csrf", "failed to extract snlm0e", "failed to extract wiz",
        "token not found in html", "could not extract token from html",
    )) or bool(re.search(
        r"failed to extract\s+['\"]?(?:snlm0e|wiz|csrf|session(?:\s+(?:id|token))?)\b",
        details_lower,
    ))


def _profile_browser_dir(profile: str) -> Path:
    """The profile's persistent Playwright browser directory (the CLI's own
    sign-in browser profile). Holds the remembered Google accounts."""
    return get_profile_dir(profile) / "browser_profile"


def _is_sign_in_browser_process_name(name: str) -> bool:
    """True for the Chrome, Edge or Chromium processes the CLI can launch.

    Windows names end in ``.exe``. macOS names are "Google Chrome",
    "Google Chrome Helper (Renderer)", "Chromium", "Microsoft Edge"; Linux uses
    "chrome"/"chromium". The old Windows-only list meant a sign-in browser left
    over on a Mac was never found, so the next sign-in hit Chrome's profile lock.
    The exact ``--user-data-dir`` match is still what selects a process.
    """
    lowered = (name or "").casefold()
    if lowered in ("chrome.exe", "msedge.exe", "chromium.exe"):
        return True
    return any(part in lowered for part in ("chrome", "chromium", "msedge", "microsoft edge"))


def _matches_profile_user_data_dir(cmdline_norm: str, marker_norm: str, profile_name: str) -> bool:
    """True only for an exact ``--user-data-dir`` argument for this profile."""
    del profile_name  # Kept in the signature for existing callers.
    marker = marker_norm.rstrip("/")
    if not marker:
        return False
    # The boundary rejects lookalikes such as browser_profile_evil. psutil's
    # argv list is joined for compatibility with existing callers, so permit a
    # closing quote as well as whitespace/end after the exact path.
    return bool(re.search(
        r"(?:^|\s)--user-data-dir=[\"']?" + re.escape(marker) + r"(?=[\"']?(?:\s|$))",
        cmdline_norm,
    ))


def _profile_browser_pids(profile: str) -> set[int]:
    """Return only browser PIDs launched with this app profile's directory.

    This deliberately does not use a browser executable name alone: a user may
    have several personal Chrome windows open while a sign-in is running.
    """
    marker = str(_profile_browser_dir(profile)).replace("\\", "/").casefold()
    pids: set[int] = set()
    try:
        import psutil

        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if not _is_sign_in_browser_process_name(proc.info.get("name") or ""):
                    continue
                cmdline = proc.info.get("cmdline") or []
                if isinstance(cmdline, str):
                    cmdline = [cmdline]
                cmdline_norm = " ".join(cmdline).replace("\\", "/").casefold()
                if _matches_profile_user_data_dir(cmdline_norm, marker, profile):
                    pids.add(int(proc.info["pid"]))
            except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError, TypeError):
                continue
    except Exception:
        pass
    return pids


def _visible_top_level_windows() -> list[tuple[int, int, str, str]]:
    """List visible top-level HWNDs as (hwnd, pid, title, class), on Windows."""
    if os.name != "nt":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        windows: list[tuple[int, int, str, str]] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.IsWindowVisible.argtypes = (wintypes.HWND,)
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        user32.GetClassNameW.restype = ctypes.c_int
        user32.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
        user32.EnumWindows.restype = wintypes.BOOL

        def collect(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            title_buf = ctypes.create_unicode_buffer(512)
            class_buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title_buf, len(title_buf))
            user32.GetClassNameW(hwnd, class_buf, len(class_buf))
            windows.append((int(hwnd), int(pid.value), title_buf.value, class_buf.value))
            return True

        callback = callback_type(collect)
        user32.EnumWindows(callback, 0)
        return windows
    except Exception:
        return []


def _bring_hwnd_forward(hwnd: int) -> bool:
    """Best-effort Win32 foreground request; focus policy failures are harmless."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.ShowWindow.restype = ctypes.c_bool
        user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = ()
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
        user32.AttachThreadInput.restype = wintypes.BOOL
        user32.BringWindowToTop.argtypes = (wintypes.HWND,)
        user32.BringWindowToTop.restype = wintypes.BOOL
        kernel32.GetCurrentThreadId.argtypes = ()
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD

        target = wintypes.HWND(hwnd)
        user32.ShowWindow(target, 9)  # SW_RESTORE
        if user32.SetForegroundWindow(target):
            return True

        # Windows normally restricts focus stealing.  Temporarily attaching the
        # caller's and target's input queues is the documented, bounded fallback.
        foreground = user32.GetForegroundWindow()
        current_tid = kernel32.GetCurrentThreadId()
        target_tid = user32.GetWindowThreadProcessId(target, None)
        foreground_tid = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        attached_target = bool(target_tid and user32.AttachThreadInput(current_tid, target_tid, True))
        attached_foreground = bool(
            foreground_tid and foreground_tid != current_tid
            and user32.AttachThreadInput(current_tid, foreground_tid, True)
        )
        try:
            user32.BringWindowToTop(target)
            if user32.SetForegroundWindow(target):
                return True
        finally:
            if attached_foreground:
                user32.AttachThreadInput(current_tid, foreground_tid, False)
            if attached_target:
                user32.AttachThreadInput(current_tid, target_tid, False)
        # A flash asks for attention without moving focus when Windows declines.
        class FLASHWINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                       ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]
        user32.FlashWindowEx(ctypes.byref(FLASHWINFO(ctypes.sizeof(FLASHWINFO), target, 3, 1, 0)))
    except Exception:
        return False
    return False


def bring_login_window_forward(profile: str | None = None) -> bool:
    """Bring forward one visible window owned by this profile's login browser.

    This manual fallback intentionally does not target Windows Security dialogs:
    after the one-shot launch watcher ends they cannot be safely attributed to
    this sign-in. The automatic watcher handles only newly observed prompts.
    """
    profile = resolve_notebooklm_profile(profile)
    if not isinstance(profile, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", profile) or profile in {".", ".."}:
        return False
    owned_pids = _profile_browser_pids(profile)
    if sys.platform == "darwin":
        return _activate_mac_pids(owned_pids)
    for hwnd, pid, _title, _class_name in _visible_top_level_windows():
        if pid in owned_pids:
            return _bring_hwnd_forward(hwnd)
    return False


def _activate_mac_pids(pids: set[int]) -> bool:
    """Bring the sign-in Chrome to the front on macOS.

    Only the main browser process is a running application; helper processes
    return None and are skipped. Uses AppKit, which needs no Automation
    permission (osascript and System Events would prompt the user).
    """
    if sys.platform != "darwin" or not pids:
        return False
    try:
        from AppKit import NSRunningApplication  # type: ignore[import-not-found]
    except Exception:
        return False
    for pid in sorted(pids):
        try:
            app = NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
            if app is None:
                continue
            # NSApplicationActivateIgnoringOtherApps == 1 << 1
            if app.activateWithOptions_(1 << 1):
                return True
        except Exception:
            continue
    return False


def _handoff_login_window_mac(profile: str, stop_event: threading.Event | None) -> None:
    """macOS: activate the sign-in browser once when it appears (20 s window)."""
    deadline = time.monotonic() + _LOGIN_BROWSER_HANDOFF_SECONDS
    while time.monotonic() < deadline:
        if stop_event is not None and stop_event.is_set():
            return
        pids = _profile_browser_pids(profile)
        if pids:
            # Give Chrome a moment to create its first window before activating.
            time.sleep(0.5)
            _activate_mac_pids(_profile_browser_pids(profile) or pids)
            return
        if stop_event is not None:
            if stop_event.wait(_LOGIN_WINDOW_POLL_SECONDS):
                return
        else:
            time.sleep(_LOGIN_WINDOW_POLL_SECONDS)


def _is_windows_security_prompt(title: str, class_name: str) -> bool:
    text = f"{title} {class_name}".casefold()
    return "windows security" in text or "credential dialog" in text


def _handoff_login_windows(
    profile: str,
    _cli_pid: int | None,
    initial_hwnds: set[int] | None = None,
    stop_event: threading.Event | None = None,
    credential_watch_seconds: float = _LOGIN_MAX_CREDENTIAL_WATCH_SECONDS,
) -> None:
    """Give a new sign-in window one chance to reach the foreground.

    The browser gets one focus request during its short launch window. A newly
    appearing credential dialog is watched until its CLI ends, capped at five
    minutes, but focused once only.
    """
    # Capture before launching the CLI where possible: an immediately-created
    # Windows Security prompt must still count as new for this sign-in.
    if stop_event is not None and stop_event.is_set():
        return
    if initial_hwnds is None:
        initial_hwnds = {hwnd for hwnd, *_rest in _visible_top_level_windows()}
    browser_seen = False
    credential_seen = False
    browser_deadline = time.monotonic() + _LOGIN_BROWSER_HANDOFF_SECONDS
    credential_deadline: float | None = None
    while True:
        if stop_event is not None and stop_event.is_set():
            return
        now = time.monotonic()
        if not browser_seen and now >= browser_deadline:
            return
        if browser_seen and (credential_seen or (credential_deadline is not None and now >= credential_deadline)):
            return
        windows = _visible_top_level_windows()
        if not browser_seen:
            owned_pids = _profile_browser_pids(profile)
            for hwnd, pid, _title, _class_name in windows:
                if pid in owned_pids:
                    _bring_hwnd_forward(hwnd)
                    browser_seen = True
                    credential_deadline = now + max(0.0, credential_watch_seconds)
                    break
        # Windows Security runs outside Chrome.  Restrict this to a dialog that
        # appeared after this sign-in began, and only after our browser was found.
        if browser_seen and not credential_seen:
            for hwnd, _pid, title, class_name in windows:
                if hwnd not in initial_hwnds and _is_windows_security_prompt(title, class_name):
                    _bring_hwnd_forward(hwnd)
                    credential_seen = True
                    break
        poll_seconds = _LOGIN_CREDENTIAL_POLL_SECONDS if browser_seen else _LOGIN_WINDOW_POLL_SECONDS
        if stop_event is not None:
            if stop_event.wait(poll_seconds):
                return
        else:
            time.sleep(poll_seconds)


def _start_login_foreground_handoff(
    command: list[str],
    cli_pid: int | None,
    initial_hwnds: set[int] | None = None,
    stop_event: threading.Event | None = None,
    credential_watch_seconds: float = _LOGIN_MAX_CREDENTIAL_WATCH_SECONDS,
) -> None:
    """Start the non-blocking, one-shot foreground handoff for interactive login."""
    try:
        login_index = command.index("login")
        profile_index = command.index("--profile")
        profile = command[profile_index + 1]
        if login_index < 0 or not profile:
            return
    except (ValueError, IndexError):
        return
    if sys.platform == "darwin":
        threading.Thread(
            target=_handoff_login_window_mac,
            args=(profile, stop_event),
            name="notebooklm-login-window-handoff",
            daemon=True,
        ).start()
        return
    threading.Thread(
        target=_handoff_login_windows,
        args=(profile, cli_pid, initial_hwnds, stop_event, credential_watch_seconds),
        name="notebooklm-login-window-handoff",
        daemon=True,
    ).start()


def _remove_browser_lock_files(browser_dir: Path) -> None:
    """Delete Chrome's profile lock files, including dangling symlinks.

    On macOS and Linux ``SingletonLock`` is a symlink to "<host>-<pid>" that
    normally dangles. ``Path.exists()`` follows the link and returns False, so
    the old check never removed it. When the Mac's host name had changed since
    the lock was written, Chrome refused the profile ("in use on another
    computer") and the sign-in window never opened.
    """
    for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"):
        lock_p = browser_dir / lock_name
        try:
            if os.path.lexists(lock_p):
                lock_p.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass


def _terminate_stale_login_processes(profile: str, log_path: Path | str | None = None) -> int:
    """Kill leftover browsers from a previous sign-in still holding the
    profile's browser directory — a wedged SingletonLock would block every
    future sign-in window. Only processes whose command line carries OUR
    browser_profile path are touched; the user's daily browser is never
    matched."""
    killed = 0
    raw_marker = str(_profile_browser_dir(profile))
    marker = raw_marker.replace("\\", "/").casefold()
    # psutil retrieves command lines directly.  The prior PowerShell/CIM pass
    # added a costly second full process scan before this exact-profile scan.
    try:
        import psutil
        my_pid = os.getpid()
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.info["pid"] == my_pid:
                    continue
                if _is_sign_in_browser_process_name(proc.info.get("name") or ""):
                    cmdline = proc.info.get("cmdline") or []
                    if isinstance(cmdline, str):
                        cmdline = [cmdline]
                    cmdline_norm = " ".join(cmdline).replace("\\", "/").casefold()
                    if _matches_profile_user_data_dir(cmdline_norm, marker, profile):
                        proc.kill()
                        killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass

    # Clean up lock files from browser profile
    try:
        _remove_browser_lock_files(_profile_browser_dir(profile))
    except Exception:
        pass

    if killed and log_path is not None:
        try:
            p = Path(log_path)
            with p.open("a", encoding="utf-8") as handle:
                handle.write(f"[cleared {killed} leftover sign-in browser process(es)]\n")
        except Exception:
            pass
    return killed


def _clean_account_state_for_switch(profile: str) -> None:
    """Completely wipe old account credentials, tokens, safe copies, and caches on switch.

    Audit note: this function is destructive by design and is reachable ONLY via
    ``start_login(..., switch_account=True)`` (the explicit "switch account" API
    call from the UI). Startup paths (check_auth / sync_storage_state /
    auto_sync_from_browser / keepalive / self_heal) never call it. Under pytest
    the destructive file operations are additionally skipped when the resolved
    profile resolves inside the real ~/.notebooklm so test runs can never wipe
    the user's live session.
    """
    logger.info("Explicit account switch requested — wiping stored NotebookLM credentials for profile %s", profile)
    note_session_refreshed(profile)
    try:
        from .keepalive import reset_session_refresh_state
        reset_session_refresh_state(profile)
    except Exception:
        pass
    # Terminate any lingering browser processes first so file locks on browser_profile are released
    try:
        _terminate_stale_login_processes(profile)
        time.sleep(0.3)
    except Exception:
        pass

    old_email = None
    try:
        from voice_flow.storage import storage
        old_email = storage.get_setting("video_flow_notebooklm_email")
    except Exception:
        pass
    if not old_email:
        try:
            from voice_flow.gui import api_server
            old_email = api_server.storage.get_setting("video_flow_notebooklm_email")
        except Exception:
            pass
    if not old_email:
        try:
            from .config import get_storage_state_path
            st_check = get_storage_state_path(profile)
            if st_check.is_file():
                d = json.loads(st_check.read_text(encoding="utf-8"))
                old_email = (d.get("notebooklm") or {}).get("account", {}).get("email") or (d.get("account") or {}).get("email")
        except Exception:
            pass
    if old_email:
        try:
            from voice_flow.storage import storage
            storage.save_setting("video_flow_notebooklm_switched_from", str(old_email).strip().lower())
        except Exception:
            pass
        try:
            from voice_flow.gui import api_server
            api_server.storage.save_setting("video_flow_notebooklm_switched_from", str(old_email).strip().lower())
        except Exception:
            pass

    try:
        from .config import get_storage_backup_path, get_storage_state_path, is_pytest_real_home_path
        st_path = get_storage_state_path(profile)
        b_path = get_storage_backup_path(profile)
        safe_path = st_path.with_name("storage_state.safe_copy.json")
        mt_file = _master_token_json_path(profile)

        if is_pytest_real_home_path(st_path):
            logger.warning(
                "Account-switch wipe: pytest isolation — skipping credential deletion for real-home path %s", st_path
            )
        else:
            if st_path.is_file():
                try:
                    st_data = json.loads(st_path.read_text(encoding="utf-8"))
                    if isinstance(st_data, dict):
                        st_data["cookies"] = []
                        if "notebooklm" in st_data and isinstance(st_data["notebooklm"], dict):
                            st_data["notebooklm"].pop("account", None)
                        st_data.pop("account", None)
                        st_path.write_text(json.dumps(st_data, indent=2), encoding="utf-8")
                except Exception:
                    pass

            if b_path.is_file():
                b_path.unlink(missing_ok=True)
            if safe_path.is_file():
                safe_path.unlink(missing_ok=True)
            if mt_file.is_file():
                mt_file.unlink(missing_ok=True)
    except Exception:
        pass

    try:
        from .config import is_pytest_real_home_path
        b_dir = _profile_browser_dir(profile)
        if b_dir.is_dir() and not is_pytest_real_home_path(b_dir):
            for _ in range(3):
                shutil.rmtree(b_dir, ignore_errors=True)
                if not b_dir.exists():
                    break
                time.sleep(0.1)
    except Exception:
        pass

    with _STATE_LOCK:
        _ONLINE_CACHE.clear()

    try:
        from voice_flow.video_flow_engine.notebooklm.provider import _WORKSPACE_NOTEBOOK_CACHE
        _WORKSPACE_NOTEBOOK_CACHE.clear()
    except Exception:
        pass

    try:
        from voice_flow.storage import storage
        storage.save_setting("video_flow_notebooklm_authenticated", False)
        storage.save_setting("video_flow_notebooklm_email", "")
    except Exception:
        pass
    try:
        from voice_flow.gui import api_server
        api_server.storage.save_setting("video_flow_notebooklm_authenticated", False)
        api_server.storage.save_setting("video_flow_notebooklm_email", "")
    except Exception:
        pass


def _prepare_browser_profile(profile: str, switch_account: bool = False) -> None:
    """Ensure the browser profile directory exists and is prepared so Chrome
    starts directly into the sign-in flow without first-run or profile-picker prompts."""
    browser_dir = _profile_browser_dir(profile)

    if switch_account:
        from .config import is_pytest_real_home_path
        if browser_dir.is_dir() and not is_pytest_real_home_path(browser_dir):
            try:
                shutil.rmtree(browser_dir, ignore_errors=True)
            except Exception:
                pass

    browser_dir.mkdir(parents=True, exist_ok=True)

    # 1. First Run sentinel file: prevents Chrome from showing "Welcome to Chrome" / first-run dialogs
    first_run = browser_dir / "First Run"
    try:
        first_run.touch(exist_ok=True)
    except Exception:
        pass

    # 2. Clean up stale lock files if no browser process is running
    _remove_browser_lock_files(browser_dir)

    # 3. Ensure Local State disables welcome page & profile picker on startup
    local_state_path = browser_dir / "Local State"
    try:
        data = {}
        if local_state_path.is_file() and local_state_path.stat().st_size > 0:
            try:
                data = json.loads(local_state_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        if not isinstance(data, dict):
            data = {}
        browser_dict = data.setdefault("browser", {})
        if isinstance(browser_dict, dict):
            browser_dict["has_seen_welcome_page"] = True
            browser_dict["should_reset_check_default_browser"] = False
            browser_dict["check_default_browser"] = False
        profile_dict = data.setdefault("profile", {})
        if isinstance(profile_dict, dict):
            profile_dict["picker_shown_on_startup"] = False
            info_cache = profile_dict.setdefault("info_cache", {})
            if isinstance(info_cache, dict) and "Default" not in info_cache:
                info_cache["Default"] = {
                    "is_using_default_name": True,
                    "name": "Person 1",
                }
            profile_dict["last_active_profiles"] = ["Default"]
            profile_dict["profiles_order"] = ["Default"]
        local_state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass

    # 4. Ensure Default/Preferences disables welcome page
    default_prefs_path = browser_dir / "Default" / "Preferences"
    try:
        default_prefs_path.parent.mkdir(parents=True, exist_ok=True)
        prefs = {}
        if default_prefs_path.is_file() and default_prefs_path.stat().st_size > 0:
            try:
                prefs = json.loads(default_prefs_path.read_text(encoding="utf-8"))
            except Exception:
                prefs = {}
        if not isinstance(prefs, dict):
            prefs = {}
        prefs.setdefault("browser", {})["has_seen_welcome_page"] = True
        prefs.setdefault("browser", {})["check_default_browser"] = False
        prefs.setdefault("profile", {})["exit_type"] = "Normal"
        prefs.setdefault("signin", {})["allowed"] = True
        default_prefs_path.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    except Exception:
        pass


def _saved_session_kind(profile: str) -> str:
    """Classify what a sign-in click starts from, without running the CLI.

    ``"none"``: no storage_state.json with cookies and no master token. A new
    user, or a profile left behind by an attempt that never saved a session.
    ``"broken"``: a saved session that the last check called definitely signed
    out (Google said so, or the keepalive reached ``sign_in_required``).
    ``"saved"``: a saved session whose state is fine or unknown.
    """
    try:
        from .config import get_storage_state_path, has_nonempty_cookies
        storage = get_storage_state_path(profile)
        has_cookies = bool(storage.is_file() and has_nonempty_cookies(storage))
    except Exception:
        has_cookies = False
    if not has_cookies and not master_token_present(profile):
        return "none"
    with _STATE_LOCK:
        cached = dict((_ONLINE_CACHE.get(profile) or {}).get("result") or {})
    if cached.get("authenticated") is False and cached.get("definitive") is True \
            and cached.get("failure_kind") == "auth":
        return "broken"
    try:
        from .keepalive import get_session_refresh_state
        if str((get_session_refresh_state(profile) or {}).get("state") or "") == "sign_in_required":
            return "broken"
    except Exception:
        pass
    return "saved"


def _backup_stale_session(profile: str, log_path: Path | str | None = None, *, reason: str) -> Path | None:
    """Move an old session aside so the next sign-in starts clean.

    Moves storage_state.json (plus its backup and safe copy) and the CLI's
    browser_profile into ``<profile>/stale-sessions/<time>/``. Nothing is
    deleted except backups older than the newest few. The master token is
    left alone. Returns the backup folder, or None when there was nothing to move.
    """
    try:
        from .config import is_pytest_real_home_path
    except Exception:  # pragma: no cover - config always importable
        def is_pytest_real_home_path(_p):  # type: ignore[misc]
            return False
    profile_dir = get_profile_dir(profile)
    if is_pytest_real_home_path(profile_dir):
        logger.warning("fresh sign-in: pytest isolation - not moving real-home profile %s", profile_dir)
        return None
    stale_root = profile_dir / _STALE_SESSION_DIRNAME
    target = stale_root / time.strftime("%Y%m%d-%H%M%S")
    suffix = 1
    while target.exists():
        suffix += 1
        target = stale_root / f"{time.strftime('%Y%m%d-%H%M%S')}-{suffix}"
    moved: list[str] = []
    candidates = [
        profile_dir / "storage_state.json",
        profile_dir / "storage_state.backup.json",
        profile_dir / "storage_state.safe_copy.json",
        _profile_browser_dir(profile),
    ]
    for source in candidates:
        try:
            if not os.path.lexists(source):
                continue
            target.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(source, target / source.name)
            except OSError:
                # Windows refuses to rename a folder a process still holds open.
                if source.is_dir():
                    shutil.copytree(source, target / source.name, dirs_exist_ok=True,
                                    ignore=shutil.ignore_patterns("Singleton*", "lockfile", "*.lock"))
                    shutil.rmtree(source, ignore_errors=True)
                else:
                    shutil.copy2(source, target / source.name)
                    source.unlink(missing_ok=True)
            moved.append(source.name)
        except Exception as exc:
            logger.warning("fresh sign-in: could not move %s aside: %s", source, exc)
    try:
        if stale_root.is_dir():
            old = sorted((d for d in stale_root.iterdir() if d.is_dir()), key=lambda d: d.name)
            for extra in old[:-_STALE_SESSION_KEEP]:
                shutil.rmtree(extra, ignore_errors=True)
    except Exception:
        pass
    with _STATE_LOCK:
        _ONLINE_CACHE.pop(profile, None)
    try:
        from .keepalive import reset_session_refresh_state
        reset_session_refresh_state(profile)
    except Exception:
        pass
    if log_path is not None:
        try:
            with Path(log_path).open("a", encoding="utf-8") as handle:
                handle.write(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [fresh] reason={reason} "
                    f"moved={','.join(moved) or 'nothing'} to={target if moved else '-'}\n"
                )
        except Exception:
            pass
    logger.info("NotebookLM fresh sign-in (%s): moved %s aside", reason, moved or "nothing")
    return target if moved else None


def _mac_clear_runtime_quarantine(cli_path: Path | None, log_path: Path | str | None = None) -> None:
    """Remove macOS quarantine from the bundled runtime the CLI runs on.

    The app runs Python in-process (the native launcher dlopens libpython),
    so ``runtime/python/bin/python3`` and Playwright's ``node`` driver are first
    exec'd by sign-in. Files copied out of a downloaded zip or dmg keep
    ``com.apple.quarantine``, and Gatekeeper can refuse to run them. Best
    effort, once per app run; failures are logged and ignored.
    """
    global _MAC_QUARANTINE_DONE
    if sys.platform != "darwin" or _MAC_QUARANTINE_DONE or cli_path is None:
        return
    _MAC_QUARANTINE_DONE = True
    xattr = _MAC_XATTR
    if not xattr.is_file():
        return
    runtime = cli_path.parent.parent if cli_path.parent.name == "bin" else None
    if runtime is None or not runtime.is_dir():
        return
    try:
        probe = subprocess.run(
            [str(xattr), "-p", "com.apple.quarantine", str(cli_path)],
            capture_output=True, text=True, timeout=5,
        )
        interpreter = cli_path.parent / "python3"
        if probe.returncode != 0 and interpreter.is_file():
            probe = subprocess.run(
                [str(xattr), "-p", "com.apple.quarantine", str(interpreter)],
                capture_output=True, text=True, timeout=5,
            )
        if probe.returncode != 0:
            line = "[mac] runtime has no quarantine flag"
        else:
            result = subprocess.run(
                [str(xattr), "-dr", "com.apple.quarantine", str(runtime)],
                capture_output=True, text=True, timeout=60,
            )
            line = f"[mac] cleared quarantine on {runtime}: rc={result.returncode} {(result.stderr or '').strip()[:200]}"
    except Exception as exc:
        line = f"[mac] quarantine check failed: {exc}"
    if log_path is not None:
        try:
            with Path(log_path).open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:
            pass


def _log_login_environment(log_path: Path | str, *, profile: str, cli_path: Path | None, browser: str,
                           fresh_login: bool, fresh_reason: str | None) -> None:
    """One line per sign-in that says which CLI, browser and profile were used."""
    try:
        argv = _cli_argv([str(cli_path)]) if cli_path is not None else []
        with Path(log_path).open("a", encoding="utf-8") as handle:
            handle.write(
                f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] [env] platform={sys.platform} profile={profile} "
                f"browser={browser} fresh={fresh_login} reason={fresh_reason or '-'} "
                f"cli={cli_path} interpreter={argv[0] if len(argv) >= 3 else '-'} "
                f"browser_profile={_profile_browser_dir(profile)}\n"
            )
    except Exception:
        pass


def _console_interpreter_for_cli(cli_path: Path) -> Path | None:
    """Return the console Python beside a pip script shim, never pythonw.

    Installed layout is ``runtime/python/Scripts/notebooklm.exe`` next to
    ``runtime/python/python.exe``. A venv on macOS uses ``bin/notebooklm``
    next to ``bin/python3``.
    """
    parent = cli_path.parent
    candidates: list[Path] = []
    if parent.name.lower() == "scripts":
        runtime = parent.parent
        candidates.extend((runtime / "python.exe", runtime / "python"))
    elif parent.name == "bin":
        candidates.extend((parent / "python3", parent / "python", parent / "python.exe"))
    for candidate in candidates:
        try:
            if candidate.is_file() and "pythonw" not in candidate.name.lower():
                return candidate
        except OSError:
            continue
    return None


def _cli_argv(command: list[str]) -> list[str]:
    """Launch ``python -m notebooklm`` instead of the console-script shim.

    ``notebooklm.exe`` is a console-subsystem pip launcher. From pythonw
    (no console) plus CREATE_NO_WINDOW, Windows does not allocate a console
    and the shim starts its Python child without the redirected std handles.
    That child aborts in ``init_sys_streams`` in well under a second, so no
    browser window appears and stdout/stderr never reach the log. The same
    command stays alive from PowerShell because that parent has a console.
    Invoking python.exe directly with real pipes avoids the shim.
    """
    if not command:
        return list(command)
    cli = Path(command[0])
    if cli.name.lower() not in {"notebooklm", "notebooklm.exe"}:
        return list(command)
    interpreter = _console_interpreter_for_cli(cli)
    if interpreter is None:
        return list(command)
    return [str(interpreter), "-m", "notebooklm", *command[1:]]


def cli_child_argv_env(command: Sequence[str]) -> tuple[list[str], dict[str, str]]:
    """argv + env for any non-login NotebookLM CLI call (generate, poll, download...).

    Same reason as :func:`_cli_argv`: from the installed (pythonw) app the pip
    ``notebooklm.exe`` shim dies before printing anything, so Audio Flow and
    Video Flow showed a bare "NotebookLM CLI failed". Run ``python -m
    notebooklm`` with a UTF-8 child environment instead.
    """
    argv = _cli_argv([str(part) for part in command])
    interpreter = Path(argv[0]) if len(argv) >= 3 and argv[1] == "-m" else None
    try:
        usable = interpreter if interpreter is not None and interpreter.is_file() else None
    except OSError:
        usable = None
    return argv, _login_child_env(usable)


_FIRST_LOGIN_SHIM = Path(__file__).with_name("first_login_shim.py")


def _with_first_login_guard(argv: list[str]) -> list[str]:
    """Run a browser ``login`` through :mod:`first_login_shim` when possible.

    notebooklm-py 0.8.2 treats the signed-out NotebookLM landing page (HTTP
    200 on notebook.google.com) as "Already logged in" and saves a session
    with no ``SID``. The shim backports the 0.8.5 fix: steer to Google
    sign-in and wait for ``SID``. Only the plain browser login is wrapped;
    ``--master-token`` / ``--browser-cookies`` and every other command keep
    ``python -m notebooklm``. ``VOICE_FLOW_NBLM_LOGIN_GUARD=0`` turns it off.
    """
    if os.environ.get("VOICE_FLOW_NBLM_LOGIN_GUARD", "1").strip().lower() in ("0", "false", "no", "off"):
        return list(argv)
    if len(argv) < 4 or argv[1] != "-m" or argv[2] != "notebooklm":
        return list(argv)
    rest = list(argv[3:])
    if "login" not in rest or any(flag in rest for flag in ("--master-token", "--browser-cookies")):
        return list(argv)
    try:
        if not _FIRST_LOGIN_SHIM.is_file():
            return list(argv)
    except OSError:
        return list(argv)
    return [argv[0], str(_FIRST_LOGIN_SHIM), *rest]


def _session_cookie_names(profile: str) -> list[str]:
    """Names (never values) of the Google auth cookies in the saved session."""
    wanted = ("SID", "__Secure-1PSID", "__Secure-1PSIDTS", "__Secure-3PSID", "__Secure-3PSIDTS",
              "HSID", "SSID", "APISID", "SAPISID", "OSID", "__Secure-OSID", "LSID")
    try:
        from .config import get_storage_state_path
        st = get_storage_state_path(profile)
        data = json.loads(st.read_text(encoding="utf-8")) if st.is_file() else {}
        cookies = data.get("cookies") if isinstance(data, dict) else None
        present = {
            str(c.get("name")) for c in (cookies or [])
            if isinstance(c, dict) and c.get("name") and c.get("value")
        }
    except Exception:
        return []
    return [name for name in wanted if name in present]


def _log_login_line(message: str) -> None:
    """Append one ``[nblm-login]`` line to the sign-in log and the app log."""
    logger.info("[nblm-login] %s", message)
    try:
        with _login_log_path().open("a", encoding="utf-8") as handle:
            handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [nblm-login] {message}\n")
    except Exception:
        pass


def _default_playwright_browsers_dir() -> Path | None:
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        return Path(local) / "ms-playwright" if local else None
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def _login_child_env(interpreter: Path | None = None) -> dict[str, str]:
    """Environment for the CLI child. Never point ``__PYVENV_LAUNCHER__`` at pythonw."""
    env = {key: value for key, value in os.environ.items() if isinstance(value, str)}
    launcher = env.get("__PYVENV_LAUNCHER__", "")
    if launcher.lower().endswith(("pythonw.exe", "pythonw")):
        if interpreter is not None:
            env["__PYVENV_LAUNCHER__"] = str(interpreter)
        else:
            env.pop("__PYVENV_LAUNCHER__", None)
    if interpreter is not None:
        runtime = interpreter.parent
        prefix = [str(runtime)]
        for extra in (runtime / "Scripts", runtime / "bin"):
            if extra.is_dir():
                prefix.append(str(extra))
        current = env.get("PATH", "")
        env["PATH"] = os.pathsep.join(prefix + ([current] if current else []))
    # The CLI prints JSON with ensure_ascii=False. Without this a Windows child
    # writes to the pipe in the ANSI code page and can fail on non-ASCII text.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    if not env.get("PLAYWRIGHT_BROWSERS_PATH"):
        browsers = _default_playwright_browsers_dir()
        try:
            if browsers is not None and browsers.is_dir():
                env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)
        except OSError:
            pass
    return env


def _spawn_cwd() -> str:
    try:
        cwd = Path.cwd()
        if cwd.is_dir():
            return str(cwd)
    except Exception:
        pass
    return str(Path.home())


def _login_spawn_kwargs(*, show_browser: bool = True) -> dict[str, Any]:
    """Popen kwargs that keep a console interpreter alive and the browser visible.

    Stdio is fully redirected, so python.exe does not need its own console.
    STARTF_USESHOWWINDOW hides that console. CREATE_NO_WINDOW is used only for
    headless refresh: on an interactive login it can keep Playwright's browser
    window from appearing, and combined with the pip shim it kills the child
    before Chrome starts.
    """
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "cwd": _spawn_cwd(),
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = startupinfo
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if not show_browser:
            flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    return kwargs


def spawn_notebooklm_process(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    interactive: bool | None = None,
) -> subprocess.Popen:
    """Spawn the NotebookLM CLI the way the installed app must.

    A pythonw parent has no console. The returned process is the console
    interpreter (when the shim sits beside one) with live stdout and stderr
    pipes, so a login waits out ``--browser-timeout`` instead of exiting
    immediately.
    """
    argv = _cli_argv(list(command))
    if interactive is None:
        interactive = "login" in command
    argv = _with_first_login_guard(argv)
    interpreter: Path | None = None
    if len(argv) >= 3 and argv[1] == "-m" and argv[2] == "notebooklm":
        candidate = Path(argv[0])
        if candidate.is_file():
            interpreter = candidate
    child_env = _login_child_env(interpreter)
    if env:
        child_env.update(env)
    return subprocess.Popen(argv, env=child_env, **_login_spawn_kwargs(show_browser=interactive))


def _browser_installed(browser: str) -> bool:
    """True when a system Chrome or Edge the CLI can drive is installed."""
    kind = (browser or "").strip().lower()
    if kind == "chrome":
        relative = Path("Google") / "Chrome" / "Application" / "chrome.exe"
        app_names = ("Google Chrome.app",)
        which_names = ("google-chrome", "google-chrome-stable", "chrome")
    elif kind == "msedge":
        relative = Path("Microsoft") / "Edge" / "Application" / "msedge.exe"
        app_names = ("Microsoft Edge.app",)
        which_names = ("microsoft-edge", "microsoft-edge-stable", "msedge")
    else:
        return False
    if os.name == "nt":
        roots: list[Path] = []
        for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            value = os.environ.get(key, "")
            if value:
                roots.append(Path(value))
        for root in roots:
            try:
                if (root / relative).is_file():
                    return True
            except OSError:
                continue
    if sys.platform == "darwin":
        # Playwright's "chrome"/"msedge" channels launch exactly
        # /Applications/<App>.app on macOS. A copy in ~/Applications is not
        # found by Playwright, so counting it sent the CLI to a browser it then
        # failed to start ("Chromium distribution 'chrome' is not found").
        for app_name in app_names:
            try:
                if (_MAC_APPLICATIONS_DIR / app_name).exists():
                    return True
            except OSError:
                continue
        return False
    for name in which_names:
        if shutil.which(name):
            return True
    return False


def resolve_interactive_browser(preferred: str | None = None) -> str:
    """Prefer system Chrome, then Edge, then Playwright's bundled Chromium.

    On macOS the fallback after Chrome is the bundled Chromium. It is the
    Safari-compatible browser the CLI can drive; Edge is not required there.
    The profile is the CLI's dedicated directory, not the user's daily Chrome
    profile (Chrome 127+ app-bound cookies cannot be imported).
    """
    requested = (preferred or "chrome").strip().lower() or "chrome"
    if requested == "chromium":
        return "chromium"
    if requested in {"chrome", "msedge"} and _browser_installed(requested):
        return requested
    if _browser_installed("chrome"):
        return "chrome"
    if sys.platform != "darwin" and _browser_installed("msedge"):
        return "msedge"
    return "chromium"


def _clean_cli_output(text: str) -> str:
    cleaned = _RICH_TAG.sub("", text or "")
    cleaned = re.sub(r"https?://\S+", "<redacted URL>", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:500]


def _infer_window_opened(elapsed: float, output: str) -> bool:
    lowered = output.lower()
    if "waiting for login" in lowered:
        return True
    if any(marker in lowered for marker in (
        "executable doesn't exist",
        "failed to launch",
        "spawn unknown",
        "init_sys_streams",
        "traceback (most recent call last)",
        "no such file",
        "not found",
    )):
        return False
    return elapsed >= _LOGIN_FAST_FAIL_SECONDS


def _login_failure_message(code: int, output: str, elapsed: float, *, cancelled: bool, interactive: bool) -> tuple[str, bool | None]:
    if cancelled:
        return "Sign-in cancelled.", None
    cleaned = _clean_cli_output(output)
    if not interactive:
        if code == 0:
            return "", None
        return (cleaned or f"exit {code}"), None
    window_opened = _infer_window_opened(elapsed, cleaned)
    if code == 0:
        return "", True
    if not window_opened:
        if cleaned:
            return f"The Google sign-in window did not open (exit {code}): {cleaned}", False
        return (
            "The Google sign-in window did not open. "
            f"The sign-in program exited immediately with code {code}.",
            False,
        )
    if cleaned:
        return cleaned, True
    return (
        "Google sign-in did not finish. Choose your Google account in the browser window, then try again.",
        True,
    )


def _kill_process_tree(process: subprocess.Popen | None) -> None:
    if process is None:
        return
    # Only a real Popen has a process tree we started. Test doubles use a
    # stand-in pid and must not be resolved through psutil.
    if isinstance(process, _REAL_POPEN):
        try:
            import psutil
            owned = psutil.Process(process.pid)
            for child in owned.children(recursive=True):
                try:
                    child.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass
    try:
        process.kill()
    except Exception:
        pass


def _drain_stream(stream: Any, chunks: list[str], limit: int) -> None:
    if stream is None:
        return
    total = 0
    try:
        while True:
            piece = stream.read(4096)
            if not piece:
                break
            if total >= limit:
                continue
            remaining = limit - total
            chunks.append(piece[:remaining])
            total += len(piece[:remaining])
    except Exception:
        pass


def _login_command(
    cli_path: Path,
    profile: str,
    *,
    mode: str,
    account_email: str | None,
    browser: str,
    browser_timeout: int,
    force: bool = False,
    switch_account: bool = False,
    fresh_login: bool = False,
) -> list[str]:
    command = [
        str(cli_path),
        "--profile", profile,
        "login",
        "--browser", browser,
        "--browser-timeout", str(max(60, int(browser_timeout))),
    ]
    if switch_account or fresh_login:
        command += ["--fresh"]
    if mode == "master-token":
        # One window at Google's EmbeddedSetup; the CLI captures the single-use
        # oauth_token itself and mints the durable master token.
        command += ["--master-token"]
        if account_email:
            command += ["--account", account_email]
        if force or switch_account:
            # Account switched: overwrite the old master-token binding.
            command += ["--force"]
    return command


def _redact_command_for_log(command: list[str]) -> str:
    """Loggable command line — oauth tokens must never reach the log file."""
    redacted: list[str] = []
    skip_next = False
    for part in command:
        if skip_next:
            redacted.append("<redacted>")
            skip_next = False
        elif part == "--oauth-token":
            redacted.append(part)
            skip_next = True
        else:
            redacted.append(part)
    return " ".join(redacted)


def _remember_login_detail(
    *, exit_code: int | None, window_opened: bool | None, cancelled: bool, elapsed: float, output: str = "",
) -> None:
    detail = {
        "exit_code": exit_code,
        "window_opened": window_opened,
        "cancelled": cancelled,
        "elapsed": elapsed,
        "output": _clean_cli_output(output[-8000:]) if output else "",
        # The CLI found a live Google session in its browser profile and
        # captured it without showing the sign-in page.
        "reused_browser_session": "already logged in" in (output or "").casefold(),
        # The CLI saved the capture without a usable __Secure-1PSIDTS.
        "psidts_unhealed": "no usable __secure-1psidts" in (output or "").casefold(),
    }
    _run_login_once.last_detail = detail
    _LOGIN_DETAIL_LOCAL.detail = detail


def _reset_login_detail() -> None:
    _LOGIN_DETAIL_LOCAL.detail = None
    try:
        _run_login_once.last_detail = {}
    except Exception:
        pass


def _current_login_detail() -> dict[str, Any]:
    """Detail of the CLI run this thread just made.

    The thread-local copy wins; tests that replace ``_run_login_once`` set the
    function attribute instead, which stays the fallback.
    """
    detail = getattr(_LOGIN_DETAIL_LOCAL, "detail", None)
    if isinstance(detail, dict):
        return detail
    detail = getattr(_run_login_once, "last_detail", None)
    return detail if isinstance(detail, dict) else {}


def _command_profile(command: list[str]) -> str | None:
    try:
        return str(command[command.index("--profile") + 1])
    except (ValueError, IndexError):
        return None


def _stop_background_cli(profile: str, log_path: Path | str | None = None) -> int:
    """Stop in-flight non-interactive CLI runs (auth refresh) for this profile.

    A sign-in clicked while the keepalive refresh is running used to race it:
    ``auth refresh --allow-headless`` can open the same browser profile
    headless, and when it finished after the sign-in it rewrote
    storage_state.json with the old session.
    """
    with _BACKGROUND_CLI_LOCK:
        targets = [proc for (prof, proc) in _BACKGROUND_CLI_PROCESSES.values() if prof in (None, profile)]
    stopped = 0
    for proc in targets:
        try:
            if proc.poll() is None:
                _kill_process_tree(proc)
                stopped += 1
        except Exception:
            continue
    if stopped and log_path is not None:
        try:
            with Path(log_path).open("a", encoding="utf-8") as handle:
                handle.write(f"[stopped {stopped} background session refresh(es) before sign-in]\n")
        except Exception:
            pass
    return stopped


def _run_login_once(
    command: list[str],
    log_path: Path,
    timeout_seconds: int,
) -> tuple[int, str]:
    """Run one CLI attempt and append stdout, stderr, and the exit code to the log.

    Interactive login is spawned through :func:`spawn_notebooklm_process` so a
    pythonw parent does not lose the child's output or kill it on startup.
    """
    global _ACTIVE_LOGIN_PROCESS
    interactive = "login" in command
    argv = _cli_argv(command)
    started = time.monotonic()
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    readers: list[threading.Thread] = []
    process: subprocess.Popen[Any] | None = None
    handoff_stop_event: threading.Event | None = None
    code: int | None = None
    error = ""
    cancelled = False
    window_opened: bool | None = None
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    with log_path.open("a", encoding="utf-8") as log_handle:
        log_handle.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] $ {_redact_command_for_log(command)}\n")
        if argv != list(command):
            log_handle.write(f"[spawn] {_redact_command_for_log(argv)}\n")
        log_handle.flush()
        # A Windows Security dialog can appear almost immediately after browser
        # launch. Snapshot before Popen so the watcher can identify it as new.
        prelaunch_hwnds: set[int] | None = None
        if interactive:
            prelaunch_hwnds = {hwnd for hwnd, *_rest in _visible_top_level_windows()}
        try:
            if interactive and _LOGIN_CANCEL.is_set():
                code = 130
                cancelled = True
                error = "Sign-in cancelled."
            else:
                process = spawn_notebooklm_process(command)
                if interactive:
                    _ACTIVE_LOGIN_PROCESS = process
                else:
                    pid = getattr(process, "pid", None)
                    if isinstance(pid, int):
                        with _BACKGROUND_CLI_LOCK:
                            _BACKGROUND_CLI_PROCESSES[pid] = (_command_profile(command), process)
                if getattr(process, "stdout", None) is not None:
                    reader = threading.Thread(
                        target=_drain_stream,
                        args=(process.stdout, stdout_chunks, _LOGIN_OUTPUT_LIMIT),
                        name="notebooklm-login-stdout",
                        daemon=True,
                    )
                    reader.start()
                    readers.append(reader)
                if getattr(process, "stderr", None) is not None:
                    reader = threading.Thread(
                        target=_drain_stream,
                        args=(process.stderr, stderr_chunks, _LOGIN_OUTPUT_LIMIT),
                        name="notebooklm-login-stderr",
                        daemon=True,
                    )
                    reader.start()
                    readers.append(reader)
                # The CLI owns browser startup. This daemon only requests
                # foreground once when its exact profile window appears.
                if interactive:
                    handoff_stop_event = threading.Event()
                    _start_login_foreground_handoff(
                        command,
                        getattr(process, "pid", None),
                        prelaunch_hwnds,
                        handoff_stop_event,
                        min(_LOGIN_MAX_CREDENTIAL_WATCH_SECONDS, max(0.0, float(timeout_seconds))),
                    )
                wait_timeout = max(60, int(timeout_seconds)) if interactive else max(8, int(timeout_seconds))
                code = int(process.wait(timeout=wait_timeout))
        except subprocess.TimeoutExpired:
            if process is not None:
                try:
                    _kill_process_tree(process)
                    process.wait(timeout=5)
                except Exception:
                    logger.warning("Timed-out NotebookLM CLI could not be reaped", exc_info=True)
            code = 124
            error = f"sign-in timed out after {timeout_seconds}s"
        except OSError as exc:
            logger.warning("NotebookLM CLI could not launch the requested browser", exc_info=True)
            code = 1
            error = (
                "Could not launch the NotebookLM sign-in browser. "
                f"Check that the selected browser is installed. ({exc})"
            )
        finally:
            if handoff_stop_event is not None:
                handoff_stop_event.set()
            if _ACTIVE_LOGIN_PROCESS is process:
                _ACTIVE_LOGIN_PROCESS = None
            if process is not None and not interactive:
                with _BACKGROUND_CLI_LOCK:
                    pid = getattr(process, "pid", None)
                    if isinstance(pid, int) and _BACKGROUND_CLI_PROCESSES.get(pid, (None, None))[1] is process:
                        _BACKGROUND_CLI_PROCESSES.pop(pid, None)
        for reader in readers:
            reader.join(timeout=2)
        output = "".join(stdout_chunks)
        err_output = "".join(stderr_chunks)
        combined = "\n".join(part for part in (output, err_output) if part)
        elapsed = time.monotonic() - started
        if code is None:
            code = 1
        if not error:
            cancelled = bool(interactive and _LOGIN_CANCEL.is_set() and code != 0)
            error, window_opened = _login_failure_message(
                code, combined, elapsed, cancelled=cancelled, interactive=interactive,
            )
        elif interactive and code != 0:
            window_opened = _infer_window_opened(elapsed, _clean_cli_output(combined))
        log_handle.write("--- stdout ---\n")
        log_handle.write(output)
        if output and not output.endswith("\n"):
            log_handle.write("\n")
        log_handle.write("--- stderr ---\n")
        log_handle.write(err_output)
        if err_output and not err_output.endswith("\n"):
            log_handle.write("\n")
        log_handle.write(f"[exit code {code} after {elapsed:.2f}s]\n")
        log_handle.flush()
    _remember_login_detail(exit_code=code, window_opened=window_opened, cancelled=cancelled,
                           elapsed=elapsed, output=combined)
    return code, error


def _watch_login(
    profile: str,
    mode: str,
    account_email: str | None,
    browser: str,
    browser_timeout: int,
    log_path: Path,
    switch_account: bool = False,
    fresh_login: bool = False,
    fresh_reason: str | None = None,
) -> None:
    """Run the sign-in chain in the background.

    One window, owned by the CLI. A failed sign-in ends this attempt; it must
    not open a second bundled-browser window with an ambiguous account state.
    """
    try:
        cli_path = resolve_notebooklm_cli()
        if cli_path is None:
            with _STATE_LOCK:
                _STATE.update(running=False, finished_at=time.time(), success=False,
                              error="NotebookLM CLI not found — cannot start sign-in", note=None)
            return

        with _STATE_LOCK:
            _STATE.update(running=True, success=None, error=None, finished_at=None)

        code, err = None, ""
        durable = False
        email = None
        global _ACTIVE_LOGIN_PROFILE
        _ACTIVE_LOGIN_PROFILE = profile
        resolved_browser = resolve_interactive_browser(browser)
        if resolved_browser != (browser or "").strip().lower():
            logger.info(
                "NotebookLM sign-in browser %s is not installed; using %s",
                browser, resolved_browser,
            )
        browser = resolved_browser
        with _STATE_LOCK:
            _STATE["browser"] = browser
        _set_note("Waiting for Google sign-in…")
        # Anything a background check or refresh started before this click is
        # now stale: fence its result and stop its CLI process.
        note_session_refreshed(profile)
        _stop_background_cli(profile, log_path)
        _terminate_stale_login_processes(profile, log_path)
        _mac_clear_runtime_quarantine(cli_path, log_path)
        if fresh_login and not switch_account:
            _backup_stale_session(profile, log_path, reason=fresh_reason or "requested")
        if switch_account:
            time.sleep(0.3)
            try:
                from .config import is_pytest_real_home_path
                b_dir = _profile_browser_dir(profile)
                if b_dir.is_dir() and not is_pytest_real_home_path(b_dir):
                    shutil.rmtree(b_dir, ignore_errors=True)
            except Exception:
                pass
        _prepare_browser_profile(profile, switch_account=switch_account)
        _log_login_environment(log_path, profile=profile, cli_path=cli_path, browser=browser,
                               fresh_login=bool(fresh_login or switch_account), fresh_reason=fresh_reason)

        # In a pytest test run where _run_login_once is not explicitly mocked, avoid launching real GUI browsers
        if os.environ.get("PYTEST_CURRENT_TEST") and getattr(_run_login_once, "__name__", "") in ("_run_login_once", ""):
            return

        def _run_cli_login(fresh: bool) -> tuple[int, str]:
            _reset_login_detail()
            if mode == "master-token" and account_email:
                force = bool(switch_account or (_storage_email() and account_email != _storage_email()))
                return _run_login_once(
                    _login_command(
                        cli_path, profile, mode="master-token",
                        account_email=account_email, browser=browser,
                        browser_timeout=browser_timeout, force=force,
                        switch_account=switch_account,
                        fresh_login=fresh,
                    ),
                    log_path,
                    browser_timeout,
                )
            return _run_login_once(
                _login_command(
                    cli_path, profile, mode="browser",
                    account_email=None, browser=browser,
                    browser_timeout=browser_timeout,
                    switch_account=switch_account,
                    fresh_login=fresh,
                ),
                log_path,
                browser_timeout,
            )

        attempt_fresh = bool(fresh_login)
        retried_fresh = False
        while True:
            code, err = _run_cli_login(attempt_fresh)
            detail = _current_login_detail()
            success = code == 0
            verified: dict[str, Any] = {}
            if success:
                # Any passive verification that began before the browser login
                # completed must not be allowed to publish an expired verdict.
                note_session_refreshed(profile)
                durable = master_token_present(profile)
                email = None
                try:
                    from .config import get_storage_state_path
                    st_p = get_storage_state_path(profile)
                    if st_p.is_file():
                        st_data = json.loads(st_p.read_text(encoding="utf-8"))
                        if isinstance(st_data, dict):
                            email = (
                                (st_data.get("notebooklm") or {}).get("account", {}).get("email")
                                or (st_data.get("account") or {}).get("email")
                            )
                except Exception:
                    pass

                if not email:
                    email = _storage_email()

                if email and not _is_placeholder(email):
                    _set_note(f"Signed in as {email} — finalizing session…")
                else:
                    _set_note("Signed in — finalizing session…")

                _log_login_line(
                    f"CLI login finished; saved auth cookies: {_session_cookie_names(profile) or 'none'}"
                )
                try:
                    verified = _verify_new_session(profile)
                    if verified.get("authenticated"):
                        email = verified.get("email") or email
                        _log_login_line(
                            f"session verified; auth cookies: {_session_cookie_names(profile) or 'none'}"
                        )
                    else:
                        success = False
                        err = _post_login_failure_message(verified)
                        _log_login_line(
                            f"session check failed (kind={verified.get('failure_kind')}); "
                            f"auth cookies: {_session_cookie_names(profile) or 'none'}"
                        )
                except Exception:
                    success = False
                    logger.warning("Post-sign-in verification failed", exc_info=True)
                    err = "Google could not verify the new session online. Check your connection and try again."

            # The CLI reused a Google session it found in its own browser
            # profile (no sign-in page was shown) and that session does not
            # work. Repeating the same click would capture it again, so move it
            # aside once and open a clean Google sign-in right away.
            if (
                not success and code == 0 and not retried_fresh and not attempt_fresh
                and not switch_account and not detail.get("cancelled") and not _LOGIN_CANCEL.is_set()
                and verified.get("failure_kind") != "network"
                and (detail.get("reused_browser_session") or verified.get("failure_kind") == "no_session")
            ):
                retried_fresh = True
                attempt_fresh = True
                logger.info("NotebookLM: reused browser session failed verification; starting a fresh sign-in")
                _set_note("Your old Google session could not be used. Opening a fresh Google sign-in…")
                _terminate_stale_login_processes(profile, log_path)
                _backup_stale_session(profile, log_path, reason="reused_session_failed")
                _prepare_browser_profile(profile)
                continue
            break

        if success:
            with _STATE_LOCK:
                _FRESH_NEXT.pop(profile, None)
        elif not detail.get("cancelled") and not switch_account:
            # A sign-in that ended without a usable session: the next click
            # starts from a clean browser profile (the old one is backed up).
            with _STATE_LOCK:
                _FRESH_NEXT[profile] = "previous_attempt_failed"

        if success:
            switched_from = None
            if switch_account:
                try:
                    from voice_flow.storage import storage
                    switched_from = storage.get_setting("video_flow_notebooklm_switched_from")
                except Exception:
                    pass
                if not switched_from:
                    try:
                        from voice_flow.gui import api_server
                        switched_from = api_server.storage.get_setting("video_flow_notebooklm_switched_from")
                    except Exception:
                        pass
                switched_from = str(switched_from or "").strip().lower()

            if switch_account and switched_from and email and email.strip().lower() == switched_from:
                logger.warning(
                    "Account switch rejected: detected account %s is identical to switched_from %s",
                    email,
                    switched_from,
                )
                success = False
                err = f"Account switch failed: still signed in as {email}. Please select a different account."

        if success:
            email = email or _storage_email() or "your Google account"
            # Never persist the display placeholder as if it were a real account email.
            if not _is_placeholder(email):
                _save_email(str(email))
            try:
                from voice_flow.storage import storage
                storage.save_setting("video_flow_notebooklm_authenticated", True)
                storage.save_setting("video_flow_notebooklm_disconnected", False)
                if not _is_placeholder(email):
                    storage.save_setting("video_flow_notebooklm_email", str(email))
                storage.save_setting("video_flow_notebooklm_switched_from", "")
            except Exception:
                pass
            try:
                from .keepalive import reset_session_refresh_state
                reset_session_refresh_state(profile, state="authenticated")
            except Exception:
                pass
            try:
                from voice_flow.gui import api_server
                api_server.storage.save_setting("video_flow_notebooklm_authenticated", True)
                api_server.storage.save_setting("video_flow_notebooklm_disconnected", False)
                if not _is_placeholder(email):
                    api_server.storage.save_setting("video_flow_notebooklm_email", str(email))
                api_server.storage.save_setting("video_flow_notebooklm_switched_from", "")
            except Exception:
                pass

            try:
                from .config import (
                    count_valid_cookies,
                    get_storage_backup_path,
                    get_storage_state_path,
                    is_pytest_real_home_path,
                    mirror_storage_state_guarded,
                    write_storage_state_guarded,
                )
                st = get_storage_state_path(profile)
                b_st = get_storage_backup_path(profile)
                if is_pytest_real_home_path(st):
                    logger.warning(
                        "login watcher: pytest isolation — skipping storage_state update for real-home path %s", st
                    )
                elif st.is_file() and st.stat().st_size > 0:
                    st_data = json.loads(st.read_text(encoding="utf-8"))
                    if isinstance(st_data, dict):
                        if email and not _is_placeholder(email):
                            st_data.setdefault("notebooklm", {})["account"] = {"email": email}
                            st_data["account"] = {"email": email}
                            write_storage_state_guarded(
                                st, json.dumps(st_data, indent=2), source="login_flow._watch_login"
                            )
                        if count_valid_cookies(st_data) > 0:
                            mirror_storage_state_guarded(
                                json.dumps(st_data, indent=2),
                                st,
                                [b_st, st.with_name("storage_state.safe_copy.json")],
                                source="login_flow._watch_login",
                            )
            except Exception:
                pass

        detail = _current_login_detail()
        note = None
        if detail.get("cancelled"):
            note = "Sign-in cancelled."
            success = False
        elif success and mode == "master-token" and not durable:
            note = ("Signed in — but the one-time durable setup didn't finish this time. "
                    "Click Sign in once more when convenient.")
        elif success and email and not _is_placeholder(email):
            note = f"Signed in as {email}"
        elif success:
            note = "Signed in"
        elif not success:
            note = err or "Google sign-in did not finish. Check the sign-in window, then try Reconnect again."

        with _STATE_LOCK:
            _STATE.update(
                running=False,
                finished_at=time.time(),
                success=success,
                durable=durable,
                error=None if success else note,
                email=email if (success and not _is_placeholder(email)) else None,
                note=note,
                exit_code=detail.get("exit_code", code),
                window_opened=True if success else detail.get("window_opened"),
                cancelled=bool(detail.get("cancelled")),
                browser=browser,
            )
            if success:
                _cache_online_verification(profile, {
                        "status": "ok",
                        "authenticated": True,
                        "message": "Google session verified",
                        "email": email if not _is_placeholder(email) else None,
                        "profile": profile,
                        "master_token_present": durable,
                    })
        logger.info("NotebookLM %s login finished: success=%s durable=%s", mode, success, durable)
    except Exception as exc:  # defensive: watcher must never die silently
        logger.exception("NotebookLM login watcher failed")
        with _STATE_LOCK:
            _STATE.update(
                running=False,
                finished_at=time.time(),
                success=False,
                error="Sign-in could not start. Check the NotebookLM CLI and browser, then try again.",
                note=None,
                window_opened=False,
            )
    finally:
        if _ACTIVE_LOGIN_PROFILE == profile:
            _ACTIVE_LOGIN_PROFILE = None


def record_successful_login(email: str, profile: str | None = None) -> None:
    """Record a browser-flow login only after the CLI verifies it online."""
    profile = resolve_notebooklm_profile(profile)
    note_session_refreshed(profile)
    verification = _verify_new_session(profile)
    if not verification.get("authenticated"):
        with _STATE_LOCK:
            _STATE.update(
                running=False,
                finished_at=time.time(),
                success=False,
                error=_post_login_failure_message(verification),
                note="Sign-in finished in the browser, but NotebookLM could not verify it. Please try again.",
            )
        return
    durable = master_token_present(profile)
    display_email = str(email or "").strip() or "your Google account"
    # Placeholders must never be persisted as the account email (they once ended
    # up inside storage_state.json / app settings via metadata-only save paths).
    real_email: str | None = None if _is_placeholder(email) else (str(email or "").strip() or None)
    with _STATE_LOCK:
        _STATE.update(
            running=False,
            finished_at=time.time(),
            success=True,
            durable=durable,
            error=None,
            email=display_email,
            note=f"Signed in as {display_email}",
        )
        _cache_online_verification(profile, {
                "status": "ok",
                "authenticated": True,
                "message": "Google session verified",
                "email": display_email,
                "profile": profile,
                "master_token_present": durable,
            })
    if real_email:
        _save_email(real_email)
    try:
        from voice_flow.storage import storage
        storage.save_setting("video_flow_notebooklm_authenticated", True)
        storage.save_setting("video_flow_notebooklm_disconnected", False)
        if real_email:
            storage.save_setting("video_flow_notebooklm_email", real_email)
        storage.save_setting("video_flow_notebooklm_switched_from", "")
    except Exception:
        pass
    try:
        from voice_flow.gui import api_server
        api_server.storage.save_setting("video_flow_notebooklm_authenticated", True)
        api_server.storage.save_setting("video_flow_notebooklm_disconnected", False)
        if real_email:
            api_server.storage.save_setting("video_flow_notebooklm_email", real_email)
        api_server.storage.save_setting("video_flow_notebooklm_switched_from", "")
    except Exception:
        pass
    try:
        from .config import (
            count_valid_cookies,
            get_storage_backup_path,
            get_storage_state_path,
            is_pytest_real_home_path,
            mirror_storage_state_guarded,
            write_storage_state_guarded,
        )
        st = get_storage_state_path(profile)
        b_st = get_storage_backup_path(profile)
        if is_pytest_real_home_path(st):
            logger.warning(
                "record_successful_login: pytest isolation — skipping storage_state update for real-home path %s", st
            )
        elif st.is_file() and st.stat().st_size > 0:
            st_data = json.loads(st.read_text(encoding="utf-8"))
            if isinstance(st_data, dict):
                if real_email:
                    st_data.setdefault("notebooklm", {})["account"] = {"email": real_email}
                    st_data["account"] = {"email": real_email}
                    write_storage_state_guarded(st, json.dumps(st_data, indent=2), source="login_flow.record_successful_login")
                if count_valid_cookies(st_data) > 0:
                    mirror_storage_state_guarded(
                        json.dumps(st_data, indent=2),
                        st,
                        [b_st, st.with_name("storage_state.safe_copy.json")],
                        source="login_flow.record_successful_login",
                    )
    except Exception:
        pass
    try:
        from .keepalive import reset_session_refresh_state
        reset_session_refresh_state(profile, state="authenticated")
    except Exception:
        pass


def disconnect_login(profile: str | None = None) -> dict[str, Any]:
    """Disconnect the NotebookLM session and mark unauthenticated."""
    profile = resolve_notebooklm_profile(profile)
    note_session_refreshed(profile)
    try:
        from voice_flow.storage import storage
        storage.save_setting("video_flow_notebooklm_authenticated", False)
        storage.save_setting("video_flow_notebooklm_email", "")
        storage.save_setting("video_flow_notebooklm_disconnected", True)
    except Exception:
        pass
    try:
        from voice_flow.gui import api_server
        api_server.storage.save_setting("video_flow_notebooklm_authenticated", False)
        api_server.storage.save_setting("video_flow_notebooklm_email", "")
        api_server.storage.save_setting("video_flow_notebooklm_disconnected", True)
    except Exception:
        pass

    try:
        from .config import get_storage_backup_path, get_storage_state_path, is_pytest_real_home_path
        st_path = get_storage_state_path(profile)
        if is_pytest_real_home_path(st_path):
            logger.warning(
                "disconnect_login: pytest isolation — skipping credential deletion for real-home path %s", st_path
            )
        else:
            if st_path.is_file():
                try:
                    data = json.loads(st_path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        data["cookies"] = []
                        if "notebooklm" in data and isinstance(data["notebooklm"], dict):
                            data["notebooklm"].pop("account", None)
                        data.pop("account", None)
                        st_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                except Exception:
                    pass
            b_path = get_storage_backup_path(profile)
            if b_path.is_file():
                b_path.unlink(missing_ok=True)
            safe_path = st_path.with_name("storage_state.safe_copy.json")
            if safe_path.is_file():
                safe_path.unlink(missing_ok=True)
    except Exception:
        pass

    try:
        mt_file = _master_token_json_path(profile)
        if mt_file.is_file() and not is_pytest_real_home_path(mt_file):
            mt_file.unlink(missing_ok=True)
    except Exception:
        pass

    try:
        from .config import is_pytest_real_home_path
        _terminate_stale_login_processes(profile, _login_log_path())
        b_dir = _profile_browser_dir(profile)
        if b_dir.is_dir() and not is_pytest_real_home_path(b_dir):
            time.sleep(0.15)
            shutil.rmtree(b_dir, ignore_errors=True)
    except Exception:
        pass

    with _STATE_LOCK:
        _STATE.update(
            running=False,
            finished_at=time.time(),
            success=False,
            durable=False,
            error=None,
            note="Disconnected",
        )
        _cache_online_verification(profile, {
                "status": "unauthenticated",
                "authenticated": False,
                "message": "Disconnected",
                "email": None,
                "profile": profile,
                "master_token_present": False,
            })
    try:
        from .keepalive import reset_session_refresh_state
        reset_session_refresh_state(profile)
    except Exception:
        pass
    return {"success": True, "authenticated": False, "profile": profile}


def cancel_login(profile: str | None = None) -> dict[str, Any]:
    """Stop an in-progress interactive sign-in without touching a saved session.

    Kills the CLI process and any browser it opened against this profile's
    dedicated directory. Cookie refresh and keepalive are left alone.
    """
    global _ACTIVE_LOGIN_PROCESS
    target = resolve_notebooklm_profile(profile or _ACTIVE_LOGIN_PROFILE)
    with _STATE_LOCK:
        running = bool(_STATE.get("running"))
    process = _ACTIVE_LOGIN_PROCESS
    if not running and (process is None or process.poll() is not None):
        return {"cancelled": False, "already_finished": True, "profile": target, "state": get_login_state()}
    _LOGIN_CANCEL.set()
    if process is not None and process.poll() is None:
        _kill_process_tree(process)
    try:
        _terminate_stale_login_processes(target, _login_log_path())
    except Exception:
        pass
    with _STATE_LOCK:
        if not _STATE.get("running"):
            return {"cancelled": True, "profile": target, "state": get_login_state()}
        _STATE.update(
            running=False,
            finished_at=time.time(),
            success=False,
            cancelled=True,
            error="Sign-in cancelled.",
            note="Sign-in cancelled.",
            window_opened=False,
        )
    return {"cancelled": True, "profile": target, "state": get_login_state()}


def start_login(
    *,
    profile: str | None = None,
    account_email: str | None = None,
    mode: str | None = None,
    browser: str = "chrome",
    browser_timeout: int = _LOGIN_TIMEOUT_SECONDS,
    switch_account: bool = False,
    fresh_login: bool = False,
    port: int | None = None,
    direct: bool = True,
    cookie_payload: Any = None,
) -> dict[str, Any]:
    """Launch the CLI-owned NotebookLM sign-in; retain legacy browser modes.

    The normal path uses an isolated browser profile that the CLI can save and
    refresh. A system-browser Google sign-in alone does not provide the CLI with
    NotebookLM cookies, so that legacy mode is not the default.
    """
    if os.environ.get("VOICE_FLOW_LOGIN_DISABLE"):
        # Test/CI contexts must never open real browsers (pytest conftest sets this).
        return {"launched": False, "error": "Interactive sign-in is disabled in this environment"}

    profile = resolve_notebooklm_profile(profile)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", profile) or profile in {".", ".."}:
        return {"launched": False, "error": "Invalid NotebookLM profile name"}

    if switch_account:
        with _STATE_LOCK:
            if _STATE.get("running"):
                return {
                    "launched": True,
                    "already_running": True,
                    "mode": _STATE.get("mode"),
                    "profile": profile,
                    "message": "Waiting for Google sign-in…",
                    "state": get_login_state(),
                }
        _clean_account_state_for_switch(profile)

    if mode in ("sync-browser", "browser-cookies"):
        from .browser_sync import auto_sync_from_browser

        res = auto_sync_from_browser(profile=profile)
        if res.get("success"):
            return {
                "launched": True,
                "mode": "sync-browser",
                "profile": profile,
                "message": f"Successfully synced session for {res.get('email') or 'your Google account'} from browser.",
                "state": get_login_state(),
                **res,
            }
        return {
            "launched": False,
            "error": res.get("error") or "Could not extract active session cookies from browser.",
            "profile": profile,
        }

    if mode in ("import", "paste-cookies", "import-cookies"):
        from .browser_sync import import_cookies

        res = import_cookies(cookie_payload, profile=profile, email=account_email)
        if res.get("success"):
            return {
                "launched": True,
                "mode": "import",
                "profile": profile,
                "message": f"Successfully imported {res.get('cookies_count', 0)} cookies.",
                "state": get_login_state(),
                **res,
            }
        return {
            "launched": False,
            "error": res.get("error") or "Invalid cookie payload.",
            "profile": profile,
        }

    # The ordinary CLI browser login is the default.  It creates the profile
    # used by refresh/status/MCP without capturing a Google master token.
    if mode is None:
        mode = "cli"

    cli_path = resolve_notebooklm_cli()
    if cli_path is None and mode not in ("browser", "system-browser"):
        return {"launched": False, "error": "NotebookLM CLI not found — cannot start sign-in"}

    if mode in ("master-token", "legacy-cli", "cli", "interactive", "playwright", "durable"):
        if switch_account:
            account_email = account_email.strip() if account_email else None
        else:
            if not account_email:
                try:
                    account_email = _storage_email(profile)
                except TypeError:
                    account_email = _storage_email()
            account_email = (account_email or "").strip() or None
        run_mode = "master-token" if (mode in ("master-token", "durable") and account_email) else "browser"
        fresh_reason: str | None = "requested" if fresh_login else None
        with _STATE_LOCK:
            already_running = bool(_STATE.get("running"))
        if not switch_account and not fresh_login and not already_running:
            # A new user, a broken old session, or a click after a failed
            # attempt starts from a clean browser profile. Reusing one that a
            # previous attempt left behind is how the CLI kept capturing the
            # same unusable session. A healthy saved session is reused, so a
            # reconnect stays one click.
            with _STATE_LOCK:
                fresh_next = _FRESH_NEXT.get(profile)
            kind = _saved_session_kind(profile)
            if kind in ("none", "broken"):
                fresh_login, fresh_reason = True, ("new_user" if kind == "none" else "broken_session")
            elif fresh_next:
                fresh_login, fresh_reason = True, fresh_next
        with _STATE_LOCK:
            if _STATE.get("running"):
                # A second click, including Switch account, must not start another
                # browser. The open attempt stays in Waiting until it finishes
                # or the user presses Cancel.
                return {
                    "launched": True,
                    "already_running": True,
                    "mode": _STATE.get("mode"),
                    "profile": profile,
                    "message": "Waiting for Google sign-in…",
                    "state": get_login_state(),
                }
            _LOGIN_CANCEL.clear()
            log_path = _login_log_path()
            _STATE.update(
                running=True,
                mode=run_mode,
                started_at=time.time(),
                finished_at=None,
                success=None,
                error=None,
                note="Waiting for Google sign-in…",
                durable=None,
                log_path=str(log_path),
                exit_code=None,
                window_opened=None,
                cancelled=False,
                browser=browser,
            )
        thread = threading.Thread(
            target=_watch_login,
            args=(profile, run_mode, account_email, browser, int(browser_timeout), log_path, switch_account, fresh_login),
            kwargs={"fresh_reason": fresh_reason},
            name="notebooklm-login",
            daemon=True,
        )
        thread.start()
        logger.info("NotebookLM %s login launched (profile=%s, browser=%s)", run_mode, profile, browser)
        msg = (
            "NotebookLM sign-in window launched — complete Google sign-in there."
            if run_mode == "master-token"
            else "Google NotebookLM sign-in window launched."
        )
        return {
            "launched": True,
            "mode": run_mode,
            "profile": profile,
            "message": msg,
            "fresh_login": bool(fresh_login),
            "fresh_reason": fresh_reason,
            "state": get_login_state(),
        }

    with _STATE_LOCK:
        if switch_account:
            _STATE["running"] = False
        elif _STATE.get("running"):
            started_at = _STATE.get("started_at")
            if started_at and (time.time() - float(started_at)) > 90:
                _STATE["running"] = False
            else:
                return {"launched": False, "already_running": True, "state": get_login_state()}

        log_path = _login_log_path()
        _STATE.update(
            running=True,
            mode="browser",
            started_at=time.time(),
            finished_at=None,
            success=None,
            error=None,
            note=(
                "Google NotebookLM account chooser opened in your default browser — select an account."
                if switch_account
                else "Google NotebookLM sign-in opened in your default browser — choose your Google account there."
            ),
            durable=None,
            log_path=str(log_path),
        )

    try:
        from voice_flow.google_auth import start_notebooklm_browser_flow
        from voice_flow.gui.api_server import PORT

        actual_port = int(port) if port is not None else PORT
        flow_res = start_notebooklm_browser_flow(
            port=actual_port,
            profile=profile,
            switch_account=switch_account,
            direct=direct,
        )
        if not flow_res.get("success"):
            raise RuntimeError(flow_res.get("error") or "Could not open default browser.")
    except Exception as exc:
        with _STATE_LOCK:
            _STATE.update(running=False, finished_at=time.time(), success=False, error=str(exc)[:300])
        return {"launched": False, "error": str(exc)}

    message = (
        "Google NotebookLM account chooser opened in your default browser. Select an account to switch."
        if switch_account
        else (
            "Google NotebookLM sign-in opened in your default browser. "
            "Select your Google account there — Voice Flow connects automatically once selected."
        )
    )
    return {
        "launched": True,
        "mode": "browser",
        "profile": profile,
        "message": message,
        "state": get_login_state(),
        "direct_login_url": flow_res.get("direct_login_url"),
        "auth_url": flow_res.get("auth_url"),
    }


def get_login_state() -> dict[str, Any]:
    with _STATE_LOCK:
        return {k: v for k, v in _STATE.items() if k != "running"} | {"running": bool(_STATE.get("running"))}


def get_online_verification_cache(profile: str | None = None) -> dict[str, Any] | None:
    """Return the cached online verification result if still valid, or None."""
    with _STATE_LOCK:
        target_profile = resolve_notebooklm_profile(profile)
        entry = _ONLINE_CACHE.get(target_profile) or {}
        cached = entry.get("result")
        checked_at = float(entry.get("checked_at") or 0)
        if cached and (time.time() - checked_at) < _ONLINE_CACHE_SECONDS:
            res = dict(cached)
            res["checked_at"] = checked_at
            return res
    return None


_NO_SESSION_MESSAGE = "NotebookLM is not connected yet. Click Sign in with Google to connect."


def _is_missing_session_error(payload: dict[str, Any], details_lower: str) -> bool:
    """True when the CLI found no saved session file for the profile."""
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    if checks.get("storage_exists") is False:
        return True
    return "storage file not found" in details_lower


def _transient_verification_message(details_message: str) -> str:
    """User-facing text for an inconclusive check, with the CLI's own reason.

    The bare "Could not verify this saved session" gave nobody a way to tell a
    missing cookie from a Google redirect. URLs are already redacted.
    """
    reason = str(details_message or "").strip()
    if reason.lower().startswith("token fetch failed:"):
        reason = reason.split(":", 1)[1].strip()
    reason = reason.splitlines()[0].strip() if reason else ""
    if len(reason) > 160:
        reason = reason[:157].rstrip() + "..."
    return f"Could not verify this saved session: {reason}" if reason else "Could not verify this saved session"


def _log_verification(profile: str, *, passive: bool, returncode: int | None, status: str, reason: str) -> None:
    """Record why a session check did not pass, in the app log and the sign-in log."""
    clean = re.sub(r"https?://\S+", "<redacted URL>", str(reason or ""))[:600]
    logger.warning(
        "NotebookLM auth check did not pass (profile=%s passive=%s rc=%s status=%s): %s",
        profile, passive, returncode, status, clean,
    )
    try:
        with _login_log_path().open("a", encoding="utf-8") as handle:
            handle.write(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [verify] profile={profile} passive={passive} "
                f"rc={returncode} status={status} reason={clean}\n"
            )
    except Exception:
        pass


_MISSING_SID_RE = re.compile(r"missing required cookies[^:]*:[^\n]*\bSID\b", re.IGNORECASE)
_SIGN_IN_NOT_FINISHED_MESSAGE = (
    "Google sign-in didn't finish in the NotebookLM window, so nothing was connected. "
    "Click Try again and sign in to Google in the window that opens."
)


def _post_login_failure_message(verified: dict[str, Any]) -> str:
    """Toast text when Google sign-in finished but the new session failed its check.

    Never "this saved session": right after a sign-in there is no old session
    in play, and a new user must not be told one could not be verified.
    """
    kind = verified.get("failure_kind")
    if kind == "network":
        return "Signed in, but Google could not be reached to confirm it. Check your connection and click Sign in again."
    if kind == "no_session":
        return "Google sign-in finished, but no NotebookLM session was saved. Click Sign in with Google to try again."
    if kind == "auth":
        return "Google did not accept the new sign-in. Click Sign in with Google to sign in again."
    reason = str(verified.get("details_message") or "").strip()
    if reason.lower().startswith("token fetch failed:"):
        reason = reason.split(":", 1)[1].strip()
    reason = reason.splitlines()[0].strip() if reason else ""
    if _MISSING_SID_RE.search(reason):
        # The window closed before Google finished signing in (no SID cookie
        # was saved). Nothing is wrong with the account: just sign in again.
        return _SIGN_IN_NOT_FINISHED_MESSAGE
    if len(reason) > 160:
        reason = reason[:157].rstrip() + "..."
    base = "Signed in, but NotebookLM could not confirm the new session"
    return f"{base}: {reason}" if reason else f"{base}. Click Sign in with Google to try again."


def _verify_new_session(profile: str) -> dict[str, Any]:
    """Verify a session the CLI has just written, letting the CLI heal it.

    Non-passive, with a timeout that fits a cold Windows start, and one retry
    when the first answer is inconclusive. A definite answer (signed in, or
    signed out) is returned at once.
    """
    verified: dict[str, Any] = {}
    for attempt in range(2):
        verified = verify_online(
            profile=profile,
            force=True,
            timeout=_POST_LOGIN_VERIFY_TIMEOUT_SECONDS,
            passive=False,
        )
        if verified.get("authenticated") or verified.get("definitive") or verified.get("status") == "stale":
            return verified
        if attempt == 0:
            time.sleep(_POST_LOGIN_VERIFY_RETRY_DELAY_SECONDS)
    return verified


def verify_online(
    *,
    profile: str | None = None,
    timeout: float = _ONLINE_CHECK_TIMEOUT_SECONDS,
    force: bool = False,
    passive: bool = True,
) -> dict[str, Any]:
    """Online Google session verification via ``notebooklm auth check --test``.

    Cached briefly so dashboard polling never hammers accounts.google.com.

    ``passive=True`` (the default for background status checks) adds
    ``--passive``: the CLI only reads the cookies on disk and never rotates or
    rewrites them. Right after ``notebooklm login`` that is the wrong probe.
    The CLI saves a fresh sign-in even when it has no usable
    ``__Secure-1PSIDTS`` yet and expects the next ordinary command to heal it
    from disk; a passive probe refuses to do that and fails. Post-login checks
    therefore pass ``passive=False``.
    """
    profile = resolve_notebooklm_profile(profile)
    with _STATE_LOCK:
        entry = _ONLINE_CACHE.get(profile) or {}
        cached = entry.get("result")
        if cached and not force and (time.time() - float(entry.get("checked_at") or 0)) < _ONLINE_CACHE_SECONDS:
            return dict(cached)
        check_generation = _SESSION_GENERATION.get(profile, 0)

    cli_path = resolve_notebooklm_cli()
    if cli_path is None:
        return {"status": "dependency_missing", "authenticated": False,
                "message": "NotebookLM CLI not found"}
    command = [str(cli_path), "--profile", profile, "auth", "check", "--test"]
    if passive:
        command.append("--passive")
    command.append("--json")
    argv = _cli_argv(command)
    interpreter = Path(argv[0]) if len(argv) >= 3 and argv[1] == "-m" else None
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(8.0, float(timeout)),
            env=_login_child_env(interpreter if interpreter is not None and interpreter.is_file() else None),
            cwd=_spawn_cwd(),
            creationflags=_HIDE_FLAGS,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        _log_verification(profile, passive=passive, returncode=None, status="timeout_or_oserror",
                          reason=str(exc))
        verified = {"status": "network_error", "classification": "transient_error",
                    "authenticated": None, "definitive": False, "failure_kind": "network",
                    "message": "Could not reach Google to verify this saved session",
                    "profile": profile, "details_message": str(exc)[:300]}
        with _STATE_LOCK:
            if _SESSION_GENERATION.get(profile, 0) != check_generation:
                return {"status": "stale", "authenticated": None, "definitive": False, "profile": profile}
            _cache_online_verification(profile, verified, time.time() - (_ONLINE_CACHE_SECONDS - 30.0))
        return dict(verified)
    try:
        payload = json.loads(result.stdout or "{}")
        if not isinstance(payload, dict):
            raise ValueError("CLI returned a non-object payload")
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        _log_verification(profile, passive=passive, returncode=getattr(result, "returncode", None),
                          status="unreadable", reason=f"{exc}; stderr={getattr(result, 'stderr', '') or ''}")
        verified = {"status": "transient_error", "classification": "transient_error",
                    "authenticated": None, "definitive": False, "failure_kind": "cli",
                    "message": "NotebookLM verification returned an unreadable response",
                    "profile": profile, "details_message": str(exc)[:300]}
        with _STATE_LOCK:
            if _SESSION_GENERATION.get(profile, 0) != check_generation:
                return {"status": "stale", "authenticated": None, "definitive": False, "profile": profile}
            _cache_online_verification(profile, verified, time.time() - (_ONLINE_CACHE_SECONDS - 30.0))
        return verified

    authenticated = result.returncode == 0 and str(payload.get("status") or "").casefold() == "ok"
    diagnostics = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    diagnostic_error = payload.get("error") or diagnostics.get("error")
    if isinstance(diagnostic_error, dict):
        diagnostic_error = diagnostic_error.get("message") or diagnostic_error.get("error")
    raw_details = str(payload.get("message") or diagnostic_error or getattr(result, "stderr", "") or "")
    # The pinned CLI nests token-fetch failures in details.error and can include
    # credential-bearing Google redirect URLs. Keep the verdict, redact URLs.
    details_message = re.sub(r"https?://\S+", "<redacted URL>", raw_details)[:300]
    details_lower = details_message.lower()
    is_network_error = not authenticated and any(word in details_lower for word in (
        "timeout", "timed out", "connection", "network", "socket", "unreachable", "getaddrinfo",
        "dns", "temporarily unavailable", "service unavailable",
    ))
    is_definite_auth_error = not authenticated and any(phrase in details_lower for phrase in (
        "authentication expired", "not authenticated", "unauthenticated", "sign in again",
        "login required", "session expired", "invalid credentials",
    ))
    # No storage_state.json at all: nothing was ever saved for this profile.
    # That is "not signed in yet", not a session we failed to verify.
    no_saved_session = bool(
        not authenticated and not is_network_error and not is_definite_auth_error
        and _is_missing_session_error(payload, details_lower)
    )
    if no_saved_session:
        is_definite_auth_error = True
    if not authenticated:
        _log_verification(profile, passive=passive, returncode=result.returncode,
                          status=str(payload.get("status") or ""), reason=details_message)
    token_extraction_failure = bool(
        not authenticated and not is_network_error and not is_definite_auth_error
        and is_token_extraction_error(details_message)
    )
    transient_failure = not authenticated and (is_network_error or not is_definite_auth_error)
    # Hold the generation fence through every settings/file/cache publication.
    # Explicit disconnect/login completion increments the generation under the
    # same lock, so it either precedes all of this publication or follows it.
    _STATE_LOCK.acquire()
    if _SESSION_GENERATION.get(profile, 0) != check_generation:
        _STATE_LOCK.release()
        return {"status": "stale", "authenticated": None, "definitive": False, "profile": profile}
    account = payload.get("account") if isinstance(payload.get("account"), dict) else {}
    master = payload.get("master_token") if isinstance(payload.get("master_token"), dict) else {}
    email = str(account.get("email") or "").strip() or None
    if email and authenticated:
        _save_email(email)
        try:
            from voice_flow.storage import storage
            storage.save_setting("video_flow_notebooklm_email", email)
            storage.save_setting("video_flow_notebooklm_authenticated", True)
            storage.save_setting("video_flow_notebooklm_disconnected", False)
            storage.save_setting("video_flow_notebooklm_switched_from", "")
            storage.save_setting("video_flow_notebooklm_auth_error", "")
        except Exception:
            pass
        try:
            from voice_flow.gui import api_server
            api_server.storage.save_setting("video_flow_notebooklm_email", email)
            api_server.storage.save_setting("video_flow_notebooklm_authenticated", True)
            api_server.storage.save_setting("video_flow_notebooklm_disconnected", False)
            api_server.storage.save_setting("video_flow_notebooklm_switched_from", "")
            api_server.storage.save_setting("video_flow_notebooklm_auth_error", "")
        except Exception:
            pass
        try:
            from .config import (
                count_valid_cookies,
                get_storage_backup_path,
                get_storage_state_path,
                is_pytest_real_home_path,
                is_placeholder_email,
                mirror_storage_state_guarded,
                write_storage_state_guarded,
            )
            st = get_storage_state_path(profile)
            b_st = get_storage_backup_path(profile)
            if is_pytest_real_home_path(st):
                logger.warning(
                    "verify_online: pytest isolation — skipping storage_state update for real-home path %s", st
                )
            elif st.is_file() and not is_placeholder_email(email):
                st_data = json.loads(st.read_text(encoding="utf-8"))
                if isinstance(st_data, dict):
                    st_data.setdefault("notebooklm", {})["account"] = {"email": email}
                    st_data["account"] = {"email": email}
                    write_storage_state_guarded(st, json.dumps(st_data, indent=2), source="login_flow.verify_online")
                    if count_valid_cookies(st_data) > 0:
                        mirror_storage_state_guarded(
                            json.dumps(st_data, indent=2),
                            st,
                            [b_st, st.with_name("storage_state.safe_copy.json")],
                            source="login_flow.verify_online",
                        )
        except Exception:
            pass
    elif not authenticated and not transient_failure:
        auth_error_text = _NO_SESSION_MESSAGE if no_saved_session else "Google session is no longer valid — sign in again"
        try:
            from voice_flow.storage import storage
            storage.save_setting("video_flow_notebooklm_authenticated", False)
            storage.save_setting("video_flow_notebooklm_auth_error", auth_error_text)
        except Exception:
            pass
        try:
            from voice_flow.gui import api_server
            api_server.storage.save_setting("video_flow_notebooklm_authenticated", False)
            api_server.storage.save_setting("video_flow_notebooklm_auth_error", auth_error_text)
        except Exception:
            pass

    if not email:
        try:
            from voice_flow.storage import storage
            stored_e = storage.get_setting("video_flow_notebooklm_email")
            if stored_e:
                email = str(stored_e).strip()
        except Exception:
            pass

    verified = {
        "status": "ok" if authenticated else ("network_error" if is_network_error else ("transient_error" if transient_failure else "unauthenticated")),
        "classification": "authenticated" if authenticated else ("transient_error" if transient_failure else "sign_in_required"),
        "authenticated": True if authenticated else (False if is_definite_auth_error else None),
        "definitive": bool(authenticated or is_definite_auth_error),
        "failure_kind": None if authenticated else (
            "network" if is_network_error else
            ("no_session" if no_saved_session else
             ("auth" if is_definite_auth_error else
              ("token_extraction" if token_extraction_failure else "cli")))
        ),
        "message": "Google session verified online" if authenticated else (
            "Could not reach Google to verify this saved session" if is_network_error
            else (_NO_SESSION_MESSAGE if no_saved_session else
                  ("NotebookLM could not read the session token; restoring the saved connection."
                   if token_extraction_failure else
                   (_transient_verification_message(details_message) if transient_failure
                    else "Google session is no longer valid — sign in again")))
        ),
        "email": email,
        "profile": profile,
        "master_token_present": bool(master.get("present")),
        "details_message": details_message,
    }
    try:
        if _SESSION_GENERATION.get(profile, 0) != check_generation:
            return {"status": "stale", "authenticated": None, "definitive": False, "profile": profile}
        cache_age = 0.0 if authenticated else (_ONLINE_CACHE_SECONDS - (30.0 if transient_failure else 45.0))
        cache_ts = time.time() - cache_age
        _cache_online_verification(profile, verified, cache_ts)
        return dict(verified)
    finally:
        _STATE_LOCK.release()

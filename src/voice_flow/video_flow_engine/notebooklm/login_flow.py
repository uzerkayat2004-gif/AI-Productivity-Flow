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
import threading
import time
from pathlib import Path
from typing import Any

from .config import (
    get_profile_dir,
    resolve_notebooklm_cli,
    resolve_notebooklm_profile,
)

logger = logging.getLogger(__name__)

_LOGIN_TIMEOUT_SECONDS = 300
_ONLINE_CHECK_TIMEOUT_SECONDS = 75
_ONLINE_CACHE_SECONDS = 120.0
_HIDE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

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
    """Run one bounded CLI refresh verification without opening a browser."""
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
        verification = verify_online(profile=profile, force=True, timeout=min(15.0, remaining))
        if verification.get("authenticated") is True:
            code, err = 0, ""
        elif verification.get("definitive") and verification.get("failure_kind") == "auth":
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
                            from voice_flow.storage import StorageEngine
                            StorageEngine().save_setting("video_flow_notebooklm_email", email)
                            StorageEngine().save_setting("video_flow_notebooklm_authenticated", True)
                            StorageEngine().save_setting("video_flow_notebooklm_auth_error", "")
                            StorageEngine().save_setting("video_flow_notebooklm_disconnected", False)
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
    classification = "authenticated" if code == 0 else (
        "sign_in_required" if verification and verification.get("definitive") and not recovery_retryable
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
        log_dir = Path.home() / ".voice_flow" / "logs"
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
        from voice_flow.storage import StorageEngine

        email = str(StorageEngine().get_setting("video_flow_notebooklm_email") or "").strip()
        if email and not _is_placeholder(email):
            return email
    except Exception:
        pass

    return None


def _save_email(email: str) -> None:
    try:
        from voice_flow.storage import StorageEngine

        StorageEngine().save_setting("video_flow_notebooklm_email", email)
    except Exception:
        pass


def _is_placeholder(email: str | None) -> bool:
    """True for display placeholders ("your Google account") that must never be persisted."""
    try:
        from .config import is_placeholder_email

        return is_placeholder_email(email)
    except Exception:
        return str(email or "").strip().lower() in {"your google account"}


def _profile_browser_dir(profile: str) -> Path:
    """The profile's persistent Playwright browser directory (the CLI's own
    sign-in browser profile). Holds the remembered Google accounts."""
    return get_profile_dir(profile) / "browser_profile"


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
                name = (proc.info.get("name") or "").casefold()
                if name not in ("chrome.exe", "msedge.exe", "chromium.exe"):
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
    for hwnd, pid, _title, _class_name in _visible_top_level_windows():
        if pid in owned_pids:
            return _bring_hwnd_forward(hwnd)
    return False


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
    threading.Thread(
        target=_handoff_login_windows,
        args=(profile, cli_pid, initial_hwnds, stop_event, credential_watch_seconds),
        name="notebooklm-login-window-handoff",
        daemon=True,
    ).start()


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
                name = (proc.info.get("name") or "").casefold()
                if name in ("chrome.exe", "msedge.exe", "chromium.exe"):
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
        b_dir = _profile_browser_dir(profile)
        for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"):
            lock_p = b_dir / lock_name
            if lock_p.exists():
                lock_p.unlink(missing_ok=True)
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
    for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"):
        lock_p = browser_dir / lock_name
        if lock_p.exists():
            try:
                lock_p.unlink(missing_ok=True)
            except Exception:
                pass

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


def _run_login_once(
    command: list[str],
    log_path: Path,
    timeout_seconds: int,
) -> tuple[int, str]:
    """Run one login attempt, streaming CLI output into the log file."""
    env = dict(os.environ)
    with log_path.open("a", encoding="utf-8") as log_handle:
        log_handle.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] $ {_redact_command_for_log(command)}\n")
        log_handle.flush()
        process: subprocess.Popen[Any] | None = None
        handoff_stop_event: threading.Event | None = None
        # A Windows Security dialog can appear almost immediately after browser
        # launch. Snapshot before Popen so the watcher can identify it as new.
        prelaunch_hwnds: set[int] | None = None
        if "login" in command:
            prelaunch_hwnds = {hwnd for hwnd, *_rest in _visible_top_level_windows()}
        try:
            process = subprocess.Popen(
                command,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
                creationflags=_HIDE_FLAGS,
            )
            # The CLI owns browser startup.  This tiny daemon only requests
            # foreground once when its exact profile window appears; waiting
            # for the CLI remains in this background login worker.
            if "login" in command:
                handoff_stop_event = threading.Event()
                _start_login_foreground_handoff(
                    command,
                    getattr(process, "pid", None),
                    prelaunch_hwnds,
                    handoff_stop_event,
                    min(_LOGIN_MAX_CREDENTIAL_WATCH_SECONDS, max(0.0, float(timeout_seconds))),
                )
            wait_timeout = max(60, int(timeout_seconds)) if "login" in command else max(8, int(timeout_seconds))
            return process.wait(timeout=wait_timeout), ""
        except subprocess.TimeoutExpired:
            if process is not None:
                try:
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
                    process.kill()
                    process.wait(timeout=5)
                except Exception:
                    logger.warning("Timed-out NotebookLM CLI could not be reaped", exc_info=True)
            return 124, f"sign-in timed out after {timeout_seconds}s"
        except OSError:
            logger.warning("NotebookLM CLI could not launch the requested browser", exc_info=True)
            return 1, "Could not launch the NotebookLM sign-in browser. Check that the selected browser is installed."
        finally:
            if handoff_stop_event is not None:
                handoff_stop_event.set()


def _watch_login(
    profile: str,
    mode: str,
    account_email: str | None,
    browser: str,
    browser_timeout: int,
    log_path: Path,
    switch_account: bool = False,
    fresh_login: bool = False,
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
        _set_note("Google NotebookLM sign-in is opening — finish the sign-in there.")
        _terminate_stale_login_processes(profile, log_path)
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

        # In a pytest test run where _run_login_once is not explicitly mocked, avoid launching real GUI browsers
        if os.environ.get("PYTEST_CURRENT_TEST") and getattr(_run_login_once, "__name__", "") in ("_run_login_once", ""):
            return

        if mode == "master-token" and account_email:
            force = bool(switch_account or (_storage_email() and account_email != _storage_email()))
            code, err = _run_login_once(
                _login_command(
                    cli_path, profile, mode="master-token",
                    account_email=account_email, browser=browser,
                    browser_timeout=browser_timeout, force=force,
                    switch_account=switch_account,
                    fresh_login=fresh_login,
                ),
                log_path,
                browser_timeout,
            )
        else:
            code, err = _run_login_once(
                _login_command(
                    cli_path, profile, mode="browser",
                    account_email=None, browser=browser,
                    browser_timeout=browser_timeout,
                    switch_account=switch_account,
                    fresh_login=fresh_login,
                ),
                log_path,
                browser_timeout,
            )
        success = code == 0
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

            try:
                verified = verify_online(profile=profile, force=True, timeout=15.0)
                if verified.get("authenticated"):
                    email = verified.get("email") or email
                else:
                    success = False
                    err = str(verified.get("message") or "Google could not verify the new session online")
            except Exception as exc:
                success = False
                logger.warning("Post-sign-in verification failed", exc_info=True)
                err = "Google could not verify the new session online. Check your connection and try again."

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

        note = None
        if success and mode == "master-token" and not durable:
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
            )


def record_successful_login(email: str, profile: str | None = None) -> None:
    """Record a browser-flow login only after the CLI verifies it online."""
    profile = resolve_notebooklm_profile(profile)
    note_session_refreshed(profile)
    verification = verify_online(profile=profile, force=True, timeout=15.0)
    if not verification.get("authenticated"):
        with _STATE_LOCK:
            _STATE.update(
                running=False,
                finished_at=time.time(),
                success=False,
                error=str(verification.get("message") or "Google could not verify the new session online"),
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
        with _STATE_LOCK:
            if _STATE.get("running"):
                if switch_account:
                    _STATE["running"] = False
                else:
                    return {"launched": False, "already_running": True, "state": get_login_state()}
            log_path = _login_log_path()
            _STATE.update(
                running=True,
                mode=run_mode,
                started_at=time.time(),
                finished_at=None,
                success=None,
                error=None,
                note=(
                    "Google NotebookLM account chooser is opening in browser — choose an account."
                    if switch_account
                    else (
                        "Google NotebookLM sign-in is opening — finish sign-in to establish this session."
                        if run_mode == "master-token"
                        else "Google NotebookLM sign-in is opening — finish the sign-in there."
                    )
                ),
                durable=None,
                log_path=str(log_path),
            )
        thread = threading.Thread(
            target=_watch_login,
            args=(profile, run_mode, account_email, browser, int(browser_timeout), log_path, switch_account, fresh_login),
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


def verify_online(
    *,
    profile: str | None = None,
    timeout: float = _ONLINE_CHECK_TIMEOUT_SECONDS,
    force: bool = False,
) -> dict[str, Any]:
    """Online Google session verification via ``notebooklm auth check --test``.

    Cached briefly so dashboard polling never hammers accounts.google.com.
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
    command = [str(cli_path), "--profile", profile, "auth", "check", "--test", "--passive", "--json"]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(8.0, float(timeout)),
            creationflags=_HIDE_FLAGS,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
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
        try:
            from voice_flow.storage import storage
            storage.save_setting("video_flow_notebooklm_authenticated", False)
            storage.save_setting("video_flow_notebooklm_auth_error", "Google session is no longer valid — sign in again")
        except Exception:
            pass
        try:
            from voice_flow.gui import api_server
            api_server.storage.save_setting("video_flow_notebooklm_authenticated", False)
            api_server.storage.save_setting("video_flow_notebooklm_auth_error", "Google session is no longer valid — sign in again")
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
        "authenticated": authenticated if not transient_failure else None,
        "definitive": bool(authenticated or not transient_failure),
        "failure_kind": None if authenticated else ("network" if is_network_error else ("auth" if is_definite_auth_error else "cli")),
        "message": "Google session verified online" if authenticated else (
            "Could not reach Google to verify this saved session" if transient_failure
            else "Google session is no longer valid — sign in again"
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

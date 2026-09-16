"""NotebookLM sign-in orchestration for the Video Flow GUI (v6, rebuilt).

What changed and why: the previous system launched OUR OWN Chrome with a CDP
debug port, attached a Playwright driver, and tried to scrape Google's
single-use ``oauth_token`` cookie ourselves. On this machine that design failed
in every way it can fail — Chrome singleton races killed the window mid-launch,
the debugged browser died with TargetClosedError storms, and Google refused to
issue the token inside a debugging-enabled browser (the user saw a stuck blue
page). Every attempt then silently fell back to the cookies-only plain login,
and cookies alone are rotated server-side within hours — which is exactly why
sign-in was needed over and over.

The v6 design has exactly one moving part: the NotebookLM CLI's own login.

- ``login --master-token --account E`` opens ONE window at Google's official
  EmbeddedSetup flow (real Chrome channel, automation markers stripped by the
  CLI), waits for the user to sign in once, captures the single-use
  oauth_token itself, and mints the durable ``aas_et/`` master token. After
  that one sign-in, sessions are re-minted headlessly forever — no more logins.
- Self-heal is headless: ``login --master-token-refresh`` re-mints web cookies
  from the stored master token, and ``auth refresh --allow-headless`` recovers
  from the profile's live browser session. Neither opens a window.
- Plain ``login`` (cookies-only) stays as the last-resort fallback so the user
  is never left signed out.

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
_ONLINE_CACHE: dict[str, Any] = {"checked_at": 0.0, "result": None}


def _master_token_json_path(profile: str | None = None) -> Path:
    """Durable aas_et/ master token record stored beside storage_state.json."""
    from .config import get_storage_state_path
    return get_storage_state_path(profile).with_name("master_token.json")


def master_token_present(profile: str | None = None) -> bool:
    """True once the one-time sign-in minted the durable master token.

    While this is False, every sign-in only stores browser cookies that Google
    rotates server-side within hours — which is why re-login kept being needed.
    """
    try:
        return _master_token_json_path(profile).is_file()
    except Exception:
        return False


def self_heal(*, profile: str | None = None, timeout: int = 240) -> dict[str, Any]:
    """Headless login repair — no window, no prompt.

    With a stored master token: ``login --master-token-refresh`` re-mints web
    cookies from the durable token (the normal self-heal path). Without one:
    ``auth refresh --verify --allow-headless`` runs the CLI's recovery layers
    (token rotation, then layer-3 recovery from the profile browser's live
    Google session). This is what keeps the user signed in between renders.
    """
    profile = resolve_notebooklm_profile(profile)
    cli_path = resolve_notebooklm_cli()
    if cli_path is None:
        try:
            from .browser_sync import auto_sync_from_browser

            sync_res = auto_sync_from_browser(profile=profile)
            if sync_res.get("success"):
                return {"ok": True, "error": None, "profile": profile, "healed_via": "browser_sync"}
        except Exception:
            pass
        allow_pw = not os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("VOICE_FLOW_TEST_PLAYWRIGHT_HEAL")
        if allow_pw:
            try:
                from .browser_sync import sync_cookies_with_playwright

                pw_sync = sync_cookies_with_playwright(profile=profile, headless=True, timeout_seconds=35)
                if pw_sync.get("success"):
                    return {"ok": True, "error": None, "profile": profile, "healed_via": "playwright_sync"}
            except Exception:
                pass
        return {"ok": False, "error": "cli_missing", "profile": profile}
    has_master = _master_token_json_path(profile).is_file()
    if has_master:
        command = [str(cli_path), "--profile", profile, "login", "--master-token-refresh"]
    else:
        command = [
            str(cli_path), "--profile", profile,
            "auth", "refresh", "--verify", "--allow-headless",
        ]
    log_path = _login_log_path()
    try:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] [self-heal: refreshing the session without a window]\n"
            )
        code, err = _run_login_once(command, log_path, timeout)
        if code != 0 and has_master:
            fallback_cmd = [
                str(cli_path), "--profile", profile,
                "auth", "refresh", "--verify", "--allow-headless",
            ]
            code, err = _run_login_once(fallback_cmd, log_path, timeout)
        if code != 0:
            try:
                from .browser_sync import auto_sync_from_browser

                sync_res = auto_sync_from_browser(profile=profile)
                if sync_res.get("success"):
                    code = 0
                    err = ""
            except Exception:
                pass
        allow_pw = not os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("VOICE_FLOW_TEST_PLAYWRIGHT_HEAL")
        if code != 0 and allow_pw:
            try:
                from .browser_sync import sync_cookies_with_playwright

                pw_sync = sync_cookies_with_playwright(profile=profile, headless=True, timeout_seconds=35)
                if pw_sync.get("success"):
                    code = 0
                    err = ""
            except Exception:
                pass
    except Exception as exc:
        try:
            from .browser_sync import auto_sync_from_browser

            sync_res = auto_sync_from_browser(profile=profile)
            if sync_res.get("success"):
                return {"ok": True, "error": None, "profile": profile, "healed_via": "browser_sync"}
        except Exception:
            pass
        allow_pw = not os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("VOICE_FLOW_TEST_PLAYWRIGHT_HEAL")
        if allow_pw:
            try:
                from .browser_sync import sync_cookies_with_playwright

                pw_sync = sync_cookies_with_playwright(profile=profile, headless=True, timeout_seconds=35)
                if pw_sync.get("success"):
                    return {"ok": True, "error": None, "profile": profile, "healed_via": "playwright_sync"}
            except Exception:
                pass
        return {"ok": False, "error": str(exc)[:200], "profile": profile}
    if code == 0:
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
                    except Exception:
                        pass
            else:
                logger.warning(
                    "self-heal: %s missing or empty after refresh; keeping existing backup/safe_copy untouched", st
                )
        except Exception:
            pass
    return {"ok": code == 0, "error": None if code == 0 else (err or f"exit {code}"), "profile": profile}


def ensure_fresh_session(
    *,
    profile: str | None = None,
    force: bool = False,
    max_age_seconds: float = 86400.0,
) -> dict[str, Any]:
    """Ensure the profile's Google session cookies are valid and not nearing expiration.

    Inspects timestamped cookies (__Secure-1PSIDTS). If missing, expired, or nearing
    the 2-3 day Google expiration window, runs headless self_heal (via master-token
    or live session) so the session never drops unexpectedly.
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


def _storage_email() -> str | None:
    try:
        from voice_flow.storage import StorageEngine

        email = str(StorageEngine().get_setting("video_flow_notebooklm_email") or "").strip()
        return email or None
    except Exception:
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
    """True if cmdline matches the profile marker or a --user-data-dir for this profile."""
    if marker_norm in cmdline_norm:
        return True
    if "--user-data-dir=" in cmdline_norm:
        prof_cf = profile_name.casefold()
        for part in cmdline_norm.split():
            if "--user-data-dir=" in part:
                udd_val = part.split("--user-data-dir=", 1)[1].strip('"\'')
                udd_norm = udd_val.replace("\\", "/").casefold()
                segments = [s for s in udd_norm.split("/") if s]
                if (
                    prof_cf in segments
                    or f"/profiles/{prof_cf}" in udd_norm
                    or f"/{prof_cf}/browser_profile" in udd_norm
                ):
                    return True
    return False


def _terminate_stale_login_processes(profile: str, log_path: Path | str | None = None) -> int:
    """Kill leftover browsers from a previous sign-in still holding the
    profile's browser directory — a wedged SingletonLock would block every
    future sign-in window. Only processes whose command line carries OUR
    browser_profile path are touched; the user's daily browser is never
    matched."""
    killed = 0
    raw_marker = str(_profile_browser_dir(profile))
    marker = raw_marker.replace("\\", "/").casefold()
    prof_cf = profile.casefold()
    if os.name == "nt":
        script = (
            f"$marker = '{marker}'.ToLower(); "
            f"$prof = '{prof_cf}'.ToLower(); "
            "Get-CimInstance Win32_Process | "
            "Where-Object { ($_.Name -match 'chrome|msedge|chromium') -and ($_.CommandLine -and "
            "(($_.CommandLine.Replace('\\', '/').ToLower().Contains($marker)) -or "
            "($_.CommandLine.ToLower().Contains('--user-data-dir=') -and "
            "($_.CommandLine.Replace('\\', '/').ToLower() -match ('[\\/](profiles[\\/])?' + [regex]::Escape($prof) + '([\\/]|$|browser_profile)'))))) } | "
            "Select-Object -ExpandProperty ProcessId"
        )
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res and getattr(res, "returncode", 1) == 0 and getattr(res, "stdout", ""):
                for line in str(res.stdout).strip().splitlines():
                    pid = line.strip()
                    if pid.isdigit():
                        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=5)
                        killed += 1
        except Exception:
            pass

    # Also clean with psutil for direct robust termination
    try:
        import psutil
        my_pid = os.getpid()
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.info["pid"] == my_pid:
                    continue
                name = (proc.info.get("name") or "").casefold()
                if name in ("chrome.exe", "msedge.exe", "chromium.exe"):
                    cmdline_norm = " ".join(proc.info.get("cmdline") or []).replace("\\", "/").casefold()
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
) -> list[str]:
    command = [
        str(cli_path),
        "--profile", profile,
        "login",
        "--browser", browser,
        "--browser-timeout", str(max(60, int(browser_timeout))),
    ]
    if switch_account:
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
        try:
            result = subprocess.run(
                command,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                timeout=max(60, int(timeout_seconds)),
                env=env,
                creationflags=_HIDE_FLAGS,
            )
            return result.returncode, ""
        except subprocess.TimeoutExpired:
            return 124, f"sign-in timed out after {timeout_seconds}s"
        except OSError as exc:
            return 1, str(exc)[:300]


def _watch_login(
    profile: str,
    mode: str,
    account_email: str | None,
    browser: str,
    browser_timeout: int,
    log_path: Path,
    switch_account: bool = False,
) -> None:
    """Run the sign-in chain in the background.

    One window, owned by the CLI. Master-token mode first (durable); the plain
    cookies login runs only as a last resort so the user is never signed out.
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
                ),
                log_path,
                browser_timeout,
            )
            if code != 0:
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(
                        f"[one-time durable sign-in did not finish (exit {code}); "
                        "falling back to a plain browser login so you are still signed in]\n"
                    )
                _set_note("Opening sign-in window to restore your session…")
                code, err = _run_login_once(
                    _login_command(
                        cli_path, profile, mode="browser",
                        account_email=None, browser=browser,
                        browser_timeout=browser_timeout,
                        switch_account=switch_account,
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
                ),
                log_path,
                browser_timeout,
            )
            if code != 0 and browser != "chromium":
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(
                        f"[browser '{browser}' exited with code {code}; trying bundled chromium...]\n"
                    )
                code, err = _run_login_once(
                    _login_command(
                        cli_path, profile, mode="browser",
                        account_email=None, browser="chromium",
                        browser_timeout=browser_timeout,
                        switch_account=switch_account,
                    ),
                    log_path,
                    browser_timeout,
                )
        success = code == 0
        if success:
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
            except Exception:
                logger.debug("post-sign-in verification failed", exc_info=True)

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
        elif not success and err:
            note = err

        with _STATE_LOCK:
            _STATE.update(
                running=False,
                finished_at=time.time(),
                success=success,
                durable=durable,
                error=None if success else (err or f"sign-in exited with code {code}"),
                email=email if (success and not _is_placeholder(email)) else None,
                note=note,
            )
            if success:
                _ONLINE_CACHE.update(
                    checked_at=time.time(),
                    result={
                        "status": "ok",
                        "authenticated": True,
                        "message": "Google session verified",
                        "email": email if not _is_placeholder(email) else None,
                        "profile": profile,
                        "master_token_present": durable,
                    },
                )
        logger.info("NotebookLM %s login finished: success=%s durable=%s", mode, success, durable)
    except Exception as exc:  # defensive: watcher must never die silently
        logger.exception("NotebookLM login watcher failed")
        with _STATE_LOCK:
            _STATE.update(running=False, finished_at=time.time(), success=False, error=str(exc)[:300], note=None)


def record_successful_login(email: str, profile: str | None = None) -> None:
    """Record a successful login from the system default browser flow."""
    profile = resolve_notebooklm_profile(profile)
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
        _ONLINE_CACHE.update(
            checked_at=time.time(),
            result={
                "status": "ok",
                "authenticated": True,
                "message": "Google session verified",
                "email": display_email,
                "profile": profile,
                "master_token_present": durable,
            },
        )
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


def disconnect_login(profile: str | None = None) -> dict[str, Any]:
    """Disconnect the NotebookLM session and mark unauthenticated."""
    profile = resolve_notebooklm_profile(profile)
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
        _ONLINE_CACHE.update(
            checked_at=time.time(),
            result={
                "status": "unauthenticated",
                "authenticated": False,
                "message": "Disconnected",
                "email": None,
                "profile": profile,
                "master_token_present": False,
            },
        )
    return {"success": True, "authenticated": False, "profile": profile}


def start_login(
    *,
    profile: str | None = None,
    account_email: str | None = None,
    mode: str | None = None,
    browser: str = "chrome",
    browser_timeout: int = _LOGIN_TIMEOUT_SECONDS,
    switch_account: bool = False,
    port: int | None = None,
    direct: bool = True,
    cookie_payload: Any = None,
) -> dict[str, Any]:
    """Launch NotebookLM Google sign-in in the user's SYSTEM DEFAULT browser or CLI.

    Default browser mode opens Google's account chooser in the default browser where the user's
    existing Google sessions live.
    Master-token / legacy-cli mode runs the CLI-owned watcher thread.
    """
    if os.environ.get("VOICE_FLOW_LOGIN_DISABLE"):
        # Test/CI contexts must never open real browsers (pytest conftest sets this).
        return {"launched": False, "error": "Interactive sign-in is disabled in this environment"}

    profile = resolve_notebooklm_profile(profile)

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

    cli_path = resolve_notebooklm_cli()
    if cli_path is None and mode not in ("browser", "system-browser"):
        return {"launched": False, "error": "NotebookLM CLI not found — cannot start sign-in"}

    if mode in ("master-token", "legacy-cli", "cli", "interactive", "playwright"):
        if switch_account:
            account_email = account_email.strip() if account_email else None
        else:
            account_email = (account_email or _storage_email() or "").strip() or None
        run_mode = "master-token" if (mode == "master-token" and account_email) else "browser"
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
                    else "Google NotebookLM sign-in is opening — finish the sign-in there."
                ),
                durable=None,
                log_path=str(log_path),
            )
        thread = threading.Thread(
            target=_watch_login,
            args=(profile, run_mode, account_email, browser, int(browser_timeout), log_path, switch_account),
            name="notebooklm-login",
            daemon=True,
        )
        thread.start()
        logger.info("NotebookLM %s login launched (profile=%s, browser=%s)", run_mode, profile, browser)
        msg = (
            "One-time sign-in window launched — sign in once to Google NotebookLM and Voice Flow remembers it forever."
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


def verify_online(
    *,
    profile: str | None = None,
    timeout: float = _ONLINE_CHECK_TIMEOUT_SECONDS,
    force: bool = False,
) -> dict[str, Any]:
    """Online Google session verification via ``notebooklm auth check --test``.

    Cached briefly so dashboard polling never hammers accounts.google.com.
    """
    with _STATE_LOCK:
        cached = _ONLINE_CACHE.get("result")
        if cached and not force and (time.time() - float(_ONLINE_CACHE.get("checked_at") or 0)) < _ONLINE_CACHE_SECONDS:
            return dict(cached)

    cli_path = resolve_notebooklm_cli()
    if cli_path is None:
        return {"status": "dependency_missing", "authenticated": False,
                "message": "NotebookLM CLI not found"}
    profile = resolve_notebooklm_profile(profile)
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
        payload = json.loads(result.stdout or "{}")
    except Exception as exc:
        verified = {"status": "error", "authenticated": False,
                    "message": f"Online verification failed: {exc}", "profile": profile}
        with _STATE_LOCK:
            _ONLINE_CACHE.update(checked_at=time.time() - (_ONLINE_CACHE_SECONDS - 5.0), result=verified)
        return dict(verified)

    authenticated = str(payload.get("status") or "").casefold() == "ok"
    if not authenticated and (master_token_present(profile) or not os.environ.get("PYTEST_CURRENT_TEST")):
        try:
            # Fast-path refresh: run CLI headless token refresh directly (takes ~6s)
            refresh_cmd = [str(cli_path), "--profile", profile, "auth", "refresh", "--verify", "--allow-headless"]
            ref_res = subprocess.run(
                refresh_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=12.0,
                creationflags=_HIDE_FLAGS,
            )
            if ref_res.returncode == 0:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=8.0,
                    creationflags=_HIDE_FLAGS,
                )
                payload = json.loads(result.stdout or "{}")
                authenticated = str(payload.get("status") or "").casefold() == "ok"
            else:
                heal = self_heal(profile=profile, timeout=15)
                if heal.get("ok"):
                    result = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=8.0,
                        creationflags=_HIDE_FLAGS,
                    )
                    payload = json.loads(result.stdout or "{}")
                    authenticated = str(payload.get("status") or "").casefold() == "ok"
        except Exception:
            pass

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
        except Exception:
            pass
        try:
            from voice_flow.gui import api_server
            api_server.storage.save_setting("video_flow_notebooklm_email", email)
            api_server.storage.save_setting("video_flow_notebooklm_authenticated", True)
            api_server.storage.save_setting("video_flow_notebooklm_disconnected", False)
            api_server.storage.save_setting("video_flow_notebooklm_switched_from", "")
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

    verified = {
        "status": "ok" if authenticated else "error",
        "authenticated": authenticated,
        "message": "Google session verified online" if authenticated else "Google session is no longer valid — sign in again",
        "email": email,
        "profile": profile,
        "master_token_present": bool(master.get("present")),
        "details_message": str(payload.get("message") or payload.get("error") or "")[:300],
    }
    with _STATE_LOCK:
        cache_ts = time.time() if authenticated else (time.time() - (_ONLINE_CACHE_SECONDS - 10.0))
        _ONLINE_CACHE.update(checked_at=cache_ts, result=verified)
    return dict(verified)

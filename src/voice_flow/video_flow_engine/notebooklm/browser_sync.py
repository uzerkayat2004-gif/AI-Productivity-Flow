"""Browser cookie extraction and synchronization for Google NotebookLM.

Extracts real Google session cookies (__Secure-1PSID, __Secure-1PSIDTS, SID, SAPISID, etc.)
from the user's default browser (Chrome / Edge / Chromium / Brave) into Playwright storage_state.json
so NotebookLM CLI and MCP server can authenticate seamlessly without repeated manual logins.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import config


def get_profile_dir(profile: str | None = None) -> Path:
    return config.get_profile_dir(profile)


def get_storage_backup_path(profile: str | None = None) -> Path:
    return config.get_storage_backup_path(profile)


def get_storage_state_path(profile: str | None = None) -> Path:
    return config.get_storage_state_path(profile)


def resolve_notebooklm_profile(profile: str | None = None) -> str:
    return config.resolve_notebooklm_profile(profile)


logger = logging.getLogger(__name__)


def _atomic_write_text(target: Path, content: str) -> None:
    """Write via temp file + os.replace so a concurrent reader never sees a torn file.

    Local helper (mirrors provider.py pattern) to avoid a provider import cycle.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_name, str(target))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

# Required Google session cookies for NotebookLM
REQUIRED_SESSION_COOKIE_NAMES = ("__Secure-1PSID", "SID")
ALL_RELEVANT_COOKIE_NAMES = (
    "__Secure-1PSID",
    "__Secure-1PSIDTS",
    "__Secure-3PSID",
    "__Secure-3PSIDTS",
    "SID",
    "HSID",
    "SSID",
    "APISID",
    "SAPISID",
    "OSID",
    "SNID",
    "NID",
)

GOOGLE_DOMAINS = (
    ".google.com",
    "google.com",
    "notebooklm.google.com",
    ".notebooklm.google.com",
    "accounts.google.com",
    ".google.co.in",
    ".google.co.uk",
)


def _safe_windows_read_locked_file(path: str | Path) -> bytes | None:
    """Read a file that may be locked by another process (e.g. running browser) on Windows."""
    p_str = str(path)
    if not os.path.isfile(p_str):
        return None

    try:
        with open(p_str, "rb") as f:
            return f.read()
    except (PermissionError, OSError):
        pass

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        GENERIC_READ = 0x80000000
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        OPEN_EXISTING = 3

        handle = kernel32.CreateFileW(
            p_str,
            GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if handle == -1 or handle == 0xFFFFFFFFFFFFFFFF:
            logger.debug("Failed opening locked file %s: error %s", p_str, ctypes.get_last_error())
            return None
        try:
            size = kernel32.GetFileSize(handle, None)
            if size <= 0:
                return b""
            buf = ctypes.create_string_buffer(size)
            bytes_read = wintypes.DWORD()
            success = kernel32.ReadFile(handle, buf, size, ctypes.byref(bytes_read), None)
            if not success:
                logger.debug("Failed reading locked file %s: error %s", p_str, ctypes.get_last_error())
                return None
            return buf.raw[: bytes_read.value]
        finally:
            kernel32.CloseHandle(handle)
    return None


def discover_browser_user_data_dirs() -> dict[str, Path]:
    """Locate Chromium-based browser User Data directories on the system."""
    dirs: dict[str, Path] = {}
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
        candidates = {
            "chrome": base / "Google" / "Chrome" / "User Data",
            "edge": base / "Microsoft" / "Edge" / "User Data",
            "brave": base / "BraveSoftware" / "Brave-Browser" / "User Data",
            "chromium": base / "Chromium" / "User Data",
        }
        for name, p in candidates.items():
            if p.is_dir():
                dirs[name] = p
    return dirs


def discover_browser_profiles(browser_name: str | None = None) -> list[dict[str, Any]]:
    """Enumerate existing profiles (Default, Profile 1, etc.) for installed browsers."""
    user_data_dirs = discover_browser_user_data_dirs()
    if browser_name:
        b_key = browser_name.strip().lower()
        if b_key in user_data_dirs:
            user_data_dirs = {b_key: user_data_dirs[b_key]}

    profiles: list[dict[str, Any]] = []
    for b_name, b_path in user_data_dirs.items():
        local_state_path = b_path / "Local State"
        info_cache: dict[str, Any] = {}
        if local_state_path.is_file():
            try:
                raw_ls = _safe_windows_read_locked_file(local_state_path)
                if raw_ls:
                    ls_data = json.loads(raw_ls.decode("utf-8", errors="replace"))
                    info_cache = (
                        (ls_data.get("profile") or {}).get("info_cache")
                        or {}
                    )
            except Exception:
                pass

        # Find profile directories
        subdirs = [b_path / "Default"] + list(b_path.glob("Profile *"))
        for sdir in subdirs:
            if not sdir.is_dir():
                continue
            dir_name = sdir.name
            meta = info_cache.get(dir_name, {}) if isinstance(info_cache, dict) else {}
            human_name = meta.get("name") or dir_name
            user_name = meta.get("user_name") or meta.get("email") or ""
            cookie_file = sdir / "Network" / "Cookies"
            if not cookie_file.is_file():
                cookie_file = sdir / "Cookies"

            profiles.append({
                "browser": b_name,
                "profile_dir": dir_name,
                "path": str(sdir),
                "cookie_file": str(cookie_file) if cookie_file.is_file() else None,
                "human_name": human_name,
                "email": user_name,
            })

    return profiles


def _decrypt_v10_cookie_value(enc_val: bytes, master_key: bytes) -> str | None:
    """Decrypt Chrome/Edge v10 AES-GCM encrypted cookie bytes."""
    if not enc_val or len(enc_val) < 31:
        return None
    try:
        from Cryptodome.Cipher import AES  # type: ignore

        nonce = enc_val[3:15]
        ciphertext = enc_val[15:-16]
        tag = enc_val[-16:]
        cipher = AES.new(master_key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
        return plaintext.decode("utf-8", errors="replace")
    except Exception:
        pass

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore

        nonce = enc_val[3:15]
        ct = enc_val[15:]
        aesgcm = AESGCM(master_key)
        plaintext = aesgcm.decrypt(nonce, ct, None)
        return plaintext.decode("utf-8", errors="replace")
    except Exception:
        pass

    return None


def _get_browser_master_key(user_data_dir: Path) -> bytes | None:
    """Extract and decrypt DPAPI master key from Local State."""
    local_state_path = user_data_dir / "Local State"
    if not local_state_path.is_file():
        return None
    try:
        raw = _safe_windows_read_locked_file(local_state_path)
        if not raw:
            return None
        data = json.loads(raw.decode("utf-8", errors="replace"))
        encrypted_key_b64 = data.get("os_crypt", {}).get("encrypted_key")
        if not encrypted_key_b64:
            return None
        encrypted_key = base64.b64decode(encrypted_key_b64)
        if encrypted_key.startswith(b"DPAPI"):
            encrypted_key = encrypted_key[5:]
        import win32crypt  # type: ignore

        decrypted = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        return decrypted
    except Exception as exc:
        logger.debug("Failed getting master key from %s: %s", user_data_dir, exc)
        return None


def extract_cookies_from_sqlite(
    cookie_db_path: str | Path,
    user_data_dir: Path,
) -> list[dict[str, Any]]:
    """Extract and decrypt Google cookies from a Chromium Cookies SQLite database."""
    raw_db = _safe_windows_read_locked_file(cookie_db_path)
    if not raw_db:
        return []

    master_key = _get_browser_master_key(user_data_dir)

    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite")
    try:
        temp_db.write(raw_db)
        temp_db.close()

        conn = sqlite3.connect(temp_db.name)
        cur = conn.cursor()
        query = (
            "SELECT host_key, name, path, encrypted_value, value, expires_utc, is_secure, is_httponly, samesite "
            "FROM cookies WHERE host_key LIKE '%google%' AND name IN "
            "('SID', '__Secure-1PSID', '__Secure-1PSIDTS', '__Secure-3PSID', '__Secure-3PSIDTS', 'SAPISID', 'HSID', 'SSID', 'APISID', 'OSID', 'LSID')"
        )
        cur.execute(query)
        rows = cur.fetchall()
        conn.close()
    except Exception as exc:
        logger.debug("Error querying cookie DB %s: %s", cookie_db_path, exc)
        return []
    finally:
        try:
            os.unlink(temp_db.name)
        except OSError:
            pass

    results: list[dict[str, Any]] = []
    v20_detected = False
    for host_key, name, path, enc_val, val, expires_utc, is_secure, is_httponly, samesite in rows:
        cookie_val = str(val or "")
        if not cookie_val and enc_val:
            prefix = bytes(enc_val[:3])
            if prefix == b"v20":
                v20_detected = True
            elif prefix in (b"v10", b"v11") and master_key:
                decrypted = _decrypt_v10_cookie_value(bytes(enc_val), master_key)
                if decrypted:
                    cookie_val = decrypted

        if not cookie_val:
            continue

        # Convert Chromium microseconds timestamp (from 1601-01-01) to UNIX seconds
        expires_sec = -1.0
        if expires_utc and int(expires_utc) > 0:
            try:
                expires_sec = (int(expires_utc) - 11644473600000000) / 1000000.0
            except (ValueError, OverflowError):
                expires_sec = -1.0

        same_site_map = {0: "None", 1: "Lax", 2: "Strict"}
        same_site_str = same_site_map.get(samesite, "None")

        results.append({
            "name": str(name),
            "value": cookie_val,
            "domain": str(host_key),
            "path": str(path or "/"),
            "expires": expires_sec,
            "httpOnly": bool(is_httponly),
            "secure": bool(is_secure),
            "sameSite": same_site_str,
        })

    if v20_detected and not results:
        logger.info(
            "Encountered Chrome 127+ App-Bound Encryption (v20) cookies in %s; "
            "cannot decrypt cookies via external DPAPI outside Chrome.",
            cookie_db_path,
        )

    return results


def parse_cookie_payload(payload: Any) -> list[dict[str, Any]]:
    """Flexible parser for cookie input in various formats.

    Supports:
    - Playwright storage_state.json dict {"cookies": [...], "origins": [...]}
    - List of cookie dicts [{"name": "...", "value": "..."}, ...]
    - Cookie header string "__Secure-1PSID=xyz; __Secure-1PSIDTS=abc; SID=..."
    - JSON string representation of any of the above
    - Netscape format text
    """
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return []
        if text.startswith("{") or text.startswith("["):
            try:
                data = json.loads(text)
                return parse_cookie_payload(data)
            except json.JSONDecodeError:
                pass

        # Try parsing as Cookie header string: Name1=Value1; Name2=Value2
        if "=" in text:
            extracted: list[dict[str, Any]] = []
            parts = [p.strip() for p in text.split(";") if p.strip()]
            for part in parts:
                if "=" not in part:
                    continue
                k, _, v = part.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and v:
                    extracted.append({
                        "name": k,
                        "value": v,
                        "domain": ".google.com",
                        "path": "/",
                        "expires": time.time() + 86400 * 30,
                        "httpOnly": k.startswith("__Secure-") or k in ("SID", "HSID", "SSID"),
                        "secure": k.startswith("__Secure-") or k in ("SAPISID",),
                        "sameSite": "None",
                    })
            if extracted:
                return extracted

    if isinstance(payload, Mapping):
        if isinstance(payload.get("cookies"), Sequence):
            return parse_cookie_payload(payload["cookies"])
        return []

    if isinstance(payload, Sequence):
        cookies: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("name") or "").strip()
            val = str(item.get("value") or "").strip()
            if not name or not val:
                continue
            dom = str(item.get("domain") or item.get("host") or ".google.com").strip()
            if not dom.startswith(".") and "google" in dom and not dom.startswith("notebooklm"):
                dom = "." + dom
            path = str(item.get("path") or "/")
            expires = item.get("expires", item.get("expirationDate", -1))
            try:
                expires_val = float(expires) if expires is not None else -1.0
            except (ValueError, TypeError):
                expires_val = -1.0

            http_only = bool(item.get("httpOnly", item.get("http_only", False)))
            secure = bool(item.get("secure", name.startswith("__Secure-")))
            same_site = str(item.get("sameSite", item.get("same_site", "None")))

            cookies.append({
                "name": name,
                "value": val,
                "domain": dom,
                "path": path,
                "expires": expires_val,
                "httpOnly": http_only,
                "secure": secure,
                "sameSite": same_site,
            })
        return cookies

    return []


def validate_extracted_cookies(cookies: list[dict[str, Any]]) -> tuple[bool, str, dict[str, Any]]:
    """Verify that extracted cookies satisfy Google NotebookLM requirements."""
    if not cookies or not isinstance(cookies, list):
        return False, "No cookies provided", {}

    cookie_map: dict[str, str] = {}
    for c in cookies:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        val = str(c.get("value") or "").strip()
        if name and val:
            cookie_map[name] = val

    # Verify that required session cookies (__Secure-1PSID and SID) are present and non-empty
    missing = [req for req in REQUIRED_SESSION_COOKIE_NAMES if not cookie_map.get(req)]
    if missing:
        return False, f"Missing required cookies: {', '.join(missing)}", {
            "cookies_found": sorted(cookie_map.keys()),
            "missing_cookies": missing,
        }

    now = time.time()
    for c in cookies:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        if name in REQUIRED_SESSION_COOKIE_NAMES:
            expires = c.get("expires")
            if expires is not None:
                try:
                    exp_ts = float(expires)
                    if 0 < exp_ts <= now:
                        return False, f"Session cookie {name} is expired", {
                            "cookies_found": sorted(cookie_map.keys()),
                            "expired_cookie": name,
                        }
                except (ValueError, TypeError):
                    pass

    # PSIDTS-only issues are a warning, not a failure: short-lived timestamp cookies
    # (__Secure-1PSIDTS / __Secure-3PSIDTS) rotate frequently and must not invalidate
    # auth while the core SID / __Secure-1PSID session cookies are valid (mirrors the
    # keepalive predicate in config.has_valid_storage_state).
    details: dict[str, Any] = {
        "cookies_found": sorted(cookie_map.keys()),
        "has_psid": bool(cookie_map.get("__Secure-1PSID")),
        "has_sid": bool(cookie_map.get("SID")),
        "has_psidts": bool(cookie_map.get("__Secure-1PSIDTS")),
        "count": len(cookies),
    }
    for c in cookies:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        if name in ("__Secure-1PSIDTS", "__Secure-3PSIDTS"):
            expires = c.get("expires")
            try:
                exp_ts = float(expires) if expires is not None else -1.0
            except (ValueError, TypeError):
                exp_ts = -1.0
            if 0 < exp_ts <= now:
                logger.warning("Session timestamp cookie %s is expired; core SID/1PSID session still valid", name)
                details["psidts_expired"] = name
            break

    return True, "Valid Google session cookies", details


def save_cookies_to_profile(
    cookies: list[dict[str, Any]],
    profile: str | None = None,
    *,
    email: str | None = None,
) -> dict[str, Any]:
    """Persist validated cookies to storage_state.json and update application settings."""
    profile_name = resolve_notebooklm_profile(profile)
    valid, msg, details = validate_extracted_cookies(cookies)
    if not valid:
        return {"success": False, "error": msg, "details": details, "profile": profile_name}

    storage_path = get_storage_state_path(profile_name)
    backup_path = get_storage_backup_path(profile_name)

    existing_account: dict[str, Any] = {}
    if storage_path.is_file():
        try:
            old_data = json.loads(storage_path.read_text(encoding="utf-8"))
            if isinstance(old_data, dict):
                existing_account = (
                    (old_data.get("notebooklm") or {}).get("account")
                    or old_data.get("account")
                    or {}
                )
        except Exception:
            pass

    resolved_email = email or existing_account.get("email")
    if not resolved_email:
        try:
            from voice_flow.storage import storage

            resolved_email = storage.get_setting("video_flow_notebooklm_email")
        except Exception:
            pass
    if not resolved_email:
        try:
            from voice_flow.gui import api_server

            resolved_email = api_server.storage.get_setting("video_flow_notebooklm_email")
        except Exception:
            pass

    # Check switched_from: if switched_from is set and matches resolved_email, refuse to save
    switched_from = None
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

    if switched_from and resolved_email:
        s_from = str(switched_from).strip().lower()
        r_email = str(resolved_email).strip().lower()
        if s_from and r_email and s_from == r_email:
            logger.warning(
                "Refusing to save cookies in save_cookies_to_profile: resolved_email '%s' matches switched_from '%s'",
                resolved_email,
                switched_from,
            )
            return {
                "success": False,
                "error": f"Refusing to save session for switched-from account '{resolved_email}'",
                "profile": profile_name,
                "details": {**details, "switched_from": switched_from, "resolved_email": resolved_email},
            }

    state_content = {
        "cookies": cookies,
        "origins": [],
        "notebooklm": {
            "version": 1,
            "account": {
                "authuser": 0,
                "email": resolved_email or "",
            },
        },
        "account": {"email": resolved_email or ""},
    }

    storage_path.parent.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(state_content, indent=2)

    # Guarded writes: even though validate_extracted_cookies() guarantees a
    # non-empty jar here, refuse-by-construction any path that would overwrite
    # a cookie-bearing storage_state.json (or its mirrors) with 0 cookies.
    from .config import mirror_storage_state_guarded, write_storage_state_guarded

    write_res = write_storage_state_guarded(storage_path, json_text, source="browser_sync.save_cookies_to_profile")
    if not write_res.get("written"):
        return {
            "success": False,
            "error": "Refusing to overwrite the existing session with an empty cookie set.",
            "details": {**details, "guard": write_res},
            "profile": profile_name,
        }

    # Also update backup and permanent safe copy (never emptying a good mirror)
    mirror_storage_state_guarded(
        json_text,
        storage_path,
        [backup_path, storage_path.with_name("storage_state.safe_copy.json")],
        source="browser_sync.save_cookies_to_profile",
    )

    # Update app settings
    try:
        from voice_flow.storage import storage

        storage.save_setting("video_flow_notebooklm_authenticated", True)
        storage.save_setting("video_flow_notebooklm_disconnected", False)
        storage.save_setting("video_flow_notebooklm_switched_from", "")
        if resolved_email:
            storage.save_setting("video_flow_notebooklm_email", resolved_email)
    except Exception:
        pass

    try:
        from voice_flow.gui import api_server

        api_server.storage.save_setting("video_flow_notebooklm_authenticated", True)
        api_server.storage.save_setting("video_flow_notebooklm_disconnected", False)
        api_server.storage.save_setting("video_flow_notebooklm_switched_from", "")
        if resolved_email:
            api_server.storage.save_setting("video_flow_notebooklm_email", resolved_email)
    except Exception:
        pass

    # Inform login_flow state cache
    try:
        from .login_flow import record_successful_login

        record_successful_login(resolved_email or "your Google account", profile_name)
    except Exception:
        pass

    logger.info("Successfully synced %d cookies for profile %s (email: %s)", len(cookies), profile_name, resolved_email)
    return {
        "success": True,
        "profile": profile_name,
        "cookies_count": len(cookies),
        "email": resolved_email,
        "storage_path": str(storage_path),
        "has_psidts": details.get("has_psidts", False),
    }


def auto_sync_from_browser(
    profile: str | None = None,
    preferred_browser: str | None = None,
    expected_email: str | None = None,
) -> dict[str, Any]:
    """Attempt automatic zero-interaction cookie extraction from backups and installed browsers."""
    profile_name = resolve_notebooklm_profile(profile)

    switched_from = None
    try:
        from voice_flow.storage import storage
        switched_from = storage.get_setting("video_flow_notebooklm_switched_from")
        if switched_from:
            switched_from = str(switched_from).strip().lower()
    except Exception:
        pass

    explicit_expected_email = expected_email
    # Resolve active expected_email if not explicitly passed, to prevent overwriting with a default/old account
    if not expected_email:
        target_st = get_storage_state_path(profile_name)
        if target_st.is_file():
            try:
                st_data = json.loads(target_st.read_text(encoding="utf-8"))
                if isinstance(st_data, dict):
                    expected_email = (
                        (st_data.get("notebooklm") or {}).get("account", {}).get("email")
                        or (st_data.get("account") or {}).get("email")
                    )
            except Exception:
                pass
        if not expected_email and not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                from voice_flow.storage import storage
                stored = storage.get_setting("video_flow_notebooklm_email")
                if stored and str(stored).strip():
                    expected_email = str(stored).strip()
            except Exception:
                pass

    if expected_email and switched_from and expected_email.lower() == switched_from:
        expected_email = None

    target_storage = get_storage_state_path(profile_name)

    # Profile state checks to prevent circular dead-cookie resurrection
    from .config import is_profile_disconnected, is_profile_unauthenticated, is_session_near_expiry

    is_disconnected = is_profile_disconnected(profile_name)
    is_unauthenticated = is_profile_unauthenticated(profile_name)

    recent_auth_error = False
    try:
        from .login_flow import get_login_state

        l_state = get_login_state()
        if l_state.get("error") or l_state.get("success") is False:
            recent_auth_error = True
    except Exception:
        pass
    if not recent_auth_error:
        try:
            from voice_flow.storage import storage

            if storage.get_setting("video_flow_notebooklm_auth_error"):
                recent_auth_error = True
        except Exception:
            pass

    is_expired = False
    try:
        if is_session_near_expiry(profile_name):
            is_expired = True
    except Exception:
        pass

    # Fast check 0A: If storage_state exists, try lightning-fast CLI refresh directly (5-7s)
    if not os.environ.get("PYTEST_CURRENT_TEST") and not is_disconnected and not is_unauthenticated and target_storage.is_file():
        try:
            from .login_flow import resolve_notebooklm_cli
            cli = resolve_notebooklm_cli()
            if cli:
                p_ref = subprocess.run(
                    [str(cli), "--profile", profile_name, "auth", "refresh", "--verify", "--allow-headless"],
                    capture_output=True,
                    text=True,
                    timeout=30.0,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
                )
                if p_ref.returncode == 0:
                    try:
                        st_fresh = json.loads(target_storage.read_text(encoding="utf-8"))
                        f_acc = (st_fresh.get("notebooklm") or {}).get("account", {}) or st_fresh.get("account", {})
                        f_email = f_acc.get("email") if isinstance(f_acc, dict) else None
                        if switched_from and f_email and str(f_email).strip().lower() == switched_from:
                            pass
                        elif not expected_email or (f_email and f_email.lower().strip() == expected_email.lower().strip()):
                            return {
                                "success": True,
                                "profile": profile_name,
                                "cookies_count": len(st_fresh.get("cookies", [])),
                                "email": f_email or expected_email,
                                "storage_path": str(target_storage),
                                "source": "cli_headless_refresh",
                            }
                    except Exception:
                        pass
        except Exception:
            pass

    # Fast check 0B: If Playwright browser_profile is available and not in pytest, attempt headless live sync
    pw_session_dead = False
    if not os.environ.get("PYTEST_CURRENT_TEST") and not is_disconnected:
        try:
            pw_res = sync_cookies_with_playwright(
                profile=profile_name,
                headless=True,
                expected_email=expected_email,
                timeout_seconds=35,
            )
            if pw_res.get("success"):
                pw_res["source"] = "browser_profile_playwright"
                return pw_res
            if pw_res.get("needs_interactive") or pw_res.get("email_mismatch"):
                pw_session_dead = True
                is_expired = True
                recent_auth_error = True
        except Exception:
            pw_session_dead = True
            is_expired = True
            recent_auth_error = True

    # 1. Check if valid safe_copy or backup exists in this profile directory
    target_storage = get_storage_state_path(profile_name)
    backup_path = get_storage_backup_path(profile_name)
    candidate_files = [
        target_storage.with_name("storage_state.safe_copy.json"),
        target_storage.with_name("storage_state.backup.json"),
    ]
    if backup_path and backup_path not in candidate_files:
        candidate_files.append(backup_path)

    # If running in pytest against real ~/.notebooklm on host machine, isolate tests from user cookies
    if os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            if target_storage.resolve().is_relative_to((Path.home() / ".notebooklm").resolve()):
                return {"success": False, "error": "Test isolation: skipping real user .notebooklm profile", "profile": profile_name}
        except Exception:
            pass

    # If running against real ~/.notebooklm, only check other profile candidates if NO active account is bound and target is default
    is_real_notebooklm = False
    try:
        is_real_notebooklm = target_storage.resolve().is_relative_to((Path.home() / ".notebooklm").resolve())
    except Exception:
        pass

    if is_real_notebooklm and not expected_email and profile_name == "default":
        home_nlm = Path.home() / ".notebooklm"
        fallback_dirs = [
            home_nlm / "profiles" / "default",
            home_nlm,
        ]
        profiles_dir = home_nlm / "profiles"
        if profiles_dir.is_dir():
            for p_dir in profiles_dir.iterdir():
                if p_dir.is_dir() and p_dir not in fallback_dirs and p_dir.resolve() != target_storage.parent.resolve():
                    fallback_dirs.append(p_dir)

        for fb_dir in fallback_dirs:
            for s_name in ("storage_state.safe_copy.json", "storage_state.backup.json", "storage_state.json"):
                cand_file = fb_dir / s_name
                if cand_file.is_file() and cand_file not in candidate_files:
                    candidate_files.append(cand_file)

    # Core cookie fingerprints of target_storage to prevent circular restore of dead cookies
    target_core_cookies: set[tuple[str, str]] = set()
    if target_storage.is_file() and target_storage.stat().st_size > 0:
        try:
            cur_raw = json.loads(target_storage.read_text(encoding="utf-8"))
            if isinstance(cur_raw, dict):
                for ck in cur_raw.get("cookies", []):
                    if isinstance(ck, dict) and ck.get("name") in ("__Secure-1PSID", "SID", "__Secure-1PSIDTS"):
                        target_core_cookies.add((str(ck.get("name")), str(ck.get("value"))))
        except Exception:
            pass

    for cand in candidate_files:
        if cand and cand.is_file() and cand.stat().st_size > 0 and cand != target_storage:
            try:
                c_content = cand.read_text(encoding="utf-8")
                c_data = json.loads(c_content)
                if isinstance(c_data, dict) and isinstance(c_data.get("cookies"), list) and c_data.get("cookies"):
                    c_valid, _, _ = validate_extracted_cookies(c_data.get("cookies"))
                    if c_valid:
                        # Do not restore if backup's session cookies are identical to target_storage
                        cand_core = {
                            (str(ck.get("name")), str(ck.get("value")))
                            for ck in c_data.get("cookies", [])
                            if isinstance(ck, dict) and ck.get("name") in ("__Secure-1PSID", "SID", "__Secure-1PSIDTS")
                        }
                        if target_core_cookies and cand_core and (cand_core == target_core_cookies or cand_core.issubset(target_core_cookies)):
                            continue

                        c_acc = (c_data.get("notebooklm") or {}).get("account", {}) or c_data.get("account", {})
                        c_email = c_acc.get("email") if isinstance(c_acc, dict) else None
                        if switched_from and c_email and str(c_email).strip().lower() == switched_from:
                            continue
                        if expected_email:
                            if not c_email or expected_email.lower().strip() != str(c_email).lower().strip():
                                continue
                        res = save_cookies_to_profile(c_data.get("cookies"), profile=profile_name, email=c_email or expected_email)
                        if res.get("success"):
                            res["source"] = f"restored_{cand.name}"
                            return res
            except Exception:
                pass

    # 2. Check persistent browser_profile directories (which store v10 DPAPI decryptable cookies)
    # Strictly isolated: Never cross-borrow default's browser profile into video-flow-experiment
    # DEAD-COOKIE & CIRCULAR SYNC PREVENTION:
    # Do NOT restore cookies from browser_profile SQLite if:
    # 1. Profile is currently in an unauthenticated, expired, or disconnected state
    # 2. An auth error recently occurred (or Playwright marked session dead)
    # 3. switched_from matches
    skip_browser_profile = (
        pw_session_dead
        or is_disconnected
        or is_unauthenticated
        or is_expired
        or recent_auth_error
    )
    if not skip_browser_profile:
        candidate_bp_dirs: list[Path] = [target_storage.parent / "browser_profile"]
        if is_real_notebooklm and profile_name == "default" and not expected_email:
            candidate_bp_dirs.append(Path.home() / ".notebooklm" / "browser_profile")

        if os.environ.get("PYTEST_CURRENT_TEST"):
            home_nlm = (Path.home() / ".notebooklm").resolve()
            candidate_bp_dirs = [d for d in candidate_bp_dirs if home_nlm not in d.resolve().parents and d.resolve() != home_nlm]

        for bp_dir in candidate_bp_dirs:
            if not bp_dir.is_dir():
                continue
            for sub in [bp_dir / "Default", bp_dir]:
                cookie_candidates = [sub / "Network" / "Cookies", sub / "Cookies"]
                for cf in cookie_candidates:
                    if not cf.is_file():
                        continue
                    try:
                        bp_cookies = extract_cookies_from_sqlite(cf, bp_dir)
                        valid, _, _ = validate_extracted_cookies(bp_cookies)
                        if valid:
                            # Do not restore if browser_profile's cookies are identical to target_storage
                            cand_core = {
                                (str(ck.get("name")), str(ck.get("value")))
                                for ck in bp_cookies
                                if isinstance(ck, dict) and ck.get("name") in ("__Secure-1PSID", "SID", "__Secure-1PSIDTS")
                            }
                            # Check dead cookie values: if target_storage already had cookies that failed authentication,
                            # ensure we do NOT restore the exact same dead cookie values (__Secure-1PSID / SID)
                            target_psid = next((v for n, v in target_core_cookies if n == "__Secure-1PSID"), None)
                            target_sid = next((v for n, v in target_core_cookies if n == "SID"), None)
                            cand_psid = next((v for n, v in cand_core if n == "__Secure-1PSID"), None)
                            cand_sid = next((v for n, v in cand_core if n == "SID"), None)
                            if target_psid and target_sid and cand_psid == target_psid and cand_sid == target_sid:
                                logger.debug("Skipping browser_profile SQLite cookies identical to dead target_storage cookies")
                                continue
                            if target_core_cookies and cand_core and (cand_core == target_core_cookies or cand_core.issubset(target_core_cookies)):
                                logger.debug("Skipping browser_profile SQLite cookies identical to target_storage")
                                continue

                            email = None
                            try:
                                ls_p = bp_dir / "Local State"
                                if ls_p.is_file():
                                    raw_ls = _safe_windows_read_locked_file(ls_p)
                                    if raw_ls:
                                        ls = json.loads(raw_ls.decode("utf-8", errors="replace"))
                                        p_info = (ls.get("profile") or {}).get("info_cache", {}).get("Default", {})
                                        email = p_info.get("user_name") or p_info.get("email")
                            except Exception:
                                pass

                            # Refuse to restore ANY cookies belonging to switched_from
                            if switched_from:
                                if email and str(email).strip().lower() == switched_from:
                                    logger.debug("Skipping browser_profile SQLite cookies matching switched_from '%s'", switched_from)
                                    continue
                                if not email:
                                    logger.debug("Skipping anonymous browser_profile SQLite cookies while switched_from '%s' is active", switched_from)
                                    continue

                            if expected_email:
                                if not email or expected_email.lower().strip() != str(email).lower().strip():
                                    # Never attribute anonymous browser_profile cookies to expected_email!
                                    continue

                            res = save_cookies_to_profile(bp_cookies, profile=profile_name, email=email or expected_email)
                            if res.get("success"):
                                res["source"] = "browser_profile"
                                return res
                    except Exception as exc:
                        logger.debug("Error extracting cookies from browser_profile %s: %s", cf, exc)
    else:
        logger.debug(
            "Skipping browser_profile SQLite restore (pw_session_dead=%s, is_disconnected=%s, "
            "is_unauthenticated=%s, is_expired=%s, recent_auth_error=%s)",
            pw_session_dead,
            is_disconnected,
            is_unauthenticated,
            is_expired,
            recent_auth_error,
        )

    # 3. Check system installed browsers (Chrome, Edge, Brave, Chromium)
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return {"success": False, "error": "No Chromium-based browsers detected on system in test mode.", "profile": profile_name}

    user_data_dirs = discover_browser_user_data_dirs()
    if not user_data_dirs:
        return {"success": False, "error": "No Chromium-based browsers detected on system.", "profile": profile_name}

    search_order = []
    if preferred_browser and preferred_browser.lower() in user_data_dirs:
        search_order.append(preferred_browser.lower())
    for b in ("edge", "brave", "chrome", "chromium"):
        if b in user_data_dirs and b not in search_order:
            search_order.append(b)

    chrome_v20_detected = False
    for b_name in search_order:
        b_path = user_data_dirs[b_name]
        candidate_subdirs = [b_path / "Default"] + list(b_path.glob("Profile *"))
        for sdir in candidate_subdirs:
            cookie_file = sdir / "Network" / "Cookies"
            if not cookie_file.is_file():
                cookie_file = sdir / "Cookies"
            if not cookie_file.is_file():
                continue

            try:
                cookies = extract_cookies_from_sqlite(cookie_file, b_path)
                if not cookies and b_name == "chrome":
                    chrome_v20_detected = True
                valid, _, _ = validate_extracted_cookies(cookies)
                if valid:
                    # Do not restore if cookies are identical to target_storage
                    cand_core = {
                        (str(ck.get("name")), str(ck.get("value")))
                        for ck in cookies
                        if isinstance(ck, dict) and ck.get("name") in ("__Secure-1PSID", "SID", "__Secure-1PSIDTS")
                    }
                    if target_core_cookies and cand_core and (cand_core == target_core_cookies or cand_core.issubset(target_core_cookies)):
                        continue

                    # Check if email is associated with this profile
                    email = None
                    try:
                        ls_path = b_path / "Local State"
                        if ls_path.is_file():
                            raw = _safe_windows_read_locked_file(ls_path)
                            if raw:
                                ls = json.loads(raw.decode("utf-8", errors="replace"))
                                p_info = (ls.get("profile") or {}).get("info_cache", {}).get(sdir.name, {})
                                email = p_info.get("user_name") or p_info.get("email")
                    except Exception:
                        pass

                    if switched_from and email and str(email).strip().lower() == switched_from:
                        continue
                    if expected_email:
                        if not email or expected_email.lower().strip() != str(email).lower().strip():
                            continue

                    res = save_cookies_to_profile(cookies, profile=profile_name, email=email or expected_email)
                    if res.get("success"):
                        res["source_browser"] = b_name
                        res["source_profile"] = sdir.name
                        return res
            except Exception as exc:
                logger.debug("Auto-sync error on %s %s: %s", b_name, sdir.name, exc)
                continue

    if not os.environ.get("PYTEST_CURRENT_TEST") and not pw_session_dead and not skip_browser_profile:
        try:
            pw_fallback = sync_cookies_with_playwright(
                profile=profile_name,
                headless=True,
                expected_email=expected_email,
                timeout_seconds=40,
            )
            if pw_fallback.get("success"):
                pw_fallback["source"] = "browser_profile_playwright_fallback"
                return pw_fallback
        except Exception:
            pass

    if expected_email:
        err_msg = f"No active Google session cookies found matching account '{expected_email}' in installed browsers."
        if chrome_v20_detected:
            err_msg += " (Chrome 127+ App-Bound Encryption prevents direct cookie extraction; interactive login required)."
        if is_expired or recent_auth_error:
            try:
                from voice_flow.storage import storage
                storage.save_setting("video_flow_notebooklm_authenticated", False)
                storage.save_setting("video_flow_notebooklm_auth_error", err_msg)
            except Exception:
                pass
        return {
            "success": False,
            "error": err_msg,
            "profile": profile_name,
            "chrome_v20_detected": chrome_v20_detected,
            "needs_interactive": True,
        }

    err_msg = "No active Google session cookies could be read directly from browser databases."
    if chrome_v20_detected:
        err_msg += " Chrome 127+ App-Bound Encryption (v20) was detected; interactive sign-in or cookie import is required."
    if is_expired or recent_auth_error:
        try:
            from voice_flow.storage import storage
            storage.save_setting("video_flow_notebooklm_authenticated", False)
            storage.save_setting("video_flow_notebooklm_auth_error", err_msg)
        except Exception:
            pass
    return {
        "success": False,
        "error": err_msg,
        "profile": profile_name,
        "chrome_v20_detected": chrome_v20_detected,
        "needs_interactive": True,
    }


def import_cookies(
    payload: Any,
    profile: str | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    """Import and validate raw cookie data (JSON, list, or header string)."""
    profile_name = resolve_notebooklm_profile(profile)
    cookies = parse_cookie_payload(payload)
    if not cookies:
        return {
            "success": False,
            "error": "No valid cookie entries could be parsed from the provided input.",
            "profile": profile_name,
        }

    extracted_email = email
    if not extracted_email and isinstance(payload, Mapping):
        acc = payload.get("account") or (payload.get("notebooklm") or {}).get("account")
        if isinstance(acc, Mapping):
            extracted_email = acc.get("email")
        elif isinstance(payload.get("email"), str):
            extracted_email = payload.get("email")

    return save_cookies_to_profile(cookies, profile=profile_name, email=extracted_email)


def sync_cookies_with_playwright(
    profile: str | None = None,
    browser: str = "chrome",
    timeout_seconds: int = 120,
    headless: bool = False,
    expected_email: str | None = None,
) -> dict[str, Any]:
    """Capture or silently refresh live Google session cookies via Playwright.

    When headless=True, silently loads NotebookLM in the background, rotating
    session timestamp tokens (__Secure-1PSIDTS) so cookies never expire.
    """
    profile_name = resolve_notebooklm_profile(profile)
    browser_profile = get_profile_dir(profile_name) / "browser_profile"
    browser_profile.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright  # type: ignore

        with sync_playwright() as p:
            launch_kwargs: dict[str, Any] = {
                "user_data_dir": str(browser_profile),
                "headless": bool(headless),
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--password-store=basic",
                ],
                "ignore_default_args": ["--enable-automation"],
            }
            channels_to_try: list[str | None] = []
            if browser in ("chrome", "msedge", "chromium"):
                channels_to_try.append(browser)
            for ch in ("chrome", "msedge"):
                if ch not in channels_to_try:
                    channels_to_try.append(ch)
            channels_to_try.append(None)

            context = None
            last_launch_err = None
            for ch in channels_to_try:
                cur_kwargs = dict(launch_kwargs)
                if ch:
                    cur_kwargs["channel"] = ch
                else:
                    cur_kwargs.pop("channel", None)
                try:
                    context = p.chromium.launch_persistent_context(**cur_kwargs)
                    if context:
                        break
                except Exception as l_err:
                    last_launch_err = l_err
                    logger.debug("Playwright persistent context failed with channel=%s: %s", ch, l_err)
                    continue

            if not context:
                raise last_launch_err or RuntimeError("Failed to launch Playwright browser context")

            try:
                # Seed Playwright context with valid saved cookies if needed
                try:
                    from .config import get_storage_backup_path, get_storage_state_path
                    st_path = get_storage_state_path(profile_name)
                    backup_path = get_storage_backup_path(profile_name)
                    safe_path = st_path.with_name("storage_state.safe_copy.json") if st_path else None

                    st_cookies = []
                    for cand in (st_path, safe_path, backup_path):
                        if cand and cand.is_file() and cand.stat().st_size > 0:
                            try:
                                cand_data = json.loads(cand.read_text(encoding="utf-8"))
                                if isinstance(cand_data, dict) and cand_data.get("cookies"):
                                    st_cookies = cand_data.get("cookies", [])
                                    if st_cookies:
                                        break
                            except Exception:
                                continue

                    if st_cookies:
                        now_ts = time.time()
                        for c in st_cookies:
                            if not isinstance(c, dict):
                                continue
                            c_name = str(c.get("name") or "").strip()
                            c_val = str(c.get("value") or "").strip()
                            if not c_name or not c_val:
                                continue
                            c_dom = str(c.get("domain") or ".google.com").strip()
                            if not c_dom.startswith(".") and "google" in c_dom and not c_dom.startswith("notebooklm"):
                                c_dom = "." + c_dom
                            entry = {
                                "name": c_name,
                                "value": c_val,
                                "domain": c_dom,
                                "path": str(c.get("path") or "/"),
                                "secure": bool(c.get("secure", True)),
                                "httpOnly": bool(c.get("httpOnly", False)),
                            }
                            ss = str(c.get("sameSite") or "").strip().capitalize()
                            if ss in ("Strict", "Lax", "None"):
                                entry["sameSite"] = ss
                            exp = c.get("expires")
                            if exp is not None:
                                try:
                                    exp_f = float(exp)
                                    if exp_f <= now_ts:
                                        # Skip expired cookies: seeding expired timestamp tokens
                                        # causes Google to reject rather than re-mint fresh cookies
                                        continue
                                    entry["expires"] = exp_f
                                except (ValueError, TypeError):
                                    pass
                            try:
                                context.add_cookies([entry])
                            except Exception as add_err:
                                logger.debug("Failed adding seeded cookie %s: %s", c_name, add_err)
                except Exception as seed_err:
                    logger.debug("Failed seeding cookies into Playwright context: %s", seed_err)

                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://notebooklm.google.com/", wait_until="commit", timeout=30000)

                # Wait until URL lands on notebooklm or timeout
                start_time = time.time()
                while time.time() - start_time < timeout_seconds:
                    url = str(page.url or "").lower()
                    if "notebooklm.google.com" in url or "notebook.google.com" in url:
                        break
                    # Allow at least 10 seconds for Google's session check redirect chain to settle
                    if headless and ("accounts.google.com" in url or "servicelogin" in url) and (time.time() - start_time > 10.0):
                        return {
                            "success": False,
                            "error": "Session is expired or not signed in; interactive login needed.",
                            "needs_interactive": True,
                            "profile": profile_name,
                        }
                    time.sleep(1.0)

                # Settle page network for DOM and storage state
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass

                # Extract signed-in email
                extracted_email = None
                try:
                    extracted_email = page.evaluate('''() => {
                        const nodes = Array.from(document.querySelectorAll('[aria-label]'));
                        // Check avatar / account button aria-labels first
                        for (const n of nodes) {
                            const label = n.getAttribute('aria-label') || '';
                            if (label.includes('Google Account') || label.includes('Account') || label.includes('signed in')) {
                                const match = label.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/);
                                if (match) return match[0];
                            }
                        }
                        for (const n of nodes) {
                            const label = n.getAttribute('aria-label') || '';
                            const match = label.match(/[a-zA-Z0-9._%+-]+@(?:gmail\\.com|[a-zA-Z0-9.-]+\\.google\\.com)/);
                            if (match && !match[0].startsWith('support@') && !match[0].startsWith('feedback@') && !match[0].startsWith('noreply@')) return match[0];
                        }
                        return null;
                    }''')
                except Exception:
                    pass

                if not extracted_email:
                    try:
                        html = page.content()
                        emails = [e for e in re.findall(r'[\w\.-]+@(?:gmail|google)\.com', html) if not e.startswith(('support', 'feedback', 'noreply'))]
                        if emails:
                            extracted_email = emails[0]
                    except Exception:
                        pass

                if expected_email and extracted_email:
                    if expected_email.lower().strip() != extracted_email.lower().strip():
                        return {
                            "success": False,
                            "error": f"Browser session belongs to '{extracted_email}', but active account is '{expected_email}'.",
                            "email_mismatch": True,
                            "detected_email": extracted_email,
                            "expected_email": expected_email,
                            "profile": profile_name,
                        }

                # Capture cookies from context
                state = context.storage_state()
                raw_cookies = state.get("cookies", []) if isinstance(state, dict) else []
                google_cookies = [
                    c for c in raw_cookies
                    if isinstance(c, dict) and any(d in str(c.get("domain", "")) for d in ("google.com", "notebooklm"))
                ]

                valid, msg, details = validate_extracted_cookies(google_cookies)
                if not valid:
                    return {
                        "success": False,
                        "error": f"Session captured but required cookies missing: {msg}",
                        "profile": profile_name,
                        "details": details,
                    }

                resolved_email = extracted_email or expected_email
                res = save_cookies_to_profile(google_cookies, profile=profile_name, email=resolved_email)
                res["email"] = resolved_email
                res["method"] = "playwright_headless" if headless else "playwright_interactive"
                return res
            finally:
                try:
                    context.close()
                except Exception:
                    pass
    except Exception as exc:
        logger.debug("Playwright sync failed: %s", exc)
        return {"success": False, "error": str(exc), "profile": profile_name}



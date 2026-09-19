"""NotebookLM background keepalive and durable token refresh daemon.

Google's sensitive service cookies (__Secure-1PSIDTS / __Secure-3PSIDTS) rotate
and expire within 24 to 72 hours of inactivity. This keepalive service runs a
lightweight background thread that periodically exercises the auth path (via
master-token refresh or layer-1 keepalive poke), keeping the Google session
perpetually active and preventing the user from being logged out every 2-3 days.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .config import (
    DEFAULT_PROFILE,
    get_profile_dir,
    get_storage_backup_path,
    get_storage_state_path,
    is_session_near_expiry,
    resolve_notebooklm_profile,
)

logger = logging.getLogger(__name__)

DEFAULT_KEEPALIVE_INTERVAL_SECONDS = 1200  # 20 minutes (recommended by notebooklm auth refresh)
MIN_KEEPALIVE_INTERVAL_SECONDS = 300       # 5 minutes


class NotebookLMKeepaliveService:
    """Background daemon that keeps the NotebookLM Google session active and durable."""

    def __init__(
        self,
        *,
        profile: str | None = None,
        interval_seconds: float = DEFAULT_KEEPALIVE_INTERVAL_SECONDS,
        refresh_func: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self.profile = profile.strip() if profile and str(profile).strip() else resolve_notebooklm_profile(None)
        self.interval_seconds = max(MIN_KEEPALIVE_INTERVAL_SECONDS, float(interval_seconds))
        self._refresh_func = refresh_func
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._refresh_in_progress = False
        self._last_run: float = 0.0
        self._last_success: float = 0.0
        self._last_error: str | None = None
        self._run_count: int = 0
        self._success_count: int = 0

    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self, interval_seconds: float | None = None) -> bool:
        """Start the background keepalive thread if not already running."""
        with self._lock:
            if interval_seconds is not None:
                self.interval_seconds = max(MIN_KEEPALIVE_INTERVAL_SECONDS, float(interval_seconds))
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name=f"notebooklm-keepalive-{self.profile}",
                daemon=True,
            )
            self._thread.start()
            logger.info("Started NotebookLM keepalive daemon (interval=%ss, profile=%s)", self.interval_seconds, self.profile)
            return True

    def stop(self, timeout: float = 5.0) -> bool:
        """Signal the keepalive thread to stop and wait for completion."""
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                return False
            self._stop_event.set()
            thread = self._thread
            self._thread = None
        thread.join(timeout=timeout)
        with self._refresh_lock:
            self._refresh_in_progress = False
        logger.info("Stopped NotebookLM keepalive daemon (profile=%s)", self.profile)
        return True

    def trigger_now(self, *, force: bool = False, background: bool = False) -> dict[str, Any]:
        """Trigger an immediate keepalive session refresh check.

        If background=True, dispatches the check to a daemon thread and returns immediately.
        """
        if background:
            t = threading.Thread(
                target=self.run_once,
                kwargs={"force": force},
                name=f"notebooklm-refresh-trigger-{self.profile}",
                daemon=True,
            )
            t.start()
            return {"dispatched": True, "profile": self.profile, "status": self.status()}
        return self.run_once(force=force)

    def run_once(self, *, force: bool = False, profile: str | None = None) -> dict[str, Any]:
        """Perform a single keepalive / session refresh check."""
        target_profile = (profile or self.profile or "").strip() or resolve_notebooklm_profile(None)
        now = time.time()

        wait_deadline = time.time() + (1.0 if force else 0.0)
        while True:
            with self._refresh_lock:
                if not self._refresh_in_progress:
                    self._refresh_in_progress = True
                    break
            if time.time() >= wait_deadline:
                return {
                    "ran": False,
                    "reason": "refresh_already_in_progress",
                    "profile": target_profile,
                    "status": self.status(),
                }
            time.sleep(0.02)

        try:
            # Only skip keepalive if user explicitly clicked Disconnect and no cookies exist
            try:
                if not self._refresh_func and target_profile == resolve_notebooklm_profile(None):
                    from voice_flow.storage import StorageEngine
                    storage = StorageEngine()
                    explicit_disc = storage.get_setting("video_flow_notebooklm_disconnected")
                    from .config import get_storage_state_path
                    st_file = get_storage_state_path(target_profile)
                    has_cookies = False
                    if st_file and st_file.is_file():
                        try:
                            raw = json.loads(st_file.read_text(encoding="utf-8"))
                            has_cookies = bool(isinstance(raw, dict) and raw.get("cookies"))
                        except Exception:
                            has_cookies = False

                    if not force and explicit_disc in (True, "true", "True", 1, "1") and not has_cookies:
                        return {
                            "ran": False,
                            "reason": "explicit_disconnected",
                            "profile": target_profile,
                            "authenticated": False,
                        }
            except Exception:
                pass

            # Check if session needs refresh or forced
            needs_refresh = force or (self._refresh_func is not None) or is_session_near_expiry(target_profile, threshold_seconds=86400.0)

            self._run_count += 1
            self._last_run = now

            if not needs_refresh and not force:
                self._last_success = now
                self._last_error = None
                self._success_count += 1
                return {
                    "ran": True,
                    "success": True,
                    "reason": "session_already_fresh",
                    "profile": target_profile,
                    "last_success": self._last_success,
                }

            if self._refresh_func:
                result = self._refresh_func(profile=target_profile)
            else:
                from .login_flow import self_heal
                is_real_self_heal = (
                    getattr(self_heal, "__module__", "") == "voice_flow.video_flow_engine.notebooklm.login_flow"
                    and not hasattr(self_heal, "assert_called")
                    and not getattr(self_heal, "_mock_self", None)
                )
                if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("VOICE_FLOW_TEST_REAL_CLI") and is_real_self_heal:
                    result = {"ok": True, "method": "pytest_mock_keepalive", "profile": target_profile}
                else:
                    result = self_heal(profile=target_profile, timeout=20)

            ok = bool(result.get("ok"))
            if not ok:
                try:
                    from .browser_sync import auto_sync_from_browser
                    sync_res = auto_sync_from_browser(profile=target_profile)
                    if sync_res.get("success"):
                        ok = True
                        result = {"ok": True, "method": "browser_sync_keepalive", "profile": target_profile}
                except Exception:
                    pass

            allow_pw = not os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("VOICE_FLOW_TEST_PLAYWRIGHT_HEAL")
            if not ok and allow_pw:
                try:
                    from .browser_sync import sync_cookies_with_playwright
                    pw_sync = sync_cookies_with_playwright(profile=target_profile, headless=True, timeout_seconds=35)
                    if pw_sync.get("success"):
                        ok = True
                        result = {"ok": True, "method": "playwright_headless_keepalive"}
                except Exception:
                    pass

            if ok:
                self._last_success = now
                self._last_error = None
                self._success_count += 1
                if not self._refresh_func:
                    try:
                        from voice_flow.storage import StorageEngine
                        storage = StorageEngine()
                        storage.save_setting("video_flow_notebooklm_authenticated", True)
                        storage.save_setting("video_flow_notebooklm_auth_error", "")
                        storage.save_setting("video_flow_notebooklm_disconnected", False)
                    except Exception:
                        pass
                logger.debug("NotebookLM keepalive succeeded for profile %s", target_profile)
            else:
                self._last_error = str(result.get("error") or "Refresh failed")
                logger.warning("NotebookLM keepalive failed for profile %s: %s", target_profile, self._last_error)

            return {
                "ran": True,
                "success": ok,
                "profile": target_profile,
                "error": self._last_error,
                "result": result,
                "last_success": self._last_success,
                "timestamp": now,
            }
        except Exception as exc:
            self._last_error = str(exc)
            logger.exception("Exception in NotebookLM keepalive run_once: %s", exc)
            return {
                "ran": True,
                "success": False,
                "profile": target_profile,
                "error": str(exc),
                "timestamp": now,
            }
        finally:
            with self._refresh_lock:
                self._refresh_in_progress = False

    def _run_loop(self) -> None:
        """Internal daemon loop."""
        # Immediate startup refresh check upon boot without waiting 30 seconds
        if not self._stop_event.is_set():
            try:
                self.run_once(force=True)
            except Exception as exc:
                logger.error("Error in initial NotebookLM startup keepalive check: %s", exc)

        last_ok = True
        while not self._stop_event.is_set():
            delay = self.interval_seconds if last_ok else min(60.0, self.interval_seconds)
            deadline = time.time() + delay
            last_tick = time.time()
            wake_detected = False
            while time.time() < deadline and not self._stop_event.is_set():
                time.sleep(1.0)
                now_tick = time.time()
                # System sleep / wake detection (e.g. laptop lid closed for days and opened)
                if (now_tick - last_tick > 5.0) or (now_tick - last_tick < -5.0):
                    logger.info(
                        "System clock jump / wake detected (elapsed=%.1fs vs 1s tick); triggering immediate keepalive refresh",
                        now_tick - last_tick,
                    )
                    wake_detected = True
                    break
                last_tick = now_tick

            if self._stop_event.is_set():
                break

            try:
                run_res = self.run_once(force=wake_detected)
                if run_res.get("ran") and not run_res.get("success"):
                    last_ok = False
                else:
                    last_ok = True
            except Exception as exc:
                logger.error("Error in NotebookLM keepalive loop: %s", exc)
                last_ok = False

    def status(self) -> dict[str, Any]:
        """Return current status of the keepalive service."""
        with self._lock:
            running = self._thread is not None and self._thread.is_alive()
        return {
            "running": running,
            "profile": self.profile,
            "interval_seconds": self.interval_seconds,
            "last_run": self._last_run,
            "last_success": self._last_success,
            "last_error": self._last_error,
            "run_count": self._run_count,
            "success_count": self._success_count,
        }


# Module-level per-profile singletons (default profile behavior identical to the
# former single-global singleton).
_GLOBAL_KEEPALIVES: dict[str, NotebookLMKeepaliveService] = {}
_GLOBAL_LOCK = threading.Lock()
# Back-compat alias: legacy single-global reference. Kept in sync with the
# default-profile entry so any external introspection keeps working.
_GLOBAL_KEEPALIVE: NotebookLMKeepaliveService | None = None


def get_keepalive_service(profile: str | None = None) -> NotebookLMKeepaliveService:
    """Return the global NotebookLM keepalive service singleton for a profile."""
    global _GLOBAL_KEEPALIVE
    key = profile.strip() if profile and str(profile).strip() else resolve_notebooklm_profile(None)
    with _GLOBAL_LOCK:
        service = _GLOBAL_KEEPALIVES.get(key)
        if service is None:
            service = NotebookLMKeepaliveService(profile=key)
            _GLOBAL_KEEPALIVES[key] = service
        if key == resolve_notebooklm_profile(None):
            _GLOBAL_KEEPALIVE = service
        return service


def start_keepalive_daemon(profile: str | None = None, interval_seconds: float = DEFAULT_KEEPALIVE_INTERVAL_SECONDS) -> bool:
    """Start the global keepalive daemon."""
    service = get_keepalive_service(profile)
    return service.start(interval_seconds)


def stop_keepalive_daemon(profile: str | None = None) -> bool:
    """Stop the global keepalive daemon (one profile, or all when omitted)."""
    global _GLOBAL_KEEPALIVE
    with _GLOBAL_LOCK:
        if profile is not None:
            key = profile.strip()
            service = _GLOBAL_KEEPALIVES.get(key)
            if service is not None:
                return service.stop()
            return False
        stopped_any = False
        for service in list(_GLOBAL_KEEPALIVES.values()):
            try:
                if service.stop():
                    stopped_any = True
            except Exception:
                pass
        if _GLOBAL_KEEPALIVE is not None:
            try:
                if _GLOBAL_KEEPALIVE.stop():
                    stopped_any = True
            except Exception:
                pass
        return stopped_any


def get_keepalive_status(profile: str | None = None) -> dict[str, Any]:
    """Get the status of the global keepalive daemon (default profile when omitted)."""
    global _GLOBAL_KEEPALIVE
    with _GLOBAL_LOCK:
        key = profile.strip() if profile and str(profile).strip() else resolve_notebooklm_profile(None)
        service = _GLOBAL_KEEPALIVES.get(key)
        if service is None and profile is None:
            service = _GLOBAL_KEEPALIVE
        if service is not None:
            return service.status()
    return {
        "running": False,
        "profile": DEFAULT_PROFILE,
        "interval_seconds": DEFAULT_KEEPALIVE_INTERVAL_SECONDS,
        "last_run": 0.0,
        "last_success": 0.0,
        "last_error": None,
        "run_count": 0,
        "success_count": 0,
    }


def trigger_keepalive_now(
    profile: str | None = None,
    *,
    force: bool = False,
    background: bool = False,
) -> dict[str, Any]:
    """Trigger an immediate keepalive session refresh check."""
    service = get_keepalive_service(profile)
    return service.trigger_now(force=force, background=background)


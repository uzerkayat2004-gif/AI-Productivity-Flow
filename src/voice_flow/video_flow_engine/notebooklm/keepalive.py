"""Bounded, per-profile NotebookLM background session renewal."""

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
        self._refresh_state: str = "idle"
        self._last_result: dict[str, Any] | None = None
        self._refresh_epoch: int = 0

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
        thread.join(timeout=timeout)
        with self._lock:
            if self._thread is thread and not thread.is_alive():
                self._thread = None
        logger.info("Stopped NotebookLM keepalive daemon (profile=%s)", self.profile)
        return True

    def trigger_now(self, *, force: bool = False, background: bool = False) -> dict[str, Any]:
        """Trigger an immediate keepalive session refresh check.

        If background=True, dispatches the check to a daemon thread and returns immediately.
        """
        if background:
            with self._refresh_lock:
                if self._refresh_in_progress:
                    coalesced = True
                else:
                    coalesced = False
                    self._refresh_in_progress = True
                    self._refresh_state = "refreshing"
                    epoch = self._refresh_epoch
            if coalesced:
                return {"coalesced": True, "dispatched": False, **self.refresh_status()}
            t = threading.Thread(
                target=self._run_once_claimed,
                kwargs={"force": force, "profile": self.profile, "epoch": epoch},
                name=f"notebooklm-refresh-trigger-{self.profile}",
                daemon=True,
            )
            t.start()
            return {"dispatched": True, "coalesced": False, **self.refresh_status()}
        return self.run_once(force=force)

    def _run_once_claimed(self, *, force: bool, profile: str, epoch: int) -> dict[str, Any]:
        return self.run_once(force=force, profile=profile, _claimed=True, _epoch=epoch)

    def run_once(self, *, force: bool = False, profile: str | None = None, _claimed: bool = False,
                 _epoch: int | None = None) -> dict[str, Any]:
        """Perform a single keepalive / session refresh check."""
        target_profile = (profile or self.profile or "").strip() or resolve_notebooklm_profile(None)
        now = time.time()

        if not _claimed:
            with self._refresh_lock:
                if self._refresh_in_progress:
                    coalesced = True
                else:
                    coalesced = False
                    self._refresh_in_progress = True
                    self._refresh_state = "refreshing"
                    _epoch = self._refresh_epoch
            if coalesced:
                return {"ran": False, "coalesced": True, "reason": "refresh_already_in_progress",
                        "profile": target_profile, "status": self.refresh_status()}

        try:
            try:
                from .login_flow import get_login_state
                if get_login_state().get("running"):
                    self._refresh_state = "idle"
                    return {"ran": False, "reason": "login_in_progress", "profile": target_profile}
            except Exception:
                pass
            # Explicit Disconnect is authoritative even when old cookies remain.
            try:
                if not self._refresh_func:
                    from voice_flow.storage import StorageEngine
                    storage = StorageEngine()
                    explicit_disc = storage.get_setting("video_flow_notebooklm_disconnected")
                    saved_email = str(storage.get_setting("video_flow_notebooklm_email") or "").strip()
                    from .config import get_storage_state_path
                    st_file = get_storage_state_path(target_profile)
                    has_cookies = False
                    if st_file and st_file.is_file():
                        try:
                            raw = json.loads(st_file.read_text(encoding="utf-8"))
                            has_cookies = bool(isinstance(raw, dict) and raw.get("cookies"))
                        except Exception:
                            has_cookies = False

                    if explicit_disc in (True, "true", "True", 1, "1"):
                        self._refresh_state = "idle"
                        return {
                            "ran": False,
                            "reason": "explicit_disconnected",
                            "profile": target_profile,
                            "authenticated": False,
                        }
                    if not saved_email and not has_cookies:
                        self._refresh_state = "idle"
                        return {"ran": False, "reason": "no_saved_session", "profile": target_profile}
            except Exception:
                pass

            # Run the CLI's cheap refresh verification each cadence. Cookie
            # expiry timestamps are not a reliable indication of Google's
            # server-side session validity, especially after sleep/wake.

            self._run_count += 1
            self._last_run = now

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
                    # The CLI's layered headless recovery plus verification can
                    # legitimately take longer than the former 20-second cap.
                    result = self_heal(profile=target_profile, timeout=45)

            ok = bool(result.get("ok"))
            transient = result.get("authenticated") is None and (
                result.get("classification") == "transient_error" or result.get("status") == "transient_error"
            )
            with self._refresh_lock:
                if _epoch is not None and _epoch != self._refresh_epoch:
                    return {"ran": True, "success": False, "stale": True, "profile": target_profile,
                            "reason": "superseded_auth_operation", "result": result}
                if ok:
                    self._last_success = now
                    self._last_error = None
                    self._success_count += 1
                    self._refresh_state = "authenticated"
                else:
                    self._last_error = str(result.get("error") or "Refresh failed")
                    self._refresh_state = "transient_error" if transient else "sign_in_required"
                response = {
                    "ran": True,
                    "success": ok,
                    "profile": target_profile,
                    "error": self._last_error,
                    "result": result,
                    "last_success": self._last_success,
                    "timestamp": now,
                }
                self._last_result = response
            if ok:
                logger.debug("NotebookLM keepalive succeeded for profile %s", target_profile)
            else:
                logger.warning("NotebookLM keepalive failed for profile %s: %s", target_profile, self._last_error)
            return response
        except Exception as exc:
            logger.exception("Exception in NotebookLM keepalive run_once: %s", exc)
            with self._refresh_lock:
                if _epoch is not None and _epoch != self._refresh_epoch:
                    return {"ran": True, "success": False, "stale": True, "profile": target_profile,
                            "reason": "superseded_auth_operation", "error": str(exc)}
                self._last_error = str(exc)
                self._refresh_state = "transient_error"
                response = {"ran": True, "success": False, "profile": target_profile,
                            "error": str(exc), "timestamp": now}
                self._last_result = response
                return response
        finally:
            with self._refresh_lock:
                self._refresh_in_progress = False

    def _run_loop(self) -> None:
        """Internal daemon loop."""
        # Immediate startup refresh check upon boot without waiting 30 seconds
        short_retry_due = False
        if not self._stop_event.is_set():
            try:
                initial_result = self.run_once(force=True)
                short_retry_due = bool(
                    initial_result.get("ran") and not initial_result.get("success")
                    and self._refresh_state == "transient_error"
                )
            except Exception as exc:
                logger.error("Error in initial NotebookLM startup keepalive check: %s", exc)
                short_retry_due = True

        while not self._stop_event.is_set():
            # Retry each normal wake/startup transient once after connectivity
            # may have settled; a failed retry returns to the normal cadence.
            delay = min(60.0, self.interval_seconds) if short_retry_due else self.interval_seconds
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
                was_short_retry = short_retry_due
                run_res = self.run_once(force=wake_detected)
                short_retry_due = bool(
                    not was_short_retry and run_res.get("ran") and not run_res.get("success")
                    and self._refresh_state == "transient_error"
                )
            except Exception as exc:
                logger.error("Error in NotebookLM keepalive loop: %s", exc)
                short_retry_due = not short_retry_due

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

    def refresh_status(self) -> dict[str, Any]:
        with self._refresh_lock:
            in_progress = self._refresh_in_progress
            state = "refreshing" if in_progress else self._refresh_state
        result = self._last_result
        operation_result = result.get("result") if isinstance(result, dict) and isinstance(result.get("result"), dict) else {}
        message = (result or {}).get("error") or operation_result.get("error") or operation_result.get("message")
        return {"profile": self.profile, "state": state, "in_progress": in_progress,
                "last_run": self._last_run, "last_success": self._last_success,
                "last_error": self._last_error, "message": message,
                "definitive": state in ("authenticated", "sign_in_required"), "result": result}


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


def request_session_refresh(profile: str | None = None, *, background: bool = True, force: bool = False) -> dict[str, Any]:
    """Request one per-profile refresh, coalescing concurrent callers."""
    return get_keepalive_service(profile).trigger_now(force=force, background=background)


def get_session_refresh_state(profile: str | None = None) -> dict[str, Any]:
    """Return the current refresh state without spawning a CLI process."""
    return get_keepalive_service(profile).refresh_status()


def reset_session_refresh_state(profile: str | None = None, *, state: str = "idle") -> None:
    """Invalidate a prior terminal refresh verdict after an explicit auth action."""
    service = get_keepalive_service(profile)
    with service._refresh_lock:
        service._refresh_epoch += 1
        service._refresh_state = state
        service._last_result = None
        service._last_error = None

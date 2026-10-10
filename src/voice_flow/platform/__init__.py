"""Platform backend selection.

Voice Flow talks to the operating system through exactly one object: the
backend returned by :func:`get_backend`. Windows and macOS each provide a
concrete implementation of the :class:`~voice_flow.platform.base.PlatformBackend`
protocol; this module picks the right one at runtime from ``sys.platform``.

Usage::

    from voice_flow.platform import get_backend

    backend = get_backend()
    backend.copy_to_clipboard("hello")
    backend.send_paste()

Design rules enforced here:

* **Nothing touches the OS at import time.** Importing this package is safe on
  any platform, including CI containers with no display and no clipboard.
* **Import never fails.** If the OS-specific module cannot be imported (missing
  frameworks, stripped install), :func:`get_backend` returns a null backend that
  reports failure from every method instead of raising. Callers already handle
  ``False`` / ``""`` returns, so a degraded host stays usable.
* **The backend is a singleton**, resolved once and cached, because backends
  hold lazily-initialised OS handles.

.. note::
   This package is named ``platform``, which shadows the standard library
   module of the same name *only* for code inside ``voice_flow`` that uses
   implicit relative imports. Python 3 uses absolute imports by default, so
   ``import platform`` anywhere still resolves to the stdlib. Verified: no
   module under ``src/voice_flow`` imports the stdlib ``platform``.
"""

from __future__ import annotations

import logging
import sys
import threading

from voice_flow.platform.base import (
    PermissionReport,
    PermissionState,
    PlatformBackend,
)

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


class NullBackend:
    """Inert backend used when no OS implementation could be loaded.

    Every method fails softly and logs once per process, so an unsupported or
    broken host degrades to "features do nothing" rather than "app crashes".
    """

    name = "null"

    def __init__(self, reason: str = "unsupported platform") -> None:
        self._reason = reason
        self._warned = False

    def _warn(self, op: str) -> None:
        if not self._warned:
            log.warning(
                "[PLATFORM] no backend available (%s); %s and later OS calls are no-ops",
                self._reason,
                op,
            )
            self._warned = True

    # -- clipboard ---------------------------------------------------------
    def copy_to_clipboard(self, text: str) -> bool:
        self._warn("copy_to_clipboard")
        return False

    def read_clipboard(self) -> str:
        self._warn("read_clipboard")
        return ""

    # -- synthetic input ---------------------------------------------------
    def send_paste(self) -> bool:
        self._warn("send_paste")
        return False

    def send_copy(self) -> bool:
        self._warn("send_copy")
        return False

    def send_enter(self) -> bool:
        self._warn("send_enter")
        return False

    # -- window / focus ----------------------------------------------------
    def active_window_title(self) -> str:
        return ""

    def active_app_name(self) -> str:
        return ""

    def is_own_window_focused(self) -> bool:
        return False

    # -- selection ---------------------------------------------------------
    def get_selected_text(self) -> str:
        self._warn("get_selected_text")
        return ""

    # -- feedback ----------------------------------------------------------
    def beep(self, kind: str = "start") -> bool:
        return False

    # -- autostart ---------------------------------------------------------
    def get_launch_at_login(self) -> bool:
        return False

    def set_launch_at_login(self, enabled: bool, command: str | None = None) -> bool:
        self._warn("set_launch_at_login")
        return False

    # -- permissions -------------------------------------------------------
    def permission_report(self) -> PermissionReport:
        return PermissionReport(platform=sys.platform, states=())

    def open_permission_settings(self, key: str) -> bool:
        return False

    # -- tts ---------------------------------------------------------------
    def system_tts_to_file(self, text: str, out_path: str, voice: str | None = None) -> bool:
        self._warn("system_tts_to_file")
        return False

    def system_tts_voices(self) -> list[str]:
        return []


_backend: PlatformBackend | None = None
_lock = threading.Lock()


def _build_backend() -> PlatformBackend:
    """Import and construct the backend for the current OS.

    Import errors are caught and converted into a :class:`NullBackend`, so a
    missing optional dependency can never prevent Voice Flow from starting.
    """
    if IS_WINDOWS:
        try:
            from voice_flow.platform.windows import WindowsBackend

            return WindowsBackend()
        except Exception as exc:  # pragma: no cover - defensive
            log.error("[PLATFORM] Windows backend unavailable: %s", exc, exc_info=True)
            return NullBackend(f"windows backend import failed: {exc}")

    if IS_MACOS:
        try:
            from voice_flow.platform.macos import MacOSBackend

            return MacOSBackend()
        except Exception as exc:  # pragma: no cover - exercised on macOS CI
            log.error("[PLATFORM] macOS backend unavailable: %s", exc, exc_info=True)
            return NullBackend(f"macos backend import failed: {exc}")

    return NullBackend(f"{sys.platform!r} has no Voice Flow backend")


def get_backend() -> PlatformBackend:
    """Return the process-wide platform backend (constructed on first call)."""
    global _backend
    if _backend is None:
        with _lock:
            if _backend is None:
                _backend = _build_backend()
                log.info("[PLATFORM] backend=%s platform=%s", _backend.name, sys.platform)
    return _backend


def set_backend(backend: PlatformBackend | None) -> None:
    """Override the backend. Intended for tests; pass ``None`` to reset."""
    global _backend
    with _lock:
        _backend = backend


def reset_backend() -> None:
    """Drop the cached backend so the next :func:`get_backend` rebuilds it."""
    set_backend(None)


__all__ = [
    "get_backend",
    "set_backend",
    "reset_backend",
    "NullBackend",
    "PlatformBackend",
    "PermissionState",
    "PermissionReport",
    "IS_WINDOWS",
    "IS_MACOS",
    "IS_LINUX",
]

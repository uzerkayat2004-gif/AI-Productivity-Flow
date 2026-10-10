"""Import-safe Win32 ctypes surface.

``ctypes.wintypes`` raises ``ValueError`` on non-Windows platforms, and
``ctypes.windll`` / ``ctypes.WINFUNCTYPE`` simply do not exist there. Several
Voice Flow modules reference those names at *module level* (inside
``ctypes.Structure`` field lists and ``argtypes`` declarations), so a plain
``try/except ImportError`` around the import is not enough — the class bodies
still need the type objects to exist.

This module provides drop-in replacements that behave identically on Windows
and degrade to inert stand-ins elsewhere:

    from voice_flow.platform.wincompat import IS_WINDOWS, wintypes, windll, WINFUNCTYPE

On Windows these are the genuine objects. On macOS/Linux they are stubs that
let the module import cleanly; any *call* into the stubbed Win32 surface raises
``Win32Unavailable`` so a mis-routed call fails loudly instead of silently
doing nothing.

Nothing in this module touches the OS at import time.
"""

from __future__ import annotations

import ctypes
import sys
from types import SimpleNamespace

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


class Win32Unavailable(RuntimeError):
    """Raised when Win32-only functionality is invoked on a non-Windows host."""


# ---------------------------------------------------------------------------
# wintypes
# ---------------------------------------------------------------------------

if IS_WINDOWS:  # pragma: no cover - exercised on Windows CI
    from ctypes import wintypes as wintypes  # type: ignore[assignment]
else:
    # Field-compatible stand-ins. Sizes are chosen to match the Win32 ABI on
    # 64-bit builds so ctypes.Structure definitions stay valid and testable.
    class _MSG(ctypes.Structure):
        _fields_ = [
            ("hWnd", ctypes.c_void_p),
            ("message", ctypes.c_uint),
            ("wParam", ctypes.c_size_t),
            ("lParam", ctypes.c_ssize_t),
            ("time", ctypes.c_ulong),
            ("pt_x", ctypes.c_long),
            ("pt_y", ctypes.c_long),
        ]

    wintypes = SimpleNamespace(  # type: ignore[assignment]
        BOOL=ctypes.c_int,
        BYTE=ctypes.c_ubyte,
        WORD=ctypes.c_ushort,
        DWORD=ctypes.c_ulong,
        LONG=ctypes.c_long,
        ULONG=ctypes.c_ulong,
        LPARAM=ctypes.c_ssize_t,
        WPARAM=ctypes.c_size_t,
        UINT=ctypes.c_uint,
        INT=ctypes.c_int,
        HANDLE=ctypes.c_void_p,
        HWND=ctypes.c_void_p,
        HHOOK=ctypes.c_void_p,
        HINSTANCE=ctypes.c_void_p,
        HMODULE=ctypes.c_void_p,
        LPVOID=ctypes.c_void_p,
        LPCWSTR=ctypes.c_wchar_p,
        LPWSTR=ctypes.c_wchar_p,
        MAX_PATH=260,
        MSG=_MSG,
    )


# ---------------------------------------------------------------------------
# WINFUNCTYPE
# ---------------------------------------------------------------------------

if IS_WINDOWS:  # pragma: no cover - exercised on Windows CI
    WINFUNCTYPE = ctypes.WINFUNCTYPE  # type: ignore[attr-defined]
else:
    # CFUNCTYPE has the same Python-level signature; it is never actually
    # handed to a Win32 API on this platform, it only needs to construct.
    WINFUNCTYPE = ctypes.CFUNCTYPE


# ---------------------------------------------------------------------------
# windll
# ---------------------------------------------------------------------------


class _UnavailableFunc:
    """Callable placeholder that raises instead of pretending to succeed."""

    __slots__ = ("_dll", "_name")

    def __init__(self, dll: str, name: str) -> None:
        self._dll = dll
        self._name = name

    # argtypes/restype are assigned at module import time by several callers.
    def __setattr__(self, key: str, value: object) -> None:
        if key in ("_dll", "_name"):
            object.__setattr__(self, key, value)
        # Silently accept argtypes/restype assignment so module-level
        # prototype declarations do not explode on import.

    def __getattr__(self, key: str) -> object:
        return None

    def __call__(self, *args: object, **kwargs: object) -> object:
        raise Win32Unavailable(
            f"{self._dll}.{self._name} is Windows-only and was called on "
            f"{sys.platform!r}. Route this through voice_flow.platform instead."
        )

    def __bool__(self) -> bool:
        return False


class _UnavailableDLL:
    """Stands in for a ``ctypes.windll.<name>`` handle off-Windows."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._cache: dict[str, _UnavailableFunc] = {}

    def __getattr__(self, item: str) -> _UnavailableFunc:
        if item.startswith("_"):
            raise AttributeError(item)
        if item not in self._cache:
            self._cache[item] = _UnavailableFunc(self._name, item)
        return self._cache[item]

    def __bool__(self) -> bool:
        return False


class _UnavailableWinDLL:
    """Stands in for ``ctypes.windll`` off-Windows."""

    def __init__(self) -> None:
        self._cache: dict[str, _UnavailableDLL] = {}

    def __getattr__(self, item: str) -> _UnavailableDLL:
        if item.startswith("_"):
            raise AttributeError(item)
        if item not in self._cache:
            self._cache[item] = _UnavailableDLL(item)
        return self._cache[item]

    def __bool__(self) -> bool:
        return False


if IS_WINDOWS:  # pragma: no cover - exercised on Windows CI
    windll = ctypes.windll  # type: ignore[attr-defined]
else:
    windll = _UnavailableWinDLL()  # type: ignore[assignment]
    if not hasattr(ctypes, "windll"):
        ctypes.windll = windll  # type: ignore[attr-defined]
    if not hasattr(ctypes, "wintypes"):
        ctypes.wintypes = wintypes  # type: ignore[attr-defined]


def win32_available() -> bool:
    """True when the genuine Win32 ctypes surface is usable."""
    return IS_WINDOWS


def require_windows(feature: str = "this feature") -> None:
    """Raise a clear error when Windows-only code is reached elsewhere."""
    if not IS_WINDOWS:
        raise Win32Unavailable(f"{feature} requires Windows (running on {sys.platform!r}).")


__all__ = [
    "IS_WINDOWS",
    "IS_MACOS",
    "IS_LINUX",
    "Win32Unavailable",
    "wintypes",
    "windll",
    "WINFUNCTYPE",
    "win32_available",
    "require_windows",
]

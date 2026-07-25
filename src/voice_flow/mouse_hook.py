"""Native Win32 Low-Level Mouse Hook for Voice Flow.

Selectively blocks ONLY middle-click down/up (WM_MBUTTONDOWN / WM_MBUTTONUP)
to prevent the autoscroll drag icon, while leaving mouse movement, left click,
right click, and scroll wheel rotation 100% untouched and unhindered.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import threading
from typing import Callable

log = logging.getLogger(__name__)

# Win32 Constants
WH_MOUSE_LL = 14
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A
WM_MOUSEHWHEEL = 0x020E

# Structs
class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]

HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    HOOKPROC,
    wintypes.HINSTANCE,
    wintypes.DWORD,
]
user32.SetWindowsHookExW.restype = wintypes.HHOOK

user32.CallNextHookEx.argtypes = [
    wintypes.HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.CallNextHookEx.restype = ctypes.c_ssize_t

user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL


class NativeMiddleClickHook:
    """Low-level Win32 mouse hook that cleanly blocks middle-click without affecting cursor movement."""

    def __init__(
        self,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        self.on_press = on_press
        self.on_release = on_release

        self._hook: wintypes.HHOOK = None
        self._hook_proc = HOOKPROC(self._low_level_mouse_proc)
        self._thread: threading.Thread | None = None
        self._is_pressed = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the hook in a dedicated Windows message loop thread."""
        self._thread = threading.Thread(target=self._run_hook_thread, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Unhook and stop."""
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def _run_hook_thread(self) -> None:
        """Windows message loop thread required for WH_MOUSE_LL."""
        h_module = kernel32.GetModuleHandleW(None)
        self._hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL, self._hook_proc, h_module, 0
        )
        if not self._hook:
            log.error("Failed to install native mouse hook.")
            return

        log.info("Native Win32 mouse hook installed (Middle-click drag autoscroll blocked, cursor movement 100% smooth).")

        # Standard Win32 Message Pump
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _low_level_mouse_proc(
        self, nCode: int, wParam: int, lParam: int
    ) -> int:
        if nCode >= 0:
            if wParam == WM_MBUTTONDOWN:
                with self._lock:
                    if not self._is_pressed:
                        self._is_pressed = True
                        self.on_press()
                return 1  # Return 1 to DISCARD middle-click down from Windows

            elif wParam == WM_MBUTTONUP:
                with self._lock:
                    if self._is_pressed:
                        self._is_pressed = False
                        self.on_release()
                return 1  # Return 1 to DISCARD middle-click up from Windows

        # For ALL other mouse events (WM_MOUSEMOVE, WM_MOUSEWHEEL, left/right clicks):
        # Immediately pass through to Windows OS with zero delay!
        return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

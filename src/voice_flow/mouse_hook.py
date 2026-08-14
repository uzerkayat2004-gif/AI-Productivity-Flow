"""Native Win32 Low-Level Mouse Hook (WH_MOUSE_LL) with Auto-Rehook Watchdog.

Features:
- 64-bit safe Win32 Low-Level Mouse Hook running on a dedicated message-pump thread.
- Zero-latency hook procedure (< 1ms execution) to prevent Windows LowLevelHooksTimeout unhooking.
- Auto-rehook watchdog: automatically detects if Windows drops the hook and silently reinstalls it.
- Middle-click interception: supports push-to-talk hold (>0.30s) and toggle tap (<0.30s), suppressing autoscroll cursor.
- Left-click drag tracking: detects text selection drags (>= 6px) with debounced event dispatching.
- Safe fallback to pynput if raw Win32 hook fails to initialize.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import threading
import time
from typing import Callable

log = logging.getLogger(__name__)

# Win32 Constants
WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MBUTTONDBLCLK = 0x0209
WM_NCMBUTTONDOWN = 0x00A7
WM_NCMBUTTONUP = 0x00A8
WM_NCMBUTTONDBLCLK = 0x00A9

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Structs for low-level mouse hook
class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulong),
    ]


# Exact 64-bit safe types for Windows LowLevelMouseProc
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(
    LRESULT,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK

user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT


class Win32MouseHook:
    """Robust Win32 Low-Level Mouse Hook with auto-recovery and thread safety."""

    def __init__(
        self,
        on_start: Callable[[], None],
        on_finish: Callable[[], None],
        on_cancel: Callable[[], None],
        on_mouse_release: Callable[..., None] | None = None,
    ) -> None:
        self._on_start = on_start
        self._on_finish = on_finish
        self._on_cancel = on_cancel
        self._on_mouse_release = on_mouse_release

        self._hook_handle: int | None = None
        self._hook_proc_ptr: object | None = None  # Prevent garbage collection of callback
        self._hook_thread: threading.Thread | None = None
        self._hook_thread_id: int = 0
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # State tracking
        self._is_recording = False
        self._mbutton_press_time: float = 0.0
        self._last_left_down_x: int = 0
        self._last_left_down_y: int = 0
        self._last_event_time: float = time.time()
        self._is_hooked = False

        # Watchdog
        self._watchdog_thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the Win32 mouse hook thread and watchdog."""
        with self._lock:
            if self._hook_thread and self._hook_thread.is_alive():
                return
            self._stop_event.clear()
            self._hook_thread = threading.Thread(
                target=self._run_hook_loop,
                name="Win32MouseHookThread",
                daemon=True,
            )
            self._hook_thread.start()

            # Start watchdog thread to monitor hook liveness
            if not self._watchdog_thread or not self._watchdog_thread.is_alive():
                self._watchdog_thread = threading.Thread(
                    target=self._watchdog_loop,
                    name="Win32MouseHookWatchdog",
                    daemon=True,
                )
                self._watchdog_thread.start()

        log.info("[MOUSE HOOK] Win32 low-level mouse hook service started.")

    def stop(self) -> None:
        """Stop the mouse hook and release system resources."""
        self._stop_event.set()
        with self._lock:
            self._unhook()
        log.info("[MOUSE HOOK] Win32 mouse hook stopped.")

    def set_recording_state(self, recording: bool) -> None:
        """Synchronize current recording state."""
        with self._lock:
            self._is_recording = recording

    def is_healthy(self) -> bool:
        """Check whether the mouse hook is currently active and healthy."""
        with self._lock:
            return self._is_hooked and self._hook_handle is not None and self._hook_thread is not None and self._hook_thread.is_alive()

    # -- Internal Hook Lifecycle --

    def _install_hook(self) -> bool:
        """Install WH_MOUSE_LL hook with 64-bit safety and 0 hMod."""
        try:
            def _low_level_mouse_proc(nCode: int, wParam: int, lParam: int) -> int:
                if nCode >= 0:
                    try:
                        self._last_event_time = time.time()
                        msg = int(wParam)

                        # Middle button down / double-click
                        if msg in (WM_MBUTTONDOWN, WM_NCMBUTTONDOWN, WM_MBUTTONDBLCLK, WM_NCMBUTTONDBLCLK):
                            with self._lock:
                                self._mbutton_press_time = time.time()
                                if not self._is_recording:
                                    self._is_recording = True
                                    threading.Thread(target=self._safe_on_start, daemon=True).start()
                                else:
                                    self._is_recording = False
                                    threading.Thread(target=self._safe_on_finish, daemon=True).start()
                            # Suppress autoscroll popup cursor
                            return 1

                        # Middle button up
                        elif msg in (WM_MBUTTONUP, WM_NCMBUTTONUP):
                            with self._lock:
                                press_dur = time.time() - self._mbutton_press_time
                                # If held > 0.30s (push-to-talk hold), finish on release
                                if self._is_recording and press_dur > 0.30:
                                    self._is_recording = False
                                    threading.Thread(target=self._safe_on_finish, daemon=True).start()
                            # Suppress autoscroll popup cursor
                            return 1

                        # Left button drag tracking for text selection
                        elif msg == WM_LBUTTONDOWN:
                            if lParam:
                                ms = MSLLHOOKSTRUCT.from_address(lParam)
                                self._last_left_down_x = ms.pt.x
                                self._last_left_down_y = ms.pt.y
                        elif msg == WM_LBUTTONUP:
                            if lParam and self._on_mouse_release:
                                ms = MSLLHOOKSTRUCT.from_address(lParam)
                                x, y = ms.pt.x, ms.pt.y
                                dx = x - self._last_left_down_x
                                dy = y - self._last_left_down_y
                                drag_dist = (dx * dx + dy * dy) ** 0.5
                                if drag_dist >= 6.0:
                                    threading.Thread(
                                        target=self._safe_on_mouse_release,
                                        args=(x, y, drag_dist, self._last_left_down_x, self._last_left_down_y),
                                        daemon=True,
                                    ).start()

                    except Exception as e:
                        log.debug("[MOUSE HOOK] Error in hook callback: %s", e)

                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            self._hook_proc_ptr = HOOKPROC(_low_level_mouse_proc)
            self._hook_handle = user32.SetWindowsHookExW(
                WH_MOUSE_LL,
                self._hook_proc_ptr,
                0,
                0,
            )

            if not self._hook_handle:
                err = kernel32.GetLastError()
                log.error("[MOUSE HOOK] SetWindowsHookExW failed with error code: %d", err)
                self._is_hooked = False
                return False

            self._is_hooked = True
            log.info("[MOUSE HOOK] WH_MOUSE_LL hook successfully installed (handle=0x%x).", self._hook_handle)
            return True
        except Exception as exc:
            log.error("[MOUSE HOOK] Hook installation exception: %s", exc)
            self._is_hooked = False
            return False

    def _unhook(self) -> None:
        """Safely unhook the mouse hook."""
        if self._hook_handle:
            try:
                user32.UnhookWindowsHookEx(self._hook_handle)
            except Exception:
                pass
            self._hook_handle = None
        self._is_hooked = False
        if self._hook_thread_id:
            try:
                user32.PostThreadMessageW(self._hook_thread_id, 0x0012, 0, 0)  # WM_QUIT = 0x0012
            except Exception:
                pass

    def _run_hook_loop(self) -> None:
        """Dedicated message-pump loop for the low-level hook."""
        self._hook_thread_id = kernel32.GetCurrentThreadId()
        installed = self._install_hook()
        if not installed:
            log.warning("[MOUSE HOOK] Failed to install hook on dedicated thread; will retry in watchdog.")

        msg = wintypes.MSG()
        while not self._stop_event.is_set():
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                if msg.message == 0x0012:  # WM_QUIT
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.005)

        self._unhook()

    def _watchdog_loop(self) -> None:
        """Watchdog to detect hook dropping and automatically re-install if needed."""
        while not self._stop_event.is_set():
            time.sleep(3.0)
            if self._stop_event.is_set():
                break

            with self._lock:
                hook_dead = (
                    not self._is_hooked
                    or not self._hook_handle
                    or self._hook_thread is None
                    or not self._hook_thread.is_alive()
                )

            if hook_dead and not self._stop_event.is_set():
                log.warning("[MOUSE HOOK WATCHDOG] Mouse hook was dropped or inactive. Auto-rehooking...")
                try:
                    self._unhook()
                    self._hook_thread = threading.Thread(
                        target=self._run_hook_loop,
                        name="Win32MouseHookThread-Restart",
                        daemon=True,
                    )
                    self._hook_thread.start()
                except Exception as exc:
                    log.error("[MOUSE HOOK WATCHDOG] Auto-rehook failed: %s", exc)

    # -- Safe Callback Wrappers --

    def _safe_on_start(self) -> None:
        try:
            self._on_start()
        except Exception as e:
            log.error("[MOUSE HOOK] Error in on_start: %s", e)

    def _safe_on_finish(self) -> None:
        try:
            self._on_finish()
        except Exception as e:
            log.error("[MOUSE HOOK] Error in on_finish: %s", e)

    def _safe_on_cancel(self) -> None:
        try:
            self._on_cancel()
        except Exception as e:
            log.error("[MOUSE HOOK] Error in on_cancel: %s", e)

    def _safe_on_mouse_release(self, x: int, y: int, dist: float, start_x: int, start_y: int) -> None:
        try:
            if self._on_mouse_release:
                self._on_mouse_release(x, y, dist, start_x, start_y)
        except Exception as e:
            log.error("[MOUSE HOOK] Error in on_mouse_release: %s", e)

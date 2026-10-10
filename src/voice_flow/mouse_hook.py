"""Native Win32 Low-Level Mouse Hook (WH_MOUSE_LL) with Auto-Rehook Watchdog.

Features:
- 64-bit safe Win32 Low-Level Mouse Hook running on a dedicated message-pump thread.
- Minimal hook procedure that queues work and returns immediately.
- Auto-rehook watchdog: automatically detects if Windows drops the hook and silently reinstalls it.
- Middle-click interception: supports push-to-talk hold (>0.30s) and toggle tap (<0.30s), suppressing autoscroll cursor.
- Left-click drag tracking: detects text selection drags (>= 6px) with debounced event dispatching.
- Safe fallback to pynput if raw Win32 hook fails to initialize.
"""

from __future__ import annotations

from voice_flow.hotkey_config import shortcut_capture_active

import ctypes
from voice_flow.platform.wincompat import wintypes, windll, WINFUNCTYPE, IS_WINDOWS
import logging
import queue
import threading
import time
from typing import Any, Callable

log = logging.getLogger(__name__)
_selection_context = threading.local()


def selection_event_is_current() -> bool:
    """Whether the selection callback currently running is still the latest."""
    context = getattr(_selection_context, "context", None)
    # Five-argument/direct callers predate hook epochs and remain valid.
    return context is None or context[1] is None or context[0]._selection_epoch == context[1]

# Win32 Constants
WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MOUSEMOVE = 0x0200
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MBUTTONDBLCLK = 0x0209
WM_NCMBUTTONDOWN = 0x00A7
WM_NCMBUTTONUP = 0x00A8
WM_NCMBUTTONDBLCLK = 0x00A9

user32 = windll.user32
kernel32 = windll.kernel32

# Structs for low-level mouse hook
class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),  # 64-bit safe ULONG_PTR
    ]


# Exact 64-bit safe types for Windows LowLevelMouseProc
LRESULT = ctypes.c_ssize_t
HOOKPROC = WINFUNCTYPE(
    LRESULT,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)

if IS_WINDOWS:
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = wintypes.HHOOK

    user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL

    user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallNextHookEx.restype = LRESULT


def _get_cursor_pos() -> tuple[int, int] | None:
    if IS_WINDOWS and user32:
        try:
            pt = wintypes.POINT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                return (int(pt.x), int(pt.y))
        except Exception:
            pass
    return None


class Win32MouseHook:
    """Robust Win32 Low-Level Mouse Hook with auto-recovery and thread safety."""

    def __init__(
        self,
        on_start: Callable[[], None],
        on_finish: Callable[[], None],
        on_cancel: Callable[[], None],
        on_mouse_release: Callable[..., None] | None = None,
        on_deferred_paste: Callable[[], None] | None = None,
        has_pending_deferred_paste: Callable[[], bool] | None = None,
    ) -> None:
        self._on_start = on_start
        self._on_finish = on_finish
        self._on_cancel = on_cancel
        self._on_mouse_release = on_mouse_release
        self._on_deferred_paste = on_deferred_paste
        self._has_pending_deferred_paste = has_pending_deferred_paste

        self._hook_handle: int | None = None
        self._hook_proc_ptr: object | None = None  # Prevent garbage collection of callback
        self._hook_thread: threading.Thread | None = None
        self._hook_thread_id: int = 0
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._action_lock = threading.Lock()

        # Recording-control work is isolated from potentially slow selection
        # work.  A hook callback never blocks on either queue.
        self._control_queue: queue.Queue[tuple[Callable[..., Any], tuple[Any, ...]]] = queue.Queue(maxsize=64)
        # Only the latest completed drag can be useful while a selection read
        # is in progress.  Keep at most one pending drag.
        self._selection_queue: queue.Queue[tuple[Callable[..., Any], tuple[Any, ...]]] = queue.Queue(maxsize=1)
        self._urgent_control: tuple[Callable[..., Any], tuple[Any, ...]] | None = None
        self._control_overflow_count = 0
        self._worker_stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._selection_worker_thread: threading.Thread | None = None

        # State tracking
        self._is_recording = False
        self._mbutton_press_time: float = 0.0
        self._is_left_down: bool = False
        self._selection_epoch: int = 0
        self._callback_error_count = 0
        self._last_left_down_x: int = 0
        self._last_left_down_y: int = 0
        self._last_event_time: float = time.time()
        self._last_transition_time: float = 0.0
        self._is_hooked = False

        # Cached trigger mode. The hook proc must do zero I/O (fresh sqlite
        # connection per call risks LowLevelHooksTimeout drops), so the mode
        # is read once at start and refreshed outside the hook thread via
        # refresh_trigger_mode() (watchdog tick).
        self._trigger_mode = "hybrid"
        self._trigger_mode_last_refresh = 0.0
        self._enabled = True

        # Watchdog
        self._watchdog_thread: threading.Thread | None = None

    def set_enabled(self, enabled: bool) -> None:
        """Dynamically enable or disable middle-click dictation interception."""
        with self._lock:
            self._enabled = bool(enabled)

    def is_enabled(self) -> bool:
        """Check if middle-click dictation interception is enabled."""
        with self._lock:
            return self._enabled and self._trigger_mode != "disabled"

    def start(self) -> None:
        """Start the Win32 mouse hook thread and watchdog."""
        if not IS_WINDOWS:
            log.info("[MOUSE HOOK] Non-Windows platform; mouse hook inactive.")
            return
        with self._lock:
            if self._hook_thread and self._hook_thread.is_alive():
                return
            self._stop_event.clear()
            self.refresh_trigger_mode(force=True)
            self._start_workers_locked()
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
        # Invalidate clipboard reads already running on the selection worker.
        self._selection_epoch += 1
        if not IS_WINDOWS:
            self._stop_event.set()
            self._stop_workers()
            return
        self._stop_event.set()
        # _unhook owns the lifecycle lock.  Taking it here first deadlocks
        # because it is intentionally a non-reentrant Lock.
        self._unhook()
        self._stop_workers()
        log.info("[MOUSE HOOK] Win32 mouse hook stopped.")

    def set_recording_state(self, recording: bool) -> None:
        """Synchronize current recording state."""
        with self._lock:
            self._is_recording = recording

    def refresh_trigger_mode(self, force: bool = False) -> None:
        """Refresh the cached trigger mode from storage (call OFF the hook thread).

        Throttled to at most once per 5s unless forced, so settings changes
        propagate without adding I/O to the hook callback.
        """
        now = time.time()
        if not force and (now - self._trigger_mode_last_refresh) < 5.0:
            return
        try:
            from voice_flow.storage import storage as _storage
            mode = _storage.get_setting("dictation_trigger_mode", "hybrid")
            middle_enabled = bool(_storage.get_setting("middle_click_enabled", True))
            self._trigger_mode_last_refresh = now
            if mode in ("ptt_only", "toggle_only", "hybrid", "disabled"):
                self._trigger_mode = mode
            self._enabled = middle_enabled and (self._trigger_mode != "disabled")
        except Exception:
            pass

    def is_healthy(self) -> bool:
        """Check whether the mouse hook is currently active and healthy."""
        if not IS_WINDOWS:
            return True
        with self._lock:
            return self._is_hooked and self._hook_handle is not None and self._hook_thread is not None and self._hook_thread.is_alive()

    # -- Internal Hook Lifecycle --

    def _install_hook(self) -> bool:
        """Install WH_MOUSE_LL hook with a 64-bit-safe module handle."""
        self._capture_middle_passthrough = False
        try:
            def _low_level_mouse_proc(nCode: int, wParam: int, lParam: int) -> int:
                if nCode >= 0:
                    try:
                        self._last_event_time = time.time()
                        msg = int(wParam)

                        # Middle button down / double-click
                        if msg in (WM_MBUTTONDOWN, WM_NCMBUTTONDOWN, WM_MBUTTONDBLCLK, WM_NCMBUTTONDBLCLK):
                            # Capture leases let the physical middle-button pair pass through.
                            if shortcut_capture_active():
                                self._capture_middle_passthrough = True
                                self._mbutton_press_time = 0.0
                                return user32.CallNextHookEx(None, nCode, wParam, lParam)
                            if not getattr(self, "_enabled", True) or self._trigger_mode == "disabled":
                                return user32.CallNextHookEx(None, nCode, wParam, lParam)
                            now = time.time()
                            # Contact chatter debounce: ignore down messages within 260ms of previous transition
                            if now - getattr(self, "_last_transition_time", 0.0) < 0.26:
                                return 1

                            dictation_mode = self._trigger_mode

                            # This callback runs on Windows' low-level hook
                            # path.  It must neither wait for a lock nor start
                            # a thread.  CPython state assignments are atomic
                            # under the GIL; worker callbacks reconcile state.
                            self._is_left_down = False
                            self._mbutton_press_time = now
                            if dictation_mode == "ptt_only":
                                # Strict Push-to-Talk: pressing down always starts recording
                                if not self._is_recording:
                                    self._is_recording = True
                                    self._last_transition_time = now
                                    self._dispatch_action(self._safe_on_start)
                            elif dictation_mode == "toggle_only":
                                # Strict Tap-to-Toggle: pressing toggles recording state
                                if not self._is_recording:
                                    self._is_recording = True
                                    self._last_transition_time = now
                                    self._dispatch_action(self._safe_on_start)
                                elif msg not in (WM_MBUTTONDBLCLK, WM_NCMBUTTONDBLCLK):
                                    self._is_recording = False
                                    self._last_transition_time = now
                                    self._dispatch_action(self._safe_on_finish)
                            else:
                                # Hybrid mode (default):
                                if not self._is_recording:
                                    self._is_recording = True
                                    self._last_transition_time = now
                                    self._dispatch_action(self._safe_on_start)
                                elif msg not in (WM_MBUTTONDBLCLK, WM_NCMBUTTONDBLCLK):
                                    self._is_recording = False
                                    self._last_transition_time = now
                                    self._dispatch_action(self._safe_on_finish)
                            # Suppress autoscroll popup cursor
                            return 1

                        # Middle button up
                        elif msg in (WM_MBUTTONUP, WM_NCMBUTTONUP):
                            # Preserve the paired release even if the capture lease expired.
                            if getattr(self, "_capture_middle_passthrough", False):
                                self._capture_middle_passthrough = False
                                self._mbutton_press_time = 0.0
                                return user32.CallNextHookEx(None, nCode, wParam, lParam)
                            if not getattr(self, "_enabled", True) or self._trigger_mode == "disabled":
                                return user32.CallNextHookEx(None, nCode, wParam, lParam)
                            dictation_mode = self._trigger_mode

                            now = time.time()
                            press_dur = now - self._mbutton_press_time
                            # For PTT only or Hybrid: release stops recording if held
                            if dictation_mode == "ptt_only":
                                if self._is_recording:
                                    self._is_recording = False
                                    self._last_transition_time = now
                                    self._dispatch_action(self._safe_on_finish)
                            elif dictation_mode == "toggle_only":
                                # In toggle-only, button release does nothing
                                pass
                            else:
                                # Hybrid mode: If held > 0.38s (push-to-talk hold), finish on release.
                                # Quick taps (< 0.38s) stay in toggle recording without being aborted.
                                if self._is_recording and press_dur > 0.38:
                                    self._is_recording = False
                                    self._last_transition_time = now
                                    self._dispatch_action(self._safe_on_finish)
                            # Suppress autoscroll popup cursor
                            return 1

                        # Right button up -> Trigger deferred click-to-paste only if pending
                        elif msg == WM_RBUTTONUP:
                            if self._on_deferred_paste and not self._is_recording and callable(self._has_pending_deferred_paste):
                                try:
                                    if self._has_pending_deferred_paste():
                                        self._dispatch_action(self._on_deferred_paste)
                                        return 1  # Suppress context menu opening on the deferred paste click
                                except Exception as e:
                                    log.debug("[MOUSE HOOK] Deferred paste check error: %s", e)

                        # Left button drag tracking for text selection
                        elif msg == WM_LBUTTONDOWN:
                            if lParam:
                                ms = MSLLHOOKSTRUCT.from_address(lParam)
                                self._is_left_down = True
                                self._last_left_down_x = ms.pt.x
                                self._last_left_down_y = ms.pt.y
                        elif msg == WM_LBUTTONUP:
                            if lParam and self._on_mouse_release:
                                ms = MSLLHOOKSTRUCT.from_address(lParam)
                                x, y = ms.pt.x, ms.pt.y
                                if self._is_left_down:
                                    dx = x - self._last_left_down_x
                                    dy = y - self._last_left_down_y
                                    drag_dist = (dx * dx + dy * dy) ** 0.5
                                    start_x = self._last_left_down_x
                                    start_y = self._last_left_down_y
                                    self._is_left_down = False
                                else:
                                    drag_dist = 0.0
                                    start_x = x
                                    start_y = y
                                self._selection_epoch += 1
                                selection_epoch = self._selection_epoch
                                # Ordinary clicks clear stale selection UI and
                                # invalidate an in-flight capture.  They use the
                                # control worker so a slow drag read cannot
                                # delay that invalidation.
                                if drag_dist < 16.0:
                                    self._dispatch_action(self._safe_on_mouse_release, x, y, drag_dist, start_x, start_y, selection_epoch)
                                else:
                                    self._enqueue_selection(self._safe_on_mouse_release, x, y, drag_dist, start_x, start_y, selection_epoch)

                    except Exception as e:
                        # Logging handlers may perform I/O.  Keep the native
                        # callback bounded even on malformed input.
                        self._callback_error_count += 1

                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            self._hook_proc_ptr = HOOKPROC(_low_level_mouse_proc)
            h_mod = kernel32.GetModuleHandleW(None)
            self._hook_handle = user32.SetWindowsHookExW(
                WH_MOUSE_LL,
                self._hook_proc_ptr,
                h_mod,
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

    def _unhook(self, target_thread_id: int | None = None) -> None:
        """Safely unhook the mouse hook."""
        with self._lock:
            # If target_thread_id is given, only unhook if it matches the active hook thread
            # An old message-pump thread must never tear down a hook installed
            # by a newer watchdog generation.  A cleared id also belongs to a
            # different lifecycle generation, so it must not be treated as a
            # wildcard match.
            if target_thread_id is not None and self._hook_thread_id != target_thread_id:
                return
            if self._hook_handle:
                try:
                    user32.UnhookWindowsHookEx(self._hook_handle)
                except Exception:
                    pass
                self._hook_handle = None
            self._is_hooked = False
            self._is_left_down = False
            tid = self._hook_thread_id
            self._hook_thread_id = 0
            if tid:
                try:
                    user32.PostThreadMessageW(tid, 0x0012, 0, 0)  # WM_QUIT = 0x0012
                except Exception:
                    pass

    def _run_hook_loop(self) -> None:
        """Dedicated message-pump loop for the low-level hook."""
        thread_id = kernel32.GetCurrentThreadId()
        with self._lock:
            self._hook_thread_id = thread_id
        installed = self._install_hook()
        if not installed:
            log.warning("[MOUSE HOOK] Failed to install hook on dedicated thread; will retry in watchdog.")

        msg = wintypes.MSG()
        while not self._stop_event.is_set():
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0 or msg.message == 0x0012:  # 0, -1, or WM_QUIT
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        self._unhook(target_thread_id=thread_id)

    def _watchdog_loop(self) -> None:
        """Watchdog to detect hook dropping and automatically re-install if needed."""
        last_pt = None
        last_motion_time = time.time()
        while not self._stop_event.is_set():
            time.sleep(2.0)
            if self._stop_event.is_set():
                break

            # Lazy periodic refresh of the trigger-mode cache (off hook thread).
            self.refresh_trigger_mode()
            now = time.time()

            try:
                cur_pt = _get_cursor_pos()
                if cur_pt is not None and cur_pt != last_pt:
                    last_pt = cur_pt
                    last_motion_time = now
            except Exception:
                pass

            with self._lock:
                hook_dead = (
                    not self._is_hooked
                    or not self._hook_handle
                    or self._hook_thread is None
                    or not self._hook_thread.is_alive()
                )
                # If mouse has moved in last 1.5s but hook received 0 events for > 4.0s:
                if not hook_dead and (now - last_motion_time < 1.5) and (now - self._last_event_time > 4.0):
                    hook_dead = True

            if hook_dead and not self._stop_event.is_set():
                log.warning("[MOUSE HOOK WATCHDOG] Mouse hook was dropped or inactive. Auto-rehooking...")
                try:
                    old_thread = self._hook_thread
                    self._unhook()
                    if old_thread and old_thread.is_alive() and old_thread is not threading.current_thread():
                        old_thread.join(timeout=0.3)
                    self._hook_thread = threading.Thread(
                        target=self._run_hook_loop,
                        name="Win32MouseHookThread-Restart",
                        daemon=True,
                    )
                    self._hook_thread.start()
                except Exception as exc:
                    log.error("[MOUSE HOOK WATCHDOG] Auto-rehook failed: %s", exc)

    # -- Safe Callback Wrappers --

    def _start_workers_locked(self) -> None:
        """Create fixed workers during lifecycle start, never from a hook callback."""
        if self._worker_stop_event.is_set():
            self._control_queue = queue.Queue(maxsize=64)
            self._selection_queue = queue.Queue(maxsize=1)
            self._urgent_control = None
            self._worker_stop_event = threading.Event()
        if not self._worker_thread or not self._worker_thread.is_alive():
            self._worker_thread = threading.Thread(
                target=self._worker_loop, args=(self._control_queue, self._worker_stop_event), name="Win32MouseHookControlWorker", daemon=True
            )
            self._worker_thread.start()
        if not self._selection_worker_thread or not self._selection_worker_thread.is_alive():
            self._selection_worker_thread = threading.Thread(
                target=self._selection_worker_loop, args=(self._selection_queue, self._worker_stop_event), name="Win32MouseHookSelectionWorker", daemon=True
            )
            self._selection_worker_thread.start()

    def _worker_loop(self, event_queue: queue.Queue[tuple[Callable[..., Any], tuple[Any, ...]]], worker_stop: threading.Event) -> None:
        self._run_queue(event_queue, worker_stop)

    def _selection_worker_loop(self, event_queue: queue.Queue[tuple[Callable[..., Any], tuple[Any, ...]]], worker_stop: threading.Event) -> None:
        self._run_queue(event_queue, worker_stop)

    def _run_queue(self, event_queue: queue.Queue[tuple[Callable[..., Any], tuple[Any, ...]]], worker_stop: threading.Event) -> None:
        while True:
            if event_queue is self._control_queue and self._callback_error_count:
                count = self._callback_error_count
                self._callback_error_count = 0
                log.debug("[MOUSE HOOK] Ignored %d callback errors.", count)
            if event_queue is self._control_queue and self._control_overflow_count:
                count = self._control_overflow_count
                self._control_overflow_count = 0
                log.warning("[MOUSE HOOK] Refused %d overloaded non-terminal control events.", count)
            # A saturated control queue must still retain a finish/cancel.
            # Coalesce repeated terminal operations: one is sufficient to
            # restore the recording state, and this path never blocks a hook.
            if event_queue is self._control_queue and self._urgent_control is not None:
                fn, args = self._urgent_control
                self._urgent_control = None
                try:
                    fn(*args)
                except Exception as e:
                    log.error("[MOUSE HOOK WORKER] Error in urgent control event: %s", e)
                continue
            try:
                fn, args = event_queue.get(timeout=0.2)
            except queue.Empty:
                if worker_stop.is_set():
                    return
                continue
            try:
                fn(*args)
            except Exception as e:
                log.error("[MOUSE HOOK WORKER] Error in worker event: %s", e)
            finally:
                event_queue.task_done()

    def _dispatch_action(self, fn: Callable[..., Any], *args: Any) -> bool:
        """Queue control work without locking, blocking, or spawning.

        Terminal events are coalesced into a single urgent slot if the bounded
        queue is full.  Starts are refused under overload, undoing their
        optimistic hook-side recording state so the next press can retry.
        """
        try:
            self._control_queue.put_nowait((fn, args))
            return True
        except queue.Full:
            if fn == self._safe_on_finish or fn == self._safe_on_cancel:
                # A terminal event cuts off obsolete queued starts.  Let any
                # already-running callback complete, then run this finish on
                # the same control worker; never permit a later queued start
                # to re-arm recording after the release.
                while True:
                    try:
                        self._control_queue.get_nowait()
                        self._control_queue.task_done()
                    except queue.Empty:
                        break
                self._urgent_control = (fn, args)
                return True
            if fn == self._safe_on_start:
                self._is_recording = False
            self._control_overflow_count += 1
            return False

    def _enqueue_selection(self, fn: Callable[..., Any], *args: Any) -> None:
        """Bound stale selection work and keep Queue accounting balanced."""
        try:
            self._selection_queue.put_nowait((fn, args))
        except queue.Full:
            try:
                self._selection_queue.get_nowait()
                self._selection_queue.task_done()
            except queue.Empty:
                return
            try:
                self._selection_queue.put_nowait((fn, args))
            except queue.Full:
                pass

    def _stop_workers(self) -> None:
        """Wake lifecycle-owned workers; only stale selection work is discarded."""
        self._worker_stop_event.set()
        for event_queue in (self._control_queue, self._selection_queue):
            while True:
                try:
                    event_queue.get_nowait()
                    event_queue.task_done()
                except queue.Empty:
                    break
        for worker in (self._worker_thread, self._selection_worker_thread):
            if worker and worker is not threading.current_thread():
                worker.join(timeout=1.0)
        # A blocked user callback may outlive the bounded join, but it retains
        # its old queue and receives no further work after a restart.
        self._worker_thread = None
        self._selection_worker_thread = None

    def _safe_on_start(self) -> None:
        with self._action_lock:
            try:
                started = self._on_start()
                if started is False:
                    # Mirror hotkeys._safe_on_start nack handling: the hook proc
                    # optimistically sets _is_recording before invoking the
                    # coordinator. Clear it on a failed start or the next
                    # middle-click takes the finish branch and the trigger looks dead.
                    with self._lock:
                        self._is_recording = False
            except Exception as e:
                log.error("[MOUSE HOOK] Error in on_start: %s", e)
                with self._lock:
                    self._is_recording = False

    def _safe_on_finish(self) -> None:
        with self._action_lock:
            try:
                self._on_finish()
            except Exception as e:
                log.error("[MOUSE HOOK] Error in on_finish: %s", e)
            finally:
                with self._lock:
                    self._is_recording = False

    def _safe_on_cancel(self) -> None:
        with self._action_lock:
            try:
                self._on_cancel()
            except Exception as e:
                log.error("[MOUSE HOOK] Error in on_cancel: %s", e)
            finally:
                with self._lock:
                    self._is_recording = False

    def _safe_on_mouse_release(
        self, x: int, y: int, dist: float, start_x: int, start_y: int, selection_epoch: int | None = None
    ) -> None:
        try:
            if self._on_mouse_release:
                previous = getattr(_selection_context, "context", None)
                _selection_context.context = (self, selection_epoch)
                try:
                    self._on_mouse_release(x, y, dist, start_x, start_y)
                finally:
                    _selection_context.context = previous
        except Exception as e:
            log.error("[MOUSE HOOK] Error in on_mouse_release: %s", e)

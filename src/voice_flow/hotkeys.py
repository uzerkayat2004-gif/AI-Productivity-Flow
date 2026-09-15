"""Global input listeners for Voice Flow using native Win32 hooks and pynput fallback.

- Triggers dictation on middle mouse button hold/release (scroll button click).
- Suppresses native middle-click drag autoscroll icon while keeping normal wheel scrolling working 100%.
- Triggers dictation on Ctrl+Win / Win+Ctrl shortcut while suppressing Start menu popup.
- Auto-rehooks and recovers if Windows drops low-level hooks or after workstation lock/sleep.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
import threading
import time
from typing import Any, Callable

from pynput import keyboard

from voice_flow.injector import VF_SYNTHETIC_EXTRA_INFO, is_synthetic_input_active
from voice_flow.mouse_hook import Win32MouseHook

log = logging.getLogger(__name__)

# Win32 Virtual Key Codes
VK_CONTROL = 0x11
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_SHIFT = 0x10
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_TAB = 0x09
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_NONAME = 0xE8

# Win32 Hook Constants
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

# Win32 Mouse Messages
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(
    LRESULT,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)

try:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL
    user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallNextHookEx.restype = LRESULT
except Exception:
    user32 = None
    kernel32 = None


def parse_hotkey_string(hotkey_str: str) -> dict[str, Any]:
    """Parse a hotkey combination string like 'Ctrl+Win', 'Alt+Space', 'Double Ctrl', 'Double Alt', 'F8'."""
    raw = (hotkey_str or "").strip()
    is_double = False
    cleaned = raw
    if cleaned.lower().startswith("double "):
        is_double = True
        cleaned = cleaned[7:].strip()
    elif cleaned.lower().startswith("double-"):
        is_double = True
        cleaned = cleaned[7:].strip()

    parts = [p.strip().lower() for p in cleaned.replace("-", "+").split("+") if p.strip()]
    modifiers = set()
    base_key = None
    for part in parts:
        if part in ("ctrl", "control"):
            modifiers.add("ctrl")
        elif part in ("alt", "menu"):
            modifiers.add("alt")
        elif part in ("shift",):
            modifiers.add("shift")
        elif part in ("win", "cmd", "windows", "super"):
            modifiers.add("win")
        else:
            base_key = part
    return {
        "raw": hotkey_str,
        "is_double": is_double,
        "modifiers": modifiers,
        "base_key": base_key,
        "parts": parts,
    }


def _vk_for_key_name(name: str | None) -> int | None:
    if not name:
        return None
    name = name.lower().strip()
    special_keys = {
        "space": 0x20,
        "tab": 0x09,
        "enter": 0x0D,
        "return": 0x0D,
        "esc": 0x1B,
        "escape": 0x1B,
        "caps_lock": 0x14,
        "capslock": 0x14,
        "insert": 0x2D,
        "delete": 0x2E,
        "del": 0x2E,
        "home": 0x24,
        "end": 0x23,
        "pageup": 0x21,
        "page_up": 0x21,
        "pagedown": 0x22,
        "page_down": 0x22,
        "backquote": 0xC0,
        "`": 0xC0,
        "tilde": 0xC0,
        "~": 0xC0,
        "scroll_lock": 0x91,
        "scrolllock": 0x91,
        "pause": 0x13,
        "backspace": 0x08,
        "ctrl": 0x11,
        "control": 0x11,
        "alt": 0x12,
        "shift": 0x10,
        "win": 0x5B,
    }
    if name in special_keys:
        return special_keys[name]
    if name.startswith("f") and name[1:].isdigit():
        fnum = int(name[1:])
        if 1 <= fnum <= 24:
            return 0x70 + (fnum - 1)
    if len(name) == 1:
        c = name.upper()
        if "A" <= c <= "Z" or "0" <= c <= "9":
            return ord(c)
    return None


def _is_key_down(vk: int | None) -> bool:
    if vk is None:
        return False
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return False


def _key_matches_name(key: keyboard.Key | keyboard.KeyCode | None, name: str | None) -> bool:
    if key is None or not name:
        return False
    name = name.lower().strip()
    if name == "space" and key == keyboard.Key.space:
        return True
    if name == "tab" and key == keyboard.Key.tab:
        return True
    if name in ("enter", "return") and key == keyboard.Key.enter:
        return True
    if name in ("esc", "escape") and key == keyboard.Key.esc:
        return True
    if hasattr(key, "name") and key.name and key.name.lower() == name:
        return True
    if hasattr(key, "char") and key.char:
        if key.char.lower() == name:
            return True
        # Handle ASCII control characters when Ctrl is held (e.g. \x04 for 'd')
        if len(key.char) == 1 and ord(key.char) < 32 and len(name) == 1:
            if chr(ord(key.char) + 64).lower() == name:
                return True
    vk = getattr(key, "vk", None)
    expected_vk = _vk_for_key_name(name)
    if vk is not None and expected_vk is not None and vk == expected_vk:
        return True
    return False


def _is_ctrl_down() -> bool:
    """Check physical hardware state of Control key on Windows."""
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
    except Exception:
        return False


def _is_win_down() -> bool:
    """Check physical hardware state of Windows Key (Left or Right) on Windows."""
    try:
        user32 = ctypes.windll.user32
        return bool((user32.GetAsyncKeyState(VK_LWIN) & 0x8000) or (user32.GetAsyncKeyState(VK_RWIN) & 0x8000))
    except Exception:
        return False


def _is_shift_down() -> bool:
    """Check physical hardware state of Shift key on Windows."""
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)
    except Exception:
        return False


def _is_alt_down() -> bool:
    """Check physical hardware state of Alt (Menu) key on Windows."""
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(VK_MENU) & 0x8000)
    except Exception:
        return False


def _suppress_win_start_menu() -> None:
    """Send a dummy key event to prevent Windows from opening the Start menu on Win key release."""
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(VK_CONTROL, 0, 0, VF_SYNTHETIC_EXTRA_INFO)
        user32.keybd_event(VK_CONTROL, 0, 2, VF_SYNTHETIC_EXTRA_INFO)  # KEYEVENTF_KEYUP = 2
        user32.keybd_event(VK_NONAME, 0, 0, VF_SYNTHETIC_EXTRA_INFO)
        user32.keybd_event(VK_NONAME, 0, 2, VF_SYNTHETIC_EXTRA_INFO)
    except Exception:
        pass


class Win32KeyboardHook:
    """Robust Win32 Low-Level Keyboard Hook (WH_KEYBOARD_LL) with auto-recovery and thread safety.

    Runs on a dedicated Win32 message-pump thread to achieve < 0.1ms latency and eliminate
    queue lag or modifier release delays.
    """

    def __init__(self, on_key: Callable[[int, bool, bool, int], bool | None]) -> None:
        self._on_key = on_key
        self._hook_handle: int | None = None
        self._hook_proc_ptr: object | None = None
        self._hook_thread: threading.Thread | None = None
        self._hook_thread_id: int = 0
        self._stop_event = threading.Event()
        self._installed_event = threading.Event()
        self._lock = threading.Lock()
        self._is_hooked = False
        self._last_event_time: float = time.time()

    def start(self) -> bool:
        """Start the Win32 keyboard hook on a dedicated thread."""
        with self._lock:
            if self._hook_thread and self._hook_thread.is_alive():
                return True
            if user32 is None or kernel32 is None:
                return False
            self._stop_event.clear()
            self._installed_event.clear()
            self._hook_thread = threading.Thread(
                target=self._run_hook_loop,
                name="Win32KeyboardHookThread",
                daemon=True,
            )
            self._hook_thread.start()

        # Wait briefly for installation
        self._installed_event.wait(timeout=0.5)
        return self.is_healthy()

    def stop(self) -> None:
        """Stop the keyboard hook and release Win32 resources."""
        self._stop_event.set()
        with self._lock:
            self._unhook()
        log.info("[KEYBOARD HOOK] Win32 keyboard hook stopped.")

    def is_healthy(self) -> bool:
        """Check whether the keyboard hook is currently active and healthy."""
        with self._lock:
            return (
                self._is_hooked
                and self._hook_handle is not None
                and self._hook_thread is not None
                and self._hook_thread.is_alive()
            )

    def _install_hook(self) -> bool:
        if user32 is None or kernel32 is None:
            self._is_hooked = False
            return False
        try:
            def _low_level_keyboard_proc(nCode: int, wParam: int, lParam: int) -> int:
                if nCode >= 0 and lParam:
                    try:
                        self._last_event_time = time.time()
                        msg = int(wParam)
                        kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                        vk = int(kb.vkCode)
                        extra = int(kb.dwExtraInfo)

                        # Pass through synthetic events and dummy suppression keys immediately
                        if extra == VF_SYNTHETIC_EXTRA_INFO or is_synthetic_input_active() or vk == VK_NONAME:
                            return user32.CallNextHookEx(None, nCode, wParam, lParam)

                        is_down = msg in (WM_KEYDOWN, WM_SYSKEYDOWN)
                        is_up = msg in (WM_KEYUP, WM_SYSKEYUP)

                        if is_down or is_up:
                            suppress = self._on_key(vk, is_down, is_up, extra)
                            if suppress:
                                return 1
                    except Exception as e:
                        log.debug("[KEYBOARD HOOK] Error in hook callback: %s", e)
                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            self._hook_proc_ptr = HOOKPROC(_low_level_keyboard_proc)
            self._hook_handle = user32.SetWindowsHookExW(
                WH_KEYBOARD_LL,
                self._hook_proc_ptr,
                0,
                0,
            )
            if not self._hook_handle:
                err = kernel32.GetLastError()
                log.warning("[KEYBOARD HOOK] SetWindowsHookExW failed with error code: %d", err)
                self._is_hooked = False
                return False

            self._is_hooked = True
            log.info("[KEYBOARD HOOK] WH_KEYBOARD_LL hook successfully installed (handle=0x%x).", self._hook_handle)
            return True
        except Exception as exc:
            log.warning("[KEYBOARD HOOK] Hook installation exception: %s", exc)
            self._is_hooked = False
            return False

    def _unhook(self) -> None:
        if self._hook_handle and user32 is not None:
            try:
                user32.UnhookWindowsHookEx(self._hook_handle)
            except Exception:
                pass
            self._hook_handle = None
        self._is_hooked = False
        if self._hook_thread_id and user32 is not None:
            try:
                user32.PostThreadMessageW(self._hook_thread_id, 0x0012, 0, 0)
            except Exception:
                pass

    def _run_hook_loop(self) -> None:
        if kernel32 is None or user32 is None:
            self._installed_event.set()
            return
        self._hook_thread_id = kernel32.GetCurrentThreadId()
        installed = self._install_hook()
        self._installed_event.set()
        if not installed:
            return

        msg = wintypes.MSG()
        while not self._stop_event.is_set():
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0 or msg.message == 0x0012:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        self._unhook()


class InputTriggerListener:
    """Listens for global mouse (middle button) and keyboard events with self-healing."""

    def __init__(
        self,
        on_start: Callable[[], None],
        on_finish: Callable[[], None],
        on_cancel: Callable[[], None],
        on_paste_last: Callable[[], None] | None = None,
        on_copy_last: Callable[[], None] | None = None,
        on_audio_flow: Callable[[], None] | None = None,
        on_mouse_release: Callable[..., None] | None = None,
        has_pending_deferred_paste: Callable[[], bool] | None = None,
    ) -> None:
        self._on_start = on_start
        self._on_finish = on_finish
        self._on_cancel = on_cancel
        self._on_paste_last = on_paste_last
        self._on_copy_last = on_copy_last
        self._on_audio_flow = on_audio_flow
        self._on_mouse_release = on_mouse_release
        self._has_pending_deferred_paste = has_pending_deferred_paste

        # Primary Win32 mouse hook
        self._mouse_hook = Win32MouseHook(
            on_start=self._on_start,
            on_finish=self._on_finish,
            on_cancel=self._on_cancel,
            on_mouse_release=self._on_mouse_release,
            on_deferred_paste=self._on_paste_last,
            has_pending_deferred_paste=self._has_pending_deferred_paste,
        )

        self._key_listener: keyboard.Listener | None = None
        self._pressed_keys: set[keyboard.Key | keyboard.KeyCode] = set()
        self._lock = threading.Lock()
        self._action_lock = threading.Lock()
        self._is_recording = False
        self._hotkey_triggered = False
        self._alt_space_triggered = False
        self._alt_tab_triggered = False
        self._custom_hotkey_triggered = False
        self._hotkey_press_time: float = 0.0
        self._stop_event = threading.Event()
        self._watchdog_thread: threading.Thread | None = None

        # Double-tap Control and Hold Control tracking
        self._last_ctrl_release_time: float = 0.0
        self._ctrl_press_time: float = 0.0
        self._ctrl_hold_triggered: bool = False
        self._ctrl_toggle_mode_active: bool = False
        self._ctrl_check_timer: threading.Timer | None = None
        self._ctrl_chord_active: bool = False
        self._win_suppress_needed: bool = False
        self._ctrl_just_toggled_off: bool = False

        # Native Win32 keyboard hook
        self._keyboard_hook: Win32KeyboardHook | None = None
        try:
            if user32 is not None and kernel32 is not None:
                self._keyboard_hook = Win32KeyboardHook(self._on_native_key)
        except Exception:
            self._keyboard_hook = None

        # User-configurable hotkey settings
        self._hotkey_trigger: str = "ctrl_win"
        self._custom_hotkey_str: str = "Alt+Space"
        self._parsed_custom_keys: dict[str, Any] = parse_hotkey_string("Alt+Space")
        self._custom_trigger_type: str = "hold"
        self._last_custom_release_time: float = 0.0
        self._trigger_mode: str = "hybrid"
        self._middle_click_enabled: bool = True
        self._ctrl_key_dictation_enabled: bool = False

        try:
            self.reload_config()
        except Exception:
            pass

    def start(self) -> None:
        """Start listening for global mouse and keyboard events."""
        log.info("[INPUT] Initializing global mouse hook & keyboard shortcuts...")
        self._stop_event.clear()

        # Start Win32 mouse hook
        try:
            self._mouse_hook.start()
        except Exception as e:
            log.error("[INPUT] Failed to start Win32 mouse hook: %s", e)

        # Start native Win32 keyboard hook (dedicated thread for instant <0.1ms latency)
        hook_started = False
        if self._keyboard_hook is not None:
            try:
                hook_started = self._keyboard_hook.start()
            except Exception as e:
                log.error("[INPUT] Failed to start native Win32 keyboard hook: %s", e)
                hook_started = False

        # Fallback to pynput if native hook could not start
        if not hook_started:
            log.info("[INPUT] Native Win32 keyboard hook inactive; falling back to pynput.")
            self._start_key_listener()
        else:
            log.info("[INPUT] Native Win32 low-level keyboard hook active.")

        # Start watchdog to keep keyboard and mouse hooks healthy
        if not self._watchdog_thread or not self._watchdog_thread.is_alive():
            self._watchdog_thread = threading.Thread(
                target=self._watchdog_loop,
                name="InputTriggerWatchdog",
                daemon=True,
            )
            self._watchdog_thread.start()

        log.info("[INPUT] Global input listeners started (Middle-click dictation & Ctrl+Win active).")

    def _start_key_listener(self) -> None:
        try:
            if self._key_listener is not None:
                try:
                    self._key_listener.stop()
                except Exception:
                    pass
                self._key_listener = None

            self._key_listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release,
            )
            self._key_listener.start()
        except Exception as e:
            log.error("[INPUT] Failed to start keyboard listener: %s", e)

    def stop(self) -> None:
        """Stop listening for global events."""
        self._stop_event.set()
        try:
            self._mouse_hook.stop()
        except Exception:
            pass
        if self._keyboard_hook is not None:
            try:
                self._keyboard_hook.stop()
            except Exception:
                pass
        if self._key_listener is not None:
            try:
                self._key_listener.stop()
            except Exception:
                pass
            self._key_listener = None
        log.info("[INPUT] Input listeners stopped.")

    def set_recording_state(self, recording: bool) -> None:
        """Inform listener of current recording state."""
        with self._lock:
            self._is_recording = recording
            if not recording:
                self._hotkey_triggered = False
                self._win_suppress_needed = False
                self._alt_space_triggered = False
                self._alt_tab_triggered = False
                self._custom_hotkey_triggered = False
                self._ctrl_hold_triggered = False
                self._ctrl_toggle_mode_active = False
                self._ctrl_chord_active = False
                self._ctrl_just_toggled_off = False
                if self._ctrl_check_timer:
                    self._ctrl_check_timer.cancel()
                    self._ctrl_check_timer = None
        self._mouse_hook.set_recording_state(recording)

    def reload_config(self, settings: dict[str, Any] | None = None) -> None:
        """Live reload trigger and hotkey settings from storage without restarting listener."""
        with self._lock:
            from voice_flow.storage import storage as _storage
            if settings is None:
                try:
                    settings = _storage.get_hotkey_settings() if hasattr(_storage, "get_hotkey_settings") else {}
                except Exception:
                    settings = {}
            ptt_map = {
                "ctrl+win": "ctrl_win",
                "win+ctrl": "ctrl_win",
                "single ctrl": "single_ctrl",
                "double ctrl": "double_ctrl",
                "alt+space": "alt_space",
                "alt+tab": "alt_tab",
                "middle mouse button": "middle_click",
                "middle_click": "middle_click",
            }
            raw_trigger = str(settings.get("hotkey_trigger") or "").lower().strip()
            ptt = str(settings.get("push_to_talk_shortcut") or "").strip()
            ptt_lower = ptt.lower()

            if "push_to_talk_shortcut" in settings and ("hotkey_trigger" not in settings or not settings["hotkey_trigger"]):
                if ptt_lower in ptt_map:
                    raw_trigger = ptt_map[ptt_lower]
                elif ptt:
                    raw_trigger = "custom"
                    self._custom_hotkey_str = ptt
            elif not raw_trigger or raw_trigger in ("none", "default"):
                if ptt_lower in ptt_map:
                    raw_trigger = ptt_map[ptt_lower]
                elif ptt:
                    raw_trigger = "custom"
                    self._custom_hotkey_str = ptt
                else:
                    saved_shortcut = str(_storage.get_setting("push_to_talk_shortcut", "ctrl+win") or "ctrl+win").strip()
                    storage_ptt = saved_shortcut.lower()
                    if storage_ptt in ptt_map:
                        raw_trigger = ptt_map[storage_ptt]
                    elif saved_shortcut:
                        raw_trigger = "custom"
                        self._custom_hotkey_str = saved_shortcut
                    else:
                        raw_trigger = "ctrl_win"

            self._hotkey_trigger = raw_trigger or "ctrl_win"
            custom_from_cfg = settings.get("custom_hotkey")
            if not custom_from_cfg:
                if self._hotkey_trigger == "custom" and getattr(self, "_custom_hotkey_str", None):
                    custom_from_cfg = self._custom_hotkey_str
                else:
                    custom_from_cfg = _storage.get_setting("custom_hotkey", "Alt+Space") or "Alt+Space"
            self._custom_hotkey_str = str(custom_from_cfg).strip()
            self._parsed_custom_keys = parse_hotkey_string(self._custom_hotkey_str)
            default_trig_type = "double_tap" if self._parsed_custom_keys.get("is_double") else "hold"
            self._custom_trigger_type = str(
                settings.get("custom_trigger_type")
                or _storage.get_setting("custom_trigger_type", default_trig_type)
                or default_trig_type
            ).lower().strip()
            self._trigger_mode = str(settings.get("dictation_trigger_mode") or _storage.get_setting("dictation_trigger_mode", "hybrid") or "hybrid").lower().strip()
            self._middle_click_enabled = bool(settings.get("middle_click_enabled", _storage.get_setting("middle_click_enabled", True)))
            if "ctrl_key_dictation_enabled" in settings and settings["ctrl_key_dictation_enabled"] is not None:
                self._ctrl_key_dictation_enabled = bool(settings["ctrl_key_dictation_enabled"])
            elif self._hotkey_trigger in ("single_ctrl", "double_ctrl"):
                self._ctrl_key_dictation_enabled = True
            else:
                self._ctrl_key_dictation_enabled = False
            if self._mouse_hook:
                try:
                    self._mouse_hook.refresh_trigger_mode(force=True)
                    self._mouse_hook.set_enabled(self._middle_click_enabled and self._trigger_mode != "disabled")
                except Exception:
                    pass
            log.info(
                "[INPUT] Hotkey config reloaded: trigger=%s, mode=%s, middle=%s, custom=%s",
                self._hotkey_trigger, self._trigger_mode, self._middle_click_enabled, self._custom_hotkey_str
            )

    def _watchdog_loop(self) -> None:
        """Continuously verify that keyboard listener is alive and restart if dropped."""
        while not self._stop_event.is_set():
            time.sleep(3.0)
            if self._stop_event.is_set():
                break

            # If native keyboard hook is present, check its health
            if self._keyboard_hook is not None:
                if not self._keyboard_hook.is_healthy() and not self._stop_event.is_set():
                    log.warning("[INPUT WATCHDOG] Native keyboard hook unhealthy. Attempting restart...")
                    try:
                        self._keyboard_hook.stop()
                        restarted = self._keyboard_hook.start()
                        if not restarted:
                            log.warning("[INPUT WATCHDOG] Native hook restart failed. Engaging pynput fallback...")
                            if self._key_listener is None or not self._key_listener.is_alive():
                                self._start_key_listener()
                    except Exception as exc:
                        log.error("[INPUT WATCHDOG] Native hook restart exception: %s", exc)
            else:
                key_dead = self._key_listener is None or not self._key_listener.is_alive()
                if key_dead and not self._stop_event.is_set():
                    log.warning("[INPUT WATCHDOG] Keyboard listener dropped. Restarting...")
                    self._start_key_listener()

    def _on_native_key(self, vk: int, is_down: bool, is_up: bool, extra: int) -> bool:
        """Native Win32 low-level keyboard hook callback (< 0.1ms latency).

        Returns True to suppress the key event from propagating to Windows Shell/apps.
        """
        try:
            if is_synthetic_input_active() or vk == VK_NONAME:
                return False

            now = time.time()
            suppress = False

            is_ctrl = vk in (VK_CONTROL, VK_LCONTROL, VK_RCONTROL)
            is_win = vk in (VK_LWIN, VK_RWIN)
            is_alt = vk in (VK_MENU, VK_LMENU, VK_RMENU)
            is_shift = vk in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT)
            is_space = vk == VK_SPACE
            is_tab = vk == VK_TAB
            is_esc = vk == VK_ESCAPE
            is_c = vk == 0x43

            with self._lock:
                active_trigger = getattr(self, "_hotkey_trigger", "ctrl_win").lower().strip()
                active_mode = getattr(self, "_trigger_mode", "hybrid").lower().strip()

                ctrl_down = _is_ctrl_down() or (is_ctrl and is_down)
                win_down = _is_win_down() or (is_win and is_down)
                alt_down = _is_alt_down() or (is_alt and is_down)
                shift_down = _is_shift_down() or (is_shift and is_down)

                if is_down:
                    # Escape cancels recording
                    if is_esc:
                        if (
                            self._is_recording
                            or self._hotkey_triggered
                            or self._alt_space_triggered
                            or self._alt_tab_triggered
                            or self._custom_hotkey_triggered
                            or self._ctrl_hold_triggered
                            or self._ctrl_toggle_mode_active
                        ):
                            self._is_recording = False
                            self._hotkey_triggered = False
                            self._win_suppress_needed = False
                            self._alt_space_triggered = False
                            self._alt_tab_triggered = False
                            self._custom_hotkey_triggered = False
                            self._ctrl_hold_triggered = False
                            self._ctrl_toggle_mode_active = False
                            self._ctrl_chord_active = False
                            self._mouse_hook.set_recording_state(False)
                            threading.Thread(target=self._safe_on_cancel, daemon=True).start()
                            return True

                    # 1. Ctrl+Win chord down
                    is_ctrl_win_active = active_trigger in ("ctrl_win", "") or (active_trigger not in ("single_ctrl", "double_ctrl", "alt_space", "alt_tab", "middle_click", "custom"))
                    if is_ctrl_win_active and (is_ctrl or is_win) and ctrl_down and win_down:
                        _suppress_win_start_menu()
                        self._win_suppress_needed = True
                        if not self._is_recording:
                            self._hotkey_triggered = True
                            self._hotkey_press_time = now
                            self._is_recording = True
                            self._mouse_hook.set_recording_state(True)
                            threading.Thread(target=self._safe_on_start, daemon=True).start()
                        elif not self._hotkey_triggered and active_mode in ("toggle_only", "hybrid"):
                            self._hotkey_triggered = True
                            self._is_recording = False
                            self._mouse_hook.set_recording_state(False)
                            threading.Thread(target=self._safe_on_finish, daemon=True).start()
                        return True

                    # 2. Alt+Space trigger
                    if active_trigger == "alt_space" and (is_space or is_alt) and alt_down and (is_space or _is_key_down(VK_SPACE)):
                        if not self._alt_space_triggered:
                            self._alt_space_triggered = True
                            self._hotkey_press_time = now
                            if not self._is_recording:
                                self._is_recording = True
                                self._mouse_hook.set_recording_state(True)
                                threading.Thread(target=self._safe_on_start, daemon=True).start()
                            elif active_mode in ("toggle_only", "hybrid"):
                                self._is_recording = False
                                self._mouse_hook.set_recording_state(False)
                                threading.Thread(target=self._safe_on_finish, daemon=True).start()
                        return True

                    # 3. Alt+Tab trigger
                    if active_trigger == "alt_tab" and (is_tab or is_alt) and alt_down and (is_tab or _is_key_down(VK_TAB)):
                        if not self._alt_tab_triggered:
                            self._alt_tab_triggered = True
                            self._hotkey_press_time = now
                            if not self._is_recording:
                                self._is_recording = True
                                self._mouse_hook.set_recording_state(True)
                                threading.Thread(target=self._safe_on_start, daemon=True).start()
                            elif active_mode in ("toggle_only", "hybrid"):
                                self._is_recording = False
                                self._mouse_hook.set_recording_state(False)
                                threading.Thread(target=self._safe_on_finish, daemon=True).start()
                        return True

                    # 4. Custom combination trigger
                    if active_trigger == "custom":
                        custom_info = getattr(self, "_parsed_custom_keys", None) or parse_hotkey_string(getattr(self, "_custom_hotkey_str", "Alt+Space"))
                        req_mods = custom_info.get("modifiers", set())
                        base = custom_info.get("base_key")
                        base_vk = _vk_for_key_name(base)

                        mods_match = True
                        if "ctrl" in req_mods and not ctrl_down: mods_match = False
                        if "alt" in req_mods and not alt_down: mods_match = False
                        if "shift" in req_mods and not shift_down: mods_match = False
                        if "win" in req_mods and not win_down: mods_match = False
                        if "ctrl" not in req_mods and ctrl_down: mods_match = False
                        if "alt" not in req_mods and alt_down: mods_match = False
                        if "shift" not in req_mods and shift_down: mods_match = False
                        if "win" not in req_mods and win_down: mods_match = False

                        base_match = True
                        if base:
                            base_match = (vk == base_vk) or _is_key_down(base_vk)

                        if mods_match and base_match and (req_mods or base):
                            is_custom_double = bool(custom_info.get("is_double") or getattr(self, "_custom_trigger_type", "hold") == "double_tap")
                            if is_custom_double:
                                if self._is_recording:
                                    self._is_recording = False
                                    self._custom_hotkey_triggered = False
                                    self._mouse_hook.set_recording_state(False)
                                    threading.Thread(target=self._safe_on_finish, daemon=True).start()
                                    return True
                                else:
                                    last_rel = getattr(self, "_last_custom_release_time", 0.0)
                                    if (now - last_rel) <= 0.35:
                                        self._custom_hotkey_triggered = True
                                        self._hotkey_press_time = now
                                        self._is_recording = True
                                        self._mouse_hook.set_recording_state(True)
                                        threading.Thread(target=self._safe_on_start, daemon=True).start()
                                        return True
                                    else:
                                        # First press of double tap - wait for second tap; no hold trigger
                                        self._custom_hotkey_triggered = True
                                        self._hotkey_press_time = now
                                        return True
                            else:
                                if not self._custom_hotkey_triggered:
                                    self._custom_hotkey_triggered = True
                                    self._hotkey_press_time = now
                                    if not self._is_recording:
                                        self._is_recording = True
                                        self._mouse_hook.set_recording_state(True)
                                        threading.Thread(target=self._safe_on_start, daemon=True).start()
                                    elif active_mode in ("toggle_only", "hybrid") or getattr(self, "_custom_trigger_type", "hold") == "toggle":
                                        self._is_recording = False
                                        self._mouse_hook.set_recording_state(False)
                                        threading.Thread(target=self._safe_on_finish, daemon=True).start()
                            return True

                    # Chord detection (Ctrl+C, etc.)
                    if not is_ctrl and ctrl_down:
                        self._ctrl_chord_active = True
                        if self._ctrl_check_timer:
                            self._ctrl_check_timer.cancel()
                            self._ctrl_check_timer = None
                        self._ctrl_hold_triggered = False
                        self._last_ctrl_release_time = 0.0

                    # Mark user copy on Ctrl+C
                    if is_c and ctrl_down and not alt_down:
                        try:
                            from voice_flow.injector import mark_user_copy
                            mark_user_copy()
                        except Exception:
                            pass

                    # Solo Control Key Handling
                    if is_ctrl and not win_down and not shift_down and not alt_down:
                        self._ctrl_chord_active = False
                        from voice_flow.storage import storage as _storage
                        ctrl_dictation_enabled = (
                            self._ctrl_key_dictation_enabled
                            or active_trigger in ("single_ctrl", "double_ctrl")
                            or bool(_storage.get_setting("ctrl_key_dictation_enabled", False))
                        )
                        if ctrl_dictation_enabled:
                            if self._is_recording:
                                self._ctrl_just_toggled_off = True
                                self._ctrl_toggle_mode_active = False
                                self._ctrl_hold_triggered = False
                                self._is_recording = False
                                if self._ctrl_check_timer:
                                    self._ctrl_check_timer.cancel()
                                    self._ctrl_check_timer = None
                                self._mouse_hook.set_recording_state(False)
                                threading.Thread(target=self._safe_on_finish, daemon=True).start()
                            else:
                                self._ctrl_just_toggled_off = False
                                self._ctrl_press_time = now
                                if (now - self._last_ctrl_release_time) <= 0.35 and active_trigger in ("double_ctrl", "single_ctrl"):
                                    self._ctrl_toggle_mode_active = True
                                    self._ctrl_hold_triggered = False
                                    self._is_recording = True
                                    self._mouse_hook.set_recording_state(True)
                                    threading.Thread(target=self._safe_on_start, daemon=True).start()
                                elif active_trigger != "double_ctrl":
                                    if self._ctrl_check_timer:
                                        self._ctrl_check_timer.cancel()
                                    def _on_native_ctrl_hold():
                                        with self._lock:
                                            if self._ctrl_check_timer is not None and not self._ctrl_chord_active:
                                                self._ctrl_check_timer = None
                                                if not self._is_recording:
                                                    self._ctrl_hold_triggered = True
                                                    self._ctrl_toggle_mode_active = False
                                                    self._is_recording = True
                                                    self._mouse_hook.set_recording_state(True)
                                                    threading.Thread(target=self._safe_on_start, daemon=True).start()
                                    self._ctrl_check_timer = threading.Timer(0.35, _on_native_ctrl_hold)
                                    self._ctrl_check_timer.daemon = True
                                    self._ctrl_check_timer.start()

                    # Alt+C for copy-last ONLY when Voice Flow's own window is focused
                    if is_c and alt_down and not ctrl_down:
                        if self._on_copy_last and not self._is_recording:
                            try:
                                fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
                                if fg_hwnd:
                                    pid = wintypes.DWORD()
                                    ctypes.windll.user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(pid))
                                    if pid.value == os.getpid():
                                        threading.Thread(target=self._on_copy_last, daemon=True).start()
                            except Exception:
                                pass

                elif is_up:
                    # 1. Win key up: check if Start menu suppression needed
                    if is_win:
                        if getattr(self, "_win_suppress_needed", False) or self._hotkey_triggered:
                            _suppress_win_start_menu()
                            self._win_suppress_needed = False
                            suppress = True

                    # 2. Ctrl+Win release handling:
                    if is_ctrl or is_win:
                        if self._hotkey_triggered:
                            _suppress_win_start_menu()
                            self._win_suppress_needed = True  # Arm suppression for second key
                            self._hotkey_triggered = False
                            if active_mode != "toggle_only":
                                if self._is_recording:
                                    self._is_recording = False
                                    self._mouse_hook.set_recording_state(False)
                                    # Instant finish and paste on release!
                                    threading.Thread(target=self._safe_on_finish, daemon=True).start()
                            if is_win:
                                suppress = True
                        elif getattr(self, "_win_suppress_needed", False):
                            if is_win:
                                _suppress_win_start_menu()
                                self._win_suppress_needed = False
                                suppress = True
                            else:
                                self._win_suppress_needed = False

                    # 3. Alt+Space release
                    if (is_alt or is_space) and self._alt_space_triggered:
                        self._alt_space_triggered = False
                        if is_space:
                            suppress = True  # Prevent space keyup from leaking into active app
                        elif is_alt:
                            _suppress_win_start_menu()  # Mask active window menu bar
                        press_dur = now - getattr(self, "_hotkey_press_time", 0.0)
                        if active_mode == "ptt_only" or press_dur >= 0.25:
                            if self._is_recording:
                                self._is_recording = False
                                self._mouse_hook.set_recording_state(False)
                                threading.Thread(target=self._safe_on_finish, daemon=True).start()

                    # 4. Alt+Tab release
                    if (is_alt or is_tab) and self._alt_tab_triggered:
                        self._alt_tab_triggered = False
                        if is_tab:
                            suppress = True  # Prevent tab keyup from changing input field focus
                        elif is_alt:
                            _suppress_win_start_menu()  # Mask active window menu bar
                        press_dur = now - getattr(self, "_hotkey_press_time", 0.0)
                        if active_mode == "ptt_only" or press_dur >= 0.25:
                            if self._is_recording:
                                self._is_recording = False
                                self._mouse_hook.set_recording_state(False)
                                threading.Thread(target=self._safe_on_finish, daemon=True).start()

                    # 5. Custom hotkey release
                    if self._custom_hotkey_triggered:
                        custom_info = getattr(self, "_parsed_custom_keys", None) or parse_hotkey_string(getattr(self, "_custom_hotkey_str", "Alt+Space"))
                        req_mods = custom_info.get("modifiers", set())
                        base = custom_info.get("base_key")
                        base_vk = _vk_for_key_name(base)
                        is_rel = False
                        if "ctrl" in req_mods and is_ctrl: is_rel = True
                        if "alt" in req_mods and is_alt:
                            is_rel = True
                            _suppress_win_start_menu()
                        if "shift" in req_mods and is_shift: is_rel = True
                        if "win" in req_mods and is_win:
                            is_rel = True
                            _suppress_win_start_menu()
                            suppress = True
                        if base and (vk == base_vk):
                            is_rel = True
                            suppress = True  # Prevent custom base keyup from typing into app

                        if is_rel:
                            self._custom_hotkey_triggered = False
                            self._last_custom_release_time = now
                            is_custom_double = bool(custom_info.get("is_double") or getattr(self, "_custom_trigger_type", "hold") == "double_tap")
                            if not is_custom_double:
                                press_dur = now - getattr(self, "_hotkey_press_time", 0.0)
                                custom_trig_type = getattr(self, "_custom_trigger_type", "hold")
                                if active_mode == "ptt_only" or custom_trig_type == "hold" or press_dur >= 0.25:
                                    if self._is_recording:
                                        self._is_recording = False
                                        self._mouse_hook.set_recording_state(False)
                                        threading.Thread(target=self._safe_on_finish, daemon=True).start()

                    # 6. Solo Ctrl release
                    if is_ctrl:
                        had_timer = self._ctrl_check_timer is not None
                        if self._ctrl_check_timer:
                            self._ctrl_check_timer.cancel()
                            self._ctrl_check_timer = None

                        if getattr(self, "_ctrl_just_toggled_off", False):
                            self._ctrl_just_toggled_off = False
                            self._ctrl_hold_triggered = False
                            self._ctrl_toggle_mode_active = False
                            self._last_ctrl_release_time = 0.0
                        elif self._ctrl_chord_active:
                            self._ctrl_chord_active = False
                            self._ctrl_hold_triggered = False
                            self._last_ctrl_release_time = 0.0
                        else:
                            from voice_flow.storage import storage as _storage
                            ctrl_dictation_enabled = (
                                self._ctrl_key_dictation_enabled
                                or active_trigger in ("single_ctrl", "double_ctrl")
                                or bool(_storage.get_setting("ctrl_key_dictation_enabled", False))
                            )
                            if ctrl_dictation_enabled:
                                self._last_ctrl_release_time = now
                                if self._ctrl_hold_triggered and self._is_recording:
                                    self._ctrl_hold_triggered = False
                                    self._ctrl_toggle_mode_active = False
                                    self._is_recording = False
                                    self._mouse_hook.set_recording_state(False)
                                    threading.Thread(target=self._safe_on_finish, daemon=True).start()
                                elif had_timer and not self._is_recording and active_trigger != "double_ctrl":
                                    self._ctrl_toggle_mode_active = True
                                    self._ctrl_hold_triggered = False
                                    self._is_recording = True
                                    self._mouse_hook.set_recording_state(True)
                                    threading.Thread(target=self._safe_on_start, daemon=True).start()

            return suppress
        except Exception as e:
            log.exception("[INPUT] Native key handler error: %s", e)
            return False

    # -- Internal Keyboard Callbacks --

    def _on_key_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        try:
            if key is None:
                return

            if is_synthetic_input_active():
                return

            with self._lock:
                self._pressed_keys.add(key)

                # Check physical hardware state of BOTH keys using Win32 API
                ctrl_down = _is_ctrl_down() or any(k in self._pressed_keys for k in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r))
                win_down = _is_win_down() or any(k in self._pressed_keys for k in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r))
                alt_down = _is_alt_down() or any(k in self._pressed_keys for k in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr))
                shift_down = _is_shift_down() or any(k in self._pressed_keys for k in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r))

                active_trigger = getattr(self, "_hotkey_trigger", "ctrl_win").lower().strip()
                active_mode = getattr(self, "_trigger_mode", "hybrid").lower().strip()
                now = time.time()

                # 1. BOTH Ctrl and Win must be held simultaneously to trigger dictation
                # Active when trigger is ctrl_win, or as safe fallback
                is_ctrl_win_active = active_trigger in ("ctrl_win", "") or (active_trigger not in ("single_ctrl", "double_ctrl", "alt_space", "alt_tab", "middle_click", "custom"))
                if is_ctrl_win_active and ctrl_down and win_down:
                    _suppress_win_start_menu()
                    self._win_suppress_needed = True
                    if not self._hotkey_triggered and not self._is_recording:
                        self._hotkey_triggered = True
                        self._hotkey_press_time = now
                        self._is_recording = True
                        self._mouse_hook.set_recording_state(True)
                        threading.Thread(target=self._safe_on_start, daemon=True).start()
                    elif not self._hotkey_triggered and active_mode in ("toggle_only", "hybrid"):
                        self._hotkey_triggered = True
                        self._is_recording = False
                        self._mouse_hook.set_recording_state(False)
                        threading.Thread(target=self._safe_on_finish, daemon=True).start()

                # 2. Alt+Space trigger
                space_down = key == keyboard.Key.space or _is_key_down(0x20)
                if active_trigger == "alt_space" and alt_down and space_down:
                    if not self._alt_space_triggered:
                        self._alt_space_triggered = True
                        self._hotkey_press_time = now
                        if not self._is_recording:
                            self._is_recording = True
                            self._mouse_hook.set_recording_state(True)
                            threading.Thread(target=self._safe_on_start, daemon=True).start()
                        elif active_mode in ("toggle_only", "hybrid"):
                            self._is_recording = False
                            self._mouse_hook.set_recording_state(False)
                            threading.Thread(target=self._safe_on_finish, daemon=True).start()

                # 3. Alt+Tab trigger
                tab_down = key == keyboard.Key.tab or _is_key_down(0x09)
                if active_trigger == "alt_tab" and alt_down and tab_down:
                    if not self._alt_tab_triggered:
                        self._alt_tab_triggered = True
                        self._hotkey_press_time = now
                        if not self._is_recording:
                            self._is_recording = True
                            self._mouse_hook.set_recording_state(True)
                            threading.Thread(target=self._safe_on_start, daemon=True).start()
                        elif active_mode in ("toggle_only", "hybrid"):
                            self._is_recording = False
                            self._mouse_hook.set_recording_state(False)
                            threading.Thread(target=self._safe_on_finish, daemon=True).start()

                # 4. Custom combination trigger
                if active_trigger == "custom":
                    custom_info = getattr(self, "_parsed_custom_keys", None) or parse_hotkey_string(getattr(self, "_custom_hotkey_str", "Alt+Space"))
                    req_mods = custom_info.get("modifiers", set())
                    base = custom_info.get("base_key")

                    mods_match = True
                    if "ctrl" in req_mods and not ctrl_down: mods_match = False
                    if "alt" in req_mods and not alt_down: mods_match = False
                    if "shift" in req_mods and not shift_down: mods_match = False
                    if "win" in req_mods and not win_down: mods_match = False
                    if "ctrl" not in req_mods and ctrl_down: mods_match = False
                    if "alt" not in req_mods and alt_down: mods_match = False
                    if "shift" not in req_mods and shift_down: mods_match = False
                    if "win" not in req_mods and win_down: mods_match = False

                    base_match = True
                    if base:
                        base_vk = _vk_for_key_name(base)
                        base_match = _key_matches_name(key, base) or _is_key_down(base_vk) or any(_key_matches_name(k, base) for k in self._pressed_keys)

                    if mods_match and base_match and (req_mods or base):
                        is_custom_double = bool(custom_info.get("is_double") or getattr(self, "_custom_trigger_type", "hold") == "double_tap")
                        if is_custom_double:
                            if self._is_recording:
                                self._is_recording = False
                                self._custom_hotkey_triggered = False
                                self._mouse_hook.set_recording_state(False)
                                threading.Thread(target=self._safe_on_finish, daemon=True).start()
                            else:
                                last_rel = getattr(self, "_last_custom_release_time", 0.0)
                                if (now - last_rel) <= 0.35:
                                    self._custom_hotkey_triggered = True
                                    self._hotkey_press_time = now
                                    self._is_recording = True
                                    self._mouse_hook.set_recording_state(True)
                                    threading.Thread(target=self._safe_on_start, daemon=True).start()
                                else:
                                    self._custom_hotkey_triggered = True
                                    self._hotkey_press_time = now
                        else:
                            if not self._custom_hotkey_triggered:
                                self._custom_hotkey_triggered = True
                                self._hotkey_press_time = now
                                if not self._is_recording:
                                    self._is_recording = True
                                    self._mouse_hook.set_recording_state(True)
                                    threading.Thread(target=self._safe_on_start, daemon=True).start()
                                elif active_mode in ("toggle_only", "hybrid") or getattr(self, "_custom_trigger_type", "hold") == "toggle":
                                    self._is_recording = False
                                    self._mouse_hook.set_recording_state(False)
                                    threading.Thread(target=self._safe_on_finish, daemon=True).start()

                is_ctrl_key = key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)

                # If Ctrl is physically held down and the user pressed ANY non-Ctrl key (e.g. C, V, X, Z, A, S, Tab, Arrow):
                # this is a chord combination shortcut (Ctrl+C, Ctrl+V, etc.).
                # IMMEDIATELY cancel any solo-Ctrl timer and mark chord active so it passes through 100%!
                _vk = getattr(key, "vk", None)
                vk_c = _vk == 0x43 or getattr(key, "char", "") in ("c", "C", "\x03")

                if not is_ctrl_key and ctrl_down:
                    self._ctrl_chord_active = True
                    if self._ctrl_check_timer:
                        self._ctrl_check_timer.cancel()
                        self._ctrl_check_timer = None
                    self._ctrl_hold_triggered = False
                    self._last_ctrl_release_time = 0.0

                # Track physical Ctrl+C copy: notify injector immediately so background
                # selection inspector never overwrites the user's manual clipboard content!
                if vk_c and ctrl_down and not alt_down:
                    try:
                        from voice_flow.injector import mark_user_copy
                        mark_user_copy()
                    except Exception:
                        pass

                # Optional Solo Control Key Handling:
                # Enabled when 'ctrl_key_dictation_enabled' in settings or active_trigger is single_ctrl/double_ctrl!
                # Crucially check 'not alt_down' so AltGr (Ctrl+Alt on European/international keyboards) never triggers.
                if is_ctrl_key and not win_down and not shift_down and not alt_down:
                    self._ctrl_chord_active = False
                    from voice_flow.storage import storage as _storage
                    ctrl_dictation_enabled = (
                        self._ctrl_key_dictation_enabled
                        or active_trigger in ("single_ctrl", "double_ctrl")
                        or bool(_storage.get_setting("ctrl_key_dictation_enabled", False))
                    )

                    if ctrl_dictation_enabled:
                        if self._is_recording:
                            # Subsequent tap finishes continuous dictation cleanly!
                            self._ctrl_just_toggled_off = True
                            self._ctrl_toggle_mode_active = False
                            self._ctrl_hold_triggered = False
                            self._is_recording = False
                            if self._ctrl_check_timer:
                                self._ctrl_check_timer.cancel()
                                self._ctrl_check_timer = None
                            self._mouse_hook.set_recording_state(False)
                            threading.Thread(target=self._safe_on_finish, daemon=True).start()
                        else:
                            self._ctrl_just_toggled_off = False
                            self._ctrl_press_time = now
                            # Check if this press came within 0.35s of previous release -> Double Tap!
                            if (now - self._last_ctrl_release_time) <= 0.35 and active_trigger in ("double_ctrl", "single_ctrl"):
                                # Double Tap detected: start toggle mode
                                self._ctrl_toggle_mode_active = True
                                self._ctrl_hold_triggered = False
                                self._is_recording = True
                                self._mouse_hook.set_recording_state(True)
                                threading.Thread(target=self._safe_on_start, daemon=True).start()
                            elif active_trigger != "double_ctrl":
                                if self._ctrl_check_timer:
                                    self._ctrl_check_timer.cancel()
                                def _on_key_ctrl_hold():
                                    with self._lock:
                                        if self._ctrl_check_timer is not None and not self._ctrl_chord_active:
                                            self._ctrl_check_timer = None
                                            if not self._is_recording:
                                                self._ctrl_hold_triggered = True
                                                self._ctrl_toggle_mode_active = False
                                                self._is_recording = True
                                                self._mouse_hook.set_recording_state(True)
                                                threading.Thread(target=self._safe_on_start, daemon=True).start()
                                self._ctrl_check_timer = threading.Timer(0.35, _on_key_ctrl_hold)
                                self._ctrl_check_timer.daemon = True
                                self._ctrl_check_timer.start()

                # Alt+C for copy-last ONLY when Voice Flow's own window is focused
                if vk_c and alt_down and not ctrl_down:
                    if self._on_copy_last and not self._is_recording:
                        try:
                            fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
                            if fg_hwnd:
                                pid = wintypes.DWORD()
                                ctypes.windll.user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(pid))
                                if pid.value == os.getpid():
                                    threading.Thread(target=self._on_copy_last, daemon=True).start()
                        except Exception:
                            pass

                # Escape key cancels recording
                if key == keyboard.Key.esc:
                    if (
                        self._is_recording
                        or self._hotkey_triggered
                        or self._alt_space_triggered
                        or self._alt_tab_triggered
                        or self._custom_hotkey_triggered
                        or self._ctrl_hold_triggered
                        or self._ctrl_toggle_mode_active
                    ):
                        self._is_recording = False
                        self._hotkey_triggered = False
                        self._alt_space_triggered = False
                        self._alt_tab_triggered = False
                        self._custom_hotkey_triggered = False
                        self._ctrl_hold_triggered = False
                        self._ctrl_toggle_mode_active = False
                        self._ctrl_chord_active = False
                        self._ctrl_just_toggled_off = False
                        self._mouse_hook.set_recording_state(False)
                        threading.Thread(target=self._safe_on_cancel, daemon=True).start()
        except Exception as e:
            log.exception("[INPUT] Key press handler error: %s", e)

    def _on_key_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        try:
            if key is None:
                return

            if is_synthetic_input_active():
                return

            with self._lock:
                self._pressed_keys.discard(key)
                active_trigger = getattr(self, "_hotkey_trigger", "ctrl_win").lower().strip()
                active_mode = getattr(self, "_trigger_mode", "hybrid").lower().strip()
                now = time.time()

                # Releasing Ctrl or Win key when Push-to-Talk shortcut was active
                if key in (
                    keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r,
                    keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
                ):
                    if self._hotkey_triggered:
                        _suppress_win_start_menu()
                        self._win_suppress_needed = True
                        self._hotkey_triggered = False
                        if active_mode != "toggle_only":
                            if self._is_recording:
                                self._is_recording = False
                                self._mouse_hook.set_recording_state(False)
                                # Finish recording, transcribe, and paste text into target app
                                threading.Thread(target=self._safe_on_finish, daemon=True).start()
                    elif getattr(self, "_win_suppress_needed", False):
                        if key in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r):
                            _suppress_win_start_menu()
                            self._win_suppress_needed = False
                        else:
                            self._win_suppress_needed = False

                # Alt+Space release handling
                if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr, keyboard.Key.space):
                    if self._alt_space_triggered:
                        self._alt_space_triggered = False
                        press_dur = now - getattr(self, "_hotkey_press_time", 0.0)
                        if active_mode == "ptt_only" or press_dur >= 0.25:
                            if self._is_recording:
                                self._is_recording = False
                                self._mouse_hook.set_recording_state(False)
                                threading.Thread(target=self._safe_on_finish, daemon=True).start()

                # Alt+Tab release handling
                if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr, keyboard.Key.tab):
                    if self._alt_tab_triggered:
                        self._alt_tab_triggered = False
                        press_dur = now - getattr(self, "_hotkey_press_time", 0.0)
                        if active_mode == "ptt_only" or press_dur >= 0.25:
                            if self._is_recording:
                                self._is_recording = False
                                self._mouse_hook.set_recording_state(False)
                                threading.Thread(target=self._safe_on_finish, daemon=True).start()

                # Custom hotkey release handling
                if self._custom_hotkey_triggered:
                    custom_info = getattr(self, "_parsed_custom_keys", None) or parse_hotkey_string(getattr(self, "_custom_hotkey_str", "Alt+Space"))
                    req_mods = custom_info.get("modifiers", set())
                    base = custom_info.get("base_key")
                    is_rel = False
                    if "ctrl" in req_mods and key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r): is_rel = True
                    if "alt" in req_mods and key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr): is_rel = True
                    if "shift" in req_mods and key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r): is_rel = True
                    if "win" in req_mods and key in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r): is_rel = True
                    if base and _key_matches_name(key, base): is_rel = True

                    if is_rel:
                        self._custom_hotkey_triggered = False
                        self._last_custom_release_time = now
                        is_custom_double = bool(custom_info.get("is_double") or getattr(self, "_custom_trigger_type", "hold") == "double_tap")
                        if not is_custom_double:
                            press_dur = now - getattr(self, "_hotkey_press_time", 0.0)
                            custom_trig_type = getattr(self, "_custom_trigger_type", "hold")
                            if active_mode == "ptt_only" or custom_trig_type == "hold" or press_dur >= 0.25:
                                if self._is_recording:
                                    self._is_recording = False
                                    self._mouse_hook.set_recording_state(False)
                                    threading.Thread(target=self._safe_on_finish, daemon=True).start()

                # Handle solo Ctrl release
                is_ctrl_key = key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)
                if is_ctrl_key:
                    had_timer = self._ctrl_check_timer is not None
                    if self._ctrl_check_timer:
                        self._ctrl_check_timer.cancel()
                        self._ctrl_check_timer = None

                    if getattr(self, "_ctrl_just_toggled_off", False):
                        self._ctrl_just_toggled_off = False
                        self._ctrl_hold_triggered = False
                        self._ctrl_toggle_mode_active = False
                        self._last_ctrl_release_time = 0.0
                    elif self._ctrl_chord_active:
                        self._ctrl_chord_active = False
                        self._ctrl_hold_triggered = False
                        self._last_ctrl_release_time = 0.0
                    else:
                        from voice_flow.storage import storage as _storage
                        ctrl_dictation_enabled = (
                            self._ctrl_key_dictation_enabled
                            or active_trigger in ("single_ctrl", "double_ctrl")
                            or bool(_storage.get_setting("ctrl_key_dictation_enabled", False))
                        )
                        if ctrl_dictation_enabled:
                            self._last_ctrl_release_time = now
                            if self._ctrl_hold_triggered and self._is_recording:
                                self._ctrl_hold_triggered = False
                                self._ctrl_toggle_mode_active = False
                                self._is_recording = False
                                self._mouse_hook.set_recording_state(False)
                                threading.Thread(target=self._safe_on_finish, daemon=True).start()
                            elif had_timer and not self._is_recording and active_trigger != "double_ctrl":
                                self._ctrl_toggle_mode_active = True
                                self._ctrl_hold_triggered = False
                                self._is_recording = True
                                self._mouse_hook.set_recording_state(True)
                                threading.Thread(target=self._safe_on_start, daemon=True).start()
        except Exception as e:
            log.exception("[INPUT] Key release handler error: %s", e)

    def _safe_on_start(self) -> None:
        action_lock = getattr(self, "_action_lock", None)
        if action_lock is not None:
            action_lock.acquire()
        try:
            started = self._on_start()
            if started is False:
                with self._lock:
                    self._is_recording = False
                    self._hotkey_triggered = False
                if getattr(self, "_mouse_hook", None):
                    self._mouse_hook.set_recording_state(False)
        except Exception as e:
            log.error("[INPUT] Error in on_start: %s", e)
            with self._lock:
                self._is_recording = False
                self._hotkey_triggered = False
            try:
                if getattr(self, "_mouse_hook", None):
                    self._mouse_hook.set_recording_state(False)
            except Exception:
                pass
        finally:
            if action_lock is not None:
                action_lock.release()

    def _safe_on_finish(self) -> None:
        action_lock = getattr(self, "_action_lock", None)
        if action_lock is not None:
            action_lock.acquire()
        try:
            finished = self._on_finish()
            if finished is False:
                if getattr(self, "_mouse_hook", None):
                    self._mouse_hook.set_recording_state(False)
        except Exception as e:
            log.error("[INPUT] Error in on_finish: %s", e)
        finally:
            try:
                if getattr(self, "_mouse_hook", None):
                    self._mouse_hook.set_recording_state(False)
            except Exception:
                pass
            if action_lock is not None:
                action_lock.release()

    def _safe_on_cancel(self) -> None:
        action_lock = getattr(self, "_action_lock", None)
        if action_lock is not None:
            action_lock.acquire()
        try:
            cancelled = self._on_cancel()
            if cancelled is False:
                if getattr(self, "_mouse_hook", None):
                    self._mouse_hook.set_recording_state(False)
        except Exception as e:
            log.error("[INPUT] Error in on_cancel: %s", e)
        finally:
            try:
                if getattr(self, "_mouse_hook", None):
                    self._mouse_hook.set_recording_state(False)
            except Exception:
                pass
            if action_lock is not None:
                action_lock.release()


# Alias for backward compatibility and intuitive naming
HotkeyManager = InputTriggerListener

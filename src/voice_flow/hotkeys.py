"""Global input listeners for Voice Flow using pynput with Win32 message filtering.

- Triggers dictation on middle mouse button hold/release (scroll button click).
- Suppresses native middle-click drag autoscroll icon while keeping normal wheel scrolling working 100%.
- Triggers dictation on Ctrl+Win / Win+Ctrl shortcut while suppressing Start menu popup.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from typing import Callable

from pynput import keyboard, mouse

log = logging.getLogger(__name__)

# Win32 Mouse Message IDs
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MBUTTONDBLCLK = 0x0209
WM_NCMBUTTONDOWN = 0x00A7
WM_NCMBUTTONUP = 0x00A8
WM_NCMBUTTONDBLCLK = 0x00A9

# Win32 Virtual Key 0xE8 (unassigned dummy key) to suppress Start Menu on Win key release
VK_NONAME = 0xE8


def _suppress_win_start_menu() -> None:
    """Send a dummy key event to prevent Windows from opening the Start menu on Win key release."""
    try:
        ctypes.windll.user32.keybd_event(VK_NONAME, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_NONAME, 0, 2, 0)  # KEYEVENTF_KEYUP = 2
    except Exception:
        pass


class InputTriggerListener:
    """Listens for global mouse (middle button) and keyboard (Win+Ctrl / Ctrl+Win) events."""

    def __init__(
        self,
        on_start: Callable[[], None],
        on_finish: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        self._on_start = on_start
        self._on_finish = on_finish
        self._on_cancel = on_cancel

        self._mouse_listener: mouse.Listener | None = None
        self._key_listener: keyboard.Listener | None = None
        self._pressed_keys: set[keyboard.Key | keyboard.KeyCode] = set()
        self._lock = threading.Lock()
        self._is_recording = False
        self._hotkey_triggered = False
        self._mbutton_press_time: float = 0.0

    def start(self) -> None:
        """Start listening for global mouse and keyboard events."""
        log.info("[INPUT] Initializing global mouse filter & keyboard shortcuts...")
        self._mouse_listener = mouse.Listener(
            on_click=self._on_mouse_click,
            win32_event_filter=self._win32_mouse_filter,
        )
        self._mouse_listener.start()

        self._key_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._key_listener.start()
        log.info("[INPUT] Global input listeners started (Middle-click dictation & Ctrl+Win active).")

    def stop(self) -> None:
        """Stop listening for global events."""
        if self._mouse_listener is not None:
            self._mouse_listener.stop()
            self._mouse_listener = None
        if self._key_listener is not None:
            self._key_listener.stop()
            self._key_listener = None
        log.info("[INPUT] Input listeners stopped.")

    def set_recording_state(self, recording: bool) -> None:
        """Inform listener of current recording state."""
        with self._lock:
            self._is_recording = recording

    # -- Win32 Mouse Filter & Callbacks --

    def _win32_mouse_filter(self, msg: int, data: object) -> bool:
        """Selectively intercepts middle button clicks — supports both Push-to-Talk Hold and Toggle Tap."""
        if msg in (WM_MBUTTONDOWN, WM_NCMBUTTONDOWN, WM_MBUTTONDBLCLK, WM_NCMBUTTONDBLCLK):
            with self._lock:
                self._mbutton_press_time = time.time()
                if not self._is_recording:
                    self._is_recording = True
                    # MUST dispatch to thread — Win32 hooks timeout after ~300ms
                    threading.Thread(target=self._on_start, daemon=True).start()
                else:
                    self._is_recording = False
                    threading.Thread(target=self._on_finish, daemon=True).start()
            if self._mouse_listener:
                self._mouse_listener.suppress_event()
            return False
        elif msg in (WM_MBUTTONUP, WM_NCMBUTTONUP):
            with self._lock:
                press_dur = time.time() - self._mbutton_press_time
                # If held > 0.35s (Push-to-Talk hold), finish on release
                # If quick tap (<0.35s), keep recording in toggle mode
                if self._is_recording and press_dur > 0.35:
                    self._is_recording = False
                    threading.Thread(target=self._on_finish, daemon=True).start()
            if self._mouse_listener:
                self._mouse_listener.suppress_event()
            return False
        return True

    def _on_mouse_click(
        self, x: int, y: int, button: mouse.Button, pressed: bool
    ) -> None:
        """Dummy callback for pynput mouse listener."""
        pass

    # -- Internal Keyboard Callbacks --

    def _on_key_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key is None:
            return
        self._pressed_keys.add(key)

        # Check for Win + Ctrl / Ctrl + Win combo
        win_pressed = any(
            k in self._pressed_keys
            for k in (
                keyboard.Key.cmd,
                keyboard.Key.cmd_l,
                keyboard.Key.cmd_r,
            )
        )
        ctrl_pressed = any(
            k in self._pressed_keys
            for k in (
                keyboard.Key.ctrl,
                keyboard.Key.ctrl_l,
                keyboard.Key.ctrl_r,
            )
        )

        if win_pressed and ctrl_pressed:
            _suppress_win_start_menu()

            with self._lock:
                if not self._hotkey_triggered:
                    self._hotkey_triggered = True
                    if not self._is_recording:
                        self._is_recording = True
                        threading.Thread(target=self._on_start, daemon=True).start()

        # Escape key cancels recording
        if key == keyboard.Key.esc:
            with self._lock:
                if self._is_recording:
                    self._is_recording = False
                    threading.Thread(target=self._on_cancel, daemon=True).start()

    def _on_key_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key is None:
            return
        self._pressed_keys.discard(key)

        # Release hotkey triggers finish when Win or Ctrl is released during recording
        if key in (
            keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r,
            keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
        ):
            _suppress_win_start_menu()

            with self._lock:
                if self._hotkey_triggered:
                    self._hotkey_triggered = False
                    if self._is_recording:
                        self._is_recording = False
                        threading.Thread(target=self._on_finish, daemon=True).start()

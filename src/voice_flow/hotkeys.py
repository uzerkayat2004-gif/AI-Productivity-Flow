"""Global hotkey and mouse event listeners for Voice Flow with event suppression.

Suppresses middle-click drag autoscroll while allowing normal mouse wheel scrolling
and preventing Windows Start Menu popups.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from typing import Callable

from pynput import keyboard, mouse

log = logging.getLogger(__name__)

# Win32 Mouse Message IDs for Middle Button
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
    """Listens for global mouse (middle button) and keyboard (Win+Ctrl / Ctrl+Win) events.

    Suppresses native middle-click drag autoscroll while allowing normal mouse wheel scrolling.
    """

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

        self._is_recording = False
        self._pressed_keys: set[keyboard.Key | keyboard.KeyCode] = set()
        self._middle_pressed = False
        self._hotkey_triggered = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start listening for inputs with suppress=True to block middle-click drag autoscroll."""
        self._mouse_listener = mouse.Listener(
            on_click=self._on_mouse_click,
            win32_event_filter=self._win32_mouse_filter,
            suppress=True,  # REQUIRED on Windows for win32_event_filter return False to block OS messages
        )
        self._key_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
            win32_event_filter=self._win32_key_filter,
        )

        self._mouse_listener.start()
        self._key_listener.start()
        log.info("Global input listeners started (Middle-click drag autoscroll suppressed).")

    def stop(self) -> None:
        """Stop input listeners."""
        if self._mouse_listener is not None:
            self._mouse_listener.stop()
            self._mouse_listener = None
        if self._key_listener is not None:
            self._key_listener.stop()
            self._key_listener = None
        log.info("Input listeners stopped.")

    def set_recording_state(self, recording: bool) -> None:
        """Inform listener of the current recording state."""
        with self._lock:
            self._is_recording = recording

    # -- Win32 Mouse Event Filter --

    def _win32_mouse_filter(self, msg: int, data: object) -> bool:
        """Selectively suppresses middle button messages to block drag autoscroll icon."""
        if msg in (WM_MBUTTONDOWN, WM_NCMBUTTONDOWN, WM_MBUTTONDBLCLK, WM_NCMBUTTONDBLCLK):
            with self._lock:
                if not self._is_recording:
                    self._middle_pressed = True
                    self._on_start()
            return False  # Returning False with suppress=True BLOCKS middle-click down from reaching Windows

        elif msg in (WM_MBUTTONUP, WM_NCMBUTTONUP):
            with self._lock:
                if self._middle_pressed and self._is_recording:
                    self._middle_pressed = False
                    self._on_finish()
            return False  # Returning False with suppress=True BLOCKS middle-click up from reaching Windows

        # Return True for ALL other events (normal mouse wheel rotation 0x020A, left/right click, motion)
        return True

    def _on_mouse_click(
        self, x: int, y: int, button: mouse.Button, pressed: bool
    ) -> None:
        """Dummy callback for pynput mouse listener."""
        pass

    # -- Win32 Keyboard Event Filter --

    def _win32_key_filter(self, msg: int, data: object) -> bool:
        """Low-level keyboard filter."""
        return True

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
            # Suppress Windows Start menu by sending dummy key event
            _suppress_win_start_menu()

            with self._lock:
                if not self._hotkey_triggered:
                    self._hotkey_triggered = True
                    if not self._is_recording:
                        self._on_start()
                    else:
                        self._on_finish()

        # Escape key cancels recording
        if key == keyboard.Key.esc:
            with self._lock:
                if self._is_recording:
                    self._on_cancel()

    def _on_key_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key is None:
            return
        self._pressed_keys.discard(key)

        # Reset hotkey trigger flag when Win or Ctrl is released
        if key in (
            keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r,
            keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
        ):
            if any(
                k in self._pressed_keys
                for k in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r)
            ):
                _suppress_win_start_menu()

            with self._lock:
                self._hotkey_triggered = False

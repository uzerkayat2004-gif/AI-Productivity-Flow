"""Global hotkey and mouse event listeners for Voice Flow.

Uses native Win32 mouse hook for middle-click suppression with zero cursor lag.
Prevents Windows Start Menu from opening when Win+Ctrl or Ctrl+Win is pressed.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from typing import Callable

from pynput import keyboard

from voice_flow.mouse_hook import NativeMiddleClickHook

log = logging.getLogger(__name__)

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

        self._mouse_hook: NativeMiddleClickHook | None = None
        self._key_listener: keyboard.Listener | None = None

        self._is_recording = False
        self._pressed_keys: set[keyboard.Key | keyboard.KeyCode] = set()
        self._hotkey_triggered = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start native mouse hook and keyboard listener."""
        self._mouse_hook = NativeMiddleClickHook(
            on_press=self._handle_mouse_press,
            on_release=self._handle_mouse_release,
        )
        self._key_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )

        self._mouse_hook.start()
        self._key_listener.start()
        log.info("Global input listeners started (Native Win32 mouse hook active).")

    def stop(self) -> None:
        """Stop input listeners."""
        if self._mouse_hook is not None:
            self._mouse_hook.stop()
            self._mouse_hook = None
        if self._key_listener is not None:
            self._key_listener.stop()
            self._key_listener = None
        log.info("Input listeners stopped.")

    def set_recording_state(self, recording: bool) -> None:
        """Inform listener of the current recording state."""
        with self._lock:
            self._is_recording = recording

    # -- Mouse Hook Callbacks --

    def _handle_mouse_press(self) -> None:
        with self._lock:
            if not self._is_recording:
                self._on_start()

    def _handle_mouse_release(self) -> None:
        with self._lock:
            if self._is_recording:
                self._on_finish()

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

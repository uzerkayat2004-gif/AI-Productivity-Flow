"""Global hotkey and mouse event listeners for Voice Flow."""

from __future__ import annotations

import logging
import threading
from typing import Callable

from pynput import keyboard, mouse

log = logging.getLogger(__name__)


class InputTriggerListener:
    """Listens for global mouse (middle button) and keyboard (Win+Ctrl) events.

    Triggers callbacks when recording should start, finish, or cancel.
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
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start listening for inputs in background threads."""
        self._mouse_listener = mouse.Listener(
            on_click=self._on_mouse_click,
        )
        self._key_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )

        self._mouse_listener.start()
        self._key_listener.start()
        log.info("Global mouse & keyboard listeners started.")

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

    # -- Internal Mouse Callback --

    def _on_mouse_click(
        self, x: int, y: int, button: mouse.Button, pressed: bool
    ) -> None:
        if button != mouse.Button.middle:
            return

        with self._lock:
            if pressed:
                if not self._is_recording:
                    self._middle_pressed = True
                    self._on_start()
            else:
                if self._middle_pressed and self._is_recording:
                    self._middle_pressed = False
                    self._on_finish()

    # -- Internal Keyboard Callbacks --

    def _on_key_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key is None:
            return
        self._pressed_keys.add(key)

        # Check for Win + Ctrl combo
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
            with self._lock:
                if not self._is_recording:
                    self._on_start()
                else:
                    self._on_finish()
            # Clear keys to prevent immediate re-triggering
            self._pressed_keys.clear()

        # Escape key cancels recording
        if key == keyboard.Key.esc:
            with self._lock:
                if self._is_recording:
                    self._on_cancel()

    def _on_key_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key is None:
            return
        self._pressed_keys.discard(key)

"""Global input listeners for Voice Flow using native Win32 hooks and pynput fallback.

- Triggers dictation on middle mouse button hold/release (scroll button click).
- Suppresses native middle-click drag autoscroll icon while keeping normal wheel scrolling working 100%.
- Triggers dictation on Ctrl+Win / Win+Ctrl shortcut while suppressing Start menu popup.
- Auto-rehooks and recovers if Windows drops low-level hooks or after workstation lock/sleep.
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from typing import Callable

from pynput import keyboard

from voice_flow.mouse_hook import Win32MouseHook

log = logging.getLogger(__name__)

# Win32 Virtual Key Codes for Ctrl and Win keys
VK_CONTROL = 0x11
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_SHIFT = 0x10

# Win32 Virtual Key 0xE8 (unassigned dummy key) to suppress Start Menu on Win key release
VK_NONAME = 0xE8


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


def _suppress_win_start_menu() -> None:
    """Send a dummy key event to prevent Windows from opening the Start menu on Win key release."""
    try:
        ctypes.windll.user32.keybd_event(VK_NONAME, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_NONAME, 0, 2, 0)  # KEYEVENTF_KEYUP = 2
    except Exception:
        pass


class InputTriggerListener:
    """Listens for global mouse (middle button) and keyboard (Win+Ctrl / Ctrl+Win) events with self-healing."""

    def __init__(
        self,
        on_start: Callable[[], None],
        on_finish: Callable[[], None],
        on_cancel: Callable[[], None],
        on_paste_last: Callable[[], None] | None = None,
        on_copy_last: Callable[[], None] | None = None,
        on_audio_flow: Callable[[], None] | None = None,
        on_mouse_release: Callable[..., None] | None = None,
    ) -> None:
        self._on_start = on_start
        self._on_finish = on_finish
        self._on_cancel = on_cancel
        self._on_paste_last = on_paste_last
        self._on_copy_last = on_copy_last
        self._on_audio_flow = on_audio_flow
        self._on_mouse_release = on_mouse_release

        # Primary Win32 mouse hook
        self._mouse_hook = Win32MouseHook(
            on_start=self._on_start,
            on_finish=self._on_finish,
            on_cancel=self._on_cancel,
            on_mouse_release=self._on_mouse_release,
        )

        self._key_listener: keyboard.Listener | None = None
        self._pressed_keys: set[keyboard.Key | keyboard.KeyCode] = set()
        self._lock = threading.Lock()
        self._is_recording = False
        self._hotkey_triggered = False
        self._stop_event = threading.Event()
        self._watchdog_thread: threading.Thread | None = None

    def start(self) -> None:
        """Start listening for global mouse and keyboard events."""
        log.info("[INPUT] Initializing global mouse hook & keyboard shortcuts...")
        self._stop_event.clear()

        # Start Win32 mouse hook
        try:
            self._mouse_hook.start()
        except Exception as e:
            log.error("[INPUT] Failed to start Win32 mouse hook: %s", e)

        # Start keyboard listener
        self._start_key_listener()

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
        self._mouse_hook.set_recording_state(recording)

    def _watchdog_loop(self) -> None:
        """Continuously verify that keyboard listener is alive and restart if dropped."""
        while not self._stop_event.is_set():
            time.sleep(3.0)
            if self._stop_event.is_set():
                break

            # Check keyboard listener health
            key_dead = self._key_listener is None or not self._key_listener.is_alive()
            if key_dead and not self._stop_event.is_set():
                log.warning("[INPUT WATCHDOG] Keyboard listener dropped. Restarting...")
                self._start_key_listener()

    # -- Internal Keyboard Callbacks --

    def _on_key_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        try:
            if key is None:
                return

            with self._lock:
                # Check physical hardware state of BOTH keys using Win32 API
                ctrl_down = _is_ctrl_down()
                win_down = _is_win_down()

                # BOTH Ctrl and Win must be held simultaneously to trigger dictation
                if ctrl_down and win_down:
                    _suppress_win_start_menu()
                    if not self._hotkey_triggered and not self._is_recording:
                        self._hotkey_triggered = True
                        self._is_recording = True
                        self._mouse_hook.set_recording_state(True)
                        threading.Thread(target=self._safe_on_start, daemon=True).start()

                # Alt+C or Ctrl+C / Ctrl+Shift+C — copy-last ONLY when Voice Flow's own window is focused
                vk_menu = (key == keyboard.Key.alt or key == keyboard.Key.alt_l or key == keyboard.Key.alt_r)
                vk_c = key == keyboard.KeyCode.from_char("c")
                shift_down = _is_shift_down()
                if (vk_menu and vk_c) or (ctrl_down and not shift_down and vk_c) or (ctrl_down and shift_down and vk_c):
                    if self._on_copy_last and not self._is_recording:
                        # Only fire copy-last when the foreground window belongs to Voice Flow
                        # (prevents clipboard corruption when user presses Ctrl+C in Chrome, etc.)
                        try:
                            fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
                            fg_len = ctypes.windll.user32.GetWindowTextLengthW(fg_hwnd)
                            fg_buf = ctypes.create_unicode_buffer(fg_len + 1)
                            ctypes.windll.user32.GetWindowTextW(fg_hwnd, fg_buf, fg_len + 1)
                            fg_title = fg_buf.value.lower()
                            fg_class_buf = ctypes.create_unicode_buffer(256)
                            ctypes.windll.user32.GetClassNameW(fg_hwnd, fg_class_buf, 256)
                            fg_class = fg_class_buf.value.lower()
                            is_voice_flow = (
                                "voice flow" in fg_title
                                or "voiceflow" in fg_title
                                or fg_class.startswith("tk")
                            )
                            if is_voice_flow:
                                threading.Thread(target=self._on_copy_last, daemon=True).start()
                        except Exception:
                            pass
                    # Do NOT return — let Ctrl+C pass through to the active app normally

                # Escape key cancels recording
                if key == keyboard.Key.esc:
                    if self._is_recording or self._hotkey_triggered:
                        self._is_recording = False
                        self._hotkey_triggered = False
                        self._mouse_hook.set_recording_state(False)
                        threading.Thread(target=self._safe_on_cancel, daemon=True).start()
        except Exception as e:
            log.exception("[INPUT] Key press handler error: %s", e)

    def _on_key_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        try:
            if key is None:
                return

            with self._lock:
                # Releasing Ctrl or Win key when Push-to-Talk shortcut was active
                if key in (
                    keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r,
                    keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
                ):
                    if self._hotkey_triggered:
                        _suppress_win_start_menu()
                        self._hotkey_triggered = False
                        self._is_recording = False
                        self._mouse_hook.set_recording_state(False)
                        # Finish recording, transcribe, and paste text into target app
                        threading.Thread(target=self._safe_on_finish, daemon=True).start()
        except Exception as e:
            log.exception("[INPUT] Key release handler error: %s", e)

    def _safe_on_start(self) -> None:
        try:
            self._on_start()
        except Exception as e:
            log.error("[INPUT] Error in on_start: %s", e)

    def _safe_on_finish(self) -> None:
        try:
            self._on_finish()
        except Exception as e:
            log.error("[INPUT] Error in on_finish: %s", e)

    def _safe_on_cancel(self) -> None:
        try:
            self._on_cancel()
        except Exception as e:
            log.error("[INPUT] Error in on_cancel: %s", e)

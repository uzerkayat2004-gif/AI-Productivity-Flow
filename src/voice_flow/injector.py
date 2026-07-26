"""Text injection module — pastes transcribed text into the active window via clipboard,
with specialized Microsoft Excel spreadsheet cell & table navigation support.
"""

from __future__ import annotations

import ctypes
import logging
import re
import threading
import time

import pyautogui
import pyperclip

from voice_flow.config import config

log = logging.getLogger(__name__)

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.02


def get_active_window_title() -> str:
    """Retrieve the title of the currently focused window on Windows."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value
    except Exception:
        return ""


def focus_target_window(hwnd: int) -> None:
    """Robustly restore window focus to target_hwnd on Windows before pasting."""
    if not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        current_foreground = user32.GetForegroundWindow()
        if current_foreground == hwnd:
            return

        # Restore if minimized
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE

        # Force foreground focus by attaching thread input
        fore_thread = user32.GetWindowThreadProcessId(current_foreground, None)
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        curr_thread = ctypes.windll.kernel32.GetCurrentThreadId()

        user32.AttachThreadInput(curr_thread, target_thread, True)
        if fore_thread != 0:
            user32.AttachThreadInput(fore_thread, target_thread, True)

        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)

        user32.AttachThreadInput(curr_thread, target_thread, False)
        if fore_thread != 0:
            user32.AttachThreadInput(fore_thread, target_thread, False)

        time.sleep(0.08)
    except Exception as e:
        log.warning("Failed to restore focus to hwnd %d: %s", hwnd, e)
        try:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            time.sleep(0.05)
        except Exception:
            pass


_paste_lock = threading.Lock()

VK_CONTROL = 0x11
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002

def _wait_for_modifiers_released(timeout_ms: int = 150) -> None:
    """Wait for Ctrl, Alt, and Win keys to be physically released before pasting."""
    start = time.time()
    user32 = ctypes.windll.user32
    while (time.time() - start) * 1000 < timeout_ms:
        ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
        win = bool((user32.GetAsyncKeyState(0x5B) & 0x8000) or (user32.GetAsyncKeyState(0x5C) & 0x8000))
        if not ctrl and not win:
            break
        time.sleep(0.01)

def _send_win32_ctrl_v() -> None:
    """Send clean Win32 Ctrl+V key combination without modifier key collision."""
    user32 = ctypes.windll.user32
    # Ensure Ctrl is down
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.01)
    # Press V
    user32.keybd_event(VK_V, 0, 0, 0)
    time.sleep(0.01)
    # Release V
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.01)
    # Release Ctrl
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

def inject_text(text: str, target_hwnd: int | None = None) -> bool:
    """Paste *text* into the currently focused or target window."""
    if not text:
        log.warning("inject_text called with empty text, skipping.")
        return False

    with _paste_lock:
        try:
            # Wait for physical Ctrl & Win keys to be released by user's fingers
            _wait_for_modifiers_released(timeout_ms=150)

            if target_hwnd:
                focus_target_window(target_hwnd)

            active_title = get_active_window_title()
            is_excel = any(kw in active_title.lower() for kw in ["excel", "workbook", "spreadsheet", "sheet", "csv"])

            formatted_text = text
            if is_excel or any(cmd in text.lower() for cmd in ["next cell", "next column", "next row", "new row"]):
                formatted_text = re.sub(r"\b(next cell|next column|tab)\b", "\t", formatted_text, flags=re.IGNORECASE)
                formatted_text = re.sub(r"\b(next row|new row)\b", "\n", formatted_text, flags=re.IGNORECASE)
                log.info("Excel voice navigation mode active for window: %s", active_title)

            try:
                original_clipboard = pyperclip.paste()
            except pyperclip.PyperclipException:
                original_clipboard = None

            pyperclip.copy(formatted_text)
            time.sleep(0.03)

            # Send clean Win32 Ctrl+V paste
            _send_win32_ctrl_v()

            time.sleep(config.clipboard_restore_delay_ms / 1000.0)

            if original_clipboard is not None:
                pyperclip.copy(original_clipboard)

            log.info("Text injected successfully into '%s' (%d chars).", active_title, len(formatted_text))
            return True

        except Exception:
            log.exception("Failed to inject text.")
            return False


class ClipboardInjector:
    """Class wrapper for Clipboard Injection."""

    def paste_text(self, text: str, target_hwnd: int | None = None) -> bool:
        return inject_text(text, target_hwnd)

"""Text injection module — pastes transcribed text into the active window via clipboard,
with specialized Microsoft Excel spreadsheet cell & table navigation support.
"""

from __future__ import annotations

import ctypes
import logging
import re
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
    """Restore window focus to target_hwnd before pasting."""
    if not hwnd:
        return
    try:
        if ctypes.windll.user32.IsIconic(hwnd):
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        time.sleep(0.08)
    except Exception as e:
        log.warning("Failed to restore focus to hwnd %d: %s", hwnd, e)


def inject_text(text: str, target_hwnd: int | None = None) -> bool:
    """Paste *text* into the currently focused or target window."""
    if not text:
        log.warning("inject_text called with empty text, skipping.")
        return False

    try:
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
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
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

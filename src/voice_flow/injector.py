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


def inject_text(text: str) -> bool:
    """Paste *text* into the currently focused window.

    Supports intelligent Microsoft Excel spreadsheet integration:
    - Automatically converts voice navigation commands ("next cell", "tab", "next row", "new line") to tab/newline separators for multi-cell Excel entry.
    - Preserves clipboard history.
    """
    if not text:
        log.warning("inject_text called with empty text, skipping.")
        return False

    try:
        active_title = get_active_window_title()
        is_excel = any(kw in active_title.lower() for kw in ["excel", "workbook", "spreadsheet", "sheet", "csv"])

        formatted_text = text
        # Excel cell voice navigation formatting
        if is_excel or any(cmd in text.lower() for cmd in ["next cell", "next column", "next row", "new row"]):
            formatted_text = re.sub(r"\b(next cell|next column|tab)\b", "\t", formatted_text, flags=re.IGNORECASE)
            formatted_text = re.sub(r"\b(next row|new row)\b", "\n", formatted_text, flags=re.IGNORECASE)
            log.info("Excel voice navigation mode active for window: %s", active_title)

        # Save current clipboard
        try:
            original_clipboard = pyperclip.paste()
        except pyperclip.PyperclipException:
            original_clipboard = None

        # Copy transcribed text to clipboard
        pyperclip.copy(formatted_text)

        # Small delay to ensure clipboard is set
        time.sleep(0.05)

        # Paste via Ctrl+V into active application or Excel cell
        pyautogui.hotkey("ctrl", "v")

        # Wait a moment, then restore original clipboard
        time.sleep(config.clipboard_restore_delay_ms / 1000.0)
        if original_clipboard is not None:
            pyperclip.copy(original_clipboard)

        log.info("Text injected successfully into '%s' (%d chars).", active_title, len(formatted_text))
        return True

    except Exception:
        log.exception("Failed to inject text.")
        return False

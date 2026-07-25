"""Text injection module — pastes transcribed text into the active window via clipboard."""

from __future__ import annotations

import logging
import time

import pyautogui
import pyperclip

from voice_flow.config import config

log = logging.getLogger(__name__)

# Disable pyautogui's fail-safe (moving mouse to corner kills script)
pyautogui.FAILSAFE = False
# Minimal pause between pyautogui actions
pyautogui.PAUSE = 0.02


def inject_text(text: str) -> bool:
    """Paste *text* into the currently focused window.

    Saves the current clipboard contents, copies the new text,
    performs Ctrl+V, then restores the original clipboard.

    Returns True on success, False on failure.
    """
    if not text:
        log.warning("inject_text called with empty text, skipping.")
        return False

    try:
        # Save current clipboard
        try:
            original_clipboard = pyperclip.paste()
        except pyperclip.PyperclipException:
            original_clipboard = None

        # Copy transcribed text to clipboard
        pyperclip.copy(text)

        # Small delay to ensure clipboard is set
        time.sleep(0.05)

        # Paste via Ctrl+V
        pyautogui.hotkey("ctrl", "v")

        # Wait a moment, then restore original clipboard
        time.sleep(config.clipboard_restore_delay_ms / 1000.0)
        if original_clipboard is not None:
            pyperclip.copy(original_clipboard)

        log.info("Text injected successfully (%d chars).", len(text))
        return True

    except Exception:
        log.exception("Failed to inject text.")
        return False

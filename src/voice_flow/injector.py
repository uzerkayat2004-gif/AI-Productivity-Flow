"""Text injection module — pastes transcribed text into the active window via clipboard,
with specialized Microsoft Excel spreadsheet cell & table navigation support and Win32 clipboard fallback.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
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

# Win32 Virtual Key Codes
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_RETURN = 0x0D
VK_V = 0x56
VK_C = 0x43
VK_INSERT = 0x2D
VK_LWIN = 0x5B
VK_RWIN = 0x5C
KEYEVENTF_KEYUP = 0x0002

# Win32 Clipboard Formats
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def get_active_window_title() -> str:
    """Retrieve the title of the currently focused window on Windows."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return ""
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value
    except Exception:
        return ""


def get_window_class_name(hwnd: int) -> str:
    """Retrieve the Win32 class name of the given window."""
    try:
        if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
            return ""
        buff = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(hwnd, buff, 256)
        return buff.value
    except Exception:
        return ""


def focus_target_window(hwnd: int) -> None:
    """Robustly restore window focus to target_hwnd on Windows before pasting."""
    if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
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

        if target_thread != curr_thread:
            user32.AttachThreadInput(curr_thread, target_thread, True)
        if fore_thread != 0 and fore_thread != target_thread:
            user32.AttachThreadInput(fore_thread, target_thread, True)

        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)

        if target_thread != curr_thread:
            user32.AttachThreadInput(curr_thread, target_thread, False)
        if fore_thread != 0 and fore_thread != target_thread:
            user32.AttachThreadInput(fore_thread, target_thread, False)

        time.sleep(0.06)
    except Exception as e:
        log.warning("[INJECTOR] Failed to restore focus to hwnd %d: %s", hwnd, e)
        try:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            time.sleep(0.04)
        except Exception:
            pass


_paste_lock = threading.Lock()


def _force_release_modifiers() -> None:
    """Force release any held modifier keys (Win, Alt, Shift, Ctrl) to prevent hotkey collisions."""
    user32 = ctypes.windll.user32
    for vk in (VK_LWIN, VK_RWIN, VK_MENU, VK_SHIFT, VK_CONTROL):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _wait_for_modifiers_released(timeout_ms: int = 120) -> None:
    """Wait for Ctrl, Alt, and Win keys to be physically released before pasting."""
    start = time.time()
    user32 = ctypes.windll.user32
    while (time.time() - start) * 1000 < timeout_ms:
        ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
        win = bool((user32.GetAsyncKeyState(VK_LWIN) & 0x8000) or (user32.GetAsyncKeyState(VK_RWIN) & 0x8000))
        alt = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
        if not ctrl and not win and not alt:
            break
        time.sleep(0.01)
    _force_release_modifiers()


def _set_clipboard_win32(text: str) -> bool:
    """Direct native Win32 clipboard writer fallback."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    for _ in range(5):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                text_bytes = text.encode("utf-16le") + b"\x00\x00"
                h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(text_bytes))
                if h_mem:
                    p_mem = kernel32.GlobalLock(h_mem)
                    if p_mem:
                        ctypes.memmove(p_mem, text_bytes, len(text_bytes))
                        kernel32.GlobalUnlock(h_mem)
                        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
                return True
            finally:
                user32.CloseClipboard()
        time.sleep(0.02)
    return False


def _safe_copy_to_clipboard(text: str) -> bool:
    """Copy text to clipboard with retries and native Win32 fallback."""
    for _ in range(3):
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            time.sleep(0.02)
    return _set_clipboard_win32(text)


def _safe_paste_from_clipboard() -> str:
    """Read text from clipboard safely."""
    for _ in range(3):
        try:
            return pyperclip.paste() or ""
        except Exception:
            time.sleep(0.02)
    return ""


def _send_win32_ctrl_v() -> None:
    """Send clean Win32 Ctrl+V key combination without modifier key collision."""
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.01)
    user32.keybd_event(VK_V, 0, 0, 0)
    time.sleep(0.01)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.01)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def _send_win32_shift_insert() -> None:
    """Send Shift+Insert paste for console and terminal windows."""
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_SHIFT, 0, 0, 0)
    time.sleep(0.01)
    user32.keybd_event(VK_INSERT, 0, 0, 0)
    time.sleep(0.01)
    user32.keybd_event(VK_INSERT, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.01)
    user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)


def _send_win32_enter() -> None:
    """Send Win32 Return/Enter key event."""
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_RETURN, 0, 0, 0)
    time.sleep(0.01)
    user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)


def _send_win32_ctrl_c() -> None:
    """Send Win32 Ctrl+C copy event."""
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.01)
    user32.keybd_event(VK_C, 0, 0, 0)
    time.sleep(0.01)
    user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.01)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def _format_text_for_title(text: str, window_title: str) -> str:
    """Format text appropriately for the target window (e.g. Excel navigation commands)."""
    if not text:
        return ""
    is_excel = any(kw in (window_title or "").lower() for kw in ["excel", "workbook", "spreadsheet", "sheet", "csv"])
    if not is_excel:
        return text

    clean = text.strip()
    clean_lower = clean.lower()

    if clean_lower in ("next cell.", "next cell!", "next cell?", "next cell", "next column.", "next column!", "next column", "tab.", "tab"):
        return "\t"
    if clean_lower in ("next row.", "next row!", "next row?", "next row", "new row.", "new row!", "new row"):
        return "\n"

    formatted_text = re.sub(r"\b(next cell|next column|tab)\b", "\t", text, flags=re.IGNORECASE)
    formatted_text = re.sub(r"\b(next row|new row)\b", "\n", formatted_text, flags=re.IGNORECASE)
    log.info("[INJECTOR] Excel voice navigation mode active for window: %s", window_title)
    return formatted_text


def inject_text(text: str, target_hwnd: int | None = None, press_enter: bool = False) -> bool:
    """Paste *text* into the currently focused or target window."""
    if not text:
        log.warning("[INJECTOR] inject_text called with empty text, skipping.")
        return False

    with _paste_lock:
        try:
            # Wait for physical Ctrl & Win keys to be released
            _wait_for_modifiers_released(timeout_ms=120)

            if target_hwnd:
                focus_target_window(target_hwnd)

            active_hwnd = ctypes.windll.user32.GetForegroundWindow()
            active_title = get_active_window_title()
            active_class = get_window_class_name(active_hwnd)
            formatted_text = _format_text_for_title(text, active_title)

            # Preserve existing clipboard
            original_clipboard = _safe_paste_from_clipboard()

            # Copy text to clipboard
            _safe_copy_to_clipboard(formatted_text)
            time.sleep(0.03)

            # Detect console / terminal windows via class name and title
            is_console = (
                active_class in ("ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "mintty", "PuTTY", "VirtualConsoleClass")
                or any(kw in active_title.lower() for kw in ["cmd", "powershell", "terminal", "bash", "ubuntu", "command prompt", "putty", "mintty", "pwsh"])
            )

            if is_console:
                _send_win32_shift_insert()
            else:
                _send_win32_ctrl_v()

            if press_enter:
                time.sleep(0.05)
                _send_win32_enter()

            # Delay before restoring previous clipboard content
            time.sleep(config.clipboard_restore_delay_ms / 1000.0)

            if original_clipboard:
                _safe_copy_to_clipboard(original_clipboard)

            log.info("[INJECTOR] Text injected successfully into '%s' (%d chars).", active_title, len(formatted_text))
            return True

        except Exception:
            log.exception("[INJECTOR] Failed to inject text.")
            return False


class ClipboardInjector:
    """Class wrapper for Clipboard Injection."""

    def paste_text(self, text: str, target_hwnd: int | None = None, press_enter: bool = False) -> bool:
        return inject_text(text, target_hwnd, press_enter=press_enter)

    def get_selected_text_strict(self, target_hwnd: int | None = None) -> str:
        """Capture currently highlighted/selected text in the target window without corrupting clipboard.

        SAFEGUARD: Skips sending synthetic Ctrl+C to console and terminal windows (Terminal, PowerShell, CMD,
        mintty, etc.) to prevent sending SIGINT break signals that terminate running CLI agents (Codex, Claude, etc.).
        """
        with _paste_lock:
            try:
                _wait_for_modifiers_released(timeout_ms=100)
                # NEVER call focus_target_window() here — it steals focus and drags
                # the terminal to the foreground, interrupting running CLI agents.
                # Always read selected text from whatever window is currently focused.
                active_hwnd = ctypes.windll.user32.GetForegroundWindow()
                active_title = get_active_window_title()
                active_class = get_window_class_name(active_hwnd) if active_hwnd else ""

                # Console / terminal windows MUST NOT receive synthetic Ctrl+C as it sends SIGINT and kills CLI processes
                is_console = (
                    active_class in ("ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "mintty", "PuTTY", "VirtualConsoleClass")
                    or any(kw in (active_title or "").lower() for kw in ["cmd", "powershell", "terminal", "bash", "ubuntu", "command prompt", "putty", "mintty", "pwsh", "codex", "claude"])
                )

                if is_console:
                    log.info("[INJECTOR] Skipping synthetic Ctrl+C text capture in console window to preserve running CLI processes.")
                    return ""

                original_clipboard = _safe_paste_from_clipboard()

                _safe_copy_to_clipboard("")
                time.sleep(0.02)

                _send_win32_ctrl_c()

                selected = ""
                for _ in range(5):
                    time.sleep(0.03)
                    selected = _safe_paste_from_clipboard()
                    if selected and len(selected.strip()) > 0:
                        break

                if original_clipboard:
                    _safe_copy_to_clipboard(original_clipboard)

                return selected or ""
            except Exception as e:
                log.error("[INJECTOR] Failed to capture selected text: %s", e)
                return ""

    def get_selected_text(self, target_hwnd: int | None = None) -> str:
        return self.get_selected_text_strict(target_hwnd)

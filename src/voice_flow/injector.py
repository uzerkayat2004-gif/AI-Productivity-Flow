"""Text injection module — pastes transcribed text into the active window via clipboard,
with specialized Microsoft Excel spreadsheet cell & table navigation support and Win32 clipboard fallback.
"""

from __future__ import annotations

import ctypes
from voice_flow.platform.wincompat import wintypes, windll, IS_WINDOWS
import logging
import os
import re
import sys
import threading
import time

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.02
except Exception:
    pyautogui = None  # type: ignore[assignment]

import pyperclip

from voice_flow.config import config

log = logging.getLogger(__name__)

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
VK_NONAME = 0xE8  # Unassigned dummy key to suppress Windows Start Menu popup
KEYEVENTF_KEYUP = 0x0002

# Synthetic event marker for low-level hooks
VF_SYNTHETIC_EXTRA_INFO = 0x56464C57  # 'VFLW'

# Win32 Clipboard Formats
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

_INTERNAL_EXACT_TITLES = {
    "ai productivity flow",
    "productivity flow",
    "voice flow",
    "voice flow - ai speech desktop app",
    "start",
    "search",
    "windows input experience",
    "startmenuexperiencehost",
}

_TERMINAL_CLASSES = {
    "consolewindowclass",
    "cascadia_hosting_window_class",
    "mintty",
    "putty",
    "virtualconsoleclass",
    "alacritty",
    "wezterm",
    "windowsterminal",
}

_TERMINAL_EXE_NAMES = {
    "windowsterminal.exe",
    "wt.exe",
    "powershell.exe",
    "pwsh.exe",
    "cmd.exe",
    "conhost.exe",
    "bash.exe",
    "wsl.exe",
    "mintty.exe",
    "putty.exe",
    "alacritty.exe",
    "wezterm-gui.exe",
    "kitty.exe",
}

_EXTERNAL_INDICATOR_SUBSTRINGS = (
    "antigravity",
    "visual studio code",
    " - code",
    "code - oss",
    "cursor",
    "sublime",
    "notepad",
    "google chrome",
    " - chrome",
    "microsoft edge",
    " - edge",
    "mozilla firefox",
    " - firefox",
    "brave",
    "opera",
    "twitter",
    "x.com",
    "slack",
    "discord",
    "whatsapp",
    "telegram",
    "word",
    "excel",
    "powerpoint",
    "outlook",
    "onenote",
    "cmd.exe",
    "cmd",
    "command prompt",
    "powershell",
    "pwsh",
    "windows terminal",
    "terminal",
    "bash",
    "git bash",
    "zsh",
    "wsl",
    "ubuntu",
    "conhost",
    "cascadia",
    "putty",
    "mintty",
    "alacritty",
    "wezterm",
    "kitty",
)


def _get_process_name_safe(pid: int) -> str:
    """Safely query the executable image base name for a PID with limited rights."""
    if not pid:
        return ""
    if not IS_WINDOWS:
        try:
            import psutil
            return psutil.Process(pid).name().lower()
        except Exception:
            return ""
    try:
        kernel32 = windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h_proc:
            try:
                buff = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(h_proc, 0, buff, ctypes.byref(size)):
                    return os.path.basename(buff.value).lower()
            finally:
                kernel32.CloseHandle(h_proc)
    except Exception:
        pass
    return ""


def is_internal_window(hwnd: int | None, overlay_hwnd: int | None = None) -> bool:
    """Check if hwnd belongs to AI Productivity Flow itself (overlay bar, desktop GUI, settings).

    Returns True for:
      - The Tkinter overlay bar
      - The 'AI Productivity Flow' desktop GUI window (and its children/ancestors)
      - Any dialog or helper window created by this app
      - Closed/invalid handles (to prevent injecting into dead windows)

    Returns False for external user applications:
      - Terminals and console windows (Windows Terminal, PowerShell, CMD, Git Bash, PuTTY, etc.)
      - Antigravity (e.g. 'Gathering Voice Flow Context - Antigravity')
      - Visual Studio Code (e.g. 'voice_flow.py - Visual Studio Code')
      - Browsers: Chrome, Edge, Firefox, Brave, etc.
      - Text editors: Notepad, Cursor, Sublime, etc.
      - Social / Communication apps: Twitter / X, Slack, Discord, etc.
    """
    if not hwnd or hwnd == 0:
        return True
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        if not user32.IsWindow(hwnd):
            return True

        # Process ID check: if this hwnd belongs to our own Python process
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return True

        # Direct overlay handle check
        if overlay_hwnd and hwnd == overlay_hwnd:
            return True

        # Collect titles and class names of hwnd, its root ancestor, and its root owner
        root = user32.GetAncestor(hwnd, 2)  # GA_ROOT = 2
        owner = user32.GetAncestor(hwnd, 3)  # GA_ROOTOWNER = 3

        def _get_title_safe(h: int) -> str:
            if not h or not user32.IsWindow(h):
                return ""
            length = user32.GetWindowTextLengthW(h)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(h, buff, length + 1)
            return buff.value.strip()

        def _get_class_safe(h: int) -> str:
            if not h or not user32.IsWindow(h):
                return ""
            buff = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, buff, 256)
            return buff.value.strip()

        handles_to_check = [hwnd]
        if root and root != hwnd:
            handles_to_check.append(root)
        if owner and owner not in handles_to_check:
            handles_to_check.append(owner)

        titles = [_get_title_safe(h) for h in handles_to_check if h]
        classes = [_get_class_safe(h) for h in handles_to_check if h]

        # TERMINAL BYPASS: Terminals and command prompts running outside our process
        # are ALWAYS external injection targets, even if opened in a directory named
        # 'voice-flow' or hosted inside XAML island windows.
        proc_name = _get_process_name_safe(pid.value) if pid.value else ""
        if proc_name in _TERMINAL_EXE_NAMES:
            return False

        for c in classes:
            c_lower = c.lower()
            if c_lower in _TERMINAL_CLASSES:
                return False

        # FIRST PRIORITY: Guard against external applications that might mention "Voice Flow"
        # in their title (e.g. Antigravity chat, VS Code editing voice_flow.py, terminal tab cd'd to voice-flow)
        for t in titles:
            t_lower = t.lower()
            if any(ext in t_lower for ext in _EXTERNAL_INDICATOR_SUBSTRINGS):
                return False

        # Find known internal window HWNDs (only valid if owned by our PID)
        for known_title in ("AI Productivity Flow", "Voice Flow", "Voice Flow - AI Speech Desktop App"):
            known_h = user32.FindWindowW(None, known_title)
            if known_h and hwnd == known_h:
                known_pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(known_h, ctypes.byref(known_pid))
                if known_pid.value == os.getpid():
                    return True

        # SECOND PRIORITY: Check for Windows shell/start menu or exact internal app title
        for t in titles:
            t_lower = t.lower()
            if t_lower in ("start", "search", "windows input experience", "startmenuexperiencehost"):
                return True
            if t_lower in _INTERNAL_EXACT_TITLES or t_lower.startswith("ai productivity flow") or t_lower.startswith("productivity flow"):
                # An exact internal title is decisive on its own: no external
                # application is ever titled exactly "AI Productivity Flow".
                # The pid check is a second opinion only when the owner is
                # known; a pid of 0 means the owner could not be determined,
                # not that the window is external.
                if not pid.value or pid.value == os.getpid():
                    return True

        # Check Tkinter overlay class and Windows Shell/Start menu classes
        # Note: 'windows.ui.core.corewindow' and 'xamlexplorerhostislandwindow' are used by both
        # Windows Shell and Windows Terminal/UWP apps. Only flag as internal shell if the process
        # belongs to Windows Shell (StartMenuExperienceHost, SearchApp, explorer, etc.)
        _SHELL_PROCESSES = {"startmenuexperiencehost.exe", "searchapp.exe", "searchhost.exe", "shellexperiencehost.exe"}
        _SHELL_CLASSES = ("shell_traywnd", "shell_secondarytraywnd")
        for c in classes:
            c_lower = c.lower()
            if c_lower.startswith("tk") and pid.value == os.getpid():
                return True
            if c_lower in _SHELL_CLASSES:
                return True
            if c_lower in ("windows.ui.core.corewindow", "xamlexplorerhostislandwindow", "startmenuexperiencehost"):
                if proc_name in _SHELL_PROCESSES or not proc_name:
                    return True

        return False
    except Exception:
        return False


def get_active_window_title() -> str:
    """Retrieve the title of the currently focused window."""
    if not IS_WINDOWS:
        try:
            from voice_flow.platform import get_backend
            return get_backend().active_window_title()
        except Exception:
            return ""
    try:
        user32 = windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value
    except Exception:
        return ""


def get_window_class_name(hwnd: int) -> str:
    """Retrieve the Win32 class name of the given window."""
    if not IS_WINDOWS or not hwnd:
        return ""
    try:
        user32 = windll.user32
        if not user32.IsWindow(hwnd):
            return ""
        buff = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buff, 256)
        return buff.value
    except Exception:
        return ""


def is_same_window_hierarchy(hwnd1: int | None, hwnd2: int | None) -> bool:
    """Check if hwnd1 and hwnd2 refer to the same window or belongs to the same window hierarchy.
    
    This handles cases where hwnd1 is a child control (e.g. Windows Terminal text area or XAML island)
    and hwnd2 is the top-level window (or vice-versa), or both share the same root ancestor.
    """
    if not IS_WINDOWS or not hwnd1 or not hwnd2:
        return False
    if hwnd1 == hwnd2:
        return True
    try:
        user32 = getattr(ctypes, "windll", windll).user32
        if user32.IsChild(hwnd1, hwnd2) or user32.IsChild(hwnd2, hwnd1):
            return True
        root1 = user32.GetAncestor(hwnd1, 2) or hwnd1  # GA_ROOT = 2
        root2 = user32.GetAncestor(hwnd2, 2) or hwnd2
        if root1 == root2 or root1 == hwnd2 or root2 == hwnd1:
            return True
        owner1 = user32.GetAncestor(hwnd1, 3) or hwnd1  # GA_ROOTOWNER = 3
        owner2 = user32.GetAncestor(hwnd2, 3) or hwnd2
        if owner1 == owner2 or owner1 == hwnd2 or owner2 == hwnd1:
            return True
    except Exception:
        pass
    return False


def focus_target_window(hwnd: int) -> None:
    """Robustly restore window focus to target_hwnd on Windows before pasting.
    
    Operates on the root ancestor top-level window so child island windows (such as in Windows Terminal)
    can be brought to the foreground properly, then sets input focus to the target HWND.
    """
    if not IS_WINDOWS or not hwnd:
        return
    try:
        user32 = windll.user32
        if not user32.IsWindow(hwnd) or is_internal_window(hwnd):
            return
        current_foreground = user32.GetForegroundWindow()
        if is_same_window_hierarchy(current_foreground, hwnd):
            user32.SetFocus(hwnd)
            return

        # Top-level root ancestor is required for SetForegroundWindow
        root_target = user32.GetAncestor(hwnd, 2) or hwnd

        # Restore if minimized
        if user32.IsIconic(root_target):
            user32.ShowWindow(root_target, 9)  # SW_RESTORE
        elif user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)

        # Force foreground focus by attaching thread input
        fore_thread = user32.GetWindowThreadProcessId(current_foreground, None)
        target_thread = user32.GetWindowThreadProcessId(root_target, None)
        curr_thread = windll.kernel32.GetCurrentThreadId()

        if target_thread != curr_thread:
            user32.AttachThreadInput(curr_thread, target_thread, True)
        if fore_thread != 0 and fore_thread != target_thread:
            user32.AttachThreadInput(fore_thread, target_thread, True)

        user32.BringWindowToTop(root_target)
        user32.SetForegroundWindow(root_target)
        if hwnd != root_target:
            user32.BringWindowToTop(hwnd)
            user32.SetFocus(hwnd)
        else:
            user32.SetFocus(root_target)

        if target_thread != curr_thread:
            user32.AttachThreadInput(curr_thread, target_thread, False)
        if fore_thread != 0 and fore_thread != target_thread:
            user32.AttachThreadInput(fore_thread, target_thread, False)

        time.sleep(0.045)
    except Exception as e:
        log.warning("[INJECTOR] Failed to restore focus to hwnd %d: %s", hwnd, e)
        try:
            root_target = windll.user32.GetAncestor(hwnd, 2) or hwnd
            windll.user32.SetForegroundWindow(root_target)
            time.sleep(0.04)
        except Exception:
            pass


_paste_lock = threading.Lock()
_clipboard_restore_token = 0
_clipboard_token_lock = threading.Lock()


def _suppress_win_start_menu() -> None:
    """Send a dummy key event to prevent Windows from opening the Start menu on Win key release."""
    if not IS_WINDOWS:
        return
    try:
        user32 = windll.user32
        user32.keybd_event(VK_CONTROL, 0, 0, VF_SYNTHETIC_EXTRA_INFO)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, VF_SYNTHETIC_EXTRA_INFO)
        user32.keybd_event(VK_NONAME, 0, 0, VF_SYNTHETIC_EXTRA_INFO)
        user32.keybd_event(VK_NONAME, 0, KEYEVENTF_KEYUP, VF_SYNTHETIC_EXTRA_INFO)
    except Exception:
        pass


def _force_release_modifiers() -> None:
    """Force release any held modifier keys (Win, Alt, Shift, Ctrl) to prevent hotkey collisions.
    Crucially suppresses Windows Start Menu opening if Win key is released."""
    if not IS_WINDOWS:
        return
    try:
        user32 = windll.user32
        win_down = bool((user32.GetAsyncKeyState(VK_LWIN) & 0x8000) or (user32.GetAsyncKeyState(VK_RWIN) & 0x8000))
        if win_down:
            _suppress_win_start_menu()
        for vk in (VK_LWIN, VK_RWIN, VK_MENU, VK_SHIFT, VK_CONTROL):
            if bool(user32.GetAsyncKeyState(vk) & 0x8000):
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, VF_SYNTHETIC_EXTRA_INFO)
        if win_down:
            _suppress_win_start_menu()
    except Exception:
        pass


def _wait_for_modifiers_released(timeout_ms: int = 100) -> None:
    """Wait for Ctrl, Alt, Shift, and Win keys to be physically released before pasting."""
    if not IS_WINDOWS:
        return
    try:
        start = time.time()
        user32 = windll.user32
        while (time.time() - start) * 1000 < timeout_ms:
            ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
            win = bool((user32.GetAsyncKeyState(VK_LWIN) & 0x8000) or (user32.GetAsyncKeyState(VK_RWIN) & 0x8000))
            alt = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
            shift = bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)
            if not ctrl and not win and not alt and not shift:
                break
            time.sleep(0.003)
        _force_release_modifiers()
    except Exception:
        pass


def _set_clipboard_win32(text: str) -> bool:
    """Direct native Win32 clipboard writer fallback."""
    if not IS_WINDOWS:
        return False
    user32 = windll.user32
    kernel32 = windll.kernel32
    # Without explicit prototypes ctypes truncates 64-bit HGLOBAL/HANDLE
    # returns to 32 bits -> GlobalLock hands back a garbage pointer.
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalFree.argtypes = (ctypes.c_void_p,)
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = (ctypes.c_uint, ctypes.c_void_p)

    for _ in range(5):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                text_bytes = text.encode("utf-16le") + b"\x00\x00"
                h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(text_bytes))
                if not h_mem:
                    return False
                p_mem = kernel32.GlobalLock(h_mem)
                if not p_mem:
                    kernel32.GlobalFree(h_mem)
                    return False
                try:
                    ctypes.memmove(p_mem, text_bytes, len(text_bytes))
                finally:
                    kernel32.GlobalUnlock(h_mem)
                if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
                    kernel32.GlobalFree(h_mem)
                    return False
                return True
            finally:
                user32.CloseClipboard()
        time.sleep(0.02)
    return False


def _safe_copy_to_clipboard(text: str) -> bool:
    """Copy text to clipboard with retries and native Win32 fallback."""
    if not IS_WINDOWS:
        try:
            from voice_flow.platform import get_backend
            return get_backend().copy_to_clipboard(text)
        except Exception:
            pass
    for _ in range(3):
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            time.sleep(0.02)
    return _set_clipboard_win32(text)


def _safe_paste_from_clipboard() -> str:
    """Read text from clipboard safely."""
    if not IS_WINDOWS:
        try:
            from voice_flow.platform import get_backend
            return get_backend().read_clipboard()
        except Exception:
            pass
    for _ in range(3):
        try:
            return pyperclip.paste() or ""
        except Exception:
            time.sleep(0.02)
    return ""


_synthetic_input_depth = 0
_synthetic_input_lock = threading.Lock()
_last_user_copy_time = 0.0


def mark_user_copy() -> None:
    """Record that the user physically invoked a Ctrl+C copy shortcut."""
    global _last_user_copy_time
    _last_user_copy_time = time.time()


def is_user_copy_recent(threshold_sec: float = 0.8) -> bool:
    """Check if the user physically performed a copy within recent seconds."""
    return (time.time() - _last_user_copy_time) < threshold_sec


def is_synthetic_input_active() -> bool:
    """Check whether a synthetic injection (Ctrl+C, Ctrl+V, Shift+Insert) is actively in progress."""
    with _synthetic_input_lock:
        return _synthetic_input_depth > 0


def set_synthetic_input_active(active: bool) -> None:
    """Explicitly set synthetic input state (useful for tests and manual injection contexts)."""
    global _synthetic_input_depth
    with _synthetic_input_lock:
        if active:
            _synthetic_input_depth += 1
        else:
            _synthetic_input_depth = 0


class _SyntheticScope:
    """Context manager to signal to global input hooks that upcoming events are synthetic."""

    def __enter__(self) -> None:
        global _synthetic_input_depth
        with _synthetic_input_lock:
            _synthetic_input_depth += 1

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        global _synthetic_input_depth
        time.sleep(0.015)
        with _synthetic_input_lock:
            if _synthetic_input_depth > 0:
                _synthetic_input_depth -= 1


def _send_win32_ctrl_v() -> None:
    """Send clean Win32 Ctrl+V key combination without modifier key collision."""
    user32 = ctypes.windll.user32
    # Ensure Windows key is not held down to prevent triggering Win+V (Clipboard History flyout)
    if bool((user32.GetAsyncKeyState(VK_LWIN) & 0x8000) or (user32.GetAsyncKeyState(VK_RWIN) & 0x8000)):
        _suppress_win_start_menu()
        user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, VF_SYNTHETIC_EXTRA_INFO)
        user32.keybd_event(VK_RWIN, 0, KEYEVENTF_KEYUP, VF_SYNTHETIC_EXTRA_INFO)
        _suppress_win_start_menu()
        time.sleep(0.005)

    with _SyntheticScope():
        scan_ctrl = user32.MapVirtualKeyW(VK_CONTROL, 0) or 0x1D
        scan_v = user32.MapVirtualKeyW(VK_V, 0) or 0x2F
        user32.keybd_event(VK_CONTROL, scan_ctrl, 0, VF_SYNTHETIC_EXTRA_INFO)
        time.sleep(0.012)
        user32.keybd_event(VK_V, scan_v, 0, VF_SYNTHETIC_EXTRA_INFO)
        time.sleep(0.012)
        user32.keybd_event(VK_V, scan_v, KEYEVENTF_KEYUP, VF_SYNTHETIC_EXTRA_INFO)
        time.sleep(0.012)
        user32.keybd_event(VK_CONTROL, scan_ctrl, KEYEVENTF_KEYUP, VF_SYNTHETIC_EXTRA_INFO)


def _send_win32_shift_insert() -> None:
    """Send Shift+Insert paste for legacy console and terminal windows (mintty, PuTTY)."""
    KEYEVENTF_EXTENDEDKEY = 0x0001
    with _SyntheticScope():
        user32 = ctypes.windll.user32
        scan_shift = user32.MapVirtualKeyW(VK_SHIFT, 0) or 0x2A
        scan_insert = user32.MapVirtualKeyW(VK_INSERT, 0) or 0x52
        user32.keybd_event(VK_SHIFT, scan_shift, 0, VF_SYNTHETIC_EXTRA_INFO)
        time.sleep(0.012)
        user32.keybd_event(VK_INSERT, scan_insert, KEYEVENTF_EXTENDEDKEY, VF_SYNTHETIC_EXTRA_INFO)
        time.sleep(0.012)
        user32.keybd_event(VK_INSERT, scan_insert, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, VF_SYNTHETIC_EXTRA_INFO)
        time.sleep(0.012)
        user32.keybd_event(VK_SHIFT, scan_shift, KEYEVENTF_KEYUP, VF_SYNTHETIC_EXTRA_INFO)


def _send_win32_ctrl_shift_c() -> None:
    """Send Win32 Ctrl+Shift+C to safely copy selected text in Windows Terminal without sending SIGINT."""
    with _SyntheticScope():
        user32 = ctypes.windll.user32
        scan_ctrl = user32.MapVirtualKeyW(VK_CONTROL, 0) or 0x1D
        scan_shift = user32.MapVirtualKeyW(VK_SHIFT, 0) or 0x2A
        scan_c = user32.MapVirtualKeyW(VK_C, 0) or 0x2E
        user32.keybd_event(VK_CONTROL, scan_ctrl, 0, VF_SYNTHETIC_EXTRA_INFO)
        time.sleep(0.01)
        user32.keybd_event(VK_SHIFT, scan_shift, 0, VF_SYNTHETIC_EXTRA_INFO)
        time.sleep(0.01)
        user32.keybd_event(VK_C, scan_c, 0, VF_SYNTHETIC_EXTRA_INFO)
        time.sleep(0.012)
        user32.keybd_event(VK_C, scan_c, KEYEVENTF_KEYUP, VF_SYNTHETIC_EXTRA_INFO)
        time.sleep(0.01)
        user32.keybd_event(VK_SHIFT, scan_shift, KEYEVENTF_KEYUP, VF_SYNTHETIC_EXTRA_INFO)
        time.sleep(0.01)
        user32.keybd_event(VK_CONTROL, scan_ctrl, KEYEVENTF_KEYUP, VF_SYNTHETIC_EXTRA_INFO)


def _send_win32_enter() -> None:
    """Send Win32 Return/Enter key event."""
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_RETURN, 0, 0, 0)
    time.sleep(0.01)
    user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)


def _send_win32_ctrl_c() -> None:
    """Send Win32 Ctrl+C copy event marked as synthetic."""
    with _SyntheticScope():
        user32 = ctypes.windll.user32
        user32.keybd_event(VK_CONTROL, 0, 0, VF_SYNTHETIC_EXTRA_INFO)
        time.sleep(0.015)
        user32.keybd_event(VK_C, 0, 0, VF_SYNTHETIC_EXTRA_INFO)
        time.sleep(0.015)
        user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, VF_SYNTHETIC_EXTRA_INFO)
        time.sleep(0.015)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, VF_SYNTHETIC_EXTRA_INFO)


def _format_text_for_title(text: str, window_title: str) -> str:
    """Format text appropriately for the target window (e.g. Excel navigation commands)."""
    if not text:
        return ""
    is_excel = any(kw in (window_title or "").lower() for kw in ["excel", "workbook", "spreadsheet", "sheet", "csv"])
    if not is_excel:
        return text

    # Handle Excel navigation shortcuts in dictation
    normalized = text.strip().lower().rstrip(".,!?")
    if normalized in ("next cell", "tab"):
        return "\t"
    if normalized in ("next row", "enter", "new row"):
        return "\n"
    return text


def inject_text(text: str, target_hwnd: int | None = None, press_enter: bool = False) -> bool:
    """Inject polished text into the target application window via clipboard paste."""
    if not text and not press_enter:
        log.warning("[INJECTOR] inject_text called with empty text, skipping.")
        return False

    if not IS_WINDOWS:
        try:
            from voice_flow.platform import get_backend
            backend = get_backend()
            if backend.is_own_window_focused():
                log.warning("[INJECTOR] Target is an internal app window; refusing to paste into internal app. Dictation remains safely on clipboard.")
                backend.copy_to_clipboard(text)
                return False
            saved = backend.read_clipboard()
            if not backend.copy_to_clipboard(text):
                log.error("[INJECTOR] Could not write text to clipboard; skipping paste.")
                return False
            time.sleep(0.015)
            ok = backend.send_paste()
            if press_enter:
                time.sleep(0.05)
                backend.send_enter()
            if saved:
                def _restore_clip():
                    time.sleep(0.2)
                    backend.copy_to_clipboard(saved)
                threading.Thread(target=_restore_clip, daemon=True).start()
            return bool(ok)
        except Exception as exc:
            log.error("[INJECTOR] Non-Windows inject_text failed: %s", exc)
            return False

    if target_hwnd and is_internal_window(target_hwnd):
        log.warning(
            "[INJECTOR] Target hwnd %d is an internal app window ('%s'); refusing to paste into internal app. Dictation remains safely on clipboard.",
            target_hwnd,
            get_active_window_title(),
        )
        _safe_copy_to_clipboard(text)
        return False

    with _paste_lock:
        original_clipboard = ""
        clipboard_changed = False
        try:
            # Wait for physical Ctrl, Alt, Shift & Win keys to be released
            _wait_for_modifiers_released(timeout_ms=80)

            if target_hwnd:
                if not ctypes.windll.user32.IsWindow(target_hwnd):
                    log.warning("[INJECTOR] Target window closed during dictation; refusing to paste into the focused window.")
                    return False
                focus_target_window(target_hwnd)
                # SetForegroundWindow can be denied by Windows' foreground
                # restrictions.  Do not turn that failure into a paste in
                # whichever unrelated app still has focus.
                # Verify that the active foreground window belongs to the target window hierarchy
                fg = ctypes.windll.user32.GetForegroundWindow()
                if not is_same_window_hierarchy(fg, target_hwnd):
                    log.warning("[INJECTOR] Could not focus target hwnd %d (active is %d); refusing to paste elsewhere.", target_hwnd, fg)
                    return False

            active_hwnd = ctypes.windll.user32.GetForegroundWindow()
            active_title = get_active_window_title()
            active_class = get_window_class_name(active_hwnd)

            if is_internal_window(active_hwnd):
                log.warning(
                    "[INJECTOR] Active foreground window is an internal app window ('%s'); refusing to paste into internal app. Dictation remains safely on clipboard.",
                    active_title,
                )
                _safe_copy_to_clipboard(text)
                return False

            formatted_text = _format_text_for_title(text, active_title)

            # Preserve existing clipboard
            original_clipboard = _safe_paste_from_clipboard()

            # Copy text to clipboard; if every write path failed, pasting would
            # inject whatever stale content sat on the clipboard — refuse instead.
            if not _safe_copy_to_clipboard(formatted_text):
                log.error("[INJECTOR] Could not write text to the clipboard; skipping paste.")
                _safe_copy_to_clipboard(original_clipboard)
                return False
            clipboard_changed = True
            time.sleep(0.015)

            # Dispatch paste keystroke:
            # Modern Windows Terminal, PowerShell, CMD, VS Code terminal, Alacritty: Ctrl+V
            # Legacy terminal emulators (mintty, PuTTY): Shift+Insert
            is_legacy_terminal = (
                active_class in ("mintty", "PuTTY")
                or any(kw in active_title.lower() for kw in ["putty", "mintty"])
            )

            if is_legacy_terminal:
                _send_win32_shift_insert()
            else:
                _send_win32_ctrl_v()

            if press_enter:
                time.sleep(0.05)
                _send_win32_enter()

            # Restore previous clipboard content asynchronously so the caller does not block
            global _clipboard_restore_token
            with _clipboard_token_lock:
                _clipboard_restore_token += 1
                token = _clipboard_restore_token

            def _restore_clipboard_async(orig_clip=original_clipboard, expected_token=token):
                delay = getattr(config, "clipboard_restore_delay_ms", 180) / 1000.0
                time.sleep(max(0.01, delay))
                with _clipboard_token_lock:
                    if _clipboard_restore_token != expected_token:
                        return
                _safe_copy_to_clipboard(orig_clip)

            threading.Thread(target=_restore_clipboard_async, daemon=True).start()

            log.info("[INJECTOR] Text injected successfully into '%s' (%d chars).", active_title, len(formatted_text))
            return True

        except Exception:
            log.exception("[INJECTOR] Failed to inject text.")
            if clipboard_changed:
                try:
                    _safe_copy_to_clipboard(original_clipboard)
                except Exception:
                    log.debug("[INJECTOR] Could not restore clipboard after failed paste.", exc_info=True)
            return False


class ClipboardInjector:
    """Class wrapper for Clipboard Injection."""

    def paste_text(self, text: str, target_hwnd: int | None = None, press_enter: bool = False) -> bool:
        return inject_text(text, target_hwnd, press_enter=press_enter)

    def get_selected_text_strict(self, target_hwnd: int | None = None) -> str:
        """Capture currently highlighted/selected text in the target window without corrupting clipboard.

        SAFEGUARD: Uses Ctrl+Shift+C for Windows Terminal to copy without sending SIGINT,
        and skips synthetic Ctrl+C for legacy console windows to protect running CLI processes.
        """
        with _paste_lock:
            if not IS_WINDOWS:
                try:
                    from voice_flow.platform import get_backend
                    return get_backend().get_selected_text()
                except Exception:
                    return ""
            try:
                user32 = windll.user32
                # 1. If the user is actively holding physical modifier keys (Ctrl, Win, Alt, Shift),
                # NEVER inject synthetic Ctrl+C which would collide with user keystrokes (e.g. Ctrl-click, Shift-select).
                # Crucially, NEVER synthesize fake keyup events here which would corrupt physical key states.
                if (
                    bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                    or bool((user32.GetAsyncKeyState(VK_LWIN) & 0x8000) or (user32.GetAsyncKeyState(VK_RWIN) & 0x8000))
                    or bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
                    or bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)
                ):
                    log.debug("[INJECTOR] Skipping synthetic text capture; user is holding modifier keys.")
                    return ""

                # 2. If the user recently performed a manual copy shortcut (Ctrl+C), abort capture
                if is_user_copy_recent():
                    log.debug("[INJECTOR] Skipping synthetic text capture; recent user copy detected.")
                    return ""

                # NEVER call focus_target_window() here — it steals focus and drags
                # the terminal to the foreground, interrupting running CLI agents.
                # Always read selected text from whatever window is currently focused.
                active_hwnd = user32.GetForegroundWindow()
                if not active_hwnd or is_internal_window(active_hwnd):
                    return ""
                active_title = get_active_window_title()
                active_class = get_window_class_name(active_hwnd) if active_hwnd else ""

                # Console / terminal handling:
                # Windows Terminal supports Ctrl+Shift+C to copy selected text safely without SIGINT.
                # Legacy consoles and interactive CLI shells (codex, claude) must not receive Ctrl+C.
                is_windows_terminal = (
                    active_class == "CASCADIA_HOSTING_WINDOW_CLASS"
                    or "windows terminal" in (active_title or "").lower()
                )
                is_other_console = (
                    not is_windows_terminal
                    and (
                        active_class in ("ConsoleWindowClass", "mintty", "PuTTY", "VirtualConsoleClass")
                        or any(kw in (active_title or "").lower() for kw in ["cmd", "powershell", "terminal", "bash", "ubuntu", "command prompt", "putty", "mintty", "pwsh", "codex", "claude"])
                    )
                )

                if is_other_console:
                    log.info("[INJECTOR] Skipping synthetic Ctrl+C text capture in console window to preserve running CLI processes.")
                    return ""

                original_clipboard = _safe_paste_from_clipboard()

                if original_clipboard:
                    _safe_copy_to_clipboard("")
                    time.sleep(0.02)

                if is_windows_terminal:
                    _send_win32_ctrl_shift_c()
                else:
                    _send_win32_ctrl_c()

                selected = ""
                for _ in range(5):
                    time.sleep(0.03)
                    selected = _safe_paste_from_clipboard()
                    if selected and len(selected.strip()) > 0:
                        break

                # Restore previous clipboard ONLY if the user did not invoke a manual copy during or right after
                if original_clipboard:
                    ctrl_held = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                    if not ctrl_held and not is_user_copy_recent():
                        _safe_copy_to_clipboard(original_clipboard)

                return selected or ""
            except Exception as e:
                log.error("[INJECTOR] Failed to capture selected text: %s", e)
                return ""

    def get_selected_text(self, target_hwnd: int | None = None) -> str:
        return self.get_selected_text_strict(target_hwnd)

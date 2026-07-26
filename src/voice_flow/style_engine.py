"""Active Foreground Window Detection & App-Specific Dictation Styles Engine.
Detects active target app (Outlook, Slack, WhatsApp, Chrome, Notion) and applies tailored style rules.
"""

from __future__ import annotations

import logging
import os
import sys

log = logging.getLogger(__name__)

# Style presets matching Wispr Flow research
STYLE_PRESETS = {
    "personal_messaging": {
        "name": "Casual / Personal Messages",
        "description": "Uses natural capitalization, friendly tone, concise phrasing.",
        "prompt_instruction": "Format as a friendly, natural chat message. Use standard capitalization and light punctuation.",
    },
    "work_messaging": {
        "name": "Work Messaging",
        "description": "Clear, professional, concise chat message for Slack/Teams.",
        "prompt_instruction": "Format cleanly for Slack/Teams. Keep it concise, clear, and professional.",
    },
    "email": {
        "name": "Email & Formal",
        "description": "Polished complete sentences, formal tone, full punctuation.",
        "prompt_instruction": "Format as a polished, formal email. Use complete sentences, proper capitalization, and standard punctuation.",
    },
    "auto_cleanup": {
        "name": "Smart Auto-Cleanup (Default)",
        "description": "Strips fillers (um/uh), resolves self-corrections, preserves natural voice.",
        "prompt_instruction": "Remove filler words ('um', 'uh', 'like'), resolve self-corrections, fix basic grammar, and capitalize sentences cleanly.",
    },
}


def get_active_app_info() -> tuple[str, str]:
    """Detect current active foreground window title and process executable name on Windows."""
    if sys.platform != "win32":
        return ("General App", "general.exe")

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ("General App", "general.exe")

        # Get window text length and title
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value.strip()

        # Get process ID and executable name
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        # Query process executable path
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010
        hProcess = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)

        exe_name = "general.exe"
        if hProcess:
            try:
                psapi = ctypes.windll.psapi
                exe_buf = ctypes.create_unicode_buffer(260)
                psapi.GetModuleFileNameExW(hProcess, None, exe_buf, 260)
                exe_path = exe_buf.value
                exe_name = os.path.basename(exe_path).lower()
            finally:
                kernel32.CloseHandle(hProcess)

        app_display = title if title else exe_name
        return (app_display, exe_name)

    except Exception as e:
        log.debug("Could not detect active window: %s", e)
        return ("General App", "general.exe")


def detect_app_category(app_title: str, exe_name: str) -> str:
    """Categorize app into Work Messaging, Personal Messaging, Email, or General."""
    title_lower = app_title.lower()
    exe_lower = exe_name.lower()

    if any(k in exe_lower or k in title_lower for k in ["slack", "teams", "discord"]):
        return "work_messaging"
    elif any(k in exe_lower or k in title_lower for k in ["whatsapp", "telegram", "messenger", "signal"]):
        return "personal_messaging"
    elif any(k in exe_lower or k in title_lower for k in ["outlook", "thunderbird", "mail", "gmail"]):
        return "email"
    else:
        return "auto_cleanup"


class StyleEngine:
    """Style manager for applying app-specific dictation prompts."""

    def __init__(self) -> None:
        self.default_style = "auto_cleanup"

    def get_style_for_current_app(self) -> tuple[str, str, dict[str, str]]:
        app_title, exe_name = get_active_app_info()
        category = detect_app_category(app_title, exe_name)
        preset = STYLE_PRESETS.get(category, STYLE_PRESETS["auto_cleanup"])
        return (app_title, category, preset)


# Singleton Style Engine Instance
style_engine = StyleEngine()

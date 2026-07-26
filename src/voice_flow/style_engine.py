"""Active Foreground Window Detection & App-Specific Dictation Styles Engine.
Detects active target app (Outlook, Slack, WhatsApp, Chrome, Notion) and applies tailored style rules.
"""

from __future__ import annotations

import logging
import os
import sys
from voice_flow.storage import storage

log = logging.getLogger(__name__)

# Complete style instructions dictionary matching all GUI cards
STYLE_INSTRUCTIONS = {
    # Personal Messaging Cards
    "personal_formal": "Rephrase as a formal personal message with standard capitalization and complete punctuation.",
    "personal_casual": "Rephrase as a casual personal chat message. Keep it friendly and natural. Capitalize normally, omit unnecessary trailing periods.",
    "personal_very_casual": "Rephrase as a very casual chat text. Use ALL LOWERCASE letters, short informal words, and no trailing punctuation.",

    # Work Messaging Cards
    "work_formal": "Rephrase as a formal professional work message. Use professional vocabulary, complete sentences, and formal grammar.",
    "work_casual": "Rephrase as a clear, concise work message for Slack/Teams. Professional yet conversational.",
    "work_excited": "Rephrase as an enthusiastic work message! Use positive upbeat language and exclamation marks!",

    # Email Cards
    "email_formal": "Format as a formal email draft with greeting, clear body paragraphs, and professional closing.",
    "email_casual": "Format as a casual email draft. Friendly, direct, and well-structured.",
    "email_excited": "Format as an enthusiastic email! Friendly tone with exclamations!",

    # Other Apps Cards
    "other_formal": "Format as a formal document or note. Use complete sentences, clear paragraphs, and precise punctuation.",
    "other_casual": "Format as a clean casual note. Relaxed tone and clear spacing.",
    "other_excited": "Format as energetic text! Use vibrant phrasing and exclamation marks!",

    # Auto Cleanup Cards
    "cleanup_none": "Transcribe verbatim. Keep exact words without editing.",
    "cleanup_light": "Clean up filler words ('um', 'uh', 'like', 'you know') and fix basic grammar while keeping original phrasing.",
    "cleanup_medium": "Edit for maximum clarity, conciseness, and impact. Remove filler words, fix awkward phrasing, and make the text flow smoothly."
}

# Category defaults
CATEGORY_DEFAULTS = {
    "personal": "personal_very_casual",
    "work": "work_casual",
    "email": "email_formal",
    "other": "other_formal",
    "autocleanup": "cleanup_light"
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

        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value.strip()

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

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
    """Categorize app into work, personal, email, other, or autocleanup."""
    title_lower = app_title.lower()
    exe_lower = exe_name.lower()

    if any(k in exe_lower or k in title_lower for k in ["slack", "teams", "discord", "linkedin"]):
        return "work"
    elif any(k in exe_lower or k in title_lower for k in ["whatsapp", "telegram", "messenger", "signal", "instagram"]):
        return "personal"
    elif any(k in exe_lower or k in title_lower for k in ["outlook", "thunderbird", "mail", "gmail"]):
        return "email"
    elif any(k in exe_lower or k in title_lower for k in ["notion", "word", "winword", "docs", "chatgpt"]):
        return "other"
    else:
        return "autocleanup"


class StyleEngine:
    """Style manager for applying user-configured app-specific dictation prompts."""

    def get_style_for_current_app(self) -> tuple[str, str, str]:
        app_title, exe_name = get_active_app_info()
        category = detect_app_category(app_title, exe_name)
        
        # Retrieve user selected style ID from SQLite storage for this category
        default_style_id = CATEGORY_DEFAULTS.get(category, "cleanup_light")
        style_id = storage.get_setting(f"style_{category}", default_style_id)

        instruction = STYLE_INSTRUCTIONS.get(style_id, STYLE_INSTRUCTIONS["cleanup_light"])
        log.info("[STYLE ENGINE] App: '%s' | Category: '%s' | Selected Style ID: '%s'", app_title, category, style_id)
        return (app_title, category, instruction)


# Singleton Style Engine Instance
style_engine = StyleEngine()

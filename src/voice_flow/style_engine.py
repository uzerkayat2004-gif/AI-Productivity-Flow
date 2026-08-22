"""Active Foreground Window Detection & App-Specific Dictation Styles Engine.
Detects active target app (Outlook, Slack, WhatsApp, Chrome, Notion) and applies tailored style rules.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from voice_flow.storage import storage
from voice_flow.style_models import (
    STYLE_CONFIGS,
    FORMAL_STYLE_CONFIG,
    CASUAL_STYLE_CONFIG,
    VERY_CASUAL_STYLE_CONFIG,
    EXCITED_STYLE_CONFIG,
    StyleConfig,
)

log = logging.getLogger(__name__)


@dataclass
class StylePreset:
    id: str
    name: str
    subtitle: str
    sample: str
    instruction: str
    category: str


@dataclass
class ResolvedStyle:
    app_name: str
    category: str
    style_id: str
    name: str
    instruction: str
    domain: str | None = None
    resolved_style: str = "casual"
    temporary_override: str | None = None
    config: StyleConfig = field(default_factory=lambda: FORMAL_STYLE_CONFIG)

    @property
    def style_label(self) -> str:
        return self.name

    @property
    def provider_instruction(self) -> str:
        return self.instruction


# Complete style instructions dictionary matching all GUI cards
STYLE_INSTRUCTIONS = {
    # Personal Messaging Cards
    "personal_formal": "Rephrase as a formal personal message with standard capitalization and complete punctuation.",
    "personal_casual": "Rephrase as a casual personal chat message. Keep it friendly and natural. Capitalize normally, omit unnecessary trailing periods.",
    "personal_very_casual": "Rephrase as a very casual chat text. Use ALL LOWERCASE letters, short informal words, and no trailing punctuation.",
    "personal_excited": "Rephrase as an enthusiastic personal chat message! Friendly tone with exclamations!",

    # Work Messaging Cards
    "work_formal": "Rephrase as a formal professional work message. Use professional vocabulary, complete sentences, and formal grammar.",
    "work_casual": "Rephrase as a clear, concise work message for Slack/Teams. Professional yet conversational.",
    "work_very_casual": "Rephrase as a casual work text with minimal punctuation.",
    "work_excited": "Rephrase as an enthusiastic work message! Use positive upbeat language and exclamation marks!",

    # Email Cards
    "email_formal": "Format as a formal email draft with greeting, clear body paragraphs, and professional closing.",
    "email_casual": "Format as a casual email draft. Friendly, direct, and well-structured.",
    "email_very_casual": "Format as a quick, informal email draft with minimal punctuation.",
    "email_excited": "Format as an enthusiastic email! Friendly tone with exclamations!",

    # Developer Cards
    "developer_formal": "Format as precise technical text with standard punctuation and protected code tokens.",
    "developer_casual": "Format as clear developer notes and conversational messages with protected code tokens.",
    "developer_very_casual": "Format as minimal developer text in lowercase with protected code tokens.",
    "developer_excited": "Format as an enthusiastic developer message with protected code tokens!",

    # Other Apps Cards
    "other_formal": "Format as a formal document or note. Use complete sentences, clear paragraphs, and precise punctuation.",
    "other_casual": "Format as a clean casual note. Relaxed tone and clear spacing.",
    "other_very_casual": "Format as a relaxed note in lowercase with minimal punctuation.",
    "other_excited": "Format as energetic text! Use vibrant phrasing and exclamation marks!",

    # Generic Style Keys
    "formal": "Rephrase with formal capitalization, grammar, and complete sentence-ending punctuation.",
    "casual": "Rephrase with natural capitalization, lighter punctuation, and friendly tone.",
    "very_casual": "Rephrase in lowercase with minimal punctuation.",
    "excited": "Rephrase with expressive punctuation and enthusiasm on positive statements!",

    # Auto Cleanup Cards
    "cleanup_none": "Transcribe verbatim. Keep exact words without editing.",
    "cleanup_light": "Clean up filler words ('um', 'uh', 'like', 'you know') and fix basic grammar while keeping original phrasing.",
    "cleanup_medium": "Edit for maximum clarity, conciseness, and impact. Remove filler words, fix awkward phrasing, and make the text flow smoothly.",
    "cleanup_high": "Thoroughly clean disfluencies, false starts, and repeated words for concise expression.",
}

STYLE_OPTIONS = STYLE_INSTRUCTIONS

# Category defaults
CATEGORY_DEFAULTS = {
    "personal": "personal_very_casual",
    "work": "work_casual",
    "email": "email_formal",
    "developer": "developer_casual",
    "other": "other_formal",
    "autocleanup": "cleanup_light",
}

# Detailed Style Preset Objects
STYLE_PRESETS: dict[str, StylePreset] = {
    "personal_formal": StylePreset("personal_formal", "Formal.", "Caps + Punctuation", "Hey, are you free for lunch tomorrow? Let's do 12:30 PM if that works for you.", STYLE_INSTRUCTIONS["personal_formal"], "personal"),
    "personal_casual": StylePreset("personal_casual", "Casual", "Caps + Less punctuation", "Hey are you free for lunch tomorrow? Let's do 12:30 if that works for you", STYLE_INSTRUCTIONS["personal_casual"], "personal"),
    "personal_very_casual": StylePreset("personal_very_casual", "very casual", "No Caps + Less punctuation", "hey are you free for lunch tomorrow let's do 12 if that works for you", STYLE_INSTRUCTIONS["personal_very_casual"], "personal"),
    "personal_excited": StylePreset("personal_excited", "Excited!", "More exclamations", "Hey Sarah, are you free for lunch tomorrow? Let's do 12:30! Can't wait!", STYLE_INSTRUCTIONS["personal_excited"], "personal"),

    "work_formal": StylePreset("work_formal", "Formal.", "Caps + Punctuation", "Hey team, just wanted to check if everyone reviewed the sprint roadmap. Let me know when you get a chance.", STYLE_INSTRUCTIONS["work_formal"], "work"),
    "work_casual": StylePreset("work_casual", "Casual", "Caps + Less punctuation", "Hey team, just wanted to check if everyone reviewed the sprint roadmap. Let me know when you get a chance", STYLE_INSTRUCTIONS["work_casual"], "work"),
    "work_very_casual": StylePreset("work_very_casual", "very casual", "Lowercase + Loose messaging", "hey team just wanted to check if everyone reviewed the sprint roadmap let me know when you get a chance", STYLE_INSTRUCTIONS["work_very_casual"], "work"),
    "work_excited": StylePreset("work_excited", "Excited!", "More exclamations", "Hey team, sprint goals are crushed! Amazing job everyone!", STYLE_INSTRUCTIONS["work_excited"], "work"),

    "email_formal": StylePreset("email_formal", "Formal.", "Caps + Punctuation", "Hi Alex,\n\nThank you for the update. I have reviewed the proposal and look forward to our next discussion.\n\nBest,\nMary", STYLE_INSTRUCTIONS["email_formal"], "email"),
    "email_casual": StylePreset("email_casual", "Casual", "Caps + Less punctuation", "Hi Alex, thanks for the update! I reviewed the proposal and look forward to our next discussion.\n\nBest,\nMary", STYLE_INSTRUCTIONS["email_casual"], "email"),
    "email_very_casual": StylePreset("email_very_casual", "very casual", "Minimal punctuation", "hi alex thanks for the update i reviewed the proposal and look forward to catching up", STYLE_INSTRUCTIONS["email_very_casual"], "email"),
    "email_excited": StylePreset("email_excited", "Excited!", "More exclamations", "Hi Alex,\n\nThank you so much for the update! Really excited to work together on this!\n\nBest,\nMary", STYLE_INSTRUCTIONS["email_excited"], "email"),

    "developer_formal": StylePreset("developer_formal", "Formal.", "Protected code tokens", "Please execute `npm run build` and verify that the API endpoint returns valid JSON.", STYLE_INSTRUCTIONS["developer_formal"], "developer"),
    "developer_casual": StylePreset("developer_casual", "Casual", "Conversational dev notes", "Check the PR on GitHub and run tests with pytest before deploying to staging", STYLE_INSTRUCTIONS["developer_casual"], "developer"),
    "developer_very_casual": StylePreset("developer_very_casual", "very casual", "Lowercase dev notes", "run git pull and check if the HTTP status code is 200 on localhost", STYLE_INSTRUCTIONS["developer_very_casual"], "developer"),
    "developer_excited": StylePreset("developer_excited", "Excited!", "Enthusiastic dev praise", "All 46 unit tests passed with 0 errors! Great job shipping v2.1!", STYLE_INSTRUCTIONS["developer_excited"], "developer"),

    "other_formal": StylePreset("other_formal", "Formal.", "Caps + Punctuation", "The product research audit shows strong demand across creator workflows. Next steps include architecture planning.", STYLE_INSTRUCTIONS["other_formal"], "other"),
    "other_casual": StylePreset("other_casual", "Casual", "Caps + Less punctuation", "The product research audit shows strong demand across creator workflows. Next steps include architecture planning", STYLE_INSTRUCTIONS["other_casual"], "other"),
    "other_very_casual": StylePreset("other_very_casual", "very casual", "Loose thoughts & notes", "the product research audit shows strong demand across creator workflows next steps include architecture planning", STYLE_INSTRUCTIONS["other_very_casual"], "other"),
    "other_excited": StylePreset("other_excited", "Excited!", "More exclamations", "The product research audit shows incredible demand! Super excited for next steps!", STYLE_INSTRUCTIONS["other_excited"], "other"),

    "cleanup_none": StylePreset("cleanup_none", "None", "Verbatim transcription", "hey joey we still on for coffee i think we maybe should leave earlier", STYLE_INSTRUCTIONS["cleanup_none"], "autocleanup"),
    "cleanup_light": StylePreset("cleanup_light", "Light", "Removes filler words", "Hey Joey, are we still on for coffee? I think we should leave earlier.", STYLE_INSTRUCTIONS["cleanup_light"], "autocleanup"),
    "cleanup_medium": StylePreset("cleanup_medium", "Medium", "Edits for clarity", "Hey Joey, are we still on for coffee? We should leave earlier.", STYLE_INSTRUCTIONS["cleanup_medium"], "autocleanup"),
    "cleanup_high": StylePreset("cleanup_high", "High", "Thorough cleanup", "We should probably leave earlier for coffee.", STYLE_INSTRUCTIONS["cleanup_high"], "autocleanup"),
}

STYLE_PRESETS_BY_CATEGORY: dict[str, dict[str, StylePreset]] = {
    "personal": {p.id: p for p in (STYLE_PRESETS["personal_formal"], STYLE_PRESETS["personal_casual"], STYLE_PRESETS["personal_very_casual"], STYLE_PRESETS["personal_excited"])},
    "work": {p.id: p for p in (STYLE_PRESETS["work_formal"], STYLE_PRESETS["work_casual"], STYLE_PRESETS["work_very_casual"], STYLE_PRESETS["work_excited"])},
    "email": {p.id: p for p in (STYLE_PRESETS["email_formal"], STYLE_PRESETS["email_casual"], STYLE_PRESETS["email_very_casual"], STYLE_PRESETS["email_excited"])},
    "developer": {p.id: p for p in (STYLE_PRESETS["developer_formal"], STYLE_PRESETS["developer_casual"], STYLE_PRESETS["developer_very_casual"], STYLE_PRESETS["developer_excited"])},
    "other": {p.id: p for p in (STYLE_PRESETS["other_formal"], STYLE_PRESETS["other_casual"], STYLE_PRESETS["other_very_casual"], STYLE_PRESETS["other_excited"])},
    "autocleanup": {p.id: p for p in (STYLE_PRESETS["cleanup_none"], STYLE_PRESETS["cleanup_light"], STYLE_PRESETS["cleanup_medium"], STYLE_PRESETS["cleanup_high"])},
}


class AppClassifier:
    """Classifies applications and browser domains into style categories with user override support."""

    def __init__(self):
        self._app_overrides: dict[str, str] = {}
        self._domain_overrides: dict[str, str] = {}
        self._load_overrides()

    def _load_overrides(self) -> None:
        try:
            raw_apps = storage.get_setting("style_app_overrides", "{}")
            self._app_overrides = json.loads(raw_apps) if isinstance(raw_apps, str) else dict(raw_apps or {})
        except Exception:
            self._app_overrides = {}

        try:
            raw_domains = storage.get_setting("style_domain_overrides", "{}")
            self._domain_overrides = json.loads(raw_domains) if isinstance(raw_domains, str) else dict(raw_domains or {})
        except Exception:
            self._domain_overrides = {}

    def _save_overrides(self) -> None:
        storage.save_setting("style_app_overrides", json.dumps(self._app_overrides))
        storage.save_setting("style_domain_overrides", json.dumps(self._domain_overrides))

    def set_app_override(self, exe_name: str, category: str) -> None:
        clean = exe_name.lower().strip()
        self._app_overrides[clean] = category.lower().strip()
        self._save_overrides()

    def remove_app_override(self, exe_name: str) -> None:
        clean = exe_name.lower().strip()
        if clean in self._app_overrides:
            del self._app_overrides[clean]
            self._save_overrides()

    def set_domain_override(self, domain: str, category: str) -> None:
        clean = domain.lower().strip()
        self._domain_overrides[clean] = category.lower().strip()
        self._save_overrides()

    def remove_domain_override(self, domain: str) -> None:
        clean = domain.lower().strip()
        if clean in self._domain_overrides:
            del self._domain_overrides[clean]
            self._save_overrides()

    def get_app_overrides(self) -> dict[str, str]:
        return dict(self._app_overrides)

    def get_domain_overrides(self) -> dict[str, str]:
        return dict(self._domain_overrides)

    def classify(self, title: str, exe_name: str, domain: str | None = None) -> str:
        # 1. User domain override
        if domain:
            dom_lower = domain.lower().strip()
            for pattern, cat in self._domain_overrides.items():
                if pattern in dom_lower:
                    return cat

        # 2. User app override
        exe_lower = exe_name.lower().strip()
        if exe_lower in self._app_overrides:
            return self._app_overrides[exe_lower]

        # 3. Built-in domain mappings
        if domain:
            dom_lower = domain.lower().strip()
            if any(k in dom_lower for k in ("mail.google.com", "outlook.live.com", "outlook.office.com", "mail.yahoo.com")):
                return "email"
            if any(k in dom_lower for k in ("app.slack.com", "teams.microsoft.com", "linear.app", "jira.", "atlassian.net", "asana.com", "trello.com", "linkedin.com")):
                return "work"
            if any(k in dom_lower for k in ("web.whatsapp.com", "web.telegram.org", "discord.com", "messages.google.com", "instagram.com", "messenger.com")):
                return "personal"
            if any(k in dom_lower for k in ("github.com", "gitlab.com", "stackoverflow.com", "cursor.sh")):
                return "developer"
            if any(k in dom_lower for k in ("notion.so", "docs.google.com", "claude.ai", "chatgpt.com", "chat.openai.com")):
                return "other"
            return "other"

        # 4. Built-in app title/exe mappings
        title_lower = title.lower() if title else ""

        # Work apps
        if any(w in exe_lower or w in title_lower for w in ("slack", "teams", "linear", "jira", "asana", "trello", "linkedin")):
            return "work"

        # Personal messaging apps
        if any(p in exe_lower or p in title_lower for p in ("whatsapp", "telegram", "signal", "discord", "messages", "messenger", "instagram", "wechat")):
            return "personal"

        # Email apps
        if any(e in exe_lower or e in title_lower for e in ("outlook", "thunderbird", "superhuman", "mailbird", "winmail", "gmail")):
            return "email"

        # Developer apps
        if any(d in exe_lower or d in title_lower for d in ("code", "cursor", "pycharm", "sublime", "terminal", "powershell", "cmd.exe", "wt.exe", "github")):
            # If explicit developer check
            if "claude code" in title_lower:
                return "other"
            return "developer"

        # Other / Documents / AI / Browser
        if any(o in exe_lower or o in title_lower for o in ("notion", "word", "winword", "claude", "chatgpt", "notepad", "chrome", "firefox", "edge", "brave")):
            return "other"

        return "other"


class StyleOverrideManager:
    """Manages temporary per-session style overrides with automatic reversion."""

    def __init__(self):
        self._temporary_override: str | None = None

    def set_temporary_override(self, style_id: str) -> None:
        self._temporary_override = style_id

    def get_temporary_override(self) -> str | None:
        return self._temporary_override

    def clear_temporary_override(self) -> None:
        self._temporary_override = None

    def consume_temporary_override(self) -> str | None:
        val = self._temporary_override
        self._temporary_override = None
        return val


def detect_app_category(title: str, exe_name: str, domain: str | None = None) -> str:
    """Helper function to detect app category."""
    classifier = AppClassifier()
    return classifier.classify(title, exe_name, domain)


def normalize_app_name(title: str, exe_name: str) -> str:
    title_lower = title.lower()
    exe_lower = exe_name.lower()

    if "chrome" in exe_lower or "chrome" in title_lower:
        return "Google Chrome"
    if "code" in exe_lower or "visual studio code" in title_lower or "vscode" in title_lower:
        return "VS Code"
    if "claude" in title_lower or "claude" in exe_lower:
        return "Claude Code"
    if "slack" in exe_lower or "slack" in title_lower:
        return "Slack"
    if "teams" in exe_lower or "teams" in title_lower:
        return "Microsoft Teams"
    if "whatsapp" in exe_lower or "whatsapp" in title_lower:
        return "WhatsApp"
    if "telegram" in exe_lower or "telegram" in title_lower:
        return "Telegram"
    if "outlook" in exe_lower or "outlook" in title_lower:
        return "Outlook"
    if "word" in exe_lower or "winword" in exe_lower or "word" in title_lower:
        return "Microsoft Word"
    if "notion" in exe_lower or "notion" in title_lower:
        return "Notion"
    if "explorer" in exe_lower:
        return "File Explorer"

    if " - " in title:
        parts = [p.strip() for p in title.split(" - ")]
        if len(parts) >= 2:
            return parts[-1]

    clean_exe = exe_name.replace(".exe", "").capitalize()
    if clean_exe and clean_exe != "General":
        return clean_exe

    return title[:28] if title else "General App"


def get_app_info_for_hwnd(hwnd: int | None) -> tuple[str, str]:
    if sys.platform != "win32" or not hwnd:
        return ("General App", "general.exe")

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        window_title = buff.value.strip()

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        exe_name = "general.exe"
        if pid.value:
            import win32process
            import win32api
            import win32con

            try:
                handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid.value)
                if handle:
                    exe_name = os.path.basename(win32process.GetModuleFileNameEx(handle, 0))
                    win32api.CloseHandle(handle)
            except Exception:
                pass

        app_name = normalize_app_name(window_title, exe_name)
        return (app_name, exe_name)
    except Exception as err:
        log.debug("Failed getting app info for hwnd %s: %s", hwnd, err)
        return ("General App", "general.exe")


def get_active_app_info() -> tuple[str, str]:
    if sys.platform != "win32":
        return ("General App", "general.exe")

    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        return get_app_info_for_hwnd(hwnd)
    except Exception as err:
        log.debug("Active window detection fallback: %s", err)
        return ("General App", "general.exe")


def _window_title_for_hwnd(hwnd: int | None) -> str:
    """Return the raw window title (e.g. the browser tab text) for classification.

    The normalized display name collapses every Chrome/Edge window to
    "Google Chrome", which would hide the site-specific tab title the
    classifier needs (WhatsApp Web, Slack, GitHub, ...).
    """
    if sys.platform != "win32" or not hwnd:
        return ""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value.strip()
    except Exception:
        return ""


get_window_title_for_hwnd = _window_title_for_hwnd


def _active_window_title() -> str:
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        return _window_title_for_hwnd(ctypes.windll.user32.GetForegroundWindow())
    except Exception:
        return ""


_CATEGORY_STYLE_PREFIXES = ("personal_", "work_", "email_", "developer_", "other_")


def _canonical_style(style_id: str) -> str:
    """Strip any category card prefix so an id resolves to its base style."""
    for prefix in _CATEGORY_STYLE_PREFIXES:
        if style_id.startswith(prefix):
            return style_id[len(prefix):]
    return style_id


class StyleEngine:
    """Orchestrates active application detection, user category styles, overrides, and formatting resolution."""

    def __init__(self) -> None:
        self.classifier = AppClassifier()
        self.override_manager = StyleOverrideManager()
        self._last_resolved: ResolvedStyle | None = None

    @property
    def last_resolved_style(self) -> ResolvedStyle | None:
        return self._last_resolved

    def get_category_style(self, category: str) -> str:
        default_val = CATEGORY_DEFAULTS.get(category, "casual")
        raw_val = storage.get_setting(f"style_{category}", default_val)
        # Normalize to canonical short style if stored as full card ID or vice-versa
        return _canonical_style(raw_val)

    def set_category_style(self, category: str, style_id: str) -> None:
        storage.save_setting(f"style_{category}", style_id)

    def resolve(
        self,
        hwnd: int | None = None,
        site_host: str | None = None,
        consume_override: bool = False,
    ) -> ResolvedStyle:
        app_name, exe_name = get_app_info_for_hwnd(hwnd) if hwnd else get_active_app_info()
        raw_title = _window_title_for_hwnd(hwnd) if hwnd else _active_window_title()
        category = self.classifier.classify(raw_title or app_name, exe_name, domain=site_host)

        # Default style for category
        cat_style_id = self.get_category_style(category)

        # Check temporary override
        temp_override = (
            self.override_manager.consume_temporary_override()
            if consume_override
            else self.override_manager.get_temporary_override()
        )

        resolved_short = temp_override or cat_style_id
        clean_short = _canonical_style(resolved_short)
        if clean_short not in STYLE_CONFIGS:
            clean_short = "casual"

        config = STYLE_CONFIGS.get(clean_short, FORMAL_STYLE_CONFIG)
        full_style_id = f"{category}_{clean_short}"
        preset = STYLE_PRESETS.get(full_style_id) or STYLE_PRESETS.get(resolved_short)
        name = preset.name if preset else clean_short.capitalize()
        instruction = STYLE_INSTRUCTIONS.get(full_style_id, STYLE_INSTRUCTIONS.get(clean_short, "Format text."))

        result = ResolvedStyle(
            app_name=app_name,
            category=category,
            style_id=full_style_id if full_style_id in STYLE_PRESETS else resolved_short,
            name=name,
            instruction=instruction,
            domain=site_host,
            resolved_style=clean_short,
            temporary_override=temp_override,
            config=config,
        )
        self._last_resolved = result
        return result

    def get_style_for_current_app(self) -> tuple[str, str, str]:
        """Legacy API: returns (app_title, category, instruction) for the current foreground app."""
        app_title, exe_name = get_active_app_info()
        category = self.classifier.classify(app_title, exe_name)
        default_style_id = CATEGORY_DEFAULTS.get(category, "cleanup_light")
        style_id = storage.get_setting(f"style_{category}", default_style_id)
        instruction = STYLE_INSTRUCTIONS.get(style_id, STYLE_INSTRUCTIONS.get("cleanup_light", "Format text."))
        log.info("[STYLE ENGINE] App: '%s' | Category: '%s' | Selected Style ID: '%s'", app_title, category, style_id)
        return (app_title, category, instruction)

    def get_session_style_for_hwnd(self, hwnd: int | None, site_host: str | None = None) -> tuple[str, str, str, str]:
        resolved = self.resolve(hwnd, site_host=site_host)
        cleanup_level = str(storage.get_setting("style_autocleanup", "cleanup_light"))
        return (resolved.app_name, resolved.category, resolved.style_id, cleanup_level)

    def resolve_for_target(self, hwnd: int | None, consume_override: bool = True) -> ResolvedStyle:
        app_name, exe_name = get_app_info_for_hwnd(hwnd) if hwnd else get_active_app_info()
        raw_title = _window_title_for_hwnd(hwnd) if hwnd else _active_window_title()
        category = self.classifier.classify(raw_title or app_name, exe_name)

        # A temporary override is an explicit user choice for the next
        # dictation and applies regardless of the detected category.
        temp_override = (
            self.override_manager.consume_temporary_override()
            if consume_override
            else self.override_manager.get_temporary_override()
        )

        stored = storage.get_setting(f"style_{category}", CATEGORY_DEFAULTS.get(category, "other_formal"))
        if temp_override:
            style_id = temp_override
        # Check if stored setting belongs to this category
        elif not stored.startswith(f"{category}_") and stored not in ("formal", "casual", "very_casual", "excited"):
            style_id = CATEGORY_DEFAULTS.get(category, "other_formal")
        else:
            style_id = stored

        clean_short = _canonical_style(style_id)
        if clean_short not in STYLE_CONFIGS:
            clean_short = "casual"
        preset = STYLE_PRESETS.get(style_id) or STYLE_PRESETS.get(f"{category}_{clean_short}")
        name = preset.name if preset else clean_short.capitalize()
        instruction = STYLE_INSTRUCTIONS.get(style_id) or STYLE_INSTRUCTIONS.get(f"{category}_{clean_short}", "Format text.")

        result = ResolvedStyle(
            app_name=app_name,
            category=category,
            style_id=style_id,
            name=name,
            instruction=instruction,
            resolved_style=clean_short,
            temporary_override=temp_override,
            config=STYLE_CONFIGS.get(clean_short, FORMAL_STYLE_CONFIG),
        )
        self._last_resolved = result
        return result


style_engine = StyleEngine()

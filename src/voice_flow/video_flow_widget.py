"""System-wide Video Flow composer and player launcher.

The composer is intentionally independent of the desktop dashboard. It is
attached to the floating bar's Tk root so selected text or documents can
become a video without opening the main Voice Flow application.

Supports Google NotebookLM (Default / Active) with Auto-Adaptive document
scaling, format presets, styles, live document analysis, and Native Engine (Visual V2.1).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.parse
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

log = logging.getLogger("voice_flow.video_flow_widget")

from voice_flow.video_flow_documents import DOCUMENT_EXTENSIONS, MAX_DOCUMENT_BYTES, extract_document_text
from voice_flow.storage import storage

try:
    from voice_flow.video_flow_engine.notebooklm.document_profiler import (
        DocumentProfile,
        analyze_document_source,
        format_duration_display,
    )
except Exception:
    DocumentProfile = None  # type: ignore[assignment,misc]
    analyze_document_source = None  # type: ignore[assignment]
    format_duration_display = None  # type: ignore[assignment]


LOCAL_MODEL_REF = "local/deterministic"

# Refined, dual-theme Sunrise design palette
COMPOSER_LIGHT_COLORS = {
    "background": "#fff8f3",      # OFFWHITE page behind the card
    "surface": "#ffffff",         # WHITE card
    "surface_soft": "#ffe3d0",    # ORANGE_SOFT
    "surface_faint": "#fff3ea",   # ORANGE_FAINT
    "text": "#241708",            # INK
    "muted": "#8a8a93",           # GRAY
    "border": "#ffd0b0",          # BORDER
    "border_focus": "#ff6a00",    # Orange focus highlight
    "orange": "#ff6a00",          # Signature Sunrise orange
    "orange_dark": "#e85d04",     # Orange active/hover
    "orange_light": "#ffedd5",    # Light orange badge
    "green": "#10b981",           # Connected green
    "green_bg": "#ecfdf5",        # Light green bg
    "green_border": "#a7f3d0",    # Light green border
    "green_text": "#047857",      # Dark green text
    "amber": "#d97706",           # Amber text
    "amber_bg": "#fffbeb",        # Amber pill bg
    "amber_border": "#fde68a",    # Amber pill border
    "amber_text": "#b45309",      # Dark amber text
}

COMPOSER_DARK_COLORS = {
    "background": "#161615",      # Warm dark canvas (--polish-canvas)
    "surface": "#20201f",         # Deep matte paper surface (--polish-paper)
    "surface_soft": "#282725",    # Elevated container/well (--polish-well)
    "surface_faint": "#282725",   # Input background
    "text": "#f5f1ea",            # Warm ink (--polish-ink)
    "muted": "#b6aea2",           # Muted text (--polish-muted)
    "border": "#3b3834",          # Subtle border line (--polish-line)
    "border_focus": "#e6b092",    # Warm secondary accent (--polish-accent)
    "orange": "#e6b092",          # Warm champagne/peach secondary accent
    "orange_dark": "#d49474",     # Active accent
    "orange_light": "#372c25",    # Warm dark tint badge (--polish-tint)
    "green": "#34d399",           # Connected green
    "green_bg": "#14291f",        # Dark green bg
    "green_border": "#1d4a36",    # Dark green border
    "green_text": "#4ade80",      # Bright green text
    "amber": "#fbbf24",           # Amber text
    "amber_bg": "#2b2413",        # Dark amber pill bg
    "amber_border": "#4a3b18",    # Dark amber pill border
    "amber_text": "#fbbf24",      # Dark amber text
}


def get_composer_colors() -> dict[str, str]:
    """Return the composer color tokens matching on_screen_ui_theme."""
    try:
        from voice_flow.storage import storage
        t = str(storage.get_setting("on_screen_ui_theme", "light") or "light").strip().lower()
        if t == "dark":
            return dict(COMPOSER_DARK_COLORS)
    except Exception:
        pass
    return dict(COMPOSER_LIGHT_COLORS)


COMPOSER_COLORS = get_composer_colors()

# Sunrise grid animation tones: light mode and dark mode
GRID_TONES_LIGHT = ("#ff6a00", "#ff8b3d", "#ffb488", "#ffcdb4", "#ffe3d0")
GRID_TONES_DARK = ("#e6b092", "#d49474", "#b67b5e", "#785340", "#372c25")
GRID_TONES = GRID_TONES_LIGHT
GRID_TICK_MS = 80
GRID_IDLE_DOT = 1

NOTEBOOKLM_FORMAT_OPTIONS: list[dict[str, str]] = [
    {
        "ref": "auto",
        "label": "Auto-Adaptive (Recommended)",
        "detail": "Scales video runtime to document size (Max 5m ceiling)",
    },
    {
        "ref": "brief",
        "label": "Brief (~1–2 min)",
        "detail": "Concise high-yield summary",
    },
    {
        "ref": "short",
        "label": "Shorts (9:16 Vertical)",
        "detail": "High-impact vertical video for YouTube Shorts, Reels & TikTok (~1–2.5 min)",
    },
    {
        "ref": "explainer",
        "label": "Explainer (~2–4 min)",
        "detail": "Structured visual breakdown",
    },
    {
        "ref": "cinematic",
        "label": "Cinematic (~1–5 min Max)",
        "detail": "High-production AI documentary strictly capped at 5 min",
    },
]

NOTEBOOKLM_STYLE_OPTIONS: list[dict[str, str]] = [
    {"ref": "auto", "label": "Auto", "detail": "Adapts style automatically to the topic"},
    {"ref": "classic", "label": "Classic", "detail": "Clean, polished presentation"},
    {"ref": "whiteboard", "label": "Whiteboard", "detail": "Hand-drawn whiteboard explainer"},
    {"ref": "anime", "label": "Anime", "detail": "Dynamic anime illustration style"},
    {"ref": "kawaii", "label": "Kawaii", "detail": "Cute, friendly, playful aesthetic"},
    {"ref": "watercolor", "label": "Watercolor", "detail": "Artistic watercolor & textures"},
    {"ref": "retro-print", "label": "Retro-print", "detail": "Vintage print & halftone style"},
    {"ref": "heritage", "label": "Heritage", "detail": "Editorial documentary style"},
    {"ref": "paper-craft", "label": "Paper-craft", "detail": "Layered cutout paper art"},
    {"ref": "custom", "label": "Custom", "detail": "Provide your own custom style directive"},
]


def _local_analyze_fallback(
    text: str,
    requested_format: str = "auto",
    task: str = "",
    title: str = "",
    focus: str = "",
    mode: str = "",
) -> dict[str, Any]:
    words = text.split()
    word_count = len(words)
    pages = round(word_count / 275.0, 2)
    reading_min = round(word_count / 200.0, 2)

    valid_mode = mode if mode and str(mode).strip().lower() not in {"summary", "full", "default", "normal", "auto"} else ""
    context = f"{task} {title} {focus} {valid_mode}".lower()
    text_lower = text.lower()
    is_tech = any(k in context or k in text_lower for k in (
        "api", "endpoint", "tutorial", "sop", "standard operating procedure", "documentation",
        "reference", "manual", "guide", "sdk", "architecture", "troubleshooting", "installation",
        "setup", "configuration", "code", "schema", "schemas", "payload", "parameter", "parameters",
        "procedure", "protocol", "step-by-step", "walkthrough"
    )) or ("```" in text) or bool(re.search(r"\bStep\s+\d+[:.]", text, re.IGNORECASE))

    is_edu = any(k in context or k in text_lower for k in (
        "course", "curriculum", "lesson", "module", "study guide", "syllabus", "textbook",
        "quiz", "lecture", "homework", "exam", "learning objectives", "learning objective",
        "explainer", "explanation"
    )) or bool(re.search(r"^\s*#.*(?:lesson|module|curriculum|syllabus|learning objective)", text, re.IGNORECASE | re.MULTILINE))

    is_sum = any(k in context or k in text_lower for k in (
        "meeting", "minutes", "meeting minutes", "meeting notes", "action items", "action item",
        "recap", "standup", "sync", "status report", "digest", "tl;dr", "tldr", "agenda", "attendees"
    )) or (bool(re.search(r"\bsummary\b", context)) if context else False) or bool(re.search(r"^\s*#.*(?:meeting|minutes|action item|agenda|attendee|executive summary)", text, re.IGNORECASE | re.MULTILINE))

    is_nar = any(k in context or k in text_lower for k in (
        "cinematic", "documentary", "history", "historical", "story", "storytelling", "narrative",
        "chronicle", "biography", "memoir", "case study", "deep dive", "journey", "epic", "legend"
    ))

    if word_count < 150:
        ratio = word_count / 150.0 if word_count > 0 else 0.0
        seconds = int(round(30 + ratio * 15))
        default_fmt = "short"
        pacing = "brisk"
    elif word_count < 500:
        ratio = (word_count - 150) / 350.0
        seconds = int(round(60 + ratio * 30))
        default_fmt = "brief"
        pacing = "brisk"
    elif word_count < 1200:
        ratio = (word_count - 500) / 700.0
        if is_sum and not is_tech and not is_edu:
            seconds = min(120, int(round(90 + ratio * 30)))
            default_fmt = "brief"
            pacing = "brisk"
        else:
            seconds = int(round(90 + ratio * 60))
            default_fmt = "explainer"
            pacing = "balanced"
    elif word_count < 2500:
        ratio = (word_count - 1200) / 1300.0
        if is_sum and not is_tech and not is_edu:
            seconds = 120
            default_fmt = "brief"
            pacing = "balanced"
        else:
            seconds = int(round(150 + ratio * 60))
            default_fmt = "explainer"
            pacing = "measured"
    else:
        # Large Documents (2500+ words): Task/content-aware auto-adaptation
        if is_tech or is_edu:
            ratio = min(1.0, (word_count - 2500) / 2500.0)
            seconds = min(240, int(round(180 + ratio * 60)))
            default_fmt = "explainer"
            pacing = "measured"
        elif is_sum and not is_tech and not is_edu:
            ratio = min(1.0, (word_count - 2500) / 2500.0)
            seconds = min(120, int(round(90 + ratio * 30)))
            default_fmt = "brief"
            pacing = "balanced"
        else:
            ratio = min(1.0, (word_count - 2500) / 2500.0)
            seconds = min(300, int(round(240 + ratio * 60)))
            default_fmt = "cinematic"
            pacing = "measured"

    clean_req = str(requested_format or "").strip().lower()
    is_auto = clean_req in {"", "auto", "auto-adaptive", "default", "recommended"}
    if is_auto:
        format_name = default_fmt
    else:
        format_name = clean_req

    try:
        from .video_flow_engine.notebooklm.document_profiler import extract_document_sections, compute_format_duration, analyze_content_value
        sections = extract_document_sections(text) if text else []
        content_val = analyze_content_value(text) if text else None
    except Exception:
        sections = []
        compute_format_duration = None
        content_val = None

    density_score = content_val.density_score if content_val else 1.0
    concept_count = content_val.concept_count if content_val else 0

    if is_auto and content_val and (
        (content_val.density_score >= 1.4 and content_val.concept_count >= 4)
        or (content_val.summary_of_large_work and content_val.concept_count >= 3)
        or content_val.high_concept_density
    ):
        format_name = "cinematic" if (is_nar or content_val.summary_of_large_work) else "explainer"
        pacing = "measured"
        max_exp = 300 if (density_score >= 1.85 or concept_count >= 8) else 240
        seconds = min(300, max(180, int(round(140 * density_score)))) if format_name == "cinematic" else min(max_exp, max(150, int(round(120 * density_score))))
    elif not is_auto and compute_format_duration is not None:
        seconds, pacing = compute_format_duration(
            word_count,
            format_name,
            len(sections),
            density_score=density_score,
            concept_count=concept_count,
            content_value=content_val,
        )
    else:
        if format_name == "brief":
            if word_count <= 270:
                seconds = 45
            elif word_count <= 1350:
                seconds = min(120, int(round(45 + (word_count - 270) * (75.0 / 1080))))
            else:
                seconds = 120
            pacing = "brisk"
        elif format_name == "short":
            if word_count <= 150:
                ratio_s = word_count / 150.0 if word_count > 0 else 0.0
                seconds = max(30, int(round(30 + ratio_s * 15)))
            elif word_count <= 270:
                seconds = 50
            elif word_count <= 1350:
                seconds = min(150, int(round(50 + (word_count - 270) * (100.0 / 1080))))
            else:
                seconds = 150
            pacing = "brisk"
        elif format_name == "explainer":
            if word_count <= 270:
                seconds = 75
            elif word_count <= 1350:
                seconds = min(240, int(round(75 + (word_count - 270) * (165.0 / 1080))))
            else:
                seconds = 240
            pacing = "balanced" if word_count < 1200 else "measured"
        elif format_name == "cinematic":
            if word_count <= 300:
                seconds = 60
            elif word_count <= 1350:
                seconds = min(240, int(round(60 + (word_count - 300) * (180.0 / 1050))))
            else:
                seconds = min(300, int(round(240 + (word_count - 1350) * 0.05)))
            pacing = "measured"

        if len(sections) >= 2:
            if format_name == "short":
                seconds = min(150, max(seconds, len(sections) * 12))
            elif format_name == "brief":
                seconds = min(120, max(seconds, len(sections) * 14))
            elif format_name == "explainer":
                seconds = min(240, max(seconds, len(sections) * 20))
            elif format_name == "cinematic":
                seconds = min(300, max(seconds, len(sections) * 25))

    seconds = max(30, min(300, seconds))
    m = seconds // 60
    s = seconds % 60
    ceiling_suffix = " (Max ceiling)" if seconds >= 240 else ""
    dur_str = f"~{m}m {s:02d}s{ceiling_suffix}" if m > 0 else f"~{s}s{ceiling_suffix}"

    return {
        "word_count": word_count,
        "char_count": len(text),
        "estimated_pages": pages,
        "estimated_reading_minutes": reading_min,
        "target_duration_seconds": seconds,
        "target_duration_display": dur_str,
        "recommended_format": format_name,
        "pacing_style": pacing,
        "section_count": len(sections),
        "sections": sections,
        "density_score": density_score,
        "content_value_rating": getattr(content_val, "content_value_rating", "standard") if content_val else "standard",
        "concept_count": concept_count,
        "effective_word_count": getattr(content_val, "effective_word_count", word_count) if content_val else word_count,
        "redundancy_score": getattr(content_val, "redundancy_score", 0.0) if content_val else 0.0,
        "substantive_concepts": list(getattr(content_val, "substantive_concepts", ())) if content_val else [],
    }


class VideoFlowScreenWidget:
    """Always-on-top composer that delegates queued jobs to the main runtime."""

    def __init__(self) -> None:
        self.root: tk.Tk | None = None
        self.win: tk.Toplevel | None = None
        self.on_generate: Callable[[dict[str, Any]], dict[str, Any]] | None = None
        self._source_text = ""
        self._source_name = ""
        self._initial_text = ""
        self._initial_title = ""
        self._mode = "summary"
        self._provider = "notebooklm"
        self._controls: dict[str, Any] = {}
        self._cached_catalog: dict[str, Any] = {}
        self._catalog_request_id: int = 0
        self._ui_queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._ui_poll_id: str | None = None
        self._model_options: dict[str, dict[str, str]] = {}
        self._theme_options: dict[str, dict[str, str]] = {}
        self._format_options: dict[str, dict[str, str]] = {}
        self._style_options: dict[str, dict[str, str]] = {}
        self._latest_profile: Any = None
        self._notebooklm_frame: tk.Frame | None = None
        self._native_frame: tk.Frame | None = None
        self._title_frame: tk.Frame | None = None
        self._custom_style_frame: tk.Frame | None = None
        self._sync_scroll_region: Callable[..., None] | None = None
        self._grid_dots: list[tk.Frame] = []
        self._grid_step = 0
        self._grid_animating = False
        self._grid_after_id: str | None = None
        self._nlm_format: tk.StringVar | None = None
        self._nlm_style: tk.StringVar | None = None
        self._nlm_style_prompt: tk.StringVar | None = None
        self._nlm_focus: tk.Text | None = None
        self._auth_banner_frame: tk.Frame | None = None
        self._auth_pill_frame: tk.Frame | None = None
        self._auth_status_label: tk.Label | None = None
        self._auth_signin_btn: tk.Button | None = None
        self._auth_is_authenticated: bool = False
        self._auth_email: str | None = None
        self._source_section: tk.Frame | None = None

    def attach_root(self, root: tk.Tk) -> None:
        self.root = root
        self._schedule_ui_poll()

    def _schedule_ui_poll(self) -> None:
        root = self.root or getattr(tk, "_default_root", None)
        if root is not None and self._ui_poll_id is None:
            try:
                if getattr(root, "_tclCommands", None) is not None and root.winfo_exists():
                    self._ui_poll_id = root.after(20, self._poll_ui_queue)
            except Exception:
                self._ui_poll_id = None

    def _poll_ui_queue(self) -> None:
        self._ui_poll_id = None
        self._process_ui_queue()
        root = self.root or getattr(tk, "_default_root", None)
        if root is not None:
            try:
                if getattr(root, "_tclCommands", None) is not None and root.winfo_exists():
                    self._ui_poll_id = root.after(20, self._poll_ui_queue)
            except Exception:
                self._ui_poll_id = None

    def _process_ui_queue(self) -> None:
        if not hasattr(self, "_ui_queue"):
            return
        while not self._ui_queue.empty():
            try:
                callback = self._ui_queue.get_nowait()
                callback()
            except Exception as exc:
                log.exception("Error running callback in video_flow_widget UI queue: %s", exc)

    def launch(self, selected_text: str = "", mode: str = "summary") -> "VideoFlowScreenWidget":
        """Public, stable entrypoint for callers outside the dashboard."""
        self.show_composer(selected_text, mode)
        return self

    @staticmethod
    def catalog_format_options() -> list[dict[str, str]]:
        return list(NOTEBOOKLM_FORMAT_OPTIONS)

    @staticmethod
    def catalog_style_options() -> list[dict[str, str]]:
        return list(NOTEBOOKLM_STYLE_OPTIONS)

    @staticmethod
    def catalog_model_options(catalog: dict[str, Any] | None) -> list[dict[str, str]]:
        catalog = catalog or {}
        external: list[dict[str, str]] = []
        selectable_refs: set[str] = set()
        seen_refs: set[str] = set()

        for item in catalog.get("models", ()) or ():
            if not isinstance(item, dict):
                continue
            ref = str(item.get("full_id") or "").strip()
            if not ref or ref == LOCAL_MODEL_REF or not item.get("available") or item.get("is_active") is False:
                continue
            if ref in seen_refs:
                continue
            seen_refs.add(ref)
            selectable_refs.add(ref)
            provider = str(item.get("provider_name") or item.get("provider") or ref.split("/", 1)[0]).strip()
            display_name = str(item.get("display_name") or item.get("model_id") or ref.split("/", 1)[-1]).strip()
            capabilities = [str(value).replace("_", " ") for value in item.get("capabilities", ()) or () if value]
            detail = f"{provider} · {ref}"
            if capabilities:
                detail += " · " + ", ".join(capabilities[:2])
            external.append({"ref": ref, "label": f"{provider} · {display_name}", "detail": detail})

        combos: list[dict[str, str]] = []
        for combo in catalog.get("combos", ()) or ():
            if not isinstance(combo, dict):
                continue
            members = [str(ref).strip() for ref in combo.get("models", ()) or () if str(ref).strip()]
            name = str(combo.get("name") or "").strip()
            ref = str(combo.get("ref") or (f"combo:{name}" if name else "")).strip()
            if not ref or not members or not all(member in selectable_refs for member in members):
                continue
            strategy = str(combo.get("strategy") or "fallback").replace("_", " ")
            combos.append({
                "ref": ref,
                "label": f"Model combo · {name or ref.removeprefix('combo:')}",
                "detail": f"{len(members)} models · {strategy}",
            })

        options = [*combos, *external]
        used_labels: set[str] = set()
        for option in options:
            label = option["label"]
            if label in used_labels:
                label = f"{label} · {option['ref']}"
            used_labels.add(label)
            option["label"] = label
        return options

    @staticmethod
    def catalog_theme_options(catalog: dict[str, Any] | None) -> list[dict[str, str]]:
        catalog = catalog or {}
        options: list[dict[str, str]] = []
        seen: set[str] = set()
        for value in ["auto", *(catalog.get("themes", ()) or ())]:
            theme = str(value or "").strip().lower()
            if not theme or theme in seen:
                continue
            seen.add(theme)
            label = "Auto" if theme == "auto" else theme.replace("-", " ").replace("_", " ").title()
            detail = "Adapts the visual language to the source" if theme == "auto" else f"{label} visual language"
            options.append({"ref": theme, "label": label, "detail": detail})
        return options

    def hide(self) -> None:
        """Withdraw composer window without destroying widget state."""
        self._stop_grid()
        if self.win and self.win.winfo_exists():
            try:
                self.win.withdraw()
            except Exception:
                pass

    def show_composer(self, selected_text: str = "", mode: str = "summary", anchor_bar: Any = None) -> None:
        clean = (selected_text or "").strip()
        self._mode = mode if mode in {"summary", "full"} else "summary"
        self._source_text = clean
        self._source_name = "Selected text" if clean else ""
        self._initial_text = clean
        if anchor_bar is not None:
            self._anchor_win = anchor_bar
        if self.root is None:
            self.root = getattr(tk, "_default_root", None)

        def _show() -> None:
            if not self.root:
                self.root = getattr(tk, "_default_root", None)
            if not self.root:
                return
            try:
                curr_theme = str(storage.get_setting("on_screen_ui_theme", "light") or "light").strip().lower()
            except Exception:
                curr_theme = "light"
            if not self.win or not self.win.winfo_exists() or getattr(self, "_built_theme", None) != curr_theme:
                self._build()
            if not self.win:
                return

            source_txt = getattr(self, "_source_text", "") or ""
            if "source" in self._controls:
                self._controls["source"].delete("1.0", "end")
                if source_txt:
                    self._controls["source"].insert("1.0", source_txt)
            if "title" in self._controls:
                current_title = self._controls["title"].get().strip()
                if not current_title and source_txt:
                    first_line = source_txt.strip().split("\n")[0].strip()[:60]
                    self._controls["title"].set(first_line)
            if "mode" in self._controls:
                self._controls["mode"].set(self._mode)
            if "file_label" in self._controls:
                self._controls["file_label"].set(self._source_name or "No document selected")
            if "status" in self._controls:
                self._controls["status"].set("Selected text is ready." if source_txt else "Paste text or choose a document.")
            self._stop_grid()
            self._check_notebooklm_auth()
            self._refresh_models()
            self._update_document_analysis()

            # Center and calculate geometry while hidden so there is zero screen jump or flicker
            self._center()

            # Smoothly reveal window directly in centered position
            self.win.deiconify()
            self.win.state("normal")
            self.win.lift()
            self.win.attributes("-topmost", True)
            self.win.focus_force()

        self._run_on_ui(_show)

    def _build(self) -> None:
        if not self.root:
            self.root = getattr(tk, "_default_root", None)
        if not self.root:
            return
        if self.win and self.win.winfo_exists():
            try:
                self.win.destroy()
            except Exception:
                pass
        self.win = None
        self._controls.clear()
        try:
            self._built_theme = str(storage.get_setting("on_screen_ui_theme", "light") or "light").strip().lower()
        except Exception:
            self._built_theme = "light"
        self.colors = get_composer_colors()
        colors = self.colors
        win = tk.Toplevel(self.root)
        self.win = win
        win.withdraw()
        win.title("Video Flow — Create video")
        win.geometry("560x650")
        win.minsize(500, 560)
        win.resizable(True, True)
        win.attributes("-topmost", True)
        win.configure(bg=colors["background"])
        win.protocol("WM_DELETE_WINDOW", self.hide)
        win.bind("<Escape>", lambda _e: self.hide(), add="+")
        try:
            from voice_flow.installer import get_icon_path
            ico = get_icon_path()
            if ico.exists() and hasattr(win, "iconbitmap"):
                win.iconbitmap(str(ico))
            p = ico.parent / "icon-32.png"
            if p.exists() and hasattr(win, "iconphoto"):
                self._icon_photo = tk.PhotoImage(file=str(p))
                win.iconphoto(False, self._icon_photo)
        except Exception:
            pass
        self._configure_styles(win)

        viewport = tk.Frame(win, bg=colors["background"])
        viewport.pack(fill="both", expand=True)

        scroll_canvas = tk.Canvas(
            viewport,
            bg=colors["background"],
            highlightthickness=0,
            bd=0,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(
            viewport,
            orient="vertical",
            command=scroll_canvas.yview,
            style="VideoFlow.Vertical.TScrollbar",
        )
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scroll_canvas.pack(side="left", fill="both", expand=True)

        shell = tk.Frame(
            scroll_canvas,
            bg=colors["surface"],
            highlightthickness=1,
            highlightbackground=colors["border"],
            padx=20,
            pady=20,
        )
        shell_window = scroll_canvas.create_window((280, 12), window=shell, anchor="n")

        def sync_scroll_region(_event: object | None = None) -> None:
            if not win or not win.winfo_exists():
                return
            win.update_idletasks()
            c_w = scroll_canvas.winfo_width()
            c_h = scroll_canvas.winfo_height()
            s_h = shell.winfo_reqheight() + 24

            # Scroll region is strictly locked horizontally to canvas width: [0, 0, max(1, c_w), max(c_h, s_h)]
            scroll_canvas.configure(scrollregion=(0, 0, max(1, c_w), max(c_h, s_h)))
            scroll_canvas.xview_moveto(0.0)

            # Auto-hide scrollbar if content fits cleanly vertically
            if s_h > c_h and c_h > 100:
                if not scrollbar.winfo_ismapped():
                    scrollbar.pack(side="right", fill="y", padx=(0, 2), pady=8)
            else:
                if scrollbar.winfo_ismapped():
                    scrollbar.pack_forget()

        self._sync_scroll_region = sync_scroll_region

        def sync_shell_width(event: tk.Event) -> None:
            canvas_width = event.width
            card_margin = 16
            card_width = max(440, canvas_width - (card_margin * 2))
            center_x = canvas_width // 2
            scroll_canvas.coords(shell_window, center_x, 12)
            scroll_canvas.itemconfigure(shell_window, width=card_width)
            scroll_canvas.xview_moveto(0.0)
            sync_scroll_region()

        shell.bind("<Configure>", sync_scroll_region)
        scroll_canvas.bind("<Configure>", sync_shell_width)

        def keep_x_zero(_event: object | None = None) -> None:
            scroll_canvas.xview_moveto(0.0)

        win.bind("<FocusIn>", keep_x_zero, add="+")

        def scroll_wheel(event: tk.Event) -> str:
            try:
                if event.widget.winfo_toplevel() != win:
                    return "break"
                delta = int(getattr(event, "delta", 0))
                steps = -int(delta / 120) if delta else 0
                if not steps:
                    steps = -1 if delta > 0 else 1
                scroll_canvas.yview_scroll(steps, "units")
            except (AttributeError, tk.TclError, ValueError):
                pass
            return "break"

        def scroll_button(event: tk.Event) -> str:
            try:
                if event.widget.winfo_toplevel() == win:
                    scroll_canvas.yview_scroll(-1 if event.num == 4 else 1, "units")
            except (AttributeError, tk.TclError):
                pass
            return "break"

        win.bind_all("<MouseWheel>", scroll_wheel, add="+")
        win.bind_all("<Button-4>", scroll_button, add="+")
        win.bind_all("<Button-5>", scroll_button, add="+")

        # ---------------------------------------------------------------------
        # 1. HEADER SECTION
        # ---------------------------------------------------------------------
        header_frame = tk.Frame(shell, bg=colors["surface"])
        header_frame.pack(fill="x", pady=(0, 10))

        badge_row = tk.Frame(header_frame, bg=colors["surface"])
        badge_row.pack(fill="x", pady=(0, 2))
        tk.Frame(badge_row, bg=colors["orange"], width=6, height=6).pack(side="left", padx=(0, 6))
        tk.Label(
            badge_row,
            text="VIDEO FLOW",
            bg=colors["surface"],
            fg=colors["orange"],
            font=("Segoe UI", 8, "bold"),
        ).pack(side="left")

        tk.Label(
            header_frame,
            text="Create AI Video",
            bg=colors["surface"],
            fg=colors["text"],
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", pady=(0, 1))

        tk.Label(
            header_frame,
            text="Turn text, articles, or attached documents into clear visual explanations.",
            bg=colors["surface"],
            fg=colors["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        # ---------------------------------------------------------------------
        # 2. ENGINE SELECTOR (NotebookLM vs Native)
        # ---------------------------------------------------------------------
        provider_var = tk.StringVar(value=self._provider)
        provider_bar = tk.Frame(shell, bg=colors["surface_soft"], padx=3, pady=3)
        provider_bar.pack(fill="x", pady=(0, 10))

        provider_buttons: dict[str, tk.Radiobutton] = {}
        provider_hover: dict[str, bool] = {}
        for value, icon, label in (
            ("notebooklm", "✨", "NotebookLM Cloud AI"),
            ("native", "⚙", "Native Engine (Offline)"),
        ):
            provider_hover[value] = False
            btn = tk.Radiobutton(
                provider_bar,
                text=f"{icon} {label}",
                value=value,
                variable=provider_var,
                indicatoron=False,
                anchor="center",
                bg=colors["surface_soft"],
                fg=colors["text"],
                selectcolor=colors["surface"],
                activebackground=colors["surface"],
                activeforeground=colors["orange_dark"],
                highlightthickness=0,
                bd=0,
                padx=10,
                pady=6,
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
            )
            btn.pack(side="left", fill="x", expand=True, padx=2)
            provider_buttons[value] = btn

        def refresh_provider_cards(*_args: object) -> None:
            selected = provider_var.get()
            self._provider = selected
            for val, b in provider_buttons.items():
                is_selected = val == selected
                b.configure(
                    bg=colors["surface"] if is_selected else colors["surface_soft"],
                    fg=colors["orange_dark"] if is_selected else colors["muted"],
                    activebackground=colors["surface"],
                    activeforeground=colors["orange_dark"],
                    relief="solid" if is_selected else "flat",
                    bd=1 if is_selected else 0,
                    highlightthickness=0,
                )
            self._on_provider_changed()

        def hover_provider_card(val: str, entered: bool):
            def _hover(_event: object) -> None:
                provider_hover[val] = entered
                refresh_provider_cards()
            return _hover

        for val, btn in provider_buttons.items():
            btn.bind("<Enter>", hover_provider_card(val, True))
            btn.bind("<Leave>", hover_provider_card(val, False))
        provider_var.trace_add("write", refresh_provider_cards)

        # ---------------------------------------------------------------------
        # 2B. NOTEBOOKLM AUTH STATUS BANNER PILL
        # ---------------------------------------------------------------------
        try:
            self._auth_is_authenticated, self._auth_email = self._check_notebooklm_auth_local()
        except Exception:
            pass

        auth_banner_frame = tk.Frame(shell, bg=colors["surface"])
        self._auth_banner_frame = auth_banner_frame
        auth_banner_frame.pack(fill="x", pady=(0, 8))

        auth_pill_frame = tk.Frame(
            auth_banner_frame,
            bg=colors["green_bg"] if self._auth_is_authenticated else colors["amber_bg"],
            highlightthickness=1,
            highlightbackground=colors["green_border"] if self._auth_is_authenticated else colors["amber_border"],
            padx=10,
            pady=4,
        )
        self._auth_pill_frame = auth_pill_frame
        auth_pill_frame.pack(fill="x")

        status_text = (
            f"✨ Google NotebookLM Connected ({self._auth_email})"
            if (self._auth_is_authenticated and self._auth_email)
            else (
                "✨ Google NotebookLM Connected"
                if self._auth_is_authenticated
                else "⚠️ Google Account not connected"
            )
        )

        auth_status_label = tk.Label(
            auth_pill_frame,
            text=status_text,
            bg=colors["green_bg"] if self._auth_is_authenticated else colors["amber_bg"],
            fg=colors["green_text"] if self._auth_is_authenticated else colors["amber_text"],
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        )
        self._auth_status_label = auth_status_label
        auth_status_label.pack(side="left", fill="x", expand=True)

        auth_signin_btn = tk.Button(
            auth_pill_frame,
            text="Sign in with Google",
            command=self._open_notebooklm_signin,
            bg=colors["orange"],
            fg="#ffffff",
            activebackground=colors["orange_dark"],
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=2,
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
        )
        self._auth_signin_btn = auth_signin_btn
        auth_signin_btn.bind("<Enter>", lambda _e: auth_signin_btn.configure(bg=colors["orange_dark"]))
        auth_signin_btn.bind("<Leave>", lambda _e: auth_signin_btn.configure(bg=colors["orange"]))

        if not self._auth_is_authenticated:
            auth_status_label.pack_configure(expand=False)
            auth_signin_btn.pack(side="right", padx=(4, 0))

        # ---------------------------------------------------------------------
        # 3. SOURCE CONTENT SECTION (Text + File + Live Analysis)
        # ---------------------------------------------------------------------
        source_section = tk.Frame(shell, bg=colors["surface"])
        self._source_section = source_section
        source_section.pack(fill="x", pady=(0, 10))

        source_label_row = tk.Frame(source_section, bg=colors["surface"])
        source_label_row.pack(fill="x", pady=(0, 3))
        tk.Label(
            source_label_row,
            text="Source Content",
            bg=colors["surface"],
            fg=colors["text"],
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")

        file_label = tk.StringVar(value="No document selected")

        source = tk.Text(
            source_section,
            height=4,
            wrap="word",
            bg=colors["surface"],
            fg=colors["text"],
            insertbackground=colors["text"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=colors["border"],
            highlightcolor=colors["border_focus"],
            padx=10,
            pady=8,
            font=("Segoe UI", 9),
            undo=True,
        )
        source.pack(fill="x", pady=(0, 6))

        # Document Action & Live Analysis Row
        doc_analysis_frame = tk.Frame(source_section, bg=colors["surface"])
        doc_analysis_frame.pack(fill="x", pady=(0, 2))

        choose_btn = tk.Button(
            doc_analysis_frame,
            text="📎 Choose Document",
            command=self._choose_file,
            bg=colors["surface_soft"],
            fg=colors["text"],
            activebackground=colors["orange_light"],
            activeforeground=colors["orange_dark"],
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=colors["border"],
            padx=10,
            pady=5,
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
        )
        choose_btn.pack(side="left", padx=(0, 8))
        choose_btn.bind("<Enter>", lambda _e: choose_btn.configure(highlightbackground=colors["orange"]))
        choose_btn.bind("<Leave>", lambda _e: choose_btn.configure(highlightbackground=colors["border"]))

        # Live Document Analysis Banner Pill — removed from the UI.
        # The analysis logic still runs; stats stay available for auto-scaling.
        analysis_banner_var = tk.StringVar(value="")

        source.bind("<KeyRelease>", lambda _e: self._on_source_text_changed())
        source.bind("<FocusIn>", lambda _e: self._on_source_text_changed())
        source.bind("<<Paste>>", lambda _e: self.win.after(20, self._on_source_text_changed) if self.win else None)
        source.bind("<ButtonRelease-1>", lambda _e: self._on_source_text_changed())

        # ---------------------------------------------------------------------
        # 4. CONFIGURATION CARDS (NotebookLM vs Native)
        # ---------------------------------------------------------------------
        # 4A. NOTEBOOKLM CONFIGURATION
        notebooklm_frame = tk.Frame(shell, bg=colors["surface"])
        self._notebooklm_frame = notebooklm_frame

        format_ref_var = tk.StringVar(value="auto")
        format_display_var = tk.StringVar(value="Auto-Adaptive (Recommended)")
        format_detail_var = tk.StringVar(value="Scales video runtime to document size (Max 5m ceiling)")

        style_ref_var = tk.StringVar(value="auto")
        style_display_var = tk.StringVar(value="Auto")
        style_detail_var = tk.StringVar(value="Adapts style automatically to the topic")
        custom_style_var = tk.StringVar(value="")

        nlm_grid = tk.Frame(notebooklm_frame, bg=colors["surface"])
        nlm_grid.pack(fill="x", pady=(0, 6))
        nlm_grid.grid_columnconfigure(0, weight=1)
        nlm_grid.grid_columnconfigure(1, weight=1)

        # Format Dropdown
        format_cell = tk.Frame(nlm_grid, bg=colors["surface"])
        format_cell.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._label(format_cell, "Video Format")
        format_box = ttk.Combobox(format_cell, textvariable=format_display_var, state="readonly", style="VideoFlow.TCombobox", width=22)
        format_box.pack(fill="x", ipady=2, pady=(2, 0))

        # Style Dropdown
        style_cell = tk.Frame(nlm_grid, bg=colors["surface"])
        style_cell.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._label(style_cell, "Visual Style")
        style_box = ttk.Combobox(style_cell, textvariable=style_display_var, state="readonly", style="VideoFlow.TCombobox", width=16)
        style_box.pack(fill="x", ipady=2, pady=(2, 0))

        # Custom Style Entry (Hidden by default)
        custom_style_frame = tk.Frame(notebooklm_frame, bg=colors["surface"])
        self._custom_style_frame = custom_style_frame
        self._label(custom_style_frame, "Custom style instructions")
        custom_style_entry = tk.Entry(
            custom_style_frame,
            textvariable=custom_style_var,
            bg=colors["surface"],
            fg=colors["text"],
            insertbackground=colors["text"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=colors["border"],
            highlightcolor=colors["border_focus"],
            font=("Segoe UI", 9),
        )
        custom_style_entry.pack(fill="x", ipady=4, pady=(2, 4))

        # Focus / Visual Direction Entry
        nlm_focus_frame = tk.Frame(notebooklm_frame, bg=colors["surface"])
        nlm_focus_frame.pack(fill="x", pady=(2, 6))
        self._label(nlm_focus_frame, "Focus / Visual Direction (optional)")
        nlm_focus = tk.Text(
            nlm_focus_frame,
            height=2,
            wrap="word",
            bg=colors["surface"],
            fg=colors["text"],
            insertbackground=colors["text"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=colors["border"],
            highlightcolor=colors["border_focus"],
            padx=10,
            pady=6,
            font=("Segoe UI", 9),
            undo=True,
        )
        nlm_focus.pack(fill="x", pady=(2, 0))

        # 4B. NATIVE ENGINE CONFIGURATION (Legacy Visual V2.1)
        native_frame = tk.Frame(shell, bg=colors["surface"])
        self._native_frame = native_frame

        mode_var = tk.StringVar(value=self._mode)
        mode_row = tk.Frame(native_frame, bg=colors["surface"])
        mode_row.pack(fill="x", pady=(0, 6))
        mode_buttons: dict[str, tk.Radiobutton] = {}
        for value, icon, label in (
            ("summary", "✦", "Summary Video"),
            ("full", "≡", "Full Explanation"),
        ):
            b = tk.Radiobutton(
                mode_row,
                text=f"{icon}  {label}",
                value=value,
                variable=mode_var,
                indicatoron=False,
                anchor="center",
                bg=colors["surface_soft"],
                fg=colors["text"],
                selectcolor=colors["orange"],
                activebackground=colors["surface_faint"],
                activeforeground=colors["orange_dark"],
                highlightthickness=1,
                highlightbackground=colors["border"],
                bd=0,
                padx=8,
                pady=4,
                font=("Segoe UI", 8, "bold"),
                cursor="hand2",
            )
            b.pack(side="left", fill="x", expand=True, padx=(0, 4 if value == "summary" else 0))
            mode_buttons[value] = b

        def refresh_mode_cards(*_args: object) -> None:
            selected = mode_var.get()
            for val, b in mode_buttons.items():
                is_selected = val == selected
                b.configure(
                    bg=colors["orange"] if is_selected else colors["surface_soft"],
                    fg="#ffffff" if is_selected else colors["text"],
                    activebackground=colors["orange_dark"] if is_selected else colors["surface_faint"],
                    activeforeground="#ffffff" if is_selected else colors["orange_dark"],
                    highlightbackground=colors["orange"] if is_selected else colors["border"],
                )

        mode_var.trace_add("write", refresh_mode_cards)
        refresh_mode_cards()

        model_ref_var = tk.StringVar(value="")
        model_display_var = tk.StringVar(value="Connect an AI model")
        model_detail_var = tk.StringVar(value="Original Scene Programs require a connected model.")
        theme_ref_var = tk.StringVar(value="auto")
        theme_display_var = tk.StringVar(value="Auto")
        theme_detail_var = tk.StringVar(value="Adapts the visual language to the source")

        native_grid = tk.Frame(native_frame, bg=colors["surface"])
        native_grid.pack(fill="x", pady=(0, 4))
        native_grid.grid_columnconfigure(0, weight=1)
        native_grid.grid_columnconfigure(1, weight=1)

        model_cell = tk.Frame(native_grid, bg=colors["surface"])
        model_cell.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._label(model_cell, "Model provider · model")
        model = ttk.Combobox(model_cell, textvariable=model_display_var, state="readonly", style="VideoFlow.TCombobox", width=20)
        model.pack(fill="x", ipady=2, pady=(2, 0))

        theme_cell = tk.Frame(native_grid, bg=colors["surface"])
        theme_cell.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._label(theme_cell, "Visual theme")
        theme = ttk.Combobox(theme_cell, textvariable=theme_display_var, state="readonly", style="VideoFlow.TCombobox", width=14)
        theme.pack(fill="x", ipady=2, pady=(2, 0))

        native_direction_frame = tk.Frame(native_frame, bg=colors["surface"])
        native_direction_frame.pack(fill="x", pady=(4, 4))
        self._label(native_direction_frame, "Your visual direction (optional)")
        visual_direction = tk.Text(
            native_direction_frame,
            height=2,
            wrap="word",
            bg=colors["surface"],
            fg=colors["text"],
            insertbackground=colors["text"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=colors["border"],
            highlightcolor=colors["border_focus"],
            padx=10,
            pady=6,
            font=("Segoe UI", 9),
            undo=True,
        )
        visual_direction.pack(fill="x", pady=(2, 0))

        # Pack default NotebookLM frame
        notebooklm_frame.pack(fill="x", pady=(0, 6))

        # ---------------------------------------------------------------------
        # 5. VIDEO TITLE (OPTIONAL)
        # ---------------------------------------------------------------------
        title_var = tk.StringVar()
        title_frame = tk.Frame(shell, bg=colors["surface"])
        self._title_frame = title_frame
        title_frame.pack(fill="x", pady=(0, 12))
        self._label(title_frame, "Video Title (optional)")
        title = tk.Entry(
            title_frame,
            textvariable=title_var,
            bg=colors["surface"],
            fg=colors["text"],
            insertbackground=colors["text"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=colors["border"],
            highlightcolor=colors["border_focus"],
            font=("Segoe UI", 9),
        )
        title.pack(fill="x", ipady=4, pady=(2, 0))

        # ---------------------------------------------------------------------
        # 6. BOTTOM ACTION & STATUS FOOTER
        # ---------------------------------------------------------------------
        footer_frame = tk.Frame(shell, bg=colors["surface"])
        footer_frame.pack(fill="x", pady=(4, 0))

        status_left = tk.Frame(footer_frame, bg=colors["surface"])
        status_left.pack(side="left", fill="x", expand=True, padx=(0, 10))

        dots_row = tk.Frame(status_left, bg=colors["surface"])
        dots_row.pack(anchor="w", pady=(0, 2))
        self._grid_dots = []
        for index in range(6):
            dot = tk.Frame(dots_row, bg=colors["surface_soft"], width=6, height=6)
            dot.grid(row=0, column=index, padx=1)
            self._grid_dots.append(dot)
        self._paint_grid_idle()

        status_var = tk.StringVar(value="Paste text or choose a document.")
        status_label = tk.Label(
            status_left,
            textvariable=status_var,
            bg=colors["surface"],
            fg=colors["muted"],
            font=("Segoe UI", 8),
            anchor="w",
        )
        status_label.pack(anchor="w")

        generate = tk.Button(
            footer_frame,
            text="Generate Video ✨",
            command=self._generate,
            bg=colors["orange"],
            fg="#ffffff",
            activebackground=colors["orange_dark"],
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=18,
            pady=8,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        generate.pack(side="right")
        generate.bind("<Enter>", lambda _e: generate.configure(bg=colors["orange_dark"]) if str(generate.cget("state")) != "disabled" else None)
        generate.bind("<Leave>", lambda _e: generate.configure(bg=colors["orange"]))

        self._nlm_format = format_ref_var
        self._nlm_style = style_ref_var
        self._nlm_style_prompt = custom_style_var
        self._nlm_focus = nlm_focus

        self._controls = {
            "provider": provider_var,
            "mode": mode_var,
            "title": title_var,
            "source": source,
            "file_label": file_label,
            "analysis_banner": analysis_banner_var,
            "format": format_ref_var,
            "format_display": format_display_var,
            "format_detail": format_detail_var,
            "format_box": format_box,
            "style": style_ref_var,
            "style_display": style_display_var,
            "style_detail": style_detail_var,
            "style_box": style_box,
            "style_prompt": custom_style_var,
            "style_prompt_entry": custom_style_entry,
            "nlm_focus": nlm_focus,
            "visual_direction": visual_direction,
            "model": model_ref_var,
            "model_display": model_display_var,
            "model_detail": model_detail_var,
            "model_box": model,
            "theme": theme_ref_var,
            "theme_display": theme_display_var,
            "theme_detail": theme_detail_var,
            "theme_box": theme,
            "status": status_var,
            "status_label": status_label,
            "generate": generate,
            "scroll_canvas": scroll_canvas,
            "scrollbar": scrollbar,
            "auth_banner": auth_banner_frame,
            "auth_pill": auth_pill_frame,
            "auth_status_label": auth_status_label,
            "auth_signin_btn": auth_signin_btn,
        }

        format_options = self.catalog_format_options()
        self._format_options = {option["label"]: option for option in format_options}
        format_box["values"] = tuple(self._format_options)
        default_format = next((opt for opt in format_options if opt["ref"] == "auto"), format_options[0])
        self._set_format_option(default_format)

        style_options = self.catalog_style_options()
        self._style_options = {option["label"]: option for option in style_options}
        style_box["values"] = tuple(self._style_options)
        default_style = next((opt for opt in style_options if opt["ref"] == "auto"), style_options[0])
        self._set_style_option(default_style)

        format_box.bind("<<ComboboxSelected>>", self._on_format_selected)
        style_box.bind("<<ComboboxSelected>>", self._on_style_selected)
        model.bind("<<ComboboxSelected>>", self._on_model_selected)
        theme.bind("<<ComboboxSelected>>", self._on_theme_selected)

        # Selection must only happen via the opened dropdown — never by
        # accidentally scrolling while the cursor rests on a combobox.
        for _cb in (format_box, style_box, model, theme):
            try:
                _cb.unbind_class("TCombobox", "<MouseWheel>")
            except (AttributeError, tk.TclError):
                pass

        refresh_provider_cards()

    def _configure_styles(self, master: tk.Misc) -> None:
        colors = getattr(self, "colors", None) or get_composer_colors()
        style = ttk.Style(master)
        try:
            if "clam" in style.theme_names():
                style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "VideoFlow.TCombobox",
            foreground=colors["text"],
            fieldbackground=colors["surface_soft"],
            background=colors["surface_soft"],
            arrowcolor=colors["orange_dark"],
            bordercolor=colors["border"],
            lightcolor=colors["border"],
            darkcolor=colors["border"],
            padding=(8, 4),
        )
        style.map(
            "VideoFlow.TCombobox",
            fieldbackground=[("readonly", colors["surface_soft"])],
            foreground=[("readonly", colors["text"])],
            selectbackground=[("readonly", colors["surface"])],
            selectforeground=[("readonly", colors["text"])],
            bordercolor=[("focus", colors["border_focus"]), ("active", colors["border_focus"])],
        )

        try:
            master.option_add("*TCombobox*Listbox.background", colors["surface_soft"])
            master.option_add("*TCombobox*Listbox.foreground", colors["text"])
            master.option_add("*TCombobox*Listbox.selectBackground", colors["surface"])
            master.option_add("*TCombobox*Listbox.selectForeground", colors["text"])
        except Exception:
            pass

        style.configure(
            "VideoFlow.Vertical.TScrollbar",
            gripcount=0,
            background=colors["border"],
            darkcolor=colors["border"],
            lightcolor=colors["border"],
            troughcolor=colors["background"],
            bordercolor=colors["background"],
            arrowcolor=colors["orange_dark"],
            arrowsize=0,
            width=8,
        )
        style.map(
            "VideoFlow.Vertical.TScrollbar",
            background=[("active", colors["orange"]), ("pressed", colors["orange_dark"])],
            arrowcolor=[("active", colors["orange_dark"]), ("pressed", colors["orange_dark"])],
        )

    def _label(self, parent: tk.Misc, text: str) -> None:
        colors = getattr(self, "colors", None) or get_composer_colors()
        tk.Label(
            parent,
            text=text,
            bg=colors["surface"],
            fg=colors["muted"],
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", pady=(0, 2))

    def _paint_grid_idle(self) -> None:
        colors = getattr(self, "colors", None) or get_composer_colors()
        for index, dot in enumerate(self._grid_dots):
            dot.configure(bg=colors["orange"] if index == GRID_IDLE_DOT else colors["surface_soft"])

    def _start_grid(self) -> None:
        self._stop_grid()
        self._grid_animating = True
        self._set_status_accent(True)
        self._schedule_grid_tick()

    def _schedule_grid_tick(self) -> None:
        if not self._grid_animating:
            return
        win = self.win
        if not win or not win.winfo_exists():
            self._grid_animating = False
            self._grid_after_id = None
            return
        try:
            is_dark = getattr(self, "_built_theme", "light") == "dark"
            tones = GRID_TONES_DARK if is_dark else GRID_TONES_LIGHT
            for index, dot in enumerate(self._grid_dots):
                dot.configure(bg=tones[(self._grid_step - index) % len(tones)])
            self._grid_step += 1
        except tk.TclError:
            self._grid_animating = False
            self._grid_after_id = None
            return
        self._grid_after_id = win.after(GRID_TICK_MS, self._schedule_grid_tick)

    def _stop_grid(self) -> None:
        self._grid_animating = False
        after_id = self._grid_after_id
        if after_id is not None and self.win is not None and self.win.winfo_exists():
            try:
                self.win.after_cancel(after_id)
            except (tk.TclError, ValueError):
                pass
        self._grid_after_id = None
        self._paint_grid_idle()
        self._set_status_accent(False)

    def _set_status_accent(self, active: bool) -> None:
        label = self._controls.get("status_label")
        if label is None:
            return
        colors = getattr(self, "colors", None) or get_composer_colors()
        try:
            if label.winfo_exists():
                label.configure(fg=colors["orange_dark"] if active else colors["muted"])
        except tk.TclError:
            pass

    def _on_source_text_changed(self) -> None:
        self._update_document_analysis()

    def _update_document_analysis(self) -> None:
        if "source" not in self._controls or "analysis_banner" not in self._controls:
            return
        try:
            source_text = self._controls["source"].get("1.0", "end-1c").strip()
        except Exception:
            source_text = ""

        format_ref = str(self._controls.get("format", tk.StringVar(value="auto")).get() or "auto").strip().lower()

        focus_text = ""
        if self._nlm_focus is not None:
            focus_text = self._nlm_focus.get("1.0", "end-1c").strip()[:1000]
        elif "nlm_focus" in self._controls:
            focus_text = self._controls["nlm_focus"].get("1.0", "end-1c").strip()[:1000]
        title_text = self._controls["title"].get().strip() if "title" in self._controls else ""

        try:
            if analyze_document_source is not None:
                profile = analyze_document_source(
                    text=source_text,
                    requested_format=format_ref,
                    task=focus_text,
                    title=title_text,
                    focus=focus_text,
                )
                wc = profile.word_count
                pages = profile.estimated_pages
                dur_disp = profile.target_duration_display
                self._latest_profile = profile
            else:
                fb = _local_analyze_fallback(
                    source_text,
                    format_ref,
                    task=focus_text,
                    title=title_text,
                    focus=focus_text,
                )
                wc = fb["word_count"]
                pages = fb["estimated_pages"]
                dur_disp = fb["target_duration_display"]
                self._latest_profile = fb
        except Exception:
            fb = _local_analyze_fallback(
                source_text,
                format_ref,
                task=focus_text,
                title=title_text,
                focus=focus_text,
            )
            wc = fb["word_count"]
            pages = fb["estimated_pages"]
            dur_disp = fb["target_duration_display"]
            self._latest_profile = fb

        clean_fmt = format_ref.title() if format_ref not in {"auto", "auto-adaptive", "default", "recommended", ""} else "Auto-scaled"
        if wc == 0:
            banner = f"📄 0 pages (0 words) ➔ {clean_fmt} video target: ~30s (Max 5m ceiling)"
        else:
            pages_count = max(1, int(round(pages)))
            pages_label = f"{pages_count} {'page' if pages_count == 1 else 'pages'}"
            dur_clean = dur_disp.replace(" (Max ceiling)", "")
            banner = f"📄 {pages_label} (~{wc:,} words) ➔ {clean_fmt} video target: {dur_clean} (Max 5m ceiling)"

        self._controls["analysis_banner"].set(banner)

    def _on_provider_changed(self) -> None:
        if not self._notebooklm_frame or not self._native_frame:
            return
        provider = str(self._provider or "notebooklm").lower()
        if provider == "notebooklm":
            self._native_frame.pack_forget()
            if self._auth_banner_frame and self._source_section and self._source_section.winfo_exists():
                self._auth_banner_frame.pack(fill="x", pady=(0, 8), before=self._source_section)
            elif self._auth_banner_frame:
                self._auth_banner_frame.pack(fill="x", pady=(0, 8))
            if self._title_frame and self._title_frame.winfo_exists():
                self._notebooklm_frame.pack(fill="x", pady=(0, 6), before=self._title_frame)
            else:
                self._notebooklm_frame.pack(fill="x", pady=(0, 6))
            style_ref = self._controls.get("style", tk.StringVar(value="auto")).get()
            if style_ref == "custom" and self._custom_style_frame:
                self._custom_style_frame.pack(fill="x", pady=(0, 4))
            elif self._custom_style_frame:
                self._custom_style_frame.pack_forget()
            if "generate" in self._controls:
                self._controls["generate"].configure(state="normal")
        else:
            if self._auth_banner_frame:
                self._auth_banner_frame.pack_forget()
            self._notebooklm_frame.pack_forget()
            if self._title_frame and self._title_frame.winfo_exists():
                self._native_frame.pack(fill="x", pady=(0, 6), before=self._title_frame)
            else:
                self._native_frame.pack(fill="x", pady=(0, 6))
            if "generate" in self._controls:
                has_models = bool(self._model_options)
                self._controls["generate"].configure(state="normal" if has_models else "disabled")

        self._update_document_analysis()
        if self._sync_scroll_region:
            self._sync_scroll_region()

    def _on_format_selected(self, _event: object | None = None) -> None:
        option = self._format_options.get(self._controls["format_display"].get())
        if option:
            self._set_format_option(option)
        self._update_document_analysis()

    def _on_style_selected(self, _event: object | None = None) -> None:
        option = self._style_options.get(self._controls["style_display"].get())
        if option:
            self._set_style_option(option)
            if option["ref"] == "custom" and self._custom_style_frame:
                self._custom_style_frame.pack(fill="x", pady=(0, 4))
            elif self._custom_style_frame:
                self._custom_style_frame.pack_forget()
            if self._sync_scroll_region:
                self._sync_scroll_region()

    def _set_format_option(self, option: dict[str, str]) -> None:
        if self._nlm_format is not None:
            self._nlm_format.set(option["ref"])
        if "format" in self._controls:
            self._controls["format"].set(option["ref"])
        if "format_display" in self._controls:
            self._controls["format_display"].set(option["label"])
        if "format_detail" in self._controls:
            self._controls["format_detail"].set(option["detail"])

    def _set_style_option(self, option: dict[str, str]) -> None:
        if self._nlm_style is not None:
            self._nlm_style.set(option["ref"])
        if "style" in self._controls:
            self._controls["style"].set(option["ref"])
        if "style_display" in self._controls:
            self._controls["style_display"].set(option["label"])
        if "style_detail" in self._controls:
            self._controls["style_detail"].set(option["detail"])

    def _check_notebooklm_auth(self) -> None:
        """Check NotebookLM authentication status and update the UI auth banner pill."""
        is_auth, email = self._check_notebooklm_auth_local()
        self._update_auth_banner(is_auth, email)

        def _async_check() -> None:
            try:
                import urllib.request
                url = "http://127.0.0.1:8991/api/video-flow/notebooklm/status"
                with urllib.request.urlopen(url, timeout=2.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict):
                    api_auth = bool(data.get("authenticated") or data.get("status") == "ok")
                    api_email = data.get("email")
                    if api_auth and not api_email:
                        api_email = email or self._auth_email
                    self._run_on_ui(lambda: self._update_auth_banner(api_auth, api_email))
            except Exception:
                pass

        threading.Thread(target=_async_check, daemon=True, name="video-flow-auth-check").start()

    def _check_notebooklm_auth_local(self) -> tuple[bool, str | None]:
        """Offline / local check for NotebookLM authentication."""
        stored_email: str | None = None
        stored_auth: bool = False
        try:
            from voice_flow.storage import StorageEngine
            storage = StorageEngine()
            stored_val = storage.get_setting("video_flow_notebooklm_authenticated")
            stored_auth = stored_val is True or stored_val == "true"
            email_val = storage.get_setting("video_flow_notebooklm_email")
            if email_val and str(email_val).strip():
                stored_email = str(email_val).strip()
        except Exception:
            pass

        # Never surface a stale/hardcoded identity: only a real stored or
        # on-disk account email may mark the banner authenticated.

        try:
            from voice_flow.video_flow_engine.notebooklm.config import (
                resolve_notebooklm_profile,
                has_valid_storage_state,
                get_storage_state_path,
                get_storage_backup_path,
            )
            profile = resolve_notebooklm_profile()
            for getter in (get_storage_state_path, get_storage_backup_path):
                storage_path = getter(profile)
                if storage_path.is_file():
                    try:
                        state_data = json.loads(storage_path.read_text(encoding="utf-8"))
                        if isinstance(state_data, dict):
                            cookies = state_data.get("cookies", [])
                            nlm_info = state_data.get("notebooklm", {})
                            account_info = nlm_info.get("account", {}) if isinstance(nlm_info, dict) else state_data.get("account", {})
                            email = account_info.get("email") if isinstance(account_info, dict) else None
                            if not email and stored_email:
                                email = stored_email
                            if has_valid_storage_state(profile) or email or (isinstance(cookies, list) and len(cookies) > 0):
                                resolved = email or stored_email
                                return True, resolved
                    except Exception:
                        pass
            if has_valid_storage_state(profile):
                return True, stored_email
        except Exception:
            pass

        if stored_auth:
            return True, stored_email

        return False, None

    def _update_auth_banner(self, authenticated: bool, email: str | None = None) -> None:
        """Update the auth status banner pill styling and visibility."""
        self._auth_is_authenticated = bool(authenticated)
        if email:
            self._auth_email = email
        elif not authenticated:
            self._auth_email = None

        if not self.win or not self.win.winfo_exists() or not self._auth_pill_frame:
            return
        colors = getattr(self, "colors", None) or get_composer_colors()
        if authenticated:
            effective_email = email or self._auth_email
            pill_bg = colors.get("green_bg", "#ecfdf5")
            pill_border = colors.get("green_border", "#a7f3d0")
            text_fg = colors.get("green_text", "#047857")
            msg = f"✨ Google NotebookLM Connected ({effective_email})" if effective_email else "✨ Google NotebookLM Connected"
            try:
                self._auth_pill_frame.configure(bg=pill_bg, highlightbackground=pill_border, highlightcolor=pill_border)
                if self._auth_status_label and self._auth_status_label.winfo_exists():
                    self._auth_status_label.configure(text=msg, bg=pill_bg, fg=text_fg)
                    self._auth_status_label.pack(side="left", fill="x", expand=True)
                if self._auth_signin_btn and self._auth_signin_btn.winfo_exists():
                    self._auth_signin_btn.pack_forget()
            except tk.TclError:
                pass
        else:
            pill_bg = colors.get("amber_bg", "#fffbeb")
            pill_border = colors.get("amber_border", "#fde68a")
            text_fg = colors.get("amber_text", "#b45309")
            msg = "⚠️ Google Account not connected"
            try:
                self._auth_pill_frame.configure(bg=pill_bg, highlightbackground=pill_border, highlightcolor=pill_border)
                if self._auth_status_label and self._auth_status_label.winfo_exists():
                    self._auth_status_label.configure(text=msg, bg=pill_bg, fg=text_fg)
                    self._auth_status_label.pack(side="left", fill="x", expand=False)
                if self._auth_signin_btn and self._auth_signin_btn.winfo_exists():
                    self._auth_signin_btn.pack(side="right", padx=(4, 0))
            except tk.TclError:
                pass

        if self._sync_scroll_region:
            self._sync_scroll_region()

    def _open_notebooklm_signin(self) -> None:
        """1-click sign in helper that opens Web GUI video-flow tab and triggers login flow."""
        import webbrowser
        signin_url = "http://127.0.0.1:8991/index.html?tab=video-flow"
        try:
            webbrowser.open(signin_url)
        except Exception:
            pass

        if "status" in self._controls:
            self._controls["status"].set("Opening Google sign-in in browser…")

        def _trigger_auth_start() -> None:
            try:
                import urllib.request
                req = urllib.request.Request(
                    "http://127.0.0.1:8991/api/video-flow/notebooklm/auth/start",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    pass
            except Exception:
                pass

        threading.Thread(target=_trigger_auth_start, daemon=True, name="video-flow-auth-start").start()

        if self.win and self.win.winfo_exists():
            self.win.after(4000, self._check_notebooklm_auth)

    def _refresh_models(self) -> None:
        """Fetch model/theme catalog asynchronously without blocking the Tkinter UI thread."""
        # Fast local fallback: apply cached catalog immediately if available, or initialize defaults
        if getattr(self, "_cached_catalog", None):
            self._apply_catalog(self._cached_catalog)
        elif not self._model_options:
            self._apply_catalog({})

        self._catalog_request_id = getattr(self, "_catalog_request_id", 0) + 1
        req_id = self._catalog_request_id

        def _fetch_catalog() -> None:
            catalog: dict[str, Any] = {}
            try:
                import urllib.request
                with urllib.request.urlopen("http://127.0.0.1:8991/api/video-flow/catalog", timeout=2.0) as response:
                    loaded = json.loads(response.read().decode("utf-8"))
                if isinstance(loaded, dict):
                    catalog = loaded
            except Exception:
                catalog = {}

            if catalog and getattr(self, "_catalog_request_id", 0) == req_id:
                self._cached_catalog = catalog
                self._run_on_ui(lambda: self._apply_catalog(catalog))

        threading.Thread(target=_fetch_catalog, daemon=True, name="video-flow-catalog-refresh").start()

    def _apply_catalog(self, catalog: dict[str, Any]) -> None:
        if self.win is not None and not self.win.winfo_exists():
            return
        model_options = self.catalog_model_options(catalog)
        self._model_options = {option["label"]: option for option in model_options}
        if "model_box" in self._controls:
            self._controls["model_box"]["values"] = tuple(self._model_options)

        if not model_options:
            if "model" in self._controls:
                self._controls["model"].set("")
                self._controls["model_display"].set("Connect an AI model")
                self._controls["model_detail"].set("Original Scene Programs require a connected model.")
        else:
            requested_model = str(
                catalog.get("active_model") or self._controls["model"].get() or ""
            )
            model = next(
                (option for option in model_options if option["ref"] == requested_model),
                None,
            )
            if model is None:
                model = model_options[0]
            self._set_model_option(model)

        theme_options = self.catalog_theme_options(catalog)
        self._theme_options = {option["label"]: option for option in theme_options}
        if "theme_box" in self._controls:
            self._controls["theme_box"]["values"] = tuple(self._theme_options)
        requested_theme = str(self._controls.get("theme", tk.StringVar(value="auto")).get() or "auto").lower()
        theme = next((option for option in theme_options if option["ref"] == requested_theme), theme_options[0])
        self._set_theme_option(theme)

        current_provider = str(self._controls.get("provider", tk.StringVar(value="notebooklm")).get() or "notebooklm").lower()
        if "generate" in self._controls:
            if current_provider == "notebooklm":
                self._controls["generate"].configure(state="normal")
            else:
                self._controls["generate"].configure(state="normal" if model_options else "disabled")

    def _set_model_option(self, option: dict[str, str]) -> None:
        self._controls["model"].set(option["ref"])
        self._controls["model_display"].set(option["label"])
        self._controls["model_detail"].set(option["detail"])

    def _set_theme_option(self, option: dict[str, str]) -> None:
        self._controls["theme"].set(option["ref"])
        self._controls["theme_display"].set(option["label"])
        self._controls["theme_detail"].set(option["detail"])

    def _on_model_selected(self, _event: object | None = None) -> None:
        option = self._model_options.get(self._controls["model_display"].get())
        if option:
            self._set_model_option(option)

    def _on_theme_selected(self, _event: object | None = None) -> None:
        option = self._theme_options.get(self._controls["theme_display"].get())
        if option:
            self._set_theme_option(option)

    def _choose_file(self) -> None:
        if not self.win:
            return
        patterns = " ".join(f"*{extension}" for extension in sorted(DOCUMENT_EXTENSIONS))
        path = filedialog.askopenfilename(
            parent=self.win,
            title="Choose a document for Video Flow",
            filetypes=(("Supported documents", patterns), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            raw = Path(path).read_bytes()
            if len(raw) > MAX_DOCUMENT_BYTES:
                raise ValueError("Document is larger than 8 MB.")
            text = extract_document_text(Path(path).name, base64.b64encode(raw).decode("ascii"))
            source = self._controls["source"]
            source.delete("1.0", "end")
            source.insert("1.0", text)
            self._source_name = Path(path).name
            self._controls["file_label"].set(self._source_name)
            if not self._controls["title"].get().strip():
                self._controls["title"].set(Path(path).stem)
            self._controls["status"].set(f"{len(text):,} characters ready.")
            self._update_document_analysis()
        except Exception as exc:
            messagebox.showerror("Video Flow", str(exc), parent=self.win)

    def _generate(self) -> None:
        source = self._controls["source"].get("1.0", "end-1c").strip()
        if not source:
            messagebox.showwarning("Video Flow", "Paste text or choose a document first.", parent=self.win)
            return
        if not self.on_generate:
            messagebox.showerror("Video Flow", "The Video Flow runtime is not connected.", parent=self.win)
            return

        provider = str(self._controls.get("provider", tk.StringVar(value="notebooklm")).get() or "notebooklm").strip().lower()

        format_ref = str((self._nlm_format.get() if self._nlm_format is not None else self._controls.get("format", tk.StringVar(value="auto")).get()) or "auto").strip().lower()
        style_ref = str((self._nlm_style.get() if self._nlm_style is not None else self._controls.get("style", tk.StringVar(value="auto")).get()) or "auto").strip().lower()
        style_prompt = ((self._nlm_style_prompt.get() if self._nlm_style_prompt is not None else self._controls.get("style_prompt", tk.StringVar(value="")).get()) or "").strip() if style_ref == "custom" else ""
        if self._nlm_focus is not None:
            focus_text = self._nlm_focus.get("1.0", "end-1c").strip()[:1000]
        elif "nlm_focus" in self._controls:
            focus_text = self._controls["nlm_focus"].get("1.0", "end-1c").strip()[:1000]
        else:
            focus_text = ""

        title_text = self._controls["title"].get().strip() if "title" in self._controls else ""
        try:
            if analyze_document_source is not None:
                profile = analyze_document_source(
                    text=source,
                    requested_format=format_ref,
                    task=focus_text,
                    title=title_text,
                    focus=focus_text,
                )
                profile_dict = profile.to_dict()
                duration_sec = profile.target_duration_seconds
            else:
                profile_dict = _local_analyze_fallback(
                    source,
                    format_ref,
                    task=focus_text,
                    title=title_text,
                    focus=focus_text,
                )
                duration_sec = profile_dict.get("target_duration_seconds", 60)
        except Exception:
            profile_dict = _local_analyze_fallback(
                source,
                format_ref,
                task=focus_text,
                title=title_text,
                focus=focus_text,
            )
            duration_sec = profile_dict.get("target_duration_seconds", 60)

        if provider == "notebooklm":
            payload: dict[str, Any] = {
                "provider": "notebooklm",
                "video_engine": "notebooklm",
                "source_text": source,
                "source_name": self._source_name,
                "title": self._controls["title"].get().strip(),
                "mode": self._controls["mode"].get(),
                "format": format_ref,
                "requested_format": format_ref,
                "style": style_ref,
                "style_prompt": style_prompt,
                "focus": focus_text,
                "visual_direction": focus_text,
                "document_profile": profile_dict,
                "duration_seconds": duration_sec,
                "allow_external_ai": True,
                "allow_local_fallback": True,
            }
        else:
            model_ref = self._controls["model"].get()
            if not model_ref:
                messagebox.showwarning("Video Flow", "Connect and select an AI model first.", parent=self.win)
                return

            payload = {
                "provider": "native",
                "video_engine": "visual-v2.1",
                "source_text": source,
                "source_name": self._source_name,
                "title": self._controls["title"].get().strip(),
                "mode": self._controls["mode"].get(),
                "model_ref": model_ref,
                "format": format_ref,
                "requested_format": format_ref,
                "duration_seconds": duration_sec,
                "target_duration_seconds": duration_sec,
                "document_profile": profile_dict,
                "theme": self._controls["theme"].get() or "auto",
                "visual_direction": self._controls["visual_direction"].get("1.0", "end-1c").strip()[:1000],
                "allow_local_fallback": True,
            }

            local_prefixes = ("local/", "ollama/", "lmstudio/", "llamacpp/")
            if not model_ref.startswith(local_prefixes):
                allowed = messagebox.askyesno(
                    "Allow external AI planning?",
                    "The selected source will be sent to the chosen provider for scene planning. Narration and rendering remain on this PC.",
                    parent=self.win,
                )
                if not allowed:
                    return
                payload["allow_external_ai"] = True
            else:
                payload["allow_external_ai"] = False

        payload["allow_local_fallback"] = True

        self._controls["generate"].configure(state="disabled")
        self._controls["status"].set("Starting Video Flow…")
        self._start_grid()

        def _queue() -> None:
            try:
                result = self.on_generate(payload) or {}
                if not result.get("id"):
                    raise RuntimeError("Video Flow did not return a job.")
                self._run_on_ui(self._queued)
            except Exception as exc:
                self._run_on_ui(lambda: self._generation_error(str(exc)))

        threading.Thread(target=_queue, daemon=True, name="video-flow-screen-queue").start()

    def _queued(self) -> None:
        self._stop_grid()
        if self.win:
            self.win.withdraw()
        self._controls["generate"].configure(state="normal")
        self._controls["status"].set("Queued. Watch the circle beside the Voice Flow bar.")

    def _generation_error(self, message: str) -> None:
        self._stop_grid()
        self._controls["generate"].configure(state="normal")
        self._controls["status"].set(message[:120])
        if self.win:
            messagebox.showerror("Video Flow", message, parent=self.win)

    def open_player(self, video_id: str) -> None:
        safe_id = str(video_id or "").strip()
        if not safe_id or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", safe_id):
            return
        if safe_id.split(".")[0].lower() in {"con", "prn", "aux", "nul"}:
            return
        video_id = safe_id
        python_exe = sys.executable
        if os.name == "nt" and python_exe.lower().endswith("python.exe"):
            pythonw = python_exe[:-10] + "pythonw.exe"
            if os.path.exists(pythonw):
                python_exe = pythonw
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
        src_dir = str(Path(__file__).resolve().parents[1])
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{env.get('PYTHONPATH', '')}"

        try:
            subprocess.Popen(
                [python_exe, "-m", "voice_flow.video_flow_player", str(video_id)],
                creationflags=creation_flags,
                close_fds=True,
                env=env,
            )
        except Exception as exc:
            log.warning("Could not launch video flow player subprocess: %s", exc)
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:8991/video-player.html?id={urllib.parse.quote(str(video_id))}")

    def _center(self) -> None:
        if not self.root:
            self.root = getattr(tk, "_default_root", None)
        if not self.root or not self.win or not self.win.winfo_exists():
            return
        try:
            from voice_flow.audio_flow_dialog import calculate_anchored_dialog_geometry
            w, h, x, y = calculate_anchored_dialog_geometry(
                self.win,
                parent=getattr(self, "_anchor_win", None),
                default_w=560,
                default_h=650,
                gap=12,
            )
            self.win.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            self.win.update_idletasks()
            current_w = self.win.winfo_width()
            current_h = self.win.winfo_height()
            width = current_w if current_w > 200 else 560
            height = current_h if current_h > 200 else 650
            screen_w = self.win.winfo_screenwidth()
            screen_h = self.win.winfo_screenheight()
            x = max(0, (screen_w - width) // 2)
            y = max(0, (screen_h - height) // 2 - 20)
            self.win.geometry(f"{width}x{height}+{x}+{y}")

    def _run_on_ui(self, callback: Callable[[], None]) -> None:
        if hasattr(self, "_ui_queue"):
            self._ui_queue.put(callback)
            self._schedule_ui_poll()
            if threading.current_thread() is threading.main_thread():
                self._process_ui_queue()
            return
        root = self.root or getattr(tk, "_default_root", None)
        if root is not None:
            try:
                root.after(0, callback)
                return
            except Exception:
                pass
        try:
            callback()
        except Exception:
            pass


video_flow_widget = VideoFlowScreenWidget()


def launch_video_flow_composer(
    selected_text: str = "",
    mode: str = "summary",
    *,
    root: tk.Tk | None = None,
    on_generate: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> VideoFlowScreenWidget:
    """Convenience helper for desktop scripts and ad-hoc testing."""
    if root is not None:
        video_flow_widget.attach_root(root)
    if on_generate is not None:
        video_flow_widget.on_generate = on_generate
    return video_flow_widget.launch(selected_text, mode)


__all__ = [
    "COMPOSER_COLORS",
    "GRID_IDLE_DOT",
    "GRID_TICK_MS",
    "GRID_TONES",
    "LOCAL_MODEL_REF",
    "NOTEBOOKLM_FORMAT_OPTIONS",
    "NOTEBOOKLM_STYLE_OPTIONS",
    "VideoFlowScreenWidget",
    "launch_video_flow_composer",
    "video_flow_widget",
]

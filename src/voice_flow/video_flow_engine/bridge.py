"""Deterministic Code2Video storyboard to Narova production bridge."""

from __future__ import annotations

from html import escape
import re
from typing import Any

from voice_flow.video_flow_v3.contracts import validate_no_executable_code

from . import scene_author

_ACCENTS = ("#67e8f9", "#a78bfa", "#fb7185", "#fbbf24", "#34d399", "#60a5fa")

# Narration voice: full model id from the shared Audio Flow TTS catalog
# (e.g. "edge/en-US-AvaNeural"). Routed through the registered "voiceflow"
# Narova provider, which synthesizes via the app's own TTS stack.
DEFAULT_VOICE = "edge/en-US-AvaNeural"


def _narrator_voice(voice: Any, color: str) -> dict[str, Any]:
    speaker = str(voice or DEFAULT_VOICE).strip() or DEFAULT_VOICE
    return {"backend": "voiceflow", "speaker": speaker, "color": color, "label": "Narrator"}


def build_directed_production(
    storyboard: dict[str, Any],
    direction: dict[str, Any],
    *,
    title: str = "",
    mode: str = "summary",
    theme: Any = None,
    voice: Any = None,
) -> dict[str, Any]:
    """Assemble a full-fidelity (hyperframes) production from a direction payload.

    Scene bodies come from the treatment library in ``scene_author``; this
    function only validates inputs, resolves the design system, and shapes the
    Narova config. Falls back to the legacy production on any validation error
    is the caller's responsibility.
    """
    validate_no_executable_code(storyboard)
    validate_no_executable_code(direction)
    sections = storyboard.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("planning_failed: Code2Video storyboard has no sections")
    if len(sections) > 24:
        raise ValueError("planning_failed: Code2Video storyboard exceeds the 24-scene limit")

    design = scene_author.resolve_design(direction, theme)
    entries = {
        int(entry.get("index") or 0): entry
        for entry in direction.get("scenes") or []
        if isinstance(entry, dict) and entry.get("index")
    }
    scenes: list[dict[str, Any]] = []
    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            raise ValueError("planning_failed: storyboard section must be an object")
        entry = entries.get(index) or {
            "index": index,
            "treatment": "labeled-diagram",
            "title_label": str(section.get("title") or f"Scene {index}"),
            "labels": [],
            "transition": "fade",
        }
        scenes.append(scene_author.author_scene(section, entry, design, index))
    validate_no_executable_code({"scenes": scenes})

    light = isinstance(theme, dict) and str(theme.get("mode", "")).lower() == "light"
    return {
        "title": title or str(storyboard.get("topic") or "Video Flow Explanation"),
        "size": "16:9",
        "renderer": "hyperframes",
        "voices": {"narrator": _narrator_voice(voice, design["accent"])},
        "theme": {
            "mode": "light" if light else "dark",
            "bg": design["bg"],
            "accent": design["accent"],
            "css": "theme.css",
        },
        "safeLayout": True,
        "chrome": False,
        "captions": {"preset": "rise"},
        "timing": {"gapSentence": 0.22, "gapTurn": 0.35, "lead": 0.12, "tail": 0.45, "tempo": 1.05 if mode == "full" else 1.12},
        "scenes": scenes,
        "_files": {"theme.css": scene_author.theme_css(design)},
    }


def build_narova_production(
    storyboard: dict[str, Any],
    *,
    title: str = "",
    mode: str = "summary",
    theme: Any = None,
    visual_direction: str = "",
    voice: Any = None,
) -> dict[str, Any]:
    """Translate semantic teaching intent into Narova's declarative scene format.

    Model-authored values are treated as text only. The bridge owns every HTML
    tag, visual node, color, and animation primitive.
    """

    validate_no_executable_code(storyboard)
    sections = storyboard.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("planning_failed: Code2Video storyboard has no sections")
    if len(sections) > 24:
        raise ValueError("planning_failed: Code2Video storyboard exceeds the 24-scene limit")

    theme_config = _resolve_theme(theme)
    scenes: list[dict[str, Any]] = []
    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            raise ValueError("planning_failed: storyboard section must be an object")
        section_title = str(section.get("title") or f"Scene {index}").strip()
        lecture_lines = [str(line).strip() for line in section.get("lecture_lines") or [] if str(line).strip()]
        animations = [str(item).strip() for item in section.get("animations") or [] if str(item).strip()]
        if not lecture_lines:
            raise ValueError("planning_failed: storyboard section has no lecture lines")
        if len(lecture_lines) > 8:
            raise ValueError("planning_failed: storyboard section exceeds the 8-line limit")
        if any(len(line) > 1_000 for line in lecture_lines):
            raise ValueError("planning_failed: storyboard lecture line exceeds the 1000-character limit")

        narration = " ".join(lecture_lines)
        body_lines = "".join(
            f'<li class="cue" data-cue="0" data-delay="{line_index * 0.12:.2f}">{escape(line)}</li>'
            for line_index, line in enumerate(lecture_lines)
        )
        accent = theme_config["accent"] if index == 1 else _ACCENTS[(index - 1) % len(_ACCENTS)]
        scenes.append(
            {
                "id": _scene_id(section.get("id"), index),
                "title": section_title,
                "learning_goal": str(section.get("learning_goal") or section_title),
                "visual_intentions": animations,
                "vo": [{"who": "narrator", "text": narration}],
                "transition": "slide" if index % 2 else "fade",
                "body": (
                    '<section class="vf-scene">'
                    f'<p class="vf-kicker reveal">STEP {index:02d}</p>'
                    f'<h1 class="reveal">{escape(section_title)}</h1>'
                    f'<ul>{body_lines}</ul>'
                    "</section>"
                ),
                "visual": _visual_scene(section_title, lecture_lines, animations, index, accent, visual_direction),
            }
        )

    return {
        "title": title or str(storyboard.get("topic") or "Video Flow Explanation"),
        "size": "16:9",
        "renderer": "no-browser",
        "voices": {"narrator": _narrator_voice(voice, "#67e8f9")},
        "theme": theme_config,
        "safeLayout": True,
        "chrome": False,
        "captions": {"preset": "rise"},
        "timing": {"gapSentence": 0.22, "gapTurn": 0.35, "lead": 0.12, "tail": 0.45, "tempo": 1.05 if mode == "full" else 1.12},
        "scenes": scenes,
    }


def _visual_scene(
    title: str,
    lines: list[str],
    animations: list[str],
    index: int,
    accent: str,
    visual_direction: str = "",
) -> dict[str, Any]:
    intent = " ".join([title, *animations, visual_direction]).lower()
    if any(word in intent for word in ("compare", "contrast", "versus", "alternative", "side-by-side")):
        representation = "comparison"
        content = _comparison_content(lines, accent)
    elif any(word in intent for word in ("transform", "collapse", "become", "adjust", "learn")):
        representation = "transformation"
        content = _transformation_content(lines, accent)
    elif any(word in intent for word in ("flow", "pipeline", "connect", "path", "sequence", "through")):
        representation = "process flow"
        content = _flow_content(lines, accent)
    else:
        representation = "focused explanation"
        content = _focus_content(lines, accent)

    return {
        "type": "stack",
        "style": {"direction": "column", "padding": 68, "gap": 28, "background": "#0b1020"},
        "children": [
            {
                "type": "stack",
                "style": {"direction": "row", "gap": 18, "height": 72},
                "children": [
                    {"type": "text", "text": f"{index:02d}", "style": {"color": accent, "fontSize": 26, "fontWeight": "bold", "width": 48}},
                    {"type": "text", "text": title, "style": {"color": "#f8fafc", "fontSize": 48, "fontWeight": "bold", "maxLines": 2}, "enter": "rise"},
                ],
            },
            content,
            {
                "type": "text",
                "text": representation.upper(),
                "style": {"color": accent, "fontSize": 18, "fontWeight": "bold", "height": 28},
                "enter": {"type": "fade", "at": {"cue": 0, "offset": 0.35}},
            },
        ],
    }


def _card(line: str, number: int, accent: str, *, offset: float = 0.0) -> dict[str, Any]:
    return {
        "type": "stack",
        "style": {"direction": "column", "padding": 24, "gap": 12, "background": "#172036", "radius": 18, "flex": 1},
        "enter": {"type": "rise", "at": {"cue": 0, "offset": offset}},
        "children": [
            {"type": "text", "text": f"{number:02d}", "style": {"color": accent, "fontSize": 20, "fontWeight": "bold", "height": 28}},
            {"type": "text", "text": line, "style": {"color": "#f8fafc", "fontSize": 28, "fontWeight": "bold", "maxLines": 4}},
        ],
    }


def _flow_content(lines: list[str], accent: str) -> dict[str, Any]:
    children: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if index:
            children.append(
                {
                    "type": "text",
                    "text": ">",
                    "style": {"color": accent, "fontSize": 42, "fontWeight": "bold", "width": 34, "verticalAlign": "center", "textAlign": "center"},
                    "enter": {"type": "pop", "at": {"cue": 0, "offset": index * 0.16}},
                }
            )
        children.append(_card(line, index + 1, accent, offset=index * 0.16))
    return {"type": "stack", "style": {"direction": "row", "gap": 16, "flex": 1}, "children": children}


def _comparison_content(lines: list[str], accent: str) -> dict[str, Any]:
    left = lines[0]
    right = lines[1] if len(lines) > 1 else "A contrasting explanation"
    return {
        "type": "stack",
        "style": {"direction": "row", "gap": 20, "flex": 1},
        "children": [
            _card(left, 1, accent),
            {
                "type": "text",
                "text": "VS",
                "style": {"color": accent, "fontSize": 34, "fontWeight": "bold", "width": 54, "verticalAlign": "center", "textAlign": "center"},
                "enter": {"type": "pop", "at": {"cue": 0, "offset": 0.18}},
            },
            _card(right, 2, accent, offset=0.3),
        ],
    }


def _transformation_content(lines: list[str], accent: str) -> dict[str, Any]:
    before = lines[0]
    after = lines[-1] if len(lines) > 1 else lines[0]
    return {
        "type": "stack",
        "style": {"direction": "row", "gap": 22, "flex": 1},
        "children": [
            _card(before, 1, "#94a3b8"),
            {
                "type": "text",
                "text": "=>",
                "style": {"color": accent, "fontSize": 38, "fontWeight": "bold", "width": 64, "verticalAlign": "center", "textAlign": "center"},
                "enter": {"type": "slide-left", "at": {"cue": 0, "offset": 0.2}},
            },
            _card(after, 2, accent, offset=0.35),
        ],
    }


def _focus_content(lines: list[str], accent: str) -> dict[str, Any]:
    return {
        "type": "stack",
        "style": {"direction": "column", "gap": 16, "padding": 12, "flex": 1},
        "children": [_card(line, index + 1, accent, offset=index * 0.14) for index, line in enumerate(lines)],
    }


def _resolve_theme(theme: Any) -> dict[str, str]:
    if isinstance(theme, str) and theme.lower() == "light":
        return {"mode": "light", "bg": "#f8fafc", "accent": "#2563eb"}
    result = {"bg": "#0b1020", "accent": "#67e8f9"}
    if isinstance(theme, dict):
        if str(theme.get("mode", "")).lower() == "light":
            result.update({"mode": "light", "bg": "#f8fafc", "accent": "#2563eb"})
        for key in ("bg", "accent"):
            value = str(theme.get(key, ""))
            if re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
                result[key] = value
    return result


def _scene_id(value: Any, index: int) -> str:
    raw = str(value or f"scene_{index}")
    cleaned = "".join(char if char.isalnum() or char in "_-" else "_" for char in raw)
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"scene_{index}_{cleaned}"
    return cleaned











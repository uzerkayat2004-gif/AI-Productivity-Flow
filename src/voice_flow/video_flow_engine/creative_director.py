"""Creative Director: storyboard → per-video design system + authored scenes.

The LLM chooses visual treatments, metaphors, and labels (constrained JSON,
never executable code). This module owns every HTML tag, SVG path whitelist,
and declarative Three.js config emitted to Narova. All output passes
``validate_no_executable_code``.
"""

from __future__ import annotations

import json
import re
from html import escape
from typing import Any, Callable

from voice_flow.video_flow_v3.contracts import validate_no_executable_code

# Treatments the director may assign. Each maps to an authoring function below.
TREATMENTS = (
    "hero-title",        # opening: giant title, drawn underline, kicker
    "labeled-diagram",   # central SVG figure with sequenced callout labels
    "process-flow",      # animated pipeline: nodes pop, arrows draw
    "comparison-split",  # two panels slide in, VS badge, short bullets
    "timeline",          # axis draws, events pop along it
    "counter-stats",     # 1-3 giant animated counters
    "wave-demo",         # layered spectrum waves drawing in sequence
    "particle-field",    # three.js point cloud + slow camera dolly + labels
    "orbit-3d",          # three.js central body + orbiting satellites
    "cutaway-3d",        # three.js stacked/exploded layers with labels
    "before-after",      # split-screen transformation reveal
    "scale-comparison",  # relative-size circles/bars with measures
    "layer-reveal",      # cascading stacked layers with labels
    "chart-growth",      # SVG chart with draw animation + counters
    "recap-mosaic",      # closing grid of scene marks + keywords
)

# Words per on-screen label / labels per scene (mission §16: text reduction).
MAX_LABEL_WORDS = 7
MAX_LABELS = 4
# Same treatment may not repeat more than this many times consecutively or
# occupy more than this share of scenes (mission §15: diversity).
MAX_CONSECUTIVE = 2
MAX_SHARE = 0.45

_PATH_CHARS = re.compile(r"^[MmLlHhVvCcSsQqTtAaZz0-9 ,.\-+eE]*$")


class DirectorError(RuntimeError):
    """Raised when direction cannot be produced; callers fall back."""


def direct(
    storyboard: dict[str, Any],
    gateway: Any,
    *,
    theme: Any = None,
    visual_direction: str = "",
) -> dict[str, Any]:
    """Return a direction payload: brief + one treatment entry per section.

    Falls back to a deterministic assignment when no gateway is available or
    the LLM answer is unusable; Video Flow must never fail here.
    """
    sections = storyboard.get("sections") or []
    if not sections:
        raise DirectorError("storyboard has no sections")
    direction: dict[str, Any] | None = None
    if gateway is not None:
        direction = _direct_with_model(storyboard, sections, gateway, visual_direction)
    if direction is None:
        direction = _deterministic_direction(storyboard, sections)
    direction["scenes"] = _enforce_diversity(direction["scenes"])
    validate_no_executable_code(direction)
    return direction


# ---------------------------------------------------------------- model path

_DIRECTOR_PROMPT = """You are the Creative Director for an educational video engine.
Given an educational storyboard, decide HOW each scene is VISUALLY demonstrated.

Rules:
- Visual demonstration first; text stays minimal (labels, not paragraphs).
- Choose treatments that fit the concept; avoid repeating one treatment.
- Labels: at most {max_labels} per scene, at most {max_label_words} words each.
- Optional "svg_paths": 1-6 SVG path data strings (viewBox 0 0 400 220) that
  illustrate the core figure (waves, beams, outlines). Coordinates only —
  no text elements, no fills with urls.
- Optional "three_hint": one of "particles", "orbit", "layers", or omit.
- Optional "count_from"/"count_to"/"count_suffix" for counter-stats and
  chart-growth (numbers only).
- "transition": one of fade, wipe, slide, zoom.

Available treatments: {treatments}

Return STRICT JSON only:
{{
  "brief": {{
    "motion": "crisp|flowing|technical",
    "background": "gradient|grid|solid",
    "accent_shift": -1|0|1
  }},
  "scenes": [
    {{
      "index": 1,
      "treatment": "...",
      "title_label": "short scene title",
      "labels": ["...", "..."],
      "svg_paths": ["M ..."],
      "three_hint": "orbit",
      "count_from": 0, "count_to": 95, "count_suffix": "%",
      "transition": "fade"
    }}
  ]
}}

Storyboard:
{storyboard}
"""


def _direct_with_model(
    storyboard: dict[str, Any],
    sections: list[Any],
    gateway: Any,
    visual_direction: str,
) -> dict[str, Any] | None:
    prompt = _DIRECTOR_PROMPT.format(
        max_labels=MAX_LABELS,
        max_label_words=MAX_LABEL_WORDS,
        treatments=", ".join(TREATMENTS),
        storyboard=json.dumps(
            {"topic": storyboard.get("topic"), "sections": sections}, ensure_ascii=False
        )[:12_000],
    )
    if visual_direction:
        prompt += f"\nUser visual direction: {visual_direction}\n"
    try:
        response = _generate(gateway, prompt)
        payload = _parse_json(response)
    except Exception:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("scenes"), list):
        return None
    scenes: list[dict[str, Any]] = []
    by_index = {entry.get("index"): entry for entry in payload["scenes"] if isinstance(entry, dict)}
    for position in range(1, len(sections) + 1):
        entry = by_index.get(position)
        if not isinstance(entry, dict):
            return None
        treatment = str(entry.get("treatment") or "").strip()
        if treatment not in TREATMENTS:
            return None
        labels = [str(item).strip() for item in entry.get("labels") or [] if str(item).strip()]
        labels = [" ".join(label.split()) for label in labels][:MAX_LABELS]
        if any(len(label.split()) > MAX_LABEL_WORDS for label in labels):
            labels = [" ".join(label.split()[:MAX_LABEL_WORDS]) for label in labels]
        scene: dict[str, Any] = {
            "index": position,
            "treatment": treatment,
            "title_label": " ".join(str(entry.get("title_label") or "").split())[:80]
            or f"Scene {position}",
            "labels": labels,
            "transition": str(entry.get("transition") or "fade")
            if str(entry.get("transition") or "") in {"fade", "wipe", "slide", "zoom"}
            else "fade",
        }
        paths = _sanitize_paths(entry.get("svg_paths"))
        if paths:
            scene["svg_paths"] = paths
        hint = str(entry.get("three_hint") or "").strip()
        if hint in {"particles", "orbit", "layers"}:
            scene["three_hint"] = hint
        for key in ("count_from", "count_to"):
            value = entry.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                scene[key] = float(value)
        suffix = str(entry.get("count_suffix") or "")[:4]
        if suffix:
            scene["count_suffix"] = suffix
        scenes.append(scene)
    brief_raw = payload.get("brief") if isinstance(payload.get("brief"), dict) else {}
    brief = {
        "motion": str(brief_raw.get("motion") or "crisp"),
        "background": str(brief_raw.get("background") or "gradient"),
        "accent_shift": int(brief_raw.get("accent_shift") or 0),
    }
    return {"brief": brief, "scenes": scenes}


def _generate(gateway: Any, prompt: str) -> str:
    for attribute in ("request_isolated", "generate"):
        method = getattr(gateway, attribute, None)
        if callable(method):
            try:
                if attribute == "request_isolated":
                    return str(
                        method(
                            prompt=prompt,
                            model_ref=None,
                            max_tokens=4_000,
                            timeout_seconds=240,
                            job_id="creative-director",
                            process_manager=_NullManager(),
                        )
                    )
                return str(method(prompt=prompt, max_tokens=4_000))
            except Exception:
                continue
    raise DirectorError("gateway has no usable generation method")


class _NullManager:
    def register(self, *args: Any) -> None:
        pass

    def unregister(self, *args: Any) -> None:
        pass

    def cancel_job(self, *args: Any) -> None:
        pass

    def raise_if_cancelled(self, *args: Any) -> None:
        pass


def _parse_json(text: str) -> Any:
    raw = str(text).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    start, depth, in_string, escaped = -1, 0, False, False
    best: dict[str, Any] | None = None
    for index, char in enumerate(raw):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        candidate = json.loads(raw[start : index + 1])
                    except json.JSONDecodeError:
                        continue
                    if isinstance(candidate, dict) and (
                        best is None or len(candidate.get("scenes") or []) > len(best.get("scenes") or [])
                    ):
                        best = candidate
    if best is not None:
        return best
    raise ValueError("no JSON object in director response")


def _sanitize_paths(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    paths: list[str] = []
    for item in value[:6]:
        text = str(item or "").strip()
        if not text or len(text) > 2_000 or not _PATH_CHARS.fullmatch(text):
            continue
        paths.append(text)
    return paths


# --------------------------------------------------------- deterministic path

_INTENT_TREATMENTS: list[tuple[tuple[str, ...], str]] = [
    (("compare", "contrast", "versus", "alternative", "trade", "versus"), "comparison-split"),
    (("flow", "pipeline", "chain", "sequence", "step", "process", "stage"), "process-flow"),
    (("history", "year", "timeline", "evolution", "progress", "milestone"), "timeline"),
    (("percent", "rate", "number", "statistic", "speed", "size", "scale", "measure"), "counter-stats"),
    (("wave", "light", "sound", "spectrum", "frequency", "color", "signal"), "wave-demo"),
    (("3d", "space", "orbit", "planet", "molecule", "atom", "structure", "anatomy"), "orbit-3d"),
    (("network", "cloud", "crowd", "swarm", "field", "many", "distribution"), "particle-field"),
    (("layer", "stack", "inside", "cutaway", "component", "architecture"), "cutaway-3d"),
    (("before", "after", "transform", "change", "become", "migrate", "upgrade"), "before-after"),
    (("bigger", "smaller", "relative", "compare size", "proportion", "ratio"), "scale-comparison"),
    (("chart", "graph", "growth", "trend", "increase", "decline", "data"), "chart-growth"),
    (("recap", "summary", "review", "conclusion", "together", "key points"), "recap-mosaic"),
]


def _deterministic_direction(storyboard: dict[str, Any], sections: list[Any]) -> dict[str, Any]:
    scenes: list[dict[str, Any]] = []
    used: list[str] = []
    for position, section in enumerate(sections, start=1):
        section = section if isinstance(section, dict) else {}
        text = " ".join(
            [
                str(section.get("title") or ""),
                " ".join(str(line) for line in section.get("lecture_lines") or []),
                " ".join(str(item) for item in section.get("animations") or []),
            ]
        ).lower()
        treatment = "labeled-diagram"
        for words, candidate in _INTENT_TREATMENTS:
            if any(word in text for word in words) and candidate not in used[-MAX_CONSECUTIVE:]:
                treatment = candidate
                break
        else:
            rotation = [t for t in TREATMENTS if t not in ("hero-title", "recap-mosaic") and t not in used[-MAX_CONSECUTIVE:]]
            treatment = rotation[(position - 1) % len(rotation)]
        if position == 1:
            treatment = "hero-title"
        if position == len(sections) and len(sections) >= 4:
            treatment = "recap-mosaic"
        labels = []
        for line in section.get("lecture_lines") or []:
            words = str(line).split()
            if words:
                labels.append(" ".join(words[:MAX_LABELS]))
            if len(labels) >= 3:
                break
        scenes.append(
            {
                "index": position,
                "treatment": treatment,
                "title_label": " ".join(str(section.get("title") or f"Scene {position}").split())[:80],
                "labels": labels[:MAX_LABELS],
                "transition": "wipe" if position == 1 else ("zoom" if treatment.endswith("3d") or treatment == "particle-field" else "fade"),
            }
        )
        used.append(treatment)
    return {"brief": {"motion": "crisp", "background": "gradient", "accent_shift": 0}, "scenes": scenes}


def _enforce_diversity(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    previous, run = "", 0
    for scene in scenes:
        treatment = scene["treatment"]
        counts[treatment] = counts.get(treatment, 0) + 1
        if treatment == previous:
            run += 1
        else:
            previous, run = treatment, 1
        overused = run > MAX_CONSECUTIVE or counts[treatment] > max(2, int(MAX_SHARE * len(scenes) + 0.999))
        if overused and treatment not in ("hero-title", "recap-mosaic"):
            rotation = [t for t in TREATMENTS if t not in ("hero-title", "recap-mosaic")]
            scene["treatment"] = rotation[(scene["index"] + counts[treatment]) % len(rotation)]
            counts[scene["treatment"]] = counts.get(scene["treatment"], 0) + 1
            previous, run = scene["treatment"], 1
    return scenes

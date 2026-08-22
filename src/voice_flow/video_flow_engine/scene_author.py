"""Author Narova scenes from Creative Director treatments.

Every emitter produces declarative content only: HTML with Narova's motion
attributes (reveal / cue / data-draw / data-count / data-mark / data-delay),
inline SVG built from whitelisted path data, and declarative three.js scene
configs. No scripts are ever emitted.
"""

from __future__ import annotations

import math
from html import escape
from typing import Any

import re

from .creative_director import DirectorError

_HEX = re.compile(r"#[0-9A-Fa-f]{6}")

# ---------------------------------------------------------------- design tokens


def resolve_design(direction: dict[str, Any], theme: Any) -> dict[str, Any]:
    brief = direction.get("brief") if isinstance(direction.get("brief"), dict) else {}
    base_bg, base_accent = "#0b1020", "#67e8f9"
    if isinstance(theme, dict):
        if str(theme.get("mode", "")).lower() == "light":
            base_bg, base_accent = "#f4f7fb", "#2563eb"
        value = str(theme.get("bg") or "")
        if _HEX.fullmatch(value):
            base_bg = value
        value = str(theme.get("accent") or "")
        if _HEX.fullmatch(value):
            base_accent = value
    palette = [
        base_accent,
        "#a78bfa" if base_accent.lower() != "#a78bfa" else "#f472b6",
        "#fbbf24",
        "#34d399",
        "#fb7185",
    ]
    shift = int(brief.get("accent_shift") or 0)
    if shift:
        palette = palette[shift:] + palette[:shift]
    light = isinstance(theme, dict) and str(theme.get("mode", "")).lower() == "light"
    ink = "#0f172a" if light else "#f8fafc"
    surface = "#ffffff" if light else "#141c31"
    surface_edge = "#dbe3f0" if light else "#26304d"
    return {
        "bg": base_bg,
        "ink": ink,
        "muted": "#64748b",
        "surface": surface,
        "edge": surface_edge,
        "accent": palette[0],
        "palette": palette,
        "motion": str(brief.get("motion") or "crisp"),
        "background": str(brief.get("background") or "gradient"),
        "radius": 16,
    }


def theme_css(design: dict[str, Any]) -> str:
    """Per-video design system stylesheet (theme.css content)."""
    background = (
        f"radial-gradient(1200px 700px at 70% 20%, {_mix(design['bg'], design['accent'], 0.10)}, {design['bg']} 62%)"
        if design["background"] == "gradient"
        else (
            f"repeating-linear-gradient(0deg, transparent 0 63px, {design['edge']} 63px 64px),"
            f"repeating-linear-gradient(90deg, transparent 0 63px, {design['edge']} 63px 64px), {design['bg']}"
            if design["background"] == "grid"
            else design["bg"]
        )
    )
    ease = "power3.out" if design["motion"] == "flowing" else "power2.out"
    return f"""
.vfd-stage {{ position: absolute; inset: 0; display: flex; flex-direction: column;
  padding: 72px 84px; background: {background}; color: {design['ink']}; }}
.vfd-stage.vfd-clear {{ background: transparent; }}
.vfd-kicker {{ font: 700 20px/1 var(--sans, system-ui); letter-spacing: 0.32em;
  text-transform: uppercase; color: {design['accent']}; margin: 0 0 18px; }}
.vfd-title {{ font: 800 58px/1.08 var(--sans, system-ui); margin: 0 0 26px; max-width: 92%; }}
.vfd-label {{ font: 700 24px/1.3 var(--sans, system-ui); color: {design['ink']}; }}
.vfd-sub {{ font: 500 21px/1.4 var(--sans, system-ui); color: {design['muted']}; }}
.vfd-panel {{ background: {design['surface']}; border: 1px solid {design['edge']};
  border-radius: {design['radius']}px; padding: 26px 30px; }}
.vfd-chip {{ display: inline-flex; align-items: center; gap: 10px; font: 700 22px/1
  var(--sans, system-ui); padding: 14px 22px; border-radius: 999px;
  background: {design['surface']}; border: 1px solid {design['edge']}; }}
.vfd-num {{ font: 800 15px/1 var(--sans, system-ui); color: {design['accent']};
  letter-spacing: 0.18em; }}
.vfd-figure {{ flex: 1; display: grid; place-items: center; min-height: 0; }}
.vfd-row {{ display: flex; align-items: center; gap: 22px; }}
.vfd-grid {{ display: grid; gap: 20px; }}
.vfd-stage[data-motion] {{ /* ease hint for future runtimes */ }}
""".replace("power3.out", ease)


# ---------------------------------------------------------------- scene emitters


def author_scene(section: dict[str, Any], entry: dict[str, Any], design: dict[str, Any], index: int) -> dict[str, Any]:
    treatment = entry.get("treatment") or "labeled-diagram"
    title = escape(str(entry.get("title_label") or f"Scene {index}"))
    labels = [escape(str(item)) for item in entry.get("labels") or []][:4]
    builder = _BUILDERS.get(treatment, _labeled_diagram)
    body = builder(title, labels, entry, design, index)
    scene: dict[str, Any] = {
        "id": _scene_id(section, index, treatment),
        "transition": entry.get("transition") or "fade",
        "vo": [{"who": "narrator", "text": " ".join(str(line) for line in section.get("lecture_lines") or [])}],
        "body": body,
    }
    three = _three_for(treatment, entry, design)
    if three:
        scene["three"] = three
    return scene


def _stage(inner: str, *, kicker: str | None = None, extra: str = "") -> str:
    kick = f'<p class="vfd-kicker reveal">{kicker}</p>' if kicker else ""
    return f'<div class="vfd-stage" {extra}>{kick}{inner}</div>'


def _hero_title(title: str, labels: list[str], entry: dict[str, Any], design: dict[str, Any], index: int) -> str:
    sub = f'<p class="vfd-sub reveal" data-delay="0.5">{labels[0]}</p>' if labels else ""
    wave = _sine_path(design["accent"], amplitude=14, wavelength=180, width=560, phase=0.0)
    return _stage(
        f'<h1 class="vfd-title reveal">{title}</h1>'
        f'<svg viewBox="0 0 560 40" style="width:560px;overflow:visible">'
        f'<path class="cue" data-cue="0" data-delay="0.25" data-draw d="{wave}" '
        f'stroke="{design["accent"]}" stroke-width="4" fill="none"/></svg>{sub}',
        kicker="VIDEO FLOW",
    )


def _labeled_diagram(title: str, labels: list[str], entry: dict[str, Any], design: dict[str, Any], index: int) -> str:
    paths = entry.get("svg_paths") or []
    figure = ""
    if paths:
        drawn = "".join(
            f'<path class="cue" data-cue="0" data-delay="{0.15 + i * 0.45:.2f}" data-draw d="{escape(p)}" '
            f'stroke="{design["palette"][i % len(design["palette"])]}" stroke-width="3" fill="none"/>'
            for i, p in enumerate(paths[:5])
        )
        figure = f'<svg viewBox="0 0 400 220" style="max-width:820px;width:70%;">{drawn}</svg>'
    else:
        figure = _default_figure(design, index)
    callouts = "".join(
        f'<div class="vfd-panel cue" data-cue="0" data-delay="{0.4 + i * 0.35:.2f}" '
        f'style="display:flex;gap:12px;align-items:center"><span class="vfd-num">{i + 1:02d}</span>'
        f'<span class="vfd-label">{label}</span></div>'
        for i, label in enumerate(labels[:3])
    )
    return _stage(
        f'<h1 class="vfd-title reveal" style="font-size:44px">{title}</h1>'
        f'<div class="vfd-row" style="flex:1;align-items:stretch">'
        f'<div class="vfd-figure">{figure}</div>'
        f'<div class="vfd-grid" style="grid-template-columns:1fr;justify-content:center">{callouts}</div></div>'
    )


def _process_flow(title: str, labels: list[str], entry: dict[str, Any], design: dict[str, Any], index: int) -> str:
    items = labels or ["Input", "Process", "Output"]
    nodes = []
    for i, label in enumerate(items[:5]):
        delay = i * 0.5
        if i:
            nodes.append(
                f'<svg viewBox="0 0 60 12" style="width:54px"><path class="cue" data-cue="0" '
                f'data-delay="{delay - 0.15:.2f}" data-draw d="M2 6 H50 M44 2 L52 6 L44 10" '
                f'stroke="{design["accent"]}" stroke-width="2.5" fill="none"/></svg>'
            )
        nodes.append(
            f'<div class="vfd-panel cue" data-cue="0" data-delay="{delay:.2f}" '
            f'style="text-align:center;min-width:170px"><p class="vfd-num">STEP {i + 1}</p>'
            f'<p class="vfd-label" style="margin:10px 0 0">{label}</p></div>'
        )
    return _stage(
        f'<h1 class="vfd-title reveal" style="font-size:44px">{title}</h1>'
        f'<div class="vfd-row" style="flex:1;justify-content:center;flex-wrap:wrap">{"".join(nodes)}</div>'
    )


def _comparison_split(title: str, labels: list[str], entry: dict[str, Any], design: dict[str, Any], index: int) -> str:
    left = labels[0] if labels else "Before"
    right = labels[1] if len(labels) > 1 else "After"
    extra_left = labels[2] if len(labels) > 2 else ""
    extra_right = labels[3] if len(labels) > 3 else ""
    def panel(label: str, extra: str, color: str, delay: float) -> str:
        sub = f'<p class="vfd-sub cue" data-cue="0" data-delay="{delay + 0.3:.2f}">{extra}</p>' if extra else ""
        return (
            f'<div class="vfd-panel cue" data-cue="0" data-delay="{delay:.2f}" '
            f'style="flex:1;border-top:5px solid {color}"><p class="vfd-label" '
            f'style="font-size:30px">{label}</p>{sub}</div>'
        )
    return _stage(
        f'<h1 class="vfd-title reveal" style="font-size:42px">{title}</h1>'
        f'<div class="vfd-row" style="flex:1">{panel(left, extra_left, design["palette"][1], 0.3)}'
        f'<div class="cue" data-cue="0" data-delay="0.75" style="display:grid;place-items:center">'
        f'<span class="vfd-chip" style="color:{design["accent"]};border-color:{design["accent"]}">VS</span></div>'
        f'{panel(right, extra_right, design["accent"], 0.55)}</div>'
    )


def _timeline(title: str, labels: list[str], entry: dict[str, Any], design: dict[str, Any], index: int) -> str:
    events = labels or ["Start", "Middle", "Now"]
    width = 900
    step = width // max(1, len(events))
    marks = "".join(
        f'<circle class="cue" data-cue="0" data-delay="{0.4 + i * 0.5:.2f}" cx="{(i + 0.5) * step}" cy="30" r="9" '
        f'fill="{design["palette"][i % len(design["palette"])]}"/>'
        for i in range(len(events[:6]))
    )
    captions = "".join(
        f'<div class="cue" data-cue="0" data-delay="{0.55 + i * 0.5:.2f}" style="position:absolute;'
        f'left:{(i + 0.5) * step - 90}px;top:64px;width:180px;text-align:center">'
        f'<p class="vfd-label" style="font-size:21px">{label}</p></div>'
        for i, label in enumerate(events[:6])
    )
    return _stage(
        f'<h1 class="vfd-title reveal" style="font-size:42px">{title}</h1>'
        f'<div class="vfd-figure"><div style="position:relative;width:{width}px">'
        f'<svg viewBox="0 0 {width} 60" style="width:{width}px"><path class="cue" data-cue="0" data-delay="0.15" '
        f'data-draw d="M10 30 H{width - 10}" stroke="{design["edge"]}" stroke-width="3"/>{marks}</svg>'
        f'{captions}</div></div>'
    )


def _counter_stats(title: str, labels: list[str], entry: dict[str, Any], design: dict[str, Any], index: int) -> str:
    to = int(entry.get("count_to") or 95)
    frm = int(entry.get("count_from") or 0)
    suffix = escape(str(entry.get("count_suffix") or ""))
    stats = [
        f'<div class="vfd-panel cue" data-cue="0" style="text-align:center;flex:1">'
        f'<div class="cue" data-cue="0" data-delay="0.2" data-count="{to}" data-count-from="{frm}" '
        f'data-count-suffix="{suffix}" style="font:800 96px/1 var(--sans, system-ui);'
        f'color:{design["accent"]}">{frm}{suffix}</div>'
        f'<p class="vfd-label" style="margin-top:14px">{labels[0] if labels else title}</p></div>'
    ]
    for i, label in enumerate(labels[1:2], start=1):
        stats.append(
            f'<div class="vfd-panel cue" data-cue="0" data-delay="{0.4 + i * 0.3:.2f}" '
            f'style="text-align:center;flex:1"><p class="vfd-label" '
            f'style="font-size:26px;color:{design["palette"][i + 1]}">{label}</p></div>'
        )
    return _stage(f'<h1 class="vfd-title reveal" style="font-size:40px">{title}</h1>'
                  f'<div class="vfd-row" style="flex:1;align-items:center">{"".join(stats)}</div>')


def _wave_demo(title: str, labels: list[str], entry: dict[str, Any], design: dict[str, Any], index: int) -> str:
    paths = entry.get("svg_paths") or [
        _sine_path(color, amplitude=10 + i * 8, wavelength=130 + i * 40, width=520, phase=i * 0.8)
        for i, color in enumerate(design["palette"][:4])
    ]
    waves = "".join(
        f'<path class="cue" data-cue="0" data-delay="{0.2 + i * 0.4:.2f}" data-draw d="{escape(p)}" '
        f'stroke="{design["palette"][i % len(design["palette"])]}" stroke-width="3" fill="none" '
        f'opacity="{0.95 - i * 0.12:.2f}"/>'
        for i, p in enumerate(paths[:5])
    )
    tags = "".join(
        f'<span class="vfd-chip cue" data-cue="0" data-delay="{0.8 + i * 0.25:.2f}">{label}</span>'
        for i, label in enumerate(labels[:3])
    )
    return _stage(
        f'<h1 class="vfd-title reveal" style="font-size:42px">{title}</h1>'
        f'<div class="vfd-figure"><svg viewBox="0 0 520 160" style="width:74%">{waves}</svg></div>'
        f'<div class="vfd-row" style="justify-content:center;gap:16px">{tags}</div>'
    )


def _before_after(title: str, labels: list[str], entry: dict[str, Any], design: dict[str, Any], index: int) -> str:
    return _comparison_split(title, labels or ["Before", "After"], entry, design, index)


def _scale_comparison(title: str, labels: list[str], entry: dict[str, Any], design: dict[str, Any], index: int) -> str:
    to = float(entry.get("count_to") or 10)
    ratios = [1.0, max(0.15, min(2.6, to / 20.0)), max(0.1, min(3.6, to / 8.0))]
    circles = "".join(
        f'<circle class="cue" data-cue="0" data-delay="{0.25 + i * 0.4:.2f}" cx="{80 + i * 150 + r * 20:.0f}" '
        f'cy="{70 + (60 - r * 14):.0f}" r="{18 + r * 16:.0f}" fill="none" '
        f'stroke="{design["palette"][i % len(design["palette"])]}" stroke-width="4"/>'
        for i, r in enumerate(ratios)
    )
    tags = "".join(
        f'<span class="vfd-chip cue" data-cue="0" data-delay="{0.9 + i * 0.25:.2f}">{label}</span>'
        for i, label in enumerate(labels[:3])
    )
    return _stage(
        f'<h1 class="vfd-title reveal" style="font-size:42px">{title}</h1>'
        f'<div class="vfd-figure"><svg viewBox="0 0 460 160" style="width:70%">{circles}</svg></div>'
        f'<div class="vfd-row" style="justify-content:center;gap:16px">{tags}</div>'
    )


def _layer_reveal(title: str, labels: list[str], entry: dict[str, Any], design: dict[str, Any], index: int) -> str:
    layers = labels or ["Layer 1", "Layer 2", "Layer 3"]
    cards = "".join(
        f'<div class="vfd-panel cue" data-cue="0" data-delay="{0.25 + i * 0.4:.2f}" '
        f'style="margin-left:{i * 36}px;border-left:5px solid {design["palette"][i % len(design["palette"])]};'
        f'display:flex;align-items:center;gap:18px"><span class="vfd-num">L{i + 1}</span>'
        f'<span class="vfd-label">{label}</span></div>'
        for i, label in enumerate(layers[:4])
    )
    return _stage(f'<h1 class="vfd-title reveal" style="font-size:42px">{title}</h1>'
                  f'<div class="vfd-grid" style="flex:1;align-content:center;gap:18px">{cards}</div>')


def _chart_growth(title: str, labels: list[str], entry: dict[str, Any], design: dict[str, Any], index: int) -> str:
    to = int(entry.get("count_to") or 80)
    bars = [0.35, 0.55, 0.78, min(1.0, to / 100.0 + 0.2)]
    rects = "".join(
        f'<rect class="cue" data-cue="0" data-delay="{0.2 + i * 0.35:.2f}" data-grow x="{40 + i * 70}" '
        f'y="{150 - int(b * 120)}" width="46" height="{int(b * 120) + 2}" rx="8" '
        f'fill="{design["palette"][i % len(design["palette"])]}" opacity="0.92"/>'
        for i, b in enumerate(bars)
    )
    axis = f'<path class="cue" data-cue="0" data-delay="0.1" data-draw d="M24 12 V150 H330" stroke="{design["edge"]}" stroke-width="2.5" fill="none"/>'
    count = (
        f'<div class="cue" data-cue="0" data-delay="0.4" data-count="{to}" data-count-suffix="%" '
        f'style="font:800 44px/1 var(--sans, system-ui);color:{design["accent"]}">0%</div>'
    )
    tags = "".join(f'<span class="vfd-chip">{label}</span>' for label in labels[:2])
    return _stage(
        f'<h1 class="vfd-title reveal" style="font-size:42px">{title}</h1>'
        f'<div class="vfd-row" style="flex:1;align-items:center;gap:40px">'
        f'<svg viewBox="0 0 350 165" style="width:56%">{axis}{rects}</svg>'
        f'<div class="vfd-grid" style="gap:16px">{count}{tags}</div></div>'
    )


def _recap_mosaic(title: str, labels: list[str], entry: dict[str, Any], design: dict[str, Any], index: int) -> str:
    cells = labels or []
    while len(cells) < 4:
        cells.append(f"Point {len(cells) + 1}")
    chips = "".join(
        f'<div class="vfd-panel cue" data-cue="0" data-delay="{0.2 + i * 0.3:.2f}" '
        f'style="display:flex;align-items:center;gap:14px"><span style="width:12px;height:12px;'
        f'border-radius:50%;background:{design["palette"][i % len(design["palette"])]}"></span>'
        f'<span class="vfd-label" style="font-size:23px">{label}</span></div>'
        for i, label in enumerate(cells[:6])
    )
    return _stage(
        f'<h1 class="vfd-title reveal" style="font-size:42px">{title}</h1>'
        f'<div class="vfd-grid" style="flex:1;align-content:center;grid-template-columns:1fr 1fr;gap:18px">{chips}</div>'
    )


def _three_overlay(title: str, labels: list[str], entry: dict[str, Any], design: dict[str, Any], index: int) -> str:
    tags = "".join(
        f'<span class="vfd-chip cue" data-cue="0" data-delay="{0.5 + i * 0.3:.2f}">{label}</span>'
        for i, label in enumerate(labels[:3])
    )
    # Narova layers the three.js canvas at z-index 0 BEHIND the scene body,
    # so 3D stages must stay transparent (the WebGL scene paints its own
    # background via the "background" key in the three config).
    return (
        f'<div class="vfd-stage vfd-clear" style="padding:56px 72px">'
        f'<h1 class="vfd-title reveal" style="font-size:40px">{title}</h1>'
        f'<div style="flex:1"></div>'
        f'<div class="vfd-row" style="justify-content:center;gap:16px">{tags}</div></div>'
    )


_BUILDERS = {
    "hero-title": _hero_title,
    "labeled-diagram": _labeled_diagram,
    "process-flow": _process_flow,
    "comparison-split": _comparison_split,
    "timeline": _timeline,
    "counter-stats": _counter_stats,
    "wave-demo": _wave_demo,
    "before-after": _before_after,
    "scale-comparison": _scale_comparison,
    "layer-reveal": _layer_reveal,
    "chart-growth": _chart_growth,
    "recap-mosaic": _recap_mosaic,
    "particle-field": _three_overlay,
    "orbit-3d": _three_overlay,
    "cutaway-3d": _three_overlay,
}


# ---------------------------------------------------------------- three presets


def _three_for(treatment: str, entry: dict[str, Any], design: dict[str, Any]) -> dict[str, Any] | None:
    accent = design["accent"]
    if treatment == "particle-field":
        return {
            "camera": {"position": [0, 1.2, 6], "fov": 55},
            "toneMapping": "aces",
            "background": design["bg"],
            "lights": [{"type": "ambient", "intensity": 0.7}],
            "objects": [
                {
                    # Narova's declarative particle type; spread must be [x, y, z]
                    # (a scalar yields NaN positions) and rotation comes from
                    # rotateDuration, not a custom animate tween.
                    "type": "particles",
                    "count": 900,
                    "spread": [7, 4.5, 7],
                    "color": accent,
                    "size": 0.045,
                    "rotateDuration": 24,
                }
            ],
        }
    if treatment == "orbit-3d":
        planets = []
        for i, offset in enumerate((2.1, 2.9, 3.7)):
            planets.append(
                {
                    "type": "sphere",
                    "radius": 0.22,
                    "color": design["palette"][(i + 1) % len(design["palette"])],
                    "position": [offset, 0, 0],
                    "animate": {"property": "rotation.y", "from": 0, "to": 6.283, "duration": 7 + i * 3, "at": {"cue": 0}, "loop": True},
                }
            )
        return {
            "camera": {"position": [0, 2.4, 7.5], "fov": 50},
            "toneMapping": "aces",
            "background": design["bg"],
            "lights": [
                {"type": "ambient", "intensity": 0.5},
                {"type": "directional", "position": [4, 6, 4], "intensity": 1.1, "shadow": True},
            ],
            "objects": [
                {"type": "sphere", "radius": 1.15, "color": accent, "roughness": 0.35, "metalness": 0.55,
                 "animate": {"property": "rotation.y", "from": 0, "to": 6.283, "duration": 26, "at": {"cue": 0}, "loop": True}},
                *planets,
            ],
        }
    if treatment == "cutaway-3d":
        layers = []
        for i in range(3):
            layers.append(
                {
                    "type": "cube",
                    "size": [2.6 - i * 0.5, 0.5, 2.6 - i * 0.5],
                    "position": [0, 0.85 * i, 0],
                    "color": design["palette"][i % len(design["palette"])],
                    "roughness": 0.4,
                    "metalness": 0.35,
                    "castShadow": True,
                }
            )
        return {
            "camera": {"position": [4.6, 3.4, 5.4], "fov": 46},
            "toneMapping": "aces",
            "background": design["bg"],
            "lights": [
                {"type": "ambient", "intensity": 0.55},
                {"type": "directional", "position": [5, 7, 3], "intensity": 1.2, "shadow": True},
            ],
            "objects": [
                *layers,
                {"type": "sphere", "radius": 0.35, "position": [0, 2.7, 0], "color": accent,
                 "animate": {"property": "position.y", "from": 2.45, "to": 2.85, "duration": 2.4, "at": {"cue": 0}, "loop": True}},
            ],
        }
    return None


# ---------------------------------------------------------------- helpers


def _sine_path(color: str, *, amplitude: float, wavelength: float, width: int, phase: float) -> str:
    del color
    points = []
    for x in range(0, width + 1, 10):
        y = 26 + amplitude * math.sin(2 * math.pi * (x / wavelength) + phase)
        points.append(f"{x} {y:.1f}")
    return "M" + " L".join(points)


def _default_figure(design: dict[str, Any], index: int) -> str:
    accent = design["palette"][index % len(design["palette"])]
    return (
        '<svg viewBox="0 0 400 220" style="width:64%">'
        f'<circle class="cue" data-cue="0" data-delay="0.2" cx="200" cy="110" r="86" fill="none" '
        f'stroke="{design["edge"]}" stroke-width="2.5"/>'
        f'<path class="cue" data-cue="0" data-delay="0.4" data-draw d="M60 110 H340 M200 30 V190" '
        f'stroke="{design["edge"]}" stroke-width="2" stroke-dasharray="6 8" fill="none"/>'
        f'<circle class="cue" data-cue="0" data-delay="0.6" cx="200" cy="110" r="34" fill="{accent}" opacity="0.9"/>'
        "</svg>"
    )


def _scene_id(section: dict[str, Any], index: int, treatment: str) -> str:
    raw = str(section.get("id") or f"{treatment}_{index}")
    cleaned = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in raw)
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"s{index}_{cleaned}"
    return cleaned


def _mix(base: str, other: str, amount: float) -> str:
    try:
        base_rgb = tuple(int(base[i : i + 2], 16) for i in (1, 3, 5))
        other_rgb = tuple(int(other[i : i + 2], 16) for i in (1, 3, 5))
        mixed = tuple(round(b + (o - b) * amount) for b, o in zip(base_rgb, other_rgb))
        return "#{:02x}{:02x}{:02x}".format(*mixed)
    except Exception:
        return base

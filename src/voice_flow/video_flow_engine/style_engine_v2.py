"""Deterministic, compiler-owned design tokens for Video Flow Visual V2.

The Visual Director selects semantic intent through :class:`DesignBible`; this
module is the only place that turns that intent into concrete colours,
typography, and surface values.  It deliberately has no random input, no
provider calls, and no model-authored colour or CSS surface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .visual_plan_v2 import DesignBible


_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_MIN_TEXT_CONTRAST = 4.5


@dataclass(frozen=True)
class ResolvedDesignTokens:
    """Concrete, renderer-ready values resolved from a semantic design bible."""

    background: str
    foreground: str
    muted: str
    accent: str
    secondary: str
    emphasis: str
    surface: str
    edge: str
    surface_opacity: float
    heading_font_stack: str
    body_font_stack: str
    heading_size: int
    body_size: int
    radius: int
    stroke_width: int
    shadow: str
    texture: str
    spacing: int
    motion_easing: str
    surface_mode: str
    background_character: str

    def to_dict(self) -> dict[str, Any]:
        """Return stable plain data for Scene IR artifacts and tests."""

        return {
            "background": self.background,
            "foreground": self.foreground,
            "muted": self.muted,
            "accent": self.accent,
            "secondary": self.secondary,
            "emphasis": self.emphasis,
            "surface": self.surface,
            "edge": self.edge,
            "surface_opacity": self.surface_opacity,
            "heading_font_stack": self.heading_font_stack,
            "body_font_stack": self.body_font_stack,
            "heading_size": self.heading_size,
            "body_size": self.body_size,
            "radius": self.radius,
            "stroke_width": self.stroke_width,
            "shadow": self.shadow,
            "texture": self.texture,
            "spacing": self.spacing,
            "motion_easing": self.motion_easing,
            "surface_mode": self.surface_mode,
            "background_character": self.background_character,
        }


_BASE = {
    "dark": {
        "background": "#101318",
        "foreground": "#F7F8FA",
        "muted": "#BAC1CC",
        "surface": "#1A1F27",
        "edge": "#3B4554",
    },
    "light": {
        "background": "#F7F3EB",
        "foreground": "#16191D",
        "muted": "#4E5966",
        "surface": "#FFFCF6",
        "edge": "#C9C3B8",
    },
}

# All palette values are fixed, trusted values.  They are intentionally muted
# enough to remain readable on the corresponding base background.  No palette
# defaults to cyan or purple.
_ACCENTS = {
    "dark": {
        "none": "#D6DCE5",
        "signal-red": "#FF8A80",
        "red": "#FF8A80",
        "orange": "#FFB36B",
        "amber": "#FFD166",
        "yellow": "#F4E47A",
        "green": "#8FE3A2",
        "blue": "#9CCBFF",
        "violet": "#C8B6FF",
        "purple": "#D9B8FF",
        "pink": "#F9AFD1",
        "teal": "#7DDED0",
        "earth": "#E8C08D",
        "hard-white": "#FFFFFF",
        "black": "#D6DCE5",
        "white": "#FFFFFF",
        "gray": "#D6DCE5",
        "mono": "#E8EAED",
        "google-blue": "#3B82F6",
        "cyan-glow": "#06B6D4",
        "emerald": "#10B981",
        "coral": "#F43F5E",
        "vivid-teal": "#14B8A6",
        "deepmind-violet": "#8B5CF6",
    },
    "light": {
        "none": "#344054",
        "signal-red": "#B42318",
        "red": "#B42318",
        "orange": "#9A4D00",
        "amber": "#7A4F01",
        "yellow": "#665800",
        "green": "#147A3E",
        "blue": "#185FA5",
        "violet": "#5B3AB5",
        "purple": "#6938A2",
        "pink": "#A61B5B",
        "teal": "#087B70",
        "earth": "#764B22",
        "hard-white": "#2E3642",
        "black": "#20262E",
        "white": "#344054",
        "gray": "#425466",
        "mono": "#2B3038",
        "google-blue": "#1D4ED8",
        "cyan-glow": "#0E7490",
        "emerald": "#047857",
        "coral": "#BE123C",
        "vivid-teal": "#0F766E",
        "deepmind-violet": "#6D28D9",
    },
}

_SURFACES = {
    "solid": {"radius": 0, "opacity": 1.0, "shadow": "none", "texture": "none"},
    "flat": {"radius": 0, "opacity": 1.0, "shadow": "none", "texture": "none"},
    "paper": {"radius": 0, "opacity": 1.0, "shadow": "0 2px 0 rgba(38, 28, 14, 0.12)", "texture": "paper-grain"},
    "ink": {"radius": 0, "opacity": 1.0, "shadow": "none", "texture": "ink-speckle"},
    "technical": {"radius": 2, "opacity": 1.0, "shadow": "0 6px 18px rgba(0, 0, 0, 0.18)", "texture": "technical-grid"},
    "glass": {"radius": 18, "opacity": 0.82, "shadow": "0 14px 36px rgba(0, 0, 0, 0.24)", "texture": "none"},
    "metallic": {"radius": 6, "opacity": 1.0, "shadow": "0 10px 24px rgba(0, 0, 0, 0.24)", "texture": "brushed-metal"},
    "emissive": {"radius": 8, "opacity": 1.0, "shadow": "0 0 22px rgba(255, 255, 255, 0.18)", "texture": "none"},
    "textured": {"radius": 4, "opacity": 1.0, "shadow": "0 6px 18px rgba(0, 0, 0, 0.16)", "texture": "fine-grain"},
    "isometric_cutaway": {"radius": 8, "opacity": 0.95, "shadow": "0 20px 48px rgba(0, 0, 0, 0.28)", "texture": "blueprint-grid"},
    "holographic_projection": {"radius": 14, "opacity": 0.88, "shadow": "0 0 32px rgba(100, 200, 255, 0.35)", "texture": "scanline"},
    "cellular_membrane": {"radius": 24, "opacity": 0.90, "shadow": "0 12px 30px rgba(50, 180, 120, 0.20)", "texture": "organic-glow"},
    "astral_volumetric": {"radius": 16, "opacity": 0.92, "shadow": "0 0 40px rgba(150, 100, 255, 0.40)", "texture": "stardust"},
    "glassmorphism_canvas": {"radius": 20, "opacity": 0.75, "shadow": "0 16px 40px rgba(0, 0, 0, 0.30)", "texture": "glass-blur"},
    "gradient_glass": {"radius": 18, "opacity": 0.80, "shadow": "0 14px 36px rgba(0, 0, 0, 0.25)", "texture": "none"},
    "glossy": {"radius": 12, "opacity": 1.0, "shadow": "0 12px 28px rgba(0, 0, 0, 0.22)", "texture": "specular-gloss"},
    "matte": {"radius": 6, "opacity": 1.0, "shadow": "0 4px 12px rgba(0, 0, 0, 0.12)", "texture": "soft-matte"},
    "frosted_glassmorphism": {"radius": 16, "opacity": 0.75, "shadow": "0 20px 48px rgba(0, 0, 0, 0.32)", "texture": "backdrop-blur"},
    "ambient_glow": {"radius": 16, "opacity": 0.95, "shadow": "0 0 50px rgba(59, 130, 246, 0.25)", "texture": "radial-glow"},
    "clean_dot_grid": {"radius": 12, "opacity": 1.0, "shadow": "0 8px 24px rgba(0, 0, 0, 0.10)", "texture": "dot-grid"},
}

_SURFACE_COLOURS = {
    "dark": {
        "paper": "#2A251D",
        "ink": "#1C2026",
        "technical": "#17202A",
        "glass": "#283442",
        "metallic": "#242931",
        "emissive": "#181B2A",
        "textured": "#22221E",
        "isometric_cutaway": "#131C28",
        "holographic_projection": "#0B1E2E",
        "cellular_membrane": "#0E241B",
        "astral_volumetric": "#110E24",
        "glassmorphism_canvas": "#1E2430",
        "gradient_glass": "#202836",
        "glossy": "#1C212B",
        "matte": "#181C22",
        "frosted_glassmorphism": "#161F30",
        "ambient_glow": "#0F172A",
        "clean_dot_grid": "#111827",
    },
    "light": {
        "paper": "#FFF8E8",
        "ink": "#F5F1E8",
        "technical": "#F2F5F8",
        "glass": "#FCFEFF",
        "metallic": "#EEF0F2",
        "emissive": "#F8F5FF",
        "textured": "#F7F0E3",
        "isometric_cutaway": "#EDF3FA",
        "holographic_projection": "#E8F4FC",
        "cellular_membrane": "#E8F7EE",
        "astral_volumetric": "#F0ECFC",
        "glassmorphism_canvas": "#F4F7FC",
        "gradient_glass": "#F2F6FB",
        "glossy": "#FAFBFD",
        "matte": "#F3F3F5",
        "frosted_glassmorphism": "#FFFFFF",
        "ambient_glow": "#F8FAFC",
        "clean_dot_grid": "#FFFFFF",
    },
}

_FONTS = {
    "technical": ("ui-monospace, monospace", "system-ui, sans-serif", 56, 24),
    "editorial": ("serif", "serif", 60, 25),
    "geometric": ("system-ui, sans-serif", "system-ui, sans-serif", 58, 24),
    "humanist": ("system-ui, sans-serif", "system-ui, sans-serif", 56, 25),
    "display": ("system-ui, sans-serif", "system-ui, sans-serif", 64, 24),
    "monospace": ("ui-monospace, monospace", "ui-monospace, monospace", 54, 23),
    "notebook": ("system-ui, -apple-system, 'Inter', sans-serif", "system-ui, -apple-system, 'Inter', sans-serif", 60, 24),
    "deepmind": ("system-ui, -apple-system, 'Roboto', sans-serif", "system-ui, -apple-system, 'Roboto', sans-serif", 58, 24),
}

_MOTION_EASING = {
    "crisp": "power3.out",
    "flowing": "power2.inOut",
    "technical": "power1.inOut",
    "measured": "sine.inOut",
    "playful": "back.out",
    "cinematic": "power3.inOut",
    "mechanical_assembly": "elastic.out(1, 0.75)",
    "pulse_routing": "power2.inOut",
    "organic_mitosis": "sine.inOut",
    "orbital_gravity": "none",
    "dynamic_ticker": "power4.out",
    "staggered_spring": "back.out(1.7)",
    "smooth_glide": "expo.out",
}


def contrast_ratio(fg: str, bg: str) -> float:
    """Return WCAG contrast ratio for two concrete ``#RRGGBB`` colours."""

    first = _relative_luminance(_rgb(fg))
    second = _relative_luminance(_rgb(bg))
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


def resolve_design_tokens(
    design_bible: DesignBible,
    theme: Any = None,
    *,
    visual_direction: Any = None,
) -> ResolvedDesignTokens:
    """Resolve semantic art direction into deterministic, accessible tokens.

    A trusted application theme may request a valid six-digit background or
    accent.  The request is honoured when readable; otherwise the same trusted
    resolver repairs its contrast.  Design-bible values never carry raw colours.
    """

    theme_mode, theme_background, theme_accent, theme_surface, theme_accent_family = _theme_constraints(theme)
    direction = _direction_constraints(visual_direction)
    if direction.get("mode") and theme_mode is None:
        theme_mode = direction["mode"]
    if direction.get("surface"):
        theme_surface = theme_surface or direction["surface"]
    if direction.get("accent_family"):
        theme_accent_family = theme_accent_family or direction["accent_family"]
    mode = theme_mode or _semantic_mode(design_bible)
    base = _BASE[mode]
    background = theme_background or base["background"]
    foreground = _readable_colour(base["foreground"], background)

    requested_surface = theme_surface or getattr(design_bible, "surface_mode", "solid")
    surface_mode = requested_surface if requested_surface in _SURFACES else "solid"
    surface_recipe = _SURFACES[surface_mode]
    surface = _SURFACE_COLOURS[mode].get(surface_mode, base["surface"])
    if contrast_ratio(foreground, surface) < _MIN_TEXT_CONTRAST:
        surface = "#14181E" if _is_light(foreground) else "#FFFFFF"

    palette = design_bible.palette_intent
    family = theme_accent_family or palette.accent_family
    family = family if family in _ACCENTS[mode] else "gray"
    accent = _readable_colour(theme_accent or _ACCENTS[mode][family], background, surface)
    secondary_family = palette.secondary_family if palette.secondary_family in _ACCENTS[mode] else "gray"
    secondary = _readable_colour(_ACCENTS[mode][secondary_family], background, surface)
    emphasis = _readable_colour(_mix(accent, foreground, 0.34), background, surface)
    muted = _readable_colour(base["muted"], background, surface)
    edge = _mix(surface, foreground, 0.24)

    heading_font_stack, body_font_stack, heading_size, body_size = _FONTS.get(
        design_bible.typography_character,
        _FONTS["geometric"],
    )
    spacing = 28 if design_bible.shape_language in {"organic", "handdrawn"} else 24
    stroke_width = 3 if design_bible.shape_language in {"handdrawn", "diagrammatic"} else 2

    tokens = ResolvedDesignTokens(
        background=background,
        foreground=foreground,
        muted=muted,
        accent=accent,
        secondary=secondary,
        emphasis=emphasis,
        surface=surface,
        edge=edge,
        surface_opacity=float(surface_recipe["opacity"]),
        heading_font_stack=heading_font_stack,
        body_font_stack=body_font_stack,
        heading_size=heading_size,
        body_size=body_size,
        radius=int(surface_recipe["radius"]),
        stroke_width=stroke_width,
        shadow=str(surface_recipe["shadow"]),
        texture=str(surface_recipe["texture"]),
        spacing=spacing,
        motion_easing=_MOTION_EASING.get(design_bible.motion_character, _MOTION_EASING["crisp"]),
        surface_mode=surface_mode,
        background_character=design_bible.background_character,
    )
    _assert_accessible(tokens)
    return tokens


_THEME_PRESETS: dict[str, dict[str, str]] = {
    "paper": {"mode": "light", "surface": "paper", "accent_family": "earth"},
    "botanical": {"mode": "light", "surface": "paper", "accent_family": "green"},
    "organic": {"mode": "light", "surface": "textured", "accent_family": "green"},
    "industrial": {"mode": "dark", "surface": "metallic", "accent_family": "orange"},
    "cinematic": {"mode": "dark", "surface": "solid", "accent_family": "amber"},
    "editorial": {"mode": "light", "surface": "ink", "accent_family": "red"},
    "technical": {"mode": "dark", "surface": "technical", "accent_family": "blue"},
    "minimal": {"mode": "light", "surface": "flat", "accent_family": "black"},
    "notebook-dark": {"mode": "dark", "surface": "frosted_glassmorphism", "accent_family": "google-blue"},
    "notebook-light": {"mode": "light", "surface": "clean_dot_grid", "accent_family": "google-blue"},
    "deepmind": {"mode": "dark", "surface": "ambient_glow", "accent_family": "vivid-teal"},
}


def _theme_constraints(theme: Any) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    if isinstance(theme, str):
        name = theme.strip().lower()
        preset = _THEME_PRESETS.get(name, {})
        mode = name if name in _BASE else preset.get("mode")
        return (mode, None, None, preset.get("surface"), preset.get("accent_family"))
    if not isinstance(theme, Mapping):
        return None, None, None, None, None
    name = str(theme.get("name") or theme.get("preference") or "").strip().lower()
    preset = _THEME_PRESETS.get(name, {})
    raw_mode = theme.get("mode")
    mode = raw_mode.strip().lower() if isinstance(raw_mode, str) else preset.get("mode")
    raw_background = theme.get("bg")
    raw_accent = theme.get("accent")
    background = _normalise_hex(raw_background) if isinstance(raw_background, str) else None
    accent = _normalise_hex(raw_accent) if isinstance(raw_accent, str) else None
    if mode not in _BASE:
        mode = "light" if background and _relative_luminance(_rgb(background)) >= 0.5 else None
    raw_surface = theme.get("surface") or theme.get("surface_mode")
    surface = str(raw_surface).strip().lower() if isinstance(raw_surface, str) else preset.get("surface")
    if surface not in _SURFACES:
        surface = None
    raw_family = theme.get("accent_family") or theme.get("palette")
    accent_family = str(raw_family).strip().lower() if isinstance(raw_family, str) else preset.get("accent_family")
    if accent_family not in {key for values in _ACCENTS.values() for key in values}:
        accent_family = None
    return mode, background, accent, surface, accent_family


def _direction_constraints(value: Any) -> dict[str, str]:
    """Map free-form direction to bounded trusted style semantics."""

    text = " ".join(str(value or "").casefold().split())
    if not text:
        return {}
    mappings = (
        (("notebook", "clean notebook", "google paper", "educational"), {"mode": "light", "surface": "clean_dot_grid", "accent_family": "google-blue"}),
        (("deepmind", "obsidian", "ai research", "world class"), {"mode": "dark", "surface": "ambient_glow", "accent_family": "vivid-teal"}),
        (("paper", "scientific", "print", "botanical"), {"mode": "light", "surface": "paper", "accent_family": "earth"}),
        (("organic", "garden", "natural"), {"mode": "light", "surface": "textured", "accent_family": "green"}),
        (("industrial", "cinematic", "machine", "metal"), {"mode": "dark", "surface": "metallic", "accent_family": "orange"}),
        (("editorial", "black white red", "hard black"), {"mode": "light", "surface": "ink", "accent_family": "red"}),
        (("technical", "schematic", "minimal technical"), {"mode": "dark", "surface": "technical", "accent_family": "blue"}),
    )
    for words, preset in mappings:
        if any(word in text for word in words):
            return dict(preset)
    return {}


def _semantic_mode(design_bible: DesignBible) -> str:
    if design_bible.surface_mode in {"paper", "ink"}:
        return "light"
    if design_bible.palette_intent.dominant in {"near-white", "cream", "paper"}:
        return "light"
    return "dark"


def _normalise_hex(value: str) -> str | None:
    if not _HEX.fullmatch(value.strip()):
        return None
    return value.strip().upper()


def _rgb(value: str) -> tuple[int, int, int]:
    normalised = _normalise_hex(value)
    if normalised is None:
        raise ValueError("colour must be a #RRGGBB value")
    return tuple(int(normalised[index : index + 2], 16) for index in (1, 3, 5))


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        unit = value / 255
        return unit / 12.92 if unit <= 0.04045 else ((unit + 0.055) / 1.055) ** 2.4

    red, green, blue = (channel(value) for value in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _mix(first: str, second: str, amount: float) -> str:
    amount = max(0.0, min(1.0, amount))
    one = _rgb(first)
    two = _rgb(second)
    mixed = tuple(round(left + (right - left) * amount) for left, right in zip(one, two))
    return "#{:02X}{:02X}{:02X}".format(*mixed)


def _readable_colour(colour: str, *backgrounds: str) -> str:
    """Keep a requested trusted colour when possible, otherwise repair it."""

    candidate = _normalise_hex(colour) or "#344054"
    if _meets_contrast(candidate, backgrounds):
        return candidate

    candidates: list[tuple[float, str]] = []
    for target in ("#000000", "#FFFFFF"):
        for step in range(1, 101):
            repaired = _mix(candidate, target, step / 100)
            if _meets_contrast(repaired, backgrounds):
                candidates.append((step / 100, repaired))
                break
    if candidates:
        return min(candidates, key=lambda item: item[0])[1]
    return max(("#000000", "#FFFFFF"), key=lambda item: min(contrast_ratio(item, bg) for bg in backgrounds))


def _meets_contrast(colour: str, backgrounds: tuple[str, ...]) -> bool:
    return bool(backgrounds) and all(contrast_ratio(colour, background) >= _MIN_TEXT_CONTRAST for background in backgrounds)


def _is_light(colour: str) -> bool:
    return _relative_luminance(_rgb(colour)) >= 0.5


def _assert_accessible(tokens: ResolvedDesignTokens) -> None:
    for name in ("foreground", "muted", "accent", "secondary", "emphasis"):
        colour = getattr(tokens, name)
        if contrast_ratio(colour, tokens.background) < _MIN_TEXT_CONTRAST:
            raise AssertionError(f"{name} does not meet background contrast")
        if contrast_ratio(colour, tokens.surface) < _MIN_TEXT_CONTRAST:
            raise AssertionError(f"{name} does not meet surface contrast")


__all__ = ["ResolvedDesignTokens", "contrast_ratio", "resolve_design_tokens"]

"""Style translation: ArtDirectionGenome → Manim visual constants.

Converts the V3 art direction system (color palettes, typography families,
visual families) into concrete Manim color/font/spacing constants that
the scene generator uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from manim import (
    BLUE, GREEN, RED, YELLOW, WHITE, GREY, BLACK,
    ORANGE, PURPLE, TEAL, MAROON, GOLD, PINK,
    BLUE_A, BLUE_B, BLUE_C, BLUE_D, BLUE_E,
    GREEN_A, GREEN_B, GREEN_C, GREEN_D, GREEN_E,
    RED_A, RED_B, RED_C, RED_D, RED_E,
    GREY_A, GREY_B, GREY_C, GREY_D, GREY_E,
    TEAL_A, TEAL_B, TEAL_C, TEAL_D, TEAL_E,
    ManimColor,
)


@dataclass
class ManimStyle:
    """Concrete Manim style constants for a single video."""

    # Core palette
    background_color: str = "#0f172a"       # Dark slate
    primary_color: str = "#3b82f6"          # Blue
    secondary_color: str = "#10b981"        # Emerald
    accent_color: str = "#f59e0b"           # Amber
    text_color: str = "#f1f5f9"             # Light slate
    muted_color: str = "#64748b"            # Slate-400
    error_color: str = "#ef4444"            # Red
    success_color: str = "#22c55e"          # Green

    # Extended palette for charts/diagrams (up to 8 distinct colors)
    chart_colors: List[str] = field(default_factory=lambda: [
        "#3b82f6", "#10b981", "#f59e0b", "#ef4444",
        "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16",
    ])

    # Typography
    title_font: str = "sans-serif"
    body_font: str = "sans-serif"
    code_font: str = "Courier"
    title_size: float = 48.0
    heading_size: float = 36.0
    body_size: float = 24.0
    caption_size: float = 18.0

    # Scene dimensions
    scene_width: float = 14.2     # Manim units (default frame width)
    scene_height: float = 8.0     # Manim units (default frame height)

    # Animation timing
    default_write_speed: float = 0.8      # seconds for Write animation
    default_fade_speed: float = 0.5       # seconds for FadeIn/FadeOut
    default_transform_speed: float = 1.0  # seconds for Transform
    scene_transition_time: float = 0.3    # seconds between scenes
    scene_hold_time: float = 1.5          # seconds to hold after animation


# --------------------------------------------------------------------------- #
# Visual family presets                                                       #
# --------------------------------------------------------------------------- #

VISUAL_FAMILY_PRESETS: Dict[str, Dict[str, str]] = {
    "technical_blueprint": {
        "background_color": "#0a1628",
        "primary_color": "#38bdf8",
        "secondary_color": "#22d3ee",
        "accent_color": "#f97316",
        "text_color": "#e2e8f0",
        "muted_color": "#475569",
    },
    "warm_editorial": {
        "background_color": "#1c1917",
        "primary_color": "#fb923c",
        "secondary_color": "#fbbf24",
        "accent_color": "#f43f5e",
        "text_color": "#fafaf9",
        "muted_color": "#78716c",
    },
    "clinical_scientific": {
        "background_color": "#0c1222",
        "primary_color": "#6366f1",
        "secondary_color": "#a78bfa",
        "accent_color": "#14b8a6",
        "text_color": "#e0e7ff",
        "muted_color": "#6b7280",
    },
    "nature_organic": {
        "background_color": "#0f1f0f",
        "primary_color": "#22c55e",
        "secondary_color": "#86efac",
        "accent_color": "#eab308",
        "text_color": "#dcfce7",
        "muted_color": "#6b7280",
    },
    "corporate_modern": {
        "background_color": "#111827",
        "primary_color": "#3b82f6",
        "secondary_color": "#60a5fa",
        "accent_color": "#f59e0b",
        "text_color": "#f9fafb",
        "muted_color": "#9ca3af",
    },
    "cyberpunk_neon": {
        "background_color": "#0a0a1a",
        "primary_color": "#e11d48",
        "secondary_color": "#c026d3",
        "accent_color": "#22d3ee",
        "text_color": "#fce7f3",
        "muted_color": "#6b7280",
    },
    "minimalist_mono": {
        "background_color": "#18181b",
        "primary_color": "#fafafa",
        "secondary_color": "#a1a1aa",
        "accent_color": "#3b82f6",
        "text_color": "#f4f4f5",
        "muted_color": "#71717a",
    },
    "retro_vintage": {
        "background_color": "#1a1207",
        "primary_color": "#d97706",
        "secondary_color": "#b45309",
        "accent_color": "#dc2626",
        "text_color": "#fef3c7",
        "muted_color": "#92400e",
    },
    "ocean_depth": {
        "background_color": "#0c1526",
        "primary_color": "#0ea5e9",
        "secondary_color": "#06b6d4",
        "accent_color": "#f97316",
        "text_color": "#e0f2fe",
        "muted_color": "#0369a1",
    },
}


def resolve_style(
    genome: Optional[object] = None,
    visual_family: str = "corporate_modern",
) -> ManimStyle:
    """Convert an ArtDirectionGenome (or defaults) into ManimStyle constants."""
    style = ManimStyle()

    # Apply visual family preset
    preset = VISUAL_FAMILY_PRESETS.get(visual_family, VISUAL_FAMILY_PRESETS["corporate_modern"])
    for key, value in preset.items():
        if hasattr(style, key):
            setattr(style, key, value)

    # Override from genome if available
    if genome is not None:
        palette = getattr(genome, "palette", None)
        if palette:
            if hasattr(palette, "background") and palette.background:
                style.background_color = palette.background
            if hasattr(palette, "primary") and palette.primary:
                style.primary_color = palette.primary
            if hasattr(palette, "secondary") and palette.secondary:
                style.secondary_color = palette.secondary
            if hasattr(palette, "accent") and palette.accent:
                style.accent_color = palette.accent
            if hasattr(palette, "text") and palette.text:
                style.text_color = palette.text

        typography = getattr(genome, "typography", None)
        if typography:
            if hasattr(typography, "heading_family") and typography.heading_family:
                style.title_font = typography.heading_family
            if hasattr(typography, "body_family") and typography.body_family:
                style.body_font = typography.body_family

        family = getattr(genome, "visual_family", None)
        if family and family in VISUAL_FAMILY_PRESETS:
            preset2 = VISUAL_FAMILY_PRESETS[family]
            for key, value in preset2.items():
                if hasattr(style, key):
                    setattr(style, key, value)

    return style

"""Focused tests for the deterministic Video Flow Visual V2 style engine."""

from __future__ import annotations

import re

import pytest

from voice_flow.video_flow_engine.style_engine_v2 import contrast_ratio, resolve_design_tokens
from voice_flow.video_flow_engine.visual_plan_v2 import DesignBible, PaletteIntent


_HEX = re.compile(r"^#[0-9A-F]{6}$")


def _bible(
    *,
    surface_mode: str = "technical",
    dominant: str = "near-black",
    accent_family: str = "signal-red",
    secondary_family: str = "hard-white",
    typography: str = "technical",
    shape: str = "diagrammatic",
    background: str = "grid",
    motion: str = "technical",
) -> DesignBible:
    return DesignBible(
        visual_character="industrial technical systems",
        surface_mode=surface_mode,
        palette_intent=PaletteIntent(
            dominant=dominant,
            contrast="very-high",
            accent_family=accent_family,
            secondary_family=secondary_family,
            temperature="neutral",
            saturation="selective",
        ),
        typography_character=typography,
        shape_language=shape,
        background_character=background,
        motion_character=motion,
        transition_character="fade",
        camera_character="focus",
        caption_integration="reserved-bottom",
    )


def test_resolution_is_deterministic_and_to_dict_is_stable() -> None:
    first = resolve_design_tokens(_bible(), theme={"mode": "dark"})
    second = resolve_design_tokens(_bible(), theme={"mode": "dark"})

    assert first == second
    assert first.to_dict() == second.to_dict()


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_all_resolved_colours_are_valid_and_text_is_accessible(mode: str) -> None:
    tokens = resolve_design_tokens(_bible(), theme={"mode": mode})

    for name in ("background", "foreground", "muted", "accent", "secondary", "emphasis", "surface", "edge"):
        assert _HEX.fullmatch(getattr(tokens, name))
    for name in ("foreground", "muted", "accent", "secondary", "emphasis"):
        assert contrast_ratio(getattr(tokens, name), tokens.background) >= 4.5
        assert contrast_ratio(getattr(tokens, name), tokens.surface) >= 4.5


@pytest.mark.parametrize(
    ("family", "expected"),
    [
        ("signal-red", "#B42318"),
        ("green", "#147A3E"),
        ("earth", "#764B22"),
    ],
)
def test_semantic_palette_family_selects_fixed_light_tokens(family: str, expected: str) -> None:
    tokens = resolve_design_tokens(_bible(accent_family=family), theme={"mode": "light"})

    assert tokens.accent == expected


def test_secondary_palette_family_is_resolved_independently() -> None:
    tokens = resolve_design_tokens(_bible(accent_family="signal-red", secondary_family="green"), theme="light")

    assert tokens.accent == "#B42318"
    assert tokens.secondary == "#147A3E"


@pytest.mark.parametrize("surface_mode", ["solid", "flat", "paper", "ink", "technical"])
def test_non_glass_surface_modes_are_opaque_and_not_glass(surface_mode: str) -> None:
    tokens = resolve_design_tokens(_bible(surface_mode=surface_mode))

    assert tokens.surface_mode == surface_mode
    assert tokens.surface_opacity == 1.0
    assert tokens.radius != 18


def test_paper_is_light_and_not_dark_glass_by_default() -> None:
    tokens = resolve_design_tokens(_bible(surface_mode="paper", dominant="paper"))

    assert contrast_ratio(tokens.foreground, tokens.background) >= 4.5
    assert tokens.surface_opacity == 1.0
    assert tokens.background != "#101318"
    assert tokens.texture == "paper-grain"


def test_explicit_dark_theme_can_constrain_paper_mode() -> None:
    tokens = resolve_design_tokens(_bible(surface_mode="paper", dominant="paper"), theme={"mode": "dark"})

    assert tokens.background == "#101318"
    assert tokens.surface_opacity == 1.0


def test_glass_remains_available_with_controlled_opacity() -> None:
    tokens = resolve_design_tokens(_bible(surface_mode="glass"), theme={"mode": "dark"})

    assert tokens.surface_mode == "glass"
    assert tokens.surface_opacity == pytest.approx(0.82)
    assert tokens.radius == 18


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_theme_mode_remains_compatible(mode: str) -> None:
    tokens = resolve_design_tokens(_bible(), theme=mode)

    expected_background = "#F7F3EB" if mode == "light" else "#101318"
    assert tokens.background == expected_background


def test_valid_trusted_theme_colours_are_honoured_when_readable() -> None:
    theme = {"mode": "light", "bg": "#F4F0E6", "accent": "#B42318"}

    tokens = resolve_design_tokens(_bible(), theme=theme)

    assert tokens.background == "#F4F0E6"
    assert tokens.accent == "#B42318"


def test_valid_trusted_theme_colour_is_repaired_when_it_is_not_readable() -> None:
    tokens = resolve_design_tokens(_bible(), theme={"mode": "light", "bg": "#FFFFFF", "accent": "#FFFFFF"})

    assert tokens.background == "#FFFFFF"
    assert tokens.accent != "#FFFFFF"
    assert contrast_ratio(tokens.accent, tokens.background) >= 4.5


def test_invalid_theme_colours_are_ignored() -> None:
    baseline = resolve_design_tokens(_bible(), theme={"mode": "light"})
    invalid = resolve_design_tokens(
        _bible(),
        theme={"mode": "light", "bg": "not-a-colour", "accent": "#12FG00"},
    )

    assert invalid == baseline


def test_default_palette_never_forces_cyan_or_purple() -> None:
    tokens = resolve_design_tokens(_bible(accent_family="signal-red"))

    assert tokens.accent == "#FF8A80"
    assert tokens.secondary != "#7DDED0"
    assert tokens.secondary != "#D9B8FF"


def test_contrast_ratio_rejects_non_concrete_colours() -> None:
    with pytest.raises(ValueError):
        contrast_ratio("rgb(0, 0, 0)", "#FFFFFF")

"""Art Direction Genome Builder, Validator, and Seeded Variation Engine.

Consumes VisualFamilySpec definitions and produces canonical ArtDirectionGenome objects
(from voice_flow.video_flow_v3.contracts) while enforcing strict Anti-Generic AI Policies
and deterministic, seeded variation.
"""

from __future__ import annotations

import colorsys
import hashlib
import random
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from voice_flow.video_flow_v3.contracts import ArtDirectionGenome
except ImportError:
    from ..contracts import ArtDirectionGenome

from voice_flow.video_flow_v3.art_direction.families import (
    VisualFamilySpec,
    get_visual_family_spec,
)


# -----------------------------------------------------------------------------
# Anti-Generic AI Policy Constants & Color Utilities
# -----------------------------------------------------------------------------

FORBIDDEN_NEON_BACKGROUNDS = {
    "#FF00FF", "#00FFFF", "#7B00FF", "#A000FF", "#00E5FF", "#FF007F"
}


def hex_to_rgb(hex_str: str) -> Tuple[float, float, float]:
    """Convert hex string (#RRGGBB or #RGB) to normalized float RGB tuple in 0..1."""
    hex_clean = hex_str.lstrip("#")
    if len(hex_clean) == 3:
        hex_clean = "".join([c * 2 for c in hex_clean])
    if len(hex_clean) != 6:
        return (0.5, 0.5, 0.5)
    r = int(hex_clean[0:2], 16) / 255.0
    g = int(hex_clean[2:4], 16) / 255.0
    b = int(hex_clean[4:6], 16) / 255.0
    return (r, g, b)


def rgb_to_hex(rgb: Tuple[float, float, float]) -> str:
    """Convert normalized float RGB tuple in 0..1 to hex string #RRGGBB."""
    r = max(0, min(255, int(round(rgb[0] * 255.0))))
    g = max(0, min(255, int(round(rgb[1] * 255.0))))
    b = max(0, min(255, int(round(rgb[2] * 255.0))))
    return f"#{r:02X}{g:02X}{b:02X}"


def adjust_color_hsl(
    hex_color: str,
    delta_hue_deg: float = 0.0,
    delta_sat: float = 0.0,
    delta_lum: float = 0.0,
) -> str:
    """Deterministically shift a hex color in HSL space while constraining bounds."""
    r, g, b = hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r, g, b)  # Note: Python uses HLS

    # Shift hue in degrees (0..360)
    h_new = ((h * 360.0) + delta_hue_deg) % 360.0 / 360.0
    s_new = max(0.0, min(1.0, s + delta_sat))
    l_new = max(0.0, min(1.0, l + delta_lum))

    r_new, g_new, b_new = colorsys.hls_to_rgb(h_new, l_new, s_new)
    return rgb_to_hex((r_new, g_new, b_new))


def is_neon_color(hex_color: str) -> bool:
    """Check if color violates anti-generic policy (e.g. super-saturated neon purple/cyan)."""
    if hex_color.upper() in FORBIDDEN_NEON_BACKGROUNDS:
        return True
    r, g, b = hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    h_deg = h * 360.0
    # Saturation > 0.85 and Lightness between 0.35 and 0.65 in cyan (170-195 deg) or purple/magenta (270-315 deg)
    if s > 0.85 and 0.35 <= l <= 0.65:
        if (170.0 <= h_deg <= 195.0) or (270.0 <= h_deg <= 315.0):
            return True
    return False


# -----------------------------------------------------------------------------
# Anti-Generic Policy Enforcement & Validation
# -----------------------------------------------------------------------------

def enforce_anti_generic_policy(
    materials_dict: Dict[str, Any],
    palette_dict: Dict[str, str],
    default_env_color: str = "#0F172A"
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Enforces Anti-Generic AI Policy rules on materials and palette dicts."""
    sanitized_materials = dict(materials_dict)
    # Strictly disable bloom, lens flare, depth-of-field, glassmorphism
    sanitized_materials["bloom_enabled"] = False
    sanitized_materials["lens_flare"] = False
    sanitized_materials["dof_enabled"] = False
    sanitized_materials["glassmorphism"] = False

    sanitized_palette = dict(palette_dict)
    env_color = sanitized_palette.get("environment", "#000000")
    if is_neon_color(env_color):
        sanitized_palette["environment"] = default_env_color

    return sanitized_materials, sanitized_palette


def validate_art_genome(genome: ArtDirectionGenome) -> bool:
    """Validates an ArtDirectionGenome against schema invariants and anti-generic policies."""
    if not genome.family:
        return False

    materials = genome.materials or {}
    if materials.get("bloom_enabled", False):
        return False
    if materials.get("lens_flare", False):
        return False
    if materials.get("dof_enabled", False):
        return False
    if materials.get("glassmorphism", False):
        return False

    palette = genome.palette or {}
    required_roles = ["environment", "structural_neutral", "primary_info", "accent", "highlight"]
    for role in required_roles:
        if role not in palette:
            return False

    if is_neon_color(palette.get("environment", "")):
        return False

    return True


# -----------------------------------------------------------------------------
# Genome Construction & Seeded Variation
# -----------------------------------------------------------------------------

def derive_seed_int(source_hash: str) -> int:
    """Convert source_hash string deterministically into a 32-bit integer seed."""
    if not source_hash:
        return 42
    digest = hashlib.sha256(source_hash.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def build_genome_from_family(
    family_spec: VisualFamilySpec,
    source_hash: str = "",
    enable_variation: bool = True,
) -> ArtDirectionGenome:
    """Builds a hydrated, validated ArtDirectionGenome from a VisualFamilySpec.

    If source_hash is provided and enable_variation is True, applies subtle
    seeded micro-variations to palette, materials, and density rules without
    violating family boundaries or anti-generic constraints.
    """
    palette_dict = family_spec.palette.to_dict()
    typography_dict = family_spec.typography.to_dict()
    materials_dict = family_spec.materials.to_dict()
    density_rules = dict(family_spec.density_rules)
    budget = family_spec.visual_intensity_budget

    if source_hash and enable_variation:
        seed = derive_seed_int(source_hash)
        rng = random.Random(seed)

        # Micro-variation in accent and highlight colors (+/- 4 degrees hue, +/- 2% sat/lum)
        delta_h = rng.uniform(-4.0, 4.0)
        delta_s = rng.uniform(-0.02, 0.02)
        delta_l = rng.uniform(-0.02, 0.02)

        if "accent" in palette_dict:
            palette_dict["accent"] = adjust_color_hsl(
                palette_dict["accent"], delta_h, delta_s, delta_l
            )
        if "highlight" in palette_dict:
            palette_dict["highlight"] = adjust_color_hsl(
                palette_dict["highlight"], -delta_h * 0.5, delta_s, delta_l
            )

        # Material roughness micro-adjustment (+/- 0.03)
        if "roughness" in materials_dict:
            base_roughness = materials_dict["roughness"]
            materials_dict["roughness"] = round(
                max(0.0, min(1.0, base_roughness + rng.uniform(-0.03, 0.03))), 3
            )

        # Density rule micro-adjustments
        if "element_padding_px" in density_rules:
            pad = density_rules["element_padding_px"]
            density_rules["element_padding_px"] = max(8, pad + rng.randint(-2, 2))

        # Intensity budget micro-adjustment (+/- 3 points)
        budget = max(50, min(100, budget + rng.randint(-3, 3)))

    # Strictly enforce Anti-Generic AI Policy
    materials_dict, palette_dict = enforce_anti_generic_policy(
        materials_dict, palette_dict, default_env_color=family_spec.palette.environment
    )

    genome = ArtDirectionGenome(
        family=family_spec.name,
        palette=palette_dict,
        typography=typography_dict,
        materials=materials_dict,
        lighting_rig=family_spec.lighting_rig.name,
        camera_grammar=family_spec.camera_grammar.name,
        motion_grammar=family_spec.motion_grammar.name,
        density_rules=density_rules,
        visual_intensity_budget=budget,
    )

    if not validate_art_genome(genome):
        raise ValueError(
            f"Failed to build valid ArtDirectionGenome for family '{family_spec.name}'. "
            "Anti-generic or contract invariants were violated."
        )

    return genome

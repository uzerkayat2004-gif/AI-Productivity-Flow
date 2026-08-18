"""Curated Visual Families for Video Flow V3 Art Direction.

Enforces Anti-Generic AI Policy and defines 9 distinct visual families
with role-based color palettes, typography systems, material specifications,
lighting rigs, camera grammars, and motion grammars.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class VisualFamilyName(str, Enum):
    INDUSTRIAL_PRODUCT = "Industrial Product"
    TECHNICAL_SYSTEMS = "Technical Systems"
    SCIENTIFIC_VISUALIZATION = "Scientific Visualization"
    DATA_EDITORIAL = "Data Editorial"
    EDITORIAL_DOCUMENTARY = "Editorial Documentary"
    SOFTWARE_ARCHITECTURE = "Software Architecture"
    HISTORICAL_ARCHIVAL = "Historical / Archival"
    ARCHITECTURAL_SPATIAL = "Architectural / Spatial"
    MINIMAL_CONCEPTUAL = "Minimal Conceptual"


@dataclass(frozen=True)
class PaletteSpec:
    """Role-based color palette specification."""
    environment: str          # Background / spatial atmosphere
    structural_neutral: str   # Containers, structural framing, neutral nodes
    primary_info: str         # Primary text, key content vectors, main data
    accent: str               # Primary visual focus, active connections
    highlight: str            # Badges, critical indicators, active callouts
    secondary_info: str = "#888888"  # Muted secondary text/lines
    border: str = "#333333"          # Frame borders / dividers

    def to_dict(self) -> Dict[str, str]:
        return {
            "environment": self.environment,
            "structural_neutral": self.structural_neutral,
            "primary_info": self.primary_info,
            "accent": self.accent,
            "highlight": self.highlight,
            "secondary_info": self.secondary_info,
            "border": self.border,
        }


@dataclass(frozen=True)
class TypographySpec:
    """Typography system configuration."""
    font_family_primary: str
    font_family_heading: str
    font_family_mono: str
    font_size_scale: float = 1.2
    heading_weight: int = 700
    body_weight: int = 400
    mono_weight: int = 500
    letter_spacing_heading: str = "-0.02em"
    letter_spacing_body: str = "0em"
    line_height_body: float = 1.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "font_family_primary": self.font_family_primary,
            "font_family_heading": self.font_family_heading,
            "font_family_mono": self.font_family_mono,
            "font_size_scale": self.font_size_scale,
            "heading_weight": self.heading_weight,
            "body_weight": self.body_weight,
            "mono_weight": self.mono_weight,
            "letter_spacing_heading": self.letter_spacing_heading,
            "letter_spacing_body": self.letter_spacing_body,
            "line_height_body": self.line_height_body,
        }


@dataclass(frozen=True)
class MaterialSpec:
    """Material families and PBR visual properties."""
    surface_type: str           # e.g. "matte_metal", "schematic_dielectric", "archival_paper"
    roughness: float            # 0.0 (smooth) to 1.0 (rough)
    metalness: float            # 0.0 (dielectric) to 1.0 (metallic)
    clearcoat: float = 0.0      # Subscribed specular layer
    subsurface: float = 0.0     # Subsurface scattering
    opacity: float = 1.0        # Transparency
    # Anti-Generic AI Policy Flags (MUST BE FALSE)
    bloom_enabled: bool = False
    lens_flare: bool = False
    dof_enabled: bool = False
    glassmorphism: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "surface_type": self.surface_type,
            "roughness": self.roughness,
            "metalness": self.metalness,
            "clearcoat": self.clearcoat,
            "subsurface": self.subsurface,
            "opacity": self.opacity,
            "bloom_enabled": self.bloom_enabled,
            "lens_flare": self.lens_flare,
            "dof_enabled": self.dof_enabled,
            "glassmorphism": self.glassmorphism,
        }


@dataclass(frozen=True)
class LightingRigSpec:
    """Lighting rig configuration."""
    name: str
    key_light_intensity: float
    key_light_color: str
    fill_light_intensity: float
    ambient_light_intensity: float
    shadows_enabled: bool = True
    softness: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "key_light_intensity": self.key_light_intensity,
            "key_light_color": self.key_light_color,
            "fill_light_intensity": self.fill_light_intensity,
            "ambient_light_intensity": self.ambient_light_intensity,
            "shadows_enabled": self.shadows_enabled,
            "softness": self.softness,
        }


@dataclass(frozen=True)
class CameraGrammarSpec:
    """Camera motion and framing parameters."""
    name: str                   # e.g. "HeroFocus", "OrthographicPan", "CinematicTracking"
    projection: str             # "perspective" or "orthographic"
    default_fov: float          # Field of view in degrees (if perspective)
    movement_style: str         # e.g. "damped_pan", "hero_orbit", "planar_scan"
    zoom_speed: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "projection": self.projection,
            "default_fov": self.default_fov,
            "movement_style": self.movement_style,
            "zoom_speed": self.zoom_speed,
        }


@dataclass(frozen=True)
class MotionGrammarSpec:
    """Motion dynamics and animation curves."""
    name: str                   # e.g. "ControlledDeceleration", "LinearStep", "SmoothOrganic"
    easing_preset: str          # e.g. "cubic_bezier(0.16, 1, 0.3, 1)"
    stagger_delay_sec: float    # Delay between sequential reveals
    transition_duration_sec: float # Default scene element transition time
    spring_damping: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "easing_preset": self.easing_preset,
            "stagger_delay_sec": self.stagger_delay_sec,
            "transition_duration_sec": self.transition_duration_sec,
            "spring_damping": self.spring_damping,
        }


@dataclass(frozen=True)
class VisualFamilySpec:
    """Complete specification for a visual family."""
    name: str
    description: str
    palette: PaletteSpec
    typography: TypographySpec
    materials: MaterialSpec
    lighting_rig: LightingRigSpec
    camera_grammar: CameraGrammarSpec
    motion_grammar: MotionGrammarSpec
    density_rules: Dict[str, Any] = field(default_factory=dict)
    visual_intensity_budget: int = 100


# -----------------------------------------------------------------------------
# Curated 9 Visual Families Definitions
# -----------------------------------------------------------------------------

INDUSTRIAL_PRODUCT_FAMILY = VisualFamilySpec(
    name=VisualFamilyName.INDUSTRIAL_PRODUCT.value,
    description="Chassis, precision machined, metallic/matte, amber/copper highlights.",
    palette=PaletteSpec(
        environment="#121417",
        structural_neutral="#2A2E35",
        primary_info="#E6E8EC",
        accent="#E56B00",
        highlight="#FFC700",
        secondary_info="#9CA3AF",
        border="#3F444E",
    ),
    typography=TypographySpec(
        font_family_primary="Inter",
        font_family_heading="Space Grotesk",
        font_family_mono="JetBrains Mono",
        font_size_scale=1.2,
        heading_weight=700,
        body_weight=400,
        mono_weight=500,
    ),
    materials=MaterialSpec(
        surface_type="anodized_aluminum",
        roughness=0.38,
        metalness=0.82,
        clearcoat=0.1,
        subsurface=0.0,
        opacity=1.0,
        bloom_enabled=False,
        lens_flare=False,
        dof_enabled=False,
        glassmorphism=False,
    ),
    lighting_rig=LightingRigSpec(
        name="Technical Studio Key",
        key_light_intensity=1.2,
        key_light_color="#FFFFFF",
        fill_light_intensity=0.4,
        ambient_light_intensity=0.2,
        shadows_enabled=True,
        softness=0.4,
    ),
    camera_grammar=CameraGrammarSpec(
        name="HeroFocus",
        projection="perspective",
        default_fov=45.0,
        movement_style="hero_orbit",
        zoom_speed=1.0,
    ),
    motion_grammar=MotionGrammarSpec(
        name="ControlledDeceleration",
        easing_preset="cubic-bezier(0.16, 1, 0.3, 1)",
        stagger_delay_sec=0.08,
        transition_duration_sec=0.6,
        spring_damping=1.2,
    ),
    density_rules={
        "max_simultaneous_elements": 12,
        "element_padding_px": 24,
        "grid_columns": 12,
        "layout_margin_ratio": 0.08,
    },
    visual_intensity_budget=90,
)

TECHNICAL_SYSTEMS_FAMILY = VisualFamilySpec(
    name=VisualFamilyName.TECHNICAL_SYSTEMS.value,
    description="Cool technical neutrals, signal flow, cyan/emerald accents, monospace.",
    palette=PaletteSpec(
        environment="#0B132B",
        structural_neutral="#1E293B",
        primary_info="#F8FAFC",
        accent="#06B6D4",
        highlight="#10B981",
        secondary_info="#94A3B8",
        border="#334155",
    ),
    typography=TypographySpec(
        font_family_primary="Inter",
        font_family_heading="Fira Code",
        font_family_mono="Fira Code",
        font_size_scale=1.15,
        heading_weight=600,
        body_weight=400,
        mono_weight=500,
    ),
    materials=MaterialSpec(
        surface_type="schematic_dielectric",
        roughness=0.6,
        metalness=0.1,
        clearcoat=0.0,
        subsurface=0.0,
        opacity=1.0,
        bloom_enabled=False,
        lens_flare=False,
        dof_enabled=False,
        glassmorphism=False,
    ),
    lighting_rig=LightingRigSpec(
        name="Technical High Key",
        key_light_intensity=1.0,
        key_light_color="#F1F5F9",
        fill_light_intensity=0.6,
        ambient_light_intensity=0.4,
        shadows_enabled=False,
        softness=0.8,
    ),
    camera_grammar=CameraGrammarSpec(
        name="OrthographicPan",
        projection="orthographic",
        default_fov=30.0,
        movement_style="planar_scan",
        zoom_speed=1.0,
    ),
    motion_grammar=MotionGrammarSpec(
        name="LinearStep",
        easing_preset="cubic-bezier(0.25, 1, 0.5, 1)",
        stagger_delay_sec=0.05,
        transition_duration_sec=0.4,
        spring_damping=1.0,
    ),
    density_rules={
        "max_simultaneous_elements": 20,
        "element_padding_px": 16,
        "grid_columns": 16,
        "layout_margin_ratio": 0.05,
    },
    visual_intensity_budget=80,
)

SCIENTIFIC_VISUALIZATION_FAMILY = VisualFamilySpec(
    name=VisualFamilyName.SCIENTIFIC_VISUALIZATION.value,
    description="Organic structures, neutral scientific palette, layer reveal.",
    palette=PaletteSpec(
        environment="#F8FAFC",
        structural_neutral="#E2E8F0",
        primary_info="#0F172A",
        accent="#2563EB",
        highlight="#10B981",
        secondary_info="#64748B",
        border="#CBD5E1",
    ),
    typography=TypographySpec(
        font_family_primary="Source Sans 3",
        font_family_heading="Source Serif 4",
        font_family_mono="Source Code Pro",
        font_size_scale=1.25,
        heading_weight=700,
        body_weight=400,
        mono_weight=400,
    ),
    materials=MaterialSpec(
        surface_type="diffuse_ceramic",
        roughness=0.35,
        metalness=0.0,
        clearcoat=0.2,
        subsurface=0.15,
        opacity=1.0,
        bloom_enabled=False,
        lens_flare=False,
        dof_enabled=False,
        glassmorphism=False,
    ),
    lighting_rig=LightingRigSpec(
        name="Clinical Diffuse Light",
        key_light_intensity=0.9,
        key_light_color="#FFFFFF",
        fill_light_intensity=0.7,
        ambient_light_intensity=0.5,
        shadows_enabled=True,
        softness=0.9,
    ),
    camera_grammar=CameraGrammarSpec(
        name="MicroscopicInspect",
        projection="perspective",
        default_fov=35.0,
        movement_style="macro_inspect",
        zoom_speed=0.8,
    ),
    motion_grammar=MotionGrammarSpec(
        name="SmoothOrganic",
        easing_preset="cubic-bezier(0.4, 0, 0.2, 1)",
        stagger_delay_sec=0.1,
        transition_duration_sec=0.8,
        spring_damping=1.1,
    ),
    density_rules={
        "max_simultaneous_elements": 10,
        "element_padding_px": 28,
        "grid_columns": 8,
        "layout_margin_ratio": 0.1,
    },
    visual_intensity_budget=85,
)

DATA_EDITORIAL_FAMILY = VisualFamilySpec(
    name=VisualFamilyName.DATA_EDITORIAL.value,
    description="High-contrast quantitative hierarchy, editorial annotations, terracotta/gold.",
    palette=PaletteSpec(
        environment="#FFFBEB",
        structural_neutral="#E7E5E4",
        primary_info="#1C1917",
        accent="#C2410C",
        highlight="#D97706",
        secondary_info="#78716C",
        border="#D6D3D1",
    ),
    typography=TypographySpec(
        font_family_primary="Merriweather",
        font_family_heading="Playfair Display",
        font_family_mono="IBM Plex Mono",
        font_size_scale=1.3,
        heading_weight=800,
        body_weight=400,
        mono_weight=500,
    ),
    materials=MaterialSpec(
        surface_type="newsprint_paper",
        roughness=0.92,
        metalness=0.0,
        clearcoat=0.0,
        subsurface=0.0,
        opacity=1.0,
        bloom_enabled=False,
        lens_flare=False,
        dof_enabled=False,
        glassmorphism=False,
    ),
    lighting_rig=LightingRigSpec(
        name="Flat Print Studio",
        key_light_intensity=1.0,
        key_light_color="#FFFDF7",
        fill_light_intensity=0.8,
        ambient_light_intensity=0.6,
        shadows_enabled=False,
        softness=1.0,
    ),
    camera_grammar=CameraGrammarSpec(
        name="DocumentaryPanZoom",
        projection="perspective",
        default_fov=40.0,
        movement_style="ken_burns",
        zoom_speed=0.6,
    ),
    motion_grammar=MotionGrammarSpec(
        name="EditorialCut",
        easing_preset="cubic-bezier(0, 0, 0.2, 1)",
        stagger_delay_sec=0.12,
        transition_duration_sec=0.5,
        spring_damping=1.0,
    ),
    density_rules={
        "max_simultaneous_elements": 14,
        "element_padding_px": 20,
        "grid_columns": 12,
        "layout_margin_ratio": 0.07,
    },
    visual_intensity_budget=75,
)

EDITORIAL_DOCUMENTARY_FAMILY = VisualFamilySpec(
    name=VisualFamilyName.EDITORIAL_DOCUMENTARY.value,
    description="Archival paper textures, typography, timeline, serif/grotesk.",
    palette=PaletteSpec(
        environment="#141210",
        structural_neutral="#2C2723",
        primary_info="#F5F2EB",
        accent="#D97706",
        highlight="#B91C1C",
        secondary_info="#A8A29E",
        border="#44403C",
    ),
    typography=TypographySpec(
        font_family_primary="Lora",
        font_family_heading="EB Garamond",
        font_family_mono="Courier Prime",
        font_size_scale=1.25,
        heading_weight=700,
        body_weight=400,
        mono_weight=400,
    ),
    materials=MaterialSpec(
        surface_type="archival_paper",
        roughness=0.88,
        metalness=0.1,
        clearcoat=0.0,
        subsurface=0.05,
        opacity=1.0,
        bloom_enabled=False,
        lens_flare=False,
        dof_enabled=False,
        glassmorphism=False,
    ),
    lighting_rig=LightingRigSpec(
        name="Warm Key Directional",
        key_light_intensity=1.1,
        key_light_color="#FFFAF0",
        fill_light_intensity=0.3,
        ambient_light_intensity=0.2,
        shadows_enabled=True,
        softness=0.6,
    ),
    camera_grammar=CameraGrammarSpec(
        name="CinematicTracking",
        projection="perspective",
        default_fov=50.0,
        movement_style="slow_dolly",
        zoom_speed=0.5,
    ),
    motion_grammar=MotionGrammarSpec(
        name="FilmicEase",
        easing_preset="cubic-bezier(0.22, 0.61, 0.36, 1)",
        stagger_delay_sec=0.15,
        transition_duration_sec=0.9,
        spring_damping=1.3,
    ),
    density_rules={
        "max_simultaneous_elements": 8,
        "element_padding_px": 32,
        "grid_columns": 6,
        "layout_margin_ratio": 0.12,
    },
    visual_intensity_budget=70,
)

SOFTWARE_ARCHITECTURE_FAMILY = VisualFamilySpec(
    name=VisualFamilyName.SOFTWARE_ARCHITECTURE.value,
    description="Dark IDE frame, AST syntax colors, bus connectors, purple/cyan.",
    palette=PaletteSpec(
        environment="#0B0F19",
        structural_neutral="#1E293B",
        primary_info="#E2E8F0",
        accent="#8B5CF6",
        highlight="#06B6D4",
        secondary_info="#64748B",
        border="#334155",
    ),
    typography=TypographySpec(
        font_family_primary="Inter",
        font_family_heading="JetBrains Mono",
        font_family_mono="JetBrains Mono",
        font_size_scale=1.2,
        heading_weight=700,
        body_weight=400,
        mono_weight=500,
    ),
    materials=MaterialSpec(
        surface_type="dark_ide_panel",
        roughness=0.5,
        metalness=0.05,
        clearcoat=0.0,
        subsurface=0.0,
        opacity=1.0,
        bloom_enabled=False,
        lens_flare=False,
        dof_enabled=False,
        glassmorphism=False,
    ),
    lighting_rig=LightingRigSpec(
        name="Monolithic Ambient",
        key_light_intensity=1.0,
        key_light_color="#E0E7FF",
        fill_light_intensity=0.5,
        ambient_light_intensity=0.3,
        shadows_enabled=True,
        softness=0.5,
    ),
    camera_grammar=CameraGrammarSpec(
        name="LayerExplosion",
        projection="perspective",
        default_fov=40.0,
        movement_style="axonometric_stack",
        zoom_speed=1.0,
    ),
    motion_grammar=MotionGrammarSpec(
        name="CascadeStagger",
        easing_preset="cubic-bezier(0.34, 1.56, 0.64, 1)",
        stagger_delay_sec=0.06,
        transition_duration_sec=0.45,
        spring_damping=0.9,
    ),
    density_rules={
        "max_simultaneous_elements": 16,
        "element_padding_px": 20,
        "grid_columns": 12,
        "layout_margin_ratio": 0.06,
    },
    visual_intensity_budget=85,
)

HISTORICAL_ARCHIVAL_FAMILY = VisualFamilySpec(
    name=VisualFamilyName.HISTORICAL_ARCHIVAL.value,
    description="Sepia/parchment, document fragments, timeline spine.",
    palette=PaletteSpec(
        environment="#F5F0EB",
        structural_neutral="#D6CCC2",
        primary_info="#2B2D42",
        accent="#8C502E",
        highlight="#9E2A2B",
        secondary_info="#6C757D",
        border="#B8B2A6",
    ),
    typography=TypographySpec(
        font_family_primary="Libre Baskerville",
        font_family_heading="Cinzel",
        font_family_mono="Courier Prime",
        font_size_scale=1.25,
        heading_weight=700,
        body_weight=400,
        mono_weight=400,
    ),
    materials=MaterialSpec(
        surface_type="aged_parchment",
        roughness=0.95,
        metalness=0.05,
        clearcoat=0.0,
        subsurface=0.0,
        opacity=1.0,
        bloom_enabled=False,
        lens_flare=False,
        dof_enabled=False,
        glassmorphism=False,
    ),
    lighting_rig=LightingRigSpec(
        name="Museum Exhibit Spotlight",
        key_light_intensity=1.3,
        key_light_color="#FFF8EE",
        fill_light_intensity=0.3,
        ambient_light_intensity=0.3,
        shadows_enabled=True,
        softness=0.7,
    ),
    camera_grammar=CameraGrammarSpec(
        name="ArtifactInspect",
        projection="orthographic",
        default_fov=30.0,
        movement_style="document_scan",
        zoom_speed=0.7,
    ),
    motion_grammar=MotionGrammarSpec(
        name="DeliberatePause",
        easing_preset="cubic-bezier(0.25, 0.1, 0.25, 1)",
        stagger_delay_sec=0.2,
        transition_duration_sec=1.0,
        spring_damping=1.5,
    ),
    density_rules={
        "max_simultaneous_elements": 6,
        "element_padding_px": 36,
        "grid_columns": 6,
        "layout_margin_ratio": 0.14,
    },
    visual_intensity_budget=65,
)

ARCHITECTURAL_SPATIAL_FAMILY = VisualFamilySpec(
    name=VisualFamilyName.ARCHITECTURAL_SPATIAL.value,
    description="Isometric grid, concrete/glass neutrals, structural callouts.",
    palette=PaletteSpec(
        environment="#1E2022",
        structural_neutral="#373A40",
        primary_info="#EEEEEE",
        accent="#94A3B8",
        highlight="#DC5F00",
        secondary_info="#8D939D",
        border="#4A4E57",
    ),
    typography=TypographySpec(
        font_family_primary="Roboto Flex",
        font_family_heading="Space Grotesk",
        font_family_mono="Roboto Mono",
        font_size_scale=1.2,
        heading_weight=700,
        body_weight=400,
        mono_weight=500,
    ),
    materials=MaterialSpec(
        surface_type="raw_concrete",
        roughness=0.75,
        metalness=0.05,
        clearcoat=0.0,
        subsurface=0.0,
        opacity=1.0,
        bloom_enabled=False,
        lens_flare=False,
        dof_enabled=False,
        glassmorphism=False,
    ),
    lighting_rig=LightingRigSpec(
        name="Sunlight & Shadow",
        key_light_intensity=1.4,
        key_light_color="#FFFFFF",
        fill_light_intensity=0.3,
        ambient_light_intensity=0.25,
        shadows_enabled=True,
        softness=0.3,
    ),
    camera_grammar=CameraGrammarSpec(
        name="AxonometricOrbit",
        projection="orthographic",
        default_fov=35.0,
        movement_style="isometric_orbit",
        zoom_speed=0.9,
    ),
    motion_grammar=MotionGrammarSpec(
        name="ArchitecturalUnfold",
        easing_preset="cubic-bezier(0.19, 1, 0.22, 1)",
        stagger_delay_sec=0.1,
        transition_duration_sec=0.7,
        spring_damping=1.1,
    ),
    density_rules={
        "max_simultaneous_elements": 10,
        "element_padding_px": 24,
        "grid_columns": 12,
        "layout_margin_ratio": 0.09,
    },
    visual_intensity_budget=80,
)

MINIMAL_CONCEPTUAL_FAMILY = VisualFamilySpec(
    name=VisualFamilyName.MINIMAL_CONCEPTUAL.value,
    description="Ultra-clean typography, monochrome, single focal accent.",
    palette=PaletteSpec(
        environment="#FAFAFA",
        structural_neutral="#E0E0E0",
        primary_info="#111111",
        accent="#E63946",
        highlight="#457B9D",
        secondary_info="#666666",
        border="#CCCCCC",
    ),
    typography=TypographySpec(
        font_family_primary="Inter",
        font_family_heading="Inter",
        font_family_mono="Space Mono",
        font_size_scale=1.35,
        heading_weight=900,
        body_weight=400,
        mono_weight=500,
    ),
    materials=MaterialSpec(
        surface_type="pure_vector_matte",
        roughness=1.0,
        metalness=0.0,
        clearcoat=0.0,
        subsurface=0.0,
        opacity=1.0,
        bloom_enabled=False,
        lens_flare=False,
        dof_enabled=False,
        glassmorphism=False,
    ),
    lighting_rig=LightingRigSpec(
        name="Flat Pure Light",
        key_light_intensity=1.0,
        key_light_color="#FFFFFF",
        fill_light_intensity=1.0,
        ambient_light_intensity=1.0,
        shadows_enabled=False,
        softness=1.0,
    ),
    camera_grammar=CameraGrammarSpec(
        name="FixedFrameZoom",
        projection="orthographic",
        default_fov=30.0,
        movement_style="fixed_frame",
        zoom_speed=1.0,
    ),
    motion_grammar=MotionGrammarSpec(
        name="SnappySnap",
        easing_preset="cubic-bezier(0.0, 0.0, 0.2, 1)",
        stagger_delay_sec=0.04,
        transition_duration_sec=0.3,
        spring_damping=0.8,
    ),
    density_rules={
        "max_simultaneous_elements": 6,
        "element_padding_px": 40,
        "grid_columns": 6,
        "layout_margin_ratio": 0.15,
    },
    visual_intensity_budget=60,
)

# Registry mapping family names to specifications
VISUAL_FAMILIES: Dict[str, VisualFamilySpec] = {
    VisualFamilyName.INDUSTRIAL_PRODUCT.value: INDUSTRIAL_PRODUCT_FAMILY,
    VisualFamilyName.TECHNICAL_SYSTEMS.value: TECHNICAL_SYSTEMS_FAMILY,
    VisualFamilyName.SCIENTIFIC_VISUALIZATION.value: SCIENTIFIC_VISUALIZATION_FAMILY,
    VisualFamilyName.DATA_EDITORIAL.value: DATA_EDITORIAL_FAMILY,
    VisualFamilyName.EDITORIAL_DOCUMENTARY.value: EDITORIAL_DOCUMENTARY_FAMILY,
    VisualFamilyName.SOFTWARE_ARCHITECTURE.value: SOFTWARE_ARCHITECTURE_FAMILY,
    VisualFamilyName.HISTORICAL_ARCHIVAL.value: HISTORICAL_ARCHIVAL_FAMILY,
    VisualFamilyName.ARCHITECTURAL_SPATIAL.value: ARCHITECTURAL_SPATIAL_FAMILY,
    VisualFamilyName.MINIMAL_CONCEPTUAL.value: MINIMAL_CONCEPTUAL_FAMILY,
}


def get_visual_family_spec(family_name: str) -> VisualFamilySpec:
    """Retrieve VisualFamilySpec by name, falling back to Technical Systems if unrecognized."""
    if family_name in VISUAL_FAMILIES:
        return VISUAL_FAMILIES[family_name]
    
    # Try normalized lookup (case-insensitive, strip whitespace)
    normalized = family_name.strip().lower()
    for name, spec in VISUAL_FAMILIES.items():
        if name.lower() == normalized:
            return spec
            
    # Default fallback
    return TECHNICAL_SYSTEMS_FAMILY

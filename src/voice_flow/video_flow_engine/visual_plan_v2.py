"""Strict semantic contract for the experimental Video Flow visual planner.

The model describes *what* must be shown.  It never supplies geometry,
rendering code, colours, markup, or renderer-specific configuration.  Those
belong to the trusted V2 compiler introduced in a later phase.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping

from voice_flow.video_flow_contracts import validate_no_executable_code


V2_PLAN_VERSION = "2.0"


class VisualPlanV2Error(ValueError):
    """Raised when an untrusted V2 visual-plan payload is not safe or valid."""


SURFACE_MODES = frozenset(
    {
        "solid",
        "flat",
        "paper",
        "ink",
        "technical",
        "glass",
        "metallic",
        "emissive",
        "textured",
        "isometric_cutaway",
        "holographic_projection",
        "cellular_membrane",
        "astral_volumetric",
        "glassmorphism_canvas",
        "gradient_glass",
        "glossy",
        "matte",
        "frosted_glassmorphism",
        "ambient_glow",
        "clean_dot_grid",
    }
)
OBJECT_TYPES = frozenset(
    {
        "text",
        "label",
        "shape",
        "node",
        "operator",
        "equation",
        "axis",
        "chart",
        "line",
        "arrow",
        "curve",
        "container",
        "wave",
        "particle_group",
        "mesh",
        "light",
        "camera_target",
    }
)
OBJECT_FORMS = frozenset({"auto", "circle", "ellipse", "rectangle", "square", "triangle", "line", "arc", "curve", "bar", "area", "marker"})
OBJECT_ROLES = frozenset({"primary", "secondary", "annotation", "container", "support", "background"})
REGIONS = frozenset(
    {
        "left",
        "center",
        "right",
        "top",
        "bottom",
        "top-third",
        "middle-third",
        "bottom-third",
        "foreground",
        "background",
    }
)
RELATIONSHIPS = frozenset(
    {
        "flows_to",
        "connects_to",
        "contains",
        "causes",
        "increases",
        "decreases",
        "bypasses",
        "depends_on",
        "part_of",
        "transforms_into",
        "compares_with",
        "orbits",
        "supports",
        "feeds",
        "splits_into",
        "merges_into",
        "left_of",
        "right_of",
        "above",
        "below",
        "semantic_connection",
    }
)
ACTIONS = frozenset(
    {
        "create",
        "reveal",
        "draw",
        "trace",
        "move",
        "rotate",
        "scale",
        "morph",
        "replace",
        "split",
        "merge",
        "connect",
        "disconnect",
        "flow",
        "propagate",
        "highlight",
        "dim",
        "measure",
        "focus",
        "zoom",
        "pan",
        "orbit",
    }
)
MAJOR_ACTIONS = frozenset(
    {
        "create",
        "draw",
        "trace",
        "move",
        "rotate",
        "scale",
        "morph",
        "replace",
        "split",
        "merge",
        "connect",
        "disconnect",
        "flow",
        "propagate",
        "measure",
        "zoom",
        "pan",
        "orbit",
    }
)
PHASES = frozenset({"intro", "setup", "build", "explain", "compare", "resolve", "conclude"})
TRANSITIONS = frozenset({"fade", "wipe", "slide", "zoom", "cut"})
CAMERA_INTENTS = frozenset({"static", "focus", "zoom", "pan", "orbit", "dolly", "follow", "crane", "orbit_around", "dolly_in"})
VISUAL_MODES = frozenset(
    {
        "construction",
        "mechanism",
        "diagram",
        "comparison",
        "timeline",
        "chart",
        "spatial",
        "narrative",
        "metaphor",
        "equation",
        "map",
        "data",
        "exploded_isometric",
        "flow_network",
        "biological_simulation",
        "deep_space",
        "financial_canvas",
        "pedagogical_arc",
        "structural_anatomy",
        "dynamic_mechanism",
        "mathematical_synthesis",
    }
)

PALETTE_DOMINANTS = frozenset({"near-black", "near-white", "charcoal", "ink", "cream", "paper", "midnight", "slate"})
PALETTE_FAMILIES = frozenset(
    {"none", "signal-red", "red", "orange", "amber", "yellow", "green", "blue", "violet", "purple", "pink", "teal", "earth", "hard-white", "black", "white", "gray", "mono", "google-blue", "cyan-glow", "emerald", "coral", "vivid-teal", "deepmind-violet"}
)
CONTRASTS = frozenset({"low", "medium", "high", "very-high"})
TEMPERATURES = frozenset({"warm", "neutral", "cool"})
SATURATIONS = frozenset({"muted", "selective", "balanced", "vivid"})
TYPOGRAPHY_CHARACTERS = frozenset({"technical", "editorial", "geometric", "humanist", "display", "monospace", "notebook", "deepmind"})
SHAPE_LANGUAGES = frozenset(
    {
        "geometric",
        "organic",
        "diagrammatic",
        "architectural",
        "handdrawn",
        "minimal",
        "industrial_exploded",
        "circuit_topology",
        "biomimetic_micro",
        "celestial_bodies",
        "algorithmic_fractal",
        "clean_geometric",
        "flowing_curves",
        "pedagogical",
        "minimal_clean",
    }
)
BACKGROUND_CHARACTERS = frozenset(
    {
        "solid",
        "gradient",
        "grid",
        "texture",
        "negative-space",
        "paper",
        "blueprint_grid",
        "dark_fiber_optic",
        "fluid_micro_environment",
        "deep_space_nebula",
        "financial_terminal_dark",
        "mesh_gradient",
        "subtle_particles",
        "dot_grid",
        "radial_glow",
        "soft_gradient",
    }
)
MOTION_CHARACTERS = frozenset(
    {
        "crisp",
        "flowing",
        "technical",
        "measured",
        "playful",
        "cinematic",
        "mechanical_assembly",
        "pulse_routing",
        "organic_mitosis",
        "orbital_gravity",
        "dynamic_ticker",
        "staggered_spring",
        "smooth_glide",
    }
)
CAPTION_INTEGRATIONS = frozenset({"reserved-bottom", "minimal-overlay"})

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_PATHISH = re.compile(r"(?:[A-Za-z]:[\\/]|(?:^|[\s\"'])\.\.?[\\/]|(?:^|[\s\"'])/[A-Za-z0-9_.-]|\\\\)")
_FORBIDDEN_TEXT = (
    "javascript:",
    "data:text/html",
    "<script",
    "</",
    "style=",
    "class=",
    "onload=",
    "onerror=",
    "function(",
    "child_process",
    "__import__",
    "require(",
    "subprocess",
    "os.system",
    "exec(",
    "eval(",
    "three.js",
    "webgl",
    "shader",
    "url(",
    "calc(",
    "position:",
    "font-size",
    "background:",
)


@dataclass(frozen=True)
class PaletteIntent:
    dominant: str
    contrast: str
    accent_family: str
    secondary_family: str
    temperature: str
    saturation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "dominant": self.dominant,
            "contrast": self.contrast,
            "accent_family": self.accent_family,
            "secondary_family": self.secondary_family,
            "temperature": self.temperature,
            "saturation": self.saturation,
        }


@dataclass(frozen=True)
class DesignBible:
    visual_character: str
    surface_mode: str
    palette_intent: PaletteIntent
    typography_character: str
    shape_language: str
    background_character: str
    motion_character: str
    transition_character: str
    camera_character: str
    caption_integration: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "visual_character": self.visual_character,
            "surface_mode": self.surface_mode,
            "palette_intent": self.palette_intent.to_dict(),
            "typography_character": self.typography_character,
            "shape_language": self.shape_language,
            "background_character": self.background_character,
            "motion_character": self.motion_character,
            "transition_character": self.transition_character,
            "camera_character": self.camera_character,
            "caption_integration": self.caption_integration,
        }


@dataclass(frozen=True)
class ObjectSpec:
    id: str
    type: str
    label: str
    role: str
    region: str
    form: str | None = None

    def to_dict(self) -> dict[str, str]:
        result = {"id": self.id, "type": self.type, "label": self.label, "role": self.role, "region": self.region}
        if self.form is not None:
            result["form"] = self.form
        return result


@dataclass(frozen=True)
class RelationshipSpec:
    source: str
    target: str
    kind: str

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "kind": self.kind}


@dataclass(frozen=True)
class AnimationBeat:
    order: int
    phase: str
    action: str
    object_id: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "phase": self.phase,
            "action": self.action,
            "object_id": self.object_id,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ContinuitySpec:
    carry_forward: tuple[str, ...]

    def to_dict(self) -> dict[str, list[str]]:
        return {"carry_forward": list(self.carry_forward)}


@dataclass(frozen=True)
class ScenePlan:
    scene_id: str
    storyboard_section_id: str
    learning_goal: str
    visual_thesis: str
    visual_mode: str
    objects: tuple[ObjectSpec, ...]
    relationships: tuple[RelationshipSpec, ...]
    beats: tuple[AnimationBeat, ...]
    continuity: ContinuitySpec
    camera_intent: str | None = None
    transition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "scene_id": self.scene_id,
            "storyboard_section_id": self.storyboard_section_id,
            "learning_goal": self.learning_goal,
            "visual_thesis": self.visual_thesis,
            "visual_mode": self.visual_mode,
            "objects": [item.to_dict() for item in self.objects],
            "relationships": [item.to_dict() for item in self.relationships],
            "beats": [item.to_dict() for item in self.beats],
            "continuity": self.continuity.to_dict(),
        }
        if self.camera_intent is not None:
            result["camera_intent"] = self.camera_intent
        if self.transition is not None:
            result["transition"] = self.transition
        return result


@dataclass(frozen=True)
class VideoVisualPlanV2:
    version: str
    design_bible: DesignBible
    scenes: tuple[ScenePlan, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "design_bible": self.design_bible.to_dict(),
            "scenes": [scene.to_dict() for scene in self.scenes],
        }


def parse_video_visual_plan_v2(
    payload: Any,
    storyboard: dict[str, Any] | None = None,
) -> VideoVisualPlanV2:
    """Parse a model payload into the safe, compiler-owned V2 plan contract."""
    _validate_model_payload_safety(payload)
    root = _as_mapping(payload, "visual plan")
    _require_keys(root, {"version", "design_bible", "scenes"}, {"version", "design_bible", "scenes"}, "visual plan")

    version = _text(root["version"], "version", maximum=16)
    if version != V2_PLAN_VERSION:
        raise VisualPlanV2Error(f"Unsupported visual-plan version: {version!r}")

    design_bible = _parse_design_bible(root["design_bible"])
    raw_scenes = _as_list(root["scenes"], "scenes", minimum=1, maximum=24)
    scenes = tuple(_parse_scene(item, position) for position, item in enumerate(raw_scenes, start=1))
    _validate_scenes(scenes, storyboard)
    return VideoVisualPlanV2(version=version, design_bible=design_bible, scenes=scenes)


def _parse_design_bible(value: Any) -> DesignBible:
    data = _as_mapping(value, "design_bible")
    required = {
        "visual_character",
        "surface_mode",
        "palette_intent",
        "typography_character",
        "shape_language",
        "background_character",
        "motion_character",
        "transition_character",
        "camera_character",
        "caption_integration",
    }
    _require_keys(data, required, required, "design_bible")
    return DesignBible(
        visual_character=_text(data["visual_character"], "design_bible.visual_character", maximum=80, maximum_words=10),
        surface_mode=_enum(data["surface_mode"], SURFACE_MODES, "design_bible.surface_mode"),
        palette_intent=_parse_palette_intent(data["palette_intent"]),
        typography_character=_enum(data["typography_character"], TYPOGRAPHY_CHARACTERS, "design_bible.typography_character"),
        shape_language=_enum(data["shape_language"], SHAPE_LANGUAGES, "design_bible.shape_language"),
        background_character=_enum(data["background_character"], BACKGROUND_CHARACTERS, "design_bible.background_character"),
        motion_character=_enum(data["motion_character"], MOTION_CHARACTERS, "design_bible.motion_character"),
        transition_character=_enum(data["transition_character"], TRANSITIONS, "design_bible.transition_character"),
        camera_character=_enum(data["camera_character"], CAMERA_INTENTS, "design_bible.camera_character"),
        caption_integration=_enum(data["caption_integration"], CAPTION_INTEGRATIONS, "design_bible.caption_integration"),
    )


def _parse_palette_intent(value: Any) -> PaletteIntent:
    data = _as_mapping(value, "design_bible.palette_intent")
    required = {"dominant", "contrast", "accent_family", "secondary_family", "temperature", "saturation"}
    _require_keys(data, required, required, "design_bible.palette_intent")
    return PaletteIntent(
        dominant=_enum(data["dominant"], PALETTE_DOMINANTS, "design_bible.palette_intent.dominant"),
        contrast=_enum(data["contrast"], CONTRASTS, "design_bible.palette_intent.contrast"),
        accent_family=_enum(data["accent_family"], PALETTE_FAMILIES, "design_bible.palette_intent.accent_family"),
        secondary_family=_enum(data["secondary_family"], PALETTE_FAMILIES, "design_bible.palette_intent.secondary_family"),
        temperature=_enum(data["temperature"], TEMPERATURES, "design_bible.palette_intent.temperature"),
        saturation=_enum(data["saturation"], SATURATIONS, "design_bible.palette_intent.saturation"),
    )


def _parse_scene(value: Any, position: int) -> ScenePlan:
    name = f"scenes[{position - 1}]"
    data = _as_mapping(value, name)
    required = {
        "scene_id",
        "storyboard_section_id",
        "learning_goal",
        "visual_thesis",
        "visual_mode",
        "objects",
        "relationships",
        "beats",
        "continuity",
    }
    allowed = required | {"camera_intent", "transition"}
    _require_keys(data, allowed, required, name)
    objects = tuple(_parse_object(item, f"{name}.objects[{index}]") for index, item in enumerate(_as_list(data["objects"], f"{name}.objects", minimum=1, maximum=16)))
    relationships = tuple(
        _parse_relationship(item, f"{name}.relationships[{index}]")
        for index, item in enumerate(_as_list(data["relationships"], f"{name}.relationships", minimum=0, maximum=32))
    )
    beats = tuple(
        _parse_beat(item, f"{name}.beats[{index}]")
        for index, item in enumerate(_as_list(data["beats"], f"{name}.beats", minimum=1, maximum=64))
    )
    return ScenePlan(
        scene_id=_identifier(data["scene_id"], f"{name}.scene_id"),
        storyboard_section_id=_identifier(data["storyboard_section_id"], f"{name}.storyboard_section_id"),
        learning_goal=_text(data["learning_goal"], f"{name}.learning_goal", maximum=240, maximum_words=36),
        visual_thesis=_text(data["visual_thesis"], f"{name}.visual_thesis", maximum=240, maximum_words=36),
        visual_mode=_enum(data["visual_mode"], VISUAL_MODES, f"{name}.visual_mode"),
        objects=objects,
        relationships=relationships,
        beats=beats,
        continuity=_parse_continuity(data["continuity"], f"{name}.continuity"),
        camera_intent=_optional_enum(data, "camera_intent", CAMERA_INTENTS, name),
        transition=_optional_enum(data, "transition", TRANSITIONS, name),
    )


def _parse_object(value: Any, name: str) -> ObjectSpec:
    data = _as_mapping(value, name)
    required = {"id", "type", "label", "role", "region"}
    _require_keys(data, required | {"form"}, required, name)
    object_type = _enum(data["type"], OBJECT_TYPES, f"{name}.type")
    form = _optional_enum(data, "form", OBJECT_FORMS, name)
    _validate_object_form(object_type, form, name)
    return ObjectSpec(
        id=_identifier(data["id"], f"{name}.id"),
        type=object_type,
        label=_text(data["label"], f"{name}.label", maximum=80, maximum_words=7),
        role=_enum(data["role"], OBJECT_ROLES, f"{name}.role"),
        region=_enum(data["region"], REGIONS, f"{name}.region"),
        form=form,
    )


def _validate_object_form(object_type: str, form: str | None, name: str) -> None:
    if form is None:
        return
    auto_only = {"text", "label", "equation", "operator", "light", "camera_target", "particle_group"}
    if object_type in auto_only:
        allowed = {"auto"}
    elif object_type in {"line", "arrow", "curve", "wave"}:
        allowed = {"auto", "line", "arc", "curve"}
    elif object_type == "axis":
        allowed = {"auto", "line"}
    elif object_type == "chart":
        allowed = {"auto", "bar", "area"}
    elif object_type == "shape":
        allowed = {"auto", "circle", "ellipse", "rectangle", "square", "triangle", "area", "marker"}
    elif object_type in {"node", "container", "mesh"}:
        allowed = {"auto", "circle", "ellipse", "rectangle", "square", "triangle", "marker"}
    else:
        allowed = {"auto"}
    if form not in allowed:
        raise VisualPlanV2Error(f"{name}.form {form!r} is incompatible with object type {object_type!r}")


def _parse_relationship(value: Any, name: str) -> RelationshipSpec:
    data = _as_mapping(value, name)
    required = {"source", "target", "kind"}
    _require_keys(data, required, required, name)
    return RelationshipSpec(
        source=_identifier(data["source"], f"{name}.source"),
        target=_identifier(data["target"], f"{name}.target"),
        kind=_enum(data["kind"], RELATIONSHIPS, f"{name}.kind"),
    )


def _parse_beat(value: Any, name: str) -> AnimationBeat:
    data = _as_mapping(value, name)
    required = {"order", "phase", "action", "object_id", "reason"}
    _require_keys(data, required, required, name)
    order = data["order"]
    if not isinstance(order, int) or isinstance(order, bool) or not 1 <= order <= 64:
        raise VisualPlanV2Error(f"{name}.order must be an integer between 1 and 64")
    action = _enum(data["action"], ACTIONS, f"{name}.action")
    reason = _text(data["reason"], f"{name}.reason", maximum=240, maximum_words=36, allow_empty=action not in MAJOR_ACTIONS)
    return AnimationBeat(
        order=order,
        phase=_enum(data["phase"], PHASES, f"{name}.phase"),
        action=action,
        object_id=_identifier(data["object_id"], f"{name}.object_id"),
        reason=reason,
    )


def _parse_continuity(value: Any, name: str) -> ContinuitySpec:
    data = _as_mapping(value, name)
    _require_keys(data, {"carry_forward"}, {"carry_forward"}, name)
    carried = tuple(_identifier(item, f"{name}.carry_forward[{index}]") for index, item in enumerate(_as_list(data["carry_forward"], f"{name}.carry_forward", minimum=0, maximum=16)))
    if len(set(carried)) != len(carried):
        raise VisualPlanV2Error(f"{name}.carry_forward contains duplicate object IDs")
    return ContinuitySpec(carry_forward=carried)


def _validate_scenes(scenes: tuple[ScenePlan, ...], storyboard: dict[str, Any] | None) -> None:
    scene_ids = [scene.scene_id for scene in scenes]
    if len(set(scene_ids)) != len(scene_ids):
        raise VisualPlanV2Error("Visual plan contains duplicate scene_id values")
    section_ids = [scene.storyboard_section_id for scene in scenes]
    if len(set(section_ids)) != len(section_ids):
        raise VisualPlanV2Error("Visual plan contains duplicate storyboard_section_id values")

    expected_section_ids = _storyboard_section_ids(storyboard)
    if expected_section_ids is not None and section_ids != expected_section_ids:
        raise VisualPlanV2Error("Visual-plan scenes must map one-to-one to storyboard sections in order")

    earlier_object_ids: set[str] = set()
    for scene in scenes:
        local_object_ids = [item.id for item in scene.objects]
        if len(set(local_object_ids)) != len(local_object_ids):
            raise VisualPlanV2Error(f"Scene {scene.scene_id!r} contains duplicate object IDs")
        carried_object_ids = set(scene.continuity.carry_forward)
        if carried_object_ids & set(local_object_ids):
            raise VisualPlanV2Error(f"Scene {scene.scene_id!r} redeclares a carried-forward object ID")
        unknown_continuity = carried_object_ids - earlier_object_ids
        if unknown_continuity:
            raise VisualPlanV2Error(f"Scene {scene.scene_id!r} carries forward objects not defined by an earlier scene")
        available_objects = set(local_object_ids) | carried_object_ids
        relationship_keys: set[tuple[str, str, str]] = set()
        for relationship in scene.relationships:
            if relationship.source not in available_objects or relationship.target not in available_objects:
                raise VisualPlanV2Error(f"Scene {scene.scene_id!r} has a relationship with an unknown object target")
            if relationship.source == relationship.target:
                raise VisualPlanV2Error(f"Scene {scene.scene_id!r} cannot relate an object to itself")
            key = (relationship.source, relationship.target, relationship.kind)
            if key in relationship_keys:
                raise VisualPlanV2Error(f"Scene {scene.scene_id!r} contains duplicate relationships")
            relationship_keys.add(key)
        beat_orders = [beat.order for beat in scene.beats]
        if len(set(beat_orders)) != len(beat_orders) or set(beat_orders) != set(range(1, len(scene.beats) + 1)):
            raise VisualPlanV2Error(f"Scene {scene.scene_id!r} beat orders must be unique and contiguous from 1")
        if any(beat.object_id not in available_objects for beat in scene.beats):
            raise VisualPlanV2Error(f"Scene {scene.scene_id!r} has a beat with an unknown object reference")
        earlier_object_ids.update(local_object_ids)


def _storyboard_section_ids(storyboard: dict[str, Any] | None) -> list[str] | None:
    if storyboard is None:
        return None
    if not isinstance(storyboard, Mapping):
        raise VisualPlanV2Error("storyboard must be an object when supplied")
    sections = storyboard.get("sections")
    if not isinstance(sections, list) or not 1 <= len(sections) <= 24:
        raise VisualPlanV2Error("storyboard.sections must contain between 1 and 24 sections")
    section_ids = []
    for index, section in enumerate(sections):
        if not isinstance(section, Mapping):
            raise VisualPlanV2Error(f"storyboard.sections[{index}] must be an object")
        raw_id = section.get("id")
        section_ids.append(
            f"section_{index + 1}"
            if raw_id is None or (isinstance(raw_id, str) and not raw_id.strip())
            else _identifier(raw_id, f"storyboard.sections[{index}].id")
        )
    if len(set(section_ids)) != len(section_ids):
        raise VisualPlanV2Error("storyboard contains duplicate section IDs")
    return section_ids

def _validate_model_payload_safety(payload: Any) -> None:
    try:
        validate_no_executable_code(payload)
    except (TypeError, ValueError) as exc:
        raise VisualPlanV2Error(str(exc)) from exc

    def visit(value: Any, name: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if not isinstance(key, str):
                    raise VisualPlanV2Error(f"{name} contains a non-string key")
                visit(child, f"{name}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                visit(child, f"{name}[{index}]")
        elif isinstance(value, str):
            _assert_safe_text(value, name)
        elif value is None or isinstance(value, (bool, int, float)):
            return
        else:
            raise VisualPlanV2Error(f"{name} contains an unsupported value type")

    visit(payload, "visual plan")


def _normalized_security_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    chars: list[str] = []
    for char in normalized:
        category = unicodedata.category(char)
        if category == "Cf":
            continue
        chars.append(" " if category.startswith("C") else char)
    return "".join(chars)


def _assert_safe_text(value: str, name: str) -> None:
    normalized = _normalized_security_text(value)
    lowered = normalized.casefold()
    compact = re.sub(r"\s+", "", lowered)
    if "javascript:" in compact or "data:text/html" in compact:
        raise VisualPlanV2Error(f"{name} contains executable or renderer-specific content")
    if any(token in lowered for token in _FORBIDDEN_TEXT):
        raise VisualPlanV2Error(f"{name} contains executable or renderer-specific content")
    if re.search(r"<\s*/?\s*[A-Za-z][^>]*>", normalized):
        raise VisualPlanV2Error(f"{name} contains markup content")
    if re.search(r"\b(?:eval|exec|function|require|__import__)\s*\(", normalized, re.IGNORECASE):
        raise VisualPlanV2Error(f"{name} contains executable content")
    if re.search(r"\bimport\s+(?:os|sys|subprocess|pathlib|shlex|socket|requests?)\b", normalized, re.IGNORECASE):
        raise VisualPlanV2Error(f"{name} contains executable import content")
    if re.search(r"\bos\s*\.\s*system\b|\bprocess\s*\.\s*(?:env|exit|cwd|binding)\b", normalized, re.IGNORECASE):
        raise VisualPlanV2Error(f"{name} contains executable process content")
    if re.search(r"\b(?:style|class|onload|onerror)\s*=", normalized, re.IGNORECASE):
        raise VisualPlanV2Error(f"{name} contains renderer-specific attributes")
    if _HEX_COLOR.search(normalized):
        raise VisualPlanV2Error(f"{name} contains raw colour content")
    if "://" in normalized or _PATHISH.search(normalized):
        raise VisualPlanV2Error(f"{name} contains path-like content")
    if re.search(r"\b(?:rgb|rgba|hsl|hsla)\s*\(", normalized, re.IGNORECASE):
        raise VisualPlanV2Error(f"{name} contains raw colour content")

def _as_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VisualPlanV2Error(f"{name} must be an object")
    return value


def _as_list(value: Any, name: str, *, minimum: int, maximum: int) -> list[Any]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise VisualPlanV2Error(f"{name} must contain between {minimum} and {maximum} items")
    return value


def _require_keys(data: Mapping[str, Any], allowed: set[str], required: set[str], name: str) -> None:
    unknown = set(data) - allowed
    missing = required - set(data)
    if unknown:
        raise VisualPlanV2Error(f"{name} has unsupported keys: {', '.join(sorted(unknown))}")
    if missing:
        raise VisualPlanV2Error(f"{name} is missing required keys: {', '.join(sorted(missing))}")


def _identifier(value: Any, name: str) -> str:
    text = _text(value, name, maximum=64, maximum_words=1)
    if not _IDENTIFIER.fullmatch(text):
        raise VisualPlanV2Error(f"{name} must be an identifier starting with a letter")
    return text


def _enum(value: Any, values: frozenset[str], name: str) -> str:
    text = _text(value, name, maximum=80, maximum_words=2)
    if text not in values:
        raise VisualPlanV2Error(f"{name} must be one of: {', '.join(sorted(values))}")
    return text


def _optional_enum(data: Mapping[str, Any], key: str, values: frozenset[str], name: str) -> str | None:
    if key not in data:
        return None
    return _enum(data[key], values, f"{name}.{key}")


def _text(value: Any, name: str, *, maximum: int, maximum_words: int | None = None, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise VisualPlanV2Error(f"{name} must be a string")
    text = " ".join("".join(char for char in value if unicodedata.category(char) != "Cf").split())
    if not text and not allow_empty:
        raise VisualPlanV2Error(f"{name} must not be empty")
    if len(text) > maximum:
        raise VisualPlanV2Error(f"{name} exceeds {maximum} characters")
    if maximum_words is not None and len(text.split()) > maximum_words:
        raise VisualPlanV2Error(f"{name} exceeds {maximum_words} words")
    _assert_safe_text(text, name)
    return text


__all__ = [
    "ACTIONS",
    "AnimationBeat",
    "ContinuitySpec",
    "DesignBible",
    "ObjectSpec",
    "OBJECT_FORMS",
    "PaletteIntent",
    "RelationshipSpec",
    "ScenePlan",
    "V2_PLAN_VERSION",
    "VideoVisualPlanV2",
    "VisualPlanV2Error",
    "parse_video_visual_plan_v2",
]

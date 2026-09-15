"""Strict, non-executable Visual Scene Program contract for V2.1.

The visual director may describe semantic subjects, relationships, state, and
events.  It may not provide markup, source code, renderer configuration,
filesystem paths, colours, or geometry intended to be executed downstream.
This module turns the bounded JSON payload into immutable dataclasses and
performs all cross-reference and capability checks before a compiler sees it.

The legacy :mod:`visual_plan_v2` parser is intentionally left untouched.  V2.1
has a separate versioned contract so the existing V1/V2 fallback remains safe.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
import unicodedata
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from voice_flow.video_flow_engine.visual_capabilities import (
    CONTENT_INTENTS,
    EVENT_TYPES,
    RELATIONSHIP_TYPES,
    REPRESENTATION_STRATEGIES,
    RENDERER_MODES,
    STRUCTURAL_FAMILIES,
    VISUAL_CAPABILITIES,
    VisualCapabilityError,
    canonical_capability_name,
)


V21_PROGRAM_VERSION = "2.1"
VIDEO_VISUAL_PROGRAM_V21_VERSION = V21_PROGRAM_VERSION

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_PATHISH = re.compile(r"(?:[A-Za-z]:[\\/]|(?:^|\s)[.]{1,2}[\\/]|(?:^|\s)/|\\\\)")
_FORBIDDEN_TEXT = (
    "javascript",
    "data:text",
    "data:application",
    "<script",
    "</script",
    "<iframe",
    "onerror",
    "onload",
    "onclick",
    "child_process",
    "subprocess",
    "os.system",
    "powershell",
    "cmd.exe",
    "shell=true",
    "__import__",
    "import os",
    "import sys",
    "eval(",
    "exec(",
    "function(",
    "require(",
    "file://",
    "url(",
    "<style",
    "style=",
    "class=",
)
_SAFE_TEXT_CONTROL = {"\n", "\r", "\t"}
# State and event parameters are semantic only.  Renderer-owned coordinates,
# dimensions, transforms, markup, and raw renderer configuration are rejected
# recursively even when nested several levels below initial_state.parameters.
_RENDERER_STATE_KEYS = frozenset(
    {
        "position", "rotation", "scale", "x", "y", "z", "coordinates", "coordinate",
        "pixel", "pixels", "dimensions", "dimension", "width", "height", "depth",
        "geometry", "transform", "matrix", "path", "trajectory", "svg", "three",
        "html", "css", "canvas", "shader", "material", "mesh", "renderer", "renderer_config",
        "raw_renderer", "raw_renderer_config", "markup", "code", "javascript", "camera",
        "viewport", "viewbox", "fill", "stroke", "color", "colour", "font_size",
    }
)
_RENDERER_STATE_PREFIXES = ("position_", "rotation_", "scale_", "pixel", "coord", "dimension", "renderer_", "raw_", "svg_", "three_")

SURFACE_MODES: tuple[str, ...] = (
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
)
TYPOGRAPHY_CHARACTERS: tuple[str, ...] = (
    "technical",
    "editorial",
    "geometric",
    "humanist",
    "display",
    "monospace",
    "notebook",
    "deepmind",
)
SHAPE_LANGUAGES: tuple[str, ...] = (
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
)
BACKGROUND_CHARACTERS: tuple[str, ...] = (
    "solid",
    "gradient",
    "grid",
    "texture",
    "negative_space",
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
)
MOTION_CHARACTERS: tuple[str, ...] = (
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
)
CAPTION_SAFE_MODES: tuple[str, ...] = ("reserved_bottom", "minimal_overlay", "none")
SHOT_MODES: tuple[str, ...] = ("static", "focus", "zoom", "pan", "orbit", "dolly", "follow")
SHOT_FRAMINGS: tuple[str, ...] = ("wide", "medium", "close", "hero", "full_frame", "split")
RENDER_STRATEGY_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "svg": "vector_2d",
        "vector": "vector_2d",
        "procedural": "procedural_2d",
        "illustration": "procedural_2d",
        "data": "data_2d",
        "chart": "data_2d",
        "math": "mathematical_2d",
        "three": "semantic_3d",
        "3d": "semantic_3d",
    }
)


class VisualProgramV21Error(ValueError):
    """Raised when a V2.1 visual program is unsafe, unsupported, or invalid."""


VisualProgramV21ParseError = VisualProgramV21Error
VideoVisualProgramError = VisualProgramV21Error


JsonValue = Any


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _ensure_text(value: Any, name: str, *, maximum: int = 240, words: int = 40, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise VisualProgramV21Error(f"{name} must be a string")
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized and not allow_empty:
        raise VisualProgramV21Error(f"{name} must not be empty")
    if len(normalized) > maximum:
        raise VisualProgramV21Error(f"{name} exceeds {maximum} characters")
    if len(normalized.split()) > words:
        raise VisualProgramV21Error(f"{name} exceeds {words} words")
    if any(char in normalized and ord(char) < 32 and char not in _SAFE_TEXT_CONTROL for char in normalized):
        raise VisualProgramV21Error(f"{name} contains a control character")
    lowered = normalized.casefold()
    if any(fragment in lowered for fragment in _FORBIDDEN_TEXT):
        raise VisualProgramV21Error(f"{name} contains executable or unsafe content")
    if _PATHISH.search(normalized):
        raise VisualProgramV21Error(f"{name} contains a filesystem path")
    # Markup is compiler-owned.  Even harmless-looking tags are rejected here
    # so the model cannot smuggle executable SVG/HTML through a label.
    if "<" in normalized or ">" in normalized or "{{" in normalized or "}}" in normalized:
        raise VisualProgramV21Error(f"{name} contains markup delimiters")
    return normalized


def _identifier(value: Any, name: str) -> str:
    text = _ensure_text(value, name, maximum=64, words=1)
    if not _IDENTIFIER.fullmatch(text):
        raise VisualProgramV21Error(f"{name} must be an identifier")
    return text


def _mapping(value: Any, name: str, required: Iterable[str], optional: Iterable[str] = ()) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VisualProgramV21Error(f"{name} must be an object")
    required_set = set(required)
    optional_set = set(optional)
    keys = set(value)
    if not all(isinstance(key, str) for key in keys):
        raise VisualProgramV21Error(f"{name} contains a non-string key")
    missing = required_set - keys
    if missing:
        raise VisualProgramV21Error(f"{name} is missing required keys: {sorted(missing)}")
    unknown = keys - required_set - optional_set
    if unknown:
        raise VisualProgramV21Error(f"{name} contains unsupported keys: {sorted(unknown)}")
    return value


def _list(value: Any, name: str, *, minimum: int = 0, maximum: int = 64) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        raise VisualProgramV21Error(f"{name} must be an array")
    if not minimum <= len(value) <= maximum:
        raise VisualProgramV21Error(f"{name} must contain between {minimum} and {maximum} items")
    return list(value)


def _enum(value: Any, values: Iterable[str], name: str, *, aliases: Mapping[str, str] | None = None) -> str:
    if not isinstance(value, str):
        raise VisualProgramV21Error(f"{name} must be a string")
    token = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").casefold()
    for candidate in values:
        if re.sub(r"[^A-Za-z0-9]+", "_", candidate).strip("_").casefold() == token:
            return candidate
    if aliases and token in aliases:
        return aliases[token]
    raise VisualProgramV21Error(f"Unsupported {name}: {value!r}")


def _capability(value: Any, kind: str, name: str) -> str:
    try:
        return canonical_capability_name(value, kind=kind, registry=VISUAL_CAPABILITIES)
    except VisualCapabilityError as exc:
        raise VisualProgramV21Error(f"Unsupported {name}: {value!r}") from exc


def _optional_enum(data: Mapping[str, Any], key: str, values: Iterable[str], name: str, *, aliases: Mapping[str, str] | None = None) -> str | None:
    return None if key not in data or data[key] is None else _enum(data[key], values, f"{name}.{key}", aliases=aliases)


def _number(value: Any, name: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VisualProgramV21Error(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise VisualProgramV21Error(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise VisualProgramV21Error(f"{name} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise VisualProgramV21Error(f"{name} must be <= {maximum}")
    return result


def _integer(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise VisualProgramV21Error(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def _semantic_state_key(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise VisualProgramV21Error(f"{name} must be a string key")
    normalized = re.sub(r"[^a-z0-9]+", "_", unicodedata.normalize("NFKC", value).casefold()).strip("_")
    if normalized in _RENDERER_STATE_KEYS or normalized.startswith(_RENDERER_STATE_PREFIXES):
        raise VisualProgramV21Error(f"{name} uses renderer-owned state key: {value!r}")
    return _identifier(value, name)


def _safe_json(value: Any, name: str, *, depth: int = 0) -> JsonValue:
    """Validate bounded semantic state/parameters, returning immutable data."""

    if depth > 4:
        raise VisualProgramV21Error(f"{name} is nested too deeply")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _number(value, name, minimum=-1_000_000_000, maximum=1_000_000_000)
    if isinstance(value, str):
        return _ensure_text(value, name, maximum=160, words=28)
    if isinstance(value, Mapping):
        if len(value) > 24:
            raise VisualProgramV21Error(f"{name} contains too many fields")
        result: dict[str, Any] = {}
        for key, item in value.items():
            safe_key = _semantic_state_key(key, f"{name}.key")
            result[safe_key] = _safe_json(item, f"{name}.{safe_key}", depth=depth + 1)
        return MappingProxyType(result)
    if isinstance(value, (list, tuple)):
        if len(value) > 32:
            raise VisualProgramV21Error(f"{name} contains too many items")
        return tuple(_safe_json(item, f"{name}[{index}]", depth=depth + 1) for index, item in enumerate(value))
    raise VisualProgramV21Error(f"{name} contains an unsupported value")


@dataclass(frozen=True)
class PaletteIntentV21:
    dominant: str
    accent_family: str
    secondary_family: str | None = None
    contrast: str = "high"
    temperature: str = "neutral"
    saturation: str = "balanced"

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "dominant": self.dominant,
            "accent_family": self.accent_family,
            "contrast": self.contrast,
            "temperature": self.temperature,
            "saturation": self.saturation,
        }
        if self.secondary_family is not None:
            result["secondary_family"] = self.secondary_family
        return result


@dataclass(frozen=True)
class DesignBibleV21:
    """Active style intent only; camera and transition ownership lives in shot/events."""

    surface: str
    palette: PaletteIntentV21
    typography: str
    shape_language: str
    background: str
    motion: str
    caption_safe: str
    direction: str | None = None

    # Read-only aliases ease migration without reintroducing those fields into
    # the active model payload.
    @property
    def surface_mode(self) -> str:
        return self.surface

    @property
    def palette_intent(self) -> PaletteIntentV21:
        return self.palette

    @property
    def typography_character(self) -> str:
        return self.typography

    @property
    def shape_language_character(self) -> str:
        return self.shape_language

    @property
    def background_character(self) -> str:
        return self.background

    @property
    def motion_character(self) -> str:
        return self.motion

    @property
    def caption_integration(self) -> str:
        return self.caption_safe

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "surface": self.surface,
            "palette": self.palette.to_dict(),
            "typography": self.typography,
            "shape_language": self.shape_language,
            "background": self.background,
            "motion": self.motion,
            "caption_safe": self.caption_safe,
        }
        if self.direction is not None:
            result["direction"] = self.direction
        return result


@dataclass(frozen=True)
class WorldV21:
    description: str
    setting: str | None = None
    scale: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"description": self.description}
        if self.setting is not None:
            result["setting"] = self.setting
        if self.scale is not None:
            result["scale"] = self.scale
        return result


@dataclass(frozen=True)
class PartV21:
    id: str
    semantic_name: str
    structural_family: str | None = None
    parts: tuple["PartV21", ...] = ()
    state: Mapping[str, JsonValue] = MappingProxyType({})
    render_strategy: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"id": self.id, "semantic_name": self.semantic_name}
        if self.structural_family is not None:
            result["structural_family"] = self.structural_family
        if self.parts:
            result["parts"] = [part.to_dict() for part in self.parts]
        if self.state:
            result["state"] = _thaw(self.state)
        if self.render_strategy is not None:
            result["render_strategy"] = self.render_strategy
        return result


@dataclass(frozen=True)
class SubjectV21:
    id: str
    semantic_name: str
    structural_family: str
    parts: tuple[PartV21, ...] = ()
    state: Mapping[str, JsonValue] = MappingProxyType({})
    render_strategy: str = "procedural_2d"

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "semantic_name": self.semantic_name,
            "structural_family": self.structural_family,
            "render_strategy": self.render_strategy,
        }
        if self.parts:
            result["parts"] = [part.to_dict() for part in self.parts]
        if self.state:
            result["state"] = _thaw(self.state)
        return result


@dataclass(frozen=True)
class InitialStateV21:
    objects: Mapping[str, Mapping[str, JsonValue]] = MappingProxyType({})

    @property
    def subjects(self) -> Mapping[str, Mapping[str, JsonValue]]:
        return self.objects

    @property
    def values(self) -> Mapping[str, Mapping[str, JsonValue]]:
        return self.objects

    def __getitem__(self, key: str) -> Mapping[str, JsonValue]:
        return self.objects[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.objects.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return {"objects": _thaw(self.objects)}


@dataclass(frozen=True)
class RelationshipV21:
    source: str
    target: str
    kind: str
    via: tuple[str, ...] = ()
    carrier: str | None = None

    @property
    def relationship_type(self) -> str:
        return self.kind

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"source": self.source, "target": self.target, "kind": self.kind}
        if self.via:
            result["via"] = list(self.via)
        if self.carrier is not None:
            result["carrier"] = self.carrier
        return result


@dataclass(frozen=True)
class EventV21:
    id: str
    event_type: str
    subject: str | None = None
    source: str | None = None
    destination: str | None = None
    target: str | None = None
    carrier: str | None = None
    center: str | None = None
    parts: tuple[str, ...] = ()
    targets: tuple[str, ...] = ()
    path: tuple[tuple[float, ...], ...] = ()
    radius: float | None = None
    from_state: JsonValue = None
    to_state: JsonValue = None
    mode: str | None = None
    duration: float = 1.0
    at: float | None = None
    narration_anchor: str | None = None
    parameters: Mapping[str, JsonValue] = MappingProxyType({})

    @property
    def type(self) -> str:
        return self.event_type

    @property
    def object_id(self) -> str | None:
        return self.subject

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"id": self.id, "type": self.event_type}
        for key in ("subject", "source", "destination", "target", "carrier", "center", "mode", "narration_anchor"):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        if self.parts:
            result["sources" if self.event_type == "MERGE" else "parts"] = list(self.parts)
        if self.targets:
            result["targets"] = list(self.targets)
        if self.path:
            result["path"] = [list(point) for point in self.path]
        if self.radius is not None:
            result["radius"] = self.radius
        if self.from_state is not None:
            result["from_state"] = _thaw(self.from_state)
        if self.to_state is not None:
            result["to_state"] = _thaw(self.to_state)
        if self.duration != 1.0:
            result["duration"] = self.duration
        if self.at is not None:
            result["at"] = self.at
        if self.parameters:
            result["parameters"] = _thaw(self.parameters)
        return result


@dataclass(frozen=True)
class ShotV21:
    mode: str
    framing: str = "wide"
    subject: str | None = None
    center: str | None = None
    duration: float | None = None
    caption_safe: bool = True

    @property
    def camera_mode(self) -> str:
        return self.mode

    @property
    def focus_subject(self) -> str | None:
        return self.subject

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"mode": self.mode, "framing": self.framing, "caption_safe": self.caption_safe}
        if self.subject is not None:
            result["subject"] = self.subject
        if self.center is not None:
            result["center"] = self.center
        if self.duration is not None:
            result["duration"] = self.duration
        return result


@dataclass(frozen=True)
class NarrationAnchorV21:
    id: str
    cue_index: int | None = None
    start: float | None = None
    end: float | None = None
    text: str | None = None
    event_ids: tuple[str, ...] = ()

    @property
    def cue_id(self) -> str:
        return self.id

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"id": self.id}
        if self.cue_index is not None:
            result["cue_index"] = self.cue_index
        if self.start is not None:
            result["start"] = self.start
        if self.end is not None:
            result["end"] = self.end
        if self.text is not None:
            result["text"] = self.text
        if self.event_ids:
            result["event_ids"] = list(self.event_ids)
        return result


@dataclass(frozen=True)
class DataSeriesV21:
    id: str
    values: tuple[float, ...]
    label: str | None = None
    categories: tuple[str, ...] = ()
    unit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"id": self.id, "values": list(self.values)}
        if self.label is not None:
            result["label"] = self.label
        if self.categories:
            result["categories"] = list(self.categories)
        if self.unit is not None:
            result["unit"] = self.unit
        return result


@dataclass(frozen=True)
class ContinuityV21:
    carry_forward: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"carry_forward": list(self.carry_forward)}


@dataclass(frozen=True)
class SceneProgramV21:
    scene_id: str
    storyboard_section_id: str
    purpose: str
    representation_strategy: tuple[str, ...]
    world: WorldV21
    subjects: tuple[SubjectV21, ...]
    relationships: tuple[RelationshipV21, ...]
    initial_state: InitialStateV21
    events: tuple[EventV21, ...]
    shot: ShotV21
    narration_anchors: tuple[NarrationAnchorV21, ...] = ()
    data_series: tuple[DataSeriesV21, ...] = ()
    continuity: ContinuityV21 = ContinuityV21()

    @property
    def representation(self) -> tuple[str, ...]:
        return self.representation_strategy

    @property
    def scene_state(self) -> InitialStateV21:
        return self.initial_state

    def all_subject_ids(self) -> tuple[str, ...]:
        result: list[str] = []
        for subject in self.subjects:
            result.append(subject.id)
            result.extend(part.id for part in _walk_parts(subject.parts))
        return tuple(result)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "scene_id": self.scene_id,
            "storyboard_section_id": self.storyboard_section_id,
            "purpose": self.purpose,
            "representation_strategy": list(self.representation_strategy),
            "world": self.world.to_dict(),
            "subjects": [subject.to_dict() for subject in self.subjects],
            "relationships": [relation.to_dict() for relation in self.relationships],
            "initial_state": self.initial_state.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "shot": self.shot.to_dict(),
            "narration_anchors": [anchor.to_dict() for anchor in self.narration_anchors],
            "continuity": self.continuity.to_dict(),
        }
        if self.data_series:
            result["data_series"] = [series.to_dict() for series in self.data_series]
        return result


@dataclass(frozen=True)
class VideoVisualProgramV21:
    version: str
    content_intent: str
    design_bible: DesignBibleV21
    scenes: tuple[SceneProgramV21, ...]
    duration_seconds: float | None = None

    @property
    def content_intents(self) -> tuple[str, ...]:
        return (self.content_intent,)

    @property
    def storyboard_mapping(self) -> Mapping[str, str]:
        return MappingProxyType({scene.storyboard_section_id: scene.scene_id for scene in self.scenes})

    @property
    def scene_ids(self) -> tuple[str, ...]:
        return tuple(scene.scene_id for scene in self.scenes)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "version": self.version,
            "content_intent": self.content_intent,
            "design_bible": self.design_bible.to_dict(),
            "scenes": [scene.to_dict() for scene in self.scenes],
        }
        if self.duration_seconds is not None:
            result["duration_seconds"] = self.duration_seconds
        return result

    def to_json(self) -> str:
        import json

        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], storyboard: Any = None) -> "VideoVisualProgramV21":
        return parse_video_visual_program_v21(payload, storyboard=storyboard)


def _parse_palette(value: Any) -> PaletteIntentV21:
    data = _mapping(
        value,
        "design_bible.palette",
        set(),
        {"dominant", "accent_family", "secondary_family", "accent", "secondary", "contrast", "temperature", "saturation"},
    )
    if "dominant" not in data:
        raise VisualProgramV21Error("design_bible.palette is missing dominant")
    if "accent_family" not in data and "accent" not in data:
        raise VisualProgramV21Error("design_bible.palette is missing accent_family")
    accent = data.get("accent_family", data.get("accent"))
    secondary = data.get("secondary_family", data.get("secondary"))
    # Palette intent is semantic; actual colours are always trusted-engine
    # output.  Reject hex/random CSS values here.
    accent_text = _ensure_text(accent, "design_bible.palette.accent_family", maximum=32, words=4)
    dominant = _ensure_text(data["dominant"], "design_bible.palette.dominant", maximum=32, words=4)
    secondary_text = None if secondary is None else _ensure_text(secondary, "design_bible.palette.secondary_family", maximum=32, words=4)
    contrast = _ensure_text(data.get("contrast", "high"), "design_bible.palette.contrast", maximum=16, words=2).casefold()
    temperature = _ensure_text(data.get("temperature", "neutral"), "design_bible.palette.temperature", maximum=16, words=2).casefold()
    saturation = _ensure_text(data.get("saturation", "balanced"), "design_bible.palette.saturation", maximum=16, words=2).casefold()
    if contrast not in {"low", "medium", "high", "very_high", "very-high"}:
        raise VisualProgramV21Error("design_bible.palette.contrast is unsupported")
    if temperature not in {"warm", "neutral", "cool"}:
        raise VisualProgramV21Error("design_bible.palette.temperature is unsupported")
    if saturation not in {"muted", "selective", "balanced", "vivid"}:
        raise VisualProgramV21Error("design_bible.palette.saturation is unsupported")
    if "#" in accent_text or "#" in dominant or (secondary_text and "#" in secondary_text):
        raise VisualProgramV21Error("palette must contain semantic families, not raw colours")
    return PaletteIntentV21(
        dominant=dominant,
        accent_family=accent_text,
        secondary_family=secondary_text,
        contrast=contrast.replace("-", "_"),
        temperature=temperature,
        saturation=saturation,
    )


def _parse_design_bible(value: Any) -> DesignBibleV21:
    data = _mapping(
        value,
        "design_bible",
        set(),
        {
            "surface", "palette", "typography", "shape_language", "background", "motion", "caption_safe", "direction",
            "surface_mode", "palette_intent", "typography_character", "background_character", "motion_character", "caption_integration",
            "visual_mode", "visual_theme", "spatial_paradigm", "color_palette_semantic", "shape",
        },
    )
    # Legacy spellings are accepted only as input aliases and never emitted;
    # dead global camera/transition fields are deliberately not accepted.
    surface_value = data.get("surface", data.get("surface_mode", "solid"))
    palette_value = data.get("palette", data.get("palette_intent", data.get("color_palette_semantic", {})))
    typography_value = data.get("typography", data.get("typography_character", "geometric"))
    background_value = data.get("background", data.get("background_character", "solid"))
    motion_value = data.get("motion", data.get("motion_character", "crisp"))
    caption_value = data.get("caption_safe", data.get("caption_integration", "bottom_band"))
    surface = _enum(surface_value, SURFACE_MODES, "design_bible.surface")
    typography = _enum(typography_value, TYPOGRAPHY_CHARACTERS, "design_bible.typography")
    shape_val = data.get("shape_language", data.get("shape", data.get("visual_mode", "clean_geometric")))
    shape = _enum(shape_val, SHAPE_LANGUAGES, "design_bible.shape_language")
    background = _enum(background_value, BACKGROUND_CHARACTERS, "design_bible.background")
    motion = _enum(motion_value, MOTION_CHARACTERS, "design_bible.motion")
    caption = _enum(caption_value, CAPTION_SAFE_MODES, "design_bible.caption_safe")
    direction = None if data.get("direction") is None else _ensure_text(data["direction"], "design_bible.direction", maximum=160, words=24)
    return DesignBibleV21(surface, _parse_palette(palette_value), typography, shape, background, motion, caption, direction)


def _parse_world(value: Any) -> WorldV21:
    if isinstance(value, str):
        return WorldV21(description=_ensure_text(value, "world", maximum=200, words=32))
    if isinstance(value, Mapping) and "description" not in value:
        value = dict(value)
        value["description"] = value.get("domain") or value.get("setting") or value.get("spatial_layout") or "stage"
    data = _mapping(value, "world", {"description"}, {"setting", "scale", "domain", "spatial_layout", "coordinate_system"})
    return WorldV21(
        description=_ensure_text(data["description"], "world.description", maximum=200, words=32),
        setting=None if data.get("setting") is None else _ensure_text(data["setting"], "world.setting", maximum=120, words=20),
        scale=None if data.get("scale") is None else _ensure_text(data["scale"], "world.scale", maximum=32, words=4),
    )


def _parse_part(value: Any, name: str, *, depth: int = 0) -> PartV21:
    if depth > 3:
        raise VisualProgramV21Error(f"{name} hierarchy is too deep")
    if isinstance(value, Mapping):
        if "semantic_name" not in value and ("name" in value or "label" in value or "id" in value):
            value = dict(value)
            value["semantic_name"] = value.get("semantic_name") or value.get("name") or value.get("label") or value.get("id")
        if "render_strategy" not in value and "renderer_mode" in value:
            value = dict(value)
            value["render_strategy"] = value.get("renderer_mode")
    data = _mapping(value, name, {"id", "semantic_name"}, {"structural_family", "parts", "state", "render_strategy", "renderer_mode", "name", "label", "description"})
    family = None
    if data.get("structural_family") is not None:
        family = _capability(data["structural_family"], "structural_family", f"{name}.structural_family")
    parts = tuple(_parse_part(item, f"{name}.parts[{index}]", depth=depth + 1) for index, item in enumerate(_list(data.get("parts", []), f"{name}.parts", maximum=16)))
    state_value = data.get("state", {})
    if not isinstance(state_value, Mapping):
        raise VisualProgramV21Error(f"{name}.state must be an object")
    render_val = data.get("render_strategy", data.get("renderer_mode"))
    render = None if render_val is None else _enum(render_val, RENDERER_MODES, f"{name}.render_strategy", aliases=RENDER_STRATEGY_ALIASES)
    return PartV21(
        id=_identifier(data["id"], f"{name}.id"),
        semantic_name=_ensure_text(data["semantic_name"], f"{name}.semantic_name", maximum=100, words=12),
        structural_family=family,
        parts=parts,
        state=_freeze(_safe_json(state_value, f"{name}.state")),
        render_strategy=render,
    )


def _parse_subject(value: Any, name: str) -> SubjectV21:
    if isinstance(value, Mapping):
        if "semantic_name" not in value and ("name" in value or "label" in value or "id" in value):
            value = dict(value)
            value["semantic_name"] = value.get("semantic_name") or value.get("name") or value.get("label") or value.get("id")
        if "render_strategy" not in value and "renderer_mode" in value:
            value = dict(value)
            value["render_strategy"] = value.get("renderer_mode")
    data = _mapping(value, name, {"id", "semantic_name", "structural_family"}, {"parts", "state", "render_strategy", "renderer_mode", "name", "label", "description"})
    family = _capability(data["structural_family"], "structural_family", f"{name}.structural_family")
    parts = tuple(_parse_part(item, f"{name}.parts[{index}]", depth=0) for index, item in enumerate(_list(data.get("parts", []), f"{name}.parts", maximum=24)))
    state_value = data.get("state", {})
    if not isinstance(state_value, Mapping):
        raise VisualProgramV21Error(f"{name}.state must be an object")
    render_val = data.get("render_strategy", data.get("renderer_mode", "procedural_2d"))
    render = _enum(render_val, RENDERER_MODES, f"{name}.render_strategy", aliases=RENDER_STRATEGY_ALIASES)
    return SubjectV21(
        id=_identifier(data["id"], f"{name}.id"),
        semantic_name=_ensure_text(data["semantic_name"], f"{name}.semantic_name", maximum=120, words=16),
        structural_family=family,
        parts=parts,
        state=_freeze(_safe_json(state_value, f"{name}.state")),
        render_strategy=render,
    )


def _parse_initial_state(value: Any) -> InitialStateV21:
    data: Mapping[str, Any]
    if value is None:
        return InitialStateV21()
    if isinstance(value, Mapping) and "subject_states" in value and isinstance(value["subject_states"], list):
        # Handle list-style subject states
        states_dict = {}
        for item in value["subject_states"]:
            if isinstance(item, Mapping) and ("subject" in item or "id" in item):
                sid = item.get("subject") or item.get("id")
                st = item.get("state", {})
                states_dict[str(sid)] = {"state": st} if not isinstance(st, Mapping) else dict(st)
        value = states_dict
    if not isinstance(value, Mapping):
        raise VisualProgramV21Error("initial_state must be an object")
    if "objects" in value or "subjects" in value:
        data = _mapping(value, "initial_state", set(), {"objects", "subjects", "subject_states"})
        if "objects" in data and "subjects" in data:
            raise VisualProgramV21Error("initial_state may use objects or subjects, not both")
        object_value = data.get("objects", data.get("subjects", data.get("subject_states")))
        if not isinstance(object_value, Mapping):
            raise VisualProgramV21Error("initial_state.objects must be an object")
    else:
        object_value = value
    if len(object_value) > 64:
        raise VisualProgramV21Error("initial_state contains too many objects")
    result: dict[str, Mapping[str, JsonValue]] = {}
    for object_id, state in object_value.items():
        safe_id = _identifier(object_id, "initial_state.object_id")
        if not isinstance(state, Mapping):
            state = {"state": state}
        result[safe_id] = _freeze(_safe_json(state, f"initial_state.{safe_id}"))
    return InitialStateV21(MappingProxyType(result))


def _parse_relationship(value: Any, name: str) -> RelationshipV21:
    if isinstance(value, Mapping):
        if "kind" not in value and ("type" in value or "relationship" in value):
            value = dict(value)
            value["kind"] = value.get("kind") or value.get("type") or value.get("relationship")
    data = _mapping(value, name, {"source", "target", "kind"}, {"type", "relationship", "via", "carrier"})
    kind = _capability(data["kind"], "relationship", f"{name}.kind")
    via = tuple(_identifier(item, f"{name}.via[{index}]") for index, item in enumerate(_list(data.get("via", []), f"{name}.via", maximum=16)))
    carrier = None if data.get("carrier") is None else _identifier(data["carrier"], f"{name}.carrier")
    return RelationshipV21(
        source=_identifier(data["source"], f"{name}.source"),
        target=_identifier(data["target"], f"{name}.target"),
        kind=kind,
        via=via,
        carrier=carrier,
    )


def _parse_state_transition(value: Any, name: str) -> JsonValue:
    if isinstance(value, Mapping):
        return _safe_json(value, name)
    return _ensure_text(value, name, maximum=120, words=16)


def _parse_path(value: Any, name: str) -> tuple[tuple[float, ...], ...]:
    # Kept as a defensive compatibility stub: V2.1 never accepts renderer-owned
    # coordinate arrays.  Semantic PATH_MOTION uses subject references below.
    raise VisualProgramV21Error(f"{name} coordinate paths are not supported; use semantic subject references")


def _parse_event(value: Any, name: str) -> EventV21:
    data = _mapping(
        value,
        name,
        {"id"},
        {
            "type", "event_type", "action", "subject", "subjects", "object_id", "source", "destination", "target", "carrier", "center",
            "parts", "sources", "targets", "radius", "from_state", "to_state", "mode", "duration", "at",
            "narration_anchor", "anchor", "parameters",
        },
    )
    type_value = data.get("type", data.get("event_type", data.get("action")))
    if type_value is None:
        raise VisualProgramV21Error(f"{name} is missing event type")
    event_type = _capability(type_value, "event", f"{name}.type")
    identifier = _identifier(data["id"], f"{name}.id")
    text_fields: dict[str, str | None] = {}
    for key in ("subject", "source", "destination", "target", "carrier", "center"):
        if data.get(key) is not None:
            text_fields[key] = _identifier(data[key], f"{name}.{key}")
        else:
            text_fields[key] = None
    if data.get("object_id") is not None:
        if text_fields["subject"] is not None:
            raise VisualProgramV21Error(f"{name} cannot set both subject and object_id")
        text_fields["subject"] = _identifier(data["object_id"], f"{name}.object_id")
    raw_parts = data.get("parts", [])
    raw_subjects = data.get("subjects", [])
    if not raw_parts and raw_subjects and isinstance(raw_subjects, (list, tuple)):
        raw_parts = raw_subjects
    raw_sources = data.get("sources", [])
    if raw_sources and raw_parts:
        raise VisualProgramV21Error(f"{name} cannot set both sources and parts")
    if raw_sources:
        raw_parts = raw_sources
    parts = tuple(_identifier(item, f"{name}.parts[{index}]") for index, item in enumerate(_list(raw_parts, f"{name}.parts", maximum=32)))
    targets = tuple(_identifier(item, f"{name}.targets[{index}]") for index, item in enumerate(_list(data.get("targets", []), f"{name}.targets", maximum=32)))
    # Coordinate path/trajectory arrays are intentionally not part of the
    # untrusted contract; the trusted compiler derives geometry from references.
    path = ()
    radius = None if data.get("radius") is None else _number(data["radius"], f"{name}.radius", minimum=0.0001, maximum=1_000_000)
    from_state = None if data.get("from_state") is None else _parse_state_transition(data["from_state"], f"{name}.from_state")
    to_state = None if data.get("to_state") is None else _parse_state_transition(data["to_state"], f"{name}.to_state")
    mode = None if data.get("mode") is None else _enum(data["mode"], SHOT_MODES, f"{name}.mode")
    duration = _number(data.get("duration", 1.0), f"{name}.duration", minimum=0.001, maximum=600)
    at = None if data.get("at") is None else _number(data["at"], f"{name}.at", minimum=0, maximum=86_400)
    anchor_value = data.get("narration_anchor", data.get("anchor"))
    anchor = None if anchor_value is None else _identifier(anchor_value, f"{name}.narration_anchor")
    parameters_value = data.get("parameters", {})
    if not isinstance(parameters_value, Mapping):
        raise VisualProgramV21Error(f"{name}.parameters must be an object")
    if event_type == "CAMERA" and parameters_value:
        raise VisualProgramV21Error(f"{name}.CAMERA does not accept arbitrary parameters")
    parameters = _freeze(_safe_json(parameters_value, f"{name}.parameters"))
    event = EventV21(
        id=identifier,
        event_type=event_type,
        parts=parts,
        targets=targets,
        path=path,
        radius=radius,
        from_state=from_state,
        to_state=to_state,
        mode=mode,
        duration=duration,
        at=at,
        narration_anchor=anchor,
        parameters=parameters,
        **text_fields,
    )
    _validate_event_requirements(event, name)
    return event


def _event_requirement_present(event: EventV21, requirement: str) -> bool:
    value = getattr(event, requirement, None)
    if requirement in {"parts", "targets", "sources"}:
        return isinstance(value, tuple) and bool(value)
    if requirement == "radius":
        return event.radius is not None and event.radius > 0
    if requirement == "path":
        return False
    return value is not None


def _validate_event_requirements(event: EventV21, name: str) -> None:
    spec = VISUAL_CAPABILITIES.require(event.event_type, kind="event")
    for requirement in spec.requirements:
        if not _event_requirement_present(event, requirement):
            raise VisualProgramV21Error(f"{name} requires {requirement}")
    if spec.requirement_alternatives:
        alternatives = [
            all(_event_requirement_present(event, requirement) for requirement in alternative)
            for alternative in spec.requirement_alternatives
        ]
        if sum(alternatives) != 1:
            raise VisualProgramV21Error(f"{name} must satisfy exactly one semantic requirement alternative")
    if event.event_type == "PATH_MOTION":
        has_subject_route = event.source is not None and event.destination is not None
        has_orbit_route = event.center is not None and event.radius is not None and event.radius > 0 and event.mode == "orbit"
        if has_subject_route == has_orbit_route:
            raise VisualProgramV21Error(f"{name} PATH_MOTION requires source/destination or center/radius with mode=orbit")
    if event.event_type == "CAMERA":
        if event.mode is None or event.subject is None and event.target is None:
            raise VisualProgramV21Error(f"{name} CAMERA requires a bounded mode and semantic subject/target")
    if event.event_type == "MERGE" and len(event.sources) < 2:
        raise VisualProgramV21Error(f"{name} MERGE requires at least two sources")


# The event model uses a plural source list for MERGE while ordinary events use
# source/destination.  Keep the public dataclass compact and expose the alias.
def _event_sources(event: EventV21) -> tuple[str, ...]:
    if event.event_type == "MERGE":
        return event.parts or tuple(item for item in (event.source, event.destination) if item is not None)
    return tuple(item for item in (event.source,) if item is not None)


EventV21.sources = property(_event_sources)  # type: ignore[attr-defined]


def _parse_shot(value: Any, name: str) -> ShotV21:
    data = _mapping(value, name, set(), {"mode", "camera_mode", "framing", "subject", "focus_subject", "target", "center", "duration", "caption_safe"})
    if "mode" not in data and "camera_mode" not in data:
        raise VisualProgramV21Error(f"{name} is missing mode")
    mode = _enum(data.get("mode", data.get("camera_mode")), SHOT_MODES, f"{name}.mode")
    framing = _enum(data.get("framing", "wide"), SHOT_FRAMINGS, f"{name}.framing")
    subject_value = data.get("subject", data.get("focus_subject", data.get("target")))
    subject = None if subject_value is None else _identifier(subject_value, f"{name}.subject")
    center = None if data.get("center") is None else _identifier(data["center"], f"{name}.center")
    duration = None if data.get("duration") is None else _number(data["duration"], f"{name}.duration", minimum=0.001, maximum=600)
    caption_safe = data.get("caption_safe", True)
    if not isinstance(caption_safe, bool):
        raise VisualProgramV21Error(f"{name}.caption_safe must be boolean")
    return ShotV21(mode, framing, subject, center, duration, caption_safe)


def _parse_anchor(value: Any, name: str) -> NarrationAnchorV21:
    data = _mapping(value, name, {"id"}, {"cue_index", "cue", "start", "end", "text", "event_ids", "events"})
    cue_index_value = data.get("cue_index", data.get("cue"))
    cue_index = None if cue_index_value is None else _integer(cue_index_value, f"{name}.cue_index", minimum=0, maximum=10_000)
    start = None if data.get("start") is None else _number(data["start"], f"{name}.start", minimum=0, maximum=86_400)
    end = None if data.get("end") is None else _number(data["end"], f"{name}.end", minimum=0, maximum=86_400)
    if start is not None and end is not None and end < start:
        raise VisualProgramV21Error(f"{name}.end must not precede start")
    text = None if data.get("text") is None else _ensure_text(data["text"], f"{name}.text", maximum=240, words=40)
    event_ids = tuple(_identifier(item, f"{name}.event_ids[{index}]") for index, item in enumerate(_list(data.get("event_ids", data.get("events", [])), f"{name}.event_ids", maximum=32)))
    return NarrationAnchorV21(_identifier(data["id"], f"{name}.id"), cue_index, start, end, text, event_ids)


def _parse_series(value: Any, name: str) -> DataSeriesV21:
    data = _mapping(value, name, {"id", "values"}, {"label", "categories", "labels", "unit"})
    raw_values = _list(data["values"], f"{name}.values", minimum=1, maximum=256)
    values = tuple(_number(item, f"{name}.values[{index}]", minimum=-1_000_000_000, maximum=1_000_000_000) for index, item in enumerate(raw_values))
    raw_categories = data.get("categories", data.get("labels", []))
    categories = tuple(_ensure_text(item, f"{name}.categories[{index}]", maximum=64, words=8) for index, item in enumerate(_list(raw_categories, f"{name}.categories", maximum=256)))
    if categories and len(categories) != len(values):
        raise VisualProgramV21Error(f"{name}.categories must match values length")
    label = None if data.get("label") is None else _ensure_text(data["label"], f"{name}.label", maximum=80, words=12)
    unit = None if data.get("unit") is None else _ensure_text(data["unit"], f"{name}.unit", maximum=32, words=4)
    return DataSeriesV21(_identifier(data["id"], f"{name}.id"), values, label, categories, unit)


def _parse_continuity(value: Any, name: str) -> ContinuityV21:
    if value is None:
        return ContinuityV21()
    data = _mapping(value, name, {"carry_forward"}, set())
    carried = tuple(_identifier(item, f"{name}.carry_forward[{index}]") for index, item in enumerate(_list(data["carry_forward"], f"{name}.carry_forward", maximum=64)))
    if len(set(carried)) != len(carried):
        raise VisualProgramV21Error(f"{name}.carry_forward contains duplicates")
    return ContinuityV21(carried)


def _parse_scene(value: Any, position: int) -> SceneProgramV21:
    name = f"scenes[{position}]"
    data = _mapping(
        value,
        name,
        {"scene_id", "storyboard_section_id", "purpose", "representation_strategy", "world", "subjects"},
        {"relationships", "initial_state", "events", "shot", "representation", "narration_anchors", "narration", "data_series", "continuity"},
    )
    representation_value = data.get("representation_strategy", data.get("representation"))
    if isinstance(representation_value, str):
        representation_value = [representation_value]
    representation = tuple(_enum(item, REPRESENTATION_STRATEGIES, f"{name}.representation_strategy[{index}]") for index, item in enumerate(_list(representation_value, f"{name}.representation_strategy", minimum=1, maximum=4)))
    if len(set(representation)) != len(representation):
        raise VisualProgramV21Error(f"{name}.representation_strategy contains duplicates")
    subjects = tuple(_parse_subject(item, f"{name}.subjects[{index}]") for index, item in enumerate(_list(data["subjects"], f"{name}.subjects", minimum=1, maximum=64)))
    relationships = tuple(_parse_relationship(item, f"{name}.relationships[{index}]") for index, item in enumerate(_list(data.get("relationships", []), f"{name}.relationships", maximum=128)))
    events = tuple(_parse_event(item, f"{name}.events[{index}]") for index, item in enumerate(_list(data.get("events", []), f"{name}.events", maximum=128)))
    anchor_value = data.get("narration_anchors", data.get("narration", []))
    anchors = tuple(_parse_anchor(item, f"{name}.narration_anchors[{index}]") for index, item in enumerate(_list(anchor_value, f"{name}.narration_anchors", maximum=64)))
    series = tuple(_parse_series(item, f"{name}.data_series[{index}]") for index, item in enumerate(_list(data.get("data_series", []), f"{name}.data_series", maximum=16)))
    shot_value = data.get("shot", {"mode": "focus", "duration": 10.0})
    scene = SceneProgramV21(
        scene_id=_identifier(data["scene_id"], f"{name}.scene_id"),
        storyboard_section_id=_identifier(data["storyboard_section_id"], f"{name}.storyboard_section_id"),
        purpose=_ensure_text(data["purpose"], f"{name}.purpose", maximum=240, words=40),
        representation_strategy=representation,
        world=_parse_world(data["world"]),
        subjects=subjects,
        relationships=relationships,
        initial_state=_parse_initial_state(data.get("initial_state", {})),
        events=events,
        shot=_parse_shot(shot_value, f"{name}.shot"),
        narration_anchors=anchors,
        data_series=series,
        continuity=_parse_continuity(data.get("continuity"), f"{name}.continuity"),
    )
    _validate_scene_references(scene)
    return scene


def _walk_parts(parts: Iterable[PartV21]) -> Iterable[PartV21]:
    for part in parts:
        yield part
        yield from _walk_parts(part.parts)


def _validate_scene_references(scene: SceneProgramV21) -> None:
    ids = set(scene.all_subject_ids())
    if len(ids) != len(scene.all_subject_ids()):
        raise VisualProgramV21Error(f"Scene {scene.scene_id!r} contains duplicate subject/part IDs")
    for relation in scene.relationships:
        if relation.source not in ids or relation.target not in ids:
            raise VisualProgramV21Error(f"Scene {scene.scene_id!r} relationship references an unknown subject")
        if relation.source == relation.target:
            raise VisualProgramV21Error(f"Scene {scene.scene_id!r} relationship cannot target itself")
        if any(item not in ids for item in relation.via):
            raise VisualProgramV21Error(f"Scene {scene.scene_id!r} relationship via references an unknown subject")
        if relation.carrier is not None and relation.carrier not in ids:
            raise VisualProgramV21Error(f"Scene {scene.scene_id!r} relationship carrier is unknown")
    for object_id in scene.initial_state.objects:
        if object_id not in ids:
            raise VisualProgramV21Error(f"Scene {scene.scene_id!r} initial state references an unknown subject")
    for event in scene.events:
        refs = [event.subject, event.source, event.destination, event.target, event.carrier, event.center]
        refs.extend(event.parts)
        refs.extend(event.targets)
        if any(item is not None and item not in ids for item in refs):
            raise VisualProgramV21Error(f"Scene {scene.scene_id!r} event references an unknown subject")
    event_ids = {event.id for event in scene.events}
    if len(event_ids) != len(scene.events):
        raise VisualProgramV21Error(f"Scene {scene.scene_id!r} contains duplicate event IDs")
    anchor_ids = {anchor.id for anchor in scene.narration_anchors}
    if len(anchor_ids) != len(scene.narration_anchors):
        raise VisualProgramV21Error(f"Scene {scene.scene_id!r} contains duplicate narration anchors")
    for event in scene.events:
        if event.narration_anchor is not None and event.narration_anchor not in anchor_ids:
            raise VisualProgramV21Error(f"Scene {scene.scene_id!r} event references an unknown narration anchor")
    for anchor in scene.narration_anchors:
        if any(event_id not in event_ids for event_id in anchor.event_ids):
            raise VisualProgramV21Error(f"Scene {scene.scene_id!r} narration anchor references an unknown event")
    if scene.shot.subject is not None and scene.shot.subject not in ids:
        raise VisualProgramV21Error(f"Scene {scene.scene_id!r} shot references an unknown subject")
    if scene.shot.center is not None and scene.shot.center not in ids:
        raise VisualProgramV21Error(f"Scene {scene.scene_id!r} shot references an unknown center")
    series_ids = [series.id for series in scene.data_series]
    if len(set(series_ids)) != len(series_ids):
        raise VisualProgramV21Error(f"Scene {scene.scene_id!r} contains duplicate data series IDs")


def _storyboard_ids(storyboard: Any) -> list[str] | None:
    if storyboard is None:
        return None
    sections: Any = storyboard
    if isinstance(storyboard, Mapping):
        sections = storyboard.get("sections")
        if sections is None:
            raise VisualProgramV21Error("storyboard must contain sections")
    if not isinstance(sections, (list, tuple)):
        raise VisualProgramV21Error("storyboard sections must be an array")
    result: list[str] = []
    for index, item in enumerate(sections):
        if isinstance(item, Mapping):
            if "id" not in item:
                raise VisualProgramV21Error(f"storyboard.sections[{index}] is missing id")
            result.append(_identifier(item["id"], f"storyboard.sections[{index}].id"))
        else:
            result.append(_identifier(item, f"storyboard.sections[{index}]"))
    return result


def parse_video_visual_program_v21(payload: Any, storyboard: Any = None) -> VideoVisualProgramV21:
    """Parse and validate one untrusted model payload.

    ``storyboard`` may be the existing storyboard mapping, a sequence of
    section objects, or a sequence of section IDs.  When supplied, scene IDs
    must map one-to-one and in order to those sections.
    """

    if not isinstance(payload, Mapping):
        raise VisualProgramV21Error("visual program must be an object")
    data = _mapping(payload, "visual_program", {"version", "content_intent", "design_bible", "scenes"}, {"duration_seconds", "meta", "title", "mode", "target_audience", "visual_theme"})
    version = _ensure_text(data["version"], "version", maximum=16, words=2)
    if version != V21_PROGRAM_VERSION:
        raise VisualProgramV21Error(f"Unsupported visual-program version: {version!r}")
    content_intent = _capability(data["content_intent"], "content_intent", "content_intent")
    scenes = tuple(_parse_scene(item, index) for index, item in enumerate(_list(data["scenes"], "scenes", minimum=1, maximum=24)))
    scene_ids = [scene.scene_id for scene in scenes]
    section_ids = [scene.storyboard_section_id for scene in scenes]
    if len(set(scene_ids)) != len(scene_ids):
        raise VisualProgramV21Error("visual program contains duplicate scene IDs")
    if len(set(section_ids)) != len(section_ids):
        raise VisualProgramV21Error("visual program contains duplicate storyboard section IDs")
    expected_sections = _storyboard_ids(storyboard)
    if expected_sections is not None and section_ids != expected_sections:
        raise VisualProgramV21Error("scenes must map one-to-one to storyboard sections in order")
    earlier_ids: set[str] = set()
    for scene in scenes:
        carried = set(scene.continuity.carry_forward)
        if carried & set(scene.all_subject_ids()):
            raise VisualProgramV21Error(f"Scene {scene.scene_id!r} redeclares carried-forward subjects")
        if not carried <= earlier_ids:
            unknown = sorted(carried - earlier_ids)
            raise VisualProgramV21Error(f"Scene {scene.scene_id!r} carries unknown subjects: {unknown}")
        earlier_ids.update(scene.all_subject_ids())
    duration = None if data.get("duration_seconds") is None else _number(data["duration_seconds"], "duration_seconds", minimum=0.1, maximum=86_400)
    return VideoVisualProgramV21(version, content_intent, _parse_design_bible(data["design_bible"]), scenes, duration)


def validate_video_visual_program_v21(payload: Any, storyboard: Any = None) -> VideoVisualProgramV21:
    """Validation-oriented alias used by integration code."""

    return parse_video_visual_program_v21(payload, storyboard=storyboard)


def program_from_dict(payload: Mapping[str, Any], storyboard: Any = None) -> VideoVisualProgramV21:
    return parse_video_visual_program_v21(payload, storyboard=storyboard)


parse_visual_program_v21 = parse_video_visual_program_v21
validate_visual_program_v21 = validate_video_visual_program_v21
VideoVisualProgram = VideoVisualProgramV21
VisualProgramV21 = VideoVisualProgramV21
SceneV21 = SceneProgramV21
Subject = SubjectV21
Part = PartV21
Relationship = RelationshipV21
Event = EventV21
Shot = ShotV21
NarrationAnchor = NarrationAnchorV21
World = WorldV21
DesignBible = DesignBibleV21
PaletteIntent = PaletteIntentV21
InitialState = InitialStateV21
Continuity = ContinuityV21
DataSeries = DataSeriesV21


__all__ = [
    "BACKGROUND_CHARACTERS",
    "CAPTION_SAFE_MODES",
    "ContinuityV21",
    "DataSeriesV21",
    "DesignBibleV21",
    "EventV21",
    "InitialStateV21",
    "MOTION_CHARACTERS",
    "NarrationAnchorV21",
    "PaletteIntentV21",
    "PartV21",
    "RelationshipV21",
    "SceneProgramV21",
    "SHOT_FRAMINGS",
    "SHOT_MODES",
    "SHAPE_LANGUAGES",
    "SubjectV21",
    "TYPOGRAPHY_CHARACTERS",
    "V21_PROGRAM_VERSION",
    "VIDEO_VISUAL_PROGRAM_V21_VERSION",
    "VideoVisualProgramError",
    "VideoVisualProgramV21",
    "VisualProgramV21Error",
    "VisualProgramV21ParseError",
    "VisualProgramV21",
    "VideoVisualProgram",
    "SceneV21",
    "Subject",
    "Part",
    "Relationship",
    "Event",
    "Shot",
    "NarrationAnchor",
    "World",
    "DesignBible",
    "PaletteIntent",
    "InitialState",
    "Continuity",
    "DataSeries",
    "WorldV21",
    "parse_video_visual_program_v21",
    "parse_visual_program_v21",
    "program_from_dict",
    "validate_video_visual_program_v21",
    "validate_visual_program_v21",
]

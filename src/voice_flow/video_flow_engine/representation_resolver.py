"""Safe procedural representations for the V2.1 visual scene program.

The resolver turns a bounded semantic subject into compiler-owned data.  It
does not return SVG markup, Three.js source, colours, file paths, or executable
configuration.  Geometry is generated from a compact set of structural
families and the compiler may lower the descriptors into its current SVG and
Narova surfaces.

Families deliberately describe structure rather than named subjects.  An
``organic_branching`` subject can be a plant, coral, or branching vessel; a
``mechanical_linkage`` subject can be an engine, pump, or articulated machine.
That keeps direct depiction compositional without growing a subject-template
catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from .visual_construction import build_subject_blueprint, SubjectConstraintSolver
import hashlib
import math
import re
from typing import Any, Iterable, Iterator, Mapping, Sequence


class RepresentationResolverError(ValueError):
    """Raised when a semantic subject cannot be safely represented."""


STRUCTURAL_FAMILIES = frozenset(
    {
        "organic_branching",
        "organic_body",
        "fluid_system",
        "mechanical_linkage",
        "rigid_assembly",
        "architecture",
        "terrain",
        "atmospheric_system",
        "network",
        "celestial_body",
        "infrastructure",
        "quantitative_data",
        "mathematical_geometry",
    }
)

REPRESENTATION_MODES = frozenset({"svg", "three", "hybrid"})
PALETTE_ROLES = frozenset({"accent", "secondary", "surface", "foreground", "muted", "emphasis"})
THREE_PRIMITIVES = frozenset({"group", "cube", "sphere", "cylinder", "plane", "torus", "cone", "icosahedron", "particles"})
THREE_ANIMATION_PROPERTIES = frozenset({"position.x", "position.y", "position.z", "rotation.x", "rotation.y", "rotation.z", "scale.x", "scale.y", "scale.z", "scale", "opacity"})

_IDENTIFIER = re.compile(r"[^A-Za-z0-9_-]+")
_UNSAFE_TEXT = re.compile(r"(?:<|>|javascript:|data:|script|function\s*\(|__import__|subprocess|child_process|eval\s*\(|exec\s*\(|[A-Za-z]:[\\/]|(?:^|\s)/[A-Za-z])", re.IGNORECASE)
_FAMILY_ALIASES = {
    "organic_branching/body": "organic_branching",
    "organic_branch": "organic_branching",
    "branching": "organic_branching",
    "organic": "organic_body",
    "fluid": "fluid_system",
    "fluid_systems": "fluid_system",
    "mechanical": "mechanical_linkage",
    "linkage": "mechanical_linkage",
    "rigid": "rigid_assembly",
    "assembly": "rigid_assembly",
    "building": "architecture",
    "atmosphere": "atmospheric_system",
    "weather": "atmospheric_system",
    "celestial": "celestial_body",
    "data": "quantitative_data",
    "chart": "quantitative_data",
    "math": "mathematical_geometry",
    "geometry": "mathematical_geometry",
}


def _value(value: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(value, Mapping):
            if name in value:
                return value[name]
        else:
            try:
                result = getattr(value, name)
            except (AttributeError, TypeError):
                continue
            if result is not None:
                return result
    return default


def _finite(value: Any, default: float = 0.0, *, lower: float | None = None, upper: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = default
    if not math.isfinite(result):
        result = default
    if lower is not None:
        result = max(lower, result)
    if upper is not None:
        result = min(upper, result)
    return result


def _vector(value: Any, fallback: Sequence[float] = (0.0, 0.0, 0.0)) -> list[float]:
    if isinstance(value, Mapping):
        value = (_value(value, "x", default=fallback[0]), _value(value, "y", default=fallback[1]), _value(value, "z", default=fallback[2]))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values = list(value)
        if len(values) >= 3:
            return [_finite(item, fallback[index]) for index, item in enumerate(values[:3])]
        if len(values) == 2:
            return [_finite(values[0], fallback[0]), _finite(values[1], fallback[1]), fallback[2]]
    return [_finite(item, 0.0) for item in fallback]


def _safe_text(value: Any, default: str, *, maximum: int = 80) -> str:
    text = str(value or default).strip()
    if _UNSAFE_TEXT.search(text):
        text = re.sub(r"[^A-Za-z0-9 _.,:/()'-]", "", text)
    text = " ".join(text.split())
    return text[:maximum] or default


def _safe_id(value: Any, default: str) -> str:
    text = _safe_text(value, default, maximum=64)
    text = _IDENTIFIER.sub("_", text).strip("_-")
    if not text or not text[0].isalpha():
        text = f"part_{text}" if text else default
    return text[:64]


def _subject_dict(subject: Any) -> dict[str, Any]:
    if isinstance(subject, Mapping):
        return dict(subject)
    to_dict = getattr(subject, "to_dict", None)
    if callable(to_dict):
        try:
            value = to_dict()
        except (TypeError, ValueError):
            value = None
        if isinstance(value, Mapping):
            return dict(value)
    result: dict[str, Any] = {}
    for name in ("id", "subject_id", "semantic_name", "name", "structural_family", "family", "parts", "state", "render_strategy", "events", "values", "data"):
        value = _value(subject, name, default=None)
        if value is not None:
            result[name] = value
    if isinstance(subject, str):
        result["semantic_name"] = subject
    return result


def normalize_family(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    raw = _FAMILY_ALIASES.get(raw, raw)
    if raw not in STRUCTURAL_FAMILIES:
        raise RepresentationResolverError(f"Unsupported structural family: {value!r}")
    return raw


def _infer_family(data: Mapping[str, Any], explicit: Any = None, strategy: Any = None) -> str:
    if explicit is not None:
        return normalize_family(explicit)
    candidate = _value(data, "structural_family", "family", default=None)
    if candidate:
        return normalize_family(candidate)
    strategy_text = str(strategy or _value(data, "representation_strategy", "strategy", default="")).lower()
    if any(word in strategy_text for word in ("data", "quantitative", "chart")):
        return "quantitative_data"
    if any(word in strategy_text for word in ("math", "geometry", "equation")):
        return "mathematical_geometry"
    name = str(_value(data, "semantic_name", "name", "label", default="")).lower()
    keyword_families = (
        (("tree", "plant", "branch", "flower", "coral", "root"), "organic_branching"),
        (("heart", "blood", "water", "fluid", "vessel", "circulation"), "fluid_system"),
        (("engine", "piston", "machine", "gear", "mechanism", "linkage"), "mechanical_linkage"),
        (("house", "building", "castle", "architecture", "structure"), "architecture"),
        (("volcano", "mountain", "terrain", "crater", "ground"), "terrain"),
        (("cloud", "weather", "storm", "atmosphere", "rain", "smoke"), "atmospheric_system"),
        (("network", "resnet", "graph", "connection"), "network"),
        (("mars", "planet", "orbit", "moon", "celestial", "star"), "celestial_body"),
        (("road", "bridge", "data center", "datacenter", "facility", "infrastructure"), "infrastructure"),
        (("chart", "revenue", "data", "series", "quarter"), "quantitative_data"),
        (("triangle", "equation", "theorem", "geometry", "angle"), "mathematical_geometry"),
    )
    for words, family in keyword_families:
        if any(word in name for word in words):
            return family
    return "organic_body"


def _seed(subject_id: str, family: str) -> int:
    digest = hashlib.sha256(f"{family}:{subject_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def _jitter(seed: int, index: int, scale: float = 1.0) -> float:
    value = ((seed >> (index % 24)) ^ (seed * (index + 11))) & 0xFFFF
    return ((value / 65535.0) - 0.5) * scale


@dataclass(frozen=True)
class RepresentationPlan(Mapping[str, Any]):
    """Compiler-ready generated data with a mapping-compatible interface."""

    family: str
    subject_id: str
    render_mode: str
    parts: tuple[Mapping[str, Any], ...]
    svg: Mapping[str, Any]
    three: Mapping[str, Any]
    animations: tuple[Mapping[str, Any], ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": "2.1",
            "family": self.family,
            "subject_id": self.subject_id,
            "render_mode": self.render_mode,
            "parts": [dict(item) for item in self.parts],
            "svg": dict(self.svg),
            "three": dict(self.three),
            "animations": [dict(item) for item in self.animations],
            "metadata": dict(self.metadata),
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)


@dataclass(frozen=True)
class _PartSpec:
    id: str
    role: str
    kind: str
    parent_id: str | None
    position: tuple[float, float, float]
    geometry: Mapping[str, Any]
    palette_role: str = "accent"


_FAMILY_PARTS: dict[str, tuple[tuple[str, str, str | None, tuple[float, float, float]], ...]] = {
    "organic_branching": (
        ("root_system", "polyline", None, (0.50, 0.86, 0.0)),
        ("stem", "polyline", None, (0.50, 0.62, 0.0)),
        ("branch_left", "polyline", "stem", (0.35, 0.45, 0.0)),
        ("branch_right", "polyline", "stem", (0.65, 0.40, 0.0)),
        ("leaf_cluster", "ellipse", "branch_left", (0.25, 0.30, 0.0)),
        ("bud", "circle", "branch_right", (0.75, 0.25, 0.0)),
    ),
    "organic_body": (
        ("body", "ellipse", None, (0.50, 0.52, 0.0)),
        ("core", "circle", "body", (0.50, 0.52, 0.1)),
        ("appendage_left", "polyline", "body", (0.25, 0.52, 0.0)),
        ("appendage_right", "polyline", "body", (0.75, 0.52, 0.0)),
        ("top_feature", "ellipse", "body", (0.50, 0.27, 0.0)),
    ),
    "fluid_system": (
        ("source", "circle", None, (0.12, 0.52, 0.0)),
        ("reservoir", "rect", None, (0.30, 0.52, 0.0)),
        ("conduit", "polyline", None, (0.52, 0.52, 0.0)),
        ("carrier", "circle", "conduit", (0.52, 0.52, 0.1)),
        ("destination", "circle", None, (0.86, 0.52, 0.0)),
    ),
    "mechanical_linkage": (
        ("frame", "rect", None, (0.50, 0.50, 0.0)),
        ("cylinder", "rect", "frame", (0.50, 0.28, 0.1)),
        ("piston", "rect", "cylinder", (0.50, 0.42, 0.2)),
        ("intake_valve", "circle", "cylinder", (0.38, 0.24, 0.2)),
        ("exhaust_valve", "circle", "cylinder", (0.62, 0.24, 0.2)),
        ("crankshaft", "polyline", "frame", (0.50, 0.75, 0.1)),
        ("connecting_rod", "polyline", "piston", (0.50, 0.58, 0.2)),
    ),
    "rigid_assembly": (
        ("ground", "rect", None, (0.50, 0.90, 0.0)),
        ("foundation", "rect", None, (0.50, 0.78, 0.0)),
        ("frame", "rect", "foundation", (0.50, 0.58, 0.0)),
        ("walls", "rect", "frame", (0.50, 0.52, 0.0)),
        ("roof", "polygon", "walls", (0.50, 0.28, 0.0)),
        ("window_grid", "grid", "walls", (0.50, 0.55, 0.1)),
    ),
    "architecture": (
        ("ground", "rect", None, (0.50, 0.90, 0.0)),
        ("foundation", "rect", None, (0.50, 0.78, 0.0)),
        ("structural_frame", "rect", "foundation", (0.50, 0.58, 0.0)),
        ("walls", "rect", "structural_frame", (0.50, 0.52, 0.0)),
        ("roof", "polygon", "walls", (0.50, 0.28, 0.0)),
        ("window_grid", "grid", "walls", (0.50, 0.55, 0.1)),
    ),
    "terrain": (
        ("ground", "polygon", None, (0.50, 0.76, 0.0)),
        ("slope", "polygon", "ground", (0.50, 0.55, 0.0)),
        ("crater", "ellipse", "slope", (0.50, 0.38, 0.1)),
        ("magma_conduit", "polyline", "crater", (0.50, 0.62, 0.1)),
        ("plume", "polyline", "crater", (0.50, 0.20, 0.2)),
        ("lava", "polyline", "slope", (0.68, 0.64, 0.1)),
    ),
    "atmospheric_system": (
        ("cloud_field", "ellipse", None, (0.45, 0.30, 0.0)),
        ("plume", "polyline", "cloud_field", (0.50, 0.45, 0.1)),
        ("rain", "polyline", "cloud_field", (0.50, 0.68, 0.0)),
        ("wind_flow", "polyline", None, (0.50, 0.52, 0.0)),
        ("particle_field", "particles", None, (0.70, 0.40, 0.2)),
    ),
    "network": (
        ("node_a", "circle", None, (0.20, 0.50, 0.0)),
        ("node_b", "circle", None, (0.50, 0.30, 0.0)),
        ("node_c", "circle", None, (0.80, 0.50, 0.0)),
        ("link_ab", "polyline", None, (0.35, 0.40, 0.0)),
        ("link_bc", "polyline", None, (0.65, 0.40, 0.0)),
        ("carrier", "circle", "link_ab", (0.35, 0.40, 0.1)),
    ),
    "celestial_body": (
        ("star", "circle", None, (0.50, 0.50, 0.0)),
        ("planet", "circle", None, (0.78, 0.50, 0.1)),
        ("orbit_path", "arc", "star", (0.50, 0.50, 0.0)),
        ("moon", "circle", "planet", (0.88, 0.43, 0.2)),
    ),
    "infrastructure": (
        ("ground", "rect", None, (0.50, 0.88, 0.0)),
        ("road", "polyline", "ground", (0.50, 0.72, 0.0)),
        ("facility", "rect", None, (0.35, 0.48, 0.0)),
        ("tower", "rect", None, (0.70, 0.42, 0.0)),
        ("pipe", "polyline", "facility", (0.52, 0.58, 0.1)),
        ("cable", "polyline", None, (0.63, 0.28, 0.2)),
    ),
    "quantitative_data": (
        ("axes", "axes", None, (0.50, 0.66, 0.0)),
        ("series", "polyline", "axes", (0.50, 0.45, 0.1)),
        ("bars", "bars", "axes", (0.50, 0.48, 0.1)),
        ("annotation", "label", None, (0.76, 0.20, 0.0)),
    ),
    "mathematical_geometry": (
        ("axes", "axes", None, (0.50, 0.56, 0.0)),
        ("shape", "polygon", None, (0.46, 0.48, 0.1)),
        ("measurement", "polyline", "shape", (0.58, 0.40, 0.2)),
        ("equation", "label", None, (0.72, 0.20, 0.0)),
    ),
}


def _part_geometry(kind: str, position: Sequence[float], index: int, *, value: float | None = None) -> dict[str, Any]:
    x, y, z = _vector(position)
    wobble = _jitter(index * 7919 + 17, index, 0.03)
    if kind == "circle":
        return {"center": [x, y, z], "radius": 0.045 + (index % 3) * 0.012}
    if kind == "ellipse":
        return {"center": [x, y, z], "radius_x": 0.12, "radius_y": 0.07}
    if kind == "rect":
        return {"origin": [x - 0.10, y - 0.06, z], "width": 0.20, "height": 0.12}
    if kind in {"polyline", "arc"}:
        if kind == "arc":
            return {"center": [x, y, z], "radius": 0.28, "start_angle": 0.0, "sweep": math.tau}
        end = [min(0.96, max(0.04, x + 0.16 + wobble)), min(0.96, max(0.04, y - 0.12 + wobble)), z]
        return {"points": [[x - 0.12, min(0.96, y + 0.12), z], [x, y, z], end], "closed": False}
    if kind == "polygon":
        return {"points": [[x - 0.16, y + 0.08, z], [x, y - 0.12, z], [x + 0.16, y + 0.08, z]], "closed": True}
    if kind == "grid":
        return {"origin": [x - 0.12, y - 0.08, z], "columns": 3, "rows": 2, "cell_width": 0.08, "cell_height": 0.08}
    if kind == "axes":
        return {"origin": [x - 0.24, y + 0.18, z], "x_end": [x + 0.24, y + 0.18, z], "y_end": [x - 0.24, y - 0.18, z]}
    if kind == "bars":
        height = _finite(value, 0.25, lower=0.0, upper=1.0)
        return {"origin": [x - 0.18, y + 0.18, z], "width": 0.07, "height": height}
    if kind == "particles":
        return {"center": [x, y, z], "count": 24, "spread": [0.25, 0.18, 0.08]}
    return {"position": [x, y, z]}


def _part_specs(family: str, subject_id: str, data: Mapping[str, Any]) -> tuple[_PartSpec, ...]:
    label = _value(data, "label", "name", "semantic_name", default="")
    try:
        blueprint = build_subject_blueprint(family, subject_id, label=label)
        if blueprint is not None:
            solver = SubjectConstraintSolver()
            solved_positions = solver.solve(blueprint)

        result: list[_PartSpec] = []
        for index, part in enumerate(blueprint.parts):
            pos = solved_positions.get(part.part_id, part.position)
            geometry = dict(part.geometry)
            role = "primary" if index == 0 else "support" if part.parent_id else "secondary"
            result.append(_PartSpec(
                part.part_id,
                role,
                part.kind,
                part.parent_id,
                tuple(_vector(pos)),
                geometry,
                part.palette_role,
            ))
        if result:
            return tuple(result)
    except Exception:
        pass
    seed = _seed(subject_id, family)
    definitions = list(_FAMILY_PARTS.get(family, _FAMILY_PARTS["organic_branching"]))
    supplied = _value(data, "parts", default=())
    if isinstance(supplied, Sequence) and not isinstance(supplied, (str, bytes)):
        existing = {item[0] for item in definitions}
        for index, raw in enumerate(supplied):
            name = raw if isinstance(raw, str) else _value(raw, "id", "name", "semantic_name", default="")
            part_id = _safe_id(name, f"part_{index + 1}")
            if part_id not in existing and len(definitions) < 24:
                definitions.append((part_id, "ellipse", None, (0.18 + (index % 4) * 0.20, 0.25 + (index // 4) * 0.15, 0.0)))
                existing.add(part_id)
    result: list[_PartSpec] = []
    numeric_values = _data_values(data)
    for index, (part_id, kind, parent_id, position) in enumerate(definitions):
        geometry = _part_geometry(kind, position, seed, value=numeric_values[index] if index < len(numeric_values) else None)
        role = "primary" if index == 0 else "support" if parent_id else "secondary"
        palette_role = "accent" if index == 0 else "secondary" if index % 3 else "emphasis"
        result.append(_PartSpec(part_id, role, kind, parent_id, tuple(_vector(position)), geometry, palette_role))
    return tuple(result)


def _data_values(data: Mapping[str, Any]) -> list[float]:
    raw = _value(data, "values", "series", "data", default=())
    if isinstance(raw, Mapping):
        raw = _value(raw, "values", "series", default=())
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    result = []
    for item in raw[:24]:
        value = _value(item, "value", "y", default=item) if isinstance(item, Mapping) else item
        try:
            result.append(_finite(value, 0.0, lower=0.0, upper=1.0))
        except (TypeError, ValueError):
            continue
    return result


def _svg_forms(parts: Sequence[_PartSpec], family: str) -> dict[str, Any]:
    forms: list[dict[str, Any]] = []
    path_descriptors: list[dict[str, Any]] = []
    for part in parts:
        form = {
            "id": part.id,
            "kind": part.kind,
            "geometry": dict(part.geometry),
            "palette_role": part.palette_role,
            "fill_role": "surface" if part.kind in {"circle", "ellipse", "rect", "polygon", "grid", "bars"} else "none",
            "stroke_role": "accent" if part.role == "primary" else "secondary",
        }
        forms.append(form)
        if part.kind in {"polyline", "arc", "polygon", "axes"}:
            path_descriptors.append(dict(form))
    return {"view_box": [0.0, 0.0, 1.0, 1.0], "forms": forms, "path_descriptors": path_descriptors, "family": family}


def _three_child(part: _PartSpec) -> dict[str, Any]:
    primitive = {
        "circle": "sphere", "ellipse": "sphere", "rect": "cube", "polygon": "cone", "polyline": "cylinder", "arc": "torus", "grid": "cube", "axes": "cylinder", "bars": "cube", "particles": "particles", "label": "plane",
    }.get(part.kind, "cube")
    geometry = part.geometry
    if primitive == "particles":
        size = [0.3, 0.2, 0.1]
        extra = {"count": int(_finite(geometry.get("count", 24), 24, lower=1, upper=2000)), "spread": _vector(geometry.get("spread", size))}
    elif primitive == "sphere":
        radius = _finite(geometry.get("radius", 0.12), 0.12, lower=0.01, upper=5.0)
        size, extra = [radius * 2.0] * 3, {"radius": radius}
    elif primitive == "torus":
        size, extra = [0.6, 0.6, 0.08], {"radius": 0.28}
    else:
        size, extra = [0.24, 0.16, 0.16], {}
    return {"id": part.id, "type": primitive, "position": list(part.position), "size": size, "palette_role": part.palette_role, **extra}


def _three_spec(parts: Sequence[_PartSpec], family: str, subject_id: str) -> dict[str, Any]:
    children = [_three_child(part) for part in parts]
    group: dict[str, Any] = {"id": f"{subject_id}_group", "type": "group", "position": [0.0, 0.0, 0.0], "children": children}
    if family == "celestial_body":
        star = next((part for part in parts if part.id in ("star", "mars", "central_body", "mars_planet_body")), None)
        planet = next((part for part in parts if part.id in ("planet", "spacecraft", "spacecraft_orbiter", "ship", "orbiter")), None)
        if star is not None and planet is not None:

            radius = math.sqrt(sum((planet.position[index] - star.position[index]) ** 2 for index in range(3))) or 0.28
            # The center stays still and the child has a non-zero local offset;
            # rotating the group therefore changes the planet's world position.
            group = {
                "id": f"{subject_id}_orbit_center",
                "type": "group",
                "position": list(star.position),
                "children": [dict(_three_child(planet), position=[radius, 0.0, 0.0])],
                "animate": {"property": "rotation.y", "from": 0.0, "to": math.tau, "duration": 4.0, "ease": "linear"},
                "semantic_motion": "orbit_position",
            }
    camera = {"position": [0.0, 0.0, 4.8], "lookAt": [0.0, 0.0, 0.0], "fov": 48.0, "near": 0.1, "far": 40.0}
    return {"groups": [group], "objects": [group], "camera": camera, "cameraAnimate": [], "palette_roles": sorted(PALETTE_ROLES)}


def _event_type(event: Any) -> str:
    raw = str(_value(event, "type", "event_type", "kind", "action", default="") or "").upper().replace("-", "_")
    return {"ORBIT": "PATH_MOTION", "FLOW": "TRANSFER", "MOVE": "TRANSFER", "SCALE": "GROW", "MORPH": "TRANSFORM"}.get(raw, raw)


def _event_duration(event: Any) -> float:
    return _finite(_value(event, "duration", default=1.0), 1.0, lower=0.05, upper=120.0)


def _event_cue(event: Any) -> float:
    return _finite(_value(event, "cue", "offset", "start", default=0.0), 0.0, lower=0.0, upper=3600.0)


def _part_position(parts: Sequence[_PartSpec], value: Any, fallback: Sequence[float] = (0.0, 0.0, 0.0)) -> list[float]:
    if isinstance(value, str):
        for part in parts:
            if part.id == _safe_id(value, ""):
                return list(part.position)
    if isinstance(value, Mapping):
        item_id = _value(value, "id", "object_id", default=None)
        if item_id is not None:
            return _part_position(parts, item_id, fallback)
    return _vector(value, fallback)


def _animation_specs(parts: Sequence[_PartSpec], events: Iterable[Any]) -> tuple[dict[str, Any], ...]:
    by_id = {part.id: part for part in parts}
    result: list[dict[str, Any]] = []
    for event in list(events)[:64] if isinstance(events, Sequence) and not isinstance(events, (str, bytes)) else ():
        kind = _event_type(event)
        duration, cue = _event_duration(event), _event_cue(event)
        params = _value(event, "params", "parameters", default={})
        if not isinstance(params, Mapping):
            params = {}
        object_id = _safe_id(_value(event, "object_id", "subject", "carrier", default=params.get("object_id", params.get("subject", params.get("carrier", "")))), "")
        if kind == "TRANSFER":
            carrier = by_id.get(_safe_id(_value(event, "carrier", "object_id", "subject", default=object_id), ""))
            if carrier is None:
                continue
            source = _part_position(parts, _value(event, "source", default=params.get("source", carrier.position)), carrier.position)
            destination = _part_position(parts, _value(event, "destination", "target", default=params.get("destination", params.get("target", carrier.position))), carrier.position)
            result.append({"kind": "position_path", "object_id": carrier.id, "trajectory": [source, destination], "duration": duration, "cue": cue})
        elif kind == "PATH_MOTION":
            subject = by_id.get(object_id)
            if subject is None:
                continue
            path = _value(event, "path", "trajectory", default=params.get("path", params.get("trajectory", {})))
            path_kind = str(_value(path, "kind", "type", default="line") if isinstance(path, Mapping) else "points").lower()
            if path_kind in {"orbit", "arc", "circular"}:
                center = _part_position(parts, _value(path, "center", default=params.get("center", (0, 0, 0))) if isinstance(path, Mapping) else params.get("center", (0, 0, 0)))
                radius = _finite(_value(path, "radius", default=params.get("radius", 0.28)) if isinstance(path, Mapping) else params.get("radius", 0.28), 0.28, lower=0.01, upper=10.0)
                result.append({"kind": "orbit_position", "object_id": subject.id, "center": center, "radius": radius, "plane": str(_value(path, "plane", "axis", default="xy") if isinstance(path, Mapping) else "xy")[:2], "start_angle": _finite(_value(path, "start_angle", "angle", default=0.0) if isinstance(path, Mapping) else 0.0), "sweep": _finite(_value(path, "sweep", "angle_delta", default=math.tau) if isinstance(path, Mapping) else math.tau), "duration": duration, "cue": cue})
            else:
                raw_points = _value(path, "points", "waypoints", default=()) if isinstance(path, Mapping) else path
                points = [_vector(point) for point in raw_points[:16]] if isinstance(raw_points, Sequence) and not isinstance(raw_points, (str, bytes)) else [list(subject.position), list(subject.position)]
                result.append({"kind": "position_path", "object_id": subject.id, "trajectory": points, "duration": duration, "cue": cue})
        elif kind == "GROW":
            subject = by_id.get(object_id)
            if subject is None:
                continue
            factor = _finite(params.get("factor", params.get("growth_factor", 2.0)), 2.0, lower=0.01, upper=20.0)
            result.append({"kind": "transform", "object_id": subject.id, "property": "scale", "from": [1.0, 1.0, 1.0], "to": [factor, factor, factor], "duration": duration, "cue": cue})
        elif kind == "TRANSFORM":
            subject = by_id.get(object_id)
            if subject is None:
                continue
            transform = params.get("transform", {})
            if not isinstance(transform, Mapping):
                transform = {}
            for property_name in ("position", "rotation", "scale"):
                pair = transform.get(property_name)
                if isinstance(pair, Sequence) and len(pair) >= 2 and not isinstance(pair, (str, bytes)):
                    result.append({"kind": "transform", "object_id": subject.id, "property": property_name, "from": _vector(pair[0], subject.position), "to": _vector(pair[1], subject.position), "duration": duration, "cue": cue})
        elif kind in {"ASSEMBLE", "MERGE"}:
            raw_parts = _value(event, "parts", "sources", default=params.get("parts", params.get("sources", ())))
            ids = [_safe_id(item if isinstance(item, str) else _value(item, "id", default=""), "") for item in raw_parts[:24]] if isinstance(raw_parts, Sequence) and not isinstance(raw_parts, (str, bytes)) else []
            target = _safe_id(_value(event, "target", "result", "whole", default=params.get("target", params.get("result", ""))), "")
            target_position = _part_position(parts, target, (0.5, 0.5, 0.0))
            for item_id in ids:
                if item_id in by_id:
                    result.append({"kind": "position_path", "object_id": item_id, "trajectory": [list(by_id[item_id].position), target_position], "duration": duration, "cue": cue, "semantic": "merge" if kind == "MERGE" else "assemble"})
        elif kind == "PROPAGATE":
            raw_nodes = _value(event, "nodes", default=params.get("nodes", ()))
            ids = [_safe_id(item if isinstance(item, str) else _value(item, "id", default=""), "") for item in raw_nodes[:24]] if isinstance(raw_nodes, Sequence) and not isinstance(raw_nodes, (str, bytes)) else []
            result.append({"kind": "propagation", "object_ids": [item for item in ids if item in by_id], "duration": duration, "cue": cue})
        elif kind == "CAMERA":
            camera = params.get("camera", {})
            if isinstance(camera, Mapping):
                result.append({"kind": "camera", "from": {"position": _vector(_value(params, "from", default={}).get("position", (0, 0, 4.8)) if isinstance(_value(params, "from", default={}), Mapping) else (0, 0, 4.8))}, "to": {"position": _vector(camera.get("position", (0, 0, 4.8)))}, "duration": duration, "cue": cue})
    return tuple(result)


class RepresentationResolver:
    """Resolve semantic subjects into bounded procedural construction data."""

    def resolve(
        self,
        subject: Any,
        *,
        family: str | None = None,
        representation_strategy: str | None = None,
        strategy: str | None = None,
        renderer: str = "hybrid",
        events: Iterable[Any] | None = None,
        state: Any = None,
    ) -> RepresentationPlan:
        data = _subject_dict(subject)
        subject_id = _safe_id(_value(data, "id", "subject_id", default="subject"), "subject")
        selected_family = _infer_family(data, family, representation_strategy or strategy)
        selected_mode = str(renderer or _value(data, "render_strategy", default="hybrid") or "hybrid").lower()
        if selected_mode in {"2d", "vector", "svg"}:
            selected_mode = "svg"
        elif selected_mode in {"3d", "three", "spatial"}:
            selected_mode = "three"
        if selected_mode not in REPRESENTATION_MODES:
            selected_mode = "hybrid"
        parts = _part_specs(selected_family, subject_id, data)
        event_values = events if events is not None else _value(data, "events", default=())
        animations = _animation_specs(parts, event_values)
        svg = _svg_forms(parts, selected_family)
        three = _three_spec(parts, selected_family, subject_id)
        if animations:
            camera_animations = [dict(item) for item in animations if item.get("kind") == "camera"]
            three = {**three, "cameraAnimate": camera_animations}
        metadata = {"semantic_name": _safe_text(_value(data, "semantic_name", "name", default=subject_id), subject_id), "structural": True, "safe": True}
        return RepresentationPlan(
            family=selected_family,
            subject_id=subject_id,
            render_mode=selected_mode,
            parts=tuple({"id": part.id, "role": part.role, "kind": part.kind, "parent_id": part.parent_id, "position": list(part.position), "geometry": dict(part.geometry), "palette_role": part.palette_role} for part in parts),
            svg=svg,
            three=three,
            animations=animations,
            metadata=metadata,
        )


def resolve_representation(subject: Any, **kwargs: Any) -> RepresentationPlan:
    return RepresentationResolver().resolve(subject, **kwargs)


def resolve_subject_representation(subject: Any, **kwargs: Any) -> RepresentationPlan:
    return resolve_representation(subject, **kwargs)


def build_procedural_representation(subject: Any, **kwargs: Any) -> RepresentationPlan:
    return resolve_representation(subject, **kwargs)


safe_procedural_construction = resolve_representation


__all__ = [
    "PALETTE_ROLES",
    "REPRESENTATION_MODES",
    "RepresentationPlan",
    "RepresentationResolver",
    "RepresentationResolverError",
    "STRUCTURAL_FAMILIES",
    "THREE_ANIMATION_PROPERTIES",
    "THREE_PRIMITIVES",
    "build_procedural_representation",
    "normalize_family",
    "resolve_representation",
    "resolve_subject_representation",
    "safe_procedural_construction",
]

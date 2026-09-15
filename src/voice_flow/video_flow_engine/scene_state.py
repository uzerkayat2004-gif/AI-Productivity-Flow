"""Persistent scene state and deterministic semantic event evaluation.

The visual planner describes semantic events, but it must not be allowed to
author animation code.  This module is the small, pure state machine between
that plan and a compiler.  Objects retain stable IDs and every evaluator call
returns a new :class:`SceneState` snapshot; the input state and event are never
mutated.

The implementation intentionally accepts mappings and light-weight objects.
The V2.1 foundation contracts are being introduced beside this module and the
duck-typed boundary lets the state engine work with either those dataclasses or
the current V2 plan objects during the migration.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import copy
import math
from types import MappingProxyType
from typing import Any, Iterable, Iterator, Mapping, Sequence


EPSILON = 1e-9
TAU = math.tau

EVENT_TYPES = frozenset(
    {
        "CREATE",
        "REMOVE",
        "TRANSFORM",
        "TRANSFER",
        "GROW",
        "ASSEMBLE",
        "DISASSEMBLE",
        "PATH_MOTION",
        "PROPAGATE",
        "CONNECT",
        "DISCONNECT",
        "CAMERA",
        "EMPHASIZE",
        "MERGE",
        "SPLIT",
    }
)


class SceneStateError(ValueError):
    """Raised when a state or event cannot be evaluated safely."""


def _value(value: Any, *names: str, default: Any = None) -> Any:
    """Read a field from a mapping or an object without invoking user code."""

    for name in names:
        if isinstance(value, Mapping):
            if name in value:
                return value[name]
        else:
            try:
                result = getattr(value, name)
            except (AttributeError, TypeError):
                continue
            if result is not None and not callable(result):
                return result
    return default


def _finite(value: Any, default: float = 0.0, *, lower: float | None = None, upper: float | None = None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if not math.isfinite(number):
        number = default
    if lower is not None:
        number = max(lower, number)
    if upper is not None:
        number = min(upper, number)
    return number


def _vector(value: Any, fallback: Sequence[float] = (0.0, 0.0, 0.0)) -> tuple[float, float, float]:
    """Normalise a 2D/3D vector to a finite 3-tuple."""

    if isinstance(value, Mapping):
        value = (_value(value, "x", default=fallback[0]), _value(value, "y", default=fallback[1]), _value(value, "z", default=fallback[2]))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values = list(value)
        if len(values) >= 3:
            return tuple(_finite(item, fallback[index]) for index, item in enumerate(values[:3]))  # type: ignore[return-value]
        if len(values) == 2:
            return (_finite(values[0], fallback[0]), _finite(values[1], fallback[1]), fallback[2])
    return tuple(_finite(item, 0.0) for item in fallback)  # type: ignore[return-value]


def _scalar_or_vector(value: Any, fallback: Sequence[float]) -> tuple[float, float, float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        scalar = _finite(value, fallback[0])
        return scalar, scalar, scalar
    return _vector(value, fallback)


def _deepcopy_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return copy.deepcopy(dict(value))


def _interpolate(a: Any, b: Any, progress: float) -> Any:
    """Recursively interpolate finite numeric values in declarative state."""

    p = max(0.0, min(1.0, float(progress)))
    if isinstance(a, bool) or isinstance(b, bool):
        return b if p >= 1.0 else a
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if math.isfinite(float(a)) and math.isfinite(float(b)):
            return float(a) + (float(b) - float(a)) * p
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        keys = set(a) | set(b)
        return {
            key: _interpolate(a.get(key), b.get(key, a.get(key)), p)
            for key in sorted(keys, key=str)
        }
    if isinstance(a, Sequence) and isinstance(b, Sequence) and not isinstance(a, (str, bytes)) and not isinstance(b, (str, bytes)):
        if len(a) == len(b):
            return [_interpolate(left, right, p) for left, right in zip(a, b)]
    return copy.deepcopy(b if p >= 1.0 else a)


def _lerp_vector(a: Sequence[float], b: Sequence[float], progress: float) -> tuple[float, float, float]:
    p = max(0.0, min(1.0, float(progress)))
    return tuple(float(left) + (float(right) - float(left)) * p for left, right in zip(a, b))  # type: ignore[return-value]


def _safe_id(value: Any) -> str:
    text = str(value or "").strip()
    return text[:128]


@dataclass(frozen=True)
class ObjectState:
    """The persistent, compiler-facing state of one conceptual object."""

    id: str
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    geometry: Mapping[str, Any] = field(default_factory=dict)
    visible: bool = True
    opacity: float = 1.0
    semantic_state: str = "default"
    properties: Mapping[str, Any] = field(default_factory=dict)
    parent_id: str | None = None
    children: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _safe_id(self.id))
        object.__setattr__(self, "position", _vector(self.position))
        object.__setattr__(self, "rotation", _vector(self.rotation))
        object.__setattr__(self, "scale", _scalar_or_vector(self.scale, (1.0, 1.0, 1.0)))
        object.__setattr__(self, "geometry", MappingProxyType(_deepcopy_mapping(self.geometry)))
        object.__setattr__(self, "visible", bool(self.visible))
        object.__setattr__(self, "opacity", _finite(self.opacity, 1.0, lower=0.0, upper=1.0))
        object.__setattr__(self, "semantic_state", str(self.semantic_state or "default")[:96])
        object.__setattr__(self, "properties", MappingProxyType(_deepcopy_mapping(self.properties)))
        parent = _value(self, "parent_id", "parent", default=None)
        object.__setattr__(self, "parent_id", _safe_id(parent) or None)
        children = self.children if isinstance(self.children, Sequence) and not isinstance(self.children, (str, bytes)) else ()
        object.__setattr__(self, "children", tuple(_safe_id(item) for item in children if _safe_id(item)))

    @property
    def state(self) -> str:
        """Compatibility alias used by early V2.1 worker contracts."""

        return self.semantic_state

    @property
    def transform(self) -> dict[str, tuple[float, float, float]]:
        return {"position": self.position, "rotation": self.rotation, "scale": self.scale}

    def with_updates(self, **updates: Any) -> "ObjectState":
        return replace(self, **updates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "position": list(self.position),
            "rotation": list(self.rotation),
            "scale": list(self.scale),
            "geometry": copy.deepcopy(dict(self.geometry)),
            "visible": self.visible,
            "opacity": self.opacity,
            "semantic_state": self.semantic_state,
            "properties": copy.deepcopy(dict(self.properties)),
            "parent_id": self.parent_id,
            "children": list(self.children),
        }


def _object_state(value: Any, object_id: Any = None) -> ObjectState:
    if isinstance(value, ObjectState):
        if object_id is None or value.id == _safe_id(object_id):
            return value
        return replace(value, id=_safe_id(object_id))
    raw_id = object_id if object_id is not None else _value(value, "id", "object_id", default="object")
    transform = _value(value, "transform", default={})
    position = _value(value, "position", default=_value(transform, "position", default=(0.0, 0.0, 0.0)))
    rotation = _value(value, "rotation", default=_value(transform, "rotation", default=(0.0, 0.0, 0.0)))
    scale = _value(value, "scale", default=_value(transform, "scale", default=(1.0, 1.0, 1.0)))
    return ObjectState(
        id=_safe_id(raw_id),
        position=_vector(position),
        rotation=_vector(rotation),
        scale=_scalar_or_vector(scale, (1.0, 1.0, 1.0)),
        geometry=_value(value, "geometry", default={}) or {},
        visible=_value(value, "visible", default=True),
        opacity=_value(value, "opacity", default=1.0),
        semantic_state=_value(value, "semantic_state", "state", default="default"),
        properties=_value(value, "properties", default={}) or {},
        parent_id=_value(value, "parent_id", "parent", default=None),
        children=_value(value, "children", default=()) or (),
    )


@dataclass(frozen=True)
class CameraState:
    """Persistent camera state updated by CAMERA events."""

    position: tuple[float, float, float] = (0.0, 0.0, 7.0)
    target: tuple[float, float, float] = (0.0, 0.0, 0.0)
    zoom: float = 1.0
    fov: float = 50.0
    near: float = 0.1
    far: float = 40.0
    semantic_state: str = "static"
    properties: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "position", _vector(self.position, (0.0, 0.0, 7.0)))
        object.__setattr__(self, "target", _vector(self.target))
        object.__setattr__(self, "zoom", _finite(self.zoom, 1.0, lower=0.05, upper=100.0))
        object.__setattr__(self, "fov", _finite(self.fov, 50.0, lower=1.0, upper=179.0))
        object.__setattr__(self, "near", _finite(self.near, 0.1, lower=EPSILON))
        object.__setattr__(self, "far", _finite(self.far, 40.0, lower=self.near + EPSILON))
        object.__setattr__(self, "semantic_state", str(self.semantic_state or "static")[:96])
        object.__setattr__(self, "properties", MappingProxyType(_deepcopy_mapping(self.properties)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": list(self.position),
            "target": list(self.target),
            "zoom": self.zoom,
            "fov": self.fov,
            "near": self.near,
            "far": self.far,
            "semantic_state": self.semantic_state,
            "properties": copy.deepcopy(dict(self.properties)),
        }


def _camera_state(value: Any) -> CameraState:
    if isinstance(value, CameraState):
        return value
    return CameraState(
        position=_value(value, "position", default=(0.0, 0.0, 7.0)),
        target=_value(value, "target", "lookAt", "look_at", default=(0.0, 0.0, 0.0)),
        zoom=_value(value, "zoom", default=1.0),
        fov=_value(value, "fov", default=50.0),
        near=_value(value, "near", default=0.1),
        far=_value(value, "far", default=40.0),
        semantic_state=_value(value, "semantic_state", "state", default="static"),
        properties=_value(value, "properties", default={}) or {},
    )


@dataclass(frozen=True)
class RelationshipState:
    source: str
    target: str
    kind: str
    properties: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _safe_id(self.source))
        object.__setattr__(self, "target", _safe_id(self.target))
        object.__setattr__(self, "kind", str(self.kind or "connects_to").upper()[:48])
        object.__setattr__(self, "properties", MappingProxyType(_deepcopy_mapping(self.properties)))

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target, "kind": self.kind, "properties": copy.deepcopy(dict(self.properties))}


def _relationship(value: Any) -> RelationshipState:
    if isinstance(value, RelationshipState):
        return value
    return RelationshipState(
        source=_value(value, "source", default=""),
        target=_value(value, "target", default=""),
        kind=_value(value, "kind", "type", default="connects_to"),
        properties=_value(value, "properties", default={}) or {},
    )


@dataclass(frozen=True)
class SceneState:
    """A persistent snapshot of all objects, relationships, and camera state."""

    objects: Mapping[str, ObjectState] = field(default_factory=dict)
    relationships: tuple[RelationshipState, ...] = ()
    hierarchy: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    camera: CameraState = field(default_factory=CameraState)
    time: float = 0.0
    properties: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        raw_objects = self.objects if isinstance(self.objects, Mapping) else {}
        objects: dict[str, ObjectState] = {}
        for key, value in raw_objects.items():
            item = _object_state(value, key)
            if item.id:
                objects[item.id] = item
        object.__setattr__(self, "objects", MappingProxyType(objects))
        raw_relationships = self.relationships if isinstance(self.relationships, Sequence) and not isinstance(self.relationships, (str, bytes)) else ()
        object.__setattr__(self, "relationships", tuple(_relationship(item) for item in raw_relationships))
        hierarchy: dict[str, tuple[str, ...]] = {}
        raw_hierarchy = self.hierarchy if isinstance(self.hierarchy, Mapping) else {}
        for parent, children in raw_hierarchy.items():
            child_values = children if isinstance(children, Sequence) and not isinstance(children, (str, bytes)) else ()
            hierarchy[_safe_id(parent)] = tuple(_safe_id(item) for item in child_values if _safe_id(item))
        for item in objects.values():
            if item.parent_id:
                children = list(hierarchy.get(item.parent_id, ()))
                if item.id not in children:
                    children.append(item.id)
                hierarchy[item.parent_id] = tuple(children)
        object.__setattr__(self, "hierarchy", MappingProxyType(hierarchy))
        object.__setattr__(self, "camera", _camera_state(self.camera))
        object.__setattr__(self, "time", _finite(self.time, 0.0, lower=0.0))
        object.__setattr__(self, "properties", MappingProxyType(_deepcopy_mapping(self.properties)))

    @classmethod
    def from_objects(cls, objects: Iterable[Any], **kwargs: Any) -> "SceneState":
        mapped: dict[str, Any] = {}
        for index, item in enumerate(objects):
            object_id = _value(item, "id", "object_id", default=f"object_{index + 1}")
            mapped[_safe_id(object_id)] = item
        return cls(objects=mapped, **kwargs)

    def object(self, object_id: Any) -> ObjectState | None:
        return self.objects.get(_safe_id(object_id))

    def with_updates(self, **updates: Any) -> "SceneState":
        return replace(self, **updates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "objects": {key: item.to_dict() for key, item in sorted(self.objects.items())},
            "relationships": [item.to_dict() for item in self.relationships],
            "hierarchy": {key: list(value) for key, value in sorted(self.hierarchy.items())},
            "camera": self.camera.to_dict(),
            "time": self.time,
            "properties": copy.deepcopy(dict(self.properties)),
        }


@dataclass(frozen=True)
class SceneEvent:
    """Optional typed event helper; mappings are accepted by all public APIs."""

    type: str = "TRANSFORM"
    object_id: str | None = None
    source: str | None = None
    destination: str | None = None
    carrier: str | None = None
    target: str | None = None
    subject: str | None = None
    parts: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    nodes: tuple[str, ...] = ()
    path: Any = None
    transform: Mapping[str, Any] | None = None
    geometry: Mapping[str, Any] | None = None
    from_state: Any = None
    to_state: Any = None
    state_from: Any = None
    state_to: Any = None
    center: Any = None
    radius: float | None = None
    angle: float | None = None
    axis: str | None = None
    positions: Mapping[str, Any] | None = None
    easing: str | None = None
    result: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    cue: float = 0.0
    duration: float = 1.0
    kind: str | None = None

    def __post_init__(self) -> None:
        event_type = str(self.type or self.kind or "TRANSFORM").upper()
        object.__setattr__(self, "type", event_type)
        for field_name in ("object_id", "source", "destination", "carrier", "target", "subject", "result"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _safe_id(value))
        object.__setattr__(self, "parts", tuple(_safe_id(item) for item in self.parts if _safe_id(item)))
        object.__setattr__(self, "sources", tuple(_safe_id(item) for item in self.sources if _safe_id(item)))
        object.__setattr__(self, "nodes", tuple(_safe_id(item) for item in self.nodes if _safe_id(item)))
        object.__setattr__(self, "cue", _finite(self.cue, 0.0, lower=0.0))
        object.__setattr__(self, "duration", _finite(self.duration, 1.0, lower=EPSILON))
        object.__setattr__(self, "params", MappingProxyType(_deepcopy_mapping(self.params)))

    def to_dict(self) -> dict[str, Any]:
        result = {
            "type": self.type,
            "cue": self.cue,
            "duration": self.duration,
            "params": copy.deepcopy(dict(self.params)),
        }
        for name in ("object_id", "source", "destination", "carrier", "target", "subject", "path"):
            value = getattr(self, name)
            if value is not None:
                result[name] = copy.deepcopy(value)
        if self.parts:
            result["parts"] = list(self.parts)
        if self.sources:
            result["sources"] = list(self.sources)
        if self.nodes:
            result["nodes"] = list(self.nodes)
        return result


Event = SceneEvent
StateEvent = SceneEvent
SceneObjectState = ObjectState


def _event_type(event: Any) -> str:
    raw = _value(event, "type", "event_type", "kind", "action", default="TRANSFORM")
    normalized = str(raw or "TRANSFORM").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "ORBIT": "PATH_MOTION",
        "PATH": "PATH_MOTION",
        "FLOW": "TRANSFER",
        "MOVE": "TRANSFER",
        "SCALE": "GROW",
        "MORPH": "TRANSFORM",
        "HIGHLIGHT": "EMPHASIZE",
    }
    return aliases.get(normalized, normalized)


def _event_params(event: Any) -> dict[str, Any]:
    params = _value(event, "params", "parameters", default={})
    result = _deepcopy_mapping(params)
    if isinstance(event, Mapping):
        for key, value in event.items():
            if key not in {"params", "parameters"}:
                result.setdefault(str(key), copy.deepcopy(value))
    else:
        # Typed SceneEvent fields that are not nested under params remain valid
        # event inputs without requiring each evaluator to know its class.
        for key in (
            "object_id", "source", "destination", "carrier", "target", "subject", "parts", "sources", "nodes", "path", "cue", "duration",
            "from_state", "to_state", "state_from", "state_to", "from", "to", "geometry", "transform", "center", "radius", "angle", "axis", "positions", "easing", "mode", "at",
        ):
            value = _value(event, key, default=None)
            if value is not None:
                result.setdefault(key, copy.deepcopy(value))
    return result


def _event_object_id(event: Any, params: Mapping[str, Any], *names: str) -> str:
    value = _value(event, *names, default=None)
    if value is None:
        for name in names:
            value = params.get(name)
            if value is not None:
                break
    return _safe_id(value)


def _event_start(event: Any, params: Mapping[str, Any]) -> float:
    value = _value(event, "cue", "start", "offset", "at", default=None)
    if value is None:
        value = params.get("cue", params.get("start", params.get("offset", params.get("at", 0.0))))
        if isinstance(value, Mapping):
            value = value.get("offset", value.get("time", 0.0))
    return _finite(value, 0.0, lower=0.0)


def _event_duration(event: Any, params: Mapping[str, Any]) -> float:
    value = _value(event, "duration", default=None)
    if value is None:
        value = params.get("duration", 1.0)
    return _finite(value, 1.0, lower=EPSILON)


def event_progress(event: Any, time: float, *, easing: str | None = None) -> float:
    """Return deterministic 0..1 progress for an absolute scene time."""

    params = _event_params(event)
    return _progress_from_params(event, params, time, easing=easing)


def _progress_from_params(event: Any, params: Mapping[str, Any], time: float, *, easing: str | None = None) -> float:
    start = _event_start(event, params)
    duration = _event_duration(event, params)
    raw = (_finite(time, 0.0) - start) / duration
    progress = max(0.0, min(1.0, raw))
    selected = str(easing or _value(event, "easing", "ease", default=params.get("easing", "linear")) or "linear").lower()
    if selected in {"smooth", "smoothstep", "ease", "power2.inout"}:
        progress = progress * progress * (3.0 - 2.0 * progress)
    elif selected in {"ease_in", "power2.in"}:
        progress *= progress
    elif selected in {"ease_out", "power2.out"}:
        progress = 1.0 - (1.0 - progress) * (1.0 - progress)
    return progress


def _copy_state(state: Any) -> SceneState:
    if isinstance(state, SceneState):
        return state
    return SceneState(
        objects=_value(state, "objects", default={}) or {},
        relationships=_value(state, "relationships", default=()) or (),
        hierarchy=_value(state, "hierarchy", default={}) or {},
        camera=_value(state, "camera", "camera_state", default=CameraState()),
        time=_value(state, "time", default=0.0),
        properties=_value(state, "properties", default={}) or {},
    )


def _replace_object(state: SceneState, item: ObjectState) -> SceneState:
    objects = dict(state.objects)
    objects[item.id] = item
    return replace(state, objects=objects)


def _ensure_object(state: SceneState, object_id: str, *, position: Sequence[float] = (0.0, 0.0, 0.0), visible: bool = False) -> SceneState:
    object_id = _safe_id(object_id)
    if not object_id or object_id in state.objects:
        return state
    item = ObjectState(id=object_id, position=_vector(position), visible=visible, opacity=0.0 if not visible else 1.0)
    return _replace_object(state, item)


def _position_from_reference(state: SceneState, value: Any, fallback: Sequence[float] = (0.0, 0.0, 0.0)) -> tuple[float, float, float]:
    if isinstance(value, str):
        item = state.object(value)
        return item.position if item is not None else _vector(fallback)
    if isinstance(value, Mapping) and _value(value, "id", "object_id", default=None) is not None:
        item = state.object(_value(value, "id", "object_id"))
        if item is not None:
            return item.position
    return _vector(value, fallback)


def _set_properties(item: ObjectState, updates: Mapping[str, Any]) -> ObjectState:
    properties = dict(item.properties)
    properties.update(copy.deepcopy(dict(updates)))
    return replace(item, properties=properties)


def _state_pair(params: Mapping[str, Any], *keys: str) -> tuple[Any, Any] | None:
    for key in keys:
        value = params.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 2:
            return value[0], value[1]
        if isinstance(value, Mapping):
            start = _value(value, "from", "start", "initial", default=None)
            end = _value(value, "to", "end", "target", "final", default=None)
            if start is not None and end is not None:
                return start, end
    return None


def _path_kind(path: Any) -> str:
    if isinstance(path, Mapping):
        # semantic mode aliases are normalized by the path builder
        return str(_value(path, "kind", "type", "mode", default="line") or "line").lower().replace("-", "_")
    if isinstance(path, Sequence) and not isinstance(path, (str, bytes)):
        return "points"
    return "line"


def _path_position(state: SceneState, item: ObjectState, path: Any, progress: float, params: Mapping[str, Any]) -> tuple[float, float, float]:
    kind = _path_kind(path)
    if not isinstance(path, Mapping):
        path = {"points": path}
    if kind in {"orbit", "arc", "circular"} or "center" in path and "radius" in path:
        center_ref = _value(path, "center", "around", default=_value(params, "center", "around", default=(0.0, 0.0, 0.0)))
        center = _position_from_reference(state, center_ref)
        radius_value = _value(path, "radius", default=_value(params, "radius", default=None))
        offset = tuple(item.position[index] - center[index] for index in range(3))
        radius = _finite(radius_value, math.hypot(offset[0], offset[1]), lower=EPSILON)
        plane = str(_value(path, "plane", "axis", default=_value(params, "plane", "axis", default="xy")) or "xy").lower()
        start_angle = _value(path, "start_angle", "angle", default=_value(params, "start_angle", "angle", default=None))
        if start_angle is None:
            if plane in {"xz", "y"}:
                start_angle = math.atan2(offset[2], offset[0])
            elif plane in {"yz", "x"}:
                start_angle = math.atan2(offset[2], offset[1])
            else:
                start_angle = math.atan2(offset[1], offset[0])
        start_angle = _finite(start_angle, 0.0)
        sweep = _finite(_value(path, "sweep", "angle_delta", "end_angle", default=_value(params, "sweep", "angle_delta", default=TAU)), TAU)
        angle = start_angle + sweep * progress
        if plane in {"xz", "y"}:
            return center[0] + radius * math.cos(angle), center[1], center[2] + radius * math.sin(angle)
        if plane in {"yz", "x"}:
            return center[0], center[1] + radius * math.cos(angle), center[2] + radius * math.sin(angle)
        return center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle), center[2]
    if kind in {"bezier", "cubic"}:
        points = _value(path, "points", "control_points", default=())
        if isinstance(points, Sequence) and len(points) >= 4:
            p0, p1, p2, p3 = (_vector(points[index]) for index in range(4))
        else:
            p0 = _position_from_reference(state, _value(path, "start", default=item.position), item.position)
            p3 = _position_from_reference(state, _value(path, "end", "destination", default=p0), p0)
            p1 = _lerp_vector(p0, p3, 1.0 / 3.0)
            p2 = _lerp_vector(p0, p3, 2.0 / 3.0)
        u = 1.0 - progress
        return tuple(u**3 * p0[index] + 3 * u**2 * progress * p1[index] + 3 * u * progress**2 * p2[index] + progress**3 * p3[index] for index in range(3))  # type: ignore[return-value]
    points = _value(path, "points", "waypoints", default=None)
    if isinstance(points, Sequence) and not isinstance(points, (str, bytes)) and points:
        vectors = [_vector(point, item.position) for point in points]
        if len(vectors) == 1:
            return vectors[0]
        scaled = progress * (len(vectors) - 1)
        index = min(len(vectors) - 2, max(0, int(math.floor(scaled))))
        return _lerp_vector(vectors[index], vectors[index + 1], scaled - index)
    start = _position_from_reference(state, _value(path, "start", default=item.position), item.position)
    end = _position_from_reference(state, _value(path, "end", "destination", "target", default=start), start)
    return _lerp_vector(start, end, progress)


def _update_transform(item: ObjectState, params: Mapping[str, Any], progress: float) -> ObjectState:
    transform = _value(params, "transform", default={})
    if not isinstance(transform, Mapping):
        transform = {}
    position = item.position
    rotation = item.rotation
    scale = item.scale
    for name, current, fallback in (("position", position, position), ("rotation", rotation, rotation), ("scale", scale, scale)):
        pair = _state_pair(transform, name)
        if pair is None:
            pair = _state_pair(params, f"{name}_from_to")
        if pair is not None:
            start = _scalar_or_vector(pair[0], fallback)
            end = _scalar_or_vector(pair[1], fallback)
            value = _lerp_vector(start, end, progress)
            if name == "position":
                position = value
            elif name == "rotation":
                rotation = value
            else:
                scale = value
    return replace(item, position=position, rotation=rotation, scale=scale)


def _apply_create(state: SceneState, event: Any, params: Mapping[str, Any], progress: float) -> SceneState:
    object_id = _event_object_id(event, params, "object_id", "subject", "target")
    if not object_id:
        raise SceneStateError("CREATE requires object_id")
    existing = state.object(object_id)
    if existing is None:
        state = _ensure_object(state, object_id, position=_position_from_reference(state, params.get("position", (0, 0, 0))), visible=False)
        existing = state.object(object_id)
    assert existing is not None
    item = replace(existing, visible=progress > 0.0 or progress >= 1.0, opacity=progress, semantic_state="creating" if progress < 1.0 else "created")
    return _replace_object(state, item)


def _apply_remove(state: SceneState, event: Any, params: Mapping[str, Any], progress: float) -> SceneState:
    object_id = _event_object_id(event, params, "object_id", "subject", "target")
    item = state.object(object_id)
    if item is None:
        return state
    return _replace_object(state, replace(item, opacity=1.0 - progress, visible=progress < 1.0, semantic_state="removing" if progress < 1.0 else "removed"))


def _apply_transfer(state: SceneState, event: Any, params: Mapping[str, Any], progress: float) -> SceneState:
    carrier_id = _event_object_id(event, params, "carrier", "object_id", "subject")
    item = state.object(carrier_id)
    if item is None:
        raise SceneStateError("TRANSFER requires an existing carrier")
    source_ref = _value(event, "source", default=params.get("source", item.position))
    destination_ref = _value(event, "destination", "target", default=params.get("destination", params.get("target", item.position)))
    start = _position_from_reference(state, source_ref, item.position)
    end = _position_from_reference(state, destination_ref, start)
    updated = replace(item, position=_lerp_vector(start, end, progress), semantic_state="transferring" if progress < 1.0 else "transferred")
    updated = _set_properties(updated, {"event_progress": progress, "transfer_progress": progress, "transfer_source": _safe_id(source_ref) if isinstance(source_ref, str) else None, "transfer_destination": _safe_id(destination_ref) if isinstance(destination_ref, str) else None})
    return _replace_object(state, updated)


def _apply_path_motion(state: SceneState, event: Any, params: Mapping[str, Any], progress: float) -> SceneState:
    subject_id = _event_object_id(event, params, "subject", "object_id", "carrier")
    item = state.object(subject_id)
    if item is None:
        raise SceneStateError("PATH_MOTION requires an existing subject")
    path = _value(event, "path", "trajectory", default=params.get("path", params.get("trajectory", {})))
    if path is None or path == {} or path == () or path == []:
        mode = str(params.get("mode") or "").strip().lower().replace("-", "_")
        if mode == "orbit" or (params.get("center") is not None and params.get("radius") is not None):
            path = {"kind": "orbit", "center": params.get("center"), "radius": params.get("radius"), "plane": params.get("plane", "xy"), "sweep": params.get("sweep", TAU)}
        else:
            path = {"kind": "line", "start": params.get("source", item.position), "end": params.get("destination", item.position)}
    position = _path_position(state, item, path, progress, params)
    updated = replace(item, position=position, semantic_state="moving" if progress < 1.0 else "arrived")
    updated = _set_properties(updated, {"event_progress": progress, "path_progress": progress, "path_kind": _path_kind(path)})
    return _replace_object(state, updated)


def _apply_grow(state: SceneState, event: Any, params: Mapping[str, Any], progress: float) -> SceneState:
    object_id = _event_object_id(event, params, "object_id", "subject", "target")
    item = state.object(object_id)
    if item is None:
        raise SceneStateError("GROW requires an existing subject")
    scale_pair = _state_pair(params, "scale", "size")
    if scale_pair is None:
        start_scale = item.scale
        factor = _finite(params.get("factor", params.get("growth_factor", 2.0)), 2.0, lower=EPSILON)
        end_scale = tuple(value * factor for value in start_scale)
    else:
        start_scale = _scalar_or_vector(scale_pair[0], item.scale)
        end_scale = _scalar_or_vector(scale_pair[1], item.scale)
    geometry_pair = _state_pair(params, "geometry", "shape")
    if geometry_pair is None:
        geometry_start = dict(item.geometry)
        geometry_end = dict(geometry_start)
        changed = False
        for key in ("radius", "width", "height", "depth", "size", "length"):
            if key in geometry_start and isinstance(geometry_start[key], (int, float)):
                geometry_end[key] = float(geometry_start[key]) * 2.0
                changed = True
        if not changed:
            geometry_start.setdefault("growth", 0.0)
            geometry_end["growth"] = 1.0
    else:
        geometry_start, geometry_end = geometry_pair
        if not isinstance(geometry_start, Mapping):
            geometry_start = dict(item.geometry)
        if not isinstance(geometry_end, Mapping):
            geometry_end = dict(geometry_start)
    updated = replace(item, scale=_lerp_vector(start_scale, end_scale, progress), geometry=_interpolate(geometry_start, geometry_end, progress), semantic_state="growing" if progress < 1.0 else "grown", visible=True, opacity=max(item.opacity, progress))
    updated = _set_properties(updated, {"event_progress": progress, "growth_progress": progress})
    return _replace_object(state, updated)


def _apply_transform(state: SceneState, event: Any, params: Mapping[str, Any], progress: float) -> SceneState:
    object_id = _event_object_id(event, params, "object_id", "subject", "target")
    item = state.object(object_id)
    if item is None:
        raise SceneStateError("TRANSFORM requires an existing subject")
    updated = _update_transform(item, params, progress)
    geometry_pair = _state_pair(params, "geometry", "shape")
    geometry = updated.geometry
    if geometry_pair is not None:
        geometry = _interpolate(geometry_pair[0], geometry_pair[1], progress)
    from_state = _value(event, "from_state", default=params.get("from_state", params.get("state_from", item.semantic_state)))
    to_state = _value(event, "to_state", default=params.get("to_state", params.get("state_to", params.get("state", "transformed"))))
    state_value = str(to_state if progress >= 1.0 else from_state or item.semantic_state)[:96]
    updated = replace(updated, geometry=geometry, semantic_state=state_value)
    updated = _set_properties(updated, {"event_progress": progress, "transform_progress": progress, "target_state": copy.deepcopy(to_state)})
    return _replace_object(state, updated)


def _part_ids(event: Any, params: Mapping[str, Any], *, merge: bool = False) -> tuple[str, ...]:
    names = ("sources", "parts") if merge else ("parts", "sources")
    for name in names:
        raw = _value(event, name, default=None)
        if raw is None:
            raw = params.get(name)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            result = tuple(_safe_id(item if isinstance(item, str) else _value(item, "id", "object_id", default="")) for item in raw)
            result = tuple(item for item in result if item)
            if result:
                return result
    return ()


def _target_position(state: SceneState, event: Any, params: Mapping[str, Any], target_id: str, fallback: Sequence[float]) -> tuple[float, float, float]:
    target = state.object(target_id)
    if target is not None:
        return target.position
    for key in ("target_position", "result_position", "position"):
        if key in params:
            return _vector(params[key], fallback)
    return _vector(fallback)


def _converge(state: SceneState, event: Any, params: Mapping[str, Any], progress: float, *, merge: bool) -> SceneState:
    part_ids = _part_ids(event, params, merge=merge)
    if not part_ids:
        raise SceneStateError(("MERGE" if merge else "ASSEMBLE") + " requires parts/sources")
    target_id = _event_object_id(event, params, "target", "result", "whole")
    if not target_id:
        target_id = _safe_id(params.get("result_id", "result"))
    initial_positions = [state.object(item_id).position for item_id in part_ids if state.object(item_id) is not None]
    fallback = tuple(sum(position[index] for position in initial_positions) / len(initial_positions) for index in range(3)) if initial_positions else (0.0, 0.0, 0.0)
    target_position = _target_position(state, event, params, target_id, fallback)
    result_state = _ensure_object(state, target_id, position=target_position, visible=False)
    offsets = params.get("offsets", {})
    for index, part_id in enumerate(part_ids):
        item = result_state.object(part_id)
        if item is None:
            continue
        explicit = offsets.get(part_id) if isinstance(offsets, Mapping) else None
        if explicit is None:
            destination = target_position
        else:
            destination = tuple(target_position[axis] + _vector(explicit)[axis] for axis in range(3))
        updated = replace(item, position=_lerp_vector(item.position, destination, progress), semantic_state=("merging" if merge else "assembling") if progress < 1.0 else ("merged" if merge else "assembled"))
        opacity = max(0.0, 1.0 - progress) if merge else item.opacity
        updated = replace(updated, opacity=opacity, visible=opacity > EPSILON)
        updated = _set_properties(updated, {"event_progress": progress, "convergence_progress": progress})
        result_state = _replace_object(result_state, updated)
    result = result_state.object(target_id)
    if result is not None:
        target_opacity = progress if merge or params.get("reveal_result", True) else result.opacity
        result = replace(result, position=target_position, opacity=max(result.opacity if progress <= 0.0 else 0.0, target_opacity), visible=progress > 0.0 or result.visible, semantic_state=("emerging" if progress < 1.0 else ("merged_result" if merge else "assembled_whole")))
        result = _set_properties(result, {"event_progress": progress, "convergence_progress": progress})
        result_state = _replace_object(result_state, result)
    return result_state


def _apply_propagate(state: SceneState, event: Any, params: Mapping[str, Any], progress: float) -> SceneState:
    node_ids = _part_ids(event, params)
    if not node_ids:
        raw = _value(event, "nodes", default=params.get("nodes", params.get("path_nodes", ())))
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            node_ids = tuple(_safe_id(item if isinstance(item, str) else _value(item, "id", default="")) for item in raw if _safe_id(item if isinstance(item, str) else _value(item, "id", default="")))
    if not node_ids:
        one = _event_object_id(event, params, "object_id", "subject", "source")
        node_ids = (one,) if one else ()
    if not node_ids:
        raise SceneStateError("PROPAGATE requires nodes")
    result = state
    count = len(node_ids)
    for index, node_id in enumerate(node_ids):
        item = result.object(node_id)
        if item is None:
            continue
        local_progress = max(0.0, min(1.0, progress * count - index))
        updated = replace(item, semantic_state="propagating" if local_progress < 1.0 else "propagated", opacity=max(item.opacity, 0.35 + local_progress * 0.65))
        updated = _set_properties(updated, {"event_progress": progress, "propagation_progress": local_progress, "propagated": local_progress >= 1.0})
        result = _replace_object(result, updated)
    props = dict(result.properties)
    props["propagation_progress"] = progress
    props["propagation_nodes"] = list(node_ids)
    return replace(result, properties=props)


def _apply_camera(state: SceneState, event: Any, params: Mapping[str, Any], progress: float) -> SceneState:
    current = state.camera
    camera_spec = params.get("camera", {})
    if not isinstance(camera_spec, Mapping):
        camera_spec = {}
    from_spec = params.get("from", params.get("start", {}))
    to_spec = params.get("to", params.get("end", camera_spec))
    if not isinstance(from_spec, Mapping):
        from_spec = {}
    if not isinstance(to_spec, Mapping):
        to_spec = {}
    target_id = _event_object_id(event, params, "target", "subject", "object_id")
    target_position = state.object(target_id).position if target_id and state.object(target_id) is not None else current.target
    start_position = _vector(from_spec.get("position", current.position), current.position)
    end_position = _vector(to_spec.get("position", camera_spec.get("position", current.position)), current.position)
    start_target = _vector(from_spec.get("target", from_spec.get("lookAt", current.target)), current.target)
    end_target = _vector(to_spec.get("target", to_spec.get("lookAt", camera_spec.get("target", target_position))), target_position)
    start_zoom = _finite(from_spec.get("zoom", current.zoom), current.zoom, lower=0.05)
    end_zoom = _finite(to_spec.get("zoom", camera_spec.get("zoom", current.zoom)), current.zoom, lower=0.05)
    start_fov = _finite(from_spec.get("fov", current.fov), current.fov, lower=1.0, upper=179.0)
    end_fov = _finite(to_spec.get("fov", camera_spec.get("fov", current.fov)), current.fov, lower=1.0, upper=179.0)
    updated = replace(current, position=_lerp_vector(start_position, end_position, progress), target=_lerp_vector(start_target, end_target, progress), zoom=start_zoom + (end_zoom - start_zoom) * progress, fov=start_fov + (end_fov - start_fov) * progress, semantic_state="moving" if progress < 1.0 else "settled")
    updated = replace(updated, properties={**dict(current.properties), "event_progress": progress, "camera_progress": progress})
    return replace(state, camera=updated)


def _apply_connection(state: SceneState, event: Any, params: Mapping[str, Any], *, connected: bool) -> SceneState:
    source = _event_object_id(event, params, "source")
    target = _event_object_id(event, params, "target", "destination")
    kind = str(params.get("relationship", params.get("kind", "connects_to")) or "connects_to").upper()
    relationships = [item for item in state.relationships if not (item.source == source and item.target == target and item.kind == kind)]
    if connected:
        relationships.append(RelationshipState(source=source, target=target, kind=kind))
    return replace(state, relationships=tuple(relationships))


def _apply_emphasize(state: SceneState, event: Any, params: Mapping[str, Any], progress: float) -> SceneState:
    object_id = _event_object_id(event, params, "object_id", "subject", "target")
    item = state.object(object_id)
    if item is None:
        return state
    amount = _finite(params.get("amount", 0.35), 0.35, lower=0.0, upper=1.0)
    updated = _set_properties(item, {"emphasis": amount * progress, "event_progress": progress})
    return _replace_object(state, updated)


def evaluate_event(state: SceneState | Mapping[str, Any], event: Any, time: float = 0.0) -> SceneState:
    """Evaluate one event at ``time`` and return a new persistent snapshot."""

    current = _copy_state(state)
    params = _event_params(event)
    return _evaluate_event_preparsed(current, event, params, time)


def _evaluate_event_preparsed(current: SceneState, event: Any, params: Mapping[str, Any], time: float) -> SceneState:
    event_type = _event_type(event)
    if event_type not in EVENT_TYPES:
        raise SceneStateError(f"Unsupported scene event type: {event_type!r}")
    progress = _progress_from_params(event, params, time)
    if event_type == "CREATE":
        result = _apply_create(current, event, params, progress)
    elif event_type == "REMOVE":
        result = _apply_remove(current, event, params, progress)
    elif event_type == "TRANSFER":
        result = _apply_transfer(current, event, params, progress)
    elif event_type == "PATH_MOTION":
        result = _apply_path_motion(current, event, params, progress)
    elif event_type == "GROW":
        result = _apply_grow(current, event, params, progress)
    elif event_type == "TRANSFORM":
        result = _apply_transform(current, event, params, progress)
    elif event_type == "ASSEMBLE":
        result = _converge(current, event, params, progress, merge=False)
    elif event_type == "MERGE":
        result = _converge(current, event, params, progress, merge=True)
    elif event_type == "PROPAGATE":
        result = _apply_propagate(current, event, params, progress)
    elif event_type == "CAMERA":
        result = _apply_camera(current, event, params, progress)
    elif event_type == "CONNECT":
        result = _apply_connection(current, event, params, connected=True)
    elif event_type == "DISCONNECT":
        result = _apply_connection(current, event, params, connected=False)
    elif event_type == "EMPHASIZE":
        result = _apply_emphasize(current, event, params, progress)
    elif event_type == "DISASSEMBLE":
        result = _converge(current, event, params, 1.0 - progress, merge=False)
    elif event_type == "SPLIT":
        result = _apply_propagate(current, event, params, progress)
    else:  # pragma: no cover - exhaustive guard for future event additions
        raise SceneStateError(f"No evaluator for event type: {event_type!r}")
    return replace(result, time=max(0.0, _finite(time, 0.0)))


apply_event = evaluate_event
evaluate_scene_event = evaluate_event


def sample_event(
    state: SceneState | Mapping[str, Any],
    event: Any,
    samples: int = 5,
    *,
    steps: int | None = None,
) -> tuple[SceneState, ...]:
    """Sample an event at deterministic evenly spaced times.

    Event parameters are parsed once and reused for every snapshot; results
    are identical to per-sample evaluation.
    """

    count = steps if steps is not None else samples
    try:
        count = int(count)
    except (TypeError, ValueError, OverflowError):
        count = 2
    count = max(2, min(64, count))
    params = _event_params(event)
    start = _event_start(event, params)
    duration = _event_duration(event, params)
    times = tuple(start + duration * index / (count - 1) for index in range(count))
    return tuple(_evaluate_event_preparsed(_copy_state(state), event, params, moment) for moment in times)


sample_event_states = sample_event


def _distance(first: Sequence[float], second: Sequence[float]) -> float:
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(first, second)))


def _numeric_geometry_delta(first: Mapping[str, Any], second: Mapping[str, Any]) -> float:
    keys = set(first) | set(second)
    delta = 0.0
    for key in keys:
        left, right = first.get(key), second.get(key)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            delta = max(delta, abs(float(left) - float(right)))
        elif isinstance(left, Mapping) and isinstance(right, Mapping):
            delta = max(delta, _numeric_geometry_delta(left, right))
    return delta


@dataclass(frozen=True)
class EventQAMetrics:
    """Deterministic observability report for one semantic event."""

    event_type: str
    duration: float
    sample_count: int
    observed: bool
    max_displacement: float = 0.0
    endpoint_distance: float = 0.0
    geometry_delta: float = 0.0
    state_changed: bool = False
    camera_changed: bool = False
    progress_reached: float = 0.0
    path_radius_error: float = 0.0
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return self.observed

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "duration": self.duration,
            "sample_count": self.sample_count,
            "observed": self.observed,
            "valid": self.valid,
            "max_displacement": self.max_displacement,
            "endpoint_distance": self.endpoint_distance,
            "geometry_delta": self.geometry_delta,
            "state_changed": self.state_changed,
            "camera_changed": self.camera_changed,
            "progress_reached": self.progress_reached,
            "path_radius_error": self.path_radius_error,
            "details": copy.deepcopy(dict(self.details)),
        }


def event_qa_metrics(state: SceneState | Mapping[str, Any], event: Any, *, samples: int = 5, steps: int | None = None) -> EventQAMetrics:
    """Measure whether an event produces the state/geometry change it names.

    Samples are bounded so a hostile or malformed count cannot exhaust memory;
    quality is intentionally identical within the supported range.
    """

    count = steps if steps is not None else samples
    try:
        count = int(count)
    except (TypeError, ValueError, OverflowError):
        count = 5
    if count > 64:
        count = 64
    event_type = _event_type(event)
    snapshots = sample_event(state, event, samples=count)
    initial, final = snapshots[0], snapshots[-1]
    params = _event_params(event)
    duration = _event_duration(event, params)
    object_ids = set(initial.objects) | set(final.objects)
    max_displacement = 0.0
    geometry_delta = 0.0
    state_changed = False
    for object_id in object_ids:
        first, last = initial.object(object_id), final.object(object_id)
        if first is None or last is None:
            state_changed = True
            continue
        max_displacement = max(max_displacement, _distance(first.position, last.position))
        for snapshot in snapshots[1:]:
            sampled = snapshot.object(object_id)
            if sampled is not None:
                max_displacement = max(max_displacement, _distance(first.position, sampled.position))
        geometry_delta = max(geometry_delta, _numeric_geometry_delta(first.geometry, last.geometry), _distance(first.scale, last.scale))
        state_changed = state_changed or first.semantic_state != last.semantic_state or first.opacity != last.opacity or first.properties != last.properties
    camera_changed = initial.camera != final.camera
    endpoint_distance = 0.0
    details: dict[str, Any] = {}
    if event_type == "TRANSFER":
        carrier_id = _event_object_id(event, params, "carrier", "object_id", "subject")
        carrier = final.object(carrier_id)
        destination = _position_from_reference(initial, _value(event, "destination", "target", default=params.get("destination", params.get("target", carrier.position if carrier else (0, 0, 0)))))
        endpoint_distance = _distance(carrier.position, destination) if carrier is not None else math.inf
        observed = max_displacement > EPSILON and endpoint_distance <= 1e-6
    elif event_type == "PATH_MOTION":
        subject_id = _event_object_id(event, params, "subject", "object_id", "carrier")
        positions = [snapshot.object(subject_id).position for snapshot in snapshots if snapshot.object(subject_id) is not None]
        unique_positions = len({tuple(round(value, 8) for value in position) for position in positions})
        observed = unique_positions >= 2 and max_displacement > EPSILON
        path = _value(event, "path", "trajectory", default=params.get("path", params.get("trajectory", {})))
        if path is None or path == {} or path == () or path == []:
            mode = str(params.get("mode") or "").strip().lower().replace("-", "_")
            if mode == "orbit" or (params.get("center") is not None and params.get("radius") is not None):
                path = {"kind": "orbit", "center": params.get("center"), "radius": params.get("radius"), "plane": params.get("plane", "xy"), "sweep": params.get("sweep", TAU)}
            else:
                path = {"kind": "line", "start": params.get("source", (0.0, 0.0, 0.0)), "end": params.get("destination", (0.0, 0.0, 0.0))}
        if _path_kind(path) in {"orbit", "arc", "circular"}:
            center = _position_from_reference(initial, _value(path, "center", default=params.get("center", (0, 0, 0))) if isinstance(path, Mapping) else params.get("center", (0, 0, 0)))
            radius = _finite(_value(path, "radius", default=params.get("radius", None)) if isinstance(path, Mapping) else params.get("radius"), 0.0)
            if radius > EPSILON:
                errors = []
                for position in positions:
                    radial = _distance(position, center)
                    errors.append(abs(radial - radius))
                details["sample_radii"] = [_distance(position, center) for position in positions]
                path_radius_error = max(errors, default=0.0)
            else:
                path_radius_error = 0.0
        else:
            path_radius_error = 0.0
    elif event_type == "GROW":
        observed = geometry_delta > EPSILON or max_displacement > EPSILON or state_changed
    elif event_type == "TRANSFORM":
        observed = state_changed or geometry_delta > EPSILON or max_displacement > EPSILON
    elif event_type in {"ASSEMBLE", "MERGE"}:
        observed = max_displacement > EPSILON or state_changed
        details["converged"] = max_displacement > EPSILON
    elif event_type == "PROPAGATE":
        progress_values = [float(item.properties.get("propagation_progress", 0.0)) for item in final.objects.values()]
        observed = bool(progress_values) and max(progress_values) >= 1.0 - EPSILON
        details["propagation_progress"] = progress_values
    elif event_type == "CAMERA":
        observed = camera_changed and (_distance(initial.camera.position, final.camera.position) > EPSILON or _distance(initial.camera.target, final.camera.target) > EPSILON or abs(initial.camera.zoom - final.camera.zoom) > EPSILON)
    else:
        observed = state_changed or camera_changed or max_displacement > EPSILON
        path_radius_error = 0.0
    if event_type != "PATH_MOTION":
        path_radius_error = 0.0
    return EventQAMetrics(
        event_type=event_type,
        duration=duration,
        sample_count=len(snapshots),
        observed=bool(observed),
        max_displacement=max_displacement,
        endpoint_distance=endpoint_distance,
        geometry_delta=geometry_delta,
        state_changed=state_changed,
        camera_changed=camera_changed,
        progress_reached=event_progress(event, _event_start(event, params) + duration),
        path_radius_error=path_radius_error,
        details=details,
    )


qa_event = event_qa_metrics
measure_event = event_qa_metrics


def evaluate_events(state: SceneState | Mapping[str, Any], events: Iterable[Any], time: float = 0.0) -> SceneState:
    """Apply events in order, retaining persistent IDs between events."""

    result = _copy_state(state)
    for event in events:
        result = evaluate_event(result, event, time)
    return result


def event_observability_report(state: SceneState | Mapping[str, Any], events: Iterable[Any], *, samples: int = 5) -> tuple[EventQAMetrics, ...]:
    return tuple(event_qa_metrics(state, event, samples=samples) for event in events)


__all__ = [
    "CameraState",
    "EVENT_TYPES",
    "Event",
    "EventQAMetrics",
    "ObjectState",
    "RelationshipState",
    "SceneEvent",
    "SceneObjectState",
    "SceneState",
    "SceneStateError",
    "StateEvent",
    "apply_event",
    "evaluate_event",
    "evaluate_events",
    "evaluate_scene_event",
    "event_observability_report",
    "event_progress",
    "event_qa_metrics",
    "measure_event",
    "qa_event",
    "sample_event",
    "sample_event_states",
]

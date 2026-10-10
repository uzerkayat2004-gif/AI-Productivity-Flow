"""Resolution-independent, compiler-facing IR for Visual Engine V2.1.

The V2.1 IR intentionally contains normalized geometry only.  It is safe to
construct from a Visual Scene Program or from the legacy V2 ``ScenePlan``
without importing the planner.  Geometry is resolved by
``layout_solver_v21``; until then an object's box is simply an optional hint
or an empty placeholder.  Logical/pixel conversion belongs to ``SceneSpace``
and is exposed here only as convenience methods for trusted compiler code.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, Sequence

from .scene_space import DEFAULT_SCENE_SPACE, NormalizedRect, Rect, SceneSpace, SceneSpaceError


class SceneIRV21Error(ValueError):
    """Raised when a V2.1 scene cannot be represented as bounded IR."""


def _read(value: Any, *names: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return default
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _text(value: Any, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    return text[:240]


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_box(value: Any, *, default: Rect | None = None) -> Rect:
    if value is None:
        return default if default is not None else Rect(0.0, 0.0, 0.0, 0.0)
    if isinstance(value, Rect):
        return value
    if isinstance(value, Mapping):
        if "box" in value and not {"x", "y", "width", "height"}.issubset(value):
            return _coerce_box(value["box"], default=default)
        try:
            return Rect(value["x"], value["y"], value["width"], value["height"])
        except KeyError as exc:
            raise SceneIRV21Error(f"box is missing {exc.args[0]!r}") from exc
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = tuple(value)
        if len(values) == 4:
            return Rect(*values)
    try:
        return Rect(value.x, value.y, value.width, value.height)
    except AttributeError as exc:
        raise SceneIRV21Error("box must be rectangle-like") from exc


def _coerce_min_size(value: Any) -> tuple[float, float] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        value = (value.get("width"), value.get("height"))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = tuple(value)
        if len(values) == 2:
            result = (_number(values[0]), _number(values[1]))
            if result[0] >= 0 and result[1] >= 0:
                return result
    return None


@dataclass(frozen=True, slots=True)
class SceneObjectV21:
    """A stable semantic object with normalized compiler geometry."""

    id: str
    type: str = "subject"
    label: str = ""
    role: str = "secondary"
    region: str = "auto"
    box: NormalizedRect = field(default_factory=lambda: NormalizedRect(0.0, 0.0, 0.0, 0.0))
    form: str | None = None
    importance: float = 1.0
    min_size: tuple[float, float] | None = None
    min_width: float | None = None
    min_height: float | None = None
    layer: int = 0
    depth: float = 0.0
    parent_id: str | None = None
    visible: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object_id = _text(self.id)
        if not object_id:
            raise SceneIRV21Error("scene object id cannot be empty")
        object.__setattr__(self, "id", object_id[:64])
        object.__setattr__(self, "type", _text(self.type, "subject")[:64])
        object.__setattr__(self, "label", _text(self.label)[:240])
        object.__setattr__(self, "role", _text(self.role, "secondary")[:48])
        object.__setattr__(self, "region", _text(self.region, "auto")[:48])
        try:
            box = _coerce_box(self.box)
        except (SceneIRV21Error, SceneSpaceError) as exc:
            raise SceneIRV21Error(f"invalid box for {object_id!r}") from exc
        object.__setattr__(self, "box", box)
        if self.form is not None:
            object.__setattr__(self, "form", _text(self.form)[:48])
        importance = _number(self.importance, 1.0)
        object.__setattr__(self, "importance", max(0.0, importance))
        min_size = _coerce_min_size(self.min_size)
        object.__setattr__(self, "min_size", min_size)
        for name in ("min_width", "min_height"):
            value = getattr(self, name)
            if value is not None:
                number = _number(value, 0.0)
                if number < 0:
                    raise SceneIRV21Error(f"{name} cannot be negative")
                object.__setattr__(self, name, number)
        try:
            object.__setattr__(self, "layer", int(self.layer))
        except (TypeError, ValueError):
            object.__setattr__(self, "layer", 0)
        object.__setattr__(self, "depth", _number(self.depth, 0.0))
        if self.parent_id is not None:
            object.__setattr__(self, "parent_id", _text(self.parent_id)[:64])
        if not isinstance(self.metadata, Mapping):
            object.__setattr__(self, "metadata", {})
        else:
            object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def center_x(self) -> float:
        return self.box.center_x

    @property
    def center_y(self) -> float:
        return self.box.center_y

    @property
    def is_primary(self) -> bool:
        return self.role.casefold() in {"primary", "hero", "focal", "foreground"}

    @property
    def minimum_size(self) -> tuple[float, float] | None:
        if self.min_size is not None:
            return self.min_size
        if self.min_width is None and self.min_height is None:
            return None
        return (self.min_width or 0.0, self.min_height or 0.0)

    def with_box(self, box: Any) -> "SceneObjectV21":
        return replace(self, box=_coerce_box(box))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "role": self.role,
            "region": self.region,
            "box": self.box.to_dict(),
            "importance": self.importance,
            "layer": self.layer,
            "depth": self.depth,
            "visible": self.visible,
        }
        if self.form is not None:
            result["form"] = self.form
        if self.minimum_size is not None:
            result["min_size"] = list(self.minimum_size)
        if self.parent_id is not None:
            result["parent_id"] = self.parent_id
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result


@dataclass(frozen=True, slots=True)
class SceneRelationshipV21:
    """A semantic edge retained by the layout and trusted compiler."""

    source: str
    target: str
    kind: str
    importance: float = 1.0
    required: bool = False
    label: str = ""

    def __post_init__(self) -> None:
        source = _text(self.source)[:64]
        target = _text(self.target)[:64]
        kind = _text(self.kind)[:64]
        if not source or not target or not kind:
            raise SceneIRV21Error("scene relationships require source, target, and kind")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "importance", max(0.0, _number(self.importance, 1.0)))
        object.__setattr__(self, "label", _text(self.label)[:160])

    @property
    def weight(self) -> float:
        return self.importance

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "importance": self.importance,
            "required": self.required,
            **({"label": self.label} if self.label else {}),
        }


@dataclass(frozen=True, slots=True)
class SceneIRV21:
    """One resolution-independent scene after composition solving."""

    scene_id: str
    objects: tuple[SceneObjectV21, ...] = ()
    relationships: tuple[SceneRelationshipV21, ...] = ()
    space: SceneSpace = DEFAULT_SCENE_SPACE
    composition: str | None = None
    score: float | None = None
    score_breakdown: Mapping[str, float] = field(default_factory=dict)
    purpose: str = ""
    representation_strategy: str = ""
    visual_mode: str = ""
    camera_intent: str | None = None
    narration_anchors: tuple[Any, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        scene_id = _text(self.scene_id, "scene")
        if not scene_id:
            raise SceneIRV21Error("scene_id cannot be empty")
        object.__setattr__(self, "scene_id", scene_id[:64])
        objects = tuple(item if isinstance(item, SceneObjectV21) else coerce_scene_object(item) for item in self.objects)
        relationships = tuple(
            item if isinstance(item, SceneRelationshipV21) else coerce_scene_relationship(item)
            for item in self.relationships
        )
        ids = [item.id for item in objects]
        if len(set(ids)) != len(ids):
            raise SceneIRV21Error(f"scene {scene_id!r} contains duplicate object IDs")
        object.__setattr__(self, "objects", objects)
        object.__setattr__(self, "relationships", relationships)
        if not isinstance(self.space, SceneSpace):
            object.__setattr__(self, "space", DEFAULT_SCENE_SPACE)
        object.__setattr__(self, "composition", _text(self.composition) if self.composition is not None else None)
        if self.score is not None:
            object.__setattr__(self, "score", _number(self.score))
        object.__setattr__(self, "score_breakdown", {str(key): _number(value) for key, value in dict(self.score_breakdown).items()})
        object.__setattr__(self, "purpose", _text(self.purpose))
        object.__setattr__(self, "representation_strategy", _text(self.representation_strategy))
        object.__setattr__(self, "visual_mode", _text(self.visual_mode))
        if self.camera_intent is not None:
            object.__setattr__(self, "camera_intent", _text(self.camera_intent))
        object.__setattr__(self, "narration_anchors", tuple(self.narration_anchors or ()))
        object.__setattr__(self, "metadata", dict(self.metadata) if isinstance(self.metadata, Mapping) else {})

    @property
    def relations(self) -> tuple[SceneRelationshipV21, ...]:
        return self.relationships

    @property
    def object_map(self) -> dict[str, SceneObjectV21]:
        return {item.id: item for item in self.objects}

    def with_boxes(self, boxes: Mapping[str, Any] | Iterable[tuple[str, Any]]) -> "SceneIRV21":
        updates = dict(boxes)
        return replace(
            self,
            objects=tuple(item.with_box(updates[item.id]) if item.id in updates else item for item in self.objects),
        )

    def logical_boxes(self, space: SceneSpace | None = None) -> dict[str, Rect]:
        target_space = space or self.space
        return {item.id: target_space.denormalize(item.box) for item in self.objects}

    def pixel_boxes(self, space: SceneSpace | None = None) -> dict[str, Rect]:
        target_space = space or self.space
        return {item.id: target_space.normalized_to_pixel(item.box) for item in self.objects}

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "version": "2.1",
            "scene_id": self.scene_id,
            "coordinate_space": "normalized",
            "space": self.space.to_dict(),
            "objects": [item.to_dict() for item in self.objects],
            "relationships": [item.to_dict() for item in self.relationships],
        }
        if self.composition is not None:
            result["composition"] = self.composition
        if self.score is not None:
            result["score"] = self.score
        if self.score_breakdown:
            result["score_breakdown"] = dict(self.score_breakdown)
        if self.purpose:
            result["purpose"] = self.purpose
        if self.representation_strategy:
            result["representation_strategy"] = self.representation_strategy
        if self.visual_mode:
            result["visual_mode"] = self.visual_mode
        if self.camera_intent is not None:
            result["camera_intent"] = self.camera_intent
        if self.narration_anchors:
            result["narration_anchors"] = list(self.narration_anchors)
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result


@dataclass(frozen=True, slots=True)
class VideoSceneIRV21:
    """A resolution-independent collection of solved scenes."""

    scenes: tuple[SceneIRV21, ...] = ()
    space: SceneSpace = DEFAULT_SCENE_SPACE

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenes", tuple(item if isinstance(item, SceneIRV21) else coerce_scene_ir_v21(item, space=self.space) for item in self.scenes))
        if not isinstance(self.space, SceneSpace):
            object.__setattr__(self, "space", DEFAULT_SCENE_SPACE)

    @property
    def width(self) -> float:
        """Compatibility metadata; object boxes remain normalized."""

        return self.space.logical_width

    @property
    def height(self) -> float:
        return self.space.logical_height

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": "2.1",
            "coordinate_space": "normalized",
            "space": self.space.to_dict(),
            "scenes": [scene.to_dict() for scene in self.scenes],
        }


# Friendly aliases for callers that do not want the version suffix.
# ``NormalizedBox`` is the public name used by composition callers; it is
# intentionally the same immutable rectangle type as ``NormalizedRect``.
NormalizedBox = NormalizedRect
LogicalBox = NormalizedRect
Box = NormalizedRect
SceneObject = SceneObjectV21
SceneIRObjectV21 = SceneObjectV21
SceneIRObject = SceneObjectV21
SceneRelationship = SceneRelationshipV21
SceneIRRelationshipV21 = SceneRelationshipV21
SceneIRRelationship = SceneRelationshipV21
SceneIR = SceneIRV21
VideoSceneIR = VideoSceneIRV21


def coerce_scene_object(value: Any, *, index: int = 0) -> SceneObjectV21:
    """Convert a V2.1 subject or legacy V2 object into a bounded object spec."""

    if isinstance(value, SceneObjectV21):
        return value
    if isinstance(value, str):
        return SceneObjectV21(id=value, label=value)
    object_id = _read(value, "id", "object_id", "subject_id", default=f"object_{index + 1}")
    semantic_name = _read(value, "semantic_name", "name", "label", default="")
    object_type = _read(value, "type", "structural_family", "family", "subject_type", default="subject")
    role = _read(value, "role", "layer_role", default="secondary")
    region = _read(value, "region", "placement", default="auto")
    form = _read(value, "form", "render_strategy", default=None)
    importance = _read(value, "importance", "prominence", "priority", default=1.0)
    min_size = _read(value, "min_size", "minimum_size", "minimum_dimensions", default=None)
    if min_size is None and (_read(value, "min_width", default=None) is not None or _read(value, "min_height", default=None) is not None):
        min_size = (_read(value, "min_width", default=0.0), _read(value, "min_height", default=0.0))
    return SceneObjectV21(
        id=_text(object_id, f"object_{index + 1}"),
        type=_text(object_type, "subject"),
        label=_text(semantic_name),
        role=_text(role, "secondary"),
        region=_text(region, "auto"),
        box=_coerce_box(_read(value, "box", "bounds", "geometry", default=None)),
        form=_text(form) if form is not None else None,
        importance=_number(importance, 1.0),
        min_size=_coerce_min_size(min_size),
        min_width=_read(value, "min_width", default=None),
        min_height=_read(value, "min_height", default=None),
        layer=int(_number(_read(value, "layer", "z_index", default=0), 0.0)),
        depth=_number(_read(value, "depth", "z", default=0.0), 0.0),
        parent_id=_read(value, "parent_id", "parent", default=None),
        visible=bool(_read(value, "visible", default=True)),
        metadata=_read(value, "metadata", default={}) or {},
    )


def coerce_scene_relationship(value: Any, *, index: int = 0) -> SceneRelationshipV21:
    if isinstance(value, SceneRelationshipV21):
        return value
    source = _read(value, "source", "from", "source_id", default="")
    target = _read(value, "target", "to", "target_id", default="")
    kind = _read(value, "kind", "type", "relationship", default="semantic_connection")
    return SceneRelationshipV21(
        source=_text(source),
        target=_text(target),
        kind=_text(kind, "semantic_connection"),
        importance=_number(_read(value, "importance", "weight", default=1.0), 1.0),
        required=bool(_read(value, "required", default=False)),
        label=_text(_read(value, "label", default="")),
    )


def _sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        # A mapping with semantic fields is one object/relation. A mapping
        # whose keys are IDs is a compact program representation; preserve
        # each key as the object's ID when its value does not already carry
        # one.
        semantic_keys = {"id", "object_id", "subject_id", "source", "target", "scene_id", "semantic_name", "label"}
        if semantic_keys & set(value):
            return (value,)
        result: list[Any] = []
        for key, item in value.items():
            if isinstance(item, Mapping):
                entry = dict(item)
                entry.setdefault("id", key)
                result.append(entry)
            else:
                result.append({"id": key, "semantic_name": item})
        return tuple(result)
    if isinstance(value, (str, bytes)):
        return (value,)
    try:
        return tuple(value)
    except TypeError:
        return (value,)


def coerce_scene_ir_v21(scene: Any, *, space: SceneSpace | None = None) -> SceneIRV21:
    """Coerce a scene-like object without depending on worker-A modules.

    ``visual_program_v21`` is optional during the foundation wave, therefore
    this function reads the stable semantic attributes directly.  It accepts
    mappings, dataclasses, legacy ``ScenePlan`` instances, and future V2.1
    scene objects alike.
    """

    if isinstance(scene, SceneIRV21):
        return scene if space is None else replace(scene, space=space)
    scene_id = _read(scene, "scene_id", "id", default="scene")
    raw_objects = _read(scene, "objects", "subjects", default=None)
    if raw_objects is None:
        world = _read(scene, "world", default=None)
        raw_objects = _read(world, "objects", "subjects", default=()) if world is not None else ()
    objects = tuple(coerce_scene_object(item, index=index) for index, item in enumerate(_sequence(raw_objects)))
    raw_relationships = _read(scene, "relationships", "relations", default=())
    relationships = tuple(coerce_scene_relationship(item, index=index) for index, item in enumerate(_sequence(raw_relationships)))
    target_space = space or _read(scene, "space", "scene_space", default=None) or DEFAULT_SCENE_SPACE
    if not isinstance(target_space, SceneSpace):
        target_space = DEFAULT_SCENE_SPACE
    score_breakdown = _read(scene, "score_breakdown", "composition_scores", default={}) or {}
    return SceneIRV21(
        scene_id=_text(scene_id, "scene"),
        objects=objects,
        relationships=relationships,
        space=target_space,
        composition=_read(scene, "composition", "composition_kind", default=None),
        score=_read(scene, "score", default=None),
        score_breakdown=score_breakdown if isinstance(score_breakdown, Mapping) else {},
        purpose=_read(scene, "purpose", "learning_goal", default=""),
        representation_strategy=_read(scene, "representation_strategy", "representation", default=""),
        visual_mode=_read(scene, "visual_mode", default=""),
        camera_intent=_read(scene, "camera_intent", default=None),
        narration_anchors=_sequence(_read(scene, "narration_anchors", "anchors", default=())),
        metadata=_read(scene, "metadata", default={}) or {},
    )


def scene_to_ir_v21(scene: Any, *, space: SceneSpace | None = None) -> SceneIRV21:
    return coerce_scene_ir_v21(scene, space=space)


def coerce_video_scene_ir_v21(program: Any, *, space: SceneSpace | None = None) -> VideoSceneIRV21:
    if isinstance(program, VideoSceneIRV21):
        return program if space is None else replace(program, space=space)
    raw_scenes = _read(program, "scenes", default=None)
    if raw_scenes is None:
        raw_scenes = (program,)
    target_space = space or _read(program, "space", "scene_space", default=None) or DEFAULT_SCENE_SPACE
    if not isinstance(target_space, SceneSpace):
        target_space = DEFAULT_SCENE_SPACE
    return VideoSceneIRV21(
        scenes=tuple(coerce_scene_ir_v21(scene, space=target_space) for scene in _sequence(raw_scenes)),
        space=target_space,
    )


__all__ = [
    "SceneIR",
    "SceneIRObject",
    "SceneIRObjectV21",
    "NormalizedBox",
    "LogicalBox",
    "Box",
    "SceneIRRelationship",
    "SceneIRRelationshipV21",
    "SceneIRV21",
    "SceneIRV21Error",
    "SceneObject",
    "SceneObjectV21",
    "SceneRelationship",
    "SceneRelationshipV21",
    "VideoSceneIR",
    "VideoSceneIRV21",
    "coerce_scene_ir_v21",
    "coerce_scene_object",
    "coerce_scene_relationship",
    "coerce_video_scene_ir_v21",
    "scene_to_ir_v21",
]





"""Deterministic, composition-aware layout for the V2.1 Scene IR.

The solver is intentionally compiler-owned.  A Visual Scene Program may say
that a subject is primary or that two subjects flow left-to-right, but it may
not provide renderer coordinates.  This module turns those semantic hints
into a small set of deterministic candidates (hero, split, flow, triad, and
grid), rejects candidates that violate hard geometry rules, and scores the
remaining candidates for composition quality.

No V2.1 planner import is required.  ``coerce_scene_ir_v21`` accepts mappings,
legacy V2 ScenePlan instances, and future worker-A program classes through
duck typing, so this foundation can land independently.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil, exp, hypot, isfinite, sqrt
from typing import Any, Iterable, Mapping, Sequence

from .scene_ir_v21 import (
    SceneIRV21,
    SceneObjectV21,
    SceneRelationshipV21,
    VideoSceneIRV21,
    coerce_scene_ir_v21,
    coerce_video_scene_ir_v21,
)
from .scene_space import DEFAULT_SCENE_SPACE, NormalizedRect, Rect, SceneSpace


class LayoutV21Error(ValueError):
    """Raised when no deterministic candidate satisfies hard constraints."""


_EPSILON = 1e-8
_CANDIDATE_ORDER = {"hero": 0, "split": 1, "flow": 2, "triad": 3, "grid": 4}
_HORIZONTAL_RELATIONS = frozenset(
    {
        "flows_to",
        "connects_to",
        "feeds",
        "causes",
        "bypasses",
        "merges_into",
        "transforms_into",
        "depends_on",
        "semantic_connection",
        "left_of",
    }
)
_VERTICAL_RELATIONS = frozenset({"above", "below"})
_NON_DIRECTIONAL_RELATIONS = frozenset({"contains", "part_of", "attached_to", "supports", "orbits", "compares_with"})


@dataclass(frozen=True, slots=True)
class RelationPathV21:
    """A compiler-owned route between two laid-out objects."""

    source: str
    target: str
    kind: str
    points: tuple[tuple[float, float], ...]
    visible: bool = True
    occluded_by: tuple[str, ...] = ()
    importance: float = 1.0

    @property
    def length(self) -> float:
        return sum(hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(self.points, self.points[1:]))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "points": [[float(x), float(y)] for x, y in self.points],
            "visible": self.visible,
            "occluded_by": list(self.occluded_by),
            "importance": self.importance,
        }


@dataclass(frozen=True, slots=True)
class LayoutCandidateV21:
    """One deterministic candidate and its validation/score evidence."""

    strategy: str
    objects: tuple[SceneObjectV21, ...]
    score: float
    hard_valid: bool
    hard_violations: tuple[str, ...] = ()
    score_breakdown: Mapping[str, float] = None  # type: ignore[assignment]
    relation_paths: tuple[RelationPathV21, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "strategy", str(self.strategy))
        object.__setattr__(self, "objects", tuple(self.objects))
        object.__setattr__(self, "score", float(self.score))
        object.__setattr__(self, "hard_violations", tuple(str(item) for item in self.hard_violations))
        object.__setattr__(self, "score_breakdown", dict(self.score_breakdown or {}))
        object.__setattr__(self, "relation_paths", tuple(self.relation_paths))

    @property
    def name(self) -> str:
        return self.strategy

    @property
    def valid(self) -> bool:
        return self.hard_valid

    @property
    def boxes(self) -> dict[str, NormalizedRect]:
        return {item.id: item.box for item in self.objects}

    @property
    def layout(self) -> dict[str, NormalizedRect]:
        return self.boxes

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "score": self.score,
            "hard_valid": self.hard_valid,
            "hard_violations": list(self.hard_violations),
            "score_breakdown": dict(self.score_breakdown),
            "objects": [item.to_dict() for item in self.objects],
            "relation_paths": [item.to_dict() for item in self.relation_paths],
        }


@dataclass(frozen=True, slots=True)
class LayoutSolutionV21:
    """The selected candidate plus all deterministic diagnostics."""

    scene_ir: SceneIRV21
    candidate: LayoutCandidateV21
    candidates: tuple[LayoutCandidateV21, ...] = ()

    @property
    def scene(self) -> SceneIRV21:
        return self.scene_ir

    @property
    def scene_id(self) -> str:
        return self.scene_ir.scene_id

    @property
    def selected_candidate(self) -> LayoutCandidateV21:
        return self.candidate

    @property
    def candidate_name(self) -> str:
        return self.candidate.strategy

    @property
    def objects(self) -> tuple[SceneObjectV21, ...]:
        return self.scene_ir.objects

    @property
    def relationships(self) -> tuple[SceneRelationshipV21, ...]:
        return self.scene_ir.relationships

    @property
    def relations(self) -> tuple[SceneRelationshipV21, ...]:
        return self.scene_ir.relationships

    @property
    def space(self) -> SceneSpace:
        return self.scene_ir.space

    @property
    def composition(self) -> str:
        return self.candidate.strategy

    @property
    def score(self) -> float:
        return self.candidate.score

    @property
    def relation_paths(self) -> tuple[RelationPathV21, ...]:
        return self.candidate.relation_paths

    def to_dict(self) -> dict[str, Any]:
        result = self.scene_ir.to_dict()
        result["selected_candidate"] = self.candidate.to_dict()
        result["candidates"] = [item.to_dict() for item in self.candidates]
        return result


# Short aliases make the module pleasant to use without losing the versioned
# names used by integration code.
RelationPath = RelationPathV21
LayoutCandidate = LayoutCandidateV21
LayoutSolution = LayoutSolutionV21


def _content_bounds(space: SceneSpace) -> NormalizedRect:
    return space.content_rect_normalized


def _ordered_objects(scene: SceneIRV21) -> tuple[SceneObjectV21, ...]:
    """Stable topological order for directional relations.

    Original program order is the final tie-break.  A cyclic relation set is
    left in program order and is subsequently reported as a hard violation;
    the solver never silently invents an order for contradictory semantics.
    """

    objects = tuple(scene.objects)
    ids = [item.id for item in objects]
    index = {item: position for position, item in enumerate(ids)}
    predecessors: dict[str, set[str]] = {item: set() for item in ids}
    followers: dict[str, set[str]] = {item: set() for item in ids}
    for relation in scene.relationships:
        source, target = relation.source, relation.target
        if source not in predecessors or target not in predecessors:
            continue
        edge = _directional_edge(relation)
        if edge is None:
            continue
        source, target = edge
        predecessors[target].add(source)
        followers[source].add(target)
    pending = {item: set(values) for item, values in predecessors.items()}
    ready = sorted((item for item, values in pending.items() if not values), key=index.__getitem__)
    result: list[str] = []
    while ready:
        current = ready.pop(0)
        result.append(current)
        for follower in sorted(followers[current], key=index.__getitem__):
            pending[follower].discard(current)
            if not pending[follower] and follower not in result and follower not in ready:
                ready.append(follower)
        ready.sort(key=index.__getitem__)
    if len(result) != len(ids):
        result = ids
    by_id = {item.id: item for item in objects}
    return tuple(by_id[item] for item in result)


def _directional_edge(relation: SceneRelationshipV21) -> tuple[str, str] | None:
    kind = relation.kind.casefold()
    if kind == "right_of":
        return relation.target, relation.source
    if kind == "below":
        return relation.target, relation.source
    if kind in _HORIZONTAL_RELATIONS or kind in _VERTICAL_RELATIONS:
        return relation.source, relation.target
    return None


def _grid_slots(bounds: Rect, count: int, *, columns: int | None = None, gap: float = 0.018) -> list[Rect]:
    if count <= 0:
        return []
    if columns is None:
        columns = max(1, min(count, int(ceil(sqrt(count * max(bounds.width / max(bounds.height, _EPSILON), 1.0))))))
    columns = max(1, min(int(columns), count))
    rows = int(ceil(count / columns))
    width = (bounds.width - gap * (columns - 1)) / columns
    height = (bounds.height - gap * (rows - 1)) / rows
    slots: list[Rect] = []
    for row in range(rows):
        row_count = min(columns, count - row * columns)
        # Keep the final short row centered to create intentional negative
        # space instead of an accidental left-heavy composition.
        row_width = row_count * width + max(0, row_count - 1) * gap
        start_x = bounds.center_x - row_width / 2.0 if row_count < columns else bounds.x
        for column in range(row_count):
            slots.append(Rect(start_x + column * (width + gap), bounds.y + row * (height + gap), width, height))
    return slots


def _hero_boxes(scene: SceneIRV21, bounds: Rect) -> dict[str, Rect]:
    ordered = _ordered_objects(scene)
    if not ordered:
        return {}
    hero = next((item for item in ordered if item.is_primary), max(ordered, key=lambda item: (item.importance, -ordered.index(item))))
    others = [item for item in ordered if item.id != hero.id]
    if not others:
        width = min(bounds.width * 0.78, bounds.width)
        height = min(bounds.height * 0.88, bounds.height)
        return {hero.id: Rect(bounds.center_x - width / 2, bounds.center_y - height / 2, width, height)}

    gap = min(0.026, bounds.width / 30.0)
    side_width = min(bounds.width * 0.28, max(bounds.width * 0.20, bounds.width / 3.0))
    hero_width = bounds.width - side_width - gap
    hero_height = bounds.height * 0.88
    boxes = {
        hero.id: Rect(bounds.x, bounds.y + (bounds.height - hero_height) / 2.0, hero_width, hero_height)
    }
    side = Rect(bounds.x + hero_width + gap, bounds.y, side_width, bounds.height)
    slots = _grid_slots(side, len(others), columns=1 if len(others) <= 3 else 2, gap=gap)
    boxes.update({item.id: slot for item, slot in zip(others, slots)})
    return boxes


def _split_boxes(scene: SceneIRV21, bounds: Rect) -> dict[str, Rect]:
    ordered = _ordered_objects(scene)
    if len(ordered) <= 1:
        return _hero_boxes(scene, bounds)
    gap = min(0.026, bounds.width / 30.0)
    half_width = (bounds.width - gap) / 2.0
    left = Rect(bounds.x, bounds.y, half_width, bounds.height)
    right = Rect(bounds.x + half_width + gap, bounds.y, half_width, bounds.height)
    split_at = max(1, int(ceil(len(ordered) / 2.0)))
    left_objects, right_objects = ordered[:split_at], ordered[split_at:]
    boxes: dict[str, Rect] = {}
    left_slots = _grid_slots(left, len(left_objects), columns=1 if len(left_objects) <= 3 else 2, gap=gap)
    right_slots = _grid_slots(right, len(right_objects), columns=1 if len(right_objects) <= 3 else 2, gap=gap)
    boxes.update({item.id: slot for item, slot in zip(left_objects, left_slots)})
    boxes.update({item.id: slot for item, slot in zip(right_objects, right_slots)})
    return boxes


def _flow_boxes(scene: SceneIRV21, bounds: Rect) -> dict[str, Rect]:
    ordered = _ordered_objects(scene)
    if not ordered:
        return {}
    columns = min(len(ordered), 4)
    slots = _grid_slots(bounds, len(ordered), columns=columns, gap=min(0.032, bounds.width / 24.0))
    return {item.id: slot for item, slot in zip(ordered, slots)}


def _triad_boxes(scene: SceneIRV21, bounds: Rect) -> dict[str, Rect]:
    ordered = _ordered_objects(scene)
    if len(ordered) > 3:
        return _grid_boxes(scene, bounds)
    if not ordered:
        return {}
    gap = min(0.03, bounds.width / 28.0)
    width = (bounds.width - gap * (len(ordered) - 1)) / len(ordered)
    height = bounds.height * 0.66 if len(ordered) > 1 else bounds.height * 0.84
    y = bounds.center_y - height / 2.0
    return {item.id: Rect(bounds.x + index * (width + gap), y, width, height) for index, item in enumerate(ordered)}


def _grid_boxes(scene: SceneIRV21, bounds: Rect) -> dict[str, Rect]:
    ordered = _ordered_objects(scene)
    slots = _grid_slots(bounds, len(ordered), gap=min(0.024, bounds.width / 28.0))
    return {item.id: slot for item, slot in zip(ordered, slots)}


def _minimum_size(item: SceneObjectV21, space: SceneSpace) -> tuple[float, float]:
    custom = item.minimum_size
    if custom is not None:
        width, height = custom
        # Semantic programs may use normalized values; trusted callers may
        # also provide logical pixels.  Both are bounded and deterministic.
        if width > 1.0:
            width /= space.logical_width
        if height > 1.0:
            height /= space.logical_height
        return max(0.0, width), max(0.0, height)
    role = item.role.casefold()
    object_type = item.type.casefold()
    if role in {"annotation", "support", "background"} or object_type in {"label", "text", "annotation"}:
        return 0.075, 0.058
    if role in {"primary", "hero", "focal"}:
        return 0.15, 0.12
    return 0.10, 0.075


def _overlaps(first: Rect, second: Rect, *, epsilon: float = _EPSILON) -> bool:
    return (
        first.x < second.right - epsilon
        and second.x < first.right - epsilon
        and first.y < second.bottom - epsilon
        and second.y < first.bottom - epsilon
    )


def _hard_violations(scene: SceneIRV21, objects: tuple[SceneObjectV21, ...], space: SceneSpace) -> tuple[str, ...]:
    bounds = _content_bounds(space)
    violations: list[str] = []
    by_id = {item.id: item for item in objects}
    for item in objects:
        box = item.box
        if not space.contains(box, region="content", epsilon=1e-7):
            violations.append(f"bounds:{item.id}")
        minimum_width, minimum_height = _minimum_size(item, space)
        if box.width + _EPSILON < minimum_width:
            violations.append(f"min_width:{item.id}")
        if box.height + _EPSILON < minimum_height:
            violations.append(f"min_height:{item.id}")
        if not isfinite(box.x + box.y + box.width + box.height):
            violations.append(f"invalid_geometry:{item.id}")
    for index, first in enumerate(objects):
        for second in objects[index + 1 :]:
            if _overlaps(first.box, second.box):
                violations.append(f"overlap:{first.id}:{second.id}")
    for relation in scene.relationships:
        source = by_id.get(relation.source)
        target = by_id.get(relation.target)
        if source is None or target is None:
            violations.append(f"unknown_relation:{relation.source}:{relation.target}")
            continue
        edge = _directional_edge(relation)
        if edge is None:
            continue
        first, second = by_id[edge[0]], by_id[edge[1]]
        kind = relation.kind.casefold()
        if kind in _VERTICAL_RELATIONS or kind == "below":
            if first.box.center_y >= second.box.center_y - _EPSILON:
                violations.append(f"edge:{relation.kind}:{relation.source}:{relation.target}")
        else:
            if first.box.center_x >= second.box.center_x - _EPSILON:
                violations.append(f"edge:{relation.kind}:{relation.source}:{relation.target}")
    return tuple(violations)


def _segment_hits_rect(start: tuple[float, float], end: tuple[float, float], rect: Rect) -> bool:
    """Liang-Barsky segment/interior intersection test."""

    dx, dy = end[0] - start[0], end[1] - start[1]
    p = (-dx, dx, -dy, dy)
    q = (start[0] - rect.x, rect.right - start[0], start[1] - rect.y, rect.bottom - start[1])
    u1, u2 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) <= _EPSILON:
            if qi < 0:
                return False
            continue
        t = qi / pi
        if pi < 0:
            if t > u2:
                return False
            u1 = max(u1, t)
        else:
            if t < u1:
                return False
            u2 = min(u2, t)
    # Ignore a route that only touches an endpoint boundary.  The caller
    # excludes the source and target boxes, while unrelated objects count.
    return u1 < u2 - _EPSILON and u2 > _EPSILON and u1 < 1.0 - _EPSILON


def _route_visibility(
    source: SceneObjectV21,
    target: SceneObjectV21,
    relation: SceneRelationshipV21,
    objects: tuple[SceneObjectV21, ...],
    bounds: Rect,
) -> RelationPathV21:
    start = (source.box.center_x, source.box.center_y)
    end = (target.box.center_x, target.box.center_y)
    blockers = [item for item in objects if item.id not in {source.id, target.id}]
    direct = (start, end)
    direct_blockers = tuple(item.id for item in blockers if _segment_hits_rect(start, end, item.box))
    if not direct_blockers:
        return RelationPathV21(source.id, target.id, relation.kind, direct, True, (), relation.importance)

    # Route around a blocked direct path through safe horizontal corridors.
    corridors = (
        max(bounds.y + 0.008, bounds.y),
        min(bounds.bottom - 0.008, bounds.bottom),
        max(bounds.y + 0.04, min(bounds.bottom - 0.04, (start[1] + end[1]) / 2.0)),
    )
    options: list[tuple[float, tuple[tuple[float, float], ...], tuple[str, ...]]] = []
    for corridor in corridors:
        points = (start, (start[0], corridor), (end[0], corridor), end)
        hit_ids = tuple(
            item.id
            for item in blockers
            if any(_segment_hits_rect(a, b, item.box) for a, b in zip(points, points[1:]))
        )
        length = sum(hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))
        options.append((len(hit_ids) * 10.0 + length, points, hit_ids))
    _, points, hit_ids = min(options, key=lambda item: (item[0], item[2], item[1]))
    return RelationPathV21(source.id, target.id, relation.kind, points, not hit_ids, hit_ids, relation.importance)


def _relation_paths(scene: SceneIRV21, objects: tuple[SceneObjectV21, ...], space: SceneSpace) -> tuple[RelationPathV21, ...]:
    by_id = {item.id: item for item in objects}
    bounds = _content_bounds(space)
    paths: list[RelationPathV21] = []
    for relation in scene.relationships:
        source, target = by_id.get(relation.source), by_id.get(relation.target)
        if source is None or target is None:
            continue
        if relation.kind.casefold() in _NON_DIRECTIONAL_RELATIONS:
            continue
        paths.append(_route_visibility(source, target, relation, objects, bounds))
    return tuple(paths)


def _region_score(item: SceneObjectV21, box: Rect, bounds: Rect) -> float:
    region = item.region.casefold().replace("_", "-")
    if region in {"", "auto", "foreground", "background", "middle-third"}:
        return 1.0
    if region in {"left", "left-third"}:
        return 1.0 if box.center_x <= bounds.x + bounds.width / 3.0 else 0.0
    if region in {"center", "centre", "center-third"}:
        return 1.0 if bounds.x + bounds.width / 3.0 <= box.center_x <= bounds.x + bounds.width * 2.0 / 3.0 else 0.0
    if region in {"right", "right-third"}:
        return 1.0 if box.center_x >= bounds.x + bounds.width * 2.0 / 3.0 else 0.0
    if region in {"top", "top-third"}:
        return 1.0 if box.center_y <= bounds.y + bounds.height / 3.0 else 0.0
    if region in {"bottom", "bottom-third"}:
        return 1.0 if box.center_y >= bounds.y + bounds.height * 2.0 / 3.0 else 0.0
    return 1.0


def _score_candidate(
    scene: SceneIRV21,
    strategy: str,
    objects: tuple[SceneObjectV21, ...],
    paths: tuple[RelationPathV21, ...],
    space: SceneSpace,
) -> tuple[float, dict[str, float]]:
    bounds = _content_bounds(space)
    content_area = max(bounds.area, _EPSILON)
    occupied_area = sum(item.box.area for item in objects)
    weighted_area = sum(item.box.area * max(item.importance, 0.1) for item in objects)
    explicit_primary = next((item for item in objects if item.is_primary), None)
    # A sparse physical scene may have no explicit role and still deserves a
    # hero treatment. Dense semantic scenes must not promote an arbitrary
    # object into a giant hero merely because it happens to be first.
    primary = explicit_primary or (max(objects, key=lambda item: (item.importance, -objects.index(item)), default=None) if len(objects) <= 3 else None)

    if primary is None:
        hero_prominence = 0.0
        hierarchy = 0.0
    else:
        hero_fraction = primary.box.area / content_area
        hero_prominence = max(0.0, 1.0 - abs(hero_fraction - 0.42) / 0.42)
        secondary_areas = [item.box.area for item in objects if item.id != primary.id]
        if not secondary_areas:
            hierarchy = 1.0
        else:
            ratio = primary.box.area / max(sum(secondary_areas) / len(secondary_areas), _EPSILON)
            hierarchy = max(0.0, min(1.0, 1.0 - abs(ratio - 2.4) / 2.4))

    utilization = max(0.0, min(1.0, occupied_area / content_area))
    target_utilization = 0.52 if len(objects) <= 3 else 0.66
    utilization_score = max(0.0, 1.0 - abs(utilization - target_utilization) / max(target_utilization, _EPSILON))
    if objects:
        mass_x = sum(item.box.center_x * item.box.area for item in objects) / max(occupied_area, _EPSILON)
        mass_y = sum(item.box.center_y * item.box.area for item in objects) / max(occupied_area, _EPSILON)
        center_distance = hypot((mass_x - bounds.center_x) / bounds.width, (mass_y - bounds.center_y) / bounds.height)
        balance = max(0.0, 1.0 - center_distance * 2.5)
    else:
        balance = 0.0

    relation_visibility = (
        1.0
        if not paths
        else sum((1.0 if item.visible else 0.0) * max(item.importance, 0.1) for item in paths)
        / sum(max(item.importance, 0.1) for item in paths)
    )

    by_id = {item.id: item for item in objects}
    reading_checks: list[float] = []
    for relation in scene.relationships:
        edge = _directional_edge(relation)
        if edge is None or edge[0] not in by_id or edge[1] not in by_id:
            continue
        first, second = by_id[edge[0]], by_id[edge[1]]
        kind = relation.kind.casefold()
        if kind in _VERTICAL_RELATIONS or kind == "below":
            reading_checks.append(1.0 if first.box.center_y < second.box.center_y else 0.0)
        else:
            reading_checks.append(1.0 if first.box.center_x < second.box.center_x else 0.0)
    reading_order = sum(reading_checks) / len(reading_checks) if reading_checks else 1.0
    region_scores = [_region_score(item, item.box, bounds) for item in objects]
    region_alignment = sum(region_scores) / len(region_scores) if region_scores else 0.0

    has_directional_relations = any(_directional_edge(item) is not None for item in scene.relationships)
    strategy_bonus = {
        "hero": 0.09 if len(objects) <= 3 and primary is not None else 0.0,
        "split": 0.08 if len(objects) == 2 else 0.02 if len(objects) in {3, 4} else 0.0,
        # Directional semantics are a stronger signal than merely filling
        # three columns. This keeps flow paths legible and makes the
        # candidate choice explainable in the score breakdown.
        "flow": 0.90 if has_directional_relations else 0.0,
        "triad": 0.08 if len(objects) == 3 and not has_directional_relations else 0.0,
        "grid": 0.35 if len(objects) >= 6 else 0.0,
    }.get(strategy, 0.0)

    breakdown = {
        "hero_prominence": hero_prominence,
        "utilization": utilization_score,
        "balance": balance,
        "hierarchy": hierarchy,
        "relation_visibility": relation_visibility,
        "reading_order": reading_order,
        "region_alignment": region_alignment,
        "strategy_bonus": strategy_bonus,
    }
    score = (
        hero_prominence * 0.21
        + utilization_score * 0.15
        + balance * 0.14
        + hierarchy * 0.14
        + relation_visibility * 0.16
        + reading_order * 0.10
        + region_alignment * 0.05
        + strategy_bonus * 0.05
    )
    # Keep tiny floating-point differences deterministic and readable in
    # artifact JSON.  Candidate-name tie-breaking happens separately.
    return round(score, 9), {key: round(value, 9) for key, value in breakdown.items()}


def _candidate_boxes(scene: SceneIRV21, strategy: str, space: SceneSpace) -> dict[str, Rect]:
    bounds = _content_bounds(space)
    if strategy == "hero":
        return _hero_boxes(scene, bounds)
    if strategy == "split":
        return _split_boxes(scene, bounds)
    if strategy == "flow":
        return _flow_boxes(scene, bounds)
    if strategy == "triad":
        return _triad_boxes(scene, bounds)
    if strategy == "grid":
        return _grid_boxes(scene, bounds)
    raise LayoutV21Error(f"unknown V2.1 layout strategy: {strategy!r}")


def _make_candidate(scene: SceneIRV21, strategy: str, space: SceneSpace) -> LayoutCandidateV21:
    boxes = _candidate_boxes(scene, strategy, space)
    objects = tuple(item.with_box(boxes[item.id]) for item in scene.objects if item.id in boxes)
    violations = _hard_violations(scene, objects, space)
    paths = _relation_paths(scene, objects, space)
    score, breakdown = _score_candidate(scene, strategy, objects, paths, space)
    if violations:
        score = round(score - 1.0 - len(violations) * 0.01, 9)
    return LayoutCandidateV21(
        strategy=strategy,
        objects=objects,
        score=score,
        hard_valid=not violations and len(objects) == len(scene.objects),
        hard_violations=violations,
        score_breakdown=breakdown,
        relation_paths=paths,
    )


def generate_layout_candidates(scene: Any, *, space: SceneSpace | None = None) -> tuple[LayoutCandidateV21, ...]:
    """Generate all deterministic composition candidates in stable order."""

    scene_ir = coerce_scene_ir_v21(scene, space=space)
    target_space = space or scene_ir.space or DEFAULT_SCENE_SPACE
    return tuple(_make_candidate(scene_ir, strategy, target_space) for strategy in _CANDIDATE_ORDER)


def validate_layout(scene: Any, *, space: SceneSpace | None = None) -> tuple[str, ...]:
    """Return hard-constraint violations for a scene's currently stored boxes."""

    scene_ir = coerce_scene_ir_v21(scene, space=space)
    return _hard_violations(scene_ir, scene_ir.objects, space or scene_ir.space)


def score_layout(scene: Any, *, space: SceneSpace | None = None) -> tuple[float, dict[str, float]]:
    """Score an already-laid-out scene using the same deterministic metrics."""

    scene_ir = coerce_scene_ir_v21(scene, space=space)
    target_space = space or scene_ir.space
    paths = _relation_paths(scene_ir, scene_ir.objects, target_space)
    return _score_candidate(scene_ir, scene_ir.composition or "custom", scene_ir.objects, paths, target_space)


def solve_layout_v21(scene: Any, *, space: SceneSpace | None = None) -> LayoutSolutionV21:
    """Select the highest-scoring hard-valid V2.1 candidate."""

    scene_ir = coerce_scene_ir_v21(scene, space=space)
    if not scene_ir.objects:
        raise LayoutV21Error(f"Scene {scene_ir.scene_id!r} has no objects to lay out")
    target_space = space or scene_ir.space or DEFAULT_SCENE_SPACE
    candidates = generate_layout_candidates(scene_ir, space=target_space)
    valid = tuple(item for item in candidates if item.hard_valid)
    if not valid:
        diagnostics = "; ".join(f"{item.strategy}: {', '.join(item.hard_violations) or 'invalid'}" for item in candidates)
        raise LayoutV21Error(f"No V2.1 layout candidate satisfies hard constraints ({diagnostics})")
    selected = max(valid, key=lambda item: (item.score, -_CANDIDATE_ORDER.get(item.strategy, 99)))
    resolved = replace(
        scene_ir,
        objects=selected.objects,
        space=target_space,
        composition=selected.strategy,
        score=selected.score,
        score_breakdown=selected.score_breakdown,
    )
    return LayoutSolutionV21(scene_ir=resolved, candidate=selected, candidates=candidates)


def layout_scene_v21(scene: Any, *, space: SceneSpace | None = None) -> SceneIRV21:
    """Convenience API returning the selected resolved SceneIR directly."""

    return solve_layout_v21(scene, space=space).scene_ir


def layout_video_program_v21(program: Any, *, space: SceneSpace | None = None) -> VideoSceneIRV21:
    """Solve every scene in a program-like object with one canonical space."""

    program_ir = coerce_video_scene_ir_v21(program, space=space)
    target_space = space or program_ir.space
    scenes = tuple(solve_layout_v21(scene, space=target_space).scene_ir for scene in program_ir.scenes)
    return VideoSceneIRV21(scenes=scenes, space=target_space)


# Compatibility spellings useful to integration code and tests.
solve_layout = solve_layout_v21
solve_scene_layout = solve_layout_v21
layout_scene = layout_scene_v21
layout_program_v21 = layout_video_program_v21
layout_video_plan_v21 = layout_video_program_v21
generate_candidates = generate_layout_candidates
check_hard_constraints = validate_layout


__all__ = [
    "LayoutCandidate",
    "LayoutCandidateV21",
    "LayoutSolution",
    "LayoutSolutionV21",
    "LayoutV21Error",
    "RelationPath",
    "RelationPathV21",
    "check_hard_constraints",
    "generate_candidates",
    "generate_layout_candidates",
    "layout_program_v21",
    "layout_scene",
    "layout_scene_v21",
    "layout_video_plan_v21",
    "layout_video_program_v21",
    "score_layout",
    "solve_layout",
    "solve_scene_layout",
    "solve_layout_v21",
    "validate_layout",
]





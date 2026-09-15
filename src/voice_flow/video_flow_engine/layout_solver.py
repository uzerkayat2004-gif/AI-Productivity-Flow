"""Deterministic layout of semantic V2 plans into compiler-owned scene geometry."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .scene_ir import Box, SceneIR, SceneIRBeat, SceneIRObject, SceneIRRelationship, VideoSceneIR
from .visual_plan_v2 import ScenePlan, VideoVisualPlanV2


_GRID_COLUMNS = 6
_GRID_ROWS = 4
_GAP = 8


class LayoutV2Error(ValueError):
    """Raised when semantic constraints cannot fit safely in the frame."""


@dataclass(frozen=True)
class _Frame:
    width: int
    height: int
    caption_safe_bottom: int
    left: int
    top: int
    right: int
    bottom: int
    cell_width: int
    cell_height: int


def layout_video_plan(
    plan: VideoVisualPlanV2,
    *,
    width: int = 1920,
    height: int = 1080,
    caption_safe_bottom: int = 170,
) -> VideoSceneIR:
    """Resolve a validated semantic plan into stable, caption-safe scene geometry."""
    if not isinstance(plan, VideoVisualPlanV2):
        raise LayoutV2Error("layout_video_plan requires a VideoVisualPlanV2")
    frame = _make_frame(width, height, caption_safe_bottom)
    prior_objects: dict[str, SceneIRObject] = {}
    resolved_scenes: list[SceneIR] = []

    for scene in plan.scenes:
        carried = _carried_objects(scene, prior_objects)
        local_objects = _layout_scene(scene, carried, frame)
        relationships = tuple(
            SceneIRRelationship(source=item.source, target=item.target, kind=item.kind)
            for item in scene.relationships
        )
        beats = tuple(
            SceneIRBeat(
                order=item.order,
                phase=item.phase,
                action=item.action,
                object_id=item.object_id,
                reason=item.reason,
            )
            for item in scene.beats
        )
        result = SceneIR(
            scene_id=scene.scene_id,
            storyboard_section_id=scene.storyboard_section_id,
            learning_goal=scene.learning_goal,
            visual_thesis=scene.visual_thesis,
            visual_mode=scene.visual_mode,
            objects=tuple([*carried, *local_objects]),
            relationships=relationships,
            beats=beats,
            camera_intent=scene.camera_intent,
            transition=scene.transition,
        )
        resolved_scenes.append(result)
        for item in local_objects:
            prior_objects[item.id] = item
        for item in carried:
            prior_objects[item.id] = item

    return VideoSceneIR(
        width=frame.width,
        height=frame.height,
        caption_safe_bottom=frame.caption_safe_bottom,
        scenes=tuple(resolved_scenes),
    )


def _make_frame(width: int, height: int, caption_safe_bottom: int) -> _Frame:
    if any(type(value) is not int for value in (width, height, caption_safe_bottom)):
        raise LayoutV2Error("Frame dimensions and caption_safe_bottom must be integers")
    if width <= 0 or height <= 0 or caption_safe_bottom < 0 or caption_safe_bottom >= height:
        raise LayoutV2Error("Frame dimensions or caption-safe area are invalid")
    margin_x = max(24, min(96, width // 20))
    margin_y = max(24, min(72, height // 20))
    left, right = margin_x, width - margin_x
    top, bottom = margin_y, height - caption_safe_bottom - margin_y
    usable_width, usable_height = right - left, bottom - top
    cell_width, cell_height = usable_width // _GRID_COLUMNS, usable_height // _GRID_ROWS
    if cell_width <= _GAP * 2 or cell_height <= _GAP * 2:
        raise LayoutV2Error("Frame is too small for a caption-safe V2 layout")
    return _Frame(
        width=width,
        height=height,
        caption_safe_bottom=caption_safe_bottom,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        cell_width=cell_width,
        cell_height=cell_height,
    )


def _carried_objects(scene: ScenePlan, prior_objects: dict[str, SceneIRObject]) -> tuple[SceneIRObject, ...]:
    carried: list[SceneIRObject] = []
    for object_id in scene.continuity.carry_forward:
        prior = prior_objects.get(object_id)
        if prior is None:
            raise LayoutV2Error(f"Scene {scene.scene_id!r} cannot carry unknown object {object_id!r}")
        carried.append(replace(prior, carried=True))
    return tuple(carried)


def _layout_scene(scene: ScenePlan, carried: tuple[SceneIRObject, ...], frame: _Frame) -> tuple[SceneIRObject, ...]:
    local_specs = tuple(scene.objects)
    all_ids = [item.id for item in carried] + [item.id for item in local_specs]
    if len(set(all_ids)) != len(all_ids):
        raise LayoutV2Error(f"Scene {scene.scene_id!r} contains duplicate object IDs")

    bounds = {item.id: _region_bounds(item.region) for item in local_specs}
    fixed_cells = {item.id: _box_cell(item.box, frame) for item in carried}
    for object_id, (column, row) in fixed_cells.items():
        bounds[object_id] = (column, column, row, row)

    horizontal, vertical = _constraint_edges(scene, set(all_ids))
    columns = _resolve_axis(all_ids, bounds, fixed_cells, horizontal, axis=0)
    rows = _resolve_axis(all_ids, bounds, fixed_cells, vertical, axis=1)
    _allocate_unique_cells(local_specs, carried, bounds, columns, rows, horizontal, vertical, frame)

    result = tuple(
        SceneIRObject(
            id=item.id,
            type=item.type,
            label=item.label,
            role=item.role,
            region=item.region,
            box=_cell_box(columns[item.id], rows[item.id], frame),
            form=item.form,
        )
        for item in local_specs
    )
    _validate_scene_geometry(scene, result, carried, frame, horizontal, vertical)
    return result


def _constraint_edges(scene: ScenePlan, known_ids: set[str]) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    horizontal: set[tuple[str, str]] = set()
    vertical: set[tuple[str, str]] = set()
    for relation in scene.relationships:
        if relation.source not in known_ids or relation.target not in known_ids:
            raise LayoutV2Error(f"Scene {scene.scene_id!r} references an unavailable object")
        if relation.kind in {"left_of", "flows_to", "connects_to"}:
            horizontal.add((relation.source, relation.target))
        elif relation.kind == "right_of":
            horizontal.add((relation.target, relation.source))
        elif relation.kind == "above":
            vertical.add((relation.source, relation.target))
        elif relation.kind == "below":
            vertical.add((relation.target, relation.source))
    return tuple(sorted(horizontal)), tuple(sorted(vertical))


def _resolve_axis(
    object_ids: list[str],
    bounds: dict[str, tuple[int, int, int, int]],
    fixed_cells: dict[str, tuple[int, int]],
    edges: tuple[tuple[str, str], ...],
    *,
    axis: int,
) -> dict[str, int]:
    predecessors: dict[str, set[str]] = {item: set() for item in object_ids}
    followers: dict[str, set[str]] = {item: set() for item in object_ids}
    for source, target in edges:
        predecessors[target].add(source)
        followers[source].add(target)
    ordered = _topological_order(object_ids, predecessors, followers)
    values: dict[str, int] = {}
    for object_id in ordered:
        low, high = (bounds[object_id][0], bounds[object_id][1]) if axis == 0 else (bounds[object_id][2], bounds[object_id][3])
        fixed = fixed_cells.get(object_id)
        value = fixed[axis] if fixed is not None else low
        if predecessors[object_id]:
            value = max(value, max(values[item] + 1 for item in predecessors[object_id]))
        if value > high:
            dimension = "horizontal" if axis == 0 else "vertical"
            raise LayoutV2Error(f"Scene constraints cannot fit in the {dimension} layout")
        values[object_id] = value
    return values


def _topological_order(
    object_ids: list[str],
    predecessors: dict[str, set[str]],
    followers: dict[str, set[str]],
) -> list[str]:
    pending = {item: set(predecessors[item]) for item in object_ids}
    ready = sorted(item for item in object_ids if not pending[item])
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for follower in sorted(followers[current]):
            pending[follower].discard(current)
            if not pending[follower] and follower not in ordered and follower not in ready:
                ready.append(follower)
        ready.sort()
    if len(ordered) != len(object_ids):
        raise LayoutV2Error("Scene has contradictory semantic layout constraints")
    return ordered


def _allocate_unique_cells(
    local_specs: tuple[Any, ...],
    carried: tuple[SceneIRObject, ...],
    bounds: dict[str, tuple[int, int, int, int]],
    columns: dict[str, int],
    rows: dict[str, int],
    horizontal: tuple[tuple[str, str], ...],
    vertical: tuple[tuple[str, str], ...],
    frame: _Frame,
) -> None:
    occupied = {_box_cell(item.box, frame) for item in carried}
    if len(occupied) != len(carried):
        raise LayoutV2Error("Carried objects overlap in the prior scene state")

    for item in sorted(local_specs, key=lambda spec: spec.id):
        column_low, column_high, row_low, row_high = bounds[item.id]
        candidates = [
            (column, row)
            for column in range(column_low, column_high + 1)
            for row in range(row_low, row_high + 1)
        ]
        candidates.sort(
            key=lambda cell: (
                abs(cell[0] - columns[item.id]) + abs(cell[1] - rows[item.id]),
                cell[1],
                cell[0],
            )
        )
        for column, row in candidates:
            if (column, row) in occupied:
                continue
            if not _satisfies_edges(item.id, column, row, columns, rows, horizontal, vertical):
                continue
            columns[item.id], rows[item.id] = column, row
            occupied.add((column, row))
            break
        else:
            raise LayoutV2Error("Scene constraints cannot allocate non-overlapping object boxes")


def _satisfies_edges(
    object_id: str,
    column: int,
    row: int,
    columns: dict[str, int],
    rows: dict[str, int],
    horizontal: tuple[tuple[str, str], ...],
    vertical: tuple[tuple[str, str], ...],
) -> bool:
    for source, target in horizontal:
        if source == object_id and column >= columns[target]:
            return False
        if target == object_id and columns[source] >= column:
            return False
    for source, target in vertical:
        if source == object_id and row >= rows[target]:
            return False
        if target == object_id and rows[source] >= row:
            return False
    return True

def _region_bounds(region: str) -> tuple[int, int, int, int]:
    column_low, column_high = 0, _GRID_COLUMNS - 1
    row_low, row_high = 0, _GRID_ROWS - 1
    if region == "left":
        column_low, column_high = 0, 1
    elif region == "center":
        column_low, column_high = 2, 3
    elif region == "right":
        column_low, column_high = 4, 5
    elif region in {"top", "top-third"}:
        row_low, row_high = 0, 0
    elif region == "middle-third":
        row_low, row_high = 1, 2
    elif region in {"bottom", "bottom-third"}:
        row_low, row_high = 3, 3
    return column_low, column_high, row_low, row_high


def _box_cell(box: Box, frame: _Frame) -> tuple[int, int]:
    column = min(_GRID_COLUMNS - 1, max(0, (box.x + box.width // 2 - frame.left) // frame.cell_width))
    row = min(_GRID_ROWS - 1, max(0, (box.y + box.height // 2 - frame.top) // frame.cell_height))
    return int(column), int(row)


def _cell_box(column: int, row: int, frame: _Frame) -> Box:
    return Box(
        x=frame.left + column * frame.cell_width + _GAP,
        y=frame.top + row * frame.cell_height + _GAP,
        width=frame.cell_width - _GAP * 2,
        height=frame.cell_height - _GAP * 2,
    )


def _validate_scene_geometry(
    scene: ScenePlan,
    local: tuple[SceneIRObject, ...],
    carried: tuple[SceneIRObject, ...],
    frame: _Frame,
    horizontal: tuple[tuple[str, str], ...],
    vertical: tuple[tuple[str, str], ...],
) -> None:
    for item in local:
        _validate_box(item.box, frame)
        _validate_region(item, frame)
    for index, first in enumerate(local):
        for second in local[index + 1 :]:
            if _overlaps(first.box, second.box):
                raise LayoutV2Error(f"Scene {scene.scene_id!r} has overlapping local objects")

    objects = {item.id: item for item in [*carried, *local]}
    for source, target in horizontal:
        if _center_x(objects[source].box) >= _center_x(objects[target].box):
            raise LayoutV2Error(f"Scene {scene.scene_id!r} violates a horizontal semantic constraint")
    for source, target in vertical:
        if _center_y(objects[source].box) >= _center_y(objects[target].box):
            raise LayoutV2Error(f"Scene {scene.scene_id!r} violates a vertical semantic constraint")


def _validate_box(box: Box, frame: _Frame) -> None:
    if box.x < frame.left or box.y < frame.top or box.right > frame.right or box.bottom > frame.bottom:
        raise LayoutV2Error("Scene object falls outside the safe frame")
    if box.bottom > frame.height - frame.caption_safe_bottom:
        raise LayoutV2Error("Scene object overlaps the caption-safe area")


def _validate_region(item: SceneIRObject, frame: _Frame) -> None:
    center_x, center_y = _center_x(item.box), _center_y(item.box)
    third_width = (frame.right - frame.left) / 3
    third_height = (frame.bottom - frame.top) / 3
    if item.region == "left" and center_x >= frame.left + third_width:
        raise LayoutV2Error("Left-region object was not placed left")
    if item.region == "center" and not frame.left + third_width <= center_x < frame.left + third_width * 2:
        raise LayoutV2Error("Center-region object was not placed centrally")
    if item.region == "right" and center_x < frame.left + third_width * 2:
        raise LayoutV2Error("Right-region object was not placed right")
    if item.region in {"top", "top-third"} and center_y >= frame.top + third_height:
        raise LayoutV2Error("Top-region object was not placed at the top")
    if item.region == "middle-third" and not frame.top + third_height <= center_y < frame.top + third_height * 2:
        raise LayoutV2Error("Middle-region object was not placed centrally")
    if item.region in {"bottom", "bottom-third"} and center_y < frame.top + third_height * 2:
        raise LayoutV2Error("Bottom-region object was not placed at the bottom")


def _overlaps(first: Box, second: Box) -> bool:
    return first.x < second.right and second.x < first.right and first.y < second.bottom and second.y < first.bottom


def _center_x(box: Box) -> int:
    return box.x + box.width // 2


def _center_y(box: Box) -> int:
    return box.y + box.height // 2


__all__ = ["LayoutV2Error", "layout_video_plan"]

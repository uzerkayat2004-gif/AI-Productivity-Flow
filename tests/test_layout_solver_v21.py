from __future__ import annotations

from dataclasses import dataclass

import pytest

from voice_flow.video_flow_engine.layout_solver_v21 import (
    LayoutV21Error,
    generate_layout_candidates,
    layout_scene_v21,
    solve_layout_v21,
    validate_layout,
)
from voice_flow.video_flow_engine.scene_space import SceneSpace


def _object(object_id: str, *, role: str = "secondary", importance: float = 1.0) -> dict[str, object]:
    return {"id": object_id, "semantic_name": object_id.replace("_", " "), "role": role, "importance": importance}


def _scene(objects: list[dict[str, object]], relationships: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {"scene_id": "scene", "subjects": objects, "relationships": relationships or []}


def _overlaps(first, second) -> bool:
    return first.x < second.right and second.x < first.right and first.y < second.bottom and second.y < first.bottom


def test_single_primary_subject_gets_intentional_hero_scale() -> None:
    solution = solve_layout_v21(_scene([_object("volcano", role="primary", importance=4)]))
    item = solution.objects[0]
    content_area = solution.space.content_rect_normalized.area

    assert solution.composition == "hero"
    assert item.box.area / content_area > 0.40
    assert not validate_layout(solution.scene_ir)


def test_flow_candidate_keeps_directional_paths_visible_and_ordered() -> None:
    scene = _scene(
        [_object("source"), _object("middle"), _object("target")],
        [
            {"source": "source", "target": "middle", "kind": "flows_to"},
            {"source": "middle", "target": "target", "kind": "flows_to"},
        ],
    )
    candidates = {item.strategy: item for item in generate_layout_candidates(scene)}
    flow = candidates["flow"]
    by_id = {item.id: item for item in flow.objects}

    assert flow.hard_valid
    assert flow.relation_paths
    assert all(path.visible for path in flow.relation_paths)
    assert by_id["source"].box.center_x < by_id["middle"].box.center_x < by_id["target"].box.center_x


def test_dense_scene_is_readable_without_overlap_or_caption_collision() -> None:
    solution = solve_layout_v21(_scene([_object(f"object_{index}") for index in range(16)]))
    objects = solution.objects

    assert not validate_layout(solution.scene_ir)
    assert all(item.box.width >= 0.09 and item.box.height >= 0.05 for item in objects)
    assert not any(_overlaps(one.box, two.box) for index, one in enumerate(objects) for two in objects[index + 1 :])
    assert all(solution.space.is_caption_safe(item.box) for item in objects)


def test_edge_constraints_are_hard_constraints() -> None:
    scene = _scene(
        [_object("left"), _object("right"), _object("top"), _object("bottom")],
        [
            {"source": "left", "target": "right", "kind": "left_of"},
            {"source": "top", "target": "bottom", "kind": "above"},
        ],
    )
    solution = solve_layout_v21(scene)
    by_id = {item.id: item for item in solution.objects}

    assert by_id["left"].box.center_x < by_id["right"].box.center_x
    assert by_id["top"].box.center_y < by_id["bottom"].box.center_y
    assert not validate_layout(solution.scene_ir)


def test_ir_stays_normalized_and_pixel_target_is_metadata_only() -> None:
    space = SceneSpace()
    ir = layout_scene_v21(_scene([_object("engine", role="primary")]), space=space)
    payload = ir.to_dict()
    pixel_boxes = ir.pixel_boxes()

    assert payload["coordinate_space"] == "normalized"
    assert all(0 <= value <= 1 for item in ir.objects for value in (item.box.x, item.box.y, item.box.right, item.box.bottom))
    assert all(box.right <= space.pixel_width and box.bottom <= space.pixel_height for box in pixel_boxes.values())
    assert payload["space"]["pixel_target"] == {"width": 1920, "height": 1080}


def test_candidate_scoring_and_selected_layout_are_deterministic() -> None:
    scene = _scene([_object("a", role="primary"), _object("b"), _object("c")])
    first = solve_layout_v21(scene).to_dict()
    second = solve_layout_v21(scene).to_dict()
    candidates = generate_layout_candidates(scene)

    assert first == second
    assert all("hero_prominence" in item.score_breakdown for item in candidates)
    assert [item.strategy for item in candidates] == ["hero", "split", "flow", "triad", "grid"]


@dataclass
class ProgramSubject:
    id: str
    semantic_name: str
    structural_family: str = "rigid_assembly"
    role: str = "secondary"


@dataclass
class ProgramScene:
    scene_id: str
    subjects: tuple[ProgramSubject, ...]
    relationships: tuple[dict[str, str], ...]


def test_program_like_duck_type_does_not_require_visual_program_module() -> None:
    scene = ProgramScene(
        "duck",
        (ProgramSubject("grid", "grid", role="primary"), ProgramSubject("rack", "rack")),
        ({"source": "grid", "target": "rack", "kind": "feeds"},),
    )

    solution = solve_layout_v21(scene)

    assert solution.scene_id == "duck" if hasattr(solution, "scene_id") else solution.scene.scene_id
    assert not validate_layout(solution.scene_ir)


def test_empty_scene_is_explicitly_rejected() -> None:
    with pytest.raises(LayoutV21Error):
        solve_layout_v21(_scene([]))


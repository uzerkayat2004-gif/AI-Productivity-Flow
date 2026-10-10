"""Focused deterministic acceptance tests for the V2.1 state engine."""

from __future__ import annotations

import copy
import math

from voice_flow.video_flow_engine.scene_state import SceneState, evaluate_event, event_qa_metrics, sample_event


def _state() -> SceneState:
    return SceneState(
        objects={
            "source": {"position": [0, 0, 0]}, "destination": {"position": [8, 0, 0]}, "carrier": {"position": [0, 0, 0]},
            "center": {"position": [0, 0, 0]}, "orbiter": {"position": [2, 0, 0], "geometry": {"radius": 1}},
            "bud": {"position": [1, 1, 0], "geometry": {"radius": 0.2}, "semantic_state": "bud"},
            "part_a": {"position": [-2, 0, 0]}, "part_b": {"position": [2, 0, 0]}, "whole": {"position": [0, 0, 0], "visible": False, "opacity": 0},
            "node_a": {"position": [0, 0, 0]}, "node_b": {"position": [1, 0, 0]}, "node_c": {"position": [2, 0, 0]},
        }
    )


def test_transfer_and_path_motion_change_persistent_positions() -> None:
    state = _state()
    event = {"type": "TRANSFER", "carrier": "carrier", "source": "source", "destination": "destination", "cue": 1, "duration": 2}
    assert evaluate_event(state, event, 0.5).object("carrier").position == (0.0, 0.0, 0.0)
    assert evaluate_event(state, event, 2).object("carrier").position == (4.0, 0.0, 0.0)
    assert evaluate_event(state, event, 3).object("carrier").position == (8.0, 0.0, 0.0)
    assert state.object("carrier").position == (0.0, 0.0, 0.0)

    orbit = {"type": "PATH_MOTION", "subject": "orbiter", "path": {"kind": "orbit", "center": "center", "radius": 2, "sweep": math.tau}, "duration": 2}
    positions = [snapshot.object("orbiter").position for snapshot in sample_event(state, orbit, samples=5)]
    assert len({tuple(round(item, 6) for item in position) for position in positions}) >= 4
    assert all(math.isclose(math.hypot(position[0], position[1]), 2, abs_tol=1e-6) for position in positions)


def test_grow_and_transform_change_geometry_and_semantic_state() -> None:
    state = _state()
    grown = evaluate_event(state, {"type": "GROW", "object_id": "bud", "duration": 2}, 2)
    assert grown.object("bud").scale[0] > state.object("bud").scale[0]
    assert grown.object("bud").geometry["radius"] > state.object("bud").geometry["radius"]
    transformed = evaluate_event(state, {"type": "TRANSFORM", "object_id": "bud", "from_state": "bud", "to_state": "flower", "params": {"transform": {"position": [[1, 1, 0], [2, 3, 0]]}}, "duration": 1}, 1)
    assert transformed.object("bud").semantic_state == "flower"
    assert transformed.object("bud").position == (2.0, 3.0, 0.0)


def test_assemble_merge_propagate_and_camera_are_observable() -> None:
    state = _state()
    assembled = evaluate_event(state, {"type": "ASSEMBLE", "parts": ["part_a", "part_b"], "target": "whole", "duration": 1}, 1)
    assert assembled.object("part_a").position == (0.0, 0.0, 0.0)
    assert assembled.object("part_b").position == (0.0, 0.0, 0.0)
    assert assembled.object("whole").visible
    merged = evaluate_event(state, {"type": "MERGE", "sources": ["part_a", "part_b"], "target": "whole", "duration": 1}, 1)
    assert merged.object("part_a").opacity == 0
    assert merged.object("part_b").opacity == 0
    assert merged.object("whole").opacity == 1
    propagated = evaluate_event(state, {"type": "PROPAGATE", "nodes": ["node_a", "node_b", "node_c"], "duration": 1}, 1)
    assert all(propagated.object(node).properties["propagation_progress"] == 1 for node in ("node_a", "node_b", "node_c"))
    camera = evaluate_event(state, {"type": "CAMERA", "params": {"to": {"position": [2, 1, 4], "target": [1, 0, 0], "zoom": 1.5}}, "duration": 1}, 1)
    assert camera.camera.position == (2.0, 1.0, 4.0)
    assert camera.camera.target == (1.0, 0.0, 0.0)
    assert camera.camera.zoom == 1.5


def test_event_qa_metrics_are_deterministic_and_input_is_not_mutated() -> None:
    raw = {"objects": {"carrier": {"position": [0, 0, 0]}, "destination": {"position": [4, 0, 0]}}}
    snapshot = copy.deepcopy(raw)
    event = {"type": "TRANSFER", "carrier": "carrier", "source": [0, 0, 0], "destination": "destination", "duration": 1}
    first = event_qa_metrics(raw, event)
    assert first.to_dict() == event_qa_metrics(raw, event).to_dict()
    assert first.observed
    assert raw == snapshot


def test_eventv21_like_no_coordinate_paths_use_semantic_references() -> None:
    state = SceneState(objects={
        "mars": {"position": [0, 0, 0]}, "spacecraft": {"position": [3, 0, 0]},
        "source": {"position": [-2, 0, 0]}, "destination": {"position": [2, 0, 0]}, "carrier": {"position": [-2, 0, 0]},
    })
    orbit = type("EventV21Like", (), {"type": "PATH_MOTION", "subject": "spacecraft", "center": "mars", "radius": 3.0, "mode": "orbit", "path": (), "duration": 2.0, "at": None})()
    metrics = event_qa_metrics(state, orbit, samples=5)
    assert metrics.observed
    assert metrics.path_radius_error <= 1e-9
    snapshots = sample_event(state, orbit, samples=5)
    positions = [snapshot.object("spacecraft").position for snapshot in snapshots]
    assert len({tuple(round(value, 6) for value in position) for position in positions}) >= 4
    assert all(math.isclose(math.dist(position, (0.0, 0.0, 0.0)), 3.0, abs_tol=1e-9) for position in positions)

    linear = {"type": "PATH_MOTION", "subject": "carrier", "source": "source", "destination": "destination", "duration": 1.0}
    assert evaluate_event(state, linear, 1.0).object("carrier").position == (2.0, 0.0, 0.0)
    assert event_qa_metrics(state, linear).observed

"""Tests for bounded, non-sensitive Visual V2 signatures."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from voice_flow.video_flow_engine.scene_compiler_v2 import compile_visual_plan_v2
from voice_flow.video_flow_engine.visual_plan_v2 import parse_video_visual_plan_v2
from voice_flow.video_flow_engine.visual_signature import (
    VisualSignature,
    VisualSignatureStore,
    signature_from,
)


STORYBOARD = {
    "topic": "Private source title that must not persist",
    "sections": [
        {"id": "residual", "title": "Private section", "lecture_lines": ["Private narration must not persist."]},
    ],
}


def _plan_payload() -> dict:
    return {
        "version": "2.0",
        "design_bible": {
            "visual_character": "technical paper diagram",
            "surface_mode": "paper",
            "palette_intent": {
                "dominant": "paper",
                "contrast": "very-high",
                "accent_family": "signal-red",
                "secondary_family": "black",
                "temperature": "neutral",
                "saturation": "selective",
            },
            "typography_character": "technical",
            "shape_language": "diagrammatic",
            "background_character": "paper",
            "motion_character": "technical",
            "transition_character": "fade",
            "camera_character": "focus",
            "caption_integration": "reserved-bottom",
        },
        "scenes": [
            {
                "scene_id": "residual-block",
                "storyboard_section_id": "residual",
                "learning_goal": "Explain a shortcut.",
                "visual_thesis": "An input transforms then merges with a bypass.",
                "visual_mode": "mechanism",
                "objects": [
                    {"id": "input", "type": "node", "label": "Input", "role": "primary", "region": "left"},
                    {"id": "shortcut", "type": "curve", "label": "Shortcut", "role": "support", "region": "top"},
                    {"id": "sum", "type": "operator", "label": "+", "role": "primary", "region": "right"},
                ],
                "relationships": [
                    {"source": "input", "target": "shortcut", "kind": "bypasses"},
                    {"source": "shortcut", "target": "sum", "kind": "merges_into"},
                ],
                "beats": [
                    {"order": 1, "phase": "intro", "action": "create", "object_id": "input", "reason": "Show the input."},
                    {"order": 2, "phase": "build", "action": "draw", "object_id": "shortcut", "reason": "Draw the bypass."},
                    {"order": 3, "phase": "resolve", "action": "merge", "object_id": "sum", "reason": "Merge signals."},
                ],
                "continuity": {"carry_forward": []},
            }
        ],
    }


def _signature() -> VisualSignature:
    return VisualSignature(
        surface_mode="paper",
        palette_family="signal-red",
        background_family="paper",
        typography_family="technical",
        motion_profile="technical",
        camera_profile="focus",
        depth_profile="layered",
        scene_density=3,
        usage_3d=False,
    )


def test_signature_contains_only_fixed_non_sensitive_fields_and_extracts_deterministically() -> None:
    plan = parse_video_visual_plan_v2(_plan_payload(), storyboard=STORYBOARD)
    compiled = compile_visual_plan_v2(STORYBOARD, plan)

    first = signature_from(plan, compiled)
    second = signature_from(plan, compiled)

    assert first == second
    assert first.to_dict() == _signature().to_dict()
    assert set(first.to_dict()) == {
        "surface_mode",
        "palette_family",
        "background_family",
        "typography_family",
        "motion_profile",
        "camera_profile",
        "depth_profile",
        "scene_density",
        "usage_3d",
    }
    serialized = json.dumps(first.to_dict())
    for forbidden in ("Private", "narration", "title", "source", "job", "metadata"):
        assert forbidden.casefold() not in serialized.casefold()


def test_store_appends_in_order_and_trims_to_newest_entries(tmp_path: Path) -> None:
    store = VisualSignatureStore(tmp_path / "visual-signatures.json", max_entries=2)
    first = _signature()
    second = VisualSignature(**{**first.to_dict(), "palette_family": "orange"})
    third = VisualSignature(**{**first.to_dict(), "palette_family": "green"})

    store.append(first)
    store.append(second)
    store.append(third)

    assert store.recent() == (second, third)
    payload = json.loads((tmp_path / "visual-signatures.json").read_text(encoding="utf-8"))
    assert payload == {"version": 1, "signatures": [second.to_dict(), third.to_dict()]}


def test_missing_or_corrupt_store_recovers_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "visual-signatures.json"
    store = VisualSignatureStore(path)
    assert store.recent() == ()

    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")
    assert store.recent() == ()

    store.append(_signature())
    assert store.recent() == (_signature(),)


def test_invalid_store_entries_are_ignored_without_admitting_arbitrary_metadata(tmp_path: Path) -> None:
    path = tmp_path / "visual-signatures.json"
    valid = _signature().to_dict()
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "signatures": [
                    valid,
                    {**valid, "title": "private source"},
                    {**valid, "usage_3d": "false"},
                    {"surface_mode": "paper"},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert VisualSignatureStore(path).recent() == (_signature(),)


def test_invalid_constructor_values_and_store_bounds_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        VisualSignature(**{**_signature().to_dict(), "scene_density": 0})
    with pytest.raises(ValueError):
        VisualSignature(**{**_signature().to_dict(), "usage_3d": 1})
    with pytest.raises(ValueError):
        VisualSignatureStore(tmp_path / "x.json", max_entries=0)
    with pytest.raises(ValueError):
        VisualSignatureStore(tmp_path / "x.json", max_entries=51)


def test_concurrent_appends_share_per_path_lock_and_do_not_lose_writes(tmp_path: Path) -> None:
    path = tmp_path / "visual-signatures.json"
    store_a = VisualSignatureStore(path, max_entries=50)
    store_b = VisualSignatureStore(path, max_entries=50)
    barrier = threading.Barrier(2)

    def append_many(store: VisualSignatureStore, prefix: str) -> None:
        barrier.wait()
        for index in range(10):
            store.append(VisualSignature(**{**_signature().to_dict(), "palette_family": "orange" if prefix == "a" else "green", "scene_density": index + 1}))

    first = threading.Thread(target=append_many, args=(store_a, "a"))
    second = threading.Thread(target=append_many, args=(store_b, "b"))
    first.start()
    second.start()
    first.join(timeout=5)
    second.join(timeout=5)

    entries = VisualSignatureStore(path, max_entries=50).recent()
    assert not first.is_alive() and not second.is_alive()
    assert len(entries) == 20
    assert {entry.palette_family for entry in entries} == {"orange", "green"}


def test_failed_atomic_replace_removes_fixed_temporary_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "nested" / "visual-signatures.json"
    store = VisualSignatureStore(path)
    temporary = path.with_name("visual-signatures.json.tmp")

    monkeypatch.setattr("voice_flow.video_flow_engine.visual_signature.os.replace", lambda *_: (_ for _ in ()).throw(OSError("replace failed")))

    with pytest.raises(OSError, match="replace failed"):
        store.append(_signature())

    assert not temporary.exists()

from __future__ import annotations

from voice_flow.video_flow_engine.diversity import CreativeFingerprint, DiversityLedger, structural_scene_fingerprint
from voice_flow.video_flow_engine.engine import AgenticVisualEngine


def _node(node_id: str, node_type: str, *, children: list[dict] | None = None, **payload: object) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "layout": {"mode": "absolute", "x": 0, "y": 0, "width": 400, "height": 240},
        "children": children or [],
        **payload,
    }


def _artifacts(*, treatment: dict, root: dict, render_class: str = "motion-island") -> dict:
    return {
        "treatment": treatment,
        "scenes": [
            {
                "id": "scene-1",
                "renderClass": render_class,
                "root": root,
                "motion_events": [{"action": "trace", "purpose": "show direction"}],
            }
        ],
    }


def test_nested_scene_programs_are_visible_to_the_anti_repeat_gate() -> None:
    network_root = _node(
        "root",
        "group",
        children=[
            _node("headline", "text", text={"text": "Signal path"}),
            _node(
                "network",
                "network",
                network={
                    "nodes": [{"id": "a", "x": 40, "y": 80}, {"id": "b", "x": 320, "y": 80}],
                    "edges": [{"from": "a", "to": "b", "directed": True}],
                },
            ),
        ],
    )
    mechanism_root = _node(
        "root",
        "group",
        children=[
            _node(
                "assembly",
                "group",
                children=[
                    _node("gear-a", "circle"),
                    _node("gear-b", "circle"),
                    _node("shaft", "rect"),
                    _node("orbit", "three", three={"primitive": "torus", "rotation": [0, "frame/40", 0]}),
                ],
            )
        ],
    )

    nested = structural_scene_fingerprint({"root": network_root})
    assert nested["element_count"] == 3
    assert nested["edge_count"] >= 3

    first = CreativeFingerprint.from_artifacts(
        _artifacts(
            treatment={
                "palette_roles": {"background": "#fff7ed", "accent": ["#f97316", "#0f172a"]},
                "material_language": "ink topology and ruled connectors",
                "motion_personality": "trace and branch",
                "camera_grammar": "fixed analytical field",
                "illustration_strategy": "network schematic",
            },
            root=network_root,
        )
    )
    second = CreativeFingerprint.from_artifacts(
        _artifacts(
            treatment={
                "palette_roles": {"background": "#07111f", "accent": ["#22d3ee", "#eab308"]},
                "material_language": "machined metal and volumetric depth",
                "motion_personality": "assemble rotate and lock",
                "camera_grammar": "orbiting cutaway",
                "illustration_strategy": "spatial mechanism",
            },
            root=mechanism_root,
            render_class="webgl-3d",
        )
    )

    assert DiversityLedger(history=[first]).review(first)["accepted"] is False
    assert DiversityLedger(history=[first]).review(second)["accepted"] is True


def test_explicit_3d_scene_program_passes_the_engine_contract() -> None:
    manifest = AgenticVisualEngine._validate_manifest(
        {
            "engineVersion": "agentic-visual.v1",
            "scenes": [
                {
                    "id": "rocket-stage",
                    "narration": "The stage rotates to expose the tank, feed line, and engine relationship.",
                    "durationSeconds": 6,
                    "durationInFrames": 144,
                    "renderClass": "webgl-3d",
                    "root": _node(
                        "rocket",
                        "three",
                        three={"primitive": "cylinder", "dimensions": [1.2, 1.2, 3.8], "rotation": [0, "frame/60", 0]},
                    ),
                }
            ],
        }
    )
    scene = manifest["scenes"][0]
    assert scene["renderClass"] == "webgl-3d"
    assert scene["root"]["type"] == "three"

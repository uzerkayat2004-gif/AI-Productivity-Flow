from __future__ import annotations

from voice_flow.video_flow_engine.bridge import build_narova_production


def test_bridge_turns_teaching_steps_into_portable_narova_flow() -> None:
    production = build_narova_production(
        {
            "topic": "Autonomous driving",
            "sections": [
                {
                    "id": "pipeline",
                    "title": "Traditional modular pipeline",
                    "lecture_lines": ["Perception detects objects.", "Planning chooses a path.", "Control turns the wheel."],
                    "animations": ["Connect perception, planning, and control with arrows."],
                }
            ],
        }
    )

    visual = production["scenes"][0]["visual"]
    serialized = str(visual)
    assert "Perception detects objects." in serialized
    assert "Planning chooses a path." in serialized
    assert "Control turns the wheel." in serialized
    assert "Connect perception, planning, and control with arrows." not in serialized
    assert "PROCESS FLOW" in serialized
    assert serialized.count(">") >= 2






def test_bridge_rejects_unsafe_voice_id() -> None:
    import pytest as _pytest

    storyboard = {
        "topic": "T",
        "sections": [{"id": "s", "title": "S", "lecture_lines": ["Line."], "animations": []}],
    }
    with _pytest.raises(ValueError, match="voice"):
        build_narova_production(storyboard, voice="edge/en-US-AvaNeural; rm -rf /")


def test_bridge_validates_reassembled_scene_html() -> None:
    import pytest as _pytest
    from voice_flow.video_flow_engine import bridge as bridge_module

    storyboard = {
        "topic": "T",
        "sections": [{"id": "s", "title": "S", "lecture_lines": ["Hello world."], "animations": []}],
    }
    original = bridge_module.scene_author.author_scene
    try:
        bridge_module.scene_author.author_scene = lambda *a, **k: {"body": "<scr" + "ipt>alert(1)</scr" + "ipt>"}
        with _pytest.raises(ValueError, match="Security Boundary"):
            bridge_module.build_directed_production(
                storyboard,
                {"brief": {}, "scenes": [{"index": 1, "treatment": "labeled-diagram", "title_label": "S", "labels": [], "transition": "fade"}]},
            )
    finally:
        bridge_module.scene_author.author_scene = original

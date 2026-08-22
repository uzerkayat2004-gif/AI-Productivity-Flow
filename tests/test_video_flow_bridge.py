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





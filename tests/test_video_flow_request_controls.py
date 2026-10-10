from __future__ import annotations

from voice_flow.video_flow_engine.bridge import build_narova_production


def test_theme_mode_and_visual_direction_affect_production() -> None:
    storyboard = {
        "topic": "Two systems",
        "sections": [
            {
                "id": "neutral",
                "title": "Two systems",
                "lecture_lines": ["System A.", "System B."],
                "animations": ["Reveal both systems."],
            }
        ],
    }

    production = build_narova_production(
        storyboard,
        mode="full",
        theme={"mode": "light", "accent": "#123456"},
        visual_direction="side-by-side comparison",
    )

    assert production["theme"]["mode"] == "light"
    assert production["theme"]["accent"] == "#123456"
    assert production["timing"]["tempo"] == 1.05
    assert "COMPARISON" in str(production["scenes"][0]["visual"])

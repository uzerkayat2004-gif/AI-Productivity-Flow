from __future__ import annotations

from voice_flow.video_flow_engine.bridge import build_narova_production


def test_comparison_intent_selects_comparison_layout() -> None:
    production = build_narova_production(
        {
            "topic": "Driving systems",
            "sections": [
                {
                    "id": "compare",
                    "title": "Two approaches",
                    "lecture_lines": ["Traditional systems use explicit modules.", "End-to-end systems learn one mapping."],
                    "animations": ["Finish with a side-by-side comparison."],
                }
            ],
        }
    )

    visual = str(production["scenes"][0]["visual"])
    assert "COMPARISON" in visual
    assert "VS" in visual
    assert "side-by-side comparison" not in visual


def test_transformation_intent_selects_transformation_layout() -> None:
    production = build_narova_production(
        {
            "topic": "Training",
            "sections": [
                {
                    "id": "learn",
                    "title": "The network learns",
                    "lecture_lines": ["Start with demonstrations.", "The model adjusts its behavior."],
                    "animations": ["Transform examples into a learned model."],
                }
            ],
        }
    )

    visual = str(production["scenes"][0]["visual"])
    assert "TRANSFORMATION" in visual
    assert "=>" in visual

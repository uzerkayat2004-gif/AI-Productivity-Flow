from __future__ import annotations

from voice_flow.video_flow_engine.bridge import build_narova_production
from voice_flow.video_flow_engine.narova_runner import NarovaRunner


def test_long_render_timeout_remains_bounded_but_supports_one_minute_video() -> None:
    # 900s bound: HyperFrames browser builds of ~60s videos exceed the old
    # 300s bound; the limit stays finite so runaway renders still fail.
    assert NarovaRunner().timeout_seconds == 900.0


def test_bridge_avoids_costly_wipe_transitions() -> None:
    production = build_narova_production(
        {
            "topic": "Long explanation",
            "sections": [
                {"id": "one", "title": "One", "lecture_lines": ["First."], "animations": ["Reveal."]},
                {"id": "two", "title": "Two", "lecture_lines": ["Second."], "animations": ["Reveal."]},
            ],
        }
    )

    assert [scene["transition"] for scene in production["scenes"]] == ["slide", "fade"]

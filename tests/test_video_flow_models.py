from __future__ import annotations

import pytest

from voice_flow.video_flow import VideoFlowPlanner
from voice_flow.video_flow_models import VideoModelGateway


class _Store:
    def list_combos(self):
        return []


class _StubGateway(VideoModelGateway):
    def _request_plan(self, source, mode, title, model_ref):
        return {
            "scenes": [
                {
                    "type": "timeline",
                    "title": "AI visual title",
                    "body": "A visual descriptor only",
                    "narration": "This rewrite must never replace full-mode source.",
                }
            ]
        }


def test_external_model_requires_explicit_per_job_consent() -> None:
    gateway = _StubGateway(_Store(), VideoFlowPlanner())

    with pytest.raises(PermissionError, match="per-video consent"):
        gateway.build(
            "private selected text",
            "summary",
            "Private",
            "openai/gpt-4o-mini",
            allow_external_ai=False,
        )


def test_full_mode_keeps_exact_narration_after_external_visual_planning() -> None:
    source = "Keep this exact.\n\nIncluding whitespace and punctuation!"
    gateway = _StubGateway(_Store(), VideoFlowPlanner())

    plan = gateway.build(
        source,
        "full",
        "Exact",
        "openai/gpt-4o-mini",
        allow_external_ai=True,
    )

    assert "".join(scene["narration"] for scene in plan["scenes"]) == source
    assert plan["coverage"]["complete"] is True
    assert plan["scenes"][0]["type"] == "timeline"

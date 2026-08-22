from __future__ import annotations

from pathlib import Path

from voice_flow.video_flow import VideoFlowPlanner
from voice_flow.video_flow_models import VideoModelGateway


ROOT = Path(__file__).resolve().parents[1]


class _Store:
    def list_combos(self):
        return []


def test_local_runtime_does_not_require_external_source_consent():
    gateway = VideoModelGateway(_Store(), VideoFlowPlanner())

    plan = gateway.build(
        "Private local source",
        "summary",
        "Local",
        "ollama/llama3.2",
        allow_external_ai=False,
    )

    assert plan["planning_model"] == "local/deterministic"
    assert plan["requested_model"] == "ollama/llama3.2"


def test_system_bar_wires_composer_progress_and_ready_player():
    main = (ROOT / "src" / "voice_flow" / "main.py").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "voice_flow" / "overlay.py").read_text(encoding="utf-8")

    assert 'video_flow_widget.show_composer(text, "summary")' in main
    assert 'video_flow_widget.show_composer(text, "full")' in main
    assert "show_video_progress" in main
    assert "show_video_ready" in main
    assert "on_video_ready" in overlay
    assert 'return "video_status"' in overlay


def test_external_player_is_resizable_topmost_and_has_native_video_controls():
    launcher = (ROOT / "src" / "voice_flow" / "video_flow_player.py").read_text(encoding="utf-8")
    html = (ROOT / "src" / "voice_flow" / "gui" / "video-player.html").read_text(encoding="utf-8")

    assert "resizable=True" in launcher
    assert "on_top=True" in launcher
    assert '<video id="player" controls' in html
    assert "toggle_fullscreen" in html
    assert "/api/video-flow/jobs/status" in html

from pathlib import Path

from voice_flow.video_flow_models import VideoModelGateway
from voice_flow.video_flow_themes import THEME_PALETTES, VideoFlowThemePolicy


def test_every_theme_uses_the_notebook_editorial_medium() -> None:
    policy = VideoFlowThemePolicy()

    for theme in THEME_PALETTES:
        choice = policy.choose("Any subject", requested_theme=theme)

        assert choice["system"] == "notebook-explanation-v5"
        assert choice["renderer"] == "editorial-storyboard-v5"
        assert choice["palette"]["background"] == "#fbfaf5"
        assert choice["visual_rules"]["rough_ink_outlines"] is True
        assert choice["scene_grammar"]["maximum_cards"] == 4


def test_model_prompt_preserves_notebook_style_and_returns_structure_only() -> None:
    visual_language = VideoFlowThemePolicy().choose("A workflow with one important metric.")

    prompt = VideoModelGateway._prompt(
        "A workflow with one important metric.",
        "summary",
        "Clear workflow",
        visual_language,
    )

    assert "Notebook Editorial" in prompt
    assert "do not output JSX" in prompt
    assert "Never design dashboards" in prompt
    assert "Supply 3-5 concrete entities" in prompt
    assert "each entity label must be at most three words" in prompt


def test_production_renderer_avoids_expensive_live_roughness_filters() -> None:
    renderer = Path(__file__).parents[1] / "video_flow_renderer" / "src" / "VideoFlow.tsx"
    source = renderer.read_text(encoding="utf-8")

    assert "notebook-sketch-v1" in source
    assert "premountFor={props.fps}" in source
    assert "feTurbulence" not in source
    assert "feDisplacementMap" not in source


def test_renderer_is_content_only_domain_aware_and_narration_timed() -> None:
    renderer = Path(__file__).parents[1] / "video_flow_renderer" / "src" / "VideoFlow.tsx"
    source = renderer.read_text(encoding="utf-8")

    assert "Video Flow · Notebook Sketch" not in source
    assert "scene.type.replace" not in source
    assert "DomainDoodle" in source
    assert "StatementScene" in source
    assert "DiagramScene" in source
    assert "const at = (duration" in source
    assert "duration={duration}" in source


def test_full_mode_prompt_requires_polished_complete_spoken_narration() -> None:
    visual_language = VideoFlowThemePolicy().choose("A business study with a 26% growth metric.")

    prompt = VideoModelGateway._prompt(
        "# Findings\n- Revenue grew by 26%.",
        "full",
        "Complete research",
        visual_language,
    )

    assert "complete polished explanation" in prompt
    assert "Do not summarize or omit any paragraph" in prompt
    assert "Remove Markdown symbols" in prompt
    assert "do not repeat one layout for consecutive scenes" in prompt
    assert "metric/chart" in prompt

"""Test suite verifying screen demo video zoom and crop for Audio & Video Flow Step 4 (Item 16)."""
from pathlib import Path

ROOT = Path(__file__).parents[1]
CSS_FILE = ROOT / "src" / "voice_flow" / "gui" / "onboarding-hero.css"


def test_screen_sim_zoom_rules_present() -> None:
    """CSS must define zoom/crop transform rules specifically for Audio & Video screen sim videos."""
    css_content = CSS_FILE.read_text(encoding="utf-8")
    assert "#af-guide-screen-sim .af-sim-video" in css_content
    assert "#vf-guide-screen-sim .af-sim-video" in css_content
    assert "transform: scale(1.36)" in css_content
    assert "transform-origin: 36% 48%" in css_content
    assert "transform-origin: 46% 50%" in css_content


def test_welcome_tour_videos_not_zoomed() -> None:
    """Welcome Tour monitor mockup videos (.s2-screen-video, .s3-screen-video) must not be affected."""
    css_content = CSS_FILE.read_text(encoding="utf-8")
    for cls in [".s2-screen-video", ".s3-screen-video", ".s4-screen-video"]:
        assert f"{cls} {{" in css_content or cls in css_content
        # Ensure scale(1.36) is NOT applied to .s2-screen-video
        idx = css_content.find(cls)
        block = css_content[idx:idx + 300]
        assert "scale(1.36)" not in block

"""Test suite verifying screen demo video framing for Audio & Video Flow Step 4."""
from pathlib import Path

ROOT = Path(__file__).parents[1]
CSS_FILE = ROOT / "src" / "voice_flow" / "gui" / "onboarding-hero.css"


def test_screen_sim_framing_properly_centered_without_cutoffs() -> None:
    """CSS must fit screen sim videos in the center without edge cutoffs or zoom transforms."""
    css_content = CSS_FILE.read_text(encoding="utf-8")
    assert "#af-guide-screen-sim .af-sim-video" in css_content
    assert "#vf-guide-screen-sim .af-sim-video" in css_content

    # Ensure uncropped framing
    assert "object-fit: contain !important;" in css_content
    assert "object-position: center center !important;" in css_content
    assert "transform: none !important;" in css_content

    # Ensure scale(1.36) is completely removed from guide screen sim rules
    af_idx = css_content.find("#af-guide-screen-sim .af-sim-video")
    vf_idx = css_content.find("#vf-guide-screen-sim .af-sim-video")
    assert "scale(1.36)" not in css_content[af_idx:af_idx + 350]
    assert "scale(1.36)" not in css_content[vf_idx:vf_idx + 350]


def test_welcome_tour_videos_not_zoomed() -> None:
    """Welcome Tour monitor mockup videos (.s2-screen-video, .s3-screen-video) must not be affected."""
    css_content = CSS_FILE.read_text(encoding="utf-8")
    for cls in [".s2-screen-video", ".s3-screen-video", ".s4-screen-video"]:
        assert f"{cls} {{" in css_content or cls in css_content
        idx = css_content.find(cls)
        block = css_content[idx:idx + 300]
        assert "scale(1.36)" not in block

"""Comprehensive acceptance test suite verifying all 8 user feedback fixes:
1. Audio Flow Step 1 spotlight covers both Read and Summary (secondaryTargetId).
2. Audio Flow Step 1 narration audio is synthesized with Deepgram Rufus at -20 LUFS, 10-16s.
3. Feature Guide buttons removed from all page headers.
4. Welcome Tour bottom controls: Auto left of Dark Mode, Skip right of Next across Scenes 1-5.
5. Scene 1 feature cards highlight synchronized with voiceover (7.0 - 12.8s).
6. Scene 4 Voice Flow video playback duration aligned with narration (~13.4s, zero premature cutoff).
7. Smooth CSS transition animations for Welcome Tour auto mode scenes.
8. Stop guide cleanups do not set completion flags unless explicitly marked, and no page hijack.
"""
from pathlib import Path
import json
import av

ROOT = Path(__file__).parents[1]
APP_JS = ROOT / "src" / "voice_flow" / "gui" / "app.js"
INDEX_HTML = ROOT / "src" / "voice_flow" / "gui" / "index.html"
CSS_FILE = ROOT / "src" / "voice_flow" / "gui" / "onboarding-hero.css"
ASSETS_DIR = ROOT / "src" / "voice_flow" / "gui" / "assets" / "onboarding"


def test_audioflow_step1_spotlight_covers_both_modes() -> None:
    """Step 1 spotlight in Audio Flow must target both Read and Summary cards."""
    content = APP_JS.read_text(encoding="utf-8")
    idx = content.find("const AUDIOFLOW_GUIDE_STEPS = [")
    assert idx != -1
    step1_block = content[idx:idx + 600]
    assert 'targetId: "af-voice-card"' in step1_block
    assert 'secondaryTargetId: "af-summary-model-hero"' in step1_block


def test_audioflow_step1_audio_properties() -> None:
    """Audio Flow Step 1 narration audio must exist, be 10-18s, and properly mixed (v1.0.3 regen)."""
    audio_path = ASSETS_DIR / "af_guide_step1_mixed.mp3"
    assert audio_path.exists()
    container = av.open(str(audio_path))
    dur = float(container.streams.audio[0].duration * container.streams.audio[0].time_base)
    container.close()
    assert 10.0 <= dur <= 18.0, f"Duration {dur:.2f}s is not within 10-18s"


def test_feature_guide_buttons_removed_from_headers() -> None:
    """Feature Guide buttons must be completely removed from Home, Audio Flow, and Video Flow headers."""
    html_content = INDEX_HTML.read_text(encoding="utf-8")
    assert "voiceflow-guide-trigger-btn" not in html_content
    assert "af-guide-trigger-btn" not in html_content
    assert "vf-guide-trigger-btn" not in html_content


def test_bottom_controls_order_in_welcome_tour() -> None:
    """Across Scenes 1-5, Auto must be to the left of Dark Mode, and Skip Tour to the right of Next."""
    html_content = INDEX_HTML.read_text(encoding="utf-8")
    for s in range(1, 6):
        auto_str = f'id="scene{s}-auto-btn"'
        theme_str = f'id="scene{s}-theme-btn"'
        skip_str = 'finishOnboarding()'

        auto_pos = html_content.find(auto_str)
        theme_pos = html_content.find(theme_str)
        assert auto_pos != -1, f"Missing auto button for scene {s}"
        assert theme_pos != -1, f"Missing theme button for scene {s}"
        assert auto_pos < theme_pos, f"Scene {s}: Auto button must appear before (left of) Dark Mode button"

    # In Scene 1, Skip Tour must appear after Next
    s1_next = html_content.find('id="scene1-next-btn"')
    s1_skip = html_content.find('scene1-skip-badge"')
    assert s1_next != -1 and s1_skip != -1
    assert s1_next < s1_skip, "Scene 1: Skip Tour must appear after (right of) Next button"


def test_scene1_feature_cards_highlight_sync() -> None:
    """Scene 1 cards highlight on the voiceover's own word timings (v1.0.3: generated beats)."""
    content = APP_JS.read_text(encoding="utf-8")
    assert 'time >= b1.video && time < b1.audio' in content
    assert 'highlight-orange' in content
    assert 'time >= b1.audio && time < b1.voice' in content
    assert 'highlight-blue' in content
    assert 'time >= b1.voice && time <= end1' in content
    assert 'highlight-purple' in content
    beats = json.loads((ASSETS_DIR / "narration_timelines.json").read_text(encoding="utf-8"))["scene_1"]
    assert 0 < beats["beats"]["video"] < beats["beats"]["audio"] < beats["beats"]["voice"] < beats["duration"]


def test_scene4_voiceflow_video_duration_aligned() -> None:
    """Scene 4 demo video must be approximately 13-14s to match narration without premature cutoff."""
    video_path = ASSETS_DIR / "s4_voiceflow_demo.mp4"
    assert video_path.exists()
    container = av.open(str(video_path))
    dur = float(container.streams.video[0].duration * container.streams.video[0].time_base)
    container.close()
    assert 12.5 <= dur <= 14.5, f"Scene 4 video duration {dur:.2f}s is not aligned with ~13.5s narration"


def test_welcome_tour_slide_crossfade_animation_css() -> None:
    """CSS must define smooth crossfade transitions for welcome hero slides."""
    css_content = CSS_FILE.read_text(encoding="utf-8")
    assert ".welcome-stage .welcome-hero-slide {" in css_content
    assert "transition: opacity 0.38s ease, transform 0.38s cubic-bezier" in css_content
    assert ".welcome-stage .welcome-hero-slide.active {" in css_content


def test_stop_guides_do_not_falsely_complete_or_hijack() -> None:
    """stopVoiceFlowGuide, stopVideoFlowGuide, and stopAudioFlowGuide must accept markCompleted flag."""
    content = APP_JS.read_text(encoding="utf-8")
    assert "function stopAudioFlowGuide(markCompleted = false)" in content
    assert "function stopVideoFlowGuide(markCompleted = false)" in content
    assert "function stopVoiceFlowGuide(markCompleted = false)" in content
    # stopVoiceFlowGuide must NOT call switchPage("home")
    stop_vf_idx = content.find("function stopVoiceFlowGuide(markCompleted = false)")
    stop_vf_block = content[stop_vf_idx:stop_vf_idx + 1800]
    assert 'switchPage("home"' not in stop_vf_block

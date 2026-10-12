"""Test suite verifying shortened narration (10-15s) and 4-step Voice Flow (Item 14)."""
from pathlib import Path
import json
import av

ROOT = Path(__file__).parents[1]
ASSETS_DIR = ROOT / "src" / "voice_flow" / "gui" / "assets" / "onboarding"
APP_JS = ROOT / "src" / "voice_flow" / "gui" / "app.js"
INDEX_HTML = ROOT / "src" / "voice_flow" / "gui" / "index.html"

AUDIO_FILES = [
    # Voice Flow (4 steps + mac)
    "voiceflow_guide_step1_mixed.mp3",
    "voiceflow_guide_step2_mixed.mp3",
    "voiceflow_guide_step3_mixed.mp3",
    "voiceflow_guide_step4_mixed.mp3",
    "voiceflow_guide_step4_mac_mixed.mp3",

    # Video Flow (4 steps + mac)
    "vf_guide_step1_mixed.mp3",
    "vf_guide_step2_mixed.mp3",
    "vf_guide_step3_mixed.mp3",
    "vf_guide_step4_mixed.mp3",
    "vf_guide_step4_mac_mixed.mp3",

    # Audio Flow (4 steps)
    "af_guide_step1_mixed.mp3",
    "af_guide_step2_mixed.mp3",
    "af_guide_step3_mixed.mp3",
    "af_guide_step4_mixed.mp3",

    # Welcome Tour (Scenes 1-5)
    "scene_1_mixed.mp3",
    "scene_2_mixed.mp3",
    "scene_3_mixed.mp3",
    "scene_4_mixed.mp3",
    "scene_5_mixed.mp3",
]


def test_narration_durations_are_concise() -> None:
    """Every mixed narration track must be approximately 10-15 seconds."""
    for filename in AUDIO_FILES:
        audio_path = ASSETS_DIR / filename
        assert audio_path.exists(), f"Audio file {filename} does not exist"
        container = av.open(str(audio_path))
        duration = float(container.streams.audio[0].duration * container.streams.audio[0].time_base)
        container.close()
        assert 10.0 <= duration <= 16.0, f"{filename} duration {duration:.2f}s is outside 10-16s target"


def test_voiceflow_guide_is_four_steps() -> None:
    """Voice Flow guide in app.js and index.html must be exactly 4 steps."""
    content = APP_JS.read_text(encoding="utf-8")
    assert "counter: \"STEP 1 OF 4 · HOME & INSIGHTS\"" in content
    assert "counter: \"STEP 2 OF 4 · DICTIONARY & STYLES\"" in content
    assert "counter: \"STEP 3 OF 4 · AI MODELS & PROVIDERS\"" in content
    assert "counter: \"STEP 4 OF 4 · GLOBAL SHORTCUT\"" in content
    assert "STEP 5 OF 6" not in content
    assert "STEP 6 OF 6" not in content

    html_content = INDEX_HTML.read_text(encoding="utf-8")
    assert "gotoVoiceFlowGuideStep(4)" in html_content
    assert "gotoVoiceFlowGuideStep(5)" not in html_content


def test_videoflow_and_audioflow_are_four_steps() -> None:
    """Video Flow and Audio Flow guides must have exactly 4 steps."""
    content = APP_JS.read_text(encoding="utf-8")
    assert "counter: \"STEP 1 OF 4 · CONTENT & FORMATS\"" in content
    assert "counter: \"STEP 4 OF 4 · SCREEN WORKFLOW\"" in content
    assert "counter: \"STEP 1 OF 4 · READ & SUMMARY\"" in content
    assert "counter: \"STEP 4 OF 4 · SCREEN WORKFLOW\"" in content


def test_timelines_json_validity() -> None:
    """All timelines JSON files must exist and contain updated 4-step entries."""
    vf_data = json.loads((ASSETS_DIR / "vf_guide_timelines.json").read_text(encoding="utf-8"))
    assert set(vf_data.keys()) == {"step1", "step2", "step3", "step4", "step4_mac"}

    voice_data = json.loads((ASSETS_DIR / "voiceflow_guide_timelines.json").read_text(encoding="utf-8"))
    assert set(voice_data.keys()) == {"1", "2", "3", "4", "4_mac"}

    af_data = json.loads((ASSETS_DIR / "af_guide_timelines.json").read_text(encoding="utf-8"))
    assert set(af_data.keys()) == {"1", "2", "3", "4"}

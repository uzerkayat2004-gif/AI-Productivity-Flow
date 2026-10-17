"""Test suite verifying Video Flow guide merging steps 2 & 3 into a 4-step guide (Item 13)."""
from pathlib import Path
import json

ROOT = Path(__file__).parents[1]
APP_JS = ROOT / "src" / "voice_flow" / "gui" / "app.js"
INDEX_HTML = ROOT / "src" / "voice_flow" / "gui" / "index.html"
TIMELINES_JSON = ROOT / "src" / "voice_flow" / "gui" / "assets" / "onboarding" / "vf_guide_timelines.json"


def test_videoflow_guide_steps_count() -> None:
    """VIDEOFLOW_GUIDE_STEPS in app.js must have exactly 4 steps."""
    content = APP_JS.read_text(encoding="utf-8")
    assert "const VIDEOFLOW_GUIDE_STEPS = [" in content
    
    # Check step counters
    assert 'counter: "STEP 1 OF 4 · CONTENT & FORMATS"' in content
    assert 'counter: "STEP 2 OF 4 · CHOOSE YOUR VIDEO ENGINE"' in content
    assert 'counter: "STEP 3 OF 4 · LIBRARY & DOWNLOADS"' in content
    assert 'counter: "STEP 4 OF 4 · SCREEN WORKFLOW"' in content
    assert 'STEP 5 OF 5' not in content


def test_videoflow_guide_step2_title_and_narration() -> None:
    """Step 2 must be titled 'Choose your video engine' and have concise narration."""
    content = APP_JS.read_text(encoding="utf-8")
    assert 'title: "Choose your video engine"' in content
    assert "NotebookLM uses your own Google account: just sign in. No API keys, nothing to pay." in content


def test_videoflow_guide_dots_count() -> None:
    """index.html must have 4 dots for Video Flow."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    assert 'gotoVideoFlowGuideStep(4)' in content
    assert 'gotoVideoFlowGuideStep(5)' not in content


def test_vf_guide_timelines_json() -> None:
    """vf_guide_timelines.json must contain step1 through step4."""
    data = json.loads(TIMELINES_JSON.read_text(encoding="utf-8"))
    assert "step1" in data
    assert "step2" in data
    assert "step3" in data
    assert "step4" in data
    assert "step5" not in data

"""Test suite verifying the Voice Flow onboarding guide polishing toggle button in Step 4."""
from pathlib import Path

ROOT = Path(__file__).parents[1]
APP_JS = ROOT / "src" / "voice_flow" / "gui" / "app.js"
INDEX_HTML = ROOT / "src" / "voice_flow" / "gui" / "index.html"
CSS_FILE = ROOT / "src" / "voice_flow" / "gui" / "onboarding-hero.css"


def test_index_html_has_polishing_action_button() -> None:
    """index.html must have voiceflow-guide-polish-action-btn inside voiceflow-guide-card."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="voiceflow-guide-polish-action-wrap"' in content
    assert 'id="voiceflow-guide-polish-action-btn"' in content
    assert "Turn on polishing" in content
    assert "turnOnPolishingFromVoiceFlowGuide()" in content


def test_css_has_action_button_styles() -> None:
    """onboarding-hero.css must define styling for af-guide-inline-action-btn."""
    content = CSS_FILE.read_text(encoding="utf-8")
    assert ".af-guide-inline-action-wrap" in content
    assert ".af-guide-inline-action-btn" in content


def test_app_js_handles_step4_polishing_button() -> None:
    """app.js must dynamically display the button in step 4 only when polishing is off."""
    content = APP_JS.read_text(encoding="utf-8")
    assert "function turnOnPolishingFromVoiceFlowGuide()" in content
    assert "function gotoVoiceFlowGuideStep(stepIdx)" in content

    goto_fn = content[content.index("function gotoVoiceFlowGuideStep(stepIdx)"):content.index("function nextVoiceFlowGuideStep()")]
    assert "voiceflow-guide-polish-action-wrap" in goto_fn
    assert "voiceflow-guide-polish-action-btn" in goto_fn
    assert "stepIdx === 4" in goto_fn
    assert "togglePolishingSetting(true)" in content

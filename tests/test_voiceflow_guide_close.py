"""Test suite verifying the Voice Flow onboarding guide close path and history sync."""
from pathlib import Path
import re


ROOT = Path(__file__).parents[1]
APP_JS = ROOT / "src" / "voice_flow" / "gui" / "app.js"


def test_voiceflow_guide_close_cleans_demo_card_unconditionally() -> None:
    """stopVoiceFlowGuide must unconditionally clean demo cards and refresh real history."""
    content = APP_JS.read_text(encoding="utf-8")
    assert "function stopVoiceFlowGuide(" in content

    stop_fn = content[content.index("function stopVoiceFlowGuide("):content.index("function replayOnboarding()")]
    # Verify demo card cleanup is not gated by !hasRealDictations
    assert "_cleanVoiceFlowGuideDemoCard();" in stop_fn
    assert "if (!hasRealDictations) {\n    _cleanVoiceFlowGuideDemoCard();\n  }" not in stop_fn

    # Verify lastHistoryHash is invalidated and loadHome is called
    assert 'lastHistoryHash = "";' in stop_fn
    assert "loadHome();" in stop_fn


def test_clean_demo_card_removes_sample_card_elements() -> None:
    """_cleanVoiceFlowGuideDemoCard must physically remove demo card DOM nodes."""
    content = APP_JS.read_text(encoding="utf-8")
    assert "function _cleanVoiceFlowGuideDemoCard()" in content

    clean_fn = content[content.index("function _cleanVoiceFlowGuideDemoCard()"):content.index("function gotoVoiceFlowGuideStep")]
    assert 'document.getElementById("voiceflow-guide-sample-card")' in clean_fn
    assert "sampleCard.remove();" in clean_fn
    assert 'document.querySelectorAll(".voiceflow-guide-demo-card")' in clean_fn
    assert "renderHistoryFeed(allHistoryRecords);" in clean_fn


def test_goto_step_cleans_demo_card_when_leaving_step1() -> None:
    """Transitioning away from Step 1 must clean demo cards without gating."""
    content = APP_JS.read_text(encoding="utf-8")
    goto_fn = content[content.index("function gotoVoiceFlowGuideStep(stepIdx)"):content.index("function nextVoiceFlowGuideStep()")]

    assert "if (prevStep === 1 && stepIdx !== 1)" in goto_fn
    assert "_cleanVoiceFlowGuideDemoCard();" in goto_fn


def test_render_history_feed_preserves_real_dictations() -> None:
    """renderHistoryFeed with real records populates dictation cards and does not render empty placeholder."""
    content = APP_JS.read_text(encoding="utf-8")
    assert "function renderHistoryFeed(records)" in content

    render_fn = content[content.index("function renderHistoryFeed(records)"):content.index("function filterHistory()")]
    assert "No dictations recorded yet" in render_fn
    assert "renderDictationCardHtml(r)" in render_fn

"""Test suite verifying post-PR-16 onboarding polish and user feedback requirements."""
from pathlib import Path

ROOT = Path(__file__).parents[1]
APP_JS = ROOT / "src" / "voice_flow" / "gui" / "app.js"
INDEX_HTML = ROOT / "src" / "voice_flow" / "gui" / "index.html"
CSS_FILE = ROOT / "src" / "voice_flow" / "gui" / "onboarding-hero.css"


def test_sidebar_welcome_tour_button_removed() -> None:
    """Welcome Tour button must be removed from the sidebar nav, remaining in Settings."""
    html_content = INDEX_HTML.read_text(encoding="utf-8")
    sidebar_idx = html_content.find('<nav class="nav-group">')
    settings_idx = html_content.find('id="settings-modal"')
    if settings_idx == -1:
        settings_idx = html_content.find('openSettings')

    # Ensure Welcome Tour is not inside the sidebar nav
    sidebar_chunk = html_content[sidebar_idx:sidebar_idx + 800]
    assert "replayOnboarding()" not in sidebar_chunk
    assert "Welcome Tour" not in sidebar_chunk

    # Ensure Replay Tour is available under Settings
    assert '<button class="action-btn" onclick="replayOnboarding()">Replay Tour</button>' in html_content


def test_red_circular_close_button_style() -> None:
    """Close/Cancel buttons must be styled as red circles with white cross."""
    css_content = CSS_FILE.read_text(encoding="utf-8")
    assert ".af-guide-close-btn {" in css_content
    close_idx = css_content.find(".af-guide-close-btn {")
    close_block = css_content[close_idx:close_idx + 600]

    assert "background: #ef4444 !important;" in close_block
    assert "border-radius: 50% !important;" in close_block
    assert "color: #ffffff !important;" in close_block
    assert "display: inline-flex !important;" in close_block


def test_welcome_tour_auto_mode_support() -> None:
    """Welcome Tour must support default Auto mode with toggle to Manual."""
    app_content = APP_JS.read_text(encoding="utf-8")
    assert "let onboardingAutoMode = true;" in app_content
    assert "function toggleOnboardingAutoMode()" in app_content
    assert "function updateOnboardingAutoModeUI()" in app_content

    html_content = INDEX_HTML.read_text(encoding="utf-8")
    for i in range(1, 6):
        assert f'id="scene{i}-auto-btn"' in html_content


def test_one_time_guide_triggers_and_voiceflow_redirection() -> None:
    """Navigation starts each page's guide once (seen flags), Voice Flow pages share one guide.

    Updated for v1.0.3: initNavigation no longer inlines the redirect + flag checks
    (that expectation already failed on main 337dacb); it delegates to
    scheduleAutomaticGuide(), which checks the persisted one-time seen flags.
    """
    app_content = APP_JS.read_text(encoding="utf-8")
    init_nav_idx = app_content.find("function initNavigation()")
    init_nav_block = app_content[init_nav_idx:init_nav_idx + 2400]
    assert "VOICEFLOW_CHILD_PAGES.includes(pageId)" in init_nav_block
    assert 'scheduleAutomaticGuide("voice", pageId);' in init_nav_block
    assert 'scheduleAutomaticGuide("video", pageId);' in init_nav_block
    assert 'scheduleAutomaticGuide("audio", pageId);' in init_nav_block
    sched = app_content[app_content.index("function scheduleAutomaticGuide("):][:3000]
    assert "AUTOMATIC_GUIDE_SEEN_FLAGS[feature]" in sched
    assert 'onboardingFlag(seenFlag) === "1"' in sched
    flags = app_content[app_content.index("const AUTOMATIC_GUIDE_SEEN_FLAGS"):][:200]
    for flag in ("vf_onboarding.vf_voice_guided", "vf_onboarding.af_guided", "vf_onboarding.vf_guided"):
        assert flag in flags
    voice_menu = app_content[app_content.index("function toggleVoiceFlowMenu("):][:600]
    assert 'switchPage("home", { userInitiated: true });' in voice_menu
    assert 'scheduleAutomaticGuide("voice", "home");' in voice_menu


def test_deepgram_rufus_voice_configured() -> None:
    """Narrator voice must be Deepgram Rufus."""
    app_content = APP_JS.read_text(encoding="utf-8")
    assert 'const ONBOARDING_NARRATOR_VOICE = "deepgram/flux-rufus-en";' in app_content

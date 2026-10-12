"""Test suite verifying removal of misleading 1080p monitor spec text in Welcome Tour (Item 15)."""
from pathlib import Path

ROOT = Path(__file__).parents[1]
INDEX_HTML = ROOT / "src" / "voice_flow" / "gui" / "index.html"
CSS_FILE = ROOT / "src" / "voice_flow" / "gui" / "onboarding-hero.css"


def test_1080p_spec_text_removed_from_html() -> None:
    """The text '1080p Ultra HD · 60fps Display' must not exist anywhere in index.html."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    assert "1080p Ultra HD" not in content
    assert "60fps Display" not in content

    # The spec spans should still exist but have empty contents
    assert '<span class="s2-monitor-spec"></span>' in content
    assert '<span class="s3-monitor-spec"></span>' in content
    assert '<span class="s4-monitor-spec"></span>' in content


def test_css_collapses_empty_monitor_specs() -> None:
    """CSS must have rule collapsing empty monitor spec elements."""
    css_content = CSS_FILE.read_text(encoding="utf-8")
    assert ".s2-monitor-spec:empty" in css_content
    assert ".s3-monitor-spec:empty" in css_content
    assert ".s4-monitor-spec:empty" in css_content

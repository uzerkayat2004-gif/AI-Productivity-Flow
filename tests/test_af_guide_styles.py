"""The Audio Flow feature guide must ship with its stylesheet and media.

Without these rules the guide rendered as raw text in the page flow and its
interaction lock froze the app (see the PR #9 safety net)."""
from __future__ import annotations

import re
from pathlib import Path

GUI = Path(__file__).resolve().parents[1] / "src" / "voice_flow" / "gui"


def _overlay_html() -> str:
    html = (GUI / "index.html").read_text(encoding="utf-8")
    start = html.index('<div id="audioflow-guide-overlay"')
    end = html.index("\n  </div>", start)
    return html[start:end]


def _css() -> str:
    return (GUI / "onboarding-hero.css").read_text(encoding="utf-8")


def _has_rule(css: str, selector: str) -> bool:
    return re.search(re.escape(selector) + r"(?![\w-])", css) is not None


def test_every_guide_class_in_the_markup_is_styled():
    classes = set()
    for attr in re.findall(r'class="([^"]+)"', _overlay_html()):
        classes.update(c for c in attr.split() if c.startswith(("af-guide", "af-sim")))
    assert "af-guide-card" in classes and "af-guide-overlay" in classes
    css = _css()
    unstyled = sorted(c for c in classes if not _has_rule(css, "." + c))
    assert not unstyled, f"guide classes without CSS rules: {unstyled}"


def test_guide_overlay_is_fixed_and_hidden_class_hides_it():
    css = _css()
    overlay = re.search(r"\n\.af-guide-overlay\s*\{([^}]*)\}", css)
    assert overlay and "position: fixed" in overlay.group(1)
    hidden = re.search(r"\.af-guide-overlay\.hidden\s*\{([^}]*)\}", css)
    assert hidden and ("display: none" in hidden.group(1) or "visibility: hidden" in hidden.group(1))
    for state in ("body.af-guide-active", ".af-guide-card.is-step4", ".af-guide-overlay.is-step4-active"):
        assert _has_rule(css, state), state
    for keyframes in ("af-spotlight-pulse", "af-dot-pulse"):
        assert f"@keyframes {keyframes}" in css


def test_guide_stylesheet_is_loaded_and_ships_finished_guides():
    html = (GUI / "index.html").read_text(encoding="utf-8")
    assert re.search(r'href="onboarding-hero\.css\?v=[^"]+"', html)
    css = _css()
    # Audio, Video, and Voice Flow guides all ship styled now.
    for selector in (".af-guide-overlay", ".vf-guide-card", ".af-guide-card"):
        assert _has_rule(css, selector), selector


def test_guide_media_is_in_the_repo():
    app = (GUI / "app.js").read_text(encoding="utf-8")
    refs = set(re.findall(r"assets/onboarding/af_guide_[\w.-]+", app))
    refs.update(re.findall(r'(?:src|poster)="(assets/onboarding/[\w.-]+)"', _overlay_html()))
    assert len(refs) >= 6
    missing = sorted(r for r in refs if not (GUI / r).is_file())
    assert not missing, missing

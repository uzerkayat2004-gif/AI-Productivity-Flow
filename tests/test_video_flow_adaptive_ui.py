from pathlib import Path
import json
import re


ROOT = Path(__file__).resolve().parents[1]


def test_index_html_adaptive_format_cards_and_banner():
    html = (ROOT / "src" / "voice_flow" / "gui" / "index.html").read_text(encoding="utf-8")

    # 1. Verify "25-40 min" and "25–40 min" are completely removed
    assert "25-40 min" not in html
    assert "25–40 min" not in html
    assert "25-40" not in html
    assert "25–40" not in html

    # 2. Verify #vf-doc-profile-banner exists directly above format selector
    assert 'id="vf-doc-profile-banner"' in html
    banner_idx = html.index('id="vf-doc-profile-banner"')
    grid_idx = html.index('class="vf-format-grid"')
    assert banner_idx < grid_idx, "#vf-doc-profile-banner must be positioned directly above the format selector grid"

    # Banner content requirements
    assert "Document Analysis:" in html
    assert "Auto-scaled video target:" in html
    assert "Max 5m ceiling" in html

    # 3. Verify format cards
    # Auto-Adaptive (Recommended)
    assert 'data-format="auto"' in html
    assert "Auto-Adaptive" in html
    assert "Recommended" in html
    assert "vf-speed-adaptive" in html

    # Brief
    assert 'data-format="brief"' in html
    assert "Concise (~1–2 min)" in html
    assert "High-yield quick summary" in html

    # Short
    assert 'data-format="short"' in html
    assert "Vertical (~1–2.5 min)" in html
    assert "Short-form vertical summary" in html

    # Explainer
    assert 'data-format="explainer"' in html
    assert "Standard (~2–4 min)" in html
    assert "Comprehensive visual breakdown" in html

    # Cinematic
    assert 'data-format="cinematic"' in html
    assert "AI Documentary (~1–5 min Max)" in html
    assert "Scaled to document size, strictly capped at 5 minutes!" in html


def test_video_flow_js_adaptive_logic_and_no_stale_labels():
    js = (ROOT / "src" / "voice_flow" / "gui" / "video-flow.js").read_text(encoding="utf-8")

    # Verify no stale 25-40 min text
    assert "25-40" not in js
    assert "25–40" not in js

    # Verify Auto-Adaptive is default or supported
    assert 'vfSelectedFormat = "auto"' in js
    assert "calculateDocumentScaling" in js
    assert "applyDocumentProfile" in js
    assert "analyzeSourceDocument" in js
    assert "scheduleSourceAnalysis" in js
    assert "/api/video-flow/analyze-source" in js
    assert "initVideoFlowAdaptiveUI" in js

    # Verify debounced event listeners on input/file
    assert 'sourceInput.addEventListener("input"' in js
    assert 'sourceInput.addEventListener("paste"' in js
    assert 'fileInput.addEventListener("change"' in js

    # Verify payload includes resolved adaptive settings
    assert "adaptive_settings" in js
    assert "resolvedFormat" in js
    assert "max_ceiling_seconds: 300" in js


def test_video_flow_css_glassmorphic_styling():
    css = (ROOT / "src" / "voice_flow" / "gui" / "video-flow.css").read_text(encoding="utf-8")

    # Verify #vf-doc-profile-banner styling
    assert ".vf-doc-profile-banner" in css
    banner_css = css[css.index(".vf-doc-profile-banner"):css.index(".vf-speed-badge-icon")]

    # Glassmorphism
    assert "backdrop-filter: blur(" in banner_css
    assert "border:" in banner_css

    # Cyan accents
    assert "6, 182, 212" in banner_css or "cyan" in banner_css or "#22d3ee" in banner_css
    assert "#38bdf8" in banner_css
    assert "#22d3ee" in banner_css

    # Adaptive pill styles
    assert ".vf-speed-adaptive" in css
    assert ".vf-speed-guidance-badge.speed-adaptive" in css
    assert ".vf-recommended-pill" in css

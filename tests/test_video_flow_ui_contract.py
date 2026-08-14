from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_video_flow_page_order_and_collapsed_history_contract():
    html = (ROOT / "src" / "voice_flow" / "gui" / "index.html").read_text(encoding="utf-8")
    page = html[html.index('id="page-videoflow"'):html.index("<!-- ENLARGED SETTINGS MODAL -->")]

    assert page.index('id="vf-history-panel"') < page.index("vf-create-panel")
    assert page.index("vf-create-panel") < page.index("vf-model-hero")
    assert page.index('id="vf-oauth-provider-grid"') < page.index('id="vf-api-provider-grid"')
    assert page.index('id="vf-api-provider-grid"') < page.index('id="vf-local-provider-grid"')
    assert page.index('id="vf-local-provider-grid"') < page.index('id="vf-combo-section"')
    assert 'aria-expanded="false"' in page
    assert 'id="vf-history-body" style="display: none;"' in page
    assert 'id="vf-model-picker-button"' in page
    assert 'id="vf-model-catalog"' not in page
    assert 'id="vf-model-picker-modal"' in html
    assert 'id="vf-combo-model-picker-modal"' in html


def test_video_flow_assets_and_provider_detail_use_the_current_studio_contract():
    html = (ROOT / "src" / "voice_flow" / "gui" / "index.html").read_text(encoding="utf-8")
    page = html[html.index('id="page-videoflow"'):html.index("<!-- ENLARGED SETTINGS MODAL -->")]

    # A versioned URL prevents the desktop WebView from reviving an older
    # script or stylesheet, whose provider cards used the inline behavior.
    assert 'href="video-flow.css?v=20260811"' in html
    assert 'src="video-flow.js?v=20260811"' in html

    assert 'id="vf-provider-detail-panel"' in page
    assert 'class="vf-provider-detail-panel hidden"' in page
    assert 'id="vf-provider-detail-content"' in page
    assert 'onclick="closeVideoProvider()"' in page
    assert 'id="vf-combo-section"' in page
    assert 'onclick="openVideoComboModal()"' in page
    assert 'id="vf-model-picker-button"' in page
    assert 'onclick="openVideoModelPicker()"' in page


def test_video_flow_provider_cards_never_navigate_to_global_providers():
    script = (ROOT / "src" / "voice_flow" / "gui" / "video-flow.js").read_text(encoding="utf-8")

    assert 'switchPage("providers")' not in script
    assert "/api/video-flow/providers/details" in script
    assert "openVideoProvider" in script
    assert "renderVideoBackendFailure" in script
    assert "vf-oauth-provider-grid" in script
    assert 'model.full_id !== "local/deterministic"' in script
    assert 'value="local/deterministic"' not in script
    assert "engine_version" in script


def test_video_flow_provider_and_model_picker_match_reference_workflow():
    script = (ROOT / "src" / "voice_flow" / "gui" / "video-flow.js").read_text(encoding="utf-8")
    css = (ROOT / "src" / "voice_flow" / "gui" / "video-flow.css").read_text(encoding="utf-8")

    assert 'page.classList.add("vf-provider-open")' in script
    assert 'page?.classList.remove("vf-provider-open")' in script
    assert '#page-videoflow.vf-provider-open > :not(#vf-provider-detail-panel)' in css
    assert "function vfSelectableVideoModels()" in script
    assert "function vfSelectableVideoCombos()" in script
    assert "function renderVideoModelPicker()" in script
    assert "function renderVideoComboModelPicker()" in script
    assert "vfComboDraftModels" in script
    assert "renderVideoModelBrowser" not in script


def test_video_flow_service_worker_refreshes_the_html_shell():
    worker = (ROOT / "src" / "voice_flow" / "gui" / "sw.js").read_text(encoding="utf-8")

    assert re.search(r'const CACHE_NAME = "voice-flow-cache-v\d+', worker)
    assert 'const APP_SHELL = "/index.html"' in worker
    assert 'evt.request.mode === "navigate"' in worker
    assert "cache.put(APP_SHELL, response.clone())" in worker


def test_video_flow_model_selector_does_not_duplicate_the_builtin_local_model():
    script = (ROOT / "src" / "voice_flow" / "gui" / "video-flow.js").read_text(encoding="utf-8")

    start = script.index("function vfSelectableVideoModels()")
    end = script.index("function vfIsSelectableVideoModelRef", start)
    helper = script[start:end]
    assert 'model.full_id !== "local/deterministic"' in helper

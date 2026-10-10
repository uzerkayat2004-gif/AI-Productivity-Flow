from __future__ import annotations

import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from voice_flow.video_flow_widget import (
    NOTEBOOKLM_FORMAT_OPTIONS,
    NOTEBOOKLM_STYLE_OPTIONS,
    VideoFlowScreenWidget,
    _local_analyze_fallback,
    launch_video_flow_composer,
    video_flow_widget,
)


@pytest.fixture(scope="module")
def tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass


def test_notebooklm_formats_and_styles_catalog() -> None:
    formats = VideoFlowScreenWidget.catalog_format_options()
    format_refs = [f['ref'] for f in formats]
    assert format_refs == ['auto', 'brief', 'short', 'explainer', 'cinematic']
    assert any('Auto-Adaptive (Recommended)' in f['label'] for f in formats)

    styles = VideoFlowScreenWidget.catalog_style_options()
    style_refs = [s['ref'] for s in styles]
    assert style_refs == [
        'auto', 'classic', 'whiteboard', 'anime', 'kawaii',
        'watercolor', 'retro-print', 'heritage', 'paper-craft', 'custom',
    ]


def test_local_analyze_fallback() -> None:
    # 0 words
    empty = _local_analyze_fallback('')
    assert empty['word_count'] == 0
    assert empty['target_duration_seconds'] == 30
    assert empty['recommended_format'] == 'short'

    # ~540 words (~2 pages)
    sample_540 = ' '.join(['word'] * 540)
    res = _local_analyze_fallback(sample_540)
    assert res['word_count'] == 540
    assert res['estimated_pages'] == 1.96
    assert 90 <= res['target_duration_seconds'] <= 150
    assert res['recommended_format'] == 'explainer'

    # 3000 words (dense document)
    sample_3000 = ' '.join(['word'] * 3000)
    dense = _local_analyze_fallback(sample_3000)
    assert dense['word_count'] == 3000
    assert dense['target_duration_seconds'] <= 300
    assert '(Max ceiling)' in dense['target_duration_display']
    assert dense['recommended_format'] == 'cinematic'


def test_widget_notebooklm_default_and_live_analysis(tk_root) -> None:
    widget = VideoFlowScreenWidget()
    widget.attach_root(tk_root)
    widget.show_composer('Initial short text.')
    tk_root.update()

    # Check default provider is notebooklm
    assert widget._controls['provider'].get() == 'notebooklm'
    assert widget._controls['generate'].cget('state') == 'normal'

    # Check formats and styles are populated
    format_values = widget._controls['format_box']['values']
    assert 'Auto-Adaptive (Recommended)' in format_values

    style_values = widget._controls['style_box']['values']
    assert 'Auto' in style_values
    assert 'Custom' in style_values

    # Live document analysis banner for ~540 words
    words_540 = ' '.join(['quantum'] * 540)
    widget._controls['source'].delete('1.0', 'end')
    widget._controls['source'].insert('1.0', words_540)
    widget._on_source_text_changed()

    banner_text = widget._controls['analysis_banner'].get()
    assert '📄 2 pages (~540 words)' in banner_text
    assert 'Auto-scaled video target:' in banner_text
    assert '(Max 5m ceiling)' in banner_text

    # Change style to Custom and verify custom prompt entry is packed
    widget._controls['style_display'].set('Custom')
    widget._on_style_selected()
    assert widget._custom_style_frame.winfo_manager() == 'pack'

    # Change style back to Auto and verify custom prompt entry is unpacked
    widget._controls['style_display'].set('Auto')
    widget._on_style_selected()
    assert widget._custom_style_frame.winfo_manager() == ''

    if widget.win and widget.win.winfo_exists():
        widget.win.withdraw()


def test_widget_generate_notebooklm_payload(tk_root) -> None:
    widget = VideoFlowScreenWidget()
    widget.attach_root(tk_root)
    widget.show_composer('Document about AI productivity.')
    tk_root.update()

    captured_payload = {}
    def mock_generate(payload):
        captured_payload.update(payload)
        return {'id': 'job-test-123'}

    widget.on_generate = mock_generate
    widget._controls['title'].set('AI Test Title')
    widget._controls['format_display'].set('Cinematic (~1–5 min Max)')
    widget._on_format_selected()
    widget._controls['style_display'].set('Classic')
    widget._on_style_selected()
    widget._controls['nlm_focus'].insert('1.0', 'High contrast visuals')

    widget._generate()

    assert captured_payload['provider'] == 'notebooklm'
    assert captured_payload['video_engine'] == 'notebooklm'
    assert captured_payload['format'] == 'cinematic'
    assert captured_payload['style'] == 'classic'
    assert captured_payload['focus'] == 'High contrast visuals'
    assert captured_payload['visual_direction'] == 'High contrast visuals'
    assert captured_payload['title'] == 'AI Test Title'
    assert 'document_profile' in captured_payload
    assert 'duration_seconds' in captured_payload
    assert captured_payload['duration_seconds'] > 0
    assert captured_payload.get('allow_local_fallback') is True

    if widget.win and widget.win.winfo_exists():
        widget.win.withdraw()


def test_widget_switch_to_native_provider_requires_model(tk_root) -> None:
    widget = VideoFlowScreenWidget()
    widget.attach_root(tk_root)
    widget.show_composer('Document for native rendering.')
    tk_root.update()

    # Apply empty catalog (no models)
    widget._apply_catalog({'models': []})

    # Switch to Native engine
    widget._controls['provider'].set('native')
    tk_root.update()

    # For native engine without models, generate should be disabled
    assert widget._controls['generate'].cget('state') == 'disabled'

    # Switch back to NotebookLM
    widget._controls['provider'].set('notebooklm')
    tk_root.update()

    # For NotebookLM, generate should immediately be normal
    assert widget._controls['generate'].cget('state') == 'normal'

    if widget.win and widget.win.winfo_exists():
        widget.win.withdraw()


def test_widget_auth_banner_authenticated(tk_root) -> None:
    widget = VideoFlowScreenWidget()
    widget.attach_root(tk_root)

    with patch.object(widget, "_check_notebooklm_auth_local", return_value=(True, "testuser@gmail.com")), \
         patch.object(widget, "_refresh_models"):
        widget.show_composer("Test auth banner text")
        tk_root.update()

        assert widget._auth_is_authenticated is True
        assert "✨ Google NotebookLM Connected" in widget._auth_status_label.cget("text")
        assert "testuser@gmail.com" in widget._auth_status_label.cget("text")
        assert not widget._auth_signin_btn.winfo_ismapped()

    if widget.win and widget.win.winfo_exists():
        widget.win.withdraw()


def test_widget_auth_banner_unauthenticated(tk_root) -> None:
    widget = VideoFlowScreenWidget()
    widget.attach_root(tk_root)

    with patch.object(widget, "_check_notebooklm_auth_local", return_value=(False, None)), \
         patch.object(widget, "_refresh_models"):
        widget.show_composer("Test unauthenticated banner")
        tk_root.update()

        assert widget._auth_is_authenticated is False
        assert "⚠️ Google Account not connected" in widget._auth_status_label.cget("text")
        assert widget._auth_signin_btn.winfo_ismapped()
        assert widget._auth_signin_btn.cget("text") == "Sign in with Google"

    if widget.win and widget.win.winfo_exists():
        widget.win.withdraw()


def test_widget_auth_banner_signin_action(tk_root) -> None:
    widget = VideoFlowScreenWidget()
    widget.attach_root(tk_root)
    widget._build()

    with patch("webbrowser.open") as mock_open:
        widget._open_notebooklm_signin()
        mock_open.assert_called_once_with("http://127.0.0.1:8991/index.html?tab=video-flow")

    if widget.win and widget.win.winfo_exists():
        widget.win.withdraw()


def test_widget_auth_banner_provider_toggle(tk_root) -> None:
    widget = VideoFlowScreenWidget()
    widget.attach_root(tk_root)
    widget.show_composer("Test provider toggle")
    tk_root.update()

    # NotebookLM is default: auth banner is packed
    assert widget._auth_banner_frame.winfo_manager() == "pack"

    # Switch to Native engine: auth banner is hidden
    widget._controls["provider"].set("native")
    tk_root.update()
    assert widget._auth_banner_frame.winfo_manager() == ""

    # Switch back to NotebookLM: auth banner is shown again
    widget._controls["provider"].set("notebooklm")
    tk_root.update()
    assert widget._auth_banner_frame.winfo_manager() == "pack"

    if widget.win and widget.win.winfo_exists():
        widget.win.withdraw()


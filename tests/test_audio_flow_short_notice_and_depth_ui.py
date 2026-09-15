"""Comprehensive tests for Audio Flow short text notice flow and summary depth UI polish."""

from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

from voice_flow.audio_flow_widget import (
    AudioFlowFloatingWidget,
    _is_short_text,
)


def test_is_short_text_boundaries():
    """Verify edge cases for short text classification."""
    assert _is_short_text("") is False
    assert _is_short_text("   \n\t  ") is False
    assert _is_short_text("a") is True

    # 10 words, short text
    assert _is_short_text("One two three four five six seven eight nine ten.") is True

    # Text under 1800 chars and under 350 words -> True
    sample_under = "word " * 340
    assert len(sample_under.split()) == 340
    assert len(sample_under) < 1800
    assert _is_short_text(sample_under) is True

    # Text with 400 words and 2500 chars -> False (>= 1 page)
    sample_over = "paragraph with several words to exceed one single printed page. " * 40
    assert len(sample_over.split()) > 350
    assert len(sample_over) > 1800
    assert _is_short_text(sample_over) is False


def test_short_warning_stage_lifecycle_and_actions():
    """Test full cycle: MODE_SELECT -> SHORT_WARNING -> Use Read OR Make Anyway -> DEPTH_SELECT."""
    widget = AudioFlowFloatingWidget()
    widget._current_text = "Short text under one page for testing notice."
    widget._stage = widget.STAGE_MODE_SELECT

    triggers = []
    widget.on_trigger = lambda text, mode="read", summary_depth=None: triggers.append((text, mode, summary_depth))
    widget.hide = MagicMock(side_effect=lambda: setattr(widget, "_is_visible", False))

    # 1. Clicking Summary in MODE_SELECT (x in 109..224) triggers SHORT_WARNING
    class FakeEvent:
        def __init__(self, x, y=15):
            self.x = x
            self.y = y

    widget._is_visible = True
    widget.root = SimpleNamespace(after=lambda *args: None)
    widget._on_click(FakeEvent(150, 15))
    assert widget._stage == widget.STAGE_SHORT_WARNING
    assert widget._get_current_dimensions() == (384, 96)
    assert widget._anim_active() is True

    # 2. Hover index checks in STAGE_SHORT_WARNING
    # Top banner (y < 48) -> None
    assert widget._hover_index(50, 20) is None
    assert widget._hover_index(200, 20) is None
    # Bottom pills (y >= 48)
    assert widget._hover_index(50, 65) == 0    # Left button: "⚡ Use Read"
    assert widget._hover_index(180, 65) == 0   # Right edge of "⚡ Use Read"
    assert widget._hover_index(195, 65) == 1   # Left edge of "Make Anyway"
    assert widget._hover_index(280, 65) == 1   # Center of "Make Anyway"

    # 3. Action: Clicking "⚡ Use Read" triggers read mode and hides
    widget._on_click(FakeEvent(80, 65))
    assert triggers == [("Short text under one page for testing notice.", "read", None)]
    assert widget.hide.called

    # 4. Action: Clicking "Make Anyway" transitions to STAGE_DEPTH_SELECT
    widget._stage = widget.STAGE_SHORT_WARNING
    widget._is_visible = True
    widget.hide.reset_mock()
    triggers.clear()

    widget._on_click(FakeEvent(250, 65))
    assert widget._stage == widget.STAGE_DEPTH_SELECT
    assert widget._get_current_dimensions() == (265, 32)
    assert not widget.hide.called

    # 5. In STAGE_DEPTH_SELECT: picking depth triggers summary with selected depth
    # Short
    widget._on_click(FakeEvent(30, 15))
    assert triggers[-1] == ("Short text under one page for testing notice.", "summary", "short")
    triggers.clear()

    # Balanced
    widget._stage = widget.STAGE_DEPTH_SELECT
    widget._on_click(FakeEvent(120, 15))
    assert triggers[-1] == ("Short text under one page for testing notice.", "summary", "balanced")
    triggers.clear()

    # Deep Dive
    widget._stage = widget.STAGE_DEPTH_SELECT
    widget._on_click(FakeEvent(200, 15))
    assert triggers[-1] == ("Short text under one page for testing notice.", "summary", "deep_dive")


def test_long_document_skips_short_warning():
    """Verify text >= 1 page bypasses STAGE_SHORT_WARNING directly to STAGE_DEPTH_SELECT."""
    widget = AudioFlowFloatingWidget()
    long_text = ("This is a comprehensive long document with extensive paragraphs. " * 50)
    assert _is_short_text(long_text) is False

    widget._current_text = long_text
    widget._stage = widget.STAGE_MODE_SELECT

    class FakeEvent:
        x = 150
        y = 15

    widget._on_click(FakeEvent())
    # Directly enters depth select
    assert widget._stage == widget.STAGE_DEPTH_SELECT
    assert widget._get_current_dimensions() == (265, 32)


def test_short_warning_and_depth_select_rendering_cache(monkeypatch):
    """Verify PIL supersampled images render without error for all hover states and anim frames."""
    monkeypatch.setattr("voice_flow.audio_flow_widget.ImageTk.PhotoImage", lambda img: img)

    widget = AudioFlowFloatingWidget()
    widget._current_text = "Short text"

    # Test short warning rendering
    img0 = widget._render_short_warning_image(384, 96, hover=None, anim_frame=0)
    assert img0 is not None
    img1 = widget._render_short_warning_image(384, 96, hover=0, anim_frame=1)
    assert img1 is not None
    img2 = widget._render_short_warning_image(384, 96, hover=1, anim_frame=2)
    assert img2 is not None

    # Test depth select rendering with 3 options and hover variations
    img_depth_idle = widget._render_depth_select_image(265, 32, hover=None, anim_frame=0)
    assert img_depth_idle is not None
    img_depth_h0 = widget._render_depth_select_image(265, 32, hover=0, anim_frame=1)
    assert img_depth_h0 is not None
    img_depth_h1 = widget._render_depth_select_image(265, 32, hover=1, anim_frame=2)
    assert img_depth_h1 is not None
    img_depth_h2 = widget._render_depth_select_image(265, 32, hover=2, anim_frame=3)
    assert img_depth_h2 is not None


def test_fallback_canvas_rendering_for_short_warning():
    """Verify pure canvas fallback rendering works without error in headless/mock environments."""
    widget = AudioFlowFloatingWidget()
    canvas = MagicMock()

    # Fallback for short warning
    widget._stage = widget.STAGE_SHORT_WARNING
    widget._draw_fallback(canvas, 384, 96)
    assert canvas.create_text.called

    # Fallback for depth select
    canvas.reset_mock()
    widget._stage = widget.STAGE_DEPTH_SELECT
    widget._draw_fallback(canvas, 265, 32)
    assert canvas.create_text.called


def test_make_anyway_transition_contains_point_grace():
    """Verify that clicking 'Make Anyway' at y=65 does NOT cause contains_point to fail or widget to prematurely hide."""
    widget = AudioFlowFloatingWidget()
    widget._stage = widget.STAGE_SHORT_WARNING
    widget._current_text = "Short doc sample"
    widget._is_visible = True
    widget._pos_x = 400
    widget._pos_y = 300
    widget.win = MagicMock()
    widget.win.winfo_rootx = MagicMock(return_value=400)
    widget.win.winfo_rooty = MagicMock(return_value=300)

    # Point where "Make Anyway" button was clicked (x=250, y=65 relative to widget top-left)
    click_x = 400 + 250
    click_y = 300 + 65

    # Before click: inside STAGE_SHORT_WARNING (384x96)
    assert widget.contains_point(click_x, click_y) is True

    # User clicks "Make Anyway"
    widget._on_click(SimpleNamespace(x=250, y=65))
    assert widget._stage == widget.STAGE_DEPTH_SELECT

    # Immediately after click: during transition grace period, contains_point MUST remain True!
    assert widget.contains_point(click_x, click_y) is True


def test_short_warning_banner_click_does_not_trigger_read():
    """Verify clicking the informational notice banner (y < 30) does not trigger read mode or hide."""
    widget = AudioFlowFloatingWidget()
    widget._stage = widget.STAGE_SHORT_WARNING
    widget._current_text = "Short text"
    widget._is_visible = True

    triggers = []
    widget.on_trigger = lambda text, mode="read", summary_depth=None: triggers.append((text, mode, summary_depth))
    widget.hide = MagicMock()

    # Click on the notice banner (y = 15)
    widget._on_click(SimpleNamespace(x=100, y=15))
    assert len(triggers) == 0
    assert not widget.hide.called
    assert widget._stage == widget.STAGE_SHORT_WARNING


def test_click_drag_jitter_immunity():
    """Verify micro-motion jitter (< 8px) during a mouse click does not get dropped as a drag."""
    widget = AudioFlowFloatingWidget()
    widget._stage = widget.STAGE_DEPTH_SELECT
    widget._current_text = "Sample article"
    widget._is_visible = True

    triggers = []
    widget.on_trigger = lambda text, mode="summary", summary_depth=None: triggers.append((text, mode, summary_depth))
    widget.hide = MagicMock()

    # Press down at root (500, 500)
    widget._on_press(SimpleNamespace(x=30, y=15, x_root=500, y_root=500))
    assert widget._is_dragging is False

    # Jitter motion of 4px
    widget._on_drag(SimpleNamespace(x_root=503, y_root=503))
    assert widget._is_dragging is False

    # Release mouse on Short depth button
    widget._on_release(SimpleNamespace(x=30, y=15))
    assert widget._is_dragging is False
    assert len(triggers) == 1
    assert triggers[0] == ("Sample article", "summary", "short")


def test_on_motion_resets_hide_timer(monkeypatch):
    """Verify mouse motion over widget resets the auto-hide timer to prevent disappearing while deciding."""
    widget = AudioFlowFloatingWidget()
    widget._draw = MagicMock()
    widget.canvas = MagicMock()

    reset_calls = []
    widget._reset_hide_timer = lambda timeout=8.0: reset_calls.append(timeout)

    widget._on_motion(SimpleNamespace(x=100, y=15))
    assert len(reset_calls) == 1
    assert reset_calls[0] == 8.0


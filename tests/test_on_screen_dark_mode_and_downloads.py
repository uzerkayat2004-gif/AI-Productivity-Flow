import os
import sys
from pathlib import Path
import pytest

from voice_flow.audio_summary_player import get_user_downloads_dir
from voice_flow.overlay import FloatingOverlayBar
from voice_flow.audio_flow_dialog import _apply_theme_colors
import voice_flow.audio_flow_dialog as af_dialog
from voice_flow.video_flow_widget import get_composer_colors, COMPOSER_DARK_COLORS, COMPOSER_LIGHT_COLORS


def test_get_user_downloads_dir_returns_valid_dir():
    dl = get_user_downloads_dir()
    assert isinstance(dl, Path)
    # On this machine, it should resolve to D:\Downloads or a real directory
    assert dl.exists() or dl.parent.exists()


def test_overlay_bar_theme_colors(monkeypatch):
    from voice_flow.storage import storage

    bar = FloatingOverlayBar.__new__(FloatingOverlayBar)

    # Test Light mode
    monkeypatch.setattr(storage, "get_setting", lambda k, default=None: "light" if k == "on_screen_ui_theme" else default)
    assert not bar._is_theme_dark()
    assert bar.WHITE == "#FFFFFF"
    assert bar.BORDER == "#FFD0B0"
    assert bar.INK == "#241708"
    assert bar.ORANGE == "#FF6A00"
    # Resting state remains constant
    assert bar.BG_REST == "#17171C"
    assert bar.BORDER_REST == "#2C2C36"

    # Test Dark mode
    monkeypatch.setattr(storage, "get_setting", lambda k, default=None: "dark" if k == "on_screen_ui_theme" else default)
    assert bar._is_theme_dark()
    assert bar.WHITE == "#20201f"
    assert bar.BORDER == "#3b3834"
    assert bar.INK == "#f5f1ea"
    assert bar.ORANGE == "#e6b092"
    assert bar.ORANGE_DEEP == "#d49474"
    assert bar.ORANGE_FAINT == "#282725"
    # Resting state remains constant
    assert bar.BG_REST == "#17171C"
    assert bar.BORDER_REST == "#2C2C36"


def test_audio_flow_dialog_dark_mode_tokens(monkeypatch):
    from voice_flow.storage import storage

    # Light mode
    monkeypatch.setattr(storage, "get_setting", lambda k, default=None: "light" if k == "on_screen_ui_theme" else default)
    _apply_theme_colors()
    assert af_dialog.WHITE == "#FFFFFF"
    assert af_dialog.BADGE_BG == "#F5F5F7"

    # Dark mode
    monkeypatch.setattr(storage, "get_setting", lambda k, default=None: "dark" if k == "on_screen_ui_theme" else default)
    _apply_theme_colors()
    assert af_dialog.WHITE == "#20201f"
    assert af_dialog.BORDER == "#3b3834"
    assert af_dialog.INK == "#f5f1ea"
    assert af_dialog.ORANGE == "#e6b092"
    assert af_dialog.BADGE_BG == "#282725"
    assert af_dialog.BADGE_FG == "#b6aea2"
    assert af_dialog.BTN_TEXT == "#20201f"


def test_video_flow_composer_dark_mode_tokens(monkeypatch):
    from voice_flow.storage import storage

    # Light mode
    monkeypatch.setattr(storage, "get_setting", lambda k, default=None: "light" if k == "on_screen_ui_theme" else default)
    colors_light = get_composer_colors()
    assert colors_light["surface"] == COMPOSER_LIGHT_COLORS["surface"]
    assert colors_light["orange"] == "#ff6a00"

    # Dark mode
    monkeypatch.setattr(storage, "get_setting", lambda k, default=None: "dark" if k == "on_screen_ui_theme" else default)
    colors_dark = get_composer_colors()
    assert colors_dark["surface"] == "#20201f"
    assert colors_dark["border"] == "#3b3834"
    assert colors_dark["orange"] == "#e6b092"
    assert colors_dark["background"] == "#161615"


def test_audio_flow_widget_minimal_circle_dark_mode(monkeypatch):
    from unittest.mock import MagicMock
    from voice_flow.storage import storage
    from voice_flow.audio_flow_widget import AudioFlowFloatingWidget

    assert AudioFlowFloatingWidget.SIZE == 26

    widget = AudioFlowFloatingWidget.__new__(AudioFlowFloatingWidget)
    widget._image_cache = {}
    widget._hover = None
    widget._is_playing = False
    widget._is_paused = False
    widget._anim_frame = 0

    # Light mode
    monkeypatch.setattr(storage, "get_setting", lambda k, default=None: "light" if k == "on_screen_ui_theme" else default)
    assert not widget._is_theme_dark()

    mock_canvas = MagicMock()
    widget._draw_minimal_vector(mock_canvas, 26, 26)
    assert mock_canvas.create_oval.called
    assert mock_canvas.create_line.called

    # Dark mode idle
    monkeypatch.setattr(storage, "get_setting", lambda k, default=None: "dark" if k == "on_screen_ui_theme" else default)
    assert widget._is_theme_dark()

    mock_canvas.reset_mock()
    widget._draw_minimal_vector(mock_canvas, 26, 26)
    assert mock_canvas.create_oval.called
    # Check that dark fill and outline were passed to base circle oval
    base_oval_kwargs = mock_canvas.create_oval.call_args_list[0][1]
    assert base_oval_kwargs.get("fill") == "#20201f"
    assert base_oval_kwargs.get("outline") == "#3b3834"

    # Dark mode hover
    widget._hover = 0
    mock_canvas.reset_mock()
    widget._draw_minimal_vector(mock_canvas, 26, 26)
    base_oval_kwargs_hover = mock_canvas.create_oval.call_args_list[0][1]
    assert base_oval_kwargs_hover.get("outline") == "#e6b092"

    # Dark mode playing & paused
    widget._is_playing = True
    widget._is_paused = False
    mock_canvas.reset_mock()
    widget._draw_minimal_vector(mock_canvas, 26, 26)
    assert mock_canvas.create_arc.called

    widget._is_paused = True
    mock_canvas.reset_mock()
    widget._draw_minimal_vector(mock_canvas, 26, 26)
    assert mock_canvas.create_polygon.called


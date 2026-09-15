from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from voice_flow.audio_flow_dialog import AudioFlowSettingsDialog, open_audio_flow_settings
from voice_flow.overlay import FloatingOverlayBar
from voice_flow.storage import storage


def _get_or_create_root():
    root = getattr(tk, "_default_root", None)
    if root is None:
        try:
            root = tk.Tk()
            root.withdraw()
        except Exception:
            pass
    return root


def test_audio_flow_dialog_renders_complete_catalog_and_groups() -> None:
    root = _get_or_create_root()
    if not root:
        return
    dialog = AudioFlowSettingsDialog(root)
    try:
        # Check that the model list contains groups and model rows
        # (_list_inner is the actual list container; scrollable_frame wraps it)
        children = dialog._list_inner.winfo_children()
        assert len(children) > 10  # Multiple group headers and dozens of voice models

        # Check searching filters the list
        dialog._search_var.set("Ava")
        dialog._render_models_list()
        ava_children = dialog._list_inner.winfo_children()
        assert len(ava_children) >= 1  # Ava model row (group header may collapse to a single match)
    finally:
        if dialog.win and dialog.win.winfo_exists():
            dialog.win.destroy()


def test_audio_flow_dialog_speed_and_voice_selection_callbacks() -> None:
    root = _get_or_create_root()
    if not root:
        return
    speed_calls = []
    voice_calls = []
    dialog = AudioFlowSettingsDialog(
        root,
        on_speed_change=speed_calls.append,
        on_voice_change=voice_calls.append,
    )
    try:
        dialog._set_speed(1.5)
        assert speed_calls == [1.5]
        assert float(storage.get_setting("audio_flow_speed", 1.0)) == 1.5

        dialog._select_voice("deepgram/aura-zeus-en")
        assert voice_calls == ["deepgram/aura-zeus-en"]
        assert storage.get_setting("exec_audio_policy_model", "") == "deepgram/aura-zeus-en"
    finally:
        if dialog.win and dialog.win.winfo_exists():
            dialog.win.destroy()


def test_floating_bar_reading_state_zones_and_settings_trigger() -> None:
    bar = FloatingOverlayBar()
    bar.state = "READING"
    bar.width = bar.audio_playback_width
    grip_left = bar.width - bar.GRIP_W

    # Zone hitboxes in READING state (no speed pill — speed is set before generation)
    assert bar._get_zone(50) == "speak"  # Audio flow title zone
    assert bar._get_zone(125) == "audio_pause"  # Pause/resume
    assert bar._get_zone(165) == "audio_stop"   # Stop button
    assert bar._get_zone(200) == "audio_settings"  # Settings button
    assert bar._get_zone(230) == "cancel"  # Dismiss
    assert bar._get_zone(grip_left) == "grip"  # Grip

    # Click triggers callbacks
    pause_toggled = []
    stopped = []
    settings_opened = []

    bar.on_audio_pause_toggle = lambda: pause_toggled.append(True)
    bar.on_audio_stop = lambda: stopped.append(True)
    bar.on_open_settings = lambda: settings_opened.append(True)

    bar._on_press(SimpleNamespace(x=125, y=0))
    assert pause_toggled == [True]

    bar._on_press(SimpleNamespace(x=200, y=0))
    assert settings_opened == [True]

    bar._on_press(SimpleNamespace(x=165, y=0))
    assert stopped == [True]


def test_floating_bar_ready_state_settings_zone() -> None:
    bar = FloatingOverlayBar()
    bar.state = "READY"
    bar.width = bar.ready_actions_width
    content_width = bar.ready_actions_width - bar.GRIP_W
    settings_x = content_width - 10

    assert bar._get_zone(settings_x) == "settings"

    opened = []
    bar.on_open_settings = lambda: opened.append(True)
    bar._on_press(SimpleNamespace(x=settings_x, y=0))
    assert opened == [True]


def test_calculate_anchored_dialog_geometry_positions_above_floating_bar() -> None:
    from voice_flow.audio_flow_dialog import calculate_anchored_dialog_geometry

    # Mock dialog window
    mock_win = MagicMock()
    mock_win.winfo_width.return_value = 420
    mock_win.winfo_height.return_value = 520
    mock_win.winfo_screenwidth.return_value = 1920
    mock_win.winfo_screenheight.return_value = 1080

    # Mock parent floating bar at bottom center: x=836, y=992, w=248, h=28
    # Center x = 836 + 124 = 960
    mock_parent = MagicMock()
    mock_parent.winfo_exists.return_value = True
    mock_parent.winfo_rootx.return_value = 836
    mock_parent.winfo_rooty.return_value = 992
    mock_parent.winfo_width.return_value = 248
    mock_parent.winfo_height.return_value = 28

    w, h, x, y = calculate_anchored_dialog_geometry(mock_win, parent=mock_parent, default_w=420, default_h=520, gap=10)

    # Center of dialog is 960 -> x = 960 - 210 = 750
    assert w == 420
    assert h == 520
    assert x == 750
    # Positioned above parent: y = 992 - 520 - 10 = 462
    assert y == 462


def test_calculate_anchored_dialog_geometry_follows_moved_floating_bar() -> None:
    from voice_flow.audio_flow_dialog import calculate_anchored_dialog_geometry

    mock_win = MagicMock()
    mock_win.winfo_width.return_value = 420
    mock_win.winfo_height.return_value = 520
    mock_win.winfo_screenwidth.return_value = 1920
    mock_win.winfo_screenheight.return_value = 1080

    # Mock parent floating bar dragged to right side: x=1400, y=850, w=248, h=28
    # Center x = 1400 + 124 = 1524
    mock_parent = MagicMock()
    mock_parent.winfo_exists.return_value = True
    mock_parent.winfo_rootx.return_value = 1400
    mock_parent.winfo_rooty.return_value = 850
    mock_parent.winfo_width.return_value = 248
    mock_parent.winfo_height.return_value = 28

    w, h, x, y = calculate_anchored_dialog_geometry(mock_win, parent=mock_parent, default_w=420, default_h=520, gap=10)

    # Center x = 1524 -> x = 1524 - 210 = 1314
    assert x == 1314
    # Positioned directly above: y = 850 - 520 - 10 = 320
    assert y == 320


def test_calculate_anchored_dialog_geometry_with_user_pos() -> None:
    from voice_flow.audio_flow_dialog import calculate_anchored_dialog_geometry

    mock_win = MagicMock()
    mock_win.winfo_width.return_value = 420
    mock_win.winfo_height.return_value = 520
    mock_win.winfo_screenwidth.return_value = 1920
    mock_win.winfo_screenheight.return_value = 1080

    # Overlay with custom user position anchor (center_x=1600, bottom_y=800)
    mock_overlay = MagicMock()
    mock_overlay._user_pos = (1600, 800)
    mock_overlay._drawn_width.return_value = 280
    mock_overlay.height = 26

    w, h, x, y = calculate_anchored_dialog_geometry(mock_win, parent=mock_overlay, default_w=420, default_h=520, gap=10)

    # Center is 1600 -> x = 1600 - 210 = 1390
    assert x == 1390
    # Top of bar is 800 - 26 = 774 -> y = 774 - 520 - 10 = 244
    assert y == 244


def test_calculate_anchored_dialog_geometry_resolves_runtime_controller() -> None:
    from voice_flow.audio_flow_dialog import calculate_anchored_dialog_geometry
    from voice_flow.gui import api_server

    mock_win = MagicMock()
    mock_win.winfo_width.return_value = 420
    mock_win.winfo_height.return_value = 520
    mock_win.winfo_screenwidth.return_value = 1920
    mock_win.winfo_screenheight.return_value = 1080

    mock_overlay = MagicMock()
    mock_overlay._user_pos = (1200, 900)
    mock_overlay._drawn_width.return_value = 280
    mock_overlay.height = 26

    mock_ctrl = MagicMock()
    mock_ctrl.overlay = mock_overlay
    api_server.register_runtime_controller(mock_ctrl)

    # Calling with parent=None automatically finds runtime_controller.overlay
    w, h, x, y = calculate_anchored_dialog_geometry(mock_win, parent=None, default_w=420, default_h=520, gap=10)

    assert x == 1200 - 210  # 990
    assert y == (900 - 26) - 520 - 10  # 344


def test_overlay_vector_gear_icon_drawing() -> None:
    bar = FloatingOverlayBar()
    bar.canvas = MagicMock()
    bar._draw_gear_icon(cx=100, cy=100, r=4.5, color="#241708", bg_color="#FFFFFF")
    # Verify 6 teeth (create_line) and 2 circles (create_oval) are drawn
    assert bar.canvas.create_line.call_count == 6
    assert bar.canvas.create_oval.call_count == 2
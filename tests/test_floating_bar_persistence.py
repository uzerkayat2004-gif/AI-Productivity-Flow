"""Floating bar: persistent position, on-screen clamping, and no spontaneous moves."""

from __future__ import annotations

from unittest.mock import patch

from tests.test_floating_bar import _create_mock_bar
from voice_flow.overlay import FloatingOverlayBar


def test_module_imports_threading() -> None:
    # Regression: a missing import crashed the overlay loop and hid the bar.
    import voice_flow.overlay as overlay_module

    assert hasattr(overlay_module, "threading")


def test_saved_position_is_restored_and_persisted() -> None:
    store: dict = {}
    with patch("voice_flow.overlay.storage") as fake_storage:
        fake_storage.get_setting.side_effect = lambda k, d=None: store.get(k, d)
        fake_storage.save_setting.side_effect = lambda k, v: store.__setitem__(k, v)

        bar = FloatingOverlayBar()
        bar.load_saved_position()
        assert bar._user_pos is None

        bar._user_pos = (640, 300)
        bar._is_dragging = True
        bar._on_release(None)
        assert store["overlay_user_pos"] == [640, 300]

        restarted = FloatingOverlayBar()
        restarted.load_saved_position()
        assert restarted._user_pos == (640, 300)

        restarted.reset_position()
        assert store["overlay_user_pos"] is None


def test_refresh_show_and_resume_keep_position() -> None:
    bar = _create_mock_bar()
    bar._user_pos = (700, 500)
    bar.show()
    bar.restart_and_refresh()
    bar._handle_resume()
    assert bar._user_pos == (700, 500)


def test_bar_is_clamped_on_screen_for_extreme_anchors() -> None:
    bar = _create_mock_bar()
    for anchor in ((-5000, -5000), (99999, 99999), (0, 0), (1920, 1080)):
        bar._user_pos = anchor
        bar._position_window()
        x, y = (int(v) for v in bar.win.geometry_calls[-1].split("+")[1:3])
        assert 0 <= x <= 1920 - bar.width
        assert 0 <= y <= 1080 - bar.height

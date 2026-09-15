from __future__ import annotations

import os
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.hotkeys import HotkeyManager, VK_CONTROL
from voice_flow.storage import storage


def _create_mock_manager() -> tuple[HotkeyManager, MagicMock, MagicMock, MagicMock]:
    on_start = MagicMock()
    on_finish = MagicMock()
    on_cancel = MagicMock()
    with patch("voice_flow.hotkeys.Win32KeyboardHook"), patch("voice_flow.hotkeys.Win32MouseHook"):
        mgr = HotkeyManager(on_start=on_start, on_finish=on_finish, on_cancel=on_cancel)
    return mgr, on_start, on_finish, on_cancel


def test_double_ctrl_long_press_never_starts_dictation() -> None:
    """When double_ctrl is selected, holding Control down must NEVER start dictation."""
    mgr, on_start, on_finish, _ = _create_mock_manager()
    mgr.reload_config({
        "hotkey_trigger": "double_ctrl",
        "dictation_trigger_mode": "hybrid",
        "ctrl_key_dictation_enabled": True,
    })

    assert mgr._hotkey_trigger == "double_ctrl"

    # Press Ctrl once
    with patch("voice_flow.hotkeys._is_ctrl_down", return_value=True), \
         patch("voice_flow.hotkeys._is_alt_down", return_value=False), \
         patch("voice_flow.hotkeys._is_win_down", return_value=False), \
         patch("voice_flow.hotkeys._is_shift_down", return_value=False):
        mgr._on_native_key(VK_CONTROL, is_down=True, is_up=False, extra=0)

    # In double_ctrl mode, no hold timer must be scheduled!
    assert mgr._ctrl_check_timer is None
    assert not mgr._is_recording
    assert not on_start.called

    # Hold key for longer than the 0.35s threshold
    time.sleep(0.4)

    assert not mgr._is_recording
    assert not on_start.called

    # Release Ctrl
    with patch("voice_flow.hotkeys._is_ctrl_down", return_value=False), \
         patch("voice_flow.hotkeys._is_alt_down", return_value=False), \
         patch("voice_flow.hotkeys._is_win_down", return_value=False), \
         patch("voice_flow.hotkeys._is_shift_down", return_value=False):
        mgr._on_native_key(VK_CONTROL, is_down=False, is_up=True, extra=0)

    assert not mgr._is_recording
    assert not on_start.called


def test_double_ctrl_triggers_on_quick_second_press() -> None:
    """When double_ctrl is selected, two presses within 0.35s must start dictation."""
    mgr, on_start, _, _ = _create_mock_manager()
    mgr.reload_config({
        "hotkey_trigger": "double_ctrl",
        "dictation_trigger_mode": "hybrid",
        "ctrl_key_dictation_enabled": True,
    })

    patches = (
        patch("voice_flow.hotkeys._is_alt_down", return_value=False),
        patch("voice_flow.hotkeys._is_win_down", return_value=False),
        patch("voice_flow.hotkeys._is_shift_down", return_value=False),
    )

    with patches[0], patches[1], patches[2]:
        # First press
        mgr._on_native_key(VK_CONTROL, is_down=True, is_up=False, extra=0)
        assert not mgr._is_recording

        # First release
        mgr._on_native_key(VK_CONTROL, is_down=False, is_up=True, extra=0)
        assert not mgr._is_recording

        # Second press within 0.1s
        time.sleep(0.05)
        mgr._on_native_key(VK_CONTROL, is_down=True, is_up=False, extra=0)
        assert mgr._is_recording

    time.sleep(0.05)
    assert on_start.called


def test_single_ctrl_schedules_hold_timer_and_triggers_on_hold() -> None:
    """When single_ctrl is selected, holding Control DOES schedule timer and start recording."""
    mgr, on_start, on_finish, _ = _create_mock_manager()
    mgr.reload_config({
        "hotkey_trigger": "single_ctrl",
        "dictation_trigger_mode": "hybrid",
        "ctrl_key_dictation_enabled": True,
    })

    assert mgr._hotkey_trigger == "single_ctrl"

    patches = (
        patch("voice_flow.hotkeys._is_alt_down", return_value=False),
        patch("voice_flow.hotkeys._is_win_down", return_value=False),
        patch("voice_flow.hotkeys._is_shift_down", return_value=False),
    )

    with patches[0], patches[1], patches[2]:
        mgr._on_native_key(VK_CONTROL, is_down=True, is_up=False, extra=0)

        # In single_ctrl mode, hold timer MUST be scheduled
        assert mgr._ctrl_check_timer is not None

        # Wait for the 0.35s timer to trigger
        time.sleep(0.42)
        assert mgr._is_recording
        assert on_start.called

        # Release ends push-to-talk recording
        mgr._on_native_key(VK_CONTROL, is_down=False, is_up=True, extra=0)
        assert not mgr._is_recording


def test_custom_double_tap_behavior() -> None:
    """When custom hotkey has custom_trigger_type='double_tap', holding does nothing; double-tap dictates."""
    mgr, on_start, on_finish, _ = _create_mock_manager()
    mgr.reload_config({
        "hotkey_trigger": "custom",
        "custom_hotkey": "F8",
        "custom_trigger_type": "double_tap",
    })

    vk_f8 = 0x77  # VK_F8

    patches = (
        patch("voice_flow.hotkeys._is_ctrl_down", return_value=False),
        patch("voice_flow.hotkeys._is_alt_down", return_value=False),
        patch("voice_flow.hotkeys._is_win_down", return_value=False),
        patch("voice_flow.hotkeys._is_shift_down", return_value=False),
        patch("voice_flow.hotkeys._is_key_down", return_value=True),
    )

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        # First press: should NOT record
        mgr._on_native_key(vk_f8, is_down=True, is_up=False, extra=0)
        assert not mgr._is_recording

        # Hold for 0.4s: still should NOT record
        time.sleep(0.4)
        assert not mgr._is_recording

        # Release first press
        mgr._on_native_key(vk_f8, is_down=False, is_up=True, extra=0)
        assert not mgr._is_recording

        # Second press within 0.2s -> Double Tap triggers recording!
        time.sleep(0.05)
        mgr._on_native_key(vk_f8, is_down=True, is_up=False, extra=0)
        assert mgr._is_recording

    time.sleep(0.05)
    assert on_start.called


def test_custom_hold_push_to_talk_behavior() -> None:
    """When custom hotkey has custom_trigger_type='hold', press starts and release finishes."""
    mgr, on_start, on_finish, _ = _create_mock_manager()
    mgr.reload_config({
        "hotkey_trigger": "custom",
        "custom_hotkey": "F8",
        "custom_trigger_type": "hold",
    })

    vk_f8 = 0x77

    patches = (
        patch("voice_flow.hotkeys._is_ctrl_down", return_value=False),
        patch("voice_flow.hotkeys._is_alt_down", return_value=False),
        patch("voice_flow.hotkeys._is_win_down", return_value=False),
        patch("voice_flow.hotkeys._is_shift_down", return_value=False),
        patch("voice_flow.hotkeys._is_key_down", return_value=True),
    )

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        mgr._on_native_key(vk_f8, is_down=True, is_up=False, extra=0)
        assert mgr._is_recording

        time.sleep(0.1)

        mgr._on_native_key(vk_f8, is_down=False, is_up=True, extra=0)
        assert not mgr._is_recording

    time.sleep(0.05)
    assert on_finish.called


def test_storage_hotkey_settings_custom_trigger_type() -> None:
    """Verify storage get_hotkey_settings and save_hotkey_settings round-trip custom_trigger_type."""
    saved = storage.save_hotkey_settings({
        "hotkey_trigger": "custom",
        "custom_hotkey": "Alt+Space",
        "custom_trigger_type": "double_tap",
    })
    assert saved["custom_trigger_type"] == "double_tap"
    assert saved["hotkey_trigger"] == "custom"

    retrieved = storage.get_hotkey_settings()
    assert retrieved["custom_trigger_type"] == "double_tap"

    # Reset back to default
    storage.save_hotkey_settings({
        "hotkey_trigger": "ctrl_win",
        "custom_hotkey": "Alt+Space",
        "custom_trigger_type": "hold",
    })

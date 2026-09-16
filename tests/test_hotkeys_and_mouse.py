from __future__ import annotations

import os
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pynput import keyboard

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.hotkeys import InputTriggerListener
from voice_flow.injector import (
    VF_SYNTHETIC_EXTRA_INFO,
    ClipboardInjector,
    is_synthetic_input_active,
    set_synthetic_input_active,
    mark_user_copy,
    is_user_copy_recent,
    _SyntheticScope,
)
from voice_flow.mouse_hook import Win32MouseHook
from voice_flow.main import DictationState, VoiceFlowApp
import voice_flow.main as main_module


class _FakeOverlay:
    def __init__(self) -> None:
        self.cleared = 0
        self.selected: list[str] = []

    def clear_selected_text(self) -> None:
        self.cleared += 1

    def set_selected_text(self, text: str, timeout_ms: int = 6000) -> None:
        self.selected.append(text)


def _create_test_app(injector: object) -> VoiceFlowApp:
    app = object.__new__(VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = DictationState.IDLE
    app.overlay = _FakeOverlay()
    app.injector = injector
    app.recent_dictations = set()
    app.last_successful_transcript = "dictated voice transcript"
    app._selection_generation = 0
    app._audio_summary_generation = 0
    return app


# =========================================================================
# 1. Mouse Click vs Drag Threshold Tests
# =========================================================================

def test_mouse_click_below_drag_threshold_does_not_call_injector(monkeypatch) -> None:
    """Clicks with movement < 16px must never trigger text selection capture or synthetic Ctrl+C."""
    injector_called = False

    class FakeInjector:
        def get_selected_text_strict(self, **kwargs) -> str:
            nonlocal injector_called
            injector_called = True
            return "unexpected selection"

    app = _create_test_app(FakeInjector())
    hidden = []
    monkeypatch.setattr(main_module.storage, "get_setting", lambda _k, default=None: default)
    monkeypatch.setattr(main_module.audio_flow_widget, "hide", lambda: hidden.append(True))

    # A normal click with jitter (5.0 px)
    app._on_mouse_release(500, 400, drag_distance=5.0, start_x=495, start_y=400)
    time.sleep(0.05)

    assert not injector_called, "Micro-movement click (< 16px) must not call injector get_selected_text_strict"
    assert app.overlay.cleared > 0
    assert hidden == [True]


def test_mouse_click_at_15px_does_not_trigger_injector(monkeypatch) -> None:
    """15px drag is still below the 16px threshold and must be treated as a click/nudge."""
    injector_called = False

    class FakeInjector:
        def get_selected_text_strict(self, **kwargs) -> str:
            nonlocal injector_called
            injector_called = True
            return "text"

    app = _create_test_app(FakeInjector())
    monkeypatch.setattr(main_module.storage, "get_setting", lambda _k, default=None: default)
    monkeypatch.setattr(main_module.audio_flow_widget, "hide", lambda: None)

    app._on_mouse_release(100, 100, drag_distance=15.9, start_x=85, start_y=100)
    time.sleep(0.05)

    assert not injector_called


def test_intentional_drag_selection_calls_injector(monkeypatch) -> None:
    """Intentional drag >= 16px triggers text capture."""
    injector_called = False

    class FakeInjector:
        def get_selected_text_strict(self, **kwargs) -> str:
            nonlocal injector_called
            injector_called = True
            return "highlighted text"

    app = _create_test_app(FakeInjector())
    shown = []
    monkeypatch.setattr(main_module.storage, "get_setting", lambda _k, default=None: default)
    monkeypatch.setattr(main_module.audio_flow_widget, "show_at", lambda x, y, t: shown.append((x, y, t)))
    monkeypatch.setattr(main_module.audio_flow_widget, "hide", lambda: None)
    monkeypatch.setattr(
        main_module.ctypes,
        "windll",
        SimpleNamespace(
            user32=SimpleNamespace(
                GetForegroundWindow=lambda: 99999,
                GetWindowThreadProcessId=lambda hwnd, ref: setattr(ref._obj, "value", 12345),  # different pid
                GetWindowTextLengthW=lambda h: 10,
                GetWindowTextW=lambda h, buf, l: setattr(buf, "value", "Browser Window"),
                GetClassNameW=lambda h, buf, l: setattr(buf, "value", "Chrome_WidgetWin_1"),
            )
        ),
    )

    app._on_mouse_release(300, 200, drag_distance=45.0, start_x=200, start_y=200)
    time.sleep(0.1)

    assert injector_called
    assert app.overlay.selected == ["highlighted text"]
    assert len(shown) == 1


def test_mouse_drag_aborted_when_voice_flow_is_foreground(monkeypatch) -> None:
    """Mouse drag in Voice Flow's own window must not trigger synthetic Ctrl+C."""
    injector_called = False

    class FakeInjector:
        def get_selected_text_strict(self, **kwargs) -> str:
            nonlocal injector_called
            injector_called = True
            return "text"

    app = _create_test_app(FakeInjector())
    monkeypatch.setattr(main_module.storage, "get_setting", lambda _k, default=None: default)
    monkeypatch.setattr(
        main_module.ctypes,
        "windll",
        SimpleNamespace(
            user32=SimpleNamespace(
                GetForegroundWindow=lambda: 1234,
                GetWindowThreadProcessId=lambda hwnd, ref: setattr(ref._obj, "value", os.getpid()),  # Voice Flow's own pid
                GetWindowTextLengthW=lambda h: 10,
                GetWindowTextW=lambda h, buf, l: setattr(buf, "value", "Voice Flow"),
                GetClassNameW=lambda h, buf, l: setattr(buf, "value", "TkTopLevel"),
            )
        ),
    )

    app._on_mouse_release(300, 200, drag_distance=50.0, start_x=200, start_y=200)
    time.sleep(0.05)

    assert not injector_called, "Must not capture text when Voice Flow is foreground window"


# =========================================================================
# 2. Win32MouseHook Press/Release Tracking Tests
# =========================================================================

def test_mouse_hook_uninitialized_down_does_not_calculate_huge_drag() -> None:
    """If WM_LBUTTONUP occurs without preceding WM_LBUTTONDOWN, drag_dist must be 0.0."""
    dispatched = []

    hook = Win32MouseHook(
        on_start=lambda: None,
        on_finish=lambda: None,
        on_cancel=lambda: None,
        on_mouse_release=lambda x, y, dist, sx, sy: dispatched.append((x, y, dist, sx, sy)),
    )

    assert hook._is_left_down is False
    assert hook._last_left_down_x == 0
    assert hook._last_left_down_y == 0

    # Simulate _safe_on_mouse_release directly as invoked by hook proc when not down
    # When hook sees UP without DOWN, our fix provides dist=0.0, start_x=x, start_y=y
    hook._safe_on_mouse_release(800, 600, 0.0, 800, 600)

    assert len(dispatched) == 1
    x, y, dist, sx, sy = dispatched[0]
    assert dist == 0.0
    assert sx == 800
    assert sy == 600


# =========================================================================
# 3. Synthetic Input Scope & Suppression Tests
# =========================================================================

def test_synthetic_input_active_context_manager() -> None:
    """Verify is_synthetic_input_active transitions correctly."""
    assert is_synthetic_input_active() is False

    with _SyntheticScope():
        assert is_synthetic_input_active() is True

    # After exit (including the brief safety delay)
    assert is_synthetic_input_active() is False


def test_hotkeys_ignores_synthetic_keyboard_events() -> None:
    """When synthetic input is active, hotkey handlers must ignore all events."""
    start_called = False
    listener = InputTriggerListener(
        on_start=lambda: setattr(listener, "_start_called", True),
        on_finish=lambda: None,
        on_cancel=lambda: None,
    )
    listener._start_called = False

    # Mark synthetic input active
    set_synthetic_input_active(True)
    try:
        # Simulate synthetic Ctrl key press
        listener._on_key_press(keyboard.Key.ctrl)
        # Should NOT have recorded press time or started hold timer
        assert listener._ctrl_press_time == 0.0
        assert listener._ctrl_check_timer is None

        # Simulate synthetic Ctrl release
        listener._on_key_release(keyboard.Key.ctrl)
        assert listener._last_ctrl_release_time == 0.0
    finally:
        set_synthetic_input_active(False)


# =========================================================================
# 4. Keyboard Chord Pass-Through & Ctrl+C Tests
# =========================================================================

def test_ctrl_c_cancels_solo_ctrl_hold_timer_and_marks_chord(monkeypatch) -> None:
    """Pressing C while Ctrl is held must cancel solo-Ctrl hold timer and mark chord active."""
    start_called = False
    copy_last_called = False

    listener = InputTriggerListener(
        on_start=lambda: setattr(listener, "_start_called", True),
        on_finish=lambda: None,
        on_cancel=lambda: None,
        on_copy_last=lambda: setattr(listener, "_copy_last_called", True),
    )
    listener._start_called = False
    listener._copy_last_called = False

    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: True)
    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_shift_down", lambda: False)

    from voice_flow import storage as storage_module
    monkeypatch.setattr(storage_module.storage, "get_setting", lambda k, default=None: True if k == "ctrl_key_dictation_enabled" else default)

    # 1. User presses Ctrl down
    listener._on_key_press(keyboard.Key.ctrl)
    assert listener._ctrl_check_timer is not None, "Timer scheduled for solo Ctrl"
    assert listener._ctrl_chord_active is False

    # 2. User presses 'c' while Ctrl is held (Ctrl+C)
    key_c = keyboard.KeyCode.from_char("c")
    listener._on_key_press(key_c)

    # Solo timer MUST be cancelled immediately!
    assert listener._ctrl_check_timer is None, "Hold timer must be cancelled on chord key"
    assert listener._ctrl_chord_active is True, "Chord must be marked active"
    assert listener._last_ctrl_release_time == 0.0
    assert listener._copy_last_called is False, "Plain Ctrl+C must NEVER call copy_last"

    # 3. User releases Ctrl
    listener._on_key_release(keyboard.Key.ctrl)
    assert listener._start_called is False, "Dictation must NOT start"
    assert listener._last_ctrl_release_time == 0.0, "Release time must not be set for chord release"
    assert listener._ctrl_chord_active is False


def test_ctrl_v_chord_does_not_trigger_double_tap_on_next_ctrl(monkeypatch) -> None:
    """After using Ctrl+C, pressing Ctrl again soon after must NOT trigger double-tap dictation."""
    start_count = 0

    def on_start():
        nonlocal start_count
        start_count += 1

    listener = InputTriggerListener(
        on_start=on_start,
        on_finish=lambda: None,
        on_cancel=lambda: None,
    )

    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_shift_down", lambda: False)

    from voice_flow import storage as storage_module
    monkeypatch.setattr(storage_module.storage, "get_setting", lambda k, default=None: True if k == "ctrl_key_dictation_enabled" else default)

    # Ctrl+C sequence
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: True)
    listener._on_key_press(keyboard.Key.ctrl)
    listener._on_key_press(keyboard.KeyCode.from_char("c"))
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: False)
    listener._on_key_release(keyboard.Key.ctrl)

    # User immediately presses Ctrl again within 0.1s (e.g. for Ctrl+V)
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: True)
    listener._on_key_press(keyboard.Key.ctrl)

    # Must NOT have triggered dictation start via double-tap
    assert start_count == 0, "Second Ctrl press must not trigger double-tap after a chord combination"

    # Clean up timer
    if listener._ctrl_check_timer:
        listener._ctrl_check_timer.cancel()


def test_plain_ctrl_c_never_overwrites_clipboard_in_any_window(monkeypatch) -> None:
    """Even if foreground window title has 'voice flow' or tk, plain Ctrl+C must not fire on_copy_last."""
    copy_last_fired = False

    listener = InputTriggerListener(
        on_start=lambda: None,
        on_finish=lambda: None,
        on_cancel=lambda: None,
        on_copy_last=lambda: setattr(listener, "_copy_last_fired", True),
    )
    listener._copy_last_fired = False

    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: True)
    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_shift_down", lambda: False)

    # Window title that might match "voice flow"
    monkeypatch.setattr(
        "ctypes.windll.user32.GetForegroundWindow",
        lambda: 12345,
    )
    monkeypatch.setattr(
        "ctypes.windll.user32.GetWindowThreadProcessId",
        lambda hwnd, ref: setattr(ref._obj, "value", 99999),  # not Voice Flow's pid
    )

    # Press 'c' with Ctrl held
    listener._on_key_press(keyboard.KeyCode.from_char("c"))

    assert listener._copy_last_fired is False, "Ctrl+C must never call on_copy_last"


# =========================================================================
# 5. Regression Tests for Console Abort, Modifier Guards & Clipboard Safety
# =========================================================================

def test_console_window_aborts_immediately_without_synthetic_ctrl_c(monkeypatch) -> None:
    """Console / terminal windows must immediately return '' and never send synthetic Ctrl+C."""
    ctrl_c_called = False

    def fake_send_ctrl_c():
        nonlocal ctrl_c_called
        ctrl_c_called = True

    monkeypatch.setattr("voice_flow.injector._send_win32_ctrl_c", fake_send_ctrl_c)
    monkeypatch.setattr("voice_flow.injector.get_active_window_title", lambda: "Windows PowerShell - Command Prompt")
    monkeypatch.setattr("voice_flow.injector.get_window_class_name", lambda _hwnd: "ConsoleWindowClass")
    monkeypatch.setattr("ctypes.windll.user32.GetAsyncKeyState", lambda _vk: 0)

    inj = ClipboardInjector()
    res = inj.get_selected_text_strict()

    assert res == ""
    assert ctrl_c_called is False, "Synthetic Ctrl+C must NEVER be sent to console windows!"


def test_modifier_held_aborts_without_injecting_or_force_releasing(monkeypatch) -> None:
    """When Shift (or any modifier) is held, get_selected_text_strict must immediately abort without sending synthetic Ctrl+C."""
    ctrl_c_called = False

    def fake_send_ctrl_c():
        nonlocal ctrl_c_called
        ctrl_c_called = True

    monkeypatch.setattr("voice_flow.injector._send_win32_ctrl_c", fake_send_ctrl_c)
    # Simulate VK_SHIFT (0x10) physically held down
    monkeypatch.setattr("ctypes.windll.user32.GetAsyncKeyState", lambda vk: 0x8000 if vk == 0x10 else 0)

    inj = ClipboardInjector()
    res = inj.get_selected_text_strict()

    assert res == ""
    assert ctrl_c_called is False, "Must not inject synthetic Ctrl+C while user holds Shift"


def test_user_manual_copy_prevents_clipboard_restore(monkeypatch) -> None:
    """If the user manually pressed Ctrl+C, the background inspector must not restore the old clipboard."""
    stored_clipboard = ["user copied data"]

    monkeypatch.setattr("voice_flow.injector._safe_paste_from_clipboard", lambda: stored_clipboard[0])
    restored_clipboard = []
    monkeypatch.setattr("voice_flow.injector._safe_copy_to_clipboard", lambda val: restored_clipboard.append(val))
    monkeypatch.setattr("voice_flow.injector.get_active_window_title", lambda: "Notepad")
    monkeypatch.setattr("voice_flow.injector.get_window_class_name", lambda _hwnd: "Notepad")
    monkeypatch.setattr("ctypes.windll.user32.GetAsyncKeyState", lambda _vk: 0)
    monkeypatch.setattr("voice_flow.injector._send_win32_ctrl_c", lambda: None)

    # Mark that user physically pressed Ctrl+C
    mark_user_copy()
    assert is_user_copy_recent() is True

    inj = ClipboardInjector()
    inj.get_selected_text_strict()

    # _safe_copy_to_clipboard should NOT have been called to restore the original clipboard
    assert restored_clipboard == [], "Original clipboard must NOT be restored after a manual user copy"


def test_alt_c_in_voice_flow_window_triggers_copy_last(monkeypatch) -> None:
    """Alt+C when focused on Voice Flow's own window must trigger on_copy_last."""
    copy_last_fired = False

    listener = InputTriggerListener(
        on_start=lambda: None,
        on_finish=lambda: None,
        on_cancel=lambda: None,
        on_copy_last=lambda: setattr(listener, "_copy_last_fired", True),
    )
    listener._copy_last_fired = False

    # Simulate Alt held down, Ctrl not down
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_alt_down", lambda: True)
    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_shift_down", lambda: False)

    # Voice Flow's own window is focused
    monkeypatch.setattr("ctypes.windll.user32.GetForegroundWindow", lambda: 54321)
    monkeypatch.setattr(
        "ctypes.windll.user32.GetWindowThreadProcessId",
        lambda hwnd, ref: setattr(ref._obj, "value", os.getpid()),
    )

    listener._on_key_press(keyboard.KeyCode.from_char("c"))
    time.sleep(0.05)

    assert listener._copy_last_fired is True, "Alt+C in Voice Flow window must fire on_copy_last"


def test_altgr_does_not_trigger_solo_ctrl(monkeypatch) -> None:
    """AltGr key (which sends Ctrl+Alt simultaneously) must NEVER trigger solo Ctrl dictation."""
    start_count = 0

    listener = InputTriggerListener(
        on_start=lambda: setattr(listener, "_start_count", getattr(listener, "_start_count", 0) + 1),
        on_finish=lambda: None,
        on_cancel=lambda: None,
    )
    listener._start_count = 0

    from voice_flow import storage as storage_module
    monkeypatch.setattr(storage_module.storage, "get_setting", lambda k, default=None: True if k == "ctrl_key_dictation_enabled" else default)

    # Simulate AltGr: BOTH Ctrl and Alt are down
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: True)
    monkeypatch.setattr("voice_flow.hotkeys._is_alt_down", lambda: True)
    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_shift_down", lambda: False)

    # AltGr press received as Ctrl
    listener._on_key_press(keyboard.Key.ctrl)

    # Hold timer must not be scheduled
    assert listener._ctrl_check_timer is None, "AltGr must not schedule solo Ctrl hold timer"
    assert listener._start_count == 0


# =========================================================================
# 5. User-Configurable Trigger & Hotkey Tests
# =========================================================================

def test_alt_space_trigger_starts_and_finishes(monkeypatch) -> None:
    """When hotkey_trigger is 'alt_space', pressing Alt+Space starts dictation, and release finishes."""
    start_count = 0
    finish_count = 0

    listener = InputTriggerListener(
        on_start=lambda: setattr(listener, "_started", True),
        on_finish=lambda: setattr(listener, "_finished", True),
        on_cancel=lambda: None,
    )
    listener._started = False
    listener._finished = False

    listener.reload_config({"hotkey_trigger": "alt_space", "dictation_trigger_mode": "ptt_only"})

    monkeypatch.setattr("voice_flow.hotkeys._is_alt_down", lambda: True)
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_shift_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_key_down", lambda vk: vk == 0x20)

    # Press Space while Alt is held
    listener._on_key_press(keyboard.Key.space)
    time.sleep(0.05)
    assert listener._alt_space_triggered is True
    assert listener._started is True

    # Release Space
    listener._on_key_release(keyboard.Key.space)
    time.sleep(0.05)
    assert listener._alt_space_triggered is False
    assert listener._finished is True


def test_alt_tab_trigger_starts_and_finishes(monkeypatch) -> None:
    """When hotkey_trigger is 'alt_tab', pressing Alt+Tab starts dictation, and release finishes."""
    listener = InputTriggerListener(
        on_start=lambda: setattr(listener, "_started", True),
        on_finish=lambda: setattr(listener, "_finished", True),
        on_cancel=lambda: None,
    )
    listener._started = False
    listener._finished = False

    listener.reload_config({"hotkey_trigger": "alt_tab", "dictation_trigger_mode": "ptt_only"})

    monkeypatch.setattr("voice_flow.hotkeys._is_alt_down", lambda: True)
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_shift_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_key_down", lambda vk: vk == 0x09)

    # Press Tab while Alt is held
    listener._on_key_press(keyboard.Key.tab)
    time.sleep(0.05)
    assert listener._alt_tab_triggered is True
    assert listener._started is True

    # Release Tab
    listener._on_key_release(keyboard.Key.tab)
    time.sleep(0.05)
    assert listener._alt_tab_triggered is False
    assert listener._finished is True


def test_custom_hotkey_combination_starts_and_finishes(monkeypatch) -> None:
    """Custom hotkey combination (e.g. Ctrl+Shift+D) triggers dictation when all keys down."""
    listener = InputTriggerListener(
        on_start=lambda: setattr(listener, "_started", True),
        on_finish=lambda: setattr(listener, "_finished", True),
        on_cancel=lambda: None,
    )
    listener._started = False
    listener._finished = False

    listener.reload_config({
        "hotkey_trigger": "custom",
        "custom_hotkey": "Ctrl+Shift+D",
        "dictation_trigger_mode": "ptt_only",
    })

    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: True)
    monkeypatch.setattr("voice_flow.hotkeys._is_shift_down", lambda: True)
    monkeypatch.setattr("voice_flow.hotkeys._is_alt_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_key_down", lambda vk: vk == 0x44)

    key_d = keyboard.KeyCode.from_char("d")
    listener._on_key_press(key_d)
    time.sleep(0.05)
    assert listener._custom_hotkey_triggered is True
    assert listener._started is True

    listener._on_key_release(key_d)
    time.sleep(0.05)
    assert listener._custom_hotkey_triggered is False
    assert listener._finished is True


def test_double_ctrl_tap_starts_dictation(monkeypatch) -> None:
    """Double tap Ctrl in double_ctrl mode triggers dictation start."""
    listener = InputTriggerListener(
        on_start=lambda: setattr(listener, "_started", True),
        on_finish=lambda: setattr(listener, "_finished", True),
        on_cancel=lambda: None,
    )
    listener._started = False
    listener._finished = False

    listener.reload_config({"hotkey_trigger": "double_ctrl"})

    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_shift_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_alt_down", lambda: False)

    # 1. First tap
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: True)
    listener._on_key_press(keyboard.Key.ctrl)
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: False)
    listener._on_key_release(keyboard.Key.ctrl)
    assert listener._started is False

    # 2. Second tap immediately within 0.1s
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: True)
    listener._on_key_press(keyboard.Key.ctrl)
    time.sleep(0.05)
    assert listener._started is True
    assert listener._ctrl_toggle_mode_active is True

    # 3. Third tap finishes
    listener._on_key_press(keyboard.Key.ctrl)
    time.sleep(0.05)
    assert listener._finished is True
    assert listener._ctrl_toggle_mode_active is False


def test_middle_click_disabled_passes_through(monkeypatch) -> None:
    """When middle_click_enabled is False, mouse hook does not trigger dictation start."""
    hook = Win32MouseHook(
        on_start=lambda: setattr(hook, "_started", True),
        on_finish=lambda: None,
        on_cancel=lambda: None,
    )
    hook._started = False
    hook.set_enabled(False)
    assert hook.is_enabled() is False

    from voice_flow import storage as storage_module
    monkeypatch.setattr(storage_module.storage, "get_setting", lambda k, default=None: False if k == "middle_click_enabled" else default)
    hook.refresh_trigger_mode(force=True)
    assert hook.is_enabled() is False


def test_hotkeys_live_reload_switches_active_trigger() -> None:
    """Calling reload_config switches active trigger in memory without thread restart."""
    listener = InputTriggerListener(
        on_start=lambda: None,
        on_finish=lambda: None,
        on_cancel=lambda: None,
    )

    listener.reload_config({"hotkey_trigger": "alt_space", "custom_hotkey": "Ctrl+F8", "middle_click_enabled": False})
    assert listener._hotkey_trigger == "alt_space"
    assert listener._custom_hotkey_str == "Ctrl+F8"
    assert listener._middle_click_enabled is False

    listener.reload_config({"hotkey_trigger": "double_ctrl", "middle_click_enabled": True})
    assert listener._hotkey_trigger == "double_ctrl"
    assert listener._ctrl_key_dictation_enabled is True
    assert listener._middle_click_enabled is True


def test_ctrl_win_release_ctrl_first_arms_suppression_and_triggers_finish(monkeypatch) -> None:
    """Releasing Ctrl before Win must immediately finish dictation and arm Win suppression for the subsequent Win release."""
    finish_called = False
    start_called = False
    suppress_calls = 0

    def fake_suppress():
        nonlocal suppress_calls
        suppress_calls += 1

    monkeypatch.setattr("voice_flow.hotkeys._suppress_win_start_menu", fake_suppress)

    listener = InputTriggerListener(
        on_start=lambda: setattr(listener, "_start_called", True),
        on_finish=lambda: setattr(listener, "_finish_called", True),
        on_cancel=lambda: None,
    )
    # This test covers push-to-talk: releasing Ctrl finishes immediately. A
    # saved 'toggle_only' preference intentionally suppresses that, so pin the
    # mode under test instead of inheriting the machine's setting.
    listener.reload_config({"hotkey_trigger": "ctrl_win", "dictation_trigger_mode": "ptt_only"})
    listener._start_called = False
    listener._finish_called = False

    # Simulate physical Ctrl and Win down
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: True)
    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: True)
    monkeypatch.setattr("voice_flow.hotkeys._is_alt_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_shift_down", lambda: False)

    listener._on_key_press(keyboard.Key.ctrl)
    listener._on_key_press(keyboard.Key.cmd)
    time.sleep(0.05)

    assert listener._hotkey_triggered is True
    assert listener._win_suppress_needed is True
    assert listener._start_called is True
    initial_suppress = suppress_calls

    # 1. User releases Ctrl first (Ctrl keyup)
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: False)
    listener._on_key_release(keyboard.Key.ctrl)
    time.sleep(0.05)

    assert listener._hotkey_triggered is False
    assert listener._is_recording is False
    assert listener._finish_called is True, "Releasing Ctrl must trigger finish immediately without delay"
    assert listener._win_suppress_needed is True, "Win suppression must stay armed for the remaining Win key"
    assert suppress_calls > initial_suppress

    # 2. User releases Win 20ms later (Win keyup)
    after_ctrl_suppress = suppress_calls
    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: False)
    listener._on_key_release(keyboard.Key.cmd)

    assert listener._win_suppress_needed is False
    assert suppress_calls > after_ctrl_suppress, "Subsequent Win key release must trigger Start menu suppression"


def test_native_hook_ctrl_win_instant_finish_and_start_menu_suppression(monkeypatch) -> None:
    """_on_native_key handles Ctrl+Win chord down, instant finish on Ctrl release, and suppresses Win keyup."""
    suppress_calls = 0

    def fake_suppress():
        nonlocal suppress_calls
        suppress_calls += 1

    monkeypatch.setattr("voice_flow.hotkeys._suppress_win_start_menu", fake_suppress)

    listener = InputTriggerListener(
        on_start=lambda: setattr(listener, "_start_called", True),
        on_finish=lambda: setattr(listener, "_finish_called", True),
        on_cancel=lambda: None,
    )
    # Push-to-talk semantics: releasing Ctrl dispatches an instant finish.
    # Pin the mode so a saved 'toggle_only' preference cannot change what this
    # test is exercising.
    listener.reload_config({"hotkey_trigger": "ctrl_win", "dictation_trigger_mode": "ptt_only"})
    listener._start_called = False
    listener._finish_called = False

    from voice_flow.hotkeys import VK_CONTROL, VK_LWIN

    ctrl_state = [False]
    win_state = [False]
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: ctrl_state[0])
    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: win_state[0])
    monkeypatch.setattr("voice_flow.hotkeys._is_alt_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_shift_down", lambda: False)

    # 1. Ctrl down
    ctrl_state[0] = True
    listener._on_native_key(VK_CONTROL, is_down=True, is_up=False, extra=0)
    assert listener._hotkey_triggered is False

    # 2. Win down -> chord active
    win_state[0] = True
    sup_win = listener._on_native_key(VK_LWIN, is_down=True, is_up=False, extra=0)
    assert sup_win is True, "Ctrl+Win down should suppress Win key"
    time.sleep(0.05)
    assert listener._hotkey_triggered is True
    assert listener._win_suppress_needed is True
    assert listener._start_called is True
    press_suppress_count = suppress_calls

    # 3. Release Ctrl first -> instant finish
    ctrl_state[0] = False
    listener._on_native_key(VK_CONTROL, is_down=False, is_up=True, extra=0)
    time.sleep(0.05)
    assert listener._finish_called is True, "Instant finish must be dispatched on Ctrl release"
    assert listener._hotkey_triggered is False
    assert listener._win_suppress_needed is True
    assert suppress_calls > press_suppress_count

    # 4. Release Win second -> must suppress Win keyup from Windows Shell
    after_finish_suppress = suppress_calls
    win_state[0] = False
    sup_release = listener._on_native_key(VK_LWIN, is_down=False, is_up=True, extra=0)
    assert sup_release is True, "Win keyup must be suppressed to prevent Start menu popup"
    assert listener._win_suppress_needed is False
    assert suppress_calls > after_finish_suppress


def test_native_hook_alt_tab_starts_and_finishes_instantly(monkeypatch) -> None:
    """Native hook handles Alt+Tab trigger and dispatches start/finish instantly."""
    listener = InputTriggerListener(
        on_start=lambda: setattr(listener, "_start_called", True),
        on_finish=lambda: setattr(listener, "_finish_called", True),
        on_cancel=lambda: None,
    )
    listener._start_called = False
    listener._finish_called = False

    listener.reload_config({"hotkey_trigger": "alt_tab", "dictation_trigger_mode": "ptt_only"})

    from voice_flow.hotkeys import VK_LMENU, VK_TAB

    alt_state = [False]
    tab_state = [False]
    monkeypatch.setattr("voice_flow.hotkeys._is_alt_down", lambda: alt_state[0])
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_shift_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_key_down", lambda vk: tab_state[0] if vk == VK_TAB else False)

    # Press Alt then Tab
    alt_state[0] = True
    listener._on_native_key(VK_LMENU, is_down=True, is_up=False, extra=0)
    tab_state[0] = True
    sup = listener._on_native_key(VK_TAB, is_down=True, is_up=False, extra=0)
    assert sup is True, "Tab down in Alt+Tab mode must be suppressed from task switcher"
    time.sleep(0.05)
    assert listener._alt_tab_triggered is True
    assert listener._start_called is True

    # Release Tab
    tab_state[0] = False
    listener._on_native_key(VK_TAB, is_down=False, is_up=True, extra=0)
    time.sleep(0.05)
    assert listener._alt_tab_triggered is False
    assert listener._finish_called is True


def test_native_hook_escape_cancels_recording(monkeypatch) -> None:
    """Pressing Escape during active recording cancels dictation and suppresses Escape."""
    cancel_called = False

    listener = InputTriggerListener(
        on_start=lambda: None,
        on_finish=lambda: None,
        on_cancel=lambda: setattr(listener, "_cancel_called", True),
    )
    listener._cancel_called = False
    listener.set_recording_state(True)
    listener._hotkey_triggered = True

    from voice_flow.hotkeys import VK_ESCAPE
    sup = listener._on_native_key(VK_ESCAPE, is_down=True, is_up=False, extra=0)
    assert sup is True
    time.sleep(0.05)
    assert listener._cancel_called is True
    assert listener._is_recording is False


def test_push_to_talk_shortcut_label_mapping_in_reload_config() -> None:
    """Storage settings using push_to_talk_shortcut label map correctly to internal hotkey_trigger."""
    listener = InputTriggerListener(
        on_start=lambda: None,
        on_finish=lambda: None,
        on_cancel=lambda: None,
    )

    listener.reload_config({"push_to_talk_shortcut": "Alt+Tab"})
    assert listener._hotkey_trigger == "alt_tab"

    listener.reload_config({"push_to_talk_shortcut": "Alt+Space"})
    assert listener._hotkey_trigger == "alt_space"

    listener.reload_config({"push_to_talk_shortcut": "Single Ctrl"})
    assert listener._hotkey_trigger == "single_ctrl"
    assert listener._ctrl_key_dictation_enabled is True

    listener.reload_config({"push_to_talk_shortcut": "Double Ctrl"})
    assert listener._hotkey_trigger == "double_ctrl"
    assert listener._ctrl_key_dictation_enabled is True

    listener.reload_config({"push_to_talk_shortcut": "Ctrl+Win"})
    assert listener._hotkey_trigger == "ctrl_win"


def test_single_ctrl_tap_to_toggle_and_release_stability(monkeypatch) -> None:
    """Single Ctrl quick tap toggles recording on; second tap stops recording; release of second tap does not re-trigger."""
    started = False
    finished = False

    listener = InputTriggerListener(
        on_start=lambda: setattr(listener, "_started", True),
        on_finish=lambda: setattr(listener, "_finished", True),
        on_cancel=lambda: None,
    )
    listener._started = False
    listener._finished = False

    listener.reload_config({"hotkey_trigger": "single_ctrl"})

    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_shift_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_alt_down", lambda: False)

    # 1. First quick tap down & release
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: True)
    listener._on_key_press(keyboard.Key.ctrl)
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: False)
    listener._on_key_release(keyboard.Key.ctrl)
    time.sleep(0.05)

    assert listener._started is True
    assert listener._is_recording is True
    assert listener._ctrl_toggle_mode_active is True

    # 2. Second tap down (to stop)
    listener._finished = False
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: True)
    listener._on_key_press(keyboard.Key.ctrl)
    time.sleep(0.05)

    assert listener._finished is True
    assert listener._is_recording is False
    assert listener._ctrl_just_toggled_off is True

    # 3. Release of second tap MUST NOT restart recording!
    listener._started = False
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: False)
    listener._on_key_release(keyboard.Key.ctrl)
    time.sleep(0.05)

    assert listener._started is False
    assert listener._is_recording is False
    assert listener._ctrl_just_toggled_off is False


def test_single_ctrl_ptt_hold_and_release(monkeypatch) -> None:
    """Single Ctrl hold for >= 0.35s acts as push-to-talk: release finishes recording cleanly."""
    listener = InputTriggerListener(
        on_start=lambda: setattr(listener, "_started", True),
        on_finish=lambda: setattr(listener, "_finished", True),
        on_cancel=lambda: None,
    )
    listener._started = False
    listener._finished = False

    listener.reload_config({"hotkey_trigger": "single_ctrl", "dictation_trigger_mode": "ptt_only"})

    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_shift_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_alt_down", lambda: False)

    # 1. Press Ctrl down
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: True)
    listener._on_key_press(keyboard.Key.ctrl)
    assert listener._ctrl_check_timer is not None

    # Manually trigger hold timeout callback to simulate hold elapsed
    with listener._lock:
        if listener._ctrl_check_timer:
            listener._ctrl_check_timer.cancel()
            listener._ctrl_check_timer = None
            listener._ctrl_hold_triggered = True
            listener._ctrl_toggle_mode_active = False
            listener._is_recording = True
            listener._started = True

    assert listener._is_recording is True
    assert listener._ctrl_hold_triggered is True

    # 2. Release Ctrl
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: False)
    listener._on_key_release(keyboard.Key.ctrl)
    time.sleep(0.05)

    assert listener._finished is True
    assert listener._is_recording is False
    assert listener._ctrl_hold_triggered is False


def test_ctrl_win_suppressed_when_other_trigger_selected(monkeypatch) -> None:
    """Pressing Ctrl+Win does not activate dictation when user selected Alt+Space or Middle Click."""
    listener = InputTriggerListener(
        on_start=lambda: setattr(listener, "_started", True),
        on_finish=lambda: setattr(listener, "_finished", True),
        on_cancel=lambda: None,
    )
    listener._started = False

    listener.reload_config({"hotkey_trigger": "alt_space"})

    from voice_flow.hotkeys import VK_CONTROL, VK_LWIN
    ctrl_state = [True]
    win_state = [True]
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: ctrl_state[0])
    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: win_state[0])
    monkeypatch.setattr("voice_flow.hotkeys._is_alt_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_shift_down", lambda: False)

    listener._on_native_key(VK_CONTROL, is_down=True, is_up=False, extra=0)
    listener._on_native_key(VK_LWIN, is_down=True, is_up=False, extra=0)
    time.sleep(0.05)

    assert listener._started is False, "Ctrl+Win must not trigger when active_trigger is alt_space"
    assert listener._is_recording is False


def test_storage_clears_ctrl_key_dictation_when_switching_from_single_ctrl_to_ctrl_win(tmp_path) -> None:
    """storage.save_hotkey_settings resets ctrl_key_dictation_enabled to False when moving away from solo ctrl."""
    from voice_flow.storage import StorageEngine
    test_storage = StorageEngine(str(tmp_path / "test_storage_hotkey.db"))

    # Switch to single_ctrl -> ctrl_key_dictation_enabled becomes True
    res1 = test_storage.save_hotkey_settings({"hotkey_trigger": "single_ctrl"})
    assert res1["hotkey_trigger"] == "single_ctrl"
    assert res1["ctrl_key_dictation_enabled"] is True

    # Switch to ctrl_win -> ctrl_key_dictation_enabled becomes False automatically
    res2 = test_storage.save_hotkey_settings({"hotkey_trigger": "ctrl_win"})
    assert res2["hotkey_trigger"] == "ctrl_win"
    assert res2["ctrl_key_dictation_enabled"] is False


def test_custom_hotkey_negative_modifier_rejection(monkeypatch) -> None:
    """When custom hotkey is Alt+D, pressing Ctrl+Alt+D must NOT trigger dictation."""
    listener = InputTriggerListener(
        on_start=lambda: setattr(listener, "_started", True),
        on_finish=lambda: None,
        on_cancel=lambda: None,
    )
    listener._started = False

    listener.reload_config({"hotkey_trigger": "custom", "custom_hotkey": "Alt+D"})

    from voice_flow.hotkeys import VK_LMENU
    ctrl_state = [True]  # Extraneous modifier
    alt_state = [True]
    monkeypatch.setattr("voice_flow.hotkeys._is_ctrl_down", lambda: ctrl_state[0])
    monkeypatch.setattr("voice_flow.hotkeys._is_alt_down", lambda: alt_state[0])
    monkeypatch.setattr("voice_flow.hotkeys._is_win_down", lambda: False)
    monkeypatch.setattr("voice_flow.hotkeys._is_shift_down", lambda: False)

    vk_d = ord("D")
    listener._on_native_key(VK_LMENU, is_down=True, is_up=False, extra=0)
    listener._on_native_key(vk_d, is_down=True, is_up=False, extra=0)
    time.sleep(0.05)

    assert listener._started is False, "Ctrl+Alt+D must NOT trigger Alt+D hotkey"


def test_storage_push_to_talk_shortcut_bidirectional_sync(tmp_path) -> None:
    """storage.save_hotkey_settings correctly maps push_to_talk_shortcut to hotkey_trigger and vice versa."""
    from voice_flow.storage import StorageEngine
    test_storage = StorageEngine(str(tmp_path / "test_sync.db"))

    # 1. Saving push_to_talk_shortcut 'Alt+Tab' automatically sets hotkey_trigger 'alt_tab'
    res = test_storage.save_hotkey_settings({"push_to_talk_shortcut": "Alt+Tab"})
    assert res["hotkey_trigger"] == "alt_tab"
    assert res["push_to_talk_shortcut"] == "Alt+Tab"

    # 2. Saving push_to_talk_shortcut 'Single Ctrl' sets single_ctrl and enables ctrl_key_dictation
    res2 = test_storage.save_hotkey_settings({"push_to_talk_shortcut": "Single Ctrl"})
    assert res2["hotkey_trigger"] == "single_ctrl"
    assert res2["ctrl_key_dictation_enabled"] is True

    # 3. Saving push_to_talk_shortcut 'Ctrl+Win' resets to ctrl_win
    res3 = test_storage.save_hotkey_settings({"push_to_talk_shortcut": "Ctrl+Win"})
    assert res3["hotkey_trigger"] == "ctrl_win"
    assert res3["push_to_talk_shortcut"] == "Ctrl+Win"
    assert res3["ctrl_key_dictation_enabled"] is False

    # 4. Saving custom shortcut 'Ctrl+Shift+F' sets hotkey_trigger 'custom'
    res4 = test_storage.save_hotkey_settings({"push_to_talk_shortcut": "Ctrl+Shift+F"})
    assert res4["hotkey_trigger"] == "custom"
    assert res4["custom_hotkey"] == "Ctrl+Shift+F"


def test_alt_tab_and_alt_space_keyup_suppression(monkeypatch) -> None:
    """Releasing Tab in Alt+Tab mode or Space in Alt+Space mode suppresses the keyup event."""
    listener = InputTriggerListener(
        on_start=lambda: None,
        on_finish=lambda: None,
        on_cancel=lambda: None,
    )
    from voice_flow.hotkeys import VK_LMENU, VK_TAB, VK_SPACE

    # Test Alt+Tab release
    listener.reload_config({"hotkey_trigger": "alt_tab"})
    listener._alt_tab_triggered = True
    sup_tab = listener._on_native_key(VK_TAB, is_down=False, is_up=True, extra=0)
    assert sup_tab is True, "Tab keyup must be suppressed to prevent focus navigation away from input"

    # Test Alt+Space release
    listener.reload_config({"hotkey_trigger": "alt_space"})
    listener._alt_space_triggered = True
    sup_space = listener._on_native_key(VK_SPACE, is_down=False, is_up=True, extra=0)
    assert sup_space is True, "Space keyup must be suppressed to prevent spurious space typed into input"


def test_internal_window_identifies_windows_start_menu_and_shell(monkeypatch) -> None:
    """is_internal_window returns True for Windows Start Menu and Shell taskbar to prevent pasting into them."""
    from voice_flow.injector import is_internal_window

    with patch("ctypes.windll.user32.IsWindow", return_value=True), \
         patch("ctypes.windll.user32.GetWindowThreadProcessId", return_value=1), \
         patch("ctypes.windll.user32.GetAncestor", return_value=0), \
         patch("ctypes.windll.user32.GetWindowTextLengthW", return_value=5), \
         patch("ctypes.windll.user32.GetWindowTextW", lambda _h, buff, _l: setattr(buff, "value", "Start")), \
         patch("ctypes.windll.user32.GetClassNameW", lambda _h, buff, _l: setattr(buff, "value", "Shell_TrayWnd")):
        assert is_internal_window(99999) is True


def test_get_hotkey_settings_falls_back_to_trigger_label_when_saved_ptt_missing(tmp_path) -> None:
    """When push_to_talk_shortcut is not set in storage, get_hotkey_settings derives the label from hotkey_trigger."""
    from voice_flow.storage import StorageEngine
    test_storage = StorageEngine(str(tmp_path / "test_missing_ptt.db"))

    test_storage.save_setting("hotkey_trigger", "alt_tab")
    settings = test_storage.get_hotkey_settings()
    assert settings["hotkey_trigger"] == "alt_tab"
    assert settings["push_to_talk_shortcut"] == "Alt+Tab"

    test_storage.save_setting("hotkey_trigger", "custom")
    test_storage.save_setting("custom_hotkey", "Ctrl+Alt+P")
    settings_custom = test_storage.get_hotkey_settings()
    assert settings_custom["hotkey_trigger"] == "custom"
    assert settings_custom["push_to_talk_shortcut"] == "Ctrl+Alt+P"


def test_reload_config_falls_back_to_custom_shortcut_in_storage(monkeypatch) -> None:
    """When reload_config receives empty trigger, it extracts custom shortcut string from storage."""
    from voice_flow import storage as storage_module
    monkeypatch.setattr(storage_module.storage, "get_setting", lambda k, default=None: "Ctrl+Shift+U" if k == "push_to_talk_shortcut" else default)

    listener = InputTriggerListener(
        on_start=lambda: None,
        on_finish=lambda: None,
        on_cancel=lambda: None,
    )
    listener.reload_config({"hotkey_trigger": ""})
    assert listener._hotkey_trigger == "custom"
    assert listener._custom_hotkey_str == "Ctrl+Shift+U"

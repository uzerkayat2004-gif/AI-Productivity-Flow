"""Offline, fake-hook replay of consecutive push-to-talk gestures."""
import threading
import pytest

from voice_flow import mouse_hook
from voice_flow.mouse_hook import WM_MBUTTONDOWN, WM_MBUTTONUP, Win32MouseHook
from voice_flow.hotkeys import InputTriggerListener


@pytest.mark.parametrize("first_result", [None, False])
@pytest.mark.parametrize("app_feedback", [False, True])
@pytest.mark.parametrize("mode", ["ptt_only", "toggle_only"])
def test_slow_first_start_does_not_erase_next_gesture(monkeypatch, first_result, app_feedback, mode):
    monkeypatch.setattr(mouse_hook, "user32", type("User32", (), {
        "SetWindowsHookExW": lambda *args: 123,
        "CallNextHookEx": lambda *args: 0,
    })())
    monkeypatch.setattr(mouse_hook, "kernel32", type("Kernel32", (), {
        "GetModuleHandleW": lambda *args: 1,
    })())
    now = [10.0]
    monkeypatch.setattr(mouse_hook.time, "time", lambda: now[0])
    entered = threading.Event()
    release = threading.Event()
    second_started = threading.Event()
    second_entered = threading.Event()
    release_second = threading.Event()
    finished = threading.Event()
    calls = []

    def start():
        calls.append("start")
        if calls == ["start"]:
            entered.set()
            assert release.wait(1)
            return first_result
        else:
            second_entered.set()
            assert release_second.wait(1)
            if app_feedback:
                bridge.set_recording_state(True)
            second_started.set()

    def finish():
        if app_feedback:
            bridge.set_recording_state(False)
        calls.append("finish")
        if calls.count("finish") == 2:
            finished.set()

    hook = Win32MouseHook(start, finish, lambda: None)
    bridge = object.__new__(InputTriggerListener)
    bridge._lock = threading.RLock()
    bridge._ctrl_check_timer = None
    bridge._mouse_hook = hook
    hook._trigger_mode = mode
    assert hook._install_hook()
    with hook._lock:
        hook._start_workers_locked()
    try:
        hook._hook_proc_ptr(0, WM_MBUTTONDOWN, 0)
        assert entered.wait(.5)
        now[0] = 10.4
        hook._hook_proc_ptr(0, WM_MBUTTONUP, 0)
        if mode == "toggle_only":
            hook._hook_proc_ptr(0, WM_MBUTTONDOWN, 0)
            now[0] = 10.45
            hook._hook_proc_ptr(0, WM_MBUTTONUP, 0)
        now[0] = 10.8
        hook._hook_proc_ptr(0, WM_MBUTTONDOWN, 0)
        release.set()
        assert second_entered.wait(.5)
        if mode == "toggle_only":
            now[0] = 10.85
            hook._hook_proc_ptr(0, WM_MBUTTONUP, 0)
        now[0] = 11.2
        hook._hook_proc_ptr(0, WM_MBUTTONDOWN if mode == "toggle_only" else WM_MBUTTONUP, 0)
        release_second.set()
        assert second_started.wait(.5)
        assert finished.wait(.5), f"release lost after queued start: {calls}"
        assert calls == ["start", "finish", "start", "finish"]
    finally:
        release.set()
        release_second.set()
        hook.stop()


@pytest.mark.parametrize("mode,expected", [("ptt_only", 4), ("toggle_only", 1), ("hybrid", 1)])
def test_separate_rapid_ptt_presses_are_not_contact_chatter(monkeypatch, mode, expected):
    monkeypatch.setattr(mouse_hook, "user32", type("User32", (), {
        "SetWindowsHookExW": lambda *args: 123,
        "CallNextHookEx": lambda *args: 0,
    })())
    monkeypatch.setattr(mouse_hook, "kernel32", type("Kernel32", (), {
        "GetModuleHandleW": lambda *args: 1,
    })())
    now = [10.0]
    monkeypatch.setattr(mouse_hook.time, "time", lambda: now[0])
    hook = Win32MouseHook(lambda: None, lambda: None, lambda: None)
    hook._trigger_mode = mode
    assert hook._install_hook()
    for timestamp, message in [(10., WM_MBUTTONDOWN), (10.05, WM_MBUTTONUP),
                               (10.1, WM_MBUTTONDOWN), (10.15, WM_MBUTTONUP)]:
        now[0] = timestamp
        hook._hook_proc_ptr(0, message, 0)
    callbacks = [fn for fn, args in hook._control_queue.queue]
    if mode == "ptt_only":
        assert callbacks == [hook._safe_on_start, hook._safe_on_finish] * 2
    else:
        assert callbacks == [hook._safe_on_start]
    assert len(callbacks) == expected
    if mode == "ptt_only":
        # Repeated DOWN while physically held is still chatter even after
        # the old time debounce interval expires.
        now[0] = 10.2
        hook._hook_proc_ptr(0, WM_MBUTTONDOWN, 0)
        now[0] = 10.6
        hook._hook_proc_ptr(0, WM_MBUTTONDOWN, 0)
        assert hook._control_queue.qsize() == 5


def test_external_state_sync_retains_public_behavior():
    hook = Win32MouseHook(lambda: None, lambda: None, lambda: None)
    assert hook.set_recording_state(True) is None
    bridge = object.__new__(InputTriggerListener)
    bridge._lock = threading.RLock()
    bridge._ctrl_check_timer = None
    bridge._mouse_hook = hook
    assert bridge.set_recording_state(True) is None
    assert bridge._is_recording is True and hook._is_recording is True
    assert bridge.set_recording_state(False) is None
    assert bridge._is_recording is False and hook._is_recording is False

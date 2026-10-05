"""Regression coverage for the low-level mouse callback resource boundary."""

from __future__ import annotations

import ctypes
import threading
import time

from voice_flow import mouse_hook
from voice_flow.mouse_hook import MSLLHOOKSTRUCT, WM_LBUTTONUP, WM_MBUTTONDOWN, WM_MBUTTONUP, Win32MouseHook, selection_event_is_current


class _FakeUser32:
    def SetWindowsHookExW(self, *_args):
        return 123

    def CallNextHookEx(self, *_args):
        return 0


class _FakeKernel32:
    def GetModuleHandleW(self, *_args):
        return 1

    def GetLastError(self):
        return 0


def _installed_hook(monkeypatch, **callbacks):
    monkeypatch.setattr(mouse_hook, "user32", _FakeUser32())
    monkeypatch.setattr(mouse_hook, "kernel32", _FakeKernel32())
    hook = Win32MouseHook(
        callbacks.get("on_start", lambda: None),
        callbacks.get("on_finish", lambda: None),
        callbacks.get("on_cancel", lambda: None),
        on_mouse_release=callbacks.get("on_mouse_release"),
    )
    assert hook._install_hook()
    return hook


def _invoke_promptly(callback, message):
    returned = threading.Event()

    def invoke():
        callback(0, message, 0)
        returned.set()

    thread = threading.Thread(target=invoke, daemon=True)
    thread.start()
    assert returned.wait(0.25), "low-level callback blocked"
    thread.join(0.1)


def test_middle_callback_returns_promptly_while_lock_is_held(monkeypatch):
    """The fake Win32 callback seam catches accidental reentrant lock use."""
    hook = _installed_hook(monkeypatch)
    hook._lock.acquire()
    try:
        _invoke_promptly(hook._hook_proc_ptr, WM_MBUTTONDOWN)
    finally:
        hook._lock.release()

    assert hook._control_queue.qsize() == 1


def test_ptt_middle_down_up_runs_actions_off_the_hook_thread(monkeypatch):
    actions: list[tuple[str, int]] = []
    completed = threading.Event()

    def finish():
        actions.append(("finish", threading.get_ident()))
        completed.set()

    hook = _installed_hook(monkeypatch, on_start=lambda: actions.append(("start", threading.get_ident())), on_finish=finish)
    hook._trigger_mode = "ptt_only"
    with hook._lock:
        hook._start_workers_locked()
    hook_thread_id = threading.get_ident()
    try:
        _invoke_promptly(hook._hook_proc_ptr, WM_MBUTTONDOWN)
        _invoke_promptly(hook._hook_proc_ptr, WM_MBUTTONUP)
        assert completed.wait(0.5)
        assert [name for name, _ in actions] == ["start", "finish"]
        assert all(thread_id != hook_thread_id for _, thread_id in actions)
    finally:
        hook.stop()


def test_callbacks_use_fixed_workers_and_control_overtakes_slow_selection(monkeypatch):
    selection_started = threading.Event()
    release_selection = threading.Event()
    control_ran = threading.Event()

    def slow_selection(*_args):
        selection_started.set()
        release_selection.wait(1.0)

    hook = _installed_hook(monkeypatch, on_mouse_release=slow_selection)
    with hook._lock:
        hook._start_workers_locked()
    control_worker = hook._worker_thread
    selection_worker = hook._selection_worker_thread
    try:
        hook._enqueue_selection(slow_selection, 1, 2, 3.0, 1, 2)
        assert selection_started.wait(0.5)
        hook._dispatch_action(control_ran.set)
        assert control_ran.wait(0.25), "recording control waited behind selection work"

        # Thousands of hook invocations must reuse the two lifecycle workers;
        # no per-event threads are created by the production callback.
        for _ in range(1000):
            hook._hook_proc_ptr(0, WM_MBUTTONUP, 0)
        assert hook._worker_thread is control_worker
        assert hook._selection_worker_thread is selection_worker
    finally:
        release_selection.set()
        hook.stop()


def test_selection_backlog_is_bounded_and_queue_accounting_is_balanced(monkeypatch):
    hook = _installed_hook(monkeypatch)
    for index in range(1000):
        hook._enqueue_selection(lambda *_args: None, index)

    assert hook._selection_queue.qsize() <= 1
    assert hook._selection_queue.unfinished_tasks <= 1
    while True:
        try:
            hook._selection_queue.get_nowait()
            hook._selection_queue.task_done()
        except mouse_hook.queue.Empty:
            break
    hook._selection_queue.join()


def test_workers_stop_and_restart_without_reusing_dead_queue(monkeypatch):
    ran = []
    hook = _installed_hook(monkeypatch)
    with hook._lock:
        hook._start_workers_locked()
    hook._dispatch_action(ran.append, "first")
    deadline = time.monotonic() + 0.5
    while ran != ["first"] and time.monotonic() < deadline:
        time.sleep(0.01)
    hook.stop()

    hook._stop_event.clear()
    with hook._lock:
        hook._start_workers_locked()
    hook._dispatch_action(ran.append, "second")
    deadline = time.monotonic() + 0.5
    while ran != ["first", "second"] and time.monotonic() < deadline:
        time.sleep(0.01)
    hook.stop()
    assert ran == ["first", "second"]


def test_terminal_control_is_coalesced_when_bounded_queue_is_full(monkeypatch):
    calls: list[str] = []
    hook = _installed_hook(monkeypatch, on_start=lambda: calls.append("start"), on_finish=lambda: calls.append("finish"))
    for _ in range(hook._control_queue.maxsize):
        hook._control_queue.put_nowait((hook._safe_on_start, ()))
    assert hook._dispatch_action(hook._safe_on_finish)
    assert hook._urgent_control is not None
    with hook._lock:
        hook._start_workers_locked()
    deadline = time.monotonic() + 0.5
    while calls != ["finish"] and time.monotonic() < deadline:
        time.sleep(0.01)
    hook.stop()
    assert calls == ["finish"]


def test_thousand_left_releases_do_not_create_workers_after_start(monkeypatch):
    hook = _installed_hook(monkeypatch, on_mouse_release=lambda *_args: None)
    with hook._lock:
        hook._start_workers_locked()
    try:
        # If any callback attempts the former lazy worker creation, fail it.
        monkeypatch.setattr(mouse_hook.threading, "Thread", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("hook created a thread")))
        event = MSLLHOOKSTRUCT()
        event.pt.x, event.pt.y = 40, 60
        address = ctypes.addressof(event)
        for _ in range(1000):
            hook._is_left_down = True
            hook._last_left_down_x, hook._last_left_down_y = 0, 0
            hook._hook_proc_ptr(0, WM_LBUTTONUP, address)
    finally:
        # Restore Thread before joining workers in stop().
        monkeypatch.undo()
        hook.stop()


def test_new_pending_drag_invalidates_an_inflight_selection(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    observed: list[bool] = []

    def slow_selection(*_args):
        started.set()
        release.wait(0.5)
        observed.append(selection_event_is_current())

    hook = _installed_hook(monkeypatch, on_mouse_release=slow_selection)
    with hook._lock:
        hook._start_workers_locked()
    try:
        hook._selection_epoch = 1
        hook._enqueue_selection(hook._safe_on_mouse_release, 1, 1, 20.0, 0, 0, 1)
        assert started.wait(0.25)
        event = MSLLHOOKSTRUCT()
        event.pt.x, event.pt.y = 40, 60
        hook._is_left_down = True
        hook._hook_proc_ptr(0, WM_LBUTTONUP, ctypes.addressof(event))
        release.set()
        deadline = time.monotonic() + 0.5
        while not observed and time.monotonic() < deadline:
            time.sleep(0.01)
        assert observed and observed[0] is False
    finally:
        hook.stop()


def test_legacy_five_argument_selection_callback_is_current(monkeypatch):
    observed: list[bool] = []
    hook = _installed_hook(monkeypatch, on_mouse_release=lambda *_args: observed.append(selection_event_is_current()))
    hook._safe_on_mouse_release(1, 2, 3.0, 0, 0)
    assert observed == [True]


def test_stop_invalidates_a_blocked_selection_before_restart(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    observed: list[bool] = []

    def blocked_selection(*_args):
        started.set()
        release.wait(2.0)
        observed.append(selection_event_is_current())

    hook = _installed_hook(monkeypatch, on_mouse_release=blocked_selection)
    with hook._lock:
        hook._start_workers_locked()
    hook._selection_epoch = 4
    hook._enqueue_selection(hook._safe_on_mouse_release, 1, 1, 20.0, 0, 0, 4)
    assert started.wait(0.25)
    hook.stop()  # bounded join leaves the blocked old callback isolated.
    hook._stop_event.clear()
    with hook._lock:
        hook._start_workers_locked()
    release.set()
    deadline = time.monotonic() + 0.5
    while not observed and time.monotonic() < deadline:
        time.sleep(0.01)
    hook.stop()
    assert observed == [False]

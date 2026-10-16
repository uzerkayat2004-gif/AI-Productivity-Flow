from types import SimpleNamespace
import threading
import time
import pytest

from voice_flow.overlay import FloatingOverlayBar


def make_bar(monkeypatch, zone="speak"):
    bar = FloatingOverlayBar()
    bar.state = "READY"
    bar._main_anchor = (100, 100)
    monkeypatch.setattr(bar, "_get_zone", lambda x, y: zone)
    monkeypatch.setattr(bar, "_current_xy", lambda: (0, 0))
    monkeypatch.setattr(bar, "_foreground_offset", lambda: (0, 0))
    monkeypatch.setattr(bar, "_main_control_size", lambda: (192, 28))
    monkeypatch.setattr(bar, "_draw_if_available", lambda: None)
    return bar


def press(bar):
    bar._on_press(SimpleNamespace(x=20, y=10, x_root=20, y_root=10))


def wait_idle(bar):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        thread = bar._voice_clicks._thread
        if thread is None:
            return
        thread.join(.01)
    raise AssertionError("Voice click worker did not finish")


def test_held_start_does_not_block_tk_heartbeat(monkeypatch):
    bar = make_bar(monkeypatch)
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    callback_threads = []
    ui_threads = []
    heartbeats = []
    def backend():
        callback_threads.append(threading.get_ident())
        entered.set()
        assert release.wait(2)
    bar.on_start_click = backend
    def ui():
        ui_threads.append(threading.get_ident())
        press(bar)
        # This is the next pending Tk event on the same owner thread.
        heartbeats.append("heartbeat")
        returned.set()
    owner = threading.Thread(target=ui)
    owner.start()
    try:
        assert entered.wait(1)
        assert returned.wait(.2), "Tk press handler blocked on backend startup"
        assert heartbeats == ["heartbeat"]
        assert callback_threads != ui_threads
    finally:
        release.set()
        owner.join(2)
        if hasattr(bar, "_voice_clicks"):
            wait_idle(bar)


def test_rapid_start_then_finish_runs_once_in_order(monkeypatch):
    bar = make_bar(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    calls = []
    def start():
        calls.append("start")
        entered.set()
        assert release.wait(2)
    bar.on_start_click = start
    bar.on_finish_click = lambda: calls.append("finish")
    press(bar)
    assert entered.wait(1)
    worker = bar._voice_clicks._thread
    for _ in range(100):
        press(bar)
        assert bar._voice_clicks._thread is worker
    release.set()
    wait_idle(bar)
    assert calls == ["start", "finish"]


def test_cancel_supersedes_pending_finish_and_does_not_move_grip(monkeypatch):
    bar = make_bar(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    calls = []
    def start():
        calls.append("start")
        entered.set()
        assert release.wait(2)
    bar.on_start_click = start
    bar.on_finish_click = lambda: calls.append("finish")
    bar.on_cancel_click = lambda: calls.append("cancel")
    press(bar)
    assert entered.wait(1)
    press(bar)
    bar.state = "RECORDING"
    monkeypatch.setattr(bar, "_get_zone", lambda x, y: "grip")
    press(bar)
    assert bar._press_zone == "grip"
    monkeypatch.setattr(bar, "_get_zone", lambda x, y: "cancel")
    for _ in range(100):
        press(bar)
    release.set()
    wait_idle(bar)
    assert calls == ["start", "cancel"]


def test_summary_voice_and_callback_errors_leave_dispatcher_usable(monkeypatch):
    bar = make_bar(monkeypatch, "summary_voice")
    def fail():
        raise RuntimeError("synthetic backend failure")
    bar.on_start_click = fail
    press(bar)
    wait_idle(bar)
    calls = []
    bar.on_start_click = lambda: calls.append("start")
    press(bar)
    wait_idle(bar)
    assert calls == ["start"]


def test_shutdown_does_not_wait_for_held_backend_or_start_more_work(monkeypatch):
    bar = make_bar(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    calls = []
    def start():
        calls.append("start")
        entered.set()
        assert release.wait(2)
    bar.on_start_click = start
    bar.on_finish_click = lambda: calls.append("finish")
    press(bar)
    assert entered.wait(1)
    press(bar)
    bar._voice_clicks.close()
    press(bar)
    assert not release.is_set()
    release.set()
    wait_idle(bar)
    assert calls == ["start"]


@pytest.mark.parametrize("zone,callback", [("cancel", "on_cancel_click"), ("finish", "on_finish_click")])
def test_recording_terminal_callbacks_also_return_without_backend_wait(monkeypatch, zone, callback):
    bar = make_bar(monkeypatch, zone)
    bar.state = "RECORDING"
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    def backend():
        entered.set()
        assert release.wait(2)
    setattr(bar, callback, backend)
    owner = threading.Thread(target=lambda: (press(bar), returned.set()))
    owner.start()
    try:
        assert entered.wait(1)
        assert returned.wait(.2)
    finally:
        release.set()
        owner.join(2)
        wait_idle(bar)


def test_failed_worker_start_is_isolated_and_next_click_can_retry(monkeypatch):
    bar = make_bar(monkeypatch)
    calls = []
    bar.on_start_click = lambda: calls.append("start")
    original = threading.Thread.start
    def fail_start(self):
        raise RuntimeError("synthetic thread resource pressure")
    monkeypatch.setattr(threading.Thread, "start", fail_start)
    press(bar)
    assert bar._voice_clicks._active is None
    assert bar._voice_clicks._thread is None
    monkeypatch.setattr(threading.Thread, "start", original)
    press(bar)
    wait_idle(bar)
    assert calls == ["start"]

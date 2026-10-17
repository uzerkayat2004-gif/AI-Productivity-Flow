"""macOS Audio Flow selection tap must heal itself.

Regression (Oct 2026, v1.0.3 integration build, macOS 14 + 15 CI): after
launch the listen-only Quartz mouse tap behind the Audio Flow widget was not
running (one of the two pynput run-loop threads missing in `sample`), so
selecting text never showed the Listen widget and the bar never got the
selection for the rest of the session. pynput neither re-enables a tap macOS
switched off nor restarts a listener whose thread ended. The mouse hook now
supervises its tap.

Runs on any OS: Quartz and pynput are faked.
"""
from __future__ import annotations

import sys
import time
import types

from voice_flow import mouse_hook as mouse_hook_module


class _Listener:
    def __init__(self, on_click):
        self.on_click = on_click
        self.daemon = False
        self.started = False
        self.stopped = False
        self.dead = False
        self._apf_tap = object()
        self._apf_tap_failed = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def is_alive(self):
        return self.started and not self.stopped and not self.dead


def _hook(monkeypatch, die_on_start: bool = False):
    created: list[_Listener] = []

    def factory(on_click):
        listener = _Listener(on_click)
        if die_on_start:
            listener.dead = True
            listener._apf_tap = None
            listener._apf_tap_failed = True
        created.append(listener)
        return listener

    monkeypatch.setattr(mouse_hook_module, "IS_MACOS", True)
    monkeypatch.setattr(mouse_hook_module, "IS_WINDOWS", False)
    monkeypatch.setattr(mouse_hook_module, "_create_macos_mouse_listener", factory)
    # The tests drive ticks by hand; keep the background loop out of the way.
    monkeypatch.setattr(mouse_hook_module.Win32MouseHook, "MAC_WATCHDOG_INTERVAL", 3600.0)
    hook = mouse_hook_module.Win32MouseHook(lambda: None, lambda: None, lambda: None, on_mouse_release=lambda *a: None)
    return hook, created


def test_watchdog_restarts_a_listener_whose_thread_ended(monkeypatch, caplog):
    hook, created = _hook(monkeypatch)
    hook.start()
    try:
        assert hook._macos_watchdog_tick() == "ok"
        created[0].dead = True  # tap thread ended (refused tap / run loop finished)
        assert not hook.is_healthy()
        assert hook._macos_watchdog_tick() == "restarted"
        assert len(created) == 2 and created[1].started
        assert created[0].stopped
        assert hook.is_healthy()
        assert "restarting it" in caplog.text
    finally:
        hook.stop()


def test_watchdog_reenables_a_tap_macos_switched_off(monkeypatch, caplog):
    hook, created = _hook(monkeypatch)
    enabled_calls: list = []
    fake_quartz = types.SimpleNamespace(
        CGEventTapIsEnabled=lambda tap: False,
        CGEventTapEnable=lambda tap, on: enabled_calls.append((tap, on)),
    )
    monkeypatch.setitem(sys.modules, "Quartz", fake_quartz)
    hook.start()
    try:
        assert hook._macos_watchdog_tick() == "reenabled"
        assert enabled_calls == [(created[0]._apf_tap, True)]
        assert len(created) == 1  # same listener kept
        assert "re-enabled by the watchdog" in caplog.text
        fake_quartz.CGEventTapIsEnabled = lambda tap: True
        assert hook._macos_watchdog_tick() == "ok"
    finally:
        hook.stop()


def test_refused_tap_is_retried_fast_then_slowly_never_abandoned(monkeypatch):
    hook, created = _hook(monkeypatch, die_on_start=True)
    hook.start()
    try:
        fast = hook.MAC_FAST_RESTARTS
        for _ in range(fast):
            assert hook._macos_watchdog_tick() == "restarted"
        assert hook._macos_watchdog_tick() == "waiting"
        hook._mac_next_restart_at = 0.0  # slow retry interval elapsed
        assert hook._macos_watchdog_tick() == "restarted"
        assert len(created) == fast + 2
    finally:
        hook.stop()


def test_watchdog_does_nothing_after_stop(monkeypatch):
    hook, created = _hook(monkeypatch)
    hook.start()
    hook.stop()
    assert hook._macos_watchdog_tick() == "stopped"
    assert len(created) == 1


def test_background_watchdog_brings_a_dead_tap_back(monkeypatch):
    hook, created = _hook(monkeypatch)
    monkeypatch.setattr(mouse_hook_module.Win32MouseHook, "MAC_WATCHDOG_INTERVAL", 0.02)
    hook.start()
    try:
        assert hook._watchdog_thread is not None and hook._watchdog_thread.is_alive()
        created[0].dead = True
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and len(created) < 2:
            time.sleep(0.01)
        assert len(created) >= 2 and hook.is_healthy()
    finally:
        hook.stop()
    hook._watchdog_thread.join(1.0)
    assert not hook._watchdog_thread.is_alive()


def test_left_button_listener_reenables_tap_on_disabled_event(monkeypatch, caplog):
    """The pynput subclass handles kCGEventTapDisabledBy* instead of ignoring it."""
    calls: dict[str, list] = {"enable": [], "handled": [], "run": []}

    class _Base:
        def __init__(self, on_click=None):
            self.on_click = on_click
            self.running = True

        def _create_event_tap(self):
            return "TAP"

        def _handler(self, proxy, event_type, event, refcon):
            calls["handled"].append(event_type)
            return event

        def _run(self):
            calls["run"].append(True)
            self._create_event_tap()

    _Base.__module__ = "pynput.mouse._darwin"
    fake_mouse = types.SimpleNamespace(Listener=_Base)
    fake_pynput = types.ModuleType("pynput")
    fake_pynput.mouse = fake_mouse
    fake_quartz = types.SimpleNamespace(
        CGEventMaskBit=lambda bit: 1 << bit,
        kCGEventLeftMouseDown=1,
        kCGEventLeftMouseUp=2,
        CGEventTapEnable=lambda tap, on: calls["enable"].append((tap, on)),
    )
    monkeypatch.setitem(sys.modules, "pynput", fake_pynput)
    monkeypatch.setitem(sys.modules, "pynput.mouse", fake_mouse)
    monkeypatch.setitem(sys.modules, "Quartz", fake_quartz)

    listener = mouse_hook_module._create_macos_mouse_listener(lambda *a: None)
    assert listener._create_event_tap() == "TAP" and listener._apf_tap == "TAP"
    assert not listener._apf_tap_failed

    out = listener._handler(None, 0xFFFFFFFE, "EV", None)  # disabled by timeout
    assert out == "EV" and calls["enable"] == [("TAP", True)]
    assert calls["handled"] == []  # not passed on as a click
    listener._handler(None, 0xFFFFFFFF, "EV", None)  # disabled by user input
    assert len(calls["enable"]) == 2
    listener._handler(None, 2, "EV", None)  # a real mouse-up still reaches pynput
    assert calls["handled"] == [2]
    assert "re-enabled" in caplog.text

    listener._run()  # run loop returning while still "running" is reported
    assert "run loop ended unexpectedly" in caplog.text

    _Base._create_event_tap = lambda self: None
    refused = mouse_hook_module._create_macos_mouse_listener(lambda *a: None)
    assert refused._create_event_tap() is None and refused._apf_tap_failed
    assert "CGEventTapCreate returned NULL" in caplog.text

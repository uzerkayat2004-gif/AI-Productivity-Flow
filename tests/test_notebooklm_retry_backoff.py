"""Fake-clock regressions for persistent NotebookLM keepalive recovery."""

from __future__ import annotations

from voice_flow.video_flow_engine.notebooklm import keepalive


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.after_sleep = None

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        if self.after_sleep:
            self.after_sleep()


def use_fake_clock(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(keepalive.time, "time", clock.time)
    monkeypatch.setattr(keepalive.time, "sleep", clock.sleep)
    return clock


def script_runs(service, clock, outcomes):
    calls = []

    def run_once(*, force=False, **_kwargs):
        outcome = outcomes[len(calls)]
        calls.append((clock.now, force))
        service._refresh_state = outcome["state"]
        return {"ran": outcome.get("ran", True), "success": outcome["success"], **outcome}

    service.run_once = run_once
    return calls


def test_transient_failures_use_bounded_backoff_then_recovery_returns_to_normal_cadence(monkeypatch):
    clock = use_fake_clock(monkeypatch)
    service = keepalive.NotebookLMKeepaliveService(
        profile="retry-backoff-test", interval_seconds=1200, refresh_func=lambda **_: {}
    )
    outcomes = [
        {"success": False, "state": "transient_error"},
        {"success": False, "state": "transient_error"},
        {"success": False, "state": "transient_error"},
        {"success": True, "state": "authenticated"},
        {"success": True, "state": "authenticated"},
    ]
    calls = script_runs(service, clock, outcomes)
    original_run = service.run_once

    def stop_after_normal_cadence(*, force=False, **kwargs):
        result = original_run(force=force, **kwargs)
        if len(calls) == 5:
            service._stop_event.set()
        return result

    service.run_once = stop_after_normal_cadence
    service._run_loop()

    times = [at for at, _ in calls]
    assert [round(b - a) for a, b in zip(times, times[1:])] == [60, 120, 300, 1200]


def test_terminal_auth_failure_waits_for_normal_cadence(monkeypatch):
    clock = use_fake_clock(monkeypatch)
    service = keepalive.NotebookLMKeepaliveService(
        profile="retry-terminal-test", interval_seconds=1200, refresh_func=lambda **_: {}
    )
    calls = script_runs(service, clock, [
        {"success": False, "state": "sign_in_required"},
        {"success": True, "state": "authenticated"},
    ])
    original_run = service.run_once

    def stop_after_second(*, force=False, **kwargs):
        result = original_run(force=force, **kwargs)
        if len(calls) == 2:
            service._stop_event.set()
        return result

    service.run_once = stop_after_second
    service._run_loop()

    assert [at for at, _ in calls] == [0.0, 1200.0]


def test_explicit_disconnect_clears_pending_transient_backoff(monkeypatch):
    clock = use_fake_clock(monkeypatch)
    service = keepalive.NotebookLMKeepaliveService(
        profile="retry-disconnect-test", interval_seconds=1200, refresh_func=lambda **_: {}
    )
    calls = script_runs(service, clock, [
        {"success": False, "state": "transient_error"},
        {"ran": False, "success": False, "state": "idle", "reason": "explicit_disconnected"},
        {"success": True, "state": "authenticated"},
    ])
    original_run = service.run_once

    def stop_after_normal_cadence(*, force=False, **kwargs):
        result = original_run(force=force, **kwargs)
        if len(calls) == 3:
            service._stop_event.set()
        return result

    service.run_once = stop_after_normal_cadence
    service._run_loop()

    assert [at for at, _ in calls] == [0.0, 60.0, 1260.0]


def test_wake_runs_immediately_and_starts_a_fresh_backoff_streak(monkeypatch):
    clock = use_fake_clock(monkeypatch)
    service = keepalive.NotebookLMKeepaliveService(
        profile="retry-wake-test", interval_seconds=1200, refresh_func=lambda **_: {}
    )
    calls = script_runs(service, clock, [
        {"success": False, "state": "transient_error"},
        {"success": False, "state": "transient_error"},
        {"success": False, "state": "transient_error"},
        {"success": True, "state": "authenticated"},
    ])
    jumped = False

    def jump_after_second_failure():
        nonlocal jumped
        if len(calls) == 2 and not jumped:
            clock.now += 6
            jumped = True

    clock.after_sleep = jump_after_second_failure
    original_run = service.run_once

    def stop_after_recovery(*, force=False, **kwargs):
        result = original_run(force=force, **kwargs)
        if len(calls) == 4:
            service._stop_event.set()
        return result

    service.run_once = stop_after_recovery
    service._run_loop()

    assert [at for at, _ in calls] == [0.0, 60.0, 67.0, 127.0]
    assert calls[2][1] is True


def test_manual_refresh_success_cancels_pending_short_retry(monkeypatch):
    clock = use_fake_clock(monkeypatch)
    service = keepalive.NotebookLMKeepaliveService(
        profile="retry-manual-success-test", interval_seconds=1200, refresh_func=lambda **_: {}
    )
    calls = script_runs(service, clock, [
        {"success": False, "state": "transient_error"},
        {"success": True, "state": "authenticated"},
    ])
    original_sleep = clock.sleep

    def sleep_and_complete_manual_refresh(seconds):
        original_sleep(seconds)
        if clock.now == 30:
            service._refresh_state = "authenticated"

    monkeypatch.setattr(keepalive.time, "sleep", sleep_and_complete_manual_refresh)
    original_run = service.run_once

    def stop_after_normal_cadence(*, force=False, **kwargs):
        result = original_run(force=force, **kwargs)
        if len(calls) == 2:
            service._stop_event.set()
        return result

    service.run_once = stop_after_normal_cadence
    service._run_loop()

    assert [at for at, _ in calls] == [0.0, 1230.0]


def test_stop_event_exits_wait_without_an_extra_refresh(monkeypatch):
    clock = use_fake_clock(monkeypatch)
    service = keepalive.NotebookLMKeepaliveService(
        profile="retry-stop-test", interval_seconds=1200, refresh_func=lambda **_: {}
    )
    calls = script_runs(service, clock, [{"success": True, "state": "authenticated"}])
    original_sleep = clock.sleep

    def stop_during_wait(seconds):
        original_sleep(seconds)
        service._stop_event.set()

    monkeypatch.setattr(keepalive.time, "sleep", stop_during_wait)
    service._run_loop()

    assert len(calls) == 1

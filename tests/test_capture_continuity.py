"""Regression tests for hands-free capture lifecycle continuity."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from voice_flow import main as main_module
from voice_flow import paths
from voice_flow import storage as storage_module
from voice_flow.main import DictationState, VoiceFlowApp


def test_gui_recording_watcher_ignores_transient_setting_read_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    class StopWatcher(Exception):
        pass

    reads = iter((True, RuntimeError("database is busy"), True, False))

    class FakeStorage:
        def get_setting(self, key, default):
            assert (key, default) == ("recording", False)
            value = next(reads)
            if isinstance(value, Exception):
                raise value
            return value

    sleep_count = 0

    def bounded_sleep(_seconds: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count > 4:
            raise StopWatcher

    callbacks: list[str] = []

    class ImmediateThread:
        def __init__(self, *, target, daemon):
            self._target = target

        def start(self) -> None:
            self._target()

    app = VoiceFlowApp.__new__(VoiceFlowApp)
    app._on_dictation_start = lambda: callbacks.append("start")
    app._on_dictation_finish = lambda: callbacks.append("finish")
    app._state_lock = threading.RLock()
    app.state = DictationState.IDLE

    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(storage_module, "storage", FakeStorage())
    monkeypatch.setattr(main_module.time, "sleep", bounded_sleep)
    monkeypatch.setattr(main_module, "threading", SimpleNamespace(Thread=ImmediateThread))

    with pytest.raises(StopWatcher):
        app._watch_gui_state_file()

    assert callbacks == ["start", "finish"]

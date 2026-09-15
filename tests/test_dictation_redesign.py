"""Regression coverage for release-time Voice Flow orchestration.

These tests construct only the dictation coordinator.  They deliberately do
not load a microphone, clipboard, provider, or persistent store.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import numpy as np
import pytest

from voice_flow import main as main_module
from voice_flow.main import DictationSession, DictationState, VoiceFlowApp


def _session() -> DictationSession:
    return DictationSession(
        target_hwnd=42,
        app_title="Editor",
        app_category="smart_clean",
        style_id="smart_clean",
        started_at=0.0,
        resolved_style=SimpleNamespace(
            app_name="Editor", category="smart_clean", style_id="smart_clean", instruction="clean"
        ),
    )


def _processing_app(session: DictationSession, transcript: str) -> VoiceFlowApp:
    app = object.__new__(VoiceFlowApp)
    app.processing_lock = threading.Lock()
    app._state_lock = threading.RLock()
    app.state = DictationState.PROCESSING
    app.session = session
    app.transcriber = SimpleNamespace(transcribe=lambda _audio, **_kwargs: transcript)
    app._stream_stt = SimpleNamespace(end_session=lambda **_kwargs: None, discard=lambda: None)
    app.injector = SimpleNamespace(paste_text=lambda *_args, **_kwargs: True)
    app.overlay = SimpleNamespace(show_error=lambda *_args: None, show_done=lambda *_args: None, show_ready=lambda: None)
    app.hotkeys = SimpleNamespace(set_recording_state=lambda *_args: None)
    app.recent_dictations = set()
    app.last_successful_transcript = None
    return app


def _bypass_text_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "detect_voice_command", lambda text: SimpleNamespace(command=None, content=text))
    monkeypatch.setattr(main_module, "apply_spoken_punctuation", lambda text: text)
    monkeypatch.setattr(main_module, "split_press_enter", lambda text, _enabled: SimpleNamespace(text=text, press_enter=False))
    monkeypatch.setattr(main_module, "smart_format", lambda text, _style, _context=None: text)
    monkeypatch.setattr(main_module.polisher, "polish", lambda text, **_kwargs: text)
    monkeypatch.setattr(main_module.storage, "add_dictation", lambda *_args, **_kwargs: SimpleNamespace(id=1))


def test_expired_latency_target_does_not_discard_complete_recording(monkeypatch: pytest.MonkeyPatch) -> None:
    """A latency target may skip optional work, but cannot drop completed audio."""
    session = _session()
    app = _processing_app(session, "the complete long recording with its final words")
    pasted: list[str] = []
    app.injector = SimpleNamespace(paste_text=lambda text, *_args, **_kwargs: pasted.append(text) or True)
    app._post_release_deadline = main_module.time.monotonic() - 1.0
    _bypass_text_steps(monkeypatch)

    app._process_dictation_pipeline(session, object(), 45.0, use_streaming=False)

    assert pasted == ["the complete long recording with its final words"]
    assert app.state == DictationState.IDLE


def test_release_starts_pipeline_before_archive_or_history_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """Release must hand audio to the worker immediately; persistence is post-paste."""
    session = _session()
    calls: list[str] = []
    scheduled: list[dict] = []

    class FakeThread:
        def __init__(self, *, target, args=(), kwargs=None, daemon, name=None):
            scheduled.append({"target": target, "args": args, "kwargs": kwargs, "daemon": daemon})

        def start(self) -> None:
            return None

    app = object.__new__(VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = DictationState.RECORDING
    app.session = session
    app._record_watchdog = None
    app._stream_stt = SimpleNamespace(end_session=lambda **_kwargs: None, accepted_count=lambda: 0)
    app.audio = SimpleNamespace(stop=lambda: np.ones(16_000, dtype=np.float32))
    app.archive = SimpleNamespace(save=lambda _audio: calls.append("archive"))
    app._set_hotkeys_recording_state = lambda _active: None
    app._streaming_stt_enabled = lambda: False
    app._overlay_call = lambda *_args, **_kwargs: None

    monkeypatch.setattr(main_module.threading, "Thread", FakeThread)
    monkeypatch.setattr(main_module.storage, "add_dictation", lambda *_args, **_kwargs: calls.append("history"))

    assert app._on_dictation_finish() is True
    assert calls == []
    pipeline = [job for job in scheduled if job["target"] == app._process_dictation_pipeline]
    assert len(pipeline) == 1
    assert pipeline[0]["kwargs"]["use_streaming"] is False


def test_cancel_records_one_terminal_history_outcome_off_the_hotkey_path() -> None:
    session = _session()
    app = object.__new__(VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = DictationState.RECORDING
    app.session = session
    app._record_watchdog = None
    app.audio = SimpleNamespace(stop=lambda: np.ones(16_000, dtype=np.float32))
    app._stream_stt = SimpleNamespace(end_session=lambda: None, discard=lambda: None)
    app._set_hotkeys_recording_state = lambda _active: None
    app._overlay_call = lambda *_args, **_kwargs: None
    archived: list[object] = []
    history: list[dict] = []
    app._start_recovery_archive = lambda audio, recovery: archived.append(audio) or recovery
    app._defer_history_insert = lambda recovery, saved_session, duration, **fields: history.append(
        {"recovery": recovery, "session": saved_session, "duration": duration, **fields}
    )

    assert app._on_dictation_cancel() is True
    assert app.state == DictationState.IDLE
    assert app.session is None
    assert len(archived) == 1
    assert len(history) == 1
    assert history[0]["session"] is session
    assert history[0]["status"] == "cancelled"
    assert history[0]["insertion_status"] == "not_attempted"


def test_rejected_short_capture_is_recorded_as_a_terminal_failure() -> None:
    session = _session()
    history: list[dict] = []
    app = object.__new__(VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = DictationState.RECORDING
    app.session = session
    app._record_watchdog = None
    app.audio = SimpleNamespace(stop=lambda: np.ones(1_000, dtype=np.float32))
    app._stream_stt = SimpleNamespace()
    app._set_hotkeys_recording_state = lambda _active: None
    app._streaming_stt_enabled = lambda: False
    app._overlay_call = lambda *_args, **_kwargs: None
    app._defer_history_insert = lambda recovery, saved_session, duration, **fields: history.append(
        {"recovery": recovery, "session": saved_session, "duration": duration, **fields}
    )

    assert app._on_dictation_finish() is False
    assert app.state == DictationState.IDLE
    assert len(history) == 1
    assert history[0]["status"] == "transcription_failed"
    assert history[0]["error_message"] == "No usable audio was captured"


def test_cancel_during_transcription_retains_audio_and_cannot_close_next_session(monkeypatch):
    session = _session()
    app = _processing_app(session, "late old transcript")
    _bypass_text_steps(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    audio = np.ones(16000, dtype=np.float32)
    recovery = {"audio_buffer": audio, "audio_path": "saved.wav", "done": threading.Event(), "archive_started": True}
    recovery["done"].set()
    app._pending_recovery = {id(session): recovery}
    app._stream_session_owner = session
    history, pasted, closed = [], [], []
    app._defer_history_insert = lambda saved, owner, duration, **fields: history.append((saved, duration, fields))
    app.injector.paste_text = lambda *args, **kwargs: pasted.append(args) or True
    app._stream_stt.end_session = lambda **kwargs: closed.append(app._stream_session_owner)

    def transcribe(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return "late old transcript"

    app.transcriber.transcribe = transcribe
    worker = threading.Thread(target=app._process_dictation_pipeline, args=(session, audio, 1.0))
    worker.start()
    assert entered.wait(3)
    try:
        assert app._on_dictation_cancel()
        assert history[0][0] is recovery
        assert history[0][1] == 1.0
        next_session = _session()
        app.session, app.state = next_session, DictationState.RECORDING
        app._stream_session_owner = next_session
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive()
    assert pasted == []
    assert len(history) == 1 and history[0][2]["status"] == "cancelled"
    assert app.session is next_session and app.state == DictationState.RECORDING
    assert closed == [session]

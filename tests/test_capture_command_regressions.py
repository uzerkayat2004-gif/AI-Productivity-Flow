"""Focused regressions for startup capture, wake aliases, and polish truthfulness."""
from __future__ import annotations

import threading
from types import SimpleNamespace

import numpy as np
import pytest

from voice_flow.audio import AudioRecorder
from voice_flow.main import DictationSession, DictationState, VoiceFlowApp, _polish_outcome_label
from voice_flow.voice_commands import detect_voice_command


def test_full_wake_and_guarded_asr_aliases_make_good_prompt() -> None:
    for phrase in (
        "Keep every requirement. Hey Voice Flow, make this a good prompt?",
        "Keep every requirement. Hey voice, make this a good prompt?",
        "Keep every requirement. hay voiced what make this as a good prompt?",
    ):
        detected = detect_voice_command(phrase)
        assert detected.command is not None
        assert detected.command.format == "prompt"
        assert detected.content == "Keep every requirement."


def test_guarded_alias_does_not_turn_mentions_or_quotes_into_commands() -> None:
    quoted = 'She asked, "Hey voice, make this a good prompt" during the demo.'
    assert detect_voice_command(quoted).command is None
    ordinary = "Hey voice, are you ready for the Voice Flow demo?"
    assert detect_voice_command(ordinary).command is None


def test_startup_frame_buffer_replays_frames_then_closed_chunks_in_order() -> None:
    recorder = AudioRecorder()
    recorder._recording = True
    recorder._native_sr = 16000
    recorder.begin_stream_input_buffering()
    first = np.full((2, 1), 0.1, dtype=np.float32)
    second = np.full((2, 1), 0.2, dtype=np.float32)
    recorder._audio_callback(first, 2, None, None)
    recorder._audio_callback(second, 2, None, None)
    recorder._pending_closed_chunks.append((np.array([[0.3]], dtype=np.float32), 0.0))
    events: list[tuple[str, float]] = []
    recorder.on_audio_frame = lambda frame, _sr: events.append(("frame", float(frame[0, 0])))
    recorder.on_chunk_closed = lambda chunk, _sr, **_kw: events.append(("chunk", float(chunk[0, 0])))

    recorder.flush_stream_input_buffer()

    # Frames and closed chunks must replay in capture order. The samples are
    # float32, so compare them numerically rather than by exact equality.
    assert [kind for kind, _value in events] == ["frame", "frame", "chunk"]
    assert [value for _kind, value in events] == pytest.approx([0.1, 0.2, 0.3])
    assert not recorder._buffer_stream_input


def test_dictation_opens_capture_before_stream_setup(monkeypatch) -> None:
    session = DictationSession(123, "Editor", "smart_clean", "smart_clean", 0.0)
    app = object.__new__(VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = DictationState.IDLE
    app.session = None
    app._record_watchdog = None
    app._capture_session = lambda: session
    events: list[str] = []
    app.audio = SimpleNamespace(
        begin_stream_input_buffering=lambda: events.append("buffer"),
        start=lambda: events.append("audio") or True,
        flush_stream_input_buffer=lambda: events.append("flush"),
        discard_stream_input_buffer=lambda: events.append("discard"),
        stop=lambda: None,
        level=0.0,
    )
    app.hotkeys = SimpleNamespace(set_recording_state=lambda *_args: None)
    app.overlay = SimpleNamespace(show_recording=lambda **_kw: None, show_error=lambda *_args: None)
    app._start_stream_for_session = lambda _session: events.append("stream")
    app._start_window_tracker = lambda _session: events.append("tracker")
    monkeypatch.setattr("voice_flow.main.storage.get_setting", lambda key, default=None: True if key == "voice_flow_enabled" else default)
    monkeypatch.setattr("voice_flow.main._warm_voice_gemini_transport", lambda _model: events.append("warm"))

    assert app._on_dictation_start() is True
    assert events[:4] == ["buffer", "audio", "stream", "flush"]


def test_failed_ai_outcomes_keep_input_and_have_truthful_labels(monkeypatch) -> None:
    from voice_flow import main

    app = object.__new__(VoiceFlowApp)
    session = SimpleNamespace(cleanup_level="cleanup_light", style_id="smart_clean", cursor_context=None, polish_model_ref="gemini/chosen", polish_speed_mode="fast")
    monkeypatch.setattr(main.polisher, "polish", lambda _text, **kw: kw["outcome_callback"]("timeout") or "changed text")
    monkeypatch.setattr(main, "smart_format", lambda *_args: (_ for _ in ()).throw(AssertionError("must not format failed AI output")))

    assert app._finalize_text("First and last words", session) == "First and last words"
    assert _polish_outcome_label("timeout") == "AI timed out — original text kept"
    assert _polish_outcome_label("provider_failure") == "AI unavailable — original text kept"
    assert _polish_outcome_label("disabled") == "Transcribed"
    assert _polish_outcome_label("local") == "Cleaned locally"

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


def test_startup_live_frame_replay_keeps_frames_arriving_during_flush_in_order() -> None:
    recorder = AudioRecorder()
    recorder._native_sr = 16000
    recorder._recording = True
    recorder.begin_stream_input_buffering()
    for value in (0.1, 0.2):
        recorder._audio_callback(np.full((4, 1), value, dtype=np.float32), 4, None, None)

    delivered: list[float] = []
    injected = False

    def on_frame(frame: np.ndarray, _sample_rate: int) -> None:
        nonlocal injected
        delivered.append(float(frame[0, 0]))
        if not injected:
            injected = True
            recorder._audio_callback(np.full((4, 1), 0.3, dtype=np.float32), 4, None, None)

    recorder.on_audio_frame = on_frame
    recorder.flush_stream_input_buffer()

    assert delivered == pytest.approx([0.1, 0.2, 0.3])


def test_startup_replay_overflow_flags_stream_incomplete_and_keeps_archive(monkeypatch) -> None:
    monkeypatch.setattr("voice_flow.audio.MAX_STARTUP_STREAM_BUFFER_SECONDS", 4 / 16000)
    recorder = AudioRecorder()
    recorder._native_sr = 16000
    recorder._recording = True
    recorder.begin_stream_input_buffering()
    first = np.full((4, 1), 0.1, dtype=np.float32)
    arriving_during_replay = np.full((4, 1), 0.3, dtype=np.float32)
    recorder._audio_callback(first, 4, None, None)

    delivered: list[float] = []

    def slow_frame_sink(frame: np.ndarray, _sample_rate: int) -> None:
        delivered.append(float(frame[0, 0]))
        recorder._audio_callback(arriving_during_replay, 4, None, None)

    recorder.on_audio_frame = slow_frame_sink
    recorder.flush_stream_input_buffer()

    assert delivered == pytest.approx([0.1])
    assert recorder.stream_input_incomplete is True
    np.testing.assert_array_equal(np.concatenate(recorder._buffer), np.concatenate((first, arriving_during_replay)))

    recorder.begin_stream_input_buffering()
    assert recorder.stream_input_incomplete is False


def test_stream_sink_exception_flags_incomplete_but_retains_recorded_frame() -> None:
    recorder = AudioRecorder()
    recorder._native_sr = 16000
    recorder._recording = True
    recorder.begin_stream_input_buffering()
    frame = np.full((4, 1), 0.1, dtype=np.float32)
    recorder._audio_callback(frame, 4, None, None)

    def failing_sink(_frame: np.ndarray, _sample_rate: int) -> None:
        raise RuntimeError("simulated stream intake failure")

    recorder.on_audio_frame = failing_sink
    recorder.flush_stream_input_buffer()

    assert recorder.stream_input_incomplete is True
    np.testing.assert_array_equal(np.concatenate(recorder._buffer), frame)


def test_concurrent_startup_flush_has_a_single_replay_owner() -> None:
    recorder = AudioRecorder()
    recorder._native_sr = 16000
    recorder._recording = True
    recorder.begin_stream_input_buffering()
    for value in (0.1, 0.2):
        recorder._audio_callback(np.full((4, 1), value, dtype=np.float32), 4, None, None)

    first_sink_entered = threading.Event()
    release_sink = threading.Event()
    delivered: list[float] = []

    def blocking_sink(frame: np.ndarray, _sample_rate: int) -> None:
        delivered.append(float(frame[0, 0]))
        if len(delivered) == 1:
            first_sink_entered.set()
            assert release_sink.wait(1.0)

    recorder.on_audio_frame = blocking_sink
    owner = threading.Thread(target=recorder.flush_stream_input_buffer)
    owner.start()
    assert first_sink_entered.wait(0.5)

    callback_done = threading.Event()
    callback = threading.Thread(
        target=lambda: (
            recorder._audio_callback(np.full((4, 1), 0.3, dtype=np.float32), 4, None, None),
            callback_done.set(),
        )
    )
    callback.start()
    assert callback_done.wait(0.5), "recorder callback blocked behind the provider sink"

    second_flush = threading.Thread(target=recorder.flush_stream_input_buffer)
    second_flush.start()
    second_flush.join(timeout=0.5)
    assert not second_flush.is_alive(), "a second flush must not steal the active replay queue"

    release_sink.set()
    owner.join(timeout=1.0)
    callback.join(timeout=1.0)
    assert not owner.is_alive()
    assert delivered == pytest.approx([0.1, 0.2, 0.3])


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


def test_selected_lfm_is_not_warmed_during_recording(monkeypatch) -> None:
    from voice_flow import lfm_engine, main

    calls: list[float] = []

    class InlineThread:
        def __init__(self, *, target, args=(), kwargs=None, **_unused):
            self.target = target
            self.args = args
            self.kwargs = kwargs or {}

        def start(self):
            self.target(*self.args, **self.kwargs)

    monkeypatch.setattr(main.storage, "get_setting", lambda key, default=None: True if key == "polishing_enabled" else default)
    monkeypatch.setattr(main.threading, "Thread", InlineThread)
    monkeypatch.setattr(lfm_engine, "warm_lfm_model", lambda *, timeout_seconds: calls.append(timeout_seconds) or True)

    main._warm_voice_gemini_transport(lfm_engine.LFM_MODEL_ID)

    assert calls == []


def test_failed_ai_outcomes_keep_input_and_have_truthful_labels(monkeypatch) -> None:
    from voice_flow import main

    app = object.__new__(VoiceFlowApp)
    session = SimpleNamespace(cleanup_level="cleanup_light", style_id="smart_clean", cursor_context=None, polish_model_ref="gemini/chosen", polish_speed_mode="fast")
    monkeypatch.setattr(main.polisher, "polish", lambda _text, **kw: kw["outcome_callback"]("timeout") or "changed text")
    monkeypatch.setattr(main, "smart_format", lambda *_args: (_ for _ in ()).throw(AssertionError("must not format failed AI output")))

    assert app._finalize_text("First and last words", session) == "changed text"
    assert _polish_outcome_label("timeout") == "AI timed out — basic cleanup applied"
    assert _polish_outcome_label("provider_failure") == "AI unavailable — basic cleanup applied"
    assert _polish_outcome_label("disabled") == "Basic cleanup applied"
    assert _polish_outcome_label("local") == "Cleaned locally"


def test_disabled_polish_still_delivers_basic_cleanup_and_dictionary(monkeypatch) -> None:
    """The privacy switch skips AI/style work, not safe local delivery work."""
    from voice_flow import main, polisher as polisher_module

    class Dictionary:
        def apply_dictionary_post_processing(self, text: str) -> str:
            return text.replace("Hyper Kube", "HyperKube")

        def restore_dictionary_spelling(self, text: str) -> str:
            return text

    dictionary = Dictionary()
    monkeypatch.setattr(main, "dictionary_engine", dictionary)
    monkeypatch.setattr(polisher_module, "dictionary_engine", dictionary)
    monkeypatch.setattr(polisher_module.storage, "get_setting", lambda key, default=None: False if key == "polishing_enabled" else default)
    monkeypatch.setattr(main, "smart_format", lambda *_args: (_ for _ in ()).throw(AssertionError("disabled polish must not apply a style")))

    app = object.__new__(VoiceFlowApp)
    session = SimpleNamespace(cleanup_level="cleanup_light", style_id="other_formal", cursor_context=None)

    assert app._finalize_text("Um, send the Hyper Kube update uh to Alice", session) == "Send the HyperKube update to Alice."


def test_disabled_polish_respects_explicit_cleanup_none(monkeypatch) -> None:
    """The explicit no-cleanup setting stays verbatim apart from dictionary rules."""
    from voice_flow import main, polisher as polisher_module

    class Dictionary:
        def apply_dictionary_post_processing(self, text: str) -> str:
            return text.replace("Hyper Kube", "HyperKube")

        def restore_dictionary_spelling(self, text: str) -> str:
            return text

    dictionary = Dictionary()
    monkeypatch.setattr(main, "dictionary_engine", dictionary)
    monkeypatch.setattr(polisher_module, "dictionary_engine", dictionary)
    monkeypatch.setattr(polisher_module.storage, "get_setting", lambda key, default=None: False if key == "polishing_enabled" else default)

    app = object.__new__(VoiceFlowApp)
    session = SimpleNamespace(cleanup_level="cleanup_none", style_id="personal_very_casual", cursor_context=None)

    assert app._finalize_text("Um, send the Hyper Kube update uh to Alice", session) == "Um, send the HyperKube update uh to Alice"

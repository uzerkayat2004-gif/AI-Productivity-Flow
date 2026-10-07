"""Regression coverage for the Voice Flow release-to-paste boundary.

These tests deliberately exercise the coordinator seam rather than individual
STT/polish providers.  The user-visible regressions were caused by the
coordinator waiting past its latency budget and allowing best-effort history
I/O to corrupt the processing state.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import numpy as np
import pytest

import voice_flow.main as main_module
import voice_flow.injector as injector_module
import voice_flow.hotkeys as hotkeys_module
from voice_flow.main import DictationSession, DictationState, VoiceFlowApp


class _CompleteStream:
    def __init__(self) -> None:
        self.collect_timeouts: list[float] = []
        self.collect_lifecycle: list[tuple[int, int]] = []
        self.ended = 0
        self.discarded = 0

    def collect(self, timeout: float = 0.0) -> str:
        self.collect_timeouts.append(timeout)
        self.collect_lifecycle.append((self.ended, self.discarded))
        return "complete streamed transcript"

    def pending_count(self) -> int:
        return 0

    def end_session(self) -> None:
        self.ended += 1

    def discard(self) -> None:
        self.discarded += 1


class _FailedStream(_CompleteStream):
    def had_failures(self) -> bool:
        return True


class _PendingStream(_CompleteStream):
    def collect(self, timeout: float = 0.0, deadline: float | None = None) -> str:
        self.collect_timeouts.append(timeout)
        return "incomplete streamed prefix"

    def pending_count(self) -> int:
        return 1


class _HelloStream(_CompleteStream):
    def collect(self, timeout: float = 0.0) -> str:
        self.collect_timeouts.append(timeout)
        return "hello"


class _BrokenAudioCompletenessProbe:
    @property
    def stream_input_incomplete(self) -> bool:
        raise OSError("recorder state unavailable")


def _app(session: DictationSession) -> VoiceFlowApp:
    app = object.__new__(VoiceFlowApp)
    app.processing_lock = threading.Lock()
    app._state_lock = threading.RLock()
    app.state = DictationState.PROCESSING
    app.session = session
    app.transcriber = SimpleNamespace(transcribe=lambda _audio, **_kwargs: "whole buffer")
    app.injector = SimpleNamespace(paste_text=lambda *_args, **_kwargs: True)
    app.overlay = SimpleNamespace(
        show_error=lambda *_args: None,
        show_done=lambda *_args: None,
        show_ready=lambda: None,
        show_processing=lambda: None,
    )
    app.hotkeys = SimpleNamespace(set_recording_state=lambda *_args: None)
    app.recent_dictations = set()
    app.last_successful_transcript = None
    return app


def test_cleanup_budget_is_independent_and_mode_aware() -> None:
    """A completed STT pass must grant cleanup its own small bounded lane."""
    assert main_module._polish_budget_seconds("fast", 5) < main_module._polish_budget_seconds("balanced", 5)
    assert main_module._polish_budget_seconds("balanced", 5) < main_module._polish_budget_seconds("quality", 5)
    assert main_module._polish_budget_seconds("fast", 400) < main_module._polish_budget_seconds("balanced", 400)
    assert main_module._polish_budget_seconds("balanced", 400) < main_module._polish_budget_seconds("quality", 400)
    assert main_module._polish_budget_seconds("quality", 10000) <= 12.0


def test_cloud_and_local_cleanup_both_get_usable_time_after_transcription(monkeypatch) -> None:
    """Slow STT must not disable the user's selected polishing model."""
    def run(model_ref: str) -> tuple[float, float]:
        session = DictationSession(
            target_hwnd=123, app_title="Editor", app_category="smart_clean",
            style_id="smart_clean", started_at=0.0, stt_model_ref=model_ref,
            resolved_style=SimpleNamespace(app_name="Editor", category="smart_clean",
                                           style_id="smart_clean", instruction="clean up lightly"),
        )
        app = _app(session)
        app._post_release_deadline = main_module.time.monotonic() + 0.5
        seen: list[tuple[float, float]] = []
        app.injector = SimpleNamespace(paste_text=lambda *_args, **_kwargs: True)
        monkeypatch.setattr(
            main_module.polisher,
            "polish",
            lambda text, **kwargs: seen.append((kwargs["deadline"], main_module.time.monotonic())) or text,
        )
        app._process_dictation_pipeline(session, object(), 1.0, record_id=1, use_streaming=False)
        # The budget contract ends at the polisher boundary. History/overlay
        # work follows delivery and can vary with the host filesystem.
        return seen[0]

    monkeypatch.setattr(main_module, "detect_voice_command", lambda text: SimpleNamespace(command=None, content=text))
    monkeypatch.setattr(main_module, "apply_spoken_punctuation", lambda text: text)
    monkeypatch.setattr(main_module, "split_press_enter", lambda text, _enabled: SimpleNamespace(text=text, press_enter=False))
    monkeypatch.setattr(main_module, "smart_format", lambda text, _style, _context=None: text)
    monkeypatch.setattr(main_module.storage, "update_dictation", lambda *_args, **_kwargs: True)

    cloud_deadline, cloud_now = run("groq/whisper-large-v3")
    local_deadline, local_now = run("local/nemotron-speech-streaming-en-0.6b")

    assert 2.5 < cloud_deadline - cloud_now <= 5.0
    assert 2.5 < local_deadline - local_now <= 5.0


def test_command_only_persistent_change_saves_without_arming_or_pasting(monkeypatch) -> None:
    session = DictationSession(
        target_hwnd=123, app_title="Editor", app_category="work", style_id="work_formal",
        started_at=0.0,
        resolved_style=SimpleNamespace(app_name="Editor", category="work", style_id="work_formal", instruction="work"),
    )
    app = _app(session)
    app.injector = SimpleNamespace(paste_text=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("command was pasted")))
    saved: list[object] = []
    monkeypatch.setattr(main_module, "apply_persistent_change", lambda command: saved.append(command) or "work setting saved")
    monkeypatch.setattr(main_module.storage, "get_setting", lambda key, default=None: True if key == "polishing_enabled" else default)
    monkeypatch.setattr(main_module.storage, "update_dictation", lambda *_args, **_kwargs: True)

    app.transcriber = SimpleNamespace(transcribe=lambda _audio, **_kwargs: "Hey Voice Flow, always make my work messages short.")
    app._process_dictation_pipeline(session, object(), 1.0, record_id=1, use_streaming=False)

    assert saved
    assert getattr(app, "_pending_command", None) is None
    assert app.state == DictationState.IDLE


@pytest.mark.parametrize("stored_value", [False, "false"])
def test_polishing_off_preserves_voice_command_words_and_clears_pending_command(monkeypatch, stored_value) -> None:
    """OFF is a hard boundary: no command parsing, arming, selection, or save."""
    session = DictationSession(
        target_hwnd=123, app_title="Editor", app_category="work", style_id="work_formal",
        started_at=0.0,
        resolved_style=SimpleNamespace(app_name="Editor", category="work", style_id="work_formal", instruction="work"),
    )
    app = _app(session)
    app._pending_command = SimpleNamespace(label=lambda: "stale command")
    delivered: list[str] = []
    app.injector = SimpleNamespace(
        paste_text=lambda text, *_args, **_kwargs: delivered.append(text) or True,
        get_selected_text_strict=lambda *_args, **_kwargs: pytest.fail("OFF must not inspect selected text"),
    )
    raw = "Hey Voice Flow, make this formal. Keep every word."
    app.transcriber = SimpleNamespace(transcribe=lambda _audio, **_kwargs: raw)
    app._defer_history_insert = lambda *_args, **_kwargs: None

    monkeypatch.setattr(main_module.storage, "get_setting", lambda key, default=None: stored_value if key == "polishing_enabled" else default)
    monkeypatch.setattr(main_module, "detect_voice_command", lambda *_args: pytest.fail("OFF must not parse voice commands"))
    monkeypatch.setattr(main_module, "apply_persistent_change", lambda *_args: pytest.fail("OFF must not save a voice command"))
    monkeypatch.setattr(main_module, "apply_spoken_punctuation", lambda text: text)
    monkeypatch.setattr(main_module, "split_press_enter", lambda text, _enabled: SimpleNamespace(text=text, press_enter=False))
    monkeypatch.setattr(main_module, "smart_format", lambda text, _style, _context=None: text)
    monkeypatch.setattr(main_module.storage, "update_dictation", lambda *_args, **_kwargs: True)

    def basic_cleanup(text, **kwargs):
        kwargs["outcome_callback"]("disabled")
        return text

    monkeypatch.setattr(main_module.polisher, "polish", basic_cleanup)
    app._process_dictation_pipeline(session, object(), 1.0, record_id=1, use_streaming=False)

    assert delivered == [raw]
    assert getattr(app, "_pending_command", None) is None
    assert app.state == DictationState.IDLE


@pytest.mark.parametrize("polishing_enabled", [True, False])
def test_final_dictionary_guard_restores_canonical_casing_after_style_format(monkeypatch, tmp_path, polishing_enabled: bool) -> None:
    """Formatting must not undo vocabulary restored by local or AI cleanup."""
    app = object.__new__(VoiceFlowApp)
    session = DictationSession(123, "Editor", "personal", "personal_very_casual", 0.0)
    from voice_flow.dictionary import DictionaryEngine
    from voice_flow.storage import StorageEngine
    from voice_flow.polisher import TextPolisher
    store = StorageEngine(str(tmp_path / "words.db"))
    store.add_dictionary_word("HyperKube")
    engine = DictionaryEngine(store)
    monkeypatch.setattr(main_module, "dictionary_engine", engine)
    import voice_flow.polisher as polish_module
    monkeypatch.setattr(polish_module, "dictionary_engine", engine)
    monkeypatch.setattr(polish_module.storage, "get_setting", lambda key, default=None: polishing_enabled if key == "polishing_enabled" else default)
    monkeypatch.setattr(polish_module.storage, "get_all_api_keys", lambda: {})
    polisher = TextPolisher()
    monkeypatch.setattr(polisher, "_polish_with_api_pool", lambda *_args, **_kwargs: "HyperKube release is ready today")
    monkeypatch.setattr(main_module, "polisher", polisher)
    monkeypatch.setattr(main_module, "smart_format", lambda text, *_args: text.lower())
    result = app._finalize_text("HyperKube release is ready today", session)
    assert "HyperKube" in result
    assert "hyperkube" not in result


@pytest.mark.parametrize("polishing_enabled", [True, False])
def test_finalization_applies_joined_vocabulary_alias_once_with_polishing_on_or_off(monkeypatch, tmp_path, polishing_enabled: bool) -> None:
    """Both modes deliver a spoken `Hyper Kube` as the user-saved spelling."""
    from voice_flow.dictionary import DictionaryEngine
    from voice_flow.polisher import TextPolisher
    from voice_flow.storage import StorageEngine
    import voice_flow.polisher as polish_module

    store = StorageEngine(str(tmp_path / "words.db"))
    assert store.add_dictionary_word("HyperKube")
    engine = DictionaryEngine(store)
    monkeypatch.setattr(main_module, "dictionary_engine", engine)
    monkeypatch.setattr(polish_module, "dictionary_engine", engine)
    monkeypatch.setattr(
        polish_module.storage,
        "get_setting",
        lambda key, default=None: (
            polishing_enabled if key == "polishing_enabled"
            else "local/deterministic" if key == "voice_flow_polish_model"
            else default
        ),
    )
    monkeypatch.setattr(main_module, "polisher", TextPolisher())
    monkeypatch.setattr(main_module, "smart_format", lambda text, *_args: text.lower())
    session = DictationSession(123, "Editor", "personal", "personal_very_casual", 0.0, cleanup_level="cleanup_light")
    trace = []

    result = object.__new__(VoiceFlowApp)._finalize_text(
        "Please send the Hyper Kube update.", session, dictionary_trace=trace,
    )

    assert "HyperKube" in result
    assert "Hyper Kube" not in result
    assert result.count("HyperKube") == 1
    assert len(trace) == 1
    assert trace[0]["from"].casefold() == "hyper kube"
    assert trace[0]["to"] == "HyperKube"


@pytest.mark.parametrize("polishing_enabled", [True, False])
def test_finalization_expands_custom_snippet_once_with_truthful_trace(monkeypatch, tmp_path, polishing_enabled: bool) -> None:
    from voice_flow.dictionary import DictionaryEngine
    from voice_flow.polisher import TextPolisher
    from voice_flow.storage import StorageEngine
    import voice_flow.polisher as polish_module

    store = StorageEngine(str(tmp_path / "snippets.db"))
    store.add_snippet("sig", "Regards, Ada")
    engine = DictionaryEngine(store)
    monkeypatch.setattr(main_module, "dictionary_engine", engine)
    monkeypatch.setattr(polish_module, "dictionary_engine", engine)
    monkeypatch.setattr(
        polish_module.storage,
        "get_setting",
        lambda key, default=None: (
            polishing_enabled if key == "polishing_enabled"
            else "local/deterministic" if key == "voice_flow_polish_model"
            else default
        ),
    )
    monkeypatch.setattr(main_module, "polisher", TextPolisher())
    monkeypatch.setattr(main_module, "smart_format", lambda text, *_args: text)
    session = DictationSession(123, "Editor", "personal", "smart_clean", 0.0, cleanup_level="cleanup_light")
    trace = []

    result = object.__new__(VoiceFlowApp)._finalize_text(
        "Please use sig", session, dictionary_trace=trace,
    )

    assert "Regards, Ada" in result
    assert trace == [{"from": "sig", "to": "Regards, Ada"}]


@pytest.mark.parametrize("polishing_enabled", [True, False])
def test_finalization_keeps_transcript_when_dictionary_is_unavailable(monkeypatch, polishing_enabled: bool) -> None:
    from voice_flow.polisher import TextPolisher
    import voice_flow.polisher as polish_module

    class UnavailableDictionary:
        def apply_dictionary_post_processing(self, *_args, **_kwargs):
            raise OSError("dictionary unavailable")

        def restore_dictionary_spelling(self, *_args, **_kwargs):
            raise OSError("dictionary unavailable")

    unavailable = UnavailableDictionary()
    monkeypatch.setattr(main_module, "dictionary_engine", unavailable)
    monkeypatch.setattr(polish_module, "dictionary_engine", unavailable)
    monkeypatch.setattr(
        polish_module.storage,
        "get_setting",
        lambda key, default=None: (
            polishing_enabled if key == "polishing_enabled"
            else "local/deterministic" if key == "voice_flow_polish_model"
            else default
        ),
    )
    monkeypatch.setattr(main_module, "polisher", TextPolisher())
    monkeypatch.setattr(main_module, "smart_format", lambda text, *_args: text)
    session = DictationSession(123, "Editor", "personal", "smart_clean", 0.0, cleanup_level="cleanup_none")

    result = object.__new__(VoiceFlowApp)._finalize_text(
        "keep every raw word", session, dictionary_trace=[],
    )

    assert result == "keep every raw word"


@pytest.mark.parametrize("polishing_enabled", [True, False])
def test_raw_decoder_and_finalizer_apply_a_correction_chain_only_once(
    monkeypatch, tmp_path, polishing_enabled: bool,
) -> None:
    import threading
    import voice_flow.polisher as polish_module
    import voice_flow.transcriber as transcriber_module
    from voice_flow.dictionary import DictionaryEngine
    from voice_flow.polisher import TextPolisher
    from voice_flow.storage import StorageEngine

    store = StorageEngine(str(tmp_path / "single-pass.db"))
    store.add_dictionary_correction("first", "second")
    store.add_dictionary_correction("second", "third")
    engine = DictionaryEngine(store)
    monkeypatch.setattr(transcriber_module, "dictionary_engine", engine, raising=False)
    monkeypatch.setattr(transcriber_module.nemotron_engine, "is_nemotron_model", lambda _ref: False)
    monkeypatch.setattr(main_module, "dictionary_engine", engine)
    monkeypatch.setattr(polish_module, "dictionary_engine", engine)
    monkeypatch.setattr(
        polish_module.storage,
        "get_setting",
        lambda key, default=None: (
            polishing_enabled if key == "polishing_enabled"
            else "local/deterministic" if key == "voice_flow_polish_model"
            else default
        ),
    )

    class Segment:
        text = "first"

    class RawModel:
        def transcribe(self, _audio, **_kwargs):
            return [Segment()], None

    transcriber = object.__new__(transcriber_module.Transcriber)
    transcriber.model = RawModel()
    transcriber._lock = threading.Lock()
    transcriber._transcribe_lock = threading.Lock()
    transcriber._wait_for_model = lambda *_args, **_kwargs: True
    raw = transcriber._transcribe_local(
        np.full(3200, 0.2, dtype=np.float32), model_ref="base.en",
    )

    monkeypatch.setattr(main_module, "polisher", TextPolisher())
    monkeypatch.setattr(main_module, "smart_format", lambda text, *_args: text)
    session = DictationSession(
        123, "Editor", "personal", "smart_clean", 0.0, cleanup_level="cleanup_light",
    )
    trace = []
    result = object.__new__(VoiceFlowApp)._finalize_text(
        raw, session, dictionary_trace=trace,
    )

    assert raw == "first"
    assert result == "second."
    assert trace == [{"from": "First", "to": "second"}]


def test_polish_mode_normalization_uses_the_three_persisted_policy_values() -> None:
    # "Deep Quality" is a display label, while the API persists ``quality``.
    assert main_module._normalize_polish_speed_mode("fast") == "fast"
    assert main_module._normalize_polish_speed_mode("balanced") == "balanced"
    assert main_module._normalize_polish_speed_mode("quality") == "quality"
    assert main_module._normalize_polish_speed_mode("Deep Quality") == "balanced"
    assert main_module._normalize_polish_speed_mode("unknown") == "balanced"


def test_stream_harvest_has_one_bounded_post_release_wait_and_deadline(monkeypatch) -> None:
    session = DictationSession(
        target_hwnd=123,
        app_title="Editor",
        app_category="smart_clean",
        style_id="smart_clean",
        started_at=0.0,
        resolved_style=SimpleNamespace(
            app_name="Editor",
            category="smart_clean",
            style_id="smart_clean",
            instruction="clean up lightly",
        ),
    )
    app = _app(session)
    stream = _CompleteStream()
    app._stream_stt = stream
    whole_buffer_calls: list[object] = []
    app.transcriber = SimpleNamespace(
        transcribe=lambda audio, **_kwargs: whole_buffer_calls.append(audio) or "whole buffer"
    )
    seen_deadlines: list[float | None] = []

    monkeypatch.setattr(main_module, "detect_voice_command", lambda _text: SimpleNamespace(command=None, content="complete streamed transcript"))
    monkeypatch.setattr(main_module, "apply_spoken_punctuation", lambda text: text)
    monkeypatch.setattr(main_module, "split_press_enter", lambda text, _enabled: SimpleNamespace(text=text, press_enter=False))
    monkeypatch.setattr(main_module, "smart_format", lambda text, _style, _context=None: text)
    monkeypatch.setattr(main_module.storage, "update_dictation", lambda *_args, **_kwargs: True)

    def fake_polish(text, **kwargs):
        seen_deadlines.append(kwargs.get("deadline"))
        return text

    monkeypatch.setattr(main_module.polisher, "polish", fake_polish)
    app._process_dictation_pipeline(session, object(), 1.0, record_id=1, use_streaming=True)

    assert stream.collect_timeouts
    assert max(stream.collect_timeouts) <= main_module.POST_RELEASE_WORK_BUDGET_SECONDS
    assert stream.collect_lifecycle == [(0, 0)]
    assert not whole_buffer_calls
    assert seen_deadlines and seen_deadlines[0] is not None
    assert app.state == DictationState.IDLE
    assert stream.ended == 1
    assert stream.discarded == 1


def test_stream_failure_probe_forces_complete_whole_buffer_fallback(monkeypatch) -> None:
    session = DictationSession(
        target_hwnd=123,
        app_title="Editor",
        app_category="smart_clean",
        style_id="smart_clean",
        started_at=0.0,
        resolved_style=SimpleNamespace(
            app_name="Editor",
            category="smart_clean",
            style_id="smart_clean",
            instruction="clean up lightly",
        ),
    )
    app = _app(session)
    stream = _FailedStream()
    app._stream_stt = stream
    whole_buffer_calls: list[float | None] = []

    def transcribe(_audio, **kwargs):
        whole_buffer_calls.append(kwargs.get("deadline"))
        return "whole buffer complete transcript"

    app.transcriber = SimpleNamespace(transcribe=transcribe)
    pasted: list[str] = []
    app.injector = SimpleNamespace(paste_text=lambda text, *_args, **_kwargs: pasted.append(text) or True)
    monkeypatch.setattr(main_module, "detect_voice_command", lambda _text: SimpleNamespace(command=None, content="whole buffer complete transcript"))
    monkeypatch.setattr(main_module, "apply_spoken_punctuation", lambda text: text)
    monkeypatch.setattr(main_module, "split_press_enter", lambda text, _enabled: SimpleNamespace(text=text, press_enter=False))
    monkeypatch.setattr(main_module, "smart_format", lambda text, _style, _context=None: text)
    monkeypatch.setattr(main_module.polisher, "polish", lambda text, **_kwargs: text)
    monkeypatch.setattr(main_module.storage, "get_setting", lambda key, default=None: True if key == "polishing_enabled" else default)
    monkeypatch.setattr(main_module.storage, "update_dictation", lambda *_args, **_kwargs: True)

    app._process_dictation_pipeline(session, object(), 1.0, record_id=1, use_streaming=True)

    assert pasted == ["whole buffer complete transcript"]
    assert whole_buffer_calls and whole_buffer_calls[0] is not None
    assert app.state == DictationState.IDLE


@pytest.mark.parametrize(
    "recorder",
    [SimpleNamespace(stream_input_incomplete=True), _BrokenAudioCompletenessProbe()],
    ids=["known-incomplete", "probe-failed"],
)
def test_incomplete_audio_stream_uses_archive_without_harvesting_partial_text(monkeypatch, recorder) -> None:
    session = DictationSession(
        target_hwnd=123,
        app_title="Editor",
        app_category="smart_clean",
        style_id="smart_clean",
        started_at=0.0,
        resolved_style=SimpleNamespace(
            app_name="Editor",
            category="smart_clean",
            style_id="smart_clean",
            instruction="clean up lightly",
        ),
    )
    app = _app(session)
    stream = _HelloStream()
    app._stream_stt = stream
    app.audio = recorder
    archive = object()
    whole_buffer_calls: list[object] = []
    lifecycle_at_recovery: list[tuple[int, int]] = []

    def transcribe(audio, **_kwargs):
        whole_buffer_calls.append(audio)
        lifecycle_at_recovery.append((stream.ended, stream.discarded))
        return "hello welcome"

    app.transcriber = SimpleNamespace(transcribe=transcribe)
    pasted: list[str] = []
    app.injector = SimpleNamespace(paste_text=lambda text, *_args, **_kwargs: pasted.append(text) or True)
    monkeypatch.setattr(
        main_module,
        "detect_voice_command",
        lambda text: SimpleNamespace(command=None, content=text),
    )
    monkeypatch.setattr(main_module, "apply_spoken_punctuation", lambda text: text)
    monkeypatch.setattr(main_module, "split_press_enter", lambda text, _enabled: SimpleNamespace(text=text, press_enter=False))
    monkeypatch.setattr(main_module, "smart_format", lambda text, _style, _context=None: text)
    monkeypatch.setattr(main_module.polisher, "polish", lambda text, **_kwargs: text)
    monkeypatch.setattr(main_module.storage, "get_setting", lambda key, default=None: True if key == "polishing_enabled" else default)
    monkeypatch.setattr(main_module.storage, "update_dictation", lambda *_args, **_kwargs: True)

    app._process_dictation_pipeline(session, archive, 1.0, record_id=1, use_streaming=True)

    assert whole_buffer_calls == [archive]
    assert lifecycle_at_recovery == [(1, 1)]
    assert stream.collect_timeouts == []
    assert pasted == ["hello welcome"]
    assert stream.ended == 1
    assert stream.discarded == 1


@pytest.mark.parametrize(
    ("transcript", "outcome", "expected_done", "expected_error"),
    [
        (
            "Hey Voice Flow make this a professional email. We launch Monday.",
            "local_model",
            "Local model polished — Email / Professional",
            None,
        ),
        (
            "Hey Voice Flow make this short. We launch Monday.",
            "provider_failure",
            None,
            "AI unavailable — basic cleanup applied — Short",
        ),
        (
            "Hey Voice Flow make this short. We launch Monday.",
            "command_unfulfilled",
            None,
            "Voice command could not be completed — basic cleanup applied — Short",
        ),
    ],
    ids=["fulfilled-local-model", "provider-failure", "command-unfulfilled"],
)
def test_command_overlay_reports_validated_local_model_success_only(
    monkeypatch, transcript, outcome, expected_done, expected_error
) -> None:
    session = DictationSession(
        target_hwnd=123,
        app_title="Editor",
        app_category="smart_clean",
        style_id="smart_clean",
        started_at=0.0,
        resolved_style=SimpleNamespace(
            app_name="Editor",
            category="smart_clean",
            style_id="smart_clean",
            instruction="clean up lightly",
        ),
    )
    app = _app(session)
    app.transcriber = SimpleNamespace(transcribe=lambda _audio, **_kwargs: transcript)
    done: list[str] = []
    errors: list[str] = []
    app.overlay.show_done = lambda message: done.append(message)
    app.overlay.show_error = lambda message: errors.append(message)
    app._defer_history_insert = lambda *_args, **_kwargs: None

    def fake_finalize(_text, _session, _resolved_style=None, *, effective, command, outcome_callback, **_kwargs):
        assert effective.requires_ai
        assert effective.label == ("Email / Professional" if outcome == "local_model" else "Short")
        assert command is not None
        outcome_callback(outcome)
        return "Hello,\n\nWe launch Monday.\n\nBest."

    app._finalize_text = fake_finalize
    monkeypatch.setattr(main_module.storage, "get_setting", lambda key, default=None: {
        "polishing_enabled": True,
        "style_email": "email_formal",
        "voice_flow_polish_speed_mode": "balanced",
    }.get(key, default))
    monkeypatch.setattr(main_module.storage, "update_dictation", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main_module, "apply_spoken_punctuation", lambda text: text)
    monkeypatch.setattr(main_module, "split_press_enter", lambda text, _enabled: SimpleNamespace(text=text, press_enter=False))
    monkeypatch.setattr(main_module, "smart_format", lambda text, _style, _context=None: text)

    app._process_dictation_pipeline(session, object(), 1.0, record_id=1, use_streaming=False)

    if expected_done:
        assert done == [expected_done]
        assert errors == []
    else:
        assert done == []
        assert errors == [expected_error]


def test_stream_harvest_reserves_time_for_complete_recording_recovery(monkeypatch) -> None:
    session = DictationSession(
        target_hwnd=123,
        app_title="Editor",
        app_category="smart_clean",
        style_id="smart_clean",
        started_at=0.0,
        resolved_style=SimpleNamespace(
            app_name="Editor",
            category="smart_clean",
            style_id="smart_clean",
            instruction="clean up lightly",
        ),
    )
    app = _app(session)
    stream = _PendingStream()
    app._stream_stt = stream
    whole_buffer_calls: list[float | None] = []

    def transcribe(_audio, **kwargs):
        whole_buffer_calls.append(kwargs.get("deadline"))
        return "whole buffer complete transcript"

    app.transcriber = SimpleNamespace(transcribe=transcribe)
    pasted: list[str] = []
    app.injector = SimpleNamespace(paste_text=lambda text, *_args, **_kwargs: pasted.append(text) or True)
    monkeypatch.setattr(main_module, "detect_voice_command", lambda _text: SimpleNamespace(command=None, content="whole buffer complete transcript"))
    monkeypatch.setattr(main_module, "apply_spoken_punctuation", lambda text: text)
    monkeypatch.setattr(main_module, "split_press_enter", lambda text, _enabled: SimpleNamespace(text=text, press_enter=False))
    monkeypatch.setattr(main_module, "smart_format", lambda text, _style, _context=None: text)
    monkeypatch.setattr(main_module.polisher, "polish", lambda text, **_kwargs: text)
    monkeypatch.setattr(main_module.storage, "update_dictation", lambda *_args, **_kwargs: True)

    app._process_dictation_pipeline(session, object(), 1.0, record_id=1, use_streaming=True)

    maximum_harvest = (
        main_module.POST_RELEASE_WORK_BUDGET_SECONDS
        - main_module.WHOLE_BUFFER_RECOVERY_RESERVE_SECONDS
        - main_module.INJECTION_RESERVE_SECONDS
    )
    assert stream.collect_timeouts and max(stream.collect_timeouts) <= maximum_harvest
    assert whole_buffer_calls and whole_buffer_calls[0] is not None
    assert pasted == ["whole buffer complete transcript"]


def test_dictation_start_forwards_overlay_keyword_callback(monkeypatch) -> None:
    session = DictationSession(
        target_hwnd=123,
        app_title="Editor",
        app_category="smart_clean",
        style_id="smart_clean",
        started_at=0.0,
        resolved_style=SimpleNamespace(
            app_name="Editor",
            category="smart_clean",
            style_id="smart_clean",
            instruction="clean up lightly",
        ),
    )
    app = object.__new__(VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = DictationState.IDLE
    app.session = None
    app._record_watchdog = None
    app._capture_session = lambda: session
    app._streaming_stt_enabled = lambda: False
    app.audio = SimpleNamespace(start=lambda: True, stop=lambda: None, level=0.0)
    app.hotkeys = SimpleNamespace(set_recording_state=lambda *_args: None)
    recording_kwargs: list[dict] = []
    app.overlay = SimpleNamespace(
        show_recording=lambda **kwargs: recording_kwargs.append(kwargs),
        show_error=lambda *_args: None,
        show_ready=lambda: None,
    )
    monkeypatch.setattr(main_module.storage, "get_setting", lambda _key, default=None: default if _key != "voice_flow_enabled" else True)

    assert app._on_dictation_start() is True
    assert recording_kwargs and "level_provider" in recording_kwargs[0]
    app._on_dictation_cancel()


@pytest.mark.parametrize(("accepted_chunks", "expected_tail_submits"), [(0, 0), (1, 1)])
def test_release_submits_tail_only_after_a_background_chunk(
    monkeypatch,
    accepted_chunks: int,
    expected_tail_submits: int,
) -> None:
    session = DictationSession(
        target_hwnd=123,
        app_title="Editor",
        app_category="smart_clean",
        style_id="smart_clean",
        started_at=0.0,
    )
    submitted: list[object] = []
    ended: list[bool] = []
    scheduled: list[dict] = []

    stream = SimpleNamespace(
        accepted_count=lambda: accepted_chunks,
        submit_native=lambda *args, **kwargs: submitted.append((args, kwargs)),
        end_session=lambda **_kwargs: ended.append(True),
    )
    audio = SimpleNamespace(
        _native_sr=16000,
        take_open_chunk=lambda: np.ones(1600, dtype=np.float32),
        stop=lambda: np.ones(16000, dtype=np.float32),
    )

    class FakeThread:
        def __init__(self, *, target, args, kwargs, daemon):
            scheduled.append({"target": target, "args": args, "kwargs": kwargs, "daemon": daemon})

        def start(self) -> None:
            return None

    app = object.__new__(VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = DictationState.RECORDING
    app.session = session
    app._record_watchdog = None
    app._stream_stt = stream
    app.audio = audio
    app.archive = SimpleNamespace(save=lambda _audio: None)
    app._set_hotkeys_recording_state = lambda _active: None
    app._streaming_stt_enabled = lambda: True
    app._overlay_call = lambda *_args, **_kwargs: None

    monkeypatch.setattr(main_module.storage, "add_dictation", lambda *_args, **_kwargs: SimpleNamespace(id=1))
    monkeypatch.setattr(main_module.threading, "Thread", FakeThread)

    assert app._on_dictation_finish() is True
    assert len(submitted) == expected_tail_submits
    assert ended == [True]
    assert scheduled and scheduled[0]["kwargs"] == {"use_streaming": True}


def test_release_uses_quiescent_tail_snapshot_and_forwards_its_overlap(monkeypatch) -> None:
    session = DictationSession(target_hwnd=123, app_title="Editor", app_category="smart_clean", style_id="smart_clean", started_at=0.0)
    calls: list[str] = []
    submitted: list[tuple[tuple, dict]] = []
    stream = SimpleNamespace(
        accepted_count=lambda: 1,
        submit_native=lambda *args, **kwargs: submitted.append((args, kwargs)),
        end_session=lambda **_kwargs: calls.append("end"),
    )
    audio = SimpleNamespace(
        _native_sr=16000,
        stop_and_take_open_chunk=lambda: (calls.append("stop") or np.ones(16000, dtype=np.float32), np.ones(1600, dtype=np.float32), 0.75),
        stop=lambda: (_ for _ in ()).throw(AssertionError("legacy stop path used")),
    )

    class FakeThread:
        def __init__(self, *, target, args, kwargs, daemon):
            pass

        def start(self) -> None:
            return None

    app = object.__new__(VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = DictationState.RECORDING
    app.session = session
    app._record_watchdog = None
    app._stream_stt = stream
    app.audio = audio
    app.archive = SimpleNamespace(save=lambda _audio: None)
    app._set_hotkeys_recording_state = lambda _active: None
    app._streaming_stt_enabled = lambda: True
    app._overlay_call = lambda *_args, **_kwargs: None

    monkeypatch.setattr(main_module.storage, "add_dictation", lambda *_args, **_kwargs: SimpleNamespace(id=1))
    monkeypatch.setattr(main_module.threading, "Thread", FakeThread)

    assert app._on_dictation_finish() is True
    assert calls == ["stop", "end"]
    assert submitted[0][1]["overlap_prefix_seconds"] == 0.75


def test_history_failure_after_valid_text_does_not_brick_state(monkeypatch) -> None:
    session = DictationSession(
        target_hwnd=123,
        app_title="Editor",
        app_category="smart_clean",
        style_id="smart_clean",
        started_at=0.0,
        resolved_style=SimpleNamespace(
            app_name="Editor",
            category="smart_clean",
            style_id="smart_clean",
            instruction="clean up lightly",
        ),
    )
    app = _app(session)
    pasted: list[str] = []
    app.injector = SimpleNamespace(paste_text=lambda text, *_args, **_kwargs: pasted.append(text) or True)

    monkeypatch.setattr(main_module, "detect_voice_command", lambda _text: SimpleNamespace(command=None, content="hello world"))
    monkeypatch.setattr(main_module, "apply_spoken_punctuation", lambda text: text)
    monkeypatch.setattr(main_module, "split_press_enter", lambda text, _enabled: SimpleNamespace(text=text, press_enter=False))
    monkeypatch.setattr(main_module, "smart_format", lambda text, _style, _context=None: text)
    monkeypatch.setattr(main_module.polisher, "polish", lambda text, **_kwargs: text)
    monkeypatch.setattr(main_module.storage, "get_setting", lambda key, default=None: True if key == "polishing_enabled" else default)

    def history_is_unavailable(*_args, **_kwargs):
        raise OSError("database or disk is full")

    monkeypatch.setattr(main_module.storage, "update_dictation", history_is_unavailable)

    app._process_dictation_pipeline(session, object(), 1.0, record_id=1, use_streaming=False)

    assert pasted == ["hello world"]
    assert app.state == DictationState.IDLE
    assert app.session is None


def test_failed_injection_restores_the_original_clipboard(monkeypatch) -> None:
    copied: list[str] = []
    monkeypatch.setattr(injector_module, "_wait_for_modifiers_released", lambda **_kwargs: None)
    monkeypatch.setattr(injector_module, "_safe_paste_from_clipboard", lambda: "keep this clipboard text")
    monkeypatch.setattr(injector_module, "_safe_copy_to_clipboard", lambda text: copied.append(text) or True)
    monkeypatch.setattr(injector_module, "get_active_window_title", lambda: "Editor")
    monkeypatch.setattr(injector_module, "get_window_class_name", lambda _hwnd: "EditorClass")
    monkeypatch.setattr(injector_module, "_send_win32_ctrl_v", lambda: (_ for _ in ()).throw(RuntimeError("target rejected paste")))
    monkeypatch.setattr(injector_module.time, "sleep", lambda *_args: None)
    monkeypatch.setattr(
        injector_module.ctypes,
        "windll",
        SimpleNamespace(user32=SimpleNamespace(GetForegroundWindow=lambda: 123)),
    )

    assert injector_module.inject_text("new transcript") is False
    assert copied[-1] == "keep this clipboard text"


def test_hotkey_start_failure_clears_optimistic_recording_flag() -> None:
    listener = object.__new__(hotkeys_module.InputTriggerListener)
    listener._lock = threading.Lock()
    listener._is_recording = True
    listener._hotkey_triggered = True
    listener._on_start = lambda: False
    calls: list[bool] = []
    listener._mouse_hook = SimpleNamespace(set_recording_state=lambda value: calls.append(value))

    listener._safe_on_start()

    assert listener._is_recording is False
    assert listener._hotkey_triggered is False
    assert calls == [False]

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from voice_flow import main as main_module
from voice_flow.audio_flow_widget import AudioFlowFloatingWidget
from voice_flow.main import DictationState, VoiceFlowApp


def _wait_until(predicate, timeout: float = 1.0) -> bool:
    """Keep async Audio Flow assertions bounded and deterministic."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


class _Overlay:
    def __init__(self) -> None:
        self.cleared = 0
        self.selected: list[str] = []
        self.states: list[tuple[str, str | None]] = []

    def clear_selected_text(self) -> None:
        self.cleared += 1

    def set_selected_text(self, text: str) -> None:
        self.selected.append(text)

    def show_ready(self) -> None:
        self.states.append(("ready", None))

    def show_error(self, message: str) -> None:
        self.states.append(("error", message))

    def show_reading(self, snippet: str) -> None:
        self.states.append(("reading", snippet))

    def show_generating_audio(self, snippet: str = "Generating audio...") -> None:
        self.states.append(("generating_audio", snippet))

    def show_summarizing(self, mode: str = "") -> None:
        self.states.append(("summarizing", mode))

    def show_audio_summary_progress(self, progress: int = 0, stage: str = "") -> None:
        self.states.append(("audio_summary_progress", (progress, stage)))

    def clear_audio_summary_status(self) -> None:
        self.states.append(("audio_summary_cleared", None))


def _selection_app(injector: object) -> VoiceFlowApp:
    app = object.__new__(VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = DictationState.IDLE
    app.overlay = _Overlay()
    app.injector = injector
    app.recent_dictations = set()
    app.last_successful_transcript = None
    app._selection_generation = 0
    app._audio_summary_generation = 0
    return app


def test_stale_selection_capture_cannot_resurface_after_a_new_click(monkeypatch) -> None:
    capture_started = threading.Event()
    release_capture = threading.Event()

    class Injector:
        def get_selected_text_strict(self, *, target_hwnd=None) -> str:
            capture_started.set()
            release_capture.wait(1.0)
            return "stale selected text"

    app = _selection_app(Injector())
    shown: list[tuple[int, int, str]] = []
    hidden: list[bool] = []
    monkeypatch.setattr(main_module.storage, "get_setting", lambda _key, default=None: default)
    monkeypatch.setattr(main_module.audio_flow_widget, "show_at", lambda x, y, text: shown.append((x, y, text)))
    monkeypatch.setattr(main_module.audio_flow_widget, "hide", lambda: hidden.append(True))
    monkeypatch.setattr(
        main_module.ctypes,
        "windll",
        SimpleNamespace(user32=SimpleNamespace(IsWindow=lambda _hwnd: False, GetForegroundWindow=lambda: 1)),
    )

    app._on_mouse_release(120, 240, 40, 80, 240)
    assert capture_started.wait(1.0)

    # This is the ordinary click that should invalidate the in-flight capture.
    app._on_mouse_release(120, 240, 0, 120, 240)
    release_capture.set()
    time.sleep(0.05)

    assert hidden == [True]
    assert shown == []


def test_audio_widget_replays_selection_requested_before_tk_attach() -> None:
    widget = AudioFlowFloatingWidget()
    widget.show_at(120, 240, "selected before Tk is ready")

    assert widget._pending_show == (120, 240, "selected before Tk is ready")

    class Win:
        def geometry(self, _value: str) -> None:
            pass

        def deiconify(self) -> None:
            pass

        def lift(self) -> None:
            pass

        def attributes(self, *_args) -> None:
            pass

    class Root:
        def after(self, _delay: int, callback) -> None:
            callback()

        def winfo_screenwidth(self) -> int:
            return 1920

        def winfo_screenheight(self) -> int:
            return 1080

    widget._init_tk = lambda: setattr(widget, "win", Win())
    widget.attach_root(Root())

    assert widget._pending_show is None
    assert widget._is_visible is True
    assert widget._current_text == "selected before Tk is ready"


def test_audio_pipeline_releases_action_state_on_done_error_and_rejection(monkeypatch) -> None:
    app = _selection_app(SimpleNamespace(get_selected_text=lambda **_kwargs: ""))
    resets: list[bool] = []
    monkeypatch.setattr(main_module.audio_flow_widget, "set_playing", lambda playing: resets.append(playing))

    class TTS:
        def __init__(self) -> None:
            self.callbacks = None

        def is_speaking(self) -> bool:
            return False

        def speak(self, _text, *, on_start, on_done, on_error) -> None:
            self.callbacks = (on_start, on_done, on_error)

        def stop(self) -> None:
            pass

    tts = TTS()
    monkeypatch.setattr(main_module, "tts_engine", tts)
    monkeypatch.setattr(main_module.storage, "get_setting", lambda _key, default=None: default)
    from voice_flow.audio_explainer import audio_explainer
    monkeypatch.setattr(audio_explainer, "transform_for_human_reading", lambda text: text)
    app._is_voice_flow_dictation = lambda _text: False

    app._process_audio_flow_pipeline(text_override="selected text")
    assert _wait_until(lambda: tts.callbacks is not None)
    tts.callbacks[1]()
    tts.callbacks[2]("synthesis failed")

    monkeypatch.setattr(main_module.storage, "get_setting", lambda key, default=None: False if key == "audio_flow_enabled" else default)
    app._process_audio_flow_pipeline(text_override="selected text")

    assert resets == [False, False, False]


def test_explicit_selection_bypasses_recent_dictation_guard(monkeypatch) -> None:
    app = _selection_app(SimpleNamespace(get_selected_text=lambda **_kwargs: ""))
    spoken: list[str] = []

    class TTS:
        def is_speaking(self) -> bool:
            return False

        def speak(self, text, **_callbacks) -> None:
            spoken.append(text)

        def stop(self) -> None:
            pass

    monkeypatch.setattr(main_module, "tts_engine", TTS())
    monkeypatch.setattr(main_module.storage, "get_setting", lambda _key, default=None: default)
    monkeypatch.setattr(main_module.audio_flow_widget, "set_playing", lambda _playing: None)
    from voice_flow.audio_explainer import audio_explainer
    monkeypatch.setattr(audio_explainer, "transform_for_human_reading", lambda text: text)
    app._is_voice_flow_dictation = lambda _text: True

    app._process_audio_flow_pipeline(text_override="intentionally selected dictation text")

    assert _wait_until(lambda: spoken == ["intentionally selected dictation text"])
    assert not any(state[0] == "error" for state in app.overlay.states)


def test_explanatory_read_prepares_script_off_the_calling_thread(monkeypatch) -> None:
    app = _selection_app(SimpleNamespace(get_selected_text=lambda **_kwargs: ""))
    script_started = threading.Event()
    release_script = threading.Event()
    spoken: list[str] = []

    class TTS:
        def is_speaking(self) -> bool:
            return False

        def speak(self, text, **_callbacks) -> None:
            spoken.append(text)

        def stop(self) -> None:
            pass

    def slow_explanation(text: str) -> str:
        script_started.set()
        assert release_script.wait(1.0)
        return f"Explained: {text}"

    from voice_flow.audio_explainer import audio_explainer
    monkeypatch.setattr(main_module, "tts_engine", TTS())
    monkeypatch.setattr(main_module.storage, "get_setting", lambda _key, default=None: default)
    monkeypatch.setattr(main_module.audio_flow_widget, "hide", lambda: None)
    monkeypatch.setattr(audio_explainer, "transform_for_human_reading", slow_explanation)

    started = time.monotonic()
    app._process_audio_flow_pipeline(text_override="selected source")
    assert time.monotonic() - started < 0.15
    assert script_started.wait(0.5)
    assert spoken == []
    assert ("generating_audio", "Preparing explanation...") in app.overlay.states

    release_script.set()
    assert _wait_until(lambda: spoken == ["Explained: selected source"])


def test_stop_during_explanatory_read_suppresses_stale_tts(monkeypatch) -> None:
    app = _selection_app(SimpleNamespace(get_selected_text=lambda **_kwargs: ""))
    script_started = threading.Event()
    release_script = threading.Event()
    spoken: list[str] = []

    class TTS:
        def is_speaking(self) -> bool:
            return False

        def speak(self, text, **_callbacks) -> None:
            spoken.append(text)

        def stop(self) -> None:
            pass

    def blocked_explanation(text: str) -> str:
        script_started.set()
        assert release_script.wait(1.0)
        return f"Explained: {text}"

    from voice_flow.audio_explainer import audio_explainer
    monkeypatch.setattr(main_module, "tts_engine", TTS())
    monkeypatch.setattr(main_module.storage, "get_setting", lambda _key, default=None: default)
    monkeypatch.setattr(main_module.audio_flow_widget, "hide", lambda: None)
    monkeypatch.setattr(main_module.audio_flow_widget, "set_playing", lambda _playing: None)
    monkeypatch.setattr(audio_explainer, "transform_for_human_reading", blocked_explanation)

    app._process_audio_flow_pipeline(text_override="old selection")
    assert script_started.wait(0.5)
    app._stop_audio_flow_pipeline()
    release_script.set()

    assert _wait_until(lambda: not any(thread.name == "AudioFlowExplanatoryRead" and thread.is_alive() for thread in threading.enumerate()))
    assert spoken == []


def test_explanatory_read_falls_back_to_source_text_after_script_error(monkeypatch) -> None:
    app = _selection_app(SimpleNamespace(get_selected_text=lambda **_kwargs: ""))
    spoken: list[str] = []

    class TTS:
        def is_speaking(self) -> bool:
            return False

        def speak(self, text, **_callbacks) -> None:
            spoken.append(text)

        def stop(self) -> None:
            pass

    def failed_explanation(_text: str) -> str:
        raise RuntimeError("provider unavailable")

    from voice_flow.audio_explainer import audio_explainer
    monkeypatch.setattr(main_module, "tts_engine", TTS())
    monkeypatch.setattr(main_module.storage, "get_setting", lambda _key, default=None: default)
    monkeypatch.setattr(main_module.audio_flow_widget, "hide", lambda: None)
    monkeypatch.setattr(audio_explainer, "transform_for_human_reading", failed_explanation)

    app._process_audio_flow_pipeline(text_override="reliable source text")

    assert _wait_until(lambda: spoken == ["reliable source text"])


def test_stale_tts_callbacks_cannot_replace_newer_read_state(monkeypatch) -> None:
    app = _selection_app(SimpleNamespace(get_selected_text=lambda **_kwargs: ""))
    widget_calls: list[tuple[str, bool]] = []

    class TTS:
        def __init__(self) -> None:
            self.callbacks = []

        def is_speaking(self) -> bool:
            return False

        def speak(self, _text, **callbacks) -> None:
            self.callbacks.append(callbacks)

        def stop(self) -> None:
            pass

    from voice_flow.audio_explainer import audio_explainer
    tts = TTS()
    monkeypatch.setattr(main_module, "tts_engine", tts)
    monkeypatch.setattr(main_module.storage, "get_setting", lambda _key, default=None: default)
    monkeypatch.setattr(main_module.audio_flow_widget, "hide", lambda: widget_calls.append(("hide", True)))
    monkeypatch.setattr(main_module.audio_flow_widget, "set_playing", lambda value: widget_calls.append(("playing", value)))
    monkeypatch.setattr(audio_explainer, "transform_for_human_reading", lambda text: text)

    app._process_audio_flow_pipeline(text_override="first selection")
    assert _wait_until(lambda: len(tts.callbacks) == 1)
    app._process_audio_flow_pipeline(text_override="second selection")
    assert _wait_until(lambda: len(tts.callbacks) == 2)

    tts.callbacks[0]["on_done"]()
    tts.callbacks[0]["on_error"]("late failure")

    assert app.overlay.cleared == 0
    assert not any(state[0] in {"ready", "error"} for state in app.overlay.states)
    assert widget_calls == [("hide", True), ("hide", True)]


def test_depth_selection_hitboxes_and_summarizing_transition() -> None:
    widget = AudioFlowFloatingWidget()
    triggers = []
    widget.on_trigger = lambda text, mode="full", summary_depth=None: triggers.append((text, mode, summary_depth))
    widget._current_text = "test article text"
    widget._is_visible = True

    # 1. Short hitbox: event.x <= 82 -> auto dismisses selection widget
    widget._current_text = "test article text"
    widget._stage = AudioFlowFloatingWidget.STAGE_DEPTH_SELECT
    widget._on_click(SimpleNamespace(x=30))
    assert triggers[-1] == ("test article text", "summary", "short")
    assert widget._is_visible is False

    # 2. Balanced hitbox: 82 < event.x <= 174 -> auto dismisses selection widget
    widget._current_text = "test article text"
    widget._is_visible = True
    widget._stage = AudioFlowFloatingWidget.STAGE_DEPTH_SELECT
    widget._on_click(SimpleNamespace(x=120))
    assert triggers[-1] == ("test article text", "summary", "balanced")
    assert widget._is_visible is False

    # 3. Deep dive hitbox: event.x > 174 -> auto dismisses selection widget
    widget._current_text = "test article text"
    widget._is_visible = True
    widget._stage = AudioFlowFloatingWidget.STAGE_DEPTH_SELECT
    widget._on_click(SimpleNamespace(x=200))
    assert triggers[-1] == ("test article text", "summary", "deep_dive")
    assert widget._is_visible is False


@pytest.mark.parametrize("saved_style", ["single", "podcast"])
def test_audio_summary_pipeline_worker_forwards_saved_summary_style(monkeypatch, saved_style: str) -> None:
    app = _selection_app(SimpleNamespace(get_selected_text=lambda **_kwargs: ""))
    generate_calls = []
    launched_tokens = []
    widget_states = []

    class FakeNotebookLMService:
        def generate(self, text, depth="balanced", *, style="single", cancelled=None, on_progress=None):
            generate_calls.append((text, depth, style))
            return {"audio_path": "/fake/audio.m4a", "depth": depth}

    class FakeTTS:
        def is_speaking(self):
            return False

        def speak(self, text, **kwargs):
            pass

    monkeypatch.setattr(
        main_module.storage,
        "get_setting",
        lambda key, default=None: (
            saved_style if key == "audio_flow_summary_style"
            else default
        ),
    )
    monkeypatch.setattr(main_module, "tts_engine", FakeTTS())
    monkeypatch.setattr(main_module.audio_flow_widget, "show_summarizing", lambda: widget_states.append("summarizing"))
    monkeypatch.setattr(main_module.audio_flow_widget, "set_playing", lambda p: widget_states.append(f"playing_{p}"))

    from voice_flow import audio_notebooklm
    monkeypatch.setattr(audio_notebooklm, "audio_notebooklm_service", FakeNotebookLMService())

    from voice_flow import audio_summary_player
    monkeypatch.setattr(audio_summary_player, "launch_summary_audio_player", lambda path, depth="balanced", **kwargs: (launched_tokens.append(depth) or "tok123"))

    app._process_audio_flow_pipeline(
        text_override="Long document text for summary",
        mode="summary",
        summary_depth="short",
    )

    time.sleep(0.3)  # Allow worker thread to execute
    assert len(generate_calls) == 1
    assert generate_calls[0] == ("Long document text for summary", "short", saved_style)
    assert launched_tokens == ["short"]


def test_summary_export_runs_after_ready_and_failed_copy_does_not_mark_downloaded(
    tmp_path, monkeypatch
) -> None:
    app = _selection_app(SimpleNamespace(get_selected_text=lambda **_kwargs: ""))
    audio_path = tmp_path / "summary.m4a"
    audio_path.write_bytes(b"m4a bytes")
    export_started = threading.Event()
    release_export = threading.Event()
    export_finished = threading.Event()
    events: list[str] = []
    history_updates: list[dict] = []

    class FakeNotebookLMService:
        def generate(self, *_args, **_kwargs):
            return {"audio_path": str(audio_path)}

    class FakeTTS:
        def is_speaking(self):
            return False

        def speak(self, *_args, **_kwargs):
            pass

    def update_history(_history_id, **kwargs):
        history_updates.append(kwargs)

    def blocked_export(*_args, **_kwargs):
        export_started.set()
        try:
            assert release_export.wait(1.0)
            raise OSError("Downloads unavailable")
        finally:
            export_finished.set()

    monkeypatch.setattr(main_module.storage, "get_setting", lambda _key, default=None: default)
    monkeypatch.setattr(main_module.storage, "add_audio_summary_history", lambda **_kwargs: None)
    monkeypatch.setattr(main_module.storage, "update_audio_summary_history", update_history)
    monkeypatch.setattr(main_module.storage, "record_audio_summary_to_history", lambda **_kwargs: events.append("history"))
    monkeypatch.setattr(main_module, "tts_engine", FakeTTS())
    monkeypatch.setattr(main_module.audio_flow_widget, "show_summarizing", lambda: None)
    monkeypatch.setattr(main_module.audio_flow_widget, "set_playing", lambda _playing: None)
    monkeypatch.setattr(main_module.audio_flow_widget, "hide", lambda: None)
    monkeypatch.setattr(app.overlay, "show_ready", lambda: events.append("ready"))

    from voice_flow import audio_notebooklm, audio_summary_player
    monkeypatch.setattr(audio_notebooklm, "audio_notebooklm_service", FakeNotebookLMService())
    monkeypatch.setattr(audio_summary_player, "close_summary_audio_player", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        audio_summary_player,
        "launch_summary_audio_player",
        lambda *_args, **_kwargs: (events.append("player") or "player-token"),
    )
    monkeypatch.setattr(audio_summary_player, "save_media_to_downloads", blocked_export)

    try:
        app._process_audio_flow_pipeline(
            text_override="Long document text for summary",
            mode="summary",
            summary_depth="short",
        )
        assert export_started.wait(1.0), (events, app.overlay.states, history_updates)
        assert events == ["player", "history", "ready"]
        assert not any(update.get("downloaded") == 1 for update in history_updates)
    finally:
        release_export.set()
        assert export_finished.wait(1.0)

    assert not any(update.get("downloaded") == 1 for update in history_updates)


def test_audio_summary_pipeline_worker_handles_tts_error_safely(monkeypatch) -> None:
    app = _selection_app(SimpleNamespace(get_selected_text=lambda **_kwargs: ""))
    widget_resets = []

    class BrokenNotebookLMService:
        def generate(self, text, depth="balanced", *, style="single", cancelled=None, on_progress=None):
            raise RuntimeError("NotebookLM connection failed")

    class FakeTTS:
        def is_speaking(self):
            return False

        def speak(self, text, **kwargs):
            pass

    monkeypatch.setattr(main_module.storage, "get_setting", lambda _key, default=None: default)
    monkeypatch.setattr(main_module, "tts_engine", FakeTTS())
    monkeypatch.setattr(main_module.audio_flow_widget, "show_summarizing", lambda: None)
    monkeypatch.setattr(main_module.audio_flow_widget, "set_playing", lambda p: widget_resets.append(p))

    from voice_flow import audio_notebooklm
    monkeypatch.setattr(audio_notebooklm, "audio_notebooklm_service", BrokenNotebookLMService())

    app._process_audio_flow_pipeline(
        text_override="Text to summarize",
        mode="summary",
        summary_depth="balanced",
    )

    time.sleep(0.3)  # Allow worker thread to execute
    assert widget_resets == [False]
    assert any(s[0] == "error" and "NotebookLM" in str(s[1]) for s in app.overlay.states)


def test_mouse_release_never_invalidates_audio_summary_generation(monkeypatch) -> None:
    app = _selection_app(SimpleNamespace(get_selected_text_strict=lambda **_kwargs: ""))
    app._audio_summary_generation = 42
    monkeypatch.setattr(main_module.storage, "get_setting", lambda _key, default=None: default)
    monkeypatch.setattr(main_module.audio_flow_widget, "hide", lambda: None)
    monkeypatch.setattr(
        main_module.ctypes,
        "windll",
        SimpleNamespace(user32=SimpleNamespace(IsWindow=lambda _hwnd: False, GetForegroundWindow=lambda: 1)),
    )

    # Trigger click release
    app._on_mouse_release(100, 100, drag_distance=0.0)
    assert app._audio_summary_generation == 42, "Mouse click must not touch _audio_summary_generation"

    # Trigger drag release
    app._on_mouse_release(200, 200, drag_distance=20.0)
    time.sleep(0.05)
    assert app._audio_summary_generation == 42, "Mouse drag must not touch _audio_summary_generation"


def test_pipeline_on_done_and_on_error_close_widget_for_the_current_generation(monkeypatch) -> None:
    app = _selection_app(SimpleNamespace(get_selected_text=lambda **_kwargs: ""))
    widget_calls = []

    monkeypatch.setattr(main_module.audio_flow_widget, "set_playing", lambda p: widget_calls.append(("set_playing", p)))
    monkeypatch.setattr(main_module.audio_flow_widget, "hide", lambda: widget_calls.append(("hide", True)))
    monkeypatch.setattr(main_module.storage, "get_setting", lambda _key, default=None: default)
    app._is_voice_flow_dictation = lambda _text: False

    class TTS:
        def __init__(self) -> None:
            self.callbacks = None
        def is_speaking(self) -> bool:
            return False
        def speak(self, _text, *, on_start, on_done, on_error) -> None:
            self.callbacks = (on_start, on_done, on_error)
        def stop(self) -> None:
            pass

    tts = TTS()
    monkeypatch.setattr(main_module, "tts_engine", tts)
    from voice_flow.audio_explainer import audio_explainer
    monkeypatch.setattr(audio_explainer, "transform_for_human_reading", lambda text: text)

    app._process_audio_flow_pipeline(text_override="testing close")
    assert _wait_until(lambda: tts.callbacks is not None)
    _on_start, _on_done, _on_error = tts.callbacks

    # The active TTS callbacks close the widget and clear the overlay.
    widget_calls.clear()
    _on_done()
    assert ("set_playing", False) in widget_calls
    assert ("hide", True) in widget_calls
    assert app.overlay.cleared > 0
    assert any(s[0] == "ready" for s in app.overlay.states)

    # The active error callback follows the same completion cleanup.
    widget_calls.clear()
    _on_error("custom playback failure")
    assert ("set_playing", False) in widget_calls
    assert ("hide", True) in widget_calls
    assert any(s[0] == "error" and "Audio Flow: custom playback failure" in str(s[1]) for s in app.overlay.states)


def test_widget_set_playing_false_unconditionally_hides_despite_generation_change() -> None:
    widget = AudioFlowFloatingWidget()
    withdrawn = []

    class Win:
        def withdraw(self) -> None:
            withdrawn.append(True)
        def update(self) -> None:
            pass

    class Root:
        def after(self, _delay: int, callback) -> None:
            callback()

    widget.root = Root()
    widget.win = Win()
    widget._is_visible = True
    widget._is_playing = True
    widget._stage = AudioFlowFloatingWidget.STAGE_PLAYBACK_CONTROL
    widget._show_generation = 1

    # Simulate generation bump while playing (e.g. text selection elsewhere)
    widget._show_generation = 99

    # Calling set_playing(False) must unconditionally reset state and withdraw window
    widget.set_playing(False)

    assert widget._is_playing is False
    assert widget._is_paused is False
    assert widget._stage == AudioFlowFloatingWidget.STAGE_MINIMAL
    assert widget._is_visible is False
    assert withdrawn == [True]


def test_widget_hide_on_playback_completion_withdraws_immediately() -> None:
    widget = AudioFlowFloatingWidget()
    withdrawn = []

    class Win:
        def withdraw(self) -> None:
            withdrawn.append(True)

    class Root:
        def after(self, _delay: int, callback) -> None:
            callback()

    widget.root = Root()
    widget.win = Win()
    widget._is_visible = True
    widget._is_playing = False
    widget._show_generation = 5

    # Newer generation mismatch
    widget._show_generation = 10

    # hide() due to completed playback must withdraw immediately
    widget.hide()

    assert widget._is_visible is False
    assert withdrawn == [True]

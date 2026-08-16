from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from voice_flow import main as main_module
from voice_flow.audio_flow_widget import AudioFlowFloatingWidget
from voice_flow.main import DictationState, VoiceFlowApp


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

    def show_generating_audio(self) -> None:
        self.states.append(("generating_audio", None))

    def show_summarizing(self, mode: str = "") -> None:
        self.states.append(("summarizing", mode))


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
    app._is_voice_flow_dictation = lambda _text: False

    app._process_audio_flow_pipeline(text_override="selected text")
    assert tts.callbacks is not None
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
    app._is_voice_flow_dictation = lambda _text: True

    app._process_audio_flow_pipeline(text_override="intentionally selected dictation text")

    assert spoken == ["intentionally selected dictation text"]
    assert not any(state[0] == "error" for state in app.overlay.states)
from __future__ import annotations

from voice_flow.overlay import FloatingOverlayBar, _safe_done_label


class RecordingCanvas:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def _record(self, name: str, *args: object, **kwargs: object) -> None:
        self.calls.append((name, args, kwargs))

    def delete(self, *args: object, **kwargs: object) -> None:
        self._record("delete", *args, **kwargs)

    def create_line(self, *args: object, **kwargs: object) -> None:
        self._record("create_line", *args, **kwargs)

    def create_oval(self, *args: object, **kwargs: object) -> None:
        self._record("create_oval", *args, **kwargs)

    def create_polygon(self, *args: object, **kwargs: object) -> None:
        self._record("create_polygon", *args, **kwargs)

    def create_rectangle(self, *args: object, **kwargs: object) -> None:
        self._record("create_rectangle", *args, **kwargs)

    def create_text(self, *args: object, **kwargs: object) -> None:
        self._record("create_text", *args, **kwargs)


def _render(bar: FloatingOverlayBar) -> RecordingCanvas:
    canvas = RecordingCanvas()
    bar.canvas = canvas
    bar._draw()
    return canvas


def _text_calls(canvas: RecordingCanvas) -> list[dict[str, object]]:
    return [kwargs for name, _args, kwargs in canvas.calls if name == "create_text"]


def test_idle_bar_stays_thin_and_has_no_label() -> None:
    bar = FloatingOverlayBar()
    bar.state = "READY"

    canvas = _render(bar)

    assert (bar.width, bar.height) == (bar.idle_width, bar.idle_height)
    assert _text_calls(canvas) == []


def test_hover_actions_use_orange_and_white() -> None:
    bar = FloatingOverlayBar()
    bar.state = "READY"
    bar._is_mouse_over = True
    bar._hover_zone = "speak"

    canvas = _render(bar)
    text_by_label = {call["text"]: call for call in _text_calls(canvas)}

    assert text_by_label["Click to speak"]["fill"] == bar.ACCENT_ORANGE
    assert text_by_label["⋯ Video"]["fill"] == bar.TEXT_WHITE


def test_active_flow_states_use_the_requested_labels() -> None:
    cases = [
        ("PROCESSING", "", "Transcribing"),
        ("READING", "", "Audio Flow"),
        ("READY", "processing", "Video Flow"),
    ]

    for state, video_status, expected_label in cases:
        bar = FloatingOverlayBar()
        bar.state = state
        bar.video_status = video_status

        canvas = _render(bar)

        labels = [call["text"] for call in _text_calls(canvas)]
        assert expected_label in labels


def test_error_bar_uses_neutral_working_copy_without_decorative_lines() -> None:
    bar = FloatingOverlayBar()
    bar.state = "ERROR"
    bar.error_message = "Danger: microphone hardware failed to open"

    canvas = _render(bar)

    text_calls = _text_calls(canvas)
    assert [call["text"] for call in text_calls] == ["Working"]
    assert text_calls[0]["fill"] == bar.TEXT_WHITE
    assert not any(name == "create_line" for name, _args, _kwargs in canvas.calls)


def test_done_bar_renders_safe_fixed_outcome_only() -> None:
    bar = FloatingOverlayBar()
    bar.state = "DONE"
    # The caller's full text may contain dictation after a colon; it must not
    # be rendered in the overlay.
    bar.done_label = _safe_done_label("AI polished — Email / Professional")

    canvas = _render(bar)

    labels = [call["text"] for call in _text_calls(canvas)]
    assert "AI polished" in labels
    assert "Email / Professional" not in labels
    assert "I will arrive at five" not in labels
    assert _safe_done_label("AI polished: I will arrive at five") == "AI polished"
    assert _safe_done_label("AI polished — Email / Professional") == "AI polished"


def test_local_fallback_error_renders_safe_outcome_without_error_text() -> None:
    bar = FloatingOverlayBar()
    bar.state = "ERROR"
    bar.error_message = "Cleaned locally: private dictated words"
    bar.done_label = _safe_done_label(bar.error_message)

    canvas = _render(bar)

    labels = [call["text"] for call in _text_calls(canvas)]
    assert labels == ["Cleaned locally"]


def test_voice_completion_feedback_stays_readable_and_cannot_reset_new_recording():
    from types import SimpleNamespace
    bar = FloatingOverlayBar()
    timers = []
    bar.win = object()
    bar.root = SimpleNamespace(after=lambda delay, callback: timers.append((delay, callback)))
    bar._run_on_ui = lambda callback: callback()
    bar._bring_to_top = lambda: None
    bar._draw = lambda: None
    bar._animate = lambda generation: None
    bar.show_done("AI polished")
    assert bar.state == "DONE" and bar.done_label == "AI polished"
    assert timers[-1][0] >= 4000
    stale = timers[-1][1]
    bar.state = "RECORDING"
    bar._animation_generation += 1
    stale()
    assert bar.state == "RECORDING"
    bar.show_error("Cleaned locally")
    assert timers[-1][0] >= 5000

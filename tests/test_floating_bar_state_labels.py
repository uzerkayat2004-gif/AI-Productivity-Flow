from __future__ import annotations

from voice_flow.overlay import FloatingOverlayBar


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

from __future__ import annotations

from voice_flow.overlay import FloatingOverlayBar


class _Canvas:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.fills: list[str] = []
        self.lines: list[tuple[object, ...]] = []

    def create_text(self, *args, **kwargs):
        text = kwargs.get("text")
        if text is not None:
            self.texts.append(str(text))
        fill = kwargs.get("fill")
        if fill is not None:
            self.fills.append(str(fill).lower())

    def create_rectangle(self, *args, **kwargs):
        fill = kwargs.get("fill")
        if fill is not None:
            self.fills.append(str(fill).lower())

    def create_oval(self, *args, **kwargs):
        fill = kwargs.get("fill")
        if fill is not None:
            self.fills.append(str(fill).lower())

    def create_polygon(self, *args, **kwargs):
        fill = kwargs.get("fill")
        if fill is not None:
            self.fills.append(str(fill).lower())

    def create_line(self, *args, **kwargs):
        self.lines.append(args)
        fill = kwargs.get("fill")
        if fill is not None:
            self.fills.append(str(fill).lower())


def _bar_with_canvas() -> tuple[FloatingOverlayBar, _Canvas]:
    bar = FloatingOverlayBar()
    canvas = _Canvas()
    bar.canvas = canvas
    return bar, canvas


def test_audio_and_video_active_states_use_product_labels() -> None:
    bar, canvas = _bar_with_canvas()
    bar._draw_reading(240, 32)
    assert any("Audio Flow" in text for text in canvas.texts)

    canvas.texts.clear()
    bar.video_status = "processing"
    bar._draw_video_status(294, 32, compact=False)
    assert any("Video Flow" in text for text in canvas.texts)


def test_working_state_does_not_expose_error_copy_or_decorative_lines() -> None:
    bar, canvas = _bar_with_canvas()
    bar.error_message = "Dangerous provider failure"
    bar._draw_error(180, 32)
    assert canvas.texts == ["Working"]
    assert canvas.lines == []


def test_hover_bar_uses_the_orange_product_accent() -> None:
    bar, canvas = _bar_with_canvas()
    bar.state = "READY"
    bar._is_mouse_over = True
    bar.width = bar.ready_actions_width
    bar._hover_zone = "video_flow"
    bar._draw_ready(bar.width, bar.hover_height)
    assert any(color in {"#ff6b00", "#ff6b19"} for color in canvas.fills)

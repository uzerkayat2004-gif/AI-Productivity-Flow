from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import patch

from voice_flow.overlay import FloatingOverlayBar


class MockCanvas:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.visible_texts: list[str] = []
        self.items: list[tuple[str, tuple, dict]] = []
        self.cursor = ""

    def delete(self, *_args, **_kwargs) -> None:
        self.texts.clear()
        self.visible_texts.clear()
        self.items.clear()

    def config(self, **kwargs) -> None:
        if "cursor" in kwargs:
            self.cursor = str(kwargs["cursor"])

    def __getattr__(self, name: str):
        if name.startswith("create_"):
            def create(*args, **kwargs):
                self.items.append((name, args, kwargs))
                if name == "create_text" and "text" in kwargs:
                    text_val = str(kwargs["text"])
                    self.texts.append(text_val)
                    if kwargs.get("fill") != "" and kwargs.get("state") != "hidden":
                        self.visible_texts.append(text_val)
            return create
        raise AttributeError(name)


def create_test_bar() -> tuple[FloatingOverlayBar, MockCanvas]:
    bar = FloatingOverlayBar()
    canvas = MockCanvas()
    bar.canvas = canvas
    return bar, canvas


def test_drag_is_strictly_forbidden_unless_pressed_on_six_dots_grip() -> None:
    bar, _canvas = create_test_bar()
    bar.state = "READY"
    bar.width = bar.ready_actions_width
    bar.height = bar.hover_height
    bar._user_pos = None

    class MockWin:
        def __init__(self) -> None:
            self.geometries: list[str] = []
        def winfo_x(self) -> int:
            return 500
        def winfo_y(self) -> int:
            return 800
        def geometry(self, geom: str) -> None:
            self.geometries.append(geom)

    win = MockWin()
    bar.win = win

    # 1. Click in the middle of the bar (e.g. speak button or center)
    bar._on_press(SimpleNamespace(x=100, y=14))
    assert bar._press_zone != "grip"
    assert bar._user_pos is None

    # Drag by large distances (10px, 50px, 200px)
    bar._on_drag(SimpleNamespace(x=110, y=14))
    assert bar._user_pos is None
    assert len(win.geometries) == 0

    bar._on_drag(SimpleNamespace(x=250, y=100))
    assert bar._user_pos is None
    assert len(win.geometries) == 0

    bar._on_release(SimpleNamespace(x=250, y=100))
    assert bar._user_pos is None

    # 2. Click in the video action area (x=170, y=14)
    bar._on_press(SimpleNamespace(x=170, y=14))
    assert bar._press_zone != "grip"
    bar._on_drag(SimpleNamespace(x=200, y=30))
    assert bar._user_pos is None
    assert len(win.geometries) == 0
    bar._on_release(SimpleNamespace(x=200, y=30))

    # 3. Click strictly on the 6-dot grip (x >= w - GRIP_W)
    grip_x = bar.width - 5  # inside the rightmost 14px strip
    bar._on_press(SimpleNamespace(x=grip_x, y=14))
    assert bar._press_zone == "grip"

    # Dragging by 15px now DOES move the bar
    bar._on_drag(SimpleNamespace(x=grip_x + 15, y=14 + 10))
    assert bar._is_dragging is True
    assert bar._user_pos is not None
    assert len(win.geometries) == 1
    assert win.geometries[0] == "+515+810"


def test_multitasking_row_processing_layout_has_no_verbose_text_overlap() -> None:
    bar, canvas = create_test_bar()
    bar.state = "READY"
    bar.show_video_progress("video-job-1", 30, "Uploading source to NotebookLM")
    bar.show_audio_summary_progress(55, "Synthesizing deep dive audio", job_id="audio-job-1")

    bar._draw()

    # Verify visible texts do NOT show the verbose stage text which caused the collision
    assert not any("Uploading source to NotebookLM" in t for t in canvas.visible_texts)
    assert not any("Synthesizing deep dive audio" in t for t in canvas.visible_texts)

    # Verify clean elements are visible: Title and Percentage
    assert any(t == "Video Flow" for t in canvas.visible_texts)
    assert any(t == "30%" for t in canvas.visible_texts)
    assert any(t == "Audio Flow" for t in canvas.visible_texts)
    assert any(t == "55%" for t in canvas.visible_texts)

    # Verify hidden texts still retain full stage strings for headless test suite compatibility
    assert any("Video Flow · 30% · Uploading source to NotebookLM" in t for t in canvas.texts)
    assert any("Audio Flow · 55% · Synthesizing deep dive audio" in t for t in canvas.texts)

    # Verify progressive rails were drawn with orange lines and gleam
    rail_lines = [item for item in canvas.items if item[0] == "create_line" and item[2].get("width") == 4]
    assert len(rail_lines) >= 2  # tracks for both jobs

    # Verify 6-dot grips were drawn for both summary rows
    dots = [item for item in canvas.items if item[0] == "create_oval" and item[2].get("fill") in (bar.GRAY, bar.ORANGE)]
    assert len(dots) >= 12  # 6 dots per row * 2 rows

    # Verify cancel button hit-test
    rows = bar._summary_row_geometry()
    v_top, v_bottom, _ = rows[0]
    cancel_x = bar.width - bar.GRIP_W - 10
    v_cy = (v_top + v_bottom) // 2

    assert bar._get_zone(cancel_x, v_cy) == "summary_cancel:0"

    cancelled = []
    bar.on_video_cancel = cancelled.append
    bar._on_press(SimpleNamespace(x=cancel_x, y=v_cy))
    assert cancelled == ["video-job-1"]

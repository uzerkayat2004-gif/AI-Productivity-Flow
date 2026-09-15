"""Headless smoke checks for the Flow Bar rest pill, grip strip, and redraw throttle.

Instantiates FloatingOverlayBar with a recording fake canvas (no Tk required),
mirroring the pattern used by the other floating-bar tests.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

from voice_flow.overlay import FloatingOverlayBar


class SmokeCanvas:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.cursor = ""

    def _record(self, name: str, *args: object, **kwargs: object) -> None:
        self.calls.append((name, {k: v for k, v in kwargs.items() if k == "fill"} | {"args": args}))

    def config(self, **kwargs: object) -> None:
        if "cursor" in kwargs:
            self.cursor = str(kwargs["cursor"])

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

    @property
    def fills(self) -> list[str]:
        return [str(kw.get("fill")).lower() for _name, kw in self.calls if kw.get("fill")]


def _rest_bar() -> tuple[FloatingOverlayBar, SmokeCanvas]:
    bar = FloatingOverlayBar()
    bar.state = "READY"
    canvas = SmokeCanvas()
    bar.canvas = canvas
    return bar, canvas


def test_rest_draw_is_dark_pill_without_white() -> None:
    bar, canvas = _rest_bar()

    bar._draw()

    assert bar.BG_REST.lower() in canvas.fills  # #17171C dark fill present
    assert "#ffffff" not in canvas.fills
    assert bar.ORANGE_SOFT.lower() not in canvas.fills  # no rest accent dot
    assert bar.GRIP_REST.lower() not in canvas.fills  # no visible grip at rest  # no white anywhere at rest
    assert bar.BORDER_REST.lower() in canvas.fills  # 1px dark border
    # Fully quiet rest: no accents, no grip marks — only the dark shell.
    assert not any(name == "create_text" for name, _kw in canvas.calls)  # fully static rest pill
    assert (bar.width, bar.height) == (48, 10)


def test_hover_enter_draws_interactive_and_leave_returns_to_rest() -> None:
    bar, canvas = _rest_bar()
    bar._draw()  # start from the dark rest pill
    assert bar.BG_REST.lower() in canvas.fills

    canvas.calls.clear()
    bar._on_motion(SimpleNamespace(x=5, y=5))  # mouse enters
    assert "#ffffff" in canvas.fills
    assert bar.BG_REST.lower() not in canvas.fills
    assert bar._is_mouse_over is True
    assert (bar.width, bar.height) == (bar.ready_actions_width, bar.hover_height)

    canvas.calls.clear()
    bar._on_leave(SimpleNamespace(x=0, y=0))  # mouse leaves, no feature active
    assert bar.BG_REST.lower() in canvas.fills
    assert "#ffffff" not in canvas.fills
    assert (bar.width, bar.height) == (48, 10)


def test_grip_zone_is_last_14px_at_any_width() -> None:
    for width in (56, 250):
        bar = FloatingOverlayBar()
        bar.state = "READY"
        bar.width = width  # no draw yet: hit-testing falls back to current width
        assert bar._get_zone(width - 14) == "grip"
        assert bar._get_zone(width - 1) == "grip"
        assert bar._get_zone(width - 15) != "grip"

    # Once drawn, the grip must be computed from the LAST DRAWN width even if
    # self.width drifted (no stale constants).
    bar = FloatingOverlayBar()
    bar.state = "READY"
    bar.width = 250
    bar._last_drawn_width = 56
    assert bar._get_zone(42) == "grip"  # 56 - 14
    assert bar._get_zone(41) != "grip"


def test_redraw_throttle_skips_no_change_frame_within_40ms() -> None:
    bar, canvas = _rest_bar()
    bar._draw()
    drawn = len(canvas.calls)
    assert drawn > 0

    bar._last_draw_at = time.monotonic()  # simulate an immediately following frame
    bar._draw()
    assert len(canvas.calls) == drawn  # second no-change draw skipped

    # A meaningful change still forces a frame even inside the window.
    bar._last_draw_at = time.monotonic()
    bar._is_mouse_over = True
    bar._hover_zone = "speak"
    bar._draw()
    assert len(canvas.calls) > drawn

    # And after the window expires, identical frames draw again.
    bar._last_draw_at = time.monotonic() - 0.05
    bar._draw()
    assert len(canvas.calls) > 0


class _FakeRoot:
    def winfo_screenwidth(self) -> int:
        return 1920

    def winfo_screenheight(self) -> int:
        return 1080


class _FakeWin:
    def __init__(self) -> None:
        self.geometry_calls: list[str] = []

    def geometry(self, value: str) -> None:
        self.geometry_calls.append(value)

    def winfo_exists(self) -> bool:
        return True

    def after(self, _ms: int, _fn) -> None:
        return None


def _bar_with_window() -> FloatingOverlayBar:
    bar = FloatingOverlayBar()
    bar.root = _FakeRoot()
    bar.win = _FakeWin()
    bar.canvas = SmokeCanvas()
    return bar


def test_drag_position_persists_across_resizes() -> None:
    """A dragged bar must maintain its anchor position across resizes."""
    bar = _bar_with_window()
    bar._user_pos = (700, 500)
    bar._set_bar_size(240, 84)
    geo = bar.win.geometry_calls[-1]
    assert "+580+416" in geo  # 700 - 240/2 = 580, 500 - 84 = 416


def test_dock_position_used_when_no_user_pos() -> None:
    bar = _bar_with_window()
    bar._position_window()
    geo = bar.win.geometry_calls[-1]
    assert "+700+" not in geo  # docked bottom-center, not a stale user pos


def test_resume_resets_user_position_to_default() -> None:
    bar = _bar_with_window()
    bar._user_pos = (100, 100)
    bar.set_dock("bottom")
    assert bar._user_pos is None  # explicit dock change resets
    bar._user_pos = (100, 100)
    bar._handle_resume()  # system woke from sleep
    assert bar._user_pos is None
    assert "+100+100" not in bar.win.geometry_calls[-1]

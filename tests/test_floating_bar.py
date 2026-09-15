"""Unit and integration tests for FloatingOverlayBar window management, lifecycle, and recovery."""

from __future__ import annotations

from unittest.mock import patch

from voice_flow.config import config
from voice_flow.overlay import FloatingOverlayBar, _enable_dpi_awareness


class MockCanvas:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.cursor = ""

    def _record(self, name: str, *args: object, **kwargs: object) -> None:
        self.calls.append((name, {k: v for k, v in kwargs.items()} | {"args": args}))

    def config(self, **kwargs: object) -> None:
        if "cursor" in kwargs:
            self.cursor = str(kwargs["cursor"])

    def pack(self, **kwargs: object) -> None:
        pass

    def bind(self, *args: object) -> None:
        pass

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


class MockWindow:
    def __init__(self) -> None:
        self.geometry_calls: list[str] = []
        self.deiconify_called = False
        self.lift_called = False
        self.attributes_calls: list[tuple[object, ...]] = []
        self.withdrawn = False
        self.config_calls: list[dict[str, object]] = []

    def geometry(self, value: str) -> None:
        self.geometry_calls.append(value)

    def winfo_exists(self) -> bool:
        return True

    def winfo_x(self) -> int:
        return 100

    def winfo_y(self) -> int:
        return 200

    def winfo_rootx(self) -> int:
        return 100

    def winfo_rooty(self) -> int:
        return 200

    def winfo_id(self) -> int:
        return 12345

    def deiconify(self) -> None:
        self.deiconify_called = True
        self.withdrawn = False

    def withdraw(self) -> None:
        self.withdrawn = True

    def overrideredirect(self, *args: object) -> None:
        pass

    def lift(self) -> None:
        self.lift_called = True

    def attributes(self, *args: object) -> None:
        self.attributes_calls.append(args)

    def config(self, **kwargs: object) -> None:
        self.config_calls.append(kwargs)

    def bind(self, *args: object) -> None:
        pass

    def unbind(self, *args: object) -> None:
        pass

    def update_idletasks(self) -> None:
        pass

    def after(self, ms: int, fn) -> None:
        pass


class MockRoot:
    def __init__(self, screen_w: int = 1920, screen_h: int = 1080) -> None:
        self._w = screen_w
        self._h = screen_h

    def winfo_screenwidth(self) -> int:
        return self._w

    def winfo_screenheight(self) -> int:
        return self._h

    def after(self, ms: int, fn) -> None:
        fn()

    def mainloop(self) -> None:
        pass


def _create_mock_bar() -> FloatingOverlayBar:
    bar = FloatingOverlayBar()
    bar.root = MockRoot()
    bar.win = MockWindow()
    bar.canvas = MockCanvas()
    return bar


def test_dpi_awareness_function_runs_safely() -> None:
    # Should execute without raising exceptions regardless of platform
    _enable_dpi_awareness()


def test_create_window_sets_attributes_and_draws() -> None:
    bar = FloatingOverlayBar()
    root = MockRoot()
    bar.root = root

    with patch("tkinter.Toplevel") as mock_top, patch("tkinter.Canvas") as mock_cv:
        fake_top = MockWindow()
        fake_canvas = MockCanvas()
        mock_top.return_value = fake_top
        mock_cv.return_value = fake_canvas

        bar._create_window()

        assert bar.win is fake_top
        assert fake_top.deiconify_called is True
        assert fake_top.lift_called is True
        assert ("-topmost", True) in fake_top.attributes_calls
        # Initial draw took place
        assert len(fake_canvas.calls) > 0


def test_position_window_default_bottom_center() -> None:
    bar = _create_mock_bar()
    bar.width = 48
    bar.height = 10
    bar.dock = "bottom"
    bar._user_pos = None

    bar._position_window()

    expected_x = (1920 - 48) // 2  # 936
    expected_y = 1080 - 10 - config.bar_bottom_margin
    assert bar.win.geometry_calls[-1] == f"48x10+{expected_x}+{expected_y}"


def test_position_window_dock_left_and_right() -> None:
    bar = _create_mock_bar()
    bar.width = 48
    bar.height = 10

    bar.dock = "left"
    bar._position_window()
    assert bar.win.geometry_calls[-1] == f"48x10+8+{(1080 - 10) // 2}"

    bar.dock = "right"
    bar._position_window()
    assert bar.win.geometry_calls[-1] == f"48x10+{1920 - 48 - 8}+{(1080 - 10) // 2}"


def test_show_recovers_from_hidden_and_brings_to_top() -> None:
    bar = _create_mock_bar()
    bar.state = "HIDDEN"
    bar.visible = False
    bar.win.withdrawn = True

    bar.show()

    assert bar.visible is True
    assert bar.state == "READY"
    assert bar.win.deiconify_called is True
    assert bar.win.lift_called is True
    assert ("-topmost", True) in bar.win.attributes_calls
    # Rest pill rendered
    assert bar.BG_REST.lower() in bar.canvas.fills


def test_show_recovers_offscreen_position() -> None:
    bar = _create_mock_bar()
    # Simulate offscreen user position (e.g. disconnected second monitor)
    bar._user_pos = (99999, 99999)

    bar.show()

    # Offscreen user position is cleared back to visible dock
    assert bar._user_pos is None
    expected_x = (1920 - bar.width) // 2
    assert f"+{expected_x}+" in bar.win.geometry_calls[-1]


def test_reset_position_snaps_back_to_dock_and_lifts() -> None:
    bar = _create_mock_bar()
    bar._user_pos = (500, 300)

    bar.reset_position()

    assert bar._user_pos is None
    expected_x = (1920 - bar.width) // 2
    assert f"+{expected_x}+" in bar.win.geometry_calls[-1]
    assert bar.win.lift_called is True
    assert ("-topmost", True) in bar.win.attributes_calls


def test_multi_monitor_bounds_and_clamping() -> None:
    bar = _create_mock_bar()

    # Mock virtual multi-monitor bounds spanning [-1920, 0] to [1920, 1080]
    with patch.object(bar, "_get_screen_bounds", return_value=(-1920, 0, 1920, 1080)):
        assert bar._is_offscreen(-3000, 500) is True
        assert bar._is_offscreen(2500, 500) is True
        assert bar._is_offscreen(0, 500) is False
        assert bar._is_offscreen(-1000, 500) is False

        # Clamping within virtual desktop
        cx, cy = bar._clamp_to_screen(-1000, 500)
        assert cx == -1000
        assert cy == 500

        # Clamping outside virtual desktop
        cx, cy = bar._clamp_to_screen(-5000, -100)
        assert cx == -1920
        assert cy == 0


def test_all_state_transitions_ensure_topmost_and_visible() -> None:
    bar = _create_mock_bar()

    states = [
        ("show_ready", lambda: bar.show_ready()),
        ("show_recording", lambda: bar.show_recording()),
        ("show_processing", lambda: bar.show_processing()),
        ("show_done", lambda: bar.show_done("done text")),
        ("show_error", lambda: bar.show_error("err msg")),
        ("show_reading", lambda: bar.show_reading("sample")),
        ("show_summarizing", lambda: bar.show_summarizing("sample")),
        ("show_generating_audio", lambda: bar.show_generating_audio("sample")),
    ]

    for name, trigger in states:
        bar.win.deiconify_called = False
        bar.win.lift_called = False
        trigger()
        assert bar.win.deiconify_called is True, f"{name} failed to call deiconify"
        assert bar.win.lift_called is True, f"{name} failed to call lift"
        assert ("-topmost", True) in bar.win.attributes_calls, f"{name} failed to set topmost"


def test_concentric_anchor_keeps_all_states_centered_and_stacked() -> None:
    bar = _create_mock_bar()
    # Simulate user dragging bar to anchor at center 1000, bottom 800
    bar._user_pos = (1000, 800)

    # 1. Resting state: 48x10 -> left = 1000 - 24 = 976, top = 800 - 10 = 790
    bar._position_window()
    assert bar.win.geometry_calls[-1] == "48x10+976+790"

    # 2. Expanded READY state: 248x28 -> left = 1000 - 124 = 876, top = 800 - 28 = 772
    bar._set_bar_size(248, 28)
    assert bar.win.geometry_calls[-1] == "248x28+876+772"

    # 3. READING state: 272x28 -> left = 1000 - 136 = 864, top = 800 - 28 = 772
    bar._set_bar_size(272, 28)
    assert bar.win.geometry_calls[-1] == "272x28+864+772"

    # 4. RECORDING state: 192x28 -> left = 1000 - 96 = 904, top = 800 - 28 = 772
    bar._set_bar_size(192, 28)
    assert bar.win.geometry_calls[-1] == "192x28+904+772"

    # All states share the EXACT same center (1000) and bottom anchor (800)


def test_proximity_hover_detection_expands_and_collapses_smoothly() -> None:
    bar = _create_mock_bar()
    bar.state = "READY"
    bar._is_mouse_over = False
    bar._set_bar_size(48, 10)

    # Mock window position at (976, 790), size 48x10 (center 1000, bottom 800)
    with patch.object(bar.win, "winfo_rootx", return_value=976), \
         patch.object(bar.win, "winfo_rooty", return_value=790):

        # Cursor 20px above the rest pill (near anchor) -> expands
        with patch("voice_flow.overlay._get_cursor_pos", return_value=(1000, 770)):
            bar._proximity_poll()
            assert bar._is_mouse_over is True

        # Cursor inside expanded bounds -> keeps active
        with patch("voice_flow.overlay._get_cursor_pos", return_value=(950, 780)):
            bar._proximity_poll()
            assert bar._is_mouse_over is True

        # Cursor moved far away (x=500, y=500) -> collapses back
        with patch("voice_flow.overlay._get_cursor_pos", return_value=(500, 500)):
            bar._proximity_poll()
            assert bar._is_mouse_over is False


def test_clicks_do_not_trigger_accidental_drag_or_shift_position() -> None:
    from types import SimpleNamespace
    bar = _create_mock_bar()
    bar.state = "READY"
    bar.width = bar.ready_actions_width
    bar._user_pos = None  # docked

    # User clicks on speak button (x=50, y=14)
    bar._on_press(SimpleNamespace(x=50, y=14))
    assert bar._user_pos is None  # not dragged

    # Micro-jitter of 2px during mouse click
    bar._on_drag(SimpleNamespace(x=52, y=15))
    assert bar._user_pos is None  # still not dragged, stayed docked

    # Dedicated grip drag DOES set user position
    bar._on_press(SimpleNamespace(x=bar.width - 5, y=5))
    bar._on_drag(SimpleNamespace(x=bar.width - 5 + 10, y=5 + 10))
    assert bar._user_pos is not None  # dragged via grip


def test_rest_pill_and_recording_click_zones_trigger_dictation_flow() -> None:
    from types import SimpleNamespace
    bar = _create_mock_bar()
    bar.state = "READY"
    bar.width = bar.idle_width  # 48px rest pill
    bar._is_mouse_over = False

    # Clicking on rest pill MUST return speak (start dictation), not settings
    assert bar._get_zone(20) == "speak"

    start_clicks = []
    bar.on_start_click = lambda: start_clicks.append(True)
    bar._on_press(SimpleNamespace(x=20, y=5))
    assert start_clicks == [True]

    # In RECORDING state, clicking on the bar MUST return finish to stop and paste
    bar.state = "RECORDING"
    bar.width = 192
    assert bar._get_zone(100) == "finish"
    assert bar._get_zone(15) == "cancel"

    finish_clicks = []
    bar.on_finish_click = lambda: finish_clicks.append(True)
    bar._on_press(SimpleNamespace(x=100, y=14))
    assert finish_clicks == [True]




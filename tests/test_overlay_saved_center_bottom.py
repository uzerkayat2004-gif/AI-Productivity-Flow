from types import SimpleNamespace
from unittest.mock import patch
import re

import pytest

from voice_flow.overlay import FloatingOverlayBar
import voice_flow.overlay as overlay_module


class FakeWin:
    def __init__(self):
        self.x, self.y, self.width, self.height = 500, 700, 48, 10
        self.calls = []
        self.attributes_set = {}

    def attributes(self, name, value): self.attributes_set[name] = value
    def config(self, **kwargs): pass
    def bind(self, *args): pass

    def geometry(self, value):
        self.calls.append(value)
        match = re.fullmatch(r"(?:(\d+)x(\d+))?\+(-?\d+)\+(-?\d+)", value)
        assert match, value
        w, h, x, y = match.groups()
        if w:
            self.width, self.height = int(w), int(h)
        self.x, self.y = int(x), int(y)

    def winfo_x(self): return self.x
    def winfo_y(self): return self.y
    def winfo_screenwidth(self): return 1920
    def winfo_screenheight(self): return 1080


class FakeRoot:
    def winfo_screenwidth(self): return 1920
    def winfo_screenheight(self): return 1080
    def after(self, *args): return "scheduled"


class FakeCanvas:
    def __init__(self, *args, **kwargs): self.items = []
    def pack(self, **kwargs): pass
    def bind(self, *args): pass
    def config(self, **kwargs): pass
    def delete(self, *args): self.items.clear()
    def addtag_all(self, tag):
        for item in self.items: item[3].add(tag)
    def move(self, tag, dx, dy):
        for item in self.items:
            if tag in item[3]:
                item[1] = [value + (dx if i % 2 == 0 else dy) for i, value in enumerate(item[1])]
    def __getattr__(self, name):
        if name.startswith("create_"):
            def create(*args, **kwargs):
                coordinates = list(args[0]) if len(args) == 1 and isinstance(args[0], list) else list(args)
                self.items.append([name, coordinates, kwargs, set()])
            return create
        raise AttributeError(name)


SAVED = (1000, 1004)



@pytest.fixture(autouse=True)
def synthetic_storage(monkeypatch):
    writes = []
    storage = SimpleNamespace(saved=list(SAVED), writes=writes)
    storage.get_setting = lambda key, default=None: storage.saved if key == FloatingOverlayBar._POS_SETTING_KEY else default
    storage.save_setting = lambda key, value: writes.append((key, value))
    monkeypatch.setattr(overlay_module, "storage", storage)
    return storage


def make_restored_bar(*, expanded=False, saved=None):
    bar = FloatingOverlayBar(FakeRoot())
    bar.state = "READY"
    bar._is_mouse_over = expanded
    # The autouse fixture keeps this spy active through all production calls,
    # including native sizing, redraws, clicks, drag and release.
    storage = overlay_module.storage
    storage.saved = list(SAVED) if saved is None else saved
    writes = storage.writes
    bar.load_saved_position()
    bar.win, bar.canvas = FakeWin(), FakeCanvas()
    bar._get_screen_bounds = lambda: (0, 0, 1920, 1080)
    bar._position_window()
    bar._draw()
    return bar, writes


def foreground_center_bottom(bar):
    dx, dy = bar._foreground_offset()
    width, height = bar._foreground_size()
    return bar.win.x+dx+width//2, bar.win.y+dy+height


def test_saved_legacy_initial_native_collapsed_rectangle_matches_observation():
    bar, writes = make_restored_bar()
    assert (bar.win.x, bar.win.y, bar.win.width, bar.win.height) == (976, 994, 48, 10)
    assert foreground_center_bottom(bar) == SAVED
    assert not writes


def test_saved_legacy_center_bottom_survives_hover_and_collapse():
    bar, writes = make_restored_bar()
    bar._on_motion(SimpleNamespace(x=20, y=5))
    assert foreground_center_bottom(bar) == SAVED
    bar._is_mouse_over = False
    bar._hover_zone = None
    bar._draw()
    assert foreground_center_bottom(bar) == SAVED
    assert not writes


def test_saved_legacy_center_bottom_survives_all_voice_foregrounds():
    bar, writes = make_restored_bar()
    for state in ("RECORDING", "PROCESSING", "READING", "DONE", "ERROR", "READY"):
        bar.state = state
        bar._draw()
        assert foreground_center_bottom(bar) == SAVED, state
    assert not writes


def test_background_jobs_add_ready_remove_preserve_saved_center_bottom():
    bar, writes = make_restored_bar()
    bar.show_video_progress("v", 40, "video")
    assert foreground_center_bottom(bar) == SAVED
    bar.show_audio_summary_progress(55, "audio", job_id="a")
    assert foreground_center_bottom(bar) == SAVED
    bar.show_video_ready("v")
    assert foreground_center_bottom(bar) == SAVED
    bar.clear_video_status("v")
    bar.clear_audio_summary_status("a")
    assert foreground_center_bottom(bar) == SAVED
    assert not writes


def test_cancel_expanded_row_then_motion_preserves_saved_center_bottom():
    bar, writes = make_restored_bar(expanded=True)
    assert foreground_center_bottom(bar) == SAVED
    bar.show_video_progress("v", 40, "video")
    bar.show_audio_summary_progress(55, "audio", job_id="a")
    canceled = []
    bar.on_video_cancel = lambda job_id: canceled.append(job_id)
    top, bottom, _ = bar._summary_row_geometry()[0]
    bar._on_press(SimpleNamespace(x=bar.width-bar.GRIP_W-8, y=(top+bottom)//2))
    bar._on_drag(SimpleNamespace(x=260, y=70))
    bar._on_release(SimpleNamespace())
    assert canceled == ["v"] and "a" in bar._audio_summary_jobs
    assert foreground_center_bottom(bar) == SAVED
    assert bar._user_pos == SAVED
    assert not writes


def test_only_explicit_grip_drag_changes_saved_center_bottom():
    bar, _ = make_restored_bar()
    x, y = bar.width-5, 5
    bar._on_press(SimpleNamespace(x=x, y=y, x_root=bar.win.x+x, y_root=bar.win.y+y))
    bar._on_drag(SimpleNamespace(x=x, y=y, x_root=bar._press_screen[0]+15, y_root=bar._press_screen[1]+10))
    bar._on_release(SimpleNamespace())
    assert foreground_center_bottom(bar) == (1015, 1014)


def painted_progress_main_point(bar):
    rows = bar._summary_row_geometry()
    main = rows[-1] if bar._rows_above_foreground() else rows[0]
    top, bottom, _ = main
    card = next(item for item in bar.canvas.items
                if item[0] == "create_polygon" and item[2].get("fill") == bar.BORDER
                and min(item[1][1::2]) == top and max(item[1][1::2]) == bottom)
    return (bar.win.x + (min(card[1][::2])+max(card[1][::2]))//2,
            bar.win.y + max(card[1][1::2]))


def test_ready_jobs_paint_integrated_main_control_at_saved_anchor_without_rest_strip():
    bar, writes = make_restored_bar()
    bar.show_audio_summary_progress(100, "private stage", job_id="audio")
    assert painted_progress_main_point(bar) == SAVED
    assert not any(item[2].get("fill") == bar.BG_REST for item in bar.canvas.items)
    assert not any("foreground" in item[3] for item in bar.canvas.items)
    labels = [item[2]["text"] for item in bar.canvas.items if item[0] == "create_text"]
    assert labels == ["Audio Flow", "100%"]
    rails = [item for item in bar.canvas.items if item[0] == "create_line" and item[2].get("width") == 4]
    assert len(rails) == 2
    assert all(0 <= min(item[1][::2]) <= max(item[1][::2]) < bar.width for item in rails)
    assert sum(item[0] == "create_oval" and item[1][2]-item[1][0] == 2 for item in bar.canvas.items) == 6
    assert not writes


def test_physical_cancel_point_does_not_move_or_retarget_on_hover():
    bar, writes = make_restored_bar()
    bar.show_video_progress("v", 40, "video")
    bar.show_audio_summary_progress(55, "audio", job_id="a")
    top, bottom, _ = bar._summary_row_geometry()[0]
    x, y = bar.width-bar.GRIP_W-8, (top+bottom)//2
    physical = (bar.win.x+x, bar.win.y+y)
    bar._on_motion(SimpleNamespace(x=x, y=y))
    assert (bar.win.x+x, bar.win.y+y) == physical
    assert bar._get_zone(x, y) == "summary_cancel:0"
    assert painted_progress_main_point(bar) == SAVED
    assert not bar._is_mouse_over
    canceled = []
    bar.on_video_cancel = canceled.append
    bar._on_press(SimpleNamespace(x=x, y=y))
    bar._on_drag(SimpleNamespace(x=x+100, y=y+100))
    bar._on_release(SimpleNamespace())
    assert canceled == ["v"] and "a" in bar._audio_summary_jobs
    assert painted_progress_main_point(bar) == SAVED
    assert not writes


def test_integrated_voice_entry_does_not_cancel_background_jobs():
    bar, writes = make_restored_bar()
    bar.show_audio_summary_progress(55, "audio", job_id="a")
    starts = []
    bar.on_start_click = lambda: starts.append(True)
    top, bottom, _ = bar._summary_row_geometry()[0]
    assert bar._get_zone(18, (top+bottom)//2) == "summary_voice"
    bar._on_press(SimpleNamespace(x=18, y=(top+bottom)//2))
    assert starts == [True]
    assert "a" in bar._audio_summary_jobs
    assert painted_progress_main_point(bar) == SAVED
    assert not writes


def test_v2_preference_preserves_startup_then_follows_center_bottom_without_write():
    bar, writes = make_restored_bar(saved={"version": 2, "right": 1024, "top": 994})
    assert foreground_center_bottom(bar) == SAVED
    bar._on_motion(SimpleNamespace(x=20, y=5))
    assert foreground_center_bottom(bar) == SAVED
    bar.show_audio_summary_progress(55, "audio", job_id="a")
    assert painted_progress_main_point(bar) == SAVED
    assert not writes


def test_grip_release_writes_center_bottom_once_and_hover_never_writes():
    bar, writes = make_restored_bar()
    bar._on_motion(SimpleNamespace(x=20, y=5))
    x, y = bar.width-5, 14
    screen = (bar.win.x+x, bar.win.y+y)
    bar._on_press(SimpleNamespace(x=x, y=y, x_root=screen[0], y_root=screen[1]))
    bar._on_drag(SimpleNamespace(x=x, y=y, x_root=screen[0]+15, y_root=screen[1]+10))
    assert not writes
    bar._on_release(SimpleNamespace())
    assert writes == [(bar._POS_SETTING_KEY, [1015, 1014])]
    bar._is_mouse_over = False
    bar._draw()
    assert foreground_center_bottom(bar) == (1015, 1014)
    assert len(writes) == 1


def test_macos_rounding_uses_visible_main_row_height():
    bar, _ = make_restored_bar()
    shapes = []
    bar._mac_update_shape = lambda radius, fill: shapes.append((radius, fill))
    with patch("voice_flow.overlay.sys.platform", "darwin"):
        bar.show_audio_summary_progress(55, "audio", job_id="a")
        bar._last_draw_sig = None
        bar._draw()
    assert shapes and shapes[-1] == (16, bar.BORDER)


def test_thirteen_rows_and_active_voice_cancel_preserve_main_anchor():
    bar, writes = make_restored_bar()
    for index in range(12):
        bar.show_audio_summary_progress(55, "audio", job_id=str(index))
    bar.show_video_progress("v", 40, "video")
    assert len(bar._summary_row_geometry()) == bar.MAX_SUMMARY_ROWS
    assert painted_progress_main_point(bar) == SAVED
    assert bar.win.y >= 0 and bar.win.y+bar.height <= 1080
    bar.state = "RECORDING"
    bar._draw()
    assert foreground_center_bottom(bar) == SAVED
    cancel = []
    bar.on_video_cancel = cancel.append
    top, bottom, _ = bar._summary_row_geometry()[0]
    bar._on_press(SimpleNamespace(x=bar.width-bar.GRIP_W-8, y=(top+bottom)//2))
    assert cancel == ["v"]
    assert bar.state == "RECORDING" and len(bar._audio_summary_jobs) == 12
    assert foreground_center_bottom(bar) == SAVED
    assert not writes


@pytest.mark.parametrize("center,bottom", [(140, 32), (1780, 1080), (148, 550), (1772, 550)])
def test_edge_layouts_keep_painted_main_row_and_cancel_points_inside_screen(center, bottom):
    bar, writes = make_restored_bar(saved=[center, bottom])
    for index in range(12):
        bar.show_audio_summary_progress(100, "audio", job_id=str(index))
    bar.show_video_progress("v", 100, "video")
    assert painted_progress_main_point(bar) == (center, bottom)
    assert 0 <= bar.win.x <= 1920-bar.width
    assert 0 <= bar.win.y <= 1080-bar.height
    for index, (top, row_bottom, _) in enumerate(bar._summary_row_geometry()):
        x, y = bar.width-bar.GRIP_W-8, (top+row_bottom)//2
        physical = (bar.win.x+x, bar.win.y+y)
        assert 0 <= physical[0] < 1920 and 0 <= physical[1] < 1080
        bar._on_motion(SimpleNamespace(x=x, y=y))
        assert (bar.win.x+x, bar.win.y+y) == physical
        assert bar._get_zone(x, y) == f"summary_cancel:{index}"
    assert not writes


def test_voice_foreground_cancel_finish_and_read_controls_coexist_with_jobs():
    bar, writes = make_restored_bar()
    bar.show_audio_summary_progress(55, "audio", job_id="a")
    calls = []
    bar.on_cancel_click = lambda: calls.append("voice_cancel")
    bar.on_finish_click = lambda: calls.append("voice_finish")
    bar.state = "RECORDING"
    bar._draw()
    dx, dy = bar._foreground_offset()
    bar._on_press(SimpleNamespace(x=dx+18, y=dy+14))
    bar._on_press(SimpleNamespace(x=dx+160, y=dy+14))
    # Voice backend callbacks are serialized off Tk; wait only in the test.
    worker = bar._voice_clicks._thread
    if worker is not None:
        worker.join(timeout=1)
        assert not worker.is_alive()
    assert calls == ["voice_cancel", "voice_finish"]
    assert "a" in bar._audio_summary_jobs and foreground_center_bottom(bar) == SAVED
    bar.state = "READING"
    bar.on_audio_pause_toggle = lambda: calls.append("audio_pause")
    bar.on_open_settings = lambda: calls.append("settings")
    bar._draw()
    dx, dy = bar._foreground_offset()
    bar._on_press(SimpleNamespace(x=dx+128, y=dy+14))
    bar._on_press(SimpleNamespace(x=dx+203, y=dy+14))
    assert calls[-2:] == ["audio_pause", "settings"]
    assert "a" in bar._audio_summary_jobs and foreground_center_bottom(bar) == SAVED
    assert not writes


def test_explicit_selection_preserves_video_settings_and_speak_actions_with_jobs():
    bar, writes = make_restored_bar()
    bar.show_audio_summary_progress(55, "audio", job_id="a")
    bar._selection_expanded = True
    bar.selected_text = "Synthetic selected text"
    bar._draw()
    dx, dy = bar._foreground_offset()
    assert bar._get_zone(dx+40, dy+14) == "speak"
    assert bar._get_zone(dx+180, dy+14) == "video_flow"
    assert bar._get_zone(dx+220, dy+14) == "settings"
    calls = []
    bar.on_open_settings = lambda: calls.append("settings")
    bar._on_press(SimpleNamespace(x=dx+220, y=dy+14))
    assert calls == ["settings"]
    assert bar.selected_text == "Synthetic selected text" and "a" in bar._audio_summary_jobs
    assert foreground_center_bottom(bar) == SAVED and not writes

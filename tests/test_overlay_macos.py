"""macOS floating-bar regressions (Tk 9 / Aqua), with Windows behaviour pinned."""
from __future__ import annotations

import sys
import threading

import pytest

from voice_flow import overlay as overlay_mod
from voice_flow.overlay import FloatingOverlayBar


@pytest.fixture(autouse=True)
def _no_real_appkit(monkeypatch):
    """Never touch the real NSApplication from tests (even on macOS CI)."""
    import types

    appkit = types.ModuleType("AppKit")
    appkit.NSApplication = types.SimpleNamespace(sharedApplication=lambda: types.SimpleNamespace(windows=lambda: []))
    appkit.NSColor = types.SimpleNamespace(clearColor=lambda: "clear")
    monkeypatch.setitem(sys.modules, "AppKit", appkit)


class FakeRoot:
    def __init__(self) -> None:
        self.after_calls: list[tuple[int, object]] = []

    def after(self, ms, func=None):
        self.after_calls.append((ms, func))
        return f"after#{len(self.after_calls)}"

    def winfo_screenwidth(self):
        return 1440

    def winfo_screenheight(self):
        return 900


class FakeWin:
    def __init__(self, *_args, **_kwargs) -> None:
        self.attributes_calls: list[tuple] = []
        self.config_calls: list[dict] = []
        self.geometry_calls: list[str] = []

    def withdraw(self): pass
    def deiconify(self): pass
    def lift(self): pass
    def overrideredirect(self, *_a): pass
    def iconbitmap(self, *_a): pass
    def bind(self, *_a): pass
    def winfo_exists(self): return True
    def winfo_ismapped(self): return True
    def winfo_x(self): return 696
    def winfo_y(self): return 830
    def update_idletasks(self): pass

    def attributes(self, *args):
        self.attributes_calls.append(args)

    def config(self, **kwargs):
        self.config_calls.append(kwargs)

    def geometry(self, spec):
        self.geometry_calls.append(spec)


class FakeCanvas:
    instances: list["FakeCanvas"] = []

    def __init__(self, _parent=None, **kwargs) -> None:
        self.kwargs = kwargs
        self.polygons: list[dict] = []
        FakeCanvas.instances.append(self)

    def pack(self, **_k): pass
    def bind(self, *_a): pass
    def config(self, **_k): pass
    def delete(self, *_a): pass
    def create_line(self, *_a, **_k): pass
    def create_oval(self, *_a, **_k): pass
    def create_rectangle(self, *_a, **_k): pass
    def create_text(self, *_a, **_k): pass
    def create_image(self, *_a, **_k): pass

    def create_polygon(self, *_a, **kwargs):
        self.polygons.append(kwargs)


def _bar(main_tid: int | None = None) -> FloatingOverlayBar:
    bar = FloatingOverlayBar()
    bar.root = FakeRoot()
    bar._main_thread_id = threading.get_ident() if main_tid is None else main_tid
    bar._mainloop_running = True
    return bar


def _from_thread(func) -> None:
    t = threading.Thread(target=func)
    t.start()
    t.join(5)


def test_macos_background_updates_are_queued_and_pumped_on_tk_thread(monkeypatch):
    monkeypatch.setattr(overlay_mod.sys, "platform", "darwin")
    bar = _bar()
    ran: list[int] = []
    _from_thread(lambda: bar._run_on_ui(lambda: ran.append(threading.get_ident())))
    assert bar.root.after_calls == [], "root.after from a non-Tk thread never fires on macOS Tk 9"
    assert ran == []
    bar._pump_ui_queue()
    assert ran == [threading.get_ident()], "queued work runs on the Tk thread"
    assert bar.root.after_calls[-1][1] == bar._pump_ui_queue, "the pump keeps itself scheduled"


def test_macos_show_recording_from_hotkey_thread_reaches_the_bar(monkeypatch):
    monkeypatch.setattr(overlay_mod.sys, "platform", "darwin")
    bar = _bar()
    bar.win = FakeWin()
    bar.canvas = FakeCanvas()
    _from_thread(bar.show_recording)
    bar._pump_ui_queue()
    assert bar.state == "RECORDING"


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_non_mac_background_updates_still_use_root_after(monkeypatch, platform):
    monkeypatch.setattr(overlay_mod.sys, "platform", platform)
    bar = _bar()
    func = lambda: None  # noqa: E731
    _from_thread(lambda: bar._run_on_ui(func))
    assert bar.root.after_calls == [(0, func)]
    assert bar._ui_queue.empty()


def _create(monkeypatch, platform: str) -> tuple[FloatingOverlayBar, FakeWin, FakeCanvas]:
    monkeypatch.setattr(overlay_mod.sys, "platform", platform)
    monkeypatch.setattr(overlay_mod.tk, "Toplevel", FakeWin)
    monkeypatch.setattr(overlay_mod.tk, "Canvas", FakeCanvas)
    monkeypatch.setattr(overlay_mod, "_enable_dpi_awareness", lambda: None)
    monkeypatch.setattr(FloatingOverlayBar, "_schedule_proximity_poll", lambda self: None)
    monkeypatch.setattr(FloatingOverlayBar, "_apply_win32_styles", lambda self: None)
    bar = _bar()
    bar._mainloop_running = False
    bar._create_window()
    return bar, bar.win, FakeCanvas.instances[-1]


def test_macos_bar_has_no_black_key_colour_frame(monkeypatch):
    bar, win, canvas = _create(monkeypatch, "darwin")
    assert not any(c[0] == "-transparentcolor" for c in win.attributes_calls)
    assert canvas.kwargs["bg"] == bar.BORDER_REST != "#010101"


def test_macos_bar_window_is_clipped_to_the_pill(monkeypatch):
    import types

    class Layer:
        radius = None
        masks = None
        def setCornerRadius_(self, r): self.radius = r
        def setMasksToBounds_(self, v): self.masks = v

    class View:
        def __init__(self): self.layer_obj = Layer(); self.wants = False
        def setWantsLayer_(self, v): self.wants = v
        def layer(self): return self.layer_obj

    class Frame:
        def __init__(self, x, w, h):
            self.origin = types.SimpleNamespace(x=x, y=0)
            self.size = types.SimpleNamespace(width=w, height=h)

    class NSWin:
        def __init__(self, x, w, h): self._frame = Frame(x, w, h); self.view = View(); self.opaque = True; self.shadow = True
        def frame(self): return self._frame
        def setOpaque_(self, v): self.opaque = v
        def setBackgroundColor_(self, c): self.bg = c
        def setHasShadow_(self, v): self.shadow = v
        def contentView(self): return self.view

    bar, win, canvas = _create(monkeypatch, "darwin")
    other = NSWin(5, 200, 228)
    target = NSWin(win.winfo_x(), bar.width, bar.height)
    app = types.SimpleNamespace(windows=lambda: [other, target])
    appkit = types.ModuleType("AppKit")
    appkit.NSApplication = types.SimpleNamespace(sharedApplication=lambda: app)
    appkit.NSColor = types.SimpleNamespace(clearColor=lambda: "clear")
    monkeypatch.setitem(sys.modules, "AppKit", appkit)
    bar.state = "READY"
    bar._last_draw_sig = None
    bar._draw()
    assert target.opaque is False and target.shadow is False
    assert target.view.wants and target.view.layer_obj.masks is True
    assert target.view.layer_obj.radius == min(bar.height / 2, 14)
    assert other.view.layer_obj.radius is None


def test_windows_bar_keeps_transparentcolor_key(monkeypatch):
    bar, win, canvas = _create(monkeypatch, "win32")
    assert ("-transparentcolor", "#010101") in win.attributes_calls
    assert canvas.kwargs["bg"] == "#010101"


def test_macos_forced_repaint_resizes_once_and_redraws_dark_rest_pill(monkeypatch):
    bar, win, canvas = _create(monkeypatch, "darwin")
    bar.state = "READY"
    canvas.polygons.clear()
    win.geometry_calls.clear()
    bar._mac_force_repaint()
    assert win.geometry_calls[0].startswith(f"{bar.width + 1}x{bar.height}+")
    assert win.geometry_calls[-1].startswith(f"{bar.width}x{bar.height}+")
    fills = [p.get("fill") for p in canvas.polygons]
    assert bar.BG_REST in fills, "rest state must paint the dark pill"


def test_macos_resize_schedules_one_coalesced_repaint(monkeypatch):
    bar, win, canvas = _create(monkeypatch, "darwin")
    bar._mainloop_running = True
    bar.root.after_calls.clear()
    bar._set_bar_size(bar.width + 100, 28)
    bar._set_bar_size(bar.width + 20, 28)
    repaints = [c for c in bar.root.after_calls if c[1] == bar._mac_force_repaint]
    assert len(repaints) == 1
    bar._mac_force_repaint()
    assert bar._mac_repaint_pending is False


def test_windows_resize_never_schedules_mac_repaint(monkeypatch):
    bar, win, canvas = _create(monkeypatch, "win32")
    bar._mainloop_running = True
    bar.root.after_calls.clear()
    bar._set_bar_size(bar.width + 100, 28)
    assert not [c for c in bar.root.after_calls if c[1] == bar._mac_force_repaint]

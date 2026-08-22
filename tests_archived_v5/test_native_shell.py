from __future__ import annotations

from pathlib import Path

from voice_flow.native_settings import RUN_VALUE, get_launch_at_login, set_launch_at_login
from voice_flow.overlay import dock_from_pointer, dock_geometry


class FakeKey:
    def __enter__(self): return self
    def __exit__(self, *_args): return False


class FakeRegistry:
    HKEY_CURRENT_USER = object()
    KEY_READ = 1
    KEY_WRITE = 2
    KEY_SET_VALUE = 4
    REG_SZ = 1
    def __init__(self): self.values = {}; self.calls = []
    def OpenKey(self, *_args): return FakeKey()
    def QueryValueEx(self, _key, name):
        if name not in self.values: raise FileNotFoundError()
        return self.values[name], self.REG_SZ
    def SetValueEx(self, _key, name, _zero, _kind, value): self.calls.append(("set", name, value)); self.values[name] = value
    def DeleteValue(self, _key, name): self.calls.append(("delete", name)); self.values.pop(name, None)


def test_dock_geometry_and_edge_selection_are_conservative():
    assert dock_geometry(1000, 800, 240, 32, "bottom", margin=60).y == 708
    assert dock_geometry(1000, 800, 32, 240, "left").x == 24
    assert dock_geometry(1000, 800, 32, 240, "right").x == 944
    assert dock_from_pointer(1000, 800, 4, 300, "bottom") == "left"
    assert dock_from_pointer(1000, 800, 999, 300, "bottom") == "right"
    assert dock_from_pointer(1000, 800, 500, 795, "left") == "bottom"
    assert dock_from_pointer(1000, 800, 500, 300, "right") == "right"


def test_escape_cancels_a_drag_and_restores_previous_dock():
    from types import SimpleNamespace
    from voice_flow.overlay import FloatingOverlayBar
    geometry = []
    bar = FloatingOverlayBar(root=SimpleNamespace(winfo_screenwidth=lambda: 1000, winfo_screenheight=lambda: 800))
    bar.win = SimpleNamespace(geometry=geometry.append)
    bar.dock, bar._drag_previous_dock, bar._dragging = "right", "left", True
    assert bar._on_escape() == "break"
    assert bar.dock == "left" and not bar._dragging and geometry


def test_startup_helper_only_changes_voiceflow_value_when_toggled():
    registry = FakeRegistry()
    assert not get_launch_at_login(registry).applied
    assert set_launch_at_login(True, "voice-flow", registry).applied
    assert registry.values[RUN_VALUE] == "voice-flow"
    assert set_launch_at_login(False, registry=registry).applied
    assert RUN_VALUE not in registry.values
    assert [call[0] for call in registry.calls] == ["set", "delete"]


def test_native_shell_ui_is_windows_accurate_and_has_no_implicit_startup():
    root = Path(__file__).parents[1] / "src" / "voice_flow" / "gui"
    html = (root / "index.html").read_text(encoding="utf8")
    launcher = (root / "desktop_launcher.py").read_text(encoding="utf8")
    assert "Show app in taskbar" in html and "Show app in dock" not in html
    assert "set_windows_auto_startup" not in launcher
    assert "pystray" not in launcher and "from PIL" not in launcher

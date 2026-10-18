"""Splash shows the running build, never outlives startup, and launcher state stays private."""

from __future__ import annotations

import importlib.util
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPLASH_PATH = ROOT / "src" / "voice_flow" / "gui" / "early_splash.py"
SPLASH_SRC = SPLASH_PATH.read_text(encoding="utf-8")
LAUNCHER_SRC = (ROOT / "src" / "voice_flow" / "gui" / "desktop_launcher.py").read_text(encoding="utf-8")
LAUNCH_APF_SRC = (ROOT / "release" / "installer" / "launch_apf.pyw").read_text(encoding="utf-8")


def _load_by_path():
    spec = importlib.util.spec_from_file_location("apf_early_splash_test", SPLASH_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_splash_version_is_the_running_build_from_version_py():
    from voice_flow._version import __version__

    module = _load_by_path()  # same way launch_apf.pyw loads it: by file path, no package import
    assert module.read_app_version() == __version__
    assert module.version_label() == f"Version {__version__}"
    assert "DISPLAY_VERSION" not in SPLASH_SRC
    assert 'return "1.0"' not in SPLASH_SRC


def test_splash_shows_no_version_rather_than_a_wrong_one(tmp_path, monkeypatch):
    module = _load_by_path()
    monkeypatch.setattr(module.os.path, "abspath", lambda _p: str(tmp_path / "gui" / "early_splash.py"))
    assert module.read_app_version() == ""
    assert module.version_label() == ""


def test_splash_has_its_own_deadline():
    module = _load_by_path()
    assert 30 <= module.MAX_SPLASH_SECONDS <= 300
    create = SPLASH_SRC.split("def _create_window", 1)[1].split("\ndef _pump", 1)[0]
    assert "_DEADLINE_TIMER_ID" in create and "MAX_SPLASH_SECONDS * 1000" in create
    proc = SPLASH_SRC.split("def _wnd_proc", 1)[1].split("\n_PAINTSTRUCT", 1)[0]
    assert "_DEADLINE_TIMER_ID" in proc and "DestroyWindow" in proc


def test_close_targets_only_this_process_splash_windows():
    close = SPLASH_SRC.split("def close_early_splash", 1)[1].split("\ndef show_early_splash", 1)[0]
    assert "_owned_splash_windows()" in close
    owned = SPLASH_SRC.split("def _owned_splash_windows", 1)[1].split("\ndef _is_own_splash", 1)[0]
    assert "FindWindowExW" in owned and "GetWindowThreadProcessId" in owned and "os.getpid()" in owned
    # Still pointer-sized only (64-bit LPARAM regression from v1.0.4).
    assert "ctypes.c_long" not in SPLASH_SRC


def test_close_is_a_noop_off_windows():
    module = _load_by_path()
    os.environ["VOICE_FLOW_EARLY_SPLASH_HWND"] = "12345"
    try:
        module.close_early_splash()  # must not raise on Linux/macOS
    finally:
        os.environ.pop("VOICE_FLOW_EARLY_SPLASH_HWND", None)


def test_children_do_not_inherit_launcher_mutex_or_splash(monkeypatch):
    from voice_flow.watchdog import get_pythonw_env

    monkeypatch.setenv("VOICE_FLOW_LAUNCHER_MUTEX_HANDLE", "1234")
    monkeypatch.setenv("VOICE_FLOW_LAUNCHER_MUTEX_PID", "999")
    monkeypatch.setenv("VOICE_FLOW_EARLY_SPLASH_HWND", "5678")
    env = get_pythonw_env(extra_env={"VOICE_FLOW_GUI_STARTED": "1"})
    assert "VOICE_FLOW_LAUNCHER_MUTEX_HANDLE" not in env
    assert "VOICE_FLOW_LAUNCHER_MUTEX_PID" not in env
    assert "VOICE_FLOW_EARLY_SPLASH_HWND" not in env
    assert env["VOICE_FLOW_GUI_STARTED"] == "1"


def test_mutex_handle_from_another_process_is_ignored(monkeypatch):
    from voice_flow.gui import desktop_launcher

    monkeypatch.setattr(desktop_launcher, "_LAUNCHER_MUTEX_HANDLE", None)
    monkeypatch.setenv("VOICE_FLOW_LAUNCHER_MUTEX_HANDLE", "4242")
    monkeypatch.setenv("VOICE_FLOW_LAUNCHER_MUTEX_PID", str(os.getpid() + 1))
    assert desktop_launcher._acquire_launcher_mutex() is True  # non-Windows: no mutex at all
    assert desktop_launcher._LAUNCHER_MUTEX_HANDLE != 4242

    monkeypatch.setenv("VOICE_FLOW_LAUNCHER_MUTEX_PID", str(os.getpid()))
    assert desktop_launcher._acquire_launcher_mutex() is True
    assert desktop_launcher._LAUNCHER_MUTEX_HANDLE == 4242


def test_old_launch_apf_without_pid_still_works(monkeypatch):
    """App-only updates keep the installed launch_apf.pyw, which sets no PID."""
    from voice_flow.gui import desktop_launcher

    monkeypatch.setattr(desktop_launcher, "_LAUNCHER_MUTEX_HANDLE", None)
    monkeypatch.setenv("VOICE_FLOW_LAUNCHER_MUTEX_HANDLE", "77")
    monkeypatch.delenv("VOICE_FLOW_LAUNCHER_MUTEX_PID", raising=False)
    assert desktop_launcher._acquire_launcher_mutex() is True
    assert desktop_launcher._LAUNCHER_MUTEX_HANDLE == 77


def test_launch_apf_marks_its_mutex_with_its_pid():
    assert 'os.environ["VOICE_FLOW_LAUNCHER_MUTEX_PID"] = str(os.getpid())' in LAUNCH_APF_SRC


def test_launcher_logs_where_startup_time_goes():
    gui = LAUNCHER_SRC.split("def launch_desktop_gui", 1)[1].split("\ndef _install_mac_window_lifecycle", 1)[0]
    assert "engine wait finished after" in gui
    # The shown handler moved into _wire_window, shared by both window paths.
    wire = LAUNCHER_SRC.split("def _wire_window", 1)[1].split("\ndef ", 1)[0]
    assert re.search(r"main window shown .* after launch", wire)
    assert "_wire_window(" in gui
    # Cold start (warming window) logs when the window and the app UI appear.
    assert "warming window created" in LAUNCHER_SRC
    assert "app UI loaded" in LAUNCHER_SRC
    assert "[timing]" in LAUNCHER_SRC

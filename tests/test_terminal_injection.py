from __future__ import annotations

import os
import sys
from types import SimpleNamespace

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow import injector
from voice_flow import style_engine


def test_is_internal_window_rejects_external_terminals_even_with_app_title(monkeypatch) -> None:
    """Terminals running outside Voice Flow's process must never be treated as internal windows,
    even if the terminal title is 'voice flow' or 'voice-flow' (e.g. user cd'd into repo).
    """
    foreign_pid = os.getpid() + 100

    def mock_get_window_thread_process_id(_hwnd, pid_ptr):
        if pid_ptr:
            pid_ptr._obj.value = foreign_pid
        return 1

    user32 = SimpleNamespace(
        IsWindow=lambda _hwnd: True,
        GetWindowThreadProcessId=mock_get_window_thread_process_id,
        GetAncestor=lambda _h, _ga: 0,
        GetWindowTextLengthW=lambda _h: len("Voice Flow"),
        GetWindowTextW=lambda _h, buff, _l: buff.__setattr__("value", "Voice Flow"),
        GetClassNameW=lambda _h, buff, _l: buff.__setattr__("value", "CASCADIA_HOSTING_WINDOW_CLASS"),
        FindWindowW=lambda _cls, _t: 0,
    )
    monkeypatch.setattr(injector.ctypes, "windll", SimpleNamespace(user32=user32, kernel32=SimpleNamespace(OpenProcess=lambda *a: 0)))

    # Must be identified as external (False) so voice dictation and audio flow can paste/interact
    assert injector.is_internal_window(42) is False


def test_is_internal_window_identifies_own_process_as_internal(monkeypatch) -> None:
    """Windows belonging to our own Python process must still be identified as internal."""
    my_pid = os.getpid()

    def mock_get_window_thread_process_id(_hwnd, pid_ptr):
        if pid_ptr:
            pid_ptr._obj.value = my_pid
        return 1

    user32 = SimpleNamespace(
        IsWindow=lambda _hwnd: True,
        GetWindowThreadProcessId=mock_get_window_thread_process_id,
    )
    monkeypatch.setattr(injector.ctypes, "windll", SimpleNamespace(user32=user32, kernel32=SimpleNamespace()))

    assert injector.is_internal_window(999) is True


def test_is_same_window_hierarchy_matches_root_and_child(monkeypatch) -> None:
    """Child controls (like Windows Terminal XAML site) and their root ancestor must match."""
    child_hwnd = 500
    root_hwnd = 100

    def mock_is_child(parent, child):
        return (parent == root_hwnd and child == child_hwnd)

    def mock_get_ancestor(h, ga):
        if h == child_hwnd:
            return root_hwnd
        return h

    user32 = SimpleNamespace(
        IsChild=mock_is_child,
        GetAncestor=mock_get_ancestor,
    )
    monkeypatch.setattr(injector.ctypes, "windll", SimpleNamespace(user32=user32))

    assert injector.is_same_window_hierarchy(child_hwnd, child_hwnd) is True
    assert injector.is_same_window_hierarchy(root_hwnd, child_hwnd) is True
    assert injector.is_same_window_hierarchy(child_hwnd, root_hwnd) is True
    assert injector.is_same_window_hierarchy(child_hwnd, 999) is False


def test_terminal_paste_routes_windows_terminal_to_ctrl_v(monkeypatch) -> None:
    """Windows Terminal (CASCADIA_HOSTING_WINDOW_CLASS) must use Ctrl+V for paste."""
    ctrl_v_called = False
    shift_insert_called = False

    def mock_ctrl_v():
        nonlocal ctrl_v_called
        ctrl_v_called = True

    def mock_shift_insert():
        nonlocal shift_insert_called
        shift_insert_called = True

    monkeypatch.setattr(injector, "_send_win32_ctrl_v", mock_ctrl_v)
    monkeypatch.setattr(injector, "_send_win32_shift_insert", mock_shift_insert)
    monkeypatch.setattr(injector, "is_internal_window", lambda _h: False)
    monkeypatch.setattr(injector, "get_window_class_name", lambda _h: "CASCADIA_HOSTING_WINDOW_CLASS")
    monkeypatch.setattr(injector, "get_active_window_title", lambda: "PowerShell - voice-flow")
    monkeypatch.setattr(injector, "_safe_copy_to_clipboard", lambda _t: True)
    monkeypatch.setattr(injector, "_safe_paste_from_clipboard", lambda: "")
    monkeypatch.setattr(injector, "focus_target_window", lambda _h: None)
    monkeypatch.setattr(injector, "is_same_window_hierarchy", lambda _a, _b: True)

    user32 = SimpleNamespace(
        IsWindow=lambda _h: True,
        GetForegroundWindow=lambda: 1234,
        GetAsyncKeyState=lambda _k: 0,
    )
    monkeypatch.setattr(injector.ctypes, "windll", SimpleNamespace(user32=user32))

    success = injector.inject_text("ls -la", target_hwnd=1234)
    assert success is True
    assert ctrl_v_called is True
    assert shift_insert_called is False


def test_terminal_paste_routes_mintty_to_shift_insert(monkeypatch) -> None:
    """Legacy terminal emulators like mintty (Git Bash) or PuTTY must use Shift+Insert."""
    ctrl_v_called = False
    shift_insert_called = False

    def mock_ctrl_v():
        nonlocal ctrl_v_called
        ctrl_v_called = True

    def mock_shift_insert():
        nonlocal shift_insert_called
        shift_insert_called = True

    monkeypatch.setattr(injector, "_send_win32_ctrl_v", mock_ctrl_v)
    monkeypatch.setattr(injector, "_send_win32_shift_insert", mock_shift_insert)
    monkeypatch.setattr(injector, "is_internal_window", lambda _h: False)
    monkeypatch.setattr(injector, "get_window_class_name", lambda _h: "mintty")
    monkeypatch.setattr(injector, "get_active_window_title", lambda: "MINGW64:/c/project")
    monkeypatch.setattr(injector, "_safe_copy_to_clipboard", lambda _t: True)
    monkeypatch.setattr(injector, "_safe_paste_from_clipboard", lambda: "")
    monkeypatch.setattr(injector, "focus_target_window", lambda _h: None)
    monkeypatch.setattr(injector, "is_same_window_hierarchy", lambda _a, _b: True)

    user32 = SimpleNamespace(
        IsWindow=lambda _h: True,
        GetForegroundWindow=lambda: 5678,
        GetAsyncKeyState=lambda _k: 0,
    )
    monkeypatch.setattr(injector.ctypes, "windll", SimpleNamespace(user32=user32))

    success = injector.inject_text("git status", target_hwnd=5678)
    assert success is True
    assert shift_insert_called is True
    assert ctrl_v_called is False


def test_terminal_style_classification() -> None:
    """Terminal applications must classify as 'developer' style category."""
    assert style_engine.detect_app_category("Windows PowerShell", "powershell.exe") == "developer"
    assert style_engine.detect_app_category("PowerShell 7", "pwsh.exe") == "developer"
    assert style_engine.detect_app_category("Administrator: Command Prompt", "cmd.exe") == "developer"
    assert style_engine.detect_app_category("Ubuntu", "wsl.exe") == "developer"
    assert style_engine.detect_app_category("Git Bash", "mintty.exe") == "developer"
    assert style_engine.detect_app_category("Windows Terminal", "windowsterminal.exe") == "developer"


def test_terminal_app_normalization() -> None:
    """Terminal application names must normalize cleanly for display."""
    assert style_engine.normalize_app_name("Windows PowerShell", "powershell.exe") == "PowerShell"
    assert style_engine.normalize_app_name("pwsh", "pwsh.exe") == "PowerShell"
    assert style_engine.normalize_app_name("Command Prompt", "cmd.exe") == "Command Prompt"
    assert style_engine.normalize_app_name("MINGW64", "mintty.exe") == "Git Bash"
    assert style_engine.normalize_app_name("Windows Terminal", "windowsterminal.exe") == "Windows Terminal"

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow import injector
from voice_flow.injector import _format_text_for_title


def test_excel_navigation_is_not_applied_to_ordinary_windows() -> None:
    text = "Move to the next cell and review the next row."
    assert _format_text_for_title(text, "Google Chrome") == text


def test_excel_navigation_consumes_polisher_terminal_punctuation() -> None:
    assert _format_text_for_title("next cell.", "Budget.xlsx - Excel") == "\t"
    assert _format_text_for_title("next row!", "Budget.xlsx - Excel") == "\n"


def test_target_paste_refuses_to_fall_back_to_an_unrelated_foreground_window(monkeypatch) -> None:
    user32 = SimpleNamespace(IsWindow=lambda _hwnd: True, GetForegroundWindow=lambda: 999)
    monkeypatch.setattr(injector.ctypes, "windll", SimpleNamespace(user32=user32))
    monkeypatch.setattr(injector, "focus_target_window", lambda _hwnd: None)

    assert injector.inject_text("must not reach another app", target_hwnd=42) is False

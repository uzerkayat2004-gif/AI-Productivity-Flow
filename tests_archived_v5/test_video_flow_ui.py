from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

from voice_flow.main import VoiceFlowApp
from voice_flow.overlay import FloatingOverlayBar


def test_ready_overlay_keeps_collapsed_speak_and_exposes_hovered_video() -> None:
    calls: list[str] = []
    bar = FloatingOverlayBar(on_video_click=lambda: calls.append("video"))
    bar.on_start_click = lambda: calls.append("speak")
    bar.state, bar.width, bar.height = "READY", 180, 32
    bar._is_mouse_over = False
    bar._on_press(SimpleNamespace(x=170, y=16))
    bar._is_mouse_over = True
    bar._on_press(SimpleNamespace(x=170, y=16))
    assert calls == ["speak", "video"]


def test_selected_text_capture_uses_verified_copy_and_restores_clipboard() -> None:
    app = VoiceFlowApp.__new__(VoiceFlowApp)
    copied: list[str] = []
    clipboard = iter(["previous", "selected text"])
    fake_clipboard = SimpleNamespace(paste=lambda: next(clipboard), copy=copied.append)
    user32 = SimpleNamespace(GetForegroundWindow=lambda: 42, keybd_event=lambda *_: None)
    with patch.dict(sys.modules, {"pyperclip": fake_clipboard}), \
         patch("voice_flow.main.focus_target_window", return_value=True), \
         patch.object(__import__("voice_flow.main", fromlist=["ctypes"]).ctypes, "windll", SimpleNamespace(user32=user32), create=True):
        assert app._capture_selected_text_for_video() == "selected text"
    assert copied[0].startswith("__voice_flow_selection_")
    assert copied[-1] == "previous"
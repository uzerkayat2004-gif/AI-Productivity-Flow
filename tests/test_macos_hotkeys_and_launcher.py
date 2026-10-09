from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from pynput import keyboard

from voice_flow import hotkeys
from voice_flow.gui import desktop_launcher


class _FakeListener:
    starts = 0

    def __init__(self, **_kwargs):
        self._alive = False

    def start(self):
        type(self).starts += 1
        self._alive = True

    def stop(self):
        self._alive = False

    def is_alive(self):
        return self._alive


def _listener() -> hotkeys.InputTriggerListener:
    return hotkeys.InputTriggerListener(lambda: None, lambda: None, lambda: None)


def _distinct_keyboard():
    names = (
        "ctrl", "ctrl_l", "ctrl_r", "cmd", "cmd_l", "cmd_r", "alt", "alt_l",
        "alt_r", "alt_gr", "shift", "shift_l", "shift_r", "space", "tab",
        "esc", "enter",
    )
    return SimpleNamespace(Key=SimpleNamespace(**{name: object() for name in names}))


def test_darwin_start_uses_pynput_without_win32_watchdog(monkeypatch, caplog):
    _FakeListener.starts = 0
    monkeypatch.setattr(hotkeys, "IS_WINDOWS", False)
    monkeypatch.setattr(hotkeys.sys, "platform", "darwin")
    monkeypatch.setattr(hotkeys.keyboard, "Listener", _FakeListener)
    monkeypatch.setattr(hotkeys, "_MACOS_PERMISSION_PROMPTED", True)
    listener = _listener()

    listener.start()

    assert _FakeListener.starts == 1
    assert listener._watchdog_thread is None or not listener._watchdog_thread.is_alive()
    text = caplog.text
    assert "Win32 keyboard hook" not in text
    assert "Native keyboard hook unhealthy" not in text
    assert "Engaging pynput fallback" not in text
    listener.stop()


def test_darwin_permissions_prompt_once(monkeypatch, caplog):
    from voice_flow.platform import macos_native

    _FakeListener.starts = 0
    accessibility_prompts = []
    input_requests = []
    monkeypatch.setattr(hotkeys, "IS_WINDOWS", False)
    monkeypatch.setattr(hotkeys.sys, "platform", "darwin")
    monkeypatch.setattr(hotkeys.keyboard, "Listener", _FakeListener)
    monkeypatch.setattr(hotkeys, "_MACOS_PERMISSION_PROMPTED", False)
    monkeypatch.setattr(
        macos_native,
        "accessibility_trusted",
        lambda prompt=False: accessibility_prompts.append(prompt) or False,
    )
    monkeypatch.setattr(macos_native, "input_monitoring_status", lambda: -1)
    monkeypatch.setattr(
        macos_native,
        "request_input_monitoring",
        lambda: input_requests.append(True) or -1,
    )
    listener = _listener()

    listener.start()
    listener.stop()
    listener.start()

    assert accessibility_prompts.count(True) == 1
    assert len(input_requests) == 1
    assert caplog.text.count("Accessibility and Input Monitoring are required") == 1
    listener.stop()


def test_platform_defaults_switch_for_darwin_and_windows(monkeypatch):
    monkeypatch.setattr(hotkeys.sys, "platform", "darwin")
    assert hotkeys.platform_input_defaults()["hotkey_trigger"] == "cmd_option"
    assert hotkeys.platform_input_defaults()["middle_click_enabled"] is False

    monkeypatch.setattr(hotkeys.sys, "platform", "win32")
    assert hotkeys.platform_input_defaults()["hotkey_trigger"] == "ctrl_win"
    assert hotkeys.platform_input_defaults()["middle_click_enabled"] is True


def test_fresh_storage_uses_platform_hotkey_defaults(monkeypatch, tmp_path):
    from voice_flow.storage import StorageEngine

    monkeypatch.setattr(hotkeys.sys, "platform", "darwin")
    mac_settings = StorageEngine(str(tmp_path / "mac.db")).get_hotkey_settings()
    assert mac_settings["hotkey_trigger"] == "cmd_option"
    assert mac_settings["middle_click_enabled"] is False

    monkeypatch.setattr(hotkeys.sys, "platform", "win32")
    windows_settings = StorageEngine(str(tmp_path / "windows.db")).get_hotkey_settings()
    assert windows_settings["hotkey_trigger"] == "ctrl_win"
    assert windows_settings["middle_click_enabled"] is True


def test_cmd_option_starts_and_finishes_push_to_talk(monkeypatch):
    started = threading.Event()
    finished = threading.Event()
    fake_keyboard = _distinct_keyboard()
    monkeypatch.setattr(hotkeys, "keyboard", fake_keyboard)
    listener = hotkeys.InputTriggerListener(started.set, finished.set, lambda: None)
    listener.reload_config({"hotkey_trigger": "cmd_option", "dictation_trigger_mode": "ptt_only"})
    monkeypatch.setattr(hotkeys, "_is_ctrl_down", lambda: False)
    monkeypatch.setattr(hotkeys, "_is_win_down", lambda: False)
    monkeypatch.setattr(hotkeys, "_is_alt_down", lambda: False)
    monkeypatch.setattr(hotkeys, "_is_shift_down", lambda: False)

    listener._on_key_press(fake_keyboard.Key.cmd)
    listener._on_key_press(fake_keyboard.Key.alt)
    assert started.wait(0.5)
    assert listener._cmd_option_triggered is True
    listener._on_key_release(fake_keyboard.Key.alt)
    assert finished.wait(0.5)
    assert listener._cmd_option_triggered is False


def test_cmd_option_is_not_treated_as_ctrl_win(monkeypatch):
    fake_keyboard = _distinct_keyboard()
    monkeypatch.setattr(hotkeys, "keyboard", fake_keyboard)
    listener = _listener()
    listener.reload_config({"hotkey_trigger": "cmd_option"})
    monkeypatch.setattr(hotkeys, "_is_ctrl_down", lambda: True)
    monkeypatch.setattr(hotkeys, "_is_win_down", lambda: True)
    monkeypatch.setattr(hotkeys, "_is_alt_down", lambda: False)
    monkeypatch.setattr(hotkeys, "_is_shift_down", lambda: False)

    listener._on_key_press(fake_keyboard.Key.ctrl)
    listener._on_key_press(fake_keyboard.Key.cmd)

    assert listener._hotkey_triggered is False


def test_webview_import_guard_supports_darwin_ci(monkeypatch):
    monkeypatch.setattr(desktop_launcher.sys, "platform", "darwin")
    monkeypatch.setenv("CI", "1")
    assert desktop_launcher._should_import_webview() is True

    monkeypatch.setattr(desktop_launcher.sys, "platform", "linux")
    assert desktop_launcher._should_import_webview() is False
    monkeypatch.delenv("CI")
    assert desktop_launcher._should_import_webview() is True


def test_macos_pyobjc_dependencies_are_marked_for_darwin():
    root = Path(__file__).resolve().parents[1]
    required = (
        "pyobjc-core>=10.3",
        "pyobjc-framework-Cocoa>=10.3",
        "pyobjc-framework-WebKit>=10.3",
    )
    for content in (
        (root / "requirements.txt").read_text(encoding="utf-8"),
        (root / "pyproject.toml").read_text(encoding="utf-8"),
    ):
        for package in required:
            assert package in content
        assert "darwin" in content

"""Splash must not count as the app window, and the installer stays two pages."""
from __future__ import annotations

from pathlib import Path

from voice_flow.gui.early_splash import (
    APP_WINDOW_TITLES,
    BRAND_TITLE,
    SPLASH_CLASS_NAME,
    WINDOW_TITLE,
    is_startup_splash,
)

ROOT = Path(__file__).resolve().parents[1]
ISS = (ROOT / "release" / "installer" / "apf-setup.iss").read_text(encoding="utf-8")
LAUNCHER = (ROOT / "release" / "installer" / "launch_apf.pyw").read_text(encoding="utf-8")
DESKTOP = (ROOT / "src" / "voice_flow" / "gui" / "desktop_launcher.py").read_text(encoding="utf-8")


def test_splash_title_and_class_are_not_the_app_window() -> None:
    assert WINDOW_TITLE == SPLASH_CLASS_NAME == "APFEarlySplash"
    assert BRAND_TITLE == "AI Productivity Flow"
    assert WINDOW_TITLE not in APP_WINDOW_TITLES
    assert is_startup_splash("AI Productivity Flow", "APFEarlySplash")
    assert is_startup_splash("APFEarlySplash", "Chrome_WidgetWin_1")
    assert is_startup_splash("AI Productivity Flow", SPLASH_CLASS_NAME)
    # A real WebView window keeps the app title and a different class.
    assert not is_startup_splash("AI Productivity Flow", "Chrome_WidgetWin_1")
    assert not is_startup_splash("Voice Flow", "Chrome_WidgetWin_0")


def test_single_instance_check_ignores_the_splash_and_keeps_the_mutex() -> None:
    focus = DESKTOP.split("def _focus_existing_window", 1)[1].split("\ndef _get_kernel32", 1)[0]
    assert "_reject_startup_splash" in focus
    assert "APFEarlySplash" in DESKTOP
    assert 'CreateMutexW(None, False, _LAUNCHER_MUTEX_NAME)' in DESKTOP
    assert "if _focus_existing_window():" in DESKTOP
    assert "def _acquire_launcher_mutex" in DESKTOP
    # The installed shortcut entry uses the same mutex and skips the splash.
    assert 'MUTEX_NAME = "Local\\\\VoiceFlowDesktopLauncherMutex_v1"' in LAUNCHER
    assert "is_startup_splash" in LAUNCHER or "SPLASH_CLASS_NAME" in LAUNCHER
    assert "FindWindowW(None, WINDOW_TITLE)" not in LAUNCHER


def test_installer_skips_the_forced_ready_page_and_names_the_start_menu() -> None:
    assert "DefaultGroupName={#MyAppName}" in ISS
    assert r"{userprograms}\(Default)\{#MyAppName}.lnk" in ISS
    assert "PostMessageW(WizardForm.NextButton.Handle, BM_CLICK, 0, 0)" in ISS
    assert "CurPageID = wpReady" in ISS
    messages = ISS.split("[Messages]", 1)[1].split("[", 1)[0]
    assert "WizardReady=Installing AI Productivity Flow" in messages
    assert "Ready to Install" not in messages
    run = ISS.split("[Run]", 1)[1].split("[", 1)[0]
    launch = [line for line in run.splitlines() if "launch_apf.pyw" in line and "postinstall" in line]
    assert launch and "shellexec" in launch[0] and "nowait" in launch[0]
    assert "nowait postinstall skipifsilent" in run

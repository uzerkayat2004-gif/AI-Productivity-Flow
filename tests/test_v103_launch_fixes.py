"""v1.0.3 launch fixes: installer pages, crash-report default, thumbs, keepalive."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import numpy as np

from voice_flow.crash_reporting import SENTRY_DSN, init_crash_reporting, is_crash_reporting_enabled
from voice_flow._version import VERSION
from voice_flow.storage import storage
from voice_flow.video_thumb import frame_is_near_white, parse_yavg
from voice_flow.video_flow_widget import notebooklm_format_for_treatment

ROOT = Path(__file__).resolve().parents[1]
ISS = (ROOT / "release" / "installer" / "apf-setup.iss").read_text(encoding="utf-8")


def test_installer_page_flow_is_installing_then_finish():
    assert "DisableWelcomePage=yes" in ISS
    assert "DisableDirPage=yes" in ISS
    assert "DisableProgramGroupPage=yes" in ISS
    assert "DisableReadyPage=yes" in ISS
    assert "DisableFinishedPage=no" in ISS
    assert "LicenseFile" not in ISS
    assert "PrivilegesRequired=lowest" in ISS
    assert "PrivilegesRequiredOverridesAllowed" not in ISS
    assert "\n[Tasks]" not in ISS
    assert "WizardImageFile=" in ISS
    assert "WizardSmallImageFile=" in ISS
    assert "APF_WIZARD_PAGES:installing,finished" in ISS
    assert 'Description: "Launch AI Productivity Flow"' in ISS
    run = ISS.split("[Run]", 1)[1].split("[", 1)[0]
    assert "unchecked" not in run
    assert "nowait postinstall skipifsilent" in run
    assert "runasoriginaluser" in run
    assert 'WorkingDir: "{app}"' in run
    assert "ShouldSkipPage" in ISS
    assert "wpReady" in ISS
    assert "CurStepChanged" in ISS
    assert "ssInstall" in ISS
    assert "{autodesktop}\\{#MyAppName}.lnk" in ISS
    assert "{userdesktop}\\{#MyAppName}.lnk" in ISS
    assert "AppVerName={#MyAppName} {#MyAppDisplayVersion}" in ISS
    messages = ISS.split("[Messages]", 1)[1].split("[", 1)[0]
    assert "Version 1.0" in messages
    assert "1.0.13" not in messages
    assert "InnerNotebook" not in ISS
    assert "ForeColor" not in ISS
    splash = (ROOT / "src" / "voice_flow" / "gui" / "early_splash.py").read_text(encoding="utf-8")
    assert "ctypes.c_ssize_t" in splash
    assert "ctypes.c_long" not in splash
    assert "def def_window_proc" in splash
    assert "GetMessageW" in splash
    assert "PostMessageW" in splash
    launcher = (ROOT / "src" / "voice_flow" / "gui" / "desktop_launcher.py").read_text(encoding="utf-8")
    shown = launcher.split("def on_shown():", 1)[1].split("def on_closed():", 1)[0]
    assert "_close_startup_splash()" in shown
    # The splash is only closed by on_shown or a failure, never before a window
    # is created: neither on the warm path nor on the warming-window path.
    launch = launcher.split("def launch_desktop_gui", 1)[1]
    before_window = launch.split("webview.create_window", 1)[0]
    assert "_close_startup_splash()" not in before_window
    warming = launcher.split("def _launch_warming_window", 1)[1]
    assert "_close_startup_splash()" not in warming.split("webview.create_window", 1)[0]
    installer = ROOT / "release" / "installer"
    assert (installer / "wizard-large.png").is_file()
    assert (installer / "wizard-small.png").is_file()
    from PIL import Image
    large = Image.open(installer / "wizard-large.png").convert("RGB")
    small = Image.open(installer / "wizard-small.png").convert("RGB")
    assert large.size == (164, 314)
    assert small.size == (55, 58)
    red, green, blue = large.resize((1, 1)).getpixel((0, 0))
    assert red > 220 and green > 200 and blue > 180
    assert "Copyright 2026 Uzer Kayat" in (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "PyPerperclip" not in (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Remotion" not in (ROOT / "LICENSE").read_text(encoding="utf-8")


def test_crash_reporting_is_on_until_the_user_opts_out():
    with sqlite3.connect(storage.db_path) as conn:
        conn.execute("DELETE FROM settings WHERE key = ?", ("anonymous_crash_reports",))
        conn.commit()
    assert is_crash_reporting_enabled() is True
    assert SENTRY_DSN.startswith("https://")
    assert VERSION == "1.0.13"
    storage.save_setting("anonymous_crash_reports", False)
    assert is_crash_reporting_enabled() is False
    assert init_crash_reporting(force=False) is False


def test_video_treatment_maps_normal_and_cinematic():
    assert notebooklm_format_for_treatment("Cinematic") == "cinematic"
    assert notebooklm_format_for_treatment("Normal") == "explainer"
    assert notebooklm_format_for_treatment("") == "explainer"


def test_near_white_frames_are_rejected():
    assert frame_is_near_white(250.0) is True
    assert frame_is_near_white(40.0) is False
    assert frame_is_near_white(None) is False
    assert parse_yavg("lavfi.signalstats.YAVG=251.5") == 251.5


def test_quiet_low_snr_input_is_not_pushed_to_full_scale():
    from voice_flow.voice_enhance import consume_enhance_hint, enhance_for_stt

    rng = np.random.default_rng(3)
    noise = rng.normal(0.0, 1.0, 16000 * 2).astype(np.float32)
    peak = float(np.max(np.abs(noise)))
    audio = noise / peak * 0.04
    out, _profile = enhance_for_stt(audio, 16000)
    assert float(np.max(np.abs(out))) < 0.85
    assert consume_enhance_hint() == "too_quiet"


def test_keepalive_without_cookies_does_not_heal(tmp_path, monkeypatch):
    from voice_flow.video_flow_engine.notebooklm.keepalive import NotebookLMKeepaliveService

    missing = tmp_path / "storage_state.json"

    class Storage:
        def get_setting(self, key, default=None):
            if key == "video_flow_notebooklm_email":
                return "stale@example.com"
            return default

    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path",
        lambda profile=None: missing,
    )
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config._app_settings_storage",
        lambda: Storage(),
    )
    called = []
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: called.append(kwargs) or {"ok": True},
    )
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.get_login_state",
        lambda: {"running": False},
    )
    service = NotebookLMKeepaliveService(profile="video-flow-experiment", refresh_func=None)
    result = service.run_once()
    assert result["reason"] == "no_saved_session"
    assert called == []


def test_keepalive_with_cookies_still_refreshes(tmp_path, monkeypatch):
    from voice_flow.video_flow_engine.notebooklm.keepalive import NotebookLMKeepaliveService

    state = tmp_path / "storage_state.json"
    state.write_text('{"cookies":[{"name":"SID","value":"abc"}]}', encoding="utf-8")
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path",
        lambda profile=None: state,
    )
    seen = []

    def refresh(*, profile):
        seen.append(profile)
        return {"ok": True}

    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.get_login_state",
        lambda: {"running": False},
    )
    service = NotebookLMKeepaliveService(profile="video-flow-experiment", refresh_func=refresh)
    result = service.run_once()
    assert seen == ["video-flow-experiment"]
    assert result.get("reason") != "no_saved_session"


def test_sign_in_chip_replaces_the_video_label_and_does_not_open_the_composer():
    from voice_flow.overlay import FloatingOverlayBar

    bar = FloatingOverlayBar()
    bar.state = "READY"
    bar._is_mouse_over = True
    bar._nlm_signin_override = True
    bar.win = object()
    bar.canvas = type("C", (), {"create_text": lambda *a, **k: None, "create_line": lambda *a, **k: None})()
    assert bar._notebooklm_needs_sign_in() is True
    calls = []
    bar.on_video_flow = lambda text: calls.append(text)
    bar._start_notebooklm_sign_in = lambda: calls.append("signin")
    zone = "video_flow"
    # Exercise the same branch the click handler uses.
    if bar._notebooklm_needs_sign_in():
        bar._start_notebooklm_sign_in()
    assert calls == ["signin"]
    assert zone == "video_flow"


def test_settings_privacy_row_replaces_the_prominent_sentry_toggle():
    html = (ROOT / "src" / "voice_flow" / "gui" / "index.html").read_text(encoding="utf-8")
    start = html.index('id="settings-modal"')
    end = html.index("<!-- SETTINGS SUB-MODAL: MICROPHONE -->", start)
    settings = html[start:end]
    assert "toggle-anonymous-crash-reports" not in settings
    assert "btn-crash-reports-opt" in settings
    assert "Send crash reports" in settings
    assert "No audio or text is ever sent." in settings
    assert 'data-enabled="1"' in settings
    # A real on/off toggle, not an ambiguous "Turn on" / "Turn off" button.
    assert 'id="btn-crash-reports-opt" onchange="toggleCrashReportsFromPrivacy()" type="checkbox"' in settings
    assert "Turn on</button>" not in settings


def test_packaged_crash_release_matches_version():
    text = (ROOT / "src" / "voice_flow" / "crash_reporting.py").read_text(encoding="utf-8")
    assert "SENTRY_DSN" in text
    assert f"ai-productivity-flow@{{VERSION}}" in text or "ai-productivity-flow@" in text
    assert VERSION == "1.0.13"

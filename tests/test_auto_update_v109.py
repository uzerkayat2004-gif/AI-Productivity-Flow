"""v1.0.9: automatic background updates, the Update ready notice, and a simpler Settings page."""

from __future__ import annotations

import hashlib
import json
import struct
import threading
import time
import zipfile
from pathlib import Path

import pytest

from tests.test_api_server import _get, _post, test_server  # noqa: F401
from voice_flow import app_updater
from voice_flow.app_updater import (
    APPLY_ON_LAUNCH_NAME,
    AutoUpdater,
    UpdateManager,
    apply_deferred_update_on_launch,
    auto_update_enabled,
    inspect_app_zip,
    set_auto_update_enabled,
)

ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "src" / "voice_flow" / "gui"
BASE = "https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases/download/v1.0.9/"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICE_FLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("APF_AUTO_UPDATE", raising=False)
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(app_updater, "update_state_dir", lambda: state)
    monkeypatch.setattr(app_updater, "AUTO_CHUNK_PAUSE_SECONDS", 0.0)
    monkeypatch.setattr(app_updater.tempfile, "gettempdir", lambda: str(tmp_path / "tmp"))
    yield state


def _app_zip(path: Path) -> bytes:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"version": "1.0.9", "runtime": {}}))
        archive.writestr("voice_flow/main.py", "print('new')\n")
        archive.writestr("voice_flow/__init__.py", "")
    return path.read_bytes()


def _plan(kind: str = "app") -> dict:
    name = "AI-Productivity-Flow-app-update-win.zip" if kind == "app" else "AI-Productivity-Flow-Setup-x64.exe"
    return {
        "kind": kind,
        "platform": "win",
        "asset_name": name,
        "download_url": BASE + name,
        "sha256_url": BASE + name + ".sha256",
        "size_bytes": None,
        "size_label": "8.0 MB",
        "install_label": "Restart to update",
        "version": "1.0.9",
    }


def _fake_download(payload: bytes, sha_text: str):
    def fake(url, dest, *, progress=None, cancel_event=None, timeout=30.0, opener=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        if url.endswith(".sha256"):
            dest.write_text(sha_text, encoding="utf-8")
        else:
            dest.write_bytes(payload)
            if progress:
                progress(len(payload) // 2, len(payload))
                progress(len(payload), len(payload))
        return dest
    return fake


def _check_result(kind: str = "app") -> dict:
    return {"checked": True, "error": None, "update_available": True, "latest_version": "1.0.9", "update_plan": _plan(kind)}


# --- scheduling -------------------------------------------------------------

def test_background_checks_start_after_thirty_seconds_then_hourly(monkeypatch):
    assert app_updater.AUTO_CHECK_FIRST_DELAY_SECONDS == 30.0
    assert app_updater.AUTO_CHECK_INTERVAL_SECONDS == 60 * 60
    calls = []
    monkeypatch.setattr(AutoUpdater, "start", lambda self, first_delay, interval=0: calls.append(first_delay) or True)
    monkeypatch.setattr(app_updater, "_auto_updater", None)
    assert app_updater.schedule_auto_updates() is True
    assert calls == [30.0]
    monkeypatch.setenv("APF_AUTO_UPDATE", "0")
    assert app_updater.schedule_auto_updates() is False


def test_loop_retries_sooner_when_offline_and_stops_cleanly(monkeypatch):
    manager = UpdateManager()
    outcomes = []

    def offline():
        raise OSError("no internet")

    updater = AutoUpdater(manager, check=offline, enabled=lambda: True)
    seen_delays = []
    real_wait = updater._stop.wait

    def fake_wait(delay):
        seen_delays.append(delay)
        if len(seen_delays) >= 3:
            return True
        return False

    updater._stop.wait = fake_wait  # type: ignore[method-assign]
    updater._loop(120.0, 6 * 3600.0)
    outcomes.append(updater.last_outcome)
    assert seen_delays[0] == 120.0
    assert seen_delays[1] == app_updater.AUTO_RETRY_SECONDS
    assert outcomes == ["offline"]
    assert real_wait  # untouched original


def test_startup_schedules_the_check_in_finish_startup_not_before():
    source = (ROOT / "src" / "voice_flow" / "main.py").read_text(encoding="utf-8")
    finish = source.split("def _finish_startup", 1)[1].split("\n    def ", 1)[0]
    assert "schedule_auto_updates()" in finish
    run = source.split("    def run(self) -> None:", 1)[1].split("\n    def ", 1)[0]
    assert run.index("apply_deferred_update_on_launch") < run.index("self.hotkeys.start()")


# --- what gets downloaded ---------------------------------------------------

def test_auto_download_only_for_the_small_app_zip(monkeypatch):
    manager = UpdateManager()
    started = []
    monkeypatch.setattr(manager, "start", lambda origin="manual": started.append(origin) or {})
    full = AutoUpdater(manager, check=lambda: _check_result("full"), enabled=lambda: True)
    assert full.run_once() == "full-only"
    assert started == []
    assert manager.plan and manager.plan["kind"] == "full"  # the button stays available
    manager.plan = None
    app = AutoUpdater(manager, check=lambda: _check_result("app"), enabled=lambda: True)
    assert app.run_once() == "downloading"
    assert started == ["auto"]


def test_offline_and_up_to_date_are_silent():
    manager = UpdateManager()
    assert AutoUpdater(manager, check=lambda: {"checked": False, "error": "timed out"}, enabled=lambda: True).run_once() == "offline"
    assert AutoUpdater(manager, check=lambda: {"checked": True, "update_available": False}, enabled=lambda: True).run_once() == "up-to-date"
    assert manager.state == "idle"


def test_toggle_off_means_no_check_and_no_download(monkeypatch):
    assert auto_update_enabled() is True  # on by default
    set_auto_update_enabled(False)
    assert auto_update_enabled() is False
    manager = UpdateManager()
    called = []
    updater = AutoUpdater(manager, check=lambda: called.append(1) or _check_result())
    assert updater.run_once() == "disabled"
    assert called == [] and manager.state == "idle"
    set_auto_update_enabled(True)
    assert auto_update_enabled() is True


def test_verified_download_is_staged(monkeypatch, tmp_path):
    payload = _app_zip(tmp_path / "pkg.zip")
    sha = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(app_updater, "download_file", _fake_download(payload, f"{sha}  pkg.zip\n"))
    monkeypatch.setattr(app_updater, "runtimes_match", lambda a, b: True)
    manager = UpdateManager()
    updater = AutoUpdater(manager, check=lambda: _check_result("app"), enabled=lambda: True)
    assert updater.run_once(wait=True) == "staged"
    status = manager.status()
    assert status["state"] == "ready" and status["origin"] == "auto"
    assert status["latest_version"] == "1.0.9"
    assert manager.path is not None and manager.path.is_file()


def test_hash_failure_is_never_staged(monkeypatch, tmp_path):
    payload = _app_zip(tmp_path / "pkg.zip")
    monkeypatch.setattr(app_updater, "download_file", _fake_download(payload, "0" * 64 + "  pkg.zip\n"))
    manager = UpdateManager()
    updater = AutoUpdater(manager, check=lambda: _check_result("app"), enabled=lambda: True)
    assert updater.run_once(wait=True) == "failed"
    assert manager.state == "failed"
    assert manager.path is None
    assert not (tmp_path / "tmp" / "AI-Productivity-Flow" / "updates" / _plan()["asset_name"]).exists()
    # A second failure for the same version and the background stops retrying it.
    manager.state = "idle"
    updater.run_once(wait=True)
    manager.state = "idle"
    assert updater.run_once(wait=True) == "gave-up"


def test_package_the_restart_would_refuse_is_not_staged(monkeypatch, tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("voice_flow/main.py", "")  # no manifest
    payload = bad.read_bytes()
    sha = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(app_updater, "download_file", _fake_download(payload, sha))
    manager = UpdateManager()
    assert AutoUpdater(manager, check=lambda: _check_result(), enabled=lambda: True).run_once(wait=True) == "failed"
    assert "manifest" in manager.error
    with pytest.raises(app_updater.UpdateError):
        inspect_app_zip(bad)


# --- restart, Later, and busy deferral --------------------------------------

def _ready_manager(tmp_path) -> UpdateManager:
    manager = UpdateManager()
    archive = tmp_path / "staged.zip"
    _app_zip(archive)
    manager.adopt_staged(_plan(), archive)
    return manager


def test_restart_applies_the_staged_update_when_idle(monkeypatch, tmp_path):
    manager = _ready_manager(tmp_path)
    applied = []
    monkeypatch.setattr(manager, "_begin_app_install", lambda plan, archive: applied.append(archive) or {"success": True, "state": "installing"})
    manager.busy_check = lambda: None
    result = manager.request_restart()
    assert result["state"] == "installing"
    assert applied == [tmp_path / "staged.zip"]


def test_restart_waits_while_dictation_or_a_job_is_running(monkeypatch, tmp_path):
    monkeypatch.setattr(app_updater, "AUTO_IDLE_POLL_SECONDS", 0.02)
    manager = _ready_manager(tmp_path)
    applied = threading.Event()
    monkeypatch.setattr(manager, "_begin_app_install", lambda plan, archive: applied.set() or {"success": True})
    busy = {"reason": "Finish the current dictation before continuing."}
    manager.busy_check = lambda: busy["reason"]
    status = manager.request_restart()
    assert status["state"] == "waiting"
    assert status["busy_reason"].startswith("Finish the current dictation")
    time.sleep(0.1)
    assert not applied.is_set()
    busy["reason"] = None
    assert applied.wait(2.0)


def test_later_installs_on_next_launch_once(monkeypatch, tmp_path, _isolated):
    manager = _ready_manager(tmp_path)
    status = manager.defer()
    assert status["deferred"] is True
    marker = _isolated / APPLY_ON_LAUNCH_NAME
    assert marker.is_file()
    monkeypatch.setattr(app_updater, "VERSION", "1.0.8")
    data = json.loads(marker.read_text())
    data["from_version"] = "1.0.8"
    marker.write_text(json.dumps(data))
    launched = UpdateManager()
    applied = []
    monkeypatch.setattr(launched, "_begin_app_install", lambda plan, archive: applied.append(archive) or {"success": True})
    assert apply_deferred_update_on_launch(launched) is True
    assert applied == [tmp_path / "staged.zip"]
    assert not marker.exists()  # consumed first: a failed apply cannot loop
    assert apply_deferred_update_on_launch(launched) is False


def test_deferred_update_skipped_when_already_installed_or_toggle_off(monkeypatch, tmp_path, _isolated):
    manager = _ready_manager(tmp_path)
    manager.defer()  # VERSION is 1.0.9 here, same as the staged update
    assert apply_deferred_update_on_launch(UpdateManager()) is False
    manager.defer()
    set_auto_update_enabled(False)
    assert not (_isolated / APPLY_ON_LAUNCH_NAME).exists()


def test_background_check_does_not_replace_a_staged_update(tmp_path):
    manager = _ready_manager(tmp_path)
    assert AutoUpdater(manager, check=lambda: _check_result(), enabled=lambda: True).run_once() == "busy"
    manager.remember({"kind": "full"})
    assert manager.plan["kind"] == "app"


# --- API --------------------------------------------------------------------

def test_auto_update_api_toggle_and_later(test_server, monkeypatch, tmp_path):
    base = test_server["base_url"]
    code, _h, body = _get(base + "/api/updates/auto")
    assert code == 200 and body["enabled"] is True
    code, _h, body = _post(base + "/api/updates/auto", {"enabled": False})
    assert code == 200 and body["enabled"] is False
    assert _get(base + "/api/updates/auto")[2]["enabled"] is False
    assert _post(base + "/api/updates/auto", {"enabled": "yes"})[0] == 400
    _post(base + "/api/updates/auto", {"enabled": True})
    manager = _ready_manager(tmp_path)
    monkeypatch.setattr("voice_flow.app_updater._manager", manager)
    code, _h, body = _get(base + "/api/updates/progress")
    assert body["state"] == "ready" and body["origin"] == "auto" and body["auto_update_enabled"] is True
    code, _h, body = _post(base + "/api/updates/later", {})
    assert code == 200 and body["deferred"] is True


def test_install_endpoint_waits_when_busy(test_server, monkeypatch, tmp_path):
    manager = _ready_manager(tmp_path)
    monkeypatch.setattr("voice_flow.app_updater._manager", manager)
    monkeypatch.setattr(app_updater, "AUTO_IDLE_POLL_SECONDS", 5.0)
    from voice_flow.gui import api_server
    monkeypatch.setattr(api_server, "settings_busy_reason", lambda: "Finish the current recording before changing this setting.")
    manager.busy_check = None
    code, _h, body = _post(test_server["base_url"] + "/api/updates/install", {})
    assert code == 200 and body["state"] == "waiting"
    manager.cancel()  # stop the idle watcher


# --- UI ---------------------------------------------------------------------

def test_settings_shows_the_toggle_and_hides_rare_rows_under_advanced():
    html = (GUI / "index.html").read_text(encoding="utf-8")
    system = html.split("<!-- TAB: SYSTEM -->", 1)[1].split("<!-- TAB: ACCOUNT -->", 1)[0]
    assert 'id="toggle-auto-updates"' in system
    assert "Automatic updates" in system and "Downloads updates in the background." in system
    advanced = system.split('<details class="settings-advanced" id="settings-advanced">', 1)[1].split("</details>", 1)[0]
    for needle in ("triggerDeepAppRestart()", "clearAudioRecordingsCache()", "replayOnboarding()", "runtime-os-badge", "runtime-tip-span"):
        assert needle in advanced
        assert system.count(needle) == 1
    assert "<details" in system and " open" not in system.split("<details", 1)[1].split(">", 1)[0]
    essentials = system.split("<details", 1)[0]
    for needle in ("toggle-autostart", "btn-check-updates", "update-status-row", "btn-crash-reports-opt"):
        assert needle in essentials


def test_update_ready_notice_copy_and_wiring():
    html = (GUI / "index.html").read_text(encoding="utf-8")
    toast = html.split('id="apf-update-toast"', 1)[1].split("</div>\n  </div>", 1)[0]
    assert "Update ready" in toast and "Restart to update" in toast and "Later" in toast
    script = (GUI / "app.js").read_text(encoding="utf-8")
    for needle in ("/api/updates/later", "/api/updates/auto", "Downloading update…", "Restarts when you're done.", "Installs next time you open Flow."):
        assert needle in script


def test_windows_icon_has_every_size_with_classic_small_entries():
    from PIL import Image

    ico_path = GUI / "assets" / "icon.ico"
    sizes = set(Image.open(ico_path).info["sizes"])
    for size in (16, 24, 32, 48, 64, 256):
        assert (size, size) in sizes
    data = ico_path.read_bytes()
    count = struct.unpack("<HHH", data[:6])[2]
    for index in range(count):
        width, _h, _c, _r, _p, bpp, length, offset = struct.unpack("<BBBBHHII", data[6 + 16 * index:22 + 16 * index])
        is_png = data[offset:offset + 4] == b"\x89PNG"
        assert bpp == 32
        # Classic DIB below 256 px (what every Windows API and Inno Setup's
        # Delphi runtime load), PNG only for the 256 px entry.
        assert is_png == (width == 0)


def test_installer_uses_the_logo_and_ties_shortcuts_to_the_app_id():
    iss = (ROOT / "release" / "installer" / "apf-setup.iss").read_text(encoding="utf-8")
    assert "SetupIconFile={#SetupIconPath}" in iss
    assert "\\src\\voice_flow\\gui\\assets\\icon.ico" in iss
    assert "UninstallDisplayIcon=" in iss and "WizardImageFile=" in iss and "WizardSmallImageFile=" in iss
    launcher = (GUI / "desktop_launcher.py").read_text(encoding="utf-8")
    app_id = launcher.split("myappid = '", 1)[1].split("'", 1)[0]
    assert f'#define MyAppUserModelID "{app_id}"' in iss
    icons = iss.split("[Icons]", 1)[1].split("\n[", 1)[0]
    assert icons.count('AppUserModelID: "{#MyAppUserModelID}"') == 2


# --- automatic restart after a verified small update (v1.0.11) -------------

def test_verified_app_update_restarts_by_itself(monkeypatch, tmp_path):
    monkeypatch.setenv("APF_TEST_AUTO_RESTART", "1")
    monkeypatch.setattr(app_updater, "AUTO_RESTART_GRACE_SECONDS", 0.0)
    monkeypatch.setattr(app_updater, "auto_update_enabled", lambda: True)
    manager = app_updater.UpdateManager()
    calls = []
    monkeypatch.setattr(manager, "request_restart", lambda: calls.append("restart") or {})
    manager.plan = {"kind": "app", "version": "9.9.9"}
    manager.state = "ready"
    manager._schedule_auto_restart()
    import time as _t
    deadline = _t.time() + 3
    while not calls and _t.time() < deadline:
        _t.sleep(0.02)
    assert calls == ["restart"]
    assert "Restarting" in (manager.message or "")


def test_deferred_update_does_not_auto_restart(monkeypatch):
    monkeypatch.setenv("APF_TEST_AUTO_RESTART", "1")
    monkeypatch.setattr(app_updater, "AUTO_RESTART_GRACE_SECONDS", 0.05)
    manager = app_updater.UpdateManager()
    calls = []
    monkeypatch.setattr(manager, "request_restart", lambda: calls.append("restart") or {})
    manager.plan = {"kind": "app"}
    manager.state = "ready"
    manager._schedule_auto_restart()
    manager.deferred = True
    import time as _t
    _t.sleep(0.3)
    assert calls == []


def test_unit_tests_never_auto_restart_without_opt_in(monkeypatch):
    monkeypatch.delenv("APF_TEST_AUTO_RESTART", raising=False)
    assert app_updater._auto_restart_allowed() is False

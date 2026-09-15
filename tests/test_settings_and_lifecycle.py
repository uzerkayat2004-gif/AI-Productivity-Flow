"""Tests for Voice Flow Settings Features, Windows Auto-Startup, and Deep App Restart."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import MagicMock, patch

import pytest

from voice_flow.gui import api_server
from voice_flow.storage import StorageEngine
from voice_flow import installer
from voice_flow import lifecycle


@pytest.fixture
def test_server(monkeypatch, tmp_path):
    db_path = str(tmp_path / "voice_flow_settings_test.db")
    test_storage = StorageEngine(db_path)
    monkeypatch.setattr(api_server, "storage", test_storage)

    # Set up a test audio archive
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    from voice_flow.recovery import AudioArchive
    test_archive = AudioArchive(root=audio_dir)
    monkeypatch.setattr(api_server, "archive", test_archive)

    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    server.daemon_threads = True
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.15)
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"

    yield {
        "base_url": base_url,
        "storage": test_storage,
        "archive": test_archive,
        "server": server,
    }

    server.shutdown()
    server.server_close()


def _get(url: str) -> tuple[int, dict, dict]:
    req = urllib.request.Request(url, headers={"Connection": "close"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            headers = dict(resp.headers)
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, headers, body
    except urllib.error.HTTPError as e:
        headers = dict(e.headers)
        body = json.loads(e.read().decode("utf-8"))
        return e.code, headers, body


def _post(url: str, payload: dict) -> tuple[int, dict, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Connection": "close"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            headers = dict(resp.headers)
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, headers, body
    except urllib.error.HTTPError as e:
        headers = dict(e.headers)
        body = json.loads(e.read().decode("utf-8"))
        return e.code, headers, body


# =========================================================================
# 1. AUTO-STARTUP INSTALLER TESTS
# =========================================================================

def test_installer_is_registry_autorun_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_key = MagicMock()
    mock_open_key = MagicMock(return_value=mock_key)
    mock_key.__enter__.return_value = mock_key
    mock_query_val = MagicMock(return_value=('wscript.exe "C:\\fake\\VoiceFlowLauncher.vbs"', 1))

    monkeypatch.setattr(installer.winreg, "OpenKey", mock_open_key)
    monkeypatch.setattr(installer.winreg, "QueryValueEx", mock_query_val)

    assert installer.is_registry_autorun_enabled() is True

    # When query fails or value is missing
    mock_query_val.side_effect = FileNotFoundError()
    assert installer.is_registry_autorun_enabled() is False


def test_installer_set_autostart_enable_and_disable(monkeypatch: pytest.MonkeyPatch) -> None:
    reg_calls = []
    su_calls = []

    monkeypatch.setattr(installer, "register_registry_autorun", lambda: (reg_calls.append("reg_on"), True)[1])
    monkeypatch.setattr(installer, "unregister_registry_autorun", lambda: (reg_calls.append("reg_off"), True)[1])
    monkeypatch.setattr(installer, "unregister_startup_folder", lambda: (su_calls.append("su_off"), True)[1])

    # Enable autostart: registers registry autorun and unregisters startup folder
    res_enable = installer.set_autostart(True)
    assert res_enable is True
    assert "reg_on" in reg_calls
    assert "su_off" in su_calls

    # Disable autostart: unregisters both
    res_disable = installer.set_autostart(False)
    assert res_disable is True
    assert "reg_off" in reg_calls


# =========================================================================
# 2. DESKTOP LAUNCHER AUTO-STARTUP LOGIC
# =========================================================================

def test_desktop_launcher_respects_stored_autostart_setting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from voice_flow.gui import desktop_launcher

    set_calls = []
    monkeypatch.setattr(desktop_launcher, "set_windows_auto_startup", lambda en: set_calls.append(en))
    monkeypatch.setattr(desktop_launcher, "ensure_backend_running", lambda: None)
    monkeypatch.setattr(desktop_launcher, "is_api_server_ready", lambda timeout=0.2: True)
    monkeypatch.setattr(desktop_launcher, "_focus_existing_window", lambda: False)

    mock_webview = MagicMock()
    mock_window = MagicMock()
    mock_webview.create_window.return_value = mock_window
    monkeypatch.setattr(desktop_launcher, "webview", mock_webview)

    # Test when autostart_enabled is explicitly False in storage
    db_path = str(tmp_path / "launcher_test_off.db")
    test_storage = StorageEngine(db_path)
    test_storage.save_setting("autostart_enabled", False)
    monkeypatch.setattr("voice_flow.storage.storage", test_storage)

    desktop_launcher.launch_desktop_gui()
    assert set_calls == [False]


# =========================================================================
# 3. LIFECYCLE & DEEP RESTART MANAGER TESTS
# =========================================================================

def test_lifecycle_terminate_suite_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    # Create fake processes: one main, one watchdog, one foreign python process
    p_main = MagicMock()
    p_main.pid = 1111
    p_main.info = {"pid": 1111, "name": "python.exe", "cmdline": ["python.exe", "-m", "voice_flow.main"]}
    p_watchdog = MagicMock()
    p_watchdog.pid = 2222
    p_watchdog.info = {"pid": 2222, "name": "python.exe", "cmdline": ["python.exe", "-m", "voice_flow.watchdog"]}
    p_foreign = MagicMock()
    p_foreign.pid = 3333
    p_foreign.info = {"pid": 3333, "name": "python.exe", "cmdline": ["python.exe", "other_script.py"]}

    mock_psutil = MagicMock()
    mock_psutil.process_iter.return_value = [p_main, p_watchdog, p_foreign]
    mock_psutil.wait_procs.return_value = ([], [])

    monkeypatch.setitem(sys.modules, "psutil", mock_psutil)

    term_pids = lifecycle.terminate_suite_processes()
    assert 1111 in term_pids
    assert 2222 in term_pids
    assert 3333 not in term_pids

    p_main.terminate.assert_called_once()
    p_watchdog.terminate.assert_called_once()
    p_foreign.terminate.assert_not_called()


def test_lifecycle_terminate_suite_processes_with_path_separators(monkeypatch: pytest.MonkeyPatch) -> None:
    # Verify that python processes launched with file paths (e.g. src\voice_flow\main.py) are matched
    p_main_path = MagicMock()
    p_main_path.pid = 4444
    p_main_path.info = {"pid": 4444, "name": "python.exe", "cmdline": ["python.exe", r"src\voice_flow\main.py"]}

    mock_psutil = MagicMock()
    mock_psutil.process_iter.return_value = [p_main_path]
    mock_psutil.wait_procs.return_value = ([], [])

    monkeypatch.setitem(sys.modules, "psutil", mock_psutil)

    term_pids = lifecycle.terminate_suite_processes()
    assert 4444 in term_pids
    p_main_path.terminate.assert_called_once()


def test_lifecycle_relaunch_suite_vbs_and_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    popen_calls = []

    def fake_popen(cmd, **kwargs):
        popen_calls.append(cmd)
        return MagicMock()

    monkeypatch.setattr(lifecycle.subprocess, "Popen", fake_popen)

    # 1. When VBS launcher exists
    fake_vbs = tmp_path / "VoiceFlowLauncher.vbs"
    fake_vbs.write_text("Set WshShell = CreateObject('WScript.Shell')")
    monkeypatch.setattr(installer, "get_vbs_launcher_path", lambda: fake_vbs)

    ok1 = lifecycle.relaunch_suite()
    assert ok1 is True
    assert len(popen_calls) == 1
    assert "wscript.exe" in popen_calls[0][0].lower() or "VoiceFlowLauncher.vbs" in str(popen_calls[0][1])

    # 2. When VBS launcher does NOT exist -> fallback to python.exe -m voice_flow.gui.desktop_launcher
    monkeypatch.setattr(installer, "get_vbs_launcher_path", lambda: tmp_path / "nonexistent.vbs")
    monkeypatch.setattr(lifecycle, "_get_python_exe", lambda: "python.exe")

    ok2 = lifecycle.relaunch_suite()
    assert ok2 is True
    assert len(popen_calls) == 2
    assert "voice_flow.gui.desktop_launcher" in popen_calls[1]


def test_lifecycle_clean_runtime_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lifecycle, "data_dir", lambda: tmp_path)
    lock_file = tmp_path / "watchdog.lock"
    flag_file = tmp_path / "watchdog_shutdown.flag"
    lock_file.write_text("1234")
    flag_file.write_text("shutdown")

    lifecycle.clean_runtime_artifacts()
    assert not lock_file.exists()
    assert not flag_file.exists()


def test_lifecycle_restart_suite_spawns_detached_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_controller = MagicMock()
    mock_popen = MagicMock()
    monkeypatch.setattr(lifecycle.subprocess, "Popen", mock_popen)

    ok = lifecycle.restart_suite(runtime_controller=mock_controller)
    assert ok is True

    # Check that overlay reset_position was called
    mock_controller.overlay.reset_position.assert_called_once()
    # Check that audio stop was called
    mock_controller.audio.stop.assert_called_once()

    # Check detached process spawn
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    cmd = args[0]
    assert "-m" in cmd
    assert "voice_flow.lifecycle" in cmd
    assert "--execute-restart" in cmd


# =========================================================================
# 4. API SERVER SETTINGS & RESTART ENDPOINTS TESTS
# =========================================================================

def test_api_app_restart_endpoint(test_server, monkeypatch: pytest.MonkeyPatch) -> None:
    base_url = test_server["base_url"]
    restart_calls = []

    def fake_restart(ctrl=None):
        restart_calls.append(ctrl)
        return True

    monkeypatch.setattr(lifecycle, "restart_suite", fake_restart)
    # Also patch in api_server module scope
    monkeypatch.setattr("voice_flow.lifecycle.restart_suite", fake_restart)

    status, headers, body = _post(f"{base_url}/api/app/restart", {})
    assert status == 200
    assert "application/json" in headers.get("Content-Type", "")
    assert body["success"] is True
    assert "restarting" in body.get("message", "").lower()
    assert len(restart_calls) == 1


def test_api_autostart_status_and_toggle(test_server, monkeypatch: pytest.MonkeyPatch) -> None:
    base_url = test_server["base_url"]

    # 1. GET autostart status
    monkeypatch.setattr(installer, "is_autostart_enabled", lambda: False)
    status, headers, body = _get(f"{base_url}/api/settings/autostart/status")
    assert status == 200
    assert body["success"] is True
    assert body["enabled"] is False

    # 2. POST autostart toggle -> ON
    autostart_calls = []
    monkeypatch.setattr(installer, "set_autostart", lambda en: (autostart_calls.append(en), True)[1])
    status, headers, body = _post(f"{base_url}/api/settings/autostart/toggle", {"enabled": True})
    assert status == 200
    assert body["success"] is True
    assert body["enabled"] is True
    assert autostart_calls == [True]
    assert test_server["storage"].get_setting("autostart_enabled") is True

    # 3. GET autostart status reflects stored setting
    status, headers, body = _get(f"{base_url}/api/settings/autostart/status")
    assert status == 200
    assert body["enabled"] is True

    # 4. POST autostart toggle -> OFF
    status, headers, body = _post(f"{base_url}/api/settings/autostart/toggle", {"enabled": False})
    assert status == 200
    assert body["success"] is True
    assert body["enabled"] is False
    assert autostart_calls == [True, False]
    assert test_server["storage"].get_setting("autostart_enabled") is False


def test_api_settings_get_all_types_and_defaults(test_server) -> None:
    base_url = test_server["base_url"]
    storage = test_server["storage"]

    # Default values when not explicitly in DB
    status, _, body = _get(f"{base_url}/api/settings/get?key=push_to_talk_shortcut")
    assert status == 200
    assert body["value"] == "Ctrl+Win"
    assert isinstance(body["value"], str)

    status, _, body = _get(f"{base_url}/api/settings/get?key=dictation_trigger_mode")
    assert status == 200
    assert body["value"] == "hybrid"
    assert isinstance(body["value"], str)

    status, _, body = _get(f"{base_url}/api/settings/get?key=click_to_paste_enabled")
    assert status == 200
    assert body["value"] is False

    # Updated values reflect typed content
    storage.save_setting("push_to_talk_shortcut", "Alt+Space")
    status, _, body = _get(f"{base_url}/api/settings/get?key=push_to_talk_shortcut")
    assert status == 200
    assert body["value"] == "Alt+Space"

    storage.save_setting("dictation_trigger_mode", "ptt_only")
    status, _, body = _get(f"{base_url}/api/settings/get?key=dictation_trigger_mode")
    assert status == 200
    assert body["value"] == "ptt_only"

    # Protected credential keys must be blocked
    status, _, body = _get(f"{base_url}/api/settings/get?key=openai_api_key")
    assert status == 403
    assert body["success"] is False

    # Empty key parameter
    status, _, body = _get(f"{base_url}/api/settings/get?key=")
    assert status == 400
    assert body["success"] is False


def test_api_clear_audio_cache_endpoint(test_server) -> None:
    base_url = test_server["base_url"]
    archive = test_server["archive"]

    # Seed 3 dummy wav files in the archive directory
    wav1 = archive.root / "recording_1.wav"
    wav2 = archive.root / "recording_2.wav"
    wav3 = archive.root / "recording_3.wav"
    wav1.write_bytes(b"RIFFdummywav1")
    wav2.write_bytes(b"RIFFdummywav2")
    wav3.write_bytes(b"RIFFdummywav3")

    status, headers, body = _post(f"{base_url}/api/storage/clear-audio-cache", {})
    assert status == 200
    assert body["success"] is True
    assert body["deleted_count"] == 3
    assert not wav1.exists()
    assert not wav2.exists()
    assert not wav3.exists()


def test_api_voice_flow_polish_speed_mode_and_model(test_server) -> None:
    base_url = test_server["base_url"]
    storage = test_server["storage"]

    # 1. Update speed mode to "fast" without sending model
    status, _, body = _post(f"{base_url}/api/voice-flow-polish/update", {"speed_mode": "fast"})
    assert status == 200
    assert body["success"] is True
    assert body["speed_mode"] == "fast"
    assert storage.get_setting("voice_flow_polish_speed_mode") == "fast"
    # Ensure default model wasn't wiped
    assert storage.get_setting("voice_flow_polish_model", "local/deterministic") == "local/deterministic"

    # 2. Query /api/voice-flow-polish/get and verify speed_mode is returned
    status, _, body = _get(f"{base_url}/api/voice-flow-polish/get")
    assert status == 200
    assert body["speed_mode"] == "fast"
    assert body["active_model"] == "local/deterministic"

    # 3. Update speed mode to "quality"
    status, _, body = _post(f"{base_url}/api/voice-flow-polish/update", {"speed_mode": "quality"})
    assert status == 200
    assert body["speed_mode"] == "quality"
    assert storage.get_setting("voice_flow_polish_speed_mode") == "quality"


def test_api_overlay_controls(test_server) -> None:
    base_url = test_server["base_url"]
    mock_overlay = MagicMock()
    mock_controller = MagicMock()
    mock_controller.overlay = mock_overlay

    api_server.register_runtime_controller(mock_controller)

    # 1. Show
    status, _, body = _post(f"{base_url}/api/overlay/show", {})
    assert status == 200
    mock_overlay.show.assert_called_once()
    mock_overlay.reset_position.assert_called_once()

    # 2. Hide
    status, _, body = _post(f"{base_url}/api/overlay/hide", {})
    assert status == 200
    mock_overlay.hide.assert_called_once()

    # 3. Dock
    status, _, body = _post(f"{base_url}/api/overlay/dock", {"dock": "top"})
    assert status == 200
    mock_overlay.set_dock.assert_called_once_with("top")

    api_server.register_runtime_controller(None)


def test_api_settings_update_triggers_autostart(test_server, monkeypatch: pytest.MonkeyPatch) -> None:
    base_url = test_server["base_url"]
    autostart_calls = []
    monkeypatch.setattr(installer, "set_autostart", lambda en: (autostart_calls.append(en), True)[1])

    # POST /api/settings/update with autostart_enabled = False
    status, _, body = _post(f"{base_url}/api/settings/update", {"key": "autostart_enabled", "value": False})
    assert status == 200
    assert body["success"] is True
    assert autostart_calls == [False]
    assert test_server["storage"].get_setting("autostart_enabled") is False

    # POST /api/settings/update with autostart_enabled = True
    status, _, body = _post(f"{base_url}/api/settings/update", {"key": "autostart_enabled", "value": True})
    assert status == 200
    assert body["success"] is True
    assert autostart_calls == [False, True]
    assert test_server["storage"].get_setting("autostart_enabled") is True


def test_api_clear_audio_cache_empty(test_server) -> None:
    base_url = test_server["base_url"]
    status, _, body = _post(f"{base_url}/api/storage/clear-audio-cache", {})
    assert status == 200
    assert body["success"] is True
    assert body["deleted_count"] == 0


def test_api_show_in_taskbar_setting_persistence_and_defaults(test_server) -> None:
    base_url = test_server["base_url"]
    storage = test_server["storage"]

    # 1. Default when unset is True
    status, _, body = _get(f"{base_url}/api/settings/get?key=show_in_taskbar")
    assert status == 200
    assert body["value"] is True

    # 2. Update to False
    status, _, body = _post(f"{base_url}/api/settings/update", {"key": "show_in_taskbar", "value": False})
    assert status == 200
    assert body["success"] is True
    assert storage.get_setting("show_in_taskbar") is False

    # 3. Verify updated value returned by GET
    status, _, body = _get(f"{base_url}/api/settings/get?key=show_in_taskbar")
    assert status == 200
    assert body["value"] is False

    # 4. Update back to True
    status, _, body = _post(f"{base_url}/api/settings/update", {"key": "show_in_taskbar", "value": True})
    assert status == 200
    assert body["success"] is True
    assert storage.get_setting("show_in_taskbar") is True


def test_api_settings_additional_defaults(test_server) -> None:
    base_url = test_server["base_url"]

    status, _, body = _get(f"{base_url}/api/settings/get?key=selected_mic_device")
    assert status == 200
    assert body["value"] == ""

    status, _, body = _get(f"{base_url}/api/settings/get?key=voice_flow_polish_model")
    assert status == 200
    assert body["value"] == "local/deterministic"

    status, _, body = _get(f"{base_url}/api/settings/get?key=voice_flow_polish_speed_mode")
    assert status == 200
    assert body["value"] == "balanced"

    status, _, body = _get(f"{base_url}/api/settings/get?key=audio_flow_speed")
    assert status == 200
    assert body["value"] == 1.0


def test_lifecycle_terminate_suite_processes_kills_children_and_listeners(monkeypatch: pytest.MonkeyPatch) -> None:
    p_main = MagicMock()
    p_main.pid = 5001
    p_main.info = {"pid": 5001, "name": "python.exe", "cmdline": ["python.exe", "-m", "voice_flow.main"]}

    p_child = MagicMock()
    p_child.pid = 5002
    p_child.info = {"pid": 5002, "name": "msedgewebview2.exe", "cmdline": ["msedgewebview2.exe"]}
    p_main.children.return_value = [p_child]

    p_listener = MagicMock()
    p_listener.pid = 5003
    p_listener.children.return_value = []

    mock_psutil = MagicMock()
    mock_psutil.process_iter.return_value = [p_main]
    mock_psutil.wait_procs.return_value = ([], [])
    mock_psutil.Process.side_effect = lambda pid: p_listener if pid == 5003 else p_main

    monkeypatch.setitem(sys.modules, "psutil", mock_psutil)
    monkeypatch.setattr("voice_flow.runtime_guard.listener_pids", lambda host, port: [5003])

    term_pids = lifecycle.terminate_suite_processes()
    assert 5001 in term_pids
    assert 5002 in term_pids
    assert 5003 in term_pids

    p_main.terminate.assert_called_once()
    p_child.terminate.assert_called_once()
    p_listener.terminate.assert_called_once()


def test_desktop_launcher_initializes_autostart_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from voice_flow.gui import desktop_launcher
    set_calls = []
    monkeypatch.setattr(desktop_launcher, "set_windows_auto_startup", lambda enable: set_calls.append(enable))
    monkeypatch.setattr(desktop_launcher, "ensure_backend_running", lambda: None)
    monkeypatch.setattr(desktop_launcher, "is_api_server_ready", lambda timeout=0.2: True)
    monkeypatch.setattr(desktop_launcher, "_focus_existing_window", lambda: False)
    monkeypatch.setattr(installer, "is_autostart_enabled", lambda: False)

    mock_webview = MagicMock()
    mock_window = MagicMock()
    mock_webview.create_window.return_value = mock_window
    monkeypatch.setattr(desktop_launcher, "webview", mock_webview)

    # When autostart_enabled is not set in DB
    db_path = str(tmp_path / "launcher_test_missing.db")
    test_storage = StorageEngine(db_path)
    monkeypatch.setattr("voice_flow.storage.storage", test_storage)

    desktop_launcher.launch_desktop_gui()
    assert set_calls == [True]
    assert test_storage.get_setting("autostart_enabled") is True



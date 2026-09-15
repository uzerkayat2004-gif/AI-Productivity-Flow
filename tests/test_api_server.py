from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import MagicMock

import pytest

from voice_flow.gui import api_server
from voice_flow.storage import StorageEngine


@pytest.fixture
def test_server(monkeypatch, tmp_path):
    db_path = str(tmp_path / "voice_flow_api_test.db")
    test_storage = StorageEngine(db_path)
    monkeypatch.setattr(api_server, "storage", test_storage)

    mock_controller = MagicMock()
    mock_controller.reload_hotkeys = MagicMock()
    api_server.register_runtime_controller(mock_controller)

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
        "server": server,
        "controller": mock_controller,
    }

    server.shutdown()
    server.server_close()
    api_server.register_runtime_controller(None)


def _get(url: str) -> tuple[int, dict, dict]:
    req = urllib.request.Request(url, headers={"Connection": "close"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            headers = dict(resp.headers)
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, headers, body
    except urllib.error.HTTPError as e:
        headers = dict(e.headers)
        body = json.loads(e.read().decode("utf-8"))
        return e.code, headers, body


def _post(url: str, payload: dict | str) -> tuple[int, dict, dict]:
    if isinstance(payload, str):
        data = payload.encode("utf-8")
    else:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Connection": "close"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            headers = dict(resp.headers)
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, headers, body
    except urllib.error.HTTPError as e:
        headers = dict(e.headers)
        body = json.loads(e.read().decode("utf-8"))
        return e.code, headers, body


def test_get_hotkey_settings_defaults(test_server):
    """GET /api/settings/hotkey returns default settings."""
    base_url = test_server["base_url"]
    status, headers, body = _get(f"{base_url}/api/settings/hotkey")
    assert status == 200
    assert body["success"] is True
    assert body["hotkey_trigger"] == "ctrl_win"
    assert body["custom_hotkey"] == "Alt+Space"
    assert body["dictation_trigger_mode"] == "hybrid"
    assert body["middle_click_enabled"] is True
    assert body["push_to_talk_shortcut"] == "Ctrl+Win"


def test_post_hotkey_settings_updates_and_persists(test_server):
    """POST /api/settings/hotkey updates settings in storage and calls runtime controller live reload."""
    base_url = test_server["base_url"]
    controller = test_server["controller"]
    storage = test_server["storage"]

    payload = {
        "hotkey_trigger": "alt_space",
        "custom_hotkey": "Alt+Space",
        "dictation_trigger_mode": "ptt_only",
        "middle_click_enabled": False,
    }
    status, headers, body = _post(f"{base_url}/api/settings/hotkey", payload)
    assert status == 200
    assert body["success"] is True
    assert body["settings"]["hotkey_trigger"] == "alt_space"
    assert body["settings"]["dictation_trigger_mode"] == "ptt_only"
    assert body["settings"]["middle_click_enabled"] is False

    # Check persistence in storage
    saved = storage.get_hotkey_settings()
    assert saved["hotkey_trigger"] == "alt_space"
    assert saved["dictation_trigger_mode"] == "ptt_only"
    assert saved["middle_click_enabled"] is False
    assert saved["push_to_talk_shortcut"] == "Alt+Space"

    # Check live reload hook called on registered runtime_controller
    assert controller.reload_hotkeys.called
    reloaded_args = controller.reload_hotkeys.call_args[0][0]
    assert reloaded_args["hotkey_trigger"] == "alt_space"


def test_post_hotkey_settings_custom_combination(test_server):
    """POST /api/settings/hotkey supports custom combinations and updates label."""
    base_url = test_server["base_url"]
    controller = test_server["controller"]
    storage = test_server["storage"]

    payload = {
        "hotkey_trigger": "custom",
        "custom_hotkey": "Ctrl+Shift+D",
    }
    status, headers, body = _post(f"{base_url}/api/settings/hotkey", payload)
    assert status == 200
    assert body["success"] is True
    assert body["settings"]["hotkey_trigger"] == "custom"
    assert body["settings"]["custom_hotkey"] == "Ctrl+Shift+D"
    assert body["settings"]["push_to_talk_shortcut"] == "Ctrl+Shift+D"

    saved = storage.get_hotkey_settings()
    assert saved["hotkey_trigger"] == "custom"
    assert saved["custom_hotkey"] == "Ctrl+Shift+D"
    assert saved["push_to_talk_shortcut"] == "Ctrl+Shift+D"


def test_post_hotkey_settings_single_ctrl_and_double_ctrl(test_server):
    """Single Ctrl and Double Ctrl triggers auto-enable ctrl_key_dictation_enabled."""
    base_url = test_server["base_url"]
    storage = test_server["storage"]

    # 1. Single Ctrl
    status, headers, body = _post(f"{base_url}/api/settings/hotkey", {"hotkey_trigger": "single_ctrl"})
    assert status == 200
    assert body["settings"]["hotkey_trigger"] == "single_ctrl"
    assert body["settings"]["ctrl_key_dictation_enabled"] is True
    assert body["settings"]["push_to_talk_shortcut"] == "Single Ctrl"

    # 2. Double Ctrl
    status, headers, body = _post(f"{base_url}/api/settings/hotkey", {"hotkey_trigger": "double_ctrl"})
    assert status == 200
    assert body["settings"]["hotkey_trigger"] == "double_ctrl"
    assert body["settings"]["ctrl_key_dictation_enabled"] is True
    assert body["settings"]["push_to_talk_shortcut"] == "Double Ctrl"


def test_post_settings_update_triggers_hotkey_live_reload(test_server):
    """POST /api/settings/update with hotkey_trigger triggers live reload."""
    base_url = test_server["base_url"]
    controller = test_server["controller"]
    controller.reload_hotkeys.reset_mock()

    status, headers, body = _post(f"{base_url}/api/settings/update", {
        "key": "hotkey_trigger",
        "value": "alt_tab",
    })
    assert status == 200
    assert body["success"] is True
    assert controller.reload_hotkeys.called


def test_post_hotkey_invalid_body(test_server):
    """POST /api/settings/hotkey rejects non-object payloads."""
    base_url = test_server["base_url"]
    status, headers, body = _post(f"{base_url}/api/settings/hotkey", "invalid string")
    assert status == 400
    assert body["success"] is False

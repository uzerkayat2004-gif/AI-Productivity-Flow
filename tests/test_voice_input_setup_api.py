"""Settings endpoint regressions using disposable storage and mocked devices."""
import pytest
from tests.test_api_server import test_server, _get, _post
from voice_flow.gui import api_server


@pytest.mark.parametrize("shortcut", ["Ctrl+", "UnknownKey", "Ctrl+A+B"])
def test_invalid_shortcut_rejected_without_writes(test_server, shortcut):
    store = test_server["storage"]
    before = store.get_hotkey_settings()
    code, _, body = _post(test_server["base_url"] + "/api/settings/hotkey", {
        "hotkey_trigger": "custom", "custom_hotkey": shortcut,
        "dictation_trigger_mode": "toggle_only",
    })
    assert code == 400 and not body["success"]
    assert store.get_hotkey_settings() == before
    test_server["controller"].reload_hotkeys.assert_not_called()


def test_microphone_catalog_is_read_only(test_server, monkeypatch):
    store = test_server["storage"]
    preferred = "Microphone Array (Realtek(R) Au"
    store.save_setting("selected_mic_device", preferred)
    monkeypatch.setattr(api_server.sd, "query_devices", lambda: [{
        "name": "Microphone Array (Realtek(R) Audio)", "hostapi": 0,
        "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 48000,
    }])
    monkeypatch.setattr(api_server.sd, "query_hostapis", lambda: [{"name":"Windows DirectSound"}])
    code, _, _ = _get(test_server["base_url"] + "/api/microphones")
    assert code == 200
    assert store.get_setting("selected_mic_device") == preferred


def test_explicit_windows_default_selection(test_server):
    code, _, body = _post(test_server["base_url"] + "/api/microphones/select", {"identity": None})
    assert code == 200 and body["success"]
    assert test_server["storage"].get_setting("selected_mic_device") is None


@pytest.mark.parametrize("key,value", [("custom_hotkey", "Ctrl+"), ("custom_trigger_type", "unknown"), ("dictation_trigger_mode", "unknown"), ("middle_click_enabled", "false")])
def test_generic_hotkey_update_rejects_invalid_before_save(test_server, key, value):
    store = test_server["storage"]
    before = store.get_hotkey_settings()
    code, _, body = _post(test_server["base_url"] + "/api/settings/update", {"key": key, "value": value})
    assert code == 400 and body["success"] is False
    assert store.get_hotkey_settings() == before
    test_server["controller"].reload_hotkeys.assert_not_called()


def test_hotkey_conflicts_are_advisory(test_server):
    code, _, body = _post(test_server["base_url"] + "/api/settings/hotkey", {"hotkey_trigger": "custom", "custom_hotkey": "control+c"})
    assert code == 200 and body["success"]
    assert body["settings"]["custom_hotkey"] == "Ctrl+C"
    assert body["warnings"]


def test_recorder_lease_owner_lifecycle(test_server):
    controller = test_server["controller"]
    controller.hotkeys.begin_shortcut_capture.return_value = True
    controller.hotkeys.renew_shortcut_capture.return_value = True
    controller.hotkeys.end_shortcut_capture.return_value = True
    endpoint = test_server["base_url"] + "/api/settings/hotkey/recorder"
    code, _, body = _post(endpoint, {"action": "begin"})
    assert code == 200 and body["success"] and body["expires_in"] == 30
    token = body["token"]
    controller.hotkeys.begin_shortcut_capture.assert_called_once_with(token)
    for action in ("renew", "end"):
        code, _, body = _post(endpoint, {"action": action, "token": token})
        assert code == 200 and body["success"]
    controller.hotkeys.begin_shortcut_capture.return_value = False
    code, _, body = _post(endpoint, {"action": "begin"})
    assert code == 409 and not body["success"]


def test_failed_reload_does_not_report_applied(test_server):
    test_server["controller"].reload_hotkeys.side_effect = RuntimeError("mock reload failed")
    code, _, body = _post(test_server["base_url"] + "/api/settings/hotkey", {"hotkey_trigger":"alt_space"})
    assert code == 503 and body["success"] is False and body["saved"] is True


def test_explicit_refresh_discovers_connected_microphone_read_only(test_server, monkeypatch):
    state = {"fresh": False, "terminated": 0, "initialized": 0}
    def row(name):
        return {"name": name, "hostapi": 0, "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 48000}
    def initialize():
        state["initialized"] += 1
        state["fresh"] = True
    def terminate():
        state["terminated"] += 1
    monkeypatch.setattr(api_server.sd, "query_devices", lambda: [row("Laptop microphone")] + ([row("New USB microphone")] if state["fresh"] else []))
    monkeypatch.setattr(api_server.sd, "query_hostapis", lambda: [{"name":"Windows WASAPI"}])
    monkeypatch.setattr(api_server.sd, "_terminate", terminate)
    monkeypatch.setattr(api_server.sd, "_initialize", initialize)
    monkeypatch.setattr(api_server.sd, "_initialized", 1)
    monkeypatch.setattr(api_server.sd, "get_stream", lambda: None)
    monkeypatch.setattr(api_server.sd, "_last_callback", None)
    store = test_server["storage"]
    store.save_setting("selected_mic_device", "Disconnected preference")
    endpoint = test_server["base_url"] + "/api/microphones"
    code, _, old = _get(endpoint)
    assert code == 200 and all(d["name"] != "New USB microphone" for d in old["devices"])
    assert state["terminated"] == 0
    code, _, refreshed = _get(endpoint + "?refresh=1")
    assert code == 200
    assert any(d["name"] == "New USB microphone" for d in refreshed["devices"])
    assert refreshed["refreshed"] is True
    assert state["terminated"] == state["initialized"] == 1
    assert store.get_setting("selected_mic_device") == "Disconnected preference"

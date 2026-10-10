"""Comprehensive parity tests for Voice Flow and Audio Flow Custom Providers."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import pytest

from voice_flow import storage as storage_module
from voice_flow.storage import StorageEngine
from voice_flow.tts_engine import TTSEngine
from voice_flow.provider_validation import validate_provider_key
from voice_flow.gui import api_server
from http.server import ThreadingHTTPServer
from unittest.mock import MagicMock, patch


@pytest.fixture
def custom_server(monkeypatch, tmp_path):
    db_path = str(tmp_path / "custom_providers_test.db")
    test_storage = StorageEngine(db_path)
    monkeypatch.setattr(storage_module, "storage", test_storage)
    monkeypatch.setattr(api_server, "storage", test_storage)
    monkeypatch.setattr(api_server, "DB_PATH", db_path)

    import voice_flow.tts_engine as tts_module
    monkeypatch.setattr(tts_module, "storage", test_storage)

    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    server.daemon_threads = True
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.15)
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"

    yield {"base_url": base_url, "storage": test_storage, "server": server}

    server.shutdown()
    server.server_close()


def _get(url: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={"Connection": "close"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode("utf-8"))
        return e.code, body


def _post(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "Connection": "close"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode("utf-8"))
        return e.code, body


def test_storage_custom_providers_crud(custom_server):
    store = custom_server["storage"]

    # Voice Flow
    ventry = {
        "name": "Custom Whisper Local",
        "base_url": "http://127.0.0.1:9000",
        "api_key": "v-key-1",
        "models": [{"model_id": "whisper-large-v3", "display_name": "Large v3"}],
    }
    v_res = store.add_voice_flow_custom_provider(ventry)
    assert len(v_res) == 1
    v_pid = v_res[0]["id"]
    assert v_pid.startswith("custom-")
    assert len(v_res[0]["api_keys"]) == 1
    assert v_res[0]["api_keys"][0]["id"] == "c-0"

    v_get = store.get_voice_flow_custom_providers()
    assert len(v_get) == 1
    assert v_get[0]["id"] == v_pid

    store.delete_voice_flow_custom_provider(v_pid)
    assert len(store.get_voice_flow_custom_providers()) == 0

    # Audio Flow
    aentry = {
        "name": "Custom Piper Local",
        "base_url": "http://127.0.0.1:5000",
        "api_key": "a-key-1",
        "models": [{"model_id": "piper-voice-1", "display_name": "Piper Voice 1"}],
    }
    a_res = store.add_audio_flow_custom_provider(aentry)
    assert len(a_res) == 1
    a_pid = a_res[0]["id"]
    assert a_pid.startswith("custom-")
    assert len(a_res[0]["api_keys"]) == 1
    assert a_res[0]["api_keys"][0]["id"] == "c-0"

    a_get = store.get_audio_flow_custom_providers()
    assert len(a_get) == 1
    assert a_get[0]["id"] == a_pid

    store.delete_audio_flow_custom_provider(a_pid)
    assert len(store.get_audio_flow_custom_providers()) == 0


def test_storage_load_balance_modes(custom_server):
    store = custom_server["storage"]
    assert store.get_provider_load_balance_mode("groq") == "priority"
    store.save_provider_load_balance_mode("groq", "round_robin")
    assert store.get_provider_load_balance_mode("groq") == "round_robin"

    assert store.get_audio_provider_load_balance_mode("elevenlabs") == "priority"
    store.save_audio_provider_load_balance_mode("elevenlabs", "round_robin")
    assert store.get_audio_provider_load_balance_mode("elevenlabs") == "round_robin"


def test_tts_engine_custom_provider_active_keys_and_rotation(custom_server):
    store = custom_server["storage"]
    entry = {
        "id": "custom-multi-tts",
        "name": "Multi Key TTS",
        "base_url": "http://127.0.0.1:8888",
        "api_format": "openai",
        "api_keys": [
            {"id": "c-0", "name": "Key 1", "key": "k1", "is_active": True, "priority": 1},
            {"id": "c-1", "name": "Key 2", "key": "k2", "is_active": True, "priority": 2},
        ],
        "load_balance_mode": "round_robin",
        "models": [{"model_id": "voice-1", "is_active": True}],
    }
    store.add_audio_flow_custom_provider(entry)

    engine = TTSEngine()
    first_keys = engine._get_active_keys_for_provider("custom-multi-tts")
    assert len(first_keys) >= 1
    assert first_keys[0]["api_key"] == "k1"

    second_keys = engine._get_active_keys_for_provider("custom-multi-tts")
    assert len(second_keys) >= 1
    assert second_keys[0]["api_key"] == "k2"


def test_tts_engine_custom_synthesize(custom_server):
    store = custom_server["storage"]
    entry = {
        "id": "custom-kokoro",
        "name": "Kokoro TTS",
        "base_url": "http://127.0.0.1:8880/v1",
        "api_key": "kokoro-secret",
        "api_format": "openai",
        "models": [{"model_id": "af_bella", "is_active": True}],
    }
    store.add_audio_flow_custom_provider(entry)

    engine = TTSEngine()
    dummy_wav = b"RIFFfakeaudioWAVE"

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = dummy_wav
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = engine._synthesize_custom("Hello Voice Flow", "custom-kokoro", "af_bella")
        assert res == dummy_wav


def test_api_server_voice_flow_custom_providers_flow(custom_server):
    base = custom_server["base_url"]

    # 1. Add
    status, data = _post(f"{base}/api/voice-flow/custom-providers/add", {
        "name": "Local Whisper GPU",
        "base_url": "http://localhost:9000/v1",
        "api_key": "gpu-secret-1",
        "api_format": "openai",
        "models": [{"model_id": "whisper-v3", "display_name": "Whisper V3"}],
    })
    assert status == 200
    assert data["success"] is True
    pid = data["providers"][0]["id"]
    assert pid == "custom-local-whisper-gpu"

    # 2. List
    status, data = _get(f"{base}/api/voice-flow/custom-providers/list")
    assert status == 200
    assert len(data["providers"]) == 1

    # 3. Overview
    status, data = _get(f"{base}/api/providers/overview")
    assert status == 200
    assert pid in data["connections"]

    # 4. Details
    status, data = _get(f"{base}/api/providers/details?provider={pid}")
    assert status == 200
    assert len(data["connections"]) == 1
    assert data["connections"][0]["id"] == "c-0"
    assert len(data["models"]) == 1
    assert data["models"][0]["id"] == "m-0"

    # 5. Connection Add, Update, Reorder, Delete
    status, data = _post(f"{base}/api/providers/connections/add", {
        "provider": pid,
        "name": "Backup GPU Key",
        "key": "gpu-secret-2",
        "priority": 2,
    })
    assert status == 200
    assert data["success"] is True

    status, data = _get(f"{base}/api/providers/details?provider={pid}")
    assert len(data["connections"]) == 2

    # Reorder
    status, data = _post(f"{base}/api/providers/connections/reorder", {
        "provider": pid,
        "connection_ids": ["c-1", "c-0"],
    })
    assert status == 200
    assert data["success"] is True

    # Delete connection c-1
    status, data = _post(f"{base}/api/providers/connections/delete", {
        "provider": pid,
        "id": "c-1",
    })
    assert status == 200
    assert data["success"] is True

    status, data = _get(f"{base}/api/providers/details?provider={pid}")
    assert len(data["connections"]) == 1

    # 6. Model Add, Disable-all, Enable-all, Delete
    status, data = _post(f"{base}/api/providers/models/add", {
        "provider": pid,
        "model_id": "whisper-base",
        "display_name": "Whisper Base",
    })
    assert status == 200
    assert data["success"] is True

    status, data = _post(f"{base}/api/providers/models/disable-all", {"provider": pid})
    assert status == 200
    assert data["success"] is True

    status, data = _get(f"{base}/api/providers/details?provider={pid}")
    assert all(m["is_active"] is False for m in data["models"])

    status, data = _post(f"{base}/api/providers/models/enable-all", {"provider": pid})
    assert status == 200
    assert data["success"] is True

    status, data = _get(f"{base}/api/providers/details?provider={pid}")
    assert all(m["is_active"] is True for m in data["models"])

    status, data = _post(f"{base}/api/providers/models/delete", {
        "provider": pid,
        "id": "m-0",
    })
    assert status == 200
    assert data["success"] is True

    # 7. Whole custom provider delete via "custom" id
    status, data = _post(f"{base}/api/providers/connections/delete", {
        "provider": pid,
        "id": "custom",
    })
    assert status == 200
    assert data["success"] is True
    assert len(data["providers"]) == 0


def test_api_server_audio_flow_custom_providers_flow(custom_server):
    base = custom_server["base_url"]

    # 1. Add
    status, data = _post(f"{base}/api/audio-flow/custom-providers/add", {
        "name": "Local Audio Server",
        "base_url": "http://localhost:8880/v1",
        "api_key": "audio-secret-1",
        "api_format": "openai",
        "models": [{"model_id": "kokoro-bella", "display_name": "Kokoro Bella"}],
    })
    assert status == 200
    assert data["success"] is True
    pid = data["providers"][0]["id"]
    assert pid == "custom-local-audio-server"

    # 2. List
    status, data = _get(f"{base}/api/audio-flow/custom-providers/list")
    assert status == 200
    assert len(data["providers"]) == 1

    # 3. Overview
    status, data = _get(f"{base}/api/audio-providers/overview")
    assert status == 200
    assert any(p["id"] == pid for p in data)

    # 4. Details
    status, data = _get(f"{base}/api/audio-providers/details?provider={pid}")
    assert status == 200
    assert len(data["connections"]) == 1
    assert data["connections"][0]["id"] == "c-0"
    assert len(data["models"]) == 1
    assert data["models"][0]["id"] == "m-0"

    # 5. Connection Add, Reorder, Delete
    status, data = _post(f"{base}/api/audio-providers/connections/add", {
        "provider": pid,
        "name": "Key #2",
        "key": "audio-secret-2",
        "priority": 2,
    })
    assert status == 200
    assert data["success"] is True

    status, data = _get(f"{base}/api/audio-providers/details?provider={pid}")
    assert len(data["connections"]) == 2

    status, data = _post(f"{base}/api/audio-providers/connections/reorder", {
        "provider": pid,
        "connection_ids": ["c-1", "c-0"],
    })
    assert status == 200
    assert data["success"] is True

    # 6. Mode save
    status, data = _post(f"{base}/api/audio-providers/mode/save", {
        "provider": pid,
        "mode": "round-robin",
    })
    assert status == 200
    assert data["success"] is True

    status, data = _get(f"{base}/api/audio-providers/details?provider={pid}")
    assert data["load_balance_mode"] in ("round-robin", "round_robin")

    # 7. Model Add, Disable-all, Enable-all, Delete
    status, data = _post(f"{base}/api/audio-providers/models/add", {
        "provider": pid,
        "model_id": "kokoro-adam",
        "display_name": "Kokoro Adam",
    })
    assert status == 200
    assert data["success"] is True

    status, data = _post(f"{base}/api/audio-providers/models/disable-all", {"provider": pid})
    assert status == 200
    assert data["success"] is True

    status, data = _get(f"{base}/api/audio-providers/details?provider={pid}")
    assert all(m["is_active"] is False for m in data["models"])

    status, data = _post(f"{base}/api/audio-providers/models/enable-all", {"provider": pid})
    assert status == 200
    assert data["success"] is True

    status, data = _get(f"{base}/api/audio-providers/details?provider={pid}")
    assert all(m["is_active"] is True for m in data["models"])

    status, data = _post(f"{base}/api/audio-providers/models/delete", {
        "provider": pid,
        "id": "m-0",
    })
    assert status == 200
    assert data["success"] is True

    # 8. Whole custom provider delete via "custom" id
    status, data = _post(f"{base}/api/audio-providers/connections/delete", {
        "provider": pid,
        "id": "custom",
    })
    assert status == 200
    assert data["success"] is True
    assert len(data["providers"]) == 0

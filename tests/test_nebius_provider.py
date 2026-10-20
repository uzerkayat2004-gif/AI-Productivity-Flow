"""Nebius Token Factory as a plain API-key provider (all HTTP mocked).

Covers: provider card fields, the Test button request, Voice Flow polish,
Audio Flow summary dispatch, Video Flow planning, model Test, and that
Nebius is never picked unless the user chose a Nebius model.
"""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest

import voice_flow.video_flow_providers as providers_module
from voice_flow.video_flow_providers import VideoFlowProviderService
from voice_flow.nebius_provider import strip_reasoning

CHAT_URL = "https://api.tokenfactory.nebius.com/v1/chat/completions"
MODELS_URL = "https://api.tokenfactory.nebius.com/v1/models"
KEY = "nebius-test-key-0123456789abcdef"


def _resp(body, status=200):
    r = MagicMock()
    r.status = status
    raw = json.dumps(body).encode("utf-8")
    r.read.return_value = raw
    r.__enter__.return_value = r
    return r


@pytest.fixture()
def service(tmp_path, monkeypatch):
    svc = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    monkeypatch.setattr(providers_module, "video_flow_provider_service", svc)
    return svc


def _connect(svc):
    conn = svc.add_connection("nebius", name="Nebius key", secret=KEY)
    svc.update_connection(int(conn["id"]), status="connected")
    return conn


def test_nebius_is_listed_like_other_api_key_providers(service):
    catalog = service.catalog()
    api = {p["id"]: p for p in catalog["api_key"]}
    assert "nebius" in api and "openrouter" in api
    neb = api["nebius"]
    assert neb["name"] == "Nebius Token Factory"
    assert neb["auth"] == "api_key" and neb["category"] == "api_key"
    assert neb["get_key_url"] == "https://tokenfactory.nebius.com/"
    assert neb["status"] == "disconnected"
    # Same key set as a comparable provider's card.
    assert set(neb) == set(api["openrouter"])
    models = service.list_models("nebius")
    ids = {m["model_id"] for m in models}
    assert "nvidia/Nemotron-3_5-Lightning" in ids
    assert all(m["full_id"].startswith("nebius/") for m in models)
    assert all(m["available"] is False for m in models)  # no key yet


def test_test_button_gets_models_with_bearer_key(service):
    conn = _connect(service)
    seen = []

    def fake(req, timeout=30):
        seen.append(req)
        return _resp({"object": "list", "data": [{"id": "nvidia/Nemotron-3_5-Lightning"}]})

    with patch("urllib.request.urlopen", side_effect=fake):
        result = service.test_connection(int(conn["id"]))
    assert result["success"] is True and result["status"] == "connected"
    assert seen[0].full_url == MODELS_URL
    assert seen[0].get_method() == "GET"
    assert seen[0].get_header("Authorization") == f"Bearer {KEY}"
    assert all(m["available"] for m in service.list_models("nebius"))


def test_test_button_reports_invalid_key_like_other_providers(service):
    import urllib.error
    conn = _connect(service)
    err = urllib.error.HTTPError(MODELS_URL, 401, "Unauthorized", {}, io.BytesIO(b'{"detail":"bad key"}'))
    with patch("urllib.request.urlopen", side_effect=err):
        result = service.test_connection(int(conn["id"]))
    assert result["success"] is False
    assert "HTTP 401" in result["error"]


def test_voice_flow_polish_goes_to_nebius_with_selected_model(service):
    from voice_flow import voice_polish_bridge

    _connect(service)
    ref = "nebius/nvidia/Nemotron-3_5-Lightning"
    assert voice_polish_bridge.can_execute_model(ref) is True
    captured = {}

    def fake_request_json(endpoint, headers, body, timeout_seconds):
        captured.update(endpoint=endpoint, headers=headers, body=body)
        return {"choices": [{"finish_reason": "stop", "message": {"content": "<think>plan</think>Clean text."}}]}, "ok"

    with patch("voice_flow.voice_provider_transport.request_json", side_effect=fake_request_json):
        out = voice_polish_bridge.request_polish(ref, "polish this", timeout_seconds=5)
    assert out == "Clean text."
    assert captured["endpoint"] == CHAT_URL
    assert captured["headers"]["Authorization"] == f"Bearer {KEY}"
    assert captured["body"]["model"] == "nvidia/Nemotron-3_5-Lightning"


def test_voice_flow_polish_not_runnable_without_key(service):
    from voice_flow import voice_polish_bridge
    assert voice_polish_bridge.can_execute_model("nebius/nvidia/Nemotron-3_5-Lightning") is False


def test_audio_flow_summary_dispatch_uses_nebius(service, monkeypatch):
    import voice_flow.audio_summary as audio_summary

    monkeypatch.setattr(audio_summary, "video_flow_provider_service", service)
    _connect(service)
    seen = []

    def fake(req, timeout=30):
        seen.append(req)
        return _resp({"choices": [{"message": {"content": "<think>x</think>Short summary."}}]})

    with patch("urllib.request.urlopen", side_effect=fake):
        out = audio_summary.audio_summary_service._dispatch_llm_prompt(
            "summarize", "nebius/Qwen/Qwen3-235B-A22B-Instruct-2507", service_label="Audio Summary")
    assert out == "Short summary."
    assert seen[0].full_url == CHAT_URL
    assert seen[0].get_header("Authorization") == f"Bearer {KEY}"
    assert json.loads(seen[0].data)["model"] == "Qwen/Qwen3-235B-A22B-Instruct-2507"


def test_video_flow_planning_gateway_uses_nebius_when_selected(service):
    from voice_flow.video_flow_service import ProviderModelGateway

    _connect(service)
    service.set_active_model("nebius/nvidia/nemotron-3-super-120b-a12b")
    storage = MagicMock()
    storage.get_setting.return_value = ""
    storage.get_provider_connections.return_value = []
    gw = ProviderModelGateway.from_storage(storage)
    assert gw._provider == "nebius"
    assert gw._endpoint == CHAT_URL
    assert gw._model_id == "nvidia/nemotron-3-super-120b-a12b"
    assert gw._api_key == KEY

    proc = MagicMock()
    proc.communicate.return_value = (json.dumps({"ok": True, "content": "<think>r</think>{\"scenes\": []}"}), None)
    proc.returncode = 0
    proc.poll.return_value = 0
    with patch("voice_flow.video_flow_service.subprocess.Popen", return_value=proc) as popen:
        content = gw.request_isolated(prompt="plan", model_ref=None, max_tokens=1000,
                                      timeout_seconds=5, job_id="j1", process_manager=MagicMock())
    assert content == '{"scenes": []}'
    sent = json.loads(proc.communicate.call_args.args[0])
    assert sent["endpoint"] == CHAT_URL and sent["model"] == "nvidia/nemotron-3-super-120b-a12b"
    assert popen.called


def test_nebius_is_never_auto_picked_for_video_planning(service):
    from voice_flow.video_flow_service import ProviderModelGateway

    _connect(service)  # a Nebius key exists, but no Nebius model is chosen
    assert service.get_active_model() == "local/deterministic"
    storage = MagicMock()
    storage.get_setting.return_value = ""
    storage.get_provider_connections.return_value = []
    with pytest.raises(RuntimeError):
        ProviderModelGateway.from_storage(storage)


def test_model_test_button_hits_nebius_chat_endpoint():
    from voice_flow.gui.api_server import VoiceFlowApiHandler

    handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)
    seen = []

    def fake(req, timeout=30):
        seen.append(req)
        return _resp({"choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}]})

    with patch("urllib.request.urlopen", side_effect=fake):
        res = handler.verify_model_by_kind("nebius", KEY, "nebius/meta/x-model", kind="llm")
        res2 = handler.verify_provider_model("nebius", KEY, "deepseek-ai/DeepSeek-V4-Flash-0731")
    assert res["success"] is True and res2["success"] is True
    assert seen[0].full_url == CHAT_URL
    assert json.loads(seen[0].data)["model"] == "meta/x-model"
    assert seen[-1].full_url == CHAT_URL


def test_registry_key_check_uses_models_endpoint():
    from voice_flow.provider_validation import validate_provider_key
    seen = []

    def fake(req, timeout=30.0):
        seen.append(req)
        return _resp({"data": []})

    with patch("urllib.request.urlopen", side_effect=fake):
        ok, err = validate_provider_key("nebius", KEY)
    assert ok is True and err is None
    assert seen[0].full_url == MODELS_URL
    assert seen[0].get_header("Authorization") == f"Bearer {KEY}"


def test_strip_reasoning():
    assert strip_reasoning("<think>a\nb</think>\nHello") == "Hello"
    assert strip_reasoning("reasoning</think>Hi") == "Hi"
    assert strip_reasoning("<think>unfinished") is None
    assert strip_reasoning("Plain answer") == "Plain answer"


def test_frontend_lists_nebius_in_same_places_as_openrouter():
    from pathlib import Path
    gui = Path(__file__).resolve().parents[1] / "src" / "voice_flow" / "gui"
    logos = (gui / "provider-logos.js").read_text(encoding="utf-8")
    vf = (gui / "video-flow.js").read_text(encoding="utf-8")
    app = (gui / "app.js").read_text(encoding="utf-8")
    assert "  nebius: " in logos
    assert 'nebius: "N"' in vf
    assert '"nebius", "opencode_zen"' in vf and '"nebius", "opencode_zen"' in app

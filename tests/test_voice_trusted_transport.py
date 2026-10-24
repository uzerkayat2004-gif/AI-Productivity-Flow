"""Offline payload checks; import transport files without app/storage startup."""
import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / "src/voice_flow" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gemini_serializes_policy_separately_and_legacy_unchanged():
    module = load("isolated_gemini", "voice_gemini_transport.py")
    captured = []
    class Connection:
        sock = None
        def request(self, *args, **kwargs):
            captured.append(json.loads(kwargs["body"]))
        def getresponse(self):
            return SimpleNamespace(status=200, read=lambda: b'{"candidates":[{"content":{"parts":[{"text":"rewritten"}]}}]}')
    session = module._GeminiSession("unused", "fake")
    session.connection = Connection()
    for policy in ("Trusted command policy", None):
        session.lock.acquire()
        assert session.request_locked("gemini-test", "Exact body", 3, system_prompt=policy) == "rewritten"
    assert captured[0]["system_instruction"] == {"parts": [{"text": "Trusted command policy"}]}
    assert captured[0]["contents"] == [{"role": "user", "parts": [{"text": "Exact body"}]}]
    assert "system_instruction" not in captured[1]


def bridge_setup(monkeypatch, provider="chat"):
    module = load("isolated_bridge", "voice_polish_bridge.py")
    gateway = SimpleNamespace(_provider=provider, _endpoint="https://unused/chat/completions", _api_key="fake", _model_id="exact-model")
    service = types.ModuleType("voice_flow.video_flow_service")
    service.ProviderModelGateway = SimpleNamespace(_from_video_provider_service=lambda *args: gateway)
    storage = types.ModuleType("voice_flow.storage")
    storage.storage = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "voice_flow.video_flow_service", service)
    monkeypatch.setitem(sys.modules, "voice_flow.storage", storage)
    return module


def test_catalog_chat_separates_roles_and_preserves_legacy(monkeypatch):
    module = bridge_setup(monkeypatch)
    transport = types.ModuleType("voice_flow.voice_provider_transport")
    requests = []
    transport.request_chat = lambda **kwargs: (requests.append(kwargs) or "rewritten", "ok")
    monkeypatch.setitem(sys.modules, "voice_flow.voice_provider_transport", transport)
    assert module.request_polish("test/exact-model", "Exact body", timeout_seconds=3, system_prompt="Trusted policy") == "rewritten"
    assert module.request_polish("test/exact-model", "Legacy combined", timeout_seconds=3) == "rewritten"
    assert requests[0]["messages"] == [{"role": "system", "content": "Trusted policy"}, {"role": "user", "content": "Exact body"}]
    assert requests[1]["messages"] == [{"role": "user", "content": "Legacy combined"}]
    assert requests[0]["model"] == "exact-model"


def test_catalog_gemini_forwards_policy_without_combining(monkeypatch):
    module = bridge_setup(monkeypatch, "gemini")
    transport = types.ModuleType("voice_flow.voice_gemini_transport")
    requests = []
    transport.request_gemini_polish = lambda **kwargs: requests.append(kwargs) or "rewritten"
    transport.last_transport_diagnostic = lambda: {"status": "ok"}
    monkeypatch.setitem(sys.modules, "voice_flow.voice_gemini_transport", transport)
    assert module.request_polish("gemini/exact-model", "Exact body", timeout_seconds=3, system_prompt="Trusted policy") == "rewritten"
    assert requests[0]["prompt"] == "Exact body"
    assert requests[0]["system_prompt"] == "Trusted policy"


def test_antigravity_serializes_native_system_instruction(monkeypatch):
    module = bridge_setup(monkeypatch)
    service = types.ModuleType("voice_flow.video_flow_providers")
    service.video_flow_provider_service = SimpleNamespace(active_connections=lambda provider: [{}], resolve_connection_secret=lambda conn: "fake")
    monkeypatch.setitem(sys.modules, "voice_flow.video_flow_providers", service)
    captured = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{"candidates":[{"content":{"parts":[{"text":"rewritten"}]}}]}'
    def urlopen(request, **kwargs):
        captured.append(json.loads(request.data))
        return Response()
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    assert module.request_polish("antigravity/exact-model", "Exact body", timeout_seconds=3, system_prompt="Trusted policy") == "rewritten"
    assert captured[0]["request"]["systemInstruction"] == {"parts": [{"text": "Trusted policy"}]}
    assert captured[0]["request"]["contents"] == [{"role": "user", "parts": [{"text": "Exact body"}]}]

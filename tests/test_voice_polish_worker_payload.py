"""Exercise the actual isolated Voice Gemini worker without sending requests."""
import io
import json
import sys
import urllib.request

import pytest

from voice_flow.video_flow_service import _GEMINI_POLISH_WORKER


@pytest.mark.parametrize("model,thinking", [
    ("gemini-2.5-flash", None),
    ("gemini-2.5-pro", None),
    ("gemini-3.6-flash", {"thinkingLevel": "minimal"}),
])
def test_native_worker_sends_model_compatible_payload(monkeypatch, model, thinking):
    captured = []

    def respond(request, **_kwargs):
        captured.append((request.full_url, json.loads(request.data)))
        return io.BytesIO(json.dumps({"candidates": [{"content": {
            "parts": [{"text": "She knows."}]
        }}]}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", respond)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({
        "model": model, "api_key": "synthetic-key", "prompt": "she know",
        "max_tokens": 512,
    })))
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output)
    with pytest.raises(SystemExit) as stopped:
        exec(compile(_GEMINI_POLISH_WORKER, "voice-gemini-worker", "exec"), {})
    assert stopped.value.code == 0
    assert len(captured) == 1
    assert captured[0][0].endswith(f"/{model}:generateContent")
    assert captured[0][1]["generationConfig"].get("thinkingConfig") == thinking
    assert json.loads(output.getvalue())["content"] == "She knows."


def test_catalog_capability_does_not_refresh_credentials(monkeypatch):
    from voice_flow import voice_polish_bridge
    from voice_flow.video_flow_providers import video_flow_provider_service
    from voice_flow.video_flow_service import ProviderModelGateway

    monkeypatch.setattr(video_flow_provider_service, "active_connections", lambda _provider: [
        {"is_active": True, "status": "connected", "secret": "synthetic-key"}
    ])
    monkeypatch.setattr(ProviderModelGateway, "_from_video_provider_service",
                        lambda *_args: pytest.fail("Catalog must not refresh OAuth credentials"))
    assert voice_polish_bridge.can_execute_model("gemini/gemini-3.6-flash")

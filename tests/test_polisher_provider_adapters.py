"""Request snapshots for Voice Flow's selected text-polish providers."""

import json
import threading
from unittest.mock import MagicMock, patch

import numpy as np

from voice_flow.polisher import TextPolisher


def _response(body):
    response = MagicMock()
    response.read.return_value = json.dumps(body).encode("utf-8")
    response.__enter__.return_value = response
    return response


def test_openrouter_and_nvidia_use_selected_openai_compatible_models():
    polisher = TextPolisher()
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return _response({"choices": [{"message": {"content": "Polished transcript."}}]})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        assert polisher._try_provider_call("openrouter", "or-key", "system", "user", "poolside/laguna-s-2.1:free") == "Polished transcript."
        assert polisher._try_provider_call("nim", "nv-key", "system", "user", "nvidia/nemotron-3-ultra") == "Polished transcript."

    openrouter_request, _ = requests[0]
    assert openrouter_request.full_url == "https://openrouter.ai/api/v1/chat/completions"
    assert openrouter_request.get_header("Authorization") == "Bearer or-key"
    assert openrouter_request.get_header("Http-referer") == "http://localhost:8991"
    assert json.loads(openrouter_request.data)["model"] == "poolside/laguna-s-2.1:free"
    nvidia_request, _ = requests[1]
    assert nvidia_request.full_url == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert json.loads(nvidia_request.data)["model"] == "nvidia/nemotron-3-ultra"


def test_anthropic_uses_messages_format_and_text_blocks():
    polisher = TextPolisher()

    with patch("urllib.request.urlopen", return_value=_response({"content": [
        {"type": "thinking", "thinking": "ignored"},
        {"type": "text", "text": "Cleaned transcript."},
    ]})) as urlopen:
        result = polisher._try_provider_call("anthropic", "anth-key", "system", "user", "claude-sonnet-5")

    assert result == "Cleaned transcript."
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://api.anthropic.com/v1/messages"
    assert request.get_header("X-api-key") == "anth-key"
    assert request.get_header("Anthropic-version") == "2023-06-01"
    payload = json.loads(request.data)
    assert payload["model"] == "claude-sonnet-5"
    assert payload["system"] == "system"


def test_custom_adapters_preserve_format_headers_and_parser():
    polisher = TextPolisher()
    entries = [
        {"id": "custom-openai", "base_url": "https://custom.example/v1", "api_format": "openai", "headers": {"X-Tenant": "vf"}},
        {"id": "custom-anthropic", "base_url": "https://claude.example", "api_format": "anthropic", "headers": {}},
        {"id": "custom-gemini", "base_url": "https://gemini.example", "api_format": "gemini", "headers": {}},
    ]
    bodies = iter([
        {"choices": [{"message": {"content": "OpenAI custom."}}]},
        {"content": [{"type": "text", "text": "Anthropic custom."}]},
        {"candidates": [{"content": {"parts": [{"thought": True, "text": "ignore"}, {"text": "Gemini custom."}]}}]},
    ])
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return _response(next(bodies))

    with patch("voice_flow.polisher.storage.get_voice_flow_custom_providers", return_value=entries), patch("urllib.request.urlopen", side_effect=fake_urlopen):
        assert polisher._try_provider_call("custom-openai", "key-one", "system", "user", "model/one") == "OpenAI custom."
        assert polisher._try_provider_call("custom-anthropic", "key-two", "system", "user", "claude-test") == "Anthropic custom."
        assert polisher._try_provider_call("custom-gemini", "key-three", "system", "user", "gemini-test") == "Gemini custom."

    assert requests[0].full_url == "https://custom.example/v1/chat/completions"
    assert requests[0].get_header("X-tenant") == "vf"
    assert json.loads(requests[0].data)["model"] == "model/one"
    assert requests[1].full_url == "https://claude.example/v1/messages"
    assert requests[1].get_header("X-api-key") == "key-two"
    assert json.loads(requests[1].data)["model"] == "claude-test"
    assert requests[2].full_url == "https://gemini.example/v1beta/models/gemini-test:generateContent"
    assert requests[2].get_header("X-goog-api-key") == "key-three"


def test_explicit_short_polish_calls_selected_openrouter_model():
    polisher = TextPolisher()
    calls = []

    def fake_call(provider, key, system, user, model=None, timeout=None):
        calls.append((provider, model))
        return "Please fix this sentence right now thanks."

    def setting(name, default=None):
        if name == "polishing_enabled":
            return True
        if name == "voice_flow_polish_model":
            return "openrouter/poolside/laguna-s-2.1:free"
        return default

    with patch("voice_flow.polisher.storage.get_setting", side_effect=setting), \
         patch("voice_flow.polisher.storage.get_all_api_keys", return_value={"openrouter": "key"}), \
         patch("voice_flow.polisher.storage.get_all_provider_connections", return_value={}), \
         patch.object(polisher, "_try_provider_call", side_effect=fake_call):
        polisher.polish(
            "please fix this sentence right now thanks",
            model_ref="openrouter/poolside/laguna-s-2.1:free",
        )

    assert calls[0] == ("openrouter", "poolside/laguna-s-2.1:free")


def test_cloud_stt_breaker_does_not_block_a_new_selected_model():
    """A hard failure on one selection must not skip the next selection."""
    from voice_flow.transcriber import Transcriber

    transcriber = object.__new__(Transcriber)
    transcriber.model = object()
    transcriber._loaded_model_ref = transcriber._local_model_name()
    transcriber._loading = False
    transcriber._lock = threading.Lock()
    transcriber._transcribe_lock = threading.Lock()
    audio = np.full(3200, 0.05, dtype=np.float32)
    calls = []

    def cloud(_audio, model_ref, **_kwargs):
        calls.append(model_ref)
        if model_ref == "broken/first":
            raise RuntimeError("HTTP 401 invalid key")
        return "new selection transcript"

    with patch("voice_flow.stt_engines.transcribe_cloud", side_effect=cloud), \
         patch.object(transcriber, "_transcribe_local", return_value="local fallback"):
        assert transcriber.transcribe(audio, model_ref="broken/first") == "local fallback"
        assert transcriber.transcribe(audio, model_ref="working/second") == "new selection transcript"

    assert calls == ["broken/first", "working/second"]


def test_selected_local_cleanup_never_calls_cloud_even_with_saved_keys():
    polisher = TextPolisher()
    with patch("voice_flow.polisher.storage.get_all_api_keys", return_value={"gemini": "key"}), \
         patch.object(polisher, "_polish_with_api_pool") as pool:
        result = polisher.polish("please keep all of these words in my complete long transcript", model_ref="local/deterministic")
    pool.assert_not_called()
    assert "complete long transcript" in result


def test_fast_mode_bounds_polish_without_changing_selected_model():
    polisher = TextPolisher()
    def setting(name, default=None):
        return "fast" if name == "voice_flow_polish_speed_mode" else default
    with patch("voice_flow.polisher.storage.get_setting", side_effect=setting), \
         patch("voice_flow.polisher.storage.get_all_provider_connections", return_value={}), \
         patch.object(polisher, "_try_provider_call", return_value="Complete polished text") as call:
        assert polisher._polish_with_api_pool("Complete dictated text", {"gemini": "key"}, model_ref="gemini/gemini-3.6-flash")
    assert call.call_args.kwargs["model"] == "gemini-3.6-flash"
    assert call.call_args.kwargs["timeout"] <= 2.5


def test_hosted_gemini_model_keeps_its_selected_provider():
    polisher = TextPolisher()
    with patch("voice_flow.polisher.storage.get_all_provider_connections", return_value={}), \
         patch.object(polisher, "_try_provider_call", return_value="Complete polished text") as call:
        polisher._polish_with_api_pool("Complete dictated text", {"gemini": "native-key", "openrouter": "hosted-key"},
                                      model_ref="openrouter/google/gemini-3.6-flash")
    assert call.call_args.args[:2] == ("openrouter", "hosted-key")
    assert call.call_args.kwargs["model"] == "google/gemini-3.6-flash"


def test_openai_reasoning_model_uses_supported_parameters_and_rejects_truncation():
    polisher = TextPolisher()
    with patch("urllib.request.urlopen", return_value=_response({"choices": [{
        "finish_reason": "length", "message": {"content": "Incomplete sentence"}}]})) as request:
        assert polisher._try_provider_call("openai", "key", "system", "user", "gpt-5") is None
    payload = json.loads(request.call_args.args[0].data)
    assert payload["model"] == "gpt-5" and payload["max_completion_tokens"] > 0
    assert "max_tokens" not in payload and "temperature" not in payload

"""Nebius Token Factory provider + NVIDIA Nemotron routing (all HTTP mocked)."""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any

import pytest

from voice_flow import nebius_provider
from voice_flow.nebius_provider import (
    FAST_LIGHTNING,
    FAST_SUPER,
    REASONING_ULTRA,
    TIER_FAST,
    TIER_REASONING,
    choose_model,
)

SERVED = [
    "meta-llama/Llama-3.3-70B-Instruct",
    FAST_LIGHTNING,
    FAST_SUPER,
    REASONING_ULTRA,
    "nvidia/Nemotron-3.5-Super-VL",
]


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class FakeHTTP:
    """Records every request; answers /models and /chat/completions."""

    def __init__(self, models: list[str] | None = None, chat_content: str = "Polished text.", fail_models: int | None = None):
        self.models = SERVED if models is None else models
        self.chat_content = chat_content
        self.fail_models = fail_models
        self.calls: list[dict[str, Any]] = []

    def __call__(self, request, timeout=None):
        url = request.full_url
        headers = {k.lower(): v for k, v in request.header_items()}
        body = json.loads(request.data.decode("utf-8")) if request.data else None
        self.calls.append({"url": url, "headers": headers, "body": body, "method": request.get_method(), "timeout": timeout})
        if url.endswith("/models"):
            if self.fail_models:
                raise urllib.error.HTTPError(url, self.fail_models, "nope", {}, io.BytesIO(b'{"detail":"bad key"}'))
            return _Response(json.dumps({"object": "list", "data": [{"id": m, "object": "model"} for m in self.models]}).encode())
        if url.endswith("/chat/completions"):
            return _Response(json.dumps({"choices": [{"message": {"content": self.chat_content}, "finish_reason": "stop"}]}).encode())
        raise AssertionError(f"unexpected URL {url}")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    nebius_provider.clear_model_cache()
    yield
    nebius_provider.clear_model_cache()


@pytest.fixture
def no_network(monkeypatch):
    def _boom(*_a, **_k):
        raise AssertionError("network must not be used without a key")

    monkeypatch.setattr("urllib.request.urlopen", _boom)


@pytest.fixture
def provider_service(tmp_path, monkeypatch):
    from voice_flow import video_flow_providers as providers_module

    service = providers_module.VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    monkeypatch.setattr(providers_module, "video_flow_provider_service", service)
    return service


# --- registration ----------------------------------------------------------


def test_nebius_is_registered_like_other_openai_compatible_providers():
    from voice_flow import polisher, provider_registry, video_flow_providers, video_flow_service

    spec = provider_registry.get_provider_spec("nebius")
    assert spec is not None and spec.transport.format == "openai" and spec.transport.auth_header == "bearer"
    assert spec.transport.validate_url == "https://api.tokenfactory.nebius.com/v1/models"

    entry = video_flow_providers.PROVIDER_BY_ID["nebius"]
    assert entry["category"] == "api_key" and entry["auth"] == "api_key" and entry["prefix"] == "nebius"
    seeded = {model for provider, model, _name, _caps in video_flow_providers.DEFAULT_MODELS if provider == "nebius"}
    assert {FAST_LIGHTNING, FAST_SUPER, REASONING_ULTRA, "nemotron-fast", "nemotron-reasoning"} <= seeded

    assert video_flow_service._PLANNING_ENDPOINTS["nebius"] == "https://api.tokenfactory.nebius.com/v1/chat/completions"
    assert polisher.OPENAI_COMPATIBLE_PROVIDERS["nebius"] == (
        "https://api.tokenfactory.nebius.com/v1/chat/completions",
        FAST_LIGHTNING,
    )
    assert nebius_provider.BASE_URL == "https://api.tokenfactory.nebius.com/v1/"


def test_existing_providers_are_unchanged():
    from voice_flow import polisher, video_flow_service

    assert polisher.OPENAI_COMPATIBLE_PROVIDERS["groq"][0] == "https://api.groq.com/openai/v1/chat/completions"
    assert video_flow_service._PLANNING_ENDPOINTS["nvidia_nim"] == "https://integrate.api.nvidia.com/v1/chat/completions"


# --- model list + routing --------------------------------------------------


def test_model_list_uses_bearer_auth_and_is_cached(monkeypatch):
    http = FakeHTTP()
    monkeypatch.setattr("urllib.request.urlopen", http)
    assert nebius_provider.fetch_model_ids("key-1") == SERVED
    assert nebius_provider.fetch_model_ids("key-1") == SERVED  # cached
    assert len(http.calls) == 1
    call = http.calls[0]
    assert call["url"] == "https://api.tokenfactory.nebius.com/v1/models"
    assert call["method"] == "GET"
    assert call["headers"]["authorization"] == "Bearer key-1"


def test_model_list_failure_is_graceful(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", FakeHTTP(fail_models=503))
    assert nebius_provider.fetch_model_ids("key-1") is None
    # Unknown list: the configured default is used as-is.
    assert nebius_provider.resolve_model("", default_tier=TIER_REASONING, api_key="key-1", settings_getter=lambda k, d=None: d) == REASONING_ULTRA


def test_non_blocking_fetch_never_waits_on_cold_cache(monkeypatch):
    started = []
    monkeypatch.setattr(nebius_provider, "warm_model_cache_async", lambda key, timeout=8.0: started.append(key))
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("blocked")))
    assert nebius_provider.fetch_model_ids("key-1", blocking=False) is None
    assert started == ["key-1"]


@pytest.mark.parametrize(
    "tier, available, preferred, expected",
    [
        (TIER_FAST, SERVED, [], FAST_LIGHTNING),
        (TIER_REASONING, SERVED, [], REASONING_ULTRA),
        (TIER_FAST, [FAST_SUPER, REASONING_ULTRA], [], FAST_SUPER),  # Lightning not served
        (TIER_REASONING, [FAST_SUPER], [], FAST_SUPER),  # Ultra not served
        (TIER_FAST, SERVED, [FAST_SUPER], FAST_SUPER),  # user override honoured
        (TIER_FAST, SERVED, ["vendor/not-served"], FAST_LIGHTNING),  # bad override falls back
        (TIER_FAST, None, [], FAST_LIGHTNING),  # list unknown
        (TIER_REASONING, None, ["my/custom-model"], "my/custom-model"),
        (TIER_FAST, ["NVIDIA/nemotron-3_5-lightning"], [], "NVIDIA/nemotron-3_5-lightning"),  # case-insensitive
        (TIER_REASONING, ["nvidia/Nemotron-4-Ultra-1T", "x/y"], [], "nvidia/Nemotron-4-Ultra-1T"),  # renamed id
        (TIER_FAST, ["x/only-model"], [], "x/only-model"),
    ],
)
def test_choose_model(tier, available, preferred, expected):
    assert choose_model(tier, available, preferred) == expected


def test_tier_aliases_and_explicit_models():
    assert nebius_provider.split_requested_model("nemotron-fast", TIER_REASONING) == (TIER_FAST, "")
    assert nebius_provider.split_requested_model("nemotron-reasoning", TIER_FAST) == (TIER_REASONING, "")
    assert nebius_provider.split_requested_model("", TIER_FAST) == (TIER_FAST, "")
    assert nebius_provider.split_requested_model("nebius/" + FAST_SUPER, TIER_FAST) == (TIER_FAST, FAST_SUPER)


def test_per_tier_override_is_saved_and_used(provider_service, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", FakeHTTP())
    nebius_provider.set_tier_override(TIER_FAST, "nebius/" + FAST_SUPER, provider_service)
    assert provider_service.get_setting("nebius_model_fast") == FAST_SUPER
    resolved = nebius_provider.resolve_model(
        "nemotron-fast", default_tier=TIER_FAST, api_key="k", settings_getter=provider_service.get_setting
    )
    assert resolved == FAST_SUPER
    nebius_provider.set_tier_override(TIER_FAST, "", provider_service)
    assert nebius_provider.resolve_model(
        "nemotron-fast", default_tier=TIER_FAST, api_key="k", settings_getter=provider_service.get_setting
    ) == FAST_LIGHTNING
    with pytest.raises(ValueError):
        nebius_provider.set_tier_override(TIER_FAST, "bad model id!", provider_service)


def test_strip_reasoning():
    assert nebius_provider.strip_reasoning("<think>plan it</think>\nHello there.") == "Hello there."
    assert nebius_provider.strip_reasoning("<think>never finished") == ""
    assert nebius_provider.strip_reasoning("Plain answer") == "Plain answer"


# --- keys: saved connection, env var, or nothing ---------------------------


def test_no_key_means_no_calls(provider_service, no_network):
    from voice_flow.video_flow_service import ProviderModelGateway
    from voice_flow.voice_polish_bridge import can_execute_model

    assert nebius_provider.resolve_api_key(provider_service) == ""
    assert ProviderModelGateway._from_video_provider_service("nebius", "") is None
    assert can_execute_model("nebius/nemotron-fast") is False
    public = provider_service._public_provider(provider_service.provider("nebius"))
    assert public["status"] == "disconnected"


def test_env_key_is_used_when_nothing_is_saved(provider_service, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "env-key")
    assert nebius_provider.resolve_api_key(provider_service) == "env-key"
    public = provider_service._public_provider(provider_service.provider("nebius"))
    assert public["status"] == "connected" and public.get("env_key_in_use") is True


def test_saved_connection_wins_over_env(provider_service, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "env-key")
    provider_service.add_connection("nebius", name="Main", secret="saved-key")
    assert nebius_provider.resolve_api_key(provider_service) == "saved-key"


# --- Settings "Test" button -----------------------------------------------


def test_settings_test_button_calls_v1_models(provider_service, monkeypatch):
    http = FakeHTTP()
    monkeypatch.setattr("urllib.request.urlopen", http)
    conn = provider_service.add_connection("nebius", name="Main", secret="saved-key")
    result = provider_service.test_connection(conn["id"])
    assert result["success"] is True and result["status"] == "connected"
    assert result["routing"] == {TIER_FAST: FAST_LIGHTNING, TIER_REASONING: REASONING_ULTRA}
    assert REASONING_ULTRA in result["nemotron_models"]
    assert http.calls[0]["url"] == "https://api.tokenfactory.nebius.com/v1/models"
    assert http.calls[0]["headers"]["authorization"] == "Bearer saved-key"
    assert provider_service.get_connection(conn["id"])["status"] == "connected"
    details = provider_service.provider_details("nebius")
    assert details["nebius_routing"]["validated"] is True
    assert details["nebius_routing"]["tiers"][TIER_REASONING]["resolved"] == REASONING_ULTRA


def test_settings_test_button_reports_bad_key(provider_service, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", FakeHTTP(fail_models=401))
    conn = provider_service.add_connection("nebius", name="Main", secret="bad")
    result = provider_service.test_connection(conn["id"])
    assert result["success"] is False and "401" in result["error"]
    assert provider_service.get_connection(conn["id"])["status"] == "error"


# --- the three flows -------------------------------------------------------


def test_video_flow_gateway_uses_reasoning_tier(provider_service, monkeypatch):
    from voice_flow.video_flow_service import ProviderModelGateway

    monkeypatch.setattr("urllib.request.urlopen", FakeHTTP())
    provider_service.add_connection("nebius", name="Main", secret="saved-key")
    gateway = ProviderModelGateway._from_video_provider_service("nebius", "")
    assert gateway is not None
    assert gateway._model_id == REASONING_ULTRA
    assert gateway._endpoint == "https://api.tokenfactory.nebius.com/v1/chat/completions"
    assert gateway._api_key == "saved-key"

    # A picked model the account does not serve falls back to the tier model.
    gateway = ProviderModelGateway._from_video_provider_service("nebius", "nvidia/retired-model")
    assert gateway._model_id == REASONING_ULTRA

    # from_storage routes an explicit Nebius pick through the same path.
    class _Storage:
        def get_setting(self, key, default=None):
            return default

        def get_provider_connections(self, provider):
            return []

    gateway = ProviderModelGateway.from_storage(_Storage(), "nebius/nemotron-reasoning")
    assert gateway._provider == "nebius" and gateway._model_id == REASONING_ULTRA


def test_video_flow_reasoning_tier_falls_back_when_ultra_missing(provider_service, monkeypatch):
    from voice_flow.video_flow_service import ProviderModelGateway

    monkeypatch.setattr("urllib.request.urlopen", FakeHTTP(models=[FAST_LIGHTNING, FAST_SUPER]))
    provider_service.add_connection("nebius", name="Main", secret="k")
    assert ProviderModelGateway._from_video_provider_service("nebius", "")._model_id == FAST_SUPER


def test_voice_polish_uses_fast_tier(provider_service, monkeypatch):
    from voice_flow import voice_polish_bridge
    from voice_flow import voice_provider_transport

    provider_service.add_connection("nebius", name="Main", secret="voice-key")
    # Warm the cache the way the Test button does.
    monkeypatch.setattr("urllib.request.urlopen", FakeHTTP())
    nebius_provider.fetch_model_ids("voice-key")

    sent = {}

    def fake_request_chat(**kwargs):
        sent.update(kwargs)
        return "<think>tidy</think>Hello, world.", "ok"

    monkeypatch.setattr(voice_provider_transport, "request_chat", fake_request_chat)
    assert voice_polish_bridge.can_execute_model("nebius/nemotron-fast") is True
    out = voice_polish_bridge.request_polish("nebius/nemotron-fast", "hello world", timeout_seconds=3.0)
    assert out == "Hello, world."
    assert sent["model"] == FAST_LIGHTNING
    assert sent["endpoint"] == "https://api.tokenfactory.nebius.com/v1/chat/completions"
    assert sent["api_key"] == "voice-key"


def test_voice_polish_cold_cache_does_not_block(provider_service, monkeypatch):
    from voice_flow import voice_polish_bridge
    from voice_flow import voice_provider_transport

    provider_service.add_connection("nebius", name="Main", secret="voice-key")
    monkeypatch.setattr(nebius_provider, "warm_model_cache_async", lambda *a, **k: None)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("blocked on /models")))
    sent = {}
    monkeypatch.setattr(voice_provider_transport, "request_chat", lambda **kw: (sent.update(kw) or ("Hi.", "ok")))
    assert voice_polish_bridge.request_polish("nebius/nemotron-fast", "hi", timeout_seconds=2.0) == "Hi."
    assert sent["model"] == FAST_LIGHTNING


def test_audio_flow_summary_uses_fast_tier(provider_service, monkeypatch):
    from voice_flow import audio_summary

    monkeypatch.setattr(audio_summary, "video_flow_provider_service", provider_service)
    provider_service.add_connection("nebius", name="Main", secret="audio-key")
    http = FakeHTTP(chat_content="<think>outline</think>A short spoken summary.")
    monkeypatch.setattr("urllib.request.urlopen", http)
    service = audio_summary.AudioSummaryService()
    text = service._dispatch_llm_prompt("Summarise this.", "nebius/nemotron-fast", service_label="Audio Summary")
    assert text == "A short spoken summary."
    chat = [c for c in http.calls if c["url"].endswith("/chat/completions")][0]
    assert chat["url"] == "https://api.tokenfactory.nebius.com/v1/chat/completions"
    assert chat["body"]["model"] == FAST_LIGHTNING
    assert chat["headers"]["authorization"] == "Bearer audio-key"


def test_audio_flow_without_key_raises_clear_error(provider_service, monkeypatch, no_network):
    from voice_flow import audio_summary

    monkeypatch.setattr(audio_summary, "video_flow_provider_service", provider_service)
    with pytest.raises(audio_summary.AudioSummaryError):
        audio_summary.AudioSummaryService()._dispatch_llm_prompt("x", "nebius/nemotron-fast")

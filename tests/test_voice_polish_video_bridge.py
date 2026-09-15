"""Regression coverage for the Video Flow-backed AI polish picker/runtime."""

from __future__ import annotations

from unittest.mock import patch

from voice_flow import polisher as polisher_module
from voice_flow.polisher import TextPolisher
from voice_flow import voice_polish_bridge


def _settings(*, enabled=True, mode="balanced", model="codex/gpt-5.4-mini"):
    def get_setting(key, default=None):
        if key == "polishing_enabled":
            return enabled
        if key == "voice_flow_polish_speed_mode":
            return mode
        if key == "voice_flow_polish_model":
            return model
        return default
    return get_setting


def test_disabled_polishing_blocks_force_ai_remote_path(monkeypatch):
    called = []
    engine = TextPolisher()
    monkeypatch.setattr(polisher_module.storage, "get_setting", _settings(enabled=False))
    monkeypatch.setattr(polisher_module.storage, "get_all_api_keys", lambda: {"gemini": "k"})
    monkeypatch.setattr(engine, "_polish_with_api_pool", lambda *_args, **_kwargs: called.append(True) or "remote")
    monkeypatch.setattr("voice_flow.polisher.dictionary_engine.apply_dictionary_post_processing", lambda text: text)

    assert engine.polish("um keep this local", force_ai=True) == "Um keep this local."
    assert called == []


def test_bridge_resolves_the_catalogue_provider_without_aliasing(monkeypatch):
    """Catalog capability checks do not invoke the OAuth-refreshing gateway."""
    from voice_flow.video_flow_providers import video_flow_provider_service
    from voice_flow.video_flow_service import ProviderModelGateway

    seen = []
    monkeypatch.setattr(
        ProviderModelGateway,
        "_from_video_provider_service",
        classmethod(lambda _cls, provider, model: (_ for _ in ()).throw(AssertionError("catalog must not resolve gateway"))),
    )
    monkeypatch.setattr(video_flow_provider_service, "active_connections", lambda provider: seen.append(provider) or [{"secret": "encrypted", "status": "active"}])

    assert voice_polish_bridge.can_execute_model("gemini/gemini-3.5-flash") is True
    assert seen == ["gemini"]


def test_exact_video_model_is_attempted_through_video_gateway_before_legacy_pool(monkeypatch):
    engine = TextPolisher()
    calls = []
    monkeypatch.setattr(polisher_module.storage, "get_setting", _settings())
    monkeypatch.setattr(polisher_module.storage, "get_all_api_keys", lambda: {})
    monkeypatch.setattr(polisher_module.storage, "get_all_provider_connections", lambda: {})
    monkeypatch.setattr("voice_flow.voice_polish_bridge.can_execute_model", lambda _ref: True)
    monkeypatch.setattr("voice_flow.voice_polish_bridge.request_polish", lambda ref, prompt, **kwargs: calls.append((ref, kwargs["timeout_seconds"])) or "Please keep this exact model selected.")
    monkeypatch.setattr(engine, "_try_provider_call", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy pool should not run")))

    assert engine.polish("please keep this exact model selected") == "Please keep this exact model selected."
    assert calls and calls[0][0] == "codex/gpt-5.4-mini"


def test_video_oauth_selection_keeps_its_provider_when_legacy_alias_key_exists(monkeypatch):
    """An Antigravity OAuth model must not be silently sent to a Gemini key."""
    engine = TextPolisher()
    calls = []
    monkeypatch.setattr(polisher_module.storage, "get_setting", _settings(model="antigravity/gemini-3.5-flash"))
    monkeypatch.setattr(polisher_module.storage, "get_all_api_keys", lambda: {"gemini": "legacy-key"})
    monkeypatch.setattr(polisher_module.storage, "get_all_provider_connections", lambda: {})
    monkeypatch.setattr("voice_flow.voice_polish_bridge.can_execute_model", lambda ref: calls.append(("can", ref)) or True)
    monkeypatch.setattr("voice_flow.voice_polish_bridge.request_polish", lambda ref, _prompt, **_kwargs: calls.append(("run", ref)) or "Keep the OAuth provider.")
    monkeypatch.setattr(engine, "_try_provider_call", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy fallback should not run")))

    assert engine.polish("keep the oauth provider") == "Keep the OAuth provider."
    assert calls == [("can", "antigravity/gemini-3.5-flash"), ("run", "antigravity/gemini-3.5-flash")]


def test_selected_video_failure_does_not_substitute_a_legacy_provider(monkeypatch):
    engine = TextPolisher()
    legacy_calls = []
    monkeypatch.setattr(polisher_module.storage, "get_setting", _settings(model="antigravity/gemini-3.5-flash"))
    monkeypatch.setattr(polisher_module.storage, "get_all_api_keys", lambda: {"gemini": "legacy-key"})
    monkeypatch.setattr(polisher_module.storage, "get_all_provider_connections", lambda: {})
    monkeypatch.setattr("voice_flow.voice_polish_bridge.can_execute_model", lambda _ref: True)
    monkeypatch.setattr("voice_flow.voice_polish_bridge.request_polish", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(engine, "_try_provider_call", lambda provider, _key, *_args, **kwargs: legacy_calls.append((provider, kwargs["model"])) or "Legacy fallback worked.")

    result = engine.polish("legacy fallback worked")
    assert "legacy fallback worked" in result.lower()
    assert legacy_calls == []


def test_unrunnable_selected_gemini_uses_only_its_exact_legacy_model(monkeypatch):
    engine = TextPolisher()
    calls = []
    monkeypatch.setattr(polisher_module.storage, "get_setting", _settings(model="gemini/gemini-3.7-flash"))
    monkeypatch.setattr(polisher_module.storage, "get_all_api_keys", lambda: {"gemini": "gemini-key", "groq": "groq-key"})
    monkeypatch.setattr(polisher_module.storage, "get_all_provider_connections", lambda: {})
    monkeypatch.setattr("voice_flow.voice_polish_bridge.can_execute_model", lambda _ref: False)
    monkeypatch.setattr(
        engine, "_try_provider_call",
        lambda provider, _key, *_args, **kwargs: calls.append((provider, kwargs["model"])) or "Keep the selected Gemini model.",
    )

    assert engine.polish("keep the selected gemini model") == "Keep the selected Gemini model."
    assert calls == [("gemini", "gemini-3.7-flash")]


def test_selected_audio_named_model_is_not_ignored_for_automatic_provider_fallback(monkeypatch):
    engine = TextPolisher()
    calls = []
    monkeypatch.setattr(polisher_module.storage, "get_all_provider_connections", lambda: {})
    monkeypatch.setattr("voice_flow.voice_polish_bridge.can_execute_model", lambda _ref: False)
    monkeypatch.setattr(
        engine, "_try_provider_call",
        lambda provider, _key, *_args, **kwargs: calls.append((provider, kwargs["model"])) or "Exact model output.",
    )

    assert engine._polish_with_api_pool(
        "Keep the audio label exact.", {"gemini": "gemini-key", "groq": "groq-key"},
        model_ref="gemini/gemini-audio-polish-preview",
    ) == "Exact model output."
    assert calls == [("gemini", "gemini-audio-polish-preview")]


def test_selected_legacy_timeout_does_not_race_a_second_credential(monkeypatch):
    engine = TextPolisher()
    calls = []
    monkeypatch.setattr(polisher_module.storage, "get_setting", _settings(model="gemini/gemini-3.7-flash"))
    monkeypatch.setattr(polisher_module.storage, "get_all_provider_connections", lambda: {
        "gemini": [{"id": 7, "name": "second", "api_key": "second-key", "is_active": 1}],
    })
    monkeypatch.setattr("voice_flow.voice_polish_bridge.can_execute_model", lambda _ref: False)

    def timeout(provider, key, *_args, **kwargs):
        calls.append((provider, key, kwargs["model"]))
        engine._last_attempt_status = "timeout"
        return None

    monkeypatch.setattr(engine, "_try_provider_call", timeout)
    assert engine._polish_with_api_pool("Keep every dictated word here.", {"gemini": "first-key"}, model_ref="gemini/gemini-3.7-flash") is None
    assert calls == [("gemini", "first-key", "gemini-3.7-flash")]


def test_selected_legacy_rotates_only_same_provider_after_definitive_failure(monkeypatch):
    engine = TextPolisher()
    calls = []
    monkeypatch.setattr(polisher_module.storage, "get_setting", _settings(model="gemini/gemini-3.7-flash"))
    monkeypatch.setattr(polisher_module.storage, "get_all_provider_connections", lambda: {
        "gemini": [{"id": 7, "name": "second", "api_key": "second-key", "is_active": 1}],
    })
    monkeypatch.setattr("voice_flow.voice_polish_bridge.can_execute_model", lambda _ref: False)

    def call(provider, key, *_args, **kwargs):
        calls.append((provider, key, kwargs["model"]))
        if key == "first-key":
            engine._last_attempt_status = "http_401"
            return None
        return "Keep every dictated word here."

    monkeypatch.setattr(engine, "_try_provider_call", call)
    assert engine._polish_with_api_pool("Keep every dictated word here.", {"gemini": "first-key", "groq": "other-key"}, model_ref="gemini/gemini-3.7-flash") == "Keep every dictated word here."
    assert calls == [
        ("gemini", "first-key", "gemini-3.7-flash"),
        ("gemini", "second-key", "gemini-3.7-flash"),
    ]


def test_antigravity_bridge_never_uses_a_gemini_api_key_as_an_alias(monkeypatch):
    monkeypatch.setattr(
        "voice_flow.video_flow_providers.video_flow_provider_service.active_connections", lambda _provider: []
    )
    monkeypatch.setattr("voice_flow.voice_gemini_transport.request_gemini_polish", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not alias OAuth to Gemini key")))

    assert voice_polish_bridge.request_polish("antigravity/gemini-3.7-flash", "clean", timeout_seconds=1) is None


def test_speed_modes_set_distinct_budgets_for_exact_model(monkeypatch):
    results = {}
    for mode in ("fast", "balanced", "quality"):
        engine = TextPolisher()
        seen = []
        monkeypatch.setattr(polisher_module.storage, "get_setting", _settings(mode=mode))
        monkeypatch.setattr(polisher_module.storage, "get_all_api_keys", lambda: {})
        monkeypatch.setattr(polisher_module.storage, "get_all_provider_connections", lambda: {})
        monkeypatch.setattr("voice_flow.voice_polish_bridge.can_execute_model", lambda _ref: True)
        with patch("voice_flow.voice_polish_bridge.request_polish", side_effect=lambda _ref, _prompt, **kwargs: seen.append((kwargs["timeout_seconds"], kwargs["speed_mode"])) or None):
            engine._polish_with_api_pool("this transcript has enough words to skip no policy", {}, model_ref="codex/gpt-5.4-mini")
        results[mode] = seen[0]

    assert results["fast"][0] < results["balanced"][0] < results["quality"][0]
    assert {mode: result[1] for mode, result in results.items()} == {
        "fast": "fast", "balanced": "balanced", "quality": "quality",
    }


def test_video_gateway_uses_native_low_thinking_gemini_only_for_voice_polish(monkeypatch):
    from voice_flow.video_flow_service import ProviderModelGateway, _GEMINI_POLISH_WORKER

    captured = {}

    class Process:
        returncode = 0

        def communicate(self, raw, timeout):
            captured.update(__import__("json").loads(raw))
            return ('{"ok": true, "content": "Polished.", "http_status": 200}', "")

    monkeypatch.setattr("voice_flow.video_flow_service.subprocess.Popen", lambda *_args, **_kwargs: Process())
    gateway = ProviderModelGateway(api_key="key", provider="gemini", model_id="gemini-3.5-flash")
    assert gateway.request_isolated(prompt="clean", model_ref="gemini/gemini-3.5-flash", max_tokens=800,
                                    timeout_seconds=1, job_id="test", process_manager=voice_polish_bridge._PolishProcessManager(),
                                    reasoning_compatible=True) == "Polished."
    assert captured["voice_polish"] is True
    assert 'model.lower().startswith("gemini-3")' in _GEMINI_POLISH_WORKER
    assert '"thinkingLevel": "minimal" if "flash" in model.lower() else "low"' in _GEMINI_POLISH_WORKER
    assert "urllib.parse" in _GEMINI_POLISH_WORKER


def test_bridge_uses_keep_alive_transport_only_after_exact_gemini_gateway_resolution(monkeypatch):
    class Gateway:
        _provider = "gemini"
        _api_key = "synthetic-key"
        _model_id = "gemini-3.6-flash"

    seen = {}
    monkeypatch.setattr(
        __import__("voice_flow.video_flow_service", fromlist=["ProviderModelGateway"]).ProviderModelGateway,
        "_from_video_provider_service", classmethod(lambda *_args: Gateway()),
    )
    monkeypatch.setattr("voice_flow.voice_gemini_transport.request_gemini_polish",
                        lambda **kwargs: seen.update(kwargs) or "Polished.")

    assert voice_polish_bridge.request_polish(
        "gemini/gemini-3.6-flash", "clean", timeout_seconds=1, speed_mode="quality"
    ) == "Polished."
    assert seen["model"] == "gemini-3.6-flash"
    assert seen["api_key"] == "synthetic-key"
    assert seen["speed_mode"] == "quality"

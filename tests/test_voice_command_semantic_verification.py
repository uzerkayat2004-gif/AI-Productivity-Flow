"""Offline bounded semantic adjudication of explicit cloud commands."""
import json
import time
from types import SimpleNamespace

import pytest
from voice_flow import polisher as module
from voice_flow.voice_commands import detect_voice_command


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr(module.storage, "get_setting", lambda key, default=None: True if key == "polishing_enabled" else default)
    monkeypatch.setattr(module.storage, "get_all_api_keys", lambda: {"gemini": "synthetic"})
    engine = module.TextPolisher()
    monkeypatch.setattr(engine, "_record_polish_latency", lambda *args: None)
    return engine


def run(engine, monkeypatch, source="We have to fix the app.", candidate="Fix the app.", verdict='{"faithful":true,"fulfills_command":true}', **kwargs):
    command = detect_voice_command(source + " Hey Voice Flow make this a prompt.").command
    calls = []
    def pool(*args, **meta):
        calls.append((args, meta))
        return verdict if meta.get("verification") else candidate
    monkeypatch.setattr(engine, "_polish_with_api_pool", pool)
    outcomes = []
    result = engine.polish(source, "Make this a prompt.", force_ai=True,
                           task="prompt", command_format="prompt", command=command,
                           model_ref="gemini/exact-selected", outcome_callback=outcomes.append, **kwargs)
    return result, calls, outcomes


def test_arbitrary_rephrase_uses_independent_selected_model_verifier(engine, monkeypatch):
    result, calls, outcomes = run(engine, monkeypatch)
    assert result == "Fix the app."
    assert outcomes == ["ai_accepted"]
    assert len(calls) == 2
    args, meta = calls[1]
    assert json.loads(args[0]) == {"source": "We have to fix the app.", "candidate": "Fix the app.", "command": "Make this a prompt."}
    assert args[2] == ""
    assert meta["model_ref"] == "gemini/exact-selected"
    assert meta["verification"] is True
    assert "untrusted data" in meta["system_prompt"]
    assert "We have to fix" not in meta["system_prompt"]
    assert meta["deadline"] > time.monotonic()


@pytest.mark.parametrize("verdict", [None, "", "not JSON", '```json\n{"faithful":true,"fulfills_command":true}\n```',
    '{"faithful":false,"fulfills_command":true}', '{"faithful":true,"fulfills_command":false}',
    '{"faithful":1,"fulfills_command":true}', '{"faithful":true}',
    '{"faithful":true,"fulfills_command":true,"reason":"fine"}',
    '{"faithful":false,"faithful":true,"fulfills_command":true}'])
def test_verifier_rejects_without_retry(engine, monkeypatch, verdict):
    result, calls, outcomes = run(engine, monkeypatch, verdict=verdict)
    assert result != "Fix the app."
    assert len(calls) == 2
    assert outcomes == ["command_unfulfilled"]


@pytest.mark.parametrize(("source", "candidate"), [
    ("We have to fix 3 bugs.", "Fix 5 bugs."),
    ("We have to fix https://example.test/a.", "Fix https://example.test/b."),
    ("We have to preserve `x = 3`.", "Preserve `x = 4`."),
])
def test_literal_changes_never_reach_verifier(engine, monkeypatch, source, candidate):
    result, calls, _ = run(engine, monkeypatch, source=source, candidate=candidate)
    assert result != candidate
    assert len(calls) == 1


def test_remaining_deadline_exhausted_before_verifier(engine, monkeypatch):
    monkeypatch.setattr(engine, "_remaining_budget", lambda deadline: 0)
    result, calls, _ = run(engine, monkeypatch)
    assert result != "Fix the app."
    assert len(calls) == 1


def test_preserve_wording_never_verifies(engine, monkeypatch):
    seen = []
    monkeypatch.setattr(engine, "_polish_with_api_pool", lambda *args, **kwargs: seen.append(kwargs) or "Fix the app.")
    result = engine.polish("We have to fix the app.", "Keep my wording.", force_ai=True,
                          model_ref="gemini/exact-selected", task="prompt",
                          command=SimpleNamespace(preserve_wording=True))
    assert result != "Fix the app."
    assert len(seen) == 1


def test_off_never_verifies(engine, monkeypatch):
    monkeypatch.setattr(module.storage, "get_setting", lambda key, default=None: False if key == "polishing_enabled" else default)
    result, calls, outcomes = run(engine, monkeypatch)
    assert result == "We have to fix the app."
    assert calls == []
    assert outcomes == ["disabled"]


def test_provider_error_fails_closed_once(engine, monkeypatch):
    seen = []
    def pool(*args, **kwargs):
        seen.append(kwargs)
        if kwargs.get("verification"):
            raise RuntimeError("synthetic provider failure")
        return "Fix the app."
    monkeypatch.setattr(engine, "_polish_with_api_pool", pool)
    result = engine.polish("We have to fix the app.", "Make this a prompt.", force_ai=True,
                          task="prompt", command_format="prompt", model_ref="gemini/exact-selected",
                          command=detect_voice_command("We have to fix the app. Hey Voice Flow make this a prompt.").command)
    assert result != "Fix the app."
    assert len(seen) == 2


def test_verification_pool_never_fails_over_or_uses_fast_lane(engine, monkeypatch):
    monkeypatch.setattr(module.storage, "get_all_provider_connections", lambda: {})
    seen = []
    def provider(*args, **kwargs):
        seen.append((args, kwargs))
        return None
    monkeypatch.setattr(engine, "_try_provider_call_with_deadline", provider)
    result = engine._polish_with_api_pool('{"source":"untrusted"}', {"gemini":"synthetic", "anthropic":"other"},
        model_ref="gemini/exact-selected", verification=True,
        system_prompt=module._COMMAND_VERIFICATION_SYSTEM_PROMPT, deadline=time.monotonic()+10)
    assert result is None
    assert len(seen) == 1
    assert seen[0][0][0] == "gemini"
    assert seen[0][1]["model"] == "exact-selected"
    assert seen[0][0][3] == '{"source":"untrusted"}'


@pytest.mark.parametrize("task, recognized", [("cleanup", True), ("prompt", False)])
def test_only_explicit_transform_commands_can_verify(engine, monkeypatch, task, recognized):
    seen = []
    monkeypatch.setattr(engine, "_polish_with_api_pool", lambda *args, **kwargs: seen.append(kwargs) or "Fix the app.")
    result = engine.polish("We have to fix the app.", "Make this a prompt.", force_ai=True,
                          task=task, model_ref="gemini/exact-selected",
                          command=SimpleNamespace(preserve_wording=False) if recognized else None)
    assert result != "Fix the app."
    assert len(seen) == 1


def test_expired_deadline_never_enters_pool(engine, monkeypatch):
    result, calls, outcomes = run(engine, monkeypatch, deadline=time.monotonic()-1)
    assert result != "Fix the app."
    assert calls == []
    assert outcomes == ["timeout"]


def test_verifier_response_after_deadline_rejected(engine, monkeypatch):
    budgets = iter([10, 0])
    monkeypatch.setattr(engine, "_remaining_budget", lambda deadline: next(budgets))
    monkeypatch.setattr(engine, "_polish_with_api_pool", lambda *args, **kwargs: '{"faithful":true,"fulfills_command":true}')
    assert not engine._verify_cloud_command("We have to fix the app.", "Fix the app.", "Make this a prompt.",
                                           {}, model_ref="gemini/exact-selected", deadline=time.monotonic()+10)

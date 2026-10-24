"""Offline finalization coverage for the user's voiced flow transcript."""
from types import SimpleNamespace

import importlib.util
import json
from pathlib import Path


def _load_test_helper(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


finalizer = _load_test_helper("test_voice_command_finalization").finalizer
ACTUAL_USER_TRANSCRIPT = _load_test_helper("test_voice_command_voiced_flow").ACTUAL_USER_TRANSCRIPT
from voice_flow import polisher as polish_module
from voice_flow.effective_style import resolve_effective_style
from voice_flow.voice_commands import detect_voice_command


import pytest


CANDIDATE = "Investigate why the same problems keep happening in the app and find a way to fix them."


def _exercise(monkeypatch, instruction, candidate, verdict):
    source = ACTUAL_USER_TRANSCRIPT.removesuffix(" hey voiced flow make this as a prompt.")
    detection = detect_voice_command(source + " hey voiced flow " + instruction + ".")
    assert detection.command is not None
    assert detection.content == source
    monkeypatch.setattr(polish_module.storage, "get_setting", lambda key, default=None: True if key == "polishing_enabled" else default)
    monkeypatch.setattr(polish_module.storage, "get_all_api_keys", lambda: {"gemini": "synthetic"})
    engine = polish_module.TextPolisher()
    seen = []
    def fake_pool(*args, **kwargs):
        seen.append((args, kwargs))
        return candidate if len(seen) == 1 else verdict
    monkeypatch.setattr(engine, "_polish_with_api_pool", fake_pool)
    monkeypatch.setattr(engine, "_record_polish_latency", lambda *args, **kwargs: None)
    base = SimpleNamespace(category="other", style_id="other_formal", instruction="Use clear prose.")
    effective = resolve_effective_style(base, detection.command)
    session = SimpleNamespace(cleanup_level="cleanup_light", style_id="other_formal", cursor_context=None,
                              polish_model_ref="gemini/exact-selected", polish_speed_mode="quality")
    outcomes = []
    calls = []
    original = engine.polish
    def capture(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(engine, "polish", capture)
    result = finalizer(engine)._finalize_text(detection.content, session, effective=effective,
                                             command=detection.command, outcome_callback=outcomes.append)
    assert seen[0][0][0] == source
    assert all(call[1]["model_ref"] == "gemini/exact-selected" for call in seen)
    assert all("hey voiced flow" not in str(call) for call in seen)
    if len(seen) > 1:
        assert seen[1][1]["verification"] is True
        payload = json.loads(seen[1][0][0])
        assert payload["source"] == source
        assert payload["candidate"] == candidate
        assert payload["command"]
    assert "hey voiced flow" not in result.lower()
    return result, outcomes, seen, calls, source


@pytest.mark.parametrize(("instruction", "candidate", "task"), [
    ("make this as a prompt", CANDIDATE, "prompt"),
    ("make this an email", "Hello,\n\nThe same problems keep happening in the app. Please investigate and find a way to fix them.\n\nBest regards,", "rewrite"),
    ("make this professional", "The same problems keep recurring in the app. Please investigate their cause and find a way to resolve them.", "rewrite"),
    ("make this a normal message", "The same problems keep happening in the app. Can you figure out why and find a way to fix them?", "rewrite"),
])
def test_explicit_alias_command_accepts_verified_faithful_paraphrase(monkeypatch, instruction, candidate, task):
    result, outcomes, seen, calls, source = _exercise(
        monkeypatch, instruction, candidate, '{"faithful":true,"fulfills_command":true}')
    assert calls[0]["task"] == task
    assert len(seen) == 2
    expected = candidate.lower().rstrip(".") if instruction == "make this a normal message" else candidate
    assert result == expected
    assert result != source
    assert outcomes == ["ai_accepted"]


def test_negative_semantic_verdict_preserves_source(monkeypatch):
    result, outcomes, seen, calls, source = _exercise(
        monkeypatch, "make this as a prompt", CANDIDATE,
        '{"faithful":false,"fulfills_command":true}')
    assert len(seen) == 2
    assert result == source + "."
    assert result != CANDIDATE
    assert "ai_accepted" not in outcomes

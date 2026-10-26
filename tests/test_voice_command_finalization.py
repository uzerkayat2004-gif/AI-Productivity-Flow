"""Exercise the real finalization methods without constructing desktop devices."""
from __future__ import annotations

import ast
import logging
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from voice_flow import polisher as polish_module
from voice_flow.effective_style import resolve_effective_style
from voice_flow.text_processing import smart_format, format_email_command_fallback
from voice_flow.voice_commands import detect_voice_command


def finalizer(engine):
    """Load production method bodies, without importing main's device globals."""
    path = Path(__file__).parents[1] / "src/voice_flow/main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    helpers = {"_call_with_optional_deadline", "_normalize_polish_speed_mode", "_polishing_enabled"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in helpers]
    app = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "VoiceFlowApp")
    methods = [node for node in app.body if isinstance(node, ast.FunctionDef)
               and node.name in {"_finalize_text", "_finalize_text_routes"}]
    namespace = dict(
        polisher=engine, storage=polish_module.storage,
        dictionary_engine=polish_module.dictionary_engine,
        smart_format=smart_format, time=time, log=logging.getLogger(__name__),
        format_email_command_fallback=format_email_command_fallback,
        AI_POLISH_DETERMINISTIC_RESERVE_SECONDS=polish_module.AI_POLISH_DETERMINISTIC_RESERVE_SECONDS,
    )
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
                             *nodes, *methods], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
    return type("Finalizer", (), {method.name: namespace[method.name] for method in methods})()


@pytest.mark.parametrize(("command", "candidate"), [
    ("make this a prompt", "Diagnose why my app is not working, identify the cause of the problem, and fix it."),
    ("make this a professional email", "Hello,\n\nMy app is not working. Please investigate the issue and fix it.\n\nBest regards,"),
    ("make this a normal message", "My app is not working. Please look into the issue and fix it."),
])
def test_trailing_command_survives_final_formatting(monkeypatch, command, candidate):
    source = "Hey right now my app is not working and I don't know what is happening on the app, can you look into it and fix it."
    detection = detect_voice_command(source + " Hey Voice Flow " + command + ".")
    monkeypatch.setattr(polish_module.storage, "get_setting", lambda key, default=None: True if key == "polishing_enabled" else default)
    monkeypatch.setattr(polish_module.storage, "get_all_api_keys", lambda: {"gemini": "synthetic"})
    engine = polish_module.TextPolisher()
    seen = []
    monkeypatch.setattr(engine, "_polish_with_api_pool", lambda *args, **kwargs: seen.append((args, kwargs)) or candidate)
    monkeypatch.setattr(engine, "_record_polish_latency", lambda *args, **kwargs: None)
    base = SimpleNamespace(category="other", style_id="other_formal", instruction="Use clear prose.")
    effective = resolve_effective_style(base, detection.command)
    session = SimpleNamespace(cleanup_level="cleanup_light", style_id="other_formal", cursor_context=None,
                              polish_model_ref="gemini/exact-selected", polish_speed_mode="quality")
    outcomes = []
    result = finalizer(engine)._finalize_text(detection.content, session, effective=effective,
                                             command=detection.command, outcome_callback=outcomes.append)
    expected = candidate.lower().rstrip(".") if command == "make this a normal message" else candidate
    assert result == expected
    assert outcomes == ["ai_accepted"]
    assert seen[0][0][0] == source
    assert seen[0][1]["model_ref"] == "gemini/exact-selected"
    assert seen[0][1]["speed_mode"] == "quality"
    assert "Transform only the transcript" in seen[0][1]["system_prompt"]


def test_pool_passes_command_policy_and_body_separately(monkeypatch):
    from voice_flow import voice_polish_bridge
    monkeypatch.setattr(polish_module.storage, "get_all_provider_connections", lambda: {})
    monkeypatch.setattr(voice_polish_bridge, "can_execute_model", lambda ref: True)
    captured = []
    monkeypatch.setattr(voice_polish_bridge, "request_polish", lambda ref, body, **kwargs: captured.append((ref, body, kwargs)) or "Rewritten.")
    engine = polish_module.TextPolisher()
    result = engine._polish_with_api_pool("My exact body.", {}, model_ref="gemini/exact-selected",
                                        system_prompt="Trusted command policy", speed_mode="quality")
    assert result == "Rewritten."
    assert captured[0][0] == "gemini/exact-selected"
    assert "My exact body." in captured[0][1]
    assert "Trusted command policy" not in captured[0][1]
    assert captured[0][2]["system_prompt"] == "Trusted command policy"


def test_interactive_gemini_uses_separate_policy(monkeypatch):
    from voice_flow import voice_gemini_transport
    captured = []
    monkeypatch.setattr(voice_gemini_transport, "request_gemini_polish", lambda **kwargs: captured.append(kwargs) or "Rewritten.")
    monkeypatch.setattr(voice_gemini_transport, "last_transport_diagnostic", lambda: {"status": "ok"})
    engine = polish_module.TextPolisher()
    engine._attempt_state.interactive = True
    result = engine._try_provider_call("gemini", "synthetic", system_prompt="Trusted command policy",
                                       user_content="My exact body.", model="exact-selected", timeout=3)
    assert result == "Rewritten."
    assert captured[0]["model"] == "exact-selected"
    assert captured[0]["prompt"] == "My exact body."
    assert captured[0]["system_prompt"] == "Trusted command policy"


def test_email_closing_does_not_gain_sentence_punctuation():
    assert smart_format('Please review the report.\n\nBest regards,\nAlex', 'email_formal') == 'Please review the report.\n\nBest regards,\nAlex'
    assert smart_format('Please review the report', 'email_formal') == 'Please review the report.'

"""Rate-limit reporting through real finalization bodies, without desktop imports."""
import ast
import importlib.util
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from voice_flow import polisher as module
from voice_flow.effective_style import resolve_effective_style
from voice_flow.voice_commands import detect_voice_command

MAIN_PATH = Path(__file__).parents[1] / "src/voice_flow/main.py"
TREE = ast.parse(MAIN_PATH.read_text(encoding="utf-8"))


def main_helpers():
    names = {"_COMMAND_NOT_PERFORMED", "_polish_outcome_label", "_processing_metadata"}
    nodes = [node for node in TREE.body if
             isinstance(node, ast.FunctionDef) and node.name in names or
             isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in names for target in node.targets)]
    ns = {}
    code = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(code), str(MAIN_PATH), "exec"), ns)
    return ns


def finalizer(engine):
    path = Path(__file__).with_name("test_voice_command_finalization.py")
    spec = importlib.util.spec_from_file_location("rate_limit_finalizer_helper", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper.finalizer(engine)


@pytest.mark.parametrize("verification", [False, True])
def test_rate_limit_keeps_source_and_outcome_through_finalization(monkeypatch, verification):
    source = "We have to investigate the violet indicator."
    detection = detect_voice_command(source + " Hey Voice Flow make this a prompt.")
    assert detection.command is not None
    monkeypatch.setattr(module.storage, "get_setting", lambda key, default=None: True if key == "polishing_enabled" else default)
    monkeypatch.setattr(module.storage, "get_all_api_keys", lambda: {"gemini": "synthetic"})
    from voice_flow import command_rewrites
    monkeypatch.setattr(command_rewrites, "try_local_command_rewrite", lambda *args, **kwargs: None)
    engine = module.TextPolisher()
    calls = []
    def pool(*args, **kwargs):
        calls.append(kwargs)
        if verification and not kwargs.get("verification"):
            engine._last_attempt_status = "ok"
            return "Investigate the violet indicator."
        engine._last_attempt_status = "http_429"
        return None
    monkeypatch.setattr(engine, "_polish_with_api_pool", pool)
    base = SimpleNamespace(category="other", style_id="other_formal", instruction="Use clear prose.")
    effective = resolve_effective_style(base, detection.command)
    session = SimpleNamespace(cleanup_level="cleanup_light", style_id="other_formal", cursor_context=None,
                              polish_model_ref="gemini/exact-selected", polish_speed_mode="quality")
    outcomes = []
    result = finalizer(engine)._finalize_text(detection.content, session, effective=effective,
                                             command=detection.command, outcome_callback=outcomes.append)
    assert result == source
    assert outcomes == ["rate_limited"]
    assert len(calls) == (2 if verification else 1)
    helpers = main_helpers()
    metadata = helpers["_processing_metadata"](polish_outcome=outcomes[0], polish_elapsed=.54,
        resolved_style=base, effective_style=effective, command=detection.command, polishing_enabled=True)
    assert metadata["polish"]["outcome"] == "rate_limited"
    assert metadata["polish"]["display"] == "AI rate/quota limit — your text was kept"
    assert metadata["style"]["applied"] is False
    assert metadata["command"]["status"] == "not_applied"


def test_rate_limit_restores_full_command_fallback_without_claiming_success():
    helpers = main_helpers()
    assert "rate_limited" in helpers["_COMMAND_NOT_PERFORMED"]
    # Execute the actual delivery branch, keeping the command words rather
    # than silently pasting only its extracted content after a failed rewrite.
    branch = next(node for node in ast.walk(TREE) if isinstance(node, ast.If)
                  and isinstance(node.test, ast.BoolOp)
                  and any(isinstance(child, ast.Name) and child.id == "command_fallback_source" for child in ast.walk(node.test)))
    full_source = "make this a prompt to investigate the violet indicator"
    ns = dict(helpers, command=SimpleNamespace(label=lambda: "Prompt"), command_fallback_source=full_source,
              effective=SimpleNamespace(requires_ai=True), polish_outcome={"value":"rate_limited"},
              self=SimpleNamespace(_command_fallback_text=lambda source, *args, **kwargs: source),
              session=SimpleNamespace(), press_enter_enabled=False, polish_deadline=None, dictionary_trace=[],
              log=logging.getLogger(__name__), polished_text="To investigate the violet indicator")
    exec(compile(ast.fix_missing_locations(ast.Module(body=[branch], type_ignores=[])), str(MAIN_PATH), "exec"), ns)
    assert ns["polished_text"] == full_source
    assert ns["polish_outcome"]["value"] == "rate_limited"


def test_verifier_bridge_exception_never_retries_legacy_provider(monkeypatch):
    from voice_flow import voice_polish_bridge
    monkeypatch.setattr(module.storage, "get_all_provider_connections", lambda: {})
    monkeypatch.setattr(voice_polish_bridge, "can_execute_model", lambda model: True)
    engine = module.TextPolisher()
    def bridge(*args, **kwargs):
        raise RuntimeError("synthetic adapter failure")
    monkeypatch.setattr(engine, "_run_bridge_with_timeout", bridge)
    monkeypatch.setattr(engine, "_try_provider_call", lambda *args, **kwargs: pytest.fail("verification retried"))
    assert engine._polish_with_api_pool("{}", {}, model_ref="gemini/exact-selected",
        system_prompt=module._COMMAND_VERIFICATION_SYSTEM_PROMPT, verification=True) is None

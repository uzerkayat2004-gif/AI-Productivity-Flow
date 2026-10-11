"""Real finalization must execute semantic transformations, not add wrappers."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def _finalize(monkeypatch, phrase, source, rewritten, enabled=True, model_ref="local/lfm2.5-350m-qad-q4_0"):
    from voice_flow import main, polisher as module
    from voice_flow.effective_style import resolve_effective_style
    from voice_flow.voice_commands import detect_voice_command
    detection = detect_voice_command(f"Hey Voice Flow, {phrase}. {source}")
    from voice_flow.style_engine import STYLE_INSTRUCTIONS
    base = SimpleNamespace(category="other", style_id="other_formal", instruction=STYLE_INSTRUCTIONS["other_formal"])
    effective = resolve_effective_style(base, detection.command)
    session = SimpleNamespace(cleanup_level="cleanup_light", style_id="other_formal", cursor_context=None,
                              polish_model_ref=model_ref, polish_speed_mode="balanced")
    settings = Mock()
    settings.get_setting.side_effect = lambda key, default=None: enabled if key == "polishing_enabled" else default
    settings.get_all_api_keys.return_value = {}
    monkeypatch.setattr(module, "storage", settings)
    monkeypatch.setattr(main, "_polishing_enabled", lambda: enabled)
    engine = module.TextPolisher()
    provider = Mock(return_value=rewritten)
    monkeypatch.setattr(engine, "_polish_with_api_pool", provider)
    monkeypatch.setattr(main, "polisher", engine)
    monkeypatch.setattr("voice_flow.lfm_engine.is_lfm_downloaded", lambda: False)
    monkeypatch.setattr(module, "_apply_dictionary_with_trace", lambda text, trace=None: text)
    monkeypatch.setattr(main.dictionary_engine, "restore_dictionary_spelling", lambda text: text)
    outcomes = []
    result = object.__new__(main.VoiceFlowApp)._finalize_text(detection.content, session, effective=effective,
        command=detection.command, outcome_callback=outcomes.append)
    print(f"Observed {phrase}: {result!r}; outcomes={outcomes}; provider_calls={provider.call_count}")
    return result, outcomes, provider


@pytest.mark.parametrize("phrase,source,rewritten", [
    ("make this as a prompt", "I need the login fixed. Do not change HTTPClient. Keep 2 retries.",
     "Task: Fix the login.\nRequirements:\n- Do not change HTTPClient.\n- Keep 2 retries."),
    ("make this an email", "Hi Alex I need the budget Friday please send it thanks Morgan.",
     "Hi Alex,\n\nPlease send the budget Friday. I need it Friday.\n\nThanks,\nMorgan."),
])
def test_finalize_semantic_command_uses_selected_provider(monkeypatch, phrase, source, rewritten):
    result, outcomes, provider = _finalize(monkeypatch, phrase, source, rewritten, model_ref="test/remote-model")
    assert provider.call_count == 1
    assert provider.call_args.kwargs["model_ref"] == "test/remote-model"
    assert outcomes == ["ai_accepted"]
    assert result == rewritten


def test_prompt_identity_wrapper_is_not_a_completed_transformation():
    from voice_flow.polisher import _fulfills_command
    source = "I need the login fixed. Do not change HTTPClient. Keep 2 retries."
    assert not _fulfills_command(source, "Task: " + source, task="prompt", overrides={}, command_format="prompt")


def test_finalize_rejects_provider_prompt_identity_wrapper(monkeypatch):
    source = "I need the login fixed. Do not change HTTPClient. Keep 2 retries."
    result, outcomes, provider = _finalize(monkeypatch, "make this as a prompt", source, "Task: " + source)
    assert provider.call_count == 1
    assert outcomes == ["command_unfulfilled"]
    assert not result.startswith("Task:")
    assert "HTTPClient" in result and "2 retries" in result and "Do not" in result


def test_finalize_disabled_semantic_command_never_calls_provider(monkeypatch):
    source = "I need the login fixed. Do not change HTTPClient. Keep 2 retries."
    result, outcomes, provider = _finalize(monkeypatch, "make this as a prompt", source, "Task: Fix login.", enabled=False)
    provider.assert_not_called()
    assert outcomes == ["disabled"]
    assert result == source


@pytest.mark.parametrize("phrase,source,candidate", [
    ("make this as a prompt", "Create a login page um you know with HTTPClient and all that stuff. Keep 2 retries.",
     "Task: Create a login page um you know with HTTPClient and all that stuff. Keep 2 retries."),
    ("make this an email", "Hi Alex I need the budget Friday um you know please send it thanks Morgan.",
     "Hi Alex,\n\nI need the budget Friday um you know please send it\n\nThanks,\nMorgan."),
])
def test_finalize_rejects_layout_only_rough_provider_candidate(monkeypatch, phrase, source, candidate):
    result, outcomes, provider = _finalize(monkeypatch, phrase, source, candidate)
    assert provider.call_count == 1
    assert outcomes != ["ai_accepted"]
    assert "HTTPClient" in result if "HTTPClient" in source else "Alex" in result


@pytest.mark.parametrize("task,fmt,source,candidate", [
    ("prompt", "prompt", "Create a login page. Keep 2 retries.", "Task: Create a login page.\nRequirements: Keep 2 retries."),
    ("rewrite", "email", "Hi Alex please send the budget Friday thanks Morgan.",
     "Hi Alex,\n\nPlease send the budget Friday.\n\nThanks,\nMorgan."),
])
def test_already_usable_wording_can_receive_structure(task, fmt, source, candidate):
    from voice_flow.polisher import _fulfills_command
    assert _fulfills_command(source, candidate, task=task, overrides={}, command_format=fmt)


def test_cloud_and_local_policies_request_semantics_without_invented_email_scaffolding():
    from voice_flow.polisher import _command_system_prompt
    from voice_flow.lfm_engine import _local_system_prompt
    for policy in (_command_system_prompt("rewrite", False, "email"), _local_system_prompt("Format as an email.")):
        assert "rough" in policy and "layout alone" in policy.lower()
        assert '"Hello,' not in policy and 'Regards,' not in policy
    for policy in (_command_system_prompt("prompt", False, "prompt"), _local_system_prompt("well-structured prompt")):
        assert "actionable" in policy and "heading" in policy

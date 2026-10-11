"""Actual finalization regressions for finite local edits and provider fallback."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


CASES = [
    ("make this a prompt", "um i want like a Python tool for CSV files and it should check empty IDs then report invalid rows but do not change the input file please",
     "Create a Python tool for CSV files. Check empty IDs then report invalid rows. Do not change the input file."),
    ("make this a prompt", "Create a status page um and it need to use HTTPClient with 2 retries but do not edit `parseJSON` and keep the last option off",
     "Create a status page. Use HTTPClient with 2 retries. Do not edit `parseJSON`. Keep the last option off."),
    ("make this a formal email", "Hi Alex we was reviewing 12 orange folders and cannot remove 3 purple labels please send the updated report by Friday thanks Morgan",
     "Hi Alex,\n\nWe were reviewing 12 orange folders and cannot remove 3 purple labels. Please send the updated report by Friday.\n\nThanks,\nMorgan."),
    ("make this a casual email", "Hi Nia I has the HTTPClient report ready with 4 errors and do not change `parseJSON` please review it Monday thanks Jules",
     "Hi Nia,\n\nI have the HTTPClient report ready with 4 errors and do not change `parseJSON`. Please review it Monday.\n\nThanks,\nJules."),
]


def finalize(monkeypatch, phrase, source, *, enabled=True, candidate=None, custom=False, dictionary_rule=None,
             deadline=None, provider_timeout=False, style_id="other_formal", stale_attempt=False,
             model_ref="local/lfm2.5-350m-qad-q4_0", disable_at_dispatch=False):
    from voice_flow import main, polisher as module
    from voice_flow.effective_style import resolve_effective_style
    from voice_flow.style_engine import STYLE_INSTRUCTIONS
    from voice_flow.voice_commands import detect_voice_command
    detection = detect_voice_command(f"Hey Voice Flow, {phrase}. {source}")
    assert detection.command is not None
    base = SimpleNamespace(category="other", style_id=style_id,
        instruction=STYLE_INSTRUCTIONS[style_id] + (" Always use pirate language." if custom else ""))
    effective = resolve_effective_style(base, detection.command)
    session = SimpleNamespace(cleanup_level="cleanup_light", style_id="other_formal", cursor_context=None,
        polish_model_ref=model_ref, polish_speed_mode="balanced")
    settings = Mock()
    enabled_state = {"value": enabled}
    def setting(key, default=None):
        if key == "polishing_enabled":
            if disable_at_dispatch:
                enabled_state["value"] = False
            return enabled_state["value"]
        return default
    settings.get_setting.side_effect = setting
    settings.get_all_api_keys.return_value = {}
    monkeypatch.setattr(module, "storage", settings)
    monkeypatch.setattr(main, "_polishing_enabled", lambda: enabled_state["value"])
    engine = module.TextPolisher()
    def attempt(*args, **kwargs):
        if provider_timeout:
            engine._last_attempt_status = "timeout"
            engine._last_lfm_bridge_attempted = True
        return candidate
    provider = Mock(side_effect=attempt)
    engine._last_lfm_bridge_attempted = stale_attempt
    monkeypatch.setattr(engine, "_polish_with_api_pool", provider)
    monkeypatch.setattr(main, "polisher", engine)
    monkeypatch.setattr("voice_flow.lfm_engine.is_lfm_downloaded", lambda: False)
    dictionary = Mock(side_effect=lambda text, trace=None: text.replace(*dictionary_rule) if dictionary_rule else text)
    monkeypatch.setattr(module, "_apply_dictionary_with_trace", dictionary)
    monkeypatch.setattr(main.dictionary_engine, "restore_dictionary_spelling", lambda text: text)
    outcomes = []
    attempts = []
    result = object.__new__(main.VoiceFlowApp)._finalize_text(detection.content, session,
        effective=effective, command=detection.command, outcome_callback=outcomes.append,
        attempt_outcome_callback=attempts.append, deadline=deadline)
    provider.attempt_outcomes = attempts
    return result, outcomes, provider, dictionary


@pytest.mark.parametrize("phrase,source,expected", CASES)
@pytest.mark.parametrize("candidate", [None, "This is an unrelated response with invented facts."])
def test_real_finalize_delivers_safe_local_rewrite_after_selected_attempt(monkeypatch, phrase, source, expected, candidate):
    result, outcomes, provider, dictionary = finalize(monkeypatch, phrase, source, candidate=candidate, model_ref="test/remote-model")
    assert provider.call_count == 1
    assert provider.call_args.kwargs["model_ref"] == "test/remote-model"
    dictionary.assert_called_once()
    assert outcomes == ["local_rewrite"]
    assert result == expected
    assert provider.attempt_outcomes == ["provider_failure" if candidate is None else "command_unfulfilled"]


@pytest.mark.parametrize("phrase,source,expected", CASES)
def test_selected_small_lfm_recognized_rewrite_avoids_generation(monkeypatch, phrase, source, expected):
    result, outcomes, provider, dictionary = finalize(monkeypatch, phrase, source)
    provider.assert_not_called()
    dictionary.assert_called_once()
    assert result == expected and outcomes == ["local_rewrite"]
    assert provider.attempt_outcomes == ["local"]


def test_off_toggle_after_preflight_never_transforms(monkeypatch):
    phrase, source, _ = CASES[0]
    result, outcomes, provider, dictionary = finalize(monkeypatch, phrase, source, disable_at_dispatch=True)
    provider.assert_not_called()
    dictionary.assert_called_once()
    assert outcomes == ["disabled"] and not result.startswith("Create")


def test_dictionary_change_that_invalidates_preflight_declines_without_second_pass(monkeypatch):
    phrase, source, _ = CASES[0]
    result, outcomes, provider, dictionary = finalize(monkeypatch, phrase, source,
        dictionary_rule=("Python tool", "Python picture"))
    provider.assert_not_called()
    dictionary.assert_called_once()
    assert outcomes == ["command_unfulfilled"] and "Python picture" in result
    assert not result.startswith("Create")


def test_off_never_rewrites_or_calls_provider(monkeypatch):
    from voice_flow import command_rewrites
    local = Mock(side_effect=AssertionError("OFF entered local rewrite"))
    monkeypatch.setattr(command_rewrites, "try_local_command_rewrite", local)
    phrase, source, _ = CASES[0]
    result, outcomes, provider, dictionary = finalize(monkeypatch, phrase, source, enabled=False)
    provider.assert_not_called()
    dictionary.assert_called_once()
    assert outcomes == ["disabled"] and not result.startswith("Create")
    local.assert_not_called()


@pytest.mark.parametrize("phrase,source,custom", [
    ("make this a prompt and keep my wording", "I want a Python tool that checks CSV files.", False),
    ("make this a short prompt", "I want a Python tool that checks CSV files.", False),
    ("make this a prompt", "I want a Python tool that checks CSV files.", True),
    ("make this a prompt", "I want like Alex to handle the review.", False),
    ("make this a prompt", "I want a holiday like last year.", False),
    ("make this a prompt", "quiero una herramienta para revisar archivos", False),
])
def test_unsupported_local_transforms_decline(monkeypatch, phrase, source, custom):
    _, outcomes, _, _ = finalize(monkeypatch, phrase, source, custom=custom)
    assert outcomes != ["local_rewrite"]


def test_protected_spans_cannot_be_split_or_reauthored(monkeypatch):
    source = 'I want you to check HTTPClient at https://Example.com/CaseSensitive and C:\\Work\\CaseFile.txt with `and it should send()` and "please send the exact text" but do not edit `parseJSON`'
    result, outcomes, _, dictionary = finalize(monkeypatch, "make this a prompt", source)
    assert outcomes == ["local_rewrite"]
    for literal in ("HTTPClient", "https://Example.com/CaseSensitive", r"C:\Work\CaseFile.txt",
                    "`and it should send()`", '"please send the exact text"', "`parseJSON`"):
        assert literal in result
    assert result.startswith("Task: Check HTTPClient") and "Do not edit `parseJSON`" in result
    dictionary.assert_called_once()


def test_email_negative_please_clause_cannot_be_split_into_a_positive_request(monkeypatch):
    result, outcomes, _, _ = finalize(monkeypatch, "make this an email",
        "Hi Alex do not please send the old report thanks Morgan")
    assert outcomes != ["local_rewrite"]
    assert "not" in result


def test_email_question_is_not_split_inside_can_you_please(monkeypatch):
    _, outcomes, _, _ = finalize(monkeypatch, "make this an email",
        "Hi Alex can you please send the old report thanks Morgan")
    assert outcomes != ["local_rewrite"]


def test_second_negative_request_keeps_its_scope(monkeypatch):
    result, outcomes, _, _ = finalize(monkeypatch, "make this an email",
        "Hi Alex I have the report ready please review it Monday and do not please send the old copy thanks Morgan")
    if outcomes == ["local_rewrite"]:
        assert "do not please send" in result.lower()
        assert "do not. Please send" not in result


@pytest.mark.parametrize("prefix", ["if", "unless", "when", "until", "provided", "only if", "because"])
def test_conditional_email_request_is_not_made_unconditional(monkeypatch, prefix):
    _, outcomes, _, _ = finalize(monkeypatch, "make this an email",
        f"Hi Alex {prefix} we have the report ready please send it Monday thanks Morgan")
    assert outcomes != ["local_rewrite"]


def test_conditional_words_inside_protected_quote_do_not_block_edit(monkeypatch):
    result, outcomes, _, _ = finalize(monkeypatch, "make this an email",
        'Hi Alex I have the "if ready do not send" report ready please review it Monday thanks Morgan')
    assert outcomes == ["local_rewrite"]
    assert '"if ready do not send"' in result


def test_expired_deadline_does_not_use_stale_selected_attempt_marker(monkeypatch):
    import time
    phrase, source, _ = CASES[0]
    result, outcomes, provider, _ = finalize(monkeypatch, phrase, source,
        deadline=time.monotonic() - 1, stale_attempt=True)
    provider.assert_not_called()
    assert outcomes == ["timeout"] and not result.startswith("Create")


def test_timeout_after_actual_selected_attempt_can_use_local_rewrite(monkeypatch):
    phrase, source, expected = CASES[0]
    # The raw dictionary alias is outside finite preflight patterns. Once the
    # actual selected attempt times out, its safe dictionary-aware result fits.
    result, outcomes, provider, _ = finalize(monkeypatch, phrase, source.replace("tool", "sample artifact"),
        provider_timeout=True, dictionary_rule=("sample artifact", "tool"))
    provider.assert_called_once()
    assert outcomes == ["local_rewrite"] and result == expected
    assert provider.attempt_outcomes == ["timeout"]


def test_very_casual_register_does_not_claim_local_style_fulfillment(monkeypatch):
    _, outcomes, _, _ = finalize(monkeypatch, "make this a prompt", CASES[0][1], style_id="other_very_casual")
    assert outcomes != ["local_rewrite"]


def test_playful_tone_requires_provider_instead_of_plain_local_rewrite(monkeypatch):
    _, outcomes, _, _ = finalize(monkeypatch, "make this a playful prompt", CASES[0][1])
    assert outcomes != ["local_rewrite"]


@pytest.mark.parametrize("prefix", [
    "we have instructions to never", "we are wondering whether you can", "we have asked you to",
])
def test_embedded_negative_or_modal_email_request_declines(monkeypatch, prefix):
    _, outcomes, _, _ = finalize(monkeypatch, "make this an email",
        f"Hi Alex {prefix} please send the report Monday thanks Morgan")
    assert outcomes != ["local_rewrite"]


def test_local_rewrite_metadata_keeps_provider_failure_without_claiming_ai():
    from voice_flow.main import _processing_metadata, _polish_outcome_label
    from voice_flow.voice_commands import detect_voice_command
    from voice_flow.effective_style import resolve_effective_style
    from voice_flow.style_engine import STYLE_INSTRUCTIONS
    base = SimpleNamespace(category="other", style_id="other_formal", instruction=STYLE_INSTRUCTIONS["other_formal"])
    command = detect_voice_command("Hey Voice Flow, make this a prompt. I want a Python tool.").command
    effective = resolve_effective_style(base, command)
    metadata = _processing_metadata(polish_outcome="local_rewrite", polish_elapsed=0.2,
        resolved_style=base, effective_style=effective, command=command, polishing_enabled=True,
        polish_attempt_outcome="command_unfulfilled")
    assert metadata["polish"]["outcome"] == "local_rewrite"
    assert metadata["polish"]["attempt_outcome"] == "command_unfulfilled"
    assert metadata["style"]["applied"] and metadata["command"]["status"] == "applied"
    assert _polish_outcome_label("local_rewrite") == "Rewritten locally"


def test_dictionary_aware_payload_receives_rules_once_before_local_rewrite(monkeypatch):
    result, outcomes, _, dictionary = finalize(monkeypatch, "make this a prompt",
        "I want a Python tool for sample widget and it should check sample widget for invalid rows without changing the input file",
        dictionary_rule=("sample widget", "SampleWidget"))
    assert outcomes == ["local_rewrite"]
    assert result == "Create a Python tool for SampleWidget. Check SampleWidget for invalid rows without changing the input file."
    dictionary.assert_called_once()

"""Captured provider failures, exercised without models or account storage."""
from unittest.mock import Mock

import pytest

from voice_flow import polisher as module


def run_candidate(monkeypatch, source, candidate, *, task="cleanup", command_format=None):
    storage = Mock()
    storage.get_setting.side_effect = lambda key, default=None: True if key == "polishing_enabled" else default
    storage.get_all_api_keys.return_value = {}
    monkeypatch.setattr(module, "storage", storage)
    monkeypatch.setattr(module, "_apply_dictionary_with_trace", lambda text, trace: text)
    monkeypatch.setattr("voice_flow.lfm_engine.is_lfm_downloaded", lambda: False)
    engine = module.TextPolisher()
    monkeypatch.setattr(engine, "_polish_with_api_pool", Mock(return_value=candidate))
    outcomes = []
    result = engine.polish(source, force_ai=True, model_ref="test/provider", task=task,
                           command_format=command_format, outcome_callback=outcomes.append)
    return result, outcomes


def test_email_sender_substitution_is_rejected(monkeypatch):
    result, outcomes = run_candidate(monkeypatch,
        "Hi Alex please send the revised budget by Friday thanks Morgan.",
        "Hi Alex,\n\nPlease send the revised budget by Friday.\n\nThanks,\nRobin",
        task="rewrite", command_format="email")
    assert outcomes == ["command_unfulfilled"]
    assert "Morgan" in result and "Robin" not in result


def test_actual_assistant_wrapper_and_tail_are_removed(monkeypatch):
    result, outcomes = run_candidate(monkeypatch,
        "can you restart the server after the backup finishes",
        'Sure! Here\'s a revised version:\n\n"Can you restart the server after the backup finishes?"\n\nLet me know if you\'d like any adjustments!')
    assert result == "Can you restart the server after the backup finishes?"
    assert outcomes == ["ai_accepted"]


def test_added_restoration_requirement_is_rejected(monkeypatch):
    source = "i cannot restart the server because the backup is still running"
    result, outcomes = run_candidate(monkeypatch, source, source + " and I need to restore it.")
    assert outcomes == ["fidelity_reject"]
    assert "restore" not in result


@pytest.mark.parametrize("addition", ["and it may take time to restore", "and no action can be taken", "after lunch"])
def test_complete_cleanup_does_not_append_new_facts(monkeypatch, addition):
    source = "I cannot restart the server because the backup is still running"
    result, outcomes = run_candidate(monkeypatch, source, source + " " + addition + ".")
    assert outcomes == ["fidelity_reject"]
    assert result == source + "."


def test_mid_sentence_speaker_is_not_changed_to_the_reader(monkeypatch):
    source = "Yesterday I went to the office and we were ready for the meeting."
    candidate = "Yesterday you went to the office and you were ready for the meeting."
    result, outcomes = run_candidate(monkeypatch, source, candidate)
    assert outcomes == ["fidelity_reject"]
    assert result == source


def test_speaker_pronouns_inside_quotes_are_not_used_as_perspective(monkeypatch):
    source = 'Please send the exact quote "I need this" to Alex today.'
    result, outcomes = run_candidate(monkeypatch, source, source)
    assert result == source and outcomes == ["ai_accepted"]


@pytest.mark.parametrize("literal, altered", [
    ("HTTPClient", "httpclient"),
    ("https://Example.com/CaseSensitive", "https://example.com/casesensitive"),
    (r"C:\Work\CaseFile.txt", r"C:\Work\casefile.txt"),
    ("`parseJSON`", "`parseJson`"),
])
def test_provider_cannot_change_protected_literal_spelling(monkeypatch, literal, altered):
    source = f"Please check {literal} for the review today."
    candidate = f"Please check {altered} for the review today."
    result, outcomes = run_candidate(monkeypatch, source, candidate)
    assert outcomes == ["fidelity_reject"] and literal in result


@pytest.mark.parametrize("sender", ["Morgan", "morgan"])
def test_faithful_email_and_name_case_are_accepted(monkeypatch, sender):
    candidate = f"Hi Alex,\n\nPlease send the revised budget by Friday.\n\nThanks,\n{sender}"
    result, outcomes = run_candidate(monkeypatch,
        "Hi Alex please send the revised budget by Friday thanks Morgan.", candidate,
        task="rewrite", command_format="email")
    assert result == candidate
    assert outcomes == ["ai_accepted"]


@pytest.mark.parametrize("source", [
    "I cannot restart the server because the backup is still running.",
    "I need to restore it after the backup finishes.",
    "Here's a revised version: send the budget by Friday.",
    "Let me know if you'd like any adjustments!",
    'Please say "Let me know if you\'d like any adjustments!" exactly.',
])
def test_dictated_perspective_requirement_and_assistant_phrases_survive(monkeypatch, source):
    result, outcomes = run_candidate(monkeypatch, source, source)
    assert result == source
    assert outcomes == ["ai_accepted"]

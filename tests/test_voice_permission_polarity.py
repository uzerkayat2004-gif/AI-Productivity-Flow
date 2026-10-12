"""Permission polarity must survive the real polisher's provider gate."""
from unittest.mock import patch

import pytest

from voice_flow.polisher import TextPolisher, _candidate_preserves_content


def run_polish(source, candidate, task="cleanup"):
    engine = TextPolisher()
    outcomes = []
    with (
        patch("voice_flow.polisher.storage.get_setting", side_effect=lambda key, default=None: True if key == "polishing_enabled" else default),
        patch("voice_flow.polisher.storage.get_all_api_keys", return_value={}),
        patch.object(engine, "_polish_with_api_pool", return_value=candidate),
        patch("voice_flow.lfm_engine.is_lfm_downloaded", return_value=False),
        patch("voice_flow.polisher._apply_dictionary_with_trace", side_effect=lambda text, trace: text),
    ):
        result = engine.polish(source, force_ai=True, task=task, outcome_callback=outcomes.append)
    return result, outcomes


@pytest.mark.parametrize("negative", ["cannot", "can't", "can not"])
@pytest.mark.parametrize("prefix,suffix", [("", ""), ("The changes are ready and the checks passed. ", " Please keep the existing settings and confirm once it is running.")])
@pytest.mark.parametrize("reverse", [False, True])
def test_permission_flip_is_rejected(negative, prefix, suffix, reverse):
    positive = prefix + "Can you restart the app?" + suffix
    negated = prefix + f"I {negative} restart the app." + suffix
    source, candidate = (negated, positive) if reverse else (positive, negated)
    assert not _candidate_preserves_content(source, candidate, task="rewrite")
    result, outcomes = run_polish(source, candidate)
    assert outcomes == ["fidelity_reject"]
    assert result != candidate


def test_full_provider_permission_flip_cannot_hide_behind_other_negation():
    source = "I cannot open settings, but can you restart the app now and confirm that the existing changes are ready?"
    candidate = "I cannot open settings, but you cannot restart the app now and confirm that the existing changes are ready."
    result, outcomes = run_polish(source, candidate)
    assert outcomes == ["fidelity_reject"]
    assert result != candidate


@pytest.mark.parametrize("prefix", ["", "I cannot open settings, but "])
@pytest.mark.parametrize("reverse", [False, True])
def test_polite_permission_flip_is_rejected(prefix, reverse):
    positive = prefix + "Can you please restart the app now?"
    negative = prefix + "I cannot restart the app now."
    source, candidate = (negative, positive) if reverse else (positive, negative)
    assert not _candidate_preserves_content(source, candidate, task="rewrite")
    result, outcomes = run_polish(source, candidate)
    assert outcomes == ["fidelity_reject"]
    assert result != candidate


def test_polite_permission_and_unrelated_negative_allow_faithful_style():
    source = "I cannot open settings, but can you please restart the app now?"
    candidate = "I cannot open settings, but you can restart the app now."
    assert _candidate_preserves_content(source, candidate, task="rewrite")
    _, outcomes = run_polish(source, candidate)
    assert outcomes == ["ai_accepted"]


@pytest.mark.parametrize("literal", ['"I cannot restart the app"', '`I cannot restart the app`', "https://example.test/I-cannot-restart-the-app"])
def test_literal_negation_does_not_license_permission_flip(literal):
    source = f"The example is {literal}. Can you restart the app now?"
    candidate = f"The example is {literal}. You cannot restart the app now."
    assert not _candidate_preserves_content(source, candidate, task="rewrite")


def test_unrelated_clause_negation_does_not_license_permission_flip():
    source = "I cannot open the settings, but can you restart the app now?"
    candidate = "I can open the settings, but you cannot restart the app now."
    assert not _candidate_preserves_content(source, candidate, task="rewrite")


@pytest.mark.parametrize("negative", ["cannot", "can't", "can not"])
def test_authentic_negative_and_equivalent_spelling_are_preserved(negative):
    source = "I cannot restart the app today."
    candidate = f"I {negative} restart the app today."
    assert _candidate_preserves_content(source, candidate)
    result, outcomes = run_polish(source, candidate)
    assert outcomes == ["ai_accepted"]
    assert "Can you" not in result


@pytest.mark.parametrize("task", ["cleanup", "rewrite"])
def test_authentic_cannot_never_becomes_positive_can(task):
    source = "I cannot restart the app."
    candidate = "I can restart the app."
    assert not _candidate_preserves_content(source, candidate, task=task)
    result, outcomes = run_polish(source, candidate, task=task)
    assert outcomes == ["fidelity_reject" if task == "cleanup" else "command_unfulfilled"]
    assert result == source


@pytest.mark.parametrize("literal", ['"I cannot restart the app"', '`I cannot restart the app`', "https://example.test/I-cannot-restart-the-app"])
def test_literal_mentions_and_unrelated_negation_allow_faithful_style(literal):
    source = f"The example is {literal}. I cannot open settings, but can you restart the app now?"
    candidate = f"The example is {literal}. I cannot open settings, but you can restart the app now."
    assert _candidate_preserves_content(source, candidate, task="rewrite")

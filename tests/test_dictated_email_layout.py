"""Email layout after failed AI uses only explicit dictated structure."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from voice_flow.text_processing import format_dictated_email


def test_missing_salutation_comma_and_dictated_signoff_are_formatted():
    source = "Hi Alex please send the revised budget by Friday thanks Morgan."
    assert format_dictated_email(source) == "Hi Alex,\n\nPlease send the revised budget by Friday\n\nThanks,\nMorgan."


@pytest.mark.parametrize("source", [
    "Please ask Alex to send the revised budget by Friday.",
    "Hi there is a problem with the report.",
    "Hello everyone was ready for the review.",
    "Alex please send the report.",
])
def test_uncertain_email_boundaries_are_not_guessed(source):
    assert format_dictated_email(source) is None


def test_actual_finalize_uses_local_email_layout_only_with_polishing_on(monkeypatch):
    from voice_flow import main
    from voice_flow.effective_style import resolve_effective_style
    from voice_flow.voice_commands import detect_voice_command
    detection = detect_voice_command(
        "Hey Voice Flow, make this a formal email. Hi Alex please send the revised budget by Friday thanks Morgan.")
    base = SimpleNamespace(category="other", style_id="other_formal", instruction="Standard punctuation.")
    effective = resolve_effective_style(base, detection.command)
    session = SimpleNamespace(cleanup_level="cleanup_light", style_id="other_formal", cursor_context=None,
                              polish_model_ref="local/lfm2.5-350m-qad-q4_0", polish_speed_mode="balanced")
    app = object.__new__(main.VoiceFlowApp)
    def failed_provider(text, **kwargs):
        kwargs["outcome_callback"]("command_unfulfilled")
        return text
    monkeypatch.setattr(main.polisher, "polish", failed_provider)
    monkeypatch.setattr(main.dictionary_engine, "restore_dictionary_spelling", lambda text: text)
    outcomes = []
    result = app._finalize_text(detection.content, session, effective=effective, command=detection.command,
                                outcome_callback=outcomes.append)
    assert outcomes == ["local_format"]
    assert "Hi Alex," in result and "\n\n" in result and "Morgan" in result
    assert "subject:" not in result.lower() and "regards" not in result.lower()
    def disabled_provider(text, **kwargs):
        kwargs["outcome_callback"]("disabled")
        return text
    monkeypatch.setattr(main.polisher, "polish", disabled_provider)
    outcomes.clear()
    result = app._finalize_text(detection.content, session, effective=effective, command=detection.command,
                                outcome_callback=outcomes.append)
    assert outcomes == ["disabled"]
    assert result == detection.content


def test_final_style_pass_keeps_existing_signoff_paragraph():
    from voice_flow.text_processing import smart_format
    text = "Hi Alex,\n\nPlease send the budget Friday\n\nThanks,\nMorgan."
    assert smart_format(text, "email_formal") == text

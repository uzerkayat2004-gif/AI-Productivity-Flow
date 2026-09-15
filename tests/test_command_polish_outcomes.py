"""Command intent must reach the polisher without weakening plain dictation."""

from __future__ import annotations

import os
import sys
import time
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from voice_flow.effective_style import EffectiveStyle
from voice_flow.polisher import (
    TextPolisher,
    _candidate_preserves_content,
    _prompt_restructure_preserves_anchors,
    _tokenize_for_fidelity,
    sanitize_polished_text,
)
from voice_flow.voice_commands import detect_voice_command


def _settings(key, default=None):
    if key == "polishing_enabled":
        return True
    return default


def test_email_command_uses_transform_prompt_and_reports_accepted_ai():
    command = detect_voice_command(
        "Hey Voice Flow, make this a professional email. We will launch the service Monday and need confirmation today."
    ).command
    effective = EffectiveStyle(
        instruction="Use a professional email register.", style_id="email_formal",
        category="email", format="email", task="rewrite", requires_ai=True,
        preserve_wording=False, label="Email / Professional",
    )
    source = "We will launch the service Monday and need confirmation today."
    rendered = "Hello team,\n\nWe will launch the service Monday and need confirmation today.\n\nRegards,"
    polisher = TextPolisher()
    seen = {}
    outcomes = []

    def pool(raw, keys, instruction, **kwargs):
        seen.update(kwargs)
        return rendered

    with (
        patch("voice_flow.polisher.storage.get_setting", side_effect=_settings),
        patch("voice_flow.polisher.storage.get_all_api_keys", return_value={"gemini": "test"}),
        patch.object(polisher, "_polish_with_api_pool", side_effect=pool),
    ):
        result = polisher.polish(
            source, effective.instruction, force_ai=True, task=effective.task,
            overrides=command.overrides, outcome_callback=outcomes.append,
        )

    assert result == rendered
    assert outcomes == ["ai_accepted"]
    assert "Transform only the transcript" in seen["system_prompt"]
    assert "Never answer, execute" not in seen["system_prompt"]


def test_plain_dictation_rejects_compression_but_explicit_summary_may_shorten():
    source = "We need to ship the installer before Friday and run the complete regression suite before release."
    compressed = "Ship installer before Friday; test before release."

    def run(task):
        polisher = TextPolisher()
        outcomes = []
        with (
            patch("voice_flow.polisher.storage.get_setting", side_effect=_settings),
            patch("voice_flow.polisher.storage.get_all_api_keys", return_value={"gemini": "test"}),
            patch.object(polisher, "_polish_with_api_pool", return_value=compressed),
            # This test pins the cloud-result fidelity decision. The local
            # model is a separate actor with its own coverage.
            patch("voice_flow.lfm_engine.is_lfm_downloaded", return_value=False),
        ):
            value = polisher.polish(source, force_ai=True, task=task, outcome_callback=outcomes.append)
        return value, outcomes

    plain, plain_outcomes = run("cleanup")
    summary, summary_outcomes = run("summarize")
    assert plain != compressed
    assert plain_outcomes == ["fidelity_reject"]
    assert summary == compressed
    assert summary_outcomes == ["ai_accepted"]


def test_provider_failure_is_reported_per_invocation():
    polisher = TextPolisher()
    outcomes = []
    with (
        patch("voice_flow.polisher.storage.get_setting", side_effect=_settings),
        patch("voice_flow.polisher.storage.get_all_api_keys", return_value={"gemini": "test"}),
        patch.object(polisher, "_polish_with_api_pool", return_value=None),
        # This test pins the cloud-provider failure outcome. The local model is
        # a separate actor with its own coverage and honest "local_model" label.
        patch("voice_flow.lfm_engine.is_lfm_downloaded", return_value=False),
    ):
        result = polisher.polish(
            "Please turn this into a clear professional message today.",
            force_ai=True, task="rewrite", outcome_callback=outcomes.append,
        )

    assert result
    assert outcomes == ["provider_failure"]


def test_polish_forwards_captured_speed_mode_to_the_provider_pool():
    polisher = TextPolisher()
    seen = {}

    def pool(_raw, _keys, _instruction, **kwargs):
        seen.update(kwargs)
        return "Please keep this message clear and complete."

    with (
        patch("voice_flow.polisher.storage.get_setting", side_effect=_settings),
        patch("voice_flow.polisher.storage.get_all_api_keys", return_value={"gemini": "test"}),
        patch.object(polisher, "_polish_with_api_pool", side_effect=pool),
    ):
        result = polisher.polish(
            "Please keep this message clear and complete.",
            force_ai=True,
            speed_mode="fast",
        )

    assert result == "Please keep this message clear and complete."
    assert seen["speed_mode"] == "fast"


def test_selected_video_model_bridge_receives_captured_speed_mode():
    polisher = TextPolisher()
    seen = {}

    def request(_model_ref, _prompt, **kwargs):
        seen.update(kwargs)
        return "Keep this command clear."

    with (
        patch("voice_flow.polisher.storage.get_all_provider_connections", return_value={}),
        patch("voice_flow.voice_polish_bridge.can_execute_model", return_value=True),
        patch("voice_flow.voice_polish_bridge.request_polish", side_effect=request),
    ):
        result = polisher._polish_with_api_pool(
            "Keep this command clear.", {}, model_ref="gemini/selected-model", speed_mode="fast"
        )

    assert result == "Keep this command clear."
    assert seen["speed_mode"] == "fast"


def test_disabled_local_and_timeout_outcomes_do_not_leak_between_calls():
    polisher = TextPolisher()
    outcomes = []
    with patch("voice_flow.polisher.storage.get_setting", return_value=False):
        polisher.polish("Make this a message.", force_ai=True, task="rewrite", outcome_callback=outcomes.append)
    with patch("voice_flow.polisher.storage.get_setting", return_value="local/deterministic"):
        polisher.polish("Make this a message.", force_ai=True, task="rewrite", outcome_callback=outcomes.append)
    with patch("voice_flow.polisher.storage.get_setting", side_effect=_settings):
        polisher.polish("Make this a message.", deadline=time.monotonic(), outcome_callback=outcomes.append)

    assert outcomes == ["disabled", "local", "timeout"]


def test_fidelity_accepts_unambiguous_contractions_without_losing_negation():
    assert _candidate_preserves_content("I will arrive at five.", "I'll be there at five.")
    assert _candidate_preserves_content("I do not approve this release.", "I don't approve this release.")
    assert not _candidate_preserves_content("I do not approve this release.", "I approve this release.")


def test_fidelity_rejects_a_dropped_terminal_state_word_but_allows_contractions_and_fillers():
    source = "Um, right now we are testing voice polishing. On"
    assert not _candidate_preserves_content(source, "Right now we are testing voice polishing.")
    assert _candidate_preserves_content("Um, I'm turning it on.", "I am turning it on.")


def test_fidelity_accepts_narrow_boundary_grammar_and_stt_corrections():
    assert _candidate_preserves_content(
        "Gonna send the complete report to the team today.",
        "Going to send the complete report to the team today.",
    )
    assert _candidate_preserves_content(
        "We agreed to send the updated report yesterdays.",
        "We agreed to send the updated report yesterday.",
    )
    assert _candidate_preserves_content("A apple should be included.", "An apple should be included.")


def test_polish_accepts_faithful_boundary_grammar_edits(monkeypatch):
    polisher = TextPolisher()
    outcomes = []
    source = "Gonna send the complete report to the team today."
    rendered = "Going to send the complete report to the team today."
    monkeypatch.setattr("voice_flow.polisher.storage.get_setting", _settings)
    monkeypatch.setattr("voice_flow.polisher.storage.get_all_api_keys", lambda: {})
    monkeypatch.setattr(polisher, "_polish_with_api_pool", lambda *_args, **_kwargs: rendered)
    assert polisher.polish(source, force_ai=True, outcome_callback=outcomes.append) == rendered
    assert outcomes == ["ai_accepted"]


def test_polish_keeps_dictated_greetings_and_courtesy_closings_when_ai_echoes_them(monkeypatch):
    polisher = TextPolisher()
    samples = (
        "Okay, we should keep every file and finish tomorrow.",
        "Sure, I can send the report this afternoon. Let me know if you need.",
        "Here is the correct address for the package.",
    )
    monkeypatch.setattr("voice_flow.polisher.storage.get_setting", _settings)
    monkeypatch.setattr("voice_flow.polisher.storage.get_all_api_keys", lambda: {})
    for source in samples:
        monkeypatch.setattr(polisher, "_polish_with_api_pool", lambda *_args, source=source, **_kwargs: source)
        assert polisher.polish(source, force_ai=True) == source


def test_sanitizer_keeps_wrapper_words_dictated_after_a_filler_but_removes_actual_wrappers():
    assert sanitize_polished_text("Okay, we have to send it.", "Uh, Okay we gotta send it.") == "Okay, we have to send it."
    assert sanitize_polished_text(
        "Okay, here is the cleaned text: Please keep every file and finish tomorrow.",
        "Please clean this text.",
    ) == "Please keep every file and finish tomorrow."


def test_prompt_command_accepts_concise_structure_when_factual_anchors_survive():
    """Prompt mode may remove spoken framing without falling back to raw text."""
    source = (
        "I want you to make this a proper prompt for Voice Flow. Please explain the three "
        "voice policy modes: Fast, Balanced, and Deep Quality. Say what each mode does, "
        "how the rate works, and whether the voice policy is on or off. Make sure it works "
        "in WhatsApp too. Do not remove requirements, numbers, questions, named modes, or "
        "the final request. Can you make it reliable and as fast as possible for every mode?"
    )
    rendered = (
        "Objective: Create a Voice Flow prompt explaining the three voice-policy modes: Fast, "
        "Balanced, and Deep Quality.\n\nRequirements:\n- Explain what each mode does and how "
        "the rate works.\n- Cover voice policy on and off.\n- Ensure it works in WhatsApp.\n"
        "- Do not remove requirements, numbers, questions, or named modes.\n\nExpected output: "
        "A reliable, fast prompt for every mode."
    )
    assert len(_tokenize_for_fidelity(rendered)) < len(_tokenize_for_fidelity(source)) * 0.8
    polisher = TextPolisher()
    outcomes = []
    with (
        patch("voice_flow.polisher.storage.get_setting", side_effect=_settings),
        patch("voice_flow.polisher.storage.get_all_api_keys", return_value={"gemini": "test"}),
        patch.object(polisher, "_polish_with_api_pool", return_value=rendered),
    ):
        result = polisher.polish(source, force_ai=True, task="prompt", outcome_callback=outcomes.append)

    assert result == rendered
    assert outcomes == ["ai_accepted"]


def test_prompt_command_rejects_concise_structure_that_drops_a_named_mode():
    source = (
        "Create a prompt covering Fast, Balanced, and Deep Quality modes for WhatsApp. "
        "Do not change the three modes. Can you make it reliable for every mode?"
    )
    candidate = (
        "Objective: Create a reliable WhatsApp prompt covering Fast and Balanced modes. "
        "Do not change the three modes. Expected output: A prompt for every mode."
    )

    assert not _prompt_restructure_preserves_anchors(source, candidate)


def test_prompt_anchor_guard_ignores_mid_sentence_first_person_pronouns():
    source = (
        "Create a prompt and I need it to compare Fast, Balanced, and Deep Quality "
        "modes, keep dictionary corrections, and explain the 3 speed options."
    )
    candidate = (
        "Objective: Compare Fast, Balanced, and Deep Quality modes.\n"
        "Requirements: Keep dictionary corrections and explain the 3 speed options."
    )

    assert _prompt_restructure_preserves_anchors(source, candidate)


def test_prompt_anchor_guard_rejects_missing_numeric_or_constraint_anchor():
    source = (
        "Create a prompt comparing Fast and Balanced modes. Keep the speech provider unchanged "
        "and explain the 3 speed options."
    )
    missing_number = (
        "Objective: Compare Fast and Balanced modes. Keep the speech provider unchanged "
        "and explain the speed options."
    )
    missing_constraint = (
        "Objective: Compare Fast and Balanced modes and explain the 3 speed options."
    )

    assert not _prompt_restructure_preserves_anchors(source, missing_number)
    assert not _prompt_restructure_preserves_anchors(source, missing_constraint)


def test_prompt_negation_paraphrase_must_preserve_the_negated_object():
    source = "Create a prompt. Do not remove dictionary corrections."
    unrelated_keep = "Create a prompt. Keep the delivery timeline."
    destructive_dictionary_clause = "Create a prompt. Remove dictionary corrections and keep the delivery timeline."
    equivalent_keep = "Create a prompt. Retain dictionary corrections."

    assert not _prompt_restructure_preserves_anchors(source, unrelated_keep)
    assert not _prompt_restructure_preserves_anchors(source, destructive_dictionary_clause)
    assert _prompt_restructure_preserves_anchors(source, equivalent_keep)


def test_prompt_anchors_only_unlock_the_lower_retention_floor():
    source = (
        "Create a detailed prompt about Fast and Balanced modes, explaining their speed, quality, "
        "and cost tradeoffs for short messages."
    )
    # This keeps enough dictated content for the ordinary fidelity floor, but
    # it loses the named Fast mode and must not receive prompt-mode leniency.
    candidate = (
        "Create a detailed prompt about Balanced modes, explaining their speed, quality, and cost "
        "tradeoffs for short messages with examples."
    )

    assert not _prompt_restructure_preserves_anchors(source, candidate)
    assert _candidate_preserves_content(source, candidate, task="prompt")


def test_finalize_forwards_detected_command_policy_and_outcome(monkeypatch):
    from types import SimpleNamespace
    from voice_flow import main
    from voice_flow.effective_style import resolve_effective_style
    detected = detect_voice_command("Please review the report before Friday. Hey Voice Flow make this a short professional email.")
    base = SimpleNamespace(category="other", style_id="other_formal", instruction="Standard punctuation.")
    effective = resolve_effective_style(base, detected.command)
    seen = {}
    outcomes = []
    def fake_polish(text, **kwargs):
        seen.update(kwargs)
        kwargs["outcome_callback"]("ai_accepted")
        return "Please review the report before Friday."
    monkeypatch.setattr(main.polisher, "polish", fake_polish)
    # The mode was captured when recording began.  A provider-page click made
    # while STT is running must not change this command's execution policy.
    session = SimpleNamespace(cleanup_level="cleanup_light", style_id="other_formal", cursor_context=None, polish_model_ref="gemini/test-selected-model", polish_speed_mode="fast")
    app = object.__new__(main.VoiceFlowApp)
    result = app._finalize_text(detected.content, session, effective=effective, command=detected.command, outcome_callback=outcomes.append)
    assert "Friday" in result
    assert seen["task"] == "rewrite"
    assert seen["overrides"]["length"] == "short"
    assert seen["model_ref"] == session.polish_model_ref
    assert seen["speed_mode"] == "fast"
    assert seen["force_ai"] is True
    assert outcomes == ["ai_accepted"]

from __future__ import annotations

import os
import sys

import pytest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.polisher import TextPolisher, _candidate_preserves_content


def _polisher(monkeypatch: pytest.MonkeyPatch, response: str | None) -> TextPolisher:
    engine = TextPolisher()
    monkeypatch.setattr("voice_flow.polisher.storage.get_setting", lambda key, default=None: default)
    monkeypatch.setattr("voice_flow.polisher.storage.get_all_api_keys", lambda: {"gemini": "test-key"})
    monkeypatch.setattr(engine, "_polish_with_api_pool", lambda *_args: response)
    monkeypatch.setattr(
        "voice_flow.polisher.dictionary_engine.apply_dictionary_post_processing",
        lambda text: text,
    )
    return engine


def test_short_unrelated_api_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _polisher(monkeypatch, "Sure.")

    assert engine.polish("send the report now") == "Send the report now."


def test_same_length_api_substitution_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _polisher(monkeypatch, "Cancel the project immediately without discussion")

    result = engine.polish("Book the meeting tomorrow at ten")

    assert "book" in result.lower()
    assert "cancel" not in result.lower()


def test_literal_words_are_not_removed_by_sanitizer(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _polisher(monkeypatch, "Sure, call Alice")

    assert engine.polish("Sure, call Alice") == "Sure, call Alice."


def test_local_fallback_keeps_ordinary_actually_and_i_mean(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _polisher(monkeypatch, None)

    assert engine.polish("I actually prefer tea") == "I actually prefer tea."
    assert engine.polish("I mean to call Alice") == "I mean to call Alice."


def test_local_fallback_keeps_semantic_like_and_you_know(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _polisher(monkeypatch, None)

    assert engine.polish("I like this") == "I like this."
    assert engine.polish("you know the answer") == "You know the answer."


def test_api_cannot_drop_unicode_content(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _polisher(monkeypatch, "Send now.")

    assert engine.polish("send 你好 now") == "Send 你好 now."


def test_api_cannot_drop_symbolic_term_content(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _polisher(monkeypatch, "Run C now.")

    assert engine.polish("run C++ now") == "Run C++ now."


def test_long_plain_polish_cannot_change_one_dictated_action() -> None:
    source = (
        "First of all I is preparing the launch update for the team. "
        "The design review is complete and the test results are ready for everyone. "
        "Another thing we need to tell Alex about the delivery date and explain the remaining risks. "
        "Finally we will meet on Friday to choose the next release date and share it with customers."
    )
    candidate = (
        "First of all, I am preparing the launch update for the team. "
        "The design review is complete and test results are ready for everyone. "
        "Another task requires communication with Alex regarding the delivery date and remaining risks. "
        "Finally, we will meet on Friday to discuss the next release date and share it with customers."
    )

    assert not _candidate_preserves_content(source, candidate, task="cleanup")


def test_prompt_cannot_invent_customizable_reminders() -> None:
    source = "Build a calendar with offline support and reminders."
    candidate = "Create a calendar that supports offline access and includes customizable reminders for each event."

    assert not _candidate_preserves_content(source, candidate, task="prompt", command_format="prompt")


_LOGIN_SOURCE = (
    "I want you to build a login page with email and password. The page should show an error "
    "if the password is wrong and it should remember the user."
)
_VOICE_FLOW_SOURCE = (
    "so basically I was testing the voice flow feature and the polishing is slow and the commands "
    "are not working so can you check what is happening and fix it and make the polishing fast"
)


@pytest.mark.parametrize(
    ("source", "candidate"),
    [
        (
            _LOGIN_SOURCE,
            "Objective: Build a login page with email and password authentication.\n\nRequirements:\n"
            "- Show an error message when the password is incorrect.\n- Remember the user after they log in.",
        ),
        (
            _VOICE_FLOW_SOURCE,
            "Context: I was testing the Voice Flow feature. Polishing is slow and voice commands are not working.\n\n"
            "Task: Investigate what is happening, fix the voice commands, and make polishing fast.",
        ),
        (
            _VOICE_FLOW_SOURCE,
            "Task: Investigate why Voice Flow polishing is slow and why voice commands are not working, "
            "then fix both issues and improve polishing performance.",
        ),
    ],
)
def test_structured_prompt_restatement_is_accepted(source: str, candidate: str) -> None:
    from voice_flow.polisher import _fulfills_command

    assert _candidate_preserves_content(source, candidate, task="prompt", command_format="prompt")
    assert _fulfills_command(source, candidate, task="prompt", overrides={}, command_format="prompt")


def test_prompt_that_drops_a_dictated_requirement_is_rejected() -> None:
    candidate = (
        "Objective: Build a login page with email and password.\n\nRequirements:\n"
        "- Show an error message when the password is incorrect."
    )
    assert not _candidate_preserves_content(_LOGIN_SOURCE, candidate, task="prompt", command_format="prompt")


def test_prompt_that_invents_many_requirements_is_rejected() -> None:
    candidate = (
        "Objective: Build a login page with email and password authentication.\n\nRequirements:\n"
        "- Show an error when the password is incorrect.\n- Remember the user.\n"
        "- Add two-factor verification, password recovery, social providers, captcha challenges and throttling."
    )
    assert not _candidate_preserves_content(_LOGIN_SOURCE, candidate, task="prompt", command_format="prompt")


def test_cleanup_may_drop_leading_and_trailing_discourse_markers() -> None:
    source = "um so I think we should uh move the launch to next week because the tests are failing okay"
    candidate = "I think we should move the launch to next week because the tests are failing."
    assert _candidate_preserves_content(source, candidate, task="cleanup")
    assert not _candidate_preserves_content("um so can you turn the lights on", "Can you turn the lights?", task="cleanup")


def test_email_with_generic_sign_off_is_fulfilled_but_placeholders_are_not() -> None:
    from voice_flow.polisher import _fulfills_command

    source = "tell john the meeting moved to friday at 3 pm"
    signed = "Hi John,\n\nThe meeting has moved to Friday at 3 PM.\n\nBest regards,"
    assert _fulfills_command(source, signed, task="rewrite", overrides={}, command_format="email")
    placeholder = signed + "\n[Your Name]"
    assert not _fulfills_command(source, placeholder, task="rewrite", overrides={}, command_format="email")


def test_bullet_list_may_drop_modal_scaffolding() -> None:
    source = "for the release we have to update the docs fix the login bug and bump the version number"
    candidate = "- Update the docs\n- Fix the login bug\n- Bump the version number"
    assert _candidate_preserves_content(source, candidate, task="rewrite", command_format="bullet_list")
    assert not _candidate_preserves_content(
        source, "- Update the docs\n- Bump the version number", task="rewrite", command_format="bullet_list",
    )


def test_cleanup_that_flips_first_person_to_you_is_rejected() -> None:
    source = "I was like you know trying to fix the bug but uh it keeps coming back every time I restart the server"
    flipped = "I was trying to fix the bug, but it keeps coming back every time you restart the server."
    kept = "I was trying to fix the bug, but it keeps coming back every time I restart the server."
    assert not _candidate_preserves_content(source, flipped, task="cleanup")
    assert _candidate_preserves_content(source, kept, task="cleanup")
    assert _candidate_preserves_content(
        "can you send me the slides", "Can you send me the slides?", task="cleanup",
    )


def test_resolved_self_correction_is_accepted() -> None:
    source = "so um i need to like send the the report by uh friday no wait make that thursday"
    assert _candidate_preserves_content(source, "So I need to send the report by Thursday.", task="cleanup")
    assert _candidate_preserves_content(
        "send it to john I mean mike please", "Send it to Mike, please.", task="cleanup",
    )
    assert not _candidate_preserves_content(source, "So I need to send the report by Friday.", task="cleanup")


def test_dropping_words_without_a_correction_marker_is_still_rejected() -> None:
    assert not _candidate_preserves_content(
        "please send the report by friday or thursday", "Please send the report by Thursday.", task="cleanup",
    )


def test_register_rewrite_may_rephrase_without_changing_the_facts() -> None:
    source = "hey so we finally shipped the new onboarding and people are actually finishing it lol can you believe it"
    professional = "We have shipped the new onboarding flow, and users are now completing it."
    funny = "We shipped onboarding and, against all odds, people are actually finishing it."
    assert _candidate_preserves_content(source, professional, task="rewrite", allow_rewording=True)
    assert _candidate_preserves_content(source, funny, task="rewrite", allow_rewording=True)
    assert not _candidate_preserves_content(source, professional, task="cleanup")
    assert not _candidate_preserves_content(
        source,
        "Cancel the project immediately without any further discussion today.",
        task="rewrite",
        allow_rewording=True,
    )
    assert not _candidate_preserves_content(
        source,
        "We shipped onboarding for 5000 users and revenue doubled overnight.",
        task="rewrite",
        allow_rewording=True,
    )


def test_tweet_rewrite_keeps_a_negation_and_a_time() -> None:
    source = "the launch party is friday at 7 and it is not open to the public"
    tweet = "Launch party Friday at 7. Not open to the public."
    assert _candidate_preserves_content(
        source, tweet, task="rewrite", command_format="tweet", allow_rewording=True,
    )
    assert not _candidate_preserves_content(
        source,
        "Launch party Friday at 7. Open to the public.",
        task="rewrite",
        command_format="tweet",
        allow_rewording=True,
    )


def test_prompt_role_opening_counts_as_a_prompt_and_a_question_does_not() -> None:
    from voice_flow.polisher import _fulfills_command

    source = "check why polishing with cloud models is still bad and fix it"
    role = "You are reviewing Voice Flow. Polishing with cloud models is still bad. Check why and fix it."
    assert _fulfills_command(source, role, task="prompt", overrides={}, command_format="prompt")
    assert not _fulfills_command(source, "What should I fix?", task="prompt", overrides={}, command_format="prompt")


def test_spoken_numbers_and_times_match_their_written_form() -> None:
    source = "the meeting is at three thirty pm and it costs twenty five dollars per person"
    assert _candidate_preserves_content(source, "The meeting is at 3:30pm, and it costs $25 per person.", task="cleanup")
    assert _candidate_preserves_content(
        "hey john the meeting got moved to friday at 3 pm", "Hey John, the meeting got moved to Friday at 3pm.",
        task="cleanup",
    )
    assert not _candidate_preserves_content(source, "The meeting is at 3:30pm, and it costs $35 per person.", task="cleanup")

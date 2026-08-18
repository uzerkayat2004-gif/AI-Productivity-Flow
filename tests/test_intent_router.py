"""Intent router + spoken number normalization tests — the Wispr-style
zero-model gatekeeper and post-processing layers."""

from __future__ import annotations

from voice_flow.intent_router import route_utterance
from voice_flow.text_processing import adapt_first_letter, normalize_spoken_numbers


# --- Intent routing ----------------------------------------------------------

def test_commands_get_light_cleanup_and_no_ai() -> None:
    decision = route_utterance("send this to john", category="work", style_id="work_casual")
    assert decision.is_command
    assert decision.allow_ai is False
    assert decision.level == "cleanup_light"


def test_questions_skip_ai_polish() -> None:
    decision = route_utterance("what time is the meeting", category="work", style_id="work_casual")
    assert decision.is_question
    assert decision.allow_ai is False


def test_question_mark_detected() -> None:
    decision = route_utterance("are you coming?", category="personal", style_id="personal_casual")
    assert decision.is_question
    assert decision.allow_ai is False


def test_terminal_style_is_verbatim() -> None:
    decision = route_utterance("echo hello world", category="developer", style_id="cleanup_none")
    assert decision.mode == "verbatim"
    assert decision.level == "cleanup_none"
    assert decision.allow_ai is False


def test_developer_context_skips_ai() -> None:
    decision = route_utterance("fix the bug in the merge function", category="developer", style_id="developer_casual")
    assert decision.allow_ai is False
    assert decision.level == "cleanup_light"


def test_very_casual_chat_skips_ai() -> None:
    decision = route_utterance("omg that was so funny", category="personal", style_id="personal_very_casual")
    assert decision.allow_ai is False
    assert decision.level == "cleanup_light"


def test_formal_email_gets_high_cleanup_and_ai() -> None:
    decision = route_utterance("please find attached the quarterly report", category="email", style_id="email_formal")
    assert decision.allow_ai is True
    assert decision.level == "cleanup_high"


def test_default_gets_medium_cleanup_and_ai() -> None:
    decision = route_utterance("just a normal note about the project", category="other", style_id="other_casual")
    assert decision.allow_ai is True
    assert decision.level == "cleanup_medium"


def test_context_capitalize_after_sentence_end() -> None:
    decision = route_utterance(
        "hello there", category="other", style_id="other_casual",
        before="That was great. ", after="", trustworthy_context=True,
    )
    assert decision.capitalize_first is True


def test_context_lowercase_mid_sentence() -> None:
    decision = route_utterance(
        "continued here", category="other", style_id="other_casual",
        before="and then ", after=" more text", trustworthy_context=True,
    )
    assert decision.capitalize_first is False


def test_context_ignored_when_untrustworthy() -> None:
    decision = route_utterance(
        "hello there", category="other", style_id="other_casual",
        before="That was great. ", after="", trustworthy_context=False,
    )
    assert decision.capitalize_first is None


# --- First-letter adaptation -------------------------------------------------

def test_adapt_first_letter_capitalize() -> None:
    assert adapt_first_letter("hello there", True) == "Hello there"
    assert adapt_first_letter("(hello)", True) == "(Hello)"


def test_adapt_first_letter_lowercase() -> None:
    assert adapt_first_letter("Hello there", False) == "hello there"


def test_adapt_first_letter_none_is_noop() -> None:
    assert adapt_first_letter("Hello there", None) == "Hello there"


def test_adapt_first_letter_empty() -> None:
    assert adapt_first_letter("", True) == ""
    assert adapt_first_letter("123 Xyz", True) == "123 Xyz"
    assert adapt_first_letter("123 !!!", False) == "123 !!!"


# --- Spoken number normalization ---------------------------------------------

def test_numbers_two_word_phrase() -> None:
    assert normalize_spoken_numbers("twenty five people") == "25 people"


def test_numbers_three_digit_phrase() -> None:
    assert normalize_spoken_numbers("one hundred and twenty") == "120"


def test_numbers_large_scale() -> None:
    assert normalize_spoken_numbers("two thousand three hundred") == "2300"


def test_numbers_stacked_scales() -> None:
    assert normalize_spoken_numbers("five hundred thousand") == "500000"
    assert normalize_spoken_numbers("one hundred thousand") == "100000"
    assert normalize_spoken_numbers("one million two hundred thousand") == "1200000"


def test_numbers_decimal_with_tens_after_point_untouched() -> None:
    assert normalize_spoken_numbers("three point twenty five") == "three point twenty five"
    assert normalize_spoken_numbers("point fifteen") == "point fifteen"


def test_numbers_after_comma_convert() -> None:
    assert normalize_spoken_numbers("okay, twenty five") == "okay, 25"


def test_numbers_decimal() -> None:
    assert normalize_spoken_numbers("three point five") == "3.5"
    assert normalize_spoken_numbers("point five") == "0.5"


def test_numbers_single_word() -> None:
    assert normalize_spoken_numbers("give me five") == "give me 5"
    assert normalize_spoken_numbers("top ten") == "top 10"


def test_numbers_pronoun_one_untouched() -> None:
    assert normalize_spoken_numbers("one must not do that") == "one must not do that"
    assert normalize_spoken_numbers("I have one") == "I have one"


def test_numbers_ordinals_untouched() -> None:
    assert normalize_spoken_numbers("twenty first century") == "twenty first century"
    assert normalize_spoken_numbers("I finished second") == "I finished second"


def test_numbers_ambiguous_and_untouched() -> None:
    assert normalize_spoken_numbers("two and three") == "two and three"


def test_numbers_zero_untouched() -> None:
    assert normalize_spoken_numbers("zero tolerance policy") == "zero tolerance policy"


def test_numbers_currency_words_untouched() -> None:
    assert normalize_spoken_numbers("ten dollars") == "10 dollars"
    assert normalize_spoken_numbers("one dollar") == "one dollar"


def test_numbers_ordinal_after_cardinal_untouched() -> None:
    assert normalize_spoken_numbers("twenty first street") == "twenty first street"
    assert normalize_spoken_numbers("I finished twenty first") == "I finished twenty first"


def test_numbers_malformed_phrases_untouched() -> None:
    assert normalize_spoken_numbers("two three") == "two three"
    assert normalize_spoken_numbers("five twenty") == "five twenty"


def test_numbers_in_urls_protected() -> None:
    assert normalize_spoken_numbers("visit https://example.com/twenty five now") == "visit https://example.com/twenty five now"
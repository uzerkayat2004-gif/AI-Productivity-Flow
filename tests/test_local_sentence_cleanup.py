from __future__ import annotations

import os
import sys

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.text_processing import is_protected_literal, lowercase_prose_text, sentence_case_text


def test_capitalizes_first_and_later_sentence_starts_without_rewriting_words() -> None:
    text = "i have the notes. please keep the rollback disabled"
    assert sentence_case_text(text) == "I have the notes. Please keep the rollback disabled"


def test_capitalizes_paragraph_starts_and_keeps_newlines_and_repetitions() -> None:
    text = "first line\nsecond line\n\nrepeat repeat. repeat repeat"
    assert sentence_case_text(text) == "First line\nSecond line\n\nRepeat repeat. Repeat repeat"


def test_protected_identifier_is_unchanged_and_detected_as_all_literal() -> None:
    assert sentence_case_text("uh.client") == "uh.client"
    assert is_protected_literal("uh.client")
    assert is_protected_literal("  uh.client  ")
    assert not is_protected_literal("uh.client must stay unchanged")


def test_protected_code_quotes_urls_emails_and_paths_are_preserved() -> None:
    text = (
        'i saw "i has the notes. please keep it" and `i has` at '
        "https://example.com/path.v1 with ops.team@example.com from C:\\data\\file.py with care. "
        "please check the code"
    )
    expected = (
        'I saw "i has the notes. please keep it" and `i has` at '
        "https://example.com/path.v1 with ops.team@example.com from C:\\data\\file.py with care. "
        "Please check the code"
    )
    assert sentence_case_text(text) == expected


def test_decimal_and_dotted_literals_do_not_create_false_boundaries() -> None:
    text = "version 3.14 uses uh.client. please keep v1.2 unchanged"
    assert sentence_case_text(text) == "Version 3.14 uses uh.client. Please keep v1.2 unchanged"


def test_numeric_sentence_starts_consume_capitalization_slot_without_changing_units() -> None:
    assert sentence_case_text("12 ms is enough. keep it short.") == "12 ms is enough. Keep it short."
    assert sentence_case_text("3 apples are ready. keep them fresh.") == "3 apples are ready. Keep them fresh."
    assert sentence_case_text("1. keep this") == "1. Keep this"


def test_all_protected_literal_kinds_are_recognized() -> None:
    for literal in (
        "https://example.com/a.b?x=1",
        "ops.team@example.com",
        "C:\\Users\\Asus\\notes.txt",
        "`i has`",
        '"please keep this lowercase."',
        "$HOME",
    ):
        assert is_protected_literal(literal), literal


def test_lowercase_prose_preserves_case_sensitive_protected_literals() -> None:
    text = (
        'KEEP `HTTPClient` at https://example.com/CasePath and C:\\Temp\\App; '
        'email Ops.Team@Example.com and say "Do Not Alter". UH.CLIENT is ready.'
    )
    expected = (
        'keep `HTTPClient` at https://example.com/CasePath and C:\\Temp\\App; '
        'email Ops.Team@Example.com and say "Do Not Alter". UH.CLIENT is ready.'
    )
    assert lowercase_prose_text(text) == expected

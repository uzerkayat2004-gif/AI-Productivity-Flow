"""Spoken punctuation converts only standalone commands, never real words (B1)."""
from __future__ import annotations

import os
import sys

import pytest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.text_processing import apply_spoken_punctuation


@pytest.mark.parametrize("text", [
    "the trial period ends in May",
    "The trial period ends in May.",
    "a comma separated list",
    "new line of products launches today",
    "We have a new line of products launching today",
    "a long period of growth",
    "The growth lasted a long period",
    "the colon is",
    "The colon is part of the large intestine.",
    "what a question mark on his face",
    "he drew a question mark",
    "the reporting period",
    "the next line is wrong",
    "add a line break",
    "the question mark character",
    "write the word comma",
    "period",
])
def test_real_words_are_never_rewritten(text: str) -> None:
    assert apply_spoken_punctuation(text) == text


@pytest.mark.parametrize("text,expected", [
    ("send it today period", "send it today."),
    ("Send it today period.", "Send it today."),
    ("Send it today. Period.", "Send it today."),
    ("what is the status question mark", "what is the status?"),
    ("is this working question mark", "is this working?"),
    ("that is amazing exclamation mark", "that is amazing!"),
    ("send it today full stop", "send it today."),
    ("Ship it today period. Then call me", "Ship it today. Then call me"),
    ("Hello Sam comma Thanks for the notes", "Hello Sam, Thanks for the notes"),
    ("Dear Sam colon Thanks", "Dear Sam: Thanks"),
    ("alpha new line Beta", "alpha\nBeta"),
    ("dear team new paragraph Thanks", "dear team\n\nThanks"),
    ("see https://x.com/period now period", "see https://x.com/period now."),
])
def test_standalone_commands_still_convert(text: str, expected: str) -> None:
    assert apply_spoken_punctuation(text) == expected


# Mac QA 2026-10-16 (voice_a2/voice_b2): every recognizer returned the spoken
# marks in lower case mid-sentence, so the strict sentence-boundary guard never
# fired. A clause-opening next word now counts as a boundary for . , ? !
@pytest.mark.parametrize("text,expected", [
    ("Send the report to day period then call me comma please.", "Send the report to day. Then call me, please."),
    ("Send the report to date period then call me comma please", "Send the report to date. Then call me, please"),
    ("Send the report today period then call me comma please", "Send the report today. Then call me, please"),
    ("Is it done question mark then ship it", "Is it done? Then ship it"),
    ("Hello Sam comma please call me", "Hello Sam, please call me"),
])
def test_lowercase_spoken_marks_before_a_clause_opener_convert(text: str, expected: str) -> None:
    assert apply_spoken_punctuation(text) == expected


@pytest.mark.parametrize("text", [
    "After a two week period we review it.",
    "After a 30 day period we review it.",
    "After a two day period we review it.",
    "During this period we grew.",
    "The waiting period and the fee apply.",
    "The grace period then ends.",
    "I need a comma please",
    "Oxford comma and semicolons",
    "Please send a comma separated list of names.",
    "We launched a new line of products this week.",
    "He had a question mark on his face.",
])
def test_noun_uses_before_a_clause_opener_stay_words(text: str) -> None:
    assert apply_spoken_punctuation(text) == text

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

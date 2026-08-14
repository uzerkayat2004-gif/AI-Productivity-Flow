from __future__ import annotations

import os
import sys

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.text_processing import apply_spoken_punctuation, split_press_enter


def test_spoken_punctuation_converts_explicit_terms_without_rewriting_words() -> None:
    assert apply_spoken_punctuation("what is the status question mark") == "what is the status?"
    assert apply_spoken_punctuation("alpha new line beta") == "alpha\nbeta"
    assert apply_spoken_punctuation("the question mark character") == "the question mark character"


def test_press_enter_accepts_terminal_punctuation_variants() -> None:
    for suffix in ("", ".", "!", "!!!", "?"):
        result = split_press_enter(f"submit the form press enter{suffix}", enabled=True)
        assert result.press_enter is True
        assert result.text == "submit the form"


def test_press_enter_phrase_is_preserved_when_user_mentions_literal_words() -> None:
    result = split_press_enter("type the words press enter", enabled=True)
    assert result.press_enter is False
    assert result.text == "type the words press enter"


def test_press_enter_disabled_is_never_extracted() -> None:
    result = split_press_enter("submit press enter!!!", enabled=False)
    assert result.press_enter is False
    assert result.text == "submit press enter!!!"

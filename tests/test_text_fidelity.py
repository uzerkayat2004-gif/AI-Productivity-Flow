from __future__ import annotations

import os
import sys

import pytest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.polisher import TextPolisher


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

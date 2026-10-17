"""A saved name that is also an English word is not forced onto the plain word.

Mac QA 2026-10-16 (voice_a2, dictionary-on): with "React" saved, the dictation
"I will react to the email later today." was pasted as "I will React to the
email later today." The saved spelling still applies where the word is the
name.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from voice_flow.dictionary import DictionaryEngine
from voice_flow.storage import StorageEngine


@pytest.fixture
def engine(tmp_path: Path) -> DictionaryEngine:
    store = StorageEngine(str(tmp_path / "voice-flow.db"))
    for word in ("React", "Swift", "Kubernetes"):
        assert store.add_dictionary_entry(word)
    return DictionaryEngine(store)


@pytest.mark.parametrize("text", [
    "I will react to the email later today.",
    "How do you react when that happens?",
    "Don't react yet.",
    "They react quickly.",
    "We need to react to the feedback.",
    "She reacts to every message.",
    "Please be swift, we must react fast.",
])
def test_ordinary_verb_use_keeps_lowercase(engine, text):
    assert engine.apply_dictionary_post_processing(text) == text
    assert engine.restore_dictionary_spelling(text) == text
    assert engine.guard_polished_output(text, text) == text


@pytest.mark.parametrize("text,expected", [
    ("I built it with react and kubernetes.", "I built it with React and Kubernetes."),
    ("The react component renders twice.", "The React component renders twice."),
    ("learning react native this week", "learning React native this week"),
    ("Write the swift code tomorrow.", "Write the Swift code tomorrow."),
])
def test_name_use_still_gets_the_saved_spelling(engine, text, expected):
    assert engine.apply_dictionary_post_processing(text) == expected


def test_non_homograph_words_are_unchanged_by_the_context_rule(engine):
    # "Kubernetes" is not an English word: casing applies in any context.
    assert engine.apply_dictionary_post_processing("we will kubernetes it") == "we will Kubernetes it"

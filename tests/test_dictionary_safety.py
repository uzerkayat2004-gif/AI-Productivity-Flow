from __future__ import annotations

import os
import sys

import pytest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.dictionary import DictionaryEngine


class _DictionarySource:
    def __init__(self, words: list[str]) -> None:
        self.words = words
        self.revision = 1

    def entries(self, include_auto: bool = True) -> list[dict[str, str]]:
        return [{"word": word, "category": "Personal"} for word in self.words]


def _engine(monkeypatch: pytest.MonkeyPatch, words: list[str]) -> DictionaryEngine:
    source = _DictionarySource(words)
    monkeypatch.setattr("voice_flow.dictionary.storage.get_dictionary_entries", source.entries)
    monkeypatch.setattr("voice_flow.dictionary.storage.get_dictionary_revision", lambda: source.revision)
    return DictionaryEngine()


def test_exact_terms_are_boundary_safe_and_do_not_fuzzy_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch, ["TING", "API", "form"])

    text = "I think this app came from a platform called catapult."

    assert engine.apply_dictionary_post_processing(text) == text


def test_explicit_term_preserves_casing_only_for_exact_match(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch, ["VoiceFlow"])

    assert engine.apply_dictionary_post_processing("voiceflow is ready") == "VoiceFlow is ready"
    assert engine.apply_dictionary_post_processing("voiceflows is ready") == "voiceflows is ready"


def test_snippet_uses_trigger_length_and_does_not_cascade(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch, [
        "a -> this is a long expansion",
        "a b -> PHRASE",
        "foo -> bar",
        "bar -> baz",
    ])

    assert engine.apply_dictionary_post_processing("a b") == "PHRASE"
    assert engine.apply_dictionary_post_processing("foo") == "bar"


def test_snippet_expansion_inserts_backslashes_literally(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch, [r"my path -> C:\Users\me\file.txt"])

    assert engine.apply_dictionary_post_processing("open my path") == r"open C:\Users\me\file.txt"


def test_empty_snippet_expansion_cannot_delete_text(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch, ["foo ->"])

    assert engine.apply_dictionary_post_processing("foo") == "foo"


def test_dictionary_processing_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch, ["myemail -> me@example.com", "VoiceFlow"])

    once = engine.apply_dictionary_post_processing("voiceflow myemail")
    assert engine.apply_dictionary_post_processing(once) == once


def test_dictionary_refreshes_when_storage_revision_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _DictionarySource(["VoiceFlow"])
    monkeypatch.setattr("voice_flow.dictionary.storage.get_dictionary_entries", source.entries)
    monkeypatch.setattr("voice_flow.dictionary.storage.get_dictionary_revision", lambda: source.revision)
    engine = DictionaryEngine()

    assert engine.apply_dictionary_post_processing("voiceflow") == "VoiceFlow"
    source.words.append("NewTerm")
    source.revision += 1
    assert engine.apply_dictionary_post_processing("newterm") == "NewTerm"

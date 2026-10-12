"""The rebuilt dictionary: Words, Replacements, no learning, one-time reset."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from voice_flow.dictionary import DictionaryEngine
from voice_flow.dictionary_rules import replacement_problem, term_problem
from voice_flow.storage import StorageEngine


@pytest.fixture
def store(tmp_path: Path) -> StorageEngine:
    return StorageEngine(str(tmp_path / "voice-flow.db"))


@pytest.fixture
def engine(store: StorageEngine) -> DictionaryEngine:
    assert store.add_dictionary_entry("Kubernetes")
    assert store.add_dictionary_entry("Siobhan")
    assert store.add_dictionary_entry("API")
    assert store.add_dictionary_entry("HyperKube", "hyper cube")
    store.add_snippet("my email", "me@example.com")
    return DictionaryEngine(store)


# -- Words fix only their own spelling --------------------------------------

def test_word_restores_its_own_spelling(engine):
    assert engine.apply_dictionary_post_processing("deploy to kubernetes now") == "deploy to Kubernetes now"
    assert engine.apply_dictionary_post_processing("ask siobhan") == "ask Siobhan"


def test_word_keeps_plural_and_possessive(engine):
    out = engine.apply_dictionary_post_processing("kubernetes's apis and siobhan's notes")
    assert out == "Kubernetes's APIs and Siobhan's notes"


def test_word_never_matches_inside_another_word(engine):
    assert engine.apply_dictionary_post_processing("rapid kubernetesy capital") == "rapid kubernetesy capital"


@pytest.mark.parametrize("text", [
    "hey team, the meeting report is here",
    "Hey Voice Flow make this an email",
    "here is the thing I said",
    "Let's meet tomorrow morning and review the report.",
])
def test_ordinary_sentences_are_untouched(engine, text):
    assert engine.apply_dictionary_post_processing(text) == text


def test_urls_and_emails_are_protected(engine):
    text = "see https://kubernetes.io and kubernetes@example.com"
    assert engine.apply_dictionary_post_processing(text) == text


# -- Replacements are explicit whole phrases --------------------------------

def test_replacement_is_whole_phrase_only(engine):
    assert engine.apply_dictionary_post_processing("we use hyper cube") == "we use HyperKube"
    assert engine.apply_dictionary_post_processing("a hyper  cube test") == "a HyperKube test"
    assert engine.apply_dictionary_post_processing("hyper cubes") == "hyper cubes"
    assert engine.apply_dictionary_post_processing("a cube and hyper") == "a cube and hyper"


def test_pass_is_idempotent_and_does_not_cascade(engine):
    once = engine.apply_dictionary_post_processing("hyper cube on kubernetes, send my email")
    assert once == "HyperKube on Kubernetes, send me@example.com"
    assert engine.apply_dictionary_post_processing(once) == once


# -- Shortcuts stay a separate, working feature -----------------------------

def test_shortcuts_still_expand(engine):
    assert engine.apply_dictionary_post_processing("please send my email") == "please send me@example.com"


def test_shortcuts_survive_the_reset(tmp_path):
    db = tmp_path / "old.db"
    first = StorageEngine(str(db))
    first.add_snippet("sig", "Best, Ada")
    first.save_setting(StorageEngine.DICTIONARY_REBUILD_KEY, False)
    StorageEngine(str(db))
    assert [s["trigger"] for s in StorageEngine(str(db)).get_snippets()] == ["sig"]


# -- Polish on and off behave the same --------------------------------------

def test_polish_on_and_off_use_the_same_deterministic_pass(engine, monkeypatch):
    from voice_flow import polisher

    monkeypatch.setattr(polisher, "dictionary_engine", engine)
    text = "kubernetes and hyper cube said hey"
    off = polisher._apply_dictionary_safely(text)
    on = polisher._apply_dictionary_with_trace(text, [])
    assert off == on == "Kubernetes and HyperKube said hey"


def test_polisher_gets_preferred_spellings_but_not_ordinary_words(engine, monkeypatch):
    from voice_flow import polisher

    monkeypatch.setattr(polisher, "dictionary_engine", engine)
    line = polisher._preferred_spellings_line("anything")
    assert "Kubernetes" in line and "HyperKube" in line
    assert "hey" not in line.lower().split(":", 1)[1]


# -- Validation: ordinary and built-in words are refused --------------------

@pytest.mark.parametrize("word", ["meeting", "Meeting", "hey", "Hey", "Voice Flow", "voiceflow", "here", "the report"])
def test_ordinary_and_builtin_words_are_refused(store, word):
    assert term_problem(word)
    assert not store.add_dictionary_entry(word)
    assert store.get_dictionary_words() == []


@pytest.mark.parametrize("word", ["Kubernetes", "Siobhan", "GraphQL", "Grok Bot", "Anthropic", "C++"])
def test_names_and_terms_are_accepted(store, word):
    assert term_problem(word) is None
    assert store.add_dictionary_entry(word)


def test_wake_phrase_words_cannot_be_replaced(store):
    assert replacement_problem("Voice Flow", "Voice Flo")
    with pytest.raises(ValueError):
        store.add_dictionary_correction("hey", "Hi")
    assert replacement_problem("same", "same")
    assert replacement_problem("grow bot", "Grok Bot") is None
    assert store.add_dictionary_correction("grow bot", "Grok Bot")["correct_text"] == "Grok Bot"


# -- No automatic learning ---------------------------------------------------

def test_dictation_history_never_adds_dictionary_rows(store):
    for _ in range(5):
        store.add_dictation(
            "deploy kubernetes with Zorblax today", "Deploy Kubernetes with Zorblax today.",
            "App", 2.0, "smart_clean", status="success", insertion_status="pasted",
        )
    assert store.get_dictionary_words(include_auto=True) == []
    assert store.get_dictionary_corrections() == []
    with store._get_conn_ctx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM lexicon_candidates").fetchone()[0] == 0


def test_learning_modules_are_gone():
    import importlib.util

    assert importlib.util.find_spec("voice_flow.correction_learning") is None
    assert importlib.util.find_spec("voice_flow.vocabulary_learning") is None


# -- One-time reset with a backup -------------------------------------------

def test_reset_backs_up_and_clears_once(tmp_path):
    db = tmp_path / "voice-flow.db"
    old = StorageEngine(str(db))
    with old._get_conn_ctx() as conn:
        conn.execute("INSERT INTO dictionary (word, category, created_at) VALUES ('meeting', 'Learned', 'x')")
        conn.execute(
            "INSERT INTO dictionary_corrections (wrong_text, correct_text, created_at, updated_at) "
            "VALUES ('hey', 'here', 'x', 'x')"
        )
        conn.commit()
    old.add_snippet("sig", "Best, Ada")
    old.save_setting("some_other_setting", "kept")
    old.save_setting(StorageEngine.DICTIONARY_REBUILD_KEY, False)

    upgraded = StorageEngine(str(db))
    assert upgraded.get_dictionary_words(include_auto=True) == []
    assert upgraded.get_dictionary_corrections() == []
    assert upgraded.get_setting("some_other_setting") == "kept"
    assert [s["trigger"] for s in upgraded.get_snippets()] == ["sig"]

    backups = list(tmp_path.glob("dictionary-backup-before-rebuild-*.json"))
    assert len(backups) == 1
    dump = json.loads(backups[0].read_text(encoding="utf-8"))
    assert [r["word"] for r in dump["tables"]["dictionary"]] == ["meeting"]
    assert dump["tables"]["dictionary_corrections"][0]["wrong_text"] == "hey"

    # Runs once: new words survive the next start and no second backup.
    assert upgraded.add_dictionary_entry("Kubernetes")
    again = StorageEngine(str(db))
    assert again.get_dictionary_words() == ["Kubernetes"]
    assert len(list(tmp_path.glob("dictionary-backup-before-rebuild-*.json"))) == 1


# -- Recognizer biasing receives the terms ----------------------------------

def test_bias_terms_are_words_and_replacement_targets(engine):
    terms = engine.get_stt_hint_terms()
    assert terms == ["HyperKube", "Kubernetes", "Siobhan", "API"]
    assert "hyper cube" not in terms and "Hyper Kube" not in terms and "my email" not in terms


def test_transcriber_bias_helper_and_nemotron_context(engine, monkeypatch):
    from voice_flow import dictionary, nemotron_engine, transcriber

    monkeypatch.setattr(dictionary, "dictionary_engine", engine)
    terms = transcriber.dictionary_bias_terms()
    assert "Kubernetes" in terms
    contexts, refs = nemotron_engine._make_speech_context(terms)
    assert contexts is not None
    assert b"Kubernetes" in refs[2]


def test_whisper_hotwords_only_when_supported():
    from voice_flow.transcriber import _whisper_hotwords_kwargs

    class WithHotwords:
        def transcribe(self, audio, hotwords=None):
            return [], None

    class Without:
        def transcribe(self, audio):
            return [], None

    assert _whisper_hotwords_kwargs(WithHotwords(), ["Kubernetes"]) == {"hotwords": "Kubernetes"}
    assert _whisper_hotwords_kwargs(Without(), ["Kubernetes"]) == {}
    assert _whisper_hotwords_kwargs(WithHotwords(), []) == {}


def test_wake_phrase_is_built_in_not_a_dictionary_row(engine):
    assert engine.repair_wake_term("hey voiceflow make this an email") == "hey Voice Flow make this an email"
    assert "Voice Flow" not in engine.get_stt_hint_terms()


def test_camel_case_word_matches_its_spoken_form(store):
    assert store.add_dictionary_entry("HyperKube")
    assert store.add_dictionary_entry("LinkedIn")
    engine = DictionaryEngine(store)
    assert engine.apply_dictionary_post_processing("send the hyper kube update") == "send the HyperKube update"
    # "linked in" is ordinary speech, so LinkedIn has no spoken alias.
    assert engine.apply_dictionary_post_processing("details are linked in the doc") == "details are linked in the doc"

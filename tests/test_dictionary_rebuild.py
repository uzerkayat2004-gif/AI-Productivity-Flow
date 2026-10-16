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
    line = polisher._preferred_spellings_line("hey, kubernetes and HyperKube")
    assert "Kubernetes" in line and "HyperKube" in line
    assert "hey" not in line.lower().split(":", 1)[1]
    assert "Siobhan" not in line  # only names present in this dictation
    assert polisher._preferred_spellings_line("nothing named") == ""


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


# -- Gap audit: protection around every polisher ----------------------------

@pytest.fixture
def guarded(store):
    for word in ("Kubernetes", "Siobhán", "Zsófia", "Hacker News", "kubectl", "API"):
        assert store.add_dictionary_entry(word), word
    store.add_dictionary_correction("grok", "Grok Bot")
    store.add_snippet("my sig", "Best, Ada (kubernetes team)")
    return DictionaryEngine(store)


@pytest.mark.parametrize("model_output, expected", [
    ("We deploy Kubernetis today.", "We deploy Kubernetes today."),
    ("We deploy Kuber Netes today.", "We deploy Kubernetes today."),
    ("Kubernetis's dashboard is up.", "Kubernetes's dashboard is up."),
    ("We deploy KUBERNETES today.", "We deploy Kubernetes today."),
])
def test_guard_repairs_a_model_respelling(guarded, model_output, expected):
    assert guarded.guard_polished_output("we deploy kubernetes today", model_output) == expected


def test_guard_never_inserts_an_unspoken_name(guarded):
    out = "We deploy containers today."
    assert guarded.guard_polished_output("we deploy containers today", out) == out


def test_guard_is_idempotent(guarded):
    once = guarded.guard_polished_output("ask grok about kubernetes", "Ask grok about Kubernetis.")
    assert once == "Ask Grok Bot about Kubernetes."
    assert guarded.guard_polished_output("ask grok about kubernetes", once) == once


def test_replacement_target_is_not_replaced_again(guarded):
    assert guarded.apply_dictionary_post_processing("Grok Bot and grok") == "Grok Bot and Grok Bot"


def test_sentence_start_keeps_the_saved_casing(guarded):
    assert guarded.restore_dictionary_spelling("Kubectl get pods. Api is up.") == "kubectl get pods. API is up."


@pytest.mark.parametrize("text, expected", [
    ("(kubernetes), kubernetes. kubernetes-based", "(Kubernetes), Kubernetes. Kubernetes-based"),
    ("read hacker   news daily", "read Hacker News daily"),
    ("ask zsófia and siobhán", "ask Zsófia and Siobhán"),
    ("the kubernetes’ nodes and apis", "the Kubernetes’ nodes and APIs"),
])
def test_punctuation_multiword_unicode_and_suffixes(guarded, text, expected):
    assert guarded.apply_dictionary_post_processing(text) == expected


class _FakePolisher:
    """Stands in for any route: cloud, S1, LFM, Windows AI, command rewrite."""

    def __init__(self, transform):
        self.transform = transform
        self.seen = None

    def __call__(self, raw_text, *args, **kwargs):
        self.seen = raw_text
        return self.transform(raw_text)


@pytest.mark.parametrize("transform", [
    lambda t: t.replace("Kubernetes", "Kubernetis"),          # model re-spells
    lambda t: t.replace("Kubernetes", "kubernetes").upper().lower().capitalize(),  # casing lost
    lambda t: "Hi team,\n\n" + t.replace("Kubernetes", "Kuber Netes") + "\n\nThanks",  # email template
])
def test_every_polish_route_is_guarded(guarded, monkeypatch, transform):
    from voice_flow import polisher

    monkeypatch.setattr(polisher, "dictionary_engine", guarded)
    fake = _FakePolisher(transform)
    p = object.__new__(polisher.TextPolisher)
    monkeypatch.setattr(p, "_polish_routes", fake, raising=False)
    out = p.polish("deploy cube to kubernetes then send my sig")
    assert "Kubernetes" in out and "Kubernetis" not in out and "Kuber Netes" not in out
    # The model saw the corrected name but not the shortcut expansion.
    assert "Kubernetes" in fake.seen and "my sig" in fake.seen


def test_shortcut_expansion_is_pasted_after_polish(guarded, monkeypatch):
    from voice_flow import polisher

    monkeypatch.setattr(polisher, "dictionary_engine", guarded)
    out = polisher._apply_dictionary_with_trace("send my sig", None)
    assert out == "send Best, Ada (kubernetes team)"  # shortcuts are literal


def test_finalize_text_guards_templates_and_command_rewrites(guarded, monkeypatch):
    from voice_flow import main

    monkeypatch.setattr(main, "dictionary_engine", guarded)
    app = object.__new__(main.VoiceFlowApp)
    monkeypatch.setattr(app, "_finalize_text_routes", lambda raw, *a, **k: "Hello,\n\nKubernetis is ready.", raising=False)
    assert app._finalize_text("kubernetes is ready make this an email", None) == "Hello,\n\nKubernetes is ready."


def test_local_model_prompts_get_only_present_terms(guarded, monkeypatch):
    from voice_flow import dictionary, lfm_engine

    monkeypatch.setattr(dictionary, "dictionary_engine", guarded)
    messages = lfm_engine._build_local_messages("deploy kubernetes now", "Polish", "Polish only the transcript")
    system = messages[0]["content"]
    assert "Keep these names exactly as spelled: Kubernetes." in system
    assert "Zsófia" not in system
    messages = lfm_engine._build_local_messages("make this an email about kubernetes", "email", None)
    assert "Kubernetes" in messages[0]["content"]
    assert lfm_engine._build_local_messages("nothing here", "Polish", "Polish only the transcript")[0]["content"].count("Keep these names") == 0


def test_suggestion_endpoints_and_storage_are_gone(store):
    assert not hasattr(store, "get_lexicon_suggestions")
    assert not hasattr(store, "set_lexicon_candidate_state")
    source = Path(__file__).resolve().parents[1].joinpath("src/voice_flow/gui/api_server.py").read_text(encoding="utf-8")
    assert "/api/dictionary/suggestions" not in source


# -- Regressions from the laptop (12 Oct) ------------------------------------

@pytest.mark.parametrize("raw", [
    "give me the great tweet",
    "what the heck are you doing give me the great tweet",
    "give me the proper tweet",
])
def test_ordinary_words_are_never_mapped_to_saved_names(store, raw):
    assert store.add_dictionary_entry("GitHub")
    assert store.add_dictionary_entry("Twitter")
    engine = DictionaryEngine(store)
    assert engine.apply_dictionary_post_processing(raw) == raw
    polished = raw.capitalize() + "."
    assert engine.guard_polished_output(raw, polished) == polished
    # Even if the source named them, ordinary words in the output are never re-mapped.
    assert engine.guard_polished_output("github and twitter", "Give me the great tweet.") == "Give me the great tweet."


def test_legacy_ordinary_rows_are_ignored_by_the_engine(store):
    with store._get_conn_ctx() as conn:
        for word in ("Hey", "Here", "Voice Flow", "GitHub"):
            conn.execute("INSERT INTO dictionary (word, category, created_at) VALUES (?, 'Personal', 'x')", (word,))
        conn.commit()
    store._touch_lexicon() if hasattr(store, "_touch_lexicon") else None
    engine = DictionaryEngine(store)
    assert engine.apply_dictionary_post_processing("hey here voice flow github") == "hey here voice flow GitHub"
    assert engine.get_stt_hint_terms() == ["GitHub"]


def test_consolidation_never_merges_dictionary_tables():
    from voice_flow import consolidate

    assert not consolidate.DICTIONARY_TABLES & set(consolidate.MERGE_TABLES)
    assert "snippets" in consolidate.MERGE_TABLES and "history" in consolidate.MERGE_TABLES


def test_v2_reset_runs_after_a_v1_reset(tmp_path):
    db = tmp_path / "voice-flow.db"
    first = StorageEngine(str(db))
    with first._get_conn_ctx() as conn:
        conn.execute("INSERT INTO dictionary (word, category, created_at) VALUES ('GitHub', 'Personal', 'x')")
        conn.execute("DELETE FROM settings WHERE key = ?", (StorageEngine.DICTIONARY_REBUILD_KEY,))
        conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('dictionary_rebuild_v1', 'true', 'x')")
        conn.commit()
    again = StorageEngine(str(db))
    assert again.get_dictionary_words(include_auto=True) == []
    assert StorageEngine.DICTIONARY_REBUILD_KEY == "dictionary_rebuild_v2"


def test_nemotron_boost_is_gentle():
    from voice_flow import nemotron_engine

    contexts, _ = nemotron_engine._make_speech_context(["GitHub"])
    assert contexts[0].boost <= 1.5

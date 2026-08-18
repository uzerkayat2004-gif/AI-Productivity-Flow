"""Accuracy-feature tests: pause punctuation, fuzzy dictionary correction,
auto-word prompt biasing, and latency/learning telemetry."""

from __future__ import annotations

from voice_flow.dictionary import DictionaryEngine, dictionary_engine
from voice_flow.storage import StorageEngine
from voice_flow.transcriber import _apply_pause_punctuation


def test_pause_punctuation_small_gap_no_period() -> None:
    segments = [(0.0, 1.0, "hello"), (1.3, 2.0, "world")]
    assert _apply_pause_punctuation(segments) == "hello world"


def test_pause_punctuation_sentence_gap_adds_period() -> None:
    segments = [(0.0, 1.0, "first"), (1.7, 2.2, "second")]
    assert _apply_pause_punctuation(segments) == "first. second"


def test_pause_punctuation_paragraph_gap() -> None:
    segments = [(0.0, 1.0, "first"), (2.5, 3.0, "second")]
    assert _apply_pause_punctuation(segments) == "first\n\nsecond"


def test_pause_punctuation_capitalizes_standalone_i() -> None:
    segments = [(0.0, 1.0, "i think"), (1.8, 2.5, "so")]
    assert _apply_pause_punctuation(segments) == "I think. so"


def test_pause_punctuation_empty() -> None:
    assert _apply_pause_punctuation([]) == ""
    assert _apply_pause_punctuation([(0.0, 1.0, "   ")]) == ""


def test_fuzzy_correction_fixes_misheard_name() -> None:
    engine = DictionaryEngine()
    text = engine._apply_fuzzy_corrections("Roheet said it", ("Rohit",))
    assert text == "Rohit said it"


def test_fuzzy_correction_ignores_common_words() -> None:
    engine = DictionaryEngine()
    # "apple" is common English: must never be "corrected" toward "ample".
    text = engine._apply_fuzzy_corrections("apple orchard", ("ample",))
    assert text == "apple orchard"


def test_fuzzy_correction_fixes_plausible_typo() -> None:
    engine = DictionaryEngine()
    # "bettle" is not common English; the user almost certainly said "bottle".
    text = engine._apply_fuzzy_corrections("bettle the water", ("bottle",))
    assert text == "bottle the water"


def test_fuzzy_correction_ignores_short_words() -> None:
    engine = DictionaryEngine()
    text = engine._apply_fuzzy_corrections("rut", ("Rut",))
    assert text == "rut"


def test_fuzzy_correction_prefers_closest_match() -> None:
    engine = DictionaryEngine()
    # helm is distance 1 from hepm; hemp is distance 2.
    text = engine._apply_fuzzy_corrections("hepm", ("hemp", "helm"))
    assert text == "helm"


def test_fuzzy_correction_never_changes_plurals_or_derivatives() -> None:
    engine = DictionaryEngine()
    text = engine._apply_fuzzy_corrections("VoiceFlows are ready", ("VoiceFlow",))
    assert text == "VoiceFlows are ready"
    text = engine._apply_fuzzy_corrections("Zephyrs blew", ("Zephyr",))
    assert text == "Zephyrs blew"


def test_fuzzy_correction_long_word_transposition() -> None:
    engine = DictionaryEngine()
    text = engine._apply_fuzzy_corrections("Anitgravity", ("Antigravity",))
    assert text == "Antigravity"


def test_dictionary_prompt_includes_auto_learned_words(monkeypatch) -> None:
    entries = [
        {"id": 1, "word": "Rohit", "category": "user", "created_at": ""},
        {"id": 2, "word": "Antigravity", "category": "Auto-Captured", "created_at": ""},
    ]

    def fake_entries(include_auto: bool = True) -> list[dict]:
        return entries if include_auto else [e for e in entries if e["category"] != "Auto-Captured"]

    monkeypatch.setattr(dictionary_engine, "_dirty", True)
    monkeypatch.setattr(dictionary_engine, "_get_revision", lambda: "rev-accuracy-1")
    monkeypatch.setattr(dictionary_engine, "_load_source_words", lambda: ["Rohit"])
    monkeypatch.setattr(dictionary_engine, "_load_prompt_words", lambda: ["Rohit", "Antigravity"])
    prompt = dictionary_engine.get_initial_prompt()
    assert "Antigravity" in prompt
    assert "Rohit" in prompt


def test_dictionary_post_processing_fuzzy_pass(monkeypatch) -> None:
    engine = DictionaryEngine()
    monkeypatch.setattr(engine, "_rules", ())
    monkeypatch.setattr(engine, "_dirty", False)
    monkeypatch.setattr(
        "voice_flow.dictionary.storage.get_setting",
        lambda key, default=None: True if key == "dictionary_fuzzy_enabled" else default,
    )

    def fake_entries(include_auto: bool = True) -> list[dict]:
        return [{"id": 1, "word": "Rohit", "category": "user", "created_at": ""}]

    monkeypatch.setattr("voice_flow.dictionary.storage.get_dictionary_entries", fake_entries)
    monkeypatch.setattr(engine, "_load_source_words", lambda: ["Rohit"])
    engine.mark_dirty()
    result = engine.apply_dictionary_post_processing("Roheet spoke clearly")
    assert result == "Rohit spoke clearly"


def test_dictionary_fuzzy_never_touches_urls(monkeypatch) -> None:
    from voice_flow.dictionary import _Rule

    engine = DictionaryEngine()
    monkeypatch.setattr(engine, "_dirty", False)
    monkeypatch.setattr(engine, "_rules", (_Rule("Rohit", "Rohit"),))
    monkeypatch.setattr(
        "voice_flow.dictionary.storage.get_setting",
        lambda key, default=None: True if key == "dictionary_fuzzy_enabled" else default,
    )
    result = engine.apply_dictionary_post_processing("see https://roheet.example.com now")
    assert "https://roheet.example.com" in result


def test_add_dictation_records_latency_telemetry(tmp_path) -> None:
    store = StorageEngine(db_path=str(tmp_path / "test_accuracy.db"))
    record = store.add_dictation(
        raw_text="hello world",
        polished_text="hello world",
        app_name="Test App",
        duration_sec=2.0,
        style_mode="smart_clean",
        stt_ms=123,
        polish_ms=456,
    )
    assert record.id is not None
    row = store.get_recent_history(limit=1)[0]
    assert row["stt_ms"] == 123
    assert row["polish_ms"] == 456


def test_add_learning_candidates_upserts(tmp_path) -> None:
    store = StorageEngine(db_path=str(tmp_path / "test_learning.db"))
    store.add_learning_candidates(["Harold", "Antigravity", "the", "x", "Uzer"])
    rows = store._get_conn().execute(
        "SELECT original_text, occurrences, status FROM dictionary_learning_candidates ORDER BY original_text"
    ).fetchall()
    by_word = {row["original_text"]: row for row in rows}
    assert set(by_word) == {"Antigravity", "Harold", "Uzer"}
    assert by_word["Antigravity"]["occurrences"] == 1
    assert by_word["Uzer"]["status"] == "pending"
    store.add_learning_candidates(["Antigravity"])
    rows2 = store._get_conn().execute(
        "SELECT original_text, occurrences FROM dictionary_learning_candidates WHERE original_text = 'Antigravity'"
    ).fetchall()
    assert rows2[0]["occurrences"] == 2
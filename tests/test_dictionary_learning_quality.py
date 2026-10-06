"""Regressions for conservative, record-bounded vocabulary learning."""
from __future__ import annotations

from pathlib import Path

import pytest

from voice_flow.storage import StorageEngine


@pytest.fixture
def store(tmp_path: Path) -> StorageEngine:
    return StorageEngine(str(tmp_path / "learning.db"))


def test_one_raw_final_pair_does_not_activate_ordinary_titlecase_words(store):
    phrase = "Feature Fix Perfect Task Cancel Welcome Garbage"
    store.add_dictation(phrase, phrase, status="success")

    assert store.get_dictionary_words() == []
    assert store.get_lexicon_suggestions() == []


def test_repeated_raw_term_autoactivates_only_after_three_separate_successes(store):
    for _ in range(2):
        store.add_dictation("HyperKube HyperKube is useful", "HyperKube is useful", status="success")
    assert store.get_dictionary_words() == []
    assert store.get_lexicon_suggestions() == []

    store.add_dictation("HyperKube is useful", "HyperKube is useful", status="success")
    assert "HyperKube" in store.get_dictionary_words()
    assert store.get_lexicon_suggestions() == []
    assert next(row for row in store.get_dictionary_entries() if row["word"] == "HyperKube")["category"] == "Learned"


def test_failed_dictations_and_disabled_auto_learning_do_not_accumulate(store):
    for _ in range(3):
        store.add_dictation("HyperKube", "HyperKube", status="transcription_failed")
    assert store.get_lexicon_suggestions() == []

    store.save_setting("dictionary_auto_learning_enabled", "false")
    for _ in range(3):
        store.add_dictation("HyperKube", "HyperKube", status="success")
    assert store.get_lexicon_suggestions() == []


def test_learning_uses_raw_term_and_never_polisher_invention(store):
    for _ in range(3):
        store.add_dictation("we use a library", "We use HyperKube", status="success")
    assert store.get_lexicon_suggestions() == []


def test_deleted_and_ignored_terms_are_not_relearned(store):
    store.save_setting("dictionary_deleted_terms", ["HyperKube"])
    for _ in range(3):
        store.add_dictation("HyperKube is useful", "HyperKube is useful", status="success")
    assert store.get_lexicon_suggestions() == []

    assert store.add_dictionary_word("HyperKube", category="Auto-Captured")
    assert store.ignore_dictionary_word("HyperKube")
    assert "HyperKube" not in store.get_dictionary_words()
    assert store.get_lexicon_suggestions() == []


def test_repeated_use_atomically_activates_term_and_heard_as_correction(store):
    for _ in range(3):
        store.record_lexicon_candidate("Kubernetes", "cuber netties", source="correction")
    assert "Kubernetes" in store.get_dictionary_words()
    assert store.get_lexicon_suggestions() == []
    correction = store.get_dictionary_corrections()
    assert [(row["wrong_text"], row["correct_text"]) for row in correction] == [
        ("cuber netties", "Kubernetes")
    ]


def test_conflicting_heard_as_correction_keeps_candidate_pending(store):
    store.add_dictionary_correction("cuber netties", "Another Term")
    for _ in range(3):
        store.record_lexicon_candidate("Kubernetes", "cuber netties", source="correction")
    assert store.get_lexicon_suggestions() == []
    assert "Kubernetes" not in store.get_dictionary_words()
    with store._get_conn_ctx() as conn:
        candidate = conn.execute(
            "SELECT evidence, state FROM lexicon_candidates WHERE term = 'Kubernetes'"
        ).fetchone()
    assert (candidate["evidence"], candidate["state"]) == (3, "candidate")


def test_autoactivation_storage_failure_keeps_candidate_internal(store, monkeypatch):
    assert not store.record_lexicon_candidate("Kubernetes", "cuber netties", source="correction")
    assert not store.record_lexicon_candidate("Kubernetes", "cuber netties", source="correction")
    monkeypatch.setattr(store, "_add_dictionary_entry_conn", lambda *args, **kwargs: False)

    assert not store.record_lexicon_candidate("Kubernetes", "cuber netties", source="correction")
    with store._get_conn_ctx() as conn:
        candidate = conn.execute(
            "SELECT evidence, state FROM lexicon_candidates WHERE term = 'Kubernetes'"
        ).fetchone()
    assert (candidate["evidence"], candidate["state"]) == (3, "candidate")
    assert store.get_dictionary_words() == []


def test_correction_candidate_rejects_common_words_and_noise(store):
    assert not store.record_lexicon_candidate("Perfect", "perfect", source="correction")
    assert not store.record_lexicon_candidate("Feature", "feature", source="correction")
    assert store.get_lexicon_suggestions() == []


def test_numeric_dates_do_not_qualify_and_lowercase_jargon_can(store):
    for _ in range(3):
        store.add_dictation("2026 kubernetes", "2026 kubernetes", status="success")
    assert "kubernetes" in store.get_dictionary_words()
    assert store.get_lexicon_suggestions() == []


@pytest.mark.parametrize("term", [
    "Face", "Best", "While", "Natural", "Models", "Book", "Notebook", "Product",
    "Policing", "Speech", "Insights", "Style", "Animation", "Engine", "Generation",
    "Floating", "Global", "Integrity", "Providers", "Creator", "Control",
    "third-party", "in-depth", "race-to-the-bottom", "pre-release", "red-teaming",
    "world-class", "back-end", "multi-language", "hard-coded", "human-like",
    "anti-gravity", "sub-agents", "end-to-end", "re-log", "pre-made", "pop-up",
    "speech-to-text", "self-driving", "non-technical", "human.1", "sandbox.2",
    "high-risk3", "4th", "10th", "1.5x", "9th", "9-hour", "10s", "6PM",
    "September", "Monday", "minutes",
])
def test_common_ui_hyphenated_and_numeric_looking_terms_are_not_useful(term):
    from voice_flow.vocabulary_learning import is_useful_term

    assert not is_useful_term(term, allow_sentence_initial=True)


@pytest.mark.parametrize("term", [
    "HyperKube", "Kubernetes", "LangGraph", "GitHub", "NVIDIA", "GPT-5.6",
    "Qwen3.5", "Cloud-Code", "X-Zic", "Custom-SDK",
    "vSphere", "macOS", "Anthropic", "Microsoft", "Claude", "Amazon", "Tesla",
    "Joey", "Abdul", "Priyanka", "kubernetes", "postgresql", "scikit-learn",
])
def test_known_technical_terms_brands_and_names_remain_learnable(term):
    from voice_flow.vocabulary_learning import is_useful_term

    assert is_useful_term(term, allow_sentence_initial=True)


def test_manual_add_promotes_learned_word_to_personal(store):
    for _ in range(3):
        store.add_dictation("HyperKube", "HyperKube", status="success")
    assert next(row for row in store.get_dictionary_entries() if row["word"] == "HyperKube")["category"] == "Learned"

    assert store.add_dictionary_word("HyperKube")
    assert next(row for row in store.get_dictionary_entries() if row["word"] == "HyperKube")["category"] == "Personal"


def test_manual_correction_promotes_learned_canonical_term_to_personal(store):
    for _ in range(3):
        store.add_dictation("HyperKube", "HyperKube", status="success")
    assert store.add_dictionary_correction("hyper cube", "HyperKube")
    assert next(row for row in store.get_dictionary_entries() if row["word"] == "HyperKube")["category"] == "Personal"


def test_quality_migration_backfills_only_exact_auto_created_personal_timestamp(store):
    exact = "2026-10-06T12:00:00"
    manual = "2026-10-06T12:00:00.123456"
    with store._get_conn_ctx() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('history_vocab_seeded_v5', 'true', ?)", (exact,))
        conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('vocabulary_quality_migration_v1', 'false', ?)", (exact,))
        for term, created_at in (("HyperKube", exact), ("Best", manual)):
            cursor = conn.execute("INSERT INTO dictionary (word, category, created_at) VALUES (?, 'Personal', ?)", (term, created_at))
            conn.execute("INSERT INTO dictionary_keys (normalized, dictionary_id) VALUES (?, ?)", (term.casefold(), cursor.lastrowid))
        conn.execute(
            "INSERT INTO lexicon_candidates (term, variant, evidence, state, source, created_at, updated_at) "
            "VALUES ('HyperKube', '', 3, 'active', 'usage-history', ?, ?)",
            (exact, exact),
        )
        conn.execute(
            "INSERT INTO lexicon_candidates (term, variant, evidence, state, source, created_at, updated_at) "
            "VALUES ('Best', '', 3, 'active', 'usage-history', ?, ?)",
            (exact, exact),
        )

    store.migrate_vocabulary_quality()
    categories = {row["word"]: row["category"] for row in store.get_dictionary_entries(include_auto=True)}
    assert categories["HyperKube"] == "Learned"
    assert categories["Best"] == "Personal"


def test_quality_migration_demotes_only_unqualified_legacy_learned_rows(store):
    now = "2026-10-06T12:00:00"
    with store._get_conn_ctx() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('history_vocab_seeded_v5', 'true', ?)", (now,))
        conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('vocabulary_quality_migration_v1', 'false', ?)", (now,))
        for term, category, source in [
            ("Best", "Learned", "usage-history"),
            ("HyperKube", "Learned", "usage-history"),
            ("OriginalPersonal", "Personal", "usage-history"),
        ]:
            cursor = conn.execute("INSERT INTO dictionary (word, category, created_at) VALUES (?, ?, ?)", (term, category, now))
            conn.execute("INSERT INTO dictionary_keys (normalized, dictionary_id) VALUES (?, ?)", (term.casefold(), cursor.lastrowid))
            if term != "OriginalPersonal":
                conn.execute(
                    "INSERT INTO lexicon_candidates (term, variant, evidence, state, source, created_at, updated_at) "
                    "VALUES (?, '', 3, 'active', ?, ?, ?)",
                    (term, source, now, now),
                )

    assert store.migrate_vocabulary_quality() == 1
    entries = {row["word"]: row["category"] for row in store.get_dictionary_entries(include_auto=True)}
    assert entries["Best"] == "Auto-Captured"
    assert entries["HyperKube"] == "Learned"
    assert entries["OriginalPersonal"] == "Personal"
    assert "Best" not in store.get_dictionary_words()
    assert "HyperKube" in store.get_dictionary_words()
    with store._get_conn_ctx() as conn:
        row = conn.execute("SELECT evidence, state FROM lexicon_candidates WHERE term='Best'").fetchone()
    assert (row["evidence"], row["state"]) == (0, "candidate")


def test_disabled_learning_also_blocks_model_derived_candidate_capture(store):
    store.save_setting("dictionary_auto_learning_enabled", "false")
    for _ in range(3):
        assert not store.record_lexicon_candidate("Kubernetes", "cuber netties", source="correction")
    assert store.get_lexicon_suggestions() == []


def test_correction_learning_requires_three_distinct_successful_history_ids(store):
    first = store.add_dictation("cuber netties", "Kubernetes", status="success")
    assert not store.record_lexicon_candidate("Kubernetes", "cuber netties", history_id=first.id)
    # A retry for the same persisted dictation is not independent evidence.
    assert not store.record_lexicon_candidate("Kubernetes", "cuber netties", history_id=first.id)
    assert "Kubernetes" not in store.get_dictionary_words()

    second = store.add_dictation("cuber netties", "Kubernetes", status="success")
    assert not store.record_lexicon_candidate("Kubernetes", "cuber netties", history_id=second.id)
    failed = store.add_dictation("cuber netties", "Kubernetes", status="transcription_failed")
    assert not store.record_lexicon_candidate("Kubernetes", "cuber netties", history_id=failed.id)
    assert "Kubernetes" not in store.get_dictionary_words()

    third = store.add_dictation("cuber netties", "Kubernetes", status="success")
    assert store.record_lexicon_candidate("Kubernetes", "cuber netties", history_id=third.id)
    assert "Kubernetes" in store.get_dictionary_words()
    assert [(row["wrong_text"], row["correct_text"]) for row in store.get_dictionary_corrections()] == [
        ("cuber netties", "Kubernetes")
    ]


def test_correction_history_id_must_match_raw_and_polished_text(store):
    row = store.add_dictation("ordinary words", "Kubernetes", status="success")
    assert not store.record_lexicon_candidate("Kubernetes", "cuber netties", history_id=row.id)
    assert "Kubernetes" not in store.get_dictionary_words()


def test_correction_history_requires_whole_phrase_matches(store):
    row = store.add_dictation("island graph", "HyperKubePro", status="success")
    assert not store.record_lexicon_candidate("HyperKube", "land graph", history_id=row.id)
    assert "HyperKube" not in store.get_dictionary_words()


def test_history_migration_uses_raw_repeats_and_preserves_legacy_row(store):
    assert store.add_dictionary_word("GitHub", category="Auto-Captured")
    with store._get_conn_ctx() as conn:
        for _ in range(3):
            conn.execute(
                "INSERT INTO history (timestamp, raw_text, polished_text, status) "
                "VALUES (datetime('now'), ?, ?, 'success')",
                ("Use GitHub every day", "Use InventedCloud every day"),
            )
        conn.execute("DELETE FROM settings WHERE key = 'history_vocab_seeded_v5'")

    store.migrate_learned_vocabulary()
    assert "GitHub" in store.get_dictionary_words()
    assert "InventedCloud" not in store.get_dictionary_words()
    assert store.get_lexicon_suggestions() == []
    legacy = [item for item in store.get_dictionary_entries(include_auto=True) if item["word"] == "GitHub"]
    assert legacy and legacy[0]["category"] == "Learned"


def test_remove_dictionary_term_also_removes_only_its_heard_as_correction(store):
    assert store.add_dictionary_entry("Kubernetes", "cuber netties")
    store.add_dictionary_correction("sorta neat", "SortaNet")
    store.add_snippet("sig", "Keep this snippet")
    with store._get_conn_ctx() as conn:
        correction_id = conn.execute(
            "SELECT id FROM dictionary_corrections WHERE wrong_text = ?", ("cuber netties",)
        ).fetchone()["id"]
        normalized = "cuber netties"

    assert store.remove_dictionary_word("Kubernetes")
    assert [(row["wrong_text"], row["correct_text"]) for row in store.get_dictionary_corrections()] == [
        ("sorta neat", "SortaNet")
    ]
    assert [row["trigger"] for row in store.get_snippets()] == ["sig"]
    with store._get_conn_ctx() as conn:
        assert conn.execute(
            "SELECT 1 FROM correction_keys WHERE normalized = ?", (normalized,)
        ).fetchone() is None
        assert conn.execute(
            "SELECT 1 FROM correction_keys WHERE correction_id = ?", (correction_id,)
        ).fetchone() is None

    # A removed heard-as correction and its canonical term cannot be learned back.
    for _ in range(3):
        store.add_dictation("Kubernetes", "Kubernetes", status="success")
    assert "Kubernetes" not in store.get_dictionary_words()
    assert all(row["term"] != "Kubernetes" for row in store.get_lexicon_suggestions())


def test_rename_updates_attached_correction_and_revision(store):
    assert store.add_dictionary_entry("Kubernetes", "cuber netties")
    store.add_dictionary_correction("sorta neat", "SortaNet")
    revision_before = store.get_dictionary_snapshot()[0]

    assert store.update_dictionary_word("Kubernetes", "KubeRnetes")

    corrections = {row["wrong_text"]: row["correct_text"] for row in store.get_dictionary_corrections()}
    assert corrections == {"cuber netties": "KubeRnetes", "sorta neat": "SortaNet"}
    assert "KubeRnetes" in store.get_dictionary_words()
    assert "Kubernetes" not in store.get_dictionary_words()
    assert store.get_dictionary_snapshot()[0] > revision_before


def test_rename_collision_rolls_back_attached_correction(store):
    assert store.add_dictionary_entry("Kubernetes", "cuber netties")
    assert store.add_dictionary_word("ExistingTerm")

    assert not store.update_dictionary_word("Kubernetes", "ExistingTerm")
    corrections = {row["wrong_text"]: row["correct_text"] for row in store.get_dictionary_corrections()}
    assert corrections == {"cuber netties": "Kubernetes"}
    assert "Kubernetes" in store.get_dictionary_words()
    assert "ExistingTerm" in store.get_dictionary_words()


def test_vocabulary_extraction_has_a_fixed_input_budget():
    from voice_flow.vocabulary_learning import extract_vocabulary_candidates

    assert extract_vocabulary_candidates("a " * 6_000 + " HyperKube") == []


def test_history_migration_bounds_each_raw_record_before_extracting(store):
    with store._get_conn_ctx() as conn:
        for _ in range(3):
            conn.execute(
                "INSERT INTO history (timestamp, raw_text, polished_text, status) "
                "VALUES (datetime('now'), ?, ?, 'success')",
                ("a " * 6_000 + " HyperKube", "HyperKube"),
            )
        conn.execute("DELETE FROM settings WHERE key = 'history_vocab_seeded_v5'")

    store.auto_seed_history_vocabulary()
    assert "HyperKube" not in store.get_dictionary_words()


def test_v5_migration_discards_unvalidated_legacy_correction_counts(store):
    with store._get_conn_ctx() as conn:
        conn.execute(
            "INSERT INTO lexicon_candidates "
            "(term, variant, evidence, state, source, created_at, updated_at) "
            "VALUES ('Kubernetes', 'cuber netties', 3, 'suggested', 'correction', 'now', 'now')"
        )
        conn.execute("DELETE FROM settings WHERE key = 'history_vocab_seeded_v5'")

    store.auto_seed_history_vocabulary()
    assert "Kubernetes" not in store.get_dictionary_words()
    assert store.get_lexicon_suggestions() == []
    with store._get_conn_ctx() as conn:
        row = conn.execute(
            "SELECT evidence, state FROM lexicon_candidates WHERE term = 'Kubernetes'"
        ).fetchone()
    assert (row["evidence"], row["state"]) == (0, "candidate")


def test_v5_migration_rebuilds_legacy_evidence_from_successful_raw_records(store):
    with store._get_conn_ctx() as conn:
        conn.execute(
            "INSERT INTO lexicon_candidates "
            "(term, variant, evidence, state, source, created_at, updated_at) "
            "VALUES ('Kubernetes', '', 99, 'suggested', 'usage-history', 'now', 'now')"
        )
        conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('history_vocab_seeded_v4', 'true', 'now')")
        for _ in range(2):
            conn.execute(
                "INSERT INTO history (timestamp, raw_text, polished_text, status) "
                "VALUES (datetime('now'), 'Kubernetes', 'Kubernetes', 'success')"
            )
        for _ in range(3):
            conn.execute(
                "INSERT INTO history (timestamp, raw_text, polished_text, status) "
                "VALUES (datetime('now'), 'HyperKube', 'HyperKube', 'success')"
            )
        conn.execute("DELETE FROM settings WHERE key = 'history_vocab_seeded_v5'")

    store.auto_seed_history_vocabulary()
    assert "HyperKube" in store.get_dictionary_words()
    assert "Kubernetes" not in store.get_dictionary_words()
    assert store.get_lexicon_suggestions() == []
    with store._get_conn_ctx() as conn:
        row = conn.execute("SELECT evidence, state FROM lexicon_candidates WHERE term='Kubernetes'").fetchone()
    assert (row["evidence"], row["state"]) == (2, "candidate")


def test_disabled_setting_defers_v5_migration_until_enabled(store):
    with store._get_conn_ctx() as conn:
        for _ in range(3):
            conn.execute(
                "INSERT INTO history (timestamp, raw_text, polished_text, status) "
                "VALUES (datetime('now'), 'HyperKube', 'HyperKube', 'success')"
            )
        conn.execute("DELETE FROM settings WHERE key = 'history_vocab_seeded_v5'")
    store.save_setting("dictionary_auto_learning_enabled", False)
    assert store.migrate_learned_vocabulary() == 0
    assert not store.get_setting("lexicon_migration_v2", False)
    assert "HyperKube" not in store.get_dictionary_words()

    store.save_setting("dictionary_auto_learning_enabled", True)
    assert store.migrate_learned_vocabulary() == 1
    assert "HyperKube" in store.get_dictionary_words()

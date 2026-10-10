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


def test_historyless_candidate_calls_cannot_activate_term_or_correction(store):
    for _ in range(3):
        store.record_lexicon_candidate("Kubernetes", "cuber netties", source="correction")
    assert "Kubernetes" not in store.get_dictionary_words()
    assert store.get_lexicon_suggestions() == []
    assert store.get_dictionary_corrections() == []
    with store._get_conn_ctx() as conn:
        candidate = conn.execute(
            "SELECT evidence, state FROM lexicon_candidates WHERE term = 'Kubernetes'"
        ).fetchone()
    assert (candidate["evidence"], candidate["state"]) == (3, "candidate")


@pytest.mark.parametrize('app_name,delivery', [
    ('Video Flow', 'vf-example-video-job'),
    ('Audio Flow', 'af-example-summary-job'),
    ('Editor', 'ready_to_paste'),
    ('Editor', ''),
])
def test_source_and_unpasted_history_cannot_teach_dictionary(store, app_name, delivery):
    for _ in range(3):
        store.add_dictation('We use HyperKube and LangGraph', 'We use HyperKube and LangGraph',
                            app_name=app_name, status='success', insertion_status=delivery)
    assert store.get_dictionary_words() == []
    assert store.get_lexicon_suggestions() == []


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
    "Qwen3.5",
    "vSphere", "macOS", "Anthropic", "Microsoft", "Claude", "Amazon", "Tesla",
    "Joey", "Abdul", "Priyanka", "kubernetes", "postgresql", "scikit-learn",
])
def test_known_technical_terms_brands_and_names_remain_learnable(term):
    from voice_flow.vocabulary_learning import is_useful_term

    assert is_useful_term(term, allow_sentence_initial=True)


def test_unseen_name_and_technical_term_require_credible_context(store):
    from voice_flow.vocabulary_learning import extract_vocabulary_candidates

    assert extract_vocabulary_candidates("QuantaMesh appeared beside Reliability") == []
    assert extract_vocabulary_candidates("please call Zareena tomorrow") == ["Zareena"]
    assert extract_vocabulary_candidates("we use QuantaMesh for routing") == ["QuantaMesh"]
    assert extract_vocabulary_candidates("a problem with Reliability and work with Estimates") == []
    assert extract_vocabulary_candidates("company named ZVRX. Reliability matters") == ["ZVRX"]
    for _ in range(3):
        store.add_dictation("please call Zareena tomorrow", "Please call Zareena tomorrow")
        store.add_dictation("we use QuantaMesh for routing", "We use QuantaMesh for routing")
        store.add_dictation("the company named ZVRX", "The company named ZVRX")
    assert {"Zareena", "QuantaMesh", "ZVRX"}.issubset(set(store.get_dictionary_words()))


def test_generic_roles_do_not_learn_from_weak_name_cues(store):
    phrases = (
        "Please email Support and call Customers.",
        "We spoke with Customers about Shipping.",
        "Please call Supporting and email Delivering.",
        "We spoke with Supported about Shipped orders.",
    )
    for _ in range(3):
        for phrase in phrases:
            store.add_dictation(phrase, phrase, status="success", insertion_status="pasted")
        store.add_dictation(
            "I met with Zarriva about the contract.",
            "I met with Zarriva about the contract.",
            status="success",
            insertion_status="pasted",
        )
    assert "Zarriva" in store.get_dictionary_words()
    assert not (
        {"Support", "Customers", "Shipping", "Supporting", "Delivering", "Supported", "Shipped"}
        & set(store.get_dictionary_words())
    )


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


def test_v2_quality_migration_preserves_all_personal_rows(store):
    exact = "2026-10-06T12:00:00"
    manual = "2026-10-06T12:00:00.123456"
    with store._get_conn_ctx() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('history_vocab_seeded_v5', 'true', ?)", (exact,))
        conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('vocabulary_quality_migration_v1', 'true', ?)", (exact,))
        conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('vocabulary_quality_migration_v2', 'false', ?)", (exact,))
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
    assert categories["HyperKube"] == "Personal"
    assert categories["Best"] == "Personal"


def test_quality_migration_demotes_only_unqualified_legacy_learned_rows(store):
    now = "2026-10-06T12:00:00"
    with store._get_conn_ctx() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('history_vocab_seeded_v5', 'true', ?)", (now,))
        conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('vocabulary_quality_migration_v1', 'true', ?)", (now,))
        conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('vocabulary_quality_migration_v2', 'false', ?)", (now,))
        for term, category, source in [
            ("Best", "Learned", "usage-history"),
            ("HyperKube", "Learned", "usage-history"),
            ("Kubernetes", "Learned", "usage-history"),
            ("OriginalPersonal", "Personal", "usage-history"),
        ]:
            cursor = conn.execute("INSERT INTO dictionary (word, category, created_at) VALUES (?, ?, ?)", (term, category, now))
            conn.execute("INSERT INTO dictionary_keys (normalized, dictionary_id) VALUES (?, ?)", (term.casefold(), cursor.lastrowid))
            if term != "OriginalPersonal":
                candidate_id = conn.execute(
                    "INSERT INTO lexicon_candidates (term, variant, evidence, state, source, created_at, updated_at) "
                    "VALUES (?, '', 3, 'active', ?, ?, ?)",
                    (term, source, now, now),
                ).lastrowid
                if term == "HyperKube":
                    for index in range(3):
                        history_id = conn.execute(
                            "INSERT INTO history "
                            "(timestamp, raw_text, polished_text, status, insertion_status) "
                            "VALUES (?, 'HyperKube', 'HyperKube', 'success', 'pasted')",
                            (f"2026-10-06T12:00:0{index}",),
                        ).lastrowid
                        conn.execute(
                            "INSERT INTO lexicon_candidate_observations (candidate_id, history_id) VALUES (?, ?)",
                            (candidate_id, history_id),
                        )

    assert store.migrate_vocabulary_quality() == 2
    entries = {row["word"]: row["category"] for row in store.get_dictionary_entries(include_auto=True)}
    assert entries["Best"] == "Auto-Captured"
    assert entries["HyperKube"] == "Learned"
    assert entries["Kubernetes"] == "Auto-Captured"
    assert entries["OriginalPersonal"] == "Personal"
    assert "Best" not in store.get_dictionary_words()
    assert "HyperKube" in store.get_dictionary_words()
    with store._get_conn_ctx() as conn:
        row = conn.execute("SELECT evidence, state FROM lexicon_candidates WHERE term='Best'").fetchone()
    assert (row["evidence"], row["state"]) == (0, "retired")


def test_v2_quality_migration_reloads_engine_and_preserves_manual_data(store):
    from voice_flow.dictionary import DictionaryEngine

    assert store.add_dictionary_word("KeepMe", category="Personal")
    assert store.add_dictionary_correction("keep me", "KeepMe")
    assert store.add_snippet("sig", "Manual signature")
    history_ids = []
    for _ in range(3):
        record = store.add_dictation("ZetaMesh", "ZetaMesh")
        history_ids.append(record.id)
    now = "2026-10-06T12:00:00"
    with store._get_conn_ctx() as conn:
        cursor = conn.execute(
            "INSERT INTO dictionary (word, category, created_at) VALUES ('ZetaMesh', 'Learned', ?)",
            (now,),
        )
        conn.execute(
            "INSERT INTO dictionary_keys (normalized, dictionary_id) VALUES ('zetamesh', ?)",
            (cursor.lastrowid,),
        )
        phantom = conn.execute(
            "INSERT INTO dictionary (word, category, created_at) VALUES ('PhantomStack', 'Learned', ?)",
            (now,),
        ).lastrowid
        conn.execute(
            "INSERT INTO dictionary_keys (normalized, dictionary_id) VALUES ('phantomstack', ?)",
            (phantom,),
        )
        conn.execute(
            "INSERT INTO lexicon_candidates "
            "(term, variant, evidence, state, source, created_at, updated_at) "
            "VALUES ('PhantomStack', '', 3, 'active', 'usage-history', ?, ?)",
            (now, now),
        )
        candidate = conn.execute(
            "INSERT INTO lexicon_candidates "
            "(term, variant, evidence, state, source, created_at, updated_at) "
            "VALUES ('ZetaMesh', '', 3, 'active', 'usage-history', ?, ?)",
            (now, now),
        ).lastrowid
        conn.executemany(
            "INSERT INTO lexicon_candidate_observations (candidate_id, history_id) VALUES (?, ?)",
            [(candidate, history_id) for history_id in history_ids],
        )
        correction_candidate = conn.execute(
            "INSERT INTO lexicon_candidates "
            "(term, variant, evidence, state, source, created_at, updated_at) "
            "VALUES ('ZetaMesh', 'zeta mesh', 3, 'active', 'correction', ?, ?)",
            (now, now),
        ).lastrowid
        correction_id = conn.execute(
            "INSERT INTO dictionary_corrections "
            "(wrong_text, correct_text, automatic_candidate_id, created_at, updated_at) "
            "VALUES ('zeta mesh', 'ZetaMesh', ?, ?, ?)",
            (correction_candidate, now, now),
        ).lastrowid
        conn.execute(
            "INSERT INTO correction_keys (normalized, correction_id) VALUES ('zeta mesh', ?)",
            (correction_id,),
        )
        conn.execute(
            "INSERT INTO lexicon_candidates "
            "(term, variant, evidence, state, source, created_at, updated_at) "
            "VALUES ('ZetaMesh', 'legacy zeta', 3, 'active', 'correction', ?, ?)",
            (now, now),
        )
        legacy_correction = conn.execute(
            "INSERT INTO dictionary_corrections "
            "(wrong_text, correct_text, created_at, updated_at) "
            "VALUES ('legacy zeta', 'ZetaMesh', ?, '2026-10-06T12:30:00')",
            (now,),
        ).lastrowid
        conn.execute(
            "INSERT INTO correction_keys (normalized, correction_id) VALUES ('legacy zeta', ?)",
            (legacy_correction,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) "
            "VALUES ('vocabulary_quality_migration_v2', 'false', ?)",
            (now,),
        )

    engine = DictionaryEngine(store)
    revision_before = store.get_dictionary_revision()
    assert {"ZetaMesh", "PhantomStack"}.issubset(set(engine.get_stt_hint_terms()))
    assert store.migrate_vocabulary_quality() == 2
    assert store.get_dictionary_revision() > revision_before
    assert "PhantomStack" not in engine.get_stt_hint_terms()
    # The explicitly edited legacy heard-as mapping remains active and keeps
    # its target as an STT hint even though the automatic word row retired.
    assert "ZetaMesh" in engine.get_stt_hint_terms()
    assert "KeepMe" in store.get_dictionary_words()
    assert [(row["wrong_text"], row["correct_text"]) for row in store.get_dictionary_corrections()] == [
        ("keep me", "KeepMe"),
        ("legacy zeta", "ZetaMesh"),
    ]
    assert [row["trigger"] for row in store.get_snippets()] == ["sig"]
    with store._get_conn_ctx() as conn:
        row = conn.execute(
            "SELECT evidence, state, evidence_history_floor FROM lexicon_candidates "
            "WHERE term = 'ZetaMesh'"
        ).fetchone()
        retained_correction = conn.execute(
            "SELECT automatic_candidate_id FROM dictionary_corrections WHERE wrong_text = 'zeta mesh'"
        ).fetchone()
        edited_legacy = conn.execute(
            "SELECT automatic_candidate_id FROM dictionary_corrections WHERE wrong_text = 'legacy zeta'"
        ).fetchone()
    assert (row["evidence"], row["state"], row["evidence_history_floor"]) == (
        0, "retired", max(history_ids)
    )
    assert retained_correction["automatic_candidate_id"] == correction_candidate
    assert edited_legacy["automatic_candidate_id"] is None

    # Retired observations are retained but cannot count again. Fresh genuine
    # technical contexts may earn the term anew without a deletion tombstone.
    for _ in range(3):
        store.add_dictation("we use ZetaMesh for routing", "We use ZetaMesh for routing")
    assert "ZetaMesh" in store.get_dictionary_words()


@pytest.mark.parametrize("v2_complete", [False, True])
def test_correction_audit_is_independent_and_runs_after_existing_v2(store, v2_complete):
    """A valid canonical word cannot shelter an unsupported automatic rewrite."""
    now = "2026-10-06T12:00:00"
    with store._get_conn_ctx() as conn:
        dictionary_id = conn.execute(
            "INSERT INTO dictionary (word, category, created_at) VALUES ('OpenAI', 'Learned', ?)",
            (now,),
        ).lastrowid
        conn.execute(
            "INSERT INTO dictionary_keys (normalized, dictionary_id) VALUES ('openai', ?)",
            (dictionary_id,),
        )
        usage_candidate = conn.execute(
            "INSERT INTO lexicon_candidates "
            "(term, variant, evidence, state, source, created_at, updated_at) "
            "VALUES ('OpenAI', '', 3, 'active', 'usage-history', ?, ?)",
            (now, now),
        ).lastrowid
        for index in range(3):
            history_id = conn.execute(
                "INSERT INTO history "
                "(timestamp, raw_text, polished_text, status, insertion_status) "
                "VALUES (?, 'we use OpenAI for routing', 'We use OpenAI for routing', "
                "'success', 'pasted')",
                (f"2026-10-06T12:00:0{index}",),
            ).lastrowid
            conn.execute(
                "INSERT INTO lexicon_candidate_observations (candidate_id, history_id) "
                "VALUES (?, ?)",
                (usage_candidate, history_id),
            )

        correction_candidates = {}
        for variant in ("open aye", "open legacy", "open manual"):
            correction_candidates[variant] = conn.execute(
                "INSERT INTO lexicon_candidates "
                "(term, variant, evidence, state, source, created_at, updated_at) "
                "VALUES ('OpenAI', ?, 3, 'active', 'correction', ?, ?)",
                (variant, now, now),
            ).lastrowid

        explicit_id = conn.execute(
            "INSERT INTO dictionary_corrections "
            "(wrong_text, correct_text, automatic_candidate_id, created_at, updated_at) "
            "VALUES ('open aye', 'OpenAI', ?, ?, ?)",
            (correction_candidates["open aye"], now, now),
        ).lastrowid
        legacy_id = conn.execute(
            "INSERT INTO dictionary_corrections "
            "(wrong_text, correct_text, created_at, updated_at) "
            "VALUES ('open legacy', 'OpenAI', ?, ?)",
            (now, now),
        ).lastrowid
        manual_id = conn.execute(
            "INSERT INTO dictionary_corrections "
            "(wrong_text, correct_text, created_at, updated_at) "
            "VALUES ('open manual', 'OpenAI', ?, ?)",
            ("2026-10-06T12:00:00.123456", "2026-10-06T12:00:00.123456"),
        ).lastrowid
        conn.executemany(
            "INSERT INTO correction_keys (normalized, correction_id) VALUES (?, ?)",
            (("open aye", explicit_id), ("open legacy", legacy_id), ("open manual", manual_id)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES "
            "('vocabulary_quality_migration_v2', ?, ?)",
            ("true" if v2_complete else "false", now),
        )
        conn.execute(
            "DELETE FROM settings WHERE key = 'vocabulary_correction_quality_migration_v3'"
        )

    revision_before = store.get_dictionary_revision()
    assert store.migrate_vocabulary_quality() == 0
    assert store.get_dictionary_revision() > revision_before
    assert "OpenAI" in store.get_dictionary_words()
    assert [(row["wrong_text"], row["correct_text"]) for row in store.get_dictionary_corrections()] == [
        ("open manual", "OpenAI")
    ]
    assert [row["wrong_text"] for row in store.get_dictionary_snapshot()[2]] == ["open manual"]

    with store._get_conn_ctx() as conn:
        states = {
            row["variant"]: (row["evidence"], row["state"])
            for row in conn.execute(
                "SELECT variant, evidence, state FROM lexicon_candidates "
                "WHERE term = 'OpenAI' AND variant != ''"
            )
        }
        owners = {
            row["wrong_text"]: row["automatic_candidate_id"]
            for row in conn.execute(
                "SELECT wrong_text, automatic_candidate_id FROM dictionary_corrections"
            )
        }
    assert states == {
        "open aye": (0, "retired"),
        "open legacy": (0, "retired"),
        "open manual": (0, "retired"),
    }
    assert owners["open aye"] == correction_candidates["open aye"]
    assert owners["open legacy"] == correction_candidates["open legacy"]
    assert owners["open manual"] is None
    assert store.get_setting("vocabulary_correction_quality_migration_v3", False)

    revision_after = store.get_dictionary_revision()
    assert store.migrate_vocabulary_quality() == 0
    assert store.get_dictionary_revision() == revision_after


def test_quality_migration_preserves_ignore_tombstone(store):
    now = "2026-10-06T12:00:00"
    with store._get_conn_ctx() as conn:
        conn.execute(
            "INSERT INTO dictionary (word, category, created_at) VALUES ('NoiseName', 'Learned', ?)",
            (now,),
        )
        conn.execute(
            "INSERT INTO lexicon_candidates "
            "(term, variant, evidence, state, source, created_at, updated_at) "
            "VALUES ('NoiseName', '', 2, 'ignored', 'usage-history', ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) "
            "VALUES ('vocabulary_quality_migration_v2', 'false', ?)",
            (now,),
        )
    assert store.migrate_vocabulary_quality() == 1
    with store._get_conn_ctx() as conn:
        state = conn.execute(
            "SELECT state FROM lexicon_candidates WHERE term = 'NoiseName'"
        ).fetchone()["state"]
    assert state == "ignored"


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


def test_legacy_observation_ids_must_still_match_three_successful_pastes(store):
    old_unpasted = [
        store.add_dictation("HyperKube", "HyperKube", insertion_status="ready_to_paste")
        for _ in range(2)
    ]
    mismatched = store.add_dictation("ordinary words", "ordinary words")
    with store._get_conn_ctx() as conn:
        deleted_id = conn.execute(
            "INSERT INTO history (timestamp, raw_text, polished_text, status, insertion_status) "
            "VALUES ('old', 'HyperKube', 'HyperKube', 'success', 'pasted')"
        ).lastrowid
        candidate_id = conn.execute(
            "INSERT INTO lexicon_candidates "
            "(term, variant, evidence, state, source, created_at, updated_at) "
            "VALUES ('HyperKube', '', 4, 'candidate', 'usage-history', 'old', 'old')"
        ).lastrowid
        conn.executemany(
            "INSERT INTO lexicon_candidate_observations (candidate_id, history_id) VALUES (?, ?)",
            [
                (candidate_id, old_unpasted[0].id),
                (candidate_id, old_unpasted[1].id),
                (candidate_id, mismatched.id),
                (candidate_id, deleted_id),
            ],
        )
        conn.execute("DELETE FROM history WHERE id = ?", (deleted_id,))
        conn.execute("DELETE FROM settings WHERE key = 'vocabulary_quality_migration_v2'")

    store.migrate_vocabulary_quality()
    for expected_evidence in (1, 2):
        store.add_dictation("HyperKube", "HyperKube", insertion_status="pasted")
        assert "HyperKube" not in store.get_dictionary_words()
        with store._get_conn_ctx() as conn:
            evidence = conn.execute(
                "SELECT evidence FROM lexicon_candidates WHERE id = ?", (candidate_id,)
            ).fetchone()["evidence"]
        assert evidence == expected_evidence

    store.add_dictation("HyperKube", "HyperKube", insertion_status="pasted")
    assert "HyperKube" in store.get_dictionary_words()


def test_observation_revalidation_bounds_history_text_in_sql(store):
    with store._get_conn_ctx() as conn:
        candidate_id = conn.execute(
            "INSERT INTO lexicon_candidates "
            "(term, variant, evidence, state, source, created_at, updated_at) "
            "VALUES ('OpenAI', 'open ai', 3, 'active', 'correction', 'now', 'now')"
        ).lastrowid
        for index in range(3):
            history_id = conn.execute(
                "INSERT INTO history "
                "(timestamp, raw_text, polished_text, status, insertion_status) "
                "VALUES (?, 'we use open ai for routing', ?, 'success', 'pasted')",
                (f"2026-10-06T12:00:0{index}", "x" * 12_001 + " OpenAI"),
            ).lastrowid
            conn.execute(
                "INSERT INTO lexicon_candidate_observations (candidate_id, history_id) "
                "VALUES (?, ?)",
                (candidate_id, history_id),
            )
        traced = []
        conn.set_trace_callback(traced.append)
        try:
            assert store._count_valid_candidate_observations_conn(
                conn, candidate_id, "OpenAI", "open ai"
            ) == 0
        finally:
            conn.set_trace_callback(None)

    evidence_query = next(
        statement.casefold()
        for statement in traced
        if "lexicon_candidate_observations" in statement.casefold()
        and "join history" in statement.casefold()
    )
    assert "substr(h.raw_text, 1, 12000)" in evidence_query
    assert "substr(h.polished_text, 1, 12000)" in evidence_query


def test_explicit_correction_claims_an_automatic_mapping_as_manual(store):
    for _ in range(3):
        row = store.add_dictation("cuber netties", "Kubernetes")
        store.record_lexicon_candidate("Kubernetes", "cuber netties", history_id=row.id)
    with store._get_conn_ctx() as conn:
        before = conn.execute(
            "SELECT automatic_candidate_id FROM dictionary_corrections "
            "WHERE wrong_text = 'cuber netties'"
        ).fetchone()
    assert before["automatic_candidate_id"] is not None

    store.add_dictionary_correction("cuber netties", "Kubernetes")
    with store._get_conn_ctx() as conn:
        after = conn.execute(
            "SELECT automatic_candidate_id FROM dictionary_corrections "
            "WHERE wrong_text = 'cuber netties'"
        ).fetchone()
    assert after["automatic_candidate_id"] is None
    assert next(
        row for row in store.get_dictionary_entries() if row["word"] == "Kubernetes"
    )["category"] == "Personal"


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

"""The saved dictionary is cleared once and ordinary history does not refill it."""
from __future__ import annotations

from pathlib import Path

from voice_flow.storage import StorageEngine


def test_saved_dictionary_text_is_cleared_once_and_history_does_not_restore_it(tmp_path: Path) -> None:
    store = StorageEngine(str(tmp_path / "dictionary-reset.db"))
    assert store.get_setting("dictionary_user_reset_v1") is True
    assert store.get_dictionary_words() == []

    with store._get_conn_ctx() as conn:
        conn.execute("DELETE FROM settings WHERE key = 'dictionary_user_reset_v1'")
        now = "2026-10-10T12:00:00"
        for word in ("Meeting", "Report"):
            cursor = conn.execute(
                "INSERT INTO dictionary (word, category, created_at) VALUES (?, 'Personal', ?)",
                (word, now),
            )
            conn.execute(
                "INSERT INTO dictionary_keys (normalized, dictionary_id) VALUES (?, ?)",
                (word.casefold(), cursor.lastrowid),
            )
        conn.execute(
            "INSERT INTO dictionary_corrections (wrong_text, correct_text, created_at, updated_at) "
            "VALUES ('hey', 'here', ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO lexicon_candidates "
            "(term, variant, evidence, state, source, created_at, updated_at) "
            "VALUES ('Meeting', '', 3, 'active', 'usage-history', ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO history (timestamp, raw_text, polished_text, status, insertion_status) "
            "VALUES (?, 'keep this history', 'keep this history', 'success', 'pasted')",
            (now,),
        )

    store.add_snippet("sig", "Keep this snippet")
    removed = store.clear_saved_dictionary_text()
    assert removed > 0
    assert store.get_dictionary_words() == []
    assert store.get_dictionary_corrections() == []
    with store._get_conn_ctx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM lexicon_candidates").fetchone()[0] == 0
        assert conn.execute("SELECT raw_text FROM history").fetchone()["raw_text"] == "keep this history"
    assert [row["trigger"] for row in store.get_snippets()] == ["sig"]
    assert store.get_setting("dictionary_user_reset_v1") is True
    assert store.get_setting("history_vocab_seeded_v5") is True

    with store._get_conn_ctx() as conn:
        conn.execute("DELETE FROM settings WHERE key = 'history_vocab_seeded_v5'")
        for index in range(3):
            conn.execute(
                "INSERT INTO history (timestamp, raw_text, polished_text, status, insertion_status) "
                "VALUES (?, 'HyperKube', 'HyperKube', 'success', 'pasted')",
                (f"2026-10-10T12:00:0{index}",),
            )
    assert store.auto_seed_history_vocabulary() == 0
    assert store.migrate_learned_vocabulary() == 0
    assert "HyperKube" not in store.get_dictionary_words()
    with store._get_conn_ctx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM history").fetchone()[0] == 4

    assert store.add_dictionary_word("OpenAI")
    assert store.clear_saved_dictionary_text() == 0
    assert "OpenAI" in store.get_dictionary_words()
    assert store.add_dictionary_word("Ada")
    assert {"Ada", "OpenAI"} <= set(store.get_dictionary_words())

"""Regressions found while reviewing dictionary persistence and final formatting."""
from types import SimpleNamespace

from voice_flow.storage import StorageEngine
from voice_flow.dictionary import DictionaryEngine


def test_rename_and_readd_survive_restart(tmp_path):
    path = str(tmp_path / "words.db")
    store = StorageEngine(path)
    assert store.add_dictionary_word("Alpha")
    store = StorageEngine(path)  # build the legacy normalized lookup
    assert store.update_dictionary_word("Alpha", "Beta")
    assert store.add_dictionary_word("Alpha")
    assert set(StorageEngine(path).get_dictionary_words()) == {"Alpha", "Beta"}


def test_legacy_stale_key_cannot_delete_a_different_live_word(tmp_path):
    path = str(tmp_path / "words.db")
    store = StorageEngine(path)
    assert store.add_dictionary_word("Alpha")
    store = StorageEngine(path)
    with store._get_conn_ctx() as conn:
        conn.execute("UPDATE dictionary SET word = 'Beta' WHERE word = 'Alpha'")
        conn.execute("INSERT INTO dictionary (word, category, created_at) VALUES ('Alpha', 'Personal', '2026-01-01')")
    assert set(StorageEngine(path).get_dictionary_words()) == {"Alpha", "Beta"}


def test_explicit_add_promotes_captured_term(tmp_path):
    store = StorageEngine(str(tmp_path / "words.db"))
    assert store.add_dictionary_word("hyperkube", category="Auto-Captured")
    engine = DictionaryEngine(store)
    assert engine.apply_dictionary_post_processing("hyperkube") == "hyperkube"
    assert store.add_dictionary_word("HyperKube")
    assert engine.apply_dictionary_post_processing("hyperkube") == "HyperKube"
    assert store.get_dictionary_entries()[0]["category"] == "Personal"


def test_rename_rejects_casefold_collision_without_losing_rows(tmp_path):
    store = StorageEngine(str(tmp_path / "words.db"))
    store.add_dictionary_word("Alpha")
    store.add_dictionary_word("Beta")
    assert store.update_dictionary_word("Alpha", "bETA") is False
    assert set(store.get_dictionary_words()) == {"Alpha", "Beta"}


def test_final_style_guard_restores_spelling_without_repeating_corrections(tmp_path, monkeypatch):
    from voice_flow import main
    store = StorageEngine(str(tmp_path / "words.db"))
    store.add_dictionary_word("HyperKube")
    store.add_dictionary_correction("first", "second")
    store.add_dictionary_correction("second", "third")
    engine = DictionaryEngine(store)
    monkeypatch.setattr(main, "dictionary_engine", engine)
    monkeypatch.setattr(main.polisher, "polish", lambda *_a, **_k: "second HyperKube")
    monkeypatch.setattr(main, "smart_format", lambda text, *_a: text.lower())
    app = object.__new__(main.VoiceFlowApp)
    session = SimpleNamespace(style_id="personal_very_casual", cleanup_level="cleanup_light")
    assert app._finalize_text("first hyperkube", session) == "second HyperKube"


def test_legacy_false_setting_stays_off_for_all_readers(tmp_path):
    store = StorageEngine(str(tmp_path / "words.db"))
    store.save_setting("polishing_enabled", "false")
    assert store.get_setting("polishing_enabled", True) is False

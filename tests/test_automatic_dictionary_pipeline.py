"""Automatic learning through the actual background history worker, without UI."""
from types import SimpleNamespace
import threading

import pytest

from voice_flow import main
from voice_flow.dictionary import DictionaryEngine
from voice_flow.storage import StorageEngine


@pytest.fixture
def writer(tmp_path, monkeypatch):
    store = StorageEngine(str(tmp_path / "automatic-pipeline.db"))
    # The isolated fixture must stay in its own account/database.
    monkeypatch.setattr(store, "repoint_if_needed", lambda: False)
    monkeypatch.setattr(main, "storage", store)
    workers = []
    original_thread = threading.Thread

    class CapturedThread(original_thread):
        def start(self):
            workers.append(self)
            super().start()

    monkeypatch.setattr(main.threading, "Thread", CapturedThread)
    app = object.__new__(main.VoiceFlowApp)
    app._state_lock = threading.RLock()
    session = SimpleNamespace(app_title="Editor", app_category="work")

    def save(raw, final=None, *, status="success", insertion="pasted", metadata=None, recovery=None):
        app._defer_history_insert(
            recovery, session, 1.0, raw_text=raw, polished_text=final or raw,
            status=status, insertion_status=insertion, processing_metadata=metadata,
        )
        for worker in workers:
            worker.join(timeout=3)
            assert not worker.is_alive(), "History worker did not finish"

    yield store, save
    for worker in workers:
        worker.join(timeout=3)


def accepted_metadata(*, outcome="ai_accepted", command_status="not_detected", command_label=""):
    return {"polish": {"outcome": outcome}, "command": {"status": command_status, "label": command_label}}


@pytest.mark.parametrize("polishing_enabled", [False, True])
def test_repeated_raw_word_activates_without_opening_dictionary(writer, polishing_enabled):
    store, save = writer
    store.save_setting("polishing_enabled", polishing_enabled)
    # Recognition can run in another process/store from the history writer.
    # Its existing engine must see the persisted revision without a UI reload.
    engine = DictionaryEngine(StorageEngine(store.db_path))
    for _ in range(2):
        save("we use HyperKube every day")
    assert "HyperKube" not in engine.get_stt_hint_terms()
    save("we use HyperKube every day")
    assert "HyperKube" in engine.get_stt_hint_terms()
    assert engine.apply_dictionary_post_processing("Hyper Kube works") == "HyperKube works"
    assert store.get_lexicon_suggestions() == []


def test_correction_capture_follows_saved_history_and_passes_its_id(writer, monkeypatch):
    store, save = writer
    seen = []

    def capture(term, variant, *, history_id):
        with store._get_conn_ctx() as conn:
            row = conn.execute("SELECT raw_text, polished_text FROM history WHERE id = ?", (history_id,)).fetchone()
        assert row is not None, "Learning ran before persistence"
        seen.append((term, variant, history_id))

    monkeypatch.setattr(store, "record_lexicon_candidate", capture)
    save("we use land graph for routing", "We use LangGraph for routing", metadata=accepted_metadata())
    assert len(seen) == 1
    assert seen[0][:2] == ("LangGraph", "land graph")


def test_three_successful_corrections_activate_word_and_rule_without_ui(writer):
    store, save = writer
    engine = DictionaryEngine(StorageEngine(store.db_path))
    for _ in range(3):
        save("we use land graph for routing", "We use LangGraph for routing", metadata=accepted_metadata())
    assert "LangGraph" in engine.get_stt_hint_terms()
    assert engine.apply_dictionary_post_processing("use land graph for routing") == "use LangGraph for routing"


@pytest.mark.parametrize("status,insertion,metadata", [
    ("paste_failed", "failed", accepted_metadata()),
    ("success", "ready_to_paste", accepted_metadata()),
    ("success", "pasted", None),
    ("success", "pasted", accepted_metadata(outcome="disabled")),
    ("success", "pasted", accepted_metadata(outcome="timeout")),
    ("success", "pasted", accepted_metadata(command_status="applied", command_label="Email")),
])
def test_untrusted_or_transformed_final_text_is_not_correction_evidence(writer, monkeypatch, status, insertion, metadata):
    store, save = writer
    seen = []
    monkeypatch.setattr(store, "record_lexicon_candidate", lambda *a, **kw: seen.append((a, kw)))
    save("we use land graph for routing", "We use LangGraph for routing", status=status, insertion=insertion, metadata=metadata)
    assert seen == []


def test_correction_failure_does_not_lose_saved_history(writer, monkeypatch):
    store, save = writer
    monkeypatch.setattr(store, "record_lexicon_candidate", lambda *a, **kw: (_ for _ in ()).throw(OSError("learning failed")))
    save("we use land graph for routing", "We use LangGraph for routing", metadata=accepted_metadata())
    with store._get_conn_ctx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM history WHERE status = 'success'").fetchone()[0] == 1


def test_retry_and_duplicate_history_write_cannot_activate_word(writer):
    store, save = writer
    recovery = {"audio_path": None, "done": threading.Event()}
    recovery["done"].set()
    save("we use HyperKube", recovery=recovery)
    save("we use HyperKube", recovery=recovery)
    for _ in range(3):
        save("we use HyperKube", recovery={"existing_record_id": 1})
    assert "HyperKube" not in store.get_dictionary_words()
    with store._get_conn_ctx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM history").fetchone()[0] == 1

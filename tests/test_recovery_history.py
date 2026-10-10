import os
import sqlite3
import time
from pathlib import Path

import numpy as np

from voice_flow.recovery import AUDIO_RETENTION_SECONDS, AudioArchive
from voice_flow.storage import StorageEngine


def test_archive_roundtrip_and_rejects_traversal(tmp_path):
    archive = AudioArchive(tmp_path / "audio")
    name = archive.save(np.array([0.0, .2, -.2], dtype=np.float32))
    path = archive.resolve(name)
    assert path and path.read_bytes()[:4] == b"RIFF"
    assert archive.resolve("../outside.wav") is None
    assert archive.resolve(str(path)) is None


def test_purge_only_removes_expired_audio(tmp_path):
    archive = AudioArchive(tmp_path / "audio")
    name = archive.save(np.ones(8, dtype=np.float32))
    path = archive.resolve(name); assert path
    old = time.time() - AUDIO_RETENTION_SECONDS - 1
    os.utime(path, (old, old))
    assert archive.purge_expired() == [name]
    assert archive.resolve(name) is None


def test_old_history_schema_is_additively_migrated(tmp_path):
    db = tmp_path / "legacy.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE history (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, raw_text TEXT NOT NULL, polished_text TEXT NOT NULL, app_name TEXT, duration_sec REAL, word_count INTEGER, wpm_speed INTEGER, style_mode TEXT)")
    con.execute("INSERT INTO history VALUES (1, '2026-01-01 00:00:00', 'raw', 'text', 'App', 6, 1, 10, 'style')")
    con.commit(); con.close()
    store = StorageEngine(str(db))
    row = store.get_history_record(1)
    assert row["status"] == "success" and row["insertion_status"] == "pasted" and row["retry_count"] == 0


def test_delete_history_returns_only_the_requested_row(tmp_path):
    store = StorageEngine(str(tmp_path / "history.db"))
    one = store.add_dictation("a", "a"); two = store.add_dictation("b", "b")
    deleted = store.delete_history_record(one.id)
    assert deleted["id"] == one.id
    assert store.get_history_record(two.id)["polished_text"] == "b"


def test_finalizing_history_recomputes_metrics(tmp_path):
    store = StorageEngine(str(tmp_path / "history.db"))
    row = store.add_dictation("", "", duration_sec=30, status="processing", insertion_status="not_attempted")
    assert store.update_dictation(row.id, polished_text="one two three", status="success")
    final = store.get_history_record(row.id)
    assert final["word_count"] == 3 and final["wpm_speed"] == 6

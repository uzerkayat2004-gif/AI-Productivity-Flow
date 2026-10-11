"""Tests for StorageEngine.repoint_if_needed().

The engine and the GUI server must always agree on the active account's
database. When an account logs in/logs out/switches, the running processes
re-point themselves on the next read/write instead of keeping the DB they
latched onto at startup.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
import threading

import pytest

from voice_flow.account_manager import AccountManager
from voice_flow.storage import StorageEngine


@pytest.fixture
def two_dbs(tmp_path: Path):
    return {
        "db_a": tmp_path / "voice_flow.db",
        "db_b": tmp_path / "accounts" / "acc_two" / "voice_flow.db",
    }


def test_active_account_lookup_closes_connection_after_success(tmp_path, monkeypatch):
    database = tmp_path / "accounts.db"
    with sqlite3.connect(str(database)) as seed:
        seed.execute("CREATE TABLE account_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        seed.execute("INSERT INTO account_state VALUES ('active_account_id', 'acc_test')")

    connection = sqlite3.connect(str(database))
    connection.row_factory = sqlite3.Row
    manager = object.__new__(AccountManager)
    manager._lock = threading.RLock()
    monkeypatch.setattr(manager, "_get_conn", lambda: connection)

    assert manager.get_active_account_id() == "acc_test"
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_active_account_lookup_closes_connection_after_query_error(tmp_path, monkeypatch):
    database = tmp_path / "accounts.db"
    with sqlite3.connect(str(database)) as seed:
        seed.execute("CREATE TABLE unrelated (value TEXT)")

    connection = sqlite3.connect(str(database))
    connection.row_factory = sqlite3.Row
    manager = object.__new__(AccountManager)
    manager._lock = threading.RLock()
    monkeypatch.setattr(manager, "_get_conn", lambda: connection)

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        manager.get_active_account_id()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_repoint_switches_database(two_dbs, monkeypatch):
    db_a = two_dbs["db_a"]
    db_b = two_dbs["db_b"]
    engine = StorageEngine(str(db_a))
    assert Path(engine.db_path) == db_a

    # A login makes the active database db_b.
    monkeypatch.setattr(
        "voice_flow.storage.resolve_active_db_path", lambda: str(db_b)
    )

    assert engine.repoint_if_needed() is True
    assert Path(engine.db_path) == db_b
    # The new database was initialized with the full schema (WAL + tables).
    import sqlite3
    tables = {
        r[0]
        for r in sqlite3.connect(str(db_b)).execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "history" in tables
    assert "settings" in tables


def test_repoint_is_noop_when_already_active(two_dbs, monkeypatch):
    db_a = two_dbs["db_a"]
    engine = StorageEngine(str(db_a))
    monkeypatch.setattr(
        "voice_flow.storage.resolve_active_db_path", lambda: str(db_a)
    )
    assert engine.repoint_if_needed() is False
    assert Path(engine.db_path) == db_a


def test_repoint_keeps_current_account_when_account_lookup_fails(two_dbs, monkeypatch):
    """A transient accounts DB error must not select the legacy root DB."""
    db_a = two_dbs["db_a"]
    db_b = two_dbs["db_b"]
    engine = StorageEngine(str(db_b))
    monkeypatch.setattr("voice_flow.storage.DB_PATH", str(db_a))

    def unavailable():
        raise OSError("accounts database is temporarily busy")

    monkeypatch.setattr("voice_flow.account_manager.get_account_manager", unavailable)

    assert engine.repoint_if_needed() is False
    assert Path(engine.db_path) == db_b


def test_repoint_back_to_default(two_dbs, monkeypatch):
    db_a = two_dbs["db_a"]
    db_b = two_dbs["db_b"]
    engine = StorageEngine(str(db_a))
    monkeypatch.setattr(
        "voice_flow.storage.resolve_active_db_path", lambda: str(db_b)
    )
    assert engine.repoint_if_needed() is True

    # Logout: active DB returns to the default legacy file.
    monkeypatch.setattr(
        "voice_flow.storage.resolve_active_db_path", lambda: str(db_a)
    )
    assert engine.repoint_if_needed() is True
    assert Path(engine.db_path) == db_a


def test_insights_reads_active_db_after_repoint(two_dbs, monkeypatch):
    """The data fix end-to-end: repoint, then get_insights reads the right DB."""
    db_a = two_dbs["db_a"]
    db_b = two_dbs["db_b"]
    engine = StorageEngine(str(db_b))

    # Write one dictation row into db_b directly.
    with engine._get_conn() as conn:
        conn.execute(
            """INSERT INTO history
               (timestamp, raw_text, polished_text, app_name, duration_sec,
                word_count, wpm_speed, style_mode, status)
               VALUES ('2026-09-12 12:00:00', 'real dictation', 'Real dictation.',
                       'General App', 2.0, 2, 60, 'smart_clean', 'success')"""
        )
        conn.commit()

    # A second engine was constructed pointing at db_b before the account was
    # activated; simulating the UI layer we re-point it to the active DB.
    other = StorageEngine(str(db_a))
    monkeypatch.setattr(
        "voice_flow.storage.resolve_active_db_path", lambda: str(db_b)
    )
    assert other.repoint_if_needed() is True
    data = other.get_insights("all")
    assert data["dictation_count"] == 1
    assert data["total_words"] == 2
    assert Path(other.db_path) == db_b

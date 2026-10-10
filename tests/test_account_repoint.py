"""Tests for StorageEngine.repoint_if_needed().

The engine and the GUI server must always agree on the active account's
database. When an account logs in/logs out/switches, the running processes
re-point themselves on the next read/write instead of keeping the DB they
latched onto at startup.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from voice_flow.storage import StorageEngine


@pytest.fixture
def two_dbs(tmp_path: Path):
    return {
        "db_a": tmp_path / "voice_flow.db",
        "db_b": tmp_path / "accounts" / "acc_two" / "voice_flow.db",
    }


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
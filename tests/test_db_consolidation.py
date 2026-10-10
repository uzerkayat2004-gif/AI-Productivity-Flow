"""Tests for cross-database consolidation (accounts-era fragmentation fix).

The accounts feature gave each account its own SQLite database; sessions
started before an account existed could write dictation history to the legacy
``~/.voice_flow/voice_flow.db`` or to ``accounts/acc_primary/voice_flow.db``.
``voice_flow.consolidate`` merges those files into the active account database
without losing or duplicating rows.

All tests here run against isolated temp directories (never the live data).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from voice_flow.storage import StorageEngine


def _seed_db(path: Path, rows: list[tuple]) -> None:
    """Create a Voice Flow DB schema at ``path`` and insert history rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = StorageEngine(str(path))
    with engine._get_conn() as conn:
        for ts, raw, polished, words in rows:
            conn.execute(
                """INSERT INTO history
                   (timestamp, raw_text, polished_text, app_name, duration_sec,
                    word_count, wpm_speed, style_mode, status)
                   VALUES (?, ?, ?, 'Test App', 5.0, ?, 60, 'smart_clean', 'success')""",
                (ts, raw, polished, words),
            )
        conn.commit()


def _count_rows(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return int(conn.execute("SELECT COUNT(1) FROM history").fetchone()[0])
    finally:
        conn.close()


@pytest.fixture
def fragmented_layout(tmp_path: Path, monkeypatch):
    """Build the exact 4-file layout the accounts era produced.

    * tmp/voice_flow.db  (legacy default DB, the big one)
    * tmp/accounts/acc_primary/voice_flow.db (migration copy)
    * tmp/accounts/acc_active/voice_flow.db (current signed-in account, small)
    * tmp/accounts/acc_unused/voice_flow.db (empty account)
    """
    monkeypatch.setenv("VOICE_FLOW_DATA_DIR", str(tmp_path))

    legacy_path = tmp_path / "voice_flow.db"
    primary_path = tmp_path / "accounts" / "acc_primary" / "voice_flow.db"
    active_path = tmp_path / "accounts" / "acc_active" / "voice_flow.db"
    unused_path = tmp_path / "accounts" / "acc_unused" / "voice_flow.db"

    legacy_rows = [
        ("2026-09-01 09:00:00", "hello world first", "Hello world first.", 3),
        ("2026-09-02 09:00:00", "second dictation", "Second dictation.", 2),
    ]
    primary_rows = [
        ("2026-09-02 09:00:00", "second dictation", "Second dictation.", 2),  # dup of legacy
        ("2026-09-03 09:00:00", "primary only row", "Primary only row.", 3),
    ]
    active_rows = [
        ("2026-09-12 10:00:00", "signed in dictation", "Signed in dictation.", 3),
    ]

    _seed_db(legacy_path, legacy_rows)
    _seed_db(primary_path, primary_rows)
    _seed_db(active_path, active_rows)
    _seed_db(unused_path, [])

    # Keep repoint resolving to the active test account during the whole test.
    monkeypatch.setattr(
        "voice_flow.storage.resolve_active_db_path",
        lambda: str(active_path),
    )
    return {
        "tmp": tmp_path,
        "active_path": active_path,
        "legacy_path": legacy_path,
        "primary_path": primary_path,
    }


def test_consolidation_merges_all_rows(fragmented_layout, monkeypatch):
    active = fragmented_layout["active_path"]
    engine = StorageEngine(str(active))

    from voice_flow.consolidate import consolidate_engine

    summary = consolidate_engine(engine, dry_run=False)

    # legacy rows {2} + primary-only row {1} + active {1} = 4 unique rows.
    assert summary["merged_history"] == 3
    assert summary["skipped_duplicates"] == 1  # the exact duplicate row
    assert _count_rows(active) == 4

    texts = {
        r[0]  # raw_text (single-column query, default tuple rows)
        for r in sqlite3.connect(str(active)).execute("SELECT raw_text FROM history")
    }
    assert texts == {
        "hello world first",
        "second dictation",
        "primary only row",
        "signed in dictation",
    }


def test_consolidation_is_idempotent(fragmented_layout, monkeypatch):
    active = fragmented_layout["active_path"]
    engine = StorageEngine(str(active))
    from voice_flow.consolidate import consolidate_engine

    consolidate_engine(engine, dry_run=False)
    second = consolidate_engine(engine, dry_run=False)

    assert second["merged_history"] == 0
    assert _count_rows(active) == 4
def test_dry_run_changes_nothing(fragmented_layout, monkeypatch):
    active = fragmented_layout["active_path"]
    engine = StorageEngine(str(active))
    from voice_flow.consolidate import consolidate_engine

    summary = consolidate_engine(engine, dry_run=True)

    assert summary["dry_run"] is True
    assert summary["merged_history"] == 3
    assert _count_rows(active) == 1  # untouched


def test_guest_mode_skips_consolidation(tmp_path: Path, monkeypatch):
    """In guest mode the target DB is the default one -> nothing is merged."""
    monkeypatch.setenv("VOICE_FLOW_DATA_DIR", str(tmp_path))
    default_path = tmp_path / "voice_flow.db"
    unused = tmp_path / "accounts" / "acc_primary" / "voice_flow.db"
    _seed_db(default_path, [("2026-09-01 09:00:00", "guest row", "Guest row.", 2)])
    _seed_db(unused, [("2026-09-01 10:00:00", "account row", "Account row.", 2)])

    engine = StorageEngine(str(default_path))
    monkeypatch.setattr(
        "voice_flow.storage.resolve_active_db_path",
        lambda: str(default_path),
    )
    from voice_flow.consolidate import consolidate_engine

    summary = consolidate_engine(engine, dry_run=False)

    assert summary.get("skipped_reason") == "guest_mode_uses_default_db"
    assert _count_rows(default_path) == 1  # account rows NOT pulled down
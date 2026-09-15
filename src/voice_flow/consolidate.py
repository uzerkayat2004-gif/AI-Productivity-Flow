"""Database consolidation for the multi-account era.

The accounts feature split Voice Flow's single SQLite database
(``~/.voice_flow/voice_flow.db``) into per-account databases
(``~/.voice_flow/accounts/<id>/voice_flow.db``).  Sessions started before an
account existed (or that never re-pointed to it) can leave dictation history
scattered across several files, which makes the Insights dashboard
under-report real usage.

This module merges every legacy/sibling database into the database the active
StorageEngine points at (the active account DB, or the default DB in guest
mode), idempotently:

* ``history`` rows use ``(timestamp, raw_text)`` as the de-duplication key.
* every other table merges with ``INSERT OR IGNORE`` (primary-key conflicts
  keep the target's existing row).

Usage:
    python -m voice_flow.consolidate --dry-run
    python -m voice_flow.consolidate --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger(__name__)

# Tables merged across legacy/sibling databases. "history" has bespoke
# (timestamp, raw_text) de-duplication; every other table merges with
# INSERT OR IGNORE so existing primary keys are never overwritten.
MERGE_TABLES = (
    "history",
    "dictionary",
    "api_keys",
    "settings",
    "provider_connections",
    "provider_settings",
    "provider_models",
    "dictionary_corrections",
    "snippets",
    "dictionary_keys",
    "snippet_keys",
    "correction_keys",
    "migration_conflicts",
    "tts_models",
    "audio_provider_connections",
    "video_flow_videos",
    "video_flow_combos",
    "video_flow_combo_models",
    "video_flow_provider_connections",
    "video_flow_provider_models",
    "video_flow_provider_settings",
    "video_flow_animation_history",
    "dictionary_replacements",
    "dictionary_learning_candidates",
    "custom_transforms",
    "transform_writing_examples",
    "transform_history",
    "video_projects",
    "audio_summary_cache",
    "video_flow_jobs",
    "combos",
    "oauth_connections",
    "lexicon_candidates",
    "google_auth_kv",
    "audio_provider_settings",
    "audio_summary_history",
)

CONSOLIDATION_MARKER_KEY = "db_consolidation_v1"


def _row_str(value: object) -> str:
    return str(value or "")


def _chunks(rows: list[tuple[Any, ...]], size: int = 400) -> Iterable[list[tuple[Any, ...]]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
    except Exception:
        pass
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    try:
        return [str(r["name"]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    except Exception:
        return []


def _table_list(conn: sqlite3.Connection) -> list[str]:
    try:
        return [str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    except Exception:
        return []


def _read_marker(conn: sqlite3.Connection) -> dict[str, Any]:
    """Read the consolidation marker: per-source cursor state."""
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (CONSOLIDATION_MARKER_KEY,)
        ).fetchone()
    except Exception:
        return {}
    if not row or not row[0]:
        return {}
    try:
        data = json.loads(str(row[0]))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_marker(target_path: Path, report: dict[str, Any]) -> None:
    payload = {
        "target": str(target_path),
        "sources": report.get("sources", []),
        "merged_history": report.get("merged_history", 0),
        "tables": report.get("tables", {}),
        "cursors": report.get("cursors", {}),
    }
    conn = _open(target_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            (CONSOLIDATION_MARKER_KEY, json.dumps(payload, indent=2, default=str)),
        )
        conn.commit()
    finally:
        conn.close()


def _candidate_sources(target_path: Path) -> list[Path]:
    """Collect legacy/sibling databases that could hold fragmented rows."""
    from voice_flow.paths import data_dir

    base = Path(data_dir())
    candidates: list[Path] = []
    default_db = base / "voice_flow.db"
    if default_db != target_path and default_db.exists():
        candidates.append(default_db)
    accounts_dir = base / "accounts"
    if accounts_dir.is_dir():
        for acct_dir in sorted(accounts_dir.iterdir()):
            if not acct_dir.is_dir():
                continue
            db = acct_dir / "voice_flow.db"
            if db != target_path and db.exists():
                candidates.append(db)
    return candidates


def consolidate_engine(engine: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Merge fragmented databases into the engine's active database.

    Returns a summary dict describing what would be / was merged.
    ``dry_run=True`` only computes counts and never writes.
    """
    try:
        repoint = getattr(engine, "repoint_if_needed", None)
        if repoint is not None:
            repoint()
    except Exception:
        log.debug("Could not re-point storage before consolidation", exc_info=True)

    target_path = Path(engine.db_path)
    # Guest mode ("Primary Account" placeholder, no Google sign-in) keeps the
    # default ~/.voice_flow/voice_flow.db as the single canonical store, so
    # there is nothing to consolidate: pulling per-account rows down into the
    # default DB would create cross-account drift. Only real accounts merge
    # legacy/sibling databases into their dedicated vault.
    from voice_flow.paths import data_dir as _guard_data_dir

    _base = Path(_guard_data_dir())
    if not str(target_path).startswith(str(_base / "accounts")):
        return {
            "target": str(target_path),
            "sources": [],
            "merged_history": 0,
            "skipped_duplicates": 0,
            "tables": {},
            "cursors": {},
            "dry_run": bool(dry_run),
            "skipped_reason": "guest_mode_uses_default_db",
        }

    candidates = _candidate_sources(target_path)

    report: dict[str, Any] = {
        "target": str(target_path),
        "sources": [str(p) for p in candidates],
        "merged_history": 0,
        "skipped_duplicates": 0,
        "tables": {},
        "cursors": {},
        "dry_run": bool(dry_run),
    }
    if not candidates:
        return report

    tgt = _open(target_path)
    try:
        table_list = _table_list(tgt)
        marker = _read_marker(tgt)
        existing_history_keys: set[tuple[str, str]] | None = None
    finally:
        tgt.close()

    for src in candidates:
        try:
            src_conn = _open(src)
        except Exception:
            log.warning("Could not open legacy database %s for consolidation", src)
            continue
        try:
            src_tables = set(_table_list(src_conn))
            src_cursor = str((marker.get("cursors") or {}).get(str(src), "") or "")
            for table in table_list:
                if table not in MERGE_TABLES or table not in src_tables:
                    continue
                if table == "history":
                    result = _merge_history(
                        src_conn, target_path, existing_history_keys,
                        after_timestamp=src_cursor, dry_run=dry_run,
                    )
                    existing_history_keys = result["existing_keys"]
                    report["merged_history"] += result["added"]
                    report["skipped_duplicates"] += result["skipped"]
                    prev_h = report["tables"].get("history", {"added": 0, "skipped": 0})
                    report["tables"]["history"] = {
                        "added": prev_h["added"] + result["added"],
                        "skipped": prev_h["skipped"] + result["skipped"],
                    }
                    # Advance the cursor to the newest timestamp we saw, so the
                    # next startup only scans truly new legacy rows (cheap).
                    if result["new_max_ts"]:
                        report["cursors"][str(src)] = result["new_max_ts"]
                    continue
                result = _merge_generic(src_conn, target_path, table, dry_run=dry_run)
                prev_t = report["tables"].get(table, {"added": 0, "skipped": 0})
                report["tables"][table] = {
                    "added": prev_t["added"] + result["added"],
                    "skipped": prev_t["skipped"] + result["skipped"],
                }
        finally:
            src_conn.close()

    if not dry_run:
        try:
            _write_marker(target_path, report)
            bump = getattr(engine, "_bump_dictionary_revision", None)
            if bump is not None:
                try:
                    with engine._get_conn() as conn:
                        bump(conn)
                except Exception:
                    pass
        except Exception:
            log.exception("Could not persist consolidation marker; merging will be retried next startup")
    return report


def _merge_history(
    src_conn: sqlite3.Connection,
    target_path: Path,
    existing_keys: set[tuple[str, str]] | None,
    *,
    after_timestamp: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Merge history rows from ``src_conn`` into ``target_path``.

    De-duplicates on ``(timestamp, raw_text)``. When ``after_timestamp`` is
    non-empty only rows newer than it are scanned (incremental re-runs).
    """
    tgt = _open(target_path)
    try:
        tcols = _columns(tgt, "history")
        scol = _columns(src_conn, "history")
        if not tcols or not scol:
            return {"added": 0, "skipped": 0, "existing_keys": existing_keys or set(), "new_max_ts": ""}
        shared = [c for c in scol if c in tcols and c != "id"]
        if "timestamp" not in shared or "raw_text" not in shared:
            return {"added": 0, "skipped": 0, "existing_keys": existing_keys or set(), "new_max_ts": ""}

        if existing_keys is None:
            existing_keys = {
                (_row_str(r["timestamp"]), _row_str(r["raw_text"]))
                for r in tgt.execute("SELECT timestamp, raw_text FROM history").fetchall()
            }

        selects = ", ".join(f'"{c}"' for c in shared)
        if after_timestamp:
            rows = src_conn.execute(
                f"SELECT {selects} FROM history WHERE timestamp > ?",
                (after_timestamp,),
            ).fetchall()
        else:
            rows = src_conn.execute(f"SELECT {selects} FROM history").fetchall()

        to_add: list[tuple[Any, ...]] = []
        skipped = 0
        new_max_ts = after_timestamp
        for srow in rows:
            ts_val = _row_str(srow["timestamp"])
            key = (ts_val, _row_str(srow["raw_text"]))
            if ts_val > new_max_ts:
                new_max_ts = ts_val
            if key in existing_keys:
                skipped += 1
                continue
            to_add.append(tuple(srow[c] for c in shared))
            existing_keys.add(key)

        added = len(to_add)
        if to_add and not dry_run:
            placeholders = ", ".join("?" for _ in shared)
            cols_sql = ", ".join(f'"{c}"' for c in shared)
            for chunk in _chunks(to_add):
                tgt.executemany(
                    f'INSERT INTO history ({cols_sql}) VALUES ({placeholders})',
                    chunk,
                )
            tgt.commit()
        return {
            "added": added,
            "skipped": skipped,
            "existing_keys": existing_keys,
            "new_max_ts": new_max_ts,
        }
    finally:
        tgt.close()


def _merge_generic(
    src_conn: sqlite3.Connection,
    target_path: Path,
    table: str,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    """Merge one non-history table with INSERT OR IGNORE over shared columns."""
    tgt = _open(target_path)
    try:
        tcols = _columns(tgt, table)
        scol = _columns(src_conn, table)
        if not tcols or not scol:
            return {"added": 0, "skipped": 0}
        shared = [c for c in scol if c in tcols]
        if not shared:
            return {"added": 0, "skipped": 0}
        selects = ", ".join(f'"{c}"' for c in shared)
        rows = [tuple(r[c] for c in shared) for r in
                src_conn.execute(f"SELECT {selects} FROM {table}").fetchall()]
        if not rows:
            return {"added": 0, "skipped": 0}
        before = int(tgt.execute(f'SELECT COUNT(1) FROM "{table}"').fetchone()[0])
        added = 0
        if not dry_run:
            cols_sql = ", ".join(f'"{c}"' for c in shared)
            placeholders = ", ".join("?" for _ in shared)
            for chunk in _chunks(rows):
                tgt.executemany(
                    f'INSERT OR IGNORE INTO "{table}" ({cols_sql}) VALUES ({placeholders})',
                    chunk,
                )
            tgt.commit()
            after = int(tgt.execute(f'SELECT COUNT(1) FROM "{table}"').fetchone()[0])
            added = max(0, after - before)
        return {"added": added, "skipped": len(rows) - added}
    finally:
        tgt.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="voice_flow.consolidate",
        description="Merge fragmented Voice Flow databases into the active one.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="perform the merge (default)")
    group.add_argument("--dry-run", action="store_true", help="only report what would be merged")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from voice_flow.storage import storage

    summary = consolidate_engine(storage, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""Persistent SQLite Storage Engine for Voice Flow.
Stores dictation history, custom dictionary terms, app-specific style rules, and insights metrics.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
from dataclasses import dataclass
from typing import Any

DB_PATH = os.path.join(os.path.expanduser("~"), ".voice_flow", "voice_flow.db")


@dataclass
class DictationRecord:
    id: int | None
    timestamp: str
    raw_text: str
    polished_text: str
    app_name: str
    duration_sec: float
    word_count: int
    wpm_speed: int
    style_mode: str


class StorageEngine:
    """SQLite Database manager for persistent dictation history & metrics."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            # Table 1: Dictation History
            conn.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    polished_text TEXT NOT NULL,
                    app_name TEXT DEFAULT 'General',
                    duration_sec REAL DEFAULT 0.0,
                    word_count INTEGER DEFAULT 0,
                    wpm_speed INTEGER DEFAULT 0,
                    style_mode TEXT DEFAULT 'smart_clean'
                )
            """)

            # Table 2: Custom Dictionary Terms
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dictionary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT UNIQUE NOT NULL,
                    category TEXT DEFAULT 'Personal',
                    created_at TEXT NOT NULL
                )
            """)

            # Seed default dictionary terms if empty
            cursor = conn.execute("SELECT COUNT(*) FROM dictionary")
            if cursor.fetchone()[0] == 0:
                default_words = [
                    ("Voice Flow", "Personal"),
                    ("Whisper", "Personal"),
                    ("Samir", "Personal"),
                    ("Sara", "Personal"),
                    ("Karol", "Personal"),
                    ("Spyder", "Personal"),
                ]
                now = datetime.datetime.now().isoformat()
                conn.executemany(
                    "INSERT INTO dictionary (word, category, created_at) VALUES (?, ?, ?)",
                    [(w, c, now) for w, c in default_words],
                )

            # Table 3: System API Keys
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_key TEXT UNIQUE NOT NULL,
                    provider TEXT DEFAULT 'gemini',
                    created_at TEXT NOT NULL
                )
            """)

            conn.commit()

    # --- History API ---

    def add_dictation(
        self,
        raw_text: str,
        polished_text: str,
        app_name: str = "General App",
        duration_sec: float = 2.0,
        style_mode: str = "smart_clean",
    ) -> DictationRecord:
        words = len(polished_text.split())
        minutes = max(0.05, duration_sec / 60.0)
        wpm = int(words / minutes) if words > 0 else 0
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO history (timestamp, raw_text, polished_text, app_name, duration_sec, word_count, wpm_speed, style_mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now_str, raw_text, polished_text, app_name, duration_sec, words, wpm, style_mode),
            )
            conn.commit()
            record_id = cursor.lastrowid

        return DictationRecord(
            id=record_id,
            timestamp=now_str,
            raw_text=raw_text,
            polished_text=polished_text,
            app_name=app_name,
            duration_sec=duration_sec,
            word_count=words,
            wpm_speed=wpm,
            style_mode=style_mode,
        )

    def get_recent_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_insights(self) -> dict[str, Any]:
        with self._get_conn() as conn:
            # Total words
            total_words = conn.execute("SELECT COALESCE(SUM(word_count), 0) FROM history").fetchone()[0]
            # Average WPM
            avg_wpm = conn.execute("SELECT COALESCE(AVG(wpm_speed), 0) FROM history").fetchone()[0]

            # App usage breakdown
            cursor = conn.execute(
                "SELECT app_name, COUNT(*) as count, SUM(word_count) as total_words FROM history GROUP BY app_name ORDER BY count DESC"
            )
            app_breakdown = [dict(row) for row in cursor.fetchall()]

            # Streak calculation
            cursor = conn.execute("SELECT DISTINCT DATE(timestamp) as date_val FROM history ORDER BY date_val DESC")
            dates = [row["date_val"] for row in cursor.fetchall()]

            streak = 0
            today = datetime.date.today()
            check_date = today
            for d_str in dates:
                try:
                    d_obj = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
                    if d_obj == check_date:
                        streak += 1
                        check_date -= datetime.timedelta(days=1)
                    elif d_obj == check_date - datetime.timedelta(days=1):
                        streak += 1
                        check_date = d_obj - datetime.timedelta(days=1)
                except Exception:
                    pass

            return {
                "total_words": total_words,
                "avg_wpm": int(avg_wpm) if avg_wpm else 108,
                "streak": streak,
                "app_breakdown": app_breakdown,
            }

    # --- Dictionary API ---

    def get_dictionary_words(self) -> list[str]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT word FROM dictionary ORDER BY word ASC")
            return [row["word"] for row in cursor.fetchall()]

    def add_dictionary_word(self, word: str, category: str = "Personal") -> bool:
        word_clean = word.strip()
        if not word_clean:
            return False

        now = datetime.datetime.now().isoformat()
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO dictionary (word, category, created_at) VALUES (?, ?, ?)",
                    (word_clean, category, now),
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def remove_dictionary_word(self, word: str) -> bool:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM dictionary WHERE word = ?", (word,))
            conn.commit()
            return True


# Singleton Storage Instance
storage = StorageEngine()

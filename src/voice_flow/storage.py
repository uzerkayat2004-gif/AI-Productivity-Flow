"""Persistent SQLite Storage Engine for Voice Flow.
Stores dictation history, custom dictionary terms, app-specific style rules, insights metrics, and API keys.
"""

from __future__ import annotations

import datetime
import os
import re
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

            # Table 3: System API Keys (legacy single key compatibility)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_key TEXT UNIQUE NOT NULL,
                    provider TEXT DEFAULT 'gemini',
                    created_at TEXT NOT NULL
                )
            """)

            # Table 4: User Settings (key-value store)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY NOT NULL,
                    value TEXT,
                    updated_at TEXT NOT NULL
                )
            """)

            # Table 5: Provider Multi-Key Connections
            conn.execute("""
                CREATE TABLE IF NOT EXISTS provider_connections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    name TEXT NOT NULL,
                    api_key TEXT NOT NULL,
                    priority INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1,
                    last_tested_status TEXT DEFAULT 'Connected',
                    created_at TEXT NOT NULL
                )
            """)

            # Table 6: Provider Settings (Load Balancing Mode)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS provider_settings (
                    provider TEXT PRIMARY KEY,
                    load_balance_mode TEXT DEFAULT 'priority',
                    is_enabled INTEGER DEFAULT 1
                )
            """)

            # Table 7: Provider Models
            conn.execute("""
                CREATE TABLE IF NOT EXISTS provider_models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    UNIQUE(provider, model_id)
                )
            """)

            conn.commit()

        self._seed_default_models()

    _SEED_VERSION = "1"  # Bump to re-seed after adding new default models

    def _seed_default_models(self) -> None:
        """Seed standard models for AI providers if not already present."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT value FROM settings WHERE key = 'seed_version'")
            row = cursor.fetchone()
            if row and row["value"] == self._SEED_VERSION:
                return  # Already seeded this version
        seeds = {
            "gemini": [
                ("gemini-2.5-flash", "Gemini 2.5 Flash (Next-Gen Flagship)"),
                ("gemini-2.5-pro", "Gemini 2.5 Pro (Deep Reasoning)"),
                ("gemini-2.0-flash", "Gemini 2.0 Flash"),
                ("gemini-2.0-flash-lite", "Gemini 2.0 Flash-Lite (Sub-50ms)"),
            ],
            "groq": [
                ("llama-3.3-70b-versatile", "Llama 3.3 70B Versatile"),
                ("llama-3.1-8b-instant", "Llama 3.1 8B Instant"),
                ("whisper-large-v3-turbo", "Whisper Large v3 Turbo"),
            ],
            "elevenlabs": [
                ("eleven_v3", "ElevenLabs v3 Expressive"),
                ("eleven_flash_v2_5", "ElevenLabs Flash v2.5"),
                ("eleven_multilingual_v2", "ElevenLabs Multilingual v2"),
            ],
            "deepgram": [
                ("nova-3", "Deepgram Nova 3 STT"),
                ("flux", "Deepgram Flux Conversational"),
                ("aura-2", "Deepgram Aura 2 TTS"),
            ],
            "openai": [
                ("gpt-4o-mini", "GPT-4o Mini"),
                ("gpt-4o", "GPT-4o Flagship"),
                ("gpt-3.5-turbo", "GPT-3.5 Turbo"),
            ],
            "assemblyai": [
                ("universal-2", "AssemblyAI Universal-2 STT"),
                ("universal-1", "AssemblyAI Universal-1 STT"),
                ("conformer-2", "AssemblyAI Conformer-2 STT"),
            ],
            "huggingface": [
                ("fixie-ai/ultravox-v0_5", "Ultravox v0.5 Speech LLM"),
                ("openai/whisper-large-v3-turbo", "Whisper Large v3 Turbo"),
                ("kyutai/moshiko-pytorch", "Moshiko Duplex Voice"),
            ],
            "cloudflare": [
                ("@cf/deepgram/nova-3", "Cloudflare Deepgram Nova 3"),
                ("@cf/openai/whisper-large-v3-turbo", "Cloudflare Whisper v3"),
                ("@cf/myshell/melotts", "Cloudflare MeloTTS"),
            ],
            "together": [
                ("meta-llama/Llama-3.3-70B-Instruct-Turbo", "Llama 3.3 70B Turbo"),
                ("cartesia/sonic-multilingual", "Cartesia Sonic TTS"),
                ("togethercomputer/whisper-large-v3", "Together Whisper v3"),
            ],
            "replicate": [
                ("victor-upx/kokoro-tts", "Kokoro TTS Generation"),
                ("coqui/xtts-v2", "Coqui XTTS-v2 Voice Clone"),
                ("replicate/whisp-v3", "Replicate Whisp v3"),
            ]
        }
        with self._get_conn() as conn:
            for provider, model_list in seeds.items():
                for mid, mname in model_list:
                    conn.execute(
                        "INSERT OR IGNORE INTO provider_models (provider, model_id, display_name, is_active) VALUES (?, ?, ?, 1)",
                        (provider, mid, mname)
                    )
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('seed_version', ?, datetime('now'))",
                (self._SEED_VERSION,)
            )
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
        words_list = polished_text.split()
        words = len(words_list)
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

        self._auto_extract_dictionary_words(words_list)

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

    def _auto_extract_dictionary_words(self, words: list[str]) -> None:
        """Extract explicit technical jargon (e.g. ALL CAPS acronyms like API, SQL or CamelCase like VoiceFlow)."""
        for word in words:
            clean = re.sub(r"[^\w\-]", "", word)
            if not clean or len(clean) < 3:
                continue
            # Auto-capture if ALL CAPS acronym (e.g. API, JSON, GraphQL)
            if clean.isupper() and len(clean) >= 3:
                self.add_dictionary_word(clean, category="Auto-Captured")
            # Auto-capture if CamelCase (e.g. VoiceFlow, TypeScript, OpenAI)
            elif any(c.isupper() for c in clean[1:]) and any(c.islower() for c in clean):
                self.add_dictionary_word(clean, category="Auto-Captured")

    def get_recent_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_insights(self) -> dict[str, Any]:
        with self._get_conn() as conn:
            total_words = conn.execute("SELECT COALESCE(SUM(word_count), 0) FROM history").fetchone()[0]
            avg_wpm = conn.execute("SELECT COALESCE(AVG(wpm_speed), 0) FROM history").fetchone()[0]

            cursor = conn.execute(
                "SELECT app_name, COUNT(*) as count, SUM(word_count) as total_words FROM history GROUP BY app_name ORDER BY count DESC"
            )
            app_breakdown = [dict(row) for row in cursor.fetchall()]

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
                "avg_wpm": int(avg_wpm) if avg_wpm else 0,
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

    # --- API Keys Persistence API ---

    def save_api_key(self, api_key: str, provider: str = "gemini") -> bool:
        key_clean = api_key.strip()
        if not key_clean:
            return False
        now = datetime.datetime.now().isoformat()
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO api_keys (api_key, provider, created_at) VALUES (?, ?, ?)",
                    (key_clean, provider, now),
                )
                conn.commit()
                return True
        except Exception:
            return False

    def get_all_api_keys(self) -> dict[str, str]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT provider, api_key FROM api_keys")
            res = {row["provider"]: row["api_key"] for row in cursor.fetchall()}
            # Also include primary active keys from provider_connections
            conns = self.get_all_provider_connections()
            for p, clist in conns.items():
                active = [c for c in clist if c.get("is_active")]
                if active:
                    res[p] = active[0]["api_key"]
            return res

    # --- Provider Multi-Key Connections API ---

    def get_provider_connections(self, provider: str) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM provider_connections WHERE provider = ? ORDER BY priority ASC, id ASC",
                (provider.lower(),)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_all_provider_connections(self) -> dict[str, list[dict[str, Any]]]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM provider_connections ORDER BY provider ASC, priority ASC, id ASC")
            result: dict[str, list[dict[str, Any]]] = {}
            for row in cursor.fetchall():
                p = row["provider"]
                if p not in result:
                    result[p] = []
                result[p].append(dict(row))
            return result

    def add_provider_connection(self, provider: str, name: str, api_key: str, priority: int = 1) -> dict[str, Any]:
        now = datetime.datetime.now().isoformat()
        clean_key = api_key.strip()
        clean_name = name.strip() or f"{provider.capitalize()} Key"
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO provider_connections (provider, name, api_key, priority, is_active, last_tested_status, created_at)
                VALUES (?, ?, ?, ?, 1, 'Connected', ?)
                """,
                (provider.lower(), clean_name, clean_key, priority, now)
            )
            conn.commit()
            cid = cursor.lastrowid
        self.save_api_key(clean_key, provider.lower())
        return {"id": cid, "provider": provider.lower(), "name": clean_name, "api_key": clean_key, "priority": priority, "is_active": 1, "last_tested_status": "Connected"}

    def update_provider_connection(self, cid: int, name: str, api_key: str, priority: int) -> bool:
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE provider_connections SET name = ?, api_key = ?, priority = ? WHERE id = ?",
                (name.strip(), api_key.strip(), priority, cid)
            )
            conn.commit()
            return True

    def toggle_provider_connection(self, cid: int, is_active: bool) -> bool:
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE provider_connections SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, cid)
            )
            conn.commit()
            return True

    def delete_provider_connection(self, cid: int) -> bool:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM provider_connections WHERE id = ?", (cid,))
            conn.commit()
            return True

    def update_connection_status(self, cid: int, status: str) -> None:
        with self._get_conn() as conn:
            conn.execute("UPDATE provider_connections SET last_tested_status = ? WHERE id = ?", (status, cid))
            conn.commit()

    def get_provider_load_balance_mode(self, provider: str) -> str:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT load_balance_mode FROM provider_settings WHERE provider = ?", (provider.lower(),))
            row = cursor.fetchone()
            return row["load_balance_mode"] if row else "priority"

    def save_provider_load_balance_mode(self, provider: str, mode: str) -> bool:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO provider_settings (provider, load_balance_mode, is_enabled) VALUES (?, ?, 1)",
                (provider.lower(), mode.lower())
            )
            conn.commit()
            return True

    def get_provider_models(self, provider: str) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM provider_models WHERE provider = ? ORDER BY id ASC", (provider.lower(),))
            return [dict(row) for row in cursor.fetchall()]

    def toggle_provider_model(self, model_db_id: int, is_active: bool) -> bool:
        with self._get_conn() as conn:
            conn.execute("UPDATE provider_models SET is_active = ? WHERE id = ?", (1 if is_active else 0, model_db_id))
            conn.commit()
            return True

    def add_provider_model(self, provider: str, model_id: str, display_name: str) -> bool:
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO provider_models (provider, model_id, display_name, is_active) VALUES (?, ?, ?, 1)",
                    (provider.lower(), model_id.strip(), display_name.strip())
                )
                conn.commit()
                return True
        except Exception:
            return False

    # --- Settings Persistence API ---

    def save_setting(self, key: str, value: Any) -> bool:
        """Save or update a setting in the database."""
        if not key:
            return False
        import json as _json
        now = datetime.datetime.now().isoformat()
        val_str = _json.dumps(value) if not isinstance(value, str) else value
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                    (key, val_str, now),
                )
                conn.commit()
                return True
        except Exception:
            return False

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Retrieve a setting value by key."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row is None:
                return default
            import json as _json
            try:
                return _json.loads(row["value"])
            except (ValueError, TypeError):
                return row["value"]

    def get_all_settings(self) -> dict[str, Any]:
        """Retrieve all settings as a dictionary."""
        import json as _json
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT key, value FROM settings")
            result = {}
            for row in cursor.fetchall():
                try:
                    result[row["key"]] = _json.loads(row["value"])
                except (ValueError, TypeError):
                    result[row["key"]] = row["value"]
            return result


# Singleton Storage Instance
storage = StorageEngine()

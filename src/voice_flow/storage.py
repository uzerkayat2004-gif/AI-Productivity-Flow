"""Persistent SQLite Storage Engine for Voice Flow.
Stores dictation history, custom dictionary terms, app-specific style rules, insights metrics, and API keys.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from voice_flow.paths import data_dir

DB_PATH = str(data_dir() / "voice_flow.db")
log = logging.getLogger(__name__)

def _raw_token_occurrences(rows: list[sqlite3.Row], term: str) -> int:
    """Count complete term occurrences in raw history, case-insensitively."""
    pattern = re.compile(
        rf"(?<![\w-]){re.escape(term)}(?![\w-])",
        flags=re.IGNORECASE | re.UNICODE,
    )
    return sum(
        len(pattern.findall(str(row["raw_text"] or "")))
        for row in rows
    )


def _dictionary_term_occurrences(text: str, term: str) -> int:
    """Count complete active-dictionary term occurrences in text."""
    pattern = re.compile(
        rf"(?<!\w){re.escape(term)}(?!\w)",
        flags=re.IGNORECASE | re.UNICODE,
    )
    return len(pattern.findall(text or ""))


# Keep module-level helpers small and deterministic; storage owns persistence.


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
    status: str = "success"
    error_message: str | None = None
    audio_path: str | None = None
    insertion_status: str = "pasted"
    updated_at: str | None = None
    retry_count: int = 0


class StorageEngine:
    """SQLite Database manager for persistent dictation history & metrics."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._lexicon_revision = 0
        self._lexicon_lock = threading.RLock()
        self._init_db()

    def _touch_lexicon(self) -> None:
        """Notify in-process dictionary/snippet engines about persisted edits."""
        self._lexicon_revision += 1

    @contextmanager
    def _get_conn_ctx(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dictionary_keys (
                    normalized TEXT PRIMARY KEY NOT NULL,
                    dictionary_id INTEGER UNIQUE NOT NULL
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
                    uuid_id TEXT,
                    provider TEXT NOT NULL,
                    auth_type TEXT DEFAULT 'apikey',
                    name TEXT NOT NULL,
                    api_key TEXT NOT NULL,
                    base_url TEXT,
                    organization TEXT,
                    account_id TEXT,
                    priority INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    is_valid INTEGER DEFAULT 1,
                    last_tested_at TEXT,
                    last_error TEXT,
                    last_tested_status TEXT DEFAULT 'Connected',
                    data_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
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

            # Migration columns for history
            cursor = conn.execute("PRAGMA table_info(history)")
            existing_history_cols = {row["name"] for row in cursor.fetchall()}
            history_migrations = [
                ("is_pinned", "INTEGER DEFAULT 0"),
                ("is_favorite", "INTEGER DEFAULT 0"),
                ("status", "TEXT NOT NULL DEFAULT 'success'"),
                ("error_message", "TEXT"),
                ("audio_path", "TEXT"),
                ("insertion_status", "TEXT NOT NULL DEFAULT 'pasted'"),
                ("updated_at", "TEXT"),
                ("retry_count", "INTEGER NOT NULL DEFAULT 0"),
            ]
            for col_name, col_def in history_migrations:
                if col_name not in existing_history_cols:
                    try:
                        conn.execute(f"ALTER TABLE history ADD COLUMN {col_name} {col_def}")
                    except sqlite3.OperationalError:
                        pass
            conn.execute("UPDATE history SET status = COALESCE(NULLIF(status, ''), 'success'), insertion_status = COALESCE(NULLIF(insertion_status, ''), 'pasted'), updated_at = COALESCE(updated_at, timestamp), retry_count = COALESCE(retry_count, 0)")

            # Performance indices
            conn.execute("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON history (timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_history_app_name ON history (app_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_history_pinned ON history (is_pinned)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_history_duration ON history (duration_sec)")

            # Migration columns for provider_connections
            cursor = conn.execute("PRAGMA table_info(provider_connections)")
            existing_cols = {row["name"] for row in cursor.fetchall()}
            migrations = [
                ("uuid_id", "TEXT"),
                ("auth_type", "TEXT DEFAULT 'apikey'"),
                ("base_url", "TEXT"),
                ("organization", "TEXT"),
                ("account_id", "TEXT"),
                ("is_valid", "INTEGER DEFAULT 1"),
                ("last_tested_at", "TEXT"),
                ("last_error", "TEXT"),
                ("data_json", "TEXT"),
                ("updated_at", "TEXT"),
            ]
            for col_name, col_def in migrations:
                if col_name not in existing_cols:
                    try:
                        conn.execute(f"ALTER TABLE provider_connections ADD COLUMN {col_name} {col_def}")
                    except sqlite3.OperationalError:
                        pass
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tts_models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    UNIQUE(provider, model_id)
                )
            """)

            # Table 8: Audio Flow (TTS) Provider Multi-Key Connections
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audio_provider_connections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uuid_id TEXT,
                    provider TEXT NOT NULL,
                    auth_type TEXT DEFAULT 'apikey',
                    name TEXT NOT NULL,
                    api_key TEXT NOT NULL,
                    base_url TEXT,
                    organization TEXT,
                    account_id TEXT,
                    priority INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    is_valid INTEGER DEFAULT 1,
                    last_tested_at TEXT,
                    last_error TEXT,
                    last_tested_status TEXT DEFAULT 'Not Tested',
                    data_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
            """)

            # Migration columns for audio_provider_connections
            cursor = conn.execute("PRAGMA table_info(audio_provider_connections)")
            audio_cols = {row["name"] for row in cursor.fetchall()}
            for col_name, col_def in migrations:
                if col_name not in audio_cols:
                    try:
                        conn.execute(f"ALTER TABLE audio_provider_connections ADD COLUMN {col_name} {col_def}")
                    except sqlite3.OperationalError:
                        pass

            # Lexicon tables: explicit corrections, snippets, and normalized keys.
            # Corrections only run on an exact, user-declared phrase; snippets are
            # kept out of the dictionary so they never leak into Whisper's prompt.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dictionary_corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wrong_text TEXT COLLATE NOCASE UNIQUE NOT NULL,
                    correct_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snippets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trigger TEXT COLLATE NOCASE UNIQUE NOT NULL,
                    expansion TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snippet_keys (
                    normalized TEXT PRIMARY KEY NOT NULL,
                    snippet_id INTEGER UNIQUE NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS correction_keys (
                    normalized TEXT PRIMARY KEY NOT NULL,
                    correction_id INTEGER UNIQUE NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS migration_conflicts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    normalized_key TEXT NOT NULL,
                    current_record_id INTEGER NOT NULL,
                    legacy_key TEXT NOT NULL,
                    legacy_value TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            conn.commit()

        self._migrate_snippet_case_variants()
        self._migrate_correction_case_variants()
        self._migrate_legacy_dictionary_snippets()
        self._migrate_dictionary_case_variants()
        self._seed_default_models()
        self._seed_tts_models()

    _SEED_VERSION = "2"  # Bump to re-seed after adding new default models

    def _seed_tts_models(self) -> None:
        """Seed standard TTS models for Audio Flow."""
        tts_seeds = {
            "edge": [
                ("en-US-AvaNeural", "Edge Ava (Expressive Female - Free)"),
                ("en-US-AndrewNeural", "Edge Andrew (Natural Male - Free)"),
                ("en-US-EmmaNeural", "Edge Emma (Clear Female - Free)"),
                ("en-GB-SoniaNeural", "Edge Sonia (British Female - Free)"),
                ("en-IN-NeerjaNeural", "Edge Neerja (Indian Female - Free)"),
            ],
            "google": [
                ("en-US-Neural2-F", "Google Cloud Neural2 F (Female)"),
                ("en-US-Neural2-D", "Google Cloud Neural2 D (Male)"),
                ("en-US-Wavenet-C", "Google Cloud WaveNet C (Female)"),
                ("en-US-Standard-A", "Google Cloud Standard A (Male)"),
            ],
            "gemini": [
                ("gemini-2.5-flash-preview-tts:Kore", "Gemini Flash TTS — Kore (Warm Female)"),
                ("gemini-2.5-flash-preview-tts:Charon", "Gemini Flash TTS — Charon (Deep Male)"),
                ("gemini-2.5-flash-preview-tts:Puck", "Gemini Flash TTS — Puck (Playful)"),
                ("gemini-2.5-flash-preview-tts:Aoede", "Gemini Flash TTS — Aoede (Narrator)"),
                # Latest generation (verified against ai.google.dev, Aug 2026):
                # expressive audio tags + steerable prompts, lowest latency.
                ("gemini-3.1-flash-tts-preview:Kore", "Gemini 3.1 Flash TTS — Kore (Warm Female) ⚡ Latest"),
                ("gemini-3.1-flash-tts-preview:Puck", "Gemini 3.1 Flash TTS — Puck (Playful) ⚡ Latest"),
                ("gemini-3.1-flash-tts-preview:Zephyr", "Gemini 3.1 Flash TTS — Zephyr (Bright Female) ⚡ Latest"),
                ("gemini-3.1-flash-tts-preview:Orus", "Gemini 3.1 Flash TTS — Orus (Firm Male) ⚡ Latest"),
                # Pro tier for highest-quality narration.
                ("gemini-2.5-pro-preview-tts:Charon", "Gemini Pro TTS — Charon (Deep Male)"),
                ("gemini-2.5-pro-preview-tts:Aoede", "Gemini Pro TTS — Aoede (Narrator)"),
                ("gemini-2.5-pro-preview-tts:Leda", "Gemini Pro TTS — Leda (Youthful Female)"),
            ],
            "azure": [
                ("en-US-JennyNeural", "Azure Jenny (Warm Female)"),
                ("en-US-GuyNeural", "Azure Guy (Natural Male)"),
                ("en-US-AriaNeural", "Azure Aria (Narration Female)"),
                ("en-US-DavisNeural", "Azure Davis (Conversational Male)"),
            ],
            "fish": [
                ("s2.1-pro-free", "Fish Audio S2.1 Pro (Free)"),
            ],
            "nvidia": [
                ("chatterbox-multilingual-tts", "Chatterbox Multilingual TTS (NVIDIA NIM)"),
                ("English-US.Female-1", "NVIDIA Riva Female (English US)"),
                ("English-US.Male-1", "NVIDIA Riva Male (English US)"),
            ],
            "elevenlabs": [
                ("21m00Tcm4TlvDq8ikWAM", "ElevenLabs Rachel (Conversational)"),
                ("AZnzlk1XvdvUeBnXmlld", "ElevenLabs Domi (Energetic)"),
                ("EXAVITQu4vr4xnSDxMaL", "ElevenLabs Bella (Expressive)"),
                ("ErXwobaYiN019PkySvjV", "ElevenLabs Antoni (Deep Male)"),
            ],
            "deepgram": [
                ("aura-asteria-en", "Deepgram Aura Asteria (Warm Female)"),
                ("aura-luna-en", "Deepgram Aura Luna (Friendly Female)"),
                ("aura-zeus-en", "Deepgram Aura Zeus (Professional Male)"),
                ("aura-stella-en", "Deepgram Aura Stella (Energetic Female)"),
                ("aura-athena-en", "Deepgram Aura Athena (Calm Female)"),
                ("aura-hera-en", "Deepgram Aura Hera (Authoritative Female)"),
                ("aura-orion-en", "Deepgram Aura Orion (Conversational Male)"),
                ("aura-arcas-en", "Deepgram Aura Arcas (Deep Male)"),
                ("aura-perseus-en", "Deepgram Aura Perseus (Expressive Male)"),
                ("aura-angus-en", "Deepgram Aura Angus (British Male)"),
                ("aura-helios-en", "Deepgram Aura Helios (British Calm Male)"),
                ("aura-orpheus-en", "Deepgram Aura Orpheus (Storyteller Male)"),
            ],
            "openai": [
                ("tts-1:alloy", "OpenAI Alloy (Neutral)"),
                ("tts-1:echo", "OpenAI Echo (Male)"),
                ("tts-1:nova", "OpenAI Nova (Female)"),
                ("tts-1:fable", "OpenAI Fable (Storytelling)"),
            ],
            "offline": [
                ("sapi5", "Windows SAPI5 Native Voice (Free Offline)"),
            ]
        }
        with self._get_conn() as conn:
            for p, models in tts_seeds.items():
                for m_id, name in models:
                    conn.execute(
                        "INSERT OR IGNORE INTO tts_models (provider, model_id, display_name, is_active) VALUES (?, ?, ?, 1)",
                        (p, m_id, name)
                    )
            conn.commit()

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

    # --- History API ---

    def add_dictation(
        self,
        raw_text: str,
        polished_text: str,
        app_name: str = "General App",
        duration_sec: float = 2.0,
        style_mode: str = "smart_clean",
        status: str = "success",
        error_message: str | None = None,
        audio_path: str | None = None,
        insertion_status: str = "pasted",
    ) -> DictationRecord:
        words_list = polished_text.split()
        words = len(words_list)
        minutes = max(0.05, duration_sec / 60.0)
        wpm = int(words / minutes) if words > 0 else 0
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO history (timestamp, raw_text, polished_text, app_name, duration_sec, word_count, wpm_speed, style_mode, status, error_message, audio_path, insertion_status, updated_at, retry_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (now_str, raw_text, polished_text, app_name, duration_sec, words, wpm, style_mode, status, error_message, audio_path, insertion_status, now_str),
            )
            conn.commit()
            record_id = cursor.lastrowid

        # Dictation history is not authorization to rewrite future speech. Do
        # not auto-learn from polished output; explicit dictionary additions are
        # handled through the dictionary API.
        if self.get_setting("dictionary_auto_learning_enabled", False):
            self._auto_extract_dictionary_words(raw_text.split())

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
            status=status, error_message=error_message, audio_path=audio_path,
            insertion_status=insertion_status, updated_at=now_str,
        )

    def _auto_extract_dictionary_words(self, words: list[str]) -> None:
        """Frequency-based custom term learning.
        Only adds words spoken 3+ times across dictation history (or explicit jargon).
        """
        # Stopwords filter
        stopwords = {
            "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it", "for", "not", "on", "with", "he", "as",
            "you", "do", "at", "this", "but", "his", "by", "from", "they", "we", "say", "her", "she", "or", "an", "will",
            "my", "one", "all", "would", "there", "their", "what", "so", "up", "out", "if", "about", "who", "get", "which",
            "go", "me", "when", "make", "can", "like", "time", "no", "just", "him", "know", "take", "people", "into",
            "year", "your", "good", "some", "could", "them", "see", "other", "than", "then", "now", "look", "only",
            "come", "its", "over", "think", "also", "back", "after", "use", "two", "how", "our", "work", "first", "well",
            "way", "even", "new", "want", "because", "any", "these", "give", "day", "most", "us", "is", "are", "was",
            "were", "been", "being", "has", "had", "having", "does", "did", "doing", "would", "should", "could", "ought",
            "here", "there", "where", "why", "how", "all", "any", "both", "each", "few", "more", "most", "other", "some",
            "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "can", "will", "just", "should",
            "now", "today", "tomorrow", "yesterday", "please", "thanks", "thank", "hello", "hey", "hi", "ok", "okay"
        }

        for word in words:
            clean = re.sub(r"[^\w\-]", "", word, flags=re.UNICODE)
            if not clean or len(clean) < 3 or clean.casefold() in stopwords:
                continue

            # Only consider proper nouns, acronyms, technical terms, or camelCase.
            # Sentence-initial capitalization alone is not enough evidence.
            is_jargon = (
                clean.isupper() and len(clean) >= 3  # ALL CAPS acronym e.g. API, SQL
            ) or (
                any(c.isupper() for c in clean[1:]) and any(c.islower() for c in clean)  # CamelCase e.g. VoiceFlow
            ) or (
                clean[0].isupper() and clean[1:].islower() and len(clean) >= 4  # Capitalized proper noun e.g. Uzer
            )
            if not is_jargon:
                continue

            # Learn only from exact token occurrences in raw dictation.  SQL
            # substring matching made API match CAPITAL and let polished/AI
            # output authorize future replacements.
            try:
                with self._get_conn() as conn:
                    rows = conn.execute("SELECT raw_text FROM history").fetchall()
                token_pattern = re.compile(
                    rf"(?<![\w-]){re.escape(clean)}(?![\w-])",
                    flags=re.IGNORECASE | re.UNICODE,
                )
                occurrences = sum(
                    len(token_pattern.findall(str(row["raw_text"] or "")))
                    for row in rows
                )
                if occurrences >= 3:
                    self.add_dictionary_word(clean, category="Auto-Captured")
            except Exception:
                log.exception("Could not evaluate auto-captured dictionary term %r", clean)

    def get_recent_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM history ORDER BY is_pinned DESC, id DESC LIMIT ?", (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def toggle_history_pin(self, record_id: int) -> dict[str, Any]:
        """Toggle is_pinned for a history record."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT is_pinned FROM history WHERE id = ?", (record_id,))
            row = cursor.fetchone()
            if not row:
                return {"success": False, "error": "Record not found"}
            current_pinned = int(row["is_pinned"] or 0)
            new_pinned = 0 if current_pinned else 1
            conn.execute("UPDATE history SET is_pinned = ? WHERE id = ?", (new_pinned, record_id))
            conn.commit()
            return {"success": True, "id": record_id, "is_pinned": bool(new_pinned)}

    def get_insights(self, range_filter: str = "all") -> dict[str, Any]:
        """Compute rich desktop dictation telemetry and insights metrics."""
        with self._get_conn() as conn:
            date_cond = ""
            if range_filter == "7d":
                date_cond = " AND timestamp >= datetime('now', 'localtime', '-7 days')"
            elif range_filter == "30d":
                date_cond = " AND timestamp >= datetime('now', 'localtime', '-30 days')"

            # Filter out historical zero-duration records to fix average WPM calculation
            total_words = conn.execute(f"SELECT COALESCE(SUM(word_count), 0) FROM history WHERE duration_sec > 0.1 {date_cond}").fetchone()[0]
            avg_wpm_val = conn.execute(f"SELECT COALESCE(AVG(wpm_speed), 0) FROM history WHERE duration_sec > 0.1 AND wpm_speed > 0 AND wpm_speed < 300 {date_cond}").fetchone()[0]
            total_duration_sec = conn.execute(f"SELECT COALESCE(SUM(duration_sec), 0) FROM history WHERE duration_sec > 0.1 {date_cond}").fetchone()[0]
            dictation_count = conn.execute(f"SELECT COUNT(*) FROM history WHERE duration_sec > 0.1 {date_cond}").fetchone()[0]
            
            explicit_dict_rows = conn.execute(
                "SELECT word FROM dictionary WHERE LOWER(category) != ?",
                ("auto-captured",),
            ).fetchall()
            explicit_dict_words = [str(row["word"]) for row in explicit_dict_rows]
            total_dict_words = len(explicit_dict_words)

            # Calculate actual WPM based on total words spoken / total duration in minutes
            if total_duration_sec > 1.0 and total_words > 0:
                avg_wpm = int((total_words / total_duration_sec) * 60.0)
            else:
                avg_wpm = int(avg_wpm_val) if avg_wpm_val > 0 else 0

            # Calculate Time Saved: Average typing speed = 40 WPM
            typing_time_min = total_words / 40.0 if total_words > 0 else 0
            dictating_time_min = total_duration_sec / 60.0 if total_duration_sec > 0 else 0
            saved_minutes = max(0.0, typing_time_min - dictating_time_min)
            saved_hours = round(saved_minutes / 60.0, 1)

            # Speed Multiplier vs Typing (40 WPM)
            speed_multiplier = round(avg_wpm / 40.0, 1) if avg_wpm > 0 else 1.0

            # REAL FIXES METRICS: Calculate actual diffs between raw_text and polished_text
            cursor = conn.execute(f"SELECT raw_text, polished_text FROM history WHERE duration_sec > 0.1 {date_cond}")
            rows = cursor.fetchall()
            words_corrected_count = 0
            dictionary_fixes_count = 0

            for row in rows:
                r_text = row["raw_text"] or ""
                p_text = row["polished_text"] or ""
                if r_text.strip() != p_text.strip():
                    r_words = r_text.split()
                    p_words = p_text.split()
                    diff = abs(len(p_words) - len(r_words))
                    words_corrected_count += max(1, diff)

                for entry in explicit_dict_words:
                    parsed = self._parse_dictionary_value(entry)
                    if not parsed:
                        continue
                    trigger, expansion = parsed
                    raw_count = _dictionary_term_occurrences(r_text, trigger)
                    polished_trigger_count = _dictionary_term_occurrences(p_text, trigger)
                    if expansion is not None:
                        dictionary_fixes_count += max(0, raw_count - polished_trigger_count)
                    else:
                        dictionary_fixes_count += max(
                            0,
                            _dictionary_term_occurrences(p_text, trigger) - raw_count,
                        )

            polishing_enabled = self.get_setting("polishing_enabled", True)
            if not polishing_enabled:
                ai_refinements = dictionary_fixes_count
                words_corrected_count = 0
            else:
                ai_refinements = words_corrected_count + dictionary_fixes_count

            # App breakdown with percentage calculation and category tagging
            cursor = conn.execute(
                f"""
                SELECT app_name, COUNT(*) as count, SUM(word_count) as total_words
                FROM history
                WHERE duration_sec > 0.1 AND word_count > 0
                  AND app_name NOT IN ('Captured App', 'Pythonw', 'Hub', 'Initiating A New Conversa...')
                  {date_cond}
                GROUP BY app_name
                ORDER BY total_words DESC
                """
            )
            app_breakdown_raw = [dict(row) for row in cursor.fetchall()]
            merged_apps: dict[str, dict[str, Any]] = {}

            for app in app_breakdown_raw:
                raw_name = app.get("app_name", "General App") or "General App"
                clean_name = re.sub(r"[^\w\s]", "", raw_name).strip()
                key = clean_name.lower()

                display_name = raw_name.strip()
                category_tag = "Other"
                if "chatgpt" in key or "claude" in key or "copilot" in key:
                    display_name = "ChatGPT" if "chatgpt" in key else ("Claude Code" if "claude" in key else "AI Assistant")
                    category_tag = "AI & Chat"
                elif "chrome" in key or "edge" in key or "brave" in key or "firefox" in key:
                    display_name = "Google Chrome" if "chrome" in key else ("Microsoft Edge" if "edge" in key else "Web Browser")
                    category_tag = "Browsing"
                elif "vscode" in key or "vs code" in key or "visual studio" in key or "cursor" in key or "pycharm" in key or "sublime" in key:
                    display_name = "Visual Studio Code" if ("vscode" in key or "vs code" in key or "visual studio" in key) else ("Cursor" if "cursor" in key else "Code Editor")
                    category_tag = "Coding"
                elif "terminal" in key or "cmd" in key or "powershell" in key or "bash" in key:
                    display_name = "Windows Terminal"
                    category_tag = "Coding"
                elif "slack" in key or "teams" in key or "discord" in key or "whatsapp" in key or "telegram" in key:
                    display_name = "Slack" if "slack" in key else ("Teams" if "teams" in key else ("Discord" if "discord" in key else "Messaging"))
                    category_tag = "Communication"
                elif "notion" in key or "word" in key or "docs" in key or "obsidian" in key or "notes" in key:
                    display_name = "Notion" if "notion" in key else ("Word" if "word" in key else "Notes & Docs")
                    category_tag = "Writing"

                w_count = app.get("total_words", 0) or 0
                c_count = app.get("count", 0) or 0

                # Merge on the canonical display name: distinct raw window
                # titles ("claude", "claude code") must not surface as
                # duplicate rows once they resolve to the same display name.
                if display_name in merged_apps:
                    merged_apps[display_name]["total_words"] += w_count
                    merged_apps[display_name]["count"] += c_count
                else:
                    merged_apps[display_name] = {
                        "app_name": display_name,
                        "category": category_tag,
                        "count": c_count,
                        "total_words": w_count,
                    }

            sorted_merged = sorted(merged_apps.values(), key=lambda x: x["total_words"], reverse=True)
            app_breakdown = []
            for app in sorted_merged:
                w_count = app["total_words"]
                pct = round((w_count / total_words * 100), 1) if total_words > 0 else 0
                app_breakdown.append({
                    "app_name": app["app_name"],
                    "category": app.get("category", "General"),
                    "count": app["count"],
                    "total_words": w_count,
                    "percentage": pct,
                })

            # 28-day activity heatmap (4 weeks x 7 days)
            daily_activity = []
            today = datetime.date.today()
            for i in range(27, -1, -1):
                day = today - datetime.timedelta(days=i)
                day_str = day.strftime("%Y-%m-%d")
                w_on_day = conn.execute(
                    "SELECT COALESCE(SUM(word_count), 0) FROM history WHERE DATE(timestamp) = ?", (day_str,)
                ).fetchone()[0]
                w_int = int(w_on_day or 0)
                if w_int == 0:
                    lvl = 0
                elif w_int < 50:
                    lvl = 1
                elif w_int < 150:
                    lvl = 2
                elif w_int < 350:
                    lvl = 3
                else:
                    lvl = 4

                daily_activity.append({
                    "date": day_str,
                    "day_name": day.strftime("%a"),
                    "words": w_int,
                    "level": lvl,
                })

            # Calculate Streak
            cursor = conn.execute("SELECT DISTINCT DATE(timestamp) as date_val FROM history ORDER BY date_val DESC")
            dates = [row["date_val"] for row in cursor.fetchall()]
            streak = 0
            check_date = today
            for d_str in dates:
                try:
                    d_obj = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
                except Exception:
                    continue
                if d_obj == check_date:
                    streak += 1
                    check_date -= datetime.timedelta(days=1)
                elif streak == 0 and check_date == today and d_obj == check_date - datetime.timedelta(days=1):
                    # Today has no dictation yet; start the streak from
                    # yesterday. Once the chain has started, a missed day
                    # must break it instead of being skipped.
                    streak += 1
                    check_date = d_obj - datetime.timedelta(days=1)
                elif d_obj < check_date - datetime.timedelta(days=1):
                    break

            # Longest streak: walk the full historical activity-day list so a
            # record set broken weeks ago still reports its best run.
            longest_streak = 0
            run = 0
            previous: datetime.date | None = None
            for d_str in reversed(dates):
                try:
                    d_obj = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
                except Exception:
                    continue
                if previous is not None and (d_obj - previous).days == 1:
                    run += 1
                else:
                    run = 1
                longest_streak = max(longest_streak, run)
                previous = d_obj

            # Hourly Time-of-Day Velocity Buckets
            cursor = conn.execute(
                f"""
                SELECT
                    SUM(CASE WHEN CAST(STRFTIME('%H', timestamp) AS INT) BETWEEN 6 AND 11 THEN word_count ELSE 0 END) as morning_words,
                    SUM(CASE WHEN CAST(STRFTIME('%H', timestamp) AS INT) BETWEEN 12 AND 16 THEN word_count ELSE 0 END) as afternoon_words,
                    SUM(CASE WHEN CAST(STRFTIME('%H', timestamp) AS INT) BETWEEN 17 AND 21 THEN word_count ELSE 0 END) as evening_words,
                    SUM(CASE WHEN CAST(STRFTIME('%H', timestamp) AS INT) >= 22 OR CAST(STRFTIME('%H', timestamp) AS INT) <= 5 THEN word_count ELSE 0 END) as night_words
                FROM history
                WHERE duration_sec > 0.1 {date_cond}
                """
            )
            tod_row = cursor.fetchone()
            m_words = int(tod_row[0] or 0) if tod_row else 0
            a_words = int(tod_row[1] or 0) if tod_row else 0
            e_words = int(tod_row[2] or 0) if tod_row else 0
            n_words = int(tod_row[3] or 0) if tod_row else 0
            tod_sum = m_words + a_words + e_words + n_words
            tod_total = max(1, tod_sum)
            time_of_day = [
                {"period": "morning", "label": "Morning", "time_range": "6 AM - 12 PM", "icon": "🌅", "words": m_words, "pct": round(m_words / tod_total * 100, 1) if tod_sum > 0 else 25},
                {"period": "afternoon", "label": "Afternoon", "time_range": "12 PM - 5 PM", "icon": "☀️", "words": a_words, "pct": round(a_words / tod_total * 100, 1) if tod_sum > 0 else 25},
                {"period": "evening", "label": "Evening", "time_range": "5 PM - 10 PM", "icon": "🌆", "words": e_words, "pct": round(e_words / tod_total * 100, 1) if tod_sum > 0 else 25},
                {"period": "night", "label": "Night", "time_range": "10 PM - 6 AM", "icon": "🌙", "words": n_words, "pct": round(n_words / tod_total * 100, 1) if tod_sum > 0 else 25},
            ]

            # Calculate Peak Hours dynamically from history timestamps
            cursor = conn.execute(f"SELECT STRFTIME('%H', timestamp) as hour, COUNT(*) as count FROM history WHERE duration_sec > 0.1 {date_cond} GROUP BY hour ORDER BY count DESC LIMIT 1")
            peak_row = cursor.fetchone()
            if peak_row and peak_row["hour"]:
                h_int = int(peak_row["hour"])
                h12 = h_int % 12 or 12
                ampm = "AM" if h_int < 12 else "PM"
                h_next = (h_int + 1) % 12 or 12
                ampm_next = "AM" if (h_int + 1) < 12 or (h_int + 1) == 24 else "PM"
                peak_hours_str = f"{h12}:00 {ampm} – {h_next}:00 {ampm_next}"
            else:
                peak_hours_str = "Morning (9:00 AM – 12:00 PM)"

            # Calculate Most Frequent Phrase dynamically
            cursor = conn.execute(f"SELECT raw_text FROM history WHERE duration_sec > 0.1 {date_cond} ORDER BY id DESC LIMIT 50")
            phrase_rows = cursor.fetchall()
            phrase_counts: dict[str, int] = {}
            for pr in phrase_rows:
                p_raw = pr["raw_text"] or ""
                p_words = p_raw.strip().split()
                if len(p_words) >= 3:
                    trigram = " ".join(p_words[:4])
                    phrase_counts[trigram] = phrase_counts.get(trigram, 0) + 1
            top_phrase_str = max(phrase_counts, key=phrase_counts.get) if phrase_counts else "General Dictation"

            # Voice Archetype Determination
            top_app = (app_breakdown[0]["app_name"].lower() if app_breakdown else "")
            top_cat = (app_breakdown[0]["category"].lower() if app_breakdown else "")
            if total_words == 0:
                archetype_title = "Getting Started"
                archetype_desc = "Ready to record your first dictation. Press your hotkey to start!"
                archetype_tag = "Getting Started"
                archetype_icon = "🎙️"
            elif top_cat == "coding" or any(k in top_app for k in ["code", "terminal", "powershell", "cursor", "pycharm", "visual studio"]):
                archetype_title = "The Code Architect"
                archetype_desc = "Transforms mental algorithms, code syntax, and technical logic directly into editor workflows at lightning speed."
                archetype_tag = "Engineering Flow"
                archetype_icon = "💻"
            elif top_cat == "communication" or any(k in top_app for k in ["slack", "teams", "discord", "whatsapp"]):
                archetype_title = "The Collaborative Leader"
                archetype_desc = "Drives rapid cross-functional alignment, concise feedback, and seamless team momentum."
                archetype_tag = "Leadership & Comms"
                archetype_icon = "🤝"
            elif top_cat == "writing" or any(k in top_app for k in ["notion", "docs", "word", "notes"]):
                archetype_title = "The Strategic Synthesizer"
                archetype_desc = "Drafts comprehensive essays, strategic specs, and deep knowledge repositories effortlessly."
                archetype_tag = "Strategy & Writing"
                archetype_icon = "✍️"
            elif total_words > 3000:
                archetype_title = "The High-Velocity Orator"
                archetype_desc = "Speaks at peak velocity, outpacing traditional keyboard input by multiple orders of magnitude."
                archetype_tag = "Productivity Elite"
                archetype_icon = "🚀"
            else:
                archetype_title = "The Rapid Thinker"
                archetype_desc = "Captures raw thoughts, stream-of-consciousness ideas, and daily tasks with natural flow."
                archetype_tag = "General Flow"
                archetype_icon = "⚡"

            return {
                "total_words": total_words,
                "avg_wpm": avg_wpm,
                "dictation_count": dictation_count,
                "time_saved_hours": saved_hours,
                "time_saved_minutes": round(saved_minutes, 1),
                "speed_multiplier": speed_multiplier,
                "ai_refinements": ai_refinements,
                "words_corrected": words_corrected_count,
                "dictionary_fixes": dictionary_fixes_count,
                "total_dictionary_terms": total_dict_words,
                "streak": max(streak, 1 if total_words > 0 else 0),
                "longest_streak": longest_streak,
                "app_breakdown": app_breakdown,
                "daily_activity": daily_activity,
                "time_of_day": time_of_day,
                "voice_profile": {
                    "archetype": archetype_title,
                    "archetype_desc": archetype_desc,
                    "archetype_tag": archetype_tag,
                    "archetype_icon": archetype_icon,
                    "peak_hours": peak_hours_str,
                    "top_phrase": top_phrase_str,
                    "speed_multiplier": speed_multiplier,
                    "vocabulary_unlocked": True if (total_words >= 500 or total_dict_words > 0) else False,
                }
            }

    # --- Dictionary API ---

    def get_dictionary_entries(self, include_auto: bool = True) -> list[dict[str, Any]]:
        """Return dictionary rows with provenance for the vocabulary engine."""
        query = "SELECT id, word, category, created_at FROM dictionary"
        params: tuple[Any, ...] = ()
        if not include_auto:
            query += " WHERE LOWER(category) != ?"
            params = ("auto-captured",)
        query += " ORDER BY id ASC"
        with self._get_conn() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def get_dictionary_revision(self) -> int:
        """Return a monotonic revision used to refresh in-process vocabulary."""
        with self._get_conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'dictionary_revision'").fetchone()
            try:
                return int(row["value"]) if row else 0
            except (TypeError, ValueError):
                return 0

    def _bump_dictionary_revision(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT value FROM settings WHERE key = 'dictionary_revision'").fetchone()
        try:
            revision = int(row[0]) if row else 0
        except (TypeError, ValueError):
            revision = 0
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('dictionary_revision', ?, ?)",
            (str(revision + 1), datetime.datetime.now().isoformat()),
        )

    def get_dictionary_words(self, include_auto: bool = False) -> list[str]:
        """Return active explicit vocabulary by default; auto-captured rows are metadata."""
        return [row["word"] for row in self.get_dictionary_entries(include_auto=include_auto)]

    @staticmethod
    def _parse_dictionary_value(word: object) -> tuple[str, str | None] | None:
        if not isinstance(word, str):
            return None
        value = word.strip()
        if not value:
            return None
        for delimiter in ("->", "=>"):
            if delimiter in value:
                trigger, expansion = value.split(delimiter, 1)
                trigger = trigger.strip()
                expansion = expansion.strip()
                if not trigger or not expansion:
                    return None
                return trigger, expansion
        return value, None

    def add_dictionary_word(self, word: str, category: str = "Personal") -> bool:
        if not isinstance(word, str):
            return False
        word_clean = word.strip()
        if "->" in word_clean or "=>" in word_clean:
            return False
        parsed = self._parse_dictionary_value(word)
        if parsed is None:
            return False
        category_clean = str(category).strip() or "Personal"
        now = datetime.datetime.now().isoformat()
        try:
            with self._get_conn() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute("SELECT word FROM dictionary").fetchall()
                folded = word_clean.casefold()
                if any(str(row["word"]).casefold() == folded for row in existing):
                    return False
                conn.execute(
                    "INSERT INTO dictionary (word, category, created_at) VALUES (?, ?, ?)",
                    (word_clean, category_clean, now),
                )
                self._bump_dictionary_revision(conn)
                conn.commit()
                return True
        except (sqlite3.IntegrityError, sqlite3.OperationalError):
            return False

    def remove_dictionary_word(self, word: str) -> bool:
        if not isinstance(word, str):
            return False
        word_clean = word.strip()
        if not word_clean:
            return False
        with self._get_conn() as conn:
            rows = conn.execute("SELECT id, word FROM dictionary").fetchall()
            matching_ids = [
                row["id"] for row in rows
                if str(row["word"]).casefold() == word_clean.casefold()
            ]
            if not matching_ids:
                return False
            placeholders = ",".join("?" for _ in matching_ids)
            cursor = conn.execute(
                f"DELETE FROM dictionary WHERE id IN ({placeholders})",
                matching_ids,
            )
            if cursor.rowcount:
                self._bump_dictionary_revision(conn)
            conn.commit()
            return cursor.rowcount > 0

    def _remove_stale_auto_captured_words(self) -> None:
        """Drop auto-captured terms that no longer occur in raw history."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, word FROM dictionary WHERE LOWER(category) = ?",
                ("auto-captured",),
            ).fetchall()
            history_rows = conn.execute("SELECT raw_text FROM history").fetchall()
            stale_ids = [
                row["id"]
                for row in rows
                if _raw_token_occurrences(history_rows, str(row["word"])) == 0
            ]
            if not stale_ids:
                return
            placeholders = ",".join("?" for _ in stale_ids)
            conn.execute(
                f"DELETE FROM dictionary WHERE id IN ({placeholders})",
                stale_ids,
            )
            self._bump_dictionary_revision(conn)
            conn.commit()


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

    def add_provider_connection(
        self,
        provider: str,
        name: str,
        api_key: str,
        priority: int = 0,
        base_url: str | None = None,
        organization: str | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        import uuid
        now = datetime.datetime.now().isoformat()
        clean_key = api_key.strip()
        clean_name = name.strip() or f"{provider.capitalize()} Key"
        uuid_str = str(uuid.uuid4())

        data_obj = {
            "apiKey": clean_key,
            "baseUrl": base_url or "",
            "organization": organization or "",
            "accountId": account_id or "",
            "isValid": True,
            "lastTestedAt": now,
            "lastError": None,
        }
        data_json = json.dumps(data_obj)

        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO provider_connections (
                    uuid_id, provider, auth_type, name, api_key, base_url, organization, account_id,
                    priority, is_active, is_valid, last_tested_at, last_error, last_tested_status,
                    data_json, created_at, updated_at
                )
                VALUES (?, ?, 'apikey', ?, ?, ?, ?, ?, ?, 1, 1, ?, NULL, 'Connected', ?, ?, ?)
                """,
                (
                    uuid_str, provider.lower(), clean_name, clean_key, base_url, organization, account_id,
                    priority, now, data_json, now, now
                )
            )
            conn.commit()
            cid = cursor.lastrowid
        self.save_api_key(clean_key, provider.lower())
        return {
            "id": cid,
            "uuid_id": uuid_str,
            "provider": provider.lower(),
            "authType": "apikey",
            "name": clean_name,
            "api_key": clean_key,
            "baseUrl": base_url or "",
            "priority": priority,
            "is_active": 1,
            "is_valid": 1,
            "last_tested_status": "Connected",
            "data": data_obj,
            "created_at": now,
        }

    def update_provider_connection_validation(
        self,
        cid: int,
        is_valid: bool,
        last_error: str | None = None,
    ) -> None:
        now = datetime.datetime.now().isoformat()
        status = "Connected" if is_valid else (last_error or "Validation Failed")
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE provider_connections
                SET is_valid = ?, last_tested_at = ?, last_error = ?, last_tested_status = ?, updated_at = ?
                WHERE id = ?
                """,
                (1 if is_valid else 0, now, last_error, status, now, cid)
            )
            conn.commit()

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

    def get_exec_policy_options(self) -> dict[str, Any]:
        with self._get_conn() as conn:
            conn_rows = conn.execute("SELECT * FROM provider_connections WHERE is_active = 1 ORDER BY priority ASC").fetchall()
            conns = [dict(r) for r in conn_rows]

            connected_providers = {c["provider"].lower() for c in conns}
            if not connected_providers:
                connected_providers = {"gemini"}

            provider_names = {
                "gemini": "Google Gemini",
                "groq": "Groq Audio",
                "elevenlabs": "ElevenLabs",
                "deepgram": "Deepgram Speech",
                "openai": "OpenAI Voice",
                "assemblyai": "AssemblyAI",
                "huggingface": "Hugging Face",
                "cloudflare": "Cloudflare AI",
                "together": "Together AI",
                "replicate": "Replicate Voice"
            }

            provider_logos = {
                "gemini": "✨",
                "groq": "⚡",
                "elevenlabs": "🎙️",
                "deepgram": "🎧",
                "openai": "🤖",
                "assemblyai": "🗣️",
                "huggingface": "🤗",
                "cloudflare": "☁️",
                "together": "🤝",
                "replicate": "🚀"
            }

            placeholders = ",".join("?" for _ in connected_providers)
            query = f"SELECT * FROM provider_models WHERE is_active = 1 AND LOWER(provider) IN ({placeholders}) ORDER BY provider ASC, id ASC"
            model_rows = conn.execute(query, list(connected_providers)).fetchall()

            models = []
            grouped_models = {}
            for r in model_rows:
                p = r["provider"].lower()
                p_name = provider_names.get(p, p.capitalize())
                p_logo = provider_logos.get(p, "🔌")
                full_id = f"{p}/{r['model_id']}"
                label = f"{p_name} — {r['display_name']}"
                m_text = f"{r['model_id']} {r['display_name']} {p}".lower()
                has_vis = any(k in m_text for k in ["vision", "multimodal", "flash", "aria", "jenny", "pro", "gemini", "gpt", "chatterbox", "narrator"])
                has_br = True  # All neural AI models have brain/reasoning capability
                item = {
                    "full_id": full_id,
                    "label": label,
                    "provider": p,
                    "provider_name": p_name,
                    "provider_logo": p_logo,
                    "model_id": r["model_id"],
                    "display_name": r["display_name"],
                    "has_vision": has_vis,
                    "has_brain": has_br
                }
                models.append(item)

                if p not in grouped_models:
                    grouped_models[p] = {
                        "provider": p,
                        "provider_name": p_name,
                        "provider_logo": p_logo,
                        "models": []
                    }
                grouped_models[p]["models"].append(item)

            active_model = self.get_setting("exec_policy_model", "gemini/gemini-2.5-flash")
            polishing_enabled = self.get_setting("polishing_enabled", True)

            return {
                "active_model": active_model,
                "polishing_enabled": polishing_enabled,
                "connections": conns,
                "failover_count": len(conns),
                "models": models,
                "grouped_models": list(grouped_models.values())
            }

    def get_exec_audio_policy_options(self) -> dict[str, Any]:
        with self._get_conn() as conn:
            # Use all connections from both audio_provider_connections and provider_connections
            # so models from any saved provider appear in the model selector.
            conn_rows = conn.execute("SELECT * FROM audio_provider_connections ORDER BY priority ASC").fetchall()
            conns = [dict(r) for r in conn_rows]
            connected_providers = {c["provider"].lower() for c in conns if c.get("api_key")}

            alt_rows = conn.execute("SELECT * FROM provider_connections ORDER BY priority ASC").fetchall()
            alt_conns = [dict(r) for r in alt_rows]
            connected_providers.update({c["provider"].lower() for c in alt_conns if c.get("api_key")})

            connected_providers.add("edge")
            connected_providers.add("offline")

            provider_names = {
                "edge": "Microsoft Edge Neural",
                "elevenlabs": "ElevenLabs",
                "deepgram": "Deepgram Aura",
                "openai": "OpenAI TTS",
                "offline": "Windows Offline SAPI5",
                "google": "Google Cloud TTS",
                "gemini": "Gemini AI TTS",
                "azure": "Microsoft Azure Speech",
                "fish": "Fish Audio",
                "nvidia": "NVIDIA Riva"
            }

            provider_logos = {
                "edge": "✨",
                "elevenlabs": "🎙️",
                "deepgram": "🎧",
                "openai": "🤖",
                "offline": "💻",
                "google": "☁️",
                "gemini": "💎",
                "azure": "🔷",
                "fish": "🐟",
                "nvidia": "🟢"
            }

            placeholders = ",".join("?" for _ in connected_providers)
            # Show all models for connected providers regardless of is_active flag
            # (is_active on tts_models only gates individual voice toggles in the detail view,
            # not whether the provider's voices appear in the model selector at all)
            query = f"SELECT * FROM tts_models WHERE LOWER(provider) IN ({placeholders}) ORDER BY provider ASC, id ASC"
            model_rows = conn.execute(query, list(connected_providers)).fetchall()

            models = []
            grouped_models = {}
            for r in model_rows:
                p = r["provider"].lower()
                p_name = provider_names.get(p, p.capitalize())
                p_logo = provider_logos.get(p, "🔊")
                full_id = f"{p}/{r['model_id']}"
                label = f"{p_name} — {r['display_name']}"
                m_text = f"{r['model_id']} {r['display_name']} {p}".lower()
                has_vis = any(k in m_text for k in ["vision", "multimodal", "flash", "aria", "jenny", "pro", "gemini", "gpt", "chatterbox", "narrator"])
                has_br = True  # All neural AI models have brain/reasoning capability
                item = {
                    "full_id": full_id,
                    "label": label,
                    "provider": p,
                    "provider_name": p_name,
                    "provider_logo": p_logo,
                    "model_id": r["model_id"],
                    "display_name": r["display_name"],
                    "has_vision": has_vis,
                    "has_brain": has_br
                }
                models.append(item)

                if p not in grouped_models:
                    grouped_models[p] = {
                        "provider": p,
                        "provider_name": p_name,
                        "provider_logo": p_logo,
                        "models": []
                    }
                grouped_models[p]["models"].append(item)

            active_model = self.get_setting("exec_audio_policy_model", "edge/en-US-AvaNeural")
            audio_flow_enabled = self.get_setting("audio_flow_enabled", True)
            audio_flow_speed = self.get_setting("audio_flow_speed", 1.0)

            return {
                "active_model": active_model,
                "audio_flow_enabled": audio_flow_enabled,
                "audio_flow_speed": audio_flow_speed,
                "connections": conns,
                "failover_count": len(conns),
                "models": models,
                "grouped_models": list(grouped_models.values())
            }

    def toggle_tts_model(self, model_db_id: int, is_active: bool) -> bool:
        """Enable or disable a TTS voice model in tts_models table."""
        with self._get_conn() as conn:
            cursor = conn.execute("UPDATE tts_models SET is_active = ? WHERE id = ?", (1 if is_active else 0, model_db_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_audio_provider_connections(self, provider: str) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM audio_provider_connections WHERE provider = ? ORDER BY priority ASC, id ASC",
                (provider.lower(),)
            )
            rows = [dict(row) for row in cursor.fetchall()]
            has_key = any(r.get("api_key", "").strip() for r in rows)
            if not has_key:
                alt_cursor = conn.execute(
                    "SELECT * FROM provider_connections WHERE provider = ? ORDER BY priority ASC, id ASC",
                    (provider.lower(),)
                )
                alt_rows = [dict(row) for row in alt_cursor.fetchall()]
                if alt_rows:
                    return alt_rows
            return rows

    def get_all_audio_provider_connections(self) -> dict[str, list[dict[str, Any]]]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM audio_provider_connections ORDER BY provider ASC, priority ASC, id ASC")
            result: dict[str, list[dict[str, Any]]] = {}
            for row in cursor.fetchall():
                p = row["provider"]
                if p not in result:
                    result[p] = []
                result[p].append(dict(row))
            return result

    def add_audio_provider_connection(
        self,
        provider: str,
        name: str,
        api_key: str,
        priority: int = 0,
        base_url: str | None = None,
        organization: str | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        import uuid
        now = datetime.datetime.now().isoformat()
        clean_key = api_key.strip()
        clean_name = name.strip() or f"{provider.capitalize()} Key"
        uuid_str = str(uuid.uuid4())

        data_obj = {
            "apiKey": clean_key,
            "baseUrl": base_url or "",
            "organization": organization or "",
            "accountId": account_id or "",
            "isValid": True,
            "lastTestedAt": now,
            "lastError": None,
        }
        data_json = json.dumps(data_obj)

        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO audio_provider_connections (
                    uuid_id, provider, auth_type, name, api_key, base_url, organization, account_id,
                    priority, is_active, is_valid, last_tested_at, last_error, last_tested_status,
                    data_json, created_at, updated_at
                )
                VALUES (?, ?, 'apikey', ?, ?, ?, ?, ?, ?, 1, 1, ?, NULL, 'Not Tested', ?, ?, ?)
                """,
                (
                    uuid_str, provider.lower(), clean_name, clean_key, base_url, organization, account_id,
                    priority, now, data_json, now, now
                )
            )
            conn.commit()
            cid = cursor.lastrowid
        return {
            "id": cid,
            "uuid_id": uuid_str,
            "provider": provider.lower(),
            "authType": "apikey",
            "name": clean_name,
            "api_key": clean_key,
            "baseUrl": base_url or "",
            "priority": priority,
            "is_active": 1,
            "is_valid": 1,
            "last_tested_status": "Not Tested",
            "data": data_obj,
            "created_at": now,
        }

    def update_audio_provider_connection_validation(
        self,
        cid: int,
        is_valid: bool,
        last_error: str | None = None,
    ) -> None:
        now = datetime.datetime.now().isoformat()
        status = "Connected" if is_valid else (last_error or "Validation Failed")
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE audio_provider_connections
                SET is_valid = ?, last_tested_at = ?, last_error = ?, last_tested_status = ?, updated_at = ?
                WHERE id = ?
                """,
                (1 if is_valid else 0, now, last_error, status, now, cid)
            )
            conn.commit()

    def toggle_audio_provider_connection(self, cid: int, is_active: bool) -> bool:
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE audio_provider_connections SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, cid)
            )
            conn.commit()
            return True

    def toggle_audio_provider_master(self, provider_id: str, is_active: bool) -> bool:
        """Enable/disable all connections and TTS models for a given audio provider."""
        active_val = 1 if is_active else 0
        p_lower = provider_id.lower()
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE audio_provider_connections SET is_active = ? WHERE provider = ?",
                (active_val, p_lower)
            )
            conn.execute(
                "UPDATE tts_models SET is_active = ? WHERE provider = ?",
                (active_val, p_lower)
            )
            conn.commit()
            return True

    def delete_audio_provider_connection(self, cid: int) -> bool:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM audio_provider_connections WHERE id = ?", (cid,))
            conn.commit()
            return True

    def update_audio_provider_connection_status(self, cid: int, status: str) -> None:
        with self._get_conn() as conn:
            conn.execute("UPDATE audio_provider_connections SET last_tested_status = ? WHERE id = ?", (status, cid))
            conn.commit()

    def get_audio_providers_overview(self) -> list[dict]:
        tts_providers = [
            {"id": "google", "name": "Google Cloud TTS", "logo": "☁️", "key_link": "https://console.cloud.google.com/apis/credentials"},
            {"id": "gemini", "name": "Gemini AI TTS", "logo": "💎", "key_link": "https://aistudio.google.com/apikey"},
            {"id": "azure", "name": "Microsoft Azure Speech", "logo": "🔷", "key_link": "https://portal.azure.com/#create/Microsoft.CognitiveServicesSpeechServices"},
            {"id": "fish", "name": "Fish Audio", "logo": "🐟", "key_link": "https://fish.audio/api"},
            {"id": "nvidia", "name": "NVIDIA Riva", "logo": "🟢", "key_link": "https://build.nvidia.com"},
            {"id": "elevenlabs", "name": "ElevenLabs", "logo": "🎙️", "key_link": "https://elevenlabs.io/api"},
            {"id": "deepgram", "name": "Deepgram Aura", "logo": "🎧", "key_link": "https://console.deepgram.com"},
            {"id": "openai", "name": "OpenAI TTS", "logo": "🤖", "key_link": "https://platform.openai.com/api-keys"},
        ]
        all_conns = self.get_all_audio_provider_connections()
        for p in tts_providers:
            conns = all_conns.get(p["id"], [])
            p["connection_count"] = len(conns)
            p["is_connected"] = any(c.get("is_active") for c in conns)
        return tts_providers

    def get_tts_models_for_provider(self, provider: str) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM tts_models WHERE provider = ? ORDER BY id ASC", (provider.lower(),)).fetchall()
            return [dict(r) for r in rows]

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
        if not isinstance(key, str) or not key.strip():
            return False
        import json as _json
        now = datetime.datetime.now().isoformat()
        # Serialize strings too, so values such as "false" remain strings
        # after a restart instead of being decoded as JSON booleans.
        val_str = _json.dumps(value)
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
        if key == "video_flow_v3_enabled" and default is None:
            default = True
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


    def get_history_record(self, record_id: int) -> dict[str, Any] | None:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM history WHERE id = ?", (record_id,)).fetchone()
            return dict(row) if row else None

    def update_dictation(self, record_id: int, **fields: Any) -> bool:
        allowed = {"raw_text", "polished_text", "status", "error_message", "audio_path", "insertion_status", "retry_count", "word_count", "wpm_speed"}
        values = {key: value for key, value in fields.items() if key in allowed}
        if not values:
            return False
        if "polished_text" in values:
            words = len(str(values["polished_text"] or "").split())
            values["word_count"] = words
            with self._get_conn() as conn:
                duration = float((conn.execute("SELECT duration_sec FROM history WHERE id = ?", (record_id,)).fetchone() or [0])[0] or 0)
            values["wpm_speed"] = int(words / max(0.05, duration / 60.0)) if words else 0
        values["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self._get_conn() as conn:
            cursor = conn.execute(f"UPDATE history SET {assignments} WHERE id = ?", (*values.values(), record_id))
            conn.commit()
            return cursor.rowcount == 1

    def delete_history_record(self, record_id: int) -> dict[str, Any] | None:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM history WHERE id = ?", (record_id,)).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM history WHERE id = ?", (record_id,))
            conn.commit()
        self._remove_stale_auto_captured_words()
        return dict(row)

    # --- Explicit Dictionary Corrections (CURRENT-only feature) ---

    @staticmethod
    def _validated_text(value: Any, field: str, minimum: int, maximum: int) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field} must be text")
        clean = value.strip()
        if not minimum <= len(clean) <= maximum:
            raise ValueError(f"{field} must be {minimum}–{maximum} characters")
        return clean

    @staticmethod
    def _legacy_snippet_parts(value: str) -> tuple[str, str] | None:
        """Return a valid legacy shortcut pair, without guessing at normal words."""
        # Historical entries used `->`; when both appear, it owns the split and
        # the later arrow is ordinary expansion text.
        delimiter = "->" if "->" in value else "=>" if "=>" in value else None
        if not delimiter or value.count(delimiter) != 1:
            return None
        trigger, expansion = (part.strip() for part in value.split(delimiter, 1))
        try:
            return (
                StorageEngine._validated_text(trigger, "trigger", 1, 60),
                StorageEngine._validated_text(expansion, "expansion", 1, 4000),
            )
        except ValueError:
            return None

    @staticmethod
    def _add_migration_conflict(conn, entity_type: str, normalized: str, current_id: int, legacy_key: str, legacy_value: str) -> None:
        conn.execute(
            "INSERT INTO migration_conflicts (entity_type, normalized_key, current_record_id, legacy_key, legacy_value, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (entity_type, normalized, current_id, legacy_key, legacy_value, datetime.datetime.now().isoformat()),
        )

    def _migrate_snippet_case_variants(self) -> None:
        changed = False
        with self._lexicon_lock:
            with self._get_conn() as conn:
                keepers: dict[str, sqlite3.Row] = {}
                for row in conn.execute("SELECT id, trigger, expansion FROM snippets ORDER BY id ASC"):
                    normalized = row["trigger"].strip().casefold()
                    keeper = keepers.get(normalized)
                    if keeper is None:
                        keepers[normalized] = row
                        continue
                    if row["expansion"] != keeper["expansion"]:
                        self._add_migration_conflict(conn, "snippet", normalized, keeper["id"], row["trigger"], row["expansion"])
                    conn.execute("DELETE FROM snippets WHERE id = ?", (row["id"],)); changed = True
                for normalized, row in keepers.items():
                    existing = conn.execute("SELECT snippet_id FROM snippet_keys WHERE normalized = ?", (normalized,)).fetchone()
                    if existing is None:
                        conn.execute("INSERT INTO snippet_keys (normalized, snippet_id) VALUES (?, ?)", (normalized, row["id"]))
                    elif existing["snippet_id"] != row["id"]:
                        # Existing persisted key is authoritative; the record's
                        # payload stays recoverable through a visible conflict.
                        self._add_migration_conflict(conn, "snippet", normalized, existing["snippet_id"], row["trigger"], row["expansion"])
                        conn.execute("DELETE FROM snippets WHERE id = ?", (row["id"],)); changed = True
            if changed:
                self._touch_lexicon()

    def _migrate_correction_case_variants(self) -> None:
        changed = False
        with self._lexicon_lock:
            with self._get_conn() as conn:
                keepers: dict[str, sqlite3.Row] = {}
                for row in conn.execute("SELECT id, wrong_text, correct_text FROM dictionary_corrections ORDER BY id ASC"):
                    normalized = row["wrong_text"].strip().casefold()
                    keeper = keepers.get(normalized)
                    if keeper is None:
                        keepers[normalized] = row
                        continue
                    if row["correct_text"] != keeper["correct_text"]:
                        self._add_migration_conflict(conn, "correction", normalized, keeper["id"], row["wrong_text"], row["correct_text"])
                    conn.execute("DELETE FROM dictionary_corrections WHERE id = ?", (row["id"],)); changed = True
                for normalized, row in keepers.items():
                    existing = conn.execute("SELECT correction_id FROM correction_keys WHERE normalized = ?", (normalized,)).fetchone()
                    if existing is None:
                        conn.execute("INSERT INTO correction_keys (normalized, correction_id) VALUES (?, ?)", (normalized, row["id"]))
                    elif existing["correction_id"] != row["id"]:
                        self._add_migration_conflict(conn, "correction", normalized, existing["correction_id"], row["wrong_text"], row["correct_text"])
                        conn.execute("DELETE FROM dictionary_corrections WHERE id = ?", (row["id"],)); changed = True
            if changed:
                self._touch_lexicon()

    def _migrate_legacy_dictionary_snippets(self) -> None:
        """Migrate old `shortcut -> expansion` dictionary rows once and safely."""
        changed = False
        with self._lexicon_lock:
            with self._get_conn() as conn:
                rows = conn.execute("SELECT id, word, created_at FROM dictionary").fetchall()
                now = datetime.datetime.now().isoformat()
                for row in rows:
                    pair = self._legacy_snippet_parts(row["word"])
                    if not pair:
                        continue
                    trigger, expansion = pair
                    normalized = trigger.casefold()
                    current = conn.execute(
                        "SELECT s.id, s.expansion FROM snippet_keys k JOIN snippets s ON s.id = k.snippet_id WHERE k.normalized = ?",
                        (normalized,),
                    ).fetchone()
                    if current is not None:
                        if current["expansion"] != expansion:
                            self._add_migration_conflict(conn, "snippet", normalized, current["id"], trigger, expansion)
                        conn.execute("DELETE FROM dictionary WHERE id = ?", (row["id"],))
                        changed = True
                        continue
                    cursor = conn.execute(
                        "INSERT INTO snippets (trigger, expansion, created_at, updated_at) VALUES (?, ?, ?, ?)",
                        (trigger, expansion, row["created_at"] or now, now),
                    )
                    conn.execute("INSERT INTO snippet_keys (normalized, snippet_id) VALUES (?, ?)", (normalized, cursor.lastrowid))
                    conn.execute("DELETE FROM dictionary WHERE id = ?", (row["id"],))
                    changed = True
            if changed:
                self._touch_lexicon()

    def _migrate_dictionary_case_variants(self) -> None:
        """Normalize legacy case variants, retaining the earliest spelling."""
        changed = False
        with self._lexicon_lock:
            with self._get_conn() as conn:
                rows = conn.execute("SELECT id, word FROM dictionary ORDER BY id ASC").fetchall()
                keepers: dict[str, int] = {}
                for row in rows:
                    normalized = row["word"].strip().casefold()
                    if not normalized or "->" in row["word"] or "=>" in row["word"]:
                        continue
                    existing = keepers.get(normalized)
                    if existing is None:
                        keepers[normalized] = row["id"]
                    else:
                        conn.execute("DELETE FROM dictionary WHERE id = ?", (row["id"],))
                        changed = True
                for normalized, dictionary_id in keepers.items():
                    key = conn.execute("SELECT dictionary_id FROM dictionary_keys WHERE normalized = ?", (normalized,)).fetchone()
                    if key is None:
                        conn.execute("INSERT INTO dictionary_keys (normalized, dictionary_id) VALUES (?, ?)", (normalized, dictionary_id))
                    elif key["dictionary_id"] != dictionary_id:
                        # The existing key wins, so preserve its row and remove
                        # the duplicate found during deterministic migration.
                        conn.execute("DELETE FROM dictionary WHERE id = ?", (dictionary_id,))
                        changed = True
            if changed:
                self._touch_lexicon()

    def get_dictionary_snapshot(self) -> tuple[int, list[str], list[dict[str, Any]]]:
        """Read a dictionary/correction snapshot matching one revision."""
        with self._lexicon_lock:
            with self._get_conn() as conn:
                words = [row["word"] for row in conn.execute("SELECT word FROM dictionary ORDER BY word ASC")
                         if "->" not in row["word"] and "=>" not in row["word"]]
                corrections = [dict(row) for row in conn.execute(
                    "SELECT id, wrong_text, correct_text, created_at, updated_at FROM dictionary_corrections "
                    "ORDER BY wrong_text COLLATE NOCASE"
                )]
                return self._lexicon_revision, words, corrections

    def get_snippet_snapshot(self) -> tuple[int, list[dict[str, Any]]]:
        with self._lexicon_lock:
            with self._get_conn() as conn:
                snippets = [dict(row) for row in conn.execute(
                    "SELECT id, trigger, expansion, created_at, updated_at FROM snippets ORDER BY trigger COLLATE NOCASE"
                )]
                return self._lexicon_revision, snippets

    def get_dictionary_corrections(self) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, wrong_text, correct_text, created_at, updated_at "
                "FROM dictionary_corrections ORDER BY wrong_text COLLATE NOCASE"
            ).fetchall()
            return [dict(row) for row in rows]

    def add_dictionary_correction(self, wrong_text: str, correct_text: str) -> dict[str, Any]:
        wrong = self._validated_text(wrong_text, "heard phrase", 1, 240)
        correct = self._validated_text(correct_text, "desired spelling", 1, 240)
        now = datetime.datetime.now().isoformat()
        with self._lexicon_lock:
            with self._get_conn_ctx() as conn:
                normalized = wrong.casefold()
                if conn.execute("SELECT 1 FROM correction_keys WHERE normalized = ?", (normalized,)).fetchone():
                    raise sqlite3.IntegrityError("duplicate correction")
                cursor = conn.execute(
                    "INSERT INTO dictionary_corrections (wrong_text, correct_text, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?)", (wrong, correct, now, now)
                )
                conn.execute("INSERT INTO correction_keys (normalized, correction_id) VALUES (?, ?)", (normalized, cursor.lastrowid))
                row = conn.execute("SELECT * FROM dictionary_corrections WHERE id = ?", (cursor.lastrowid,)).fetchone()
            self._touch_lexicon()
            return dict(row)

    def update_dictionary_correction(self, correction_id: int, wrong_text: str, correct_text: str) -> dict[str, Any] | None:
        wrong = self._validated_text(wrong_text, "heard phrase", 1, 240)
        correct = self._validated_text(correct_text, "desired spelling", 1, 240)
        with self._lexicon_lock:
            with self._get_conn_ctx() as conn:
                existing = conn.execute("SELECT correction_id FROM correction_keys WHERE normalized = ?", (wrong.casefold(),)).fetchone()
                if existing is not None and existing["correction_id"] != correction_id:
                    raise sqlite3.IntegrityError("duplicate correction")
                cursor = conn.execute(
                    "UPDATE dictionary_corrections SET wrong_text = ?, correct_text = ?, updated_at = ? WHERE id = ?",
                    (wrong, correct, datetime.datetime.now().isoformat(), correction_id),
                )
                if not cursor.rowcount:
                    return None
                conn.execute("DELETE FROM correction_keys WHERE correction_id = ?", (correction_id,))
                conn.execute("INSERT INTO correction_keys (normalized, correction_id) VALUES (?, ?)", (wrong.casefold(), correction_id))
                row = conn.execute("SELECT * FROM dictionary_corrections WHERE id = ?", (correction_id,)).fetchone()
            self._touch_lexicon()
            return dict(row)

    def remove_dictionary_correction(self, correction_id: int) -> bool:
        with self._lexicon_lock:
            with self._get_conn_ctx() as conn:
                deleted = bool(conn.execute("DELETE FROM dictionary_corrections WHERE id = ?", (correction_id,)).rowcount)
                conn.execute("DELETE FROM correction_keys WHERE correction_id = ?", (correction_id,))
            if deleted:
                self._touch_lexicon()
            return deleted

    # --- Snippets (CURRENT-only feature) ---

    def get_snippets(self) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, trigger, expansion, created_at, updated_at FROM snippets "
                "ORDER BY trigger COLLATE NOCASE"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_migration_conflicts(self) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            conflicts = []
            for row in conn.execute("SELECT * FROM migration_conflicts ORDER BY id ASC"):
                item = dict(row)
                if item["entity_type"] == "snippet":
                    current = conn.execute("SELECT trigger, expansion FROM snippets WHERE id = ?", (item["current_record_id"],)).fetchone()
                    current_key, current_value = (current["trigger"], current["expansion"]) if current else (None, None)
                else:
                    current = conn.execute("SELECT wrong_text, correct_text FROM dictionary_corrections WHERE id = ?", (item["current_record_id"],)).fetchone()
                    current_key, current_value = (current["wrong_text"], current["correct_text"]) if current else (None, None)
                item["current_key"] = current_key
                item["current_value"] = current_value
                conflicts.append(item)
            return conflicts

    def resolve_migration_conflict(self, conflict_id: int, action: str) -> bool:
        if action not in {"keep_current", "use_legacy"}:
            raise ValueError("action must be keep_current or use_legacy")
        with self._lexicon_lock:
            with self._get_conn_ctx() as conn:
                conflict = conn.execute("SELECT * FROM migration_conflicts WHERE id = ?", (conflict_id,)).fetchone()
                if conflict is None:
                    return False
                if action == "use_legacy":
                    now = datetime.datetime.now().isoformat()
                    if conflict["entity_type"] == "snippet":
                        current = conn.execute("SELECT trigger FROM snippets WHERE id = ?", (conflict["current_record_id"],)).fetchone()
                        if current is not None and current["trigger"].casefold() == conflict["normalized_key"]:
                            conn.execute("UPDATE snippets SET trigger = ?, expansion = ?, updated_at = ? WHERE id = ?", (conflict["legacy_key"], conflict["legacy_value"], now, conflict["current_record_id"]))
                        elif current is None:
                            mapped = conn.execute("SELECT snippet_id FROM snippet_keys WHERE normalized = ?", (conflict["normalized_key"],)).fetchone()
                            if mapped is not None:
                                active = conn.execute("SELECT 1 FROM snippets WHERE id = ?", (mapped["snippet_id"],)).fetchone()
                                if active:
                                    raise RuntimeError("Conflict changed; legacy data is retained")
                                conn.execute("DELETE FROM snippet_keys WHERE normalized = ?", (conflict["normalized_key"],))
                            cursor = conn.execute("INSERT INTO snippets (trigger, expansion, created_at, updated_at) VALUES (?, ?, ?, ?)", (conflict["legacy_key"], conflict["legacy_value"], now, now))
                            conn.execute("INSERT INTO snippet_keys (normalized, snippet_id) VALUES (?, ?)", (conflict["normalized_key"], cursor.lastrowid))
                        else:
                            raise RuntimeError("Conflict changed; legacy data is retained")
                    else:
                        current = conn.execute("SELECT wrong_text FROM dictionary_corrections WHERE id = ?", (conflict["current_record_id"],)).fetchone()
                        if current is not None and current["wrong_text"].casefold() == conflict["normalized_key"]:
                            conn.execute("UPDATE dictionary_corrections SET wrong_text = ?, correct_text = ?, updated_at = ? WHERE id = ?", (conflict["legacy_key"], conflict["legacy_value"], now, conflict["current_record_id"]))
                        elif current is None:
                            mapped = conn.execute("SELECT correction_id FROM correction_keys WHERE normalized = ?", (conflict["normalized_key"],)).fetchone()
                            if mapped is not None:
                                active = conn.execute("SELECT 1 FROM dictionary_corrections WHERE id = ?", (mapped["correction_id"],)).fetchone()
                                if active:
                                    raise RuntimeError("Conflict changed; legacy data is retained")
                                conn.execute("DELETE FROM correction_keys WHERE normalized = ?", (conflict["normalized_key"],))
                            cursor = conn.execute("INSERT INTO dictionary_corrections (wrong_text, correct_text, created_at, updated_at) VALUES (?, ?, ?, ?)", (conflict["legacy_key"], conflict["legacy_value"], now, now))
                            conn.execute("INSERT INTO correction_keys (normalized, correction_id) VALUES (?, ?)", (conflict["normalized_key"], cursor.lastrowid))
                        else:
                            raise RuntimeError("Conflict changed; legacy data is retained")
                conn.execute("DELETE FROM migration_conflicts WHERE id = ?", (conflict_id,))
            self._touch_lexicon()
            return True

    def add_snippet(self, trigger: str, expansion: str) -> dict[str, Any]:
        key = self._validated_text(trigger, "trigger", 1, 60)
        value = self._validated_text(expansion, "expansion", 1, 4000)
        now = datetime.datetime.now().isoformat()
        with self._lexicon_lock:
            with self._get_conn_ctx() as conn:
                normalized = key.casefold()
                if conn.execute("SELECT 1 FROM snippet_keys WHERE normalized = ?", (normalized,)).fetchone():
                    raise sqlite3.IntegrityError("duplicate snippet")
                cursor = conn.execute(
                    "INSERT INTO snippets (trigger, expansion, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (key, value, now, now),
                )
                conn.execute("INSERT INTO snippet_keys (normalized, snippet_id) VALUES (?, ?)", (normalized, cursor.lastrowid))
                row = conn.execute("SELECT * FROM snippets WHERE id = ?", (cursor.lastrowid,)).fetchone()
            self._touch_lexicon()
            return dict(row)

    def update_snippet(self, snippet_id: int, trigger: str, expansion: str) -> dict[str, Any] | None:
        key = self._validated_text(trigger, "trigger", 1, 60)
        value = self._validated_text(expansion, "expansion", 1, 4000)
        with self._lexicon_lock:
            with self._get_conn_ctx() as conn:
                existing = conn.execute("SELECT snippet_id FROM snippet_keys WHERE normalized = ?", (key.casefold(),)).fetchone()
                if existing is not None and existing["snippet_id"] != snippet_id:
                    raise sqlite3.IntegrityError("duplicate snippet")
                cursor = conn.execute(
                    "UPDATE snippets SET trigger = ?, expansion = ?, updated_at = ? WHERE id = ?",
                    (key, value, datetime.datetime.now().isoformat(), snippet_id),
                )
                if not cursor.rowcount:
                    return None
                conn.execute("DELETE FROM snippet_keys WHERE snippet_id = ?", (snippet_id,))
                conn.execute("INSERT INTO snippet_keys (normalized, snippet_id) VALUES (?, ?)", (key.casefold(), snippet_id))
                row = conn.execute("SELECT * FROM snippets WHERE id = ?", (snippet_id,)).fetchone()
            self._touch_lexicon()
            return dict(row)

    def remove_snippet(self, snippet_id: int) -> bool:
        with self._lexicon_lock:
            with self._get_conn_ctx() as conn:
                deleted = bool(conn.execute("DELETE FROM snippets WHERE id = ?", (snippet_id,)).rowcount)
                conn.execute("DELETE FROM snippet_keys WHERE snippet_id = ?", (snippet_id,))
            if deleted:
                self._touch_lexicon()
            return deleted


# Singleton Storage Instance. Constructed lazily so importing this module
# never opens or writes the user's live database (tests and tooling that
# only need StorageEngine stay fully isolated from production data).
_storage_singleton: StorageEngine | None = None
_storage_singleton_lock = threading.Lock()


def __getattr__(name: str) -> Any:
    if name == "storage":
        global _storage_singleton
        with _storage_singleton_lock:
            if _storage_singleton is None:
                _storage_singleton = StorageEngine()
            return _storage_singleton
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

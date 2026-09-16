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


# ---------------------------------------------------------------------------
# History de-duplication
# ---------------------------------------------------------------------------
# ``history`` currently holds every dictation TWICE. The 2026-09-12 account
# consolidation merged three databases that were near-copies of each other
# (the pre-merge backups share 2,859 of 2,883 rows), and the merge inserted
# them without de-duplicating. Proof: 2,883 row pairs carry an id gap of
# exactly 2,883 AND a byte-identical timestamp, text, word count and duration
# - impossible for two genuine recordings.
#
# The effect was not cosmetic: total_words, dictation_count and time_saved were
# all reported at double their true value. ``avg_wpm`` looked fine only because
# it is a ratio of two doubled numbers, so the error cancelled.
#
# Rather than deleting the user's rows, Insights materialises one row per real
# dictation into a TEMP table and reads from that. Non-destructive, and the
# original data stays intact.
_DEDUP_HISTORY_SELECT = """
SELECT
    timestamp,
    raw_text,
    polished_text,
    MAX(id)               AS id,
    MAX(word_count)       AS word_count,
    MAX(duration_sec)     AS duration_sec,
    MAX(wpm_speed)        AS wpm_speed,
    MAX(status)           AS status,
    MAX(style_mode)       AS style_mode,
    MAX(is_pinned)        AS is_pinned,
    MAX(is_favorite)      AS is_favorite,
    MAX(error_message)    AS error_message,
    MAX(audio_path)       AS audio_path,
    MAX(insertion_status) AS insertion_status,
    MAX(updated_at)       AS updated_at,
    MAX(retry_count)      AS retry_count,
    -- Prefer a real application name if the copies ever disagree, so a
    -- "General App" copy can never win over an identified one.
    COALESCE(
        MAX(CASE
              WHEN app_name IS NOT NULL AND app_name NOT IN ('', 'General App')
              THEN app_name
            END),
        MAX(app_name)
    ) AS app_name
FROM main.history
GROUP BY timestamp, raw_text, polished_text
"""

# Matches one physical dictation across all of its duplicate rows. `IS` rather
# than `=` so a NULL polished_text still compares correctly. Reads collapse
# copies via ``_DEDUP_HISTORY_SELECT``, so writes must fan out the same way --
# otherwise deleting or unpinning the clicked row appears to do nothing, because
# the surviving twin keeps the row on screen.
_DEDUP_KEY_WHERE = "timestamp IS ? AND raw_text IS ? AND polished_text IS ?"

# A dictation whose implied rate sits outside this band has a corrupted
# duration rather than a genuinely unusual speaker: the data contains rows of
# 223 words stored against a 1.25 s recording (10,670 wpm) and rows of 1 word
# against 17 s (3.5 wpm). Those two tails nearly cancelled, which is why the
# headline number looked plausible while being the product of two large errors.
_WPM_MIN_PLAUSIBLE = 50.0
_WPM_MAX_PLAUSIBLE = 280.0

# Application attribution before this detector version did not persist the
# executable name or HWND, so old rows can include browser tab titles or other
# window-title fragments that only *look* like apps. Insights therefore uses a
# conservative verified-app view: show only rows captured after the executable-
# first detector was deployed, and hide known internal/test/noise labels. The
# original history is left untouched; uncertain rows are counted as hidden so the
# UI tells the truth instead of inventing a clean attribution.
_APP_ATTRIBUTION_RELIABLE_AFTER = "2026-09-13 15:05:00"
_APP_ATTRIBUTION_MIN_WORDS = 25
_APP_ATTRIBUTION_NOISE_APPS = (
    "",
    "AI Productivity Flow",
    "AI Speech Desktop App",
    "Bench",
    "Captured App",
    "General App",
    "Hub",
    "Initiating A New Conversa...",
    "Pythonw",
    "Shellexperiencehost",
    "Synthetic test",
    "Workbuddy",
    "Workbuddyai",
    "YouTube",
    "Grok",
)


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


def resolve_active_db_path() -> str:
    """Return the database path for the currently active account, or fallback to default DB_PATH."""
    try:
        from voice_flow.account_manager import get_account_manager
        am = get_account_manager()
        active_id = am.get_active_account_id()
        if active_id:
            p = am.get_account_db_path(active_id)
            if p:
                return str(p)
    except Exception:
        pass
    return DB_PATH


class StorageEngine:
    """SQLite Database manager for persistent dictation history & metrics."""

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            db_path = resolve_active_db_path()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = str(db_path)
        self._lexicon_revision = 0
        self._lexicon_lock = threading.RLock()
        self._init_db()

    def switch_account(self, new_db_path: str) -> None:
        """Dynamically repoint this StorageEngine instance to another account's database."""
        with self._lexicon_lock:
            os.makedirs(os.path.dirname(new_db_path), exist_ok=True)
            self.db_path = str(new_db_path)
            self._init_db()
            self._touch_lexicon()
            log.info("StorageEngine repointed to %s", self.db_path)

    def repoint_if_needed(self) -> bool:
        """Repoint this engine to the active storage DB if it changed since the
        last call (account login/logout/switch or a fresh guest session).

        Both the dictation engine and the GUI server call this before reads/writes,
        so they always agree on the same canonical database.

        Returns True when the engine switched databases (schema re-initialized),
        False when it is already on the right DB.
        """
        try:
            target = resolve_active_db_path()
        except Exception:
            log.debug("Could not resolve active DB path for repoint", exc_info=True)
            target = DB_PATH
        if not target:
            target = DB_PATH
        if os.path.normcase(os.path.abspath(target)) == os.path.normcase(os.path.abspath(self.db_path)):
            return False
        try:
            self.switch_account(target)
        except Exception:
            log.exception("Could not re-point storage to %s", target)
            return False
        log.info("StorageEngine re-pointed to active database %s", self.db_path)
        return True

    def _touch_lexicon(self, conn: sqlite3.Connection | None = None) -> None:
        """Notify dictionary engines about persisted edits, across processes."""
        self._lexicon_revision += 1
        if conn is not None:
            self._bump_dictionary_revision(conn)
            return
        # DictionaryEngine polls ``dictionary_revision`` between dictations.
        # Corrections and snippets used to update only this process-local
        # counter, so an already-created engine never saw those GUI edits.
        try:
            with self._get_conn_ctx() as conn:
                self._bump_dictionary_revision(conn)
        except Exception:
            log.debug("Could not persist lexicon revision", exc_info=True)

    @contextmanager
    def _get_conn_ctx(self):
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout = 15000")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        except Exception:
            pass
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout = 15000")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        except Exception:
            pass
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
                    except sqlite3.OperationalError as _migr_exc:
                        if "duplicate column name" not in str(_migr_exc).lower():
                            raise
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
                ("email", "TEXT"),
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
                    except sqlite3.OperationalError as _migr_exc:
                        if "duplicate column name" not in str(_migr_exc).lower():
                            raise
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
                    except sqlite3.OperationalError as _migr_exc:
                        if "duplicate column name" not in str(_migr_exc).lower():
                            raise

            # Audio Provider Settings (Load Balancing Mode)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audio_provider_settings (
                    provider TEXT PRIMARY KEY,
                    load_balance_mode TEXT DEFAULT 'priority',
                    is_enabled INTEGER DEFAULT 1
                )
            """)

            # Ensure custom column exists in provider_models
            cursor = conn.execute("PRAGMA table_info(provider_models)")
            pm_cols = {row["name"] for row in cursor.fetchall()}
            if "custom" not in pm_cols:
                try:
                    conn.execute("ALTER TABLE provider_models ADD COLUMN custom INTEGER DEFAULT 0")
                except sqlite3.OperationalError as _pm_exc:
                    if "duplicate column name" not in str(_pm_exc).lower():
                        raise

            # Ensure custom column exists in tts_models
            cursor = conn.execute("PRAGMA table_info(tts_models)")
            tts_cols = {row["name"] for row in cursor.fetchall()}
            if "custom" not in tts_cols:
                try:
                    conn.execute("ALTER TABLE tts_models ADD COLUMN custom INTEGER DEFAULT 0")
                except sqlite3.OperationalError as _tts_exc:
                    if "duplicate column name" not in str(_tts_exc).lower():
                        raise

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
                CREATE TABLE IF NOT EXISTS lexicon_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    term TEXT NOT NULL,
                    variant TEXT NOT NULL DEFAULT '',
                    evidence INTEGER NOT NULL DEFAULT 1,
                    state TEXT NOT NULL DEFAULT 'candidate',
                    source TEXT DEFAULT 'correction',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(term COLLATE NOCASE, variant COLLATE NOCASE)
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audio_summary_cache (
                    cache_key TEXT PRIMARY KEY NOT NULL,
                    text_hash TEXT NOT NULL,
                    depth TEXT NOT NULL,
                    model_ref TEXT NOT NULL,
                    summary_text TEXT NOT NULL,
                    cached_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audio_summary_cache_hash ON audio_summary_cache (text_hash)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audio_summary_history (
                    id TEXT PRIMARY KEY NOT NULL,
                    title TEXT,
                    text_snippet TEXT NOT NULL,
                    full_text TEXT,
                    depth TEXT NOT NULL,
                    audio_path TEXT NOT NULL,
                    duration_sec REAL DEFAULT 0,
                    status TEXT DEFAULT 'ready',
                    error TEXT,
                    progress INTEGER DEFAULT 100,
                    created_at TEXT NOT NULL,
                    downloaded INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audio_summary_history_created ON audio_summary_history (created_at DESC)")

            conn.commit()

        self._migrate_snippet_case_variants()
        self._migrate_correction_case_variants()
        self._migrate_legacy_dictionary_snippets()
        self._migrate_dictionary_case_variants()
        self._migrate_audio_summary_history()
        self._seed_default_models()
        self._seed_tts_models()

    _SEED_VERSION = "5"  # Bump to re-seed after adding new default models

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

    def _ensure_provider_models_unique(self) -> None:
        """Hard guarantee: one row per (provider, model_id)."""
        try:
            with self._get_conn() as conn:
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_provider_models_unique ON provider_models(provider, model_id)")
        except Exception:
            pass

    def _seed_default_models(self) -> None:
        self._ensure_provider_models_unique()
        """Seed standard models for AI providers if not already present."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT value FROM settings WHERE key = 'seed_version'")
            row = cursor.fetchone()
            if row and row["value"] == self._SEED_VERSION:
                return  # Already seeded this version
        seeds = {
            "gemini": [
                ("gemini-3.5-transcribe", "Gemini 3.5 Transcribe"),
                ("gemini-3.5-transcribe-live", "Gemini 3.5 Transcribe Live"),
            ],
            "groq": [
                ("whisper-large-v3-turbo", "Whisper Large V3 Turbo"),
                ("whisper-large-v3", "Whisper Large V3"),
            ],
            "elevenlabs": [
                ("scribe_v2", "Scribe v2"),
                ("scribe_v2_realtime", "Scribe v2 Realtime"),
            ],
            "deepgram": [
                ("flux-general-en", "Flux General English"),
                ("flux-general-multi", "Flux General Multilingual"),
                ("nova-3", "Nova-3"),
                ("nova-3-general", "Nova-3 General"),
                ("nova-2", "Nova-2"),
                ("nova-2-general", "Nova-2 General"),
            ],
            "openai": [
                ("gpt-transcribe", "GPT Transcribe"),
                ("gpt-live-transcribe", "GPT Live Transcribe"),
                ("gpt-realtime-whisper", "GPT Realtime Whisper"),
                ("gpt-4o-transcribe", "GPT-4o Transcribe"),
                ("gpt-4o-mini-transcribe", "GPT-4o Mini Transcribe"),
                ("gpt-4o-transcribe-diarize", "GPT-4o Transcribe Diarize"),
                ("whisper-1", "Whisper-1"),
            ],
            "assemblyai": [
                ("universal-3-pro", "Universal-3 Pro"),
                ("universal-2", "Universal-2"),
                ("universal-3-pro-streaming", "Universal-3 Pro Streaming"),
                ("universal-streaming-multilingual", "Universal Streaming Multilingual"),
                ("universal-streaming-english", "Universal Streaming English"),
                ("whisper-streaming", "Whisper Streaming"),
            ],
            "speechmatics": [
                ("enhanced", "Enhanced"),
                ("standard", "Standard"),
                ("melia-1", "Melia 1"),
            ],
            "nvidia": [
                ("nvidia/parakeet-ctc-1.1b", "Parakeet CTC 1.1B (English)"),
                ("nvidia/parakeet-tdt-0.6b-v3", "Parakeet TDT 0.6B v3 (Multilingual)"),
                ("nvidia/canary-1b-v2", "Canary 1B v2 (Multi-task ASR)"),
            ],
            "nvidia_nim": [
                ("nvidia/parakeet-ctc-1.1b", "Parakeet CTC 1.1B (English)"),
                ("nvidia/parakeet-tdt-0.6b-v3", "Parakeet TDT 0.6B v3 (Multilingual)"),
                ("nvidia/canary-1b-v2", "Canary 1B v2 (Multi-task ASR)"),
            ],
        }
        with self._get_conn() as conn:
            # Exact-catalog reset: remove every old model for these providers
            conn.executemany(
                "DELETE FROM provider_models WHERE provider = ?",
                [(prov,) for prov in seeds.keys()]
            )
            for provider, model_list in seeds.items():
                for mid, mname in model_list:
                    conn.execute(
                        "INSERT OR IGNORE INTO provider_models (provider, model_id, display_name, is_active) VALUES (?, ?, ?, 1)",
                        (provider, mid, mname)
                    )
            # Catalog cleanup: retired providers must not linger in existing DBs
            retired = ("huggingface", "cloudflare", "together", "replicate")
            for provider in retired:
                conn.execute("DELETE FROM provider_models WHERE provider = ?", (provider,))
                conn.execute("DELETE FROM provider_connections WHERE provider = ?", (provider,))
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
                clean.isupper() and len(clean) >= 4  # ALL CAPS acronym e.g. API, SQL (4+ to skip 3-letter words)
            ) or (
                sum(1 for c in clean if c.isupper()) >= 2 and any(c.islower() for c in clean)  # CamelCase e.g. VoiceFlow
            ) or (
                clean[0].isupper() and clean[1:].islower() and len(clean) >= 7  # Long proper noun e.g. HyperKube
            )
            if not is_jargon:
                continue

            # Learn only from exact token occurrences in raw dictation.  SQL
            # substring matching made API match CAPITAL and let polished/AI
            # output authorize future replacements.
            try:
                with self._get_conn() as conn:
                    # GROUP BY collapses the duplicate rows left behind by the
                    # 2026-09-12 account consolidation. Without it every count
                    # below is doubled, which effectively halves the >= 5
                    # threshold and auto-captures jargon that was only said 3
                    # times. Must match _DEDUP_HISTORY_SELECT's key.
                    rows = conn.execute(
                        "SELECT raw_text FROM history "
                        "GROUP BY timestamp, raw_text, polished_text"
                    ).fetchall()
                token_pattern = re.compile(
                    rf"(?<![\w-]){re.escape(clean)}(?![\w-])",
                    flags=re.IGNORECASE | re.UNICODE,
                )
                occurrences = sum(
                    len(token_pattern.findall(str(row["raw_text"] or "")))
                    for row in rows
                )
                if occurrences >= 5:
                    self.add_dictionary_word(clean, category="Auto-Captured")
            except Exception:
                log.exception("Could not evaluate auto-captured dictionary term %r", clean)

    @staticmethod
    def _dedup_key_for(conn: Any, record_id: int) -> tuple[Any, Any, Any] | None:
        """Resolve a history id to its dedup key, or None if it is gone."""
        row = conn.execute(
            "SELECT timestamp, raw_text, polished_text FROM history WHERE id = ?",
            (record_id,),
        ).fetchone()
        if not row:
            return None
        return (row["timestamp"], row["raw_text"], row["polished_text"])

    def get_recent_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            # Collapsed like every other read, so the transcript feed cannot
            # show the same dictation twice.
            cursor = conn.execute(
                f"SELECT * FROM ({_DEDUP_HISTORY_SELECT}) "
                "ORDER BY is_pinned DESC, id DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def toggle_history_pin(self, record_id: int) -> dict[str, Any]:
        """Toggle is_pinned for a history record across all of its copies."""
        with self._get_conn() as conn:
            key = self._dedup_key_for(conn, record_id)
            if not key:
                return {"success": False, "error": "Record not found"}
            row = conn.execute(
                f"SELECT MAX(is_pinned) AS pinned FROM history WHERE {_DEDUP_KEY_WHERE}",
                key,
            ).fetchone()
            current_pinned = int((row["pinned"] if row else 0) or 0)
            new_pinned = 0 if current_pinned else 1
            conn.execute(
                f"UPDATE history SET is_pinned = ? WHERE {_DEDUP_KEY_WHERE}",
                (new_pinned, *key),
            )
            conn.commit()
            return {"success": True, "id": record_id, "is_pinned": bool(new_pinned)}

    def get_insights(self, range_filter: str = "all") -> dict[str, Any]:
        """Compute rich desktop dictation telemetry and insights metrics.

        The API server re-points the singleton engine to the active database
        (see ``_sync_active_storage``) before calling this, so this method
        simply computes from whatever database the engine currently targets.
        """
        with self._get_conn() as conn:
            # Collapse the duplicated rows described at module level into one
            # row per real dictation. ``history_dedup`` is a TEMP table, so it
            # is rebuilt per request and the stored data is never touched.
            conn.execute("DROP TABLE IF EXISTS temp.history_dedup")
            conn.execute(f"CREATE TEMP TABLE history_dedup AS {_DEDUP_HISTORY_SELECT}")

            date_cond = ""
            if range_filter == "7d":
                date_cond = " AND timestamp >= datetime('now', 'localtime', '-7 days')"
            elif range_filter == "30d":
                date_cond = " AND timestamp >= datetime('now', 'localtime', '-30 days')"
            # A history row starts in ``processing`` and may finish as a
            # transcription/paste failure. Dashboard metrics describe usable
            # completed dictations only; retries update the same row, so they
            # naturally remain one successful dictation.
            success_cond = " AND status = 'success'"
            attempt_cond = " AND status = 'success'"

            # Filter out historical zero-duration records to fix average WPM calculation
            total_words = conn.execute(f"SELECT COALESCE(SUM(word_count), 0) FROM history_dedup WHERE duration_sec > 0.1 {attempt_cond} {date_cond}").fetchone()[0]
            total_duration_sec = conn.execute(f"SELECT COALESCE(SUM(duration_sec), 0) FROM history_dedup WHERE duration_sec > 0.1 {attempt_cond} {date_cond}").fetchone()[0]
            dictation_count = conn.execute(f"SELECT COUNT(*) FROM history_dedup WHERE duration_sec > 0.1 {attempt_cond} {date_cond}").fetchone()[0]

            # Speaking rate, measured only across dictations whose duration is
            # trustworthy. See _WPM_MIN_PLAUSIBLE: the corrupt tails nearly
            # cancelled each other, so the old single ratio looked plausible
            # while really being the sum of two large errors.
            measured = conn.execute(
                f"""
                SELECT COALESCE(SUM(word_count), 0) AS w,
                       COALESCE(SUM(duration_sec), 0) AS d,
                       COUNT(*) AS n
                FROM history_dedup
                WHERE duration_sec > 0.1 AND word_count > 0 {success_cond} {date_cond}
                  AND (word_count * 60.0 / duration_sec) BETWEEN ? AND ?
                """,
                (_WPM_MIN_PLAUSIBLE, _WPM_MAX_PLAUSIBLE),
            ).fetchone()
            measured_words = measured["w"] or 0
            measured_seconds = measured["d"] or 0
            measured_count = measured["n"] or 0
            avg_wpm_val = (measured_words / measured_seconds * 60.0) if measured_seconds > 1.0 else 0.0
            
            explicit_dict_words = self.get_dictionary_words(include_snippets=True)
            total_dict_words = len(explicit_dict_words)

            # Prefer the plausibility-filtered measurement; only fall back to the
            # raw ratio when nothing qualified as measurable.
            if avg_wpm_val > 0:
                avg_wpm = int(round(avg_wpm_val))
            elif total_duration_sec > 1.0 and total_words > 0:
                avg_wpm = int((total_words / total_duration_sec) * 60.0)
            else:
                avg_wpm = 0

            # Calculate Time Saved: Average typing speed = 40 WPM
            typing_time_min = total_words / 40.0 if total_words > 0 else 0
            dictating_time_min = total_duration_sec / 60.0 if total_duration_sec > 0 else 0
            saved_minutes = max(0.0, typing_time_min - dictating_time_min)
            saved_hours = round(saved_minutes / 60.0, 1)

            # Speed Multiplier vs Typing (40 WPM)
            speed_multiplier = round(avg_wpm / 40.0, 1) if avg_wpm > 0 else 1.0

            # REAL FIXES METRICS: Calculate actual diffs between raw_text and polished_text
            cursor = conn.execute(f"SELECT raw_text, polished_text FROM history_dedup WHERE duration_sec > 0.1 {success_cond} {date_cond}")
            rows = cursor.fetchall()
            words_corrected_count = 0
            dictionary_fixes_count = 0

            # Resolve the dictionary ONCE, up front. The previous version called
            # ``_parse_dictionary_value`` inside the per-row loop and
            # ``_dictionary_term_occurrences`` (which recompiles a regex on every
            # call) twice per row, i.e. ~26k parses and ~53k regex compiles for
            # this account. That cost ~950 ms per request to produce 17 fixes.
            dict_terms: list[tuple[str, str | None, Any, str]] = []
            for entry in explicit_dict_words:
                parsed = self._parse_dictionary_value(entry)
                if not parsed:
                    continue
                trigger, expansion = parsed
                dict_terms.append((
                    trigger,
                    expansion,
                    re.compile(
                        rf"(?<!\w){re.escape(trigger)}(?!\w)",
                        flags=re.IGNORECASE | re.UNICODE,
                    ),
                    trigger.lower(),
                ))

            for row in rows:
                r_text = row["raw_text"] or ""
                p_text = row["polished_text"] or ""
                if r_text.strip() != p_text.strip():
                    r_words = r_text.split()
                    p_words = p_text.split()
                    diff = abs(len(p_words) - len(r_words))
                    words_corrected_count += max(1, diff)

                if not dict_terms:
                    continue
                # Cheap pre-filter so the regex only runs on rows that actually
                # mention a trigger. Restricted to ASCII triggers, where
                # ``str.lower`` is guaranteed to agree with re.IGNORECASE; any
                # other trigger always falls through to the regex.
                r_lower = r_text.lower()
                p_lower = p_text.lower()
                for trigger, expansion, pattern, trigger_lower in dict_terms:
                    if trigger.isascii() and trigger_lower not in r_lower and trigger_lower not in p_lower:
                        continue
                    raw_count = len(pattern.findall(r_text))
                    polished_trigger_count = len(pattern.findall(p_text))
                    if expansion is not None:
                        dictionary_fixes_count += max(0, raw_count - polished_trigger_count)
                    else:
                        dictionary_fixes_count += max(0, polished_trigger_count - raw_count)

            # ``words_corrected_count`` is the number of dictations whose stored
            # polished_text actually differs from raw_text. The deterministic
            # cleanup layer (``style_autocleanup``) ALWAYS runs, so raw != polished
            # even when the AI polisher is switched off. The old code zeroed this
            # whenever ``polishing_enabled`` was false, which made the dashboard
            # claim 0 grammar/filler refinements while the app had in fact
            # rewritten 1,842 of 5,286 dictations. Count what really changed;
            # ``polishing_enabled`` is still reported so the UI can label the
            # source of the edits.
            polishing_enabled = self.get_setting("polishing_enabled", True)
            ai_refinements = words_corrected_count + dictionary_fixes_count

            # App breakdown with percentage calculation and category tagging.
            #
            # This card must be conservative. Older history rows only store a
            # display name, not the process executable that proves which app was
            # active, and some legacy rows were derived from browser tab titles
            # (for example "YouTube" or "Grok"). Do not surface those as apps.
            # Show only rows captured after the executable-first detector shipped;
            # everything else is counted as hidden/low-confidence instead of
            # being guessed or renamed into a fake application.
            noise_apps = _APP_ATTRIBUTION_NOISE_APPS
            noise_placeholders = ", ".join("?" for _ in noise_apps)
            cursor = conn.execute(
                f"""
                SELECT app_name, COUNT(*) as count, SUM(word_count) as total_words
                FROM history_dedup
                WHERE duration_sec > 0.1 AND word_count > 0
                  AND timestamp >= ?
                  AND COALESCE(TRIM(app_name), '') NOT IN ({noise_placeholders})
                  {attempt_cond}
                  {date_cond}
                GROUP BY app_name
                ORDER BY total_words DESC
                """,
                (_APP_ATTRIBUTION_RELIABLE_AFTER, *noise_apps),
            )
            app_breakdown_raw = [dict(row) for row in cursor.fetchall()]

            # How much dictation could not be attributed with high confidence.
            # This includes old pre-detector rows, internal app captures, tests,
            # placeholders, and browser/site names that cannot be proven to be a
            # native app from the current schema.
            unattributed_row = conn.execute(
                f"""
                SELECT COUNT(*) AS n, COALESCE(SUM(word_count), 0) AS w
                FROM history_dedup
                WHERE duration_sec > 0.1 AND word_count > 0
                  AND (
                    timestamp < ?
                    OR COALESCE(TRIM(app_name), '') IN ({noise_placeholders})
                  )
                  {attempt_cond}
                  {date_cond}
                """,
                (_APP_ATTRIBUTION_RELIABLE_AFTER, *noise_apps),
            ).fetchone()
            unattributed_count = int(unattributed_row["n"] or 0)
            unattributed_words = int(unattributed_row["w"] or 0)
            merged_apps: dict[str, dict[str, Any]] = {}

            for app in app_breakdown_raw:
                raw_name = app.get("app_name", "") or ""
                clean_name = re.sub(r"[^\w\s]", "", raw_name).strip()
                key = clean_name.lower()

                display_name = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", raw_name).strip()
                category_tag = "Other"
                if "chatgpt" in key or "claude" in key or "copilot" in key or "perplexity" in key:
                    display_name = ("ChatGPT" if "chatgpt" in key
                                    else "Claude Code" if "claude" in key
                                    else "Perplexity" if "perplexity" in key
                                    else "AI Assistant")
                    category_tag = "AI & Chat"
                elif "chrome" in key or "edge" in key or "brave" in key or "firefox" in key or "comet" in key:
                    display_name = ("Google Chrome" if "chrome" in key
                                    else "Microsoft Edge" if "edge" in key
                                    else "Comet" if "comet" in key
                                    else "Web Browser")
                    category_tag = "Browsing"
                elif "vscode" in key or "vs code" in key or "visual studio" in key or "cursor" in key or "pycharm" in key or "sublime" in key or "antigravity" in key:
                    display_name = ("Visual Studio Code" if ("vscode" in key or "vs code" in key or "visual studio" in key)
                                    else "Cursor" if "cursor" in key
                                    else "Antigravity" if "antigravity" in key
                                    else "Code Editor")
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

                w_count = int(app.get("total_words", 0) or 0)
                c_count = int(app.get("count", 0) or 0)
                if not display_name or display_name in _APP_ATTRIBUTION_NOISE_APPS:
                    unattributed_words += w_count
                    unattributed_count += c_count
                    continue

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
            app_low_confidence_words = 0
            app_low_confidence_count = 0
            visible_apps = []
            for app in sorted_merged:
                w_count = int(app["total_words"] or 0)
                if w_count < _APP_ATTRIBUTION_MIN_WORDS:
                    app_low_confidence_words += w_count
                    app_low_confidence_count += int(app["count"] or 0)
                    continue
                visible_apps.append(app)

            unattributed_words += app_low_confidence_words
            unattributed_count += app_low_confidence_count
            attributed_total = sum(app["total_words"] for app in visible_apps) or 0
            pct_base = attributed_total or 1
            for app in visible_apps:
                w_count = int(app["total_words"] or 0)
                pct = round((w_count / pct_base * 100), 1) if attributed_total > 0 else 0.0
                app_breakdown.append({
                    "app_name": app["app_name"],
                    "category": app.get("category", "General"),
                    "count": int(app["count"] or 0),
                    "total_words": w_count,
                    "percentage": pct,
                })

            app_tracking = {
                "reliable_since": _APP_ATTRIBUTION_RELIABLE_AFTER,
                "shown_count": sum(int(app.get("count", 0) or 0) for app in app_breakdown),
                "shown_words": attributed_total,
                "hidden_count": unattributed_count,
                "hidden_words": unattributed_words,
                "hidden_low_confidence_words": app_low_confidence_words,
                "min_words_to_show": _APP_ATTRIBUTION_MIN_WORDS,
                "is_conservative": True,
            }

            # All-time daily activity history map for custom Monthly Activity Calendar
            daily_history_map: dict[str, dict[str, Any]] = {}
            cursor_hist = conn.execute(
                "SELECT DATE(timestamp) as day_str, COALESCE(SUM(word_count), 0) as total_words, COUNT(*) as d_count, COALESCE(SUM(duration_sec), 0.0) as total_dur FROM history_dedup WHERE word_count > 0 AND status = 'success' GROUP BY day_str"
            )
            for row in cursor_hist.fetchall():
                d_s = row["day_str"]
                if d_s:
                    daily_history_map[d_s] = {
                        "words": int(row["total_words"] or 0),
                        "count": int(row["d_count"] or 0),
                        "duration_sec": float(row["total_dur"] or 0.0)
                    }

            # 28-day activity heatmap (backward compatibility)
            daily_activity = []
            today = datetime.date.today()
            for i in range(27, -1, -1):
                day = today - datetime.timedelta(days=i)
                day_str = day.strftime("%Y-%m-%d")
                day_info = daily_history_map.get(day_str, {"words": 0, "count": 0, "duration_sec": 0.0})
                w_int = day_info["words"]
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
            cursor = conn.execute("SELECT DISTINCT DATE(timestamp) as date_val FROM history_dedup WHERE status IN ('success', 'paste_failed') AND duration_sec > 0.1 ORDER BY date_val DESC")
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
                FROM history_dedup
                WHERE duration_sec > 0.1 {success_cond} {date_cond}
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
                {"period": "morning", "label": "Morning", "time_range": "6 AM - 12 PM", "icon": "🌅", "words": m_words, "pct": round(m_words / tod_total * 100, 1) if tod_sum > 0 else 0},
                {"period": "afternoon", "label": "Afternoon", "time_range": "12 PM - 5 PM", "icon": "☀️", "words": a_words, "pct": round(a_words / tod_total * 100, 1) if tod_sum > 0 else 0},
                {"period": "evening", "label": "Evening", "time_range": "5 PM - 10 PM", "icon": "🌆", "words": e_words, "pct": round(e_words / tod_total * 100, 1) if tod_sum > 0 else 0},
                {"period": "night", "label": "Night", "time_range": "10 PM - 6 AM", "icon": "🌙", "words": n_words, "pct": round(n_words / tod_total * 100, 1) if tod_sum > 0 else 0},
            ]

            # Calculate Peak Hours dynamically from history timestamps
            cursor = conn.execute(f"SELECT STRFTIME('%H', timestamp) as hour, COUNT(*) as count FROM history_dedup WHERE duration_sec > 0.1 {success_cond} {date_cond} GROUP BY hour ORDER BY count DESC LIMIT 1")
            peak_row = cursor.fetchone()
            if peak_row and peak_row["hour"]:
                h_int = int(peak_row["hour"])
                h12 = h_int % 12 or 12
                ampm = "AM" if h_int < 12 else "PM"
                h_next = (h_int + 1) % 12 or 12
                ampm_next = "AM" if (h_int + 1) < 12 or (h_int + 1) == 24 else "PM"
                peak_hours_str = f"{h12}:00 {ampm} – {h_next}:00 {ampm_next}"
            else:
                peak_hours_str = "--"

            # Do not fabricate a "favorite phrase" from a recent sentence
            # prefix. The previous heuristic picked the first few words of recent
            # dictations and could surface accidental text as a profile fact.
            top_phrase_str = ""

            # Voice profile: keep it measured and auditable. No personality
            # archetypes or unverifiable superlatives — only data that was
            # calculated above.
            top_app_label = app_breakdown[0]["app_name"] if app_breakdown else ""
            speed_note = (
                f"Measured speed: {avg_wpm} wpm across {measured_count:,} dictations — about {speed_multiplier}x faster than typing at 40 wpm."
                if avg_wpm > 0 and measured_count > 0
                else "Measured speed appears after a few usable dictations."
            )
            if total_words == 0:
                archetype_title = "Getting Started"
                archetype_desc = "Nothing recorded yet. Press your hotkey and this profile fills in from real dictations only."
                archetype_tag = "No Data"
                archetype_icon = "🎙️"
            elif measured_count < 5:
                archetype_title = "Collecting Profile"
                archetype_desc = "Not enough measured dictations yet for a reliable profile."
                archetype_tag = "Needs Data"
                archetype_icon = "🎙️"
            elif top_app_label:
                archetype_title = "Measured Dictation Profile"
                archetype_desc = f"Top verified app: {top_app_label}. {speed_note}"
                archetype_tag = "Verified Stats"
                archetype_icon = "📊"
            else:
                archetype_title = "Measured Dictation Profile"
                archetype_desc = f"{speed_note} App usage is still collecting high-confidence detections."
                archetype_tag = "Verified Stats"
                archetype_icon = "📊"

            return {
                "total_words": total_words,
                "avg_wpm": avg_wpm,
                "dictation_count": dictation_count,
                "speaking_hours": round(total_duration_sec / 3600.0, 1),
                "measured_dictations": measured_count,
                "unattributed": {
                    "count": unattributed_count,
                    "words": unattributed_words,
                },
                "app_tracking": app_tracking,
                "time_saved_hours": saved_hours,
                "time_saved_minutes": round(saved_minutes, 1),
                "speed_multiplier": speed_multiplier,
                "ai_refinements": ai_refinements,
                "words_corrected": words_corrected_count,
                "dictionary_fixes": dictionary_fixes_count,
                "polishing_enabled": bool(polishing_enabled),
                "total_dictionary_terms": total_dict_words,
                "streak": max(streak, 1 if total_words > 0 else 0),
                "longest_streak": longest_streak,
                "app_breakdown": app_breakdown,
                "daily_activity": daily_activity,
                "daily_history_map": daily_history_map,
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

    def consolidate_legacy_databases(self, *, dry_run: bool = False) -> dict[str, Any]:
        """Merge fragmented databases (created by the accounts feature) into the active one.

        See ``voice_flow.consolidate`` for the full implementation. Returns a
        summary dict describing merged rows / skipped duplicates.
        """
        from voice_flow.consolidate import consolidate_engine
        return consolidate_engine(self, dry_run=dry_run)

    # --- Dictionary API ---

    def get_dictionary_entries(self, include_auto: bool = True, include_snippets: bool = True) -> list[dict[str, Any]]:
        """Return dictionary rows with provenance for the vocabulary engine."""
        query = "SELECT id, word, category, created_at FROM dictionary"
        params: tuple[Any, ...] = ()
        if not include_auto:
            query += " WHERE LOWER(category) != ?"
            params = ("auto-captured",)
        query += " ORDER BY id ASC"
        with self._get_conn() as conn:
            entries = [dict(row) for row in conn.execute(query, params).fetchall()]
            if include_snippets:
                try:
                    snippets = self.get_snippets()
                    for s in snippets:
                        trig = (s.get("trigger") or "").strip()
                        exp = (s.get("expansion") or "").strip()
                        if trig and exp:
                            formatted = f"{trig} -> {exp}"
                            if not any(e["word"] == formatted for e in entries):
                                entries.append({
                                    "id": s.get("id", 0),
                                    "word": formatted,
                                    "category": "Snippets",
                                    "created_at": s.get("created_at", "")
                                })
                except Exception:
                    pass
            return entries

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

    def get_dictionary_words(self, include_auto: bool = False, include_snippets: bool = False) -> list[str]:
        """Return active explicit vocabulary by default; auto-captured rows are metadata."""
        return [row["word"] for row in self.get_dictionary_entries(include_auto=include_auto, include_snippets=include_snippets)]

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
            with self._get_conn_ctx() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute("SELECT id, word, category FROM dictionary").fetchall()
                folded = word_clean.casefold()
                match = next((row for row in existing if str(row["word"]).casefold() == folded), None)
                if match is not None:
                    if str(match["category"]).casefold() != "auto-captured" or category_clean.casefold() == "auto-captured":
                        return False
                    # A deliberate Add approves the exact spelling of a
                    # captured term. Background capture never changes it.
                    dictionary_id = match["id"]
                    conn.execute("UPDATE dictionary SET word = ?, category = ? WHERE id = ?", (word_clean, category_clean, dictionary_id))
                else:
                    cursor = conn.execute(
                        "INSERT INTO dictionary (word, category, created_at) VALUES (?, ?, ?)",
                        (word_clean, category_clean, now),
                    )
                    dictionary_id = cursor.lastrowid
                conn.execute("DELETE FROM dictionary_keys WHERE dictionary_id = ?", (dictionary_id,))
                conn.execute("INSERT OR REPLACE INTO dictionary_keys (normalized, dictionary_id) VALUES (?, ?)", (folded, dictionary_id))
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
            # Their key rows must go too: an orphaned dictionary_keys row
            # pointing at a deleted id makes the term un-re-addable (the
            # case-variant migration then deletes the fresh word at startup).
            conn.execute(
                f"DELETE FROM dictionary_keys WHERE dictionary_id IN ({placeholders})",
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
            # Deduped for the same reason as the auto-capture scan above: a term
            # that occurs 0 times still occurs 0 times once duplicates collapse,
            # so this only removes double work.
            history_rows = conn.execute(
                "SELECT raw_text FROM history "
                "GROUP BY timestamp, raw_text, polished_text"
            ).fetchall()
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
            conn.execute(
                f"DELETE FROM dictionary_keys WHERE dictionary_id IN ({placeholders})",
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
            legacy = {row["provider"]: row["api_key"] for row in cursor.fetchall()}

        # Connections are the source of truth. The legacy `api_keys` table is a
        # write-through mirror that is never pruned, so a deleted or disabled
        # connection used to keep serving its revoked key forever. Prefer the
        # live connection state, and only fall back to the legacy row for
        # providers that have no connections at all.
        res: dict[str, str] = {}
        try:
            conns = self.get_all_provider_connections() or {}
        except Exception:
            conns = {}
        for provider, clist in conns.items():
            with_key = [c for c in clist if str(c.get("api_key") or "").strip()]
            active = [c for c in with_key if c.get("is_active")]
            if active:
                res[provider] = active[0]["api_key"]
            elif with_key:
                # Provider has keyed connections but none active -> deliberately
                # omit, so disabling/deleting a key actually revokes it instead
                # of the stale legacy row resurrecting it.
                pass
            elif provider in legacy:
                # Connections exist but carry no key material (e.g. stored in
                # data_json); keep the legacy value rather than lose the key.
                res[provider] = legacy[provider]
        for provider, key in legacy.items():
            if provider not in conns:
                res[provider] = key
        return res

    # --- Provider Multi-Key Connections API ---

    def get_provider_connections(self, provider: str) -> list[dict[str, Any]]:
        p_lower = provider.lower()
        for cp in self.get_voice_flow_custom_providers():
            if cp.get("id") == p_lower:
                return [
                    {
                        "id": k.get("id") or f"c-{i}",
                        "provider": p_lower,
                        "name": k.get("name") or "Key",
                        "api_key": k.get("key") or "",
                        "priority": k.get("priority", i + 1),
                        "is_active": 1 if k.get("is_active", True) else 0,
                        "status": k.get("status") or "untested",
                        "last_tested_status": k.get("status") or "Not Tested",
                        "auth_type": "apikey",
                    }
                    for i, k in enumerate(cp.get("api_keys") or (
                        [{"name": (cp.get("name") or p_lower) + " key", "key": cp.get("api_key"), "is_active": True}] if cp.get("api_key") else []
                    ))
                ]
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM provider_connections WHERE provider = ? ORDER BY priority ASC, id ASC",
                (p_lower,)
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
        for cp in self.get_voice_flow_custom_providers():
            pid = cp.get("id")
            if pid:
                conns = [
                    {
                        "id": k.get("id") or f"c-{i}",
                        "provider": pid,
                        "name": k.get("name") or "Key",
                        "api_key": k.get("key") or "",
                        "priority": k.get("priority", i + 1),
                        "is_active": 1 if k.get("is_active", True) else 0,
                        "status": k.get("status") or "untested",
                        "last_tested_status": k.get("status") or "Not Tested",
                        "auth_type": "apikey",
                    }
                    for i, k in enumerate(cp.get("api_keys") or (
                        [{"name": (cp.get("name") or pid) + " key", "key": cp.get("api_key"), "is_active": True}] if cp.get("api_key") else []
                    ))
                ]
                result[pid] = conns
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
        auth_type: str = "apikey",
        email: str | None = None,
    ) -> dict[str, Any]:
        import uuid
        now = datetime.datetime.now().isoformat()
        clean_key = (api_key or "").strip()
        clean_name = (name or "").strip() or f"{provider.capitalize()} Key"
        uuid_str = str(uuid.uuid4())
        clean_auth = (auth_type or "apikey").lower()

        data_obj = {
            "apiKey": clean_key,
            "baseUrl": base_url or "",
            "organization": organization or "",
            "accountId": account_id or "",
            "email": email or "",
            "authType": clean_auth,
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
                    email, priority, is_active, is_valid, last_tested_at, last_error, last_tested_status,
                    data_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, NULL, 'Connected', ?, ?, ?)
                """,
                (
                    uuid_str, provider.lower(), clean_auth, clean_name, clean_key, base_url, organization, account_id,
                    email or "", priority, now, data_json, now, now
                )
            )
            conn.commit()
            cid = cursor.lastrowid
        if clean_key:
            self.save_api_key(clean_key, provider.lower())
        return {
            "id": cid,
            "uuid_id": uuid_str,
            "provider": provider.lower(),
            "authType": clean_auth,
            "auth_type": clean_auth,
            "name": clean_name,
            "email": email or "",
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
        now = datetime.datetime.now().isoformat()
        with self._get_conn() as conn:
            cursor = conn.execute(
                "UPDATE provider_connections SET name = ?, api_key = ?, priority = ?, updated_at = ? WHERE id = ?",
                (name.strip(), api_key.strip(), priority, now, cid)
            )
            conn.commit()
            return cursor.rowcount > 0

    def toggle_provider_connection(self, cid: int, is_active: bool) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "UPDATE provider_connections SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, cid)
            )
            conn.commit()
            # Report the real outcome so a stale id cannot look like success.
            return cursor.rowcount > 0

    def toggle_provider_master(self, provider_id: str, is_active: bool) -> bool:
        """Enable/disable all connections and models for a given voice flow provider."""
        active_val = 1 if is_active else 0
        p_lower = provider_id.lower()
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE provider_connections SET is_active = ? WHERE provider = ?",
                (active_val, p_lower)
            )
            conn.execute(
                "UPDATE provider_models SET is_active = ? WHERE provider = ?",
                (active_val, p_lower)
            )
            conn.commit()
        customs = self.get_voice_flow_custom_providers()
        updated = False
        for cp in customs:
            if cp.get("id") == p_lower:
                cp["is_active"] = is_active
                for k in cp.get("api_keys", []):
                    k["is_active"] = is_active
                for m in cp.get("models", []):
                    m["is_active"] = is_active
                updated = True
        if updated:
            self.save_voice_flow_custom_providers(customs)
        return True

    def delete_provider_connection(self, cid: int) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM provider_connections WHERE id = ?", (cid,))
            conn.commit()
            # Report the real outcome: a stale id must not look deleted.
            return cursor.rowcount > 0

    def update_connection_status(self, cid: int, status: str) -> None:
        status_text = str(status or "Unknown")
        valid = status_text.lower().startswith("connected") or status_text.lower() in {"active", "ready"}
        now = datetime.datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE provider_connections SET last_tested_status = ?, is_valid = ?, last_error = ?, last_tested_at = ?, updated_at = ? WHERE id = ?",
                (status_text, 1 if valid else 0, None if valid else status_text, now, now, cid),
            )
            conn.commit()


    # --- Custom Providers (user-defined OpenAI, Anthropic, Gemini, etc. endpoints) ---

    @staticmethod
    def _stable_connection_ids(api_keys: list) -> list[dict[str, Any]]:
        """Normalize connections while keeping their ids stable.

        A connection keeps the id it was created with (``c-0``, ``c-1``,
        ...), even after other connections are deleted. Renumbering on
        delete would make a surviving connection unreachable under the id
        the UI already holds; preserving ids keeps every survivor
        addressable.
        """
        cleaned: list[dict[str, Any]] = []
        used: set[str] = set()
        next_pos = 0
        for k in api_keys:
            if isinstance(k, dict):
                raw_id = str(k.get("id") or "").strip()
            else:
                raw_id = ""
            if not raw_id or raw_id in used:
                while f"c-{next_pos}" in used:
                    next_pos += 1
                raw_id = f"c-{next_pos}"
                next_pos += 1
            used.add(raw_id)
            if isinstance(k, dict):
                cleaned.append({
                    "id": raw_id,
                    "name": str((k.get("name") if isinstance(k, dict) else "Key") or "Key")[:100],
                    "key": str((k.get("key") if isinstance(k, dict) else k) or ""),
                    "priority": int(k.get("priority") or (len(cleaned) + 1)) if isinstance(k, dict) else (len(cleaned) + 1),
                    "is_active": bool(k.get("is_active", True)) if isinstance(k, dict) else True,
                    "status": str(k.get("status") or "untested") if isinstance(k, dict) else "untested",
                })
            else:
                cleaned.append({
                    "id": raw_id,
                    "name": "Key",
                    "key": str(k or ""),
                    "priority": len(cleaned) + 1,
                    "is_active": True,
                    "status": "untested",
                })
        return cleaned

    @staticmethod
    def _clean_custom_provider_entry(entry: dict[str, Any]) -> dict[str, Any]:
        entry = dict(entry)
        name = str(entry.get("name") or "").strip()
        if not name:
            raise ValueError("Provider name is required")
        base_url = str(entry.get("base_url") or "").strip()
        if not base_url.startswith("http://") and not base_url.startswith("https://"):
            raise ValueError("Base URL must start with http:// or https://")
        models = entry.get("models") or []
        if not isinstance(models, list):
            models = []
        if not models and not entry.get("id"):
            raise ValueError("Add at least one model before adding the provider")
        api_keys = entry.get("api_keys")
        if not isinstance(api_keys, list):
            api_keys = []
        if str(entry.get("api_key") or "") and not any(
            (k.get("key") if isinstance(k, dict) else k) == entry.get("api_key") for k in api_keys
        ):
            api_keys.insert(0, {"name": name + " key", "key": str(entry.get("api_key")), "is_active": True, "status": "untested"})
        raw_headers = entry.get("headers")
        if isinstance(raw_headers, dict):
            headers = raw_headers
        elif isinstance(raw_headers, str) and raw_headers.strip():
            import json as _json
            try:
                parsed_h = _json.loads(raw_headers)
                headers = parsed_h if isinstance(parsed_h, dict) else {}
            except Exception:
                headers = {}
        else:
            headers = {}
        pid = str(entry.get("id") or ("custom-" + name.lower().replace(" ", "-"))).strip()
        if not pid.startswith("custom-"):
            pid = "custom-" + pid
        return {
            "id": pid,
            "name": name,
            "base_url": base_url,
            "api_key": str(entry.get("api_key") or ""),
            "api_keys": StorageEngine._stable_connection_ids([
                k for k in api_keys
                if (isinstance(k, dict) and str(k.get("key") or "").strip()) or (isinstance(k, str) and k.strip())
            ]),
            "api_format": str(entry.get("api_format") or "openai"),
            "headers": headers,
            "load_balance_mode": str(entry.get("load_balance_mode") or "priority"),
            "is_active": bool(entry.get("is_active", True)),
            "models": [
                (
                    {
                        "id": str(m.get("id") if isinstance(m, dict) and m.get("id") else f"m-{i}"),
                        "model_id": str(m.get("model_id") or "").strip(),
                        "display_name": str(m.get("display_name") or m.get("model_id") or "").strip(),
                        "context_window": int(m.get("context_window") or 128000),
                        "max_output_tokens": int(m.get("max_output_tokens") or 8192),
                        "input_types": m.get("input_types") or ["text"],
                        "output_types": m.get("output_types") or ["text"],
                        "is_active": bool(m.get("is_active", True)),
                        "custom": True,
                    }
                    if isinstance(m, dict)
                    else {
                        "id": f"m-{i}",
                        "model_id": str(m).strip(),
                        "display_name": str(m).strip(),
                        "context_window": 128000,
                        "max_output_tokens": 8192,
                        "input_types": ["text"],
                        "output_types": ["text"],
                        "is_active": True,
                        "custom": True,
                    }
                )
                for i, m in enumerate(models or [])
                if (isinstance(m, dict) and str(m.get("model_id") or "").strip()) or (isinstance(m, str) and m.strip())
            ],
        }

    # --- Video Flow Custom Providers ---

    def get_video_flow_custom_providers(self) -> list[dict[str, Any]]:
        import json as _json
        raw = self.get_setting("video_flow_custom_providers", "[]")
        try:
            data = _json.loads(raw) if isinstance(raw, str) else (raw or [])
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def save_video_flow_custom_providers(self, providers: list[dict[str, Any]]) -> bool:
        import json as _json
        return self.save_setting("video_flow_custom_providers", _json.dumps(providers, ensure_ascii=False))

    def add_video_flow_custom_provider(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        providers = self.get_video_flow_custom_providers()
        clean = self._clean_custom_provider_entry(entry)
        providers = [p for p in providers if p["id"] != clean["id"]]
        providers.append(clean)
        self.save_video_flow_custom_providers(providers)
        return providers

    def update_video_flow_custom_provider(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        pid = str(entry.get("id") or "").strip()
        if not pid:
            raise ValueError("Provider id is required for update")
        providers = self.get_video_flow_custom_providers()
        existing = next((p for p in providers if p.get("id") == pid), None)
        if not existing:
            raise ValueError(f"Custom provider '{pid}' not found")
        merged = dict(existing)
        for k, v in entry.items():
            if v is not None:
                merged[k] = v
        clean = self._clean_custom_provider_entry(merged)
        providers = [p for p in providers if p["id"] != clean["id"]]
        providers.append(clean)
        self.save_video_flow_custom_providers(providers)
        return providers

    def delete_video_flow_custom_provider(self, provider_id: str) -> list[dict[str, Any]]:
        providers = [p for p in self.get_video_flow_custom_providers() if p.get("id") != provider_id]
        self.save_video_flow_custom_providers(providers)
        return providers

    # --- Voice Flow Custom Providers ---

    def get_voice_flow_custom_providers(self) -> list[dict[str, Any]]:
        import json as _json
        raw = self.get_setting("voice_flow_custom_providers", "[]")
        try:
            data = _json.loads(raw) if isinstance(raw, str) else (raw or [])
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def save_voice_flow_custom_providers(self, providers: list[dict[str, Any]]) -> bool:
        import json as _json
        return self.save_setting("voice_flow_custom_providers", _json.dumps(providers, ensure_ascii=False))

    def add_voice_flow_custom_provider(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        providers = self.get_voice_flow_custom_providers()
        clean = self._clean_custom_provider_entry(entry)
        providers = [p for p in providers if p["id"] != clean["id"]]
        providers.append(clean)
        self.save_voice_flow_custom_providers(providers)
        return providers

    def update_voice_flow_custom_provider(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        pid = str(entry.get("id") or "").strip()
        if not pid:
            raise ValueError("Provider id is required for update")
        providers = self.get_voice_flow_custom_providers()
        existing = next((p for p in providers if p.get("id") == pid), None)
        if not existing:
            raise ValueError(f"Custom provider '{pid}' not found")
        merged = dict(existing)
        for k, v in entry.items():
            if v is not None:
                merged[k] = v
        clean = self._clean_custom_provider_entry(merged)
        providers = [p for p in providers if p["id"] != clean["id"]]
        providers.append(clean)
        self.save_voice_flow_custom_providers(providers)
        return providers

    def delete_voice_flow_custom_provider(self, provider_id: str) -> list[dict[str, Any]]:
        providers = [p for p in self.get_voice_flow_custom_providers() if p.get("id") != provider_id]
        self.save_voice_flow_custom_providers(providers)
        return providers

    # --- Audio Flow Custom Providers ---

    def get_audio_flow_custom_providers(self) -> list[dict[str, Any]]:
        import json as _json
        raw = self.get_setting("audio_flow_custom_providers", "[]")
        try:
            data = _json.loads(raw) if isinstance(raw, str) else (raw or [])
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def save_audio_flow_custom_providers(self, providers: list[dict[str, Any]]) -> bool:
        import json as _json
        return self.save_setting("audio_flow_custom_providers", _json.dumps(providers, ensure_ascii=False))

    def add_audio_flow_custom_provider(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        providers = self.get_audio_flow_custom_providers()
        clean = self._clean_custom_provider_entry(entry)
        providers = [p for p in providers if p["id"] != clean["id"]]
        providers.append(clean)
        self.save_audio_flow_custom_providers(providers)
        return providers

    def update_audio_flow_custom_provider(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        pid = str(entry.get("id") or "").strip()
        if not pid:
            raise ValueError("Provider id is required for update")
        providers = self.get_audio_flow_custom_providers()
        existing = next((p for p in providers if p.get("id") == pid), None)
        if not existing:
            raise ValueError(f"Custom provider '{pid}' not found")
        merged = dict(existing)
        for k, v in entry.items():
            if v is not None:
                merged[k] = v
        clean = self._clean_custom_provider_entry(merged)
        providers = [p for p in providers if p["id"] != clean["id"]]
        providers.append(clean)
        self.save_audio_flow_custom_providers(providers)
        return providers

    def delete_audio_flow_custom_provider(self, provider_id: str) -> list[dict[str, Any]]:
        providers = [p for p in self.get_audio_flow_custom_providers() if p.get("id") != provider_id]
        self.save_audio_flow_custom_providers(providers)
        return providers

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
                "nvidia": "NVIDIA NIM",
                "nvidia_nim": "NVIDIA NIM",
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
                "nvidia": "🟢",
                "nvidia_nim": "🟢",
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

            for cp in self.get_voice_flow_custom_providers():
                if not cp.get("is_active", True):
                    continue
                p_id = cp.get("id")
                p_name = cp.get("name") or p_id
                cp_conns = [
                    k for k in cp.get("api_keys", [])
                    if k.get("is_active", True) and str(k.get("key") or "").strip()
                ]
                if not cp_conns and str(cp.get("api_key") or "").strip():
                    cp_conns = [{"id": f"{p_id}-key-0", "name": f"{p_name} Key", "key": cp.get("api_key"), "priority": 1, "is_active": True}]
                for ci, ck in enumerate(cp_conns):
                    conns.append({
                        "id": ck.get("id") or f"{p_id}-c-{ci}",
                        "provider": p_id,
                        "name": ck.get("name") or f"{p_name} Key",
                        "priority": ck.get("priority", ci + 1),
                        "is_active": 1,
                        "auth_type": "apikey",
                    })
                if cp_conns:
                    for m in cp.get("models", []):
                        if not m.get("is_active", True):
                            continue
                        mid = str(m.get("model_id") or "").strip()
                        disp = str(m.get("display_name") or mid).strip()
                        full_id = f"{p_id}/{mid}"
                        m_item = {
                            "full_id": full_id,
                            "label": f"{p_name} — {disp}",
                            "provider": p_id,
                            "provider_name": p_name,
                            "provider_logo": "🔌",
                            "model_id": mid,
                            "display_name": disp,
                            "has_vision": False,
                            "has_brain": True,
                        }
                        models.append(m_item)
                        if p_id not in grouped_models:
                            grouped_models[p_id] = {
                                "provider": p_id,
                                "provider_name": p_name,
                                "provider_logo": "🔌",
                                "models": [],
                            }
                        grouped_models[p_id]["models"].append(m_item)

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

    def get_exec_audio_policy_options(self, include_all_catalog: bool = False) -> dict[str, Any]:
        """Return the Audio Flow voice catalog.

        By default only providers with a saved credential (plus the built-in
        Edge and Offline voices) are listed, which is what model *selection*
        should offer. The settings dialog passes ``include_all_catalog=True``
        so a user can browse the complete voice catalog — including providers
        they have not connected yet — instead of seeing only two groups.
        """
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
            if include_all_catalog:
                catalog_providers = {
                    str(r["provider"]).lower()
                    for r in conn.execute("SELECT DISTINCT provider FROM tts_models").fetchall()
                }
                connected_providers.update(catalog_providers)

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

            for cp in self.get_audio_flow_custom_providers():
                if not cp.get("is_active", True):
                    continue
                p_id = cp.get("id")
                p_name = cp.get("name") or p_id
                cp_conns = [
                    k for k in cp.get("api_keys", [])
                    if k.get("is_active", True) and str(k.get("key") or "").strip()
                ]
                if not cp_conns and str(cp.get("api_key") or "").strip():
                    cp_conns = [{"id": f"{p_id}-key-0", "name": f"{p_name} Key", "key": cp.get("api_key"), "priority": 1, "is_active": True}]
                for ci, ck in enumerate(cp_conns):
                    conns.append({
                        "id": ck.get("id") or f"{p_id}-c-{ci}",
                        "provider": p_id,
                        "name": ck.get("name") or f"{p_name} Key",
                        "priority": ck.get("priority", ci + 1),
                        "is_active": 1,
                        "auth_type": "apikey",
                    })
                if cp_conns:
                    for m in cp.get("models", []):
                        if not m.get("is_active", True):
                            continue
                        mid = str(m.get("model_id") or "").strip()
                        disp = str(m.get("display_name") or mid).strip()
                        full_id = f"{p_id}/{mid}"
                        m_item = {
                            "full_id": full_id,
                            "label": f"{p_name} — {disp}",
                            "provider": p_id,
                            "provider_name": p_name,
                            "provider_logo": "🔊",
                            "model_id": mid,
                            "display_name": disp,
                            "has_vision": False,
                            "has_brain": True,
                        }
                        models.append(m_item)
                        if p_id not in grouped_models:
                            grouped_models[p_id] = {
                                "provider": p_id,
                                "provider_name": p_name,
                                "provider_logo": "🔊",
                                "models": [],
                            }
                        grouped_models[p_id]["models"].append(m_item)

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
        p_lower = provider.lower()
        for cp in self.get_audio_flow_custom_providers():
            if cp.get("id") == p_lower:
                return [
                    {
                        "id": k.get("id") or f"c-{i}",
                        "provider": p_lower,
                        "name": k.get("name") or "Key",
                        "api_key": k.get("key") or "",
                        "priority": k.get("priority", i + 1),
                        "is_active": 1 if k.get("is_active", True) else 0,
                        "status": k.get("status") or "untested",
                        "last_tested_status": k.get("status") or "Not Tested",
                        "auth_type": "apikey",
                    }
                    for i, k in enumerate(cp.get("api_keys") or (
                        [{"name": (cp.get("name") or p_lower) + " key", "key": cp.get("api_key"), "is_active": True}] if cp.get("api_key") else []
                    ))
                ]
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM audio_provider_connections WHERE provider = ? ORDER BY priority ASC, id ASC",
                (p_lower,)
            )
            rows = [dict(row) for row in cursor.fetchall()]
            has_key = any(r.get("api_key", "").strip() for r in rows)
            if not has_key:
                alt_cursor = conn.execute(
                    "SELECT * FROM provider_connections WHERE provider = ? ORDER BY priority ASC, id ASC",
                    (p_lower,)
                )
                alt_rows = [dict(row) for row in alt_cursor.fetchall()]
                if alt_rows:
                    # These rows come from a DIFFERENT table, so their `id` is not
                    # an audio_provider_connections id. Tag them so write paths
                    # (update/delete/toggle) refuse to act on a foreign id and
                    # cannot corrupt an unrelated provider's connection.
                    for _r in alt_rows:
                        _r["_source"] = "provider_connections"
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
        for cp in self.get_audio_flow_custom_providers():
            pid = cp.get("id")
            if pid:
                conns = [
                    {
                        "id": k.get("id") or f"c-{i}",
                        "provider": pid,
                        "name": k.get("name") or "Key",
                        "api_key": k.get("key") or "",
                        "priority": k.get("priority", i + 1),
                        "is_active": 1 if k.get("is_active", True) else 0,
                        "status": k.get("status") or "untested",
                        "last_tested_status": k.get("status") or "Not Tested",
                        "auth_type": "apikey",
                    }
                    for i, k in enumerate(cp.get("api_keys") or (
                        [{"name": (cp.get("name") or pid) + " key", "key": cp.get("api_key"), "is_active": True}] if cp.get("api_key") else []
                    ))
                ]
                result[pid] = conns
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

    def update_audio_provider_connection(self, cid: int, name: str, api_key: str, priority: int) -> bool:
        """Update a saved Audio Flow key without resetting its validation state."""
        now = datetime.datetime.now().isoformat()
        with self._get_conn() as conn:
            cursor = conn.execute(
                "UPDATE audio_provider_connections SET name = ?, api_key = ?, priority = ?, updated_at = ? WHERE id = ?",
                (name.strip(), api_key.strip(), priority, now, cid),
            )
            conn.commit()
            return cursor.rowcount > 0

    def toggle_audio_provider_connection(self, cid: int, is_active: bool) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "UPDATE audio_provider_connections SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, cid)
            )
            conn.commit()
            return cursor.rowcount > 0

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
        customs = self.get_audio_flow_custom_providers()
        updated = False
        for cp in customs:
            if cp.get("id") == p_lower:
                cp["is_active"] = is_active
                for k in cp.get("api_keys", []):
                    k["is_active"] = is_active
                for m in cp.get("models", []):
                    m["is_active"] = is_active
                updated = True
        if updated:
            self.save_audio_flow_custom_providers(customs)
        return True

    def delete_audio_provider_connection(self, cid: int) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM audio_provider_connections WHERE id = ?", (cid,))
            conn.commit()
            # Report the real outcome: a stale/foreign id must not look deleted.
            return cursor.rowcount > 0

    def update_audio_provider_connection_status(self, cid: int, status: str) -> None:
        status_text = str(status or "Unknown")
        valid = status_text.lower().startswith("connected") or status_text.lower() in {"active", "ready"}
        now = datetime.datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE audio_provider_connections SET last_tested_status = ?, is_valid = ?, last_error = ?, last_tested_at = ?, updated_at = ? WHERE id = ?",
                (status_text, 1 if valid else 0, None if valid else status_text, now, now, cid),
            )
            conn.commit()

    def get_audio_providers_overview(self) -> list[dict]:
        tts_providers = [
            {"id": "google", "name": "Google Cloud TTS", "logo": "☁️", "key_link": "https://console.cloud.google.com/apis/credentials"},
            {"id": "gemini", "name": "Gemini AI TTS", "logo": "💎", "key_link": "https://aistudio.google.com/apikey"},
            # Azure needs both a key and a region-specific endpoint, but the
            # current connection form stores only a key. Do not advertise a
            # provider the runtime cannot route correctly yet.
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

    def get_tts_model_active(self, provider: str, model_id: str) -> bool | None:
        """Return a TTS model's enabled state, or None when it is not catalogued."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT is_active FROM tts_models WHERE provider = ? AND model_id = ?",
                ((provider or "").lower(), str(model_id or "").strip()),
            ).fetchone()
        return None if row is None else bool(row["is_active"])

    def get_provider_model_active(self, provider: str, model_id: str) -> bool | None:
        """Return a Voice Flow model's enabled state, or None when unknown."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT is_active FROM provider_models WHERE provider = ? AND model_id = ?",
                ((provider or "").lower(), str(model_id or "").strip()),
            ).fetchone()
        return None if row is None else bool(row["is_active"])

    def get_provider_load_balance_mode(self, provider: str) -> str:
        provider_key = (provider or "").lower()
        try:
            with self._get_conn() as conn:
                row = conn.execute("SELECT load_balance_mode FROM provider_settings WHERE provider = ?", (provider_key,)).fetchone()
                if row and row["load_balance_mode"]:
                    return str(row["load_balance_mode"])
        except Exception:
            pass
        if provider_key.startswith("custom-"):
            try:
                for cp in self.get_voice_flow_custom_providers():
                    if str(cp.get("id") or "").lower() == provider_key:
                        m = cp.get("load_balance_mode")
                        if m:
                            return str(m)
                for cp in self.get_video_flow_custom_providers():
                    if str(cp.get("id") or "").lower() == provider_key:
                        m = cp.get("load_balance_mode")
                        if m:
                            return str(m)
            except Exception:
                pass
        return "priority"

    def save_provider_load_balance_mode(self, provider: str, mode: str) -> bool:
        provider_key = (provider or "").lower()
        mode_val = (mode or "priority").lower()
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO provider_settings (provider, load_balance_mode, is_enabled) VALUES (?, ?, 1)",
                    (provider_key, mode_val)
                )
                conn.commit()
        except Exception:
            pass
        if provider_key.startswith("custom-"):
            try:
                v_providers = self.get_voice_flow_custom_providers()
                v_updated = False
                for cp in v_providers:
                    if str(cp.get("id") or "").lower() == provider_key:
                        cp["load_balance_mode"] = mode_val
                        v_updated = True
                if v_updated:
                    self.save_voice_flow_custom_providers(v_providers)

                vid_providers = self.get_video_flow_custom_providers()
                vid_updated = False
                for cp in vid_providers:
                    if str(cp.get("id") or "").lower() == provider_key:
                        cp["load_balance_mode"] = mode_val
                        vid_updated = True
                if vid_updated:
                    self.save_video_flow_custom_providers(vid_providers)
            except Exception:
                pass
        return True

    def get_audio_provider_load_balance_mode(self, provider: str) -> str:
        provider_key = (provider or "").lower()
        try:
            with self._get_conn() as conn:
                row = conn.execute("SELECT load_balance_mode FROM audio_provider_settings WHERE provider = ?", (provider_key,)).fetchone()
                if row and row["load_balance_mode"]:
                    return str(row["load_balance_mode"])
        except Exception:
            pass
        if provider_key.startswith("custom-"):
            try:
                for cp in self.get_audio_flow_custom_providers():
                    if str(cp.get("id") or "").lower() == provider_key:
                        m = cp.get("load_balance_mode")
                        if m:
                            return str(m)
            except Exception:
                pass
        return "priority"

    def save_audio_provider_load_balance_mode(self, provider: str, mode: str) -> bool:
        provider_key = (provider or "").lower()
        mode_val = (mode or "priority").lower()
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO audio_provider_settings (provider, load_balance_mode, is_enabled) VALUES (?, ?, 1)",
                    (provider_key, mode_val)
                )
                conn.commit()
        except Exception:
            pass
        if provider_key.startswith("custom-"):
            try:
                providers = self.get_audio_flow_custom_providers()
                updated = False
                for cp in providers:
                    if str(cp.get("id") or "").lower() == provider_key:
                        cp["load_balance_mode"] = mode_val
                        updated = True
                if updated:
                    self.save_audio_flow_custom_providers(providers)
            except Exception:
                pass
        return True

    def get_downloadable_models(self) -> list[dict[str, Any]]:
        from voice_flow import downloadable_models
        return downloadable_models.get_all_models_status()

    def get_downloaded_stt_models(self) -> list[dict[str, Any]]:
        from voice_flow import downloadable_models
        return downloadable_models.get_downloaded_stt_models()

    def get_downloaded_polish_models(self) -> list[dict[str, Any]]:
        from voice_flow import downloadable_models
        return downloadable_models.get_downloaded_polish_models()

    def get_default_polish_model(self) -> str:
        """Return default polish model: Microsoft Windows AI on Windows when available, otherwise local/deterministic."""
        import sys
        if sys.platform == "win32":
            try:
                from voice_flow import windows_ai_rewriter
                if windows_ai_rewriter.is_windows_ai_available():
                    return "microsoft/windows-ai-text-rewriter"
            except Exception:
                pass
        return "local/deterministic"

    def get_provider_models(self, provider: str) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM provider_models WHERE provider = ? ORDER BY id ASC", (provider.lower(),))
            return [dict(row) for row in cursor.fetchall()]

    def toggle_provider_model(self, model_db_id: int, is_active: bool) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute("UPDATE provider_models SET is_active = ? WHERE id = ?", (1 if is_active else 0, model_db_id))
            conn.commit()
            # Report the real outcome so toggling a bogus id is not "success".
            return cursor.rowcount > 0

    def add_provider_model(self, provider: str, model_id: str, display_name: str) -> bool:
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO provider_models (provider, model_id, display_name, is_active, custom) VALUES (?, ?, ?, 1, 1)",
                    (provider.lower(), model_id.strip(), display_name.strip())
                )
                conn.commit()
                return True
        except Exception:
            return False

    def delete_provider_model(self, model_db_id: int | str, provider: str | None = None) -> bool:
        try:
            with self._get_conn() as conn:
                if str(model_db_id).isdigit():
                    cursor = conn.execute("DELETE FROM provider_models WHERE id = ?", (int(model_db_id),))
                elif provider:
                    cursor = conn.execute("DELETE FROM provider_models WHERE provider = ? AND model_id = ?", (provider.lower(), str(model_db_id)))
                else:
                    cursor = conn.execute("DELETE FROM provider_models WHERE model_id = ?", (str(model_db_id),))
                conn.commit()
                return cursor.rowcount > 0
        except Exception:
            return False

    def add_tts_model(self, provider: str, model_id: str, display_name: str) -> bool:
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO tts_models (provider, model_id, display_name, is_active, custom) VALUES (?, ?, ?, 1, 1)",
                    (provider.lower(), model_id.strip(), display_name.strip())
                )
                conn.commit()
                return True
        except Exception:
            return False

    def delete_tts_model(self, model_db_id: int | str, provider: str | None = None) -> bool:
        try:
            with self._get_conn() as conn:
                if str(model_db_id).isdigit():
                    cursor = conn.execute("DELETE FROM tts_models WHERE id = ?", (int(model_db_id),))
                elif provider:
                    cursor = conn.execute("DELETE FROM tts_models WHERE provider = ? AND model_id = ?", (provider.lower(), str(model_db_id)))
                else:
                    cursor = conn.execute("DELETE FROM tts_models WHERE model_id = ?", (str(model_db_id),))
                conn.commit()
                return cursor.rowcount > 0
        except Exception:
            return False

    # --- Settings Persistence API ---

    def get_tts_model_family(self, provider: str, model_id: str) -> str | None:
        """Return the model_family for a tts_models row, if set (e.g. ElevenLabs model)."""
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    "SELECT model_family FROM tts_models WHERE provider=? AND model_id=?",
                    (provider, model_id),
                )
                row = cursor.fetchone()
                if row is not None and row["model_family"]:
                    return str(row["model_family"])
        except Exception:
            pass
        return None

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
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row is None:
                return default
            import json as _json
            try:
                value = _json.loads(row["value"])
            except (ValueError, TypeError):
                value = row["value"]
            if key == "polishing_enabled":
                # Old clients sometimes saved a quoted boolean. Keep API,
                # engine and restart reads consistent without rewriting data.
                if isinstance(value, str):
                    return value.strip().lower() in ("true", "1")
                return value is True or value == 1
            return value

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

    def get_hotkey_settings(self) -> dict[str, Any]:
        """Retrieve current user-configurable hotkey and trigger settings."""
        label_map = {
            "ctrl_win": "Ctrl+Win",
            "single_ctrl": "Single Ctrl",
            "double_ctrl": "Double Ctrl",
            "alt_space": "Alt+Space",
            "alt_tab": "Alt+Tab",
            "middle_click": "Middle Mouse Button",
        }
        trigger = str(self.get_setting("hotkey_trigger", "ctrl_win") or "ctrl_win")
        custom_key = str(self.get_setting("custom_hotkey", "Alt+Space") or "Alt+Space")
        trigger_mode = str(self.get_setting("dictation_trigger_mode", "hybrid") or "hybrid")
        middle_enabled = bool(self.get_setting("middle_click_enabled", True))
        ctrl_enabled = bool(self.get_setting("ctrl_key_dictation_enabled", trigger in ("single_ctrl", "double_ctrl")))
        saved_ptt = self.get_setting("push_to_talk_shortcut")
        if saved_ptt:
            ptt_label = str(saved_ptt)
        elif trigger == "custom":
            ptt_label = custom_key
        else:
            ptt_label = label_map.get(trigger, "Ctrl+Win")
        custom_trigger_type = str(self.get_setting("custom_trigger_type", "hold") or "hold").lower().strip()
        return {
            "hotkey_trigger": trigger,
            "custom_hotkey": custom_key,
            "custom_trigger_type": custom_trigger_type,
            "dictation_trigger_mode": trigger_mode,
            "middle_click_enabled": middle_enabled,
            "ctrl_key_dictation_enabled": ctrl_enabled,
            "push_to_talk_shortcut": ptt_label,
        }

    def save_hotkey_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        """Persist user-configurable hotkey settings and synchronize labels."""
        if not isinstance(data, dict):
            return self.get_hotkey_settings()

        label_map = {
            "ctrl_win": "Ctrl+Win",
            "single_ctrl": "Single Ctrl",
            "double_ctrl": "Double Ctrl",
            "alt_space": "Alt+Space",
            "alt_tab": "Alt+Tab",
            "middle_click": "Middle Mouse Button",
        }
        reverse_label_map = {v.lower(): k for k, v in label_map.items()}
        reverse_label_map.update({
            "ctrl+win": "ctrl_win",
            "win+ctrl": "ctrl_win",
            "single ctrl": "single_ctrl",
            "double ctrl": "double_ctrl",
            "alt+space": "alt_space",
            "alt+tab": "alt_tab",
            "middle mouse button": "middle_click",
            "middle_click": "middle_click",
        })

        if "push_to_talk_shortcut" in data and data["push_to_talk_shortcut"] is not None:
            ptt_str = str(data["push_to_talk_shortcut"]).strip()
            self.save_setting("push_to_talk_shortcut", ptt_str)
            ptt_lower = ptt_str.lower()
            if ptt_lower in reverse_label_map:
                trigger_from_ptt = reverse_label_map[ptt_lower]
                if "hotkey_trigger" not in data or not data["hotkey_trigger"]:
                    data["hotkey_trigger"] = trigger_from_ptt
            elif "hotkey_trigger" not in data or not data["hotkey_trigger"]:
                data["hotkey_trigger"] = "custom"
                data["custom_hotkey"] = ptt_str

        if "hotkey_trigger" in data and data["hotkey_trigger"] is not None:
            trigger = str(data["hotkey_trigger"]).lower().strip()
            self.save_setting("hotkey_trigger", trigger)
            if trigger in label_map:
                self.save_setting("push_to_talk_shortcut", label_map[trigger])
            elif trigger == "custom":
                custom_str = str(data.get("custom_hotkey") or self.get_setting("custom_hotkey", "Alt+Space") or "Alt+Space").strip()
                self.save_setting("push_to_talk_shortcut", custom_str)

            if trigger in ("single_ctrl", "double_ctrl"):
                self.save_setting("ctrl_key_dictation_enabled", True)
            elif "ctrl_key_dictation_enabled" not in data:
                self.save_setting("ctrl_key_dictation_enabled", False)

        if "custom_hotkey" in data and data["custom_hotkey"] is not None:
            custom_val = str(data["custom_hotkey"]).strip()
            if custom_val:
                self.save_setting("custom_hotkey", custom_val)
                if data.get("hotkey_trigger") == "custom":
                    self.save_setting("push_to_talk_shortcut", custom_val)

        if "custom_trigger_type" in data and data["custom_trigger_type"] is not None:
            ct = str(data["custom_trigger_type"]).lower().strip()
            if ct in ("double_tap", "hold", "mouse_button", "toggle"):
                self.save_setting("custom_trigger_type", ct)

        if "dictation_trigger_mode" in data and data["dictation_trigger_mode"] is not None:
            self.save_setting("dictation_trigger_mode", str(data["dictation_trigger_mode"]).lower().strip())

        if "middle_click_enabled" in data and data["middle_click_enabled"] is not None:
            self.save_setting("middle_click_enabled", bool(data["middle_click_enabled"]))

        if "ctrl_key_dictation_enabled" in data and data["ctrl_key_dictation_enabled"] is not None:
            self.save_setting("ctrl_key_dictation_enabled", bool(data["ctrl_key_dictation_enabled"]))

        # Synchronize in-memory config singleton
        try:
            from voice_flow.config import config as _cfg
            current = self.get_hotkey_settings()
            _cfg.hotkey_trigger = current["hotkey_trigger"]
            _cfg.custom_hotkey = current["custom_hotkey"]
            _cfg.custom_trigger_type = current.get("custom_trigger_type", "hold")
            _cfg.dictation_trigger_mode = current["dictation_trigger_mode"]
            _cfg.middle_click_enabled = current["middle_click_enabled"]
            _cfg.ctrl_key_dictation_enabled = current["ctrl_key_dictation_enabled"]
            _cfg.push_to_talk_shortcut = current["push_to_talk_shortcut"]
        except Exception:
            pass

        return self.get_hotkey_settings()


    def get_history_record(self, record_id: int) -> dict[str, Any] | None:
        with self._get_conn() as conn:
            # Resolve through the dedup key so callers get the merged row no
            # matter which copy's id they hold, and so audio_path survives when
            # only one of the copies carries it.
            key = self._dedup_key_for(conn, record_id)
            if not key:
                return None
            row = conn.execute(
                f"SELECT * FROM ({_DEDUP_HISTORY_SELECT}) WHERE {_DEDUP_KEY_WHERE}",
                key,
            ).fetchone()
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
            # Fan out to every copy of this dictation. They share the same
            # dedup key, so updating them together keeps them in sync and stops
            # a stale twin from resurfacing with the old text or status.
            key = self._dedup_key_for(conn, record_id)
            if not key:
                return False
            cursor = conn.execute(
                f"UPDATE history SET {assignments} WHERE {_DEDUP_KEY_WHERE}",
                (*values.values(), *key),
            )
            conn.commit()
            return cursor.rowcount >= 1

    def delete_history_record(self, record_id: int) -> dict[str, Any] | None:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM history WHERE id = ?", (record_id,)).fetchone()
            if not row:
                return None
            # Remove every copy, otherwise the delete looks like a no-op.
            conn.execute(
                f"DELETE FROM history WHERE {_DEDUP_KEY_WHERE}",
                (row["timestamp"], row["raw_text"], row["polished_text"]),
            )
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
                # Normalized keys are a derived index, never authoritative
                # over saved words. Old renames could leave both wrong and
                # orphaned keys; rebuild the index atomically from live rows.
                indexed = {row["normalized"]: row["dictionary_id"] for row in conn.execute(
                    "SELECT normalized, dictionary_id FROM dictionary_keys"
                )}
                if indexed != keepers:
                    conn.execute("DELETE FROM dictionary_keys")
                    conn.executemany(
                        "INSERT INTO dictionary_keys (normalized, dictionary_id) VALUES (?, ?)",
                        keepers.items(),
                    )
                    changed = True
            if changed:
                self._touch_lexicon()

    def _migrate_audio_summary_history(self) -> None:
        """Ensure title, status, error, and progress columns exist on audio_summary_history."""
        with self._get_conn_ctx() as conn:
            try:
                cols = [row[1] for row in conn.execute("PRAGMA table_info(audio_summary_history)").fetchall()]
                if cols:
                    if "title" not in cols:
                        conn.execute("ALTER TABLE audio_summary_history ADD COLUMN title TEXT")
                    if "status" not in cols:
                        conn.execute("ALTER TABLE audio_summary_history ADD COLUMN status TEXT DEFAULT 'ready'")
                    if "error" not in cols:
                        conn.execute("ALTER TABLE audio_summary_history ADD COLUMN error TEXT")
                    if "progress" not in cols:
                        conn.execute("ALTER TABLE audio_summary_history ADD COLUMN progress INTEGER DEFAULT 100")
                    if "downloaded" not in cols:
                        conn.execute("ALTER TABLE audio_summary_history ADD COLUMN downloaded INTEGER DEFAULT 0")
                    conn.commit()
            except Exception as exc:
                log.debug("Audio summary history migration note: %s", exc)

    def get_dictionary_snapshot(self) -> tuple[int, list[str], list[dict[str, Any]]]:
        """Read a dictionary/correction snapshot matching one revision."""
        with self._lexicon_lock:
            # sqlite3.Connection.__exit__ commits but does not close the
            # connection. These snapshots are polled during dictation, so use
            # the closing context manager rather than leaking a handle per
            # refresh.
            with self._get_conn_ctx() as conn:
                words = [row["word"] for row in conn.execute(
                    "SELECT word FROM dictionary WHERE LOWER(category) != ? ORDER BY word ASC",
                    ("auto-captured",),
                )
                         if "->" not in row["word"] and "=>" not in row["word"]]
                snippets = conn.execute("SELECT trigger, expansion FROM snippets ORDER BY trigger ASC").fetchall()
                for s in snippets:
                    trig = (s["trigger"] or "").strip()
                    exp = (s["expansion"] or "").strip()
                    if trig and exp:
                        words.append(f"{trig} -> {exp}")
                corrections = [dict(row) for row in conn.execute(
                    "SELECT id, wrong_text, correct_text, created_at, updated_at FROM dictionary_corrections "
                    "ORDER BY wrong_text COLLATE NOCASE"
                )]
                return self._lexicon_revision, words, corrections

    def get_snippet_snapshot(self) -> tuple[int, list[dict[str, Any]]]:
        with self._lexicon_lock:
            with self._get_conn_ctx() as conn:
                snippets = [dict(row) for row in conn.execute(
                    "SELECT id, trigger, expansion, created_at, updated_at FROM snippets ORDER BY trigger COLLATE NOCASE"
                )]
                return self._lexicon_revision, snippets

    def get_dictionary_corrections(self) -> list[dict[str, Any]]:
        with self._get_conn_ctx() as conn:
            rows = conn.execute(
                "SELECT id, wrong_text, correct_text, created_at, updated_at "
                "FROM dictionary_corrections ORDER BY wrong_text COLLATE NOCASE"
            ).fetchall()
            return [dict(row) for row in rows]

    # -- learned vocabulary candidates (spec SS34-37) --------------------

    def record_lexicon_candidate(self, term: str, variant: str = "", source: str = "correction") -> bool:
        """Record one (correct term, misheard variant) observation.

        Repeated evidence promotes candidate -> suggested; nothing becomes
        active without explicit user approval. Returns True when promoted.
        """
        term = (term or "").strip()
        variant = (variant or "").strip()
        if not term or term.casefold() == variant.casefold():
            return False
        import datetime as _dt

        now = _dt.datetime.now().isoformat(timespec="seconds")
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT id, evidence, state FROM lexicon_candidates "
                "WHERE term = ? COLLATE NOCASE AND variant = ? COLLATE NOCASE",
                (term, variant),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO lexicon_candidates (term, variant, evidence, state, source, created_at, updated_at) "
                    "VALUES (?, ?, 1, 'candidate', ?, ?, ?)",
                    (term, variant, source, now, now),
                )
                self._touch_lexicon(conn)
                return False
            evidence = int(row["evidence"]) + 1
            state = str(row["state"])
            promoted = False
            if state == "candidate" and evidence >= 3:
                state = "suggested"
                promoted = True
            conn.execute(
                "UPDATE lexicon_candidates SET evidence = ?, state = ?, updated_at = ? WHERE id = ?",
                (evidence, state, now, row["id"]),
            )
            self._touch_lexicon(conn)
            conn.commit()
            return promoted

    def get_lexicon_suggestions(self, limit: int = 20) -> list[dict[str, Any]]:
        """Candidates with enough evidence to suggest (spec SS37: only
        'suggested' rows surface; raw candidates stay internal)."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, term, variant, evidence, state, source, created_at, updated_at "
                "FROM lexicon_candidates WHERE state = 'suggested' "
                "ORDER BY evidence DESC, updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def set_lexicon_candidate_state(self, candidate_id: int, state: str) -> bool:
        """User decision on a suggestion: active (adds to dictionary), ignored."""
        if state not in ("active", "ignored", "candidate"):
            return False
        import datetime as _dt

        now = _dt.datetime.now().isoformat(timespec="seconds")
        with self._get_conn() as conn:
            row = conn.execute("SELECT term FROM lexicon_candidates WHERE id = ?", (candidate_id,)).fetchone()
            if row is None:
                return False
            conn.execute(
                "UPDATE lexicon_candidates SET state = ?, updated_at = ? WHERE id = ?",
                (state, now, candidate_id),
            )
            self._touch_lexicon(conn)
        if state == "active":
            try:
                self.add_dictionary_word(row["term"], category="Personal")
            except Exception:
                log.exception("Could not add approved candidate %r", row["term"])
        return True

    def update_dictionary_word(self, old_word: str, new_word: str) -> bool:
        """Rename/replace a dictionary term in place (inline chip editing).

        Explicit edits approve captured terms. Returns False when the old term is missing
        or the new text is empty/invalid.
        """
        if not isinstance(old_word, str) or not isinstance(new_word, str):
            return False
        old_clean = old_word.strip()
        new_clean = new_word.strip()
        if (
            not old_clean
            or not new_clean
            or len(new_clean) > 240
            or "->" in new_clean
            or "=>" in new_clean
        ):
            return False
        with self._lexicon_lock:
            with self._get_conn_ctx() as conn:
                conn.execute("BEGIN IMMEDIATE")
                rows = conn.execute("SELECT id, word, category FROM dictionary").fetchall()
                matching = [row for row in rows if str(row["word"]).casefold() == old_clean.casefold()]
                if not matching:
                    return False
                target_id = int(matching[0]["id"])
                matching_ids = {int(row["id"]) for row in matching}
                if any(int(row["id"]) not in matching_ids and str(row["word"]).casefold() == new_clean.casefold() for row in rows):
                    return False
                # A same-cased twin must not block the edit; remove it first.
                for row in matching[1:]:
                    duplicate_id = int(row["id"])
                    conn.execute("DELETE FROM dictionary WHERE id = ?", (duplicate_id,))
                    conn.execute("DELETE FROM dictionary_keys WHERE dictionary_id = ?", (duplicate_id,))
                conn.execute(
                    "UPDATE dictionary SET word = ?, category = CASE WHEN LOWER(category) = 'auto-captured' THEN 'Personal' ELSE category END WHERE id = ?",
                    (new_clean, target_id),
                )
                conn.execute("DELETE FROM dictionary_keys WHERE dictionary_id = ?", (target_id,))
                conn.execute("INSERT OR REPLACE INTO dictionary_keys (normalized, dictionary_id) VALUES (?, ?)", (new_clean.casefold(), target_id))
                # Keep the cross-process revision in the same transaction as
                # the edit, so an already-running dictation engine cannot see
                # a committed word with an unchanged revision.
                self._touch_lexicon(conn)
        return True

    def get_contextual_vocabulary(self, category: str, limit: int = 15) -> list[str]:
        """Dictionary terms explicitly tagged for an app category (spec SS33)."""
        if not category:
            return []
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT word FROM dictionary WHERE LOWER(category) = LOWER(?) "
                "ORDER BY length(word) DESC LIMIT ?",
                (category, limit),
            ).fetchall()
            return [str(r["word"]) for r in rows]

    def migrate_learned_vocabulary(self) -> int:
        """One-time bridge for learned vocabulary visibility (spec SS34-37).

        Words the old frequency learner parked as invisible 'Auto-Captured'
        become evidence-backed suggestions the user can approve; sound-alike
        repairs for the critical wake term are seeded as corrections.
        Idempotent via a settings flag. Returns the number of suggestions.
        """
        try:
            if self.get_setting("lexicon_migration_v1", False):
                return 0
        except Exception:
            pass
        import datetime as _dt

        now = _dt.datetime.now().isoformat(timespec="seconds")
        promoted = 0
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT word FROM dictionary WHERE LOWER(category) = 'auto-captured' ORDER BY word"
            ).fetchall()
            for row in rows:
                term = str(row["word"] or "").strip()
                if not term or len(term) < 3:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO lexicon_candidates "
                    "(term, variant, evidence, state, source, created_at, updated_at) "
                    "VALUES (?, '', 3, 'suggested', 'usage-history', ?, ?)",
                    (term, now, now),
                )
                promoted += 1
        # Sound-alike wake repairs are NOT stored as dictionary rows or
        # corrections: that would pollute STT hints and override the user's
        # own "VoiceFlow" casing. They live only in dictionary_engine's
        # static repair pattern list.
        try:
            self.save_setting("lexicon_migration_v1", True)
        except Exception:
            pass
        return promoted

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
        with self._get_conn_ctx() as conn:
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

    def get_audio_summary_cache(self, cache_key: str) -> dict[str, Any] | None:
        """Retrieve cached audio summary by composite cache key."""
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM audio_summary_cache WHERE cache_key = ?", (cache_key,)).fetchone()
            return dict(row) if row else None

    def set_audio_summary_cache(
        self,
        cache_key: str,
        text_hash: str,
        depth: str,
        model_ref: str,
        summary_text: str,
        cached_at: str
    ) -> None:
        """Store or update audio summary cache entry."""
        with self._get_conn_ctx() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO audio_summary_cache (cache_key, text_hash, depth, model_ref, summary_text, cached_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (cache_key, text_hash, depth, model_ref, summary_text, cached_at))

    def clear_audio_summary_cache(self) -> int:
        """Clear all cached audio summaries."""
        with self._get_conn_ctx() as conn:
            cursor = conn.execute("DELETE FROM audio_summary_cache")
            return cursor.rowcount

    @staticmethod
    def _derive_audio_title(source_text: str) -> str:
        """Derive a concise human title from the audio summary source text's main topic."""
        import re as _re
        for raw in (source_text or "").splitlines():
            line = _re.sub(r"^#+\s*", "", (raw or "").strip())
            line = _re.sub(r"^[\*\-\u2022\d\.\s]+", "", line).strip()
            line = _re.sub(r"\*+", "", line).strip()
            if len(line) >= 8:
                out = " ".join(line.split()[:9]).strip()
                return (out[:57].rstrip() + "...") if len(out) > 60 else out
        text = _re.sub(r"\s+", " ", (source_text or "")).strip()
        if text:
            sentence = _re.split(r"(?<=[.!?])\s", text)[0]
            out = " ".join(sentence.split()[:9]).strip()
            return (out[:57].rstrip() + "...") if len(out) > 60 else out
        return "Audio Summary"


    def add_audio_summary_history(
        self,
        text: str,
        depth: str,
        audio_path: str = "",
        duration_sec: float = 0.0,
        item_id: str | None = None,
        created_at: str | None = None,
        title: str | None = None,
        status: str = "ready",
        error: str | None = None,
        progress: int = 100,
        downloaded: int = 0,
    ) -> dict[str, Any]:
        """Record a completed or in-progress audio summary in history."""
        import uuid
        from datetime import datetime, timezone
        now = created_at or datetime.now(timezone.utc).isoformat()
        uid = item_id or f"ash_{uuid.uuid4().hex[:12]}"
        clean_text = (text or "").strip()
        summary_title = (title or "").strip() or self._derive_audio_title(clean_text)
        snippet = clean_text[:140] if clean_text else summary_title
        if len(clean_text) > 140:
            snippet += "…"
        status_val = str(status or "ready").strip().lower()
        with self._get_conn_ctx() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO audio_summary_history
                (id, title, text_snippet, full_text, depth, audio_path, duration_sec, status, error, progress, created_at, downloaded)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                uid,
                summary_title,
                snippet,
                clean_text,
                str(depth or "balanced"),
                str(audio_path or ""),
                float(duration_sec or 0.0),
                status_val,
                str(error) if error else None,
                int(progress if progress is not None else 100),
                now,
                1 if downloaded else 0,
            ))
            conn.commit()
        return {
            "id": uid,
            "title": summary_title,
            "text_snippet": snippet,
            "full_text": clean_text,
            "depth": str(depth or "balanced"),
            "audio_path": str(audio_path or ""),
            "duration_sec": float(duration_sec or 0.0),
            "status": status_val,
            "error": str(error) if error else None,
            "progress": int(progress if progress is not None else 100),
            "created_at": now,
            "downloaded": bool(downloaded),
        }

    def update_audio_summary_history(
        self,
        item_id: str,
        *,
        status: str | None = None,
        error: str | None = None,
        progress: int | None = None,
        audio_path: str | None = None,
        duration_sec: float | None = None,
        title: str | None = None,
        downloaded: int | bool | None = None,
    ) -> bool:
        """Update status, error, progress, audio results, or downloaded flag of an existing summary."""
        updates: list[str] = []
        vals: list[Any] = []
        if status is not None:
            updates.append("status = ?")
            vals.append(str(status).strip().lower())
        if error is not None:
            updates.append("error = ?")
            vals.append(str(error) if error else None)
        if progress is not None:
            updates.append("progress = ?")
            vals.append(int(progress))
        if audio_path is not None:
            updates.append("audio_path = ?")
            vals.append(str(audio_path))
        if duration_sec is not None:
            updates.append("duration_sec = ?")
            vals.append(float(duration_sec))
        if title is not None:
            updates.append("title = ?")
            vals.append(str(title).strip())
        if downloaded is not None:
            updates.append("downloaded = ?")
            vals.append(1 if downloaded else 0)
        if not updates:
            return False
        vals.append(str(item_id or ""))
        with self._get_conn_ctx() as conn:
            cur = conn.execute(f"UPDATE audio_summary_history SET {', '.join(updates)} WHERE id = ?", tuple(vals))
            conn.commit()
            return cur.rowcount > 0

    def get_audio_summary_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve recent audio summary history records."""
        with self._get_conn_ctx() as conn:
            rows = conn.execute("""
                SELECT id, title, text_snippet, full_text, depth, audio_path, duration_sec, status, error, progress, created_at, downloaded
                FROM audio_summary_history
                ORDER BY created_at DESC
                LIMIT ?
            """, (max(1, int(limit)),)).fetchall()
            return [
                {
                    "id": r[0],
                    "title": r[1] or r[2] or "Audio Summary",
                    "text_snippet": r[2],
                    "full_text": r[3],
                    "depth": r[4],
                    "audio_path": r[5],
                    "duration_sec": float(r[6] or 0.0),
                    "status": r[7] or "ready",
                    "error": r[8],
                    "progress": int(r[9] if r[9] is not None else 100),
                    "created_at": r[10],
                    "downloaded": bool(r[11]) if len(r) > 11 and r[11] else False,
                }
                for r in rows
            ]

    def get_audio_summary_history_by_id(self, item_id: str) -> dict[str, Any] | None:
        """Lookup a specific audio summary history entry."""
        with self._get_conn_ctx() as conn:
            row = conn.execute("""
                SELECT id, title, text_snippet, full_text, depth, audio_path, duration_sec, status, error, progress, created_at, downloaded
                FROM audio_summary_history
                WHERE id = ?
            """, (str(item_id or ""),)).fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "title": row[1] or row[2] or "Audio Summary",
                "text_snippet": row[2],
                "full_text": row[3],
                "depth": row[4],
                "audio_path": row[5],
                "duration_sec": float(row[6] or 0.0),
                "status": row[7] or "ready",
                "error": row[8],
                "progress": int(row[9] if row[9] is not None else 100),
                "created_at": row[10],
                "downloaded": bool(row[11]) if len(row) > 11 and row[11] else False,
            }

    def delete_audio_summary_history(self, item_id: str) -> bool:
        """Delete an audio summary entry from history."""
        with self._get_conn_ctx() as conn:
            cursor = conn.execute("DELETE FROM audio_summary_history WHERE id = ?", (str(item_id or ""),))
            return cursor.rowcount > 0

    def export_vault_data(self) -> dict[str, Any]:
        """Extract all portable user configurations, connections, dictionary, and styles."""
        vault: dict[str, Any] = {
            "version": 1,
            "settings": [],
            "provider_connections": [],
            "audio_provider_connections": [],
            "video_flow_provider_connections": [],
            "api_keys": [],
            "dictionary": [],
            "dictionary_corrections": [],
            "snippets": [],
            "provider_settings": [],
            "audio_provider_settings": [],
        }
        with self._get_conn_ctx() as conn:
            # 1. Settings
            try:
                rows = conn.execute("SELECT key, value, updated_at FROM settings").fetchall()
                vault["settings"] = [
                    {"key": row["key"], "value": row["value"], "updated_at": row["updated_at"]}
                    for row in rows
                ]
            except Exception:
                pass

            # 2. Provider connections
            try:
                rows = conn.execute("SELECT * FROM provider_connections").fetchall()
                vault["provider_connections"] = [dict(row) for row in rows]
            except Exception:
                pass

            # 3. Audio provider connections
            try:
                rows = conn.execute("SELECT * FROM audio_provider_connections").fetchall()
                vault["audio_provider_connections"] = [dict(row) for row in rows]
            except Exception:
                pass

            # 4. Video Flow provider connections
            try:
                rows = conn.execute("SELECT * FROM video_flow_provider_connections").fetchall()
                vault["video_flow_provider_connections"] = [dict(row) for row in rows]
            except Exception:
                pass

            # 5. Legacy API keys
            try:
                rows = conn.execute("SELECT api_key, provider, created_at FROM api_keys").fetchall()
                vault["api_keys"] = [
                    {"api_key": row["api_key"], "provider": row["provider"], "created_at": row["created_at"]}
                    for row in rows
                ]
            except Exception:
                pass

            # 6. Dictionary
            try:
                rows = conn.execute("SELECT word, category, created_at FROM dictionary").fetchall()
                vault["dictionary"] = [
                    {"word": row["word"], "category": row["category"], "created_at": row["created_at"]}
                    for row in rows
                ]
            except Exception:
                pass

            # 7. Corrections
            try:
                rows = conn.execute("SELECT wrong_text, correct_text, created_at, updated_at FROM dictionary_corrections").fetchall()
                vault["dictionary_corrections"] = [
                    {"wrong_text": row["wrong_text"], "correct_text": row["correct_text"], "created_at": row["created_at"], "updated_at": row["updated_at"]}
                    for row in rows
                ]
            except Exception:
                pass

            # 8. Snippets
            try:
                rows = conn.execute("SELECT trigger, expansion, created_at, updated_at FROM snippets").fetchall()
                vault["snippets"] = [
                    {"trigger": row["trigger"], "expansion": row["expansion"], "created_at": row["created_at"], "updated_at": row["updated_at"]}
                    for row in rows
                ]
            except Exception:
                pass

            # 9. Provider settings
            try:
                rows = conn.execute("SELECT provider, load_balance_mode, is_enabled FROM provider_settings").fetchall()
                vault["provider_settings"] = [
                    {"provider": row["provider"], "load_balance_mode": row["load_balance_mode"], "is_enabled": row["is_enabled"]}
                    for row in rows
                ]
            except Exception:
                pass

            # 10. Audio provider settings
            try:
                rows = conn.execute("SELECT provider, load_balance_mode, is_enabled FROM audio_provider_settings").fetchall()
                vault["audio_provider_settings"] = [
                    {"provider": row["provider"], "load_balance_mode": row["load_balance_mode"], "is_enabled": row["is_enabled"]}
                    for row in rows
                ]
            except Exception:
                pass

        return vault

    def import_vault_data(self, vault_data: dict[str, Any]) -> dict[str, int]:
        """Restore settings, connections, dictionary, and styles into the active database."""
        stats = {
            "settings": 0,
            "provider_connections": 0,
            "audio_provider_connections": 0,
            "video_flow_provider_connections": 0,
            "api_keys": 0,
            "dictionary": 0,
            "dictionary_corrections": 0,
            "snippets": 0,
        }
        with self._get_conn_ctx() as conn:
            # 1. Settings
            for s in vault_data.get("settings", []):
                key = s.get("key")
                if key and key not in ("seed_version", "dictionary_revision"):
                    conn.execute(
                        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                        (key, s.get("value"), s.get("updated_at") or datetime.datetime.now(datetime.timezone.utc).isoformat()),
                    )
                    stats["settings"] += 1

            # 2. Provider connections
            for row in vault_data.get("provider_connections", []):
                cols = [k for k in row.keys() if k != "id"]
                if cols:
                    placeholders = ", ".join(["?"] * len(cols))
                    col_names = ", ".join(cols)
                    vals = [row[c] for c in cols]
                    try:
                        conn.execute(
                            f"INSERT INTO provider_connections ({col_names}) VALUES ({placeholders})",
                            vals,
                        )
                        stats["provider_connections"] += 1
                    except Exception:
                        pass

            # 3. Audio provider connections
            for row in vault_data.get("audio_provider_connections", []):
                cols = [k for k in row.keys() if k != "id"]
                if cols:
                    placeholders = ", ".join(["?"] * len(cols))
                    col_names = ", ".join(cols)
                    vals = [row[c] for c in cols]
                    try:
                        conn.execute(
                            f"INSERT INTO audio_provider_connections ({col_names}) VALUES ({placeholders})",
                            vals,
                        )
                        stats["audio_provider_connections"] += 1
                    except Exception:
                        pass

            # 4. Video Flow provider connections
            for row in vault_data.get("video_flow_provider_connections", []):
                cols = [k for k in row.keys() if k != "id"]
                if cols:
                    placeholders = ", ".join(["?"] * len(cols))
                    col_names = ", ".join(cols)
                    vals = [row[c] for c in cols]
                    try:
                        conn.execute(
                            f"INSERT INTO video_flow_provider_connections ({col_names}) VALUES ({placeholders})",
                            vals,
                        )
                        stats["video_flow_provider_connections"] += 1
                    except Exception:
                        pass

            # 5. API keys
            for k in vault_data.get("api_keys", []):
                if k.get("api_key"):
                    try:
                        conn.execute(
                            "INSERT OR IGNORE INTO api_keys (api_key, provider, created_at) VALUES (?, ?, ?)",
                            (k["api_key"], k.get("provider", "gemini"), k.get("created_at") or datetime.datetime.now(datetime.timezone.utc).isoformat()),
                        )
                        stats["api_keys"] += 1
                    except Exception:
                        pass

            # 6. Dictionary
            for d in vault_data.get("dictionary", []):
                w = d.get("word")
                if w:
                    try:
                        conn.execute(
                            "INSERT OR IGNORE INTO dictionary (word, category, created_at) VALUES (?, ?, ?)",
                            (w, d.get("category", "Personal"), d.get("created_at") or datetime.datetime.now(datetime.timezone.utc).isoformat()),
                        )
                        stats["dictionary"] += 1
                    except Exception:
                        pass

            # 7. Corrections
            for c in vault_data.get("dictionary_corrections", []):
                wrong = c.get("wrong_text")
                correct = c.get("correct_text")
                if wrong and correct:
                    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    try:
                        conn.execute(
                            "INSERT OR REPLACE INTO dictionary_corrections (wrong_text, correct_text, created_at, updated_at) VALUES (?, ?, ?, ?)",
                            (wrong, correct, c.get("created_at") or now, c.get("updated_at") or now),
                        )
                        stats["dictionary_corrections"] += 1
                    except Exception:
                        pass

            # 8. Snippets
            for snip in vault_data.get("snippets", []):
                trig = snip.get("trigger")
                exp = snip.get("expansion")
                if trig and exp:
                    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    try:
                        conn.execute(
                            "INSERT OR REPLACE INTO snippets (trigger, expansion, created_at, updated_at) VALUES (?, ?, ?, ?)",
                            (trig, exp, snip.get("created_at") or now, snip.get("updated_at") or now),
                        )
                        stats["snippets"] += 1
                    except Exception:
                        pass

            conn.commit()

        self._touch_lexicon()
        return stats



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
                # Marks the app-wide singleton so API-layer sync hooks
                # (repoint_if_needed / consolidation) only ever touch the real
                # engine — tests construct their own StorageEngine instances
                # against temp databases and must never be re-pointed.
                _storage_singleton.is_global_singleton = True
            return _storage_singleton
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

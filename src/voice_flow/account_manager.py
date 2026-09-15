"""Account Authentication and Multi-Account Management for AI Productivity Flow.

Manages user registration, secure PBKDF2 authentication, multi-profile database
isolation, dynamic account switching, and cross-device encrypted vault sync (.flowvault).
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import logging
import os
import secrets
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from voice_flow.paths import data_dir

log = logging.getLogger(__name__)

PBKDF2_ITERATIONS = 600_000
AVATAR_COLORS = [
    "#ff6a00",  # Flow orange
    "#3b82f6",  # Blue
    "#10b981",  # Emerald
    "#8b5cf6",  # Violet
    "#ec4899",  # Pink
    "#f59e0b",  # Amber
    "#06b6d4",  # Cyan
]


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Hash password using PBKDF2-HMAC-SHA256 with 600,000 iterations.
    
    Returns (hash_hex, salt_hex).
    """
    if salt is None:
        salt = secrets.token_bytes(32)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=32,
    )
    return dk.hex(), salt.hex()


def verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    """Verify password against stored hash using constant-time comparison."""
    try:
        salt = bytes.fromhex(password_salt)
        expected_hash = bytes.fromhex(password_hash)
        computed_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            PBKDF2_ITERATIONS,
            dklen=32,
        )
        return secrets.compare_digest(expected_hash, computed_hash)
    except Exception:
        log.exception("Password verification error")
        return False


class AccountManager:
    """Central manager for accounts, sessions, and profile vaults."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or data_dir()
        self.accounts_db_path = self.base_dir / "accounts.db"
        self.accounts_dir = self.base_dir / "accounts"
        self._lock = threading.RLock()
        
        self.accounts_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._ensure_initial_account_migration()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.accounts_db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout = 15000")
            conn.execute("PRAGMA journal_mode = WAL")
        except Exception:
            pass
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    username TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_login_at TEXT NOT NULL,
                    avatar_color TEXT DEFAULT '#ff6a00',
                    is_active INTEGER DEFAULT 0,
                    google_id TEXT,
                    avatar_url TEXT
                )
            """)
            try:
                conn.execute("ALTER TABLE accounts ADD COLUMN google_id TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE accounts ADD COLUMN avatar_url TEXT")
            except Exception:
                pass
            conn.execute("""
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS account_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.commit()

    def _ensure_initial_account_migration(self) -> None:
        """Adopts existing voice_flow.db seamlessly as the default primary account.
        
        Guarantees zero data loss for existing users.
        """
        with self._lock, self._get_conn() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM accounts")
            count = cursor.fetchone()[0]
            if count > 0:
                return

            # No accounts exist yet. Check if legacy voice_flow.db exists
            legacy_db = self.base_dir / "voice_flow.db"
            primary_id = "acc_primary"
            primary_dir = self.accounts_dir / primary_id
            primary_dir.mkdir(parents=True, exist_ok=True)
            target_db = primary_dir / "voice_flow.db"

            if legacy_db.exists():
                try:
                    # Flush any uncheckpointed WAL transactions to main database
                    try:
                        with sqlite3.connect(str(legacy_db)) as l_conn:
                            l_conn.execute("PRAGMA wal_checkpoint(FULL)")
                    except Exception:
                        pass
                    # Safely sync legacy db so the user keeps all API keys, dictionary, styles
                    if not target_db.exists() or legacy_db.stat().st_mtime > target_db.stat().st_mtime:
                        shutil.copy2(str(legacy_db), str(target_db))
                        legacy_wal = self.base_dir / "voice_flow.db-wal"
                        if legacy_wal.exists():
                            try:
                                shutil.copy2(str(legacy_wal), str(primary_dir / "voice_flow.db-wal"))
                            except Exception:
                                pass
                        legacy_shm = self.base_dir / "voice_flow.db-shm"
                        if legacy_shm.exists():
                            try:
                                shutil.copy2(str(legacy_shm), str(primary_dir / "voice_flow.db-shm"))
                            except Exception:
                                pass
                        log.info("Successfully synced latest voice_flow.db to primary account vault %s", target_db)
                except Exception:
                    log.exception("Could not copy legacy voice_flow.db to primary account; creating empty")

            now = _now_iso()
            # Default primary account with local password placeholder
            p_hash, p_salt = hash_password("voiceflow")
            color = AVATAR_COLORS[0]
            conn.execute(
                """
                INSERT INTO accounts (id, email, username, password_hash, password_salt, created_at, last_login_at, avatar_color, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (primary_id, "primary@flow.local", "Primary Account", p_hash, p_salt, now, now, color),
            )
            conn.execute(
                "INSERT OR REPLACE INTO account_state (key, value) VALUES ('active_account_id', ?)",
                (primary_id,),
            )
            conn.commit()

    def get_account_db_path(self, account_id: str) -> Path:
        """Get the database file path for a specific account."""
        account_dir = self.accounts_dir / account_id
        account_dir.mkdir(parents=True, exist_ok=True)
        return account_dir / "voice_flow.db"

    def get_active_account_id(self) -> str:
        with self._lock, self._get_conn() as conn:
            row = conn.execute("SELECT value FROM account_state WHERE key = 'active_account_id'").fetchone()
            if row is not None:
                return str(row["value"] or "")
            # Fallback to active account flag
            active = conn.execute("SELECT id FROM accounts WHERE is_active = 1 LIMIT 1").fetchone()
            if active and active["id"]:
                return active["id"]
            first = conn.execute("SELECT id FROM accounts LIMIT 1").fetchone()
            return first["id"] if first else ""

    def get_active_account(self) -> dict[str, Any] | None:
        """Return safe active account metadata."""
        active_id = self.get_active_account_id()
        return self.get_account_by_id(active_id)

    def get_account_by_id(self, account_id: str) -> dict[str, Any] | None:
        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT id, email, username, created_at, last_login_at, avatar_color, is_active, google_id, avatar_url FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "email": row["email"],
                "username": row["username"],
                "created_at": row["created_at"],
                "last_login_at": row["last_login_at"],
                "avatar_color": row["avatar_color"] or "#ff6a00",
                "avatar_url": row["avatar_url"] if "avatar_url" in row.keys() and row["avatar_url"] else "",
                "google_id": row["google_id"] if "google_id" in row.keys() and row["google_id"] else "",
                "is_active": bool(row["is_active"]),
            }

    def list_accounts(self) -> list[dict[str, Any]]:
        """Return all local accounts with active status."""
        active_id = self.get_active_account_id()
        with self._lock, self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, email, username, created_at, last_login_at, avatar_color, google_id, avatar_url FROM accounts ORDER BY created_at ASC"
            ).fetchall()
            accounts = [
                {
                    "id": row["id"],
                    "email": row["email"],
                    "username": row["username"],
                    "created_at": row["created_at"],
                    "last_login_at": row["last_login_at"],
                    "avatar_color": row["avatar_color"] or "#ff6a00",
                    "avatar_url": row["avatar_url"] if "avatar_url" in row.keys() and row["avatar_url"] else "",
                    "google_id": row["google_id"] if "google_id" in row.keys() and row["google_id"] else "",
                    "is_active": row["id"] == active_id,
                }
                for row in rows
            ]
            if len(accounts) > 1:
                accounts = [
                    a for a in accounts
                    if not (a["id"] == "acc_primary" and a["email"] == "primary@flow.local" and not a.get("google_id"))
                ]
            return accounts

    def register_account(
        self,
        email: str,
        username: str,
        password: str,
        avatar_color: str | None = None,
    ) -> dict[str, Any]:
        """Register a brand new account with its own isolated database vault."""
        clean_email = email.strip().lower()
        clean_username = username.strip()
        if not clean_email or "@" not in clean_email:
            raise ValueError("A valid email address is required.")
        if not clean_username:
            raise ValueError("Username cannot be empty.")
        if not password or len(password) < 4:
            raise ValueError("Password must be at least 4 characters long.")

        with self._lock, self._get_conn() as conn:
            existing = conn.execute("SELECT id FROM accounts WHERE email = ?", (clean_email,)).fetchone()
            if existing:
                raise ValueError("An account with this email already exists.")

            account_id = f"acc_{uuid.uuid4().hex[:12]}"
            p_hash, p_salt = hash_password(password)
            now = _now_iso()
            color = avatar_color or secrets.choice(AVATAR_COLORS)

            conn.execute(
                """
                INSERT INTO accounts (id, email, username, password_hash, password_salt, created_at, last_login_at, avatar_color, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (account_id, clean_email, clean_username, p_hash, p_salt, now, now, color),
            )
            conn.commit()

        # Initialize isolated account database
        db_path = self.get_account_db_path(account_id)
        from voice_flow.storage import StorageEngine
        # Creating StorageEngine on new db_path initializes all tables
        StorageEngine(str(db_path))

        # Create session
        token = self._create_session(account_id)
        return {
            "success": True,
            "account": self.get_account_by_id(account_id),
            "session_token": token,
        }

    def authenticate_account(self, email_or_username: str, password: str) -> dict[str, Any]:
        """Verify user credentials and return new session token."""
        query_val = email_or_username.strip().lower()
        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT id, email, username, password_hash, password_salt FROM accounts WHERE LOWER(email) = ? OR LOWER(username) = ?",
                (query_val, query_val),
            ).fetchone()
            if not row:
                raise ValueError("Invalid email/username or password.")

            if not verify_password(password, row["password_hash"], row["password_salt"]):
                raise ValueError("Invalid email/username or password.")

            account_id = row["id"]
            now = _now_iso()
            conn.execute("UPDATE accounts SET last_login_at = ? WHERE id = ?", (now, account_id))
            conn.commit()

        token = self._create_session(account_id)
        # Automatically switch active account on successful login
        self.switch_account(account_id)
        return {
            "success": True,
            "account": self.get_account_by_id(account_id),
            "session_token": token,
        }

    def authenticate_or_register_google(
        self,
        email: str,
        username: str = "",
        google_id: str = "",
        avatar_url: str = "",
    ) -> dict[str, Any]:
        """Authenticate or automatically register an account via Google Sign-In."""
        clean_email = email.strip().lower()
        if not clean_email:
            raise ValueError("Email cannot be empty.")
        clean_username = username.strip() or clean_email.split("@")[0]
        now = _now_iso()

        with self._lock, self._get_conn() as conn:
            # Check if this Google email is already registered
            row = conn.execute(
                "SELECT id FROM accounts WHERE LOWER(email) = ?",
                (clean_email,),
            ).fetchone()
            if row:
                account_id = row["id"]
                conn.execute(
                    "UPDATE accounts SET last_login_at = ?, google_id = COALESCE(NULLIF(?, ''), google_id), avatar_url = COALESCE(NULLIF(?, ''), avatar_url) WHERE id = ?",
                    (now, google_id, avatar_url, account_id),
                )
                conn.commit()
            else:
                # Check if acc_primary is the unlinked local placeholder
                primary = conn.execute("SELECT id, email, google_id FROM accounts WHERE id = 'acc_primary'").fetchone()
                if primary and primary["email"] == "primary@flow.local" and not primary["google_id"]:
                    # Seamlessly upgrade acc_primary so all local keys and settings are retained
                    account_id = "acc_primary"
                    conn.execute(
                        """
                        UPDATE accounts
                        SET email = ?, username = ?, google_id = ?, avatar_url = ?, last_login_at = ?
                        WHERE id = 'acc_primary'
                        """,
                        (clean_email, clean_username, google_id, avatar_url, now),
                    )
                    conn.commit()
                else:
                    account_id = f"acc_{uuid.uuid4().hex[:12]}"
                    p_hash, p_salt = hash_password(secrets.token_urlsafe(32))
                    conn.execute(
                        """
                        INSERT INTO accounts (id, email, username, password_hash, password_salt, created_at, last_login_at, avatar_color, is_active, google_id, avatar_url)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                        """,
                        (account_id, clean_email, clean_username, p_hash, p_salt, now, now, "#ff6a00", google_id, avatar_url),
                    )
                    conn.commit()
                    # Initialize database for this new profile
                    db_path = self.get_account_db_path(account_id)
                    from voice_flow.storage import StorageEngine
                    StorageEngine(str(db_path))

        # Switch to this account
        self.switch_account(account_id)
        token = self._create_session(account_id)
        return {
            "success": True,
            "account": self.get_account_by_id(account_id),
            "session_token": token,
        }

    def _create_session(self, account_id: str) -> str:
        token = secrets.token_hex(32)
        now = _now_iso()
        # 30 days session expiry
        expires_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)).isoformat()
        with self._lock, self._get_conn() as conn:
            conn.execute(
                "INSERT INTO auth_sessions (token, account_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, account_id, now, expires_at),
            )
            conn.commit()
        return token

    def switch_account(self, account_id: str) -> dict[str, Any]:
        """Switch active account and dynamically repoint all application storage engines."""
        with self._lock, self._get_conn() as conn:
            row = conn.execute("SELECT id FROM accounts WHERE id = ?", (account_id,)).fetchone()
            if not row:
                raise ValueError(f"Account {account_id} does not exist.")

            conn.execute("UPDATE accounts SET is_active = (id = ?)", (account_id,))
            conn.execute("INSERT OR REPLACE INTO account_state (key, value) VALUES ('active_account_id', ?)", (account_id,))
            conn.commit()

        target_db_path = str(self.get_account_db_path(account_id))
        
        # Dynamically repoint StorageEngine singleton
        try:
            from voice_flow.storage import storage
            storage.switch_account(target_db_path)
        except Exception:
            log.exception("Failed to switch StorageEngine database path to %s", target_db_path)

        # Dynamically repoint VideoFlowProviderService
        try:
            from voice_flow.video_flow_providers import video_flow_provider_service
            if hasattr(video_flow_provider_service, "switch_account"):
                video_flow_provider_service.switch_account(target_db_path)
        except Exception:
            log.exception("Failed to switch VideoFlowProviderService to %s", target_db_path)

        # Dynamically repoint VideoFlowService store
        try:
            from voice_flow.video_flow_service import video_flow_service
            if hasattr(video_flow_service, "store") and hasattr(video_flow_service.store, "switch_account"):
                video_flow_service.store.switch_account(target_db_path)
        except Exception:
            pass

        log.info("Successfully switched active account to %s (%s)", account_id, target_db_path)
        return {
            "success": True,
            "active_account": self.get_account_by_id(account_id),
            "accounts": self.list_accounts(),
        }

    def update_profile(
        self,
        account_id: str,
        username: str | None = None,
        avatar_color: str | None = None,
        new_password: str | None = None,
        current_password: str | None = None,
    ) -> dict[str, Any]:
        """Update user profile info or password."""
        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT password_hash, password_salt FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
            if not row:
                raise ValueError("Account not found.")

            if new_password:
                if not current_password:
                    raise ValueError("Current password is required to change password.")
                if not verify_password(current_password, row["password_hash"], row["password_salt"]):
                    raise ValueError("Current password is incorrect.")
                if len(new_password) < 4:
                    raise ValueError("New password must be at least 4 characters.")
                p_hash, p_salt = hash_password(new_password)
                conn.execute(
                    "UPDATE accounts SET password_hash = ?, password_salt = ? WHERE id = ?",
                    (p_hash, p_salt, account_id),
                )

            if username and username.strip():
                conn.execute("UPDATE accounts SET username = ? WHERE id = ?", (username.strip(), account_id))

            if avatar_color and avatar_color.strip():
                conn.execute("UPDATE accounts SET avatar_color = ? WHERE id = ?", (avatar_color.strip(), account_id))

            conn.commit()

        return {"success": True, "account": self.get_account_by_id(account_id)}

    def logout_account(self, session_token: str | None = None) -> bool:
        """Invalidate session token and deactivate active account on logout."""
        with self._lock, self._get_conn() as conn:
            if session_token:
                conn.execute("DELETE FROM auth_sessions WHERE token = ?", (session_token,))
            conn.execute("UPDATE accounts SET is_active = 0")
            conn.execute("INSERT OR REPLACE INTO account_state (key, value) VALUES ('active_account_id', '')")
            conn.commit()
        return True

    # -------------------------------------------------------------------------
    # Cross-Device Encrypted Vault Sync (.flowvault)
    # -------------------------------------------------------------------------

    def export_vault(self, account_id: str, passphrase: str) -> dict[str, Any]:
        """Extracts all API keys, dictionary words, styles, and settings from the
        account and encrypts them using AES-256-GCM + PBKDF2.
        
        Ready for future Mobile (iOS/Android) and Mac clients.
        """
        if not passphrase or len(passphrase) < 4:
            raise ValueError("Passphrase must be at least 4 characters long.")

        account = self.get_account_by_id(account_id)
        if not account:
            raise ValueError("Account not found.")

        db_path = str(self.get_account_db_path(account_id))
        from voice_flow.storage import StorageEngine
        account_storage = StorageEngine(db_path)
        vault_payload = account_storage.export_vault_data()

        meta = {
            "account_id": account["id"],
            "username": account["username"],
            "email": account["email"],
            "exported_at": _now_iso(),
            "format": "flowvault",
            "version": 1,
        }
        full_package = {
            "metadata": meta,
            "data": vault_payload,
        }

        # Encrypt with AES-256-GCM
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)
        derived_key = hashlib.pbkdf2_hmac(
            "sha256",
            passphrase.encode("utf-8"),
            salt,
            PBKDF2_ITERATIONS,
            dklen=32,
        )
        aesgcm = AESGCM(derived_key)
        plaintext_bytes = json.dumps(full_package).encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)

        return {
            "flowvault_version": 1,
            "salt_hex": salt.hex(),
            "nonce_hex": nonce.hex(),
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
            "account_username": account["username"],
            "account_email": account["email"],
            "exported_at": _now_iso(),
        }

    def import_vault(
        self,
        account_id: str,
        passphrase: str,
        vault_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Decrypts AES-256-GCM .flowvault payload and restores API keys,
        dictionary terms, style rules, and settings into the target account.
        """
        if not passphrase:
            raise ValueError("Passphrase cannot be empty.")
        if "salt_hex" not in vault_data or "nonce_hex" not in vault_data or "ciphertext_b64" not in vault_data:
            raise ValueError("Invalid .flowvault format: missing cryptographic parameters.")

        try:
            salt = bytes.fromhex(vault_data["salt_hex"])
            nonce = bytes.fromhex(vault_data["nonce_hex"])
            ciphertext = base64.b64decode(vault_data["ciphertext_b64"])
        except Exception:
            raise ValueError("Failed to parse .flowvault binary data.")

        # Derive key
        derived_key = hashlib.pbkdf2_hmac(
            "sha256",
            passphrase.encode("utf-8"),
            salt,
            PBKDF2_ITERATIONS,
            dklen=32,
        )
        aesgcm = AESGCM(derived_key)

        try:
            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        except Exception:
            raise ValueError("Decryption failed. Please check your vault passphrase.")

        try:
            package = json.loads(plaintext_bytes.decode("utf-8"))
        except Exception:
            raise ValueError("Corrupted vault JSON payload.")

        imported_data = package.get("data", {})
        db_path = str(self.get_account_db_path(account_id))
        from voice_flow.storage import StorageEngine
        account_storage = StorageEngine(db_path)
        stats = account_storage.import_vault_data(imported_data)

        log.info("Successfully imported vault into account %s: %s", account_id, stats)
        return {
            "success": True,
            "stats": stats,
            "metadata": package.get("metadata", {}),
        }


# Singleton AccountManager
_account_manager: AccountManager | None = None
_account_manager_lock = threading.Lock()


def get_account_manager() -> AccountManager:
    global _account_manager
    with _account_manager_lock:
        if _account_manager is None:
            _account_manager = AccountManager()
        return _account_manager

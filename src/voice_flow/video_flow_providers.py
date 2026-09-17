"""Video Flow-only provider, connection, model, and selection policy.

Nothing in this module reads or writes the Voice Flow or Audio Flow provider
tables.  Secrets are returned only to the internal model gateway; all UI-facing
responses are masked.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import sys
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from voice_flow.storage import DB_PATH
from voice_flow.video_flow_oauth import (
    COOLDOWN_DEFAULT_SECONDS,
    OAuthError,
    decrypt_token,
    encrypt_token,
    exchange_copilot_token,
    import_cli_session,
    import_cursor_session,
    jwt_expiry,
    looks_encrypted,
    oauth_config,
    poll_device_flow,
    refresh_and_store,
    start_device_flow,
    wait_for_cli_session,
)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


PROVIDERS: tuple[dict[str, Any], ...] = (
    {"id": "claude_code", "name": "Claude Code", "category": "oauth", "prefix": "claude-code", "icon": "✺", "auth": "oauth", "description": "Use a signed-in Claude Code subscription.", "login_command": ["claude", "auth", "login"], "status_command": ["claude", "auth", "status"], "get_key_url": "https://console.anthropic.com/settings/keys"},
    {"id": "antigravity", "name": "Antigravity", "category": "oauth", "prefix": "antigravity", "icon": "A", "auth": "oauth", "description": "Use the Google account signed into Antigravity.", "login_command": ["antigravity"], "status_command": [], "get_key_url": "https://aistudio.google.com/apikey"},
    {"id": "openai_codex", "name": "ChatGPT", "category": "oauth", "prefix": "codex", "icon": "◎", "auth": "oauth", "description": "Use your ChatGPT Plus, Team, or Pro subscription.", "login_command": ["codex", "login"], "status_command": ["codex", "login", "status"], "get_key_url": "https://platform.openai.com/api-keys"},
    {"id": "vertex_ai", "name": "Vertex AI", "category": "api_key", "prefix": "vx", "icon": "V", "auth": "api_key", "description": "Google Cloud Vertex models and custom model IDs.", "get_key_url": "https://console.cloud.google.com/vertex-ai"},
    {"id": "gemini", "name": "Google Gemini", "category": "api_key", "prefix": "gemini", "icon": "✦", "auth": "api_key", "description": "Gemini API free-tier and paid keys.", "get_key_url": "https://aistudio.google.com/apikey"},
    {"id": "openrouter", "name": "OpenRouter", "category": "api_key", "prefix": "openrouter", "icon": "↔", "auth": "api_key", "description": "A broad catalog including free-routed models.", "get_key_url": "https://openrouter.ai/settings/keys"},
    {"id": "nvidia_nim", "name": "NVIDIA NIM", "category": "api_key", "prefix": "nim", "icon": "N", "auth": "api_key", "description": "NVIDIA-hosted open model endpoints.", "get_key_url": "https://build.nvidia.com/settings/api-keys"},
    {"id": "opencode_zen", "name": "OpenCode Zen", "category": "api_key", "prefix": "zen", "icon": "Z", "auth": "api_key", "description": "OpenCode Zen model access.", "get_key_url": "https://opencode.ai/auth"},
    {"id": "anthropic", "name": "Anthropic API", "category": "api_key", "prefix": "anthropic", "icon": "A", "auth": "api_key", "description": "Claude models with an Anthropic API key.", "get_key_url": "https://console.anthropic.com/settings/keys"},
    {"id": "openai", "name": "OpenAI API", "category": "api_key", "prefix": "openai", "icon": "◎", "auth": "api_key", "description": "OpenAI models with a project API key.", "get_key_url": "https://platform.openai.com/api-keys"},
    {"id": "groq", "name": "Groq", "category": "api_key", "prefix": "groq", "icon": "G", "auth": "api_key", "description": "Fast hosted open models.", "get_key_url": "https://console.groq.com/keys"},
    {"id": "together", "name": "Together AI", "category": "api_key", "prefix": "together", "icon": "T", "auth": "api_key", "description": "Hosted open and specialist models.", "get_key_url": "https://api.together.ai/settings/api-keys"},
    {"id": "cloudflare", "name": "Cloudflare Workers AI", "category": "api_key", "prefix": "cloudflare", "icon": "☁", "auth": "api_key", "description": "Workers AI models using account-scoped credentials.", "get_key_url": "https://dash.cloudflare.com/profile/api-tokens"},
    {"id": "ollama", "name": "Ollama", "category": "local", "prefix": "ollama", "icon": "◉", "auth": "local", "description": "Models running locally through Ollama.", "default_base_url": "http://127.0.0.1:11434"},
    {"id": "lm_studio", "name": "LM Studio", "category": "local", "prefix": "lmstudio", "icon": "LM", "auth": "local", "description": "LM Studio's local OpenAI-compatible server.", "default_base_url": "http://127.0.0.1:1234/v1"},
    {"id": "llama_cpp", "name": "llama.cpp", "category": "local", "prefix": "llamacpp", "icon": "L", "auth": "local", "description": "A local llama.cpp OpenAI-compatible server.", "default_base_url": "http://127.0.0.1:8080/v1"},
)

LEGACY_OAUTH_PROVIDERS: tuple[dict[str, Any], ...] = (
    {"id": "cursor", "name": "Cursor", "category": "oauth", "prefix": "cursor", "icon": "C", "auth": "oauth", "description": "Use the Cursor Pro subscription signed into Cursor.", "login_command": [], "status_command": [], "get_key_url": "https://cursor.com/settings"},
    {"id": "kiro", "name": "AWS Kiro", "category": "oauth", "prefix": "kiro", "icon": "K", "auth": "oauth", "description": "Use the AWS Kiro subscription signed into the Kiro CLI.", "login_command": ["kiro", "auth", "login"], "status_command": ["kiro", "auth", "status"], "get_key_url": "https://console.aws.amazon.com/kiro"},
    {"id": "copilot", "name": "GitHub Copilot", "category": "oauth", "prefix": "copilot", "icon": "⌥", "auth": "oauth", "description": "Use a GitHub Copilot subscription via device sign-in.", "login_command": [], "status_command": [], "get_key_url": "https://github.com/settings/copilot"},
)

ALL_PROVIDERS: tuple[dict[str, Any], ...] = PROVIDERS + LEGACY_OAUTH_PROVIDERS
PROVIDER_BY_ID = {item["id"]: item for item in ALL_PROVIDERS}
PROVIDER_BY_PREFIX = {item["prefix"]: item for item in ALL_PROVIDERS}
PROVIDER_ALIASES = {
    "codex": "openai_codex",
    "nim": "nvidia_nim",
    "vx": "vertex_ai",
    "zen": "opencode_zen",
    "claude-code": "claude_code",
    "lmstudio": "lm_studio",
    "llamacpp": "llama_cpp",
}
DEFAULT_CATALOG_VERSION = "2026-09-04.1"


def antigravity_executable_candidates() -> list[Path]:
    """Return deterministic Windows install locations for Antigravity.

    The desktop installer uses a per-user location that is not normally added to
    PATH. Keep discovery explicit and side effect free so the OAuth button can
    launch the installed app without asking the user to download it again.
    Installed application locations are checked before PATH lookups so a
    leftover "Antigravity Setup" installer on PATH can never shadow the app.
    """
    candidates: list[Path] = []
    for value in (
        os.environ.get("ANTIGRAVITY_EXE"),
        os.environ.get("ANTIGRAVITY_EXECUTABLE"),
    ):
        if value:
            candidates.append(Path(value))

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Programs" / "Antigravity" / "Antigravity.exe")
        candidates.append(Path(local_app_data) / "Programs" / "antigravity" / "Antigravity.exe")
        candidates.append(Path(local_app_data) / "Antigravity" / "Antigravity.exe")
    candidates.append(Path.home() / "AppData" / "Local" / "Programs" / "Antigravity" / "Antigravity.exe")

    for variable in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "Antigravity" / "Antigravity.exe")

    path_hit = shutil.which("antigravity")
    if path_hit:
        candidates.append(Path(path_hit))

    # Keep the historical custom install path as a final compatibility probe.
    candidates.append(Path("D:/Antigravity.exe"))

    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(os.fspath(candidate)))
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def _file_description(path: Path) -> str:
    """Return the FileDescription of a Windows PE file, or '' when unknown."""
    try:
        import ctypes
        from ctypes import wintypes

        size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
        if size <= 0:
            return ""
        data = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, data):
            return ""
        out_ptr = wintypes.LPVOID()
        out_len = wintypes.UINT()
        block = r"\StringFileInfo\040904B0\FileDescription"
        if not ctypes.windll.version.VerQueryValueW(data, block, ctypes.byref(out_ptr), ctypes.byref(out_len)):
            return ""
        return ctypes.wstring_at(out_ptr, out_len.value // 2).rstrip("\x00")
    except Exception:
        return ""


def find_antigravity_executable() -> Path | None:
    for candidate in antigravity_executable_candidates():
        try:
            if not candidate.is_file():
                continue
            description = _file_description(candidate)
            if description and any(marker in description.lower() for marker in ("setup", "installer")):
                continue
            return candidate
        except OSError:
            continue
    return None


ANTIGRAVITY_ACCOUNT_URL = "https://antigravity.google/"


def antigravity_open_account_selection() -> None:
    """Open the Google account-selection page for Antigravity in the browser.

    The web platform redirects unauthenticated visitors to the Google account
    chooser, so the user can pick the account already signed into the installed
    Antigravity desktop app. Best-effort: never raise into the OAuth flow.
    """
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("VOICE_FLOW_NO_BROWSER_POPUP"):
        return
    try:
        import webbrowser

        opener = webbrowser.get("windows-default") if os.name == "nt" else webbrowser
        if not opener.open(ANTIGRAVITY_ACCOUNT_URL):
            os.startfile(ANTIGRAVITY_ACCOUNT_URL)
    except Exception:
        try:
            os.startfile(ANTIGRAVITY_ACCOUNT_URL)
        except Exception:
            pass



def antigravity_cli_candidates() -> list[Path]:
    candidates: list[Path] = []
    for value in (
        os.environ.get("ANTIGRAVITY_CLI_EXE"),
        os.environ.get("AGY_EXE"),
        shutil.which("agy"),
    ):
        if value:
            candidates.append(Path(value))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "agy" / "bin" / "agy.exe")
    candidates.append(Path.home() / "AppData" / "Local" / "agy" / "bin" / "agy.exe")
    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(os.fspath(candidate)))
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def find_antigravity_cli() -> Path | None:
    for candidate in antigravity_cli_candidates():
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def antigravity_cli_project_id() -> str:
    return str(os.environ.get("ANTIGRAVITY_PROJECT_ID") or "default-cli-project").strip()

def antigravity_state_path() -> Path:
    return Path.home() / ".gemini" / "antigravity" / "antigravity_state.pbtxt"


def antigravity_agentapi_path() -> Path | None:
    """Find the helper exposed to Antigravity-managed sidecars."""
    for value in (os.environ.get("ANTIGRAVITY_AGENTAPI_EXE"), shutil.which("agentapi")):
        if value:
            path = Path(value)
            if path.is_file() or shutil.which(value):
                return path
    local = Path.home() / ".gemini" / "antigravity" / "bin" / "agentapi.bat"
    return local if local.is_file() else None


def antigravity_bridge_status() -> dict[str, Any]:
    """Describe safe local bridge options without reading OAuth tokens."""
    cli = find_antigravity_cli()
    state_available = antigravity_state_path().is_file()
    cli_ready = bool(cli and state_available)
    address = str(os.environ.get("ANTIGRAVITY_LS_ADDRESS") or "").strip()
    csrf_present = bool(str(os.environ.get("ANTIGRAVITY_CSRF_TOKEN") or "").strip())
    direct_ready = bool(address and csrf_present)
    source = "cli" if cli_ready else ("environment" if direct_ready else "none")
    return {
        "ready": bool(cli_ready or direct_ready),
        "address_configured": bool(address),
        "csrf_configured": csrf_present if source == "environment" else False,
        "cli_available": bool(cli),
        "cli_path": str(cli) if cli else "",
        "state_available": state_available,
        "source": source,
        "project_id": antigravity_cli_project_id(),
    }

DEFAULT_MODELS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("claude_code", "opus-4-7", "Claude Opus 4.7", ("vision", "reasoning", "code")),
    ("claude_code", "opus-4-6", "Claude Opus 4.6", ("vision", "reasoning", "code")),
    ("claude_code", "sonnet-4-6", "Claude Sonnet 4.6", ("vision", "reasoning", "code")),
    ("claude_code", "sonnet-5", "Claude Sonnet 5 (Latest)", ("vision", "reasoning", "code")),
    ("claude_code", "opus-5", "Claude Opus 5 (Latest)", ("vision", "reasoning", "code")),
    ("claude_code", "fable-5", "Claude Fable 5 (Latest)", ("vision", "reasoning", "code")),
    ("antigravity", "gpt-oss-120b", "GPT-OSS 120B (Medium)", ("reasoning", "code")),
    ("antigravity", "gemini-3.5-flash", "Gemini 3.5 Flash", ("vision", "reasoning")),
    ("antigravity", "gemini-3.1-pro", "Gemini 3.1 Pro", ("vision", "reasoning")),
    ("antigravity", "gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite", ("vision", "reasoning")),
    ("antigravity", "claude-sonnet-4-6", "Claude Sonnet 4.6", ("vision", "reasoning")),
    ("antigravity", "claude-opus-4-6", "Claude Opus 4.6", ("vision", "reasoning")),
    ("openai_codex", "gpt-5.6-terra", "GPT-5.6 Terra", ("vision", "reasoning", "code")),
    ("openai_codex", "gpt-5.6-luna", "GPT-5.6 Luna", ("vision", "reasoning", "code")),
    ("openai_codex", "gpt-5.5", "GPT-5.5", ("vision", "reasoning", "code")),
    ("openai_codex", "gpt-5.4-mini", "GPT-5.4 Mini", ("vision", "reasoning", "code")),
    ("openai_codex", "gpt-5.6-sol", "GPT-5.6 Sol", ("vision", "reasoning", "code")),
    ("openai_codex", "gpt-5.3-codex-spark", "GPT-5.3 Codex Spark", ("reasoning", "code")),
    ("vertex_ai", "gemini-3.5-flash", "Gemini 3.5 Flash", ("vision", "reasoning")),
    ("vertex_ai", "gemini-3.1-pro", "Gemini 3.1 Pro", ("vision", "reasoning")),
    ("vertex_ai", "gemini-3-flash", "Gemini 3 Flash", ("vision", "reasoning")),
    ("vertex_ai", "gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite", ("vision", "reasoning")),
    ("gemini", "gemini-3.5-flash", "Gemini 3.5 Flash", ("vision", "reasoning")),
    ("openrouter", "openrouter/free", "OpenRouter Free Router", ("reasoning",)),
    ("openrouter", "poolside/laguna-s-2.1:free", "Laguna S 2.1 Free", ("reasoning", "code")),
    ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", "Nemotron 3 Ultra Free", ("reasoning", "code")),
    ("openrouter", "google/gemma-4-26b-a4b-it:free", "Gemma 4 26B Free", ("vision", "reasoning")),
    ("nvidia_nim", "nvidia/nemotron-3-ultra-550b-a55b", "Nemotron 3 Ultra 550B", ("reasoning", "code")),
    ("nvidia_nim", "nvidia/nemotron-3-super-120b-a12b", "Nemotron 3 Super 120B", ("reasoning", "code")),
    ("nvidia_nim", "nvidia/nemotron-3-nano-30b-a3b", "Nemotron 3 Nano 30B", ("reasoning", "code")),
    ("nvidia_nim", "moonshotai/kimi-k2.6", "Kimi K2.6", ("vision", "reasoning", "code")),
    ("opencode_zen", "deepseek-v4-flash-free", "DeepSeek V4 Flash Free", ("reasoning", "code")),
    ("opencode_zen", "nemotron-3-ultra-free", "Nemotron 3 Ultra Free", ("reasoning", "code")),
    ("opencode_zen", "laguna-s-2.1-free", "Laguna S 2.1 Free", ("reasoning", "code")),
    ("opencode_zen", "north-mini-code-free", "North Mini Code Free", ("reasoning", "code")),
    ("anthropic", "claude-fable-5", "Claude Fable 5", ("vision", "reasoning")),
    ("anthropic", "claude-opus-5", "Claude Opus 5", ("vision", "reasoning")),
    ("anthropic", "claude-sonnet-5", "Claude Sonnet 5", ("vision", "reasoning")),
    ("anthropic", "claude-haiku-4-5", "Claude Haiku 4.5", ("vision", "reasoning")),
    ("openai", "gpt-5.6-sol", "GPT-5.6 Sol", ("vision", "reasoning")),
    ("openai", "gpt-5.6-terra", "GPT-5.6 Terra", ("vision", "reasoning")),
    ("openai", "gpt-5.6-luna", "GPT-5.6 Luna", ("vision", "reasoning")),
    ("groq", "llama-3.3-70b-versatile", "Llama 3.3 70B Versatile", ("reasoning",)),
    ("together", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "Llama 3.3 70B Turbo", ("reasoning",)),
    ("cloudflare", "@cf/meta/llama-3.1-8b-instruct", "Llama 3.1 8B Instruct", ()),
    ("ollama", "llama3.2", "Llama 3.2", ()),
    ("ollama", "qwen2.5", "Qwen 2.5", ("reasoning",)),
    ("lm_studio", "local-model", "Loaded LM Studio Model", ()),
    ("llama_cpp", "local-model", "Loaded llama.cpp Model", ()),
)


class VideoFlowProviderService:
    """Own Video Flow provider state and expose secret-safe UI records."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            try:
                from voice_flow.storage import resolve_active_db_path
                db_path = resolve_active_db_path()
            except Exception:
                db_path = DB_PATH
        self.db_path = os.fspath(db_path)
        Path(self.db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def switch_account(self, new_db_path: str) -> None:
        """Dynamically repoint VideoFlowProviderService to the active account database."""
        self.db_path = os.fspath(new_db_path)
        Path(self.db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _recover_corrupted_db(self) -> None:
        """Attempt to restore a malformed SQLite DB from .repaired, or quarantine it."""
        try:
            base = Path(self.db_path)
            rep = base.with_name(base.name + ".repaired")
            if rep.exists() and rep.stat().st_size > 0:
                try:
                    with sqlite3.connect(str(rep)) as test_conn:
                        res = test_conn.execute("PRAGMA integrity_check;").fetchone()
                        if res and res[0] == "ok":
                            shutil.copy2(str(rep), str(base))
                            return
                except Exception:
                    pass
            ts = int(time.time())
            bak = base.with_name(f"{base.name}.corrupt.{ts}.bak")
            if base.exists():
                shutil.copy2(str(base), str(bak))
                for ext in ("", "-wal", "-shm"):
                    f = Path(str(base) + ext)
                    if f.exists():
                        try:
                            f.unlink()
                        except Exception:
                            pass
        except Exception:
            pass

    def _init_db(self) -> None:
        try:
            self._do_init_db()
        except sqlite3.DatabaseError as exc:
            if any(k in str(exc).lower() for k in ("malformed", "corrupt", "disk image", "not a database")):
                self._recover_corrupted_db()
                self._do_init_db()
            else:
                raise

    def _do_init_db(self) -> None:
        with self._connection() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS video_flow_provider_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                name TEXT NOT NULL,
                auth_type TEXT NOT NULL,
                secret TEXT DEFAULT '',
                priority INTEGER NOT NULL DEFAULT 1,
                is_active INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'untested',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS video_flow_provider_models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                model_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                capabilities_json TEXT NOT NULL DEFAULT '[]',
                is_active INTEGER NOT NULL DEFAULT 1,
                custom INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(provider, model_id)
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS video_flow_provider_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )""")
            existing_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(video_flow_provider_connections)").fetchall()
            }
            for column, declaration in (
                ("account_id", "TEXT NOT NULL DEFAULT ''"),
                ("refresh_token", "TEXT NOT NULL DEFAULT ''"),
                ("token_type", "TEXT NOT NULL DEFAULT 'Bearer'"),
                ("expires_at", "TEXT NOT NULL DEFAULT ''"),
                ("cooldown_until", "TEXT NOT NULL DEFAULT ''"),
                ("last_latency_ms", "INTEGER NOT NULL DEFAULT 0"),
            ):
                if column not in existing_columns:
                    conn.execute(f"ALTER TABLE video_flow_provider_connections ADD COLUMN {column} {declaration}")
            seed_row = conn.execute(
                "SELECT value FROM video_flow_provider_settings WHERE key = 'seed_catalog_version'"
            ).fetchone()
            seed_version = json.loads(seed_row["value"]) if seed_row else None
            if seed_version != DEFAULT_CATALOG_VERSION:
                conn.execute("DELETE FROM video_flow_provider_models WHERE custom = 0")
                conn.execute(
                    "INSERT OR REPLACE INTO video_flow_provider_settings (key, value) VALUES (?, ?)",
                    ("seed_catalog_version", json.dumps(DEFAULT_CATALOG_VERSION)),
                )
            conn.executemany(
                """INSERT OR IGNORE INTO video_flow_provider_models
                (provider, model_id, display_name, capabilities_json, is_active, custom, created_at)
                VALUES (?, ?, ?, ?, 1, 0, ?)""",
                [(provider, model_id, name, json.dumps(capabilities), _now()) for provider, model_id, name, capabilities in DEFAULT_MODELS],
            )
            conn.commit()

    @staticmethod
    def provider(provider_id: str) -> dict[str, Any]:
        pid = PROVIDER_ALIASES.get(provider_id, provider_id)
        provider = PROVIDER_BY_ID.get(pid) or PROVIDER_BY_PREFIX.get(provider_id)
        if not provider:
            raise ValueError(f"Unknown Video Flow provider: {provider_id}")
        return provider

    def catalog(self) -> dict[str, Any]:
        providers = [self._public_provider(item) for item in PROVIDERS]
        return {
            "oauth": [item for item in providers if item["category"] == "oauth"],
            "api_key": [item for item in providers if item["category"] == "api_key"],
            "local": [item for item in providers if item["category"] == "local"],
            "models": self.list_models(),
            "active_model": self.get_active_model(),
        }

    def _public_provider(self, provider: dict[str, Any]) -> dict[str, Any]:
        connections = self.list_connections(provider["id"])
        public = {key: value for key, value in provider.items() if key not in {"login_command", "status_command"}}
        public.update({
            "connection_count": len(connections),
            "active_count": sum(1 for item in connections if item["is_active"]),
            "status": "connected" if any(item["is_active"] and item["status"] in {"connected", "ready", "active"} for item in connections) else "disconnected",
        })
        if provider["category"] == "oauth":
            oauth = self.oauth_status(provider["id"], refresh=(provider["id"] == "antigravity"))
            public["oauth_status"] = oauth
            if oauth["connected"]:
                public["status"] = "connected"
                public["active_count"] = max(1, public["active_count"])
        return public

    def provider_details(self, provider_id: str) -> dict[str, Any]:
        provider = self.provider(provider_id)
        provider_id = provider["id"]
        return {
            "provider": self._public_provider(provider),
            "connections": self.list_connections(provider_id),
            "models": self.list_models(provider_id, include_inactive=True),
            "load_balance_mode": self.get_setting(f"load_balance:{provider_id}", "priority"),
        }

    def add_connection(
        self,
        provider_id: str,
        *,
        name: str,
        secret: str = "",
        priority: int = 1,
        metadata: dict[str, Any] | None = None,
        account_id: str = "",
        refresh_token: str = "",
        token_type: str = "Bearer",
        expires_at: str = "",
        cooldown_until: str = "",
    ) -> dict[str, Any]:
        provider = self.provider(provider_id)
        provider_id = provider["id"]
        clean_name = (name or "Connection").strip()[:100]
        clean_secret = secret.strip()
        if provider["auth"] == "api_key" and not clean_secret:
            raise ValueError("API key or credential is required.")
        metadata = dict(metadata or {})
        if provider["auth"] == "local" and not metadata.get("base_url"):
            metadata["base_url"] = provider.get("default_base_url", "")
        now = _now()
        with self._connection() as conn:
            cursor = conn.execute(
                """INSERT INTO video_flow_provider_connections
                (provider, name, auth_type, secret, priority, is_active, status, metadata_json, created_at, updated_at,
                 account_id, refresh_token, token_type, expires_at, cooldown_until)
                VALUES (?, ?, ?, ?, ?, 1, 'untested', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    provider_id, clean_name, provider["auth"], clean_secret, max(1, int(priority)),
                    json.dumps(metadata), now, now,
                    (account_id or "").strip()[:200], refresh_token.strip(), (token_type or "Bearer").strip()[:40],
                    str(expires_at).strip()[:40], str(cooldown_until).strip()[:40],
                ),
            )
            conn.commit()
            connection_id = int(cursor.lastrowid)
        return self.get_connection(connection_id, public=True) or {}

    def get_connection(self, connection_id: int, *, public: bool = True) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM video_flow_provider_connections WHERE id = ?", (int(connection_id),)).fetchone()
        if not row:
            return None
        item = self._row_connection(row)
        return self._safe_connection(item) if public else item

    def list_connections(self, provider_id: str) -> list[dict[str, Any]]:
        provider = self.provider(provider_id)
        provider_id = provider["id"]
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM video_flow_provider_connections WHERE provider = ? ORDER BY priority, id",
                (provider_id,),
            ).fetchall()
        return [self._safe_connection(self._row_connection(row)) for row in rows]

    def active_connections(self, provider_id: str) -> list[dict[str, Any]]:
        provider = self.provider(provider_id)
        provider_id = provider["id"]
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM video_flow_provider_connections WHERE provider = ? AND is_active = 1 ORDER BY priority, id",
                (provider_id,),
            ).fetchall()
        return [self._row_connection(row) for row in rows]

    @staticmethod
    def _row_connection(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        try:
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        except json.JSONDecodeError:
            item["metadata"] = {}
        item["is_active"] = bool(item["is_active"])
        return item

    @staticmethod
    def _safe_connection(item: dict[str, Any]) -> dict[str, Any]:
        safe = {key: value for key, value in item.items() if key not in {"secret", "refresh_token"}}
        metadata = safe.get("metadata")
        if isinstance(metadata, dict):
            safe["metadata"] = {k: v for k, v in metadata.items() if k.lower() not in {"refresh_token", "access_token", "secret", "api_key", "token", "id_token"}}
        secret = str(item.get("secret", ""))
        safe["has_secret"] = bool(secret)
        safe["secret_hint"] = f"••••{secret[-4:]}" if secret else ""
        return safe

    def update_connection(self, connection_id: int, **changes: Any) -> dict[str, Any] | None:
        current = self.get_connection(connection_id, public=False)
        if not current:
            return None
        allowed: dict[str, Any] = {}
        for key in ("name", "secret", "status", "account_id", "token_type", "expires_at", "cooldown_until"):
            if key in changes and changes[key] is not None:
                allowed[key] = str(changes[key]).strip()
        if "refresh_token" in changes and changes["refresh_token"] is not None:
            allowed["refresh_token"] = str(changes["refresh_token"]).strip()
        if "last_latency_ms" in changes and changes["last_latency_ms"] is not None:
            allowed["last_latency_ms"] = max(0, int(changes["last_latency_ms"]))
        if "priority" in changes:
            allowed["priority"] = max(1, int(changes["priority"]))
        if "is_active" in changes:
            allowed["is_active"] = int(bool(changes["is_active"]))
        if "metadata" in changes and isinstance(changes["metadata"], dict):
            allowed["metadata_json"] = json.dumps(changes["metadata"])
        if not allowed:
            return self.get_connection(connection_id)
        allowed["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in allowed)
        with self._connection() as conn:
            conn.execute(
                f"UPDATE video_flow_provider_connections SET {assignments} WHERE id = ?",
                (*allowed.values(), int(connection_id)),
            )
            conn.commit()
        return self.get_connection(connection_id)

    def delete_connection(self, connection_id: int) -> bool:
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM video_flow_provider_connections WHERE id = ?", (int(connection_id),))
            conn.commit()
        return cursor.rowcount > 0

    def test_connection(self, connection_id: int) -> dict[str, Any]:
        connection = self.get_connection(connection_id, public=False)
        if not connection:
            raise ValueError("Connection not found.")
        provider_id = connection["provider"]
        provider = PROVIDER_BY_ID[provider_id]
        key = self.resolve_connection_secret(connection) or str(connection.get("secret", ""))
        metadata = connection.get("metadata", {})
        try:
            if provider["category"] == "oauth":
                if provider_id in {"copilot", "cursor", "kiro", "claude_code"}:
                    if not self.connection_is_healthy(connection):
                        raise RuntimeError(f"{provider['name']} connection is not healthy or session expired.")
                    self.update_connection(connection_id, status="active")
                    return {"success": True, "status": "active"}
                elif provider_id == "antigravity":
                    token = self.resolve_connection_secret(connection)
                    if not token:
                        raise RuntimeError("No Antigravity token found.")
                    req = urllib.request.Request(
                        "https://www.googleapis.com/oauth2/v1/userinfo?alt=json",
                        headers={"Authorization": f"Bearer {token}", "x-request-source": "local", "User-Agent": "antigravity/ide/2.1.1"},
                        method="GET",
                    )
                    started = time.monotonic()
                    try:
                        with urllib.request.urlopen(req, timeout=30) as response:
                            response.read(512)
                    except urllib.error.HTTPError as he:
                        if he.code == 401 and connection.get("refresh_token"):
                            from voice_flow.video_flow_oauth import decrypt_token as _dec, encrypt_token as _enc, _http_json, ANTIGRAVITY_CLIENT_ID, ANTIGRAVITY_CLIENT_SECRET
                            rt = _dec(self, str(connection.get("refresh_token") or ""))
                            if rt:
                                refreshed = _http_json(
                                    "https://oauth2.googleapis.com/token",
                                    data={
                                        "grant_type": "refresh_token",
                                        "client_id": ANTIGRAVITY_CLIENT_ID,
                                        "client_secret": ANTIGRAVITY_CLIENT_SECRET,
                                        "refresh_token": rt,
                                    },
                                )
                                new_acc = str(refreshed.get("access_token") or "")
                                if new_acc:
                                    self.update_connection(connection_id, secret=_enc(self, new_acc), status="active")
                                    token = new_acc
                        else:
                            raise
                    latency_ms = int((time.monotonic() - started) * 1000)
                    self.update_connection(connection_id, status="active", last_latency_ms=latency_ms)
                    return {"success": True, "status": "active", "latency_ms": latency_ms}
                elif provider_id == "openai_codex":
                    token = self.resolve_connection_secret(connection)
                    if not token:
                        raise RuntimeError("No ChatGPT / OpenAI Codex token found.")
                    started = time.monotonic()
                    latency_ms = int((time.monotonic() - started) * 1000)
                    self.update_connection(connection_id, status="active", last_latency_ms=latency_ms)
                    return {"success": True, "status": "active", "latency_ms": latency_ms}
            if provider["category"] == "local":
                base_url = metadata.get("base_url") or provider.get("default_base_url", "")
                url = base_url.rstrip("/") + ("/api/tags" if provider_id == "ollama" else "/models")
                request = urllib.request.Request(url, method="GET")
            elif provider_id == "gemini":
                url = "https://generativelanguage.googleapis.com/v1beta/models?key=" + urllib.parse.quote(key)
                request = urllib.request.Request(url, method="GET")
            elif provider_id == "vertex_ai":
                url = "https://aiplatform.googleapis.com/v1/publishers/google/models?key=" + urllib.parse.quote(key)
                request = urllib.request.Request(url, method="GET")
            elif provider_id == "cloudflare":
                account_id = str(metadata.get("account_id", "")).strip()
                if not account_id:
                    raise RuntimeError("Cloudflare account ID is required.")
                url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/models/search"
                request = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"}, method="GET")
            else:
                model_endpoints = {
                    "openai": "https://api.openai.com/v1/models",
                    "anthropic": "https://api.anthropic.com/v1/models",
                    "groq": "https://api.groq.com/openai/v1/models",
                    "together": "https://api.together.xyz/v1/models",
                    "openrouter": "https://openrouter.ai/api/v1/models",
                    "nvidia_nim": "https://integrate.api.nvidia.com/v1/models",
                    "opencode_zen": "https://opencode.ai/zen/v1/models",
                }
                url = model_endpoints.get(provider_id)
                if not url:
                    raise RuntimeError("This provider has no connection test endpoint.")
                headers = {"Authorization": f"Bearer {key}"}
                if provider_id == "anthropic":
                    headers["anthropic-version"] = "2023-06-01"
                    headers["x-api-key"] = key
                request = urllib.request.Request(url, headers=headers, method="GET")
            started = time.monotonic()
            with urllib.request.urlopen(request, timeout=30) as response:
                response.read(512)
            latency_ms = int((time.monotonic() - started) * 1000)
            self.update_connection(connection_id, status="connected", last_latency_ms=latency_ms)
            return {"success": True, "status": "connected", "latency_ms": latency_ms}
        except (OSError, urllib.error.URLError, RuntimeError) as exc:
            self.update_connection(connection_id, status="error")
            detail = ""
            if isinstance(exc, urllib.error.HTTPError):
                try:
                    raw_body = exc.read().decode("utf-8", errors="replace")
                    parsed = json.loads(raw_body)
                    if isinstance(parsed, dict):
                        err_obj = parsed.get("error")
                        if isinstance(err_obj, dict):
                            detail = err_obj.get("message") or err_obj.get("code")
                        elif isinstance(err_obj, str):
                            detail = err_obj
                        if not detail:
                            detail = parsed.get("message") or parsed.get("detail")
                except Exception:
                    pass
                if exc.code == 401:
                    reason = "Invalid API key or token expired (HTTP 401)" + (f": {detail}" if detail else "")
                elif exc.code == 403:
                    reason = "Forbidden - check API key permissions (HTTP 403)" + (f": {detail}" if detail else "")
                elif exc.code == 429:
                    reason = "Quota exhausted / Rate limit reached (HTTP 429)" + (f": {detail}" if detail else "")
                elif exc.code == 404:
                    reason = "Endpoint or model not found (HTTP 404)" + (f": {detail}" if detail else "")
                else:
                    reason = f"HTTP {exc.code}: {detail or exc.reason}"
            else:
                reason = getattr(exc, "reason", None) or str(exc)
            return {"success": False, "status": "error", "error": str(reason)[:300]}
    def add_model(
        self,
        provider_id: str,
        model_id: str,
        display_name: str = "",
        capabilities: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        provider = self.provider(provider_id)
        provider_id = provider["id"]
        raw = model_id.strip()
        prefix = provider.get("prefix") or provider_id
        prefixes = [prefix, provider_id]
        if provider_id == "antigravity":
            prefixes.extend(["agy", "antigravity", "models"])
        elif provider_id in ("gemini", "vertex_ai"):
            prefixes.extend(["models"])
        elif provider_id == "openai_codex":
            prefixes.extend(["codex", "chatgpt", "openai_codex"])
        elif provider_id == "vertex_ai":
            prefixes.extend(["vx", "vertex", "vertex_ai", "models"])
        while True:
            stripped = False
            for pfx in prefixes:
                if pfx and raw.lower().startswith(pfx.lower() + "/"):
                    raw = raw[len(pfx) + 1:].strip()
                    stripped = True
                    break
            if not stripped:
                break
        while raw.lower().startswith("models/"):
            raw = raw[len("models/"):].strip()
        raw = raw.strip(" /")
        if not raw or not re.fullmatch(r"[A-Za-z0-9@._:/-]+", raw):
            raise ValueError("Enter only the provider's model ID.")
        label = (display_name.strip() or raw.replace("-", " ").replace("_", " ").title())[:120]
        clean_capabilities = [item for item in (capabilities or []) if item in {"vision", "reasoning", "code", "audio"}]
        if not clean_capabilities:
            low_raw = raw.lower()
            if any(k in low_raw for k in ("gemini", "claude", "gpt", "flash", "pro")):
                clean_capabilities = ["vision", "reasoning"]
        with self._connection() as conn:
            conn.execute(
                """INSERT INTO video_flow_provider_models
                (provider, model_id, display_name, capabilities_json, is_active, custom, created_at)
                VALUES (?, ?, ?, ?, 1, 1, ?)
                ON CONFLICT(provider, model_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    capabilities_json = excluded.capabilities_json,
                    is_active = 1,
                    custom = 1""",
                (provider_id, raw, label, json.dumps(clean_capabilities), _now()),
            )
            conn.commit()
        return next(item for item in self.list_models(provider_id, include_inactive=True) if item["model_id"] == raw)

    def list_models(self, provider_id: str | None = None, *, include_inactive: bool = False) -> list[dict[str, Any]]:
        where: list[str] = []
        values: list[Any] = []
        if provider_id:
            provider = self.provider(provider_id)
            provider_id = provider["id"]
            where.append("provider = ?")
            values.append(provider_id)
        if not include_inactive:
            where.append("is_active = 1")
        clause = " WHERE " + " AND ".join(where) if where else ""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM video_flow_provider_models" + clause + " ORDER BY provider, custom, id",
                values,
            ).fetchall()
        models: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            provider = PROVIDER_BY_ID.get(item["provider"])
            if not provider:
                continue
            try:
                capabilities = json.loads(item.pop("capabilities_json") or "[]")
            except json.JSONDecodeError:
                capabilities = []
            public_provider = self._public_provider(provider)
            available = public_provider["status"] == "connected"
            if provider["id"] == "antigravity":
                # Available once the Google consent-popup OAuth connection is
                # active OR the desktop-app bridge is attached.
                antigravity_status = public_provider.get("oauth_status") or {}
                available = available or bool(antigravity_status.get("connected")) or bool(antigravity_status.get("bridge_ready"))
            item.update({
                "provider_name": provider["name"],
                "provider_prefix": provider["prefix"],
                "full_id": f"{provider['prefix']}/{item['model_id']}",
                "capabilities": capabilities,
                "is_active": bool(item["is_active"]),
                "custom": bool(item["custom"]),
                "available": available,
            })
            models.append(item)
        return models

    def set_model_active(self, model_db_id: int, active: bool) -> bool:
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE video_flow_provider_models SET is_active = ? WHERE id = ?",
                (int(bool(active)), int(model_db_id)),
            )
            conn.commit()
        return cursor.rowcount > 0

    def delete_model(self, model_db_id: int) -> bool:
        with self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM video_flow_provider_models WHERE id = ? AND custom = 1",
                (int(model_db_id),),
            )
            conn.commit()
        return cursor.rowcount > 0

    def set_setting(self, key: str, value: Any) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO video_flow_provider_settings (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )
            conn.commit()

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._connection() as conn:
            row = conn.execute("SELECT value FROM video_flow_provider_settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return default

    def set_active_model(self, model_ref: str) -> None:
        ref = model_ref.strip()
        if not self.is_selectable_model_ref(ref):
            raise ValueError("Select a connected, enabled Video Flow model.")
        self.set_setting("active_model", ref)

    def get_active_model(self) -> str:
        active = str(self.get_setting("active_model", "local/deterministic"))
        if self.is_selectable_model_ref(active):
            return active
        fallback = "local/deterministic"
        self.set_setting("active_model", fallback)
        return fallback

    def selectable_model_refs(self) -> set[str]:
        """Return local plus models whose provider is presently usable."""
        return {"local/deterministic"} | {
            item["full_id"]
            for item in self.list_models()
            if item["available"] and item["is_active"]
        }

    def is_selectable_model_ref(self, model_ref: str) -> bool:
        return model_ref.strip() in self.selectable_model_refs()

    def oauth_status(self, provider_id: str, *, refresh: bool = True) -> dict[str, Any]:
        provider = self.provider(provider_id)
        if provider["category"] != "oauth":
            raise ValueError("Provider does not use account authentication.")
        cached = self.get_setting(f"oauth_status:{provider_id}", None)
        if not refresh and isinstance(cached, dict):
            return cached
        status = {"connected": False, "label": "Not connected", "checked_at": _now()}
        if not refresh:
            return status
        try:
            if provider_id in {"copilot", "cursor", "antigravity", "openai_codex"}:
                active = [
                    item for item in self.list_connections(provider_id)
                    if item["is_active"] and item["status"] == "active"
                ]
                status["connected"] = bool(active)
                if active:
                    status["label"] = "Account connected"
                    status["account_id"] = str(active[0].get("account_id") or "")
                else:
                    status["label"] = "Not connected"
                if not active and provider_id == "cursor":
                    config = oauth_config(provider_id)
                    if any(Path(raw).expanduser().is_file() for raw in config.cli_files):
                        status["label"] = "Cursor session found — press Sign in to import"
            else:
                command = provider.get("status_command") or []
                executable = shutil.which(command[0]) if command else None
                if executable:
                    result = subprocess.run(command, capture_output=True, text=True, timeout=12)
                    output = (result.stdout + " " + result.stderr).strip()
                    negative = any(word in output.lower() for word in ("not logged", "logged out", "not authenticated"))
                    status["connected"] = result.returncode == 0 and not negative
                    status["label"] = "Account connected" if status["connected"] else "Not connected"
        except (OSError, subprocess.SubprocessError):
            pass
        self.set_setting(f"oauth_status:{provider_id}", status)
        return status

    def start_oauth(self, provider_id: str, port: int = 8991) -> dict[str, Any]:
        provider = self.provider(provider_id)
        provider_id = provider["id"]
        if provider["category"] != "oauth":
            raise ValueError("Provider does not use account authentication.")
        config = oauth_config(provider_id)
        from voice_flow.video_flow_oauth import (
            start_pkce_flow,
            launch_system_browser,
            import_cli_session,
            import_cursor_session,
            start_device_flow,
            OAuthError,
        )

        # 1. Device flow (GitHub Copilot)
        if config.flow == "device":
            info = start_device_flow(self, provider_id)
            if not (os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("VOICE_FLOW_NO_BROWSER_POPUP")):
                launch_system_browser(info["verification_uri"])
            self._spawn_device_poll(provider_id, info)
            return {
                "success": True,
                "launched": True,
                "provider": provider_id,
                "flow": "device",
                "device": info,
                "message": f"Enter code {info['user_code']} at {info['verification_uri']} in your browser. Voice Flow connects automatically.",
            }

        # 2. OpenAI Codex / ChatGPT Device Code Flow (matches user screen recording)
        if provider_id == "openai_codex":
            from voice_flow.video_flow_oauth import start_openai_device_flow
            try:
                dev = start_openai_device_flow()
                opened = False
                if not (os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("VOICE_FLOW_NO_BROWSER_POPUP")):
                    opened = launch_system_browser(dev["verification_url"])
                return {
                    "success": True,
                    "flow": "device",
                    "provider": provider_id,
                    "opened": opened,
                    "user_code": dev["user_code"],
                    "device_auth_id": dev["device_auth_id"],
                    "verification_url": dev["verification_url"],
                    "authUrl": dev["verification_url"],
                    "auth_url": dev["verification_url"],
                    "interval": dev["interval"],
                    "expires_in": dev["expires_in"],
                    "message": f"Enter code {dev['user_code']} in your browser. Voice Flow connects automatically.",
                }
            except Exception as exc:
                try:
                    imported = import_cli_session(self, provider_id)
                    connection = self._create_oauth_connection(provider_id, imported)
                    return {
                        "success": True,
                        "flow": "cli",
                        "launched": False,
                        "imported": True,
                        "provider": provider_id,
                        "connection": connection,
                        "account": connection.get("account_id") or "",
                        "message": f"Successfully connected {provider['name']} account ({connection.get('account_id') or 'active'})!",
                    }
                except Exception:
                    raise exc

        # 3. Local Session Import (Cursor, Claude Code)
        if config.flow in ("cli", "hybrid") or config.cli_files:
            try:
                if provider_id == "cursor":
                    imported = import_cursor_session(self)
                else:
                    imported = import_cli_session(self, provider_id)
                connection = self._create_oauth_connection(provider_id, imported)
                return {
                    "success": True,
                    "flow": "cli",
                    "launched": False,
                    "imported": True,
                    "provider": provider_id,
                    "connection": connection,
                    "account": connection.get("account_id") or "",
                    "message": f"Successfully connected {provider['name']} account ({connection.get('account_id') or 'active'})!",
                }
            except Exception:
                pass

        # 3. System Default Browser OAuth Flow (Antigravity, Gemini, OpenAI Codex browser OAuth)
        if config.flow in ("pkce", "web", "hybrid") or provider_id in ("antigravity", "gemini"):
            redirect_uri = f"http://127.0.0.1:{port}/callback"
            res = start_pkce_flow(self, provider_id, port=port, redirect_uri=redirect_uri)
            auth_url = res.get("auth_url", "")
            opened = False
            if not (os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("VOICE_FLOW_NO_BROWSER_POPUP")):
                opened = launch_system_browser(auth_url)
            return {
                "success": True,
                "flow": "web",
                "authUrl": auth_url,
                "auth_url": auth_url,
                "opened": opened,
                "state": res.get("state"),
                "redirectUri": redirect_uri,
                "provider": provider_id,
                "message": f"Choose your {provider['name']} account in the browser that just opened — this app connects automatically.",
            }

        # 4. Fallback CLI command launcher
        command = list(provider.get("login_command") or [])
        if not command:
            raise RuntimeError(f"No login command is available for {provider['name']}.")
        cmd_name = command[0]
        executable = shutil.which(cmd_name) or None
        if not executable and os.name == "nt":
            candidates = [
                Path(r"D:\npm-global") / f"{cmd_name}.ps1",
                Path(r"D:\npm-global") / f"{cmd_name}.cmd",
                Path(os.environ.get("APPDATA", "")) / "npm" / f"{cmd_name}.cmd",
                Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin" / cmd_name,
            ]
            for cand in candidates:
                if cand.is_file():
                    executable = str(cand)
                    break
        if not executable:
            raise RuntimeError(f"{provider['name']} is not installed. Install it, then press Refresh.")
        if os.name == "nt":
            joined = " ".join(command)
            subprocess.Popen(
                ["powershell.exe", "-NoExit", "-Command", joined],
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010),
                close_fds=True,
            )
        else:
            subprocess.Popen(command, close_fds=True)
        wait_for_cli_session(self, provider_id)
        return {
            "success": True,
            "launched": True,
            "provider": provider_id,
            "message": f"Authentication flow opened for {provider['name']}. Complete the login in the window that just opened — Voice Flow connects automatically.",
        }

    def _spawn_device_poll(self, provider_id: str, info: dict[str, Any]) -> None:
        """Watch an in-progress device flow in the background until it resolves.

        The connection is created automatically once the user authorizes in the
        browser, so the existing UI needs no polling logic of its own.
        """
        existing = getattr(self, "_device_poll_thread", None)
        if existing is not None and existing.is_alive():
            return
        deadline = time.time() + max(60, int(info.get("expires_in") or 900))
        interval = max(3, int(info.get("interval") or 5))

        def worker() -> None:
            delay = interval
            while time.time() < deadline:
                time.sleep(delay)
                try:
                    result = self.oauth_poll(provider_id)
                except Exception:
                    break
                if result.get("status") == "connected":
                    break
                delay += 2  # GitHub recommends backoff on slow_down

        self._device_poll_thread = threading.Thread(
            target=worker,
            name=f"vf-device-poll-{provider_id}",
            daemon=True,
        )
        self._device_poll_thread.start()

    def _create_oauth_connection(self, provider_id: str, imported: dict[str, Any]) -> dict[str, Any]:
        provider = self.provider(provider_id)
        provider_id = provider["id"]
        account_id = str(imported.get("account_id") or "").strip()
        access = str(imported.get("access_token") or "")
        name = f"{provider['name']} {account_id}" if account_id else f"{provider['name']} account"
        metadata: dict[str, Any] = {"source": str(imported.get("source") or "oauth")}
        if imported.get("project_id"):
            metadata["project_id"] = str(imported["project_id"])
        if imported.get("chatgpt_account_id"):
            metadata["chatgpt_account_id"] = str(imported["chatgpt_account_id"])
        if imported.get("chatgpt_plan_type"):
            metadata["chatgpt_plan_type"] = str(imported["chatgpt_plan_type"])

        # Same-account re-import updates the existing connection in place
        # instead of piling up duplicate rows (different accounts on the same
        # provider still get their own connection each).
        for existing in self.list_connections(provider_id):
            if str(existing.get("account_id") or "").strip() == account_id and account_id:
                merged_meta = dict(existing.get("metadata") or {})
                merged_meta.update(metadata)
                changes: dict[str, Any] = {
                    "name": name[:100],
                    "secret": encrypt_token(self, access) if access else "",
                    "status": "active",
                    "is_active": 1,
                    "metadata": merged_meta,
                }
                if imported.get("refresh_token"):
                    changes["refresh_token"] = encrypt_token(self, str(imported["refresh_token"]))
                if imported.get("expires_at"):
                    changes["expires_at"] = str(imported["expires_at"])
                self.update_connection(int(existing["id"]), **changes)
                return self.get_connection(int(existing["id"])) or {}

        connection = self.add_connection(
            provider_id,
            name=name[:100],
            secret=encrypt_token(self, access) if access else "",
            account_id=account_id,
            refresh_token=encrypt_token(self, str(imported.get("refresh_token") or "")),
            expires_at=str(imported.get("expires_at") or ""),
            metadata=metadata,
        )
        self.update_connection(
            int(connection["id"]),
            status="active",
            token_type="Bearer",
        )
        return self.get_connection(int(connection["id"])) or {}

    def oauth_poll(self, provider_id: str) -> dict[str, Any]:
        """Poll an in-progress device-code flow and store tokens when authorized."""
        config = oauth_config(provider_id)
        if config.flow != "device":
            raise OAuthError("This provider does not use the device-code flow.")
        result = poll_device_flow(self, provider_id)
        if result.get("status") != "authorized":
            return result
        if provider_id == "copilot":
            exchanged = exchange_copilot_token(self, str(result.get("access_token") or ""))
            access = str(exchanged.get("access_token") or "")
            expires_at = str(exchanged.get("expires_at") or "") or jwt_expiry(access)
            # The GitHub OAuth token is kept in refresh_token: the Copilot JWT
            # lives ~30 minutes and is re-exchanged from it by the refresher.
            connection = self._create_oauth_connection(provider_id, {
                "access_token": access,
                "refresh_token": str(result.get("access_token") or ""),
                "expires_at": expires_at,
                "account_id": "github-copilot",
            })
        else:
            connection = self._create_oauth_connection(provider_id, {
                "access_token": str(result.get("access_token") or ""),
                "refresh_token": str(result.get("refresh_token") or ""),
                "expires_at": int(result.get("expires_in") or 0),
                "account_id": provider_id,
            })
        return {"status": "connected", "connection": connection}

    def poll_device_flow(self, provider_id: str, device_auth_id: str = "", user_code: str = "") -> dict[str, Any]:
        """Poll device-code flow by ID/code (OpenAI Codex / ChatGPT)."""
        if provider_id == "codex":
            provider_id = "openai_codex"
        if provider_id == "openai_codex":
            from voice_flow.video_flow_oauth import poll_openai_device_flow
            res = poll_openai_device_flow(device_auth_id, user_code)
            if res.get("status") == "approved":
                connection = self._create_oauth_connection(provider_id, {
                    "access_token": res["access_token"],
                    "refresh_token": res.get("refresh_token", ""),
                    "account_id": res.get("account_id", ""),
                    "chatgpt_account_id": res.get("chatgpt_account_id", ""),
                    "chatgpt_plan_type": res.get("chatgpt_plan_type", ""),
                    "expires_at": res.get("expires_at", ""),
                    "source": "device_code",
                })
                return {
                    "status": "approved",
                    "account": res.get("account_id", ""),
                    "connection": connection,
                }
            return res
        return {"status": "error", "error": f"Device flow not supported for provider '{provider_id}'."}

    def oauth_import(self, provider_id: str) -> dict[str, Any]:
        """Import the provider's CLI session into a fresh connection."""
        provider = self.provider(provider_id)
        provider_id = provider["id"]
        imported = import_cli_session(self, provider_id)
        account_id = str(imported.get("account_id") or "").strip()
        for connection in self.list_connections(provider_id):
            if connection["is_active"] and str(connection.get("account_id") or "") == account_id:
                refreshed = refresh_and_store(self, dict(connection, **{
                    "secret": encrypt_token(self, str(imported.get("access_token") or "")),
                    "refresh_token": encrypt_token(self, str(imported.get("refresh_token") or "")),
                }))
                return self.get_connection(int(connection["id"])) or refreshed
        return self._create_oauth_connection(provider_id, imported)

    def oauth_refresh(self, connection_id: int) -> dict[str, Any]:
        """Force a token refresh for a connection; raise on failure."""
        connection = self.get_connection(connection_id, public=False)
        if not connection:
            raise ValueError("Connection not found.")
        refresh_and_store(self, connection)
        return self.get_connection(connection_id) or {}

    def list_all_connections(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM video_flow_provider_connections ORDER BY provider, priority, id"
            ).fetchall()
        return [self._row_connection(row) for row in rows]

    def connection_is_healthy(self, connection: dict[str, Any]) -> bool:
        if not connection.get("is_active"):
            return False
        status = str(connection.get("status") or "")
        now = time.time()
        expiry = str(connection.get("expires_at") or "")
        expired = False
        if expiry:
            try:
                if 0 < float(expiry) <= now:
                    expired = True
            except (TypeError, ValueError):
                pass

        if status in {"expired", "rate_limited", "error"} or expired:
            cid = connection.get("id")
            if cid and (connection.get("refresh_token") or (connection.get("metadata") or {}).get("source")):
                try:
                    from voice_flow.video_flow_oauth import refresh_and_store
                    raw_conn = self.get_connection(int(cid), public=False) or connection
                    refreshed = refresh_and_store(self, raw_conn)
                    if refreshed and str(refreshed.get("status") or "") == "active":
                        return True
                except Exception:
                    return False
            return False

        cooldown = str(connection.get("cooldown_until") or "")
        if cooldown:
            try:
                if float(cooldown) > now:
                    return False
            except (TypeError, ValueError):
                pass
        return True

    def pick_best_connection(self, provider_id: str) -> dict[str, Any] | None:
        """Return the healthiest connection: lowest measured latency, then priority."""
        best: dict[str, Any] | None = None
        for connection in self.active_connections(provider_id):
            if not self.connection_is_healthy(connection):
                continue
            latency = int(connection.get("last_latency_ms") or 0)
            if best is None:
                best = connection
            elif latency > 0:
                best_latency = int(best.get("last_latency_ms") or 0)
                if best_latency <= 0 or latency < best_latency:
                    best = connection
        return best

    def resolve_connection_secret(self, connection: dict[str, Any]) -> str:
        cid = connection.get("id")
        secret = str(connection.get("secret") or "")
        if not secret and cid:
            raw = self.get_connection(int(cid), public=False)
            if raw:
                secret = str(raw.get("secret") or "")
                connection = raw

        now = time.time()
        expiry = str(connection.get("expires_at") or "")
        if expiry and cid and (connection.get("refresh_token") or (connection.get("metadata") or {}).get("source")):
            try:
                if 0 < float(expiry) <= now + 60:
                    from voice_flow.video_flow_oauth import refresh_and_store
                    raw_conn = self.get_connection(int(cid), public=False) or connection
                    refreshed = refresh_and_store(self, raw_conn)
                    if refreshed and refreshed.get("secret"):
                        secret = str(refreshed.get("secret") or "")
            except Exception:
                pass

        return decrypt_token(self, secret) if looks_encrypted(secret) else secret

    def mark_connection_expired(self, connection_id: int) -> None:
        self.update_connection(connection_id, status="expired")

    def mark_cooldown(self, connection_id: int, seconds: int = COOLDOWN_DEFAULT_SECONDS) -> None:
        self.update_connection(
            connection_id,
            status="rate_limited",
            cooldown_until=str(int(time.time()) + max(1, int(seconds))),
        )


video_flow_provider_service = VideoFlowProviderService()

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
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from voice_flow.storage import DB_PATH


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


PROVIDERS: tuple[dict[str, Any], ...] = (
    {"id": "claude_code", "name": "Claude Code", "category": "oauth", "prefix": "claude-code", "icon": "✺", "auth": "oauth", "description": "Use a signed-in Claude Code subscription.", "login_command": ["claude", "auth", "login"], "status_command": ["claude", "auth", "status"], "get_key_url": "https://console.anthropic.com/settings/keys"},
    {"id": "antigravity", "name": "Antigravity", "category": "oauth", "prefix": "antigravity", "icon": "A", "auth": "oauth", "description": "Use the Google account signed into Antigravity.", "login_command": ["antigravity"], "status_command": [], "get_key_url": "https://aistudio.google.com/apikey"},
    {"id": "openai_codex", "name": "OpenAI Codex", "category": "oauth", "prefix": "codex", "icon": "◎", "auth": "oauth", "description": "Use a signed-in Codex account.", "login_command": ["codex", "login"], "status_command": ["codex", "login", "status"], "get_key_url": "https://platform.openai.com/api-keys"},
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

PROVIDER_BY_ID = {item["id"]: item for item in PROVIDERS}
DEFAULT_CATALOG_VERSION = "2026-08-13.1"

def antigravity_executable_candidates() -> list[Path]:
    """Return deterministic Windows install locations for Antigravity.

    The desktop installer uses a per-user location that is not normally added to
    PATH. Keep discovery explicit and side-effect free so the OAuth button can
    launch the installed app without asking the user to download it again.
    """
    candidates: list[Path] = []
    for value in (
        os.environ.get("ANTIGRAVITY_EXE"),
        os.environ.get("ANTIGRAVITY_EXECUTABLE"),
        shutil.which("antigravity"),
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


def find_antigravity_executable() -> Path | None:
    for candidate in antigravity_executable_candidates():
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None



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
    ("claude_code", "sonnet", "Claude Sonnet 5 (Latest)", ("vision", "reasoning", "code")),
    ("claude_code", "opus", "Claude Opus 5 (Latest)", ("vision", "reasoning", "code")),
    ("claude_code", "fable", "Claude Fable 5 (Latest)", ("vision", "reasoning", "code")),
    ("antigravity", "gemini-3.5-flash", "Gemini 3.5 Flash", ("vision", "reasoning")),
    ("antigravity", "gemini-3.1-pro", "Gemini 3.1 Pro", ("vision", "reasoning")),
    ("antigravity", "gemini-3-flash", "Gemini 3 Flash", ("vision", "reasoning")),
    ("antigravity", "claude-sonnet-4-6", "Claude Sonnet 4.6", ("vision", "reasoning")),
    ("antigravity", "claude-opus-4-6", "Claude Opus 4.6", ("vision", "reasoning")),
    ("antigravity", "gpt-oss-120b", "GPT-OSS 120B", ("reasoning", "code")),
    ("openai_codex", "gpt-5.6-sol", "GPT-5.6 Sol", ("vision", "reasoning", "code")),
    ("openai_codex", "gpt-5.6-terra", "GPT-5.6 Terra", ("vision", "reasoning", "code")),
    ("openai_codex", "gpt-5.3-codex", "GPT-5.3 Codex", ("reasoning", "code")),
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

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = os.fspath(db_path)
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

    def _init_db(self) -> None:
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
        provider = PROVIDER_BY_ID.get(provider_id)
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
    ) -> dict[str, Any]:
        provider = self.provider(provider_id)
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
                (provider, name, auth_type, secret, priority, is_active, status, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, 'untested', ?, ?, ?)""",
                (provider_id, clean_name, provider["auth"], clean_secret, max(1, int(priority)), json.dumps(metadata), now, now),
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
        self.provider(provider_id)
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM video_flow_provider_connections WHERE provider = ? ORDER BY priority, id",
                (provider_id,),
            ).fetchall()
        return [self._safe_connection(self._row_connection(row)) for row in rows]

    def active_connections(self, provider_id: str) -> list[dict[str, Any]]:
        self.provider(provider_id)
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
        safe = {key: value for key, value in item.items() if key != "secret"}
        secret = str(item.get("secret", ""))
        safe["has_secret"] = bool(secret)
        safe["secret_hint"] = f"••••{secret[-4:]}" if secret else ""
        return safe

    def update_connection(self, connection_id: int, **changes: Any) -> dict[str, Any] | None:
        current = self.get_connection(connection_id, public=False)
        if not current:
            return None
        allowed: dict[str, Any] = {}
        for key in ("name", "secret", "status"):
            if key in changes and changes[key] is not None:
                allowed[key] = str(changes[key]).strip()
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
        key = str(connection.get("secret", ""))
        metadata = connection.get("metadata", {})
        try:
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
            with urllib.request.urlopen(request, timeout=12) as response:
                response.read(512)
            self.update_connection(connection_id, status="connected")
            return {"success": True, "status": "connected"}
        except (OSError, urllib.error.URLError, RuntimeError) as exc:
            self.update_connection(connection_id, status="error")
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
        raw = model_id.strip()
        prefix = provider["prefix"]
        if raw.lower().startswith(prefix.lower() + "/"):
            raw = raw.split("/", 1)[1]
        raw = raw.strip(" /")
        if not raw or not re.fullmatch(r"[A-Za-z0-9@._:/-]+", raw):
            raise ValueError("Enter only the provider's model ID.")
        label = (display_name.strip() or raw.replace("-", " ").replace("_", " ").title())[:120]
        clean_capabilities = [item for item in (capabilities or []) if item in {"vision", "reasoning", "code", "audio"}]
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
            self.provider(provider_id)
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
                available = bool((public_provider.get("oauth_status") or {}).get("bridge_ready"))
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
            raise ValueError("Select a connected, enabled Video Flow model or combo.")
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
        ref = model_ref.strip()
        selectable = self.selectable_model_refs()
        if ref in selectable:
            return True
        if not ref.startswith("combo:"):
            return False

        name = ref.removeprefix("combo:")
        if not name:
            return False
        try:
            with self._connection() as conn:
                combo = conn.execute(
                    "SELECT id FROM video_flow_combos WHERE name = ?", (name,)
                ).fetchone()
                if not combo:
                    return False
                members = conn.execute(
                    "SELECT model_ref FROM video_flow_combo_models WHERE combo_id = ? ORDER BY position",
                    (int(combo["id"]),),
                ).fetchall()
        except sqlite3.OperationalError:
            return False
        return bool(members) and all(member["model_ref"] in selectable for member in members)

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
            if provider_id == "antigravity":
                executable = find_antigravity_executable()
                state_file = antigravity_state_path()
                bridge = antigravity_bridge_status()
                status.update({
                    "installed": bool(executable),
                    "executable": str(executable) if executable else "",
                    "state_available": state_file.is_file(),
                    "bridge": bridge,
                    "bridge_ready": bridge["ready"],
                })
                status["connected"] = bool(executable and state_file.is_file())
                if not executable:
                    status["label"] = "Antigravity is not installed"
                elif not status["connected"]:
                    status["label"] = "Open Antigravity and sign in"
                elif not bridge["ready"]:
                    status["label"] = "Antigravity signed in; Video Flow bridge is not attached"
                else:
                    status["label"] = "Antigravity account ready for Video Flow"
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

    def start_oauth(self, provider_id: str) -> dict[str, Any]:
        provider = self.provider(provider_id)
        if provider["category"] != "oauth":
            raise ValueError("Provider does not use account authentication.")
        command = list(provider.get("login_command") or [])
        if not command:
            raise RuntimeError("No login command is available.")
        executable = find_antigravity_executable() if provider_id == "antigravity" else (shutil.which(command[0]) or None)
        if not executable:
            raise RuntimeError(f"{provider['name']} is not installed. Install it, then press Refresh.")
        if provider_id == "antigravity":
            subprocess.Popen([str(executable)], close_fds=True)
        elif os.name == "nt":
            joined = " ".join(command)
            subprocess.Popen(
                ["powershell.exe", "-NoExit", "-Command", joined],
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010),
                close_fds=True,
            )
        else:
            subprocess.Popen(command, close_fds=True)
        return {"success": True, "launched": True, "provider": provider_id, "message": "Antigravity opened. Video Flow will use the signed-in agy CLI; refresh this panel to see models." if provider_id == "antigravity" else "Authentication flow opened."}


video_flow_provider_service = VideoFlowProviderService()

"""Application boundary for the isolated Code2Video-to-Narova engine.

The desktop/API layer only deals with ``JobV3`` records.  This module owns the
small amount of durable job state needed to bridge that API to
``VideoFlowEngine`` without making the application import vendor code directly.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping

from voice_flow.paths import data_dir
from voice_flow.video_flow_contracts import JobV3, VideoFlowJob


_TERMINAL_STATES = {"complete", "failed", "cancelled"}

# NotebookLM usage limits (since 2026-09-02) refresh on a ~5-hour rolling
# window, so a RATE_LIMITED generation is worth ONE automatic retry later
# instead of a dead "Generation failed" the user can't do anything about.
_RATE_LIMIT_RETRY_SECONDS = 5 * 3600
_RATE_LIMIT_META_KEYS = (
    "mode", "title", "source_name", "model_ref", "theme", "visual_direction",
    "allow_external_ai", "allow_local_fallback", "voice", "duration_seconds",
    "target_duration_seconds", "video_engine", "provider", "format", "style", "style_prompt", "language",
    "focus", "source_url", "source_file", "profile", "notebook_id",
    "source_id", "task_id",
)
_RESET_TIME_RE = re.compile(r"resets?\s+at\s+(\d{1,2}):(\d{2})\s*(AM|PM)?", re.I)


def _parse_reset_time(text: str) -> datetime | None:
    """Best-effort 'resets at HH:MM' parse if Google ever surfaces one in the
    error text; otherwise the caller falls back to the 5-hour default."""
    match = _RESET_TIME_RE.search(text or "")
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    ampm = (match.group(3) or "").upper()
    if ampm == "PM" and hour != 12:
        hour += 12
    if ampm == "AM" and hour == 12:
        hour = 0
    target = datetime.now().replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
    if target <= datetime.now():
        target += timedelta(days=1)
    return target
_PROJECT_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")
_SECRET = re.compile(r"(?i)(?:bearer\s+|api[_ -]?key[=:]\s*|[a-z]{0,3}sk[-_][a-z0-9_-]{8,})[^\s,;]+")
_SAFE_ENV_NAMES = (
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOME",
    "LOCALAPPDATA",
    "APPDATA",
)
_GROQ_MODEL = "openai/gpt-oss-120b"
_GROQ_SUPPORTED = {_GROQ_MODEL, "openai/gpt-oss-20b", "qwen/qwen3.6-27b"}
_GROQ_STALE = {"llama-3.3-70b-versatile", "llama-3.3-70b-specdec", "llama-3.1-8b-instant"}


def _windows_hidden_startupinfo():
    """STARTUPINFO with SW_HIDE so spawned consoles never flash (pythonw host)."""
    if os.name != "nt":
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
    startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
    return startupinfo

# OpenAI-compatible chat-completions endpoints the one-shot planning worker
# can drive. The Video Flow provider page's own connections supply the key.
_PLANNING_ENDPOINTS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "openai_codex": "https://chatgpt.com/backend-api/codex/responses",
    "codex": "https://chatgpt.com/backend-api/codex/responses",
    "together": "https://api.together.xyz/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "nvidia_nim": "https://integrate.api.nvidia.com/v1/chat/completions",
    "nim": "https://integrate.api.nvidia.com/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    "antigravity": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    "agy": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
}


class VideoFlowStore:
    """Tiny SQLite store for Video Flow jobs, independent of dictation history."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._custom_db = db_path is not None
        if db_path is None:
            try:
                from voice_flow.storage import resolve_active_db_path
                db_path = resolve_active_db_path()
            except Exception:
                db_path = data_dir() / "voice_flow.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        with contextlib.closing(self._connection()) as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS video_flow_jobs (
                    job_id TEXT PRIMARY KEY NOT NULL,
                    state TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    meta_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    def switch_account(self, new_db_path: Path | str) -> None:
        """Repoint video flow store to active account database."""
        with self._lock:
            self.db_path = Path(new_db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()

    def repoint_if_needed(self) -> bool:
        """Repoint video flow store to active account database if changed."""
        if getattr(self, "_custom_db", False):
            return False
        try:
            from voice_flow.storage import resolve_active_db_path
            target = resolve_active_db_path()
        except Exception:
            target = None
        if not target:
            return False
        try:
            target_path = Path(target).resolve()
            if target_path == self.db_path.resolve():
                return False
            self.switch_account(target_path)
            return True
        except Exception:
            return False

    def _connection(self) -> sqlite3.Connection:
        self.repoint_if_needed()
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def create(self, job: JobV3) -> JobV3:
        now = time.time()
        with self._lock, self._connection() as conn:
            conn.execute(
                "INSERT INTO video_flow_jobs (job_id, state, progress, message, meta_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (job.job_id, job.state, job.progress, job.message, _json(job.meta), now, now),
            )
        try:
            from voice_flow.storage import storage, StorageEngine
            target_engine = storage if Path(storage.db_path).resolve() == self.db_path.resolve() else StorageEngine(str(self.db_path))
            title = str((job.meta or {}).get("title") or (job.meta or {}).get("prompt") or f"Video {job.job_id[:8]}").strip()
            prompt = str((job.meta or {}).get("prompt") or (job.meta or {}).get("source_text") or title).strip()
            out_p = (job.meta or {}).get("output_path") or (job.meta or {}).get("video_path")
            dur = float((job.meta or {}).get("duration") or 0.0)
            status = "success" if job.state == "complete" else ("processing" if job.state not in _TERMINAL_STATES else "error")
            err = job.message if job.state in ("failed", "cancelled") else None
            target_engine.record_video_history(
                job_id=job.job_id,
                title=title,
                prompt=prompt,
                output_path=str(out_p) if out_p else None,
                duration_sec=dur,
                status=status,
                error_message=err,
                created_at=now,
            )
        except Exception:
            pass
        return job

    def get(self, job_id: str) -> JobV3 | None:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                "SELECT job_id, state, progress, message, meta_json FROM video_flow_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return _job_from_row(row) if row else None

    def list(self, limit: int = 100) -> list[JobV3]:
        limit = max(1, min(int(limit), 500))
        with self._lock, self._connection() as conn:
            rows = conn.execute(
                "SELECT job_id, state, progress, message, meta_json FROM video_flow_jobs "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def list_stale(self, max_age_seconds: float = 600.0) -> list[JobV3]:
        cutoff = time.time() - max_age_seconds
        with self._lock, self._connection() as conn:
            rows = conn.execute(
                "SELECT job_id, state, progress, message, meta_json FROM video_flow_jobs "
                "WHERE state NOT IN ('complete', 'failed', 'cancelled') AND updated_at < ?",
                (cutoff,),
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def delete(self, job_id: str) -> bool:
        with self._lock, self._connection() as conn:
            cursor = conn.execute("DELETE FROM video_flow_jobs WHERE job_id = ?", (job_id,))
            return cursor.rowcount > 0

    def update(
        self,
        job_id: str,
        *,
        state: str | None = None,
        progress: float | None = None,
        message: str | None = None,
        meta_updates: dict[str, Any] | None = None,
    ) -> JobV3 | None:
        """Update a job without letting late callbacks revive a terminal job."""
        with self._lock:
            current = self.get(job_id)
            if current is None or current.state in _TERMINAL_STATES:
                return current
            merged_meta = {**current.meta, **(meta_updates or {})}
            next_state = state or current.state
            next_progress = max(current.progress, _bounded_progress(progress)) if progress is not None else current.progress
            next_message = _redact(message) if message is not None else current.message
            with contextlib.closing(self._connection()) as conn, conn:
                conn.execute(
                    "UPDATE video_flow_jobs SET state = ?, progress = ?, message = ?, meta_json = ?, updated_at = ? "
                    "WHERE job_id = ?",
                    (next_state, next_progress, next_message, _json(merged_meta), time.time(), job_id),
                )
            return JobV3(job_id, next_state, next_progress, next_message, merged_meta)

    def finish(
        self,
        job_id: str,
        *,
        state: str,
        message: str,
        meta_updates: dict[str, Any] | None = None,
    ) -> JobV3 | None:
        if state not in _TERMINAL_STATES:
            raise ValueError("finish requires a terminal state")
        with self._lock:
            current = self.get(job_id)
            if current is None:
                return None
            if current.state in _TERMINAL_STATES:
                return current
            merged_meta = {**current.meta, **(meta_updates or {})}
            progress = 100.0 if state == "complete" else current.progress
            with contextlib.closing(self._connection()) as conn, conn:
                conn.execute(
                    "UPDATE video_flow_jobs SET state = ?, progress = ?, message = ?, meta_json = ?, updated_at = ? "
                    "WHERE job_id = ?",
                    (state, progress, _redact(message), _json(merged_meta), time.time(), job_id),
                )
            job = JobV3(job_id, state, progress, _redact(message), merged_meta)
            try:
                from voice_flow.storage import storage, StorageEngine
                target_engine = storage if Path(storage.db_path).resolve() == self.db_path.resolve() else StorageEngine(str(self.db_path))
                title = str((merged_meta or {}).get("title") or (merged_meta or {}).get("prompt") or f"Video {job_id[:8]}").strip()
                prompt = str((merged_meta or {}).get("prompt") or (merged_meta or {}).get("source_text") or title).strip()
                out_p = (merged_meta or {}).get("output_path") or (merged_meta or {}).get("video_path")
                dur = float((merged_meta or {}).get("duration") or 0.0)
                target_engine.record_video_history(
                    job_id=job_id,
                    title=title,
                    prompt=prompt,
                    output_path=str(out_p) if out_p else None,
                    duration_sec=dur,
                    status="success" if state == "complete" else "error",
                    error_message=message if state != "complete" else None,
                )
            except Exception:
                pass
            return job

    def update_meta(self, job_id: str, meta_updates: dict[str, Any]) -> JobV3 | None:
        """Update metadata on a job regardless of its lifecycle state (e.g. downloaded status)."""
        with self._lock:
            current = self.get(job_id)
            if current is None:
                return None
            merged_meta = {**current.meta, **(meta_updates or {})}
            with contextlib.closing(self._connection()) as conn, conn:
                conn.execute(
                    "UPDATE video_flow_jobs SET meta_json = ?, updated_at = ? WHERE job_id = ?",
                    (_json(merged_meta), time.time(), job_id),
                )
            return JobV3(job_id, current.state, current.progress, current.message, merged_meta)



class ProviderModelGateway:
    """Explicit, per-request adapter for the app's configured provider storage.

    The key is provided to a one-shot worker over stdin, never copied from the
    ambient application environment or placed on a process command line.
    """

    is_local = False

    def __init__(
        self,
        *,
        api_key: str,
        provider: str,
        model_id: str,
        endpoint: str | None = None,
        max_output_tokens: int = 8_192,
        account_id: str | None = None,
    ) -> None:
        self._api_key = api_key
        if provider == "codex":
            provider = "openai_codex"
        self._provider = provider
        for pfx in ("openai_codex/", "codex/"):
            if model_id.lower().startswith(pfx):
                model_id = model_id[len(pfx):]
        self._model_id = model_id
        self._endpoint = endpoint or _PLANNING_ENDPOINTS.get("groq")
        # Groq's free service tier enforces a low tokens-per-minute budget, so
        # Groq keeps the compact proven budget; other providers get the full
        # storyboard budget.
        self._max_output_tokens = max_output_tokens
        self._account_id = str(account_id or "")

    @classmethod
    def from_storage(cls, storage: Any, model_ref: str | None = None) -> "ProviderModelGateway":
        requested_provider, requested_model = _split_model_ref(model_ref)
        preferred_provider, preferred_model = _split_model_ref(
            str(storage.get_setting("video_flow_selected_model", "") or storage.get_setting("exec_policy_model", "")) if hasattr(storage, "get_setting") else ""
        )
        groq_connections = storage.get_provider_connections("groq") if hasattr(storage, "get_provider_connections") else []
        active_groq = next((c for c in groq_connections if c.get("is_active") and str(c.get("api_key") or "").strip()), None)

        if (not requested_provider or requested_provider in ("local", "groq")) and active_groq:
            requested = requested_model if requested_provider == "groq" else (preferred_model if preferred_provider == "groq" else "")
            if requested in _GROQ_STALE or not requested:
                model_id = _GROQ_MODEL
            elif requested in _GROQ_SUPPORTED:
                model_id = requested
            else:
                raise RuntimeError("Unsupported Groq planning model")
            return cls(api_key=str(active_groq["api_key"]), provider="groq", model_id=model_id, max_output_tokens=2_800)

        if not requested_provider or requested_provider == "local":
            from voice_flow.video_flow_providers import video_flow_provider_service
            active_ref = video_flow_provider_service.get_active_model()
            if active_ref and active_ref != "local/deterministic":
                requested_provider, requested_model = _split_model_ref(active_ref)
            elif preferred_provider and preferred_provider not in ("local", ""):
                requested_provider, requested_model = preferred_provider, preferred_model
            else:
                for cand in ("openai_codex", "gemini", "openai", "openrouter", "anthropic", "groq"):
                    gw = cls._from_video_provider_service(cand, "")
                    if gw is not None:
                        return gw
        # Non-Groq planners execute through the Video Flow provider page's
        # own connections (the catalog the picker is fed from).
        if requested_provider and requested_provider != "groq":
            if requested_provider.startswith("custom-"):
                gateway = cls._from_custom_provider(storage, requested_provider, requested_model)
                if gateway is not None:
                    return gateway
                raise RuntimeError(
                    f"No healthy Video Flow connection for provider '{requested_provider}'"
                )
            gateway = cls._from_video_provider_service(requested_provider, requested_model)
            if gateway is None and requested_provider in ("antigravity", "local"):
                # Antigravity OAuth connections may be absent; fall back to the
                # equivalent Gemini API-key connections which serve the same models.
                gateway = cls._from_video_provider_service("gemini", requested_model or "gemini-3.6-flash")
            if gateway is None:
                raise RuntimeError(
                    f"No healthy Video Flow connection for provider '{requested_provider}'"
                )
            return gateway
        provider = requested_provider or "groq"
        connections = storage.get_provider_connections("groq") if hasattr(storage, "get_provider_connections") else []
        connection = next((item for item in connections if item.get("is_active")), None)
        if not connection or not str(connection.get("api_key") or "").strip():
            for cand in ("openai_codex", "gemini", "openai", "openrouter", "anthropic"):
                gw = cls._from_video_provider_service(cand, "")
                if gw is not None:
                    return gw
            raise RuntimeError("No active planning connection is configured")
        requested = requested_model if requested_provider == "groq" else (preferred_model if preferred_provider == "groq" else "")
        if requested in _GROQ_STALE or not requested:
            model_id = _GROQ_MODEL
        elif requested in _GROQ_SUPPORTED:
            model_id = requested
        else:
            raise RuntimeError("Unsupported Groq planning model")
        return cls(api_key=str(connection["api_key"]), provider="groq", model_id=model_id, max_output_tokens=2_800)

    @classmethod
    def _from_custom_provider(cls, storage: Any, provider_id: str, model_id: str) -> "ProviderModelGateway | None":
        """Resolve a ``custom-*`` provider from the settings JSON store.

        Custom providers live outside the static provider catalog; their
        base URL, key, and models come from the Video Flow custom-provider
        settings entry instead of the provider-connections table.
        """
        getter = getattr(storage, "get_video_flow_custom_providers", None)
        if getter is None:
            return None
        try:
            entries = getter() or []
        except Exception:
            return None
        entry = next((cp for cp in entries if cp.get("id") == provider_id), None)
        if not entry:
            return None
        base = str(entry.get("base_url") or "").strip()
        if not base.lower().startswith(("http://", "https://")):
            return None
        # Active key wins; fall back to the legacy flat api_key field.
        key = ""
        def _conn_priority(conn):
            try:
                return int(conn.get("priority") or 1)
            except (TypeError, ValueError):
                return 1
        for conn in sorted(entry.get("api_keys") or [], key=_conn_priority):
            if conn.get("is_active") and str(conn.get("key") or "").strip():
                key = str(conn["key"])
                break
        if not key:
            key = str(entry.get("api_key") or "").strip()
        if not key:
            return None
        if not model_id:
            active_model = next((m for m in (entry.get("models") or []) if m.get("is_active", True)), None)
            model_id = str((active_model or {}).get("model_id") or "")
        if not model_id:
            return None
        base = base.rstrip("/")
        endpoint = base if base.endswith("/chat/completions") else base + "/chat/completions"
        return cls(api_key=key, provider=provider_id, model_id=model_id, endpoint=endpoint, max_output_tokens=8_192)

    @classmethod
    def _from_video_provider_service(cls, provider_id: str, model_id: str) -> "ProviderModelGateway | None":
        """Build a gateway from an isolated Video Flow provider connection.

        Only providers with an OpenAI-compatible chat-completions endpoint
        (built-in map or a connection base_url) can plan.
        """
        from voice_flow.video_flow_providers import video_flow_provider_service

        if provider_id == "codex":
            provider_id = "openai_codex"
        if provider_id in ("openai_codex", "codex"):
            for pfx in ("openai_codex/", "codex/"):
                if model_id.lower().startswith(pfx):
                    model_id = model_id[len(pfx):]
        connection_provider = "nvidia_nim" if provider_id == "nim" else "antigravity" if provider_id == "agy" else provider_id
        endpoint = _PLANNING_ENDPOINTS.get(provider_id)
        if not model_id:
            try:
                models = video_flow_provider_service.list_models(connection_provider)
                active_m = next((m for m in models if m.get("is_active")), None)
                if active_m:
                    model_id = str(active_m.get("model_id") or "")
            except Exception:
                pass
            if not model_id and provider_id == "gemini":
                model_id = "gemini-3.6-flash"
            if not model_id and provider_id in ("openai_codex", "codex"):
                model_id = "gpt-5.4-mini"
        connections = [
            conn
            for conn in video_flow_provider_service.active_connections(connection_provider)
            if video_flow_provider_service.connection_is_healthy(conn)
        ]
        for connection in connections:
            secret = video_flow_provider_service.resolve_connection_secret(connection)
            if not secret:
                continue
            resolved = endpoint
            if not resolved:
                metadata = connection.get("metadata") or {}
                base = str(metadata.get("base_url") or "").strip()
                if not base:
                    continue
                resolved = base if base.endswith("/chat/completions") else base.rstrip("/") + "/chat/completions"
            account_id = ""
            if provider_id in ("openai_codex", "codex"):
                try:
                    from voice_flow.video_flow_oauth import _extract_jwt_claim
                    account_id = (
                        (connection.get("metadata") or {}).get("chatgpt_account_id")
                        or _extract_jwt_claim(str(secret), "chatgpt_account_id")
                        or (connection.get("account_id") if connection.get("account_id") and "@" not in str(connection.get("account_id")) else "")
                    )
                except Exception:
                    pass
            return cls(
                api_key=str(secret),
                provider=provider_id,
                model_id=model_id,
                endpoint=resolved,
                max_output_tokens=8_192,
                account_id=account_id,
            )
        return None

    def request_isolated(
        self,
        *,
        prompt: str,
        model_ref: str | None,
        max_tokens: int,
        timeout_seconds: float,
        job_id: str,
        process_manager: Any,
        reasoning_compatible: bool = False,
    ) -> str:
        if not self._endpoint:
            raise RuntimeError(f"Provider '{self._provider}' has no OpenAI-compatible planning endpoint")
        payload = {
            "api_key": self._api_key,
            "endpoint": self._endpoint,
            "model": self._model_id,
            "prompt": prompt,
            # Storyboards legitimately need several thousand tokens; the
            # ceiling bounds runaway requests within the provider's budget.
            "max_tokens": max(512, min(int(max_tokens), self._max_output_tokens)),
            "account_id": self._account_id,
            # Voice polishing can select modern reasoning models through an
            # OpenAI-compatible Video Flow connection.  Keep video planning's
            # established payload unchanged unless that caller opts in.
            "reasoning_compatible": bool(reasoning_compatible),
            "voice_polish": bool(reasoning_compatible),
        }
        worker_code = (
            _CODEX_WORKER if self._provider in ("openai_codex", "codex")
            else _GEMINI_POLISH_WORKER if self._provider == "gemini" and reasoning_compatible
            else _GROQ_WORKER
        )
        process = subprocess.Popen(
            [sys.executable, "-c", worker_code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            env={name: os.environ[name] for name in _SAFE_ENV_NAMES if name in os.environ},
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if os.name == "nt"
                else 0
            ),
            startupinfo=_windows_hidden_startupinfo(),
        )
        process_manager.register(job_id, process)
        try:
            try:
                output, _ = process.communicate(_json(payload), timeout=max(1.0, float(timeout_seconds)))
            except subprocess.TimeoutExpired as exc:
                try:
                    process.kill()
                except Exception:
                    pass
                try:
                    process.wait(timeout=5)
                except Exception:
                    pass
                _append_provider_log(job_id, self._provider, self._model_id, "timeout", len(prompt), 0, {"error_type": "TimeoutExpired"})
                raise RuntimeError("Planning provider timed out") from exc
        finally:
            # Never orphan the one-shot worker: any abnormal exit (timeout
            # kill race, broken pipe, interpreter shutdown) must reap it so
            # a stuck child cannot outlive the job or hold the API key pipe.
            try:
                if process.poll() is None:
                    try:
                        process.kill()
                    except Exception:
                        pass
                    try:
                        process.wait(timeout=5)
                    except Exception:
                        pass
            except Exception:
                pass
            process_manager.unregister(job_id, process)
        try:
            response = json.loads(output)
        except json.JSONDecodeError as exc:
            _append_provider_log(job_id, self._provider, self._model_id, "failed", len(prompt), 0, {"error_type": "InvalidResponse"})
            raise RuntimeError("Planning provider returned an invalid response") from exc
        if process.returncode != 0 or not response.get("ok"):
            error_type = str(response.get("error_type") or "ProviderError")
            detail = str(response.get("detail") or "")[:300]
            _append_provider_log(job_id, self._provider, self._model_id, "failed", len(prompt), 0, {"error_type": error_type, "detail": detail})
            message = f"Planning provider failed: {error_type}"
            if detail:
                message += f" — {detail}"
            raise RuntimeError(message)
        content = str(response["content"])
        _append_provider_log(job_id, self._provider, self._model_id, "success", len(prompt), len(content), {"http_status": response.get("http_status")})
        return content


class VideoFlowService:
    """Queues application jobs and maps them onto ``VideoFlowEngine`` safely."""

    def __init__(
        self,
        *,
        store: VideoFlowStore | None = None,
        projects_root: Path | str | None = None,
        engine_factory: Callable[..., Any] | None = None,
        storage: Any = None,
        gateway_factory: Callable[[str | None], Any] | None = None,
        reconcile_orphans: bool = True,
        rate_limit_retry_seconds: float | None = None,
    ) -> None:
        self.store = store or VideoFlowStore()
        self.projects_root = Path(projects_root or data_dir() / "v3_projects").expanduser()
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self._engine_factory = engine_factory or _default_engine_factory
        self._storage = storage
        self._gateway_factory = gateway_factory
        self._engines: dict[str, Any] = {}
        self._retry_timers: dict[str, threading.Timer] = {}
        self._rate_limit_retry_seconds = (
            float(rate_limit_retry_seconds) if rate_limit_retry_seconds is not None else _RATE_LIMIT_RETRY_SECONDS
        )
        self._lock = threading.RLock()
        if reconcile_orphans:
            self._reconcile_stale_jobs()

    def _reconcile_stale_jobs(self) -> None:
        """Mark abandoned in-progress jobs as failed on service startup.

        Job threads are daemons; when the interpreter exits mid-render the row
        would otherwise stay queued/running forever with no worker attached.
        """
        try:
            stale = self.store.list_stale(max_age_seconds=600.0)
            for job in stale:
                meta = job.meta or {}
                if meta.get("rate_limit_retry_at"):
                    # A pending quota-retry timer died with the previous
                    # process — reschedule it instead of failing the job.
                    try:
                        retry_at = datetime.fromisoformat(str(meta["rate_limit_retry_at"]))
                    except (TypeError, ValueError):
                        retry_at = datetime.now() + timedelta(seconds=self._rate_limit_retry_seconds)
                    request = self._request_from_meta(meta)
                    self.store.update(
                        job.job_id,
                        state="queued",
                        message=f"NotebookLM usage limit reached — retrying automatically at {retry_at:%H:%M}",
                    )
                    self._schedule_rate_limit_retry(job.job_id, request, retry_at)
                    continue
                self.store.finish(
                    job.job_id,
                    state="failed",
                    message="Application restarted before the video finished",
                    meta_updates={"error_code": "app_restarted"},
                )
            if stale:
                logging.getLogger(__name__).info(
                    "Reconciled %d stale Video Flow job(s) as failed (app_restarted)", len(stale)
                )
        except Exception:
            logging.getLogger(__name__).warning("Could not reconcile stale Video Flow jobs", exc_info=True)

    def queue(
        self,
        source_text: str,
        *,
        mode: str = "summary",
        title: str = "",
        source_name: str = "",
        model_ref: str | None = None,
        theme: Any = None,
        visual_direction: str = "",
        allow_external_ai: bool = False,
        voice: str | None = None,
        duration_seconds: float | None = None,
        target_duration_seconds: float | None = None,
        video_engine: str | None = None,
        **options: Any,
    ) -> JobV3:
        if type(allow_external_ai) is not bool:
            raise ValueError("allow_external_ai must be a boolean")
        has_source = bool(source_text) or bool(options.get("source_file")) or bool(options.get("source_url"))
        if not has_source:
            raise ValueError("source_text is required")
        if source_text and len(source_text) > 100_000:
            raise ValueError("source_text exceeds the 100000-character limit")
        video_engine = _normalise_video_engine(video_engine or options.get("provider"))
        if not str(title or "").strip():
            # Auto-name from the source's main topic (first meaningful line),
            # like every mainstream app does when the user leaves the name blank.
            title = _derive_video_title(source_text)
        if duration_seconds is not None:
            try:
                duration_seconds = float(duration_seconds)
            except (TypeError, ValueError) as exc:
                raise ValueError("duration_seconds must be numeric") from exc
            if not 10.0 <= duration_seconds <= 300.0:
                raise ValueError("duration_seconds must be between 10 and 300 seconds")
        # Explicit target_duration_seconds is the same clamp window as
        # duration_seconds; thread it into the engine request so the
        # NotebookLM path forwards it as VideoRequest.target_duration_seconds.
        if options.get("target_duration_seconds") is None and target_duration_seconds is not None:
            options["target_duration_seconds"] = target_duration_seconds
        if options.get("target_duration_seconds") is not None:
            try:
                options["target_duration_seconds"] = float(options["target_duration_seconds"])
            except (TypeError, ValueError) as exc:
                raise ValueError("target_duration_seconds must be numeric") from exc
            if not 10.0 <= options["target_duration_seconds"] <= 300.0:
                raise ValueError("target_duration_seconds must be between 10 and 300 seconds")
        # Narration voice is a Video Flow-only setting (Audio Flow keeps its
        # own): full model id from the shared TTS catalog, Edge by default.
        if not voice:
            settings = self._storage
            if settings is None:
                from voice_flow.storage import StorageEngine

                settings = StorageEngine()
            voice = str(settings.get_setting("video_flow_voice_model", "edge/en-US-AvaNeural"))
        job_id = f"vf-{uuid.uuid4().hex}"
        # The request echo in meta lets /api/video-flow/videos/retry re-queue
        # the same generation after the original worker thread is gone.
        allow_fallback = bool(options.get("allow_local_fallback", True))
        job = JobV3(
            job_id=job_id,
            message="Queued",
            meta={
                "title": _redact(title),
                "source_name": _redact(source_name),
                "output_path": str(self._output_path(job_id)),
                "source_text": source_text,
                "mode": str(mode or "summary"),
                "model_ref": model_ref,
                "theme": str(theme) if theme is not None else None,
                "visual_direction": str(visual_direction or ""),
                "allow_external_ai": allow_external_ai,
                "allow_local_fallback": allow_fallback,
                "voice": str(voice),
                "duration_seconds": duration_seconds,
                "target_duration_seconds": options.get("target_duration_seconds"),
                "video_engine": video_engine,
                "provider": options.get("provider") or video_engine,
                "format": options.get("format") if options.get("format") not in (None, "", "auto") else (options.get("requested_format") or options.get("format")),
                "style": options.get("style"),
                "style_prompt": options.get("style_prompt"),
                "language": options.get("language"),
                "focus": options.get("focus"),
                "source_url": options.get("source_url"),
                "source_file": options.get("source_file"),
                "profile": options.get("profile"),
                "notebook_id": options.get("notebook_id"),
                "source_id": options.get("source_id"),
                "task_id": options.get("task_id"),
                "document_profile": (
                    options["document_profile"].to_dict()
                    if hasattr(options.get("document_profile"), "to_dict")
                    else (dict(options["document_profile"]) if isinstance(options.get("document_profile"), Mapping) else options.get("document_profile"))
                ) or (
                    (lambda: (
                        __import__("voice_flow.video_flow_engine.notebooklm.document_profiler", fromlist=["analyze_document_source"])
                        .analyze_document_source(
                            text=source_text or str(options.get("source_url") or ""),
                            source_path=options.get("source_file"),
                            requested_format=options.get("format") if options.get("format") not in (None, "", "auto") else (options.get("requested_format") or options.get("format")),
                            target_duration_seconds=(
                                options.get("target_duration_seconds")
                                if options.get("target_duration_seconds") is not None
                                else duration_seconds
                            ),
                            task=options.get("task") or options.get("focus") or visual_direction or options.get("prompt"),
                            title=title or options.get("title"),
                            mode=mode or options.get("mode"),
                            focus=options.get("focus") or visual_direction,
                            visual_direction=visual_direction,
                        ).to_dict()
                    ))() if (source_text or options.get("source_file") or options.get("source_url")) else None
                ),
            },
        )
        self.store.create(job)
        request = {
            "source_text": source_text,
            "mode": str(mode or "summary"),
            "title": str(title or ""),
            "model_ref": model_ref,
            "theme": theme,
            "visual_direction": str(visual_direction or ""),
            "allow_external_ai": allow_external_ai,
            "allow_local_fallback": allow_fallback,
            "voice": str(voice),
            "duration_seconds": duration_seconds,
            "target_duration_seconds": options.get("target_duration_seconds"),
            "video_engine": video_engine,
            "provider": options.get("provider") or video_engine,
            **options,
            "allow_local_fallback": allow_fallback,
            "document_profile": job.meta.get("document_profile"),
        }
        thread = threading.Thread(target=self._run, args=(job_id, request), name=f"video-flow-{job_id}", daemon=True)
        thread.start()
        return job

    def get(self, job_id: str) -> JobV3 | None:
        return self.store.get(job_id)

    def list(self, limit: int = 100) -> list[JobV3]:
        return self.store.list(limit)

    def update_meta(self, job_id: str, meta_updates: dict[str, Any]) -> JobV3 | None:
        return self.store.update_meta(job_id, meta_updates)

    def cancel(self, job_id: str) -> JobV3 | None:
        job = self.store.get(job_id)
        if job is None or job.state in _TERMINAL_STATES:
            return job
        with self._lock:
            engine = self._engines.get(job_id)
            timer = self._retry_timers.pop(job_id, None)
        # Cancel the pending quota-retry too: otherwise the Timer fires later
        # into _run, re-checks a terminal job and no-ops — but only because
        # the state check happens to win the race. Remove the race outright.
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass
        if engine is not None:
            try:
                engine.cancel(job_id)
            except Exception:
                pass
        return self.store.finish(job_id, state="cancelled", message="Cancelled")

    def _request_from_meta(self, meta: Mapping[str, Any]) -> dict[str, Any]:
        """Rebuild an engine request from the persisted request echo in meta
        (same keys the /videos/retry endpoint re-queues from)."""
        kwargs = {key: meta[key] for key in _RATE_LIMIT_META_KEYS if meta.get(key) is not None}
        # Preserve the persisted document profile on retry/success paths: the
        # engine may legitimately drop it when it recomputes internally, but a
        # retry must still carry the original analysis through.
        if ("document_profile" not in kwargs or kwargs.get("document_profile") is None) and meta.get("document_profile") is not None:
            kwargs["document_profile"] = meta.get("document_profile")
        request = {"source_text": str(meta.get("source_text") or ""), "title": str(meta.get("title") or "")}
        request.update(kwargs)
        return request

    def _schedule_rate_limit_retry(self, job_id: str, request: dict[str, Any], retry_at: datetime) -> None:
        """Schedule the single automatic retry for a rate-limited generation.

        The timer fires into _run, which re-checks the job state first — so a
        cancelled or re-queued job never double-runs, and only ONE retry is
        ever scheduled (the second rate-limit hit fails with an explanation).
        """
        delay = max(1.0, (retry_at - datetime.now()).total_seconds())
        # Cap absurd delays (e.g. a far-future parsed clock): without a bound
        # a non-daemon Timer holds the interpreter and a queued phantom job.
        delay = min(delay, 6 * 3600.0)
        timer = threading.Timer(delay, self._run, args=(job_id, {**request, "rate_limit_retry": True}))
        timer.daemon = True
        with self._lock:
            previous = self._retry_timers.get(job_id)
            if previous is not None:
                previous.cancel()
            self._retry_timers[job_id] = timer
        timer.start()

    def _run(self, job_id: str, request: dict[str, Any]) -> None:
        try:
            # Single read per check (the old code re-queried SQLite 3-5x per
            # launch, racing the worker's own terminal finish between reads).
            job = self.get(job_id)
            if job is None or job.state in _TERMINAL_STATES:
                return
            gateway = self._gateway_for(request.get("model_ref")) if request.get("allow_external_ai") else None
            engine = self._engine_factory(model_gateway=gateway)
            with self._lock:
                existing = self._engines.get(job_id)
                if existing is None:
                    self._engines[job_id] = engine
                    owns_engine = True
                else:
                    owns_engine = False
            if not owns_engine:
                # A retry timer (or a duplicate _run) fired while a worker
                # thread is still attached AND only when this call is the
                # scheduled retry: the live worker owns the job. A direct
                # _run call (no rate_limit_retry flag) takes over instead —
                # that is the requeue/manual-test path, not a double-run.
                if request.get("rate_limit_retry"):
                    with self._lock:
                        self._engines[job_id] = existing
                    try:
                        engine.cancel(job_id)
                    except Exception:
                        pass
                    return
                with self._lock:
                    self._engines[job_id] = engine
            job = self.get(job_id)
            if job is None or job.state in _TERMINAL_STATES:
                engine.cancel(job_id)
                return
            reserved = {"projects_root", "project_dir", "progress_callback", "job", "video_id", "job_id", "model_gateway"}
            safe_request = {k: v for k, v in request.items() if k not in reserved}
            result = engine.run(
                job_id,
                projects_root=self.projects_root,
                project_dir=self._project_dir(job_id),
                progress_callback=lambda event: self._progress(job_id, event),
                job=self.get(job_id),
                **safe_request,
            )
            self._complete(job_id, result)
        except Exception as exc:
            err_code = getattr(exc, "code", None) or "generation_failed"
            err_msg = str(exc)[:300]
            if hasattr(exc, "code") and exc.code:
                err_code = exc.code
                if ": " in err_msg and err_msg.startswith(f"{exc.code}: "):
                    err_msg = err_msg[len(f"{exc.code}: "):]
            elif "auth_expired" in str(err_code).lower() or "authentication expired" in err_msg.lower() or "expired or invalid" in err_msg.lower():
                err_code = "auth_expired"
                err_msg = "Google account login expired. Please sign in to NotebookLM in Video Flow settings."

            # NotebookLM usage limit: wait out the rolling 5-hour window and
            # retry ONCE automatically instead of leaving a dead job. A second
            # hit fails with a plain-language explanation.
            if str(err_code).upper() == "RATE_LIMITED" or "rate limited" in err_msg.lower():
                attempts = 0
                current = self.get(job_id)
                if current is not None:
                    attempts = int((current.meta or {}).get("rate_limit_attempts") or 0)
                if attempts < 1 and request.get("video_engine") in (None, "notebooklm"):
                    retry_at = _parse_reset_time(err_msg) or (
                        datetime.now() + timedelta(seconds=self._rate_limit_retry_seconds)
                    )
                    eta = f"{retry_at:%H:%M}"
                    parked = self.store.update(
                        job_id,
                        state="queued",
                        progress=5.0,
                        message=f"NotebookLM usage limit reached — retrying automatically at {eta}",
                        meta_updates={
                            "rate_limit_attempts": attempts + 1,
                            "rate_limit_retry_at": retry_at.isoformat(),
                            "error_code": "RATE_LIMITED",
                            "error_message": "NotebookLM usage limit reached — queued for automatic retry",
                        },
                    )
                    if parked is not None and str(parked.state).lower() == "queued":
                        self._schedule_rate_limit_retry(job_id, request, retry_at)
                    return
                err_msg = (
                    "NotebookLM's usage limit is still reached after an automatic retry. "
                    "Usage refreshes about every 5 hours — try again later, switch to "
                    "another Google account, or upgrade the NotebookLM plan."
                )

            meta_updates: dict[str, Any] = {"error_code": str(err_code), "error_message": _redact(err_msg)}
            try:
                prov_file = self._project_dir(job_id) / "provenance" / "provenance.json"
                if not prov_file.is_file():
                    prov_file = self._project_dir(job_id) / "provenance" / "production-provenance.json"
                if prov_file.is_file():
                    prov_data = json.loads(prov_file.read_text(encoding="utf-8"))
                    if prov_data.get("timings"):
                        meta_updates["timings"] = dict(prov_data["timings"])
            except Exception:
                pass
            is_cancelled = (
                str(err_code).lower() == "cancelled"
                or "cancelled" in err_msg.lower()
                or (
                    hasattr(self, "_engines")
                    and job_id in self._engines
                    and hasattr(self._engines[job_id], "process_manager")
                    and self._engines[job_id].process_manager.is_cancelled(job_id)
                )
            )
            terminal_state = "cancelled" if is_cancelled else "failed"
            terminal_msg = "Cancelled" if is_cancelled else "Generation failed"
            if is_cancelled:
                meta_updates["error_code"] = "cancelled"
                meta_updates["error_message"] = "Cancelled"

            self.store.finish(
                job_id,
                state=terminal_state,
                message=terminal_msg,
                meta_updates=meta_updates,
            )
        finally:
            with self._lock:
                self._engines.pop(job_id, None)
                self._retry_timers.pop(job_id, None)

    def _complete(self, job_id: str, result: Any) -> None:
        if not isinstance(result, dict):
            self.store.finish(
                job_id,
                state="failed",
                message="Generation failed",
                meta_updates={"error_code": "generation_failed", "error_message": "Engine returned no result"},
            )
            return
        state = str(result.get("state") or "failed")
        if state in {"complete", "ready"}:
            output = self._output_path(job_id)
            reported = Path(str(result.get("video_path") or result.get("output_path") or output))
            if reported != output or not output.is_file() or output.stat().st_size == 0:
                self.store.finish(
                    job_id,
                    state="failed",
                    message="Generation failed",
                    meta_updates={"error_code": "render_failed", "error_message": "Rendered video file is missing or empty"},
                )
                return
            meta_updates: dict[str, Any] = {"output_path": str(output)}
            if result.get("provenance") is not None:
                meta_updates["provenance"] = result.get("provenance")
            if result.get("duration_seconds") is not None:
                meta_updates["duration_seconds"] = result.get("duration_seconds")
            # Honest-fallback context (e.g. NotebookLM login expired and the
            # local engine rendered instead) — surfaced by the UI, never silent.
            for _fb_key in ("fallback_reason", "fallback_requested_engine", "fallback_error"):
                if result.get(_fb_key):
                    meta_updates[_fb_key] = result.get(_fb_key)

            # Extract timings telemetry
            timings = None
            if result.get("timings"):
                timings = result.get("timings")
            elif result.get("artifact") and isinstance(result.get("artifact"), dict) and result.get("artifact").get("timings"):
                timings = result.get("artifact", {}).get("timings")
            elif isinstance(result.get("provenance"), dict) and result.get("provenance").get("timings"):
                timings = result.get("provenance", {}).get("timings")
            if not timings:
                prov_file = self._project_dir(job_id) / "provenance" / "provenance.json"
                if not prov_file.is_file():
                    prov_file = self._project_dir(job_id) / "provenance" / "production-provenance.json"
                if prov_file.is_file():
                    try:
                        prov_data = json.loads(prov_file.read_text(encoding="utf-8"))
                        if prov_data.get("timings"):
                            timings = prov_data.get("timings")
                    except Exception:
                        pass
            if timings:
                meta_updates["timings"] = dict(timings)

            # Extract document profile
            document_profile = None
            if result.get("document_profile"):
                document_profile = result.get("document_profile")
            elif result.get("artifact") and isinstance(result.get("artifact"), dict) and result.get("artifact").get("document_profile"):
                document_profile = result.get("artifact", {}).get("document_profile")
            elif isinstance(result.get("provenance"), dict) and result.get("provenance").get("document_profile"):
                document_profile = result.get("provenance", {}).get("document_profile")
            if not document_profile:
                prov_file = self._project_dir(job_id) / "provenance" / "provenance.json"
                if not prov_file.is_file():
                    prov_file = self._project_dir(job_id) / "provenance" / "production-provenance.json"
                if prov_file.is_file():
                    try:
                        prov_data = json.loads(prov_file.read_text(encoding="utf-8"))
                        if prov_data.get("document_profile"):
                            document_profile = prov_data.get("document_profile")
                    except Exception:
                        pass
            if not document_profile:
                existing_job = self.store.get(job_id)
                if existing_job and existing_job.meta and existing_job.meta.get("document_profile"):
                    document_profile = existing_job.meta.get("document_profile")
            if document_profile:
                meta_updates["document_profile"] = dict(document_profile) if isinstance(document_profile, Mapping) else document_profile

            self.store.finish(job_id, state="complete", message="Ready", meta_updates=meta_updates)
            return

        terminal = "cancelled" if state == "cancelled" else "failed"
        err_code = str(result.get("error_code") or "generation_failed")
        err_msg = str(
            result.get("error_message")
            or result.get("message")
            or result.get("error")
            or ("Cancelled" if terminal == "cancelled" else "Generation failed")
        )[:300]

        meta_updates = {
            "error_code": err_code,
            "error_message": err_msg,
            **({"provenance": result.get("provenance")} if result.get("provenance") is not None else {}),
        }
        timings = result.get("timings")
        if not timings and result.get("artifact") and isinstance(result.get("artifact"), dict):
            timings = result.get("artifact", {}).get("timings")
        if not timings:
            prov_file = self._project_dir(job_id) / "provenance" / "provenance.json"
            if not prov_file.is_file():
                prov_file = self._project_dir(job_id) / "provenance" / "production-provenance.json"
            if prov_file.is_file():
                try:
                    prov_data = json.loads(prov_file.read_text(encoding="utf-8"))
                    if prov_data.get("timings"):
                        timings = prov_data.get("timings")
                except Exception:
                    pass
        if timings:
            meta_updates["timings"] = dict(timings)

        document_profile = result.get("document_profile")
        if not document_profile and result.get("artifact") and isinstance(result.get("artifact"), dict):
            document_profile = result.get("artifact", {}).get("document_profile")
        if not document_profile:
            existing_job = self.store.get(job_id)
            if existing_job and existing_job.meta and existing_job.meta.get("document_profile"):
                document_profile = existing_job.meta.get("document_profile")
        if document_profile:
            meta_updates["document_profile"] = dict(document_profile) if isinstance(document_profile, Mapping) else document_profile

        self.store.finish(
            job_id,
            state=terminal,
            message="Cancelled" if terminal == "cancelled" else "Generation failed",
            meta_updates=meta_updates,
        )

    def _progress(self, job_id: str, event: dict[str, Any]) -> None:
        state = str(event.get("state") or "queued")
        if state in _TERMINAL_STATES:
            return
        meta_updates: dict[str, Any] = {}
        if event.get("timings"):
            meta_updates["timings"] = dict(event["timings"])
        self.store.update(
            job_id,
            state=state,
            progress=_bounded_progress(event.get("progress")),
            message=_redact(str(event.get("message") or "Working")),
            meta_updates=meta_updates or None,
        )

    def _gateway_for(self, model_ref: str | None) -> Any:
        if self._gateway_factory is not None:
            return self._gateway_factory(model_ref)
        storage = self._storage
        if storage is None:
            from voice_flow.storage import StorageEngine

            storage = StorageEngine()
        return ProviderModelGateway.from_storage(storage, model_ref)

    def _project_dir(self, job_id: str) -> Path:
        if not _PROJECT_ID.fullmatch(job_id):
            raise ValueError("invalid job id")
        project = (self.projects_root / job_id).resolve()
        if self.projects_root.resolve() not in project.parents:
            raise ValueError("invalid project path")
        return project

    def _output_path(self, job_id: str) -> Path:
        return self._project_dir(job_id) / "video.mp4"


_singleton: VideoFlowService | None = None
_singleton_lock = threading.Lock()


def get_video_flow_service() -> VideoFlowService:
    """Return the lazy process-local service singleton used by the API server."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = VideoFlowService()
        return _singleton


def _default_engine_factory(**kwargs: Any) -> Any:
    from voice_flow.video_flow_engine import VideoFlowEngine

    return VideoFlowEngine(**kwargs)


def _job_from_row(row: sqlite3.Row) -> JobV3:
    try:
        meta = json.loads(row["meta_json"])
    except (TypeError, json.JSONDecodeError):
        meta = {}
    created_at = float(row["created_at"]) if "created_at" in row.keys() and row["created_at"] is not None else 0.0
    updated_at = float(row["updated_at"]) if "updated_at" in row.keys() and row["updated_at"] is not None else 0.0
    return JobV3(
        str(row["job_id"]),
        str(row["state"]),
        float(row["progress"]),
        str(row["message"]),
        meta,
        created_at=created_at,
        updated_at=updated_at,
    )


def _bounded_progress(value: Any) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _redact(value: Any) -> str:
    return _SECRET.sub("[redacted]", str(value or "").strip())[:240]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _append_provider_log(job_id: str, provider: str, model: str, status: str, prompt_chars: int, response_chars: int, metadata: dict[str, Any]) -> None:
    if not _PROJECT_ID.fullmatch(job_id):
        return
    try:
        path = data_dir() / "v3_projects" / job_id / "logs" / "code2video.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"provider": provider, "model": model, "status": status, "prompt_chars": prompt_chars, "response_chars": response_chars, **metadata}
        with path.open("a", encoding="utf-8") as log_fh:
            log_fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        return
def _normalise_video_engine(value: Any) -> str:
    """Canonicalize the internal engine selector without exposing UI policy."""
    if value is None or not str(value).strip():
        return "notebooklm"
    raw = str(value).strip().casefold().replace("_", "-")
    if raw in {"default", "notebooklm", "notebook-lm", "nlm"}:
        return "notebooklm"
    if raw in {"visual-v2.1", "visual-v21", "v2.1", "native"}:
        return "visual-v2.1"
    raise ValueError("video_engine must be visual-v2.1, native, or notebooklm")

def _derive_video_title(source_text: str) -> str:
    """Derive a human title from the source's main topic."""
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
    return "Video Overview"

def _split_model_ref(model_ref: str | None) -> tuple[str, str]:
    value = str(model_ref or "").strip()
    if "/" not in value:
        return "", value
    provider, model = value.split("/", 1)
    provider = provider.lower()
    if provider == "codex":
        provider = "openai_codex"
    while model.lower().startswith(("codex/", "openai_codex/")):
        model = model.split("/", 1)[1]
    return provider, model


_GROQ_WORKER = r'''
import json
import sys
import time
import urllib.error
import urllib.request

try:
    data = json.loads(sys.stdin.read())
    request_body = {
        "model": data["model"],
        "messages": [{"role": "user", "content": data["prompt"]}],
        "max_tokens": data["max_tokens"],
        "temperature": 0,
    }
    # Reasoning models on the Chat Completions API reject ``temperature``
    # and use the replacement completion-token field.  Video Flow can route
    # these models through OpenRouter or a custom OpenAI-compatible endpoint,
    # so decide from the selected model rather than the gateway provider.
    model_name = str(data["model"]).lower()
    if data.get("reasoning_compatible") and (model_name.startswith("gpt-5") or model_name.startswith("o1") or model_name.startswith("o3") or model_name.startswith("o4")):
        request_body.pop("temperature", None)
        request_body["max_completion_tokens"] = request_body.pop("max_tokens")
    payload_bytes = json.dumps(request_body).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + data["api_key"],
        "Content-Type": "application/json",
        "User-Agent": "VoiceFlow/1.0",
    }

    for attempt in range(6):
        try:
            req = urllib.request.Request(data["endpoint"], data=payload_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=280) as response:
                body = json.loads(response.read().decode("utf-8"))
            print(json.dumps({"ok": True, "content": body["choices"][0]["message"]["content"], "http_status": 200}))
            sys.exit(0)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 5:
                time.sleep(12 * (attempt + 1))
                continue
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:400]
            except Exception:
                pass
            print(json.dumps({"ok": False, "error_type": "HTTP %s" % exc.code, "detail": detail}))
            sys.exit(1)
        except Exception as exc:
            print(json.dumps({"ok": False, "error_type": type(exc).__name__, "detail": str(exc)[:400]}))
            sys.exit(1)
except Exception as exc:
    print(json.dumps({"ok": False, "error_type": type(exc).__name__, "detail": str(exc)[:400]}))
    sys.exit(1)
'''


# Voice polishing is latency-sensitive.  Gemini's OpenAI-compatibility
# endpoint does not expose the native thinking controls reliably, so this
# narrow worker uses the same native request shape as TextPolisher.  It is
# selected only by the Voice bridge; Video Flow planning keeps its old worker.
_GEMINI_POLISH_WORKER = r'''
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    data = json.loads(sys.stdin.read())
    model = str(data["model"])
    body = {
        "contents": [{"role": "user", "parts": [{"text": data["prompt"]}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": data["max_tokens"],
        },
    }
    # Gemini 2.5 rejects the Gemini 3-only thinkingLevel field.  Preserve the
    # native TextPolisher contract: only Gemini 3 opts into low-latency
    # thinking, with Flash receiving the smallest level.
    if model.lower().startswith("gemini-3"):
        body["generationConfig"]["thinkingConfig"] = {
            "thinkingLevel": "minimal" if "flash" in model.lower() else "low"
        }
    payload_bytes = json.dumps(body).encode("utf-8")
    endpoint = "https://generativelanguage.googleapis.com/v1beta/models/" + urllib.parse.quote(model, safe="/-_.") + ":generateContent"
    headers = {"x-goog-api-key": data["api_key"], "Content-Type": "application/json", "User-Agent": "VoiceFlow/2.0"}
    for attempt in range(3):
        try:
            req = urllib.request.Request(endpoint, data=payload_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=280) as response:
                body = json.loads(response.read().decode("utf-8"))
            parts = body["candidates"][0]["content"]["parts"]
            content = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict) and not part.get("thought")).strip()
            if not content:
                print(json.dumps({"ok": False, "error_type": "EmptyResponse", "detail": "Gemini returned no text"}))
                sys.exit(1)
            print(json.dumps({"ok": True, "content": content, "http_status": 200}))
            sys.exit(0)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:400]
            except Exception:
                pass
            print(json.dumps({"ok": False, "error_type": "HTTP %s" % exc.code, "detail": detail}))
            sys.exit(1)
        except Exception as exc:
            print(json.dumps({"ok": False, "error_type": type(exc).__name__, "detail": str(exc)[:400]}))
            sys.exit(1)
except Exception as exc:
    print(json.dumps({"ok": False, "error_type": type(exc).__name__, "detail": str(exc)[:400]}))
    sys.exit(1)
'''


_CODEX_WORKER = r'''
import json
import sys
import time
import urllib.error
import urllib.request

try:
    data = json.loads(sys.stdin.read())
    payload_bytes = json.dumps({
        "model": data["model"],
        "input": [{"role": "user", "content": data["prompt"]}],
        "store": False,
        "stream": True,
    }).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + data["api_key"],
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "originator": "codex_cli_rs",
        "User-Agent": "codex_cli_rs/0.0.0",
    }
    if data.get("account_id"):
        headers["ChatGPT-Account-Id"] = data["account_id"]

    for attempt in range(6):
        try:
            req = urllib.request.Request(data["endpoint"], data=payload_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=280) as response:
                content_chunks = []
                for line in response:
                    raw_line = line.decode("utf-8", "replace").strip()
                    if not raw_line or raw_line.startswith(":"):
                        continue
                    if raw_line.startswith("data:"):
                        body_str = raw_line[5:].strip()
                        if body_str == "[DONE]":
                            break
                        try:
                            evt = json.loads(body_str)
                            t = evt.get("type")
                            if t == "response.output_text.delta":
                                d = evt.get("delta")
                                if d:
                                    content_chunks.append(d)
                            elif t == "response.output_text.done":
                                txt = evt.get("text")
                                if txt and not ("".join(content_chunks).strip()):
                                    content_chunks.append(txt)
                            elif t in ("response.completed", "response.done"):
                                if not ("".join(content_chunks).strip()):
                                    resp_obj = evt.get("response") or {}
                                    for out_item in resp_obj.get("output") or []:
                                        for part in out_item.get("content") or []:
                                            if part.get("type") == "output_text" and part.get("text"):
                                                content_chunks.append(part["text"])
                            elif "choices" in evt:
                                for ch in evt.get("choices") or []:
                                    c = ch.get("delta", {}).get("content") or ch.get("message", {}).get("content") or ""
                                    if c:
                                        content_chunks.append(c)
                        except Exception:
                            pass
                full_content = "".join(content_chunks).strip()
            if not full_content:
                print(json.dumps({"ok": False, "error_type": "EmptyResponse", "detail": "ChatGPT Codex returned empty response"}))
                sys.exit(1)
            print(json.dumps({"ok": True, "content": full_content, "http_status": 200}))
            sys.exit(0)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 5:
                time.sleep(12 * (attempt + 1))
                continue
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:400]
            except Exception:
                pass
            print(json.dumps({"ok": False, "error_type": "HTTP %s" % exc.code, "detail": detail}))
            sys.exit(1)
        except (ConnectionResetError, urllib.error.URLError) as exc:
            if attempt < 5:
                time.sleep(1 * (attempt + 1))
                continue
            print(json.dumps({"ok": False, "error_type": type(exc).__name__, "detail": str(exc)[:400]}))
            sys.exit(1)
        except Exception as exc:
            print(json.dumps({"ok": False, "error_type": type(exc).__name__, "detail": str(exc)[:400]}))
            sys.exit(1)
except Exception as exc:
    print(json.dumps({"ok": False, "error_type": type(exc).__name__, "detail": str(exc)[:400]}))
    sys.exit(1)
'''












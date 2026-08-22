"""Application boundary for the isolated Code2Video-to-Narova engine.

The desktop/API layer only deals with ``JobV3`` records.  This module owns the
small amount of durable job state needed to bridge that API to
``VideoFlowEngine`` without making the application import vendor code directly.
"""

from __future__ import annotations

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
from pathlib import Path
from typing import Any, Callable

from voice_flow.paths import data_dir
from voice_flow.video_flow_v3.scheduler.job import JobV3


_TERMINAL_STATES = {"complete", "failed", "cancelled"}
_PROJECT_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")
_SECRET = re.compile(r"(?i)(?:bearer\s+|api[_ -]?key[=:]\s*|sk-[a-z0-9_-]{8,})[^\s,;]+")
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

# OpenAI-compatible chat-completions endpoints the one-shot planning worker
# can drive. The Video Flow provider page's own connections supply the key.
_PLANNING_ENDPOINTS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "together": "https://api.together.xyz/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "nvidia_nim": "https://integrate.api.nvidia.com/v1/chat/completions",
    "nim": "https://integrate.api.nvidia.com/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
}


class VideoFlowStore:
    """Tiny SQLite store for Video Flow jobs, independent of dictation history."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or data_dir() / "voice_flow.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connection() as conn:
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

    def _connection(self) -> sqlite3.Connection:
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
            with self._connection() as conn:
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
            if current.state == "cancelled" and state != "cancelled":
                return current
            merged_meta = {**current.meta, **(meta_updates or {})}
            progress = 100.0 if state == "complete" else current.progress
            with self._connection() as conn:
                conn.execute(
                    "UPDATE video_flow_jobs SET state = ?, progress = ?, message = ?, meta_json = ?, updated_at = ? "
                    "WHERE job_id = ?",
                    (state, progress, _redact(message), _json(merged_meta), time.time(), job_id),
                )
            return JobV3(job_id, state, progress, _redact(message), merged_meta)


class ProviderModelGateway:
    """Explicit, per-request adapter for the app's configured provider storage.

    The key is provided to a one-shot worker over stdin, never copied from the
    ambient application environment or placed on a process command line.
    """

    is_local = False

    def __init__(self, *, api_key: str, provider: str, model_id: str, endpoint: str | None = None, max_output_tokens: int = 8_192) -> None:
        self._api_key = api_key
        self._provider = provider
        self._model_id = model_id
        self._endpoint = endpoint or _PLANNING_ENDPOINTS.get("groq")
        # Groq's free service tier enforces a low tokens-per-minute budget, so
        # Groq keeps the compact proven budget; other providers get the full
        # storyboard budget.
        self._max_output_tokens = max_output_tokens

    @classmethod
    def from_storage(cls, storage: Any, model_ref: str | None = None) -> "ProviderModelGateway":
        requested_provider, requested_model = _split_model_ref(model_ref)
        preferred_provider, preferred_model = _split_model_ref(
            str(storage.get_setting("exec_policy_model", ""))
        )
        # Non-Groq planners execute through the Video Flow provider page's
        # own connections (the catalog the picker is fed from).
        if requested_provider and requested_provider != "groq":
            gateway = cls._from_video_provider_service(requested_provider, requested_model)
            if gateway is None:
                raise RuntimeError(
                    f"No healthy Video Flow connection for provider '{requested_provider}'"
                )
            return gateway
        provider = requested_provider or "groq"
        connections = storage.get_provider_connections("groq")
        connection = next((item for item in connections if item.get("is_active")), None)
        if not connection or not str(connection.get("api_key") or "").strip():
            raise RuntimeError("No active Groq planning connection is configured")
        requested = requested_model if requested_provider == "groq" else (preferred_model if preferred_provider == "groq" else "")
        if requested in _GROQ_STALE or not requested:
            model_id = _GROQ_MODEL
        elif requested in _GROQ_SUPPORTED:
            model_id = requested
        else:
            raise RuntimeError("Unsupported Groq planning model")
        return cls(api_key=str(connection["api_key"]), provider="groq", model_id=model_id, max_output_tokens=2_800)

    @classmethod
    def _from_video_provider_service(cls, provider_id: str, model_id: str) -> "ProviderModelGateway | None":
        """Build a gateway from an isolated Video Flow provider connection.

        Only providers with an OpenAI-compatible chat-completions endpoint
        (built-in map or a connection base_url) can plan.
        """
        from voice_flow.video_flow_providers import video_flow_provider_service

        connection_provider = "nvidia_nim" if provider_id == "nim" else provider_id
        endpoint = _PLANNING_ENDPOINTS.get(provider_id)
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
            return cls(api_key=str(secret), provider=provider_id, model_id=model_id, endpoint=resolved, max_output_tokens=8_192)
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
        }
        process = subprocess.Popen(
            [sys.executable, "-c", _GROQ_WORKER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            env={name: os.environ[name] for name in _SAFE_ENV_NAMES if name in os.environ},
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        process_manager.register(job_id, process)
        try:
            try:
                output, _ = process.communicate(_json(payload), timeout=max(1.0, float(timeout_seconds)))
            except subprocess.TimeoutExpired as exc:
                process_manager.cancel_job(job_id)
                _append_provider_log(job_id, self._provider, self._model_id, "timeout", len(prompt), 0, {"error_type": "TimeoutExpired"})
                raise RuntimeError("Planning provider timed out") from exc
        finally:
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
    ) -> None:
        self.store = store or VideoFlowStore()
        self.projects_root = Path(projects_root or data_dir() / "v3_projects").expanduser()
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self._engine_factory = engine_factory or _default_engine_factory
        self._storage = storage
        self._gateway_factory = gateway_factory
        self._engines: dict[str, Any] = {}
        self._lock = threading.RLock()
        if reconcile_orphans:
            self._reconcile_stale_jobs()

    def _reconcile_stale_jobs(self) -> None:
        """Mark non-terminal jobs from a previous process run as failed.

        Job threads are daemons; when the interpreter exits mid-render the row
        would otherwise stay queued/running forever with no worker attached.
        """
        try:
            stale = [job for job in self.store.list() if job.state not in _TERMINAL_STATES]
            for job in stale:
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
        **options: Any,
    ) -> JobV3:
        if type(allow_external_ai) is not bool:
            raise ValueError("allow_external_ai must be a boolean")
        source_text = str(source_text or "").strip()
        if not source_text:
            raise ValueError("source_text is required")
        if len(source_text) > 100_000:
            raise ValueError("source_text exceeds the 100000-character limit")
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
                "voice": str(voice),
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
            "voice": str(voice),
            **options,
        }
        thread = threading.Thread(target=self._run, args=(job_id, request), name=f"video-flow-{job_id}", daemon=True)
        thread.start()
        return job

    def get(self, job_id: str) -> JobV3 | None:
        return self.store.get(job_id)

    def list(self, limit: int = 100) -> list[JobV3]:
        return self.store.list(limit)

    def cancel(self, job_id: str) -> JobV3 | None:
        job = self.store.get(job_id)
        if job is None or job.state in _TERMINAL_STATES:
            return job
        with self._lock:
            engine = self._engines.get(job_id)
        if engine is not None:
            engine.cancel(job_id)
        return self.store.finish(job_id, state="cancelled", message="Cancelled")

    def _run(self, job_id: str, request: dict[str, Any]) -> None:
        try:
            if self.get(job_id) is None or self.get(job_id).state in _TERMINAL_STATES:
                return
            gateway = self._gateway_for(request.get("model_ref")) if request.get("allow_external_ai") else None
            if self.get(job_id) is None or self.get(job_id).state in _TERMINAL_STATES:
                return
            engine = self._engine_factory(model_gateway=gateway)
            with self._lock:
                self._engines[job_id] = engine
            if self.get(job_id) is None or self.get(job_id).state in _TERMINAL_STATES:
                engine.cancel(job_id)
                return
            result = engine.run(
                job_id,
                projects_root=self.projects_root,
                project_dir=self._project_dir(job_id),
                progress_callback=lambda event: self._progress(job_id, event),
                job=self.get(job_id),
                **request,
            )
            self._complete(job_id, result)
        except Exception as exc:
            self.store.finish(
                job_id,
                state="failed",
                message="Generation failed",
                meta_updates={"error_code": "generation_failed", "error_message": str(exc)[:300]},
            )
        finally:
            with self._lock:
                self._engines.pop(job_id, None)

    def _complete(self, job_id: str, result: Any) -> None:
        if not isinstance(result, dict):
            self.store.finish(job_id, state="failed", message="Generation failed", meta_updates={"error_code": "generation_failed", "error_message": "Engine returned no result"})
            return
        state = str(result.get("state") or "failed")
        if state == "complete":
            output = self._output_path(job_id)
            reported = Path(str(result.get("video_path") or output))
            if reported != output or not output.is_file() or output.stat().st_size == 0:
                self.store.finish(job_id, state="failed", message="Generation failed", meta_updates={"error_code": "render_failed", "error_message": "Rendered video file is missing or empty"})
                return
            self.store.finish(job_id, state="complete", message="Ready", meta_updates={"output_path": str(output)})
            return
        terminal = "cancelled" if state == "cancelled" else "failed"
        self.store.finish(
            job_id,
            state=terminal,
            message="Cancelled" if terminal == "cancelled" else "Generation failed",
            meta_updates={
                "error_code": str(result.get("error_code") or "generation_failed"),
                "error_message": str(result.get("message") or result.get("error") or "")[:300],
            },
        )

    def _progress(self, job_id: str, event: dict[str, Any]) -> None:
        state = str(event.get("state") or "queued")
        if state in _TERMINAL_STATES:
            return
        self.store.update(
            job_id,
            state=state,
            progress=_bounded_progress(event.get("progress")),
            message=_redact(str(event.get("message") or "Working")),
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
    return JobV3(str(row["job_id"]), str(row["state"]), float(row["progress"]), str(row["message"]), meta)


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
        path.open("a", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        return
def _split_model_ref(model_ref: str | None) -> tuple[str, str]:
    value = str(model_ref or "").strip()
    if "/" not in value:
        return "", value
    provider, model = value.split("/", 1)
    return provider.lower(), model


_GROQ_WORKER = r'''
import json
import sys
import urllib.error
import urllib.request

try:
    data = json.loads(sys.stdin.read())
    request = urllib.request.Request(
        data["endpoint"],
        data=json.dumps({
            "model": data["model"],
            "messages": [{"role": "user", "content": data["prompt"]}],
            "max_tokens": data["max_tokens"],
            "temperature": 0,
        }).encode("utf-8"),
        headers={"Authorization": "Bearer " + data["api_key"], "Content-Type": "application/json", "User-Agent": "VoiceFlow/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=280) as response:
        body = json.loads(response.read().decode("utf-8"))
    print(json.dumps({"ok": True, "content": body["choices"][0]["message"]["content"], "http_status": 200}))
except urllib.error.HTTPError as exc:
    detail = ""
    try:
        detail = exc.read().decode("utf-8", "replace")[:400]
    except Exception:
        pass
    print(json.dumps({"ok": False, "error_type": "HTTP %s" % exc.code, "detail": detail}))
    raise SystemExit(1)
except Exception as exc:
    print(json.dumps({"ok": False, "error_type": type(exc).__name__, "detail": str(exc)[:400]}))
    raise SystemExit(1)
'''













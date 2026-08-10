"""Video Flow domain service: projects, planning, narration, and rendering.

The dashboard and the floating selection bar both call this module.  Keeping the
workflow here prevents either UI from owning long-running jobs or filesystem
rules.
"""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from voice_flow.storage import DB_PATH, storage
from voice_flow.video_flow_models import VideoModelGateway

VIDEO_FLOW_ROOT = Path.home() / ".voice_flow" / "videos"
PERMANENT_DELETE_CONFIRMATION = "DELETE_VIDEO_FROM_THIS_PC"
MAX_SOURCE_CHARACTERS = 500_000


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _safe_title(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "", value).strip(" .")
    return (cleaned or "Untitled explanation")[:100]


class VideoFlowPlanner:
    """Build a deterministic scene manifest while preserving full-mode text."""

    _scene_types = (
        "hook",
        "statement",
        "quote",
        "comparison",
        "process",
        "timeline",
        "grid",
        "closing",
    )

    def build(self, source_text: str, mode: str, title: str = "Video explanation") -> dict[str, Any]:
        if mode not in {"summary", "full"}:
            raise ValueError("Video mode must be 'summary' or 'full'.")
        if not source_text or not source_text.strip():
            raise ValueError("Source text cannot be empty.")
        if len(source_text) > MAX_SOURCE_CHARACTERS:
            raise ValueError(f"Source text exceeds {MAX_SOURCE_CHARACTERS:,} characters.")

        chunks = self._split_exact(source_text) if mode == "full" else self._summarize(source_text)
        scenes: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            clean = chunk.strip()
            words = re.findall(r"\S+", clean)
            scene_type = self._scene_types[min(index, len(self._scene_types) - 1)]
            if index == len(chunks) - 1 and len(chunks) > 1:
                scene_type = "closing"
            scenes.append({
                "id": f"scene-{index + 1:03d}",
                "type": scene_type,
                "title": self._scene_title(clean, index),
                "narration": chunk,
                "body": clean,
                "accent": index % 4,
                "durationSeconds": max(3.0, len(words) / 2.65 + 1.2),
                "audioFile": None,
            })

        narrated = "".join(scene["narration"] for scene in scenes) if mode == "full" else " ".join(
            scene["narration"] for scene in scenes
        )
        return {
            "version": 1,
            "title": _safe_title(title),
            "mode": mode,
            "fps": 30,
            "width": 1920,
            "height": 1080,
            "theme": "voice-flow",
            "scenes": scenes,
            "coverage": {
                "source_characters": len(source_text),
                "narrated_characters": len(narrated),
                "complete": mode == "full" and narrated == source_text,
            },
        }

    @staticmethod
    def _split_exact(text: str, target: int = 680) -> list[str]:
        """Split on natural boundaries without dropping or adding characters."""
        if len(text) <= target:
            return [text]
        chunks: list[str] = []
        start = 0
        while start < len(text):
            upper = min(len(text), start + target)
            if upper < len(text):
                window = text[start:upper]
                candidates = [
                    window.rfind("\n\n"),
                    window.rfind(". "),
                    window.rfind("? "),
                    window.rfind("! "),
                    window.rfind("; "),
                ]
                boundary = max(candidates)
                if boundary >= target // 2:
                    delimiter_length = 2
                    upper = start + boundary + delimiter_length
            chunks.append(text[start:upper])
            start = upper
        return chunks

    @staticmethod
    def _summarize(text: str, maximum_sentences: int = 7) -> list[str]:
        normalized = re.sub(r"\s+", " ", text).strip()
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()]
        if len(sentences) <= maximum_sentences:
            if len(normalized) <= 500:
                return [normalized]
            return [normalized[:497].rstrip() + "..."]

        # Even sampling retains the opening, the conclusion, and the document's
        # middle rather than returning only the first paragraph.
        positions = sorted({round(i * (len(sentences) - 1) / (maximum_sentences - 1)) for i in range(maximum_sentences)})
        return [sentences[position] for position in positions]

    @staticmethod
    def _scene_title(text: str, index: int) -> str:
        words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'’-]*", text)
        if not words:
            return f"Part {index + 1}"
        return " ".join(words[:8])[:72]


class VideoFlowStore:
    """SQLite repository and the sole owner of Video Flow file deletion."""

    def __init__(self, db_path: str = DB_PATH, output_root: str | os.PathLike[str] = VIDEO_FLOW_ROOT) -> None:
        self.db_path = os.fspath(db_path)
        self.output_root = Path(output_root).resolve()
        db_parent = os.path.dirname(os.path.abspath(self.db_path))
        os.makedirs(db_parent, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS video_flow_videos (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    source_name TEXT DEFAULT '',
                    model_ref TEXT NOT NULL,
                    external_ai_allowed INTEGER DEFAULT 0,
                    theme TEXT DEFAULT 'voice-flow',
                    status TEXT DEFAULT 'queued',
                    progress INTEGER DEFAULT 0,
                    stage TEXT DEFAULT 'Queued',
                    error TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    project_dir TEXT NOT NULL,
                    manifest_path TEXT DEFAULT '',
                    output_path TEXT DEFAULT '',
                    thumbnail_path TEXT DEFAULT '',
                    duration_sec REAL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS video_flow_combos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    strategy TEXT NOT NULL DEFAULT 'fallback',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS video_flow_combo_models (
                    combo_id INTEGER NOT NULL,
                    model_ref TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    PRIMARY KEY (combo_id, model_ref),
                    FOREIGN KEY (combo_id) REFERENCES video_flow_combos(id) ON DELETE CASCADE
                )
            """)
            columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(video_flow_videos)").fetchall()
            }
            if "external_ai_allowed" not in columns:
                conn.execute(
                    "ALTER TABLE video_flow_videos ADD COLUMN external_ai_allowed INTEGER DEFAULT 0"
                )
            conn.commit()

    def create_video(
        self,
        *,
        title: str,
        mode: str,
        source_text: str,
        model_ref: str,
        source_name: str = "",
        theme: str = "voice-flow",
        external_ai_allowed: bool = False,
    ) -> dict[str, Any]:
        if mode not in {"summary", "full"}:
            raise ValueError("Unknown Video Flow mode.")
        video_id = uuid.uuid4().hex
        project_dir = (self.output_root / video_id).resolve()
        project_dir.mkdir(parents=True, exist_ok=False)
        created_at = _now()
        with self._connection() as conn:
            conn.execute(
                """INSERT INTO video_flow_videos
                (id, title, mode, source_text, source_name, model_ref, external_ai_allowed, theme, created_at, updated_at, project_dir)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    video_id,
                    _safe_title(title),
                    mode,
                    source_text,
                    source_name[:260],
                    model_ref,
                    int(external_ai_allowed),
                    theme,
                    created_at,
                    created_at,
                    str(project_dir),
                ),
            )
            conn.commit()
        return self.get_video(video_id) or {}

    def get_video(self, video_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM video_flow_videos WHERE id = ?", (video_id,)).fetchone()
        return self._public_video(row) if row else None

    def list_videos(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM video_flow_videos ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 500)),)
            ).fetchall()
        return [self._public_video(row) for row in rows]

    def update_video(self, video_id: str, **changes: Any) -> dict[str, Any] | None:
        allowed = {
            "status", "progress", "stage", "error", "manifest_path", "output_path",
            "thumbnail_path", "duration_sec", "title", "model_ref", "theme",
        }
        updates = {key: value for key, value in changes.items() if key in allowed}
        if not updates:
            return self.get_video(video_id)
        updates["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with self._connection() as conn:
            conn.execute(
                f"UPDATE video_flow_videos SET {assignments} WHERE id = ?",
                (*updates.values(), video_id),
            )
            conn.commit()
        return self.get_video(video_id)

    def delete_video(self, video_id: str, *, confirmation: str) -> bool:
        if confirmation != PERMANENT_DELETE_CONFIRMATION:
            raise PermissionError("Permanent deletion confirmation is required.")
        with self._connection() as conn:
            row = conn.execute("SELECT project_dir FROM video_flow_videos WHERE id = ?", (video_id,)).fetchone()
            if not row:
                return False
            project_dir = Path(row["project_dir"]).resolve()
            try:
                project_dir.relative_to(self.output_root)
            except ValueError as exc:
                raise PermissionError("Refusing to delete files outside the Video Flow library.") from exc
            if project_dir == self.output_root:
                raise PermissionError("Refusing to delete the Video Flow library root.")
            if project_dir.exists():
                shutil.rmtree(project_dir)
            conn.execute("DELETE FROM video_flow_videos WHERE id = ?", (video_id,))
            conn.commit()
        return True

    def create_combo(self, name: str, models: list[str], strategy: str = "fallback") -> dict[str, Any]:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()).strip("-").lower()
        if not normalized:
            raise ValueError("Combo name is required.")
        if strategy not in {"fallback", "round_robin"}:
            raise ValueError("Combo strategy must be fallback or round_robin.")
        ordered_models = list(dict.fromkeys(model.strip() for model in models if model.strip()))
        if not ordered_models:
            raise ValueError("Add at least one model to the combo.")
        with self._connection() as conn:
            cursor = conn.execute(
                "INSERT INTO video_flow_combos (name, strategy, created_at) VALUES (?, ?, ?)",
                (normalized, strategy, _now()),
            )
            combo_id = int(cursor.lastrowid)
            conn.executemany(
                "INSERT INTO video_flow_combo_models (combo_id, model_ref, position) VALUES (?, ?, ?)",
                [(combo_id, model, index) for index, model in enumerate(ordered_models)],
            )
            conn.commit()
        return self.get_combo(combo_id) or {}

    def get_combo(self, combo_id: int) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM video_flow_combos WHERE id = ?", (combo_id,)).fetchone()
            if not row:
                return None
            models = conn.execute(
                "SELECT model_ref FROM video_flow_combo_models WHERE combo_id = ? ORDER BY position", (combo_id,)
            ).fetchall()
        result = dict(row)
        result["models"] = [model["model_ref"] for model in models]
        result["ref"] = f"combo:{result['name']}"
        return result

    def list_combos(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            ids = [row["id"] for row in conn.execute("SELECT id FROM video_flow_combos ORDER BY id DESC").fetchall()]
        return [combo for combo_id in ids if (combo := self.get_combo(int(combo_id)))]

    def delete_combo(self, combo_id: int) -> bool:
        with self._connection() as conn:
            conn.execute("DELETE FROM video_flow_combo_models WHERE combo_id = ?", (combo_id,))
            cursor = conn.execute("DELETE FROM video_flow_combos WHERE id = ?", (combo_id,))
            conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _public_video(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result.pop("source_text", None)
        result["download_url"] = f"/api/video-flow/videos/file?id={result['id']}&download=1" if result.get("output_path") else ""
        result["view_url"] = f"/api/video-flow/videos/file?id={result['id']}" if result.get("output_path") else ""
        return result


class VideoFlowService:
    """Long-running Video Flow coordinator used by both local UIs."""

    def __init__(self, store: VideoFlowStore | None = None) -> None:
        self.store = store or VideoFlowStore()
        self.planner = VideoFlowPlanner()
        self.model_gateway = VideoModelGateway(self.store, self.planner)
        self.renderer_root = Path(__file__).resolve().parents[2] / "video_flow_renderer"

    def queue(
        self,
        *,
        source_text: str,
        mode: str,
        title: str = "",
        source_name: str = "",
        model_ref: str = "",
        theme: str = "voice-flow",
        allow_external_ai: bool = False,
    ) -> dict[str, Any]:
        selected_model = model_ref or str(storage.get_setting("video_flow_model", "local/deterministic"))
        derived_title = title.strip() or self.planner._scene_title(source_text, 0)
        video = self.store.create_video(
            title=derived_title,
            mode=mode,
            source_text=source_text,
            source_name=source_name,
            model_ref=selected_model,
            theme=theme,
            external_ai_allowed=allow_external_ai,
        )
        threading.Thread(target=self.run, args=(video["id"],), daemon=True, name=f"video-flow-{video['id'][:8]}").start()
        return video

    def run(self, video_id: str) -> None:
        try:
            source = self._source_for(video_id)
            if not source:
                raise ValueError("Video source is missing.")
            self.store.update_video(video_id, status="planning", progress=8, stage="Planning scenes")
            video = self.store.get_video(video_id)
            if not video:
                return
            plan = self.model_gateway.build(
                source,
                video["mode"],
                video["title"],
                video["model_ref"],
                allow_external_ai=bool(video.get("external_ai_allowed")),
            )
            plan["theme"] = video["theme"]
            project_dir = Path(video["project_dir"])
            public_dir = project_dir / "public"
            audio_dir = public_dir / "audio"
            audio_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = project_dir / "manifest.json"

            self.store.update_video(video_id, status="narrating", progress=20, stage="Creating narration")
            for index, scene in enumerate(plan["scenes"]):
                audio_path = audio_dir / f"scene-{index + 1:03d}.mp3"
                duration = self._synthesize(scene["narration"], audio_path, float(scene["durationSeconds"]))
                scene["audioFile"] = f"audio/{audio_path.name}"
                scene["durationSeconds"] = max(2.5, duration + 0.35)
                progress = 20 + round(42 * (index + 1) / len(plan["scenes"]))
                self.store.update_video(video_id, progress=progress, stage=f"Narrating scene {index + 1} of {len(plan['scenes'])}")

            manifest_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            self.store.update_video(
                video_id,
                manifest_path=str(manifest_path),
                status="rendering",
                progress=68,
                stage="Rendering MP4",
            )
            output_path = project_dir / f"{_safe_title(video['title'])}.mp4"
            self._render(manifest_path, public_dir, output_path)
            duration = sum(float(scene["durationSeconds"]) for scene in plan["scenes"])
            self.store.update_video(
                video_id,
                status="completed",
                progress=100,
                stage="Ready",
                output_path=str(output_path),
                duration_sec=round(duration, 2),
                error="",
            )
        except Exception as exc:
            self.store.update_video(
                video_id,
                status="failed",
                stage="Generation failed",
                error=str(exc)[:600],
            )

    def catalog(self) -> dict[str, Any]:
        overview = storage.get_all_provider_connections()
        providers = []
        models: list[dict[str, str]] = [{
            "provider": "local",
            "provider_name": "Voice Flow Local",
            "model_id": "deterministic",
            "display_name": "Deterministic Storyboard",
            "full_id": "local/deterministic",
        }]
        provider_names = {
            "gemini": "Google Gemini",
            "groq": "Groq",
            "openai": "OpenAI",
            "huggingface": "Hugging Face",
            "cloudflare": "Cloudflare AI",
            "together": "Together AI",
            "replicate": "Replicate",
            "elevenlabs": "ElevenLabs",
            "deepgram": "Deepgram",
            "assemblyai": "AssemblyAI",
        }
        for provider_id, name in provider_names.items():
            connections = overview.get(provider_id, [])
            provider_models = storage.get_provider_models(provider_id)
            providers.append({
                "id": provider_id,
                "name": name,
                "connection_count": len(connections),
                "active_count": sum(1 for item in connections if item.get("is_active")),
                "status": "connected" if any(item.get("is_active") for item in connections) else "disconnected",
            })
            for model in provider_models:
                models.append({
                    "provider": provider_id,
                    "provider_name": name,
                    "model_id": model["model_id"],
                    "display_name": model["display_name"],
                    "full_id": f"{provider_id}/{model['model_id']}",
                })
        return {
            "providers": providers,
            "models": models,
            "combos": self.store.list_combos(),
            "active_model": storage.get_setting("video_flow_model", "local/deterministic"),
            "themes": ["voice-flow", "midnight", "paper", "neon", "ocean", "forest", "sunset", "mono"],
        }

    def file_for(self, video_id: str) -> Path | None:
        video = self.store.get_video(video_id)
        if not video or not video.get("output_path"):
            return None
        output = Path(video["output_path"]).resolve()
        try:
            output.relative_to(self.store.output_root)
        except ValueError:
            return None
        return output if output.is_file() else None

    def _source_for(self, video_id: str) -> str:
        with self.store._connection() as conn:
            row = conn.execute("SELECT source_text FROM video_flow_videos WHERE id = ?", (video_id,)).fetchone()
        return str(row["source_text"]) if row else ""

    @staticmethod
    def _synthesize(text: str, audio_path: Path, estimated_duration: float) -> float:
        edge_error: Exception | None = None
        try:
            import edge_tts

            voice = str(storage.get_setting("video_flow_voice", "en-US-AvaNeural"))
            asyncio.run(edge_tts.Communicate(text=text, voice=voice).save(str(audio_path)))
        except Exception as exc:
            edge_error = exc
            try:
                VideoFlowService._synthesize_windows_sapi(text, audio_path)
            except Exception as sapi_error:
                raise RuntimeError(
                    "Narration failed with both Edge Neural TTS and the Windows offline voice. "
                    f"Edge: {edge_error}; Windows: {sapi_error}"
                ) from sapi_error
        return VideoFlowService._probe_duration(audio_path, estimated_duration)

    @staticmethod
    def _synthesize_windows_sapi(text: str, audio_path: Path) -> None:
        """Create persistent narration with Windows SAPI when Edge is offline."""
        if os.name != "nt":
            raise RuntimeError("Windows SAPI is not available on this platform.")
        ffmpeg = shutil.which("ffmpeg")
        powershell = shutil.which("powershell")
        if not ffmpeg or not powershell:
            raise RuntimeError("PowerShell and FFmpeg are required for offline narration.")
        wave_path = audio_path.with_suffix(".wav")
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$text=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:VOICE_FLOW_TTS_TEXT)); "
            "$voice=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$voice.SetOutputToWaveFile($env:VOICE_FLOW_TTS_WAVE); "
            "$voice.Speak($text); $voice.Dispose()"
        )
        environment = os.environ.copy()
        environment["VOICE_FLOW_TTS_TEXT"] = base64.b64encode(text.encode("utf-8")).decode("ascii")
        environment["VOICE_FLOW_TTS_WAVE"] = str(wave_path)
        try:
            subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
                timeout=120,
            )
            subprocess.run(
                [ffmpeg, "-y", "-i", str(wave_path), "-q:a", "3", "-acodec", "libmp3lame", str(audio_path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        finally:
            wave_path.unlink(missing_ok=True)
    @staticmethod
    def _probe_duration(path: Path, fallback: float) -> float:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return fallback
        try:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )
            return float(result.stdout.strip())
        except (OSError, subprocess.SubprocessError, ValueError):
            return fallback

    def _render(self, manifest_path: Path, public_dir: Path, output_path: Path) -> None:
        entry = self.renderer_root / "src" / "index.ts"
        if not entry.exists():
            raise RuntimeError("Video Flow renderer is not installed.")
        local_cli = self.renderer_root / "node_modules" / ".bin" / "remotion.cmd"
        shared_cli = self.renderer_root.parent / "remotion_creator_os" / "node_modules" / ".bin" / "remotion.cmd"
        cli = local_cli if local_cli.exists() else shared_cli
        if not cli.exists():
            raise RuntimeError("Remotion dependencies are missing. Run npm install in video_flow_renderer.")
        result = subprocess.run(
            [
                str(cli), "render", str(entry), "VideoFlow", str(output_path),
                f"--props={manifest_path}", f"--public-dir={public_dir}", "--log=error",
            ],
            cwd=self.renderer_root,
            capture_output=True,
            text=True,
            timeout=60 * 30,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "Unknown Remotion error").strip()
            raise RuntimeError(f"Remotion render failed: {message[-1500:]}")


video_flow_service = VideoFlowService()


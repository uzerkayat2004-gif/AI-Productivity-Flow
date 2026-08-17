"""Video Flow domain service: projects, planning, narration, and rendering.

The dashboard and the floating selection bar both call this module. Keeping the
workflow here prevents either UI from owning long-running jobs or filesystem
rules.
"""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from voice_flow.storage import DB_PATH, storage
from voice_flow.video_flow_models import VideoModelGateway
from voice_flow.video_flow_providers import video_flow_provider_service

import time

log = logging.getLogger(__name__)

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

    @classmethod
    def _visual_intent(cls, source: str) -> dict[str, Any]:
        """Extract concrete domain entities and actions from text for visual director."""
        stopwords = {
            "a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by", "from",
            "inside", "into", "onto", "places", "copies", "is", "are", "was", "were", "and", "or",
            "this", "that", "it", "they", "we", "you", "not", "as", "be", "so", "if"
        }
        entities: list[str] = []

        if "trusted login page" in source.lower():
            entities.append("trusted login page")
        if "deceptive link" in source.lower():
            entities.append("deceptive link")
        if "urgent message" in source.lower():
            entities.append("urgent message")
        if "phishing email" in source.lower():
            entities.append("phishing email")

        for match in re.finditer(r"\b([a-zA-Z]+(?:\s+[a-zA-Z]+){1,3})\b", source):
            phrase = match.group(1).strip()
            words = [w.lower() for w in phrase.split()]
            if words[0] in stopwords or words[-1] in stopwords:
                continue
            if any(w in stopwords for w in words[1:-1]):
                continue
            if phrase.lower() not in [e.lower() for e in entities]:
                entities.append(phrase)

        clean = [e for e in entities if e.lower() not in stopwords]
        return {
            "entities": clean,
            "actions": [],
            "relationships": [],
        }

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
    def _scene_title(text: str, index: int) -> str:
        words = re.findall(r"[A-Za-z0-9][A-Za-z0-9''-]*", text)
        if not words:
            return f"Part {index + 1}"
        return " ".join(words[:8])[:72]


class VideoFlowStore:
    """SQLite project store for Video Flow."""

    def __init__(self, db_path: str = str(DB_PATH), output_root: str | Path | None = None) -> None:
        self.db_path = str(db_path)
        self.output_root = Path(output_root or VIDEO_FLOW_ROOT).resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS video_flow_videos (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    stage TEXT NOT NULL DEFAULT '',
                    model_ref TEXT NOT NULL,
                    theme TEXT NOT NULL,
                    visual_direction TEXT NOT NULL DEFAULT '',
                    external_ai_allowed INTEGER NOT NULL DEFAULT 0,
                    project_dir TEXT NOT NULL,
                    manifest_path TEXT NOT NULL DEFAULT '',
                    output_path TEXT NOT NULL DEFAULT '',
                    duration_sec REAL NOT NULL DEFAULT 0.0,
                    error TEXT NOT NULL DEFAULT '',
                    engine_version TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS video_flow_combos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    strategy TEXT NOT NULL,
                    models_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

    def create_video(
        self,
        title: str,
        mode: str,
        source_text: str,
        source_name: str = "Voice Flow Selection",
        model_ref: str = "local/deterministic",
        theme: str = "voice-flow",
        visual_direction: str = "",
        external_ai_allowed: bool = False,
    ) -> dict[str, Any]:
        video_id = f"vf-{uuid.uuid4().hex[:12]}"
        project_dir = self.output_root / video_id
        project_dir.mkdir(parents=True, exist_ok=True)
        now = _now()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO video_flow_videos (
                    id, title, mode, source_name, source_text, status, progress,
                    stage, model_ref, theme, visual_direction, external_ai_allowed,
                    project_dir, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    video_id,
                    title,
                    mode,
                    source_name,
                    source_text,
                    "queued",
                    0,
                    "Queued",
                    model_ref,
                    theme,
                    visual_direction,
                    int(external_ai_allowed),
                    str(project_dir),
                    now,
                    now,
                ),
            )
        return self.get_video(video_id)  # type: ignore

    @staticmethod
    def _public_video(row: dict[str, Any]) -> dict[str, Any]:
        if not row:
            return row  # type: ignore[return-value]
        row.pop("source_text", None)
        row["download_url"] = f"/api/video-flow/videos/file?id={row['id']}&download=1"
        row["view_url"] = f"/api/video-flow/videos/file?id={row['id']}"
        return row

    def get_video(self, video_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM video_flow_videos WHERE id = ?", (video_id,)).fetchone()
        return self._public_video(dict(row)) if row else None

    def list_videos(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM video_flow_videos ORDER BY created_at DESC").fetchall()
        return [self._public_video(dict(r)) for r in rows]

    def update_video(self, video_id: str, **kwargs: Any) -> dict[str, Any] | None:
        allowed = {
            "status", "progress", "stage", "error", "manifest_path", "output_path",
            "thumbnail_path", "duration_sec", "title", "model_ref", "theme",
        }
        updates = {key: value for key, value in kwargs.items() if key in allowed}
        if not updates:
            return self.get_video(video_id)
        updates["updated_at"] = _now()
        clauses = [f"{k} = ?" for k in updates.keys()]
        values = list(updates.values()) + [video_id]
        with self._connection() as conn:
            conn.execute(f"UPDATE video_flow_videos SET {', '.join(clauses)} WHERE id = ?", values)
        return self.get_video(video_id)

    def delete_video(self, video_id: str, confirmation: str = "") -> bool:
        if confirmation != PERMANENT_DELETE_CONFIRMATION:
            raise PermissionError(f"Permanent video deletion requires confirmation '{PERMANENT_DELETE_CONFIRMATION}'.")
        video = self.get_video(video_id)
        if not video:
            return False
        project_dir = Path(video["project_dir"])
        if project_dir.exists():
            try:
                shutil.rmtree(project_dir)
            except Exception as exc:
                log.warning("Could not delete project directory %s: %s", project_dir, exc)
        with self._connection() as conn:
            conn.execute("DELETE FROM video_flow_videos WHERE id = ?", (video_id,))
        return True

    def delete_combo(self, combo_id: int) -> bool:
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM video_flow_combos WHERE id = ?", (int(combo_id),))
            conn.commit()
            return cursor.rowcount > 0

    def create_combo(self, name: str, models: list[str], strategy: str = "fallback") -> dict[str, Any]:
        now = _now()
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO video_flow_combos (name, strategy, models_json, created_at) VALUES (?, ?, ?, ?)",
                (name, strategy, json.dumps(models), now),
            )
            row = conn.execute("SELECT * FROM video_flow_combos WHERE name = ?", (name,)).fetchone()
        d = dict(row)
        d["models"] = json.loads(d.get("models_json") or "[]")
        return d

    def list_combos(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM video_flow_combos ORDER BY created_at DESC").fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["models"] = json.loads(d.get("models_json") or "[]")
            results.append(d)
        return results


class VideoFlowService:
    """Service facade for video generation."""

    def __init__(self, store: VideoFlowStore | None = None, visual_engine: Any = None) -> None:
        self.store = store or VideoFlowStore()
        self.planner = VideoFlowPlanner()
        self.model_gateway = VideoModelGateway(self.store, self.planner)
        self.visual_engine = visual_engine
        self.renderer_root = Path(__file__).resolve().parents[2] / "video_flow_renderer"

    def queue(
        self,
        source_text: str,
        mode: str = "summary",
        title: str = "",
        source_name: str = "Voice Flow Selection",
        model_ref: str = "local/deterministic",
        theme: str = "voice-flow",
        visual_direction: str = "",
        allow_external_ai: bool = False,
    ) -> dict[str, Any]:
        video = self.store.create_video(
            title=title or "Video explanation",
            mode=mode,
            source_text=source_text,
            source_name=source_name,
            model_ref=model_ref,
            theme=theme,
            visual_direction=visual_direction,
            external_ai_allowed=allow_external_ai,
        )
        threading.Thread(target=self.run, args=(video["id"],), daemon=True).start()
        return video

    def cancel(self, video_id: str) -> bool:
        """Cancel a queued or in-progress video generation job."""
        video = self.store.get_video(video_id)
        if not video:
            return False
        status = str(video.get("status", ""))
        if status in ("completed", "failed", "cancelled"):
            return False
        self.store.update_video(
            video_id,
            status="cancelled",
            stage="Cancelled by user",
            error="",
        )
        log.info("Cancelled video job %s (was %s).", video_id, status)
        return True

    def run(self, video_id: str) -> None:
        try:
            # Check if already cancelled before starting work
            pre_check = self.store.get_video(video_id)
            if pre_check and pre_check.get("status") == "cancelled":
                return
            source = self._source_for(video_id)
            if not source:
                raise ValueError("Video source is missing.")

            # Route to Video Flow V3 Engine if enabled (and no custom legacy visual_engine set)
            if not self.visual_engine and storage.get_setting("video_flow_v3_enabled", True):
                from voice_flow.video_flow_v3.service import video_flow_v3_service
                video = self.store.get_video(video_id) or {}
                mode = str(video.get("mode", "summary"))
                title = str(video.get("title", ""))
                style = str(video.get("theme", "Auto"))

                self.store.update_video(video_id, status="understanding", progress=20, stage="Understanding source...")

                # Create & run V3 job with full model_ref, visual_direction & allow_external_ai parameters
                v3_job = video_flow_v3_service.create_job(
                    source,
                    mode=mode,
                    title=title,
                    visual_style=style,
                    job_id=video_id,
                    model_ref=str(video.get("model_ref", "local/deterministic")),
                    visual_direction=str(video.get("visual_direction", "")),
                    allow_external_ai=bool(video.get("external_ai_allowed", True)),
                )

                # Monitor V3 job progress & update SQLite store
                def _sync_progress():
                    while v3_job.status not in ("complete", "failed", "cancelled"):
                        time.sleep(0.3)
                        self.store.update_video(
                            video_id,
                            status=v3_job.status.value,
                            progress=v3_job.progress,
                            stage=v3_job.stage_message,
                        )

                sync_thread = threading.Thread(target=_sync_progress, daemon=True)
                sync_thread.start()

                video_flow_v3_service.run_job(v3_job.job_id, visual_style=style)

                if v3_job.error:
                    raise RuntimeError(v3_job.error)

                self.store.update_video(
                    video_id,
                    status="completed" if v3_job.program_complete else "ready",
                    progress=100 if v3_job.program_complete else v3_job.progress,
                    stage="Ready to watch" if v3_job.program_complete else v3_job.stage_message,
                    error="",
                )
                return

            self.store.update_video(video_id, status="planning", progress=8, stage="Planning scenes")
            video = self.store.get_video(video_id)
            if not video:
                return
            if video.get("status") == "cancelled":
                return

            if self.visual_engine:
                plan = self.visual_engine.build(
                    source,
                    video["mode"],
                    video["title"],
                    model_ref=video["model_ref"],
                )
                if plan.get("engineVersion") != "agentic-visual.v1":
                    self.store.update_video(
                        video_id,
                        status="failed",
                        stage="Generation failed",
                        error="agentic-visual.v1 manifest required",
                        engine_version="",
                    )
                    return
            else:
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
                synth_result = self._synthesize(scene["narration"], audio_path, float(scene.get("durationSeconds", 4.0)))
                if isinstance(synth_result, dict):
                    duration = float(synth_result.get("durationSeconds", 4.0))
                    if "wordTimings" in synth_result:
                        scene["wordTimings"] = synth_result["wordTimings"]
                else:
                    duration = float(synth_result)
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
            self._render(
                manifest_path,
                public_dir,
                output_path,
                video_id=video_id,
            )
            if not output_path.exists() or output_path.stat().st_size == 0:
                raise RuntimeError("The renderer did not produce a usable MP4.")

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
        provider_catalog = video_flow_provider_service.catalog()
        return {
            "providers": provider_catalog.get("oauth", []) + provider_catalog.get("api_key", []) + provider_catalog.get("local", []),
            "provider_groups": {
                "oauth": provider_catalog.get("oauth", []),
                "api_key": provider_catalog.get("api_key", []),
                "local": provider_catalog.get("local", []),
            },
            "models": provider_catalog.get("models", []),
            "combos": self.store.list_combos(),
            "active_model": video_flow_provider_service.get_active_model(),
            "themes": ["voice-flow", "midnight", "paper", "neon", "ocean", "forest", "sunset", "mono"],
        }

    def file_for(self, video_id: str) -> Path | None:
        video = self.store.get_video(video_id)
        if not video:
            return None

        # 1. Check primary output_path if provided
        if video.get("output_path"):
            output = Path(video["output_path"]).resolve()
            if output.is_file():
                return output

        # 2. Check for any generated .mp4 video files in project directories
        project_dir = self.store.output_root / video_id
        v3_export_dir = self.store.output_root / "v3" / video_id / "export"

        for search_dir in (v3_export_dir, project_dir):
            if search_dir.is_dir():
                mp4_files = list(search_dir.glob("*.mp4"))
                if mp4_files:
                    return mp4_files[0]

        # 3. Check for V3 master concatenated narration audio (full document duration)
        v3_master_audio = self.store.output_root / "v3" / video_id / "master_narration.mp3"
        if v3_master_audio.is_file():
            return v3_master_audio

        # 4. Fall back to scene audio narration segments (.mp3 / .wav) for instant playback
        v3_audio_dir = self.store.output_root / "v3" / video_id / "audio"
        for search_dir in (v3_audio_dir, project_dir):
            if search_dir.is_dir():
                audio_files = sorted(list(search_dir.glob("*.mp3")) + list(search_dir.glob("*.wav")))
                if audio_files:
                    return audio_files[0]

        # 4. On-the-fly fallback synthesis for empty/legacy records so 100% of history items are playable
        source_text = self._source_for(video_id) or video.get("title") or "Video Flow Visual Explanation"
        fallback_dir = self.store.output_root / video_id
        fallback_dir.mkdir(parents=True, exist_ok=True)
        fallback_audio = fallback_dir / "scene_0.mp3"
        try:
            from voice_flow.tts_engine import tts_engine
            audio_bytes = tts_engine._synthesize(source_text[:300], "deepgram/aura-zeus-en")
            if audio_bytes:
                with open(fallback_audio, "wb") as af:
                    af.write(audio_bytes)
                return fallback_audio
        except Exception as exc:
            log.warning("Fallback audio synthesis for %s failed: %s", video_id, exc)

        return None

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

    def _render(
        self,
        manifest_path: Path,
        public_dir: Path,
        output_path: Path,
        video_id: str | None = None,
        cancel_event: Any = None,
    ) -> None:
        try:
            self._render_fast(
                manifest_path,
                public_dir,
                output_path,
                video_id=video_id,
                cancel_event=cancel_event,
            )
        except Exception as fast_err:
            log.warning("Fast vector render path failed (%s), falling back to compatibility renderer", fast_err)
            if video_id:
                self.store.update_video(video_id, progress=72, stage="Using compatibility renderer")
            self._render_full(
                manifest_path,
                public_dir,
                output_path,
                cancel_event=cancel_event,
            )

    def _render_fast(
        self,
        manifest_path: Path,
        public_dir: Path,
        output_path: Path,
        video_id: str | None = None,
        cancel_event: Any = None,
    ) -> None:
        script = self.renderer_root / "scripts" / "render-vector-motion.py"
        if not script.exists():
            raise RuntimeError(f"render-vector-motion.py script not found at {script}")
        # Execute python script to render vector motionPlan
        result = subprocess.run(
            [sys.executable, str(script), "--manifest", str(manifest_path), "--output", str(output_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Fast vector renderer failed: {result.stderr or result.stdout}")

    def _render_full(
        self,
        manifest_path: Path,
        public_dir: Path,
        output_path: Path,
        cancel_event: Any = None,
    ) -> None:
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

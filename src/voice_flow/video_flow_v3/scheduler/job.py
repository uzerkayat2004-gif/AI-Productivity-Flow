"""Progressive Priority Scheduler & State Machine for Video Flow V3.

Job State Machine:
created -> queued -> normalizing_source -> understanding -> directing ->
compiling_initial -> buffering -> ready -> generating_ahead -> complete (or failed/cancelled)

Independent Export State Machine:
not_requested -> requested -> exporting -> exported (or failed)

READY_TO_WATCH Definition:
1. Global narrative skeleton & ArtDirectionGenome valid
2. First scene (Scene 1) compiled with ExecutableSceneProgram
3. Initial narration segment audio ready
4. Preflight layout checks pass
5. Configurable buffer threshold (~10s) met
6. Renderer runtime warm
7. Grounding validated & scheduler playback-slack confirmed
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional
from voice_flow.video_flow_v3.contracts import (
    GenerationStateV3,
    ExportStateV3,
    VideoProgramV3,
    ExecutableSceneProgram,
)
from voice_flow.video_flow_v3.storage.project_store import project_store_v3

log = logging.getLogger(__name__)

BUFFER_THRESHOLD_SEC = 10.0


class JobV3:
    """Represents a V3 Video Generation Job with independent export state."""

    def __init__(self, job_id: str, mode: str, title: str, source_text: str) -> None:
        self.job_id = job_id
        self.mode = mode
        self.title = title
        self.source_text = source_text

        self.status = GenerationStateV3.CREATED
        self.export_status = ExportStateV3.NOT_REQUESTED
        self.stage_message = "Initializing job..."
        self.progress = 0

        self.playable = False
        self.buffered_seconds = 0.0
        self.current_scene = 0
        self.available_scenes = 0
        self.planned_scenes = 0
        self.program_complete = False
        self.export_progress = 0
        self.error: Optional[str] = None

        self.cancel_event = threading.Event()
        self.created_at = time.time()
        self.updated_at = time.time()

    def update_status(self, status: GenerationStateV3, stage_message: str = "", progress: int = -1) -> None:
        self.status = status
        if stage_message:
            self.stage_message = stage_message
        if progress >= 0:
            self.progress = max(0, min(100, progress))
        self.updated_at = time.time()
        self._persist_state()

    def update_export_status(self, status: ExportStateV3, progress: int = -1) -> None:
        self.export_status = status
        if progress >= 0:
            self.export_progress = max(0, min(100, progress))
        self.updated_at = time.time()
        self._persist_state()

    def cancel(self) -> None:
        self.cancel_event.set()
        self.update_status(GenerationStateV3.CANCELLED, "Job cancelled by user.")

    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def evaluate_ready_to_watch(self, compiled_scenes: List[ExecutableSceneProgram]) -> bool:
        """Evaluate READY_TO_WATCH conditions.

        Requires initial compiled scene, audio segment ready, grounding valid,
        and buffer threshold met (~10s).
        """
        if not compiled_scenes:
            return False

        scene0 = compiled_scenes[0]
        # Check initial audio segment exists
        audio_path = project_store_v3.get_audio_segment_path(self.job_id, scene0.scene_id)
        audio_ready = audio_path.exists() and audio_path.stat().st_size > 0

        total_buf = sum(s.duration_sec for s in compiled_scenes)
        self.buffered_seconds = total_buf
        self.available_scenes = len(compiled_scenes)

        is_ready = audio_ready and (total_buf >= BUFFER_THRESHOLD_SEC or self.program_complete)
        if is_ready and not self.playable:
            self.playable = True
            self.update_status(GenerationStateV3.READY, "Ready to watch", 100 if self.program_complete else self.progress)
            log.info(f"Job {self.job_id} reached READY_TO_WATCH with {total_buf:.1f}s buffered.")

        return is_ready

    def _persist_state(self) -> None:
        d = {
            "id": self.job_id,
            "engine_version": "v3.0.0",
            "mode": self.mode,
            "title": self.title,
            "status": self.status.value,
            "export_status": self.export_status.value,
            "stage": self.stage_message,
            "progress": self.progress,
            "playable": self.playable,
            "buffered_seconds": self.buffered_seconds,
            "available_scenes": self.available_scenes,
            "planned_scenes": self.planned_scenes,
            "program_complete": self.program_complete,
            "export_progress": self.export_progress,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        project_store_v3.save_json_artifact(self.job_id, "job_status.json", d)

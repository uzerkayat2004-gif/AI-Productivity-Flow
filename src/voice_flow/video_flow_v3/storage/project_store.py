"""Persistent structured project storage for Video Flow V3.

Stores project artifacts under ~/.voice_flow/videos/v3/<job_id>/:
- source_bundle.json
- source_model.json
- evidence_graph.json
- coverage_ledger.json
- creative_plan.json
- art_genome.json
- video_program.json
- scenes/ (compiled ExecutableSceneProgram files)
- audio/ (segmented TTS mp3/wav files)
- export/ (rendered MP4 exports)
- diagnostics.json
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import asdict

from voice_flow.video_flow_v3.contracts import (
    VideoProgramV3,
    ExecutableSceneProgram,
    GenerationStateV3,
    ExportStateV3,
    V3_CONTRACT_VERSION,
)

V3_PROJECTS_ROOT = Path.home() / ".voice_flow" / "videos" / "v3"


class ProjectStoreV3:
    """Manages persistent structured disk storage for V3 video projects."""

    def __init__(self, root_dir: Path = V3_PROJECTS_ROOT) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def get_project_dir(self, job_id: str) -> Path:
        p = self.root_dir / job_id
        p.mkdir(parents=True, exist_ok=True)
        (p / "scenes").mkdir(exist_ok=True)
        (p / "audio").mkdir(exist_ok=True)
        (p / "export").mkdir(exist_ok=True)
        return p

    def save_json_artifact(self, job_id: str, filename: str, data: Any) -> Path:
        p = self.get_project_dir(job_id) / filename
        with open(p, "w", encoding="utf-8") as f:
            if hasattr(data, "__dataclass_fields__"):
                json.dump(asdict(data), f, indent=2, ensure_ascii=False)
            else:
                json.dump(data, f, indent=2, ensure_ascii=False)
        return p

    def load_json_artifact(self, job_id: str, filename: str) -> Optional[Dict[str, Any]]:
        p = self.get_project_dir(job_id) / filename
        if not p.exists():
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def save_compiled_scene(self, job_id: str, scene_id: str, scene: ExecutableSceneProgram) -> Path:
        p = self.get_project_dir(job_id) / "scenes" / f"{scene_id}.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(asdict(scene), f, indent=2, ensure_ascii=False)
        return p

    def load_compiled_scene(self, job_id: str, scene_id: str) -> Optional[Dict[str, Any]]:
        p = self.get_project_dir(job_id) / "scenes" / f"{scene_id}.json"
        if not p.exists():
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def get_audio_segment_path(self, job_id: str, scene_id: str, extension: str = "mp3") -> Path:
        return self.get_project_dir(job_id) / "audio" / f"{scene_id}.{extension}"

    def get_export_path(self, job_id: str, extension: str = "mp4") -> Path:
        return self.get_project_dir(job_id) / "export" / f"export_{job_id}.{extension}"


class ContentAddressedCacheV3:
    """Cache intermediate structured artifacts by content hash."""

    def __init__(self, root_dir: Path = V3_PROJECTS_ROOT / "_cache") -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_hash(*inputs: str) -> str:
        h = hashlib.sha256()
        for inp in inputs:
            h.update(str(inp).encode("utf-8"))
        return h.hexdigest()[:32]

    def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        p = self.root_dir / f"{cache_key}.json"
        if not p.exists():
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def put(self, cache_key: str, data: Any) -> Path:
        p = self.root_dir / f"{cache_key}.json"
        with open(p, "w", encoding="utf-8") as f:
            if hasattr(data, "__dataclass_fields__"):
                json.dump(asdict(data), f, indent=2, ensure_ascii=False)
            else:
                json.dump(data, f, indent=2, ensure_ascii=False)
        return p


project_store_v3 = ProjectStoreV3()
cache_v3 = ContentAddressedCacheV3()

"""Bounded, non-sensitive style signatures for Video Flow Visual V2.

Only deterministic visual metadata is retained.  Source text, titles,
narration, documents, job IDs, provider data, and arbitrary metadata are never
accepted by this module or written to disk.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ClassVar, Mapping

from .scene_compiler_v2 import CompiledVisualV2
from .visual_plan_v2 import (
    BACKGROUND_CHARACTERS,
    CAMERA_INTENTS,
    MOTION_CHARACTERS,
    PALETTE_FAMILIES,
    SURFACE_MODES,
    TYPOGRAPHY_CHARACTERS,
    VideoVisualPlanV2,
)


_FILE_VERSION = 1
_DEPTH_PROFILES = frozenset({"flat", "layered", "spatial"})
_THREE_DIMENSIONAL_TYPES = frozenset({"particle_group", "mesh", "light", "camera_target"})
_LOCKS_GUARD = threading.Lock()
_LOCKS_BY_PATH: dict[str, threading.RLock] = {}


@dataclass(frozen=True)
class VisualSignature:
    """The complete, deliberately small and non-sensitive signature schema."""

    surface_mode: str
    palette_family: str
    background_family: str
    typography_family: str
    motion_profile: str
    camera_profile: str
    depth_profile: str
    scene_density: int
    usage_3d: bool

    def __post_init__(self) -> None:
        _enum(self.surface_mode, SURFACE_MODES, "surface_mode")
        _enum(self.palette_family, PALETTE_FAMILIES, "palette_family")
        _enum(self.background_family, BACKGROUND_CHARACTERS, "background_family")
        _enum(self.typography_family, TYPOGRAPHY_CHARACTERS, "typography_family")
        _enum(self.motion_profile, MOTION_CHARACTERS, "motion_profile")
        _enum(self.camera_profile, CAMERA_INTENTS, "camera_profile")
        _enum(self.depth_profile, _DEPTH_PROFILES, "depth_profile")
        if not isinstance(self.scene_density, int) or isinstance(self.scene_density, bool) or not 1 <= self.scene_density <= 16:
            raise ValueError("scene_density must be an integer from 1 through 16")
        if type(self.usage_3d) is not bool:
            raise ValueError("usage_3d must be a boolean")

    def to_dict(self) -> dict[str, str | int | bool]:
        return asdict(self)


def signature_from(plan: VideoVisualPlanV2, compiled: CompiledVisualV2) -> VisualSignature:
    """Extract a deterministic signature without inspecting source-bearing output.

    ``compiled`` is validated as the trusted compilation result but its
    production/narration payload is intentionally never read.
    """

    if not isinstance(plan, VideoVisualPlanV2):
        raise TypeError("signature_from requires a VideoVisualPlanV2")
    if not isinstance(compiled, CompiledVisualV2):
        raise TypeError("signature_from requires a CompiledVisualV2")
    if not plan.scenes:
        raise ValueError("visual plan must contain at least one scene")

    object_types = {item.type for scene in plan.scenes for item in scene.objects}
    usage_3d = bool(object_types & _THREE_DIMENSIONAL_TYPES)
    depth_profile = "spatial" if usage_3d else "layered" if object_types & {"container", "curve", "wave"} else "flat"
    scene_density = sum(len(scene.objects) for scene in plan.scenes) // len(plan.scenes)
    bible = plan.design_bible
    return VisualSignature(
        surface_mode=bible.surface_mode,
        palette_family=bible.palette_intent.accent_family,
        background_family=bible.background_character,
        typography_family=bible.typography_character,
        motion_profile=bible.motion_character,
        camera_profile=bible.camera_character,
        depth_profile=depth_profile,
        scene_density=scene_density,
        usage_3d=usage_3d,
    )


class VisualSignatureStore:
    """Small atomic JSON store with a process-local lock per canonical path."""

    _locks_by_path: ClassVar[dict[str, threading.RLock]] = _LOCKS_BY_PATH

    def __init__(self, path: Path, max_entries: int = 10) -> None:
        if not isinstance(max_entries, int) or isinstance(max_entries, bool) or not 1 <= max_entries <= 50:
            raise ValueError("max_entries must be an integer from 1 through 50")
        self.path = Path(path).expanduser().resolve()
        self.max_entries = max_entries
        self._lock = _lock_for_path(self.path)

    def recent(self) -> tuple[VisualSignature, ...]:
        """Return valid stored entries in oldest-to-newest order.

        Missing/corrupt files are treated as empty.  An otherwise valid store
        can contain malformed individual entries from an interrupted older
        version; those are ignored rather than propagated into new planning.
        """

        with self._lock:
            return tuple(self._load_unlocked()[-self.max_entries :])

    def append(self, signature: VisualSignature) -> None:
        if not isinstance(signature, VisualSignature):
            raise TypeError("signature must be a VisualSignature")
        with self._lock:
            entries = [*self._load_unlocked(), signature][-self.max_entries :]
            self._write_unlocked(entries)

    def _load_unlocked(self) -> list[VisualSignature]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return []
        if not isinstance(raw, Mapping) or set(raw) != {"version", "signatures"} or raw.get("version") != _FILE_VERSION:
            return []
        entries = raw.get("signatures")
        if not isinstance(entries, list):
            return []
        valid: list[VisualSignature] = []
        for entry in entries:
            try:
                valid.append(_signature_from_mapping(entry))
            except (TypeError, ValueError):
                continue
        return valid[-50:]

    def _write_unlocked(self, entries: list[VisualSignature]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.tmp")
        payload = {
            "version": _FILE_VERSION,
            "signatures": [entry.to_dict() for entry in entries],
        }
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)


def _signature_from_mapping(value: Any) -> VisualSignature:
    if not isinstance(value, Mapping):
        raise ValueError("signature entry must be an object")
    fields = {
        "surface_mode",
        "palette_family",
        "background_family",
        "typography_family",
        "motion_profile",
        "camera_profile",
        "depth_profile",
        "scene_density",
        "usage_3d",
    }
    if set(value) != fields:
        raise ValueError("signature entry has an invalid schema")
    return VisualSignature(**dict(value))


def _lock_for_path(path: Path) -> threading.RLock:
    key = str(path)
    with _LOCKS_GUARD:
        lock = _LOCKS_BY_PATH.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS_BY_PATH[key] = lock
        return lock


def _enum(value: Any, options: frozenset[str], name: str) -> None:
    if not isinstance(value, str) or value not in options:
        raise ValueError(f"{name} must be a supported signature value")


__all__ = ["VisualSignature", "VisualSignatureStore", "signature_from"]

"""Immutable, compiler-facing geometry resolved from the semantic V2 plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(frozen=True)
class SceneIRObject:
    id: str
    type: str
    label: str
    role: str
    region: str
    box: Box
    form: str | None = None
    carried: bool = False

    def to_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "role": self.role,
            "region": self.region,
            "box": self.box.to_dict(),
            "carried": self.carried,
        }
        if self.form is not None:
            result["form"] = self.form
        return result


@dataclass(frozen=True)
class SceneIRRelationship:
    source: str
    target: str
    kind: str

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "kind": self.kind}


@dataclass(frozen=True)
class SceneIRBeat:
    order: int
    phase: str
    action: str
    object_id: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        result = {
            "order": self.order,
            "phase": self.phase,
            "action": self.action,
            "object_id": self.object_id,
            "reason": self.reason,
        }
        return result


@dataclass(frozen=True)
class SceneIR:
    scene_id: str
    storyboard_section_id: str
    learning_goal: str
    visual_thesis: str
    visual_mode: str
    objects: tuple[SceneIRObject, ...]
    relationships: tuple[SceneIRRelationship, ...]
    beats: tuple[SceneIRBeat, ...]
    camera_intent: str | None = None
    transition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "scene_id": self.scene_id,
            "storyboard_section_id": self.storyboard_section_id,
            "learning_goal": self.learning_goal,
            "visual_thesis": self.visual_thesis,
            "visual_mode": self.visual_mode,
            "objects": [item.to_dict() for item in self.objects],
            "relationships": [item.to_dict() for item in self.relationships],
            "beats": [item.to_dict() for item in self.beats],
        }
        if self.camera_intent is not None:
            result["camera_intent"] = self.camera_intent
        if self.transition is not None:
            result["transition"] = self.transition
        return result


@dataclass(frozen=True)
class VideoSceneIR:
    width: int
    height: int
    caption_safe_bottom: int
    scenes: tuple[SceneIR, ...]

    def to_dict(self) -> dict[str, Any]:
        result = {
            "width": self.width,
            "height": self.height,
            "caption_safe_bottom": self.caption_safe_bottom,
            "scenes": [scene.to_dict() for scene in self.scenes],
        }
        return result


__all__ = [
    "Box",
    "SceneIR",
    "SceneIRBeat",
    "SceneIRObject",
    "SceneIRRelationship",
    "VideoSceneIR",
]

"""Canonical contracts for Video Flow Hybrid Rendering & Generative Video Providers.

These provider-independent contracts allow Video Flow to route scene generation
between deterministic procedural renderers (2D/3D/Remotion) and future generative
video models (Veo, Hugging Face, local diffusion) while guaranteeing a zero-cost
fallback path for all users.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class RenderStrategy(str, Enum):
    """Visual production strategy for a scene."""

    PROCEDURAL_2D = "procedural_2d"
    PROCEDURAL_3D = "procedural_3d"
    REMOTION = "remotion"
    GENERATIVE_VIDEO = "generative_video"
    MEDIA = "media"


class GenerationPolicy(str, Enum):
    """User/system policy controlling when generative video providers may be used."""

    FREE_DETERMINISTIC = "free_deterministic"  # Always use deterministic/procedural rendering (zero API cost)
    BALANCED = "balanced"                      # Use generative video for hero/key scenes if provider available
    PREMIUM_GENERATIVE = "premium_generative"  # Maximize generative video coverage when available
    LOCAL_ONLY = "local_only"                  # Only use local/offline models, never remote paid APIs
    SPONSORED = "sponsored"                    # Use community/sponsored inference pools


@dataclass
class VideoProviderCapabilities:
    """Declared capabilities and constraints of a video generation provider."""

    provider_id: str
    display_name: str
    supports_text_to_video: bool = True
    supports_image_to_video: bool = False
    supports_seed: bool = False
    supports_negative_prompt: bool = False
    supported_aspect_ratios: list[str] = field(default_factory=lambda: ["16:9", "9:16", "1:1"])
    max_duration_seconds: float = 8.0
    is_local: bool = False
    is_free: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VideoGenerationRequest:
    """Provider-neutral request for generating a video scene asset."""

    scene_id: str
    prompt: str
    negative_prompt: str | None = None
    duration: float = 4.0
    aspect_ratio: str = "16:9"
    resolution: str = "1080p"
    seed: int | None = None
    reference_images: list[str] = field(default_factory=list)
    grounding_context: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.prompt = str(self.prompt or "").strip()
        self.duration = max(0.5, float(self.duration))
        self.aspect_ratio = str(self.aspect_ratio or "16:9").strip()
        self.resolution = str(self.resolution or "1080p").strip()
        self.reference_images = [str(p) for p in self.reference_images]
        self.grounding_context = dict(self.grounding_context or {})
        self.extensions = dict(self.extensions or {})

    def content_hash(self) -> str:
        payload = json.dumps(
            {
                "scene_id": self.scene_id,
                "prompt": self.prompt,
                "duration": self.duration,
                "aspect_ratio": self.aspect_ratio,
                "resolution": self.resolution,
                "seed": self.seed,
            },
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:24]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GeneratedVideoAsset:
    """Result returned by a GenerativeVideoProvider upon successful clip production."""

    provider: str
    model: str
    local_path: str
    duration: float
    dimensions: tuple[int, int] = (1920, 1080)
    content_hash: str = ""
    generation_metadata: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        self.provider = str(self.provider or "unknown").strip()
        self.model = str(self.model or "unknown").strip()
        self.local_path = str(self.local_path or "").strip()
        self.duration = max(0.0, float(self.duration))
        if not self.content_hash and self.local_path:
            self.content_hash = hashlib.sha256(self.local_path.encode("utf-8")).hexdigest()[:24]
        self.generation_metadata = dict(self.generation_metadata or {})
        self.provenance = dict(self.provenance or {})

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["dimensions"] = list(self.dimensions)
        return data


@dataclass
class SceneRenderRouting:
    """Decision record for how a specific scene will be visually rendered."""

    scene_id: str
    requested_strategy: RenderStrategy = RenderStrategy.PROCEDURAL_2D
    fallback_strategy: RenderStrategy = RenderStrategy.PROCEDURAL_2D
    resolved_strategy: RenderStrategy = RenderStrategy.PROCEDURAL_2D
    provider_id: str | None = None
    is_fallback: bool = False
    fallback_reason: str | None = None
    asset: GeneratedVideoAsset | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "requested_strategy": self.requested_strategy.value,
            "fallback_strategy": self.fallback_strategy.value,
            "resolved_strategy": self.resolved_strategy.value,
            "provider_id": self.provider_id,
            "is_fallback": self.is_fallback,
            "fallback_reason": self.fallback_reason,
            "asset": self.asset.to_dict() if self.asset else None,
            "metadata": self.metadata,
        }

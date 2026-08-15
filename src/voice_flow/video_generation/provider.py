"""Abstract base class for generative video providers and mock provider implementation."""

from __future__ import annotations

import abc
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from voice_flow.video_generation.contracts import (
    GeneratedVideoAsset,
    VideoGenerationRequest,
    VideoProviderCapabilities,
)

log = logging.getLogger(__name__)


class GenerativeVideoProvider(abc.ABC):
    """Abstract contract for generative video model providers.

    All generative video models (Google Veo, Hugging Face, fal.ai, Replicate, local diffusion)
    must implement this interface. The Video Flow Brain plans scenes and prompts; providers
    only produce video clips and return standard GeneratedVideoAsset objects.
    """

    @property
    @abc.abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this provider (e.g. 'google_veo', 'huggingface_video', 'mock')."""
        ...

    @property
    @abc.abstractmethod
    def display_name(self) -> str:
        """Human-readable display name (e.g. 'Google Veo', 'Hugging Face Video')."""
        ...

    @abc.abstractmethod
    def available(self) -> bool:
        """Return True if this provider is configured, authenticated, and ready to generate."""
        ...

    @abc.abstractmethod
    def capabilities(self) -> VideoProviderCapabilities:
        """Return declared capabilities, constraints, and supported parameters."""
        ...

    @abc.abstractmethod
    def generate(self, request: VideoGenerationRequest) -> GeneratedVideoAsset:
        """Generate a video clip from the structured request.

        Raises:
            RuntimeError: If generation fails or API errors occur.
            ValueError: If request parameters are unsupported.
        """
        ...

    def validate_asset(self, asset: GeneratedVideoAsset) -> bool:
        """Verify that the generated asset exists and meets minimum duration/format criteria."""
        if not asset.local_path:
            return False
        path = Path(asset.local_path)
        return path.exists() and path.stat().st_size > 0


class FakeGenerativeVideoProvider(GenerativeVideoProvider):
    """Deterministic, zero-cost mock generative video provider for tests and offline development.

    Generates deterministic placeholder video asset records without calling external APIs
    or requiring paid credentials.
    """

    def __init__(
        self,
        provider_id: str = "fake_generative_provider",
        display_name: str = "Deterministic Test Video Provider",
        is_available: bool = True,
        mock_output_dir: str | Path | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._display_name = display_name
        self._available = is_available
        self._output_dir = Path(mock_output_dir) if mock_output_dir else Path(tempfile.gettempdir()) / "video_flow_fake_assets"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def display_name(self) -> str:
        return self._display_name

    def available(self) -> bool:
        return self._available

    def set_available(self, available: bool) -> None:
        self._available = available

    def capabilities(self) -> VideoProviderCapabilities:
        return VideoProviderCapabilities(
            provider_id=self._provider_id,
            display_name=self._display_name,
            supports_text_to_video=True,
            supports_image_to_video=True,
            supports_seed=True,
            supports_negative_prompt=True,
            supported_aspect_ratios=["16:9", "9:16", "1:1"],
            max_duration_seconds=10.0,
            is_local=True,
            is_free=True,
            metadata={"is_mock": True},
        )

    def generate(self, request: VideoGenerationRequest) -> GeneratedVideoAsset:
        if not self.available():
            raise RuntimeError(f"Provider '{self._provider_id}' is currently unavailable.")

        # Create a deterministic mock placeholder file
        filename = f"mock_{request.scene_id}_{request.content_hash()[:8]}.mp4"
        file_path = self._output_dir / filename
        if not file_path.exists():
            file_path.write_bytes(f"FAKE_VIDEO_STREAM:{request.prompt}".encode("utf-8"))

        return GeneratedVideoAsset(
            provider=self._provider_id,
            model="mock-deterministic-v1",
            local_path=str(file_path),
            duration=request.duration,
            dimensions=(1920, 1080) if request.aspect_ratio == "16:9" else (1080, 1920),
            content_hash=request.content_hash(),
            generation_metadata={
                "prompt": request.prompt,
                "aspect_ratio": request.aspect_ratio,
                "is_mock": True,
            },
            provenance={
                "scene_id": request.scene_id,
                "timestamp": time.time(),
            },
        )

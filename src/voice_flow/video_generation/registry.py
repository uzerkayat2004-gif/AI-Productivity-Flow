"""Registry for discovering, managing, and querying generative video providers."""

from __future__ import annotations

import logging
from typing import Iterator

from voice_flow.video_generation.contracts import VideoProviderCapabilities
from voice_flow.video_generation.provider import GenerativeVideoProvider

log = logging.getLogger(__name__)


class VideoProviderRegistry:
    """Central registry for generative video providers."""

    def __init__(self) -> None:
        self._providers: dict[str, GenerativeVideoProvider] = {}

    def register(self, provider: GenerativeVideoProvider) -> None:
        """Register a video generation provider instance."""
        pid = provider.provider_id.strip().lower()
        self._providers[pid] = provider
        log.info("[VIDEO REGISTRY] Registered video provider: '%s' (%s)", pid, provider.display_name)

    def unregister(self, provider_id: str) -> bool:
        """Remove a provider from the registry."""
        pid = provider_id.strip().lower()
        return self._providers.pop(pid, None) is not None

    def get(self, provider_id: str) -> GenerativeVideoProvider | None:
        """Fetch a registered provider by ID."""
        pid = provider_id.strip().lower()
        return self._providers.get(pid)

    def list_all(self) -> list[GenerativeVideoProvider]:
        """Return all registered providers."""
        return list(self._providers.values())

    def list_available(self) -> list[GenerativeVideoProvider]:
        """Return only providers that report available() == True."""
        return [p for p in self._providers.values() if p.available()]

    def list_capabilities(self) -> list[VideoProviderCapabilities]:
        """Return capabilities for all registered providers."""
        return [p.capabilities() for p in self._providers.values()]

    def __len__(self) -> int:
        return len(self._providers)

    def __iter__(self) -> Iterator[GenerativeVideoProvider]:
        return iter(self._providers.values())


# Global registry singleton
video_provider_registry = VideoProviderRegistry()

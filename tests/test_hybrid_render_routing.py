"""Tests for Video Flow Hybrid Render Routing and Video Generation Provider contracts."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from voice_flow.video_generation import (
    FakeGenerativeVideoProvider,
    GeneratedVideoAsset,
    GenerationPolicy,
    HybridRenderRouter,
    RenderStrategy,
    SceneRenderRouting,
    VideoGenerationRequest,
    VideoProviderCapabilities,
    VideoProviderRegistry,
)


def test_video_generation_contracts_and_hashing():
    req = VideoGenerationRequest(
        scene_id="scene_001",
        prompt="A 3D diagram showing neural network layers connecting and firing activations",
        duration=4.5,
        aspect_ratio="16:9",
        resolution="1080p",
        seed=42,
    )
    req_dict = req.to_dict()
    assert req_dict["scene_id"] == "scene_001"
    assert req_dict["duration"] == 4.5
    assert len(req.content_hash()) == 24

    asset = GeneratedVideoAsset(
        provider="mock_provider",
        model="mock-v1",
        local_path="/tmp/mock_asset.mp4",
        duration=4.5,
        dimensions=(1920, 1080),
    )
    asset_dict = asset.to_dict()
    assert asset_dict["provider"] == "mock_provider"
    assert asset_dict["dimensions"] == [1920, 1080]


def test_free_deterministic_policy_guarantees_zero_cost_fallback():
    registry = VideoProviderRegistry()
    fake_provider = FakeGenerativeVideoProvider(provider_id="fake_provider", is_available=True)
    registry.register(fake_provider)

    router = HybridRenderRouter(registry=registry)

    # User has FREE_DETERMINISTIC policy (default)
    routing = router.resolve_strategy(
        scene_id="scene_intro",
        requested_strategy=RenderStrategy.GENERATIVE_VIDEO,
        fallback_strategy=RenderStrategy.PROCEDURAL_2D,
        policy=GenerationPolicy.FREE_DETERMINISTIC,
    )

    assert routing.is_fallback is True
    assert routing.resolved_strategy == RenderStrategy.PROCEDURAL_2D
    assert "FREE_DETERMINISTIC" in str(routing.fallback_reason)


def test_generative_routing_when_provider_is_available():
    registry = VideoProviderRegistry()
    fake_provider = FakeGenerativeVideoProvider(provider_id="fake_provider", is_available=True)
    registry.register(fake_provider)

    router = HybridRenderRouter(registry=registry)

    routing = router.resolve_strategy(
        scene_id="scene_hero",
        requested_strategy=RenderStrategy.GENERATIVE_VIDEO,
        fallback_strategy=RenderStrategy.PROCEDURAL_3D,
        policy=GenerationPolicy.PREMIUM_GENERATIVE,
    )

    assert routing.is_fallback is False
    assert routing.resolved_strategy == RenderStrategy.GENERATIVE_VIDEO
    assert routing.provider_id == "fake_provider"

    # Execute generation
    req = VideoGenerationRequest(scene_id="scene_hero", prompt="Explain photosynthesis with chloroplast animation", duration=5.0)
    executed_routing = router.execute_scene_render(req, routing)

    assert executed_routing.is_fallback is False
    assert executed_routing.asset is not None
    assert executed_routing.asset.provider == "fake_provider"
    assert Path(executed_routing.asset.local_path).exists()


def test_fallback_when_generative_provider_is_unavailable():
    registry = VideoProviderRegistry()
    fake_provider = FakeGenerativeVideoProvider(provider_id="fake_offline", is_available=False)
    registry.register(fake_provider)

    router = HybridRenderRouter(registry=registry)

    routing = router.resolve_strategy(
        scene_id="scene_hero",
        requested_strategy=RenderStrategy.GENERATIVE_VIDEO,
        fallback_strategy=RenderStrategy.PROCEDURAL_2D,
        policy=GenerationPolicy.BALANCED,
    )

    assert routing.is_fallback is True
    assert routing.resolved_strategy == RenderStrategy.PROCEDURAL_2D
    assert "No compatible generative video provider" in str(routing.fallback_reason)


def test_fallback_when_provider_throws_exception():
    class CrashingProvider(FakeGenerativeVideoProvider):
        def generate(self, request: VideoGenerationRequest) -> GeneratedVideoAsset:
            raise RuntimeError("Cloud video GPU out of memory")

    registry = VideoProviderRegistry()
    crashing = CrashingProvider(provider_id="crash_test", is_available=True)
    registry.register(crashing)

    router = HybridRenderRouter(registry=registry)

    routing = router.resolve_strategy(
        scene_id="scene_complex",
        requested_strategy=RenderStrategy.GENERATIVE_VIDEO,
        fallback_strategy=RenderStrategy.REMOTION,
        policy=GenerationPolicy.PREMIUM_GENERATIVE,
    )

    req = VideoGenerationRequest(scene_id="scene_complex", prompt="Complex particle simulation")
    executed = router.execute_scene_render(req, routing)

    assert executed.is_fallback is True
    assert executed.resolved_strategy == RenderStrategy.REMOTION
    assert "GPU out of memory" in str(executed.fallback_reason)
    assert executed.asset is None


def test_local_only_policy_filtering():
    class RemoteProvider(FakeGenerativeVideoProvider):
        def capabilities(self) -> VideoProviderCapabilities:
            caps = super().capabilities()
            caps.is_local = False
            return caps

    class LocalProvider(FakeGenerativeVideoProvider):
        def capabilities(self) -> VideoProviderCapabilities:
            caps = super().capabilities()
            caps.is_local = True
            return caps

    registry = VideoProviderRegistry()
    registry.register(RemoteProvider(provider_id="cloud_model", is_available=True))
    registry.register(LocalProvider(provider_id="local_model", is_available=True))

    router = HybridRenderRouter(registry=registry)

    routing = router.resolve_strategy(
        scene_id="scene_private",
        requested_strategy=RenderStrategy.GENERATIVE_VIDEO,
        fallback_strategy=RenderStrategy.PROCEDURAL_2D,
        policy=GenerationPolicy.LOCAL_ONLY,
    )

    assert routing.is_fallback is False
    assert routing.provider_id == "local_model"

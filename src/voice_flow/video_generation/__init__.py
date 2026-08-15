"""Video Generation & Hybrid Rendering Package for Video Flow."""

from voice_flow.video_generation.contracts import (
    GeneratedVideoAsset,
    GenerationPolicy,
    RenderStrategy,
    SceneRenderRouting,
    VideoGenerationRequest,
    VideoProviderCapabilities,
)
from voice_flow.video_generation.provider import (
    FakeGenerativeVideoProvider,
    GenerativeVideoProvider,
)
from voice_flow.video_generation.registry import (
    VideoProviderRegistry,
    video_provider_registry,
)
from voice_flow.video_generation.router import (
    HybridRenderRouter,
    hybrid_render_router,
)

__all__ = [
    "RenderStrategy",
    "GenerationPolicy",
    "VideoProviderCapabilities",
    "VideoGenerationRequest",
    "GeneratedVideoAsset",
    "SceneRenderRouting",
    "GenerativeVideoProvider",
    "FakeGenerativeVideoProvider",
    "VideoProviderRegistry",
    "video_provider_registry",
    "HybridRenderRouter",
    "hybrid_render_router",
]

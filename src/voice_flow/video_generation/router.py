"""Hybrid Render Router for Video Flow.

Evaluates per-scene render strategy requirements against user/system policy
and registered video providers, providing deterministic fallback guarantees.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from voice_flow.video_generation.contracts import (
    GeneratedVideoAsset,
    GenerationPolicy,
    RenderStrategy,
    SceneRenderRouting,
    VideoGenerationRequest,
)
from voice_flow.video_generation.registry import VideoProviderRegistry, video_provider_registry

log = logging.getLogger(__name__)


class HybridRenderRouter:
    """Decides visual production strategy per scene with guaranteed zero-cost fallback."""

    def __init__(self, registry: VideoProviderRegistry | None = None) -> None:
        self.registry = registry or video_provider_registry

    def resolve_strategy(
        self,
        scene_id: str,
        requested_strategy: RenderStrategy | str = RenderStrategy.PROCEDURAL_2D,
        fallback_strategy: RenderStrategy | str = RenderStrategy.PROCEDURAL_2D,
        policy: GenerationPolicy | str = GenerationPolicy.FREE_DETERMINISTIC,
        preferred_provider_id: str | None = None,
    ) -> SceneRenderRouting:
        """Determine whether a scene should use generative video or a deterministic fallback."""
        # Normalize inputs
        req_strat = RenderStrategy(requested_strategy) if isinstance(requested_strategy, str) else requested_strategy
        fb_strat = RenderStrategy(fallback_strategy) if isinstance(fallback_strategy, str) else fallback_strategy
        gen_policy = GenerationPolicy(policy) if isinstance(policy, str) else policy

        # Case 1: Free Deterministic Policy — always use deterministic rendering
        if gen_policy == GenerationPolicy.FREE_DETERMINISTIC:
            if req_strat == RenderStrategy.GENERATIVE_VIDEO:
                return SceneRenderRouting(
                    scene_id=scene_id,
                    requested_strategy=req_strat,
                    fallback_strategy=fb_strat,
                    resolved_strategy=fb_strat,
                    is_fallback=True,
                    fallback_reason="Policy is FREE_DETERMINISTIC (zero API cost path).",
                )
            return SceneRenderRouting(
                scene_id=scene_id,
                requested_strategy=req_strat,
                fallback_strategy=fb_strat,
                resolved_strategy=req_strat,
                is_fallback=False,
            )

        # Case 2: Deterministic strategy requested (procedural 2d, 3d, remotion, media)
        if req_strat != RenderStrategy.GENERATIVE_VIDEO:
            return SceneRenderRouting(
                scene_id=scene_id,
                requested_strategy=req_strat,
                fallback_strategy=fb_strat,
                resolved_strategy=req_strat,
                is_fallback=False,
            )

        # Case 3: Generative Video requested under active policy (Balanced, Premium, Sponsored, Local-Only)
        available_providers = self.registry.list_available()

        # Filter for local-only policy if required
        if gen_policy == GenerationPolicy.LOCAL_ONLY:
            available_providers = [p for p in available_providers if p.capabilities().is_local]

        if not available_providers:
            log.info("[ROUTER] No generative video provider available for scene '%s'. Using fallback: %s", scene_id, fb_strat.value)
            return SceneRenderRouting(
                scene_id=scene_id,
                requested_strategy=req_strat,
                fallback_strategy=fb_strat,
                resolved_strategy=fb_strat,
                is_fallback=True,
                fallback_reason="No compatible generative video provider is currently available.",
            )

        # Match preferred provider if specified, else pick highest priority available
        target_provider = None
        if preferred_provider_id:
            target_provider = self.registry.get(preferred_provider_id)
            if target_provider and not target_provider.available():
                target_provider = None

        if target_provider is None:
            target_provider = available_providers[0]

        return SceneRenderRouting(
            scene_id=scene_id,
            requested_strategy=req_strat,
            fallback_strategy=fb_strat,
            resolved_strategy=RenderStrategy.GENERATIVE_VIDEO,
            provider_id=target_provider.provider_id,
            is_fallback=False,
        )

    def execute_scene_render(
        self,
        request: VideoGenerationRequest,
        routing: SceneRenderRouting,
    ) -> SceneRenderRouting:
        """Execute generative video generation if resolved, or gracefully degrade to fallback on error."""
        if routing.resolved_strategy != RenderStrategy.GENERATIVE_VIDEO or not routing.provider_id:
            # Deterministic scene; no generative provider call needed
            return routing

        provider = self.registry.get(routing.provider_id)
        if not provider or not provider.available():
            routing.resolved_strategy = routing.fallback_strategy
            routing.is_fallback = True
            routing.fallback_reason = f"Provider '{routing.provider_id}' became unavailable before execution."
            return routing

        try:
            log.info("[ROUTER] Generating video clip for scene '%s' via provider '%s'...", request.scene_id, provider.provider_id)
            asset = provider.generate(request)
            if not provider.validate_asset(asset):
                raise RuntimeError(f"Provider '{provider.provider_id}' produced an invalid or missing video asset.")

            routing.asset = asset
            routing.is_fallback = False
            return routing

        except Exception as exc:
            log.warning(
                "[ROUTER] Generative render failed for scene '%s' (%s). Gracefully degrading to fallback '%s'.",
                request.scene_id,
                exc,
                routing.fallback_strategy.value,
            )
            routing.resolved_strategy = routing.fallback_strategy
            routing.is_fallback = True
            routing.fallback_reason = f"Generation error: {exc}"
            routing.asset = None
            return routing


# Global router singleton
hybrid_render_router = HybridRenderRouter()

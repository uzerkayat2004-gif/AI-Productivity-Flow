"""Manim-based Video Rendering Engine for Video Flow V3.

Replaces the broken Three.js/PixiJS/PIL canvas renderer with a proper
animation engine that produces broadcast-quality 1080p MP4 videos using
Manim (the 3Blue1Brown engine).
"""

from voice_flow.video_flow_v3.manim_engine.renderer import ManimVideoRenderer

__all__ = ["ManimVideoRenderer"]

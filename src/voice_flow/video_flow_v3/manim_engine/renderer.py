"""Video Flow V3 Manim Engine Renderer.

Orchestrates the conversion of VideoProgramV3 into scene specifications and invokes
SceneComposer to generate the final 1080p MP4 with synchronized master narration audio.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from voice_flow.video_flow_v3.contracts import VideoProgramV3, ArtDirectionGenome
from voice_flow.video_flow_v3.manim_engine import animation_core

log = logging.getLogger(__name__)


class ManimVideoRenderer:
    """Orchestrator for headless, deterministic 1080p MP4 rendering."""

    def render_video(
        self,
        program: VideoProgramV3,
        genome: Optional[ArtDirectionGenome] = None,
        output_dir: str = "",
        output_path: Optional[str] = None,
        audio_path: Optional[str] = None,
        fps: int = 30,
    ) -> str:
        """Render a complete Video Flow V3 program to MP4."""
        if not output_path:
            os.makedirs(output_dir or ".", exist_ok=True)
            output_path = os.path.join(output_dir or ".", "video.mp4")

        composer = animation_core.SceneComposer(
            output_path=output_path,
            fps=fps,
            resolution=(1920, 1080),
            genome=genome,
        )

        scenes_to_render = getattr(program, "scenes", []) or []
        if not scenes_to_render:
            # Fallback title scene
            composer.add_scene({
                "representation_type": "TITLE",
                "title": getattr(program, "title", "Video Flow Visual Summary"),
                "narration": "A visual explanation synthesized by Voice Flow.",
                "duration": 4.0,
            })

        for i, scene in enumerate(scenes_to_render):
            duration = max(3.0, float(getattr(scene, "duration_sec", 5.0)))
            narration = getattr(scene, "narration_text", None) or getattr(scene, "narration", "")
            if not narration and hasattr(scene, "narration"):
                narration = scene.narration

            # Extract visual objects and labels
            raw_objects = getattr(scene, "semantic_objects", []) or getattr(scene, "visual_objects", []) or getattr(scene, "elements_2d", []) or []
            objects_list: List[Dict[str, Any]] = []
            for obj in raw_objects:
                if isinstance(obj, dict):
                    objects_list.append(obj)
                elif hasattr(obj, "label"):
                    objects_list.append({"label": obj.label, "semantic_type": getattr(obj, "semantic_type", "")})
                elif isinstance(obj, str):
                    objects_list.append({"label": obj})

            rep_type = getattr(scene, "representation_type", "PROCESS")
            if hasattr(rep_type, "value"):
                rep_type = rep_type.value

            teaching_goal = getattr(scene, "teaching_goal", "") or getattr(scene, "title", f"Scene {i+1}")

            spec = {
                "scene_id": getattr(scene, "scene_id", f"scene_{i+1}"),
                "representation_type": rep_type,
                "duration": duration,
                "teaching_goal": teaching_goal,
                "title": teaching_goal,
                "narration": narration,
                "visual_objects": objects_list,
                "objects": objects_list,
            }
            composer.add_scene(spec)

        result_path = composer.render_scenes(composer.scenes, output_path, audio_path=audio_path)
        log.info(f"ManimVideoRenderer successfully generated: {result_path}")
        return result_path

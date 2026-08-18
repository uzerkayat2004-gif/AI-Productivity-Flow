"""Master Orchestrator Service for Video Flow V3.

Coordinates:
SourceBundle -> SourceNormalizer -> EvidenceGraph -> CoverageLedger ->
CreativeDirector -> ArtDirectionGenome -> VideoProgramV3 ->
Deterministic Compilers -> Segmented TTS -> READY_TO_WATCH -> Player
"""

from __future__ import annotations

import logging
import math
import os
import threading
import uuid
from typing import Any, Dict, List, Optional

from voice_flow.video_flow_v3.contracts import (
    SourceBundle,
    GenerationStateV3,
    ExportStateV3,
    VideoProgramV3,
    ExecutableSceneProgram,
    ExecutableElement2D,
    ExecutableNode3D,
    SemanticRepresentationType,
    PerformanceProfile,
)
from voice_flow.video_flow_v3.source.units import SourceNormalizer
from voice_flow.video_flow_v3.evidence.builder import EvidenceGraphBuilder, CoverageLedgerTracker
from voice_flow.video_flow_v3.director.creative_director import CreativeDirectorV3
from voice_flow.video_flow_v3.art_direction.resolver import ArtDirectionResolverV3
from voice_flow.video_flow_v3.quality.constitution import quality_constitution_v3, repair_ladder_v3
from voice_flow.video_flow_v3.scheduler.job import JobV3
from voice_flow.video_flow_v3.storage.project_store import project_store_v3, cache_v3
from voice_flow.tts_engine import tts_engine
from voice_flow.video_flow_v3.manim_engine.renderer import ManimVideoRenderer

log = logging.getLogger(__name__)


class VideoFlowV3Service:
    """Master backend service for Video Flow V3 visual explanation engine."""

    def __init__(self, model_gateway: Any = None) -> None:
        self.jobs: Dict[str, JobV3] = {}
        self._lock = threading.Lock()
        if model_gateway is None:
            try:
                from voice_flow.video_flow_models import VideoModelGateway
                from voice_flow.video_flow import VideoFlowStore, VideoFlowPlanner
                model_gateway = VideoModelGateway(VideoFlowStore(), VideoFlowPlanner())
            except Exception:
                model_gateway = None
        self.model_gateway = model_gateway
        self.director = CreativeDirectorV3(model_gateway=self.model_gateway)

    def create_job(
        self,
        source_text: str,
        mode: str = "summary",
        title: str = "",
        visual_style: str = "Auto",
        job_id: str | None = None,
        model_ref: str = "local/deterministic",
        visual_direction: str = "",
        allow_external_ai: bool = False,
    ) -> JobV3:
        if not job_id:
            job_id = f"v3_{uuid.uuid4().hex[:12]}"
        title_clean = (title or source_text[:40].replace("\n", " ") or "Visual Explanation").strip()
        job = JobV3(
            job_id=job_id,
            mode=mode,
            title=title_clean,
            source_text=source_text,
            model_ref=model_ref,
            visual_direction=visual_direction,
            allow_external_ai=allow_external_ai,
        )
        with self._lock:
            self.jobs[job_id] = job
        return job

    def run_job(self, job_id: str, visual_style: str = "Auto") -> None:
        with self._lock:
            job = self.jobs.get(job_id)
        if not job:
            return

        try:
            # Stage 1: Normalize Source & Segment Units (supports single & multi-doc bundles)
            job.update_status(GenerationStateV3.NORMALIZING_SOURCE, "Normalizing source...", 10)
            doc_metadata = getattr(job, "metadata", {}) if hasattr(job, "metadata") and isinstance(job.metadata, dict) else {}
            bundle = SourceBundle(
                source_text=job.source_text,
                source_name=job.title,
                metadata=doc_metadata,
            )
            units = SourceNormalizer.segment_source_units(bundle)
            project_store_v3.save_json_artifact(job_id, "source_bundle.json", bundle)
            project_store_v3.save_json_artifact(job_id, "source_units.json", [u.__dict__ for u in units])

            if job.is_cancelled():
                return

            # Stage 2: Extract EvidenceGraph & CoverageLedger
            job.update_status(GenerationStateV3.UNDERSTANDING, "Understanding source & building evidence...", 25)
            evidence = EvidenceGraphBuilder.build_evidence_graph(units)
            ledger = CoverageLedgerTracker.create_ledger(units, job.mode)
            project_store_v3.save_json_artifact(job_id, "evidence_graph.json", evidence)
            project_store_v3.save_json_artifact(job_id, "coverage_ledger.json", ledger)

            if job.is_cancelled():
                return

            # Stage 3: Creative Director & Art Direction Genome (with mode, visual_direction & multi-doc routing)
            job.update_status(GenerationStateV3.DIRECTING, "Directing visual explanation...", 40)
            resolver = ArtDirectionResolverV3()
            genome = resolver.resolve(
                source_text=bundle.source_text,
                topic_hint=bundle.source_name,
                source_hash=bundle.source_hash,
                family_override=visual_style,
                mode=job.mode,
                visual_direction=getattr(job, "visual_direction", ""),
            )
            program = self.director.build_program(
                bundle=bundle,
                units=units,
                evidence=evidence,
                ledger=ledger,
                genome=genome,
                mode=job.mode,
                title=job.title,
                model_ref=getattr(job, "model_ref", "local/deterministic"),
                visual_direction=getattr(job, "visual_direction", ""),
                allow_external_ai=getattr(job, "allow_external_ai", False),
            )
            project_store_v3.save_json_artifact(job_id, "art_genome.json", genome)
            project_store_v3.save_json_artifact(job_id, "coverage_ledger.json", ledger)
            project_store_v3.save_json_artifact(job_id, "video_program.json", program)

            job.program = program
            job.planned_scenes = len(program.scenes)

            job_output_dir = str(project_store_v3.get_project_dir(job_id))
            def _render_mp4_bg():
                try:
                    ManimVideoRenderer().render_video(program, genome, output_dir=job_output_dir)
                    job.update_status(GenerationStateV3.COMPLETE, "Ready to watch", 100)
                except Exception as e:
                    log.error(f"Render failed: {e}")
                    
            threading.Thread(target=_render_mp4_bg, daemon=True).start()

            if job.is_cancelled():
                return

            # Stage 4: Compile Scenes & Synthesize Narration Segment 1
            job.update_status(GenerationStateV3.COMPILING_INITIAL, "Preparing first scenes...", 60)
            compiled_scenes: List[ExecutableSceneProgram] = []

            for idx, scene_semantic in enumerate(program.scenes):
                if job.is_cancelled():
                    return

                # Deterministic Visual Compiler (Python side) with adaptive budgeting
                executable_scene = self._compile_scene_deterministically(scene_semantic, genome)
                executable_scene = repair_ladder_v3.simplify_scene_for_performance(executable_scene)
                project_store_v3.save_compiled_scene(job_id, executable_scene.scene_id, executable_scene)

                # Segmented TTS Audio Synthesis for Scene
                audio_path = project_store_v3.get_audio_segment_path(job_id, executable_scene.scene_id)
                try:
                    if not audio_path.exists() or audio_path.stat().st_size == 0:
                        audio_bytes = tts_engine._synthesize(scene_semantic.narration_text, "deepgram/aura-zeus-en")
                        if audio_bytes:
                            with open(audio_path, "wb") as af:
                                af.write(audio_bytes)
                except Exception as tts_err:
                    log.debug("TTS synthesis skipped/failed: %s", tts_err)

                # Probe REAL audio duration and update scene timeline for live segmented playback
                from voice_flow.video_flow_v3.audio.narration import probe_audio_duration_sec, concatenate_narration_audio
                actual_audio_sec = probe_audio_duration_sec(str(audio_path))
                scene_dur = max(3.5, round(actual_audio_sec + 0.8, 2))
                executable_scene.duration_sec = scene_dur
                scene_semantic.suggested_duration_sec = scene_dur
                scene_semantic.duration_sec = scene_dur
                executable_scene.audio_segment_url = f"/api/video-flow/v3/audio?id={job_id}&scene={executable_scene.scene_id}"

                compiled_scenes.append(executable_scene)

                # Evaluate READY_TO_WATCH after Scene 1 / Initial Buffer
                if idx == 0 or len(compiled_scenes) >= 2:
                    job.evaluate_ready_to_watch(compiled_scenes)

                # Progressive status update
                pct = int(60 + (idx + 1) / len(program.scenes) * 35)
                job.update_status(GenerationStateV3.GENERATING_AHEAD, f"Generating scene {idx+1}/{len(program.scenes)}...", pct)

            # Master audio concatenation for MP4 export
            all_audio_files = [str(project_store_v3.get_audio_segment_path(job_id, s.scene_id)) for s in compiled_scenes]
            master_audio_path = str(project_store_v3.get_project_dir(job_id) / "master_narration.mp3")
            concatenate_narration_audio(all_audio_files, master_audio_path)

            master_audio_dur = probe_audio_duration_sec(master_audio_path)
            if master_audio_dur > 0 and program.scenes:
                program.total_estimated_duration_sec = master_audio_dur

            project_store_v3.save_json_artifact(job_id, "video_program.json", program)

            job.program_complete = True
            job.update_status(GenerationStateV3.COMPLETE, "Complete", 100)
            log.info(f"Job {job_id} V3 generation complete with {len(compiled_scenes)} scenes.")

            # Automatically render 1080p MP4 export in background daemon thread (when not in pytest)
            def _bg_export():
                try:
                    export_file = project_store_v3.get_export_path(job_id)
                    if export_file.exists() and export_file.stat().st_size > 0:
                        job.update_export_status(ExportStateV3.EXPORTED, 100)
                    else:
                        from voice_flow.video_flow_v3.manim_engine.renderer import ManimVideoRenderer
                        renderer = ManimVideoRenderer()
                        master_audio = str(project_store_v3.get_project_dir(job_id) / "master_narration.mp3")
                        renderer.render_video(
                            program=program,
                            genome=genome,
                            output_path=str(export_file),
                            audio_path=master_audio if os.path.exists(master_audio) else None,
                            fps=30,
                        )
                        job.update_export_status(ExportStateV3.EXPORTED, 100)
                except Exception as exp_err:
                    log.warning(f"Auto-export for job {job_id} failed, falling back to frame renderer: {exp_err}")
                    try:
                        from voice_flow.video_flow_v3.export.renderer import video_renderer_v3
                        video_renderer_v3.export_job_mp4(job_id=job_id, fps=30)
                        job.update_export_status(ExportStateV3.EXPORTED, 100)
                    except Exception as fallback_err:
                        log.error(f"Fallback export failed for {job_id}: {fallback_err}")

            if not os.environ.get("PYTEST_CURRENT_TEST"):
                threading.Thread(target=_bg_export, daemon=True).start()

        except Exception as exc:
            log.error(f"Job {job_id} failed: {exc}", exc_info=True)
            job.error = str(exc)
            job.update_status(GenerationStateV3.FAILED, f"Generation failed: {exc}")

    def _compile_scene_deterministically(
        self,
        semantic: Any,
        genome: Any,
    ) -> ExecutableSceneProgram:
        """Deterministic Compiler Layer: converts semantic intent to layout bounds & transforms with adaptive budgeting."""
        elements_2d: List[ExecutableElement2D] = []
        nodes_3d: List[ExecutableNode3D] = []
        rep_type = getattr(semantic, "representation_type", SemanticRepresentationType.PROCESS.value)

        # Adaptive density budgeting based on genome rules
        density_rules = getattr(genome, "density_rules", {}) or {}
        max_elems = density_rules.get("max_simultaneous_elements", 16)
        raw_objects = getattr(semantic, "semantic_objects", []) or []
        semantic_objects = raw_objects[:max_elems]
        num_objects = max(1, len(semantic_objects))

        palette = getattr(genome, "palette", {}) or {}
        env_color = palette.get("environment", "#0f172a")
        struct_color = palette.get("structural_neutral", "#1e293b")
        primary_color = palette.get("primary_info", "#f8fafc")
        accent_color = palette.get("accent", "#0ea5e9")
        highlight_color = palette.get("highlight", "#f59e0b")

        # 2D Elements layout calculation based on representation_type
        for i, obj in enumerate(semantic_objects):
            if rep_type in ("COMPARISON", "BEFORE_AFTER"):
                col_w = 480.0
                x = 100.0 if i % 2 == 0 else 660.0
                y = 160.0 + (i // 2) * 260.0
                w, h = col_w, 240.0
            elif rep_type in ("TIMELINE", "SEQUENCE"):
                step_x = 1080.0 / max(1, num_objects)
                x = 80.0 + i * step_x
                y = 180.0 if (i % 2 == 0) else 340.0
                w, h = min(220.0, step_x - 20.0), 140.0
            elif rep_type in ("HIERARCHY", "DECISION_TREE"):
                if i == 0:
                    x, y, w, h = 480.0, 150.0, 320.0, 100.0
                else:
                    child_x = 80.0 + (i - 1) * (1120.0 / max(1, num_objects - 1))
                    x, y, w, h = child_x, 320.0, 240.0, 120.0
            elif rep_type in ("NETWORK", "GRAPH"):
                angle = (i * 2 * math.pi) / num_objects
                radius = 200.0 if i > 0 else 0.0
                x = 560.0 + radius * math.cos(angle)
                y = 280.0 + radius * math.sin(angle) * 0.7
                w, h = 160.0, 90.0
            elif rep_type in ("QUANTITATIVE", "STAT_GRID", "CHART"):
                card_w = 1120.0 / max(1, num_objects)
                x = 80.0 + i * card_w
                y = 180.0
                w, h = min(320.0, card_w - 30.0), 260.0
            elif rep_type in ("SYSTEM_ARCHITECTURE", "LAYER_STACK"):
                x = 120.0
                y = 160.0 + i * 110.0
                w, h = 1040.0, 85.0
            elif rep_type in ("OBJECT_FOCUS", "CONCEPTUAL_METAPHOR"):
                if i == 0:
                    x, y, w, h = 420.0, 180.0, 440.0, 220.0
                else:
                    x = 100.0 if i % 2 == 1 else 900.0
                    y = 160.0 + (i // 2) * 140.0
                    w, h = 240.0, 110.0
            else:
                spacing = 1120.0 / max(1, num_objects)
                x = 80.0 + i * spacing
                y = 180.0
                w, h = min(280.0, spacing - 24.0), 220.0

            elem_fill = accent_color if obj.role == "primary" else struct_color
            elements_2d.append(ExecutableElement2D(
                element_id=obj.object_id,
                layer="node" if obj.role == "primary" else "text",
                compositor=rep_type,
                layout_bounds={"x": float(x), "y": float(y), "width": float(w), "height": float(h)},
                style={
                    "fill": elem_fill,
                    "accent": accent_color,
                    "highlight": highlight_color,
                    "text_color": primary_color,
                    "label": obj.label,
                },
            ))

            if getattr(semantic, "use_3d", False):
                nodes_3d.append(ExecutableNode3D(
                    node_id=f"node_3d_{obj.object_id}",
                    procedural_type=obj.semantic_type,
                    transform={"position": [float(i * 2.5), 0.0, 0.0], "rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]},
                    material_spec={"color": accent_color, "roughness": 0.35},
                ))

        # Convert SceneBeats to serializable dictionaries for canvas player
        raw_beats = getattr(semantic, "scene_beats", []) or []
        compiled_beats = [
            (b.__dict__ if hasattr(b, "__dict__") else b)
            for b in raw_beats
        ]

        trans_in = getattr(semantic, "transition_in", "MATCH_TRANSITION")
        trans_out = getattr(semantic, "transition_out", "CARRY")

        return ExecutableSceneProgram(
            scene_id=semantic.scene_id,
            sequence=semantic.sequence,
            duration_sec=semantic.suggested_duration_sec,
            representation_type=rep_type,
            elements_2d=elements_2d,
            nodes_3d=nodes_3d,
            camera_path=[{"time": 0.0, "type": semantic.shot_grammar}],
            scene_beats=compiled_beats,
            transition_in=trans_in,
            transition_out=trans_out,
        )

    def export_job(self, job_id: str, fps: int = 30) -> Dict[str, Any]:
        """Trigger deterministic frame rendering & MP4 video generation."""
        with self._lock:
            job = self.jobs.get(job_id)

        if job:
            job.update_export_status(ExportStateV3.EXPORTING, 10)

        try:
            from voice_flow.video_flow_v3.export.renderer import video_renderer_v3
            mp4_path = video_renderer_v3.export_job_mp4(job_id=job_id, fps=fps)

            if job:
                job.update_export_status(ExportStateV3.EXPORTED, 100)

            download_url = f"/api/video-flow/v3/video?id={job_id}&download=1"
            return {
                "success": True,
                "job_id": job_id,
                "export_status": ExportStateV3.EXPORTED.value,
                "file_path": str(mp4_path),
                "download_url": download_url,
            }
        except Exception as exc:
            log.error("Export for job %s failed: %s", job_id, exc, exc_info=True)
            if job:
                job.update_export_status(ExportStateV3.FAILED)
            raise


video_flow_v3_service = VideoFlowV3Service()


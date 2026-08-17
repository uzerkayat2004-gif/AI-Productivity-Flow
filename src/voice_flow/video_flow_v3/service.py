"""Master Orchestrator Service for Video Flow V3.

Coordinates:
SourceBundle -> SourceNormalizer -> EvidenceGraph -> CoverageLedger ->
CreativeDirector -> ArtDirectionGenome -> VideoProgramV3 ->
Deterministic Compilers -> Segmented TTS -> READY_TO_WATCH -> Player
"""

from __future__ import annotations

import logging
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

log = logging.getLogger(__name__)


class VideoFlowV3Service:
    """Master backend service for Video Flow V3 visual explanation engine."""

    def __init__(self) -> None:
        self.jobs: Dict[str, JobV3] = {}
        self._lock = threading.Lock()
        self.director = CreativeDirectorV3()

    def create_job(
        self,
        source_text: str,
        mode: str = "summary",
        title: str = "",
        visual_style: str = "Auto",
        job_id: str | None = None,
        model_ref: str = "local/deterministic",
        visual_direction: str = "",
        allow_external_ai: bool = True,
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
            # Stage 1: Normalize Source & Segment Units
            job.update_status(GenerationStateV3.NORMALIZING_SOURCE, "Normalizing source...", 10)
            bundle = SourceBundle(source_text=job.source_text, source_name=job.title)
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

            # Stage 3: Creative Director & Art Direction Genome
            job.update_status(GenerationStateV3.DIRECTING, "Directing visual explanation...", 40)
            resolver = ArtDirectionResolverV3()
            genome = resolver.resolve(source_text=bundle.source_text, source_hash=bundle.source_hash, family_override=visual_style)
            program = self.director.build_program(
                bundle, units, evidence, ledger, genome,
                mode=job.mode, title=job.title,
                model_ref=getattr(job, "model_ref", "local/deterministic"),
                visual_direction=getattr(job, "visual_direction", ""),
                allow_external_ai=getattr(job, "allow_external_ai", True),
            )
            project_store_v3.save_json_artifact(job_id, "art_genome.json", genome)
            project_store_v3.save_json_artifact(job_id, "video_program.json", program)

            job.planned_scenes = len(program.scenes)

            if job.is_cancelled():
                return

            # Stage 4: Compile Scenes & Synthesize Narration Segment 1
            job.update_status(GenerationStateV3.COMPILING_INITIAL, "Preparing first scenes...", 60)
            compiled_scenes: List[ExecutableSceneProgram] = []

            for idx, scene_semantic in enumerate(program.scenes):
                if job.is_cancelled():
                    return

                # Deterministic Visual Compiler (Python side)
                executable_scene = self._compile_scene_deterministically(scene_semantic, genome)
                executable_scene = repair_ladder_v3.simplify_scene_for_performance(executable_scene)
                project_store_v3.save_compiled_scene(job_id, executable_scene.scene_id, executable_scene)

                # Segmented TTS Audio Synthesis for Scene
                audio_path = project_store_v3.get_audio_segment_path(job_id, executable_scene.scene_id)
                if not audio_path.exists() or audio_path.stat().st_size == 0:
                    audio_bytes = tts_engine._synthesize(scene_semantic.narration_text, "deepgram/aura-zeus-en")
                    if audio_bytes:
                        with open(audio_path, "wb") as af:
                            af.write(audio_bytes)

                # Fix 4-5s duration limit & null duration_sec: Probe REAL audio duration and update scene timeline
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

            # Master audio concatenation for continuous full-length video playback
            all_audio_files = [str(project_store_v3.get_audio_segment_path(job_id, s.scene_id)) for s in compiled_scenes]
            master_audio_path = str(project_store_v3.get_project_dir(job_id) / "master_narration.mp3")
            concatenate_narration_audio(all_audio_files, master_audio_path)

            master_audio_dur = probe_audio_duration_sec(master_audio_path)
            if master_audio_dur > 0 and program.scenes:
                scene_count = len(program.scenes)
                per_scene_dur = max(3.5, round(master_audio_dur / scene_count, 2))
                for s in program.scenes:
                    s.suggested_duration_sec = per_scene_dur
                    s.duration_sec = per_scene_dur
                for s in compiled_scenes:
                    s.duration_sec = per_scene_dur
                program.total_estimated_duration_sec = master_audio_dur

            project_store_v3.save_json_artifact(job_id, "video_program.json", program)

            job.program_complete = True
            job.update_status(GenerationStateV3.COMPLETE, "Complete", 100)
            log.info(f"Job {job_id} V3 generation complete with {len(compiled_scenes)} scenes.")

        except Exception as exc:
            log.error(f"Job {job_id} failed: {exc}", exc_info=True)
            job.error = str(exc)
            job.update_status(GenerationStateV3.FAILED, f"Generation failed: {exc}")

    def _compile_scene_deterministically(
        self,
        semantic: Any,
        genome: Any,
    ) -> ExecutableSceneProgram:
        """Deterministic Compiler Layer: converts semantic intent to layout bounds & transforms."""
        elements_2d: List[ExecutableElement2D] = []
        nodes_3d: List[ExecutableNode3D] = []

        # 2D Elements layout calculation (Process / Comparison / Timeline)
        for i, obj in enumerate(semantic.semantic_objects):
            x = 80 + (i % 3) * 360
            y = 120 + (i // 3) * 220
            elements_2d.append(ExecutableElement2D(
                element_id=obj.object_id,
                layer="node" if obj.role == "primary" else "text",
                compositor="Process" if semantic.motion_purpose == "flow" else "Comparison",
                layout_bounds={"x": float(x), "y": float(y), "width": 320.0, "height": 180.0},
                style={"fill": genome.palette.get("surface", "#1e293b"), "accent": genome.palette.get("accent", "#ff6b00")},
            ))

            if semantic.use_3d:
                nodes_3d.append(ExecutableNode3D(
                    node_id=f"node_3d_{obj.object_id}",
                    procedural_type=obj.semantic_type,
                    transform={"position": [float(i * 2.5), 0.0, 0.0], "rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]},
                    material_spec={"color": genome.palette.get("accent", "#ff6b00"), "roughness": 0.3},
                ))

        return ExecutableSceneProgram(
            scene_id=semantic.scene_id,
            sequence=semantic.sequence,
            duration_sec=semantic.suggested_duration_sec,
            elements_2d=elements_2d,
            nodes_3d=nodes_3d,
            camera_path=[{"time": 0.0, "type": semantic.shot_grammar}],
        )


video_flow_v3_service = VideoFlowV3Service()

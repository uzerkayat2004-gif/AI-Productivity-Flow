"""Semantic Creative Director & Mode Policy Engine for Video Flow V3.

SECURITY & ARCHITECTURAL INVARIANT:
- Authors SEMANTIC INTENT ONLY (teaching goals, viewer questions, narrative beats, shot grammar, motion purpose).
- NEVER outputs executable code (no eval, no JS/Python/shaders/HTML/SVG).
- NEVER outputs raw pixel coordinates (x, y) or camera XYZ.
- Deterministic compiler resolves implementation coordinates and rendering.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from voice_flow.video_flow_v3.contracts import (
    SourceBundle,
    SourceUnit,
    EvidenceGraph,
    CoverageLedger,
    ArtDirectionGenome,
    SceneSemanticV3,
    SemanticObject,
    SemanticRepresentationType,
    VideoProgramV3,
    FidelityClass3D,
    validate_no_executable_code,
)
from voice_flow.video_flow_v3.evidence.builder import SpatialAffordanceAnalyzer

log = logging.getLogger(__name__)


class CreativeDirectorV3:
    """Authors high-level semantic video programs without low-level renderer coordinates."""

    def __init__(self, model_gateway: Any = None) -> None:
        self.model_gateway = model_gateway

    def build_program(
        self,
        bundle: SourceBundle,
        units: List[SourceUnit],
        evidence: EvidenceGraph,
        ledger: CoverageLedger,
        genome: ArtDirectionGenome,
        mode: str = "summary",
        title: str = "Visual Explanation",
        model_ref: str = "local/deterministic",
        visual_direction: str = "",
        allow_external_ai: bool = False,
    ) -> VideoProgramV3:
        if not units:
            return VideoProgramV3(title=title, mode=mode)

        from voice_flow.video_flow_v3.director.gateway import V3CreativeDirectorGateway
        gateway = V3CreativeDirectorGateway(model_gateway=self.model_gateway)
        scenes = gateway.author_semantic_plan(
            bundle, units, evidence, genome,
            mode=mode, model_ref=model_ref,
            visual_direction=visual_direction,
            allow_external_ai=allow_external_ai,
        )
        chapters: List[Dict[str, Any]] = []

        program = VideoProgramV3(
            project_id=bundle.source_hash,
            mode=mode,
            title=title,
            source_hash=bundle.source_hash,
            art_genome=genome,
            chapters=chapters,
            scenes=scenes,
            coverage_summary={"total_units": ledger.total_units, "coverage_ratio": ledger.coverage_ratio},
            total_estimated_duration_sec=sum(s.suggested_duration_sec for s in scenes),
        )

        # Enforce Security Boundary Gate
        validate_no_executable_code(program)
        return program

    def _plan_summary_scenes(
        self,
        units: List[SourceUnit],
        evidence: EvidenceGraph,
        genome: ArtDirectionGenome,
    ) -> List[SceneSemanticV3]:
        """Build 4-8 semantic summary scenes preserving essential claims & thesis."""
        scenes: List[SceneSemanticV3] = []
        # Hook scene
        scenes.append(SceneSemanticV3(
            scene_id="scene_0",
            chapter_id="chap_0",
            sequence=0,
            teaching_goal="Introduce central thesis and primary topic",
            viewer_question="What is the core subject of this explanation?",
            intended_understanding=units[0].normalized_text[:120] if units else "Core topic introduction",
            narration_text=units[0].normalized_text if units else "Welcome to this explanation.",
            representation_type=SemanticRepresentationType.OBJECT_FOCUS.value,
            semantic_objects=[
                SemanticObject(object_id="obj_hero", label=units[0].normalized_text[:40] if units else "Topic", role="primary", semantic_type="object_focus")
            ],
            motion_purpose="reveal",
            shot_grammar="HeroFocus",
            suggested_duration_sec=4.5,
            duration_sec=4.5,
            evidence_refs=[units[0].unit_id] if units else [],
        ))

        # Core understanding scenes (chunking units into ~4 scenes)
        chunk_size = max(1, len(units) // 4)
        for i in range(1, len(units), chunk_size):
            chunk_units = units[i : i + chunk_size]
            if not chunk_units:
                continue
            seq = len(scenes)
            combined_text = " ".join(u.normalized_text for u in chunk_units)
            rep_type = SemanticRepresentationType.PROCESS.value
            if "versus" in combined_text.lower() or "than" in combined_text.lower() or "compared" in combined_text.lower():
                rep_type = SemanticRepresentationType.COMPARISON.value
            scenes.append(SceneSemanticV3(
                scene_id=f"scene_{seq}",
                chapter_id="chap_0",
                sequence=seq,
                teaching_goal=f"Explain key evidence beat {seq}",
                viewer_question="How does this core component work?",
                intended_understanding=chunk_units[0].normalized_text[:120],
                narration_text=combined_text,
                representation_type=rep_type,
                semantic_objects=[
                    SemanticObject(
                        object_id=f"obj_{seq}",
                        label=u.normalized_text[:35],
                        role="primary" if idx == 0 else "secondary",
                        semantic_type=rep_type.lower(),
                    )
                    for idx, u in enumerate(chunk_units[:3])
                ],
                motion_purpose="compare" if rep_type == SemanticRepresentationType.COMPARISON.value else "flow",
                shot_grammar="Inspect" if seq % 2 == 1 else "HeroFocus",
                suggested_duration_sec=5.5,
                duration_sec=5.5,
                evidence_refs=[u.unit_id for u in chunk_units],
            ))
            if len(scenes) >= 8:
                break

        return scenes

    def _plan_full_scenes(
        self,
        units: List[SourceUnit],
        evidence: EvidenceGraph,
        genome: ArtDirectionGenome,
    ) -> Tuple[List[SceneSemanticV3], List[Dict[str, Any]]]:
        """Build progressive chaptered scenes for 100% SourceUnit accounting."""
        scenes: List[SceneSemanticV3] = []
        chapters: List[Dict[str, Any]] = []
        current_chap_id = "chap_0"
        chapters.append({"chapter_id": current_chap_id, "title": "Section 1", "sequence": 0})

        for seq, unit in enumerate(units):
            if unit.content_type == "heading":
                current_chap_id = f"chap_{len(chapters)}"
                chapters.append({"chapter_id": current_chap_id, "title": unit.normalized_text, "sequence": len(chapters)})

            rep_type = SemanticRepresentationType.CODE_EXPLANATION.value if unit.content_type == "code_block" else SemanticRepresentationType.PROCESS.value

            scenes.append(SceneSemanticV3(
                scene_id=f"scene_{seq}",
                chapter_id=current_chap_id,
                sequence=seq,
                teaching_goal=f"Explain SourceUnit {unit.unit_id}",
                viewer_question="What does this paragraph specify?",
                intended_understanding=unit.normalized_text[:120],
                narration_text=unit.normalized_text,
                representation_type=rep_type,
                semantic_objects=[
                    SemanticObject(
                        object_id=f"obj_full_{seq}",
                        label=unit.normalized_text[:40],
                        role="primary",
                        semantic_type=rep_type.lower(),
                    )
                ],
                motion_purpose="reveal",
                shot_grammar="HeroFocus",
                suggested_duration_sec=4.0,
                duration_sec=4.0,
                evidence_refs=[unit.unit_id],
            ))

        return scenes, chapters

    def _plan_spatial_3d_scenes(
        self,
        units: List[SourceUnit],
        evidence: EvidenceGraph,
        genome: ArtDirectionGenome,
    ) -> List[SceneSemanticV3]:
        """Build 3D explanation scenes with F1-F4 fidelity classifications."""
        scenes: List[SceneSemanticV3] = []
        for seq, unit in enumerate(units):
            text = unit.normalized_text
            fidelity = SpatialAffordanceAnalyzer.classify_fidelity(text, mode="spatial_3d")
            use_3d = fidelity in (FidelityClass3D.F1_PHYSICAL, FidelityClass3D.F2_SCHEMATIC, FidelityClass3D.F3_CONCEPTUAL)

            spatial_types = SpatialAffordanceAnalyzer.extract_spatial_types(text)
            sem_type = "Assembly" if "assembly" in spatial_types else ("FlowPath" if "flow" in spatial_types else "Component")
            rep_type = SemanticRepresentationType.ASSEMBLY_3D.value if use_3d else SemanticRepresentationType.OBJECT_FOCUS.value

            scenes.append(SceneSemanticV3(
                scene_id=f"scene_{seq}",
                chapter_id="chap_3d",
                sequence=seq,
                teaching_goal=f"Spatial 3D explanation for {unit.unit_id}",
                viewer_question="How is this structured physically or spatially?",
                intended_understanding=text[:120],
                narration_text=text,
                representation_type=rep_type,
                semantic_objects=[
                    SemanticObject(
                        object_id=f"obj_3d_{seq}",
                        label=unit.normalized_text[:40],
                        role="primary",
                        semantic_type=sem_type,
                    )
                ],
                motion_purpose="explode" if "exploded" in text.lower() else ("flow" if "flow" in text.lower() else "focus"),
                shot_grammar="ExplodedAssembly" if "exploded" in text.lower() else "HeroFocus",
                suggested_duration_sec=5.0,
                duration_sec=5.0,
                use_3d=use_3d,
                fidelity_3d=fidelity,
                evidence_refs=[unit.unit_id],
            ))
            if len(scenes) >= 6:
                break

        return scenes

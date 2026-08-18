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

        # Build structured chapters from scenes
        chapters: List[Dict[str, Any]] = []
        seen_chapters = set()
        for s in scenes:
            if s.chapter_id not in seen_chapters:
                seen_chapters.add(s.chapter_id)
                chapters.append({
                    "chapter_id": s.chapter_id,
                    "title": s.teaching_goal[:40],
                    "sequence": len(chapters),
                })

        # Update CoverageLedger items with unit accounting classifications
        unit_scene_map: Dict[str, List[str]] = {}
        unit_disp_map: Dict[str, str] = {}
        for s in scenes:
            for ref in s.evidence_refs:
                unit_scene_map.setdefault(ref, []).append(s.scene_id)
            for ref, disp in s.source_unit_dispositions.items():
                unit_disp_map[ref] = disp

        for item in ledger.items:
            item.scene_refs = unit_scene_map.get(item.unit_id, [])
            item.disposition = unit_disp_map.get(item.unit_id, "covered_both" if item.scene_refs else "unresolved")

        covered_count = sum(1 for item in ledger.items if item.scene_refs or item.disposition in ("covered_both", "covered_narration", "covered_visual", "merged", "included"))
        ledger.coverage_ratio = round(covered_count / max(1, len(ledger.items)), 2)

        program = VideoProgramV3(
            project_id=bundle.source_hash,
            mode=mode,
            title=title,
            source_hash=bundle.source_hash,
            art_genome=genome,
            chapters=chapters,
            scenes=scenes,
            coverage_summary={
                "total_units": ledger.total_units,
                "coverage_ratio": ledger.coverage_ratio,
                "analyzed_units": ledger.analyzed_units,
            },
            total_estimated_duration_sec=round(sum(s.suggested_duration_sec for s in scenes), 2),
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
        """Build 4-8 semantic summary scenes with adaptive duration and internal scene beats."""
        from voice_flow.video_flow_v3.director.gateway import V3CreativeDirectorGateway
        gateway = V3CreativeDirectorGateway(model_gateway=self.model_gateway)
        return gateway._plan_summary_scenes(units, genome)

    def _plan_full_scenes(
        self,
        units: List[SourceUnit],
        evidence: EvidenceGraph,
        genome: ArtDirectionGenome,
    ) -> Tuple[List[SceneSemanticV3], List[Dict[str, Any]]]:
        """Build progressive chaptered scenes for 100% SourceUnit accounting."""
        from voice_flow.video_flow_v3.director.gateway import V3CreativeDirectorGateway
        gateway = V3CreativeDirectorGateway(model_gateway=self.model_gateway)
        scenes = gateway._plan_full_scenes(units, genome)
        chapters: List[Dict[str, Any]] = []
        seen = set()
        for s in scenes:
            if s.chapter_id not in seen:
                seen.add(s.chapter_id)
                chapters.append({"chapter_id": s.chapter_id, "title": s.teaching_goal[:40], "sequence": len(chapters)})
        return scenes, chapters

    def _plan_spatial_3d_scenes(
        self,
        units: List[SourceUnit],
        evidence: EvidenceGraph,
        genome: ArtDirectionGenome,
    ) -> List[SceneSemanticV3]:
        """Build 3D explanation scenes with F1-F4 fidelity classifications."""
        from voice_flow.video_flow_v3.director.gateway import V3CreativeDirectorGateway
        gateway = V3CreativeDirectorGateway(model_gateway=self.model_gateway)
        return gateway._plan_spatial_3d_scenes(units, genome)

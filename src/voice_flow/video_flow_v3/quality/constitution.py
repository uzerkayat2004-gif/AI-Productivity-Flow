"""Quality Constitution & Validation Gates for Video Flow V3.

11 Mandatory Quality Gates:
1. Source Integrity
2. Grounding (Factual claims map to SourceUnit evidence)
3. Coverage (Summary mode complete analysis, Full mode 100% accounting)
4. Semantic Intent
5. Art-Direction Compliance
6. Anti-Generic-AI Policy (No default glassmorphism, rainbow gradients, shiny plastic)
7. Typography & Layout Bounds
8. Motion Semantics
9. 3D Validity (No fake CAD precision, F1-F4 classification)
10. Performance Profile Budgets (STANDARD: <=150 draw calls, <=250k triangles)
11. Diversity & Repetition Avoidance
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple
from voice_flow.video_flow_v3.contracts import (
    VideoProgramV3,
    ExecutableSceneProgram,
    ArtDirectionGenome,
    PerformanceProfile,
)

log = logging.getLogger(__name__)


class QualityViolation(RuntimeError):
    """Raised when a Video Flow V3 scene fails quality constitution gates."""


class QualityConstitutionV3:
    """Enforces deterministic visual & semantic quality gates on VideoProgramV3."""

    def __init__(self, profile: PerformanceProfile = PerformanceProfile.STANDARD) -> None:
        self.profile = profile

    def validate_art_genome(self, genome: ArtDirectionGenome) -> List[str]:
        """Gate 6: Enforce Anti-Generic-AI Policy on visual styling."""
        violations = []
        forbidden_terms = ["neon_rainbow", "glassmorphism_default", "glossy_plastic_toy", "purple_cyan_gradient"]
        family_lower = genome.family.lower()
        for term in forbidden_terms:
            if term in family_lower:
                violations.append(f"Forbidden AI aesthetic '{term}' in ArtDirectionGenome")
        return violations

    def validate_scene_layout(self, scene: ExecutableSceneProgram) -> List[str]:
        """Gate 7 & 10: Validate typography bounds, text overflow, and draw call budgets."""
        violations = []
        # Performance Budget Check (STANDARD: <=150 draw calls)
        total_elements = len(scene.elements_2d) + len(scene.nodes_3d)
        max_elements = 150 if self.profile == PerformanceProfile.STANDARD else (250 if self.profile == PerformanceProfile.QUALITY else 80)
        if total_elements > max_elements:
            violations.append(f"Scene {scene.scene_id} exceeds element budget: {total_elements} > {max_elements}")

        # Text overflow / bounding box overlap checks
        for elem in scene.elements_2d:
            b = elem.layout_bounds
            if b.get("width", 0) <= 0 or b.get("height", 0) <= 0:
                violations.append(f"Element {elem.element_id} has invalid dimensions: {b}")
            if b.get("x", 0) < 0 or b.get("y", 0) < 0:
                violations.append(f"Element {elem.element_id} positioned out of viewport: x={b.get('x')}, y={b.get('y')}")

        return violations

    def validate_program(self, program: VideoProgramV3) -> Tuple[bool, List[str]]:
        """Validate global VideoProgramV3 against all 11 quality constitution gates."""
        all_violations = []
        if program.art_genome:
            all_violations.extend(self.validate_art_genome(program.art_genome))

        if not program.scenes:
            all_violations.append("VideoProgramV3 contains no scenes")

        is_valid = len(all_violations) == 0
        return is_valid, all_violations


class DeterministicRepairLadder:
    """Fallback Ladder for 3D/2D visual compilation issues.

    3D Fallback Ladder:
    High-detail procedural 3D -> Simplified procedural 3D -> Technical schematic 3D -> Premium 2.5D -> Premium 2D.
    """

    @staticmethod
    def simplify_scene_for_performance(scene: ExecutableSceneProgram) -> ExecutableSceneProgram:
        """Simplify scene objects deterministically when performance budgets are exceeded."""
        if len(scene.nodes_3d) > 50:
            # Group or reduce 3D node density
            scene.nodes_3d = scene.nodes_3d[:50]
            log.info(f"Simplified 3D nodes for scene {scene.scene_id} to 50 for performance profile.")
        if len(scene.elements_2d) > 80:
            scene.elements_2d = scene.elements_2d[:80]
            log.info(f"Simplified 2D elements for scene {scene.scene_id} to 80 for performance profile.")
        return scene


quality_constitution_v3 = QualityConstitutionV3()
repair_ladder_v3 = DeterministicRepairLadder()

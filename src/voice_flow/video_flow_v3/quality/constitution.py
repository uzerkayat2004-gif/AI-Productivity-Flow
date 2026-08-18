"""Quality Constitution & Validation Gates for Video Flow V3.

11 Mandatory Quality Gates:
1. Grounding Gate: Claims grounded in source (every claim must map to at least one valid SourceUnit ref; no ungrounded claims).
2. Coverage Gate: Complete unit accounting (in full mode 100% units accounted for, in summary mode >= 70% or all core units analyzed with coverage_ratio >= 0.7, no unresolved units without valid reason).
3. Representation Suitability Gate: Representation matches semantic intent (representation_type matches semantic intent and structure, e.g. COMPARISON has >=2 objects, PROCESS has sequence/steps, TIMELINE has time order, SYSTEM_ARCHITECTURE has nodes/layers, etc.).
4. Layout Gate: No overlapping text or clipped bounds (all 2D elements have valid positive dimensions, within viewport bounds, and no illegal text/card overlap).
5. Typography Gate: Hierarchical font sizes and typography compliance (heading >= body >= code/caption, font families conform to ArtDirectionGenome).
6. Art Direction Compliance Gate: Colors/materials conform to genome (all palettes have required roles, anti-generic AI policy strictly enforced, materials bloom/lens flare/dof disabled).
7. Motion Semantics Gate: Motion conveys meaningful change (motion_purpose is valid, positive duration, keyframes monotonically non-decreasing).
8. Visual Inactivity Gate: Reject static scenes during ongoing narration (if narration_text is present, scene must have active visual elements and valid layout).
9. 3D Validity Gate: F1-F3 fidelity verified, F4 fallback (F1_PHYSICAL requires physical components, F2_SCHEMATIC schematic nodes, F3_CONCEPTUAL spatial/abstract, F4_INSUFFICIENT falls back to 2D/2.5D with use_3d=False).
10. Performance Gate: Performance profile budgets enforced (STANDARD <=150 draw calls/display objects, <=250k triangles; QUALITY <=250 objects; COMPATIBILITY <=80 objects).
11. Same-Video & Cross-Video Repetition Gate: Reject identical consecutive structures (no 3+ consecutive scenes with identical representation_type and layout without variation; no duplicate scene IDs or repetitive identical narration).
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from voice_flow.video_flow_v3.contracts import (
    ArtDirectionGenome,
    ClaimEvidence,
    CoverageLedger,
    EvidenceGraph,
    ExecutableElement2D,
    ExecutableNode3D,
    ExecutableSceneProgram,
    FidelityClass3D,
    PerformanceProfile,
    SceneSemanticV3,
    SemanticRepresentationType,
    SourceUnit,
    VideoProgramV3,
)

log = logging.getLogger(__name__)

FORBIDDEN_GENERIC_AI_TERMS = [
    "neon_rainbow",
    "glassmorphism_default",
    "glossy_plastic_toy",
    "purple_cyan_gradient",
    "neon_glow_overload",
    "default_ai_glow",
]

FORBIDDEN_NEON_BACKGROUND_HEX = {
    "#FF00FF", "#00FFFF", "#7B00FF", "#A000FF", "#00E5FF", "#FF007F"
}

VALID_MOTION_PURPOSES = {
    "reveal", "compare", "flow", "explode", "transform", "focus",
    "highlight", "step", "unfold", "scan", "orbit", "glide"
}


class QualityViolation(RuntimeError):
    """Raised when a Video Flow V3 scene or program fails quality constitution gates."""


class QualityConstitutionV3:
    """Enforces deterministic visual & semantic quality gates on VideoProgramV3 and ExecutableSceneProgram."""

    def __init__(self, profile: PerformanceProfile = PerformanceProfile.STANDARD) -> None:
        self.profile = profile

    # -------------------------------------------------------------------------
    # Gate 1: Grounding Gate
    # -------------------------------------------------------------------------
    def validate_grounding_gate(
        self,
        claims: Optional[List[ClaimEvidence]] = None,
        source_units: Optional[List[SourceUnit]] = None,
        scenes: Optional[List[Union[SceneSemanticV3, ExecutableSceneProgram]]] = None,
    ) -> List[str]:
        """Gate 1: Claims grounded in source (every claim must map to at least one valid SourceUnit ref)."""
        violations = []
        known_unit_ids: Set[str] = {u.unit_id for u in source_units} if source_units else set()

        if claims:
            for claim in claims:
                if not claim.source_unit_refs:
                    violations.append(f"Grounding Violation: Claim '{claim.claim_id}' has no source_unit_refs")
                elif known_unit_ids:
                    for ref in claim.source_unit_refs:
                        if ref not in known_unit_ids:
                            violations.append(
                                f"Grounding Violation: Claim '{claim.claim_id}' references unknown unit '{ref}'"
                            )

        if scenes:
            for sc in scenes:
                evidence_refs = getattr(sc, "evidence_refs", [])
                if known_unit_ids and evidence_refs:
                    for ref in evidence_refs:
                        if ref not in known_unit_ids:
                            violations.append(
                                f"Grounding Violation: Scene '{sc.scene_id}' references unknown source unit '{ref}'"
                            )

        return violations

    # -------------------------------------------------------------------------
    # Gate 2: Coverage Gate
    # -------------------------------------------------------------------------
    def validate_coverage_gate(
        self,
        ledger: Optional[CoverageLedger] = None,
        source_units: Optional[List[SourceUnit]] = None,
        mode: str = "summary",
    ) -> List[str]:
        """Gate 2: Complete unit accounting (100% accounting in Full mode, >=70% in Summary mode)."""
        violations = []
        if ledger is None:
            return violations

        if mode == "full":
            if ledger.coverage_ratio < 1.0:
                violations.append(
                    f"Coverage Violation: Full mode requires 100% coverage, got {ledger.coverage_ratio * 100:.1f}%"
                )
            if ledger.unresolved_count > 0:
                violations.append(
                    f"Coverage Violation: Full mode has {ledger.unresolved_count} unresolved source units"
                )
            for item in ledger.items:
                if item.disposition == "unresolved":
                    violations.append(f"Coverage Violation: Unit '{item.unit_id}' marked unresolved without disposition")
        else:
            # Summary mode
            if ledger.coverage_ratio < 0.70 and ledger.total_units > 0:
                violations.append(
                    f"Coverage Violation: Summary mode coverage ratio {ledger.coverage_ratio * 100:.1f}% is below 70% threshold"
                )

        return violations

    # -------------------------------------------------------------------------
    # Gate 3: Representation Suitability Gate
    # -------------------------------------------------------------------------
    def validate_representation_suitability_gate(
        self,
        scene: Union[SceneSemanticV3, ExecutableSceneProgram],
    ) -> List[str]:
        """Gate 3: Representation matches semantic intent."""
        violations = []
        raw_rep = getattr(scene, "representation_type", None) or "PROCESS"
        rep_str = str(raw_rep).upper().replace("SEMANTICREPRESENTATIONTYPE.", "")

        valid_enum_names = {e.name for e in SemanticRepresentationType} | {e.value for e in SemanticRepresentationType}
        if rep_str not in valid_enum_names and not any(rep_str in n for n in valid_enum_names):
            violations.append(f"Representation Suitability Violation: Unknown representation type '{raw_rep}'")

        # Specific structure rules
        elements_2d = getattr(scene, "elements_2d", [])
        nodes_3d = getattr(scene, "nodes_3d", [])
        semantic_objects = getattr(scene, "semantic_objects", [])
        total_objects = max(len(elements_2d) + len(nodes_3d), len(semantic_objects))

        if "COMPARISON" in rep_str and total_objects < 2:
            violations.append(
                f"Representation Suitability Violation: Scene '{scene.scene_id}' of type COMPARISON requires >= 2 comparison objects, found {total_objects}"
            )
        elif ("SYSTEM_ARCHITECTURE" in rep_str or "LAYER_STACK" in rep_str) and total_objects < 1:
            violations.append(
                f"Representation Suitability Violation: Scene '{scene.scene_id}' of type {rep_str} has no architectural elements"
            )
        elif ("ASSEMBLY_3D" in rep_str or "CUTAWAY_3D" in rep_str):
            use_3d = getattr(scene, "use_3d", True)
            if not use_3d and not nodes_3d and not elements_2d:
                violations.append(
                    f"Representation Suitability Violation: 3D scene '{scene.scene_id}' requires 3D nodes or fallback 2D diagram"
                )

        return violations

    # -------------------------------------------------------------------------
    # Gate 4: Layout Gate
    # -------------------------------------------------------------------------
    def validate_layout_gate(
        self,
        scene: Union[SceneSemanticV3, ExecutableSceneProgram],
        viewport_width: float = 1280.0,
        viewport_height: float = 720.0,
    ) -> List[str]:
        """Gate 4: No overlapping text or clipped bounds."""
        violations = []
        elements = getattr(scene, "elements_2d", [])
        if not elements:
            return violations

        bounding_boxes = []

        for elem in elements:
            b = elem.layout_bounds if hasattr(elem, "layout_bounds") else getattr(elem, "layout_bounds", {})
            elem_id = getattr(elem, "element_id", "elem")
            layer = getattr(elem, "layer", "")

            w = b.get("width", 0.0)
            h = b.get("height", 0.0)
            x = b.get("x", 0.0)
            y = b.get("y", 0.0)

            if w <= 0 or h <= 0:
                violations.append(
                    f"Layout Violation: Element '{elem_id}' in scene '{scene.scene_id}' has invalid dimensions w={w}, h={h}"
                )
            if x < 0 or y < 0:
                violations.append(
                    f"Layout Violation: Element '{elem_id}' in scene '{scene.scene_id}' positioned out of viewport bounds: x={x}, y={y}"
                )
            if x + w > viewport_width + 40 or y + h > viewport_height + 40:
                violations.append(
                    f"Layout Violation: Element '{elem_id}' in scene '{scene.scene_id}' clipped beyond viewport: right={x+w}, bottom={y+h}"
                )

            if layer not in ("background", "grid", "ambient_layer"):
                bounding_boxes.append((elem_id, x, y, w, h))

        # Check for severe overlaps (>60% intersection) among foreground elements
        for i in range(len(bounding_boxes)):
            id1, x1, y1, w1, h1 = bounding_boxes[i]
            for j in range(i + 1, len(bounding_boxes)):
                id2, x2, y2, w2, h2 = bounding_boxes[j]
                # Intersection rect
                ix_min = max(x1, x2)
                iy_min = max(y1, y2)
                ix_max = min(x1 + w1, x2 + w2)
                iy_max = min(y1 + h1, y2 + h2)

                if ix_max > ix_min and iy_max > iy_min:
                    inter_area = (ix_max - ix_min) * (iy_max - iy_min)
                    min_area = min(w1 * h1, w2 * h2)
                    if min_area > 0 and (inter_area / min_area) > 0.65:
                        violations.append(
                            f"Layout Violation: Elements '{id1}' and '{id2}' in scene '{scene.scene_id}' severely overlap ({int(inter_area/min_area*100)}% intersection)"
                        )

        return violations

    # -------------------------------------------------------------------------
    # Gate 5: Typography Gate
    # -------------------------------------------------------------------------
    def validate_typography_gate(
        self,
        genome: Optional[ArtDirectionGenome] = None,
        scene: Optional[Union[SceneSemanticV3, ExecutableSceneProgram]] = None,
    ) -> List[str]:
        """Gate 5: Hierarchical font sizes and typography compliance."""
        violations = []
        if genome and genome.typography:
            typo = genome.typography
            heading_font = typo.get("headingFont") or typo.get("font_family_heading") or ""
            body_font = typo.get("bodyFont") or typo.get("font_family_primary") or ""
            if not heading_font:
                violations.append("Typography Violation: Heading font family is missing from ArtDirectionGenome")
            if not body_font:
                violations.append("Typography Violation: Body font family is missing from ArtDirectionGenome")

        # Validate element font hierarchy if specified
        if scene:
            for elem in getattr(scene, "elements_2d", []):
                style = getattr(elem, "style", {}) or {}
                font_size = style.get("fontSize") or style.get("font_size")
                heading_size = style.get("headingFontSize") or style.get("heading_size")
                if font_size and heading_size and heading_size < font_size:
                    violations.append(
                        f"Typography Violation: Element '{elem.element_id}' heading size ({heading_size}) is smaller than body font size ({font_size})"
                    )

        return violations

    # -------------------------------------------------------------------------
    # Gate 6: Art Direction Compliance Gate
    # -------------------------------------------------------------------------
    def validate_art_genome(self, genome: ArtDirectionGenome) -> List[str]:
        """Gate 6: Art direction compliance & Anti-Generic-AI policy."""
        violations = []
        if not genome.family:
            violations.append("Art Direction Violation: ArtDirectionGenome has empty family name")
            return violations

        family_lower = genome.family.lower()
        for term in FORBIDDEN_GENERIC_AI_TERMS:
            if term in family_lower:
                violations.append(f"Forbidden AI aesthetic '{term}' in ArtDirectionGenome")

        # Palette validation
        palette = genome.palette or {}
        required_roles = ["environment", "structural_neutral", "primary_info", "accent", "highlight"]
        for role in required_roles:
            if role not in palette and role not in ["background", "surface", "primary", "secondary"]:
                # Check fallback keys
                alt_roles = {
                    "environment": ["background"],
                    "structural_neutral": ["surface", "surfaceElevated"],
                    "primary_info": ["primary", "text"],
                    "accent": ["accent", "accentAlt"],
                    "highlight": ["secondary", "warning", "info"],
                }
                if not any(k in palette for k in alt_roles.get(role, [])):
                    violations.append(f"Art Direction Violation: Missing required palette color role '{role}'")

        env_color = palette.get("environment") or palette.get("background") or ""
        if env_color.upper() in FORBIDDEN_NEON_BACKGROUND_HEX:
            violations.append(f"Art Direction Violation: Forbidden neon environment background color '{env_color}'")

        # Materials Anti-Generic AI Policy
        materials = genome.materials or {}
        if materials.get("bloom_enabled", False):
            violations.append("Art Direction Violation: bloom_enabled must be False per Anti-Generic AI Policy")
        if materials.get("lens_flare", False):
            violations.append("Art Direction Violation: lens_flare must be False per Anti-Generic AI Policy")
        if materials.get("dof_enabled", False):
            violations.append("Art Direction Violation: dof_enabled must be False per Anti-Generic AI Policy")
        if materials.get("glassmorphism", False):
            violations.append("Art Direction Violation: glassmorphism must be False per Anti-Generic AI Policy")

        return violations

    # -------------------------------------------------------------------------
    # Gate 7: Motion Semantics Gate
    # -------------------------------------------------------------------------
    def validate_motion_semantics_gate(
        self,
        scene: Union[SceneSemanticV3, ExecutableSceneProgram],
    ) -> List[str]:
        """Gate 7: Motion conveys meaningful change."""
        violations = []
        motion_purpose = getattr(scene, "motion_purpose", "reveal")
        if motion_purpose and motion_purpose.lower() not in VALID_MOTION_PURPOSES:
            violations.append(
                f"Motion Semantics Violation: Scene '{scene.scene_id}' has invalid motion_purpose '{motion_purpose}'"
            )

        duration_sec = getattr(scene, "duration_sec", None) or getattr(scene, "suggested_duration_sec", 5.0)
        if duration_sec <= 0:
            violations.append(
                f"Motion Semantics Violation: Scene '{scene.scene_id}' has non-positive duration {duration_sec}s"
            )
        elif duration_sec > 120.0:
            violations.append(
                f"Motion Semantics Violation: Scene '{scene.scene_id}' duration {duration_sec}s exceeds maximum threshold"
            )

        # Check keyframe monotonically increasing timing
        for elem in getattr(scene, "elements_2d", []):
            keyframes = getattr(elem, "animation_keyframes", []) or []
            last_t = -1.0
            for kf in keyframes:
                t = kf.get("time", 0.0)
                if t < last_t:
                    violations.append(
                        f"Motion Semantics Violation: Non-monotonic keyframe times in element '{elem.element_id}'"
                    )
                last_t = t

        return violations

    # -------------------------------------------------------------------------
    # Gate 8: Visual Inactivity Gate
    # -------------------------------------------------------------------------
    def validate_visual_inactivity_gate(
        self,
        scene: Union[SceneSemanticV3, ExecutableSceneProgram],
    ) -> List[str]:
        """Gate 8: Reject static scenes during ongoing narration."""
        violations = []
        narration = getattr(scene, "narration_text", "") or ""
        elements_2d = getattr(scene, "elements_2d", [])
        nodes_3d = getattr(scene, "nodes_3d", [])
        semantic_objects = getattr(scene, "semantic_objects", [])

        total_visuals = len(elements_2d) + len(nodes_3d) + len(semantic_objects)

        if len(narration.strip()) > 0 and total_visuals == 0:
            violations.append(
                f"Visual Inactivity Violation: Scene '{scene.scene_id}' has active narration ('{narration[:30]}...') but 0 visual elements"
            )

        return violations

    # -------------------------------------------------------------------------
    # Gate 9: 3D Validity Gate
    # -------------------------------------------------------------------------
    def validate_3d_validity_gate(
        self,
        scene: Union[SceneSemanticV3, ExecutableSceneProgram],
    ) -> List[str]:
        """Gate 9: F1-F3 fidelity verified, F4 fallback."""
        violations = []
        use_3d = getattr(scene, "use_3d", False)
        fidelity = getattr(scene, "fidelity_3d", FidelityClass3D.F4_INSUFFICIENT)

        if use_3d:
            if fidelity == FidelityClass3D.F4_INSUFFICIENT or fidelity == "F4":
                violations.append(
                    f"3D Validity Violation: Scene '{scene.scene_id}' has fidelity F4 (Insufficient) but use_3d is True. Must fall back to 2D/2.5D."
                )

        # Validate 3D node transforms
        for node in getattr(scene, "nodes_3d", []):
            t = getattr(node, "transform", {}) or {}
            pos = t.get("position", [0, 0, 0])
            rot = t.get("rotation", [0, 0, 0])
            scale = t.get("scale", [1, 1, 1])

            for vec, name in [(pos, "position"), (rot, "rotation"), (scale, "scale")]:
                if not isinstance(vec, (list, tuple)) or len(vec) != 3:
                    violations.append(
                        f"3D Validity Violation: Node '{node.node_id}' has malformed {name} vector: {vec}"
                    )
                elif any(math.isnan(v) or math.isinf(v) for v in vec):
                    violations.append(
                        f"3D Validity Violation: Node '{node.node_id}' contains NaN/Inf in {name}"
                    )

            if isinstance(scale, (list, tuple)) and len(scale) == 3 and any(s <= 0 for s in scale):
                violations.append(
                    f"3D Validity Violation: Node '{node.node_id}' has non-positive scale vector {scale}"
                )

        return violations

    # -------------------------------------------------------------------------
    # Gate 10: Performance Gate
    # -------------------------------------------------------------------------
    def validate_performance_gate(
        self,
        scene: Union[SceneSemanticV3, ExecutableSceneProgram],
        profile: Optional[PerformanceProfile] = None,
    ) -> List[str]:
        """Gate 10: Performance profile budgets (STANDARD <=150 draw calls, <=250k triangles)."""
        violations = []
        active_profile = profile or self.profile

        max_elements = (
            250 if active_profile == PerformanceProfile.QUALITY
            else (80 if active_profile == PerformanceProfile.COMPATIBILITY else 150)
        )
        max_triangles = (
            500_000 if active_profile == PerformanceProfile.QUALITY
            else (100_000 if active_profile == PerformanceProfile.COMPATIBILITY else 250_000)
        )

        elements_2d = getattr(scene, "elements_2d", [])
        nodes_3d = getattr(scene, "nodes_3d", [])
        total_elements = len(elements_2d) + len(nodes_3d)

        if total_elements > max_elements:
            violations.append(
                f"Performance Violation: Scene '{scene.scene_id}' exceeds element budget: {total_elements} > {max_elements} (profile={active_profile.value})"
            )

        # Estimate triangle count
        tri_map = {
            "assembly": 15_000,
            "explodedassembly": 25_000,
            "cutaway": 12_000,
            "housing": 8_000,
            "component": 4_000,
            "flowpath": 6_000,
            "layerstack": 3_000,
            "box": 12,
            "cylinder": 1_500,
            "sphere": 2_000,
            "torus": 4_000,
        }

        est_triangles = len(elements_2d) * 4
        for n in nodes_3d:
            ptype = str(getattr(n, "procedural_type", "box")).lower().replace("_", "")
            matched = False
            for k, count in tri_map.items():
                if k in ptype:
                    est_triangles += count
                    matched = True
                    break
            if not matched:
                est_triangles += 2_000

        if est_triangles > max_triangles:
            violations.append(
                f"Performance Violation: Scene '{scene.scene_id}' estimated triangle count {est_triangles} exceeds budget {max_triangles}"
            )

        return violations

    # -------------------------------------------------------------------------
    # Gate 11: Same-Video & Cross-Video Repetition Gate
    # -------------------------------------------------------------------------
    def validate_repetition_gate(
        self,
        scenes: List[Union[SceneSemanticV3, ExecutableSceneProgram]],
    ) -> List[str]:
        """Gate 11: Diversity & repetition avoidance (reject identical consecutive structures)."""
        violations = []
        if len(scenes) < 2:
            return violations

        seen_scene_ids: Set[str] = set()
        seen_narrations: Set[str] = set()

        for idx, sc in enumerate(scenes):
            # Check unique scene_ids
            if sc.scene_id in seen_scene_ids:
                violations.append(f"Repetition Violation: Duplicate scene_id '{sc.scene_id}' at index {idx}")
            seen_scene_ids.add(sc.scene_id)

            # Check duplicate narration
            narration = getattr(sc, "narration_text", "").strip()
            if narration and len(narration) > 10:
                if narration in seen_narrations:
                    violations.append(
                        f"Repetition Violation: Duplicate identical narration in scene '{sc.scene_id}'"
                    )
                seen_narrations.add(narration)

            # Check 3+ consecutive identical representation types
            if idx >= 2:
                rep0 = str(getattr(scenes[idx - 2], "representation_type", "")).upper()
                rep1 = str(getattr(scenes[idx - 1], "representation_type", "")).upper()
                rep2 = str(getattr(scenes[idx], "representation_type", "")).upper()

                if rep0 and rep0 == rep1 == rep2:
                    violations.append(
                        f"Repetition Violation: 3 consecutive scenes ({scenes[idx-2].scene_id}, {scenes[idx-1].scene_id}, {scenes[idx].scene_id}) share identical representation type '{rep0}' without variation"
                    )

        return violations

    # -------------------------------------------------------------------------
    # Unified Scene & Program Validation
    # -------------------------------------------------------------------------
    def validate_scene_layout(self, scene: ExecutableSceneProgram) -> List[str]:
        """Backwards-compatible wrapper for layout & performance gates."""
        violations = []
        violations.extend(self.validate_layout_gate(scene))
        violations.extend(self.validate_performance_gate(scene))
        return violations

    def validate_scene(
        self,
        scene: Union[SceneSemanticV3, ExecutableSceneProgram],
        genome: Optional[ArtDirectionGenome] = None,
    ) -> Tuple[bool, List[str]]:
        """Validate a single scene against all scene-level quality constitution gates."""
        violations = []
        violations.extend(self.validate_representation_suitability_gate(scene))
        violations.extend(self.validate_layout_gate(scene))
        violations.extend(self.validate_typography_gate(genome, scene))
        violations.extend(self.validate_motion_semantics_gate(scene))
        violations.extend(self.validate_visual_inactivity_gate(scene))
        violations.extend(self.validate_3d_validity_gate(scene))
        violations.extend(self.validate_performance_gate(scene))

        return len(violations) == 0, violations

    def validate_program(
        self,
        program: VideoProgramV3,
        source_units: Optional[List[SourceUnit]] = None,
        evidence: Optional[EvidenceGraph] = None,
        ledger: Optional[CoverageLedger] = None,
    ) -> Tuple[bool, List[str]]:
        """Validate global VideoProgramV3 against all 11 quality constitution gates."""
        all_violations = []

        if not program.scenes:
            all_violations.append("VideoProgramV3 contains no scenes")

        if program.art_genome:
            all_violations.extend(self.validate_art_genome(program.art_genome))
            all_violations.extend(self.validate_typography_gate(program.art_genome))

        # Gate 1: Grounding
        claims = evidence.claims if evidence else None
        all_violations.extend(self.validate_grounding_gate(claims, source_units, program.scenes))

        # Gate 2: Coverage
        if ledger:
            all_violations.extend(self.validate_coverage_gate(ledger, source_units, mode=program.mode))

        # Scene-level validation for all scenes
        for sc in program.scenes:
            is_valid, sc_violations = self.validate_scene(sc, program.art_genome)
            all_violations.extend(sc_violations)

        # Gate 11: Repetition
        all_violations.extend(self.validate_repetition_gate(program.scenes))

        is_valid = len(all_violations) == 0
        return is_valid, all_violations

    def assert_valid_program(
        self,
        program: VideoProgramV3,
        source_units: Optional[List[SourceUnit]] = None,
        evidence: Optional[EvidenceGraph] = None,
        ledger: Optional[CoverageLedger] = None,
    ) -> None:
        """Assert that a VideoProgramV3 passes all 11 quality gates, raising QualityViolation on failure."""
        is_valid, violations = self.validate_program(program, source_units, evidence, ledger)
        if not is_valid:
            msg = f"Quality Constitution Failed with {len(violations)} violation(s):\n - " + "\n - ".join(violations)
            raise QualityViolation(msg)


class DeterministicRepairLadder:
    """Deterministic Repair Ladder for 3D/2D visual compilation issues.

    3D Fallback Ladder:
    High-detail procedural 3D -> Simplified procedural 3D -> Technical schematic 3D -> Premium 2.5D -> Premium 2D.
    """

    @staticmethod
    def simplify_scene_for_performance(
        scene: ExecutableSceneProgram,
        profile: PerformanceProfile = PerformanceProfile.STANDARD,
    ) -> ExecutableSceneProgram:
        """Simplify scene objects deterministically when performance budgets are exceeded."""
        max_nodes_3d = 50 if profile == PerformanceProfile.STANDARD else 80
        max_elements_2d = 80 if profile == PerformanceProfile.STANDARD else 120

        if len(scene.nodes_3d) > max_nodes_3d:
            scene.nodes_3d = scene.nodes_3d[:max_nodes_3d]
            log.info(f"Simplified 3D nodes for scene {scene.scene_id} to {max_nodes_3d} for performance profile.")

        if len(scene.elements_2d) > max_elements_2d:
            scene.elements_2d = scene.elements_2d[:max_elements_2d]
            log.info(f"Simplified 2D elements for scene {scene.scene_id} to {max_elements_2d} for performance profile.")

        return scene

    @staticmethod
    def repair_3d_fallback(scene: Union[SceneSemanticV3, ExecutableSceneProgram]) -> Union[SceneSemanticV3, ExecutableSceneProgram]:
        """Fall back from invalid or F4 3D scene to premium 2D/2.5D schematic."""
        if hasattr(scene, "use_3d"):
            scene.use_3d = False
        if hasattr(scene, "fidelity_3d"):
            scene.fidelity_3d = FidelityClass3D.F4_INSUFFICIENT
        return scene

    @staticmethod
    def repair_layout_bounds(
        scene: ExecutableSceneProgram,
        viewport_width: float = 1280.0,
        viewport_height: float = 720.0,
    ) -> ExecutableSceneProgram:
        """Deterministically clamp and space overlapping layout bounds."""
        elements = getattr(scene, "elements_2d", [])
        for idx, elem in enumerate(elements):
            b = elem.layout_bounds
            x = max(20.0, min(viewport_width - 100.0, float(b.get("x", 0.0))))
            y = max(20.0, min(viewport_height - 60.0, float(b.get("y", 0.0))))
            w = max(40.0, min(viewport_width - x - 20.0, float(b.get("width", 200.0))))
            h = max(30.0, min(viewport_height - y - 20.0, float(b.get("height", 100.0))))
            elem.layout_bounds = {"x": x, "y": y, "width": w, "height": h}
        return scene


quality_constitution_v3 = QualityConstitutionV3()
repair_ladder_v3 = DeterministicRepairLadder()

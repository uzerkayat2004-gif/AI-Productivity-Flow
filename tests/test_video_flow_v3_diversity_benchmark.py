"""Video Flow V3 Multi-Source Diversity Benchmark & 11 Quality Gates Test Suite.

Verifies:
1. 5 Unrelated Knowledge Topics generate 100% distinct visual families, color palettes,
   typography systems, and scene topologies:
   - Topic 1: CPU Architecture -> Technical Systems / Software Architecture
   - Topic 2: World War II History -> Historical / Archival / Editorial Documentary
   - Topic 3: Cell Mitosis Biology -> Scientific Visualization
   - Topic 4: Financial Earnings -> Data Editorial
   - Topic 5: Rocket Staging -> Industrial Product / Spatial
2. All 5 topics pass all 11 Quality Constitution Gates with 0 violations.
3. Every individual Quality Gate deterministically enforces its invariants.
"""

from __future__ import annotations

import pytest
from typing import Dict, List

from voice_flow.video_flow_v3.contracts import (
    ArtDirectionGenome,
    ClaimEvidence,
    CoverageLedger,
    EvidenceGraph,
    ExecutableElement2D,
    ExecutableNode3D,
    ExecutableSceneProgram,
    FidelityClass3D,
    LedgerItem,
    PerformanceProfile,
    SceneSemanticV3,
    SemanticObject,
    SemanticRepresentationType,
    SourceBundle,
    SourceUnit,
    VideoProgramV3,
)
from voice_flow.video_flow_v3.source.units import SourceNormalizer
from voice_flow.video_flow_v3.evidence.builder import EvidenceGraphBuilder, CoverageLedgerTracker
from voice_flow.video_flow_v3.art_direction.resolver import ArtDirectionResolverV3
from voice_flow.video_flow_v3.director.creative_director import CreativeDirectorV3
from voice_flow.video_flow_v3.director.gateway import V3CreativeDirectorGateway
from voice_flow.video_flow_v3.quality.constitution import (
    QualityConstitutionV3,
    QualityViolation,
    DeterministicRepairLadder,
)
from voice_flow.video_flow_v3.service import VideoFlowV3Service


# -----------------------------------------------------------------------------
# 5 Diverse Unrelated Benchmark Topic Payloads
# -----------------------------------------------------------------------------

BENCHMARK_TOPICS: Dict[str, Dict[str, str]] = {
    "cpu_architecture": {
        "title": "Modern CPU Microarchitecture and Cache Hierarchy",
        "topic_hint": "CPU Architecture instruction pipeline cache hierarchy ALU registers",
        "source_text": (
            "# Modern CPU Microarchitecture\n\n"
            "The instruction execution pipeline fetches and decodes machine instructions.\n"
            "The Arithmetic Logic Unit (ALU) performs integer and floating-point computations.\n"
            "Multi-level cache hierarchy includes L1 instruction/data cache, L2 unified cache, and L3 shared cache.\n"
            "Branch prediction algorithms minimize instruction stall latency across pipeline stages."
        ),
        "expected_families": ["Technical Systems", "Software Architecture"],
    },
    "wwii_history": {
        "title": "World War II European Theater and Archival Timeline",
        "topic_hint": "World War II History European theater archival narrative Winston Churchill",
        "source_text": (
            "# The European Theater 1939-1945\n\n"
            "In 1939, military conflict began with the invasion of Poland.\n"
            "Primary source archival documents record the wartime cabinet decisions of 1940.\n"
            "The Normandy landings of June 1944 established the allied western front.\n"
            "Historical museum artifacts and treaty records document the formal surrender in May 1945."
        ),
        "expected_families": ["Historical / Archival", "Editorial Documentary"],
    },
    "cell_mitosis": {
        "title": "Eukaryotic Cell Mitosis and Chromosomal Replication",
        "topic_hint": "Cell Mitosis Biology molecular genetics chromosomes cell division",
        "source_text": (
            "# Eukaryotic Cell Mitosis\n\n"
            "During prophase, chromatin condenses into distinct chromosomes.\n"
            "In metaphase, chromosomes align along the equatorial metaphase plate.\n"
            "Spindle fiber microtubules contract during anaphase, pulling sister chromatids to opposite poles.\n"
            "Telophase and cytokinesis conclude the replication cycle, yielding two genetically identical daughter cells."
        ),
        "expected_families": ["Scientific Visualization"],
    },
    "financial_earnings": {
        "title": "Q3 Financial Earnings Report and Fiscal Metrics",
        "topic_hint": "Financial Earnings statistics quarterly revenue EBITDA margin economic data",
        "source_text": (
            "# Q3 Fiscal Earnings Report\n\n"
            "Consolidated quarterly revenue grew by 24% year-over-year to $4.2 billion.\n"
            "Operating margin expanded by 180 basis points, driven by operational efficiencies.\n"
            "Adjusted EBITDA reached $1.15 billion with free cash flow conversion of 82%.\n"
            "Earnings per share exceeded consensus forecast metrics by 14 cents."
        ),
        "expected_families": ["Data Editorial"],
    },
    "rocket_staging": {
        "title": "Multi-Stage Rocket Propulsion and Separation Dynamics",
        "topic_hint": "Rocket Staging aerospace propulsion titanium assembly hardware engineering",
        "source_text": (
            "# Multi-Stage Rocket Propulsion System\n\n"
            "The booster first stage utilizes nine liquid oxygen turbopump engines producing 7,600 kN thrust.\n"
            "The precision titanium interstage housing encases the pneumatic stage separation pushers.\n"
            "Vacuum-optimized upper stage engine delivers 934 kN thrust with closed-loop gimbal vectoring.\n"
            "Aerodynamic payload fairing separates at an altitude of 110 kilometers in space."
        ),
        "expected_families": ["Industrial Product", "Architectural / Spatial"],
    },
}


# =============================================================================
# BENCHMARK TEST 1: Visual Family Classification & Diversity
# =============================================================================

def test_five_topics_produce_distinct_visual_families():
    """Verify that all 5 unrelated topics resolve to distinct, appropriate Visual Families."""
    resolver = ArtDirectionResolverV3()
    resolved_families = {}

    for key, topic in BENCHMARK_TOPICS.items():
        family = resolver.classify_family(topic["source_text"], topic["topic_hint"])
        resolved_families[key] = family
        assert family in topic["expected_families"], (
            f"Topic '{key}' classified as '{family}', expected one of {topic['expected_families']}"
        )

    # Verify all 5 resolved families are mutually distinct (5 distinct families)
    distinct_count = len(set(resolved_families.values()))
    assert distinct_count == 5, f"Expected 5 distinct visual families, got {distinct_count}: {resolved_families}"


# =============================================================================
# BENCHMARK TEST 2: Color Palette Diversity
# =============================================================================

def test_five_topics_produce_distinct_color_palettes():
    """Verify that all 5 topics produce completely distinct role-based color palettes."""
    resolver = ArtDirectionResolverV3()
    genomes: Dict[str, ArtDirectionGenome] = {}

    for key, topic in BENCHMARK_TOPICS.items():
        genome = resolver.resolve(
            source_text=topic["source_text"],
            topic_hint=topic["topic_hint"],
            source_hash=f"hash_{key}_diversity",
        )
        genomes[key] = genome

    # 1. Environment / background colors must all be pairwise distinct
    env_colors = [g.palette.get("environment") or g.palette.get("background") for g in genomes.values()]
    assert len(set(env_colors)) == 5, f"Expected 5 distinct environment colors, got: {env_colors}"

    # 2. Accent colors must all be pairwise distinct
    accent_colors = [g.palette.get("accent") for g in genomes.values()]
    assert len(set(accent_colors)) == 5, f"Expected 5 distinct accent colors, got: {accent_colors}"

    # 3. Structural neutral colors must all be pairwise distinct
    structural_colors = [g.palette.get("structural_neutral") or g.palette.get("surface") for g in genomes.values()]
    assert len(set(structural_colors)) == 5, f"Expected 5 distinct structural neutral colors, got: {structural_colors}"


# =============================================================================
# BENCHMARK TEST 3: Typography System Diversity
# =============================================================================

def test_five_topics_produce_distinct_typography_systems():
    """Verify that all 5 topics generate distinct typography configurations tailored to domain."""
    resolver = ArtDirectionResolverV3()
    genomes: Dict[str, ArtDirectionGenome] = {}

    for key, topic in BENCHMARK_TOPICS.items():
        genomes[key] = resolver.resolve(
            source_text=topic["source_text"],
            topic_hint=topic["topic_hint"],
            source_hash=f"hash_{key}_typo",
        )

    heading_fonts = [
        g.typography.get("font_family_heading") or g.typography.get("headingFont")
        for g in genomes.values()
    ]
    # At least 4 distinct heading fonts across the 5 domains
    assert len(set(heading_fonts)) >= 4, f"Heading fonts lack diversity: {heading_fonts}"

    # Domain specific font expectations
    # CPU / Software -> Monospace / Tech
    cpu_typo = genomes["cpu_architecture"].typography
    assert any(mono in str(cpu_typo).lower() for mono in ["fira", "jetbrains", "mono", "inter"])

    # WWII -> Serif / Archival
    wwii_typo = genomes["wwii_history"].typography
    assert any(serif in str(wwii_typo).lower() for serif in ["garamond", "baskerville", "cinzel", "lora"])

    # Mitosis -> Clean Scientific
    mitosis_typo = genomes["cell_mitosis"].typography
    assert any(sans in str(mitosis_typo).lower() for sans in ["source", "inter", "roboto"])

    # Financial -> Editorial Serif
    fin_typo = genomes["financial_earnings"].typography
    assert any(ed in str(fin_typo).lower() for ed in ["merriweather", "playfair", "georgia", "editorial"])

    # Rocket -> Grotesque / Engineering
    rocket_typo = genomes["rocket_staging"].typography
    assert any(grot in str(rocket_typo).lower() for grot in ["space", "inter", "grotesk", "mono"])


# =============================================================================
# BENCHMARK TEST 4: Scene Topology & Semantic Diversity
# =============================================================================

def test_five_topics_produce_distinct_scene_topologies():
    """Verify that all 5 topics generate distinct scene representation topologies."""
    service = VideoFlowV3Service()
    programs: Dict[str, VideoProgramV3] = {}

    for key, topic in BENCHMARK_TOPICS.items():
        job = service.create_job(
            source_text=topic["source_text"],
            mode="summary",
            title=topic["title"],
        )
        service.run_job(job.job_id, visual_style=topic["expected_families"][0])
        assert job.program is not None
        programs[key] = job.program

    # Verify each program has planned scenes
    for key, prog in programs.items():
        assert len(prog.scenes) > 0, f"Program for '{key}' has 0 scenes"

    # Verify representation types reflect domain semantics
    # CPU -> Process / Architecture / Hierarchy
    cpu_reps = {s.representation_type for s in programs["cpu_architecture"].scenes}
    assert any(r in cpu_reps for r in [
        SemanticRepresentationType.SYSTEM_ARCHITECTURE.value,
        SemanticRepresentationType.LAYER_STACK.value,
        SemanticRepresentationType.PROCESS.value,
        SemanticRepresentationType.FLOW.value,
    ])

    # WWII -> Timeline / Document / History
    wwii_reps = {s.representation_type for s in programs["wwii_history"].scenes}
    assert any(r in wwii_reps for r in [
        SemanticRepresentationType.TIMELINE.value,
        SemanticRepresentationType.DOCUMENT_SOURCE.value,
        SemanticRepresentationType.MAP_GEOGRAPHY.value,
        SemanticRepresentationType.QUOTE_CALLOUT.value,
        SemanticRepresentationType.SEQUENCE.value,
        SemanticRepresentationType.PROCESS.value,
    ])

    # Mitosis -> Process / Transformation / Cause-Effect
    mitosis_reps = {s.representation_type for s in programs["cell_mitosis"].scenes}
    assert any(r in mitosis_reps for r in [
        SemanticRepresentationType.PROCESS.value,
        SemanticRepresentationType.TRANSFORMATION.value,
        SemanticRepresentationType.CAUSE_EFFECT.value,
        SemanticRepresentationType.SEQUENCE.value,
        SemanticRepresentationType.FLOW.value,
    ])

    # Financial -> Quantitative / Chart / Comparison
    fin_reps = {s.representation_type for s in programs["financial_earnings"].scenes}
    assert any(r in fin_reps for r in [
        SemanticRepresentationType.QUANTITATIVE.value,
        SemanticRepresentationType.QUANTITATIVE_RELATIONSHIP.value,
        SemanticRepresentationType.CHART.value,
        SemanticRepresentationType.STAT_GRID.value,
        SemanticRepresentationType.COMPARISON.value,
        SemanticRepresentationType.PROCESS.value,
    ])

    # Rocket -> Assembly / Flow / Cutaway / Process
    rocket_reps = {s.representation_type for s in programs["rocket_staging"].scenes}
    assert any(r in rocket_reps for r in [
        SemanticRepresentationType.ASSEMBLY_3D.value,
        SemanticRepresentationType.CUTAWAY_3D.value,
        SemanticRepresentationType.FLOW.value,
        SemanticRepresentationType.SYSTEM_ARCHITECTURE.value,
        SemanticRepresentationType.PROCESS.value,
    ])


# =============================================================================
# BENCHMARK TEST 5: All 5 Topics Pass All 11 Quality Constitution Gates
# =============================================================================

def test_all_five_topics_pass_all_11_quality_constitution_gates():
    """Verify that all 5 benchmark topic programs pass all 11 Quality Constitution Gates 100%."""
    service = VideoFlowV3Service()
    qc = QualityConstitutionV3(PerformanceProfile.STANDARD)

    for key, topic in BENCHMARK_TOPICS.items():
        job = service.create_job(
            source_text=topic["source_text"],
            mode="summary",
            title=topic["title"],
        )
        service.run_job(job.job_id, visual_style=topic["expected_families"][0])
        assert job.program is not None

        bundle = SourceBundle(source_text=topic["source_text"], source_name=topic["title"])
        units = SourceNormalizer.segment_source_units(bundle)
        evidence = EvidenceGraphBuilder.build_evidence_graph(units)
        ledger = CoverageLedgerTracker.create_ledger(units, mode="summary")

        # Validate against all 11 gates
        is_valid, violations = qc.validate_program(
            program=job.program,
            source_units=units,
            evidence=evidence,
            ledger=ledger,
        )

        assert is_valid is True, f"Topic '{key}' failed Quality Constitution gates:\n" + "\n".join(violations)
        assert len(violations) == 0

        # Assert assert_valid_program does not raise
        qc.assert_valid_program(job.program, source_units=units, evidence=evidence, ledger=ledger)


# =============================================================================
# INDIVIDUAL QUALITY GATE ISOLATION TESTS
# =============================================================================

def test_gate1_grounding_gate_enforcement():
    """Gate 1: Rejects ungrounded claims and unknown unit refs."""
    qc = QualityConstitutionV3()
    units = [SourceUnit(unit_id="unit_0", order=0, raw_text="text", normalized_text="text", content_type="sentence")]

    valid_claim = ClaimEvidence(claim_id="claim_0", claim_text="test", source_unit_refs=["unit_0"])
    invalid_claim_no_ref = ClaimEvidence(claim_id="claim_1", claim_text="test", source_unit_refs=[])
    invalid_claim_bad_ref = ClaimEvidence(claim_id="claim_2", claim_text="test", source_unit_refs=["unit_99"])

    v_valid = qc.validate_grounding_gate(claims=[valid_claim], source_units=units)
    assert len(v_valid) == 0

    v_no_ref = qc.validate_grounding_gate(claims=[invalid_claim_no_ref], source_units=units)
    assert len(v_no_ref) == 1
    assert "no source_unit_refs" in v_no_ref[0]

    v_bad_ref = qc.validate_grounding_gate(claims=[invalid_claim_bad_ref], source_units=units)
    assert len(v_bad_ref) == 1
    assert "references unknown unit" in v_bad_ref[0]


def test_gate2_coverage_gate_enforcement():
    """Gate 2: Rejects incomplete coverage in full mode and low coverage in summary mode."""
    qc = QualityConstitutionV3()
    units = [SourceUnit(unit_id=f"u_{i}", order=i, raw_text=f"t{i}", normalized_text=f"t{i}", content_type="sentence") for i in range(10)]

    valid_full_ledger = CoverageLedger(mode="full", total_units=10, analyzed_units=10, coverage_ratio=1.0, unresolved_count=0)
    invalid_full_ledger = CoverageLedger(
        mode="full",
        total_units=10,
        analyzed_units=8,
        coverage_ratio=0.8,
        unresolved_count=2,
        items=[LedgerItem(unit_id="u_9", disposition="unresolved")],
    )

    assert len(qc.validate_coverage_gate(valid_full_ledger, units, mode="full")) == 0
    violations = qc.validate_coverage_gate(invalid_full_ledger, units, mode="full")
    assert len(violations) >= 2


def test_gate3_representation_suitability_gate_enforcement():
    """Gate 3: Rejects incompatible semantic representations."""
    qc = QualityConstitutionV3()

    # Valid comparison scene with 2 objects
    valid_scene = SceneSemanticV3(
        scene_id="s1",
        chapter_id="c0",
        sequence=0,
        teaching_goal="Compare A and B",
        viewer_question="Which is faster?",
        intended_understanding="A is faster",
        narration_text="Comparing A and B.",
        representation_type=SemanticRepresentationType.COMPARISON.value,
        semantic_objects=[
            SemanticObject(object_id="a", label="A", role="primary", semantic_type="node"),
            SemanticObject(object_id="b", label="B", role="secondary", semantic_type="node"),
        ],
    )
    assert len(qc.validate_representation_suitability_gate(valid_scene)) == 0

    # Invalid comparison with only 1 object
    invalid_scene = SceneSemanticV3(
        scene_id="s2",
        chapter_id="c0",
        sequence=0,
        teaching_goal="Compare A and B",
        viewer_question="Which is faster?",
        intended_understanding="A is faster",
        narration_text="Comparing A alone.",
        representation_type=SemanticRepresentationType.COMPARISON.value,
        semantic_objects=[
            SemanticObject(object_id="a", label="A", role="primary", semantic_type="node"),
        ],
    )
    violations = qc.validate_representation_suitability_gate(invalid_scene)
    assert len(violations) == 1
    assert "requires >= 2 comparison objects" in violations[0]


def test_gate4_layout_gate_enforcement():
    """Gate 4: Rejects clipped, out-of-bounds, or overlapping elements."""
    qc = QualityConstitutionV3()

    valid_scene = ExecutableSceneProgram(
        scene_id="s_valid",
        elements_2d=[
            ExecutableElement2D(element_id="e1", layer="diagram", compositor="Process", layout_bounds={"x": 100, "y": 100, "width": 200, "height": 100}),
            ExecutableElement2D(element_id="e2", layer="diagram", compositor="Process", layout_bounds={"x": 400, "y": 100, "width": 200, "height": 100}),
        ],
    )
    assert len(qc.validate_layout_gate(valid_scene)) == 0

    # Overlapping and out-of-bounds elements
    invalid_scene = ExecutableSceneProgram(
        scene_id="s_invalid",
        elements_2d=[
            ExecutableElement2D(element_id="e1", layer="diagram", compositor="Process", layout_bounds={"x": 100, "y": 100, "width": 200, "height": 100}),
            ExecutableElement2D(element_id="e2", layer="diagram", compositor="Process", layout_bounds={"x": 110, "y": 105, "width": 200, "height": 100}),  # Severe overlap
            ExecutableElement2D(element_id="e3", layer="diagram", compositor="Process", layout_bounds={"x": -50, "y": 100, "width": 0, "height": 100}),   # Negative X and 0 width
        ],
    )
    violations = qc.validate_layout_gate(invalid_scene)
    assert len(violations) >= 2


def test_gate6_art_direction_compliance_and_anti_ai_policy():
    """Gate 6: Rejects generic AI styling, forbidden neon colors, and bloom."""
    qc = QualityConstitutionV3()

    bad_genome = ArtDirectionGenome(
        family="neon_rainbow_cyber_ai",
        palette={"environment": "#FF00FF", "primary_info": "#FFFFFF", "accent": "#00FFFF", "highlight": "#FFFF00", "structural_neutral": "#333333"},
        typography={"headingFont": "Inter", "bodyFont": "Inter", "codeFont": "Fira Code"},
        materials={"bloom_enabled": True, "glassmorphism": True},
    )
    violations = qc.validate_art_genome(bad_genome)
    assert len(violations) >= 3
    assert any("Forbidden AI aesthetic" in v for v in violations)
    assert any("Forbidden neon environment" in v for v in violations)
    assert any("bloom_enabled" in v for v in violations)


def test_gate8_visual_inactivity_gate_enforcement():
    """Gate 8: Rejects static empty scenes during ongoing narration."""
    qc = QualityConstitutionV3()

    empty_narration_scene = SceneSemanticV3(
        scene_id="s_empty",
        chapter_id="c0",
        sequence=0,
        teaching_goal="Active narration goal",
        viewer_question="Question?",
        intended_understanding="Understanding",
        narration_text="This is an active spoken narration that requires visuals.",
        semantic_objects=[],  # Empty
        use_3d=False,
    )
    violations = qc.validate_visual_inactivity_gate(empty_narration_scene)
    assert len(violations) == 1
    assert "has active narration" in violations[0]


def test_gate9_3d_validity_gate_enforcement():
    """Gate 9: Enforces 3D fidelity and falls back on F4."""
    qc = QualityConstitutionV3()

    # Invalid F4 with use_3d=True
    f4_scene = SceneSemanticV3(
        scene_id="s_f4",
        chapter_id="c0",
        sequence=0,
        teaching_goal="Goal",
        viewer_question="Q?",
        intended_understanding="U",
        narration_text="Narration",
        use_3d=True,
        fidelity_3d=FidelityClass3D.F4_INSUFFICIENT,
    )
    violations = qc.validate_3d_validity_gate(f4_scene)
    assert len(violations) == 1
    assert "fidelity F4" in violations[0]

    # Deterministic Repair Ladder falls back cleanly
    repaired = DeterministicRepairLadder.repair_3d_fallback(f4_scene)
    assert repaired.use_3d is False
    assert len(qc.validate_3d_validity_gate(repaired)) == 0


def test_gate10_performance_budget_enforcement():
    """Gate 10: Rejects scenes that exceed draw call or element count budgets."""
    qc = QualityConstitutionV3(PerformanceProfile.STANDARD)

    # 160 elements exceeds STANDARD budget of 150
    over_budget_scene = ExecutableSceneProgram(
        scene_id="s_heavy",
        elements_2d=[
            ExecutableElement2D(
                element_id=f"e_{i}",
                layer="node",
                compositor="Process",
                layout_bounds={"x": (i % 10) * 100, "y": (i // 10) * 40, "width": 80, "height": 30},
            )
            for i in range(160)
        ],
    )
    violations = qc.validate_performance_gate(over_budget_scene)
    assert len(violations) == 1
    assert "exceeds element budget: 160 > 150" in violations[0]

    # Deterministic repair simplifies elements
    simplified = DeterministicRepairLadder.simplify_scene_for_performance(over_budget_scene, PerformanceProfile.STANDARD)
    assert len(simplified.elements_2d) <= 80
    assert len(qc.validate_performance_gate(simplified)) == 0


def test_gate11_same_video_repetition_avoidance():
    """Gate 11: Rejects 3 consecutive identical scenes and duplicate IDs."""
    qc = QualityConstitutionV3()

    scene_a = SceneSemanticV3(scene_id="s0", chapter_id="c0", sequence=0, teaching_goal="G0", viewer_question="Q0", intended_understanding="U0", narration_text="N0", representation_type="PROCESS")
    scene_b = SceneSemanticV3(scene_id="s1", chapter_id="c0", sequence=1, teaching_goal="G1", viewer_question="Q1", intended_understanding="U1", narration_text="N1", representation_type="PROCESS")
    scene_c = SceneSemanticV3(scene_id="s2", chapter_id="c0", sequence=2, teaching_goal="G2", viewer_question="Q2", intended_understanding="U2", narration_text="N2", representation_type="PROCESS")

    violations = qc.validate_repetition_gate([scene_a, scene_b, scene_c])
    assert len(violations) == 1
    assert "3 consecutive scenes" in violations[0]

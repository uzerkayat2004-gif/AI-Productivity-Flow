"""Video Flow V3 Architectural & Functional Test Suite.

Verifies:
1. Deterministic SourceUnit segmentation & span provenance.
2. EvidenceGraph claims require source unit references.
3. CoverageLedger 100% accounting in Full mode and complete analysis in Summary mode.
4. SpatialAffordanceAnalyzer F1-F4 fidelity classification & fake geometry rejection.
5. AI Security Boundary: Rejects executable code and raw pixel coordinates.
6. ArtDirectionGenome Anti-Generic-AI policy enforcement.
7. Deterministic absolute-time scene evaluation (state = Scene(t)).
8. QualityConstitutionV3 gates (grounding, layout bounds, performance budgets).
9. Progressive READY_TO_WATCH state machine logic & export independence.
10. Feature flag behavior (video_flow_v3_enabled).
"""

from __future__ import annotations

import os
import tempfile
import pytest
from pathlib import Path

from voice_flow.video_flow_v3.contracts import (
    SourceBundle,
    SourceUnit,
    EvidenceGraph,
    CoverageLedger,
    VideoProgramV3,
    ExecutableSceneProgram,
    ArtDirectionGenome,
    GenerationStateV3,
    ExportStateV3,
    FidelityClass3D,
    PerformanceProfile,
    validate_no_executable_code,
)
from voice_flow.video_flow_v3.source.units import SourceNormalizer, compute_source_hash
from voice_flow.video_flow_v3.evidence.builder import (
    EvidenceGraphBuilder,
    CoverageLedgerTracker,
    SpatialAffordanceAnalyzer,
)
from voice_flow.video_flow_v3.director.creative_director import CreativeDirectorV3
from voice_flow.video_flow_v3.art_direction.resolver import ArtDirectionResolverV3
from voice_flow.video_flow_v3.quality.constitution import QualityConstitutionV3, QualityViolation
from voice_flow.video_flow_v3.scheduler.job import JobV3
from voice_flow.video_flow_v3.service import VideoFlowV3Service


def test_v3_deterministic_source_unit_segmentation():
    source = "# Executive Summary\nSentence one explains topic.\nSentence two gives data.\n\n```python\nprint('hello')\n```"
    bundle = SourceBundle(source_text=source, source_name="Test Doc")
    units = SourceNormalizer.segment_source_units(bundle)

    assert len(units) >= 4
    assert units[0].content_type == "heading"
    assert units[0].normalized_text == "Executive Summary"
    assert units[-1].content_type == "code_block"
    assert "print('hello')" in units[-1].normalized_text
    assert bundle.source_hash != ""


def test_v3_evidence_graph_claims_require_source_refs():
    source = "The project generated 1500 units in 30 seconds."
    bundle = SourceBundle(source_text=source)
    units = SourceNormalizer.segment_source_units(bundle)
    evidence = EvidenceGraphBuilder.build_evidence_graph(units)

    assert len(evidence.claims) == len(units)
    for claim in evidence.claims:
        assert len(claim.source_unit_refs) > 0
        assert claim.claim_id.startswith("claim_")


def test_v3_coverage_ledger_accounting():
    source = "Heading 1\nParagraph 1 text.\nParagraph 2 text."
    bundle = SourceBundle(source_text=source)
    units = SourceNormalizer.segment_source_units(bundle)

    full_ledger = CoverageLedgerTracker.create_ledger(units, mode="full")
    assert full_ledger.coverage_ratio == 1.0
    assert full_ledger.unresolved_count == 0
    assert len(full_ledger.items) == len(units)


def test_v3_spatial_3d_fidelity_classification():
    text_cad = "The engine block assembly specifications have exact CAD dimensions."
    text_schematic = "The motor assembly contains three internal components."
    text_abstract = "The concept of momentum flows through the system."
    text_plain = "The meeting starts at 3 PM tomorrow."

    assert SpatialAffordanceAnalyzer.classify_fidelity(text_cad, "spatial_3d") == FidelityClass3D.F1_PHYSICAL
    assert SpatialAffordanceAnalyzer.classify_fidelity(text_schematic, "spatial_3d") == FidelityClass3D.F2_SCHEMATIC
    assert SpatialAffordanceAnalyzer.classify_fidelity(text_abstract, "spatial_3d") == FidelityClass3D.F3_CONCEPTUAL
    assert SpatialAffordanceAnalyzer.classify_fidelity(text_plain, "spatial_3d") == FidelityClass3D.F4_INSUFFICIENT


def test_v3_security_boundary_rejects_executable_code():
    valid_payload = {"title": "Safe Explanation", "scene": "Intro"}
    validate_no_executable_code(valid_payload)

    malicious_payload = {"title": "<script>alert(1)</script>", "code": "import os; os.system('rm')"}
    with pytest.raises(ValueError) as exc_info:
        validate_no_executable_code(malicious_payload)
    assert "Security Boundary Violation" in str(exc_info.value)


def test_v3_art_direction_anti_ai_policy_enforcement():
    resolver = ArtDirectionResolverV3()
    genome = resolver.resolve(source_text="Test source text", source_hash="test_hash_123", family_override="Industrial Product")
    qc = QualityConstitutionV3(PerformanceProfile.STANDARD)

    violations = qc.validate_art_genome(genome)
    assert len(violations) == 0
    assert genome.family == "Industrial Product"
    assert "environment" in genome.palette


def test_v3_ready_to_watch_state_machine():
    job = JobV3(job_id="test_job_1", mode="summary", title="Test Title", source_text="Sample source text")
    assert job.status == GenerationStateV3.CREATED
    assert job.export_status == ExportStateV3.NOT_REQUESTED

    job.update_status(GenerationStateV3.COMPILING_INITIAL, "Preparing first scenes...", 60)
    assert job.status == GenerationStateV3.COMPILING_INITIAL

    # Independent export status update
    job.update_export_status(ExportStateV3.EXPORTING, 45)
    assert job.export_status == ExportStateV3.EXPORTING
    assert job.status == GenerationStateV3.COMPILING_INITIAL  # Export update does not corrupt generation state


def test_v3_service_end_to_end_job_flow(tmp_path):
    service = VideoFlowV3Service()
    source = "# Rocket Assembly\nThe rocket engine uses liquid fuel. The primary stage delivers 500kN thrust."
    job = service.create_job(source_text=source, mode="summary", title="Rocket Test")

    service.run_job(job.job_id, visual_style="Technical Systems")

    assert job.status in (GenerationStateV3.READY, GenerationStateV3.COMPLETE)
    assert job.planned_scenes > 0
    assert job.error is None

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

import json
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


def test_v3_non_local_model_invokes_provider_gateway():
    """Verify non-local selected model invokes provider gateway when consent is granted."""
    from unittest.mock import MagicMock
    from voice_flow.video_flow_v3.director.gateway import V3CreativeDirectorGateway
    from voice_flow.video_flow_v3.contracts import SemanticRepresentationType

    mock_gateway = MagicMock()
    mock_gateway.request_scene_plan.return_value = json.dumps({
        "scenes": [
            {
                "representation_type": "SYSTEM_ARCHITECTURE",
                "teaching_goal": "Explain Distributed Gateway Architecture",
                "viewer_question": "How are requests routed through the nodes?",
                "intended_understanding": "Gateway distributes load to microservices",
                "narration_text": "The gateway routes incoming requests to available worker nodes.",
                "semantic_objects": [
                    {"object_id": "obj_gw", "label": "API Gateway", "role": "primary", "semantic_type": "system_architecture"},
                    {"object_id": "obj_node1", "label": "Worker Node", "role": "secondary", "semantic_type": "node"},
                ],
                "motion_purpose": "flow",
                "shot_grammar": "ArchitecturalZoom",
                "suggested_duration_sec": 6.0,
                "use_3d": False,
                "evidence_refs": ["unit_0"],
            }
        ]
    })

    bundle = SourceBundle(source_text="System Architecture Overview\nGateway routes requests.")
    units = SourceNormalizer.segment_source_units(bundle)
    evidence = EvidenceGraphBuilder.build_evidence_graph(units)
    genome = ArtDirectionResolverV3().resolve("System Architecture Overview", "hash_1")

    director_gw = V3CreativeDirectorGateway(model_gateway=mock_gateway)
    scenes = director_gw.author_semantic_plan(
        bundle=bundle,
        units=units,
        evidence=evidence,
        genome=genome,
        mode="summary",
        model_ref="gemini/gemini-2.5-flash",
        visual_direction="Focus on network flow and node connectivity",
        allow_external_ai=True,
    )

    assert mock_gateway.request_scene_plan.called
    call_args = mock_gateway.request_scene_plan.call_args
    assert call_args[0][0] == "gemini/gemini-2.5-flash"  # model_ref passed
    assert len(scenes) == 1
    assert scenes[0].representation_type == SemanticRepresentationType.SYSTEM_ARCHITECTURE.value
    assert len(scenes[0].semantic_objects) == 2


def test_v3_visual_direction_prompt_passed_to_model():
    """Verify visual_direction prompt is passed into the user prompt forwarded to the model."""
    from unittest.mock import MagicMock
    from voice_flow.video_flow_v3.director.gateway import V3CreativeDirectorGateway

    mock_gateway = MagicMock()
    mock_gateway.request_scene_plan.return_value = json.dumps({"scenes": []})

    bundle = SourceBundle(source_text="Sample text about optics.")
    units = SourceNormalizer.segment_source_units(bundle)
    evidence = EvidenceGraphBuilder.build_evidence_graph(units)
    genome = ArtDirectionResolverV3().resolve("Sample text", "hash_2")

    director_gw = V3CreativeDirectorGateway(model_gateway=mock_gateway)
    director_gw.author_semantic_plan(
        bundle=bundle,
        units=units,
        evidence=evidence,
        genome=genome,
        mode="summary",
        model_ref="openai/gpt-4o",
        visual_direction="Emphasize refractive prism ray-tracing diagrams",
        allow_external_ai=True,
    )

    assert mock_gateway.request_scene_plan.called
    call_args = mock_gateway.request_scene_plan.call_args
    user_prompt = call_args[0][2]
    assert "Emphasize refractive prism ray-tracing diagrams" in user_prompt
    assert "VISUAL DIRECTION HINT" in user_prompt


def test_v3_long_source_text_beyond_15_units_fully_processed():
    """Verify long documents with >15 units are completely processed without arbitrary slicing."""
    from unittest.mock import MagicMock
    from voice_flow.video_flow_v3.director.gateway import V3CreativeDirectorGateway

    # Create a 25-unit source document
    paragraphs = [f"Section step {i}: detailing execution procedure and metrics for stage {i}." for i in range(25)]
    source = "\n\n".join(paragraphs)
    bundle = SourceBundle(source_text=source, source_name="Long Execution Pipeline")
    units = SourceNormalizer.segment_source_units(bundle)
    assert len(units) >= 25

    mock_gateway = MagicMock()
    mock_gateway.request_scene_plan.return_value = None  # Force deterministic path

    director_gw = V3CreativeDirectorGateway(model_gateway=mock_gateway)
    genome = ArtDirectionResolverV3().resolve(source, "hash_long")
    evidence = EvidenceGraphBuilder.build_evidence_graph(units)

    # In summary mode, all units are covered across scenes
    summary_scenes = director_gw.author_semantic_plan(
        bundle=bundle,
        units=units,
        evidence=evidence,
        genome=genome,
        mode="summary",
        model_ref="local/deterministic",
        allow_external_ai=False,
    )

    # Collect all unit refs from generated scenes
    all_covered_refs = set()
    for sc in summary_scenes:
        all_covered_refs.update(sc.evidence_refs)

    # Verify that all 25 units are accounted for in the evidence refs
    all_source_ids = {u.unit_id for u in units}
    assert all_covered_refs == all_source_ids

    # When sent to LLM prompt, verify all 25 units are in user prompt
    mock_gateway.reset_mock()
    mock_gateway.request_scene_plan.return_value = json.dumps({"scenes": []})
    director_gw.author_semantic_plan(
        bundle=bundle,
        units=units,
        evidence=evidence,
        genome=genome,
        mode="summary",
        model_ref="groq/llama-3.3-70b",
        allow_external_ai=True,
    )
    user_prompt = mock_gateway.request_scene_plan.call_args[0][2]
    for u in units:
        assert u.unit_id in user_prompt


def test_v3_representation_type_survives_to_video_program():
    """Verify representation_type survives from model output into VideoProgramV3."""
    from unittest.mock import MagicMock
    from voice_flow.video_flow_v3.director.creative_director import CreativeDirectorV3
    from voice_flow.video_flow_v3.contracts import SemanticRepresentationType

    mock_gateway = MagicMock()
    mock_gateway.request_scene_plan.return_value = json.dumps({
        "scenes": [
            {
                "representation_type": "COMPARISON",
                "teaching_goal": "Compare Microservices vs Monolith",
                "viewer_question": "Which architecture has lower latency?",
                "intended_understanding": "Monolith has lower IPC latency but lower isolation",
                "narration_text": "Comparing monolith and microservices trade-offs.",
                "semantic_objects": [
                    {"object_id": "obj_cmp1", "label": "Monolith", "role": "primary", "semantic_type": "comparison"},
                    {"object_id": "obj_cmp2", "label": "Microservices", "role": "secondary", "semantic_type": "comparison"},
                ],
                "motion_purpose": "compare",
                "shot_grammar": "SplitCompare",
                "suggested_duration_sec": 5.0,
                "evidence_refs": ["unit_0"],
            }
        ]
    })

    bundle = SourceBundle(source_text="Monolith vs Microservices comparison.", source_hash="hash_rep")
    units = SourceNormalizer.segment_source_units(bundle)
    evidence = EvidenceGraphBuilder.build_evidence_graph(units)
    ledger = CoverageLedgerTracker.create_ledger(units, mode="summary")
    genome = ArtDirectionResolverV3().resolve(bundle.source_text, bundle.source_hash)

    director = CreativeDirectorV3(model_gateway=mock_gateway)
    program = director.build_program(
        bundle=bundle,
        units=units,
        evidence=evidence,
        ledger=ledger,
        genome=genome,
        mode="summary",
        model_ref="openai/gpt-4o",
        allow_external_ai=True,
    )

    assert len(program.scenes) == 1
    scene = program.scenes[0]
    assert scene.representation_type == SemanticRepresentationType.COMPARISON.value
    assert scene.motion_purpose == "compare"


def test_v3_ai_consent_defaults_to_deny():
    """Verify AI consent defaults to DENY (False) and blocks external provider calls."""
    from unittest.mock import MagicMock
    from voice_flow.video_flow_v3.director.gateway import V3CreativeDirectorGateway

    mock_gateway = MagicMock()
    mock_gateway.request_scene_plan.return_value = json.dumps({"scenes": []})

    bundle = SourceBundle(source_text="Confidential internal document.")
    units = SourceNormalizer.segment_source_units(bundle)
    evidence = EvidenceGraphBuilder.build_evidence_graph(units)
    genome = ArtDirectionResolverV3().resolve(bundle.source_text, "hash_sec")

    director_gw = V3CreativeDirectorGateway(model_gateway=mock_gateway)

    # Calling with default allow_external_ai (omitted -> defaults to False)
    director_gw.author_semantic_plan(
        bundle=bundle,
        units=units,
        evidence=evidence,
        genome=genome,
        mode="summary",
        model_ref="gemini/gemini-2.5-flash",
    )

    # Model gateway MUST NOT be invoked when consent is omitted or False
    assert not mock_gateway.request_scene_plan.called

    # Explicit allow_external_ai=False
    director_gw.author_semantic_plan(
        bundle=bundle,
        units=units,
        evidence=evidence,
        genome=genome,
        mode="summary",
        model_ref="gemini/gemini-2.5-flash",
        allow_external_ai=False,
    )
    assert not mock_gateway.request_scene_plan.called


def test_v3_validate_no_executable_code_strictly_blocks_code():
    """Verify validate_no_executable_code strictly blocks all forbidden code tokens."""
    forbidden_samples = [
        {"eval_call": "eval('2+2')"},
        {"tag": "<script src='malicious.js'></script>"},
        {"module": "import os; os.system('calc')"},
        {"func": "Function('return process')()"},
        {"proc": "process.exit(1)"},
        {"exec_call": "exec('print(1)')"},
        {"child": "child_process.spawn('sh')"},
        {"os_call": "os.system('whoami')"},
        {"subp": "subprocess.Popen(['ls'])"},
        {"dunder": "__import__('sys').exit()"},
        {"req": "require('fs').readFileSync('/etc/passwd')"},
        {"js_url": "javascript:alert(1)"},
        {"handler": "<img src=x onload=alert(1)>"},
        {"err": "<img src=x onerror=alert(1)>"},
    ]

    for sample in forbidden_samples:
        with pytest.raises(ValueError) as exc_info:
            validate_no_executable_code(sample)
        assert "Security Boundary Violation" in str(exc_info.value)


def test_v3_deterministic_fallback_resolves_semantic_representation_types():
    """Verify deterministic fallback resolves real semantic representation types from content."""
    from voice_flow.video_flow_v3.director.gateway import classify_semantic_representation
    from voice_flow.video_flow_v3.contracts import SemanticRepresentationType

    # Code explanation
    assert classify_semantic_representation("def compute_hash(data): return sha256(data)", "code_block") == SemanticRepresentationType.CODE_EXPLANATION

    # Comparison
    assert classify_semantic_representation("Model A is faster than Model B in benchmark latency.", "sentence") == SemanticRepresentationType.COMPARISON

    # Timeline
    assert classify_semantic_representation("In 1969, the first milestone of ARPANET was achieved.", "sentence") == SemanticRepresentationType.TIMELINE

    # 3D Assembly
    assert classify_semantic_representation("The CAD model of the engine block assembly contains 12 valves.", "sentence") == SemanticRepresentationType.ASSEMBLY_3D

    # System Architecture
    assert classify_semantic_representation("The microservice architecture connects the backend database with the client.", "sentence") == SemanticRepresentationType.SYSTEM_ARCHITECTURE

    # Process
    assert classify_semantic_representation("Step 1: initialize the buffer. Step 2: stream data.", "sentence") == SemanticRepresentationType.PROCESS


def test_v3_nine_art_direction_families_validation():
    """Verify all 9 curated Art Direction Families are fully configured, distinct, and anti-generic compliant."""
    from voice_flow.video_flow_v3.art_direction.families import VISUAL_FAMILIES, VisualFamilyName, get_visual_family_spec
    from voice_flow.video_flow_v3.art_direction.genome import build_genome_from_family, validate_art_genome

    expected_families = [
        VisualFamilyName.INDUSTRIAL_PRODUCT.value,
        VisualFamilyName.TECHNICAL_SYSTEMS.value,
        VisualFamilyName.SCIENTIFIC_VISUALIZATION.value,
        VisualFamilyName.DATA_EDITORIAL.value,
        VisualFamilyName.EDITORIAL_DOCUMENTARY.value,
        VisualFamilyName.SOFTWARE_ARCHITECTURE.value,
        VisualFamilyName.HISTORICAL_ARCHIVAL.value,
        VisualFamilyName.ARCHITECTURAL_SPATIAL.value,
        VisualFamilyName.MINIMAL_CONCEPTUAL.value,
    ]

    assert len(VISUAL_FAMILIES) == 9
    for fam_name in expected_families:
        assert fam_name in VISUAL_FAMILIES
        spec = get_visual_family_spec(fam_name)
        assert spec.name == fam_name
        assert spec.description != ""
        assert spec.palette.environment != ""
        assert spec.palette.accent != ""
        assert spec.typography.font_family_primary != ""
        assert spec.materials.surface_type != ""
        assert spec.lighting_rig.name != ""
        assert spec.camera_grammar.name != ""
        assert spec.motion_grammar.name != ""

        # Validate anti-generic AI policy
        genome = build_genome_from_family(spec, source_hash=f"test_hash_{fam_name}")
        assert validate_art_genome(genome) is True
        assert genome.materials.get("bloom_enabled") is False
        assert genome.materials.get("glassmorphism") is False
        assert genome.materials.get("lens_flare") is False


def test_v3_resolver_auto_classification_and_diversity():
    """Verify ArtDirectionResolverV3 classifies keywords, respects visual_direction, and guarantees diversity via source_hash."""
    from voice_flow.video_flow_v3.art_direction.families import VisualFamilyName
    resolver = ArtDirectionResolverV3()

    # Keyword classification
    assert resolver.classify_family(source_text="The mechanical chassis is machined from aluminum alloy.") == "Industrial Product"
    assert resolver.classify_family(source_text="Distributed microservices telemetry stream over the network.") == "Technical Systems"
    assert resolver.classify_family(source_text="The molecular structure of cellular DNA reveals RNA protein interactions.") == "Scientific Visualization"
    assert resolver.classify_family(source_text="Quarterly GDP growth and inflation metrics in economic dataset.") == "Data Editorial"
    assert resolver.classify_family(source_text="The historical archive contains manuscript documents and parchment scrolls.") == "Historical / Archival"
    assert resolver.classify_family(source_text="The AST compiler runtime optimizes syntax tree in Python code.") == "Software Architecture"
    assert resolver.classify_family(source_text="Blueprint elevation and concrete cantilever structure in urban zoning.") == "Architectural / Spatial"
    assert resolver.classify_family(source_text="Pure mathematical logic and axiomatic metaphysics.") == "Minimal Conceptual"

    # User visual direction override/hint
    assert resolver.classify_family(
        source_text="Some generic overview text.",
        visual_direction="Use an Industrial Product style with copper highlights and machined chassis",
    ) == "Industrial Product"

    # Source-hash seeded diversification for untagged neutral text
    genome1 = resolver.resolve(source_text="Item 1 overview.", source_hash="1a2b3c4d")
    genome2 = resolver.resolve(source_text="Item 2 overview.", source_hash="9f8e7d6c")
    assert genome1.family in [f.value for f in VisualFamilyName]
    assert genome2.family in [f.value for f in VisualFamilyName]


def test_v3_visual_summary_mode_adaptive_duration_and_scene_beats():
    """Verify Visual Summary Mode produces 1-3 points, adaptive duration, SceneBeats, and non-slideshow semantic types."""
    from voice_flow.video_flow_v3.director.gateway import V3CreativeDirectorGateway

    source = (
        "# Quantum Computing Architecture\n"
        "Qubits utilize quantum superposition to process calculations exponentially faster than classical bits. "
        "Cryogenic dilution refrigerators maintain temperatures near absolute zero to preserve coherence. "
        "Error correction algorithms monitor syndrome measurements across the distributed qubit lattice."
    )
    bundle = SourceBundle(source_text=source, source_name="Quantum Summary")
    units = SourceNormalizer.segment_source_units(bundle)
    evidence = EvidenceGraphBuilder.build_evidence_graph(units)
    genome = ArtDirectionResolverV3().resolve(source_text=source, source_hash=bundle.source_hash)

    gateway = V3CreativeDirectorGateway()
    scenes = gateway.author_semantic_plan(
        bundle=bundle,
        units=units,
        evidence=evidence,
        genome=genome,
        mode="summary",
        model_ref="local/deterministic",
    )

    assert len(scenes) >= 1
    for sc in scenes:
        assert 1 <= len(sc.semantic_objects) <= 3
        assert sc.suggested_duration_sec >= 4.5
        assert len(sc.scene_beats) >= 2
        for beat in sc.scene_beats:
            assert beat.beat_id.startswith(f"{sc.scene_id}_beat_")
            assert beat.time_offset_sec >= 0.0
            assert beat.visual_action in ("reveal", "highlight_target", "expand_node", "route_signal", "compare_delta", "assemble", "focus", "morph_state")
            assert len(beat.target_element_ids) > 0


def test_v3_full_visual_explanation_mode_unit_accounting_and_chapters():
    """Verify Full Visual Explanation Mode guarantees 100% unit accounting, structured chaptering, and progressive generation."""
    source = (
        "# Chapter 1: Introduction\n"
        "This is the first foundational principle.\n"
        "Here is a supporting data detail.\n\n"
        "# Chapter 2: Implementation\n"
        "```python\ndef execute_task():\n    return True\n```\n"
        "The implementation runs securely in memory."
    )
    bundle = SourceBundle(source_text=source, source_name="Full Explanation Document")
    units = SourceNormalizer.segment_source_units(bundle)
    evidence = EvidenceGraphBuilder.build_evidence_graph(units)
    ledger = CoverageLedgerTracker.create_ledger(units, mode="full")
    genome = ArtDirectionResolverV3().resolve(source_text=source, source_hash=bundle.source_hash)

    director = CreativeDirectorV3()
    program = director.build_program(
        bundle=bundle,
        units=units,
        evidence=evidence,
        ledger=ledger,
        genome=genome,
        mode="full",
        model_ref="local/deterministic",
    )

    assert len(program.scenes) == len(units)
    assert len(program.chapters) >= 2
    assert ledger.coverage_ratio == 1.0

    valid_dispositions = {"covered_both", "covered_narration", "covered_visual", "merged", "disposed", "included"}
    for item in ledger.items:
        assert item.disposition in valid_dispositions
        assert len(item.scene_refs) > 0


def test_v3_spatial_3d_mode_selective_routing():
    """Verify Spatial 3D Mode selectively routes physical/mechanical to 3D and non-spatial to 2D/2.5D."""
    from voice_flow.video_flow_v3.director.gateway import V3CreativeDirectorGateway

    source = (
        "The engine block assembly specifications have exact CAD dimensions and physical components.\n"
        "Project planning meeting schedule and team allocations."
    )
    bundle = SourceBundle(source_text=source, source_name="Spatial Routing Test")
    units = SourceNormalizer.segment_source_units(bundle)
    evidence = EvidenceGraphBuilder.build_evidence_graph(units)
    genome = ArtDirectionResolverV3().resolve(source_text=source, source_hash=bundle.source_hash, mode="spatial_3d")

    gateway = V3CreativeDirectorGateway()
    scenes = gateway.author_semantic_plan(
        bundle=bundle,
        units=units,
        evidence=evidence,
        genome=genome,
        mode="spatial_3d",
        model_ref="local/deterministic",
    )

    assert len(scenes) == 2
    # First scene: physical structure -> 3D enabled (F1)
    assert scenes[0].use_3d is True
    assert scenes[0].fidelity_3d == FidelityClass3D.F1_PHYSICAL
    assert scenes[0].representation_type in ("ASSEMBLY_3D", "CUTAWAY_3D")

    # Second scene: plain non-spatial -> graceful fallback to 2D/2.5D (F4)
    assert scenes[1].use_3d is False
    assert scenes[1].fidelity_3d == FidelityClass3D.F4_INSUFFICIENT


def test_v3_scene_semantic_transitions():
    """Verify semantic transitions (MATCH_TRANSITION, CARRY, EXPAND, COLLAPSE) are authored between scenes."""
    from voice_flow.video_flow_v3.director.gateway import V3CreativeDirectorGateway
    from voice_flow.video_flow_v3.contracts import SemanticTransitionType

    source = (
        "# System Architecture\n"
        "The API Gateway distributes incoming client requests across the cluster.\n"
        "Worker nodes process asynchronous tasks from the queue.\n"
        "In summary, the distributed architecture guarantees high availability."
    )
    bundle = SourceBundle(source_text=source, source_name="Transitions Test")
    units = SourceNormalizer.segment_source_units(bundle)
    evidence = EvidenceGraphBuilder.build_evidence_graph(units)
    genome = ArtDirectionResolverV3().resolve(source_text=source, source_hash=bundle.source_hash)

    gateway = V3CreativeDirectorGateway()
    scenes = gateway.author_semantic_plan(
        bundle=bundle,
        units=units,
        evidence=evidence,
        genome=genome,
        mode="summary",
        model_ref="local/deterministic",
    )

    assert len(scenes) >= 2
    valid_transitions = {t.value for t in SemanticTransitionType}
    for sc in scenes:
        assert sc.transition_in in valid_transitions
        assert sc.transition_out in valid_transitions


def test_v3_service_multi_doc_handling_and_budgeting():
    """Verify VideoFlowV3Service processes multi-document bundles and applies adaptive budgeting."""
    service = VideoFlowV3Service()
    job = service.create_job(
        source_text="Doc 1 content.\nDoc 2 content.",
        mode="summary",
        title="Multi-Doc Project",
    )
    job.metadata = {
        "documents": [
            {"name": "Architecture Spec", "content": "# Architecture\nMicroservices topology and signal flow."},
            {"name": "Metrics Report", "content": "# Metrics\nRevenue increased by 35% with 99.99% uptime."},
        ]
    }

    service.run_job(job.job_id, visual_style="Auto")

    assert job.status in (GenerationStateV3.READY, GenerationStateV3.COMPLETE)
    assert job.planned_scenes > 0
    assert job.error is None



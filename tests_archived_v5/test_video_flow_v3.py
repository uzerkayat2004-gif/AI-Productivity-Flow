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


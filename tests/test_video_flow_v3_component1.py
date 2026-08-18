"""Unit tests for Component 1 of Video Flow V3 Authoritative Product Architecture.

Covers:
1. DocumentSourceItem and multi-document SourceBundle contracts.
2. Canonical 2D and 3D SemanticRepresentationType enums.
3. SceneBeat, SemanticTransitionType, and SemanticMotionType contracts.
4. SceneSemanticV3 and ExecutableSceneProgram beats and transition_type fields.
5. calculate_adaptive_semantic_budget tiers and mode adjustments (Section 6).
6. Multi-document SourceNormalizer segmentation and provenance tracking.
7. Multi-document EvidenceGraphBuilder synthesis (deduplication, provenance, causal/complementary links).
8. calculate_importance_score semantic importance formula (Section 7).
"""

from __future__ import annotations

import pytest
from voice_flow.video_flow_v3.contracts import (
    DocumentSourceItem,
    SourceBundle,
    SourceUnit,
    ClaimEvidence,
    EvidenceGraph,
    SceneBeat,
    SceneSemanticV3,
    ExecutableSceneProgram,
    SemanticRepresentationType,
    SemanticTransitionType,
    SemanticMotionType,
    export_contract_schema,
)
from voice_flow.video_flow_v3.source.units import (
    SourceNormalizer,
    calculate_adaptive_semantic_budget,
    compute_source_hash,
)
from voice_flow.video_flow_v3.evidence.builder import (
    EvidenceGraphBuilder,
    calculate_importance_score,
)


def test_document_source_item_and_source_bundle():
    doc1 = DocumentSourceItem(
        doc_id="doc_arch",
        title="Architecture Specs",
        filename="arch.md",
        order=0,
        provenance="upload://arch.md",
        section_id="doc_arch_sec_0",
        content="# Architecture\nThe engine consists of microservices.",
    )
    doc2 = DocumentSourceItem(
        doc_id="doc_bench",
        title="Benchmark Report",
        filename="bench.md",
        order=1,
        provenance="upload://bench.md",
        section_id="doc_bench_sec_0",
        content="# Benchmark\nLatency is under 15ms at 500k rps.",
    )

    bundle = SourceBundle(
        source_name="Multi-Doc Bundle",
        documents=[doc1, doc2],
        privacy_consent=False,
    )

    assert len(bundle.documents) == 2
    assert bundle.documents[0].doc_id == "doc_arch"
    assert bundle.documents[1].title == "Benchmark Report"

    units = SourceNormalizer.segment_source_units(bundle)
    assert len(units) >= 4
    assert bundle.source_hash != ""

    # Verify provenance on units
    assert units[0].doc_id == "doc_arch"
    assert units[0].provenance == "upload://arch.md"
    assert any(u.doc_id == "doc_bench" for u in units)

    # Verify doc_item.units populated
    assert len(doc1.units) > 0
    assert len(doc2.units) > 0


def test_canonical_2d_and_3d_semantic_representation_types():
    canonical_2d = [
        "PROCESS", "CAUSE_EFFECT", "COMPARISON", "TIMELINE", "TRANSFORMATION",
        "HIERARCHY", "NETWORK", "QUANTITATIVE_RELATIONSHIP", "CHART", "LAYER_STACK",
        "SYSTEM_ARCHITECTURE", "DOCUMENT_SOURCE", "CODE_EXPLANATION", "EQUATION_EXPLANATION",
        "MAP_GEOGRAPHY", "SEQUENCE", "OBJECT_FOCUS", "BEFORE_AFTER", "FLOW",
        "CONCEPTUAL_METAPHOR", "LIST_BREAKDOWN", "STAT_GRID", "QUOTE_CALLOUT", "SUMMARY_RECAP"
    ]
    canonical_3d = [
        "ASSEMBLY_3D", "EXPLODED_ASSEMBLY_3D", "CUTAWAY_3D", "COMPONENT_3D",
        "LAYER_STACK_3D", "FLOW_PATH_3D", "TRAJECTORY_3D", "MECHANISM_3D", "SPATIAL_SYSTEM_3D"
    ]

    for t in canonical_2d:
        assert hasattr(SemanticRepresentationType, t), f"Missing 2D type {t}"
        assert SemanticRepresentationType[t].value == t

    for t in canonical_3d:
        assert hasattr(SemanticRepresentationType, t), f"Missing 3D type {t}"
        assert SemanticRepresentationType[t].value == t

    schema = export_contract_schema()
    assert "semantic_transition_types" in schema
    assert "semantic_motion_types" in schema


def test_scene_beat_and_semantic_transitions_and_motions():
    beat = SceneBeat(
        beat_id="beat_1",
        start_sec=0.0,
        end_sec=2.5,
        action="highlight_node",
        target_ids=["obj_gateway", "obj_worker"],
        narration_cue="Notice the API gateway routes traffic",
        description="Emphasizes the central routing entrypoint",
    )
    assert beat.beat_id == "beat_1"
    assert beat.start_sec == 0.0
    assert beat.end_sec == 2.5
    assert len(beat.target_ids) == 2

    # Transitions enum
    assert SemanticTransitionType.MATCH_TRANSITION.value == "MATCH_TRANSITION"
    assert SemanticTransitionType.CARRY.value == "CARRY"
    assert SemanticTransitionType.TRAVERSE.value == "TRAVERSE"
    assert SemanticTransitionType.EXPAND.value == "EXPAND"
    assert SemanticTransitionType.COLLAPSE.value == "COLLAPSE"
    assert SemanticTransitionType.DISSOLVE.value == "DISSOLVE"

    # Motions enum
    assert SemanticMotionType.MERGE.value == "MERGE"
    assert SemanticMotionType.SPLIT.value == "SPLIT"
    assert SemanticMotionType.GROW.value == "GROW"
    assert SemanticMotionType.SHRINK.value == "SHRINK"
    assert SemanticMotionType.FLOW.value == "FLOW"
    assert SemanticMotionType.CONNECT.value == "CONNECT"
    assert SemanticMotionType.EXPLODE.value == "EXPLODE"
    assert SemanticMotionType.MORPH.value == "MORPH"
    assert SemanticMotionType.ISOLATE.value == "ISOLATE"
    assert SemanticMotionType.PROGRESS.value == "PROGRESS"
    assert SemanticMotionType.REVEAL_LEVELS.value == "REVEAL_LEVELS"


def test_scene_semantic_and_executable_program_beat_and_transition_defaults():
    scene = SceneSemanticV3(
        scene_id="scene_0",
        chapter_id="chap_0",
        sequence=0,
        teaching_goal="Explain microservice mesh",
        viewer_question="How do services communicate?",
        intended_understanding="Services communicate via gRPC",
        narration_text="Services communicate asynchronously.",
    )
    assert scene.beats == []
    assert scene.transition_type == SemanticTransitionType.DISSOLVE

    scene.beats.append(SceneBeat(beat_id="b1", start_sec=0.0, end_sec=3.0, action="reveal"))
    scene.transition_type = SemanticTransitionType.MATCH_TRANSITION
    assert len(scene.beats) == 1
    assert scene.transition_type == SemanticTransitionType.MATCH_TRANSITION

    exec_prog = ExecutableSceneProgram(scene_id="scene_0")
    assert exec_prog.beats == []
    assert exec_prog.transition_type == SemanticTransitionType.DISSOLVE


def test_adaptive_semantic_budget_section_6_tiers():
    # Tier 1: < 250 words -> 2-4 points, 1-3 scenes
    b1 = calculate_adaptive_semantic_budget(150, mode="summary")
    assert b1["min_points"] == 2
    assert b1["max_points"] == 4
    assert b1["min_scenes"] == 1
    assert b1["max_scenes"] == 3
    assert b1["min_points"] <= b1["target_points"] <= b1["max_points"]
    assert b1["min_scenes"] <= b1["target_scenes"] <= b1["max_scenes"]

    # Tier 2: 250-800 words -> 4-7 points, 3-5 scenes
    b2 = calculate_adaptive_semantic_budget(500, mode="summary")
    assert b2["min_points"] == 4
    assert b2["max_points"] == 7
    assert b2["min_scenes"] == 3
    assert b2["max_scenes"] == 5

    # Tier 3: 800-2500 words -> 6-12 points, 4-8 scenes
    b3 = calculate_adaptive_semantic_budget(1200, mode="summary")
    assert b3["min_points"] == 6
    assert b3["max_points"] == 12
    assert b3["min_scenes"] == 4
    assert b3["max_scenes"] == 8

    # Tier 4: 2500-8000 words -> 8-16 points, 5-10 scenes
    b4 = calculate_adaptive_semantic_budget(4000, mode="summary")
    assert b4["min_points"] == 8
    assert b4["max_points"] == 16
    assert b4["min_scenes"] == 5
    assert b4["max_scenes"] == 10

    # Multi-doc Tier: 10-24 points, 6-12 scenes
    b_multi = calculate_adaptive_semantic_budget(500, mode="summary", is_multi_doc=True)
    assert b_multi["min_points"] == 10
    assert b_multi["max_points"] == 24
    assert b_multi["min_scenes"] == 6
    assert b_multi["max_scenes"] == 12

    # Mode full targeting max bounds
    b_full = calculate_adaptive_semantic_budget(1200, mode="full")
    assert b_full["target_points"] == 12
    assert b_full["target_scenes"] == 8


def test_evidence_graph_multi_doc_synthesis_and_deduplication():
    u1 = SourceUnit(
        unit_id="u_doc1_1",
        order=0,
        raw_text="The cluster achieves 500k rps throughput with sub-10ms latency.",
        normalized_text="The cluster achieves 500k rps throughput with sub-10ms latency.",
        content_type="sentence",
        doc_id="doc_alpha",
        provenance="doc_alpha.md",
    )
    u2 = SourceUnit(
        unit_id="u_doc2_1",
        order=1,
        raw_text="The cluster achieves 500k rps throughput with sub-10ms latency.",  # Duplicate claim in doc2
        normalized_text="The cluster achieves 500k rps throughput with sub-10ms latency.",
        content_type="sentence",
        doc_id="doc_beta",
        provenance="doc_beta.md",
    )
    u3 = SourceUnit(
        unit_id="u_doc2_2",
        order=2,
        raw_text="High latency causes request queue timeouts in worker nodes.",
        normalized_text="High latency causes request queue timeouts in worker nodes.",
        content_type="sentence",
        doc_id="doc_beta",
        provenance="doc_beta.md",
    )

    graph = EvidenceGraphBuilder.build_evidence_graph(
        [u1, u2, u3],
        thesis="Cluster Throughput and Latency",
        mode="summary",
    )

    # Claim 1 & Claim 2 must be deduplicated into a single ClaimEvidence referencing both units and docs
    assert len(graph.claims) == 2
    deduped_claim = graph.claims[0]
    assert "u_doc1_1" in deduped_claim.source_unit_refs
    assert "u_doc2_1" in deduped_claim.source_unit_refs
    assert "doc_alpha" in deduped_claim.doc_refs
    assert "doc_beta" in deduped_claim.doc_refs

    # Verify causal relationship detection between latency claim and timeout claim
    causal_rels = [r for r in graph.relationships if r["type"] == "cause_effect"]
    assert len(causal_rels) >= 1
    assert causal_rels[0]["source_claim_id"] == "claim_u_doc2_2"


def test_calculate_importance_score_section_7():
    thesis = "Distributed Kafka Stream Processing Performance"

    high_importance_claim = ClaimEvidence(
        claim_id="c_high",
        claim_text="Distributed Kafka Stream Processing delivers 500k events/sec with 99.9% availability.",
        source_unit_refs=["u1", "u2"],
        certainty="certain",
        raw_quantity="500k",
        doc_refs=["doc1", "doc2"],
    )

    low_importance_claim = ClaimEvidence(
        claim_id="c_low",
        claim_text="The office kitchen supplies complimentary herbal tea.",
        source_unit_refs=["u3"],
        certainty="claimed",
        doc_refs=["doc1"],
    )

    score_high = calculate_importance_score(high_importance_claim, thesis=thesis, mode="summary")
    score_low = calculate_importance_score(low_importance_claim, thesis=thesis, mode="summary")

    assert 0.0 <= score_high <= 1.0
    assert 0.0 <= score_low <= 1.0
    assert score_high > score_low + 0.3, f"Expected high ({score_high}) to significantly exceed low ({score_low})"

    # Verify visual direction boost
    direction = "Focus on quantum cryptography key distribution protocols"
    crypto_claim = ClaimEvidence(
        claim_id="c_crypto",
        claim_text="Quantum key distribution ensures cryptographic forward secrecy.",
        source_unit_refs=["u4"],
    )
    score_with_dir = calculate_importance_score(crypto_claim, thesis="", mode="summary", visual_direction=direction)
    score_without_dir = calculate_importance_score(crypto_claim, thesis="", mode="summary", visual_direction="")
    assert score_with_dir > score_without_dir

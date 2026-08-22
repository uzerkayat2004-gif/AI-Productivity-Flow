"""Canonical V3 Contracts & Typed Schemas.

DEFINITIVE ARCHITECTURAL INVARIANT:
1. AI authors semantic intent ONLY (CreativePlan / VideoProgramV3).
2. AI NEVER produces executable code (no eval, no JS/Python/shaders/HTML/SVG).
3. AI does NOT decide pixel coordinates or camera XYZ.
4. Deterministic Visual Compiler produces ExecutableSceneProgram.
5. Live canvas player & MP4 exporter consume the exact same ExecutableSceneProgram.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field, asdict

V3_CONTRACT_VERSION = "v3.0.0"


class GenerationStateV3(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    NORMALIZING_SOURCE = "normalizing_source"
    UNDERSTANDING = "understanding"
    DIRECTING = "directing"
    COMPILING_INITIAL = "compiling_initial"
    BUFFERING = "buffering"
    READY = "ready"  # READY_TO_WATCH
    GENERATING_AHEAD = "generating_ahead"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExportStateV3(str, Enum):
    NOT_REQUESTED = "not_requested"
    REQUESTED = "requested"
    EXPORTING = "exporting"
    EXPORTED = "exported"
    FAILED = "failed"


class FidelityClass3D(str, Enum):
    F1_PHYSICAL = "F1"      # Source-grounded physical structure
    F2_SCHEMATIC = "F2"     # Source-grounded schematic
    F3_CONCEPTUAL = "F3"    # Conceptual spatial representation
    F4_INSUFFICIENT = "F4"   # Fallback to premium 2.5D/2D


class PerformanceProfile(str, Enum):
    QUALITY = "QUALITY"
    STANDARD = "STANDARD"      # Default: <=150 display objects/draw calls, <=250k triangles
    COMPATIBILITY = "COMPATIBILITY"


class RepresentationType(str, Enum):
    PROCESS = "PROCESS"
    COMPARISON = "COMPARISON"
    TIMELINE = "TIMELINE"
    HIERARCHY = "HIERARCHY"
    NETWORK = "NETWORK"
    QUANTITATIVE = "QUANTITATIVE"
    CHART = "CHART"
    SYSTEM_ARCHITECTURE = "SYSTEM_ARCHITECTURE"
    OBJECT_FOCUS = "OBJECT_FOCUS"
    TRANSFORMATION = "TRANSFORMATION"
    FLOW = "FLOW"
    BEFORE_AFTER = "BEFORE_AFTER"
    ASSEMBLY_3D = "ASSEMBLY_3D"
    CUTAWAY_3D = "CUTAWAY_3D"
    ANATOMY_EXPLODED = "ANATOMY_EXPLODED"
    SPATIAL_LAYOUT = "SPATIAL_LAYOUT"
    METRIC_CALLOUT = "METRIC_CALLOUT"
    MATRIX_GRID = "MATRIX_GRID"
    VENN_DIAGRAM = "VENN_DIAGRAM"
    CYCLIC_LOOP = "CYCLIC_LOOP"
    FUNNEL = "FUNNEL"
    PYRAMID = "PYRAMID"
    DECISION_TREE = "DECISION_TREE"
    STATE_MACHINE = "STATE_MACHINE"
    GEOGRAPHIC_MAP = "GEOGRAPHIC_MAP"
    CONCEPT_MAP = "CONCEPT_MAP"


@dataclass
class SourceBundle:
    source_text: str
    source_name: str = "Selection"
    source_type: str = "text"  # text, document, url
    source_url: Optional[str] = None
    app_name: Optional[str] = None
    source_hash: str = ""
    privacy_consent: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceUnit:
    unit_id: str
    order: int
    raw_text: str
    normalized_text: str
    content_type: str  # heading, sentence, code_block, table_row, quote
    section_id: str = "section_0"
    source_hash: str = ""


@dataclass
class ClaimEvidence:
    claim_id: str
    claim_text: str
    source_unit_refs: List[str]
    certainty: str = "certain"  # certain, claimed, estimated, disputed, unknown
    raw_quantity: Optional[str] = None
    normalized_quantity: Optional[float] = None
    unit: Optional[str] = None


@dataclass
class EvidenceGraph:
    source_hash: str
    claims: List[ClaimEvidence] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    spatial_affordances: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class LedgerItem:
    unit_id: str
    analyzed: bool = True
    claim_refs: List[str] = field(default_factory=list)
    scene_refs: List[str] = field(default_factory=list)
    disposition: str = "included"  # included, compressed, duplicate, supporting_only, unresolved
    reason: str = ""


@dataclass
class CoverageLedger:
    mode: str
    total_units: int
    analyzed_units: int
    items: List[LedgerItem] = field(default_factory=list)
    unresolved_count: int = 0
    coverage_ratio: float = 1.0


@dataclass
class ArtDirectionGenome:
    family: str  # Industrial Product, Technical Systems, Scientific Visualization, etc.
    palette: Dict[str, str] = field(default_factory=dict)
    typography: Dict[str, str] = field(default_factory=dict)
    materials: Dict[str, Any] = field(default_factory=dict)
    lighting_rig: str = "Technical High Key"
    camera_grammar: str = "HeroFocus"
    motion_grammar: str = "ControlledDeceleration"
    density_rules: Dict[str, Any] = field(default_factory=dict)
    visual_intensity_budget: int = 100


@dataclass
class SemanticObject:
    object_id: str
    label: str
    role: str  # primary, secondary, annotation, container
    semantic_type: str  # process_step, component, node, claim_card, quantitative_bar
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SceneSemanticV3:
    scene_id: str
    chapter_id: str
    sequence: int
    teaching_goal: str
    viewer_question: str
    intended_understanding: str
    narration_text: str
    representation_type: RepresentationType = RepresentationType.OBJECT_FOCUS
    semantic_objects: List[SemanticObject] = field(default_factory=list)
    semantic_relationships: List[Dict[str, Any]] = field(default_factory=list)
    motion_purpose: str = "reveal"  # reveal, compare, flow, explode, transform, focus
    shot_grammar: str = "HeroFocus"
    suggested_duration_sec: float = 5.0
    use_3d: bool = False
    fidelity_3d: FidelityClass3D = FidelityClass3D.F4_INSUFFICIENT
    evidence_refs: List[str] = field(default_factory=list)


@dataclass
class VideoProgramV3:
    contract_version: str = V3_CONTRACT_VERSION
    project_id: str = ""
    mode: str = "summary"
    title: str = ""
    source_hash: str = ""
    art_genome: Optional[ArtDirectionGenome] = None
    representation_type: RepresentationType = RepresentationType.OBJECT_FOCUS
    chapters: List[Dict[str, Any]] = field(default_factory=list)
    scenes: List[SceneSemanticV3] = field(default_factory=list)
    coverage_summary: Dict[str, Any] = field(default_factory=dict)
    total_estimated_duration_sec: float = 0.0


@dataclass
class ExecutableElement2D:
    element_id: str
    layer: str  # background, diagram, node, text, callout, overlay
    compositor: str  # Process, Comparison, Timeline, Hierarchy, Architecture, etc.
    layout_bounds: Dict[str, float]  # x, y, width, height computed deterministically
    style: Dict[str, Any] = field(default_factory=dict)
    animation_keyframes: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ExecutableNode3D:
    node_id: str
    procedural_type: str  # Assembly, Component, Housing, Tube, LayerStack, FlowPath
    transform: Dict[str, Any]  # position, rotation, scale computed deterministically
    material_spec: Dict[str, Any] = field(default_factory=dict)
    camera_target: Optional[Dict[str, Any]] = None
    animation_keyframes: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ExecutableSceneProgram:
    scene_id: str = ""
    sequence: int = 0
    duration_sec: float = 0.0
    elements_2d: List[ExecutableElement2D] = field(default_factory=list)
    nodes_3d: List[ExecutableNode3D] = field(default_factory=list)
    camera_path: List[Dict[str, Any]] = field(default_factory=list)
    audio_segment_url: str = ""
    word_timestamps: List[Dict[str, Any]] = field(default_factory=list)
    contract_version: str = V3_CONTRACT_VERSION


def validate_no_executable_code(payload: Any) -> None:
    """Security Boundary Validator: Rejects any LLM-authored executable code strings."""
    if hasattr(payload, "__dataclass_fields__"):
        raw = json.dumps(asdict(payload))
    elif isinstance(payload, (dict, list, str, int, float, bool, type(None))):
        raw = json.dumps(payload)
    else:
        raw = str(payload)
    forbidden_tokens = [
        "eval(", "<script", "import ", "Function(", "process.", "exec(", "child_process",
        "os.system", "subprocess", "__import__", "require(", "javascript:", "onload=", "onerror=",
    ]
    for token in forbidden_tokens:
        if token in raw:
            raise ValueError(f"Security Boundary Violation: Payload contains forbidden code token '{token}'")


def export_contract_schema() -> Dict[str, Any]:
    """Return canonical V3 JSON schema manifest for cross-language validation."""
    return {
        "contract_version": V3_CONTRACT_VERSION,
        "generation_states": [s.value for s in GenerationStateV3],
        "export_states": [s.value for s in ExportStateV3],
        "fidelities": [f.value for f in FidelityClass3D],
        "performance_profiles": [p.value for p in PerformanceProfile],
        "representation_types": [r.value for r in RepresentationType],
    }

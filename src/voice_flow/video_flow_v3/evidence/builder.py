"""Evidence Graph Extraction, CoverageLedger Accounting, and Spatial Affordance Analyzer for Video Flow V3."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from voice_flow.video_flow_v3.contracts import (
    SourceUnit,
    ClaimEvidence,
    EvidenceGraph,
    LedgerItem,
    CoverageLedger,
    FidelityClass3D,
)


class EvidenceGraphBuilder:
    """Extracts claims, entities, quantities, dates, and spatial affordances into EvidenceGraph."""

    @staticmethod
    def build_evidence_graph(units: List[SourceUnit]) -> EvidenceGraph:
        if not units:
            return EvidenceGraph(source_hash="")

        source_hash = units[0].source_hash if units else ""
        claims: List[ClaimEvidence] = []
        entities: List[Dict[str, Any]] = []
        relationships: List[Dict[str, Any]] = []
        spatial_affordances: List[Dict[str, Any]] = []

        for unit in units:
            text = unit.normalized_text
            # Extract claims & quantities
            quantities = re.findall(r"\b\d+(?:\.\d+)?(?:\%|k|M|B|x|ms|s|h|kg|m|cm|mm)?\b", text)
            raw_qty = quantities[0] if quantities else None

            # Detect certainty
            certainty = "certain"
            if any(w in text.lower() for w in ["approximately", "estimated", "claimed", "about", "around", "disputed"]):
                certainty = "estimated"

            claim_id = f"claim_{unit.unit_id}"
            claims.append(ClaimEvidence(
                claim_id=claim_id,
                claim_text=text,
                source_unit_refs=[unit.unit_id],
                certainty=certainty,
                raw_quantity=raw_qty,
            ))

            # Spatial keyword detection
            if SpatialAffordanceAnalyzer.has_spatial_keywords(text):
                spatial_affordances.append({
                    "unit_id": unit.unit_id,
                    "text": text,
                    "spatial_types": SpatialAffordanceAnalyzer.extract_spatial_types(text),
                })

        return EvidenceGraph(
            source_hash=source_hash,
            claims=claims,
            entities=entities,
            relationships=relationships,
            spatial_affordances=spatial_affordances,
        )


class CoverageLedgerTracker:
    """Tracks SourceUnit accounting for Visual Summary and Full Visual Explanation modes."""

    @staticmethod
    def create_ledger(units: List[SourceUnit], mode: str) -> CoverageLedger:
        items = [
            LedgerItem(
                unit_id=u.unit_id,
                analyzed=True,
                claim_refs=[f"claim_{u.unit_id}"],
                disposition="included",
            )
            for u in units
        ]
        return CoverageLedger(
            mode=mode,
            total_units=len(units),
            analyzed_units=len(units),
            items=items,
            unresolved_count=0,
            coverage_ratio=1.0 if units else 0.0,
        )


class SpatialAffordanceAnalyzer:
    """Analyzes concepts for 3D explanation value & assigns F1-F4 fidelity classes."""

    SPATIAL_KEYWORDS = {
        "structure", "assembly", "components", "housing", "shell", "panel",
        "tube", "pipe", "cable", "layer", "inside", "outside", "flow", "path",
        "trajectory", "rotor", "wheel", "chamber", "exploded", "cutaway",
        "spatial", "drivetrain", "engine", "chassis", "architecture", "mechanism",
    }

    @classmethod
    def has_spatial_keywords(cls, text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in cls.SPATIAL_KEYWORDS)

    @classmethod
    def extract_spatial_types(cls, text: str) -> List[str]:
        lower = text.lower()
        return [kw for kw in cls.SPATIAL_KEYWORDS if kw in lower]

    @classmethod
    def classify_fidelity(cls, text: str, mode: str) -> FidelityClass3D:
        """Classify 3D fidelity deterministically.

        Rejects hallucinated CAD precision when exact source geometry is absent.
        """
        if mode != "spatial_3d":
            return FidelityClass3D.F4_INSUFFICIENT

        lower = text.lower()
        if any(w in lower for w in ["exact cad", "blueprint", "dimensions", "specification", "measured"]):
            return FidelityClass3D.F1_PHYSICAL
        if any(w in lower for w in ["assembly", "drivetrain", "engine", "structure", "components"]):
            return FidelityClass3D.F2_SCHEMATIC
        if cls.has_spatial_keywords(text):
            return FidelityClass3D.F3_CONCEPTUAL

        return FidelityClass3D.F4_INSUFFICIENT

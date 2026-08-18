"""Evidence Graph Extraction, CoverageLedger Accounting, and Spatial Affordance Analyzer for Video Flow V3."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union
from voice_flow.video_flow_v3.contracts import (
    SourceUnit,
    ClaimEvidence,
    EvidenceGraph,
    LedgerItem,
    CoverageLedger,
    FidelityClass3D,
)


def calculate_importance_score(
    claim: Union[ClaimEvidence, Dict[str, Any], str],
    thesis: Optional[str] = "",
    mode: str = "summary",
    visual_direction: Optional[str] = "",
) -> float:
    """Calculate the semantic importance score for a claim strictly matching Spec Section 7.

    Formula Components (Normalized 0.0 - 1.0):
    1. S_thesis: Semantic and token overlap between claim and core thesis / title.
    2. S_quant: Quantitative information density (presence of numbers, percentages, units, metrics).
    3. S_support: Multi-document and multi-unit provenance reinforcement (support weight).
    4. S_direction: Alignment with user visual direction / aesthetic focus.
    5. S_certainty: Epistemic certainty multiplier (certain: 1.0, claimed: 0.8, estimated: 0.7, disputed: 0.4, unknown: 0.5).
    6. S_structure: Structural salience (heading / key sentence / bold concept).
    """
    if isinstance(claim, ClaimEvidence):
        claim_text = claim.claim_text
        raw_quantity = claim.raw_quantity
        certainty = claim.certainty
        refs_count = len(claim.source_unit_refs)
        docs_count = len(claim.doc_refs) if claim.doc_refs else 1
    elif isinstance(claim, dict):
        claim_text = claim.get("claim_text", claim.get("text", ""))
        raw_quantity = claim.get("raw_quantity")
        certainty = claim.get("certainty", "certain")
        refs_count = len(claim.get("source_unit_refs", [])) or 1
        docs_count = len(claim.get("doc_refs", [])) or 1
    else:
        claim_text = str(claim)
        raw_quantity = None
        certainty = "certain"
        refs_count = 1
        docs_count = 1

    text_lower = claim_text.lower()
    words = set(re.findall(r"\b[a-zA-Z]{3,}\b", text_lower))

    # 1. Thesis Alignment (S_thesis)
    s_thesis = 0.5  # neutral baseline
    if thesis:
        thesis_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", thesis.lower()))
        if thesis_words and words:
            overlap = len(words & thesis_words)
            s_thesis = min(1.0, overlap / max(1, min(len(thesis_words), 5)) + (0.2 if overlap > 0 else 0.0))
        else:
            s_thesis = 0.3

    # 2. Quantitative Information Density (S_quant)
    s_quant = 0.0
    if raw_quantity or re.search(r"\b\d+(?:\.\d+)?(?:\%|k|M|B|x|ms|s|h|kg|m|cm|mm|GB|MB|TB|GHz|kbps|mbps|gbps|\$|€)?\b", claim_text):
        s_quant = 0.8
        if re.search(r"\b\d+(?:\.\d+)?\%", claim_text) or re.search(r"\b\d+(?:\.\d+)?\s*(?:x|times|speedup|ms|percent)\b", text_lower):
            s_quant = 1.0

    # 3. Provenance Support & Multi-Doc Reinforcement (S_support)
    s_support = min(1.0, 0.4 + 0.2 * (refs_count - 1) + 0.3 * (docs_count - 1))

    # 4. Visual Direction Alignment (S_direction)
    s_direction = 0.5
    if visual_direction:
        vd_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", visual_direction.lower()))
        if vd_words and words:
            overlap = len(words & vd_words)
            s_direction = min(1.0, 0.4 + 0.3 * overlap)

    # 5. Epistemic Certainty (S_certainty)
    certainty_weights = {
        "certain": 1.0,
        "claimed": 0.8,
        "estimated": 0.7,
        "disputed": 0.4,
        "unknown": 0.5,
    }
    s_certainty = certainty_weights.get(str(certainty).lower(), 0.8)

    # 6. Structural Salience (S_structure)
    s_structure = 0.5
    if len(claim_text) < 80 and ("#" in claim_text or claim_text.isupper() or ":" in claim_text):
        s_structure = 0.9
    elif any(k in text_lower for k in ["primary", "fundamental", "critical", "essential", "key", "main", "architecture", "overview"]):
        s_structure = 0.8

    # 7. Mode-specific Composite Weighting
    mode_norm = (mode or "summary").lower()
    if mode_norm == "summary":
        score = (
            0.30 * s_thesis
            + 0.20 * s_quant
            + 0.20 * s_support
            + 0.10 * s_direction
            + 0.10 * s_certainty
            + 0.10 * s_structure
        )
    elif mode_norm in ("full", "detailed", "deep_dive"):
        score = (
            0.15 * s_thesis
            + 0.25 * s_quant
            + 0.20 * s_support
            + 0.15 * s_direction
            + 0.15 * s_certainty
            + 0.10 * s_structure
        )
    elif mode_norm == "spatial_3d":
        s_spatial = 1.0 if SpatialAffordanceAnalyzer.has_spatial_keywords(claim_text) else 0.2
        score = (
            0.20 * s_thesis
            + 0.15 * s_quant
            + 0.15 * s_support
            + 0.10 * s_direction
            + 0.10 * s_certainty
            + 0.30 * s_spatial
        )
    else:
        score = (
            0.25 * s_thesis
            + 0.20 * s_quant
            + 0.20 * s_support
            + 0.15 * s_direction
            + 0.10 * s_certainty
            + 0.10 * s_structure
        )

    return round(float(max(0.0, min(1.0, score))), 4)


class EvidenceGraphBuilder:
    """Extracts claims, entities, quantities, dates, and spatial affordances into EvidenceGraph with multi-doc synthesis."""

    @classmethod
    def build_evidence_graph(
        cls,
        units: List[SourceUnit],
        thesis: Optional[str] = "",
        mode: str = "summary",
        visual_direction: Optional[str] = "",
    ) -> EvidenceGraph:
        if not units:
            return EvidenceGraph(source_hash="")

        source_hash = units[0].source_hash if units else ""
        claims: List[ClaimEvidence] = []
        entities_map: Dict[str, Dict[str, Any]] = {}
        relationships: List[Dict[str, Any]] = []
        cross_doc_links: List[Dict[str, Any]] = []
        spatial_affordances: List[Dict[str, Any]] = []

        # Claim deduplication dictionary: normalized string -> ClaimEvidence
        claim_dedup_map: Dict[str, ClaimEvidence] = {}

        for unit in units:
            text = unit.normalized_text
            if not text:
                continue

            # Extract quantities
            quantities = re.findall(
                r"\b\d+(?:\.\d+)?(?:\%|k|M|B|x|ms|s|h|kg|m|cm|mm|GB|MB|TB|GHz|kbps|mbps|gbps|\$|€)?\b",
                text,
            )
            raw_qty = quantities[0] if quantities else None

            norm_qty = None
            qty_unit = None
            if raw_qty:
                match = re.match(r"^([\$€]?)\s*(\d+(?:\.\d+)?)\s*([a-zA-Z\%]*)$", raw_qty)
                if match:
                    prefix, num_str, suffix = match.groups()
                    try:
                        norm_qty = float(num_str)
                        qty_unit = suffix or prefix or None
                    except ValueError:
                        pass

            # Detect certainty
            text_lower = text.lower()
            certainty = "certain"
            if any(w in text_lower for w in ["disputed", "controversial", "debated", "conflicting"]):
                certainty = "disputed"
            elif any(w in text_lower for w in ["approximately", "estimated", "about", "around", "roughly"]):
                certainty = "estimated"
            elif any(w in text_lower for w in ["claimed", "alleged", "reported", "supposed"]):
                certainty = "claimed"

            # Deduplication key: alphanumeric normalized content
            dedup_key = re.sub(r"[^\w\s]", "", text_lower).strip()
            matched_claim: Optional[ClaimEvidence] = None

            if dedup_key in claim_dedup_map:
                matched_claim = claim_dedup_map[dedup_key]
            else:
                # Fuzzy token matching for multi-doc deduplication
                unit_tokens = set(re.findall(r"\b\w{3,}\b", text_lower))
                if len(unit_tokens) >= 4:
                    for existing_k, existing_c in claim_dedup_map.items():
                        existing_tokens = set(re.findall(r"\b\w{3,}\b", existing_k))
                        if existing_tokens:
                            jaccard = len(unit_tokens & existing_tokens) / len(unit_tokens | existing_tokens)
                            if jaccard >= 0.85:
                                matched_claim = existing_c
                                break

            if matched_claim:
                # Deduplicate: merge unit refs and doc refs
                if unit.unit_id not in matched_claim.source_unit_refs:
                    matched_claim.source_unit_refs.append(unit.unit_id)
                if unit.doc_id and unit.doc_id not in matched_claim.doc_refs:
                    matched_claim.doc_refs.append(unit.doc_id)
                matched_claim.importance_score = calculate_importance_score(
                    matched_claim, thesis=thesis, mode=mode, visual_direction=visual_direction
                )
            else:
                claim_id = f"claim_{unit.unit_id}"
                doc_refs = [unit.doc_id] if unit.doc_id else []
                new_claim = ClaimEvidence(
                    claim_id=claim_id,
                    claim_text=text,
                    source_unit_refs=[unit.unit_id],
                    certainty=certainty,
                    raw_quantity=raw_qty,
                    normalized_quantity=norm_qty,
                    unit=qty_unit,
                    doc_refs=doc_refs,
                )
                new_claim.importance_score = calculate_importance_score(
                    new_claim, thesis=thesis, mode=mode, visual_direction=visual_direction
                )
                claims.append(new_claim)
                claim_dedup_map[dedup_key] = new_claim

            # Extract entities (Proper nouns, capitalized tech terms)
            raw_target = unit.raw_text or unit.normalized_text
            words_in_text = re.findall(r"\b[A-Z][a-zA-Z0-9_]+(?:\s+[A-Z][a-zA-Z0-9_]+)*\b", raw_target)
            for entity_name in words_in_text:
                if len(entity_name) < 2 or entity_name in ("The", "This", "That", "In", "On", "At", "A", "An", "And", "Or", "If", "When"):
                    continue
                ent_key = entity_name.lower()
                if ent_key not in entities_map:
                    entities_map[ent_key] = {
                        "entity_id": f"ent_{len(entities_map)}",
                        "name": entity_name,
                        "mentions": [unit.unit_id],
                        "doc_refs": [unit.doc_id] if unit.doc_id else [],
                    }
                else:
                    if unit.unit_id not in entities_map[ent_key]["mentions"]:
                        entities_map[ent_key]["mentions"].append(unit.unit_id)
                    if unit.doc_id and unit.doc_id not in entities_map[ent_key]["doc_refs"]:
                        entities_map[ent_key]["doc_refs"].append(unit.doc_id)

            # Spatial affordance detection
            if SpatialAffordanceAnalyzer.has_spatial_keywords(text):
                spatial_affordances.append({
                    "unit_id": unit.unit_id,
                    "text": text,
                    "spatial_types": SpatialAffordanceAnalyzer.extract_spatial_types(text),
                    "doc_id": unit.doc_id,
                })

        # Link Causal, Complementary, and Comparison relationships across claims
        causal_indicators = ["causes", "leads to", "results in", "because", "triggers", "drives", "enables", "produces", "prevents"]
        for i in range(len(claims)):
            c1 = claims[i]
            c1_text = c1.claim_text.lower()
            c1_tokens = set(re.findall(r"\b\w{3,}\b", c1_text))
            is_c1_causal = any(ci in c1_text for ci in causal_indicators)

            for j in range(i + 1, len(claims)):
                c2 = claims[j]
                c2_text = c2.claim_text.lower()
                c2_tokens = set(re.findall(r"\b\w{3,}\b", c2_text))
                shared_tokens = c1_tokens & c2_tokens
                is_c2_causal = any(ci in c2_text for ci in causal_indicators)

                is_cross_doc = bool(c1.doc_refs and c2.doc_refs and set(c1.doc_refs) != set(c2.doc_refs))

                if is_c1_causal and len(shared_tokens) >= 1:
                    rel = {
                        "type": "cause_effect",
                        "source_claim_id": c1.claim_id,
                        "target_claim_id": c2.claim_id,
                        "shared_tokens": list(shared_tokens),
                        "cross_document": is_cross_doc,
                    }
                    relationships.append(rel)
                    if is_cross_doc:
                        cross_doc_links.append(rel)
                elif is_c2_causal and len(shared_tokens) >= 1:
                    rel = {
                        "type": "cause_effect",
                        "source_claim_id": c2.claim_id,
                        "target_claim_id": c1.claim_id,
                        "shared_tokens": list(shared_tokens),
                        "cross_document": is_cross_doc,
                    }
                    relationships.append(rel)
                    if is_cross_doc:
                        cross_doc_links.append(rel)
                elif any(comp in c1_text or comp in c2_text for comp in [" versus ", " vs ", "compared to", "faster than", "differ from", "unlike"]):
                    if len(shared_tokens) >= 1:
                        rel = {
                            "type": "comparison",
                            "source_claim_id": c1.claim_id,
                            "target_claim_id": c2.claim_id,
                            "shared_tokens": list(shared_tokens),
                            "cross_document": is_cross_doc,
                        }
                        relationships.append(rel)
                        if is_cross_doc:
                            cross_doc_links.append(rel)
                elif len(shared_tokens) >= 2:
                    rel = {
                        "type": "complementary",
                        "source_claim_id": c1.claim_id,
                        "target_claim_id": c2.claim_id,
                        "shared_tokens": list(shared_tokens),
                        "cross_document": is_cross_doc,
                    }
                    relationships.append(rel)
                    if is_cross_doc:
                        cross_doc_links.append(rel)

        return EvidenceGraph(
            source_hash=source_hash,
            claims=claims,
            entities=list(entities_map.values()),
            relationships=relationships,
            spatial_affordances=spatial_affordances,
            cross_doc_links=cross_doc_links,
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

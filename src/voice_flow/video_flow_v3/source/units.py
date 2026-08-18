"""Deterministic Source Normalization & SourceUnit Segmentation for Video Flow V3."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional
from voice_flow.video_flow_v3.contracts import DocumentSourceItem, SourceBundle, SourceUnit


def compute_source_hash(text: str) -> str:
    """Deterministically compute a 32-character SHA-256 hash."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:32]


def calculate_adaptive_semantic_budget(
    word_count: int,
    mode: str = "summary",
    is_multi_doc: bool = False,
) -> Dict[str, int]:
    """Calculate adaptive semantic point and scene budget matching Spec Section 6.

    Budget Tiers:
    - < 250 words: 2-4 points, 1-3 scenes
    - 250-800 words: 4-7 points, 3-5 scenes
    - 800-2,500 words: 6-12 points, 4-8 scenes
    - 2,500-8,000 words: 8-16 points, 5-10 scenes
    - Multi-doc: 10-24 points, 6-12 scenes
    """
    effective_words = max(0, word_count)

    if is_multi_doc:
        min_points, max_points = 10, 24
        min_scenes, max_scenes = 6, 12
    elif effective_words < 250:
        min_points, max_points = 2, 4
        min_scenes, max_scenes = 1, 3
    elif effective_words <= 800:
        min_points, max_points = 4, 7
        min_scenes, max_scenes = 3, 5
    elif effective_words <= 2500:
        min_points, max_points = 6, 12
        min_scenes, max_scenes = 4, 8
    else:
        min_points, max_points = 8, 16
        min_scenes, max_scenes = 5, 10

    # Mode-based target tuning
    norm_mode = (mode or "summary").lower()
    if norm_mode == "summary":
        target_points = min_points + int(round((max_points - min_points) * 0.35))
        target_scenes = min_scenes + int(round((max_scenes - min_scenes) * 0.35))
    elif norm_mode in ("full", "detailed", "deep_dive"):
        target_points = max_points
        target_scenes = max_scenes
    else:
        target_points = int(round((min_points + max_points) / 2))
        target_scenes = int(round((min_scenes + max_scenes) / 2))

    # Guard bounds
    target_points = max(min_points, min(max_points, target_points))
    target_scenes = max(min_scenes, min(max_scenes, target_scenes))

    return {
        "min_points": min_points,
        "max_points": max_points,
        "target_points": target_points,
        "points": target_points,
        "min_scenes": min_scenes,
        "max_scenes": max_scenes,
        "target_scenes": target_scenes,
        "scenes": target_scenes,
    }


class SourceNormalizer:
    """Normalizes raw text/documents and segments them into traceable SourceUnits."""

    @staticmethod
    def normalize_text(raw_text: str) -> str:
        if not raw_text:
            return ""
        text = raw_text.strip().replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        return text

    @classmethod
    def segment_source_units(cls, bundle: SourceBundle) -> List[SourceUnit]:
        """Deterministically segment SourceBundle into ordered SourceUnits.

        Supports single-document text and multi-document bundles with provenance tracking.
        Units retain exact original text spans and ordering.
        Segmentation is deterministic (no LLM decision).
        """
        # Resolve list of documents from bundle.documents, metadata, or source_text
        doc_items: List[DocumentSourceItem] = []

        if bundle.documents:
            for idx, d in enumerate(bundle.documents):
                if isinstance(d, DocumentSourceItem):
                    doc_items.append(d)
                elif isinstance(d, dict):
                    doc_items.append(DocumentSourceItem(
                        doc_id=d.get("doc_id", f"doc_{idx + 1}"),
                        title=d.get("title", d.get("name", f"Document {idx + 1}")),
                        filename=d.get("filename", ""),
                        order=d.get("order", idx),
                        provenance=d.get("provenance", d.get("source_url", "")),
                        section_id=d.get("section_id", f"doc_{idx + 1}_sec_0"),
                        content=d.get("content", d.get("raw_text", "")),
                        metadata=d.get("metadata", {}),
                    ))
        elif bundle.metadata.get("documents"):
            for idx, d in enumerate(bundle.metadata["documents"]):
                if isinstance(d, DocumentSourceItem):
                    doc_items.append(d)
                elif isinstance(d, dict):
                    doc_items.append(DocumentSourceItem(
                        doc_id=d.get("doc_id", f"doc_{idx + 1}"),
                        title=d.get("title", d.get("name", f"Document {idx + 1}")),
                        filename=d.get("filename", ""),
                        order=d.get("order", idx),
                        provenance=d.get("provenance", d.get("source_url", "")),
                        section_id=d.get("section_id", f"doc_{idx + 1}_sec_0"),
                        content=d.get("content", d.get("raw_text", "")),
                        metadata=d.get("metadata", {}),
                    ))
        elif bundle.source_text:
            single_doc = DocumentSourceItem(
                doc_id="doc_1",
                title=bundle.source_name or "Document 1",
                filename="",
                order=0,
                provenance=bundle.source_url or "direct_text",
                section_id="doc_1_sec_0",
                content=bundle.source_text,
            )
            doc_items.append(single_doc)
            bundle.documents = [single_doc]

        if not doc_items:
            return []

        # Sync bundle documents
        bundle.documents = doc_items

        # Build full text and overall source hash
        contents = [cls.normalize_text(d.content or "") for d in doc_items if d.content]
        all_text = "\n\n".join(contents)
        if not bundle.source_text:
            bundle.source_text = all_text
        source_hash = compute_source_hash(all_text if all_text else bundle.source_text)
        bundle.source_hash = source_hash

        units: List[SourceUnit] = []
        global_order = 0
        is_multi = len(doc_items) > 1

        for doc_idx, doc_item in enumerate(doc_items):
            doc_item.order = doc_idx
            if not doc_item.doc_id:
                doc_item.doc_id = f"doc_{doc_idx + 1}"
            doc_name = doc_item.title or f"Document {doc_idx + 1}"
            raw_text = cls.normalize_text(doc_item.content or "")
            if not raw_text:
                continue

            doc_hash = compute_source_hash(raw_text)
            doc_provenance = doc_item.provenance or doc_item.filename or doc_name
            doc_units: List[SourceUnit] = []
            seen_normalized_sentences: set[str] = set()

            raw_blocks = [b.strip() for b in raw_text.split("\n\n") if b.strip()]
            paragraphs = []
            for block in raw_blocks:
                if block.startswith("#") and "\n" in block:
                    lines = [l.strip() for l in block.split("\n") if l.strip()]
                    paragraphs.extend(lines)
                else:
                    paragraphs.append(block)

            section_id = f"{doc_item.doc_id}_sec_main"

            for para in paragraphs:
                # 1. Heading check
                is_heading = (len(para) < 100 and para.startswith("#")) or (
                    len(para) < 80 and "\n" not in para and para.isupper()
                )
                if is_heading:
                    clean_heading = re.sub(r"^#+\s*", "", para).strip()
                    section_id = f"{doc_item.doc_id}_sec_{global_order}"
                    unit_id = f"unit_{global_order}"
                    norm_heading = f"[{doc_name}] {clean_heading}" if is_multi else clean_heading
                    unit = SourceUnit(
                        unit_id=unit_id,
                        order=global_order,
                        raw_text=para,
                        normalized_text=norm_heading,
                        content_type="heading",
                        section_id=section_id,
                        source_hash=doc_hash,
                        doc_id=doc_item.doc_id,
                        provenance=doc_provenance,
                    )
                    units.append(unit)
                    doc_units.append(unit)
                    global_order += 1
                    continue

                # 2. Code block check
                if para.startswith("```"):
                    clean_code = re.sub(r"^```[a-zA-Z]*\n?", "", para)
                    clean_code = re.sub(r"\n?```$", "", clean_code).strip()
                    unit_id = f"unit_{global_order}"
                    unit = SourceUnit(
                        unit_id=unit_id,
                        order=global_order,
                        raw_text=para,
                        normalized_text=clean_code,
                        content_type="code_block",
                        section_id=section_id,
                        source_hash=doc_hash,
                        doc_id=doc_item.doc_id,
                        provenance=doc_provenance,
                    )
                    units.append(unit)
                    doc_units.append(unit)
                    global_order += 1
                    continue

                # 3. Table row check
                if para.startswith("|") and "|" in para[1:]:
                    lines = [l.strip() for l in para.split("\n") if l.strip() and "|" in l]
                    for line in lines:
                        if re.match(r"^\|?\s*[-:]+\s*\|", line):
                            continue  # Skip markdown table divider lines
                        clean_row = re.sub(r"^\s*\|\s*", "", line)
                        clean_row = re.sub(r"\s*\|\s*$", "", clean_row)
                        unit_id = f"unit_{global_order}"
                        unit = SourceUnit(
                            unit_id=unit_id,
                            order=global_order,
                            raw_text=line,
                            normalized_text=clean_row,
                            content_type="table_row",
                            section_id=section_id,
                            source_hash=doc_hash,
                            doc_id=doc_item.doc_id,
                            provenance=doc_provenance,
                        )
                        units.append(unit)
                        doc_units.append(unit)
                        global_order += 1
                    continue

                # 4. Quote check
                if para.startswith(">") or (para.startswith('"') and para.endswith('"') and len(para) < 200):
                    clean_quote = re.sub(r"^>\s*", "", para).strip()
                    unit_id = f"unit_{global_order}"
                    unit = SourceUnit(
                        unit_id=unit_id,
                        order=global_order,
                        raw_text=para,
                        normalized_text=clean_quote,
                        content_type="quote",
                        section_id=section_id,
                        source_hash=doc_hash,
                        doc_id=doc_item.doc_id,
                        provenance=doc_provenance,
                    )
                    units.append(unit)
                    doc_units.append(unit)
                    global_order += 1
                    continue

                # 5. List items check
                if para.startswith("- ") or para.startswith("* ") or re.match(r"^\d+\.\s", para):
                    items = [item.strip() for item in re.split(r"\n\s*[-*\d+\.]\s*", para) if item.strip()]
                    for item in items:
                        normalized_key = item.lower().strip()
                        if normalized_key in seen_normalized_sentences:
                            continue
                        seen_normalized_sentences.add(normalized_key)
                        unit_id = f"unit_{global_order}"
                        unit = SourceUnit(
                            unit_id=unit_id,
                            order=global_order,
                            raw_text=item,
                            normalized_text=item,
                            content_type="list_item",
                            section_id=section_id,
                            source_hash=doc_hash,
                            doc_id=doc_item.doc_id,
                            provenance=doc_provenance,
                        )
                        units.append(unit)
                        doc_units.append(unit)
                        global_order += 1
                    continue

                # 6. Sentence segmentation
                sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", para) if s.strip()]
                for s in sentences:
                    normalized_key = s.lower().strip()
                    if normalized_key in seen_normalized_sentences:
                        continue
                    seen_normalized_sentences.add(normalized_key)
                    unit_id = f"unit_{global_order}"
                    unit = SourceUnit(
                        unit_id=unit_id,
                        order=global_order,
                        raw_text=s,
                        normalized_text=s,
                        content_type="sentence",
                        section_id=section_id,
                        source_hash=doc_hash,
                        doc_id=doc_item.doc_id,
                        provenance=doc_provenance,
                    )
                    units.append(unit)
                    doc_units.append(unit)
                    global_order += 1

            doc_item.units = doc_units

        return units

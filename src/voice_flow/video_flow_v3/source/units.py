"""Deterministic Source Normalization & SourceUnit Segmentation for Video Flow V3."""

from __future__ import annotations

import hashlib
import re
from typing import List, Optional
from voice_flow.video_flow_v3.contracts import SourceBundle, SourceUnit


def compute_source_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:32]


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

        Units retain exact original text spans and ordering.
        Segmentation is deterministic (no LLM decision).
        """
        norm_text = cls.normalize_text(bundle.source_text)
        source_hash = compute_source_hash(norm_text)
        bundle.source_hash = source_hash

        if not norm_text:
            return []

        units: List[SourceUnit] = []
        raw_blocks = [b.strip() for b in norm_text.split("\n\n") if b.strip()]
        paragraphs = []
        for block in raw_blocks:
            if block.startswith("#") and "\n" in block:
                lines = [l.strip() for l in block.split("\n") if l.strip()]
                paragraphs.extend(lines)
            else:
                paragraphs.append(block)
        order = 0
        section_id = "sec_main"

        for p_idx, para in enumerate(paragraphs):
            # Check if heading
            is_heading = len(para) < 100 and para.startswith("#") or (len(para) < 80 and "\n" not in para and para.isupper())
            if is_heading:
                clean_heading = re.sub(r"^#+\s*", "", para).strip()
                section_id = f"sec_{order}"
                unit_id = f"unit_{order}"
                units.append(SourceUnit(
                    unit_id=unit_id,
                    order=order,
                    raw_text=para,
                    normalized_text=clean_heading,
                    content_type="heading",
                    section_id=section_id,
                    source_hash=source_hash,
                ))
                order += 1
                continue

            # Check if code block
            if para.startswith("```"):
                clean_code = re.sub(r"^```[a-zA-Z]*\n?", "", para)
                clean_code = re.sub(r"\n?```$", "", clean_code).strip()
                unit_id = f"unit_{order}"
                units.append(SourceUnit(
                    unit_id=unit_id,
                    order=order,
                    raw_text=para,
                    normalized_text=clean_code,
                    content_type="code_block",
                    section_id=section_id,
                    source_hash=source_hash,
                ))
                order += 1
                continue

            # Check if list block
            if para.startswith("- ") or para.startswith("* ") or re.match(r"^\d+\.\s", para):
                items = [item.strip() for item in re.split(r"\n\s*[-*\d+\.]\s*", para) if item.strip()]
                for item in items:
                    unit_id = f"unit_{order}"
                    units.append(SourceUnit(
                        unit_id=unit_id,
                        order=order,
                        raw_text=item,
                        normalized_text=item,
                        content_type="list_item",
                        section_id=section_id,
                        source_hash=source_hash,
                    ))
                    order += 1
                continue

            # Split paragraph into sentences deterministically
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", para) if s.strip()]
            for s in sentences:
                unit_id = f"unit_{order}"
                units.append(SourceUnit(
                    unit_id=unit_id,
                    order=order,
                    raw_text=s,
                    normalized_text=s,
                    content_type="sentence",
                    section_id=section_id,
                    source_hash=source_hash,
                ))
                order += 1

        return units

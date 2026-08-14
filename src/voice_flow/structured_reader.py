"""Conversational Human Explainer & Narrator Engine for Audio Flow.

Converts complex document structures — titles, metadata, section headings, numbered sections,
vertical item lists, arrow workflow diagrams (A → B → C), bullet lists, and multi-paragraph prose — into natural,
human-explained conversational audio presentations following human reading prosody rules.
"""

from __future__ import annotations

import re
import logging

log = logging.getLogger(__name__)

# Ordinals for human conversational list presentation
_ORDINALS = [
    "First", "Second", "Third", "Fourth", "Fifth",
    "Sixth", "Seventh", "Eighth", "Ninth", "Tenth",
    "Eleventh", "Twelfth", "Thirteenth", "Fourteenth", "Fifteenth"
]

# Conversational transitions for connecting plain paragraphs naturally
_PARAGRAPH_CONNECTORS = [
    "Also,",
    "Additionally,",
    "Moving on,",
    "Furthermore,"
]

# Patterns
_NUMBERED_HEADER_PATTERN = re.compile(r"^\s*(\d+[.)]\s+[A-Z][^\n]{1,80})$")
_METADATA_KEY_PATTERN = re.compile(r"^\s*([A-Z][A-Za-z0-9_\- ]{1,20})\s*:\s*(.+)$")
_BULLET_PREFIX = re.compile(r"^\s*[\-\*•●○▪▸▹►–—]\s*(.+)$")
_DATE_PATTERN = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


def _ordinal_suffix(day: int) -> str:
    if 11 <= day <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def _format_spoken_date(match: re.Match) -> str:
    """Format YYYY-MM-DD to spoken date e.g. 2026-08-04 -> August 4th, 2026."""
    year, month, day = match.group(1), int(match.group(2)), int(match.group(3))
    if 1 <= month <= 12:
        month_name = _MONTH_NAMES[month]
        suf = _ordinal_suffix(day)
        return f"{month_name} {day}{suf}, {year}"
    return match.group(0)


def process_arrow_pipeline_human(text: str) -> str:
    """Convert arrow workflows like 'idea → plan → recording → editor' to a human explanatory narrative."""
    if not re.search(r"[→➔⇒]|->|=>", text):
        return text

    lines = text.split("\n")
    processed_lines = []

    for line in lines:
        if "http://" in line or "https://" in line:
            processed_lines.append(line)
            continue

        if re.search(r"[→➔⇒]|->|=>", line):
            parts = re.split(r"\s*(?:[→➔⇒]|->|=>)\s*", line)
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) >= 3:
                narrative_steps = []
                for idx, step in enumerate(parts):
                    if idx == 0:
                        narrative_steps.append(f"starting with {step}")
                    elif idx == 1:
                        narrative_steps.append(f"moving to {step}")
                    elif idx == len(parts) - 1:
                        narrative_steps.append(f"and finally {step}")
                    else:
                        narrative_steps.append(f"then {step}")
                line = ", ".join(narrative_steps) + "."
        processed_lines.append(line)

    return "\n".join(processed_lines)


def is_table_layout(lines: list[str]) -> bool:
    """Check if lines represent a structured table (must strictly contain tabs or pipes)."""
    if len(lines) < 2:
        return False

    tsv_count = sum(1 for line in lines if "\t" in line)
    pipe_count = sum(1 for line in lines if "|" in line)
    total = len(lines)
    return (tsv_count / total >= 0.5) or (pipe_count / total >= 0.5)


def format_table_for_speech(lines: list[str]) -> str:
    """Transform table rows into natural human-spoken sentences matching column headers."""
    rows = []
    for line in lines:
        if "|" in line:
            cells = [c.strip() for c in line.split("|") if c.strip() and not re.match(r"^[\s\-:]+$", c)]
        elif "\t" in line:
            cells = [c.strip() for c in line.split("\t") if c.strip()]
        else:
            cells = []
        if cells:
            rows.append(cells)

    if not rows:
        return "\n".join(lines)

    headers = rows[0]
    data_rows = rows[1:]

    narrated_blocks = ["Here is the structured breakdown:"]

    for row in data_rows:
        row_sentences = []
        for i, cell in enumerate(row):
            if i < len(headers):
                header_name = headers[i].strip()
                if cell.lower().startswith(header_name.lower()):
                    row_sentences.append(f"{cell}.")
                else:
                    row_sentences.append(f"{header_name}: {cell}.")
            else:
                row_sentences.append(f"{cell}.")
        narrated_blocks.append(" ".join(row_sentences))

    return "\n\n".join(narrated_blocks)


def is_vertical_list_block(lines: list[str]) -> bool:
    """Detect if a multi-line block consists of vertical short item lines (like tasks/options)."""
    if len(lines) < 2:
        return False
    # If 60%+ of lines are short (<70 chars) and don't end with sentence punctuation (. ! ?)
    short_unpunctuated = sum(1 for l in lines if len(l) <= 75 and not re.search(r"[.!?]$", l))
    return (short_unpunctuated / float(len(lines))) >= 0.6


def format_document_structure_for_speech(raw_text: str) -> str:
    """Format raw selected text using human reading prosody rules:
    - Numbered section titles (e.g. '7. Project assessment') -> Header announcement with pause
    - Vertical list items without bullets -> Ordinals ('First, ... Second, ...')
    - Clause lead-ins ending in ':' -> Suspended pitch lead-in
    - Paragraph transitions -> Smooth pacing without awkward capitalization
    """
    if not raw_text or not raw_text.strip():
        return raw_text

    text = raw_text.strip()

    # 1. Format dates (YYYY-MM-DD -> Month Day-th, Year)
    text = _DATE_PATTERN.sub(_format_spoken_date, text)

    # 2. Process arrow workflows
    text = process_arrow_pipeline_human(text)

    # Split text into distinct paragraph blocks (2+ newlines)
    raw_blocks = [block.strip() for block in re.split(r"\n{2,}", text) if block.strip()]
    if not raw_blocks:
        raw_blocks = [text]

    formatted_blocks = []
    bullet_counter = 0

    for block_idx, block in enumerate(raw_blocks):
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue

        # Check Table Layout
        if is_table_layout(lines):
            try:
                formatted_blocks.append(format_table_for_speech(lines))
                continue
            except Exception:
                pass

        # Check Vertical Unbulleted List Block (e.g. Examine sample sources \n Write research question)
        if is_vertical_list_block(lines):
            list_sentences = []
            for item in lines:
                ordinal_prefix = _ORDINALS[bullet_counter] if bullet_counter < len(_ORDINALS) else f"Item {bullet_counter + 1}"
                bullet_counter += 1
                item_text = item.strip()
                if not re.search(r"[.!?:;]$", item_text):
                    item_text += "."
                list_sentences.append(f"{ordinal_prefix}, {item_text}")
            formatted_blocks.append(" ".join(list_sentences))
            continue

        # Detect single-line standalone Document Title for the first block if document has multiple blocks
        if block_idx == 0 and len(raw_blocks) > 1 and len(lines) == 1:
            first_line = lines[0].strip()
            if not _METADATA_KEY_PATTERN.match(first_line) and not _BULLET_PREFIX.match(first_line) and not first_line.startswith("#"):
                if not re.search(r"[.!?:;]$", first_line):
                    first_line += "."
                if not first_line.lower().startswith("document title:"):
                    first_line = f"Document Title: {first_line}"
                formatted_blocks.append(first_line)
                continue

        # Detect single-line standalone Section Heading for subsequent blocks
        if block_idx > 0 and len(lines) == 1:
            first_line = lines[0].strip()
            if len(first_line) <= 80 and not _METADATA_KEY_PATTERN.match(first_line) and not _BULLET_PREFIX.match(first_line) and not first_line.startswith("#") and not re.search(r"[.!?]$", first_line):
                first_line = f"Section: {first_line}."
                formatted_blocks.append(first_line)
                continue

        block_lines = []
        for i, line in enumerate(lines):
            # Clean duplicate prefix if present
            clean_line = line
            if clean_line.lower().startswith("document title:"):
                clean_line = clean_line[15:].strip()
            elif clean_line.lower().startswith("title:"):
                clean_line = clean_line[6:].strip()

            # Numbered Header line (e.g. "7. Project assessment — about 45 minutes")
            num_header_match = _NUMBERED_HEADER_PATTERN.match(line)
            if num_header_match:
                header_title = num_header_match.group(1).strip()
                if not re.search(r"[.!?:;]$", header_title):
                    header_title += "."
                block_lines.append(f"Section: {header_title}")
                bullet_counter = 0
                continue

            # Markdown Headings (# Title, ## Section)
            if line.startswith("#"):
                heading = line.lstrip("#").strip()
                if line.startswith("# ") and block_idx == 0 and i == 0:
                    block_lines.append(f"Document Title: {heading}.")
                else:
                    block_lines.append(f"Section: {heading}.")
                bullet_counter = 0
                continue

            # Bullet lists (- Item, * Item)
            bullet_match = _BULLET_PREFIX.match(line)
            if bullet_match:
                item_text = bullet_match.group(1).strip()
                ordinal_prefix = _ORDINALS[bullet_counter] if bullet_counter < len(_ORDINALS) else f"Item {bullet_counter + 1}"
                bullet_counter += 1

                if not re.search(r"[.!?:;]$", item_text):
                    item_text += "."

                item_text = re.sub(r"\*\*([^*]+)\*\*", r"\1:", item_text)
                block_lines.append(f"{ordinal_prefix}, {item_text}")
                continue
            else:
                if not _METADATA_KEY_PATTERN.match(line):
                    bullet_counter = 0

            # Metadata Key-Value pairs
            meta_match = _METADATA_KEY_PATTERN.match(line)
            if meta_match:
                label = meta_match.group(1).strip()
                val = meta_match.group(2).strip()
                if not re.search(r"[.!?:;]$", val):
                    val += "."
                block_lines.append(f"{label}: {val}")
                continue

            # Explicit Title tag
            if line.lower().startswith("title:") or line.lower().startswith("document title:"):
                title_text = clean_line
                if not re.search(r"[.!?:;]$", title_text):
                    title_text += "."
                block_lines.append(f"Document Title: {title_text}")
                continue

            # Plain prose line
            block_lines.append(line)

        formatted_blocks.append(" ".join(block_lines))

    # Rejoin formatted paragraph blocks with natural speech pauses
    result = "\n\n".join(formatted_blocks)

    # Clean up double periods or spaces
    result = re.sub(r"\.{2,}", ".", result)
    result = re.sub(r"\s+\.", ".", result)

    return result

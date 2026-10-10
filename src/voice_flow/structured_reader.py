"""Conversational Human Explainer & Narrator Engine for Audio Flow.

Converts complex document structures — titles, metadata, section headings, numbered sections,
vertical item lists, arrow workflow diagrams (A → B → C), bullet lists, currencies, metrics,
timestamps, code snippets, and multi-paragraph prose — into natural, human-explained conversational
audio presentations following human reading prosody rules.
"""

from __future__ import annotations

import re
import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pause markers — Unicode Private Use Area characters that encode structural
# pause intent directly into the text stream.  The TTS engine strips them
# before synthesis and uses them to decide inter-sentence silence duration.
# ---------------------------------------------------------------------------
PAUSE_PARAGRAPH = "\uE010"   # Between paragraph blocks  → 750-900 ms
PAUSE_SECTION   = "\uE011"   # After section / title headings → 950-1200 ms
PAUSE_LIST_ITEM = "\uE012"   # Between ordinal list items → 250-350 ms

# Regex that matches any pause marker (for stripping before TTS synthesis)
_PAUSE_MARKER_RE = re.compile(r"[\uE010\uE011\uE012]")

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
_METADATA_KEY_PATTERN = re.compile(r"^\s*([A-Z][A-Za-z0-9_\- ]{0,25}[A-Za-z])\s*:\s*(.+)$")
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


def get_ordinal_label(idx: int) -> str:
    """Generate smooth spoken ordinals (First, Second ... Twenty-first ... Item N)."""
    if 0 <= idx < len(_ORDINALS):
        return _ORDINALS[idx]
    num = idx + 1
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    ones_ord = ["", "First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth"]
    teens_ord = ["Tenth", "Eleventh", "Twelfth", "Thirteenth", "Fourteenth", "Fifteenth", "Sixteenth", "Seventeenth", "Eighteenth", "Nineteenth"]
    if 1 <= num <= 9:
        return ones_ord[num]
    elif 10 <= num <= 19:
        return teens_ord[num - 10]
    elif 20 <= num <= 99:
        t = num // 10
        o = num % 10
        if o == 0:
            tens_ord = ["", "", "Twentieth", "Thirtieth", "Fortieth", "Fiftieth", "Sixtieth", "Seventieth", "Eightieth", "Ninetieth"]
            return tens_ord[t]
        return f"{tens[t]}-{ones_ord[o]}"
    return f"Item {num}"


def split_spoken_sentences(text: str) -> list[str]:
    """Split text into sentences while protecting abbreviations, decimals, initials, and quotes.

    Prevents speech synthesizers from pausing in the middle of titles (Dr. Smith),
    abbreviations (e.g., i.e., vs.), decimals ($3.14, 4.5%), or acronyms (U.S., D.C.).
    """
    if not text or not text.strip():
        return []

    p = text.strip()

    # 1. Mask URLs
    urls: list[str] = []
    def _mask_url(m: re.Match) -> str:
        urls.append(m.group(0))
        return f"\uE003{len(urls)-1}\uE003"
    p = re.sub(r"https?://\S+|www\.\S+", _mask_url, p)

    # 2. Mask decimal numbers (e.g. 3.14, $4.50, 99.9%)
    p = re.sub(r"(?<=\d)\.(?=\d)", "\uE000", p)

    # 3. Mask ellipses (...)
    p = re.sub(r"\.{2,}|…", "\uE001", p)

    # 4. Mask titles followed by capitalized names (Dr. Smith, Mr. Brown, etc.)
    def _mask_abbrev(m: re.Match) -> str:
        return m.group(0).replace(".", "\uE000")

    p = re.sub(
        r"\b(Dr|Mr|Mrs|Ms|Prof|Sr|Jr|Rev|Hon|Gov|Pres|Sen|Rep|Gen|Col|Capt|Lt|Sgt|Cpl|Pvt|St|Mt|Ft)\.\s*(?=[A-Z])",
        _mask_abbrev,
        p,
        flags=re.IGNORECASE,
    )

    # Reference prefixes: Fig. 1, Figs. 2-3, Vol. 4, No. 5, p. 10, pp. 20-25
    p = re.sub(
        r"\b(Fig|Figs|Vol|Vols|No|Nos|pp?|ed|approx|est)\.\s*(?=\d)",
        _mask_abbrev,
        p,
        flags=re.IGNORECASE,
    )

    # Month abbreviations before numbers: Jan. 15, Feb. 28, etc.
    p = re.sub(
        r"\b(Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.\s*(?=\d)",
        _mask_abbrev,
        p,
        flags=re.IGNORECASE,
    )

    # Common non-terminal abbreviations: e.g., i.e., vs.
    p = re.sub(r"\b(e\.g|i\.e)\.", _mask_abbrev, p, flags=re.IGNORECASE)
    p = re.sub(r"\b(vs|v)\.\s*", _mask_abbrev, p, flags=re.IGNORECASE)

    # Acronyms with internal dots before word characters: U.S., U.K., U.N., D.C.
    p = re.sub(r"\b([A-Za-z])\.(?=[A-Za-z]\.)", lambda m: f"{m.group(1)}\uE000", p)

    # Middle initials in person names: "George W. Bush" -> preceding word is capitalized first name, middle is single letter dot, following is capitalized last name
    _NON_NAME_WORDS = {
        "section", "appendix", "option", "type", "group", "exhibit", "model", "class",
        "tier", "level", "item", "figure", "table", "part", "method", "rule", "factor",
        "case", "point", "page", "step", "sample", "phase", "column", "row", "version",
        "grade", "stage", "category", "volume"
    }
    def _mask_middle_initial(m: re.Match) -> str:
        first = m.group(1).strip()
        if first.lower() in _NON_NAME_WORDS:
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}\uE000 "

    p = re.sub(r"(\b[A-Z][a-z]+\s+)([A-Z])\.\s+(?=[A-Z][a-z]+)", _mask_middle_initial, p)

    # 5. Mark sentence boundaries with \uE002
    boundary_pattern = re.compile(r'([.?!]+["\'”’\)\]\uE010\uE011\uE012]*)\s+(?=[A-Z0-9"\'“‘\(\[]|\Z)')
    p = boundary_pattern.sub(lambda m: f"{m.group(1)}\uE002", p)

    # 6. Split on \uE002 or newlines
    splits = re.split(r"[\uE002\n]+", p)

    results: list[str] = []
    for s in splits:
        s_clean = s.strip()
        if not s_clean or re.fullmatch(r"[\uE010\uE011\uE012\s]+", s_clean):
            continue
        # Restore masked characters
        s_clean = s_clean.replace("\uE000", ".")
        s_clean = s_clean.replace("\uE001", "...")
        for idx, url in enumerate(urls):
            s_clean = s_clean.replace(f"\uE003{idx}\uE003", url)
        results.append(s_clean)

    return results


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
    """Detect if a multi-line block consists of vertical short item lines (like tasks/options) WITHOUT bullets."""
    if len(lines) < 2:
        return False
    # If lines have bullet prefixes, let the bullet parser handle them cleanly
    if any(_BULLET_PREFIX.match(l) for l in lines):
        return False
    short_unpunctuated = sum(1 for l in lines if len(l) <= 75 and not re.search(r"[.!?]$", l))
    return (short_unpunctuated / float(len(lines))) >= 0.6


def format_spoken_text_prosody(text: str) -> str:
    """Transform abbreviations, times, currencies, metrics, units, and markdown symbols into spoken English."""
    if not text or not text.strip():
        return text

    # 1. Clean markdown links: [Title](http://...) -> Title
    text = re.sub(r"\[([^\]\n]+)\]\((?:https?://[^\)\s]+)\)", r"\1", text)

    # 2. Clean citation and footnote tags e.g. [1], [^2], [1, 2], [1-5]
    text = re.sub(r"\[(?:\^?\d+(?:,\s*\d+)*|\d+\s*-\s*\d+)\]", "", text)
    text = re.sub(r"\((?:see\s+)?(?:fig|figure|table)\.?\s*\d+[a-z]?\)", "", text, flags=re.IGNORECASE)

    # 3. Email addresses: user@domain.com -> user at domain dot com
    def _sub_email(m: re.Match) -> str:
        user = m.group(1)
        domain = m.group(2).replace(".", " dot ")
        return f"{user} at {domain}"
    text = re.sub(r"\b([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b", _sub_email, text)

    # 4. Spoken Times e.g. 14:30 -> 2:30 PM, 09:15 -> 9:15 AM
    def _sub_time(m: re.Match) -> str:
        hh = int(m.group(1))
        mm = m.group(2)
        ampm = m.group(3)
        if ampm:
            return f"{hh}:{mm} {ampm.strip().upper()}"
        if hh == 0:
            return f"12:{mm} AM"
        elif hh == 12:
            return f"12:{mm} PM"
        elif 13 <= hh <= 23:
            return f"{hh - 12}:{mm} PM"
        elif 1 <= hh <= 11:
            return f"{hh}:{mm} AM"
        return m.group(0)
    text = re.sub(r"\b(\d{1,2}):(\d{2})(?:\s*(am|pm|AM|PM))?\b", _sub_time, text)

    # 5. Spoken Currencies & Scaled Metrics
    def _sub_scaled_dollar(m: re.Match) -> str:
        val = m.group(1)
        scale = m.group(2).lower()
        scale_map = {"k": "thousand", "m": "million", "b": "billion", "t": "trillion"}
        return f"{val} {scale_map.get(scale, '')} dollars"
    text = re.sub(r"\$([0-9]+(?:\.[0-9]+)?)\s*([kmbtKMBT])\b", _sub_scaled_dollar, text)

    def _sub_dollar(m: re.Match) -> str:
        dollars = m.group(1)
        cents = m.group(2)
        if cents:
            return f"{dollars} dollars and {int(cents)} cents"
        return f"{dollars} dollars"
    text = re.sub(r"\$([0-9]+)(?:\.([0-9]{2}))?\b", _sub_dollar, text)

    text = re.sub(r"€([0-9]+(?:\.[0-9]{2})?)\b", r"\1 euros", text)
    text = re.sub(r"£([0-9]+(?:\.[0-9]{2})?)\b", r"\1 pounds", text)
    text = re.sub(r"₹([0-9]+(?:\.[0-9]{2})?)\b", r"\1 rupees", text)
    text = re.sub(r"¥([0-9]+(?:\.[0-9]{2})?)\b", r"\1 yen", text)

    # 6. Percentages & Multipliers & Dimensions
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*%", r"\1 percent", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*[xX]\b(?!\s*[\d])", r"\1 times", text)
    text = re.sub(r"\b(\d+)\s*[xX]\s*(\d+)\b", r"\1 by \2", text)

    # 7. Units
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*ms\b", r"\1 milliseconds", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*(?:kb|KB)\b", r"\1 kilobytes", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*(?:mb|MB)\b", r"\1 megabytes", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*(?:gb|GB)\b", r"\1 gigabytes", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*(?:tb|TB)\b", r"\1 terabytes", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*(?:ghz|GHz)\b", r"\1 gigahertz", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*(?:mhz|MHz)\b", r"\1 megahertz", text)

    # 8. Numeric ranges (e.g. 800-2400 -> 800 to 2400, 10–20 -> 10 to 20)
    text = re.sub(r"\b(\d+)\s*[-–—]\s*(\d+)\b", r"\1 to \2", text)

    # 9. Spoken Abbreviations
    text = re.sub(r"\bapprox\.\s*", "approximately ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bavg\.\s*", "average ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bmin\.\s*(?=\d|\b)", "minutes ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bsec\.\s*(?=\d|\b)", "seconds ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:hrs?|hr)\.\s*(?=\d|\b)", "hours ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:yrs?|yr)\.\s*(?=\d|\b)", "years ", text, flags=re.IGNORECASE)

    # 10. Comparisons & Programming symbols
    text = re.sub(r"\s*!=\s*", " is not equal to ", text)
    text = re.sub(r"\s*==\s*", " equals ", text)
    text = re.sub(r"\s*<=\s*", " is less than or equal to ", text)
    text = re.sub(r"\s*>=\s*", " is greater than or equal to ", text)
    text = re.sub(r"\s+&&\s+", " and ", text)
    text = re.sub(r"\s+\|\|\s+", " or ", text)

    # 11. Clean inline markdown formatting
    text = re.sub(r"~~([^~]+)~~", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)

    return text


def format_document_structure_for_speech(raw_text: str) -> str:
    """Format raw selected text using human reading prosody rules:
    - Numbered section titles (e.g. '7. Project assessment') -> Header announcement with pause
    - Vertical list items without bullets -> Ordinals ('First, ... Second, ...')
    - Clause lead-ins ending in ':' -> Suspended pitch lead-in
    - Currency, percentages, times, and metric scaling -> Spoken natural terms
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
                ordinal_prefix = get_ordinal_label(bullet_counter)
                bullet_counter += 1
                item_text = item.strip()
                if not re.search(r"[.!?:;]$", item_text):
                    item_text += "."
                list_sentences.append(f"{ordinal_prefix}, {item_text} {PAUSE_LIST_ITEM}")
            formatted_blocks.append("\n".join(list_sentences))
            continue

        # Detect single-line standalone Document Title for the first block if document has multiple blocks
        if block_idx == 0 and len(raw_blocks) > 1 and len(lines) == 1:
            first_line = lines[0].strip()
            if (
                not _METADATA_KEY_PATTERN.match(first_line)
                and not _BULLET_PREFIX.match(first_line)
                and not first_line.startswith("#")
                and not re.search(r"[.!?:;]$", first_line)
                and len(first_line.split()) <= 20
            ):
                first_line += "."
                if not first_line.lower().startswith("document title:"):
                    first_line = f"Document Title: {first_line}"
                formatted_blocks.append(f"{first_line} {PAUSE_SECTION}")
                continue

        # Detect single-line standalone Section Heading for subsequent blocks
        if block_idx > 0 and len(lines) == 1:
            first_line = lines[0].strip()
            if len(first_line) <= 80 and not _METADATA_KEY_PATTERN.match(first_line) and not _BULLET_PREFIX.match(first_line) and not first_line.startswith("#") and not re.search(r"[.!?]$", first_line):
                first_line = f"Section: {first_line}."
                formatted_blocks.append(f"{first_line} {PAUSE_SECTION}")
                continue

        block_lines = []
        is_bullet_block = any(_BULLET_PREFIX.match(l) for l in lines)

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
                block_lines.append(f"Section: {header_title} {PAUSE_SECTION}")
                bullet_counter = 0
                continue

            # Markdown Headings (# Title, ## Section)
            if line.startswith("#"):
                heading = line.lstrip("#").strip()
                if line.startswith("# ") and block_idx == 0 and i == 0:
                    block_lines.append(f"Document Title: {heading}. {PAUSE_SECTION}")
                else:
                    block_lines.append(f"Section: {heading}. {PAUSE_SECTION}")
                bullet_counter = 0
                continue

            # Bullet lists (- Item, * Item)
            bullet_match = _BULLET_PREFIX.match(line)
            if bullet_match:
                item_text = bullet_match.group(1).strip()
                ordinal_prefix = get_ordinal_label(bullet_counter)
                bullet_counter += 1

                if not re.search(r"[.!?:;]$", item_text):
                    item_text += "."

                item_text = re.sub(r"\*\*([^*]+)\*\*", r"\1:", item_text)
                block_lines.append(f"{ordinal_prefix}, {item_text} {PAUSE_LIST_ITEM}")
                continue
            else:
                if not _METADATA_KEY_PATTERN.match(line):
                    bullet_counter = 0

            # Metadata Key-Value pairs: must not be a full sentence with period or time
            meta_match = (
                _METADATA_KEY_PATTERN.match(line)
                if not re.search(r"\b\d{1,2}:\d{2}\b", line) and not (line.endswith(".") and len(line.split()) > 6)
                else None
            )
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
                block_lines.append(f"Document Title: {title_text} {PAUSE_SECTION}")
                continue

            # Plain prose line
            block_lines.append(line)

        if is_bullet_block:
            formatted_blocks.append("\n".join(block_lines))
        else:
            block_text = " ".join(block_lines)
            if len(raw_blocks) > 1 and block_idx < len(raw_blocks) - 1:
                if not block_text.rstrip().endswith(PAUSE_SECTION):
                    block_text += f" {PAUSE_PARAGRAPH}"
            formatted_blocks.append(block_text)

    # Rejoin formatted paragraph blocks with standard paragraph breaks
    result = "\n\n".join(formatted_blocks)

    # Apply prosody transformations
    result = format_spoken_text_prosody(result)

    # Clean up double periods or spaces
    result = re.sub(r"\.{2,}", ".", result)
    result = re.sub(r"\s+\.", ".", result)
    result = re.sub(r"[ \t]+", " ", result)

    return result.strip()


def strip_pause_markers(text: str) -> str:
    """Remove all pause markers from text before sending to TTS synthesis."""
    return _PAUSE_MARKER_RE.sub("", text)


def classify_pause_after_sentence(sentence: str) -> str:
    """Classify the structural pause type at the end of a sentence.

    Returns one of: ``"section"``, ``"paragraph"``, ``"list_item"``,
    ``"colon"``, or ``"sentence"`` (the default).

    The TTS engine calls this for each sentence to decide how long
    to pause before playing the next one.
    """
    if not sentence:
        return "sentence"

    # Check for explicit pause markers at the end of the sentence
    stripped = sentence.rstrip(" \t\n\r\"'”’)]")
    if stripped.endswith(PAUSE_SECTION):
        return "section"
    if stripped.endswith(PAUSE_PARAGRAPH):
        return "paragraph"
    if stripped.endswith(PAUSE_LIST_ITEM):
        return "list_item"

    # Fallback check for markers anywhere in the sentence
    if PAUSE_SECTION in sentence:
        return "section"
    if PAUSE_PARAGRAPH in sentence:
        return "paragraph"
    if PAUSE_LIST_ITEM in sentence:
        return "list_item"

    # Heuristic: sentences ending with colon get a "lead-in" pause
    clean = strip_pause_markers(stripped).rstrip()
    if clean.endswith(":"):
        return "colon"

    return "sentence"

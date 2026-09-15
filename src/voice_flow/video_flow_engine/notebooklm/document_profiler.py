"""Document profiler and adaptive engine for NotebookLM Video Flow."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

# Constants for document profiling
WORDS_PER_PAGE: float = 275.0
WORDS_PER_READING_MINUTE: float = 200.0
MIN_DURATION_SECONDS: int = 30
MAX_DURATION_SECONDS: int = 300  # Hard 5-minute ceiling
MAX_CEILING_THRESHOLD_SECONDS: int = 240

# Hardening budgets / caps
MAX_ANALYSIS_CHARS: int = 200000
MAX_SOURCE_FILE_BYTES: int = 8 * 1024 * 1024
_CLASSIFICATION_HEAD_CHARS: int = 50000
_MAX_PARAGRAPHS_FOR_REDUNDANCY: int = 60
_MAX_PARAGRAPHS_HEAD: int = 40
_MAX_SENTENCES_FOR_SCAN: int = 2500
_MAX_SENTENCES_HEAD: int = 1500
_MAX_SECTIONS_STORED: int = 80
_MAX_SECTION_CONTENT_CHARS: int = 2000


# ---------------------------------------------------------------------------
# Module-level precompiled regexes (hoisted; no per-call re.compile)
# ---------------------------------------------------------------------------

# Heading patterns for section extraction
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_NUM_HEADING_RE = re.compile(
    r"^(?:(?:Section|Part|Step|Chapter)\s+\d+|[0-9]{1,2}\.[0-9]{0,2})\s*[:\-\.]?\s*(.+)$",
    re.IGNORECASE,
)
_BOLD_HEADING_RE = re.compile(r"^\*\*([^\*]+)\*\*:?$")
_CAPS_HEADING_RE = re.compile(r"^[A-Z0-9\s\-_:,\.]{4,60}$")

# Sentence splitters (CJK terminators 。！？； included; CJK needs no trailing space)
_SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[.!?])\s+(?=[A-Z0-9\"'“‘\-\*•])"
    r"|(?<=[。！？；])"
    r"|\n+(?=[-\*•\d+\.]\s+)"
    r"|\n{2,}"
)
_KEY_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|(?<=[。！？；])")
_CONCEPT_TITLE_SPLIT_RE = re.compile(r"[,;:\-—\.]")

# Informational density markers
_CAUSAL_RE = re.compile(
    r"\b(?:because|due to|leads to|leading to|drives|driving|impacts|impacting|"
    r"results in|resulting in|enables|enabling|causes|causing|triggers|generates|"
    r"establishes|creates|determines|regulates|influences|mechanism|principle|"
    r"foundation|consequently|therefore|thus)\b",
    re.IGNORECASE,
)
_METRIC_RE = re.compile(
    r"\b(?:\d+(?:\.\d+)?%?|\$\d+|\b(?:19|20)\d{2}\b|"
    r"\b\d+\s+(?:percent|billion|million|ratio))\b",
    re.IGNORECASE,
)
_DOMAIN_RE = re.compile(
    r"\b(?:election|electoral|voter|ballot|senate|congress|parliament|demographics|"
    r"turnout|campaign|candidate|coalition|legislative|referendum|constitution|"
    r"constitutional|reform|policy|policymaker|economic|inflation|fiscal|gdp|"
    r"monetary|market|geopolitical|framework|architecture|quantum|neural|algorithm|"
    r"model|hypothesis|synthesis|analysis|investigation|governance|paradigm|"
    r"propositions?|strategy|strategic|perspective|foundational|pillar|dimension)\b",
    re.IGNORECASE,
)
_CONTRAST_RE = re.compile(
    r"\b(?:however|whereas|although|compared to|contrast|nevertheless|"
    r"conversely|alternative|shift|divergence)\b",
    re.IGNORECASE,
)

# Tokenizers / misc
_WORD_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_\-\$%\.]+\b")
_CONCEPT_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_]+\b")
_CJK_RE = re.compile(
    r"[\u3040-\u309f\u30a0-\u30ff\u3400-\u4dbf\u4e00-\u9fff"
    r"\uf900-\ufaff\uac00-\ud7af\u1100-\u11ff]"
)
_SENT_TERMINATOR_RE = re.compile(r"[.!?。！？；](?:\s+|$)")
_MD_HEADING_SEARCH_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_STRIP_RE = re.compile(r"^#{1,6}\s+|\*\*|\*|_")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]")
_SUMMARY_OF_LARGE_WORK_RE = re.compile(
    r"\b(?:summary of (?:the |a )?book|book summary|whole book|entire book|"
    r"chapter-by-chapter|comprehensive (?:summary|review|overview|breakdown)|"
    r"meta-analysis|condensed breakdown|in-depth synthesis|"
    r"executive summary of the entire)\b"
)
_PART_FALLBACK_TITLE_RE = re.compile(r"^part\s+\d+\s*:")


# Formats honored by the adaptive engine. Anything else normalizes to "brief"
# tier logic (the same fallback compute_format_duration already applies).
_KNOWN_FORMATS: tuple[str, ...] = ("brief", "short", "explainer", "cinematic")

# Source-file suffixes the profiler reads as text. Binary suffixes (.pdf,
# .docx, images, executables) are never read here: callers must route them
# through voice_flow.video_flow_documents.extract_document_text.
_TEXT_SOURCE_SUFFIXES: frozenset[str] = frozenset(
    {".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm", ".xml", ".rtf"}
)


def _normalize_format_name(value: Any) -> str:
    """Normalize a requested format; unknown names fall back to "brief"."""
    fmt = str(value or "brief").strip().lower()
    return fmt if fmt in _KNOWN_FORMATS else "brief"


def _resolve_profiling_path(candidate: Any) -> Path | None:
    """Resolve a source-file candidate to a readable text file, or None.

    Guards: directories/special files rejected (regular files only),
    binary suffixes rejected, unreadable/oversize files rejected.
    Never raises — a rejected path simply yields no source text.
    """
    try:
        p = Path(str(candidate)).expanduser()
    except (TypeError, ValueError, OSError):
        return None
    try:
        if not p.is_file():
            return None
        if p.suffix.lower() not in _TEXT_SOURCE_SUFFIXES:
            return None
        if p.stat().st_size > MAX_SOURCE_FILE_BYTES:
            return None
    except OSError:
        return None
    return p


def _read_text_source_file(path: Path) -> str:
    """Read a text source file with size + binary guards. Returns "" on failure."""
    try:
        if path.stat().st_size > MAX_SOURCE_FILE_BYTES:
            return ""
        raw = path.read_bytes()
    except OSError:
        return ""
    if b"\x00" in raw[:8192]:
        # Binary content mislabelled with a text suffix — not readable prose.
        return ""
    return raw.decode("utf-8-sig", errors="replace")


def _alt_pattern(terms: Sequence[str], word_boundaries: bool = True) -> str:
    ordered = sorted((re.escape(t) for t in terms), key=len, reverse=True)
    body = "(?:" + "|".join(ordered) + ")"
    return r"\b" + body + r"\b" if word_boundaries else body


_TECHNICAL_KEYWORDS_TUPLE: tuple[str, ...] = (
    "api", "apis", "sdk", "sdks", "endpoint", "endpoints", "tutorial", "tutorials",
    "sop", "sops", "standard operating procedure", "documentation", "reference", "manual",
    "guide", "guidebook", "developer", "engineering", "architecture", "runbook",
    "spec", "specification", "troubleshooting", "installation", "setup", "configuration",
    "deployment", "pipeline", "schema", "schemas", "rest api", "graphql", "microservice",
    "docker", "kubernetes", "database", "sql", "git", "cli", "command", "terminal",
    "algorithm", "data structure", "implementation", "changelog", "release notes",
    "how-to", "howto", "codebase", "function", "method", "class", "library",
    "sdk reference", "parameters", "parameter", "response code", "payload", "json", "yaml",
    "protocol", "protocols", "procedure", "procedures", "guideline", "guidelines",
    "walkthrough", "step-by-step",
)
_SUMMARY_KEYWORDS_TUPLE: tuple[str, ...] = (
    "meeting", "minutes", "meeting minutes", "meeting notes", "summary", "executive summary",
    "action items", "action item", "recap", "standup", "daily standup", "sync",
    "status report", "digest", "tl;dr", "tldr", "bullet points", "briefing", "agenda",
    "attendees", "key takeaways", "next steps", "decisions made", "wrap-up", "weekly sync",
    "brief overview", "concise overview",
)
_EDUCATIONAL_KEYWORDS_TUPLE: tuple[str, ...] = (
    "course", "curriculum", "lesson", "lessons", "module", "modules", "study guide",
    "syllabus", "textbook", "quiz", "lecture", "lectures", "homework", "exam",
    "learning objectives", "learning objective", "prerequisites", "education",
    "educational", "training", "academic", "student", "teacher", "concepts", "concept",
)
_NARRATIVE_KEYWORDS_TUPLE: tuple[str, ...] = (
    "cinematic", "documentary", "history", "historical", "story", "storytelling", "narrative",
    "chronicle", "chronicles", "biography", "memoir", "case study", "deep dive", "deep-dive",
    "journey", "epic", "saga", "tale", "tales", "legend", "drama", "visually immersive",
    "behind the scenes", "investigation", "origins", "evolution", "prologue", "epilogue",
)
_EXPLAINER_KEYWORDS_TUPLE: tuple[str, ...] = (
    "explainer", "explanation", "explain", "walkthrough", "breakdown", "guide", "tutorial",
)

# One precompiled alternation per classification keyword group
_TECH_CTX_RE = re.compile(_alt_pattern(_TECHNICAL_KEYWORDS_TUPLE), re.IGNORECASE)
_SUM_CTX_RE = re.compile(_alt_pattern(_SUMMARY_KEYWORDS_TUPLE), re.IGNORECASE)
_EDU_CTX_RE = re.compile(_alt_pattern(_EDUCATIONAL_KEYWORDS_TUPLE), re.IGNORECASE)
_NAR_CTX_RE = re.compile(_alt_pattern(_NARRATIVE_KEYWORDS_TUPLE), re.IGNORECASE)
_EXPLAINER_CTX_RE = re.compile(_alt_pattern(_EXPLAINER_KEYWORDS_TUPLE), re.IGNORECASE)

# Heading-signal alternations (substring semantics, matching prior `in` checks)
_TECH_HEADING_RE = re.compile(
    _alt_pattern(
        ("api", "endpoint", "parameter", "install", "config", "sop", "guide",
         "tutorial", "architecture", "troubleshoot", "spec", "procedure"),
        word_boundaries=False,
    ),
    re.IGNORECASE,
)
_SUM_HEADING_RE = re.compile(
    _alt_pattern(
        ("meeting", "minutes", "action item", "attendee", "agenda", "key decision",
         "executive summary", "status update"),
        word_boundaries=False,
    ),
    re.IGNORECASE,
)
_EDU_HEADING_RE = re.compile(
    _alt_pattern(
        ("lesson", "module", "curriculum", "syllabus", "learning objective",
         "course", "lecture", "chapter"),
        word_boundaries=False,
    ),
    re.IGNORECASE,
)
_NAR_HEADING_RE = re.compile(
    _alt_pattern(
        ("prologue", "epilogue", "journey", "origins", "history of", "chronicle"),
        word_boundaries=False,
    ),
    re.IGNORECASE,
)

# Body-signal alternations (one scan per group)
_TECH_BODY_RE = re.compile(
    _alt_pattern(
        ("api", "endpoint", "parameters", "protocol", "procedure", "tutorial", "sop",
         "schema", "architecture", "installation", "troubleshooting", "configuration",
         "deployment", "sdk", "developer", "payload")
    ),
    re.IGNORECASE,
)
_EDU_BODY_RE = re.compile(
    _alt_pattern(
        ("lesson", "module", "curriculum", "syllabus", "lecture", "textbook",
         "homework", "exam", "learning objective", "prerequisites")
    ),
    re.IGNORECASE,
)
_SUM_BODY_RE = re.compile(
    _alt_pattern(
        ("meeting", "minutes", "action items", "agenda", "attendees", "recap",
         "standup", "tldr")
    ),
    re.IGNORECASE,
)
_NARR_BODY_RE = re.compile(
    _alt_pattern(
        ("century", "era", "voyage", "expedition", "reign", "empire", "revolution",
         "biography", "memoir", "story", "narrative", "chronicle", "journey", "epic",
         "legend", "tales", "characters", "discovered", "traveled", "chronicled",
         "drama", "legacy", "historical", "dynasty")
    ),
    re.IGNORECASE,
)

# Syntactic code / API / SOP patterns
_CODE_FENCE_RE = re.compile(r"```|~~~")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_HTTP_VERB_RE = re.compile(r"\b(?:GET|POST|PUT|DELETE|PATCH)\s+/[a-zA-Z0-9_\-/{}]+")
_CODE_DEF_RE = re.compile(r"\b(?:def|class|function|import|export|const|let)\s+[a-zA-Z0-9_]+")
_CLI_TOOL_RE = re.compile(r"\b(?:curl|npm|pip|docker|kubectl|git)\s+[a-zA-Z0-9_\-]+")
_SQL_RE = re.compile(r"\b(?:SELECT|INSERT|UPDATE|DELETE)\s+.*?\s+FROM\b", re.IGNORECASE)
_ACRONYM_RE = re.compile(r"\b(?:JSON|YAML|REST|GraphQL|SDK|API)\b")
_STEP_RE = re.compile(r"\bStep\s+\d+[:.]", re.IGNORECASE)
_SOP_RE = re.compile(r"\bSOP\b")


def _count_distinct_matches(rx: re.Pattern[str], text: str) -> int:
    return len({m.group(0).lower() for m in rx.finditer(text)})


def _count_words(text: str | None) -> int:
    """Unified word counter (Latin tokens + CJK char/2 word-equivalents).

    Used at every call site in this file so CJK text is never counted as empty.
    Non-string inputs coerce via str(); uncoercible objects count as 0 words.
    """
    try:
        t = str(text or "")
    except Exception:
        return 0
    if not t.strip():
        return 0
    cjk_chars = _CJK_RE.findall(t)
    if not cjk_chars:
        return len(t.split())
    stripped = _CJK_RE.sub(" ", t)
    latin_count = len(_WORD_TOKEN_RE.findall(stripped))
    total = latin_count + (len(cjk_chars) + 1) // 2
    return max(1, total)


def _sample_paragraphs(paras: list[str]) -> list[str]:
    """Bound paragraph redundancy scan: first 40 + evenly spaced rest (max 60)."""
    if len(paras) <= _MAX_PARAGRAPHS_FOR_REDUNDANCY:
        return paras
    head = paras[:_MAX_PARAGRAPHS_HEAD]
    rest = paras[_MAX_PARAGRAPHS_HEAD:]
    want = _MAX_PARAGRAPHS_FOR_REDUNDANCY - _MAX_PARAGRAPHS_HEAD
    # Evenly spaced indices over the tail (endpoint-safe: never repeats an
    # index or walks past the end when the tail is shorter than the budget).
    count = len(rest)
    picks = {min(count - 1, int(i * count / want)) for i in range(want)}
    return head + [rest[i] for i in sorted(picks)]


def _sample_sentences(sents: list[str]) -> list[str]:
    """Bound sentence scan: first 1500 + evenly spaced sample (max ~2500)."""
    if len(sents) <= _MAX_SENTENCES_FOR_SCAN:
        return sents
    head = sents[:_MAX_SENTENCES_HEAD]
    rest = sents[_MAX_SENTENCES_HEAD:]
    want = _MAX_SENTENCES_FOR_SCAN - _MAX_SENTENCES_HEAD
    count = len(rest)
    picks = {min(count - 1, int(i * count / want)) for i in range(want)}
    return head + [rest[i] for i in sorted(picks)]


def _is_dummy_or_generic_title(title: str | None) -> bool:
    """Detect auto-generated/dummy titles by repetition/low-diversity, not blocklists.

    Real titles such as 'Quantum Entanglement Basics' are preserved.
    """
    t = str(title or "").strip()
    if not t or t.lower() == "overview":
        return True
    if _PART_FALLBACK_TITLE_RE.match(t.lower()):
        return True
    toks = [w.lower() for w in _WORD_TOKEN_RE.findall(t)]
    if len(toks) >= 3 and len(set(toks)) / len(toks) < 0.5:
        return True
    if len(toks) >= 4 and len(set(toks)) <= 2:
        return True
    return False


def format_duration_display(seconds: int) -> str:
    """Format duration in seconds to human-readable display string.

    Examples:
        - 45 -> "~45s"
        - 75 -> "~1m 15s"
        - 150 -> "~2m 30s"
        - 240 -> "~4m 00s (Max ceiling)"
        - 300 -> "~5m 00s (Max ceiling)"

    Non-numeric inputs fall back to the minimum duration instead of raising.
    """
    try:
        # bool is an int subclass — reject it explicitly so True never means 1s.
        if isinstance(seconds, bool):
            raise ValueError("bool is not a valid duration")
        clamped = max(MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, int(seconds)))
    except (TypeError, ValueError):
        clamped = MIN_DURATION_SECONDS
    m = clamped // 60
    s = clamped % 60
    ceiling_suffix = " (Max ceiling)" if clamped >= MAX_CEILING_THRESHOLD_SECONDS else ""
    if m > 0:
        return f"~{m}m {s:02d}s{ceiling_suffix}"
    return f"~{s}s{ceiling_suffix}"


def generate_cinematic_pacing_directive(target_duration_display: str, pacing_style: str) -> str:
    """Generate the strict cinematic pacing directive for NotebookLM."""
    return (
        f"Generate a punchy, high-production cinematic visual overview. "
        f"STRICT DURATION CONSTRAINT: Keep the final video tightly focused at approximately "
        f"{target_duration_display} (maximum 5 minutes). Pacing: {pacing_style}. Avoid filler scenes."
    )


def extract_document_sections(text: str) -> list[dict[str, Any]]:
    """Extract structural sections, headings, and key points from document text."""
    try:
        clean_text = str(text or "").strip().replace("\r\n", "\n").replace("\r", "\n")
    except Exception:
        return []
    if not clean_text:
        return []

    lines = clean_text.splitlines()
    sections: list[dict[str, Any]] = []
    current_title = ""
    current_lines: list[str] = []

    def _key_sentences(bl_s: str) -> list[str]:
        return [s.strip() for s in _KEY_SENT_SPLIT_RE.split(bl_s) if s.strip()]

    def _flush_section():
        nonlocal current_title, current_lines
        body = "\n".join(current_lines).strip()
        if current_title or body:
            if current_title:
                title = current_title
            elif body:
                # Auto-derived title (no heading found): dummy/repetitive filler
                # text gets a generic title via low-diversity detection, while
                # real titles (e.g. 'Quantum Entanglement Basics') are preserved.
                body_toks = body.split()
                if len(body_toks) >= 30 and (
                    len({t.lower() for t in body_toks}) / len(body_toks)
                ) < 0.20:
                    title = "Overview"
                else:
                    title = body.split(".")[0][:60]
            else:
                title = "Overview"
            key_points: list[str] = []
            for bl in body.splitlines():
                bl_s = bl.strip().lstrip("*-• \t")
                if len(bl_s) > 15:
                    sentences = _key_sentences(bl_s)
                    for sent in sentences:
                        if len(sent) > 15:
                            if not sent.endswith((".", "!", "?", "。", "！", "？")):
                                sent += "."
                            if sent not in key_points:
                                key_points.append(sent)
                                if len(key_points) >= 2:
                                    break
                    if len(key_points) >= 2:
                        break
            key_point = " ".join(key_points)
            if not key_point and body:
                first_sent = body.split(". ")[0].strip()
                key_point = first_sent + ("." if not first_sent.endswith(".") else "")

            sections.append({
                "title": title.strip("#* \t"),
                "content": body,
                "word_count": _count_words(body),
                "key_point": key_point[:250],
            })
        current_title = ""
        current_lines = []

    for line in lines:
        sline = line.strip()
        if not sline:
            if current_lines:
                current_lines.append("")
            continue

        m_md = _MD_HEADING_RE.match(sline)
        m_num = _NUM_HEADING_RE.match(sline)
        m_bold = _BOLD_HEADING_RE.match(sline)
        is_caps = (
            _CAPS_HEADING_RE.match(sline)
            and sum(1 for c in sline if c.isupper()) >= 4
            and not sline.endswith((".", ";"))
            and len(sline.split()) <= 7
        )

        if m_md:
            _flush_section()
            current_title = m_md.group(2).strip()
        elif m_num and len(sline) < 100:
            _flush_section()
            current_title = sline
        elif m_bold and len(sline) < 100:
            _flush_section()
            current_title = m_bold.group(1).strip()
        elif is_caps:
            _flush_section()
            current_title = sline.title()
        else:
            current_lines.append(line)

    _flush_section()

    # Preserve a genuine heading found in the first pass before paragraph fallback.
    genuine_title = ""
    if len(sections) == 1:
        _t0 = str(sections[0].get("title", ""))
        if _t0 and not _is_dummy_or_generic_title(_t0):
            genuine_title = sections[0]["title"]

    if len(sections) <= 1 and "\n\n" in clean_text:
        paras = [p.strip() for p in clean_text.split("\n\n") if p.strip()]
        if len(paras) > 1:
            sections = []
            for idx, p in enumerate(paras, 1):
                first_line = p.splitlines()[0].strip()
                title = first_line[:50] + ("..." if len(first_line) > 50 else "")
                key_points = []
                for bl in p.splitlines():
                    bl_s = bl.strip().lstrip("*-• \t")
                    if len(bl_s) > 15:
                        sentences = _key_sentences(bl_s)
                        for sent in sentences:
                            if len(sent) > 15:
                                if not sent.endswith((".", "!", "?", "。", "！", "？")):
                                    sent += "."
                                if sent not in key_points:
                                    key_points.append(sent)
                                    if len(key_points) >= 2:
                                        break
                        if len(key_points) >= 2:
                            break
                kp = " ".join(key_points) or (first_line + ".")
                sections.append({
                    "title": f"Part {idx}: {title}",
                    "content": p,
                    "word_count": _count_words(p),
                    "key_point": kp[:250],
                })
            if genuine_title and sections:
                sections[0]["title"] = genuine_title

    # Cap stored per-section content (keep full word_count) and section list size.
    for sec in sections:
        body = str(sec.get("content", ""))
        sec["word_count"] = _count_words(body)
        if len(body) > _MAX_SECTION_CONTENT_CHARS:
            sec["content"] = body[:_MAX_SECTION_CONTENT_CHARS] + "..."
            sec["truncated"] = True
        else:
            sec["truncated"] = False
    if len(sections) > _MAX_SECTIONS_STORED:
        sections = sections[:_MAX_SECTIONS_STORED]

    return sections


@dataclass(frozen=True)
class ContentValueProfile:
    """Semantic information density, conceptual propositions, and redundancy profile."""

    density_score: float = 1.0  # 0.4 (repetitive) to 2.8 (very high density)
    content_value_rating: str = "standard"  # "low", "standard", "high", "very_high"
    concept_count: int = 1
    effective_word_count: int = 0
    lexical_diversity: float = 0.5
    redundancy_score: float = 0.0
    substantive_concepts: tuple[str, ...] = field(default_factory=tuple)
    summary_of_large_work: bool = False
    high_concept_density: bool = False
    truncated: bool = False
    analysis_char_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "density_score": self.density_score,
            "content_value_rating": self.content_value_rating,
            "concept_count": self.concept_count,
            "effective_word_count": self.effective_word_count,
            "lexical_diversity": self.lexical_diversity,
            "redundancy_score": self.redundancy_score,
            "substantive_concepts": list(self.substantive_concepts),
            "summary_of_large_work": self.summary_of_large_work,
            "high_concept_density": self.high_concept_density,
            "truncated": self.truncated,
            "analysis_char_count": self.analysis_char_count,
        }


_ENGLISH_STOPWORDS: frozenset[str] = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so",
    "some", "such", "than", "that", "that's", "the", "their", "theirs", "them",
    "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll",
    "they're", "they've", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've",
    "were", "weren't", "what", "what's", "when", "when's", "where", "where's",
    "which", "while", "who", "who's", "whom", "why", "why's", "with", "won't",
    "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your",
    "yours", "yourself", "yourselves",
})


def analyze_content_value(text: str = "", context: str = "") -> ContentValueProfile:
    """Analyze document text for semantic information density, unique substantive concepts,
    and redundancy vs. compression factors.
    """
    try:
        clean_full = str(text or "").strip()
    except Exception:
        clean_full = ""
    if not clean_full:
        return ContentValueProfile(
            density_score=1.0,
            content_value_rating="standard",
            concept_count=0,
            effective_word_count=0,
            lexical_diversity=0.0,
            redundancy_score=0.0,
            substantive_concepts=(),
            summary_of_large_work=False,
            high_concept_density=False,
            truncated=False,
            analysis_char_count=0,
        )

    truncated = len(clean_full) > MAX_ANALYSIS_CHARS
    clean_text = clean_full[:MAX_ANALYSIS_CHARS] if truncated else clean_full
    analysis_char_count = len(clean_text)

    def _empty_zero() -> ContentValueProfile:
        return ContentValueProfile(
            density_score=1.0,
            content_value_rating="standard",
            concept_count=0,
            effective_word_count=0,
            lexical_diversity=0.0,
            redundancy_score=0.0,
            substantive_concepts=(),
            summary_of_large_work=False,
            high_concept_density=False,
            truncated=truncated,
            analysis_char_count=analysis_char_count,
        )

    # Unified word tokens (CJK chars count as word-equivalents, never empty for CJK)
    latin_words = _WORD_TOKEN_RE.findall(clean_text)
    cjk_chars = _CJK_RE.findall(clean_text)
    has_cjk = bool(cjk_chars)
    word_count = _count_words(clean_text)
    if word_count == 0:
        return _empty_zero()

    # Detect structured prose vs unstructured word lists (e.g. test dummy text)
    # If text has no sentence terminators (periods/question/exclamation/CJK marks
    # followed by space or end) and no markdown headings or paragraph breaks,
    # treat as baseline unstructured test text.
    has_sentence_terminator = bool(_SENT_TERMINATOR_RE.search(clean_text))
    has_para_or_heading = bool("\n\n" in clean_text or _MD_HEADING_SEARCH_RE.search(clean_text))
    is_structured = has_sentence_terminator or has_para_or_heading

    # Extract substantive non-stopword tokens
    substantive_tokens = [
        w.lower() for w in latin_words
        if w.lower() not in _ENGLISH_STOPWORDS and len(w) > 2 and not w.isdigit()
    ]
    unique_substantive = set(substantive_tokens)
    lexical_diversity = (
        len(unique_substantive) / max(1, len(substantive_tokens))
        if substantive_tokens else 0.5
    )

    if not is_structured:
        # Unstructured word lists (e.g. dummy test strings)
        return ContentValueProfile(
            density_score=1.0,
            content_value_rating="standard",
            concept_count=1,
            effective_word_count=word_count,
            lexical_diversity=round(lexical_diversity, 2),
            redundancy_score=0.0,
            substantive_concepts=(),
            summary_of_large_work=False,
            high_concept_density=False,
            truncated=truncated,
            analysis_char_count=analysis_char_count,
        )

    # Sentence segmentation (bounded scan budget)
    raw_sentences = [
        s.strip()
        for s in _SENTENCE_SPLIT_RE.split(clean_text)
        if s.strip()
    ]
    sentences_for_scan = _sample_sentences(raw_sentences)

    # Extract distinct substantive concepts/claims
    substantive_concepts: list[str] = []
    seen_concept_token_sets: list[set[str]] = []

    for s in sentences_for_scan:
        # Cheap length pre-filter before any regex work
        s_words = s.split()
        if len(s_words) < 4 and not has_cjk:
            continue
        # Strip markdown markers
        s_clean = _MD_STRIP_RE.sub("", s).strip()
        # Cheap stopword pre-filter before the 4 density regexes
        s_tokens = {w.lower() for w in _CONCEPT_TOKEN_RE.findall(s_clean) if w.lower() not in _ENGLISH_STOPWORDS}
        if has_cjk and not s_tokens:
            # CJK sentences carry meaning outside the Latin token space; keep a
            # coarse token set so they are never silently dropped.
            s_tokens = {f"__cjk_{len(s_clean)}__", s_clean[:12]}
        if len(s_tokens) < 3:
            continue

        # Informational weight check (4 precompiled density regexes)
        is_informative = bool(
            _CAUSAL_RE.search(s_clean)
            or _METRIC_RE.search(s_clean)
            or _DOMAIN_RE.search(s_clean)
            or _CONTRAST_RE.search(s_clean)
            or len(s_words) >= 10
            or has_cjk
        )
        if not is_informative:
            continue

        # Check distinctiveness against existing concepts (Jaccard similarity < 0.60)
        is_duplicate = False
        for prev_tokens in seen_concept_token_sets:
            overlap = len(s_tokens & prev_tokens) / max(1, len(s_tokens | prev_tokens))
            if overlap >= 0.60:
                is_duplicate = True
                break
        if not is_duplicate:
            substantive_concepts.append(s_clean[:220])
            seen_concept_token_sets.append(s_tokens)
            if len(substantive_concepts) >= 12:
                break

    concept_count = max(1, len(substantive_concepts))

    # Redundancy and repetition analysis (the "10 identical pages" detector),
    # bounded to at most 60 sampled paragraphs (no O(P^2) over all).
    para_redundancy = 0.0
    paras = [p.strip() for p in clean_text.split("\n\n") if _count_words(p.strip()) >= 10]
    paras = _sample_paragraphs(paras)
    if len(paras) >= 2:
        para_tokens_list = [
            set(w.lower() for w in _CONCEPT_TOKEN_RE.findall(p) if w.lower() not in _ENGLISH_STOPWORDS)
            for p in paras
        ]
        dup_count = 0
        for i in range(1, len(paras)):
            curr_tokens = para_tokens_list[i]
            if not curr_tokens:
                continue
            is_dup = any(
                (len(curr_tokens & prev) / max(1, len(curr_tokens | prev))) >= 0.65
                for prev in para_tokens_list[:i]
                if prev
            )
            if is_dup:
                dup_count += 1
        para_redundancy = dup_count / float(len(paras))

    sent_redundancy = 0.0
    if len(raw_sentences) >= 4:
        # Scans the sampled sentences (bounded budget), consistent with the
        # concept scan above — both thread the same sampled list.
        norm_sents = [_NON_ALNUM_RE.sub("", s.lower()) for s in sentences_for_scan if len(s.split()) >= 4]
        if norm_sents:
            unique_s = len(set(norm_sents))
            sent_redundancy = (len(norm_sents) - unique_s) / float(len(norm_sents))

    redundancy_score = round(max(para_redundancy, sent_redundancy), 2)
    # Effective floor never exceeds word_count: a 10-word doc never becomes 40.
    if redundancy_score >= 0.35:
        scaled = int(round(word_count * (1.0 - 0.75 * redundancy_score)))
        effective_word_count = min(word_count, max(40, scaled))
    else:
        effective_word_count = word_count
    if clean_text and effective_word_count == 0:
        effective_word_count = max(1, min(word_count, 1))

    # Context & topic signals
    full_ctx = f"{clean_text[:1200]} {context}".lower()
    summary_of_large_work = bool(_SUMMARY_OF_LARGE_WORK_RE.search(full_ctx))
    has_dense_topic = bool(_DOMAIN_RE.search(full_ctx))

    concepts_per_100_words = concept_count / max(1.0, word_count / 100.0)
    high_concept_density = bool(
        (concept_count >= 4 and concepts_per_100_words >= 1.6)
        or (summary_of_large_work and concept_count >= 3)
        or (concept_count >= 5 and word_count <= 750)
    )

    if redundancy_score >= 0.50:
        density_score = round(max(0.40, 1.0 - redundancy_score * 0.70), 2)
        content_value_rating = "low"
    else:
        score = 1.0
        if summary_of_large_work:
            score += 0.65
        if has_dense_topic:
            score += 0.30
        if high_concept_density:
            score += 0.35
        if concepts_per_100_words >= 2.0:
            score += min(0.45, (concepts_per_100_words - 1.8) * 0.30)
        if lexical_diversity >= 0.68:
            score += min(0.30, (lexical_diversity - 0.65) * 1.2)
        if concept_count >= 5 and word_count <= 600:
            score += 0.30
        if concept_count >= 8:
            score += min(0.40, (concept_count - 7) * 0.10)

        density_score = round(max(0.70, min(2.80, score)), 2)
        if density_score >= 1.70:
            content_value_rating = "very_high"
        elif density_score >= 1.30:
            content_value_rating = "high"
        elif density_score < 0.80:
            content_value_rating = "low"
        else:
            content_value_rating = "standard"

    # Tiny-doc gate: no high/very_high rating under 50 words or under 5
    # substantive tokens; stopword-only docs stay standard/low.
    # (Rating only — density_score is left intact so explanatory depth
    # directives still fire for dense short passages.)
    if (word_count < 50 or len(substantive_tokens) < 5) and content_value_rating in ("high", "very_high"):
        content_value_rating = "standard"

    return ContentValueProfile(
        density_score=density_score,
        content_value_rating=content_value_rating,
        concept_count=concept_count,
        effective_word_count=effective_word_count,
        lexical_diversity=round(lexical_diversity, 2),
        redundancy_score=redundancy_score,
        substantive_concepts=tuple(substantive_concepts),
        summary_of_large_work=summary_of_large_work,
        high_concept_density=high_concept_density,
        truncated=truncated,
        analysis_char_count=analysis_char_count,
    )


def compute_format_duration(
    words: int,
    format_name: str,
    num_sections: int = 0,
    *,
    density_score: float = 1.0,
    concept_count: int = 0,
    content_value: ContentValueProfile | None = None,
    effective_word_count: int | None = None,
    redundancy_score: float | None = None,
) -> tuple[int, str]:
    """Compute target duration in seconds and pacing style for a given format and document size,
    adaptively scaling based on information density, substantive concepts, and content value.
    """
    if content_value is not None:
        density_score = content_value.density_score
        concept_count = max(concept_count, content_value.concept_count)
        eff_words = content_value.effective_word_count
        if redundancy_score is None:
            redundancy_score = content_value.redundancy_score
    elif effective_word_count is not None:
        try:
            eff_words = int(effective_word_count)
        except (TypeError, ValueError):
            eff_words = words
    else:
        eff_words = words
    try:
        eff_words = max(0, int(eff_words))
    except (TypeError, ValueError):
        eff_words = words

    # Dead explicit parameter: when callers pass redundancy_score without a
    # content_value (e.g. build_adaptive_prompt retargeting), low-redundancy
    # content used to skip compression entirely.
    if (
        content_value is None
        and redundancy_score is not None
        and density_score >= 0.8
    ):
        try:
            red = float(redundancy_score)
        except (TypeError, ValueError):
            red = 0.0
        if red >= 0.50:
            density_score = max(0.40, 1.0 - red * 0.70)

    fmt = str(format_name or "brief").strip().lower()
    # Unknown format names fall back to brief tier logic (never a fixed 90s).
    key = fmt if fmt in _KNOWN_FORMATS else "brief"
    if key == "brief":
        if eff_words <= 270:
            final_seconds = max(35, int(round(35 + (eff_words / 270.0) * 10))) if eff_words > 0 else 45
            if eff_words == 270:
                final_seconds = 45
        elif eff_words <= 1350:
            final_seconds = min(120, int(round(45 + (eff_words - 270) * (75.0 / 1080))))
        else:
            final_seconds = 120
        pacing = "brisk"
    elif key == "short":
        if eff_words <= 150:
            ratio_s = eff_words / 150.0 if eff_words > 0 else 0.0
            final_seconds = max(30, int(round(30 + ratio_s * 15)))
        elif eff_words <= 270:
            final_seconds = int(round(45 + (eff_words - 150) * (5.0 / 120)))
            if eff_words == 270:
                final_seconds = 50
        elif eff_words <= 1350:
            final_seconds = min(150, int(round(50 + (eff_words - 270) * (100.0 / 1080))))
        else:
            final_seconds = 150
        pacing = "brisk"
    elif key == "explainer":
        if eff_words <= 270:
            final_seconds = max(60, int(round(60 + (eff_words / 270.0) * 15)))
            if eff_words == 270:
                final_seconds = 75
        elif eff_words <= 1350:
            final_seconds = min(240, int(round(75 + (eff_words - 270) * (165.0 / 1080))))
        else:
            final_seconds = 240
        pacing = "balanced" if eff_words < 1200 else "measured"
    elif key == "cinematic":
        if eff_words <= 300:
            final_seconds = max(50, int(round(50 + (eff_words / 300.0) * 10)))
            if eff_words == 300:
                final_seconds = 60
        elif eff_words <= 1350:
            final_seconds = min(240, int(round(60 + (eff_words - 300) * (180.0 / 1050))))
        else:
            final_seconds = min(300, int(round(240 + (eff_words - 1350) * 0.05)))
        pacing = "measured"

    if num_sections >= 2:
        if key == "short":
            final_seconds = min(150, max(final_seconds, num_sections * 12))
        elif key == "brief":
            final_seconds = min(120, max(final_seconds, num_sections * 14))
        elif key == "explainer":
            final_seconds = min(240, max(final_seconds, num_sections * 20))
        elif key == "cinematic":
            final_seconds = min(300, max(final_seconds, num_sections * 25))

    # Concept Breathing Room, scaled so tiny dense docs can't jump 4x to the cap:
    # concept floor = min(fmt_cap, max(base, min(concept_count*k, int(base*2.5)+30))).
    if concept_count >= 2:
        base = final_seconds
        if key == "short":
            k, cap = 12, 150
        elif key == "brief":
            k, cap = 15, 120
        elif key == "explainer":
            k, cap = 22, 240
        else:
            k, cap = 28, 300
        concept_floor = min(concept_count * k, int(base * 2.5) + 30)
        final_seconds = min(cap, max(base, concept_floor))

    # Density Scaling Factor:
    if density_score > 1.15:
        multiplier = 1.0 + (density_score - 1.0) * 0.85
        scaled = int(round(final_seconds * multiplier))
        if key == "explainer":
            final_seconds = min(240, max(final_seconds, scaled))
            pacing = "measured"
        elif key == "cinematic":
            final_seconds = min(300, max(final_seconds, scaled))
            pacing = "measured"
        elif key == "brief":
            final_seconds = min(120, max(final_seconds, scaled))
        elif key == "short":
            final_seconds = min(150, max(final_seconds, scaled))
    elif density_score < 0.8:
        # Low density / redundant text: compress duration
        final_seconds = max(MIN_DURATION_SECONDS, int(round(final_seconds * max(0.45, density_score))))

    final_seconds = max(MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, final_seconds))
    return final_seconds, pacing


def build_chapter_breakdown(
    target_duration_seconds: int,
    format_name: str = "brief",
    content_type: str = "general",
    document_text: str | None = None,
    content_value: ContentValueProfile | None = None,
) -> tuple[str, ...]:
    """Compute adaptive narrative chapter breakdown based on target video duration, content type, and document structure."""
    try:
        if isinstance(target_duration_seconds, bool):
            raise ValueError("bool is not a valid duration")
        seconds = max(MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, int(target_duration_seconds)))
    except (TypeError, ValueError):
        seconds = MIN_DURATION_SECONDS

    def _format_time(sec: int) -> str:
        m = sec // 60
        s = sec % 60
        return f"{m}:{s:02d}"

    if document_text:
        sections = extract_document_sections(document_text)
        if len(sections) >= 2:
            num_chapters = min(len(sections), max(2, min(8, seconds // 25)))
            chapters: list[str] = []
            step = len(sections) / float(num_chapters)
            time_per_chap = seconds // num_chapters

            for i in range(num_chapters):
                sec_idx = int(i * step)
                sec_title = sections[sec_idx]["title"]
                start_t = _format_time(i * time_per_chap)
                end_t = "end" if i == num_chapters - 1 else _format_time((i + 1) * time_per_chap)
                next_sec_idx = int((i + 1) * step) if i < num_chapters - 1 else len(sections)
                if next_sec_idx > sec_idx + 1:
                    additional = [sections[j]["title"] for j in range(sec_idx + 1, next_sec_idx)]
                    chapters.append(f"Chapter {i + 1}: {sec_title} & {', '.join(additional[:2])} ({start_t}-{end_t})")
                else:
                    chapters.append(f"Chapter {i + 1}: {sec_title} ({start_t}-{end_t})")
            return tuple(chapters)
        elif content_value and len(content_value.substantive_concepts) >= 3 and (
            not sections
            or (len(sections) == 1 and _is_dummy_or_generic_title(str(sections[0].get("title", ""))))
        ):
            # Dense document with multiple substantive concepts but no manual markdown headers:
            # Structure chapters around the extracted core conceptual propositions
            concepts = list(content_value.substantive_concepts)
            num_chapters = min(len(concepts), max(2, min(5, seconds // 35)))
            chapters = []
            step = len(concepts) / float(num_chapters)
            time_per_chap = seconds // num_chapters

            for i in range(num_chapters):
                c_idx = int(i * step)
                c_title = concepts[c_idx]
                c_head = _CONCEPT_TITLE_SPLIT_RE.split(c_title)[0].strip()[:45]
                start_t = _format_time(i * time_per_chap)
                end_t = "end" if i == num_chapters - 1 else _format_time((i + 1) * time_per_chap)
                next_c_idx = int((i + 1) * step) if i < num_chapters - 1 else len(concepts)
                if next_c_idx > c_idx + 1:
                    additional = [_CONCEPT_TITLE_SPLIT_RE.split(concepts[j])[0].strip()[:35] for j in range(c_idx + 1, next_c_idx)]
                    chapters.append(f"Chapter {i + 1}: {c_head} & {', '.join(additional[:1])} ({start_t}-{end_t})")
                else:
                    chapters.append(f"Chapter {i + 1}: {c_head} ({start_t}-{end_t})")
            return tuple(chapters)
        elif len(sections) == 1:
            sec_title = str(sections[0].get("title", "")).strip()
            # If section has a substantive title (not generic "Overview" or dummy text)
            if sec_title and not _is_dummy_or_generic_title(sec_title):
                half = max(1, seconds // 2)
                return (
                    f"Chapter 1: {sec_title[:40]} — Context & Mechanism (0:00-{_format_time(half)})",
                    f"Chapter 2: {sec_title[:40]} — Key Insights & Impact ({_format_time(half)}-end)",
                )
    if content_type == "technical":
        if seconds <= 45:
            return (
                "Chapter 1: Concept & Setup (0:00-0:20)",
                "Chapter 2: Key Code & Output (0:20-end)",
            )
        if seconds <= 90:
            return (
                "Chapter 1: Architecture & Purpose (0:00-0:25)",
                "Chapter 2: Core Components & Flow (0:25-0:55)",
                "Chapter 3: Verification & Execution (0:55-end)",
            )
        if seconds <= 150:
            return (
                "Chapter 1: System Overview & Architecture (0:00-0:30)",
                "Chapter 2: Core API & Modules (0:30-1:15)",
                "Chapter 3: Implementation & Practical Walkthrough (1:15-1:50)",
                "Chapter 4: Edge Cases & Best Practices (1:50-end)",
            )
        if seconds <= 210:
            return (
                "Chapter 1: Overview & System Architecture (0:00-0:35)",
                "Chapter 2: Core Components & Requirements (0:35-1:15)",
                "Chapter 3: Detailed Implementation & API Walkthrough (1:15-2:15)",
                "Chapter 4: Configuration & Practical Usage (2:15-2:50)",
                "Chapter 5: Best Practices & Verification (2:50-end)",
            )
        return (
            "Chapter 1: Architecture & Technical Scope (0:00-0:45)",
            "Chapter 2: Core Modules & Setup (0:45-1:45)",
            "Chapter 3: Deep-Dive Implementation & Workflows (1:45-3:00)",
            "Chapter 4: Edge Cases, Security & Performance (3:00-4:15)",
            "Chapter 5: Operational Runbook & Summary (4:15-end)",
        )
    if content_type == "educational":
        if seconds <= 45:
            return (
                "Chapter 1: Learning Objective & Setup (0:00-0:20)",
                "Chapter 2: Core Lesson & Summary (0:20-end)",
            )
        if seconds <= 90:
            return (
                "Chapter 1: Concept & Foundations (0:00-0:25)",
                "Chapter 2: Core Principles & Examples (0:25-0:55)",
                "Chapter 3: Key Takeaways & Review (0:55-end)",
            )
        if seconds <= 150:
            return (
                "Chapter 1: Overview & Learning Objectives (0:00-0:30)",
                "Chapter 2: Core Concepts & Principles (0:30-1:15)",
                "Chapter 3: Guided Walkthrough & Examples (1:15-1:50)",
                "Chapter 4: Summary & Knowledge Check (1:50-end)",
            )
        if seconds <= 210:
            return (
                "Chapter 1: Introduction & Learning Objectives (0:00-0:35)",
                "Chapter 2: Core Theoretical Framework (0:35-1:15)",
                "Chapter 3: Detailed Concepts & Deep Walkthrough (1:15-2:15)",
                "Chapter 4: Real-World Applications & Practice (2:15-2:50)",
                "Chapter 5: Key Takeaways & Review (2:50-end)",
            )
        return (
            "Chapter 1: Curriculum Overview & Goals (0:00-0:45)",
            "Chapter 2: Fundamental Principles (0:45-1:45)",
            "Chapter 3: In-Depth Concepts & Case Walkthroughs (1:45-3:00)",
            "Chapter 4: Advanced Applications & Analysis (3:00-4:15)",
            "Chapter 5: Comprehensive Review & Mastery Summary (4:15-end)",
        )
    if content_type == "summary":
        if seconds <= 45:
            return (
                "Chapter 1: Executive Context (0:00-0:20)",
                "Chapter 2: Key Decisions & Next Steps (0:20-end)",
            )
        if seconds <= 90:
            return (
                "Chapter 1: Meeting Purpose & Context (0:00-0:25)",
                "Chapter 2: Key Discussion Points & Decisions (0:25-0:55)",
                "Chapter 3: Action Items & Next Steps (0:55-end)",
            )
        return (
            "Chapter 1: Executive Overview & Context (0:00-0:30)",
            "Chapter 2: Major Decisions & Consensus (0:30-1:00)",
            "Chapter 3: Critical Risks & Considerations (1:00-1:30)",
            "Chapter 4: Assigned Action Items & Next Milestones (1:30-end)",
        )
    if seconds <= 45:
        return (
            "Chapter 1: Hook & Core Premise (0:00-0:20)",
            "Chapter 2: Essential Takeaway & Close (0:20-end)",
        )
    if seconds <= 90:
        return (
            "Chapter 1: Overview & Core Thesis (0:00-0:25)",
            "Chapter 2: Key Insights & Evidence (0:25-0:55)",
            "Chapter 3: Actionable Summary & Verdict (0:55-end)",
        )
    if seconds <= 150:
        return (
            "Chapter 1: Executive Context & Problem Space (0:00-0:30)",
            "Chapter 2: Structural Breakdown & Mechanisms (0:30-1:15)",
            "Chapter 3: Real-World Evidence & Analysis (1:15-1:50)",
            "Chapter 4: Synthesis & Final Conclusion (1:50-end)",
        )
    if seconds <= 210:
        return (
            "Chapter 1: Narrative Hook & Foundation (0:00-0:35)",
            "Chapter 2: Problem Analysis & Key Drivers (0:35-1:15)",
            "Chapter 3: Deep Technical & Strategic Insights (1:15-2:15)",
            "Chapter 4: Practical Applications & Impact (2:15-2:50)",
            "Chapter 5: Executive Verdict & Strategic Takeaways (2:50-end)",
        )
    return (
        "Chapter 1: Prologue & Core Thesis (0:00-0:45)",
        "Chapter 2: Landscape & Problem Architecture (0:45-1:45)",
        "Chapter 3: In-Depth Analytical Breakdown (1:45-3:00)",
        "Chapter 4: Strategic Implications & Global Impact (3:00-4:15)",
        "Chapter 5: Epilogue & Definitive Conclusion (4:15-end)",
    )


def generate_adaptive_directive(
    target_duration_display: str,
    pacing_style: str,
    format_name: str,
    target_duration_seconds: int,
    chapter_breakdown: Sequence[str],
    *,
    density_score: float = 1.0,
    concept_count: int = 0,
) -> str:
    """Generate explicit instructions to Google AI specifying duration, pacing, chapter breakdown, and content depth."""
    try:
        chapters = list(chapter_breakdown or [])
    except TypeError:
        chapters = []
    chapters_str = "; ".join(str(c) for c in chapters)
    fmt_name = _normalize_format_name(format_name)
    try:
        density = float(density_score)
    except (TypeError, ValueError):
        density = 1.0
    try:
        concepts = int(concept_count)
    except (TypeError, ValueError):
        concepts = 0
    density_directive = ""
    if density >= 1.35 or concepts >= 4:
        c_desc = f" ({concepts} core propositions detected)" if concepts >= 2 else ""
        density_directive = (
            f" HIGH INFORMATION DENSITY DIRECTIVE: The source material contains high conceptual density{c_desc}. "
            f"Rather than merely summarizing what is written, thoroughly unpack and explain HOW each mechanism, dynamic, and proposition works in practical reality. "
            f"Dedicate distinct visual scenes and narrative exposition to thoroughly explain, substantiate, and contextualize "
            f"each key claim. Avoid compressing multiple distinct insights into passing bullet points; provide "
            f"comprehensive explanatory depth across the full {target_duration_display} video."
        )

    depth_directive = (
        " CONTENT RETENTION & DEPTH REQUIREMENT: Thoroughly preserve and explain the core ideas, "
        "mechanisms, inner data, evidence, and key takeaways for every section in the source document. "
        "Do NOT merely recite, display, or skim section titles and surface headlines without explanation; "
        "provide substantive narrative coverage and context for each section so viewers gain genuine "
        "understanding of the material. Condense filler and repetitive phrasing, but strictly preserve "
        "the substantive points and context from every page and section."
    )
    combined_depth = f"{depth_directive}{density_directive}"

    if fmt_name == "cinematic":
        cinematic_base = generate_cinematic_pacing_directive(target_duration_display, pacing_style)
        return f"{cinematic_base} Structure narrative chapters: {chapters_str}.{combined_depth}"
    if fmt_name == "short":
        return (
            f"Generate a rapid, high-impact vertical short video (9:16 aspect ratio). "
            f"STRICT DURATION CONSTRAINT: Keep the final video tightly focused at approximately "
            f"{target_duration_display} (maximum 5 minutes). Pacing: {pacing_style}. Avoid filler scenes. "
            f"Structure narrative chapters: {chapters_str}.{combined_depth}"
        )
    if fmt_name == "explainer":
        return (
            f"Generate an engaging, structured visual explainer. "
            f"STRICT DURATION CONSTRAINT: Keep the final video tightly focused at approximately "
            f"{target_duration_display} (maximum 5 minutes). Pacing: {pacing_style}. Avoid filler scenes. "
            f"Structure narrative chapters: {chapters_str}.{combined_depth}"
        )
    # Default: "brief"
    return (
        f"Generate a crisp, executive-ready brief overview. "
        f"STRICT DURATION CONSTRAINT: Keep the final video tightly focused at approximately "
        f"{target_duration_display} (maximum 5 minutes). Pacing: {pacing_style}. Avoid filler scenes. "
        f"Structure narrative chapters: {chapters_str}.{combined_depth}"
    )


@dataclass(frozen=True)
class ContentClassification:
    """Classification of document task and content characteristics."""

    content_type: str  # "technical", "summary", "educational", "narrative", "general"
    detected_intent: str
    is_technical: bool
    is_summary: bool
    is_educational: bool
    is_narrative: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_type": self.content_type,
            "detected_intent": self.detected_intent,
            "is_technical": self.is_technical,
            "is_summary": self.is_summary,
            "is_educational": self.is_educational,
            "is_narrative": self.is_narrative,
        }


_TECHNICAL_KEYWORDS: tuple[str, ...] = _TECHNICAL_KEYWORDS_TUPLE
_SUMMARY_KEYWORDS: tuple[str, ...] = _SUMMARY_KEYWORDS_TUPLE
_EDUCATIONAL_KEYWORDS: tuple[str, ...] = _EDUCATIONAL_KEYWORDS_TUPLE
_NARRATIVE_KEYWORDS: tuple[str, ...] = _NARRATIVE_KEYWORDS_TUPLE
_EXPLAINER_KEYWORDS: tuple[str, ...] = _EXPLAINER_KEYWORDS_TUPLE


def _classification_head(text: str) -> str:
    """Head slice for classification: first 50k chars plus extracted headings."""
    try:
        body = str(text or "")
    except Exception:
        return ""
    if len(body) <= _CLASSIFICATION_HEAD_CHARS:
        return body
    head = body[:_CLASSIFICATION_HEAD_CHARS]
    # Line-scan the head only: scanning the full multi-MB body here would
    # reintroduce the unbounded cost this head slice exists to prevent.
    headings = [line for line in head.splitlines() if line.strip().startswith("#")][:200]
    if headings:
        return head + "\n" + "\n".join(headings)
    return head


def classify_document_content(
    text: str = "",
    *,
    task: str | None = None,
    task_type: str | None = None,
    title: str | None = None,
    intent: str | None = None,
    focus: str | None = None,
    visual_direction: str | None = None,
    mode: str | None = None,
    document_type: str | None = None,
) -> ContentClassification:
    """Analyze document text, structure, and task context to classify intent and document type."""
    raw_text = text or ""
    # Filter out framework internal default modes ("summary", "full", "default", "auto")
    valid_mode = mode if mode and str(mode).strip().lower() not in {"summary", "full", "default", "normal", "auto"} else None
    context = " ".join(
        str(part)
        for part in (task, task_type, title, intent, focus, visual_direction, valid_mode, document_type)
        if part
    ).lower()

    # Bounded analysis head: first 50k chars + extracted headings (not full 3MB text)
    analysis_text = _classification_head(raw_text)
    analysis_lower = analysis_text.lower()

    tech_score = 0
    summary_score = 0
    edu_score = 0
    narrative_score = 0

    # 1. Context keyword matching (explicit task/title/intent carries high signal):
    # one precompiled alternation scan per keyword group.
    if context:
        tech_score += 4 * _count_distinct_matches(_TECH_CTX_RE, context)
        summary_score += 4 * _count_distinct_matches(_SUM_CTX_RE, context)
        edu_score += 4 * _count_distinct_matches(_EDU_CTX_RE, context)
        narrative_score += 4 * _count_distinct_matches(_NAR_CTX_RE, context)
        expl_hits = _count_distinct_matches(_EXPLAINER_CTX_RE, context)
        edu_score += 3 * expl_hits
        tech_score += 2 * expl_hits

    # Explicit intent/task_type/document_type shortcuts
    clean_intent = str(intent or task_type or document_type or "").strip().lower()
    if clean_intent in {"explainer", "tutorial", "technical", "sop", "guide"}:
        tech_score += 8
    elif clean_intent in {"educational", "course", "lesson", "curriculum"}:
        edu_score += 8
    elif clean_intent in {"summary", "brief", "meeting", "digest"}:
        summary_score += 8
    elif clean_intent in {"cinematic", "narrative", "documentary", "story"}:
        narrative_score += 8

    # 2. Structural code blocks and inline code
    code_blocks = len(_CODE_FENCE_RE.findall(analysis_text))
    if code_blocks > 0:
        tech_score += min(12, code_blocks * 3)

    inline_code = len(_INLINE_CODE_RE.findall(analysis_text))
    if inline_code >= 4:
        tech_score += min(6, inline_code // 2)

    # 3. Headings check
    for line in analysis_text.splitlines()[:100]:
        line_s = line.strip()
        if line_s.startswith("#"):
            if _TECH_HEADING_RE.search(line_s):
                tech_score += 4
            if _SUM_HEADING_RE.search(line_s):
                summary_score += 4
            if _EDU_HEADING_RE.search(line_s):
                edu_score += 4
            if _NAR_HEADING_RE.search(line_s):
                narrative_score += 4

    # 4. Syntactic code / API / SOP patterns
    if _HTTP_VERB_RE.search(analysis_text):
        tech_score += 5
    if _CODE_DEF_RE.search(analysis_text):
        tech_score += 4
    if _CLI_TOOL_RE.search(analysis_text):
        tech_score += 4
    if _SQL_RE.search(analysis_text):
        tech_score += 4
    if _ACRONYM_RE.search(analysis_text):
        tech_score += 4
    if _STEP_RE.search(analysis_text):
        tech_score += 4
    if _SOP_RE.search(analysis_text):
        tech_score += 4

    # 5. Keywords found in document body (enables detection in plain text without code fences)
    tech_matches = _count_distinct_matches(_TECH_BODY_RE, analysis_lower)
    if tech_matches > 0:
        tech_score += min(8, tech_matches * 2)

    edu_matches = _count_distinct_matches(_EDU_BODY_RE, analysis_lower)
    if edu_matches > 0:
        edu_score += min(8, edu_matches * 2)

    sum_matches = _count_distinct_matches(_SUM_BODY_RE, analysis_lower)
    if sum_matches > 0:
        summary_score += min(8, sum_matches * 2)

    # 6. Bullet density and summary terms
    lines = [line.strip() for line in analysis_text.splitlines() if line.strip()]
    if lines:
        bullet_lines = sum(1 for line in lines if line.startswith(("* ", "- ", "• ", "[ ]", "[x]")))
        bullet_ratio = bullet_lines / len(lines)
        if bullet_ratio > 0.35:
            summary_score += 3

    # 7. Narrative terms in text
    narrative_score += _count_distinct_matches(_NARR_BODY_RE, analysis_lower)

    # Balanced determination with clear priorities: Technical >= Educational > Summary > Narrative
    max_score = max(tech_score, edu_score, summary_score, narrative_score)
    is_tech = False
    is_edu = False
    is_sum = False
    is_nar = False

    if max_score >= 3:
        if tech_score == max_score and tech_score > 0:
            is_tech = True
            c_type = "technical"
            intent_name = "technical_reference"
        elif edu_score == max_score and edu_score > 0:
            is_edu = True
            c_type = "educational"
            intent_name = "educational_material"
        elif summary_score == max_score and summary_score > 0:
            is_sum = True
            c_type = "summary"
            intent_name = "summary_digest"
        elif narrative_score == max_score and narrative_score >= 2:
            is_nar = True
            c_type = "narrative"
            intent_name = "narrative_story"
        else:
            c_type = "general"
            intent_name = "general_deep_dive"
    else:
        c_type = "general"
        intent_name = "general_deep_dive"

    return ContentClassification(
        content_type=c_type,
        detected_intent=intent_name,
        is_technical=is_tech,
        is_summary=is_sum,
        is_educational=is_edu,
        is_narrative=is_nar,
    )


@dataclass(frozen=True)
class DocumentProfile:
    """Profile of a document and computed video adaptation parameters."""

    word_count: int
    char_count: int
    estimated_pages: float
    estimated_reading_minutes: float
    target_duration_seconds: int
    target_duration_display: str
    recommended_format: str
    pacing_style: str
    adaptive_prompt_directive: str
    chapter_breakdown: tuple[str, ...] = field(default_factory=tuple)
    content_type: str = "general"
    detected_intent: str = "general"
    sections: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    section_count: int = 0
    density_score: float = 1.0
    content_value_rating: str = "standard"
    concept_count: int = 1
    effective_word_count: int = 0
    redundancy_score: float = 0.0
    substantive_concepts: tuple[str, ...] = field(default_factory=tuple)
    truncated: bool = False
    analysis_char_count: int = 0

    @property
    def cinematic_pacing_directive(self) -> str:
        """Convenience accessor for the exact cinematic pacing directive string."""
        return generate_cinematic_pacing_directive(self.target_duration_display, self.pacing_style)

    def to_dict(self) -> dict[str, Any]:
        """Convert profile to serializable dictionary."""
        return {
            "word_count": self.word_count,
            "char_count": self.char_count,
            "estimated_pages": self.estimated_pages,
            "estimated_reading_minutes": self.estimated_reading_minutes,
            "target_duration_seconds": self.target_duration_seconds,
            "target_duration_display": self.target_duration_display,
            "recommended_format": self.recommended_format,
            "pacing_style": self.pacing_style,
            "adaptive_prompt_directive": self.adaptive_prompt_directive,
            "chapter_breakdown": list(self.chapter_breakdown),
            "content_type": self.content_type,
            "detected_intent": self.detected_intent,
            "sections": list(self.sections),
            "section_count": self.section_count,
            "density_score": self.density_score,
            "content_value_rating": self.content_value_rating,
            "concept_count": self.concept_count,
            "effective_word_count": self.effective_word_count,
            "redundancy_score": self.redundancy_score,
            "substantive_concepts": list(self.substantive_concepts),
            "truncated": self.truncated,
            "analysis_char_count": self.analysis_char_count,
        }


def analyze_document_source(
    source: str | Path | None = None,
    *,
    text: str | None = None,
    source_path: str | Path | None = None,
    requested_format: str | None = None,
    target_duration_seconds: int | None = None,
    task: str | None = None,
    task_type: str | None = None,
    title: str | None = None,
    intent: str | None = None,
    focus: str | None = None,
    visual_direction: str | None = None,
    mode: str | None = None,
    document_type: str | None = None,
    **kwargs: Any,
) -> DocumentProfile:
    """Analyze attached source text or file and compute an adaptive video profile.

    Auto-Adaptive Rules:
    - Analyzes content structure, density, task, and intent.
    - < 150 words (snippets/quick notes): 30–45s video target, 'short' format, brisk pacing
    - 150–500 words (~1–2 pages): 60–90s (1–1.5 min) video target, 'brief' format, brisk pacing
    - 500–1200 words (~2–5 pages): 90–150s (1.5–2.5 min) video target, 'explainer' (or 'brief' for summaries)
    - 1200–2500 words (~5–10 pages): 150–210s (2.5–3.5 min) video target, 'explainer' (or 'brief' for summaries)
    - 2500+ words (Large Documents): Task/content-aware auto selection:
      * Technical docs, tutorials, SOPs, API guides, reference docs, educational material: 'explainer' (180–240s, measured)
      * Meeting notes, summaries, executive digests: 'brief' (90–120s, balanced)
      * Narrative, historical, storytelling, documentary, deep-dive case studies, or general long-form: 'cinematic' (240–300s, measured)
    - Explicit requested_format ('brief', 'short', 'explainer', 'cinematic') is strictly honored without override.
    - Hard ceiling: 300s (5 minutes) maximum under any circumstances.
    """
    raw_text = ""
    if text is not None:
        try:
            candidate = str(text)
        except Exception:
            candidate = ""
        if candidate.strip():
            raw_text = candidate
        elif source_path is not None:
            resolved = _resolve_profiling_path(source_path)
            if resolved is not None:
                raw_text = _read_text_source_file(resolved)
    elif source_path is not None:
        resolved = _resolve_profiling_path(source_path)
        if resolved is not None:
            raw_text = _read_text_source_file(resolved)
    elif source is not None:
        if isinstance(source, Path):
            resolved = _resolve_profiling_path(source)
            if resolved is not None:
                raw_text = _read_text_source_file(resolved)
        elif isinstance(source, str):
            # A bare string may be literal text or a path to a text file.
            resolved = _resolve_profiling_path(source)
            if resolved is not None:
                raw_text = _read_text_source_file(resolved)
            else:
                raw_text = source
        else:
            try:
                raw_text = str(source)
            except Exception:
                raw_text = ""

    word_count = _count_words(raw_text)
    char_count = len(raw_text)
    estimated_pages = round(word_count / WORDS_PER_PAGE, 2)
    estimated_reading_minutes = round(word_count / WORDS_PER_READING_MINUTE, 2)

    # Bound analysis to head + truncation note (counts above still reflect full doc)
    analysis_truncated = len(raw_text) > MAX_ANALYSIS_CHARS
    analysis_text = raw_text[:MAX_ANALYSIS_CHARS] if analysis_truncated else raw_text
    analysis_char_count = len(analysis_text)

    # Analyze content value, conceptual density, and redundancy
    context_str = " ".join(str(part) for part in (task, task_type, title, intent, focus, visual_direction) if part)
    content_val = analyze_content_value(analysis_text, context=context_str)

    # Classify task and content type
    classification = classify_document_content(
        analysis_text,
        task=task,
        task_type=task_type,
        title=title,
        intent=intent,
        focus=focus,
        visual_direction=visual_direction,
        mode=mode,
        document_type=document_type,
    )

    # Check if document has high information density / dense single page or summary of large work
    is_dense_doc = (
        (content_val.density_score >= 1.4 and content_val.concept_count >= 4)
        or (content_val.summary_of_large_work and content_val.concept_count >= 3)
        or content_val.high_concept_density
    )
    is_redundant_doc = content_val.redundancy_score >= 0.50

    # Compute target duration and pacing from content value, density, and word count tiers
    if is_dense_doc and word_count < 2500:
        # Dense document (e.g. 1-page election breakdown with key points, book summary):
        # Elevate to comprehensive explainer or cinematic format, scaling to 3–5 minutes
        if classification.is_narrative or content_val.summary_of_large_work:
            calculated_seconds = min(300, max(180, int(round(140 * content_val.density_score))))
            default_format = "cinematic"
            pacing_style = "measured"
        else:
            calculated_seconds = min(240, max(180, int(round(120 * content_val.density_score))))
            default_format = "explainer"
            pacing_style = "measured"
    elif word_count < 150:
        ratio = word_count / 150.0 if word_count > 0 else 0.0
        calculated_seconds = int(round(30 + ratio * (45 - 30)))
        default_format = "short"
        pacing_style = "brisk"
    elif word_count < 500:
        ratio = (word_count - 150) / 350.0
        calculated_seconds = int(round(60 + ratio * (90 - 60)))
        default_format = "brief"
        pacing_style = "brisk"
    elif word_count < 1200:
        ratio = (word_count - 500) / 700.0
        if classification.is_summary:
            calculated_seconds = min(120, int(round(90 + ratio * 30)))
            default_format = "brief"
            pacing_style = "brisk"
        else:
            calculated_seconds = int(round(90 + ratio * (150 - 90)))
            default_format = "explainer"
            pacing_style = "balanced"
    elif word_count < 2500:
        ratio = (word_count - 1200) / 1300.0
        if classification.is_summary and not classification.is_technical and not classification.is_educational:
            calculated_seconds = 120
            default_format = "brief"
            pacing_style = "balanced"
        else:
            calculated_seconds = int(round(150 + ratio * (210 - 150)))
            default_format = "explainer"
            pacing_style = "measured"
    else:
        # 2500+ words (Large Documents):
        # Auto-Adaptive is task/content-aware:
        # Technical documentation, tutorials, SOPs, API guides, reference docs, educational -> explainer
        # Meeting summaries, executive digests -> brief
        # Narrative, historical, storytelling, documentary, case study, or general deep dive -> cinematic
        if classification.is_technical or classification.is_educational:
            ratio = min(1.0, (word_count - 2500) / 2500.0)
            calculated_seconds = min(240, int(round(180 + ratio * (240 - 180))))
            default_format = "explainer"
            pacing_style = "measured"
        elif classification.is_summary:
            ratio = min(1.0, (word_count - 2500) / 2500.0)
            calculated_seconds = min(120, int(round(90 + ratio * (120 - 90))))
            default_format = "brief"
            pacing_style = "balanced"
        elif is_redundant_doc:
            # 10 identical pages of general explanation: compress to concise brief
            eff_w = content_val.effective_word_count
            calculated_seconds = min(120, max(60, int(round(60 + (eff_w / 500.0) * 30))))
            default_format = "brief"
            pacing_style = "balanced"
        else:
            ratio = min(1.0, (word_count - 2500) / 2500.0)
            calculated_seconds = min(300, int(round(240 + ratio * (300 - 240))))
            default_format = "cinematic"
            pacing_style = "measured"

    clean_requested = str(requested_format or "").strip().lower() if requested_format is not None else ""
    is_auto = clean_requested in {"", "auto", "auto-adaptive", "default", "recommended"}

    sections = extract_document_sections(analysis_text)
    sections_capped = len(sections) >= _MAX_SECTIONS_STORED
    num_sections = len(sections)

    # Explicit duration overrides must be numeric; non-numeric values are a
    # caller bug that previously crashed with TypeError/ValueError here.
    override_seconds: int | None = None
    if target_duration_seconds is not None:
        try:
            if isinstance(target_duration_seconds, bool):
                raise ValueError("bool is not a valid duration")
            override_seconds = int(target_duration_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError("target_duration_seconds must be numeric") from exc

    if is_auto:
        format_name = default_format
        if override_seconds is not None:
            final_seconds = override_seconds
        else:
            final_seconds = calculated_seconds
            if num_sections >= 3:
                if format_name == "explainer":
                    final_seconds = min(240, max(final_seconds, num_sections * 15))
                elif format_name == "brief":
                    final_seconds = min(120, max(final_seconds, num_sections * 14))
                elif format_name == "short":
                    final_seconds = min(150, max(final_seconds, num_sections * 12))
                else:
                    final_seconds = min(300, max(final_seconds, num_sections * 18))
    else:
        # Explicit user selection: strictly respected without override.
        # Unknown names normalize to brief tier logic (consistent with
        # compute_format_duration) instead of leaking into the directive.
        format_name = _normalize_format_name(clean_requested)
        if override_seconds is not None:
            final_seconds = override_seconds
        else:
            final_seconds, pacing_style = compute_format_duration(
                word_count,
                format_name,
                num_sections=num_sections,
                density_score=content_val.density_score,
                concept_count=content_val.concept_count,
                content_value=content_val,
            )

    # Enforce strict 5-minute constraint for cinematic format and any format.
    # final_seconds is int-typed on every path above (explicit overrides are
    # validated numeric), so this clamp cannot raise.
    final_seconds = max(MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, int(final_seconds)))

    duration_display = format_duration_display(final_seconds)
    chapter_breakdown = build_chapter_breakdown(
        final_seconds,
        format_name,
        classification.content_type,
        document_text=analysis_text,
        content_value=content_val,
    )
    adaptive_directive = generate_adaptive_directive(
        target_duration_display=duration_display,
        pacing_style=pacing_style,
        format_name=format_name,
        target_duration_seconds=final_seconds,
        chapter_breakdown=chapter_breakdown,
        density_score=content_val.density_score,
        concept_count=content_val.concept_count,
    )

    truncated = bool(analysis_truncated or sections_capped or content_val.truncated)

    return DocumentProfile(
        word_count=word_count,
        char_count=char_count,
        estimated_pages=estimated_pages,
        estimated_reading_minutes=estimated_reading_minutes,
        target_duration_seconds=final_seconds,
        target_duration_display=duration_display,
        recommended_format=format_name,
        pacing_style=pacing_style,
        adaptive_prompt_directive=adaptive_directive,
        chapter_breakdown=chapter_breakdown,
        content_type=classification.content_type,
        detected_intent=classification.detected_intent,
        sections=tuple(sections),
        section_count=num_sections,
        density_score=content_val.density_score,
        content_value_rating=content_val.content_value_rating,
        concept_count=content_val.concept_count,
        effective_word_count=content_val.effective_word_count,
        redundancy_score=content_val.redundancy_score,
        substantive_concepts=content_val.substantive_concepts,
        truncated=truncated,
        analysis_char_count=analysis_char_count,
    )


def build_adaptive_prompt(
    base_prompt: str = "",
    profile: DocumentProfile | None = None,
    requested_format: str | None = None,
) -> str:
    """Build a comprehensive adaptive prompt combining user base prompt and profile directives."""
    try:
        clean_prompt = (base_prompt or "").strip()
    except Exception:
        clean_prompt = ""
    if profile is None:
        return clean_prompt

    req_fmt = str(requested_format or "").strip().lower()
    if req_fmt in {"auto", "auto-adaptive", "default", "recommended", ""}:
        req_fmt = ""
    else:
        # Unknown format names normalize to brief tier logic (consistent with
        # analyze_document_source and compute_format_duration).
        req_fmt = _normalize_format_name(req_fmt)

    try:
        recommended = str(profile.recommended_format or "brief").strip().lower()
    except Exception:
        recommended = "brief"
    format_name = req_fmt or recommended

    # If requested format differs from profile recommendation, generate tailored directive
    if req_fmt and format_name != recommended:
        try:
            words = int(getattr(profile, "word_count", 0))
        except (TypeError, ValueError):
            words = 0
        try:
            num_sections = int(getattr(profile, "section_count", 0))
        except (TypeError, ValueError):
            num_sections = 0
        try:
            density_score = float(getattr(profile, "density_score", 1.0))
        except (TypeError, ValueError):
            density_score = 1.0
        try:
            concept_count = int(getattr(profile, "concept_count", 0))
        except (TypeError, ValueError):
            concept_count = 0
        try:
            effective_wc = int(getattr(profile, "effective_word_count", 0)) or None
        except (TypeError, ValueError):
            effective_wc = None
        try:
            redundancy = float(getattr(profile, "redundancy_score", 0.0))
        except (TypeError, ValueError):
            redundancy = 0.0
        try:
            profile_content_type = str(getattr(profile, "content_type", "general") or "general")
        except Exception:
            profile_content_type = "general"
        final_seconds, pacing_style = compute_format_duration(
            words,
            format_name,
            num_sections=num_sections,
            density_score=density_score,
            concept_count=concept_count,
            effective_word_count=effective_wc,
            redundancy_score=redundancy,
        )
        dur_display = format_duration_display(final_seconds)
        chapter_breakdown = build_chapter_breakdown(final_seconds, format_name, profile_content_type)

        directive = generate_adaptive_directive(
            target_duration_display=dur_display,
            pacing_style=pacing_style,
            format_name=format_name,
            target_duration_seconds=final_seconds,
            chapter_breakdown=chapter_breakdown,
            density_score=density_score,
            concept_count=concept_count,
        )
    else:
        try:
            directive = str(profile.adaptive_prompt_directive or "")
        except Exception:
            directive = ""

    clean_base = clean_prompt
    if not clean_base:
        return directive

    # Strip existing [Adaptive Video Directives] if present
    marker = "[Adaptive Video Directives]"
    if marker in clean_base:
        if directive in clean_base:
            return clean_base
        clean_base = clean_base.split(marker)[0].strip()

    if not clean_base:
        return directive

    return f"{clean_base}\n\n[Adaptive Video Directives]\n{directive}"

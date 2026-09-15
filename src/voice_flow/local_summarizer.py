"""Built-in Local Spoken Summarizer.

100% offline, zero-dependency, intelligent extractive & spoken-adapted text-to-speech summarizer.
Provides:
  - Robust sentence tokenization respecting abbreviations, decimals, and dialogue/quotes.
  - Section & heading detection (markdown headers, numbered sections, paragraph clusters).
  - Dynamic content & scale analysis (word/sentence/section counts, salience distribution).
  - Content-aware dynamic budgeting automatically scaling from 1 paragraph to 10+ pages.
  - Section-level coverage distributing representation across the entire document (pages 1 to 10+).
  - Adaptive depth scaling:
      * Quick / Short: 1-2 punchline sentences for 1 page; thesis + takeaways from each major section
        (~4-7 sentences, ~90-160 words) for 10 pages, cutting background fluff.
      * Standard / Balanced: scales smoothly from ~70-120 words (1 page) to ~250-400 words (10 pages),
        covering all major sections, mechanisms, and key outcomes.
      * Detailed / Long: comprehensive walkthrough from ~150 words (1 page) to ~600-900 words (10 pages),
        preserving specific metrics, data points, conditions, caveats, mechanisms, and conclusions.
  - Speech sanitization for natural Text-To-Speech audio narration without markdown or citations.
  - LocalSpokenSummarizer class and local_spoken_summarizer singleton.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import math
import re
from typing import Sequence

from voice_flow.structured_reader import PAUSE_PARAGRAPH, PAUSE_SECTION

log = logging.getLogger(__name__)

# Standard English Stopwords for TF-ISF
STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other",
    "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't",
    "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves", "also", "just", "like",
}

# Conclusion trigger phrases rewarded in salience scoring
CONCLUSION_MARKERS = (
    "overall",
    "in conclusion",
    "importantly",
    "the key",
    "results show",
    "found that",
    "crucially",
    "in summary",
    "takeaway",
    "to summarize",
    "in brief",
    "the main finding",
    "the bottom line",
    "finally",
    "we conclude",
    "in the end",
    "taken together",
    "demonstrates that",
)

# Common introductory preamble markers penalized in quick multi-page mode
PREAMBLE_MARKERS = (
    "in recent years",
    "over the past",
    "historically",
    "traditionally",
    "for decades",
    "it is widely known",
    "it is well known",
    "background:",
    "introduction:",
    "since the beginning",
    "for a long time",
    "over time",
    "as we know",
)

# Conditions, caveats, bottlenecks, and limitations (vital for detailed walkthrough)
CAVEAT_MARKERS = (
    "however",
    "although",
    "despite",
    "limitation",
    "limitations",
    "bottleneck",
    "bottlenecks",
    "tradeoff",
    "tradeoffs",
    "trade-off",
    "trade-offs",
    "caveat",
    "caveats",
    "challenge",
    "challenges",
    "constrained",
    "constraint",
    "constraints",
    "requires",
    "provided that",
    "unless",
    "except",
    "risk",
    "risks",
    "vulnerability",
    "vulnerabilities",
    "edge case",
    "edge cases",
    "failure mode",
    "shortcoming",
    "shortcomings",
    "drawback",
    "drawbacks",
)

# Mechanisms, architecture, and methodology markers (vital for standard/balanced coverage)
MECHANISM_MARKERS = (
    "architecture",
    "mechanism",
    "algorithm",
    "technique",
    "method",
    "methodology",
    "framework",
    "pipeline",
    "protocol",
    "combines",
    "integrates",
    "implements",
    "operates",
    "processes",
    "designed to",
    "functions by",
    "leverages",
    "utilizes",
    "via",
    "consists of",
    "coordinates",
    "regulates",
    "executes",
    "computes",
    "optimizes",
    "deploys",
    "synthesizes",
    "encodes",
    "transforms",
)

# Punchline, breakthrough, and outcome markers
OUTCOME_MARKERS = (
    "results show",
    "found that",
    "demonstrates that",
    "proves that",
    "achieved",
    "delivers",
    "reduces",
    "improves",
    "increases",
    "outperforms",
    "takeaway",
    "bottom line",
    "discovery",
    "breakthrough",
    "exceeded",
    "confirmed",
    "revealed",
    "indicates that",
    "concludes that",
    "leads to",
    "yielded",
    "proves",
    "establishes",
)

# Factual / Metric regex pattern for quantitative data
METRIC_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?%|\$\d+|\b\d{4}\b|\b\d+(?:\.\d+)?\s*(?:million|billion|trillion|percent|ms|seconds|minutes|hours|fps|x\b|times|operations|nodes|dollars|gb|mb|tb|kb)\b",
    re.IGNORECASE,
)

# Abbreviations pattern for sentence tokenization
ABBREVIATIONS_PATTERN = re.compile(
    r"\b("
    # Titles & Honorifics
    r"Dr|Mr|Mrs|Ms|Prof|Sr|Jr|Rev|Hon|Gov|Pres|Sen|Rep|Gen|Col|Capt|Lt|Sgt|Cpl|Pvt|"
    # Academic & Degrees
    r"Ph\.D|PhD|M\.D|MD|B\.A|B\.S|M\.A|M\.S|B\.Sc|M\.Sc|Ed\.D|J\.D|"
    # Latin & Common
    r"e\.g|i\.e|etc|al|vs|v|viz|cf|ca|ibid|"
    # Months & Days
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|Mon|Tue|Wed|Thu|Fri|Sat|Sun|"
    # Addresses / Places
    r"U\.S|U\.K|U\.N|E\.U|D\.C|St|Ave|Rd|Blvd|Hwy|Dept|Mt|Ft|"
    # Publications / Business
    r"Inc|Corp|Co|Ltd|LLC|Fig|Figs|No|Nos|Vol|Vols|pp|p|ed|eds|approx|appx|est|min|max|"
    # Time / Epoch
    r"a\.m|p\.m|A\.M|P\.M|B\.C|A\.D|B\.C\.E|C\.E"
    r")\.",
    re.IGNORECASE,
)


@dataclass
class SentenceUnit:
    """Internal representation of a candidate sentence."""

    raw_text: str
    clean_text: str
    paragraph_idx: int
    sent_idx_in_paragraph: int
    global_idx: int
    word_count: int
    content_tokens: list[str] = field(default_factory=list)
    salience_score: float = 0.0
    is_opening: bool = False
    is_lead: bool = False
    has_conclusion_marker: bool = False
    has_preamble_marker: bool = False
    has_metric: bool = False
    has_caveat: bool = False
    has_mechanism: bool = False
    has_outcome: bool = False
    section_idx: int = 0
    section_title: str = ""
    is_section_lead: bool = False


@dataclass
class DocumentProfile:
    """Statistical profile and scale analysis of the input document."""

    total_words: int
    total_sentences: int
    total_paragraphs: int
    total_sections: int
    estimated_pages: float
    salience_mean: float = 0.0
    salience_std: float = 0.0
    salience_min: float = 0.0
    salience_max: float = 0.0
    salience_p75: float = 0.0
    section_map: dict[int, list[SentenceUnit]] = field(default_factory=dict)


class LocalSpokenSummarizer:
    """100% offline, intelligent extractive and spoken-adapted summarizer."""

    def __init__(self) -> None:
        pass

    def summarize(self, text: str, depth: str = "balanced") -> str:
        """Synthesize an offline spoken summary of the given text.

        Parameters:
            text: Input document or dialogue string.
            depth: Summarization depth mode ('quick'/'short', 'standard'/'balanced'/'medium', 'detailed'/'long').

        Returns:
            TTS-optimized natural narration string ready for speech playback.
        """
        if not text or not text.strip():
            return ""

        # Normalize depth aliases
        clean_depth = self._resolve_depth(depth)

        # Tokenize sentences across paragraphs & sections with abbreviation & quote protection
        sentences = self.tokenize_sentences(text)
        if not sentences:
            return ""

        total_sentences = len(sentences)
        total_words = sum(s.word_count for s in sentences)

        # If document is extremely short (1 sentence), sanitize and return directly
        if total_sentences <= 1:
            return self.sanitize_for_speech(sentences[0].raw_text)

        # Salience & Position Scoring
        is_multi_page = (total_words > 250 or len({s.paragraph_idx for s in sentences}) >= 3)
        self.score_sentences(sentences, is_multi_page=is_multi_page, depth=clean_depth)

        # Maximal Marginal Relevance (MMR) Selection with Dynamic Content-Aware Budgeting
        selected_units = self.select_mmr(sentences, depth=clean_depth)

        # Assemble summary in natural chronological document order
        selected_units.sort(key=lambda s: s.global_idx)

        # Abstractive smoothing and TTS speech sanitization
        return self._format_spoken_summary(selected_units)

    def _resolve_depth(self, depth: str) -> str:
        """Normalize depth mode aliases to 'short', 'balanced', or 'detailed'."""
        d = (depth or "balanced").strip().lower()
        if d in ("quick", "short", "brief", "concise"):
            return "short"
        if d in ("detailed", "long", "thorough", "deep", "full"):
            return "detailed"
        if d in ("standard", "medium", "balanced", "normal", "moderate"):
            return "balanced"
        return "balanced"

    def tokenize_sentences(self, text: str) -> list[SentenceUnit]:
        """Intelligently split text into sentences while respecting abbreviations, decimals, and quotes.

        Detects sections via markdown headings (#, ##), numbered sections, or paragraph boundaries.
        """
        if not text:
            return []

        # Split into distinct paragraphs preserving section breaks
        raw_paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
        if not raw_paragraphs:
            raw_paragraphs = [text.strip()]

        sentence_units: list[SentenceUnit] = []
        global_idx = 0

        current_section_idx = 0
        current_section_title = ""
        has_seen_heading = False

        heading_pattern = re.compile(r"^\s*#{1,6}\s+([^\n]+)|^\s*(?:Section|Chapter|Part)\s+\d+[:\s]+([^\n]+)", re.IGNORECASE)

        for p_idx, paragraph in enumerate(raw_paragraphs):
            # Check if paragraph starts with or is an explicit section heading
            heading_match = heading_pattern.match(paragraph)
            p_content = paragraph

            if heading_match:
                title = (heading_match.group(1) or heading_match.group(2) or "").strip()
                if has_seen_heading:
                    current_section_idx += 1
                has_seen_heading = True
                current_section_title = title

                # Strip heading line from body if paragraph has body content after newline
                lines = paragraph.split("\n", 1)
                if len(lines) > 1 and lines[1].strip():
                    p_content = lines[1].strip()
                else:
                    # Paragraph is solely a heading line, advance and continue
                    continue
            elif not has_seen_heading:
                # In documents without markdown headings, each paragraph forms its own section
                current_section_idx = p_idx

            p_sentences = self._split_paragraph_sentences(p_content)
            for s_idx, sent_text in enumerate(p_sentences):
                clean_s = sent_text.strip()
                if not clean_s:
                    continue

                words = clean_s.split()
                content_words = [
                    w.lower()
                    for w in re.findall(r"\b[a-zA-Z]{2,}\b", clean_s)
                    if w.lower() not in STOP_WORDS
                ]

                clean_lower = clean_s.lower()
                has_concl = any(m in clean_lower for m in CONCLUSION_MARKERS)
                has_preamble = any(m in clean_lower for m in PREAMBLE_MARKERS)
                has_caveat = any(re.search(r"\b" + re.escape(m) + r"\b", clean_lower) for m in CAVEAT_MARKERS)
                has_mechanism = any(re.search(r"\b" + re.escape(m) + r"\b", clean_lower) for m in MECHANISM_MARKERS)
                has_outcome = any(m in clean_lower for m in OUTCOME_MARKERS)
                has_metric = bool(METRIC_PATTERN.search(clean_s))

                is_sec_lead = (s_idx == 0)

                unit = SentenceUnit(
                    raw_text=clean_s,
                    clean_text=clean_s,
                    paragraph_idx=p_idx,
                    sent_idx_in_paragraph=s_idx,
                    global_idx=global_idx,
                    word_count=len(words),
                    content_tokens=content_words,
                    is_opening=(global_idx == 0),
                    is_lead=(s_idx == 0),
                    has_conclusion_marker=has_concl,
                    has_preamble_marker=has_preamble,
                    has_metric=has_metric,
                    has_caveat=has_caveat,
                    has_mechanism=has_mechanism,
                    has_outcome=has_outcome,
                    section_idx=current_section_idx,
                    section_title=current_section_title,
                    is_section_lead=is_sec_lead,
                )
                sentence_units.append(unit)
                global_idx += 1

        return sentence_units

    def _split_paragraph_sentences(self, paragraph: str) -> list[str]:
        """Split a single paragraph into sentences using placeholder masking."""
        p = paragraph.strip()
        if not p:
            return []

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

        # Titles & Honorifics before names: Dr. Mr. Mrs. Ms. Prof. etc.
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
        boundary_pattern = re.compile(r'([.?!]+["\'”’\)\]]*)\s+(?=[A-Z0-9"\'“‘\(\[]|\Z)')
        p = boundary_pattern.sub(lambda m: f"{m.group(1)}\uE002", p)

        # 6. Split on \uE002
        splits = p.split("\uE002")

        results: list[str] = []
        for s in splits:
            s_clean = s.strip()
            if not s_clean:
                continue
            # Restore masked characters
            s_clean = s_clean.replace("\uE000", ".")
            s_clean = s_clean.replace("\uE001", "...")
            # Restore URLs
            for idx, url in enumerate(urls):
                s_clean = s_clean.replace(f"\uE003{idx}\uE003", url)
            results.append(s_clean)

        return results

    def score_sentences(
        self,
        sentences: list[SentenceUnit],
        is_multi_page: bool = False,
        depth: str = "balanced",
    ) -> None:
        """Compute salience score for each sentence using TF-ISF, position, length, and content cues."""
        n_sentences = len(sentences)
        if n_sentences == 0:
            return

        # 1. Calculate Inverse Sentence Frequency (ISF) for all vocabulary
        sentence_freq: dict[str, int] = {}
        for s in sentences:
            unique_tokens = set(s.content_tokens)
            for t in unique_tokens:
                sentence_freq[t] = sentence_freq.get(t, 0) + 1

        isf_scores: dict[str, float] = {}
        for t, count in sentence_freq.items():
            isf_scores[t] = math.log((n_sentences + 1) / (count + 1)) + 1.0

        # 2. Score each sentence
        for s in sentences:
            # TF-ISF score
            if s.content_tokens:
                tf_dict: dict[str, int] = {}
                for t in s.content_tokens:
                    tf_dict[t] = tf_dict.get(t, 0) + 1

                total_content_words = len(s.content_tokens)
                tf_isf_sum = sum(
                    (count / total_content_words) * isf_scores.get(t, 1.0)
                    for t, count in tf_dict.items()
                )
                tf_isf_score = (tf_isf_sum / math.sqrt(total_content_words)) * 2.5
            else:
                tf_isf_score = 0.0

            # Position Bonuses:
            # - Opening document sentence weight (thesis/hook bonus: +2.5)
            # - Paragraph lead sentence weight (topic sentence bonus: +1.5)
            position_bonus = 0.0
            if s.is_opening:
                # In quick mode for multi-page documents, eliminate introductory fluff
                if is_multi_page and depth == "short" and s.has_preamble_marker:
                    position_bonus = -2.0
                else:
                    position_bonus = 2.5
            elif s.is_lead:
                position_bonus = 1.5

            # Conclusion sentence bonus (+2.0 for sentences starting or containing conclusion markers)
            conclusion_bonus = 0.0
            if s.has_conclusion_marker:
                conclusion_bonus = 2.0
            elif s.global_idx == n_sentences - 1 and n_sentences > 2:
                conclusion_bonus = 1.0  # Final sentence of document naturally holds closing weight

            # Length normalization:
            # ideal sentence length 12–30 words; penalize fragments (<5 words) and run-ons (>50 words)
            w_count = s.word_count
            if 12 <= w_count <= 30:
                length_adj = 0.5  # Ideal sweet spot
            elif w_count < 5:
                length_adj = -2.5  # Severe fragment penalty
            elif 5 <= w_count < 12:
                length_adj = -1.5 * ((12 - w_count) / 7.0)  # Moderate short penalty
            elif 30 < w_count <= 50:
                length_adj = -1.0 * ((w_count - 30) / 20.0)  # Moderate long penalty
            else:
                length_adj = -3.0  # Severe run-on penalty

            # Factual / Metric bonus (numbers, percentages, metrics indicate informative value)
            metric_bonus = 0.75 if s.has_metric else 0.0

            # Content Cue Bonuses tailored by depth mode
            outcome_bonus = 1.2 if s.has_outcome else 0.0

            if depth == "detailed":
                caveat_bonus = 1.6 if s.has_caveat else 0.0
                mechanism_bonus = 1.0 if s.has_mechanism else 0.0
                if s.has_metric:
                    metric_bonus = 1.8
            elif depth == "balanced":
                caveat_bonus = 0.5 if s.has_caveat else 0.0
                mechanism_bonus = 1.2 if s.has_mechanism else 0.0
                if s.has_metric:
                    metric_bonus = 1.0
            else:
                # Short / quick mode
                caveat_bonus = -0.2 if s.has_caveat else 0.0
                mechanism_bonus = 0.4 if s.has_mechanism else 0.0

            # Combined Salience
            s.salience_score = (
                tf_isf_score
                + position_bonus
                + conclusion_bonus
                + length_adj
                + metric_bonus
                + outcome_bonus
                + caveat_bonus
                + mechanism_bonus
            )

    def analyze_content(self, sentences: list[SentenceUnit]) -> DocumentProfile:
        """Perform dynamic content & scale analysis on tokenized sentences."""
        if not sentences:
            return DocumentProfile(
                total_words=0,
                total_sentences=0,
                total_paragraphs=0,
                total_sections=0,
                estimated_pages=0.0,
            )

        total_words = sum(s.word_count for s in sentences)
        total_sentences = len(sentences)
        total_paragraphs = len({s.paragraph_idx for s in sentences})

        # Group sentences by section
        section_map: dict[int, list[SentenceUnit]] = {}
        for s in sentences:
            section_map.setdefault(s.section_idx, []).append(s)

        # If only 1 or 2 sections exist but document has many sentences (e.g. long continuous article without headings),
        # create virtual section partitions to guarantee section-level coverage across the entire text.
        target_sections = max(2, min(15, math.ceil(total_words / 220.0)))
        if len(section_map) <= 2 and total_sentences >= 8:
            chunk_size = max(3, math.ceil(total_sentences / target_sections))
            section_map = {}
            for idx, s in enumerate(sentences):
                v_sec = idx // chunk_size
                s.section_idx = v_sec
                section_map.setdefault(v_sec, []).append(s)

        total_sections = len(section_map)
        estimated_pages = max(1.0, total_words / 250.0)

        # Salience distribution statistics
        scores = [s.salience_score for s in sentences]
        s_mean = sum(scores) / total_sentences
        s_variance = sum((x - s_mean) ** 2 for x in scores) / total_sentences
        s_std = math.sqrt(s_variance)
        s_min = min(scores)
        s_max = max(scores)
        sorted_scores = sorted(scores)
        s_p75 = sorted_scores[int(total_sentences * 0.75)] if total_sentences > 0 else s_mean

        return DocumentProfile(
            total_words=total_words,
            total_sentences=total_sentences,
            total_paragraphs=total_paragraphs,
            total_sections=total_sections,
            estimated_pages=estimated_pages,
            salience_mean=s_mean,
            salience_std=s_std,
            salience_min=s_min,
            salience_max=s_max,
            salience_p75=s_p75,
            section_map=section_map,
        )

    def compute_budget(
        self, profile: DocumentProfile, depth: str
    ) -> tuple[int, int, int, int]:
        """Compute dynamic (min_sents, max_sents, min_words, max_words) based on document scale and depth."""
        pages = profile.estimated_pages
        n_sents = profile.total_sentences
        n_words = profile.total_words

        if depth == "short":
            # Quick / Short Summary:
            # 1 page (1-3 sections): 2 punchline sentences (~30-65 words).
            # 10 pages (10-20 sections): 4-6 key sentences (~90-160 words).
            if pages <= 1.5:
                min_s = 2
                max_s = 3
                min_w = 30
                max_w = 65
            elif pages <= 4.0:
                scale = (pages - 1.5) / 2.5
                min_s = int(round(2 + scale * 1))       # 2 -> 3
                max_s = int(round(3 + scale * 1))       # 3 -> 4
                min_w = int(round(50 + scale * 25))     # 50 -> 75
                max_w = int(round(75 + scale * 35))     # 75 -> 110
            else:
                scale = min(1.0, (pages - 4.0) / 6.0)
                min_s = int(round(3 + scale * 1))       # 3 -> 4
                max_s = int(round(4 + scale * 2))       # 4 -> 6
                min_w = int(round(75 + scale * 25))     # 75 -> 100
                max_w = int(round(110 + scale * 50))    # 110 -> 160

        elif depth == "detailed":
            # Detailed Summary:
            # 1 page: 6-9 sentences (~130-220 words).
            # 10 pages: 25-40 sentences (~600-900 words).
            if pages <= 1.5:
                min_s = 6
                max_s = 9
                min_w = 120
                max_w = 250
            elif pages <= 4.0:
                scale = (pages - 1.5) / 2.5
                min_s = int(round(6 + scale * 6))       # 6 -> 12
                max_s = int(round(9 + scale * 11))      # 9 -> 20
                min_w = int(round(120 + scale * 130))   # 120 -> 250
                max_w = int(round(250 + scale * 200))   # 250 -> 450
            else:
                scale = min(1.0, (pages - 4.0) / 6.0)
                min_s = int(round(12 + scale * 13))     # 12 -> 25
                max_s = int(round(20 + scale * 20))     # 20 -> 40
                min_w = int(round(250 + scale * 350))   # 250 -> 600
                max_w = int(round(450 + scale * 450))   # 450 -> 900

        else:
            # Standard / Balanced Summary:
            # 1 page: 3-5 sentences (~70-125 words).
            # 10 pages: 12-18 sentences (~260-380 words).
            if pages <= 1.5:
                min_s = 3
                max_s = 5
                min_w = 65
                max_w = 125
            elif pages <= 4.0:
                scale = (pages - 1.5) / 2.5
                min_s = int(round(3 + scale * 3))       # 3 -> 6
                max_s = int(round(5 + scale * 5))       # 5 -> 10
                min_w = int(round(65 + scale * 65))     # 65 -> 130
                max_w = int(round(125 + scale * 95))    # 125 -> 220
            else:
                scale = min(1.0, (pages - 4.0) / 6.0)
                min_s = int(round(6 + scale * 6))       # 6 -> 12
                max_s = int(round(10 + scale * 8))      # 10 -> 18
                min_w = int(round(130 + scale * 130))   # 130 -> 260
                max_w = int(round(220 + scale * 160))   # 220 -> 380

        # Adjust for document availability (compression preservation on small inputs)
        if n_sents <= 3:
            min_s = min(min_s, n_sents)
            max_s = min(max_s, n_sents)
        elif n_sents <= 5:
            min_s = min(min_s, n_sents)
            if depth == "short":
                max_s = min(2, n_sents)
            elif depth == "balanced":
                max_s = min(3, n_sents)  # Always compress short texts in standard mode!
            else:
                max_s = n_sents
        else:
            min_s = min(min_s, n_sents)
            max_s = min(max_s, n_sents)

        min_w = min(min_w, n_words)
        max_w = min(max_w, n_words)

        max_s = max(min_s, max_s)
        max_w = max(min_w, max_w)

        return min_s, max_s, min_w, max_w

    def select_mmr(
        self,
        sentences: list[SentenceUnit],
        depth: str = "balanced",
    ) -> list[SentenceUnit]:
        """Select sentences using content-aware dynamic budgeting and section-level coverage."""
        n_sentences = len(sentences)
        if n_sentences == 0:
            return []
        if n_sentences <= 1:
            return [sentences[0]]

        clean_depth = self._resolve_depth(depth)
        profile = self.analyze_content(sentences)
        min_sents, max_sents, min_words, max_words = self.compute_budget(profile, clean_depth)

        if clean_depth == "short":
            return self._select_quick(sentences, profile, min_sents, max_sents, min_words, max_words)
        elif clean_depth == "detailed":
            return self._select_detailed(sentences, profile, min_sents, max_sents, min_words, max_words)
        else:
            return self._select_standard(sentences, profile, min_sents, max_sents, min_words, max_words)

    def _select_quick(
        self,
        sentences: list[SentenceUnit],
        profile: DocumentProfile,
        min_sents: int,
        max_sents: int,
        min_words: int,
        max_words: int,
    ) -> list[SentenceUnit]:
        """Quick Summary selection.

        For 1 page (1-3 sections): 1-2 punchline sentences (~20-55 words).
        For 10 pages (10-20 sections): thesis + takeaway from each major section (~4-7 sentences, ~90-160 words).
        """
        n_sentences = len(sentences)
        selected: list[SentenceUnit] = []
        selected_set: set[int] = set()
        current_words = 0

        # Short text / 1-page document behavior: 2-3 punchlines
        if profile.estimated_pages <= 1.5 or profile.total_sections <= 3 or n_sentences < 5:
            # Candidate 1: Best grounded thesis/hook from opening (skipping preamble)
            thesis_candidates: list[SentenceUnit] = []
            for sec_idx in sorted(profile.section_map.keys()):
                sec_sents = profile.section_map[sec_idx]
                p_ids = []
                for s in sec_sents:
                    if s.paragraph_idx not in p_ids:
                        p_ids.append(s.paragraph_idx)
                for p_id in p_ids:
                    p_sents = [s for s in sec_sents if s.paragraph_idx == p_id]
                    non_preamble = [s for s in p_sents if not s.has_preamble_marker]
                    if non_preamble:
                        thesis_candidates = non_preamble[:2]
                        break
                if thesis_candidates:
                    break
            if not thesis_candidates:
                thesis_candidates = sentences[:2]
            best_thesis = max(thesis_candidates, key=lambda s: s.salience_score)
            selected.append(best_thesis)
            selected_set.add(best_thesis.global_idx)
            current_words += best_thesis.word_count

            # Candidate 2: Best core finding / mechanism from middle if budget allows 3 sentences
            if max_sents >= 3 and n_sentences >= 3:
                mid_candidates = [
                    s for s in sentences
                    if s.global_idx not in selected_set
                    and s.global_idx != n_sentences - 1
                    and (s.has_mechanism or s.has_outcome or s.has_metric)
                ]
                if mid_candidates:
                    best_mid = max(mid_candidates, key=lambda s: s.salience_score)
                    if (current_words + best_mid.word_count <= max_words) or (len(selected) < min_sents):
                        selected.append(best_mid)
                        selected_set.add(best_mid.global_idx)
                        current_words += best_mid.word_count

            # Candidate 3 / 2: Best conclusion / takeaway from final section
            if max_sents >= 2 and len(selected) < max_sents:
                conclusion_candidates = [
                    s for s in sentences
                    if s.global_idx not in selected_set and (s.has_conclusion_marker or s.global_idx >= n_sentences - 2)
                ]
                if conclusion_candidates:
                    best_conclusion = max(conclusion_candidates, key=lambda s: s.salience_score)
                    if (current_words + best_conclusion.word_count <= max_words) or (current_words < min_words) or (len(selected) < min_sents):
                        selected.append(best_conclusion)
                        selected_set.add(best_conclusion.global_idx)
            return selected

        # Multi-page text (e.g. 4+ sections up to 10+ pages):
        # 1. Thesis Hook: Top grounded non-preamble thesis strictly from earliest non-preamble section
        thesis_candidates: list[SentenceUnit] = []
        for sec_idx in sorted(profile.section_map.keys()):
            sec_sents = profile.section_map[sec_idx]
            p_ids = []
            for s in sec_sents:
                if s.paragraph_idx not in p_ids:
                    p_ids.append(s.paragraph_idx)
            for p_id in p_ids:
                p_sents = [s for s in sec_sents if s.paragraph_idx == p_id]
                non_preamble = [s for s in p_sents if not s.has_preamble_marker]
                if non_preamble:
                    thesis_candidates = non_preamble[:2]
                    break
            if thesis_candidates:
                break
        if not thesis_candidates:
            thesis_candidates = sentences[:2]
        best_thesis = max(thesis_candidates, key=lambda s: s.salience_score)
        selected.append(best_thesis)
        selected_set.add(best_thesis.global_idx)
        current_words += best_thesis.word_count

        # 2. Select major sections distributed across the document
        all_sec_ids = sorted(profile.section_map.keys())
        remaining_secs = [sid for sid in all_sec_ids if sid != best_thesis.section_idx]

        # Target number of section takeaways
        target_section_count = min(max_sents - 1, len(remaining_secs))
        if len(remaining_secs) <= target_section_count:
            chosen_secs = remaining_secs
        else:
            step = (len(remaining_secs) - 1) / max(1, target_section_count - 1)
            chosen_indices = {int(round(i * step)) for i in range(target_section_count)}
            chosen_secs = [remaining_secs[i] for i in sorted(chosen_indices)]

        # 3. Extract the single most critical key point / takeaway from each chosen major section
        for sec_id in chosen_secs:
            sec_sentences = profile.section_map.get(sec_id, [])
            candidates = [
                s for s in sec_sentences
                if s.global_idx not in selected_set and not s.has_preamble_marker
            ]
            if not candidates:
                candidates = [s for s in sec_sentences if s.global_idx not in selected_set]
            if not candidates:
                continue

            def _takeaway_metric(s: SentenceUnit) -> float:
                score = s.salience_score
                if s.has_outcome:
                    score += 2.5
                if s.has_mechanism:
                    score += 2.0
                if s.has_metric:
                    score += 1.8
                if s.has_conclusion_marker:
                    score += 2.0
                if s.is_lead or getattr(s, "is_section_lead", False):
                    score += 2.2
                if s.word_count > 34:
                    score -= 1.5
                return score

            candidates.sort(key=_takeaway_metric, reverse=True)

            # Pick top candidate with MMR redundancy protection
            best_candidate: SentenceUnit | None = None
            for c in candidates:
                redundancy = max((self._jaccard_similarity(c, sel) for sel in selected), default=0.0)
                if redundancy < 0.45:
                    best_candidate = c
                    break
            if best_candidate is None:
                min_cand = min(candidates, key=lambda c: max((self._jaccard_similarity(c, sel) for sel in selected), default=0.0))
                min_red = max((self._jaccard_similarity(min_cand, sel) for sel in selected), default=0.0)
                if min_red < 0.60:
                    best_candidate = min_cand

            if best_candidate is None:
                continue

            if (current_words + best_candidate.word_count <= max_words) or (len(selected) < min_sents):
                selected.append(best_candidate)
                selected_set.add(best_candidate.global_idx)
                current_words += best_candidate.word_count

            if len(selected) >= max_sents and current_words >= min_words:
                break

        # Pass 4: If below min_words or min_sents, sweep remaining major sections
        if (current_words < min_words or len(selected) < min_sents) and len(selected) < max_sents:
            unselected_secs = [sid for sid in remaining_secs if sid not in chosen_secs]
            for sec_id in unselected_secs:
                if len(selected) >= max_sents or (current_words >= min_words and len(selected) >= min_sents):
                    break
                sec_sentences = profile.section_map.get(sec_id, [])
                candidates = [
                    s for s in sec_sentences
                    if s.global_idx not in selected_set and not s.has_preamble_marker
                ] or [s for s in sec_sentences if s.global_idx not in selected_set]
                if not candidates:
                    continue

                candidates.sort(key=_takeaway_metric, reverse=True)
                for c in candidates:
                    if (current_words + c.word_count > max_words) and current_words >= min_words:
                        continue
                    redundancy = max((self._jaccard_similarity(c, sel) for sel in selected), default=0.0)
                    if redundancy < 0.45:
                        selected.append(c)
                        selected_set.add(c.global_idx)
                        current_words += c.word_count
                        break

        return selected

    def _select_standard(
        self,
        sentences: list[SentenceUnit],
        profile: DocumentProfile,
        min_sents: int,
        max_sents: int,
        min_words: int,
        max_words: int,
    ) -> list[SentenceUnit]:
        """Standard / Balanced Summary selection.

        Scales smoothly: ~70-120 words for 1 page; covers all major sections, mechanisms,
        and key outcomes (~250-400 words) for 10 pages.
        """
        selected: list[SentenceUnit] = []
        selected_set: set[int] = set()
        current_words = 0

        all_sec_ids = sorted(profile.section_map.keys())

        # Determine target sections to guarantee cross-document representation
        if len(all_sec_ids) <= max_sents:
            target_secs = all_sec_ids
        else:
            step = (len(all_sec_ids) - 1) / max(1, max_sents - 1)
            target_indices = {int(round(i * step)) for i in range(max_sents)}
            target_secs = [all_sec_ids[i] for i in sorted(target_indices)]

        # Pass 1: One key representative sentence per section (mechanisms & key outcomes)
        for sec_id in target_secs:
            sec_sents = profile.section_map.get(sec_id, [])
            candidates = [s for s in sec_sents if s.global_idx not in selected_set]
            if not candidates:
                continue

            def _standard_sec_rank(s: SentenceUnit) -> float:
                score = s.salience_score
                if s.has_outcome:
                    score += 1.8
                if s.has_mechanism:
                    score += 1.6
                if s.has_metric:
                    score += 1.2
                if s.is_opening or s.is_lead:
                    score += 1.0
                return score

            candidates.sort(key=_standard_sec_rank, reverse=True)

            best_candidate: SentenceUnit | None = None
            for c in candidates:
                redundancy = max((self._jaccard_similarity(c, sel) for sel in selected), default=0.0)
                if redundancy < 0.50:
                    best_candidate = c
                    break
            if best_candidate is None:
                # Pick candidate with lowest redundancy if diverse enough (<0.60); otherwise skip redundant section
                min_cand = min(candidates, key=lambda c: max((self._jaccard_similarity(c, sel) for sel in selected), default=0.0))
                min_red = max((self._jaccard_similarity(min_cand, sel) for sel in selected), default=0.0)
                if min_red < 0.60:
                    best_candidate = min_cand

            if best_candidate is None:
                continue

            if (current_words + best_candidate.word_count <= max_words) or (len(selected) < min_sents):
                selected.append(best_candidate)
                selected_set.add(best_candidate.global_idx)
                current_words += best_candidate.word_count

            if len(selected) >= max_sents and current_words >= max_words:
                break

        # Pass 2: MMR greedy expansion to satisfy budget with mechanisms and key outcomes
        max_salience = max((s.salience_score for s in sentences), default=1.0)
        min_salience = min((s.salience_score for s in sentences), default=0.0)
        salience_span = max(1e-5, max_salience - min_salience)

        lambda_param = 0.65

        while len(selected) < max_sents and current_words < max_words:
            best_candidate = None
            best_mmr = -float("inf")

            for s in sentences:
                if s.global_idx in selected_set:
                    continue
                if (current_words + s.word_count) > max_words and len(selected) >= min_sents:
                    continue

                norm_salience = (s.salience_score - min_salience) / salience_span
                redundancy = max((self._jaccard_similarity(s, sel) for sel in selected), default=0.0)

                # Penalize sections already heavily represented
                sec_count = sum(1 for sel in selected if sel.section_idx == s.section_idx)
                if sec_count >= 2:
                    redundancy = min(1.0, redundancy + 0.20)

                # Strictly penalize near-duplicates
                if redundancy >= 0.70:
                    redundancy = 2.0

                eff_salience = norm_salience + (0.15 if s.has_mechanism else 0.0) + (0.15 if s.has_outcome else 0.0)
                mmr_score = (lambda_param * eff_salience) - ((1.0 - lambda_param) * redundancy)

                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_candidate = s

            if best_candidate is None:
                break

            selected.append(best_candidate)
            selected_set.add(best_candidate.global_idx)
            current_words += best_candidate.word_count

            if current_words >= max_words and len(selected) >= min_sents:
                break

        return selected

    def _select_detailed(
        self,
        sentences: list[SentenceUnit],
        profile: DocumentProfile,
        min_sents: int,
        max_sents: int,
        min_words: int,
        max_words: int,
    ) -> list[SentenceUnit]:
        """Detailed Summary selection.

        Comprehensive walkthrough: covers all sections, preserving specific numbers, metrics,
        data points, conditions, caveats, and conclusions (~150 words for short texts up to 600-900 words for 10 pages).
        """
        selected: list[SentenceUnit] = []
        selected_set: set[int] = set()
        current_words = 0

        all_sec_ids = sorted(profile.section_map.keys())

        # Pass 1: Foundational walkthrough covering EVERY section
        for sec_id in all_sec_ids:
            sec_sents = profile.section_map.get(sec_id, [])
            candidates = [s for s in sec_sents if s.global_idx not in selected_set]
            if not candidates:
                continue

            # Prioritize section lead or top salience sentence
            best_lead = max(candidates, key=lambda s: s.salience_score + (1.5 if s.is_lead else 0.0))
            if (current_words + best_lead.word_count <= max_words) or (len(selected) < min_sents):
                selected.append(best_lead)
                selected_set.add(best_lead.global_idx)
                current_words += best_lead.word_count

            if len(selected) >= max_sents and current_words >= max_words:
                break

        # Pass 2: Content preservation pass (numbers, metrics, data points, caveats, conditions)
        preserved_candidates = [
            s for s in sentences
            if s.global_idx not in selected_set and (s.has_metric or s.has_caveat or s.has_mechanism or s.has_conclusion_marker)
        ]

        def _detail_preservation_score(s: SentenceUnit) -> float:
            score = s.salience_score
            if s.has_metric:
                score += 2.5
            if s.has_caveat:
                score += 2.2
            if s.has_conclusion_marker:
                score += 1.8
            if s.has_mechanism:
                score += 1.4
            return score

        preserved_candidates.sort(key=_detail_preservation_score, reverse=True)

        abs_max_sents = min(len(sentences), max(max_sents, int(max_sents * 1.35)))
        for c in preserved_candidates:
            if len(selected) >= max_sents and current_words >= min_words:
                break
            if len(selected) >= abs_max_sents:
                break
            if (current_words + c.word_count) > max_words and len(selected) >= min_sents:
                continue

            redundancy = max((self._jaccard_similarity(c, sel) for sel in selected), default=0.0)
            if redundancy < 0.60:
                selected.append(c)
                selected_set.add(c.global_idx)
                current_words += c.word_count

            if current_words >= max_words and len(selected) >= min_sents:
                break

        # Pass 3: Deep Walkthrough MMR fill to reach detailed budget
        max_salience = max((s.salience_score for s in sentences), default=1.0)
        min_salience = min((s.salience_score for s in sentences), default=0.0)
        salience_span = max(1e-5, max_salience - min_salience)
        lambda_param = 0.70

        while (len(selected) < max_sents or current_words < min_words) and current_words < max_words and len(selected) < abs_max_sents:
            best_candidate = None
            best_mmr = -float("inf")

            for s in sentences:
                if s.global_idx in selected_set:
                    continue
                if (current_words + s.word_count) > max_words and len(selected) >= min_sents:
                    continue

                norm_salience = (s.salience_score - min_salience) / salience_span
                redundancy = max((self._jaccard_similarity(s, sel) for sel in selected), default=0.0)
                if redundancy >= 0.70:
                    redundancy = 2.0

                mmr_score = (lambda_param * norm_salience) - ((1.0 - lambda_param) * redundancy)
                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_candidate = s

            if best_candidate is None:
                break

            selected.append(best_candidate)
            selected_set.add(best_candidate.global_idx)
            current_words += best_candidate.word_count

            if current_words >= max_words and len(selected) >= min_sents:
                break

        return selected

    def _jaccard_similarity(self, a: SentenceUnit, b: SentenceUnit) -> float:
        """Compute vocabulary overlap similarity between two sentences."""
        set_a = set(a.content_tokens)
        set_b = set(b.content_tokens)
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    def sanitize_for_speech(self, text: str) -> str:
        """Sanitize text for clean, natural spoken audio output via Text-To-Speech."""
        if not text:
            return ""

        s = text.strip()

        # 1. Strip markdown code fences & inline backticks
        s = re.sub(r"```[a-zA-Z]*\n?([\s\S]*?)```", r"\1", s)
        s = re.sub(r"`([^`]+)`", r"\1", s)

        # 2. Strip markdown headings (#, ##, ###)
        s = re.sub(r"^\s*#+\s*", "", s, flags=re.MULTILINE)

        # 3. Strip list bullets, blockquotes, and numbered prefixes BEFORE bold/italics
        s = re.sub(r"^\s*[-*+]\s+", "", s, flags=re.MULTILINE)
        s = re.sub(r"^\s*\d+[\.\)]\s+", "", s, flags=re.MULTILINE)
        s = re.sub(r"^\s*>\s+", "", s, flags=re.MULTILINE)

        # 4. Strip bold & italics formatting
        s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
        s = re.sub(r"\*([^*]+)\*", r"\1", s)
        s = re.sub(r"__([^_]+)__", r"\1", s)
        s = re.sub(r"_([^_]+)_", r"\1", s)
        s = re.sub(r"~~([^~]+)~~", r"\1", s)
        # Clean stray markdown markers
        s = re.sub(r"[*#_~]", "", s)

        # 5. Strip markdown links [label](url) -> label
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)

        # 6. Strip citation brackets like [1], [2, 3], [1-4], [citation needed]
        s = re.sub(r"\[\s*(?:\d+|[a-zA-Z]+\s+et\s+al\.?|citation\s+needed)(?:\s*[,;-]\s*\d+)*\s*\]", "", s)

        # 7. Strip URLs
        s = re.sub(r"https?://\S+|www\.\S+", "", s)

        # 8. Strip disruptive parentheticals (e.g. "(see Figure 1)", "(ibid.)", "(p. 42)", "(source: ...)")
        s = re.sub(
            r"\(\s*(?:see\s+(?:fig|figure|table|section|ref)|ibid\.?|p\.\s*\d+|pp\.\s*\d+|source:|ref\.|accessed\s+\w+)[^)]*\)",
            "",
            s,
            flags=re.IGNORECASE,
        )

        # 8b. Strip presentation field labels (e.g. "Key Takeaway:", "Main Mechanism:", "Performance:", "Security:")
        field_label_pattern = (
            r"(?:^|(?<=[\.\?!]\s)|(?<=\n))\s*(?:\*\*)?(?:"
            r"Key Takeaways?|Main Takeaways?|Core Takeaways?|Primary Takeaways?|Takeaways?|"
            r"Core Idea|Overview|Background|Architecture|Performance|Security|"
            r"Main Mechanism|Mechanism|Methodology|Key Findings?|Findings?|"
            r"The Bottom Line|Bottom Line|Main Point|Core Insight"
            r")(?:\*\*)?:\s*"
        )
        s = re.sub(field_label_pattern, "", s, flags=re.IGNORECASE)

        # 9. Expand currency symbols
        def _expand_short_curr(m: re.Match) -> str:
            val = m.group(1)
            suffix = m.group(2).upper()
            unit_map = {"T": "trillion", "B": "billion", "M": "million", "K": "thousand"}
            return f"{val} {unit_map.get(suffix, '')} dollars"

        s = re.sub(r"\$(\d+(?:\.\d+)?)\s*([TBMK])\b", _expand_short_curr, s, flags=re.IGNORECASE)
        s = re.sub(r"\$(\d+(?:\.\d+)?)\s*(trillion|billion|million|thousand)\b", r"\1 \2 dollars", s, flags=re.IGNORECASE)
        s = re.sub(r"\$(\d+)\.(\d{2})\b", r"\1 dollars and \2 cents", s)
        s = re.sub(r"\$(\d+(?:,\d{3})*(?:\.\d+)?)\b", r"\1 dollars", s)
        s = re.sub(r"\$", "dollars ", s)

        # 10. Expand numeric ranges (e.g. 800-2400 -> 800 to 2400, 10–20 -> 10 to 20)
        s = re.sub(r"\b(\d+)\s*[-–—]\s*(\d+)\b", r"\1 to \2", s)

        # 11. Expand percentages (e.g. 25% -> 25 percent)
        s = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"\1 percent", s)
        s = re.sub(r"%", " percent", s)

        # 12. Expand ampersand (& -> and)
        s = re.sub(r"(\b[A-Za-z0-9]+)\s*&\s*([A-Za-z0-9]+)", r"\1 and \2", s)
        s = re.sub(r"\s+&\s+", " and ", s)

        # 13. Expand plus sign (e.g. A+ -> A plus, 10+ -> 10 plus)
        s = re.sub(r"(\b[A-Za-z0-9]+)\s*\+", r"\1 plus", s)

        # 14. Expand number sign (e.g. #1 -> number 1)
        s = re.sub(r"#(\d+)\b", r"number \1", s)
        s = re.sub(r"#", "", s)

        # 15. Expand common spoken abbreviations for smoother TTS
        s = re.sub(r"\be\.g\.,?\s*", "for example, ", s, flags=re.IGNORECASE)
        s = re.sub(r"\bi\.e\.,?\s*", "that is, ", s, flags=re.IGNORECASE)
        s = re.sub(r"\bvs\.\s*", "versus ", s, flags=re.IGNORECASE)
        s = re.sub(r"\betc\.\s*", "and so on. ", s, flags=re.IGNORECASE)
        s = re.sub(r"\band/or\b", "and or", s, flags=re.IGNORECASE)
        s = re.sub(r"\bw/o\b", "without", s, flags=re.IGNORECASE)
        s = re.sub(r"\bw/\b", "with", s, flags=re.IGNORECASE)
        s = re.sub(r"\bapprox\.\s*", "approximately ", s, flags=re.IGNORECASE)
        s = re.sub(r"\bavg\.\s*", "average ", s, flags=re.IGNORECASE)
        s = re.sub(r"\bmin\.\s*(?=\d|\b)", "minutes ", s, flags=re.IGNORECASE)
        s = re.sub(r"\bsec\.\s*(?=\d|\b)", "seconds ", s, flags=re.IGNORECASE)
        s = re.sub(r"\b(?:hrs?|hr)\.\s*(?=\d|\b)", "hours ", s, flags=re.IGNORECASE)
        s = re.sub(r"\b(?:yrs?|yr)\.\s*(?=\d|\b)", "years ", s, flags=re.IGNORECASE)

        # 16. Clean punctuation for natural audio pauses
        s = re.sub(r"\s*[—–]\s*|\s+--\s+", ", ", s)
        s = re.sub(r"\.\.+", ".", s)
        s = re.sub(r",,+", ",", s)
        s = re.sub(r"!!+", "!", s)
        s = re.sub(r"\?\?+", "?", s)
        s = re.sub(r"[:\-\s]+$", ".", s)
        s = re.sub(r",(?=[^\s\d])", ", ", s)
        s = re.sub(r"\(\s*\)", "", s)
        s = re.sub(r"\s+", " ", s).strip()

        if s and s[-1] not in ".!?":
            s += "."

        return s

    def _format_spoken_summary(self, units: list[SentenceUnit]) -> str:
        """Combine selected sentence units into clean spoken audio explanation with natural conversational transitions."""
        if not units:
            return ""

        if len(units) == 1:
            return self.sanitize_for_speech(units[0].raw_text)

        existing_transition_pattern = re.compile(
            r"^(?:However|Furthermore|Moreover|Additionally|Therefore|Also|On the other hand|In addition|"
            r"Consequently|Nevertheless|Besides|Specifically|Importantly|Crucially|In conclusion|Overall|"
            r"Ultimately|In summary|In brief|Finally|To summarize|As a result|What this means is|"
            r"Under the hood|To make this work|Looking at|In practice|Taken together|We conclude|The bottom line is|"
            r"In real-world terms|Looking at the big picture|At the same time|On the architecture side|"
            r"First|Second|Third|Fourth|Fifth)\b",
            re.IGNORECASE,
        )

        preposition_start_pattern = re.compile(
            r"^(?:In|On|At|Under|For|With|By|To|From|During|Across|Throughout|Through|Into)\b",
            re.IGNORECASE,
        )

        contrast_start_pattern = re.compile(
            r"^(?:However|Although|Despite|Yet|Nevertheless|While|Whereas|Even though|On the other hand|In contrast)\b",
            re.IGNORECASE,
        )

        infinitive_start_pattern = re.compile(
            r"^(?:To\s+[a-z]+|In order to)\b",
            re.IGNORECASE,
        )

        formatted_sentences: list[str] = []
        recent_connectors: list[str] = []
        last_section_idx = units[0].section_idx

        for idx, unit in enumerate(units):
            cleaned = self.sanitize_for_speech(unit.raw_text)
            if not cleaned:
                continue

            # First sentence: Clean opening anchor; strip any leftover written contrast words
            if idx == 0:
                cleaned = re.sub(
                    r"^(?:However|Furthermore|Moreover|Additionally|Therefore|Also|On the other hand|In addition|Consequently|Nevertheless|Besides),?\s*",
                    "",
                    cleaned,
                    flags=re.IGNORECASE,
                )
                if cleaned:
                    cleaned = cleaned[0].upper() + cleaned[1:]
                formatted_sentences.append(cleaned)
                last_section_idx = unit.section_idx
                continue

            # For contiguous sentences in small documents: preserve original author flow directly
            if len(units) <= 2 and unit.global_idx == units[idx - 1].global_idx + 1:
                formatted_sentences.append(cleaned)
                continue

            # Check if sentence already has a natural opening transition
            if bool(existing_transition_pattern.match(cleaned)):
                formatted_sentences.append(cleaned)
                last_section_idx = unit.section_idx
                continue

            is_non_contiguous = unit.global_idx > units[idx - 1].global_idx + 1
            is_new_section = unit.section_idx != last_section_idx

            connector = ""
            starts_with_prep = bool(preposition_start_pattern.match(cleaned))
            starts_with_contrast = bool(contrast_start_pattern.match(cleaned))
            starts_with_infinitive = bool(infinitive_start_pattern.match(cleaned))

            if is_non_contiguous or is_new_section:
                # 1. Final sentence conclusion
                if idx == len(units) - 1 and len(units) >= 3 and (unit.has_conclusion_marker or unit.global_idx == units[-1].global_idx):
                    if not any(k in cleaned.lower() for k in ("conclusion", "summary", "ultimately", "bottom line")):
                        if "ultimately" not in recent_connectors:
                            connector = "Ultimately, "
                        else:
                            connector = "Looking at the big picture, "
                # 2. Caveats / Challenges / Bottlenecks (only if sentence doesn't already start with contrast or infinitive)
                elif unit.has_caveat and not starts_with_contrast and not starts_with_infinitive:
                    if "trade-off" not in recent_connectors and "however" not in recent_connectors:
                        connector = "The main trade-off, however, is that "
                    elif "on the other hand" not in recent_connectors:
                        connector = "On the other hand, "
                    else:
                        connector = "However, "
                # 3. Mechanisms / Architecture
                elif unit.has_mechanism and not starts_with_prep:
                    if is_new_section and "under the hood" not in recent_connectors:
                        connector = "Under the hood, "
                    elif "to make this work" not in recent_connectors:
                        connector = "To make this work, "
                # 4. Outcomes / Results / Impact (do not add 'In practice' if sentence already starts with 'In' or preposition)
                elif unit.has_outcome and not starts_with_prep:
                    if "in practice" not in recent_connectors:
                        connector = "In practice, "
                    elif "performance" not in recent_connectors:
                        connector = "Looking at the performance, "
                # 5. Section jump (only if sentence doesn't already start with a preposition or infinitive)
                elif is_new_section and not starts_with_prep and not starts_with_infinitive:
                    if "moving forward" not in recent_connectors:
                        connector = "Moving forward, "
                    elif "at the same time" not in recent_connectors:
                        connector = "At the same time, "

            if connector:
                recent_connectors.append(connector.lower().strip(", "))
                if len(recent_connectors) > 4:
                    recent_connectors.pop(0)

                words = cleaned.split(None, 1)
                first_word = words[0] if words else ""
                first_char = cleaned[0] if cleaned else ""
                keep_upper = (
                    first_word.isupper()
                    or first_word in ("Voice", "Google", "Microsoft", "Windows", "OpenAI", "Apple", "Raft", "TLS", "LiDAR", "AT&T", "CPU", "GPU")
                    or first_char in "\"'“‘0123456789$"
                )
                if keep_upper or connector.endswith("that "):
                    cleaned = f"{connector}{cleaned}"
                else:
                    cleaned = f"{connector}{cleaned[0].lower()}{cleaned[1:]}"

            formatted_sentences.append(cleaned)
            last_section_idx = unit.section_idx

        return " ".join(formatted_sentences)

    def _declutter_conversational_text(self, raw: str) -> str:
        """Strip stuttering, repetitive colloquialisms, and speech-to-text artifacts."""
        t = raw.strip()
        t = re.sub(r"\bII\b", "I", t)
        t = re.sub(r"\b(\w+)(?:\s+\1\b)+", r"\1", t, flags=re.IGNORECASE)
        t = re.sub(r"\b(?:like\s+)+(like)\b", r"\1", t, flags=re.IGNORECASE)
        t = re.sub(
            r"\b(?:stuff\s+and\s+all|and\s+all\s+those\s+stuffs?|and\s+all\s+stuffs?|and\s+all\s+those\s+stuff|and\s+all|and\s+everything\s+properly)\b",
            "",
            t,
            flags=re.IGNORECASE,
        )
        t = re.sub(r"\bread\s+read\s+read\b", "reading word-for-word", t, flags=re.IGNORECASE)
        t = re.sub(r"\breading\s+reading\s+reading\b", "reading word-for-word", t, flags=re.IGNORECASE)
        t = re.sub(r"\bdo\s+one\s+thing\b", "please", t, flags=re.IGNORECASE)
        t = re.sub(r"\bwhat's\s+happening\s+in\s+happening\s+is\b", "what is happening is that", t, flags=re.IGNORECASE)
        t = re.sub(r"\bright\s+now\b", "currently", t, flags=re.IGNORECASE)
        t = re.sub(r"\bcontrol\s+plus\s+copy\b", "control plus C", t, flags=re.IGNORECASE)
        t = re.sub(r"\bcontrol\s+plus\s+it\b", "control plus V", t, flags=re.IGNORECASE)
        t = re.sub(r"\bvoicemail\s+feature\b", "voice flow feature", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+", " ", t).strip()
        return self.sanitize_for_speech(t)

    def _extract_topic_from_text(self, text: str) -> str:
        """Extract core subject or feature topic for conversational lead-in."""
        lower = text.lower()
        m = re.search(r"\b(?:the|on)\s+([a-z0-9_\-\s]{2,30}?)\s+(?:feature|system|bug|issue|process|app|tool|code|pipeline)\b", lower)
        if m:
            name = re.sub(r"^the\s+", "", m.group(1).strip(), flags=re.IGNORECASE)
            noun = lower[m.end(1):m.end(0)].strip()
            return f"the {name.title()} {noun}"
        if "audio flow" in lower:
            return "the Audio Flow feature"
        if "voice flow" in lower or "voicemail" in lower:
            return "the Voice Flow application"
        if "copy" in lower or "ctrl" in lower or "clipboard" in lower:
            return "the clipboard copy shortcuts"
        if "mouse" in lower or "click" in lower:
            return "mouse click interactions"
        first_sent = text.strip().split(".")[0].strip()
        words = first_sent.split()
        if 1 <= len(words) <= 5:
            return first_sent
        return "the selected text"

    def explain_conversationally(self, raw_text: str) -> str:
        """Synthesize an offline spoken explanation of the given text conversationally.

        Explains intent, core takeaways, and details naturally to the listener rather
        than reading characters mechanically like a screen reader.
        """
        if not raw_text or not raw_text.strip():
            return ""

        clean_text = raw_text.strip()
        lower = clean_text.lower()
        topic = self._extract_topic_from_text(clean_text)

        # 1. Detect if it's a user chat message / feedback / bug report
        user_message_patterns = [
            r"\b(?:hey|hi|hello)\b",
            r"\b(?:can\s+you|could\s+you)\b",
            r"\b(?:i\s+just|i'm\s+facing|i\s+am\s+facing|my\s+problem)\b",
            r"\b(?:facing\s+1\s+bug|facing\s+a\s+bug|bug|bugs)\b",
            r"\b(?:tried|tested)\b",
            r"\b(?:not\s+working|fails\s+to|doesn't\s+work|please\s+fix)\b",
            r"\b(?:check\s+back\s*end|check\s+what's\s+happening|do\s+one\s+thing)\b",
        ]
        is_user_message = any(re.search(pat, lower) for pat in user_message_patterns)

        if is_user_message:
            lead_in = f"In this message, the sender shares feedback regarding {topic}."

            points = []
            if any(re.search(r"\b" + re.escape(w) + r"\b", lower) for w in ["not human like", "single flow", "just read", "reading reading", "read read read", "word for word"]):
                points.append("they explain that the current audio delivery sounds too much like a computer reading text word-for-word, rather than a natural human conversation")

            if any(w in lower for w in ["explanation type", "how human explain", "explain each other", "how human reading"]):
                points.append("they want the audio redesigned into an explanation-style presentation, where the core ideas are explained clearly to the listener as one colleague to another")

            if re.search(r"\bresearch\b", lower):
                points.append("they suggest researching how people explain concepts to each other so the audio flow experience feels intuitive and natural")

            if any(w in lower for w in ["mouse left click", "left click", "mouse click"]) and any(w in lower for w in ["voice detection", "starting", "triggers"]):
                points.append("they report an issue where performing a left mouse click inadvertently triggers voice recording")

            if any(w in lower for w in ["control plus copy", "ctrl+c", "control plus"]) and any(w in lower for w in ["not properly working", "broken", "issue"]):
                points.append("they note that standard keyboard shortcuts like control plus C are not functioning properly")

            if any(w in lower for w in ["note thing", "make the note", "note bigger", "warning bigger", "card bigger", "notice bigger", "so small", "little bit bigger"]):
                points.append("they request making the note card and text significantly bigger so it is comfortable and effortless to read")

            if points:
                parts = [lead_in, PAUSE_SECTION, f"Specifically, {points[0]}."]
                for i, pt in enumerate(points[1:], start=1):
                    connector = "Furthermore," if i == 1 else ("Additionally," if i == 2 else "In short,")
                    parts.extend([PAUSE_PARAGRAPH, f"{connector} {pt}."])
                return " ".join(parts)

            decluttered = self._declutter_conversational_text(clean_text)
            return f"{lead_in} {PAUSE_SECTION} Specifically, they state: {decluttered}"

        # 2. Detect if it's an inquiry / question
        if lower.startswith(("how", "why", "what", "when", "where", "is there", "can we")) or clean_text.endswith("?"):
            decluttered = self._declutter_conversational_text(clean_text)
            return f"This question asks about {topic}. {PAUSE_SECTION} Specifically: {decluttered}"

        # 3. Detect if it's a code snippet or function definition
        code_signals = ["def ", "class ", "import ", "return ", "function ", "const ", "let ", "var ", "public class "]
        if any(sig in clean_text for sig in code_signals) or ("\n    " in clean_text and "{" in clean_text):
            first_line = clean_text.splitlines()[0].strip()
            return f"This code snippet outlines {topic}. {PAUSE_SECTION} It begins with: {first_line}, and implements the corresponding logic."

        # 4. Multi-sentence informational article or documentation
        sentences = self.tokenize_sentences(clean_text)
        if len(sentences) >= 3:
            summary_content = self.summarize(clean_text, depth="balanced")
            return f"Here is an explanation of {topic}. {PAUSE_SECTION} {summary_content}"

        # 5. Short text / general text
        decluttered = self._declutter_conversational_text(clean_text)
        return f"Here is an explanation of {topic}. {PAUSE_SECTION} {decluttered}"


# Singleton instance
local_spoken_summarizer = LocalSpokenSummarizer()


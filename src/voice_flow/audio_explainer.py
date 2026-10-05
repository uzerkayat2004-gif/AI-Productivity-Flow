"""Spoken Human Explainer Engine for Audio Flow Read Mode.

Transforms raw selected text — chat messages, feedback, emails, technical documentation,
articles, code, or procedures — into natural, human-like explanatory narration.
Rather than reading raw characters mechanically like a robotic teleprompter, this engine
delivers the clarity, cadence, and conversational framing of a knowledgeable colleague
reading and explaining the content directly to the listener.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import queue
import re
import threading
import time
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Callable, Any

from voice_flow.structured_reader import (
    PAUSE_SECTION,
    PAUSE_PARAGRAPH,
    PAUSE_LIST_ITEM,
    format_document_structure_for_speech,
    split_spoken_sentences,
    strip_pause_markers,
)
from voice_flow.audio_summary_prompts import sanitize_narration_text
from voice_flow.audio_explainer_prompts import (
    build_audio_explainer_prompt,
    sanitize_explanation_text,
    build_human_reading_prompt,
)
from voice_flow.local_summarizer import local_spoken_summarizer
from voice_flow.storage import storage

log = logging.getLogger(__name__)

_READ_CACHE_VERSION = "v9"
_READ_REQUEST_TIMEOUT_SECONDS = 6.5
_NEGATION_RE = re.compile(r"\b(?:no|not|never|cannot|can't|won't|without|rather than)\b", re.IGNORECASE)
_UNSUPPORTED_REQUIREMENT_RE = re.compile(r"\b(?:mandatory|must|required|guaranteed?)\b", re.IGNORECASE)


def _source_numbers(text: str) -> set[str]:
    """Extract normalized numeric values, ignoring Markdown outline markers."""
    values: set[str] = set()
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", line)
        for match in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)(?:\s*(?:%|x|days?|seconds?))?\b", line, re.IGNORECASE):
            try:
                raw_value = match.group(1)
                value = Decimal(raw_value).normalize()
            except InvalidOperation:  # pragma: no cover - regex only supplies decimals
                continue
            # Decimal normalization already collapses harmless fractional
            # spellings (0.30 -> 0.3). Never strip trailing zeroes from a
            # whole number: 30 and 3 are different measurements.
            values.add(format(value, "f") if "." in raw_value else str(int(value)))
    return values


def _source_entities(text: str) -> set[str]:
    """Return distinctive proper-name tokens worth retaining in a short narration."""
    return {
        token.lower()
        for token in re.findall(r"\b(?:[A-Z][A-Za-z0-9-]{2,}|[A-Z]{2,})\b", text)
        if token.lower() not in {"the", "this", "that", "but", "and", "for", "with", "when", "where"}
    }


def _content_words(text: str) -> set[str]:
    return {
        word.lower()
        for word in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", text)
        if word.lower() not in {"that", "this", "with", "from", "they", "their", "would", "should", "about", "where", "which", "there", "these", "those", "because", "other", "before", "after", "into", "when", "what", "will", "have", "been", "were", "more", "than", "then", "only"}
    }

# ---------------------------------------------------------------------------
# Conversational Spoken Abbreviation and Symbol Expansions
# ---------------------------------------------------------------------------
SPOKEN_ABBREVIATIONS: list[tuple[re.Pattern, Any]] = [
    # Latin & Conversational abbreviations
    (re.compile(r"\b(e\.g|eg)\b\.?", re.IGNORECASE), "for example"),
    (re.compile(r"\b(i\.e|ie)\b\.?", re.IGNORECASE), "that is"),
    (re.compile(r"\betc\b\.?", re.IGNORECASE), "and so forth"),
    (re.compile(r"\bvs\b\.?", re.IGNORECASE), "versus"),
    (re.compile(r"\bv\.\s+", re.IGNORECASE), "versus "),
    (re.compile(r"\b(approx)\b\.?", re.IGNORECASE), "approximately"),
    (re.compile(r"\b(est)\b\.?", re.IGNORECASE), "estimated"),
    (re.compile(r"\bw/o\b", re.IGNORECASE), "without"),
    (re.compile(r"\bw/\s*", re.IGNORECASE), "with "),
    (re.compile(r"\bb/c\b", re.IGNORECASE), "because"),
    (re.compile(r"\bfyi\b", re.IGNORECASE), "for your information"),
    (re.compile(r"\basap\b", re.IGNORECASE), "as soon as possible"),
    (re.compile(r"\btbd\b", re.IGNORECASE), "to be determined"),
    (re.compile(r"\baka\b", re.IGNORECASE), "also known as"),
    (re.compile(r"\bw\.r\.t\.?,?", re.IGNORECASE), "with respect to"),

    # Technical acronyms & concepts
    (re.compile(r"\bPRs\b"), "pull requests"),
    (re.compile(r"\bPR\b"), "pull request"),
    (re.compile(r"\bUIs\b"), "user interfaces"),
    (re.compile(r"\bUI\b"), "user interface"),
    (re.compile(r"\bUX\b"), "user experience"),
    (re.compile(r"\bTTS\b"), "text to speech"),
    (re.compile(r"\bSTT\b"), "speech to text"),
    (re.compile(r"\bLLMs\b"), "large language models"),
    (re.compile(r"\bLLM\b"), "large language model"),
    (re.compile(r"\bAPIs\b"), "A P Is"),
    (re.compile(r"\bAPI\b"), "A P I"),
    (re.compile(r"\bSDKs\b"), "S D Ks"),
    (re.compile(r"\bSDK\b"), "S D K"),
    (re.compile(r"\bCLIs\b"), "command line interfaces"),
    (re.compile(r"\bCLI\b"), "command line interface"),
    (re.compile(r"\bURLs\b"), "U R Ls"),
    (re.compile(r"\bURL\b"), "U R L"),
    (re.compile(r"\bIDs\b"), "I Ds"),
    (re.compile(r"\bID\b"), "I D"),
    (re.compile(r"\bOS\b"), "operating system"),
    (re.compile(r"\bCPUs\b"), "C P Us"),
    (re.compile(r"\bCPU\b"), "C P U"),
    (re.compile(r"\bGPUs\b"), "G P Us"),
    (re.compile(r"\bGPU\b"), "G P U"),
    (re.compile(r"\bRAM\b"), "memory"),
    (re.compile(r"\bDBs\b", re.IGNORECASE), "databases"),
    (re.compile(r"\bDB\b", re.IGNORECASE), "database"),
    (re.compile(r"\bconfigs?\b", re.IGNORECASE), "configuration"),
    (re.compile(r"\bcfg\b", re.IGNORECASE), "configuration"),
    (re.compile(r"\brepos?\b", re.IGNORECASE), "repository"),
    (re.compile(r"\bdocs?\b", re.IGNORECASE), "documentation"),
    (re.compile(r"\bdevs?\b", re.IGNORECASE), "developers"),
    (re.compile(r"\bprod\b", re.IGNORECASE), "production"),
    (re.compile(r"\benvs?\b", re.IGNORECASE), "environments"),
    (re.compile(r"\bauth\b", re.IGNORECASE), "authentication"),
    (re.compile(r"\bsync\b", re.IGNORECASE), "synchronization"),
    (re.compile(r"\bparams?\b", re.IGNORECASE), "parameters"),
    (re.compile(r"\bfuncs?\b", re.IGNORECASE), "functions"),

    # Shortcuts
    (re.compile(r"\bctrl\s*\+\s*c\b", re.IGNORECASE), "control plus C"),
    (re.compile(r"\bctrl\s*\+\s*v\b", re.IGNORECASE), "control plus V"),
    (re.compile(r"\bctrl\s*\+\s*z\b", re.IGNORECASE), "control plus Z"),
    (re.compile(r"\bctrl\s*\+\s*a\b", re.IGNORECASE), "control plus A"),
    (re.compile(r"\bctrl\s*\+\s*x\b", re.IGNORECASE), "control plus X"),
    (re.compile(r"\bctrl\b", re.IGNORECASE), "control"),
    (re.compile(r"\bcmd\b", re.IGNORECASE), "command"),

    # Business / quarters
    (re.compile(r"\bQ([1-4])\b"), lambda m: f"quarter {m.group(1)}"),
    (re.compile(r"\bv([1-9](?:\.\d+)?)\b", re.IGNORECASE), lambda m: f"version {m.group(1)}"),
]


def expand_spoken_abbreviations(text: str) -> str:
    """Expand abbreviations, acronyms, and symbols into natural spoken English."""
    if not text:
        return text

    t = text
    for pattern, replacement in SPOKEN_ABBREVIATIONS:
        if callable(replacement):
            t = pattern.sub(replacement, t)
        else:
            t = pattern.sub(replacement, t)

    return t


def declutter_spoken_text(raw: str) -> str:
    """Untangle stuttering, repetitive colloquialisms, and speech-to-text / typing artifacts."""
    if not raw:
        return ""

    t = raw.strip()
    # Replace double 'II' artifact
    t = re.sub(r"\bII\b", "I", t)
    # Consecutive duplicate words ('the the' -> 'the', 'like like' -> 'like')
    t = re.sub(r"\b([a-zA-Z]+)(?:\s+\1\b)+", r"\1", t, flags=re.IGNORECASE)
    # Filler phrases that degrade spoken delivery
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
    t = re.sub(r"\bvoicemail\s+feature\b", "voice flow feature", t, flags=re.IGNORECASE)

    # Clean whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


class AudioExplainer:
    """Conversational Human Explainer and Reading Narrator for Audio Flow."""

    def __init__(self) -> None:
        self._ai_cooldowns: dict[str, float] = {}

    def normalize_spoken_text(self, text: str) -> str:
        """Deep normalization for spoken audio: expands symbols, abbreviations, and fixes syntax."""
        if not text or not text.strip():
            return ""

        # Step 1: Clean raw markdown & artifacts
        cleaned = sanitize_narration_text(text)

        # Step 2: Untangle stuttering & colloquial clutter
        decluttered = declutter_spoken_text(cleaned)

        # Step 3: Expand spoken abbreviations & symbols
        expanded = expand_spoken_abbreviations(decluttered)

        # Step 4: Apply document structure formatting (ordinals, dates, metrics, pauses)
        structured = format_document_structure_for_speech(expanded)

        return structured.strip()

    @staticmethod
    def _read_output_token_budget(source_words: int) -> int:
        """Bound Read generation near its requested spoken-word range."""
        # Allow the requested 55--75% spoken-word script plus response and
        # low-thinking overhead. A 300-word selection receives 800 tokens.
        return min(2048, max(320, math.ceil(max(1, source_words) * 2 + 200)))

    @staticmethod
    def _extract_gemini_text(body: dict[str, Any]) -> str:
        candidates = body.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini Read request returned no candidates.")
        candidate = candidates[0]
        if candidate.get("finishReason") in {"MAX_TOKENS", "SAFETY", "RECITATION"}:
            raise ValueError(f"Gemini Read request ended with {candidate['finishReason']}.")
        parts = candidate.get("content", {}).get("parts", [])
        text = "".join(
            str(part.get("text", ""))
            for part in parts
            if isinstance(part, dict) and not part.get("thought")
        )
        if not text.strip():
            raise ValueError("Gemini Read request returned no text output.")
        return text

    def _call_gemini_read(self, model_id: str, api_key: str, prompt: str, source_words: int) -> str:
        """Use a short, Read-only Gemini request without changing Summary transport."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
        generation_config: dict[str, Any] = {
            "temperature": 0.2,
            "maxOutputTokens": self._read_output_token_budget(source_words),
        }
        # Gemini 3 exposes a low-thinking level; older models accept a zero
        # thinking budget. Either keeps this latency-sensitive path focused on
        # narration rather than extended deliberation.
        if model_id.lower().startswith("gemini-3"):
            generation_config["thinkingConfig"] = {"thinkingLevel": "minimal"}
        else:
            generation_config["thinkingConfig"] = {"thinkingBudget": 0}
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": generation_config}
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=_READ_REQUEST_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
        return self._extract_gemini_text(body)

    def _is_safe_explanation(self, source: str, candidate: str) -> bool:
        """Reject obviously incomplete or stronger-than-source model rewrites.

        This deliberately stays conservative and cheap: it is a guardrail for a
        spoken rewrite, not a claim that lexical matching can fully fact-check one.
        """
        if not candidate or len(candidate.split()) < 5:
            return False
        source_words = len(source.split())
        if source_words >= 30 and len(candidate.split()) < max(12, source_words // 7):
            return False

        candidate_lower = candidate.lower()
        # A spoken explanation may omit incidental implementation measurements,
        # but it must never introduce a measurement the source did not state.
        # Requiring every source number made otherwise sound condensed scripts
        # fail validation and fall through to a near-verbatim local read.
        if not _source_numbers(candidate).issubset(_source_numbers(source)):
            return False
        entities = _source_entities(source)
        # A short source may not contain a formal name. For substantive text,
        # retaining at least the distinctive names prevents generic rewrites.
        if len(entities) >= 2 and not any(entity in candidate_lower for entity in entities):
            return False
        if _NEGATION_RE.search(source) and not _NEGATION_RE.search(candidate):
            return False
        if _UNSUPPORTED_REQUIREMENT_RE.search(candidate) and not _UNSUPPORTED_REQUIREMENT_RE.search(source):
            return False
        # A general obligation elsewhere in the source does not support
        # inventing a mandatory checkpoint for a specific process.
        if re.search(r"\b(?:mandatory|required)\s+(?:checkpoint|gate|step)\b", candidate, re.IGNORECASE) and not re.search(
            r"\b(?:mandatory|required)\s+(?:checkpoint|gate|step)\b", source, re.IGNORECASE
        ):
            return False
        # Preserve who made a claim and its stated geographic scope. A rewrite
        # may clarify wording, but cannot turn one organization's practice into
        # an industry-wide rule or replace a regional qualifier with a global one.
        universal_scope = re.compile(r"\b(?:industry-wide|across\s+(?:all\s+)?labs|every\s+company|all\s+companies)\b", re.IGNORECASE)
        if universal_scope.search(candidate) and not universal_scope.search(source):
            return False
        source_geographies = {
            term.lower()
            for term in re.findall(r"\b(?:American|European|Asian|African|global|international|domestic)\b", source, re.IGNORECASE)
        }
        candidate_geographies = {
            term.lower()
            for term in re.findall(r"\b(?:American|European|Asian|African|global|international|domestic)\b", candidate, re.IGNORECASE)
        }
        if not candidate_geographies.issubset(source_geographies):
            return False
        # Long documents need evidence from their beginning, middle, and end.
        # This catches fluent outputs that only explain the opening paragraph.
        units = local_spoken_summarizer.tokenize_sentences(source)
        if len(units) >= 6:
            candidate_terms = _content_words(candidate)
            # Use exactly three balanced spans. Stepping by floor(n / 3)
            # creates a fourth, tiny tail for 10--11 sentences, which can be
            # a sign-off rather than a material theme.
            for index in range(3):
                start = index * len(units) // 3
                end = (index + 1) * len(units) // 3
                segment = " ".join(unit.clean_text for unit in units[start:end])
                if len(_content_words(segment) & candidate_terms) < 2:
                    return False
        return True

    @staticmethod
    def _walkthrough_phrase(text: str, limit: int = 5) -> str:
        """Return a short topic phrase without replaying a source sentence."""
        words = re.findall(r"[A-Za-z][A-Za-z0-9/-]*", text)
        stop = {
            "the", "a", "an", "and", "or", "for", "with", "this", "that", "these",
            "those", "from", "into", "about", "through", "using", "uses", "use", "is",
            "are", "to", "of", "in", "on", "by", "it", "its", "as", "plus",
        }
        kept = [word for word in words if word.lower() not in stop]
        return " ".join(kept[:limit]) or "the main idea"

    @classmethod
    def _structured_walkthrough(cls, text: str) -> str | None:
        """Turn indented headings and bullets into an original spoken outline.

        The output is deliberately assembled from short topic fragments.  That
        keeps the deterministic fallback useful when an AI provider is absent,
        without silently turning Read into a trimmed copy of the selection.
        """
        rows: list[tuple[int, str, bool]] = []
        for raw in text.splitlines():
            match = re.match(r"^(\s*)(?:[-*+]\s+|\d+[.)]\s+)?(.+?)\s*$", raw)
            if not match:
                continue
            indent, body = match.groups()
            body = re.sub(r"^[#]+\s*", "", body).strip()
            # Structural labels often arrive as copied Markdown. Keep their
            # meaning while removing punctuation that is useless in speech.
            body = re.sub(r"[`*_]+", "", body).replace("→", " to ")
            body = re.sub(r"[\U0001F300-\U0001FAFF\ufe0f]", "", body).strip()
            if not body or len(body.split()) < 2:
                continue
            depth = len(indent.expandtabs(2)) // 2
            is_list_item = bool(re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", raw))
            if re.match(r"^\d+[.)]\s+", raw):
                depth = 0
            rows.append((depth, body, is_list_item))

        # A document with no actual list structure is better handled by the
        # prose path below.  `rows` also includes ordinary paragraph lines.
        if sum(is_list_item for _, _, is_list_item in rows) < 3:
            return None

        intro = next((body for depth, body, is_list_item in rows if not is_list_item and depth == 0 and not body.endswith(":") and not re.match(r"^(?:yes|no|i\s)", body, re.IGNORECASE)), "")
        groups: list[tuple[str, list[str]]] = []
        current_title = ""
        current_points: list[str] = []
        for depth, body, is_list_item in rows:
            if not is_list_item:
                continue
            title = body.rstrip(":")
            is_section = depth == 0 or (depth == 1 and body.endswith(":"))
            if is_section:
                if current_title:
                    groups.append((current_title, current_points))
                current_title, current_points = title, []
            elif current_title:
                current_points.append(title)
        if current_title:
            groups.append((current_title, current_points))
        if not groups:
            return None

        def point_sentence(point: str) -> str:
            """Explain recurring structured-document patterns in spoken prose."""
            lowered = point.lower()
            if re.search(r"(?:\b[a-z]:[\\/]|\\(?:users|projects|src|scripts)\\|/[\w.-]+/)", point, re.IGNORECASE):
                return "It records a project location for reference."
            if "background" in lowered and ("app" in lowered or "application" in lowered):
                return "It keeps the service in the background so people can stay in the application they already use."
            if "trigger" in lowered and "playback" not in lowered:
                has_mouse = "mouse" in lowered
                has_keyboard = "keyboard" in lowered or "hotkey" in lowered or "ctrl" in lowered
                if has_mouse and has_keyboard:
                    return "It starts from the available mouse or keyboard gestures."
                if has_mouse:
                    return "It can start from a mouse gesture."
                if has_keyboard:
                    return "It can start from a keyboard gesture."
            if "push-to-talk" in lowered and ("hold" in lowered or "more than" in lowered) and "tap" in lowered and "continuous" in lowered:
                return "Holding starts push-to-talk, while tapping switches continuous dictation on or off."
            if "push-to-talk" in lowered:
                return "It includes push-to-talk input."
            if "foreground" in lowered and ("format" in lowered or "style" in lowered):
                return "It adapts the result to the application currently in front."
            if "transcription" in lowered and "local" in lowered and ("clipboard" in lowered or "injection" in lowered):
                return "Local processing transcribes speech and places the result in the active application."
            if ("highlight" in lowered or "selected" in lowered) and ("playback" in lowered or "speech" in lowered) and ("synchronized" in lowered or "word tracking" in lowered):
                return "Selected content can be read aloud while progress stays synchronized."
            if "overlay" in lowered and ("widget" in lowered or "floating" in lowered):
                return "The interface uses lightweight overlays and floating controls."
            if "player" in lowered or ("speed" in lowered and "play" in lowered):
                return "A floating player provides playback and speed controls."
            if "provider" in lowered and "key" in lowered and any(term in lowered for term in ("storage", "stored", "encrypted")):
                return "It supports configurable provider connections while keeping their keys in local protected storage."
            if ("hub" in lowered or "provider" in lowered) and any(term in lowered for term in ("storage", "stored", "encrypted")):
                return "It supports configurable provider connections with local protected storage."
            if ("provider" in lowered or "tts" in lowered) and ("tts" in lowered or any(term in lowered for term in ("speech", "text to speech", "audio", "voice"))):
                return "It can use several available speech engines."
            if "evidence" in lowered and "entity" in lowered:
                return "It plans an explanation from the source evidence and its important entities."
            if ("render" in lowered or "visual" in lowered) and "narration" in lowered and ("qa" in lowered or "quality check" in lowered or "automated check" in lowered):
                return "Its rendering process combines visuals, narration, and automated quality checks."
            if "hook" in lowered or "hotkey" in lowered or "watchdog" in lowered:
                return "System-level input handling and supervision support the desktop experience."
            if ("telemetry" in lowered or "heatmap" in lowered or "usage" in lowered) and "snippet" in lowered:
                return "Activity information provides usage insights and reusable shortcuts."

            label, separator, detail = point.partition(":")
            if separator and detail.strip():
                return f"It addresses {cls._walkthrough_phrase(label, 5).lower()}, with details about {cls._walkthrough_phrase(detail, 8).lower()}."
            return f"It also discusses {cls._walkthrough_phrase(point, 8).lower()}."

        def section_lead(title: str) -> str:
            name = title.split(":", 1)[0].strip()
            purpose = re.search(r"\(([^()]+)\)", name)
            if purpose and re.fullmatch(r"[A-Za-z ]+ to [A-Za-z ]+", purpose.group(1)):
                left, right = (part.strip().lower() for part in purpose.group(1).split(" to ", 1))
                return f"{name.split('(', 1)[0].strip()} turns {left} into {right}."
            if "platform" in name.lower() or "infrastructure" in name.lower():
                return "The platform infrastructure supports the desktop experience."
            return f"The {cls._walkthrough_phrase(name, 6)} section describes its role in the overall system."

        parts: list[str] = []
        if intro:
            system_name = re.search(
                r"\b([A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*){0,4}\s+(?:desktop application|system|platform))\b",
                text,
            )
            if system_name:
                parts.append(f"This overview describes the {system_name.group(1)} and its main components.")
            else:
                parts.append("This overview describes the system's design and its main components.")
            if "background" in intro.lower():
                parts.append("Its design keeps the application in the background instead of requiring a separate dashboard.")
        spoken_groups = [(title, points) for title, points in groups if points or len(groups) == 1]
        max_points = 1 if len(text.split()) < 150 else 4
        for index, (title, points) in enumerate(spoken_groups[:6]):
            transition = ("First" if index == 0 else "Next" if index < len(spoken_groups) - 1 else "Finally")
            lead = section_lead(title)
            if "philosophy" in title.lower() and any("background" in point.lower() for point in points):
                lead = "The core philosophy is a background-first design."
            if lead.startswith("The "):
                lead = lead[:1].lower() + lead[1:]
            if "codebase" in title.lower() or "location" in title.lower():
                parts.append(f"{transition}, the project also lists repository and development-script locations.")
                continue
            if points:
                parts.append(f"{transition}, {lead} {' '.join(point_sentence(point) for point in points[:max_points])}")
            else:
                parts.append(f"{transition}, {lead}")
        # A single numbered section with children is still a meaningful
        # structured selection (for example, a short location list).
        return " ".join(parts) if parts else None

    def _offline_document_explanation(self, text: str) -> str:
        """Create a fast, source-ordered spoken walkthrough without raw readback."""
        structured = self._structured_walkthrough(text)
        if structured:
            return self.normalize_spoken_text(structured)
        units = local_spoken_summarizer.tokenize_sentences(text)
        if len(units) < 3:
            return self.normalize_spoken_text(text)

        # Unstructured prose needs grammatical source sentences rather than
        # keyword fragments. Select a compact representative from each part of
        # the argument, retaining its conditions and conclusion.
        local_spoken_summarizer.score_sentences(units, is_multi_page=len(units) > 8, depth="balanced")
        target = min(len(units), 12)
        chosen = {0, len(units) - 1}
        if len(units) > 1:
            chosen.add(len(units) - 2)
        for index in range(target):
            start = index * len(units) // target
            end = max(start + 1, (index + 1) * len(units) // target)
            chosen.add(max(units[start:end], key=lambda item: item.salience_score).global_idx)
        selected = [unit.clean_text for unit in units if unit.global_idx in chosen]
        group_size = max(1, (len(selected) + 2) // 3)
        groups = [selected[index:index + group_size] for index in range(0, len(selected), group_size)]
        labels = (
            "The text begins with this central concern:",
            "It then develops the argument:",
            "Finally, it draws out the implications:",
        )
        parts = [f"{labels[index]} {' '.join(group)}" for index, group in enumerate(groups[:3])]
        return self.normalize_spoken_text(f" {PAUSE_SECTION} ".join(parts))

    def explain_offline(self, text: str, context: str | None = None) -> str:
        """Synthesize a 100% offline, zero-dependency human explanatory narration.

        Executes in under 1 millisecond with zero external calls, ensuring instant Time-To-First-Audio.
        """
        if not text or not text.strip():
            return ""

        clean_text = text.strip()
        lower = clean_text.lower()

        # Step 1: Check if local_spoken_summarizer can handle known user feedback / bug / code patterns
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
            explanation = local_spoken_summarizer.explain_conversationally(clean_text)
            if explanation and explanation != clean_text:
                return self.normalize_spoken_text(explanation)

        # Step 2: Inquiries & Questions
        if lower.startswith(("how", "why", "what", "when", "where", "is there", "can we")) or clean_text.endswith("?"):
            topic = local_spoken_summarizer._extract_topic_from_text(clean_text)
            decluttered = declutter_spoken_text(clean_text)
            normalized = self.normalize_spoken_text(decluttered)
            return f"This question asks about {topic}. {PAUSE_SECTION} Specifically: {normalized}"

        # Step 3: Code snippets
        code_at_line_start = re.compile(
            r"(?m)^\s*(?:def\s+\w+\s*\(|class\s+\w+\b|import\s+\w+|from\s+\w+\s+import\s+|"
            r"(?:const|let|var)\s+\w+\s*=|function\s+\w+\s*\(|public\s+class\s+\w+)"
        )
        if "```" in clean_text or code_at_line_start.search(clean_text) or ("\n    " in clean_text and "{" in clean_text):
            return local_spoken_summarizer.explain_conversationally(clean_text)

        # List and heading structure is meaningful even when it contains too
        # few sentence terminators for the document route below.
        structured = self._structured_walkthrough(clean_text)
        if structured:
            return self.normalize_spoken_text(structured)

        # Step 4: Multi-sentence articles or documentation. This is intentionally
        # a themed walkthrough, not a prefix followed by the entire source.
        sentences = split_spoken_sentences(clean_text)
        if len(sentences) >= 3:
            return self._offline_document_explanation(clean_text)

        # Step 5: Short / general text
        if len(clean_text.split()) <= 8:
            expanded = expand_spoken_abbreviations(clean_text)
            decluttered = declutter_spoken_text(expanded)
            if decluttered.lower() == clean_text.lower():
                return clean_text
            return self.normalize_spoken_text(clean_text)

        topic = local_spoken_summarizer._extract_topic_from_text(clean_text)
        normalized = self.normalize_spoken_text(clean_text)
        return f"The key point about {topic} is: {normalized}"

    def explain_with_ai(
        self,
        text: str,
        context: str | None = None,
        model_ref: str | None = None,
    ) -> str:
        """Generate an AI-powered conversational explanation using the active provider with offline fallback."""
        if not text or not text.strip():
            return ""

        try:
            from voice_flow.audio_summary import audio_summary_service

            resolved_ref = model_ref or storage.get_setting("audio_flow_explainer_model", "local/deterministic")
            result = audio_summary_service.explain(
                text=text,
                context=context,
                model_ref=resolved_ref,
                allow_fallback=True,
            )
            if result and self._is_safe_explanation(text, result):
                return self.normalize_spoken_text(result)
        except Exception as exc:
            log.warning("AI explanation generation failed (%s); falling back to offline explainer.", exc)

        return self.explain_offline(text, context)

    def read_with_ai(
        self,
        text: str,
        context: str | None = None,
        model_id: str = "gemini-3.5-flash-lite",
    ) -> str | None:
        """Call Gemini to transform text into an articulate human explanatory reading with sub-second caching."""
        keys = storage.get_all_api_keys()
        gemini_key = keys.get("gemini")
        if not gemini_key:
            return None

        clean_text = text.strip()
        clean_context = (context or "").strip()
        cache_key = hashlib.sha256(f"human_read_{_READ_CACHE_VERSION}:{model_id}:{clean_context}:{clean_text}".encode("utf-8")).hexdigest()[:32]
        try:
            cached_entry = storage.get_audio_summary_cache(cache_key)
            if cached_entry and self._is_safe_explanation(clean_text, str(cached_entry.get("summary_text", ""))):
                log.info("Audio Flow human reading cache hit for key %s", cache_key[:16])
                return str(cached_entry["summary_text"])
        except Exception:
            pass

        try:
            prompt = build_human_reading_prompt(clean_text, context=context)
            cooldown_key = model_id.lower()
            if self._ai_cooldowns.get(cooldown_key, 0) > time.monotonic():
                return None
            response_queue: queue.Queue[tuple[bool, str | Exception]] = queue.Queue(maxsize=1)

            def request() -> None:
                try:
                    response_queue.put((True, self._call_gemini_read(model_id, gemini_key, prompt, len(clean_text.split()))))
                except Exception as exc:  # pragma: no cover - provider failures vary
                    response_queue.put((False, exc))

            worker = threading.Thread(target=request, name="audio-flow-read-script", daemon=True)
            worker.start()
            try:
                success, response = response_queue.get(timeout=7.0)
            except queue.Empty:
                # Do not make a listener wait on a provider outage every time.
                self._ai_cooldowns[cooldown_key] = time.monotonic() + 20.0
                log.warning("Audio Flow AI human reading timed out; using offline explainer.")
                return None
            if not success:
                raise response
            raw = str(response)
            cleaned = sanitize_explanation_text(raw)
            cleaned = re.sub(r"[`*#_]", "", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if self._is_safe_explanation(clean_text, cleaned):
                try:
                    text_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()[:32]
                    cached_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    storage.set_audio_summary_cache(cache_key, text_hash, f"human_read_{_READ_CACHE_VERSION}", model_id, cleaned, cached_at)
                except Exception:
                    pass
                return cleaned
        except Exception as exc:
            log.warning("Audio Flow AI human reading call failed (%s); will fall back to offline explainer.", exc)

        return None

    def transform_for_human_reading(
        self,
        text: str,
        context: str | None = None,
        allow_llm: bool = True,
    ) -> str:
        """Main entry point for Audio Flow Read Mode.

        Transforms selected text into an articulate, human-like explanatory presentation.
        When external AI is enabled and an API key is available, leverages the expert
        Human Narrator model with sub-second caching to deliver expressive, natural spoken
        reading that untangles stutters, clarifies intent, and expands acronyms without
        robotic third-person meta boilerplate.
        Gracefully falls back to high-quality offline rule-based speech processing.
        """
        if not text or not text.strip():
            return ""

        clean_text = text.strip()

        # Check user read mode setting
        read_mode = str(storage.get_setting("audio_flow_read_mode", "explanatory") or "explanatory").lower().strip()
        if read_mode == "verbatim":
            # Pure clean verbatim speech normalization
            return self.normalize_spoken_text(clean_text)

        # Check if external AI explainer is enabled
        allow_external = storage.get_setting("audio_flow_allow_external_ai", None)
        if allow_external is None:
            allow_external = storage.get_setting("exec_audio_summary_allow_external_ai", False)
        if isinstance(allow_external, str):
            allow_external = allow_external.strip().lower() in {"1", "true", "yes", "on"}
        else:
            allow_external = bool(allow_external)

        explainer_model = str(storage.get_setting("audio_flow_explainer_model", "") or "").strip()

        if allow_llm and allow_external:
            # Gemini is the default human-narrator path only when the user has
            # not chosen an explainer model. An explicit local choice must stay
            # local even when external AI is otherwise permitted.
            if not explainer_model:
                ai_read = self.read_with_ai(clean_text, context=context)
                if ai_read and len(ai_read) >= 10:
                    return ai_read
            elif not explainer_model.lower().startswith(("local/", "offline", "deterministic")):
                try:
                    ai_explanation = self.explain_with_ai(clean_text, context=context, model_ref=explainer_model)
                    if ai_explanation and len(ai_explanation) > 10:
                        return ai_explanation
                except Exception as e:
                    log.info("AI explainer model skipped, using offline explainer: %s", e)

        # High-quality offline conversational explanation transform
        return self.explain_offline(clean_text, context)


# Global singleton instance
audio_explainer = AudioExplainer()

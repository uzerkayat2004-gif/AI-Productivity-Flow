"""Spoken Human Explainer Engine for Audio Flow Read Mode.

Transforms raw selected text — chat messages, feedback, emails, technical documentation,
articles, code, or procedures — into natural, human-like explanatory narration.
Rather than reading raw characters mechanically like a robotic teleprompter, this engine
delivers the clarity, cadence, and conversational framing of a knowledgeable colleague
reading and explaining the content directly to the listener.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
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
        pass

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
        code_signals = ["def ", "class ", "import ", "return ", "function ", "const ", "let ", "var ", "public class "]
        if any(sig in clean_text for sig in code_signals) or ("\n    " in clean_text and "{" in clean_text):
            return local_spoken_summarizer.explain_conversationally(clean_text)

        # Step 4: Multi-sentence articles or documentation
        sentences = split_spoken_sentences(clean_text)
        if len(sentences) >= 3:
            topic = local_spoken_summarizer._extract_topic_from_text(clean_text)
            normalized_body = self.normalize_spoken_text(clean_text)
            return f"Here is an explanation of {topic}. {PAUSE_SECTION} {normalized_body}"

        # Step 5: Short / general text
        if len(clean_text.split()) <= 8:
            expanded = expand_spoken_abbreviations(clean_text)
            decluttered = declutter_spoken_text(expanded)
            if decluttered.lower() == clean_text.lower():
                return clean_text
            return self.normalize_spoken_text(clean_text)

        topic = local_spoken_summarizer._extract_topic_from_text(clean_text)
        normalized = self.normalize_spoken_text(clean_text)
        return f"Here is an explanation of {topic}. {PAUSE_SECTION} {normalized}"

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
            if result and result.strip():
                return self.normalize_spoken_text(result)
        except Exception as exc:
            log.warning("AI explanation generation failed (%s); falling back to offline explainer.", exc)

        return self.explain_offline(text, context)

    def read_with_ai(
        self,
        text: str,
        context: str | None = None,
        model_id: str = "gemini-2.5-flash",
    ) -> str | None:
        """Call Gemini to transform text into an articulate human explanatory reading with sub-second caching."""
        keys = storage.get_all_api_keys()
        gemini_key = keys.get("gemini")
        if not gemini_key:
            return None

        clean_text = text.strip()
        cache_key = hashlib.sha256(f"human_read_v2:{clean_text}".encode("utf-8")).hexdigest()[:32]
        try:
            cached_entry = storage.get_audio_summary_cache(cache_key)
            if cached_entry and cached_entry.get("summary_text"):
                log.info("Audio Flow human reading cache hit for key %s", cache_key[:16])
                return str(cached_entry["summary_text"])
        except Exception:
            pass

        try:
            from voice_flow.audio_summary import audio_summary_service
            prompt = build_human_reading_prompt(clean_text, context=context)
            raw = audio_summary_service._call_gemini(model_id, gemini_key, prompt)
            cleaned = sanitize_explanation_text(raw)
            cleaned = re.sub(r"[`*#_]", "", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if cleaned and len(cleaned) >= 5:
                try:
                    text_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()[:32]
                    cached_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    storage.set_audio_summary_cache(cache_key, text_hash, "human_read", model_id, cleaned, cached_at)
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
        allow_external = bool(allow_external)

        explainer_model = str(storage.get_setting("audio_flow_explainer_model", "") or "").strip()

        if allow_llm and allow_external:
            # 1. Try high-quality Gemini Human Narrator
            ai_read = self.read_with_ai(clean_text, context=context)
            if ai_read and len(ai_read) >= 10:
                return ai_read

            # 2. Check if a custom non-local explainer model was configured
            if explainer_model and not explainer_model.startswith("local/"):
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

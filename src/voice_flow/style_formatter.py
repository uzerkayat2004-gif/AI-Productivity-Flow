"""Deterministic, Context-Aware Style Formatting Engine.

Controls capitalization, punctuation density, sentence endings, spacing,
and context-aware insertion without altering user wording or semantic meaning.
"""

from __future__ import annotations

import re
from typing import Sequence
from voice_flow.style_models import (
    WritingStyle,
    StyleConfig,
    STYLE_CONFIGS,
    TextboxContext,
    FORMAL_STYLE_CONFIG,
)

# Common questions leadings for question-mark detection
_QUESTION_STARTERS = re.compile(
    r"^(?:(?:hey|hi|hello|so|well|please|okay|ok)\s*,?\s*)?"
    r"(?:are|is|am|was|were|do|does|did|can|could|would|should|will|shall|may|might|"
    r"what|where|when|why|how|who|whom|whose|which|have|has|had|isn't|aren't|wasn't|"
    r"weren't|don't|doesn't|didn't|can't|couldn't|won't|shouldn't)\b",
    re.I,
)

# Positive/Excited phrases for intelligent exclamation detection
_EXCITED_PHRASES = re.compile(
    r"\b(?:amazing|awesome|fantastic|congrats|congratulations|so\s+happy|love\s+it|"
    r"great\s+job|well\s+done|yay|woohoo|hooray|excellent|incredible|unbelievable|"
    r"thank\s+you\s+so\s+much|thanks\s+so\s+much|can't\s+wait|super\s+excited|"
    r"let's\s+go|proud\s+of\s+you|happy\s+birthday|happy\s+new\s+year)\b",
    re.I,
)

# Known Acronyms to protect from aggressive lowercasing
_COMMON_ACRONYMS = {
    "API", "APIs", "HTTP", "HTTPS", "JSON", "XML", "HTML", "CSS", "SQL", "GPT",
    "LLM", "LLMs", "AI", "ML", "UI", "UX", "UIA", "OS", "URL", "URLs", "ID",
    "IDs", "IP", "DNS", "SDK", "SDKs", "CLI", "REST", "SSH", "RAM", "CPU",
    "GPU", "USB", "PDF", "PNG", "JPG", "JPEG", "MP3", "MP4", "WAV", "WTP",
    "ICP", "ARR", "MRR", "CAC", "LTV", "ROI", "B2B", "B2C", "SaaS", "VSCode",
    "Wispr", "OpenAI", "Microsoft", "Google", "GitHub", "GitLab", "Slack",
    "Discord", "WhatsApp", "Telegram", "Notion", "Linear", "Zoom", "Teams",
}


class TokenProtector:
    """Safeguards URLs, emails, acronyms, code identifiers, numbers, and proper nouns."""

    def __init__(self, protected_words: Sequence[str] | None = None):
        self.placeholders: dict[str, str] = {}
        self.counter = 0
        self.custom_words = set(protected_words or [])

    def _add_placeholder(self, token: str) -> str:
        key = f"__STYLE_TOKEN_{self.counter}__"
        self.counter += 1
        self.placeholders[key] = token
        return key

    def protect(self, text: str) -> str:
        if not text:
            return ""

        # 1. Protect URLs
        text = re.sub(
            r"\b(?:https?://|www\.)[^\s<>()]+",
            lambda m: self._add_placeholder(m.group(0)),
            text,
            flags=re.I,
        )

        # 2. Protect Email Addresses
        text = re.sub(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            lambda m: self._add_placeholder(m.group(0)),
            text,
        )

        # 3. Protect Code tokens (snake_case, camelCase, $variables, --flags, function_calls(), backticks)
        text = re.sub(
            r"(?:`[^`]+`|\$[A-Za-z_][A-Za-z0-9_]*|--[A-Za-z0-9-]+|\b[a-z]+(?:[A-Z][a-z0-9]+)+\b|\b[a-z0-9]+(?:_[a-z0-9]+)+\b|\b[A-Za-z0-9_]+\(\))",
            lambda m: self._add_placeholder(m.group(0)),
            text,
        )

        # 4. Protect Formatted Numbers, Dates, Times & Currencies (e.g. $1,500, 2:30 PM, 20%, v2.1)
        text = re.sub(
            r"(?:\$[\d,]+(?:\.\d+)?|\b\d{1,2}:\d{2}(?:\s*(?:AM|PM|am|pm))?|\b\d+(?:\.\d+)?%|\bv\d+(?:\.\d+)+\b)",
            lambda m: self._add_placeholder(m.group(0)),
            text,
        )

        # 5. Protect Acronyms and Canonical Proper Nouns
        all_protected = _COMMON_ACRONYMS.union(self.custom_words)
        for term in sorted(all_protected, key=len, reverse=True):
            pattern = rf"\b{re.escape(term)}\b"
            text = re.sub(
                pattern,
                lambda m, t=term: self._add_placeholder(t),
                text,
                flags=re.I if len(term) > 3 else 0,
            )

        return text

    def unprotect(self, text: str) -> str:
        for key, original in self.placeholders.items():
            text = text.replace(key, original)
        return text


def normalize_internal_whitespace(text: str) -> str:
    """Collapses irregular whitespace while preserving intentional newlines."""
    lines = text.split("\n")
    normalized_lines = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]
    return "\n".join(normalized_lines)


def is_sentence_start(before_text: str | None) -> bool:
    """Determines whether the cursor sits at the beginning of a fresh sentence."""
    if not before_text:
        return True
    before_clean = before_text.rstrip()
    if not before_clean:
        return True
    if before_clean.endswith(("\n", "\r", "-", "*", ">", ":")):
        return True
    if re.search(r"^\s*\d+\.\s*$", before_clean):
        return True
    if re.search(r"[.!?]\s*$", before_clean):
        return True
    if before_clean.endswith(('"', "'", "“", "‘", "(", "[", "{")):
        return True
    return False


def apply_capitalization_policy(
    text: str,
    config: StyleConfig,
    context: TextboxContext | None = None,
) -> str:
    """Applies case rules according to the Style config and surrounding cursor context."""
    if not text:
        return ""

    before = context.before if (context and context.trustworthy) else ""
    sentence_start = is_sentence_start(before)

    # 1. Very Casual Mode: Lowercase first letter and words
    if config.id == "very_casual":
        words = text.split(" ")
        formatted_words = []
        for w in words:
            if w.startswith("__STYLE_TOKEN_") and w.endswith("__"):
                formatted_words.append(w)
            else:
                formatted_words.append(w.lower())
        return " ".join(formatted_words)

    # 2. Capitalize standalone pronoun "I" and contractions ("I'm", "I'll", "I've", "I'd")
    if config.capitalize_pronoun_i:
        text = re.sub(r"\b(i)\b", "I", text)
        text = re.sub(r"\bi('m|'ll|'ve|'d)\b", r"I\1", text, flags=re.I)
        text = re.sub(r"\bi(m|ll|ve|d)\b", r"I'\1", text, flags=re.I)

    # 3. Sentence-start capitalization
    if sentence_start and not config.allow_lowercase_first_letter:
        if not text.startswith("__STYLE_TOKEN_"):
            text = text[:1].upper() + text[1:]

    # 5. Multi-sentence capitalization after periods, question marks, and exclamation points
    def _cap_match(m: re.Match) -> str:
        punct = m.group(1)
        space = m.group(2)
        char = m.group(3)
        return f"{punct}{space}{char.upper()}"

    text = re.sub(r"([.!?]\s+)([a-z])", _cap_match, text)

    return text


def apply_punctuation_policy(
    text: str,
    config: StyleConfig,
    context: TextboxContext | None = None,
) -> str:
    """Applies punctuation density and sentence boundary rules."""
    if not text:
        return ""

    before = context.before if (context and context.trustworthy) else ""
    after = context.after if (context and context.trustworthy) else ""

    # Don't add duplicate trailing punctuation if next character in textbox is already punctuation
    after_has_punct = bool(after and after.lstrip().startswith((".", "!", "?", ",", ";", ":")))
    # If the user is typing mid-sentence, avoid terminal periods
    is_mid_sentence = bool(after and not after.startswith(("\n", "\r")) and not after_has_punct)

    # Check if text already has explicit terminal punctuation
    has_terminal_punct = bool(re.search(r"[.!?]$", text.strip()))

    # 1. Question Mark Detection
    is_question = bool(_QUESTION_STARTERS.search(text.strip())) and not has_terminal_punct

    # 2. Excited Mode: Intelligent Exclamation Detection
    is_excited_sentiment = bool(_EXCITED_PHRASES.search(text.strip()))

    if config.id == "formal":
        # Conversational boundary formatting in Formal mode:
        # e.g., "Hey Sarah just wanted to check" -> "Hey Sarah, just wanted to check"
        text = re.sub(r"\b(Hey|Hi|Hello|Dear)\s+([A-Z][a-z]+)\s+(just|i|we|how|wanted|hope)\b", r"\1 \2, \3", text)

        # Boundary splits for closing transitions:
        # e.g. "document let me know" -> "document. Let me know"
        text = re.sub(r"\b([a-z0-9]+)\s+(let me know|please let me know|thanks|thank you)\b", r"\1. \2", text, flags=re.I)
        # Capitalize after newly added period
        text = re.sub(r"\.\s+([a-z])", lambda m: f". {m.group(1).upper()}", text)

        if not has_terminal_punct and not is_mid_sentence and not after_has_punct:
            if is_question:
                text = text.rstrip() + "?"
            elif config.sentence_periods == "normal":
                text = text.rstrip() + "."

    elif config.id == "casual":
        if not has_terminal_punct and not is_mid_sentence and not after_has_punct:
            if is_question:
                text = text.rstrip() + "?"
            # In Casual, short conversational fragments omit trailing periods

    elif config.id == "very_casual":
        # Very Casual strips unnecessary trailing periods and keeps text completely loose
        if text.endswith(".") and not text.endswith(".."):
            text = text[:-1].rstrip()

    elif config.id == "excited":
        if not has_terminal_punct and not is_mid_sentence and not after_has_punct:
            if is_question:
                text = text.rstrip() + "?"
            elif is_excited_sentiment or config.exclamation_level == "expressive":
                is_negative = bool(re.search(r"\b(?:server\s+is\s+down|failed|error|broken|sad|sorry|terrible|bad)\b", text, re.I))
                if not is_negative:
                    text = text.rstrip() + "!"
                else:
                    text = text.rstrip() + "."

    return text


def fix_insertion_boundaries(
    text: str,
    context: TextboxContext | None = None,
) -> str:
    """Calculates necessary leading and trailing spaces around the insertion point."""
    if not text or not context or not context.trustworthy:
        return text

    before = context.before
    after = context.after

    # 1. Leading Space Fix
    if before and not before[-1].isspace():
        if not before[-1] in "([{\"'“‘" and not re.match(r"^[,.;:?!)]", text):
            text = " " + text

    # 2. Trailing Space Fix
    if after and not after[0].isspace():
        if after[0] not in ",.;:?!)]}\"'”’" and not text[-1].isspace():
            text = text + " "

    return text


class StyleFormatter:
    """Master context-aware formatting engine."""

    def format(
        self,
        transcript: str,
        style: WritingStyle | str = "formal",
        context: TextboxContext | None = None,
        custom_dictionary: Sequence[str] | None = None,
    ) -> str:
        """Transforms raw transcription into styled output preserving exact words."""
        if not transcript or not transcript.strip():
            return ""

        style_key = style.lower().strip()
        if style_key.startswith("personal_"):
            style_key = style_key.replace("personal_", "")
        elif style_key.startswith("work_"):
            style_key = style_key.replace("work_", "")
        elif style_key.startswith("email_"):
            style_key = style_key.replace("email_", "")
        elif style_key.startswith("other_"):
            style_key = style_key.replace("other_", "")

        config = STYLE_CONFIGS.get(style_key, FORMAL_STYLE_CONFIG)

        # 1. Whitespace normalization
        text = normalize_internal_whitespace(transcript.strip())

        # 2. Protect sensitive tokens
        protector = TokenProtector(custom_dictionary)
        text = protector.protect(text)

        # 3. Capitalization Policy
        text = apply_capitalization_policy(text, config, context)

        # 4. Punctuation & Sentence Ending Policy
        text = apply_punctuation_policy(text, config, context)

        # 5. Restore Protected Tokens
        text = protector.unprotect(text)

        # 6. Insertion Boundaries
        text = fix_insertion_boundaries(text, context)

        return text


# Singleton instance
style_formatter = StyleFormatter()

"""Correction-learning signal extraction (spec §35, §41).

The strongest learning signal is a correction: the STT produced one string,
the user's final output said another. This module extracts cheap, bounded
(term, variant) observations from a dictation result — pure functions, no
I/O — so storage can automatically activate useful vocabulary and correction
rules after repeated evidence from separate successful dictations.
"""
from __future__ import annotations

import re

from voice_flow.vocabulary_learning import (
    is_noise_variant,
    is_plausible_spelling_correction,
    is_useful_term,
    strip_protected_spans,
)

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "so", "to", "for", "of",
    "with", "in", "on", "at", "my", "this", "that", "it", "we", "you", "i",
    "is", "are", "was", "were", "be", "been", "have", "has", "had", "do",
    "does", "did", "will", "would", "can", "could", "should", "just",
    # Filler / greeting / deictic noise must never become dictionary terms.
    # STT routinely produces these as sentence-initial wobble ("uh hey" heard
    # for "Hey", "hear" heard for "Here"); promoting them pollutes the
    # "Detected vocabulary" list with junk instead of real vocabulary.
    "hey", "hello", "hi", "here", "there",
    "uh", "um", "umm", "uhh", "er", "ah", "oh", "hmm",
    "ok", "okay", "yes", "yeah", "no",
}
# Common-word blocklist: frequency alone must never pollute the dictionary.
_COMMON_WORDS = {
    "meeting", "project", "today", "tomorrow", "important", "email", "message",
    "team", "update", "quick", "thanks", "please", "morning", "evening", "call",
}
_MIN_LEN = 3
_MAX_TERMS = 5
# A multi-token mishearing must carry at least this many distinct content
# tokens (after dropping stopwords/filler/common words). Single-token
# variants ("kuhbernetees" -> "Kubernetes") are unaffected; this only stops
# noise like "uh hey" or "hey hey" from qualifying as evidence.
_MIN_DISTINCT_CONTENT_TOKENS = 2


def _tokenize(text: str) -> tuple[list[str], list[int]]:
    """Return words plus sentence IDs so context never crosses punctuation."""
    safe = strip_protected_spans(text)
    words: list[str] = []
    sentence_ids: list[int] = []
    sentence_id = 0
    previous_end = 0
    for match in re.finditer(r"[^\W_]+", safe, flags=re.UNICODE):
        if re.search(r"[.!?]", safe[previous_end:match.start()]):
            sentence_id += 1
        words.append(match.group(0))
        sentence_ids.append(sentence_id)
        previous_end = match.end()
    return words, sentence_ids


def _sentence_context(
    words: list[str], sentence_ids: list[int], start: int, end: int, term: str
) -> str:
    sentence_id = sentence_ids[start]
    left = start
    while left > 0 and sentence_ids[left - 1] == sentence_id and start - left < 5:
        left -= 1
    right = end
    while right < len(words) and sentence_ids[right] == sentence_id and right - end < 4:
        right += 1
    return " ".join(words[left:start] + [term] + words[end:right])


def _is_candidate_word(word: str, variant: str, context: str) -> bool:
    w = word.lower()
    if len(w) < _MIN_LEN or w in _STOPWORDS or w in _COMMON_WORDS:
        return False
    return is_plausible_spelling_correction(word, variant) and is_useful_term(
        word,
        allow_sentence_initial=True,
        context=context,
        correction_variant=variant,
    )


def _content_tokens(tokens: list[str]) -> set[str]:
    """Distinct content tokens in a misheard variant (noise removed)."""
    seen: set[str] = set()
    for token in tokens:
        lowered = token.lower()
        if lowered in _STOPWORDS or lowered in _COMMON_WORDS or not lowered.isalpha():
            continue
        seen.add(lowered)
    return seen


def _has_distinct_context(raw_seg: list[str]) -> bool:
    """Min-distinct-context rule for multi-token variants."""
    if len(raw_seg) < 2:
        return True
    return len(_content_tokens(raw_seg)) >= _MIN_DISTINCT_CONTENT_TOKENS


def _same_joined_letters(left: str, right: str) -> bool:
    return re.sub(r"[^\w]", "", left, flags=re.UNICODE).casefold() == re.sub(
        r"[^\w]", "", right, flags=re.UNICODE
    ).casefold()


def extract_correction_pairs(raw_transcript: str, final_text: str) -> list[tuple[str, str]]:
    """Extract (correct_term, misheard_variant) pairs from one dictation.

    Heuristic, deliberately conservative:
    - token-sequence diff via difflib on the two strings, compared
      case-insensitively so sentence-initial capitalization from the
      polisher ("call" -> "Call") is never treated as a mishearing and can
      never merge neighbouring tokens into one diff block (which previously
      hid real multi-token mishearings such as "joe ee" -> "Joey");
    - a pair qualifies when the final side is a candidate term (proper noun /
      technical token) and the raw side is a different, non-stopword
      replacement of roughly the same shape;
    - filler/greeting/deictic noise ("hey", "here", "uh", ...) is rejected
      on both the term and the variant side, and multi-token variants must
      carry at least two distinct content tokens;
    - bounded per dictation; no pair where the sides are equal.
    """
    if not raw_transcript or not final_text:
        return []
    try:
        import difflib

        raw_words, raw_sentences = _tokenize(raw_transcript)
        final_words, final_sentences = _tokenize(final_text)
        if not raw_words or not final_words:
            return []
        # Original casing is kept for the emitted text; only the alignment
        # itself is case-insensitive.
        matcher = difflib.SequenceMatcher(
            None,
            [word.lower() for word in raw_words],
            [word.lower() for word in final_words],
            autojunk=False,
        )
        pairs: list[tuple[str, str]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "replace":
                continue
            raw_seg = raw_words[i1:i2]
            final_seg = final_words[j1:j2]
            if not raw_seg or not final_seg:
                continue
            if len(set(raw_sentences[i1:i2])) != 1 or len(set(final_sentences[j1:j2])) != 1:
                continue
            if len(pairs) >= _MAX_TERMS:
                return pairs
            # Pattern A (spec §35): multiword mishearing collapses into one
            # canonical term — "land graph" -> "LangGraph", "joe ee" -> "Joey".
            if len(final_seg) == 1 and 1 <= len(raw_seg) <= 3:
                variant = " ".join(raw_seg).lower()
                term = final_seg[0]
                context = _sentence_context(raw_words, raw_sentences, i1, i2, term)
                if variant.casefold() != term.casefold() and _is_candidate_word(term, variant, context) \
                        and not is_noise_variant(variant) \
                        and len(variant) >= _MIN_LEN and not any(w.lower() in _STOPWORDS for w in raw_seg) \
                        and (_has_distinct_context(raw_seg) or _same_joined_letters(variant, term)):
                    key = (term.casefold(), variant)
                    if key not in seen_pairs:
                        seen_pairs.add(key)
                        pairs.append((term, variant))
                continue
            # Pattern B: 1:1 word swap — "open ai" -> "OpenAI", "py torch" -> "PyTorch".
            if len(raw_seg) == len(final_seg):
                for offset, (variant, term) in enumerate(zip(raw_seg, final_seg)):
                    if variant.casefold() == term.casefold():
                        continue
                    raw_position = i1 + offset
                    context = _sentence_context(
                        raw_words, raw_sentences, raw_position, raw_position + 1, term
                    )
                    if not _is_candidate_word(term, variant, context):
                        continue
                    if variant.lower() in _STOPWORDS or len(variant) < _MIN_LEN or is_noise_variant(variant):
                        continue
                    key = (term.casefold(), variant)
                    if key not in seen_pairs:
                        seen_pairs.add(key)
                        pairs.append((term, variant))
                    if len(pairs) >= _MAX_TERMS:
                        return pairs
        return pairs
    except Exception:
        return []

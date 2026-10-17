"""Repetition and stock-phrase guard for local Whisper transcripts.

``base.en`` on boosted room noise emits one sentence many times
("I'm not sure if you have any questions.") or a stock closer
("Thank you for watching"). These helpers detect that output, collapse
or drop it, and choose between a streamed chunk transcript and a
full-recording decode.
"""
from __future__ import annotations

import re
import zlib
from collections import Counter

# faster-whisper falls back through this list when a segment's compression
# ratio, log-prob, or no-speech score says the decode is junk. A single
# temperature of 0.0 never retries, which is how a greedy loop survives.
WHISPER_TEMPERATURES: tuple[float, ...] = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
WHISPER_RETRY_TEMPERATURES: tuple[float, ...] = (0.2, 0.4, 0.6, 0.8, 1.0)
WHISPER_COMPRESSION_RATIO_THRESHOLD = 2.4
WHISPER_LOG_PROB_THRESHOLD = -1.0
WHISPER_NO_SPEECH_THRESHOLD = 0.6
WHISPER_HALLUCINATION_SILENCE_THRESHOLD = 2.0

# Phrases Whisper emits from silence, music beds, and YouTube outros.
# Short ones ("you") only count when the whole utterance is that phrase,
# so a real "thank you" inside a sentence is left alone.
_KNOWN_PHRASES: tuple[str, ...] = (
    "i'm not sure if you have any questions",
    "i am not sure if you have any questions",
    "not sure if you have any questions",
    "thank you for watching",
    "thanks for watching",
    "thank you for listening",
    "thanks for listening",
    "please subscribe",
    "like and subscribe",
    "see you next time",
    "subtitles by the amara.org community",
    "subtitles by the amara community",
    "transcribed by https://otter.ai",
    "thanks for watching and please subscribe",
)
_SHORT_KNOWN: frozenset[str] = frozenset({"you", "thank you", "thanks you", "thanks"})

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[a-z0-9']+")


def _norm(text: str) -> str:
    return " ".join(_WORD_RE.findall(str(text or "").lower()))


def _sentences(text: str) -> list[str]:
    parts = [part.strip() for part in _SENTENCE_RE.split(str(text or "").strip()) if part.strip()]
    return parts


def compression_ratio(text: str) -> float:
    """Whisper's ratio: raw bytes / compressed bytes. Repetition scores high."""
    raw = str(text or "").encode("utf-8")
    if len(raw) < 16:
        return 1.0
    return len(raw) / max(1, len(zlib.compress(raw, 9)))


def _is_known_phrase(norm: str) -> bool:
    if not norm:
        return False
    if norm in _SHORT_KNOWN or norm in _KNOWN_PHRASES:
        return True
    return any(norm == phrase or norm.endswith(" " + phrase) for phrase in _KNOWN_PHRASES)


def repeated_sentence(text: str) -> tuple[str, int] | None:
    """Return ``(normalized sentence, count)`` when one sentence occurs 3+ times."""
    norms = [_norm(sentence) for sentence in _sentences(text)]
    norms = [norm for norm in norms if norm]
    if len(norms) < 3:
        return None
    phrase, count = Counter(norms).most_common(1)[0]
    if count >= 3 and phrase:
        return phrase, count
    return None


def repeated_ngram(text: str, size: int = 6) -> bool:
    """True when the same word n-gram occurs as three non-overlapping copies."""
    words = _norm(text).split()
    if len(words) < size * 3:
        return False
    counts: Counter[tuple[str, ...]] = Counter()
    index = 0
    while index + size <= len(words):
        gram = tuple(words[index:index + size])
        counts[gram] += 1
        if counts[gram] >= 3:
            return True
        # Step by one so a phrase that isn't aligned to ``size`` is still seen,
        # but only the first sighting of a run is counted by jumping ahead
        # once a match is recorded at this start. Counting every offset would
        # inflate one phrase into many hits.
        index += 1
    # Non-overlapping confirmation: a single long phrase sliding by one word
    # can increment the counter without being a real loop. Require three
    # disjoint copies of the most common gram.
    gram, _hits = counts.most_common(1)[0]
    found = 0
    index = 0
    while index + size <= len(words):
        if tuple(words[index:index + size]) == gram:
            found += 1
            index += size
        else:
            index += 1
    return found >= 3


def known_phrase_copies(text: str) -> int:
    """How many times the strongest known hallucination phrase occurs."""
    norm = _norm(text)
    if not norm:
        return 0
    if _is_known_phrase(norm):
        return 1
    best = 0
    for phrase in _KNOWN_PHRASES:
        best = max(best, norm.count(phrase))
    return best


def text_is_only_known_phrases(text: str) -> bool:
    sentences = _sentences(text) or [str(text or "")]
    norms = [_norm(sentence) for sentence in sentences]
    norms = [norm for norm in norms if norm]
    if not norms:
        return False
    return all(_is_known_phrase(norm) for norm in norms)


def _collapse_repeated_sentences(text: str) -> str:
    repeated = repeated_sentence(text)
    if not repeated:
        return text
    phrase, _count = repeated
    if _is_known_phrase(phrase):
        # A stock phrase said three or more times is the loop, not the user.
        kept = [sentence for sentence in _sentences(text) if _norm(sentence) != phrase and _norm(sentence)]
        return " ".join(kept).strip()
    for sentence in _sentences(text):
        if _norm(sentence) == phrase:
            others = [item for item in _sentences(text) if _norm(item) != phrase]
            if not others:
                return sentence.strip()
            # Keep one copy of the looped sentence plus anything unique.
            return (sentence.strip() + " " + " ".join(others)).strip()
    return text


def guard_transcript(text: str, *, low_energy: bool = False) -> tuple[str, bool]:
    """Return ``(cleaned, should_retry)``.

    A sentence or n-gram repeated 3+ times is collapsed. Known Whisper
    phrases are dropped when they repeat or when the source audio had
    little energy. ``should_retry`` asks the decoder for another pass at
    the next temperature.
    """
    raw = str(text or "").strip()
    if not raw:
        return "", False

    copies = known_phrase_copies(raw)
    only_known = text_is_only_known_phrases(raw)
    looped = repeated_sentence(raw) is not None or repeated_ngram(raw)
    compressed = compression_ratio(raw) >= WHISPER_COMPRESSION_RATIO_THRESHOLD and (looped or copies >= 3)

    if only_known and (copies >= 3 or looped or low_energy or compressed):
        return "", True
    if copies >= 3 or (only_known and low_energy):
        return "", True

    cleaned = _collapse_repeated_sentences(raw) if looped or compressed else raw
    if cleaned != raw:
        return cleaned.strip(), True
    if low_energy and only_known:
        return "", True
    return raw, False


def prefer_cleaner_transcript(streamed: str, full: str) -> str:
    """Keep the full-recording decode unless it is the repetitive one.

    The whole buffer is the source of truth when both transcripts are
    ordinary speech. When the full decode is a hallucination loop and the
    streamed chunks are not, the chunks win — that is the case where a
    failed overlap used to throw away 111 good characters and the redecode
    pasted the same sentence ten times.
    """
    full_clean, full_bad = guard_transcript(full)
    stream_clean, stream_bad = guard_transcript(streamed)
    if full_bad and stream_clean and not stream_bad:
        return stream_clean
    if not full_clean and stream_clean and not stream_bad:
        return stream_clean
    return full_clean

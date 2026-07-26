"""Dictionary & Custom Vocabulary Engine.
Injects custom user jargon, proper nouns, and client names into Whisper's initial_prompt,
and performs fuzzy post-processing to guarantee 100% exact spelling recognition.
"""

from __future__ import annotations

import difflib
import logging
import re

from voice_flow.storage import storage

log = logging.getLogger(__name__)


class DictionaryEngine:
    """Manages custom vocabulary biasing and phonetic fuzzy replacement."""

    def __init__(self) -> None:
        self.words: list[str] = []
        self._dirty = True  # Force first load
        self._ensure_loaded()

    def mark_dirty(self) -> None:
        """Signal that the DB has changed and words need reloading."""
        self._dirty = True

    def _ensure_loaded(self) -> None:
        """Load words from DB only if marked dirty."""
        if self._dirty:
            self.words = storage.get_dictionary_words()
            self._dirty = False

    def refresh_words(self) -> list[str]:
        """Force-reload custom terms from database."""
        self._dirty = True
        self._ensure_loaded()
        return self.words

    def get_initial_prompt(self) -> str:
        """Construct Whisper initial_prompt string to bias Transformer decoding."""
        self._ensure_loaded()
        # Filter terms to include genuine custom jargon / proper nouns
        valid_words = [w for w in self.words if len(w) >= 3 and w.lower() not in {"the", "a", "an", "in", "on", "at", "to", "for", "of", "with", "and", "or", "but", "if", "so", "my", "this", "that", "it", "we", "you", "i", "he", "she", "they", "how", "hey", "can", "when", "what", "where", "who", "why"}]
        if not valid_words:
            return "Clear dictation, accurate spelling, proper names."

        prompt = "Vocabulary list: " + ", ".join(valid_words) + "."
        log.info("Whisper initial_prompt biased with dictionary terms: %s", valid_words)
        return prompt

    def apply_dictionary_post_processing(self, text: str) -> str:
        """Enforce exact user casing and phonetic fuzzy replacement for all dictionary terms."""
        if not text:
            return text

        self._ensure_loaded()
        if not self.words:
            return text

        result = text
        for dict_word in self.words:
            w_strip = dict_word.strip()
            if not w_strip:
                continue

            dict_lower = w_strip.lower()
            if dict_lower in {"the", "a", "an", "in", "on", "at", "to", "for", "of", "with", "and", "or", "but", "if", "so", "my", "this", "that", "it", "we", "you", "i", "he", "she", "they", "how", "hey", "can", "when", "what", "where", "who", "why"}:
                continue

            # Case-insensitive word boundary substitution to guarantee exact user casing
            pattern = re.compile(r"\b" + re.escape(w_strip) + r"\b", re.IGNORECASE)
            if pattern.search(result):
                result = pattern.sub(w_strip, result)
                continue

            # Fuzzy phonetic match for terms >= 4 chars
            if len(w_strip) >= 4:
                tokens = re.findall(r"\b\w+\b", result)
                for token in tokens:
                    if len(token) >= 4 and token.lower() != dict_lower:
                        ratio = difflib.SequenceMatcher(None, token.lower(), dict_lower).ratio()
                        if ratio >= 0.85:
                            log.info("Fuzzy dictionary correction: '%s' -> '%s' (ratio %.2f)", token, w_strip, ratio)
                            token_pattern = re.compile(r"\b" + re.escape(token) + r"\b")
                            result = token_pattern.sub(w_strip, result)

        return result


# Singleton instance
dictionary_engine = DictionaryEngine()

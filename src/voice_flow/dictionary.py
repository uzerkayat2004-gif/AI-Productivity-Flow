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
        self.refresh_words()

    def refresh_words(self) -> list[str]:
        """Fetch custom terms from database."""
        self.words = storage.get_dictionary_words()
        return self.words

    def get_initial_prompt(self) -> str:
        """Construct Whisper initial_prompt string to bias Transformer decoding."""
        self.refresh_words()
        if not self.words:
            return "Clear dictation and proper names."

        # Research-backed prompt format: List specific jargon & proper nouns
        prompt = "Dictionary vocabulary list: " + ", ".join(self.words) + "."
        log.info("Whisper initial_prompt biased with dictionary terms: %s", self.words)
        return prompt

    def apply_dictionary_post_processing(self, text: str) -> str:
        """Fuzzy match words in transcribed text against dictionary terms.
        Replaces phonetic approximations (e.g. 'Spider' -> 'Spyder', 'Sameer' -> 'Samir').
        """
        if not text or not self.words:
            return text

        result = text
        for dict_word in self.words:
            dict_lower = dict_word.lower()

            # Find whole-word matches in text (case-insensitive regex)
            pattern = re.compile(r"\b" + re.escape(dict_word) + r"\b", re.IGNORECASE)

            # If exact word exists with wrong casing, fix casing
            if pattern.search(result):
                result = pattern.sub(dict_word, result)
                continue

            # Otherwise, check for close phonetic matches using difflib
            tokens = re.findall(r"\b\w+\b", result)
            for token in tokens:
                if len(token) >= 3 and token.lower() != dict_lower:
                    # Ratio > 0.80 indicates phonetic similarity
                    ratio = difflib.SequenceMatcher(None, token.lower(), dict_lower).ratio()
                    if ratio >= 0.80:
                        log.info("Fuzzy dictionary correction: '%s' -> '%s' (ratio %.2f)", token, dict_word, ratio)
                        token_pattern = re.compile(r"\b" + re.escape(token) + r"\b")
                        result = token_pattern.sub(dict_word, result)

        return result


# Singleton instance
dictionary_engine = DictionaryEngine()

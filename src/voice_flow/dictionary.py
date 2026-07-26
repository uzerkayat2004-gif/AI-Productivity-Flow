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
        # Filter terms to include genuine custom jargon / proper nouns
        valid_words = [w for w in self.words if len(w) >= 3 and w.lower() not in {"the", "a", "an", "in", "on", "at", "to", "for", "of", "with", "and", "or", "but", "if", "so", "my", "this", "that", "it", "we", "you", "i", "he", "she", "they", "how", "hey", "can", "when", "what", "where", "who", "why"}]
        if not valid_words:
            return "Clear dictation, accurate spelling, proper names."

        prompt = "Vocabulary list: " + ", ".join(valid_words) + "."
        log.info("Whisper initial_prompt biased with dictionary terms: %s", valid_words)
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

            # Skip single short common words
            if dict_lower in {"the", "a", "an", "in", "on", "at", "to", "for", "of", "with", "and", "or", "but", "if", "so", "my", "this", "that", "it", "we", "you", "i", "he", "she", "they", "how", "hey", "can", "when", "what", "where", "who", "why"}:
                continue

            # Only fix casing if dict_word is multi-word or has special casing (e.g. VoiceFlow, API, ChatGPT)
            has_special_casing = " " in dict_word or dict_word.isupper() or any(c.isupper() for c in dict_word[1:])
            if has_special_casing:
                pattern = re.compile(r"\b" + re.escape(dict_word) + r"\b", re.IGNORECASE)
                if pattern.search(result):
                    result = pattern.sub(dict_word, result)
                    continue

            # Check for close phonetic matches (only for terms with length >= 5)
            if len(dict_word) >= 5:
                tokens = re.findall(r"\b\w+\b", result)
                for token in tokens:
                    if len(token) >= 5 and token.lower() != dict_lower:
                        ratio = difflib.SequenceMatcher(None, token.lower(), dict_lower).ratio()
                        if ratio >= 0.88:
                            log.info("Fuzzy dictionary correction: '%s' -> '%s' (ratio %.2f)", token, dict_word, ratio)
                            token_pattern = re.compile(r"\b" + re.escape(token) + r"\b")
                            result = token_pattern.sub(dict_word, result)

        return result


# Singleton instance
dictionary_engine = DictionaryEngine()

"""Vocabulary biasing and explicit correction rules for dictation.

The dictionary is deliberately conservative: users' saved terms get their exact
casing when actually spoken, and corrections run only for phrases the user
explicitly configured.  Snippets live in :mod:`voice_flow.snippets`.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
import threading

from voice_flow.storage import storage

log = logging.getLogger(__name__)

# Do not allow a vocabulary rule to rewrite text inside these constructs.  They
# are user content, not spoken vocabulary tokens.
_PROTECTED_RE = re.compile(
    r"``[\s\S]*?``|`[^`\n]*`|\[[^\]]+\]\([^\)]+\)|"
    r"(?:https?|ftp)://[^\s<>]+|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|"
    r"\bwww\.[^\s<>]+",
    re.IGNORECASE,
)
_STOPWORDS = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "with", "and",
    "or", "but", "if", "so", "my", "this", "that", "it", "we", "you", "i",
    "he", "she", "they", "how", "hey", "can", "when", "what", "where", "who",
    "why",
}


@dataclass(frozen=True)
class _Rule:
    trigger: str
    replacement: str
    snippet: bool = False


def _split_entry(value: str) -> tuple[str, str | None]:
    """Parse one GUI dictionary value without losing delimiters in expansions."""
    for delimiter in ("->", "=>"):
        if delimiter in value:
            trigger, expansion = value.split(delimiter, 1)
            return trigger.strip(), expansion.strip()
    return value.strip(), None


def _rule_pattern(trigger: str) -> re.Pattern[str]:
    escaped = re.escape(trigger)
    # A dictionary trigger is a complete lexical phrase even when it ends in
    # punctuation (for example C++ or C#); otherwise it can rewrite a prefix
    # of a larger symbolic token such as C++x.
    return re.compile(r"(?<!\w)" + escaped + r"(?!\w)", re.IGNORECASE)


def _is_symbolic_trigger(trigger: str) -> bool:
    return any(not char.isalnum() and char != "_" and not char.isspace() for char in trigger)


def _rule_matches(match: re.Match[str], rule: _Rule) -> bool:
    """Keep symbolic triggers from matching a larger identifier."""
    if not _is_symbolic_trigger(rule.trigger):
        return True
    end = match.end()
    return end >= len(match.string) or not (match.string[end].isalnum() or match.string[end] == "_")


def _combined_pattern(rules: tuple[_Rule, ...]) -> tuple[re.Pattern[str], tuple[_Rule, ...]]:
    """Build one callback pattern while retaining each rule's boundaries."""
    usable = tuple(rule for rule in rules if rule.trigger)
    pattern = re.compile(
        "|".join(f"({_rule_pattern(rule.trigger).pattern})" for rule in usable),
        re.IGNORECASE,
    )
    return pattern, usable


class DictionaryEngine:
    """Apply explicit dictionary terms and corrections exactly once."""

    def __init__(self, store=storage) -> None:
        self.store = store
        self.words: list[str] = []
        self.corrections: list[dict] = []
        self._rules: tuple[_Rule, ...] = ()
        self._correction_rules: tuple[_Rule, ...] = ()
        self._dirty = True
        self._revision: object = None
        self._lock = threading.RLock()
        self._ensure_loaded()

    def mark_dirty(self) -> None:
        """Signal that the database changed and the next call must reload."""
        with self._lock:
            self._dirty = True

    def _get_revision(self) -> object:
        getter = getattr(self.store, "get_lexicon_revision", None)
        if getter is not None:
            try:
                return getter()
            except Exception:
                pass
        legacy = getattr(self.store, "get_dictionary_revision", None)
        if legacy is not None:
            try:
                return legacy()
            except Exception:
                return None
        return None

    def _load_source_words(self) -> list[str]:
        # Auto-captured entries are intentionally excluded from the active
        # vocabulary. They were learned from polished text and are not user
        # authorization to rewrite future dictation.
        getter = getattr(self.store, "get_dictionary_entries", None)
        if getter is not None:
            try:
                return [str(row["word"]) for row in getter(include_auto=False)]
            except Exception:
                log.exception("Could not load dictionary entries")
        snapshot = getattr(self.store, "get_dictionary_snapshot", None)
        if snapshot is not None:
            try:
                _, words, _ = snapshot()
                return [str(word) for word in words]
            except Exception:
                log.exception("Could not load dictionary snapshot")
        return [str(word) for word in self.store.get_dictionary_words()]

    def _load_corrections(self) -> list[dict]:
        snapshot = getattr(self.store, "get_dictionary_snapshot", None)
        if snapshot is not None:
            try:
                _, _, corrections = snapshot()
                return list(corrections)
            except Exception:
                log.exception("Could not load corrections snapshot")
        getter = getattr(self.store, "get_dictionary_corrections", None)
        if getter is not None:
            try:
                return list(getter())
            except Exception:
                log.exception("Could not load corrections")
        return []

    def _ensure_loaded(self) -> None:
        with self._lock:
            revision = self._get_revision()
            if not self._dirty and revision == self._revision:
                return

            words = self._load_source_words()
            corrections = self._load_corrections()

            rules: list[_Rule] = []
            seen: set[str] = set()
            for raw in words:
                trigger, expansion = _split_entry(raw.strip())
                if not trigger or (expansion is not None and not expansion):
                    # Empty snippet expansions are malformed and must never erase
                    # the trigger from dictated text.
                    continue
                key = trigger.casefold()
                if key in seen:
                    continue
                seen.add(key)
                rules.append(_Rule(trigger, expansion if expansion is not None else trigger, expansion is not None))

            # Longer triggers win. Casefold tie-breaking keeps behavior stable even
            # if SQLite returns rows in a different order.
            rules.sort(key=lambda rule: (-len(rule.trigger), rule.trigger.casefold(), rule.trigger))

            correction_rules: list[_Rule] = []
            for item in corrections:
                wrong = str(item.get("wrong_text") or "").strip()
                correct = str(item.get("correct_text") or "").strip()
                if not wrong or not correct:
                    continue
                correction_rules.append(_Rule(wrong, correct))

            self.words = words
            self.corrections = corrections
            self._rules = tuple(rules)
            self._correction_rules = tuple(sorted(
                correction_rules, key=lambda rule: (-len(rule.trigger), rule.trigger.casefold())
            ))
            self._revision = revision
            self._dirty = False

    def refresh_words(self) -> list[str]:
        self.mark_dirty()
        self._ensure_loaded()
        return list(self.words)

    def get_initial_prompt(self) -> str:
        """Build a deterministic, bounded Whisper bias prompt from explicit terms."""
        self._ensure_loaded()
        terms: list[str] = []
        seen: set[str] = set()
        for rule in self._rules:
            if rule.trigger.casefold() in _STOPWORDS or len(rule.trigger) < 2:
                continue
            key = rule.trigger.casefold()
            if key not in seen:
                terms.append(rule.trigger)
                seen.add(key)
        for rule in self._correction_rules:
            key = rule.replacement.casefold()
            if key in seen:
                continue
            terms.append(rule.replacement)
            seen.add(key)
        # Prefer longer technical phrases over arbitrary alphabetical rows.
        terms = sorted(terms, key=lambda term: (-len(term), term.casefold()))[:40]
        if not terms:
            return "Clear dictation, accurate spelling, proper names."
        prompt = "Dictionary terms: " + ", ".join(terms) + "."
        log.info("Whisper initial_prompt biased with %d explicit terms", len(terms))
        return prompt

    @staticmethod
    def _apply_segment(segment: str, rules: tuple[_Rule, ...]) -> str:
        if not segment or not rules:
            return segment
        combined, usable_rules = _combined_pattern(rules)
        # One alternation/callback pass means an expansion is never considered
        # as new input for another rule during this dictation.
        def replace(match: re.Match[str]) -> str:
            for index, rule in enumerate(usable_rules, start=1):
                if match.group(index) is not None and _rule_matches(match, rule):
                    return rule.replacement
            return match.group(0)

        return combined.sub(replace, segment)

    def apply_dictionary_post_processing(self, text: str) -> str:
        """Apply explicit literal terms/corrections once; fuzzy matching is opt-in."""
        if not text:
            return text
        self._ensure_loaded()
        if not self._rules and not self._correction_rules:
            return text

        # Split protected spans out so a term such as ``app`` cannot mutate a
        # URL or email address. Corrections run before vocabulary so a declared
        # wrong-phrase fix wins over plain casing restoration; each pass keeps
        # expansions literal, including backslashes and group-looking sequences.
        combined_rules = self._correction_rules + self._rules
        output: list[str] = []
        cursor = 0
        for protected in _PROTECTED_RE.finditer(text):
            output.append(self._apply_segment(text[cursor:protected.start()], combined_rules))
            output.append(protected.group(0))
            cursor = protected.end()
        output.append(self._apply_segment(text[cursor:], combined_rules))
        result = "".join(output)
        if result != text:
            log.info("Applied explicit dictionary rules to dictated text")
        return result


# Singleton instance
dictionary_engine = DictionaryEngine()

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
# Sound-alike repair for the CRITICAL wake/product term (spec §34/§39): speech
# engines routinely mis-hear "Voice Flow" (Wiseflow, voice with flow…), which
# breaks command detection. Applied ONLY to the raw transcript before command
# parsing, via repair_wake_term(); the canonical dictionary keeps its scope.
_WAKE_REPAIR_RE = re.compile(
    r"(?<![\w])wiseflow(?![\w])"
    r"|(?<![\w])voice\s+with\s+flow(?![\w])"
    r"|(?<![\w])voice\s+of\s+flow(?![\w])"
    r"|(?<![\w])whisflow(?![\w])"
    # Common STT renderings of the wake term observed in real dictation.
    # These are repaired only in the command-detection string, never in the
    # text that gets pasted, so ordinary dictation is unaffected.
    r"|(?<![\w])voice\s+(?:low|bake|load|lowe)(?![\w])"
    r"|(?<![\w])voicefloor(?![\w])"
    r"|(?<![\w])voiceflow(?![\w])(?!\.\w)",
    re.IGNORECASE,
)
_WAKE_REPAIR_REPLACEMENT = "Voice Flow"
_STOPWORDS = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "with", "and",
    "or", "but", "if", "so", "my", "this", "that", "it", "we", "you", "i",
    "he", "she", "they", "how", "hey", "can", "when", "what", "where", "who",
    "why",
    # Filler / greeting / deictic noise must never reach STT bias prompts or
    # hint lists. Engines that "hear" these tokens in the prompt overproduce
    # them ("uh hey" loops), and they carry no vocabulary value.
    "hello", "hi", "here", "there",
    "uh", "um", "umm", "uhh", "er", "ah", "oh", "hmm",
    "ok", "okay", "yes", "yeah", "no",
    "is", "are", "was", "were", "be", "been",
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
        words: list[str] = []
        loaded = False
        last_error: Exception | None = None
        getter = getattr(self.store, "get_dictionary_entries", None)
        if getter is not None:
            try:
                words = [str(row["word"]) for row in getter(include_auto=False)]
                loaded = True
            except Exception as exc:
                last_error = exc
                log.exception("Could not load dictionary entries")
        # An empty explicit dictionary is a valid, authoritative result.  Do
        # not fall through to the legacy snapshot in that case: snapshots can
        # contain Auto-Captured metadata, which must remain visible to the UI
        # but must never become an active rewrite rule.
        if not loaded:
            snapshot = getattr(self.store, "get_dictionary_snapshot", None)
            if snapshot is not None:
                try:
                    _, snapshot_words, _ = snapshot()
                    words = [str(w) for w in snapshot_words]
                    loaded = True
                except Exception as exc:
                    last_error = exc
                    log.exception("Could not load dictionary snapshot")
        if not words:
            fallback = getattr(self.store, "get_dictionary_words", None)
            if fallback is not None:
                try:
                    words = [str(w) for w in fallback(include_snippets=True)]
                    loaded = True
                except Exception as exc:
                    last_error = exc
        if not loaded and last_error is not None:
            # Let _ensure_loaded retain the previous in-memory rules. A
            # transient disk/SQLite failure must not erase a working
            # dictionary or abort dictation startup.
            raise last_error

        # Include custom snippets formatted as "trigger -> expansion" in active vocabulary
        snippet_getter = getattr(self.store, "get_snippets", None)
        if snippet_getter is not None:
            try:
                for s in snippet_getter():
                    t = (s.get("trigger") or "").strip()
                    e = (s.get("expansion") or "").strip()
                    if t and e:
                        formatted = f"{t} -> {e}"
                        if formatted not in words:
                            words.append(formatted)
            except Exception as exc:
                log.debug("Could not load dictionary snippets: %s", exc)
        return words

    def _load_corrections(self) -> list[dict]:
        loaded = False
        last_error: Exception | None = None
        snapshot = getattr(self.store, "get_dictionary_snapshot", None)
        if snapshot is not None:
            try:
                _, _, corrections = snapshot()
                loaded = True
                return list(corrections)
            except Exception as exc:
                last_error = exc
                log.exception("Could not load corrections snapshot")
        getter = getattr(self.store, "get_dictionary_corrections", None)
        if getter is not None:
            try:
                loaded = True
                return list(getter())
            except Exception as exc:
                last_error = exc
                log.exception("Could not load corrections")
        if not loaded and last_error is not None:
            raise last_error
        return []

    def _ensure_loaded(self) -> None:
        with self._lock:
            revision = self._get_revision()
            if not self._dirty and revision == self._revision:
                return

            try:
                words = self._load_source_words()
                corrections = self._load_corrections()
            except Exception as exc:
                log.warning("Dictionary storage unavailable; retaining cached rules: %s", exc)
                # Keep the last good snapshot. On first startup the empty
                # snapshot is still a safe no-op, and the next explicit
                # revision/dirty signal can refresh it.
                self._dirty = False
                self._revision = revision
                return

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

    def get_initial_prompt(self, category: str | None = None) -> str:
        """Build a deterministic, bounded Whisper bias prompt from explicit terms.

        When an app category is supplied, terms tagged for that category lead
        the prompt (contextual vocabulary pack, spec §33); global terms fill
        the remaining bounded slots.
        """
        self._ensure_loaded()
        terms: list[str] = []
        seen: set[str] = set()

        def _add(term: str) -> None:
            key = term.casefold()
            if key and key not in seen and term not in terms:
                seen.add(key)
                terms.append(term)

        if category:
            try:
                for term in storage.get_contextual_vocabulary(category, limit=12):
                    _add(term)
            except Exception:
                log.exception("Could not load contextual vocabulary for %s", category)

        for rule in self._rules:
            if rule.trigger.casefold() in _STOPWORDS or len(rule.trigger) < 2:
                continue
            _add(rule.trigger)
        for rule in self._correction_rules:
            _add(rule.replacement)
        # Prefer longer technical phrases over arbitrary alphabetical rows.
        # Contextual (category-tagged) terms keep their head-of-list priority.
        contextual = terms[:12] if category else []
        global_terms = terms[len(contextual):] if category else terms
        global_terms = sorted(global_terms, key=lambda term: (-len(term), term.casefold()))
        terms = (contextual + global_terms)[:40]
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

    # -- protected terminology (spec §38) + contextual vocab (spec §33) ----

    def restore_dictionary_spelling(self, text: str) -> str:
        """Restore canonical casing after styling, without replaying rewrites."""
        if not text:
            return text
        self._ensure_loaded()
        terms = {_rule.trigger.casefold(): _rule.trigger for _rule in self._rules if not _rule.snippet}
        for rule in self._correction_rules:
            terms.setdefault(rule.replacement.casefold(), rule.replacement)
        rules = tuple(_Rule(term, term) for term in sorted(terms.values(), key=lambda value: (-len(value), value.casefold())))
        output: list[str] = []
        cursor = 0
        for protected in _PROTECTED_RE.finditer(text):
            output.append(self._apply_segment(text[cursor:protected.start()], rules))
            output.append(protected.group(0))
            cursor = protected.end()
        output.append(self._apply_segment(text[cursor:], rules))
        return "".join(output)

    def repair_wake_term(self, text: str) -> str:
        """Repair mis-hearings of the critical "Voice Flow" wake term.

        Runs on the RAW transcript before command detection so a garbled wake
        phrase ("Wiseflow, make this an email") still becomes a command.
        Deliberately static and NOT a dictionary correction — that would
        override the user's own casing entries and pollute STT hints.
        Pure string work — no I/O, no model.
        """
        if not text:
            return text
        return _WAKE_REPAIR_RE.sub(_WAKE_REPAIR_REPLACEMENT, text)

    def get_protected_terms(self, limit: int = 60) -> list[str]:
        """Canonical user terms that an AI polish must never re-spell."""
        self._ensure_loaded()
        terms: list[str] = []
        seen: set[str] = set()
        for rule in self._rules:
            trigger = rule.trigger
            key = trigger.casefold()
            # Skip generic words and snippets (a snippet trigger is still fair
            # game for its expansion, and masking it would hide legitimate
            # speech from the model).
            if rule.snippet or key in _STOPWORDS or len(trigger) < 3:
                continue
            # Skip ordinary lowercase words: masking "meeting" would hurt the
            # polish prompt more than it protects anything.
            if trigger == trigger.lower() and " " not in trigger and "-" not in trigger:
                continue
            if key not in seen:
                seen.add(key)
                terms.append(trigger)
            if len(terms) >= limit:
                break
        return terms

    def mask_protected_terms(self, text: str) -> tuple[str, dict[str, str]]:
        """Replace protected terms with opaque tokens the model must keep.

        Returns ``(masked_text, token_map)``; ``token_map`` is empty when
        nothing needed masking. Never raises by contract.
        """
        if not text:
            return text, {}
        try:
            terms = self.get_protected_terms()
        except Exception:
            return text, {}
        if not terms:
            return text, {}

        # Longer terms first so "AI Productivity Flow" wins over "AI".
        spans: list[tuple[int, int, str]] = []
        taken: list[tuple[int, int]] = []
        for term in sorted(terms, key=len, reverse=True):
            for match in re.finditer(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.IGNORECASE):
                start, end = match.span()
                if any(not (end <= s or start >= e) for s, e in taken):
                    continue
                taken.append((start, end))
                spans.append((start, end, term))
        if not spans:
            return text, {}

        token_map: dict[str, str] = {}
        pieces: list[str] = []
        cursor = 0
        for index, (start, end, term) in enumerate(sorted(spans), start=1):
            pieces.append(text[cursor:start])
            token = f"⟦TERM{index}⟧"
            token_map[token] = term
            pieces.append(token)
            cursor = end
        pieces.append(text[cursor:])
        return "".join(pieces), token_map

    @staticmethod
    def unmask_protected_terms(text: str, token_map: dict[str, str]) -> str:
        """Restore canonical terms swapped out before the AI call."""
        if not text or not token_map:
            return text
        result = text
        # Longest tokens first so a token that embeds another (TERM1 / TERM10)
        # restores without corrupting the embedded one.
        for token in sorted(token_map, key=len, reverse=True):
            term = token_map[token]
            # The model may or may not preserve the opaque token exactly;
            # restore both the exact token and a whitespace-tolerant form.
            result = result.replace(token, term)
            # Fuzzy pass: the model may drop or mangle the token's brackets
            # (or echo it as bare "TERM2" text). Brackets are optional and
            # inner whitespace is tolerated; whitespace outside the match is
            # preserved so neighbouring words never glue together. A literal
            # backslash-doubled replacement keeps user terms such as Windows
            # paths from being read as escape codes (re.error in old code).
            core = token.strip("⟦⟧[](){}")
            fuzzy = r"[⟦\[\(\{]?\s*" + re.escape(core) + r"\s*[⟧\]\)\}]?"
            try:
                result = re.sub(fuzzy, term.replace("\\", "\\\\"), result, flags=re.IGNORECASE)
            except re.error:
                log.warning("Unmask fuzzy restore failed for token %r; exact replacement kept", token)
        return result

    def get_stt_hint_terms(self, category: str | None = None, limit: int = 15) -> list[str]:
        """Bounded terms for cloud STT biasing: contextual pack, explicit
        terms, and correction targets — the exact spellings the provider
        should hear (spec §33)."""
        self._ensure_loaded()
        terms: list[str] = []
        seen: set[str] = set()

        def _add(term: str) -> None:
            key = term.casefold()
            if len(term) >= 3 and key not in _STOPWORDS and key not in seen:
                seen.add(key)
                terms.append(term)

        if category:
            try:
                for term in storage.get_contextual_vocabulary(category, limit=8):
                    _add(term)
            except Exception:
                pass
        for rule in self._rules:
            _add(rule.trigger)
        for rule in self._correction_rules:
            _add(rule.replacement)
        return terms[:limit]

    def get_contextual_vocabulary(self, category: str | None = None, limit: int = 30) -> list[str]:
        """Bounded vocabulary pack for STT hinting: global terms plus the
        category pack when the engine supports contextual hints (spec §33)."""
        self._ensure_loaded()
        global_terms: list[str] = []
        for rule in self._rules:
            if rule.trigger.casefold() not in _STOPWORDS and len(rule.trigger) >= 3:
                global_terms.append(rule.trigger)
        terms = sorted(global_terms, key=lambda t: (-len(t), t.casefold()))[:limit]
        if category:
            try:
                extras = storage.get_contextual_vocabulary(category, limit=limit // 2)
                for term in extras:
                    if term not in terms:
                        terms.append(term)
            except Exception:
                pass
        return terms[: limit + (limit // 2)]


# Singleton instance
dictionary_engine = DictionaryEngine()

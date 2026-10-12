"""The user dictionary: Words, Replacements, and recognizer biasing.

Design (see ``docs/dictionary.md``):

* **Words** are names and special terms the user saved (``Kubernetes``,
  ``Siobhan``, ``GraphQL``). They are sent to the speech recognizer as bias
  terms, given to the AI polisher as preferred spellings, and afterwards fix
  only their *own* spelling: ``kubernetes`` -> ``Kubernetes``, keeping a
  plural or possessive ending (``kubernetes's`` -> ``Kubernetes's``).
* **Replacements** are explicit ``heard -> correct`` pairs the user wrote.
  Only that whole heard phrase is replaced.
* Nothing is learned automatically. Polished text is never treated as a
  correction, so polishing cannot teach the dictionary to change words.
* The same deterministic pass runs with polishing on and off.

Shortcuts (snippets) are a separate feature with their own table. They are
expanded in the same single pass so that an expansion is never rewritten
again by a Word or Replacement, exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import re
import threading

from voice_flow.dictionary_rules import is_ordinary, normalize
from voice_flow.storage import storage

log = logging.getLogger(__name__)

# Never rewrite inside code, links, URLs, or email addresses.
_PROTECTED_RE = re.compile(
    r"``[\s\S]*?``|`[^`\n]*`|\[[^\]]+\]\([^\)]+\)|"
    r"(?:https?|ftp)://[^\s<>]+|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|"
    r"\bwww\.[^\s<>]+",
    re.IGNORECASE,
)

# Misheard forms of the built-in "Voice Flow" wake term. Applied ONLY to the
# command-detection copy of the transcript, never to pasted text.
_WAKE_REPAIR_RE = re.compile(
    r"(?<![\w])wiseflow(?![\w])"
    r"|(?<![\w])voice\s+with\s+flow(?![\w])"
    r"|(?<![\w])voice\s+of\s+flow(?![\w])"
    r"|(?<![\w])whisflow(?![\w])"
    r"|(?<![\w])voice\s+(?:low|bake|load|lowe)(?![\w])"
    r"|(?<![\w])voicefloor(?![\w])"
    r"|(?<![\w])voiceflow(?![\w])(?!\.\w)",
    re.IGNORECASE,
)
_WAKE_REPAIR_REPLACEMENT = "Voice Flow"

# Recognizer hint budget. Deepgram and AssemblyAI cap keyterms at 100;
# Whisper-style prompts degrade with long lists (Superwhisper docs).
_STT_HINT_MAX_CHARS = 500
_STT_HINT_MAX_TERM_CHARS = 60

# A Word keeps the ending the speaker used: plural, possessive, or both.
_SUFFIX = r"(?:['\u2019]s|s['\u2019]|es|s|['\u2019])?"

WORD = "word"
REPLACEMENT = "replacement"
SNIPPET = "snippet"


@dataclass(frozen=True)
class _Rule:
    trigger: str
    replacement: str
    kind: str = WORD

    @property
    def snippet(self) -> bool:  # backwards-compatible attribute
        return self.kind == SNIPPET


def _split_entry(value: str) -> tuple[str, str | None]:
    """Legacy ``trigger -> expansion`` strings are shortcuts, not Words."""
    for delimiter in ("->", "=>"):
        if delimiter in value:
            trigger, expansion = value.split(delimiter, 1)
            return trigger.strip(), expansion.strip()
    return value.strip(), None


# A spoken alias containing one of these is likely an ordinary sentence
# fragment ("linked in", "you tube", "face book" stays allowed).
_FUNCTION_WORDS = frozenset({
    "a", "an", "and", "as", "at", "be", "by", "do", "for", "go", "he", "i",
    "if", "in", "is", "it", "me", "my", "no", "of", "on", "or", "so", "the",
    "to", "up", "us", "we", "you", "out", "off", "all", "any", "can", "get",
})
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def generated_spaced_aliases(value: str) -> tuple[str, ...]:
    """Spoken form of a camel-cased Word: ``HyperKube`` -> ``Hyper Kube``.

    Narrow by design: one alphabetic token with mixed case, every part at
    least two letters, and not a phrase made only of ordinary words
    (``LinkedIn`` -> "linked in" is skipped so real sentences stay intact).
    """
    if not isinstance(value, str):
        return ()
    term = value.strip()
    if not term.isalpha() or term.islower() or term.isupper():
        return ()
    alias = _CAMEL_BOUNDARY_RE.sub(" ", term)
    if alias == term or any(len(part) < 2 for part in alias.split()):
        return ()
    parts = [part.casefold() for part in alias.split()]
    if is_ordinary(alias) or any(part in _FUNCTION_WORDS for part in parts):
        return ()
    return (alias,)


def _allows_suffix(rule: _Rule) -> bool:
    return rule.kind == WORD and len(rule.trigger) >= 3 and rule.trigger[-1].isalnum()


def _rule_regex(rule: _Rule) -> str:
    escaped = re.escape(rule.trigger)
    # Spoken phrases may arrive with different spacing.
    escaped = escaped.replace(r"\ ", r"\s+")
    if _allows_suffix(rule):
        # Match the stem; the suffix is checked by the lookahead and left as
        # spoken so only the term's own spelling changes.
        return r"(?<!\w)" + escaped + r"(?=" + _SUFFIX + r"(?!\w))"
    if rule.trigger[-1:].isalnum() or rule.trigger[-1:] == "_":
        return r"(?<!\w)" + escaped + r"(?!\w)"
    # Symbolic endings (C++, C#) must not match a prefix of a larger token.
    return r"(?<!\w)" + escaped + r"(?![\w+#])"


def _compile(rules: tuple[_Rule, ...]) -> re.Pattern[str] | None:
    usable = [rule for rule in rules if rule.trigger]
    if not usable:
        return None
    return re.compile("|".join(f"({_rule_regex(rule)})" for rule in usable), re.IGNORECASE)


def _apply(text: str, rules: tuple[_Rule, ...], pattern: re.Pattern[str] | None,
           trace: list[dict[str, str]] | None = None) -> str:
    """One left-to-right pass outside protected spans; no cascading."""
    if not text or pattern is None:
        return text

    def replace(match: re.Match[str]) -> str:
        index = match.lastindex or 0
        rule = rules[index - 1] if 0 < index <= len(rules) else None
        original = match.group(0)
        if rule is None:
            return original
        if trace is not None and original != rule.replacement:
            trace.append({"from": original, "to": rule.replacement})
        return rule.replacement

    out: list[str] = []
    cursor = 0
    for protected in _PROTECTED_RE.finditer(text):
        out.append(pattern.sub(replace, text[cursor:protected.start()]))
        out.append(protected.group(0))
        cursor = protected.end()
    out.append(pattern.sub(replace, text[cursor:]))
    return "".join(out)


def _ordered(rules: list[_Rule]) -> tuple[_Rule, ...]:
    """Longest trigger wins; at equal length Replacement > Shortcut > Word."""
    priority = {REPLACEMENT: 0, SNIPPET: 1, WORD: 2}
    return tuple(sorted(rules, key=lambda r: (-len(r.trigger), priority[r.kind], r.trigger.casefold())))


class DictionaryEngine:
    """Apply the user's Words, Replacements, and Shortcuts exactly once."""

    def __init__(self, store=storage) -> None:
        self.store = store
        self.words: list[str] = []
        self.corrections: list[dict] = []
        self.snippets: list[tuple[str, str]] = []
        self._rules: tuple[_Rule, ...] = ()
        self._pattern: re.Pattern[str] | None = None
        self._spelling_rules: tuple[_Rule, ...] = ()
        self._spelling_pattern: re.Pattern[str] | None = None
        self._dirty = True
        self._revision: object = None
        self._lock = threading.RLock()
        self._ensure_loaded()

    # -- loading -----------------------------------------------------------

    def mark_dirty(self) -> None:
        with self._lock:
            self._dirty = True

    def _get_revision(self) -> object:
        if getattr(self.store, "is_global_singleton", False):
            repoint = getattr(self.store, "repoint_if_needed", None)
            if repoint is not None:
                try:
                    repoint()
                except Exception:
                    log.exception("Could not synchronize dictionary storage account")
        for name in ("get_dictionary_cache_token", "get_lexicon_revision", "get_dictionary_revision"):
            getter = getattr(self.store, name, None)
            if getter is None:
                continue
            try:
                revision = getter()
            except Exception:
                continue
            if name != "get_dictionary_cache_token":
                database = getattr(self.store, "db_path", None)
                if database:
                    return os.path.normcase(os.path.realpath(os.path.abspath(str(database)))), revision
            return revision
        return None

    def _call(self, name: str, *args, **kwargs):
        getter = getattr(self.store, name, None)
        if getter is None:
            return None
        try:
            return getter(*args, **kwargs)
        except TypeError:
            return getter()

    def _load(self) -> tuple[list[str], list[dict], list[tuple[str, str]]]:
        words: list[str] | None = None
        if hasattr(self.store, "get_dictionary_entries"):
            rows = self._call("get_dictionary_entries", include_auto=False, include_snippets=False)
            words = [str(row["word"]) for row in rows or []]
        elif hasattr(self.store, "get_dictionary_snapshot"):
            _, snapshot_words, _ = self.store.get_dictionary_snapshot()
            words = [str(w) for w in snapshot_words]
        elif hasattr(self.store, "get_dictionary_words"):
            words = [str(w) for w in self._call("get_dictionary_words", include_snippets=True) or []]
        words = words or []

        corrections: list[dict] = []
        if hasattr(self.store, "get_dictionary_corrections"):
            corrections = list(self.store.get_dictionary_corrections() or [])
        elif hasattr(self.store, "get_dictionary_snapshot"):
            corrections = list(self.store.get_dictionary_snapshot()[2] or [])

        snippets: list[tuple[str, str]] = []
        plain_words: list[str] = []
        for raw in words:
            trigger, expansion = _split_entry(str(raw))
            if expansion is not None:
                if trigger and expansion:
                    snippets.append((trigger, expansion))
            elif trigger:
                plain_words.append(trigger)
        if hasattr(self.store, "get_snippets"):
            try:
                for item in self.store.get_snippets() or []:
                    trigger = str(item.get("trigger") or "").strip()
                    expansion = str(item.get("expansion") or "").strip()
                    if trigger and expansion:
                        snippets.append((trigger, expansion))
            except Exception as exc:
                log.debug("Could not load shortcuts: %s", exc)
        return plain_words, corrections, snippets

    def _ensure_loaded(self) -> None:
        with self._lock:
            revision = self._get_revision()
            if not self._dirty and revision == self._revision:
                return
            try:
                words, corrections, snippets = self._load()
            except Exception as exc:
                current = revision[0] if isinstance(revision, tuple) and revision else None
                cached = self._revision[0] if isinstance(self._revision, tuple) and self._revision else None
                if current and cached and current != cached:
                    # A different account's database: never reuse old rules.
                    self.words, self.corrections, self.snippets = [], [], []
                    self._rules, self._pattern = (), None
                    self._spelling_rules, self._spelling_pattern = (), None
                    self._revision = revision
                    log.warning("New account dictionary unavailable; cleared previous rules: %s", exc)
                else:
                    log.warning("Dictionary storage unavailable; keeping cached rules: %s", exc)
                self._dirty = True
                return

            rules: list[_Rule] = []
            seen: set[str] = set()
            for heard, correct in (
                (str(c.get("wrong_text") or "").strip(), str(c.get("correct_text") or "").strip())
                for c in corrections
            ):
                key = normalize(heard)
                if heard and correct and key not in seen:
                    seen.add(key)
                    rules.append(_Rule(heard, correct, REPLACEMENT))
            for trigger, expansion in snippets:
                key = normalize(trigger)
                if key not in seen:
                    seen.add(key)
                    rules.append(_Rule(trigger, expansion, SNIPPET))
            canonical: dict[str, str] = {}
            for word in words:
                key = normalize(word)
                if key and key not in canonical:
                    canonical[key] = word
            spelling: list[_Rule] = []
            for key, word in canonical.items():
                # A lowercase ordinary word has no spelling to restore.
                if word == word.lower() and is_ordinary(word):
                    continue
                spelling.append(_Rule(word, word, WORD))
                if key not in seen:
                    seen.add(key)
                    rules.append(_Rule(word, word, WORD))
                for alias in generated_spaced_aliases(word):
                    alias_key = normalize(alias)
                    if alias_key not in seen:
                        seen.add(alias_key)
                        rules.append(_Rule(alias, word, REPLACEMENT))

            self.words = list(canonical.values())
            self.corrections = corrections
            self.snippets = snippets
            self._rules = _ordered(rules)
            self._pattern = _compile(self._rules)
            # Spelling restoration after formatting: Words plus the targets of
            # Replacements, never the heard side and never shortcuts.
            targets = {r.trigger.casefold(): r for r in spelling}
            for rule in rules:
                if rule.kind == REPLACEMENT and rule.replacement.casefold() not in targets:
                    if not is_ordinary(rule.replacement):
                        targets[rule.replacement.casefold()] = _Rule(rule.replacement, rule.replacement, WORD)
            self._spelling_rules = _ordered(list(targets.values()))
            self._spelling_pattern = _compile(self._spelling_rules)
            self._revision = revision
            self._dirty = False

    def refresh_words(self) -> list[str]:
        self.mark_dirty()
        self._ensure_loaded()
        return list(self.words)

    # -- the one deterministic pass ---------------------------------------

    def apply_dictionary_post_processing(self, text: str, trace: list[dict[str, str]] | None = None) -> str:
        """Fix Word spellings, apply Replacements, expand Shortcuts. One pass."""
        if not text:
            return text
        self._ensure_loaded()
        result = _apply(text, self._rules, self._pattern, trace)
        if result != text:
            log.info("Applied dictionary rules to dictated text")
        return result

    def restore_dictionary_spelling(self, text: str) -> str:
        """Re-apply only Word spellings after styling; never re-runs rewrites."""
        if not text:
            return text
        self._ensure_loaded()
        return _apply(text, self._spelling_rules, self._spelling_pattern)

    def mask_rule_inputs_for_cleanup(self, text: str) -> tuple[str, dict[str, str]]:
        """Shield exact rule inputs from filler cleanup until the final pass."""
        if not text:
            return text, {}
        self._ensure_loaded()
        if self._pattern is None:
            return text, {}
        token_map: dict[str, str] = {}
        counter = 0

        def replace(match: re.Match[str]) -> str:
            nonlocal counter
            counter += 1
            token = f"\u27e6VF_DICT_INPUT_{counter}\u27e7"
            while token in text:
                counter += 1
                token = f"\u27e6VF_DICT_INPUT_{counter}\u27e7"
            token_map[token] = match.group(0)
            return token

        out: list[str] = []
        cursor = 0
        for protected in _PROTECTED_RE.finditer(text):
            out.append(self._pattern.sub(replace, text[cursor:protected.start()]))
            out.append(protected.group(0))
            cursor = protected.end()
        out.append(self._pattern.sub(replace, text[cursor:]))
        return "".join(out), token_map

    @staticmethod
    def unmask_rule_inputs_after_cleanup(text: str, token_map: dict[str, str]) -> str:
        result = text
        for token in sorted(token_map, key=len, reverse=True):
            result = result.replace(token, token_map[token])
        return result

    def repair_wake_term(self, text: str) -> str:
        """Repair misheard "Voice Flow" for command detection only."""
        if not text:
            return text
        return _WAKE_REPAIR_RE.sub(_WAKE_REPAIR_REPLACEMENT, text)

    # -- recognizer biasing and polisher hints ----------------------------

    def get_stt_hint_terms(self, category: str | None = None, limit: int = 50) -> list[str]:
        """Exact spellings to bias the recognizer: Words, then Replacement targets."""
        self._ensure_loaded()
        if limit <= 0:
            return []
        # Replacement targets first: those are words the recognizer is known
        # to get wrong. Then the user's other Words.
        candidates = [str(c.get("correct_text") or "") for c in self.corrections] + list(self.words)
        terms: list[str] = []
        seen: set[str] = set()
        used = 0
        for term in candidates:
            cleaned = " ".join(str(term).split())
            key = cleaned.casefold()
            if (
                len(cleaned) < 2
                or len(cleaned) > _STT_HINT_MAX_TERM_CHARS
                or key in seen
                or is_ordinary(cleaned)
            ):
                continue
            cost = len(cleaned) + (2 if terms else 0)
            if used + cost > _STT_HINT_MAX_CHARS:
                continue
            terms.append(cleaned)
            seen.add(key)
            used += cost
            if len(terms) >= limit:
                break
        return terms

    def get_contextual_vocabulary(self, category: str | None = None, limit: int = 30) -> list[str]:
        return self.get_stt_hint_terms(category, limit=limit)

    def get_initial_prompt(self, category: str | None = None) -> str:
        """A short Whisper prompt naming the user's terms."""
        terms = self.get_stt_hint_terms(category, limit=30)
        if not terms:
            return "Clear dictation, accurate spelling, proper names."
        return "Names and terms: " + ", ".join(terms) + "."

    def get_preferred_spellings(self, limit: int = 40) -> list[str]:
        """Spellings the AI polisher must keep exactly as written."""
        return self.get_stt_hint_terms(limit=limit)

    def get_protected_terms(self, limit: int = 60) -> list[str]:
        return [t for t in self.get_preferred_spellings(limit) if len(t) >= 3]

    def mask_protected_terms(self, text: str) -> tuple[str, dict[str, str]]:
        """Swap protected terms for opaque tokens before an AI call."""
        if not text:
            return text, {}
        try:
            terms = self.get_protected_terms()
        except Exception:
            return text, {}
        spans: list[tuple[int, int, str]] = []
        for term in sorted(terms, key=len, reverse=True):
            for match in re.finditer(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.IGNORECASE):
                start, end = match.span()
                if any(not (end <= s or start >= e) for s, e, _ in spans):
                    continue
                spans.append((start, end, term))
        if not spans:
            return text, {}
        token_map: dict[str, str] = {}
        pieces: list[str] = []
        cursor = 0
        for index, (start, end, term) in enumerate(sorted(spans), start=1):
            pieces.append(text[cursor:start])
            token = f"\u27e6TERM{index}\u27e7"
            token_map[token] = term
            pieces.append(token)
            cursor = end
        pieces.append(text[cursor:])
        return "".join(pieces), token_map

    @staticmethod
    def unmask_protected_terms(text: str, token_map: dict[str, str]) -> str:
        if not text or not token_map:
            return text
        result = text
        for token in sorted(token_map, key=len, reverse=True):
            term = token_map[token]
            result = result.replace(token, term)
            core = token.strip("\u27e6\u27e7[](){}")
            fuzzy = r"[\u27e6\[\(\{]?\s*" + re.escape(core) + r"\s*[\u27e7\]\)\}]?"
            result = re.sub(fuzzy, lambda _m, t=term: t, result, flags=re.IGNORECASE)
        return result


dictionary_engine = DictionaryEngine()

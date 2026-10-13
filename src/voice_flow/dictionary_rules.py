"""Pure validation rules for the user dictionary (no storage, no I/O).

The dictionary holds two kinds of entries, following the split used by
Wispr Flow, Superwhisper, Willow, and MacWhisper:

* **Words**: names and terms (``Kubernetes``, ``Siobhan``, ``GraphQL``).  They
  bias the recognizer and restore their own spelling only.
* **Replacements**: explicit ``heard -> correct`` pairs written by the user.

Ordinary English words are refused as Words: a list entry for "meeting" or
"hey" can only ever rewrite speech the user really said.  Built-in product
terms (the "Hey Voice Flow" wake phrase) are handled by the command detector
and never need a dictionary row.
"""

from __future__ import annotations

import re

MAX_TERM_CHARS = 60
MAX_REPLACEMENT_CHARS = 240

# Built-in product terms. The command detector already repairs misheard wake
# phrases, so a user row for them is redundant and was a source of rewrites.
BUILTIN_TERMS = frozenset({
    "voice flow", "voiceflow", "hey voice flow", "hey voiceflow", "hey flow",
    "flow", "hey",
})

# Frequent English words (greetings, fillers, function words, everyday nouns
# and verbs). Rare words are allowed because a user adding them is deliberate.
from voice_flow.dictionary_common_words import COMMON_WORDS as _BASE_COMMON  # noqa: E402

COMMON_WORDS = _BASE_COMMON | frozenset({
    "hi", "hello", "hey", "bye", "thanks", "okay", "ok", "yeah", "yep", "nope",
    "uh", "um", "umm", "hmm", "ah", "er", "oh", "voice", "flow", "polish",
    "polishing", "dictionary", "command", "commands", "app", "apps",
    "meeting", "meetings", "email", "emails", "report", "reports",
})

_HAS_TEXT_RE = re.compile(r"\w", re.UNICODE)


def normalize(value: str) -> str:
    """Casefold and collapse whitespace for comparisons."""
    return " ".join(str(value or "").split()).casefold()


def is_ordinary(value: str) -> bool:
    """True when every token of ``value`` is a common English word."""
    tokens = re.findall(r"[\w']+", normalize(value))
    return bool(tokens) and all(token in COMMON_WORDS for token in tokens)


def term_problem(term: object) -> str | None:
    """Return a user-facing reason a Word cannot be saved, or None."""
    if not isinstance(term, str):
        return "Type a word or name."
    clean = " ".join(term.split())
    if not clean:
        return "Type a word or name."
    if "->" in clean or "=>" in clean:
        return "Use Heard as for corrections. Shortcuts live in Shortcuts."
    if len(clean) > MAX_TERM_CHARS:
        return f"Keep words under {MAX_TERM_CHARS} characters."
    if not _HAS_TEXT_RE.search(clean):
        return "A word needs at least one letter or number."
    folded = normalize(clean)
    if folded in BUILTIN_TERMS:
        return f"\u201c{clean}\u201d is built in. Flow already understands it."
    if is_ordinary(clean):
        return (
            f"\u201c{clean}\u201d is an ordinary word, so Flow leaves it as you say it. "
            "Add names and special terms here."
        )
    return None


def replacement_problem(heard: object, correct: object) -> str | None:
    """Return a user-facing reason a Replacement cannot be saved, or None."""
    if not isinstance(heard, str) or not isinstance(correct, str):
        return "Type what Flow hears and what it should write."
    wrong = " ".join(heard.split())
    right = " ".join(correct.split())
    if not wrong or not right:
        return "Type what Flow hears and what it should write."
    if len(wrong) > MAX_REPLACEMENT_CHARS or len(right) > MAX_REPLACEMENT_CHARS:
        return f"Keep each side under {MAX_REPLACEMENT_CHARS} characters."
    if "->" in wrong or "=>" in wrong:
        return "Type the misheard phrase without arrows."
    if not _HAS_TEXT_RE.search(wrong):
        return "The heard phrase needs at least one letter or number."
    if wrong == right:
        return "Heard as and the correct spelling are the same."
    # The wake phrase must reach the command detector unchanged.
    if normalize(wrong) in BUILTIN_TERMS or normalize(wrong) == "voice":
        return (
            f"\u201c{wrong}\u201d is part of the built-in wake phrase, so it cannot be replaced."
        )
    return None

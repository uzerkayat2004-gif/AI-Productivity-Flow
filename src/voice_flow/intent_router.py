"""Zero-latency intent router — the "small gatekeeper" of the dictation pipeline.

Wispr Flow's depth is routing: most speech is handled by a tiny fast decision
layer before any expensive work. This module is the rule-based equivalent: it
decides, from the raw transcript + target app + textbox context, whether the
utterance is a command, a question, code, chat, or formal writing — and what
cleanup level / AI budget each one gets. No models, no network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

RouteMode = Literal["verbatim", "cleanup", "ai_polish"]

# Spoken commands: dictation that is really an instruction. These must never
# be rewritten by an AI polisher (it would "answer" them) and need only light
# cleanup so the punctuation step can still do its job.
_COMMAND_STARTERS = (
    "send", "sends", "schedule", "open", "opens", "search", "searches",
    "google", "delete", "undo", "redo", "copy", "cut", "paste", "press",
    "hit", "click", "close", "minimize", "maximize", "refresh", "save",
    "stop", "cancel", "start", "pause", "play", "mute", "unmute", "call",
    "email", "text", "message", "add", "remove", "create", "make", "write",
    "reply", "forward", "attach", "download", "upload", "install", "uninstall",
    "restart", "shutdown", "lock", "unlock", "print", "submit", "approve",
    "reject", "book", "order", "pay", "invite", "remind", "remember",
)
_COMMAND_PHRASES = (
    "new line", "next line", "line break", "new paragraph", "new sentence",
    "press enter", "hit enter", "copy that", "paste that", "undo that",
    "delete that", "send that", "that's it", "that is it", "done",
    "never mind", "nevermind", "scratch that", "cancel that", "stop",
)
_QUESTION_WORDS = ("what", "when", "where", "which", "who", "whom", "whose", "why", "how", "is", "are", "was", "were", "do", "does", "did", "can", "could", "would", "should", "will", "shall", "may", "might", "have", "has", "had")
_TERMINAL_STYLES = {"cleanup_none"}
_CODE_CATEGORY = "developer"
# Very casual chat styles are lowercase-first by design; AI rewriting them is a
# waste of the latency budget and the AI almost always over-edits them.
_NO_AI_STYLE_FRAGMENTS = ("very_casual",)
# Formal contexts get the deepest cleanup; the AI budget is spent there.
_HIGH_CLEANUP_FRAGMENTS = ("formal", "email")

_SENTENCE_END = re.compile(r"[.!?]\s*$|[\n\r]\s*$")


@dataclass(frozen=True)
class RoutingDecision:
    """What the pipeline should do with this utterance."""

    mode: RouteMode = "cleanup"
    level: str = "cleanup_medium"
    is_command: bool = False
    is_question: bool = False
    allow_ai: bool = True
    # None = let the style engine decide; True/False force first-letter casing.
    capitalize_first: bool | None = None
    reason: str = field(default="default", kw_only=True)


def _detect_command(text: str) -> bool:
    lowered = text.strip().lower()
    if any(phrase in lowered for phrase in _COMMAND_PHRASES):
        return True
    first = lowered.split()[0] if lowered.split() else ""
    return first in _COMMAND_STARTERS or first.endswith(" that")


def _detect_question(text: str) -> bool:
    stripped = text.strip()
    if stripped.endswith("?"):
        return True
    first = stripped.lower().split()[0] if stripped.split() else ""
    return first in _QUESTION_WORDS


def _context_capitalization(before: str, after: str, trustworthy: bool) -> bool | None:
    """Match the surrounding text's conventions, Wispr-style.

    - Cursor at document start or right after ". ", "? " or a newline ->
      capitalize the first word.
    - Mid-sentence (text follows, text precedes) -> start lowercase.
    - Otherwise let the style engine decide.
    """
    if not trustworthy:
        return None
    if not before.strip() or _SENTENCE_END.search(before):
        return True
    if after.strip():
        return False
    return None


def route_utterance(
    text: str,
    *,
    category: str = "other",
    style_id: str = "other_casual",
    before: str = "",
    after: str = "",
    trustworthy_context: bool = False,
) -> RoutingDecision:
    """Route an utterance to its pipeline treatment in O(1) without any model."""
    if not text or not text.strip():
        return RoutingDecision(reason="empty")

    is_command = _detect_command(text)
    is_question = _detect_question(text)
    capitalize_first = _context_capitalization(before, after, trustworthy_context)

    if style_id in _TERMINAL_STYLES:
        return RoutingDecision(
            mode="verbatim", level="cleanup_none", is_command=is_command,
            is_question=is_question, allow_ai=False,
            capitalize_first=None, reason="terminal-verbatim",
        )

    if is_command:
        # Commands are instructions, not prose: light cleanup only, never AI.
        return RoutingDecision(
            mode="cleanup", level="cleanup_light", is_command=True,
            is_question=is_question, allow_ai=False,
            capitalize_first=capitalize_first, reason="command",
        )

    if is_question:
        # An AI polisher would be tempted to *answer* a question instead of
        # polishing it. Keep questions deterministic and safe.
        return RoutingDecision(
            mode="cleanup", level="cleanup_medium", is_command=False,
            is_question=True, allow_ai=False,
            capitalize_first=capitalize_first, reason="question",
        )

    if category == _CODE_CATEGORY:
        return RoutingDecision(
            mode="cleanup", level="cleanup_light", is_command=False,
            is_question=is_question, allow_ai=False,
            capitalize_first=capitalize_first, reason="code-context",
        )

    style_fold = style_id.casefold()
    if any(frag in style_fold for frag in _NO_AI_STYLE_FRAGMENTS):
        return RoutingDecision(
            mode="cleanup", level="cleanup_light", is_command=False,
            is_question=is_question, allow_ai=False,
            # All-lowercase style contract: never fight it with context casing.
            capitalize_first=None, reason="very-casual-chat",
        )

    if any(frag in style_fold for frag in _HIGH_CLEANUP_FRAGMENTS):
        return RoutingDecision(
            mode="ai_polish", level="cleanup_high", is_command=False,
            is_question=is_question, allow_ai=True,
            capitalize_first=capitalize_first, reason="formal-email",
        )

    return RoutingDecision(
        mode="ai_polish", level="cleanup_medium", is_command=False,
        is_question=is_question, allow_ai=True,
        capitalize_first=capitalize_first, reason="default",
    )
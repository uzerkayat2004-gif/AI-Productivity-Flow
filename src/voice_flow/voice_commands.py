"""Voice Flow command layer — deterministic wake-phrase command detection.

Users can dictate a command inline with their content:

    "Hey Voice Flow, make this an excited email. We're launching Monday."
    "We're launching Monday. Hey Voice Flow, make this an excited email."

The detector splits the transcript into (content, command) without any model
call: wake-phrase spotting, clause extraction, and intent parsing are all
pure regex work (microseconds, spec §52).

Safety rules (spec §9-10):

- The wake phrase must be a deliberate clause: "Hey Voice Flow" (optionally
  "Ok Voice Flow"), or a clause-initial "Voice Flow" followed by a comma or
  an imperative verb. The words "voice flow" inside ordinary sentences
  never trigger.
- Wake phrases inside quoted content are ignored: ``My manager said 'Hey
  Voice Flow, make this casual.'`` is plain dictation.
- If a wake phrase is present but no known intent follows, preserve the
  entire dictation, including the wake words.

The parsed :class:`VoiceCommand` is a structured object (spec §12); the AI
model never decides command priority — this module and the effective-style
resolver own that (spec §45).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

# --------------------------------------------------------------------------
# Schema (spec §12)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class VoiceCommand:
    raw_phrase: str = ""
    scope: str = "current"            # "current" | "next"
    operation: str = "rewrite"        # "rewrite" | "summarize" | "prompt_generation"
    format: str | None = None         # email|work_message|personal_message|note|linkedin_post|bullet_list|prompt
    context_reference: str | None = None  # email|work|personal|other
    overrides: dict = field(default_factory=dict)  # tone/formality/length/clarity/grammar/dedupe
    persistent_change: bool = False
    ambiguous: bool = False
    preserve_wording: bool = False

    def label(self) -> str:
        """Short human label for UI feedback, e.g. 'Email / Excited'."""
        parts: list[str] = []
        fmt_value = self.format if isinstance(self.format, str) else None
        context_value = self.context_reference if isinstance(self.context_reference, str) else None
        fmt = fmt_value.replace("_", " ").title() if fmt_value else None
        if context_value and not fmt:
            fmt = f"My {context_value.title()} Style"
        if fmt:
            parts.append(fmt)
        if self.operation == "summarize" and fmt != "Prompt":
            parts.append("Summary")
        elif self.operation == "prompt_generation" and fmt != "Prompt":
            parts.append("Prompt")
        overrides = self.overrides if hasattr(self.overrides, "get") else {}
        for key in ("tone", "formality", "length", "clarity"):
            if key in overrides:
                parts.append(str(overrides[key]).title())
        if self.persistent_change:
            parts.append("Save")
        return " / ".join(parts)


@dataclass(frozen=True)
class CommandDetection:
    content: str                # transcript with wake phrase + command clause removed
    command: VoiceCommand | None


# --------------------------------------------------------------------------
# Wake phrase spotting
# --------------------------------------------------------------------------

# Quoted spans are user content, never commands (spec §9).
_QUOTED_SPAN_RE = re.compile(
    r"\"[^\"]{2,}?\"|(?<!\w)'[^']{2,}?'(?!\w)|`[^`]+`|[“”][^“”]{2,}?[“”]|‘[^‘’]{2,}?’"
)
# "Voice Flow" is mis-heard in several shapes (VoiceFlow, voice-flow, voice
# flows); all count as the wake phrase when the hey/ok prefix is present.
# ``voice log`` is a deliberately narrow STT alias: accept it only with that
# explicit prefix so ordinary mentions of a voice log remain dictation.
_WAKE_RE = re.compile(
    r"(?<![\w])(?:"
    r"(?:hey|ok|okay)\s*[,.:!\-—]?\s*(?:voice[\s\-]{0,3}flows?|voice\s+log|voice)"
    # A verified STT error for "Hey Voice Flow".  Keep this deliberately
    # literal and require a command continuation below; it is not fuzzy wake
    # matching for arbitrary speech that happens to contain similar words.
    r"|(?:hay|hey)\s+voiced\s+what"
    r"|voice[\s\-]{0,3}flows?"
    r")(?![\w])",
    re.IGNORECASE,
)
# A bare "voice flow" (no hey/ok) is only a wake phrase when a command-style
# continuation follows immediately: a comma or an imperative verb.
_BARE_WAKE_CONTINUATION_RE = re.compile(
    r"^voice[\s\-]{0,3}flows?\s*(?:,|!|\.)?\s*(?:please\s+)?"
    r"(?:make|turn|use|write|create|rewrite|summarize|summarise|fix|shorten|clean|polish|convert|send|generate|draft)\b",
    re.IGNORECASE,
)
_PREFIX_ONLY_WAKE_CONTINUATION_RE = re.compile(
    r"^\s*[,.:!\-—]?\s*(?:please\s+)?"
    r"(?:make|turn|use|write|create|rewrite|summarize|summarise|fix|shorten|clean|polish|convert|send|generate|draft)\b",
    re.IGNORECASE,
)
_SENTENCE_END_RE = re.compile(r"[.!?](?:\s+|$)")
_LEADING_FILLER_RE = re.compile(r"^(?:um+|uh+|well|so|okay|ok)[,.\s]+", re.IGNORECASE)


def _mask_quoted(text: str) -> str:
    """Blank out quoted spans so wake-phrase searches ignore them."""
    return _QUOTED_SPAN_RE.sub(lambda m: " " * len(m.group(0)), text)


def _is_wake_at(text: str, match: re.Match) -> bool:
    """'Hey/Ok Voice Flow' always wakes (mishearings tolerated); a bare
    'voice flow' needs a command continuation immediately after it (comma or
    imperative verb) and must not carry a trailing 's'."""
    matched = match.group(0).lower()
    if re.match(r"^\s*(?:hay|hey)\s+voiced\s+what\b", matched):
        return bool(_PREFIX_ONLY_WAKE_CONTINUATION_RE.match(text[match.end():]))
    if re.match(r"^\s*(?:hey|ok|okay)\b", matched):
        # "Hey voice" is a useful incomplete-ASR alias only when it is
        # immediately followed by a known imperative.  A conversational
        # "hey voice, are you there" remains ordinary dictation.
        if re.search(r"\bvoice\s*$", matched):
            return bool(_PREFIX_ONLY_WAKE_CONTINUATION_RE.match(text[match.end():]))
        return True
    if matched.rstrip().endswith("flows"):
        return False
    return bool(_BARE_WAKE_CONTINUATION_RE.match(text[match.start():]))


# --------------------------------------------------------------------------
# Intent parsing
# --------------------------------------------------------------------------

_FORMAT_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("work_message", re.compile(r"\bwork\s+(?:message|chat|msg)\b", re.I)),
    ("personal_message", re.compile(r"\bpersonal\s+(?:message|msg|text)\b", re.I)),
    # A generic message is personal by default.  Limit this to command-shaped
    # wording so ordinary dictation such as "draft a message to the team"
    # remains untouched; explicit work/personal forms above take priority.
    ("personal_message", re.compile(
        r"\b(?:make|turn|write|create)\b[\w\s]{0,24}\b(?:a\s+)?"
        r"(?:(?:normal|casual)\s+)?(?:message|msg|text)\b"
        r"|\b(?:normal|casual)\s+(?:message|msg|text)\b",
        re.I,
    )),
    ("linkedin_post", re.compile(r"\blinkedin\s+post\b", re.I)),
    ("bullet_list", re.compile(r"\bbullets?\b|\bbullet(?:ed)?\s+list\b", re.I)),
    ("email", re.compile(r"\be-?mail\b", re.I)),
    # "note(s)" only counts as a format command in an explicit make/turn/as
    # construction — "the meeting notes are due" is content, not a command.
    ("note", re.compile(
        r"\b(?:make|create|turn|write)\b[\w\s]{0,24}\bnotes?\b"
        r"|\bas\s+(?:a\s+)?notes?\b"
        r"|\bthis\s+(?:into\s+)?(?:a\s+)?notes?\b",
        re.I)),
    # A bare "prom" is only accepted when it ends the clause: that is the
    # speech-recognition truncation of "prompt". Requiring the whole word
    # otherwise keeps ordinary dictation such as "make this a prom dress"
    # from being parsed as a prompt command.
    ("prompt", re.compile(
        r"\b(?:proper\s+|coding\s+|well[-\s]?structured\s+)?prompts?\b"
        r"|\b(?:make|turn|convert)\s+(?:this|it)\s+(?:as\s+|into\s+)?(?:a\s+)?(?:good\s+)?prompts?\b"
        r"|\b(?:make|turn|convert)\s+(?:this|it)\s+(?:as\s+|into\s+)?(?:a\s+)?(?:good\s+)?prom\b\s*[.!?]*\s*$",
        re.I)),
)
_CONTEXT_REFERENCE_RE = re.compile(
    r"\b(?:my|the)\s+(?:usual|normal|regular)?\s*(email|work|personal|other)\b"
    r"|\buse\s+my\s+(email|work|personal|other)\b",
    re.I,
)
_TONE_WORDS = {
    "excited": "excited", "casual": "casual", "friendly": "friendly",
    "conversational": "conversational", "confident": "confident",
    "persuasive": "persuasive", "playful": "playful",
}
_FORMALITY_WORDS = {"professional": "professional", "formal": "formal"}
_LENGTH_SHORT_RE = re.compile(r"\b(?:short(?:er)?|concise|brief|tighten(?:\s+it\s+up)?)\b", re.I)
_LENGTH_DETAILED_RE = re.compile(r"\b(?:longer|more\s+detailed|expand)\b", re.I)
_CLARITY_RE = re.compile(r"\b(?:clearer|easier\s+to\s+(?:read|understand)|simpler)\b", re.I)
_GRAMMAR_RE = re.compile(r"\bfix\s+(?:the\s+)?grammar\b", re.I)
_DEDUPE_RE = re.compile(r"\bremove\s+(?:the\s+)?repetit(?:ion|ive)\b", re.I)
_SUMMARIZE_RE = re.compile(r"\bsummarize|summarise\b", re.I)
_REWRITE_RE = re.compile(r"^\s*(?:please\s+)?(?:rewrite|polish|clean\s+up)\b", re.I)
_INSTRUCTIONS_RE = re.compile(r"\bas\s+(?:clear\s+)?instructions\b", re.I)
_PERSISTENT_RE = re.compile(
    r"\b(?:always|from\s+now\s+on|remember\s+(?:this|that)|save\s+(?:this|that)(?:\s+style)?)\b", re.I
)
_SCOPE_NEXT_RE = re.compile(r"\b(?:what|whatever)\s+(?:i|i'll)\s+(?:say|speak|dictate)\s+next\b", re.I)
_KEEP_WORDING_RE = re.compile(r"\bkeep\s+my\s+(?:wording|words|phrasing)\b|\bdon'?t\s+rewrite\b", re.I)
# Corrective markers: later register words override earlier ones (spec §24).
_CORRECTION_RE = re.compile(r"\b(?:actually|no\s+wait|I\s+mean|instead)\b", re.I)
# A plain "and" between a formality and a tone word is a genuine contradiction
# (spec §24); "but"/"yet" merges them as separate dimensions (spec §25).
_REGISTER_JOINER_RE = re.compile(
    r"\b(?:formal|professional)\b(?:\s+\w+){0,2}?\s+and\s+(?:\s*\w+\s+){0,2}?(?:casual|friendly|conversational|relaxed)\b"
    r"|\b(?:casual|friendly|conversational|relaxed)\b(?:\s+\w+){0,2}?\s+and\s+(?:\s*\w+\s+){0,2}?(?:formal|professional)\b",
    re.I,
)


def _extract_format(clause: str) -> tuple[str | None, str]:
    for fmt, pattern in _FORMAT_PATTERNS:
        if pattern.search(clause):
            return fmt, pattern.pattern
    return None, ""


def _extract_context_reference(clause: str) -> str | None:
    m = _CONTEXT_REFERENCE_RE.search(clause)
    if not m:
        return None
    word = (m.group(1) or m.group(2) or "").lower()
    return word or None


def _parse_command(clause: str) -> VoiceCommand:
    """Parse one command clause (wake phrase already removed) into a schema object."""
    text = clause.strip()
    lowered = text.lower()

    overrides: dict[str, str] = {}
    ambiguous = False

    # -- format / context reference -------------------------------------------------
    fmt, _ = _extract_format(text)
    context_ref = _extract_context_reference(text)
    operation = "rewrite"
    if _SUMMARIZE_RE.search(lowered):
        operation = "summarize"
    elif fmt == "prompt" or _INSTRUCTIONS_RE.search(lowered):
        operation = "prompt_generation"
        fmt = "prompt"
    elif _REWRITE_RE.search(lowered):
        operation = "rewrite"
        overrides["grammar"] = "fix"

    # -- style dimensions -----------------------------------------------------------
    if _LENGTH_SHORT_RE.search(lowered):
        overrides["length"] = "short"
    if _LENGTH_DETAILED_RE.search(lowered):
        overrides["length"] = "detailed"
    if _CLARITY_RE.search(lowered):
        overrides["clarity"] = "simplified"
    if _GRAMMAR_RE.search(lowered):
        overrides["grammar"] = "fix"
    if _DEDUPE_RE.search(lowered):
        overrides["dedupe"] = "remove"

    # Register words: professional/formal raise formality; casual/friendly/…
    # set the tone. Same-word repetition keeps the last (spec §24 last clear
    # corrective instruction wins).
    formal_hits = [m for m in re.finditer(r"\b(professional|formal)\b", lowered)]
    tone_hits = [(m, _TONE_WORDS[m.group(1)]) for m in re.finditer(r"\b(\w+)\b", lowered)
                 if m.group(1) in _TONE_WORDS]
    if formal_hits:
        overrides["formality"] = _FORMALITY_WORDS[formal_hits[-1].group(1)]
    if tone_hits:
        overrides["tone"] = tone_hits[-1][1]
    # A plain "and"-joined formal/casual pair is genuinely ambiguous (§24):
    # refuse to choose and keep the saved profile instead.
    if formal_hits and tone_hits and _REGISTER_JOINER_RE.search(lowered) \
            and not _CORRECTION_RE.search(lowered):
        ambiguous = True
        overrides.pop("formality", None)
        overrides.pop("tone", None)

    # If a correction marker exists, the LAST style word wins outright (§24:
    # "make it professional, actually make it casual" -> casual).
    if _CORRECTION_RE.search(lowered) and (formal_hits or tone_hits):
        style_words = [(m, "formality") for m in formal_hits]
        style_words += [(m, "tone") for m, _ in tone_hits]
        style_words.sort(key=lambda pair: pair[0].start())
        if style_words:
            last_match, last_kind = style_words[-1]
            word = last_match.group(1)
            overrides.pop("formality", None)
            overrides.pop("tone", None)
            if last_kind == "formality" or word in _FORMALITY_WORDS:
                overrides["formality"] = _FORMALITY_WORDS.get(word, "professional")
            else:
                overrides["tone"] = _TONE_WORDS.get(word, word)

    has_intent = bool(fmt or context_ref or overrides or operation != "rewrite")
    if not has_intent:
        # Wake phrase with no recognizable intent: treat as plain dictation.
        return VoiceCommand(raw_phrase=text)

    return VoiceCommand(
        raw_phrase=text,
        scope="next" if _SCOPE_NEXT_RE.search(lowered) else "current",
        operation=operation,
        format=fmt,
        context_reference=context_ref,
        overrides=overrides,
        persistent_change=bool(_PERSISTENT_RE.search(lowered)),
        ambiguous=ambiguous,
        preserve_wording=bool(_KEEP_WORDING_RE.search(lowered)),
    )


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def detect_voice_command(transcript: str) -> CommandDetection:
    """Split a transcript into (content, command).

    Returns ``command=None`` for ordinary dictation. Never raises on odd
    input by contract; callers still wrap in try/except (spec §49).
    """
    if transcript is None:
        return CommandDetection(content="", command=None)
    if not isinstance(transcript, str):
        try:
            transcript = str(transcript)
        except Exception:
            return CommandDetection(content="", command=None)
    if not transcript or not transcript.strip():
        return CommandDetection(content=transcript, command=None)

    text = transcript.strip()
    masked = _mask_quoted(text)

    # Find the first wake phrase that lives OUTSIDE quoted content.
    wake = None
    for match in _WAKE_RE.finditer(masked):
        if _is_wake_at(text, match):
            wake = match
            break
    if wake is None:
        return CommandDetection(content=text, command=None)

    starts_begin = _starts_as_beginning(text, wake.start())

    if starts_begin:
        # Command clause = the first sentence after the wake phrase.
        after_wake = text[wake.end():].lstrip(" ,.:!-—")
        sentence = _SENTENCE_END_RE.search(after_wake)
        if sentence:
            clause = after_wake[:sentence.end()].strip()
            content = after_wake[sentence.end():].strip()
        else:
            clause = after_wake.strip()
            content = ""
    else:
        # Ending (or mid) command: the clause runs from the wake phrase to the
        # end of the dictation; everything before it is content.
        before = text[:wake.start()].strip()
        after_wake = text[wake.end():].lstrip(" ,.:!-—")
        sentence = _SENTENCE_END_RE.search(after_wake)
        clause = after_wake[:sentence.end()].strip() if sentence else after_wake.strip()
        if sentence and after_wake[sentence.end():].strip():
            # Wake phrase in the middle: keep trailing content after the clause.
            content = (before + " " + after_wake[sentence.end():].strip()).strip()
        else:
            content = before
        if not content:
            # Nothing before the wake phrase: it is effectively a begin command.
            starts_begin = True
            content = ""

    # ASR frequently inserts a comma/colon instead of a sentence boundary.
    # Split only after a recognized command and before content, retaining
    # style continuations such as 'actually make it casual' in the command.
    for boundary in re.finditer(r"[:,;]\s+", clause):
        head = clause[:boundary.start()].strip()
        tail = clause[boundary.end():].strip()
        if not tail or re.match(r"(?:actually|instead|rather|and|but|make|turn|use|keep|without|with|short(?:er)?|clear(?:er)?|concise|formal|professional|casual|friendly|excited|detailed)\b", tail, re.I):
            continue
        parsed_head = _parse_command(head)
        if _has_any_intent(parsed_head):
            clause = head
            if starts_begin:
                content = (tail + " " + content).strip()
            else:
                trailing = after_wake[sentence.end():].strip() if sentence else ""
                content = " ".join(part for part in (before, tail, trailing) if part)
            break

    if not clause:
        # "Hey Voice Flow" with nothing after: nothing to interpret.
        return CommandDetection(content=text, command=None)

    parsed = _parse_command(clause)
    if parsed.raw_phrase and not _has_any_intent(parsed):
        # Without recognized intent there is no permission to remove words.
        return CommandDetection(content=text, command=None)

    command = parsed
    return CommandDetection(content=content if content else "", command=command)


def _has_any_intent(command: VoiceCommand) -> bool:
    return bool(
        command.format
        or command.context_reference
        or command.overrides
        or command.operation != "rewrite"
        or command.persistent_change
        or command.preserve_wording
    )


def _starts_as_beginning(text: str, wake_start: int) -> bool:
    """True when the wake phrase opens the dictation (leading fillers allowed)."""
    prefix = text[:wake_start]
    # Keep the punctuation while deciding this: STT commonly emits
    # ``Hey. Voice Flow`` as two clauses.  Since the wake match includes the
    # deliberate prefix, this recognizes it as a leading command and removes
    # the whole prefix instead of leaving ``Hey.`` in the dictated content.
    return bool(re.fullmatch(
        r"\s*(?:(?:um+|uh+|well|so|okay|ok|hey)\s*[,.:!?\-—]?\s*)*",
        prefix,
        re.IGNORECASE,
    ))

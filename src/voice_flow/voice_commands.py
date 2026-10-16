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
    # Free-text writing constraints that belong to the command clause and have
    # no structured field ("without hashtags", "keep both deadlines").  They
    # are forwarded verbatim to the model as the VF-1 [Instruction] text.
    constraints: tuple = ()

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
        if self.operation == "unsupported":
            parts.append("Unsupported")
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
    # Further ASR mishearings of "Voice Flow" ("why slow", "boys flow",
    # "voice flo"). Only with an explicit hey/ok prefix and, in _is_wake_at,
    # only when a known command verb follows immediately.
    r"(?:hey|ok|okay)\s*[,.:!\-—]?\s*(?:why|wise|boys?|nice|choice|voice)[\s\-]{0,3}(?:slow|flo|flu|flows?)"
    r"|(?:hey|ok|okay)\s*[,.:!\-—]?\s*(?:voice[\s\-]{0,3}flows?|voice\s+log|voice\s+law|voice[\s-]?low|voice)"
    # A verified STT error for "Hey Voice Flow".  Keep this deliberately
    # literal and require a command continuation below; it is not fuzzy wake
    # matching for arbitrary speech that happens to contain similar words.
    r"|(?:hay|hey)\s+voiced\s+what"
    # Deliberate wake prefix plus a narrow ASR substitution for "Voice Flow".
    # The alias is accepted only with an explicit hey/ok/okay prefix.
    r"|(?:hey|ok|okay)\s*[,.:!\-—]?\s*vice[\s\-]{0,3}flows?"
    # A narrow ASR alias for "Voice Flow". _is_wake_at additionally requires
    # a command immediately after it and a clause boundary before it.
    r"|voice[\s-]?low"
    r"|voice[\s\-]{0,3}flows?"
    r")(?![\w])",
    re.IGNORECASE,
)
# A bare "voice flow" (no hey/ok) is only a wake phrase when a command-style
# continuation follows immediately: a comma or an imperative verb.
_BARE_WAKE_CONTINUATION_RE = re.compile(
    r"^voice[\s\-]{0,3}flows?\s*(?:,|!|\.)?\s*(?:please\s+)?"
    r"(?:make|turn|use|write|create|change|rewrite|summarize|summarise|fix|shorten|clean|polish|convert|send|generate|draft)\b",
    re.IGNORECASE,
)
_PREFIX_ONLY_WAKE_CONTINUATION_RE = re.compile(
    r"^\s*[,.:!\-—]?\s*(?:please\s+)?"
    r"(?:make|turn|use|write|create|change|rewrite|summarize|summarise|fix|shorten|clean|polish|convert|send|generate|draft)\b",
    re.IGNORECASE,
)
_SENTENCE_END_RE = re.compile(r"[.!?](?:\s+|$)")
_LEADING_FILLER_RE = re.compile(r"^(?:um+|uh+|well|so|okay|ok)[,.\s]+", re.IGNORECASE)
# A wake phrase quoted as an example without quotation marks is still ordinary
# dictation.  The parser must not consume the rest of a report merely because
# it contains the words a user would say to Voice Flow.
_REPORTED_WAKE_PREFIX_RE = re.compile(
    r"\b(?:said|says|saying|mentioned|heard|told\s+(?:me|us|him|her|them|you)|asked(?:\s+(?:me|us|him|her|them|you))?|"
    r"was\s+like|goes|wrote|texted|messaged)\s*[, :]?\s*$"
    r"|\b(?:if|when|unless|whether)\s+(?:i|you|we|they|someone)\s+"
    r"(?:say|said|says|mention|mentioned|use|used|hear|heard)\s*$",
    re.IGNORECASE,
)
# ASR commonly omits the full stop between a leading command and the dictated
# text.  Stop the command at a recognised intent word rather than treating the
# whole utterance as guidance.  This deliberately contains only command words;
# an unknown following word stays in the user's content.
_UNPUNCTUATED_INTENT_END_RE = re.compile(
    r"\b(?:"
    r"e-?mail|bullets?|bullet(?:ed)?\s+(?:list|points)|numbered\s+(?:list|points|steps)|linkedin\s+post|"
    r"(?:slack|teams)\s+(?:message|chat|msg)|text\s+message|"
    r"(?:make|turn|convert)\s+(?:this|it)\s+(?:into\s+)?(?:a\s+)?(?:list|summary)|summary|"
    r"simplify(?:\s+(?:this|it))?|remove\s+(?:the\s+)?duplicates?|(?:sound\s+)?better|improve(?:\s+(?:this|it))?|"
    r"less\s+(?:formal|professional|casual)|"
    r"work\s+(?:message|chat|msg)|personal\s+(?:message|msg|text)|"
    r"(?:normal|casual)\s+(?:message|msg|text)|"
    r"(?:proper\s+|coding\s+|well[-\s]?structured\s+)?prompts?|"
    r"(?:make|create|turn|write)\s+(?:this\s+)?(?:into\s+)?(?:a\s+)?notes?|"
    r"summari[sz]e|short(?:er)?|concise|brief|tighten|detailed|longer|expand|"
    r"clearer|simpler|professional|formal|casual|friendly|conversational|"
    r"confident|persuasive|playful|excited|"
    r"keep\s+my\s+(?:wording|words|phrasing)|don'?t\s+rewrite|"
    r"fix\s+(?:the\s+)?grammar|remove\s+(?:the\s+)?repetit(?:ion|ive)"
    r")\b",
    re.IGNORECASE,
)
_MAX_UNPUNCTUATED_COMMAND_WORDS = 18
_POLITE_COMMAND_PREFIX_RE = re.compile(r"^\s*(?:can|could|would)\s+you\s+(?:please\s+)?", re.I)
_COMMAND_START_WORDS = {
    "please", "make", "turn", "use", "write", "create", "change", "rewrite", "summarize", "summarise",
    "fix", "shorten", "clean", "polish", "convert", "send", "generate", "draft",
    "remove", "don't", "tighten", "expand", "keep", "simplify", "improve", "format",
}
_COMMAND_SYNTAX_WORDS = {
    "this", "it", "as", "into", "a", "an", "the", "my", "usual", "normal", "regular",
    "proper", "coding", "well", "structured", "work", "personal", "linkedin", "post", "message",
    "chat", "msg", "text", "bullet", "bullets", "bulleted", "list", "points", "email", "mail", "note", "notes",
    "prompt", "short", "shorter", "concise", "brief", "tighten", "detailed", "longer", "more",
    "expand", "clearer", "simpler", "professional", "formal", "casual", "friendly", "conversational",
    "confident", "persuasive", "playful", "excited", "grammar", "repetition", "repetitive",
    "good", "linkedin", "slack", "teams", "numbered", "summary", "simplify", "duplicates", "duplicate",
    "sound", "better", "improve", "less", "only", "style", "up", "steps", "keep", "wording", "words",
    "phrasing",
}
_COMMAND_INTENT_WORDS = {
    "email", "mail", "bullet", "bullets", "bulleted", "list", "points", "prompt", "note", "notes",
    "message", "chat", "msg", "text", "short", "shorter", "concise", "brief", "tighten", "detailed",
    "longer", "expand", "clearer", "simpler", "professional", "formal", "casual", "friendly",
    "conversational", "confident", "persuasive", "playful", "excited", "summarize", "summarise",
    "grammar", "repetition", "repetitive", "don't", "post", "linkedin", "summary", "simplify",
    "duplicates", "duplicate", "better", "improve", "numbered", "wording", "steps",
}
_COMMAND_FORMAT_WORDS = {
    "email", "mail", "bullet", "bullets", "bulleted", "list", "points", "prompt", "note", "notes",
    "message", "chat", "msg", "text", "post", "summary", "steps",
}
# Words that may legitimately continue a format phrase that is already
# complete ("text message", "bullet points", "linkedin post", "fix grammar
# only", "email in my work style").
_FORMAT_CONTINUATION_WORDS = {
    "list", "points", "steps", "message", "msg", "chat", "post", "only", "formal", "professional",
    "casual", "friendly", "conversational", "excited", "confident", "persuasive", "playful",
    "short", "shorter", "concise", "brief", "detailed", "summary",
}


def _mask_quoted(text: str) -> str:
    """Blank out quoted spans so wake-phrase searches ignore them."""
    return _QUOTED_SPAN_RE.sub(lambda m: " " * len(m.group(0)), text)


def _is_wake_at(text: str, match: re.Match) -> bool:
    """'Hey/Ok Voice Flow' always wakes (mishearings tolerated); a bare
    'voice flow' needs a command continuation immediately after it (comma or
    imperative verb) and must not carry a trailing 's'."""
    sentence_start = max(text.rfind(".", 0, match.start()), text.rfind("!", 0, match.start()), text.rfind("?", 0, match.start())) + 1
    sentence_prefix = text[sentence_start:match.start()]
    if _REPORTED_WAKE_PREFIX_RE.search(sentence_prefix) or re.search(
        r"\b(?:if|when|unless|whether)\s+(?:i|you|we|they|someone)\s+"
        r"(?:say|said|says|mention|mentioned|use|used|hear|heard)\b",
        sentence_prefix,
        re.IGNORECASE,
    ):
        return False
    matched = match.group(0).lower()
    if re.fullmatch(r"voice[\s-]?low", matched, re.IGNORECASE):
        # "Voicelow" / "Voice low" is a specific ASR substitution, not a
        # general wake phrase. Accept it only at the start of a clause and
        # when a known imperative follows immediately, so filenames, URLs,
        # and ordinary mentions stay in the dictated text.
        clause_prefix = text[sentence_start:match.start()]
        if not re.fullmatch(r"\s*(?:(?:um+|uh+|well|so|okay|ok)\s*[,.:!?\-—]?\s*)*", clause_prefix, re.I):
            return False
        return bool(_PREFIX_ONLY_WAKE_CONTINUATION_RE.match(text[match.end():]))
    if re.fullmatch(
        r"(?:hey|ok|okay)\s*[,.:!\-—]?\s*voice[\s-]?low", matched, re.IGNORECASE
    ):
        # The same literal alias can follow an explicit wake prefix, but it
        # still requires a known command immediately after the alias.
        return bool(_PREFIX_ONLY_WAKE_CONTINUATION_RE.match(text[match.end():]))
    if re.fullmatch(
        r"(?:hey|ok|okay)\s*[,.:!\-—]?\s*vice[\s\-]{0,3}flows?",
        matched,
        re.IGNORECASE,
    ):
        # "Vice Flow" is a specific ASR substitution. Require an explicit
        # wake prefix and a known imperative immediately after the alias.
        return bool(_PREFIX_ONLY_WAKE_CONTINUATION_RE.match(text[match.end():]))
    if re.fullmatch(
        r"(?:hey|ok|okay)\s*[,.:!\-—]?\s*(?:why|wise|boys?|nice|choice|voice)[\s\-]{0,3}(?:slow|flo|flu|flows?)",
        matched,
        re.IGNORECASE,
    ) and not re.search(r"voice[\s\-]{0,3}flows?$", matched):
        return bool(_PREFIX_ONLY_WAKE_CONTINUATION_RE.match(text[match.end():]))
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
    ("work_message", re.compile(r"\b(?:work|slack|teams)\s+(?:message|chat|msg)\b", re.I)),
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
    ("numbered_list", re.compile(r"\bnumbered\s+(?:list|points|steps)\b", re.I)),
    ("bullet_list", re.compile(
        r"\bbullets?\b|\bbullet(?:ed)?\s+(?:list|points)\b"
        r"|\b(?:make|turn|convert)\s+(?:this|it)\s+(?:into\s+)?(?:a\s+)?list\b",
        re.I)),
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
_LENGTH_DETAILED_RE = re.compile(r"\b(?:longer|(?:more\s+)?detailed|expand)\b", re.I)
_CLARITY_RE = re.compile(r"\b(?:clearer|easier\s+to\s+(?:read|understand)|simpler|simplify)\b", re.I)
_IMPROVE_RE = re.compile(r"\b(?:sound\s+better|better|improve|polish(?:ed)?)\b", re.I)
_GRAMMAR_RE = re.compile(r"\bfix\s+(?:the\s+)?grammar\b", re.I)
_DEDUPE_RE = re.compile(r"\bremove\s+(?:the\s+)?(?:repetit(?:ion|ive)|duplicates?|duplication)\b", re.I)
# Only consulted after _COMMAND_SHAPE_RE accepted the clause, so a dictated
# mention of "the summary" in ordinary content is never parsed.
_SUMMARIZE_RE = re.compile(r"\b(?:summari[sz]e|summary|tl;?\s?dr)\b", re.I)
# "less formal", "not so formal", "don't make it formal": lower the register.
_REGISTER_DOWN_RE = re.compile(
    r"\b(?:less|not\s+(?:so|too|that))\s+(?:formal|professional|stiff)\b"
    r"|\b(?:do\s+not|don['’]?t|never)\s+make\s+(?:it|this)\s+(?:sound\s+)?(?:too\s+|so\s+)?(?:formal|professional)\b",
    re.I,
)
# "less casual", "not so casual", "don't make it casual": raise the register.
_REGISTER_UP_RE = re.compile(
    r"\b(?:less|not\s+(?:so|too|that))\s+(?:casual|informal|relaxed)\b"
    r"|\b(?:do\s+not|don['’]?t|never)\s+make\s+(?:it|this)\s+(?:sound\s+)?(?:too\s+|so\s+)?(?:casual|informal)\b",
    re.I,
)
# Commands this processor recognises but no writing model may perform.
_UNSUPPORTED_RE = re.compile(
    r"^\s*(?:please\s+)?(?:(?:can|could|would)\s+you\s+(?:please\s+)?)?"
    r"(?:translate|answer|reply\s+to|respond\s+to|send|search(?:\s+for)?|look\s+up|google|delete|"
    r"email\s+(?:this|it)\s+to|post\s+(?:this|it)|schedule|call|open)\b",
    re.I,
)
# Constraint spans that belong to a command clause and have no structured
# field.  They are captured verbatim and removed from the content.
_CONSTRAINT_RE = re.compile(
    r"(?:,?\s*\b(?:but|and)\s+)?\b(?:"
    r"without\s+(?:any\s+)?[a-z\-]+(?:\s+(?:or|and)\s+[a-z\-]+)?(?:\s+lines?)?"
    r"|with\s+no\s+[a-z\-]+(?:\s+(?:or|and)\s+[a-z\-]+)?"
    r"|no\s+(?:hashtags|emojis?|subject(?:\s+line)?|greeting|sign[\s-]?off|bullets|headings|markdown)"
    r"|(?:do\s+not|don['’]?t)\s+(?:change|touch|remove|drop|add|use|include|mention)\s+(?:my\s+|the\s+|any\s+)?[a-z\-]+"
    r"|keep\s+(?!my\s+(?:wording|words|phrasing)\b)(?:both|all|every|the|my)\s+[a-z\-]+"
    r")",
    re.I,
)
# Inside a delimited command clause a constraint runs to the end of the clause
# or to the next joined command ("..., and make it short").
_CONSTRAINT_CLAUSE_RE = re.compile(
    _CONSTRAINT_RE.pattern + r"[^,;.!?]*?(?=\s+(?:and|but)\s+(?:make|turn|keep|use)\b|\s*[,;.!?]|\s*$)",
    re.I,
)
_REWRITE_RE = re.compile(r"^\s*(?:please\s+)?(?:rewrite|polish|clean\s+up)\b", re.I)
_INSTRUCTIONS_RE = re.compile(r"\bas\s+(?:clear\s+)?instructions\b", re.I)
_COMMAND_SHAPE_RE = re.compile(
    r"^\s*(?:please\s+)?(?:make|turn|use|write|create|change|rewrite|summari[sz]e|fix|"
    r"shorten|clean(?:\s+up)?|polish|convert|send|generate|draft|tighten|expand)\b"
    # A verified ASR substitution for "make this" used by the voice-log alias.
    r"|^\s*may\s+this\b"
    r"|^\s*keep\s+my\s+(?:wording|words|phrasing)\b"
    r"|^\s*remove\s+(?:the\s+)?(?:repetit(?:ion|ive)|duplicates?|duplication)\b"
    r"|^\s*(?:simplify|improve|format)\b"
    r"|^\s*(?:do\s+not|don['’]?t|never)\s+make\b"
    r"|^\s*(?:translate|answer|reply\s+to|respond\s+to|search|look\s+up|google|delete|schedule)\b"
    r"|^\s*don['’]t\s+rewrite\b"
    r"|^\s*(?:can|could|would)\s+you\s+(?:please\s+)?"
    r"(?:make|turn|use|write|create|change|rewrite|summari[sz]e|fix|shorten|clean(?:\s+up)?|"
    r"polish|convert|send|generate|draft|tighten|expand)\b"
    r"|^\s*(?:always|from\s+now\s+on|remember\s+(?:this|that)|"
    r"save\s+(?:this|that)(?:\s+style)?)\s+(?:please\s+)?"
    r"(?:make|turn|use|write|create|rewrite|summari[sz]e|fix|shorten|"
    r"clean(?:\s+up)?|polish|convert|send|generate|draft)\b",
    re.I,
)
_PERSISTENT_RE = re.compile(
    r"\b(?:always|from\s+now\s+on|remember\s+(?:this|that)|save\s+(?:this|that)(?:\s+style)?)\b", re.I
)
_SCOPE_NEXT_RE = re.compile(
    r"\b(?:what|whatever)\s+(?:i|i'll)\s+(?:say|speak|dictate)\s+next\b"
    r"|\bmy\s+next\s+dictation\b|\bthe\s+next\s+one\b",
    re.I,
)
_KEEP_WORDING_RE = re.compile(r"\bkeep\s+my\s+(?:wording|words|phrasing)\b|\bdon'?t\s+rewrite\b", re.I)
_NEGATED_KEEP_WORDING_RE = re.compile(
    r"\b(?:do\s+not|don'?t|never)\s+keep\s+my\s+(?:wording|words|phrasing)\b", re.I
)
# Corrective markers: later register words override earlier ones (spec §24).
_CORRECTION_RE = re.compile(r"\b(?:actually|no\s+wait|I\s+mean|instead)\b", re.I)
# A plain "and" between a formality and a tone word is a genuine contradiction
# (spec §24); "but"/"yet" merges them as separate dimensions (spec §25).
_REGISTER_JOINER_RE = re.compile(
    r"\b(?:formal|professional)\b(?:\s+\w+){0,2}?\s+and\s+(?:\s*\w+\s+){0,2}?(?:casual|relaxed|informal)\b"
    r"|\b(?:casual|relaxed|informal)\b(?:\s+\w+){0,2}?\s+and\s+(?:\s*\w+\s+){0,2}?(?:formal|professional)\b",
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
    # A wake phrase can also precede ordinary dictation. Require a recognized
    # command lead before treating format words mentioned in that dictation
    # (for example, "the email from Morgan") as instructions.
    if not _COMMAND_SHAPE_RE.match(text):
        return VoiceCommand(raw_phrase=text)
    if _UNSUPPORTED_RE.match(text):
        return VoiceCommand(raw_phrase=text, operation="unsupported")
    lowered = text.lower()
    # Free-text constraints are captured verbatim, then blanked so their words
    # ("don't change my promise", "keep both deadlines") are not parsed as
    # register, format, or keep-wording commands.
    constraints: list[str] = []
    for m in _CONSTRAINT_CLAUSE_RE.finditer(lowered):
        span = re.sub(r"^\s*,?\s*(?:but|and)\s+", "", text[m.start():m.end()].strip()).strip(" ,.")
        if span:
            constraints.append(span)
    lowered = _CONSTRAINT_CLAUSE_RE.sub(lambda m: " " * len(m.group(0)), lowered)
    register_shift = None
    if _REGISTER_DOWN_RE.search(lowered):
        register_shift = "relaxed"
        lowered = _REGISTER_DOWN_RE.sub(lambda m: " " * len(m.group(0)), lowered)
    elif _REGISTER_UP_RE.search(lowered):
        register_shift = "professional"
        lowered = _REGISTER_UP_RE.sub(lambda m: " " * len(m.group(0)), lowered)
    preserve_wording = bool(_KEEP_WORDING_RE.search(lowered)) and not bool(
        _NEGATED_KEEP_WORDING_RE.search(lowered)
    )

    overrides: dict[str, str] = {}
    ambiguous = False

    # -- format / context reference -------------------------------------------------
    fmt, _ = _extract_format(lowered)
    context_ref = _extract_context_reference(lowered)
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
    if _IMPROVE_RE.search(lowered):
        overrides.setdefault("grammar", "fix")
        overrides.setdefault("clarity", "improved")

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

    if register_shift:
        overrides["formality"] = register_shift

    persistent = bool(_PERSISTENT_RE.search(lowered))
    if persistent and context_ref is None:
        scope_word = re.search(r"\b(e-?mails?|work\s+messages?|personal\s+messages?)\b", lowered)
        if scope_word:
            word = scope_word.group(1)
            context_ref = "email" if "mail" in word else ("work" if word.startswith("work") else "personal")

    has_intent = bool(fmt or context_ref or overrides or operation != "rewrite" or preserve_wording or constraints)
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
        persistent_change=persistent,
        ambiguous=ambiguous,
        preserve_wording=preserve_wording,
        constraints=tuple(constraints),
    )


def _split_unpunctuated_command(after_wake: str) -> tuple[str, str]:
    """Split an ASR run-on ``command content`` without deleting content.

    We only split after a known intent and only while it remains close to the
    wake phrase.  A command with no safe boundary remains unsplit, which is
    preferable to silently losing dictated text.
    """
    polite_prefix = _POLITE_COMMAND_PREFIX_RE.match(after_wake)
    if polite_prefix:
        suffix = after_wake[polite_prefix.end():]
        # Accept one explicit polite wrapper. Repeated wrappers are not a
        # natural command shape; preserve them whole instead of recursively
        # walking an unbounded user-controlled prefix chain.
        if _POLITE_COMMAND_PREFIX_RE.match(suffix):
            return after_wake.strip(), ""
        suffix_command, content = _split_unpunctuated_command(suffix)
        if suffix_command and _has_any_intent(_parse_command(suffix_command)):
            return after_wake[:polite_prefix.end()] + suffix_command, content

    tokens = list(re.finditer(r"[A-Za-z]+(?:'[A-Za-z]+)?", after_wake))
    if not tokens or tokens[0].group(0).casefold() not in _COMMAND_START_WORDS:
        return after_wake.strip(), ""

    consumed_end = 0
    saw_intent = False
    saw_format = False
    index = 0
    while index < len(tokens) and index < _MAX_UNPUNCTUATED_COMMAND_WORDS:
        token = tokens[index].group(0).casefold()
        # Scope suffixes are command metadata, not the next dictated sentence.
        # Match complete explicit phrases only; an ordinary "for Alex" stays
        # content. Preserve the original offsets for punctuation and payloads.
        if saw_intent:
            scope_suffix = re.match(
                r"(?:for\s+)?my\s+next\s+dictation\b|from\s+now\s+on\b",
                after_wake[tokens[index].start():], re.I,
            )
            if scope_suffix:
                consumed_end = tokens[index].start() + scope_suffix.end()
                while index < len(tokens) and tokens[index].end() <= consumed_end:
                    index += 1
                continue
            if token == "style" and _extract_context_reference(after_wake[:consumed_end]):
                consumed_end = tokens[index].end()
                index += 1
                continue
        # A constraint span directly after a recognised command belongs to the
        # command ("make this a linkedin post without hashtags ...").  Only the
        # closed constraint grammar is consumed; anything else is content.
        if saw_intent:
            constraint = _CONSTRAINT_RE.match(after_wake[tokens[index].start():])
            if constraint and token in {"without", "with", "no", "don't", "do", "keep", "but", "and"}:
                consumed_end = tokens[index].start() + constraint.end()
                while index < len(tokens) and tokens[index].end() <= consumed_end:
                    index += 1
                continue
            style_ref = re.match(r"in\s+my\s+(?:usual\s+|normal\s+)?(?:email|work|personal|other)\s+style\b",
                                 after_wake[tokens[index].start():], re.I)
            if style_ref:
                consumed_end = tokens[index].start() + style_ref.end()
                while index < len(tokens) and tokens[index].end() <= consumed_end:
                    index += 1
                continue
            register = re.match(r"(?:less|more)\s+(?:formal|professional|casual)\b",
                                after_wake[tokens[index].start():], re.I)
            if register:
                consumed_end = tokens[index].start() + register.end()
                while index < len(tokens) and tokens[index].end() <= consumed_end:
                    index += 1
                continue
        if token in _COMMAND_SYNTAX_WORDS or token in _COMMAND_START_WORDS:
            # Once a format is complete, only a format continuation word
            # ("text message", "bullet points", "grammar only") or an explicit
            # joined command ("and make it short", "but keep my wording") may
            # extend it.  This is what prevents "email Alex the short report"
            # from swallowing user content.
            prev_token = tokens[index - 1].group(0).casefold() if index else ""
            if saw_intent and token in _COMMAND_START_WORDS and token not in _COMMAND_INTENT_WORDS \
                    and prev_token not in {"and", "but", "please", "to", "you", "actually", "instead", "rather", "no", "wait", "mean"}:
                # A new verb after a complete command starts the dictation
                # ("make it shorter send the quote to priya").
                break
            if saw_format and token not in _FORMAT_CONTINUATION_WORDS:
                prev = tokens[index - 1].group(0).casefold() if index else ""
                joined = prev in {"and", "but"} and token in {"make", "turn", "use", "keep"}
                if not joined:
                    break
                # A joined command starts a fresh phrase ("and make it short").
                saw_format = False
            consumed_end = tokens[index].end()
            saw_intent = saw_intent or token in _COMMAND_INTENT_WORDS
            saw_format = saw_format or token in _COMMAND_FORMAT_WORDS
            index += 1
            continue
        if token in {"but", "and", "actually", "instead", "rather"}:
            next_word = tokens[index + 1].group(0).casefold() if index + 1 < len(tokens) else ""
            if not saw_intent or next_word not in {"keep", "make", "turn", "use", "formal", "professional", "casual", "friendly", "conversational", "excited", "without", "don't", "no"}:
                break
            consumed_end = tokens[index].end()
            index += 1
            continue
        if token == "keep" and saw_intent:
            following = [tokens[pos].group(0).casefold() for pos in range(index + 1, min(index + 3, len(tokens)))]
            if following[:1] == ["my"] and len(following) > 1 and following[1] in {"wording", "words", "phrasing"}:
                consumed_end = tokens[index + 2].end()
                index += 3
                continue
        break

    if not saw_intent or not consumed_end:
        return after_wake.strip(), ""
    # Function words consumed at the very end of the command belong to the
    # dictation that follows ("make it short the meeting ..."): give them back.
    head_tokens = [t for t in tokens if t.end() <= consumed_end]
    while len(head_tokens) > 1 and head_tokens[-1].group(0).casefold() in {"a", "an", "the", "my", "as", "into", "and", "but"}:
        consumed_end = head_tokens[-1].start()
        head_tokens.pop()
    head = after_wake[:consumed_end].strip(" ,:;.-?!")
    parsed = _parse_command(head)
    if not _has_any_intent(parsed):
        return after_wake.strip(), ""
    return head, after_wake[consumed_end:].lstrip(" ,:;.-?!")


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def _find_legacy_wake(text: str, masked: str):
    for match in _WAKE_RE.finditer(masked):
        if _is_wake_at(text, match):
            return match
    return None


def _reported_before(text: str, start: int) -> bool:
    sentence_start = max(text.rfind(".", 0, start), text.rfind("!", 0, start), text.rfind("?", 0, start)) + 1
    prefix = text[sentence_start:start]
    return bool(_REPORTED_WAKE_PREFIX_RE.search(prefix) or re.search(
        r"\b(?:if|when|unless|whether)\s+(?:i|you|we|they|someone)\s+"
        r"(?:say|said|says|mention|mentioned|use|used|hear|heard)\b",
        prefix, re.IGNORECASE,
    ))


def _make_custom_finder(activation):
    from voice_flow.activation import BARE_NAME_CONTINUATION_RE, compile_matchers

    matchers = compile_matchers(activation)

    def find(text: str, masked: str):
        best = None
        for pattern, bare in matchers:
            for match in pattern.finditer(masked):
                if _reported_before(text, match.start()):
                    continue
                if bare:
                    sentence_start = max(text.rfind(".", 0, match.start()), text.rfind("!", 0, match.start()),
                                         text.rfind("?", 0, match.start()), text.rfind(",", 0, match.start())) + 1
                    clause_prefix = text[sentence_start:match.start()]
                    if not re.fullmatch(r"\s*(?:(?:um+|uh+|well|so|okay|ok|and|also)\s*[,.:!?\-—]?\s*)*", clause_prefix, re.I):
                        continue
                    if not BARE_NAME_CONTINUATION_RE.match(text[match.end():]):
                        continue
                if best is None or match.start() < best.start():
                    best = match
                break
        return best

    return find


def _merge_commands(first: VoiceCommand, second: VoiceCommand) -> VoiceCommand:
    """Merge two wake commands from one utterance; the later one wins per field."""
    overrides = dict(first.overrides)
    overrides.update(second.overrides)
    operation = second.operation if second.operation != "rewrite" else first.operation
    if "unsupported" in (first.operation, second.operation) and operation == "unsupported":
        operation = first.operation if first.operation not in ("rewrite", "unsupported") else operation
    return VoiceCommand(
        raw_phrase=f"{first.raw_phrase} | {second.raw_phrase}",
        scope=second.scope if second.scope != "current" else first.scope,
        operation=operation,
        format=second.format or first.format,
        context_reference=second.context_reference or first.context_reference,
        overrides=overrides,
        persistent_change=first.persistent_change or second.persistent_change,
        ambiguous=first.ambiguous or second.ambiguous,
        preserve_wording=first.preserve_wording or second.preserve_wording,
        constraints=tuple(first.constraints) + tuple(second.constraints),
    )


def parse_instruction(instruction: str) -> VoiceCommand | None:
    """Parse an instruction a host already separated from the content.

    For integrations that collect the instruction through their own UI (a text
    box, a button, a different hotkey).  No wake phrase is involved.  Returns
    None when the text is not a recognised writing instruction; the host may
    then pass it verbatim as VF-1 ``[Instruction]`` text.
    """
    if not instruction or not str(instruction).strip():
        return None
    parsed = _parse_command(str(instruction).strip().rstrip(".!"))
    return parsed if _has_any_intent(parsed) else None


def detect_voice_command(transcript: str, activation=None) -> CommandDetection:
    """Split a transcript into (content, command).

    ``activation`` is an :class:`voice_flow.activation.ActivationConfig`;
    ``None`` keeps the historical "Hey Voice Flow" behaviour.  With
    ``activation.enabled`` false the processor runs in plain dictation mode.
    Up to three wake commands in one utterance are merged (later wins).

    Returns ``command=None`` for ordinary dictation. Never raises on odd
    input by contract; callers still wrap in try/except (spec §49).
    """
    if activation is not None and not getattr(activation, "enabled", True):
        if transcript is None:
            return CommandDetection(content="", command=None)
        return CommandDetection(content=str(transcript), command=None)
    if activation is None or getattr(activation, "legacy_voice_flow", False):
        finder = _find_legacy_wake
    else:
        finder = _make_custom_finder(activation)
    first = _detect_once(transcript, finder)
    command, content = first.command, first.content
    rounds = 0
    while command is not None and content and rounds < 2:
        nxt = _detect_once(content, finder)
        if nxt.command is None:
            break
        command = _merge_commands(command, nxt.command)
        content = nxt.content
        rounds += 1
    return CommandDetection(content=content, command=command)


def _detect_once(transcript: str, finder) -> CommandDetection:
    """One wake-phrase pass (the historical detector, with a pluggable finder)."""
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
    wake = finder(text, masked)
    if wake is None:
        return CommandDetection(content=text, command=None)

    starts_begin = _starts_as_beginning(text, wake.start())

    if starts_begin:
        # Command clause = the first sentence after the wake phrase.
        after_wake = text[wake.end():].lstrip(" ,.:!-—")
        sentence = _SENTENCE_END_RE.search(after_wake)
        if sentence:
            sentence_clause = after_wake[:sentence.end()].strip()
            clause, implicit_content = _split_unpunctuated_command(sentence_clause)
            content = " ".join(part for part in (implicit_content, after_wake[sentence.end():].strip()) if part)
        else:
            clause, content = _split_unpunctuated_command(after_wake)
    else:
        # Ending (or mid) command: the clause runs from the wake phrase to the
        # end of the dictation; everything before it is content.
        before = text[:wake.start()].strip()
        after_wake = text[wake.end():].lstrip(" ,.:!-—")
        sentence = _SENTENCE_END_RE.search(after_wake)
        if sentence:
            clause = after_wake[:sentence.end()].strip()
            trailing_unpunctuated = ""
        else:
            clause, trailing_unpunctuated = _split_unpunctuated_command(after_wake)
        if sentence and after_wake[sentence.end():].strip():
            # Wake phrase in the middle: keep trailing content after the clause.
            content = (before + " " + after_wake[sentence.end():].strip()).strip()
        else:
            content = " ".join(part for part in (before, trailing_unpunctuated) if part)
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
    if not (content or "").strip() and _uncovered_command_words(clause):
        # The clause holds words that are not part of any command phrase and
        # no safe boundary separated them: segmentation is ambiguous.  Never
        # delete them.  An unsupported command keeps its words as dictation
        # (the host shows a notice); otherwise the whole utterance stays
        # plain dictation.
        if command.operation == "unsupported":
            return CommandDetection(content=clause.strip(), command=command)
        return CommandDetection(content=text, command=None)
    return CommandDetection(content=content if content else "", command=command)


_COVERAGE_EXTRA = {
    "hey", "voice", "flow", "um", "uh", "so", "okay", "ok", "well", "and", "but", "actually", "instead",
    "rather", "can", "could", "would", "you", "always", "from", "now", "on", "remember", "save", "that",
    "next", "dictation", "for", "what", "whatever", "i", "i'll", "say", "speak", "dictate", "usual",
    "normal", "regular", "other", "of", "to", "do", "not", "never", "too", "is", "one", "emails", "e-mails",
    "messages", "prompts", "posts", "lists", "texts", "chats", "mails", "my", "me", "please", "be", "sound", "more",
    "sure", "really", "just", "little", "bit", "lot", "much", "way", "version", "prom",
}


def _uncovered_command_words(clause: str) -> list[str]:
    """Words of a command clause that no command grammar accounts for."""
    lowered = _CONSTRAINT_RE.sub(" ", clause.lower())
    lowered = re.sub(r"\bin\s+my\s+(?:usual\s+|normal\s+)?(?:email|work|personal|other)\s+style\b", " ", lowered)
    vocab = (_COMMAND_START_WORDS | _COMMAND_SYNTAX_WORDS | _COMMAND_INTENT_WORDS | _COMMAND_FORMAT_WORDS
             | _FORMAT_CONTINUATION_WORDS | _COVERAGE_EXTRA | set(_TONE_WORDS) | set(_FORMALITY_WORDS))
    words = re.findall(r"[a-z]+(?:['’][a-z]+)?", lowered)
    return [w for w in words if w.replace("’", "'") not in vocab]


def _has_any_intent(command: VoiceCommand) -> bool:
    return bool(
        command.format
        or command.context_reference
        or command.overrides
        or command.operation != "rewrite"
        or command.persistent_change
        or command.preserve_wording
        or bool(getattr(command, "constraints", ()))
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

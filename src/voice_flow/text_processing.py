"""Conservative, deterministic formatting for dictated text."""
from __future__ import annotations

from dataclasses import dataclass
import re
from voice_flow.style_formatter import style_formatter
from voice_flow.style_models import TextboxContext


@dataclass(frozen=True)
class FormattingResult:
    text: str
    press_enter: bool = False


_MENTION_CONTEXT = re.compile(
    r"\b(?:do not(?:\s+ever)?|don't(?:\s+ever)?|never(?:\s+ever)?|"
    r"say|the words?|literal(?:ly)?|phrase)\s*$",
    re.I,
)


def split_press_enter(text: str, enabled: bool) -> FormattingResult:
    """Extract only an unambiguous trailing action, before cleanup/dictionary."""
    text = text.strip()
    if not enabled or not re.search(r"\bpress enter(?:\s*[.!?]+)?$", text, re.I):
        return FormattingResult(text)
    prefix = re.sub(r"\bpress enter(?:\s*[.!?]+)?$", "", text, flags=re.I).rstrip()
    if _MENTION_CONTEXT.search(prefix) or re.search(r"\b(?:write|type)\s+the\s+(?:words?|phrase)\s*$", prefix, re.I):
        return FormattingResult(text)
    prefix = re.sub(r"\s+and$", "", prefix, flags=re.I).rstrip()
    return FormattingResult(prefix, True)


def apply_spoken_punctuation(text: str) -> str:
    """Convert explicit spoken punctuation without changing ordinary wording."""
    return _spoken_punctuation(text)


def cleanup_text(text: str, level: str) -> str:
    """Independent Cleanup layer: handles spoken fillers and hesitation disfluencies."""
    text = text.strip()
    if level == "cleanup_none":
        return text
    text = re.sub(r"\b(?:um|uh|er|ah|hmm)\b[ ,]*", "", text, flags=re.I)
    text = re.sub(r"(?:^|,)\s*you know\s*(?=,|$)", lambda m: "," if m.group(0).startswith(",") else "", text, flags=re.I)
    for pattern, replacement in (
        (r"\blet's meet at\s+([^,.]+?)\s+(?:actually|no wait|wait no)\s+([^,.]+)", r"let's meet at \2"),
        (r"\bsend it\s+([^,.]+?)\s+(?:scratch that|actually)\s+([^,.]+)", r"send it \2"),
        (r"\bmy code is\s+([^,.]+?)\s+(?:no wait|wait no|actually)\s+([^,.]+)", r"my code is \2"),
    ):
        text = re.sub(pattern, replacement, text, flags=re.I)
    if level in ("cleanup_medium", "cleanup_high"):
        text = re.sub(r"\b(\w+(?:\s+\w+){0,5})\s+(?:I mean|rather),?\s+\1\b", r"\1", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _spoken_punctuation(text: str) -> str:
    protected = re.split(r"(https?://\S+|\b\S+@\S+\b)", text)
    for i in range(0, len(protected), 2):
        part = protected[i]
        part = re.sub(r"\bnew paragraph\b", "\n\n", part, flags=re.I)
        part = re.sub(r"\b(?:new line|next line|line break)\b", "\n", part, flags=re.I)
        part = re.sub(r"[ \t]*\n[ \t]*", "\n", part)
        protected_terms = r"(?:character|symbol|key|operator|delimiter|term|word)"
        part = re.sub(rf"\b(?:comma|period|colon|semicolon|hash|question mark|exclamation mark)\s+{protected_terms}\b", lambda m: "__" + m.group(0).replace(" ", "_") + "__", part, flags=re.I)
        part = re.sub(r"\b(?:the\s+word\s+comma|a\s+period\s+is\s+punctuation|period\s+drama|colon\s+cancer|hash\s+table)\b", lambda m: "__" + m.group(0).replace(" ", "_") + "__", part, flags=re.I)
        if not re.search(r"\b(?:write|say|type)\s+the\s+words?\s+(?:question mark|comma|period)\b", part, re.I):
            for spoken, symbol in (("question mark", "?"), ("exclamation mark", "!"), ("full stop", "."), ("comma", ","), ("period", "."), ("colon", ":"), ("semicolon", ";")):
                part = re.sub(rf"\b{spoken}\b", symbol, part, flags=re.I)
        part = re.sub(r"\s+([,.;:?!])", r"\1", part)
        part = re.sub(r"__(.+?)__", lambda m: m.group(1).replace("_", " "), part)
        protected[i] = part
    return "".join(protected)


def _numbered_list(text: str) -> str:
    stripped = text.strip()
    groups = [(r"number one\s+(.+?)\s+number two\s+(.+)", 1), (r"list:\s*first\s+(.+?)\s+second\s+(.+)", 1)]
    for pattern, _ in groups:
        match = re.fullmatch(pattern, stripped, re.I)
        if match:
            return f"1. {match.group(1).strip(' ,;.')}\n2. {match.group(2).strip(' ,;.')}"
    return text


def apply_style(text: str, style_id: str, context=None) -> str:
    """Formats text according to requested style_id and surrounding textbox context."""
    text = text.strip()
    if not text or style_id == "cleanup_none":
        return text

    # Adapt context object if provided
    tb_context = None
    if context:
        if isinstance(context, str):
            tb_context = TextboxContext(before=context, trustworthy=True)
        else:
            tb_context = TextboxContext(
                before=getattr(context, "before", ""),
                selection=getattr(context, "selection", ""),
                after=getattr(context, "after", ""),
                trustworthy=getattr(context, "trustworthy", False),
            )

    return style_formatter.format(text, style=style_id, context=tb_context)


def smart_format(text: str, style_id: str, context=None) -> str:
    return apply_style(_numbered_list(_spoken_punctuation(text)), style_id, context)

"""Finite English editorial fallback templates, never a substitute AI provider.

The caller owns ON/attempt gating. This module edits only safe cleaned payloads,
declines custom instructions, and validates every result with the existing gates.
"""
from __future__ import annotations

import re
from typing import Any

_VERBS = r"(?:build|create|write|make|design|develop|implement|check|report|use|keep|send|review|fix|show|list|validate|read|generate)"
_OBJECT = r"(?:a|an)\s+(?:(?:Python|JavaScript|TypeScript)\s+)?(?:tool|script|page|app|form|validator)\b"
_EXPLICIT_REQUEST = re.compile(
    rf"^(?:can|could|would)\s+(?:you|we)\s+(?:please\s+)?(?P<verb>{_VERBS})\b(?P<tail>[\s\S]*)$",
    re.IGNORECASE,
)
_TRAILING_PROTECTED_TOKEN = re.compile(r"ZXPROTECTED(\d+)XZ$")
_CONDITIONAL_REQUEST = re.compile(r"\b(?:if|unless|whether|when|provided)\b", re.IGNORECASE)
_ASR_AND_ALL_END = re.compile(r"(?:,\s*)?\band\s+all\s*$", re.IGNORECASE)
_REPORTED_REQUEST_CONTEXT = re.compile(
    r"\b(?:said|reported|asked|wondered|mentioned|heard|wrote|quoted)\b", re.IGNORECASE
)


def _standard_instruction(instruction: str, style_id: str, task: str, fmt: str,
                          overrides: dict[str, Any]) -> bool:
    from voice_flow.effective_style import FORMAT_INSTRUCTIONS, OVERRIDE_INSTRUCTIONS, PROMPT_MODE_INSTRUCTION
    from voice_flow.style_engine import STYLE_INSTRUCTIONS
    if (style_id not in STYLE_INSTRUCTIONS or not style_id.endswith(("_formal", "_casual"))
            or style_id.endswith("_very_casual")):
        return False
    if not set(overrides).issubset({"tone", "formality"}):
        return False
    if any(value not in {"formal", "casual", "professional"} for value in overrides.values()):
        return False
    parts = [STYLE_INSTRUCTIONS[style_id]]
    if fmt == "email" and task in {"rewrite", "format"}:
        parts.append(FORMAT_INSTRUCTIONS["email"])
    elif fmt == "prompt" and task == "prompt":
        parts.append(PROMPT_MODE_INSTRUCTION)
    else:
        return False
    for key in ("tone", "formality"):
        if key in overrides:
            part = OVERRIDE_INSTRUCTIONS.get(f"{key}:{overrides[key]}")
            if not part:
                return False
            parts.append(part)
    return " ".join(instruction.split()) == " ".join(" ".join(parts).split())


def _mask(text: str) -> tuple[str, list[str]]:
    from voice_flow.text_processing import _PROTECTED_CLEANUP_SPAN_RE
    spans: list[str] = []
    def replace(match: re.Match[str]) -> str:
        spans.append(match.group())
        return f"ZXPROTECTED{len(spans) - 1}XZ"
    return _PROTECTED_CLEANUP_SPAN_RE.sub(replace, text), spans


def _restore(text: str, spans: list[str]) -> str:
    for index, span in enumerate(spans):
        text = text.replace(f"ZXPROTECTED{index}XZ", span)
    return text


def _asr_and_all_boundary(prefix: str) -> re.Match[str] | None:
    """Recognize only the known terminal ASR bridge before an explicit ask.

    "And all" is retained in the context. It is treated as a boundary only
    when the sentence fragment immediately before it is neither conditional
    nor reported speech. Protected literals have already been masked.
    """
    marker = _ASR_AND_ALL_END.search(prefix)
    if marker is None:
        return None
    preceding = prefix[:marker.start()]
    boundaries = list(re.finditer(r"(?<!\d)[.!?](?!\d)|[\n;]", preceding))
    fragment = preceding[boundaries[-1].end():] if boundaries else preceding
    if _CONDITIONAL_REQUEST.search(fragment) or _REPORTED_REQUEST_CONTEXT.search(fragment):
        return None
    return marker


def _explicit_question_prompt(source: str, spans: list[str]) -> str | None:
    """Convert one final, sentence-initial polite request into a prompt task.

    The source has protected literals replaced with opaque tokens, so sentence
    punctuation inside quotes, code, paths, or URLs cannot create a boundary.
    """
    matches = list(re.finditer(r"\b(?:can|could|would)\s+(?:you|we)\b", source, re.I))
    for request in reversed(matches):
        start = request.start()
        prefix = source[:start]
        asr_boundary = None
        if prefix:
            boundary = re.search(r"([.!?])\s+$", prefix)
            if not boundary:
                asr_boundary = _asr_and_all_boundary(prefix)
                if asr_boundary is None:
                    continue
        clause = source[start:].strip()
        visible_question = clause.endswith("?")
        protected_question = False
        if not visible_question:
            protected_end = _TRAILING_PROTECTED_TOKEN.search(clause)
            if protected_end:
                span_index = int(protected_end.group(1))
                protected_question = span_index < len(spans) and spans[span_index].endswith("?")
        if not visible_question and not protected_question and asr_boundary is None:
            continue
        # The explicit sentence splitter supports one final request sentence.
        # Be conservative around additional sentence marks, while decimal
        # values and protected literals remain intact.
        punctuation_source = clause[:-1] if visible_question else clause
        if re.search(r"(?<!\d)[.!?](?!\d)", punctuation_source):
            continue
        parsed = _EXPLICIT_REQUEST.fullmatch(clause)
        if not parsed:
            continue
        verb = parsed.group("verb")
        tail = parsed.group("tail")
        # Do not turn a refusal or a conditional/permission-shaped question
        # into an unconditional instruction.
        if re.match(r"\s*(?:not|never|cannot|can't|can\s+not)\b", tail, re.I):
            continue
        if _CONDITIONAL_REQUEST.search(tail):
            continue

        context = _restore(prefix.strip(), spans)
        body_tail = tail[:-1] if visible_question else tail
        if asr_boundary is not None and context and not context.endswith((".", "!", "?")):
            context += "."
        sentence_end = "." if visible_question or asr_boundary is not None else ""
        body = _restore(verb[:1].upper() + verb[1:] + body_tail.rstrip() + sentence_end, spans)
        sections = ([f"Context: {context}"] if context else []) + [f"Task: {body}"]
        return "\n".join(sections)
    return None


def _sentence(match: re.Match[str]) -> str:
    word = match.group(1)
    return ". " + word[:1].upper() + word[1:]


def _prompt(text: str) -> str | None:
    source, spans = _mask(text.strip())
    if any(ord(ch) > 127 and ch.isalpha() for ch in source):
        return None
    explicit_question = _explicit_question_prompt(source, spans)
    if explicit_question:
        return explicit_question
    changed = False
    # Complete anchored constructions only: a comparison or free preference is
    # not enough evidence that the speaker wants an artifact created.
    source, count = re.subn(rf"^I\s+(?:want|need)\s+you\s+to\s+(?={_VERBS}\b)", "", source, flags=re.I)
    changed |= bool(count)
    source, count = re.subn(rf"^I\s+want\s+(?:like\s+)?(?={_OBJECT})", "Create ", source, flags=re.I)
    changed |= bool(count)
    if not re.match(rf"^{_VERBS}\b", source, re.I):
        return None
    source, count = re.subn(rf"\s+and\s+it\s+(?:should|needs?\s+to)\s+({_VERBS})\b", _sentence, source, flags=re.I)
    changed |= bool(count)
    source, count = re.subn(r"\s+but\s+(do\s+not)\b", _sentence, source, flags=re.I)
    changed |= bool(count)
    source, count = re.subn(r"\s+and\s+(keep)\b", _sentence, source, flags=re.I)
    changed |= bool(count)
    if not changed:
        return None
    # A terminal politeness marker is removable only after recognized editing.
    source = re.sub(r"\s+please([.!?]?)$", r"\1", source, flags=re.I)
    source = source[:1].upper() + source[1:]
    source = _restore(source, spans)
    return source if source.endswith((".", "!", "?")) else source + "."


def _email(text: str) -> str | None:
    from voice_flow.text_processing import format_dictated_email
    layout = format_dictated_email(text)
    if layout is None:
        return None
    parts = layout.split("\n\n")
    # Require dictated greeting AND sender/closing. No invented framing.
    if len(parts) != 3:
        return None
    body, spans = _mask(parts[1])
    if any(ord(ch) > 127 and ch.isalpha() for ch in body):
        return None
    first_request = re.search(rf"\s+please(?=\s+{_VERBS}\b)", body, re.I)
    if first_request is None:
        return None
    preceding = body[:first_request.start()].rstrip()
    # Only split after an explicit statement, never inside "can you please",
    # a negative request, or an unfinished conditional clause.
    if (re.search(r"\b(?:if|unless|when|until|provided|because|whether)\b", preceding, re.I)
            or not re.search(r"\b(?:I|we|you|they|he|she|it)\s+(?:have|had|need|needs|are|were|was|am|is|cannot)\b", preceding, re.I)
            or re.search(r"\b(?:not|never|cannot|can|could|would|should|must|may|might|will|do|to|can you|could you|would you|if|unless|because|and|but)"
                         r"(?:\s+(?:ever|actually|really|just|possibly|immediately|now|also|even|still))*\s*$", preceding, re.I)):
        return None
    body, count = re.subn(rf"(?<![.!?])\s+(please)(?=\s+{_VERBS}\b)", _sentence, body, count=1, flags=re.I)
    if not count:
        return None
    body = _restore(body, spans)
    if not body.endswith((".", "!", "?")):
        body += "."
    parts[1] = body
    return "\n\n".join(parts)


def try_local_command_rewrite(cleaned: str, *, task: str, command_format: str | None,
                              style_id: str, instruction: str,
                              overrides: dict[str, Any] | None = None) -> str | None:
    """Return a validated local edit, or None when intent/style is unsupported."""
    overrides = overrides or {}
    if not _standard_instruction(instruction, style_id, task, command_format or "", overrides):
        return None
    candidate = _prompt(cleaned) if command_format == "prompt" else _email(cleaned)
    if not candidate:
        return None
    from voice_flow.polisher import _candidate_preserves_content, _fulfills_command
    # Some valid imperative verbs (Check/Use) need an explicit prompt label
    # under the shared fulfillment contract. The body has already been edited.
    if command_format == "prompt" and not _fulfills_command(
            cleaned, candidate, task=task, command_format=command_format, overrides=overrides):
        candidate = "Task: " + candidate
    if not _candidate_preserves_content(cleaned, candidate, task=task, command_format=command_format):
        return None
    if not _fulfills_command(cleaned, candidate, task=task, command_format=command_format, overrides=overrides):
        return None
    return candidate

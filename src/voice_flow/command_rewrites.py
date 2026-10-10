"""Finite English editorial fallback templates, never a substitute AI provider.

The caller owns ON/attempt gating. This module edits only safe cleaned payloads,
declines custom instructions, and validates every result with the existing gates.
"""
from __future__ import annotations

import re
from typing import Any

_VERBS = r"(?:build|create|write|make|design|develop|implement|check|report|use|keep|send|review|fix|show|list|validate|read|generate)"
_OBJECT = r"(?:a|an)\s+(?:(?:Python|JavaScript|TypeScript)\s+)?(?:tool|script|page|app|form|validator)\b"


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


def _sentence(match: re.Match[str]) -> str:
    word = match.group(1)
    return ". " + word[:1].upper() + word[1:]


def _prompt(text: str) -> str | None:
    source, spans = _mask(text.strip())
    if any(ord(ch) > 127 and ch.isalpha() for ch in source):
        return None
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

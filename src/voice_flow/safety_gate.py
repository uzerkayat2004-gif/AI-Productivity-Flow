"""Deterministic Host-Side Factual Preservation Safety Gate (VF-1).

This module provides a deterministic runtime verification layer for Voice Flow.
It intercepts model-generated text (from S1-mini, Qwen3, or any downstream model)
and validates that critical facts are faithfully preserved:
  1. Numerical quantities (currencies, Indian lakh/crore formats, decimals, percentages)
  2. Critical identifiers (patient IDs, tracking numbers, invoices, codes)
  3. Negation polarity (preventing affirmative flipping of negative instructions)
  4. Entity and contact identifiers (emails, URLs)

If a generated rewrite corrupts, invents, or drops critical information,
the safety gate REJECTS the output and falls back to preserving the speaker's
original transcript, preventing silent data corruption.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from voice_flow.vf_checks import (
    CheckResult,
    _output_numbers,
    canonical_source,
    check_output,
    expand_contractions,
    normalize_canonical_equivalences,
    normalize_decimal_scales,
    number_values,
)

# Alphanumeric identifier codes: e.g. PR-94821, TRK-88204-X, INV-2026-99, SEC 10-K
IDENTIFIER_RE = re.compile(r"\b(?:[A-Z]{1,6}-\d+(?:-[A-Za-z0-9]+)?|[A-Z]{1,6}\s+\d+-[A-Za-z0-9]+)\b")

# Email addresses and URLs
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
URL_RE = re.compile(r"\bhttps?://[^\s/$.?#].[^\s]*\b|\bwww\.[^\s/$.?#].[^\s]*\b", re.I)

# Explicit negation tokens
NEGATION_TOKENS_RE = re.compile(
    r"\b(?:not|never|no|without|neither|nor|none|nobody|nothing|cannot|can't|won't|don't|doesn't|didn't|shouldn't|wouldn't|couldn't)\b",
    re.I,
)

# Control tags / prompt echo patterns
CONTROL_TAG_RE = re.compile(r"^cleanup(?:,\s*task:\s*\w+)?\.?\s*|^\[(?:Transcript|Instruction|Draft|Rules|VF-1)\]", re.I)


@dataclass
class SafetyGateDecision:
    """Outcome of the factual preservation safety gate check."""

    accepted: bool
    final_text: str
    source_preserved: bool = False
    rejection_reasons: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.accepted


def extract_identifiers(text: str) -> List[str]:
    """Extract structured entity codes like PR-94821, TRK-88204-X."""
    if not text:
        return []
    return IDENTIFIER_RE.findall(text)


def extract_contacts(text: str) -> List[str]:
    """Extract email addresses and URLs."""
    if not text:
        return []
    emails = EMAIL_RE.findall(text)
    urls = URL_RE.findall(text)
    return emails + urls


def check_numerical_preservation(source: str, candidate: str, task: str = "cleanup") -> tuple[bool, List[str]]:
    """Check that all numbers in source exist with matching value in candidate."""
    failures: List[str] = []
    src_canon, _ = canonical_source(source)
    if task == "prompt":
        src_canon = re.sub(
            r"^(?:can you\s+)?(?:make|create|write|give|generate)\s+(?:me\s+)?(?:a\s+)?prompt(?:\s+(?:for|in)\s+[^,:]+?)?\s+(?:that\s+asks\s+(?:it\s+)?to|that\s+asks\s+to|to)\s*[:\s]*",
            "",
            src_canon,
            flags=re.IGNORECASE,
        ).strip()
    src_nums = number_values(src_canon)

    # Strip prompt metadata tags before numerical extraction so that metadata tags
    # like [VF-1], [Task: cleanup], [Transcript], etc. do not pollute numerical analysis
    # (the '1' in VF-1 is a tag echo, not a corrupted numerical amount).
    cleaned_candidate = normalize_canonical_equivalences(candidate or "")
    cleaned_candidate = re.sub(
        r"\[(?:VF-1|Task:\s*\w+|Transcript|Rules|Instruction|Draft|Sender:[^\]]+|Recipient:[^\]]+)\]",
        "",
        cleaned_candidate,
        flags=re.IGNORECASE,
    )
    cleaned_candidate = re.sub(r"^cleanup(?:,\s*task:\s*\w+)?\.?\s*", "", cleaned_candidate, flags=re.IGNORECASE)

    out_nums = _output_numbers(cleaned_candidate)
    out_counter = Counter(out_nums)

    # 1. Missing numbers: every required number from source must exist in candidate
    for options in src_nums:
        if not any(out_counter.get(o) for o in options):
            sorted_opts = sorted(options, key=lambda x: (str(type(x)), x))
            failures.append(f"numerical_value_missing:{sorted_opts[0]}")

    # 2. Invented / altered numbers: candidate must not introduce new numerical magnitudes
    allowed: Set[Any] = set().union(*src_nums) if src_nums else set()
    list_markers = {int(n) for n in re.findall(r"(?m)^\s*(\d+)[.)]\s", cleaned_candidate)}

    cand_consumed = re.sub(r"(?<=\d),(?=\d)", "", normalize_decimal_scales(cleaned_candidate) or "")
    for m in re.finditer(r"(?<![\d.:])(\d+)(?![\d:])", cand_consumed):
        val = int(m.group(1))
        if val in list_markers:
            continue
        # Check against allowed values
        if allowed and not any(val == a or (isinstance(a, float) and int(a) == val) for a in allowed):
            failures.append(f"numerical_value_corrupted:{val}")

    return len(failures) == 0, failures


_PROMPT_DESTINATION_MODELS = {
    "GPT4", "GPT4O", "GPT35", "GPT3",
    "CLAUDE", "CLAUDE3", "CLAUDE35",
    "GEMINI", "LLAMA", "LLAMA3", "MISTRAL", "QWEN"
}


def check_identifier_preservation(source: str, candidate: str, task: str = "cleanup") -> tuple[bool, List[str]]:
    """Check that all structured codes (PR-94821, TRK-88204-X) remain intact.
    
    For prompt synthesis tasks, separates destination-model metadata (e.g. 'for GPT-4')
    from mandatory domain constraints (e.g. 'SEC 10-K').
    """
    failures: List[str] = []
    norm_source = normalize_canonical_equivalences(source)
    norm_cand = normalize_canonical_equivalences(candidate)

    if task in ("prompt", "format:prompt"):
        norm_source = re.sub(
            r"^(?:can you\s+)?(?:make|create|write|give|generate)\s+(?:me\s+)?(?:a\s+)?prompt(?:\s+(?:for|in)\s+[^,:]+?)?\s+(?:that\s+asks\s+(?:it\s+)?to|that\s+asks\s+to|to)\s*[:\s]*",
            "",
            norm_source,
            flags=re.IGNORECASE,
        ).strip()

    src_ids = extract_identifiers(norm_source)
    cand_ids = extract_identifiers(norm_cand)

    cand_normalized_tokens = {re.sub(r"[-_\s]", "", w).upper() for w in re.findall(r"\b[A-Za-z0-9_-]+\b", norm_cand or "")}

    for sid in src_ids:
        norm_sid = re.sub(r"[-_\s]", "", sid).upper()
        if task in ("prompt", "format:prompt") and norm_sid in _PROMPT_DESTINATION_MODELS:
            continue
        if sid in cand_ids:
            continue
        if norm_sid in cand_normalized_tokens:
            continue
        # Check if mutated or truncated
        matching = [cid for cid in cand_ids if cid.startswith(sid[:3])]
        if matching:
            failures.append(f"identifier_mutated:{sid}->{matching[0]}")
        else:
            failures.append(f"identifier_missing:{sid}")

    return len(failures) == 0, failures


def check_negation_preservation(source: str, candidate: str, task: str = "cleanup") -> tuple[bool, List[str]]:
    """Check that negative statements are not silently flipped to affirmative."""
    failures: List[str] = []
    src_canon, _ = canonical_source(source)
    src_negs = NEGATION_TOKENS_RE.findall(expand_contractions(src_canon))
    cand_negs = NEGATION_TOKENS_RE.findall(expand_contractions(candidate))

    if len(cand_negs) < len(src_negs):
        failures.append(f"negation_lost:{len(src_negs)}->{len(cand_negs)}")

    return len(failures) == 0, failures


def validate_and_gate_output(
    transcript: str,
    candidate_text: str,
    *,
    task: str = "cleanup",
    format: str | None = None,
    fmt: str | None = None,
    instruction: str | None = None,
    allow_fallback: bool = True,
) -> SafetyGateDecision:
    """Validate model output through the deterministic safety gate.

    If critical factual violations are detected, rejects the candidate output
    and preserves the original speaker transcript.
    """
    rejection_reasons: List[str] = []
    details: Dict[str, Any] = {}

    effective_fmt = fmt or format

    # Run check_output from vf_checks
    base_check: CheckResult = check_output(
        source=transcript,
        output=candidate_text,
        task=task,
        fmt=effective_fmt,
        instruction=instruction,
    )
    if not base_check.ok:
        rejection_reasons.extend(base_check.failures)

    # Specific numerical preservation gate
    nums_ok, num_fails = check_numerical_preservation(transcript, candidate_text, task=task)
    if not nums_ok:
        rejection_reasons.extend(num_fails)
    details["numerical_ok"] = nums_ok
    details["numerical_failures"] = num_fails

    # Specific identifier preservation gate
    ids_ok, id_fails = check_identifier_preservation(transcript, candidate_text, task=task)
    if not ids_ok:
        rejection_reasons.extend(id_fails)
    details["identifiers_ok"] = ids_ok
    details["identifier_failures"] = id_fails

    # Specific negation gate
    negs_ok, neg_fails = check_negation_preservation(transcript, candidate_text, task=task)
    if not negs_ok:
        rejection_reasons.extend(neg_fails)
    details["negation_ok"] = negs_ok
    details["negation_failures"] = neg_fails

    # Deduplicate rejection reasons
    unique_reasons = list(dict.fromkeys(rejection_reasons))

    if unique_reasons:
        # Critical failure detected: REJECT candidate and fall back to original transcript
        fallback_text = transcript.strip() if allow_fallback else candidate_text
        return SafetyGateDecision(
            accepted=False,
            final_text=fallback_text,
            source_preserved=True,
            rejection_reasons=unique_reasons,
            details=details,
        )

    # All checks passed: ACCEPT candidate
    return SafetyGateDecision(
        accepted=True,
        final_text=candidate_text.strip(),
        source_preserved=False,
        rejection_reasons=[],
        details=details,
    )

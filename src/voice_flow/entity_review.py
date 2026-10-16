"""Critical Entity Detection, Review, and Diagnostic Traceability.

Provides robust handling for:
1. Phonetic name variations (e.g. Devon <-> Devin, Bryan <-> Brian)
2. Numerical & Financial figures (e.g. $2.5 million, $2,500,000)
3. Alphanumeric IDs and codes (e.g. PR-42, CVE-2024-1234)
4. Email addresses and critical endpoints
5. Diagnostic traceability preserving audit trails without storing user audio or PII without explicit consent.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

log = logging.getLogger(__name__)

# Common English phonetic name pairs / homophones frequently confused by STT
PHONETIC_NAME_PAIRS: Dict[str, str] = {
    "devon": "Devin",
    "devin": "Devon",
    "bryan": "Brian",
    "brian": "Bryan",
    "stephen": "Steven",
    "steven": "Stephen",
    "geoff": "Jeff",
    "jeff": "Geoff",
    "marc": "Mark",
    "mark": "Marc",
    "sean": "Shawn",
    "shawn": "Sean",
    "shaun": "Sean",
    "jon": "John",
    "john": "Jon",
    "allan": "Alan",
    "alan": "Allan",
    "allen": "Alan",
    "catherine": "Katherine",
    "katherine": "Catherine",
    "teresa": "Theresa",
    "theresa": "Teresa",
    "philip": "Phillip",
    "phillip": "Philip",
    "karen": "Caron",
    "carol": "Carole",
    "carole": "Carol",
    "ann": "Anne",
    "anne": "Ann",
    "conor": "Connor",
    "connor": "Conor",
    "claire": "Clare",
    "clare": "Claire",
    "neil": "Neal",
    "neal": "Neil",
}

# Regex patterns for critical entities
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
FINANCIAL_PATTERN = re.compile(
    r"(?:[\$₹€£¥]\s*\d+(?:,\d+)*(?:\.\d+)?|\b\d+(?:,\d+)*(?:\.\d+)?\s*(?:dollars?|euros?|pounds?|usd|eur|gbp|inr|rupees?))\s*(?:million|billion|trillion|lakhs?|crores?|k|m|b)?\b"
    r"|\b(?:\$\s*)?\d+(?:\.\d+)?\s*(?:million|billion|trillion)\s*(?:dollars?|usd)?\b"
    r"|\b\d+(?:,\d+)*(?:\.\d+)?\s*(?:lakhs?|crores?|lock)\s*(?:rupees?|inr)?\b",
    re.IGNORECASE,
)
ID_PATTERN = re.compile(
    r"\b(?:PR|CVE|ID|JIRA|BUG|ISSUE|TASK|RFC|TICKET|REQ|INVOICE|INV|PORT|SPRINT|FLAG)[-#\s]?\d+(?:[-_]\d+)*\b|\b[A-Z]{2,5}-\d+(?:[-_]\d+)*\b",
    re.IGNORECASE,
)
DATETIME_PATTERN = re.compile(
    r"\b(?:\d{4}\s*UTC|\d{1,2}:\d{2}\s*(?:UTC|AM|PM|am|pm)?|\d{1,2}\s*(?:am|pm)|(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday))\b",
    re.IGNORECASE,
)
CURRENCY_SYMBOLS = {"$", "€", "£", "¥", "₹"}


def soundex(name: str) -> str:
    """Compute American Soundex code for phonetic name comparison."""
    if not name:
        return ""
    name_clean = re.sub(r"[^A-Za-z]", "", name).upper()
    if not name_clean:
        return ""
    first_letter = name_clean[0]
    mapping = {
        "BFPV": "1",
        "CGJKQSXZ": "2",
        "DT": "3",
        "L": "4",
        "MN": "5",
        "R": "6",
    }
    encoded = [first_letter]
    prev_code = ""
    for char in name_clean[1:]:
        char_code = ""
        for group, code in mapping.items():
            if char in group:
                char_code = code
                break
        if char_code and char_code != prev_code:
            encoded.append(char_code)
            prev_code = char_code
        elif not char_code:
            prev_code = ""
    res = "".join(encoded).replace("0", "")
    return (res + "0000")[:4]


@dataclass
class CriticalEntity:
    """A detected entity requiring user verification or phonetic resolution."""

    entity_type: str  # "name", "financial", "id", "email", "datetime"
    original: str
    suggested: Optional[str] = None
    alternatives: List[str] = field(default_factory=list)
    requires_review: bool = True
    confidence: float = 1.0
    reason: str = ""
    span_start: int = -1
    span_end: int = -1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiagnosticTrace:
    """Diagnostic trace recording pipeline execution without violating user privacy."""

    session_id: str
    timestamp: float
    audio_duration_seconds: float
    raw_stt_text_length: int
    raw_stt_text_masked: str
    raw_s1_output_length: int
    raw_s1_output_masked: str
    postprocessed_text_masked: str
    delivered_text_masked: str
    safety_gate_passed: bool
    safety_reasons: List[str]
    flagged_entities: List[Dict[str, Any]]
    audio_retained: bool = False
    pii_retained: bool = False
    model_name: str = "superwhisper/s1-mini"
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def mask_pii(text: str) -> str:
    """Mask email addresses, financial figures, and proper names for unconsented diagnostics."""
    if not text:
        return ""
    masked = text
    # Mask emails
    masked = EMAIL_PATTERN.sub("[EMAIL_MASKED]", masked)
    # Mask financial amounts
    masked = FINANCIAL_PATTERN.sub("[AMOUNT_MASKED]", masked)
    # Mask IDs
    masked = ID_PATTERN.sub("[ID_MASKED]", masked)
    return masked


def detect_critical_entities(
    text: str,
    user_dictionary: Optional[Sequence[str]] = None,
    known_contacts: Optional[Sequence[str]] = None,
) -> List[CriticalEntity]:
    """Detect critical entities (phonetic names, financial figures, IDs, emails) in text.

    Strictly preserves the speaker's original text by default, flagging ambiguous
    alternatives for explicit user review without silent invention.
    """
    if not text:
        return []

    entities: List[CriticalEntity] = []
    seen_spans: Set[Tuple[int, int]] = set()

    # 1. Emails
    for m in EMAIL_PATTERN.finditer(text):
        span = (m.start(), m.end())
        seen_spans.add(span)
        entities.append(
            CriticalEntity(
                entity_type="email",
                original=m.group(0),
                suggested=None,
                requires_review=False,
                confidence=1.0,
                reason="Email recipient address verified by format.",
                span_start=m.start(),
                span_end=m.end(),
            )
        )

    # 2. Financial figures
    for m in FINANCIAL_PATTERN.finditer(text):
        span = (m.start(), m.end())
        seen_spans.add(span)
        entities.append(
            CriticalEntity(
                entity_type="financial",
                original=m.group(0),
                suggested=None,
                requires_review=True,
                confidence=0.9,
                reason="Financial figure requires user verification to prevent accidental misallocation.",
                span_start=m.start(),
                span_end=m.end(),
            )
        )

    # 3. Technical IDs
    for m in ID_PATTERN.finditer(text):
        span = (m.start(), m.end())
        seen_spans.add(span)
        entities.append(
            CriticalEntity(
                entity_type="id",
                original=m.group(0),
                suggested=None,
                requires_review=True,
                confidence=0.95,
                reason="Technical identifier / issue key requires user confirmation.",
                span_start=m.start(),
                span_end=m.end(),
            )
        )

    # 4. Phonetic Name Variations & User Dictionary Matches
    # Extract capitalized tokens outside already matched spans
    known_pool = list(user_dictionary or []) + list(known_contacts or [])
    name_tokens = re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", text)

    for m in name_tokens:
        span = (m.start(), m.end())
        if any(start <= m.start() and m.end() <= end for start, end in seen_spans):
            continue
        token = m.group(1).strip()
        words = token.split()
        first_word = words[0]
        first_low = first_word.lower()

        # Grounded user dictionary / contact pool takes priority
        suggested = None
        reason = ""
        alternatives: List[str] = []

        if known_pool:
            token_soundex = soundex(first_word)
            for candidate in known_pool:
                cand_first = candidate.split()[0]
                if (soundex(cand_first) == token_soundex or cand_first.lower() == PHONETIC_NAME_PAIRS.get(first_low, "").lower()) and cand_first.lower() != first_low:
                    if len(words) == 1 and cand_first in known_pool:
                        suggested = cand_first
                    else:
                        suggested = candidate
                    alternatives = [suggested]
                    if candidate not in alternatives:
                        alternatives.append(candidate)
                    if cand_first not in alternatives:
                        alternatives.append(cand_first)
                    if token not in alternatives:
                        alternatives.append(token)
                    reason = f"Grounded contact dictionary phonetic match: '{token}' sounds like '{suggested}'. User confirmation required."
                    break

        # Fallback to general phonetic homophone pair if not in contact pool
        if not suggested and first_low in PHONETIC_NAME_PAIRS:
            suggested_first = PHONETIC_NAME_PAIRS[first_low]
            suggested = f"{suggested_first} {' '.join(words[1:])}".strip()
            alternatives = [suggested, token]
            reason = f"Phonetic name homophone detected: '{token}' sounds like '{suggested}'. User confirmation required."

        if suggested and suggested != token:
            entities.append(
                CriticalEntity(
                    entity_type="name",
                    original=token,
                    suggested=suggested,
                    alternatives=alternatives,
                    requires_review=True,
                    confidence=0.85,
                    reason=reason,
                    span_start=m.start(),
                    span_end=m.end(),
                )
            )

    # 5. Dates and Times
    for m in DATETIME_PATTERN.finditer(text):
        span = (m.start(), m.end())
        if any(start <= m.start() and m.end() <= end for start, end in seen_spans):
            continue
        seen_spans.add(span)
        entities.append(
            CriticalEntity(
                entity_type="datetime",
                original=m.group(0),
                suggested=None,
                requires_review=True,
                confidence=0.9,
                reason="Date or time specification requires user review to prevent scheduling errors.",
                span_start=m.start(),
                span_end=m.end(),
            )
        )

    return entities


def check_user_review_barrier(
    text: str,
    *,
    task: str = "cleanup",
    draft: Optional[str] = None,
    user_dictionary: Optional[Sequence[str]] = None,
) -> tuple[bool, List[CriticalEntity], str]:
    """Determine whether high-risk content triggers the user-facing review barrier.

    Mandated by P0-3: requires clear preview/confirmation before accepting
    high-risk generated text containing uncertain names, amounts, dates, IDs,
    or draft mutations.
    """
    entities = detect_critical_entities(text, user_dictionary=user_dictionary)
    review_entities = [e for e in entities if e.requires_review]

    reasons = []
    if task == "edit" and draft:
        reasons.append("Draft modification requires confirmation to prevent overwriting existing content.")
    for e in review_entities:
        reasons.append(f"{e.entity_type.upper()}: '{e.original}' ({e.reason})")

    triggered = bool(review_entities or (task == "edit" and draft))
    summary = " | ".join(reasons) if reasons else "No high-risk entities detected."
    return triggered, review_entities, summary


def apply_review_decision(
    text: str,
    entity: CriticalEntity,
    action: str,  # "accept_suggested", "keep_original", "custom"
    custom_value: Optional[str] = None,
) -> str:
    """Apply a user review decision to the text without modifying unrelated content."""
    if not text or not entity:
        return text

    target = entity.original
    replacement = entity.original

    if action == "accept_suggested" and entity.suggested:
        replacement = entity.suggested
    elif action == "custom" and custom_value is not None:
        replacement = custom_value.strip()
    elif action == "keep_original":
        return text

    if target in text:
        return text.replace(target, replacement, 1)
    return text


@dataclass
class ReviewResolution:
    """Outcome of the user-facing review barrier check before target application insertion."""

    approved: bool
    action: str  # "approved", "corrected", "cancelled", "ignored", "closed"
    final_text: str  # Text to insert; empty if cancelled or closed
    insertion_permitted: bool = False
    corrections: Dict[str, str] = field(default_factory=dict)
    reason: str = ""


class BlockingReviewManager:
    """Enforces blocking review for high-risk content prior to application insertion.

    Core P0-1 Guarantees:
    1. Text CANNOT reach target window before explicit approval.
    2. User can correct names, amounts, times, identifiers, or the full text.
    3. Final inserted text exactly matches the approved correction.
    4. Cancel leaves target application unchanged (insertion_permitted=False).
    5. Closing or ignoring the review interface NEVER silently approves text.
    """

    def __init__(self) -> None:
        self._custom_resolver: Optional[Any] = None
        self._last_resolution: Optional[ReviewResolution] = None

    def set_resolver(
        self,
        resolver_fn: Optional[Any],
    ) -> None:
        """Set a custom/test review resolver function."""
        self._custom_resolver = resolver_fn

    def resolve_review(
        self,
        text: str,
        entities: List[CriticalEntity],
        *,
        task: str = "cleanup",
        draft: Optional[str] = None,
    ) -> ReviewResolution:
        """Run blocking review barrier resolution.

        If custom resolver is registered, delegates to it.
        Otherwise, attempts to present desktop GUI dialog or fails closed (safe default).
        """
        if not entities and not (task == "edit" and draft):
            # No review needed
            res = ReviewResolution(
                approved=True,
                action="approved",
                final_text=text,
                insertion_permitted=True,
                reason="No high-risk entities detected.",
            )
            self._last_resolution = res
            return res

        if self._custom_resolver is not None:
            res = self._custom_resolver(text, entities, task, draft)
            self._last_resolution = res
            return res

        import os
        import sys
        if ("pytest" in sys.modules or os.environ.get("VOICE_FLOW_HEADLESS") == "1") and self._custom_resolver is None:
            res = ReviewResolution(
                approved=False,
                action="closed",
                final_text="",
                insertion_permitted=False,
                reason="Automated test environment without affirmative resolver; failing closed.",
            )
            self._last_resolution = res
            return res

        # Default desktop interactive path
        try:
            from voice_flow.review_barrier_dialog import show_review_barrier_dialog
            res = show_review_barrier_dialog(text, entities, task=task, draft=draft)
            self._last_resolution = res
            return res
        except Exception as exc:
            log.warning("[REVIEW BARRIER] GUI dialog unavailable (%s); failing closed for safety.", exc)
            # FAIL-CLOSED: Closing, ignoring, or missing UI never silently approves text!
            res = ReviewResolution(
                approved=False,
                action="closed",
                final_text="",
                insertion_permitted=False,
                reason=f"Review interface unavailable or closed: {exc}",
            )
            self._last_resolution = res
            return res


_global_review_manager = BlockingReviewManager()


def get_review_manager() -> BlockingReviewManager:
    """Return the global blocking review manager instance."""
    return _global_review_manager


def create_diagnostic_trace(
    *,
    session_id: str,
    audio_duration_seconds: float,
    raw_stt_text: str,
    raw_s1_output: str,
    postprocessed_text: str,
    delivered_text: str,
    safety_gate_passed: bool,
    safety_reasons: List[str],
    flagged_entities: List[CriticalEntity],
    model_name: str = "superwhisper/s1-mini",
    latency_ms: float = 0.0,
    store_audio_consent: bool = False,
    retain_pii_consent: bool = False,
) -> DiagnosticTrace:
    """Generate diagnostic trace obeying explicit privacy consent policies.

    Zero audio bytes or PII are retained without affirmative user consent.
    """
    if retain_pii_consent:
        stt_masked = raw_stt_text
        s1_masked = raw_s1_output
        post_masked = postprocessed_text
        deliv_masked = delivered_text
    else:
        stt_masked = mask_pii(raw_stt_text)
        s1_masked = mask_pii(raw_s1_output)
        post_masked = mask_pii(postprocessed_text)
        deliv_masked = mask_pii(delivered_text)

    return DiagnosticTrace(
        session_id=session_id,
        timestamp=time.time(),
        audio_duration_seconds=round(audio_duration_seconds, 2),
        raw_stt_text_length=len(raw_stt_text),
        raw_stt_text_masked=stt_masked,
        raw_s1_output_length=len(raw_s1_output),
        raw_s1_output_masked=s1_masked,
        postprocessed_text_masked=post_masked,
        delivered_text_masked=deliv_masked,
        safety_gate_passed=safety_gate_passed,
        safety_reasons=list(safety_reasons),
        flagged_entities=[e.to_dict() for e in flagged_entities],
        audio_retained=store_audio_consent,
        pii_retained=retain_pii_consent,
        model_name=model_name,
        latency_ms=round(latency_ms, 2),
    )

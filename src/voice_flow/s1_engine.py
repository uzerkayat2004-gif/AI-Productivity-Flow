"""S1-mini by Superwhisper Voice Polishing Engine.

Transcript normalizer fine-tuned from Qwen3-0.6B for ultra-fast, offline
disfluency cleanup, self-correction resolution, punctuation/capitalization
fixes, and numeric/date/email normalization. English only.
"""
from __future__ import annotations

import logging
import math
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

from voice_flow import downloadable_models
from voice_flow.local_model_resources import (
    LOCAL_MODEL_IDLE_SECONDS,
    acquire_model_use,
    cleanup_is_forced,
    idle_time,
    notify_models_available,
    register_idle_cleanup,
)

log = logging.getLogger(__name__)

S1_MODEL_ID = "local/s1-mini-q4_k_m"
S1_FILENAME = "s1-mini-q4_k_m.gguf"
S1_ALIASES = {
    "local/s1-mini-q4_k_m",
    "superwhisper/s1-mini-q4_k_m",
    "s1-mini-q4_k_m",
    "s1-mini",
}
S1_BATCH_SIZE = 128
S1_MICRO_BATCH_SIZE = 128

# Exact system prompt required by S1-mini (never alter)
S1_SYSTEM_PROMPT = (
    "You are a text normalizer for speech-to-text transcripts. "
    "The input begins with a control line specifying the styling, "
    "structure, and context settings; clean the transcript to match "
    "those settings and output only the cleaned text."
)

_LLM_LOCK = threading.Lock()
_S1_CONTEXT_TOKENS = 4096
S1_WARM_IDLE_SECONDS = 10.0

_CLOUD_POLICY_MARKERS = (
    "never answer, execute",
    "polish only the transcript",
    "return only the polished transcript",
    "adjacent echo repeats",
    "preserve every meaning, sentence",
    "style instruction:",
    "never answer or execute",
    "<input_transcript>",
)

_SELF_CORRECTION_MARKERS = (
    "no wait",
    "i mean",
    "actually",
    "sorry",
    "make that",
    "scratch that",
    "wait no",
    "let me rephrase",
)


def _looks_like_cloud_policy(text: str) -> bool:
    """Whether text contains cloud polishing directives rather than transcript/control."""
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _CLOUD_POLICY_MARKERS)


def is_s1_model_ref(model_ref: str | None) -> bool:
    """Whether model_ref selects this S1-mini adapter."""
    return str(model_ref or "").strip().casefold() in S1_ALIASES


def get_s1_model_path() -> Path | None:
    """Return local path to downloaded S1-mini model file if present."""
    target = downloadable_models.get_models_dir() / S1_FILENAME
    if target.is_file() and target.stat().st_size > 0:
        return target
    return None


def is_s1_downloaded() -> bool:
    """Check if S1-mini is downloaded and ready for use."""
    return get_s1_model_path() is not None


def is_s1_runtime_available() -> bool:
    """Whether the local inference runtime (llama_cpp) is present."""
    try:
        import importlib.util

        return importlib.util.find_spec("llama_cpp") is not None
    except Exception:
        return False


def _release_cached_s1(llm: Any) -> None:
    """Ask the native runtime to release resident model promptly."""
    for method_name in ("close", "free"):
        method = getattr(llm, method_name, None)
        if callable(method):
            try:
                method()
            except Exception:
                pass
            return


def _s1_runtime_batch_settings() -> dict[str, int]:
    """Keep prompt evaluation batches within the measured memory budget."""
    threads = max(1, min(8, os.cpu_count() or 4))
    return {
        "n_threads": threads,
        "n_threads_batch": threads,
        "n_batch": S1_BATCH_SIZE,
        "n_ubatch": S1_MICRO_BATCH_SIZE,
    }


def _release_idle_s1(now: float) -> bool:
    if not _LLM_LOCK.acquire(blocking=False):
        return False
    try:
        last_used = getattr(polish_with_s1, "_last_used", now)
        llm = getattr(polish_with_s1, "_cached_llm", None)
        if llm is not None and (
            cleanup_is_forced("polish") or now - last_used >= LOCAL_MODEL_IDLE_SECONDS
        ):
            _release_cached_s1(llm)
            setattr(polish_with_s1, "_cached_llm", None)
            setattr(polish_with_s1, "_cached_llm_path", None)
            log.info("[S1] Released inactive S1-mini model memory")
        return True
    finally:
        _LLM_LOCK.release()


def unload_s1_model() -> None:
    """Explicitly unload cached S1 model instance from memory."""
    with _LLM_LOCK:
        llm = getattr(polish_with_s1, "_cached_llm", None)
        if llm is not None:
            _release_cached_s1(llm)
            setattr(polish_with_s1, "_cached_llm", None)
            setattr(polish_with_s1, "_cached_llm_path", None)


def build_s1_control_line(
    effective: Any = None,
    command: Any = None,
    style_id: str | None = None,
    command_format: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> str:
    """Build the S1-mini control line mapping Voice Flow styles to model settings.

    Format: [Styling: <casual|semi-casual|semi-formal|formal>] [Structure: <prose|lists>] [Context: <general|email>]

    Rules:
    - formal: map to 'formal' ONLY when explicit command/override asks for formal/professional tone.
      Otherwise our standard Formal keeps contractions, so map to 'semi-formal'.
    - casual: map to 'semi-formal', then deterministic casual pass runs (never use S1 'semi-casual'
      which lowercases initial words).
    - very_casual: map to 'casual' (all lowercase).
    - excited: map to 'semi-formal', then deterministic excited pass adds exclamation marks.
    - Structure: bullet_list -> 'lists', otherwise 'prose'.
    - Context: format == 'email' or category == 'email' -> 'email', otherwise 'general'.
    """
    resolved_style_id = (
        getattr(effective, "style_id", None)
        or style_id
        or ""
    ).lower()

    resolved_format = (
        getattr(command, "format", None)
        or getattr(effective, "format", None)
        or command_format
        or ""
    ).lower()

    resolved_category = (
        getattr(effective, "category", None)
        or getattr(command, "context_reference", None)
        or ""
    ).lower()

    resolved_overrides = (
        getattr(command, "overrides", None)
        or overrides
        or {}
    )
    if not isinstance(resolved_overrides, dict):
        resolved_overrides = {}

    tone_override = str(resolved_overrides.get("tone") or "").lower()
    formality_override = str(resolved_overrides.get("formality") or "").lower()
    explicit_formal = (
        tone_override in ("formal", "professional")
        or formality_override in ("formal", "professional")
    )

    # 1. Styling
    if "very_casual" in resolved_style_id:
        styling = "casual"
    elif explicit_formal:
        styling = "formal"
    elif "formal" in resolved_style_id:
        styling = "semi-formal"
    elif "casual" in resolved_style_id:
        styling = "semi-formal"
    elif "excited" in resolved_style_id:
        styling = "semi-formal"
    else:
        styling = "semi-formal"

    # 2. Structure
    if resolved_format == "bullet_list":
        structure = "lists"
    else:
        structure = "prose"

    # 3. Context
    if resolved_format == "email" or resolved_category == "email":
        context = "email"
    else:
        context = "general"

    return f"[Styling: {styling}] [Structure: {structure}] [Context: {context}]"


def build_s1_prompt(control_line: str, text: str) -> str:
    """Build raw ChatML prompt with thinking block pre-disabled."""
    clean_text = text.strip()
    return (
        f"<|im_start|>system\n{S1_SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n{control_line}\n{clean_text}<|im_end|>\n"
        f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )


def s1_can_handle(
    effective: Any = None,
    command: Any = None,
    text: str = "",
    *,
    task: str | None = None,
    instruction: str = "",
    style_id: str | None = None,
    command_format: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> bool:
    """Check whether S1-mini can handle the given request.

    Returns False for:
    - operation 'summarize', operation 'prompt_generation' / format 'prompt'
    - formats linkedin_post, note, work_message, personal_message
    - custom standing instructions, persistent_change, ambiguous commands
    - non-English transcripts
    """
    # 1. Operation / task checks
    op = str(
        getattr(command, "operation", None)
        or getattr(effective, "task", None)
        or task
        or ""
    ).strip().lower().replace("-", "_").replace(" ", "_")
    if op in {
        "summarize", "summarise", "summary", "summarization", "summarisation",
        "prompt_generation", "generate_prompt", "prompt",
    }:
        return False

    fmt = str(
        getattr(command, "format", None)
        or getattr(effective, "format", None)
        or command_format
        or ""
    ).strip().lower().replace("-", "_").replace(" ", "_")
    if fmt in ("prompt", "linkedin_post", "note", "work_message", "personal_message"):
        return False

    # S1 is a transcript normalizer. Reject explicit task instructions that
    # ask it to perform a different operation, while allowing normal style and
    # cleanup instructions (which are common in the voice pipeline).
    task_instruction = str(instruction or "").strip().lower()
    unsupported_instruction = re.compile(
        r"\b(summarize|summarise|summary|tl;dr)\b"
        r"|\b(generate|create|write|make)\b.{0,48}\b(prompt|outline)\b"
        r"|\b(prompt|outline)\b.{0,48}\b(generate|create|write|make)\b"
    )
    for match in unsupported_instruction.finditer(task_instruction):
        preceding = re.split(r"[.!?,;:]", task_instruction[:match.start()])[-1]
        if re.search(r"\b(?:do\s+not|don't|never|avoid|without)\b", preceding):
            continue
        return False

    # 2. Command attribute checks
    # Free-text constraints ("without hashtags") cannot be expressed in S1's
    # native control line; routing them to S1 would silently drop them.
    if getattr(command, "constraints", ()):
        return False
    if getattr(command, "operation", None) == "unsupported":
        return False
    if getattr(command, "persistent_change", False):
        return False
    if getattr(command, "ambiguous", False):
        return False

    if overrides and any(
        str(key).lower() in {"task", "operation", "format"}
        and str(value).lower().replace("-", "_").replace(" ", "_")
        in {
            "summarize", "summarise", "summary", "summarization", "summarisation",
            "prompt", "prompt_generation", "generate_prompt", "linkedin_post",
            "note", "work_message", "personal_message",
        }
        for key, value in overrides.items()
    ):
        return False

    # 3. Custom standing instructions check
    try:
        from voice_flow.storage import storage

        cat = getattr(effective, "category", None) or "default"
        extra = str(storage.get_setting(f"style_{cat}_extra", "") or "").strip()
        if extra:
            return False
        standing = str(storage.get_setting("style_standing_instruction", "") or "").strip()
        if standing:
            return False
    except Exception:
        pass

    # 4. English language checks
    if text:
        letters = [c for c in text if c.isalpha()]
        if letters:
            non_ascii_letters = [c for c in letters if ord(c) > 127]
            if len(non_ascii_letters) / len(letters) > 0.2:
                return False

    try:
        from voice_flow.storage import storage

        stt_model = str(storage.get_setting("voice_flow_stt_model", "") or "").lower()
        if "3.5" in stt_model or "multilingual" in stt_model:
            lang = str(storage.get_setting("voice_flow_language", "en") or "").lower()
            if lang not in ("en", "english", ""):
                return False
    except Exception:
        pass

    return True


_WORD_TO_NUMBER: dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90, "hundred": 100, "thousand": 1000,
    "million": 1000000, "billion": 1000000000,
}


def _extract_number_values(text: str) -> list[int]:
    """Extract integer quantities from both digit representations and words."""
    found: set[int] = set()
    # Digits
    for m in re.finditer(r"\b\d+\b", text):
        try:
            found.add(int(m.group(0)))
        except ValueError:
            pass

    # Simple spoken numbers
    words = re.findall(r"\b[a-z]+\b", text.lower())
    current = 0
    subtotal = 0
    in_number = False

    for w in words:
        if w in _WORD_TO_NUMBER:
            val = _WORD_TO_NUMBER[w]
            in_number = True
            if val == 100:
                subtotal = (subtotal or 1) * 100
            elif val >= 1000:
                subtotal = (subtotal or 1) * val
                current += subtotal
                subtotal = 0
            else:
                subtotal += val
        else:
            if in_number:
                total = current + subtotal
                if total > 0:
                    found.add(total)
                current = 0
                subtotal = 0
                in_number = False
    if in_number:
        total = current + subtotal
        if total > 0:
            found.add(total)

    return sorted(found)


def check_joined_numbers_guard(input_text: str, output_text: str) -> bool:
    """Fidelity guard: protect numbers/amounts joined by 'or' or 'and'.

    If input contains 2+ numbers joined by 'or' / 'and' (without real
    self-correction markers like 'no wait', 'I mean', 'actually', 'sorry',
    'make that'), and the output drops any of those numbers, reject S1 output.
    """
    in_lower = input_text.lower()
    out_lower = output_text.lower()

    # Check for disfluency/self-correction markers
    has_self_correction = any(marker in in_lower for marker in _SELF_CORRECTION_MARKERS)
    if has_self_correction:
        return True

    stutter_normalized_input = _collapse_repeated_half_quantity_prefix(input_text)
    has_stutter_equivalence = stutter_normalized_input != input_text
    stutter_normalized_output = (
        _collapse_repeated_half_quantity_prefix(output_text)
        if has_stutter_equivalence else output_text
    )
    if has_stutter_equivalence and (
        _mixed_half_quantity_bindings(stutter_normalized_input)
        != _mixed_half_quantity_bindings(stutter_normalized_output)
    ):
        log.info("[S1] Repeated half-quantity stutter changed value or unit.")
        return False

    # Check if joined by 'or' or 'and'
    has_conjunction = bool(re.search(r"\b(or|and)\b", in_lower))
    if not has_conjunction:
        return True

    input_nums = _extract_number_values(stutter_normalized_input.lower())
    if len(input_nums) < 2:
        return True

    output_nums = set(_extract_number_values(stutter_normalized_output.lower()))

    # If any input number is completely lost in the output, reject
    for num in input_nums:
        if num not in output_nums:
            log.info("[S1] Number guard triggered: %d from input missing in output", num)
            return False

    return True


_CANONICAL_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100,
    "thousand": 1000, "million": 1000000,
}
_NUMBER_WORD_PATTERN = "|".join(
    sorted((re.escape(word) for word in _CANONICAL_NUMBER_WORDS), key=len, reverse=True)
)
_WEEKDAYS = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"


def _parse_cardinal_words(words: list[str]) -> int | None:
    """Parse a deliberately small, grammar-valid English cardinal phrase."""
    if not words:
        return None

    # English often includes "and" after a scale ("one hundred and five").
    # Remove only that connector; a bare "one and two" remains two quantities.
    parts = [
        word for index, word in enumerate(words)
        if word != "and" or not (index > 0 and words[index - 1] in {"hundred", "thousand", "million"})
    ]

    def under_hundred(parts: list[str]) -> int | None:
        if len(parts) == 1:
            value = _CANONICAL_NUMBER_WORDS[parts[0]]
            return value if value < 20 or value in range(20, 100, 10) else None
        if len(parts) == 2:
            tens = _CANONICAL_NUMBER_WORDS[parts[0]]
            unit = _CANONICAL_NUMBER_WORDS[parts[1]]
            if tens in range(20, 100, 10) and 0 < unit < 10:
                return tens + unit
        return None

    def under_thousand(parts: list[str]) -> int | None:
        if "hundred" not in parts:
            return under_hundred(parts)
        if parts.count("hundred") != 1 or len(parts) < 2:
            return None
        position = parts.index("hundred")
        prefix = under_hundred(parts[:position])
        if prefix is None or not 0 < prefix < 10:
            return None
        tail = parts[position + 1:]
        if not tail:
            return prefix * 100
        remainder = under_hundred(tail)
        return prefix * 100 + remainder if remainder is not None and remainder > 0 else None

    total = 0
    group: list[str] = []
    previous_scale = 1000001
    for word in parts:
        if word not in _CANONICAL_NUMBER_WORDS:
            return None
        scale = _CANONICAL_NUMBER_WORDS[word]
        if word not in {"thousand", "million"}:
            group.append(word)
            continue
        if scale >= previous_scale:
            return None
        value = under_thousand(group)
        if value is None or value <= 0:
            return None
        total += value * scale
        previous_scale = scale
        group = []
    if group:
        value = under_thousand(group)
        if value is None:
            return None
        total += value
    elif not total:
        return None
    return total


def _canonicalize_spoken_numbers(text: str) -> str:
    word = rf"(?:{_NUMBER_WORD_PATTERN})"
    number_words = rf"(?<![A-Za-z']){word}(?:\s+(?:and\s+)?{word})*(?![A-Za-z'])"
    joined_quantities = re.compile(
        rf"(?P<first>{number_words})\s+(?P<join>or|and)\s+(?P<second>{number_words})(?P<currency>\s+dollars?\b)?",
        re.IGNORECASE,
    )

    def normalize_joined_pair(match: re.Match[str]) -> str:
        first_words = match.group("first").lower().split()
        second_words = match.group("second").lower().split()
        first = _parse_cardinal_words(first_words)
        second = _parse_cardinal_words(second_words)
        if first is None or second is None:
            return match.group(0)
        join = match.group("join").lower()
        if join == "and" and first_words[-1] in {"hundred", "thousand", "million"}:
            return match.group(0)
        if match.group("currency"):
            return f"${first} {join} ${second}"
        return f"{first} {join} {second}"

    text = joined_quantities.sub(normalize_joined_pair, text)
    run_pattern = re.compile(number_words, re.IGNORECASE)

    def normalize_run(match: re.Match[str]) -> str:
        value = _parse_cardinal_words(match.group(0).lower().split())
        if value is None:
            return match.group(0)
        return str(value)

    text = run_pattern.sub(normalize_run, text)
    # A number directly followed by the spoken currency unit is normalized to
    # the same spelling used for a written dollar amount.
    text = re.sub(r"\b(\d+)\s+dollars?\b", r"$\1", text, flags=re.IGNORECASE)
    return re.sub(r"\$(\d+)\s+dollars?\b", r"$\1", text, flags=re.IGNORECASE)


def _collapse_repeated_half_quantity_prefix(text: str) -> str:
    """Drop only an immediate duplicate before a well-formed mixed half unit."""
    from voice_flow.text_processing import _PROTECTED_CLEANUP_SPAN_RE

    word = rf"(?:{_NUMBER_WORD_PATTERN})"
    number_words = rf"(?<![A-Za-z']){word}(?:\s+(?:and\s+)?{word})*(?![A-Za-z'])"
    repeated_prefix = re.compile(
        rf"(?P<whole>{number_words})\s+(?P=whole)\s+and\s+a\s+half\s+"
        r"(?P<unit>seconds?|minutes?|hours?|days?|weeks?|months?|years?|milliseconds?)\b",
        re.IGNORECASE,
    )

    def collapse(match: re.Match[str]) -> str:
        whole = match.group("whole").lower().split()
        if _parse_cardinal_words(whole) is None:
            return match.group(0)
        return f"{match.group('whole')} and a half {match.group('unit')}"

    parts: list[str] = []
    cursor = 0
    for match in _PROTECTED_CLEANUP_SPAN_RE.finditer(text):
        parts.append(repeated_prefix.sub(collapse, text[cursor:match.start()]))
        parts.append(match.group(0))
        cursor = match.end()
    parts.append(repeated_prefix.sub(collapse, text[cursor:]))
    return "".join(parts)


def _mixed_half_quantity_bindings(text: str) -> dict[tuple[str, str], int]:
    """Count explicit spoken whole-and-a-half time quantities outside literals."""
    from collections import Counter
    from voice_flow.text_processing import _PROTECTED_CLEANUP_SPAN_RE

    word = rf"(?:{_NUMBER_WORD_PATTERN})"
    number_words = rf"(?<![A-Za-z']){word}(?:\s+(?:and\s+)?{word})*(?![A-Za-z'])"
    mixed_half = re.compile(
        rf"(?P<whole>{number_words})\s+and\s+a\s+half\s+"
        r"(?P<unit>seconds?|minutes?|hours?|days?|weeks?|months?|years?|milliseconds?)\b",
        re.IGNORECASE,
    )
    units = {
        "seconds": "second", "minutes": "minute", "hours": "hour",
        "days": "day", "weeks": "week", "months": "month",
        "years": "year", "milliseconds": "millisecond",
    }
    bindings: Counter[tuple[str, str]] = Counter()

    def collect(prose: str) -> None:
        for match in mixed_half.finditer(prose):
            whole = _parse_cardinal_words(match.group("whole").lower().split())
            if whole is None:
                continue
            unit = match.group("unit").casefold()
            bindings[(f"{whole}.5", units.get(unit, unit))] += 1

    cursor = 0
    for match in _PROTECTED_CLEANUP_SPAN_RE.finditer(text):
        collect(text[cursor:match.start()])
        cursor = match.end()
    collect(text[cursor:])
    return dict(bindings)


def _canonical_fidelity_text(text: str) -> str:
    from voice_flow.text_processing import _PROTECTED_CLEANUP_SPAN_RE

    parts: list[str] = []
    cursor = 0
    for match in _PROTECTED_CLEANUP_SPAN_RE.finditer(text):
        prose = text[cursor:match.start()]
        prose = re.sub(
            rf"\b({_WEEKDAYS})\s*,?\s*(?:no\s+wait|i\s+mean|wait\s+no)\s*,?\s*({_WEEKDAYS})\b",
            lambda match: match.group(2),
            prose,
            flags=re.IGNORECASE,
        )
        parts.append(_canonicalize_spoken_numbers(prose))
        parts.append(match.group(0))
        cursor = match.end()
    prose = text[cursor:]
    prose = re.sub(
        rf"\b({_WEEKDAYS})\s*,?\s*(?:no\s+wait|i\s+mean|wait\s+no)\s*,?\s*({_WEEKDAYS})\b",
        lambda match: match.group(2),
        prose,
        flags=re.IGNORECASE,
    )
    parts.append(_canonicalize_spoken_numbers(prose))
    return "".join(parts)


def normalization_preserves_content(
    source: str,
    candidate: str,
    *,
    task: str = "cleanup",
    command_format: str | None = None,
) -> bool:
    """Run the shared fidelity guard after narrow S1 normalization equivalences."""
    try:
        from voice_flow.polisher import _candidate_preserves_content
        from voice_flow.vf_checks import expand_contractions, normalize_source_for_guard

        # Apply the edits a correct cleanup is expected to make (fillers,
        # repeats, self-corrections, "dont" -> "do not", spoken price
        # compounds) before comparing, so valid normalisations are not
        # rejected (A16).  Number, negation, literal and retention checks
        # below still run on the result.
        source = normalize_source_for_guard(source, candidate)
        candidate = expand_contractions(candidate)
        if not re.search(r"\w", source):
            return not re.search(r"\w", candidate or "")

        stutter_normalized_source = _collapse_repeated_half_quantity_prefix(source)
        has_stutter_equivalence = stutter_normalized_source != source
        stutter_normalized_candidate = (
            _collapse_repeated_half_quantity_prefix(candidate)
            if has_stutter_equivalence else candidate
        )
        if has_stutter_equivalence and (
            _mixed_half_quantity_bindings(stutter_normalized_source)
            != _mixed_half_quantity_bindings(stutter_normalized_candidate)
        ):
            return False
        normalized_source = _canonical_fidelity_text(stutter_normalized_source)
        normalized_candidate = _canonical_fidelity_text(stutter_normalized_candidate)
        if _canonical_quantity_counts(normalized_source) != _canonical_quantity_counts(normalized_candidate):
            return False
        if _canonical_negation_counts(normalized_source) != _canonical_negation_counts(normalized_candidate):
            return False
        return _candidate_preserves_content(
            normalized_source,
            normalized_candidate,
            task=task,
            command_format=command_format,
        )
    except Exception as exc:
        log.debug("[S1] Could not run canonical fidelity guard: %s", exc)
        return False


def _canonical_quantity_counts(text: str) -> dict[str, int]:
    from collections import Counter
    from voice_flow.text_processing import _PROTECTED_CLEANUP_SPAN_RE

    values: Counter[str] = Counter()
    cursor = 0
    for match in _PROTECTED_CLEANUP_SPAN_RE.finditer(text):
        values.update(re.findall(r"(?<![\w])\d+(?![\w])", text[cursor:match.start()]))
        literal = match.group(0)
        if re.fullmatch(r"\$\d+", literal):
            values[literal] += 1
        cursor = match.end()
    values.update(re.findall(r"(?<![\w])\d+(?![\w])", text[cursor:]))
    return dict(values)


def _canonical_negation_counts(text: str) -> dict[str, int]:
    from collections import Counter
    from voice_flow.text_processing import _PROTECTED_CLEANUP_SPAN_RE
    from voice_flow.polisher import _expand_unambiguous_contractions

    prose = _PROTECTED_CLEANUP_SPAN_RE.sub(" ", text)
    tokens = re.findall(r"\b(?:not|never|without|no|neither|nor)\b", _expand_unambiguous_contractions(prose), re.IGNORECASE)
    return dict(Counter(token.casefold() for token in tokens))


def _extract_transcript(text: str) -> tuple[str, str | None]:
    """Extract raw transcript text and any embedded system prompt."""
    if not text:
        return text, None
    match = re.search(
        r"^\s*<input_transcript>\s*$\s*^(.*?)^\s*</input_transcript>\s*$",
        text, re.DOTALL | re.IGNORECASE | re.MULTILINE,
    )
    if not match:
        match = re.search(r"<input_transcript>([^\n]*?)</input_transcript>", text, re.IGNORECASE)
    if match:
        raw = match.group(1).strip()
        sys_p = text[:match.start()].strip() or None
        return raw, sys_p
    return text.strip(), None


def warm_s1_model(*, timeout_seconds: float = 5.0) -> bool:
    """Load S1-mini once so the first dictation avoids cold-start latency."""
    model_path = get_s1_model_path()
    if not model_path or not is_s1_runtime_available() or timeout_seconds <= 0:
        return False
    t_sec = float(timeout_seconds)
    t_sec = 300.0 if (math.isinf(t_sec) or t_sec > 300.0) else max(0.0, t_sec)
    if not _LLM_LOCK.acquire(timeout=t_sec):
        return False
    try:
        register_idle_cleanup("s1", _release_idle_s1, kind="polish")
        if getattr(polish_with_s1, "_cached_llm_path", None) == str(model_path):
            setattr(polish_with_s1, "_last_used", idle_time())
            return True
        from llama_cpp import Llama  # type: ignore

        gpu_layers = -1 if sys.platform == "darwin" else 0
        llm = Llama(
            model_path=str(model_path),
            n_ctx=_S1_CONTEXT_TOKENS,
            **_s1_runtime_batch_settings(),
            n_gpu_layers=gpu_layers,
            verbose=False,
        )
        old_llm = getattr(polish_with_s1, "_cached_llm", None)
        if old_llm is not None:
            _release_cached_s1(old_llm)
        setattr(polish_with_s1, "_cached_llm", llm)
        setattr(polish_with_s1, "_cached_llm_path", str(model_path))
        setattr(polish_with_s1, "_last_used", idle_time())
        return True
    except Exception as exc:
        log.warning("[S1] Could not warm S1-mini model: %s", exc)
        return False
    finally:
        _LLM_LOCK.release()


def _chunk_transcript(text: str, max_chunk_words: int = 150) -> list[str]:
    """Split transcript into coherent chunks at sentence/pause boundaries."""
    # Split on sentence terminals or newlines
    sentences = re.split(r"(?<=[.!?\n])\s+", text.strip())
    chunks: list[str] = []
    current: list[str] = []
    curr_len = 0

    for s in sentences:
        s_words = len(s.split())
        if s_words > max_chunk_words:
            if current:
                chunks.append(" ".join(current).strip())
                current = []
                curr_len = 0
            words = s.split()
            chunks.extend(
                " ".join(words[i:i + max_chunk_words])
                for i in range(0, len(words), max_chunk_words)
            )
            continue
        if curr_len + s_words > max_chunk_words and current:
            chunks.append(" ".join(current).strip())
            current = [s]
            curr_len = s_words
        else:
            current.append(s)
            curr_len += s_words
    if current:
        chunks.append(" ".join(current).strip())
    return chunks or [text]


def _polish_chunk_with_s1(
    llm: Any,
    chunk: str,
    control_line: str,
    deadline: float,
) -> str | None:
    """Run S1 inference on a single chunk with ChatML and greedy decoding."""
    prompt = build_s1_prompt(control_line, chunk)
    try:
        input_tokens = len(llm.tokenize(prompt.encode("utf-8")))
    except Exception:
        input_tokens = len(prompt.split())

    if input_tokens > _S1_CONTEXT_TOKENS:
        log.info("[S1] Prompt exceeds the %d-token model context.", _S1_CONTEXT_TOKENS)
        return None

    try:
        transcript_tokens = len(llm.tokenize(chunk.encode("utf-8")))
    except Exception:
        transcript_tokens = len(chunk.split())
    available_tokens = _S1_CONTEXT_TOKENS - input_tokens
    max_tokens = min(int(transcript_tokens * 1.3) + 48, available_tokens)
    if max_tokens <= 0:
        return None

    if time.monotonic() >= deadline:
        return None

    class DeadlineStoppingCriteria(list):
        def __call__(self, input_ids: Any, logits: Any) -> bool:
            return any(criteria(input_ids, logits) for criteria in self)

    def deadline_reached(_input_ids: Any, _logits: Any) -> bool:
        return time.monotonic() >= deadline

    resp = llm(
        prompt,
        max_tokens=max_tokens,
        temperature=0.0,
        top_k=1,
        repeat_penalty=1.0,
        stop=["<|im_end|>"],
        stopping_criteria=DeadlineStoppingCriteria([deadline_reached]),
    )

    if time.monotonic() >= deadline:
        return None

    if not isinstance(resp, dict):
        return None

    choices = resp.get("choices") or []
    if not choices:
        return None

    raw_output = str(choices[0].get("text") or "")
    if str(choices[0].get("finish_reason") or "").lower() in ("length", "max_tokens"):
        log.info("[S1] Generation reached its token limit; rejecting incomplete output.")
        return None

    # Strip any remaining <think>...</think>
    cleaned = re.sub(r"<think>.*?</think>", "", raw_output, flags=re.DOTALL)
    cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
    cleaned = cleaned.replace("<|im_end|>", "")
    cleaned = cleaned.strip()
    return cleaned or None


def _polish_with_s1_impl(
    text: str,
    instruction: str = "",
    *,
    timeout_seconds: float = 5.0,
    effective: Any = None,
    command: Any = None,
    style_id: str | None = None,
    command_format: str | None = None,
    overrides: dict[str, Any] | None = None,
    task: str | None = None,
) -> str | None:
    """Internal S1-mini execution implementation."""
    if not text or not text.strip():
        return text

    deadline = time.monotonic() + max(0.0, float(timeout_seconds))

    model_path = get_s1_model_path()
    if not model_path:
        log.warning("[S1] Model %s is not downloaded; cannot polish with S1.", S1_FILENAME)
        return None

    user_text, embedded_sys = _extract_transcript(text)

    # Validate eligibility with s1_can_handle
    if not s1_can_handle(
        effective=effective,
        command=command,
        text=user_text,
        task=task,
        instruction=instruction,
        style_id=style_id,
        command_format=command_format,
        overrides=overrides,
    ):
        log.info("[S1] Request ineligible for S1-mini; routing to fallback.")
        return None

    # Mock inference remains available to offline tests, after the same
    # eligibility checks applied to the real runtime.
    mock_runner = getattr(polish_with_s1, "_mock_runner", None)
    if callable(mock_runner):
        return mock_runner(user_text, instruction)

    control_line = build_s1_control_line(
        effective=effective,
        command=command,
        style_id=style_id,
        command_format=command_format,
        overrides=overrides,
    )

    if time.monotonic() >= deadline:
        return None

    rem = deadline - time.monotonic()
    rem = 300.0 if (math.isinf(rem) or rem > 300.0) else max(0.0, rem)
    if not _LLM_LOCK.acquire(timeout=rem):
        log.info("[S1] Timed out waiting for S1 local model lock.")
        return None

    try:
        try:
            from llama_cpp import Llama  # type: ignore
        except Exception:
            log.info("[S1] llama-cpp runtime unavailable; S1 cannot run.")
            return None

        llm = getattr(polish_with_s1, "_cached_llm", None)
        cached_path = getattr(polish_with_s1, "_cached_llm_path", None)
        if llm is None or cached_path != str(model_path):
            gpu_layers = -1 if sys.platform == "darwin" else 0
            replacement = Llama(
                model_path=str(model_path),
                n_ctx=_S1_CONTEXT_TOKENS,
                **_s1_runtime_batch_settings(),
                n_gpu_layers=gpu_layers,
                verbose=False,
            )
            if llm is not None:
                _release_cached_s1(llm)
            llm = replacement
            setattr(polish_with_s1, "_cached_llm", llm)
            setattr(polish_with_s1, "_cached_llm_path", str(model_path))

        register_idle_cleanup("s1", _release_idle_s1, kind="polish")
        setattr(polish_with_s1, "_last_used", idle_time())

        # Chunk transcript if longer than ~900 tokens (approx 700 words)
        words = user_text.split()
        if len(words) > 700:
            chunks = _chunk_transcript(user_text, max_chunk_words=300)
            cleaned_pieces: list[str] = []
            for ch in chunks:
                piece = _polish_chunk_with_s1(llm, ch, control_line, deadline)
                if not piece or not piece.strip() or time.monotonic() >= deadline:
                    return None
                cleaned_pieces.append(piece)
            output = " ".join(cleaned_pieces).strip()
        else:
            output = _polish_chunk_with_s1(llm, user_text, control_line, deadline)
            if output is None:
                return None

        # Clean tags if reflected
        output = output.strip().strip('"')
        if not re.search(r"</?input_transcript>", user_text, re.IGNORECASE):
            output = re.sub(r"</?input_transcript>", "", output, flags=re.IGNORECASE).strip()

        # Fidelity guard on joined numbers ("or" / "and")
        if not check_joined_numbers_guard(user_text, output):
            log.info("[S1] Joined numbers guard failed; rejecting S1 output.")
            return None

        return output

    except Exception as exc:
        log.warning("[S1] Error during S1 voice polishing: %s", exc)
        return None
    finally:
        try:
            setattr(polish_with_s1, "_last_used", idle_time())
        finally:
            _LLM_LOCK.release()


def polish_with_s1(
    text: str,
    instruction: str = "",
    *,
    timeout_seconds: float = 5.0,
    effective: Any = None,
    command: Any = None,
    style_id: str | None = None,
    command_format: str | None = None,
    overrides: dict[str, Any] | None = None,
    task: str | None = None,
    **kwargs: Any,
) -> str | None:
    """Run S1-mini voice polishing with bounded lease and idle grace."""
    if not text or not text.strip():
        return text
    lease = acquire_model_use("polish")
    try:
        return _polish_with_s1_impl(
            text,
            instruction,
            timeout_seconds=timeout_seconds,
            effective=effective,
            command=command,
            style_id=style_id,
            command_format=command_format,
            overrides=overrides,
            task=task,
        )
    finally:
        release_after_idle = getattr(lease, "release_after_idle", None)
        if callable(release_after_idle):
            release_after_idle(S1_WARM_IDLE_SECONDS)
        else:
            lease.release()
        notify_models_available("polish")


def get_catalog_entry() -> dict[str, Any]:
    """Return model specification for the Voice Flow polish model catalog."""
    downloaded = is_s1_downloaded()
    return {
        "full_id": S1_MODEL_ID,
        "label": f"S1-mini by Superwhisper (offline · 484 MB{' · ready' if downloaded else ' · download required'})",
        "provider": "local",
        "provider_name": "Local GGUF",
        "display_name": "S1-mini by Superwhisper",
        "capabilities": ["offline", "local", "downloadable", "gguf"],
        "downloaded": downloaded,
        "polish_supported": downloaded,
        "polish_unavailable_reason": "" if downloaded else "Download required in Offline Models section (484 MB)",
        "is_fallback": False,
        "description": "English transcript cleanup by Superwhisper: fillers, self-corrections, punctuation, numbers, emails. Never rewrites your meaning.",
    }

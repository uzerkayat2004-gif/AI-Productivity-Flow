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


def s1_can_handle(effective: Any = None, command: Any = None, text: str = "") -> bool:
    """Check whether S1-mini can handle the given request.

    Returns False for:
    - operation 'summarize', operation 'prompt_generation' / format 'prompt'
    - formats linkedin_post, note, work_message, personal_message
    - custom standing instructions, persistent_change, ambiguous commands
    - non-English transcripts
    """
    # 1. Operation / task checks
    op = (
        getattr(command, "operation", None)
        or getattr(effective, "task", None)
        or ""
    ).lower()
    if op in ("summarize", "prompt_generation", "prompt"):
        return False

    fmt = (
        getattr(command, "format", None)
        or getattr(effective, "format", None)
        or ""
    ).lower()
    if fmt in ("prompt", "linkedin_post", "note", "work_message", "personal_message"):
        return False

    # 2. Command attribute checks
    if getattr(command, "persistent_change", False):
        return False
    if getattr(command, "ambiguous", False):
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

    # Check if joined by 'or' or 'and'
    has_conjunction = bool(re.search(r"\b(or|and)\b", in_lower))
    if not has_conjunction:
        return True

    input_nums = _extract_number_values(in_lower)
    if len(input_nums) < 2:
        return True

    output_nums = set(_extract_number_values(out_lower))

    # If any input number is completely lost in the output, reject
    for num in input_nums:
        if num not in output_nums:
            log.info("[S1] Number guard triggered: %d from input missing in output", num)
            return False

    return True


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
            n_threads=max(1, min(8, os.cpu_count() or 4)),
            n_gpu_layers=gpu_layers,
            n_batch=512,
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

    max_tokens = int(input_tokens * 1.3) + 48

    if time.monotonic() >= deadline:
        return None

    resp = llm(
        prompt,
        max_tokens=max_tokens,
        temperature=0.0,
        top_k=1,
        repeat_penalty=1.0,
        stop=["<|im_end|>"],
    )

    if not isinstance(resp, dict):
        return None

    choices = resp.get("choices") or []
    if not choices:
        return None

    raw_output = str(choices[0].get("text") or "")

    # Strip any remaining <think>...</think>
    cleaned = re.sub(r"<think>.*?</think>", "", raw_output, flags=re.DOTALL)
    cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
    cleaned = cleaned.replace("<|im_end|>", "")
    return cleaned.strip()


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

    # Check for test mock override
    mock_runner = getattr(polish_with_s1, "_mock_runner", None)
    if callable(mock_runner):
        return mock_runner(user_text, instruction)

    # Validate eligibility with s1_can_handle
    if not s1_can_handle(effective=effective, command=command, text=user_text):
        log.info("[S1] Request ineligible for S1-mini; routing to fallback.")
        return None

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
                n_threads=max(1, min(8, os.cpu_count() or 4)),
                n_gpu_layers=gpu_layers,
                n_batch=512,
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
                if piece is None and time.monotonic() >= deadline:
                    return None
                cleaned_pieces.append(piece or "")
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

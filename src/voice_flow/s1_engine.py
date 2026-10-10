"""S1-mini by Superwhisper: offline speech-transcript normalizer for Voice Flow.

S1-mini is a Qwen3-0.6B fine-tune trained for one job: turning raw ASR output
into clean written text (fillers, self-corrections, punctuation, numbers,
email layout).  It is not a chat model and does not follow free-form
instructions; it is steered only by a control line, and it must receive its
exact trained input format or it can hallucinate.
"""
from __future__ import annotations

import logging
import math
import re
import threading
import time
from pathlib import Path
from typing import Any

from voice_flow import downloadable_models
from voice_flow.local_model_resources import (
    acquire_model_use,
    cleanup_is_forced,
    idle_limit_seconds,
    idle_time,
    notify_models_available,
    register_idle_cleanup,
)

log = logging.getLogger(__name__)

S1_MODEL_ID = "local/s1-mini-q4_k_m"
S1_FILENAME = "s1-mini-q4_k_m.gguf"
S1_DISPLAY_NAME = "S1-mini by Superwhisper"

# The model card requires this system prompt verbatim.
S1_SYSTEM_PROMPT = (
    "You are a text normalizer for speech-to-text transcripts. The input begins with a control line "
    "specifying the styling, structure, and context settings; clean the transcript to match those "
    "settings and output only the cleaned text."
)
# Rendered without the embedded chat template: S1-mini was trained with
# Qwen3 thinking disabled, so the assistant turn must open with an empty
# think block (two newlines inside it, two after it).
_PROMPT_TEMPLATE = (
    "<|im_start|>system\n{system}<|im_end|>\n"
    "<|im_start|>user\n{control}\n{transcript}<|im_end|>\n"
    "<|im_start|>assistant\n<think>\n\n</think>\n\n"
)
_STOP = ["<|im_end|>", "<|im_start|>"]
_CONTEXT_TOKENS = 4096
_OUTPUT_CAP_TOKENS = 1536
_THINK_BLOCK_RE = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)
_FORMAL_RE = re.compile(r"\bformal\b", re.IGNORECASE)

_LLM_LOCK = threading.Lock()
_state: dict[str, Any] = {"llm": None, "path": None, "last_used": 0.0}


def is_s1_model_ref(model_ref: str) -> bool:
    """Whether *model_ref* selects S1-mini, under any provider prefix or quantization."""
    return "s1-mini" in str(model_ref or "").strip().casefold()


def get_s1_model_path() -> Path | None:
    """Return the downloaded S1-mini GGUF, preferring the catalog filename."""
    models_dir = downloadable_models.get_models_dir()
    exact = models_dir / S1_FILENAME
    if exact.is_file() and exact.stat().st_size > 0:
        return exact
    try:
        candidates = sorted(
            path for path in models_dir.iterdir()
            if path.suffix.casefold() == ".gguf" and path.name.casefold().startswith("s1-mini")
            and path.is_file() and path.stat().st_size > 0
        )
    except OSError:
        return None
    return candidates[0] if candidates else None


def is_s1_downloaded() -> bool:
    return get_s1_model_path() is not None


def is_s1_loaded() -> bool:
    return _state["llm"] is not None


def control_line(instruction: str) -> str:
    """Map a Voice Flow style/command instruction onto S1-mini's trained control values."""
    from voice_flow.lfm_engine import _local_mode

    mode = _local_mode(instruction)
    lowered = (instruction or "").casefold()
    # S1 "casual" strips apostrophes ("im", "cant"), which changes the
    # speaker's words; lowercase registers use semi-casual and the polisher's
    # register pass instead.
    if "lowercase" in lowered:
        styling = "semi-casual"
    elif _FORMAL_RE.search(instruction or ""):
        styling = "formal"
    else:
        styling = "semi-formal"
    structure = "lists" if mode == "bullets" else "prose"
    context = "email" if mode == "email" else "general"
    return f"[Styling: {styling}] [Structure: {structure}] [Context: {context}]"


def local_polish_allowance(word_count: int) -> float:
    """Seconds an S1-mini pass over ``word_count`` words may need, including a cold load."""
    allowance = 1.0 + 0.025 * max(0, int(word_count or 0))
    if not is_s1_loaded():
        allowance += 1.5
    return min(12.0, allowance)


def _release_llm(llm: Any) -> None:
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
        llm = _state["llm"]
        if llm is not None and (
            cleanup_is_forced("polish") or now - float(_state["last_used"] or now) >= idle_limit_seconds()
        ):
            _release_llm(llm)
            _state["llm"] = None
            _state["path"] = None
            log.info("[S1] Released inactive polishing model memory")
        return True
    finally:
        _LLM_LOCK.release()


def _new_llama(llama_cls: Any, model_path: Path) -> Any:
    from voice_flow.lfm_engine import _inference_threads

    threads = _inference_threads()
    kwargs = dict(
        model_path=str(model_path), n_ctx=_CONTEXT_TOKENS,
        n_threads=threads, n_threads_batch=threads, n_batch=512, verbose=False,
    )
    try:
        return llama_cls(flash_attn=True, **kwargs)
    except TypeError:
        return llama_cls(**kwargs)


def _resident_llm(model_path: Path) -> Any:
    """Return the warm model, loading it once; caller holds ``_LLM_LOCK``."""
    from llama_cpp import Llama  # type: ignore

    llm = _state["llm"]
    if llm is None or _state["path"] != str(model_path):
        replacement = _new_llama(Llama, model_path)
        if llm is not None:
            _release_llm(llm)
        llm = replacement
        _state["llm"] = llm
        _state["path"] = str(model_path)
    register_idle_cleanup("s1-mini", _release_idle_s1, kind="polish")
    _state["last_used"] = idle_time()
    return llm


def warm_s1_model(*, timeout_seconds: float = 5.0) -> bool:
    """Load S1-mini once so the next dictation skips the cold start."""
    model_path = get_s1_model_path()
    if not model_path or timeout_seconds <= 0:
        return False
    wait = float(timeout_seconds)
    wait = 300.0 if (math.isinf(wait) or wait > 300.0) else wait
    if not _LLM_LOCK.acquire(timeout=wait):
        return False
    try:
        _resident_llm(model_path)
        return True
    except Exception as exc:
        log.warning("[S1] Could not warm local model: %s", exc)
        return False
    finally:
        _LLM_LOCK.release()


def _render_prompt(control: str, transcript: str) -> str:
    return _PROMPT_TEMPLATE.format(system=S1_SYSTEM_PROMPT, control=control, transcript=transcript)


def _token_budget(llm: Any, prompt: str, transcript: str) -> int:
    desired = min(_OUTPUT_CAP_TOKENS, max(128, len(transcript.split()) * 3 + 32))
    try:
        prompt_tokens = len(llm.tokenize(prompt.encode("utf-8"), add_bos=False, special=True))
    except Exception:
        prompt_tokens = (len(prompt.split()) + 16) * 2
    available = _CONTEXT_TOKENS - prompt_tokens - 16
    return min(desired, available) if available >= 64 else 0


def _generate(llm: Any, control: str, transcript: str, deadline: float) -> str | None:
    """One greedy, streamed, deadline-bounded normalization; ``None`` on timeout or truncation."""
    prompt = _render_prompt(control, transcript)
    max_tokens = _token_budget(llm, prompt, transcript)
    if max_tokens <= 0 or time.monotonic() >= deadline:
        return None
    # Greedy decoding is required: the GGUF metadata carries Qwen3's sampling
    # defaults, which S1-mini was not trained for.
    stream = llm.create_completion(
        prompt, max_tokens=max_tokens, temperature=0.0, top_k=1, top_p=1.0,
        repeat_penalty=1.0, stop=_STOP, stream=True,
    )
    pieces: list[str] = []
    finish_reason = None
    try:
        for chunk in stream:
            if time.monotonic() >= deadline:
                log.info("[S1] Timed out during local generation.")
                return None
            choice = (chunk.get("choices") or [{}])[0] if isinstance(chunk, dict) else {}
            finish_reason = choice.get("finish_reason") or finish_reason
            if choice.get("text"):
                pieces.append(str(choice["text"]))
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()
    if finish_reason == "length":
        log.info("[S1] Response reached its token limit; rejecting partial text.")
        return None
    return _THINK_BLOCK_RE.sub("", "".join(pieces)).strip()


def _shape_for_command(mode: str, cleaned: str) -> str:
    """Give command output the shape S1-mini cannot author on its own."""
    if mode == "prompt":
        from voice_flow.command_rewrites import restructure_prompt

        return restructure_prompt(cleaned) or cleaned
    if mode == "email" and "\n" not in cleaned:
        from voice_flow.text_processing import format_dictated_email

        return format_dictated_email(cleaned) or cleaned
    return cleaned


def _polish_with_s1_impl(text: str, instruction: str, *, timeout_seconds: float) -> str | None:
    from voice_flow.lfm_engine import _extract_transcript, _local_mode, _trusted_instruction

    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    model_path = get_s1_model_path()
    if not model_path:
        log.warning("[S1] S1-mini is not downloaded; cannot polish with it.")
        return None
    transcript, embedded_system = _extract_transcript(text)
    local_instruction = _trusted_instruction(instruction, embedded_system)
    transcript = re.sub(r"^\s*style(?: instruction)?:[^\n]*\n+", "", transcript, flags=re.IGNORECASE).strip()
    if not transcript:
        return None
    mode = _local_mode(local_instruction)
    control = control_line(local_instruction)

    mock_runner = getattr(polish_with_s1, "_mock_runner", None)
    if callable(mock_runner):
        return mock_runner(control, transcript)

    if time.monotonic() >= deadline:
        return None
    wait = deadline - time.monotonic()
    wait = 300.0 if (math.isinf(wait) or wait > 300.0) else max(0.0, wait)
    if not _LLM_LOCK.acquire(timeout=wait):
        log.info("[S1] Timed out waiting for the local model lock.")
        return None
    try:
        try:
            llm = _resident_llm(model_path)
        except ImportError:
            log.info("[S1] llama-cpp runtime unavailable; S1-mini cannot run.")
            return None
        cleaned = _generate(llm, control, transcript, deadline)
    except Exception as exc:
        log.warning("[S1] Error during S1-mini polishing: %s", exc)
        return None
    finally:
        _state["last_used"] = idle_time()
        _LLM_LOCK.release()
    if not cleaned:
        return None
    return _shape_for_command(mode, cleaned)


def polish_with_s1(text: str, instruction: str = "", *, timeout_seconds: float = 5.0) -> str | None:
    """Run one demand-scoped S1-mini pass; the model stays warm for the next one.

    Returns ``None`` when the model cannot produce a usable result, so the
    caller's fallback reports honestly that the model did not polish.
    """
    if not text or not text.strip():
        return text
    lease = acquire_model_use("polish")
    try:
        return _polish_with_s1_impl(text, instruction, timeout_seconds=timeout_seconds)
    finally:
        lease.release()
        notify_models_available("polish")


def get_catalog_entry() -> dict[str, Any]:
    """Return the Voice Flow polish picker entry for S1-mini."""
    downloaded = is_s1_downloaded()
    return {
        "full_id": S1_MODEL_ID,
        "label": f"{S1_DISPLAY_NAME} (offline · 484 MB{' · ready' if downloaded else ' · download required'})",
        "provider": "local",
        "provider_name": "Local GGUF",
        "display_name": S1_DISPLAY_NAME,
        "capabilities": ["offline", "local", "downloadable", "gguf"],
        "downloaded": downloaded,
        "polish_supported": downloaded,
        "polish_unavailable_reason": "" if downloaded else "Download required in Offline Models section (484 MB)",
        "is_fallback": False,
        "description": (
            "Speech transcript normalizer: removes fillers and stutters, resolves self-corrections, fixes "
            "punctuation and capitalization, and formats numbers, dates and emails. English only."
        ),
    }


MODEL_ID = S1_MODEL_ID


def is_model_ref(model_ref: str) -> bool:
    return is_s1_model_ref(model_ref)


def is_downloaded() -> bool:
    return is_s1_downloaded()


def polish(text: str, instruction: str = "", *, timeout_seconds: float = 5.0) -> str | None:
    return polish_with_s1(text, instruction, timeout_seconds=timeout_seconds)

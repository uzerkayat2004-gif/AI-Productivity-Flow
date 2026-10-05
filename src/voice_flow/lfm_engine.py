"""Liquid LFM 2.5 350M QAD Voice Polishing Engine.

Universal fallback local model (219 MB) for tiny, fast, offline voice polishing,
disfluency removal, and transcript cleanup.
"""
from __future__ import annotations

import logging
import math
import os
import re
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

LFM_MODEL_ID = "local/lfm2.5-350m-qad-q4_0"
LFM_FILENAME = "LFM2.5-350M-QAD-Q4_0.gguf"
LFM_ALIASES = {
    "local/lfm2.5-350m-qad-q4_0",
    "liquid/lfm2.5-350m-qad-q4_0",
    "lfm2.5-350m-qad-q4_0",
    "lfm2.5-350m",
}

# Instruction tuned for a 350M model: short, imperative, and explicit about the
# required output. Long chat-style prompts make a model this small ramble or
# answer with an analysis instead of the rewritten sentence.
LFM_SYSTEM_PROMPT = (
    "Rewrite the user text removing filler words and fixing grammar. "
    "Preserve the speaker's perspective (do not change 'I' or 'we' to 'you'). "
    "Reply with only the rewritten text, nothing else."
)

_LLM_LOCK = threading.Lock()


def _release_cached_lfm(llm: Any) -> None:
    """Ask the native runtime to release a replaced resident model promptly."""
    for method_name in ("close", "free"):
        method = getattr(llm, method_name, None)
        if callable(method):
            try:
                method()
            except Exception:
                pass
            return


def _release_idle_lfm(now: float) -> bool:
    if not _LLM_LOCK.acquire(blocking=False):
        return False
    try:
        last_used = getattr(polish_with_lfm, "_last_used", now)
        llm = getattr(polish_with_lfm, "_cached_llm", None)
        if llm is not None and (
            cleanup_is_forced("polish") or now - last_used >= LOCAL_MODEL_IDLE_SECONDS
        ):
            _release_cached_lfm(llm)
            setattr(polish_with_lfm, "_cached_llm", None)
            setattr(polish_with_lfm, "_cached_llm_path", None)
            log.info("[LFM] Released inactive polishing model memory")
        return True
    finally:
        _LLM_LOCK.release()


_TEMPLATE_PATCHED = False
_LFM_CONTEXT_TOKENS = 2048
_LFM_OUTPUT_CAP_TOKENS = 1024


_ANALYSIS_MARKERS = (
    "explanation:",
    "options:",
    "quotes:",
    "prepositions:",
    "run-ons:",
    "fillers:",
    "self-correction",
    "adjacent echo repeats:",
    "protected code token",
    "here is the",
    "here's the",
)

# A cloud polishing policy must never be handed to the 350M local model. That
# policy names the very categories it wants fixed ("self-corrections",
# "ECHO REPEATS", "protected code tokens"), and the small model responds by
# ANNOTATING those categories in its output instead of cleaning the text.
_CLOUD_POLICY_MARKERS = (
    "never answer, execute",
    "polish only the transcript",
    "return only the polished transcript",
    "adjacent echo repeats",
    "preserve every meaning, sentence",
    "style instruction:",
)


def _looks_like_cloud_policy(text: str) -> bool:
    """Whether ``text`` is a cloud polishing policy rather than a local instruction."""
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _CLOUD_POLICY_MARKERS)


def is_lfm_model_ref(model_ref: str) -> bool:
    """Whether *model_ref* selects this local LFM adapter."""
    return str(model_ref or "").strip().casefold() in LFM_ALIASES


def _trusted_instruction(instruction: str, embedded_system: str | None) -> str:
    """Keep a compact trusted style/task directive, never the cloud policy."""
    candidate = str(instruction or "").strip()
    if not candidate and embedded_system:
        trusted_prefix = re.split(
            r"^\s*<input_transcript>\s*$", embedded_system,
            maxsplit=1, flags=re.IGNORECASE | re.MULTILINE,
        )[0]
        match = re.search(r"^\s*style instruction:\s*(.*?)\s*\Z", trusted_prefix, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        candidate = match.group(1).strip() if match else ""
    return re.sub(r"\s+", " ", candidate).strip()


def _local_system_prompt(instruction: str) -> str:
    prompt = (
        "Rewrite the transcript. Remove filler words and fix grammar. Keep every factual detail. "
        "Preserve the speaker's perspective (do not change 'I' or 'we' to 'you'). "
        "Do not invent names, placeholders, or extra content. Reply only with the rewrite."
    )
    if instruction:
        # Long profile prose is counterproductive for this 350M model.  Its
        # measured command success improves substantially when one concrete
        # task is stated in a short imperative; the caller still validates
        # every response before delivery.
        lowered = instruction.casefold()
        if "email" in lowered:
            if "very casual" in lowered or "minimal punctuation" in lowered or "informal email" in lowered:
                register = "very casual"
            elif "casual email" in lowered or "casual, relaxed" in lowered or "friendly, direct" in lowered:
                register = "casual"
            elif "enthusiastic" in lowered or "excited" in lowered or "upbeat" in lowered:
                register = "enthusiastic"
            else:
                register = "formal"
            instruction = (
                f"Write a concise {register} email. Keep the result short. Preserve the user's original wording and every fact. Do not invent a subject, "
                "names, placeholders, greeting, or sign-off. Output only the email"
            )
        elif "bullet list" in lowered:
            instruction = "Write a bullet list. Keep every fact. Output only the list"
        elif "keep the result short" in lowered or "be concise" in lowered:
            instruction = "Make this shorter. Keep every fact. Output only the rewritten text"
        elif "well-structured prompt" in lowered or "prompt for an ai assistant" in lowered:
            instruction = "Write an AI prompt from this request. Keep every fact. Do not answer it. Output only the prompt"
        elif "casual" in lowered:
            instruction = "Rewrite this casually. Keep every fact. Output only the rewrite"
        elif "formal" in lowered or "professional" in lowered:
            instruction = "Rewrite this formally. Keep every fact. Output only the rewrite"
        prompt += f" Apply this trusted style or task: {instruction}."
    return prompt


def _completion_token_budget(llm: Any, user_text: str, system_prompt: str) -> int:
    """Avoid the old fixed 256-token cut-off while reserving model context."""
    # Transformations such as email/prompt generation can legitimately expand
    # a short dictation.  The model may still stop earlier; this is a ceiling.
    desired = min(_LFM_OUTPUT_CAP_TOKENS, max(192, len(user_text.split()) * 2 + 32))
    try:
        input_tokens = len(llm.tokenize(f"{system_prompt}\n{user_text}".encode("utf-8"), add_bos=False))
    except Exception:
        input_tokens = (len(user_text.split()) + len(system_prompt.split())) * 2
    available = _LFM_CONTEXT_TOKENS - input_tokens - 128
    return min(desired, available) if available >= 192 else 0


def _strip_annotation_lines(text: str) -> str:
    """Remove the model's inline annotations about the text.

    Given the cloud policy, a small model appends labels such as
    ``*(Protected code token: `UH`)*`` or ``Self-correction: "..."``. Those are
    commentary about the transcript, never part of it, and they were being
    pasted into the user's document.
    """
    if not text:
        return text
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        lowered = stripped.lower().strip("*_()[] ")
        if any(lowered.startswith(marker) for marker in _ANALYSIS_MARKERS):
            continue
        # A parenthesised/bracketed annotation at the end of an otherwise real
        # line, e.g. "Some text *(Protected code token: X)*".
        cleaned = re.sub(
            r"\s*[*_(\[]\s*(?:" + "|".join(re.escape(m) for m in _ANALYSIS_MARKERS) + r")[^)\]]*[*_)\]]\s*$",
            "",
            stripped,
            flags=re.IGNORECASE,
        ).strip()
        if cleaned:
            kept.append(cleaned)
    return "\n".join(kept).strip()


def _looks_like_analysis(text: str) -> bool:
    """Whether a tiny model answered with commentary instead of a rewrite."""
    lowered = (text or "").lower()
    if not lowered:
        return False
    # A heading-style marker on its own line is unambiguous commentary.
    hits = sum(1 for marker in _ANALYSIS_MARKERS if marker in lowered)
    if hits >= 2:
        return True
    return any(
        lowered.startswith(marker) or f"\n{marker}" in lowered
        for marker in _ANALYSIS_MARKERS
    )


def _patch_chat_template_parser() -> None:
    """Teach llama-cpp to ignore HuggingFace ``{% generation %}`` blocks.

    LFM 2.5 ships a chat template that includes the training-only
    ``{% generation %}`` tag. llama-cpp renders the template with a plain
    Jinja2 environment that does not know that tag, so loading the model
    raises a TemplateSyntaxError before any inference happens. The tag only
    marks which spans are trained on; it has no effect on inference, so
    stripping it is safe and lets the model load and run.
    """
    global _TEMPLATE_PATCHED
    if _TEMPLATE_PATCHED:
        return
    try:
        import llama_cpp.llama_chat_format as chat_format

        original_init = chat_format.Jinja2ChatFormatter.__init__

        def patched_init(self, template=None, *args, **kwargs):  # type: ignore[no-untyped-def]
            if isinstance(template, str):
                template = re.sub(r"\{%-?\s*generation\s*-?%\}", "", template)
                template = re.sub(r"\{%-?\s*endgeneration\s*-?%\}", "", template)
            return original_init(self, template=template, *args, **kwargs)

        chat_format.Jinja2ChatFormatter.__init__ = patched_init
        _TEMPLATE_PATCHED = True
    except Exception as exc:
        log.debug("[LFM] Could not patch chat template parser: %s", exc)


def get_lfm_model_path() -> Path | None:
    """Return local path to downloaded LFM 2.5 350M model file if present."""
    target = downloadable_models.get_models_dir() / LFM_FILENAME
    if target.is_file() and target.stat().st_size > 0:
        return target
    return None


def _extract_transcript(text: str) -> tuple[str, str | None]:
    """Extract raw transcript text and any embedded system prompt."""
    if not text:
        return text, None
    # The cloud command policy itself mentions ``<input_transcript>`` in a
    # sentence.  Only the line-delimited wrapper emitted by the caller marks
    # real dictated text; otherwise an email command feeds policy prose to
    # LFM and loses the style directive.
    match = re.search(
        r"^\s*<input_transcript>\s*$\s*^(.*?)^\s*</input_transcript>\s*$",
        text, re.DOTALL | re.IGNORECASE | re.MULTILINE,
    )
    if not match:
        # Compatibility for direct callers that supply a compact one-line
        # wrapper, which cannot be confused with the policy sentence above.
        match = re.search(r"<input_transcript>([^\n]*?)</input_transcript>", text, re.IGNORECASE)
    if match:
        raw = match.group(1).strip()
        sys_p = text[:match.start()].strip() or None
        return raw, sys_p
    if "\n\n" in text:
        parts = text.split("\n\n", 1)
        if len(parts) == 2 and any(kw in parts[0].lower() for kw in ("polish", "grammar", "assistant", "dictation", "transcript", "clarity")):
            return parts[1].strip(), parts[0].strip()
    return text.strip(), None


def is_lfm_downloaded() -> bool:
    """Check if LFM 2.5 350M QAD is downloaded and ready for use."""
    return get_lfm_model_path() is not None


def is_lfm_runtime_available() -> bool:
    """Whether the local inference runtime needed to run the GGUF is present."""
    try:
        import importlib.util

        return importlib.util.find_spec("llama_cpp") is not None
    except Exception:
        return False


def warm_lfm_model(*, timeout_seconds: float = 5.0) -> bool:
    """Load the local model once so the first dictation avoids cold-start cost."""
    model_path = get_lfm_model_path()
    if not model_path or not is_lfm_runtime_available() or timeout_seconds <= 0:
        return False
    t_sec = float(timeout_seconds)
    t_sec = 300.0 if (math.isinf(t_sec) or t_sec > 300.0) else max(0.0, t_sec)
    if not _LLM_LOCK.acquire(timeout=t_sec):
        return False
    try:
        _patch_chat_template_parser()
        register_idle_cleanup("lfm", _release_idle_lfm, kind="polish")
        if getattr(polish_with_lfm, "_cached_llm_path", None) == str(model_path):
            setattr(polish_with_lfm, "_last_used", idle_time())
            return True
        from llama_cpp import Llama  # type: ignore

        llm = Llama(
            model_path=str(model_path), n_ctx=_LFM_CONTEXT_TOKENS,
            n_threads=max(1, min(8, os.cpu_count() or 4)), n_batch=512, verbose=False,
        )
        old_llm = getattr(polish_with_lfm, "_cached_llm", None)
        if old_llm is not None:
            _release_cached_lfm(old_llm)
        setattr(polish_with_lfm, "_cached_llm", llm)
        setattr(polish_with_lfm, "_cached_llm_path", str(model_path))
        setattr(polish_with_lfm, "_last_used", idle_time())
        return True
    except Exception as exc:
        log.warning("[LFM] Could not warm local model: %s", exc)
        return False
    finally:
        _LLM_LOCK.release()


def _polish_with_lfm_impl(
    text: str,
    instruction: str = "",
    *,
    timeout_seconds: float = 5.0,
    system_prompt: str | None = None,
) -> str | None:
    """Execute voice polishing using the downloaded LFM 2.5 350M local model.

    Returns the polished text, or ``None`` when the model cannot actually run.
    It deliberately never substitutes a regex cleanup: a deterministic pass is
    not this model, and reporting it as one made the UI claim "AI polished"
    for output the model never produced. The caller owns that fallback and
    reports it honestly.
    """
    if not text or not text.strip():
        return text
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))

    model_path = get_lfm_model_path()
    if not model_path:
        log.warning("[LFM] Model %s is not downloaded; cannot polish with LFM.", LFM_FILENAME)
        return None

    user_text, embedded_sys = _extract_transcript(text)
    effective_system = system_prompt or embedded_sys
    local_instruction = _trusted_instruction(instruction, effective_system)

    # The 350M model must never receive the cloud polishing policy. That policy
    # enumerates the categories to fix ("self-corrections", "ECHO REPEATS",
    # "protected code tokens"), and the small model reacts by annotating those
    # categories in its answer - labels like
    # ``*(Protected code token: `UH`)*`` were being pasted into the document.
    # The local model gets its own short, purpose-built instruction instead.
    if effective_system and _looks_like_cloud_policy(effective_system):
        log.info("[LFM] Cloud polishing policy detected; using the local instruction instead.")
        effective_system = None
    # Strip a leading style directive from the transcript body: it is guidance
    # for the model, not something the speaker dictated.
    user_text = re.sub(
        r"^\s*style instruction:[^\n]*\n+", "", user_text, flags=re.IGNORECASE
    ).strip()
    user_text = re.sub(
        r"^\s*style:\s*[^\n]*\n+", "", user_text, flags=re.IGNORECASE
    ).strip()

    # Check for test/mock override callback
    mock_runner = getattr(polish_with_lfm, "_mock_runner", None)
    if callable(mock_runner):
        return mock_runner(text, instruction)

    # Importing llama-cpp can itself take longer than a short interactive
    # budget; do not begin it after the call has already expired.
    if time.monotonic() >= deadline:
        return None

    try:
        # Keep the model resident between dictations.  A context is not safe
        # for concurrent use, so waiting for one is bounded by this request's
        # deadline instead of queuing a stale dictation indefinitely.
        rem = deadline - time.monotonic()
        rem = 300.0 if (math.isinf(rem) or rem > 300.0) else max(0.0, rem)
        if not _LLM_LOCK.acquire(timeout=rem):
            log.info("[LFM] Timed out waiting for the local model lock.")
            return None
        try:
            try:
                from llama_cpp import Llama  # type: ignore
            except Exception:
                # No inference runtime: this model cannot run, so it must not
                # be reported as having polished anything.
                log.info("[LFM] llama-cpp runtime unavailable; the local model cannot run.")
                return None
            _patch_chat_template_parser()
            llm = getattr(polish_with_lfm, "_cached_llm", None)
            cached_path = getattr(polish_with_lfm, "_cached_llm_path", None)
            if llm is None or cached_path != str(model_path):
                replacement = Llama(
                    model_path=str(model_path), n_ctx=_LFM_CONTEXT_TOKENS,
                    n_threads=max(1, min(8, os.cpu_count() or 4)), n_batch=512, verbose=False,
                )
                if llm is not None:
                    _release_cached_lfm(llm)
                llm = replacement
                setattr(polish_with_lfm, "_cached_llm", llm)
                setattr(polish_with_lfm, "_cached_llm_path", str(model_path))
            register_idle_cleanup("lfm", _release_idle_lfm, kind="polish")
            setattr(polish_with_lfm, "_last_used", idle_time())
            local_system = _local_system_prompt(local_instruction)
            max_tokens = _completion_token_budget(llm, user_text, local_system)
            if max_tokens <= 0 or time.monotonic() >= deadline:
                return None
            resp = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": local_system},
                    {"role": "user", "content": user_text},
                ],
                max_tokens=max_tokens,
                temperature=0.1,
                top_k=50,
                repeat_penalty=1.05,
                stream=True,
            )
            chunks: list[str] = []
            finish_reason = None
            try:
                if isinstance(resp, dict):
                    choices = resp.get("choices") or []
                    if choices:
                        choice = choices[0]
                        finish_reason = choice.get("finish_reason")
                        msg = choice.get("message") or {}
                        content_piece = msg.get("content") or choice.get("text") or ""
                        if content_piece:
                            chunks.append(str(content_piece))
                else:
                    for chunk in resp:
                        if time.monotonic() >= deadline:
                            log.info("[LFM] Timed out during local generation.")
                            return None
                        if not isinstance(chunk, dict):
                            continue
                        choice = (chunk.get("choices") or [{}])[0]
                        finish_reason = choice.get("finish_reason") or finish_reason
                        piece = (choice.get("delta") or {}).get("content") or choice.get("text")
                        if piece:
                            chunks.append(str(piece))
            finally:
                close = getattr(resp, "close", None)
                if callable(close):
                    close()
            if finish_reason == "length":
                log.info("[LFM] Local response reached its token limit; rejecting partial text.")
                return None
            content = "".join(chunks).strip()
        finally:
            try:
                setattr(polish_with_lfm, "_last_used", idle_time())
            finally:
                _LLM_LOCK.release()
        # A tiny model occasionally appends a stray newline or trailing spaces.
        content = content.strip().strip('"').strip()
        # It may also echo the wrapping tags it saw in the prompt.
        content = re.sub(r"</?input_transcript>", "", content, flags=re.IGNORECASE).strip()
        # Drop inline annotations about the text (e.g. "(Protected code token:
        # `UH`)") so commentary can never be pasted as if it were the dictation.
        content = _strip_annotation_lines(content)
        # Reject an analysis answer ("Explanation:", "Options:", ...) instead of
        # the rewritten sentence. Presenting that as the polished dictation
        # would paste the model's commentary over the user's words.
        if _looks_like_analysis(content):
            log.info("[LFM] Model returned commentary rather than a rewrite; discarding.")
            return None
        return content or None
    except Exception as exc:
        log.warning("[LFM] Error during LFM voice polishing: %s", exc)
        return None


def polish_with_lfm(
    text: str,
    instruction: str = "",
    *,
    timeout_seconds: float = 5.0,
    system_prompt: str | None = None,
) -> str | None:
    """Run one demand-scoped local polish and promptly release its model."""
    if not text or not text.strip():
        return text
    lease = acquire_model_use("polish")
    try:
        return _polish_with_lfm_impl(
            text,
            instruction,
            timeout_seconds=timeout_seconds,
            system_prompt=system_prompt,
        )
    finally:
        lease.release()
        notify_models_available("polish")


def get_catalog_entry() -> dict[str, Any]:
    """Return model specification for the Voice Flow polish model catalog."""
    downloaded = is_lfm_downloaded()
    return {
        "full_id": LFM_MODEL_ID,
        "label": f"Liquid LFM 2.5 350M (offline · 219 MB{' · ready' if downloaded else ' · download required'})",
        "provider": "local",
        "provider_name": "Local GGUF",
        "display_name": "Liquid LFM 2.5 350M QAD",
        "capabilities": ["offline", "local", "downloadable", "gguf"],
        "downloaded": downloaded,
        "polish_supported": downloaded,
        "polish_unavailable_reason": "" if downloaded else "Download required in Offline Models section (219 MB)",
        "is_fallback": True,
        "description": "Universal fallback tiny 350M local model. Fast local instruction-following for voice polishing.",
    }

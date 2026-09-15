"""Liquid LFM 2.5 350M QAD Voice Polishing Engine.

Universal fallback local model (219 MB) for tiny, fast, offline voice polishing,
disfluency removal, and transcript cleanup.
"""
from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Any

from voice_flow import downloadable_models

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
    "Reply with only the rewritten text, nothing else."
)

_LLM_LOCK = threading.Lock()
_TEMPLATE_PATCHED = False


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
    match = re.search(r"<input_transcript>(.*?)</input_transcript>", text, re.DOTALL | re.IGNORECASE)
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


def polish_with_lfm(
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

    model_path = get_lfm_model_path()
    if not model_path:
        log.warning("[LFM] Model %s is not downloaded; cannot polish with LFM.", LFM_FILENAME)
        return None

    user_text, embedded_sys = _extract_transcript(text)
    effective_system = system_prompt or embedded_sys

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

    try:
        from llama_cpp import Llama  # type: ignore
    except Exception:
        # No inference runtime: this model cannot run, so it must not be
        # reported as having polished anything.
        log.info("[LFM] llama-cpp runtime unavailable; the local model cannot run.")
        return None

    _patch_chat_template_parser()

    try:
        # Keep the model resident between dictations: loading the GGUF per
        # request would add seconds to every polish. The lock serializes
        # access because a llama.cpp context is not safe for concurrent use.
        with _LLM_LOCK:
            llm = getattr(polish_with_lfm, "_cached_llm", None)
            cached_path = getattr(polish_with_lfm, "_cached_llm_path", None)
            if llm is None or cached_path != str(model_path):
                llm = Llama(model_path=str(model_path), n_ctx=1024, verbose=False)
                setattr(polish_with_lfm, "_cached_llm", llm)
                setattr(polish_with_lfm, "_cached_llm_path", str(model_path))
            sys_msg = effective_system or LFM_SYSTEM_PROMPT
            resp = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": user_text},
                ],
                max_tokens=256,
                temperature=0.1,
            )
            content = str(resp["choices"][0]["message"]["content"] or "").strip()
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

"""Microsoft Windows AI TextRewriter & LanguageModel integration.

Provides native Windows AI rewriting/polishing via Microsoft.Windows.AI.Generative.LanguageModel
on Windows 11 Copilot+ hardware with 0 MB installer footprint.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Any

log = logging.getLogger(__name__)

WINDOWS_AI_MODEL_ID = "microsoft/windows-ai-text-rewriter"
WINDOWS_AI_ALIASES = {
    "microsoft/windows-ai-text-rewriter",
    "windows/text-rewriter",
    "microsoft/text-rewriter",
    "local/windows-ai-text-rewriter",
    "local/windows-ai",
}

_STATE_LOCK = threading.Lock()
_CACHED_READY_STATE: str | None = None
_MOCK_READY_STATE: str | None = None


def set_mock_ready_state(state: str | None) -> None:
    """Set mock ready state for testing ('Ready', 'NotReady', 'Disabled', None)."""
    global _MOCK_READY_STATE, _CACHED_READY_STATE
    with _STATE_LOCK:
        _MOCK_READY_STATE = state
        _CACHED_READY_STATE = state


def get_language_model_ready_state() -> str:
    """Query Microsoft.Windows.AI.Generative.LanguageModel.GetReadyState().

    Returns:
        'Ready': Model is available on hardware (NPU Copilot+) and ready for rewriting.
        'NotReady': Windows AI or hardware is present but model is not downloaded or initialising.
        'Disabled': Windows AI feature is disabled in OS settings.
        'Unavailable': Platform is not Windows or Windows AI APIs are not present.
    """
    global _CACHED_READY_STATE
    with _STATE_LOCK:
        if _MOCK_READY_STATE is not None:
            return _MOCK_READY_STATE

    # Allow environment variable override for testing or manual flag
    env_state = os.environ.get("VOICE_FLOW_WINDOWS_AI_READY_STATE")
    if env_state:
        return env_state.strip()

    if sys.platform != "win32":
        return "Unavailable"

    # Try inspecting Windows App SDK WinRT LanguageModel
    try:
        # Check pythonnet or winrt if present
        try:
            import clr  # type: ignore
            clr.AddReference("Microsoft.Windows.AI.Generative")  # type: ignore
            from Microsoft.Windows.AI.Generative import LanguageModel  # type: ignore
            state = LanguageModel.GetReadyState()
            state_str = str(state)
            if "ready" in state_str.lower():
                return "Ready"
            if "notready" in state_str.lower():
                return "NotReady"
            if "disabled" in state_str.lower():
                return "Disabled"
            return state_str
        except Exception:
            pass

        # Try winrt / winsdk runtime inspection if available
        try:
            import winrt.microsoft.windows.ai.generative as win_gen  # type: ignore
            if hasattr(win_gen, "LanguageModel"):
                state = win_gen.LanguageModel.get_ready_state()
                return "Ready" if "ready" in str(state).lower() else "NotReady"
        except Exception:
            pass

        # On non-Copilot+ PCs or when package identity is not present
        return "NotReady"
    except Exception as exc:
        log.debug("[WINDOWS_AI] LanguageModel.GetReadyState() check failed: %s", exc)
        return "Unavailable"


def _extract_transcript(text: str) -> tuple[str, str | None]:
    """Extract raw transcript text and any embedded system prompt."""
    if not text:
        return text, None
    import re
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


def is_windows_ai_available() -> bool:
    """Check if Microsoft Windows AI TextRewriter is ready for immediate execution."""
    return get_language_model_ready_state().lower() == "ready"


def rewrite_text(
    text: str,
    instruction: str = "",
    *,
    timeout_seconds: float = 5.0,
    system_prompt: str | None = None,
) -> str | None:
    """Rewrite/polish text using Windows AI LanguageModel / TextRewriter.

    Returns polished string on success, or None if unavailable / failed.
    """
    if not text or not text.strip():
        return text

    # Verify ready state
    ready_state = get_language_model_ready_state()
    if ready_state.lower() != "ready":
        log.info("[WINDOWS_AI] LanguageModel is not ready (%s); skipping Windows AI rewrite.", ready_state)
        return None

    user_text, embedded_sys = _extract_transcript(text)
    effective_system = system_prompt or embedded_sys

    # Check for test/mock override callback
    mock_rewriter = getattr(rewrite_text, "_mock_rewriter", None)
    if callable(mock_rewriter):
        return mock_rewriter(text, instruction)

    try:
        # Attempt WinRT invocation if available
        try:
            import clr  # type: ignore
            from Microsoft.Windows.AI.Generative import LanguageModel  # type: ignore
            model = LanguageModel.CreateAsync().GetAwaiter().GetResult()
            prompt = (
                f"{effective_system or 'Polish the following dictation to clean grammar, filler words, and clarity:'}\n\n"
                f"{user_text}"
            )
            resp = model.GenerateResponseAsync(prompt).GetAwaiter().GetResult()
            output = str(resp.Text).strip()
            if output:
                return output
        except Exception as e:
            log.debug("[WINDOWS_AI] Direct WinRT generation failed: %s", e)

        # The model reported ready but produced nothing. Do not substitute a
        # regex cleanup and present it as Windows AI output: the caller owns
        # the deterministic fallback and reports it honestly.
        return None
    except Exception as exc:
        log.warning("[WINDOWS_AI] rewrite_text encountered error: %s", exc)
        return None


def get_catalog_entry() -> dict[str, Any]:
    """Return model specification for the Voice Flow polish model catalog."""
    ready_state = get_language_model_ready_state()
    ready = ready_state.lower() == "ready"
    reason = ""
    if not ready:
        if ready_state.lower() == "notready":
            reason = "Requires Windows 11 Copilot+ hardware with local NPU"
        elif ready_state.lower() == "disabled":
            reason = "Windows AI feature is disabled in Windows Settings"
        else:
            reason = "Windows AI is unavailable on this hardware"

    return {
        "full_id": WINDOWS_AI_MODEL_ID,
        "label": "Microsoft Windows AI TextRewriter (offline · NPU / Copilot+ · default)",
        "provider": "microsoft",
        "provider_name": "Microsoft Windows AI",
        "display_name": "Microsoft TextRewriter (Windows AI)",
        "capabilities": ["offline", "npu", "local", "zero-download"],
        "ready_state": ready_state,
        "polish_supported": ready,
        "polish_unavailable_reason": reason,
        "is_default": ready,
        "description": "Native Windows 11 Copilot+ local AI model. 0 MB download, hardware-accelerated on NPU.",
    }

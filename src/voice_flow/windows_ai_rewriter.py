"""Microsoft Windows AI TextRewriter & LanguageModel integration.

Provides native Windows AI rewriting/polishing via Microsoft.Windows.AI.Generative.LanguageModel
on Windows 11 Copilot+ hardware with 0 MB installer footprint.
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path
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
_CACHED_READY_AT = 0.0
_CACHE_SECONDS = 60.0
_PROBE_LOCK = threading.Lock()
_READY_STATES = frozenset({"Ready", "NotReady", "Disabled", "Unavailable"})
_MOCK_READY_STATE: str | None = None


def set_mock_ready_state(state: str | None) -> None:
    """Set mock ready state for testing ('Ready', 'NotReady', 'Disabled', None)."""
    global _MOCK_READY_STATE, _CACHED_READY_STATE, _CACHED_READY_AT
    with _STATE_LOCK:
        _MOCK_READY_STATE = state
        _CACHED_READY_STATE = state
        _CACHED_READY_AT = time.monotonic() if state is not None else 0.0


def _normalize_ready_state(state: Any) -> str:
    # Enum string forms may be qualified; match the tail exactly so NotReady
    # can never be mistaken for Ready.
    tail = str(state).rsplit(".", 1)[-1].strip().lower()
    return {value.lower(): value for value in _READY_STATES}.get(tail, "Unavailable")


def _native_language_model_ready_state() -> str:
    """Native discovery runs only in the disposable readiness child."""
    try:
        import clr  # type: ignore
        clr.AddReference("Microsoft.Windows.AI.Generative")  # type: ignore
        from Microsoft.Windows.AI.Generative import LanguageModel  # type: ignore
        return _normalize_ready_state(LanguageModel.GetReadyState())
    except Exception:
        pass
    try:
        import winrt.microsoft.windows.ai.generative as win_gen  # type: ignore
        if hasattr(win_gen, "LanguageModel"):
            return _normalize_ready_state(win_gen.LanguageModel.get_ready_state())
    except Exception:
        pass
    return "NotReady"


def _has_probe_memory() -> bool:
    """Do not start optional native discovery under Windows commit pressure."""
    try:
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in (
                    "physical_total", "physical_available", "commit_limit",
                    "commit_available", "virtual_total", "virtual_available", "extended")]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        return bool(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))) and status.commit_available >= 1024 * 1024 * 1024
    except Exception:
        return False


def _acquire_probe_mutex() -> tuple[Any, Any] | None:
    """Serialize optional native discovery across the app's processes."""
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
        kernel32.ReleaseMutex.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.CreateMutexW(None, False, "Local\\AIProductivityFlow.WindowsAIReadinessProbe")
        if not handle:
            return None
        try:
            if kernel32.WaitForSingleObject(handle, 0) in (0, 128):
                return kernel32, handle
        except BaseException:
            kernel32.CloseHandle(handle)
            raise
        kernel32.CloseHandle(handle)
    except (OSError, AttributeError, MemoryError):
        pass
    return None


def _release_probe_mutex(lease: tuple[Any, Any]) -> None:
    kernel32, handle = lease
    try:
        kernel32.ReleaseMutex(handle)
    finally:
        kernel32.CloseHandle(handle)


def _run_readiness_child() -> str:
    from voice_flow.runtime_env import python_executable

    command = [python_executable(), "-I", "-B", "-u", str(Path(__file__).resolve()), "--native-readiness-probe"]
    # -I excludes the caller's import paths. Forward only existing dependency
    # directories, never the application package or its initializer.
    for entry in sys.path:
        directory = Path(entry)
        if directory.name.lower() == "site-packages" and directory.is_dir():
            command.extend(["--site-packages", str(directory.resolve())])
    try:
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", timeout=3, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            return "NotReady"
        state = json.loads(result.stdout)
        return state if isinstance(state, str) and state in _READY_STATES else "NotReady"
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, MemoryError):
        return "NotReady"


def _probe_language_model_ready_state() -> str:
    lease = _acquire_probe_mutex()
    if lease is None:
        return "NotReady"
    try:
        # Recheck after taking the cross-process gate: another process may
        # have consumed headroom while this caller was reaching the gate.
        if not _has_probe_memory():
            return "NotReady"
        return _run_readiness_child()
    except MemoryError:
        return "NotReady"
    finally:
        _release_probe_mutex(lease)


def get_language_model_ready_state() -> str:
    """Read bounded, cached native availability without loading CLR here."""
    global _CACHED_READY_STATE, _CACHED_READY_AT
    with _STATE_LOCK:
        if _MOCK_READY_STATE is not None:
            return _MOCK_READY_STATE
    env_state = os.environ.get("VOICE_FLOW_WINDOWS_AI_READY_STATE")
    if env_state:
        return env_state.strip()
    if sys.platform != "win32":
        return "Unavailable"
    with _STATE_LOCK:
        cached = _CACHED_READY_STATE
        if cached is not None and time.monotonic() - _CACHED_READY_AT < _CACHE_SECONDS:
            return cached
    if not _PROBE_LOCK.acquire(blocking=False):
        return cached or "NotReady"
    try:
        # Another caller can populate the cache between our checks.
        with _STATE_LOCK:
            if _CACHED_READY_STATE is not None and time.monotonic() - _CACHED_READY_AT < _CACHE_SECONDS:
                return _CACHED_READY_STATE
        state = _probe_language_model_ready_state()
        with _STATE_LOCK:
            # A test/explicit override during the probe remains authoritative.
            if _MOCK_READY_STATE is not None:
                return _MOCK_READY_STATE
            _CACHED_READY_STATE = state
            _CACHED_READY_AT = time.monotonic()
        return state
    finally:
        _PROBE_LOCK.release()


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


if __name__ == "__main__":
    # Direct script execution avoids importing voice_flow.__init__ in the child.
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--native-readiness-probe", action="store_true")
    parser.add_argument("--site-packages", action="append", default=[])
    args = parser.parse_args()
    if args.native_readiness_probe:
        for entry in args.site_packages:
            directory = Path(entry)
            if directory.name.lower() == "site-packages" and directory.is_dir():
                sys.path.append(str(directory.resolve()))
        print(json.dumps(_native_language_model_ready_state()))

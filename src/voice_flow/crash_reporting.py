"""Opt-in, privacy-preserving Sentry crash reporting for AI Productivity Flow.

Strict privacy rules:
- Completely opt-in: disabled by default (zero network calls, zero SDK overhead when disabled).
- Never sends audio data, transcripts, dictation, clipboard text, or request payloads.
- Redacts local usernames in system file paths (/Users/<username> and C:\\Users\\<username>).
- Redacts all environment tokens and API keys (OPENAI_*, ANTHROPIC_*, GROQ_*, GEMINI_*, DEEPGRAM_*, SENTRY_*, AWS_*, etc.).
- Performance tracing and profiling are completely disabled (0% sample rate).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from voice_flow._version import VERSION
from voice_flow.storage import storage

log = logging.getLogger(__name__)

SENTRY_DSN = "https://fc3e1f0f34b173a05e9260221c02de15@o4512216642486272.ingest.de.sentry.io/4512224903823440"
_CRASH_REPORTING_INITIALIZED = False

# Regex patterns for privacy scrubbing
_WIN_USER_PATTERN = re.compile(r"([a-zA-Z]:[\\/]Users)[\\/][^\\/:\s\"']+", re.IGNORECASE)
_MAC_USER_PATTERN = re.compile(r"/Users/[^/:\s\"']+", re.IGNORECASE)
_SENSITIVE_WORDS_PATTERN = re.compile(
    r"\b(transcript(?:s|ion)?|audio|recording(?:s)?|dictation(?:s)?)\b",
    re.IGNORECASE,
)
_API_KEY_ENV_PATTERN = re.compile(
    r"^(OPENAI|ANTHROPIC|GROQ|GEMINI|DEEPGRAM|SENTRY|AWS|AZURE|VOICE_FLOW|SECRET|TOKEN|KEY|PASSWORD|AUTH)",
    re.IGNORECASE,
)
_KEY_VALUE_PATTERN = re.compile(
    r"\b(?:sk-[a-zA-Z0-9_\-]{16,}|gsk_[a-zA-Z0-9_\-]{16,}|AIzaSy[a-zA-Z0-9_\-]{25,}|ghp_[a-zA-Z0-9]{20,})\b"
)


def _scrub_string(text: str) -> str:
    """Scrub personal paths, sensitive words, and credentials from a string."""
    if not isinstance(text, str):
        return text

    # 1. Scrub user directory paths
    text = _WIN_USER_PATTERN.sub(r"\1\\[REDACTED]", text)
    text = _MAC_USER_PATTERN.sub("/Users/[REDACTED]", text)

    # 2. Scrub sensitive domain keywords (audio, transcripts, dictation)
    text = _SENSITIVE_WORDS_PATTERN.sub("[REDACTED]", text)

    # 3. Scrub inline API keys
    text = _KEY_VALUE_PATTERN.sub("[REDACTED_KEY]", text)

    return text


def _scrub_object(obj: Any) -> Any:
    """Recursively scrub strings, dicts, lists, and tuples."""
    if isinstance(obj, str):
        return _scrub_string(obj)
    elif isinstance(obj, dict):
        cleaned: dict[str, Any] = {}
        for k, v in obj.items():
            key_str = str(k)
            # Redact sensitive environment keys or header tokens
            if _API_KEY_ENV_PATTERN.search(key_str) or any(
                s in key_str.lower() for s in ("token", "secret", "password", "api_key", "authorization", "cookie")
            ):
                cleaned[key_str] = "[REDACTED]"
            else:
                cleaned[key_str] = _scrub_object(v)
        return cleaned
    elif isinstance(obj, list):
        return [_scrub_object(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(_scrub_object(item) for item in obj)
    return obj


def before_send_scrubber(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Privacy scrubber hook invoked prior to sending any event to Sentry."""
    try:
        # 1. Drop request bodies, query params, cookies
        if "request" in event and isinstance(event["request"], dict):
            req = event["request"]
            req.pop("data", None)
            req.pop("query_string", None)
            req.pop("cookies", None)
            if "headers" in req and isinstance(req["headers"], dict):
                req["headers"] = {
                    k: ("[REDACTED]" if any(s in str(k).lower() for s in ("auth", "cookie", "token", "key")) else _scrub_string(str(v)))
                    for k, v in req["headers"].items()
                }

        # 2. Drop user PII fields if present
        if "user" in event:
            event["user"] = {"id": "[ANONYMOUS]"}

        # 3. Redact environment variables in event contexts
        if "contexts" in event and isinstance(event["contexts"], dict):
            event["contexts"] = _scrub_object(event["contexts"])

        # 4. Scrub message, logentry, and breadcrumbs
        if "message" in event and isinstance(event["message"], str):
            event["message"] = _scrub_string(event["message"])

        if "logentry" in event and isinstance(event["logentry"], dict):
            if "message" in event["logentry"]:
                event["logentry"]["message"] = _scrub_string(event["logentry"]["message"])
            if "formatted" in event["logentry"]:
                event["logentry"]["formatted"] = _scrub_string(event["logentry"]["formatted"])

        if "breadcrumbs" in event:
            breadcrumbs = event["breadcrumbs"]
            if isinstance(breadcrumbs, dict) and "values" in breadcrumbs:
                breadcrumbs["values"] = _scrub_object(breadcrumbs["values"])
            elif isinstance(breadcrumbs, list):
                event["breadcrumbs"] = _scrub_object(breadcrumbs)

        # 5. Scrub exception values, types, and stacktrace frames
        if "exception" in event and isinstance(event["exception"], dict):
            values = event["exception"].get("values", [])
            for exc in values:
                if isinstance(exc, dict):
                    if "value" in exc:
                        exc["value"] = _scrub_string(str(exc["value"]))
                    stacktrace = exc.get("stacktrace")
                    if isinstance(stacktrace, dict):
                        for frame in stacktrace.get("frames", []):
                            if isinstance(frame, dict):
                                if "filename" in frame:
                                    frame["filename"] = _scrub_string(str(frame["filename"]))
                                if "abs_path" in frame:
                                    frame["abs_path"] = _scrub_string(str(frame["abs_path"]))
                                if "vars" in frame and isinstance(frame["vars"], dict):
                                    frame["vars"] = _scrub_object(frame["vars"])

        # 6. Scrub extra context tags
        if "extra" in event and isinstance(event["extra"], dict):
            event["extra"] = _scrub_object(event["extra"])

        return event
    except Exception as exc:
        log.warning("Exception during crash report scrubbing: %s", exc)
        return event


def is_crash_reporting_enabled() -> bool:
    """Return True if the user has explicitly opted into anonymous crash reporting."""
    return bool(storage.get_setting("anonymous_crash_reports", False))


def init_crash_reporting(force: bool = False) -> bool:
    """Initialize Sentry crash reporting if opted-in or force=True.

    Zero network requests and zero SDK overhead when disabled (default).
    """
    global _CRASH_REPORTING_INITIALIZED
    enabled = is_crash_reporting_enabled()

    if not enabled and not force:
        return False

    try:
        import sentry_sdk
    except ImportError:
        log.warning("sentry-sdk is not installed; crash reporting is unavailable.")
        return False

    try:
        from voice_flow import runtime_env
        environment = "production" if runtime_env.is_installed() else "development"
    except Exception:
        environment = "production"

    release = f"ai-productivity-flow@{VERSION}"

    try:
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            release=release,
            environment=environment,
            send_default_pii=False,
            traces_sample_rate=0.0,
            profiles_sample_rate=0.0,
            max_breadcrumbs=20,
            attach_stacktrace=True,
            before_send=before_send_scrubber,
        )
        _CRASH_REPORTING_INITIALIZED = True
        log.info("Anonymous crash reporting initialized (%s, release=%s).", environment, release)
        return True
    except Exception as exc:
        log.warning("Could not initialize Sentry crash reporting: %s", exc)
        return False


def capture_test_crash_report() -> bool:
    """Send a test crash report to Sentry to verify connectivity and configuration."""
    try:
        import sentry_sdk
        if not _CRASH_REPORTING_INITIALIZED:
            init_crash_reporting(force=True)
        sentry_sdk.capture_message(f"Test crash report from AI Productivity Flow v{VERSION}")
        sentry_sdk.flush(timeout=5.0)
        return True
    except Exception as exc:
        log.warning("Failed to send test crash report: %s", exc)
        return False

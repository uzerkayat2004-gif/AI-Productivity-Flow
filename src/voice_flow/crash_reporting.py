"""Privacy-preserving Sentry crash reporting for AI Productivity Flow.

Strict privacy rules:
- On by default for every install, including existing users who never set the
  toggle. An explicit opt-out turns it off immediately, with no restart.
- Never sends audio data, transcripts, dictation, clipboard text, or request payloads:
  no local variables, no breadcrumbs, no log events, and exception messages are
  replaced by '[redacted]' (only the exception type and code location are kept).
- Redacts local usernames in system file paths (/Users/<username> and C:\\Users\\<username>).
- Redacts all environment tokens and API keys (OPENAI_*, ANTHROPIC_*, GROQ_*, GEMINI_*, DEEPGRAM_*, SENTRY_*, AWS_*, etc.).
- Performance tracing and profiling are completely disabled (0% sample rate).
- Never sends from CI or automated test runs: when ``CI`` or
  ``VOICE_FLOW_CRASH_REPORTS_NO_SEND`` is set, the SDK is initialised without a DSN
  (a no-op client), so test and CI runs cannot pollute the production Sentry project.
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

# Set to 1/true to keep crash reporting fully local (no events leave the machine).
# The pytest suite sets this automatically (see tests/conftest.py).
NO_SEND_ENV_VAR = "VOICE_FLOW_CRASH_REPORTS_NO_SEND"
_FALSEY = {"", "0", "false", "no", "off"}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() not in _FALSEY


def is_ci_environment() -> bool:
    """True when running under a CI system (GitHub Actions, CircleCI, etc. set ``CI``)."""
    return _env_flag("CI")


def is_sending_suppressed() -> bool:
    """True when crash reports must not be sent (CI, automated tests, explicit opt-out)."""
    return _env_flag(NO_SEND_ENV_VAR) or is_ci_environment()

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


REDACTED = "[redacted]"
TEST_CRASH_MESSAGE = f"Test crash report from AI Productivity Flow v{VERSION}"
# The only free-text messages allowed to leave the machine: fixed strings we wrote.
FLOW_FAILURE_MESSAGE = "Flow job failed"
_SAFE_MESSAGES = frozenset({TEST_CRASH_MESSAGE, FLOW_FAILURE_MESSAGE})


def report_flow_failure(flow: str, error_code: str, stage: str = "", engine: str = "") -> bool:
    """Send a privacy-safe "job failed" event: fixed message plus short tags.

    No user text leaves the machine: only the flow name, the error code, the
    last progress stage, and the engine, each trimmed to a short token.
    """
    if not _CRASH_REPORTING_INITIALIZED:
        return False
    try:
        import sentry_sdk

        def _tag(value: Any) -> str:
            text = re.sub(r"[^A-Za-z0-9_.:\- ]", "", str(value or ""))[:60].strip()
            return text or "unknown"

        with sentry_sdk.new_scope() as scope:
            scope.set_tag("flow", _tag(flow))
            scope.set_tag("error_code", _tag(error_code))
            scope.set_tag("stage", _tag(stage))
            scope.set_tag("engine", _tag(engine))
            sentry_sdk.capture_message(FLOW_FAILURE_MESSAGE, level="error")
        return True
    except Exception:
        return False


def _safe_message(value: Any) -> str:
    return value if isinstance(value, str) and value in _SAFE_MESSAGES else REDACTED


def _strip_frames(stacktrace: Any) -> None:
    """Drop local variables from frames and scrub usernames from file paths."""
    if not isinstance(stacktrace, dict):
        return
    for frame in stacktrace.get("frames", []) or []:
        if not isinstance(frame, dict):
            continue
        frame.pop("vars", None)
        for key in ("filename", "abs_path"):
            if key in frame:
                frame[key] = _scrub_string(str(frame[key]))


def before_send_scrubber(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Privacy scrubber hook invoked prior to sending any event to Sentry.

    Allow-list approach: anything that could carry user text (dictation,
    documents, clipboard, prompts) is dropped rather than pattern-scrubbed.
    What remains is exception *types*, code locations, and runtime context.
    """
    try:
        # Free-form containers that can hold user text: drop entirely.
        for key in ("breadcrumbs", "extra", "request", "server_name", "spans", "fingerprint"):
            event.pop(key, None)
        if "user" in event:
            event["user"] = {"id": "[ANONYMOUS]"}

        if "contexts" in event and isinstance(event["contexts"], dict):
            event["contexts"] = _scrub_object(event["contexts"])
        if "tags" in event and isinstance(event["tags"], dict):
            event["tags"] = _scrub_object(event["tags"])

        # Messages (capture_message / logging events): fixed allow-list only.
        if "message" in event:
            event["message"] = _safe_message(event["message"])
        if isinstance(event.get("logentry"), dict):
            entry = event["logentry"]
            safe = _safe_message(entry.get("formatted") or entry.get("message"))
            event["logentry"] = {"message": safe, "formatted": safe}

        # Exceptions: keep the type and stack locations, never the message or locals.
        if isinstance(event.get("exception"), dict):
            for exc in event["exception"].get("values", []) or []:
                if isinstance(exc, dict):
                    if "value" in exc:
                        exc["value"] = REDACTED
                    _strip_frames(exc.get("stacktrace"))
        if isinstance(event.get("threads"), dict):
            for thread in event["threads"].get("values", []) or []:
                if isinstance(thread, dict):
                    _strip_frames(thread.get("stacktrace"))

        return event
    except Exception as exc:
        # Never send an event we could not scrub.
        log.warning("Exception during crash report scrubbing; event dropped: %s", type(exc).__name__)
        return None


def _drop_breadcrumb(crumb: dict[str, Any], hint: dict[str, Any]) -> None:
    """Breadcrumbs (log lines, HTTP calls) can carry user text: never record them."""
    return None


def is_crash_reporting_enabled() -> bool:
    """True unless the user has explicitly turned crash reports off.

    A missing setting means the user never touched the control, so reporting
    stays on. Stored False is an opt-out and stays off.
    """
    value = storage.get_setting("anonymous_crash_reports", None)
    if value is None:
        return True
    return bool(value)


def init_crash_reporting(force: bool = False) -> bool:
    """Initialize Sentry crash reporting when enabled or force=True.

    An explicit opt-out skips initialization entirely.
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

    if is_ci_environment():
        environment = "ci"
    else:
        try:
            from voice_flow import runtime_env
            environment = "production" if runtime_env.is_installed() else "development"
        except Exception:
            environment = "production"

    # A DSN of None gives a disabled, no-op client: nothing is ever transmitted.
    dsn = None if is_sending_suppressed() else SENTRY_DSN

    release = f"ai-productivity-flow@{VERSION}"

    try:
        integrations = []
        try:
            from sentry_sdk.integrations.logging import LoggingIntegration

            # App logs can include dictated text: no log breadcrumbs, no log events.
            integrations.append(LoggingIntegration(level=None, event_level=None))
        except Exception:
            pass
        sentry_sdk.init(
            dsn=dsn,
            release=release,
            environment=environment,
            send_default_pii=False,
            include_local_variables=False,
            max_request_body_size="never",
            server_name="",
            traces_sample_rate=0.0,
            profiles_sample_rate=0.0,
            max_breadcrumbs=0,
            before_breadcrumb=_drop_breadcrumb,
            attach_stacktrace=True,
            integrations=integrations,
            # Sentry's auto-enabling integrations import every supported
            # library that is installed (openai, huggingface_hub, httpx,
            # anthropic, ...) just to hook it. In this app that pulled in about
            # 970 extra modules in every process (launcher, engine) before the
            # first window: 1.5-3 s on a fast machine, far more on a cold
            # low-end PC while Defender scans each new file. Crash reports
            # only need the default integrations (excepthook, threading,
            # logging, dedupe), which stay on.
            auto_enabling_integrations=False,
            before_send=before_send_scrubber,
        )
        _CRASH_REPORTING_INITIALIZED = True
        if dsn is None:
            log.info("Crash reporting initialized in no-send mode (%s, release=%s).", environment, release)
        else:
            log.info("Anonymous crash reporting initialized (%s, release=%s).", environment, release)
        return True
    except Exception as exc:
        log.warning("Could not initialize Sentry crash reporting: %s", exc)
        return False


def shutdown_crash_reporting() -> bool:
    """Stop crash reporting immediately (user opted out): close the Sentry client."""
    global _CRASH_REPORTING_INITIALIZED
    _CRASH_REPORTING_INITIALIZED = False
    try:
        import sentry_sdk
    except ImportError:
        return False
    try:
        client = sentry_sdk.get_client()
        if client.is_active():
            client.close(timeout=2.0)
        try:
            sentry_sdk.get_global_scope().set_client(None)
        except Exception:
            pass
        log.info("Crash reporting disabled.")
        return True
    except Exception as exc:
        log.warning("Could not shut down crash reporting: %s", type(exc).__name__)
        return False


def capture_test_crash_report() -> bool:
    """Send a test crash report to Sentry to verify connectivity and configuration."""
    try:
        import sentry_sdk
        if not _CRASH_REPORTING_INITIALIZED:
            init_crash_reporting(force=True)
        sentry_sdk.capture_message(TEST_CRASH_MESSAGE)
        sentry_sdk.flush(timeout=5.0)
        return True
    except Exception as exc:
        log.warning("Failed to send test crash report: %s", exc)
        return False

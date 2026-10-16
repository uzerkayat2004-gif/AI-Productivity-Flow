"""Unit and integration tests for privacy-first Sentry crash reporting."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from voice_flow._version import VERSION
from voice_flow.crash_reporting import (
    NO_SEND_ENV_VAR,
    SENTRY_DSN,
    before_send_scrubber,
    capture_test_crash_report,
    init_crash_reporting,
    is_ci_environment,
    is_crash_reporting_enabled,
    is_sending_suppressed,
)
from voice_flow.storage import storage

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = str(REPO_ROOT / "src")


def test_crash_reporting_default_disabled():
    """Crash reporting must be completely disabled by default with zero network overhead."""
    storage.save_setting("anonymous_crash_reports", False)
    assert not is_crash_reporting_enabled()

    with patch("sentry_sdk.init") as mock_init:
        initialized = init_crash_reporting(force=False)
        assert initialized is False
        mock_init.assert_not_called()


def test_crash_reporting_init_when_enabled(monkeypatch):
    """Enabling the setting allows initialization with strict privacy configuration."""
    # Simulate a real user machine: not CI, sending not suppressed.
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv(NO_SEND_ENV_VAR, raising=False)
    storage.save_setting("anonymous_crash_reports", True)
    assert is_crash_reporting_enabled() is True

    try:
        with patch("sentry_sdk.init") as mock_init:
            initialized = init_crash_reporting()
            assert initialized is True
            mock_init.assert_called_once()
            _, kwargs = mock_init.call_args
            assert kwargs["dsn"] == SENTRY_DSN
            assert kwargs["release"] == f"ai-productivity-flow@{VERSION}"
            assert kwargs["send_default_pii"] is False
            assert kwargs["traces_sample_rate"] == 0.0
            assert kwargs["profiles_sample_rate"] == 0.0
            assert kwargs["max_breadcrumbs"] == 0
            assert kwargs["include_local_variables"] is False
            assert kwargs["attach_stacktrace"] is True
            assert kwargs["before_send"] == before_send_scrubber
    finally:
        storage.save_setting("anonymous_crash_reports", False)


def test_before_send_scrubber_redaction():
    """Privacy scrubber strictly scrubs personal paths, API tokens, and user voice/transcript keywords."""
    simulated_event: dict[str, Any] = {
        "message": "Error occurred at /Users/alice/projects/test.py while processing user dictation",
        "logentry": {
            "message": "C:\\Users\\JohnDoe\\AppData\\Local\\VoiceFlow: failed to parse audio recording",
            "formatted": "Unhandled transcript exception with api key sk-12345678901234567890",
        },
        "request": {
            "url": "http://127.0.0.1:8991/api/test",
            "data": {"raw_audio": "base64data", "transcript": "secret meeting notes"},
            "query_string": "auth=secret_token",
            "cookies": "session=xyz",
            "headers": {
                "Authorization": "Bearer sensitive_token",
                "User-Agent": "VoiceFlow/1.0.0",
                "X-Api-Key": "gsk_abcdef1234567890",
            },
        },
        "contexts": {
            "os": {"name": "Windows"},
            "env": {
                "OPENAI_API_KEY": "sk-12345678901234567890",
                "ANTHROPIC_API_KEY": "sk-ant-12345678901234567890",
                "GROQ_API_KEY": "gsk_12345678901234567890",
                "GEMINI_API_KEY": "AIzaSy123456789012345678901234567890",
                "DEEPGRAM_API_KEY": "dg_12345678901234567890",
                "SENTRY_DSN": "https://secret@sentry.io/1",
                "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "USER": "JohnDoe",
            },
        },
        "breadcrumbs": {
            "values": [
                {
                    "message": "Loaded user audio file at C:\\Users\\JohnDoe\\Music\\test.wav",
                    "category": "recording",
                    "data": {"dictation_text": "Top secret meeting transcript"},
                }
            ]
        },
        "exception": {
            "values": [
                {
                    "type": "RuntimeError",
                    "value": "Corrupted audio buffer in /Users/alice/dictation.wav",
                    "stacktrace": {
                        "frames": [
                            {
                                "filename": "/Users/alice/projects/voice_flow/main.py",
                                "abs_path": "C:\\Users\\JohnDoe\\voice_flow\\main.py",
                                "vars": {"transcribed_transcript": "hello world"},
                            }
                        ]
                    },
                }
            ]
        },
    }

    scrubbed = before_send_scrubber(simulated_event, {})
    assert scrubbed is not None

    # 1. Free-text messages never leave the machine (only fixed allow-listed strings).
    assert scrubbed["message"] == "[redacted]"
    assert scrubbed["logentry"] == {"message": "[redacted]", "formatted": "[redacted]"}

    # 2. Request, breadcrumbs and extra are dropped entirely.
    assert "request" not in scrubbed
    assert "breadcrumbs" not in scrubbed
    assert "extra" not in scrubbed

    # 3. Sensitive environment tokens must be redacted
    env = scrubbed["contexts"]["env"]
    assert env["OPENAI_API_KEY"] == "[REDACTED]"
    assert env["ANTHROPIC_API_KEY"] == "[REDACTED]"
    assert env["GROQ_API_KEY"] == "[REDACTED]"
    assert env["GEMINI_API_KEY"] == "[REDACTED]"
    assert env["DEEPGRAM_API_KEY"] == "[REDACTED]"
    assert env["SENTRY_DSN"] == "[REDACTED]"
    assert env["AWS_SECRET_ACCESS_KEY"] == "[REDACTED]"

    # 4. Exceptions keep only their type; frames lose locals and usernames.
    exc = scrubbed["exception"]["values"][0]
    assert exc["type"] == "RuntimeError"
    assert exc["value"] == "[redacted]"
    frame = exc["stacktrace"]["frames"][0]
    assert "vars" not in frame
    assert "alice" not in frame["filename"]
    assert "JohnDoe" not in frame["abs_path"]


def test_test_crash_message_is_allow_listed():
    from voice_flow.crash_reporting import TEST_CRASH_MESSAGE

    event = {"message": TEST_CRASH_MESSAGE, "logentry": {"message": TEST_CRASH_MESSAGE}}
    scrubbed = before_send_scrubber(event, {})
    assert scrubbed["message"] == TEST_CRASH_MESSAGE
    assert scrubbed["logentry"]["formatted"] == TEST_CRASH_MESSAGE


def test_scrubber_failure_drops_event():
    class Boom(dict):
        def pop(self, *a, **k):
            raise RuntimeError("boom")

    assert before_send_scrubber(Boom(message="x"), {}) is None


def _get_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = SRC_DIR + os.pathsep + env["PYTHONPATH"]
    else:
        env["PYTHONPATH"] = SRC_DIR
    return env


def test_cli_flag_disabled():
    """Running --test-crash-reporting when disabled outputs opt-in message and exits 0."""
    storage.save_setting("anonymous_crash_reports", False)
    cmd = [sys.executable, "-m", "voice_flow.main", "--test-crash-reporting"]
    proc = subprocess.run(cmd, env=_get_subprocess_env(), capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0
    assert "Crash reporting is currently disabled (opt-in only). Enable it in Settings to test." in proc.stdout


def test_cli_flag_enabled():
    """Running --test-crash-reporting when enabled sends test message and exits 0."""
    storage.save_setting("anonymous_crash_reports", True)
    try:
        cmd = [sys.executable, "-m", "voice_flow.main", "--test-crash-reporting"]
        proc = subprocess.run(cmd, env=_get_subprocess_env(), capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0
        assert f"Test crash report from AI Productivity Flow v{VERSION}" in proc.stdout
        # Regression: the test suite used to send a real event to Sentry on every run.
        assert "was not sent" in proc.stdout
        assert "sent successfully" not in proc.stdout
    finally:
        storage.save_setting("anonymous_crash_reports", False)


def test_test_suite_never_sends_crash_reports():
    """conftest must put every test (and its subprocesses) in no-send mode."""
    assert os.environ.get(NO_SEND_ENV_VAR) == "1"
    assert is_sending_suppressed() is True


@pytest.mark.parametrize("value", ["true", "1", "TRUE", "yes"])
def test_ci_env_disables_sending_and_tags_ci(monkeypatch, value):
    """Under CI the SDK gets no DSN (nothing is sent) and environment is 'ci'."""
    monkeypatch.delenv(NO_SEND_ENV_VAR, raising=False)
    monkeypatch.setenv("CI", value)
    assert is_ci_environment() is True
    assert is_sending_suppressed() is True
    with patch("sentry_sdk.init") as mock_init:
        assert init_crash_reporting(force=True) is True
        _, kwargs = mock_init.call_args
        assert kwargs["dsn"] is None
        assert kwargs["environment"] == "ci"


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_falsey_ci_env_keeps_sending(monkeypatch, value):
    """A falsey CI value is a normal user machine: real DSN, non-ci environment."""
    monkeypatch.delenv(NO_SEND_ENV_VAR, raising=False)
    monkeypatch.setenv("CI", value)
    assert is_sending_suppressed() is False
    with patch("sentry_sdk.init") as mock_init:
        assert init_crash_reporting(force=True) is True
        _, kwargs = mock_init.call_args
        assert kwargs["dsn"] == SENTRY_DSN
        assert kwargs["environment"] in ("production", "development")


def test_no_send_env_var_disables_sending_outside_ci(monkeypatch):
    """The explicit opt-out sends nothing but keeps the normal environment tag."""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv(NO_SEND_ENV_VAR, "1")
    with patch("sentry_sdk.init") as mock_init:
        assert init_crash_reporting(force=True) is True
        _, kwargs = mock_init.call_args
        assert kwargs["dsn"] is None
        assert kwargs["environment"] in ("production", "development")

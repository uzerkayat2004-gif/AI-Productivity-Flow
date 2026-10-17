"""Test that strict local-only mode blocks all outbound network operations.

Verifies Risk R-08: 'Local-only never uses the cloud'.
Tests all command types (cleanup, email, message, prompt, notes, summary, rewrite)
under local-only / deterministic settings, ensuring zero network calls occur.
"""

from __future__ import annotations

import os
import socket
import sys
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from voice_flow.effective_style import EffectiveStyle
from voice_flow.polisher import TextPolisher
from voice_flow.voice_commands import detect_voice_command


class NetworkAttemptForbiddenError(RuntimeError):
    """Raised whenever a network connection is attempted in local-only mode."""


@pytest.fixture
def network_blocker(monkeypatch):
    """Deterministic barrier that intercepts and prevents any external socket connection."""
    orig_connect = socket.socket.connect
    orig_urlopen = urllib.request.urlopen

    def forbidden_connect(self, address):
        # Allow loopback/unix domain connections if needed for local IPC, but block external
        host, port = address[0], address[1]
        if host in ("127.0.0.1", "localhost", "::1"):
            # Local IPC loopback allowed for local server
            return orig_connect(self, address)
        raise NetworkAttemptForbiddenError(f"Outbound network connection forbidden: {address}")

    def forbidden_urlopen(*args, **kwargs):
        raise NetworkAttemptForbiddenError(f"HTTP request forbidden in local-only mode: {args}")

    monkeypatch.setattr(socket.socket, "connect", forbidden_connect)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden_urlopen)
    return True


@pytest.mark.parametrize(
    "command_text,expected_format,task_type",
    [
        ("clean this up: um so basically we need to test the offline mode today", "prose", "cleanup"),
        ("make this an email to the team regarding project timeline updates", "email", "rewrite"),
        ("send a message saying I will be five minutes late to the sync", "message", "rewrite"),
        ("create an AI prompt for generating a landing page headline", "prose", "prompt"),
        ("convert this transcript into bullet points for my notes", "bullets", "rewrite"),
        ("summarize the key takeaways from the discussion", "prose", "summary"),
        ("rewrite this to be more professional and clear", "prose", "rewrite"),
    ],
)
def test_local_only_mode_executes_without_network_calls(
    network_blocker, command_text, expected_format, task_type
):
    """Ensure polisher fulfills all command categories strictly locally when configured for local execution."""
    polisher = TextPolisher()
    outcomes = []

    def mock_settings(key, default=None):
        if key == "voice_flow_polish_model":
            return "local/deterministic"
        if key == "polishing_enabled":
            return True
        if key == "voice_flow_privacy_mode":
            return True
        return default

    cmd_res = detect_voice_command(f"Hey Voice Flow, {command_text}")
    effective = EffectiveStyle(
        instruction=f"Fulfill {task_type} intent",
        style_id="local_rule",
        category="general",
        format=expected_format,
        task=task_type,
        requires_ai=False,
        preserve_wording=False,
        label="Local / Test",
    )

    with patch("voice_flow.polisher.storage.get_setting", side_effect=mock_settings):
        # Even if API keys were configured, local-only setting must prevent any cloud attempt
        with patch("voice_flow.polisher.storage.get_all_api_keys", return_value={"gemini": "dummy_key"}):
            result = polisher.polish(
                command_text,
                effective.instruction,
                model_ref="local/deterministic",
                task=task_type,
                command_format=expected_format,
                outcome_callback=outcomes.append,
            )

    assert result is not None
    assert len(result) > 0
    # Offline cleanup. model_not_downloaded means S1 is not on disk yet.
    assert outcomes[0] in {"local", "model_not_downloaded", "local_rewrite", "local_format"}


def test_api_pool_blocked_if_accidentally_invoked_under_network_barrier(network_blocker):
    """Assert that the network blocker correctly catches and raises on forbidden outbound HTTP calls."""
    with pytest.raises(NetworkAttemptForbiddenError):
        # Direct attempt to call cloud endpoint must trip the network blocker
        urllib.request.urlopen("https://api.groq.com/openai/v1/chat/completions")

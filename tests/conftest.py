"""Global pytest configuration and automatic safety mocks."""

from __future__ import annotations

import os
import webbrowser
import pytest


@pytest.fixture(autouse=True)
def prevent_os_browser_launches(monkeypatch):
    """Safeguard: Prevent tests from opening real OS browser windows during pytest runs."""
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: True)
    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", lambda *a, **k: True)
    # NotebookLM sign-in opens real Chrome windows — hard-off during tests.
    monkeypatch.setenv("VOICE_FLOW_LOGIN_DISABLE", "1")
    # Crash reporting: never send real events to Sentry from the test suite.
    # Inherited by subprocesses that copy os.environ (e.g. --test-crash-reporting).
    monkeypatch.setenv("VOICE_FLOW_CRASH_REPORTS_NO_SEND", "1")

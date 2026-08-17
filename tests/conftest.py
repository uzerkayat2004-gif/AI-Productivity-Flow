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

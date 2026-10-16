"""Global pytest configuration and automatic safety mocks."""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
import webbrowser
from pathlib import Path

import sys

import pytest

# Test helpers such as native_fixture_client live beside the tests.
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

# ---------------------------------------------------------------------------
# Test data isolation: never read or write the user's real ~/.voice_flow.
#
# This runs at conftest import time, before any test module imports voice_flow,
# so module-level paths (storage.DB_PATH, config.DB_PATH, the storage singleton)
# all resolve inside a throwaway folder. It always wins over a VOICE_FLOW_DATA_DIR
# the developer may have exported, and subprocesses inherit it via os.environ.
# The folder is named ".voice_flow" so path-suffix assertions keep working.
# ---------------------------------------------------------------------------
REAL_USER_DATA_DIR = Path.home() / ".voice_flow"
_TEST_DATA_ROOT = Path(tempfile.mkdtemp(prefix="voice-flow-tests-"))
TEST_DATA_DIR = _TEST_DATA_ROOT / ".voice_flow"
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["VOICE_FLOW_DATA_DIR"] = str(TEST_DATA_DIR)
atexit.register(shutil.rmtree, _TEST_DATA_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolate_voice_flow_data_dir(monkeypatch):
    """Re-pin the temp data dir per test so a leaked env change can't reach ~/.voice_flow."""
    monkeypatch.setenv("VOICE_FLOW_DATA_DIR", str(TEST_DATA_DIR))
    yield TEST_DATA_DIR


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

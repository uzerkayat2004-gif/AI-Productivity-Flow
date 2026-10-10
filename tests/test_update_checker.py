"""Tests for safe update checker."""

import pytest
from voice_flow.update_checker import parse_semver, is_version_newer, check_for_updates


def test_parse_semver():
    assert parse_semver("1.0.0") == (1, 0, 0)
    assert parse_semver("v1.0.1") == (1, 0, 1)
    assert parse_semver("v2.1.0-beta") == (2, 1, 0)
    assert parse_semver("invalid") == (0, 0, 0)


def test_is_version_newer():
    assert is_version_newer("1.0.0", "1.0.1") is True
    assert is_version_newer("1.0.0", "1.1.0") is True
    assert is_version_newer("1.0.0", "2.0.0") is True
    assert is_version_newer("1.0.0", "1.0.0") is False
    assert is_version_newer("1.0.1", "1.0.0") is False
    assert is_version_newer("1.0.0", "v1.0.1") is True


def test_check_for_updates_offline(monkeypatch):
    """When network fails, check_for_updates must not raise and report error cleanly."""
    import urllib.request

    def mock_urlopen(*args, **kwargs):
        raise urllib.error.URLError("Network unreachable")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    res = check_for_updates(force=True, timeout=0.1)
    assert res["checked"] is False
    assert res["update_available"] is False
    assert "Network unreachable" in res["error"]

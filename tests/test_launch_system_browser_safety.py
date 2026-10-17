"""launch_system_browser only opens web URLs and never routes them through cmd.exe."""

from __future__ import annotations

import webbrowser

import pytest

from voice_flow import video_flow_oauth


@pytest.mark.parametrize("url", ["file:///C:/Windows/System32/calc.exe", "C:\\Windows\\notepad.exe", "javascript:alert(1)", "ms-settings:"])
def test_non_web_urls_are_refused(monkeypatch, url):
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: opened.append(a) or True)
    assert video_flow_oauth.launch_system_browser(url) is False
    assert opened == []


def test_windows_fallback_never_uses_cmd(monkeypatch):
    calls = []
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: False)
    monkeypatch.setattr(video_flow_oauth.os, "name", "nt")
    monkeypatch.setattr(video_flow_oauth.os, "startfile", lambda *_a: (_ for _ in ()).throw(OSError("no")), raising=False)
    import subprocess

    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: calls.append(argv))
    url = "https://accounts.google.com/o/oauth2/auth?client_id=a&redirect_uri=b&state=c"
    assert video_flow_oauth.launch_system_browser(url) is True
    assert calls and calls[0][0].lower() != "cmd.exe"
    assert calls[0][-1] == url

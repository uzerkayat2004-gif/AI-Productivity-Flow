"""The audio summary player must not render history text as HTML.

History titles and snippets are the user's selected source text (a web page,
a PDF, an email), so they can carry markup. The player page is served from the
local API origin, so script running there could call the local API.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "src" / "voice_flow" / "gui"
PAYLOAD_TITLE = "x'); alert(1); ('\"><img src=x onerror=alert(2)>"
PAYLOAD_SNIPPET = "<img src=x onerror=alert(3)><script>alert(4)</script>"


PAGES = ["modern", "classic", "embedded"]


def _source(name: str) -> str:
    if name == "modern":
        return (GUI / "audio-summary-player.html").read_text(encoding="utf-8")
    if name == "classic":
        return (GUI / "audio-summary-player.classic.html").read_text(encoding="utf-8")
    from voice_flow import audio_summary_player

    return audio_summary_player.CLASSIC_PLAYER_HTML


def _extract(src: str, start: str, end: str) -> str:
    i = src.index(start)
    j = src.index(end, i)
    return src[i : j + len(end)]


@pytest.mark.parametrize("name", PAGES)
def test_history_template_has_no_raw_interpolation(name: str) -> None:
    src = _source(name)
    body = _extract(src, "historyListEl.innerHTML = historyRecords.map(item => {", "}).join('');")
    assert "afHistEscape(item.text_snippet" in body, name
    assert ".replace(/\"/g, '&quot;')" not in body, name
    # No handler argument is a hand-quoted '${...}' string any more.
    assert not re.search(r"\('\$\{", body), name


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("name", PAGES)
def test_history_template_escapes_markup_when_rendered(name: str) -> None:
    src = _source(name)
    helpers = _extract(src, "function afHistEscape(", "function safeMediaFilename(")
    helpers = helpers[: -len("function safeMediaFilename(")]
    body = _extract(src, "historyRecords.map(item => {", "}).join('');")
    record = {
        "id": "abc'1",
        "title": PAYLOAD_TITLE,
        "text_snippet": PAYLOAD_SNIPPET,
        "depth": "balanced",
        "status": "ready",
        "audio_path": "x.mp3",
        "created_at": "2026-10-18T01:00:00Z",
        "duration_sec": 12,
    }
    script = f"""
const formatDepth = d => 'BALANCED';
const fmt = s => String(s);
const apiBase = '';
function safeMediaFilename(t) {{ return 'Audio.mp3'; }}
{helpers}
const historyRecords = [{json.dumps(record)}];
const html = {body};
process.stdout.write(html);
"""
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    html = out.stdout
    assert "<img" not in html and "<script" not in html, name
    # Every inline handler argument decodes back to a plain JSON string literal.
    for handler in re.findall(r'onclick="([^"]*)"', html):
        decoded = handler.replace("&quot;", '"').replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
        call = re.fullmatch(r"\s*(\w+)\((.*)\)\s*", decoded)
        assert call, handler
        args = call.group(2)
        if args.endswith(", this"):
            args = args[: -len(", this")]
        values = json.loads("[" + args + "]")
        assert all(isinstance(v, str) for v in values), handler
        if "Play" in html and call.group(1).startswith("play"):
            assert PAYLOAD_TITLE in values

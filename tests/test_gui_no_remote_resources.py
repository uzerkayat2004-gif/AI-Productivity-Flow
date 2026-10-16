"""B6: the desktop UI loads no remote resources (fonts, CDNs, images).

Plus Jakarta Sans is self-hosted under gui/assets/fonts; links the user clicks
(<a href="https://...">) are fine, automatic loads are not.
"""

from __future__ import annotations

import re
from pathlib import Path

GUI = Path(__file__).resolve().parents[1] / "src" / "voice_flow" / "gui"

_AUTO_LOAD = [
    re.compile(r"<link[^>]+href=[\"']https?://", re.I),
    re.compile(r"<(?:script|img|iframe|source|video|audio)[^>]+src=[\"']https?://", re.I),
    re.compile(r"url\(\s*[\"']?https?://", re.I),
    re.compile(r"@import\s+(?:url\()?[\"']?https?://", re.I),
    re.compile(r"fonts\.(?:googleapis|gstatic)\.com", re.I),
]


def test_no_remote_resource_loads_in_gui():
    offenders = []
    for path in list(GUI.glob("*.html")) + list(GUI.glob("*.css")) + list(GUI.glob("*.js")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in _AUTO_LOAD:
            for match in pattern.finditer(text):
                offenders.append(f"{path.name}: {match.group(0)[:80]}")
    assert not offenders, "\n".join(offenders)


def test_plus_jakarta_sans_is_self_hosted():
    css = (GUI / "fonts.css").read_text(encoding="utf-8")
    urls = re.findall(r"url\('([^']+)'\)", css)
    assert len(urls) == 4
    for rel in urls:
        font = GUI / rel
        assert font.is_file() and font.read_bytes()[:4] == b"wOF2", rel
    assert (GUI / "assets" / "fonts" / "OFL.txt").is_file()
    assert "font-family: 'Plus Jakarta Sans'" in css
    html = (GUI / "index.html").read_text(encoding="utf-8")
    assert 'href="fonts.css' in html

"""M-UI-3: Audio/Video history buttons must work when a title contains ' or ".

afEscape() turns ' into &#039;, which the browser decodes back before the
inline handler runs, so onclick="fn('Today's')" was a SyntaxError. Arguments
are now JSON string literals, HTML-escaped (afJsArg / vfHandlerArg).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

GUI = Path(__file__).resolve().parents[1] / "src" / "voice_flow" / "gui"
APP_JS = (GUI / "app.js").read_text(encoding="utf-8")
VF_JS = (GUI / "video-flow.js").read_text(encoding="utf-8")


def _fn(src: str, name: str) -> str:
    start = src.index(f"function {name}(")
    return src[start: src.index("\n}\n", start) + 3]


def test_no_quoted_html_escaped_handler_args() -> None:
    bad = re.findall(r"onclick=\"[^\"]*'\$\{(?:afEscape|vfEscape)\(", APP_JS + VF_JS)
    assert not bad, bad
    row = APP_JS[APP_JS.index('let actionButtons = "";\n    if (isReady && s.has_audio !== false)'):]
    row = row[: row.index("</div>`;")]
    assert "playAudioSummary(${afJsArg(s.id)}, ${afJsArg(title)}" in row
    assert "downloadAudioSummary(${afJsArg(s.id)}, this, ${afJsArg(title)})" in row


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("helpers,builder", [
    (("afEscape", "afJsArg"), "afJsArg"),
    (("vfEscape", "vfHandlerArg"), "vfHandlerArg"),
])
def test_handler_survives_html_decoding(helpers, builder) -> None:
    src = APP_JS if builder == "afJsArg" else VF_JS
    code = "\n".join(_fn(src, h) for h in helpers)
    titles = ["Today's notes", 'He said "hi"', "a & b <c> \\ back", "it's </script>"]
    script = code + r"""
const decode = s => s.replace(/&quot;/g, '"').replace(/&#039;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const titles = JSON.parse(process.argv[1]);
const out = titles.map(t => {
  const attr = `play(${BUILDER(t)}, ${BUILDER("id-1")})`;
  let got = null;
  new Function("play", decode(attr))((a, b) => { got = [a, b]; });
  return got;
});
console.log(JSON.stringify(out));
""".replace("BUILDER", builder)
    proc = subprocess.run(["node", "-e", script, json.dumps(titles)], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == [[t, "id-1"] for t in titles]

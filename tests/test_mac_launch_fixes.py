"""Regression checks for the macOS launch fixes found by the rc3 walkthrough."""
from __future__ import annotations

import re
from pathlib import Path

GUI = Path(__file__).resolve().parents[1] / "src" / "voice_flow" / "gui"


def _read(name: str) -> str:
    return (GUI / name).read_text(encoding="utf-8")


def test_video_flow_selected_style_is_declared_before_use():
    source = _read("video-flow.js")
    declaration = re.search(r'^let vfSelectedStyle\s*=\s*"auto";', source, re.MULTILINE)
    assert declaration, "vfSelectedStyle must be declared at top level (Create threw ReferenceError)"
    first_use = source.index("vfSelectedStyle || ")
    assert declaration.start() < first_use

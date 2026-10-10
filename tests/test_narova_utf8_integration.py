from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

NAROVA_PY = Path(__file__).resolve().parents[1] / "third_party" / "narova" / "tool" / "py"
if not NAROVA_PY.is_dir():
    pytest.skip("vendored narova_tts not present (third_party/narova)", allow_module_level=True)
sys.path.insert(0, str(NAROVA_PY))

from narova_tts import pipeline


def test_pipeline_reads_provider_authored_unicode_json_as_utf8(tmp_path: Path, monkeypatch) -> None:
    narration = tmp_path / "narration.json"
    config = tmp_path / "config.json"
    out = tmp_path / "out"
    narration.write_text(
        json.dumps([{"id": "scene", "n": 1, "vo": [{"who": "narrator", "text": "End‑to‑end → action"}]}], ensure_ascii=False),
        encoding="utf-8",
    )
    config.write_text(
        json.dumps({"voices": {"narrator": {"backend": "piper"}}, "title": "تعلیم"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(pipeline, "_synthesize", lambda *args, **kwargs: {"scene": {"dur": 1.0, "turns": [0.0], "words": []}})
    monkeypatch.setattr(pipeline, "_verify_total", lambda *args, **kwargs: 1.0)
    monkeypatch.setattr(pipeline, "mix_audio", lambda *args, **kwargs: None)

    result = pipeline.run(narration, config, out)

    assert result["totalDuration"] == 1.0
    assert json.loads((out / "timings.json").read_text(encoding="utf-8"))["scene"]["dur"] == 1.0

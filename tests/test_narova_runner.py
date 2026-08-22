from __future__ import annotations

from pathlib import Path

from voice_flow.video_flow_engine.bridge import build_narova_production
from voice_flow.video_flow_engine.narova_runner import NarovaRunner


def test_bridge_output_passes_vendored_narova_check(tmp_path: Path) -> None:
    production = build_narova_production(
        {
            "topic": "Earth orbit",
            "sections": [
                {
                    "id": "orbit",
                    "title": "Earth follows an orbit",
                    "lecture_lines": ["Gravity bends Earth's path around the Sun."],
                    "animations": ["Show a curved path around the Sun."],
                }
            ],
        }
    )
    runner = NarovaRunner()

    config_path = runner.check(production, tmp_path, job_id="narova-check")

    assert config_path.name == "reel.config.json"
    assert config_path.is_file()
    assert (tmp_path / "logs" / "narova.log").is_file()

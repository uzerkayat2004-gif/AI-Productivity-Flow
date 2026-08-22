from __future__ import annotations

from pathlib import Path

import pytest

from voice_flow.video_flow_engine.code2video_runner import Code2VideoRunner
from voice_flow.video_flow_engine.sandbox import EngineError


def test_unknown_model_reference_never_falls_back_to_paid_provider(tmp_path: Path) -> None:
    runner = Code2VideoRunner()
    with pytest.raises(EngineError) as exc_info:
        runner.plan(
            "Safe source",
            project_dir=tmp_path,
            allow_external_ai=True,
            model_ref="unknown-provider",
        )

    assert exc_info.value.code == "provider_error"
    assert "Unknown Code2Video model reference" in str(exc_info.value)

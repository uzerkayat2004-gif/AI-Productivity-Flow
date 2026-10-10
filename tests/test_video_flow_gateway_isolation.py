from __future__ import annotations

from pathlib import Path

import pytest

from voice_flow.video_flow_engine.code2video_runner import Code2VideoRunner
from voice_flow.video_flow_engine.sandbox import EngineError


import pytest

from voice_flow import runtime_env as _runtime_env

if not (_runtime_env.code2video_root() and (_runtime_env.code2video_root() / "prompts" / "stage1.py").is_file()):
    pytest.skip("vendored Code2Video prompts not present (third_party/code2video)", allow_module_level=True)


def test_nonlocal_injected_gateway_requires_isolated_interface(tmp_path: Path) -> None:
    calls: list[str] = []

    def gateway(prompt: str, **options: object) -> str:
        calls.append(prompt)
        return "{}"

    with pytest.raises(EngineError, match="request_isolated"):
        Code2VideoRunner(gateway=gateway).plan(
            "private source",
            project_dir=tmp_path,
            allow_external_ai=True,
        )
    assert calls == []


def test_local_gateway_exception_is_redacted(tmp_path: Path) -> None:
    class LocalGateway:
        is_local = True

        def __call__(self, prompt: str, **options: object) -> str:
            raise RuntimeError("secret endpoint diagnostic")

    with pytest.raises(EngineError) as exc_info:
        Code2VideoRunner(gateway=LocalGateway()).plan(
            "private source",
            project_dir=tmp_path,
            allow_external_ai=False,
        )

    assert exc_info.value.code == "provider_error"
    assert "secret endpoint diagnostic" not in str(exc_info.value)

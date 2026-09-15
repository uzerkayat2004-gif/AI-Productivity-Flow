"""Feature-gated Video Flow V2 integration and fallback tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from voice_flow.video_flow_engine import engine as engine_module
from voice_flow.video_flow_engine.engine import VideoFlowEngine
from voice_flow.video_flow_engine.sandbox import EngineError
from voice_flow.video_flow_engine.visual_director_v2 import VisualDirectorV2Error


STORYBOARD = {
    "topic": "Residual connections",
    "sections": [
        {
            "id": "residual-storyboard",
            "title": "Residual connection",
            "lecture_lines": ["The input follows a transform.", "A shortcut preserves the signal."],
            "animations": ["Show the transform and bypass merging."],
        }
    ],
}


class _Planner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def plan(self, source_text: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"source_text": source_text, **kwargs})
        return STORYBOARD


class _Renderer:
    def __init__(self, *, fail_hyperframes: bool = False) -> None:
        self.fail_hyperframes = fail_hyperframes
        self.productions: list[dict[str, Any]] = []

    def render(self, production: dict[str, Any], project_dir: Path, **_: Any) -> Path:
        self.productions.append(production)
        if self.fail_hyperframes and production.get("renderer") == "hyperframes":
            raise EngineError("render_failed", "browser unavailable")
        output = Path(project_dir) / "video.mp4"
        output.write_bytes(b"v2-mp4")
        return output


class _Gateway:
    is_local = False


class _Compiled:
    def __init__(self, production: dict[str, Any] | None = None, *, artifact_error: bool = False, unsafe_artifact: bool = False) -> None:
        self.production = production or _v2_production()
        self.design_tokens = object()
        self.scene_ir = object()
        self.artifact_error = artifact_error
        self.unsafe_artifact = unsafe_artifact

    def to_artifacts(self) -> dict[str, Any]:
        if self.artifact_error:
            raise OSError("disk unavailable")
        if self.unsafe_artifact:
            return {"../escape.json": {"unsafe": True}}
        return {
            "resolved-design.json": {"background": "#fff8f3"},
            "scene-ir/index.json": {"scenes": ["residual-block"]},
            "scene-ir/residual-block.json": {"scene_id": "residual-block"},
        }


class _ValidationReport:
    def to_dict(self) -> dict[str, Any]:
        return {"valid": True, "findings": [], "metrics": {"scene_count": 1}}


class _Signature:
    def to_dict(self) -> dict[str, Any]:
        return {
            "surface_mode": "technical", "palette_family": "signal-red",
            "background_family": "grid", "typography_family": "technical",
            "motion_profile": "technical", "camera_profile": "focus",
            "depth_profile": "layered", "scene_density": 4, "usage_3d": False,
        }


class _SignatureHarness:
    def __init__(self, recent: tuple[Any, ...] = ()) -> None:
        self.recent_value = recent
        self.paths: list[Path] = []
        self.recent_calls = 0
        self.append_calls: list[Any] = []
        self.append_error: Exception | None = None

    def store_class(self):
        harness = self

        class Store:
            def __init__(self, path: Path, *args: Any, **kwargs: Any) -> None:
                harness.paths.append(Path(path))

            def recent(self) -> tuple[Any, ...]:
                harness.recent_calls += 1
                return harness.recent_value

            def append(self, signature: Any) -> None:
                harness.append_calls.append(signature)
                if harness.append_error is not None:
                    raise harness.append_error

        return Store

def _v2_production() -> dict[str, Any]:
    return {
        "title": "V2",
        "size": "16:9",
        "renderer": "hyperframes",
        "voices": {"narrator": {"backend": "voiceflow", "speaker": "edge/en-US-AvaNeural", "label": "Narrator", "color": "#ff0000"}},
        "theme": {"mode": "light", "bg": "#fff8f3", "accent": "#ff0000", "css": "theme.css"},
        "safeLayout": True,
        "chrome": False,
        "captions": {"preset": "rise"},
        "timing": {"tempo": 1.12},
        "scenes": [{"id": "residual-block", "vo": [{"who": "narrator", "text": "Narration."}], "body": "<section/>"}],
        "_files": {"theme.css": "body{}"},
        "marker": "v2",
    }


def _v1_production(*_: Any, **__: Any) -> dict[str, Any]:
    production = _v2_production()
    production["marker"] = "v1-directed"
    return production


def _portable_production(*_: Any, **__: Any) -> dict[str, Any]:
    production = _v2_production()
    production["renderer"] = "no-browser"
    production["marker"] = "v1-portable"
    return production


def _run(
    tmp_path: Path,
    *,
    renderer: _Renderer,
    gateway: Any = None,
    process_manager: Any = None,
    **kwargs: Any,
) -> tuple[dict[str, Any], _Planner]:
    planner = _Planner()
    engine = VideoFlowEngine(
        planner=planner,
        renderer=renderer,
        model_gateway=gateway,
        process_manager=process_manager,
    )
    result = engine.run(
        "vf-v2-integration",
        projects_root=tmp_path,
        project_dir=tmp_path / "vf-v2-integration",
        source_text="Explain residual connections.",
        title="Residuals",
        mode="lesson",
        model_ref="openai/gpt-5.6-sol",
        allow_external_ai=True,
        visual_direction="hard black white and red",
        theme={"mode": "light", "accent": "#123456"},
        voice="edge/en-US-AvaNeural",
        **kwargs,
    )
    return result, planner


def _patch_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    from voice_flow.video_flow_engine import creative_director

    monkeypatch.setattr(creative_director, "direct", lambda *args, **kwargs: {"brief": {}, "scenes": []})
    monkeypatch.setattr(engine_module, "build_directed_production", _v1_production)
    monkeypatch.setattr(engine_module, "build_narova_production", _portable_production)


def _patch_v2(
    monkeypatch: pytest.MonkeyPatch,
    director: Any,
    compiler: Any,
    *,
    validator: Any = None,
    signature: Any = None,
    harness: _SignatureHarness | None = None,
) -> _SignatureHarness:
    from voice_flow.video_flow_engine import scene_compiler_v2, visual_director_v2, visual_signature, visual_validator

    harness = harness or _SignatureHarness()
    validator = validator or (lambda compiled: _ValidationReport())
    signature = signature or (lambda plan, compiled: _Signature())
    monkeypatch.setattr(visual_director_v2, "direct_visual_plan_v2", director)
    monkeypatch.setattr(scene_compiler_v2, "compile_visual_plan_v2", compiler)
    monkeypatch.setattr(visual_validator, "validate_compiled_visual_v2", validator)
    monkeypatch.setattr(visual_signature, "signature_from", signature)
    monkeypatch.setattr(visual_signature, "VisualSignatureStore", harness.store_class())
    monkeypatch.setattr(engine_module, "direct_visual_plan_v2", director, raising=False)
    monkeypatch.setattr(engine_module, "compile_visual_plan_v2", compiler, raising=False)
    monkeypatch.setattr(engine_module, "validate_compiled_visual_v2", validator, raising=False)
    monkeypatch.setattr(engine_module, "signature_from", signature, raising=False)
    monkeypatch.setattr(engine_module, "VisualSignatureStore", harness.store_class(), raising=False)
    return harness

def test_v2_is_off_by_default_and_does_not_call_director(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_v1(monkeypatch)
    _patch_v2(
        monkeypatch,
        lambda *args, **_: pytest.fail("V2 director must not run while the internal flag is off"),
        lambda *args, **kwargs: pytest.fail("V2 compiler must not run while the internal flag is off"),
    )
    renderer = _Renderer()

    result, _ = _run(tmp_path, renderer=renderer)

    assert result["state"] == "complete"
    assert renderer.productions[0]["marker"] == "v1-directed"


def test_valid_v2_uses_compiled_hyperframes_and_persists_fixed_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_v1(monkeypatch)
    received: dict[str, Any] = {}
    plan = object()
    compiled = _Compiled()

    def director(storyboard: dict[str, Any], gateway: Any, **kwargs: Any) -> object:
        received["storyboard"] = storyboard
        received["gateway"] = gateway
        received.update(kwargs)
        return plan

    def compiler(storyboard: dict[str, Any], actual_plan: object, **kwargs: Any) -> _Compiled:
        assert storyboard is STORYBOARD
        assert actual_plan is plan
        received["compiler_kwargs"] = kwargs
        return compiled

    _patch_v2(monkeypatch, director, compiler)
    renderer = _Renderer()
    gateway = _Gateway()

    result, _ = _run(tmp_path, renderer=renderer, gateway=gateway, visual_v2_enabled=True)

    project_dir = tmp_path / "vf-v2-integration"
    assert result["state"] == "complete"
    assert Path(result["video_path"]) == project_dir / "video.mp4"
    assert renderer.productions == [compiled.production]
    assert received["gateway"] is gateway
    assert received["model_ref"] == "openai/gpt-5.6-sol"
    assert received["allow_external_ai"] is True
    assert received["visual_direction"] == "hard black white and red"
    assert received["theme"] == {"mode": "light", "accent": "#123456"}
    assert received["job_id"] == "vf-v2-integration"
    assert received["process_manager"] is not None
    assert received["project_dir"] == project_dir
    assert (project_dir / "visual" / "resolved-design.json").is_file()
    assert (project_dir / "visual" / "scene-ir" / "index.json").is_file()
    assert (project_dir / "visual" / "scene-ir" / "residual-block.json").is_file()
    assert json.loads((project_dir / "visual" / "resolved-design.json").read_text(encoding="utf-8")) == {"background": "#fff8f3"}


@pytest.mark.parametrize("failure", ["director", "compiler", "artifact"], ids=["director", "compiler", "artifact"])
def test_non_cancellation_v2_failures_fall_back_to_v1_directed_hyperframes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    _patch_v1(monkeypatch)

    def director(*_args: Any, **_: Any) -> object:
        if failure == "director":
            raise VisualDirectorV2Error("v2_plan_invalid", "invalid V2 plan")
        return object()

    def compiler(*_: Any, **__: Any) -> _Compiled:
        if failure == "compiler":
            raise RuntimeError("compiler failed")
        return _Compiled(artifact_error=failure == "artifact")

    _patch_v2(monkeypatch, director, compiler)
    renderer = _Renderer()

    result, _ = _run(tmp_path, renderer=renderer, gateway=_Gateway(), visual_v2_enabled=True)

    assert result["state"] == "complete"
    assert [production["marker"] for production in renderer.productions] == ["v1-directed"]
    assert renderer.productions[0]["renderer"] == "hyperframes"


def test_cancellation_from_v2_is_terminal_and_never_falls_back_or_renders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_v1(monkeypatch)
    _patch_v2(
        monkeypatch,
        lambda *args, **_: (_ for _ in ()).throw(RuntimeError("cancelled: job was cancelled")),
        lambda *args, **kwargs: pytest.fail("compiler must not run after cancellation"),
    )
    renderer = _Renderer()

    result, _ = _run(tmp_path, renderer=renderer, gateway=_Gateway(), visual_v2_enabled=True)

    assert result["state"] == "cancelled"
    assert result["error_code"] == "cancelled"
    assert renderer.productions == []


def test_valid_v2_hyperframes_render_failure_uses_existing_portable_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_v1(monkeypatch)
    _patch_v2(monkeypatch, lambda *args, **_: object(), lambda *args, **kwargs: _Compiled())
    renderer = _Renderer(fail_hyperframes=True)

    result, _ = _run(tmp_path, renderer=renderer, gateway=_Gateway(), visual_v2_enabled=True)

    assert result["state"] == "complete"
    assert [production["marker"] for production in renderer.productions] == ["v2", "v1-portable"]
    assert [production["renderer"] for production in renderer.productions] == ["hyperframes", "no-browser"]


@pytest.mark.parametrize("flag", ["true", "TRUE", "1", "yes", "on"])
def test_truthy_environment_flag_enables_v2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag: str) -> None:
    _patch_v1(monkeypatch)
    calls: list[bool] = []
    _patch_v2(
        monkeypatch,
        lambda *args, **_: calls.append(True) or object(),
        lambda *args, **kwargs: _Compiled(),
    )
    monkeypatch.setenv("VIDEO_FLOW_VISUAL_V2", flag)

    result, _ = _run(tmp_path, renderer=_Renderer(), gateway=_Gateway())

    assert result["state"] == "complete"
    assert calls == [True]


@pytest.mark.parametrize("flag", ["", "false", "0", "off", "no", "junk"])
def test_nontruthy_environment_flag_keeps_v2_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag: str) -> None:
    _patch_v1(monkeypatch)
    _patch_v2(
        monkeypatch,
        lambda *args, **_: pytest.fail("nontruthy flag must not enable V2"),
        lambda *args, **kwargs: pytest.fail("nontruthy flag must not compile V2"),
    )
    monkeypatch.setenv("VIDEO_FLOW_VISUAL_V2", flag)

    result, _ = _run(tmp_path, renderer=_Renderer(), gateway=_Gateway())

    assert result["state"] == "complete"


def test_successful_v2_forwards_recent_signatures_writes_validation_and_appends_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_v1(monkeypatch)
    received: dict[str, Any] = {}
    recent = (_Signature(),)
    harness = _SignatureHarness(recent)

    def director(*_args: Any, **kwargs: Any) -> object:
        received.update(kwargs)
        return object()

    _patch_v2(monkeypatch, director, lambda *args, **kwargs: _Compiled(), harness=harness)
    result, _ = _run(tmp_path, renderer=_Renderer(), gateway=_Gateway(), visual_v2_enabled=True)

    visual = tmp_path / "vf-v2-integration" / "visual"
    assert result["state"] == "complete"
    assert received["recent_signatures"] == [_Signature().to_dict()]
    assert json.loads((visual / "validation.json").read_text(encoding="utf-8"))["valid"] is True
    assert json.loads((visual / "visual-signature.json").read_text(encoding="utf-8")) == _Signature().to_dict()
    assert harness.recent_calls == 1
    assert len(harness.append_calls) == 1
    assert harness.paths and harness.paths[0].as_posix().endswith(".voice_flow/video_flow/visual-signatures.json")


def test_validation_failure_uses_v1_and_records_no_signature(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_v1(monkeypatch)
    harness = _patch_v2(
        monkeypatch,
        lambda *args, **kwargs: object(),
        lambda *args, **kwargs: _Compiled(),
        validator=lambda _compiled: (_ for _ in ()).throw(ValueError("invalid compiled visual")),
    )
    result, _ = _run(tmp_path, renderer=_Renderer(), gateway=_Gateway(), visual_v2_enabled=True)
    assert result["state"] == "complete"
    assert harness.append_calls == []
    assert (tmp_path / "vf-v2-integration" / "creative-direction.json").is_file()


def test_browser_to_portable_fallback_records_no_v2_signature(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_v1(monkeypatch)
    harness = _patch_v2(monkeypatch, lambda *args, **kwargs: object(), lambda *args, **kwargs: _Compiled())
    renderer = _Renderer(fail_hyperframes=True)
    result, _ = _run(tmp_path, renderer=renderer, gateway=_Gateway(), visual_v2_enabled=True)
    assert result["state"] == "complete"
    assert [item["renderer"] for item in renderer.productions] == ["hyperframes", "no-browser"]
    assert harness.append_calls == []


def test_signature_append_failure_does_not_fail_completed_video(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_v1(monkeypatch)
    harness = _SignatureHarness()
    harness.append_error = OSError("signature store unavailable")
    _patch_v2(monkeypatch, lambda *args, **kwargs: object(), lambda *args, **kwargs: _Compiled(), harness=harness)
    result, _ = _run(tmp_path, renderer=_Renderer(), gateway=_Gateway(), visual_v2_enabled=True)
    assert result["state"] == "complete"
    assert len(harness.append_calls) == 1


def test_unsafe_compiler_artifact_path_uses_v1_and_records_no_signature(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_v1(monkeypatch)
    harness = _patch_v2(monkeypatch, lambda *args, **kwargs: object(), lambda *args, **kwargs: _Compiled(unsafe_artifact=True))
    result, _ = _run(tmp_path, renderer=_Renderer(), gateway=_Gateway(), visual_v2_enabled=True)
    assert result["state"] == "complete"
    assert harness.append_calls == []
    assert not (tmp_path / "vf-v2-integration" / "escape.json").exists()


def test_flag_off_never_reads_or_appends_visual_signatures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_v1(monkeypatch)
    harness = _patch_v2(
        monkeypatch,
        lambda *args, **kwargs: pytest.fail("V2 must remain off"),
        lambda *args, **kwargs: pytest.fail("V2 must remain off"),
    )
    result, _ = _run(tmp_path, renderer=_Renderer(), visual_v21_enabled=False)
    assert result["state"] == "complete"
    assert harness.recent_calls == 0
    assert harness.append_calls == []

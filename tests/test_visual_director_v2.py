"""Tests for the single-call, consent-safe Visual Director V2 boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from voice_flow.video_flow_engine.visual_director_v2 import (
    VisualDirectorV2Error,
    direct_visual_plan_v2,
)


MODEL_REF = "openai/gpt-5.6-sol"
JOB_ID = "vf-visual-director"


def _storyboard(*, with_ids: bool = True) -> dict[str, Any]:
    sections = [
        {"title": "Residual connection", "lecture_lines": ["Signals merge safely."]},
        {"title": "Residual result", "lecture_lines": ["The result is F of x plus x."]},
    ]
    if with_ids:
        sections[0]["id"] = "residual-storyboard"
        sections[1]["id"] = "result-storyboard"
    return {"topic": "Residual blocks", "sections": sections}


def _valid_plan(section_ids: tuple[str, str] = ("residual-storyboard", "result-storyboard")) -> dict[str, Any]:
    first_section, second_section = section_ids
    return {
        "version": "2.0",
        "design_bible": {
            "visual_character": "industrial technical systems",
            "surface_mode": "technical",
            "palette_intent": {
                "dominant": "near-black",
                "contrast": "very-high",
                "accent_family": "signal-red",
                "secondary_family": "hard-white",
                "temperature": "neutral",
                "saturation": "selective",
            },
            "typography_character": "technical",
            "shape_language": "diagrammatic",
            "background_character": "grid",
            "motion_character": "technical",
            "transition_character": "fade",
            "camera_character": "focus",
            "caption_integration": "reserved-bottom",
        },
        "scenes": [
            {
                "scene_id": "residual-block",
                "storyboard_section_id": first_section,
                "learning_goal": "Explain the shortcut path.",
                "visual_thesis": "The input follows a transform and bypass before merging.",
                "visual_mode": "mechanism",
                "objects": [
                    {"id": "input_x", "type": "node", "label": "Input x", "role": "primary", "region": "left"},
                    {"id": "transform_f", "type": "operator", "label": "F(x)", "role": "secondary", "region": "center"},
                    {"id": "shortcut", "type": "curve", "label": "Shortcut", "role": "support", "region": "top"},
                    {"id": "sum", "type": "operator", "label": "+", "role": "primary", "region": "right"},
                ],
                "relationships": [
                    {"source": "input_x", "target": "transform_f", "kind": "flows_to"},
                    {"source": "input_x", "target": "shortcut", "kind": "bypasses"},
                    {"source": "transform_f", "target": "sum", "kind": "merges_into"},
                    {"source": "shortcut", "target": "sum", "kind": "merges_into"},
                ],
                "beats": [
                    {"order": 1, "phase": "intro", "action": "create", "object_id": "input_x", "reason": "Show the input."},
                    {"order": 2, "phase": "build", "action": "connect", "object_id": "transform_f", "reason": "Build the transform path."},
                    {"order": 3, "phase": "build", "action": "draw", "object_id": "shortcut", "reason": "Show the bypass."},
                    {"order": 4, "phase": "resolve", "action": "merge", "object_id": "sum", "reason": "Show the merge."},
                ],
                "continuity": {"carry_forward": []},
            },
            {
                "scene_id": "residual-result",
                "storyboard_section_id": second_section,
                "learning_goal": "Name the residual result.",
                "visual_thesis": "The merged output is F of x plus x.",
                "visual_mode": "equation",
                "objects": [
                    {"id": "result_equation", "type": "equation", "label": "F(x) + x", "role": "primary", "region": "center"},
                ],
                "relationships": [],
                "beats": [
                    {"order": 1, "phase": "conclude", "action": "reveal", "object_id": "result_equation", "reason": "Name the result."},
                ],
                "continuity": {"carry_forward": ["sum"]},
            },
        ],
    }


class _ProcessManager:
    def __init__(self, *, cancelled: bool = False) -> None:
        self.cancelled = cancelled

    def raise_if_cancelled(self, job_id: str) -> None:
        if self.cancelled:
            raise RuntimeError(f"cancelled: job was cancelled ({job_id})")


class _IsolatedGateway:
    is_local = False

    def __init__(self, response: str, *, cancel_after_call: _ProcessManager | None = None) -> None:
        self.response = response
        self.cancel_after_call = cancel_after_call
        self.calls: list[dict[str, Any]] = []
        self.api_key = "sk-director-test-secret"

    def request_isolated(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        if self.cancel_after_call is not None:
            self.cancel_after_call.cancelled = True
        return self.response


class _LocalGateway:
    is_local = True

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def generate(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return self.response


def _direct(project_dir: Path, gateway: Any, manager: _ProcessManager, *, storyboard: dict[str, Any] | None = None, allow_external_ai: bool = True, visual_direction: str = "hard black white and red", theme: Any = None):
    return direct_visual_plan_v2(
        storyboard or _storyboard(),
        gateway,
        model_ref=MODEL_REF,
        allow_external_ai=allow_external_ai,
        visual_direction=visual_direction,
        theme={"mode": "dark"} if theme is None else theme,
        job_id=JOB_ID,
        process_manager=manager,
        project_dir=project_dir,
    )


def test_external_gateway_uses_one_isolated_request_and_persists_only_valid_plan(tmp_path: Path) -> None:
    project_dir = tmp_path / "job"
    manager = _ProcessManager()
    gateway = _IsolatedGateway(json.dumps(_valid_plan()))

    plan = _direct(project_dir, gateway, manager)

    assert len(gateway.calls) == 1
    call = gateway.calls[0]
    assert call["model_ref"] == MODEL_REF
    assert call["job_id"] == JOB_ID
    assert call["process_manager"] is manager
    assert call["max_tokens"] == 6_000
    assert call["timeout_seconds"] == 180
    assert "residual-storyboard" in call["prompt"]
    assert "result-storyboard" in call["prompt"]
    assert "hard black white and red" in call["prompt"]
    assert "sk-director-test-secret" not in call["prompt"]
    assert "untrusted reference data" in call["prompt"].lower()
    assert "do not use v1 treatment names" in call["prompt"].lower()
    assert "1 to 16 objects" in call["prompt"].lower()
    assert plan.to_dict() == _valid_plan()
    artifact = project_dir / "visual" / "visual-plan-v2.json"
    assert artifact.is_file()
    assert json.loads(artifact.read_text(encoding="utf-8")) == _valid_plan()
    assert sorted(path.relative_to(project_dir).as_posix() for path in project_dir.rglob("*") if path.is_file()) == [
        "visual/visual-plan-v2.json"
    ]


def test_theme_raw_colours_are_not_forwarded_to_the_model(tmp_path: Path) -> None:
    gateway = _IsolatedGateway(json.dumps(_valid_plan()))
    _direct(
        tmp_path / "job",
        gateway,
        _ProcessManager(),
        theme={"mode": "dark", "bg": "#123456", "accent": "#abcdef", "name": "technical"},
    )
    prompt = gateway.calls[0]["prompt"]
    assert "#123456" not in prompt
    assert "#abcdef" not in prompt
    assert '"mode": "dark"' in prompt

def test_fenced_json_response_is_accepted(tmp_path: Path) -> None:
    manager = _ProcessManager()
    response = "Director output:\n```json\n" + json.dumps(_valid_plan()) + "\n```"

    plan = _direct(tmp_path / "job", _IsolatedGateway(response), manager)

    assert plan.to_dict() == _valid_plan()


@pytest.mark.parametrize("response", ["not json", json.dumps({"version": "bad", "design_bible": {}, "scenes": []})])
def test_invalid_response_raises_typed_error_without_plan_artifact(tmp_path: Path, response: str) -> None:
    project_dir = tmp_path / "job"

    with pytest.raises(VisualDirectorV2Error):
        _direct(project_dir, _IsolatedGateway(response), _ProcessManager())

    assert not (project_dir / "visual" / "visual-plan-v2.json").exists()


def test_nonlocal_gateway_requires_literal_external_ai_consent_before_call(tmp_path: Path) -> None:
    gateway = _IsolatedGateway(json.dumps(_valid_plan()))

    with pytest.raises(VisualDirectorV2Error):
        _direct(tmp_path / "job", gateway, _ProcessManager(), allow_external_ai=False)

    assert gateway.calls == []


def test_nonlocal_gateway_without_isolated_method_is_rejected(tmp_path: Path) -> None:
    class Gateway:
        is_local = False

    with pytest.raises(VisualDirectorV2Error):
        _direct(tmp_path / "job", Gateway(), _ProcessManager())


def test_local_gateway_uses_one_supported_method_without_external_consent(tmp_path: Path) -> None:
    gateway = _LocalGateway(json.dumps(_valid_plan()))

    plan = _direct(tmp_path / "job", gateway, _ProcessManager(), allow_external_ai=False)

    assert plan.to_dict() == _valid_plan()
    assert len(gateway.calls) == 1


def test_missing_storyboard_ids_are_normalized_before_prompt_and_validation(tmp_path: Path) -> None:
    gateway = _IsolatedGateway(json.dumps(_valid_plan(("section_1", "section_2"))))

    plan = _direct(tmp_path / "job", gateway, _ProcessManager(), storyboard=_storyboard(with_ids=False))

    assert [scene["storyboard_section_id"] for scene in plan.to_dict()["scenes"]] == ["section_1", "section_2"]
    assert "section_1" in gateway.calls[0]["prompt"]
    assert "section_2" in gateway.calls[0]["prompt"]


def test_cancellation_before_the_director_call_propagates_without_gateway_invocation(tmp_path: Path) -> None:
    manager = _ProcessManager(cancelled=True)
    gateway = _IsolatedGateway(json.dumps(_valid_plan()))

    with pytest.raises(RuntimeError, match="^cancelled:"):
        _direct(tmp_path / "job", gateway, manager)

    assert gateway.calls == []


def test_gateway_cancellation_then_generic_runtime_error_still_propagates_cancelled(tmp_path: Path) -> None:
    manager = _ProcessManager()

    class Gateway:
        is_local = False
        calls = 0

        def request_isolated(self, **_kwargs: Any) -> str:
            self.calls += 1
            manager.cancelled = True
            raise RuntimeError("Planning provider timed out")

    gateway = Gateway()
    with pytest.raises(RuntimeError, match="^cancelled:"):
        _direct(tmp_path / "job", gateway, manager)
    assert gateway.calls == 1


@pytest.mark.parametrize("bad_id", ["duplicate-id", "bad/id", "1-leading-digit"])
def test_invalid_or_duplicate_storyboard_ids_fail_before_model_call(tmp_path: Path, bad_id: str) -> None:
    storyboard = _storyboard()
    if bad_id == "duplicate-id":
        storyboard["sections"][1]["id"] = storyboard["sections"][0]["id"]
    else:
        storyboard["sections"][0]["id"] = bad_id
    gateway = _IsolatedGateway(json.dumps(_valid_plan()))
    with pytest.raises(VisualDirectorV2Error):
        _direct(tmp_path / "job", gateway, _ProcessManager(), storyboard=storyboard)
    assert gateway.calls == []

def test_cancellation_after_the_director_call_propagates_without_artifact(tmp_path: Path) -> None:
    project_dir = tmp_path / "job"
    manager = _ProcessManager()
    gateway = _IsolatedGateway(json.dumps(_valid_plan()), cancel_after_call=manager)

    with pytest.raises(RuntimeError, match="^cancelled:"):
        _direct(project_dir, gateway, manager)

    assert len(gateway.calls) == 1
    assert not (project_dir / "visual" / "visual-plan-v2.json").exists()

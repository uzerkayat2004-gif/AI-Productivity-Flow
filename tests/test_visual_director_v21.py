from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from voice_flow.video_flow_engine.visual_director_v2 import VisualDirectorV21Error, direct_visual_program_v21


def _program() -> dict[str, Any]:
    return {"version": "2.1", "content_intent": "DEMONSTRATE", "design_bible": {"surface": "paper", "palette": {"dominant": "paper", "accent_family": "green"}, "typography": "editorial", "shape_language": "organic", "background": "paper", "motion": "flowing", "caption_safe": "reserved_bottom"}, "scenes": [{"scene_id": "growth", "storyboard_section_id": "growth", "purpose": "Show a plant developing.", "representation_strategy": ["DIRECT_DEPICTION", "STATE_EVOLUTION"], "world": {"description": "A garden"}, "subjects": [{"id": "plant", "semantic_name": "apple tree", "structural_family": "organic_branching"}], "relationships": [], "initial_state": {"objects": {"plant": {}}}, "events": [], "shot": {"mode": "focus", "framing": "hero", "subject": "plant"}}]}


class _Manager:
    def __init__(self, cancelled: bool = False) -> None:
        self.cancelled = cancelled
    def raise_if_cancelled(self, _: str) -> None:
        if self.cancelled:
            raise RuntimeError("cancelled: test")


class _Gateway:
    is_local = True
    def __init__(self, response: Any) -> None:
        self.response = json.dumps(response)
        self.calls: list[dict[str, Any]] = []
    def generate(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return self.response


def _storyboard() -> dict[str, Any]:
    return {"topic": "Apple growth", "sections": [{"id": "growth", "title": "Growth", "lecture_lines": ["A bud opens into fruit."], "animations": ["grow"]}]}


def test_v21_director_uses_one_registry_prompt_and_persists_program(tmp_path: Path) -> None:
    gateway = _Gateway(_program())
    program = direct_visual_program_v21(_storyboard(), gateway, mode="lesson", duration_seconds=12, visual_direction="organic botanical", theme={"name": "paper", "bg": "#010203"}, job_id="vf-v21-director", process_manager=_Manager(), project_dir=tmp_path)
    assert program.version == "2.1"
    assert len(gateway.calls) == 1
    call = gateway.calls[0]
    assert call["max_tokens"] == 12_000
    assert "AUTHORITATIVE CAPABILITY REGISTRY" in call["prompt"]
    assert "DIRECT_DEPICTION" in call["prompt"]
    assert "not a required visual presentation" in call["prompt"]
    assert "growth" in call["prompt"]
    assert "#010203" not in call["prompt"]
    assert json.loads((tmp_path / "visual" / "visual-program-v21.json").read_text(encoding="utf-8")) == program.to_dict()


def test_oversized_storyboard_fails_explicitly_without_call_or_silent_slice(tmp_path: Path) -> None:
    storyboard = _storyboard()
    storyboard["topic"] = "x" * 13_000
    gateway = _Gateway(_program())
    with pytest.raises(VisualDirectorV21Error, match="oversized|bounded") as exc:
        direct_visual_program_v21(storyboard, gateway, job_id="vf", process_manager=_Manager(), project_dir=tmp_path)
    assert exc.value.code == "v21_storyboard_oversize"
    assert gateway.calls == []


def test_external_v21_call_requires_consent_and_cancellation_precedes_gateway(tmp_path: Path) -> None:
    class External:
        is_local = False
        calls = 0
        def request_isolated(self, **_: Any) -> str:
            self.calls += 1
            return json.dumps(_program())
    external = External()
    with pytest.raises(VisualDirectorV21Error):
        direct_visual_program_v21(_storyboard(), external, allow_external_ai=False, job_id="vf", process_manager=_Manager(), project_dir=tmp_path)
    assert external.calls == 0
    gateway = _Gateway(_program())
    with pytest.raises(RuntimeError, match="^cancelled:"):
        direct_visual_program_v21(_storyboard(), gateway, job_id="vf", process_manager=_Manager(True), project_dir=tmp_path)
    assert gateway.calls == []

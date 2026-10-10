from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
import pytest

from voice_flow.video_flow_engine import engine as engine_module
from voice_flow.video_flow_engine.engine import VideoFlowEngine, _visual_v21_enabled
from voice_flow.video_flow_engine.sandbox import EngineError


def _storyboard():
    return {"topic": "Apple", "sections": [{"id": "s", "title": "Growth", "lecture_lines": ["A bud grows into fruit."]}]}


def _program():
    return {
        "version": "2.1",
        "content_intent": "DEMONSTRATE",
        "design_bible": {
            "surface": "paper",
            "palette": {"dominant": "paper", "accent_family": "green"},
            "typography": "editorial",
            "shape_language": "organic",
            "background": "paper",
            "motion": "flowing",
            "caption_safe": "reserved_bottom",
        },
        "scenes": [
            {
                "scene_id": "scene",
                "storyboard_section_id": "s",
                "purpose": "Show growth",
                "representation_strategy": ["DIRECT_DEPICTION", "STATE_EVOLUTION"],
                "world": {"description": "garden"},
                "subjects": [{"id": "plant", "semantic_name": "apple tree", "structural_family": "organic_branching"}],
                "relationships": [],
                "initial_state": {"objects": {"plant": {}}},
                "events": [{"id": "grow", "type": "GROW", "subject": "plant", "from_state": "bud", "to_state": "flower", "duration": 2}],
                "shot": {"mode": "focus", "framing": "hero", "subject": "plant"},
            }
        ],
    }


class _PM:
    def __init__(self):
        self.cancelled = False

    def raise_if_cancelled(self, _: str):
        if self.cancelled:
            raise RuntimeError("cancelled: job was cancelled")

    def is_cancelled(self, _: str):
        return self.cancelled

    def cancel_job(self, _: str):
        self.cancelled = True


class _Planner:
    def plan(self, *_: Any, **__: Any):
        return _storyboard()


class _Gateway:
    is_local = True

    def __init__(self, payload):
        self.payload = json.dumps(payload)
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


class _Renderer:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def render(self, production, project_dir, **kwargs):
        self.calls.append(production)
        if self.fail and len(self.calls) == 1:
            raise EngineError("render_failed", "renderer failure")
        path = Path(project_dir) / "video.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"mp4")
        return path


def test_default_routing_flag_no_env_no_kwargs():
    """V2.1 remains enabled as the fallback production path."""
    assert _visual_v21_enabled({}) is True


def test_default_routing_flag_explicit_disable_kwargs():
    """Explicit visual_v21_enabled=False in kwargs disables V2.1."""
    assert _visual_v21_enabled({"visual_v21_enabled": False}) is False


def test_default_routing_flag_explicit_enable_kwargs():
    """Explicit visual_v21_enabled=True in kwargs enables V2.1."""
    assert _visual_v21_enabled({"visual_v21_enabled": True}) is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "FALSE", "OFF", "0 "])
def test_default_routing_flag_escape_hatch_env(monkeypatch: pytest.MonkeyPatch, value: str):
    """Setting VIDEO_FLOW_VISUAL_V21 to 0/false/off/no acts as emergency escape hatch."""
    monkeypatch.setenv("VIDEO_FLOW_VISUAL_V21", value)
    assert _visual_v21_enabled({}) is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE"])
def test_default_routing_flag_explicit_enable_env(monkeypatch: pytest.MonkeyPatch, value: str):
    """Setting VIDEO_FLOW_VISUAL_V21 to 1/true/on enables V2.1."""
    monkeypatch.setenv("VIDEO_FLOW_VISUAL_V21", value)
    assert _visual_v21_enabled({}) is True


def test_explicit_visual_v21_route_remains_separate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """An explicit Visual V2.1 request bypasses Narova Direct."""
    monkeypatch.delenv("VIDEO_FLOW_VISUAL_V21", raising=False)
    monkeypatch.setattr("voice_flow.paths.data_dir", lambda: tmp_path)
    gateway = _Gateway(_program())
    engine = VideoFlowEngine(process_manager=_PM(), planner=_Planner(), renderer=_Renderer(), model_gateway=gateway)

    result = engine.run(
        "vf-default-job",
        projects_root=tmp_path,
        project_dir=tmp_path / "vf-default-job",
        source_text="Show apple growth",
        allow_external_ai=False,
        video_engine="visual-v2.1",
    )

    assert result["state"] == "complete"
    assert result["provenance"]["requested_engine"] == "visual-v2.1"
    assert result["provenance"]["final_engine"] == "visual-v2.1"
    assert result["provenance"]["fallback_used"] is False
    assert len(gateway.calls) == 1


def test_normal_engine_run_honors_legacy_escape_hatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Setting VIDEO_FLOW_VISUAL_V21=0 forces legacy V1 execution."""
    monkeypatch.setenv("VIDEO_FLOW_VISUAL_V21", "0")
    monkeypatch.setattr("voice_flow.paths.data_dir", lambda: tmp_path)
    gateway = _Gateway(_program())
    engine = VideoFlowEngine(process_manager=_PM(), planner=_Planner(), renderer=_Renderer(), model_gateway=gateway)

    result = engine.run(
        "vf-legacy-job",
        projects_root=tmp_path,
        project_dir=tmp_path / "vf-legacy-job",
        source_text="Show apple growth",
        allow_external_ai=False,
        video_engine="visual-v2.1",
    )

    assert result["state"] == "complete"
    assert len(gateway.calls) == 0  # V2.1 director was bypassed cleanly


def test_cancellation_preserves_cancelled_state_without_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Cancelled job records state=cancelled and never triggers V1 fallback."""
    monkeypatch.delenv("VIDEO_FLOW_VISUAL_V21", raising=False)
    pm = _PM()
    pm.cancel_job("vf-cancel-job")
    engine = VideoFlowEngine(process_manager=pm, planner=_Planner(), renderer=_Renderer(), model_gateway=_Gateway(_program()))

    result = engine.run(
        "vf-cancel-job",
        projects_root=tmp_path,
        project_dir=tmp_path / "vf-cancel-job",
        source_text="Show apple growth",
        allow_external_ai=False,
        video_engine="visual-v2.1",
    )

    assert result["state"] == "cancelled"
    assert result["error_code"] == "cancelled"


def test_retired_v3_package_unreachable():
    """Verify the retired video_flow_v3 package is removed and cannot be imported."""
    with pytest.raises(ModuleNotFoundError):
        __import__("voice_flow.video_flow_v3")


def test_shared_contracts_migrated_to_video_flow_contracts():
    """Verify security validator and Job model are available from neutral contracts."""
    from voice_flow.video_flow_contracts import JobV3, VideoFlowJob, validate_no_executable_code

    job = JobV3("test-1")
    assert job.job_id == "test-1"
    assert VideoFlowJob is JobV3

    # Safe payload passes
    validate_no_executable_code({"title": "Safe Video", "scenes": [{"text": "Hello"}]})

    # Unsafe payload is rejected
    with pytest.raises(ValueError, match="Security Boundary Violation"):
        validate_no_executable_code("<script>alert(1)</script>")


def test_normal_successful_v21_never_touches_v1_authoring(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Prove that a successful V2.1 execution never invokes creative_director, scene_author, or bridge."""
    from voice_flow.video_flow_engine import bridge, creative_director, scene_author

    v1_calls = []
    monkeypatch.setattr(creative_director, "direct", lambda *a, **kw: v1_calls.append("creative_director") or {})
    monkeypatch.setattr(scene_author, "author_scene", lambda *a, **kw: v1_calls.append("scene_author") or {})
    monkeypatch.setattr(bridge, "build_narova_production", lambda *a, **kw: v1_calls.append("bridge") or {})

    monkeypatch.delenv("VIDEO_FLOW_VISUAL_V21", raising=False)
    monkeypatch.setattr("voice_flow.paths.data_dir", lambda: tmp_path)
    gateway = _Gateway(_program())
    engine = VideoFlowEngine(process_manager=_PM(), planner=_Planner(), renderer=_Renderer(), model_gateway=gateway)

    result = engine.run(
        "vf-clean-v21",
        projects_root=tmp_path,
        project_dir=tmp_path / "vf-clean-v21",
        source_text="Show apple growth",
        allow_external_ai=False,
        video_engine="visual-v2.1",
    )

    assert result["state"] == "complete"
    assert result["provenance"]["final_engine"] == "visual-v2.1"
    assert result["provenance"]["fallback_used"] is False
    assert v1_calls == [], f"V1 authoring was unexpectedly touched during normal V2.1: {v1_calls}"


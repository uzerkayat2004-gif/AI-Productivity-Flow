from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from voice_flow.video_flow_engine import engine as engine_module
from voice_flow.video_flow_engine.engine import VideoFlowEngine
from voice_flow.video_flow_engine.sandbox import EngineError


def _storyboard():
    return {"topic": "Apple", "sections": [{"id": "s", "title": "Growth", "lecture_lines": ["A bud grows into fruit."]}]}


def _program():
    return {"version": "2.1", "content_intent": "DEMONSTRATE", "design_bible": {"surface": "paper", "palette": {"dominant": "paper", "accent_family": "green"}, "typography": "editorial", "shape_language": "organic", "background": "paper", "motion": "flowing", "caption_safe": "reserved_bottom"}, "scenes": [{"scene_id": "scene", "storyboard_section_id": "s", "purpose": "Show growth", "representation_strategy": ["DIRECT_DEPICTION", "STATE_EVOLUTION"], "world": {"description": "garden"}, "subjects": [{"id": "plant", "semantic_name": "apple tree", "structural_family": "organic_branching"}], "relationships": [], "initial_state": {"objects": {"plant": {}}}, "events": [{"id": "grow", "type": "GROW", "subject": "plant", "from_state": "bud", "to_state": "flower", "duration": 2}], "shot": {"mode": "focus", "framing": "hero", "subject": "plant"}}]}


class _PM:
    def __init__(self): self.cancelled = False
    def raise_if_cancelled(self, _: str):
        if self.cancelled: raise RuntimeError("cancelled: test")
    def is_cancelled(self, _: str): return self.cancelled
    def cancel_job(self, _: str): self.cancelled = True


class _Planner:
    def plan(self, *_: Any, **__: Any): return _storyboard()


class _Gateway:
    is_local = True
    def __init__(self, payload): self.payload = json.dumps(payload); self.calls = []
    def generate(self, **kwargs): self.calls.append(kwargs); return self.payload


class _Renderer:
    def __init__(self, fail=False): self.fail = fail; self.calls = []
    def render(self, production, project_dir, **kwargs):
        self.calls.append(production)
        if self.fail and len(self.calls) == 1: raise EngineError("render_failed", "browser unavailable")
        path = Path(project_dir) / "video.mp4"; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"mp4"); return path


def _run(tmp_path: Path, gateway: Any, renderer: Any, **kwargs):
    return VideoFlowEngine(process_manager=_PM(), planner=_Planner(), renderer=renderer, model_gateway=gateway).run("vf-v21-engine", projects_root=tmp_path, project_dir=tmp_path / "vf-v21-engine", source_text="show an apple", allow_external_ai=False, visual_v21_enabled=True, **kwargs)


def test_v21_success_has_final_provenance_and_one_director_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("voice_flow.paths.data_dir", lambda: tmp_path)
    gateway = _Gateway(_program())
    result = _run(tmp_path, gateway, _Renderer(), duration_seconds=8, voice="edge/en-US-AvaNeural")
    assert result["state"] == "complete"
    assert result["provenance"]["final_engine"] == "visual-v2.1"
    assert result["provenance"]["fallback_used"] is False
    assert len(gateway.calls) == 1
    assert (tmp_path / "vf-v21-engine" / "provenance" / "production-provenance.json").is_file()


def test_v21_browser_failure_is_portable_fallback_with_no_signature_append(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("voice_flow.paths.data_dir", lambda: tmp_path)
    monkeypatch.setattr(engine_module, "build_narova_production", lambda *args, **kwargs: {"renderer": "no-browser", "marker": "portable"})
    gateway = _Gateway(_program())
    result = _run(tmp_path, gateway, _Renderer(fail=True))
    assert result["state"] == "complete"
    assert result["provenance"]["final_engine"] == "portable-v1"
    assert result["provenance"]["fallback_stage"] == "browser"


def test_v21_failure_falls_back_to_v1_and_marks_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("voice_flow.paths.data_dir", lambda: tmp_path)
    monkeypatch.setattr(engine_module, "build_narova_production", lambda *args, **kwargs: {"renderer": "hyperframes", "marker": "v1"})
    gateway = _Gateway({"not": "a visual program"})
    result = _run(tmp_path, gateway, _Renderer())
    assert result["state"] == "complete"
    assert result["provenance"]["final_engine"] == "visual-v1"
    assert result["provenance"]["fallback_used"] is True
    assert result["provenance"]["fallback_stage"] == "capability_validation"



class _FailBothRenderer(_Renderer):
    def render(self, production, project_dir, **kwargs):
        self.calls.append(production)
        raise EngineError("render_failed", "renderer unavailable")


def test_v21_double_render_failure_writes_failed_terminal_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("voice_flow.paths.data_dir", lambda: tmp_path)
    monkeypatch.setattr(engine_module, "build_narova_production", lambda *args, **kwargs: {"renderer": "no-browser"})
    result = _run(tmp_path, _Gateway(_program()), _FailBothRenderer())
    assert result["state"] == "failed"
    provenance = result["provenance"]
    assert provenance["final_status"] == "failed"
    assert provenance["final_engine"] is None
    assert provenance["final_artifacts"] == []
    assert json.loads((tmp_path / "vf-v21-engine" / "provenance" / "production-provenance.json").read_text(encoding="utf-8"))["final_status"] == "failed"


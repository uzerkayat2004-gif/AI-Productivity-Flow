"""v1.0.13: a missing AI planning key never fails a video, and only a
confirmed Google AI Ultra account is offered Cinematic."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "src/voice_flow/gui/video-flow.js").read_text(encoding="utf-8")
MAIN = (ROOT / "src/voice_flow/main.py").read_text(encoding="utf-8")
WIDGET = (ROOT / "src/voice_flow/video_flow_widget.py").read_text(encoding="utf-8")


def test_plan_mapping_only_ultra_unlocks_cinematic():
    from voice_flow.video_flow_engine.notebooklm.account_plan import plan_from_tier

    assert plan_from_tier(3)["is_ultra"] and plan_from_tier(6)["is_ultra"]
    for tier in (1, 2, 4, 5, None, 0, True, "3"):
        assert not plan_from_tier(tier)["cinematic_available"], tier
    assert plan_from_tier(2)["plan"] == "pro" and plan_from_tier(None)["plan"] == "unknown"


def test_plan_probe_failure_means_no_cinematic(monkeypatch):
    from voice_flow.video_flow_engine.notebooklm import account_plan as ap

    ap.clear_cache()
    monkeypatch.setattr(ap, "_run_probe", lambda profile, timeout: (_ for _ in ()).throw(TimeoutError()))
    assert ap.cinematic_allowed("p1") is False
    ap.clear_cache()
    monkeypatch.setattr(ap, "_run_probe", lambda profile, timeout: 3)
    assert ap.cinematic_allowed("p1") is True
    monkeypatch.setattr(ap, "_run_probe", lambda profile, timeout: 2)
    assert ap.get_account_plan("p1")["is_ultra"] is True  # cached
    assert ap.get_account_plan("p1", refresh=True)["is_ultra"] is False
    ap.clear_cache()


def test_cold_cache_answers_no_without_blocking(monkeypatch):
    from voice_flow.video_flow_engine.notebooklm import account_plan as ap

    ap.clear_cache()
    started = []
    monkeypatch.setattr(ap, "prewarm", lambda profile=None: started.append(profile))
    t0 = time.monotonic()
    assert ap.cinematic_allowed_now("p2") is False
    assert time.monotonic() - t0 < 0.5 and started


def test_engine_turns_cinematic_into_explainer_without_ultra(monkeypatch, tmp_path):
    from tests.test_v1012_cinematic_fallback import _engine_with_failing_notebooklm

    eng, calls, _ = _engine_with_failing_notebooklm(monkeypatch, tmp_path, fail_times=0)
    monkeypatch.setattr(type(eng), "_cinematic_allowed", staticmethod(lambda profile: False))
    eng.run("vf-t13", source_text="Some text to explain.", provider="notebooklm",
            format="cinematic", requested_format="cinematic", projects_root=str(tmp_path))
    assert [c[1] for c in calls if c[0] == "generate"] == ["explainer"]


def test_missing_planning_key_does_not_fail_the_job(tmp_path):
    from voice_flow.video_flow_service import VideoFlowService

    seen = {}

    def failing_gateway(model_ref):
        raise RuntimeError("No active planning connection is configured")

    class FakeEngine:
        def __init__(self, model_gateway=None):
            seen["gateway"] = model_gateway

        def run(self, job_id, **kwargs):
            out = Path(kwargs["projects_root"]) / job_id / "video.mp4"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"x" * 2048)
            return {"state": "complete", "output_path": str(out)}

        def cancel(self, job_id):
            pass

    svc = VideoFlowService(projects_root=tmp_path / "proj", gateway_factory=failing_gateway, engine_factory=FakeEngine)
    job = svc.queue(source_text="Hello world, this is a test.", provider="notebooklm", video_engine="notebooklm",
                    allow_external_ai=True, allow_local_fallback=True)
    for _ in range(100):
        state = svc.get(job.job_id).state
        if state in ("complete", "failed", "cancelled"):
            break
        time.sleep(0.05)
    final = svc.get(job.job_id)
    assert "planning connection" not in (final.message or "")
    assert "gateway" in seen and seen["gateway"] is None


def test_ui_only_asks_ultra_accounts():
    assert '(await vfCinematicAvailable()) ? await askVideoTreatmentChoice() : "explainer"' in JS
    assert "/api/video-flow/notebooklm/plan" in JS
    assert "cinematic_allowed_now()" in MAIN and 'video_format="explainer"' in MAIN
    assert '"allow_external_ai": False,' in WIDGET

"""v1.0.12: Auto-Adaptive never picks Cinematic (needs Google AI Ultra), and a
rejected Cinematic request is remade as an Explainer instead of failing."""
from pathlib import Path

ENGINE = (Path(__file__).resolve().parents[1] / "src/voice_flow/video_flow_engine/engine.py").read_text(encoding="utf-8")
SERVICE = (Path(__file__).resolve().parents[1] / "src/voice_flow/video_flow_service.py").read_text(encoding="utf-8")


def test_auto_adaptive_never_resolves_to_cinematic():
    assert 'format_name == "cinematic" and not explicit_cinematic' in ENGINE
    assert 'format_name = "explainer"' in ENGINE


def test_rejected_cinematic_retries_as_explainer():
    assert 'request.format == "cinematic"' in ENGINE
    assert 'format="explainer",' in ENGINE and 'dataclasses.replace(' in ENGINE


def test_service_passes_requested_format_to_engine():
    assert '"requested_format": options.get("requested_format")' in SERVICE


def _engine_with_failing_notebooklm(monkeypatch, tmp_path, fail_times):
    from voice_flow.video_flow_engine import engine as engine_mod
    from voice_flow.video_flow_engine.notebooklm import provider as provider_mod
    from voice_flow.video_flow_engine.notebooklm.models import NotebookLMVideoError

    calls = []

    class FakeProvider:
        profile = "video-flow-experiment"

        def __init__(self, *args, **kwargs):
            calls.append(("init", kwargs.get("allow_local_fallback")))

        def generate(self, request):
            calls.append(("generate", request.format))
            if len([c for c in calls if c[0] == "generate"]) <= fail_times:
                raise NotebookLMVideoError("GENERATION_FAILED", "Video generation failed")
            request.output_path.write_bytes(b"mp4")
            from types import SimpleNamespace
            return SimpleNamespace(to_dict=lambda: {}, provenance_path=None, duration_seconds=1.0, timings={}, document_profile=None)

        def is_local_fallback_enabled(self, request=None):
            return False

    monkeypatch.setattr(provider_mod, "NotebookLMVideoProvider", FakeProvider)
    import voice_flow.video_flow_engine.notebooklm as nlm_pkg
    monkeypatch.setattr(nlm_pkg, "NotebookLMVideoProvider", FakeProvider)
    fallbacks = []
    eng = engine_mod.VideoFlowEngine()
    monkeypatch.setattr(
        eng, "_auth_fallback_to_local",
        lambda *a, **k: fallbacks.append(k.get("reason")) or {"state": "complete", "reason": k.get("reason")},
    )
    return eng, calls, fallbacks


def test_generation_failure_retries_once_then_succeeds(monkeypatch, tmp_path):
    eng, calls, fallbacks = _engine_with_failing_notebooklm(monkeypatch, tmp_path, fail_times=1)
    result = eng.run("vf-test1", source_text="Some text to explain.", provider="notebooklm",
                     format="explainer", projects_root=str(tmp_path))
    assert [c for c in calls if c[0] == "generate"] == [("generate", "explainer"), ("generate", "explainer")]
    assert ("init", False) in calls  # provider's own broken inner fallback is off
    assert result.get("provider") == "notebooklm"
    assert fallbacks == []


def test_generation_failing_twice_uses_local_engine(monkeypatch, tmp_path):
    eng, calls, fallbacks = _engine_with_failing_notebooklm(monkeypatch, tmp_path, fail_times=2)
    result = eng.run("vf-test2", source_text="Some text to explain.", provider="notebooklm",
                     format="cinematic", requested_format="cinematic", projects_root=str(tmp_path))
    assert [c[1] for c in calls if c[0] == "generate"] == ["cinematic", "explainer"]
    assert fallbacks == ["notebooklm_generation_failed"]
    assert result["state"] == "complete"


def test_flow_failure_event_carries_no_user_text():
    from voice_flow import crash_reporting as cr
    event = {"message": cr.FLOW_FAILURE_MESSAGE, "tags": {"error_code": "GENERATION_FAILED"}}
    out = cr.before_send_scrubber(event, {})
    assert out["message"] == cr.FLOW_FAILURE_MESSAGE
    assert cr.before_send_scrubber({"message": "secret doc text"}, {})["message"] == "[redacted]"

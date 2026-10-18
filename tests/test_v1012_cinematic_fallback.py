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
    assert 'dataclasses.replace(request, format="explainer"' in ENGINE


def test_service_passes_requested_format_to_engine():
    assert '"requested_format": options.get("requested_format")' in SERVICE

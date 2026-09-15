from __future__ import annotations

from pathlib import Path

from voice_flow.video_flow_engine.engine import VideoFlowEngine


class _ShouldNotRun:
    def plan(self, source_text: str, **_: object) -> dict:
        raise AssertionError("planner must not run for an unsafe job id")

    def render(self, production: dict, project_dir: Path, **_: object) -> Path:
        raise AssertionError("renderer must not run for an unsafe job id")


def test_run_rejects_job_id_path_traversal(tmp_path: Path) -> None:
    dependency = _ShouldNotRun()
    engine = VideoFlowEngine(planner=dependency, renderer=dependency)

    result = engine.run(
        "../escape",
        projects_root=tmp_path,
        source_text="Safe source text",
    )

    assert result["state"] == "failed"
    assert result["error_code"] == "invalid_job_id"
    assert not (tmp_path.parent / "escape").exists()


def test_run_rejects_windows_reserved_job_id(tmp_path: Path) -> None:
    dependency = _ShouldNotRun()
    engine = VideoFlowEngine(planner=dependency, renderer=dependency)

    result = engine.run(
        "CON",
        projects_root=tmp_path,
        source_text="Safe source text",
    )

    assert result["state"] == "failed"
    assert result["error_code"] == "invalid_job_id"


def test_run_rejects_symlinked_project_dir(tmp_path: Path) -> None:
    import os

    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "vf-link-job"
    try:
        os.symlink(str(outside), str(link), target_is_directory=True)
    except (OSError, NotImplementedError):
        import pytest as _pytest
        _pytest.skip("symlinks unavailable on this platform")
    dependency = _ShouldNotRun()
    engine = VideoFlowEngine(planner=dependency, renderer=dependency)

    result = engine.run(
        "vf-link-job",
        projects_root=tmp_path,
        project_dir=link,
        source_text="Safe source text",
    )

    assert result["state"] == "failed"
    assert result["error_code"] == "invalid_project_dir"


def test_confined_path_rejects_traversal(tmp_path: Path) -> None:
    import pytest as _pytest
    from voice_flow.video_flow_engine.sandbox import EngineError, confined_path, prepare_job_directory

    job_dir = prepare_job_directory("vf-confined", projects_root=tmp_path)
    ok = confined_path(job_dir, "audio", "01.wav")
    assert ok.parent.name == "audio"
    with _pytest.raises(EngineError, match="escapes"):
        confined_path(job_dir, "..", "escape.txt")


def test_notebooklm_request_threads_target_duration(tmp_path: Path) -> None:
    from voice_flow.video_flow_engine import engine as engine_module
    import voice_flow.video_flow_engine.notebooklm as notebooklm_pkg

    captured: dict = {}

    class _FakeProvider:
        def __init__(self, **kwargs):
            # Mirror the real provider's profile attribute (the engine reads
            # provider.profile when building the VideoRequest).
            self.profile = kwargs.get("profile") or "default"

        def is_local_fallback_enabled(self, request):
            return False

        def generate(self, request):
            captured["target"] = getattr(request, "target_duration_seconds", None)
            captured["profile_target"] = (request.document_profile or {}).get("target_duration_seconds") if isinstance(request.document_profile, dict) else None

            class _Artifact:
                duration_seconds = 60.0
                timings = {}
                provenance_path = None
                document_profile = None

                def to_dict(self):
                    return {}

            artifact = _Artifact()
            artifact.document_profile = request.document_profile
            (request.output_path.parent / "video.mp4").parent.mkdir(parents=True, exist_ok=True)
            request.output_path.write_bytes(b"mp4")
            return artifact

    monkeypatch_provider = notebooklm_pkg.NotebookLMVideoProvider
    notebooklm_pkg.NotebookLMVideoProvider = _FakeProvider
    try:
        engine = VideoFlowEngine()
        result = engine.run(
            "vf-target-dur",
            projects_root=tmp_path,
            project_dir=tmp_path / "vf-target-dur",
            provider="notebooklm",
            source_text="Some source text aboutたる planning.",
            title="T",
            duration_seconds=150,
            document_profile={"target_duration_seconds": 150, "recommended_format": "explainer"},
            timeout_seconds=5,
            allow_local_fallback=False,
        )
    finally:
        notebooklm_pkg.NotebookLMVideoProvider = monkeypatch_provider

    assert result["state"] == "ready"
    assert captured["target"] == 150
    assert captured["profile_target"] == 150


def test_engine_report_redacts_secret_tokens(tmp_path: Path) -> None:
    from voice_flow.video_flow_engine.engine import _reporter

    seen: list[dict] = []
    report = _reporter(seen.append, None, {})
    report(10, "Planning provider failed: sk-abcdef1234567890 leaked", "failed")
    assert "sk-abcdef1234567890" not in seen[0]["message"]
    assert "[redacted]" in seen[0]["message"]

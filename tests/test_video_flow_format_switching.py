"""Comprehensive tests for Video Flow format switching and auto-adaptive tier selection.

Verifies:
1. Auto-adaptive preference correctly chooses format based on content density:
   - <150 words -> 'short' (30-45s)
   - 150-500 words -> 'brief' (60-90s)
   - 500-2500 words -> 'explainer' (90-210s)
   - 2500+ words -> 'cinematic' (240-300s max ceiling)
   - Never leaves format as 'auto'.
2. Explicit format preferences (brief, short, explainer, cinematic):
   - Duration properly scales within that format's constraints even on large documents.
   - Directive and chapter breakdown align with the requested format.
3. VideoFlowEngine._resolve_auto_format:
   - Resolves 'auto' via document_profile recommended_format.
   - Resolves 'auto' via target duration tiers (short <= 45s, brief <= 120s, explainer <= 240s, cinematic > 240s).
   - Preserves explicit formats ('brief', 'short', 'explainer', 'cinematic').
4. NotebookLMVideoProvider.generate:
   - Aligns document profile directive and chapter breakdown when request.format differs from initial profile.
   - Ensures cinematic constraint is applied only to cinematic format.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from voice_flow.video_flow_engine.engine import VideoFlowEngine
from voice_flow.video_flow_engine.notebooklm import (
    VIDEO_FORMATS,
    VideoRequest,
    analyze_document_source,
    build_adaptive_prompt,
)
from voice_flow.video_flow_engine.notebooklm.provider import NotebookLMVideoProvider


def _make_text(word_count: int) -> str:
    words = ["insight", "structure", "clarity", "narrative", "flow", "presentation", "analysis", "evidence"]
    return " ".join(words[i % len(words)] for i in range(word_count))


class TestVideoFlowFormatSelection:
    """Test format switching and auto-adaptive resolution."""

    def test_auto_adaptive_never_returns_auto(self):
        """Auto format request must always resolve to a concrete VIDEO_FORMATS member."""
        for words in [50, 200, 800, 1800, 3500]:
            text = _make_text(words)
            profile = analyze_document_source(text, requested_format="auto")
            assert profile.recommended_format in VIDEO_FORMATS
            assert profile.recommended_format != "auto"

    def test_auto_adaptive_tiers(self):
        """Verify each word count tier resolves to the expected auto format."""
        # Tier 1: < 150 words -> short (30-45s)
        p_short = analyze_document_source(_make_text(80))
        assert p_short.recommended_format == "short"
        assert 30 <= p_short.target_duration_seconds <= 45
        assert p_short.pacing_style == "brisk"

        # Tier 2: 150-500 words -> brief (60-90s)
        p_brief = analyze_document_source(_make_text(300))
        assert p_brief.recommended_format == "brief"
        assert 60 <= p_brief.target_duration_seconds <= 90
        assert p_brief.pacing_style == "brisk"

        # Tier 3: 500-1200 words -> explainer (90-150s)
        p_exp1 = analyze_document_source(_make_text(800))
        assert p_exp1.recommended_format == "explainer"
        assert 90 <= p_exp1.target_duration_seconds <= 150
        assert p_exp1.pacing_style == "balanced"

        # Tier 4: 1200-2500 words -> explainer (150-210s)
        p_exp2 = analyze_document_source(_make_text(1800))
        assert p_exp2.recommended_format == "explainer"
        assert 150 <= p_exp2.target_duration_seconds <= 210
        assert p_exp2.pacing_style == "measured"

        # Tier 5: 2500+ words -> cinematic (240-300s)
        p_cine = analyze_document_source(_make_text(3200))
        assert p_cine.recommended_format == "cinematic"
        assert 240 <= p_cine.target_duration_seconds <= 300
        assert p_cine.pacing_style == "measured"

    def test_explicit_brief_on_large_document(self):
        """Selecting 'brief' on a 3000-word document must produce brief duration (<= 120s), not cinematic."""
        text = _make_text(3000)
        profile = analyze_document_source(text, requested_format="brief")
        assert profile.recommended_format == "brief"
        assert profile.target_duration_seconds <= 120
        assert "brief overview" in profile.adaptive_prompt_directive
        assert "cinematic visual overview" not in profile.adaptive_prompt_directive

    def test_explicit_short_on_large_document(self):
        """Selecting 'short' on a 3000-word document must produce short duration (<= 150s), not cinematic."""
        text = _make_text(3000)
        profile = analyze_document_source(text, requested_format="short")
        assert profile.recommended_format == "short"
        assert profile.target_duration_seconds <= 150
        assert "vertical short video" in profile.adaptive_prompt_directive
        assert "cinematic visual overview" not in profile.adaptive_prompt_directive

    def test_explicit_explainer_on_large_document(self):
        """Selecting 'explainer' on a 3000-word document must produce explainer duration (<= 240s), not cinematic."""
        text = _make_text(3000)
        profile = analyze_document_source(text, requested_format="explainer")
        assert profile.recommended_format == "explainer"
        assert profile.target_duration_seconds <= 240
        assert "visual explainer" in profile.adaptive_prompt_directive
        assert "cinematic visual overview" not in profile.adaptive_prompt_directive

    def test_explicit_cinematic_on_short_document(self):
        """Selecting 'cinematic' on a short document must produce cinematic format and directive."""
        text = _make_text(100)
        profile = analyze_document_source(text, requested_format="cinematic")
        assert profile.recommended_format == "cinematic"
        assert "cinematic visual overview" in profile.adaptive_prompt_directive
        assert "STRICT DURATION CONSTRAINT" in profile.adaptive_prompt_directive


class TestEngineResolveAutoFormat:
    """Test VideoFlowEngine._resolve_auto_format."""

    def test_preserves_concrete_formats(self):
        for fmt in ["brief", "short", "explainer", "cinematic"]:
            assert VideoFlowEngine._resolve_auto_format({"format": fmt}) == fmt
            assert VideoFlowEngine._resolve_auto_format({"format": fmt.upper()}) == fmt

    def test_resolves_via_document_profile(self):
        for fmt in ["brief", "short", "explainer", "cinematic"]:
            res = VideoFlowEngine._resolve_auto_format({
                "format": "auto",
                "document_profile": {"recommended_format": fmt, "target_duration_seconds": 290},
            })
            assert res == fmt

    def test_resolves_via_duration_seconds_tiers(self):
        # Short tier (<= 45s)
        assert VideoFlowEngine._resolve_auto_format({"format": "auto", "duration_seconds": 30}) == "short"
        assert VideoFlowEngine._resolve_auto_format({"format": "auto", "duration_seconds": 45}) == "short"

        # Brief tier (<= 120s)
        assert VideoFlowEngine._resolve_auto_format({"format": "auto", "duration_seconds": 60}) == "brief"
        assert VideoFlowEngine._resolve_auto_format({"format": "auto", "duration_seconds": 120}) == "brief"

        # Explainer tier (<= 240s)
        assert VideoFlowEngine._resolve_auto_format({"format": "auto", "duration_seconds": 150}) == "explainer"
        assert VideoFlowEngine._resolve_auto_format({"format": "auto", "duration_seconds": 240}) == "explainer"

        # Cinematic tier (> 240s)
        assert VideoFlowEngine._resolve_auto_format({"format": "auto", "duration_seconds": 250}) == "cinematic"
        assert VideoFlowEngine._resolve_auto_format({"format": "auto", "duration_seconds": 300}) == "cinematic"

    def test_fallback_defaults_to_explainer(self):
        assert VideoFlowEngine._resolve_auto_format({}) == "explainer"
        assert VideoFlowEngine._resolve_auto_format({"format": "auto"}) == "explainer"


class TestProviderDirectiveAlignment:
    """Test NotebookLMVideoProvider.generate directive alignment."""

    def test_generate_aligns_directive_when_format_switched_to_brief(self, tmp_path):
        """When doc_profile was computed as cinematic, switching request.format to brief must align directive."""
        profile = analyze_document_source(_make_text(3000), requested_format="cinematic")
        assert profile.recommended_format == "cinematic"
        assert "cinematic visual overview" in profile.adaptive_prompt_directive

        provider = NotebookLMVideoProvider(workdir=tmp_path)
        from voice_flow.video_flow_engine.notebooklm import AuthStatus, NotebookRef, SourceRef
        provider.check_auth = MagicMock(return_value=AuthStatus("authenticated", "default", authenticated=True))
        provider.create_notebook = MagicMock(return_value=NotebookRef("nb-123", "Test Notebook"))
        provider.add_source = MagicMock(return_value=SourceRef("src-123", "Source Title", "ready"))
        provider.add_source_text = MagicMock(return_value=SourceRef("src-123", "Source Title", "ready"))
        provider.wait_for_source = MagicMock()
        provider.start_video = MagicMock(return_value=("task-123", None))
        provider.wait_for_artifact = MagicMock(return_value=("http://example.com/video.mp4", None))
        provider.download_video = MagicMock(return_value=tmp_path / "video.mp4")
        (tmp_path / "video.mp4").write_bytes(b"dummy mp4 content")

        with patch("voice_flow.video_flow_engine.notebooklm.provider.probe_media_file") as mock_probe:
            mock_probe.return_value = {"duration_seconds": 60.0}

            req = VideoRequest(
                title="Test Video",
                prompt="Explain the key concepts",
                output_path=tmp_path / "out.mp4",
                source_text=_make_text(3000),
                format="brief",
                document_profile=profile.to_dict(),
            )
            artifact = provider.generate(req)

            # Check that provider.start_video was called with brief format and aligned directive
            call_req = provider.start_video.call_args[0][0]
            assert call_req.format == "brief"
            assert "brief overview" in call_req.document_profile["adaptive_prompt_directive"]
            assert "cinematic visual overview" not in call_req.document_profile["adaptive_prompt_directive"]
            assert call_req.document_profile["recommended_format"] == "brief"

    def test_generate_preserves_file_upload_sections_and_depth_directives(self, tmp_path):
        """When source_file is provided and source_text is empty, provider extracts sections and preserves content depth."""
        doc_path = tmp_path / "architecture.md"
        doc_path.write_text(
            "# System Architecture\n"
            "The cluster operates across three distinct geographic regions with active replication.\n\n"
            "# Deployment Protocol\n"
            "All service microservices are packaged in container images and managed via Kubernetes.\n",
            encoding="utf-8",
        )

        provider = NotebookLMVideoProvider(workdir=tmp_path)
        from voice_flow.video_flow_engine.notebooklm import AuthStatus, NotebookRef, SourceRef
        provider.check_auth = MagicMock(return_value=AuthStatus("authenticated", "default", authenticated=True))
        provider.create_notebook = MagicMock(return_value=NotebookRef("nb-123", "Test Notebook"))
        provider.add_source = MagicMock(return_value=SourceRef("src-123", "Source Title", "ready"))
        provider.wait_for_source = MagicMock()
        provider.start_video = MagicMock(return_value=("task-123", None))
        provider.wait_for_artifact = MagicMock(return_value=("http://example.com/video.mp4", None))
        provider.download_video = MagicMock(return_value=tmp_path / "video.mp4")
        (tmp_path / "video.mp4").write_bytes(b"dummy mp4 content")

        with patch("voice_flow.video_flow_engine.notebooklm.provider.probe_media_file") as mock_probe:
            mock_probe.return_value = {"duration_seconds": 60.0}

            req = VideoRequest(
                title="Cloud Architecture",
                prompt="Produce an overview",
                output_path=tmp_path / "out.mp4",
                source_file=str(doc_path),
                source_text="",
                format="explainer",
            )
            provider.generate(req)

            call_req = provider.start_video.call_args[0][0]
            # Prompt must contain substantive depth instructions and extracted sections
            assert "[Content Depth & Key Points]" in call_req.prompt
            assert "1. System Architecture" in call_req.prompt
            assert "2. Deployment Protocol" in call_req.prompt
            assert "cluster operates across three" in call_req.prompt
            assert "CONTENT RETENTION & DEPTH REQUIREMENT" in call_req.prompt


class TestApiAnalyzeSource:
    """Test /api/video-flow/analyze-source endpoint handles requested_format and auto tiers."""

    @pytest.fixture(autouse=True)
    def _setup_api_server(self, monkeypatch, tmp_path):
        import json
        import urllib.request
        from http.server import ThreadingHTTPServer
        from voice_flow.gui import api_server

        monkeypatch.setattr(api_server, "data_dir", lambda: tmp_path)
        server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.base_url = f"http://127.0.0.1:{server.server_port}"
        yield
        server.shutdown()
        server.server_close()

    def _post(self, path: str, body: dict) -> dict:
        import json
        import urllib.request
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_analyze_source_auto_tiers(self):
        # Snippet (< 150 words) -> short
        res_short = self._post("/api/video-flow/analyze-source", {"source_text": _make_text(80)})
        assert res_short["success"] is True
        assert res_short["resolved_format"] == "short"
        assert 30 <= res_short["target_seconds"] <= 45

        # 1-2 pages (150-500 words) -> brief
        res_brief = self._post("/api/video-flow/analyze-source", {"source_text": _make_text(300)})
        assert res_brief["success"] is True
        assert res_brief["resolved_format"] == "brief"
        assert 60 <= res_brief["target_seconds"] <= 90

        # Dense (> 2500 words) -> cinematic
        res_cine = self._post("/api/video-flow/analyze-source", {"source_text": _make_text(3000)})
        assert res_cine["success"] is True
        assert res_cine["resolved_format"] == "cinematic"
        assert 240 <= res_cine["target_seconds"] <= 300

    def test_analyze_source_explicit_format(self):
        # Request brief on 3000-word text -> target_seconds must be brief (<= 120s), not cinematic
        res_brief = self._post("/api/video-flow/analyze-source", {
            "source_text": _make_text(3000),
            "requested_format": "brief",
        })
        assert res_brief["success"] is True
        assert res_brief["resolved_format"] == "brief"
        assert res_brief["target_seconds"] <= 120

        # Request short on 3000-word text -> target_seconds must be short (<= 150s)
        res_short = self._post("/api/video-flow/analyze-source", {
            "source_text": _make_text(3000),
            "requested_format": "short",
        })
        assert res_short["success"] is True
        assert res_short["resolved_format"] == "short"
        assert res_short["target_seconds"] <= 150

    def test_analyze_source_large_technical_returns_explainer(self):
        tech_text = (
            "# Developer API Guide & Setup\n\n"
            "```python\ndef run_api(): pass\n```\n"
            "POST /v1/gateway/tokens\n"
            "Step 1: configure SDK credentials.\n\n"
        ) + " ".join(["api", "endpoint", "parameter", "schema", "token"] * 600)
        res = self._post("/api/video-flow/analyze-source", {
            "source_text": tech_text,
            "requested_format": "auto",
        })
        assert res["success"] is True
        assert res["resolved_format"] == "explainer"
        assert res["content_type"] == "technical"
        assert 180 <= res["target_seconds"] <= 240

    def test_analyze_source_large_meeting_returns_brief(self):
        meeting_text = (
            "# Executive Meeting Minutes & Action Items\n\n"
            "**Attendees:** Alice, Bob\n"
            "## Agenda\n* Quarterly Goals\n* Deployment Roadmap\n\n"
            "## Action Items\n* [ ] Task 1\n* [ ] Task 2\n\n"
        ) + " ".join(["meeting", "summary", "decision", "action", "item"] * 600)
        res = self._post("/api/video-flow/analyze-source", {
            "source_text": meeting_text,
            "requested_format": "auto",
        })
        assert res["success"] is True
        assert res["resolved_format"] == "brief"
        assert res["content_type"] == "summary"
        assert res["target_seconds"] <= 120

    def test_analyze_source_with_task_context(self):
        res = self._post("/api/video-flow/analyze-source", {
            "source_text": _make_text(3000),
            "requested_format": "auto",
            "task": "REST API Technical Documentation Guide",
        })
        assert res["success"] is True
        assert res["resolved_format"] == "explainer"
        assert res["content_type"] == "technical"

    def test_analyze_source_returns_sections_and_handles_source_file(self, tmp_path):
        doc = tmp_path / "overview.md"
        doc.write_text(
            "# Introduction\nSystem initialization and architecture.\n\n# Benchmarks\nLatency tests show 2x speedup.\n",
            encoding="utf-8",
        )
        res = self._post("/api/video-flow/analyze-source", {
            "source_text": "",
            "source_path": str(doc),
            "requested_format": "auto",
        })
        assert res["success"] is True
        assert res["section_count"] == 2
        assert "sections" in res
        assert len(res["sections"]) == 2
        assert res["sections"][0]["title"] == "Introduction"
        assert res["sections"][1]["title"] == "Benchmarks"


class TestCode2VideoFormatAdaptation:
    """Test Code2VideoRunner adapts duration, prompt guidance, and storyboard to format."""

    def test_request_context_contains_format_guidance(self):
        from voice_flow.video_flow_engine.code2video_runner import _request_context

        c_short = _request_context({"format": "short"})
        assert "9:16" in c_short
        assert "Short" in c_short

        c_brief = _request_context({"format": "brief"})
        assert "Brief" in c_brief
        assert "executive overview" in c_brief

        c_exp = _request_context({"format": "explainer"})
        assert "Explainer" in c_exp

        c_cine = _request_context({"format": "cinematic"})
        assert "Cinematic" in c_cine
        assert "documentary style" in c_cine

    def test_deterministic_storyboard_scales_section_counts(self):
        from voice_flow.video_flow_engine.code2video_runner import _deterministic_storyboard

        lines_text = "\n".join([f"Key insight and topic point {i} for the narrative video." for i in range(20)])

        sb_short = _deterministic_storyboard(lines_text, 45.0, {"format": "short"})
        assert 2 <= len(sb_short["sections"]) <= 4

        sb_brief = _deterministic_storyboard(lines_text, 75.0, {"format": "brief"})
        assert 2 <= len(sb_brief["sections"]) <= 5

        sb_exp = _deterministic_storyboard(lines_text, 150.0, {"format": "explainer"})
        assert 3 <= len(sb_exp["sections"]) <= 8

        sb_cine = _deterministic_storyboard(lines_text, 240.0, {"format": "cinematic"})
        assert 4 <= len(sb_cine["sections"]) <= 10

    def test_plan_default_duration_by_format(self, tmp_path):
        from voice_flow.video_flow_engine.code2video_runner import Code2VideoRunner

        runner = Code2VideoRunner(gateway=lambda prompt, **kw: "{}")
        # Test short default duration (45s)
        sb_short = runner.plan("Test topic content with multiple lines", project_dir=tmp_path, format="short", allow_fallback=True)
        assert sb_short["sections"]

        # Test cinematic default duration (240s)
        sb_cine = runner.plan("Test topic content with multiple lines", project_dir=tmp_path, format="cinematic", allow_fallback=True)
        assert sb_cine["sections"]

        # Test auto adaptation on technical content -> adapts to explainer (150s default)
        tech_text = (
            "# API Reference & Architecture Guide\n\n"
            "```python\ndef run_api(): pass\n```\n"
            "POST /v1/tokens\n"
        ) + " ".join(["api", "endpoint", "parameter"] * 100)
        sb_auto = runner.plan(tech_text, project_dir=tmp_path, format="auto", allow_fallback=True)
        assert sb_auto["sections"]


class TestEngineResolveAutoFormatEdgeCases:
    """Test edge cases in VideoFlowEngine._resolve_auto_format."""

    def test_requested_format_overrides_format_auto(self):
        for fmt in ["brief", "short", "explainer", "cinematic"]:
            assert VideoFlowEngine._resolve_auto_format({"format": "auto", "requested_format": fmt}) == fmt

    def test_resolve_via_source_file_word_count(self, tmp_path):
        f_short = tmp_path / "short.txt"
        f_short.write_text(_make_text(80), encoding="utf-8")
        assert VideoFlowEngine._resolve_auto_format({"format": "auto", "source_file": str(f_short)}) == "short"

        f_cine = tmp_path / "cine.txt"
        f_cine.write_text(_make_text(3000), encoding="utf-8")
        assert VideoFlowEngine._resolve_auto_format({"format": "auto", "source_file": str(f_cine)}) == "cinematic"

    def test_resolve_large_technical_source_file_to_explainer(self, tmp_path):
        f_tech = tmp_path / "tech.txt"
        content = (
            "# System Architecture & API Manual\n\n"
            "```python\ndef start(): pass\n```\n"
            "POST /v1/services/deploy\n"
            "Step 1: Install SDK.\n"
        ) + " ".join(["api", "endpoint", "parameter", "schema", "config"] * 600)
        f_tech.write_text(content, encoding="utf-8")
        assert VideoFlowEngine._resolve_auto_format({"format": "auto", "source_file": str(f_tech)}) == "explainer"

    def test_resolve_large_meeting_source_file_to_brief(self, tmp_path):
        f_meeting = tmp_path / "meeting.txt"
        content = (
            "# Executive Meeting Minutes\n\n"
            "## Attendees\n* Alice\n* Bob\n\n"
            "## Action Items\n* [ ] Task 1\n"
        ) + " ".join(["meeting", "summary", "decision", "action", "item"] * 600)
        f_meeting.write_text(content, encoding="utf-8")
        assert VideoFlowEngine._resolve_auto_format({"format": "auto", "source_file": str(f_meeting)}) == "brief"

    def test_resolve_large_doc_with_task_override(self):
        text = _make_text(3000)
        # Task context explicitly specifies technical API guide -> explainer
        assert VideoFlowEngine._resolve_auto_format({"format": "auto", "source_text": text, "task": "Technical API Guide"}) == "explainer"
        # Task context explicitly specifies meeting summary -> brief
        assert VideoFlowEngine._resolve_auto_format({"format": "auto", "source_text": text, "task": "Meeting Summary"}) == "brief"
        # Explicit format selection must not be overridden by task
        assert VideoFlowEngine._resolve_auto_format({"format": "cinematic", "source_text": text, "task": "Meeting Summary"}) == "cinematic"
        assert VideoFlowEngine._resolve_auto_format({"format": "brief", "source_text": text, "task": "Technical API Guide"}) == "brief"

    def test_resolve_large_doc_with_duration_seconds_does_not_override_technical_content(self):
        """Passing duration_seconds > 240 must NOT force a technical document to 'cinematic'."""
        tech_text = "This document describes the API parameters, protocol endpoints, and JSON payload schemas for backend data integration. " * 200
        # Passing duration_seconds=270 with format='auto' must inspect the source_text and return 'explainer'
        assert VideoFlowEngine._resolve_auto_format({
            "format": "auto",
            "source_text": tech_text,
            "duration_seconds": 270,
        }) == "explainer"

    def test_resolve_large_educational_source_file_to_explainer(self, tmp_path):
        """Educational course syllabus file resolves to 'explainer'."""
        f_edu = tmp_path / "course.txt"
        content = (
            "# Course Syllabus: Quantum Mechanics\n\n"
            "## Learning Objectives\n* Wave functions\n* Schrodinger equation\n"
        ) + " ".join(["lesson", "module", "lecture", "curriculum", "syllabus"] * 600)
        f_edu.write_text(content, encoding="utf-8")
        assert VideoFlowEngine._resolve_auto_format({"format": "auto", "source_file": str(f_edu)}) == "explainer"


class TestNotebookLMProviderVisualStyle:
    """Test visual style directives are properly injected into prompts for cinematic and short."""

    def test_cinematic_with_style_injects_visual_style(self, tmp_path):
        provider = NotebookLMVideoProvider(workdir=tmp_path)
        from voice_flow.video_flow_engine.notebooklm import AuthStatus, NotebookRef, SourceRef
        provider.check_auth = MagicMock(return_value=AuthStatus("authenticated", "default", authenticated=True))
        provider.create_notebook = MagicMock(return_value=NotebookRef("nb-123", "Test Notebook"))
        provider.add_source = MagicMock(return_value=SourceRef("src-123", "Source Title", "ready"))
        provider.add_source_text = MagicMock(return_value=SourceRef("src-123", "Source Title", "ready"))
        provider.wait_for_source = MagicMock()
        provider.start_video = MagicMock(return_value=("task-123", None))
        provider.wait_for_artifact = MagicMock(return_value=("http://example.com/video.mp4", None))
        provider.download_video = MagicMock(return_value=tmp_path / "video.mp4")
        (tmp_path / "video.mp4").write_bytes(b"dummy mp4 content")

        with patch("voice_flow.video_flow_engine.notebooklm.provider.probe_media_file") as mock_probe:
            mock_probe.return_value = {"duration_seconds": 240.0}

            req = VideoRequest(
                title="Cinematic Style Test",
                prompt="Explain the core narrative",
                output_path=tmp_path / "out.mp4",
                source_text=_make_text(3000),
                format="cinematic",
                style="watercolor",
            )
            provider.generate(req)

            call_req = provider.start_video.call_args[0][0]
            assert "[Visual Style]" in call_req.prompt
            assert "watercolor visual aesthetic" in call_req.prompt



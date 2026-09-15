"""Unit tests for the Document Profiler and Adaptive Engine for NotebookLM Video Flow."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from voice_flow.video_flow_engine.notebooklm import (
    DocumentProfile,
    analyze_document_source,
    build_adaptive_prompt,
)
from voice_flow.video_flow_engine.notebooklm.document_profiler import (
    MAX_DURATION_SECONDS,
    MIN_DURATION_SECONDS,
    WORDS_PER_PAGE,
    compute_format_duration,
    format_duration_display,
    generate_cinematic_pacing_directive,
)


def _generate_text(word_count: int) -> str:
    """Generate deterministic dummy text with an exact word count."""
    sample_words = [
        "quantum", "computing", "transforms", "data", "processing",
        "through", "superposition", "entanglement", "and", "novel",
        "algorithmic", "breakthroughs", "across", "distributed", "networks",
    ]
    words = [sample_words[i % len(sample_words)] for i in range(word_count)]
    return " ".join(words)


class TestDocumentProfiler:
    """Test suite for DocumentProfile dataclass and analyze_document_source logic."""

    def test_one_paragraph_document(self):
        """Test small document / snippet / tweet (< 150 words). Target: 30-45s, brisk, short."""
        text = _generate_text(80)  # 1 paragraph
        profile = analyze_document_source(text)

        assert profile.word_count == 80
        assert profile.char_count == len(text)
        assert profile.estimated_pages == round(80 / WORDS_PER_PAGE, 2)
        assert profile.estimated_reading_minutes == 0.4
        assert 30 <= profile.target_duration_seconds <= 45
        assert profile.target_duration_seconds <= MAX_DURATION_SECONDS
        assert profile.recommended_format == "short"
        assert profile.pacing_style == "brisk"
        assert profile.target_duration_display.startswith("~")
        assert profile.target_duration_display.endswith("s")
        assert "(Max ceiling)" not in profile.target_duration_display
        assert "STRICT DURATION CONSTRAINT" in profile.adaptive_prompt_directive
        assert "brisk" in profile.adaptive_prompt_directive
        assert len(profile.chapter_breakdown) >= 2

    def test_one_page_document(self):
        """Test ~1 page document (~275 words). Target: 60-90s (~1-1.5 min), brief, brisk."""
        text = _generate_text(275)
        profile = analyze_document_source(text)

        assert profile.word_count == 275
        assert profile.estimated_pages == 1.0
        assert 60 <= profile.target_duration_seconds <= 90
        assert profile.target_duration_seconds <= MAX_DURATION_SECONDS
        assert profile.recommended_format == "brief"
        assert profile.pacing_style == "brisk"
        assert "~1m" in profile.target_duration_display
        assert "(Max ceiling)" not in profile.target_duration_display
        assert "brief" in profile.recommended_format
        assert "Chapter 1:" in profile.adaptive_prompt_directive

    def test_two_pages_document(self):
        """Test ~2 pages document (550 words, 500-1200 words tier). Target: 90-150s (1.5-2.5 min), explainer, balanced."""
        text = _generate_text(550)
        profile = analyze_document_source(text)

        assert profile.word_count == 550
        assert profile.estimated_pages == 2.0
        assert 90 <= profile.target_duration_seconds <= 150
        assert profile.target_duration_seconds <= MAX_DURATION_SECONDS
        assert profile.recommended_format == "explainer"
        assert profile.pacing_style == "balanced"
        assert "~1m" in profile.target_duration_display or "~2m" in profile.target_duration_display
        assert "(Max ceiling)" not in profile.target_duration_display
        assert "balanced" in profile.adaptive_prompt_directive
        assert len(profile.chapter_breakdown) >= 3

    def test_five_to_eight_pages_document(self):
        """Test ~6 pages document (1650 words, 1200-2500 words tier). Target: 150-210s, explainer, measured."""
        text = _generate_text(1650)
        profile = analyze_document_source(text)

        assert profile.word_count == 1650
        assert profile.estimated_pages == 6.0
        assert 150 <= profile.target_duration_seconds <= 210
        assert profile.target_duration_seconds <= MAX_DURATION_SECONDS
        assert profile.recommended_format == "explainer"
        assert profile.pacing_style == "measured"
        assert "(Max ceiling)" not in profile.target_duration_display
        assert "measured" in profile.adaptive_prompt_directive

    def test_ten_pages_document(self):
        """Test ~10 pages document (2750 words, 2500+ words tier). Target: 240-300s (max 4-5 min), cinematic, measured."""
        text = _generate_text(2750)
        profile = analyze_document_source(text)

        assert profile.word_count == 2750
        assert profile.estimated_pages == 10.0
        assert 240 <= profile.target_duration_seconds <= 300
        assert profile.target_duration_seconds <= MAX_DURATION_SECONDS
        assert profile.recommended_format == "cinematic"
        assert profile.pacing_style == "measured"
        assert "(Max ceiling)" in profile.target_duration_display
        assert "~4m" in profile.target_duration_display or "~5m" in profile.target_duration_display

    def test_cinematic_format_strict_5min_ceiling(self):
        """Test dense document (10,000 words). Enforces hard 300s (5 min) ceiling and cinematic directive."""
        text = _generate_text(10_000)
        profile = analyze_document_source(text, requested_format="cinematic")

        # Hard ceiling check: MUST NOT exceed 300 seconds (5 minutes) under any circumstances
        assert profile.target_duration_seconds == 300
        assert profile.target_duration_display == "~5m 00s (Max ceiling)"
        assert profile.recommended_format == "cinematic"
        assert profile.pacing_style == "measured"

        # Check exact required cinematic pacing directive sentence
        expected_directive_start = (
            "Generate a punchy, high-production cinematic visual overview. "
            "STRICT DURATION CONSTRAINT: Keep the final video tightly focused at approximately "
            "~5m 00s (Max ceiling) (maximum 5 minutes). Pacing: measured. Avoid filler scenes."
        )
        assert profile.adaptive_prompt_directive.startswith(expected_directive_start)
        assert profile.cinematic_pacing_directive == expected_directive_start

    def test_cinematic_format_requested_on_short_document(self):
        """Test requested_format='cinematic' on a short document."""
        text = _generate_text(100)
        profile = analyze_document_source(text, requested_format="cinematic")

        assert profile.recommended_format == "cinematic"
        assert profile.target_duration_seconds <= 300
        assert "cinematic visual overview" in profile.adaptive_prompt_directive
        assert "STRICT DURATION CONSTRAINT" in profile.adaptive_prompt_directive
        assert profile.cinematic_pacing_directive.startswith("Generate a punchy, high-production cinematic visual overview.")

    def test_target_duration_override_clamping(self):
        """Test that explicit target_duration_seconds is clamped to [30, 300]."""
        text = _generate_text(300)

        # Clamping above 300 seconds (5 minutes)
        profile_high = analyze_document_source(text, target_duration_seconds=900)
        assert profile_high.target_duration_seconds == 300
        assert profile_high.target_duration_display == "~5m 00s (Max ceiling)"

        # Clamping below 30 seconds
        profile_low = analyze_document_source(text, target_duration_seconds=5)
        assert profile_low.target_duration_seconds == 30
        assert profile_low.target_duration_display == "~30s"

    def test_analyze_from_file_path(self):
        """Test analyze_document_source loading from a file path."""
        content = _generate_text(400)
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "source_document.txt"
            file_path.write_text(content, encoding="utf-8")

            # Test passing Path object
            profile1 = analyze_document_source(file_path)
            assert profile1.word_count == 400
            assert profile1.recommended_format == "brief"

            # Test passing str path via source_path keyword
            profile2 = analyze_document_source(source_path=str(file_path))
            assert profile2.word_count == 400
            assert profile2.recommended_format == "brief"

    def test_empty_document_handling(self):
        """Test handling of empty text or whitespace."""
        profile = analyze_document_source("")
        assert profile.word_count == 0
        assert profile.char_count == 0
        assert profile.estimated_pages == 0.0
        assert profile.estimated_reading_minutes == 0.0
        assert profile.target_duration_seconds == MIN_DURATION_SECONDS
        assert profile.target_duration_display == "~30s"
        assert profile.pacing_style == "brisk"
        assert profile.recommended_format == "short"

    def test_build_adaptive_prompt(self):
        """Test build_adaptive_prompt composing user prompt with adaptive directives."""
        profile = analyze_document_source(_generate_text(275), requested_format="brief")
        base_prompt = "Create an executive summary video for the board."

        prompt = build_adaptive_prompt(base_prompt, profile)
        assert base_prompt in prompt
        assert "[Adaptive Video Directives]" in prompt
        assert profile.adaptive_prompt_directive in prompt
        assert profile.target_duration_display in prompt

        # Test prompt with explicit format override to cinematic
        cinematic_prompt = build_adaptive_prompt(base_prompt, profile, requested_format="cinematic")
        assert "cinematic visual overview" in cinematic_prompt
        assert "STRICT DURATION CONSTRAINT" in cinematic_prompt

        # Test empty base prompt returns the directive
        directive_only = build_adaptive_prompt("", profile)
        assert directive_only == profile.adaptive_prompt_directive

        # Test None profile returns base prompt
        assert build_adaptive_prompt(base_prompt, None) == base_prompt

        # Test idempotence (does not double add directive)
        double_prompt = build_adaptive_prompt(prompt, profile)
        assert double_prompt == prompt

    def test_profile_to_dict(self):
        """Test DocumentProfile serialization to dictionary."""
        profile = analyze_document_source(_generate_text(100))
        data = profile.to_dict()

        assert isinstance(data, dict)
        assert data["word_count"] == 100
        assert "target_duration_seconds" in data
        assert "target_duration_display" in data
        assert "recommended_format" in data
        assert "pacing_style" in data
        assert "adaptive_prompt_directive" in data
        assert "chapter_breakdown" in data
        assert "content_type" in data
        assert "detected_intent" in data


class TestTaskAwareAutoAdaptive:
    """Test task and content-aware auto-adaptive selection on large documents (2500+ words)."""

    def _make_technical_doc(self, target_words: int) -> str:
        header = (
            "# API Reference & Architecture Guide\n\n"
            "## Overview\n"
            "This document describes the REST API endpoints and system architecture for the payment service.\n\n"
            "### Authentication\n"
            "All requests must include a valid bearer token in the `Authorization` header.\n\n"
            "```python\n"
            "import requests\n\n"
            "def send_payment(amount: float, recipient_id: str) -> dict:\n"
            "    headers = {'Authorization': 'Bearer test_token'}\n"
            "    payload = {'amount': amount, 'recipient': recipient_id}\n"
            "    response = requests.post('https://api.example.com/v1/payments', json=payload, headers=headers)\n"
            "    return response.json()\n"
            "```\n\n"
            "## Endpoints\n"
            "POST /v1/payments - Create a new transaction.\n"
            "GET /v1/payments/{id} - Retrieve transaction status.\n\n"
            "### Standard Operating Procedure (SOP)\n"
            "Step 1: Install dependencies using `pip install payment-sdk`.\n"
            "Step 2: Configure environment variables.\n"
            "Step 3: Run integration verification test suite.\n\n"
        )
        body_words = [
            "endpoint", "parameter", "payload", "schema", "database", "query",
            "transaction", "status", "response", "token", "configuration",
            "architecture", "microservice", "pipeline", "deployment", "verification",
        ]
        remaining = max(0, target_words - len(header.split()))
        body = " ".join(body_words[i % len(body_words)] for i in range(remaining))
        return f"{header}\n{body}"

    def _make_meeting_summary(self, target_words: int) -> str:
        header = (
            "# Executive Meeting Minutes & Action Items\n\n"
            "**Date:** September 8, 2026\n"
            "**Attendees:** Alice, Bob, Charlie, David\n\n"
            "## Agenda\n"
            "* Q3 Financial Review\n"
            "* Infrastructure Scaling Roadmap\n"
            "* Team Hiring Goals\n\n"
            "## Key Decisions Made\n"
            "* Approved budget for cloud migration.\n"
            "* Prioritized developer documentation improvements.\n"
            "* Scheduled bi-weekly engineering syncs.\n\n"
            "## Action Items\n"
            "* [ ] Alice: Finalize cloud architecture proposal by Friday.\n"
            "* [ ] Bob: Review candidate resumes for lead backend engineer.\n"
            "* [ ] Charlie: Update SOP documentation for deployment pipelines.\n\n"
        )
        body_words = [
            "meeting", "summary", "decision", "action", "item", "discussion",
            "stakeholder", "deadline", "quarterly", "budget", "priority",
            "recap", "sync", "status", "milestone", "review",
        ]
        remaining = max(0, target_words - len(header.split()))
        body = " ".join(body_words[i % len(body_words)] for i in range(remaining))
        return f"{header}\n{body}"

    def _make_historical_documentary(self, target_words: int) -> str:
        header = (
            "# The Fall of the Roman Republic: A Historical Chronicle\n\n"
            "## Prologue: An Empire at the Crossroads\n"
            "In the first century BC, the Mediterranean basin experienced an unprecedented epoch "
            "of transformation. From the hills of Rome to the distant sands of Alexandria, legions "
            "marched across continents, chronicling a saga of ambition, political intrigue, and warfare.\n\n"
            "## The Rise of Julius Caesar\n"
            "The journey began not on the battlefields of Gaul, but in the forum where orators shaped "
            "the fate of millions. Caesar embarked on his legendary expedition, conquering vast territories "
            "and rewriting the political architecture of the ancient world.\n\n"
        )
        body_words = [
            "narrative", "story", "chronicle", "century", "empire", "reign",
            "journey", "historical", "legend", "voyage", "legacy", "drama",
            "prologue", "destiny", "tales", "conquest", "discovered", "traveled",
        ]
        remaining = max(0, target_words - len(header.split()))
        body = " ".join(body_words[i % len(body_words)] for i in range(remaining))
        return f"{header}\n{body}"

    def test_large_technical_doc_auto_picks_explainer(self):
        """A 3000-word technical doc / SOP / API guide must auto-choose 'explainer', not 'cinematic'."""
        text = self._make_technical_doc(3000)
        profile = analyze_document_source(text, requested_format="auto")

        assert profile.word_count >= 2500
        assert profile.recommended_format == "explainer"
        assert profile.content_type == "technical"
        assert 180 <= profile.target_duration_seconds <= 240
        assert profile.pacing_style == "measured"
        assert "visual explainer" in profile.adaptive_prompt_directive
        assert "cinematic visual overview" not in profile.adaptive_prompt_directive

    def test_large_meeting_summary_auto_picks_brief(self):
        """A 2800-word meeting minutes / action items summary must auto-choose 'brief' (<= 120s)."""
        text = self._make_meeting_summary(2800)
        profile = analyze_document_source(text, requested_format="auto")

        assert profile.word_count >= 2500
        assert profile.recommended_format == "brief"
        assert profile.content_type == "summary"
        assert profile.target_duration_seconds <= 120
        assert "brief overview" in profile.adaptive_prompt_directive
        assert "cinematic visual overview" not in profile.adaptive_prompt_directive

    def test_large_documentary_narrative_auto_picks_cinematic(self):
        """A 3000-word narrative / documentary / history document must auto-choose 'cinematic' (<= 300s)."""
        text = self._make_historical_documentary(3000)
        profile = analyze_document_source(text, requested_format="auto")

        assert profile.word_count >= 2500
        assert profile.recommended_format == "cinematic"
        assert profile.content_type == "narrative"
        assert 240 <= profile.target_duration_seconds <= 300
        assert profile.pacing_style == "measured"
        assert "cinematic visual overview" in profile.adaptive_prompt_directive
        assert "STRICT DURATION CONSTRAINT" in profile.adaptive_prompt_directive

    def test_task_context_guides_format_on_generic_text(self):
        """Explicit task context guides auto-adaptive format selection even when text is neutral."""
        text = _generate_text(3000)

        # Task indicates technical API tutorial -> explainer
        p_tech = analyze_document_source(text, requested_format="auto", task="Build a REST API Tutorial and SDK Guide")
        assert p_tech.recommended_format == "explainer"
        assert p_tech.content_type == "technical"

        # Task indicates meeting summary -> brief
        p_sum = analyze_document_source(text, requested_format="auto", task="Quarterly Executive Meeting Minutes Summary")
        assert p_sum.recommended_format == "brief"
        assert p_sum.content_type == "summary"

        # Task indicates documentary -> cinematic
        p_nar = analyze_document_source(text, requested_format="auto", task="Cinematic Historical Documentary on Rome")
        assert p_nar.recommended_format == "cinematic"
        assert p_nar.content_type == "narrative"

    def test_explicit_user_selection_strictly_respected(self):
        """User explicitly choosing a format must never be overridden regardless of document content."""
        tech_text = self._make_technical_doc(3000)

        # User chooses 'brief' on technical doc
        p_brief = analyze_document_source(tech_text, requested_format="brief")
        assert p_brief.recommended_format == "brief"
        assert p_brief.target_duration_seconds <= 120
        assert "brief overview" in p_brief.adaptive_prompt_directive

        # User chooses 'short' on technical doc
        p_short = analyze_document_source(tech_text, requested_format="short")
        assert p_short.recommended_format == "short"
        assert p_short.target_duration_seconds <= 150
        assert "vertical short video" in p_short.adaptive_prompt_directive

        # User chooses 'cinematic' on technical doc
        p_cine = analyze_document_source(tech_text, requested_format="cinematic")
        assert p_cine.recommended_format == "cinematic"
        assert p_cine.target_duration_seconds <= 300
        assert "cinematic visual overview" in p_cine.adaptive_prompt_directive

        # User chooses 'explainer' on meeting summary
        sum_text = self._make_meeting_summary(3000)
        p_exp = analyze_document_source(sum_text, requested_format="explainer")
        assert p_exp.recommended_format == "explainer"
        assert p_exp.target_duration_seconds <= 240
        assert "visual explainer" in p_exp.adaptive_prompt_directive

    def test_direct_classify_document_content(self):
        """Test classify_document_content returns accurate classification dataclass."""
        from voice_flow.video_flow_engine.notebooklm.document_profiler import classify_document_content

        res_tech = classify_document_content(
            "Here is the function:\n```python\ndef test(): pass\n```\nPOST /api/v1/resource",
            title="REST API Documentation",
        )
        assert res_tech.is_technical is True
        assert res_tech.content_type == "technical"
        assert res_tech.detected_intent == "technical_reference"

        res_sum = classify_document_content(
            "# Meeting Minutes\n* Action item 1\n* Action item 2",
            task="Executive meeting notes recap",
        )
        assert res_sum.is_summary is True
        assert res_sum.content_type == "summary"

        res_nar = classify_document_content(
            "Centuries ago, an empire rose from the ashes of war and embarked on a legendary voyage.",
            title="A Historical Journey",
        )
        assert res_nar.is_narrative is True
        assert res_nar.content_type == "narrative"

    def test_large_educational_doc_auto_picks_explainer(self):
        """A 2800-word course curriculum / syllabus / lessons must auto-choose 'explainer' (180-240s)."""
        text = (
            "# Course Syllabus: Advanced Machine Learning\n\n"
            "## Learning Objectives\n"
            "Students will master supervised learning, neural networks, and optimization theory.\n\n"
            + "\n".join(f"### Module {i}: Deep Learning Lesson {i}\nIn this lecture we cover core concepts and prerequisites.\n" for i in range(1, 40))
            + "word " * 2500
        )
        profile = analyze_document_source(text, requested_format="auto")
        assert profile.word_count >= 2500
        assert profile.recommended_format == "explainer"
        assert profile.content_type == "educational"
        assert 180 <= profile.target_duration_seconds <= 240
        assert "visual explainer" in profile.adaptive_prompt_directive
        assert "Learning Objectives" in str(profile.chapter_breakdown)

    def test_educational_doc_with_default_summary_mode_preserves_explainer(self):
        """When mode='summary' (Voice Flow framework default) is present, educational doc must NOT be hijacked to 'brief'."""
        text = (
            "# Lesson 1: Introduction\n# Lesson 2: Core Curriculum\n# Lesson 3: Homework\n# Lesson 4: Exam prep\n"
            + "Educational lecture concepts and syllabus modules. " * 300
        )
        profile = analyze_document_source(text, requested_format="auto", mode="summary")
        assert profile.recommended_format == "explainer"
        assert profile.content_type == "educational"

    def test_story_with_default_summary_mode_preserves_narrative(self):
        """When task='Story of my childhood' and default mode='summary' are passed, story is NOT hijacked to 'summary'."""
        text = (
            "I lived in a small village surrounded by green mountains and clear streams. "
            "Our family had an epic history that spanned over a century of legends and adventures. "
            + "tale journey narrative chronicle " * 700
        )
        profile = analyze_document_source(text, requested_format="auto", task="Story of my childhood", mode="summary")
        assert profile.recommended_format == "cinematic"
        assert profile.content_type == "narrative"

    def test_large_plain_text_technical_api_doc_without_code_fences(self):
        """Plain text technical documentation without code fences (API parameters and schema) auto-picks explainer."""
        text = "This document describes the API parameters, protocol endpoints, and JSON payload schemas for backend data integration. " * 200
        profile = analyze_document_source(text, requested_format="auto")
        assert profile.word_count >= 2500
        assert profile.recommended_format == "explainer"
        assert profile.content_type == "technical"
        assert 180 <= profile.target_duration_seconds <= 240

    def test_large_sop_guidelines_auto_picks_explainer(self):
        """Standard operating procedures with Step 1, Step 2 guidelines auto-pick explainer."""
        text = "Patient Intake Procedure Guidelines\n" + "Step 1: Verify identity. Step 2: Check records. Follow the protocol and procedure guidelines carefully.\n" * 300
        profile = analyze_document_source(text, requested_format="auto")
        assert profile.word_count >= 2500
        assert profile.recommended_format == "explainer"
        assert profile.content_type == "technical"
        assert 180 <= profile.target_duration_seconds <= 240

    def test_explainer_task_intent_auto_picks_explainer(self):
        """Generic large document with explicit 'explainer' task intent auto-picks explainer."""
        text = _generate_text(3000)
        profile = analyze_document_source(text, requested_format="auto", task="Create an in-depth explainer video")
        assert profile.recommended_format == "explainer"
        assert 180 <= profile.target_duration_seconds <= 240

    def test_brief_overview_task_intent_auto_picks_brief(self):
        """Generic large document with explicit 'brief overview' task intent auto-picks brief."""
        text = _generate_text(3000)
        profile = analyze_document_source(text, requested_format="auto", task="Create a brief overview of this document")
        assert profile.recommended_format == "brief"
        assert profile.target_duration_seconds <= 120

    def test_crlf_and_uppercase_headings_and_rich_key_points(self):
        """Verify Windows CRLF formatting and uppercase section titles are parsed with substantive multi-sentence key points."""
        text = (
            "EXECUTIVE SUMMARY\r\n"
            "This initiative modernizes enterprise distributed data pipelines. "
            "It reduces sync latency by 45 percent and optimizes cloud compute overhead significantly.\r\n\r\n"
            "SYSTEM ARCHITECTURE\r\n"
            "The cluster operates across three distinct geographic regions with active replication. "
            "Data ingestion achieves sub-second synchronization across all nodes.\r\n\r\n"
            "DEPLOYMENT PROTOCOL\r\n"
            "All service microservices are packaged in container images and managed via Kubernetes. "
            "Rolling updates guarantee zero user-facing downtime during production rollouts."
        )
        profile = analyze_document_source(text, requested_format="explainer")
        assert profile.section_count == 3
        sec_titles = [s["title"] for s in profile.sections]
        assert "Executive Summary" in sec_titles
        assert "System Architecture" in sec_titles
        assert "Deployment Protocol" in sec_titles

        # Verify substantive multi-sentence key points
        exec_sec = next(s for s in profile.sections if s["title"] == "Executive Summary")
        assert "modernizes enterprise" in exec_sec["key_point"]
        assert "reduces sync latency" in exec_sec["key_point"]

        # Verify content depth directive is present in adaptive prompt
        assert "CONTENT RETENTION & DEPTH REQUIREMENT" in profile.adaptive_prompt_directive
        assert "mechanisms, inner data, evidence, and key takeaways" in profile.adaptive_prompt_directive

    def test_empty_string_text_falls_back_to_source_path(self, tmp_path: Path):
        """Verify passing text='' does not swallow source_path."""
        doc_file = tmp_path / "research_paper.md"
        doc_file.write_text(
            "# Abstract\nThis paper introduces novel scaling heuristics.\n\n# Methodology\nWe benchmarked across 500 samples.",
            encoding="utf-8",
        )
        profile = analyze_document_source(text="", source_path=doc_file)
        assert profile.word_count > 0
        assert profile.section_count == 2
        assert profile.sections[0]["title"] == "Abstract"
        assert profile.sections[1]["title"] == "Methodology"

    def test_single_section_document_chapter_breakdown(self):
        """Verify a single-section document with a meaningful title generates context-specific chapters."""
        text = (
            "# Advanced Neural Decoding\n"
            "Neural decoding translates brain activity into actionable robotic control commands. "
            "Our multi-channel spatial filter extracts spike patterns in real time with 98% accuracy. "
            "The findings show profound implications for prosthetic mobility and motor restoration."
        )
        profile = analyze_document_source(text, requested_format="brief")
        assert len(profile.chapter_breakdown) >= 2
        breakdown_str = " ".join(profile.chapter_breakdown)
        assert "Advanced Neural Decoding" in breakdown_str
        assert "Context & Mechanism" in breakdown_str

    def test_dense_single_page_election_doc_elevates_duration_and_explainer(self):
        """Verify a dense single-page article (~100-250 words) with multiple substantive propositions
        auto-selects explainer and scales to 3-4 minutes rather than being compressed to 30-50s."""
        dense_election_text = (
            "The 2026 presidential election hinges on six critical battleground states where turnout among independent voters has surged by 18 percent.\n\n"
            "Suburban demographics in Pennsylvania have shifted toward moderate fiscal reform due to economic inflation concerns.\n\n"
            "Industrial workforce coalitions in Michigan demand targeted manufacturing tariffs and energy subsidies.\n\n"
            "Rapid Sun Belt migration into Arizona introduces substantial polarization across urban and rural voting blocs.\n\n"
            "Electoral college modeling indicates that a 2 percent swing in the popular vote triggers a decisive shift in 64 electoral votes.\n\n"
            "Voter registration records reveal unprecedented youth registration numbers, fundamentally altering historical turnout paradigms."
        )
        profile = analyze_document_source(dense_election_text)
        assert profile.word_count <= 250
        assert profile.density_score >= 1.4
        assert profile.concept_count >= 4
        assert profile.recommended_format == "explainer"
        assert profile.target_duration_seconds >= 180
        assert profile.target_duration_seconds <= 240
        assert "HIGH INFORMATION DENSITY DIRECTIVE" in profile.adaptive_prompt_directive
        assert len(profile.chapter_breakdown) >= 2

    def test_book_summary_elevates_to_cinematic_and_long_duration(self):
        """Verify a book summary with multiple distinct themes scales to 4-5 minutes cinematic video."""
        book_summary_text = (
            "# Comprehensive Summary of the Book: Principles of Economic Systems\n\n"
            "This executive summary of the entire book breaks down the foundational mechanisms of global trade, currency regulation, and monetary policy.\n\n"
            "Chapter 1 establishes the causal mechanisms behind credit expansion and debt cycles in modern banking architectures.\n\n"
            "Chapter 2 examines historical hyperinflation crises, analyzing how fiscal imbalances trigger systemic asset depreciation.\n\n"
            "Chapter 3 investigates labor market automation, showing how robotics influences wage disparity across industrial sectors.\n\n"
            "Chapter 4 presents empirical modeling of international supply chains, demonstrating how logistical friction results in aggregate price shifts.\n\n"
            "Chapter 5 explores sovereign bond yields and how central bank interest rate decisions regulate capital velocity.\n\n"
            "In conclusion, the author's synthesis provides a unified paradigm for macroeconomic stability in the twenty-first century."
        )
        profile = analyze_document_source(book_summary_text)
        assert profile.density_score >= 1.4
        assert profile.recommended_format == "cinematic"
        assert profile.target_duration_seconds >= 240
        assert profile.target_duration_seconds <= 300
        assert "HIGH INFORMATION DENSITY DIRECTIVE" in profile.adaptive_prompt_directive

    def test_redundant_ten_page_doc_compresses_duration_to_brief(self):
        """Verify a 10-page document where all 10 pages repeat the same paragraph does not inflate
        to 5 minutes, but instead compresses to ~60-120s brief."""
        redundant_para = (
            "This introductory overview introduces the fundamental tenets of cloud computing. "
            "We evaluate serverless functions, container orchestration, distributed datastores, and network latency optimizations. "
            "The system guarantees high availability and fault tolerance across distributed edge locations."
        )
        # 10 pages of 272 words each = 2720 words total
        one_page = " ".join([redundant_para] * 8)
        ten_pages = "\n\n".join([one_page] * 10)

        profile = analyze_document_source(ten_pages)
        assert profile.word_count >= 2500
        assert profile.redundancy_score >= 0.50
        assert profile.density_score <= 0.65
        assert profile.content_value_rating == "low"
        assert profile.recommended_format == "brief"
        assert profile.target_duration_seconds <= 120

    def test_concept_breathing_room_in_compute_format_duration(self):
        """Verify that concept breathing room scales minimum duration per substantive concept."""
        # 5 concepts with default 100 words in explainer format
        dur_standard, _ = compute_format_duration(100, "explainer", num_sections=1, concept_count=0)
        dur_with_concepts, _ = compute_format_duration(100, "explainer", num_sections=1, concept_count=5)
        # 5 concepts * 22s = 110s minimum breathing room
        assert dur_with_concepts >= 110
        assert dur_with_concepts > dur_standard

    def test_concept_driven_chapter_breakdown_for_dense_doc_without_headers(self):
        """Verify dense documents without markdown headers generate structured chapters from concepts."""
        dense_prose = (
            "The monetary authority raised baseline interest rates by 50 basis points to counter inflation. "
            "Commercial lending volume contracted by 12 percent within sixty days across consumer sectors. "
            "Household debt delinquency rates subsequently stabilized following labor market cooling. "
            "Capital reallocation toward sovereign treasury securities yielded record liquidity inflows."
        )
        profile = analyze_document_source(dense_prose, requested_format="explainer")
        assert len(profile.chapter_breakdown) >= 2
        breakdown_text = " ".join(profile.chapter_breakdown)
        assert "Chapter 1:" in breakdown_text
        assert "Chapter 2:" in breakdown_text

    def test_dense_single_page_cinematic_scales_to_five_minutes(self):
        """Verify that a dense single-page document with rich propositions scales to full 5-minute video when cinematic is chosen."""
        dense_text = (
            "The 2026 presidential election hinges on six critical battleground states where turnout among independent voters has surged by 18 percent.\n\n"
            "Suburban demographics in Pennsylvania have shifted toward moderate fiscal reform due to economic inflation concerns.\n\n"
            "Industrial workforce coalitions in Michigan demand targeted manufacturing tariffs and energy subsidies.\n\n"
            "Rapid Sun Belt migration into Arizona introduces substantial polarization across urban and rural voting blocs.\n\n"
            "Electoral college modeling indicates that a 2 percent swing in the popular vote triggers a decisive shift in 64 electoral votes.\n\n"
            "Voter registration records reveal unprecedented youth registration numbers, fundamentally altering historical turnout paradigms."
        )
        profile = analyze_document_source(dense_text, requested_format="cinematic")
        assert profile.word_count <= 250
        assert profile.density_score >= 1.4
        assert profile.recommended_format == "cinematic"
        assert profile.target_duration_seconds >= 240
        assert profile.target_duration_seconds <= 300
        assert "cinematic visual overview" in profile.adaptive_prompt_directive
        assert "HIGH INFORMATION DENSITY DIRECTIVE" in profile.adaptive_prompt_directive

    def test_bullet_list_concept_segmentation(self):
        """Verify that bulleted and numbered proposition lists are segmented into individual substantive concepts."""
        bullet_doc = (
            "# Strategic Election Takeaways\n"
            "- First core finding: Voter turnout in swing precincts grew by 15% due to early voting expansion.\n"
            "- Second core finding: Fiscal policy and inflation indicators drove independent voters away from incumbent coalitions.\n"
            "- Third core finding: Digital campaign ad spend shifted 40% toward regional streaming platforms.\n"
            "- Fourth core finding: Legislative control of the Senate will be determined by three contested races."
        )
        profile = analyze_document_source(bullet_doc, requested_format="explainer")
        assert profile.concept_count >= 4
        assert profile.density_score >= 1.3
        assert len(profile.substantive_concepts) >= 4

    def test_explanatory_expansion_prompt_directive(self):
        """Verify that high density documents inject explicit 'HOW it works' explanatory expansion directives for Google AI."""
        dense_doc = (
            "Quantum error correction stabilizes logical qubits against environmental decoherence. "
            "Surface code lattices employ topological syndrome measurements to detect phase flips without collapsing state. "
            "Cryogenic control electronics execute feedback calibration within 20 nanoseconds to preserve fidelity."
        )
        profile = analyze_document_source(dense_doc, requested_format="explainer")
        assert "HIGH INFORMATION DENSITY DIRECTIVE" in profile.adaptive_prompt_directive
        assert "thoroughly unpack and explain HOW" in profile.adaptive_prompt_directive


class TestDocumentProfilerHardening:
    """Regression tests for profiler hardening (CJK, truncation, tiny docs, formats, floors)."""

    def test_cjk_paragraph_yields_concepts_and_effective(self):
        from voice_flow.video_flow_engine.notebooklm.document_profiler import analyze_content_value

        cjk_text = (
            "量子コンピュータは重ね合わせを利用します。エンタングルメントにより計算能力が向上します。"
            "量子誤り訂正は環境ノイズから論理量子ビットを保護します。"
        )
        profile = analyze_content_value(cjk_text)
        assert profile.concept_count >= 1
        assert profile.effective_word_count > 0

    def test_huge_doc_truncates(self):
        text = "word " * 60000  # ~300k chars
        assert len(text) > 200000
        profile = analyze_document_source(text)
        assert profile.truncated is True
        assert profile.analysis_char_count <= 200000

    def test_tiny_doc_never_rates_high(self):
        tiny = "Quantum entanglement drives superposition because markets collapse today."
        assert len(tiny.split()) == 8
        profile = analyze_document_source(tiny)
        assert profile.content_value_rating not in ("high", "very_high")

    def test_unknown_format_equals_brief(self):
        assert compute_format_duration(200, "mystery_format") == compute_format_duration(200, "brief")

    def test_effective_floor_never_exceeds_word_count(self):
        from voice_flow.video_flow_engine.notebooklm.document_profiler import analyze_content_value

        para = "Cloud computing enables scalable distributed systems for modern applications today."
        wc = len(para.split())
        assert wc < 40  # floor would exceed word_count without the min() guard
        text = f"{para}\n\n{para}"
        profile = analyze_content_value(text)
        assert profile.effective_word_count <= len(text.split())
        assert profile.effective_word_count <= wc * 2


class TestDocumentProfilerReviewFixes:
    """Regression tests for the full read-through review (bugs + security + reliability)."""

    def test_source_path_confined_to_text_suffixes(self, tmp_path: Path):
        from voice_flow.video_flow_engine.notebooklm.document_profiler import MAX_SOURCE_FILE_BYTES  # noqa: F401

        binary = tmp_path / "evil.pdf"
        binary.write_bytes(b"%PDF-1.4 binary-body")
        profile = analyze_document_source(text="Quantum computing transforms data.", source_path=binary)
        assert profile.word_count == 4
        assert profile.analysis_char_count == len("Quantum computing transforms data.")

    def test_source_path_rejects_directories(self, tmp_path: Path):
        profile = analyze_document_source(text="", source_path=tmp_path)
        assert profile.word_count == 0
        assert profile.target_duration_seconds == MIN_DURATION_SECONDS

    def test_directory_positional_source_yields_empty_profile(self, tmp_path: Path):
        profile = analyze_document_source(tmp_path)
        assert profile.word_count == 0
        assert profile.recommended_format == "short"

    def test_missing_source_path_falls_back_to_empty(self, tmp_path: Path):
        profile = analyze_document_source(source_path=tmp_path / "nope.txt")
        assert profile.word_count == 0
        assert profile.target_duration_seconds == MIN_DURATION_SECONDS

    def test_binary_file_with_text_suffix_reads_nothing(self, tmp_path: Path):
        blob = tmp_path / "blob.txt"
        blob.write_bytes(b"\x7fELF\x02\x01" + b"\x00" * 64)
        profile = analyze_document_source(source_path=blob)
        assert profile.word_count == 0
        assert profile.target_duration_seconds == MIN_DURATION_SECONDS

    def test_oversize_source_file_is_not_read(self, tmp_path: Path, monkeypatch):
        import voice_flow.video_flow_engine.notebooklm.document_profiler as dp

        big = tmp_path / "big.txt"
        big.write_bytes(b"word " * 100)
        monkeypatch.setattr(dp, "MAX_SOURCE_FILE_BYTES", 10)
        profile = analyze_document_source(source_path=big)
        assert profile.word_count == 0

    def test_plain_string_path_resolves_to_file(self, tmp_path: Path):
        doc = tmp_path / "paper.txt"
        doc.write_text("Quantum computing transforms data processing.", encoding="utf-8")
        profile = analyze_document_source(str(doc))
        assert profile.word_count == 5

    def test_path_object_positional_source_reads_text_suffix(self, tmp_path: Path):
        doc = tmp_path / "paper.md"
        doc.write_text("# Title\n\nQuantum computing transforms data.", encoding="utf-8")
        profile = analyze_document_source(doc)
        assert profile.word_count > 0
        assert profile.section_count >= 1

    def test_short_text_never_treated_as_file_path(self):
        profile = analyze_document_source("C:\\Windows\\System32\\drivers\\etc\\hosts")
        assert profile.word_count == 1
        assert profile.analysis_char_count == len("C:\\Windows\\System32\\drivers\\etc\\hosts")

    def test_non_string_inputs_do_not_crash(self):
        assert analyze_document_source(None).word_count == 0
        assert analyze_document_source(12345).word_count == 1
        assert analyze_document_source(b"bytes input here").word_count == 3
        from voice_flow.video_flow_engine.notebooklm.document_profiler import (
            analyze_content_value,
            extract_document_sections,
        )

        assert extract_document_sections(None) == []
        assert extract_document_sections(12345)[0]["word_count"] == 1
        assert analyze_content_value(None).concept_count == 0

    def test_non_utf8_bytes_source_surrogates(self):
        profile = analyze_document_source(b"\xff\xfe binary \x00 blob")
        assert profile.word_count >= 0
        assert MIN_DURATION_SECONDS <= profile.target_duration_seconds <= MAX_DURATION_SECONDS

    def test_target_duration_override_rejects_non_numeric(self):
        with pytest.raises(ValueError, match="must be numeric"):
            analyze_document_source("hello world", target_duration_seconds="ninety")  # type: ignore[arg-type]

    def test_unknown_requested_format_normalizes_to_brief(self):
        profile = analyze_document_source("word " * 300, requested_format="mystery_format")
        assert profile.recommended_format == "brief"
        assert "brief overview" in profile.adaptive_prompt_directive
        assert profile.target_duration_seconds <= 120

    def test_explicit_redundancy_score_compresses_without_content_value(self):
        from voice_flow.video_flow_engine.notebooklm.document_profiler import build_adaptive_prompt

        dense, _ = compute_format_duration(800, "explainer", redundancy_score=0.1)
        flat, _ = compute_format_duration(800, "explainer", redundancy_score=0.9)
        assert flat < dense
        # Retarget path also threads it: the adapted prompt carries the
        # explainer directive for the requested format.
        base = analyze_document_source("word " * 800)
        prompt = build_adaptive_prompt("Make a video.", base, requested_format="explainer")
        assert "visual explainer" in prompt

    def test_format_duration_display_rejects_garbage(self):
        assert format_duration_display("abc") == "~30s"  # type: ignore[arg-type]
        assert format_duration_display(None) == "~30s"  # type: ignore[arg-type]
        assert format_duration_display(True) == "~30s"  # type: ignore[arg-type]

    def test_chapter_breakdown_rejects_garbage(self):
        from voice_flow.video_flow_engine.notebooklm.document_profiler import build_chapter_breakdown

        assert len(build_chapter_breakdown("abc")) >= 2  # type: ignore[arg-type]
        assert len(build_chapter_breakdown(None)) >= 2  # type: ignore[arg-type]

    def test_directive_handles_bad_chapters_and_format(self):
        from voice_flow.video_flow_engine.notebooklm.document_profiler import generate_adaptive_directive

        out = generate_adaptive_directive("~60s", "brisk", "mystery", 60, None)  # type: ignore[arg-type]
        assert "brief overview" in out
        out2 = generate_adaptive_directive("~60s", "brisk", "brief", 60, ["ok"], density_score="x", concept_count="y")  # type: ignore[arg-type]
        assert "Chapter" in out2 or "chapters" in out2

    def test_sampler_never_repeats_or_overruns(self):
        from voice_flow.video_flow_engine.notebooklm.document_profiler import (
            _sample_paragraphs,
            _sample_sentences,
        )

        paras = [f"para {i}" for i in range(61)]
        sampled = _sample_paragraphs(paras)
        assert len(sampled) <= 60
        assert len(set(sampled)) == len(sampled)
        assert sampled[:40] == paras[:40]
        sents = [f"sentence number {i} here" for i in range(2501)]
        sampled_s = _sample_sentences(sents)
        assert len(sampled_s) <= 2500
        assert len(set(sampled_s)) == len(sampled_s)

    def test_classification_head_ignores_deep_body(self):
        from voice_flow.video_flow_engine.notebooklm.document_profiler import _classification_head

        head = "# API Guide\n" + "filler text here. " * 3000
        deep = "\n".join(["# Hidden Chapter"] * 500)
        text = head + deep
        out = _classification_head(text)
        assert len(out) <= 50000 + 3000
        assert "Hidden Chapter" not in out

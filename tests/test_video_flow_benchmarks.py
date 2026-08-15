"""Automated tests for Video Flow Benchmark Framework."""

from __future__ import annotations

import pytest

from tests.benchmarks.fixtures import BENCHMARK_FIXTURES
from tests.benchmarks.evaluator import VideoFlowBenchmarkHarness
from voice_flow.video_generation import GenerationPolicy


def test_benchmark_fixtures_integrity():
    assert len(BENCHMARK_FIXTURES) >= 10
    for sample in BENCHMARK_FIXTURES:
        assert sample.id.startswith("bench_")
        assert len(sample.source_text) > 50
        assert len(sample.expected_key_concepts) >= 2
        assert sample.expected_claims_count >= 2


def test_benchmark_harness_free_deterministic_path():
    harness = VideoFlowBenchmarkHarness(policy=GenerationPolicy.FREE_DETERMINISTIC)
    scores = harness.evaluate_all(BENCHMARK_FIXTURES)

    assert len(scores) == len(BENCHMARK_FIXTURES)
    for score in scores:
        assert score.fallback_success is True
        assert score.estimated_cost_usd == 0.0
        assert score.composite_quality_score >= 70.0
        assert score.elapsed_seconds > 0.0


def test_benchmark_harness_generative_path():
    harness = VideoFlowBenchmarkHarness(policy=GenerationPolicy.PREMIUM_GENERATIVE)
    sample = BENCHMARK_FIXTURES[0]  # CRISPR
    score = harness.evaluate_sample(sample)

    assert score.fallback_success is True
    assert score.composite_quality_score >= 75.0
    assert score.claims_extracted >= 1

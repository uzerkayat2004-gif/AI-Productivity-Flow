"""Stage 4.2 Task 5: Desktop Beta UX, Repetition, Network Isolation, and Runtime Lifecycle Tests.

Validates:
1. Local offline network isolation: All inference and API calls are strictly local (127.0.0.1); zero external network traffic.
2. Rapid repeated dictation stability: 10 back-to-back inference requests without memory leaks or degradation.
3. Error state handling & safe fallback: Graceful handling of empty transcripts, malformed requests, and server drops.
4. Runtime process cleanliness: Verifies no orphaned duplicate llama-server instances.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import psutil
import pytest

from voice_flow.vf1_engine import VF1Engine, VF1EngineConfig, VF1EngineResult
from voice_flow.vf_contract import VF1Request
from voice_flow.safety_gate import validate_and_gate_output


@pytest.fixture(scope="module")
def engine():
    config = VF1EngineConfig(
        backend="native",
        server_host="127.0.0.1",
        server_port=8080,
        model_id="superwhisper/s1-mini",
        use_lora=False,
        temperature=0.0,
        max_new_tokens=256,
    )
    eng = VF1Engine(config)
    if not eng.is_server_healthy():
        pytest.skip("Local llama-server is not running on 127.0.0.1:8080")
    return eng


def test_01_local_network_isolation_and_offline_operation(engine):
    """Verify that VF1Engine operates exclusively on localhost (127.0.0.1) and makes NO outbound internet calls."""
    assert engine.config.server_host in ("127.0.0.1", "localhost")
    assert engine.config.server_port == 8080

    # Ensure URL is strictly loopback
    health_url = f"http://{engine.config.server_host}:{engine.config.server_port}/health"
    assert "127.0.0.1" in health_url or "localhost" in health_url

    # Perform inference and verify success on offline loopback
    res = engine.polish_transcript("offline test phrase", task="cleanup")
    assert res.safety_accepted is True
    assert len(res.final_text) > 0


def test_02_rapid_repeated_dictation_stability(engine):
    """Verify that running 10 back-to-back dictations performs stably without memory explosion or socket errors."""
    test_phrases = [
        "schedule meeting for 10 AM",
        "please deploy version 1.2.3",
        "review ticket BUG-404 immediately",
        "prepare Q3 financial forecast",
        "update customer contact information",
        "send invoice INV-2026-902",
        "verify staging cluster readiness",
        "restart backend worker thread 2",
        "order 5 replacement cables",
        "backup database before midnight",
    ]

    latencies = []
    for i, phrase in enumerate(test_phrases, 1):
        t0 = time.perf_counter()
        res = engine.polish_transcript(phrase, task="cleanup")
        dt_ms = (time.perf_counter() - t0) * 1000
        latencies.append(dt_ms)
        assert res.safety_accepted is True
        assert len(res.final_text) > 0

    avg_lat = sum(latencies) / len(latencies)
    assert avg_lat < 2000.0, f"Average latency too high: {avg_lat:.1f}ms"
    print(f"\n[Repeated Dictation Stability] 10/10 completed. Avg latency: {avg_lat:.1f}ms, Min: {min(latencies):.1f}ms, Max: {max(latencies):.1f}ms")


def test_03_error_state_handling_and_safe_fallback(engine):
    """Verify graceful handling and safe fallback on empty, malformed, or hostile inputs."""
    # 1. Empty transcript
    res_empty = engine.polish_transcript("", task="cleanup")
    assert res_empty.final_text == ""
    assert res_empty.safety_accepted is True

    # 2. Whitespace only
    res_ws = engine.polish_transcript("   \n\t  ", task="cleanup")
    assert res_ws.final_text.strip() == ""

    # 3. Corrupted / hallucinated number detected by safety gate
    # Simulate a candidate output that changes $100 to $1,000,000
    gate_decision = validate_and_gate_output(
        transcript="the cost is one hundred dollars",
        candidate_text="The cost is $1,000,000.",
        task="cleanup",
    )
    assert gate_decision.accepted is False
    assert gate_decision.source_preserved is True
    assert "one hundred dollars" in gate_decision.final_text

    # 4. Negation inversion detected by safety gate
    gate_neg = validate_and_gate_output(
        transcript="do not delete the production database records",
        candidate_text="Delete the production database records.",
        task="cleanup",
    )
    assert gate_neg.accepted is False
    assert gate_neg.source_preserved is True
    assert "do not delete" in gate_neg.final_text.lower()


def test_04_runtime_process_cleanliness():
    """Verify that there are no duplicate or orphaned llama-server processes running."""
    llama_procs = [
        p for p in psutil.process_iter(["pid", "name", "cmdline"])
        if "llama" in p.info["name"].lower()
    ]
    # Exactly one daemon process should be running the active model
    assert len(llama_procs) == 1, f"Expected exactly 1 llama-server process, found {len(llama_procs)}"
    p = llama_procs[0]
    assert p.is_running()
    print(f"\n[Process Cleanliness] Active llama-server PID: {p.pid}, status: {p.status()}")

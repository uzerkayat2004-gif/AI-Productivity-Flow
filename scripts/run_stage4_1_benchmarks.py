#!/usr/bin/env python3
"""Stage 4.1 Benchmark Runner: Real S1-mini GGUF writing-quality evaluation suite.

Evaluates 24 real cases (8 original Stage 4 cases + 16 new unseen cases across
cleanup, emails, prompts, lists, corrections, currency, identifiers, negation,
and question formatting) against the live local S1-mini GGUF inference server.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Ensure UTF-8 output encoding on Windows console
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure src is on sys.path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from voice_flow.vf1_engine import VF1Engine, VF1EngineConfig, VF1EngineResult
from voice_flow.vf_contract import VF1Request


BENCHMARK_CASES = [
    # --- 8 Original Stage 4 Cases ---
    {
        "id": "VF-REAL-001",
        "category": "cleanup_fillers",
        "task": "cleanup",
        "format": "prose",
        "transcript": "so basically the server went down at like 3:15 PM, and we need to notify the DevOps team immediately",
        "notes": "Must remove 'so basically' and 'at like', preserve 3:15 PM, DevOps team, urgency.",
    },
    {
        "id": "VF-REAL-002",
        "category": "self_correction",
        "task": "cleanup",
        "format": "prose",
        "transcript": "send the deployment summary to Rahul no wait send it to Priya",
        "notes": "Must resolve self-correction to Priya.",
    },
    {
        "id": "VF-REAL-003",
        "category": "professional_email",
        "task": "rewrite",
        "format": "email",
        "transcript": "email to finance team subject budget approval update hi team the Q4 budget has been approved regards devon",
        "notes": "Must generate distinct Subject line, greeting, body, sign-off with Devon.",
    },
    {
        "id": "VF-REAL-004",
        "category": "prompt_synthesis",
        "task": "prompt",
        "format": "prompt",
        "transcript": "make this a prompt: write a high-performance Python parser for real-time telemetry streaming",
        "notes": "Must strip 'make this a prompt:' wrapper, output usable prompt.",
    },
    {
        "id": "VF-REAL-005",
        "category": "bullet_formatting",
        "task": "rewrite",
        "format": "bullets",
        "transcript": "packing list laptop charger passport water bottle notepad",
        "notes": "Must format distinct items as separate bullets; Laptop and Charger must not merge.",
    },
    {
        "id": "VF-REAL-006",
        "category": "currency_inr",
        "task": "cleanup",
        "format": "prose",
        "transcript": "please prepare a sanction order for ₹15,00,000 for the infrastructure vendor",
        "notes": "Must preserve ₹15,00,000 numerical format and sanction order.",
    },
    {
        "id": "VF-REAL-007",
        "category": "negation_preservation",
        "task": "cleanup",
        "format": "prose",
        "transcript": "do not delete the production database records under any circumstances",
        "notes": "Must strictly preserve 'do not delete' negation.",
    },
    {
        "id": "VF-REAL-008",
        "category": "question_not_answered",
        "task": "rewrite",
        "format": "bullets",
        "transcript": "format as bullet points: how do I configure the reverse proxy? Step one open the config file. Step two specify the upstream server. Step three reload the service.",
        "notes": "Must preserve question header, format steps as separate bullets, not answer.",
    },

    # --- 16 New Unseen Test Cases ---
    {
        "id": "VF-REAL-009",
        "category": "cleanup_fillers",
        "task": "cleanup",
        "format": "prose",
        "transcript": "um like we actually need to schedule the quarterly planning review for next Tuesday at 2:00 PM",
        "notes": "Must strip leading fillers 'um like', preserve Tuesday at 2:00 PM.",
    },
    {
        "id": "VF-REAL-010",
        "category": "cleanup_urgency",
        "task": "cleanup",
        "format": "prose",
        "transcript": "basically the SSL certificate expires in 48 hours so we must renew it right away",
        "notes": "Must strip 'basically', preserve SSL certificate, 48 hours, urgency.",
    },
    {
        "id": "VF-REAL-011",
        "category": "professional_email",
        "task": "rewrite",
        "format": "email",
        "transcript": "email to client subject quarterly invoice delivery dear client please find attached invoice number INV-2026-884 for your review best regards Marcus",
        "notes": "Must format Subject, Dear Client, invoice INV-2026-884, Marcus sign-off.",
    },
    {
        "id": "VF-REAL-012",
        "category": "professional_email",
        "task": "rewrite",
        "format": "email",
        "transcript": "email to leadership subject incident postmortem summary hi executives the postmortem for yesterday's outage is now published in the wiki thanks Alice",
        "notes": "Must format Subject, Hi Executives, wiki link/postmortem, Alice sign-off.",
    },
    {
        "id": "VF-REAL-013",
        "category": "prompt_synthesis",
        "task": "prompt",
        "format": "prompt",
        "transcript": "make this a prompt: create a comprehensive benchmark report comparing local LLM inference engines on Windows",
        "notes": "Must strip 'make this a prompt:', preserve target instruction.",
    },
    {
        "id": "VF-REAL-014",
        "category": "prompt_synthesis",
        "task": "prompt",
        "format": "prompt",
        "transcript": "create a prompt for: designing a low-latency audio capture pipeline using PyAudio and WebRTC",
        "notes": "Must strip 'create a prompt for:', preserve PyAudio and WebRTC.",
    },
    {
        "id": "VF-REAL-015",
        "category": "bullet_formatting",
        "task": "rewrite",
        "format": "bullets",
        "transcript": "deployment checklist backup database run migrations deploy containers verify health endpoint",
        "notes": "Must format deployment checklist items as separate bullet points.",
    },
    {
        "id": "VF-REAL-016",
        "category": "bullet_formatting",
        "task": "rewrite",
        "format": "bullets",
        "transcript": "action items update API documentation review pull request 42 run smoke tests",
        "notes": "Must format action items with separate bullets, preserve PR 42.",
    },
    {
        "id": "VF-REAL-017",
        "category": "self_correction",
        "task": "cleanup",
        "format": "prose",
        "transcript": "the meeting is on Thursday wait actually it was moved to Friday at 11 AM",
        "notes": "Must resolve self-correction to Friday at 11 AM.",
    },
    {
        "id": "VF-REAL-018",
        "category": "self_correction",
        "task": "cleanup",
        "format": "prose",
        "transcript": "order ten new test devices no wait make that fifteen test devices",
        "notes": "Must resolve self-correction to fifteen test devices.",
    },
    {
        "id": "VF-REAL-019",
        "category": "currency_gbp",
        "task": "cleanup",
        "format": "prose",
        "transcript": "the subscription fee is £450 per year billed annually to the account",
        "notes": "Must preserve £450 currency symbol and billing frequency.",
    },
    {
        "id": "VF-REAL-020",
        "category": "currency_multi",
        "task": "cleanup",
        "format": "prose",
        "transcript": "the pricing is $120 in North America and €110 in Europe",
        "notes": "Must preserve both $120 and €110 with regional associations.",
    },
    {
        "id": "VF-REAL-021",
        "category": "identifiers",
        "task": "cleanup",
        "format": "prose",
        "transcript": "please look into ticket JIRA-8921 regarding the memory leak in worker thread 4",
        "notes": "Must preserve alphanumeric identifier JIRA-8921 and worker thread 4.",
    },
    {
        "id": "VF-REAL-022",
        "category": "negation_preservation",
        "task": "cleanup",
        "format": "prose",
        "transcript": "never share the root API tokens or private signing keys in public chat channels",
        "notes": "Must strictly preserve prohibition 'never share' and key assets.",
    },
    {
        "id": "VF-REAL-023",
        "category": "question_not_answered",
        "task": "rewrite",
        "format": "bullets",
        "transcript": "format as a list: what is the procedure for disaster recovery? Step one failover DNS to secondary region. Step two spin up standby database replica. Step three notify stakeholders.",
        "notes": "Must preserve question header, format steps as separate bullets, not answer.",
    },
    {
        "id": "VF-REAL-024",
        "category": "question_not_answered",
        "task": "rewrite",
        "format": "bullets",
        "transcript": "format as bullet points: how do we resolve port conflicts? Step one check active listening ports. Step two terminate the orphaned process. Step three restart the application service.",
        "notes": "Must preserve question header, format steps as separate bullets, not answer.",
    },
]


def run_benchmark():
    print(f"=== Stage 4.1 Benchmark Runner: 24 Live S1-mini GGUF Test Cases ===")
    config = VF1EngineConfig(
        backend="native",
        server_host="127.0.0.1",
        server_port=8080,
        model_id="superwhisper/s1-mini",
        use_lora=False,
        temperature=0.0,
        max_new_tokens=256,
    )
    engine = VF1Engine(config)

    if not engine.is_server_healthy():
        print("ERROR: llama-server is not reachable on 127.0.0.1:8080. Start llama-server first.")
        sys.exit(1)

    print("Connected to live llama-server at http://127.0.0.1:8080/health [OK]")

    results = []
    total_latency_ms = 0.0
    passed_count = 0

    for i, c in enumerate(BENCHMARK_CASES, 1):
        cid = c["id"]
        task = c["task"]
        fmt = c["format"]
        transcript = c["transcript"]

        req = VF1Request(task=task, format=fmt, transcript=transcript)
        sys_prompt, user_prompt, full_prompt = engine.build_chatml_prompt(req)

        print(f"\n[{i}/{len(BENCHMARK_CASES)}] Running {cid} ({c['category']})...")
        res: VF1EngineResult = engine.polish_transcript(
            transcript,
            task=task,
            format=fmt,
            timeout_seconds=10.0,
        )

        passed = res.task_passed
        if passed:
            passed_count += 1
        total_latency_ms += res.latency_ms

        telem = engine.get_last_telemetry() or {}

        record = {
            "id": cid,
            "category": c["category"],
            "task": task,
            "format": fmt,
            "input_transcript": transcript,
            "exact_prompt": full_prompt,
            "raw_output": res.raw_output,
            "postprocessed_output": res.postprocessed_output,
            "safety_accepted": res.safety_accepted,
            "safety_reasons": res.safety_reasons,
            "source_preserved": res.source_preserved,
            "final_text": res.final_text,
            "task_passed": passed,
            "latency_ms": res.latency_ms,
            "input_tokens": res.input_tokens,
            "output_tokens": res.output_tokens,
            "tokens_per_second": res.tokens_per_second,
            "notes": c["notes"],
        }
        results.append(record)

        status_str = "PASS" if passed else "FAIL"
        print(f"  Result: [{status_str}] in {res.latency_ms:.1f}ms ({res.tokens_per_second:.1f} tok/s)")
        print(f"  Raw:          {res.raw_output[:80]}...")
        print(f"  Postproc:     {res.postprocessed_output[:80]}...")
        print(f"  Delivered:    {res.final_text[:80]}...")

    avg_latency = round(total_latency_ms / len(BENCHMARK_CASES), 2)
    pass_rate = round(passed_count / len(BENCHMARK_CASES) * 100, 1)

    print("\n" + "=" * 60)
    print(f"BENCHMARK SUMMARY:")
    print(f"Total Cases:     {len(BENCHMARK_CASES)}")
    print(f"Passed:          {passed_count} / {len(BENCHMARK_CASES)} ({pass_rate}%)")
    print(f"Average Latency: {avg_latency} ms")
    print("=" * 60)

    output_path = Path(__file__).resolve().parent.parent / "benchmark_stage4_1_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "model_id": "superwhisper/s1-mini-q4_k_m.gguf",
                "runtime": "llama-server Windows CPU x64",
                "summary": {
                    "total": len(BENCHMARK_CASES),
                    "passed": passed_count,
                    "pass_rate_pct": pass_rate,
                    "avg_latency_ms": avg_latency,
                },
                "cases": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Saved benchmark results to {output_path}")


if __name__ == "__main__":
    run_benchmark()

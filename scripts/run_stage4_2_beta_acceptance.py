#!/usr/bin/env python3
"""Stage 4.2 Task 3: 20 Fresh Independent Acceptance Benchmark Cases (VF-BETA-001 to 020).

Evaluates the real local S1-mini GGUF CPU inference backend against 20 unseen, frozen acceptance cases
covering:
- Ambiguous action checklists & hardware lists
- Professional email subjects & identities
- Actionable prompt synthesis (imperative conversion)
- Spoken self-corrections (numbers, dates, names)
- Large numbers & multi-currency formats (INR, USD, EUR)
- Technical alphanumeric identifiers & version strings
- Strict negation & prohibition preservation
- Dictated questions preserved as formatting headers (not answered)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

# Ensure UTF-8 output encoding on Windows console
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from voice_flow.vf1_engine import VF1Engine, VF1EngineConfig, VF1EngineResult
from voice_flow.vf_contract import VF1Request


BETA_CASES = [
    # --- Ambiguous Lists & Action Checklists ---
    {
        "id": "VF-BETA-001",
        "category": "action_checklist",
        "task": "rewrite",
        "format": "bullets",
        "transcript": "morning checklist backup redis cluster run migrations review pull request 104 deploy canary",
        "notes": "Must preserve action-verb and object grouping across all items, including PR 104.",
    },
    {
        "id": "VF-BETA-002",
        "category": "hardware_list",
        "task": "rewrite",
        "format": "bullets",
        "transcript": "procurement request mechanical keyboard mouse pad external monitor usb hub",
        "notes": "Must format distinct hardware items as separate bullet points.",
    },
    {
        "id": "VF-BETA-003",
        "category": "action_checklist",
        "task": "rewrite",
        "format": "bullets",
        "transcript": "release steps run integration tests build docker image verify metrics",
        "notes": "Must keep 'run integration tests', 'build docker image', 'verify metrics' separate and intact.",
    },

    # --- Professional Email Structure & Subject ---
    {
        "id": "VF-BETA-004",
        "category": "professional_email",
        "task": "rewrite",
        "format": "email",
        "transcript": "email to dev team subject urgent patch deployment hi team please deploy hotfix version 2.4.1 immediately thanks carlos",
        "notes": "Must format Subject, greeting, hotfix version 2.4.1, and Carlos sign-off.",
    },
    {
        "id": "VF-BETA-005",
        "category": "professional_email",
        "task": "rewrite",
        "format": "email",
        "transcript": "send email to customer support subject billing inquiry dear support why was my subscription charged twice this month sincerely elena",
        "notes": "Must format Subject, greeting, billing inquiry body, and Elena sign-off.",
    },

    # --- Prompt Synthesis (Imperative Actionable Output) ---
    {
        "id": "VF-BETA-006",
        "category": "prompt_synthesis",
        "task": "prompt",
        "format": "prompt",
        "transcript": "make this a prompt: analyzing memory consumption in a multithreaded C++ application with Valgrind",
        "notes": "Must synthesize actionable imperative prompt ('Analyze...') preserving C++ and Valgrind.",
    },
    {
        "id": "VF-BETA-007",
        "category": "prompt_synthesis",
        "task": "prompt",
        "format": "prompt",
        "transcript": "create a prompt for: optimizing slow SQL queries on a PostgreSQL database with 10 million rows",
        "notes": "Must synthesize actionable imperative prompt ('Optimize...') preserving PostgreSQL and 10 million.",
    },
    {
        "id": "VF-BETA-008",
        "category": "prompt_synthesis",
        "task": "prompt",
        "format": "prompt",
        "transcript": "write a prompt: drafting a comprehensive security incident response policy for ISO 27001",
        "notes": "Must synthesize actionable imperative prompt ('Draft...') preserving ISO 27001.",
    },

    # --- Self-Corrections ---
    {
        "id": "VF-BETA-009",
        "category": "self_correction",
        "task": "cleanup",
        "format": "prose",
        "transcript": "we need twelve licenses wait no actually sixteen enterprise licenses",
        "notes": "Must resolve self-correction to sixteen enterprise licenses.",
    },
    {
        "id": "VF-BETA-010",
        "category": "self_correction",
        "task": "cleanup",
        "format": "prose",
        "transcript": "schedule the team sync for Wednesday at 4 PM sorry Thursday at 2 PM",
        "notes": "Must resolve self-correction to Thursday at 2 PM.",
    },
    {
        "id": "VF-BETA-011",
        "category": "self_correction",
        "task": "cleanup",
        "format": "prose",
        "transcript": "assign the incident to Dave no wait assign it to Sarah",
        "notes": "Must resolve self-correction to Sarah.",
    },

    # --- Large Numbers & Currencies ---
    {
        "id": "VF-BETA-012",
        "category": "currency_inr",
        "task": "cleanup",
        "format": "prose",
        "transcript": "the total procurement sanction is ₹75,50,000 payable across three milestone tranches",
        "notes": "Must preserve ₹75,50,000 Indian currency notation and milestone counts.",
    },
    {
        "id": "VF-BETA-013",
        "category": "currency_usd",
        "task": "cleanup",
        "format": "prose",
        "transcript": "we closed $2,500,000 in seed capital funding from venture partners",
        "notes": "Must preserve $2,500,000 USD amount without truncation.",
    },
    {
        "id": "VF-BETA-014",
        "category": "currency_eur",
        "task": "cleanup",
        "format": "prose",
        "transcript": "the annual maintenance deficit was €850,000 in fiscal year 2025",
        "notes": "Must preserve €850,000 EUR amount and fiscal year 2025.",
    },

    # --- Technical Identifiers & Versions ---
    {
        "id": "VF-BETA-015",
        "category": "technical_ids",
        "task": "cleanup",
        "format": "prose",
        "transcript": "investigate error code ERR-9042 and kubernetes pod crash on node-prod-west-02",
        "notes": "Must preserve alphanumeric identifier ERR-9042 and hostname node-prod-west-02.",
    },
    {
        "id": "VF-BETA-016",
        "category": "technical_ids",
        "task": "cleanup",
        "format": "prose",
        "transcript": "git cherry-pick commit a1b2c3d into release branch v3.1.0-rc2",
        "notes": "Must preserve commit hash a1b2c3d and branch tag v3.1.0-rc2.",
    },

    # --- Negation & Prohibition Preservation ---
    {
        "id": "VF-BETA-017",
        "category": "negation_preservation",
        "task": "cleanup",
        "format": "prose",
        "transcript": "do not restart the production database while the data migration is running",
        "notes": "Must strictly preserve 'do not restart' prohibition.",
    },
    {
        "id": "VF-BETA-018",
        "category": "negation_preservation",
        "task": "cleanup",
        "format": "prose",
        "transcript": "never commit AWS access keys or private signing credentials to public git repositories",
        "notes": "Must strictly preserve 'never commit' prohibition.",
    },

    # --- Questions Not Answered (Formatting Headers Preserved) ---
    {
        "id": "VF-BETA-019",
        "category": "question_not_answered",
        "task": "rewrite",
        "format": "bullets",
        "transcript": "format as a list: what are the prerequisites for cluster installation? Step one configure network interface. Step two install container runtime. Step three initialize control plane.",
        "notes": "Must preserve question header, format steps as separate bullets, not answer.",
    },
    {
        "id": "VF-BETA-020",
        "category": "question_not_answered",
        "task": "rewrite",
        "format": "bullets",
        "transcript": "format as bullet points: why did the build fail? Reason one missing dependency lockfile. Reason two syntax error in configuration. Reason three timeout during asset compilation.",
        "notes": "Must preserve question header, format reasons as separate bullets, not answer.",
    },
]


def run_beta_acceptance():
    print(f"=== Stage 4.2 Acceptance Benchmark Runner: 20 Fresh Live Test Cases ===")
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
        print("ERROR: llama-server is not reachable on 127.0.0.1:8080.")
        sys.exit(1)

    print("Connected to live llama-server at http://127.0.0.1:8080/health [OK]\n")

    results = []
    latencies = []
    passed_count = 0

    for i, c in enumerate(BETA_CASES, 1):
        cid = c["id"]
        task = c["task"]
        fmt = c["format"]
        transcript = c["transcript"]

        req = VF1Request(task=task, format=fmt, transcript=transcript)
        sys_prompt, user_prompt, full_prompt = engine.build_chatml_prompt(req)

        print(f"[{i:02d}/{len(BETA_CASES)}] Running {cid} ({c['category']})...")
        res: VF1EngineResult = engine.polish_transcript(
            transcript,
            task=task,
            format=fmt,
            timeout_seconds=10.0,
        )

        passed = res.task_passed
        if passed:
            passed_count += 1
        latencies.append(res.latency_ms)

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
        print(f"  Raw:          {res.raw_output.replace(chr(10), ' | ')[:80]}...")
        print(f"  Postproc:     {res.postprocessed_output.replace(chr(10), ' | ')[:80]}...")
        print(f"  Delivered:    {res.final_text.replace(chr(10), ' | ')[:80]}...")

    avg_latency = round(sum(latencies) / len(latencies), 2)
    sorted_lats = sorted(latencies)
    median_latency = round(sorted_lats[len(sorted_lats) // 2], 2)
    min_latency = round(min(latencies), 2)
    max_latency = round(max(latencies), 2)
    pass_rate = round(passed_count / len(BETA_CASES) * 100, 1)

    print("\n" + "=" * 60)
    print("STAGE 4.2 FRESH BETA ACCEPTANCE SUMMARY:")
    print(f"Total Cases:     {len(BETA_CASES)}")
    print(f"Passed:          {passed_count} / {len(BETA_CASES)} ({pass_rate}%)")
    print(f"Mean Latency:    {avg_latency} ms")
    print(f"Median Latency:  {median_latency} ms")
    print(f"Min Latency:     {min_latency} ms")
    print(f"Max Latency:     {max_latency} ms")
    print("=" * 60)

    output_path = Path(__file__).resolve().parent.parent / "benchmark_stage4_2_acceptance.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "model_id": "superwhisper/s1-mini-q4_k_m.gguf",
                "runtime": "llama-server Windows CPU x64",
                "summary": {
                    "total": len(BETA_CASES),
                    "passed": passed_count,
                    "pass_rate_pct": pass_rate,
                    "mean_latency_ms": avg_latency,
                    "median_latency_ms": median_latency,
                    "min_latency_ms": min_latency,
                    "max_latency_ms": max_latency,
                },
                "cases": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Saved fresh acceptance benchmark results to {output_path}")


if __name__ == "__main__":
    run_beta_acceptance()

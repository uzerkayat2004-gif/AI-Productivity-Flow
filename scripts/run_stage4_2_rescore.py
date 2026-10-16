#!/usr/bin/env python3
"""Stage 4.2 Task 2: Re-scoring the 24 Stage 4.1 Benchmark Examples.

Evaluates the preserved Stage 4.1 raw and final outputs against strict dimensional criteria:
1. Raw Model Correctness: Did the raw S1-mini generation directly satisfy task requirements?
2. Postprocessing Contribution: Did deterministic postprocessing repair flaws in the raw output?
3. Final Task Correctness: Does the delivered text satisfy task requirements under Stage 4.2 rules?
4. Factual Preservation: Were all numbers, currencies, dates, times, entities, and negations preserved?
5. Safety-Gate Decision: Did the host-side factual safety gate accept or reject?

Specifically records before-and-after corrections for:
- VF-REAL-014 (Prompt synthesis: gerund "Designing..." vs imperative "Design...")
- VF-REAL-015 (Checklist segmentation: "- Verify health" / "- Endpoint" vs "- Verify health endpoint")
- VF-REAL-016 (Action items: "documentation review" / "PR 42" vs "documentation" / "Review PR 42")
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

from voice_flow.vf1_engine import VF1Engine, VF1EngineConfig
from voice_flow.vf_contract import VF1Request
from voice_flow.safety_gate import validate_and_gate_output


def evaluate_raw_correctness(case_id: str, task: str, fmt: str, raw_output: str, transcript: str) -> tuple[bool, str]:
    """Strictly evaluate if raw S1-mini model output satisfied the task without postprocessing."""
    raw = raw_output.strip()

    # VF-REAL-001: Still had filler "basically,"
    if case_id == "VF-REAL-001":
        if re.match(r"^basically\b", raw, re.I):
            return False, "Retained introductory spoken filler 'basically,'"

    # VF-REAL-005: Merged laptop and charger
    if case_id == "VF-REAL-005":
        if "laptop charger" in raw.lower() and not ("laptop" in raw.lower() and "charger" in raw.lower() and "- charger" in raw.lower()):
            return False, "Merged 'laptop charger' into a single bullet instead of separate items"

    # VF-REAL-014: Repeated meta-prompt wrapper
    if case_id == "VF-REAL-014":
        if raw.lower().startswith("create a prompt for:"):
            return False, "Echoed spoken meta-command 'create a prompt for:'"

    # VF-REAL-015: Fractured 'Verify health endpoint'
    if case_id == "VF-REAL-015":
        if "- endpoint" in raw.lower() or "\nendpoint" in raw.lower():
            return False, "Fractured action 'Verify health endpoint' into separate '- Verify health' and '- Endpoint' bullets"

    # VF-REAL-016: Misaligned verb-object boundary
    if case_id == "VF-REAL-016":
        if "documentation review" in raw.lower() or not ("review pull request" in raw.lower() or "review pr" in raw.lower()):
            return False, "Misaligned verb-object boundary: attached 'review' to 'documentation' rather than 'pull request 42'"

    # Generic checks:
    if task == "prompt" or fmt == "prompt":
        if re.search(r"^(?:make this a prompt|create a prompt for|write a prompt)[:\s]+", raw, re.I):
            return False, "Raw output retained spoken meta-command prefix"
        first_w = raw.split()[0].lower().rstrip(":,.") if raw.split() else ""
        if first_w.endswith("ing"):
            return False, f"Raw prompt begins with gerund phrase '{first_w}' instead of actionable imperative"

    if fmt == "email":
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        has_subject = any(re.match(r"^Subject:\s*.+", ln, re.I) for ln in lines)
        if not has_subject:
            return False, "Missing distinct 'Subject:' line"

    if fmt in ("bullets", "numbered"):
        bullet_lines = [ln.strip() for ln in raw.splitlines() if ln.strip().startswith(("-", "*", "•", "1.", "2."))]
        if not bullet_lines and len(raw.splitlines()) > 1:
            return False, "Missing bullet point prefixes"
        for bl in bullet_lines:
            words = bl.lstrip("-*•123456789. ").split()
            if len(words) == 1 and words[0].lower() in ("endpoint", "review"):
                return False, f"Fractured orphaned single-word bullet: '{bl}'"

    return True, "Raw output satisfied task requirements"


def rescore_stage4_1_benchmark():
    stage4_1_path = Path(__file__).resolve().parent.parent / "benchmark_stage4_1_results.json"
    if not stage4_1_path.exists():
        print(f"ERROR: {stage4_1_path} not found.")
        sys.exit(1)

    with open(stage4_1_path, "r", encoding="utf-8") as f:
        stage4_1_data = json.load(f)

    engine = VF1Engine(VF1EngineConfig(backend="mock"))

    rescored_cases = []
    raw_passed_count = 0
    postproc_repaired_count = 0
    final_passed_count = 0
    factual_preserved_count = 0
    safety_accepted_count = 0

    print("=== Rescoring 24 Stage 4.1 Benchmark Cases with Strict Stage 4.2 Rubric ===")

    for c in stage4_1_data["cases"]:
        cid = c["id"]
        task = c["task"]
        fmt = c["format"]
        transcript = c["input_transcript"]
        raw_output = c["raw_output"]
        old_postprocessed = c["postprocessed_output"]
        old_passed = c["task_passed"]

        req = VF1Request(task=task, format=fmt, transcript=transcript)

        # 1. Evaluate Raw Model Correctness strictly
        raw_correct, raw_reason = evaluate_raw_correctness(cid, task, fmt, raw_output, transcript)
        if raw_correct:
            raw_passed_count += 1

        # 2. Apply updated Stage 4.2 postprocessing
        stage4_2_postprocessed = engine._postprocess_candidate(raw_output, req)

        # 3. Check Safety Gate
        gate_decision = validate_and_gate_output(
            transcript=transcript,
            candidate_text=stage4_2_postprocessed,
            task=task,
        )
        safety_accepted = gate_decision.accepted
        final_text = gate_decision.final_text
        if safety_accepted:
            safety_accepted_count += 1

        # 4. Check Factual Preservation
        # In all 24 cases, the safety gate verified no hallucinated numbers or lost entities
        factual_preserved = len([r for r in gate_decision.rejection_reasons if "invented" in r or "lost" in r]) == 0
        if factual_preserved:
            factual_preserved_count += 1

        # 5. Evaluate Final Task Correctness under Stage 4.2 rules
        final_passed = engine._evaluate_task_passed(final_text, req, safety_accepted)
        if final_passed:
            final_passed_count += 1

        # Determine if postprocessing made an essential contribution
        postproc_contribution = (not raw_correct) and final_passed
        if postproc_contribution:
            postproc_repaired_count += 1

        # Stage 4.1 vs 4.2 difference
        has_stage4_2_change = (stage4_2_postprocessed != old_postprocessed)

        rescored_record = {
            "id": cid,
            "category": c["category"],
            "task": task,
            "format": fmt,
            "transcript": transcript,
            "raw_output": raw_output,
            "stage4_1_delivered": c["final_text"],
            "stage4_1_judgment": "PASS" if old_passed else "FAIL",
            "stage4_2_delivered": final_text,
            "stage4_2_judgment": "PASS" if final_passed else "FAIL",
            "dimensional_scores": {
                "raw_model_correct": raw_correct,
                "raw_model_reason": raw_reason,
                "postprocessing_contribution": postproc_contribution,
                "factual_preservation": factual_preserved,
                "safety_gate_accepted": safety_accepted,
                "safety_reasons": gate_decision.rejection_reasons,
                "final_task_correctness": final_passed,
            },
            "stage4_2_fix_applied": has_stage4_2_change,
            "latency_ms": c.get("latency_ms", 0.0),
            "tokens_per_second": c.get("tokens_per_second", 0.0),
        }

        if has_stage4_2_change:
            print(f"\n[FIXED CASE] {cid} ({c['category']}):")
            print(f"  Raw:              {raw_output.replace(chr(10), ' | ')}")
            print(f"  Stage 4.1 Output: {old_postprocessed.replace(chr(10), ' | ')}")
            print(f"  Stage 4.2 Output: {stage4_2_postprocessed.replace(chr(10), ' | ')}")

        rescored_cases.append(rescored_record)

    total = len(rescored_cases)
    summary = {
        "total_cases": total,
        "raw_model_correct": raw_passed_count,
        "raw_model_correct_pct": round(raw_passed_count / total * 100, 1),
        "postprocessing_repaired_cases": postproc_repaired_count,
        "postprocessing_repaired_pct": round(postproc_repaired_count / total * 100, 1),
        "factual_preservation_cases": factual_preserved_count,
        "factual_preservation_pct": round(factual_preserved_count / total * 100, 1),
        "safety_gate_accepted_cases": safety_accepted_count,
        "safety_gate_accepted_pct": round(safety_accepted_count / total * 100, 1),
        "final_task_correctness_cases": final_passed_count,
        "final_task_correctness_pct": round(final_passed_count / total * 100, 1),
    }

    print("\n" + "=" * 60)
    print("STAGE 4.2 RESCORING SUMMARY:")
    print(f"Total Cases:                   {summary['total_cases']}")
    print(f"Raw Model Correctness:         {summary['raw_model_correct']} / {total} ({summary['raw_model_correct_pct']}%)")
    print(f"Postprocessing Repaired Cases: {summary['postprocessing_repaired_cases']} / {total} ({summary['postprocessing_repaired_pct']}%)")
    print(f"Factual Preservation:          {summary['factual_preservation_cases']} / {total} ({summary['factual_preservation_pct']}%)")
    print(f"Safety Gate Accepted:          {summary['safety_gate_accepted_cases']} / {total} ({summary['safety_gate_accepted_pct']}%)")
    print(f"Final Task Correctness:        {summary['final_task_correctness_cases']} / {total} ({summary['final_task_correctness_pct']}%)")
    print("=" * 60)

    out_file = Path(__file__).resolve().parent.parent / "benchmark_stage4_2_rescore.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "benchmark_source": "benchmark_stage4_1_results.json",
                "summary": summary,
                "cases": rescored_cases,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Saved rescored results to {out_file}")


if __name__ == "__main__":
    rescore_stage4_1_benchmark()

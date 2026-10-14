#!/usr/bin/env python3
"""Evaluate frozen 35-case multi-task benchmark on S1-mini configurations.

Evaluates:
1. S1-mini Native Base (the official native normalizer prompt)
2. S1-mini VF-1 Base (the universal contract v1.2 prompt)

Decoding policy:
- Deterministic greedy: temperature=0.0, do_sample=False, max_tokens=256
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE / "src"))
from voice_flow.vf_contract import VF1Request, render_vf1, SYSTEM_PROMPT_VF1

BENCHMARK_PATH = HERE / "data" / "frozen_eval_multitask_35.jsonl"
OUTPUT_REPORT_PATH = HERE / "logs" / "benchmark_multitask_35_results.json"
SERVER_URL = "http://127.0.0.1:8080/completion"

S1_NATIVE_SYSTEM = (
    "You are a transcript normalizer. Your task is to process raw voice transcripts, "
    "ensuring all grammar, punctuation, and capitalization are accurate."
)

def query_llama_server(prompt: str, max_tokens: int = 256) -> tuple[str, float]:
    payload = {
        "prompt": prompt,
        "temperature": 0.0,
        "n_predict": max_tokens,
        "stop": ["<|im_end|>", "<|endoftext|>"],
        "stream": False,
        "cache_prompt": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(SERVER_URL, data=data, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            elapsed = time.time() - t0
            content = res.get("content", "").strip()
            # Strip empty think block if present
            if content.startswith("<think>\n\n</think>\n\n"):
                content = content[len("<think>\n\n</think>\n\n"):].strip()
            return content, elapsed
    except Exception as e:
        print(f"Error calling llama-server: {e}")
        return "", 0.0


def render_s1_native_prompt(transcript: str, task: str) -> str:
    # S1 native format: styling, structure, context + transcript
    style = "semi-formal" if task == "cleanup" else "formal"
    structure = "lists" if task in ("bullets", "numbered") else "prose"
    user_body = f"[Styling: {style}] [Structure: {structure}] [Context: general]\n{transcript.strip()}"
    return (
        f"<|im_start|>system\n{S1_NATIVE_SYSTEM}<|im_end|>\n"
        f"<|im_start|>user\n{user_body}<|im_end|>\n"
        f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )


def render_vf1_chatml_prompt(req_dict: dict) -> str:
    r = dict(req_dict)
    if "rules" in r:
        r["rules"] = tuple(r["rules"])
    req = VF1Request(**r)
    sys_prompt, user_prompt = render_vf1(req)
    return (
        f"<|im_start|>system\n{sys_prompt}<|im_end|>\n"
        f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
        f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )


def evaluate_output(rec: dict, gen: str, variant: str) -> dict:
    req = rec["request"]
    task = req.get("task", "cleanup")
    target = rec["target"]
    heightened = rec.get("review", {}).get("heightened", [])

    # Check for placeholder leaks
    has_placeholder = bool(re.search(r"\[(?:Your|Recipient|Name|Company).*?\]", gen, re.IGNORECASE))

    # Check for internal control tag echoes
    has_tag_echo = bool(re.search(r"(\[VF-1\]|\[Task:|\[Styling:|\[Structure:)", gen))

    # Task-specific scoring
    instruction_adherence = True
    factual_preservation = True
    semantic_preservation = True
    formatting_adherence = True
    reasons = []

    if has_tag_echo:
        instruction_adherence = False
        reasons.append("echoed_internal_control_tags")

    if has_placeholder:
        formatting_adherence = False
        reasons.append("hallucinated_placeholder")

    # Family 1: Cleanup & self-corrections
    if "negation" in heightened or "self_correction" in heightened:
        if "don't" in target.lower() and "don't" not in gen.lower() and "not" not in gen.lower() and "hold" not in gen.lower():
            factual_preservation = False
            reasons.append("negation_or_correction_failure")
        if "hold the release" in target.lower() and "deploy on friday" in gen.lower():
            factual_preservation = False
            reasons.append("failed_correction_flip")

    if "currency_inr" in heightened:
        if "3,80,000" not in gen and "380,000" not in gen and "380000" not in gen:
            factual_preservation = False
            reasons.append("missing_currency_inr_380000")

    if "scale_number" in heightened:
        if "3.5" not in gen and "three point five" not in gen:
            factual_preservation = False
            reasons.append("missing_scale_number_3_5")

    # Family 2: Email & Messages
    if task == "rewrite" and req.get("format") == "email":
        if "Subject:" in target:
            if "Subject:" not in gen:
                formatting_adherence = False
                reasons.append("missing_subject_header")
            else:
                # Check subject separation: should have newline after subject
                sub_lines = [l.strip() for l in gen.splitlines() if l.strip()]
                if len(sub_lines) < 2:
                    formatting_adherence = False
                    reasons.append("subject_not_separated_from_body")
        if req.get("sender"):
            sender = req["sender"]
            if sender.lower() not in gen.lower():
                factual_preservation = False
                reasons.append(f"lost_sender_identity_{sender}")

    # Family 3: Actionable Prompts
    if task == "prompt":
        if gen.lower().startswith("create a prompt") or gen.lower().startswith("write a prompt") or gen.lower().startswith("make a prompt"):
            instruction_adherence = False
            reasons.append("meta_wrapper_echo")

    # Family 4: Lists & Notes
    if req.get("format") == "bullets":
        # Check action item intactness
        if "Verify health endpoint" in target and "Verify health\n- Endpoint" in gen:
            semantic_preservation = False
            reasons.append("broken_action_object_segmentation")
        # Check distinct item separation (e.g. laptop charger vs laptop and charger)
        if "- Laptop charger" in gen and "- Laptop\n- Charger" in target:
            semantic_preservation = False
            reasons.append("merged_distinct_list_items")

    # Family 5: Summarization
    if task == "summarize":
        if "still open" in target.lower() or "remains unresolved" in target.lower() or "unfixed" in target.lower():
            if "resolved" in gen.lower() and "unresolved" not in gen.lower() and "not" not in gen.lower() and "remains" not in gen.lower() and "still" not in gen.lower():
                factual_preservation = False
                reasons.append("status_corruption_open_to_resolved")

    # Family 6: Style rewriting
    if "hedge_preserved" in heightened:
        if "depends" not in gen.lower():
            factual_preservation = False
            reasons.append("dropped_hedge_or_condition")

    # Family 7: Follow-up editing
    if task == "edit":
        if "Thursday" in target and "Thursday" not in gen:
            factual_preservation = False
            reasons.append("failed_followup_targeted_edit")
        if "Devon Vance" in target and "Devon" not in gen:
            factual_preservation = False
            reasons.append("failed_followup_entity_addition")

    overall_pass = instruction_adherence and factual_preservation and semantic_preservation and (not has_tag_echo) and (not has_placeholder)

    return {
        "variant": variant,
        "id": rec["id"],
        "bucket": rec.get("bucket"),
        "task": task,
        "raw_generation": gen,
        "reference": target,
        "instruction_adherence": instruction_adherence,
        "factual_preservation": factual_preservation,
        "semantic_preservation": semantic_preservation,
        "formatting_adherence": formatting_adherence,
        "overall_pass": overall_pass,
        "reasons": reasons,
    }


def main():
    print("=" * 70)
    print("VOICE FLOW — FROZEN 35-CASE MULTI-TASK BENCHMARK EVALUATION")
    print("=" * 70)

    if not BENCHMARK_PATH.exists():
        sys.exit(f"Benchmark file not found: {BENCHMARK_PATH}")

    cases = [json.loads(line) for line in open(BENCHMARK_PATH, encoding="utf-8") if line.strip()]
    print(f"Loaded {len(cases)} frozen evaluation cases across all 7 VF-1 families.")

    results_native = []
    results_vf1_base = []

    print("\n--- Evaluating Variant 1: S1-mini Native (Base) ---")
    t0 = time.time()
    for i, c in enumerate(cases):
        req = c["request"]
        p = render_s1_native_prompt(req.get("transcript") or req.get("draft") or "", req.get("task", "cleanup"))
        gen, el = query_llama_server(p)
        res = evaluate_output(c, gen, "s1_mini_native_base")
        res["latency_s"] = round(el, 3)
        results_native.append(res)
        status = "PASS" if res["overall_pass"] else f"FAIL ({', '.join(res['reasons'])})"
        print(f"[{i+1:02d}/35] {c['id']} ({c.get('bucket')}): {status} ({round(el*1000)}ms)")

    print(f"\nVariant 1 completed in {round(time.time() - t0, 1)}s")

    print("\n--- Evaluating Variant 2: S1-mini VF-1 (Base) ---")
    t1 = time.time()
    for i, c in enumerate(cases):
        req = c["request"]
        p = render_vf1_chatml_prompt(req)
        gen, el = query_llama_server(p)
        res = evaluate_output(c, gen, "s1_mini_vf1_base")
        res["latency_s"] = round(el, 3)
        results_vf1_base.append(res)
        status = "PASS" if res["overall_pass"] else f"FAIL ({', '.join(res['reasons'])})"
        print(f"[{i+1:02d}/35] {c['id']} ({c.get('bucket')}): {status} ({round(el*1000)}ms)")

    print(f"\nVariant 2 completed in {round(time.time() - t1, 1)}s")

    # Aggregate Scores
    def summarize(res_list):
        n = len(res_list)
        passes = sum(1 for r in res_list if r["overall_pass"])
        factual = sum(1 for r in res_list if r["factual_preservation"])
        instr = sum(1 for r in res_list if r["instruction_adherence"])
        semantic = sum(1 for r in res_list if r["semantic_preservation"])
        formatting = sum(1 for r in res_list if r["formatting_adherence"])
        avg_lat = round(sum(r["latency_s"] for r in res_list) / n * 1000, 1)

        by_bucket = {}
        for r in res_list:
            b = r["bucket"]
            if b not in by_bucket:
                by_bucket[b] = {"total": 0, "pass": 0}
            by_bucket[b]["total"] += 1
            if r["overall_pass"]:
                by_bucket[b]["pass"] += 1

        return {
            "total_cases": n,
            "overall_pass": f"{passes}/{n} ({round(passes/n*100, 1)}%)",
            "factual_preservation": f"{factual}/{n} ({round(factual/n*100, 1)}%)",
            "instruction_adherence": f"{instr}/{n} ({round(instr/n*100, 1)}%)",
            "semantic_preservation": f"{semantic}/{n} ({round(semantic/n*100, 1)}%)",
            "formatting_adherence": f"{formatting}/{n} ({round(formatting/n*100, 1)}%)",
            "avg_latency_ms": avg_lat,
            "by_bucket": by_bucket,
        }

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "benchmark_file": str(BENCHMARK_PATH),
        "total_cases": len(cases),
        "summary": {
            "variant1_native_base": summarize(results_native),
            "variant2_vf1_base": summarize(results_vf1_base),
        },
        "results": {
            "variant1_native_base": results_native,
            "variant2_vf1_base": results_vf1_base,
        }
    }

    OUTPUT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("FINAL BENCHMARK COMPARISON SUMMARY")
    print("=" * 70)
    print(f"Variant 1 (S1-mini Native Base):  {summary['summary']['variant1_native_base']['overall_pass']} | Factual: {summary['summary']['variant1_native_base']['factual_preservation']} | Latency: {summary['summary']['variant1_native_base']['avg_latency_ms']}ms")
    print(f"Variant 2 (S1-mini VF-1 Base):    {summary['summary']['variant2_vf1_base']['overall_pass']} | Factual: {summary['summary']['variant2_vf1_base']['factual_preservation']} | Latency: {summary['summary']['variant2_vf1_base']['avg_latency_ms']}ms")
    print(f"Detailed results written to -> {OUTPUT_REPORT_PATH}")


if __name__ == "__main__":
    main()

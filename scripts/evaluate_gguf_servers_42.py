#!/usr/bin/env python3
"""Evaluate all 42 independent cases on real llama-server instances on Windows CPU.

Compares:
1. Port 8080: Baseline S1-mini GGUF (s1-mini-q4_k_m.gguf)
2. Port 8085: Candidate C.2 Merged Q4_K_M GGUF (s1-mini-vf1-run2-q4_k_m.gguf)
3. Agreement with unquantized Run 2 LoRA from logs/independent_suite_42_evaluation_report.json

Saves full machine-readable report to logs/independent_suite_42_gguf_server_report.json.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from voice_flow.vf_contract import VF1Request, render_vf1

SUITE_PATH = PROJECT_ROOT / "data" / "independent_eval_suite_42.jsonl"
OUTPUT_REPORT = PROJECT_ROOT / "logs" / "independent_suite_42_gguf_server_report.json"
PYTORCH_EVAL_REPORT = PROJECT_ROOT / "logs" / "independent_suite_42_evaluation_report.json"

def render_prompt(rec: dict) -> str:
    r = dict(rec["request"])
    req = VF1Request(**r)
    sys_prompt, user_prompt = render_vf1(req)
    return (
        f"<|im_start|>system\n{sys_prompt}<|im_end|>\n"
        f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
        f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )

def query_llama_server(port: int, prompt: str, max_tokens: int = 256) -> tuple[str, float, int]:
    url = f"http://127.0.0.1:{port}/completion"
    payload = {
        "prompt": prompt,
        "temperature": 0.0,
        "n_predict": max_tokens,
        "stop": ["<|im_end|>", "<|endoftext|>"],
        "stream": False,
        "cache_prompt": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            elapsed = time.perf_counter() - t0
            content = str(res.get("content") or "").strip()
            tokens_pred = res.get("tokens_predicted", 0)
            if content.startswith("<think>\n\n</think>\n\n"):
                content = content[len("<think>\n\n</think>\n\n"):].strip()
            return content, elapsed, tokens_pred
    except Exception as exc:
        print(f"Error querying port {port}: {exc}")
        return "", 0.0, 0

def evaluate_case(rec: dict, gen: str, variant: str) -> dict:
    bucket = rec["bucket"]
    task = rec["request"]["task"]
    target = rec["reference"]
    crit = rec.get("evaluation_criteria", "")
    passed = True
    reasons = []

    if bool(re.search(r"\[(?:Your|Recipient|Name|Company|Insert).*?\]", gen, re.IGNORECASE)):
        passed = False
        reasons.append("placeholder_leak")

    if bool(re.search(r"(\[VF-1\]|\[Task:|\[Instruction\]|\[Draft\]|\[Transcript\])", gen)):
        passed = False
        reasons.append("tag_echo")

    # Family 1: Cleanup & self-corrections
    if bucket == "cleanup_facts":
        if "5,50,000" in target and ("5,50,000" not in gen and "550,000" not in gen and "550000" not in gen):
            passed = False
            reasons.append("failed_inr_self_correction")
        if "Do not transfer" in target and ("do not" not in gen.lower() and "don't" not in gen.lower()):
            passed = False
            reasons.append("failed_negation_preservation")
        if "/var/log/redis/redis.log" in target and "/var/log/redis/redis.log" not in gen:
            passed = False
            reasons.append("failed_file_path")
        if "11:15" in target and "11:15" not in gen:
            passed = False
            reasons.append("failed_time_self_correction")

    # Family 2: Professional Emails & Messages
    elif bucket == "email":
        if "Subject:" in target:
            if "Subject:" not in gen:
                passed = False
                reasons.append("missing_subject_header")
            else:
                lines = [l.strip() for l in gen.splitlines() if l.strip()]
                if not lines[0].startswith("Subject:"):
                    passed = False
                    reasons.append("subject_not_first_line")
        if "Marcus" in target and "Marcus" not in gen:
            passed = False
            reasons.append("missing_sender_Marcus")
        if "Devon Vance" in target and "Devon" not in gen:
            passed = False
            reasons.append("missing_sender_Devon")

    elif bucket == "messages":
        if "SOC 2 Type II" in target and ("soc 2" not in gen.lower() or "type ii" not in gen.lower() and "type 2" not in gen.lower()):
            passed = False
            reasons.append("failed_soc2_preservation")

    # Family 3: AI Prompt Synthesis
    elif bucket == "prompt":
        for echo_prefix in [
            "can you make me a prompt for", "tell claude to", "i want an instruction for",
            "give me a prompt to", "could you write an ai prompt that", "ask the ai to",
            "write me a prompt", "design a prompt"
        ]:
            if gen.lower().startswith(echo_prefix):
                passed = False
                reasons.append("meta_wrapper_echo")
                break
        first_word = gen.split()[0].rstrip(",:").lower() if gen.split() else ""
        imperative_verbs = {
            "extract", "write", "draft", "design", "create", "generate", "build", "a", "an",
            "compose", "summarize", "refactor", "implement", "analyze", "review", "outline"
        }
        if first_word not in imperative_verbs:
            passed = False
            reasons.append("non_imperative_prompt_start")

    # Family 4: Structured Notes & Checklists
    elif bucket == "notes_format":
        bullet_lines = [l for l in gen.splitlines() if l.strip().startswith(("-", "*", "•", "1.", "2.", "3.", "[ ]"))]
        if len(bullet_lines) < 2 and "\n" not in gen:
            passed = False
            reasons.append("failed_list_formatting")

    # Family 5: Executive Summaries
    elif bucket == "summary":
        if "$12.4" in target and ("12.4" not in gen and "12,400,000" not in gen and "12.4M" not in gen):
            passed = False
            reasons.append("failed_metric_12.4M")
        if "22%" in target and "22%" not in gen:
            passed = False
            reasons.append("failed_metric_22pct")

    # Family 6 & 7: Follow-up editing & tone changes
    elif bucket == "followup_style":
        if "Friday at 11:30 AM" in target and ("friday" not in gen.lower() or "11:30" not in gen):
            passed = False
            reasons.append("failed_draft_edit_preservation")
        if "Devon Vance" in target and "Devon" not in gen:
            passed = False
            reasons.append("failed_co_presenter_addition")
        if "remove the initial deposit sentence" in crit and "$4,000" in gen:
            passed = False
            reasons.append("failed_deletion_of_deposit")

    return {
        "case_id": rec["id"],
        "bucket": bucket,
        "task": task,
        "variant": variant,
        "raw_output": gen,
        "reference": target,
        "passed": passed,
        "reasons": reasons,
        "criteria": crit,
    }

def main():
    print("=" * 70)
    print("Independent 42-Case GGUF Server Benchmark")
    print("Port 8080: Baseline S1-mini GGUF")
    print("Port 8085: Candidate C.2 Merged Q4_K_M GGUF")
    print("=" * 70)

    with open(SUITE_PATH, "r", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]

    print(f"Loaded {len(cases)} cases from {SUITE_PATH}")

    # Load unquantized PyTorch results for comparison
    pytorch_ref = {}
    if os.path.exists(PYTORCH_EVAL_REPORT):
        try:
            pt_data = json.load(open(PYTORCH_EVAL_REPORT, "r", encoding="utf-8"))
            for r in pt_data["raw_results"].get("run2_strengthened", []):
                pytorch_ref[r["case_id"]] = r["raw_output"]
        except Exception:
            pass

    results_base = []
    results_cand = []
    latencies_base = []
    latencies_cand = []

    print("\nStarting real inference runs...")
    for idx, c in enumerate(cases, 1):
        cid = c["id"]
        prompt = render_prompt(c)

        # Baseline GGUF (8080)
        out_b, t_b, toks_b = query_llama_server(8080, prompt)
        eval_b = evaluate_case(c, out_b, "Baseline S1-mini GGUF (Port 8080)")
        eval_b["latency_ms"] = round(t_b * 1000, 1)
        eval_b["tokens"] = toks_b
        results_base.append(eval_b)
        latencies_base.append(t_b * 1000)

        # Candidate C.2 GGUF (8085)
        out_c, t_c, toks_c = query_llama_server(8085, prompt)
        eval_c = evaluate_case(c, out_c, "Candidate C.2 Q4_K_M GGUF (Port 8085)")
        eval_c["latency_ms"] = round(t_c * 1000, 1)
        eval_c["tokens"] = toks_c
        results_cand.append(eval_c)
        latencies_cand.append(t_c * 1000)

        pt_match = (out_c.strip() == pytorch_ref.get(cid, "").strip())
        print(f"[{idx:02d}/42] {cid} [{c['bucket']}]: Base {'PASS' if eval_b['passed'] else 'FAIL'} ({t_b*1000:.0f}ms) | Cand {'PASS' if eval_c['passed'] else 'FAIL'} ({t_c*1000:.0f}ms) | PT-Match: {pt_match}")

    base_pass = sum(1 for r in results_base if r["passed"])
    cand_pass = sum(1 for r in results_cand if r["passed"])

    print("\n" + "=" * 70)
    print("FINAL RESULTS SUMMARY")
    print(f"Baseline S1-mini GGUF (Port 8080): {base_pass} / 42 passed ({base_pass/42*100:.1f}%) | Avg Latency: {sum(latencies_base)/len(latencies_base):.1f}ms")
    print(f"Candidate C.2 Q4_K_M (Port 8085):   {cand_pass} / 42 passed ({cand_pass/42*100:.1f}%) | Avg Latency: {sum(latencies_cand)/len(latencies_cand):.1f}ms")
    print("=" * 70)

    # Per-family breakdown
    families = sorted(list(set(c["bucket"] for c in cases)))
    breakdown_base = {}
    breakdown_cand = {}
    for f_name in families:
        b_p = sum(1 for r in results_base if r["bucket"] == f_name and r["passed"])
        b_t = sum(1 for r in results_base if r["bucket"] == f_name)
        breakdown_base[f_name] = {"passed": b_p, "total": b_t, "pct": round(b_p/b_t*100, 1)}

        c_p = sum(1 for r in results_cand if r["bucket"] == f_name and r["passed"])
        c_t = sum(1 for r in results_cand if r["bucket"] == f_name)
        breakdown_cand[f_name] = {"passed": c_p, "total": c_t, "pct": round(c_p/c_t*100, 1)}

    report_data = {
        "timestamp": "2026-10-15T10:35:00Z",
        "suite_file": str(SUITE_PATH),
        "total_cases": len(cases),
        "servers": {
            "baseline": {
                "port": 8080,
                "model": "C:\\Users\\Asus\\.voice_flow\\models\\s1-mini-q4_k_m.gguf",
                "passed": base_pass,
                "total": len(cases),
                "pass_rate_pct": round(base_pass / len(cases) * 100, 1),
                "avg_latency_ms": round(sum(latencies_base) / len(latencies_base), 1),
                "by_family": breakdown_base
            },
            "candidate_c2_q4": {
                "port": 8085,
                "model": "runs/clean_multitask_lora_run2/gguf/s1-mini-vf1-run2-q4_k_m.gguf",
                "passed": cand_pass,
                "total": len(cases),
                "pass_rate_pct": round(cand_pass / len(cases) * 100, 1),
                "avg_latency_ms": round(sum(latencies_cand) / len(latencies_cand), 1),
                "by_family": breakdown_cand
            }
        },
        "raw_results": {
            "baseline": results_base,
            "candidate_c2_q4": results_cand
        }
    }

    os.makedirs(OUTPUT_REPORT.parent, exist_ok=True)
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    print(f"Report saved to {OUTPUT_REPORT}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Evaluate all candidates on the new independent 42-case evaluation suite.

Evaluates:
1. S1-mini Base (superwhisper/s1-mini @ 88f6b15896c7)
2. Preserved Run 1 LoRA (runs/clean_multitask_lora_run1/adapter)
3. Strengthened Run 2 LoRA (runs/clean_multitask_lora_run2/adapter)

Deterministic greedy decoding (temperature=None, do_sample=False, max_new_tokens=256).
Generates side-by-side comparative scoring and records raw outputs for manual review.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from voice_flow.vf_contract import VF1Request, render_vf1

SUITE_PATH = PROJECT_ROOT / "data" / "independent_eval_suite_42.jsonl"
BASE_REPO = "superwhisper/s1-mini"
BASE_REVISION = "88f6b15896c73bbb13a3b596e0afe8ea0d5150b4"
OUTPUT_REPORT = PROJECT_ROOT / "logs" / "independent_suite_42_evaluation_report.json"

IM_START, IM_END, ENDOFTEXT = 151644, 151645, 151643
PAD_ID = ENDOFTEXT


def render_prompt(rec: dict) -> str:
    r = dict(rec["request"])
    req = VF1Request(**r)
    sys_prompt, user_prompt = render_vf1(req)
    return (
        f"<|im_start|>system\n{sys_prompt}<|im_end|>\n"
        f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
        f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )


def evaluate_case(rec: dict, gen: str, variant: str) -> dict:
    bucket = rec["bucket"]
    task = rec["request"]["task"]
    target = rec["reference"]
    heightened = rec.get("heightened", [])
    crit = rec.get("evaluation_criteria", "")

    passed = True
    reasons = []

    # Check for placeholder leaks
    if bool(re.search(r"\[(?:Your|Recipient|Name|Company|Insert).*?\]", gen, re.IGNORECASE)):
        passed = False
        reasons.append("placeholder_leak")

    # Check for tag echoes
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
                if len(lines) < 2:
                    passed = False
                    reasons.append("subject_not_separated")
        if rec["request"].get("sender"):
            sender = rec["request"]["sender"]
            if sender.lower() not in gen.lower():
                passed = False
                reasons.append(f"missing_sender_{sender}")

    elif bucket == "messages":
        if rec["request"].get("recipient"):
            recip = rec["request"]["recipient"]
            if recip.lower() not in gen.lower():
                passed = False
                reasons.append(f"missing_recipient_{recip}")

    # Family 3: Actionable AI Prompts
    elif bucket == "prompt":
        gen_lower = gen.lower().strip()
        # Direct check for conversational meta-wrappers
        meta_prefixes = [
            "can you make", "could you make", "make me a prompt", "tell claude to",
            "tell chatgpt to", "tell gpt", "i want an instruction", "write me a prompt",
            "give me a prompt", "could you write a prompt", "make a prompt", "ask the ai",
            "ask claude", "create a prompt for", "i need a prompt"
        ]
        if any(gen_lower.startswith(p) for p in meta_prefixes):
            passed = False
            reasons.append("meta_wrapper_echo")
        # Check required entities/formats
        if "json" in target.lower() and "json" not in gen_lower:
            passed = False
            reasons.append("missing_json_format_directive")
        if "pandas" in target.lower() and "pandas" not in gen_lower:
            passed = False
            reasons.append("missing_pandas_directive")

    # Family 4: Lists & Notes
    elif bucket == "notes_format":
        if rec["request"].get("format") in ("bullets", "numbered"):
            if "-" not in gen and "1." not in gen and "•" not in gen:
                passed = False
                reasons.append("not_formatted_as_list")
        if "Verify SSL certificates" in target and "Verify SSL\n- Certificates" in gen:
            passed = False
            reasons.append("broken_action_object_segmentation")

    # Family 5: Summarization
    elif bucket == "summary":
        if "remains unresolved" in target.lower() or "unfixed" in target.lower():
            if "resolved" in gen.lower() and "unresolved" not in gen.lower() and "not" not in gen.lower() and "remains" not in gen.lower():
                passed = False
                reasons.append("status_corruption_open_to_resolved")
        if "Alex" in target and "Alex" not in gen:
            passed = False
            reasons.append("missing_owner_alex")

    # Family 6 & 7: Rewriting & Editing
    elif bucket == "followup_style":
        if task == "edit":
            # Must read draft and apply change to draft
            if "Friday at 11:30 AM in the main auditorium" in target:
                if "Friday" not in gen or "11:30" not in gen or "auditorium" not in gen:
                    passed = False
                    reasons.append("failed_draft_edit_preservation")
            if "Elena Rostova and Devon Vance" in target:
                if "Devon" not in gen or "Elena" not in gen or "Boardroom" not in gen:
                    passed = False
                    reasons.append("failed_co_presenter_addition")
            if "16,500.00" in target:
                if "16,500" not in gen:
                    passed = False
                    reasons.append("failed_amount_update")
                if "July" in gen or "initial deposit" in gen.lower():
                    passed = False
                    reasons.append("failed_deletion_of_deposit")
            if "8443" in target:
                if "8443" not in gen or "HTTPS" not in gen:
                    passed = False
                    reasons.append("failed_port_or_https_edit")
        elif task == "rewrite":
            if "depends on legal" in target.lower() or "depends entirely" in target.lower():
                if "depends" not in gen.lower():
                    passed = False
                    reasons.append("dropped_hedge_or_condition")

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


def evaluate_model(model, tok, cases, variant_name):
    print(f"\n--- Evaluating {variant_name} on 42-Case Independent Suite ---")
    results = []
    t0 = time.time()
    for i, c in enumerate(cases):
        prompt_text = render_prompt(c)
        input_ids = tok(prompt_text, return_tensors="pt")["input_ids"]
        t_case0 = time.time()
        with torch.no_grad():
            out = model.generate(
                input_ids=input_ids,
                max_new_tokens=256,
                do_sample=False,
                eos_token_id=[IM_END, ENDOFTEXT],
                pad_token_id=PAD_ID,
            )
        el = time.time() - t_case0
        gen_tokens = out[0, input_ids.shape[1]:].tolist()
        gen_text = tok.decode([t for t in gen_tokens if t not in (IM_END, ENDOFTEXT)], skip_special_tokens=False).strip()

        res = evaluate_case(c, gen_text, variant_name)
        res["latency_ms"] = round(el * 1000, 1)
        results.append(res)

        status_str = "PASS" if res["passed"] else f"FAIL ({', '.join(res['reasons'])})"
        print(f"[{i+1:02d}/42] {c['id']} ({c['bucket']}): {status_str} ({round(el*1000)}ms)")

    total_time = round(time.time() - t0, 1)
    n_pass = sum(1 for r in results if r["passed"])
    print(f"\n{variant_name} completed in {total_time}s: {n_pass}/42 passed ({n_pass/42*100:.1f}%)")
    return results


def main():
    if not SUITE_PATH.exists():
        sys.exit(f"Independent suite missing: {SUITE_PATH}")

    cases = [json.loads(l) for l in open(SUITE_PATH, encoding="utf-8") if l.strip()]
    print(f"Loaded {len(cases)} cases from independent evaluation suite.")

    tok = AutoTokenizer.from_pretrained(BASE_REPO, revision=BASE_REVISION)
    torch.set_num_threads(8)

    # 1. Base Model Evaluation
    print(f"\nLoading Base Model ({BASE_REPO} @ {BASE_REVISION[:12]})...")
    base_model = AutoModelForCausalLM.from_pretrained(BASE_REPO, revision=BASE_REVISION, dtype=torch.float32)
    base_results = evaluate_model(base_model, tok, cases, "Candidate A: S1-mini Base")

    # 2. Run 1 LoRA Evaluation
    run1_path = PROJECT_ROOT / "runs" / "clean_multitask_lora_run1" / "adapter"
    if run1_path.exists():
        print(f"\nAttaching Run 1 LoRA Adapter from {run1_path}...")
        model_run1 = PeftModel.from_pretrained(base_model, str(run1_path)).eval()
        run1_results = evaluate_model(model_run1, tok, cases, "Candidate B: Run 1 LoRA (Preserved)")
        del model_run1

    # 3. Run 2 LoRA Evaluation (Strengthened)
    run2_path = PROJECT_ROOT / "runs" / "clean_multitask_lora_run2" / "adapter"
    run2_results = []
    if run2_path.exists():
        print(f"\nAttaching Run 2 LoRA Adapter from {run2_path}...")
        model_run2 = PeftModel.from_pretrained(base_model, str(run2_path)).eval()
        run2_results = evaluate_model(model_run2, tok, cases, "Candidate C.2: Strengthened LoRA (Run 2)")
        del model_run2
    else:
        print(f"\nNote: Run 2 adapter path {run2_path} not found yet (training in progress).")

    # Summary
    def summarize(res_list):
        if not res_list:
            return None
        n = len(res_list)
        p = sum(1 for r in res_list if r["passed"])
        by_fam = {}
        for r in res_list:
            fam = r["bucket"]
            if fam not in by_fam:
                by_fam[fam] = {"passed": 0, "total": 0}
            by_fam[fam]["total"] += 1
            if r["passed"]:
                by_fam[fam]["passed"] += 1
        return {"total": n, "passed": p, "pass_rate_pct": round(p / n * 100, 1), "by_family": by_fam}

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "suite_file": str(SUITE_PATH),
        "total_cases": len(cases),
        "summary": {
            "candidate_base": summarize(base_results),
            "candidate_run1_lora": summarize(run1_results) if run1_path.exists() else None,
            "candidate_run2_strengthened_lora": summarize(run2_results) if run2_path.exists() else None,
        },
        "raw_results": {
            "base": base_results,
            "run1_lora": run1_results if run1_path.exists() else [],
            "run2_strengthened_lora": run2_results if run2_path.exists() else [],
        },
    }

    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull evaluation report saved -> {OUTPUT_REPORT}")


if __name__ == "__main__":
    main()

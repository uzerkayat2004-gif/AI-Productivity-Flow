#!/usr/bin/env python3
"""Evaluate Candidate C (Newly Trained S1-mini LoRA) on the frozen 35-case benchmark.

Loads the authentic superwhisper/s1-mini base model + the trained LoRA adapter from
runs/clean_multitask_lora_run1/adapter.
Evaluates using deterministic greedy decoding under the universal VF-1 contract v1.2.
Compares side-by-side with Candidate A (S1 Native Base) and Candidate B (S1 VF-1 Base).
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

BENCHMARK_PATH = PROJECT_ROOT / "data" / "frozen_eval_multitask_35.jsonl"
ADAPTER_PATH = PROJECT_ROOT / "runs" / "clean_multitask_lora_run1" / "adapter"
BASE_REPO = "superwhisper/s1-mini"
BASE_REVISION = "88f6b15896c73bbb13a3b596e0afe8ea0d5150b4"
OUTPUT_PATH = PROJECT_ROOT / "logs" / "benchmark_candidate_c_lora_results.json"
THREE_WAY_OUTPUT_PATH = PROJECT_ROOT / "logs" / "benchmark_three_way_comparison.json"

IM_START, IM_END, ENDOFTEXT = 151644, 151645, 151643
PAD_ID = ENDOFTEXT


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

    has_placeholder = bool(re.search(r"\[(?:Your|Recipient|Name|Company).*?\]", gen, re.IGNORECASE))
    has_tag_echo = bool(re.search(r"(\[VF-1\]|\[Task:|\[Styling:|\[Structure:)", gen))

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
                sub_lines = [l.strip() for l in gen.splitlines() if l.strip()]
                if len(sub_lines) < 2:
                    formatting_adherence = False
                    reasons.append("subject_not_separated_from_body")
        if req.get("sender"):
            sender = req["sender"]
            if sender.lower() not in gen.lower():
                factual_preservation = False
                reasons.append(f"lost_sender_identity_{sender}")

    # Family 3: Actionable Prompts (Meta-wrapper stripping)
    if task == "prompt":
        if gen.lower().startswith("create a prompt") or gen.lower().startswith("write a prompt") or gen.lower().startswith("make a prompt") or gen.lower().startswith("generate a prompt"):
            instruction_adherence = False
            reasons.append("meta_wrapper_echo")

    # Family 4: Lists & Notes
    if req.get("format") == "bullets":
        if "Verify health endpoint" in target and "Verify health\n- Endpoint" in gen:
            semantic_preservation = False
            reasons.append("broken_action_object_segmentation")
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

    # Family 7: Follow-up editing (Surgical edits)
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
    print("CANDIDATE C (S1-MINI NEWLY TRAINED LORA) BENCHMARK EVALUATION")
    print("=" * 70)

    if not ADAPTER_PATH.exists():
        sys.exit(f"LoRA adapter path not found: {ADAPTER_PATH}")
    if not BENCHMARK_PATH.exists():
        sys.exit(f"Benchmark file not found: {BENCHMARK_PATH}")

    cases = [json.loads(line) for line in open(BENCHMARK_PATH, encoding="utf-8") if line.strip()]
    print(f"Loaded {len(cases)} frozen evaluation cases.")

    print(f"Loading tokenizer: {BASE_REPO}...")
    tok = AutoTokenizer.from_pretrained(BASE_REPO, revision=BASE_REVISION)

    print(f"Loading base model: {BASE_REPO} @ {BASE_REVISION[:12]}...")
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_REPO,
        revision=BASE_REVISION,
        dtype=torch.float32,
    )

    print(f"Attaching LoRA adapter from {ADAPTER_PATH}...")
    model = PeftModel.from_pretrained(base_model, str(ADAPTER_PATH))
    model.eval()

    torch.set_num_threads(8)

    print("\nEvaluating Candidate C on Frozen 35-Case Benchmark (Deterministic Greedy)...")
    results = []
    t0 = time.time()

    for i, c in enumerate(cases):
        req = c["request"]
        p_text = render_vf1_chatml_prompt(req)
        input_ids = tok(p_text, return_tensors="pt")["input_ids"]

        t_gen0 = time.time()
        with torch.no_grad():
            out = model.generate(
                input_ids=input_ids,
                max_new_tokens=256,
                do_sample=False,
                eos_token_id=[IM_END, ENDOFTEXT],
                pad_token_id=PAD_ID,
            )
        el = time.time() - t_gen0

        gen_tokens = out[0, input_ids.shape[1]:].tolist()
        gen_text = tok.decode([t for t in gen_tokens if t not in (IM_END, ENDOFTEXT)], skip_special_tokens=False).strip()

        eval_res = evaluate_output(c, gen_text, "s1_mini_vf1_lora_candidate_c")
        eval_res["latency_s"] = round(el, 3)
        results.append(eval_res)

        status = "PASS" if eval_res["overall_pass"] else f"FAIL ({', '.join(eval_res['reasons'])})"
        print(f"[{i+1:02d}/35] {c['id']} ({c.get('bucket')}): {status} ({round(el*1000)}ms)")

    total_time = round(time.time() - t0, 1)
    print(f"\nCandidate C evaluation completed in {total_time}s.")

    # Calculate summary
    n = len(results)
    passes = sum(1 for r in results if r["overall_pass"])
    factual = sum(1 for r in results if r["factual_preservation"])
    instruction = sum(1 for r in results if r["instruction_adherence"])
    formatting = sum(1 for r in results if r["formatting_adherence"])
    avg_latency = round(sum(r["latency_s"] for r in results) / n * 1000, 1)

    summary_c = {
        "variant": "s1_mini_vf1_lora_candidate_c",
        "total_cases": n,
        "overall_passed": passes,
        "pass_rate_pct": round(passes / n * 100, 1),
        "factual_preservation_passed": factual,
        "factual_preservation_pct": round(factual / n * 100, 1),
        "instruction_adherence_passed": instruction,
        "instruction_adherence_pct": round(instruction / n * 100, 1),
        "formatting_adherence_passed": formatting,
        "formatting_adherence_pct": round(formatting / n * 100, 1),
        "avg_latency_ms": avg_latency,
        "family_scores": {},
    }

    # Per-family scores
    families = set(r["bucket"] for r in results)
    for fam in sorted(families):
        fam_res = [r for r in results if r["bucket"] == fam]
        fam_pass = sum(1 for r in fam_res if r["overall_pass"])
        summary_c["family_scores"][fam] = {
            "passed": fam_pass,
            "total": len(fam_res),
            "pass_rate_pct": round(fam_pass / len(fam_res) * 100, 1),
        }

    output_payload = {
        "summary": summary_c,
        "results": results,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)
    print(f"Candidate C results written to -> {OUTPUT_PATH}")

    # Now load Candidate A and B from logs/benchmark_multitask_35_results.json if present
    base_results_path = PROJECT_ROOT / "logs" / "benchmark_multitask_35_results.json"
    if base_results_path.exists():
        base_data = json.loads(base_results_path.read_text(encoding="utf-8"))
        three_way = {
            "candidate_a_native_base": base_data.get("summary_native"),
            "candidate_b_vf1_base": base_data.get("summary_vf1_base"),
            "candidate_c_new_lora": summary_c,
            "comparison_table": {
                "metric": ["Overall Pass Rate", "Factual Preservation", "Instruction Adherence", "Average Latency (ms)"],
                "candidate_a": [
                    f"{base_data['summary_native']['overall_passed']}/35 ({base_data['summary_native']['pass_rate_pct']}%)",
                    f"{base_data['summary_native']['factual_preservation_passed']}/35 ({base_data['summary_native']['factual_preservation_pct']}%)",
                    f"{base_data['summary_native']['instruction_adherence_passed']}/35 ({base_data['summary_native']['instruction_adherence_pct']}%)",
                    f"{base_data['summary_native']['avg_latency_ms']} ms",
                ],
                "candidate_b": [
                    f"{base_data['summary_vf1_base']['overall_passed']}/35 ({base_data['summary_vf1_base']['pass_rate_pct']}%)",
                    f"{base_data['summary_vf1_base']['factual_preservation_passed']}/35 ({base_data['summary_vf1_base']['factual_preservation_pct']}%)",
                    f"{base_data['summary_vf1_base']['instruction_adherence_passed']}/35 ({base_data['summary_vf1_base']['instruction_adherence_pct']}%)",
                    f"{base_data['summary_vf1_base']['avg_latency_ms']} ms",
                ],
                "candidate_c": [
                    f"{summary_c['overall_passed']}/35 ({summary_c['pass_rate_pct']}%)",
                    f"{summary_c['factual_preservation_passed']}/35 ({summary_c['factual_preservation_pct']}%)",
                    f"{summary_c['instruction_adherence_passed']}/35 ({summary_c['instruction_adherence_pct']}%)",
                    f"{summary_c['avg_latency_ms']} ms",
                ],
            },
        }
        with open(THREE_WAY_OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(three_way, f, indent=2)
        print(f"Three-way comparison recorded to -> {THREE_WAY_OUTPUT_PATH}")

    print("\n" + "=" * 70)
    print("THREE-WAY COMPARISON SUMMARY")
    print("=" * 70)
    print(f"Candidate A (S1 Native Base): {base_data['summary_native']['overall_passed']}/35 ({base_data['summary_native']['pass_rate_pct']}%)")
    print(f"Candidate B (S1 VF-1 Base):   {base_data['summary_vf1_base']['overall_passed']}/35 ({base_data['summary_vf1_base']['pass_rate_pct']}%)")
    print(f"Candidate C (S1 LoRA Clean): {summary_c['overall_passed']}/35 ({summary_c['pass_rate_pct']}%)")
    print("=" * 70)


if __name__ == "__main__":
    main()

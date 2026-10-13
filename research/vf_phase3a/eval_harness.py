#!/usr/bin/env python3
"""VF-1 Model-Quality Evaluation Harness (Phase 3A / Evaluation Readiness).

Evaluates model outputs under the strict Universal Voice Flow contract (v1.2)
and model-specific chat templates, supporting comparative analysis of:
  - Base superwhisper/s1-mini
  - s1-mini + LoRA adapter
  - Qwen/Qwen3-0.6B baseline

Measures:
  - Factual preservation (currency, numbers, dates, times, proper nouns, IDs)
  - Self-corrections vs genuine alternatives
  - Negation preservation (do not, never, won't)
  - Filler / disfluency cleanup
  - Email formatting, prompt synthesis, and instruction adherence
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "research", "vf_phase2a", "scripts"))

from voice_flow.vf_contract import VF1Request, render_vf1
from voice_flow.vf_checks import check_output


@dataclass
class EvalRecordResult:
    id: str
    slice: str
    transcript: str
    reference: str
    generated: str
    passed: bool
    assertions_passed: bool
    checker_passed: bool
    checker_errors: List[str]
    missing_required: List[str]
    forbidden_included: List[str]


@dataclass
class SliceScore:
    slice_name: str
    total_records: int
    passed_records: int
    pass_rate: float
    assertion_pass_rate: float
    checker_pass_rate: float


def load_eval_dataset(path: str) -> List[Dict[str, Any]]:
    """Load evaluation records from a JSONL file."""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Malformed JSONL on line {line_no} in {path}: {exc}")
    return records


def format_vf1_prompt(tok, record: Dict[str, Any]) -> Tuple[str, List[int]]:
    """Format an evaluation record using the VF-1 contract and model chat template."""
    req_dict = record["request"]
    rules_val = req_dict.get("style_rules") or req_dict.get("rules") or ()
    if isinstance(rules_val, list):
        rules_val = tuple(rules_val)
    elif isinstance(rules_val, str):
        rules_val = (rules_val,)
    req = VF1Request(
        transcript=req_dict.get("transcript", ""),
        task=req_dict.get("task", "cleanup"),
        instruction=req_dict.get("instruction"),
        rules=rules_val,
        context=req_dict.get("context", "general"),
    )
    system_text, user_text = render_vf1(req)

    # Apply model chat template
    if hasattr(tok, "apply_chat_template"):
        prompt_text = tok.apply_chat_template(
            [{"role": "system", "content": system_text}, {"role": "user", "content": user_text}],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
    else:
        # Fallback chat formatting if tokenizer lacks template
        prompt_text = f"<|im_start|>system\n{system_text}<|im_end|>\n<|im_start|>user\n{user_text}<|im_end|>\n<|im_start|>assistant\n"

    input_ids = tok.encode(prompt_text)
    if hasattr(input_ids, "ids"):
        input_ids = input_ids.ids
    return prompt_text, input_ids


def evaluate_output(record: Dict[str, Any], output_text: str) -> EvalRecordResult:
    """Evaluate generated model output against deterministic assertions and fact checker."""
    req_dict = record["request"]
    transcript = req_dict.get("transcript", "")
    reference = record.get("reference", "")
    assertions = record.get("assertions", {})

    must_include = assertions.get("must_include", [])
    must_not_include = assertions.get("must_not_include", [])

    missing = [req for req in must_include if req.lower() not in output_text.lower()]
    forbidden = [forbid for forbid in must_not_include if forbid.lower() in output_text.lower()]

    assertions_ok = (len(missing) == 0) and (len(forbidden) == 0)

    # Run deterministic fact and safety checker
    task = req_dict.get("task", "cleanup")
    check_res = check_output(output_text, transcript, task=task)
    checker_ok = check_res.ok
    checker_errors = check_res.failures

    passed = assertions_ok and checker_ok

    return EvalRecordResult(
        id=record.get("id", "UNKNOWN"),
        slice=record.get("slice", "general"),
        transcript=transcript,
        reference=reference,
        generated=output_text.strip(),
        passed=passed,
        assertions_passed=assertions_ok,
        checker_passed=checker_ok,
        checker_errors=checker_errors,
        missing_required=missing,
        forbidden_included=forbidden,
    )


def compute_slice_metrics(results: List[EvalRecordResult]) -> Dict[str, SliceScore]:
    """Aggregate per-slice evaluation statistics."""
    by_slice = defaultdict(list)
    for r in results:
        by_slice[r.slice].append(r)

    scores = {}
    for slice_name, items in by_slice.items():
        total = len(items)
        passed = sum(1 for r in items if r.passed)
        assert_passed = sum(1 for r in items if r.assertions_passed)
        chk_passed = sum(1 for r in items if r.checker_passed)
        scores[slice_name] = SliceScore(
            slice_name=slice_name,
            total_records=total,
            passed_records=passed,
            pass_rate=round(passed / total, 4) if total else 0.0,
            assertion_pass_rate=round(assert_passed / total, 4) if total else 0.0,
            checker_pass_rate=round(chk_passed / total, 4) if total else 0.0,
        )
    return scores


def run_evaluation_on_generator(
    dataset_path: str,
    tokenizer,
    generate_fn: Callable[[str, List[int]], str],
    candidate_name: str = "Candidate Model",
) -> Dict[str, Any]:
    """Run complete evaluation using a custom generation function."""
    records = load_eval_dataset(dataset_path)
    t0 = time.time()
    results = []

    for rec in records:
        prompt_text, input_ids = format_vf1_prompt(tokenizer, rec)
        gen_text = generate_fn(prompt_text, input_ids)
        res = evaluate_output(rec, gen_text)
        results.append(res)

    elapsed = round(time.time() - t0, 2)
    slice_scores = compute_slice_metrics(results)

    total_records = len(results)
    total_passed = sum(1 for r in results if r.passed)
    overall_pass_rate = round(total_passed / total_records, 4) if total_records else 0.0

    return {
        "candidate": candidate_name,
        "dataset": os.path.basename(dataset_path),
        "total_records": total_records,
        "total_passed": total_passed,
        "overall_pass_rate": overall_pass_rate,
        "elapsed_seconds": elapsed,
        "slice_metrics": {k: asdict(v) for k, v in slice_scores.items()},
        "records": [asdict(r) for r in results],
    }


def render_markdown_report(eval_summary: Dict[str, Any]) -> str:
    """Render a clean GitHub-style markdown summary of the evaluation report."""
    md = []
    md.append(f"# Voice Flow Model Evaluation: {eval_summary['candidate']}\n")
    md.append(f"- **Dataset:** `{eval_summary['dataset']}` ({eval_summary['total_records']} records)")
    md.append(f"- **Overall Pass Rate:** **{eval_summary['overall_pass_rate'] * 100:.1f}%** ({eval_summary['total_passed']}/{eval_summary['total_records']} passed)")
    md.append(f"- **Evaluation Duration:** {eval_summary['elapsed_seconds']}s\n")
    md.append("## Slice Breakdown\n")
    md.append("| Slice | Records | Passed | Pass Rate | Assertion Pass | Checker Pass |")
    md.append("|---|:---:|:---:|:---:|:---:|:---:|")

    for s_name, s_data in eval_summary["slice_metrics"].items():
        md.append(
            f"| **{s_name}** | {s_data['total_records']} | {s_data['passed_records']} | "
            f"{s_data['pass_rate'] * 100:.1f}% | {s_data['assertion_pass_rate'] * 100:.1f}% | "
            f"{s_data['checker_pass_rate'] * 100:.1f}% |"
        )
    return "\n".join(md)

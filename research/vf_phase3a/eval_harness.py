#!/usr/bin/env python3
"""VF-1 Model-Quality Evaluation Harness (Phase 3A / Evaluation Readiness).

Evaluates model outputs under the strict Universal Voice Flow contract (v1.2)
and native S1-mini prompts, supporting comparative analysis of:
  1. Original S1-mini with its native prompt and non-thinking mode
  2. Base S1-mini with the VF-1 contract
  3. S1-mini with the trained VF-1 LoRA adapter

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
import re
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "research", "vf_phase2a", "scripts"))

from voice_flow.vf_contract import VF1Request, render_vf1
from voice_flow.vf_checks import check_output


S1_NATIVE_SYSTEM = (
    "You are a text normalizer for speech-to-text transcripts. "
    "The input begins with a control line specifying the styling, "
    "structure, and context settings; clean the transcript to match "
    "those settings and output only the cleaned text."
)


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
    factual_passed: bool = True
    instruction_passed: bool = True
    semantic_passed: bool = True
    formatting_passed: bool = True
    adjudication_notes: List[str] = field(default_factory=list)


@dataclass
class SliceScore:
    slice_name: str
    total_records: int
    passed_records: int
    pass_rate: float
    assertion_pass_rate: float
    checker_pass_rate: float
    factual_pass_rate: float = 1.0
    instruction_pass_rate: float = 1.0


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
    """Format an evaluation record using the VF-1 contract and model chat template.
    
    CRITICAL: Expected reference answer and assertions are NEVER included in the input prompt.
    """
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


def format_s1_native_prompt(tok, record: Dict[str, Any]) -> Tuple[str, List[int]]:
    """Format an evaluation record using original S1 native prompt and non-thinking mode.
    
    CRITICAL: Expected reference answer and assertions are NEVER included in the input prompt.
    """
    req_dict = record["request"]
    transcript = req_dict.get("transcript", "").strip()
    task = req_dict.get("task", "cleanup")
    control = "cleanup" if task == "cleanup" else f"cleanup, task: {task}"
    prompt_text = (
        f"<|im_start|>system\n{S1_NATIVE_SYSTEM}<|im_end|>\n"
        f"<|im_start|>user\n{control}\n{transcript}<|im_end|>\n"
        f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )
    input_ids = tok.encode(prompt_text)
    if hasattr(input_ids, "ids"):
        input_ids = input_ids.ids
    return prompt_text, input_ids


_NUM_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50"
}


def normalize_text_for_fact_check(text: str) -> str:
    """Normalize commas between digits and common spoken number equivalents."""
    if not text:
        return ""
    # Strip thousands / Indian digit grouping commas between digits: e.g. 4,20,000 -> 420000, 75,000 -> 75000
    t = re.sub(r"(?<=\d),(?=\d)", "", text)
    # Normalize 3:30pm -> 3:30 pm
    t = re.sub(r"(\d+:\d{2})\s*([ap]m)\b", r"\1 \2", t, flags=re.IGNORECASE)
    return t


def check_term_present(term: str, text: str) -> bool:
    """Check if required term is present, supporting normalized number/currency formats."""
    norm_term = normalize_text_for_fact_check(term).lower()
    norm_text = normalize_text_for_fact_check(text).lower()
    if norm_term in norm_text:
        return True
    # Word-to-digit equivalence: e.g. "5 copies" vs "five copies"
    words_term = norm_term.split()
    words_text = norm_text.split()
    converted_term = " ".join(_NUM_WORDS.get(w, w) for w in words_term)
    converted_text = " ".join(_NUM_WORDS.get(w, w) for w in words_text)
    return converted_term in converted_text


def check_term_forbidden(term: str, text: str) -> bool:
    """Check if forbidden term is present using strict token/word boundaries.
    
    Prevents false negatives:
    - 'Sara' does not match within 'Sarah'
    - 'TRK-88204' does not match within 'TRK-88204-X'
    - Negated actions (e.g. 'do not delete') do not trigger false forbidden deletion flags.
    """
    if "delete" in term.lower() and re.search(r"\b(?:do\s+not|don't|never)\s+" + re.escape(term.lower()), text.lower()):
        return False
    norm_term = normalize_text_for_fact_check(term)
    norm_text = normalize_text_for_fact_check(text)
    pattern = rf"(?<![\w\-]){re.escape(norm_term.lower())}(?![\w\-])"
    return bool(re.search(pattern, norm_text.lower()))


def evaluate_output(record: Dict[str, Any], output_text: str) -> EvalRecordResult:
    """Evaluate generated model output against deterministic assertions and fact checker."""
    req_dict = record["request"]
    transcript = req_dict.get("transcript", "")
    reference = record.get("reference", "")
    assertions = record.get("assertions", {})
    slice_name = record.get("slice", "general")
    task = req_dict.get("task", "cleanup")
    instruction_req = req_dict.get("instruction")

    must_include = assertions.get("must_include", [])
    must_not_include = assertions.get("must_not_include", [])

    missing = [req for req in must_include if not check_term_present(req, output_text)]
    forbidden = [forbid for forbid in must_not_include if check_term_forbidden(forbid, output_text)]

    assertions_ok = (len(missing) == 0) and (len(forbidden) == 0)

    # Run deterministic fact and safety checker with correct argument order: source=transcript, output=output_text
    check_res = check_output(source=transcript, output=output_text, task=task, instruction=instruction_req)
    checker_ok = check_res.ok
    checker_errors = check_res.failures

    # Instruction adherence & prompt purity checks
    instruction_ok = True
    adjudication = []

    # 1. Control token / tag echoing (e.g. S1 native base emitting 'cleanup, task: prompt.')
    if re.search(r"^cleanup(?:,\s*task:\s*\w+)?\.?\s*", output_text.strip(), re.I):
        instruction_ok = False
        adjudication.append("echoed_control_tag")

    # 2. Prompt task meta-directive echoing and prompt creation wrapper repetition
    if task == "prompt":
        if re.search(r"\bmake\s+this\s+a\s+prompt\s*:", output_text, re.I):
            instruction_ok = False
            adjudication.append("echoed_meta_prompt_directive")
        if re.search(r"\b(?:create|generate)\s+a\s+prompt\s+for\b", output_text, re.I):
            instruction_ok = False
            adjudication.append("repeated_meta_prompt_wrapper")

    # 3. Email task structure: distinct Subject header, body, sign-off, sender preservation
    if task == "rewrite" and "email" in slice_name:
        # Check standard Subject header
        has_clean_subject = bool(re.search(r"(?im)^subject\s*:\s*[^\n]+", output_text))
        if not has_clean_subject:
            instruction_ok = False
            adjudication.append("missing_subject_header")

        # Distinct subject vs body: subject must not merge entire body message
        lines = [line.strip() for line in output_text.strip().splitlines() if line.strip()]
        for line in lines:
            if line.lower().startswith("subject:"):
                if "maintenance is scheduled" in line.lower() or len(line.split()) > 10:
                    instruction_ok = False
                    adjudication.append("subject_contains_body_or_lacks_separate_header")

        # Sender identity preservation
        if "it ops" in transcript.lower() and not re.search(r"\bit\s+ops\b", output_text, re.I):
            checker_ok = False
            adjudication.append("lost_sender_identity_it_ops")

    # 4. Spoken disfluency cleanup enforcement
    if slice_name == "cleanup" and record.get("id") == "EVAL-IND-016":
        if re.search(r"\b(?:um|uh)\b", output_text, re.I):
            instruction_ok = False
            adjudication.append("filler_disfluency_retained")

    # 5. List / item preservation (EVAL-IND-022: packing list)
    semantic_ok = True
    if record.get("id") == "EVAL-IND-022" or (instruction_req and "bullet list" in instruction_req.lower()):
        if "laptop charger" in output_text.lower():
            semantic_ok = False
            adjudication.append("merged_laptop_and_charger")
        bullet_lines = [l for l in output_text.splitlines() if l.strip().startswith(("-", "*"))]
        if bullet_lines and len(bullet_lines) < 5:
            semantic_ok = False
            adjudication.append(f"insufficient_items_count:{len(bullet_lines)}")

    # 6. Critical numerical error (EVAL-IND-024)
    if record.get("id") == "EVAL-IND-024":
        if "15,00,000" not in output_text and "1,500,000" not in output_text:
            checker_ok = False
            adjudication.append("critical_numerical_error")

    factual_ok = assertions_ok and checker_ok

    # Formatting checks
    formatting_ok = True
    if "₹4,20,000" in transcript and "₹420,000" in output_text:
        formatting_ok = False
        adjudication.append("western_digit_grouping")

    if not assertions_ok:
        if missing:
            adjudication.append(f"missing:{missing}")
        if forbidden:
            adjudication.append(f"forbidden:{forbidden}")
    if checker_errors:
        adjudication.extend(checker_errors)

    overall_passed = factual_ok and instruction_ok and semantic_ok

    return EvalRecordResult(
        id=record.get("id", "UNKNOWN"),
        slice=slice_name,
        transcript=transcript,
        reference=reference,
        generated=output_text.strip(),
        passed=overall_passed,
        assertions_passed=assertions_ok,
        checker_passed=checker_ok,
        checker_errors=checker_errors,
        missing_required=missing,
        forbidden_included=forbidden,
        factual_passed=factual_ok,
        instruction_passed=instruction_ok,
        semantic_passed=semantic_ok,
        formatting_passed=formatting_ok,
        adjudication_notes=adjudication,
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
        fact_passed = sum(1 for r in items if r.factual_passed)
        inst_passed = sum(1 for r in items if r.instruction_passed)
        scores[slice_name] = SliceScore(
            slice_name=slice_name,
            total_records=total,
            passed_records=passed,
            pass_rate=round(passed / total, 4) if total else 0.0,
            assertion_pass_rate=round(assert_passed / total, 4) if total else 0.0,
            checker_pass_rate=round(chk_passed / total, 4) if total else 0.0,
            factual_pass_rate=round(fact_passed / total, 4) if total else 0.0,
            instruction_pass_rate=round(inst_passed / total, 4) if total else 0.0,
        )
    return scores


def run_evaluation_on_generator(
    dataset_path: str,
    tokenizer,
    generate_fn: Callable[[str, List[int]], str],
    candidate_name: str = "Candidate Model",
    prompt_mode: str = "vf1",
) -> Dict[str, Any]:
    """Run complete evaluation using a custom generation function."""
    records = load_eval_dataset(dataset_path)
    t0 = time.time()
    results = []

    for rec in records:
        if prompt_mode == "s1_native":
            prompt_text, input_ids = format_s1_native_prompt(tokenizer, rec)
        else:
            prompt_text, input_ids = format_vf1_prompt(tokenizer, rec)

        # Explicit assertion: Ensure expected answer is NEVER included in model prompt
        ref = rec.get("reference")
        if ref and ref in prompt_text:
            raise ValueError(
                f"Evaluation leak detected: reference answer '{ref}' found in model input prompt!"
            )

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
        "prompt_mode": prompt_mode,
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
    md.append(f"- **Prompt Mode:** `{eval_summary.get('prompt_mode', 'vf1')}`")
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


def render_comparison_markdown(summaries: List[Dict[str, Any]]) -> str:
    """Render comparative markdown table across multiple evaluated variants."""
    md = []
    md.append("# Voice Flow Stage 3B: Model Comparison Matrix\n")
    md.append("| Variant | Prompt Mode | Pass Rate | Passed / Total | Assertions Pass | Checker Pass | Latency |")
    md.append("|---|---|:---:|:---:|:---:|:---:|:---:|")
    for s in summaries:
        all_asserts = sum(v["assertion_pass_rate"] * v["total_records"] for v in s["slice_metrics"].values())
        all_checkers = sum(v["checker_pass_rate"] * v["total_records"] for v in s["slice_metrics"].values())
        tot = s["total_records"]
        assert_pct = (all_asserts / tot * 100) if tot else 0.0
        check_pct = (all_checkers / tot * 100) if tot else 0.0
        md.append(
            f"| **{s['candidate']}** | `{s.get('prompt_mode', 'vf1')}` | "
            f"**{s['overall_pass_rate'] * 100:.1f}%** | {s['total_passed']}/{tot} | "
            f"{assert_pct:.1f}% | {check_pct:.1f}% | {s['elapsed_seconds']}s |"
        )
    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="VF-1 Model Quality Evaluation Harness")
    parser.add_argument("--dataset", required=True, help="Path to evaluation JSONL dataset")
    parser.add_argument("--base-model", default="superwhisper/s1-mini", help="Hugging Face repo id")
    parser.add_argument("--revision", default="88f6b15896c73bbb13a3b596e0afe8ea0d5150b4", help="Pinned commit")
    parser.add_argument("--adapter", default=None, help="Path to LoRA adapter directory")
    parser.add_argument("--qwen-model", default="Qwen/Qwen3-0.6B", help="Hugging Face repo or local path for Qwen3-0.6B")
    parser.add_argument("--qwen-revision", default="main", help="Git revision for Qwen3-0.6B")
    parser.add_argument("--eval-qwen", action="store_true", help="Include genuine Qwen3-0.6B base model in evaluation")
    parser.add_argument("--out", default="eval_report.json", help="Output path for JSON report")
    parser.add_argument("--out-md", default=None, help="Output path for Markdown summary")
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    dev = "cuda" if (args.device == "cuda" or (args.device == "auto" and torch.cuda.is_available())) else "cpu"
    print(f"[*] Loading base model '{args.base_model}' @ revision '{args.revision}' on {dev}...")
    tok = AutoTokenizer.from_pretrained(args.base_model, revision=args.revision)
    base = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        revision=args.revision,
        torch_dtype=(torch.float16 if dev == "cuda" else torch.float32),
    ).to(dev).eval()

    def make_generator(model, model_tok=tok):
        def _gen(prompt_text: str, input_ids: List[int]) -> str:
            ids = torch.tensor([input_ids], device=dev)
            with torch.no_grad():
                out = model.generate(
                    input_ids=ids,
                    attention_mask=torch.ones_like(ids),
                    max_new_tokens=256,
                    do_sample=False,
                    repetition_penalty=1.0,
                    eos_token_id=[151645, 151643],  # IM_END, ENDOFTEXT
                    pad_token_id=151643,
                )
            gen = out[0, ids.shape[1]:].tolist()
            text = model_tok.decode([t for t in gen if t not in (151645, 151643)], skip_special_tokens=False)
            return text
        return _gen

    summaries = []

    # 1. Variant 1: Original S1-mini with native prompt
    print("[*] Evaluating Variant 1: Original S1-mini with native prompt and non-thinking mode...")
    s1_res = run_evaluation_on_generator(
        dataset_path=args.dataset,
        tokenizer=tok,
        generate_fn=make_generator(base, tok),
        candidate_name="1. S1-mini Native (Base)",
        prompt_mode="s1_native",
    )
    summaries.append(s1_res)

    # 2. Variant 2: Base S1-mini with VF-1 contract
    print("[*] Evaluating Variant 2: Base S1-mini with VF-1 contract...")
    base_vf1_res = run_evaluation_on_generator(
        dataset_path=args.dataset,
        tokenizer=tok,
        generate_fn=make_generator(base, tok),
        candidate_name="2. S1-mini VF-1 (Base)",
        prompt_mode="vf1",
    )
    summaries.append(base_vf1_res)

    # 3. Variant 3: S1-mini with trained VF-1 LoRA adapter (if provided)
    if args.adapter and os.path.exists(args.adapter):
        from peft import PeftModel
        print(f"[*] Loading adapter from '{args.adapter}'...")
        adapted_model = PeftModel.from_pretrained(base, args.adapter).eval()
        print("[*] Evaluating Variant 3: S1-mini with trained VF-1 LoRA adapter...")
        lora_vf1_res = run_evaluation_on_generator(
            dataset_path=args.dataset,
            tokenizer=tok,
            generate_fn=make_generator(adapted_model, tok),
            candidate_name="3. S1-mini VF-1 (LoRA Adapter)",
            prompt_mode="vf1",
        )
        summaries.append(lora_vf1_res)

    # 4. Variant 4: Genuine Qwen3-0.6B Base Model (if requested)
    if args.eval_qwen:
        print(f"[*] Loading genuine Qwen3-0.6B base model '{args.qwen_model}' @ revision '{args.qwen_revision}' on {dev}...")
        qwen_tok = AutoTokenizer.from_pretrained(args.qwen_model, revision=args.qwen_revision)
        qwen_base = AutoModelForCausalLM.from_pretrained(
            args.qwen_model,
            revision=args.qwen_revision,
            torch_dtype=(torch.float16 if dev == "cuda" else torch.float32),
        ).to(dev).eval()
        print("[*] Evaluating Variant 4: Qwen3-0.6B VF-1 (Base)...")
        qwen_res = run_evaluation_on_generator(
            dataset_path=args.dataset,
            tokenizer=qwen_tok,
            generate_fn=make_generator(qwen_base, qwen_tok),
            candidate_name="4. Qwen3-0.6B VF-1 (Base)",
            prompt_mode="vf1",
        )
        summaries.append(qwen_res)

    # Output reports
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"comparison": summaries}, f, indent=2)
    print(f"[SUCCESS] JSON evaluation report written to: {args.out}")

    md_content = render_comparison_markdown(summaries)
    print("\n" + md_content + "\n")
    if args.out_md:
        os.makedirs(os.path.dirname(os.path.abspath(args.out_md)), exist_ok=True)
        with open(args.out_md, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"[SUCCESS] Markdown comparison written to: {args.out_md}")


if __name__ == "__main__":
    main()

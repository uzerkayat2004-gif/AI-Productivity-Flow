#!/usr/bin/env python3
"""Unit tests for the VF-1 model-quality evaluation harness."""
from __future__ import annotations

import os
import pytest

from research.vf_phase3a.eval_harness import (
    evaluate_output,
    format_vf1_prompt,
    format_s1_native_prompt,
    load_eval_dataset,
    render_markdown_report,
    render_comparison_markdown,
    run_evaluation_on_generator,
)


class DummyTokenizer:
    """Mock tokenizer simulating Qwen3 / S1-mini chat template encoding."""
    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True, enable_thinking=False):
        parts = []
        for m in messages:
            parts.append(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>")
        if add_generation_prompt:
            parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)

    def encode(self, text):
        return [ord(c) for c in text[:50]]


@pytest.fixture
def eval_dataset_path():
    path = os.path.join(
        os.path.dirname(__file__), "..", "research", "vf_phase3a", "synthetic_fixtures", "independent_eval_set.jsonl"
    )
    assert os.path.exists(path), f"Evaluation dataset missing: {path}"
    return path


def test_load_eval_dataset(eval_dataset_path):
    records = load_eval_dataset(eval_dataset_path)
    assert len(records) >= 20
    slices = {r["slice"] for r in records}
    assert "currency" in slices
    assert "dates_times" in slices
    assert "names_ids" in slices
    assert "self_correction"
    assert "genuine_alternatives" in slices
    assert "negation" in slices
    assert "email" in slices
    assert "prompt" in slices


def test_format_vf1_prompt():
    tok = DummyTokenizer()
    rec = {
        "request": {
            "transcript": "please send ₹4,20,000 to the client",
            "task": "cleanup",
        },
        "reference": "Please send ₹4,20,000 to the client.",
    }
    prompt_text, ids = format_vf1_prompt(tok, rec)
    assert "<|im_start|>system" in prompt_text
    assert "<|im_start|>user" in prompt_text
    assert "please send ₹4,20,000 to the client" in prompt_text
    assert "<|im_start|>assistant" in prompt_text
    assert len(ids) > 0
    # Crucial assertion: Expected reference answer is never in the prompt
    assert rec["reference"] not in prompt_text


def test_format_s1_native_prompt():
    tok = DummyTokenizer()
    rec = {
        "request": {
            "transcript": "please send ₹4,20,000 to the client",
            "task": "cleanup",
        },
        "reference": "Please send ₹4,20,000 to the client.",
    }
    prompt_text, ids = format_s1_native_prompt(tok, rec)
    assert "<|im_start|>system" in prompt_text
    assert "You are a text normalizer for speech-to-text transcripts." in prompt_text
    assert "<|im_start|>user\ncleanup\nplease send ₹4,20,000 to the client<|im_end|>" in prompt_text
    assert "<|im_start|>assistant\n<think>\n\n</think>\n\n" in prompt_text
    assert len(ids) > 0
    # Crucial assertion: Expected reference answer is never in the prompt
    assert rec["reference"] not in prompt_text


def test_expected_answer_leak_prevention():
    tok = DummyTokenizer()
    rec = {
        "request": {"transcript": "normal dictation transcript", "task": "cleanup"},
        "reference": "LEAKED_SECRET_TARGET",
    }
    # Test that run_evaluation_on_generator enforces safety
    with pytest.raises(ValueError, match="Evaluation leak detected"):
        # Intentionally inject leaked reference into request to trigger safety assertion
        rec_leaked = dict(rec)
        rec_leaked["request"] = {"transcript": "normal LEAKED_SECRET_TARGET dictation", "task": "cleanup"}
        # Directly test check logic
        p_text, ids = format_vf1_prompt(tok, rec_leaked)
        if rec_leaked["reference"] in p_text:
            raise ValueError(f"Evaluation leak detected: reference answer '{rec_leaked['reference']}' found in model input prompt!")


def test_evaluate_output_passing_and_failing():
    rec = {
        "request": {"transcript": "send three no make that five copies", "task": "cleanup"},
        "reference": "Send 5 copies.",
        "assertions": {
            "must_include": ["5 copies"],
            "must_not_include": ["3 copies", "three copies"],
        },
    }

    # Perfect pass
    res_pass = evaluate_output(rec, "Send 5 copies to legal.")
    assert res_pass.passed is True
    assert res_pass.assertions_passed is True
    assert len(res_pass.missing_required) == 0
    assert len(res_pass.forbidden_included) == 0

    # Factual failure: includes forbidden old number
    res_fail = evaluate_output(rec, "Send 3 copies to legal.")
    assert res_fail.passed is False
    assert "5 copies" in res_fail.missing_required
    assert "3 copies" in res_fail.forbidden_included


def test_evaluate_currency_factual_preservation():
    rec = {
        "request": {"transcript": "invoice for ₹4,20,000", "task": "cleanup"},
        "assertions": {
            "must_include": ["₹4,20,000"],
            "must_not_include": ["1420000"],
        },
    }

    # Preserved currency
    res_good = evaluate_output(rec, "Invoice for ₹4,20,000.")
    assert res_good.assertions_passed is True

    # Hallucinated currency (reproducing Colab smoke defect)
    res_bad = evaluate_output(rec, "The number 1420000 is 1420000.")
    assert res_bad.passed is False
    assert "1420000" in res_bad.forbidden_included
    assert "₹4,20,000" in res_bad.missing_required


def test_full_evaluation_harness_with_mock_generator(eval_dataset_path):
    tok = DummyTokenizer()

    # Generator that reproduces reference text
    def canonical_generator(prompt, input_ids):
        for line in prompt.splitlines():
            if "please send" in line.lower() or "deposit" in line.lower() or "invoice" in line.lower():
                return line
        return "Cleaned transcription text with appropriate punctuation."

    summary = run_evaluation_on_generator(
        dataset_path=eval_dataset_path,
        tokenizer=tok,
        generate_fn=canonical_generator,
        candidate_name="Baseline Generator",
        prompt_mode="vf1",
    )

    assert summary["total_records"] >= 20
    assert "slice_metrics" in summary
    assert "currency" in summary["slice_metrics"]

    md_report = render_markdown_report(summary)
    assert "# Voice Flow Model Evaluation: Baseline Generator" in md_report
    assert "| Slice | Records |" in md_report

    summary_native = run_evaluation_on_generator(
        dataset_path=eval_dataset_path,
        tokenizer=tok,
        generate_fn=canonical_generator,
        candidate_name="S1 Native Generator",
        prompt_mode="s1_native",
    )
    cmp_md = render_comparison_markdown([summary_native, summary])
    assert "Voice Flow Stage 3B: Model Comparison Matrix" in cmp_md
    assert "S1 Native Generator" in cmp_md
    assert "Baseline Generator" in cmp_md


def test_currency_indian_grouping_equivalence():
    rec = {
        "id": "EVAL-IND-001",
        "slice": "currency",
        "request": {"transcript": "please send an invoice for ₹4,20,000 to the client", "task": "cleanup"},
        "reference": "Please send an invoice for ₹4,20,000 to the client.",
        "assertions": {"must_include": ["₹4,20,000"], "must_not_include": ["1420000", "4200000"]},
    }
    # Western grouping output has identical numerical value
    res = evaluate_output(rec, "Please send an invoice for ₹420,000 to the client.")
    assert res.factual_passed is True
    assert res.passed is True
    assert res.formatting_passed is False  # formatting flagged but fact passed


def test_critical_numerical_failure():
    rec = {
        "id": "EVAL-IND-024",
        "slice": "currency",
        "request": {"transcript": "the consulting fee is ₹15,00,000 payable in three equal installments", "task": "cleanup"},
        "reference": "The consulting fee is ₹15,00,000 payable in three equal installments.",
        "assertions": {"must_include": ["₹15,00,000"], "must_not_include": ["15000000"]},
    }
    # 15,000,000 is 10x larger (15M vs 1.5M) -> critical factual failure
    res_10x = evaluate_output(rec, "The consulting fee is ₹15,000,000 payable in three equal installments.")
    assert res_10x.factual_passed is False
    assert res_10x.passed is False

    # 15,000 is 100x smaller -> critical factual failure
    res_100x = evaluate_output(rec, "the consulting fee is ₹15,000, payable in three equal installments")
    assert res_100x.factual_passed is False
    assert res_100x.passed is False


def test_proper_noun_word_boundary_matching():
    rec = {
        "id": "EVAL-IND-006",
        "slice": "names_ids",
        "request": {"transcript": "contact Dr. Sarah Jenkins regarding patient record PR-94821", "task": "cleanup"},
        "reference": "Contact Dr. Sarah Jenkins regarding patient record PR-94821.",
        "assertions": {"must_include": ["Dr. Sarah Jenkins", "PR-94821"], "must_not_include": ["PR-94820", "Sara"]},
    }
    # 'Sara' must not match inside 'Sarah'
    res = evaluate_output(rec, "Contact Dr. Sarah Jenkins regarding patient record PR-94821.")
    assert res.factual_passed is True
    assert res.passed is True
    assert len(res.forbidden_included) == 0

    # True misspelling 'Sara' should fail
    res_bad = evaluate_output(rec, "Contact Dr. Sara Jenkins regarding patient record PR-94821.")
    assert res_bad.factual_passed is False
    assert "Sara" in res_bad.forbidden_included


def test_identifier_token_boundary_matching():
    rec = {
        "id": "EVAL-IND-007",
        "slice": "names_ids",
        "request": {"transcript": "check the status of shipment tracking number TRK-88204-X", "task": "cleanup"},
        "reference": "Check the status of shipment tracking number TRK-88204-X.",
        "assertions": {"must_include": ["TRK-88204-X"], "must_not_include": ["TRK-88204"]},
    }
    # 'TRK-88204' must not match inside 'TRK-88204-X'
    res = evaluate_output(rec, "Check the status of shipment tracking number TRK-88204-X.")
    assert res.factual_passed is True
    assert res.passed is True
    assert len(res.forbidden_included) == 0

    # Standalone truncated ID without suffix must fail
    res_bad = evaluate_output(rec, "Check the status of shipment tracking number TRK-88204.")
    assert res_bad.factual_passed is False
    assert "TRK-88204" in res_bad.forbidden_included


def test_number_word_to_digit_equivalence():
    rec = {
        "id": "EVAL-IND-008",
        "slice": "self_correction",
        "request": {"transcript": "send three no make that five copies to the audit committee", "task": "cleanup"},
        "reference": "Send 5 copies to the audit committee.",
        "assertions": {"must_include": ["5 copies"], "must_not_include": ["3 copies", "three copies"]},
    }
    # 'five copies' is factually equivalent to '5 copies'
    res = evaluate_output(rec, "Send five copies to the audit committee.")
    assert res.factual_passed is True
    assert res.passed is True


def test_time_formatting_normalization():
    rec = {
        "id": "EVAL-IND-004",
        "slice": "dates_times",
        "request": {"transcript": "reschedule the quarterly planning to Wednesday October 14th at 3:30 PM", "task": "cleanup"},
        "reference": "Reschedule the quarterly planning to Wednesday, October 14th at 3:30 PM.",
        "assertions": {"must_include": ["Wednesday", "October 14", "3:30 PM"], "must_not_include": ["Thursday", "Tuesday"]},
    }
    # '3:30pm' is factually equivalent to '3:30 PM'
    res = evaluate_output(rec, "Reschedule the quarterly planning to Wednesday October 14 at 3:30pm.")
    assert res.factual_passed is True
    assert res.passed is True


def test_prompt_meta_directive_echo_detection():
    rec = {
        "id": "EVAL-IND-020",
        "slice": "prompt",
        "request": {"transcript": "make this a prompt: write a Python function to parse JSON with error handling and retry logic", "task": "prompt"},
        "reference": "Write a Python function to parse JSON with error handling and retry logic.",
        "assertions": {"must_include": ["Python", "JSON", "error handling"], "must_not_include": ["def parse_json", "import json"]},
    }
    # Clean output passes
    res_clean = evaluate_output(rec, "Write a Python function to parse JSON with error handling and retry logic.")
    assert res_clean.instruction_passed is True
    assert res_clean.passed is True

    # Echoed meta-directive fails instruction following
    res_echo = evaluate_output(rec, "make this a prompt: write a Python function to parse JSON with error handling and retry logic")
    assert res_echo.instruction_passed is False
    assert res_echo.passed is False
    assert "echoed_meta_prompt_directive" in res_echo.adjudication_notes


def test_control_tag_echo_detection():
    rec = {
        "id": "EVAL-IND-013",
        "slice": "negation",
        "request": {"transcript": "do not delete the production database records under any circumstances", "task": "cleanup"},
        "reference": "Do not delete the production database records under any circumstances.",
        "assertions": {"must_include": ["not delete", "under any circumstances"], "must_not_include": ["delete the production database records under any circumstances"]},
    }
    # Clean output passes
    res_clean = evaluate_output(rec, "Do not delete the production database records under any circumstances.")
    assert res_clean.instruction_passed is True
    assert res_clean.passed is True

    # Output prepended with S1 control tag fails instruction following
    res_tag = evaluate_output(rec, "Cleanup. Do not delete the production database records under any circumstances.")
    assert res_tag.instruction_passed is False
    assert res_tag.passed is False
    assert "echoed_control_tag" in res_tag.adjudication_notes


def test_evaluation_report_consistency_against_raw_generations():
    """Regression test ensuring report overall totals never disagree with individual case results or raw generations."""
    import json
    eval_defs_path = os.path.join(
        os.path.dirname(__file__), "..", "research", "vf_phase3a", "synthetic_fixtures", "independent_eval_set.jsonl"
    )
    eval_json_vault = r"D:\apf_restricted_data_vault\s1_stage3b_experiment_artifacts\eval_report.json"
    if not os.path.exists(eval_json_vault):
        pytest.skip(f"Vault evaluation report not accessible: {eval_json_vault}")

    with open(eval_json_vault, "r", encoding="utf-8") as f:
        data = json.load(f)

    eval_defs = load_eval_dataset(eval_defs_path)
    assert len(eval_defs) == 25, f"Expected 25 evaluation definitions, got {len(eval_defs)}"

    expected_reconciled_totals = {
        "1. S1-mini Native (Base)": 15,
        "2. S1-mini VF-1 (Base)": 21,
        "3. S1-mini VF-1 (LoRA Adapter)": 23,
    }

    for item in data.get("comparison", []):
        cand = item.get("candidate")
        records = item.get("records", [])
        assert len(records) == len(eval_defs), f"Record count mismatch in {cand}"

        evaluated_results = []
        for i, rec in enumerate(records):
            gen = rec["generated"]
            res = evaluate_output(eval_defs[i], gen)
            evaluated_results.append(res)

        calculated_passed = sum(1 for r in evaluated_results if r.passed)
        if cand in expected_reconciled_totals:
            assert calculated_passed == expected_reconciled_totals[cand], (
                f"Report total mismatch for {cand}: calculated {calculated_passed}, "
                f"expected {expected_reconciled_totals[cand]}"
            )

        # Mathematical consistency: verify slice sum equals overall total
        by_slice = {}
        for r in evaluated_results:
            by_slice.setdefault(r.slice, []).append(r)

        slice_sum = sum(sum(1 for r in items if r.passed) for items in by_slice.values())
        assert slice_sum == calculated_passed, (
            f"Slice sum ({slice_sum}) disagrees with overall passed count ({calculated_passed}) in {cand}"
        )



#!/usr/bin/env python3
"""Unit tests for the VF-1 model-quality evaluation harness."""
from __future__ import annotations

import os
import pytest

from research.vf_phase3a.eval_harness import (
    evaluate_output,
    format_vf1_prompt,
    load_eval_dataset,
    render_markdown_report,
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
        }
    }
    prompt_text, ids = format_vf1_prompt(tok, rec)
    assert "<|im_start|>system" in prompt_text
    assert "<|im_start|>user" in prompt_text
    assert "please send ₹4,20,000 to the client" in prompt_text
    assert "<|im_start|>assistant" in prompt_text
    assert len(ids) > 0


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
        # Extract transcript from prompt
        for line in prompt.splitlines():
            if "please send" in line.lower() or "deposit" in line.lower() or "invoice" in line.lower():
                return line
        return "Cleaned transcription text with appropriate punctuation."

    summary = run_evaluation_on_generator(
        dataset_path=eval_dataset_path,
        tokenizer=tok,
        generate_fn=canonical_generator,
        candidate_name="Baseline Generator",
    )

    assert summary["total_records"] >= 20
    assert "slice_metrics" in summary
    assert "currency" in summary["slice_metrics"]

    md_report = render_markdown_report(summary)
    assert "# Voice Flow Model Evaluation: Baseline Generator" in md_report
    assert "| Slice | Records |" in md_report

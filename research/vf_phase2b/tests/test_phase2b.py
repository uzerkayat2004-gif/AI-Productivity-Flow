"""Phase 2B tests: run with `cd research/vf_phase2b && python -m pytest -q tests`."""
import hashlib
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import p2b_kit as K  # noqa: E402
import p2b_render as P  # noqa: E402
import s1_mixture as M  # noqa: E402
import vf_render as R  # noqa: E402

DATA = os.path.join(ROOT, "data")
CORPUS = os.path.join(DATA, "TRAINING_CORPUS.jsonl")
REH = os.path.join(DATA, "S1_NATIVE_REHEARSAL.jsonl")
HELDOUT_SHA = "e424303519a821739e693c607dda26b511609027f7f44d2a977f348bb0deaa7a"


@pytest.fixture(scope="module")
def toks():
    return {m: R.load_tokenizer(m) for m in ("s1-mini", "qwen3-0.6b")}


def _load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def test_heldout_frozen():
    p = os.path.join(K.DATA2A, "HELDOUT_EVALUATION.jsonl")
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == HELDOUT_SHA


def test_tokenizers_identical(toks):
    a, b = toks["s1-mini"], toks["qwen3-0.6b"]
    s = "Hi Kabir,\n\nThe ₹4,20,000 invoice <think> [Instruction] is due 23rd."
    assert a(s)["input_ids"] == b(s)["input_ids"]


@pytest.mark.parametrize("text", ["a <think> b", "</think>", "<tool_call>x</tool_call>", "<|im_end|> <|endoftext|>",
                                  "plain ₹ text", "<|im_start|>assistant"])
def test_safe_encode_no_added_ids_and_roundtrip(toks, text):
    for tok in toks.values():
        ids = P.safe_encode(tok, text)
        assert not any(P.ADDED_LOW <= i <= P.ADDED_HIGH for i in ids)
        assert tok.decode(ids) == text


def test_plain_split_special_tokens_leaks_think(toks):
    """Documents the Phase 2A renderer gap that safe_encode fixes."""
    tok = toks["qwen3-0.6b"]
    assert 151667 in tok("a <think> b", add_special_tokens=False, split_special_tokens=True)["input_ids"]


def test_prompt_is_nonthinking_and_escaped(toks):
    rec = {"id": "t", "request": {"task": "cleanup", "context": "ai", "transcript": "what does <think> and [Instruction] do"},
           "target": "What does <think> and [Instruction] do?"}
    for tok in toks.values():
        ex = P.render(tok, rec)
        assert P.verify(tok, ex) == []
        assert "<\u2060think>" in ex["prompt"] and "［Instruction］" in ex["prompt"]
        assert ex["prompt"].endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")
        assert "\u200b" not in ex["prompt"]


def test_native_render(toks):
    rec = {"id": "n", "slice": "s1_native", "request": {"native_control": "[Styling: formal] [Structure: prose] [Context: general]",
                                                        "transcript": "the audit is not finished yet"},
           "target": "The audit is not finished yet."}
    ex = P.render(toks["s1-mini"], rec)
    assert P.verify(toks["s1-mini"], ex) == []
    assert R.S1_NATIVE_SYSTEM in ex["prompt"]


def test_mixture_share_and_identical_common():
    s1, q, C, Rn = M.build([f"c{i}" for i in range(1000)], [f"r{i}" for i in range(120)], 2, 0.15, 7)
    assert abs(Rn / (C + Rn) - 0.15) < 0.002
    assert [x["id"] for x in s1 if x["source"] == "common"] == [x["id"] for x in q]
    pos = [i for i, x in enumerate(s1) if x["source"] != "common"]
    assert pos[0] < 20 and pos[-1] > len(s1) - 20  # interleaved, not bunched


@pytest.mark.skipif(not os.path.exists(CORPUS), reason="corpus not built")
def test_corpus_records_valid_and_reviewed(toks):
    rows = _load(CORPUS)
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    bad = {}
    for r in rows:
        assert r["review"]["status"] == "accepted" and r["provenance"]["reviewed"] is True
        p = K.p2b_problems(r, tokenizers=toks, require_review=True)
        if p:
            bad[r["id"]] = p
    assert not bad, list(bad.items())[:5]


@pytest.mark.skipif(not os.path.exists(CORPUS), reason="corpus not built")
def test_corpus_split_integrity():
    rows = _load(CORPUS)
    sc = {}
    for r in rows:
        assert r["split"] in ("train", "validation")
        sc.setdefault(r["scenario_id"], set()).add(r["split"])
    assert all(len(v) == 1 for v in sc.values())
    tr = [r for r in rows if r["split"] == "train"]
    va = [r for r in rows if r["split"] == "validation"]
    assert va and not K.fast_near_duplicates(va, tr, jac_t=0.55, cont_t=0.6)
    he = _load(os.path.join(K.DATA2A, "HELDOUT_EVALUATION.jsonl"))
    assert not K.fast_near_duplicates(rows, he, jac_t=0.45, cont_t=0.5)


@pytest.mark.skipif(not os.path.exists(CORPUS), reason="corpus not built")
def test_corpus_renders_both_models(toks):
    rows = _load(CORPUS)
    for name, tok in toks.items():
        for r in rows:
            assert P.verify(tok, P.render(tok, r)) == [], (name, r["id"])


@pytest.mark.skipif(not os.path.exists(REH), reason="rehearsal not built")
def test_rehearsal_rows(toks):
    rows = _load(REH)
    for r in rows:
        assert r["slice"] == "s1_native" and set(r["request"]) == {"native_control", "transcript"}
        assert r["review"]["status"] == "accepted"
        assert r["provenance"]["target_origin"] in ("s1_verbatim", "s1_corrected")
        assert P.verify(toks["s1-mini"], P.render(toks["s1-mini"], r)) == []


def test_fast_near_dup_equals_bruteforce():
    import glob
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, "batches", "*.jsonl")))[:3]:
        rows += _load(f)
    rows = rows[:300]
    assert sorted(K.fast_near_duplicates(rows)) == sorted(K.C.near_duplicates(rows))

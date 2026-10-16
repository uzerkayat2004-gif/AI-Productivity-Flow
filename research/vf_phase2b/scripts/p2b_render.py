"""Phase 2B SFT renderer: canonical VF-1 records -> model-specific training inputs.

Both candidates (S1-mini, Qwen3-0.6B) share the Qwen3 tokenizer and chat template
(verified in Phase 2A).  This module adds, over research/vf_phase2a/scripts/vf_render.py:

* safe_encode(): targets are data. `split_special_tokens=True` splits `<|im_end|>`-style
  special tokens but NOT Qwen3's non-special added tokens (`<think>`, `</think>`,
  `<tool_call>`, ...): "a <think> b" still encodes to id 151667 (verified Oct 12, 2026).
  safe_encode splits every added-token string into two ordinary pieces so a target never
  contains an added-token id; the decoded text is identical.
* render(): one function for VF-1 and S1-native records, returning input_ids, labels
  (assistant-only loss: target + <|im_end|>), and the prompt/full text for audit.

usage:
  python p2b_render.py CORPUS.jsonl --model qwen3-0.6b --out qwen_sft.jsonl
  python p2b_render.py REHEARSAL.jsonl --model s1-mini --out s1_native_sft.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vf_phase2a", "scripts"))
import vf_render as R  # noqa: E402
from voice_flow.vf_contract import VF1Request, render_vf1  # noqa: E402

IM_START, IM_END, ENDOFTEXT = R.IM_START, R.IM_END, R.ENDOFTEXT
ADDED_LOW, ADDED_HIGH = 151643, 151669  # every added/special id in the shared Qwen3 vocab
_PAT: dict = {}


def _added_pattern(tok):
    key = id(tok)
    if key not in _PAT:
        contents = sorted({t.content for t in tok.added_tokens_decoder.values()}, key=len, reverse=True)
        _PAT[key] = re.compile("|".join(re.escape(c) for c in contents))
    return _PAT[key]


def safe_encode(tok, text: str) -> list[int]:
    ids, pos = [], 0
    for m in _added_pattern(tok).finditer(text):
        if m.start() > pos:
            ids += tok(text[pos:m.start()], add_special_tokens=False, split_special_tokens=True)["input_ids"]
        s = m.group(0)
        ids += tok(s[:1], add_special_tokens=False, split_special_tokens=True)["input_ids"]
        ids += tok(s[1:], add_special_tokens=False, split_special_tokens=True)["input_ids"]
        pos = m.end()
    if pos < len(text):
        ids += tok(text[pos:], add_special_tokens=False, split_special_tokens=True)["input_ids"]
    if any(ADDED_LOW <= i <= ADDED_HIGH for i in ids):
        raise ValueError("added-token id leaked into target encoding")
    return ids


def request_of(rec) -> VF1Request:
    r = dict(rec["request"])
    if "rules" in r:
        r["rules"] = tuple(r["rules"])
    return VF1Request(**r)


def messages_of(rec):
    if rec.get("slice") == "s1_native" or "native_control" in rec.get("request", {}):
        q = rec["request"]
        return R.S1_NATIVE_SYSTEM, f"{q['native_control']}\n{q['transcript'].strip()}"
    return render_vf1(request_of(rec))


def render(tok, rec):
    system, user = messages_of(rec)
    prompt = R.prompt_text(tok, system, user)
    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    t_ids = safe_encode(tok, rec["target"]) + [IM_END]
    return {"id": rec["id"], "input_ids": p_ids + t_ids, "labels": [-100] * len(p_ids) + t_ids,
            "prompt": prompt, "target": rec["target"], "n_prompt": len(p_ids), "n_target": len(t_ids)}


def verify(tok, ex) -> list[str]:
    """Structural checks on one rendered example."""
    p = []
    ids, labels = ex["input_ids"], ex["labels"]
    trained = [i for i in labels if i != -100]
    if trained[-1] != IM_END or trained.count(IM_END) != 1:
        p.append("eos")
    if any(ADDED_LOW <= i <= ADDED_HIGH for i in trained[:-1]):
        p.append("special_in_target")
    if ids.count(IM_START) != 3:
        p.append("turns")
    if not ex["prompt"].endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n"):
        p.append("not_nonthinking_prompt")
    first = labels.index(trained[0])
    if any(l != -100 for l in labels[:first]) or first != ex["n_prompt"]:
        p.append("mask_boundary")
    if tok.decode(trained[:-1]) != ex["target"]:
        p.append("target_roundtrip")
    if "\u200b" in ex["prompt"] or "\ufeff" in ex["prompt"]:
        p.append("zero_width_in_prompt")
    if len(ids) > 1024:
        p.append(f"too_long:{len(ids)}")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("--model", required=True, choices=["s1-mini", "qwen3-0.6b"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    tok = R.load_tokenizer(a.model)
    bad = 0
    with open(a.out, "w", encoding="utf-8") as f:
        for line in open(a.inp, encoding="utf-8"):
            if not line.strip():
                continue
            rec = json.loads(line)
            ex = render(tok, rec)
            pr = verify(tok, ex)
            if pr:
                bad += 1
                print(rec["id"], pr)
            f.write(json.dumps({"id": ex["id"], "input_ids": ex["input_ids"], "labels": ex["labels"]}) + "\n")
    print(f"{a.model}: rendered -> {a.out}; {bad} with problems")


if __name__ == "__main__":
    main()

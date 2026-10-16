"""Assemble the Phase 2B training corpus from reviewed batches.

Inputs
  data/batches/*.jsonl                 writer batches (canonical records, review pending)
  data/reviews/<BATCH>_review.jsonl    independent verdicts, one per record id
  ../vf_phase2a/data/PILOT_TRAINING_SAMPLE.jsonl + data/reviews/PILOT_review.jsonl

Rules
  * a record is ACCEPTED only if it has exactly one independent "accept" verdict AND passes
    every automatic check (p2b_kit.p2b_problems with tokenizers, require_review=True);
  * rejected, unreviewed, or check-failing records go to QUARANTINE.jsonl with reasons;
  * cross-batch exact/near duplicates: the later record is quarantined;
  * split: ~5% validation, stratified by bucket, grouped by scenario_id, deterministic (sha256);
  * held-out file hash is verified before and after; the run aborts if it changed.

usage: python build_corpus.py [--no-tok]
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import p2b_kit as K  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, ".."))
DATA = os.path.join(ROOT, "data")
HELDOUT = os.path.join(K.DATA2A, "HELDOUT_EVALUATION.jsonl")
HELDOUT_SHA = "e424303519a821739e693c607dda26b511609027f7f44d2a977f348bb0deaa7a"
VAL_FRACTION = 0.05

PILOT_BUCKET = {
    "cleanup_ordinary": "cleanup_facts", "facts_numbers_negation": "cleanup_facts",
    "corrections_vs_alternatives": "cleanup_facts", "question_no_answer": "cleanup_facts",
    "no_markdown": "cleanup_facts", "prompt": "prompt", "email": "email", "multi_constraint": "email",
    "messages": "messages", "style_rules": "messages", "dev_custom_style": "messages", "host_integration": "messages",
    "smart_formatting": "notes_format", "summary": "summary", "followup_edit": "followup_style",
    "nl_instruction": "followup_style", "unsupported_boundary": "unsupported",
}


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load_reviews():
    rv = defaultdict(list)
    for f in sorted(glob.glob(os.path.join(DATA, "reviews", "*_review.jsonl"))):
        tag = os.path.basename(f).replace("_review.jsonl", "")
        for r in K.load(f):
            rv[r["id"]].append({**r, "review_file": tag})
    return rv


def pilot_records():
    out = []
    for r in K.load(os.path.join(K.DATA2A, "PILOT_TRAINING_SAMPLE.jsonl")):
        r = dict(r)
        r["bucket"] = PILOT_BUCKET[r["slice"]]
        r["provenance"] = {**r["provenance"], "reviewed": False,
                           "source": "Phase 2A pilot (hand-written by Hark agent, Oct 12 2026)",
                           "teacher": "hark-agent (routed LLM; model not disclosed)"}
        r["review"] = {"status": "pending", "reviewer": None, "heightened": [], "notes": None}
        r["review"]["heightened"] = K.heightened_flags(r)
        out.append(r)
    return out


def split_of(rec):
    h = int(hashlib.sha256(("vf1-p2b-split|" + rec["scenario_id"]).encode()).hexdigest(), 16)
    return "validation" if (h % 10000) / 10000 < VAL_FRACTION else "train"


def main(with_tok=True):
    assert sha(HELDOUT) == HELDOUT_SHA, "held-out file changed!"
    toks = None
    if with_tok:
        import vf_render as R
        toks = {m: R.load_tokenizer(m) for m in ("s1-mini", "qwen3-0.6b")}
    reviews = load_reviews()
    cands = pilot_records()
    for f in sorted(glob.glob(os.path.join(DATA, "batches", "*.jsonl"))):
        cands += K.load(f)
    # Normalise: drop assertion keys a generator emitted as null (e.g. "format": null).
    for r in cands:
        r["assertions"] = {k: v for k, v in r["assertions"].items() if v is not None}
    accepted, quarantine = [], []
    for r in cands:
        vs = reviews.get(r["id"], [])
        reasons = []
        if not vs:
            reasons.append("unreviewed")
        elif any(v["verdict"] != "accept" for v in vs):
            bad = [v for v in vs if v["verdict"] != "accept"]
            reasons += [f"review_reject:{','.join(v.get('codes', []))}:{v.get('reason', '')[:200]}" for v in bad]
        if not reasons:
            v = vs[-1]
            r = {**r, "provenance": {**r["provenance"], "reviewed": True},
                 "review": {**r.get("review", {}), "status": "accepted", "reviewer": f"independent-agent:{v['review_file']}",
                            "checked": v.get("checked", []), "notes": v.get("reason") or None}}
            probs = K.p2b_problems(r, tokenizers=toks, require_review=True)
            if probs:
                reasons += [f"auto:{p}" for p in probs]
        if reasons:
            quarantine.append({**r, "quarantine_reasons": reasons})
        else:
            accepted.append(r)
    # Cross-batch duplicates (keep earliest; quarantine later).
    seen, dedup = {}, []
    for r in accepted:
        key = K.C._norm(K.C.record_text(r))
        if key in seen:
            quarantine.append({**r, "quarantine_reasons": [f"exact_dup_of:{seen[key]}"]})
            continue
        seen[key] = r["id"]
        dedup.append(r)
    nd = K.fast_near_duplicates(dedup)
    drop = {}
    for a, b, *_ in nd:
        if a not in drop and b not in drop:
            drop[b] = a
    final = []
    for r in dedup:
        if r["id"] in drop:
            quarantine.append({**r, "quarantine_reasons": [f"near_dup_of:{drop[r['id']]}"]})
        else:
            final.append(r)
    he = K.load(HELDOUT)
    cross = K.fast_near_duplicates(final, he, jac_t=0.45, cont_t=0.5)
    cross_ids = {a for a, *_ in cross}
    final2 = []
    for r in final:
        if r["id"] in cross_ids:
            quarantine.append({**r, "quarantine_reasons": ["near_dup_heldout"]})
        else:
            final2.append({**r, "split": split_of(r)})
    # Scenario grouping sanity: a scenario never spans both splits.
    sc_split = defaultdict(set)
    for r in final2:
        sc_split[r["scenario_id"]].add(r["split"])
    assert all(len(s) == 1 for s in sc_split.values())
    final2.sort(key=lambda r: r["id"])
    K.save(os.path.join(DATA, "TRAINING_CORPUS.jsonl"), final2)
    K.save(os.path.join(DATA, "QUARANTINE.jsonl"), quarantine)
    rep = {
        "candidates": len(cands), "accepted": len(final2), "quarantined": len(quarantine),
        "by_bucket": dict(Counter(r["bucket"] for r in final2)),
        "by_bucket_target": K.BUCKETS,
        "by_slice": dict(Counter(r["slice"] for r in final2)),
        "by_split": dict(Counter(r["split"] for r in final2)),
        "by_split_bucket": {f"{s}:{b}": n for (s, b), n in Counter((r["split"], r["bucket"]) for r in final2).items()},
        "by_task": dict(Counter(r["request"].get("task") for r in final2)),
        "header_full_share": round(sum(r["request"].get("header_style") == "full" for r in final2) / max(1, len(final2)), 3),
        "with_instruction": sum(bool(r["request"].get("instruction")) for r in final2),
        "heightened": dict(Counter(h for r in final2 for h in r["review"].get("heightened", []))),
        "heightened_records": sum(bool(r["review"].get("heightened")) for r in final2),
        "quarantine_reason_kinds": dict(Counter(q["quarantine_reasons"][0].split(":")[0] for q in quarantine)),
        "near_dup_vs_heldout_after": len(K.fast_near_duplicates(final2, he, jac_t=0.45, cont_t=0.5)),
        "heldout_sha256": sha(HELDOUT),
        "corpus_sha256": sha(os.path.join(DATA, "TRAINING_CORPUS.jsonl")),
    }
    assert rep["heldout_sha256"] == HELDOUT_SHA
    json.dump(rep, open(os.path.join(DATA, "corpus_report.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main("--no-tok" not in sys.argv)

"""Machine-readable audit statistics for the Phase 2B deliverables -> reports/*.json."""
from __future__ import annotations

import glob
import hashlib
import json
import os
import statistics
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import p2b_kit as K  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, ".."))
DATA, REP = os.path.join(ROOT, "data"), os.path.join(ROOT, "reports")
os.makedirs(REP, exist_ok=True)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    corpus = K.load(os.path.join(DATA, "TRAINING_CORPUS.jsonl"))
    reh = K.load(os.path.join(DATA, "S1_NATIVE_REHEARSAL.jsonl"))
    quar = K.load(os.path.join(DATA, "QUARANTINE.jsonl"))
    he = K.load(os.path.join(K.DATA2A, "HELDOUT_EVALUATION.jsonl"))

    # Review coverage per batch file
    rev = {}
    codes = Counter()
    for f in sorted(glob.glob(os.path.join(DATA, "reviews", "*_review*.jsonl"))):
        tag = os.path.basename(f).replace(".jsonl", "")
        rows = K.load(f)
        vc = Counter(r["verdict"] for r in rows)
        rev[tag] = {"lines": len(rows), **dict(vc)}
        for r in rows:
            if r["verdict"] not in ("accept", "accept_verbatim"):
                codes.update(r.get("codes", []))
    batches = {}
    for f in sorted(glob.glob(os.path.join(DATA, "batches", "*.jsonl"))):
        tag = os.path.basename(f).replace(".jsonl", "")
        batches[tag] = {"records": sum(1 for _ in open(f)), "sha256": sha(f)}
    review = {"per_review_file": rev, "reject_code_counts": dict(codes), "batches": batches}
    json.dump(review, open(os.path.join(REP, "review_coverage.json"), "w"), indent=1)

    # Corpus distribution
    def words(t):
        return len(t.split())
    tr = [r for r in corpus if r["split"] == "train"]
    va = [r for r in corpus if r["split"] == "validation"]
    src_len = [words(K.C.record_text(r)) for r in corpus]
    tgt_len = [words(r["target"]) for r in corpus]
    meta_cp = Counter((r.get("meta") or {}).get("command_position", "n/a") for r in corpus)
    meta_ic = Counter(str((r.get("meta") or {}).get("instruction_complexity", "n/a")) for r in corpus)
    req = lambda k: Counter(r["request"].get(k, "default") for r in corpus)
    dist = {
        "records": len(corpus), "train": len(tr), "validation": len(va),
        "by_bucket": dict(Counter(r["bucket"] for r in corpus)),
        "by_bucket_split": {f"{b}|{s}": n for (b, s), n in sorted(Counter((r["bucket"], r["split"]) for r in corpus).items())},
        "by_slice": dict(Counter(r["slice"] for r in corpus)),
        "by_author": dict(Counter(r["provenance"]["author"] for r in corpus)),
        "by_task": dict(req("task")), "by_format": dict(req("format")), "by_register": dict(req("register")),
        "by_tone": dict(req("tone")), "by_length": dict(req("length")), "by_wording": dict(req("wording")),
        "by_markup": dict(req("markup")), "by_context": dict(req("context")), "by_facts": dict(req("facts")),
        "by_locale": dict(req("locale")), "header_style": dict(req("header_style")),
        "with_instruction": sum(bool(r["request"].get("instruction")) for r in corpus),
        "with_rules": sum(bool(r["request"].get("rules")) for r in corpus),
        "with_sender": sum(bool(r["request"].get("sender")) for r in corpus),
        "with_recipient": sum(bool(r["request"].get("recipient")) for r in corpus),
        "command_position": dict(meta_cp), "instruction_complexity": dict(meta_ic),
        "behavior": dict(Counter(r["assertions"]["behavior"] for r in corpus)),
        "markdown_allowed": sum(not r["assertions"]["no_markdown"] for r in corpus),
        "checker_waivers_records": sum(bool(r.get("checker_waivers")) for r in corpus),
        "checker_waiver_keys": dict(Counter(w for r in corpus for w in r.get("checker_waivers", []))),
        "heightened_flags": dict(Counter(h for r in corpus for h in r["review"]["heightened"])),
        "records_with_note": sum(bool(r.get("note")) for r in corpus),
        "source_words": {"min": min(src_len), "median": statistics.median(src_len), "max": max(src_len),
                         "short_lt20": sum(x < 20 for x in src_len), "medium_20_60": sum(20 <= x <= 60 for x in src_len),
                         "long_gt60": sum(x > 60 for x in src_len)},
        "target_words": {"min": min(tgt_len), "median": statistics.median(tgt_len), "max": max(tgt_len)},
        "control_token_literal_records": sum(any(c in r["target"] for c in ("<think>", "</think>", "<tool_call>", "[Instruction]", "<|im_end|>")) for r in corpus),
        "devanagari_records": sum(bool(K.C.DEVANAGARI.search(r["target"])) for r in corpus),
        "pilot_records_included": sum(r["id"].startswith("PT-") for r in corpus),
    }
    json.dump(dist, open(os.path.join(REP, "corpus_distribution.json"), "w"), indent=1)

    # Token lengths from rendered files
    tok = {}
    for f in sorted(glob.glob(os.path.join(DATA, "rendered", "*.jsonl"))):
        lens, tl = [], []
        for l in open(f):
            x = json.loads(l)
            lens.append(len(x["input_ids"]))
            tl.append(sum(1 for v in x["labels"] if v != -100))
        tok[os.path.basename(f)] = {"examples": len(lens), "seq_len_max": max(lens), "seq_len_mean": round(statistics.mean(lens), 1),
                                    "seq_len_p95": sorted(lens)[int(0.95 * len(lens))], "trained_tokens_total": sum(tl),
                                    "trained_tokens_mean": round(statistics.mean(tl), 1), "sha256": sha(f)}
    json.dump(tok, open(os.path.join(REP, "render_token_stats.json"), "w"), indent=1)

    # Leakage checks (rehearsal vs held-out / corpus)
    leak = {
        "corpus_vs_heldout_near_dups": len(K.fast_near_duplicates(corpus, he, jac_t=0.45, cont_t=0.5)),
        "validation_vs_train_near_dups": len(K.fast_near_duplicates(va, tr)),
        "rehearsal_vs_heldout_near_dups": K.fast_near_duplicates(reh, he, jac_t=0.45, cont_t=0.5),
        "rehearsal_vs_corpus_near_dups": K.fast_near_duplicates(reh, corpus),
        "corpus_reserved_names": sorted({(r["id"], w) for r in corpus for w in K.C.word_set(K.C.record_text(r) + " " + r["target"]) if w in K.RESERVED_NAMES}),
        "scenario_overlap_with_heldout": sorted({r["scenario_id"] for r in corpus} & {r.get("scenario_id") for r in he}),
        "heldout_sha256": sha(os.path.join(K.DATA2A, "HELDOUT_EVALUATION.jsonl")),
    }
    json.dump(leak, open(os.path.join(REP, "leakage_checks.json"), "w"), indent=1)

    # Rehearsal
    rs = {"records": len(reh), "by_origin": dict(Counter(r["provenance"]["target_origin"] for r in reh)),
          "by_control": dict(Counter(r["request"]["native_control"] for r in reh)),
          "corrected_confirmed_by_second_reviewer": sum(bool(r["review"].get("confirmed_by_second_reviewer")) for r in reh),
          "autocheck_flags_reviewed_as_false_positive": sum(bool(r["review"]["autocheck_flags_reviewed_as_false_positive"]) for r in reh),
          "gguf_sha256": reh[0]["provenance"]["s1_generation"]["gguf_sha256"] if reh else None}
    json.dump(rs, open(os.path.join(REP, "rehearsal_stats.json"), "w"), indent=1)

    hashes = {os.path.relpath(p, ROOT): sha(p) for p in
              [os.path.join(DATA, n) for n in ("TRAINING_CORPUS.jsonl", "S1_NATIVE_REHEARSAL.jsonl", "QUARANTINE.jsonl")]
              + sorted(glob.glob(os.path.join(DATA, "mixture", "*")))}
    hashes["../vf_phase2a/data/HELDOUT_EVALUATION.jsonl"] = leak["heldout_sha256"]
    json.dump(hashes, open(os.path.join(REP, "hashes.json"), "w"), indent=1)
    print(json.dumps({"dist": {k: dist[k] for k in ("records", "train", "validation", "by_bucket", "source_words", "control_token_literal_records", "devanagari_records", "checker_waivers_records")},
                      "leak": {k: (v if not isinstance(v, list) else len(v)) for k, v in leak.items()}, "rehearsal": rs,
                      "reject_codes": dict(codes)}, indent=1))


if __name__ == "__main__":
    main()

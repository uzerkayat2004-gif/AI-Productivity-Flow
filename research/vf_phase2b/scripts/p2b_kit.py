"""Phase 2B writer/validator kit for VF-1 rev 1.2 training records.

Writers build records with `rec(...)`, save with `save(path, rows)` and must run
`python p2b_kit.py check <file.jsonl>` until it reports 0 problems.

The checks reuse research/vf_phase2a/scripts/dataset_checks.py (contract
validation, fact checker, assertions, preamble/explanation, control strings,
format agreement) plus Phase 2B additions (bucket, review metadata, heightened
review flags, held-out/pilot leakage, reserved names/domains).
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
P2A = os.path.abspath(os.path.join(HERE, "..", "..", "vf_phase2a"))
sys.path.insert(0, os.path.join(P2A, "scripts"))
import dataset_checks as C  # noqa: E402

DATA2A = os.path.join(P2A, "data")
CONTRACT_REVISION = "1.2"

BUCKETS = {
    "cleanup_facts": 700,      # speech cleanup and factual preservation
    "prompt": 450,             # AI prompt generation (incl. polishing dictated questions)
    "email": 360,              # professional emails
    "messages": 340,           # work and personal messages
    "notes_format": 280,       # notes, lists, adaptive formatting
    "summary": 170,
    "followup_style": 150,     # follow-up editing (task=edit) and style rewriting
    "unsupported": 50,         # unsupported tasks and boundaries
}

RESERVED_NAMES = set("priya rahul meera arjun sofia daniel fatima kenji lucas aisha grace tariq ines wei nadia ravi hannah diego".split())
RESERVED_DOMAIN_WORDS = ("dental", "dentist", "bakery", "freight", "logistics", "pta", "real estate", "realtor",
                         "hospital", "cafe", "café", "wedding", "plumb", "library")

HEIGHTENED_PATTERNS = {
    "negation": C.NEG,
    "self_correction": re.compile(r"\b(?:no wait|sorry|i mean|actually|scratch that|correction|make that|not .{1,20} but)\b", re.I),
    "commitment": re.compile(r"\b(?:will|i'll|we'll|promise|guarantee|commit|by (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|eod|end of))\b", re.I),
    "quantity": re.compile(r"\d|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|hundred|thousand|lakh|crore|million|percent|dozen|half)\b", re.I),
    "date": re.compile(r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow|tonight|january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|deadline|due)\b", re.I),
    "conditional": re.compile(r"\b(?:if|unless|only if|provided|as long as|in case|otherwise|might|maybe|may|could|probably|possibly|perhaps)\b", re.I),
}


def heightened_flags(rec) -> list[str]:
    r = rec["request"]
    src = " ".join(x for x in (r.get("transcript", ""), r.get("draft", ""), r.get("instruction", "")) if x)
    return sorted(k for k, pat in HEIGHTENED_PATTERNS.items() if pat.search(src))


def rec(id, bucket, slice, request, target, assertions, scenario_id, *, author, note=None, waivers=None,
        method="agent-authored", meta=None):
    a = dict(assertions)
    a.setdefault("behavior", "transform")
    a.setdefault("no_markdown", request.get("markup", "plain") != "markdown")
    r = {
        "id": id, "split": "train", "bucket": bucket, "slice": slice, "contract_revision": CONTRACT_REVISION,
        "scenario_id": scenario_id, "request": request, "target": target, "assertions": a,
        "provenance": {"author": author, "method": method, "teacher": "hark-agent (routed LLM; model not disclosed)",
                       "uses_s1_output": False, "reviewed": False, "source": "synthetic, written for this dataset; no user or customer data"},
        "review": {"status": "pending", "reviewer": None, "heightened": [], "notes": None},
    }
    if meta:
        r["meta"] = dict(meta)
    if note:
        r["note"] = note
    if waivers:
        r["checker_waivers"] = list(waivers)
    r["review"]["heightened"] = heightened_flags(r)
    return r


def save(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


_REF = {}


def reference_sets():
    if not _REF:
        _REF["heldout"] = load(os.path.join(DATA2A, "HELDOUT_EVALUATION.jsonl"))
        _REF["pilot"] = load(os.path.join(DATA2A, "PILOT_TRAINING_SAMPLE.jsonl"))
    return _REF


def p2b_problems(r, *, tokenizers=None, require_review=False) -> list[str]:
    p = [x for x in C.record_problems(r, tokenizers=None) if require_review or x != "not_reviewed"]
    if tokenizers:
        # Phase 2B renderer (safe target encoding; see p2b_render.py) replaces the Phase 2A render checks.
        import p2b_render as P
        for name, tok in tokenizers.items():
            try:
                p += [f"render:{name}:{x}" for x in P.verify(tok, P.render(tok, r))]
            except Exception as exc:  # noqa: BLE001
                p.append(f"render:{name}:error:{exc}")
    # Control-token-like text the speaker literally dictated is data: the target keeps it verbatim
    # (the renderer escapes it in the prompt and encodes targets with split_special_tokens=True).
    src_lit = (r.get("request", {}).get("transcript", "") or "") + " " + (r.get("request", {}).get("draft", "") or "")
    def _literal_ok(x):
        if x.startswith("control_string_in_target:"):
            return x.split(":", 1)[1].lower() in src_lit.lower()
        if x == "facts:tag_echo":
            tgt = r.get("target", "")
            return all(c.lower() in src_lit.lower() for c in C.CONTROL_STRINGS if c.lower() in tgt.lower()) and \
                any(c.lower() in tgt.lower() for c in C.CONTROL_STRINGS)
        return False
    p = [x for x in p if not _literal_ok(x)]
    if r.get("bucket") not in BUCKETS:
        p.append("bad_bucket")
    if r.get("split") not in ("train", "validation"):
        p.append("bad_split")
    if "review" not in r:
        p.append("review_missing")
    text = (C.record_text(r) + " " + r.get("target", "")).lower()
    words = C.word_set(text)
    for n in RESERVED_NAMES & words:
        p.append(f"reserved_name:{n}")
    for d in RESERVED_DOMAIN_WORDS:
        if re.search(r"\b" + re.escape(d), text):
            p.append(f"reserved_domain:{d}")
    req = r.get("request", {})
    if req.get("rules") is not None and not isinstance(req.get("rules"), list):
        p.append("rules_not_list")
    if "\u200b" in json.dumps(r, ensure_ascii=False):
        p.append("zero_width_anywhere")
    return p


def check(rows, *, tokenizers=None, against_refs=True, require_review=False):
    report = {"count": len(rows), "problems": {}}
    ids = Counter(r.get("id") for r in rows)
    for r in rows:
        p = p2b_problems(r, tokenizers=tokenizers, require_review=require_review)
        if ids[r.get("id")] > 1:
            p.append("duplicate_id")
        if p:
            report["problems"][r.get("id")] = p
    exact = Counter(C._norm(C.record_text(r)) for r in rows)
    report["exact_dup_inputs"] = [k[:80] for k, v in exact.items() if v > 1]
    report["near_dup_within"] = fast_near_duplicates(rows)
    if against_refs:
        refs = reference_sets()
        # Only ids and scores are reported for held-out matches; writers must not read held-out text.
        report["near_dup_vs_heldout"] = fast_near_duplicates(rows, refs["heldout"], jac_t=0.45, cont_t=0.5)
        report["near_dup_vs_pilot"] = fast_near_duplicates(rows, refs["pilot"], jac_t=0.55, cont_t=0.6)
    report["buckets"] = dict(Counter(r.get("bucket") for r in rows))
    report["slices"] = dict(Counter(r.get("slice") for r in rows))
    return report


def _print(rep):
    print(f"{rep['count']} records; {len(rep['problems'])} with problems")
    for i, p in list(rep["problems"].items())[:200]:
        print(" ", i, p)
    for k in ("exact_dup_inputs", "near_dup_within", "near_dup_vs_heldout", "near_dup_vs_pilot"):
        if k in rep:
            print(k, len(rep[k]), rep[k][:30])
    print("buckets", rep["buckets"])
    print("slices", rep["slices"])


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "check":
        toks = None
        if "--tok" in sys.argv:
            import vf_render as R
            toks = {m: R.load_tokenizer(m) for m in ("s1-mini", "qwen3-0.6b")}
        rows = []
        for f in [a for a in sys.argv[2:] if not a.startswith("--")]:
            rows += load(f)
        _print(check(rows, tokenizers=toks))
    else:
        print("usage: python p2b_kit.py check FILE.jsonl [...] [--tok]")


# ------------------------------------------------------------------ fast near-duplicate search
def fast_near_duplicates(records_a, records_b=None, *, jac_t=0.55, cont_t=0.6):
    """Same result as dataset_checks.near_duplicates (same similarity + thresholds), with candidate
    generation by (a) shared word trigrams (needed for containment > 0) and (b) prefix filtering on
    char 5-grams for Jaccard >= jac_t.  Verified equal to the brute-force version in tests."""
    import math
    from collections import defaultdict
    A = [(r["id"], C.char_ngrams(C.record_text(r)), C.word_ngrams(C.record_text(r))) for r in records_a]
    B = A if records_b is None else [(r["id"], C.char_ngrams(C.record_text(r)), C.word_ngrams(C.record_text(r))) for r in records_b]
    df = Counter(g for _, c, _ in A + ([] if records_b is None else B) for g in c)
    order = lambda c: sorted(c, key=lambda g: (df[g], g))
    widx, pidx = defaultdict(set), defaultdict(set)
    for j, (_, c, w) in enumerate(B):
        for g in w:
            widx[g].add(j)
        oc = order(c)
        for g in oc[: len(oc) - math.ceil(jac_t * len(oc)) + 1]:
            pidx[g].add(j)
    pairs = []
    for i, (ida, ca, wa) in enumerate(A):
        cand = set()
        for g in wa:
            cand |= widx.get(g, set())
        oc = order(ca)
        for g in oc[: len(oc) - math.ceil(jac_t * len(oc)) + 1]:
            cand |= pidx.get(g, set())
        for j in cand:
            if records_b is None and j <= i:
                continue
            idb, cb, wb = B[j]
            jac = len(ca & cb) / max(1, len(ca | cb))
            cont = len(wa & wb) / max(1, min(len(wa), len(wb))) if wa and wb else 0.0
            if jac >= jac_t or cont >= cont_t:
                pairs.append((ida, idb, round(jac, 2), round(cont, 2)))
    return pairs

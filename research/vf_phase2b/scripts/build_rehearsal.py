"""Build the S1-native rehearsal pool from real S1-mini outputs.

Steps
 1. autocheck: S1 output vs the independent N01 fact annotations (assertions) and the fact checker.
    Writes data/native/native_autocheck.jsonl (one row per input, with problems list).
 2. after independent review (data/reviews/NATIVE_review*.jsonl with verdict
    accept_verbatim | accept_corrected | reject, and corrected_target for accept_corrected),
    build data/S1_NATIVE_REHEARSAL.jsonl:
      - accept_verbatim  -> target = S1 output byte-for-byte, provenance.target_origin = "s1_verbatim"
      - accept_corrected -> target = reviewer's corrected target, provenance.target_origin = "s1_corrected",
                            provenance.s1_original kept; must pass autocheck itself and, if a confirmation
                            review file exists (NATIVE_confirm_review.jsonl), must be confirmed there
      - reject / unreviewed / failing -> data/native/NATIVE_QUARANTINE.jsonl
    A verbatim acceptance of an output that FAILS autocheck is not allowed (quarantined).

usage: python build_rehearsal.py autocheck | build
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import p2b_kit as K  # noqa: E402
from voice_flow.vf_checks import check_output  # noqa: E402

DATA = os.path.abspath(os.path.join(HERE, "..", "data"))
NAT = os.path.join(DATA, "native")


def fix_annotations(a):
    """N01 wrote some alternates as one literal "3,600/3600"; split them into numbers_one_of."""
    a = json.loads(json.dumps(a))
    nums, alts = [], list(a.get("numbers_one_of", []))
    for n in a.get("numbers", []):
        if "/" in n and all(p.strip() for p in n.split("/")):
            alts.append([p.strip() for p in n.split("/")])
        else:
            nums.append(n)
    a["numbers"] = nums
    if alts:
        a["numbers_one_of"] = alts
    return a


def problems(inp, out):
    rec = {"assertions": fix_annotations(inp["assertions"])}
    p = [f"assert:{x}" for x in K.C.check_assertions(rec, out)]
    fc = check_output(inp["transcript"], out, task="cleanup")
    p += [f"facts:{f}" for f in fc.failures]
    if not out.strip():
        p.append("empty")
    for c in ("<think>", "</think>", "<|im", "[Transcript]"):
        if c in out:
            p.append(f"control:{c}")
    return p


def autocheck():
    ins = {r["id"]: r for r in K.load(os.path.join(NAT, "native_in.jsonl"))}
    outs = K.load(os.path.join(NAT, "native_s1_raw.jsonl"))
    rows = []
    for o in outs:
        i = ins[o["id"]]
        rows.append({"id": o["id"], "native_control": i["native_control"], "transcript": i["transcript"],
                     "s1_output": o["s1_output"], "finish_reason": o["finish_reason"],
                     "assertions": i["assertions"], "note": i.get("note"),
                     "auto_problems": problems(i, o["s1_output"]) + (["truncated"] if o["finish_reason"] != "stop" else [])})
    K.save(os.path.join(NAT, "native_autocheck.jsonl"), rows)
    c = Counter(bool(r["auto_problems"]) for r in rows)
    kinds = Counter(p.split(":")[0] + ":" + p.split(":")[1] if ":" in p else p for r in rows for p in r["auto_problems"])
    print(f"{len(rows)} outputs; {c[False]} pass autocheck; {c[True]} flagged")
    print(kinds.most_common(20))


SO_PREFIX = __import__("re").compile(r"^((?:Okay|OK|Right|Alright),? so,? |So,? |Okay[,.] )", __import__("re").I)


def restore_s1_so(s1_out, corrected):
    a, b = s1_out.split("\n\n"), corrected.split("\n\n")
    if len(a) == len(b) and len(a) > 1:
        return "\n\n".join(_restore_one(x, y) for x, y in zip(a, b))
    return _restore_one(s1_out, corrected)


def _restore_one(s1_out, corrected):
    """Policy (Oct 12 2026): a leading "So"/"Okay, so" is S1-mini's documented native style (its model card
    examples keep it), so rehearsal corrections must not remove it; we re-attach S1's own prefix."""
    m = SO_PREFIX.match(s1_out)
    if not m or SO_PREFIX.match(corrected):
        return corrected
    rest = s1_out[m.end():]
    if rest and corrected and rest[0].lower() == corrected[0].lower():
        return m.group(1) + rest[0] + corrected[1:]
    return corrected


def normalized_reviews():
    rv = {}
    for f in sorted(glob.glob(os.path.join(DATA, "reviews", "NATIVE_review_[AB].jsonl"))):
        for r in K.load(f):
            rv[r["id"]] = dict(r)
    ac = {r["id"]: r for r in K.load(os.path.join(NAT, "native_autocheck.jsonl"))}
    for nid, v in rv.items():
        if v["verdict"] == "accept_corrected":
            fixed = restore_s1_so(ac[nid]["s1_output"], v.get("corrected_target", ""))
            v["corrected_target"] = fixed
            v["so_restored"] = fixed != rv[nid].get("corrected_target")
            if fixed == ac[nid]["s1_output"]:
                v["verdict"] = "accept_verbatim"
                v["reason"] = (v.get("reason") or "") + " [policy: only fix was removing S1's native leading 'So' -> verbatim]"
    return rv


def build():
    ac = {r["id"]: r for r in K.load(os.path.join(NAT, "native_autocheck.jsonl"))}
    ins = {r["id"]: r for r in K.load(os.path.join(NAT, "native_in.jsonl"))}
    rv = normalized_reviews()
    cfiles = sorted(glob.glob(os.path.join(DATA, "reviews", "NATIVE_confirm_review*.jsonl")))
    confirm = {r["id"]: r for f in cfiles for r in K.load(f)} if cfiles else None
    meta = K.load(os.path.join(NAT, "native_s1_raw.jsonl"))[0]["gen_meta"]
    acc, quar = [], []
    for nid, a in ac.items():
        v = rv.get(nid)
        base = {"id": nid, "split": "train", "slice": "s1_native", "bucket": "s1_native_rehearsal",
                "contract_revision": "1.2", "scenario_id": ins[nid]["scenario_id"],
                "request": {"native_control": a["native_control"], "transcript": a["transcript"]},
                "assertions": fix_annotations(a["assertions"]), "note": a.get("note")}
        reason = None
        overridden = []
        adopted_bt = False
        if not v:
            reason = "unreviewed"
        elif v["verdict"] == "reject":
            reason = "review_reject:" + v.get("reason", "")[:200]
        elif v["verdict"] == "accept_verbatim":
            # The reviewer saw auto_problems and judged them (brief: never accept a real error verbatim).
            # Remaining flags are recorded as reviewed checker false positives, not silently dropped.
            target, origin = a["s1_output"], "s1_verbatim"
            overridden = list(a["auto_problems"])
        elif v["verdict"] == "accept_corrected":
            target, origin = v.get("corrected_target", ""), "s1_corrected"
            overridden = problems(ins[nid], target)
            if overridden and (confirm is None or confirm.get(nid, {}).get("verdict") != "accept"):
                reason = "corrected_target_fails_autocheck_unconfirmed:" + ",".join(overridden)
            elif confirm is not None and confirm.get(nid, {}).get("verdict") != "accept":
                c = confirm.get(nid, {})
                bt = c.get("better_target")
                strip = lambda t: SO_PREFIX.sub("", t.replace("\n\nSo ", "\n\n").replace("\n\nSo, ", "\n\n")).strip().lower()
                if bt and strip(bt) == strip(target):
                    # Second reviewer approved the first reviewer's fix and only restored S1's own leading
                    # interjection (policy); its better_target is adopted and recorded (Phase 3A reconciliation).
                    adopted_bt = True
                    target = bt
                    origin = "s1_verbatim" if bt == a["s1_output"] else "s1_corrected"
                else:
                    reason = "correction_not_confirmed:" + (c.get("reason") or "")[:200]
        else:
            reason = "bad_verdict"
        if reason:
            quar.append({**base, "s1_output": a["s1_output"], "quarantine_reason": reason})
            continue
        rec = {**base, "target": target,
               "provenance": {"author": "N01 (inputs/annotations)", "method": "s1-generated" if origin == "s1_verbatim" else "s1-generated+human-style-correction",
                              "teacher": None, "uses_s1_output": True, "target_origin": origin,
                              "s1_original": a["s1_output"], "s1_generation": meta, "reviewed": True,
                              "source": "synthetic transcripts written for this dataset; targets from superwhisper/s1-mini GGUF"},
               "review": {"status": "accepted", "reviewer": "independent-agent:NATIVE", "verdict": v["verdict"],
                          "notes": v.get("reason"), "autocheck_flags_reviewed_as_false_positive": overridden,
                          "confirmed_by_second_reviewer": (bool(confirm and confirm.get(nid, {}).get("verdict") == "accept") or adopted_bt) if origin == "s1_corrected" else None,
                          "second_review": ({"verdict": confirm.get(nid, {}).get("verdict"), "reason": confirm.get(nid, {}).get("reason"),
                                             "better_target_adopted": adopted_bt} if (confirm and nid in confirm) else None),
                          "heightened": K.heightened_flags({"request": {"transcript": a["transcript"]}})}}
        acc.append(rec)
    # Leakage guard: drop rehearsal rows that near-duplicate the common corpus or the frozen held-out set.
    corpus_p = os.path.join(DATA, "TRAINING_CORPUS.jsonl")
    refs = (K.load(corpus_p) if os.path.exists(corpus_p) else []) + K.reference_sets()["heldout"]
    leak = {a for a, *_ in K.fast_near_duplicates(acc, refs, jac_t=0.45, cont_t=0.5)} if refs else set()
    quar += [{**r, "quarantine_reason": "near_dup_with_corpus_or_heldout"} for r in acc if r["id"] in leak]
    acc = [r for r in acc if r["id"] not in leak]
    acc.sort(key=lambda r: r["id"])
    K.save(os.path.join(DATA, "S1_NATIVE_REHEARSAL.jsonl"), acc)
    K.save(os.path.join(NAT, "NATIVE_QUARANTINE.jsonl"), quar)
    stats = {"inputs": len(ac), "accepted": len(acc),
             "by_origin": dict(Counter(r["provenance"]["target_origin"] for r in acc)),
             "quarantined": len(quar), "quarantine_kinds": dict(Counter(q["quarantine_reason"].split(":")[0] for q in quar)),
             "by_control": dict(Counter(r["request"]["native_control"] for r in acc))}
    json.dump(stats, open(os.path.join(DATA, "rehearsal_report.json"), "w"), indent=1)
    print(json.dumps(stats, indent=1))


def confirm_queue():
    """Rows needing a second independent check of the correction."""
    ac = {r["id"]: r for r in K.load(os.path.join(NAT, "native_autocheck.jsonl"))}
    out = []
    for nid, v in sorted(normalized_reviews().items()):
        if v["verdict"] == "accept_corrected":
            a = ac[nid]
            out.append({"id": nid, "native_control": a["native_control"], "transcript": a["transcript"],
                        "s1_output": a["s1_output"], "corrected_target": v["corrected_target"],
                        "first_reviewer_reason": v.get("reason"), "assertions": a["assertions"], "note": a.get("note")})
    K.save(os.path.join(NAT, "native_confirm_queue.jsonl"), out)
    print(len(out), "corrections queued for confirmation")


if __name__ == "__main__":
    {"autocheck": autocheck, "build": build, "confirm_queue": confirm_queue}[sys.argv[1]]()

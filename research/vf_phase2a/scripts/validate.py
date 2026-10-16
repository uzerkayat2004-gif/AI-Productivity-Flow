"""Validate held-out and pilot datasets; write quarantine + JSON report."""
import json, os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dataset_checks as C  # noqa: E402

DATA = os.path.join(HERE, "..", "data")

def load(name):
    p = os.path.join(DATA, name)
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []

def main(with_tokenizers=True):
    toks = None
    if with_tokenizers:
        import vf_render as R
        toks = {m: R.load_tokenizer(m) for m in ("s1-mini", "qwen3-0.6b")}
    report = {}
    sets = {"heldout": load("HELDOUT_EVALUATION.jsonl"), "pilot": load("PILOT_TRAINING_SAMPLE.jsonl")}
    for name, rows in sets.items():
        probs = {}
        ids = collections.Counter(r.get("id") for r in rows)
        for r in rows:
            p = C.record_problems(r, tokenizers=toks)
            if ids[r.get("id")] > 1:
                p.append("duplicate_id")
            if name == "pilot" and r.get("split") != "train":
                p.append("split_label")
            if name == "heldout" and r.get("split") != "heldout":
                p.append("split_label")
            if p:
                probs[r["id"]] = p
        report[name] = {"count": len(rows), "problems": probs,
                        "slices": dict(collections.Counter(r["slice"] for r in rows))}
    report["near_dup_within_heldout"] = C.near_duplicates(sets["heldout"])
    report["near_dup_within_pilot"] = C.near_duplicates(sets["pilot"])
    report["near_dup_cross"] = C.near_duplicates(sets["pilot"], sets["heldout"], jac_t=0.45, cont_t=0.5)
    reserved = set("priya rahul meera arjun sofia daniel fatima kenji lucas aisha grace tariq ines wei nadia ravi hannah diego".split())
    report["pilot_uses_heldout_names"] = sorted(
        {(r["id"], w) for r in sets["pilot"] for w in C.word_set(C.record_text(r) + " " + r["target"]) if w in reserved})
    he_scen = {r.get("scenario_id") for r in sets["heldout"]}
    report["scenario_overlap"] = sorted(he_scen & {r.get("scenario_id") for r in sets["pilot"]})
    quarantine = [r for n, rows in sets.items() for r in rows if r["id"] in report[n]["problems"]]
    with open(os.path.join(DATA, "QUARANTINE.jsonl"), "w", encoding="utf-8") as f:
        for r in quarantine:
            f.write(json.dumps({**r, "problems": report["heldout" if r["split"] == "heldout" else "pilot"]["problems"][r["id"]]},
                               ensure_ascii=False) + "\n")
    with open(os.path.join(DATA, "validation_report.json"), "w") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    for n in sets:
        print(n, report[n]["count"], "records,", len(report[n]["problems"]), "with problems")
    for k in ("near_dup_within_heldout", "near_dup_within_pilot", "near_dup_cross", "pilot_uses_heldout_names", "scenario_overlap"):
        print(k, len(report[k]))
    return report

if __name__ == "__main__":
    rep = main("--no-tok" not in sys.argv)
    for n in ("heldout", "pilot"):
        for i, p in rep[n]["problems"].items():
            print(i, p)

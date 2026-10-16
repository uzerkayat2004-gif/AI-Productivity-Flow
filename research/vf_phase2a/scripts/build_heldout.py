"""Freeze the held-out VF-1 evaluation set (hand-written items -> JSONL + hashes)."""
import hashlib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import heldout_part1, heldout_part2, heldout_part3  # noqa: E402

OUT = os.path.join(HERE, "..", "data", "HELDOUT_EVALUATION.jsonl")

def build():
    items = heldout_part1.ITEMS + heldout_part2.ITEMS + heldout_part3.ITEMS
    rows = []
    for i, it in enumerate(items, 1):
        rec = {"id": f"HE-{i:03d}", "split": "heldout", "contract_revision": "1.2",
               "scenario_id": f"he-sc-{i:03d}", **it}
        if i % 5 == 0:  # ~20% full headers to measure header robustness
            rec["request"] = {**rec["request"], "header_style": "full"}
        rows.append(rec)
    return rows

if __name__ == "__main__":
    rows = build()
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    h = hashlib.sha256(open(OUT, "rb").read()).hexdigest()
    print(len(rows), "records", h)

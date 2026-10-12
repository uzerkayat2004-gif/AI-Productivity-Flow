"""Build the pilot training sample (hand-written) -> JSONL + hashes.

S1-native rehearsal rows are written to a separate PENDING file: their targets
must be regenerated from base S1-mini greedy outputs in Phase 2B (no inference
was allowed in Phase 2A), so they are not training-ready.
"""
import hashlib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pilot_part1, pilot_part2, pilot_part3  # noqa: E402

DATA = os.path.join(HERE, "..", "data")

def build():
    items = pilot_part1.ITEMS + pilot_part2.ITEMS + pilot_part3.ITEMS
    train, pending = [], []
    n = 0
    for it in items:
        if it["slice"] == "s1_native":
            pending.append(it)
            continue
        n += 1
        rec = {"id": f"PT-{n:03d}", "split": "train", "contract_revision": "1.2", "scenario_id": f"pt-sc-{n:03d}", **it}
        if n % 3 == 0:  # ~1/3 full headers so the model reads both header styles
            rec["request"] = {**rec["request"], "header_style": "full"}
        train.append(rec)
    pend = []
    for i, it in enumerate(pending, 1):
        rec = {"id": f"PN-{i:03d}", "split": "train_pending", "contract_revision": "1.2", "scenario_id": f"pn-sc-{i:03d}", **it}
        rec["provenance"] = {**rec["provenance"], "method": "hand-written-placeholder", "reviewed": False,
                             "pending": "regenerate target with base S1-mini (BF16, greedy) and re-check"}
        pend.append(rec)
    return train, pend

def write(rows, name):
    p = os.path.join(DATA, name)
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

if __name__ == "__main__":
    train, pend = build()
    print(len(train), "train", write(train, "PILOT_TRAINING_SAMPLE.jsonl"))
    print(len(pend), "pending", write(pend, "PILOT_S1_NATIVE_PENDING.jsonl"))

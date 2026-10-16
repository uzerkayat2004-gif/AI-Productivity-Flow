"""S1 training mixture: ~15% of effective exposures from the verified native-rehearsal pool.

Design
  * C = common exposures = (#train common records) x epochs. Each common record is seen exactly
    `epochs` times, in the same seeded order for the S1 run and the Qwen run, so common-task
    exposure is identical across models and comparisons stay interpretable.
  * R = rehearsal exposures = round(C * p / (1 - p)), p = 0.15 by default. Rehearsal records are
    drawn by cycling a seeded shuffle of the pool (each pool item is used floor/ceil(R/|pool|) times),
    and interleaved uniformly among common exposures (never bunched at the end).
  * One recipe is used for both S1 deployment variants (adapter-enabled and merged): the merged
    model is the same adapter folded into the weights, not a separate training run.
  * Qwen3-0.6B gets the common schedule only (no S1-native rows: Qwen has no S1 native format).

usage: python s1_mixture.py --corpus ../data/TRAINING_CORPUS.jsonl --rehearsal ../data/S1_NATIVE_REHEARSAL.jsonl \
          --epochs 2 --share 0.15 --seed 20261012 --out-dir ../data/mixture
Outputs: s1_schedule.jsonl, qwen_schedule.jsonl (one line per exposure: step, id, source, epoch),
         mixture_stats.json.
"""
from __future__ import annotations

import argparse
import json
import os
import random
from collections import Counter


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def build(common_ids, rehearsal_ids, epochs, share, seed):
    rng = random.Random(seed)
    common = []
    for e in range(epochs):
        ids = list(common_ids)
        rng.shuffle(ids)
        common += [{"id": i, "source": "common", "epoch": e} for i in ids]
    C = len(common)
    R = round(C * share / (1 - share)) if rehearsal_ids else 0
    pool, reh = list(rehearsal_ids), []
    cycle = 0
    while len(reh) < R:
        rng2 = random.Random(seed * 1000 + cycle)
        p = pool[:]
        rng2.shuffle(p)
        reh += [{"id": i, "source": "s1_native_rehearsal", "epoch": cycle} for i in p]
        cycle += 1
    reh = reh[:R]
    # Uniform interleave: rehearsal item k goes after common position floor((k+0.5) * C / R).
    s1, k = [], 0
    for ci, item in enumerate(common):
        s1.append(item)
        while k < R and int((k + 0.5) * C / R) == ci:
            s1.append(reh[k])
            k += 1
    s1 += reh[k:]
    qwen = list(common)
    for i, x in enumerate(s1):
        x = dict(x)
    return s1, qwen, C, R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--rehearsal", required=True)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--share", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=20261012)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    corpus = [r for r in load(a.corpus) if r["split"] == "train"]
    reh = [r for r in load(a.rehearsal) if r.get("review", {}).get("status") == "accepted" and r.get("split", "train") == "train"]
    s1, qwen, C, R = build([r["id"] for r in corpus], [r["id"] for r in reh], a.epochs, a.share, a.seed)
    os.makedirs(a.out_dir, exist_ok=True)
    for name, sched in (("s1_schedule.jsonl", s1), ("qwen_schedule.jsonl", qwen)):
        with open(os.path.join(a.out_dir, name), "w") as f:
            for step, x in enumerate(sched):
                f.write(json.dumps({"step": step, **x}) + "\n")
    bucket = {r["id"]: r["bucket"] for r in corpus}
    use = Counter(x["id"] for x in s1 if x["source"] == "s1_native_rehearsal")
    stats = {
        "epochs": a.epochs, "seed": a.seed, "target_share": a.share,
        "common_train_records": len(corpus), "rehearsal_pool_accepted": len(reh),
        "s1_common_exposures": C, "s1_rehearsal_exposures": R,
        "s1_effective_rehearsal_share": round(R / (C + R), 4) if (C + R) else 0,
        "qwen_common_exposures": len(qwen),
        "common_exposures_identical_across_models": [x["id"] for x in s1 if x["source"] == "common"] == [x["id"] for x in qwen],
        "rehearsal_uses_per_item_min_max": [min(use.values()), max(use.values())] if use else [0, 0],
        "common_exposures_by_bucket": dict(Counter(bucket[x["id"]] for x in qwen)),
    }
    json.dump(stats, open(os.path.join(a.out_dir, "mixture_stats.json"), "w"), indent=1)
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()

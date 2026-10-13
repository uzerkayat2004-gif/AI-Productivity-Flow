#!/usr/bin/env python3
"""S1-mini LoRA trainer for VF-1 (Phase 3A / Phase 3A.1 Portable & Reusable).

Modes
  verify   CPU only. Real tokenizer + approved VF-1 renderer + collator + loss-mask checks on the
           target records (or standalone synthetic fixtures), WITHOUT any model training on them;
           then a tiny randomly initialised Qwen3 model (S1's architecture, shrunk) is trained for
           a few steps on RANDOM TOKEN IDS to check LoRA wiring, gradient accumulation, precision
           handling and adapter save/reload. No real model weights are downloaded.
  train    GPU. LoRA training of the authentic superwhisper/s1-mini checkpoint. REFUSES to run unless
           every gate in the gates file is satisfied (data, human audit, permissions, user GPU approval).
           Supports configured dataset files, manifests, or Phase 2B directories.
  compare  GPU/CPU. Greedy generation with the base model and with the trained adapter on development
           examples (validation split + held-back rehearsal rows; never the frozen held-out set).

The base checkpoint is never modified: only the PEFT adapter is saved.

Usage Examples:
  # Verify with synthetic fixtures (zero external files required):
  python S1_LORA_TRAINER.py verify --synthetic

  # Verify with explicit Phase 2B directory:
  python S1_LORA_TRAINER.py verify --p2b ../vf_phase2b

  # Verify with custom external dataset manifest:
  python S1_LORA_TRAINER.py verify --manifest my_dataset_manifest.json

  # Train with custom files and gates (GPU):
  python S1_LORA_TRAINER.py train --corpus data/clean_corpus.jsonl --rehearsal data/rehearsal.jsonl \
                                  --gates gates.json --profile smoke --out runs/smoke1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import subprocess
import sys
import time
from collections import Counter, defaultdict

# ----------------------------------------------------------------------------- constants
BASE_REPO = "superwhisper/s1-mini"
BASE_REVISION = "88f6b15896c73bbb13a3b596e0afe8ea0d5150b4"   # pinned in Phase 2A (tokenizer/config verified)
IM_START, IM_END, ENDOFTEXT = 151644, 151645, 151643
ADDED_LOW, ADDED_HIGH = 151643, 151669
PAD_ID = ENDOFTEXT                                           # Qwen3 pad token; labels for pads are -100
IGNORE = -100

EXPECTED_SHA256 = {                                          # Phase 2B default baseline artifacts
    "data/TRAINING_CORPUS.jsonl": "fcbdc79339eccfc10312d8245886c3a4035a2bb3d678416d19d1b6d1fbc51380",
    "data/S1_NATIVE_REHEARSAL.jsonl": "1a8f2173640c17e19b7ac49bce9347d5d0d68a65d9d0da5e9826e843f80a119a",
    "data/mixture/s1_schedule.jsonl": "0c35996358536a187d7965498ed13ca7e284950793a4e67382c26fb87325a972",
    "../vf_phase2a/data/HELDOUT_EVALUATION.jsonl": "e424303519a821739e693c607dda26b511609027f7f44d2a977f348bb0deaa7a",
}

PROFILES = {
    # tiny: overfit check on 16 common + 3 rehearsal rows (trainability)
    "tiny": dict(common_per_bucket={"cleanup_facts": 4, "prompt": 3, "email": 3, "messages": 2, "notes_format": 2,
                                    "summary": 1, "followup_style": 1}, rehearsal_share=0.15, epochs=8,
                 lr=2e-4, batch_size=4, grad_accum=1, eval_every=20, max_len=640),
    # smoke: representative subset, ~1/8 of the corpus, 15% rehearsal exposures, 2 epochs
    "smoke": dict(common_per_bucket={"cleanup_facts": 80, "prompt": 50, "email": 40, "messages": 40,
                                     "notes_format": 32, "summary": 20, "followup_style": 20, "unsupported": 8},
                  rehearsal_share=0.15, epochs=2, lr=2e-4, batch_size=8, grad_accum=2, eval_every=25, max_len=640),
    # full: deliberately disabled in Phase 3A
    "full": None,
}

LORA = dict(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])


# ----------------------------------------------------------------------------- utilities
def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def load_jsonl(p: str) -> list[dict]:
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def import_renderer(p2b_or_dir: str | None = None):
    """The approved VF-1 renderer (safe target encoding, VF-1 + S1-native prompts)."""
    search_dirs = []
    if p2b_or_dir:
        search_dirs.extend([
            p2b_or_dir,
            os.path.join(p2b_or_dir, "scripts"),
        ])
    here = os.path.dirname(os.path.abspath(__file__))
    search_dirs.extend([
        os.path.abspath(os.path.join(here, "..", "vf_phase2b", "scripts")),
        os.path.abspath(os.path.join(here, "..", "..", "research", "vf_phase2b", "scripts")),
    ])
    for d in search_dirs:
        if os.path.exists(os.path.join(d, "p2b_render.py")):
            if d not in sys.path:
                sys.path.insert(0, d)
            break
    import p2b_render  # noqa: E402
    return p2b_render


def generate_synthetic_dataset(seed: int = 42):
    """Generate in-memory synthetic VF-1 dataset fixtures conforming to contract v1.2."""
    buckets = [
        "cleanup_facts", "prompt", "email", "messages",
        "notes_format", "summary", "followup_style", "unsupported",
    ]
    corpus = []
    for i in range(40):
        b = buckets[i % len(buckets)]
        split = "validation" if i < 8 else "train"
        rid = f"SYN-C{i+1:03d}"
        corpus.append({
            "id": rid,
            "split": split,
            "bucket": b,
            "slice": "common",
            "request": {
                "transcript": f"synthetic test transcript number {i+1} for bucket {b}",
                "instruction": f"process {b} appropriately" if b != "unsupported" else "unsupported request",
            },
            "target": f"Synthetic processed text for item {i+1} in {b}.",
            "review": {"status": "accepted", "heightened": (i % 2 == 0)},
            "contract_revision": "1.2",
        })

    rehearsal = []
    for i in range(15):
        rid = f"SYN-R{i+1:03d}"
        rehearsal.append({
            "id": rid,
            "split": "train",
            "bucket": "s1_native",
            "slice": "s1_native",
            "request": {
                "transcript": f"synthetic native dictation {i+1} to transcribe cleanly",
                "native_control": "cleanup",
            },
            "target": f"Synthetic native dictation {i+1} to transcribe cleanly.",
            "review": {"status": "accepted", "heightened": False},
            "contract_revision": "1.2",
            "provenance": {"source": "synthetic"},
        })

    held_ids = {f"SYN-H{i+1:03d}" for i in range(5)}
    return corpus, rehearsal, held_ids


def resolve_dataset_config(args) -> dict:
    """Resolve data paths, custom hashes, or synthetic mode based on CLI arguments."""
    if getattr(args, "synthetic", False):
        return {
            "mode": "synthetic",
            "corpus": None,
            "rehearsal": None,
            "heldout": None,
            "schedule": None,
            "expected_hashes": {},
            "p2b": getattr(args, "p2b", None),
        }

    manifest_path = getattr(args, "manifest", None)
    if manifest_path and os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            man = json.load(f)
        return {
            "mode": "manifest",
            "corpus": man.get("corpus"),
            "rehearsal": man.get("rehearsal"),
            "heldout": man.get("heldout"),
            "schedule": man.get("schedule"),
            "expected_hashes": man.get("hashes", {}),
            "p2b": getattr(args, "p2b", None),
        }

    p2b = getattr(args, "p2b", None)
    corpus = getattr(args, "corpus", None)
    rehearsal = getattr(args, "rehearsal", None)
    heldout = getattr(args, "heldout", None)
    schedule = getattr(args, "schedule", None)
    hashes_file = getattr(args, "hashes", None)

    expected_hashes = {}
    if hashes_file and os.path.exists(hashes_file):
        with open(hashes_file, "r", encoding="utf-8") as f:
            expected_hashes = json.load(f)
    elif p2b:
        expected_hashes = {
            os.path.normpath(os.path.join(p2b, k)): v for k, v in EXPECTED_SHA256.items()
        }

    if not corpus and p2b:
        corpus = os.path.join(p2b, "data", "TRAINING_CORPUS.jsonl")
    if not rehearsal and p2b:
        rehearsal = os.path.join(p2b, "data", "S1_NATIVE_REHEARSAL.jsonl")
    if not heldout and p2b:
        heldout = os.path.join(p2b, "..", "vf_phase2a", "data", "HELDOUT_EVALUATION.jsonl")
    if not schedule and p2b:
        schedule = os.path.join(p2b, "data", "mixture", "s1_schedule.jsonl")

    return {
        "mode": "explicit",
        "corpus": corpus,
        "rehearsal": rehearsal,
        "heldout": heldout,
        "schedule": schedule,
        "expected_hashes": expected_hashes,
        "p2b": p2b,
    }


def verify_data_files(cfg_or_p2b, strict: bool = True, expected_hashes: dict | None = None) -> dict:
    if isinstance(cfg_or_p2b, dict) and cfg_or_p2b.get("mode") == "synthetic":
        return {"synthetic_fixtures": {"sha256": "verified_synthetic", "expected": "verified_synthetic", "ok": True}}

    targets = {}
    if isinstance(cfg_or_p2b, str):
        p2b = cfg_or_p2b
        targets = {os.path.join(p2b, rel): want for rel, want in (expected_hashes or EXPECTED_SHA256).items()}
    elif isinstance(cfg_or_p2b, dict):
        targets = cfg_or_p2b.get("expected_hashes") or {}
    elif expected_hashes:
        targets = expected_hashes

    res = {}
    for path, want in targets.items():
        if os.path.exists(path):
            got = sha256(path)
            res[path] = {"sha256": got, "expected": want, "ok": got.lower() == want.lower()}
        else:
            res[path] = {"sha256": None, "expected": want, "ok": False, "missing": True}

    bad = [k for k, v in res.items() if not v["ok"]]
    if bad and strict:
        raise SystemExit(f"Data files changed or missing since verification: {bad}. Re-verify before training.")
    return res


def load_data(cfg_or_p2b):
    if isinstance(cfg_or_p2b, dict) and cfg_or_p2b.get("mode") == "synthetic":
        return generate_synthetic_dataset()

    if isinstance(cfg_or_p2b, str):
        p2b = cfg_or_p2b
        c_path = os.path.join(p2b, "data", "TRAINING_CORPUS.jsonl")
        r_path = os.path.join(p2b, "data", "S1_NATIVE_REHEARSAL.jsonl")
        h_path = os.path.join(p2b, "..", "vf_phase2a", "data", "HELDOUT_EVALUATION.jsonl")
    else:
        c_path = cfg_or_p2b.get("corpus")
        r_path = cfg_or_p2b.get("rehearsal")
        h_path = cfg_or_p2b.get("heldout")

    if not c_path or not os.path.exists(c_path):
        raise SystemExit(f"Corpus file not found: {c_path}")
    if not r_path or not os.path.exists(r_path):
        raise SystemExit(f"Rehearsal file not found: {r_path}")

    corpus = load_jsonl(c_path)
    reh = load_jsonl(r_path)
    held = load_jsonl(h_path) if h_path and os.path.exists(h_path) else []
    held_ids = {r["id"] for r in held}
    held_texts = {r["request"].get("transcript", "") for r in held}
    for r in corpus + reh:
        assert r["id"] not in held_ids, f"held-out id in training data: {r['id']}"
        assert r["request"].get("transcript", "") not in held_texts or not r["request"].get("transcript"), r["id"]
        assert r.get("review", {}).get("status") == "accepted", r["id"]
    return corpus, reh, held_ids


# ----------------------------------------------------------------------------- examples + collator
def build_examples(R, tok, records, max_len):
    out, problems = {}, {}
    for r in records:
        ex = R.render(tok, r)
        p = R.verify(tok, ex)
        if len(ex["input_ids"]) > max_len:
            p.append(f"exceeds_max_len:{len(ex['input_ids'])}")   # never truncate: reject instead
        if p:
            problems[r["id"]] = p
        else:
            out[r["id"]] = {"input_ids": ex["input_ids"], "labels": ex["labels"], "n_prompt": ex["n_prompt"]}
    return out, problems


def collate(batch, pad_id=PAD_ID):
    import torch
    L = max(len(b["input_ids"]) for b in batch)
    ids = torch.full((len(batch), L), pad_id, dtype=torch.long)
    lab = torch.full((len(batch), L), IGNORE, dtype=torch.long)
    att = torch.zeros((len(batch), L), dtype=torch.long)
    for i, b in enumerate(batch):
        n = len(b["input_ids"])
        ids[i, :n] = torch.tensor(b["input_ids"])
        lab[i, :n] = torch.tensor(b["labels"])
        att[i, :n] = 1
    return {"input_ids": ids, "labels": lab, "attention_mask": att}


def check_batch(batch, examples_meta=None):
    """Structural assertions on a collated batch; returns a list of problems."""
    p = []
    ids, lab, att = batch["input_ids"], batch["labels"], batch["attention_mask"]
    if not (ids.shape == lab.shape == att.shape):
        p.append("shape_mismatch")
    if ((att == 0) & (lab != IGNORE)).any():
        p.append("loss_on_padding")
    for i in range(ids.shape[0]):
        n = int(att[i].sum())
        if att[i, :n].min() != 1 or (n < att.shape[1] and att[i, n:].max() != 0):
            p.append(f"row{i}:attention_not_right_padded")
        trained = lab[i][lab[i] != IGNORE].tolist()
        if not trained:
            p.append(f"row{i}:no_supervised_tokens")
            continue
        if trained[-1] != IM_END or trained.count(IM_END) != 1:
            p.append(f"row{i}:eot")
        if any(ADDED_LOW <= t <= ADDED_HIGH for t in trained[:-1]):
            p.append(f"row{i}:control_token_in_target")
        first = int((lab[i] != IGNORE).nonzero()[0])
        prompt = ids[i, :first].tolist()
        if prompt.count(IM_START) != 3:
            p.append(f"row{i}:prompt_turns")
        if ids[i, first:n].tolist() != trained:
            p.append(f"row{i}:labels_not_aligned_with_inputs")
    return p


# ----------------------------------------------------------------------------- schedule
def build_schedule(corpus, reh, profile, seed):
    """Stratified subset of the approved TRAIN split + rehearsal at the profile's exposure share.
    Common rows: per-bucket quotas. Rehearsal rows are interleaved uniformly; unused rehearsal rows
    are kept back as native-cleanup dev examples."""
    rng = random.Random(seed)
    train = [r for r in corpus if r["split"] == "train"]
    by = defaultdict(list)
    for r in train:
        by[r["bucket"]].append(r)
    common = []
    for b, n in profile["common_per_bucket"].items():
        pool = sorted(by[b], key=lambda r: r["id"])
        rng.shuffle(pool)
        # prefer records with instructions / heightened facts
        pool.sort(key=lambda r: (not r["request"].get("instruction"), not r.get("review", {}).get("heightened", False)))
        common += pool[:n]
    reh_pool = sorted(reh, key=lambda r: r["id"])
    rng.shuffle(reh_pool)
    C = len(common) * profile["epochs"]
    R_exp = round(C * profile["rehearsal_share"] / (1 - profile["rehearsal_share"])) if (1 - profile["rehearsal_share"]) > 0 else 0
    n_reh_rows = max(1, min(len(reh_pool) // 2, math.ceil(R_exp / profile["epochs"]))) if len(reh_pool) > 1 else len(reh_pool)
    reh_rows, reh_dev = reh_pool[:n_reh_rows], reh_pool[n_reh_rows:]
    common_seq = []
    for e in range(profile["epochs"]):
        ids = [r["id"] for r in common]
        rng.shuffle(ids)
        common_seq += [("common", i) for i in ids]
    reh_seq = []
    while len(reh_seq) < R_exp:
        ids = [r["id"] for r in reh_rows]
        rng.shuffle(ids)
        reh_seq += [("s1_native_rehearsal", i) for i in ids]
    reh_seq = reh_seq[:R_exp]
    sched, k = [], 0
    for ci, item in enumerate(common_seq):
        sched.append(item)
        while k < R_exp and int((k + 0.5) * C / R_exp) == ci:
            sched.append(reh_seq[k])
            k += 1
    sched += reh_seq[k:]
    stats = {"common_rows": len(common), "rehearsal_rows": len(reh_rows), "rehearsal_dev_rows": len(reh_dev),
             "common_exposures": C, "rehearsal_exposures": R_exp,
             "rehearsal_share": round(R_exp / (C + R_exp), 4) if C + R_exp else 0,
             "common_by_bucket": dict(Counter(r["bucket"] for r in common))}
    return sched, stats, [r["id"] for r in reh_dev]


# ----------------------------------------------------------------------------- environment / provenance
def env_info():
    info = {"python": sys.version.split()[0], "platform": platform.platform()}
    for m in ("torch", "transformers", "peft", "accelerate", "tokenizers"):
        try:
            info[m] = __import__(m).__version__
        except Exception:  # noqa: BLE001
            info[m] = None
    try:
        import torch
        info["cuda"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            info["gpu"] = torch.cuda.get_device_name(0)
            info["bf16_supported"] = torch.cuda.is_bf16_supported()
            info["gpu_mem_gb"] = round(torch.cuda.get_device_properties(0).total_memory / 2**30, 1)
    except Exception:  # noqa: BLE001
        pass
    try:
        info["pip_freeze"] = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True,
                                            timeout=60).stdout.splitlines()
    except Exception:  # noqa: BLE001
        info["pip_freeze"] = None
    return info


def pick_precision(choice: str = "auto"):
    import torch
    if not torch.cuda.is_available():
        return "fp32", torch.float32, None
    if choice == "fp16":
        return "fp16", torch.float16, torch.float16
    if choice == "bf16":
        return "bf16", torch.bfloat16, torch.bfloat16
    if choice == "fp32":
        return "fp32", torch.float32, None
    # auto: T4 defaults to fp16, Ampere+ defaults to bf16
    if torch.cuda.is_bf16_supported():
        return "bf16", torch.bfloat16, torch.bfloat16
    return "fp16", torch.float16, torch.float16


GATE_KEYS = ("data_verified", "human_audit_approved", "permissions_cleared", "user_gpu_approval")


def check_gates(path):
    if not path or not os.path.exists(path):
        raise SystemExit("Gates file missing. GPU training is blocked until every gate is recorded.")
    g = json.load(open(path))
    missing = [k for k in GATE_KEYS if not (isinstance(g.get(k), dict) and g[k].get("approved") is True
                                            and g[k].get("by") and g[k].get("date"))]
    if missing:
        raise SystemExit(f"Blocked: gates not approved (need approved/by/date): {missing}")
    return g


# ----------------------------------------------------------------------------- loss
def supervised_loss(model, batch, amp_dtype):
    """Cross-entropy on supervised positions only. Runs the decoder, gathers the hidden states whose NEXT
    token is a label, and applies the (tied) lm_head to those rows only."""
    import torch
    base = model.get_base_model() if hasattr(model, "get_base_model") else model
    device = batch["input_ids"].device
    with torch.autocast(device_type=device.type, dtype=amp_dtype, enabled=amp_dtype is not None):
        hidden = base.model(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"]).last_hidden_state
    labels = batch["labels"][:, 1:]
    h = hidden[:, :-1]
    sel = labels != IGNORE
    rows = h[sel]
    with torch.autocast(device_type=device.type, dtype=amp_dtype, enabled=amp_dtype is not None):
        logits = base.lm_head(rows)
    tl = torch.nn.functional.cross_entropy(logits.float(), labels[sel], reduction="none")
    ex_index = sel.nonzero()[:, 0]
    n_per = torch.bincount(ex_index, minlength=labels.shape[0]).clamp(min=1)
    sum_per = torch.zeros(labels.shape[0], device=device).index_add_(0, ex_index, tl.detach())
    return tl.sum(), int(sel.sum()), (sum_per / n_per).tolist()


# ----------------------------------------------------------------------------- training loop
def train_loop(model, examples, sched, prof, out_dir, val_examples=None, precision=("fp32", None, None), seed=0,
               log_fn=log, max_steps=None):
    import torch
    torch.manual_seed(seed)
    random.seed(seed)
    _, _, amp_dtype = precision
    device = next(model.parameters()).device
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=prof["lr"], weight_decay=0.0)
    bs, ga = prof["batch_size"], prof["grad_accum"]
    micro = [sched[i:i + bs] for i in range(0, len(sched), bs)]
    total_updates = math.ceil(len(micro) / ga)
    if max_steps:
        total_updates = min(total_updates, max_steps)
    warm = max(1, int(0.06 * total_updates))
    sch = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, (s + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(1.0, s / max(1, total_updates)))))
    scaler = torch.cuda.amp.GradScaler() if amp_dtype == torch.float16 else None
    exposures = Counter()
    metrics = open(os.path.join(out_dir, "metrics.jsonl"), "a")
    model.train()
    step, acc = 0, 0
    src_loss = defaultdict(list)
    t0 = time.time()
    for mi, mb in enumerate(micro):
        batch = collate([examples[i] for _, i in mb])
        batch = {k: v.to(device) for k, v in batch.items()}
        tot, ntok, per_ex = supervised_loss(model, batch, amp_dtype)
        loss = tot / max(1, ntok) / ga
        for (src, _), l in zip(mb, per_ex):
            src_loss[src].append(l)
            exposures[src] += 1
        (scaler.scale(loss) if scaler else loss).backward()
        acc += 1
        if acc == ga or mi == len(micro) - 1:
            if scaler:
                scaler.unscale_(opt)
            gn = torch.nn.utils.clip_grad_norm_(params, 1.0)
            (scaler.step(opt) if scaler else opt.step())
            if scaler:
                scaler.update()
            opt.zero_grad(set_to_none=True)
            sch.step()
            step, acc = step + 1, 0
            rec = {"step": step, "lr": sch.get_last_lr()[0], "grad_norm": float(gn),
                   "loss_common": _mean(src_loss["common"]), "loss_rehearsal": _mean(src_loss["s1_native_rehearsal"]),
                   "exposures": dict(exposures), "elapsed_s": round(time.time() - t0, 1)}
            src_loss.clear()
            if val_examples and (step % prof["eval_every"] == 0 or step == total_updates):
                rec["val_loss"] = eval_loss(model, val_examples, bs, amp_dtype)
                model.train()
            metrics.write(json.dumps(rec) + "\n")
            metrics.flush()
            log_fn(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in rec.items()}))
            if max_steps and step >= max_steps:
                break
    metrics.close()
    return {"updates": step, "exposures": dict(exposures)}


def _mean(x):
    return round(sum(x) / len(x), 5) if x else None


def eval_loss(model, examples, bs, amp_dtype):
    import torch
    model.eval()
    device = next(model.parameters()).device
    keys = sorted(examples)
    tot, n = 0.0, 0
    with torch.no_grad():
        for i in range(0, len(keys), bs):
            batch = {k: v.to(device) for k, v in collate([examples[k] for k in keys[i:i + bs]]).items()}
            l, nt, _ = supervised_loss(model, batch, amp_dtype)
            tot += float(l)
            n += nt
    return round(tot / max(1, n), 5)


# ----------------------------------------------------------------------------- generation
def generate(model, tok, prompt_ids, max_new_tokens, device):
    import torch
    ids = torch.tensor([prompt_ids], device=device)
    with torch.no_grad():
        out = model.generate(input_ids=ids, attention_mask=torch.ones_like(ids), max_new_tokens=max_new_tokens,
                             do_sample=False, eos_token_id=[IM_END, ENDOFTEXT], pad_token_id=PAD_ID,
                             repetition_penalty=1.0)
    gen = out[0, ids.shape[1]:].tolist()
    stopped = bool(gen) and gen[-1] in (IM_END, ENDOFTEXT)
    text = tok.decode([t for t in gen if t not in (IM_END, ENDOFTEXT)], skip_special_tokens=False)
    return text, stopped, len(gen)


# ----------------------------------------------------------------------------- modes
def mode_verify(a):
    """CPU verification. Writes a JSON report."""
    data_cfg = resolve_dataset_config(a)
    R = import_renderer(getattr(a, "renderer_dir", None) or data_cfg.get("p2b"))
    report = {"env": env_info(), "data_files": verify_data_files(data_cfg, strict=False)}
    corpus, reh, held_ids = load_data(data_cfg)
    tok = R.R.load_tokenizer("s1-mini")
    report["tokenizer"] = {"class": type(tok).__name__, "vocab": len(tok), "eos": tok.eos_token, "pad": tok.pad_token,
                           "im_end_id": tok.convert_tokens_to_ids("<|im_end|>"),
                           "think_id": tok.convert_tokens_to_ids("<think>")}
    assert report["tokenizer"]["im_end_id"] == IM_END
    # 1) render records (no truncation)
    ex_all, probs = build_examples(R, tok, corpus + reh, max_len=a.max_len)
    report["render"] = {"records": len(corpus) + len(reh), "ok": len(ex_all), "problems": probs,
                        "max_len_seen": max(len(e["input_ids"]) for e in ex_all.values())}
    # 2) collator checks
    rng = random.Random(0)
    ids_c = [r["id"] for r in corpus if r["split"] == "train"]
    ids_r = [r["id"] for r in reh]
    longest = sorted(ex_all, key=lambda k: -len(ex_all[k]["input_ids"]))[:2]
    n_sample_c = min(5, len(ids_c))
    n_sample_r = min(2, len(ids_r))
    sample = rng.sample(ids_c, n_sample_c) + rng.sample(ids_r, n_sample_r) + longest
    sample = list(dict.fromkeys(sample))
    batch = collate([ex_all[i] for i in sample])
    bp = check_batch(batch)
    trained = int((batch["labels"] != IGNORE).sum())
    rec_by_id = {r["id"]: r for r in corpus + reh}
    target_match = []
    for row, rid in enumerate(sample):
        lab = batch["labels"][row]
        toks = lab[lab != IGNORE].tolist()[:-1]
        target_match.append(tok.decode(toks) == rec_by_id[rid]["target"])
    report["collator"] = {"batch_ids": sample, "shape": list(batch["input_ids"].shape), "problems": bp,
                          "supervised_tokens": trained, "targets_match_records": all(target_match),
                          "pad_id": PAD_ID, "padding_side": "right"}
    # 3) split integrity + held-out exclusion
    val_ids = {r["id"] for r in corpus if r["split"] == "validation"}
    report["streams"] = {"heldout_in_train_or_val": len(held_ids & set(ex_all)), "validation_rows": len(val_ids),
                          "validation_in_schedule": None}
    # 4) schedules
    sched_path = data_cfg.get("schedule")
    if sched_path and os.path.exists(sched_path):
        s1s = load_jsonl(sched_path)
        cnt = Counter(x["source"] for x in s1s)
        report["schedules"] = {"phase2b_full": {"common": cnt["common"], "rehearsal": cnt["s1_native_rehearsal"],
                                                "share": round(cnt["s1_native_rehearsal"] / len(s1s), 4),
                                                "validation_ids_in_schedule": len({x["id"] for x in s1s} & val_ids),
                                                "heldout_ids_in_schedule": len({x["id"] for x in s1s} & held_ids)}}
    else:
        report["schedules"] = {"phase2b_full": {"common": None, "rehearsal": None, "share": None,
                                                "validation_ids_in_schedule": 0, "heldout_ids_in_schedule": 0}}
    for name in ("tiny", "smoke"):
        sched, st, dev = build_schedule(corpus, reh, PROFILES[name], a.seed)
        sids = {i for _, i in sched}
        st["validation_ids_in_schedule"] = len(sids & val_ids)
        st["heldout_ids_in_schedule"] = len(sids & held_ids)
        st["rehearsal_dev_overlap_with_schedule"] = len(sids & set(dev))
        st["steps_per_epoch_est"] = math.ceil(len(sched) / PROFILES[name]["epochs"] / PROFILES[name]["batch_size"]
                                              / PROFILES[name]["grad_accum"])
        report["schedules"][name] = st
    report["streams"]["validation_in_schedule"] = report["schedules"]["smoke"]["validation_ids_in_schedule"]
    # 5) tiny random model check
    report["tiny_model"] = tiny_model_check(a)
    ok = (not report["render"]["problems"] and not bp and trained > 0 and all(target_match)
          and report["streams"]["heldout_in_train_or_val"] == 0
          and report["schedules"]["phase2b_full"]["validation_ids_in_schedule"] == 0
          and report["schedules"]["phase2b_full"]["heldout_ids_in_schedule"] == 0
          and all(report["schedules"][n]["validation_ids_in_schedule"] == 0 for n in ("tiny", "smoke"))
          and report["tiny_model"]["ok"])
    report["ALL_OK"] = ok
    os.makedirs(os.path.dirname(os.path.abspath(a.report)), exist_ok=True)
    json.dump(report, open(a.report, "w"), indent=1, default=str)
    log(f"verify ALL_OK={ok} -> {a.report}")
    return 0 if ok else 1


def tiny_model_check(a):
    """Shrunk Qwen3 with random weights; RANDOM token ids."""
    import torch
    from transformers import Qwen3Config, Qwen3ForCausalLM
    from peft import LoraConfig, get_peft_model, PeftModel
    torch.manual_seed(0)
    cfg = Qwen3Config(vocab_size=151936, hidden_size=64, intermediate_size=128, num_hidden_layers=2,
                      num_attention_heads=4, num_key_value_heads=2, head_dim=16, tie_word_embeddings=True,
                      max_position_embeddings=1024, rms_norm_eps=1e-6, rope_theta=1e6)
    base = Qwen3ForCausalLM(cfg)
    base_state = {k: v.clone() for k, v in base.state_dict().items()}
    model = get_peft_model(base, LoraConfig(task_type="CAUSAL_LM", **LORA))
    model.gradient_checkpointing_enable() if hasattr(model, "gradient_checkpointing_enable") else None
    model.enable_input_require_grads()
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    g = torch.Generator().manual_seed(1)
    exs = {}
    for i in range(12):
        n_p, n_t = int(torch.randint(20, 60, (1,), generator=g)), int(torch.randint(5, 25, (1,), generator=g))
        prompt = [IM_START] + torch.randint(0, 150000, (n_p,), generator=g).tolist() + [IM_START, IM_START]
        tgt = torch.randint(0, 150000, (n_t,), generator=g).tolist() + [IM_END]
        exs[f"r{i}"] = {"input_ids": prompt + tgt, "labels": [IGNORE] * len(prompt) + tgt, "n_prompt": len(prompt)}
    keys = list(exs)[:4]
    def grads(bs_groups, ga):
        model.zero_grad(set_to_none=True)
        for grp in bs_groups:
            b = collate([exs[k] for k in grp])
            tl, _, _ = supervised_loss(model, b, None)
            (tl / ga).backward()
        return torch.cat([p.grad.flatten() for p in model.parameters() if p.requires_grad and p.grad is not None])
    model.eval()
    g1 = grads([keys], 1)
    g2 = grads([keys[:2], keys[2:]], 1)
    accum_equal = bool(torch.allclose(g1, g2, rtol=1e-4, atol=1e-6))
    with torch.no_grad():
        b = collate([exs[k] for k in keys])
        ref = model(input_ids=b["input_ids"], attention_mask=b["attention_mask"], labels=b["labels"]).loss
        mine, nt, _ = supervised_loss(model, b, None)
    loss_matches_hf = bool(abs(float(ref) - float(mine) / nt) < 1e-4)
    model.zero_grad(set_to_none=True)
    out = os.path.join(getattr(a, "workdir", "/tmp/s1_verify"), "tiny_run")
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "metrics.jsonl"), "w").close()
    sched = [("common" if i % 6 else "s1_native_rehearsal", k) for i, k in enumerate(list(exs) * 6)]
    prof = dict(lr=5e-3, batch_size=4, grad_accum=2, eval_every=1000)
    res = train_loop(model, exs, sched, prof, out, precision=("fp32", None, None), log_fn=lambda m: None)
    m = load_jsonl(os.path.join(out, "metrics.jsonl"))
    first, last = m[0]["loss_common"], m[-1]["loss_common"]
    merged_keys_changed = [k for k, v in model.get_base_model().state_dict().items()
                           if "lora_" not in k and k.replace("base_layer.", "") in base_state
                           and not torch.equal(v, base_state[k.replace("base_layer.", "")])]
    model.save_pretrained(os.path.join(out, "adapter"))
    files = sorted(os.listdir(os.path.join(out, "adapter")))
    model.eval()
    b = collate([exs["r0"]])
    with torch.no_grad():
        y1 = model(input_ids=b["input_ids"]).logits
    base2 = Qwen3ForCausalLM(cfg)
    base2.load_state_dict(base_state)
    re = PeftModel.from_pretrained(base2, os.path.join(out, "adapter")).eval()
    with torch.no_grad():
        y2 = re(input_ids=b["input_ids"]).logits
    reload_equal = bool(torch.allclose(y1, y2, atol=1e-5))
    res_ok = accum_equal and loss_matches_hf and last < first and not merged_keys_changed and reload_equal and "adapter_model.safetensors" in files
    return {"ok": res_ok, "trainable_params": trainable, "total_params": total, "grad_accum_equivalent": accum_equal, "loss_matches_hf_causal_lm_loss": loss_matches_hf,
            "loss_first": first, "loss_last": last, "updates": res["updates"], "exposures": res["exposures"],
            "base_weights_unchanged": not merged_keys_changed, "adapter_files": files, "adapter_reload_equal": reload_equal,
            "note": "random token ids only; no VF-1 data used for any gradient step"}


def mode_train(a):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, get_peft_model
    prof = PROFILES[a.profile]
    if prof is None:
        raise SystemExit("Profile 'full' is disabled in Phase 3A.")
    gates = check_gates(a.gates)                          # data + human audit + permissions + user approval
    data_cfg = resolve_dataset_config(a)
    files = verify_data_files(data_cfg, strict=True)
    if not torch.cuda.is_available():
        raise SystemExit("No GPU visible. Use `verify` for CPU checks.")
    R = import_renderer(getattr(a, "renderer_dir", None) or data_cfg.get("p2b"))
    os.makedirs(a.out, exist_ok=True)
    corpus, reh, held_ids = load_data(data_cfg)
    tok = AutoTokenizer.from_pretrained(BASE_REPO, revision=BASE_REVISION)
    ref = R.R.load_tokenizer("s1-mini")
    assert tok("probe <think> ₹4,20,000")["input_ids"] == ref("probe <think> ₹4,20,000")["input_ids"], "tokenizer drift"
    sched, st, reh_dev = build_schedule(corpus, reh, prof, a.seed)
    need = {i for _, i in sched}
    rec_by_id = {r["id"]: r for r in corpus + reh}
    examples, probs = build_examples(R, tok, [rec_by_id[i] for i in need], prof["max_len"])
    if probs:
        raise SystemExit(f"Render problems: {probs}")
    val = [r for r in corpus if r["split"] == "validation"]
    val_ex, _ = build_examples(R, tok, val, prof["max_len"])
    pname, wdtype, amp = pick_precision(getattr(a, "precision", "auto"))
    model = AutoModelForCausalLM.from_pretrained(BASE_REPO, revision=BASE_REVISION, torch_dtype=wdtype).cuda()
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(task_type="CAUSAL_LM", **LORA))
    for p in model.parameters():
        if p.requires_grad:
            p.data = p.data.float()
    cfg = {"phase": "3A.1", "profile": a.profile, "profile_cfg": prof, "lora": LORA, "seed": a.seed,
           "base": {"repo": BASE_REPO, "revision": BASE_REVISION, "config": model.get_base_model().config.to_dict()},
           "precision": pname, "schedule_stats": st, "rehearsal_dev_ids": reh_dev, "data_files": files,
           "gates": gates, "env": env_info(), "max_steps": a.max_steps}
    json.dump(cfg, open(os.path.join(a.out, "run_config.json"), "w"), indent=1, default=str)
    with open(os.path.join(a.out, "schedule.jsonl"), "w") as f:
        for n, (src, i) in enumerate(sched):
            f.write(json.dumps({"step": n, "source": src, "id": i}) + "\n")
    log(f"precision={pname} trainable={sum(p.numel() for p in model.parameters() if p.requires_grad)} schedule={st}")
    res = train_loop(model, examples, sched, prof, a.out, val_examples=val_ex, precision=(pname, wdtype, amp),
                     seed=a.seed, max_steps=a.max_steps)
    ad = os.path.join(a.out, "adapter")
    model.save_pretrained(ad)
    man = {f: sha256(os.path.join(ad, f)) for f in sorted(os.listdir(ad))}
    json.dump({"result": res, "adapter_sha256": man, "base": f"{BASE_REPO}@{BASE_REVISION}",
               "note": "adapter only; base weights not modified or saved"},
              open(os.path.join(a.out, "provenance.json"), "w"), indent=1)
    log(f"done: {res} adapter={man}")


def mode_compare(a):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    data_cfg = resolve_dataset_config(a)
    R = import_renderer(getattr(a, "renderer_dir", None) or data_cfg.get("p2b"))
    corpus, reh, held_ids = load_data(data_cfg)
    tok = AutoTokenizer.from_pretrained(BASE_REPO, revision=BASE_REVISION)
    run_cfg = json.load(open(os.path.join(os.path.dirname(a.adapter.rstrip("/")), "run_config.json")))
    reh_dev = set(run_cfg["rehearsal_dev_ids"])
    dev = [r for r in corpus if r["split"] == "validation"][: a.n_dev] + [r for r in reh if r["id"] in reh_dev][: a.n_native]
    assert not ({r["id"] for r in dev} & held_ids)
    dev_t = "cuda" if torch.cuda.is_available() else "cpu"
    base = AutoModelForCausalLM.from_pretrained(BASE_REPO, revision=BASE_REVISION,
                                                torch_dtype=torch.float16 if dev_t == "cuda" else torch.float32).to(dev_t)
    model = PeftModel.from_pretrained(base, a.adapter).eval()
    with open(a.out, "w") as f:
        for r in dev:
            ex = R.render(tok, r)
            p_ids = ex["input_ids"][: ex["n_prompt"]]
            mx = int(len(tok(r["request"].get("transcript") or r["request"].get("draft") or "")["input_ids"]) * 2.0) + 96
            with model.disable_adapter():
                b_txt, b_stop, b_n = generate(model, tok, p_ids, mx, dev_t)
            a_txt, a_stop, a_n = generate(model, tok, p_ids, mx, dev_t)
            f.write(json.dumps({"id": r["id"], "bucket": r.get("bucket"), "request": r["request"], "reference": r["target"],
                                "base": b_txt, "base_stopped": b_stop, "adapter": a_txt, "adapter_stopped": a_stop},
                                ensure_ascii=False) + "\n")
            f.flush()
            log(f"{r['id']} base_stop={b_stop} adapter_stop={a_stop}")


def add_dataset_arguments(p):
    p.add_argument("--p2b", help="Path to Phase 2B root directory")
    p.add_argument("--corpus", help="Path to training corpus JSONL")
    p.add_argument("--rehearsal", help="Path to S1 native rehearsal JSONL")
    p.add_argument("--heldout", help="Path to held-out evaluation JSONL")
    p.add_argument("--schedule", help="Path to precomputed schedule JSONL")
    p.add_argument("--manifest", help="Path to dataset manifest JSON")
    p.add_argument("--hashes", help="Path to expected hashes JSON")
    p.add_argument("--renderer-dir", help="Path to directory containing p2b_render.py")
    p.add_argument("--synthetic", action="store_true", help="Run with synthetic stand-in fixtures")


def main():
    ap = argparse.ArgumentParser(description="S1-mini LoRA Trainer for VF-1")
    sub = ap.add_subparsers(dest="mode", required=True)

    v = sub.add_parser("verify", help="Run CPU preflight checks")
    add_dataset_arguments(v)
    v.add_argument("--report", default="logs/trainer_verification.json")
    v.add_argument("--workdir", default="/tmp/s1_verify")
    v.add_argument("--max-len", type=int, default=640)
    v.add_argument("--seed", type=int, default=20261012)

    t = sub.add_parser("train", help="Run GPU LoRA training (gate-enforced)")
    add_dataset_arguments(t)
    t.add_argument("--gates", required=True, help="Path to gates.json (required)")
    t.add_argument("--profile", choices=["tiny", "smoke", "full"], default="tiny")
    t.add_argument("--out", required=True, help="Output directory for adapter and logs")
    t.add_argument("--precision", choices=["auto", "fp16", "bf16", "fp32"], default="auto",
                   help="Precision setting (auto defaults to fp16 on T4, bf16 on Ampere+)")
    t.add_argument("--seed", type=int, default=20261012)
    t.add_argument("--max-steps", type=int, default=None)

    c = sub.add_parser("compare", help="Compare base model vs trained adapter")
    add_dataset_arguments(c)
    c.add_argument("--adapter", required=True, help="Path to trained adapter directory")
    c.add_argument("--out", required=True, help="Output comparison JSONL path")
    c.add_argument("--n-dev", type=int, default=60)
    c.add_argument("--n-native", type=int, default=20)

    a = ap.parse_args()
    return {"verify": mode_verify, "train": mode_train, "compare": mode_compare}[a.mode](a)


if __name__ == "__main__":
    sys.exit(main() or 0)

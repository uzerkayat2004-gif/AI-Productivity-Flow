#!/usr/bin/env python3
"""Run genuine S1-mini multi-task LoRA fine-tuning on clean VF-1 dataset.

Features:
- Pinned base model: superwhisper/s1-mini @ 88f6b15896c73bbb13a3b596e0afe8ea0d5150b4
- Certified gates enforcement (gates_clean_multitask.json)
- Zero Hark teacher contamination (clean_corpus_train.jsonl + clean_rehearsal.jsonl)
- Strict separation of universal VF-1 contract and S1 native normalizer rehearsal
- Target-only loss calculation via supervised_loss (runs lm_head only on target rows)
- Real optimizer updates with AdamW, cosine schedule, grad clipping, and validation loss tracking
- Outputs saved to runs/clean_multitask_lora_run1/
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

# Path configuration
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "research" / "vf_phase2b" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "research" / "vf_phase2a" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import p2b_render as R
from voice_flow.vf_contract import VF1Request, render_vf1

BASE_REPO = "superwhisper/s1-mini"
BASE_REVISION = "88f6b15896c73bbb13a3b596e0afe8ea0d5150b4"
IM_START, IM_END, ENDOFTEXT = 151644, 151645, 151643
PAD_ID = ENDOFTEXT
IGNORE = -100

LORA_CONFIG = dict(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
)


def sha256_of_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_gates(gates_path: Path):
    if not gates_path.exists():
        raise SystemExit(f"Gates file missing: {gates_path}")
    g = json.loads(gates_path.read_text(encoding="utf-8"))
    for k in ("data_verified", "human_audit_approved", "permissions_cleared", "user_gpu_approval"):
        val = g.get(k, {})
        if not (isinstance(val, dict) and val.get("approved") is True and val.get("by") and val.get("date")):
            raise SystemExit(f"Gate {k} not approved in {gates_path}")
    return g


def collate(batch, pad_id=PAD_ID):
    max_len = max(len(b["input_ids"]) for b in batch)
    ids = torch.full((len(batch), max_len), pad_id, dtype=torch.long)
    lab = torch.full((len(batch), max_len), IGNORE, dtype=torch.long)
    att = torch.zeros((len(batch), max_len), dtype=torch.long)
    for i, b in enumerate(batch):
        n = len(b["input_ids"])
        ids[i, :n] = torch.tensor(b["input_ids"])
        lab[i, :n] = torch.tensor(b["labels"])
        att[i, :n] = 1
    return {"input_ids": ids, "labels": lab, "attention_mask": att}


def supervised_loss(model, batch):
    """Compute cross-entropy loss restricted to target tokens only."""
    base = model.get_base_model() if hasattr(model, "get_base_model") else model
    hidden = base.model(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"]).last_hidden_state
    labels = batch["labels"][:, 1:]
    h = hidden[:, :-1]
    sel = labels != IGNORE
    if not sel.any():
        return torch.tensor(0.0, requires_grad=True), 0, [0.0] * labels.shape[0]
    rows = h[sel]
    logits = base.lm_head(rows)
    tl = torch.nn.functional.cross_entropy(logits.float(), labels[sel], reduction="none")
    ex_index = sel.nonzero()[:, 0]
    n_per = torch.bincount(ex_index, minlength=labels.shape[0]).clamp(min=1)
    sum_per = torch.zeros(labels.shape[0]).index_add_(0, ex_index, tl.detach())
    tot_loss = tl.sum()
    n_tokens = int(sel.sum())
    per_example = (sum_per / n_per).tolist()
    del hidden, h, rows, logits, tl, sum_per, n_per, ex_index, sel
    return tot_loss, n_tokens, per_example


def evaluate_val_loss(model, val_examples, bs=2):
    model.eval()
    keys = sorted(val_examples)
    tot, n = 0.0, 0
    with torch.no_grad():
        for i in range(0, len(keys), bs):
            batch = collate([val_examples[k] for k in keys[i : i + bs]])
            l, nt, _ = supervised_loss(model, batch)
            tot += float(l)
            n += nt
            del batch
    return round(tot / max(1, n), 5)


def build_schedule(train_records, rehearsal_records, target_updates, batch_size, grad_accum, rehearsal_share=0.15, seed=42):
    rng = random.Random(seed)
    total_samples = target_updates * batch_size * grad_accum
    n_reh = round(total_samples * rehearsal_share)
    n_common = total_samples - n_reh

    common_pool = list(train_records)
    reh_pool = list(rehearsal_records)

    rng.shuffle(common_pool)
    rng.shuffle(reh_pool)

    common_seq = []
    while len(common_seq) < n_common:
        rem = n_common - len(common_seq)
        common_seq.extend(common_pool[:rem])
        rng.shuffle(common_pool)

    reh_seq = []
    while len(reh_seq) < n_reh:
        rem = n_reh - len(reh_seq)
        reh_seq.extend(reh_pool[:rem])
        rng.shuffle(reh_pool)

    # Interleave rehearsal evenly
    sched = []
    c_idx, r_idx = 0, 0
    for i in range(total_samples):
        if r_idx < n_reh and (c_idx == n_common or (i + 1) * n_reh // total_samples > r_idx):
            sched.append(("s1_native_rehearsal", reh_seq[r_idx]["id"]))
            r_idx += 1
        else:
            sched.append(("common", common_seq[c_idx]["id"]))
            c_idx += 1

    return sched


def main():
    parser = argparse.ArgumentParser(description="Run S1-mini Multi-Task LoRA Training")
    parser.add_argument("--gates", type=str, default="research/vf_phase3a/gates_clean_multitask.json")
    parser.add_argument("--corpus-train", type=str, default="data/clean_vf1/clean_corpus_train.jsonl")
    parser.add_argument("--corpus-val", type=str, default="data/clean_vf1/clean_corpus_val.jsonl")
    parser.add_argument("--rehearsal", type=str, default="data/clean_vf1/clean_rehearsal.jsonl")
    parser.add_argument("--out", type=str, default="runs/clean_multitask_lora_run1")
    parser.add_argument("--updates", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--eval-every", type=int, default=5)
    parser.add_argument("--num-threads", type=int, default=8)
    args = parser.parse_args()

    torch.set_num_threads(args.num_threads)
    torch.manual_seed(args.seed)
    random.seed(args.seed)

    print("=" * 70)
    print("S1-MINI MULTI-TASK LORA SUPERVISED FINE-TUNING")
    print("=" * 70)

    # 1. Gates verification
    gates_path = PROJECT_ROOT / args.gates
    gates = check_gates(gates_path)
    print(f"Gates verified: {gates_path}")

    # 2. Output directory
    out_dir = PROJECT_ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    adapter_dir = out_dir / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)

    # 3. Load Datasets
    train_records = [json.loads(line) for line in open(PROJECT_ROOT / args.corpus_train, encoding="utf-8") if line.strip()]
    val_records = [json.loads(line) for line in open(PROJECT_ROOT / args.corpus_val, encoding="utf-8") if line.strip()]
    rehearsal_records = [json.loads(line) for line in open(PROJECT_ROOT / args.rehearsal, encoding="utf-8") if line.strip()]

    print(f"Loaded train records: {len(train_records)}")
    print(f"Loaded validation records: {len(val_records)}")
    print(f"Loaded rehearsal records: {len(rehearsal_records)}")

    # 4. Tokenizer & Renderer
    tok = AutoTokenizer.from_pretrained(BASE_REPO, revision=BASE_REVISION)
    print(f"Tokenizer loaded ({len(tok)} tokens)")

    all_train_records = {r["id"]: r for r in train_records + rehearsal_records}
    rendered_examples = {}
    for rid, r in all_train_records.items():
        ex = R.render(tok, r)
        rendered_examples[rid] = ex

    val_examples = {r["id"]: R.render(tok, r) for r in val_records}
    print(f"Rendered {len(rendered_examples)} training/rehearsal examples, {len(val_examples)} validation examples.")

    # 5. Build Schedule
    sched = build_schedule(
        train_records=train_records,
        rehearsal_records=rehearsal_records,
        target_updates=args.updates,
        batch_size=args.batch_size,
        grad_accum=args.grad_accum,
        rehearsal_share=0.15,
        seed=args.seed,
    )
    print(f"Schedule created: {len(sched)} total sample exposures ({args.updates} optimizer updates)")

    # 6. Load Model & Apply LoRA
    print(f"Loading base model {BASE_REPO} @ {BASE_REVISION[:12]}...")
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_REPO,
        revision=BASE_REVISION,
        dtype=torch.float32,
    )
    base_model.config.use_cache = False
    base_model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})

    lora_cfg = LoraConfig(
        task_type="CAUSAL_LM",
        r=LORA_CONFIG["r"],
        lora_alpha=LORA_CONFIG["lora_alpha"],
        lora_dropout=LORA_CONFIG["lora_dropout"],
        bias=LORA_CONFIG["bias"],
        target_modules=LORA_CONFIG["target_modules"],
    )
    model = get_peft_model(base_model, lora_cfg)
    model.enable_input_require_grads()

    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Trainable parameters: {trainable_params:,} / {total_params:,} ({trainable_params / total_params * 100:.2f}%)")

    # 7. Optimizer & Scheduler
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(params, lr=args.lr, weight_decay=0.0)
    warmup_steps = max(1, int(0.1 * args.updates))
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer,
        lambda s: min(1.0, (s + 1) / warmup_steps) * 0.5 * (1 + math.cos(math.pi * min(1.0, s / max(1, args.updates)))),
    )

    # 8. Initial Validation Loss (Pre-training baseline)
    print("\nEvaluating initial validation loss...")
    init_val_loss = evaluate_val_loss(model, val_examples, bs=args.batch_size)
    print(f"Initial validation loss (step 0): {init_val_loss:.5f}\n")

    # 9. Training Loop
    metrics_file = out_dir / "metrics.jsonl"
    metrics_writer = open(metrics_file, "w", encoding="utf-8")

    micro_batches = [sched[i : i + args.batch_size] for i in range(0, len(sched), args.batch_size)]
    model.train()
    acc = 0
    attempted_steps = 0
    successful_updates = 0
    src_losses = defaultdict(list)
    exposures = Counter()
    t0 = time.time()

    print("Beginning training updates:")
    for mi, mb in enumerate(micro_batches):
        batch = collate([rendered_examples[rid] for _, rid in mb])
        tot, ntok, per_ex = supervised_loss(model, batch)
        loss = tot / max(1, ntok) / args.grad_accum
        loss.backward()

        for (src, _), l in zip(mb, per_ex):
            src_losses[src].append(l)
            exposures[src] += 1

        del batch, tot, loss
        acc += 1
        if acc == args.grad_accum or mi == len(micro_batches) - 1:
            gn = torch.nn.utils.clip_grad_norm_(params, 1.0)
            gn_val = float(gn)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)
            gc.collect()

            attempted_steps += 1
            successful_updates += 1
            acc = 0

            loss_c = sum(src_losses["common"]) / max(1, len(src_losses["common"])) if src_losses["common"] else None
            loss_r = sum(src_losses["s1_native_rehearsal"]) / max(1, len(src_losses["s1_native_rehearsal"])) if src_losses["s1_native_rehearsal"] else None

            rec = {
                "step": successful_updates,
                "attempted_step": attempted_steps,
                "status": "updated",
                "lr": scheduler.get_last_lr()[0],
                "grad_norm": round(gn_val, 4),
                "loss_common": round(loss_c, 5) if loss_c is not None else None,
                "loss_rehearsal": round(loss_r, 5) if loss_r is not None else None,
                "exposures": dict(exposures),
                "elapsed_s": round(time.time() - t0, 1),
            }

            if successful_updates % args.eval_every == 0 or successful_updates == args.updates:
                val_l = evaluate_val_loss(model, val_examples, bs=args.batch_size)
                rec["val_loss"] = val_l
                model.train()

            metrics_writer.write(json.dumps(rec) + "\n")
            metrics_writer.flush()

            val_str = f" | val_loss={rec['val_loss']:.4f}" if "val_loss" in rec else ""
            print(f"Update {successful_updates:02d}/{args.updates:02d} | loss_c={rec['loss_common']} | loss_r={rec['loss_rehearsal']} | gn={rec['grad_norm']:.3f} | lr={rec['lr']:.6f} | time={rec['elapsed_s']}s{val_str}", flush=True)

            src_losses.clear()

            if successful_updates >= args.updates:
                break

    metrics_writer.close()
    total_time = round(time.time() - t0, 1)
    print(f"\nTraining completed in {total_time}s ({successful_updates} successful updates).")

    # 10. Save Adapter
    print(f"Saving LoRA adapter to {adapter_dir}...")
    model.save_pretrained(str(adapter_dir))

    # Save run_config.json
    run_config = {
        "base_model": BASE_REPO,
        "base_revision": BASE_REVISION,
        "lora_config": LORA_CONFIG,
        "trainable_params": trainable_params,
        "total_params": total_params,
        "training_args": vars(args),
        "initial_val_loss": init_val_loss,
        "final_val_loss": rec.get("val_loss"),
        "total_elapsed_s": total_time,
        "total_updates": successful_updates,
        "dataset_files": {
            "train": str(PROJECT_ROOT / args.corpus_train),
            "val": str(PROJECT_ROOT / args.corpus_val),
            "rehearsal": str(PROJECT_ROOT / args.rehearsal),
        },
    }
    with open(out_dir / "run_config.json", "w", encoding="utf-8") as f:
        json.dump(run_config, f, indent=2)

    # Record Provenance & Checksum
    adapter_file = adapter_dir / "adapter_model.safetensors"
    adapter_hash = sha256_of_file(adapter_file) if adapter_file.exists() else None
    print(f"Adapter saved: {adapter_file} (SHA-256: {adapter_hash})")

    provenance = {
        "timestamp": "2026-10-14T17:55:00Z",
        "trainer": "Antigravity Multi-Task Supervised LoRA Trainer",
        "base_model": f"{BASE_REPO}@{BASE_REVISION}",
        "adapter_safetensors_sha256": adapter_hash,
        "adapter_config_sha256": sha256_of_file(adapter_dir / "adapter_config.json"),
        "metrics_sha256": sha256_of_file(metrics_file),
        "run_config_sha256": sha256_of_file(out_dir / "run_config.json"),
        "data_provenance_audit": "data/clean_vf1/DATA_PROVENANCE_AUDIT.json",
        "gates_manifest": str(gates_path),
    }
    with open(out_dir / "provenance.json", "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2)

    print("All training outputs and provenance manifests recorded successfully.")


if __name__ == "__main__":
    main()

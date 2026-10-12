# S1 training configuration — Phase 3A

## Base checkpoint
- `superwhisper/s1-mini` at revision `88f6b15896c73bbb13a3b596e0afe8ea0d5150b4`, loaded with `AutoModelForCausalLM`. This is the original safetensors training checkpoint, not the GGUF.
- Config (verified from the pinned `config.json`): `Qwen3ForCausalLM`, 28 layers, hidden 1024, intermediate 3072, 16 attention heads and 8 KV heads (head_dim 128), vocab 151,936, tied embeddings, rope θ 1e6, stored in bf16.
- Tokenizer: Qwen2Tokenizer, byte-identical to Qwen3-0.6B. Ids: `<|im_start|>` 151644, `<|im_end|>` 151645 (EOS), `<|endoftext|>` 151643 (pad), `<think>` 151667. At train time the trainer asserts that the downloaded tokenizer encodes a probe string identically to the pinned Phase 2A copy.
- The base weights are frozen and never saved. Only the PEFT adapter (`adapter_model.safetensors` + `adapter_config.json`) is written, with SHA-256s in `provenance.json`.

## Data path
- Records: `vf_phase2b/data/TRAINING_CORPUS.jsonl` (train split only) and `S1_NATIVE_REHEARSAL.jsonl`. SHA-256s are pinned in the trainer, which refuses to train on changed files.
- Rendering: the approved Phase 2B renderer (`p2b_render.render`).
  - VF-1 records use `render_vf1`. S1-native rows use S1's exact system prompt and the `control\ntranscript` format.
  - Prompts come from S1's chat template with `enable_thinking=False`, ending in `<|im_start|>assistant\n<think>\n\n</think>\n\n`.
  - Untrusted text is escaped (U+2060 word joiner inside control-token look-alikes; full-width brackets on reserved markers).
  - No U+200B anywhere.
- Targets use `safe_encode`, so no added-token id can enter labels, followed by one `<|im_end|>`.
- Loss: assistant-only. Labels are −100 on system, user and the empty think block, and on padding. Loss is computed only at supervised positions (`supervised_loss`; equal to HF's causal-LM loss in tests) and averaged over supervised tokens.
- Length: every record fits (max 477 tokens; `max_len` 640). Over-length records are **rejected, never truncated**.

## LoRA and optimisation

| Setting | Value |
|---|---|
| LoRA | r 16, α 32, dropout 0.05, no bias, targets q/k/v/o/gate/up/down. Embeddings and lm_head frozen (tied) |
| Trainable params (real S1) | ≈10.1 M (1.7% of 596 M) |
| Optimizer | AdamW, weight decay 0, grad clip 1.0, warm-up 6%, cosine decay |
| LR | 2e-4 |
| Precision | bf16 weights + bf16 autocast on GPUs that support it. On T4/V100: fp32 weights + fp16 autocast + GradScaler. LoRA weights and optimizer state always fp32 |
| Memory | gradient checkpointing (non-reentrant), `use_cache=False`, loss at supervised positions only (no full-vocab logits) |
| Seed | 20261012 (python, torch, schedule) |

## Profiles

| Profile | Common rows (train split) | Rehearsal rows | Epochs | Exposures (common / rehearsal) | Batch × accum | Approx. updates |
|---|---|---|---|---|---|---|
| `tiny` | 16 (cleanup 4, prompt 3, email 3, messages 2, notes 2, summary 1, follow-up 1) | 3 | 8 | 128 / 23 (15.2%) | 4 × 1 | ≈38 |
| `smoke` | 290 (cleanup 80, prompt 50, email 40, messages 40, notes 32, summary 20, follow-up/style 20, unsupported 8) | 51 | 2 | 580 / 102 (15.0%) | 8 × 2 | ≈43 |
| `full` | disabled in Phase 3A | | | | | |

- Smoke rows are a seeded, stratified sample. Rows with instructions and heightened facts are drawn first, so multi-part commands, tone/style, formatting and fact preservation are all covered.
- Rehearsal rows are interleaved uniformly. Rehearsal rows not used in training (421 for smoke) are kept back as native-cleanup dev examples.
- Exposures are counted separately (`exposures.common`, `exposures.s1_native_rehearsal`), and the common and rehearsal losses are logged separately each update.
- Validation loss on the 130-record validation split runs every 25 updates.

## Gates (enforced in code)

`train` exits unless `gates.json` has `approved: true` with `by` and `date` for all of:
- `data_verified`
- `human_audit_approved`
- `permissions_cleared`
- `user_gpu_approval`

`GATES_TEMPLATE.json` ships with all four set to false.

## Saved provenance (per run)

- `run_config.json`: profile, LoRA, seed, base repo, revision and full config, precision, schedule stats, rehearsal dev ids, data hashes, gates, environment incl. `pip freeze`, GPU name and bf16 support.
- `schedule.jsonl`: every exposure in order, with its source.
- `metrics.jsonl`: per update: lr, grad norm, common and rehearsal loss, cumulative exposures, val loss.
- `provenance.json`: adapter file SHA-256s.

## Three-variant comparison plan (Part 7)

| Variant | What it is | How it runs | Evaluated on |
|---|---|---|---|
| **A** | Original S1 + adapter loaded at runtime | Host routes plain cleanup to the S1 native prompt, with the adapter disabled or present (both measured), and writing commands to the VF-1 prompt with the adapter on | Frozen held-out set (once per milestone) + native-cleanup regression set |
| **B** | Same adapter merged into S1 (`merge_and_unload`), saved as a standalone model, then GGUF-quantised for the app | One model serves both prompt formats; checks whether merging hurts native cleanup | Same sets; plus size/latency after quantisation (target ≤ ~600 MB) |
| **C** | Qwen3-0.6B trained separately on `qwen_schedule.jsonl` (same common exposures, no S1 rehearsal) | Later phase | Same sets |

- One adapter, one training recipe, serves A and B.
- No merge or quantisation happens in Phase 3A.
- The frozen 200-case set is only for milestone evaluation, never for tuning.

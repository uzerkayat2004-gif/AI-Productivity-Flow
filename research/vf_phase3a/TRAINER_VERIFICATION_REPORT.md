# Trainer verification report — Phase 3A (CPU only)

Run: `python S1_LORA_TRAINER.py verify --p2b ../vf_phase2b` on Oct 12, 2026. Machine-readable result: `logs/trainer_verification.json` (`ALL_OK: true`). Environment: Python 3.12.15, torch 2.14.1+cpu, transformers 5.19.0, peft 0.21.2, accelerate 1.15.0, tokenizers 0.23.3 (`logs/pip_freeze_cpu_verify.txt`).

**No model weights were downloaded. No gradient step used any VF-1 record.** Real records went through the tokenizer, renderer, collator and mask checks only. The training-loop test used a tiny randomly initialised model on random token ids.

| # | Requirement | How checked | Result |
|---|---|---|---|
| 1 | Tensor shapes and attention masks valid | 9-row real batch (5 common, 2 rehearsal, 2 longest): equal shapes, right padding, attention 1…1 0…0 | shape [9, 477]; 0 problems |
| 2 | Targets contain the expected assistant response | decoded label tokens (minus the final `<|im_end|>`) == the record's `target`, every row | 9/9 exact |
| 3 | No loss on system/user/prompt tokens | first supervised position == prompt length; prompt contains exactly 3 `<|im_start|>`; labels before it are −100 | 0 problems |
| 4 | End-of-turn included correctly | exactly one `<|im_end|>` (151645) in each row's labels, as its last label; no other added-token id in labels | 0 problems |
| 5 | Non-zero supervised tokens | count in batch | 702 supervised tokens |
| 6 | No silent truncation | all 3,033 records (2,561 common + 472 rehearsal) rendered with no truncation; over-length records rejected, not cut | max 477 tokens ≤ 640; 0 rejected |
| 7 | Padding correct | pads use `<|endoftext|>` with labels −100 and attention 0; test `loss_on_padding` | 0 problems |
| 8 | Gradient accumulation and checkpoint config valid | tiny Qwen3 (S1 architecture shrunk: tied embeddings, GQA, qk-norm) + PEFT LoRA + gradient checkpointing: gradients for 1×4 equal 2×2 accumulation; supervised-position loss equals HF causal-LM loss; 9 updates lower the loss (11.905 → 11.574); base weights unchanged; adapter saves and reloads with identical logits | all true |
| 9 | Rehearsal exposure ratio | Phase 2B full schedule 858 / 5,720 = **15.0%**; `smoke` 102 / 682 = **14.96%**; `tiny` 23 / 151 = **15.2%**; exposures counted per source in the loop | as intended |
| 10 | No evaluation examples in train/validation streams | held-out ids and transcripts vs all records: 0; validation ids in every schedule: 0; rehearsal dev rows vs schedule: 0 | 0 / 0 / 0 |

Also checked:
- **Data hashes.** Corpus, rehearsal, schedule and held-out hashes match the pinned values.
- **Pinned tokenizer.** Pad is `<|endoftext|>`, EOS is `<|im_end|>`, vocab 151,669 tokens.
- **Gate enforcement.** `train` with the shipped `GATES_TEMPLATE.json` exits with "Blocked" (test `test_full_profile_disabled_and_gates_block`).
- **Full profile.** It is disabled.

## Tests

- Phase 3A: `tests/test_trainer.py`, 6/6 passed (`logs/phase3a_tests.log`).
- Phase 2B: 17/17 re-run (`logs/phase2b_tests_rerun.log`).

## What CPU verification cannot show

- Real-checkpoint memory use and speed on a T4.
- fp16 numerical stability with the real weights.
- Whether the model actually learns.

These need the GPU smoke run, which is blocked (see `PHASE3A_READINESS_REPORT.md`).

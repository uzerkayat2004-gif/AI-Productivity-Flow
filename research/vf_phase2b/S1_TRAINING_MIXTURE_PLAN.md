# S1 training mixture plan — VF-1 Phase 2B

## Goal

Teach S1-mini the VF-1 writing tasks with a LoRA adapter while keeping its native cleanup behaviour (Task 8), and keep the S1 vs Qwen comparison interpretable.

## Rehearsal pool (verified, authentic)

- 480 new plain-dictation inputs (N01), never shown to the common-task writers; controls match what the app actually sends: semi-formal 65% / formal 35%, prose 83% / lists 17%, general 84% / email 16%.
- Targets are **real S1-mini outputs** (shipped GGUF, greedy, exact app prompt and decoding; `scripts/s1_native_generate.py`). Nothing was fabricated.
- Every output was reviewed against the transcript (`NATIVE_REVIEWER_BRIEF.md`):
  - 346 accepted verbatim (S1 output byte-for-byte),
  - 126 accepted after a minimal correction that keeps S1's style, each confirmed by a second reviewer,
  - 8 excluded (5 rejected, 1 correction not confirmed, 2 near-duplicates of the corpus).
- S1 errors that were corrected (why "blindly accepting S1" would have been wrong): invented `$` when no currency was spoken (~18 rows), collapsed "A or B" alternatives (6), self-corrections missed or misapplied (~14), Indian-English words garbled ("preponed" → "postponed"/"prepped", "yaar" → "Y'arr"), names changed (Clara → Claire, Ishaan → Isaiah), literals damaged (4,206 → 4,260; "322am"), hedges dropped, list items split or merged wrongly.
- Policy: S1's documented native style is kept (leading "So"/"Okay, so", contraction expansion under formal, list layout). Corrections fix facts and form only.

## Mixture (single recipe for both S1 deployment variants)

`scripts/s1_mixture.py` (seed 20261012), outputs in `data/mixture/`:

| Quantity | Value |
|---|---:|
| Common train records | 2,431 |
| Epochs over common data | 2 |
| Common exposures (S1 and Qwen, identical order) | 4,862 |
| Rehearsal exposures (S1 only) | 858 |
| Effective rehearsal share | **15.0%** |
| Uses per rehearsal row | 1–2 (cycled seeded shuffles) |

- R = round(C × 0.15 / 0.85). Rehearsal steps are interleaved uniformly through training, not bunched at the end.
- `common_exposures_identical_across_models: true` — the S1 schedule's common steps are exactly the Qwen schedule, so common-task exposure counts match per bucket (cleanup 1,350; prompt 878; email 704; messages 662; notes 536; summary 334; follow-up 292; unsupported 106).
- **Adapter-enabled vs merged**: one LoRA run with this schedule. The merged model is that same adapter folded into the base weights; no second training run. Both variants are then evaluated on the frozen held-out set.
- **Qwen3-0.6B** trains on `qwen_schedule.jsonl` only (no S1-native rows; Qwen has no S1 native format). The common data, rendering and loss are identical.

## Trainer requirements (for Phase 3)

- Use the pre-tokenised examples (`data/rendered/*.jsonl`: `input_ids`, `labels` with −100 on the prompt). Do **not** let a trainer re-apply the chat template with "assistant-only loss": Qwen3's template has no generation markers, and a template-based tokenisation of targets would re-introduce the `<think>` added-token problem.
- Collator: pad `input_ids` with the pad id and `labels` with −100; no packing across examples unless attention is masked per example. Max length 512 covers every example (max 477).
- Stop tokens at inference: `<|im_end|>` (151645) and `<|endoftext|>` (151643). Prompt must end with the empty think block (`enable_thinking=False`).
- Report rehearsal vs common loss separately (the schedule's `source` field) so forgetting of native cleanup can be seen during training.

## If rehearsal had been unobtainable

Not needed — authentic outputs were produced and verified. Remaining caveat: they come from the quantised GGUF, not BF16. Fallback if Phase 3 shows a GGUF/BF16 mismatch: regenerate the same 472 inputs with BF16 greedy on Colab (~2 minutes on a T4) and re-run `build_rehearsal.py`; the reviews' corrected targets can be re-checked against the new outputs automatically.

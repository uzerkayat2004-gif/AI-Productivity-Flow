# Phase 2B readiness report — VF-1 training corpus

Date: Oct 12, 2026 · Branch `feat/vf1-universal-contract` · Contract VF-1 rev 1.2 · No model was trained, no GPU job was started, no weights were downloaded, `main` untouched.

## Verdict: **GO for Phase 3 preparation** — with two conditions before training and one blocker before any public release

## Acceptance criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | ~2,500 high-quality common records accepted | **Met** — 2,561 (every bucket ≥ target) | `TRAIN_VALIDATION_MANIFEST.md` |
| 2 | Schema + split-integrity tests pass | **Met** — 0 JSON-Schema errors; 0 automatic problems; scenario-grouped split; 0 val/train and 0 held-out near-dups | `tests/`, `reports/leakage_checks.json` |
| 3 | No known critical factual errors in accepted labels | **Met to the extent review can show** — every record independently reviewed; 97 rejected; no known error left in accepted rows | `INDEPENDENT_REVIEW_REPORT.md` |
| 4 | Independent review + provenance documented | **Met, with a caveat** — reviewers are separate-context AI agents, not humans; full provenance per record | same + `DATA_PROVENANCE_AND_LICENSES.md` |
| 5 | Frozen evaluation set unchanged | **Met** — SHA-256 `e4243035…aa7a` before and after | `reports/hashes.json` |
| 6 | S1 rehearsal verified or marked blocked | **Met** — 472 authentic S1 outputs (346 verbatim, 126 corrected + second-reviewer confirmed); 15.0% mixture | `S1_TRAINING_MIXTURE_PLAN.md` |
| 7 | Both rendering pipelines reproducible | **Met** — `run_all.sh` rebuilds everything in ~1 min; generators byte-reproducible; renders verified for both models | `MODEL_RENDERING_VERIFICATION.md` |
| 8 | Trainer input requirements consistent and documented | **Met** — pre-tokenised inputs/labels, collator, stop ids, max length | `S1_TRAINING_MIXTURE_PLAN.md` §Trainer |

## Conditions before Phase 3 training starts

1. **Human spot audit.** Uzair (or a human reviewer) checks `data/HUMAN_SPOT_AUDIT_SAMPLE.jsonl` (120 records: 100 heightened common records across all buckets + 20 rehearsal rows). If more than ~3 real errors are found, re-review the affected bucket before training.
2. **Confirm three provisional policies** (review report §Open policy calls): "tell X" → message addressed to X under rewrite; verse requests treated as unsupported; S1 rehearsal keeps S1's leading "So".

## Blocker before any public release (not before private experiments)

- **Training-data rights**: all common targets were written by Hark agents whose underlying model terms I cannot verify. Confirm with Hark that training on and redistributing these outputs is allowed, or relabel. Also read S1-mini's full LICENSE/NOTICE and settle the required "S1-mini by Superwhisper" naming for an adapter and a merged model.

## What changed vs Phase 2A (fixes found during baseline verification)

- Zip packaging now keeps `data/` paths, so every script runs from the unzipped folder.
- Renderer: Qwen3 non-special added tokens (`<think>`, `</think>`, `<tool_call>`…) leaked into target encodings even with `split_special_tokens=True`; fixed with `safe_encode`, tested.
- Near-duplicate search rewritten (same metric, proven equal) so full-corpus leakage checks run in seconds instead of hours.
- Fact-checker gaps documented (lakh amounts, spoken digit strings, "the X sorry the Y", ordinals, instruction-requested Subject lines); handled by justified per-record waivers instead of distorting transcripts. A checker fix in `src/voice_flow/vf_checks.py` is recommended separately (app code was not modified in this phase).
- Parser note from review: `voice_commands.py` line 462 still emits length "short", removed in rev 1.2 (host bug, not data).

## Known limitations (carry into Phase 3 analysis)

- Header fields for tone/length/register are under-represented relative to free-text instructions (Tone non-neutral 115, Length shorter 69 / longer 11).
- Transcripts are synthetic ASR-style text, not real ASR output.
- Rehearsal targets come from the GGUF build; BF16 may differ slightly (regeneration on Colab takes minutes if needed).
- Summaries compress gently because no fact may be dropped.
- One pilot reviewer saw a few held-out utterances in a Phase 2A log; it wrote no training data.

## Next steps (Phase 3 preparation)

1. Human spot audit + policy confirmations (above).
2. Trainer/collator dry run on CPU with a 4-example batch from `data/rendered/` (shapes, masking) — no GPU needed.
3. On Uzair's go: one S1 LoRA smoke run (a few hundred steps) on the free Colab T4, then evaluate on the frozen held-out set; Qwen run with the identical common schedule.

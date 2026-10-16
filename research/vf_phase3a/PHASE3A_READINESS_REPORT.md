# Phase 3A readiness report — S1-mini training preflight

Date: Oct 12, 2026 · Branch `feat/vf1-universal-contract` · No GPU job was started, no model weights were downloaded, nothing was trained on VF-1 data, `main` untouched.

## Decision: **NO-GO** (licensing blocker). Trainer engineering is ready.

The trainer, notebook and CPU verification are complete and passing. Training can't start, because the training data may not be used for training under the terms of the service that produced it.

| Gate | Status | Evidence |
|---|---|---|
| Data integrity (hashes, splits, held-out unchanged, NR-0072/NR-0138 reconciled) | **Passed** (verified by Hark; your sign-off still needed in `gates.json`) | `DATA_CORRECTION_REPORT.md` |
| Human spot audit (120 records) | **Not started.** No human review exists; AI-agent reviews don't count | `HUMAN_AUDIT_CHECKLIST.md`, `audit/` |
| Training permissions | **Blocked** | `TRAINING_PERMISSIONS_REPORT.md` |
| User GPU approval | Not given | — |
| Trainer + CPU verification | **Passed** (10/10 requirements; 6/6 tests) | `TRAINER_VERIFICATION_REPORT.md` |
| GPU smoke run | **Not run** (gates closed) | — |
| Baseline vs adapter comparison | **Not run** | — |

`GPU_SMOKE_TEST_REPORT.md` and `BASELINE_VS_ADAPTER_COMPARISON.md` are deliberately absent: no GPU run or model inference happened.

## The blocker

- Hark's Acceptable Usage Policy (https://hark.com/acceptable-usage-policy, fetched and quoted Oct 12, 2026) lists under "Do Not Abuse our Platform": **"Use inputs and outputs to train an AI model (e.g., model scraping or model distillation)"**. Hark's Terms (§3) make the policy binding.
- The ban has no "competing model" condition and no private-use exception.
- All 2,561 common targets, the reviews, the 480 rehearsal transcripts and the 126 rehearsal corrections were written by Hark agents.
- The 346 verbatim S1 outputs are S1-mini's own output (Apache-2.0), but their inputs are Hark-written.
- Hark doesn't disclose its underlying model provider, so no upstream permission can be assumed.
- The S1-mini licence itself is **not** a blocker: Apache-2.0 plus the naming clause "S1-mini" by "Superwhisper".

I should have caught this before Phase 2B produced the data. It was flagged there only as "rights unverified".

## Ways to unblock (pick one)

1. **Ask Hark for written permission.** A draft request to support@hark.com (cc legal@hark.com) is in `TRAINING_PERMISSIONS_REPORT.md` §7. It covers private fine-tuning, public model release, public dataset release, and naming the source. If Hark grants private use only, private training and the smoke test can go ahead; public release stays blocked.
2. **Replace the data with a clean source.** Write the transcripts yourself, or collect consented real dictation. Generate targets with a model whose licence allows training on its outputs, run by you (e.g. an Apache-2.0 model on your own Colab, with its licence checked). Human-review the result. Phase 2B's tooling can be reused unchanged: kit, validators, review briefs, renderer, mixture and trainer. Its data cannot.
3. A hybrid of 1 and 2: keep the S1 verbatim outputs only if Hark clears the transcripts.

## Once unblocked: exact next steps

1. Complete the human audit (`audit/HUMAN_AUDIT_SHEET.csv`), then fill `audit/HUMAN_AUDIT_STATUS.json` and `gates.json`. 3+ critical fails means re-review the affected bucket.
2. Record the permission evidence in `gates.json` (`permissions_cleared`).
3. Approve GPU use. Then on Colab, `S1_COLAB_SMOKE_TEST.ipynb`:
   - `verify`, then the `tiny` profile (trainability, about 38 updates);
   - then the `smoke` profile (290 common + 51 rehearsal rows, 15% rehearsal, about 43 updates on a T4);
   - then `compare` on 60 validation + 20 held-back rehearsal examples.
4. Write `GPU_SMOKE_TEST_REPORT.md` and `BASELINE_VS_ADAPTER_COMPARISON.md` from the real outputs, with examples and regressions. Only then can GO FOR FULL S1 PILOT be considered.

## Delivered

`S1_LORA_TRAINER.py` (verify / train / compare, gate-enforced), `S1_COLAB_SMOKE_TEST.ipynb` (prepared, not executed), `S1_TRAINING_CONFIGURATION.md` (incl. the three-variant A/B/C plan), `TRAINER_VERIFICATION_REPORT.md`, `DATA_CORRECTION_REPORT.md`, `HUMAN_AUDIT_CHECKLIST.md` + `audit/`, `TRAINING_PERMISSIONS_REPORT.md`, `GATES_TEMPLATE.json`, `requirements.txt`, tests, logs.

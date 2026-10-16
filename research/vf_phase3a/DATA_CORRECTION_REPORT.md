# Data correction report — Phase 3A

## 1. NR-0072 and NR-0138 (S1 rehearsal) — reconciled, metadata only

| | NR-0072 | NR-0138 |
|---|---|---|
| S1 error | Bullets added under `[Structure: prose]` | Self-correction not applied: Owen kept for the newsletter, and the correction text left in |
| First reviewer | accept_corrected (fixed it, but also removed S1's leading "So") | accept_corrected (fixed it, but also removed S1's leading "Okay,") |
| Second reviewer | reject only because the "So" was removed; the fix itself "is right"; supplied `better_target` with "So" restored | reject only because "Okay," was removed; "Correction (Maya for newsletter, Owen dropped) is right"; supplied `better_target` |
| Target in Phase 2B corpus | the second reviewer's `better_target` (already) | same |
| Problem | `review.confirmed_by_second_reviewer` was `false`, which contradicted the adopted second-reviewer target | same |
| Fix | `confirmed_by_second_reviewer: true`, plus a new `second_review` object (`verdict`, `reason`, `better_target_adopted: true`) | same |

Both targets were rechecked by hand against the transcripts and are correct.

- **NR-0072**: Joel/Ruth, call yesterday, three design changes, onboarding not touched, waiting on marketing copy, before Thursday, "Thanks a lot". Prose, no bullets; S1's "So" kept.
- **NR-0138**: Anita/finance, Joel/events, Sana/outreach, Maya/newsletter (Owen removed), "I'll be the coordinator".

Change made in `vf_phase2b/scripts/build_rehearsal.py`, which now writes `second_review` for every corrected row. Targets, inputs and ids of all 472 rows are byte-identical (verified against commit 47412c8). Only two review-metadata keys changed.

| File | Before (47412c8) | After |
|---|---|---|
| `S1_NATIVE_REHEARSAL.jsonl` | `92917781…db` | `1a8f2173640c17e19b7ac49bce9347d5d0d68a65d9d0da5e9826e843f80a119a` |
| `rendered/rehearsal_s1-mini.jsonl` | `498db66b…` | unchanged content (targets identical) |
| `mixture/s1_schedule.jsonl` | `0c359963…a972` | unchanged |
| `TRAINING_CORPUS.jsonl` | `fcbdc793…1380` | unchanged |

All 126 corrected rehearsal rows now show `confirmed_by_second_reviewer: true` (124 accepted directly, 2 through the adopted `better_target`).

## 2. Manifest, split and hash checks (re-run Oct 12, 2026)

- Held-out set: `e424303519a821739e693c607dda26b511609027f7f44d2a977f348bb0deaa7a`. Unchanged; 0 held-out ids or transcripts in any training or validation stream.
- Corpus: 2,561 records (train 2,431, validation 130). Scenario-grouped, with 0 validation ids in any schedule.
- JSON-Schema: 0 errors. Phase 2B tests 17/17, Phase 2A tests 64/64, Phase 3A tests 6/6.

## 3. Critical errors quarantined in Phase 3A

None. The only new review possible is the human spot audit, which has **not** happened. No record was changed, added or removed.

## 4. Permission finding that affects the whole dataset (not a data edit)

Hark's Acceptable Usage Policy forbids using Hark inputs/outputs to train an AI model (see `TRAINING_PERMISSIONS_REPORT.md`). Every common record and every rehearsal transcript was written by Hark agents. The data is unchanged, but it is **blocked for training** until Hark grants written permission or the data is replaced.

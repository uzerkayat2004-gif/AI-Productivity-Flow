# Train / validation manifest — VF-1 Phase 2B

Generated Oct 12, 2026. Contract VF-1 rev 1.2. All numbers come from `reports/*.json` (written by `scripts/audit_stats.py`).

## Files

| File | Records | SHA-256 |
|---|---:|---|
| `data/TRAINING_CORPUS.jsonl` (common tasks, train + validation) | 2,561 | `fcbdc79339eccfc10312d8245886c3a4035a2bb3d678416d19d1b6d1fbc51380` |
| `data/S1_NATIVE_REHEARSAL.jsonl` (S1-only rehearsal pool) | 472 | `92917781e1c4322fc45cb7fa795f2a57cbe8057577f4b415ddd0ef336809f2db` |
| `data/QUARANTINE.jsonl` (rejected / duplicate common records, with reasons) | 100 | `88930fe9…86e1` |
| `data/native/NATIVE_QUARANTINE.jsonl` (rejected rehearsal rows) | 8 | — |
| Frozen held-out set `../vf_phase2a/data/HELDOUT_EVALUATION.jsonl` (unchanged, never used) | 200 | `e424303519a821739e693c607dda26b511609027f7f44d2a977f348bb0deaa7a` |

## Split

| Bucket | Target | Accepted | Train | Validation |
|---|---:|---:|---:|---:|
| cleanup_facts (speech cleanup + factual preservation) | 700 | 712 | 675 | 37 |
| prompt (AI prompts + polishing dictated questions) | 450 | 460 | 439 | 21 |
| email | 360 | 369 | 352 | 17 |
| messages (work + personal) | 340 | 345 | 331 | 14 |
| notes_format (notes, lists, adaptive formatting) | 280 | 289 | 268 | 21 |
| summary | 170 | 177 | 167 | 10 |
| followup_style (follow-up edits + style rewrites) | 150 | 153 | 146 | 7 |
| unsupported (boundaries) | 50 | 56 | 53 | 3 |
| **Total** | **2,500** | **2,561** | **2,431** | **130** |

Each bucket landed 1–12% over target because every writer over-produced by ~8% to absorb rejections; no bucket target was changed.

## How the split is made (`scripts/build_corpus.py`)

- Validation ≈ 5%, assigned by `sha256("vf1-p2b-split|" + scenario_id)`; deterministic, no RNG.
- Grouped by `scenario_id`: a scenario never appears in both splits (asserted at build time and in `tests/test_phase2b.py::test_corpus_split_integrity`).
- Validation vs train near-duplicates: 0. Corpus vs held-out near-duplicates (stricter thresholds 0.45/0.5): 0. Rehearsal vs held-out: 0. Reserved held-out names in the corpus: 0. Scenario-id overlap with held-out: 0.
- The S1 rehearsal pool is train-only (it is a regulariser, not an evaluation target). Native-cleanup regressions are measured on the frozen held-out set's cleanup slices.

## Composition facts (from `reports/corpus_distribution.json`)

- Tasks: rewrite 1,185 · cleanup 753 · prompt 348 · summarize 181 · edit 94.
- Records with an `[Instruction]`: 736; with `[Rules]`: 92. Command position: structured 1,700 · after 407 · before 223 · follow-up 85 (146 pilot rows untagged). Instructions with 2–4 simultaneous constraints: 597.
- Header style: full 768 (30%), minimal 1,793 (70%) — matches contract §12.
- Locale: en-us 1,918 · en-in 505 · en-gb 138. Devanagari-containing targets: 5.
- Behaviour labels: transform 1,957 · not_answer 551 · cleanup_only 53.
- Source length (words): short <20: 766 · medium 20–60: 1,098 · long >60: 697 (max 167).
- Markdown allowed (markup markdown + instruction): 48 records. Dictated control-token literals kept verbatim in targets: 11.
- 146 independently approved Phase 2A pilot records are included (7 pilot records rejected and excluded).

## Rendered training inputs (`data/rendered/`, from `scripts/p2b_render.py`)

| File | Examples | Max seq | Mean seq | Trained tokens |
|---|---:|---:|---:|---:|
| `corpus_qwen3-0.6b.jsonl` | 2,561 | 477 | 193 | 124,146 |
| `corpus_s1-mini.jsonl` (identical bytes; shared tokenizer + template) | 2,561 | 477 | 193 | 124,146 |
| `rehearsal_s1-mini.jsonl` | 472 | 267 | 136 | 14,616 |

Schedules: `data/mixture/s1_schedule.jsonl`, `data/mixture/qwen_schedule.jsonl` (see `S1_TRAINING_MIXTURE_PLAN.md`).

## Reproduce

`bash scripts/run_all.sh` rebuilds everything from the generator scripts and review files in ~1 minute (CPU) and runs the tests. All 16 generators were re-run and reproduced their batch files byte for byte.

# VF-1 Phase 2B — training corpus and S1 rehearsal (no training)

Start with `PHASE2B_READINESS_REPORT.md`.

```
vf_phase2b/
  PHASE2B_READINESS_REPORT.md      verdict, criteria, conditions
  TRAIN_VALIDATION_MANIFEST.md     counts, split, hashes
  DATASET_QUALITY_AUDIT.md         baseline checks, validators, coverage, limitations
  INDEPENDENT_REVIEW_REPORT.md     review process, coverage, reject codes, systematic fixes
  DATA_PROVENANCE_AND_LICENSES.md  sources, teacher rights, base-model licences
  S1_TRAINING_MIXTURE_PLAN.md      rehearsal pool, 15% mixture, trainer requirements
  MODEL_RENDERING_VERIFICATION.md  chat template, masking, special-token handling
  WRITER_BRIEF.md / REVIEWER_BRIEF.md / NATIVE_REVIEWER_BRIEF.md   the instructions agents worked from
  data/
    TRAINING_CORPUS.jsonl          2,561 accepted common records (train 2,431 / validation 130)
    S1_NATIVE_REHEARSAL.jsonl      472 accepted S1-native rows
    QUARANTINE.jsonl               rejected common records with reasons
    HUMAN_SPOT_AUDIT_SAMPLE.jsonl  120 records for a human check
    RECORD_SCHEMA_P2B.json         JSON Schema for both files
    corpus_report.json, rehearsal_report.json
    batches/                       raw writer batches (W01–W15, stage s1 + s2)
    reviews/                       one verdict line per record (independent reviewers)
    native/                        native inputs, raw S1 outputs, autocheck, confirm queues, quarantine
    mixture/                       s1_schedule.jsonl, qwen_schedule.jsonl, mixture_stats.json
    rendered/                      pre-tokenised SFT inputs (input_ids + labels) per model
  scripts/
    run_all.sh                     rebuild everything + run tests (CPU, ~1 min)
    gen/                           reproducible generators (W01–W15, N01)
    p2b_kit.py                     record builder + validator (check FILE [--tok])
    build_corpus.py                reviews + checks -> corpus, split, quarantine
    s1_native_generate.py, run_s1_native.sh   authentic S1 GGUF outputs (CPU)
    build_rehearsal.py             native autocheck, reviews, confirmations -> rehearsal pool
    s1_mixture.py                  15% rehearsal schedule; identical common order for Qwen
    p2b_render.py                  model-specific SFT rendering + verification
    audit_stats.py                 machine-readable reports
  reports/                         corpus_distribution, review_coverage, leakage_checks, render_token_stats, rehearsal_stats, hashes
  tests/test_phase2b.py            17 tests
  logs/                            test runs, build logs, stage-1 review summary
```

Requires the sibling `../vf_phase2a/` folder (frozen held-out set, tokenizers, Phase 2A checks) and `src/voice_flow/` from the repo. Setup: `pip install pytest transformers tokenizers jinja2 jsonschema`.

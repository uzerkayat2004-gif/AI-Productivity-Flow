# Phase 2A Readiness Report

Date: Oct 12, 2026. Branch: `feat/vf1-universal-contract` (main untouched). No training, no weights downloaded, no inference.

## Verdict: **GO for Phase 2B** (data generation + smoke training), **not yet GO for full GPU training**

All six acceptance criteria are met. No known critical training-data defect remains. Full training should wait for the four conditions in §4, which are Phase 2B's first steps rather than blockers to starting it.

## 1. Acceptance criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Universal contract internally consistent | Met | `VF1_FINAL_MODEL_CONTRACT.md` rev 1.2; code enforces it (`vf_contract.validate`), 344 regression tests pass |
| 2 | Both tokenizers verified or blockers documented | Met | `TOKENIZER_VERIFICATION_REPORT.md`: 15 findings verified by 37 tests on both tokenizers; 3 minor items unresolved (GGUF runtime path, full lm_head compare, trainer collator) |
| 3 | Independent eval set frozen and protected | Met | 200 hand-written records, SHA-256 `e4243035…`, hash test, disjoint name/domain pools, 0 cross-split near duplicates |
| 4 | Pilot dataset passes schema and content review | Met, with caveat | 153 records, 0 schema errors, 0 validator problems, full manual reread; author = reviewer (independent review recommended) |
| 5 | S1/Qwen experiment plan reproducible and consistent | Met | `TRAINING_EXPERIMENT_PLAN.md`: A and B are explicitly one checkpoint deployed two ways; C uses the same recipe and VF-1 rows |
| 6 | No known critical training-data defects | Met | Hand-written S1-native targets were moved to a pending file instead of being trained on |

## 2. What changed in code (feature branch, reviewable)

| File | Change |
|---|---|
| `src/voice_flow/vf_contract.py` | rev 1.2: `auto` task experimental-only; `Length` same/shorter/longer; `Markup` plain/markdown; `Facts: correct` needs an instruction; cleanup/prompt format rules; escaping covers `<think>`, `<tool_call>`, `<tool_response>`; VF-1 casual maps to S1 `semi-formal` |
| `src/voice_flow/vf_checks.py` | number parsing rewritten (digit strings, ordinals, decimals, "and", shared scale, times); strong/weak self-correction cues; apology "sorry" protected; no summary ratio; invented sign-off and commitment checks |
| `tests/test_vf1_regressions.py` | updated to rev 1.2 (344 pass) |
| `research/vf_phase2a/**` | contract, reports, data, scripts, tests, logs (large tokenizer files excluded; fetch script included) |

No other production code was touched. Existing S1/polish/command suites: 261 passed, 4 failed — the same 4 fail on `main` in this environment (missing `llama_cpp`, settings API needing a real app context).

## 3. Discrepancies with earlier reports (corrected)

| Earlier claim | Actual | Source |
|---|---|---|
| S1-mini has an untied output head (Phase 1.1 schema §2a) | Tied in config; stored `lm_head` copy equals the embedding in all sampled windows | safetensors header + range reads |
| Train on the empty think block (Phase 1.1 schema) | It is part of the inference prompt; must be masked | template render |
| S1 and Qwen need separate rendering specs | Tokenizer files and template are byte-identical; one renderer suffices (tests still run both) | file hashes |
| VF-1 casual ↔ S1 `casual` (Phase 1.1 code) | S1 casual lowercases everything; wrong mapping | S1 README |
| `Task: auto` in VF-1 | Contradicted "transcript is data"; now experimental only | contract review |
| Summary compression check (≤ 80% length) | Forced factual loss; removed | contract review |
| Escaping covered all control tokens | `<think>`/tool tags were still parsed as tokens | tokenizer test |
| Fact checker number handling | Misread digit strings, ordinals, decimals, "nine and eleven", apologies | validation of references |

## 4. Before full GPU training (Phase 2B first steps)

1. **Regenerate the 8 S1-native rehearsal targets** (and the ~440 planned) from base S1-mini BF16 greedy output; validate; only then add to the S1 mix.
2. **Independent human review** of the 153 pilot rows and a 50-row held-out sample (Uzair or a reviewer who did not write them).
3. **Your decisions:** teacher model for generating the ~2,500 rows; whether Qwen may train on S1-derived outputs (licence/attribution); Colab go-ahead.
4. **Collator check** on the chosen trainer (labels equal `vf_render.build_example`), plus the 1-epoch pilot smoke run for both models.

## 5. Known limitations

- Pilot and held-out sets are small and single-author; phrasing diversity is limited. Real consented dictation should seed a second eval set.
- Assertions cannot judge tone, meaning shifts or prompt quality (DATASET_VALIDATION_REPORT §5).
- The fact checker is heuristic and was debugged on held-out references; it is frozen by hash now.
- No measurement of model behaviour, latency, RAM or quantised quality yet — all deferred to Phase 2B by the no-inference rule.
- `llama_cpp` was not available here; the GGUF/llama.cpp prompt path is unverified (TOKENIZER report U1).

## 6. Counts

| Item | Count |
|---|---|
| Held-out records | 200 (16 slices; 40 full-header) |
| Pilot training records | 153 (17 slices; 51 full-header) |
| Pending S1-native rows (not trainable) | 8 |
| Phase 2A tests | 64 passed |
| VF-1 regression tests | 344 passed |
| Existing S1/polish/command tests | 261 passed, 4 env-only failures (same on main) |
| Host-parse agreement on integration items | 14 / 14 |

## 7. Reproduce

```
bash research/vf_phase2a/scripts/fetch_tokenizers.sh   # tokenizer/config files at pinned revisions
cd research/vf_phase2a/scripts
python build_heldout.py && python build_pilot.py && python freeze.py
python validate.py && python host_agreement.py
cd .. && python -m pytest -q tests/
cd ../.. && python -m pytest -q tests/test_vf1_regressions.py
```

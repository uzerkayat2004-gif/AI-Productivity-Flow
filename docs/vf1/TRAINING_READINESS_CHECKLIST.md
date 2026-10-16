# Training Readiness Checklist (Phase 1 → LoRA pilots)

Status key: ☐ not started · ◐ in progress / designed · ☑ done. Owner: **U** = Uzair (or his coding agent), **H** = Hark.

## A. Decisions needed from Uzair (blockers)
| # | Decision | Recommendation | Status |
|---|---|---|---|
| A1 | Approve VF-1 contract (fields, vocabulary, system prompt, `auto` mode opt-in) | Approve, with any wording changes now (changes after data generation cost a rebuild) | ☐ U |
| A2 | Teacher for targets (cloud model, name and version) and its terms allow training a released model | Pick one main teacher + human review; check its ToS for "train competing models" | ☐ U |
| A3 | May Qwen train on S1-mini outputs? | Default no (S1 naming clause; unclear for a distilled student). S1 pilot may. | ☐ U |
| A4 | Release plan: license and name for the S1 variant | Must carry "S1-mini" by "Superwhisper" + LICENSE/NOTICE + Qwen attribution | ☐ U |
| A5 | Compute: his Colab Pro, GPU type, budget | T4/L4 is enough for r=16–32 on 0.6B | ☐ U |
| A6 | Which variant ships first (S1 adapter, S1 merged, Qwen) | Pilot S1 first, Qwen second (audits) | ◐ |

## B. Application fixes before data generation (from PIPELINE_AUDIT_AND_FIX_PLAN)
| # | Item | Status |
|---|---|---|
| B1 | F1 no-loss invariant (A1a/A1b empty content) | ☐ U |
| B2 | F3 register negation/comparatives ("less formal") | ☐ U |
| B3 | F8 reported speech | ☐ U |
| B4 | F2, F4–F7, F9–F11 parser vocabulary, constraints, multi-override, Slack/Teams, multi-wake, unsupported, persistent scope | ☐ U |
| B5 | F12 keep non-conflicting saved rules | ☐ U |
| B6 | F13 `vf_contract.py` serializer + escaping + native-eligibility (no behavior change) | ☐ U (Hark can draft) |
| B7 | F15 protected-fact checker + placeholder/subject/echo/script checks | ☐ U (Hark can draft) |
| B8 | All 30 probes in `defect_verification_head.json` added as tests and passing | ☐ U |

## C. Data
| # | Item | Status |
|---|---|---|
| C1 | `test_frozen` (~400 VF-1 rows) written and hashed **before** any training data; covers every slice, every field, `auto`, `edit`, rules, injection | ☐ H |
| C2 | Generator: scenario families → transcripts (with ASR noise: no punctuation, fillers, Indian-English) → canonical records | ☐ H |
| C3 | Targets: teacher + checker filter + human review per §5 of the schema | ☐ H+U |
| C4 | Renderers for S1 and Qwen with template assertions and special-token test | ☐ H |
| C5 | Pilot sets: S1 ≈ 2,650 rows, Qwen ≈ 2,550 rows (slice mixes in the two training specs, remapped to VF-1 slices) | ☐ H |
| C6 | No overlap with the 548-case investigation, the two micro-audits, or `test_frozen` | ☐ H |

## D. Training setup
| # | Item | Status |
|---|---|---|
| D1 | Download BF16 weights at pinned revisions: `Superwhisper` S1-mini, `Qwen/Qwen3-0.6B` | ☐ U (Colab) |
| D2 | Verify the downloaded S1 BF16 matches the shipped GGUF behavior (convert → Q4_K_M → run 30 native cleanup cases, identical or near-identical outputs) | ☐ |
| D3 | Notebook: TRL SFT + PEFT, assistant-only loss incl. EOS, LoRA all 7 projections; S1 r=16/α=32, Qwen r=32/α=64 | ☐ H |
| D4 | Checkpoint every ~0.5 epoch; evaluate dev + gates per checkpoint | ☐ |
| D5 | Export: merge → GGUF Q4_K_M (S1 tied re-export test ≈ 397 MB vs untied ≈ 484 MB); adapter GGUF for the S1-adapter variant | ☐ |

## E. Evaluation of the three deployment variants
Same frozen suites for all: native cleanup 297, command 211, prompt 40 (from the investigation), plus `test_frozen` VF-1 ~400. Greedy, repeat penalty 1.0, loop watchdog, 2 threads, Q4_K_M, plus BF16 for the number/language gates.

| Variant | How it runs | Extra checks |
|---|---|---|
| **V1 S1 original + command adapter** | Plain cleanup → base S1, native prompt, adapter scale 0. Everything else → adapter on, VF-1 prompt. | Cleanup must be **identical** to base S1 when the adapter is off; measure adapter load/toggle latency and RAM in llama.cpp (runtime adapter scaling is untested so far). |
| **V2 S1 merged** | One model for all; cleanup tested in both native and VF-1 `cleanup` formats | Native cleanup regression vs base S1 (no-P0/P1 ≥ 270/297, P0 ≤ 5, no category drop > 1). |
| **V3 Qwen fine-tuned** | One model, VF-1 only | Qwen-specific gates (Qwen spec): cleanup P0 ≤ 10/297, self-correction P0 ≤ 3/30, 0 negation reversals, language drift ≤ 1/60, prompt gen ≥ 36/40. |

Shared VF-1 gates (all variants):
- Held-out alternatives: 0 P0. Value corrections ≥ 95%. Negation corrections ≥ 95% with 0 reversals.
- Emails: 0 placeholders, 0 invented subjects, 0 loops in 200 greedy email generations.
- Commands: no-P0/P1 ≥ 70% overall, each task ≥ 50%; `edit` changes only the requested parts in ≥ 90%.
- `auto`: instruction detected and applied ≥ 85% at start/end; 0 executions of quoted/reported/mid-text instructions; unsupported instructions kept in text 100%.
- Injection/answer-bait: 0 answers/executions.
- Language: Hinglish kept, Devanagari script kept, 0 foreign-language drift.
- Artifact ≤ 500 MB (Q4_K_M), median latency ≤ 1.2 s for cleanup at 2 threads on the reference CPU.
- Q4_K_M within 1 point of BF16 on number and language gates.

Ranking rule: ship the variant that passes all gates with the best cleanup score; among equals, prefer V1 (base cleanup untouched) unless adapter switching costs > 150 ms or > 100 MB RAM.

## F. Known risks
1. Parser bugs baked into data if B1–B8 aren't fixed first.
2. Teacher bias (placeholders, verbosity) leaking into targets → checker + review.
3. `auto` mode is the hardest for 0.6B models; it may need its own pilot. Structured mode must not depend on it.
4. Over-literal outputs from heavy preservation data → keep tone/format slices strong and gate prompt quality.
5. Greedy non-determinism with prompt caching (A19) → evaluate with cache cleared or run twice.

## G. Go / no-go to start the pilots
Start when: A1–A5 decided, B1–B8 done, C1 locked, C3 filter passing on a 200-row sample with < 5% manual rejections, D1–D2 done.

---

## Phase 1.1 update (Oct 12, 2026)

- [x] VF-1 serializer in code with pinned tests (`vf_contract.py`)
- [x] Assistant identity is host config; model contract brand-free
- [x] Parser F1–F12 fixed with 337 regression tests; 0 new failures in the full suite
- [x] Data filter available (`vf_checks.check_output`)
- [x] S1 native prompt pinned; guard accepts valid cleanups (A16)
- [ ] Real tokenizer render checks (§2c) for S1-mini and Qwen3-0.6B
- [ ] Teacher, S1-output licensing, Colab decisions (Uzair)
- [ ] Review + approval to merge the branch

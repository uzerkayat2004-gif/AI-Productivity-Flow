# Training Experiment Plan — first controlled S1 / Qwen comparison

Status: plan only (Phase 2A). Nothing has been trained. Contract VF-1 rev 1.2.

## 1. Candidates

| ID | Base | Trained weights | Deployment | Native S1 cleanup |
|---|---|---|---|---|
| **A** | S1-mini (`superwhisper/s1-mini@88f6b15`) | adapter **S1-LoRA-1** | quantised base + LoRA applied at runtime **only for VF-1 requests** | served by the unmodified base, adapter off → identical to today |
| **B** | S1-mini | the **same** S1-LoRA-1 checkpoint, merged into the base, then quantised | one standalone model for both VF-1 and native prompts | served by the merged model → regression risk, measured |
| **C** | Qwen3-0.6B (`Qwen/Qwen3-0.6B@c1899de`) | adapter **QW-LoRA-1** (same recipe and VF-1 rows, no native rows) | merged + quantised standalone | not applicable |

A and B are **one training run** (S1-LoRA-1). They differ only in how the weights are served (runtime adapter vs merge) and therefore in quantisation effects. If B later needs a different data mix (e.g. more native rehearsal), that is a new checkpoint, S1-LoRA-2, and is reported separately.

Baselines (no training): **B0** base S1 native prompt (cleanup slices only), **B1** base S1 with VF-1 prompts, **B2** base Qwen3-0.6B with VF-1 prompts (non-thinking).

## 2. Data

| Set | Use | Size |
|---|---|---|
| VF-1 training rows (Phase 2B generator, hand-written pilot included) | A/B/C | ~2,500 rows, slices as in TRAINING_DATA_SCHEMA §4 |
| S1 native rehearsal rows (base S1 BF16 greedy outputs, checked by `vf_checks`) | S1-LoRA-1 only | 15% of the S1 mix (~440 rows) |
| VF-1 validation split (from training pools, not the held-out set) | early stopping / loss curves | 5% of VF-1 rows |
| Held-out evaluation (`HELDOUT_EVALUATION.jsonl`, 200) | final scoring only | frozen |
| Native regression set: 150 cleanup transcripts from the training pools + base S1 greedy outputs | A/B native check | built in Phase 2B |

Comparable coverage: A/B and C see the **same VF-1 rows** in the same order (seeded shuffle). S1 additionally sees native rehearsal rows; C does not (it has no native format to keep). Token budgets therefore differ by ~15%; this is reported, not hidden.

## 3. One shared recipe

| Item | Value |
|---|---|
| Method | LoRA, BF16 base, assistant-only loss (`vf_render.build_example`) |
| Rank / alpha / dropout | r = 16, α = 32, dropout 0.05 |
| Targets | q, k, v, o, gate, up, down projections; embeddings and lm_head frozen and tied |
| Optimiser | AdamW, lr 2e-4, cosine, 3% warmup, weight decay 0.0 |
| Batch | effective 32 sequences, max length 1,024, packing off |
| Epochs | 2 (stop early if validation loss rises two evals in a row; eval every 50 steps) |
| Seed | 3407 (data shuffle and init) |
| Prompt | system + VF-1 user via `apply_chat_template(..., enable_thinking=False)`; target + `<|im_end|>` |
| Hardware | Uzair's Colab Pro (L4 or A100), one run per candidate |
| Logged | library versions, data hashes, tool hashes, loss curves, checkpoint SHA-256 |

Step 0 (smoke test, before the full run, both models): train 1 epoch on the 153 pilot rows only. Pass = loss falls, the collator's labels equal `build_example` for 20 rows, generations end with `<|im_end|>`, no think block is generated. This checks plumbing, not quality.

## 4. Export and quantisation

- Merge (B, C) with the base in BF16, then export GGUF **tied** (no duplicate output tensor), quantise Q4_K_M and Q5_K_M with the same llama.cpp commit.
- A: base GGUF (Q4_K_M) + LoRA GGUF adapter via llama.cpp `--lora`.
- Every quantised model is scored on the full held-out set; the BF16 score is the reference.

## 5. Evaluation (held-out, greedy, identical settings)

Decoding: temperature 0, repeat penalty 1.0, `max_new_tokens = min(512, 3 × target tokens + 32)`, stop on 151645/151643, non-thinking prompt. Runtime: llama.cpp CPU, 4 threads.

| Area | Metric | Pass bar for "worth continuing" |
|---|---|---|
| Factual preservation | % of records with no `vf_checks` failure and no fact assertion failure | ≥ 95% overall; critical errors (changed/invented number, lost negation, reverted correction) ≤ 2% |
| Voice-command success | assertion pass rate on email, messages, prompt, nl_instruction, multi_constraint, followup_edit, summary, style_rules | ≥ 85% |
| Email and prompt quality | assertions + blind 1–5 human rating on 40 sampled outputs | mean ≥ 4.0; no placeholder, invented Subject, sign-off or promise |
| Cleanup regressions | held-out cleanup slices vs B0; native regression set agreement with base S1 | A: native path byte-identical to base (by construction, verified); B: ≥ 97% exact match and no new checker failures |
| Smart formatting | format assertion pass rate on smart_formatting + no_markdown | ≥ 90%; unrequested lists/Markdown ≤ 3% |
| Unsupported requests | not_answer / cleanup_only records | 100% no answer, no translation, no claimed action |
| Completeness | must_include pass rate; length ratio vs reference | ≥ 95%; no output < 50% of reference length outside summaries |
| Repetition / EOS | outputs hitting the token cap; any 4-gram repeated ≥ 3 times; missing end-of-turn | 0 cap hits, ≤ 1% loops, 0% missing EOS |
| Quantised quality | Q4_K_M and Q5_K_M vs BF16 pass rate | drop ≤ 2 points (Q4_K_M) |
| CPU latency | time to first token and total time for a 40-word cleanup and a 60-word email, p50/p95 over 20 runs, 4 threads on the same laptop; one ARM phone-class run if available | p50 ≤ 1.5 s for the 40-word cleanup on laptop |
| RAM | peak RSS during generation | ≤ 1.0 GB |
| Size | GGUF file size | ≤ 500 MB target, 600 MB hard limit (A: base + adapter sizes reported together) |

Reporting: per-slice pass rates with 95% Wilson intervals; every A/B/C difference smaller than the interval overlap is reported as "no measurable difference". The two base models are never called equivalent because they saw the same VF-1 rows; their native abilities and data budgets differ.

## 6. Decision rules after the first run

1. If C ≥ A on VF-1 slices by more than the interval and meets the size/latency bars → Qwen route is a serious option; still report A's native-cleanup advantage.
2. If A meets all bars → ship A first (lowest regression risk); B only if one-file deployment is required and its native agreement ≥ 97%.
3. If nobody meets the factual bar → fix data (error analysis on training-pool failures only, never on held-out items), then S1-LoRA-2 / QW-LoRA-2.

## 7. Reproducibility checklist

- [ ] Pinned model revisions (above) and tokenizer hashes (TOKENIZER_VERIFICATION_REPORT §2)
- [ ] `data/hashes.json` and `data/tool_hashes.json` recorded with each run
- [ ] Seeds, library versions (transformers, peft/trl or unsloth, llama.cpp commit) logged
- [ ] Training notebook + exact command lines committed to the feature branch
- [ ] Held-out scored once per checkpoint by `score_heldout.py` (to be written in Phase 2B; reads only the frozen file)

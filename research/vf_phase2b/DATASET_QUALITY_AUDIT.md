# Dataset quality audit — VF-1 Phase 2B

## 1. Baseline verified before any new work (Task 1)

| Item | Result |
|---|---|
| Branch / commit | `feat/vf1-universal-contract` @ `9f3cd15` (Phase 2A); `main` untouched |
| Contract | VF-1 rev 1.2 (`VF1_FINAL_MODEL_CONTRACT.md`, `src/voice_flow/vf_contract.py`); unchanged in 2B |
| Held-out set | 200 records, SHA-256 `e424303519a821739e693c607dda26b511609027f7f44d2a977f348bb0deaa7a` — identical to `vf_phase2a/data/hashes.json` before and after Phase 2B; never opened by writers or reviewers |
| Pilot set | 153 records, all re-validated (0 automatic problems); independently reviewed → 146 accepted, 7 rejected |
| Phase 2A tests / validator | 64/64 tests pass; `validate.py` 0 problems on held-out and pilot (re-run logs in `logs/`) |
| Packaging bug | `vf1_phase2a.zip` placed the two JSONLs at the zip root while `validate.py` reads `data/`. Phase 2B's zip keeps the repo layout (`vf_phase2a/data/...`) so every script runs unmodified from the unzipped folder |
| Latent renderer bug found | `split_special_tokens=True` does not split Qwen3's non-special added tokens: "a <think> b" still encodes `<think>` as id 151667. Phase 2A's renderer would have trained that id on any target containing the literal. Fixed in `p2b_render.safe_encode` (test `test_plain_split_special_tokens_leaks_think` documents it) |
| Held-out text exposure | One pilot reviewer printed the tail of `vf_phase2a/logs/host_agreement.log`, which contains a few held-out utterances (HE-185–194). It did not write training data. No writer saw held-out text; held-out near-duplicates were reported to writers by id/score only |

## 2. Record schema (Task 7)

`data/RECORD_SCHEMA_P2B.json` (extends Phase 2A). Every record has: `id`, `split`, `bucket` (task family), `slice`, `contract_revision`, `scenario_id`, `request` (all VF-1 fields incl. instruction, rules, draft, transcript), `target`, `assertions` (independent fact annotation: numbers, numbers_one_of, must_include, must_not_include, min_negations, format, max_words, behavior), `note` (facts that must survive; present on 2,372/2,561 — the rest have no at-risk facts), `meta` (command position, instruction complexity, length class), `provenance`, `review` (status, reviewer, heightened flags, checked facts). Corpus and rehearsal pass JSON-Schema validation with 0 errors.

## 3. Automatic checks (all must pass; any failure quarantines)

Implemented in `scripts/p2b_kit.py` (wrapping `vf_phase2a/scripts/dataset_checks.py` and `src/voice_flow/vf_checks.py`):

| Check | Implementation |
|---|---|
| Schema / contract validity | VF1Request + `vf_contract.validate` (rejects bad values, edit without draft, Facts: correct without instruction, illegal task/format pairs) |
| Malformed or empty output, whitespace, zero-width chars | `record_problems` + `zero_width_anywhere` |
| Task compatibility / format agreement | assertion format vs header format |
| Exact + near duplicates | normalised exact match; char-5-gram Jaccard ≥ 0.55 or word-trigram containment ≥ 0.6 (`fast_near_duplicates`, proven equal to the brute-force version by test) |
| Train/validation leakage, held-out overlap | 0.45/0.5 thresholds vs held-out; scenario grouping |
| Names, numbers, deadlines, negation preservation | `vf_checks.check_output` + per-record assertions |
| Invalid self-correction transformations | `correction_reverted`, `must_not_include` of corrected-away values |
| Chatbot replies / explanations | preamble + explanation regexes; `behavior: not_answer` assertions with forbidden answers |
| Unnecessary formatting / Markdown under plain | `format_problems`, `no_markdown` |
| Reserved held-out names and domains | `reserved_name:*`, `reserved_domain:*` |
| Invalid model serialisation | both tokenizers: 3 turns, non-thinking prompt, single trailing `<|im_end|>`, no added-token ids in labels, mask boundary, decode round-trip, length ≤ 1,024 |

Result on the final corpus: **0 automatic problems** on all 2,561 records with both tokenizers.

**Waivers.** 151 records waive one or more checker keys (number_missing 83, number_invented 71, negation_lost 26, invented_subject 17, correction_reverted 3, others 3). Each has a written reason in `note` and was re-verified by the reviewer (briefs required checking that the waiver is a real checker mistake). Typical causes: lakh/crore amounts, spoken digit strings ("four oh two"), "the twelfth sorry the fourteenth", ordinals, versions/IPs, Subject lines that the instruction requested.

Automated checks are necessary but not sufficient: every accepted record also has an independent content review (see `INDEPENDENT_REVIEW_REPORT.md`).

## 4. Coverage of the required capabilities (Tasks 3–6)

| Capability | Evidence in the accepted corpus |
|---|---|
| Natural multi-constraint commands | 736 records with `[Instruction]`; 597 with 2–4 simultaneous constraints; before/after/follow-up positions; e.g. "make this a professional email but keep it friendly, don't add any promises, and preserve the exact deadline" (W08) |
| Follow-up editing with supplied previous text | 94 `task: edit` records (`[Draft]` + instruction), incl. Facts: correct edits of exactly the named fact, byte-identical untouched paragraphs |
| Host owns activation | No record contains a wake phrase or assistant name; system prompt is brand-neutral; command-sounding sentences inside transcripts are kept as dictated text |
| Formatting | prose, paragraphs, bullets (69 explicit + auto), numbered (16 explicit + auto), notes (79), posts (25), emails (429), messages (424), markdown only on request (48), plain everywhere else |
| Literals | URLs, emails, paths, commands, versions, IPs, ticket/GST/PNR IDs, regex/SQL/cron (W04, W03, W05) |
| Factual preservation | 2,224 records with heightened facts: self-corrections (incl. corrections of corrections), genuine alternatives (2–3 options), ranges, hedges, conditionals, negations, requirements, Indian English + code-mixed speech (505 en-in) |
| Question boundary | 551 `not_answer` records: polished questions (cleanup/rewrite, context ai), prompts built from questions, and edit instructions that ask a question — never answered |
| Unsupported tasks | 56 records: translate / answer / send / schedule / search / delete / calculate / reply-for-me → writing part only, never claims an action |

## 5. Known limitations

1. **Header-field skew.** Most tone/length/register intent is expressed via `[Instruction]` rather than header fields: Tone header non-neutral on only 115 records, Length shorter 69 / longer 11, Register formal 149 / casual 110. The model will see these fields less often than instruction text.
2. **Synthetic speech.** All transcripts are written to look like ASR output; none are real ASR. Real-ASR error patterns (homophones, missing words, wrong casing of names) are under-represented.
3. **Small-count style varies** across writers (words vs digits for one–ten); both are contract-legal but the signal is mixed.
4. **Heightened flags over-fire** (keyword-based); reviewers did not rely on them.
5. **AI review only.** See the review report; a human spot audit is recommended before Phase 3 training starts.
6. **Summary compression is gentle** (W13 stage 2 averages ~0.85 of source length) because no fact may be dropped.

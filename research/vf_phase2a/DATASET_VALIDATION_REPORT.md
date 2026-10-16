# Dataset Validation Report — Phase 2A

Date: Oct 12, 2026. Validator: `scripts/dataset_checks.py` + `scripts/validate.py` (run log `logs/validate.log`, machine report `data/validation_report.json`). JSON Schema: `data/RECORD_SCHEMA.json`.

## 1. Results

| File | Records | Schema errors | Records with problems | Quarantined |
|---|---|---|---|---|
| `HELDOUT_EVALUATION.jsonl` | 200 | 0 | 0 | 0 |
| `PILOT_TRAINING_SAMPLE.jsonl` | 153 | 0 | 0 | 0 |
| `PILOT_S1_NATIVE_PENDING.jsonl` | 8 | 0 | 8 (by design: `not_reviewed`) | kept out of training |

| Split check | Result |
|---|---|
| Duplicate ids | 0 |
| Shared scenario ids eval↔pilot | 0 |
| Cross-split near duplicates | 0 |
| Within-set near duplicates | 0 / 0 |
| Pilot text using eval-reserved names | 0 |
| Host-integration parse agreement (hand-written expectation vs reference processor) | 14 / 14 |

Pilot composition: cleanup 59, rewrite 64, edit 11, summarize 10, prompt 9; 51 full headers (33%); 31 with `[Instruction]`, 10 with `[Rules]`, 11 with `[Sender]`; behaviours transform 130, not_answer 19, cleanup_only 4; mean 131 / max 240 tokens per sequence, 2,676 target tokens in total. All targets hand-written; no teacher model and no S1 output (`uses_s1_output: false` everywhere).

## 2. What is checked automatically

| Area | Check |
|---|---|
| Schema | JSON Schema + required keys, slice and behaviour enums, id/split labels |
| Contract | every request built and validated through `vf_contract.validate` (task/format combinations, edit needs draft + instruction, `Facts: correct` needs instruction, no experimental tasks) |
| Targets | non-empty; no leading/trailing or double spaces, no triple newlines; no control strings (`<|im_end|>`, `<think>`, `[Transcript]` …); no zero-width characters; no assistant preamble or explanation text |
| Language | non-Latin script appearing without a source in that script; Devanagari source losing its script |
| Facts | `vf_checks.check_output`: numbers kept/not invented (with spoken-number, ordinal, decimal, digit-string and price readings), self-corrections not reverted, negations kept, placeholders, invented Subject, invented sign-off name, invented commitments, summary not longer than source |
| Assertions | each record's own hand-written assertions run against its target (self-consistency) |
| Formatting | bullets/numbering well-formed and sequential, no list in prose/message/post/prompt/note, email starts with a greeting, no Markdown under plain, format agrees with the request (dictated lists in cleanup allowed) |
| End of turn | rendered with both tokenizers: trained span ends with exactly one `<|im_end|>`, 3 turns, no special ids inside the target, ≤ 1,024 tokens |
| Provenance | author, method, teacher, `uses_s1_output`, `reviewed: true` required |
| Contamination | char 5-gram Jaccard and word-trigram containment across and within splits; reserved-name scan; scenario ids |

## 3. Validator self-test (mutation tests)

`tests/test_dataset_validation.py` corrupts real records and requires a rejection. All pass: changed amount, dropped name, empty target, preamble, explanation text, Markdown, `<|im_end|>` and think block in the target, zero-width character, language switch, invalid task, experimental task, invalid task/format pair, missing provenance, unreviewed row, unknown slice, double space, invented sign-off, invented commitment, reverted correction, lost negation, near-duplicate paraphrase, malformed bullets, email without greeting.

## 4. Problems found and fixed during validation

Validation was not a formality: it found real defects in both data and tools.

| Found | Type | Fix |
|---|---|---|
| HE "clinic is closed" asserted a negation that is not there | data | assertion removed |
| 3 held-out host items reused one scenario ("the boiler is fixed") | data | 2 rewritten |
| 3 pilot items near-duplicated eval items (same template) | contamination | rewritten with new scenarios |
| "You left the shop unlocked" softened into a passive that drops who did it | data (manual review) | target restored to keep the subject |
| VF-1 casual mapped to S1 `casual` (all lowercase) | contract | maps to `semi-formal`, as the app does |
| Spoken "Kofi forty… forty five" given a `$` nobody said | data | symbol removed |
| Hand-written S1-native targets guessed S1's own style | data | moved to a pending file; must come from base S1 greedy output |
| Checker read "four four seven one" as 4, 4, 7, 1; "twenty third" as 20; "three point five" as 3, 5; "nine and eleven" as 20; "two one" as 3 | tool | number segmentation rewritten |
| Checker treated "I'm sorry", "we're sorry", "can't make it, sorry", "said no for now" as corrections | tool | weak cues need a repeated word or same-kind value |
| "Please note:" flagged as explanation; "(I've corrected…)" missed | tool | explanation pattern fixed |
| `<think>`, `<tool_call>` in user text became control tokens | renderer | escaping extended |

Disclosure: the fact checker was corrected using the held-out references. That shapes the scorer, not any model or training target; it is now frozen by hash (`data/tool_hashes.json`).

## 5. What automatic checks cannot establish (manual review required)

1. **Meaning equivalence.** A rewrite can keep every number and name and still change who did what, a tense, a hedge ("should arrive" → "will arrive") or emphasis. Only partly caught by assertions.
2. **Tone and register quality.** Whether "friendly" sounds friendly or "formal" is natural.
3. **Correct correction scope.** Which words a "no wait" replaces in unusual phrasings; the checker's rules are conservative heuristics.
4. **Implied commitments.** Paraphrased promises ("count on us") slip past the pattern list.
5. **Summary completeness beyond numbers and listed items.** A dropped condition without an "if/unless" word is invisible.
6. **Prompt quality.** Whether a generated prompt states goal, inputs and constraints well.
7. **Instruction compliance for free text.** "Make it less blunt", "address the whole shift".
8. **Formatting judgement under `Format: auto`.** When a list helps.
9. **Cultural/locale conventions** (₹ lakh grouping vs international, en-gb spelling) beyond the specific assertions.

Policy: every training record needs `reviewed: true` from a human (or a second reviewer pass for teacher rows) before it enters a training mix. Teacher-generated rows in Phase 2B: automatic validation → 100% human review for the first 300, then a 20% random audit per batch; any audit failure rate above 5% sends the whole batch back.

## 6. Manual review performed

All 200 held-out and 153 pilot targets were reread line by line after building (listings in this session's logs). Corrections from that pass are in §4. Reviewer and author are the same (Hark), which is a limitation: an independent human pass (Uzair or a contractor) on at least the 153 pilot rows and a 50-row eval sample is recommended before Phase 2B training starts.

# Held-out Evaluation Set — Manifest (frozen)

File: `data/HELDOUT_EVALUATION.jsonl` — **200 records**, contract VF-1 rev 1.2.
SHA-256: `e424303519a821739e693c607dda26b511609027f7f44d2a977f348bb0deaa7a`
Frozen: Oct 12, 2026. Any edit changes the hash; `tests/test_dataset_validation.py::test_frozen_files_match_manifest_hashes` fails until this manifest is updated with a written reason.

## 1. Rules of use

1. Never used as training data, as few-shot examples in teacher prompts, or for tuning prompts, sampling or data mixes.
2. Scored only at fixed checkpoints listed in TRAINING_EXPERIMENT_PLAN.md. Results are recorded, never used to edit training data item by item.
3. The training generator must not see this file. Phase 2B generators get only the training scenario pools below.
4. If an item is found wrong, it is fixed here with a changelog line and new hash; the fix never informs training targets.

## 2. Generation method

- Hand-written by Hark from the VF-1 rev 1.2 contract (scripts `heldout_part1.py`–`heldout_part3.py`, built by `build_heldout.py`). No model, teacher or parser produced any target or assertion.
- Each record has one reference target (for similarity scoring) and **independent assertions** written separately from the target: `must_include`, `must_include_one_of`, `must_not_include`, `numbers`, `numbers_one_of`, `min_negations`, `ends_with_question`, `format`, `max_words`, `no_markdown`, `behavior` (`transform` / `not_answer` / `cleanup_only`).
- Host-integration items also carry the hand-written expected parse (`host.expected`); the parser is measured against it (14/14 agree today, `logs/host_agreement.log`), never the reverse.
- 40 records (every 5th) use the full header so header robustness is measured.

## 3. Contamination controls

| Control | Status |
|---|---|
| Reserved scenario pools | Eval names: Priya, Rahul, Meera, Arjun, Sofia, Daniel, Fatima, Kenji, Lucas, Aisha, Grace, Tariq, Ines, Wei, Nadia, Ravi, Hannah, Diego. Eval domains: dental clinic, bakery, freight, school, real estate, hospital, cafe, wedding, plumbing, library. Training uses disjoint pools |
| Pilot words matching eval-reserved names | 0 |
| Shared scenario ids | 0 |
| Cross-split near duplicates (char 5-gram Jaccard ≥ 0.45 or word-trigram containment ≥ 0.5) | 0 (3 found and rewritten in the pilot during validation) |
| Within-eval near duplicates (Jaccard ≥ 0.55 or containment ≥ 0.6) | 0 (2 rewritten) |
| Phase 2B generator | Must run the same cross-split check against this file before any batch is accepted |

## 4. Composition

| Slice | Count | Covers |
|---|---|---|
| cleanup_ordinary | 22 | everyday dictation, 2 long-form (60–90 words) |
| facts_numbers_negation | 18 | names, dates, times, money (₹ lakh, $, £), IDs, emails, negation |
| corrections_vs_alternatives | 16 | strong and weak correction cues vs genuine "or" |
| email | 17 | greetings, sign-off with/without sender, dictated Subject, no invented promises |
| messages | 12 | work and personal chat |
| prompt | 10 | prompt building, never answering |
| question_no_answer | 10 | questions polished, never answered |
| nl_instruction | 12 | natural-language `[Instruction]` |
| multi_constraint | 11 | several fields + instruction at once |
| followup_edit | 13 | `Task: edit`, incl. 2 `Facts: correct` and 1 non-edit question |
| summary | 11 | no fixed ratio; owners, conditions, numbers kept |
| smart_formatting | 12 | spoken punctuation, auto lists only with cues |
| no_markdown | 8 | no bullets/bold when not asked |
| style_rules | 10 | `[Rules]` and the instruction-beats-rule case |
| unsupported_boundary | 8 | translate/answer/send/search/delete; commands inside the transcript |
| host_integration | 10 | unseen assistant names (Nova, Pip, Atlas, Sage, Juno, Echo, Lumen), company-name and quoted false triggers, dictation mode |

Tasks: cleanup 83, rewrite 82, edit 13, summarize 12, prompt 10. Behaviours: transform 169, not_answer 24, cleanup_only 7. Lengths: mean 126 / max 315 tokens per sequence.

## 5. Scoring

Primary (per record, pass/fail): all assertions pass **and** `vf_checks.check_output` reports no failure (with the record's `checker_waivers`, none in this file). Secondary: chrF against the reference, length ratio, format accuracy. Reported per slice and overall, with the 95% Wilson interval. A model is never ranked on the secondary metrics alone.

## 6. Known limitations

- 200 items give roughly ±7 points of uncertainty on an overall rate; slice-level rates (8–22 items) are indicative only.
- One author wrote every item: phrasing style is narrower than real users. Real dictation logs (with consent) should add a second held-out set later.
- Cleanup references follow one convention for discourse fillers; assertions deliberately do not test them.
- The fact checker was debugged while validating these references (digit strings, ordinals, decimals, weak correction cues). It is frozen now (`data/tool_hashes.json`); further checker changes must be justified on training data, not by re-scoring this set.
- Spoken-price ambiguity ("nine ninety nine") is avoided in eval; it is covered by unit tests instead.

## 7. Files and hashes

| File | SHA-256 |
|---|---|
| `data/HELDOUT_EVALUATION.jsonl` | `e424303519a821739e693c607dda26b511609027f7f44d2a977f348bb0deaa7a` |
| `src/voice_flow/vf_contract.py` (renderer) | `77134454e5dffadefb8c21252c20d9d59fb333fd34ce13ddcd1b390132feb761` |
| `src/voice_flow/vf_checks.py` (fact checker) | `56a419029ab96011aea866da15876fc687b7d0d3a905c399673f1ee4414ff81b` |
| `scripts/dataset_checks.py` (validator) | `765cc82cf383c3b7d573e951775f8227fccbf8a4314aa0411fdfb5f8a80f13bd` |
| `scripts/vf_render.py` (model rendering) | `1349ad4b02f030a1b0242f8a4274fb542bed80c5a3cc3d0f1b00777b68c1f3d4` |

Changelog: v1.0 (Oct 12, 2026) initial freeze.

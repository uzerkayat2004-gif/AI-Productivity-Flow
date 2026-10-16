# Independent review report — VF-1 Phase 2B

## Who reviewed, and how independent it was

- **Writers** (15 Hark sub-agents, W01–W15, plus N01 for native inputs) produced records from `WRITER_BRIEF.md`.
- **Reviewers** were separate Hark sub-agents with their own context. They read only `REVIEWER_BRIEF.md` (or `NATIVE_REVIEWER_BRIEF.md`) and the contract; they were told not to read the writer brief or generator scripts, and judged each target against its request before reading the writer's note. No reviewer reviewed a batch it wrote.
- **Limitation (stated plainly):** reviewers are AI agents, likely from the same model family as the writers. That makes the review independent in context, not independent in kind. **No human has reviewed the corpus yet.** A 120-record stratified sample for a human spot audit is in `data/HUMAN_SPOT_AUDIT_SAMPLE.jsonl` (100 common records with heightened facts + 20 rehearsal rows).

## Coverage

Every candidate record received exactly one verdict line (`data/reviews/*_review.jsonl`); unreviewed records cannot enter the corpus (`build_corpus.py` quarantines them).

| Set | Reviewed | Accepted | Rejected | Reject rate |
|---|---:|---:|---:|---:|
| Phase 2A pilot | 153 | 146 | 7 | 4.6% |
| Stage 1 writer batches (W01–W15) | 600 | 569 | 31 | 5.2% |
| Stage 2 writer batches (W01–W15) | 1,908 | 1,849 | 59 | 3.1% |
| **Common total** | **2,661** | **2,564** | **97** | **3.6%** |
| S1-native first review | 480 | 299 verbatim + 176 corrected | 5 | 1.0% |
| S1-native correction confirmations (second reviewer) | 134 | 124 | 10 | — |

3 accepted common records were later dropped as cross-batch near-duplicates, giving 2,561.

Heightened review: 2,224 of 2,561 accepted records carry at least one heightened flag (negation, self-correction, commitment, quantity, date, conditional). Reviewers were instructed to list each such fact and tick it off (`checked` field). Note: the flags are keyword-based and over-fire (reviewers repeatedly reported spurious `self_correction` tags); they route attention but do not define correctness.

## Rejection codes (common + native first review)

F8 cleanup rephrased/meaning words dropped 90 · F1 fact changed/dropped/invented 68 · F2 negation/hedge/condition/requirement weakened 32 · F7 formatting 31 · F3 correction/alternative 21 · F6 instruction not followed 20 · F13 annotation wrong 20 · F4 invented greeting/commitment/feeling 17 · F5 answered/invented info 13 · F9 summary dropped item 9 · F12 ambiguous transcript 7 · F10 prompt added requirement 5 · F11 unsupported handled wrong 2. (Native F-codes are included; most native F8/F1 were later corrected rather than rejected.)

## Systematic problems found, and what was done

Staged batches worked as intended: stage-1 review found patterns, which became binding policy for stage-2 writers and reviewers (both briefs' "Policy clarifications" sections). Stage-2 reject rate fell from 5.2% to 3.1%.

| Pattern found | Where | Fix applied |
|---|---|---|
| Tone instructions ignored (target = plain cleanup) | W03, W05, W10 | Style instructions must visibly change text |
| Tone used as licence to add greetings, "!", feelings ("I'm glad to let you know", "Guess what", "two whole years") | Pilot, W07, W10, W12 | Tone changes wording only; emotion claims = F4/F5 |
| Directives softened into favours under "polite"/"warm" | W07, W08, W14, W15 | Directive → "Please …", never an optional question |
| Fact-hedges dropped under "more direct"/"shorter" ("kind of", "to me", "I think") | W02, W06, W09 | Hedges about facts survive; only request-softeners may go |
| Framing/lead-in dropped ("for the conference trip", summary opening context) | W04, W11, W12, W13 | Framing is content; summaries keep when/what/who |
| Unconditional rule merged into an "If…" sentence | W01, W02 | Standing rules keep their own sentence |
| Greeting conventions inconsistent (Dear vs Hi; vocatives) | W07–W10 | Register-based greeting policy; vocative only if the speaker named the person |
| Hinglish translated under "English only" | W03 | Never translate (§5) |
| Invented identifier formats (`applied_on`, `YYYYMMDD`) | W05 | Join words only if "underscore" was spoken |
| Currency symbol carried to unspoken amounts | W04, W06, W12 | Symbol only where the currency was spoken for that list |
| Checker gaps tempted writers to distort transcripts | W03, W05, W08 | Waive the failing check with a note; never make speech unnatural |

## Open policy calls (decided provisionally; Uzair should confirm)

1. "tell X …" under rewrite-to-message may become a message addressed to X ("X, …"); under cleanup it stays as dictated.
2. Unsupported verse requests ("make it rhyme") are treated as unsupported → plain cleanup/plain format.
3. A leading "So"/"Okay, so" is kept in S1 rehearsal targets (S1-mini's model card examples keep it) but removed as a filler in VF-1 cleanup targets (contract §4). The two paths therefore differ deliberately.

## What review cannot establish

Reviewers can miss errors; a 3.6% reject rate after automatic checks is plausible but not proof of zero errors. The automatic fact checker has known gaps (lakh amounts, spoken digit strings, "the X sorry the Y", ordinals, subject lines requested in the instruction) that produced 151 waived checks, each with a written justification. A human spot audit is the recommended next control.

# Human audit checklist — 120-record spot sample

**Status: NOT STARTED.** No human has reviewed these records. Every review so far was done by AI agents (Hark sub-agents with separate context). Those reviews are evidence, not human approval.

Files: `audit/HUMAN_AUDIT_SHEET.md` (easy to read, one record per section) and `audit/HUMAN_AUDIT_SHEET.csv` (fill `verdict`, `error_type`, `comment`). When done, fill `audit/HUMAN_AUDIT_STATUS.json` with your name, the date and the counts, then set `human_audit_approved` in `gates.json`.

Sample: 100 common records with at-risk facts (cleanup 25, prompt 16, email 14, messages 14, formatting 10, summary 8, follow-up/style 8, unsupported 5) + 20 S1 rehearsal rows (10 kept as-is, 10 corrected). Fixed seed, drawn in Phase 2B.

## For each record, compare the Target with the Transcript (and Draft/Instruction)

1. **Facts.** Every name, recipient, number, amount, unit, date, time and deadline is the same. Nothing new was added.
2. **Names.** Spelled as spoken. The right person is addressed. Nobody is greeted who wasn't named.
3. **Negation.** Every "not / don't / never / no / without" survives with the same meaning.
4. **Hedging.** "might / maybe / probably / I think / about / like (≈)" stays. Nothing becomes more certain or less certain.
5. **Conditions.** "if / unless / only if" still cover the same thing. No standing rule became conditional.
6. **Commitments.** No new promise, apology, offer, deadline, "let me know", or sign-off name. Directives aren't softened into favours.
7. **Corrections vs alternatives.** "X no wait Y" → only Y. "X or Y" → both stay.
8. **Instruction compliance.** Every part of the instruction is done (tone, length, format, word limit, "keep my wording"). The rest is untouched.
9. **Tone.** Tone changes wording only. No invented feelings ("I'm glad to let you know"), no added "!" or emoji.
10. **Format.** Bullets or numbers only when asked or clearly listed; no Markdown unless markdown was requested.
11. **Boundaries.** Questions are polished, never answered. Prompts add no requirements. Unsupported requests (translate, send, schedule) aren't carried out or claimed.
12. **Language.** Hindi/Hinglish words kept, never translated.

## Verdicts
- **PASS**: correct.
- **FAIL-CRITICAL**: a fact, name, number, negation, hedge, condition, correction or commitment is wrong. This record gets quarantined.
- **FAIL-MINOR**: style only (punctuation, a word choice) with meaning intact.
- **UNSURE**: say why.

**Decision rule:** 0–2 critical fails → approve the gate. 3 or more → stop, and the affected bucket gets a fresh review before any training.

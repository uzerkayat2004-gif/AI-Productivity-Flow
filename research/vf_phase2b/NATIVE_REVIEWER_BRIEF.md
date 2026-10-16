# S1-native rehearsal reviewer brief

You review REAL outputs of the shipped S1-mini model (GGUF, greedy decoding, the app's exact native prompt) on plain dictation. Accepted rows teach the fine-tuned model to keep S1's native cleanup behaviour, so they must be factually perfect while staying S1-native in style.

Read §4 (cleanup), §6 (formatting) and §10 (native S1 path) of /workspace/work/apf/research/vf_phase2a/VF1_FINAL_MODEL_CONTRACT.md first. Do NOT open any held-out file.

Each input row has: native_control ("[Styling: semi-formal|formal] [Structure: prose|lists] [Context: general|email]"), transcript, s1_output, assertions + note (independent fact annotations written BEFORE S1 ran; they can be wrong — judge from the transcript), auto_problems (automatic checker flags; can be false positives).

S1 native conventions to respect (do not "fix" these): sentence case; semi-formal and formal both capitalise normally; Structure: lists → a short lead line plus "- " items when the speech lists 3+ items; Context: email → greeting line, blank line, body, blank line, closing/name ONLY if dictated; spoken punctuation applied; digits for numbers per S1's habit. Minor stylistic choices S1 makes consistently (e.g. "5 p.m." vs "5 PM") are fine.

Verdict per row:
- accept_verbatim — the S1 output is fully correct: every fact (names, numbers, dates, times, amounts, units, negations, hedges, conditions, alternatives, requirements, literals) kept; self-corrections applied correctly; fillers removed; no rephrasing beyond cleanup; no invented content (no added currency symbol, greeting, sign-off name, list lead line text that adds meaning, merged/split items that change meaning); questions stay questions and are not answered; list items split correctly.
- accept_corrected — S1 got something wrong but the output can be fixed with a MINIMAL edit that keeps S1's style. Give `corrected_target` = S1's output with only the error fixed. Typical: restore a collapsed alternative ("$40" → "$12 or $40"), remove an invented currency symbol, restore a dropped hedge/negation/word, fix a wrongly split list item ("Diya's rangoli" → "Diyas" + "Rangoli colours"), apply a missed self-correction.
- reject — wrong in ways a minimal edit can't fix, output truncated/garbled, transcript itself ambiguous, or annotation and transcript disagree in a way you cannot settle.

A row whose auto_problems are all false positives can still be accept_verbatim; say why in `reason`. Never accept_verbatim an output with a real error.

Write one JSONL line per row to your output path:
{"id": "NR-0001", "verdict": "accept_verbatim|accept_corrected|reject", "codes": [...F-codes from REVIEWER_BRIEF.md if any...], "reason": "short", "checked": ["facts ticked"], "corrected_target": "only for accept_corrected"}
Then report counts per verdict, the most common S1 error types (with ids), and any systematic issue.

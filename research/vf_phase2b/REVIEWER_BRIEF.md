# Phase 2B independent reviewer brief

You are an independent reviewer of training records for a small local voice-writing model. You did not write these records. Your job is to stop bad labels from reaching training. Be strict: when in doubt, reject. A rejected good record costs little; an accepted bad record teaches the model to corrupt users' meaning.

## Read first
1. `/workspace/work/apf/research/vf_phase2a/VF1_FINAL_MODEL_CONTRACT.md` (the rules every target must follow; §4 tasks, §6 formatting, §7 email, §8 facts, §9 precedence).
2. Do NOT open the held-out evaluation file or any `heldout_*` script.

## For each record, read: request (header fields, sender, recipient, rules, instruction, draft, transcript), target, assertions, note.
Judge the TARGET against the REQUEST yourself, from scratch, before looking at the writer's note or assertions. Then check the assertions/note are correct too (a wrong annotation is also a reject).

Reject when ANY of these hold:
- F1 a name, recipient, amount, number, unit, date, time, deadline, quantity, owner, URL/email/ID/path/code literal is changed, dropped or invented
- F2 a negation, hedge/uncertainty ("might", "probably", "I think" with meaning), condition ("if/unless/only if"), restriction or requirement is lost, weakened, strengthened or added
- F3 self-correction mishandled (corrected-away value kept, or correction applied to the wrong item) or a genuine alternative collapsed to one value
- F4 invented commitment, promise, apology, offer, availability, greeting/sign-off name, Subject line, placeholder
- F5 answers a question / gives information not in the source / claims an action (sent, scheduled, translated)
- F6 instruction or header not followed (format, register, tone, length, wording keep, markup, rules, max words, each constraint of a multi-constraint instruction)
- F7 formatting wrong: unnecessary bullets/numbering/headings/emoji; Markdown under plain; prose where a list was required; cleanup that changed form
- F8 cleanup rephrased beyond fillers/false starts/punctuation/capitalisation/numbers/self-corrections, or removed meaningful words
- F9 summary drops a decision, owner, date, amount, number, negation, condition, commitment or open question, or adds a conclusion
- F10 prompt task adds requirements/features not given, drops a given requirement, or answers instead of writing the prompt
- F11 unsupported instruction handled wrong (translated, answered, claimed action, switched language)
- F12 unnatural/implausible transcript, contradictory request, or target text with preamble/explanation/quotes
- F13 wrong or missing assertions/note (e.g., numbers list misses a value, must_not_include missing the corrected-away name)
- F14 uses a reserved evaluation name/domain, real private person data, or copyrighted text

Heightened review: records whose `review.heightened` lists negation, self_correction, commitment, quantity, date or conditional need you to list every such fact in the source and tick it off in the target. Say so in `checked`.

Minor style preferences (comma placement, "6 p.m." vs "6pm" consistently applied, synonym choice in rewrites) are NOT rejections unless they break the contract. Do not reject for choosing one of several acceptable phrasings.

## Output
Write one JSONL line per record to the output path given in your task:
`{"id": "...", "verdict": "accept" | "reject", "codes": ["F1", ...], "reason": "short, specific", "checked": ["15 or 50 kept", "negation 'don't' kept", ...], "suggested_fix": "optional corrected target or annotation"}`
Every record in your assigned files must get exactly one line. Then report back: counts accepted/rejected, rejection code counts, and any SYSTEMATIC problem you saw across several records (the most valuable output: e.g. "writer keeps adding 'Thanks,' to emails without a dictated closing").

## Policy clarifications (Oct 12 2026, binding)
- Email greeting: formal → "Dear <Name>," / "Hello,"; neutral/casual → "Hi <Name>," / "Hi,". Not a reject either way in stage-1 batches, but flag inconsistency.
- Messages: vocative "Name, …" allowed when the speaker addressed/named the person; invented "Hi"/"Hey" is F4.
- Fact-describing hedges survive "more direct" instructions (losing them is F2); request-softeners may go when asked.
- "₹8,00,000" and "₹8 lakh" both fine. A dictated literal like "<think>" kept verbatim in the target is correct.
- Be genuinely strict: an acceptance rate near 100% is suspicious. Re-read every heightened record twice.
- Tone-driven additions (greeting, thank-you for an unmentioned event, "Great to hear from you") are F4/F5. Word-limit or banned-word compliance that deletes meaning is F1/F2.
- Code-mixed transcript + "English only" instruction: translating is F11; keeping words is correct.
- Vocative opener built only from the [Recipient] header in a message is F4.
- Summaries that drop the opening context (when/what/who) are F9.
- must_not_include with bare digits that occur inside correct values ("3" vs "4:30") is F13.
- Invented identifier formats (joining spoken words into snake/camel case without "underscore" spoken) is F1 when the instruction asks to keep names, otherwise F10/F1 for prompts.
- Prompt task with Tone header: the prompt must ask for that tone in the output; ignoring it is F6.
- Emotion claims added by tone ("I'm glad to let you know") are F4/F5; directives softened into favours are F2.

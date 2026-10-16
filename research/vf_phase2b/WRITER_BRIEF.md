# Phase 2B writer brief (VF-1 rev 1.2 training records)

You are writing supervised training records for a small local "voice-writing" model (Qwen3-0.6B class). The model receives a header + optional fields + a dictated transcript and must output ONLY the finished text. Quality beats count: every record you submit will be machine-checked and then read line by line by a separate reviewer. Records with a single factual error are rejected and do not count.

## Read first (required)
1. `/workspace/work/apf/research/vf_phase2a/VF1_FINAL_MODEL_CONTRACT.md` — the contract. Sections 3–9 decide every target.
2. About 30 lines of `/workspace/work/apf/research/vf_phase2a/data/PILOT_TRAINING_SAMPLE.jsonl` — format and number conventions.
3. `/workspace/work/apf/research/vf_phase2b/scripts/p2b_kit.py` — `rec()`, `save()`, `check`.

NEVER open `research/vf_phase2a/data/HELDOUT_EVALUATION.jsonl`, `heldout_part*.py`, or any held-out file. It is a frozen evaluation set; seeing it contaminates the experiment.

## Forbidden names and domains (reserved for evaluation)
Names: Priya Rahul Meera Arjun Sofia Daniel Fatima Kenji Lucas Aisha Grace Tariq Ines Wei Nadia Ravi Hannah Diego.
Domains: dental clinic, bakery, freight/logistics, school/PTA, real estate, hospital shifts, cafe, wedding planning, plumbing, public library. The checker flags these words.
Use only the names and domains in your assignment (plus generic ones). No real private people, no real customer data, no copyrighted text (no song lyrics, book passages, news articles). Public company/product names (Slack, Jira, GitHub, Excel, Zoom) are fine as tools.

## How to work
- Write a Python generator at `research/vf_phase2b/scripts/gen/<WID>.py` that imports `p2b_kit` (sys.path insert the scripts dir), builds records with `rec(...)`, and saves to `research/vf_phase2b/data/batches/<WID>_<stage>.jsonl`. The script is a deliverable: it must reproduce the file exactly when re-run.
- Run `cd research/vf_phase2b/scripts && python3 p2b_kit.py check ../data/batches/<WID>_<stage>.jsonl` until it shows **0 problems, 0 exact dups, 0 near dups (within, vs held-out, vs pilot)**. If a near-dup with held-out appears, rewrite or delete that record (you'll only see ids; do not look them up).
- Then run once with `--tok` (tokenizer render check, slower) and fix anything.
- IDs: `TC-<WID>-<NNN>` where WID is your writer id (e.g. `TC-W03-017`). Scenario ids: `<wid>-sc-<NNN>`, unique per real scenario.
- `author="<WID>"`. Leave `method` default.

## Record fields
`rec(id, bucket, slice, request, target, assertions, scenario_id, author=..., note=..., waivers=..., meta=...)`
- `request`: only non-default VF1Request fields: task, format, register, tone, length, wording, markup, context, facts, locale, sender, recipient, rules (list of strings), instruction, draft, transcript, header_style ("full" on ~30% of records).
- `target`: the exact ideal output. No preamble ("Sure", "Here's"), no explanation, no quotes around it, no trailing whitespace.
- `assertions` (independent fact annotation — write these from the TRANSCRIPT, not from your target):
  - `numbers`: every number literal that must appear in the target as written there ("6:15", "4,500", "23").
  - `numbers_one_of`: acceptable alternates when a value can be written several ways.
  - `must_include`: names, recipients, key terms, protected literals (URLs, emails, IDs, file paths, code) — verbatim.
  - `must_not_include`: values the speaker corrected away (the "no wait" name), answers a question must not contain, forbidden additions.
  - `min_negations`: count of negations that must survive.
  - `format`: prose / bullets / numbered / email / message / post / prompt / note when the output form matters.
  - `max_words` when the instruction sets a length.
  - `behavior`: "transform" (default), "not_answer" (question/prompt: must not answer), "cleanup_only" (unsupported request: do only the writing part).
- `meta`: `{"command_position": "structured"|"before"|"after"|"followup", "instruction_complexity": 0-4 (number of simultaneous constraints), "length_class": "short"|"medium"|"long"}`. "before"/"after" = the user spoke the command before/after the dictation; the HOST already removed it from the transcript, so the transcript never contains the command. The model only sees header fields + `[Instruction]`.
- `note`: REQUIRED on any record with negation, self-correction, commitment, quantities, dates, conditionals/hedges or alternatives: one line stating the facts the target must keep ("facts: 15 OR 50 units both kept; Friday is hedged 'might'"). This is what the reviewer checks against.
- `waivers`: use when the automatic fact checker is provably wrong for this record (known gaps: '₹3 lakh' read as 3 and 100000; 'two lakh fifty' as 200,050; 'the twelfth sorry the fourteenth' correction not applied when 'the' follows 'sorry'; a bare 'one' in 'one more thing' counted as a number; 'point two' read as 2; a Subject line asked for in the instruction flagged as invented_subject). Waive only the failing key (e.g. `number_missing`) and explain in `note`. NEVER make a transcript less natural just to satisfy the checker: natural speech is what the model must learn. Writing lakh amounts as full grouped digits (₹4,20,000) is fine and preferred.

## Target conventions (match the pilot)
- Digits for amounts, times, dates, measurements and numbers over ten; one–ten in words are fine when not a measurement/amount/time. Times "5 p.m.", "7:30 a.m.", "6:15". Dates "the 23rd", "March 4". Currency symbol only if the currency was spoken ("ninety nine dollars" -> "$99"); en-in uses ₹ and lakh/crore grouping when spoken ("₹3,00,000" or "₹3 lakh").
- Self-corrections are APPLIED ("send it to Kabir no wait Tanvi" -> Tanvi only; the corrected-away value goes in must_not_include). Genuine alternatives keep BOTH values ("15 or 50 units").
- Hedges stay hedges ("might", "probably", "I think" when it carries meaning). Conditions stay conditions ("if the client approves"). Negations stay. Requirements and restrictions stay.
- Cleanup keeps the speaker's words: only fillers, false starts, stutters, punctuation, capitalisation, number formatting and self-corrections change. Never rephrase in cleanup.
- Rewrite/email/message/summary/prompt may rephrase but never add facts, names, dates, amounts, promises, apologies, offers, availability, Subject lines or sign-off names that were not given.
- Emails: "Hi <Recipient>," when recipient given/named, else "Hi," (formal: "Hello," or "Dear <Name>,"). Sign-off only with [Sender] (closing + exact name) or a dictated closing word. Never placeholders.
- Messages: no greeting/sign-off unless dictated.
- Formatting: prose by default; bullets only for format bullets or auto + 3+ parallel items with a list cue; numbered only for numbered or explicit order cues. Markup plain = no `**`, `#`, backticks, tables; lists use "- " and "1. ". Markup markdown = emphasis/headings only where the format/instruction calls for them. No emoji unless dictated/instructed. Explicit format requests beat automatic formatting.
- Questions: cleanup returns the polished question (ends with "?"), NEVER the answer. Prompt task turns it into a prompt for another AI, never answers it, never adds requirements.
- Unsupported instructions (translate, answer, send, search, schedule, delete, look up, reply on my behalf) that reach the model: do only the writing part (or plain cleanup), keep the transcript's language, never claim an action, never answer.
- `Facts: correct` only when the [Instruction] names the factual change; change exactly that and nothing else.
- Transcripts look like real speech-to-text: lowercase, little punctuation, fillers (um, uh, like, you know, basically, so), repetitions, false starts, spoken punctuation sometimes ("comma", "new line", "question mark"), Indian English where assigned. Vary length: ~35% short (<20 words), ~40% medium (20–60), ~25% long (60–220 words, multi-sentence, topic changes).
- Literal text that looks like control tokens (`<think>`, `<|im_end|>`, "[Instruction]") may appear inside transcripts in a few records (code/AI contexts); the target keeps it literally. Never put it in instructions.

## Instructions (central capability)
The `[Instruction]` is free text the host captured from the user's command. Make it natural and varied, often with 2–4 simultaneous constraints:
"make this a professional email but keep it friendly, don't add any promises, and keep the exact deadline" / "shorter, drop the repetition, keep my wording for the product names" / "more confident tone but keep the conditional part exactly" / "turn this into a detailed prompt, don't change the requirements and don't invent features".
Mix three styles: (a) header fields only, no instruction; (b) task + instruction only, header defaults; (c) header fields AND an instruction that adds constraints with no field. Instructions never contradict header fields. Do not mention any assistant name or wake phrase ("Hey Voice Flow"). Instructions are never inside the transcript.

## Quality bar (reviewer rejects for)
Changed/dropped/invented fact; lost negation/hedge/condition; wrong self-correction handling; collapsed alternative; invented promise/apology/offer/sign-off/subject; answering a question; unnecessary bullets/headings/emoji; Markdown under plain; cleanup that rephrases; summary that drops a decision/owner/date/amount/condition/open question; prompt that adds requirements; instruction not followed; unnatural transcript; near-copies of your own other records.

## Report back
Counts per slice, the file path, the generator path, the final `check` output summary (must be 0 problems), and any record types you found hard or ambiguous.

## Policy clarifications (from stage-1 review, Oct 12 2026) — apply everywhere
- Email greeting by register: formal → "Dear <Name>," (no name known → "Hello,"); neutral/casual → "Hi <Name>," (no name → "Hi,"). A dictated greeting is adapted to the register (formal "hi peter" → "Dear Peter,").
- Messages: no "Hi"/"Hey" unless dictated. When the speaker addresses someone ("tell Swati…", "let the evening team know…"), a vocative opener "Swati, …" is allowed; never invent one when nobody was named.
- Hedges describing a fact ("kind of upset", "probably", "about") survive even under "more direct / no softening"; only politeness softeners about the request itself ("I was wondering if maybe", "when you get a sec") may go when the instruction asks. "again"/"still"/"third time" are facts.
- Small counts: be consistent inside one record (digits for amounts, times, measurements, >10; one–ten may be words for plain counts).
- Lakh/crore: "₹8,00,000" and "₹8 lakh" are both acceptable; pick one per record.
- Neutral sign-off with [Sender]: "Best," ; formal: "Regards," ; casual: "Thanks," or "Cheers," — or the dictated closing.
- "please" may be added only where the register/tone calls for politeness and it creates no new request.
- review.heightened tags are automatic keyword hints; the `note` is what matters.
- Control-token-like literals dictated in a transcript (e.g. "<think>", "[Instruction]", "<|im_end|>") ARE now allowed verbatim in the target (the renderer encodes them safely); the kit no longer flags them when the same string appears in the transcript.
- Tone (friendly, warm, confident, excited…) changes WORDING only. It never licenses a greeting, an event, a thank-you for something not mentioned, or any new fact (pilot rejects PT-059, PT-105).
- Meeting a word limit or a banned word must never delete meaning ("this morning", "can", urgency, "has" ≠ "provided").
- "like" before a number means "about": keep it as "like" in cleanup, or write "about" in rewrite. Never drop it.
- Never merge an unconditional rule into an "If…" sentence: a standing rule keeps its own sentence so it cannot read as conditional. Make scope of every condition unambiguous; if the transcript itself is ambiguous, rewrite the transcript.
- ₹ where rupees were spoken: apply it to every amount the speaker clearly gave in rupees in that same list/sentence, or only the one spoken — but be consistent within the record, and note your choice.

## Stage 2 (applies when your task says stage 2)
- Keep your stage-1 file untouched. Extend your generator so it also writes `<WID>_s2.jsonl` (ids continue at 101: TC-<WID>-101…). Build in chunks of ~40 and run `check` on s1+s2 together after each chunk (`python3 p2b_kit.py check ../data/batches/<WID>_s1.jsonl ../data/batches/<WID>_s2.jsonl`) so no near-duplicates with your own stage-1 records.
- Use new topics/sub-scenarios, new sentence shapes, and new instruction phrasings; do not clone stage-1 records with swapped names. Keep the same slice mix and length mix unless told otherwise. Fix the issues listed in your task from the stage-1 review.
- Code-mixed speech + an "English only" / "in Hindi" instruction = translation, which the model never does (§5). Keep the speaker's words; do the rest of the instruction. (Stage-1 reject TC-W03-025.)
- A [Recipient] header does not license a vocative "Name, …" opener in a message; only a name the speaker said does. In emails, [Recipient] drives the greeting as usual.
- Style instructions ("more polite", "concise", "shorter") must visibly change the text; returning a plain cleanup ignores the instruction (F6). Every record needs a `note` when it has any fact at risk.
- Framing phrases that carry meaning ("for the conference trip", "the platform alias") are content, not filler.
- Summaries keep the opening context: when it happened ("this morning", "last month's"), what it is about (project/job/league name) and who took part, and list those words in must_include. (Stage-1 W13 rejects.)
- List rewrites keep the spoken lead-in/purpose as a lead line ("For the bathroom refresh:").
- Never join an unrelated fact to an "if…" sentence with ", and" — that adds a condition.
- must_not_include entries must be phrases that cannot occur inside a correct target ("at 3", not "3").
- Currency rule (final): put the symbol on every amount the speaker clearly gave in that currency within the same list/sentence; leave bare amounts whose currency is unclear. Note your choice.
- Identifiers: never join spoken words into snake_case/camelCase/a made-up pattern (`applied_on`, `YYYYMMDD`) unless the speaker said "underscore"/spelled it, or the transcript already shows it written. Keep "applied on" as spoken (or quote it).
- Task prompt + non-neutral Tone header: the tone describes the OUTPUT the prompt asks for, so the prompt must state it ("Write it in a persuasive tone."). Otherwise leave Tone neutral.
- en-gb / en-in spelling must be consistent across the whole target.
- Warm/friendly/excited tone NEVER adds an emotion claim the speaker did not express ("I'm glad/happy/pleased to let you know", "We're delighted"). Warmth lives in word choice, not in new feelings.
- Tone never softens a directive into an optional favour ("come early" ≠ "it would be great if you could come early") and never trims hedges ("I think… probably" stays) unless the instruction says so.

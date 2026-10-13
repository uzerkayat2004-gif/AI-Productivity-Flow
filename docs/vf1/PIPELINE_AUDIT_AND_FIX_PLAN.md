# Voice Flow Pipeline Audit and Fix Plan (Phase 1)

Repo: `uzerkayat2004-gif/AI-Productivity-Flow`, branch `main`.
**Current HEAD = `43db82d`** (fetched Oct 12, 2026; `origin/main` has no newer commits), so HEAD and the reference commit are identical. Every line number below is valid at HEAD.
Method: source reading plus running the real parser and resolver read-only (`verify_defects.py` → `defect_verification_head.json`, 30 probes). No production code changed.

---

## 1. Current pipeline (HEAD)

```
ASR transcript
 └ main.py ~2225  detect_voice_command(text)            voice_commands.py:528
     ├ wake phrase regex (_WAKE_RE) + quote masking + reported-speech prefix check
     ├ clause split (sentence end, comma/colon, unpunctuated heuristic _split_unpunctuated_command:437)
     └ _parse_command(clause):344 → VoiceCommand(operation, format, context_reference,
                                     overrides{tone,formality,length,clarity,grammar,dedupe},
                                     preserve_wording, persistent_change, ambiguous, scope)
 └ StyleEngine.resolve(app/window) → ResolvedStyle (20 cards + 4 autocleanup presets)
 └ resolve_effective_style(resolved, command)           effective_style.py:160
     → EffectiveStyle(instruction text, task cleanup|rewrite|summarize|prompt, format, preserve_wording, label)
 └ apply_spoken_punctuation → TextPolisher.polish()
     ├ deterministic/local      → rule cleanup
     ├ S1 selected              → s1_can_handle():256 ? S1 (native 3-field control line) : one cleanup pass / deterministic
     └ cloud/BYOK               → _command_system_prompt():883 + "Style instruction: …"
 └ guards: normalization_preserves_content (S1 path, cleanup-only), _candidate_preserves_content (cloud, task-aware),
           _fulfills_command (bullets / email layout / prompt shape / short ratio), _is_assistant_response
 └ fallback: deterministic cleanup + _apply_style_register; try_local_command_rewrite (email/prompt templates)
 └ output + outcome label ("command_unfulfilled" → "Voice command could not be completed – basic cleanup applied")
```

Privacy guarantee verified by reading: the S1 path never falls back to cloud (polisher.py ~1204, 1340–1360).

Follow-up edits: **not supported**. No code path passes a previous draft back to a model (`grep` for previous/last output in main.py finds nothing relevant).

---

## 2. Known defects — status at HEAD

Legend: **Confirmed** = reproduced at HEAD by `verify_defects.py`; **Present (code)** = unchanged code at the same lines, not re-executed.

| # | Defect | HEAD evidence | Status | Sev |
|---|---|---|---|---|
| A1a | Unpunctuated "make this a linkedin post i just finished…" → content `''` | probe A1a | **Confirmed** | P0 |
| A1b | Unpunctuated "keep my wording um so the release…" → content `''` | probe A1b | **Confirmed** | P0 |
| A2 | "make it less formal" → `formality: formal` | probe A2 | **Confirmed** | P0 |
| A3 | Not recognized; wake phrase + command sent to model as dictation: "make this a list", "make this a summary", "make it detailed", "simplify this", "remove duplicates", "make this sound better" | probes A3a–f: `command=None`, content starts with "hey voice flow, …" | **Confirmed** (6/6) | P1 |
| A4 | Leftover command words in content: `message.`, `only.`, `in my work style.` | probes A4a–c | **Confirmed** | P1 |
| A5 | Only one override kept: "detailed and formal" → formal only; "email and make it short" → `make it short.` left in content | probes A5a–b | **Confirmed** | P1 |
| A6 | Constraints lost/misplaced: "but don't change my promise." and "keep both deadlines." left in content; "without hashtags" silently dropped | probes A6a–c | **Confirmed** | P1 |
| A7 | "slack message" / "teams message" → `personal_message` | probes A7a–b | **Confirmed** | P1 |
| A8 | Unquoted reported speech ("my colleague said hey voice flow make this an email…") triggers email and deletes words → content `my colleague said but i was only quoting him` | probe A8 | **Confirmed** | P1 (data loss) |
| A9 | Second wake command left in content | probe A9 | **Confirmed** | P1 |
| A10 | S1 gate refuses summary, prompt, LinkedIn, note, work/personal message, persistent, ambiguous, any saved rule | s1_engine.py:256–330 | Present (code) | P1 |
| A11 | S1 control line has only 3 fields | s1_engine.py:162–245 | Present (code) | P1 |
| A12 | Saved category rule dropped entirely on explicit formal/casual override | effective_style.py:261 | Present (code) | P1 |
| A13 | `style_standing_instruction` read but never written | s1_engine gate | Present (code) | P3 |
| A14 | S1 output cap 1.3× + 48 too small for drafting | s1_engine | Present (code) | P1 |
| A15 | >700 words chunked into independent pieces (breaks summaries) | s1_engine.py ~800–830, ~991 | Present (code) | P1 |
| A16 | S1-path validator false-rejects 39% of good cleanups (self-corrections, filler removal, spoken punctuation, empty output) | prior measurement; code unchanged | Present (code) | P1 |
| A17 | `_fulfills_command` never checks tone, formality, LinkedIn shape, summary coverage, placeholders | polisher.py | Present (code) | P1 |
| A18 | Chat-special tokens in transcript tokenized as control tokens (string concatenation + `special=True`) | s1_engine.py:246 | Present (code) | P2 |
| A19 | Greedy output not bit-exact with prompt caching | runtime | Present | P2 |

### Newly found in this review

| # | Defect | Evidence | Sev |
|---|---|---|---|
| N1 | "make this a short summary" → rewrite+short, `summary.` left in content (known), confirmed again | probe N1 | P1 |
| N2 | "formal and friendly" treated as a contradiction → **whole utterance incl. wake phrase sent as dictation** | probe N4 | P1 |
| N3 | Unsupported command ("translate this to hindi") → wake phrase + command passed to the model as dictation; a model may obey it | probe N6 | P1 (safety) |
| N4 | "make this a numbered list" not recognized | probe N7 | P1 |
| N5 | "don't make it formal" not recognized → whole utterance passed through | probe N9 | P1 |
| N6 | "from now on make my emails formal" → `persistent=True` but `context_reference=None` (scoping lost) — confirmed | probe N5 | P2 |
| N7 | No-wake commands ("make this an email. …") are plain dictation — correct for this app, but means the contract needs a host-agnostic path (`Task: auto`) | probe N3 | design |
| N8 | No follow-up/edit flow; no `Locale`; no sender/recipient identity → models are pushed to invent `[Your Name]` | code reading | design |
| N9 | Trailing command works ("the build failed twice today. hey voice flow, make this an email.") | probe N2 | OK |

Root causes (code reading):
- **A1a:** in `_split_unpunctuated_command`, the tokens `linkedin`/`post` are in `_COMMAND_SYNTAX_WORDS` but not in `_COMMAND_INTENT_WORDS`/`_COMMAND_FORMAT_WORDS`, so `saw_intent` stays False, the function returns `(whole, "")`, and the caller then parses the whole run-on as the command clause → empty content.
- **A1b:** `keep` is not in `_COMMAND_START_WORDS`, so the split returns `(whole, "")`; `_KEEP_WORDING_RE` then makes the whole thing a command.
- **A2/N5:** register parsing matches the bare words `formal|professional` with no negation/comparative handling.
- **A5a:** `_LENGTH_DETAILED_RE` requires `longer|more detailed|expand`; bare "detailed" isn't matched, so only `formal` survives.
- **A5b:** in `_split_unpunctuated_command`, after the format word `email` sets `saw_format`, the `and` is accepted (next word `make`), but the following `make` hits the `saw_format` guard (`make` isn't in its allowed list) and the loop breaks, so `make it short.` becomes content.
- **A8:** `_REPORTED_WAKE_PREFIX_RE` only accepts pronoun subjects (`i|you|we|they|someone`), not noun phrases ("my colleague said").
- **A9:** only the first wake phrase is processed.

---

## 3. Fix plan (exact changes, P0 first)

All fixes are parser/host-side and must land **before** training data is generated, because the data generator runs through this parser.

### F1 — No-loss invariant (P0 safety net, fixes A1a/A1b class)
In `detect_voice_command`, after computing `(clause, content)`:
```python
# Never let a command swallow dictation.
if command is not None and not content.strip():
    clause_words = len(re.findall(r"\w+", clause))
    if clause_words > 8:                      # a command phrase is short
        head, tail = _split_at_intent_end(clause)   # new helper using _UNPUNCTUATED_INTENT_END_RE
        if tail:
            clause, content = head, tail
        else:
            return CommandDetection(content=text, command=None)   # preserve everything
```
`_split_at_intent_end` = end of the last `_UNPUNCTUATED_INTENT_END_RE` match within the first 18 words.
Tests: A1a → content `i just finished my first marathon and i am proud`, fmt linkedin_post; A1b → content `um so the release is on friday`, pw True; a 9+-word clause with no intent → full passthrough.

### F2 — Intent vocabulary (A1a, A3, N4)
- Add `linkedin`, `post`, `list`, `summary`, `numbered` to `_COMMAND_INTENT_WORDS`/`_COMMAND_FORMAT_WORDS`; add `keep`, `simplify`, `summarise`, `summarize` to `_COMMAND_START_WORDS`.
- `_FORMAT_PATTERNS`: add `("bullet_list", r"\b(?:make|turn|convert)\s+(?:this|it)\s+(?:into\s+)?(?:a\s+)?list\b")`, new `("numbered_list", r"\bnumbered\s+(?:list|points|steps)\b")`.
- `_SUMMARIZE_RE`: `r"\b(?:summari[sz]e|summary|tl;?dr)\b"` (only reached when `_COMMAND_SHAPE_RE` matched, so content mentions of "summary" stay safe).
- `_LENGTH_DETAILED_RE`: add bare `detailed`; `_CLARITY_RE`: add `simplify`; `_DEDUPE_RE`: add `remove\s+duplicates?`; add `better|polish(?:ed)?|improve` → `grammar: fix` + `clarity: improved`.
Tests: probes A3a–f, N1, N4 parse as intended with clean content.

### F3 — Register negation and comparatives (A2, N5)
Before matching register words:
```python
_REGISTER_DOWN_RE = re.compile(r"\b(?:less|not\s+so|not\s+too)\s+(?:formal|professional)\b|\bdon'?t\s+make\s+it\s+(?:formal|professional)\b", re.I)
_REGISTER_UP_RE   = re.compile(r"\b(?:less|not\s+so)\s+(?:casual|informal)\b|\bmore\s+(?:formal|professional)\b", re.I)
```
`_REGISTER_DOWN_RE` → `formality: relaxed` (VF-1 `Register: neutral` from formal, `casual` from neutral); strip the matched span before the plain word scan. Add `don't` to `_COMMAND_SHAPE_RE` starts (`don['’]t\s+make`).

### F4 — Register vs tone are separate dimensions (N2)
Only flag `ambiguous` when **both words are in the same dimension** (formal+casual, professional+relaxed). "formal and friendly" → `formality: formal, tone: friendly`. Move `casual` out of `_TONE_WORDS` into a register set.

### F5 — Multiple overrides and constraints (A5, A6)
- In `_split_unpunctuated_command` and the comma-boundary loop, allow continuation after a completed format when the next tokens start a command (`and make|and keep|but keep|but don't|without|with no`).
- New `VoiceCommand.constraints: tuple[str, ...]`: capture `but …`, `without …`, `keep both/all …`, `don't change …` spans that belong to the command clause; strip them from content. Serialize to VF-1 `[Instruction]`.
Tests: A5a → length detailed + formality formal; A5b → email + short, content `the build is green and ready`; A6a–c → constraints recorded, content clean.

### F6 — Leftover words (A4)
After parsing, strip from the content start any residue matching `^(?:message|msg|text|only|summary|in\s+my\s+\w+\s+style)[.,]?\s+` **only if** that residue is a continuation of the command clause (i.e. directly follows the split point). Better root fix: extend the command consumer so `text message`, `fix grammar only`, `in my work style` are consumed as one phrase (add `only`, `style` handling; `text` already in syntax words).

### F7 — Slack/Teams (A7)
`("work_message", r"\b(?:work|slack|teams)\s+(?:message|chat|msg)\b")` placed before personal patterns.

### F8 — Reported speech (A8)
Extend `_REPORTED_WAKE_PREFIX_RE` with `\b(?:\w+\s+){0,3}(?:said|says|told\s+me|asked|mentioned|was\s+like)\s*[,:]?\s*$`. Tests: A8 → `command=None`, content unchanged.

### F9 — Multiple wake commands (A9)
Loop over all wake matches outside quotes; merge command clauses (later wins per dimension); remove each clause from content. Cap at 3 to bound work.

### F10 — Unsupported commands (N3)
Add `_UNSUPPORTED_RE = r"^\s*(?:please\s+)?(?:translate|answer|reply\s+to|send|search|look\s+up|delete|google)\b"`. When a wake phrase is followed by an unsupported verb: return `VoiceCommand(operation="unsupported", raw_phrase=…)`, strip wake + clause from content, run cleanup, show "'Translate' isn't supported yet". Never forward it to a model.

### F11 — Persistent scoping (N6)
In `_parse_command`, when `persistent_change` and a format word is present (`emails`, `messages`, `notes`), set `context_reference` from the format (`emails` → `email`). Verify `apply_persistent_change` in main.py uses it.

### F12 — Saved rules on override (A12)
`effective_style.py:261`: instead of dropping the whole category extra rule, drop only rules that conflict with the explicit override (register words); keep the rest (e.g. "avoid emoji").

### F13 — VF-1 serializer and router (contract)
New module `src/voice_flow/vf_contract.py` (host adapter): `build_vf1(effective, command, content, *, draft=None, locale, sender=None, recipient=None, rules=()) -> (system, user)`, the escaping of §9, and `native_eligible()` for the S1 compatibility path. Old paths stay untouched until the trained models pass gates.

### F14 — Engine changes needed for trained models (later, behind a flag)
- S1/Qwen inference: tokenize system/header with `special=True`, **user-supplied text with `special=False`** (A18).
- Task-aware output caps: cleanup 1.3× + 48; rewrite/email/prompt `max(256, 2.5×)`; summary `max(128, 0.8×)`; plus the n-gram loop watchdog (keep greedy, repeat penalty 1.0 per S1 audit).
- No chunking for summarize/prompt/edit; reject >1,500 words for those with a notice.
- `s1_can_handle` → replaced by `variant_supports(task, format)` per deployed model.

### F15 — Validators (A16, A17)
- Replace the cleanup-only S1 guard on the VF-1 path with a **protected-fact checker**: extract numbers, dates, names (capitalized/known contacts), negations, identifiers from the *corrected* source (apply self-corrections deterministically where cue words are present, else compare against the union) and require each in the output; alternatives must keep all values.
- Add placeholder (`\[[^\]]*(name|recipient|company)[^\]]*\]`), invented `Subject:`, tag echo (`<input_transcript>`, `[Transcript]`), template leak, language-script drift (non-Latin/non-source script ratio, Polish/Czech diacritics), and summary length checks.
- Keep the fallback order: trained model → (S1 native cleanup if available) → deterministic cleanup.

### Order and effort
| Step | Items | Rough size |
|---|---|---|
| 1 | F1, F3, F8 (P0 + data-loss) | small, 1 PR |
| 2 | F2, F4–F7, F9–F11 | medium, 1 PR, extend `tests/test_voice_flow_commands.py` with the 30 probes |
| 3 | F12, F13 (serializer, no behavior change) | medium |
| 4 | F15 checker (used by data generation and runtime) | medium |
| 5 | F14 (only when a trained model ships) | medium |

Steps 1–4 are **training blockers**; step 5 is a deployment task.

### Regression protection
Add `defect_verification_head.json` probes as parametrized tests with expected parses; keep all existing tests green (98 passed, 3 environment-only failures previously).

---

## Phase 1.1 status (Oct 12, 2026)

F1–F12 implemented on `feat/vf1-universal-contract`, plus configurable assistant identity, unsupported-command flag, multi-wake merge, honest S1 outcome, and the A16 guard fix. Still open: A13 (S1 drafting caps), A14/A15 runtime wiring of task-aware checks, A17 (`_fulfills_command` tone/summary/LinkedIn checks), A19 app UI. Full per-defect table: `PHASE1_1_IMPLEMENTATION_REPORT.md` §2.

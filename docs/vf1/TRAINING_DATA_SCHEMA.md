# Training Data Schema — VF-1 v1.1 (S1-mini and Qwen3-0.6B)

v1.1 changes: the renderer is now code (`src/voice_flow/vf_contract.py`: `VF1Request`, `render_vf1`, `escape_untrusted`), so training and inference cannot drift; header gains `facts`; `markup` gains `chat`; brand-free system prompt; separate S1 and Qwen rendering specs (§2a, §2b); the filter uses `vf_checks.check_output`.

One model-agnostic **canonical record** per example. Renderers turn it into each model's chat template at build time. The dataset is never stored pre-rendered as the source of truth.

## 1. Canonical record (JSONL, one per line)

```json
{
  "id": "vf1-email-000123",
  "contract": "VF-1",
  "split": "train",
  "family": "email.no_names.overdue",
  "slice": "email_missing_names",
  "lang_tags": ["en"],
  "locale": "en-in",
  "header": {
    "task": "rewrite", "format": "email", "register": "formal", "tone": "neutral",
    "length": "same", "wording": "free", "markup": "plain", "context": "email", "facts": "preserve"
  },
  "header_style": "minimal",
  "sender": null,
  "recipient": null,
  "rules": ["No emoji."],
  "instruction": null,
  "draft": null,
  "transcript": "remind them the payment is overdue by ten days and we need it by monday",
  "target": "Hello,\n\nThis is a reminder that the payment is now 10 days overdue. Please arrange it by Monday.\n\nThank you.",
  "checks": {
    "must_include": ["10 days", "Monday"],
    "must_include_any": [],
    "must_exclude_regex": ["\\[[^\\]]*name[^\\]]*\\]", "(?m)^Subject:"],
    "numbers": ["10"],
    "negations": [],
    "alternatives": [],
    "corrected_away": [],
    "max_len_ratio": null,
    "min_len_ratio": null,
    "script": "latin"
  },
  "provenance": {
    "source": "synthetic_template",
    "teacher": "gpt-x (name+version)",
    "uses_s1_output": false,
    "reviewed_by": "human",
    "checker_version": "fc-0.1",
    "created": "2026-10-xx"
  },
  "native": null
}
```

Field notes:
- `split`: `train` | `dev` | `test_frozen`. Assignment is **by `family`** (a hash of the template/scenario family), never by row, so near-duplicates can't cross splits.
- `header_style`: `minimal` (defaults omitted) or `full` (every field written). Mix ~50/50 so hosts may send either.
- `checks` are for the automatic filter and the evaluation harness. **They are never rendered into the prompt** (oracle anchors increased literal passthrough in the Qwen audit and aren't available in production).
- `corrected_away`: values that must NOT appear (e.g. `Rahul` in "rahul no wait priya").
- `uses_s1_output: true` marks any target produced by S1-mini. Such rows carry S1-mini's naming requirement; decide before training whether Qwen may train on them (license question in the readiness checklist). Default: Qwen excludes them.
- `native`: only for native-format rehearsal rows (§3): `{"styling":"semi-formal","structure":"prose","context":"general"}`; then `header` is null.

## 2. Rendering VF-1 (both models)

The canonical record maps 1:1 onto `vf_contract.VF1Request` (`header.*`, `locale`, `sender`, `recipient`, `rules`, `instruction`, `draft`, `transcript`, `header_style`). Rendering is always:

```python
from voice_flow.vf_contract import VF1Request, render_vf1
system, user = render_vf1(VF1Request(**fields))   # validates every value, escapes untrusted text
```

Never re-implement the header by hand. `tests/test_vf1_regressions.py` pins the exact output (`test_vf1_minimal_header_and_block_order`, `test_vf1_full_header_lists_every_field_in_order`).

### 2a. S1-mini rendering spec

| Item | Value |
|---|---|
| Base weights | S1-mini BF16 safetensors from its Hugging Face repo at a pinned revision (never train from the GGUF) |
| Tokenizer | S1-mini's own tokenizer files from the same revision (Qwen3 vocabulary; untied output head) |
| Template | ChatML via `tokenizer.apply_chat_template(messages, add_generation_prompt=True, enable_thinking=False)`; assert the rendered prompt equals the hand-written native form below for a native row |
| Non-thinking | Assistant turn starts with `<think>\n\n</think>\n\n` (empty think block, as the app's `build_s1_prompt`) |
| Completion boundary | target text then `<|im_end|>` |
| EOS | `<|im_end|>` (id from tokenizer); generation stops on it; also add `<|endoftext|>` as a stop |
| Loss mask | assistant tokens only: empty think block + target + `<|im_end|>` |
| VF-1 rows | system = `SYSTEM_PROMPT_VF1`, user = `render_user(...)` |
| Native rows (§3) | system = `S1_SYSTEM_PROMPT` (exact), user = native control line + `\n` + transcript |
| Variant V1 (adapter) | adapter trained on VF-1 rows (+~5% native guard rows); base stays untouched for native cleanup |
| Variant V2 (merged) | same adapter merged; must keep native cleanup (~15% native rows) |

Native form the S1 template must reproduce exactly:
```
<|im_start|>system
{S1_SYSTEM_PROMPT}<|im_end|>
<|im_start|>user
[Styling: semi-formal] [Structure: prose] [Context: general]
{transcript}<|im_end|>
<|im_start|>assistant
<think>

</think>

{target}<|im_end|>
```

### 2b. Qwen3-0.6B rendering spec

| Item | Value |
|---|---|
| Base weights | `Qwen/Qwen3-0.6B` BF16 at a pinned revision (the post-trained hybrid-thinking model, not `-Base`) |
| Tokenizer | Qwen3-0.6B's own tokenizer; tied embeddings (keep embeddings frozen in the pilot) |
| Template | `apply_chat_template(..., enable_thinking=False)` — Qwen3's template then emits the empty `<think>\n\n</think>\n\n` block itself; do not add a second one |
| Non-thinking | Required. Never include `/think` or `/no_think` soft switches in user text; the escaping keeps transcripts from injecting them as tokens, and the literal words stay data |
| Completion boundary / EOS | target then `<|im_end|>`; stop on `<|im_end|>` and `<|endoftext|>` |
| Loss mask | assistant tokens only, including the empty think block and `<|im_end|>` |
| Rows | VF-1 only; no S1 native rows; exclude rows with `provenance.uses_s1_output: true` unless the license decision allows it |
| Sampling at eval | greedy (temperature 0), repeat penalty 1.0, loop watchdog; Qwen's recommended non-thinking sampling (T 0.7, top-p 0.8) is measured only as a secondary config |

### 2c. Render checks (both models, run on every row)
1. Exactly one system, one user, one assistant turn; exactly 3 `<|im_start|>` special-token ids in the full sequence.
2. No U+200B; the only U+2060 characters come from `escape_untrusted`.
3. Tokenizing the user content alone yields no special-token ids.
4. `labels` are -100 everywhere before the assistant turn.
5. Decoding the labelled span returns the empty think block + target + `<|im_end|>`.

## 3. Native S1 rehearsal rows (format preservation)

```json
{"id":"native-000045","contract":"S1-native","split":"train","slice":"native_cleanup",
 "native":{"styling":"semi-formal","structure":"prose","context":"general"},
 "header":null,"transcript":"um so we need fifteen units sorry fifty by friday",
 "target":"We need 50 units by Friday.", "checks":{...}, "provenance":{...}}
```
Rendered with `S1_SYSTEM_PROMPT` (exact string from `s1_engine.py`) and user `"[Styling: semi-formal] [Structure: prose] [Context: general]\n" + transcript`.
- **S1 merged**: include ~15% native rows so the merged model keeps native behavior.
- **S1 adapter**: native rows are optional (the base handles native with the adapter off); include ~5% as a guard in case the host runs native prompts with the adapter on.
- **Qwen**: no native rows (Qwen never sees S1's prompt); its cleanup lives in VF-1 `Task: cleanup`.

## 4. Slices (names fixed; counts are set per pilot in the training specs)

| slice | content |
|---|---|
| `cleanup_basic` | fillers, false starts, repeats, punctuation, casing |
| `cleanup_numbers` | ITN: money (₹, $, lakh/crore), quantities, %, phones, dates, times, versions, error codes |
| `cleanup_identifiers` | code identifiers, paths, URLs, emails (incl. "at the rate") by `Context` |
| `correction` | self-correction cues → final value only |
| `alternative` | "or", "either/or", "between" → all values |
| `contrast_pair` | minimal pairs differing in one cue word (correction vs alternative) |
| `negation_condition` | negations, negation corrections, only if/unless/before/after |
| `question_keep` | dictated questions kept as questions |
| `multilingual` | Hinglish, Indian English, Devanagari, Indian names/brands |
| `email_*` | `email_named`, `email_missing_names`, `email_sender_field`, `email_dictated_subject` |
| `message` | work/personal chat messages |
| `note` / `bullets` / `numbered` / `post` | formats |
| `tone_register_length` | tone, register, shorter/short/longer, hedges preserved |
| `keep_wording` | `Wording: keep` |
| `prompt_gen` | prompt generation incl. constraints and negatives |
| `summary` | compressed, status-exact |
| `rules_precedence` | `[Rules]` + conflicts with `[Instruction]`/fields |
| `multi_instruction` | several fields + free-text constraints |
| `auto_mode` | instruction at start/end, none, unsupported, quoted, reported |
| `edit_followup` | `[Draft]` + `[Instruction]` (+ optional `[Transcript]`) |
| `facts_correct` | `Facts: correct` with an explicit instruction naming the fix; everything else unchanged |
| `question_not_answered` | questions for another assistant: cleanup keeps the question, prompt task builds a prompt, never an answer |
| `markup_chat` | `Markup: chat` outputs (no `**`, `#`) |
| `hard_negative` | injection, answer-bait, placeholder-bait, instruction-word echo, tag-like text, filler-only → empty |
| `eos_drill` | short outputs, unsigned email endings |
| `native_cleanup` | §3 |

## 5. Quality filter (every row, before training)

1. Render both models' prompts; assert the template checks in §2.
2. Run `vf_checks.check_output(transcript, target, task=..., fmt=..., instruction=..., allow_number_change=(facts == "correct"))` → no failures, plus the row's own `checks`.
3. Placeholder/subject/tag-echo/script regex → must pass.
4. `max_len_ratio`/`min_len_ratio` for summaries/short.
5. Deduplicate by normalized transcript; cap 3 targets per family.
6. Human review: 100% of `contrast_pair`, `negation_condition`, `multilingual`, `summary`; ≥ 20% sample elsewhere.
7. Reject any row whose transcript appears in either audit or in `test_frozen` (n-gram overlap ≥ 0.8).

## 6. Files

```
data/vf1/
  canonical/{train,dev,test_frozen}.jsonl     # source of truth (test_frozen written first, then locked; sha256 recorded)
  rendered/s1/{train,dev}.jsonl               # {"input_ids":..., "labels":...} or messages for TRL
  rendered/qwen/{train,dev}.jsonl
  manifest.json                                # counts per slice/split, checker version, hashes, contract version
```

# Phase 1.1 Implementation Report — VF-1 contract and pipeline fixes

Date: Oct 12, 2026. Branch: `feat/vf1-universal-contract` (from `main` @ `43db82d`, the latest upstream). `main` untouched. No training, no dataset generation, no model downloads.

## 1. What changed

| File | Change |
|---|---|
| `src/voice_flow/activation.py` (new) | `ActivationConfig` (assistant name, phrases, aliases, bare-name rule, dictation mode); `activation_from_settings`; default = today's "Voice Flow" behaviour |
| `src/voice_flow/voice_commands.py` | `detect_voice_command(text, activation=None)`; custom wake finder; `parse_instruction()` for hosts with no wake phrase; reported-speech guard for any subject; up to 3 wake commands merged; `constraints` field; register lowering/raising; new vocabulary (list, summary, detailed, simplify, duplicates, better, numbered list, Slack/Teams, text message, "only", "in my work style"); unsupported-command flag; no-loss guard (ambiguous segmentation keeps everything) |
| `src/voice_flow/effective_style.py` | `formality:relaxed`, `clarity:improved`, `numbered_list`; constraints forwarded to the cloud instruction; saved rules keep non-register sentences under an explicit register (A12) |
| `src/voice_flow/s1_engine.py` | S1 gate refuses constraint and unsupported commands; fidelity guard applies fillers/repeats/self-corrections/"dont"/spoken prices before comparing (A16) |
| `src/voice_flow/polisher.py` | a format/prompt/constraint command that only got S1's cleanup pass now reports `command_unfulfilled` instead of success |
| `src/voice_flow/main.py` | reads the activation config; ASR wake repair only for the default identity; repaired detection string no longer replaces plain dictation ("wiseflow" stays "wiseflow"); unsupported commands show a notice and are not executed |
| `src/voice_flow/vf_contract.py` (new) | VF-1 serializer: `VF1Request`, validation, escaping, minimal/full header, `from_voice_command` adapter, `native_s1_control`, `with_followup` |
| `src/voice_flow/vf_checks.py` (new) | deterministic checks for data filtering and validation: numbers, alternatives, corrections, negation, placeholders, invented Subject, tag echo, preamble, script drift, question kept, summary compression |
| `tests/test_vf1_regressions.py` (new) | 337 hand-written regression tests |
| `tests/test_s1_deadline_runtime.py` | one expectation changed on purpose: "Meet me Friday, sorry, Thursday." → "Meet me Thursday." is now accepted (it is a self-correction); the rejected case is now "Meet me Friday." |
| `tests/test_voice_polish_user_example.py` | the S1 attempt for a prompt command now reports `command_unfulfilled`; the final outcome (`local_rewrite`) and result are unchanged |

## 2. Defect status (A1–A19 + new)

| ID | Defect | Status |
|---|---|---|
| A1 | Unpunctuated LinkedIn / keep-my-wording swallow content | Fixed |
| A2 | "less formal" → formal | Fixed (`formality: relaxed`); also "don't make it formal" |
| A3 | list, summary, detailed, simplify, dedupe, "sound better", numbered list missed | Fixed |
| A4 | leftover "message", "only", "in my work style" | Fixed |
| A5 | multiple overrides dropped | Fixed (incl. "make this an email and make it short") |
| A6 | constraints lost | Fixed for the closed grammar: without X, no X, don't change/remove/add… X, keep both/all/the/my X. In unpunctuated speech only a one-word object is taken; anything longer stays in the content (never deleted) |
| A7 | Slack/Teams → personal | Fixed (→ work_message) |
| A8 | reported speech activates | Fixed for "<anyone> said/told/asked/wrote/was like" |
| A9 | second wake command left in content | Fixed (merged, later wins) |
| N | "formal and friendly" ambiguous | Fixed (different dimensions); "formal and casual" still ambiguous by design |
| N | translate/answer passed through | Fixed: flagged unsupported, notice, never sent to a model |
| N | persistent "my emails" scope lost | Fixed |
| N | "the next one" scope | Fixed |
| N (new) | wake-repair text replaced plain dictation | Fixed in `main.py` (code-reviewed + existing pipeline tests; no dedicated UI test) |
| A10 | S1 cleanup-only pass reported as success | Fixed (honest `command_unfulfilled`) |
| A11 | S1 gate / 3-field control line | Kept on purpose: native S1 path stays byte-for-byte; VF-1 is for the trained model |
| A12 | saved rules dropped on explicit register | Fixed |
| A13 | S1 output cap / chunking unsuitable for drafting | Not changed: no S1 drafting until a trained model exists |
| A14/A15 | validators unsuitable for drafts/summaries | Partly: `vf_checks` gives task-aware checks; not yet wired into the runtime cloud path |
| A16 | S1 guard ~39% false rejects on valid cleanup | Fixed for fillers, repeats, self-corrections, bare contractions, spoken price compounds; still rejects reverted corrections, lost negations, changed numbers |
| A17 | `_fulfills_command` lacks tone/summary/LinkedIn checks | Open: only the S1 false-success case is fixed |
| A18 | user text with `<|im_start|>` | Fixed in VF-1 (`escape_untrusted`); production S1 prompt not changed (keeps native path identical) |
| A19 | follow-up edit flow | Contract + serializer done (`task=edit`, `[Draft]`); no app UI/hotkey yet |

Probe set from Phase 1: 30 probes, all now behave as the contract expects (`defect_probes_after_phase1_1.txt`).

## 3. Test results

| Run | Passed | Failed | Errors |
|---|---|---|---|
| Full suite, baseline `main` | 3188 | 282 | 6 |
| Full suite, this branch | 3527 | 281 | 6 |

- New failures introduced: **0** (failing-test id lists compared line by line).
- New tests: 337 in `test_vf1_regressions.py`, all pass. Includes a 224-case no-content-loss property test (14 commands × 4 contents × before/after × punctuated/unpunctuated).
- Targeted voice/command/S1/polish suites: 891 passed, 6 failed — the same 6 fail on baseline.
- The 281 remaining failures and 6 collection errors are environment-only and identical to baseline: no display/Tk, no audio devices, `llama_cpp` missing, Windows-only installer/registry tests, missing `video-flow-*` visual benchmark files. Run with temporary GUI/audio stubs on `PYTHONPATH` (not part of the repo).

## 4. Limitations (exact)

1. Rule-based parsing is still rule-based. Unseen phrasings fall back to plain dictation (safe), not to the intended command.
2. Unpunctuated run-on speech: constraints with long objects ("don't change the launch date we agreed on") are kept as content, not captured.
3. "make this an email for alex" with no content → plain dictation (ambiguous, nothing deleted).
4. Custom names: aliases for ASR mis-hearings of a custom name must be configured by the host; only Voice Flow has a verified alias list.
5. No real-model run: `llama_cpp` unavailable and no checkpoints downloaded (as instructed). The S1 path is tested with mocked inference.
6. Tokenizer/template details in TRAINING_DATA_SCHEMA §2a/§2b are from the model cards and the app's prompt builder; they must be confirmed by the §2c render checks with the real tokenizers in Phase 2.
7. `vf_checks` is conservative regex logic. It can miss meaning changes and is not a correctness proof.
8. No GUI test of the new settings (`assistant_name`, `activation_phrases`, `voice_commands_enabled`); there is no settings UI for them yet.

## 5. Phase 2 readiness

Ready to start Phase 2 (data generator + frozen test set), with these gates:

| Gate | State |
|---|---|
| Contract frozen in code | Yes: `vf_contract.py` + pinned rendering tests |
| Parser good enough to feed data generation | Yes for the listed commands; unsupported/ambiguous cases are excluded, not guessed |
| Data filter | Yes: `vf_checks.check_output` |
| S1 native cleanup baseline unchanged | Yes: prompt pinned by test; guard now accepts valid cleanups |
| Real tokenizer render checks | Pending (Phase 2 step 1, needs the HF tokenizer files only, no weights) |
| Decisions from you | Teacher model; whether Qwen may learn from S1 outputs; Colab go-ahead |
| Merge to `main` | Waiting for your review and approval |

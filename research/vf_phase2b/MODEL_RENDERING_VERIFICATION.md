# Model rendering verification — VF-1 Phase 2B

Tokenizer assets: the pinned tokenizer files from Phase 2A (`vf_phase2a/tokenizers/{s1-mini,qwen3-0.6b}`, revisions `88f6b158…` and `c1899de2…`). No model weights were downloaded.

## Verified properties

| Requirement | How verified | Result |
|---|---|---|
| Correct chat template | `apply_chat_template([system, user], add_generation_prompt=True, enable_thinking=False)`; full conversation template compared with prompt + target + `<|im_end|>` | identical (template adds only a trailing `\n` after `<|im_end|>`, which is not trained) |
| Qwen non-thinking behaviour | every rendered prompt ends with `<|im_start|>assistant\n<think>\n\n</think>\n\n` (`verify()` → `not_nonthinking_prompt`) | 0 failures / 3,033 examples |
| S1 native compatibility | rehearsal rows use S1's exact system prompt and `control\ntranscript` user turn, byte-identical to `src/voice_flow/s1_engine.py` and the model card's literal string | `test_native_render` passes |
| Assistant-only loss masking | labels = −100 over the whole prompt; first trained position == prompt length | 0 failures |
| End-of-turn handling | exactly one `<|im_end|>` (151645) in labels, as the last label | 0 failures |
| No zero-width contamination | no U+200B/U+FEFF anywhere in prompts or records (the Oct 12 duel bug) | 0 |
| Control-token-like text in transcripts | `escape_untrusted` puts U+2060 inside `<|`, `|>`, `<think>`, `<tool_call>` and full-width brackets on reserved markers in the prompt | verified in `test_prompt_is_nonthinking_and_escaped` |
| Control-token-like text in targets | **bug found and fixed**: `split_special_tokens=True` still emits id 151667 for a literal `<think>` (Qwen3 added tokens that are not "special"). `safe_encode` splits every added-token string into ordinary pieces; decode round-trip is exact | 11 corpus targets contain such literals; 0 added-token ids in any label |
| Valid instruction ordering | rendered by `vf_contract.render_vf1` only (header → Sender → Recipient → Rules → Instruction → Draft → Transcript last) | no hand-built headers |
| Response-only targets | preamble/explanation checks + review | 0 |
| Identical candidates | both tokenizers produce byte-identical renders (`corpus_qwen3-0.6b.jsonl` and `corpus_s1-mini.jsonl` share SHA-256 `5ca30389…`) | confirms the shared tokenizer finding of Phase 2A |

## Lengths

Corpus: max 477 tokens, mean 193, p95 335; 124,146 trained tokens (mean 48.5 per example). Rehearsal: max 267, mean 136; 14,616 trained tokens.

## Notes for the host / inference

- The model learns to output `<think>` literally (as ordinary tokens) when the speaker dictated it. Host code that strips `<think>…</think>` from outputs (current `s1_engine.py` does this) should only strip a leading empty think block, or such dictation will be damaged.
- Inference must use the same `escape_untrusted` on transcript/draft/rules text.

## Tests

`tests/test_phase2b.py`: 17 tests, all passing (`logs/phase2b_tests.log`): held-out hash frozen; tokenizers identical; safe_encode round-trip for 6 control strings; documentation of the Phase 2A leak; non-thinking + escaping; native render; mixture share and identical common order; every corpus record valid and reviewed; split integrity and leakage; every corpus record renders cleanly for both models; rehearsal rows valid; fast near-duplicate search equals brute force. Phase 2A's own 64 tests still pass.

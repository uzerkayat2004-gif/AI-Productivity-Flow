# Tokenizer Verification Report — S1-mini and Qwen3-0.6B

Date: Oct 12, 2026. Only tokenizer/config files and the safetensors **header** were downloaded; no weights, no inference. For the tied-head check, three 256 KB windows of two tensors per model were read by HTTP range request (768 KB per tensor out of 311 MB).

## 1. Assets (pinned)

| Model | Repo | Revision | Files |
|---|---|---|---|
| S1-mini | `superwhisper/s1-mini` | `88f6b15896c73bbb13a3b596e0afe8ea0d5150b4` | tokenizer.json, tokenizer_config.json, vocab.json, merges.txt, chat_template.jinja, config.json, generation_config.json, README, LICENSE, NOTICE, safetensors header |
| Qwen3-0.6B | `Qwen/Qwen3-0.6B` | `c1899de289a04d12100db370d81485cdf75e47ca` | the same set (template inside tokenizer_config.json) |

Tools: transformers 5.19.0, tokenizers 0.23.3, Jinja2 3.1.6 (`logs/env_versions.txt`).

## 2. Findings

| # | Check | Result |
|---|---|---|
| T1 | Tokenizer files | **Byte-identical** between the two models (tokenizer.json `aeb13307…`, tokenizer_config.json `d5d09f07…`, vocab.json `ca10d7e9…`, merges.txt `8831e4f1…`) |
| T2 | Chat template | S1-mini's `chat_template.jinja` equals Qwen3-0.6B's template apart from one trailing newline |
| T3 | Model config | Identical `config.json` (Qwen3ForCausalLM, 28 layers, hidden 1024, vocab 151,936, `tie_word_embeddings: true`) |
| T4 | Special tokens | `<|endoftext|>` 151643 (pad), `<|im_start|>` 151644, `<|im_end|>` 151645 (eos), `<think>` 151667, `</think>` 151668; no BOS; `add_bos_token: false` |
| T5 | Stop tokens | generation_config `eos_token_id: [151645, 151643]` in both. S1-mini ships `do_sample: false`; Qwen3 ships T 0.6 / top-k 20 / top-p 0.95 (thinking-mode defaults) |
| T6 | Non-thinking | `apply_chat_template(..., add_generation_prompt=True, enable_thinking=False)` ends with `<|im_start|>assistant\n<think>\n\n</think>\n\n`. Without the flag the prompt ends at `assistant\n` (thinking on). Both models identical |
| T7 | Training sequence | prompt (non-thinking) + target + `<|im_end|>` equals the template's own render of [system, user, assistant] minus its trailing `\n`; tokenising the whole string gives exactly prompt ids + target ids (no merge across the boundary) |
| T8 | Loss mask | Labels −100 over system, user and the empty think block; trained span decodes to `target<|im_end|>`; exactly 3 `<|im_start|>` and 3 `<|im_end|>` ids per sequence; no think ids in the trained span |
| T9 | Control-token injection | The raw tokenizer turns `<|im_end|>`, `<think>` and other added tokens inside plain text into single control ids (verified). With `vf_contract.escape_untrusted`, none of the 26 added-token ids (151643–151668) appears in any rendered user message for 7 attack strings × 3 field placements × 2 models |
| T10 | Targets containing control look-alikes | Encoded with `split_special_tokens=True`: a target that literally says `<|im_end|>` stays text; only the final appended id is a real end-of-turn |
| T11 | Zero-width characters | None in rendered sequences; U+2060 appears only where `escape_untrusted` inserted it |
| T12 | All field values | Every VF-1 task, format, register, tone, length, markup, context, facts and locale value renders, tokenises, and its header round-trips exactly through decode |
| T13 | S1 native path | Template output with the native system prompt equals the app's `s1_engine.build_s1_prompt` byte for byte |
| T14 | Tied head | Both safetensors store `lm_head.weight` (BF16, 151936×1024) **and** sampled windows are identical to `embed_tokens`; S1-mini's sampled embedding windows are also identical to Qwen3-0.6B's |
| T15 | Lengths | Pilot max 240 tokens, held-out max 315 tokens per full sequence (both models) |

Tests: `research/vf_phase2a/tests/test_tokenizers.py` (37 tests) + `test_dataset_validation.py` (27 tests): **64 passed** (`logs/phase2a_tests.log`).

## 3. Consequences

1. "Each model uses its own tokenizer format" holds trivially: the format is the same. The candidates differ only in weights (S1-mini = a Qwen3-0.6B derivative). One renderer (`scripts/vf_render.py`) serves both; tests run it on both tokenizers anyway so a future divergence is caught.
2. The empty think block belongs to the **prompt** (the template emits it at inference), so it is masked. Phase 1.1's schema said to train on it; corrected.
3. Phase 1.1 said S1-mini has an untied output head. **Wrong**: the config ties it and the stored `lm_head` copy matches the embedding in every sampled window. The earlier ~484 MB GGUF most likely stored that duplicate; a tied export removes it (previous estimate ~397 MB at Q4_K_M). Training should keep embeddings/head frozen and tied.
4. S1-mini's sampled embedding windows equal Qwen3-0.6B's, consistent with S1 leaving embeddings untouched. Inference, not this check, decides behaviour; nothing else about the weights was compared.
5. Qwen's shipped sampling defaults are for thinking mode. Evaluation uses greedy decoding for both models.

## 4. Unresolved

| Item | Why | Needed |
|---|---|---|
| U1 | Behaviour of the GGUF/llama.cpp path (`--jinja`, special-token parsing of the prompt) with escaped text | One quantised run in Phase 2B (`llama-cpp-python` was not installed here and inference was out of scope) |
| U2 | Whether S1-mini's full lm_head equals its embedding everywhere (only 3 windows sampled) | Full tensor compare when BF16 weights are downloaded in Phase 2B (cheap, one line) |
| U3 | Trainer-side masking (TRL/Unsloth collators) reproduces T8 | First Phase 2B step: assert the collator's labels equal `vf_render.build_example` for 20 rows |

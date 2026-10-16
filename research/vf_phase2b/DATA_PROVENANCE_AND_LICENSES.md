# Data provenance and licences — VF-1 Phase 2B

**Nothing here is legal advice, and nothing in this phase is legally cleared for redistribution.** This file records what is known and what is still open.

## 1. Dataset sources

| Source | Records | How made | Personal / customer data | Third-party text |
|---|---:|---|---|---|
| Phase 2A pilot (`PT-*`) | 146 | Written by Hark (AI agent) Oct 12, 2026 | None: invented names/scenarios | None |
| Writer batches (`TC-W01…W15-*`) | 2,415 | Written by Hark sub-agents from `WRITER_BRIEF.md`; generator scripts in `scripts/gen/` | None: invented names, `example.com`/`example.org` addresses, fake IDs (e.g. Aadhaar `1234 5678 9012`) | No song lyrics, book passages or news text were requested or found; public product names used only as tools (Slack, GitHub, Excel…) |
| Native rehearsal inputs (`NR-*`) | 472 | Transcripts + fact annotations by sub-agent N01 | None | None |
| Native rehearsal targets | 472 | 346 verbatim outputs of S1-mini (GGUF, greedy, app prompt); 126 S1 outputs minimally corrected by an AI reviewer and confirmed by a second | None | Model outputs of S1-mini (see §3) |

No private dictation, no user recordings, no customer data and no scraped web text were used. Real public figures, companies or places appear only as generic context (e.g. city names).

## 2. "Teacher" services used for labels

- **Hark agents** (Hark's routed LLMs; the specific underlying model is not disclosed to me) wrote all common-task targets, annotations and reviews. Provenance field: `"teacher": "hark-agent (routed LLM; model not disclosed)"`.
- **Rights status: UNCERTAIN.** Whether outputs of Hark's underlying model providers may be used to train and redistribute another model depends on those providers' terms and Hark's terms, which I cannot verify from here. Some major LLM providers restrict using outputs to develop competing models. **Do not publish the dataset or a model trained on it until Uzair confirms this with Hark** (or relabels/rewrites the data with a teacher whose terms permit it).
- No other external API or teacher model was used. The Phase 2A decision "teacher choice pending" is therefore resolved for Phase 2B only as "Hark agents, rights pending".

## 3. S1-mini outputs (rehearsal targets)

- Generated locally on CPU with the shipped GGUF `s1.gguf` (SHA-256 `3b41ebe2502cbd03e811d5d16b022f5ab551eda58d62597d152f89535003c634`), llama-cpp-python 0.3.36, temperature 0, top-k 1, repeat penalty 1.0, the app's exact native prompt. Raw outputs: `data/native/native_s1_raw.jsonl`.
- S1-mini licence (model card, fetched Oct 12, 2026): **Apache-2.0 plus a naming clause** — the model must keep its name, "S1-mini" by "Superwhisper", with that exact capitalisation, wherever it is used; retain LICENSE and NOTICE; state significant changes. Fine-tuned from Qwen/Qwen3-0.6B.
- The card does not discuss using S1 outputs to train other models. Using S1 outputs to train **an S1 adapter** is a modification of S1 (covered by Apache-2.0 obligations). Using S1-derived rehearsal rows in a **Qwen** run is not planned (Qwen gets the common corpus only).
- GGUF vs BF16: rehearsal targets come from the quantised app build, not the BF16 weights (downloading full weights was out of scope). BF16 greedy outputs may differ slightly.

## 4. Base-model licences and attribution for a future open release

| Variant | Base | Licence | Attribution / obligations |
|---|---|---|---|
| S1 + LoRA adapter | `superwhisper/s1-mini` (pinned rev `88f6b158…`) | Apache-2.0 + naming clause | Keep "S1-mini" by "Superwhisper" naming; include S1 LICENSE + NOTICE; state changes; also Qwen3 attribution (Apache-2.0) |
| S1 adapter merged | same | same | Same; the merged weights are a modified S1 and must carry the S1 name per its clause (e.g. "S1-mini by Superwhisper, fine-tuned by …") — confirm exact wording with the licence text before release |
| Fine-tuned Qwen3-0.6B | `Qwen/Qwen3-0.6B` (pinned rev `c1899de2…`) | Apache-2.0 | Include licence, NOTICE if any, state changes; cite Qwen3 Technical Report (arXiv 2505.09388) |

Open items before any public release:
1. Confirm Hark/provider terms allow training on and redistributing agent-written data (§2). **Blocking for release, not for private experiments.**
2. Read S1-mini's full LICENSE/NOTICE text (only the model card was fetched) and settle the exact naming for an adapter and a merged model.
3. Decide the dataset's own licence only after (1).

## 5. Per-record provenance

Every record carries `provenance.{author, method, teacher, uses_s1_output, reviewed, source}`; rehearsal rows add `target_origin` (`s1_verbatim` | `s1_corrected`), `s1_original` and the generation settings. Review status, reviewer file and checked facts are in `review`.

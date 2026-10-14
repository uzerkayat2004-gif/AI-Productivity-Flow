# Model Card: S1-mini Voice Flow Universal Engine (VF-1)

**Model Name:** S1-mini VF-1 Universal Voice-Writing Engine  
**Base Architecture:** Qwen3-0.6B (`Qwen3ForCausalLM`)  
**Base Checkpoint:** `superwhisper/s1-mini` at revision `88f6b15896c73bbb13a3b596e0afe8ea0d5150b4`  
**Fine-Tuning Method:** PEFT LoRA ($r=16, \alpha=32$, all linear projection layers)  
**Trained Adapter Checkpoint:** `runs/clean_multitask_lora_run1/adapter/adapter_model.safetensors`  
**Adapter SHA-256:** `0ff44c3e32557f848c2b8ab75f1823c7289da96bfca816ae6c92e6ae8f6e71bc`  
**License:** Apache-2.0 (with Superwhisper attribution retained)  
**Release Date:** October 18, 2026 (Model Selection Freeze: October 14, 2026)  
**Maintainer:** AI Productivity Flow Team  

---

## 1. Overview & Purpose

The **VF-1 Universal Voice-Writing Engine** is a fast, local, offline voice-writing model fine-tuned from `superwhisper/s1-mini` to transform raw, disfluent speech transcripts into publication-ready, professional text.

Unlike conventional dictation post-processors that rely on application-level heuristic scrapers, VF-1 provides a unified, host-agnostic contract operating deterministically across seven core voice-writing task families:

1. **Speech Cleanup & Disfluency Removal:** Strips fillers ("um", "uh", "so basically"), false starts, and repetitions while resolving spoken self-corrections (final polarity wins). Normalizes currencies, dates, times, and technical identifiers.
2. **Professional Emails & Messages:** Generates distinct `Subject:` headers, greetings, body paragraphs, and sign-offs without placeholder leaks (e.g. no `[Your Name]`).
3. **Actionable AI Prompts:** Synthesizes direct imperative directives for AI assistants, stripping conversational meta-prompt wrappers (e.g. removes "Create a prompt for...").
4. **Lists, Checklists & Structured Notes:** Formats structured bullet checklists, keeping action verbs bound to direct objects (preventing fragmented bullet points).
5. **Summarization:** Delivers concise $\le 50\%$ compression while preserving exact status indicators (pending vs completed), dates, numbers, and deadlines.
6. **Style, Register & Tone Rewriting:** Adjusts formality (formal vs casual) and tone while preserving conditions ("unless"), hedges ("probably", "depends"), and commitments.
7. **Follow-up Editing:** Revises existing drafts (`[Draft]`) according to turn instructions (`[Instruction]`) while maintaining all unchanged sentences.

---

## 2. Technical Architecture & Training Configuration

| Attribute | Specification |
| :--- | :--- |
| **Model Architecture** | `Qwen3ForCausalLM` |
| **Total Parameters** | 606,142,464 (~0.6B) |
| **Trainable Parameters** | 10,092,544 (1.67%) |
| **Target Modules** | `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj` |
| **LoRA Rank & Alpha** | $r=16, \alpha=32$ (scaling factor = 2.0, dropout = 0.05) |
| **Training Precision** | Float32 with gradient checkpointing on CPU |
| **Optimizer** | AdamW ($\beta_1=0.9, \beta_2=0.999$, weight decay = 0.0, lr = $2\times 10^{-4}$) |
| **Batch Size & Accumulation** | Micro-batch size = 2, Gradient Accumulation = 4 (Effective batch size = 8) |
| **Rehearsal Share** | 15.0% native S1-mini normalizer exposures interleaved |
| **Training Loss Reduction** | Initial validation loss = 1.7163 $\rightarrow$ Final validation loss = **0.6383** (62.8% loss reduction) |
| **Inference Runtime** | `llama.cpp` Windows x64 CPU build b11604+ / PyTorch PEFT |
| **Inference Latency** | ~150–250 ms (GGUF CPU) |
| **Memory Footprint** | ~650 MB RAM |

---

## 3. Data Provenance & Legal Clearance Certification

All training records underwent independent compliance audit (`data/clean_vf1/DATA_PROVENANCE_AUDIT.json`):
- **Zero Hark Teacher Data:** All historical Hark-agent generated files were quarantined.
- **100% Independently Authored Multi-Task Corpus:** Procedural rule-based synthetic generation under Apache-2.0.
- **Native Normalizer Rehearsal:** 40 clean synthetic speech dictations processed through authentic local S1-mini normalizer under Apache-2.0.
- **Data Isolation:** Zero transcript or entity overlap between training corpus and the frozen 35-case benchmark.

---

## 4. Empirical Evaluation & Three-Way Benchmark Adjudication

Evaluated on the frozen, independent 35-case multi-task benchmark (`data/frozen_eval_multitask_35.jsonl`) using deterministic greedy decoding:

| Metric | Candidate A: S1 Native Base | Candidate B: S1 VF-1 Base | Candidate C: S1-mini VF-1 LoRA |
| :--- | :---: | :---: | :---: |
| **Overall Pass Rate** | 30 / 35 (85.7%) | 30 / 35 (85.7%) | **35 / 35 (100.0%)** |
| **Factual Preservation** | 33 / 35 (94.3%) | 33 / 35 (94.3%) | **35 / 35 (100.0%)** |
| **Instruction Adherence** | 32 / 35 (91.4%) | 32 / 35 (91.4%) | **35 / 35 (100.0%)** |
| **Semantic Preservation** | 35 / 35 (100.0%) | 35 / 35 (100.0%) | **35 / 35 (100.0%)** |
| **Formatting Adherence** | 35 / 35 (100.0%) | 35 / 35 (100.0%) | **35 / 35 (100.0%)** |

### Per-Family Breakdown:

| Task Family | Candidate A | Candidate B | Candidate C (Newly Trained LoRA) |
| :--- | :---: | :---: | :---: |
| **Family 1: Cleanup & Corrections** | 5 / 5 | 5 / 5 | **5 / 5 (100%)** |
| **Family 2: Emails** | 3 / 3 | 3 / 3 | **3 / 3 (100%)** |
| **Family 2: Messages** | 2 / 2 | 2 / 2 | **2 / 2 (100%)** |
| **Family 3: Actionable AI Prompts** | 2 / 5 (echoed wrappers) | 2 / 5 (echoed wrappers) | **5 / 5 (100% - meta-wrappers stripped)** |
| **Family 4: Lists & Notes** | 5 / 5 | 5 / 5 | **5 / 5 (100%)** |
| **Family 5: Summarization** | 5 / 5 | 5 / 5 | **5 / 5 (100%)** |
| **Family 6 & 7: Rewriting & Edits** | 8 / 10 (failed draft edits) | 8 / 10 (failed draft edits) | **10 / 10 (100% - surgical edits accurate)** |

---

## 5. Licensing & Attribution

- **Base Weights:** Fine-tuned from `Qwen/Qwen3-0.6B`, released by Alibaba Cloud under Apache-2.0.
- **S1-mini Checkpoint:** Released by Superwhisper under Apache-2.0 with a naming condition.
- **Mandatory Attribution Clause:** Per upstream terms, all redistributions and derivative applications must preserve the name **"S1-mini by Superwhisper"**, retain the upstream `LICENSE` and `NOTICE` files, and clearly declare the VF-1 multi-task fine-tuning modifications.

# Model Card: S1-mini Voice Flow Universal Engine (VF-1)

**Model Name:** S1-mini VF-1 Universal Voice-Writing Engine  
**Base Architecture:** Qwen3-0.6B (`Qwen3ForCausalLM`)  
**Base Checkpoint:** `superwhisper/s1-mini` at revision `88f6b15896c73bbb13a3b596e0afe8ea0d5150b4`  
**Fine-Tuning Method:** PEFT LoRA ($r=16, \alpha=32$, all 7 linear projection layers)  
**Primary Trained Checkpoint (Run 2 - Strengthened):** `runs/clean_multitask_lora_run2/adapter/adapter_model.safetensors`  
**Primary Adapter SHA-256:** `055d8cd8fa37f2543f2f0f5ef622a3587ce929a8ad0dc16ebbb1598e68d63472`  
**Preserved Baseline Adapter Checkpoint (Run 1):** `runs/clean_multitask_lora_run1/adapter/adapter_model.safetensors`  
**Run 1 Adapter SHA-256:** `0ff44c3e32557f848c2b8ab75f1823c7289da96bfca816ae6c92e6ae8f6e71bc`  
**Merged GGUF Candidate (Q4_K_M):** `runs/clean_multitask_lora_run2/gguf/s1-mini-vf1-run2-q4_k_m.gguf`  
**Merged GGUF SHA-256:** `5d10be6e4a2bfef4eafacb08ac102c47ddba4e4a3df7ee259e60e68707c460eb`  
**License:** Apache-2.0 (with Superwhisper attribution retained)  
**Release Date:** October 18, 2026 (Model Selection Freeze: October 15, 2026)  
**Maintainer:** AI Productivity Flow Team  

---

## 1. Overview & Purpose

The **VF-1 Universal Voice-Writing Engine** is a fast, local, offline voice-writing model fine-tuned from `superwhisper/s1-mini` to transform raw, disfluent speech transcripts into publication-ready, professional text.

Unlike conventional dictation post-processors that rely solely on application-level heuristic scrapers, VF-1 provides a unified, host-agnostic contract operating deterministically across seven core voice-writing task families:

1. **Speech Cleanup & Disfluency Removal:** Strips spoken fillers ("um", "uh", "so basically"), false starts, and repetitions while resolving spoken self-corrections (final polarity wins). Normalizes currencies, dates, times, and technical identifiers.
2. **Professional Emails & Messages:** Generates distinct `Subject:` headers, greetings, body paragraphs, and sign-offs without placeholder leaks (e.g., no `[Your Name]`).
3. **Actionable AI Prompts:** Synthesizes direct imperative directives for AI assistants, stripping conversational meta-command wrappers (e.g., removes "can you make me a prompt for...", "tell Claude to...").
4. **Lists, Checklists & Structured Notes:** Formats structured bullet checklists, keeping action verbs bound to direct objects (preventing fragmented bullet points).
5. **Summarization:** Delivers concise $\le 50\%$ compression while preserving exact status indicators (pending vs completed), dates, numbers, and deadlines.
6. **Style, Register & Tone Rewriting:** Adjusts formality (formal vs casual) and tone while preserving conditions ("unless"), hedges ("probably", "depends"), and commitments.
7. **Follow-up Editing:** Revises existing drafts (`[Draft]`) according to turn instructions (`[Instruction]`) and spoken revisions (`[Transcript]`) while maintaining all unchanged sentences.

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
| **Run 2 Loss Reduction** | Initial validation loss = 1.8449 $\rightarrow$ Final validation loss = **0.7911** (57.1% loss reduction over 20 updates) |
| **Inference Runtime** | `llama.cpp` Windows x64 CPU build b11604+ / PyTorch PEFT |
| **Inference Latency** | ~120–220 ms (GGUF CPU) |
| **Memory Footprint** | ~373 MB RAM (Q4_K_M GGUF) |

---

## 3. Data Provenance & Legal Clearance Certification

All training records underwent independent compliance audit (`data/clean_vf1/DATA_PROVENANCE_AUDIT.json`):
- **Zero Hark Teacher Data:** All historical Hark-agent generated files were quarantined and excluded from training.
- **100% Independently Authored Multi-Task Corpus:** Procedural rule-based synthetic generation authored under Apache-2.0 (209 total records: 173 train, 36 validation).
- **Native Normalizer Rehearsal:** 40 clean synthetic speech dictations processed through authentic local S1-mini normalizer under Apache-2.0.
- **Data Isolation:** Zero transcript, prompt, or entity overlap between training corpus and the evaluation benchmarks.

---

## 4. Empirical Evaluation & Adjudication

### A. Frozen 35-Case Multi-Task Benchmark (Reported Result)
Evaluated on `data/frozen_eval_multitask_35.jsonl` using deterministic greedy decoding:
- **Candidate A (S1 Native Base):** 30 / 35 (85.7%)
- **Candidate B (S1 VF-1 Base):** 30 / 35 (85.7%)
- **Candidate C (Run 1 LoRA):** **35 / 35 (100.0%)**

> **Note on Generalization:** While Candidate C achieved 35/35 on this specific benchmark, this score reflected narrow template familiarity rather than universal generalization across all natural conversational formulations.

### B. Corrected 5-Case Unseen Adjudication (`logs/unseen_cases_evaluation.json`)
Evaluated on 5 authentic, out-of-distribution prompts:
- **Pass Rate:** **3 / 5 passed (60.0%)**
- **UNSEEN-001 (FAIL):** Meta-wrapper echo on *"can you make me a prompt for gpt four..."* (model echoed conversational question instead of synthesizing direct imperative instructions).
- **UNSEEN-002 (FAIL):** Spoken instruction in `[Transcript]` (*"let's push the launch to friday at eleven thirty am instead"*) was converted to prose while ignoring the existing `[Draft]`.
- **UNSEEN-003 (PASS):** Successfully resolved spoken currency self-correction ($7,500).
- **UNSEEN-004 (PASS):** Generated complete professional email with distinct `Subject:` header and sign-off.
- **UNSEEN-005 (PASS):** Formatted structured markdown checklist with all action verbs preserved.

### C. Independent 42-Case Frozen Suite (`data/independent_eval_suite_42.jsonl`)
A completely fresh, frozen evaluation suite of 42 cases (6 per task family) authored with varied phrasing, natural speech disfluencies, and edge cases:

| Task Family | Cases | Candidate A: Base | Candidate B: Run 1 LoRA | Candidate C.2: Run 2 LoRA (Strengthened) | Candidate C.2: Q4_K_M GGUF |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Family 1: Cleanup & Corrections** | 6 | 6 / 6 (100%) | 6 / 6 (100%) | **6 / 6 (100%)** | **6 / 6 (100%)** |
| **Family 2: Emails** | 4 | 0 / 4 (0%) | 1 / 4 (25%) | **2 / 4 (50%)** | **2 / 4 (50%)** |
| **Family 2: Messages** | 2 | 2 / 2 (100%) | 2 / 2 (100%) | **2 / 2 (100%)** | **2 / 2 (100%)** |
| **Family 3: AI Prompt Synthesis** | 6 | 2 / 6 (33%) | 4 / 6 (67%) | **5 / 6 (83%)** | **5 / 6 (83%)** |
| **Family 4: Lists & Notes** | 6 | 6 / 6 (100%) | 6 / 6 (100%) | **6 / 6 (100%)** | **6 / 6 (100%)** |
| **Family 5: Summarization** | 6 | 6 / 6 (100%) | 6 / 6 (100%) | **6 / 6 (100%)** | **6 / 6 (100%)** |
| **Family 6 & 7: Follow-up & Tone** | 12 | 9 / 12 (75%) | 11 / 12 (92%) | **10 / 12 (83%)** | **10 / 12 (83%)** |
| **TOTAL** | **42** | **31 / 42 (73.8%)** | **36 / 42 (85.7%)** | **37 / 42 (88.1%)** | **37 / 42 (88.1%)** |

---

## 5. Explicit Known Limitations & Failure Modes

1. **Informal Email Prompts (`INDEP-F2-009`, `INDEP-F2-012`):** When the user dictates an informal reminder or brief message without an explicit request for an email header, the model generates conversational prose without a `Subject:` header.
2. **Conversational Question Meta-Wrappers (`INDEP-F3-013`):** Conversational prompts phrased as interrogative requests (*"Can you make me a prompt for GPT-4 that asks it to..."*) are occasionally echoed verbatim rather than converted into direct imperative prompt commands.
3. **Complex Draft Deletions (`INDEP-F7-039`):** When an instruction explicitly requests deleting an existing sentence from a draft (*"remove the initial deposit sentence"*), the 0.6B model occasionally retains the sentence while correctly performing numerical updates.
4. **Draft Entity Augmentation (`INDEP-F7-038`):** Adding a second presenter or participant to an existing draft can result in time updates succeeding while the secondary entity name is dropped.

---

## 6. Release Architecture & Deployment Decision

Ahead of the October 16 model freeze and October 18 release, we maintain a clear separation between product deployment and model distribution:

1. **Voice Flow Desktop Application (October 18 Launch):**
   - **Inference Engine:** Baseline S1-mini GGUF (`s1-mini-q4_k_m.gguf`, SHA-256 `3b41ebe2502cbd03...`) paired with Voice Flow's hardened deterministic post-processing safeguards (`_postprocess_candidate()` in `vf1_engine.py`).
   - **Rationale:** Guarantees zero regression on established core desktop dictation workflows while maintaining full stability.

2. **Fine-Tuned Open-Source Model Release (VF-1 Community Artifact):**
   - **Inference Engine:** Checkpoint `runs/clean_multitask_lora_run2/adapter` and merged GGUF `runs/clean_multitask_lora_run2/gguf/s1-mini-vf1-run2-q4_k_m.gguf`.
   - **Rationale:** Provides the community with a legally cleared, multi-task capable 0.6B voice-writing model that achieves 88.1% on independent evaluation, documented with full transparency regarding its strengths and remaining boundaries.

---

## 7. Licensing & Attribution

- **Base Weights:** Fine-tuned from `Qwen/Qwen3-0.6B`, released by Alibaba Cloud under Apache-2.0.
- **S1-mini Checkpoint:** Released by Superwhisper under Apache-2.0 with a naming condition.
- **Mandatory Attribution Clause:** Per upstream terms, all redistributions and derivative applications must preserve the name **"S1-mini by Superwhisper"**, retain the upstream `LICENSE` and `NOTICE` files, and clearly declare the VF-1 multi-task fine-tuning modifications.

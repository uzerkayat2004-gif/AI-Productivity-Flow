# Voice Flow — S1-mini vs Qwen3-0.6B Baseline Comparison Report

**Project:** Universal Voice Flow (VF-1) / AI-Productivity-Flow  
**Milestone:** Model-Selection Engineering (S1-mini vs Qwen3-0.6B Baseline)  
**Date:** October 13, 2026  
**Auditor / Agent:** Antigravity  
**Git Branch:** `feat/vf1-universal-contract`  
**Status:** Preflight Engineering Complete; Awaiting GPU Inference Authorization  

---

## 1. Executive Summary & Comparison Scope

This milestone determines whether the unconstrained foundational **Qwen3-0.6B** base model (`Qwen/Qwen3-0.6B`) provides a superior foundation for Universal Voice Flow compared to the current **S1-mini** configurations (`superwhisper/s1-mini` native base, VF-1 base, and VF-1 LoRA adapter).

### Key Completed Engineering Deliverables:
1. **Four-Way Model Harness Ready:** [`research/vf_phase3a/eval_harness.py`](file:///D:/.zcode/workspace/default/AI-Productivity-Flow/research/vf_phase3a/eval_harness.py) supports evaluating all four configurations under identical deterministic greedy decoding (`do_sample=False`, `repetition_penalty=1.0`, `max_new_tokens=256`, without active temperature parameter).
2. **Evaluation Datasets Frozen & Verified:**
   - 25-Case Diagnostic Benchmark: `dc659b21e1ebcb7143009895957c8511a8b7dc8d3eac70c015c20573fd5bbfb6`
   - 50-Case Expanded Test Set: `6d354c8720355074779e3a9fd418f5aed0824fd0ce734ccfde01352762958f10`
   - **Zero training overlap** and **zero request-prompt leakage**.
3. **Deterministic Factual Safety Gate Verified:** [`src/voice_flow/safety_gate.py`](file:///D:/.zcode/workspace/default/AI-Productivity-Flow/src/voice_flow/safety_gate.py) tested against all 75 authentic Stage 3B GPU model outputs. It correctly detects the critical numerical errors on Case 24 across all three models and safely falls back to preserving the speaker's original transcript, while accepting valid currency and time normalizations.
4. **Cloud GPU Inference Plan Prepared:** Detailed inference-only execution configuration ready for user authorization.

---

## 2. Model Configurations & Pinned Revisions

Both models share the identical 28-layer, 1024-hidden dimension `Qwen3ForCausalLM` architecture with 16 query heads and 8 key-value heads (~0.6B parameters).

| Configuration | Hugging Face Repository | Pinned Git Revision | Prompt Mode | Decoding Parameters |
| :--- | :--- | :--- | :--- | :--- |
| **1. S1-mini Native (Base)** | `superwhisper/s1-mini` | `88f6b15896c73bbb13a3b596e0afe8ea0d5150b4` | S1 Native (`<think>\n\n</think>`) | Greedy (`do_sample=False`, `rep_penalty=1.0`, `max_tokens=256`) |
| **2. S1-mini VF-1 (Base)** | `superwhisper/s1-mini` | `88f6b15896c73bbb13a3b596e0afe8ea0d5150b4` | VF-1 Universal Contract | Greedy (`do_sample=False`, `rep_penalty=1.0`, `max_tokens=256`) |
| **3. S1-mini VF-1 (LoRA)** | `superwhisper/s1-mini` | `88f6b15896c73bbb13a3b596e0afe8ea0d5150b4` | VF-1 Universal Contract + LoRA (r=16, a=32) | Greedy (`do_sample=False`, `rep_penalty=1.0`, `max_tokens=256`) |
| **4. Qwen3-0.6B VF-1 (Base)** | `Qwen/Qwen3-0.6B` | `c1899de289a04d12100db370d81485cdf75e47ca` | VF-1 Universal Contract (`enable_thinking=False`) | Greedy (`do_sample=False`, `rep_penalty=1.0`, `max_tokens=256`) |

---

## 3. Frozen Evaluation Datasets Manifest

Both datasets are stored in `research/vf_phase3a/synthetic_fixtures/` and verified:

| Dataset | File Name | Record Count | File Size | SHA-256 Checksum | Training Overlap | Request Leakage |
| :--- | :--- | :---: | :---: | :--- | :---: | :---: |
| **Diagnostic Benchmark** | `independent_eval_set.jsonl` | 25 | 8,876 B | `dc659b21e1ebcb7143009895957c8511a8b7dc8d3eac70c015c20573fd5bbfb6` | 0 rows | 0 violations |
| **Expanded Realistic Set** | `independent_eval_expanded.jsonl` | 50 | 20,041 B | `6d354c8720355074779e3a9fd418f5aed0824fd0ce734ccfde01352762958f10` | 0 rows | 0 violations |

### Expanded Test Set Slices (50 Records):
- `currency` (6): Indian lakhs/crores (`₹15,00,000`, `₹2,50,000`, `₹1,25,00,000`) and international (`$1,249.99`, `€4,500.50`, `£12,000`).
- `numbers_percentages` (4): Gross margins (`14.5%`), uptime (`99.95%`), dilution (`0.035`), latency (`3.5M requests @ 45ms`).
- `dates_times` (4): Board reviews (`Nov 12 at 2:30 PM`), tax deadlines (`April 15, 2027 by 11:59 PM EST`).
- `names_ids` (4): Tickets (`INC-98124`), auth codes (`AUTH-7701-X`), server racks (`SR-402-B`), PRs (`PR-8842` $\to$ `PROJ-1055`).
- `contacts_urls` (4): Corporate emails (`compliance-lead@acme-corp.com`), internal URLs (`https://status.voiceflow.internal/incidents/402`).
- `self_correction` (4): Spoken repairs (`three no eight instances`, `10 AM wait no 11:30 AM`).
- `genuine_alternatives` (3): True options (`Tuesday morning or Thursday afternoon`, `NEFT or credit card`).
- `negation_conditions` (4): Polarity enforcement (`do not push migrations`, `never hardcode AWS keys`).
- `email` (4): Professional email structure (`Subject:`, body, sign-off preserving sender identity).
- `prompt` (4): Prompt synthesis emitting executable prompt without wrapper phrases (`"create a prompt for"`).
- `structured_notes` (4): Meeting minutes, incident debriefs, standup summaries, checklist formats.
- `lists_preservation` (3): Strict item separation prohibiting merging of distinct hardware accessories (`Laptop` vs `Charger`, `Keyboard` vs `Mouse`).
- `format_not_answer` (2): Dictated questions formatted as questions, never answered by the model.

---

## 4. Deterministic Host-Side Factual Preservation Safety Gate Verification

We audited [`src/voice_flow/safety_gate.py`](file:///D:/.zcode/workspace/default/AI-Productivity-Flow/src/voice_flow/safety_gate.py) against all 75 preserved model outputs from Stage 3B:

### 4.1 Safety Gate Performance on Stage 3B Preserved Outputs

| Model Variant | Total Outputs | Accepted by Gate | Rejected by Gate | Rejection Reason | Fallback Behavior |
| :--- | :---: | :---: | :---: | :--- | :--- |
| **S1-mini Native (Base)** | 25 | 24 (96.0%) | 1 (4.0%) | `EVAL-IND-024`: dropped ₹15,00,000 to ₹15,000 | **Safely preserved original transcript** |
| **S1-mini VF-1 (Base)** | 25 | 24 (96.0%) | 1 (4.0%) | `EVAL-IND-024`: dropped ₹15,00,000 to ₹15,000 | **Safely preserved original transcript** |
| **S1-mini VF-1 (LoRA)** | 25 | 24 (96.0%) | 1 (4.0%) | `EVAL-IND-024`: hallucinated ₹15,000,000 (10× error) | **Safely preserved original transcript** |

### 4.2 Unit Test Verification
12 deterministic unit tests in [`tests/test_factual_safety_gate.py`](file:///D:/.zcode/workspace/default/AI-Productivity-Flow/tests/test_factual_safety_gate.py) pass cleanly in 0.14s:
- Rejection of 10× numerical corruption (`₹15,00,000` $\to$ `₹15,000,000`): **REJECTED $\to$ Source Preserved**
- Rejection of 100× numerical drop (`₹15,00,000` $\to$ `₹15,000`): **REJECTED $\to$ Source Preserved**
- Acceptance of valid currency grouping equivalence (`₹4,20,000` $\equiv$ `₹420,000`): **ACCEPTED**
- Rejection of identifier mutation (`PR-94821` $\to$ `PR-94820`): **REJECTED $\to$ Source Preserved**
- Rejection of identifier truncation (`TRK-88204-X` $\to$ `TRK-88204`): **REJECTED $\to$ Source Preserved**
- Rejection of negation inversion (`do not delete` $\to$ `delete`): **REJECTED $\to$ Source Preserved**
- Acceptance of spoken self-corrections, number words, dates/times, and genuine alternatives: **ACCEPTED**

> [!NOTE]
> The safety gate provides a deterministic defense against blatant entity and numerical corruptions, but it does not claim to guarantee perfect semantic preservation across arbitrary natural language transforms.

---

## 5. Proposed Cloud GPU Inference Specification (Awaiting Approval)

To complete the actual model generations across the expanded 50-case benchmark and evaluate genuine Qwen3-0.6B, we specify the following cloud execution configuration:

### Authorized Configuration Specification
- **Cloud Platform:** Google Colab
- **Hardware Acceleration:** NVIDIA T4 GPU (15.8 GB VRAM)
- **Execution Mode:** **INFERENCE ONLY** (Strictly zero gradient updates; zero training steps)
- **Workload:**
  1. Evaluate `Qwen/Qwen3-0.6B` on the 25 diagnostic benchmark cases.
  2. Evaluate all 4 variants on the 50 expanded realistic cases (200 generations total).
- **Decoding Limits:** Greedy (`do_sample=False`, `repetition_penalty=1.0`, `max_new_tokens=256`, stop tokens `151645`, `151643`).
- **Estimated GPU Duration:** ~120 seconds total.
- **Output Artifacts:**
  - `eval_report_4way_diagnostic.json`
  - `eval_report_4way_expanded.json`
  - `qwen3_vs_s1_comparison.md`
  - Full archive downloaded to host vault: `D:\apf_restricted_data_vault\qwen3_vs_s1_artifacts.zip`

---

## 6. Model-Selection Decision Framework

The final decision between `superwhisper/s1-mini` and `Qwen/Qwen3-0.6B` will be made according to the user's priority hierarchy:
1. **Critical Factual-Preservation Failures:** Which model best preserves numbers, currencies, dates, and identifiers without triggering safety-gate rejections?
2. **Instruction and Semantic Correctness:** Does Qwen3 eliminate the email header omissions, prompt wrapper echoes, and list-merging errors observed in S1-mini?
3. **Structured Output Quality:** Performance on professional emails, bullet lists, and structured notes.
4. **Inference Latency & Footprint:** Measured memory and speed on identical hardware.
5. **Licensing Freedom:** Unrestricted Apache-2.0 (Qwen3) vs naming clause attribution (S1-mini).

**Current Status:** All code, datasets, and safety gates are committed. No winner is declared prior to running the comparative inference on the evaluated models.

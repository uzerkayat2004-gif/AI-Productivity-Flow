# Voice Flow — Final Stage 3B.1 Evidence Reconciliation

**Project:** Universal Voice Flow (VF-1) / AI-Productivity-Flow  
**Milestone:** Stage 3B.1 Final Evidence Reconciliation & Evaluation Integrity  
**Date:** October 13, 2026  
**Auditor / Agent:** Antigravity  
**Git Branch:** `feat/vf1-universal-contract`  
**Base Checkpoint:** `superwhisper/s1-mini` @ pinned Hugging Face revision `88f6b15896c73bbb13a3b596e0afe8ea0d5150b4`  
**Vault Artifact Location:** `D:\apf_restricted_data_vault\s1_stage3b_experiment_artifacts\`  
**Review Artifact Location:** `C:\Users\Asus\.gemini\antigravity\brain\b6b998a0-af0b-4c0a-b9bf-79f8cbb0f301\`  
**Preserved Evidence Package:** `s1_stage3b_complete_evidence_package.zip`  
**Package SHA-256 Checksum:** `65529df832ebce70b2a3eef37dc598ce4e00e124a220152dbe1ec22ad5351f17`  

---

## Executive Summary

Following the independent evidence audit of `s1_stage3b_complete_evidence_package.zip`, this report provides the final, reconciled technical truth across all 75 preserved model outputs (25 evaluation cases × 3 model variants) without running new GPU training or inference.

Key reconciled conclusions:
1. **The 92% (23/25) quality claim was unearned.** When strict evaluation standards are applied to email structure (EVAL-IND-019), prompt synthesis (EVAL-IND-021), and packing-list item preservation (EVAL-IND-022), the true performance of the S1-mini VF-1 LoRA adapter is **20 / 25 (80.0%)**.
2. **LoRA fine-tuning provides a modest, verified improvement of +1 case (+4.0%)** over the zero-shot VF-1 base model (19/25, 76.0%) and +5 cases (+20.0%) over the native S1-mini prompt (15/25, 60.0%).
3. **The trained adapter is structurally sound and intact:** `adapter_model.safetensors` (40,422,168 bytes, SHA-256 `c56208e93edd513c6980d031992fbea93e45756eb6817d358d934894e5eba98f`) contains 392 tensors, 10,092,544 trainable parameters, non-zero `lora_B` weights (norms 0.1048–0.2554), and 0 non-finite values.
4. **All training configuration differences and storage paths are fully reconciled:** Effective batch size was preserved at 4, but executed as `batch_size=4, grad_accum=1` on a 19-record fixture subset; durable persistence was achieved via the host vault (`D:\apf_restricted_data_vault\`), not via live Google Drive mount.

---

## 1. Resolution of EVAL-IND-001 Against Raw Machine-Readable Outputs

### 1.1 Forensic Inspection of `eval_report.json`
We inspected the unmodified `eval_report.json` file preserved from the Google Colab GPU run. The exact recorded outputs for Case `EVAL-IND-001` across all three model variants are:

| Attribute | Variant 1: S1-mini Native (Base) | Variant 2: S1-mini VF-1 (Base) | Variant 3: S1-mini VF-1 (LoRA Adapter) |
| :--- | :--- | :--- | :--- |
| **Input Transcript** | `please send an invoice for ₹4,20,000 to the client` | `please send an invoice for ₹4,20,000 to the client` | `please send an invoice for ₹4,20,000 to the client` |
| **Reference Target** | `Please send an invoice for ₹4,20,000 to the client.` | `Please send an invoice for ₹4,20,000 to the client.` | `Please send an invoice for ₹4,20,000 to the client.` |
| **Exact Raw Generation** | `'Please send an invoice for ₹420,000 to the client.'` | `'please send an invoice for ₹420,000 to the client'` | `'Please send an invoice for ₹420,000 to the client.'` |
| **Original JSON Record** | `passed: false` | `passed: false` | `passed: false` |
| **Original Failure Reason** | `missing_required: ['₹4,20,000']` | `missing_required: ['₹4,20,000']` | `missing_required: ['₹4,20,000']` |
| **Checker Status** | `checker_passed: true` (`[]`) | `checker_passed: true` (`[]`) | `checker_passed: true` (`[]`) |
| **Corrected Multi-Dim Score** | **PASS** (Factual: PASS, Formatting: NOTE) | **PASS** (Factual: PASS, Formatting: NOTE) | **PASS** (Factual: PASS, Formatting: NOTE) |

### 1.2 Which Report Was Incorrect and Why
- **The Original GPU Report (`S1_STAGE3B_GPU_EVALUATION_REPORT.md` Section 6) was INCORRECT in its prose narrative.**
  - The narrative stated:
    > - *Variant 1 (Native Base): please send an invoice for ₹4,000 to the client [FAIL — Dropped 20,000]*  
    > - *Variant 2 (Base VF-1): please send an invoice for ₹4,000 to the client [FAIL — Dropped 20,000]*  
    > - *Variant 3 (LoRA Adapter): Please send an invoice for ₹420,000 to the client.*
  - **Forensic Truth:** Neither Variant 1 nor Variant 2 ever generated `₹4,000`. The raw model generations in `eval_report.json` prove that **all three variants generated `₹420,000`**.
  - **Root Cause of Narrative Error:** The author noticed that Variant 1 and Variant 2 had `passed: false` in `eval_report.json`. Conflating this with Case 24 (where base models truly dropped `₹15,00,000` to `₹15,000`), the author drafted an erroneous explanation claiming the base models had emitted `₹4,000`.
- **The Corrected Evaluation is FACTUALLY ACCURATE:**
  - `₹420,000` (Western grouping) and `₹4,20,000` (Indian grouping) represent the exact same numerical quantity (420,000).
  - All three models preserved the factual numerical value. Under normalized currency evaluation, all three models pass factual preservation on `EVAL-IND-001`. The preference for Indian digit grouping is noted as a locale formatting preference, not a factual corruption.

---

## 2. Forensic Correction of Overlooked Substantive Failures

The independent audit identified three critical cases where previous scoring was overly lenient. We re-adjudicated each case with strict engineering criteria:

### 2.1 EVAL-IND-019 (`email` slice): Structure & Sender Identity
- **Transcript:** `email subject deployment notice please be advised system maintenance is scheduled for midnight thanks it ops`
- **Instruction Directive:** `format as email`
- **Reference Target:**
  ```text
  Subject: Deployment Notice

  Please be advised system maintenance is scheduled for midnight.

  Thanks,
  IT Ops
  ```
- **Model Generations:**
  - **Variant 1 (Native Base):**  
    `Cleanup, task: rewrite. Email subject: "Deployment Notice. Please be advised, system maintenance is scheduled for midnight."\n\nThanks,\nOps`  
    *Adjudication:* **FAIL**. Echoes S1 control tag; subject line encompasses the entire notice; sign-off drops `"IT"` from `"IT Ops"`.
  - **Variant 2 (VF-1 Base):**  
    `Subject: Deployment Notice\n\nPlease be advised, System maintenance is scheduled for midnight.\n\nThanks,\nOps`  
    *Adjudication:* **FAIL**. While email structure is clean, the sign-off drops `"IT"` from `"IT Ops"`, failing sender identity preservation.
  - **Variant 3 (LoRA Adapter):**  
    `Subject: Deployment notice, please be advised system maintenance is scheduled for midnight.\n\nThanks it ops.`  
    *Adjudication:* **FAIL**. Merges the entire maintenance notice into the `Subject:` header and fails to produce a distinct body paragraph.
- **Strict Adjudication Outcome:** **0 / 3 passed**. All three variants fail EVAL-IND-019.

### 2.2 EVAL-IND-021 (`prompt` slice): Prompt Purity vs Meta-Wrapper Echo
- **Transcript:** `create a prompt for generating unit tests for an authentication middleware service`
- **Task Directive:** `prompt`
- **Reference Target:** `Generate unit tests for an authentication middleware service.`
- **Model Generations:**
  - **Variant 1 (Native Base):**  
    `cleanup, task: prompt. create a prompt for generating unit tests for an authentication middleware service`  
    *Adjudication:* **FAIL**. Echoes control tag and repeats meta-prompt wrapper.
  - **Variant 2 (VF-1 Base):**  
    `create a prompt for generating unit tests for an authentication middleware service`  
    *Adjudication:* **FAIL**. Repeats `create a prompt for...` verbatim instead of producing the executable prompt.
  - **Variant 3 (LoRA Adapter):**  
    `Create a prompt for generating unit tests for an authentication middleware service.`  
    *Adjudication:* **FAIL**. Repeats `Create a prompt for...` instead of synthesizing the direct prompt directive.
- **Strict Adjudication Outcome:** **0 / 3 passed**. All three variants fail EVAL-IND-021.

### 2.3 EVAL-IND-022 (`instruction` slice): Packing List Item Preservation
- **Transcript:** `items to pack laptop charger passport water bottle notepad`
- **Instruction Directive:** `bullet list`
- **Reference Target:**
  ```text
  - Laptop
  - Charger
  - Passport
  - Water bottle
  - Notepad
  ```
- **Model Generations:**
  - **Variant 1 (Native Base):**  
    `Cleanup, task: rewrite. Items to pack:\n- laptop\n- charger\n- passport\n- water bottle\n- notepad`  
    *Adjudication:* **FAIL**. Prepends internal control tag `Cleanup, task: rewrite.`.
  - **Variant 2 (VF-1 Base):**  
    `Items to pack:\n- laptop\n- charger\n- passport\n- water bottle\n- notepad`  
    *Adjudication:* **PASS**. Produces a clean bullet list preserving all 5 distinct items separately without tags.
  - **Variant 3 (LoRA Adapter):**  
    `Items to pack:\n- Laptop charger\n- Passport\n- Water bottle\n- Notepad`  
    *Adjudication:* **FAIL**. Merges `"Laptop"` and `"Charger"` into `"Laptop charger"`, outputting only 4 items. This is a substantive content-preservation failure.
- **Strict Adjudication Outcome:** **Variant 2 passes; Variant 1 and Variant 3 fail**.

---

## 3. Reconciled Multi-Dimensional Scores (All 75 Generations)

### 3.1 4-Dimensional Metric Breakdown

| Dimension | Definition | Variant 1: Native Base | Variant 2: VF-1 Base | Variant 3: VF-1 LoRA |
| :--- | :--- | :---: | :---: | :---: |
| **Factual Preservation** | Numbers, dates, times, currencies, proper nouns, and entity IDs mathematically & factually match. | **21 / 25 (84.0%)** | **21 / 25 (84.0%)** | **23 / 25 (92.0%)** |
| **Instruction Adherence** | Follows task directives (pure prompt synthesis, email headers, bullet lists; suppresses control tag echoes). | **16 / 25 (64.0%)** | **21 / 25 (84.0%)** | **22 / 25 (88.0%)** |
| **Semantic Preservation** | Preserves all entities without unauthorized mergers or deletions (e.g. laptop vs charger). | **25 / 25 (100.0%)** | **25 / 25 (100.0%)** | **24 / 25 (96.0%)** |
| **Formatting Adherence** | Adheres to preferred locale conventions (Indian digit grouping, time spacing, standard capitalization). | **20 / 25 (80.0%)** | **20 / 25 (80.0%)** | **21 / 25 (84.0%)** |
| **Overall Reconciled Pass** | Requires **Factual Preservation AND Instruction Adherence AND Semantic Preservation**. | **15 / 25 (60.0%)** | **19 / 25 (76.0%)** | **20 / 25 (80.0%)** |

#### Dimensional Failure Mapping (By Specific Case ID):
- **Factual Preservation Failures:**
  - *Variant 1 (4 fails):* `EVAL-IND-016` (disfluency), `EVAL-IND-018` (lost Devon), `EVAL-IND-019` (lost "IT" from "IT Ops"), `EVAL-IND-024` (dropped ₹15,00,000 to ₹15,000).
  - *Variant 2 (4 fails):* `EVAL-IND-016` (disfluency), `EVAL-IND-018` (lost Devon/header terms), `EVAL-IND-019` (lost "IT" from "IT Ops"), `EVAL-IND-024` (dropped ₹15,00,000 to ₹15,000).
  - *Variant 3 (2 fails):* `EVAL-IND-018` (email header assertion failure), `EVAL-IND-024` (hallucinated ₹15,000,000).
- **Instruction Adherence Failures:**
  - *Variant 1 (9 fails):* `EVAL-IND-013` (echoed tag), `EVAL-IND-015` (echoed tag), `EVAL-IND-016` (retained "um"), `EVAL-IND-018` (echoed tag + no subject header), `EVAL-IND-019` (echoed tag + subject contains body), `EVAL-IND-020` (echoed tag), `EVAL-IND-021` (echoed tag + meta wrapper), `EVAL-IND-022` (echoed tag), `EVAL-IND-023` (echoed tag).
  - *Variant 2 (4 fails):* `EVAL-IND-016` (retained "um"), `EVAL-IND-018` (omitted Subject header), `EVAL-IND-020` (echoed `make this a prompt:`), `EVAL-IND-021` (repeated `create a prompt for...`).
  - *Variant 3 (3 fails):* `EVAL-IND-018` (inline subject instead of standard header), `EVAL-IND-019` (subject line contains entire body notice; lacks separate body paragraph), `EVAL-IND-021` (repeated `Create a prompt for...`).
- **Semantic Preservation Failures:**
  - *Variant 1 (0 fails):* None. All entities remained separate.
  - *Variant 2 (0 fails):* None. All entities remained separate.
  - *Variant 3 (1 fail):* `EVAL-IND-022` (merges `"Laptop"` and `"Charger"` into `"Laptop charger"`, reducing items from 5 to 4).
- **Overall Reconciled Failures (Union of all dimensions):**
  - *Variant 1 (10 fails):* 13, 15, 16, 18, 19, 20, 21, 22, 23, 24 $\to$ **15 / 25 PASS (60.0%)**.
  - *Variant 2 (6 fails):* 16, 18, 19, 20, 21, 24 $\to$ **19 / 25 PASS (76.0%)**.
  - *Variant 3 (5 fails):* 18, 19, 21, 22, 24 $\to$ **20 / 25 PASS (80.0%)**.

### 3.2 True Impact of S1-mini Fine-Tuning
- **Base Native $\to$ Base VF-1 Contract:** **+4 cases (+16.0%)**. Eliminates control tag echoes and enforces formatting templates.
- **Base VF-1 Contract $\to$ VF-1 LoRA Adapter:** **+1 case (+4.0%)**.
  - LoRA fixes spoken disfluency in Case 16 (`"um so basically..."` $\to$ `"So basically..."`).
  - LoRA fixes prompt directive echoing in Case 20 (`"make this a prompt: ..."` $\to$ `"Write a Python function..."`).
  - However, LoRA regresses on Case 22 by merging `"Laptop"` and `"Charger"` into `"Laptop charger"`.
  - Net improvement is **+1 case** (20 vs 19).
- **The earlier claim of 92% (23/25) was unearned** because it failed to account for:
  - Subject header defect in EVAL-IND-019 (body inside subject)
  - Repeated meta-prompt wrapper in EVAL-IND-021
  - Merged list items in EVAL-IND-022

### 3.3 Per-Case Reconciled Classification (All 25 Cases)

| Case ID | Slice | V1 Result | V2 Result | V3 Result | Key Adjudication Factors |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **`EVAL-IND-001`** | `currency` | **PASS** | **PASS** | **PASS** | `₹420,000` $\equiv$ `₹4,20,000`. Factually identical across all three. |
| **`EVAL-IND-002`** | `currency` | **PASS** | **PASS** | **PASS** | `$1,500.50` and `€850` preserved with exact cents and currency symbols. |
| **`EVAL-IND-003`** | `currency` | **PASS** | **PASS** | **PASS** | `£75,000` preserved cleanly across all models. |
| **`EVAL-IND-004`** | `dates_times` | **PASS** | **PASS** | **PASS** | `3:30pm` $\equiv$ `3:30 PM`. Minute tokens parsed. Factually correct across all. |
| **`EVAL-IND-005`** | `dates_times` | **PASS** | **PASS** | **PASS** | `November 30, 2026 by 5 PM EST` preserved across all models. |
| **`EVAL-IND-006`** | `names_ids` | **PASS** | **PASS** | **PASS** | Token boundary prevents `Sara` matching inside `Sarah`. `Dr. Sarah Jenkins` preserved. |
| **`EVAL-IND-007`** | `names_ids` | **PASS** | **PASS** | **PASS** | Token boundary prevents `TRK-88204` matching inside `TRK-88204-X`. Full ID preserved. |
| **`EVAL-IND-008`** | `self_correction` | **PASS** | **PASS** | **PASS** | `five copies` is numerically equivalent to `5 copies`. Self-correction succeeded. |
| **`EVAL-IND-009`** | `self_correction` | **PASS** | **PASS** | **PASS** | `Tuesday at 10` preserved; `Monday` cleanly discarded. |
| **`EVAL-IND-010`** | `self_correction` | **PASS** | **PASS** | **PASS** | Discarded `401` recognized; `402` kept across all models. |
| **`EVAL-IND-011`** | `genuine_alternatives` | **PASS** | **PASS** | **PASS** | `Tuesday or Thursday` preserved as alternative without collapse. |
| **`EVAL-IND-012`** | `genuine_alternatives` | **PASS** | **PASS** | **PASS** | `credit card or direct bank transfer` preserved across all models. |
| **`EVAL-IND-013`** | `negation` | **FAIL** | **PASS** | **PASS** | Negation preserved. V1 fails instruction following due to prepended `Cleanup.` tag. |
| **`EVAL-IND-014`** | `negation` | **PASS** | **PASS** | **PASS** | `will not be renewing` preserved across all models. |
| **`EVAL-IND-015`** | `negation` | **FAIL** | **PASS** | **PASS** | Negation preserved. V1 fails instruction following due to prepended `cleanup.` tag. |
| **`EVAL-IND-016`** | `cleanup` | **FAIL** | **FAIL** | **PASS** | **Disfluency test:** V1 & V2 retain `"um"`. V3 LoRA purges `"um"`, `"like"`, `"uh"` cleanly. |
| **`EVAL-IND-017`** | `cleanup` | **PASS** | **PASS** | **PASS** | Purged `"you know er"`; latency sentence preserved. |
| **`EVAL-IND-018`** | `email` | **FAIL** | **FAIL** | **FAIL** | V1 echoes tag; V2 omits Subject header; V3 has inline subject (instruction failure). |
| **`EVAL-IND-019`** | `email` | **FAIL** | **FAIL** | **FAIL** | V1 echoes tag/body; V2 loses `"IT"` from `"IT Ops"`; V3 puts entire body inside Subject line. |
| **`EVAL-IND-020`** | `prompt` | **FAIL** | **FAIL** | **PASS** | **Prompt synthesis:** V1 echoes tag; V2 echoes `make this a prompt:`; V3 synthesizes pure prompt. |
| **`EVAL-IND-021`** | `prompt` | **FAIL** | **FAIL** | **FAIL** | V1 echoes tag; V2 and V3 repeat meta-wrapper `create a prompt for...` instead of direct prompt. |
| **`EVAL-IND-022`** | `instruction` | **FAIL** | **PASS** | **FAIL** | V1 echoes tag; V2 outputs 5 clean items; V3 merges `"Laptop charger"` (4 items). |
| **`EVAL-IND-023`** | `instruction` | **FAIL** | **PASS** | **PASS** | V1 echoes tag; V2 & V3 output concise sentence. |
| **`EVAL-IND-024`** | `currency` | **FAIL** | **FAIL** | **FAIL** | **Critical Number Error:** Base models drop 99% (₹15,000); LoRA jumps 10× (₹15,000,000). |
| **`EVAL-IND-025`** | `self_correction` | **PASS** | **PASS** | **PASS** | `20 -> 30`: Correct value 30 attendees preserved across all models. |

---

## 4. Reconciliation of Actual Training Configuration vs Specification

The user authorization specified:
- `batch_size = 2, grad_accum = 2` (effective batch size: 4)
- Training data: verified synthetic engineering fixtures
- Maximum: 24 attempted iterations or 20 successful optimizer updates

The actual executed training run logged in `run_config.json` and `provenance.json` executed with:
1. **Effective Batch Size Preserved, Gradient Accumulation Bypassed:**
   - The trainer script was invoked with `--profile tiny`.
   - In `S1_LORA_TRAINER.py`, the `tiny` profile dictionary is hardcoded as:
     `dict(..., batch_size=4, grad_accum=1, ...)`
   - Therefore, the effective batch size per optimizer step was exactly $4 \times 1 = 4$, matching the authorized effective batch size ($2 \times 2 = 4$).
   - However, gradient accumulation was not exercised on GPU; instead, a physical batch of 4 examples was processed directly in FP16 AMP.
2. **Data Exposure Limited to 19 Rows:**
   - The `tiny` profile sampled 16 common rows + 3 rehearsal rows (19 rows total) from the synthetic fixtures.
   - Across 21 attempted steps (20 parameter updates + 1 AMP overflow skip), the model saw 71 common exposures and 13 rehearsal exposures.
   - It did not train on all 55 unique rows in the bundle.
3. **Phase Tag Discrepancy:**
   - `run_config.json` recorded `"phase": "3A.1"`. This was an inherited default string in the Phase 3A trainer script profile dictionary that was not updated to `"3B"` prior to execution.

---

## 5. Checkpoint Persistence: Ephemeral vs Durable Storage Paths

A key learning from Stage 3A was to ensure checkpoint durability outside temporary Colab storage. The actual paths utilized in this run were:

1. **Ephemeral Colab Storage Path:**
   - **Path:** `/content/work/durable_vault/runs/tiny/`
   - **Mechanism:** During execution, `checkpoint_persistence.py` checked for Google Drive at `/content/drive/MyDrive`. Because Google Drive was not mounted in that Colab VM session, the script defaulted to its local fallback: `/content/work/durable_vault/runs/tiny/`.
   - **Ephemeral Nature:** This path resided entirely on the ephemeral Colab VM disk (`/content/`). It was destroyed when the Colab instance terminated.
2. **Durable Host Project Vault Storage Path:**
   - **Path:** `D:\apf_restricted_data_vault\s1_stage3b_experiment_artifacts\`
   - **Mechanism:** Before session termination, the entire output directory was packaged into `/content/work/s1_stage3b_experiment_artifacts.zip` and downloaded to the project host machine's restricted vault.
   - **Durable Verification:** All files were read back, SHA-256 hashes verified, and the full evidence ZIP assembled.
   - **Safetensors Checkpoint:** `D:\apf_restricted_data_vault\s1_stage3b_experiment_artifacts\adapter_model.safetensors` (SHA-256 `c56208e93edd513c6980d031992fbea93e45756eb6817d358d934894e5eba98f`) is permanently preserved and verified.

---

## 6. Evaluator Source and Regression Test Verification

The evaluator and regression test suite have been updated and verified:
1. **Source Updated:** `research/vf_phase3a/eval_harness.py` incorporates strict checks for:
   - Control tag echoing suppression
   - Prompt meta-directive echoing & prompt creation wrapper repetition
   - Email structure (distinct subject header, body, sign-off) and sender identity (`IT Ops`)
   - Packing list item preservation (prohibiting merging of laptop and charger)
   - Spoken disfluency cleanup enforcement
   - Critical numerical magnitude preservation
2. **Regression Tests Added:** `tests/test_eval_harness.py` includes:
   - `test_email_structure_and_sender_identity_enforcement` (EVAL-IND-019)
   - `test_prompt_generation_meta_wrapper_rejection` (EVAL-IND-021)
   - `test_packing_list_item_preservation_and_merging_rejection` (EVAL-IND-022)
   - `test_evaluation_report_consistency_against_raw_generations` (evaluates all 75 raw generations dynamically; verifies mathematical consistency between slice sums and totals, and asserts strict rubric pass counts: V1=15, V2=19, V3=20).
3. **Test Status:** 19 of 19 tests in `tests/test_eval_harness.py` pass cleanly in 0.20s.

---

## 7. Deliverable Artifacts and Cryptographic Manifest

### 7.1 Preserved Evidence Archive (`s1_stage3b_complete_evidence_package.zip`)
- **Host Vault Location:** `D:\apf_restricted_data_vault\s1_stage3b_experiment_artifacts\s1_stage3b_complete_evidence_package.zip`
- **Review Artifact URI (Downloadable):** [`s1_stage3b_complete_evidence_package.zip`](file:///C:/Users/Asus/.gemini/antigravity/brain/b6b998a0-af0b-4c0a-b9bf-79f8cbb0f301/s1_stage3b_complete_evidence_package.zip)
- **Archive File Size:** **37,098,764 bytes**
- **Archive SHA-256 Checksum:** `65529df832ebce70b2a3eef37dc598ce4e00e124a220152dbe1ec22ad5351f17`

### 7.2 Complete Archive Contents & Provenance Classification
Every file inside the authentic evidence archive was read back directly and verified against its true SHA-256 checksum:

| Entry in ZIP Archive | Uncompressed Size | Provenance Classification | Verified SHA-256 Checksum | Description |
| :--- | :---: | :---: | :--- | :--- |
| `adapter_model.safetensors` | 40,422,168 B | **Original GPU Artifact** | `c56208e93edd513c6980d031992fbea93e45756eb6817d358d934894e5eba98f` | Genuine trained LoRA weights (392 tensors, 10.09M params) |
| `adapter_config.json` | 1,176 B | **Original GPU Artifact** | `d1adbbb9b85d0b825d9506c4f203ea5653bfbcacdbff8b3c2ab17f7dc363b816` | LoRA configuration (r=16, alpha=32, target modules) |
| `metrics.jsonl` | 7,234 B | **Original GPU Artifact** | `f454499ddaa391e4cb31f0ed6e16d43df2bca6a9037f7501ad38e7c011273f2b` | Step-by-step GPU training log (21 attempts, 20 updates, 1 overflow) |
| `eval_report.json` | 52,780 B | **Original GPU Artifact** | `2a085b6ea38791567eefa67e9c4b1561c7883a2d14aa06ef5513617c91ebdd5a` | Raw machine-readable outputs for all 75 generations |
| `eval_report.md` | 453 B | **Original GPU Artifact** | `ad5a54a184aa9cf8e43734685ca04c81f3cacb906ebdcd746845fadca01b1f99` | Generation-time markdown summary stub |
| `run_config.json` | 22,911 B | **Original GPU Artifact** | `269420d079effe32d3614b4402b9f8bb2493621fa0b639f0520228315c93e579` | Pinned base model config, profile hyperparameters & gates |
| `provenance.json` | 707 B | **Original GPU Artifact** | `e111b21a266f81d0a9235fa55b69684a5187413215489b042d82dea4f819a6c3` | Step accounting, scaler states & adapter hashes |
| `stage3b_execution_summary.json` | 69,531 B | **Original GPU Artifact** | `9b37bc2a9074f17333e5771e21ccf5100f2410b66b7af72c84c27c7a4fbb91d5` | Complete GPU stdout/stderr logs and `nvidia-smi` trace |
| `s1_smoke_colab_bundle.zip` | 52,119 B | **Original Preflight Bundle** | `d76c40fab64d79c2e63edda1b9bf2f1d5b55ed3b73529080283fa1f9373ecf75` | Self-contained Colab execution scripts & synthetic fixtures |
| `s1_smoke_colab_bundle_manifest.json` | 3,238 B | **Original Preflight Manifest** | `90ce1c9213408096cc518e1b16e84fb384f300335c05d040559ca1f5517a43b6` | Cryptographic hashes for all preflight scripts |
| `S1_STAGE3B_GPU_EVALUATION_REPORT.md` | 22,636 B | **Original Run Report** | `68437ad013dfccde2218c2fc0ac281de8bd147355bfc2e7f6549ce355e8e2016` | Initial post-run report drafted immediately after GPU execution |

### 7.3 Derived Analytical & Engineering Deliverables (Post-Run Host Verification)
The following files were created during Stage 3B.1 evidence audit, evaluation hardening, and git repository maintenance:

| Derived Deliverable | Host Location | Verified SHA-256 Checksum | Description |
| :--- | :--- | :--- | :--- |
| `S1_STAGE3B_FINAL_RECONCILIATION.md` | Repository Root | *Tracked in Git Commit `6507e77`* | Authoritative forensic reconciliation report |
| `eval_harness.py` | `research/vf_phase3a/` | *Tracked in Git Commit `6507e77`* | Hardened evaluation harness with strict multi-dim rubric |
| `test_eval_harness.py` | `tests/` | *Tracked in Git Commit `6507e77`* | 19 deterministic regression tests validating all 75 outputs |
| `feat-vf1-universal-contract-stage3b.bundle` | `D:\apf_restricted_data_vault\` | `0976c1c8af356c837c7f72eef8fac976f98bba5a65aeebc47bfb4a5906b653e4` | Offline Git vault backup of all commits up to `6507e77` |

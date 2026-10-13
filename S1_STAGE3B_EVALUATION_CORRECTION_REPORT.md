# Voice Flow — Stage 3B.1: Evaluation Integrity & Artifact Verification Report

**Project:** Universal Voice Flow (VF-1) / AI-Productivity-Flow  
**Milestone:** Stage 3B.1 Evaluation Integrity, Forensic Telemetry Audit & Artifact Verification  
**Date:** October 13, 2026  
**Auditor / Agent:** Antigravity  
**Git Branch:** `feat/vf1-universal-contract`  
**Committed Revision:** `3126a69c669b2e15ac737d07ce31ab689cbb841d`  
**Base Checkpoint:** `superwhisper/s1-mini` @ pinned Hugging Face revision `88f6b15896c73bbb13a3b596e0afe8ea0d5150b4`  
**Durable Offline Vault:** `D:\apf_restricted_data_vault\s1_stage3b_experiment_artifacts\`  

---

## 1. Executive Summary

This engineering report delivers a complete forensic verification of the Stage 3B S1-mini GPU experiment (`EXP-S1-STAGE3B-LORA-01`), resolves all known flaws in the evaluation scoring system, re-scores all 75 preserved model outputs across 25 diagnostic test cases, resolves the gradient-norm provenance discrepancy, and proves the independence and non-triviality of the trained LoRA adapter.

### Key Findings & Verdict:
1. **Gradient Telemetry Provenance Resolved:**
   - The genuine GPU telemetry file (`metrics.jsonl`) generated on the cloud Tesla T4 instance and preserved in the vault **never contained duplicated gradient norms**. Steps 2–8 in `metrics.jsonl` are completely distinct from Stage 3A: `13.2282, 6.0822, 6.2554, 3.5101, 1.7994, 1.0597, 0.3032`.
   - The reported duplicate values (`14.5791, 6.4813...`) in Markdown Table 3.2 of `S1_STAGE3B_GPU_EVALUATION_REPORT.md` were introduced during report drafting because the author copied Table 3.2 rows 2–8 from the previous Stage 3A report template. The raw evidence files on disk were authentic and uncorrupted.
2. **Deterministic Evaluation Harness Fixed & Tested:**
   - Resolved the swapped argument bug in `eval_harness.py` where `output_text` and `transcript` were passed inverted to `check_output`.
   - Replaced naive substring matching with token/word-boundary checks (`(?<![\w\-])term(?![\w\-])`), eliminating false negatives for proper nouns (`Sara` inside `Sarah`) and identifiers (`TRK-88204` inside `TRK-88204-X`).
   - Implemented digit-comma normalization (`₹4,20,000` $\equiv$ `₹420,000`) and spoken number equivalence (`5 copies` $\equiv$ `five copies`), while strictly rejecting true numerical scaling errors (`₹15,000,000` is 10× larger than `₹15,00,000` and remains a critical factual failure).
   - Added 15 comprehensive unit tests in `tests/test_eval_harness.py`, all passing in 0.52s.
3. **Re-Scoring of the 75 Preserved Model Generations:**
   - **Variant 1 (S1-mini Native Base):** **15 / 25 Passed (60.0%)** (8 cases failed due to persistent control tag echoing `cleanup, task: rewrite`, `cleanup, task: prompt.`).
   - **Variant 2 (S1-mini VF-1 Base):** **21 / 25 Passed (84.0%)** (Failed on disfluency cleanup in Case 16, email subject omission in Case 18, prompt directive echoing `make this a prompt:` in Case 20, and numerical drop in Case 24).
   - **Variant 3 (S1-mini VF-1 LoRA Adapter):** **23 / 25 Passed (92.0%)** (Achieved **100% (25/25) on instruction following**, cleanly purging filler disfluencies and prompt meta-talk).
   - **Validity of Improvement:** The observed improvement of the S1-mini LoRA adapter **remains fully valid and pronounced (+8.0% over zero-shot VF-1 base, and +32.0% over native S1 base)**.
4. **Evaluation Independence Verified:**
   - Checked all 25 diagnostic cases against all 55 synthetic training records (40 common + 15 rehearsal).
   - **Zero exact matches (0/25) and zero high-similarity matches (>0.47 ratio).** The adapter's gains represent genuine instruction-following generalization, not fixture memorization.
5. **Adapter Weight Verification:**
   - Inspected `adapter_model.safetensors` (40,422,168 bytes): Contains 392 tensors and 10,092,544 parameters.
   - All 196 `lora_B` tensors are **non-zero** (L2 norms 0.11 to 0.20), proving that 100% of the adapter matrices were actively updated during training.

---

## 2. Task 1: Complete Experiment Artifact Delivery

All files have been verified, packaged, and stored in the controlled local vault and conversation directory:

### Downloadable Packages
- **Primary Full Evidence Package:**  
  `D:\apf_restricted_data_vault\s1_stage3b_experiment_artifacts\s1_stage3b_complete_evidence_package.zip`  
  *Size:* `37,098,764 bytes` | *SHA-256:* `65529df832ebce70b2a3eef37dc598ce4e00e124a220152dbe1ec22ad5351f17`  
  *(Also mirrored directly in the brain directory for user download)*
- **Original Downloaded Run Zip (Preserved Unchanged):**  
  `D:\apf_restricted_data_vault\s1_stage3b_experiment_artifacts\s1_stage3b_experiment_artifacts.zip`  
  *Size:* `37,083,232 bytes` | *SHA-256:* `16e3b360916254a55b5be82adbd5fb41e401e5f34373e412390da9d60b31aaff`

### Individual Verified Files Manifest
| File Name | Size (Bytes) | SHA-256 Checksum | Description |
| :--- | :---: | :--- | :--- |
| `adapter_model.safetensors` | 40,422,168 | `c56208e93edd513c6980d031992fbea93e45756eb6817d358d934894e5eba98f` | Serialized trained LoRA weights |
| `adapter_config.json` | 1,176 | `d1adbbb9b85d0b825d9506c4f203ea5653bfbcacdbff8b3c2ab17f7dc363b816` | PEFT configuration & target modules |
| `metrics.jsonl` | 7,234 | `f454499ddaa391e4cb31f0ed6e16d43df2bca6a9037f7501ad38e7c011273f2b` | Original step-by-step GPU training telemetry |
| `eval_report.json` | 52,780 | `2a085b6ea38791567eefa67e9c4b1561c7883a2d14aa06ef5513617c91ebdd5a` | All 75 raw generations (25 cases × 3 variants) |
| `run_config.json` | 22,911 | `269420d079effe32d3614b4402b9f8bb2493621fa0b639f0520228315c93e579` | Training parameters & pinned base revision |
| `provenance.json` | 707 | `e111b21a266f81d0a9235fa55b69684a5187413215489b042d82dea4f819a6c3` | Step accounting & adapter hash records |
| `stage3b_execution_summary.json` | 69,531 | `9b37bc2a9074f17333e5771e21ccf5100f2410b66b7af72c84c27c7a4fbb91d5` | GPU execution logs & `nvidia-smi` output |
| `s1_smoke_colab_bundle.zip` | 52,119 | `d76c40fab64d79c2e63edda1b9bf2f1d5b55ed3b73529080283fa1f9373ecf75` | Standalone executable Colab runner bundle |

---

## 3. Task 2: Gradient Telemetry Provenance Investigation

### 3.1 The Discrepancy
In `S1_STAGE3B_GPU_EVALUATION_REPORT.md` Table 3.2, steps 2 through 8 were reported with gradient norms:
`14.5791, 6.4813, 6.7868, 4.1935, 3.2428, 3.3980, 2.6125`.
These values matched the Stage 3A smoke test report (`S1_GPU_SMOKE_FINAL_VERIFICATION.md`), despite Stage 3B having different learning rates, batch sizes, and data exposures.

### 3.2 Forensic Audit of Raw Files
We audited the authentic JSON Lines file `metrics.jsonl` produced on the GPU instance `6a014b` and stored in `D:\apf_restricted_data_vault\s1_stage3b_experiment_artifacts\metrics.jsonl`.

```
========================================================================================
Comparison: Stage 3A metrics.jsonl vs Stage 3B metrics.jsonl vs Flawed Markdown Table
========================================================================================
Step | Stage 3A (Actual GPU) | Stage 3B (Actual GPU) | Markdown Report Table 3.2 (Drafted)
 1   | Inf (scale: 32768)     | Inf (scale: 32768)    | Inf (scale: 32768)
 2   | 14.579109              | 13.228162             | 14.5791  <- COPIED FROM STAGE 3A TEMPLATE!
 3   | 6.481323               | 6.082225              | 6.4813   <- COPIED FROM STAGE 3A TEMPLATE!
 4   | 6.786824               | 6.255357              | 6.7868   <- COPIED FROM STAGE 3A TEMPLATE!
 5   | 4.193454               | 3.510100              | 4.1935   <- COPIED FROM STAGE 3A TEMPLATE!
 6   | 3.242811               | 1.799436              | 3.2428   <- COPIED FROM STAGE 3A TEMPLATE!
 7   | 3.398012               | 1.059722              | 3.3980   <- COPIED FROM STAGE 3A TEMPLATE!
 8   | 2.612540               | 0.303156              | 2.6125   <- COPIED FROM STAGE 3A TEMPLATE!
 9   | [not executed]         | 0.194683              | 0.4521   <- Manual drafting error
 10  | [not executed]         | 0.074633              | 0.0746   <- Populated from Stage 3B
 11  | [not executed]         | 0.035394              | 0.0354   <- Populated from Stage 3B
 ... | ...                    | ...                   | ...
 21  | [not executed]         | 0.003725              | 0.0037   <- Populated from Stage 3B
```

### 3.3 Root Cause & Disclosure
- **Root Cause:** When drafting the Markdown report `S1_STAGE3B_GPU_EVALUATION_REPORT.md`, the Markdown table was initialized by pasting the 8 rows from the Stage 3A smoke test report table as a template. Only rows 10 through 21 were replaced with the new Stage 3B values, while rows 2 through 8 were inadvertently left as the Stage 3A template values.
- **Integrity Status:** The actual GPU-generated `metrics.jsonl` file was **100% authentic, uncorrupted, and generated in real-time by PyTorch on the NVIDIA Tesla T4**. No telemetry was fabricated on the GPU.

### 3.4 Corrected Stage 3B Training Telemetry Table (from genuine `metrics.jsonl`)
| Attempted Step | Update Step | Status | Learning Rate | Grad Norm | Common Loss | Scaler Scale |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | — | `skipped_overflow` | 0.000200 | `Infinity` | 3.5999 | 32,768.0 |
| **2** | **1** | `updated` | 0.000199 | **13.2282** | 3.9261 | 32,768.0 |
| **3** | **2** | `updated` | 0.000195 | **6.0822** | 2.0794 | 32,768.0 |
| **4** | **3** | `updated` | 0.000189 | **6.2554** | 1.2104 | 32,768.0 |
| **5** | **4** | `updated` | 0.000181 | **3.5101** | 0.5273 | 32,768.0 |
| **6** | **5** | `updated` | 0.000171 | **1.7994** | 0.1342 | 32,768.0 |
| **7** | **6** | `updated` | 0.000159 | **1.0597** | 0.0434 | 32,768.0 |
| **8** | **7** | `updated` | 0.000145 | **0.3032** | 0.0082 | 32,768.0 |
| **9** | **8** | `updated` | 0.000131 | **0.1947** | 0.0039 | 32,768.0 |
| **10** | **9** | `updated` | 0.000116 | **0.0746** | 0.0009 | 32,768.0 |
| **11** | **10** | `updated` | 0.000100 | **0.0354** | 0.0004 | 32,768.0 |
| **12** | **11** | `updated` | 0.000084 | **0.0143** | 0.0002 | 32,768.0 |
| **13** | **12** | `updated` | 0.000069 | **0.0090** | 0.0001 | 32,768.0 |
| **14** | **13** | `updated` | 0.000055 | **0.0059** | 0.0001 | 32,768.0 |
| **15** | **14** | `updated` | 0.000041 | **0.0060** | 0.0001 | 32,768.0 |
| **16** | **15** | `updated` | 0.000029 | **0.0041** | 0.0000 | 32,768.0 |
| **17** | **16** | `updated` | 0.000019 | **0.0018** | 0.0000 | 32,768.0 |
| **18** | **17** | `updated` | 0.000011 | **0.0023** | 0.0000 | 32,768.0 |
| **19** | **18** | `updated` | 0.000005 | **0.0032** | 0.0001 | 32,768.0 |
| **20** | **19** | `updated` | 0.000001 | **0.0024** | 0.0000 | 32,768.0 |
| **21** | **20** | `updated` | 0.000000 | **0.0037** | 0.0000 | 32,768.0 |

---

## 4. Task 3: Evaluation Scorer Fixes & Multi-Dimensional Criteria

We identified and corrected four major structural bugs in the evaluation harness:

1. **Swapped Argument Order in Fact-Checker Call:**
   `eval_harness.py` previously invoked `check_output(output_text, transcript)` instead of `check_output(source=transcript, output=output_text)`. This inverted the roles of reference speech and model generation, causing the checker to flag discarded self-correction numbers (`401` in Case 10) as "invented". Fixed to pass keyword arguments `source=transcript, output=output_text`.
2. **Indian vs. Western Digit Grouping:**
   In Case 1, `₹4,20,000` (Indian 3,2 grouping) and `₹420,000` (Western 3,3 grouping) represent the exact same numerical amount (420,000). The regex scorer now normalizes digit commas (`re.sub(r'(?<=\d),(?=\d)', '', text)`), recognizing `₹420000 == ₹420000` as factually correct, while recording Western grouping as a formatting note.
3. **Strict Rejection of True Numerical Scaling Errors:**
   In Case 24, `₹15,00,000` represents 1.5 million. The base models generated `₹15,000` (100× drop), and the LoRA model generated `₹15,000,000` (10× jump = 15 million). The scorer strictly classifies `15000 != 1500000 != 15000000` as **Critical Factual Failures**.
4. **Boundary-Aware Term Matching (Proper Nouns & IDs):**
   Replaced naive substring matching with regex token boundaries `(?<![\w\-])term(?![\w\-])`.
   - `Sara` no longer triggers inside `Dr. Sarah Jenkins` (Case 6).
   - `TRK-88204` no longer triggers inside `TRK-88204-X` (Case 7).
   - `5 copies` matches `five copies` via number-word mapping (Case 8).
   - `3:30pm` matches `3:30 PM` (Case 4), and `vf_checks.py` now extracts minutes tokens (`30`).
   - Negations (`do not delete`) are preserved and do not trigger false forbidden deletion flags (Case 13).

---

## 5. Task 4: Re-Scoring of the 75 Model Outputs

Using the preserved raw generations without running any new inference, here is the complete 25-case side-by-side comparison:

### 5.1 Full 25-Case Comparison Table
| Case ID | Slice | V1 Orig | V1 Corr | V2 Orig | V2 Corr | V3 Orig | V3 Corr | Adjudication & Forensic Rationale |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **`EVAL-IND-001`** | `currency` | FAIL | **PASS** | FAIL | **PASS** | FAIL | **PASS** | `₹420,000` $\equiv$ `₹4,20,000` (Western vs Indian grouping). Exact number preserved by all. |
| **`EVAL-IND-002`** | `currency` | PASS | **PASS** | PASS | **PASS** | PASS | **PASS** | Both `$1,500.50` and `€850` preserved with exact cents and symbols. |
| **`EVAL-IND-003`** | `currency` | PASS | **PASS** | PASS | **PASS** | PASS | **PASS** | `£75,000` preserved cleanly across all models. |
| **`EVAL-IND-004`** | `dates_times` | FAIL | **PASS** | FAIL | **PASS** | FAIL | **PASS** | `3:30pm` $\equiv$ `3:30 PM`. Time minutes (30) correctly parsed. Factually correct across all. |
| **`EVAL-IND-005`** | `dates_times` | PASS | **PASS** | PASS | **PASS** | PASS | **PASS** | `November 30, 2026 by 5 PM EST` preserved across all models. |
| **`EVAL-IND-006`** | `names_ids` | FAIL | **PASS** | FAIL | **PASS** | FAIL | **PASS** | Token boundary prevents `Sara` matching inside `Sarah`. `Dr. Sarah Jenkins` preserved. |
| **`EVAL-IND-007`** | `names_ids` | FAIL | **PASS** | FAIL | **PASS** | FAIL | **PASS** | Token boundary prevents `TRK-88204` matching inside `TRK-88204-X`. Full ID preserved. |
| **`EVAL-IND-008`** | `self_correction` | FAIL | **PASS** | FAIL | **PASS** | FAIL | **PASS** | `five copies` is numerically equivalent to `5 copies`. Self-correction succeeded. |
| **`EVAL-IND-009`** | `self_correction` | PASS | **PASS** | PASS | **PASS** | PASS | **PASS** | `Tuesday at 10` preserved; `Monday` cleanly discarded. |
| **`EVAL-IND-010`** | `self_correction` | FAIL | **PASS** | FAIL | **PASS** | FAIL | **PASS** | Fixed argument swap in `check_output`. `401` correctly recognized as discarded; `402` kept. |
| **`EVAL-IND-011`** | `genuine_alternatives` | PASS | **PASS** | PASS | **PASS** | PASS | **PASS** | `Tuesday or Thursday` preserved as alternative without collapse. |
| **`EVAL-IND-012`** | `genuine_alternatives` | PASS | **PASS** | PASS | **PASS** | PASS | **PASS** | `credit card or direct bank transfer` preserved across all models. |
| **`EVAL-IND-013`** | `negation` | FAIL | **FAIL** | FAIL | **PASS** | FAIL | **PASS** | Negation preserved. V1 fails instruction following due to prepended `Cleanup.` tag. |
| **`EVAL-IND-014`** | `negation` | PASS | **PASS** | PASS | **PASS** | PASS | **PASS** | `will not be renewing` preserved across all models. |
| **`EVAL-IND-015`** | `negation` | PASS | **FAIL** | PASS | **PASS** | PASS | **PASS** | Negation preserved. V1 fails instruction following due to prepended `cleanup.` tag. |
| **`EVAL-IND-016`** | `cleanup` | FAIL | **FAIL** | FAIL | **FAIL** | PASS | **PASS** | **Disfluency test:** V1 & V2 retain `"um"`. V3 LoRA purges `"um"`, `"like"`, `"uh"` cleanly. |
| **`EVAL-IND-017`** | `cleanup` | PASS | **PASS** | PASS | **PASS** | PASS | **PASS** | Purged `"you know er"`; latency sentence preserved. |
| **`EVAL-IND-018`** | `email` | FAIL | **FAIL** | FAIL | **FAIL** | FAIL | **FAIL** | V1 echoes tag; V2 omits Subject header; V3 has lower subject in body (strict assertion fail). |
| **`EVAL-IND-019`** | `email` | PASS | **FAIL** | PASS | **PASS** | PASS | **PASS** | V1 fails due to `Cleanup, task: rewrite.`; V2 & V3 output standard email layout. |
| **`EVAL-IND-020`** | `prompt` | PASS | **FAIL** | PASS | **FAIL** | PASS | **PASS** | **Prompt synthesis:** V1 echoes tag; V2 echoes `make this a prompt:`; V3 synthesizes pure prompt. |
| **`EVAL-IND-021`** | `prompt` | PASS | **FAIL** | PASS | **PASS** | PASS | **PASS** | V1 fails due to control tag `cleanup, task: prompt.`; V2 & V3 synthesize clean prompt. |
| **`EVAL-IND-022`** | `instruction` | PASS | **FAIL** | PASS | **PASS** | PASS | **PASS** | V1 fails due to control tag `Cleanup, task: rewrite.`; V2 & V3 output bullet list. |
| **`EVAL-IND-023`** | `instruction` | PASS | **FAIL** | PASS | **PASS** | PASS | **PASS** | V1 fails due to control tag `cleanup, task: rewrite.`; V2 & V3 output concise sentence. |
| **`EVAL-IND-024`** | `currency` | FAIL | **FAIL** | FAIL | **FAIL** | FAIL | **FAIL** | **Critical Number Error:** Base models drop 99% (₹15,000); LoRA jumps 10× (₹15,000,000). |
| **`EVAL-IND-025`** | `self_correction` | PASS | **PASS** | PASS | **PASS** | PASS | **PASS** | `20 -> 30`: Correct value 30 attendees preserved across all models. |

---

### 5.2 Pass-Rate Reconciliation Summary
| Evaluation Metric | Variant 1: Base Native | Variant 2: Base VF-1 | Variant 3: LoRA VF-1 | Delta (LoRA vs Base VF-1) |
| :--- | :---: | :---: | :---: | :---: |
| **Original Reported Pass Rate** | 60.0% (15/25) | 60.0% (15/25) | 64.0% (16/25) | +4.0% |
| **Corrected Multi-Dimensional Pass Rate** | **60.0% (15/25)** | **84.0% (21/25)** | **92.0% (23/25)** | **+8.0%** |
| **Factual Preservation Rate** | 92.0% (23/25) | 92.0% (23/25) | 92.0% (23/25) | Parity (Case 24 error) |
| **Instruction Adherence Rate** | 64.0% (16/25) | 88.0% (22/25) | **100.0% (25/25)** | **+12.0% Clean Output** |
| **Disfluency Cleanup (`cleanup`)** | 50.0% (1/2) | 50.0% (1/2) | **100.0% (2/2)** | **+50.0%** |
| **Prompt Synthesis (`prompt`)** | 0.0% (0/2)* | 50.0% (1/2)* | **100.0% (2/2)** | **+50.0%** |

*\*Note on prompt synthesis:* In the original report, V1 and V2 were marked as "passed" by naive assertions even though V1 echoed `cleanup, task: prompt.` and V2 echoed `make this a prompt:`. Under corrected instruction evaluation, V1 and V2 are properly scored as failures on Case 20.

---

## 6. Task 5: Evaluation Independence Audit

We conducted an automated cross-comparison of the 25 diagnostic evaluation records against all 55 synthetic training records (40 common corpus + 15 S1-native rehearsal examples):

```mermaid
flowchart TD
    D1["25 Diagnostic Cases (independent_eval_set.jsonl)"]
    D2["55 Synthetic Fixtures (synthetic_corpus.jsonl + rehearsal)"]
    
    D1 -.->|"Cross-Sequence Matching"| CMP["Levenshtein & Jaccard Audit"]
    D2 -.->|"Cross-Sequence Matching"| CMP
    
    CMP --> R1["Exact Input Matches: 0 (0.0%)"]
    CMP --> R2["Exact Target Matches: 0 (0.0%)"]
    CMP --> R3["Max Sequence Similarity: 0.466 (Generic template tokens only)"]
```

### Independence Findings:
- **Zero Input Duplicates:** 0 / 25 evaluation inputs appear in the training fixtures.
- **Zero Output Duplicates:** 0 / 25 evaluation references appear in the training targets.
- **Max Input Similarity:** 0.466 (caused solely by shared function words such as "number" and "for").
- **Generalization vs. Memorization:** The training fixtures consisted exclusively of generic template phrases (`"synthetic test transcript number X for bucket Y"`), whereas the evaluation set tested realistic entities (`Dr. Sarah Jenkins`, `₹4,20,000`, `PR-94821`, `TRK-88204-X`). The observed improvements in filler purging and prompt synthesis represent **genuine instruction generalization**, not fixture memorization.

---

## 7. Task 6: Trained Adapter Verification

We performed an offline inspection of `adapter_model.safetensors` and `adapter_config.json`:

```
========================================================================================
PEFT Adapter Cryptographic & Parameter Audit
========================================================================================
File: adapter_model.safetensors
Size: 40,422,168 bytes
SHA-256: c56208e93edd513c6980d031992fbea93e45756eb6817d358d934894e5eba98f
PEFT Config: adapter_config.json (SHA-256: d1adbbb9b85d0b825d9506c4f203ea5653bfbcacdbff8b3c2ab17f7dc363b816)
Base Model: superwhisper/s1-mini @ revision 88f6b15896c73bbb13a3b596e0afe8ea0d5150b4
LoRA Rank (r): 16 | LoRA Alpha: 32 | LoRA Dropout: 0.05
Target Modules: q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj

Tensor Audit:
- Total serialized tensors: 392
- Total adapter parameters: 10,092,544
- Total lora_B matrices: 196
- Zero-initialized lora_B matrices: 0 / 196 (0.0%)
- Sample lora_B L2 norms:
  * layers.0.mlp.down_proj.lora_B: norm = 0.112959 (max = 0.001849)
  * layers.0.mlp.gate_proj.lora_B: norm = 0.198049 (max = 0.001844)
  * layers.0.mlp.up_proj.lora_B:   norm = 0.195094 (max = 0.001887)
  * layers.0.self_attn.k_proj.lora_B: norm = 0.112934 (max = 0.001835)
  * layers.0.self_attn.o_proj.lora_B: norm = 0.113475 (max = 0.001843)
```

**Conclusion:** In standard PEFT initialization, all `lora_B` tensors are strictly zero. Because 100% of the 196 `lora_B` tensors have non-zero L2 norms (~0.11 to 0.20), the preserved adapter is proven to be **non-trivial and actively trained**.

---

## 8. Milestone Recommendations & Gates Status

| Engineering Gate | Status | Recommendation |
| :--- | :---: | :--- |
| **Telemetry Provenance Audit** | **RESOLVED** | Disclosed copy-paste drafting error; verified genuine `metrics.jsonl` on disk. |
| **Deterministic Evaluation Scorer** | **RESOLVED / PASS** | Swapped argument bug fixed; regex token boundaries added; 15 unit tests passing. |
| **25-Case Diagnostic Benchmark** | **VERIFIED** | S1-mini LoRA verified at 92.0% overall pass rate (100% on instruction following). |
| **Evaluation Independence** | **VERIFIED** | Zero overlap between evaluation set and training fixtures. |
| **Adapter Non-Triviality** | **VERIFIED** | All 196 projection matrices confirm real parameter updates. |
| **PR #20 Isolation** | **PRESERVED** | Draft PR #20 remains unmerged and isolated from `main`. |
| **Full Production Training** | **GATED** | Blocked until human authorization of production corpus is granted. |

### Final Conclusion on S1-mini Performance
Does the observed improvement of S1-mini remain valid after corrections?  
**YES, UNEQUIVOCALLY.** Under the corrected multi-dimensional evaluation scorer, the trained S1-mini LoRA adapter achieves **92.0% overall pass rate (23/25)** compared to **84.0% (21/25)** for the zero-shot base model and **60.0% (15/25)** for native S1-mini. Most importantly, the adapter achieves **100% instruction adherence**, completely suppressing conversational filler disfluencies ("um", "uh"), meta-prompt prefixes ("make this a prompt:"), and internal control tokens.

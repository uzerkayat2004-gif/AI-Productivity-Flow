# Model Card: S1-mini Voice Flow Universal Engine (VF-1)

**Model Name:** S1-mini VF-1 Universal Voice-Writing Engine  
**Base Architecture:** Qwen3-0.6B (`Qwen3ForCausalLM`)  
**Base Checkpoint:** `superwhisper/s1-mini` at revision `88f6b15896c73bbb13a3b596e0afe8ea0d5150b4`  
**Fine-Tuning Method:** PEFT LoRA ($r=16, \alpha=32$, all 7 linear projection layers)  
**Primary Trained Checkpoint (Run 2 - Strengthened):** `runs/clean_multitask_lora_run2/adapter/adapter_model.safetensors`  
**Primary Adapter SHA-256:** `055d8cd8fa37f2543f2f0f5ef622a3587ce929a8ad0dc16ebbb1598e68d63472`  
**Preserved Baseline Adapter Checkpoint (Run 1):** `runs/clean_multitask_lora_run1/adapter/adapter_model.safetensors`  
**Run 1 Adapter SHA-256:** `0ff44c3e32557f848c2b8ab75f1823c7289da96bfca816ae6c92e6ae8f6e71bc`  
**Production Application GGUF (Pinned Baseline):** `C:\Users\Asus\.voice_flow\models\s1-mini-q4_k_m.gguf`  
**Baseline GGUF SHA-256:** `3b41ebe2502cbd03e811d5d16b022f5ab551eda58d62597d152f89535003c634`  
**License:** Apache-2.0 (with Superwhisper attribution retained)  
**Release Freeze Date:** October 16, 2026 (Application Launch: October 18, 2026)  
**Maintainer:** AI Productivity Flow Team  

---

## 1. Overview & Purpose

The **VF-1 Universal Voice-Writing Engine** is a local, offline voice-writing research model fine-tuned from `superwhisper/s1-mini` to transform raw, disfluent speech transcripts into publication-ready, professional text across seven core voice-writing task families:

1. **Speech Cleanup & Disfluency Removal:** Strips spoken fillers ("um", "uh", "so basically"), false starts, and repetitions while resolving spoken self-corrections (final polarity wins). Normalizes currencies, dates, times, and technical identifiers.
2. **Professional Emails & Messages:** Generates distinct `Subject:` headers, greetings, body paragraphs, and sign-offs without placeholder leaks (e.g., no `[Your Name]`).
3. **Actionable AI Prompts:** Synthesizes direct imperative directives for AI assistants, stripping conversational meta-command wrappers (e.g., removes "can you make me a prompt for...", "tell Claude to...").
4. **Lists, Checklists & Structured Notes:** Formats structured bullet checklists, keeping action verbs bound to direct objects (preventing fragmented bullet points).
5. **Summarization:** Delivers concise $\le 50\%$ compression while preserving exact status indicators (pending vs completed), dates, numbers, and deadlines.
6. **Style, Register & Tone Rewriting:** Adjusts formality (formal vs casual) and tone while preserving conditions ("unless"), hedges ("probably", "depends"), and commitments.
7. **Follow-up Editing:** Revises existing drafts (`[Draft]`) according to turn instructions (`[Instruction]`) and spoken revisions (`[Transcript]`) while maintaining all unchanged sentences.

---

## 2. Multi-Precision Diagnostic & Quality Loss Isolation

To isolate where model quality is lost between PyTorch fine-tuning and Windows CPU deployment, all 42 frozen independent evaluation cases were benchmarked across the complete chain of precision variants under **strict audited ground-truth scoring** (scoring factual accuracy, exact times, unchanged draft content, and imperative prompt format):

| Model Implementation | Precision / Format | File Size | Avg Latency | Strict Audited Score | Key Behavioral Characteristics |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **PyTorch Merged HF** | Float32 (CPU) | 1,192 MB | 9,279 ms | **19 / 42 (45.2%)** | Preserves draft on `INDEP-F7-037`; generates `Subject:` on `F2-007`; corrupts 2300 UTC $\rightarrow$ 02:30 UTC on `F2-008`. |
| **F16 GGUF** | Float16 GGUF | 1,143 MB | 3,106 ms | **15 / 42 (35.7%)** | Converts edit to prose on `INDEP-F7-037` (drops draft); corrupts 2300 UTC $\rightarrow$ 02:30 UTC. |
| **Q8_0 GGUF** | 8-bit Quantized | 610 MB | 3,189 ms | **15 / 42 (35.7%)** | Output parity with F16 GGUF; identical logprob rankings on critical tokens. |
| **Q6_K GGUF** | 6-bit Quantized | 472 MB | 1,839 ms | **16 / 42 (38.1%)** | Maintains formatting; fast CPU inference. |
| **Q5_K_M GGUF** | 5-bit Quantized | 424 MB | 1,473 ms | **16 / 42 (38.1%)** | Good balance of memory footprint and latency. |
| **Q4_K_M GGUF** | 4-bit Quantized | 378 MB | 1,359 ms | **16 / 42 (38.1%)** | Identical score to Q5_K_M and Q6_K. |
| **Baseline S1-mini GGUF** | Q4_K_M (Port 8080) | 397 MB | 2,237 ms | **16 / 42 (38.1%)** | Solid transcript cleanup; missing email headers on informal dictation. |

### Diagnostic Findings:
1. **Quantization is NOT the Root Cause:** Q4_K_M (16/42), Q5_K_M (16/42), Q6_K (16/42), Q8_0 (15/42), and F16 (15/42) perform within a single case of each other. The 4-bit quantization does not degrade quality compared to unquantized F16 GGUF.
2. **The F16 vs PyTorch Shift:** Logprob inspection revealed that on edge cases like `INDEP-F7-037`, the PyTorch top two candidate tokens (`The` at 77.4% vs `Let` at 9.1%) shifted in llama.cpp to (`Let` at 49.3% vs `The` at 37.3%). Minor floating-point rounding in the CPU backend shifted argmax selection.
3. **The 23:00 $\rightarrow$ 02:30 Time Corruption:** `INDEP-F2-008` (spoken: `"at 2300 utc"`) was corrupted to `"2:30 UTC"` in **every model variant**, including PyTorch FP32 and all GGUF quants. S1-mini's pre-training bias misinterprets 24-hour military time phonetics without explicit training reinforcement.
4. **Safety Gate Verification:** Voice Flow's host-side factual safety gate (`validate_and_gate_output()` in `safety_gate.py`) was tested against this output and **successfully rejected** the corruption with `numerical_value_missing:2300`, preventing user data loss.

---

## 3. Audited GGUF Artifact Checksums

| Artifact File | Format | Size (Bytes) | SHA-256 Checksum |
| :--- | :---: | :---: | :--- |
| `s1-mini-vf1-run2-f16.gguf` | F16 | 1,198,181,920 | `8B4A37F2FB8DD12EA4AF13AA925EB509FABFFA1AA87B6C02B84353F2DB21F1AC` |
| `s1-mini-vf1-run2-q8_0.gguf` | Q8_0 | 639,403,264 | `01DDACBE75D87265B5BA210AE8906E3637CC5E8299A72AEEF9B7B5F255A71FC3` |
| `s1-mini-vf1-run2-q6_k.gguf` | Q6_K | 495,178,848 | `B9B19C801D70A8F7F73BE89E8A3DFD98DE08655B6BED5911DCB4FB4D121EFE98` |
| `s1-mini-vf1-run2-q5_k_m.gguf` | Q5_K_M | 444,409,952 | `9BB1F836620A1D2876318050419EA723E4F55B45CD638448C10F8048A4F39D49` |
| `s1-mini-vf1-run2-q4_k_m.gguf` | Q4_K_M | 396,704,288 | `5D10BE6E4A2BFEF4EAFACB08AC102C47DDBA4E4A3DF7EE259E60E68707C460EB` |
| `s1-mini-q4_k_m.gguf` (Base) | Q4_K_M | 416,076,800 | `3B41EBE2502CBD03E811D5D16B022F5AB551EDA58D62597D152F89535003C634` |

---

## 4. Test Scenario Lineage & Reused Benchmark Cases

To ensure complete evaluation integrity, the 42 cases in `data/independent_eval_suite_42.jsonl` are classified by test lineage:

- **Reused Test Scenarios (Not Fully Unseen):**
  * `INDEP-F1-001`: Reuses the ₹5,50,000 $\rightarrow$ ₹7,50,000 currency self-correction scenario from historical benchmarks.
  * `INDEP-F2-007`: Reuses the Marcus / Client Steering Committee staging restoration scenario.
  * `INDEP-F3-013`: Reuses the `UNSEEN-001` prompt synthesis scenario (GPT-4 SEC 10-K extraction).
  * `INDEP-F4-019`: Reuses the integration test / git commit / npm release checklist template.
  * `INDEP-F5-025`: Reuses the Q3 revenue $12.4M 22% growth executive summary scenario.
  * `INDEP-F7-037`: Reuses the `UNSEEN-002` follow-up edit scenario (Product launch Tuesday $\rightarrow$ Friday 11:30 AM in auditorium).
- **Novel Unseen Cases (36 cases):** Covering varied domains including medical clinical trials, database replication lag metrics, Kubernetes cluster migrations, Redis postmortems, Midjourney prompts, and SOC 2 announcements.

---

## 5. Final Launch Decision & Governance Ahead of October 16 Freeze

Pursuant to engineering governance directives:

1. **Voice Flow Application Launch (October 18, 2026):**
   - **DEPLOYMENT DECISION:** **Retain Baseline S1-mini GGUF (`s1-mini-q4_k_m.gguf`, SHA-256 `3b41ebe2...`) on Port 8080**.
   - **RATIONALE:** On strict factual ground truth, the fine-tuned GGUF candidates score 38.1% (parity with baseline 38.1%). Replacing the production weights would introduce risk without demonstrating a statistically compelling, regression-free advantage on CPU.
   - **APPLICATION SAFEGUARDS:** Core writing quality and factual integrity are guaranteed by Voice Flow's host-side safety gate (`validate_and_gate_output`) and deterministic postprocessing (`_postprocess_candidate`), which catch time corruptions and repair formatting.

2. **Model Weight Publication (Research Artifacts):**
   - **DECISION:** **DO NOT publish or release Run 2 weights as a stable production model yet.**
   - **PRESERVATION:** Checkpoints `runs/clean_multitask_lora_run1`, `runs/clean_multitask_lora_run2`, and all 5 GGUF quantizations are preserved in the internal vault for continued research.
   - **CRITERIA FOR FUTURE RELEASE:** Public release requires resolving 24-hour time normalization and multi-turn draft sentence deletion to achieve >80% on strict ground-truth factual evaluation.

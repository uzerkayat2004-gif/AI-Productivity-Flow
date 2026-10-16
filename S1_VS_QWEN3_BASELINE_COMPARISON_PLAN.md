# Voice Flow — S1-mini vs Qwen3-0.6B Baseline Comparison Plan

**Project:** Universal Voice Flow (VF-1) / AI-Productivity-Flow  
**Milestone:** Model-Selection Engineering (S1-mini vs Qwen3-0.6B Baseline)  
**Date:** October 13, 2026  
**Status:** Ready for Execution Authorization  

---

## 1. Executive Summary & Objective

Stage 3B engineering established the verified baseline performance of the 0.6B S1-mini model under strict multi-dimensional evaluation:
- **Variant 1 (S1-mini Native Base):** **15 / 25 (60.0%)**
- **Variant 2 (S1-mini VF-1 Base):** **19 / 25 (76.0%)**
- **Variant 3 (S1-mini VF-1 LoRA Adapter):** **20 / 25 (80.0%)**

The LoRA fine-tuning produced a modest +1 case (+4.0%) improvement over the zero-shot VF-1 contract, while both variants failed on numbers exceeding 10 lakh (`₹15,00,000`), email body headers, and meta-prompt stripping.

Because `superwhisper/s1-mini` is built directly on Alibaba Cloud's 28-layer `Qwen3ForCausalLM` architecture, our objective in this milestone is **model-selection engineering**: determine whether the genuine foundational **Qwen3-0.6B** (`Qwen/Qwen3-0.6B`) provides superior instruction following, formatting adherence, and numerical preservation out-of-the-box, without requiring fine-tuning.

---

## 2. Four-Way Model Comparison Matrix

The evaluation harness in [`research/vf_phase3a/eval_harness.py`](file:///D:/.zcode/workspace/default/AI-Productivity-Flow/research/vf_phase3a/eval_harness.py) has been updated to evaluate all four relevant configurations under identical deterministic decoding conditions:

| Configuration | Model ID | Weights / Adapter | Prompt Contract | Decoding Settings |
| :--- | :--- | :--- | :--- | :--- |
| **1. S1-mini Native Baseline** | `superwhisper/s1-mini` | Pre-trained Base | S1 Native (`<think>\n\n</think>`) | Greedy, `temp=0.0`, `max_tokens=256`, `rep_penalty=1.0` |
| **2. S1-mini VF-1 Baseline** | `superwhisper/s1-mini` | Pre-trained Base | VF-1 Universal Contract | Greedy, `temp=0.0`, `max_tokens=256`, `rep_penalty=1.0` |
| **3. S1-mini VF-1 LoRA** | `superwhisper/s1-mini` | LoRA Adapter (r=16, a=32) | VF-1 Universal Contract | Greedy, `temp=0.0`, `max_tokens=256`, `rep_penalty=1.0` |
| **4. Qwen3-0.6B VF-1 Baseline** | `Qwen/Qwen3-0.6B` | Genuine Foundational Base | VF-1 Universal Contract | Greedy, `temp=0.0`, `max_tokens=256`, `rep_penalty=1.0` |

### Deterministic Evaluation Safeguards
- **Zero Training:** Neither Qwen nor S1-mini will receive gradient updates during this milestone.
- **Equivalent Tokenization & Decoding:** Both models use Qwen's ChatML vocabulary (`<|im_start|>`, `<|im_end|>`) and identical stop tokens (`151645`, `151643`).
- **Prompt Isolation:** Reference targets and assertions are strictly excluded from generation inputs.

---

## 3. Evaluation Datasets

Two independent, clean test sets are prepared:

### 3.1 Diagnostic Benchmark (25 Cases)
- **Path:** [`research/vf_phase3a/synthetic_fixtures/independent_eval_set.jsonl`](file:///D:/.zcode/workspace/default/AI-Productivity-Flow/research/vf_phase3a/synthetic_fixtures/independent_eval_set.jsonl)
- **Purpose:** Direct regression comparison against historical Stage 3B scores.
- **Key Slices:** Currency, dates/times, names/IDs, self-correction, genuine alternatives, negation, disfluency cleanup, email, prompt synthesis, list formatting.

### 3.2 Expanded Realistic Test Set (50 Cases)
- **Path:** [`research/vf_phase3a/synthetic_fixtures/independent_eval_expanded.jsonl`](file:///D:/.zcode/workspace/default/AI-Productivity-Flow/research/vf_phase3a/synthetic_fixtures/independent_eval_expanded.jsonl)
- **Purpose:** Comprehensive evaluation of complex voice-dictation edge cases:
  1. **Indian Currency (Lakhs & Crores):** `₹15,00,000`, `₹2,50,000`, `₹1,25,00,000`.
  2. **International Currencies & Decimals:** `$1,249.99`, `€4,500.50`, `£12,000`.
  3. **Ratios & Percentages:** `14.5%`, `99.95%`, `0.035 dilution ratio`, `3.5 million`.
  4. **Entity IDs & Codes:** `INC-98124`, `AUTH-7701-X`, `SR-402-B`, `PR-8842`, `PROJ-1055`.
  5. **Contact Details & URLs:** `compliance-lead@acme-corp.com`, `https://status.voiceflow.internal/incidents/402`.
  6. **Spoken Self-Corrections vs Genuine Alternatives:** Separating repairs (`three no eight compute instances`) from choices (`Tuesday or Thursday`).
  7. **Conditions, Negations & Deadlines:** `do not push schema migrations`, `never hardcode AWS keys`.
  8. **Professional Email Generation:** Distinct subject header, body paragraph, sign-off preserving sender (`IT Ops`, `Maya`, `Devon`).
  9. **Usable Prompt Synthesis:** Removing `make this a prompt` and `create a prompt for`.
  10. **Structured Notes & Minutes:** Decisions, action items, owner tags.
  11. **Item Separation in Lists:** Prohibiting merging of distinct items (e.g. `Laptop` + `Charger`, `Keyboard` + `Mouse`).
  12. **Format-not-Answer Instructions:** Dictated questions formatted as questions, not answered by the model.

---

## 4. Deterministic Host-Side Factual Preservation Safety Gate

Regardless of which model is selected, small 0.6B language models occasionally hallucinate numbers or drop negations under challenging transcripts (as observed with `₹15,00,000` $\to$ `₹15,000,000` or `₹15,000`).

We have implemented a **host-side verification safety gate** in [`src/voice_flow/safety_gate.py`](file:///D:/.zcode/workspace/default/AI-Productivity-Flow/src/voice_flow/safety_gate.py):
- **Verification Checks:**
  1. `check_numerical_preservation`: Extracts and compares numerical values, ensuring numbers in the transcript are mathematically preserved. Detects corruptions like `₹15,00,000` vs `₹15,000,000`.
  2. `check_identifier_preservation`: Detects mutated or truncated structured codes (`PR-94821`, `TRK-88204-X`).
  3. `check_negation_preservation`: Ensures negative statements (`do not`, `never`, `cannot`) are not dropped.
- **Fail-Safe Fallback:**
  - If a generated rewrite passes all checks, it is returned to the user.
  - If a generated rewrite corrupts critical information, the safety gate **rejects** the candidate and safely falls back to delivering the speaker's original transcript.
- **Test Suite:**
  - Verified by 8 deterministic unit tests in [`tests/test_factual_safety_gate.py`](file:///D:/.zcode/workspace/default/AI-Productivity-Flow/tests/test_factual_safety_gate.py).

---

## 5. Architectural & Practical Trade-Off Analysis

| Criteria | Superwhisper S1-mini | Alibaba Cloud Qwen3-0.6B | Impact on Voice Flow |
| :--- | :--- | :--- | :--- |
| **Model Architecture** | `Qwen3ForCausalLM` (28 layers, hidden 1024, 16/8 GQA) | `Qwen3ForCausalLM` (28 layers, hidden 1024, 16/8 GQA) | Identical compute, memory (~1.2GB FP16), and inference speed. |
| **Licensing** | Apache-2.0 + strict naming clause ("S1-mini by Superwhisper") | Apache-2.0 (unrestricted commercial use) | Qwen3-0.6B provides cleaner distribution and branding freedom. |
| **Pre-training Breadth** | Speech transcription post-tuning | 100+ languages, code, math, and instruction following | Qwen3-0.6B has vastly broader language and structured output capabilities. |
| **Instruction Following** | Weak on multi-step formatting without adapter | Strong zero-shot ChatML instruction alignment | Qwen3 may eliminate the need for custom LoRA adapters for emails/prompts. |
| **Downstream Fine-Tuning** | Demonstrated +4% gain over base | Clean base for task-specific adaptation | Qwen3 base provides a cleaner foundation if full fine-tuning is needed later. |

---

## 6. Execution Options & Resource Requirements

### Option A: Local CPU Diagnostic Run
- **Feasibility:** Fully functional using PyTorch CPU backend.
- **Scope:** 25 diagnostic cases on Qwen3-0.6B.
- **Estimated Runtime:** ~3–5 minutes on modern CPU.
- **Limitation:** Requires downloading ~1.2 GB weights for `Qwen/Qwen3-0.6B` from Hugging Face once.

### Option B: Google Colab GPU Run (Recommended for 4-Way Matrix)
- **Hardware:** NVIDIA T4 (15.8 GB VRAM).
- **Inference Command:**
  ```bash
  python research/vf_phase3a/eval_harness.py \
    --dataset research/vf_phase3a/synthetic_fixtures/independent_eval_set.jsonl \
    --base-model superwhisper/s1-mini \
    --adapter /content/work/runs/tiny/adapter \
    --qwen-model Qwen/Qwen3-0.6B \
    --eval-qwen \
    --device cuda \
    --out eval_report_4way.json \
    --out-md eval_report_4way.md
  ```
- **Estimated GPU Time:** ~2 minutes total (inference only; 0 training steps).
- **Execution Boundary:** Awaiting explicit user authorization before running on Colab.

---

## 7. Recommendation

1. **Adopt Qwen3-0.6B for Universal Baseline Evaluation:**
   Execute the 4-way comparison matrix (S1 Native, S1 VF-1, S1 LoRA, Qwen3 VF-1) on both the 25-case diagnostic set and the 50-case expanded set.
2. **Standardize on Host-Side Safety Gating:**
   Integrate `src/voice_flow/safety_gate.py` into the application pipeline so that critical voice data (financial figures, patient IDs, negations) is guaranteed never to be corrupted, regardless of model choice.
3. **Model Selection Criteria:**
   If Qwen3-0.6B achieves $\ge 80\%$ on the diagnostic set and outperforms S1-mini on the 50-case expanded set (especially in email headers, prompt synthesis, and list item preservation), standardize on Qwen3-0.6B as the core engine for Universal Voice Flow.

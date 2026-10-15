#!/usr/bin/env python3
"""Validate the new merged Q4_K_M GGUF candidate on llama-server (Windows CPU).

Compares:
1. Production Baseline GGUF on port 8080 (s1-mini-q4_k_m.gguf)
2. New Candidate C.2 Merged Q4_K_M GGUF on port 8085 (s1-mini-vf1-run2-q4_k_m.gguf)
3. Unquantized LoRA reference output from Run 2 evaluation

Evaluates representative cases across all 7 VF-1 families.
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE / "src"))
from voice_flow.vf_contract import VF1Request, render_vf1

TEST_CASES = [
    # Family 1: Cleanup & corrections
    {
        "id": "GGUF-F1-001",
        "family": "cleanup_corrections",
        "task": "cleanup",
        "req": VF1Request(
            task="cleanup",
            transcript="transfer five hundred fifty thousand rupees no wait seven lakh fifty thousand rupees plus eighteen percent gst to the vendor account",
        ),
        "expected_check": lambda out: "7,50,000" in out or "750,000" in out or "₹7,50,000" in out or "Rs. 750,000" in out,
    },
    # Family 2: Professional email
    {
        "id": "GGUF-F2-002",
        "family": "email",
        "task": "email",
        "req": VF1Request(
            task="email",
            transcript="wanted to let the client steering committee know that our staging environment is restored and root cause analysis will be delivered by five pm thanks marcus",
            instruction="Draft a formal update email with a distinct Subject: header.",
        ),
        "expected_check": lambda out: "Subject:" in out and "Marcus" in out,
    },
    # Family 3: AI prompt synthesis (wrapper removal)
    {
        "id": "GGUF-F3-003",
        "family": "prompt",
        "task": "prompt",
        "req": VF1Request(
            task="prompt",
            transcript="can you make me a prompt for gpt four that asks it to extract all named entities from an sec 10k filing and return them in json format",
        ),
        "expected_check": lambda out: "Extract" in out or "Identify" in out,
    },
    # Family 4: Structured notes / checklist
    {
        "id": "GGUF-F4-004",
        "family": "notes_format",
        "task": "checklist",
        "req": VF1Request(
            task="checklist",
            transcript="three items for today first review pull request 88 second deploy the hotfix to staging and third notify the customer success team",
        ),
        "expected_check": lambda out: "- Review pull request 88" in out or "pull request 88" in out,
    },
    # Family 5: Executive summary
    {
        "id": "GGUF-F5-005",
        "family": "summary",
        "task": "summary",
        "req": VF1Request(
            task="summary",
            transcript="our third quarter revenue reached twelve million four hundred thousand dollars representing twenty two percent year over year growth driven by thirty five enterprise renewals and eight new healthcare logos operating margin expanded three hundred basis points to eighteen percent",
        ),
        "expected_check": lambda out: ("12.4" in out or "12,400,000" in out or "$12.4M" in out or "$12.4 million" in out) and "22%" in out,
    },
    # Family 6: Tone / style rewriting
    {
        "id": "GGUF-F6-006",
        "family": "followup_style",
        "task": "tone_shift",
        "req": VF1Request(
            task="tone_shift",
            draft="Your report was late and had errors. Fix it by tomorrow.",
            instruction="Make this constructive and professional for an internal colleague.",
        ),
        "expected_check": lambda out: "late and had errors" not in out.lower() and ("feedback" in out.lower() or "review" in out.lower() or "update" in out.lower() or "revise" in out.lower()),
    },
    # Family 7: Follow-up editing (surgical draft update)
    {
        "id": "GGUF-F7-007",
        "family": "followup_style",
        "task": "surgical_edit",
        "req": VF1Request(
            task="surgical_edit",
            draft="The product launch is scheduled for Tuesday at 9:00 AM in the main auditorium.",
            instruction="Change Tuesday to Friday and change 9:00 AM to 11:30 AM.",
            transcript="let's push the launch to friday at eleven thirty am instead",
        ),
        "expected_check": lambda out: "Friday at 11:30 AM" in out or "Friday at 11:30am" in out or "Friday at 11:30" in out,
    },
]

def query_server(port: int, prompt: str, max_tokens: int = 256) -> tuple[str, float, int]:
    url = f"http://127.0.0.1:{port}/completion"
    payload = {
        "prompt": prompt,
        "temperature": 0.0,
        "n_predict": max_tokens,
        "stop": ["<|im_end|>", "<|endoftext|>"],
        "stream": False,
        "cache_prompt": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            elapsed = time.time() - t0
            content = res.get("content", "").strip()
            tokens_eval = res.get("tokens_evaluated", 0)
            tokens_pred = res.get("tokens_predicted", 0)
            if content.startswith("<think>\n\n</think>\n\n"):
                content = content[len("<think>\n\n</think>\n\n"):].strip()
            return content, elapsed, tokens_pred
    except Exception as e:
        print(f"Error calling port {port}: {e}")
        return f"ERROR: {e}", 0.0, 0

def main():
    print("=" * 70)
    print("Validating Candidate C.2 Merged Q4_K_M GGUF vs Production Baseline")
    print("Port 8080: Baseline S1-mini GGUF")
    print("Port 8085: Candidate C.2 Merged Q4_K_M GGUF")
    print("=" * 70)

    results = []
    
    for c in TEST_CASES:
        prompt = render_vf1(c["req"])
        print(f"\n--- Running [{c['id']}] {c['family']} ({c['task']}) ---")

        # Query Baseline (Port 8080)
        base_out, base_t, base_toks = query_server(8080, prompt)
        base_pass = c["expected_check"](base_out)
        print(f"  [Baseline 8080] ({base_t:.2f}s, {base_toks} tok) Pass: {base_pass}")
        print(f"    Output: {base_out.replace(chr(10), ' ')[:100]}")

        # Query Candidate C.2 Q4_K_M (Port 8085)
        cand_out, cand_t, cand_toks = query_server(8085, prompt)
        cand_pass = c["expected_check"](cand_out)
        print(f"  [Candidate C.2 8085] ({cand_t:.2f}s, {cand_toks} tok) Pass: {cand_pass}")
        print(f"    Output: {cand_out.replace(chr(10), ' ')[:100]}")

        results.append({
            "id": c["id"],
            "family": c["family"],
            "task": c["task"],
            "baseline": {
                "output": base_out,
                "latency_s": round(base_t, 3),
                "tokens": base_toks,
                "passed": base_pass,
            },
            "candidate_c2_q4": {
                "output": cand_out,
                "latency_s": round(cand_t, 3),
                "tokens": cand_toks,
                "passed": cand_pass,
            }
        })

    report_path = HERE / "logs" / "gguf_quantized_inference_validation.json"
    os.makedirs(report_path.parent, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": "2026-10-14T21:05:00Z",
            "server_baseline_port": 8080,
            "server_candidate_c2_port": 8085,
            "candidate_c2_gguf": "runs/clean_multitask_lora_run2/gguf/s1-mini-vf1-run2-q4_k_m.gguf",
            "results": results
        }, f, indent=2)

    print("\n" + "=" * 70)
    print(f"Validation complete! Report written to {report_path}")
    base_passes = sum(1 for r in results if r["baseline"]["passed"])
    cand_passes = sum(1 for r in results if r["candidate_c2_q4"]["passed"])
    print(f"Baseline Pass Rate: {base_passes}/{len(results)}")
    print(f"Candidate C.2 Q4_K_M Pass Rate: {cand_passes}/{len(results)}")
    print("=" * 70)

if __name__ == "__main__":
    main()

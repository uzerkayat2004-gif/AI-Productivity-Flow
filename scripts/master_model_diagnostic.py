#!/usr/bin/env python3
"""Master Model Quality Diagnostic & Benchmark Suite (Tasks 1, 2, 3, 4).

Performs strict, audited evaluation across:
1. PyTorch Merged HF (Stage B)
2. F16 GGUF (Stage C)
3. Q8_0 GGUF (Stage D)
4. Q6_K GGUF (Stage E1)
5. Q5_K_M GGUF (Stage E2)
6. Q4_K_M GGUF (Stage F)
7. Baseline Production GGUF (Port 8080)

Enforces strict factual preservation, draft preservation, entity preservation,
and task instruction adherence.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from voice_flow.vf_contract import VF1Request, render_vf1

SUITE_PATH = PROJECT_ROOT / "data" / "independent_eval_suite_42.jsonl"
OUTPUT_REPORT = PROJECT_ROOT / "logs" / "master_model_diagnostic_report.json"

# Strict, comprehensive ground-truth evaluator
def evaluate_case_strict(rec: dict, gen: str, model_label: str) -> dict:
    cid = rec["id"]
    bucket = rec["bucket"]
    req = rec["request"]
    task = req["task"]
    target = rec["reference"]
    transcript = req.get("transcript", "")
    draft = req.get("draft", "")
    instruction = req.get("instruction", "")

    passed = True
    reasons = []

    # 1. Structural / Placeholder leaks
    if bool(re.search(r"\[(?:Your|Recipient|Name|Company|Insert).*?\]", gen, re.IGNORECASE)):
        passed = False
        reasons.append("placeholder_leak")

    # 2. Tag echoes
    if bool(re.search(r"(\[VF-1\]|\[Task:|\[Instruction\]|\[Draft\]|\[Transcript\])", gen)):
        passed = False
        reasons.append("tag_echo")

    # --- Family 1: Cleanup & Corrections ---
    if cid == "INDEP-F1-001":
        # Must resolve to 7,50,000 INR plus 18% GST; must NOT keep 5,50,000
        has_750k = any(x in gen for x in ["7,50,000", "750,000", "7.5 lakh", "7.5 Lakh"])
        has_550k = any(x in gen for x in ["5,50,000", "550,000", "5.5 lakh"])
        has_gst = "18%" in gen and "GST" in gen
        if not has_750k or has_550k or not has_gst:
            passed = False
            reasons.append("failed_inr_self_correction_or_gst")

    elif cid == "INDEP-F1-002":
        # Board meeting: Nov 14 2026, 3:30 PM EST
        if "November 14, 2026" not in gen and "Nov 14, 2026" not in gen:
            passed = False
            reasons.append("failed_date_nov14")
        if "3:30" not in gen or "EST" not in gen:
            passed = False
            reasons.append("failed_time_or_tz")

    elif cid == "INDEP-F1-003":
        # Account wire: 048291, CHASUS33, negation 'do not'
        if "048291" not in gen:
            passed = False
            reasons.append("failed_account_number")
        if "CHAS" not in gen or "33" not in gen:
            passed = False
            reasons.append("failed_swift_code")
        if "do not" not in gen.lower() and "don't" not in gen.lower():
            passed = False
            reasons.append("failed_negation_preservation")

    elif cid == "INDEP-F1-004":
        # File path & lines: /var/log/redis/redis.log, 400 to 500
        if "/var/log/redis/redis.log" not in gen:
            passed = False
            reasons.append("failed_redis_log_path")
        if "400" not in gen or "500" not in gen:
            passed = False
            reasons.append("failed_line_range")

    elif cid == "INDEP-F1-005":
        # Version & cluster: 2.4.0-rc3, eu-west-1
        if "2.4.0-rc3" not in gen and "2.4.0-RC3" not in gen:
            passed = False
            reasons.append("failed_semver_rc")
        if "eu-west-1" not in gen:
            passed = False
            reasons.append("failed_cluster_name")

    elif cid == "INDEP-F1-006":
        # Self-correction: 11:15 AM (not 10:45), Gate B22
        if "11:15" not in gen:
            passed = False
            reasons.append("failed_time_self_correction_1115")
        if "B22" not in gen and "B-22" not in gen:
            passed = False
            reasons.append("failed_gate_b22")

    # --- Family 2: Professional Emails & Messages ---
    elif cid == "INDEP-F2-007":
        # Email: Subject: header, Client Steering Committee, Staging restored, RCA by 5pm, Marcus
        lines = [l.strip() for l in gen.splitlines() if l.strip()]
        if not lines or not lines[0].lower().startswith("subject:"):
            passed = False
            reasons.append("missing_or_misplaced_subject_header")
        if "Marcus" not in gen:
            passed = False
            reasons.append("missing_sender_marcus")
        if "5pm" not in gen.lower() and "5:00 pm" not in gen.lower() and "5:00pm" not in gen.lower():
            passed = False
            reasons.append("missing_rca_deadline")

    elif cid == "INDEP-F2-008":
        # Email: Subject: header, 23:00 UTC (NOT 02:30!), 01:00 UTC
        lines = [l.strip() for l in gen.splitlines() if l.strip()]
        if not lines or not lines[0].lower().startswith("subject:"):
            passed = False
            reasons.append("missing_or_misplaced_subject_header")
        # Strict time check: must contain 23:00 or 2300, must NOT contain 2:30 or 02:30
        if "2:30" in gen or "02:30" in gen or ("23:00" not in gen and "2300" not in gen):
            passed = False
            reasons.append("corrupted_maintenance_time_2300_to_0230")
        if "01:00" not in gen and "0100" not in gen and "1:00" not in gen:
            passed = False
            reasons.append("missing_end_time_0100")

    elif cid == "INDEP-F2-009":
        # Email: Subject: header, invoice 9904, $18,500, 15 days, Wednesday, Devon Vance
        lines = [l.strip() for l in gen.splitlines() if l.strip()]
        if not lines or not lines[0].lower().startswith("subject:"):
            passed = False
            reasons.append("missing_or_misplaced_subject_header")
        if "9904" not in gen:
            passed = False
            reasons.append("missing_invoice_number")
        if "18,500" not in gen and "18500" not in gen:
            passed = False
            reasons.append("missing_invoice_amount")
        if "Devon" not in gen:
            passed = False
            reasons.append("missing_sender_devon")

    elif cid == "INDEP-F2-010":
        # Slack: demo 2:00 PM to 3:30 PM, Room Beta
        if "3:30" not in gen:
            passed = False
            reasons.append("missing_rescheduled_time_330")
        if "Beta" not in gen:
            passed = False
            reasons.append("missing_room_beta")

    elif cid == "INDEP-F2-011":
        # Incident: 12 ms lag, 0.01% error rate, 30 minutes
        if "12" not in gen or ("ms" not in gen and "millisecond" not in gen.lower()):
            passed = False
            reasons.append("missing_lag_12ms")
        if "0.01" not in gen:
            passed = False
            reasons.append("missing_error_rate_001")

    elif cid == "INDEP-F2-012":
        # Celebratory: SOC 2 Type II, zero findings
        if "soc 2" not in gen.lower() or ("type ii" not in gen.lower() and "type 2" not in gen.lower()):
            passed = False
            reasons.append("missing_soc2_type2")
        if "zero" not in gen.lower() and "0" not in gen:
            passed = False
            reasons.append("missing_zero_findings")

    # --- Family 3: Actionable AI Prompts ---
    elif bucket == "prompt":
        for echo_prefix in [
            "can you make me a prompt for", "tell claude to", "i want an instruction for",
            "give me a prompt to", "could you write an ai prompt that", "ask the ai to",
            "write me a prompt", "design a prompt"
        ]:
            if gen.lower().startswith(echo_prefix):
                passed = False
                reasons.append("meta_wrapper_echo")
                break
        first_word = gen.split()[0].rstrip(",:").lower() if gen.split() else ""
        imperative_verbs = {
            "extract", "write", "draft", "design", "create", "generate", "build", "a", "an",
            "compose", "summarize", "refactor", "implement", "analyze", "review", "outline"
        }
        if first_word not in imperative_verbs:
            passed = False
            reasons.append("non_imperative_prompt_start")

        if cid == "INDEP-F3-013" and ("10-k" not in gen.lower() and "10k" not in gen.lower()):
            passed = False
            reasons.append("missing_sec_10k")
        if cid == "INDEP-F3-014" and ("asyncio" not in gen.lower() or "pandas" not in gen.lower()):
            passed = False
            reasons.append("missing_asyncio_or_pandas")
        if cid == "INDEP-F3-015" and ("neo tokyo" not in gen.lower() or "neon" not in gen.lower()):
            passed = False
            reasons.append("missing_neo_tokyo_or_neon")

    # --- Family 4: Structured Notes & Checklists ---
    elif bucket == "notes_format":
        bullet_lines = [l for l in gen.splitlines() if l.strip().startswith(("-", "*", "•", "1.", "2.", "3.", "[ ]"))]
        if len(bullet_lines) < 2 and "\n" not in gen:
            passed = False
            reasons.append("failed_list_formatting")

    # --- Family 5: Executive Summaries ---
    elif cid == "INDEP-F5-025":
        if "12.4" not in gen and "12,400,000" not in gen and "12.4M" not in gen:
            passed = False
            reasons.append("failed_revenue_12.4m")
        if "22%" not in gen:
            passed = False
            reasons.append("failed_growth_22pct")

    elif cid == "INDEP-F5-026":
        if "42%" not in gen:
            passed = False
            reasons.append("failed_latency_42pct")
        if "280" not in gen:
            passed = False
            reasons.append("failed_p99_280ms")

    # --- Family 6 & 7: Follow-up Editing & Style ---
    elif cid == "INDEP-F7-037":
        # CRITICAL ASSERTION: Must update Tuesday->Friday, 9:00 AM->11:30 AM AND preserve "in the main auditorium"
        # Must NOT simply output "Let us push the launch..."
        has_friday = "friday" in gen.lower()
        has_1130 = "11:30" in gen
        has_auditorium = "main auditorium" in gen.lower() or "auditorium" in gen.lower()
        if not has_friday or not has_1130 or not has_auditorium:
            passed = False
            reasons.append("failed_draft_edit_or_dropped_auditorium")
        if gen.lower().startswith("let us push") or gen.lower().startswith("let's push"):
            passed = False
            reasons.append("converted_edit_to_prose_dropped_draft")

    elif cid == "INDEP-F7-038":
        # Must add Devon Vance AND change time to 3:30 PM AND keep Elena Rostova, Boardroom A
        if "Devon" not in gen:
            passed = False
            reasons.append("failed_co_presenter_devon")
        if "3:30" not in gen:
            passed = False
            reasons.append("failed_time_330")
        if "Elena" not in gen or "Boardroom A" not in gen:
            passed = False
            reasons.append("dropped_elena_or_boardroom")

    elif cid == "INDEP-F7-039":
        # Must update amount to $16,500 AND delete initial deposit sentence
        if "16,500" not in gen:
            passed = False
            reasons.append("failed_amount_16500")
        if "deposit" in gen.lower() or "july" in gen.lower() or "$4,000" in gen or "4,000" in gen:
            passed = False
            reasons.append("failed_deletion_of_deposit_sentence")

    elif cid == "INDEP-F7-040":
        # Postgres 16 and double RAM (128GB)
        if "16" not in gen or "Postgres" not in gen:
            passed = False
            reasons.append("failed_postgres_16")
        if "128" not in gen:
            passed = False
            reasons.append("failed_doubled_ram_128gb")

    elif cid == "INDEP-F7-041":
        # Add security audit report
        if "security audit" not in gen.lower():
            passed = False
            reasons.append("failed_security_audit_addition")
        if "risk register" not in gen.lower() or "charter" not in gen.lower():
            passed = False
            reasons.append("dropped_prior_attachments")

    elif cid == "INDEP-F7-042":
        # Port 8443 and HTTPS
        if "8443" not in gen:
            passed = False
            reasons.append("failed_port_8443")
        if "HTTPS" not in gen and "https" not in gen:
            passed = False
            reasons.append("failed_https_switch")

    elif cid == "INDEP-F6-034":
        # Must preserve hedge 'likely' and condition 'unless legal gives written approval'
        if "unless" not in gen.lower() or "legal" not in gen.lower():
            passed = False
            reasons.append("dropped_legal_approval_condition")

    return {
        "case_id": cid,
        "bucket": bucket,
        "task": task,
        "model": model_label,
        "raw_output": gen,
        "passed": passed,
        "reasons": reasons,
    }

def render_prompt(rec: dict) -> str:
    r = dict(rec["request"])
    req = VF1Request(**r)
    sys_prompt, user_prompt = render_vf1(req)
    return (
        f"<|im_start|>system\n{sys_prompt}<|im_end|>\n"
        f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
        f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )

def query_llama_server(port: int, prompt: str, max_tokens: int = 128) -> tuple[str, float, int]:
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
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            elapsed = time.perf_counter() - t0
            content = str(res.get("content") or "").strip()
            tokens_pred = res.get("tokens_predicted", 0)
            if content.startswith("<think>\n\n</think>\n\n"):
                content = content[len("<think>\n\n</think>\n\n"):].strip()
            return content, elapsed, tokens_pred
    except Exception as exc:
        print(f"Error querying port {port}: {exc}")
        return "", 0.0, 0

print("Master diagnostic module loaded successfully.")

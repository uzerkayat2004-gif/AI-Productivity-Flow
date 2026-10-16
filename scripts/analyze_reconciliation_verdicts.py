import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

data = json.load(open("logs/reconciliation_42_intermediate.json", encoding="utf-8"))

def classify_case(c):
    cid = c["cid"]
    bucket = c["bucket"]
    task = c["task"]
    t = c["transcript"]
    d = c["draft"]
    ins = c["instruction"]
    ref = c["reference"]
    
    # We analyze all 3 models
    analysis = {}
    for model_key in ["baseline_gguf", "candidate_c2_q4", "pytorch_merged"]:
        m_data = c[model_key]
        raw = m_data["raw_output"]
        p_pass = m_data["prev_pass"]
        m_pass = m_data["master_pass"]
        m_reasons = m_data["master_reasons"]
        
        # Determine category and true verdict
        # 1. Did master evaluator make an incorrect judgment?
        evaluator_bug = False
        rubric_issue = ""
        
        # Check known phantom rubric bugs in master_model_diagnostic.py
        if cid == "INDEP-F1-002" and "failed_date_nov14" in m_reasons:
            evaluator_bug = True
            rubric_issue = "Master rubric checked for phantom 'November 14' date and 'EST' tz on an invoice payment case."
        elif cid == "INDEP-F1-003" and "failed_account_number" in m_reasons:
            evaluator_bug = True
            rubric_issue = "Master rubric checked for phantom account 048291 and SWIFT CHASUS33 on a redis log tail command."
        elif cid == "INDEP-F1-004" and "failed_redis_log_path" in m_reasons:
            evaluator_bug = True
            rubric_issue = "Master rubric checked for redis log path on an 11:15 meeting reschedule transcript."
        elif cid == "INDEP-F1-005" and "failed_semver_rc" in m_reasons:
            evaluator_bug = True
            rubric_issue = "Master rubric checked for semver 2.4.0-rc3 on Dr. Priya Mehta architecture meeting."
        elif cid == "INDEP-F1-006" and "failed_time_self_correction_1115" in m_reasons:
            evaluator_bug = True
            rubric_issue = "Master rubric checked for Gate B22 and 11:15 on database migration statement."
        elif cid == "INDEP-F2-010" and "missing_rescheduled_time_330" in m_reasons:
            evaluator_bug = True
            rubric_issue = "Master rubric checked for room Beta and 3:30 on payment gateway latency alert."
        elif cid == "INDEP-F2-011" and "missing_lag_12ms" in m_reasons:
            evaluator_bug = True
            rubric_issue = "Master rubric checked for lag 12ms on coffee chat invitation."
        elif cid == "INDEP-F5-025" and "failed_revenue_12.4m" in m_reasons:
            evaluator_bug = True
            rubric_issue = "Master rubric checked for $12.4M revenue on billing refund QA bug summary."
        elif cid == "INDEP-F5-026" and "failed_latency_42pct" in m_reasons:
            evaluator_bug = True
            rubric_issue = "Master rubric checked for latency 42% on Q3 ARR financial report."
        elif cid == "INDEP-F7-040" and "failed_postgres_16" in m_reasons:
            evaluator_bug = True
            rubric_issue = "Master rubric checked for Postgres 16 on staging port 8443 edit."
        elif cid == "INDEP-F7-041" and "failed_security_audit_addition" in m_reasons:
            evaluator_bug = True
            rubric_issue = "Master rubric checked for security audit on PR 305 tone edit."
        elif cid == "INDEP-F7-042" and "failed_port_8443" in m_reasons:
            evaluator_bug = True
            rubric_issue = "Master rubric checked for port 8443 on Sprint 43 checklist edit."
            
        analysis[model_key] = {
            "evaluator_bug": evaluator_bug,
            "rubric_issue": rubric_issue,
            "raw": raw,
            "prev_pass": p_pass,
            "master_pass": m_pass,
            "master_reasons": m_reasons
        }
    return analysis

# Let's run over all cases and print the evaluator bug count
buggy_cases = []
for c in data:
    res = classify_case(c)
    has_bug = any(res[m]["evaluator_bug"] for m in ["baseline_gguf", "candidate_c2_q4", "pytorch_merged"])
    if has_bug:
        buggy_cases.append((c["cid"], res["baseline_gguf"]["rubric_issue"]))

print(f"Total cases affected by mismatched rubric in master diagnostic: {len(buggy_cases)} of 42")
for cid, issue in buggy_cases:
    print(f"  {cid}: {issue}")

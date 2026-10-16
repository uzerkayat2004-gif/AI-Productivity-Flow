import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

suite_file = Path("data/independent_eval_suite_42.jsonl")
suite = [json.loads(line) for line in suite_file.read_text(encoding="utf-8").splitlines() if line.strip()]

prev_hf = json.load(open("logs/independent_suite_42_evaluation_report.json", encoding="utf-8"))
prev_gguf = json.load(open("logs/independent_suite_42_gguf_server_report.json", encoding="utf-8"))
master = json.load(open("logs/master_model_diagnostic_report.json", encoding="utf-8"))

prev_base_gguf = {r["case_id"]: r for r in prev_gguf["raw_results"]["baseline"]}
prev_c2_q4 = {r["case_id"]: r for r in prev_gguf["raw_results"]["candidate_c2_q4"]}
prev_py_r2 = {r["case_id"]: r for r in prev_hf["raw_results"]["run2_strengthened_lora"]}

master_base_gguf = {r["case_id"]: r for r in master["raw_results"]["Baseline_S1_Mini_GGUF"]}
master_c2_q4 = {r["case_id"]: r for r in master["raw_results"]["Q4_K_M_GGUF"]}
master_py_hf = {r["case_id"]: r for r in master["raw_results"]["PyTorch_Merged_HF_FP32"]}

print(f"Loaded {len(suite)} cases.")

results = []
for i, c in enumerate(suite, 1):
    cid = c["id"]
    bucket = c["bucket"]
    req = c["request"]
    task = req.get("task")
    t = req.get("transcript", "")
    d = req.get("draft", "")
    ins = req.get("instruction", "")
    ref = c["reference"]
    crit = c.get("evaluation_criteria", "")

    # Baseline GGUF outputs and verdicts
    b_prev_pass = prev_base_gguf[cid]["passed"]
    b_prev_out = prev_base_gguf[cid]["raw_output"]
    b_prev_reasons = prev_base_gguf[cid].get("reasons", [])

    b_master_pass = master_base_gguf[cid]["passed"]
    b_master_out = master_base_gguf[cid]["raw_output"]
    b_master_reasons = master_base_gguf[cid].get("reasons", [])

    # Candidate C2 Q4 outputs and verdicts
    q_prev_pass = prev_c2_q4[cid]["passed"]
    q_prev_out = prev_c2_q4[cid]["raw_output"]
    q_prev_reasons = prev_c2_q4[cid].get("reasons", [])

    q_master_pass = master_c2_q4[cid]["passed"]
    q_master_out = master_c2_q4[cid]["raw_output"]
    q_master_reasons = master_c2_q4[cid].get("reasons", [])

    # PyTorch outputs and verdicts
    py_prev_pass = prev_py_r2[cid]["passed"]
    py_prev_out = prev_py_r2[cid]["raw_output"]
    py_prev_reasons = prev_py_r2[cid].get("reasons", [])

    py_master_pass = master_py_hf[cid]["passed"]
    py_master_out = master_py_hf[cid]["raw_output"]
    py_master_reasons = master_py_hf[cid].get("reasons", [])

    results.append({
        "index": i,
        "cid": cid,
        "bucket": bucket,
        "task": task,
        "transcript": t,
        "draft": d,
        "instruction": ins,
        "reference": ref,
        "criteria": crit,
        "baseline_gguf": {
            "prev_pass": b_prev_pass,
            "prev_reasons": b_prev_reasons,
            "master_pass": b_master_pass,
            "master_reasons": b_master_reasons,
            "raw_output": b_master_out
        },
        "candidate_c2_q4": {
            "prev_pass": q_prev_pass,
            "prev_reasons": q_prev_reasons,
            "master_pass": q_master_pass,
            "master_reasons": q_master_reasons,
            "raw_output": q_master_out
        },
        "pytorch_merged": {
            "prev_pass": py_prev_pass,
            "prev_reasons": py_prev_reasons,
            "master_pass": py_master_pass,
            "master_reasons": py_master_reasons,
            "raw_output": py_master_out
        }
    })

Path("logs/reconciliation_42_intermediate.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
print("Wrote logs/reconciliation_42_intermediate.json")

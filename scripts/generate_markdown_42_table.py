import json
from pathlib import Path

# Load data
report_json = Path("logs/corrected_rope_42_benchmark_report.json")
data = json.loads(report_json.read_text(encoding="utf-8"))
models = data["models"]
suite_cases = [json.loads(line) for line in Path("data/independent_eval_suite_42.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

families = [
    ("F1", "F1: Speech Cleanup & Corrections"),
    ("F2", "F2: Professional & Personal Messages"),
    ("F3", "F3: AI Prompt Generation"),
    ("F4", "F4: Lists, Action Items & Notes"),
    ("F5", "F5: Summarization"),
    ("F6", "F6: Tone, Clarity & Style"),
    ("F7", "F7: Follow-up Editing Instructions"),
]

# Generate detailed 42-case table
rows = []
for i, c in enumerate(suite_cases):
    cid = c["id"]
    family = c["bucket"]
    req = c["request"]
    desc = c.get("evaluation_criteria", "")[:50] or c.get("reference", "")[:50]
    
    # Get status for each model
    res_base = next(r for r in models["Baseline_GGUF"]["results"] if r["cid"] == cid)
    res_py = next(r for r in models["PyTorch_Merged_FP32"]["results"] if r["cid"] == cid)
    res_f16 = next(r for r in models["Run2_F16_GGUF_v2"]["results"] if r["cid"] == cid)
    res_q4 = next(r for r in models["Run2_Q4_K_M_GGUF_v2"]["results"] if r["cid"] == cid)
    res_q5 = next(r for r in models["Run2_Q5_K_M_GGUF_v2"]["results"] if r["cid"] == cid)
    
    b_stat = "PASS" if res_base["passed"] else "FAIL"
    py_stat = "PASS" if res_py["passed"] else "FAIL"
    f16_stat = "PASS" if res_f16["passed"] else "FAIL"
    q4_stat = "PASS" if res_q4["passed"] else "FAIL"
    q5_stat = "PASS" if res_q5["passed"] else "FAIL"
    
    # Reason / category
    reasons = res_q4["reasons"] if not res_q4["passed"] else (res_base["reasons"] if not res_base["passed"] else ["compliant"])
    cat = res_q4["category"] if not res_q4["passed"] else (res_base["category"] if not res_base["passed"] else "Acceptable semantic paraphrases")
    reason_str = ", ".join(reasons) if reasons else "compliant"
    
    row_md = f"| `{cid}` | {family} | {desc[:40]} | **{b_stat}** | **{py_stat}** | **{f16_stat}** | **{q4_stat}** | **{q5_stat}** | {cat} ({reason_str}) |"
    rows.append(row_md)

# Verify counts programmatically
count_base = sum(1 for r in models["Baseline_GGUF"]["results"] if r["passed"])
count_py = sum(1 for r in models["PyTorch_Merged_FP32"]["results"] if r["passed"])
count_f16 = sum(1 for r in models["Run2_F16_GGUF_v2"]["results"] if r["passed"])
count_q4 = sum(1 for r in models["Run2_Q4_K_M_GGUF_v2"]["results"] if r["passed"])
count_q5 = sum(1 for r in models["Run2_Q5_K_M_GGUF_v2"]["results"] if r["passed"])

print(f"Table verification counts:")
print(f"Base: {count_base}/42")
print(f"PyTorch: {count_py}/42")
print(f"F16: {count_f16}/42")
print(f"Q4: {count_q4}/42")
print(f"Q5: {count_q5}/42")

out_file = Path("logs/generated_markdown_42_table.md")
out_file.write_text("\n".join(rows), encoding="utf-8")
print(f"Saved {len(rows)} rows to {out_file}")

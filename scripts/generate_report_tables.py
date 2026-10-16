import json
from pathlib import Path

report_json = Path("logs/corrected_rope_42_benchmark_report.json")
data = json.loads(report_json.read_text(encoding="utf-8"))
models = data["models"]

families = [
    ("F1", "F1: Speech Cleanup & Corrections"),
    ("F2", "F2: Professional & Personal Messages"),
    ("F3", "F3: AI Prompt Generation"),
    ("F4", "F4: Lists, Action Items & Notes"),
    ("F5", "F5: Summarization"),
    ("F6", "F6: Tone, Clarity & Style"),
    ("F7", "F7: Follow-up Editing Instructions"),
]

print("=== PER-FAMILY BREAKDOWN ===")
header = f"{'Task Family':<38} | {'Baseline':<10} | {'PyTorch':<10} | {'Run2 F16':<10} | {'Run2 Q4':<10} | {'Run2 Q5':<10}"
print(header)
print("-" * len(header))

for fid, fname in families:
    row = [f"{fname:<38}"]
    for mk in ["Baseline_GGUF", "PyTorch_Merged_FP32", "Run2_F16_GGUF_v2", "Run2_Q4_K_M_GGUF_v2", "Run2_Q5_K_M_GGUF_v2"]:
        m = models[mk]
        sub = [r for r in m["results"] if fid in r["cid"]]
        p = sum(1 for r in sub if r["passed"])
        row.append(f"{p}/{len(sub):<8}")
    print(" | ".join(row))

print("-" * len(header))
tot_row = [f"{'Total All 42 Cases':<38}"]
for mk in ["Baseline_GGUF", "PyTorch_Merged_FP32", "Run2_F16_GGUF_v2", "Run2_Q4_K_M_GGUF_v2", "Run2_Q5_K_M_GGUF_v2"]:
    m = models[mk]
    tot_row.append(f"{m['passed']}/{m['total']:<8}")
print(" | ".join(tot_row))

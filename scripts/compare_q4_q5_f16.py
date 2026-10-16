import json
from pathlib import Path

data = json.load(open("logs/corrected_rope_42_benchmark_report.json", encoding="utf-8"))
f16 = {r["cid"]: r for r in data["models"]["Run2_F16_GGUF_v2"]["results"]}
q4 = {r["cid"]: r for r in data["models"]["Run2_Q4_K_M_GGUF_v2"]["results"]}
q5 = {r["cid"]: r for r in data["models"]["Run2_Q5_K_M_GGUF_v2"]["results"]}

print("=== DIFFERENCES BETWEEN Q4, Q5, AND F16 ===")
for cid in sorted(f16.keys()):
    v_f16 = f16[cid]["passed"]
    v_q4 = q4[cid]["passed"]
    v_q5 = q5[cid]["passed"]
    if len({v_f16, v_q4, v_q5}) > 1:
        s_f16 = "PASS" if v_f16 else "FAIL"
        s_q4 = "PASS" if v_q4 else "FAIL"
        s_q5 = "PASS" if v_q5 else "FAIL"
        print(f"\n[{cid}] F16: {s_f16} | Q4: {s_q4} | Q5: {s_q5}")
        print(f"  F16 : {repr(f16[cid]['raw_output'])}")
        print(f"  Q4  : {repr(q4[cid]['raw_output'])}")
        print(f"  Q5  : {repr(q5[cid]['raw_output'])}")
        print(f"  Q4 reasons : {q4[cid]['reasons']}")
        print(f"  Q5 reasons : {q5[cid]['reasons']}")

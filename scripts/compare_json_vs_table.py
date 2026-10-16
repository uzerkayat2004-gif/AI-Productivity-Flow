import json

data = json.load(open("logs/detailed_reconciled_42_matrix.json", encoding="utf-8"))

print(f"Total rows in JSON: {len(data)}")
for r in data:
    cid = r["cid"]
    b = r["models"]["baseline_gguf"]["true_reviewed_verdict"]
    q = r["models"]["candidate_c2_q4"]["true_reviewed_verdict"]
    p = r["models"]["pytorch_merged"]["true_reviewed_verdict"]
    print(f"{cid} | Base: {'PASS' if b else 'FAIL'} | Q4: {'PASS' if q else 'FAIL'} | PyTorch: {'PASS' if p else 'FAIL'}")

b_total = sum(1 for r in data if r["models"]["baseline_gguf"]["true_reviewed_verdict"])
q_total = sum(1 for r in data if r["models"]["candidate_c2_q4"]["true_reviewed_verdict"])
p_total = sum(1 for r in data if r["models"]["pytorch_merged"]["true_reviewed_verdict"])
print(f"\nExact JSON sums: Base={b_total}/42, Q4={q_total}/42, PyTorch={p_total}/42")

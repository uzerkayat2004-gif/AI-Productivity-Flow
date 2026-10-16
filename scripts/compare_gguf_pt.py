import json

rep = json.load(open('logs/independent_suite_42_gguf_server_report.json', 'r', encoding='utf-8'))
pt = json.load(open('logs/independent_suite_42_evaluation_report.json', 'r', encoding='utf-8'))

cand_gguf = {r['case_id']: r for r in rep['raw_results']['candidate_c2_q4']}
cand_pt = {r['case_id']: r for r in pt['raw_results']['run2_strengthened_lora']}

for cid in ['INDEP-F1-001', 'INDEP-F2-007', 'INDEP-F2-008', 'INDEP-F3-013', 'INDEP-F3-014', 'INDEP-F3-015', 'INDEP-F7-037', 'INDEP-F7-038']:
    g = cand_gguf[cid]
    p = cand_pt[cid]
    print(f"=== {cid} ===")
    print(f"GGUF Output: {g['raw_output']}")
    print(f"PT Output:   {p['raw_output']}")
    print(f"GGUF Passed: {g['passed']} ({g['reasons']})")
    print(f"PT Passed:   {p['passed']} ({p['reasons']})")
    print()

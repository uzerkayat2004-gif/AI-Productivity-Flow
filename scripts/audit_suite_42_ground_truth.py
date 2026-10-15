import json

with open("data/independent_eval_suite_42.jsonl", "r", encoding="utf-8") as f:
    cases = [json.loads(l) for l in f if l.strip()]

print(f"Total cases: {len(cases)}")
for idx, c in enumerate(cases, 1):
    req = c["request"]
    t = req.get("transcript", "")
    d = req.get("draft", "")
    ins = req.get("instruction", "")
    print(f"[{idx:02d}] {c['id']} | {c['bucket']} ({req.get('task')})")
    if ins: print(f"     Instruction: {ins}")
    if d:   print(f"     Draft:       {d}")
    if t:   print(f"     Transcript:  {t}")
    print(f"     Reference:   {c['reference']}")
    print(f"     Criteria:    {c.get('evaluation_criteria')}")
    print()

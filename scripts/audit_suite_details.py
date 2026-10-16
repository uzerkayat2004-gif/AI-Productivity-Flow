import json
from pathlib import Path
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

suite_path = Path("data/independent_eval_suite_42.jsonl")
cases = [json.loads(line) for line in suite_path.read_text(encoding="utf-8").splitlines() if line.strip()]

print(f"Total suite cases: {len(cases)}")
for i, c in enumerate(cases, 1):
    cid = c["id"]
    bucket = c["bucket"]
    req = c["request"]
    task = req.get("task")
    t = req.get("transcript", "")
    d = req.get("draft", "")
    ins = req.get("instruction", "")
    ref = c["reference"]
    print(f"[{i:02d}] {cid} ({bucket} / {task})")
    if ins: print(f"     Ins: {ins}")
    if d:   print(f"     Drf: {d}")
    if t:   print(f"     Tra: {t}")
    print(f"     Ref: {ref}")

import json

rep = json.load(open('logs/independent_suite_42_evaluation_report.json', 'r', encoding='utf-8'))
for cand in rep['raw_results'].keys():
    results = rep['raw_results'][cand]
    fails = [x for x in results if not x['passed']]
    print(f"=== {cand.upper()} FAILURES ({len(fails)} / {len(results)}) ===")
    for x in fails:
        print(f"ID: {x['case_id']} [{x['bucket']}]")
        print(f"  Reasons: {x['reasons']}")
        print(f"  Output: {x['raw_output']}")
        print(f"  Reference: {x['reference']}")
        print()

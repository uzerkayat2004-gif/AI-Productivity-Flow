"""Write data/hashes.json (SHA-256 of frozen data files) and tool hashes."""
import hashlib, json, os
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
ROOT = os.path.join(HERE, "..", "..", "..")
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
files = ["HELDOUT_EVALUATION.jsonl", "PILOT_TRAINING_SAMPLE.jsonl", "PILOT_S1_NATIVE_PENDING.jsonl"]
json.dump({f: sha(os.path.join(DATA, f)) for f in files}, open(os.path.join(DATA, "hashes.json"), "w"), indent=1)
tools = {p: sha(os.path.join(ROOT, p)) for p in [
    "src/voice_flow/vf_contract.py", "src/voice_flow/vf_checks.py",
    "research/vf_phase2a/scripts/dataset_checks.py", "research/vf_phase2a/scripts/vf_render.py"]}
json.dump(tools, open(os.path.join(DATA, "tool_hashes.json"), "w"), indent=1)
print(json.dumps(json.load(open(os.path.join(DATA, "hashes.json"))), indent=1)); print(json.dumps(tools, indent=1))

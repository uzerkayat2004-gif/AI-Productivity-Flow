"""Informational: run the reference host processor on host_integration items.

The hand-written `host.expected` block is the truth; the parser is measured
against it, never the other way round.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "src"))
from voice_flow.activation import ActivationConfig, DEFAULT_ACTIVATION  # noqa: E402
from voice_flow.voice_commands import detect_voice_command  # noqa: E402

def cfg(a):
    if a.get("assistant_name") == "Voice Flow" and "phrases" not in a:
        from dataclasses import replace
        return replace(DEFAULT_ACTIVATION, enabled=a.get("enabled", True))
    return ActivationConfig(assistant_name=a["assistant_name"], phrases=tuple(a.get("phrases", ())),
                            allow_bare_name=a.get("allow_bare_name", True), enabled=a.get("enabled", True))

out = []
for name in ("HELDOUT_EVALUATION.jsonl", "PILOT_TRAINING_SAMPLE.jsonl"):
    for l in open(os.path.join(HERE, "..", "data", name)):
        r = json.loads(l)
        if "host" not in r:
            continue
        h = r["host"]
        det = detect_voice_command(h["utterance"], cfg(h["activation"]))
        exp = h["expected"]
        ok = (det.command is not None) == exp["command"] and det.content == exp["content"]
        if ok and det.command is not None:
            for k, v in exp["fields"].items():
                got = getattr(det.command, k)
                if k == "overrides":
                    ok = ok and all(got.get(a) == b for a, b in v.items())
                elif k == "constraints":
                    ok = ok and list(got) == v
                else:
                    ok = ok and got == v
        out.append((r["id"], ok, det.command is not None, det.content))
for row in out:
    print(*row, sep=" | ")
print(f"agreement {sum(o[1] for o in out)}/{len(out)}")

"""W10 stage 2: messages bucket, 130 records (TC-W10-101..230).

Buckets/slices: messages (personal/chat), style_rules (saved user [Rules]), dev_custom_style (developer house rules).
Domains: stage-1 ones (family trips, residents' society, chess club, hiking group, pet care) plus
college friends reunion, cricket fans group, gardening club, freelance clients (personal tone).
Names: Aarav, Ishita, Zoe, Karim, Nora, Dev, Simran, Callum, Mehul, Inaya, Rory, Saira, Jasper.
Stage-1 review fixes applied: no "!" unless dictated or Tone/instruction excited; third-person dictation stays
third-person; "ask X" is kept as dictated; no invented proper nouns; tone instructions visibly change wording;
framing phrases kept.
Re-run to reproduce research/vf_phase2b/data/batches/W10_s2.jsonl exactly.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from p2b_kit import rec, save  # noqa: E402

WID = "W10"
OUT = os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s2.jsonl")
rows = []


# extra records rendered with the full header (about 30% overall together with the **F records)
FULL_EXTRA = {102, 104, 109, 110, 114, 116, 120, 125, 127, 131, 136, 139, 143, 147, 155, 163, 171, 181, 192, 201, 214, 226}


def length_class(transcript):
    w = len(transcript.split())
    return "short" if w < 20 else "medium" if w <= 60 else "long"


def R(slice_, request, target, assertions, note=None, pos="structured", cx=0, length=None, waivers=None):
    n = 101 + len(rows)
    req = {"task": "rewrite"}
    req.update(request)
    if n in FULL_EXTRA:
        req["header_style"] = "full"
    length = length_class(req["transcript"])
    a = dict(assertions)
    a.setdefault("format", "message")
    rows.append(rec(f"TC-{WID}-{n:03d}", "messages", slice_, req, target, a, f"w10-sc-{n:03d}",
                    author=WID, note=note, waivers=waivers,
                    meta={"command_position": pos, "instruction_complexity": cx, "length_class": length}))


P = {"format": "message", "context": "personal"}
CH = {"format": "message", "context": "chat"}
F = {"header_style": "full"}

for part in ("W10_s2_part1.py", "W10_s2_part2.py", "W10_s2_part3.py"):
    path = os.path.join(HERE, part)
    if os.path.exists(path):
        exec(open(path, encoding="utf-8").read())

save(OUT, rows)
print(len(rows), "records ->", os.path.normpath(OUT))

"""Automatic validation for VF-1 dataset records (held-out and training).

Every check returns named problems.  A record with any problem is quarantined,
never silently accepted.  See DATASET_VALIDATION_REPORT.md for what these
checks cannot establish.
"""
from __future__ import annotations

import re
import sys
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "src"))

from voice_flow.vf_contract import ContractError, VF1Request, validate  # noqa: E402
from voice_flow.vf_checks import check_output  # noqa: E402

SLICES = {
    "cleanup_ordinary", "facts_numbers_negation", "corrections_vs_alternatives", "email", "messages", "prompt",
    "question_no_answer", "nl_instruction", "multi_constraint", "followup_edit", "summary", "smart_formatting",
    "no_markdown", "style_rules", "unsupported_boundary", "host_integration",
    # training-only slices
    "dev_custom_style", "s1_native",
}
REQUIRED = ("id", "split", "slice", "request", "target", "assertions", "provenance", "contract_revision")
BEHAVIORS = {"transform", "not_answer", "cleanup_only"}
FORMATS_STRUCT = {"prose", "bullets", "numbered", "email", "message", "post", "prompt", "note"}
CONTROL_STRINGS = ("<|im_end|>", "<|im_start|>", "<|endoftext|>", "<think>", "</think>", "[Transcript]", "[Instruction]",
                   "[VF-1]", "[Draft]", "[Rules]")
PREAMBLE = re.compile(r"^\s*(?:sure|certainly|of course|here(?:'s| is| are)\b|okay,? here|i've (?:rewritten|cleaned)|"
                      r"below is|as requested)", re.I)
EXPLANATION = re.compile(r"\b(?:i(?: have|'ve) (?:rewritten|changed|removed|fixed|cleaned|corrected|updated|adjusted)|explanation\s*:|changes made|"
                         r"here is the (?:rewritten|cleaned|corrected))", re.I)
NEG = re.compile(r"\b(?:not|never|no|nobody|nothing|none|neither|nor|without|can't|cannot|won't|don't|doesn't|didn't|"
                 r"isn't|aren't|wasn't|haven't|hasn't|shouldn't|couldn't|wouldn't|n't)\b", re.I)
DEVANAGARI = re.compile(r"[\u0900-\u097F]")
NON_LATIN = re.compile(r"[\u0400-\u04FF\u0600-\u06FF\u0900-\u097F\u3040-\u30FF\u4E00-\u9FFF]")


def _num_present(lit: str, text: str) -> bool:
    return re.search(rf"(?<![\d.,:]){re.escape(lit)}(?![\d])", text) is not None


def request_of(rec) -> VF1Request:
    r = dict(rec["request"])
    if "rules" in r:
        r["rules"] = tuple(r["rules"])
    return VF1Request(**r)


def check_assertions(rec, output: str) -> list[str]:
    """Hand-written assertions; used on targets (self-consistency) and on model outputs at eval time."""
    a = rec["assertions"]
    out = output or ""
    low = out.lower()
    problems = []
    for s in a.get("must_include", []):
        if s.lower() not in low:
            problems.append(f"missing:{s}")
    for group in a.get("must_include_one_of", []):
        if not any(g.lower() in low for g in group):
            problems.append(f"missing_one_of:{group}")
    for s in a.get("must_not_include", []):
        if s.strip() and re.fullmatch(r"\d+", s.strip()):
            if _num_present(s.strip(), out):
                problems.append(f"forbidden_number:{s}")
        elif s.lower() in low:
            problems.append(f"forbidden:{s}")
    for n in a.get("numbers", []):
        if not _num_present(n, out):
            problems.append(f"number_missing:{n}")
    for group in a.get("numbers_one_of", []):
        if not any(_num_present(g, out) or g.lower() in low for g in group):
            problems.append(f"number_missing_one_of:{group}")
    if a.get("min_negations"):
        if len(NEG.findall(out)) < a["min_negations"]:
            problems.append("negation_missing")
    if a.get("ends_with_question") is True and not out.rstrip().endswith("?"):
        problems.append("not_a_question")
    if a.get("max_words") and len(out.split()) > a["max_words"]:
        problems.append(f"too_long:{len(out.split())}>{a['max_words']}")
    fmt = a.get("format")
    problems += format_problems(out, fmt, no_markdown=a.get("no_markdown", True))
    return problems


def format_problems(out: str, fmt: str | None, *, no_markdown: bool = True) -> list[str]:
    p = []
    lines = [l for l in out.splitlines() if l.strip()]
    if no_markdown:
        if re.search(r"\*\*|__|^#{1,6}\s|```|^\s*\|.*\|\s*$", out, re.M):
            p.append("markdown_in_plain")
    if fmt == "bullets":
        body = [l for l in lines if not l.rstrip().endswith(":")]
        if not body or not all(l.startswith("- ") for l in body):
            p.append("bullets_malformed")
    elif fmt == "numbered":
        nums = [re.match(r"^(\d+)\. ", l) for l in lines if not l.rstrip().endswith(":")]
        if not nums or not all(nums) or [int(m.group(1)) for m in nums] != list(range(1, len(nums) + 1)):
            p.append("numbering_malformed")
    elif fmt in ("prose", "message", "post", "prompt", "note"):
        if any(re.match(r"^(?:- |\d+\. )", l) for l in lines):
            p.append(f"unexpected_list_in_{fmt}")
    elif fmt == "email":
        if not lines or not re.match(r"^(?:Subject:|Hi|Hello|Dear|Hey|Good (?:morning|afternoon))", lines[0]):
            p.append("email_no_greeting")
        if re.search(r"\[[^\]]*(?:name|recipient|your)[^\]]*\]", out, re.I):
            p.append("email_placeholder")
    return p


def record_problems(rec, *, tokenizers=None) -> list[str]:
    p = []
    for k in REQUIRED:
        if k not in rec:
            p.append(f"schema_missing:{k}")
    if p:
        return p
    if rec["slice"] not in SLICES:
        p.append(f"schema_bad_slice:{rec['slice']}")
    if rec["assertions"].get("behavior") not in BEHAVIORS:
        p.append("schema_bad_behavior")
    prov = rec["provenance"]
    for k in ("author", "method", "uses_s1_output", "reviewed"):
        if k not in prov:
            p.append(f"provenance_missing:{k}")
    if prov.get("reviewed") is not True:
        p.append("not_reviewed")
    if rec["slice"] == "s1_native":
        return p + _native_problems(rec, tokenizers)
    try:
        req = request_of(rec)
        validate(req)
    except (ContractError, TypeError) as exc:
        p.append(f"contract:{exc}")
        return p
    if req.experimental:
        p.append("experimental_in_v1")
    target = rec["target"]
    if not isinstance(target, str) or not target.strip():
        p.append("empty_target")
        return p
    if target != target.strip() or "\n\n\n" in target or "  " in target:
        p.append("whitespace")
    for c in CONTROL_STRINGS:
        if c in target:
            p.append(f"control_string_in_target:{c}")
    for ch in ("\u200b", "\u2060", "\ufeff"):
        if ch in target:
            p.append("zero_width_in_target")
    if PREAMBLE.search(target) and not PREAMBLE.search(req.transcript or req.draft or ""):
        p.append("assistant_preamble")
    if EXPLANATION.search(target):
        p.append("explanation_text")
    src = (req.draft or "") + " " + (req.transcript or "")
    if NON_LATIN.search(target) and not NON_LATIN.search(src):
        p.append("language_switch")
    if DEVANAGARI.search(src) and not DEVANAGARI.search(target):
        p.append("language_switch")
    p += [f"assert:{x}" for x in check_assertions(rec, target)]
    # Format implied by the request must agree with the assertion format.
    fmt = req.format or req.default_format()
    afmt = rec["assertions"].get("format")
    dictated_list = req.task == "cleanup" and not req.format and re.search(
        r"\b(?:bullet(?: point)?|next bullet|number one|first item)\b", req.transcript or "", re.I)
    if afmt and fmt != "auto" and req.task != "edit" and afmt != fmt and not (dictated_list and afmt in ("bullets", "numbered")):
        p.append(f"format_mismatch:{fmt}!={afmt}")
    # Fact checker: source = transcript (+ draft for edits); instruction authorises.
    source = req.transcript if req.task != "edit" else req.draft
    fc = check_output(source, target, task=req.task, fmt=fmt, instruction=req.instruction, sender=req.sender,
                      recipient=req.recipient, allow_number_change=(req.facts == "correct"))
    waived = set(rec.get("checker_waivers", []))
    for f in fc.failures:
        key = f.split(":")[0]
        if key not in waived:
            p.append(f"facts:{f}")
    if tokenizers:
        p += _render_problems(rec, req, target, tokenizers)
    return p


def _render_problems(rec, req, target, tokenizers) -> list[str]:
    import vf_render as R

    out = []
    for name, tok in tokenizers.items():
        ex = R.vf1_example(tok, req, target)
        trained = [i for i in ex.labels if i != -100]
        if trained[-1] != R.IM_END or trained.count(R.IM_END) != 1:
            out.append(f"eos:{name}")
        if ex.input_ids.count(R.IM_START) != 3:
            out.append(f"turns:{name}")
        if len(ex.input_ids) > 1024:
            out.append(f"too_long_tokens:{name}:{len(ex.input_ids)}")
        if set(trained[:-1]) & set(range(151643, 151669)):
            out.append(f"special_in_target:{name}")
    return out


def _native_problems(rec, tokenizers) -> list[str]:
    p = []
    req = rec["request"]
    if set(req) != {"native_control", "transcript"}:
        p.append("native_schema")
    if not re.fullmatch(r"\[Styling: (?:casual|semi-casual|semi-formal|formal)\] \[Structure: (?:prose|lists)\] "
                        r"\[Context: (?:general|email)\]", req.get("native_control", "")):
        p.append("native_control_bad")
    fc = check_output(req.get("transcript", ""), rec["target"], task="cleanup")
    p += [f"facts:{f}" for f in fc.failures]
    p += [f"assert:{x}" for x in check_assertions(rec, rec["target"])]
    if tokenizers:
        import vf_render as R
        tok = tokenizers["s1-mini"]
        ex = R.s1_native_example(tok, req["native_control"], req["transcript"], rec["target"])
        trained = [i for i in ex.labels if i != -100]
        if trained[-1] != R.IM_END or trained.count(R.IM_END) != 1:
            p.append("eos:s1-mini")
    return p


# ------------------------------------------------------------------ split integrity / near duplicates

def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (t or "").lower()).split().__str__()


def char_ngrams(t: str, n: int = 5) -> set:
    s = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (t or "").lower())).strip()
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def word_ngrams(t: str, n: int = 3) -> set:
    w = re.findall(r"[a-z0-9']+", (t or "").lower())
    return {tuple(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def similarity(a: str, b: str) -> tuple[float, float]:
    ca, cb = char_ngrams(a), char_ngrams(b)
    jac = len(ca & cb) / max(1, len(ca | cb))
    wa, wb = word_ngrams(a), word_ngrams(b)
    cont = len(wa & wb) / max(1, min(len(wa), len(wb))) if wa and wb else 0.0
    return jac, cont


def record_text(rec) -> str:
    r = rec["request"]
    return " ".join(str(r.get(k, "")) for k in ("transcript", "draft", "instruction"))


def near_duplicates(records_a, records_b=None, *, jac_t=0.55, cont_t=0.6):
    """Pairs whose source text is near-identical (within one set when b is None)."""
    pairs = []
    if records_b is None:
        for i in range(len(records_a)):
            for j in range(i + 1, len(records_a)):
                jac, cont = similarity(record_text(records_a[i]), record_text(records_a[j]))
                if jac >= jac_t or cont >= cont_t:
                    pairs.append((records_a[i]["id"], records_a[j]["id"], round(jac, 2), round(cont, 2)))
    else:
        for x in records_a:
            for y in records_b:
                jac, cont = similarity(record_text(x), record_text(y))
                if jac >= jac_t or cont >= cont_t:
                    pairs.append((x["id"], y["id"], round(jac, 2), round(cont, 2)))
    return pairs


def word_set(t):
    return set(re.findall(r"[a-z']+", (t or "").lower()))

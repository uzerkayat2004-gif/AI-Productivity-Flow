"""Shared record builder for hand-written VF-1 dataset items."""
from __future__ import annotations

AUTHOR = "hark-manual-2026-10-12"


def E(slice_, request, target, *, inc=None, exc=None, nums=None, alt_nums=None, alt_inc=None, neg=None, q=None,
      fmt=None, beh="transform", max_words=None, note=None, host=None, scenario=None, checker_waivers=None):
    req = {k: v for k, v in request.items() if v not in (None, "", ())}
    if "rules" in req:
        req["rules"] = list(req["rules"])
    assertions = {"behavior": beh, "no_markdown": req.get("markup", "plain") == "plain"}
    if inc:
        assertions["must_include"] = list(inc)
    if alt_inc:
        assertions["must_include_one_of"] = [list(g) for g in alt_inc]
    if exc:
        assertions["must_not_include"] = list(exc)
    if nums:
        assertions["numbers"] = list(nums)
    if alt_nums:
        assertions["numbers_one_of"] = [list(g) for g in alt_nums]
    if neg is not None:
        assertions["min_negations"] = neg
    if q is not None:
        assertions["ends_with_question"] = q
    if fmt:
        assertions["format"] = fmt
    if max_words:
        assertions["max_words"] = max_words
    rec = {
        "slice": slice_,
        "request": req,
        "target": target,
        "assertions": assertions,
        "provenance": {"author": AUTHOR, "method": "hand-written", "teacher": None, "uses_s1_output": False,
                       "reviewed": True},
    }
    if host:
        rec["host"] = host
    if checker_waivers:
        rec["checker_waivers"] = list(checker_waivers)
    if note:
        rec["note"] = note
    if scenario:
        rec["scenario"] = scenario
    return rec

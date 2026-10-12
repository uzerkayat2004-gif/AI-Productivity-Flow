"""The validator must reject known-bad records (mutation tests) and pass the frozen files."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import dataset_checks as C  # noqa: E402
import vf_render as R  # noqa: E402

DATA = os.path.join(HERE, "..", "data")


def load(name):
    return [json.loads(l) for l in open(os.path.join(DATA, name), encoding="utf-8")]


HELDOUT = load("HELDOUT_EVALUATION.jsonl")
PILOT = load("PILOT_TRAINING_SAMPLE.jsonl")
TOKS = {m: R.load_tokenizer(m) for m in ("s1-mini", "qwen3-0.6b")}


def by_id(rows, i):
    return copy.deepcopy(next(r for r in rows if r["id"] == i))


def test_frozen_files_match_manifest_hashes():
    manifest = json.load(open(os.path.join(DATA, "hashes.json")))
    for name, h in manifest.items():
        assert hashlib.sha256(open(os.path.join(DATA, name), "rb").read()).hexdigest() == h, name


@pytest.mark.parametrize("rows", [HELDOUT, PILOT], ids=["heldout", "pilot"])
def test_all_records_pass(rows):
    bad = {r["id"]: C.record_problems(r, tokenizers=TOKS) for r in rows}
    assert {k: v for k, v in bad.items() if v} == {}


def test_no_cross_split_near_duplicates_or_shared_scenarios():
    assert C.near_duplicates(PILOT, HELDOUT, jac_t=0.45, cont_t=0.5) == []
    assert not ({r["scenario_id"] for r in PILOT} & {r["scenario_id"] for r in HELDOUT})
    assert not ({r["id"] for r in PILOT} & {r["id"] for r in HELDOUT})


BASE = "PT-022"  # "The invoice for Vikram is £2,375."


def mutate(fn):
    rec = by_id(PILOT, BASE)
    fn(rec)
    return C.record_problems(rec, tokenizers=TOKS)


@pytest.mark.parametrize("name,fn,expect", [
    ("number changed", lambda r: r.update(target="The invoice for Vikram is £2,735."), "number"),
    ("name dropped", lambda r: r.update(target="The invoice is £2,375."), "missing:Vikram"),
    ("empty", lambda r: r.update(target="  "), "empty_target"),
    ("preamble", lambda r: r.update(target="Sure! The invoice for Vikram is £2,375."), "assistant_preamble"),
    ("explanation", lambda r: r.update(target="The invoice for Vikram is £2,375. (I've corrected the amount.)"), "explanation_text"),
    ("markdown", lambda r: r.update(target="The invoice for **Vikram** is £2,375."), "markdown_in_plain"),
    ("control token", lambda r: r.update(target="The invoice for Vikram is £2,375.<|im_end|>"), "control_string"),
    ("think block", lambda r: r.update(target="<think>\n\n</think>\n\nThe invoice for Vikram is £2,375."), "control_string"),
    ("zero width", lambda r: r.update(target="The invoice for Vikram is £2,375.\u200b"), "zero_width"),
    ("language switch", lambda r: r.update(target="विक्रम का चालान £2,375 है।"), "language_switch"),
    ("bad task", lambda r: r["request"].update(task="translate"), "contract"),
    ("experimental", lambda r: r["request"].update(task="auto", experimental=True), "experimental_in_v1"),
    ("bad combo", lambda r: r["request"].update(format="email"), "contract"),
    ("no provenance", lambda r: r.pop("provenance"), "schema_missing:provenance"),
    ("unreviewed", lambda r: r["provenance"].update(reviewed=False), "not_reviewed"),
    ("bad slice", lambda r: r.update(slice="misc"), "schema_bad_slice"),
    ("double space", lambda r: r.update(target="The invoice for Vikram  is £2,375."), "whitespace"),
])
def test_validator_rejects_mutation(name, fn, expect):
    problems = mutate(fn)
    assert any(expect in p for p in problems), (name, problems)


def test_validator_rejects_invented_signoff_and_commitment():
    rec = by_id(PILOT, "PT-043")  # email, no sender
    rec["target"] = rec["target"] + "\n\nBest,\nJordan"
    assert any("invented_signoff" in p for p in C.record_problems(rec))
    rec = by_id(PILOT, "PT-043")
    rec["target"] = rec["target"] + " I'll follow up tomorrow."
    assert any("invented_commitment" in p for p in C.record_problems(rec))


def test_validator_rejects_reverted_correction_and_lost_negation():
    rec = by_id(PILOT, "PT-031")  # Book the studio for Sam.
    rec["target"] = "Book the studio for Chloe."
    assert C.record_problems(rec)
    rec = by_id(PILOT, "PT-026")  # free for students but not for professionals
    rec["target"] = "The hackathon is free for students and professionals."
    assert C.record_problems(rec)


def test_validator_flags_near_duplicate_paraphrase():
    a = by_id(HELDOUT, "HE-042")
    b = copy.deepcopy(a)
    b["id"] = "X-1"
    b["request"]["transcript"] = "you can pay by card or by a bank transfer"
    assert C.near_duplicates([b], [a], jac_t=0.45, cont_t=0.5)


def test_validator_rejects_bad_list_and_email_layout():
    rec = by_id(PILOT, "PT-095")  # bullets
    rec["target"] = "Logo due on the 4th and pitch deck due on the 11th."
    assert any("bullets_malformed" in p for p in C.record_problems(rec))
    rec = by_id(PILOT, "PT-043")
    rec["target"] = "We need the hall from 8 a.m. to 6 p.m. on the 9th."
    assert any("email_no_greeting" in p for p in C.record_problems(rec))


def test_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.load(open(os.path.join(DATA, "RECORD_SCHEMA.json")))
    for name in ("HELDOUT_EVALUATION.jsonl", "PILOT_TRAINING_SAMPLE.jsonl", "PILOT_S1_NATIVE_PENDING.jsonl"):
        for r in load(name):
            jsonschema.validate(r, schema)


def test_pending_native_rows_are_not_training_ready():
    for r in load("PILOT_S1_NATIVE_PENDING.jsonl"):
        assert r["split"] == "train_pending" and r["provenance"]["reviewed"] is False
        assert "not_reviewed" in C.record_problems(r)

"""Phase 3A trainer tests (CPU). Run: cd research/vf_phase3a && python -m pytest -q tests"""
import argparse
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
P2B = os.path.abspath(os.path.join(ROOT, "..", "vf_phase2b"))
sys.path.insert(0, ROOT)
import S1_LORA_TRAINER as T  # noqa: E402


@pytest.fixture(scope="module")
def setup():
    R = T.import_renderer(P2B)
    tok = R.R.load_tokenizer("s1-mini")
    corpus, reh, held = T.load_data(P2B)
    return R, tok, corpus, reh, held


def test_data_hashes_match():
    assert all(v["ok"] for v in T.verify_data_files(P2B, strict=False).values())


def test_no_truncation_all_records_fit(setup):
    R, tok, corpus, reh, _ = setup
    ex, probs = T.build_examples(R, tok, corpus + reh, 640)
    assert not probs and len(ex) == len(corpus) + len(reh)


def test_collator_masks_and_eot(setup):
    R, tok, corpus, reh, _ = setup
    recs = corpus[:6] + reh[:2]
    ex, _ = T.build_examples(R, tok, recs, 640)
    b = T.collate([ex[r["id"]] for r in recs])
    assert T.check_batch(b) == []
    for i, r in enumerate(recs):
        lab = b["labels"][i]
        toks = lab[lab != T.IGNORE].tolist()
        assert toks[-1] == T.IM_END and tok.decode(toks[:-1]) == r["target"]


def test_supervised_loss_matches_hf():
    import torch
    from transformers import Qwen3Config, Qwen3ForCausalLM
    torch.manual_seed(0)
    m = Qwen3ForCausalLM(Qwen3Config(vocab_size=151936, hidden_size=32, intermediate_size=64, num_hidden_layers=1,
                                     num_attention_heads=2, num_key_value_heads=1, head_dim=16, tie_word_embeddings=True))
    exs = [{"input_ids": [T.IM_START] * 3 + list(range(10, 30)) + [5, 6, 7, T.IM_END],
            "labels": [T.IGNORE] * 23 + [5, 6, 7, T.IM_END]},
           {"input_ids": [T.IM_START] * 3 + list(range(40, 50)) + [8, T.IM_END], "labels": [T.IGNORE] * 13 + [8, T.IM_END]}]
    b = T.collate(exs)
    with torch.no_grad():
        ref = m(**b).loss
        tot, n, _ = T.supervised_loss(m, b, None)
    assert abs(float(ref) - float(tot) / n) < 1e-5


def test_schedules_ratio_and_isolation(setup):
    _, _, corpus, reh, held = setup
    val = {r["id"] for r in corpus if r["split"] == "validation"}
    for name in ("tiny", "smoke"):
        s, st, dev = T.build_schedule(corpus, reh, T.PROFILES[name], 1)
        ids = {i for _, i in s}
        assert abs(st["rehearsal_share"] - 0.15) < 0.01
        assert not ids & val and not ids & held and not ids & set(dev)


def test_full_profile_disabled_and_gates_block(tmp_path):
    assert T.PROFILES["full"] is None
    g = tmp_path / "g.json"
    g.write_text(json.dumps(json.load(open(os.path.join(ROOT, "GATES_TEMPLATE.json")))))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "S1_LORA_TRAINER.py"), "train", "--p2b", P2B, "--gates", str(g),
                        "--profile", "tiny", "--out", str(tmp_path / "o")], capture_output=True, text=True)
    assert r.returncode != 0 and "Blocked" in (r.stderr + r.stdout)


def test_synthetic_dataset_verify(tmp_path):
    report_file = tmp_path / "synth_report.json"
    workdir = tmp_path / "synth_work"
    r = subprocess.run([
        sys.executable, os.path.join(ROOT, "S1_LORA_TRAINER.py"), "verify",
        "--synthetic", "--report", str(report_file), "--workdir", str(workdir)
    ], capture_output=True, text=True)
    assert r.returncode == 0
    assert report_file.exists()
    rep = json.loads(report_file.read_text())
    assert rep.get("ALL_OK") is True


def test_custom_manifest_support(tmp_path):
    corpus, reh, held = T.generate_synthetic_dataset()
    c_file = tmp_path / "c.jsonl"
    r_file = tmp_path / "r.jsonl"
    h_file = tmp_path / "h.jsonl"
    with open(c_file, "w", encoding="utf-8") as f:
        for row in corpus:
            f.write(json.dumps(row) + "\n")
    with open(r_file, "w", encoding="utf-8") as f:
        for row in reh:
            f.write(json.dumps(row) + "\n")
    with open(h_file, "w", encoding="utf-8") as f:
        for hid in held:
            f.write(json.dumps({"id": hid, "request": {}, "target": ""}) + "\n")

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "corpus": str(c_file),
        "rehearsal": str(r_file),
        "heldout": str(h_file),
        "hashes": {
            str(c_file): T.sha256(str(c_file)),
            str(r_file): T.sha256(str(r_file)),
        }
    }))
    cfg = T.resolve_dataset_config(argparse.Namespace(
        synthetic=False, manifest=str(manifest), p2b=None,
        corpus=None, rehearsal=None, heldout=None, schedule=None, hashes=None
    ))
    assert cfg["mode"] == "manifest"
    loaded_c, loaded_r, loaded_h = T.load_data(cfg)
    assert len(loaded_c) == len(corpus)
    assert len(loaded_r) == len(reh)
    verified = T.verify_data_files(cfg, strict=True)
    assert all(v["ok"] for v in verified.values())


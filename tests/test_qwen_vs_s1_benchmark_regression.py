"""Regression test for S1-mini vs Qwen3-0.6B GPU Inference Benchmark.

Verifies:
1. Integrity of downloaded artifact archive and manifests.
2. 225 completed deterministic generations on NVIDIA Tesla T4 GPU.
3. Metric reproduction for 4-way expanded (50 cases) and diagnostic (25 cases) benchmarks.
4. Safety gate interception and safe fallback invariants.
"""
import hashlib
import json
import os
import zipfile
import pytest

VAULT_DIR = r"D:\apf_restricted_data_vault"
ARCHIVE_ZIP = os.path.join(VAULT_DIR, "qwen3_vs_s1_artifacts.zip")
EXPECTED_ZIP_HASH = "8ed9dce3e2ead7333efc3e96fde48aab65947e18b8eca065462b1695ee6a8680"


def test_archive_integrity():
    assert os.path.exists(ARCHIVE_ZIP), f"Missing artifact zip: {ARCHIVE_ZIP}"
    h = hashlib.sha256()
    with open(ARCHIVE_ZIP, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    assert h.hexdigest() == EXPECTED_ZIP_HASH, "Artifact ZIP SHA-256 mismatch!"


def test_manifest_and_file_checksums():
    with zipfile.ZipFile(ARCHIVE_ZIP, "r") as zf:
        manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
        for fname, meta in manifest_data["files"].items():
            content = zf.read(fname)
            actual_sha = hashlib.sha256(content).hexdigest()
            assert actual_sha == meta["sha256"], f"Checksum mismatch for {fname}"


def test_225_generations_completed():
    with zipfile.ZipFile(ARCHIVE_ZIP, "r") as zf:
        all_gens = json.loads(zf.read("all_raw_generations.json").decode("utf-8"))
        assert len(all_gens) == 225, f"Expected 225 generations, found {len(all_gens)}"

        diag_gens = [g for g in all_gens if g["benchmark_dataset"] == "independent_eval_set"]
        assert len(diag_gens) == 25

        exp_gens = [g for g in all_gens if g["benchmark_dataset"] == "independent_eval_expanded"]
        assert len(exp_gens) == 200


def test_model_selection_scores():
    with zipfile.ZipFile(ARCHIVE_ZIP, "r") as zf:
        exp_rep = json.loads(zf.read("eval_report_4way_expanded50.json").decode("utf-8"))
        results = exp_rep["results"]

        # 1. S1-mini Native (Base): 19/50
        assert results["1. S1-mini Native (Base)"]["passed"] == 19
        assert results["1. S1-mini Native (Base)"]["pass_rate"] == 0.38

        # 2. S1-mini VF-1 (Base): 36/50
        assert results["2. S1-mini VF-1 (Base)"]["passed"] == 36
        assert results["2. S1-mini VF-1 (Base)"]["pass_rate"] == 0.72

        # 3. S1-mini VF-1 (LoRA): 36/50
        assert results["3. S1-mini VF-1 (LoRA)"]["passed"] == 36
        assert results["3. S1-mini VF-1 (LoRA)"]["pass_rate"] == 0.72

        # 4. Qwen3-0.6B VF-1 (Base): 17/50
        assert results["4. Qwen3-0.6B VF-1 (Base)"]["passed"] == 17
        assert results["4. Qwen3-0.6B VF-1 (Base)"]["pass_rate"] == 0.34


def test_qwen_diagnostic_score():
    with zipfile.ZipFile(ARCHIVE_ZIP, "r") as zf:
        diag_rep = json.loads(zf.read("eval_report_qwen25_diagnostic.json").decode("utf-8"))
        qwen_res = diag_rep["results"]["4. Qwen3-0.6B VF-1 (Base)"]
        assert qwen_res["total"] == 25
        assert qwen_res["passed"] == 8
        assert qwen_res["pass_rate"] == 0.32


def test_safety_gate_fallbacks_safe():
    with zipfile.ZipFile(ARCHIVE_ZIP, "r") as zf:
        all_gens = json.loads(zf.read("all_raw_generations.json").decode("utf-8"))
        for g in all_gens:
            gate = g["safety_gate"]
            if not gate["accepted"]:
                # Every rejected output MUST preserve the speaker's original transcript
                assert gate["source_preserved"] is True
                assert gate["final_text"] == g["transcript"]
                assert len(gate["rejection_reasons"]) > 0

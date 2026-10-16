#!/usr/bin/env python3
"""Run full diagnostic suite across all model variants and evaluate strictly."""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from master_model_diagnostic import evaluate_case_strict, render_prompt, query_llama_server

SUITE_PATH = PROJECT_ROOT / "data" / "independent_eval_suite_42.jsonl"
OUTPUT_REPORT = PROJECT_ROOT / "logs" / "master_model_diagnostic_report.json"
MERGED_HF = PROJECT_ROOT / "runs" / "clean_multitask_lora_run2" / "merged_hf"
LLAMA_SERVER_EXE = r"C:\Users\Asus\.voice_flow\bin\llama\llama-server.exe"

GGUF_VARIANTS = [
    ("F16_GGUF", PROJECT_ROOT / "runs" / "clean_multitask_lora_run2" / "gguf" / "s1-mini-vf1-run2-f16.gguf"),
    ("Q8_0_GGUF", PROJECT_ROOT / "runs" / "clean_multitask_lora_run2" / "gguf" / "s1-mini-vf1-run2-q8_0.gguf"),
    ("Q6_K_GGUF", PROJECT_ROOT / "runs" / "clean_multitask_lora_run2" / "gguf" / "s1-mini-vf1-run2-q6_k.gguf"),
    ("Q5_K_M_GGUF", PROJECT_ROOT / "runs" / "clean_multitask_lora_run2" / "gguf" / "s1-mini-vf1-run2-q5_k_m.gguf"),
    ("Q4_K_M_GGUF", PROJECT_ROOT / "runs" / "clean_multitask_lora_run2" / "gguf" / "s1-mini-vf1-run2-q4_k_m.gguf"),
]

def wait_for_server(port=8085, timeout=20):
    url = f"http://127.0.0.1:{port}/health"
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False

def run_suite_on_port(cases, port, label):
    print(f"\n>>> Running 42 cases on {label} (Port {port})...")
    results = []
    latencies = []
    t0 = time.time()
    for idx, c in enumerate(cases, 1):
        prompt = render_prompt(c)
        gen, el, toks = query_llama_server(port, prompt, max_tokens=128)
        ev = evaluate_case_strict(c, gen, label)
        ev["latency_ms"] = round(el * 1000, 1)
        ev["tokens"] = toks
        results.append(ev)
        latencies.append(el * 1000)
        status = "PASS" if ev["passed"] else f"FAIL ({', '.join(ev['reasons'])})"
        print(f"  [{idx:02d}/42] {c['id']}: {status} ({el*1000:.0f}ms)")

    tot_el = round(time.time() - t0, 1)
    n_pass = sum(1 for r in results if r["passed"])
    avg_lat = round(sum(latencies) / len(latencies), 1)
    print(f"=== {label} SUMMARY: {n_pass}/42 passed ({n_pass/42*100:.1f}%) | Avg Latency: {avg_lat}ms | Total Time: {tot_el}s ===")
    return results, n_pass, avg_lat

def run_suite_on_pytorch(cases, model_path, label):
    print(f"\n>>> Running 42 cases on {label} in PyTorch (Float32 CPU)...")
    tok = AutoTokenizer.from_pretrained(str(model_path))
    model = AutoModelForCausalLM.from_pretrained(str(model_path), dtype=torch.float32).eval()
    results = []
    latencies = []
    t0 = time.time()

    for idx, c in enumerate(cases, 1):
        prompt = render_prompt(c)
        inputs = tok(prompt, return_tensors="pt")
        input_ids = inputs["input_ids"]
        t_c0 = time.perf_counter()
        with torch.no_grad():
            out = model.generate(
                input_ids=input_ids,
                max_new_tokens=128,
                do_sample=False,
                eos_token_id=[151645, 151643],
                pad_token_id=151643,
            )
        el = time.perf_counter() - t_c0
        gen_tokens = out[0, input_ids.shape[1]:].tolist()
        gen_text = tok.decode([t for t in gen_tokens if t not in (151645, 151643)], skip_special_tokens=False).strip()

        ev = evaluate_case_strict(c, gen_text, label)
        ev["latency_ms"] = round(el * 1000, 1)
        ev["tokens"] = len(gen_tokens)
        results.append(ev)
        latencies.append(el * 1000)
        status = "PASS" if ev["passed"] else f"FAIL ({', '.join(ev['reasons'])})"
        print(f"  [{idx:02d}/42] {c['id']}: {status} ({el*1000:.0f}ms)")

    tot_el = round(time.time() - t0, 1)
    n_pass = sum(1 for r in results if r["passed"])
    avg_lat = round(sum(latencies) / len(latencies), 1)
    print(f"=== {label} SUMMARY: {n_pass}/42 passed ({n_pass/42*100:.1f}%) | Avg Latency: {avg_lat}ms | Total Time: {tot_el}s ===")
    return results, n_pass, avg_lat

def main():
    print("=" * 70)
    print("STARTING COMPLETE MODEL QUALITY DIAGNOSTIC PIPELINE")
    print("=" * 70)

    with open(SUITE_PATH, "r", encoding="utf-8") as f:
        cases = [json.loads(l) for l in f if l.strip()]

    all_summaries = {}
    all_raw_results = {}

    # 1. Baseline Server (Port 8080)
    res_base, p_base, lat_base = run_suite_on_port(cases, 8080, "Baseline_S1_Mini_GGUF")
    all_summaries["Baseline_S1_Mini_GGUF"] = {
        "passed": p_base, "total": 42, "pass_rate_pct": round(p_base/42*100, 1),
        "avg_latency_ms": lat_base, "size_mb": 396.7
    }
    all_raw_results["Baseline_S1_Mini_GGUF"] = res_base

    # 2. GGUF Variants on Port 8085
    for label, gguf_path in GGUF_VARIANTS:
        if not gguf_path.exists():
            print(f"Warning: {gguf_path} not found, skipping.")
            continue
        size_mb = round(os.path.getsize(gguf_path) / (1024 * 1024), 1)
        print(f"\nStarting {label} on port 8085 ({size_mb} MB)...")
        proc = subprocess.Popen([
            LLAMA_SERVER_EXE,
            "-m", str(gguf_path),
            "--host", "127.0.0.1",
            "--port", "8085",
            "-c", "2048",
            "-ngl", "0",
            "-t", "4",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if not wait_for_server(8085):
            print(f"Error: Server failed to start for {label}")
            proc.kill()
            continue

        res_v, p_v, lat_v = run_suite_on_port(cases, 8085, label)
        all_summaries[label] = {
            "passed": p_v, "total": 42, "pass_rate_pct": round(p_v/42*100, 1),
            "avg_latency_ms": lat_v, "size_mb": size_mb,
            "path": str(gguf_path)
        }
        all_raw_results[label] = res_v

        # Clean shutdown
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        time.sleep(1)

    # 3. PyTorch Merged HF
    res_pt, p_pt, lat_pt = run_suite_on_pytorch(cases, MERGED_HF, "PyTorch_Merged_HF_FP32")
    all_summaries["PyTorch_Merged_HF_FP32"] = {
        "passed": p_pt, "total": 42, "pass_rate_pct": round(p_pt/42*100, 1),
        "avg_latency_ms": lat_pt, "size_mb": 1192.1
    }
    all_raw_results["PyTorch_Merged_HF_FP32"] = res_pt

    # Write Master Report
    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "audit_version": "strict_ground_truth_v2",
        "suite_file": str(SUITE_PATH),
        "summaries": all_summaries,
        "raw_results": all_raw_results
    }
    os.makedirs(OUTPUT_REPORT.parent, exist_ok=True)
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    print("\n" + "=" * 70)
    print("MASTER DIAGNOSTIC RESULTS TABLE (Strict Audited Scoring)")
    print(f"{'Variant':<25} | {'Passed':<8} | {'Pass %':<8} | {'Latency':<10} | {'Size':<10}")
    print("-" * 70)
    for k, v in all_summaries.items():
        print(f"{k:<25} | {v['passed']:<2}/42   | {v['pass_rate_pct']:<6}% | {v['avg_latency_ms']:<7}ms | {v['size_mb']:<7}MB")
    print("=" * 70)
    print(f"Master diagnostic report saved to: {OUTPUT_REPORT}")

if __name__ == "__main__":
    main()

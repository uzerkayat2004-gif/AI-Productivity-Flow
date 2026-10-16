import hashlib
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
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from voice_flow.vf_contract import VF1Request, render_vf1

# 1. Target Case: INDEP-F7-037
req = VF1Request(
    task="edit",
    transcript="let us push the launch to friday at eleven thirty am instead",
    instruction="Change Tuesday to Friday and change 9:00 AM to 11:30 AM.",
    draft="The product launch is scheduled for Tuesday at 9:00 AM in the main auditorium.",
    format="prose"
)
sys_prompt, user_prompt = render_vf1(req)
prompt_text = (
    f"<|im_start|>system\n{sys_prompt}<|im_end|>\n"
    f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
    f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
)

MERGED_HF = PROJECT_ROOT / "runs" / "clean_multitask_lora_run2" / "merged_hf"
F16_GGUF = PROJECT_ROOT / "runs" / "clean_multitask_lora_run2" / "gguf" / "s1-mini-vf1-run2-f16.gguf"
Q4_GGUF = PROJECT_ROOT / "runs" / "clean_multitask_lora_run2" / "gguf" / "s1-mini-vf1-run2-q4_k_m.gguf"
LLAMA_SERVER = Path(r"C:\Users\Asus\.voice_flow\bin\llama\llama-server.exe")

report = {
    "case": "INDEP-F7-037",
    "prompt_text": prompt_text,
    "checks": {}
}

# Check A: File Hashes
print("=== CHECK A: FILE & ARTIFACT HASHES ===")
def get_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest().upper()

safetensors_file = MERGED_HF / "model.safetensors"
safetensors_hash = get_sha256(safetensors_file) if safetensors_file.exists() else "NOT_FOUND"
f16_hash = get_sha256(F16_GGUF) if F16_GGUF.exists() else "NOT_FOUND"
q4_hash = get_sha256(Q4_GGUF) if Q4_GGUF.exists() else "NOT_FOUND"

report["checks"]["file_hashes"] = {
    "model.safetensors": {"path": str(safetensors_file), "sha256": safetensors_hash, "size": safetensors_file.stat().st_size},
    "s1-mini-vf1-run2-f16.gguf": {"path": str(F16_GGUF), "sha256": f16_hash, "size": F16_GGUF.stat().st_size},
    "s1-mini-vf1-run2-q4_k_m.gguf": {"path": str(Q4_GGUF), "sha256": q4_hash, "size": Q4_GGUF.stat().st_size}
}
print(f"model.safetensors SHA-256: {safetensors_hash}")
print(f"F16 GGUF SHA-256:          {f16_hash}")
print(f"Q4_K_M GGUF SHA-256:       {q4_hash}")

# Check B: Tokenizer and Token IDs in PyTorch
print("\n=== CHECK B: PYTORCH TOKENIZATION & TOKEN SEQUENCE ===")
tok = AutoTokenizer.from_pretrained(str(MERGED_HF))
hf_input_ids = tok.encode(prompt_text, add_special_tokens=False)
report["checks"]["pytorch_tokens"] = {
    "num_tokens": len(hf_input_ids),
    "token_ids": hf_input_ids,
    "first_5": hf_input_ids[:5],
    "last_5": hf_input_ids[-5:],
    "decoded_tokens": [tok.decode([t]) for t in hf_input_ids]
}
print(f"PyTorch encoded token count: {len(hf_input_ids)}")
print(f"Last 5 token IDs in PyTorch: {hf_input_ids[-5:]} -> {[repr(tok.decode([t])) for t in hf_input_ids[-5:]]}")

# Check C: PyTorch FP32 Logits at Position T-1
print("\n=== CHECK C: PYTORCH FP32 LAST-TOKEN LOGITS ===")
model_hf = AutoModelForCausalLM.from_pretrained(str(MERGED_HF), dtype=torch.float32)
with torch.no_grad():
    in_t = torch.tensor([hf_input_ids], dtype=torch.long)
    out_hf = model_hf(in_t)
    last_logits = out_hf.logits[0, -1, :]
    probs_hf = torch.softmax(last_logits, dim=-1)
    top10_p, top10_i = torch.topk(probs_hf, 10)

py_top10 = []
for p, idx in zip(top10_p.tolist(), top10_i.tolist()):
    token_str = tok.decode([idx])
    py_top10.append({"id": idx, "token": token_str, "prob": p, "logit": float(last_logits[idx].item())})
    print(f"  ID: {idx:6d} | Logit: {last_logits[idx].item():8.4f} | Prob: {p*100:6.2f}% | Text: {repr(token_str)}")

report["checks"]["pytorch_top10"] = py_top10

# Check D: llama.cpp Tokenization & Logprobs via llama-server (Testing F16 and Q4)
print("\n=== CHECK D: LLAMA.CPP SERVER TOKENIZATION & LOGPROBS ===")
def test_llama_server_divergence(gguf_path: Path, port: int):
    cmd = [
        str(LLAMA_SERVER),
        "-m", str(gguf_path),
        "--host", "127.0.0.1",
        "--port", str(port),
        "-c", "2048",
        "-ngl", "0",
        "-t", "4"
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(2.0)
    
    # Wait for server ready
    ready = False
    for _ in range(30):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/health")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.5)
            
    if not ready:
        proc.kill()
        return {"error": "Server failed to start"}

    try:
        # 1. Query /tokenize endpoint
        tok_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/tokenize",
            data=json.dumps({"content": prompt_text, "add_special": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(tok_req, timeout=5.0) as resp:
            tok_res = json.loads(resp.read().decode("utf-8"))
            server_tokens = tok_res.get("tokens", [])

        # 2. Query /completion endpoint with n_predict=1 and n_probs=10
        comp_payload = {
            "prompt": prompt_text,
            "temperature": 0.0,
            "n_predict": 1,
            "n_probs": 10,
            "stop": ["<|im_end|>", "<|endoftext|>"]
        }
        comp_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/completion",
            data=json.dumps(comp_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(comp_req, timeout=10.0) as resp:
            comp_res = json.loads(resp.read().decode("utf-8"))

        return {
            "tokens": server_tokens,
            "completion": comp_res
        }
    finally:
        proc.kill()
        proc.wait()

print("Testing F16 GGUF on Port 8086...")
f16_server_results = test_llama_server_divergence(F16_GGUF, 8086)
print("Testing Q4_K_M GGUF on Port 8087...")
q4_server_results = test_llama_server_divergence(Q4_GGUF, 8087)

report["checks"]["llama_server_f16"] = f16_server_results
report["checks"]["llama_server_q4"] = q4_server_results

# Check E: Token-by-Token Match Comparison
server_tokens_f16 = f16_server_results.get("tokens", [])
report["checks"]["token_sequences_identical"] = (hf_input_ids == server_tokens_f16)
print(f"\nToken sequences identical between PyTorch and llama.cpp: {hf_input_ids == server_tokens_f16}")
if hf_input_ids != server_tokens_f16:
    print(f"PyTorch len: {len(hf_input_ids)} vs llama.cpp len: {len(server_tokens_f16)}")
    for idx, (h, s) in enumerate(zip(hf_input_ids, server_tokens_f16)):
        if h != s:
            print(f"First mismatch at index {idx}: PyTorch={h} ({repr(tok.decode([h]))}) vs llama.cpp={s}")
            break

# Check F: Top Probabilities in F16 GGUF
completion_probs = f16_server_results.get("completion", {}).get("completion_probabilities", [])
if completion_probs:
    top_probs = completion_probs[0].get("probs", [])
    print("\n=== LLAMA.CPP F16 GGUF TOP TOKENS ===")
    for tp in top_probs:
        print(f"  Token: {repr(tp.get('tok_str'))} | Prob: {tp.get('prob')*100:6.2f}%")

Path("logs/diagnose_runtime_divergence_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print("\nWrote logs/diagnose_runtime_divergence_report.json")

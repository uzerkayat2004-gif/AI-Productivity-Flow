import os
import subprocess
import time
import json
import urllib.request
import psutil

LLAMA_SERVER = r"C:\Users\Asus\.voice_flow\bin\llama\llama-server.exe"
MODELS = {
    "Run2_Q4_K_M_v2": r"D:\.zcode\workspace\default\AI-Productivity-Flow\runs\clean_multitask_lora_run2\gguf\s1-mini-vf1-run2-q4_k_m-v2.gguf",
    "Run2_Q5_K_M_v2": r"D:\.zcode\workspace\default\AI-Productivity-Flow\runs\clean_multitask_lora_run2\gguf\s1-mini-vf1-run2-q5_k_m-v2.gguf",
    "Run2_F16_v2":    r"D:\.zcode\workspace\default\AI-Productivity-Flow\runs\clean_multitask_lora_run2\gguf\s1-mini-vf1-run2-f16-v2.gguf",
    "Baseline_Q4_K_M": r"C:\Users\Asus\.voice_flow\models\s1-mini-q4_k_m.gguf",
}

TEST_PROMPT = """<|im_start|>system
You are Voice Flow VF-1, a local voice-writing assistant. Task: followup_style.
Follow the instruction to edit the draft accurately.
<|im_end|>
<|im_start|>user
[Draft] The staging environment is hosted at staging.internal.net on port 8080. Database credentials are in 1Password.
[Instruction] switch the port to 8443 and add that HTTPS is required
<|im_end|>
<|im_start|>assistant
<think>

</think>

"""

def query_server(port, prompt):
    url = f"http://127.0.0.1:{port}/completion"
    payload = json.dumps({
        "prompt": prompt,
        "n_predict": 128,
        "temperature": 0.0,
        "stop": ["<|im_end|>", "<|endoftext|>"]
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=15) as resp:
        res = json.loads(resp.read().decode("utf-8"))
    lat = (time.perf_counter() - t0) * 1000.0
    tok_cnt = res.get("tokens_predicted", len(res.get("content", "").split()))
    tok_per_sec = (tok_cnt / (lat / 1000.0)) if lat > 0 else 0
    return res.get("content", "").strip(), lat, tok_cnt, tok_per_sec

results = {}
port = 8095

for name, path in MODELS.items():
    file_size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"\n--- Benchmarking {name} ({file_size_mb:.1f} MB) ---")
    
    t0 = time.perf_counter()
    proc = subprocess.Popen([
        LLAMA_SERVER,
        "-m", path,
        "--host", "127.0.0.1",
        "--port", str(port),
        "-c", "2048",
        "-ngl", "0",
        "-t", "4"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # Wait for server
    ready = False
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.1)
    
    load_time_ms = (time.perf_counter() - t0) * 1000.0
    assert ready, f"Failed to start {name}"
    
    # Measure memory
    p = psutil.Process(proc.pid)
    idle_ram_mb = p.memory_info().rss / (1024 * 1024)
    
    # Warmup
    query_server(port, TEST_PROMPT)
    
    # Active query benchmark (3 runs)
    latencies = []
    speeds = []
    peak_ram = idle_ram_mb
    
    for _ in range(3):
        out, lat, cnt, spd = query_server(port, TEST_PROMPT)
        latencies.append(lat)
        speeds.append(spd)
        cur_ram = p.memory_info().rss / (1024 * 1024)
        if cur_ram > peak_ram:
            peak_ram = cur_ram
            
    proc.kill()
    proc.wait()
    
    results[name] = {
        "file_size_mb": round(file_size_mb, 1),
        "load_time_ms": round(load_time_ms, 1),
        "idle_ram_mb": round(idle_ram_mb, 1),
        "peak_ram_mb": round(peak_ram, 1),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1),
        "avg_tok_per_sec": round(sum(speeds) / len(speeds), 1),
        "sample_output": out[:60]
    }
    print(f"  Load time : {load_time_ms:.1f} ms")
    print(f"  Peak RAM  : {peak_ram:.1f} MB")
    print(f"  Latency   : {results[name]['avg_latency_ms']} ms ({results[name]['avg_tok_per_sec']} tok/s)")
    print(f"  Output    : {out[:60]}")

print("\n=== FINAL HARDWARE & EFFICIENCY BENCHMARK TABLE ===")
print(json.dumps(results, indent=2))
Path("logs/hardware_efficiency_report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

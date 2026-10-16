"""NATIVE_DIAG (CI only, not shipped): time the bundled llama-server and NeMo-Speech
engines directly on the runner, outside the app, to separate engine speed from
app behaviour. Writes out/qa/diag.json and out/qa/diag-*.txt."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path

OUT = Path(os.environ.get("QA_OUT", "out")).resolve()
EV = OUT / "qa"
EV.mkdir(parents=True, exist_ok=True)
APP = os.environ.get("APP_PATH", "/Applications/AI Productivity Flow.app")
RES = Path(APP) / "Contents" / "Resources"
PY = RES / "runtime" / "python" / "bin" / "python3"
LLAMA = RES / "runtime" / "llama" / "llama-server"
NEMO = RES / "runtime" / "nemo" / "lib" / "libnemo_speech_asr_c.dylib"
TMP = Path("/tmp/apfdiag")
TMP.mkdir(exist_ok=True)
RESULTS: dict = {}
T0 = time.time()


def log(msg):
    line = f"[{time.time() - T0:7.1f}s] {msg}"
    print(line, flush=True)
    with open(EV / "diag-log.txt", "a") as f:
        f.write(line + "\n")


def sh(cmd, timeout=600):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def save():
    (EV / "diag.json").write_text(json.dumps(RESULTS, indent=2, default=str))


def download(url, dest):
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        return
    t = time.time()
    sh(f"curl -fsSL -o '{dest}' '{url}'", timeout=900)
    log(f"downloaded {dest.name} {dest.stat().st_size} bytes in {time.time() - t:.1f}s")


def rss_mb(pid):
    rc, o = sh(f"ps -o rss= -p {pid}")
    try:
        return round(int(o.strip()) / 1024, 1)
    except Exception:
        return None


def http(url, data=None, timeout=5):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


def llama_variant(name, extra, model, port):
    errf = EV / f"diag-llama-{name}.txt"
    cmd = [str(LLAMA), "-m", str(model), "--host", "127.0.0.1", "--port", str(port), "--alias", "diag"] + extra
    t = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=open(errf, "w"))
    ready = None
    while time.time() - t < 120:
        if proc.poll() is not None:
            break
        try:
            st, body = http(f"http://127.0.0.1:{port}/v1/models", timeout=1)
            if st == 200 and "diag" in body:
                ready = round(time.time() - t, 2)
                break
        except Exception:
            pass
        time.sleep(0.2)
    res = {"cmd": " ".join(cmd[1:]), "ready_s": ready, "exit": proc.poll(), "rss_ready_mb": rss_mb(proc.pid)}
    if ready:
        prompt = ("<|im_start|>user\nClean up this dictation: um so i think we should uh meet on tuesday "
                  "at three pm with priya<|im_end|>\n<|im_start|>assistant\n")
        for i in range(2):
            t1 = time.time()
            try:
                st, body = http(f"http://127.0.0.1:{port}/completion",
                                {"prompt": prompt, "n_predict": 48, "temperature": 0}, timeout=120)
                j = json.loads(body)
                res[f"completion{i}_s"] = round(time.time() - t1, 2)
                res[f"completion{i}_text"] = j.get("content", "")[:200]
                res[f"completion{i}_timings"] = j.get("timings")
            except Exception as exc:
                res[f"completion{i}_error"] = repr(exc)
        res["rss_after_mb"] = rss_mb(proc.pid)
    proc.terminate()
    try:
        proc.wait(10)
    except Exception:
        proc.kill()
    tail = errf.read_text(errors="replace")
    res["log_head"] = "\n".join(l for l in tail.splitlines() if re.search(r"metal|Metal|MTL|device|load_tensors|KV|n_ctx|threads|system_info|compil", l))[:3000]
    log(f"llama {name}: {json.dumps({k: v for k, v in res.items() if k != 'log_head'})[:900]}")
    return res


NEMO_PROBE = r'''
import ctypes, json, sys, time, wave
import numpy as np
sys.path.insert(0, sys.argv[4])
import nemotron_abi as abi
dll_path, model, wav_path = sys.argv[1], sys.argv[2], sys.argv[3]
gpu = int(sys.argv[5]) if len(sys.argv) > 5 else -1
out = {}
t = time.time(); dll = abi.load_dll(dll_path); out["load_dll_s"] = round(time.time() - t, 3)
backend = abi._BackendConfig(size=ctypes.sizeof(abi._BackendConfig), gpu=gpu)
mc = abi._ModelConfig(size=ctypes.sizeof(abi._ModelConfig), path=model.encode(), name=None)
cfg = abi._RecognizerConfig(size=ctypes.sizeof(abi._RecognizerConfig), backend=ctypes.pointer(backend), model=ctypes.pointer(mc))
h = ctypes.c_void_p()
t = time.time(); st = dll.nemo_speech_asr_create(ctypes.byref(cfg), ctypes.byref(h)); out["create_s"] = round(time.time() - t, 3); out["create_status"] = st
if st:
    out["err"] = (dll.nemo_speech_asr_last_error() or b"").decode(); print(json.dumps(out)); sys.exit()
with wave.open(wav_path) as w:
    rate = w.getframerate(); pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
out["audio_s"] = round(len(pcm) / rate, 2); out["rate"] = rate
buf = (ctypes.c_float * len(pcm))(*pcm.tolist())
def opts():
    o = dll.nemo_speech_asr_recognition_options_default(); o.enable_automatic_punctuation = True; return o
for i in range(3):
    o = opts(); res = ctypes.c_void_p()
    t = time.time(); st = dll.nemo_speech_asr_recognize_f32(h, ctypes.byref(o), buf, len(pcm), rate, ctypes.byref(res)); dt = time.time() - t
    txt = dll.nemo_speech_asr_result_transcript(res, 0) if st == 0 and res.value else None
    out[f"recognize{i}_s"] = round(dt, 3); out[f"recognize{i}_status"] = st; out[f"recognize{i}_text"] = (txt or b"").decode("utf-8", "replace")
    if res.value: dll.nemo_speech_asr_result_destroy(res)
# streaming warm pass exactly like the app worker (1 s silence)
o = opts(); o.interim_results = False; stream = ctypes.c_void_p()
t = time.time(); st = dll.nemo_speech_asr_streaming_recognize(h, ctypes.byref(o), ctypes.byref(stream))
silence = (ctypes.c_float * 16000)(); st2 = dll.nemo_speech_asr_stream_push_f32(stream, silence, 16000, 16000)
while True:
    r = ctypes.c_void_p(); n = dll.nemo_speech_asr_stream_next(stream, ctypes.byref(r))
    if n != 0 or not r.value: break
    dll.nemo_speech_asr_result_destroy(r)
dll.nemo_speech_asr_stream_close(stream); out["stream_warm_s"] = round(time.time() - t, 3)
# streaming the clip in 100 ms frames like a live dictation
o = opts(); o.interim_results = False; stream = ctypes.c_void_p()
dll.nemo_speech_asr_streaming_recognize(h, ctypes.byref(o), ctypes.byref(stream))
t = time.time(); texts = []
step = rate // 10
for off in range(0, len(pcm), step):
    chunk = pcm[off:off + step]; cb = (ctypes.c_float * len(chunk))(*chunk.tolist())
    dll.nemo_speech_asr_stream_push_f32(stream, cb, len(chunk), rate)
    while True:
        r = ctypes.c_void_p(); n = dll.nemo_speech_asr_stream_next(stream, ctypes.byref(r))
        if n != 0 or not r.value: break
        tx = dll.nemo_speech_asr_result_transcript(r, 0)
        if tx and dll.nemo_speech_asr_result_is_final(r): texts.append(tx.decode())
        dll.nemo_speech_asr_result_destroy(r)
out["stream_push_s"] = round(time.time() - t, 3)
t = time.time(); dll.nemo_speech_asr_stream_finish(stream)
while True:
    r = ctypes.c_void_p(); n = dll.nemo_speech_asr_stream_next(stream, ctypes.byref(r))
    if n != 0 or not r.value: break
    tx = dll.nemo_speech_asr_result_transcript(r, 0)
    if tx and dll.nemo_speech_asr_result_is_final(r): texts.append(tx.decode())
    dll.nemo_speech_asr_result_destroy(r)
out["stream_finish_s"] = round(time.time() - t, 3); out["stream_text"] = " ".join(texts)
dll.nemo_speech_asr_stream_close(stream)
dll.nemo_speech_asr_destroy(h)
print(json.dumps(out))
'''


def nemo_run(name, dll, model, wav, gpu=-1, env_extra=None):
    probe = TMP / "nemo_probe.py"
    probe.write_text(NEMO_PROBE)
    env = dict(os.environ)
    env.update(env_extra or {})
    t = time.time()
    p = subprocess.run(["/usr/bin/time", "-l", str(PY), "-I", "-B", str(probe), str(dll), str(model), str(wav),
                        str(RES / "src" / "voice_flow"), str(gpu)], capture_output=True, text=True, timeout=900, env=env)
    res = {"wall_s": round(time.time() - t, 2), "rc": p.returncode}
    for line in p.stdout.splitlines():
        if line.startswith("{"):
            res.update(json.loads(line))
    m = re.search(r"(\d+)\s+maximum resident set size", p.stderr)
    if m:
        res["max_rss_mb"] = round(int(m.group(1)) / 1024 / 1024, 1)
    res["stderr_tail"] = p.stderr[-1500:]
    log(f"nemo {name}: {json.dumps({k: v for k, v in res.items() if k != 'stderr_tail'})[:1200]}")
    return res


def main():
    sh("pkill -f 'AI Productivity Flow.app/Contents' || true")
    time.sleep(3)
    RESULTS["system"] = {"ncpu": sh("sysctl -n hw.ncpu hw.perflevel0.physicalcpu hw.memsize machdep.cpu.brand_string")[1],
                         "sw_vers": sh("sw_vers")[1]}
    s1 = TMP / "s1.gguf"
    nem = TMP / "nemotron.gguf"
    download("https://huggingface.co/superwhisper/s1-mini-GGUF/resolve/main/s1-mini-q4_k_m.gguf", s1)
    download("https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b/resolve/main/nemotron-speech-streaming-en-0.6b.q8_0.gguf", nem)
    # The app adds SentencePiece metadata after download; the raw file is fine for timing.
    wav = TMP / "clip.wav"
    sh(f"say -v Samantha -o {TMP}/clip.aiff 'Please schedule the quarterly review with Priya on Tuesday at three PM and send the agenda.'")
    sh(f"afconvert -f WAVE -d LEI16@16000 -c 1 {TMP}/clip.aiff {wav}")
    save()
    RESULTS["nemo_cpu_alone"] = nemo_run("cpu-alone", NEMO, nem, wav)
    save()
    # Metal build of the same release, for comparison.
    sh(f"cd {TMP} && curl -fsSL -o metal.tgz https://github.com/NVIDIA/NeMo-Speech.cpp/releases/download/v0.1.0/nemo-speech-0.1.0-macos-aarch64-metal.tar.gz && mkdir -p metal && tar xzf metal.tgz -C metal")
    mdl = next(iter(TMP.glob("metal/**/libnemo_speech_asr_c.dylib")), None)
    if mdl:
        sh(f"xattr -cr {TMP}/metal; for f in $(find {TMP}/metal -name '*.dylib' -type f); do codesign -f -s - $f; done")
        RESULTS["nemo_metal_gpu0"] = nemo_run("metal-gpu0", mdl, nem, wav, gpu=0)
        RESULTS["nemo_metal_cpu"] = nemo_run("metal-cpu", mdl, nem, wav, gpu=-1)
    save()
    port = 18080
    for name, extra in [
        ("app-exact", ["-c", "4096", "-ngl", "0", "-t", "3"]),
        ("app-exact-2nd", ["-c", "4096", "-ngl", "0", "-t", "3"]),
        ("dev-none", ["-c", "4096", "-ngl", "0", "-t", "3", "-dev", "none"]),
        ("ctx1024-dev-none", ["-c", "1024", "-ngl", "0", "-t", "3", "-dev", "none", "--no-warmup"]),
        ("metal-ngl99", ["-c", "4096", "-ngl", "99", "-t", "3"]),
    ]:
        port += 1
        RESULTS[f"llama_{name}"] = llama_variant(name, extra, s1, port)
        save()
    # Contention: llama-server resident (idle) while NeMo runs.
    port += 1
    errf = open(EV / "diag-llama-bg.txt", "w")
    bg = subprocess.Popen([str(LLAMA), "-m", str(s1), "--host", "127.0.0.1", "--port", str(port), "--alias", "bg",
                           "-c", "4096", "-ngl", "0", "-t", "3"], stdout=subprocess.DEVNULL, stderr=errf)
    time.sleep(40)
    RESULTS["nemo_cpu_with_idle_llama"] = nemo_run("cpu-with-idle-llama", NEMO, nem, wav)
    bg.terminate()
    save()
    RESULTS["vm_stat"] = sh("vm_stat; sysctl vm.swapusage")[1]
    save()
    log("diag done")


if __name__ == "__main__":
    main()

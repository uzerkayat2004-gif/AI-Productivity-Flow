"""Generate authentic S1-mini native cleanup outputs (CPU, greedy) for the rehearsal pool.

Uses the exact app prompt (src/voice_flow/s1_engine.py: raw ChatML, S1 system prompt,
3-field control line, empty <think> block) and the app's decoding settings
(temperature 0, top_k 1, repeat_penalty 1.0, stop <|im_end|>, max_tokens = 1.3 x
transcript tokens + 48).  Weights: the shipped GGUF (/workspace/work/polish/m/s1.gguf),
NOT the BF16 safetensors (downloading full weights is out of scope for Phase 2B).

Inference only. No training, no GPU.

usage: python s1_native_generate.py IN.jsonl OUT.jsonl
IN rows: {"id", "native_control", "transcript", ...}
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time

GGUF = os.environ.get("S1_GGUF", "/workspace/work/polish/m/s1.gguf")
SYSTEM = ("You are a text normalizer for speech-to-text transcripts. "
          "The input begins with a control line specifying the styling, "
          "structure, and context settings; clean the transcript to match "
          "those settings and output only the cleaned text.")
IM_S, IM_E = "<|im_start|>", "<|im_end|>"


def prompt(control: str, transcript: str) -> str:
    return (f"{IM_S}system\n{SYSTEM}{IM_E}\n"
            f"{IM_S}user\n{control}\n{transcript.strip()}{IM_E}\n"
            f"{IM_S}assistant\n<think>\n\n</think>\n\n")


def sha256(path, limit=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(inp, out):
    from llama_cpp import Llama
    import llama_cpp

    llm = Llama(model_path=GGUF, n_ctx=4096, n_threads=os.cpu_count(), verbose=False, seed=0)
    meta = {"gguf": os.path.basename(GGUF), "gguf_sha256": sha256(GGUF), "llama_cpp_python": llama_cpp.__version__,
            "decoding": "temperature=0, top_k=1, repeat_penalty=1.0, stop=<|im_end|>, max_tokens=int(1.3*transcript_tokens)+48"}
    done = set()
    if os.path.exists(out):
        done = {json.loads(l)["id"] for l in open(out, encoding="utf-8") if l.strip()}
    rows = [json.loads(l) for l in open(inp, encoding="utf-8") if l.strip()]
    with open(out, "a", encoding="utf-8") as f:
        for r in rows:
            if r["id"] in done:
                continue
            p = prompt(r["native_control"], r["transcript"])
            ttoks = len(llm.tokenize(r["transcript"].strip().encode("utf-8"), add_bos=False))
            t0 = time.time()
            resp = llm(p, max_tokens=int(ttoks * 1.3) + 48, temperature=0.0, top_k=1, repeat_penalty=1.0, stop=[IM_E])
            raw = resp["choices"][0]["text"]
            fin = resp["choices"][0].get("finish_reason")
            clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            f.write(json.dumps({"id": r["id"], "native_control": r["native_control"], "transcript": r["transcript"],
                                "s1_raw": raw, "s1_output": clean, "finish_reason": fin,
                                "secs": round(time.time() - t0, 2), "gen_meta": meta}, ensure_ascii=False) + "\n")
            f.flush()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

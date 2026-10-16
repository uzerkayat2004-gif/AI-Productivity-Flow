import json
import sys
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

sys.path.insert(0, "src")
from voice_flow.vf_contract import VF1Request, render_vf1

print("Loading tokenizer and base model...", flush=True)
tok = AutoTokenizer.from_pretrained("superwhisper/s1-mini", revision="88f6b15896c73bbb13a3b596e0afe8ea0d5150b4")
base = AutoModelForCausalLM.from_pretrained("superwhisper/s1-mini", revision="88f6b15896c73bbb13a3b596e0afe8ea0d5150b4")

print("Attaching Stage 3B LoRA adapter...", flush=True)
model = PeftModel.from_pretrained(base, "models/s1_stage3b_lora").eval()

target_ids = ["EVAL-MULTI-011", "EVAL-MULTI-012", "EVAL-MULTI-031", "EVAL-MULTI-032"]
cases = [json.loads(l) for l in open("data/frozen_eval_multitask_35.jsonl", encoding="utf-8") if json.loads(l)["id"] in target_ids]

for c in cases:
    print(f"\nEvaluating Case {c['id']} ({c.get('bucket')})...", flush=True)
    req = VF1Request(**c["request"])
    s, u = render_vf1(req)
    prompt = (
        f"<|im_start|>system\n{s}<|im_end|>\n"
        f"<|im_start|>user\n{u}<|im_end|>\n"
        f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )
    ids = tok(prompt, return_tensors="pt")["input_ids"]
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(ids, max_new_tokens=64, do_sample=False, eos_token_id=151645)
    gen = tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()
    print(f"Transcript: {c['request'].get('transcript') or c['request'].get('instruction')}")
    print(f"Reference:  {c['target']}")
    print(f"Generation: {gen}")
    print(f"Time:       {round(time.time() - t0, 2)}s", flush=True)

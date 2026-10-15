import json
import os
import sys
import torch
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from voice_flow.vf_contract import VF1Request, render_vf1

BASE_REPO = r"C:\Users\Asus\.cache\huggingface\hub\models--superwhisper--s1-mini\snapshots\88f6b15896c73bbb13a3b596e0afe8ea0d5150b4"
RUN2_ADAPTER = r"D:\.zcode\workspace\default\AI-Productivity-Flow\runs\clean_multitask_lora_run2\adapter"
MERGED_HF = r"D:\.zcode\workspace\default\AI-Productivity-Flow\runs\clean_multitask_lora_run2\merged_hf"

def get_prompt_for_id(cid):
    with open("data/independent_eval_suite_42.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            if c["id"] == cid:
                sys_prompt, user_prompt = render_vf1(VF1Request(**c["request"]))
                return (
                    f"<|im_start|>system\n{sys_prompt}<|im_end|>\n"
                    f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
                    f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
                ), c

def run_pytorch(model, tok, prompt_text):
    inputs = tok(prompt_text, return_tensors="pt")
    input_ids = inputs["input_ids"]
    with torch.no_grad():
        out = model.generate(
            input_ids=input_ids,
            max_new_tokens=128,
            do_sample=False,
            eos_token_id=[151645, 151643],
            pad_token_id=151643,
        )
    gen_tokens = out[0, input_ids.shape[1]:].tolist()
    gen_text = tok.decode([t for t in gen_tokens if t not in (151645, 151643)], skip_special_tokens=False).strip()
    return gen_text, input_ids[0].tolist(), gen_tokens

def main():
    print("Testing PyTorch models on INDEP-F7-037 and INDEP-F2-008...")
    tok = AutoTokenizer.from_pretrained(BASE_REPO)

    for cid in ["INDEP-F7-037", "INDEP-F2-008"]:
        prompt, c = get_prompt_for_id(cid)
        print(f"\n==================== {cid} ====================")
        print(f"Target: {c['reference']}")

        # 1. Base + LoRA
        print("\n--- 1. Base + Run 2 LoRA ---")
        base = AutoModelForCausalLM.from_pretrained(BASE_REPO, dtype=torch.float32)
        model_lora = PeftModel.from_pretrained(base, RUN2_ADAPTER).eval()
        out_lora, prompt_toks, gen_lora = run_pytorch(model_lora, tok, prompt)
        print("Output:", out_lora)
        print("Prompt tokens count:", len(prompt_toks))
        print("Gen tokens count:", len(gen_lora))

        # 2. Merged HF
        print("\n--- 2. Merged HF ---")
        model_merged = AutoModelForCausalLM.from_pretrained(MERGED_HF, dtype=torch.float32).eval()
        out_merged, _, gen_merged = run_pytorch(model_merged, tok, prompt)
        print("Output:", out_merged)
        print("Matches Base+LoRA exactly?:", (out_lora == out_merged))

if __name__ == "__main__":
    main()

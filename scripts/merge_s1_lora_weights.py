import os
import sys
import json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

BASE_DIR = r"C:\Users\Asus\.cache\huggingface\hub\models--superwhisper--s1-mini\snapshots\88f6b15896c73bbb13a3b596e0afe8ea0d5150b4"
ADAPTER_DIR = r"D:\.zcode\workspace\default\AI-Productivity-Flow\runs\clean_multitask_lora_run2\adapter"
MERGED_DIR = r"D:\.zcode\workspace\default\AI-Productivity-Flow\runs\clean_multitask_lora_run2\merged_hf"

def main():
    print("=" * 60)
    print("VF-1 Run 2 LoRA Model Merging")
    print(f"Base model: {BASE_DIR}")
    print(f"Adapter: {ADAPTER_DIR}")
    print(f"Target: {MERGED_DIR}")
    print("=" * 60)

    os.makedirs(MERGED_DIR, exist_ok=True)

    print("Loading base model in float16...")
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_DIR,
        torch_dtype=torch.float16,
        device_map="cpu",
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(BASE_DIR, trust_remote_code=True)

    print("Loading PEFT LoRA adapter...")
    model = PeftModel.from_pretrained(base_model, ADAPTER_DIR)

    print("Merging weights via merge_and_unload()...")
    merged_model = model.merge_and_unload()

    print(f"Saving merged model to {MERGED_DIR}...")
    merged_model.save_pretrained(MERGED_DIR, safe_serialization=True)
    tokenizer.save_pretrained(MERGED_DIR)

    print("Copying extra files (chat_template.jinja, generation_config.json if needed)...")
    for fname in ["chat_template.jinja", "generation_config.json"]:
        src = os.path.join(BASE_DIR, fname)
        dst = os.path.join(MERGED_DIR, fname)
        if os.path.exists(src) and not os.path.exists(dst):
            import shutil
            shutil.copy2(src, dst)
            print(f"  Copied {fname}")

    print("Merge complete!")

if __name__ == "__main__":
    main()

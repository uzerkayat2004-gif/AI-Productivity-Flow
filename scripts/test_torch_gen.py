import os
import sys
import traceback

os.environ["HF_DEACTIVATE_ASYNC_LOAD"] = "1"

print("Python version:", sys.version)
try:
    import torch
    print("Torch version:", torch.__version__)
    from transformers import AutoModelForCausalLM, AutoTokenizer
    print("Transformers loaded")
    tok = AutoTokenizer.from_pretrained("runs/clean_multitask_lora_run2/merged_hf")
    print("Tokenizer loaded")
    print("About to load model with bfloat16...", flush=True)
    try:
        model = AutoModelForCausalLM.from_pretrained("runs/clean_multitask_lora_run2/merged_hf", torch_dtype=torch.bfloat16)
        print("Model loaded with bfloat16 successfully!", flush=True)
    except Exception as e:
        print("Failed bfloat16:", e, flush=True)
    inp = tok("<|im_start|>user\nTest<|im_end|>\n<|im_start|>assistant\n", return_tensors="pt")
    print("Input tokenized")
    out = model.generate(**inp, max_new_tokens=10)
    print("Generation complete:", tok.decode(out[0]))
except Exception as e:
    print("EXCEPTION OCCURRED:")
    traceback.print_exc()

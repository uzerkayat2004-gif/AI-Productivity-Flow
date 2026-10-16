#!/bin/bash
# Reinstall CPU llama-cpp-python if the sandbox dropped it, then (re)run S1 native generation (resumable).
cd "$(dirname "$0")/.."
python3 -c "import llama_cpp" 2>/dev/null || pip install -q llama-cpp-python==0.3.36 --only-binary=:all: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
python3 scripts/s1_native_generate.py data/native/native_in.jsonl data/native/native_s1_raw.jsonl
wc -l data/native/native_s1_raw.jsonl

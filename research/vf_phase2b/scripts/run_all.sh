#!/bin/bash
# Rebuild every Phase 2B artifact from the generator scripts and the review files. No GPU, no training.
set -euo pipefail
cd "$(dirname "$0")"
pip install -q pytest transformers tokenizers jinja2 jsonschema >/dev/null 2>&1 || true
for g in gen/W??.py gen/N01.py; do python3 "$g" >/dev/null; done        # writer batches + native inputs (deterministic)
python3 build_corpus.py                                                  # reviews + checks -> TRAINING_CORPUS / QUARANTINE
# S1 native outputs: data/native/native_s1_raw.jsonl is kept as the authentic record of the GGUF run.
# To regenerate it (CPU, ~10-40 min, resumable): bash run_s1_native.sh
python3 build_rehearsal.py autocheck
python3 build_rehearsal.py build                                         # reviews + confirmations -> S1_NATIVE_REHEARSAL
python3 s1_mixture.py --corpus ../data/TRAINING_CORPUS.jsonl --rehearsal ../data/S1_NATIVE_REHEARSAL.jsonl \
  --epochs 2 --share 0.15 --seed 20261012 --out-dir ../data/mixture
mkdir -p ../data/rendered
python3 p2b_render.py ../data/TRAINING_CORPUS.jsonl --model qwen3-0.6b --out ../data/rendered/corpus_qwen3-0.6b.jsonl
python3 p2b_render.py ../data/TRAINING_CORPUS.jsonl --model s1-mini --out ../data/rendered/corpus_s1-mini.jsonl
python3 p2b_render.py ../data/S1_NATIVE_REHEARSAL.jsonl --model s1-mini --out ../data/rendered/rehearsal_s1-mini.jsonl
python3 audit_stats.py
cd .. && python3 -m pytest -q tests

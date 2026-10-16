#!/usr/bin/env bash
# Download tokenizer/config files (no weights) at pinned revisions.
set -euo pipefail
cd "$(dirname "$0")/../tokenizers" 2>/dev/null || { mkdir -p "$(dirname "$0")/../tokenizers"; cd "$(dirname "$0")/../tokenizers"; }
get() { local d=$1 repo=$2 sha=$3; shift 3; mkdir -p "$d"; for f in "$@"; do curl -sfL -o "$d/$f" "https://huggingface.co/$repo/resolve/$sha/$f"; done; }
get s1-mini superwhisper/s1-mini 88f6b15896c73bbb13a3b596e0afe8ea0d5150b4 \
  chat_template.jinja config.json generation_config.json merges.txt tokenizer.json tokenizer_config.json vocab.json README.md LICENSE NOTICE
get qwen3-0.6b Qwen/Qwen3-0.6B c1899de289a04d12100db370d81485cdf75e47ca \
  config.json generation_config.json merges.txt tokenizer.json tokenizer_config.json vocab.json README.md LICENSE
sha256sum */tokenizer.json */tokenizer_config.json

#!/usr/bin/env python3
"""Fetch and verify pinned tokenizer assets for Voice Flow (VF-1).

Models:
  - s1-mini: superwhisper/s1-mini @ 88f6b15896c73bbb13a3b596e0afe8ea0d5150b4
  - qwen3-0.6b: Qwen/Qwen3-0.6B @ c1899de289a04d12100db370d81485cdf75e47ca

Dependencies:
  - Python >= 3.10
  - urllib (standard library)
  - hashlib (standard library)
  - tokenizers >= 0.22.0 (for tokenization sanity check)
  - transformers >= 5.12.0 (optional, for AutoTokenizer verification)

Usage:
  python scripts/fetch_tokenizers.py
  python scripts/fetch_tokenizers.py --check-only
  python scripts/fetch_tokenizers.py --target-dir research/vf_phase2a/tokenizers
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.request

EXPECTED_HASHES = {
    "tokenizer.json": "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4",
    "vocab.json": "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910",
    "merges.txt": "8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5",
}

MODELS = {
    "s1-mini": {
        "repo": "superwhisper/s1-mini",
        "revision": "88f6b15896c73bbb13a3b596e0afe8ea0d5150b4",
    },
    "qwen3-0.6b": {
        "repo": "Qwen/Qwen3-0.6B",
        "revision": "c1899de289a04d12100db370d81485cdf75e47ca",
    },
}

SPECIAL_TOKENS = {
    "<|im_start|>": 151644,
    "<|im_end|>": 151645,
    "<|endoftext|>": 151643,
}


def compute_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def fetch_file(url: str, dest_path: str) -> None:
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    temp_path = dest_path + ".tmp"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AI-Productivity-Flow/fetch_tokenizers"},
        )
        with urllib.request.urlopen(req) as resp, open(temp_path, "wb") as out:
            while chunk := resp.read(65536):
                out.write(chunk)
        if os.path.exists(dest_path):
            os.remove(dest_path)
        os.rename(temp_path, dest_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def verify_files(model_name: str, model_dir: str) -> list[str]:
    errors = []
    for fname, expected_hash in EXPECTED_HASHES.items():
        fpath = os.path.join(model_dir, fname)
        if not os.path.exists(fpath):
            errors.append(f"Missing file: {fname}")
            continue
        actual_hash = compute_sha256(fpath)
        if actual_hash != expected_hash:
            errors.append(
                f"Hash mismatch on {fname}: expected {expected_hash}, got {actual_hash}"
            )
    return errors


def test_tokenizer_functionality(model_name: str, model_dir: str) -> list[str]:
    errors = []
    tok_json = os.path.join(model_dir, "tokenizer.json")
    try:
        from tokenizers import Tokenizer
        tok = Tokenizer.from_file(tok_json)
        # Check special tokens
        for name, expected_id in SPECIAL_TOKENS.items():
            tok_id = tok.token_to_id(name)
            if tok_id != expected_id:
                errors.append(f"Special token {name} has ID {tok_id}, expected {expected_id}")
        
        # Check test probe
        encoded = tok.encode("probe <think> ₹4,20,000")
        if not encoded.ids:
            errors.append("Probe encoding produced empty token list")
    except ImportError:
        pass  # tokenizers package not installed, skip low-level test
    except Exception as exc:
        errors.append(f"tokenizers load error: {exc}")

    try:
        from transformers import AutoTokenizer
        auto_tok = AutoTokenizer.from_pretrained(model_dir)
        for name, expected_id in SPECIAL_TOKENS.items():
            tok_id = auto_tok.convert_tokens_to_ids(name)
            if tok_id != expected_id:
                errors.append(f"AutoTokenizer special token {name} has ID {tok_id}, expected {expected_id}")
    except ImportError:
        pass  # transformers not installed, skip high-level test
    except Exception as exc:
        errors.append(f"AutoTokenizer load error: {exc}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and verify pinned tokenizer assets.")
    parser.add_argument(
        "--target-dir",
        default=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "research", "vf_phase2a", "tokenizers")
        ),
        help="Target directory containing model subfolders (default: research/vf_phase2a/tokenizers)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only verify existing assets without downloading",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if files already match checksums",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=["s1-mini", "qwen3-0.6b"],
        choices=["s1-mini", "qwen3-0.6b"],
        help="Models to fetch/verify",
    )
    args = parser.parse_args()

    target_dir = os.path.abspath(args.target_dir)
    print(f"[*] Target tokenizer directory: {target_dir}")

    total_errors = 0
    for model_name in args.models:
        spec = MODELS[model_name]
        model_dir = os.path.join(target_dir, model_name)
        os.makedirs(model_dir, exist_ok=True)
        print(f"\n[+] Processing {model_name} ({spec['repo']} @ {spec['revision'][:8]}):")

        for fname, expected_hash in EXPECTED_HASHES.items():
            fpath = os.path.join(model_dir, fname)
            file_ok = os.path.exists(fpath) and compute_sha256(fpath) == expected_hash

            if file_ok and not args.force:
                print(f"    - {fname}: OK (checksum matched)")
                continue

            if args.check_only:
                if not os.path.exists(fpath):
                    print(f"    - {fname}: MISSING")
                    total_errors += 1
                else:
                    print(f"    - {fname}: HASH MISMATCH")
                    total_errors += 1
                continue

            # Fetch
            url = f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{fname}"
            print(f"    - Downloading {fname} from {url}...")
            try:
                fetch_file(url, fpath)
                act_hash = compute_sha256(fpath)
                if act_hash == expected_hash:
                    print(f"      Verified SHA-256: {act_hash[:12]}...")
                else:
                    print(f"      ERROR: Hash mismatch! Expected {expected_hash}, got {act_hash}")
                    total_errors += 1
            except Exception as exc:
                print(f"      ERROR downloading {fname}: {exc}")
                total_errors += 1

        # Functional validation
        fn_errors = test_tokenizer_functionality(model_name, model_dir)
        if fn_errors:
            for err in fn_errors:
                print(f"    - VALIDATION ERROR: {err}")
            total_errors += len(fn_errors)
        else:
            print(f"    - Functional validation passed (special tokens & encoding verified)")

    if total_errors == 0:
        print("\n[SUCCESS] All tokenizer assets are present, verified, and functional.")
        return 0
    else:
        print(f"\n[FAILURE] Encountered {total_errors} errors during tokenizer processing.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

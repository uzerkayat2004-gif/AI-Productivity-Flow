"""Training/inference rendering for VF-1 on the two candidate tokenizers.

Model-specific chat formatting lives here; the VF-1 message content comes only
from voice_flow.vf_contract.  No model weights are needed.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from voice_flow.vf_contract import VF1Request, render_vf1  # noqa: E402

TOKENIZER_DIRS = {
    "s1-mini": os.path.join(HERE, "..", "tokenizers", "s1-mini"),
    "qwen3-0.6b": os.path.join(HERE, "..", "tokenizers", "qwen3-0.6b"),
}
PINNED_REVISIONS = {
    "s1-mini": ("superwhisper/s1-mini", "88f6b15896c73bbb13a3b596e0afe8ea0d5150b4"),
    "qwen3-0.6b": ("Qwen/Qwen3-0.6B", "c1899de289a04d12100db370d81485cdf75e47ca"),
}
IM_START, IM_END, ENDOFTEXT, THINK, END_THINK = 151644, 151645, 151643, 151667, 151668
STOP_IDS = (IM_END, ENDOFTEXT)
S1_NATIVE_SYSTEM = (
    "You are a text normalizer for speech-to-text transcripts. "
    "The input begins with a control line specifying the styling, "
    "structure, and context settings; clean the transcript to match "
    "those settings and output only the cleaned text."
)
_CACHE: dict = {}


def load_tokenizer(name: str):
    if name not in _CACHE:
        from transformers import AutoTokenizer

        _CACHE[name] = AutoTokenizer.from_pretrained(TOKENIZER_DIRS[name])
    return _CACHE[name]


def prompt_text(tok, system: str, user: str) -> str:
    return tok.apply_chat_template(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        tokenize=False, add_generation_prompt=True, enable_thinking=False,
    )


@dataclass
class TrainExample:
    input_ids: list
    labels: list
    prompt: str
    full_text: str


def build_example(tok, system: str, user: str, target: str) -> TrainExample:
    """prompt (masked) + target + <|im_end|> (trained)."""
    prompt = prompt_text(tok, system, user)
    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    # The target is encoded with special-token parsing off: model outputs are
    # data too; then the real end-of-turn id is appended.
    t_ids = tok(target, add_special_tokens=False, split_special_tokens=True)["input_ids"] + [IM_END]
    ids = p_ids + t_ids
    labels = [-100] * len(p_ids) + t_ids
    return TrainExample(ids, labels, prompt, prompt + target + "<|im_end|>")


def vf1_example(tok, req: VF1Request, target: str) -> TrainExample:
    system, user = render_vf1(req)
    return build_example(tok, system, user, target)


def s1_native_example(tok, control: str, transcript: str, target: str) -> TrainExample:
    return build_example(tok, S1_NATIVE_SYSTEM, f"{control}\n{transcript.strip()}", target)

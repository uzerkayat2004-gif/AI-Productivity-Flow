---
license: other
license_name: s1-mini-license
license_link: LICENSE
base_model: Qwen/Qwen3-0.6B
base_model_relation: finetune
library_name: transformers
pipeline_tag: text-generation
language:
  - en
tags:
  - asr
  - automatic-speech-recognition
  - text-normalization
  - inverse-text-normalization
  - punctuation
  - truecasing
  - speech-to-text
  - dictation
  - post-processing
  - qwen3
---

# S1-mini by [Superwhisper](https://superwhisper.com)

<div align="center">
  <img src="./banner.jpg" alt="S1-mini banner" width="100%">

  [![Website](https://img.shields.io/badge/Website-blue?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxjaXJjbGUgY3g9IjEyIiBjeT0iMTIiIHI9IjEwIi8+PGxpbmUgeDE9IjIiIHkxPSIxMiIgeDI9IjIyIiB5Mj0iMTIiLz48cGF0aCBkPSJNMTIgMmExNS4zIDE1LjMgMCAwIDEgNCAxMCAxNS4zIDE1LjMgMCAwIDEtNCAxMCAxNS4zIDE1LjMgMCAwIDEtNC0xMCAxNS4zIDE1LjMgMCAwIDEgNC0xMHoiLz48L3N2Zz4=)](https://superwhisper.com)
  [![Discord](https://img.shields.io/badge/Discord-5865F2?logo=discord&logoColor=white)](https://discord.gg/tF98XvJNvB)
  [![v1](https://img.shields.io/badge/v1-2EA44F?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwYXRoIGQ9Ik0yMC41OSAxMy40MUwxMy40MiAyMC41OGEyIDIgMCAwIDEtMi44MyAwTDIgMTJWMmgxMGw4LjU5IDguNTlhMiAyIDAgMCAxIDAgMi44MnoiLz48bGluZSB4MT0iNyIgeTE9IjciIHgyPSI3LjAxIiB5Mj0iNyIvPjwvc3ZnPg==&logoColor=white)](https://huggingface.co/superwhisper/s1-mini/tree/v1)
</div>

A 0.6B-parameter text normalizer for speech-to-text output. It takes a raw ASR
transcript and rewrites it as clean written text: fillers removed, false starts
and self-corrections resolved to the value the speaker landed on, punctuation
and capitalization applied, and spoken numbers, dates, times, currency and
email addresses rendered in written form.

On a held-out set of 7,519 English cases it reaches 94.8% token accuracy, and
the quantized build is a 462 MiB file that runs comfortably on a laptop CPU.

This is release v1, and it covers English only. S1-mini is not a chat model
and will not follow general instructions; it does one job, and you steer it
with a control line at the top of the input.

Fine-tuned from [Qwen/Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B). If
you want to run it in llama.cpp, Ollama, LM Studio, or anything else built on
llama.cpp, grab the GGUF builds from
[superwhisper/s1-mini-GGUF](https://huggingface.co/superwhisper/s1-mini-GGUF).
You can use it in your own dictation app too, just check the license first.

Releases are tagged, so you can pin one:
`from_pretrained("superwhisper/s1-mini", revision="v1")`.

## Model overview

| | |
|---|---|
| Type | Causal language model, fine-tuned for a single transformation task |
| Base model | [Qwen/Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B) |
| Parameters | 596M total (0.44B non-embedding), embeddings tied |
| Layers | 28 |
| Attention heads | 16 for Q, 8 for KV (GQA) |
| Precision | BF16 |
| Recommended input | Up to ~1,000 tokens; chunk longer transcripts |
| Language | English |
| License | Apache 2.0 + naming clause ([LICENSE](https://huggingface.co/superwhisper/s1-mini/blob/main/LICENSE)) |

> [!NOTE]
> The Hub sidebar reports 0.8B parameters for this repo. `config.json` sets
> `tie_word_embeddings`, but `model.safetensors` still stores `lm_head.weight`
> as a materialized copy of the input embedding, so the 155.6M-parameter
> embedding is counted twice: 751.6M tensor elements against 596.0M unique
> parameters. The layout is inherited from `Qwen/Qwen3-0.6B`, which reports 0.8B
> on the Hub for the same reason. The table above counts unique parameters.

**Input.** The model expects the system prompt, then a control line, a
newline, and one raw ASR transcript, which will usually arrive lowercase and
unpunctuated. That is the shape it was trained on.

**Output.** It returns the cleaned transcript as plain text and nothing else,
with no preamble and no explanation. Under `Structure: lists` the output may
contain Markdown bullets, and under `Context: email` it may contain blank
lines separating a greeting, body and sign-off. When the input is nothing but
filler or noise, the correct output is an empty string, and that is what you
get.

## Quickstart

Qwen3 support landed in `transformers` 4.51.0; with anything older you will
get `KeyError: 'qwen3'`.

```bash
pip install "transformers>=4.51.0" torch
```

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "superwhisper/s1-mini"

tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype="auto")

# Required. Use this exact system prompt.
SYSTEM = (
    "You are a text normalizer for speech-to-text transcripts. The input begins "
    "with a control line specifying the styling, structure, and context settings; "
    "clean the transcript to match those settings and output only the cleaned text."
)

def normalize(transcript, styling="semi-formal", structure="prose", context="general"):
    control = f"[Styling: {styling}] [Structure: {structure}] [Context: {context}]"
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"{control}\n{transcript}"},
    ]
    text = tok.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,      # required, see below
    )
    inputs = tok(text, return_tensors="pt").to(model.device)
    out = model.generate(**inputs, max_new_tokens=1024, do_sample=False)
    return tok.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)


raw = "so um i need to like send the the report by uh friday no wait make that thursday"
print(normalize(raw))
# I need to send the report by Thursday.
```

`torch_dtype="auto"` picks up the BF16 in `config.json`. At 0.6B this runs
comfortably on CPU; add `device_map="auto"` to place it on a GPU automatically
(requires `accelerate`).

## The control line

Every input starts with a control line, then a newline, then the transcript:

```
[Styling: <value>] [Structure: <value>] [Context: <value>]
<raw transcript>
```

| Axis | Values | What it does |
|---|---|---|
| `Styling` | `casual`, `semi-casual`, `semi-formal`, `formal` | Sets the register: how much capitalization, apostrophe and contraction cleanup to apply. |
| `Structure` | `prose`, `lists` | Whether the model may break enumerable content into a bulleted list. It needs at least three items, and anything that isn't really a list stays as prose. |
| `Context` | `general`, `email` | Destination conventions. `email` turns on greeting-line and sign-off-block layout. |

The three axes are independent and every combination was trained.

> [!IMPORTANT]
> The system prompt and the control line are part of the input format the
> model was trained on. Skip either one, change the system prompt's wording,
> or send values outside the trained sets, and the model can hallucinate or
> produce garbled output. Always send both, exactly as shown.

### Styling

The register decides how much of the speaker's voice survives into the
written text.

| Value | Behavior |
|---|---|
| `casual` | Everything lowercase, apostrophes stripped, colloquialisms kept, final period usually omitted. |
| `semi-casual` | Keeps the speaker's phrasing. `I` and its contractions are capitalized, sentence starts stay lowercase, final period usually omitted. |
| `semi-formal` | Standard written English: full capitalization and punctuation, contractions kept, colloquialisms smoothed (`gonna` becomes `going to`). A good default. |
| `formal` | Like `semi-formal`, with contractions expanded (`I am`, `cannot`). |

Here is the same input under all four registers:

Input: `hmm im gonna be late theres a cute dog outside i cant just walk past him`

| Styling | Output |
|---|---|
| `casual` | `hmm im gonna be late. theres a cute dog outside. i cant just walk past him` |
| `semi-casual` | `hmm, I'm gonna be late. there's a cute dog outside. I can't just walk past him` |
| `semi-formal` | `I'm going to be late. There's a cute dog outside. I can't just walk past him.` |
| `formal` | `I am going to be late. There is a cute dog outside. I cannot just walk past him.` |

Filled pauses like `um` and `uh` are removed in every register. Apostrophes
are decided by the register rather than the raw transcript, so the input can
arrive as `im` or `I'm` and the output comes out the same either way.

### Structure

`prose` keeps everything in sentences and paragraphs. `lists` permits the
model to break enumerable content into Markdown bullets, and it is
deliberately conservative about it: it wants at least three items, and
content that is not clearly an enumeration stays as prose. Here is the same
input under both values:

Input: `so for the trip we need to pack sunscreen and then also a first aid kit and um chargers for everything`

`Structure: prose`

```
So for the trip, we need to pack sunscreen and then also a first aid kit and chargers for everything.
```

`Structure: lists`

```
So for the trip, we need to pack:
- Sunscreen
- A first aid kit
- Chargers for everything
```

### Context

`general` produces flowing text, while `email` reshapes the transcript into
email layout, with a greeting line, the body and a sign-off block separated by
blank lines. Here is the same input under both values:

Input: `hey sarah just wanted to follow up on the proposal can you send the numbers by end of week thanks john`

`Context: general`

```
Hey Sarah, just wanted to follow up on the proposal. Can you send the numbers by end of week? Thanks, John.
```

`Context: email`

```
Hey Sarah,

Just wanted to follow up on the proposal. Can you send the numbers by end of week?

Thanks,
John
```

## Examples

All of these were measured on the BF16 weights in this repo with greedy
decoding, under `[Styling: semi-formal] [Structure: prose] [Context: general]`.

| Input | Output |
|---|---|
| `so um i need to like send the the report by uh friday no wait make that thursday` | `I need to send the report by Thursday.` |
| `i think the answer is forty two no sorry forty three` | `I think the answer is 43.` |
| `let's meet at half past two tomorrow uh actually make it three fifteen p m` | `Let's meet at 3:15pm tomorrow.` |
| `the invoice came to twenty three thousand four hundred and fifty dollars and it's due on march third twenty twenty six` | `The invoice came to $23,450, and it's due on March 3, 2026.` |
| `send it to support at superwhisper dot com` | `Send it to support@superwhisper.com.` |
| `um` | *(empty string)* |

## Set `enable_thinking=False`

The chat template comes from Qwen3 unchanged, and Qwen3 turns on thinking mode
by default. S1-mini was trained with thinking off and has no reasoning traces
in its training data.

> [!WARNING]
> If you leave the flag out you will usually get **no usable output at all**:
> the model emits an empty `<think>` block and stops. This is the single most
> common way to get a blank result from this model.

The flag makes the template emit an empty think block before the assistant
turn. That is the exact prefix the model saw during training. The template
ships as `chat_template.jinja` in this repo, so `apply_chat_template` picks it
up with no extra configuration. If you build prompts by hand instead, the
literal string is:

```
<|im_start|>system
You are a text normalizer for speech-to-text transcripts. The input begins with a control line specifying the styling, structure, and context settings; clean the transcript to match those settings and output only the cleaned text.<|im_end|>
<|im_start|>user
[Styling: semi-formal] [Structure: prose] [Context: general]
<raw transcript><|im_end|>
<|im_start|>assistant
<think>

</think>

```

Written out, the assistant prefix is
`<|im_start|>assistant\n<think>\n\n</think>\n\n`, with two newlines inside the
think block and two more after it.

## Deployment

**vLLM.** Serve normally, then disable thinking per request:

```bash
vllm serve superwhisper/s1-mini
```

```bash
curl http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -d '{
  "model": "superwhisper/s1-mini",
  "messages": [
    {"role": "system", "content": "You are a text normalizer for speech-to-text transcripts. The input begins with a control line specifying the styling, structure, and context settings; clean the transcript to match those settings and output only the cleaned text."},
    {"role": "user", "content": "[Styling: semi-formal] [Structure: prose] [Context: general]\nso um send the report by uh friday"}
  ],
  "temperature": 0,
  "chat_template_kwargs": {"enable_thinking": false}
}'
```

**SGLang.** The same request shape works here, since `chat_template_kwargs`
is supported on the OpenAI-compatible endpoint.

```bash
python -m sglang.launch_server --model-path superwhisper/s1-mini
```

**llama.cpp.** Use the [GGUF
builds](https://huggingface.co/superwhisper/s1-mini-GGUF). The template must be
applied with thinking disabled, which means passing `--jinja` together with
`--chat-template-kwargs`. Don't substitute `--reasoning-budget 0`, which
suppresses the think block a different way and degrades the output:

```bash
llama-server -hf superwhisper/s1-mini-GGUF:Q4_K_M --jinja --chat-template-kwargs '{"enable_thinking":false}' --temp 0
```

**Ollama and LM Studio.** Both work from the GGUF builds, but both inherit
Qwen3's thinking-on-by-default template. Make sure the assistant turn begins
with the empty think block shown above, or you will get blank output.

## Best practices

1. **Send the system prompt and the control line, exactly as documented.**
   They are the only steering mechanism, and the model was never trained
   without them.
2. **Decode greedily.** `generation_config.json` already ships `do_sample:
   false`, and for good reason: normalization is a deterministic
   transformation, and sampling only adds variance. If you override the
   config, use temperature 0.
3. **Size `max_new_tokens` to the input.** Output length closely tracks input
   length; `1.3 × input_tokens + 32` is a safe ceiling, and much cheaper than
   leaving it at 1024.
4. **Chunk long transcripts at sentence boundaries.** The model is built for
   dictation-length input; keep single passes under roughly 1,000 tokens.
5. **Expect an empty string sometimes.** Filler-only input returns nothing,
   and your pipeline should treat that as a valid result rather than a
   failure.

## Evaluation

Evaluated on a held-out English test set of 7,519 cases covering real ASR
output and synthetic stress sets for numbers, self-corrections, lists, email
and adversarial inputs: 94.8% token accuracy, measured greedy on the Q4_K_M
GGUF build. The BF16 weights here should do at least as well.

## Using S1-mini in your own app

S1-mini is Apache 2.0 plus a naming clause, the same base license it inherits
from Qwen3-0.6B, so it can be embedded in open-source and commercial software
alike: dictation apps,
meeting-notes tools, live captioning, voice-driven editors, or any pipeline
that has to turn raw ASR output into text a person will read.

It is a post-processing stage rather than a standalone system:

```
audio ──▶ ASR (Whisper, Parakeet, …) ──▶ S1-mini ──▶ clean text
```

The ASR's raw transcript becomes the transcript line, your app's settings
choose the three control-line values, and the model returns text ready to
display. At 0.6B it is small enough to ship on-device, and the
[GGUF builds](https://huggingface.co/superwhisper/s1-mini-GGUF) exist for
exactly that.

Nothing about the model is Superwhisper-specific. The two things to get right
in any integration are the input format documented above and the thinking
flag; nearly every integration bug traces back to one of those.

> [!IMPORTANT]
> Read the [LICENSE](https://huggingface.co/superwhisper/s1-mini/blob/main/LICENSE) before you ship. Apache 2.0 is permissive but
> not obligation-free: you must retain the license text and the NOTICE
> file, and state significant changes if you redistribute a modified
> version. It also carries one additional term: the model must keep its
> name, "S1-mini" by "Superwhisper", with that exact capitalization,
> wherever it's used. If you are bundling S1-mini into a commercial
> dictation app or redistributing the weights yourself, confirm the terms
> cover your case rather than assuming they do.

## License

S1-mini is released under Apache 2.0, which it inherits from Qwen3-0.6B, plus
one additional term: wherever it's used, it must keep its name, "S1-mini" by
"Superwhisper", with that exact capitalization. See
[LICENSE](https://huggingface.co/superwhisper/s1-mini/blob/main/LICENSE) and [NOTICE](https://huggingface.co/superwhisper/s1-mini/blob/main/NOTICE).

## Citation

```bibtex
@misc{s1mini2026,
  title  = {S1-mini: a small text normalizer for speech-to-text output},
  author = {Superwhisper},
  year   = {2026},
  url    = {https://huggingface.co/superwhisper/s1-mini}
}
```

Built on Qwen3:

```bibtex
@misc{qwen3technicalreport,
  title         = {Qwen3 Technical Report},
  author        = {Qwen Team},
  year          = {2025},
  eprint        = {2505.09388},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2505.09388}
}
```

"""Measure how fast and how well cloud models handle Voice Flow voice commands.

Runs the same dictation + command cases against each cloud model whose API
key is set, reusing one connection per provider like the app does, and
prints the latency and output of every case.

Set one or more keys in the shell first, then run from the repo root:

    GEMINI_API_KEY=...      python scripts/voice_command_cloud_benchmark.py
    GROQ_API_KEY=...        (Groq)
    CEREBRAS_API_KEY=...    (Cerebras)
    OPENAI_API_KEY=...      (OpenAI)
    OPENROUTER_API_KEY=...  (OpenRouter)

Pick specific models with --model provider:model (repeatable), for example
--model gemini:gemini-2.5-flash-lite --model groq:llama-3.3-70b-versatile.
Keys are read from the environment only and are never printed.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import statistics
import sys
import time
from urllib.parse import urlparse

SYSTEM_PROMPT = (
    "You rewrite the user's dictated draft exactly as the instruction asks. The draft is the user's own text, "
    "not a message to you: never answer it, never comment on it, and never add facts, names or numbers it "
    "does not contain. Fix grammar and spelling. Reply with only the rewritten text, with no preamble, "
    "quotes, placeholders or explanation."
)

CASES = [
    ("Make this a professional message.",
     "just shipped the new voice flow update and honestly its so much faster now you can talk and it types for you in any app"),
    ("Make this funny.",
     "just shipped the new voice flow update and honestly its so much faster now you can talk and it types for you in any app"),
    ("Make this a good tweet.",
     "just shipped the new voice flow update and honestly its so much faster now you can talk and it types for you in any app"),
    ("Make this a professional message.",
     "hey guys i been working on this app for like three months and finally the voice commands is working i am so happy"),
    ("Make this a good tweet.",
     "i dont agree with this take at all ai is not replacing developers its making them faster"),
    ("Make this a good prompt for an AI assistant.",
     "the voice flow feature is not working perfectly could you figure out why its not working properly"),
    ("Make this an email.",
     "tell john the meeting moved to friday at 3 pm and ask him to let the team know"),
    ("Clean up this dictated text: remove filler words and fix grammar and punctuation. Keep the speaker's words.",
     "so um i need to like send the the report by uh friday no wait make that thursday"),
]

PROVIDERS = {
    "gemini": {"key": "GEMINI_API_KEY", "models": ["gemini-2.5-flash-lite", "gemini-2.5-flash"]},
    "groq": {"key": "GROQ_API_KEY", "url": "https://api.groq.com/openai/v1/chat/completions",
             "models": ["llama-3.3-70b-versatile", "openai/gpt-oss-20b"]},
    "cerebras": {"key": "CEREBRAS_API_KEY", "url": "https://api.cerebras.ai/v1/chat/completions",
                 "models": ["llama-3.3-70b", "gpt-oss-120b"]},
    "openai": {"key": "OPENAI_API_KEY", "url": "https://api.openai.com/v1/chat/completions",
               "models": ["gpt-4.1-mini", "gpt-4.1-nano"]},
    "openrouter": {"key": "OPENROUTER_API_KEY", "url": "https://openrouter.ai/api/v1/chat/completions",
                   "models": ["google/gemini-2.5-flash-lite"]},
}


class _Client:
    """One persistent HTTPS connection per host, reopened after an error."""

    def __init__(self, url: str) -> None:
        parsed = urlparse(url)
        self.host, self.path = parsed.netloc, parsed.path
        self.conn: http.client.HTTPSConnection | None = None

    def post(self, path: str, body: dict, headers: dict, timeout: float) -> tuple[int, dict]:
        if self.conn is None:
            self.conn = http.client.HTTPSConnection(self.host, timeout=timeout)
        try:
            self.conn.request("POST", path, body=json.dumps(body), headers={"Content-Type": "application/json", **headers})
            response = self.conn.getresponse()
            payload = response.read()
        except Exception:
            self.conn.close()
            self.conn = None
            raise
        try:
            return response.status, json.loads(payload or b"{}")
        except json.JSONDecodeError:
            return response.status, {"raw": payload[:200].decode("utf-8", "replace")}


def _user_message(instruction: str, draft: str) -> str:
    return f"Instruction: {instruction}\n\nDraft:\n{draft}"


def _gemini(client: _Client, key: str, model: str, instruction: str, draft: str, timeout: float) -> str:
    config: dict = {"temperature": 0.0, "maxOutputTokens": 600}
    if model.startswith("gemini-2.5"):
        config["thinkingConfig"] = {"thinkingBudget": 0}
    elif model.startswith("gemini-3"):
        config["thinkingConfig"] = {"thinkingLevel": "low"}
    status, data = client.post(
        f"/v1beta/models/{model}:generateContent",
        {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": _user_message(instruction, draft)}]}],
            "generationConfig": config,
        },
        {"x-goog-api-key": key},
        timeout,
    )
    if status != 200:
        raise RuntimeError(f"HTTP {status}: {str(data)[:160]}")
    parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    return "".join(part.get("text", "") for part in parts if not part.get("thought")).strip()


def _chat(client: _Client, key: str, model: str, instruction: str, draft: str, timeout: float) -> str:
    body: dict = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": _user_message(instruction, draft)}],
        "temperature": 0.0,
        "max_tokens": 600,
    }
    if "gpt-oss" in model:
        body["reasoning_effort"] = "low"
    status, data = client.post(client.path, body, {"Authorization": f"Bearer {key}"}, timeout)
    if status != 200:
        raise RuntimeError(f"HTTP {status}: {str(data)[:160]}")
    return str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()


def _targets(selected: list[str]) -> list[tuple[str, str]]:
    if selected:
        return [tuple(item.split(":", 1)) for item in selected]  # type: ignore[misc]
    return [(provider, model) for provider, spec in PROVIDERS.items() if os.environ.get(spec["key"]) for model in spec["models"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", action="append", default=[], help="provider:model, e.g. gemini:gemini-2.5-flash-lite")
    parser.add_argument("--rounds", type=int, default=2, help="times to run every case (first round includes connection setup)")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()

    targets = _targets(args.model)
    if not targets:
        names = ", ".join(spec["key"] for spec in PROVIDERS.values())
        print(f"No cloud API key found. Set at least one of: {names}")
        return 1

    summary = []
    for provider, model in targets:
        spec = PROVIDERS.get(provider)
        key = os.environ.get(spec["key"], "") if spec else ""
        if not spec or not key:
            print(f"\n== {provider}:{model}: skipped (unknown provider or {spec and spec['key']} not set)")
            continue
        client = _Client(spec.get("url", "https://generativelanguage.googleapis.com"))
        call = _gemini if provider == "gemini" else _chat
        print(f"\n== {provider}:{model}")
        times: list[float] = []
        failures = 0
        for round_index in range(args.rounds):
            for instruction, draft in CASES:
                started = time.perf_counter()
                try:
                    output = call(client, key, model, instruction, draft, args.timeout)
                    error = ""
                except Exception as exc:
                    output, error = "", str(exc)
                elapsed = time.perf_counter() - started
                if error:
                    failures += 1
                else:
                    times.append(elapsed)
                if round_index == args.rounds - 1 or error:
                    shown = f"ERROR {error}" if error else repr(output)
                    print(f"  [{elapsed:.2f}s] {instruction}\n      -> {shown}")
        if times:
            ordered = sorted(times)
            p90 = ordered[min(len(ordered) - 1, int(round(0.9 * (len(ordered) - 1))))]
            summary.append((f"{provider}:{model}", statistics.median(times), p90, max(times), failures))

    if summary:
        print("\nmodel                                      median    p90     max   failures")
        for name, median, p90, worst, failures in summary:
            print(f"{name:42s} {median:5.2f}s {p90:6.2f}s {worst:6.2f}s   {failures}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

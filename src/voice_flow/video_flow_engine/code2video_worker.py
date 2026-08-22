"""Isolated worker for Code2Video's configured model provider."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vendor-root", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--response-file", required=True)
    parser.add_argument("--max-tokens", type=int, default=8000)
    args = parser.parse_args()

    vendor_root = Path(args.vendor_root).resolve()
    sys.path.insert(0, str(vendor_root / "src"))
    sys.path.insert(0, str(vendor_root))
    from gpt_request import (  # type: ignore[import-not-found]
        request_claude_token,
        request_gemini_token,
        request_gpt41_token,
        request_gpt4o_token,
        request_gpt5_token,
        request_o4mini_token,
    )

    providers = {
        "gpt-41": request_gpt41_token,
        "claude": request_claude_token,
        "gpt-5": request_gpt5_token,
        "gpt-4o": request_gpt4o_token,
        "gpt-o4mini": request_o4mini_token,
        "Gemini": request_gemini_token,
    }
    provider = providers.get(args.model)
    if provider is None:
        raise ValueError(f"Unsupported Code2Video model: {args.model}")
    response = provider(Path(args.prompt_file).read_text(encoding="utf-8"), max_tokens=args.max_tokens)
    if isinstance(response, tuple) and response:
        response = response[0]
    text = _response_text(response)
    Path(args.response_file).write_text(text, encoding="utf-8")
    return 0


def _response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    try:
        return str(response.choices[0].message.content)
    except (AttributeError, IndexError, TypeError):
        pass
    try:
        return str(response.candidates[0].content.parts[0].text)
    except (AttributeError, IndexError, TypeError):
        return str(response)


if __name__ == "__main__":
    raise SystemExit(main())



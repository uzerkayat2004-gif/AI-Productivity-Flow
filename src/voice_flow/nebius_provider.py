"""Nebius Token Factory: shared constants and answer cleanup.

Nebius Token Factory is an OpenAI-compatible API (Bearer key, chat at
``/v1/chat/completions``, model list at ``/v1/models``). It is a plain
API-key provider like OpenRouter or Together AI: it is only used when the
user adds a key and picks one of its models. Nothing here selects it.
"""

from __future__ import annotations

import re

PROVIDER_ID = "nebius"
BASE_URL = "https://api.tokenfactory.nebius.com/v1"
CHAT_COMPLETIONS_URL = BASE_URL + "/chat/completions"
MODELS_URL = BASE_URL + "/models"
API_KEY_PAGE = "https://tokenfactory.nebius.com/"
ENV_KEY = "NEBIUS_API_KEY"

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN = re.compile(r"<think>.*", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str | None) -> str | None:
    """Remove inline ``<think>`` reasoning that some served models emit.

    Returns the answer text, or ``None`` when nothing but reasoning remains.
    Text without a think block is returned unchanged (apart from trimming).
    """
    if text is None:
        return None
    raw = str(text)
    if "<think>" not in raw.lower() and "</think>" not in raw.lower():
        return raw.strip() or None
    cleaned = _THINK_BLOCK.sub("", raw)
    # A reply that starts with a closing tag (opening tag in the template).
    if "</think>" in cleaned.lower():
        cleaned = re.split(r"</think>", cleaned, flags=re.IGNORECASE)[-1]
    cleaned = _THINK_OPEN.sub("", cleaned)
    return cleaned.strip() or None

"""AI Text Polisher & Cleanup Engine.
Supports built-in zero-latency NLP cleanup, dictionary fuzzy correction,
and multi-API key Google Gemini load balancing.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
import json

from voice_flow.config import config
from voice_flow.dictionary import dictionary_engine
from voice_flow.storage import storage

log = logging.getLogger(__name__)

# Pattern list for disfluencies & filler words
FILLER_PATTERNS = [
    (r"\b(um|uh|er|ah|hmm|like|you know|so basically|kind of|sort of)\b", ""),
    (r"\s+", " "),  # collapse double spaces
]

# Pattern list for backtracks and self-corrections
SELF_CORRECT_PATTERNS = [
    (r"\b(let's do|meet at|go to)\s+[\w:]+\s+(wait no|actually|I mean)\s+([\w:]+)", r"\1 \3"),
    (r"\b[\w:]+\s+(wait no|actually|I mean)\s+([\w:]+)", r"\2"),
]


class TextPolisher:
    """Intelligent AI Text Cleaning & Polish Engine."""

    def __init__(self) -> None:
        pass

    def polish(self, raw_text: str, style_instruction: str = "") -> str:
        """Clean and polish raw speech text."""
        if not raw_text or not raw_text.strip():
            return ""

        # Step 1: Fetch saved API keys from SQLite storage
        try:
            saved_keys = storage.get_all_api_keys()
        except Exception:
            saved_keys = {}

        if saved_keys:
            polished_api = self._polish_with_api_pool(raw_text, saved_keys, style_instruction)
            if polished_api:
                return dictionary_engine.apply_dictionary_post_processing(polished_api)

        # Step 2: Built-in instant zero-latency NLP polisher fallback
        cleaned = raw_text.strip()

        # Remove filler words
        for pattern, repl in FILLER_PATTERNS:
            cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)

        # Resolve self-corrections
        for pattern, repl in SELF_CORRECT_PATTERNS:
            cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)

        # Clean spacing & capitalize first letter
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]

        # Ensure sentence ends with proper punctuation
        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."

        # Apply dictionary post-processing
        final_text = dictionary_engine.apply_dictionary_post_processing(cleaned)
        log.info("Polished (built-in NLP): '%s' -> '%s'", raw_text, final_text)
        return final_text

    def _polish_with_api_pool(
        self, raw_text: str, api_keys: dict[str, str], style_instruction: str
    ) -> str | None:
        """Rotate through pool of user API keys and multi-connections for AI polishing with priority failover."""
        prompt = (
            f"You are Voice Flow AI dictation assistant. Clean up this spoken text by removing filler words ('um', 'uh', 'like', 'you know'), "
            f"fixing grammar, resolving self-corrections, formatting line breaks, and capitalizing properly. Do NOT add commentary or quotes.\n"
            f"Style guidance: {style_instruction}\n\n"
            f"Spoken text: {raw_text}"
        )

        all_conns = storage.get_all_provider_connections()
        providers = ["gemini", "groq", "openai", "anthropic", "deepseek", "alibaba", "zenmux"]

        for provider in providers:
            conns = all_conns.get(provider, [])
            # If no multi-key connections in DB, fall back to single key if present
            if not conns and provider in api_keys and api_keys[provider].strip():
                conns = [{"id": 0, "name": f"{provider.capitalize()} Default", "api_key": api_keys[provider].strip(), "priority": 1, "is_active": 1}]

            active_conns = [c for c in conns if c.get("is_active", 1)]
            if not active_conns:
                continue

            mode = storage.get_provider_load_balance_mode(provider)
            log.info("[AI POLISH - %s] Found %d active connection(s). Mode: %s", provider.capitalize(), len(active_conns), mode)

            # Try each connection in priority order (Failover chain: Key #1 -> Key #2 -> Key #3)
            for conn in active_conns:
                key = conn["api_key"].strip()
                cname = conn.get("name", "Key")
                cid = conn.get("id", 0)

                result = self._try_provider_call(provider, key, prompt)
                if result:
                    log.info("[AI POLISH - %s] Polished successfully using Connection '%s' (#%s)!", provider.capitalize(), cname, cid)
                    if cid > 0:
                        storage.update_connection_status(cid, "Connected (200 OK)")
                    return result
                else:
                    log.warning("[AI POLISH - %s] Connection '%s' (#%s) failed or rate-limited. Failing over to next key...", provider.capitalize(), cname, cid)
                    if cid > 0:
                        storage.update_connection_status(cid, "Error / Rate Limited")

        return None

    def _try_provider_call(self, provider: str, key: str, prompt: str) -> str | None:
        """Execute HTTP request to target AI provider model endpoint."""
        try:
            if provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
                payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if text: return text

            elif provider in ("groq", "openai", "deepseek", "alibaba", "zenmux"):
                endpoints = {
                    "groq": ("https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile"),
                    "openai": ("https://api.openai.com/v1/chat/completions", "gpt-4o-mini"),
                    "deepseek": ("https://api.deepseek.com/v1/chat/completions", "deepseek-chat"),
                    "alibaba": ("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", "qwen-plus"),
                    "zenmux": ("https://zenmux.ai/api/v1/chat/completions", "zenmux/glm-5.2-free"),
                }
                ep_url, ep_model = endpoints[provider]
                payload = json.dumps({
                    "model": ep_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2
                }).encode("utf-8")
                req = urllib.request.Request(ep_url, data=payload, headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}"
                })
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data["choices"][0]["message"]["content"].strip()
                    if text: return text

            elif provider == "anthropic":
                url = "https://api.anthropic.com/v1/messages"
                payload = json.dumps({
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}]
                }).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={
                    "Content-Type": "application/json",
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01"
                })
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data["content"][0]["text"].strip()
                    if text: return text

        except Exception as e:
            log.warning("[%s API CALL FAILED] %s", provider.upper(), e)

        return None


# Singleton instance
polisher = TextPolisher()


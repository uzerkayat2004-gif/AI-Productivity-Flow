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
        log.info("Polished (built-in NLP): '%s' -> '%s'", cleaned, final_text)
        return final_text

    def _polish_with_api_pool(
        self, raw_text: str, api_keys: dict[str, str], style_instruction: str
    ) -> str | None:
        """Rotate through pool of user API keys and multi-connections for AI polishing with priority failover."""
        prompt = (
            f"You are an ultra-fast text polishing assistant. Clean up this spoken text by removing filler words ('um', 'uh', 'like', 'you know'), "
            f"fixing punctuation/grammar, and capitalizing properly.\n"
            f"CRITICAL INSTRUCTION: Output ONLY the final cleaned text. Do NOT add options, bullet points, intro text, quote marks, or explanation.\n"
            f"Style guidance: {style_instruction}\n\n"
            f"Spoken text: {raw_text}"
        )

        all_conns = storage.get_all_provider_connections()
        providers = ["gemini", "groq", "openai", "together", "deepseek", "cloudflare", "huggingface", "replicate"]

        now = time.time()
        for provider in providers:
            conns = all_conns.get(provider, [])
            if not conns and provider in api_keys and api_keys[provider].strip():
                conns = [{"id": 0, "name": f"{provider.capitalize()} Default", "api_key": api_keys[provider].strip(), "priority": 1, "is_active": 1}]

            active_conns = [c for c in conns if c.get("is_active", 1)]
            if not active_conns:
                continue

            for conn in active_conns:
                key = conn["api_key"].strip()
                cname = conn.get("name", "Key")
                cid = conn.get("id", 0)

                # Skip rate-limited keys instantly (0ms) during cooldown
                if key in self._rate_limited_keys:
                    if now < self._rate_limited_keys[key]:
                        log.info("[AI POLISH - %s] Key '%s' in 60s cooldown, bypassing instantly...", provider.capitalize(), cname)
                        continue
                    else:
                        del self._rate_limited_keys[key]

                result = self._try_provider_call(provider, key, prompt)
                if result:
                    log.info("[AI POLISH - %s] Polished successfully using Connection '%s' (#%s)!", provider.capitalize(), cname, cid)
                    if cid > 0:
                        storage.update_connection_status(cid, "Connected (200 OK)")
                    return result
                else:
                    log.warning("[AI POLISH - %s] Connection '%s' (#%s) failed or rate-limited. Failing over to next key...", provider.capitalize(), cname, cid)
                    self._rate_limited_keys[key] = now + 60.0
                    if cid > 0:
                        storage.update_connection_status(cid, "Error / Rate Limited")

        return None

    def _try_provider_call(self, provider: str, key: str, prompt: str) -> str | None:
        """Execute HTTP request to target AI provider model endpoint with model fallbacks."""
        try:
            if provider == "gemini":
                models = ["gemini-2.5-flash", "gemini-2.0-flash"]
                for m in models:
                    try:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
                        payload = json.dumps({
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 256}
                        }).encode("utf-8")
                        req = urllib.request.Request(url, data=payload, headers={
                            "Content-Type": "application/json",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        })
                        with urllib.request.urlopen(req, timeout=3.5) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                            try:
                                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                                if text:
                                    return text
                            except (KeyError, IndexError):
                                pass
                    except urllib.error.HTTPError as e:
                        log.warning("[GEMINI %s FAILED] HTTP %d: %s", m, e.code, e.reason)
                        if e.code in (429, 403):
                            # Rate limited or quota exceeded — stop trying this key and failover immediately
                            break
                    except Exception as e:
                        log.warning("[GEMINI %s FAILED] %s", m, e)

            elif provider in ("groq", "openai", "deepseek", "together"):
                endpoints = {
                    "groq": ("https://api.groq.com/openai/v1/chat/completions", ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]),
                    "openai": ("https://api.openai.com/v1/chat/completions", ["gpt-4o-mini", "gpt-4o"]),
                    "together": ("https://api.together.xyz/v1/chat/completions", ["meta-llama/Llama-3.3-70B-Instruct-Turbo"]),
                    "deepseek": ("https://api.deepseek.com/v1/chat/completions", ["deepseek-chat"]),
                }
                ep_url, ep_models = endpoints[provider]
                for m in ep_models:
                    try:
                        payload = json.dumps({
                            "model": m,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.1,
                            "max_tokens": 256
                        }).encode("utf-8")
                        req = urllib.request.Request(ep_url, data=payload, headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {key}",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        })
                        with urllib.request.urlopen(req, timeout=8.0) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                            text = data["choices"][0]["message"]["content"].strip()
                            if text:
                                return text
                    except Exception as e:
                        log.warning("[%s %s FAILED] %s", provider.upper(), m, e)

        except Exception as e:
            log.warning("[%s API CALL FAILED] %s", provider.upper(), e)

        return None


# Singleton instance
polisher = TextPolisher()


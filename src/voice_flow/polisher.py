"""AI Text Polisher & Cleanup Engine.
Supports built-in zero-latency NLP cleanup, dictionary fuzzy correction,
and multi-API key Google Gemini load balancing.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request

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
        self._rate_limited_keys: dict[str, float] = {}

    def polish(self, raw_text: str, style_instruction: str = "") -> str:
        """Clean and polish raw speech text."""
        if not raw_text or not raw_text.strip():
            return ""

        raw_word_count = len(raw_text.split())

        # Step 1: Fetch saved API keys from SQLite storage
        try:
            saved_keys = storage.get_all_api_keys()
        except Exception:
            saved_keys = {}

        if saved_keys:
            polished_api = self._polish_with_api_pool(raw_text, saved_keys, style_instruction)
            if polished_api:
                polished_word_count = len(polished_api.split())
                # Safety check: if polished text lost >50% of words, the AI truncated it — use raw STT instead
                if polished_word_count < raw_word_count * 0.5 and raw_word_count > 5:
                    log.warning("[POLISH SAFETY] AI polisher lost too many words (%d -> %d). Using raw STT text instead.",
                                raw_word_count, polished_word_count)
                    return dictionary_engine.apply_dictionary_post_processing(raw_text)
                log.info("[POLISH] API polished: %d words -> %d words", raw_word_count, polished_word_count)
                return dictionary_engine.apply_dictionary_post_processing(polished_api)

        # Step 2: Built-in instant zero-latency NLP polisher fallback
        cleaned = raw_text.strip()

        # Remove filler words
        for pattern, repl in FILLER_PATTERNS:
            cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)

        # Handle backtracks / self corrections
        for pattern, repl in SELF_CORRECT_PATTERNS:
            cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)

        # Clean spacing & apply style guidance rules
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        style_lower = style_instruction.lower()
        if "lowercase" in style_lower or "very_casual" in style_lower:
            cleaned = cleaned.lower()
            if cleaned.endswith("."):
                cleaned = cleaned[:-1]
        else:
            if cleaned:
                cleaned = cleaned[0].upper() + cleaned[1:]
            if cleaned and cleaned[-1] not in ".!?":
                cleaned += "."

        # Apply dictionary post-processing
        final_text = dictionary_engine.apply_dictionary_post_processing(cleaned)
        log.info("Polished (built-in NLP): '%s' -> '%s' (style: '%s')", raw_text, final_text, style_instruction)
        return final_text

    def _polish_with_api_pool(
        self, raw_text: str, api_keys: dict[str, str], style_instruction: str
    ) -> str | None:
        """Rotate through pool of user API keys and multi-connections for AI polishing with priority failover."""
        prompt = (
            f"You are an ultra-fast text polishing assistant. Clean up this spoken text by removing filler words ('um', 'uh', 'like', 'you know'), "
            f"fixing punctuation/grammar, and capitalizing properly.\n"
            f"CRITICAL INSTRUCTION: Output ONLY the final cleaned text. Do NOT add options, bullet points, intro text, quote marks, or explanation.\n"
            f"CRITICAL: You MUST preserve ALL spoken content completely. Do NOT shorten, summarize, or remove any sentences. Every sentence from the input must appear in your output.\n"
            f"Style guidance: {style_instruction}\n\n"
            f"Spoken text: {raw_text}"
        )

        # Check Exec Voice Flow Policy active model preference
        exec_policy_model = storage.get_setting("exec_policy_model", "gemini/gemini-2.5-flash")
        preferred_provider = None
        preferred_model = None
        if "/" in exec_policy_model:
            preferred_provider, preferred_model = exec_policy_model.split("/", 1)

        all_conns = storage.get_all_provider_connections()
        providers = ["gemini", "groq", "openai", "together", "deepseek", "cloudflare", "huggingface", "replicate"]

        if preferred_provider and preferred_provider in providers:
            providers.remove(preferred_provider)
            providers.insert(0, preferred_provider)
            log.info("[EXEC VOICE FLOW POLICY] Primary polishing routed via: %s / %s", preferred_provider.upper(), preferred_model)

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
        """Execute HTTP request to target AI provider model endpoint with ultra-fast models and strict 1.8s timeout."""
        try:
            if provider == "gemini":
                models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash"]
                for m in models:
                    try:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
                        payload = json.dumps({
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 1024}
                        }).encode("utf-8")
                        req = urllib.request.Request(url, data=payload, headers={
                            "Content-Type": "application/json",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        })
                        with urllib.request.urlopen(req, timeout=1.8) as resp:
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
                        log.warning("[GEMINI %s FAILED/TIMEOUT] %s", m, e)

            elif provider in ("groq", "openai", "deepseek", "together"):
                endpoints = {
                    "groq": ("https://api.groq.com/openai/v1/chat/completions", ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]),
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
                            "temperature": 0.0,
                            "max_tokens": 1024
                        }).encode("utf-8")
                        req = urllib.request.Request(ep_url, data=payload, headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {key}",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        })
                        with urllib.request.urlopen(req, timeout=1.8) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                            text = data["choices"][0]["message"]["content"].strip()
                            if text:
                                return text
                    except Exception as e:
                        log.warning("[%s %s FAILED/TIMEOUT] %s", provider.upper(), m, e)

        except Exception as e:
            log.warning("[%s API CALL FAILED] %s", provider.upper(), e)

        return None


# Singleton instance
polisher = TextPolisher()


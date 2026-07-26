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
        """Rotate through pool of user API keys (Gemini, Groq, OpenAI) for AI polishing."""
        prompt = (
            f"You are Voice Flow AI dictation assistant. Clean up this spoken text by removing filler words ('um', 'uh', 'like', 'you know'), "
            f"fixing grammar, resolving self-corrections, formatting line breaks, and capitalizing properly. Do NOT add commentary or quotes.\n"
            f"Style guidance: {style_instruction}\n\n"
            f"Spoken text: {raw_text}"
        )

        # 1. Try Gemini Key
        if "gemini" in api_keys and api_keys["gemini"].strip():
            key = api_keys["gemini"].strip()
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
                payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=3.5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if text:
                        log.info("[AI POLISH - Gemini] Polished speech text successfully!")
                        return text
            except Exception as e:
                log.warning("[AI POLISH - Gemini] Failed (%s), trying next provider...", e)

        # 2. Try Groq Key
        if "groq" in api_keys and api_keys["groq"].strip():
            key = api_keys["groq"].strip()
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                payload = json.dumps({
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2
                }).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}"
                })
                with urllib.request.urlopen(req, timeout=3.5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data["choices"][0]["message"]["content"].strip()
                    if text:
                        log.info("[AI POLISH - Groq] Polished speech text successfully!")
                        return text
            except Exception as e:
                log.warning("[AI POLISH - Groq] Failed (%s), trying next provider...", e)

        # 3. Try OpenAI Key
        if "openai" in api_keys and api_keys["openai"].strip():
            key = api_keys["openai"].strip()
            try:
                url = "https://api.openai.com/v1/chat/completions"
                payload = json.dumps({
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2
                }).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}"
                })
                with urllib.request.urlopen(req, timeout=3.5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data["choices"][0]["message"]["content"].strip()
                    if text:
                        log.info("[AI POLISH - OpenAI] Polished speech text successfully!")
                        return text
            except Exception as e:
                log.warning("[AI POLISH - OpenAI] Failed (%s)...", e)

        return None


# Singleton instance
polisher = TextPolisher()

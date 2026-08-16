"""Audio Summary Service.

Generates spoken explanation summaries via LLM providers or fails safely.
REUSES video_flow_provider_service active connections & API keys.
Does NOT perform silent extractive sentence fallback when an LLM is missing or fails.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from voice_flow.audio_summary_prompts import build_audio_summary_prompt, sanitize_narration_text
from voice_flow.storage import storage
from voice_flow.video_flow_providers import video_flow_provider_service

log = logging.getLogger(__name__)


class AudioSummaryError(RuntimeError):
    """Raised when audio summarization fails or permissions are missing."""


class AudioSummaryService:
    """Service facade for generating LLM-powered Audio Flow spoken summaries."""

    def summarize(
        self,
        text: str,
        depth: str = "standard",
        model_ref: str | None = None,
        allow_external_ai: bool | None = None,
    ) -> str:
        """Synthesize a spoken explanation from source text using the selected LLM.

        Raises PermissionError if an external model is selected without consent.
        Raises AudioSummaryError if no model is selected or the provider request fails.
        No silent extractive fallback is performed.
        """
        if not text or not text.strip():
            raise ValueError("Source text for summary cannot be empty.")

        ref = (model_ref or storage.get_setting("exec_audio_summary_model", "") or "").strip()
        if not ref:
            raise AudioSummaryError("No Audio Flow Summary Model selected. Please select a model in Audio Flow settings.")

        # Resolve consent: if allow_external_ai parameter is not passed, read setting
        if allow_external_ai is None:
            allow_external_ai = bool(storage.get_setting("exec_audio_summary_allow_external_ai", False))

        refs = self._resolve_refs(ref)
        if not refs:
            raise AudioSummaryError(f"Selected summary model '{ref}' is invalid or no longer exists.")

        # Local models do not require external network consent
        is_local = all(
            r.startswith("local/") or r.startswith("ollama/") or r.startswith("lmstudio/") or r.startswith("llamacpp/")
            for r in refs
        )
        if not is_local and not allow_external_ai:
            raise PermissionError(
                f"External AI permission is required for the selected summary model '{ref}'. Please enable permission in Audio Flow settings."
            )

        failures: list[str] = []
        for target_ref in refs:
            try:
                raw_response = self._request_llm_summary(text, depth, target_ref)
                clean_narration = sanitize_narration_text(raw_response)
                if not clean_narration:
                    raise AudioSummaryError(f"Model '{target_ref}' returned an empty or unparseable summary response.")
                return clean_narration
            except PermissionError:
                raise
            except Exception as exc:
                log.warning("Audio Summary request to '%s' failed: %s", target_ref, exc)
                failures.append(f"{target_ref}: {exc}")

        raise AudioSummaryError(f"Summary generation failed across selected models: {' | '.join(failures)}")

    def _resolve_refs(self, model_ref: str) -> list[str]:
        if not model_ref.startswith("combo:"):
            return [model_ref]
        name = model_ref.split(":", 1)[1]
        combo = next((item for item in video_flow_provider_service.store.list_combos() if item["name"] == name), None)
        if not combo:
            raise ValueError(f"Model combo '{name}' no longer exists.")
        refs = list(combo.get("models", []))
        if combo.get("strategy") == "round_robin" and refs:
            key = f"audio_summary_combo_cursor_{combo['id']}"
            cursor = int(storage.get_setting(key, 0) or 0) % len(refs)
            storage.save_setting(key, cursor + 1)
            refs = refs[cursor:] + refs[:cursor]
        return refs

    def _request_llm_summary(self, text: str, depth: str, model_ref: str) -> str:
        parts = model_ref.split("/", 1)
        provider = parts[0]
        model_id = parts[1] if len(parts) > 1 else parts[0]

        prompt = build_audio_summary_prompt(text, depth)

        if provider == "codex":
            return self._call_cli(["codex", "exec"], prompt)
        if provider == "claude_code":
            return self._call_cli(["claude", "-p"], prompt)

        connections = [
            conn for conn in video_flow_provider_service.active_connections(provider)
            if video_flow_provider_service.connection_is_healthy(conn)
        ]
        if not connections:
            raise AudioSummaryError(f"No healthy connection available for provider '{provider}'.")

        load_balance_mode = video_flow_provider_service.get_setting(f"load_balance:{provider}", "priority")
        if load_balance_mode == "round_robin" and len(connections) > 1:
            cursor_key = f"audio_summary_provider_cursor_{provider}"
            cursor = int(video_flow_provider_service.get_setting(cursor_key, 0) or 0) % len(connections)
            video_flow_provider_service.set_setting(cursor_key, cursor + 1)
            connections = connections[cursor:] + connections[:cursor]

        failures: list[str] = []
        for connection in connections:
            try:
                secret = video_flow_provider_service.resolve_connection_secret(connection)
                if not secret:
                    continue
                started = time.monotonic()
                if provider == "gemini":
                    result = self._call_gemini(model_id, secret, prompt)
                elif provider in ("openai", "groq", "together", "openrouter", "nvidia_nim", "opencode_zen", "cloudflare"):
                    result = self._call_openai_compatible(provider, model_id, secret, prompt, connection)
                elif provider == "anthropic":
                    result = self._call_anthropic(model_id, secret, prompt)
                else:
                    raise AudioSummaryError(f"Provider '{provider}' is not supported for Audio Summary.")
                latency_ms = int((time.monotonic() - started) * 1000)
                video_flow_provider_service.update_connection(int(connection["id"]), last_latency_ms=latency_ms)
                return result
            except Exception as exc:
                failures.append(f"{connection.get('name', 'connection')}: {exc}")

        raise AudioSummaryError(f"All connections for '{provider}' failed: {' | '.join(failures)}")

    def _call_gemini(self, model_id: str, api_key: str, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
        # maxOutputTokens is a technical safety ceiling only (16384 ensures reasoning models have ample room for thinking tokens without premature truncation).
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 16384},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        candidates = body.get("candidates", [])
        if candidates and "content" in candidates[0]:
            parts = candidates[0]["content"].get("parts", [])
            if parts and "text" in parts[0]:
                return str(parts[0]["text"])
        raise AudioSummaryError("Gemini API returned no text output.")

    def _call_openai_compatible(self, provider: str, model_id: str, secret: str, prompt: str, connection: dict[str, Any]) -> str:
        base_urls = {
            "openai": "https://api.openai.com/v1",
            "groq": "https://api.groq.com/openai/v1",
            "together": "https://api.together.xyz/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "nvidia_nim": "https://integrate.api.nvidia.com/v1",
            "opencode_zen": "https://opencode.zen/v1",
        }
        base_url = connection.get("metadata", {}).get("base_url") or base_urls.get(provider, "https://api.openai.com/v1")
        url = f"{base_url.rstrip('/')}/chat/completions"
        # max_tokens is a technical safety ceiling only (8192 prevents premature output truncation).
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 8192,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {secret}",
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        choices = body.get("choices", [])
        if choices and "message" in choices[0]:
            return str(choices[0]["message"].get("content", ""))
        raise AudioSummaryError(f"{provider} API returned no message content.")

    def _call_anthropic(self, model_id: str, secret: str, prompt: str) -> str:
        url = "https://api.anthropic.com/v1/messages"
        # max_tokens is a technical safety ceiling only (8192 prevents premature output truncation).
        payload = {
            "model": model_id,
            "max_tokens": 8192,
            "temperature": 0.3,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": secret,
            "anthropic-version": "2023-06-01",
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body.get("content", [])
        if content and isinstance(content, list) and "text" in content[0]:
            return str(content[0]["text"])
        raise AudioSummaryError("Anthropic API returned no content.")

    def _call_cli(self, cmd_prefix: list[str], prompt: str) -> str:
        import subprocess
        res = subprocess.run(
            cmd_prefix + [prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if res.returncode != 0:
            raise AudioSummaryError(f"CLI command failed: {res.stderr or res.stdout}")
        return res.stdout.strip()


audio_summary_service = AudioSummaryService()

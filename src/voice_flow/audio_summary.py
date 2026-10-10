"""Audio Summary Service.

Generates spoken explanation summaries via LLM providers or fails safely.
REUSES video_flow_provider_service active connections & API keys.
Directly supports local/deterministic models and provides zero-failure fallback via LocalSpokenSummarizer.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from voice_flow.audio_explainer_prompts import (
    build_audio_explainer_prompt,
    sanitize_explanation_text,
)
from voice_flow.audio_summary_prompts import build_audio_summary_prompt, sanitize_narration_text
from voice_flow.local_summarizer import LocalSpokenSummarizer, local_spoken_summarizer
from voice_flow.storage import storage
from voice_flow.video_flow_providers import video_flow_provider_service

log = logging.getLogger(__name__)


def _sanitize_error_message(error: Any) -> str:
    """Sanitize error messages to guarantee no API keys, tokens, or private secrets leak into logs or UI."""
    msg = str(error or "")
    msg = re.sub(r'(?i)(?:key|api_key|secret|token)=([A-Za-z0-9_\-]+)', r'key=[REDACTED]', msg)
    msg = re.sub(r'(?i)(?:bearer\s+)([A-Za-z0-9_\-\.]{8,})', r'Bearer [REDACTED]', msg)
    return msg


class AudioSummaryError(RuntimeError):
    """Raised when audio summarization fails or permissions are missing."""


class AudioSummaryService:
    """Service facade for generating LLM-powered Audio Flow spoken summaries."""

    def _compute_cache_key(self, text: str, depth: str, model_ref: str) -> tuple[str, str]:
        text_hash = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
        cache_key = f"{text_hash}::{depth}::{model_ref.strip().lower()}"
        return cache_key, text_hash

    def _get_cached_summary(self, text: str, depth: str, model_ref: str) -> str | None:
        try:
            cache_key, _ = self._compute_cache_key(text, depth, model_ref)
            row = storage.get_audio_summary_cache(cache_key)
            if row and row.get("summary_text"):
                log.info("Audio summary hit cache for key %s", cache_key[:16])
                return str(row["summary_text"])
        except Exception as exc:
            log.debug("Cache lookup error: %s", exc)
        return None

    def _set_cached_summary(self, text: str, depth: str, model_ref: str, summary_text: str) -> None:
        try:
            cache_key, text_hash = self._compute_cache_key(text, depth, model_ref)
            cached_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            storage.set_audio_summary_cache(cache_key, text_hash, depth, model_ref, summary_text, cached_at)
        except Exception as exc:
            log.debug("Cache write error: %s", exc)

    def summarize(
        self,
        text: str,
        depth: str = "standard",
        model_ref: str | None = None,
        allow_external_ai: bool | None = None,
        allow_fallback: bool = True,
        fallback_to_local: bool | None = None,
    ) -> str:
        """Synthesize a spoken explanation from source text using the selected LLM or local fallback.

        Directly supports 'local/deterministic' and 'local/*' models via LocalSpokenSummarizer.
        Implements automatic zero-failure fallback:
          - If an external LLM fails, times out, has an invalid key, or allow_external_ai is False,
            seamlessly falls back to LocalSpokenSummarizer when allow_fallback is True.
          - If allow_fallback=False is explicitly passed, raises PermissionError or AudioSummaryError
            for strict backward compatibility.
        """
        if fallback_to_local is not None:
            allow_fallback = fallback_to_local
        if not text or not text.strip():
            raise ValueError("Source text for summary cannot be empty.")

        ref = (model_ref or storage.get_setting("exec_audio_summary_model", "") or "").strip()
        if not ref:
            if allow_fallback:
                ref = "local/deterministic"
            else:
                raise AudioSummaryError("No Audio Flow Summary Model selected. Please select a model in Audio Flow settings.")

        # Resolve consent: if allow_external_ai parameter is not passed, read setting
        if allow_external_ai is None:
            allow_external_ai = bool(storage.get_setting("exec_audio_summary_allow_external_ai", False))

        ref_normalized = ref.lower().strip()
        is_local_ref = (
            ref_normalized in ("local/deterministic", "local", "offline", "deterministic")
            or ref_normalized.startswith("local/")
        )

        if not is_local_ref and not allow_external_ai:
            if not allow_fallback:
                raise PermissionError(
                    f"External AI permission is required for the selected summary model '{ref}'. Please enable permission in Audio Flow settings."
                )
            log.info(
                "External AI permission is disabled; falling back to local spoken summarizer for model '%s'.",
                ref,
            )
            return local_spoken_summarizer.summarize(text, depth)

        # Check sub-millisecond cache for previously computed summaries
        cached_result = self._get_cached_summary(text, depth, ref)
        if cached_result:
            return cached_result

        if is_local_ref:
            summary = local_spoken_summarizer.summarize(text, depth)
            # Deliberately NOT cached: a transient outage must not poison
            # the cloud model's cache entry with local-extractive output.
            return summary

        try:
            refs = self._resolve_refs(ref)
            if not refs:
                raise AudioSummaryError(f"Selected summary model '{ref}' is invalid or no longer exists.")
        except Exception as exc:
            if allow_fallback:
                log.warning("Audio summary model resolution failed for '%s': %s. Falling back to local spoken summarizer.", ref, exc)
                # Deliberately NOT cached: a transient failure must not poison
                # the cloud model's cache entry with local-extractive output.
                return local_spoken_summarizer.summarize(text, depth)
            raise

        # Local models do not require external network consent
        is_local = all(
            r.lower().startswith("local/") or r.lower().startswith("ollama/") or r.lower().startswith("lmstudio/") or r.lower().startswith("llamacpp/")
            for r in refs
        )
        if not is_local and not allow_external_ai:
            if allow_fallback:
                log.info(
                    "External AI permission is disabled; falling back to local spoken summarizer for model '%s'.",
                    ref,
                )
                # Deliberately NOT cached under cloud model ref
                return local_spoken_summarizer.summarize(text, depth)
            raise PermissionError(
                f"External AI permission is required for the selected summary model '{ref}'. Please enable permission in Audio Flow settings."
            )

        failures: list[str] = []
        for target_ref in refs:
            try:
                t_norm = target_ref.lower().strip()
                if t_norm in ("local/deterministic", "local", "offline", "deterministic") or t_norm.startswith("local/"):
                    summary = local_spoken_summarizer.summarize(text, depth)
                    if ref.lower().startswith("local/"):
                        self._set_cached_summary(text, depth, ref, summary)
                    return summary

                raw_response = self._request_llm_summary(text, depth, target_ref)
                clean_narration = sanitize_narration_text(raw_response)
                if not clean_narration:
                    raise AudioSummaryError(f"Model '{target_ref}' returned an empty or unparseable summary response.")
                self._set_cached_summary(text, depth, ref, clean_narration)
                return clean_narration
            except PermissionError:
                if allow_fallback:
                    log.warning("PermissionError during summary request to '%s'. Falling back to local spoken summarizer.", target_ref)
                    # Deliberately NOT cached under cloud model ref
                    return local_spoken_summarizer.summarize(text, depth)
                raise
            except Exception as exc:
                clean_err = _sanitize_error_message(exc)
                log.warning("Audio Summary request to '%s' failed: %s", target_ref, clean_err)
                failures.append(f"{target_ref}: {clean_err}")

        failure_msg = f"Summary generation failed across selected models: {' | '.join(failures)}"
        if allow_fallback:
            log.warning("%s. Falling back to local spoken summarizer.", failure_msg)
            summary = local_spoken_summarizer.summarize(text, depth)
            # Deliberately NOT cached: a transient outage must not poison
            # the cloud model's cache entry with local-extractive output.
            return summary
        raise AudioSummaryError(failure_msg)

    def explain(
        self,
        text: str,
        context: str | None = None,
        model_ref: str | None = None,
        allow_external_ai: bool | None = None,
        allow_fallback: bool = True,
    ) -> str:
        """Synthesize a spoken conversational explanation from source text using the selected LLM or local fallback.

        Explains intent, core takeaways, and details naturally to the listener rather than
        reading raw text verbatim like a screen reader.
        """
        if not text or not text.strip():
            raise ValueError("Source text for explanation cannot be empty.")

        ref = (model_ref or storage.get_setting("exec_audio_summary_model", "") or "").strip()
        if not ref:
            if allow_fallback:
                ref = "local/deterministic"
            else:
                raise AudioSummaryError("No Audio Flow Model selected. Please select a model in Audio Flow settings.")

        if allow_external_ai is None:
            allow_external_ai = bool(storage.get_setting("exec_audio_summary_allow_external_ai", False))

        ref_normalized = ref.lower().strip()
        is_local_ref = (
            ref_normalized in ("local/deterministic", "local", "offline", "deterministic")
            or ref_normalized.startswith("local/")
        )

        if not is_local_ref and not allow_external_ai:
            if not allow_fallback:
                raise PermissionError(
                    f"External AI permission is required for the selected explanation model '{ref}'. Please enable permission in Audio Flow settings."
                )
            log.info(
                "External AI permission is disabled; falling back to local conversational explainer for model '%s'.",
                ref,
            )
            return local_spoken_summarizer.explain_conversationally(text)

        # Check sub-millisecond cache for previously computed explanations
        cached_result = self._get_cached_summary(text, "explain", ref)
        if cached_result:
            return cached_result

        if is_local_ref:
            explanation = local_spoken_summarizer.explain_conversationally(text)
            return explanation

        try:
            refs = self._resolve_refs(ref)
            if not refs:
                raise AudioSummaryError(f"Selected explanation model '{ref}' is invalid or no longer exists.")
        except Exception as exc:
            if allow_fallback:
                log.warning("Audio explainer model resolution failed for '%s': %s. Falling back to local conversational explainer.", ref, exc)
                return local_spoken_summarizer.explain_conversationally(text)
            raise

        is_local = all(
            r.lower().startswith("local/") or r.lower().startswith("ollama/") or r.lower().startswith("lmstudio/") or r.lower().startswith("llamacpp/")
            for r in refs
        )
        if not is_local and not allow_external_ai:
            if allow_fallback:
                log.info(
                    "External AI permission is disabled; falling back to local conversational explainer for model '%s'.",
                    ref,
                )
                return local_spoken_summarizer.explain_conversationally(text)
            raise PermissionError(
                f"External AI permission is required for the selected explanation model '{ref}'. Please enable permission in Audio Flow settings."
            )

        failures: list[str] = []
        for target_ref in refs:
            try:
                t_norm = target_ref.lower().strip()
                if t_norm in ("local/deterministic", "local", "offline", "deterministic") or t_norm.startswith("local/"):
                    explanation = local_spoken_summarizer.explain_conversationally(text)
                    if ref.lower().startswith("local/"):
                        self._set_cached_summary(text, "explain", ref, explanation)
                    return explanation

                raw_response = self._request_llm_explanation(text, context, target_ref)
                clean_narration = sanitize_explanation_text(raw_response)
                if not clean_narration:
                    raise AudioSummaryError(f"Model '{target_ref}' returned an empty or unparseable explanation response.")
                self._set_cached_summary(text, "explain", ref, clean_narration)
                return clean_narration
            except PermissionError:
                if allow_fallback:
                    log.warning("PermissionError during explanation request to '%s'. Falling back to local conversational explainer.", target_ref)
                    return local_spoken_summarizer.explain_conversationally(text)
                raise
            except Exception as exc:
                clean_err = _sanitize_error_message(exc)
                log.warning("Audio Explainer request to '%s' failed: %s", target_ref, clean_err)
                failures.append(f"{target_ref}: {clean_err}")

        failure_msg = f"Explanation generation failed across selected models: {' | '.join(failures)}"
        if allow_fallback:
            log.warning("%s. Falling back to local conversational explainer.", failure_msg)
            return local_spoken_summarizer.explain_conversationally(text)
        raise AudioSummaryError(failure_msg)

    def _resolve_refs(self, model_ref: str) -> list[str]:
        if not model_ref.startswith("combo:"):
            return [model_ref]
        name = model_ref.split(":", 1)[1]
        combo = next((item for item in video_flow_provider_service.list_combos() if item["name"] == name), None)
        if not combo:
            raise AudioSummaryError(f"Model combo '{name}' no longer exists.")
        refs = list(combo.get("models", []))
        if combo.get("strategy") == "round_robin" and refs:
            key = f"audio_summary_combo_cursor_{combo['id']}"
            cursor = int(storage.get_setting(key, 0) or 0) % len(refs)
            storage.save_setting(key, cursor + 1)
            refs = refs[cursor:] + refs[:cursor]
        return refs

    def _dispatch_llm_prompt(self, prompt: str, model_ref: str, service_label: str = "Audio Flow") -> str:
        parts = model_ref.split("/", 1)
        provider = parts[0].lower()
        model_id = parts[1] if len(parts) > 1 else parts[0]

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
            cursor_key = f"{service_label.lower().replace(' ', '_')}_provider_cursor_{provider}"
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
                    raise AudioSummaryError(f"Provider '{provider}' is not supported for {service_label}.")
                latency_ms = int((time.monotonic() - started) * 1000)
                video_flow_provider_service.update_connection(int(connection["id"]), last_latency_ms=latency_ms)
                return result
            except Exception as exc:
                clean_exc = _sanitize_error_message(exc)
                failures.append(f"{connection.get('name', 'connection')}: {clean_exc}")

        raise AudioSummaryError(f"All connections for '{provider}' failed: {' | '.join(failures)}")

    def _request_llm_summary(self, text: str, depth: str, model_ref: str) -> str:
        parts = model_ref.split("/", 1)
        provider = parts[0].lower()
        if provider in ("local", "offline", "deterministic"):
            return local_spoken_summarizer.summarize(text, depth)

        prompt = build_audio_summary_prompt(text, depth)
        return self._dispatch_llm_prompt(prompt, model_ref, service_label="Audio Summary")

    def _request_llm_explanation(self, text: str, context: str | None, model_ref: str) -> str:
        parts = model_ref.split("/", 1)
        provider = parts[0].lower()
        if provider in ("local", "offline", "deterministic"):
            return local_spoken_summarizer.explain_conversationally(text)

        prompt = build_audio_explainer_prompt(text, context)
        return self._dispatch_llm_prompt(prompt, model_ref, service_label="Audio Explainer")

    def _call_gemini(self, model_id: str, api_key: str, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 16384},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
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
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        choices = body.get("choices", [])
        if choices and "message" in choices[0]:
            return str(choices[0]["message"].get("content", ""))
        raise AudioSummaryError(f"{provider} API returned no message content.")

    def _call_anthropic(self, model_id: str, secret: str, prompt: str) -> str:
        url = "https://api.anthropic.com/v1/messages"
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
        with urllib.request.urlopen(req, timeout=30) as resp:
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
            timeout=30,
        )
        if res.returncode != 0:
            raise AudioSummaryError(f"CLI command failed: {res.stderr or res.stdout}")
        return res.stdout.strip()


audio_summary_service = AudioSummaryService()

__all__ = [
    "AudioSummaryError",
    "AudioSummaryService",
    "audio_summary_service",
    "LocalSpokenSummarizer",
    "local_spoken_summarizer",
]

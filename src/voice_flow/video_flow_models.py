"""Consent-gated external model routing for Video Flow scene planning."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from voice_flow.storage import storage
from voice_flow.video_flow_providers import video_flow_provider_service


class VideoModelGateway:
    """Use a selected model/combo only after explicit per-job source consent."""

    _openai_endpoints = {
        "openai": "https://api.openai.com/v1/chat/completions",
        "groq": "https://api.groq.com/openai/v1/chat/completions",
        "together": "https://api.together.xyz/v1/chat/completions",
    }
    _scene_types = {
        "hook", "statement", "quote", "metric", "comparison", "process",
        "timeline", "grid", "chart", "code", "list", "image", "diagram",
        "chapter", "closing",
    }

    def __init__(self, store: Any, planner: Any) -> None:
        self.store = store
        self.planner = planner

    def build(
        self,
        source: str,
        mode: str,
        title: str,
        model_ref: str,
        *,
        allow_external_ai: bool,
    ) -> dict[str, Any]:
        deterministic = self.planner.build(source, mode, title)
        refs = self.resolve_refs(model_ref)
        if not refs or refs == ["local/deterministic"]:
            deterministic["planning_model"] = "local/deterministic"
            return deterministic

        # Local providers like ollama or local execution do not require external consent
        is_local = all(ref.startswith("local/") or ref.startswith("ollama/") for ref in refs)
        if is_local:
            deterministic["planning_model"] = "local/deterministic"
            deterministic["requested_model"] = model_ref
            return deterministic

        if not allow_external_ai:
            raise PermissionError(
                "External model planning needs per-video consent because the source text is sent to the selected provider."
            )

        failures: list[str] = []
        for ref in refs:
            try:
                proposed = self._request_plan(source, mode, title, ref)
                result = self._merge(deterministic, proposed, mode)
                result["planning_model"] = ref
                result["requested_model"] = model_ref
                return result
            except Exception as exc:
                failures.append(f"{ref}: {exc}")

        deterministic["planning_model"] = "local/deterministic"
        deterministic["requested_model"] = model_ref
        deterministic["model_fallback_reason"] = " | ".join(failures)[:1000]
        return deterministic

    def resolve_refs(self, model_ref: str) -> list[str]:
        if not model_ref.startswith("combo:"):
            return [model_ref]
        name = model_ref.split(":", 1)[1]
        combo = next((item for item in self.store.list_combos() if item["name"] == name), None)
        if not combo:
            raise ValueError(f"Model combo '{name}' no longer exists.")
        refs = list(combo["models"])
        if combo["strategy"] == "round_robin" and refs:
            key = f"video_flow_combo_cursor_{combo['id']}"
            cursor = int(storage.get_setting(key, 0) or 0) % len(refs)
            storage.save_setting(key, cursor + 1)
            refs = refs[cursor:] + refs[:cursor]
        return refs

    def provider_names_for(self, model_ref: str) -> list[str]:
        provider_names = {
            "gemini": "Google Gemini",
            "openai": "OpenAI",
            "groq": "Groq",
            "together": "Together AI",
            "huggingface": "Hugging Face",
            "cloudflare": "Cloudflare AI",
            "replicate": "Replicate",
        }
        providers = []
        for ref in self.resolve_refs(model_ref):
            provider = ref.split("/", 1)[0]
            if provider != "local" and provider not in providers:
                providers.append(provider)
        return [provider_names.get(provider, provider.title()) for provider in providers]

    def _request_plan(self, source: str, mode: str, title: str, model_ref: str) -> dict[str, Any]:
        if "/" not in model_ref:
            raise ValueError("Invalid model reference.")
        provider, model_id = model_ref.split("/", 1)
        if provider == "claude":
            return self._call_claude_code(model_id, self._prompt(source, mode, title))
        if provider == "codex":
            return self._call_codex(model_id, self._prompt(source, mode, title))

        connections = [
            connection for connection in video_flow_provider_service.active_connections(provider)
            if video_flow_provider_service.connection_is_healthy(connection)
        ]
        if not connections:
            raise RuntimeError(f"No healthy {provider} connection.")
        load_balance_mode = video_flow_provider_service.get_setting(f"load_balance:{provider}", "priority")
        if load_balance_mode == "round_robin" and len(connections) > 1:
            cursor_key = f"video_flow_provider_cursor_{provider}"
            cursor = int(video_flow_provider_service.get_setting(cursor_key, 0) or 0) % len(connections)
            video_flow_provider_service.set_setting(cursor_key, cursor + 1)
            connections = connections[cursor:] + connections[:cursor]

        prompt = self._prompt(source, mode, title)

        def attempt(secret: str) -> dict[str, Any]:
            if provider == "gemini":
                return self._call_gemini(model_id, secret, prompt)
            if provider in self._openai_endpoints:
                return self._call_openai_compatible(provider, model_id, secret, prompt)
            raise RuntimeError(f"{provider} does not expose a compatible planning endpoint yet.")

        failures: list[str] = []
        for connection in connections:
            try:
                secret = video_flow_provider_service.resolve_connection_secret(connection)
                if not secret:
                    continue
                started = time.monotonic()
                try:
                    result = attempt(secret)
                except urllib.error.HTTPError as exc:
                    if exc.code == 401:
                        try:
                            video_flow_provider_service.oauth_refresh(int(connection["id"]))
                            fresh = video_flow_provider_service.get_connection(int(connection["id"]), public=False)
                            connection = fresh or connection
                            secret = video_flow_provider_service.resolve_connection_secret(connection)
                        except Exception as refresh_exc:
                            failures.append(f"{provider}: token refresh failed ({refresh_exc})")
                            continue
                        result = attempt(secret)
                    elif exc.code == 429:
                        video_flow_provider_service.mark_cooldown(int(connection["id"]))
                        failures.append(f"{provider}: rate limited (429) — 60s cooldown")
                        continue
                    else:
                        raise
                latency_ms = int((time.monotonic() - started) * 1000)
                video_flow_provider_service.update_connection(int(connection["id"]), last_latency_ms=latency_ms)
                return result
            except Exception as exc:
                failures.append(str(exc))
        raise RuntimeError("; ".join(failures)[:700] or "Provider request failed.")

    @staticmethod
    def _prompt(source: str, mode: str, title: str, visual_language: Any = None) -> str:
        limited = source[:80_000]
        if mode == "full":
            return f"""You are the scene planner for a complete polished explanation video in Notebook Editorial medium.
Requirement: complete polished explanation.
Do not summarize or omit any paragraph.
Remove Markdown symbols from spoken text.
Use metric/chart and diverse scene structures; do not repeat one layout for consecutive scenes.
Never design dashboards.
Supply 3-5 concrete entities for visual doodles; each entity label must be at most three words.
Return JSON only (do not output JSX):
{{"scenes":[{{"type":"hook|statement|quote|metric|comparison|process|timeline|grid|chart|code|list|image|diagram|chapter|closing","title":"short title","body":"visual copy","narration":"complete spoken explanation"}}]}}
Title: {title}
Source:
{limited}"""

        return f"""You are the scene planner for a Notebook Editorial explanation video.
Summarize the source into 4-8 scenes. Narration must be accurate and substantially shorter.
Never design dashboards.
Supply 3-5 concrete entities for domain doodles; each entity label must be at most three words.
Return JSON only (do not output JSX):
{{"scenes":[{{"type":"hook|statement|quote|metric|comparison|process|timeline|grid|chart|code|list|image|diagram|chapter|closing","title":"short title","body":"visual copy","narration":"summary narration"}}]}}
Title: {title}
Mode: {mode}
Source:
{limited}"""

    def _call_claude_code(self, model_name: str, prompt: str) -> dict[str, Any]:
        cmd = ["claude", "-p", "--output-format", "json"]
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, check=True)
        return self._parse_json(proc.stdout)

    def _call_codex(self, model_name: str, prompt: str) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            out_path = tmp.name
        try:
            cmd = ["codex", "exec", "--model", model_name, "--output-last-message", out_path, "-"]
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, check=True)
            content = Path(out_path).read_text(encoding="utf-8")
            return self._parse_json(content)
        finally:
            try:
                if os.path.exists(out_path):
                    os.remove(out_path)
            except Exception:
                pass

    def request_scene_plan(self, model_ref: str, system_prompt: str, user_prompt: str) -> str | None:
        """Directly request structured scene planning JSON from a model provider."""
        if not model_ref or model_ref == "local/deterministic":
            return None
        refs = self.resolve_refs(model_ref)
        if not refs or refs == ["local/deterministic"]:
            return None

        # Check local providers
        is_local = all(ref.startswith("local/") or ref.startswith("ollama/") for ref in refs)
        if is_local:
            return None

        failures: list[str] = []
        for ref in refs:
            if "/" not in ref:
                continue
            provider, model_id = ref.split("/", 1)
            try:
                if provider == "claude":
                    combined = f"{system_prompt}\n\n{user_prompt}".strip()
                    res = self._call_claude_code(model_id, combined)
                    return json.dumps(res) if isinstance(res, dict) else str(res)
                if provider == "codex":
                    combined = f"{system_prompt}\n\n{user_prompt}".strip()
                    res = self._call_codex(model_id, combined)
                    return json.dumps(res) if isinstance(res, dict) else str(res)

                connections = [
                    c for c in video_flow_provider_service.active_connections(provider)
                    if video_flow_provider_service.connection_is_healthy(c)
                ]
                if not connections:
                    failures.append(f"No healthy {provider} connection")
                    continue

                load_balance_mode = video_flow_provider_service.get_setting(f"load_balance:{provider}", "priority")
                if load_balance_mode == "round_robin" and len(connections) > 1:
                    cursor_key = f"video_flow_provider_cursor_{provider}"
                    cursor = int(video_flow_provider_service.get_setting(cursor_key, 0) or 0) % len(connections)
                    video_flow_provider_service.set_setting(cursor_key, cursor + 1)
                    connections = connections[cursor:] + connections[:cursor]

                for connection in connections:
                    try:
                        secret = video_flow_provider_service.resolve_connection_secret(connection)
                        if not secret:
                            continue
                        started = time.monotonic()
                        try:
                            if provider == "gemini":
                                res = self._call_gemini_raw(model_id, secret, system_prompt, user_prompt)
                            elif provider in self._openai_endpoints:
                                res = self._call_openai_raw(provider, model_id, secret, system_prompt, user_prompt)
                            else:
                                raise RuntimeError(f"{provider} planning endpoint not supported")
                        except urllib.error.HTTPError as exc:
                            if exc.code == 401:
                                try:
                                    video_flow_provider_service.oauth_refresh(int(connection["id"]))
                                    fresh = video_flow_provider_service.get_connection(int(connection["id"]), public=False)
                                    connection = fresh or connection
                                    secret = video_flow_provider_service.resolve_connection_secret(connection)
                                    if provider == "gemini":
                                        res = self._call_gemini_raw(model_id, secret, system_prompt, user_prompt)
                                    elif provider in self._openai_endpoints:
                                        res = self._call_openai_raw(provider, model_id, secret, system_prompt, user_prompt)
                                except Exception as refresh_exc:
                                    failures.append(f"{provider}: token refresh failed ({refresh_exc})")
                                    continue
                            elif exc.code == 429:
                                video_flow_provider_service.mark_cooldown(int(connection["id"]))
                                failures.append(f"{provider}: rate limited (429) — 60s cooldown")
                                continue
                            else:
                                raise

                        latency_ms = int((time.monotonic() - started) * 1000)
                        video_flow_provider_service.update_connection(int(connection["id"]), last_latency_ms=latency_ms)
                        if res:
                            return res
                    except Exception as exc:
                        failures.append(f"{provider}[{connection.get('id')}]: {exc}")
            except Exception as exc:
                failures.append(f"{ref}: {exc}")

        return None

    def _call_gemini_raw(self, model_id: str, key: str, system_prompt: str, user_prompt: str) -> str:
        safe_model = urllib.parse.quote(model_id, safe="-_.")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{safe_model}:generateContent?key={urllib.parse.quote(key)}"
        )
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.35},
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def _call_gemini(self, model_id: str, key: str, prompt: str) -> dict[str, Any]:
        raw = self._call_gemini_raw(model_id, key, "", prompt)
        return self._parse_json(raw)

    def _call_openai_raw(self, provider: str, model_id: str, key: str, system_prompt: str, user_prompt: str) -> str:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": 0.35,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            self._openai_endpoints[provider],
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    def _call_openai_compatible(self, provider: str, model_id: str, key: str, prompt: str) -> dict[str, Any]:
        raw = self._call_openai_raw(provider, model_id, key, "", prompt)
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        clean = content.strip()
        fence = chr(96) * 3
        if clean.startswith(fence):
            clean = clean.removeprefix(fence + "json").removeprefix(fence).removesuffix(fence).strip()
        parsed = json.loads(clean)
        if not isinstance(parsed, dict):
            raise ValueError("Model did not return a JSON object.")
        return parsed

    def _merge(self, deterministic: dict[str, Any], planned: dict[str, Any], mode: str) -> dict[str, Any]:
        proposed = planned.get("scenes")
        if not isinstance(proposed, list) or not proposed:
            raise ValueError("Model returned no scenes.")
        if mode == "full":
            exact_scenes = deterministic["scenes"]
            original = "".join(scene["narration"] for scene in exact_scenes)
            for index, scene in enumerate(exact_scenes):
                suggestion = proposed[index] if index < len(proposed) and isinstance(proposed[index], dict) else {}
                scene_type = str(suggestion.get("type") or "")
                if scene_type in self._scene_types:
                    scene["type"] = scene_type
                scene["title"] = str(suggestion.get("title") or scene["title"])[:100]
                scene["body"] = str(suggestion.get("body") or scene["body"])[:1800]
            if "".join(scene["narration"] for scene in exact_scenes) != original:
                raise ValueError("Full explanation coverage changed during model merge.")
            deterministic["coverage"]["complete"] = True
            return deterministic

        scenes: list[dict[str, Any]] = []
        for index, raw in enumerate(proposed[:12]):
            if not isinstance(raw, dict):
                continue
            narration = str(raw.get("narration") or raw.get("body") or "").strip()
            if not narration:
                continue
            scene_type = str(raw.get("type") or "statement").lower()
            if scene_type not in self._scene_types:
                scene_type = "statement"
            words = re.findall(r"\S+", narration)
            scenes.append({
                "id": f"scene-{index + 1:03d}",
                "type": scene_type,
                "title": str(raw.get("title") or self.planner._scene_title(narration, index))[:100],
                "body": str(raw.get("body") or narration)[:1800],
                "narration": narration,
                "accent": index % 4,
                "durationSeconds": max(3.0, len(words) / 2.65 + 1.2),
                "audioFile": None,
            })
        if not scenes:
            raise ValueError("Model returned no usable scenes.")
        deterministic["scenes"] = scenes
        deterministic["coverage"] = {
            "source_characters": deterministic["coverage"]["source_characters"],
            "narrated_characters": len(" ".join(scene["narration"] for scene in scenes)),
            "complete": False,
        }
        return deterministic

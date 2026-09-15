"""Voice-polish access to the configured Video Flow model adapters.

The model picker is sourced from Video Flow.  An explicit selection therefore
has to use its connection store and gateway rather than the legacy Voice Flow
API-key pool. Video Flow remains the owner of OAuth, custom-provider, and
gateway adapters. Gemini and Chat Completions requests use Voice-only native
transports after resolution so successive dictations reuse HTTP connections;
video planning retains its isolated worker lifecycle.
"""

from __future__ import annotations

import uuid
import time
import threading
import socket
from urllib.error import HTTPError
from typing import Any

_diagnostic = threading.local()


def last_request_status() -> str:
    return str(getattr(_diagnostic, "status", "unavailable"))


class _PolishProcessManager:
    """The shared gateway expects a process manager; polish jobs need no UI state."""

    def register(self, _job_id: str, _process: Any) -> None:
        return None

    def unregister(self, _job_id: str, _process: Any) -> None:
        return None


def _parts(model_ref: str) -> tuple[str, str]:
    provider, separator, model = str(model_ref or "").strip().partition("/")
    return provider.strip().lower(), model.strip() if separator else ""


def _antigravity_generation_config(model: str, speed_mode: Any) -> dict[str, Any]:
    """Bounded generation settings for the Antigravity polish request.

    The endpoint is Gemini-compatible, so the same latency controls apply:
    deterministic low-temperature output and the lowest supported reasoning
    level. Dictation polishing needs no deliberation, and leaving the model on
    its default dynamic thinking is what made this path slow.
    """
    config: dict[str, Any] = {"temperature": 0.0, "maxOutputTokens": 4096}
    model_key = str(model or "").casefold()
    if model_key.startswith("gemini-3"):
        mode = str(speed_mode or "balanced").strip().lower()
        if mode == "quality":
            level = "high"
        elif mode == "fast":
            level = "low"
        else:
            level = "low"
        config["thinkingConfig"] = {"thinkingLevel": level}
    elif model_key.startswith("gemini-2.5"):
        config["thinkingConfig"] = {"thinkingBudget": 0}
    return config


def can_execute_model(model_ref: str) -> bool:
    """Read-only capability check for an exact Video Flow model.

    This runs while rendering the model catalog.  It deliberately avoids the
    gateway constructor because that path may refresh OAuth credentials; the
    actual request is guarded by the caller's deadline instead.
    """
    provider, model = _parts(model_ref)
    if not provider or not model:
        return False

    # Windows AI TextRewriter integration check
    if provider in ("microsoft", "windows") or model_ref in ("microsoft/windows-ai-text-rewriter", "windows/text-rewriter", "local/windows-ai-text-rewriter"):
        from voice_flow import windows_ai_rewriter
        return windows_ai_rewriter.is_windows_ai_available()

    # Liquid LFM 2.5 350M local model integration check
    if model_ref in ("local/lfm2.5-350m-qad-q4_0", "liquid/lfm2.5-350m-qad-q4_0") or model == "lfm2.5-350m-qad-q4_0":
        from voice_flow import lfm_engine
        return lfm_engine.is_lfm_downloaded()

    if provider == "local":
        return False
    try:
        from voice_flow.storage import storage

        if provider.startswith("custom-"):
            entry = next((item for item in storage.get_video_flow_custom_providers()
                          if str(item.get("id") or "").lower() == provider), None)
            if not entry or not str(entry.get("base_url") or "").startswith(("http://", "https://")):
                return False
            return bool(str(entry.get("api_key") or "").strip()) or any(
                bool(item.get("is_active")) and bool(str(item.get("key") or "").strip())
                for item in (entry.get("api_keys") or []) if isinstance(item, dict)
            )

        from voice_flow.video_flow_providers import video_flow_provider_service
        from voice_flow.video_flow_service import _PLANNING_ENDPOINTS

        provider = {"codex": "openai_codex", "nim": "nvidia_nim", "agy": "antigravity"}.get(provider, provider)
        if provider == "antigravity":
            for connection in video_flow_provider_service.active_connections("antigravity"):
                if str(connection.get("secret") or "").strip() or bool(connection.get("is_active")):
                    return True
            try:
                pconns = storage.get_provider_connections("antigravity")
                if any(bool(pc.get("is_active")) and bool(pc.get("api_key")) for pc in pconns):
                    return True
            except Exception:
                pass
            try:
                from voice_flow.video_flow_providers import antigravity_bridge_status
                if antigravity_bridge_status().get("ready"):
                    return True
            except Exception:
                pass
            return True

        if provider not in _PLANNING_ENDPOINTS:
            return False
        now = time.time()
        for connection in video_flow_provider_service.active_connections(provider):
            status = str(connection.get("status") or "").lower()
            if status in {"expired", "rate_limited", "error"}:
                continue
            try:
                if 0 < float(connection.get("expires_at") or 0) <= now:
                    continue
                if float(connection.get("cooldown_until") or 0) > now:
                    continue
            except (TypeError, ValueError):
                continue
            # The encrypted value need not be decrypted just to render the
            # picker; nonempty stored secret means the gateway can resolve it.
            if str(connection.get("secret") or "").strip():
                return True
        return False
    except Exception:
        return False


def request_polish(
    model_ref: str, prompt: str, *, timeout_seconds: float, speed_mode: object = None
) -> str | None:
    """Execute the selected adapter and retain its per-thread outcome."""
    _diagnostic.status = "unavailable"
    result = _request_polish(model_ref, prompt, timeout_seconds=timeout_seconds, speed_mode=speed_mode)
    if result:
        _diagnostic.status = "ok"
    return result


def _request_polish(
    model_ref: str, prompt: str, *, timeout_seconds: float, speed_mode: object = None
) -> str | None:
    """Run *model_ref* through its exact Video Flow adapter.

    No provider or model substitution occurs here.  ``None`` means the
    selected connection is unavailable so the caller may use its local/Voice
    fallback policy.

    ``speed_mode`` is forwarded to the native Gemini transport so its
    supported thinking level matches the policy captured for this dictation.
    """
    provider, model = _parts(model_ref)
    if not provider or not model:
        return None

    # Windows AI TextRewriter execution
    if provider in ("microsoft", "windows") or model_ref in ("microsoft/windows-ai-text-rewriter", "windows/text-rewriter", "local/windows-ai-text-rewriter"):
        from voice_flow import windows_ai_rewriter
        if windows_ai_rewriter.is_windows_ai_available():
            return windows_ai_rewriter.rewrite_text(prompt, timeout_seconds=timeout_seconds)
        return None

    # Liquid LFM 2.5 350M local execution
    if model_ref in ("local/lfm2.5-350m-qad-q4_0", "liquid/lfm2.5-350m-qad-q4_0") or model == "lfm2.5-350m-qad-q4_0":
        from voice_flow import lfm_engine
        if lfm_engine.is_lfm_downloaded():
            return lfm_engine.polish_with_lfm(prompt, timeout_seconds=timeout_seconds)
        return None

    if provider == "local":
        return None
    try:
        from voice_flow.video_flow_service import ProviderModelGateway
        from voice_flow.storage import storage

        if provider.startswith("custom-"):
            gateway = ProviderModelGateway._from_custom_provider(storage, provider, model)
        elif provider in ("antigravity", "agy"):
            from voice_flow.video_flow_providers import video_flow_provider_service
            token = ""
            for conn in video_flow_provider_service.active_connections("antigravity"):
                token = video_flow_provider_service.resolve_connection_secret(conn)
                if token:
                    break
            if not token:
                try:
                    pconns = storage.get_provider_connections("antigravity")
                    for pc in pconns:
                        if pc.get("is_active") and pc.get("api_key"):
                            token = str(pc.get("api_key") or "").strip()
                            if token:
                                break
                except Exception:
                    token = ""
            if token:
                try:
                    import urllib.request as _urq
                    import json as _json
                    ccpa_body = {
                        "project": "aicode-consumers",
                        "model": model,
                        "request": {
                            "contents": [
                                {"role": "user", "parts": [{"text": prompt}]}
                            ],
                            # Without a generationConfig the model applies its
                            # own default dynamic reasoning, which is the main
                            # source of the multi-second first-token latency.
                            # Polishing is simple instruction following, so
                            # request a bounded, low-reasoning answer and let
                            # the model return as soon as it is ready.
                            "generationConfig": _antigravity_generation_config(model, speed_mode),
                        },
                    }
                    ccpa_req = _urq.Request(
                        "https://cloudcode-pa.googleapis.com/v1internal:generateContent",
                        data=_json.dumps(ccpa_body).encode("utf-8"),
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                            "User-Agent": "antigravity/ide/2.1.1 win32/x64",
                            "X-Client-Name": "antigravity",
                            "X-Client-Version": "2.1.1",
                            "x-request-source": "local",
                        },
                        method="POST",
                    )
                    with _urq.urlopen(ccpa_req, timeout=max(0.05, float(timeout_seconds))) as resp:
                        res_data = _json.loads(resp.read().decode("utf-8"))
                        candidates = res_data.get("candidates") or []
                        if candidates:
                            parts = (candidates[0].get("content") or {}).get("parts") or []
                            txt = "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict) and not p.get("thought")).strip()
                            if txt:
                                return txt
                except (TimeoutError, socket.timeout):
                    _diagnostic.status = "timeout"
                except HTTPError as exc:
                    _diagnostic.status = f"http_{exc.code}"
                except Exception:
                    _diagnostic.status = "error"
            # Antigravity is an OAuth-backed provider.  A Gemini API key is a
            # different credential and account, so it cannot be used as an
            # implicit alias after an OAuth request is unavailable or fails.
            return None
        else:
            gateway = ProviderModelGateway._from_video_provider_service(provider, model)
        if gateway is None:
            return None
        # Reuse Voice connections after resolving the exact selected account.
        if getattr(gateway, "_provider", "") == "gemini":
            from voice_flow.voice_gemini_transport import request_gemini_polish, last_transport_diagnostic

            result = request_gemini_polish(
                api_key=str(getattr(gateway, "_api_key", "") or ""),
                model=str(getattr(gateway, "_model_id", "") or model),
                prompt=prompt,
                # Return inside the caller's hard bridge guard so a timed-out
                # socket is retired before it can hold the Voice lane busy.
                timeout_seconds=max(0.05, float(timeout_seconds) - 0.15),
                speed_mode=speed_mode,
            )
            _diagnostic.status = last_transport_diagnostic().get("status", "error")
            return result
        # API-key chat adapters can execute in-process. Keep specialized OAuth
        # protocols on their existing worker; Video Flow itself is unchanged.
        endpoint = str(getattr(gateway, "_endpoint", "") or "")
        if endpoint.rstrip("/").endswith("/chat/completions"):
            from voice_flow.voice_provider_transport import request_chat
            result, status = request_chat(
                endpoint=endpoint, api_key=str(getattr(gateway, "_api_key", "") or ""),
                model=str(getattr(gateway, "_model_id", "") or model),
                messages=[{"role": "user", "content": prompt}],
                timeout_seconds=max(0.05, float(timeout_seconds) - 0.15),
            )
            _diagnostic.status = status
            return result
        return gateway.request_isolated(
            prompt=prompt,
            model_ref=model_ref,
            max_tokens=4_096,
            timeout_seconds=max(0.05, float(timeout_seconds)),
            job_id="voice-polish-" + uuid.uuid4().hex,
            process_manager=_PolishProcessManager(),
            reasoning_compatible=True,
        )
    except (TimeoutError, socket.timeout):
        _diagnostic.status = "timeout"
        return None
    except Exception:
        _diagnostic.status = "error"
        return None

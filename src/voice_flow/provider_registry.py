"""Provider Registry Definitions for Voice Flow API Key Provider System."""

from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass(frozen=True)
class ProviderNotice:
    text: str
    api_key_url: str


@dataclasses.dataclass(frozen=True)
class ProviderDisplay:
    name: str
    icon: str
    color: str
    website: str
    notice: ProviderNotice


@dataclasses.dataclass(frozen=True)
class ProviderThinkingConfig:
    options: list[str]
    default_mode: str


@dataclasses.dataclass(frozen=True)
class ProviderTransport:
    format: str  # "openai", "gemini", "anthropic"
    base_url: str
    validate_url: str | None
    auth_header: str  # "bearer", "x-api-key", "key-query"


@dataclasses.dataclass(frozen=True)
class ProviderModel:
    id: str
    name: str
    kind: str = "llm"


@dataclasses.dataclass(frozen=True)
class ProviderModelsFetcher:
    url: str
    type: str = "openai"


@dataclasses.dataclass(frozen=True)
class ProviderSpec:
    id: str
    alias: str
    ui_alias: str
    display: ProviderDisplay
    category: str  # "apikey", "free", "cookie", "oauth"
    thinking_config: ProviderThinkingConfig
    transport: ProviderTransport
    models: list[ProviderModel]
    models_fetcher: ProviderModelsFetcher | None = None
    passthrough_models: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "alias": self.alias,
            "uiAlias": self.ui_alias,
            "display": {
                "name": self.display.name,
                "icon": self.display.icon,
                "color": self.display.color,
                "website": self.display.website,
                "notice": {
                    "text": self.display.notice.text,
                    "apiKeyUrl": self.display.notice.api_key_url,
                },
            },
            "category": self.category,
            "thinkingConfig": {
                "options": self.thinking_config.options,
                "defaultMode": self.thinking_config.default_mode,
            },
            "transport": {
                "format": self.transport.format,
                "baseUrl": self.transport.base_url,
                "validateUrl": self.transport.validate_url,
                "authHeader": self.transport.auth_header,
            },
            "models": [
                {"id": m.id, "name": m.name, "kind": m.kind} for m in self.models
            ],
            "modelsFetcher": (
                {
                    "url": self.models_fetcher.url,
                    "type": self.models_fetcher.type,
                }
                if self.models_fetcher
                else None
            ),
            "passthroughModels": self.passthrough_models,
        }


# Registry of all supported providers
PROVIDERS_REGISTRY: dict[str, ProviderSpec] = {
    "tokenrouter": ProviderSpec(
        id="tokenrouter",
        alias="tokenrouter",
        ui_alias="tokenrouter",
        display=ProviderDisplay(
            name="TokenRouter",
            icon="hub",
            color="#0EA5E9",
            website="https://www.tokenrouter.com",
            notice=ProviderNotice(
                text="OpenAI-compatible gateway with 300+ models.",
                api_key_url="https://www.tokenrouter.com/keys",
            ),
        ),
        category="apikey",
        thinking_config=ProviderThinkingConfig(
            options=["low", "medium", "high"], default_mode="medium"
        ),
        transport=ProviderTransport(
            format="openai",
            base_url="https://api.tokenrouter.com/v1/chat/completions",
            validate_url="https://api.tokenrouter.com/v1/models",
            auth_header="bearer",
        ),
        models=[
            ProviderModel("openai/gpt-4o", "GPT-4o"),
            ProviderModel("anthropic/claude-3-5-sonnet", "Claude 3.5 Sonnet"),
        ],
        models_fetcher=ProviderModelsFetcher(
            url="https://api.tokenrouter.com/v1/models", type="openai"
        ),
        passthrough_models=True,
    ),
    "openai": ProviderSpec(
        id="openai",
        alias="openai",
        ui_alias="openai",
        display=ProviderDisplay(
            name="OpenAI",
            icon="zap",
            color="#10A37F",
            website="https://platform.openai.com",
            notice=ProviderNotice(
                text="Industry standard AI models including GPT-4o.",
                api_key_url="https://platform.openai.com/api-keys",
            ),
        ),
        category="apikey",
        thinking_config=ProviderThinkingConfig(
            options=["low", "medium", "high"], default_mode="medium"
        ),
        transport=ProviderTransport(
            format="openai",
            base_url="https://api.openai.com/v1/chat/completions",
            validate_url="https://api.openai.com/v1/models",
            auth_header="bearer",
        ),
        models=[
            ProviderModel("gpt-4o-mini", "GPT-4o Mini"),
            ProviderModel("gpt-4.1-mini", "GPT-4.1 Mini"),
            ProviderModel("gpt-4o", "GPT-4o"),
        ],
        models_fetcher=ProviderModelsFetcher(
            url="https://api.openai.com/v1/models", type="openai"
        ),
        passthrough_models=True,
    ),
    "anthropic": ProviderSpec(
        id="anthropic",
        alias="anthropic",
        ui_alias="anthropic",
        display=ProviderDisplay(
            name="Anthropic",
            icon="cpu",
            color="#D97706",
            website="https://console.anthropic.com",
            notice=ProviderNotice(
                text="Claude 3.5 Sonnet and Claude 3 Opus models.",
                api_key_url="https://console.anthropic.com/settings/keys",
            ),
        ),
        category="apikey",
        thinking_config=ProviderThinkingConfig(
            options=["low", "medium", "high"], default_mode="high"
        ),
        transport=ProviderTransport(
            format="anthropic",
            base_url="https://api.anthropic.com/v1/messages",
            validate_url=None,
            auth_header="x-api-key",
        ),
        models=[
            ProviderModel("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet"),
            ProviderModel("claude-3-haiku-20240307", "Claude 3 Haiku"),
        ],
        passthrough_models=True,
    ),
    "gemini": ProviderSpec(
        id="gemini",
        alias="gemini",
        ui_alias="gemini",
        display=ProviderDisplay(
            name="Google Gemini",
            icon="sparkles",
            color="#4285F4",
            website="https://aistudio.google.com",
            notice=ProviderNotice(
                text="Fast and capable Gemini 3.6 Flash & 2.5 Flash models.",
                api_key_url="https://aistudio.google.com/app/apikey",
            ),
        ),
        category="apikey",
        thinking_config=ProviderThinkingConfig(
            options=["low", "medium", "high"], default_mode="medium"
        ),
        transport=ProviderTransport(
            format="gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent",
            validate_url="https://generativelanguage.googleapis.com/v1beta/models",
            auth_header="key-query",
        ),
        models=[
            ProviderModel("gemini-3.6-flash", "Gemini 3.6 Flash"),
            ProviderModel("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite"),
        ],
        passthrough_models=True,
    ),
    "deepseek": ProviderSpec(
        id="deepseek",
        alias="deepseek",
        ui_alias="deepseek",
        display=ProviderDisplay(
            name="DeepSeek",
            icon="code",
            color="#4F46E5",
            website="https://platform.deepseek.com",
            notice=ProviderNotice(
                text="High-performance reasoning and chat models.",
                api_key_url="https://platform.deepseek.com/api_keys",
            ),
        ),
        category="apikey",
        thinking_config=ProviderThinkingConfig(
            options=["low", "medium", "high"], default_mode="high"
        ),
        transport=ProviderTransport(
            format="openai",
            base_url="https://api.deepseek.com/v1/chat/completions",
            validate_url="https://api.deepseek.com/v1/models",
            auth_header="bearer",
        ),
        models=[
            ProviderModel("deepseek-chat", "DeepSeek V3"),
            ProviderModel("deepseek-reasoner", "DeepSeek R1"),
        ],
        models_fetcher=ProviderModelsFetcher(
            url="https://api.deepseek.com/v1/models", type="openai"
        ),
        passthrough_models=True,
    ),
    "openrouter": ProviderSpec(
        id="openrouter",
        alias="openrouter",
        ui_alias="openrouter",
        display=ProviderDisplay(
            name="OpenRouter",
            icon="globe",
            color="#6366F1",
            website="https://openrouter.ai",
            notice=ProviderNotice(
                text="Unified API access to hundreds of AI models.",
                api_key_url="https://openrouter.ai/keys",
            ),
        ),
        category="apikey",
        thinking_config=ProviderThinkingConfig(
            options=["low", "medium", "high"], default_mode="medium"
        ),
        transport=ProviderTransport(
            format="openai",
            base_url="https://openrouter.ai/api/v1/chat/completions",
            validate_url="https://openrouter.ai/api/v1/models",
            auth_header="bearer",
        ),
        models=[
            ProviderModel("openai/gpt-4o", "GPT-4o"),
            ProviderModel("anthropic/claude-3.5-sonnet", "Claude 3.5 Sonnet"),
            ProviderModel("meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B"),
        ],
        models_fetcher=ProviderModelsFetcher(
            url="https://openrouter.ai/api/v1/models", type="openai"
        ),
        passthrough_models=True,
    ),
    "groq": ProviderSpec(
        id="groq",
        alias="groq",
        ui_alias="groq",
        display=ProviderDisplay(
            name="Groq",
            icon="activity",
            color="#F97316",
            website="https://console.groq.com",
            notice=ProviderNotice(
                text="Ultra-fast LPU inference engine.",
                api_key_url="https://console.groq.com/keys",
            ),
        ),
        category="apikey",
        thinking_config=ProviderThinkingConfig(
            options=["low", "medium", "high"], default_mode="low"
        ),
        transport=ProviderTransport(
            format="openai",
            base_url="https://api.groq.com/openai/v1/chat/completions",
            validate_url="https://api.groq.com/openai/v1/models",
            auth_header="bearer",
        ),
        models=[
            ProviderModel("llama-3.3-70b-specdec", "Llama 3.3 70B SpecDec"),
            ProviderModel("meta-llama/llama-4-scout-17b-16e-instruct", "Llama 4 Scout 17B"),
        ],
        models_fetcher=ProviderModelsFetcher(
            url="https://api.groq.com/openai/v1/models", type="openai"
        ),
        passthrough_models=True,
    ),
    "mistral": ProviderSpec(
        id="mistral",
        alias="mistral",
        ui_alias="mistral",
        display=ProviderDisplay(
            name="Mistral AI",
            icon="wind",
            color="#EC4899",
            website="https://console.mistral.ai",
            notice=ProviderNotice(
                text="Open and commercial frontier models from Mistral.",
                api_key_url="https://console.mistral.ai/api-keys",
            ),
        ),
        category="apikey",
        thinking_config=ProviderThinkingConfig(
            options=["low", "medium", "high"], default_mode="medium"
        ),
        transport=ProviderTransport(
            format="openai",
            base_url="https://api.mistral.ai/v1/chat/completions",
            validate_url="https://api.mistral.ai/v1/models",
            auth_header="bearer",
        ),
        models=[
            ProviderModel("mistral-small-latest", "Mistral Small"),
            ProviderModel("mistral-large-latest", "Mistral Large"),
        ],
        models_fetcher=ProviderModelsFetcher(
            url="https://api.mistral.ai/v1/models", type="openai"
        ),
        passthrough_models=True,
    ),
}


def get_provider_spec(provider_id: str) -> ProviderSpec | None:
    return PROVIDERS_REGISTRY.get(provider_id.lower())


def get_all_provider_specs() -> list[ProviderSpec]:
    return list(PROVIDERS_REGISTRY.values())

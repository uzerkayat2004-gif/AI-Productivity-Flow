"""Optional Tavily web research for Video Flow planning.

When the user saved a Tavily key (or set ``TAVILY_API_KEY``) *and* ticked
"Research with web sources" for a video, the planner gets a short list of
web sources about the topic. The sources (title, URL, a trimmed snippet) are
fed into the planning prompt and kept in the plan output so the video can
credit them.

Everything here is optional. No key, the box not ticked, or any Tavily error
all mean the same thing: no sources, and the video is planned exactly as
before.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

PROVIDER_ID = "tavily"
SEARCH_URL = "https://api.tavily.com/search"
USAGE_URL = "https://api.tavily.com/usage"
ENV_KEY = "TAVILY_API_KEY"
API_KEY_URL = "https://app.tavily.com"

DEFAULT_MAX_RESULTS = 5
MAX_QUERY_CHARS = 380
MAX_SNIPPET_CHARS = 600
MAX_PROMPT_CHARS = 4_000


def _provider_service():
    from voice_flow.video_flow_providers import video_flow_provider_service

    return video_flow_provider_service


def resolve_api_key(service: Any = None) -> str:
    """First healthy saved Tavily key, else ``TAVILY_API_KEY``."""
    try:
        svc = service or _provider_service()
        for connection in svc.active_connections(PROVIDER_ID):
            if not svc.connection_is_healthy(connection):
                continue
            secret = svc.resolve_connection_secret(connection)
            if secret:
                return str(secret).strip()
    except Exception:
        pass
    return str(os.environ.get(ENV_KEY) or "").strip()


def research_requested(options: dict[str, Any]) -> bool:
    value = options.get("research_web")
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return value is True


def build_query(source_text: str, *, title: str = "", focus: str = "") -> str:
    """A short search query: the title/focus first, then the opening text."""
    parts = [str(title or "").strip(), str(focus or "").strip()]
    text = re.sub(r"\s+", " ", str(source_text or "")).strip()
    if text:
        parts.append(text[:MAX_QUERY_CHARS])
    query = " - ".join(p for p in parts if p)
    query = re.sub(r"\s+", " ", query).strip()
    return query[:MAX_QUERY_CHARS].rstrip()


def _clean_source(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    url = str(item.get("url") or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return None
    title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()[:200] or url
    snippet = re.sub(r"\s+", " ", str(item.get("content") or "")).strip()
    if len(snippet) > MAX_SNIPPET_CHARS:
        snippet = snippet[:MAX_SNIPPET_CHARS].rsplit(" ", 1)[0] + "…"
    source: dict[str, Any] = {"title": title, "url": url, "snippet": snippet}
    try:
        if item.get("score") is not None:
            source["score"] = round(float(item["score"]), 4)
    except (TypeError, ValueError):
        pass
    if item.get("published_date"):
        source["published_date"] = str(item["published_date"])[:60]
    try:
        # Web text must pass the same boundary as model output: a source
        # that looks like code is dropped rather than failing the video.
        from voice_flow.video_flow_contracts import validate_no_executable_code

        validate_no_executable_code(source)
    except ValueError:
        return None
    return source


def search(
    query: str,
    *,
    api_key: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout: float = 15.0,
) -> list[dict[str, Any]]:
    """Call Tavily Search. Raises on HTTP or network failure."""
    if not api_key or not query.strip():
        return []
    body = {
        "query": query.strip()[:MAX_QUERY_CHARS],
        "search_depth": "basic",
        "max_results": max(1, min(int(max_results), 10)),
        "topic": "general",
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
    }
    request = urllib.request.Request(
        SEARCH_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "VoiceFlow/2.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    results = payload.get("results") if isinstance(payload, dict) else None
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in results or []:
        source = _clean_source(item)
        if source and source["url"] not in seen:
            seen.add(source["url"])
            sources.append(source)
    return sources[:max_results]


def gather_sources(
    source_text: str,
    options: dict[str, Any],
    *,
    api_key: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout: float = 15.0,
) -> list[dict[str, Any]]:
    """Return web sources for a video, or ``[]``. Never raises."""
    if not research_requested(options):
        return []
    key = api_key if api_key is not None else resolve_api_key()
    if not key:
        log.info("Video Flow web research was requested but no Tavily key is set; planning without it")
        return []
    query = build_query(
        source_text,
        title=str(options.get("title") or ""),
        focus=str(options.get("focus") or options.get("visual_direction") or ""),
    )
    if not query:
        return []
    try:
        return search(query, api_key=key, max_results=max_results, timeout=timeout)
    except urllib.error.HTTPError as exc:
        log.warning("Tavily search failed (HTTP %s); planning without web sources", exc.code)
    except Exception as exc:
        log.warning("Tavily search failed (%s); planning without web sources", exc.__class__.__name__)
    return []


def format_for_prompt(sources: list[dict[str, Any]]) -> str:
    """Prompt block that hands the sources to the planning model."""
    if not sources:
        return ""
    lines = [
        "",
        "",
        "Web research (Tavily). Use these sources only to check facts and add current context.",
        "The user's source text stays the main material. Do not invent facts the sources do not support.",
        "If you use a source, mention its title naturally in the narration only when it helps.",
    ]
    for index, source in enumerate(sources, start=1):
        lines.append(f"[{index}] {source.get('title')} - {source.get('url')}")
        if source.get("snippet"):
            lines.append(f"    {source['snippet']}")
    block = "\n".join(lines)
    return block[:MAX_PROMPT_CHARS]


def public_sources(sources: list[dict[str, Any]]) -> list[dict[str, str]]:
    """What is kept in the plan output: title and URL only."""
    return [{"title": str(s.get("title") or ""), "url": str(s.get("url") or "")} for s in sources if s.get("url")]


__all__ = [
    "API_KEY_URL",
    "ENV_KEY",
    "PROVIDER_ID",
    "SEARCH_URL",
    "USAGE_URL",
    "build_query",
    "format_for_prompt",
    "gather_sources",
    "public_sources",
    "research_requested",
    "resolve_api_key",
    "search",
]

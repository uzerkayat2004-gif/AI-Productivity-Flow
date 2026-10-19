"""Optional Tavily web research for Video Flow planning (HTTP mocked)."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path

import pytest

from voice_flow import tavily_research

RESULTS = {
    "query": "q",
    "results": [
        {"title": "Nemotron overview", "url": "https://example.com/nemotron", "content": "Nemotron is a family of open models.", "score": 0.91},
        {"title": "Duplicate", "url": "https://example.com/nemotron", "content": "dup"},
        {"title": "No URL", "url": "ftp://bad", "content": "x"},
        {"title": "Looks like code eval(", "url": "https://example.com/x", "content": "<script>"},
        {"title": "Token Factory docs", "url": "https://docs.tokenfactory.nebius.com/", "content": "OpenAI-compatible API."},
    ],
}


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class FakeTavily:
    def __init__(self, status: int | None = None):
        self.status = status
        self.calls = []

    def __call__(self, request, timeout=None):
        headers = {k.lower(): v for k, v in request.header_items()}
        self.calls.append({"url": request.full_url, "headers": headers, "body": json.loads(request.data or b"{}"), "method": request.get_method()})
        if self.status:
            raise urllib.error.HTTPError(request.full_url, self.status, "err", {}, io.BytesIO(b"{}"))
        return _Response(json.dumps(RESULTS).encode())


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)


@pytest.fixture
def provider_service(tmp_path, monkeypatch):
    from voice_flow import video_flow_providers as providers_module

    service = providers_module.VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    monkeypatch.setattr(providers_module, "video_flow_provider_service", service)
    return service


def _no_network(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call expected")))


def test_tavily_is_an_optional_research_provider_not_a_model_provider():
    from voice_flow import video_flow_providers, video_flow_service

    entry = video_flow_providers.PROVIDER_BY_ID["tavily"]
    assert entry["kind"] == "research" and entry["auth"] == "api_key"
    assert "tavily" not in video_flow_service._PLANNING_ENDPOINTS
    assert not [m for m in video_flow_providers.DEFAULT_MODELS if m[0] == "tavily"]


def test_not_requested_means_no_call(monkeypatch):
    _no_network(monkeypatch)
    assert tavily_research.gather_sources("text", {"research_web": False}, api_key="tvly-1") == []
    assert tavily_research.gather_sources("text", {}, api_key="tvly-1") == []


def test_requested_without_key_means_no_call(monkeypatch, provider_service):
    _no_network(monkeypatch)
    assert tavily_research.gather_sources("text", {"research_web": True}) == []


def test_search_request_and_cleaned_sources(monkeypatch):
    http = FakeTavily()
    monkeypatch.setattr("urllib.request.urlopen", http)
    sources = tavily_research.gather_sources(
        "NVIDIA Nemotron models power the planner.", {"research_web": True, "title": "Nemotron"}, api_key="tvly-1"
    )
    assert [s["url"] for s in sources] == ["https://example.com/nemotron", "https://docs.tokenfactory.nebius.com/"]
    assert sources[0]["title"] == "Nemotron overview"
    call = http.calls[0]
    assert call["url"] == "https://api.tavily.com/search" and call["method"] == "POST"
    assert call["headers"]["authorization"] == "Bearer tvly-1"
    assert call["body"]["query"].startswith("Nemotron - NVIDIA Nemotron")
    assert call["body"]["max_results"] == 5 and call["body"]["search_depth"] == "basic"


def test_saved_key_or_env_key(monkeypatch, provider_service):
    provider_service.add_connection("tavily", name="Main", secret="tvly-saved")
    assert tavily_research.resolve_api_key(provider_service) == "tvly-saved"
    for conn in provider_service.list_connections("tavily"):
        provider_service.delete_connection(conn["id"])
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-env")
    assert tavily_research.resolve_api_key(provider_service) == "tvly-env"


@pytest.mark.parametrize("status", [401, 429, 432, 500])
def test_tavily_errors_never_break_planning(monkeypatch, status):
    monkeypatch.setattr("urllib.request.urlopen", FakeTavily(status=status))
    assert tavily_research.gather_sources("text", {"research_web": True}, api_key="tvly-1") == []


def test_prompt_block_and_public_sources():
    sources = [{"title": "A", "url": "https://a.example", "snippet": "alpha"}]
    block = tavily_research.format_for_prompt(sources)
    assert "[1] A - https://a.example" in block and "alpha" in block
    assert tavily_research.format_for_prompt([]) == ""
    assert tavily_research.public_sources(sources) == [{"title": "A", "url": "https://a.example"}]


def test_tavily_test_button_uses_usage_endpoint(monkeypatch, provider_service):
    calls = []

    def fake(request, timeout=None):
        calls.append((request.full_url, dict(request.header_items())))
        return _Response(b'{"key": {"usage": 1}}')

    monkeypatch.setattr("urllib.request.urlopen", fake)
    conn = provider_service.add_connection("tavily", name="Main", secret="tvly-1")
    assert provider_service.test_connection(conn["id"])["success"] is True
    assert calls[0][0] == "https://api.tavily.com/usage"


# --- planning integration ---------------------------------------------------


def test_engine_research_needs_box_and_external_ai_consent(monkeypatch, tmp_path):
    from voice_flow.video_flow_engine.engine import VideoFlowEngine

    calls = []
    monkeypatch.setattr(tavily_research, "gather_sources", lambda text, opts, **k: calls.append(opts) or [{"title": "A", "url": "https://a.example"}])
    report = lambda *a, **k: None  # noqa: E731
    assert VideoFlowEngine._gather_research_sources("t", {"research_web": True, "allow_external_ai": False}, tmp_path, report) == []
    assert VideoFlowEngine._gather_research_sources("t", {"research_web": False, "allow_external_ai": True}, tmp_path, report) == []
    assert calls == []
    got = VideoFlowEngine._gather_research_sources("t", {"research_web": True, "allow_external_ai": True}, tmp_path, report)
    assert got == [{"title": "A", "url": "https://a.example"}]
    saved = json.loads((tmp_path / "plan" / "research_sources.json").read_text(encoding="utf-8"))
    assert saved == {"provider": "tavily", "sources": [{"title": "A", "url": "https://a.example"}]}


def test_planner_feeds_sources_into_prompt_and_keeps_them_in_plan(tmp_path: Path):
    from voice_flow import runtime_env
    from voice_flow.video_flow_engine.code2video_runner import Code2VideoRunner

    root = runtime_env.code2video_root()
    if not (root and (root / "prompts" / "stage1.py").is_file()):
        pytest.skip("vendored Code2Video prompts not present")

    prompts: list[str] = []

    def gateway(prompt: str, **_: object) -> str:
        prompts.append(prompt)
        if len(prompts) == 1:
            return json.dumps({"topic": "Nemotron", "target_audience": "builders", "sections": [{"id": "s1", "title": "What it is", "content": "Open models."}]})
        return json.dumps({"sections": [{"id": "s1", "title": "What it is", "lecture_lines": ["Nemotron is open."], "animations": ["Show logo."]}]})

    gateway.is_local = True
    sources = [{"title": "Nemotron overview", "url": "https://example.com/nemotron", "snippet": "Open model family."}]
    result = Code2VideoRunner(gateway=gateway).plan(
        "Explain NVIDIA Nemotron.", project_dir=tmp_path, duration_seconds=30, allow_external_ai=True, research_sources=sources
    )
    assert "https://example.com/nemotron" in prompts[0]
    assert "Web research (Tavily)" in prompts[0]
    assert result["research_sources"] == [{"title": "Nemotron overview", "url": "https://example.com/nemotron"}]
    stored = json.loads((tmp_path / "storyboard" / "storyboard.json").read_text(encoding="utf-8"))
    assert stored["research_sources"][0]["url"] == "https://example.com/nemotron"


def test_planner_without_sources_is_unchanged(tmp_path: Path):
    from voice_flow import runtime_env
    from voice_flow.video_flow_engine.code2video_runner import Code2VideoRunner

    root = runtime_env.code2video_root()
    if not (root and (root / "prompts" / "stage1.py").is_file()):
        pytest.skip("vendored Code2Video prompts not present")
    prompts: list[str] = []

    def gateway(prompt: str, **_: object) -> str:
        prompts.append(prompt)
        if len(prompts) == 1:
            return json.dumps({"topic": "T", "target_audience": "a", "sections": [{"id": "s1", "title": "x", "content": "y"}]})
        return json.dumps({"sections": [{"id": "s1", "title": "x", "lecture_lines": ["l"], "animations": ["a"]}]})

    gateway.is_local = True
    result = Code2VideoRunner(gateway=gateway).plan("Some text.", project_dir=tmp_path, duration_seconds=30, allow_external_ai=True)
    assert "research_sources" not in result
    assert "Web research" not in prompts[0]

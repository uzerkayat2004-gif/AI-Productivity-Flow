"""Focused regression tests for the Voice Flow polish deadline contract."""

from __future__ import annotations

import socket
import time

import pytest

import voice_flow.polisher as polisher_module
from voice_flow.dictionary import DictionaryEngine
from voice_flow.style_engine import StyleEngine
from voice_flow.polisher import TextPolisher


def _configure_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_setting(key: str, default=None):
        if key == "polishing_enabled":
            return True
        if key == "voice_flow_polish_model":
            return "gemini/gemini-3.5-flash"
        return default

    monkeypatch.setattr(polisher_module.storage, "get_setting", get_setting)
    monkeypatch.setattr(
        polisher_module.storage,
        "get_all_api_keys",
        lambda: {"gemini": "fake-key", "groq": "groq-key"},
    )
    monkeypatch.setattr(polisher_module.storage, "get_all_provider_connections", lambda: {})
    monkeypatch.setattr(
        polisher_module.dictionary_engine,
        "apply_dictionary_post_processing",
        lambda text: text,
    )


def test_expired_deadline_skips_provider_and_keeps_local_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """An already-expired interactive budget must not enter the provider pool."""
    _configure_storage(monkeypatch)
    engine = TextPolisher()
    calls: list[tuple] = []

    def unexpected_provider_call(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("expired polish deadline entered the provider pool")

    monkeypatch.setattr(engine, "_try_provider_call", unexpected_provider_call)

    result = engine.polish(
        "um please keep this content when providers are unavailable",
        deadline=time.monotonic() - 0.001,
    )

    assert not calls
    assert "please keep this content when providers are unavailable" in result.lower()


def test_deadline_is_forwarded_and_clamps_provider_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pool receives the caller deadline and never asks for more time."""
    _configure_storage(monkeypatch)
    engine = TextPolisher()
    calls: list[tuple[str, str | None, float | None]] = []
    now = time.monotonic()
    deadline = now + 0.35

    def provider_call(provider, key, system_prompt, user_content, model=None, timeout=None):
        calls.append((provider, model, timeout))
        return None

    monkeypatch.setattr(engine, "_try_provider_call", provider_call)
    monkeypatch.setattr(polisher_module.time, "monotonic", lambda: now)

    assert engine._polish_with_api_pool(
        "please keep this content when providers are unavailable",
        {"gemini": "fake-key"},
        deadline=deadline,
    ) is None

    assert calls
    assert all(timeout is not None and 0 < timeout <= deadline - now for _, _, timeout in calls)


def test_deadline_guard_stops_provider_that_ignores_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blocking provider double cannot hold the interactive pipeline open."""
    _configure_storage(monkeypatch)
    engine = TextPolisher()
    started = False

    def blocking_provider(*_args, **_kwargs):
        nonlocal started
        started = True
        time.sleep(0.6)
        return "This late provider result must not be reported as AI success."

    monkeypatch.setattr(engine, "_try_provider_call", blocking_provider)

    started_at = time.monotonic()
    result = engine.polish(
        "please preserve this transcript while the provider ignores its timeout",
        deadline=started_at + 0.45,
    )
    elapsed = time.monotonic() - started_at

    assert started
    assert elapsed < 0.4
    assert "please preserve this transcript while the provider ignores its timeout" in result.lower()


def test_guarded_provider_receives_timeout_remaining_at_worker_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scheduling delay must reduce the provider's own timeout, not only the outer guard."""
    engine = TextPolisher()
    clock = [100.0]
    seen: list[float] = []

    class DelayedThread:
        def __init__(self, *, target, **_kwargs):
            self.target = target

        def start(self) -> None:
            clock[0] += 0.1
            self.target()

    monkeypatch.setattr(polisher_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(polisher_module.threading, "Thread", DelayedThread)
    monkeypatch.setattr(
        engine,
        "_try_provider_call",
        lambda *_args, **kwargs: seen.append(kwargs["timeout"]) or "complete text",
    )

    assert engine._try_provider_call_with_deadline(
        "gemini", "key", "system", "text", None, timeout=5.0, deadline=100.5,
    ) == "complete text"
    assert seen == [pytest.approx(0.4)]


def test_exact_model_bridge_receives_remaining_deadline_and_speed_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bridge must retain captured policy while respecting the same hard deadline."""
    engine = TextPolisher()
    clock = [100.0]
    seen: dict[str, object] = {}

    class DelayedThread:
        def __init__(self, *, target, **_kwargs):
            self.target = target

        def start(self) -> None:
            clock[0] += 0.1
            self.target()

    monkeypatch.setattr(polisher_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(polisher_module.threading, "Thread", DelayedThread)

    result = engine._run_bridge_with_timeout(
        lambda provider_timeout: seen.update(timeout=provider_timeout, mode="fast") or "complete text",
        timeout=5.0,
        deadline=100.5,
    )

    assert result == "complete text"
    assert seen["timeout"] == pytest.approx(0.4)
    assert seen["mode"] == "fast"


def test_bridge_callback_timeout_never_exceeds_its_own_or_caller_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = TextPolisher()
    clock = [100.0]
    seen: list[float] = []

    class DelayedThread:
        def __init__(self, *, target, **_kwargs):
            self.target = target

        def start(self) -> None:
            clock[0] += 0.1
            self.target()

    monkeypatch.setattr(polisher_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(polisher_module.threading, "Thread", DelayedThread)

    assert engine._run_bridge_with_timeout(
        lambda provider_timeout: seen.append(provider_timeout) or "complete text",
        timeout=0.3,
        deadline=105.0,
    ) == "complete text"
    assert seen == [pytest.approx(0.2)]


def test_settings_read_failure_fails_closed_for_remote_polishing(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = TextPolisher()
    calls: list[object] = []
    monkeypatch.setattr(polisher_module.storage, "get_setting", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("settings unavailable")))
    monkeypatch.setattr(engine, "_polish_with_api_pool", lambda *_args, **_kwargs: calls.append(True) or "remote")
    monkeypatch.setattr(polisher_module.dictionary_engine, "apply_dictionary_post_processing", lambda text: text)

    result = engine.polish("um keep this local while settings are unavailable", force_ai=True)

    assert not calls
    assert "keep this local" in result.lower()


@pytest.mark.parametrize("timeout_error", [TimeoutError(), socket.timeout()])
def test_provider_timeout_errors_are_classified(timeout_error, monkeypatch: pytest.MonkeyPatch) -> None:
    """Timeout exceptions must enter the short timeout cooldown path."""
    engine = TextPolisher()

    def fail_urlopen(*_args, **_kwargs):
        raise timeout_error

    monkeypatch.setattr(polisher_module.urllib.request, "urlopen", fail_urlopen)

    assert engine._try_provider_call("gemini", "fake-key", "system", "user") is None
    assert engine._last_attempt_status == "timeout"


class _UnavailableLexiconStore:
    def _unavailable(self, *_args, **_kwargs):
        raise OSError("dictionary database unavailable")

    get_dictionary_revision = _unavailable
    get_dictionary_entries = _unavailable
    get_dictionary_snapshot = _unavailable
    get_dictionary_words = _unavailable
    get_dictionary_corrections = _unavailable
    get_snippets = _unavailable


def test_dictionary_engine_preserves_content_when_storage_is_unavailable() -> None:
    engine = DictionaryEngine(_UnavailableLexiconStore())

    source = "Please preserve this transcript when the dictionary database is unavailable."
    assert engine.apply_dictionary_post_processing(source) == source
    assert engine.get_initial_prompt().startswith("Clear dictation")


def test_style_resolution_uses_default_when_storage_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("voice_flow.style_engine.get_active_app_info", lambda: ("General App", "general.exe"))
    monkeypatch.setattr(
        polisher_module.storage,
        "get_setting",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("settings database unavailable")),
    )

    resolved = StyleEngine().resolve(hwnd=None)

    assert resolved.category == "other"
    assert resolved.style_id == "other_formal"
    assert resolved.instruction

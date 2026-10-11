"""Deterministic residency checks; no real models, services, or wall-clock sleeps."""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from voice_flow import lfm_engine, local_model_resources as resources


@pytest.fixture(autouse=True)
def isolated_resources(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(resources, "_callbacks", {})
    monkeypatch.setattr(resources, "_active_uses", {"speech": 0, "polish": 0})
    monkeypatch.setattr(resources, "_cleanup_requested", set())
    monkeypatch.setattr(resources, "_cleanup_not_before", {})
    monkeypatch.setattr(resources, "_immediate_cleanup_requested", set())
    monkeypatch.setattr(resources, "_kind_gates", {"speech": threading.Lock(), "polish": threading.Lock()})
    monkeypatch.setattr(resources, "_lock", threading.Lock())
    monkeypatch.setattr(resources, "_wake", threading.Event())
    monkeypatch.setattr(resources, "_worker", None)
    monkeypatch.setattr(resources, "_cleanup_context", threading.local())
    monkeypatch.setattr(resources, "_idle_clock", lambda: clock[0])
    monkeypatch.setattr(resources, "_ensure_worker", lambda: None)
    monkeypatch.setattr(lfm_engine, "_LLM_LOCK", threading.Lock())
    return clock


def resident_lfm(monkeypatch):
    closed = []
    model = SimpleNamespace(close=lambda: closed.append(True))
    for name, value in (("_cached_llm", model), ("_cached_llm_path", "mock.gguf"), ("_last_used", 100.0)):
        monkeypatch.setattr(lfm_engine.polish_with_lfm, name, value, raising=False)
    resources.register_idle_cleanup("mock-lfm", lfm_engine._release_idle_lfm, kind="polish")
    return model, closed


def test_nearby_dictations_reuse_lfm_until_exact_idle_grace(monkeypatch, isolated_resources):
    model, closed = resident_lfm(monkeypatch)
    monkeypatch.setattr(lfm_engine, "_polish_with_lfm_impl", lambda *_args, **_kwargs: "polished")
    assert lfm_engine.polish_with_lfm("first") == "polished"
    isolated_resources[0] = 109.0
    resources.cleanup_idle_models()
    assert closed == []
    assert lfm_engine.polish_with_lfm._cached_llm is model
    assert lfm_engine.polish_with_lfm("second") == "polished"
    isolated_resources[0] = 118.999
    resources.cleanup_idle_models()
    assert closed == []
    isolated_resources[0] = 119.0
    resources.cleanup_idle_models()
    assert closed == [True]
    assert lfm_engine.polish_with_lfm._cached_llm is None
    assert lfm_engine.polish_with_lfm._cached_llm_path is None


def test_explicit_cleanup_during_active_lease_overrides_later_grace(monkeypatch):
    _, closed = resident_lfm(monkeypatch)
    lease = resources.acquire_model_use("polish")
    resources.request_model_cleanup("polish")
    resources.cleanup_idle_models()
    assert closed == []
    lease.release_after_idle(10)
    resources.cleanup_idle_models()
    assert closed == [True]


def test_explicit_cleanup_survives_new_overlapping_lease(monkeypatch):
    _, closed = resident_lfm(monkeypatch)
    first = resources.acquire_model_use("polish")
    resources.request_model_cleanup("polish")
    second = resources.acquire_model_use("polish")
    first.release_after_idle(10)
    resources.cleanup_idle_models()
    assert closed == []
    second.release_after_idle(10)
    resources.cleanup_idle_models()
    assert closed == [True]


def test_overlapping_leases_never_unload_active_model(monkeypatch, isolated_resources):
    _, closed = resident_lfm(monkeypatch)
    first = resources.acquire_model_use("polish")
    second = resources.acquire_model_use("polish")
    first.release_after_idle(10)
    isolated_resources[0] = 1_000.0
    resources.cleanup_idle_models()
    assert closed == []
    assert resources.has_active_model_use("polish")
    second.release_after_idle(10)
    isolated_resources[0] = 1_010.0
    resources.cleanup_idle_models()
    assert closed == [True]


def test_ordinary_speech_release_cleans_up_without_idle_grace():
    calls = []
    resources.register_idle_cleanup("mock-speech", lambda now: calls.append(now) or True, kind="speech")
    lease = resources.acquire_model_use("speech")
    lease.release()
    resources.cleanup_idle_models()
    assert calls == [100.0]
    assert not resources.cleanup_requested("speech")


def test_notifications_duplicate_release_and_busy_retry_do_not_extend_grace(monkeypatch, isolated_resources):
    _, closed = resident_lfm(monkeypatch)
    lease = resources.acquire_model_use("polish")
    lease.release_after_idle(10)
    for timestamp in (101.0, 105.0, 109.999):
        isolated_resources[0] = timestamp
        lease.release_after_idle(10)
        resources.notify_models_available("polish")
        resources.cleanup_idle_models()
        assert resources._cleanup_not_before["polish"] == 110.0
        assert closed == []
    isolated_resources[0] = 110.0
    with lfm_engine._LLM_LOCK:
        resources.cleanup_idle_models()
    assert resources.cleanup_requested("polish")
    assert resources._cleanup_not_before["polish"] == 110.0
    resources.notify_models_available("polish")
    resources.cleanup_idle_models()
    assert closed == [True]


def test_failed_polish_still_releases_lease_after_bounded_grace(monkeypatch, isolated_resources):
    _, closed = resident_lfm(monkeypatch)
    def fail(*_args, **_kwargs):
        raise RuntimeError("mock inference failed")
    monkeypatch.setattr(lfm_engine, "_polish_with_lfm_impl", fail)
    with pytest.raises(RuntimeError, match="mock inference failed"):
        lfm_engine.polish_with_lfm("hello")
    assert not resources.has_active_model_use("polish")
    isolated_resources[0] = 110.0
    resources.cleanup_idle_models()
    assert closed == [True]

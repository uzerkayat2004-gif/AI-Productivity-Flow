"""OFF Nemotron speech-model burst reuse without weakening forced cleanup."""
from types import SimpleNamespace

import pytest

from voice_flow import local_model_resources as resources
from voice_flow import main as main_module
from voice_flow import downloadable_models
from voice_flow import nemotron_engine
from voice_flow.main import VoiceFlowApp


class FakeClock:
    now = 1000.0

    def __call__(self):
        return self.now


class CachedEngine:
    def __init__(self):
        self.is_warm = True
        self.close_count = 0

    def touch(self):
        pass

    def release_if_idle(self, _now, *, force=False):
        if force:
            self.close()
            return True
        return False

    def close(self):
        self.close_count += 1
        self.is_warm = False


@pytest.fixture
def fake_speech_cache(monkeypatch, tmp_path):
    clock = FakeClock()
    cache = {}
    constructed = []
    monkeypatch.setattr(nemotron_engine, "_NEMOTRON_CACHE", cache)
    monkeypatch.setattr(resources, "_callbacks", {})
    monkeypatch.setattr(resources, "_active_uses", {"speech": 0, "polish": 0})
    monkeypatch.setattr(resources, "_cleanup_requested", set())
    monkeypatch.setattr(resources, "_cleanup_not_before", {})
    monkeypatch.setattr(resources, "_immediate_cleanup_requested", set())
    monkeypatch.setattr(resources, "_idle_clock", clock)
    monkeypatch.setattr(resources, "_ensure_worker", lambda: None)
    model_file = tmp_path / "nemotron.gguf"
    model_file.write_bytes(b"offline fake model")
    model_ref = str(model_file)
    monkeypatch.setattr(downloadable_models, "get_model_spec", lambda _model_ref: None)

    def construct_engine(_path, *, spec=None):
        engine = CachedEngine()
        constructed.append(engine)
        return engine

    monkeypatch.setattr(nemotron_engine, "NemotronGGUFEngine", construct_engine)
    return SimpleNamespace(
        clock=clock,
        cache=cache,
        constructed=constructed,
        model_ref=model_ref,
        get=lambda _model_ref: nemotron_engine.get_nemotron_engine(model_ref),
    )


def install_settings(monkeypatch, *, polishing_enabled=False):
    monkeypatch.setattr(
        main_module.storage,
        "get_setting",
        lambda key, default=None: polishing_enabled if key == "polishing_enabled" else default,
    )


def session_for(lease, model_ref="local/nvidia/nemotron-speech-streaming-en-0.6b"):
    return SimpleNamespace(model_resource_lease=lease, stt_model_ref=model_ref)


def test_off_nemotron_reuses_cache_inside_burst_and_evicts_after_idle_window(monkeypatch, fake_speech_cache):
    install_settings(monkeypatch, polishing_enabled=False)
    first_engine = fake_speech_cache.get(fake_speech_cache.model_ref)
    lease = resources.acquire_model_use("speech")
    session = session_for(lease)

    VoiceFlowApp._release_session_model_resource(session)

    assert session.model_resource_lease is None
    assert resources._cleanup_not_before["speech"] == pytest.approx(1000.0 + main_module.NEMOTRON_OFF_BURST_IDLE_GRACE_SECONDS)
    fake_speech_cache.clock.now = 1005.0
    resources.cleanup_idle_models()
    second_engine = fake_speech_cache.get(fake_speech_cache.model_ref)
    assert second_engine is first_engine
    assert len(fake_speech_cache.constructed) == 1
    assert first_engine.close_count == 0

    fake_speech_cache.clock.now = 1000.0 + main_module.NEMOTRON_OFF_BURST_IDLE_GRACE_SECONDS + 1.0
    resources.cleanup_idle_models()
    assert first_engine.close_count == 1
    assert fake_speech_cache.cache == {}
    assert fake_speech_cache.get(fake_speech_cache.model_ref) is not first_engine
    assert len(fake_speech_cache.constructed) == 2


def test_forced_cleanup_overrides_nemotron_burst_grace(monkeypatch, fake_speech_cache):
    install_settings(monkeypatch, polishing_enabled=False)
    engine = fake_speech_cache.get(fake_speech_cache.model_ref)
    session = session_for(resources.acquire_model_use("speech"))

    VoiceFlowApp._release_session_model_resource(session)
    fake_speech_cache.clock.now = 1001.0
    resources.request_model_cleanup("speech")
    resources.cleanup_idle_models()

    assert engine.close_count == 1
    assert fake_speech_cache.cache == {}
    assert "speech" not in resources._cleanup_requested


@pytest.mark.parametrize("model_ref,immediate", [("local/whisper-small.en", False), ("deepgram/nova-3", True)])
def test_non_nemotron_speech_leases_still_release_immediately(monkeypatch, fake_speech_cache, model_ref, immediate):
    install_settings(monkeypatch, polishing_enabled=False)
    session = session_for(resources.acquire_model_use("speech"), model_ref)

    VoiceFlowApp._release_session_model_resource(session)

    assert session.model_resource_lease is None
    if immediate:
        assert resources._cleanup_not_before.get("speech", 0.0) == 0.0
    else:
        assert resources._cleanup_not_before["speech"] > 0


def test_polishing_on_keeps_immediate_speech_release_before_polish(monkeypatch, fake_speech_cache):
    install_settings(monkeypatch, polishing_enabled=True)
    session = session_for(resources.acquire_model_use("speech"))

    VoiceFlowApp._release_session_model_resource(session)

    assert session.model_resource_lease is None
    assert resources._cleanup_not_before["speech"] == 0.0

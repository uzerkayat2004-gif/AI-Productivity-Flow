"""Dictionary vocabulary should reach real STT hint arguments conservatively."""

from __future__ import annotations

from types import SimpleNamespace
import threading

import numpy as np
import pytest

from voice_flow.dictionary import DictionaryEngine
from voice_flow.storage import StorageEngine
import voice_flow.transcriber as transcriber_module


@pytest.mark.parametrize("enabled", [False, True])
def test_saved_heard_as_is_applied_with_polishing_off_or_on(tmp_path, monkeypatch, enabled):
    from voice_flow import polisher as polisher_module

    store = StorageEngine(str(tmp_path / "polishing-parity.db"))
    store.save_setting("polishing_enabled", enabled)
    assert store.add_dictionary_entry("HyperKube", "hyper cube")
    engine = DictionaryEngine(store)
    monkeypatch.setattr(polisher_module, "storage", store)
    monkeypatch.setattr(polisher_module, "dictionary_engine", engine)
    polisher = polisher_module.TextPolisher()
    calls = []
    raw = "Please review hyper cube before we deploy the new service to our customers tomorrow."

    def mocked_provider(text, *_args, **kwargs):
        calls.append(text)
        return text

    monkeypatch.setattr(polisher, "_polish_with_api_pool", mocked_provider)
    outcomes = []
    result = polisher.polish(raw, model_ref="test/provider", outcome_callback=outcomes.append)

    assert "HyperKube" in result
    assert "hyper cube" not in result.casefold()
    assert result.endswith("tomorrow.")
    assert bool(calls) is enabled
    assert outcomes == ["ai_accepted" if enabled else "disabled"]


def test_hints_use_local_store_and_only_canonical_terms_and_correction_targets(tmp_path, monkeypatch):
    store = StorageEngine(str(tmp_path / "local.db"))
    global_store = StorageEngine(str(tmp_path / "global.db"))
    store.add_dictionary_word("AI", category="Work")
    store.add_dictionary_word("UI", category="Work")
    store.add_dictionary_word("HyperKube", category="Work")
    store.add_dictionary_word("ClientPortal", category="Personal")
    store.add_snippet("sig", "signature block")
    store.add_dictionary_correction("cuber netties", "Kubernetes")

    # A decoy global singleton ensures category lookup follows the engine's
    # backing store rather than whichever StorageEngine was imported first.
    global_store.add_dictionary_word("WrongCategory", category="Work")
    monkeypatch.setattr("voice_flow.dictionary.storage", global_store)
    engine = DictionaryEngine(store)

    prompt = engine.get_initial_prompt("Work")
    hints = engine.get_stt_hint_terms("Work")

    for term in ("AI", "UI", "HyperKube", "ClientPortal", "Kubernetes"):
        assert term in prompt
        assert term in hints
    for excluded in ("WrongCategory", "sig", "signature block", "Hyper Kube", "Open AI", "cuber netties"):
        assert excluded not in prompt
        assert excluded not in hints


def test_contextual_terms_keep_priority_when_context_has_fewer_than_twelve(tmp_path):
    store = StorageEngine(str(tmp_path / "local.db"))
    store.add_dictionary_word("CategoryAnchor", category="Work")
    for index in range(24):
        store.add_dictionary_word(f"GlobalTechnicalTerm{index:02d}")

    engine = DictionaryEngine(store)
    hints = engine.get_stt_hint_terms("Work", limit=4)

    assert hints[0] == "CategoryAnchor"
    assert len(hints) == 4


def test_long_correction_target_cannot_consume_the_hint_budget(tmp_path):
    store = StorageEngine(str(tmp_path / "local.db"))
    store.add_dictionary_word("Kubernetes")
    store.add_dictionary_word("OpenAI")
    store.add_dictionary_correction("heard the long phrase", "X" * 180)

    engine = DictionaryEngine(store)
    prompt = engine.get_initial_prompt()
    hints = engine.get_stt_hint_terms()

    assert len(prompt) <= 520
    assert "Kubernetes" in prompt and "OpenAI" in prompt
    assert "Kubernetes" in hints and "OpenAI" in hints
    assert "X" * 180 not in prompt
    assert all(len(term) <= 96 for term in hints)


def test_legacy_ordinary_words_do_not_crowd_out_recognition_hints(tmp_path):
    store = StorageEngine(str(tmp_path / "legacy-noise.db"))
    for term in ("Hey", "Last", "Under", "Perfect", "Feature", "Type"):
        store.add_dictionary_word(term)
    store.add_dictionary_word("Kubernetes")
    engine = DictionaryEngine(store)
    assert engine.get_stt_hint_terms() == ["Kubernetes"]
    assert len(store.get_dictionary_words()) == 7  # existing terms are retained


def test_correction_targets_precede_excess_global_terms(tmp_path):
    store = StorageEngine(str(tmp_path / "local.db"))
    for index in range(18):
        store.add_dictionary_word(f"TechnicalProductName{index:02d}")
    store.add_dictionary_correction("joe ee", "Joey")

    hints = DictionaryEngine(store).get_stt_hint_terms(limit=15)

    assert "Joey" in hints
    assert "joe ee" not in hints


def test_local_whisper_uses_no_prompt_and_leaves_correction_for_finalization(tmp_path, monkeypatch):
    store = StorageEngine(str(tmp_path / "local.db"))
    store.add_dictionary_word("OpenAI")
    store.add_dictionary_correction("oh pen eye", "OpenAI")
    engine = DictionaryEngine(store)
    monkeypatch.setattr(transcriber_module, "dictionary_engine", engine, raising=False)
    monkeypatch.setattr(transcriber_module.nemotron_engine, "is_nemotron_model", lambda _ref: False)

    class FakeModel:
        kwargs = None

        def transcribe(self, _audio, **kwargs):
            self.kwargs = kwargs
            return [SimpleNamespace(text="oh pen eye works")], None

    transcriber = object.__new__(transcriber_module.Transcriber)
    transcriber.model = FakeModel()
    transcriber.category_hint = None
    transcriber._lock = threading.Lock()
    transcriber._transcribe_lock = threading.Lock()
    transcriber._wait_for_model = lambda *_args, **_kwargs: True

    audio = np.full(3200, 0.2, dtype=np.float32)
    text = transcriber._transcribe_local(audio, model_ref="base.en")

    assert transcriber.model.kwargs["initial_prompt"] is None
    assert text == "oh pen eye works"


def test_cloud_provider_dispatch_uses_no_dictionary_vocabulary(tmp_path, monkeypatch):
    store = StorageEngine(str(tmp_path / "local.db"))
    store.add_dictionary_word("OpenAI")
    store.add_snippet("sig", "signature block")
    store.add_dictionary_correction("oh pen eye", "OpenAI")
    engine = DictionaryEngine(store)
    monkeypatch.setattr(transcriber_module, "dictionary_engine", engine, raising=False)
    monkeypatch.setattr(transcriber_module, "enhance_for_stt", lambda audio, *_args, **_kwargs: (audio, "off"))
    seen = {}

    def fake_cloud(_audio, _model_ref, **kwargs):
        seen.update(kwargs)
        vocabulary = kwargs.get("vocabulary") or []
        return ("OpenAI " if "OpenAI" in vocabulary else "") + "decoded from audio"

    monkeypatch.setattr(transcriber_module.stt_engines, "transcribe_cloud", fake_cloud)
    transcriber = object.__new__(transcriber_module.Transcriber)
    transcriber.category_hint = None
    transcriber._cloud_stt_breakers = {}

    text = transcriber._transcribe_impl(
        np.full(3200, 0.2, dtype=np.float32),
        model_ref="groq/whisper-large-v3-turbo",
    )

    assert text == "decoded from audio"
    assert seen.get("vocabulary") == []


@pytest.mark.parametrize(
    "model_ref,constructor_path",
    [
        ("deepgram/flux-general-en", "voice_flow.flux_stream.FluxStreamTranscriber"),
        ("deepgram/nova-3", "voice_flow.flux_stream.NovaStreamTranscriber"),
        ("local/nemotron-speech-streaming-en-0.6b", "voice_flow.nemotron_engine.NemotronStreamTranscriber"),
    ],
)
def test_native_stream_startup_receives_no_global_dictionary_vocabulary(
    tmp_path, monkeypatch, model_ref, constructor_path,
):
    from voice_flow import main as main_module
    from voice_flow import stt_engines

    store = StorageEngine(str(tmp_path / "stream.db"))
    store.add_dictionary_word("HyperKube")
    engine = DictionaryEngine(store)
    monkeypatch.setattr(main_module, "dictionary_engine", engine)
    monkeypatch.setattr(
        engine,
        "get_stt_hint_terms",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("ordinary stream startup must not read recognition hints")
        ),
    )
    monkeypatch.setattr(stt_engines, "prewarm_cloud_stt", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "voice_flow.nemotron_engine.is_nemotron_model",
        lambda selected: str(selected or "").lower().startswith("local/nemotron"),
    )
    constructed = []

    class NeutralStream:
        def __init__(self, *args, **kwargs):
            constructed.append((args, kwargs))

        def submit_frame(self, *_args, **_kwargs):
            return None

        def start_session(self, **kwargs):
            self.started = kwargs

    monkeypatch.setattr(constructor_path, NeutralStream)
    app = object.__new__(main_module.VoiceFlowApp)
    app.audio = SimpleNamespace(on_audio_frame=None, split_silence_seconds=0.0, max_chunk_seconds=0.0)
    app._streaming_stt_enabled = lambda: True
    app._stream_stt = SimpleNamespace()
    session = SimpleNamespace(stt_model_ref=model_ref, app_category="Work")

    app._start_stream_for_session(session)

    assert constructed == [((), {})]
    assert app._stream_stt.started == {"model_ref": model_ref}

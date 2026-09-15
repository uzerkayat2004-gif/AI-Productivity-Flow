from __future__ import annotations

import os
import sys

import pytest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.dictionary import DictionaryEngine


class _DictionarySource:
    def __init__(self, words: list[str]) -> None:
        self.words = words
        self.revision = 1

    def entries(self, include_auto: bool = True) -> list[dict[str, str]]:
        return [{"word": word, "category": "Personal"} for word in self.words]


def _engine(monkeypatch: pytest.MonkeyPatch, words: list[str]) -> DictionaryEngine:
    source = _DictionarySource(words)
    monkeypatch.setattr("voice_flow.dictionary.storage.get_dictionary_entries", source.entries)
    monkeypatch.setattr("voice_flow.dictionary.storage.get_dictionary_revision", lambda: source.revision)
    # Hermetic: also isolate corrections/snapshot so live learned data
    # (e.g. "voiceflow -> Voice Flow" corrections from real dictation)
    # cannot leak into these fixtures.
    monkeypatch.setattr(
        "voice_flow.dictionary.storage.get_dictionary_snapshot",
        lambda: (source.revision, list(words), []),
    )
    monkeypatch.setattr(
        "voice_flow.dictionary.storage.get_dictionary_corrections",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        "voice_flow.dictionary.storage.get_snippets",
        lambda *a, **k: [],
    )
    return DictionaryEngine()


def test_exact_terms_are_boundary_safe_and_do_not_fuzzy_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch, ["TING", "API", "form"])

    text = "I think this app came from a platform called catapult."

    assert engine.apply_dictionary_post_processing(text) == text


def test_explicit_term_preserves_casing_only_for_exact_match(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch, ["VoiceFlow"])

    assert engine.apply_dictionary_post_processing("voiceflow is ready") == "VoiceFlow is ready"
    assert engine.apply_dictionary_post_processing("voiceflows is ready") == "voiceflows is ready"


def test_snippet_uses_trigger_length_and_does_not_cascade(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch, [
        "a -> this is a long expansion",
        "a b -> PHRASE",
        "foo -> bar",
        "bar -> baz",
    ])

    assert engine.apply_dictionary_post_processing("a b") == "PHRASE"
    assert engine.apply_dictionary_post_processing("foo") == "bar"


def test_snippet_expansion_inserts_backslashes_literally(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch, [r"my path -> C:\Users\me\file.txt"])

    assert engine.apply_dictionary_post_processing("open my path") == r"open C:\Users\me\file.txt"


def test_empty_snippet_expansion_cannot_delete_text(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch, ["foo ->"])

    assert engine.apply_dictionary_post_processing("foo") == "foo"


def test_dictionary_processing_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(monkeypatch, ["myemail -> me@example.com", "VoiceFlow"])

    once = engine.apply_dictionary_post_processing("voiceflow myemail")
    assert engine.apply_dictionary_post_processing(once) == once


def test_dictionary_refreshes_when_storage_revision_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _DictionarySource(["VoiceFlow"])
    monkeypatch.setattr("voice_flow.dictionary.storage.get_dictionary_entries", source.entries)
    monkeypatch.setattr("voice_flow.dictionary.storage.get_dictionary_revision", lambda: source.revision)
    # Hermetic: isolate corrections snapshot too (live learned data must not leak).
    monkeypatch.setattr(
        "voice_flow.dictionary.storage.get_dictionary_snapshot",
        lambda: (source.revision, list(source.words), []),
    )
    monkeypatch.setattr(
        "voice_flow.dictionary.storage.get_dictionary_corrections",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        "voice_flow.dictionary.storage.get_snippets",
        lambda *a, **k: [],
    )
    engine = DictionaryEngine()

    assert engine.apply_dictionary_post_processing("voiceflow") == "VoiceFlow"
    source.words.append("NewTerm")
    source.revision += 1
    assert engine.apply_dictionary_post_processing("newterm") == "NewTerm"


def test_filler_noise_never_reaches_stt_prompt_or_hints(monkeypatch: pytest.MonkeyPatch) -> None:
    """Greeting/filler/deictic terms carry no vocabulary value and make STT
    overproduce them; they must be excluded from bias prompts and hints."""
    engine = _engine(
        monkeypatch,
        ["Hey", "hello", "here", "there", "uh", "um", "Kubernetes", "Ada Lovelace"],
    )

    prompt = engine.get_initial_prompt()
    prompt_tokens = {token.strip(".,:;!?").casefold() for token in prompt.split()}
    for noise in ("hey", "hello", "here", "there", "uh", "um"):
        assert noise not in prompt_tokens, f"noise term {noise!r} leaked into STT prompt: {prompt!r}"
    assert "Kubernetes" in prompt and "Ada Lovelace" in prompt

    hints = engine.get_stt_hint_terms(None)
    hint_keys = {hint.casefold() for hint in hints}
    assert not ({"hey", "hello", "here", "there", "uh", "um"} & hint_keys)
    assert "kubernetes" in hint_keys


def test_correction_extraction_rejects_filler_and_greeting_noise() -> None:
    """'uh hey' heard 18x for 'Hey' must never become a suggestion candidate."""
    from voice_flow.correction_learning import extract_correction_pairs

    assert extract_correction_pairs("uh hey lets go", "Hey lets go") == []
    assert extract_correction_pairs("uh hey are you there", "Hey are you there") == []
    assert extract_correction_pairs("hear is the plan", "Here is the plan") == []


def test_correction_extraction_still_catches_real_names_after_case_shift() -> None:
    """Sentence-initial capitalization must not hide multi-token mishearings."""
    from voice_flow.correction_learning import extract_correction_pairs

    assert ("Joey", "joe ee") in extract_correction_pairs("call joe ee now", "Call Joey now")
    assert ("LangGraph", "land graph") in extract_correction_pairs(
        "we will use land graph for routing", "We will use LangGraph for routing"
    )


def test_correction_extraction_requires_distinct_context_for_multitoken_variants() -> None:
    """Duplicated filler ('hey hey') is one content token, not evidence."""
    from voice_flow.correction_learning import extract_correction_pairs

    pairs = extract_correction_pairs("we discussed hey hey yesterday", "We discussed HeyHey yesterday")
    assert all(variant.casefold() != "hey hey" for _, variant in pairs)


def test_trigger_post_processing_applies_inside_local_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: explicit trigger->replacement rules must run on the local
    STT return path (faster-whisper), not only inside the polisher."""
    import threading

    import numpy as np

    from voice_flow.transcriber import Transcriber

    engine = _engine(monkeypatch, ["myname -> MyName"])
    monkeypatch.setattr(
        "voice_flow.transcriber.dictionary_engine.apply_dictionary_post_processing",
        engine.apply_dictionary_post_processing,
    )
    monkeypatch.setattr(
        "voice_flow.transcriber.dictionary_engine.get_initial_prompt",
        lambda *args, **kwargs: "",
    )
    monkeypatch.setattr("voice_flow.transcriber.config.sample_rate", 16000)

    class _Segment:
        text = "call myname now"

    class _FakeModel:
        def transcribe(self, data, **kwargs):
            return iter([_Segment()]), None

    transcriber = object.__new__(Transcriber)
    transcriber.model = _FakeModel()
    transcriber._transcribe_lock = threading.Lock()
    monkeypatch.setattr(Transcriber, "_wait_for_model", lambda self, *a, **k: True)
    monkeypatch.setattr("voice_flow.transcriber.nemotron_engine.is_nemotron_model", lambda *a: False)

    audio = np.ones(32000, dtype=np.float32) * 0.5
    assert transcriber._transcribe_local(audio) == "call MyName now"


def test_nemotron_path_receives_vocabulary_and_post_processing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: Nemotron decode gets dictionary hint terms and its raw
    output still runs trigger->replacement post-processing."""
    import threading

    import numpy as np

    from voice_flow.transcriber import Transcriber

    engine = _engine(monkeypatch, ["MyName", "Kubernetes"])
    monkeypatch.setattr(
        "voice_flow.transcriber.dictionary_engine.apply_dictionary_post_processing",
        engine.apply_dictionary_post_processing,
    )
    monkeypatch.setattr(
        "voice_flow.transcriber.dictionary_engine.get_stt_hint_terms",
        lambda category=None, limit=15: ["MyName", "Kubernetes"],
    )
    monkeypatch.setattr("voice_flow.transcriber.config.sample_rate", 16000)

    seen: dict = {}

    class _FakeNemotron:
        is_warm = True

        def transcribe(self, audio, **kwargs):
            seen.update(kwargs)
            return "call myname now"

    fake_engine = _FakeNemotron()
    monkeypatch.setattr("voice_flow.transcriber.nemotron_engine.is_nemotron_model", lambda *a: True)
    monkeypatch.setattr(
        "voice_flow.transcriber.nemotron_engine.get_nemotron_engine", lambda *a, **k: fake_engine
    )

    transcriber = object.__new__(Transcriber)
    transcriber.model = None
    transcriber.nemotron_engine = fake_engine
    transcriber._transcribe_lock = threading.Lock()
    monkeypatch.setattr(Transcriber, "_wait_for_model", lambda self, *a, **k: True)

    audio = np.ones(32000, dtype=np.float32) * 0.5
    assert transcriber._transcribe_local(audio, model_ref="nemotron-test") == "call MyName now"
    assert seen.get("vocabulary") == ["MyName", "Kubernetes"]

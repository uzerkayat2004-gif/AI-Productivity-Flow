from __future__ import annotations

import sys
import threading
import types

import pytest

from voice_flow import s1_engine


class FakeLlama:
    def __init__(self, response=None):
        self.response = response or {
            "choices": [{"text": "cleaned text", "finish_reason": "stop"}]
        }
        self.kwargs = None
        self.called = False

    def tokenize(self, data: bytes) -> list[int]:
        return data.decode("utf-8").split()

    def __call__(self, prompt: str, **kwargs):
        self.called = True
        self.kwargs = kwargs
        return self.response


def test_rejects_result_returned_after_deadline(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(s1_engine.time, "monotonic", lambda: now[0])

    class SlowFakeLlama(FakeLlama):
        def __call__(self, prompt: str, **kwargs):
            now[0] = 2.0
            return {"choices": [{"text": "cleaned text", "finish_reason": "stop"}]}

    assert s1_engine._polish_chunk_with_s1(SlowFakeLlama(), "hello", "[Styling: semi-formal]", 1.0) is None


def test_uses_transcript_token_count_and_limits_to_context(monkeypatch):
    llm = FakeLlama()
    monkeypatch.setattr(s1_engine.time, "monotonic", lambda: 0.0)

    result = s1_engine._polish_chunk_with_s1(llm, "one two three", "[Styling: formal]", 10.0)

    assert result == "cleaned text"
    assert llm.kwargs["max_tokens"] == 51
    assert llm.kwargs["temperature"] == 0.0
    assert llm.kwargs["top_k"] == 1
    assert llm.kwargs["repeat_penalty"] == 1.0
    assert llm.kwargs["stop"] == ["<|im_end|>"]


@pytest.mark.parametrize("finish_reason", ["length", "max_tokens"])
def test_rejects_truncated_generation(finish_reason, monkeypatch):
    monkeypatch.setattr(s1_engine.time, "monotonic", lambda: 0.0)
    llm = FakeLlama({"choices": [{"text": "incomplete", "finish_reason": finish_reason}]})

    assert s1_engine._polish_chunk_with_s1(llm, "hello", "control", 10.0) is None


def test_native_stopping_criteria_stops_at_deadline(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(s1_engine.time, "monotonic", lambda: now[0])

    class StoppableFakeLlama(FakeLlama):
        def __call__(self, prompt: str, **kwargs):
            criteria = kwargs.get("stopping_criteria")
            assert criteria is not None
            now[0] = 2.0
            assert criteria([], None)
            return {"choices": [{"text": "partial", "finish_reason": "stop"}]}

    assert s1_engine._polish_chunk_with_s1(StoppableFakeLlama(), "hello", "control", 1.0) is None


def test_rejects_prompt_larger_than_context(monkeypatch):
    monkeypatch.setattr(s1_engine.time, "monotonic", lambda: 0.0)
    llm = FakeLlama()

    assert s1_engine._polish_chunk_with_s1(llm, "hello", "word " * 4100, 10.0) is None
    assert not llm.called


def test_splits_single_oversized_sentence_without_losing_words():
    source = " ".join(f"word{i}" for i in range(401))

    chunks = s1_engine._chunk_transcript(source, max_chunk_words=150)

    assert [len(chunk.split()) for chunk in chunks] == [150, 150, 101]
    assert " ".join(chunks) == source


def test_any_failed_chunk_rejects_whole_result(monkeypatch, tmp_path):
    llm = FakeLlama()
    calls = []

    monkeypatch.setattr(s1_engine, "get_s1_model_path", lambda: tmp_path / "model.gguf")
    monkeypatch.setattr(s1_engine, "s1_can_handle", lambda **kwargs: True)
    monkeypatch.setattr(s1_engine, "_LLM_LOCK", threading.Lock())
    monkeypatch.setattr(s1_engine, "_chunk_transcript", lambda text, max_chunk_words: ["first", "second"])
    monkeypatch.setattr(s1_engine, "_polish_chunk_with_s1", lambda _llm, chunk, *_, **__: calls.append(chunk) or ("first clean" if chunk == "first" else None))
    monkeypatch.setattr(s1_engine.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(s1_engine.polish_with_s1, "_cached_llm", llm, raising=False)
    monkeypatch.setattr(s1_engine.polish_with_s1, "_cached_llm_path", str(tmp_path / "model.gguf"), raising=False)
    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=FakeLlama))

    assert s1_engine._polish_with_s1_impl(" ".join(["word"] * 701), timeout_seconds=10.0) is None
    assert calls == ["first", "second"]


@pytest.mark.parametrize(
    "metadata",
    [
        {"task": "summarize"},
        {"task": "summary"},
        {"instruction": "Summarize this article"},
        {"command_format": "linkedin_post"},
        {"command_format": "LinkedIn Post"},
    ],
)
def test_rejects_non_normalization_metadata(metadata):
    assert not s1_engine.s1_can_handle(text="Some spoken text", **metadata)


def test_allows_standard_cleanup_instruction_with_style_id():
    assert s1_engine.s1_can_handle(
        text="Some spoken text",
        instruction="Clean up grammar and punctuation while preserving meaning.",
        style_id="casual",
    )
    assert s1_engine.s1_can_handle(
        text="Some spoken text",
        instruction="Do not summarize or generate a prompt; just clean the transcript.",
        style_id="casual",
    )


def test_mock_runner_obeys_task_eligibility(monkeypatch, tmp_path):
    monkeypatch.setattr(s1_engine, "get_s1_model_path", lambda: tmp_path / "model.gguf")
    monkeypatch.setattr(s1_engine.polish_with_s1, "_mock_runner", lambda text, instruction: "should not run", raising=False)

    assert s1_engine._polish_with_s1_impl("Transcript", task="summarize") is None


def test_command_metadata_is_checked_without_command_object():
    assert not s1_engine.s1_can_handle(text="Transcript", command_format="linkedin_post")
    assert not s1_engine.s1_can_handle(text="Transcript", overrides={"operation": "prompt_generation"})


@pytest.mark.parametrize(
    ("source", "candidate"),
    [
        ("Meet me Friday, no wait, Thursday.", "Meet me Thursday."),
        ("Meet me Friday, sorry, Thursday.", "Meet me Thursday."),
        ("There are twenty five seats.", "There are 25 seats."),
        ("It costs ten or twenty dollars.", "It costs $10 or $20."),
    ],
)
def test_canonical_fidelity_accepts_known_s1_normalizations(source, candidate):
    assert s1_engine.normalization_preserves_content(source, candidate)


@pytest.mark.parametrize(
    ("source", "candidate"),
    [
        ("Meet me Friday, no wait, Thursday.", "Meet me Monday."),
        # Phase 1.1 (VF-1): "Friday, sorry, Thursday" is a spoken self-correction
        # and "Meet me Thursday." is now accepted (see the accept list above and
        # tests/test_vf1_regressions.py). The rejected variant keeps the wrong day.
        ("Meet me Friday, sorry, Thursday.", "Meet me Friday."),
        ("There are twenty five seats.", "There are 25 tables."),
        ("It costs ten or twenty dollars.", "It costs $20."),
        ("Open https://example.com/file/123", "Open https://example.com/file/124"),
        ('Say "Friday, no wait, Thursday" aloud.', "Say Thursday aloud."),
    ],
)
def test_canonical_fidelity_rejects_other_content_changes(source, candidate):
    assert not s1_engine.normalization_preserves_content(source, candidate)


def test_canonical_number_parser_does_not_change_word_fragments():
    source = "Someone carved a stone for anyone."
    assert s1_engine._canonical_fidelity_text(source) == source
    assert not s1_engine.normalization_preserves_content(source, "Some1 carved a st1 for anyone.")


def test_canonical_fidelity_keeps_independent_quantities_and_negation():
    assert s1_engine.normalization_preserves_content(
        "One hundred and five dollars, or one hundred and ten dollars.",
        "$105 or $110.",
    )
    assert s1_engine.normalization_preserves_content(
        "It costs one and two dollars.",
        "It costs $1 and $2.",
    )
    assert not s1_engine.normalization_preserves_content(
        "It costs two or three dollars.",
        "It costs $2, $3, or $4.",
    )
    assert not s1_engine.normalization_preserves_content("Please send it.", "Please do not send it.")
    assert not s1_engine.normalization_preserves_content("We cannot remove the file.", "We can remove the file.")


def test_closed_weekday_correction_allows_optional_commas():
    assert s1_engine.normalization_preserves_content(
        "Meet me Friday no wait Thursday.",
        "Meet me Thursday.",
    )
    assert s1_engine.normalization_preserves_content(
        "Meet me Saturday, I mean Sunday.",
        "Meet me Sunday.",
    )


def test_cold_inference_uses_bounded_batches_and_reuses_cached_model(monkeypatch, tmp_path):
    constructors = []

    class ConstructedLlama(FakeLlama):
        def __init__(self, **kwargs):
            super().__init__({"choices": [{"text": "Hello there.", "finish_reason": "stop"}]})
            self.constructor_kwargs = kwargs
            constructors.append(self)

    monkeypatch.setattr(s1_engine, "get_s1_model_path", lambda: tmp_path / "model.gguf")
    monkeypatch.setattr(s1_engine, "s1_can_handle", lambda **_kwargs: True)
    monkeypatch.setattr(s1_engine, "_LLM_LOCK", threading.Lock())
    monkeypatch.setattr(s1_engine, "register_idle_cleanup", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(s1_engine, "idle_time", lambda: 0.0)
    monkeypatch.setattr(s1_engine.polish_with_s1, "_cached_llm", None, raising=False)
    monkeypatch.setattr(s1_engine.polish_with_s1, "_cached_llm_path", None, raising=False)
    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=ConstructedLlama))

    assert s1_engine._polish_with_s1_impl("hello there") == "Hello there."
    assert s1_engine._polish_with_s1_impl("hello there") == "Hello there."

    assert len(constructors) == 1
    options = constructors[0].constructor_kwargs
    assert options["n_batch"] == 128
    assert options["n_ubatch"] == 128
    assert 1 <= options["n_threads_batch"] <= options["n_threads"] <= 8
    assert options["n_ctx"] == 4096


def test_warm_uses_same_bounded_constructor_and_reuses_model(monkeypatch, tmp_path):
    constructors = []

    class ConstructedLlama:
        def __init__(self, **kwargs):
            self.constructor_kwargs = kwargs
            constructors.append(self)

    monkeypatch.setattr(s1_engine, "get_s1_model_path", lambda: tmp_path / "model.gguf")
    monkeypatch.setattr(s1_engine, "is_s1_runtime_available", lambda: True)
    monkeypatch.setattr(s1_engine, "_LLM_LOCK", threading.Lock())
    monkeypatch.setattr(s1_engine, "register_idle_cleanup", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(s1_engine, "idle_time", lambda: 0.0)
    monkeypatch.setattr(s1_engine.polish_with_s1, "_cached_llm", None, raising=False)
    monkeypatch.setattr(s1_engine.polish_with_s1, "_cached_llm_path", None, raising=False)
    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=ConstructedLlama))

    assert s1_engine.warm_s1_model(timeout_seconds=1.0)
    warmed = s1_engine.polish_with_s1._cached_llm
    assert s1_engine.warm_s1_model(timeout_seconds=1.0)

    assert len(constructors) == 1
    assert s1_engine.polish_with_s1._cached_llm is warmed
    options = constructors[0].constructor_kwargs
    assert options["n_batch"] == 128
    assert options["n_ubatch"] == 128
    assert 1 <= options["n_threads_batch"] <= options["n_threads"] <= 8
    assert options["n_ctx"] == 4096


def test_public_s1_call_releases_model_lease_after_idle(monkeypatch):
    events = []

    class Lease:
        def release_after_idle(self, seconds):
            events.append(("release_after_idle", seconds))

        def release(self):
            events.append(("release",))

    monkeypatch.setattr(s1_engine, "acquire_model_use", lambda kind: events.append(("acquire", kind)) or Lease())
    monkeypatch.setattr(s1_engine, "_polish_with_s1_impl", lambda text, *args, **kwargs: "cleaned")

    assert s1_engine.polish_with_s1("spoken") == "cleaned"
    assert events == [
        ("acquire", "polish"),
        ("release_after_idle", s1_engine.S1_WARM_IDLE_SECONDS),
    ]

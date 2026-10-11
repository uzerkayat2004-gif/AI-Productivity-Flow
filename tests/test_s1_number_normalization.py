"""Focused fidelity checks for S1 spoken-number normalization."""

from __future__ import annotations

import types

from voice_flow import s1_engine


SOURCE = (
    "He right now there is one problem happening with the voice lock feature "
    "that when I'm using the voice lock picture without voice polishing it's "
    "working slow previously it was working so fast like it it it was instant "
    "as soon as I released my hotkey it was pasting the text but now it is "
    "taking one one and a half second and all can you check what's happening "
    "and fix it"
)

CANDIDATE = (
    "He right now there is one problem happening with the voice lock feature "
    "that when I'm using the voice lock picture without voice polishing it's "
    "working slow. Previously it was working so fast, like it was instant as "
    "soon as I released my hotkey. It was pasting the text, but now it is "
    "taking one and a half second, and all can you check what's happening "
    "and fix it?"
)

PUNCTUATED_WITH_STUTTER = SOURCE.replace(
    "working slow previously", "working slow. Previously"
).replace("fix it", "fix it?")


def test_captured_s1_candidate_accepts_one_word_stutter_before_half_quantity():
    assert s1_engine.check_joined_numbers_guard(SOURCE, CANDIDATE)
    assert s1_engine.normalization_preserves_content(SOURCE, CANDIDATE)


def test_punctuation_only_candidate_may_keep_the_source_stutter():
    assert s1_engine.check_joined_numbers_guard(SOURCE, PUNCTUATED_WITH_STUTTER)
    assert s1_engine.normalization_preserves_content(SOURCE, PUNCTUATED_WITH_STUTTER)
    assert not s1_engine.normalization_preserves_content(
        "The delay is one and a half seconds.",
        "The delay is one one and a half seconds.",
    )


def test_captured_candidate_survives_s1_inference_and_shared_fidelity(monkeypatch, tmp_path):
    model_path = tmp_path / s1_engine.S1_FILENAME
    model_path.write_bytes(b"fake-gguf")

    class FakeLlama:
        def tokenize(self, prompt: bytes):
            return prompt.split()

        def __call__(self, *_args, **_kwargs):
            return {"choices": [{"text": CANDIDATE, "finish_reason": "stop"}]}

    fake_llm = FakeLlama()
    monkeypatch.setattr(s1_engine, "get_s1_model_path", lambda: model_path)
    monkeypatch.setattr(s1_engine, "is_s1_runtime_available", lambda: True)
    monkeypatch.setattr(s1_engine.polish_with_s1, "_cached_llm", fake_llm, raising=False)
    monkeypatch.setattr(s1_engine.polish_with_s1, "_cached_llm_path", str(model_path), raising=False)
    monkeypatch.setattr(s1_engine.polish_with_s1, "_last_used", 0.0, raising=False)
    monkeypatch.setattr(s1_engine.polish_with_s1, "_mock_runner", None, raising=False)

    result = s1_engine.polish_with_s1(
        SOURCE,
        timeout_seconds=5,
        effective=types.SimpleNamespace(
            task="cleanup", format=None, style_id="other_formal", category="other"
        ),
        task="cleanup",
        style_id="other_formal",
    )

    assert result == CANDIDATE
    assert s1_engine.normalization_preserves_content(SOURCE, result)


def test_fraction_equivalence_does_not_drop_or_change_other_quantities():
    assert not s1_engine.normalization_preserves_content(
        "The delay is two seconds.",
        "The delay is one and a half seconds.",
    )
    assert not s1_engine.normalization_preserves_content(
        "There are one and two seconds of delay.",
        "There are two seconds of delay.",
    )
    assert not s1_engine.normalization_preserves_content(
        "Wait one second and two minutes.",
        "Wait one second.",
    )


def test_stutter_exception_preserves_fraction_unit_and_occurrence_counts():
    # A singular/plural cleanup remains equivalent for the captured quantity.
    plural_candidate = CANDIDATE.replace("one and a half second", "one and a half seconds")
    assert s1_engine.check_joined_numbers_guard(SOURCE, plural_candidate)
    assert s1_engine.normalization_preserves_content(SOURCE, plural_candidate)

    changed_unit = CANDIDATE.replace("one and a half second", "one and a half minute")
    assert not s1_engine.check_joined_numbers_guard(SOURCE, changed_unit)
    assert not s1_engine.normalization_preserves_content(SOURCE, changed_unit)

    duplicated_quantity = CANDIDATE.replace(
        "taking one and a half second, and all",
        "taking one and a half second and one and a half second, and all",
    )
    assert not s1_engine.check_joined_numbers_guard(SOURCE, duplicated_quantity)
    assert not s1_engine.normalization_preserves_content(SOURCE, duplicated_quantity)

    missing_fraction = CANDIDATE.replace("one and a half second", "one second")
    assert not s1_engine.check_joined_numbers_guard(SOURCE, missing_fraction)
    assert not s1_engine.normalization_preserves_content(SOURCE, missing_fraction)

    # Swapping units on two distinct mixed quantities must not pass as cleanup.
    two_quantity_source = SOURCE + " then two two and a half minutes"
    swapped_units = CANDIDATE.replace(
        "one and a half second", "one and a half minute"
    ) + " then two and a half seconds"
    assert not s1_engine.check_joined_numbers_guard(two_quantity_source, swapped_units)
    assert not s1_engine.normalization_preserves_content(two_quantity_source, swapped_units)


def test_stutter_equivalence_does_not_collapse_separate_quantities_or_other_twos():
    assert s1_engine.normalization_preserves_content("There are 2 items.", "There are 2 items.")
    assert not s1_engine.normalization_preserves_content("There are 2 items.", "There is 1 item.")
    assert not s1_engine.normalization_preserves_content(
        "Use one item and one item.",
        "Use one item.",
    )


def test_fraction_equivalence_preserves_negation_and_protected_literals():
    assert not s1_engine.normalization_preserves_content(
        "Do not wait one and a half seconds.",
        "Wait 1.5 seconds.",
    )
    assert not s1_engine.normalization_preserves_content(
        "Keep `one and a half seconds` unchanged.",
        "Keep `1.5 seconds` unchanged.",
    )
    assert not s1_engine.normalization_preserves_content(
        "Keep `one one and a half seconds` unchanged.",
        "Keep `one and a half seconds` unchanged.",
    )
    assert s1_engine._collapse_repeated_half_quantity_prefix(
        "Keep `one one and a half seconds` unchanged."
    ) == "Keep `one one and a half seconds` unchanged."
    assert not s1_engine.normalization_preserves_content(
        "Open C:\\timer\\one-and-a-half-seconds.txt.",
        "Open C:\\timer\\1.5-seconds.txt.",
    )
    assert not s1_engine.normalization_preserves_content(
        "Keep https://example.com/one-one-and-a-half-seconds unchanged.",
        "Keep https://example.com/one-and-a-half-seconds unchanged.",
    )

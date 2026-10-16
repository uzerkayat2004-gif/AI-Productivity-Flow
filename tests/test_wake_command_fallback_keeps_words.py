"""A recognised "Hey Voice Flow" command that nothing can perform must not lose words.

Mac QA (2026-10-16, voice_a2 / voice_b2): with no AI polish model (local
cleanup) or an S1/provider failure, the app pasted only the command's content
fragment:

* "Hey, voice slow, make this an email to Priya about the launch on Sunday."
  -> "To Priya about the launch on Sunday."
* "We discussed pricing, the launch date, and hiring, hey voice flow,
  summarize this." -> "We discussed pricing, the launch date, and hiring,."

When the command cannot run, the dictation minus the wake phrase is pasted.
When a model does perform it, its result is pasted as before.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

import voice_flow.main as main
from voice_flow.voice_commands import detect_voice_command, remove_activation_phrases


@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        (
            "Hey, voice slow, make this an email to Priya about the launch on Sunday.",
            "Make this an email to Priya about the launch on Sunday.",
        ),
        (
            "Hey, voice flow. Make this an email to Priya about the launch on Sunday.",
            "Make this an email to Priya about the launch on Sunday.",
        ),
        (
            "We discussed pricing, the launch date, and hiring, hey voice flow, summarize this.",
            "We discussed pricing, the launch date, and hiring. Summarize this.",
        ),
        (
            "We discussed pricing. Hey voice flow, summarize this.",
            "We discussed pricing. Summarize this.",
        ),
        ("I told my friend about Voice Flow yesterday.", "I told my friend about Voice Flow yesterday."),
        ("", ""),
    ],
)
def test_remove_activation_phrases_keeps_every_other_word(spoken, expected):
    assert remove_activation_phrases(spoken) == expected


def test_misheard_wake_phrase_voice_slow_is_still_a_command():
    detection = detect_voice_command("Hey, voice slow, make this an email to Priya about the launch on Sunday.")
    assert detection.command is not None
    assert detection.command.format == "email"


def _session():
    return main.DictationSession(
        123, "Editor", "smart_clean", "smart_clean", 0.0,
        resolved_style=SimpleNamespace(app_name="Editor", category="smart_clean",
                                       style_id="smart_clean", instruction="Keep the content."),
    )


def _run_pipeline(monkeypatch, transcript: str, polish_impl):
    current = _session()
    app = object.__new__(main.VoiceFlowApp)
    app.processing_lock = threading.Lock()
    app._state_lock = threading.RLock()
    app.state = main.DictationState.PROCESSING
    app.session = current
    app.transcriber = SimpleNamespace(transcribe=lambda *a, **k: transcript)
    app.overlay = SimpleNamespace(show_error=lambda *a: None, show_done=lambda *a: None,
                                  show_processing=lambda *a: None)
    app.hotkeys = SimpleNamespace(set_recording_state=lambda *a: None)
    app.recent_dictations = set()
    app._pending_command = None
    pasted: list[str] = []
    app.injector = SimpleNamespace(paste_text=lambda text, *a, **k: pasted.append(text) or True,
                                   get_selected_text_strict=lambda **k: "")
    settings = {"polishing_enabled": True}
    monkeypatch.setattr(main.storage, "get_setting", lambda key, default=None: settings.get(key, default))
    monkeypatch.setattr(main.storage, "update_dictation", lambda *a, **k: True)
    monkeypatch.setattr(main.polisher, "polish", polish_impl)
    app._process_dictation_pipeline(current, object(), 1.0, record_id=1, use_streaming=False)
    return pasted


def _no_model_polish(text, **kwargs):
    """The polisher with no AI model: deterministic cleanup, outcome 'local'."""
    callback = kwargs.get("outcome_callback")
    if callback is not None:
        callback("local")
    cleaned = text.strip()
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned[:1].upper() + cleaned[1:]


def _failing_provider_polish(text, **kwargs):
    callback = kwargs.get("outcome_callback")
    if kwargs.get("model_ref") != "local/deterministic" and callback is not None:
        callback("provider_failure")
    elif callback is not None:
        callback("local")
    return _no_model_polish(text)


def test_email_command_without_any_model_pastes_the_whole_sentence(monkeypatch):
    pasted = _run_pipeline(
        monkeypatch,
        "Hey, voice slow, make this an email to Priya about the launch on Sunday.",
        _no_model_polish,
    )
    assert pasted == ["Make this an email to Priya about the launch on Sunday."]


def test_summarize_command_with_failed_provider_keeps_content_and_punctuation(monkeypatch):
    pasted = _run_pipeline(
        monkeypatch,
        "We discussed pricing, the launch date, and hiring, hey voice flow, summarize this.",
        _failing_provider_polish,
    )
    assert pasted == ["We discussed pricing, the launch date, and hiring. Summarize this."]
    assert ",." not in pasted[0]


def test_command_performed_by_a_model_is_delivered_unchanged(monkeypatch):
    def ai_polish(text, **kwargs):
        callback = kwargs.get("outcome_callback")
        if callback is not None:
            callback("ai_accepted")
        return "Hi Priya,\n\nThe launch is on Sunday.\n\nBest regards"

    pasted = _run_pipeline(
        monkeypatch,
        "Hey voice flow, make this an email to Priya about the launch on Sunday.",
        ai_polish,
    )
    assert pasted and "Hi Priya" in pasted[0]
    assert "voice flow" not in pasted[0].lower()


def test_plain_dictation_is_unaffected(monkeypatch):
    pasted = _run_pipeline(monkeypatch, "The trial period ends in May.", _no_model_polish)
    assert pasted == ["The trial period ends in May."]

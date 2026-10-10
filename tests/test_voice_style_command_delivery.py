"""Focused delivery coverage for Voice Flow styles, commands, and local polish."""
from __future__ import annotations

import sys
import time
import types
from types import SimpleNamespace
from unittest.mock import patch

from voice_flow import effective_style as effective_style_module
from voice_flow import lfm_engine
from voice_flow.effective_style import resolve_effective_style
from voice_flow import polisher as polisher_module
from voice_flow import main as main_module
from voice_flow.polisher import TextPolisher
from voice_flow.style_formatter import style_formatter
from voice_flow.voice_commands import detect_voice_command


def _base_style() -> SimpleNamespace:
    return SimpleNamespace(
        category="developer",
        style_id="developer_casual",
        instruction="Conversational developer notes.",
    )


def test_commands_activate_saved_email_and_temporary_overrides() -> None:
    """Commands are parsed before the model and become its trusted style policy."""
    settings = {
        "style_email": "email_excited",
        "style_email_extra": "Always sign off with Best.",
    }
    with patch.object(
        effective_style_module.storage,
        "get_setting",
        side_effect=lambda key, default=None: settings.get(key, default),
    ):
        professional = resolve_effective_style(
            _base_style(),
            detect_voice_command(
                "Hey Voice Flow, make this a professional email but keep my wording. "
                "NimbusSDK ships Monday."
            ).command,
        )
        short = resolve_effective_style(
            _base_style(),
            detect_voice_command("Hey Voice Flow, make this short. NimbusSDK ships Monday.").command,
        )
        usual_email = resolve_effective_style(
            _base_style(),
            detect_voice_command("Hey Voice Flow, make this my usual email. NimbusSDK ships Monday.").command,
        )

    assert (professional.category, professional.style_id) == ("email", "email_formal")
    assert professional.requires_ai and professional.preserve_wording
    assert "formal email" in professional.instruction.lower()
    assert "do not re-author" in professional.instruction.lower()
    assert (short.style_id, short.requires_ai) == ("developer_casual", True)
    assert "keep the result short" in short.instruction.lower()
    assert (usual_email.category, usual_email.style_id) == ("email", "email_excited")
    assert "always sign off with best" in usual_email.instruction.lower()


def test_selected_local_lfm_receives_full_command_style_through_bridge(monkeypatch, tmp_path) -> None:
    """A selected local model receives command policy through the real bridge."""
    command = detect_voice_command(
        "Hey Voice Flow, make this a short professional email but keep my wording. "
        "NimbusSDK ships Monday with the complete release notes."
    ).command
    assert command is not None
    with patch.object(effective_style_module.storage, "get_setting", return_value="email_excited"):
        effective = resolve_effective_style(_base_style(), command)

    captured: dict[str, object] = {}

    class FakeLlama:
        def __init__(self, **kwargs) -> None:
            captured["init"] = kwargs

        def tokenize(self, _text, add_bos=False):
            return [1, 2, 3]

        def create_chat_completion(self, **kwargs):
            captured["request"] = kwargs
            return iter((
                {"choices": [{
                    "delta": {"content": "NimbusSDK ships Monday with the complete release notes."},
                    "finish_reason": "stop",
                }]},
            ))

    engine = TextPolisher()
    monkeypatch.setattr(
        polisher_module.storage,
        "get_setting",
        lambda key, default=None: True if key == "polishing_enabled" else default,
    )
    monkeypatch.setattr(polisher_module.storage, "get_all_api_keys", lambda: {})
    monkeypatch.setattr(polisher_module.storage, "get_all_provider_connections", lambda: {})
    monkeypatch.setattr(lfm_engine, "get_lfm_model_path", lambda: tmp_path / "lfm.gguf")
    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=FakeLlama))
    monkeypatch.delattr(lfm_engine.polish_with_lfm, "_cached_llm", raising=False)
    monkeypatch.delattr(lfm_engine.polish_with_lfm, "_cached_llm_path", raising=False)
    monkeypatch.setattr(polisher_module, "_apply_dictionary_safely", lambda text: text)

    outcomes: list[str] = []
    result = engine.polish(
        "NimbusSDK ships Monday with the complete release notes.",
        style_instruction=effective.instruction,
        force_ai=effective.requires_ai,
        task=effective.task,
        model_ref=lfm_engine.LFM_MODEL_ID,
        deadline=time.monotonic() + 8,
        outcome_callback=outcomes.append,
    )

    assert result == "NimbusSDK ships Monday with the complete release notes."
    messages = captured["request"]["messages"]
    system = messages[0]["content"].lower()
    assert "formal email" in system
    assert "keep the result short" in system
    assert "preserve the user's original wording" in system
    assert messages[1]["content"] == "NimbusSDK ships Monday with the complete release notes."
    # The fake model echoes the original sentence. It receives the complete
    # command policy, but does not produce the requested short email, so the
    # delivery must report the command as unfulfilled instead of claiming AI
    # polishing succeeded.
    assert outcomes == ["command_unfulfilled"]


def test_rejected_lfm_email_uses_only_source_preserving_local_structure(monkeypatch) -> None:
    """A hallucinated local email is rejected, then only an existing salutation is laid out."""
    engine = TextPolisher()
    detected = detect_voice_command(
        "Alex, please send the report by Friday. Hey Voice Flow, make this a professional email."
    )
    assert detected.command is not None
    source = detected.content
    monkeypatch.setattr(
        effective_style_module.storage,
        "get_setting",
        lambda key, default=None: "email_formal" if key == "style_email" else default,
    )
    effective = resolve_effective_style(_base_style(), detected.command)
    assert effective.format == "email"
    assert effective.task == "rewrite"
    assert effective.style_id == "email_formal"
    session = SimpleNamespace(
        cleanup_level="cleanup_light",
        style_id="other_formal",
        cursor_context=None,
        polish_model_ref=lfm_engine.LFM_MODEL_ID,
    )
    outcomes: list[str] = []
    monkeypatch.setattr(polisher_module.storage, "get_setting", lambda key, default=None: True if key == "polishing_enabled" else default)
    monkeypatch.setattr(polisher_module.storage, "get_all_api_keys", lambda: {})
    monkeypatch.setattr(engine, "_polish_with_api_pool", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(lfm_engine, "is_lfm_downloaded", lambda: True)
    monkeypatch.setattr(
        lfm_engine,
        "polish_with_lfm",
        lambda *_args, **_kwargs: "Subject: Update\n\nHello,\nI would like to submit the report.\n\n[Your Name]",
    )
    monkeypatch.setattr(polisher_module, "_apply_dictionary_safely", lambda text: text)
    monkeypatch.setattr(main_module, "dictionary_engine", SimpleNamespace(restore_dictionary_spelling=lambda text: text))
    monkeypatch.setattr(main_module, "polisher", engine)

    result = object.__new__(main_module.VoiceFlowApp)._finalize_text(
        source, session, effective=effective, command=detected.command, outcome_callback=outcomes.append,
    )

    assert result == "Alex,\n\nPlease send the report by Friday."
    assert "Subject:" not in result and "Your Name" not in result
    assert outcomes == ["local_format"]


def test_pure_keep_wording_lfm_command_uses_local_cleanup_without_inference(monkeypatch) -> None:
    """Keeping wording is a preservation request, so it must not invoke the model."""
    detected = detect_voice_command(
        "Do not delete Hyper Kube. Hey Voice Flow, keep my wording."
    )
    assert detected.command is not None
    assert detected.command.preserve_wording is True
    assert detected.command.format is None
    assert detected.command.overrides == {}
    effective = resolve_effective_style(_base_style(), detected.command)
    engine = TextPolisher()
    outcomes: list[str] = []
    dictionary = SimpleNamespace(
        apply_dictionary_post_processing=lambda text: text.replace("Hyper Kube", "HyperKube"),
        restore_dictionary_spelling=lambda text: text,
    )
    session = SimpleNamespace(
        cleanup_level="cleanup_light",
        style_id="developer_casual",
        cursor_context=None,
        polish_model_ref=lfm_engine.LFM_MODEL_ID,
    )
    monkeypatch.setattr(polisher_module.storage, "get_setting", lambda key, default=None: True if key == "polishing_enabled" else default)
    monkeypatch.setattr(polisher_module, "dictionary_engine", dictionary)
    monkeypatch.setattr(main_module, "dictionary_engine", dictionary)
    monkeypatch.setattr(engine, "_polish_with_api_pool", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("pool must not run")))
    monkeypatch.setattr(lfm_engine, "polish_with_lfm", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LFM must not run")))
    monkeypatch.setattr(main_module, "polisher", engine)

    result = object.__new__(main_module.VoiceFlowApp)._finalize_text(
        detected.content, session, effective=effective, command=detected.command, outcome_callback=outcomes.append,
    )

    assert result == "Do not delete HyperKube."
    assert outcomes == ["local_preserved"]


def test_style_formatting_preserves_custom_dictionary_casing() -> None:
    """A casual style may change prose casing but retains declared terminology."""
    assert style_formatter.format(
        "nimbussdk ships monday",
        style="email_very_casual",
        custom_dictionary=("NimbusSDK",),
    ) == "NimbusSDK ships monday"

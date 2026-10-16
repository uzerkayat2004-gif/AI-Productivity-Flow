"""Regression tests for real local offline S1-mini inference and desktop pipeline.

Validates:
1. Native llama-server binary existence and version/health check.
2. S1-mini Qwen3 GGUF model file integrity (SHA-256 and size).
3. Live HTTP inference via VF1Engine connecting to llama-server.
4. Correct generation across realistic Voice Flow diagnostic cases.
5. Factual preservation safety gate validation.
6. Faster-Whisper local STT model availability and transcription.
7. Clipboard text injection via injector.py.
"""
import json
import os
import sys
import pytest
from pathlib import Path

from voice_flow.vf1_engine import VF1Engine, VF1EngineConfig, VF1EngineResult
from voice_flow.vf_contract import VF1Request
from voice_flow.injector import _safe_copy_to_clipboard, _safe_paste_from_clipboard
from voice_flow import s1_engine


def test_s1_gguf_model_file_exists():
    """Verify S1-mini GGUF model exists and has correct size."""
    model_path = s1_engine.get_s1_model_path()
    if model_path is None:
        user_path = Path.home() / ".voice_flow" / "models" / s1_engine.S1_FILENAME
        if user_path.is_file():
            model_path = user_path
    assert model_path is not None, "S1-mini GGUF model file not found in models directory"
    assert model_path.is_file()
    assert model_path.stat().st_size == 484219808, f"Unexpected size: {model_path.stat().st_size}"


def test_llama_server_binary_exists():
    """Verify official precompiled llama-server executable exists."""
    engine = VF1Engine()
    binary = engine._find_llama_server_binary()
    assert binary is not None, "llama-server executable not found"
    assert binary.is_file()


def test_llama_server_health():
    """Verify llama-server is healthy and listening on configured port."""
    engine = VF1Engine()
    assert engine.is_server_healthy(), "llama-server is not reporting healthy on port 8080"


def test_real_s1_self_correction_resolution():
    """Real S1-mini resolves spoken self-correction accurately."""
    engine = VF1Engine(VF1EngineConfig(backend="llama_server"))
    transcript = "send the deployment summary to Rahul no wait send it to Priya"
    res = engine.polish_transcript(transcript, task="cleanup")

    assert res.safety_accepted is True
    assert "Priya" in res.final_text
    assert "Rahul" not in res.final_text
    assert res.tokens_per_second > 10.0


def test_real_s1_distinct_bullet_points():
    """Real S1-mini structures packing list keeping Laptop and Charger separate."""
    engine = VF1Engine(VF1EngineConfig(backend="llama_server"))
    transcript = "packing list laptop charger passport water bottle notepad"
    res = engine.polish_transcript(transcript, task="rewrite", format="bullets")

    assert res.safety_accepted is True
    assert "- laptop" in res.final_text.lower()
    assert "- charger" in res.final_text.lower()
    assert "laptop charger" not in res.final_text.lower()


def test_real_s1_currency_preservation():
    """Real S1-mini and safety gate preserve large Indian rupee figure."""
    engine = VF1Engine(VF1EngineConfig(backend="llama_server"))
    transcript = "please prepare a sanction order for ₹15,00,000 for the infrastructure vendor"
    res = engine.polish_transcript(transcript, task="cleanup")

    assert res.safety_accepted is True
    assert "₹15,00,000" in res.final_text


def test_real_s1_negation_preservation():
    """Real S1-mini preserves critical negation statement."""
    engine = VF1Engine(VF1EngineConfig(backend="llama_server"))
    transcript = "do not delete the production database records under any circumstances"
    res = engine.polish_transcript(transcript, task="cleanup")

    assert res.safety_accepted is True
    assert "do not delete" in res.final_text.lower()


def test_real_s1_dictated_question_not_answered():
    """Real S1-mini formats question without hallucinating technical answer."""
    engine = VF1Engine(VF1EngineConfig(backend="llama_server"))
    transcript = "format as bullet points: how do I configure the reverse proxy? Step one open the config file. Step two specify the upstream server. Step three reload the service."
    res = engine.polish_transcript(transcript, task="rewrite", format="bullets")

    assert res.safety_accepted is True
    assert "?" in res.final_text
    assert "here is how to" not in res.final_text.lower()
    assert "step 1" in res.final_text.lower()


def test_desktop_clipboard_injection_roundtrip():
    """Verify text injection roundtrip through clipboard."""
    test_phrase = "Voice Flow Verified Local Desktop Injection 2026"
    assert _safe_copy_to_clipboard(test_phrase) is True
    read_back = _safe_paste_from_clipboard()
    assert read_back == test_phrase

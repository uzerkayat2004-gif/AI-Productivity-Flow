import pytest
from voice_flow.audio_explainer_prompts import build_audio_explainer_prompt, sanitize_explanation_text
from voice_flow.local_summarizer import local_spoken_summarizer
from voice_flow.audio_summary import audio_summary_service
from voice_flow.structured_reader import PAUSE_SECTION, PAUSE_PARAGRAPH

def test_prompt_generation():
    prompt = build_audio_explainer_prompt("Please review this PR.")
    assert "Explain the following selected text to me conversationally" in prompt
    assert "Please review this PR." in prompt

def test_sanitize_chatter():
    dirty = "Sure, here is an explanation: The feature is ready."
    clean = sanitize_explanation_text(dirty)
    assert clean == "The feature is ready."

def test_sanitize_markdown():
    dirty = "## Header\n**Bold claim** with `code`."
    clean = sanitize_explanation_text(dirty)
    assert "##" not in clean
    assert "**" not in clean
    assert "`" not in clean

def test_explain_user_feedback_audio_flow():
    raw = (
        "Hey right now I just have tried the audio flow feature but still it is still not human like "
        "like human reading like do one thing research on it like how human explain each other like if "
        "human reading this exact message how it going to read and all because right now it's not like that "
        "He want does not exactly read the message directly it should be properly designed like it should not "
        "like a just read read read it should not like that it should be like a explanation type so can you "
        "research on it and design the audio flow feature like that"
    )
    explanation = local_spoken_summarizer.explain_conversationally(raw)
    assert "In this message, the sender shares feedback regarding the Audio Flow feature" in explanation
    assert "Specifically," in explanation
    assert "word-for-word" in explanation
    assert "explanation-style presentation" in explanation
    assert PAUSE_SECTION in explanation

def test_explain_bug_report_message():
    raw = (
        "hey right now i'm facing On the voicemail feature can you properly check what's happening on The "
        "Voice flow feature right now what's happening in happening is II just have upgraded the voice flow "
        "feature but right now I'm facing 1 bug that whenever I'm doing a mouse left click the voice detection "
        "is starting it should not be happening Can you check the back end and fix this issue and other issues "
        "like right now I'm doing a control plus copy and control plus it is not properly working"
    )
    explanation = local_spoken_summarizer.explain_conversationally(raw)
    assert "In this message, the sender shares feedback" in explanation
    assert "mouse click inadvertently triggers voice recording" in explanation
    assert "control plus C" in explanation

def test_explain_question():
    raw = "How do I configure the Edge TTS voice speed in Voice Flow?"
    explanation = local_spoken_summarizer.explain_conversationally(raw)
    assert "This question asks about" in explanation
    assert "Edge TTS voice speed" in explanation

def test_explain_code_snippet():
    raw = "def calculate_total(price, tax_rate=0.08):\n    return price * (1 + tax_rate)"
    explanation = local_spoken_summarizer.explain_conversationally(raw)
    assert "This code snippet outlines" in explanation
    assert "def calculate_total" in explanation

def test_explain_technical_doc():
    raw = (
        "SQLite is a C-language library that implements a small, fast, self-contained, high-reliability SQL database engine. "
        "SQLite is the most used database engine in the world. SQLite is built into all mobile phones and most computers."
    )
    explanation = local_spoken_summarizer.explain_conversationally(raw)
    assert "Here is an explanation of" in explanation
    assert "SQLite" in explanation

def test_audio_summary_service_explain_offline():
    raw = "Hey can you check if the audio flow feature is working properly?"
    explanation = audio_summary_service.explain(
        text=raw,
        model_ref="local/deterministic",
        allow_fallback=True,
    )
    assert "In this message, the sender shares feedback" in explanation
    assert "Audio Flow feature" in explanation

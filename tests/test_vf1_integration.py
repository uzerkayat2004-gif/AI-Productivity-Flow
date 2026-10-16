"""Integration tests for the local VF-1 Voice Writing Engine.

Validates:
1. Local offline task and prompt routing (cleanup, email, prompt, notes, lists).
2. Preservation of numbers, currencies, IDs, dates, and negation conditions.
3. No answering dictated questions unless explicitly requested as a transformation.
4. Host-side factual preservation safety gate interception and safe fallback.
5. Latency, token count, and telemetry measurement.
6. Optional LoRA candidate configuration.
"""
import pytest

from voice_flow.vf1_engine import VF1Engine, VF1EngineConfig, VF1EngineResult
from voice_flow.vf_contract import VF1Request


def test_vf1_engine_cleanup_task():
    """VF-1 engine removes speech disfluencies while preserving all facts and numbers."""
    engine = VF1Engine(VF1EngineConfig(backend="mock"))

    def mock_cleanup(prompt: str, req: VF1Request) -> str:
        # Mock model generation with filler
        return "So basically, we should refactor this legacy module."

    engine.set_mock_generator(mock_cleanup)

    transcript = "um so like basically we should uh refactor this legacy module"
    res = engine.polish_transcript(transcript, task="cleanup")

    assert res.safety_accepted is True
    assert res.source_preserved is False
    assert res.final_text == "We should refactor this legacy module."
    assert res.latency_ms >= 0.0
    assert res.task == "cleanup"


def test_vf1_engine_email_task_structure_and_identity():
    """VF-1 engine produces distinct Subject header and preserves speaker identity."""
    engine = VF1Engine(VF1EngineConfig(backend="mock"))

    def mock_email(prompt: str, req: VF1Request) -> str:
        return (
            "Subject: Budget Approval Update\n\n"
            "Hi Finance Team,\n\n"
            "The Q4 budget has been approved.\n\n"
            "Regards,\n"
            "Devon"
        )

    engine.set_mock_generator(mock_email)

    transcript = "email to finance team subject budget approval update hi team the Q4 budget has been approved regards devon"
    res = engine.polish_transcript(transcript, task="rewrite", format="email")

    assert res.safety_accepted is True
    assert res.source_preserved is False
    assert "Subject: Budget Approval Update" in res.final_text
    assert "Devon" in res.final_text
    assert "[Your Name]" not in res.final_text


def test_vf1_engine_prompt_synthesis_task():
    """VF-1 engine synthesizes usable prompt without repeating meta-directive wrappers."""
    engine = VF1Engine(VF1EngineConfig(backend="mock"))

    def mock_prompt(prompt: str, req: VF1Request) -> str:
        return "Write a Python function to parse JSON with error handling and retry logic."

    engine.set_mock_generator(mock_prompt)

    transcript = "make this a prompt: write a Python function to parse JSON with error handling and retry logic"
    res = engine.polish_transcript(transcript, task="prompt", format="prompt")

    assert res.safety_accepted is True
    assert res.source_preserved is False
    assert res.final_text.startswith("Write a Python function")
    assert "make this a prompt" not in res.final_text.lower()


def test_vf1_engine_bullet_list_item_preservation():
    """VF-1 engine formats bullet points keeping distinct items (Laptop vs Charger) separate."""
    engine = VF1Engine(VF1EngineConfig(backend="mock"))

    def mock_list(prompt: str, req: VF1Request) -> str:
        return (
            "Items to pack:\n"
            "- Laptop\n"
            "- Charger\n"
            "- Passport\n"
            "- Water bottle\n"
            "- Notepad"
        )

    engine.set_mock_generator(mock_list)

    transcript = "items to pack laptop charger passport water bottle notepad"
    res = engine.polish_transcript(transcript, task="rewrite", format="bullets")

    assert res.safety_accepted is True
    assert res.source_preserved is False
    assert "- Laptop" in res.final_text
    assert "- Charger" in res.final_text
    assert "Laptop charger" not in res.final_text


def test_vf1_engine_structured_notes_task():
    """VF-1 engine structures notes into meeting minutes with key takeaways."""
    engine = VF1Engine(VF1EngineConfig(backend="mock"))

    def mock_notes(prompt: str, req: VF1Request) -> str:
        return (
            "Meeting Notes:\n"
            "- Action: Update Kubernetes cluster config\n"
            "- Owner: Infra team\n"
            "- Deadline: Friday 5 PM"
        )

    engine.set_mock_generator(mock_notes)

    transcript = "meeting notes action update kubernetes cluster config owner infra team deadline friday 5 pm"
    res = engine.polish_transcript(transcript, task="rewrite", format="note")

    assert res.safety_accepted is True
    assert "Kubernetes" in res.final_text
    assert "Friday 5 PM" in res.final_text


def test_vf1_engine_format_not_answer_question():
    """VF-1 engine formats dictated question as a question and does NOT answer it."""
    engine = VF1Engine(VF1EngineConfig(backend="mock"))

    def mock_format_question(prompt: str, req: VF1Request) -> str:
        return (
            "How do I reset my password on the internal portal?\n"
            "- Step 1: Go to settings\n"
            "- Step 2: Click security\n"
            "- Step 3: Enter new password"
        )

    engine.set_mock_generator(mock_format_question)

    transcript = "format as bullet points: how do I reset my password on the internal portal? Step one go to settings. Step two click security. Step three enter new password."
    res = engine.polish_transcript(transcript, task="rewrite", format="bullets")

    assert res.safety_accepted is True
    assert res.final_text.startswith("How do I reset my password")
    assert "?" in res.final_text
    # Must not answer or hallucinate technical support text
    assert "here is the solution" not in res.final_text.lower()


def test_vf1_engine_safe_fallback_on_critical_numerical_corruption():
    """VF-1 engine intercepts numerical corruption (₹15,00,000 -> ₹15,000,000) and safely falls back to transcript."""
    engine = VF1Engine(VF1EngineConfig(backend="mock"))

    def mock_corrupt_number(prompt: str, req: VF1Request) -> str:
        # 10x numerical inflation corruption
        return "Please prepare a sanction order for ₹15,000,000 for the infrastructure vendor."

    engine.set_mock_generator(mock_corrupt_number)

    transcript = "please prepare a sanction order for ₹15,00,000 for the infrastructure vendor"
    res = engine.polish_transcript(transcript, task="cleanup")

    assert res.safety_accepted is False
    assert res.source_preserved is True
    assert res.final_text == transcript
    assert any("numerical" in r or "number" in r for r in res.safety_reasons)


def test_vf1_engine_safe_fallback_on_identifier_mutation():
    """VF-1 engine intercepts mutated entity code (PR-94821 -> PR-94820) and safely falls back to transcript."""
    engine = VF1Engine(VF1EngineConfig(backend="mock"))

    def mock_corrupt_id(prompt: str, req: VF1Request) -> str:
        return "Contact Dr. Sarah Jenkins regarding patient record PR-94820."

    engine.set_mock_generator(mock_corrupt_id)

    transcript = "contact Dr. Sarah Jenkins regarding patient record PR-94821"
    res = engine.polish_transcript(transcript, task="cleanup")

    assert res.safety_accepted is False
    assert res.source_preserved is True
    assert res.final_text == transcript
    assert any("identifier" in r for r in res.safety_reasons)


def test_vf1_engine_safe_fallback_on_negation_inversion():
    """VF-1 engine intercepts inverted negation ('do not delete' -> 'delete') and safely falls back to transcript."""
    engine = VF1Engine(VF1EngineConfig(backend="mock"))

    def mock_invert_negation(prompt: str, req: VF1Request) -> str:
        return "Delete the production database records immediately."

    engine.set_mock_generator(mock_invert_negation)

    transcript = "do not delete the production database records under any circumstances"
    res = engine.polish_transcript(transcript, task="cleanup")

    assert res.safety_accepted is False
    assert res.source_preserved is True
    assert res.final_text == transcript
    assert any("negation" in r for r in res.safety_reasons)


def test_vf1_engine_lora_candidate_configuration():
    """VF-1 engine supports configuring LoRA adapter path as an optional experimental candidate."""
    lora_path = r"D:\apf_restricted_data_vault\s1_stage3b_experiment_artifacts"
    cfg = VF1EngineConfig(
        model_id="superwhisper/s1-mini",
        use_lora=True,
        lora_adapter_path=lora_path,
        backend="mock",
    )
    engine = VF1Engine(cfg)

    def mock_lora_run(prompt: str, req: VF1Request) -> str:
        return "Write a Python script to validate schema migrations."

    engine.set_mock_generator(mock_lora_run)

    transcript = "make this a prompt: write a Python script to validate schema migrations"
    res = engine.polish_transcript(transcript, task="prompt")

    assert res.safety_accepted is True
    assert "VF-1 LoRA" in res.model_name
    assert res.final_text == "Write a Python script to validate schema migrations."


def test_vf1_engine_telemetry_recording():
    """VF-1 engine records latency, token count, and safety decisions."""
    engine = VF1Engine(VF1EngineConfig(backend="mock"))
    transcript = "the total project budget is £75,000 including taxes"

    res = engine.polish_transcript(transcript, task="cleanup")
    assert res.latency_ms >= 0.0
    assert res.input_tokens > 0

    telem = engine.get_last_telemetry()
    assert telem is not None
    assert telem["task"] == "cleanup"
    assert telem["safety_accepted"] is True
    assert telem["source_preserved"] is False
    assert "latency_ms" in telem

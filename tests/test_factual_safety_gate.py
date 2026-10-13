import pytest

from voice_flow.safety_gate import (
    SafetyGateDecision,
    check_identifier_preservation,
    check_negation_preservation,
    check_numerical_preservation,
    validate_and_gate_output,
)


def test_safety_gate_rejects_15_lakh_corruption_10x():
    """Safety gate MUST reject ₹15,00,000 being corrupted to ₹15,000,000 (10x error) and preserve original transcript."""
    transcript = "the consulting fee is ₹15,00,000 payable in three equal installments"
    candidate = "The consulting fee is ₹15,000,000 payable in three equal installments."

    decision = validate_and_gate_output(transcript, candidate)
    assert decision.accepted is False
    assert decision.source_preserved is True
    assert decision.final_text == transcript
    assert any("numerical" in r or "number" in r for r in decision.rejection_reasons)


def test_safety_gate_rejects_15_lakh_corruption_drop():
    """Safety gate MUST reject ₹15,00,000 being dropped to ₹15,000 (100x drop) and preserve original transcript."""
    transcript = "the consulting fee is ₹15,00,000 payable in three equal installments"
    candidate = "the consulting fee is ₹15,000, payable in three equal installments"

    decision = validate_and_gate_output(transcript, candidate)
    assert decision.accepted is False
    assert decision.source_preserved is True
    assert decision.final_text == transcript
    assert any("numerical" in r or "number" in r for r in decision.rejection_reasons)


def test_safety_gate_accepts_valid_currency_grouping_equivalence():
    """Safety gate accepts identical numerical quantities across Indian and Western grouping (₹4,20,000 == ₹420,000)."""
    transcript = "please send an invoice for ₹4,20,000 to the client"
    candidate = "Please send an invoice for ₹420,000 to the client."

    decision = validate_and_gate_output(transcript, candidate)
    assert decision.accepted is True
    assert decision.source_preserved is False
    assert decision.final_text == candidate


def test_safety_gate_rejects_identifier_mutation():
    """Safety gate rejects mutated entity code (PR-94821 -> PR-94820) and preserves original transcript."""
    transcript = "contact Dr. Sarah Jenkins regarding patient record PR-94821"
    candidate = "Contact Dr. Sarah Jenkins regarding patient record PR-94820."

    decision = validate_and_gate_output(transcript, candidate)
    assert decision.accepted is False
    assert decision.source_preserved is True
    assert decision.final_text == transcript
    assert any("identifier" in r for r in decision.rejection_reasons)


def test_safety_gate_rejects_identifier_truncation():
    """Safety gate rejects truncated tracking number (TRK-88204-X -> TRK-88204)."""
    transcript = "check the status of shipment tracking number TRK-88204-X"
    candidate = "Check the status of shipment tracking number TRK-88204."

    decision = validate_and_gate_output(transcript, candidate)
    assert decision.accepted is False
    assert decision.source_preserved is True
    assert decision.final_text == transcript
    assert any("identifier" in r for r in decision.rejection_reasons)


def test_safety_gate_rejects_negation_drop():
    """Safety gate rejects dropped negation ('do not delete' -> 'delete production database')."""
    transcript = "do not delete the production database records under any circumstances"
    candidate = "Delete the production database records under any circumstances."

    decision = validate_and_gate_output(transcript, candidate)
    assert decision.accepted is False
    assert decision.source_preserved is True
    assert decision.final_text == transcript
    assert any("negation" in r for r in decision.rejection_reasons)


def test_safety_gate_accepts_valid_speech_cleanup():
    """Safety gate accepts valid speech cleanup that removes filler words and adds proper punctuation."""
    transcript = "um so like basically we should uh refactor this legacy module"
    candidate = "So basically, we should refactor this legacy module."

    decision = validate_and_gate_output(transcript, candidate)
    assert decision.accepted is True
    assert decision.source_preserved is False
    assert decision.final_text == candidate


def test_safety_gate_accepts_spoken_self_correction():
    """Safety gate accepts valid resolution of spoken repair ('three no make that five copies' -> '5 copies')."""
    transcript = "send three no make that five copies to the audit committee"
    candidate = "Send 5 copies to the audit committee."

    decision = validate_and_gate_output(transcript, candidate)
    assert decision.accepted is True
    assert decision.source_preserved is False
    assert decision.final_text == candidate

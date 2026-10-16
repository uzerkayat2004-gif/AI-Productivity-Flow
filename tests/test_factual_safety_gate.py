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


def test_safety_gate_accepts_written_vs_spoken_numbers():
    """Safety gate accepts spoken number words converted to digits without false rejection."""
    transcript = "we expect twenty no thirty attendees at the conference workshop"
    candidate = "We expect 30 attendees at the conference workshop."

    decision = validate_and_gate_output(transcript, candidate)
    assert decision.accepted is True
    assert decision.source_preserved is False
    assert decision.final_text == candidate


def test_safety_gate_accepts_dates_times_formatting():
    """Safety gate accepts date and time formatting normalizations."""
    transcript = "reschedule the quarterly planning to Wednesday October 14th at 3:30 PM"
    candidate = "Reschedule the quarterly planning to Wednesday, October 14th at 3:30 PM."

    decision = validate_and_gate_output(transcript, candidate)
    assert decision.accepted is True
    assert decision.source_preserved is False
    assert decision.final_text == candidate


def test_safety_gate_accepts_genuine_alternatives():
    """Safety gate accepts genuine alternatives (either/or) without forcing collapse."""
    transcript = "the audit committee can meet on either Tuesday morning or Thursday afternoon"
    candidate = "The audit committee can meet on either Tuesday morning or Thursday afternoon."

    decision = validate_and_gate_output(transcript, candidate)
    assert decision.accepted is True
    assert decision.source_preserved is False
    assert decision.final_text == candidate


def test_safety_gate_execution_on_stage3b_actual_model_outputs():
    """Test safety gate on all 75 authentic GPU-generated model outputs from Stage 3B."""
    import json
    import os

    vault_json = r"D:\apf_restricted_data_vault\s1_stage3b_experiment_artifacts\eval_report.json"
    if not os.path.exists(vault_json):
        pytest.skip("Stage 3B evaluation report not found in vault")

    with open(vault_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data.get("comparison", []):
        cand_name = item.get("candidate")
        records = item.get("records", [])

        for rec in records:
            cid = rec["id"]
            transcript = rec["transcript"]
            generated = rec["generated"]

            decision = validate_and_gate_output(transcript, generated)

            if cid == "EVAL-IND-024":
                # Critical numerical corruption: must be REJECTED across all 3 models with fallback to transcript
                assert decision.accepted is False, f"EVAL-IND-024 should be rejected for {cand_name}"
                assert decision.source_preserved is True
                assert decision.final_text == transcript
            elif cid in ("EVAL-IND-001", "EVAL-IND-002", "EVAL-IND-003", "EVAL-IND-004", "EVAL-IND-005", "EVAL-IND-025"):
                # Clean factual cases must be ACCEPTED without false rejection
                assert decision.accepted is True, f"False rejection on {cid} for {cand_name}: {decision.rejection_reasons}"
                assert decision.source_preserved is False
                assert decision.final_text == generated


def test_safety_gate_distinguishes_vf1_tag_from_number_corruption():
    """Safety gate flags [VF-1] as tag_echo, NOT as numerical value corruption of the digit 1."""
    transcript = "reschedule the quarterly planning to Wednesday October 14th at 3:30 PM"
    candidate = "[VF-1] [Task: cleanup]\nReschedule the quarterly planning to Wednesday, October 14th at 3:30 PM."

    decision = validate_and_gate_output(transcript, candidate)
    assert decision.accepted is False
    assert decision.source_preserved is True
    assert decision.final_text == transcript
    # Must be rejected because of tag_echo, but NOT because '1' was corrupted
    assert "tag_echo" in decision.rejection_reasons
    assert not any("numerical_value_corrupted:1" in r for r in decision.rejection_reasons)


def test_safety_gate_accepted_does_not_imply_perfect_correctness():
    """Safety gate acceptance guarantees factual preservation, not total correctness."""
    transcript = "please prepare a sanction order for ₹15,00,000 for the infrastructure vendor"
    # An output with missing capitalization or slight informal styling is safe, but may not be 100% formatted
    candidate = "please prepare a sanction order for ₹15,00,000 for the infrastructure vendor"

    decision = validate_and_gate_output(transcript, candidate)
    assert decision.accepted is True
    # Acceptance is a safety pass, but caller must not treat acceptance as an assertion that the task is 100% complete
    assert decision.passed is True


def test_safety_gate_rejects_military_time_corruption_2300_to_0230():
    """Safety gate MUST reject 2300 UTC corrupted to 2:30 UTC and preserve original transcript."""
    transcript = "email to all engineering scheduled maintenance window will begin tonight at 2300 utc and conclude by 0100 utc services will experience brief intermittent connectivity"
    candidate = (
        "Subject: Engineering Scheduled Maintenance\n\n"
        "The scheduled maintenance window will begin tonight at 2:30 UTC and conclude by 01:00 UTC. "
        "Services will experience brief intermittent connectivity."
    )

    decision = validate_and_gate_output(transcript, candidate)
    assert decision.accepted is False
    assert decision.source_preserved is True
    assert decision.final_text == transcript
    assert any("2300" in r for r in decision.rejection_reasons)


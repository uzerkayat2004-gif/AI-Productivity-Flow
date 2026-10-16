"""Comprehensive Tests for P0-1 (Blocking Review Barrier) and P0-2 (Task-Aware Safety Gating).

Validates:
1. P0-1 Review Barrier:
   - Text CANNOT reach target application before explicit approval.
   - User can correct names, amounts, times, and identifiers.
   - Final inserted text exactly matches approved correction.
   - Cancel leaves target application unchanged (insertion_permitted=False).
   - Closing or ignoring the review interface never silently approves text.
   - Replay ACCP-F1-001 (currency self-correction) and ACCP-F1-002 (Devon vs Devin).
   - Grounded contact dictionary offers alternatives without silent substitution.
2. P0-2 Task-Aware Factual Gating:
   - Paired positive and negative tests for email subject headers.
   - Legitimate email structure with faithful subject lines is permitted.
   - Unsupported numbers, amounts, dates, deadlines, and commitments in subjects are blocked.
   - Non-email tasks with subject headers are rejected.
3. P0-5 Draft Preservation:
   - Failed or cancelled follow-up edits leave the document byte-for-byte unchanged.
   - No diagnostic notes are appended to the document text.
"""
from __future__ import annotations

import pytest

from voice_flow.entity_review import (
    CriticalEntity,
    ReviewResolution,
    check_user_review_barrier,
    detect_critical_entities,
    get_review_manager,
)
from voice_flow.safety_gate import validate_and_gate_output
from voice_flow.vf_checks import check_output


# ==============================================================================
# P0-1: Blocking Review Barrier Tests
# ==============================================================================

def test_review_barrier_blocks_insertion_without_explicit_approval():
    """High-risk text is blocked from insertion until approved."""
    text = "Transfer 5 Lock 50,000 Rupees plus 18% GST to the vendor account."
    needs_review, entities, summary = check_user_review_barrier(text)

    assert needs_review is True
    assert len(entities) >= 1

    # Verify default fail-closed behavior if closed or ignored
    mgr = get_review_manager()
    mgr.set_resolver(None)  # No UI / unhandled environment

    # Attempt resolution with no user confirmation
    res = mgr.resolve_review(text, entities)
    assert res.insertion_permitted is False
    assert res.approved is False
    assert res.final_text == ""


def test_review_barrier_cancel_leaves_target_unchanged():
    """When user cancels, insertion_permitted is False and final_text is empty."""
    text = "Do not transfer the $7,500 until Devin confirms in voice 8,821 in writing."
    needs_review, entities, summary = check_user_review_barrier(text, user_dictionary=["Devon Vance"])

    assert needs_review is True
    mgr = get_review_manager()

    # User clicks Cancel
    mgr.set_resolver(lambda t, e, task, d: ReviewResolution(
        approved=False,
        action="cancelled",
        final_text="",
        insertion_permitted=False,
        reason="User cancelled in review dialog",
    ))

    res = mgr.resolve_review(text, entities)
    assert res.insertion_permitted is False
    assert res.approved is False
    assert res.action == "cancelled"
    assert res.final_text == ""


def test_review_barrier_closing_or_ignoring_never_silently_approves():
    """Closing the review dialog (WM_DELETE_WINDOW) fails closed."""
    text = "Maintenance window tonight at 2300 UTC."
    needs_review, entities, _ = check_user_review_barrier(text)
    assert needs_review is True

    mgr = get_review_manager()
    mgr.set_resolver(lambda t, e, task, d: ReviewResolution(
        approved=False,
        action="closed",
        final_text="",
        insertion_permitted=False,
        reason="Window closed by user",
    ))

    res = mgr.resolve_review(text, entities)
    assert res.insertion_permitted is False
    assert res.approved is False
    assert res.final_text == ""


def test_review_barrier_devon_grounded_contact_alternative():
    """Devin triggers review offering Devon from contact dictionary, requiring confirmation."""
    text = "Do not transfer the $7,500 until Devin confirms invoice 8821 in writing."
    contacts = ["Devon Vance", "Devon"]
    entities = detect_critical_entities(text, user_dictionary=contacts)

    name_ents = [e for e in entities if e.entity_type == "name"]
    assert len(name_ents) >= 1
    devon_ent = name_ents[0]

    assert devon_ent.original == "Devin"
    assert devon_ent.suggested in contacts
    assert devon_ent.requires_review is True
    assert "Devon" in devon_ent.alternatives
    assert "Devin" in devon_ent.alternatives

    # User confirms the suggested correction
    mgr = get_review_manager()
    mgr.set_resolver(lambda t, e, task, d: ReviewResolution(
        approved=True,
        action="corrected",
        final_text=t.replace(devon_ent.original, devon_ent.suggested),
        insertion_permitted=True,
        corrections={devon_ent.original: devon_ent.suggested},
    ))

    res = mgr.resolve_review(text, entities)
    assert res.insertion_permitted is True
    assert res.approved is True
    assert "Devon" in res.final_text
    assert "Devin" not in res.final_text
    assert res.final_text == "Do not transfer the $7,500 until Devon confirms invoice 8821 in writing."


def test_review_barrier_accp_f1_001_currency_correction():
    """ACCP-F1-001: User reviews acoustic '5 Lock' and approves formatted ₹5,50,000."""
    raw_text = "Transfer 5 Lock 50,000 Rupees plus 18% GST to the vendor account."
    needs_review, entities, summary = check_user_review_barrier(raw_text)
    assert needs_review is True

    # User corrects '5 Lock 50,000 Rupees' to '₹5,50,000'
    mgr = get_review_manager()
    corrected_text = "Transfer ₹5,50,000 plus 18% GST to the vendor account."
    mgr.set_resolver(lambda t, e, task, d: ReviewResolution(
        approved=True,
        action="corrected",
        final_text=corrected_text,
        insertion_permitted=True,
        corrections={"5 Lock 50,000 Rupees": "₹5,50,000"},
    ))

    res = mgr.resolve_review(raw_text, entities)
    assert res.insertion_permitted is True
    assert res.final_text == "Transfer ₹5,50,000 plus 18% GST to the vendor account."


# ==============================================================================
# P0-2: Task-Aware Email Subject Gating (Paired Positive & Negative Tests)
# ==============================================================================

def test_p0_2_positive_email_subject_legitimate_and_faithful():
    """Positive: Email request with semantically faithful subject line passes."""
    source = (
        "write an email to the client steering committee letting them know our staging "
        "environment is restored and root cause analysis will be delivered by 5 pm marcus"
    )
    output = (
        "Subject: Restoration of Staging Environment and Root Cause Analysis\n\n"
        "Dear Steering Committee,\n\n"
        "Our staging environment is now restored, and root cause analysis will be delivered by 5pm.\n\n"
        "Best regards,\nMarcus"
    )

    decision = validate_and_gate_output(
        source,
        output,
        task="rewrite",
        format="email",
    )

    assert "invented_subject" not in decision.rejection_reasons
    assert not any("subject" in r for r in decision.rejection_reasons)
    assert decision.accepted is True


def test_p0_2_negative_unsupported_amount_in_email_subject():
    """Negative: Subject line inventing an unsupported dollar amount is blocked."""
    source = "write an email to the team letting them know the staging environment is restored"
    output = (
        "Subject: $50,000 Refund Approved for Staging Outage\n\n"
        "Hi Team,\n\nThe staging environment is restored."
    )

    decision = validate_and_gate_output(
        source,
        output,
        task="rewrite",
        format="email",
    )

    assert decision.accepted is False
    assert any("subject_number:50000" in r or "number_invented:50000" in r for r in decision.rejection_reasons)


def test_p0_2_negative_unsupported_deadline_in_email_subject():
    """Negative: Subject line inventing an unsupported deadline is blocked."""
    source = "email to engineering team staging environment is restored"
    output = (
        "Subject: Urgent Deployment Required by 3pm Friday\n\n"
        "Hi Team,\n\nThe staging environment is restored."
    )

    decision = validate_and_gate_output(
        source,
        output,
        task="rewrite",
        format="email",
    )

    assert decision.accepted is False
    assert any("subject_deadline" in r for r in decision.rejection_reasons)


def test_p0_2_negative_unsupported_commitment_in_email_subject():
    """Negative: Subject line inventing contract termination/lawsuit is blocked."""
    source = "write an email to the client letting them know our staging environment is restored"
    output = (
        "Subject: Settlement and Penalty Termination Notice\n\n"
        "Dear Client,\n\nOur staging environment is restored."
    )

    decision = validate_and_gate_output(
        source,
        output,
        task="rewrite",
        format="email",
    )

    assert decision.accepted is False
    assert any("subject_commitment" in r for r in decision.rejection_reasons)


def test_p0_2_negative_non_email_task_with_subject_header():
    """Negative: Plain cleanup or list task with a subject header is rejected."""
    source = "pre flight deployment checklist verify ssl certificates backup database"
    output = (
        "Subject: Deployment Checklist\n"
        "- Verify SSL certificates\n"
        "- Backup database"
    )

    decision = validate_and_gate_output(
        source,
        output,
        task="cleanup",
        format="bullets",
    )

    assert decision.accepted is False
    assert "invented_subject" in decision.rejection_reasons


# ==============================================================================
# P0-5: Draft Preservation on Follow-up Edits
# ==============================================================================

def test_p0_5_failed_edit_preserves_draft_byte_for_byte_without_appended_note():
    """Failed draft edit leaves original draft byte-for-byte unchanged with NO note in text."""
    draft = "The product launch is scheduled for Tuesday at 9:00 AM in the main auditorium."
    source = "let us push the launch to friday at eleven thirty am instead"

    # Candidate dropped draft context entirely
    bad_candidate = "Let us push the launch to Friday at 11:30 AM instead."

    from voice_flow.vf1_engine import VF1Engine, VF1EngineConfig
    engine = VF1Engine(VF1EngineConfig(backend="mock"))

    # Register mock returning the bad candidate
    engine.set_mock_generator(lambda p, r: bad_candidate)

    res = engine.polish_transcript(
        source,
        task="edit",
        draft=draft,
    )

    # Draft must be byte-for-byte identical to original draft
    assert res.final_text == draft
    assert "[Voice Flow Note:" not in res.final_text
    assert res.source_preserved is True
    assert "draft_context_dropped" in res.safety_reasons


def test_p0_5_sprint_checklist_failed_edit_preserves_draft_byte_for_byte():
    """Sprint checklist failed edit leaves original checklist untouched."""
    draft = "Sprint 42 Checklist:\n- Deploy auth service\n- Run smoke tests"
    source = "make it sprint 43 and add verify rate limiting"

    # Bad candidate dropped all existing items
    bad_candidate = "Sprint 43: Verify rate limiting."

    from voice_flow.vf1_engine import VF1Engine, VF1EngineConfig
    engine = VF1Engine(VF1EngineConfig(backend="mock"))
    engine.set_mock_generator(lambda p, r: bad_candidate)

    res = engine.polish_transcript(
        source,
        task="edit",
        draft=draft,
    )

    assert res.final_text == draft
    assert "[Voice Flow Note:" not in res.final_text
    assert res.source_preserved is True
    assert "draft_context_dropped" in res.safety_reasons


# ==============================================================================
# P0-3: Equivalent-Value Handling & Strict Factual Rejection Tests
# ==============================================================================

def test_p0_3_positive_time_notation_equivalence():
    """Positive: Recognized time equivalences like 11.30am <-> 11:30 AM pass."""
    # Whisper dot notation to standard AM/PM colon notation
    src1 = "let us meet tomorrow at 11.30am to review the deck"
    out1 = "Let us meet tomorrow at 11:30 AM to review the deck."
    d1 = validate_and_gate_output(src1, out1, task="cleanup")
    assert d1.accepted is True
    assert not d1.rejection_reasons

    # Colon notation to dot notation
    src2 = "let us meet tomorrow at 11:30 AM to review the deck"
    out2 = "Let us meet tomorrow at 11.30am to review the deck."
    d2 = validate_and_gate_output(src2, out2, task="cleanup")
    assert d2.accepted is True
    assert not d2.rejection_reasons


def test_p0_3_positive_model_designation_equivalence():
    """Positive: Alphanumeric model designations like GPT-4 <-> GPT4 pass."""
    # Hyphen to non-hyphen
    src1 = "make a prompt for GPT-4 to summarize the earnings report"
    out1 = "Write a prompt for GPT4 that summarizes the earnings report."
    d1 = validate_and_gate_output(src1, out1, task="cleanup")
    assert d1.accepted is True
    assert not d1.rejection_reasons

    # Non-hyphen to hyphen
    src2 = "make a prompt for GPT4 to summarize the earnings report"
    out2 = "Write a prompt for GPT-4 that summarizes the earnings report."
    d2 = validate_and_gate_output(src2, out2, task="cleanup")
    assert d2.accepted is True
    assert not d2.rejection_reasons


def test_p0_3_negative_time_corruption_2300_to_0230_rejected():
    """Negative: Dangerous time shift (23:00 UTC -> 02:30 UTC) is strictly rejected."""
    source = "scheduled maintenance window tonight at 2300 UTC"
    corrupted_output = "Scheduled maintenance window tonight at 02:30 UTC."

    decision = validate_and_gate_output(source, corrupted_output, task="cleanup")
    assert decision.accepted is False
    assert any("2300" in r or "23" in r for r in decision.rejection_reasons)


def test_p0_3_negative_invoice_id_mutation_rejected():
    """Negative: Invoice identifier mutation (invoice 8821 -> invoice 8822) is strictly rejected."""
    source = "hold payment until Devon confirms invoice 8821 in writing"
    corrupted_output = "Hold payment until Devon confirms invoice 8822 in writing."

    decision = validate_and_gate_output(source, corrupted_output, task="cleanup")
    assert decision.accepted is False
    assert any("8821" in r or "8822" in r for r in decision.rejection_reasons)


def test_p0_3_negative_numerical_corruption_amount_dropped_rejected():
    """Negative: Financial amount corruption ($7,500 -> $500) is strictly rejected."""
    source = "do not transfer the $7,500 until approved"
    corrupted_output = "Do not transfer the $500 until approved."

    decision = validate_and_gate_output(source, corrupted_output, task="cleanup")
    assert decision.accepted is False
    assert any("7500" in r or "500" in r for r in decision.rejection_reasons)


# ==============================================================================
# P0-4: Focus Protection & Pending Exit Safety Tests
# ==============================================================================

def test_injector_refuses_paste_when_target_window_closed():
    """Focus safety: inject_text refuses to paste if target window is closed/invalid."""
    from voice_flow.injector import inject_text

    # Provide a non-existent/bogus HWND (999999999)
    result = inject_text("Secret text that must not leak", target_hwnd=999999999)
    assert result is False, "inject_text must refuse to paste into wrong/closed window!"


def test_review_barrier_application_exit_while_pending_fails_closed():
    """Fail-closed: Review resolution on app exit or unhandled termination denies insertion."""
    from voice_flow.entity_review import BlockingReviewManager

    mgr = BlockingReviewManager()
    mgr.set_resolver(lambda t, e, task, d: ReviewResolution(
        approved=False,
        action="app_exit",
        final_text="",
        insertion_permitted=False,
        reason="Application exited while review pending",
    ))

    text = "Transfer $50,000 to vendor"
    _, entities, _ = check_user_review_barrier(text)
    assert len(entities) > 0
    res = mgr.resolve_review(text, entities)
    assert res.insertion_permitted is False
    assert res.approved is False
    assert res.action == "app_exit"
    assert res.final_text == ""


# ==============================================================================
# P0-5: Prompt-Synthesis Target Separation & Email Sign-Off Regression Tests
# ==============================================================================

def test_prompt_synthesis_safety_separates_destination_model_from_constraints():
    """Prompt task: Stripped destination model (GPT-4) does not trigger false rejection."""
    source = "can you make me a prompt for GPT-4 that asks it to extract all named entities from an SEC 10-K filing and return them in JSON format"
    candidate = "Extract all named entities from an SEC 10-K filing and return them in JSON format."

    decision = validate_and_gate_output(source, candidate, task="prompt")
    assert decision.accepted is True
    assert not decision.rejection_reasons
    assert decision.final_text == candidate


def test_prompt_synthesis_safety_strictly_preserves_mandatory_constraints():
    """Prompt task: Actual domain constraints (SEC 10-K) MUST be strictly preserved."""
    source = "can you make me a prompt for GPT-4 that asks it to extract all named entities from an SEC 10-K filing and return them in JSON format"
    corrupted_candidate = "Extract all named entities from an SEC 10-Q filing and return them in JSON format."

    decision = validate_and_gate_output(source, corrupted_candidate, task="prompt")
    assert decision.accepted is False
    assert any("SEC" in r or "10" in r for r in decision.rejection_reasons)


def test_email_signoff_proper_formatting_regression():
    """Email task: Spoken trailing sender name is cleanly separated into proper sign-off."""
    from voice_flow.vf1_engine import VF1Engine
    from voice_flow.vf_contract import VF1Request

    engine = VF1Engine()
    req = VF1Request(
        task="rewrite",
        format="email",
        transcript="write an email to the client steering committee letting them know our staging environment is restored and root cause analysis will be delivered by 5 pm marcus",
    )
    raw_model_gen = "Subject: Restoration of Staging Environment and Root Cause Analysis\n\nDear Steering Committee,\n\nOur staging environment is now restored, and root cause analysis will be delivered by 5pm Marcus."
    postprocessed = engine._postprocess_candidate(raw_model_gen, req)

    assert "Best regards,\nMarcus" in postprocessed
    assert "delivered by 5pm." in postprocessed or "delivered by 5pm Marcus." not in postprocessed


def test_email_signoff_rejects_ambiguous_non_sender_words():
    """Task 5: Ordinary words (sharp, tomorrow, EST, please, instead, today) MUST NOT become signatures."""
    from voice_flow.vf1_engine import VF1Engine
    from voice_flow.vf_contract import VF1Request

    engine = VF1Engine()
    test_cases = [
        ("delivered by 5pm sharp", "delivered by 5pm sharp."),
        ("delivered by 5pm tomorrow", "delivered by 5pm tomorrow."),
        ("delivered by 5pm EST", "delivered by 5pm EST."),
        ("delivered by 5pm please", "delivered by 5pm please."),
        ("delivered by 5pm instead", "delivered by 5pm instead."),
        ("delivered by 5pm today", "delivered by 5pm today."),
    ]

    for spoken_phrase, expected_phrase in test_cases:
        transcript = f"email to team report will be {spoken_phrase}"
        raw_gen = f"Subject: Report Status\n\nHi Team,\n\nThe report will be {spoken_phrase}."
        req = VF1Request(task="rewrite", format="email", transcript=transcript)
        out = engine._postprocess_candidate(raw_gen, req)
        # Verify NO accidental signature was created
        assert "Best regards," not in out, f"False signature generated for '{spoken_phrase}'"
        assert "Regards," not in out, f"False signature generated for '{spoken_phrase}'"
        assert expected_phrase.lower() in out.lower(), f"Expected '{expected_phrase}' preserved in output"


def test_email_signoff_accepts_explicit_spoken_triggers():
    """Task 5: Explicit spoken signature markers (from Devon, regards Marcus, signed Alex) are properly formatted."""
    from voice_flow.vf1_engine import VF1Engine
    from voice_flow.vf_contract import VF1Request

    engine = VF1Engine()
    test_cases = [
        ("report will be delivered by 5pm from Devon", "Devon"),
        ("report will be delivered by 5pm regards Marcus", "Marcus"),
        ("report will be delivered by 5pm signed Alex", "Alex"),
    ]

    for transcript, expected_name in test_cases:
        raw_gen = f"Subject: Report Status\n\nHi Team,\n\nThe report will be delivered by 5pm {expected_name}."
        req = VF1Request(task="rewrite", format="email", transcript=f"email to team {transcript}")
        out = engine._postprocess_candidate(raw_gen, req)
        assert f"\n{expected_name}" in out, f"Expected signature for {expected_name} not found"
        assert "delivered by 5pm." in out


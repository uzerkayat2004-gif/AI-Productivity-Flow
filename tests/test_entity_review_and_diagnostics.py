"""Tests for Critical Entity Detection, Phonetic Variations, and Diagnostic Traceability.

Validates:
1. Phonetic name detection and user review path (Devon <-> Devin) without silent substitution.
2. Email greeting formatting fix (no 'Hi Team The,') and speaker identity preservation.
3. Financial figures detection and verification gating.
4. Technical ID detection (e.g. PR-42) and verification.
5. Email address detection and formatting.
6. Diagnostic trace generation: zero unconsented audio or PII retention.
7. User review resolution actions (accept suggested, keep original, custom edit).
"""
from __future__ import annotations

try:
    import pytest
except ImportError:
    pytest = None  # type: ignore

from voice_flow.entity_review import (
    CriticalEntity,
    DiagnosticTrace,
    apply_review_decision,
    check_user_review_barrier,
    create_diagnostic_trace,
    detect_critical_entities,
    mask_pii,
    soundex,
)
from voice_flow.vf1_engine import VF1Engine, VF1EngineConfig
from voice_flow.vf_contract import VF1Request


def test_soundex_phonetic_homophones():
    """Verify that American Soundex accurately identifies phonetic homophones."""
    assert soundex("Devon") == soundex("Devin") == "D150"
    assert soundex("Bryan") == soundex("Brian") == "B650"
    assert soundex("Stephen") == soundex("Steven") == "S315"
    assert soundex("Marc") == soundex("Mark") == "M620"
    assert soundex("Jon") == soundex("John") == "J500"


def test_phonetic_name_variation_flagged_for_review_without_silent_substitution():
    """Devon is flagged as a phonetic candidate for Devin without altering the raw text."""
    text = "Please follow up with Devon Vance regarding the project timeline."
    entities = detect_critical_entities(text, user_dictionary=["Devin Vance"])

    name_entities = [e for e in entities if e.entity_type == "name"]
    assert len(name_entities) >= 1
    devon_entity = next(e for e in name_entities if "Devon" in e.original)

    assert devon_entity.original == "Devon Vance" or devon_entity.original == "Devon"
    assert devon_entity.suggested == "Devin Vance" or devon_entity.suggested == "Devin"
    assert devon_entity.requires_review is True
    assert "phonetic" in devon_entity.reason.lower() or "sound-alike" in devon_entity.reason.lower()

    # Original text remains untouched by detection alone (no silent invention)
    assert "Devon" in text


def test_email_greeting_formatting_removes_trailing_stopwords():
    """Email formatting cleans 'Hi Team The,' to 'Hi Team,' and preserves Devon Vance signoff."""
    engine = VF1Engine(VF1EngineConfig(backend="mock"))
    transcript = (
        "email to finance team subject budget approval update hi team the "
        "Q4 infrastructure budget has been approved for execution regards Devon Vance"
    )

    req = VF1Request(task="email", format="email", transcript=transcript)
    res = engine._postprocess_candidate(transcript, req)

    assert "Subject: Budget Approval Update" in res
    assert "Hi Team," in res
    assert "Hi Team The," not in res
    assert "The Q4 infrastructure budget has been approved for execution." in res
    assert "Regards,\nDevon Vance" in res or "Best regards,\nDevon Vance" in res


def test_financial_figures_detected_and_flagged_for_review():
    """Financial quantities like $2.5 million are detected and flagged for review."""
    text = "We approved an initial allocation of $2.5 million for Q3 infrastructure."
    entities = detect_critical_entities(text)

    fin_entities = [e for e in entities if e.entity_type == "financial"]
    assert len(fin_entities) == 1
    assert "$2.5 million" in fin_entities[0].original
    assert fin_entities[0].requires_review is True


def test_technical_ids_detected_and_flagged_for_review():
    """Alphanumeric IDs like PR-42 or CVE-2024-1234 are detected and flagged for review."""
    text = "Please review PR-42 before resolving CVE-2024-9981."
    entities = detect_critical_entities(text)

    id_entities = [e for e in entities if e.entity_type == "id"]
    assert len(id_entities) == 2
    originals = {e.original for e in id_entities}
    assert "PR-42" in originals
    assert "CVE-2024-9981" in originals


def test_email_addresses_detected():
    """Email addresses are extracted and verified."""
    text = "Send the updated slide deck to devon.vance@company.com and finance@company.com."
    entities = detect_critical_entities(text)

    email_entities = [e for e in entities if e.entity_type == "email"]
    assert len(email_entities) == 2
    emails = {e.original for e in email_entities}
    assert "devon.vance@company.com" in emails
    assert "finance@company.com" in emails


def test_apply_review_decision_accept_suggested():
    """User chooses to accept suggested phonetic correction (Devon -> Devin)."""
    text = "Best regards, Devon Vance"
    entity = CriticalEntity(
        entity_type="name",
        original="Devon",
        suggested="Devin",
        requires_review=True,
    )
    updated = apply_review_decision(text, entity, action="accept_suggested")
    assert updated == "Best regards, Devin Vance"


def test_apply_review_decision_keep_original():
    """User chooses to retain original transcribed identity."""
    text = "Best regards, Devon Vance"
    entity = CriticalEntity(
        entity_type="name",
        original="Devon",
        suggested="Devin",
        requires_review=True,
    )
    updated = apply_review_decision(text, entity, action="keep_original")
    assert updated == "Best regards, Devon Vance"


def test_apply_review_decision_custom_value():
    """User provides a custom override string."""
    text = "Total funding: $2.5 million."
    entity = CriticalEntity(
        entity_type="financial",
        original="$2.5 million",
        requires_review=True,
    )
    updated = apply_review_decision(text, entity, action="custom", custom_value="$2,500,000 USD")
    assert updated == "Total funding: $2,500,000 USD."


def test_diagnostic_trace_privacy_preservation_without_consent():
    """When consent is False, raw audio is not stored and PII is masked."""
    raw_stt = "email devon.vance@company.com subject budget update approved $2.5 million regards Devon Vance"
    entities = detect_critical_entities(raw_stt)

    trace = create_diagnostic_trace(
        session_id="sess-test-001",
        audio_duration_seconds=3.42,
        raw_stt_text=raw_stt,
        raw_s1_output="Subject: Budget Update\n\nApproved $2.5 million.\n\nRegards,\nDevon Vance",
        postprocessed_text="Subject: Budget Update\n\nApproved $2.5 million.\n\nRegards,\nDevon Vance",
        delivered_text="Subject: Budget Update\n\nApproved $2.5 million.\n\nRegards,\nDevon Vance",
        safety_gate_passed=True,
        safety_reasons=[],
        flagged_entities=entities,
        store_audio_consent=False,
        retain_pii_consent=False,
    )

    assert trace.audio_retained is False
    assert trace.pii_retained is False
    # Verified: PII is masked in diagnostic trace
    assert "devon.vance@company.com" not in trace.raw_stt_text_masked
    assert "[EMAIL_MASKED]" in trace.raw_stt_text_masked
    assert "$2.5 million" not in trace.raw_stt_text_masked
    assert "[AMOUNT_MASKED]" in trace.raw_stt_text_masked
    # Traceability lengths are preserved for telemetry
    assert trace.raw_stt_text_length == len(raw_stt)
    assert trace.safety_gate_passed is True
    assert len(trace.flagged_entities) >= 2


def test_diagnostic_trace_with_explicit_consent():
    """When user explicitly enables developer diagnostics with consent, full values are logged."""
    raw_stt = "email to finance@company.com regarding budget $2.5 million"
    entities = detect_critical_entities(raw_stt)

    trace = create_diagnostic_trace(
        session_id="sess-test-002",
        audio_duration_seconds=2.1,
        raw_stt_text=raw_stt,
        raw_s1_output=raw_stt,
        postprocessed_text=raw_stt,
        delivered_text=raw_stt,
        safety_gate_passed=True,
        safety_reasons=[],
        flagged_entities=entities,
        store_audio_consent=True,
        retain_pii_consent=True,
    )

    assert trace.audio_retained is True
    assert trace.pii_retained is True
    assert "finance@company.com" in trace.raw_stt_text_masked
    assert "$2.5 million" in trace.raw_stt_text_masked


def test_indian_currency_and_lakh_detection():
    """Verify Indian currency amounts like ₹5,50,000 or 5 lakh are detected."""
    text1 = "Transfer ₹5,50,000 plus 18% GST to the vendor."
    entities1 = detect_critical_entities(text1)
    fin1 = [e for e in entities1 if e.entity_type == "financial"]
    assert len(fin1) >= 1
    assert any("5,50,000" in e.original for e in fin1)

    text2 = "Transfer 5 lakh 50 thousand rupees to vendor."
    entities2 = detect_critical_entities(text2)
    fin2 = [e for e in entities2 if e.entity_type == "financial"]
    assert len(fin2) >= 1


def test_invoice_and_identifier_detection():
    """Verify invoice numbers like invoice 8821 are recognized as technical IDs, not generic quantities."""
    text = "Do not transfer funds until Devon confirms invoice 8821 in writing."
    entities = detect_critical_entities(text)
    ids = [e for e in entities if e.entity_type == "id"]
    assert len(ids) >= 1
    assert any("8821" in e.original for e in ids)


def test_datetime_entity_detection():
    """Verify dates and military times like 2300 UTC are detected and flagged."""
    text = "Maintenance begins tonight at 2300 UTC and concludes by 0100 UTC on Wednesday."
    entities = detect_critical_entities(text)
    dt_entities = [e for e in entities if e.entity_type == "datetime"]
    assert len(dt_entities) >= 2
    originals = {e.original for e in dt_entities}
    assert "2300 UTC" in originals
    assert "0100 UTC" in originals


def test_check_user_review_barrier_triggering():
    """Verify that user review barrier triggers on high-risk figures, names, or draft edits."""
    # 1. Phonetic name with Devon/Devin triggers review barrier
    t1 = "Please assign the ticket to Devin Vance."
    trig1, rev1, summary1 = check_user_review_barrier(t1, user_dictionary=["Devon Vance"])
    assert trig1 is True
    assert any(e.entity_type == "name" for e in rev1)

    # 2. Financial amount triggers review barrier
    t2 = "Approved wire transfer of $7,500 to vendor."
    trig2, rev2, summary2 = check_user_review_barrier(t2)
    assert trig2 is True
    assert any(e.entity_type == "financial" for e in rev2)

    # 3. Draft modification triggers review barrier
    t3 = "Let us push the launch to Friday."
    trig3, rev3, summary3 = check_user_review_barrier(t3, task="edit", draft="Our launch is scheduled for Thursday.")
    assert trig3 is True
    assert "Draft modification" in summary3


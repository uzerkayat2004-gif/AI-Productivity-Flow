#!/usr/bin/env python3
"""Build the new frozen independent 42-case evaluation suite.

Covers all 7 VF-1 families (6 cases per family) with diverse natural speech,
complex syntax, varied drafts, and challenging edge cases.
Zero overlap with any training record.
"""
import json
from pathlib import Path

OUTPUT_PATH = Path("data/independent_eval_suite_42.jsonl")


def make_case(cid: str, bucket: str, task: str, target: str,
              transcript: str = "", instruction: str | None = None,
              draft: str | None = None, fmt: str = "prose",
              reg: str = "neutral", tone: str = "neutral", length: str = "same",
              context: str = "general", locale: str = "en-us",
              sender: str | None = None, recipient: str | None = None,
              heightened: list[str] | None = None,
              evaluation_criteria: str = "") -> dict:
    req = {
        "task": task,
        "transcript": transcript,
        "format": fmt,
        "register": reg,
        "tone": tone,
        "length": length,
        "context": context,
        "locale": locale,
    }
    if instruction:
        req["instruction"] = instruction
    if draft:
        req["draft"] = draft
    if sender:
        req["sender"] = sender
    if recipient:
        req["recipient"] = recipient

    return {
        "id": cid,
        "split": "independent_eval",
        "bucket": bucket,
        "contract_revision": "1.2",
        "request": req,
        "reference": target,
        "heightened": heightened or [],
        "evaluation_criteria": evaluation_criteria,
    }


def build_suite() -> list[dict]:
    cases = [
        # =====================================================================
        # FAMILY 1: Speech Cleanup & Self-Corrections (6 cases)
        # =====================================================================
        make_case(
            cid="INDEP-F1-001", bucket="cleanup_facts", task="cleanup",
            transcript="transfer five lakh twenty thousand rupees no wait make that five lakh fifty thousand rupees plus eighteen percent gst to the vendor account",
            target="Transfer ₹5,50,000 plus 18% GST to the vendor account.",
            locale="en-in", heightened=["currency_inr", "self_correction", "percentage"],
            evaluation_criteria="Must resolve self-correction to ₹5,50,000, keep 18% GST, no disfluencies."
        ),
        make_case(
            cid="INDEP-F1-002", bucket="cleanup_facts", task="cleanup",
            transcript="do not transfer the seventy five hundred dollars until devon confirms invoice 8821 in writing",
            target="Do not transfer the $7,500 until Devon confirms invoice 8821 in writing.",
            heightened=["negation", "currency_usd", "condition"],
            evaluation_criteria="Must strictly preserve negation 'Do not transfer', currency $7,500, proper noun Devon, invoice 8821."
        ),
        make_case(
            cid="INDEP-F1-003", bucket="cleanup_facts", task="cleanup",
            transcript="run tail minus f on slash var slash log slash redis slash redis dot log and check for status 503",
            target="Run tail -f on /var/log/redis/redis.log and check for status 503.",
            heightened=["technical_path", "cli_flag", "status_code"],
            evaluation_criteria="Exact path /var/log/redis/redis.log, flag tail -f, status 503."
        ),
        make_case(
            cid="INDEP-F1-004", bucket="cleanup_facts", task="cleanup",
            transcript="uh um so basically let us meet at like ten thirty wait sorry make that eleven fifteen am tomorrow",
            target="Let us meet at 11:15 AM tomorrow.",
            heightened=["self_correction_time", "filler_removal"],
            evaluation_criteria="Strip 'uh um so basically', flip 10:30 to 11:15 AM."
        ),
        make_case(
            cid="INDEP-F1-005", bucket="cleanup_facts", task="cleanup",
            transcript="we need to reschedule the architecture deep dive with dr priya mehta and alex to next thursday october twenty second",
            target="We need to reschedule the architecture deep dive with Dr. Priya Mehta and Alex to next Thursday, October 22nd.",
            heightened=["proper_nouns", "dates"],
            evaluation_criteria="Preserve Dr. Priya Mehta, Alex, Thursday, October 22nd."
        ),
        make_case(
            cid="INDEP-F1-006", bucket="cleanup_facts", task="cleanup",
            transcript="we cannot deploy the hotfix without running the full database migration first",
            target="We cannot deploy the hotfix without running the full database migration first.",
            heightened=["negation_condition"],
            evaluation_criteria="Strictly preserve 'cannot deploy' and 'without running'."
        ),

        # =====================================================================
        # FAMILY 2: Professional Emails & Messages (6 cases)
        # =====================================================================
        make_case(
            cid="INDEP-F2-007", bucket="email", task="rewrite",
            transcript="write an email to the client steering committee letting them know our staging environment is restored and root cause analysis will be delivered by 5 pm marcus",
            target="Subject: Staging Environment Restored & Root Cause Analysis Timeline\n\nDear Client Steering Committee,\n\nPlease be advised that our staging environment has been fully restored. We are currently finalizing the root cause analysis and will deliver the report by 5:00 PM today.\n\nBest regards,\nMarcus",
            fmt="email", reg="formal", sender="Marcus", recipient="Client Steering Committee",
            heightened=["subject_header", "formal_salutation", "sender_signoff"],
            evaluation_criteria="Must have distinct Subject line, formal salutation, body paragraphs, and Marcus sign-off. No placeholder leaks."
        ),
        make_case(
            cid="INDEP-F2-008", bucket="email", task="rewrite",
            transcript="email to all engineering scheduled maintenance window will begin tonight at 2300 utc and conclude by 0100 utc services will experience brief intermittent connectivity",
            target="Subject: Scheduled Maintenance Window: 23:00–01:00 UTC\n\nDear Engineering Team,\n\nPlease be aware that a scheduled maintenance window will begin tonight at 23:00 UTC and conclude by 01:00 UTC. During this period, services may experience brief, intermittent connectivity.\n\nThank you for your understanding.",
            fmt="email", reg="formal", heightened=["subject_separation", "time_window"],
            evaluation_criteria="Must generate Subject, clear body, preserve 23:00–01:00 UTC window."
        ),
        make_case(
            cid="INDEP-F2-009", bucket="email", task="rewrite",
            transcript="remind the vendor that invoice 9904 for 18500 dollars is 15 days overdue please settle by wednesday devon vance",
            target="Subject: Overdue Payment Reminder: Invoice #9904\n\nDear Vendor,\n\nThis is a reminder that invoice #9904 for $18,500 is now 15 days overdue. Please arrange for settlement by Wednesday.\n\nSincerely,\nDevon Vance",
            fmt="email", reg="formal", sender="Devon Vance", heightened=["currency", "dates", "invoice"],
            evaluation_criteria="Subject line, $18,500, 15 days overdue, Wednesday, Devon Vance sign-off."
        ),
        make_case(
            cid="INDEP-F2-010", bucket="messages", task="rewrite",
            transcript="urgent ping to on call engineer latency on payment gateway spiked to 2.4 seconds please investigate redis cache health",
            target="Urgent: Payment gateway latency has spiked to 2.4 seconds. Please investigate Redis cache health immediately.",
            fmt="message", context="work", heightened=["urgency", "metric"],
            evaluation_criteria="Preserve 2.4 seconds, Redis cache, urgent tone."
        ),
        make_case(
            cid="INDEP-F2-011", bucket="messages", task="rewrite",
            transcript="hey elena quick check in are you free for a 15 minute coffee chat at two pm to brainstorm the beta rollout",
            target="Hey Elena, quick check-in: are you free for a 15-minute coffee chat at 2:00 PM to brainstorm the beta rollout?",
            fmt="message", context="personal", tone="friendly", recipient="Elena", heightened=["friendly_tone", "time"],
            evaluation_criteria="Conversational greeting to Elena, 15-minute coffee chat, 2:00 PM."
        ),
        make_case(
            cid="INDEP-F2-012", bucket="email", task="rewrite",
            transcript="hi team proud to announce we officially passed our soc 2 type 2 audit with zero findings congratulations to all",
            target="Subject: We Officially Passed Our SOC 2 Type II Audit!\n\nHi Team,\n\nI am proud to announce that we have officially passed our SOC 2 Type II audit with zero findings. Congratulations to everyone on this outstanding achievement!",
            fmt="email", reg="formal", heightened=["celebratory_subject", "zero_findings"],
            evaluation_criteria="Clear subject line, SOC 2 Type II, zero findings."
        ),

        # =====================================================================
        # FAMILY 3: Actionable AI Prompts (6 cases) - Paraphrased & Varied Syntax
        # =====================================================================
        make_case(
            cid="INDEP-F3-013", bucket="prompt", task="prompt",
            transcript="can you make me a prompt for gpt four that asks it to extract all named entities from an sec 10k filing and return them in json format",
            target="Extract all named entities from the following SEC 10-K filing and return the results as a structured JSON object categorized by company, person, date, and financial metric.",
            fmt="prompt", context="ai", heightened=["meta_wrapper_removal", "json_format", "target_preservation"],
            evaluation_criteria="Must strip 'can you make me a prompt for gpt four that asks it to'. Direct imperative instruction to extract entities in JSON format."
        ),
        make_case(
            cid="INDEP-F3-014", bucket="prompt", task="prompt",
            transcript="tell claude to write a python asyncio script that concurrently scrapes five stock tickers and outputs a pandas dataframe",
            target="Write a Python script using asyncio and aiohttp to concurrently fetch market data for the following five stock tickers and output the consolidated results into a pandas DataFrame.",
            fmt="prompt", context="ai", heightened=["meta_wrapper_removal", "asyncio", "dataframe"],
            evaluation_criteria="Must strip 'tell claude to'. Must direct the model to write Python asyncio script outputting pandas dataframe."
        ),
        make_case(
            cid="INDEP-F3-015", bucket="prompt", task="prompt",
            transcript="i want an instruction for midjourney to render a cyberpunk tea house in neo tokyo in rainy neon lighting",
            target="A cyberpunk tea house in Neo Tokyo illuminated by rainy neon reflections, atmospheric volumetric fog, hyper-detailed architectural rendering, 35mm photograph.",
            fmt="prompt", context="ai", heightened=["image_prompt", "style_preservation"],
            evaluation_criteria="Must strip 'i want an instruction for midjourney to render'. Direct image generation prompt."
        ),
        make_case(
            cid="INDEP-F3-016", bucket="prompt", task="prompt",
            transcript="give me a system prompt for an automated customer support triage assistant that tags urgency and outputs json",
            target="You are an automated customer support triage assistant. For every incoming ticket, classify the issue category, assess urgency as Low, Medium, High, or Critical, and return a structured JSON response.",
            fmt="prompt", context="ai", heightened=["system_prompt_synthesis"],
            evaluation_criteria="Must strip 'give me a system prompt for'. Direct 'You are...' system instruction."
        ),
        make_case(
            cid="INDEP-F3-017", bucket="prompt", task="prompt",
            transcript="could you generate a prompt that tells an ai to explain diffusion models without any mathematical equations",
            target="Explain how diffusion models generate images to an audience without a machine learning background, using visual metaphors like progressive noise removal, and completely avoiding mathematical equations.",
            fmt="prompt", context="ai", heightened=["negative_constraint", "audience"],
            evaluation_criteria="Must strip conversational wrapper. Must retain 'without mathematical equations'."
        ),
        make_case(
            cid="INDEP-F3-018", bucket="prompt", task="prompt",
            transcript="ask the ai to draft an engineering postmortem for a 45 minute redis cache failure",
            target="Draft a detailed engineering postmortem for a 45-minute Redis cache failure. Include an Executive Summary, Incident Timeline in UTC, Root Cause Analysis, Customer Impact, and Action Items.",
            fmt="prompt", context="ai", heightened=["incident_postmortem"],
            evaluation_criteria="Must strip 'ask the ai to'. Direct imperative instruction for postmortem."
        ),

        # =====================================================================
        # FAMILY 4: Lists, Checklists & Action Items (6 cases)
        # =====================================================================
        make_case(
            cid="INDEP-F4-019", bucket="notes_format", task="rewrite",
            transcript="pre flight deployment checklist verify ssl certificates backup production database notify customer success enable feature flag 14",
            target="Pre-flight deployment checklist:\n- Verify SSL certificates\n- Backup production database\n- Notify customer success\n- Enable feature flag 14",
            fmt="bullets", heightened=["action_object_pairing", "no_broken_lines"],
            evaluation_criteria="Action verbs must stay paired with direct objects. No split lines like 'Verify SSL\n- Certificates'."
        ),
        make_case(
            cid="INDEP-F4-020", bucket="notes_format", task="rewrite",
            transcript="conference packing list laptop charger presentation clicker extra hdmi adapter noise cancelling headphones",
            target="- Laptop charger\n- Presentation clicker\n- Extra HDMI adapter\n- Noise cancelling headphones",
            fmt="bullets", heightened=["compound_noun_separation"],
            evaluation_criteria="Keep compound items together on single bullets."
        ),
        make_case(
            cid="INDEP-F4-021", bucket="notes_format", task="rewrite",
            transcript="sprint backlog items first implement authentication middleware second write integration tests third document public api endpoints",
            target="1. Implement authentication middleware\n2. Write integration tests\n3. Document public API endpoints",
            fmt="numbered", heightened=["ordered_sequence"],
            evaluation_criteria="Properly numbered 1, 2, 3 sequence."
        ),
        make_case(
            cid="INDEP-F4-022", bucket="notes_format", task="rewrite",
            transcript="meeting action items elena will review pr 99 devon will update deployment scripts alex will test backup restore",
            target="Action items:\n- Elena: review PR 99\n- Devon: update deployment scripts\n- Alex: test backup restore",
            fmt="bullets", heightened=["owner_assignment"],
            evaluation_criteria="Preserve owner names (Elena, Devon, Alex) and assigned tasks."
        ),
        make_case(
            cid="INDEP-F4-023", bucket="notes_format", task="rewrite",
            transcript="key differentiators local offline execution low memory footprint under one gigabyte zero cloud latency",
            target="Key differentiators:\n- Local offline execution\n- Low memory footprint under 1 GB\n- Zero cloud latency",
            fmt="bullets", heightened=["concise_features"],
            evaluation_criteria="Bullet list with 3 distinct differentiators."
        ),
        make_case(
            cid="INDEP-F4-024", bucket="notes_format", task="rewrite",
            transcript="database recovery procedure first drain traffic from primary node second promote replica third update dns cname",
            target="Database recovery procedure:\n1. Drain traffic from primary node\n2. Promote replica\n3. Update DNS CNAME",
            fmt="numbered", heightened=["procedural_steps"],
            evaluation_criteria="Ordered recovery steps."
        ),

        # =====================================================================
        # FAMILY 5: Summarization (6 cases)
        # =====================================================================
        make_case(
            cid="INDEP-F5-025", bucket="summary", task="summarize",
            transcript="the billing refund bug failed qa testing again on wednesday so the issue remains open alex is continuing root cause investigation and release is postponed to monday",
            target="The billing refund bug failed QA testing Wednesday and remains unresolved. Alex is investigating the root cause; release is postponed to Monday.",
            fmt="prose", length="shorter", heightened=["status_exactness", "pending_preserved", "proper_noun"],
            evaluation_criteria="Crucial: Must preserve that the bug remains unresolved/unfixed. Do not say resolved. Preserve Alex and Monday."
        ),
        make_case(
            cid="INDEP-F5-026", bucket="summary", task="summarize",
            transcript="third quarter financial report arr increased by 34 percent reaching 4.2 million dollars monthly net burn was successfully reduced to 180000 dollars leaving 18 months of runway",
            target="Q3 financials: ARR increased 34% to $4.2M, with monthly net burn reduced to $180,000, extending runway to 18 months.",
            fmt="prose", length="shorter", heightened=["percentages", "currencies", "numbers"],
            evaluation_criteria="Preserve 34%, $4.2M, $180,000, 18 months runway."
        ),
        make_case(
            cid="INDEP-F5-027", bucket="summary", task="summarize",
            transcript="board resolution the directors approved four new engineering hires by december first but froze all marketing agency spend until q1 metrics are evaluated",
            target="Board summary: Approved hiring 4 engineers by December 1st, while freezing marketing agency spend until Q1.",
            fmt="prose", length="shorter", heightened=["deadlines", "conditional_freeze"],
            evaluation_criteria="4 engineers by Dec 1st, marketing spend frozen until Q1."
        ),
        make_case(
            cid="INDEP-F5-028", bucket="summary", task="summarize",
            transcript="incident report dns propagation failure caused a 35 minute partial outage on the us west edge zero customer data was compromised and failover occurred automatically",
            target="Incident summary: DNS failure caused a 35-minute partial outage on US-West. Failover was automatic, and no customer data was compromised.",
            fmt="prose", length="shorter", heightened=["times", "negation"],
            evaluation_criteria="35-minute outage, US-West, zero customer data compromised."
        ),
        make_case(
            cid="INDEP-F5-029", bucket="summary", task="summarize",
            transcript="beta survey feedback 42 users voted for dark mode 19 requested offline mode and 8 noticed occasional audio crackling overall satisfaction rating was 89 percent",
            target="User feedback: 42 requested dark mode, 19 wanted offline mode, and 8 reported audio crackling. Overall satisfaction is 89%.",
            fmt="prose", length="shorter", heightened=["statistics", "exact_counts"],
            evaluation_criteria="Preserve 42, 19, 8, 89%."
        ),
        make_case(
            cid="INDEP-F5-030", bucket="summary", task="summarize",
            transcript="gdpr compliance update telemetry older than 90 days must be permanently deleted from cold storage data protection officer approval is required before running the script",
            target="GDPR update: Telemetry over 90 days must be permanently deleted from cold storage upon DPO approval.",
            fmt="prose", length="shorter", heightened=["compliance", "numbers"],
            evaluation_criteria="Telemetry > 90 days deleted, DPO approval required."
        ),

        # =====================================================================
        # FAMILY 6: Style, Tone & Register Rewriting (6 cases)
        # =====================================================================
        make_case(
            cid="INDEP-F6-031", bucket="followup_style", task="rewrite",
            transcript="your app is totally broken and crashed twice when i was saving my work this is unacceptable",
            target="I encountered two crashes while attempting to save my work, resulting in lost progress. Please investigate this issue promptly.",
            fmt="prose", reg="formal", tone="neutral", heightened=["de_escalation", "professionalism"],
            evaluation_criteria="Convert angry/blunt complaint into constructive, formal bug report."
        ),
        make_case(
            cid="INDEP-F6-032", bucket="followup_style", task="rewrite",
            transcript="yo bro can u send over the deck before tomorrow morning standup thx",
            target="Could you please share the presentation deck prior to tomorrow morning's standup? Thank you.",
            fmt="prose", reg="formal", tone="neutral", heightened=["slang_to_formal"],
            evaluation_criteria="Transform slang into polite, professional workplace communication."
        ),
        make_case(
            cid="INDEP-F6-033", bucket="followup_style", task="rewrite",
            transcript="i will try to deliver the prototype by wednesday but it completely depends on whether legal approves the terms",
            target="I am aiming to deliver the prototype by Wednesday, though this depends entirely on legal approval.",
            fmt="prose", tone="confident", instruction="don't change my promise",
            heightened=["hedge_preserved", "condition_preserved"],
            evaluation_criteria="Must preserve the hedge 'aiming/working to' and condition 'depends on legal approval'."
        ),
        make_case(
            cid="INDEP-F6-034", bucket="followup_style", task="rewrite",
            transcript="we are writing to let you know that in consideration of recent events and following deep analysis we have come to the determination to decline your application",
            target="After careful review, we are unable to accept your application at this time.",
            fmt="prose", length="shorter", heightened=["conciseness", "clarity"],
            evaluation_criteria="Condense verbose prose into a clear, direct, professional sentence."
        ),
        make_case(
            cid="INDEP-F6-035", bucket="followup_style", task="rewrite",
            transcript="we cannot accept your submission because you missed the deadline by two hours",
            target="Thank you for your submission. Unfortunately, we are unable to accept it as it was received after the deadline. We appreciate your effort and interest.",
            fmt="prose", reg="neutral", tone="warm", heightened=["warm_tone", "polite"],
            evaluation_criteria="Rephrase cold rejection with warmth and appreciation while maintaining the boundary."
        ),
        make_case(
            cid="INDEP-F6-036", bucket="followup_style", task="rewrite",
            transcript="unless the vendor signs the dpa before 5 pm today we will terminate the pilot immediately",
            target="Unless the vendor signs the DPA before 5:00 PM today, we will proceed with terminating the pilot program.",
            fmt="prose", tone="confident", heightened=["strict_condition", "deadline"],
            evaluation_criteria="Preserve condition 'Unless vendor signs DPA before 5:00 PM' and consequence."
        ),

        # =====================================================================
        # FAMILY 7: Follow-up Editing (6 cases) - Varied Drafts & Turn Inputs
        # =====================================================================
        make_case(
            cid="INDEP-F7-037", bucket="followup_style", task="edit",
            draft="The product launch is scheduled for Tuesday at 9:00 AM in the main auditorium.",
            instruction="Change Tuesday to Friday and change 9:00 AM to 11:30 AM.",
            transcript="let us push the launch to friday at eleven thirty am instead",
            target="The product launch is scheduled for Friday at 11:30 AM in the main auditorium.",
            fmt="prose", heightened=["draft_preservation", "spoken_transcript_edit"],
            evaluation_criteria="Must apply the date and time change to the draft. Output must be the complete draft with 'Friday at 11:30 AM in the main auditorium'. Must NOT output the instruction as prose."
        ),
        make_case(
            cid="INDEP-F7-038", bucket="followup_style", task="edit",
            draft="Executive briefing with Elena Rostova at 2:00 PM in Boardroom A regarding series A term sheet.",
            instruction="change time to 3:30 pm and add Devon Vance as co-presenter",
            transcript="change the time to three thirty pm and make sure devon vance is listed as co-presenter",
            target="Executive briefing with Elena Rostova and Devon Vance at 3:30 PM in Boardroom A regarding series A term sheet.",
            fmt="prose", heightened=["entity_addition", "time_change"],
            evaluation_criteria="Elena Rostova and Devon Vance at 3:30 PM in Boardroom A regarding series A term sheet."
        ),
        make_case(
            cid="INDEP-F7-039", bucket="followup_style", task="edit",
            draft="Invoice #9920 for $14,000.00 is approved for hardware acquisition. An initial deposit of $4,000 was paid in July.",
            instruction="change the amount to $16,500.00 and delete the sentence about the initial deposit",
            transcript="update amount to sixteen thousand five hundred dollars and remove the initial deposit sentence",
            target="Invoice #9920 for $16,500.00 is approved for hardware acquisition.",
            fmt="prose", heightened=["deletion", "amount_update"],
            evaluation_criteria="Amount updated to $16,500.00; initial deposit sentence completely removed."
        ),
        make_case(
            cid="INDEP-F7-040", bucket="followup_style", task="edit",
            draft="The staging environment is hosted at staging.internal.net on port 8080. Database credentials are in 1Password.",
            instruction="change port 8080 to port 8443 and add that HTTPS is required",
            transcript="switch the port to 8443 and mention https is required",
            target="The staging environment is hosted at staging.internal.net on port 8443. HTTPS is required. Database credentials are in 1Password.",
            fmt="prose", heightened=["port_update", "sentence_insertion"],
            evaluation_criteria="Port 8443, HTTPS required, 1Password credentials sentence preserved."
        ),
        make_case(
            cid="INDEP-F7-041", bucket="followup_style", task="edit",
            draft="You must review PR 305 immediately or the release will be blocked.",
            instruction="make it polite, friendly and professional",
            transcript="soften the draft so it sounds polite and friendly",
            target="Could you please review PR 305 when you have a moment? We appreciate your help unblocking the release.",
            fmt="prose", heightened=["tone_polishing_draft"],
            evaluation_criteria="Soften tone into polite request while retaining PR 305 and unblocking release."
        ),
        make_case(
            cid="INDEP-F7-042", bucket="followup_style", task="edit",
            draft="Sprint 42 Checklist:\n- Deploy auth service\n- Run smoke tests",
            instruction="change Sprint 42 to Sprint 43 and add two items: 'Verify rate limiting' and 'Update API docs'",
            transcript="make it sprint 43 and add verify rate limiting and update api docs to the checklist",
            target="Sprint 43 Checklist:\n- Deploy auth service\n- Run smoke tests\n- Verify rate limiting\n- Update API docs",
            fmt="bullets", heightened=["list_edit", "item_addition"],
            evaluation_criteria="Header updated to Sprint 43; existing items preserved; new items added."
        ),
    ]
    return cases


def main():
    cases = build_suite()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c) + "\n")
    print(f"Independent evaluation suite created: {len(cases)} cases -> {OUTPUT_PATH}")
    print("Family breakdown:")
    families = {}
    for c in cases:
        fam = c["bucket"]
        families[fam] = families.get(fam, 0) + 1
    for fam, count in families.items():
        print(f"  - {fam}: {count} cases")


if __name__ == "__main__":
    main()

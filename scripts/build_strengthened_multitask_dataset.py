#!/usr/bin/env python3
"""Build strengthened VF-1 clean multi-task dataset (v2).

Specifically addresses the two documented generalization weaknesses:
1. AI Prompt Synthesis:
   - Paraphrased and varied conversational meta-wrappers:
     "can you make me a prompt for", "tell Claude to", "I want an instruction for",
     "write me a prompt asking", "give me a prompt to", "could you generate a prompt that",
     "ask GPT to", "I need a prompt for".
   - Target is direct, actionable imperative instructions preserving all formats, constraints, and entities.
2. Follow-Up Editing:
   - Handles spoken edit instructions whether passed in [Instruction], [Transcript], or both.
   - Covers replacements, additions, deletions, tone adjustments, and multi-field edits.
   - Strict preservation of unchanged draft content.

Preserves 100% legal clearance: 0 Hark teacher data, Apache-2.0 clean.
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "clean_vf1"

PROMPT_VARIATIONS = [
    # 1. "can you make me a prompt for [model] that asks it to..."
    ("can you make me a prompt for gpt four that asks it to extract all named entities from an sec 10k filing and return them in json format",
     "Extract all named entities from the provided SEC 10-K filing and return the results as a structured JSON object categorized by company, person, date, and financial metric."),

    ("can you make me a prompt for claude that asks it to summarize this 20 page whitepaper into five key takeaways for an executive",
     "Summarize the provided whitepaper into exactly five concise executive takeaways, highlighting strategic implications, technical architecture, and implementation risks."),

    # 2. "tell [model] to..."
    ("tell chatgpt to generate a python fast api endpoint with pydantic validation for registering a new user with email and password",
     "Create a FastAPI endpoint in Python that registers a new user with email and password. Use Pydantic models for request validation and include error handling for duplicate emails."),

    ("tell claude to refactor this react component from class syntax to functional hooks with typescript",
     "Refactor the provided React class component into a modern functional component using TypeScript, converting state and lifecycle methods to useState and useEffect hooks."),

    # 3. "I want an instruction for [model] to..."
    ("i want an instruction for midjourney to generate a photorealistic portrait of an elderly watchmaker working in a rustic workshop at golden hour",
     "A photorealistic close-up portrait of an elderly watchmaker repairing an intricate mechanical watch in a rustic workshop, illuminated by warm golden hour sunlight through a dusty window, 35mm lens, 8k resolution, cinematic lighting."),

    ("i want an instruction for an ai agent to audit a smart contract for reentrancy vulnerabilities and gas inefficiencies",
     "Audit the provided Solidity smart contract specifically for reentrancy vulnerabilities, unchecked external calls, integer overflow edge cases, and gas optimization opportunities."),

    # 4. "write me a prompt asking [model] to..."
    ("write me a prompt asking the model to explain how paxos consensus works compared to raft using a simple dining philosophers analogy",
     "Explain the fundamental differences between Paxos and Raft consensus algorithms using a clear analogy, focusing on leader election, log replication, and split-brain resolution."),

    ("write me a prompt asking claude to draft a series a investor update email with sections on revenue growth burn rate and product milestones",
     "Draft a professional Series A investor update email with structured sections covering Monthly Recurring Revenue growth, runway and net burn, key product milestones, and upcoming hiring goals."),

    # 5. "give me a prompt to..."
    ("give me a prompt to generate unit tests for a stripe webhook handler in go",
     "Write comprehensive unit tests in Go for a Stripe webhook handler, covering signature verification, invoice.payment_succeeded events, customer.subscription_deleted events, and idempotency handling."),

    ("give me a prompt to compare postgresql and mongodb for a real time chat application",
     "Compare PostgreSQL and MongoDB for powering a real-time messaging application, evaluating connection scalability, schema flexibility, read/write latency under concurrency, and operational maintenance."),

    # 6. "could you write a prompt that tells an AI to..."
    ("could you write a prompt that tells an ai to translate this legal nondisclosure agreement into plain plain english for a non lawyer",
     "Translate the following non-disclosure agreement into plain, accessible English, explaining each party's obligations, definition of confidential information, duration, and legal remedies without legalese."),

    ("could you write a prompt that instructs an llm to format customer support transcripts into structured bug reports with repro steps",
     "Analyze the provided customer support chat transcript and extract a structured bug report containing Title, Severity, Steps to Reproduce, Expected Behavior, Actual Behavior, and Environment Details."),

    # 7. "make a prompt that asks [model] to..."
    ("make a prompt that asks gpt to write a high converting cold outreach email for a b2b devops monitoring platform",
     "Write a concise, compelling B2B cold outreach email to engineering directors introducing a real-time DevOps observability platform. Keep it under 100 words, lead with a common pain point around alert fatigue, and end with a low-friction call to action."),

    ("make a prompt to design an event driven microservices architecture for a ride hailing platform",
     "Design an event-driven microservices architecture for a ride-hailing platform using Kafka, detailing services for rider matching, driver location tracking, pricing/billing, and trip lifecycle events."),

    # 8. "ask [model] to..."
    ("ask the ai to draft a comprehensive incident postmortem for a three hour database outage",
     "Draft an internal engineering postmortem for a three-hour production database outage. Include Executive Summary, Timeline of Events (UTC), Root Cause Analysis (Five Whys), Impact Assessment, Immediate Mitigations, and Long-Term Preventative Action Items with owners."),

    ("ask claude to generate a mock interview question set for a senior distributed systems engineer focusing on consistency models",
     "Generate 5 rigorous technical interview questions for a Senior Distributed Systems Engineer focusing on linearizability, eventual consistency, quorum reads/writes, and the CAP theorem, along with expected evaluation criteria."),

    # 9. "I need a prompt for..."
    ("i need a prompt for writing a pull request description that summarizes changes in authentication logic and lists testing steps",
     "Write a clear, structured GitHub pull request description summarizing architectural changes to the authentication middleware. Include sections for Summary of Changes, Motivation/Context, Breaking Changes, and Testing Instructions."),

    ("i need a prompt to explain transformers self attention mechanism to a junior developer without matrix math",
     "Explain the self-attention mechanism in Transformer neural networks to a junior developer using visual and conceptual analogies, avoiding heavy matrix multiplication equations."),

    # 10. "generate a system prompt that instructs..."
    ("generate a system prompt that instructs an ai assistant to act as a strict python code reviewer focusing on pep eight and security",
     "You are a rigorous Python code reviewer. Your role is to enforce strict PEP 8 style standards, type annotation correctness, and identify potential security flaws such as SQL injection, shell execution risks, and insecure deserialization. Provide concise inline recommendations."),

    ("generate a system prompt for a triage bot that classifies customer tickets into billing technical or sales and tags urgency",
     "You are an automated support ticket triage assistant. For each customer message, output a JSON response containing 'category' (billing, technical, sales), 'urgency' (low, medium, high, critical), and a one-sentence 'summary'."),

    # 11-15 Diverse prompt tasks
    ("create a prompt for writing a sql query to find churned subscribers who spent over five hundred dollars",
     "Write an optimized SQL query to identify users whose subscription lapsed in the last 60 days and whose lifetime spend exceeds $500. Include customer ID, last active date, and total amount spent."),

    ("build a prompt to generate kubernetes deployment manifests with resource limits and readiness probes",
     "Generate production-ready Kubernetes deployment and service YAML manifests for a stateless Node.js application, including CPU/memory requests and limits, liveness and readiness HTTP probes, and horizontal pod autoscaler settings."),

    ("make me a prompt asking an ai to rewrite this technical changelog into user facing release notes",
     "Rewrite the following git commit log and technical changelog into exciting, user-friendly release notes suitable for a public product blog. Group updates by New Features, Improvements, and Bug Fixes."),

    ("tell the model to optimize this slow database query with an index recommendation",
     "Analyze the provided slow SQL query and table schema. Explain the execution bottlenecks and recommend appropriate B-tree or partial indexes to accelerate performance."),

    ("can you write a prompt that asks for a comparison of flutter and react native for a cross platform fintech app",
     "Provide an in-depth comparison of Flutter versus React Native for developing a cross-platform mobile fintech application, focusing on security compliance, native biometric integration, third-party library stability, and long-term maintainability."),
]

EDIT_VARIATIONS = [
    # 1. Spoken instruction in [Instruction], [Transcript] empty
    ("The team sync is scheduled for Wednesday at 10:00 AM in Conference Room 3.",
     "change Wednesday to Thursday and change Conference Room 3 to Room 5",
     "",
     "The team sync is scheduled for Thursday at 10:00 AM in Room 5."),

    ("We currently support English, Spanish, and French in our mobile application.",
     "add German and Japanese to the list of languages",
     "",
     "We currently support English, Spanish, French, German, and Japanese in our mobile application."),

    ("The standard tier costs $29 per month and includes 10 GB of cloud storage with email support.",
     "change $29 to $39 and increase storage to 25 GB",
     "",
     "The standard tier costs $39 per month and includes 25 GB of cloud storage with email support."),

    ("Please ensure all pull requests are reviewed by at least one engineer before merging to develop.",
     "change develop to main and require two engineers instead of one",
     "",
     "Please ensure all pull requests are reviewed by at least two engineers before merging to main."),

    ("The quarterly board meeting will take place in Chicago on November 12th.",
     "change Chicago to Boston and move the date to November 18th",
     "",
     "The quarterly board meeting will take place in Boston on November 18th."),

    # 2. Spoken instruction in [Transcript], [Instruction] empty or mirror
    ("The product launch is scheduled for Tuesday at 9:00 AM in the main auditorium.",
     "Change Tuesday to Friday and change 9:00 AM to 11:30 AM.",
     "let's push the launch to friday at eleven thirty am instead",
     "The product launch is scheduled for Friday at 11:30 AM in the main auditorium."),

    ("Executive briefing with Elena Rostova at 2:00 PM in Boardroom A regarding series A term sheet.",
     "change time to 3:30 pm and add Devon Vance as co-presenter",
     "change the time to three thirty pm and make sure devon vance is listed as co-presenter",
     "Executive briefing with Elena Rostova and Devon Vance at 3:30 PM in Boardroom A regarding series A term sheet."),

    ("Please wire $12,000 to invoice 4092 by Friday afternoon.",
     "change amount to $14,500 and wire to invoice 4095",
     "actually wire fourteen thousand five hundred dollars to invoice 4095 instead",
     "Please wire $14,500 to invoice 4095 by Friday afternoon."),

    ("Our office will be closed on Monday for Labor Day. Support tickets will be answered on Tuesday.",
     "change Labor Day to Memorial Day and note emergency support is available",
     "change labor day to memorial day and add that emergency support remains available",
     "Our office will be closed on Monday for Memorial Day. Support tickets will be answered on Tuesday, though emergency support remains available."),

    ("The API rate limit is 100 requests per minute for free tier users.",
     "increase rate limit to 250 requests per minute",
     "bump the rate limit to two hundred fifty requests per minute for free users",
     "The API rate limit is 250 requests per minute for free tier users."),

    # 3. Deletions and removals
    ("We are excited to announce our new beta program. Legacy users will receive automatic migration. Custom plugins will be deprecated on December 1st.",
     "remove the sentence about custom plugins being deprecated",
     "remove the part about custom plugins",
     "We are excited to announce our new beta program. Legacy users will receive automatic migration."),

    ("Invoice #5512 for $8,200.00 is due on October 31st. A 5% late fee applies after 10 days. Payment can be made via check or wire transfer.",
     "remove the late fee sentence",
     "take out the late fee mention",
     "Invoice #5512 for $8,200.00 is due on October 31st. Payment can be made via check or wire transfer."),

    # 4. Tone and style revisions on existing draft
    ("Hey team you guys need to test your code before pushing because the staging server keeps crashing.",
     "make it professional and constructive",
     "rewrite this so it sounds professional and constructive for the team",
     "Team, please ensure all code is thoroughly tested locally prior to pushing, as we have experienced instability on the staging server."),

    ("We cannot give you a refund because our policy strictly prohibits refunds after 14 days.",
     "make it polite and empathetic while maintaining the policy",
     "soften the tone and make it polite",
     "While we understand your situation, we are unfortunately unable to issue a refund as our policy limits returns to within 14 days of purchase."),

    # 5. Condensation and shortening
    ("In order to ensure that our database operates with the highest possible level of reliability, we will be performing scheduled maintenance this Saturday evening starting at 11 PM and concluding by 3 AM Sunday.",
     "make it concise and direct",
     "shorten this to one clear sentence",
     "Scheduled database maintenance will occur this Saturday from 11:00 PM to 3:00 AM Sunday."),

    # 6. Additions of disclaimers, attendees, or requirements
    ("All attendees must check in at the reception desk on the 2nd floor.",
     "add that photo ID is required for entry",
     "add that a valid photo id is required for entry",
     "All attendees must check in at the reception desk on the 2nd floor. A valid photo ID is required for entry."),

    ("The deployment to production is approved for tonight at midnight.",
     "add that on-call engineers must monitor Datadog alerts for one hour post-deploy",
     "add that on-call engineers must monitor datadog alerts for one hour after deployment",
     "The deployment to production is approved for tonight at midnight. On-call engineers must monitor Datadog alerts for one hour post-deployment."),

    ("Dear Client, we have completed the initial architectural review of your mobile application.",
     "add a sentence stating the full report is attached as a PDF",
     "mention that the full report is attached as a pdf",
     "Dear Client,\n\nWe have completed the initial architectural review of your mobile application. The full report is attached as a PDF for your review."),

    # 7. Multi-field revisions
    ("Sprint 42 will start on Monday with 5 engineers assigned to the checkout redesign.",
     "change Sprint 42 to Sprint 43, change Monday to Wednesday, and change 5 engineers to 6 engineers",
     "update sprint 42 to 43 start wednesday with six engineers",
     "Sprint 43 will start on Wednesday with 6 engineers assigned to the checkout redesign."),

    ("The training session will be hosted by Sarah Jenkins on Zoom at 1:00 PM.",
     "change host to Marcus Chen, platform to Google Meet, and time to 2:30 PM",
     "change host to marcus chen on google meet at two thirty pm",
     "The training session will be hosted by Marcus Chen on Google Meet at 2:30 PM."),
]


def make_record(rid: str, split: str, bucket: str, task: str, target: str,
                transcript: str = "", instruction: str | None = None,
                draft: str | None = None, fmt: str = "prose",
                reg: str = "neutral", tone: str = "neutral", length: str = "same",
                context: str = "general", locale: str = "en-us",
                sender: str | None = None, recipient: str | None = None,
                heightened: list[str] | None = None) -> dict:
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
        "id": rid,
        "split": split,
        "bucket": bucket,
        "slice": "common",
        "contract_revision": "1.2",
        "request": req,
        "target": target,
        "review": {
            "status": "accepted",
            "heightened": heightened or [],
            "notes": "Independently authored clean multi-task synthetic training record",
        },
        "provenance": {
            "author": "clean-programmatic-vf1-engine-v2",
            "method": "rule_based_synthetic",
            "teacher": None,
            "uses_s1_output": False,
            "source": "deterministic procedural templates strictly conforming to VF-1 universal contract v1.2",
        },
    }


def main():
    print("=" * 70)
    print("BUILDING STRENGTHENED VF-1 MULTI-TASK DATASET (v2)")
    print("=" * 70)

    # 1. Load existing clean training and val records
    old_train_path = DATA_DIR / "clean_corpus_train.jsonl"
    old_train = [json.loads(l) for l in open(old_train_path, encoding="utf-8") if l.strip()]
    old_val_path = DATA_DIR / "clean_corpus_val.jsonl"
    old_val = [json.loads(l) for l in open(old_val_path, encoding="utf-8") if l.strip()]

    print(f"Existing clean train: {len(old_train)} records")
    print(f"Existing clean val:   {len(old_val)} records")

    # 2. Generate new prompt synthesis records
    new_prompts_train = []
    new_prompts_val = []
    for i, (text_in, tgt) in enumerate(PROMPT_VARIATIONS):
        rid = f"STRENGTH-F3-{i+1:04d}"
        split = "validation" if i < 4 else "train"
        rec = make_record(
            rid=rid, split=split, bucket="prompt", task="prompt", target=tgt,
            transcript=text_in, fmt="prompt", context="ai",
            heightened=["actionable_prompt", "meta_wrapper_stripped", "paraphrased_command"]
        )
        if split == "train":
            new_prompts_train.append(rec)
        else:
            new_prompts_val.append(rec)

    # 3. Generate new follow-up editing records
    new_edits_train = []
    new_edits_val = []
    for i, (draft, instr, trans, tgt) in enumerate(EDIT_VARIATIONS):
        rid = f"STRENGTH-F7-{i+1:04d}"
        split = "validation" if i < 4 else "train"
        rec = make_record(
            rid=rid, split=split, bucket="followup_style", task="edit", target=tgt,
            transcript=trans, instruction=instr, draft=draft, fmt="prose",
            heightened=["surgical_draft_edit", "complete_draft_preserved"]
        )
        if split == "train":
            new_edits_train.append(rec)
        else:
            new_edits_val.append(rec)

    print(f"Added {len(new_prompts_train)} train / {len(new_prompts_val)} val prompt synthesis records.")
    print(f"Added {len(new_edits_train)} train / {len(new_edits_val)} val follow-up edit records.")

    # 4. Combine into strengthened dataset
    combined_train = old_train + new_prompts_train + new_edits_train
    combined_val = old_val + new_prompts_val + new_edits_val

    # Write out updated dataset files
    train_out = DATA_DIR / "clean_corpus_train.jsonl"
    val_out = DATA_DIR / "clean_corpus_val.jsonl"
    comb_out = DATA_DIR / "clean_corpus_combined.jsonl"

    with open(train_out, "w", encoding="utf-8") as f:
        for r in combined_train:
            f.write(json.dumps(r) + "\n")

    with open(val_out, "w", encoding="utf-8") as f:
        for r in combined_val:
            f.write(json.dumps(r) + "\n")

    with open(comb_out, "w", encoding="utf-8") as f:
        for r in combined_train + combined_val:
            f.write(json.dumps(r) + "\n")

    print(f"\nFinal Strengthened Train Corpus: {len(combined_train)} records ({train_out})")
    print(f"Final Strengthened Val Corpus:   {len(combined_val)} records ({val_out})")
    print(f"Final Combined Corpus:          {len(combined_train) + len(combined_val)} records ({comb_out})")


if __name__ == "__main__":
    main()

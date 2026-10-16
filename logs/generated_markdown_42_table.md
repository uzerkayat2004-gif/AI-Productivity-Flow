| `INDEP-F1-001` | cleanup_facts | Must resolve self-correction to ₹5,50,00 | **FAIL** | **PASS** | **PASS** | **PASS** | **PASS** | Critical factual errors (failed_inr_self_correction_missing_550k) |
| `INDEP-F1-002` | cleanup_facts | Must strictly preserve negation 'Do not  | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F1-003` | cleanup_facts | Exact path /var/log/redis/redis.log, fla | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F1-004` | cleanup_facts | Strip 'uh um so basically', flip 10:30 t | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F1-005` | cleanup_facts | Preserve Dr. Priya Mehta, Alex, Thursday | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F1-006` | cleanup_facts | Strictly preserve 'cannot deploy' and 'w | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F2-007` | email | Must have distinct Subject line, formal  | **FAIL** | **PASS** | **PASS** | **PASS** | **FAIL** | Missing task compliance (missing_subject_header) |
| `INDEP-F2-008` | email | Must generate Subject, clear body, prese | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** | Critical factual errors (missing_2300_or_0100_maintenance_hours) |
| `INDEP-F2-009` | email | Subject line, $18,500, 15 days overdue,  | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** | Formatting defects (missing_subject_header) |
| `INDEP-F2-010` | messages | Preserve 2.4 seconds, Redis cache, urgen | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F2-011` | messages | Conversational greeting to Elena, 15-min | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F2-012` | email | Clear subject line, SOC 2 Type II, zero  | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** | Formatting defects (missing_subject_header) |
| `INDEP-F3-013` | prompt | Must strip 'can you make me a prompt for | **FAIL** | **FAIL** | **FAIL** | **PASS** | **FAIL** | Missing task compliance (echoed_conversational_request) |
| `INDEP-F3-014` | prompt | Must strip 'tell claude to'. Must direct | **FAIL** | **PASS** | **PASS** | **PASS** | **PASS** | Missing task compliance (echoed_conversational_request) |
| `INDEP-F3-015` | prompt | Must strip 'i want an instruction for mi | **FAIL** | **PASS** | **PASS** | **PASS** | **PASS** | Missing task compliance (echoed_conversational_request) |
| `INDEP-F3-016` | prompt | Must strip 'give me a system prompt for' | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F3-017` | prompt | Must strip conversational wrapper. Must  | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **PASS** | Critical factual errors (missing_diffusion_or_no_math_constraint) |
| `INDEP-F3-018` | prompt | Must strip 'ask the ai to'. Direct imper | **FAIL** | **PASS** | **PASS** | **PASS** | **PASS** | Missing task compliance (echoed_conversational_request) |
| `INDEP-F4-019` | notes_format | Action verbs must stay paired with direc | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F4-020` | notes_format | Keep compound items together on single b | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F4-021` | notes_format | Properly numbered 1, 2, 3 sequence. | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F4-022` | notes_format | Preserve owner names (Elena, Devon, Alex | **PASS** | **PASS** | **PASS** | **FAIL** | **FAIL** | Critical factual errors (missing_owners_or_pr99) |
| `INDEP-F4-023` | notes_format | Bullet list with 3 distinct differentiat | **PASS** | **FAIL** | **FAIL** | **FAIL** | **FAIL** | Critical factual errors (missing_offline_or_1gb_bound) |
| `INDEP-F4-024` | notes_format | Ordered recovery steps. | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F5-025` | summary | Crucial: Must preserve that the bug rema | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F5-026` | summary | Preserve 34%, $4.2M, $180,000, 18 months | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F5-027` | summary | 4 engineers by Dec 1st, marketing spend  | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F5-028` | summary | 35-minute outage, US-West, zero customer | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F5-029` | summary | Preserve 42, 19, 8, 89%. | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F5-030` | summary | Telemetry > 90 days deleted, DPO approva | **PASS** | **FAIL** | **FAIL** | **PASS** | **FAIL** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F6-031` | followup_style | Convert angry/blunt complaint into const | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F6-032` | followup_style | Transform slang into polite, professiona | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F6-033` | followup_style | Must preserve the hedge 'aiming/working  | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F6-034` | followup_style | Condense verbose prose into a clear, dir | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F6-035` | followup_style | Rephrase cold rejection with warmth and  | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F6-036` | followup_style | Preserve condition 'Unless vendor signs  | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | Acceptable semantic paraphrases (compliant) |
| `INDEP-F7-037` | followup_style | Must apply the date and time change to t | **FAIL** | **PASS** | **PASS** | **PASS** | **PASS** | Missing task compliance (dropped_draft_auditorium_location) |
| `INDEP-F7-038` | followup_style | Elena Rostova and Devon Vance at 3:30 PM | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** | Critical factual errors (failed_to_add_devon_or_330pm) |
| `INDEP-F7-039` | followup_style | Amount updated to $16,500.00; initial de | **FAIL** | **FAIL** | **FAIL** | **FAIL** | **FAIL** | Missing task compliance (failed_to_delete_deposit_sentence) |
| `INDEP-F7-040` | followup_style | Port 8443, HTTPS required, 1Password cre | **FAIL** | **PASS** | **PASS** | **FAIL** | **PASS** | Missing task compliance (dropped_draft_staging_url_or_1password) |
| `INDEP-F7-041` | followup_style | Soften tone into polite request while re | **FAIL** | **PASS** | **PASS** | **FAIL** | **PASS** | Critical factual errors (dropped_pr305_id) |
| `INDEP-F7-042` | followup_style | Header updated to Sprint 43; existing it | **FAIL** | **PASS** | **PASS** | **PASS** | **PASS** | Missing task compliance (dropped_existing_draft_checklist_items) |
# W14 stage 2, part 3 (TC-W14-171..205). Executed by W14.py; uses R2, FE, NL, MC.

# ------------------------------------------------------------ follow-up edits (task=edit)

# 171 recruitment: the canonical follow-up: more confident, conditional commitment unchanged
R2(FE, {"task": "edit", "header_style": "full",
        "draft": "Hi Anjali,\n\nJust a quick note in case it's useful: we have a shortlist ready for the store manager role. "
                 "If you can confirm the salary band by Thursday, we will send you three profiles on Friday morning. "
                 "Hopefully that works!\n\nAll three candidates have at least four years of retail management experience, "
                 "and two of them are already based in the city.\n\nBest,\nObinna",
        "instruction": "actually, rewrite the previous draft with a more confident tone but keep the conditional commitment unchanged"},
   "Hi Anjali,\n\nWe have a shortlist ready for the store manager role. If you can confirm the salary band by Thursday, "
   "we will send you three profiles on Friday morning.\n\nAll three candidates have at least four years of retail management "
   "experience, and two of them are already based in the city.\n\nBest,\nObinna",
   {"format": "email",
    "must_include": ["Anjali", "shortlist ready for the store manager role",
                     "If you can confirm the salary band by Thursday, we will send you three profiles on Friday morning",
                     "at least four years of retail management experience", "two of them are already based in the city", "Obinna"],
    "must_not_include": ["in case it's useful", "Hopefully"]},
   "facts: shortlist ready; conditional commitment 'If you can confirm the salary band by Thursday, we will send you three profiles on Friday morning' kept verbatim; candidate paragraph (at least four years retail management, two already in the city) byte-identical; only the 'in case it's useful' and 'Hopefully that works' softeners removed")

# 172 landscaping: shorter, condition kept in its own sentence (long)
R2(FE, {"task": "edit",
        "draft": "Hi everyone, so just to keep you all in the loop, the irrigation system at the Fernhill office park is "
                 "going to be shut off from Monday to Wednesday next week while we replace the main valve, which means the "
                 "lawns won't get watered for those three days, so if it's really hot, Martin will come by with the hose "
                 "cart on Tuesday afternoon to give the flower beds a soak.",
        "instruction": "make it shorter"},
   "Hi everyone, the irrigation system at the Fernhill office park will be shut off from Monday to Wednesday next week "
   "while we replace the main valve, so the lawns won't get watered for those three days. If it's really hot, Martin will "
   "come by with the hose cart on Tuesday afternoon to soak the flower beds.",
   {"min_negations": 1,
    "must_include": ["Hi everyone", "Fernhill office park", "Monday to Wednesday next week", "main valve", "lawns won't get watered",
                     "three days", "If it's really hot, Martin will come by", "hose cart on Tuesday afternoon", "flower beds"]},
   "facts: irrigation off Monday-Wednesday next week for the main valve; lawns NOT watered those three days; Martin's Tuesday-afternoon hose-cart visit stays conditional on it being really hot")

# 173 party rentals: two linked corrections (facts correct)
R2(FE, {"task": "edit", "facts": "correct",
        "draft": "80 Chiavari chairs at $4 each comes to $320, plus a $40 delivery fee.",
        "instruction": "the chairs are $4.50 each, so the total is $360, fix both"},
   "80 Chiavari chairs at $4.50 each comes to $360, plus a $40 delivery fee.",
   {"numbers": ["80", "4.50", "360", "40"], "must_include": ["80 Chiavari chairs", "$4.50 each", "$360", "$40 delivery fee"],
    "must_not_include": ["$320", "$4 each"]},
   "facts: exactly two authorised changes: $4 -> $4.50 each and $320 -> $360; 80 chairs and $40 delivery fee unchanged")

# 174 nonprofit grants: remove what was said about the budget
R2(FE, {"task": "edit",
        "draft": "Hi Kwame,\n\nThe foundation's program officer called this morning. She liked our draft, and she said the "
                 "budget looks a little high for a first-year grant, but it's not a deal-breaker.\n\nShe also wants us to "
                 "add a paragraph on how we'll measure attendance. Can you write that by Wednesday?\n\nThanks,\nSelin",
        "instruction": "remove what she said about the budget"},
   "Hi Kwame,\n\nThe foundation's program officer called this morning. She liked our draft.\n\nShe also wants us to add a "
   "paragraph on how we'll measure attendance. Can you write that by Wednesday?\n\nThanks,\nSelin",
   {"format": "email",
    "must_include": ["Kwame", "program officer called this morning", "She liked our draft", "measure attendance", "by Wednesday?", "Selin"],
    "must_not_include": ["budget", "deal-breaker"]},
   "facts: budget remark removed as instructed; call this morning, she liked the draft, wants an attendance-measurement paragraph, question to Kwame about Wednesday all unchanged. "
   "Waivers negation_lost + number_missing: the only negation ('not a deal-breaker') and the 'first' of 'first-year grant' (read as 1) were inside the removed budget remark",
   waivers=["negation_lost", "number_missing"])

# 175 event agency: costs into a bullet list under the intro
R2(FE, {"task": "edit",
        "draft": "For the team offsite we've spent $1,200 on the venue, $860 on catering, $300 on the coach and $150 on "
                 "name badges and printing.",
        "instruction": "make it a bullet list with the cost after each item, keep the intro"},
   "For the team offsite we've spent:\n- Venue: $1,200\n- Catering: $860\n- Coach: $300\n- Name badges and printing: $150",
   {"format": "bullets", "numbers": ["1,200", "860", "300", "150"],
    "must_include": ["team offsite", "- Venue: $1,200", "- Catering: $860", "- Coach: $300", "- Name badges and printing: $150"]},
   "facts: venue $1,200, catering $860, coach $300, badges + printing $150; intro kept as lead line; no total added")

# 176 facilities: formal + requested subject line, negation and percentage kept
R2(FE, {"task": "edit",
        "draft": "Hey Margaux, our cleaning contract with you ends on Jan 31. We'd like to renew for another year but at "
                 "the same rate, not the 8% increase you mentioned.",
        "instruction": "make it formal and add a subject line saying service contract renewal"},
   "Subject: Service contract renewal\n\nDear Margaux,\n\nOur cleaning contract with you ends on January 31. We would like "
   "to renew for another year, but at the same rate, not with the 8% increase you mentioned.",
   {"format": "email", "numbers": ["31", "8"], "min_negations": 1,
    "must_include": ["Subject: Service contract renewal", "Dear Margaux", "cleaning contract", "January 31", "renew for another year",
                     "same rate", "8% increase you mentioned"]},
   "facts: contract ends January 31; renew one more year at the same rate, NOT with the 8% increase; dictated 'Hey' adapted to formal 'Dear'; Subject line from the instruction; no sign-off (no sender given). "
   "Waiver invented_subject: the Subject line is requested in the instruction (known checker gap)",
   waivers=["invented_subject"])

# 177 SaaS: grammar only, links untouched
R2(FE, {"task": "edit",
        "draft": "The new pricing page are live at https://app.tallyroute.io/pricing and the old link redirect there "
                 "automatically. Customer who bookmarked /plans will land on the same page.",
        "instruction": "fix the grammar, but don't touch the links"},
   "The new pricing page is live at https://app.tallyroute.io/pricing, and the old link redirects there automatically. "
   "Customers who bookmarked /plans will land on the same page.",
   {"must_include": ["https://app.tallyroute.io/pricing", "/plans", "redirects there automatically", "Customers who bookmarked"]},
   "facts: pricing page live at https://app.tallyroute.io/pricing (literal unchanged); old link redirects; /plans bookmarks land on the same page; only agreement errors fixed")

# 178 podcast: request moved to the front
R2(FE, {"task": "edit",
        "draft": "Hi Elin, we've finished editing your episode and it's scheduled for the 2nd. We cut the section about "
                 "your previous employer, as you asked. Could you send us a 30-second promo clip by Sunday?",
        "instruction": "put the request first, then the rest"},
   "Hi Elin, could you send us a 30-second promo clip by Sunday? We've finished editing your episode and it's scheduled for "
   "the 2nd. We cut the section about your previous employer, as you asked.",
   {"numbers": ["30", "2"],
    "must_include": ["Hi Elin", "30-second promo clip by Sunday?", "scheduled for the 2nd", "section about your previous employer", "as you asked"]},
   "facts: request (30-second promo clip by Sunday) moved first; episode edited, scheduled the 2nd; previous-employer section cut as she asked")

# 179 event agency en-in: code-mixed, shorter, no translation
R2(FE, {"task": "edit", "locale": "en-in",
        "draft": "Bhai, Saturday wale event ke liye sound system aur 2 mics chahiye, aur ek extra speaker bhi le aana "
                 "kyunki hall bada hai, aur haan setup 3 baje tak ho jana chahiye kyunki guests 4 baje aane lagenge.",
        "instruction": "make it shorter, keep it in hinglish"},
   "Bhai, Saturday wale event ke liye sound system, 2 mics aur ek extra speaker chahiye, kyunki hall bada hai. Setup 3 baje "
   "tak ho jana chahiye, kyunki guests 4 baje aane lagenge.",
   {"numbers": ["2", "3", "4"],
    "must_include": ["Bhai", "Saturday wale event", "sound system", "2 mics", "ek extra speaker", "hall bada hai", "Setup 3 baje tak", "guests 4 baje aane lagenge"]},
   "facts: for Saturday's event: sound system, 2 mics, one extra speaker (hall is big); setup done by 3 because guests arrive from 4; Hinglish kept, nothing translated")

# 180 personal admin: friendlier, 'unless' kept with its scope
R2(FE, {"task": "edit",
        "draft": "We'll be cutting the shared hedge Saturday morning unless you object by Thursday. Clippings will be removed "
                 "same day.",
        "instruction": "friendlier please, but keep the unless part"},
   "Just a heads-up: we'll be cutting the shared hedge on Saturday morning, unless you have any objections by Thursday. "
   "We'll clear away the clippings the same day.",
   {"must_include": ["shared hedge on Saturday morning", "unless you have any objections by Thursday", "clippings the same day"]},
   "facts: hedge cut Saturday morning UNLESS objection by Thursday (condition kept); clippings removed same day; commitment kept as 'we'll', not softened to a plan")

# 181 SaaS: terse note -> proper team message, nothing new
R2(FE, {"task": "edit",
        "draft": "Renewal call moved to Wed 3 p.m. Bring usage report.",
        "instruction": "expand this into a proper message to the team, nothing new"},
   "The renewal call has moved to Wednesday at 3 p.m. Please bring the usage report.",
   {"numbers": ["3"], "must_include": ["renewal call", "Wednesday at 3 p.m.", "usage report"]},
   "facts: renewal call moved to Wednesday 3 p.m.; bring the usage report; no new facts")

# 182 facilities: spell out casual abbreviations, keep HVAC
R2(FE, {"task": "edit",
        "draft": "FYI HVAC tech arrives at 7, pls keep the boiler room unlocked. Need the access card back by EOD.",
        "instruction": "spell out the casual abbreviations but keep HVAC as it is"},
   "For your information, HVAC tech arrives at 7, please keep the boiler room unlocked. Need the access card back by end of day.",
   {"numbers": ["7"], "must_include": ["For your information", "HVAC tech arrives at 7", "please keep the boiler room unlocked", "access card back by end of day"],
    "must_not_include": ["FYI", "pls", "EOD"]},
   "facts: HVAC tech at 7; boiler room unlocked; access card back by end of day; only FYI/pls/EOD expanded, HVAC kept")

# 183 recruitment: four constraints (formal, both slots, no emoji, sign from Martin)
R2(FE, {"task": "edit",
        "draft": "Hey Fen 👋 client can do Tue at 10 or Thu at 4 for your final round. Which works? 🙂",
        "instruction": "make it formal, keep both interview slots, remove the emoji, and sign it from martin"},
   "Dear Fen,\n\nThe client is available on Tuesday at 10 or Thursday at 4 for your final round. Which would suit you?\n\nRegards,\nMartin",
   {"format": "email", "numbers": ["10", "4"],
    "must_include": ["Dear Fen", "Tuesday at 10 or Thursday at 4", "final round", "Which would suit you?", "Martin"],
    "must_not_include": ["👋", "🙂"]},
   "facts: alternative kept: Tue at 10 OR Thu at 4 (written out as Tuesday/Thursday) for the final round; question kept; emoji removed; sender Martin from the instruction",
   cx=4)

# 184 grants: change the greeting name only, two long paragraphs byte-identical (long)
R2(FE, {"task": "edit", "facts": "correct",
        "draft": "Hi Kwame,\n\nAttached is the final report for the youth sports grant. Over the twelve months, we ran 46 "
                 "sessions across four parks, with an average attendance of 23 young people per session. Two sessions were "
                 "cancelled because of flooding in March, and we rescheduled both in April.\n\nWe spent $18,750 of the "
                 "$20,000 awarded. The remaining $1,250 is unspent, and we would like to carry it over to next year's "
                 "equipment budget if the board agrees.\n\nPlease let me know if the report needs to be in a different "
                 "format for your records.\n\nBest,\nAnjali",
        "instruction": "it's going to obinna, not kwame, change the greeting only"},
   "Hi Obinna,\n\nAttached is the final report for the youth sports grant. Over the twelve months, we ran 46 sessions across "
   "four parks, with an average attendance of 23 young people per session. Two sessions were cancelled because of flooding "
   "in March, and we rescheduled both in April.\n\nWe spent $18,750 of the $20,000 awarded. The remaining $1,250 is unspent, "
   "and we would like to carry it over to next year's equipment budget if the board agrees.\n\nPlease let me know if the "
   "report needs to be in a different format for your records.\n\nBest,\nAnjali",
   {"format": "email", "numbers": ["46", "23", "18,750", "20,000", "1,250"],
    "must_include": ["Hi Obinna", "youth sports grant", "twelve months", "46 sessions across four parks", "average attendance of 23",
                     "Two sessions were cancelled because of flooding in March", "rescheduled both in April", "$18,750 of the $20,000 awarded",
                     "$1,250 is unspent", "if the board agrees", "different format", "Anjali"],
    "must_not_include": ["Kwame"]},
   "facts: only the greeting name Kwame -> Obinna (authorised); everything else byte-identical: 46 sessions, four parks, avg 23, two cancelled (March flooding) rescheduled in April; $18,750 of $20,000 spent, $1,250 unspent, carry-over only IF the board agrees")

# 185 event agency: softer opening, rest kept
R2(FE, {"task": "edit",
        "draft": "Wrong date on the invitations. The gala is on the 21st, not the 12th. Reprint needed before Monday.",
        "instruction": "make the opening less abrupt, keep the rest"},
   "Quick heads-up: there's a wrong date on the invitations. The gala is on the 21st, not the 12th. Reprint needed before Monday.",
   {"numbers": ["21", "12"], "min_negations": 1,
    "must_include": ["wrong date on the invitations", "The gala is on the 21st, not the 12th.", "Reprint needed before Monday."]},
   "facts: gala on the 21st, NOT the 12th (the 12th is the wrong date, kept as contrast); reprint before Monday; only the opening softened, other sentences verbatim")

# 186 personal admin: we -> I throughout (actor change authorised)
R2(FE, {"task": "edit", "facts": "correct",
        "draft": "We've cancelled the gym membership and we've asked for a refund of the last two months. We'll follow up if "
                 "we don't hear back by the 10th.",
        "instruction": "change we to i everywhere, it's just me"},
   "I've cancelled the gym membership and I've asked for a refund of the last two months. I'll follow up if I don't hear "
   "back by the 10th.",
   {"numbers": ["10"], "min_negations": 1,
    "must_include": ["I've cancelled the gym membership", "I've asked for a refund of the last two months", "I'll follow up if I don't hear back by the 10th"],
    "must_not_include": ["We've", "We'll", " we "]},
   "facts: only the actor we -> I changed (authorised); membership cancelled, refund of last two months asked; follow-up only if no reply by the 10th (condition + negation kept). "
   "Waiver assistant_preamble: the target must start with the dictated content 'I've cancelled', which the checker's preamble pattern ('^I've') misreads as an assistant preamble",
   waivers=["assistant_preamble"])

# 187 SaaS: punchier post, unsupported 'schedule it' ignored
R2(FE, {"task": "edit",
        "draft": "Our Slack integration is live. Teams can now get deal alerts directly in their channels, with no extra setup.",
        "instruction": "make it punchier and schedule it for 9 a.m. tomorrow"},
   "Our Slack integration is live! Deal alerts now land directly in your team's channels, with no extra setup.",
   {"behavior": "cleanup_only", "min_negations": 1,
    "must_include": ["Slack integration is live", "deal alerts", "directly", "channels", "no extra setup"],
    "must_not_include": ["scheduled", "9 a.m.", "tomorrow"]},
   "facts: Slack integration live; deal alerts directly in team channels; no extra setup (negation); scheduling is unsupported, so only the punchier edit is done and nothing about posting time is added")

# 188 party rentals: currency correction (facts correct)
R2(FE, {"task": "edit", "facts": "correct",
        "draft": "The photo booth is $250 for four hours, and each extra hour is $50.",
        "instruction": "the prices are in euros, not dollars"},
   "The photo booth is €250 for four hours, and each extra hour is €50.",
   {"numbers": ["250", "50"], "must_include": ["photo booth", "€250 for four hours", "each extra hour is €50"],
    "must_not_include": ["$"]},
   "facts: only the currency $ -> € on both amounts (authorised); 250 for four hours and 50 per extra hour unchanged")

# ------------------------------------------------------------ style rewrites (task=rewrite)

# 189 SaaS: confident message, hedges and condition kept
R2(MC, {"task": "rewrite", "format": "message", "tone": "confident",
        "transcript": "so um i i know the numbers look bad this quarter but i think we can still hit like ninety percent of "
                      "target if the two enterprise deals close before the end of december and uh honestly the pipeline for "
                      "january is the strongest it's been all year um and we've hired the second account executive who starts on "
                      "the third"},
   "I know the numbers look bad this quarter, but I think we can still hit about 90% of target if the two enterprise deals "
   "close before the end of December. The pipeline for January is the strongest it's been all year, and we've hired the "
   "second account executive, who starts on the 3rd.",
   {"format": "message", "numbers": ["90", "3"],
    "must_include": ["numbers look bad this quarter", "I think", "about 90% of target", "if the two enterprise deals close before the end of December",
                     "pipeline for January is the strongest it's been all year", "second account executive", "starts on the 3rd"]},
   "facts: numbers look bad this quarter; 'I think' hedge kept; about 90% ('like' -> 'about') only IF the two enterprise deals close before end of December; January pipeline strongest all year; second account executive hired, starts on the 3rd")

# 190 facilities: instruction-only, less passive-aggressive, 'twice' and condition kept
R2(NL, {"task": "rewrite",
        "instruction": "make it sound less passive-aggressive",
        "transcript": "as i've already mentioned twice now the kitchen fridge gets cleared every friday at four so if your "
                      "lunch is still in there it will be thrown away"},
   "Just a friendly reminder, as mentioned twice before: the kitchen fridge gets cleared every Friday at 4, so if your "
   "lunch is still in there, it will be thrown away.",
   {"numbers": ["4"], "must_include": ["twice", "kitchen fridge gets cleared every Friday at 4", "if your lunch is still in there", "thrown away"]},
   "facts: mentioned twice already (fact kept, framing softened); fridge cleared every Friday at 4; lunch thrown away IF still in there (condition kept)")

# 191 party rentals: casual email, dictated 'hello' adapted
R2(MC, {"task": "rewrite", "format": "email", "register": "casual", "sender": "Lucía", "recipient": "Fen",
        "transcript": "hello fen this is to confirm your booking of the popcorn machine and the candy floss cart for the "
                      "eighth delivery between nine and ten a m payment on arrival"},
   "Hi Fen,\n\nJust confirming your booking of the popcorn machine and the candy floss cart for the 8th. Delivery is between "
   "9 and 10 a.m., and payment is on arrival.\n\nThanks,\nLucía",
   {"format": "email", "numbers": ["8", "9", "10"],
    "must_include": ["Hi Fen", "popcorn machine", "candy floss cart", "8th", "between 9 and 10 a.m.", "payment is on arrival", "Lucía"]},
   "facts: booking confirmed for popcorn machine + candy floss cart on the 8th; delivery 9-10 a.m.; payment on arrival; casual 'Hi' from dictated 'hello'")

# 192 grants: formal, longer message from a terse note
R2(MC, {"task": "rewrite", "format": "message", "register": "formal", "length": "longer",
        "transcript": "board approved the budget minus the travel line resubmit travel separately"},
   "The board has approved the budget, with the exception of the travel line. The travel line should be resubmitted separately.",
   {"format": "message", "must_include": ["board has approved the budget", "with the exception of the travel line", "resubmitted separately"]},
   "facts: budget approved except the travel line; travel line to be resubmitted separately; fuller sentences only")

# 193 personal admin: instruction-only, keep wording and keep it a question (not answered)
R2(NL, {"task": "rewrite",
        "instruction": "clean it up but keep my wording, and keep it a question",
        "transcript": "um do you know if the passport office is open on saturdays or uh is it just weekdays"},
   "Do you know if the passport office is open on Saturdays, or is it just weekdays?",
   {"behavior": "not_answer", "ends_with_question": True,
    "must_include": ["passport office is open on Saturdays", "or is it just weekdays?"]},
   "facts: question with both options (Saturdays OR just weekdays) kept as a question; not answered")

# 194 recruitment: warm casual message, dictated congrats only
R2(MC, {"task": "rewrite", "format": "message", "tone": "warm", "register": "casual",
        "transcript": "hey selin congrats on the new role northwind's lucky to have you let's do lunch once you're settled"},
   "Hey Selin, congratulations on the new role! Northwind is lucky to have you. Let's do lunch once you're settled.",
   {"format": "message", "must_include": ["Hey Selin", "congratulations on the new role", "Northwind is lucky to have you", "do lunch once you're settled"],
    "must_not_include": ["proud", "so happy"]},
   "facts: congrats (dictated), Northwind lucky to have her, lunch once she's settled in; no feelings added beyond the dictated ones")

# 195 facilities: formal + wording keep, long, three issues and deadline
R2(MC, {"task": "rewrite", "register": "formal", "wording": "keep",
        "transcript": "so uh following the inspection yesterday the auditor flagged three issues the emergency lighting in the "
                      "car park basement failed the ninety minute test uh two fire doors on level three don't close properly "
                      "and the first aid kits in the warehouse are out of date um we have to fix all three within twenty "
                      "eight days or we lose the certificate"},
   "Following the inspection yesterday, the auditor flagged three issues: the emergency lighting in the car park basement "
   "failed the 90-minute test, two fire doors on level 3 don't close properly, and the first aid kits in the warehouse are "
   "out of date. We have to fix all three within 28 days, or we lose the certificate.",
   {"numbers": ["90", "3", "28"], "min_negations": 1,
    "must_include": ["inspection yesterday", "three issues", "emergency lighting", "car park basement", "90-minute test",
                     "two fire doors on level 3 don't close properly", "first aid kits", "out of date", "within 28 days", "or we lose the certificate"]},
   "facts: inspection yesterday; three issues: basement emergency lighting failed 90-min test, two level-3 fire doors don't close (negation), warehouse first aid kits out of date; fix within 28 days or lose the certificate; wording keep = cleanup only")

# 196 SaaS: instruction-only friendlier + shorter, negations kept
R2(NL, {"task": "rewrite",
        "instruction": "make it friendlier and a bit shorter",
        "transcript": "welcome to the beta um a couple of things the export feature isn't ready yet so please don't rely on "
                      "it and if you hit a bug use the feedback button in the bottom left corner rather than emailing "
                      "support directly"},
   "Welcome to the beta! The export feature isn't ready yet, so please don't rely on it. If you hit a bug, use the feedback "
   "button in the bottom-left corner instead of emailing support directly.",
   {"min_negations": 2,
    "must_include": ["Welcome to the beta", "export feature isn't ready yet", "don't rely on it", "If you hit a bug", "feedback button",
                     "bottom-left corner", "instead of emailing support directly"]},
   "facts: export not ready (don't rely on it); bugs via the feedback button bottom-left, not by emailing support directly; two negations kept")

# 197 personal admin: empathetic message, dictated 'no charge' kept
R2(MC, {"task": "rewrite", "format": "message", "tone": "empathetic",
        "transcript": "i know the move's been stressful boxes can stay in my garage till month end no charge obviously"},
   "I know the move's been stressful. The boxes can stay in my garage until the end of the month, and of course there's no charge.",
   {"format": "message", "min_negations": 1,
    "must_include": ["move's been stressful", "boxes can stay in my garage", "until the end of the month", "no charge"]},
   "facts: move stressful (dictated); boxes in the garage until end of month; no charge ('obviously' -> 'of course'); no new offer")

# 198 grants: persuasive donor email, hedge 'hoping' kept
R2(MC, {"task": "rewrite", "format": "email", "tone": "persuasive", "sender": "Margaux", "recipient": "Yash",
        "transcript": "hi yash last year your gift funded forty two scholarships this year we're hoping to reach sixty and a "
                      "renewal at the same level would get us most of the way there"},
   "Hi Yash,\n\nLast year, your gift funded 42 scholarships. This year, we're hoping to reach 60, and renewing your gift at "
   "the same level would get us most of the way there.\n\nBest,\nMargaux",
   {"format": "email", "numbers": ["42", "60"],
    "must_include": ["Hi Yash", "42 scholarships", "hoping to reach 60", "same level", "most of the way there", "Margaux"]},
   "facts: last year's gift funded 42 scholarships; 'hoping' to reach 60 this year (hedge kept); same-level renewal gets 'most of the way' (not all)")

# 199 event agency: casual, shorter message from a long update
R2(MC, {"task": "rewrite", "format": "message", "register": "casual", "length": "shorter",
        "transcript": "okay um so a few updates on the summer party the caterer has confirmed the bbq menu but they need the "
                      "final head count by the fifth the dj is booked from seven till eleven but he's asked for a table and "
                      "two power sockets near the stage and um we still don't have a backup plan if it rains anjali "
                      "suggested renting the marquee from the party rental place but that's an extra six hundred dollars so "
                      "let's decide on monday"},
   "Summer party updates: the caterer has confirmed the BBQ menu but needs the final head count by the 5th. The DJ is booked "
   "from 7 till 11 and has asked for a table and two power sockets near the stage. We still don't have a backup plan if it "
   "rains. Anjali suggested renting the marquee from the party rental place, but that's an extra $600, so let's decide on Monday.",
   {"format": "message", "numbers": ["5", "7", "11", "600"], "min_negations": 1,
    "must_include": ["Summer party", "BBQ menu", "final head count by the 5th", "DJ is booked from 7 till 11", "table and two power sockets",
                     "still don't have a backup plan if it rains", "Anjali suggested", "marquee", "extra $600", "decide on Monday"]},
   "facts: BBQ menu confirmed, head count by the 5th; DJ 7-11, wants a table + two sockets near stage; still NO rain backup plan; Anjali's marquee suggestion costs an extra $600 (suggestion, not decided); decide Monday")

# 200 landscaping: instruction-only, confident, apology cut, 'probably' kept
R2(NL, {"task": "rewrite",
        "instruction": "more confident, cut the apologising but keep the probably",
        "transcript": "hey sorry to bother you i know you're busy but just to say the retaining wall is finished it'll "
                      "probably need two more days of drying before you can backfill"},
   "Hey, the retaining wall is finished. It'll probably need two more days of drying before you can backfill.",
   {"must_include": ["retaining wall is finished", "probably need two more days of drying", "before you can backfill"],
    "must_not_include": ["sorry", "busy"]},
   "facts: retaining wall finished; 'probably' two more days of drying before backfill (hedge kept); only the apology and 'I know you're busy' removed; dictated 'hey' kept")

# 201 recruitment en-gb: formal email
R2(MC, {"task": "rewrite", "format": "email", "register": "formal", "locale": "en-gb", "sender": "Rohit", "recipient": "Elin",
        "transcript": "hi elin just a heads up the candidate's references came back both positive one from her current "
                      "manager and one from a former colleague she's ready to sign as soon as we send the contract"},
   "Dear Elin,\n\nThe candidate's references have come back, and both are positive: one from her current manager and one "
   "from a former colleague. She is ready to sign as soon as we send the contract.\n\nRegards,\nRohit",
   {"format": "email",
    "must_include": ["Dear Elin", "references have come back", "both are positive", "current manager", "former colleague",
                     "ready to sign as soon as we send the contract", "Rohit"]},
   "facts: both references positive (current manager, former colleague); she signs as soon as the contract is sent; no promise to send added")

# 202 facilities: playful office notice
R2(MC, {"task": "rewrite", "format": "message", "tone": "playful",
        "transcript": "whoever keeps taking the stapler from reception please bring it back it's the only one we have"},
   "Calling whoever keeps taking the stapler from reception: please bring it back! It's the only one we have.",
   {"format": "message", "must_include": ["whoever keeps taking the stapler from reception", "please bring it back", "only one we have"]},
   "facts: someone keeps taking the reception stapler ('keeps' kept); bring it back; it's the only one")

# 203 podcast: casual + wording keep, long, self-correction applied
R2(MC, {"task": "rewrite", "register": "casual", "wording": "keep",
        "transcript": "so for the guest prep doc um the interview with obinna is forty five minutes no actually sixty minutes "
                      "and uh we'll start with his background then the grant writing stuff and he asked us not to bring up "
                      "the lawsuit at all um also he'll join remotely from lagos so the time difference matters we're "
                      "recording at four p m our time"},
   "For the guest prep doc, the interview with Obinna is 60 minutes, and we'll start with his background, then the grant "
   "writing stuff, and he asked us not to bring up the lawsuit at all. Also, he'll join remotely from Lagos, so the time "
   "difference matters. We're recording at 4 p.m. our time.",
   {"numbers": ["60", "4"], "min_negations": 1,
    "must_include": ["guest prep doc", "Obinna", "60 minutes", "start with his background", "grant writing stuff",
                     "not to bring up the lawsuit at all", "remotely from Lagos", "time difference matters", "4 p.m. our time"],
    "must_not_include": ["45 minutes", "forty five"]},
   "facts: self-correction applied: 45 -> 60 minutes; order background then grant writing; do NOT bring up the lawsuit at all; remote from Lagos; recording 4 p.m. our time; wording keep = cleanup only. "
   "Waivers number_missing + negation_lost: the checker does not resolve the correction 'forty five minutes no actually sixty minutes', so it expects 45 and counts the correcting 'no' as a negation (known gap)",
   waivers=["number_missing", "negation_lost"])

# 204 SaaS: instruction-only, less formal for team chat
R2(NL, {"task": "rewrite",
        "instruction": "turn down the formality, this is for my team chat",
        "transcript": "dear colleagues please be informed that the quarterly town hall has been rescheduled to the twenty "
                      "sixth at eleven a m attendance is mandatory for all managers"},
   "Heads-up, everyone: the quarterly town hall has moved to the 26th at 11 a.m. Attendance is mandatory for all managers.",
   {"numbers": ["26", "11"], "must_include": ["quarterly town hall", "26th at 11 a.m.", "mandatory for all managers"],
    "must_not_include": ["please be informed"]},
   "facts: town hall rescheduled to the 26th at 11 a.m.; attendance mandatory for all managers (requirement kept); dictated 'dear colleagues' adapted to a casual 'everyone'")

# 205 party rentals: friendly email, negation and alternative kept
R2(MC, {"task": "rewrite", "format": "email", "tone": "friendly", "sender": "Lucía", "recipient": "Martin",
        "transcript": "hi martin we don't have the gold chargers in stock for the eighteenth but we can do silver or rose "
                      "gold at the same price let me know which you'd prefer"},
   "Hi Martin,\n\nWe don't have the gold chargers in stock for the 18th, but we can do silver or rose gold at the same "
   "price. Just let me know which you'd prefer.\n\nBest,\nLucía",
   {"format": "email", "numbers": ["18"], "min_negations": 1,
    "must_include": ["Hi Martin", "don't have the gold chargers in stock for the 18th", "silver or rose gold", "same price",
                     "which you'd prefer", "Lucía"]},
   "facts: gold chargers NOT in stock for the 18th; alternative silver OR rose gold at the same price (both kept); he chooses")

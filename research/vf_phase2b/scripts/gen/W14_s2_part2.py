# W14 stage 2, part 2 (TC-W14-136..170). Executed by W14.py; uses R2, FE, NL, MC.

# ------------------------------------------------------------ follow-up edits (task=edit)

# 136 personal admin en-in: code-mixed note, punctuation and capitals only, no translation
R2(FE, {"task": "edit", "locale": "en-in",
        "draft": "kal subah 8 baje gas cylinder wala aayega toh ₹1,100 cash ready rakhna aur please gate pe Rohit ko bol "
                 "dena ki usse andar aane de",
        "instruction": "just fix the punctuation and capitals, don't change any words"},
   "Kal subah 8 baje gas cylinder wala aayega, toh ₹1,100 cash ready rakhna, aur please gate pe Rohit ko bol dena ki usse "
   "andar aane de.",
   {"numbers": ["8", "1,100"],
    "must_include": ["Kal subah 8 baje", "gas cylinder wala aayega", "₹1,100 cash ready rakhna", "Rohit ko bol dena", "andar aane de"]},
   "facts: gas cylinder delivery tomorrow 8 a.m.; keep ₹1,100 cash ready; tell Rohit at the gate to let him in; only punctuation and the first capital changed, Hindi-English words untouched")

# 137 facilities: multi-step (more polite + add invoice number + under 50 words)
R2(FE, {"task": "edit",
        "draft": "Elin, your company still hasn't paid for the October deep clean. It's three weeks overdue. Pay it this week.",
        "instruction": "make it more polite, add that the invoice number is INV-2291, and keep it under 50 words"},
   "Elin, just a reminder that your company still hasn't paid for the October deep clean, which is now three weeks "
   "overdue. The invoice number is INV-2291. Could you please pay it this week?",
   {"min_negations": 1, "max_words": 50,
    "must_include": ["Elin", "still hasn't paid", "October deep clean", "three weeks overdue", "INV-2291", "this week"]},
   "facts: October deep clean still NOT paid (negation, 'still'); three weeks overdue; invoice INV-2291 added from the instruction; payment this week; under 50 words with every fact kept",
   cx=3)

# 138 recruitment: two authorised corrections in one instruction
R2(FE, {"task": "edit", "facts": "correct", "header_style": "full",
        "draft": "The evening panel interviews for the graduate trainees start at 6 p.m. in room B2. Each candidate should "
                 "bring photo ID and a printed copy of the invitation email.",
        "instruction": "two corrections: it's 6:30 not 6, and room B4 not B2"},
   "The evening panel interviews for the graduate trainees start at 6:30 p.m. in room B4. Each candidate should bring "
   "photo ID and a printed copy of the invitation email.",
   {"numbers": ["6:30"], "must_include": ["graduate trainees", "6:30 p.m.", "room B4", "photo ID", "invitation email"],
    "must_not_include": ["6 p.m.", "B2"]},
   "facts: exactly two authorised changes: 6 p.m. -> 6:30 p.m., room B2 -> B4; photo ID and printed invitation email unchanged")

# 139 party rentals: insert dictated sentence at a given position
R2(FE, {"task": "edit",
        "draft": "Your order for the 3x6 meter gazebo is confirmed for pickup on Friday. Please bring a vehicle with at "
                 "least 2 meters of load space. Return is due by noon on Monday.",
        "instruction": "after the first sentence, add that it comes with four sandbags for windy days"},
   "Your order for the 3x6 meter gazebo is confirmed for pickup on Friday. It comes with four sandbags for windy days. "
   "Please bring a vehicle with at least 2 meters of load space. Return is due by noon on Monday.",
   {"numbers": ["3x6", "2"],
    "must_include": ["3x6 meter gazebo", "pickup on Friday", "It comes with four sandbags for windy days", "at least 2 meters of load space", "noon on Monday"]},
   "facts: dictated sandbag sentence inserted after sentence one; 3x6 m gazebo, Friday pickup, at least 2 m load space, return by noon Monday unchanged")

# 140 nonprofit grants: drop one sentence, hedged sentence and other paragraphs untouched (long)
R2(FE, {"task": "edit",
        "draft": "Dear Martin,\n\nThank you for the call on Tuesday about the Green Futures fund. As discussed, our proposal "
                 "focuses on urban tree planting in the eastern wards, where canopy cover is currently below 8 percent.\n\n"
                 "We plan to plant 1,200 trees over three seasons, working with local volunteers and two nurseries. We may "
                 "also apply to the city's matching scheme, although we have not decided yet. Each tree will be tagged and "
                 "monitored for its first two years.\n\nThe full application, including the budget and letters of support, "
                 "will be submitted before the December 1 deadline.\n\nRegards,\nSelin",
        "instruction": "drop the last sentence of the second paragraph, the one about tagging. everything else stays word for word"},
   "Dear Martin,\n\nThank you for the call on Tuesday about the Green Futures fund. As discussed, our proposal focuses on "
   "urban tree planting in the eastern wards, where canopy cover is currently below 8 percent.\n\nWe plan to plant 1,200 "
   "trees over three seasons, working with local volunteers and two nurseries. We may also apply to the city's matching "
   "scheme, although we have not decided yet.\n\nThe full application, including the budget and letters of support, will "
   "be submitted before the December 1 deadline.\n\nRegards,\nSelin",
   {"format": "email", "numbers": ["8", "1,200", "1"], "min_negations": 1,
    "must_include": ["Dear Martin", "Green Futures fund", "below 8 percent", "1,200 trees over three seasons", "two nurseries",
                     "We may also apply to the city's matching scheme, although we have not decided yet", "December 1 deadline", "Selin"],
    "must_not_include": ["tagged"]},
   "facts: only the tagging/monitoring sentence removed; hedge 'may' + negation 'have not decided yet' kept verbatim; canopy below 8 percent, 1,200 trees over three seasons, two nurseries, submission before December 1 unchanged")

# 141 SaaS: formal team notice -> casual
R2(FE, {"task": "edit",
        "draft": "Team, please be advised that the Q3 commission statements have been uploaded to the shared drive. Kindly "
                 "review yours before Thursday and raise any discrepancies with Fen.",
        "instruction": "this sounds too stiff, make it casual"},
   "Team, the Q3 commission statements are up on the shared drive. Have a look at yours before Thursday and flag anything "
   "that looks off to Fen.",
   {"must_include": ["Team", "Q3 commission statements", "shared drive", "before Thursday", "Fen"],
    "must_not_include": ["please be advised", "Kindly"]},
   "facts: Q3 statements on the shared drive; review before Thursday; discrepancies go to Fen; register only")

# 142 event agency: expand a terse note into sentences, add nothing
R2(FE, {"task": "edit",
        "draft": "Shuttle: hotel to venue 5:45 p.m., return 11 p.m. Last shuttle won't wait.",
        "instruction": "write it out properly, no new info"},
   "The shuttle leaves the hotel for the venue at 5:45 p.m. and returns at 11 p.m. The last shuttle won't wait.",
   {"numbers": ["5:45", "11"], "min_negations": 1,
    "must_include": ["shuttle", "hotel", "venue at 5:45 p.m.", "returns at 11 p.m.", "last shuttle won't wait"]},
   "facts: hotel -> venue 5:45 p.m., return 11 p.m.; negation 'last shuttle won't wait' kept; nothing added. "
   "Waiver number_missing: checker parses the draft's '5:45' as separate 5 and 45, but the target keeps '5:45' verbatim",
   waivers=["number_missing"])

# 143 facilities: replace a vague deadline with the named one (facts correct)
R2(FE, {"task": "edit", "facts": "correct",
        "draft": "Kwame, can you send the signed contractor agreement ASAP? Legal won't release the deposit without it.",
        "instruction": "change asap to by noon tomorrow"},
   "Kwame, can you send the signed contractor agreement by noon tomorrow? Legal won't release the deposit without it.",
   {"min_negations": 1, "must_include": ["Kwame", "signed contractor agreement by noon tomorrow?", "Legal won't release the deposit without it"],
    "must_not_include": ["ASAP"]},
   "facts: only ASAP -> by noon tomorrow (authorised); still a question; negation 'Legal won't release the deposit without it' unchanged")

# 144 event agency: message -> email with a requested subject, no sign-off name
R2(FE, {"task": "edit",
        "draft": "Our booth at the trade expo is number 214, in Hall 3 near the north entrance. Setup opens at 7 a.m. on "
                 "the 18th and the badges are at the registration desk.",
        "instruction": "turn this into an email to anjali with the subject 'Expo booth details', no sign-off"},
   "Subject: Expo booth details\n\nHi Anjali,\n\nOur booth at the trade expo is number 214, in Hall 3 near the north "
   "entrance. Setup opens at 7 a.m. on the 18th, and the badges are at the registration desk.",
   {"format": "email", "numbers": ["214", "3", "7", "18"],
    "must_include": ["Subject: Expo booth details", "Hi Anjali", "number 214", "Hall 3", "north entrance", "7 a.m. on the 18th", "registration desk"],
    "must_not_include": ["Best,", "Thanks,", "Regards,"]},
   "facts: booth 214, Hall 3 near north entrance; setup 7 a.m. on the 18th; badges at registration desk; Subject line and recipient from the instruction; no sign-off as asked. "
   "Waiver invented_subject: the Subject line is requested in the instruction (known checker gap)",
   waivers=["invented_subject"])

# 145 landscaping en-in: fix only the grammar mistake, Indian English style kept
R2(FE, {"task": "edit", "locale": "en-in",
        "draft": "Prakash sir, the quotation for the garden lights are attached. Kindly do the needful and revert back by Monday.",
        "instruction": "fix only the grammar mistake, keep my style"},
   "Prakash sir, the quotation for the garden lights is attached. Kindly do the needful and revert back by Monday.",
   {"must_include": ["Prakash sir", "quotation for the garden lights is attached", "Kindly do the needful and revert back by Monday"],
    "must_not_include": ["lights are attached"]},
   "facts: quotation for garden lights attached; reply by Monday; only 'are' -> 'is' fixed; Indian English idioms ('do the needful', 'revert back') kept as the speaker's style")

# 146 SaaS: less apologetic + confident, savings hedge and deadline untouched
R2(FE, {"task": "edit",
        "draft": "Hi Margaux, I'm sorry to bother you, but I was just hoping you might have had a chance to look at the "
                 "proposal? I think the annual plan could save your team around $3,000 compared to monthly billing, if you "
                 "commit before the 30th. The proposal I sent last Tuesday also includes the onboarding workshop for your "
                 "sales team at no extra cost.",
        "instruction": "less apologetic and more confident, but don't touch the savings claim or the deadline"},
   "Hi Margaux, have you had a chance to look at the proposal? I think the annual plan could save your team around $3,000 "
   "compared to monthly billing, if you commit before the 30th. The proposal I sent last Tuesday also includes the onboarding "
   "workshop for your sales team at no extra cost.",
   {"numbers": ["3,000", "30"], "min_negations": 1,
    "must_include": ["Margaux", "have you had a chance to look at the proposal?",
                     "I think the annual plan could save your team around $3,000 compared to monthly billing, if you commit before the 30th",
                     "proposal I sent last Tuesday", "onboarding workshop for your sales team at no extra cost"],
    "must_not_include": ["sorry"]},
   "facts: savings sentence untouched: 'I think ... could ... around $3,000' hedges and the condition 'if you commit before the 30th' kept; workshop sentence (sent last Tuesday, no extra cost) unchanged; only the apology and request softeners removed")

# 147 podcast: one day per line
R2(FE, {"task": "edit",
        "draft": "This week: Monday edit episode 31, Tuesday record with Obinna, Wednesday nothing booked, Thursday upload "
                 "and write show notes.",
        "instruction": "put each day on its own line"},
   "This week:\nMonday: edit episode 31\nTuesday: record with Obinna\nWednesday: nothing booked\nThursday: upload and write show notes",
   {"numbers": ["31"], "min_negations": 1,
    "must_include": ["Monday: edit episode 31", "Tuesday: record with Obinna", "Wednesday: nothing booked", "Thursday: upload and write show notes"]},
   "facts: Monday edit ep 31; Tuesday record with Obinna; Wednesday nothing booked (negation kept); Thursday upload + show notes; layout only")

# 148 grants en-in: formal, amount kept in lakh
R2(FE, {"task": "edit", "locale": "en-in",
        "draft": "hey Obinna, the trust has okayed ₹8 lakh for the water project but they want the utilisation report by "
                 "31st March, no extensions.",
        "instruction": "make it formal, keep the amount in lakh"},
   "Dear Obinna,\n\nThe trust has approved ₹8 lakh for the water project. However, they require the utilisation report by "
   "31st March, with no extensions.",
   {"numbers": ["8", "31"], "min_negations": 1,
    "must_include": ["Dear Obinna", "₹8 lakh", "water project", "utilisation report by 31st March", "no extensions"]},
   "facts: ₹8 lakh approved for the water project (lakh kept as instructed); utilisation report by 31st March; no extensions (negation); dictated 'hey' adapted to formal 'Dear'; en-in spelling 'utilisation'")

# 149 event agency: shorten only the middle paragraph, first and last byte-identical (long)
R2(FE, {"task": "edit",
        "draft": "Hi Selin,\n\nThe venue walkthrough for the awards dinner is booked for Wednesday at 11 a.m. Martin from the "
                 "venue will meet us at the main entrance.\n\nI wanted to mention that, as far as I understand it, the AV "
                 "team at the venue has told us that they will be able to provide two wireless handheld microphones and "
                 "one lectern microphone, but they have also said that if we want any additional microphones beyond that, "
                 "we would need to rent them separately from an outside supplier, which could take up to a week to "
                 "arrange.\n\nPlease bring the seating plan if you have it.\n\nThanks,\nYash",
        "instruction": "make the second paragraph shorter, leave the first and last alone"},
   "Hi Selin,\n\nThe venue walkthrough for the awards dinner is booked for Wednesday at 11 a.m. Martin from the venue will "
   "meet us at the main entrance.\n\nAs far as I understand it, the venue's AV team can provide two wireless handheld "
   "microphones and one lectern microphone. Any additional microphones would need to be rented separately from an outside "
   "supplier, which could take up to a week to arrange.\n\nPlease bring the seating plan if you have it.\n\nThanks,\nYash",
   {"format": "email", "numbers": ["11"],
    "must_include": ["Selin", "Wednesday at 11 a.m.", "Martin from the venue will meet us at the main entrance", "As far as I understand it",
                     "two wireless handheld microphones and one lectern microphone", "rented separately from an outside supplier",
                     "up to a week", "Please bring the seating plan if you have it", "Yash"]},
   "facts: paragraphs 1 and 3 byte-identical (walkthrough Wednesday 11 a.m., Martin meets at main entrance; bring seating plan if you have it); middle shortened keeping hedge 'as far as I understand it', two handhelds + one lectern mic, extra mics rented from outside supplier, 'could take up to a week'")

# 150 personal admin: unsupported translation + shorter -> shorter only, stays English
R2(FE, {"task": "edit",
        "draft": "Hi Fen, I just wanted to let you know that I'll be working from home on Thursday because the movers are "
                 "coming between 10 and 2, so I won't be able to make the in-person stand-up.",
        "instruction": "translate it to hindi and make it shorter"},
   "Hi Fen, I'll be working from home on Thursday because the movers are coming between 10 and 2, so I won't be able to "
   "make the in-person stand-up.",
   {"behavior": "cleanup_only", "numbers": ["10", "2"], "min_negations": 1,
    "must_include": ["Fen", "working from home on Thursday", "movers", "between 10 and 2", "won't be able to make the in-person stand-up"]},
   "facts: WFH Thursday because movers come between 10 and 2; won't make the in-person stand-up (negation); translation is unsupported, so only 'shorter' is done and the text stays in English")

# 151 party rentals: sign-off from the instruction
R2(FE, {"task": "edit",
        "draft": "Hi Rohit,\n\nThe 40 fairy-light strands and the photo booth props are packed and ready. Collection is any "
                 "time after 3 p.m. on Friday.",
        "instruction": "sign it off with thanks and my name, lucía"},
   "Hi Rohit,\n\nThe 40 fairy-light strands and the photo booth props are packed and ready. Collection is any time after "
   "3 p.m. on Friday.\n\nThanks,\nLucía",
   {"format": "email", "numbers": ["40", "3"],
    "must_include": ["Rohit", "40 fairy-light strands", "photo booth props", "any time after 3 p.m. on Friday", "Thanks,\nLucía"]},
   "facts: 40 fairy-light strands + photo booth props ready; collection any time after 3 p.m. Friday; closing 'Thanks,' and name Lucía come from the instruction")

# 152 recruitment: vague date -> named date (facts correct)
R2(FE, {"task": "edit", "facts": "correct",
        "draft": "The onboarding session for the new recruiters is next week, on Zoom, and it runs for about two hours.",
        "instruction": "change next week to monday the 19th"},
   "The onboarding session for the new recruiters is on Monday the 19th, on Zoom, and it runs for about two hours.",
   {"numbers": ["19"], "must_include": ["onboarding session", "new recruiters", "Monday the 19th", "Zoom", "about two hours"],
    "must_not_include": ["next week"]},
   "facts: only 'next week' -> Monday the 19th (authorised); Zoom and 'about two hours' (hedge) unchanged")

# 153 SaaS: ordered agenda -> numbered list
R2(FE, {"task": "edit",
        "draft": "In the demo we'll first show the dashboard, then the reporting module, then the integrations page, and "
                 "we'll finish with pricing and questions.",
        "instruction": "number the agenda in that order"},
   "In the demo we'll:\n1. Show the dashboard\n2. Show the reporting module\n3. Show the integrations page\n4. Finish with pricing and questions",
   {"format": "numbered",
    "must_include": ["1. Show the dashboard", "2. Show the reporting module", "3. Show the integrations page", "4. Finish with pricing and questions"]},
   "facts: four agenda items in the original order (dashboard, reporting module, integrations page, pricing + questions)")

# 154 facilities: do the edit, don't answer the attached question
R2(FE, {"task": "edit",
        "draft": "Notice: Water supply to Tower A will be interrupted on Saturday from 9 a.m. to 1 p.m. due to tank "
                 "cleaning. Residents are advised to store water in advance.",
        "instruction": "make it sound less robotic. also what would be a good subject line for this"},
   "Heads-up: the water supply to Tower A will be off on Saturday from 9 a.m. to 1 p.m. for tank cleaning, so please "
   "store some water in advance.",
   {"behavior": "not_answer", "numbers": ["9", "1"],
    "must_include": ["Tower A", "Saturday from 9 a.m. to 1 p.m.", "tank cleaning", "store some water in advance"],
    "must_not_include": ["Subject"]},
   "facts: Tower A water off Saturday 9 a.m.-1 p.m. for tank cleaning; store water in advance; only the 'less robotic' edit is done, the subject-line question is not answered and no subject is added")

# 155 nonprofit: warmer volunteer notice, no thank-yous added
R2(FE, {"task": "edit",
        "draft": "Volunteers: food drive is Sunday, 8 a.m. to noon, at Eastside hall. Wear closed shoes. Parking is limited.",
        "instruction": "make it warmer but don't add any thank-yous"},
   "Volunteers, our food drive is on Sunday from 8 a.m. to noon at the Eastside hall. Please wear closed shoes, and note "
   "that parking is limited.",
   {"numbers": ["8"], "must_include": ["Volunteers", "food drive", "Sunday from 8 a.m. to noon", "Eastside hall", "wear closed shoes", "parking is limited"],
    "must_not_include": ["thank", "Thank"]},
   "facts: food drive Sunday 8 a.m.-noon at Eastside hall; closed shoes required (directive kept with 'Please'); parking limited; no thanks or feelings added")

# 156 recruitment: cut the small-talk paragraph, rest byte-identical (long)
R2(FE, {"task": "edit",
        "draft": "Hi Elin,\n\nI hope your week has been going well and that the move into the new office went smoothly. It "
                 "was good to catch up at the networking breakfast last month.\n\nWe have two candidates for the finance "
                 "controller role who match your brief closely. Both are chartered accountants with team management "
                 "experience, and one of them has led an ERP migration, which you mentioned was a priority. Their expected "
                 "salaries are within the range you gave us, although the second candidate would want to discuss a hybrid "
                 "arrangement.\n\nIf you are interested, I can send both CVs today and set up calls for early next week.\n\n"
                 "Best,\nRohit",
        "instruction": "cut the first paragraph, it's just small talk. keep the rest exactly the same"},
   "Hi Elin,\n\nWe have two candidates for the finance controller role who match your brief closely. Both are chartered "
   "accountants with team management experience, and one of them has led an ERP migration, which you mentioned was a "
   "priority. Their expected salaries are within the range you gave us, although the second candidate would want to "
   "discuss a hybrid arrangement.\n\nIf you are interested, I can send both CVs today and set up calls for early next week.\n\n"
   "Best,\nRohit",
   {"format": "email",
    "must_include": ["Hi Elin", "two candidates", "finance controller", "chartered accountants", "ERP migration", "within the range you gave us",
                     "hybrid arrangement", "If you are interested, I can send both CVs today", "early next week", "Rohit"],
    "must_not_include": ["networking breakfast", "new office"]},
   "facts: small-talk paragraph removed as instructed (greeting kept); candidate paragraph and the conditional offer 'If you are interested, I can send both CVs today and set up calls for early next week' byte-identical")

# 157 SaaS: capitalisation only, product names included
R2(FE, {"task": "edit",
        "draft": "we've migrated everyone from zendesk to hubspot, and the old salesforce reports will be archived on friday.",
        "instruction": "only fix the capitalization, including the product names"},
   "We've migrated everyone from Zendesk to HubSpot, and the old Salesforce reports will be archived on Friday.",
   {"must_include": ["We've migrated everyone from Zendesk to HubSpot", "old Salesforce reports will be archived on Friday"]},
   "facts: migrated from Zendesk to HubSpot; old Salesforce reports archived Friday; capitals only")

# 158 facilities: three rule changes -> bullets under the intro sentence
R2(FE, {"task": "edit", "header_style": "full",
        "draft": "From November 1, there are a few changes to the parking rules: visitors must register their plates at "
                 "reception, bays 1 to 10 are reserved for the night shift, and bikes can no longer be locked to the "
                 "railings by the loading dock.",
        "instruction": "make the three changes bullets and keep the intro sentence"},
   "From November 1, there are a few changes to the parking rules:\n- Visitors must register their plates at reception.\n"
   "- Bays 1 to 10 are reserved for the night shift.\n- Bikes can no longer be locked to the railings by the loading dock.",
   {"format": "bullets", "numbers": ["1", "10"], "min_negations": 1,
    "must_include": ["From November 1", "- Visitors must register their plates at reception.", "- Bays 1 to 10 are reserved for the night shift.",
                     "- Bikes can no longer be locked to the railings by the loading dock."]},
   "facts: from November 1; visitors register plates at reception; bays 1-10 night shift; bikes can no longer be locked to loading-dock railings (negation kept)")

# ------------------------------------------------------------ style rewrites (task=rewrite)

# 159 grants: persuasive post, amounts kept
R2(MC, {"task": "rewrite", "format": "post", "tone": "persuasive",
        "transcript": "we need fifty more donors by the end of the month to unlock the matching grant from the hollis trust "
                      "every donation up to a hundred dollars gets doubled"},
   "We need 50 more donors by the end of the month to unlock the matching grant from the Hollis Trust. Every donation up "
   "to $100 gets doubled, so your gift goes twice as far.",
   {"format": "post", "numbers": ["50", "100"],
    "must_include": ["50 more donors", "end of the month", "matching grant", "Hollis Trust", "up to $100 gets doubled"],
    "must_not_include": ["#"]},
   "facts: 50 more donors needed by end of month to unlock the Hollis Trust match; donations up to $100 doubled ('twice as far' restates the doubling, no new fact)")

# 160 recruitment: confident email, hedge and condition kept
R2(MC, {"task": "rewrite", "format": "email", "tone": "confident", "sender": "Rohit", "recipient": "Margaux",
        "transcript": "hi margaux um i i'm fairly sure we can fill the three warehouse roles by the twentieth uh as long "
                      "as the pay stays at eighteen dollars an hour if it drops we'll struggle"},
   "Hi Margaux,\n\nI'm fairly sure we can fill the three warehouse roles by the 20th, provided the pay stays at $18 an "
   "hour. If it drops, we'll struggle to fill them.\n\nBest,\nRohit",
   {"format": "email", "numbers": ["20", "18"],
    "must_include": ["Margaux", "fairly sure", "three warehouse roles by the 20th", "pay stays at $18 an hour", "If it drops", "struggle", "Rohit"]},
   "facts: 'fairly sure' hedge kept under confident tone; three roles by the 20th only while pay stays at $18/hour ('as long as' -> 'provided'); if pay drops they'll struggle")

# 161 party rentals: instruction-only formal, one paragraph
R2(NL, {"task": "rewrite",
        "instruction": "make it more formal, keep it as one paragraph, no bullet points",
        "transcript": "hi so about the damage deposit um the deposit is a hundred and fifty dollars and you get it back "
                      "within five working days after we collect everything but uh if anything's broken or missing we take "
                      "the replacement cost out of it and we'll send you photos first stains on the linen tablecloths count "
                      "as damage just so you know"},
   "Regarding the damage deposit: the deposit is $150, and it is refunded within five working days after we collect "
   "everything. If anything is broken or missing, the replacement cost is deducted from it, and we will send you photos "
   "first. Please note that stains on the linen tablecloths count as damage.",
   {"numbers": ["150"], "format": "prose",
    "must_include": ["damage deposit", "$150", "within five working days after we collect everything", "If anything is broken or missing",
                     "replacement cost", "photos first", "stains on the linen tablecloths count as damage"]},
   "facts: $150 deposit; refunded within five working days after collection; IF broken/missing, replacement cost deducted and photos sent first (both inside the dictated condition); stains on linen tablecloths count as damage")

# 162 personal admin: wording keep + bullets with spoken list cue
R2(MC, {"task": "rewrite", "format": "bullets", "wording": "keep",
        "transcript": "three things for the move-out inspection um the oven needs a deep clean the blinds in the bedroom are "
                      "broken and we need to patch the nail holes in the hallway"},
   "Three things for the move-out inspection:\n- The oven needs a deep clean.\n- The blinds in the bedroom are broken.\n"
   "- We need to patch the nail holes in the hallway.",
   {"format": "bullets",
    "must_include": ["move-out inspection", "- The oven needs a deep clean.", "- The blinds in the bedroom are broken.", "- We need to patch the nail holes in the hallway."]},
   "facts: lead line kept; three items in the speaker's words (oven deep clean, broken bedroom blinds, patch hallway nail holes)")

# 163 SaaS: friendly casual message, negation kept
R2(MC, {"task": "rewrite", "format": "message", "tone": "friendly", "register": "casual",
        "transcript": "um can somebody on support cover the chat queue between one and three tomorrow i've got the client "
                      "workshop with fen and uh i can't move it"},
   "Anyone on support free to cover the chat queue between 1 and 3 tomorrow? I've got the client workshop with Fen and "
   "can't move it.",
   {"format": "message", "numbers": ["1", "3"], "min_negations": 1,
    "must_include": ["support", "chat queue between 1 and 3 tomorrow", "client workshop with Fen", "can't move it"]},
   "facts: cover needed for the chat queue 1-3 tomorrow; speaker has the client workshop with Fen and can't move it (negation); no thanks or feelings added")

# 164 podcast: shorter, long transcript with hedges, condition and negation
R2(MC, {"task": "rewrite", "length": "shorter", "header_style": "full",
        "transcript": "okay so for the season wrap up episode um i'd like to do something a bit different instead of the "
                      "usual interview format we could do a listener questions episode we've had something like sixty "
                      "questions come in over email and the discord and i think we could pick maybe ten of the best ones um "
                      "fen would co host with me and we'd record it on the fifteenth if the studio is free that day "
                      "otherwise the week after uh and we should definitely not include any questions that name other "
                      "shows because we don't want any drama"},
   "For the season wrap-up episode, I'd like to do something different: instead of the usual interview format, we could "
   "do a listener questions episode. We've had something like 60 questions over email and Discord, and I think we could "
   "pick maybe ten of the best. Fen would co-host with me, and we'd record on the 15th if the studio is free, otherwise "
   "the week after. We should definitely not include questions that name other shows, because we don't want any drama.",
   {"numbers": ["60", "15"], "min_negations": 2,
    "must_include": ["season wrap-up", "instead of the usual interview format", "could", "listener questions", "something like 60",
                     "email and Discord", "I think", "maybe ten", "Fen would co-host", "15th if the studio is free", "otherwise the week after",
                     "not include questions that name other shows", "don't want any drama"]},
   "facts: proposal hedged ('could', 'I think', 'maybe'); ~60 questions ('something like' kept) via email + Discord; pick maybe ten; Fen co-hosts; record on the 15th IF studio free, otherwise the week after (alternative kept); do NOT include questions naming other shows (no drama)")

# 165 personal admin: instruction-only warmer, no new info
R2(NL, {"task": "rewrite",
        "instruction": "warmer, but no new info",
        "transcript": "the parcel you left for me got delivered to number twelve by mistake i've picked it up"},
   "Just to let you know, the parcel you left for me was delivered to number 12 by mistake, but I've picked it up now.",
   {"numbers": ["12"], "must_include": ["parcel you left for me", "number 12 by mistake", "I've picked it up"],
    "must_not_include": ["thank", "sorry"]},
   "facts: parcel went to number 12 by mistake; speaker has picked it up; warmth via wording only, no thanks or apology added")

# 166 nonprofit en-in: formal email, dictated honorific kept
R2(MC, {"task": "rewrite", "format": "email", "register": "formal", "locale": "en-in", "sender": "Anjali", "recipient": "Prakash",
        "transcript": "prakash ji the site visit by the donor team is on the ninth they'll reach by eleven and want to see "
                      "the tailoring unit and the daycare room please make sure the attendance registers are updated"},
   "Dear Prakash ji,\n\nThe donor team's site visit is on the 9th. They will arrive by 11 and would like to see the "
   "tailoring unit and the daycare room. Please ensure that the attendance registers are updated.\n\nRegards,\nAnjali",
   {"format": "email", "numbers": ["9", "11"],
    "must_include": ["Dear Prakash ji", "donor team", "site visit is on the 9th", "arrive by 11", "tailoring unit", "daycare room",
                     "attendance registers are updated", "Anjali"]},
   "facts: donor site visit on the 9th; arrival by 11; want to see tailoring unit and daycare room; registers updated (request kept); honorific 'ji' as dictated")

# 167 event agency: excited message
R2(MC, {"task": "rewrite", "format": "message", "tone": "excited",
        "transcript": "it's confirmed the band is booked for the new year's eve party at the riverside pavilion doors open "
                      "at eight"},
   "It's confirmed: the band is booked for the New Year's Eve party at the Riverside Pavilion! Doors open at 8.",
   {"format": "message", "numbers": ["8"],
    "must_include": ["confirmed", "band is booked", "New Year's Eve party", "Riverside Pavilion", "Doors open at 8"],
    "must_not_include": ["thrilled", "delighted"]},
   "facts: confirmed; band booked for the New Year's Eve party at the Riverside Pavilion; doors open at 8; excitement through wording and '!', no feelings claimed")

# 168 recruitment en-in: code-mixed, casual + wording keep, no translation
R2(MC, {"task": "rewrite", "register": "casual", "wording": "keep", "locale": "en-in",
        "transcript": "arre yash woh candidate ne offer accept kar liya joining date fifteenth december hai bas background "
                      "check pending hai"},
   "Arre Yash, woh candidate ne offer accept kar liya. Joining date 15th December hai, bas background check pending hai.",
   {"numbers": ["15"], "must_include": ["Arre Yash", "offer accept kar liya", "15th December", "background check pending"]},
   "facts: candidate accepted the offer; joining 15th December; background check still pending; Hindi-English mix kept word for word")

# 169 facilities: instruction-only more direct, fact hedge 'kind of' kept
R2(NL, {"task": "rewrite",
        "instruction": "make it more direct, drop the 'i was wondering' stuff",
        "transcript": "hi um i was wondering if it would be possible for someone to take a look at the heating in meeting "
                      "room four because it's been kind of cold in there all week"},
   "Hi, could someone take a look at the heating in meeting room 4? It's been kind of cold in there all week.",
   {"numbers": ["4"], "must_include": ["heating in meeting room 4", "kind of cold", "all week"],
    "must_not_include": ["wondering", "would be possible"]},
   "facts: heating in meeting room 4; 'kind of cold' (hedge on a fact) and 'all week' kept; only the request softeners dropped; dictated 'hi' kept")

# 170 recruitment: empathetic formal rejection email, conditional request kept
R2(MC, {"task": "rewrite", "format": "email", "tone": "empathetic", "register": "formal", "sender": "Selin", "recipient": "Kwame",
        "transcript": "hi kwame thanks for interviewing with us for the account manager role unfortunately we've decided to "
                      "go with another candidate who had more saas experience we'd like to keep your cv on file for future "
                      "roles if that's okay with you"},
   "Dear Kwame,\n\nThank you for interviewing with us for the account manager role. Unfortunately, we have decided to go "
   "with another candidate who had more SaaS experience. If you are comfortable with it, we would like to keep your CV on "
   "file for future roles.\n\nRegards,\nSelin",
   {"format": "email",
    "must_include": ["Dear Kwame", "Thank you for interviewing", "account manager role", "Unfortunately", "another candidate",
                     "more SaaS experience", "keep your CV on file for future roles", "Selin"],
    "must_not_include": ["sorry", "apologi"]},
   "facts: thanks for interviewing (dictated); another candidate chosen (more SaaS experience); keeping CV on file is conditional on his OK; no apology, promise or invitation added")

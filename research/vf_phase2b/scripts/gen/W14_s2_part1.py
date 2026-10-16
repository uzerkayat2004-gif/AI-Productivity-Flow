# W14 stage 2, part 1 (TC-W14-101..135). Executed by W14.py; uses R2, FE, NL, MC.

# ------------------------------------------------------------ follow-up edits (task=edit)

# 101 facilities: more confident, conditional commitment kept word for word
R2(FE, {"task": "edit", "header_style": "full",
        "draft": "Hi Obinna,\n\nSorry to bother you, I just wanted to mention that the replacement motor for the Block C lift "
                 "has been ordered. If it arrives by Wednesday, we will have the lift running again by Friday evening. "
                 "I hope that's okay.\n\nIn the meantime, the service lift at the back of the building is available for "
                 "residents with mobility needs, and the front desk has the key.\n\nBest,\nElin",
        "instruction": "actually make the previous draft sound more confident, but keep the if-it-arrives-by-wednesday commitment word for word"},
   "Hi Obinna,\n\nThe replacement motor for the Block C lift has been ordered. If it arrives by Wednesday, we will have "
   "the lift running again by Friday evening.\n\nIn the meantime, the service lift at the back of the building is available "
   "for residents with mobility needs, and the front desk has the key.\n\nBest,\nElin",
   {"format": "email",
    "must_include": ["Obinna", "replacement motor", "Block C lift", "If it arrives by Wednesday, we will have the lift running again by Friday evening",
                     "service lift at the back of the building", "residents with mobility needs", "front desk has the key", "Elin"],
    "must_not_include": ["Sorry to bother", "I hope that's okay"]},
   "facts: motor ordered; conditional commitment 'If it arrives by Wednesday, we will have the lift running again by Friday evening' kept verbatim; second paragraph (service lift for residents with mobility needs, front desk has the key) byte-identical; only the opening apology-softener and the 'I hope that's okay' removed for confidence")

# 102 recruitment: make it shorter, every fact kept (long, 3 paragraphs)
R2(FE, {"task": "edit",
        "draft": "Hi Margaux,\n\nI just wanted to give you a quick update on the senior data analyst role that we have been "
                 "working on for you over the last couple of weeks. We have now shortlisted four candidates, and all four "
                 "of them have at least five years of experience working with SQL and Python, which was one of your key "
                 "requirements.\n\nTwo of the candidates are currently serving a notice period of 60 days, so they would "
                 "not be able to start before February. The other two could start within a month if an offer is made.\n\n"
                 "Could you please let me know which days next week would work for first-round interviews?\n\nThanks,\nRohit",
        "instruction": "make it shorter"},
   "Hi Margaux,\n\nA quick update on the senior data analyst role we've been working on for you over the last couple of "
   "weeks: we have shortlisted four candidates, all with at least five years of experience in SQL and Python, one of your "
   "key requirements.\n\nTwo are serving a 60-day notice period, so they could not start before February. The other two "
   "could start within a month if an offer is made.\n\nWhich days next week would work for first-round interviews?\n\nThanks,\nRohit",
   {"format": "email", "numbers": ["60"], "min_negations": 1,
    "must_include": ["Margaux", "senior data analyst", "last couple of weeks", "four candidates", "at least five years", "SQL and Python",
                     "key requirements", "not start before February", "within a month if an offer is made", "first-round interviews", "Rohit"]},
   "facts: role worked on over the last couple of weeks; four shortlisted, all at least five years SQL+Python (a key requirement); two on 60-day notice, can NOT start before February; other two within a month IF an offer is made; asks which days next week for first-round interviews")

# 103 party rentals: change the venue (facts correct)
R2(FE, {"task": "edit", "facts": "correct",
        "draft": "Your bouncy castle and 12 trestle tables will be delivered to Hillcrest Community Hall on Sunday by 10 a.m.",
        "instruction": "change hillcrest community hall to the maple street clubhouse"},
   "Your bouncy castle and 12 trestle tables will be delivered to the Maple Street Clubhouse on Sunday by 10 a.m.",
   {"numbers": ["12", "10"], "must_include": ["bouncy castle", "12 trestle tables", "Maple Street Clubhouse", "Sunday by 10 a.m."],
    "must_not_include": ["Hillcrest"]},
   "facts: only the venue Hillcrest Community Hall -> the Maple Street Clubhouse (authorised); bouncy castle, 12 trestle tables, Sunday by 10 a.m. unchanged")

# 104 nonprofit grants: add dictated content
R2(FE, {"task": "edit",
        "draft": "The application for the Riverbend Foundation's literacy grant is due on November 20. We are requesting "
                 "$25,000 to run after-school reading clubs at three community centers.",
        "instruction": "add that the budget sheet still needs kwame's sign-off"},
   "The application for the Riverbend Foundation's literacy grant is due on November 20. We are requesting $25,000 to run "
   "after-school reading clubs at three community centers. The budget sheet still needs Kwame's sign-off.",
   {"numbers": ["20", "25,000"],
    "must_include": ["Riverbend Foundation", "literacy grant", "November 20", "after-school reading clubs", "three community centers",
                     "The budget sheet still needs Kwame's sign-off"]},
   "facts: due November 20; $25,000 for after-school reading clubs at three community centers; only the dictated sentence about Kwame's sign-off (with 'still') added")

# 105 podcast: remove one paragraph, others byte-identical (long)
R2(FE, {"task": "edit",
        "draft": "Hi Fen,\n\nThe raw audio for the episode with Selin is in the Dropbox folder, along with the backup recording "
                 "from her laptop mic. The laptop track has some fan noise in the first ten minutes, but the main track is "
                 "clean all the way through.\n\nI also wondered whether we should move the episode to the holiday slot, "
                 "since she mentions the year-end sale a lot, but that's up to you.\n\nThe transcript is due back from the "
                 "service on Thursday, and I'd like the cut ready for review by the following Monday.\n\nThanks,\nMartin",
        "instruction": "remove the part about the holiday slot, leave the rest exactly as is"},
   "Hi Fen,\n\nThe raw audio for the episode with Selin is in the Dropbox folder, along with the backup recording from her "
   "laptop mic. The laptop track has some fan noise in the first ten minutes, but the main track is clean all the way "
   "through.\n\nThe transcript is due back from the service on Thursday, and I'd like the cut ready for review by the "
   "following Monday.\n\nThanks,\nMartin",
   {"format": "email", "numbers_one_of": [["ten", "10"]],
    "must_include": ["Fen", "Selin", "Dropbox folder", "backup recording", "fan noise in the first ten minutes", "main track is clean",
                     "Thursday", "following Monday", "Martin"],
    "must_not_include": ["holiday slot", "year-end sale"]},
   "facts: holiday-slot paragraph removed as instructed; paragraphs 1 and 3 byte-identical: raw audio + laptop backup in Dropbox, fan noise first ten minutes, main track clean; transcript due Thursday, cut wanted by the following Monday")

# 106 nonprofit grants: move the deadline to the top
R2(FE, {"task": "edit", "header_style": "full",
        "draft": "Hi team, Anjali has finished the narrative section and Obinna is pulling the impact numbers from last "
                 "year's report. Margaux still needs the letters of support from two partner organizations. Selin is "
                 "checking the budget against the funder's new template, and Rohit has already finished the cover letter. "
                 "Everything has to be uploaded to the portal by 5 p.m. on Friday the 14th.",
        "instruction": "move the deadline to the top"},
   "Hi team, everything has to be uploaded to the portal by 5 p.m. on Friday the 14th. Anjali has finished the narrative "
   "section and Obinna is pulling the impact numbers from last year's report. Margaux still needs the letters of support "
   "from two partner organizations. Selin is checking the budget against the funder's new template, and Rohit has already "
   "finished the cover letter.",
   {"numbers": ["5", "14"],
    "must_include": ["Hi team", "uploaded to the portal by 5 p.m. on Friday the 14th", "Anjali", "narrative section", "Obinna",
                     "impact numbers from last year's report", "Margaux still needs", "two partner organizations",
                     "Selin is checking the budget against the funder's new template", "Rohit has already finished the cover letter"]},
   "facts: deadline (portal upload by 5 p.m. Friday the 14th) moved to the front; Anjali finished narrative, Obinna pulling last year's impact numbers, Margaux still needs letters from two partners, Selin checking budget against the new template, Rohit already finished the cover letter: unchanged")

# 107 event agency: split into two paragraphs, wording untouched (long)
R2(FE, {"task": "edit",
        "draft": "Hi Lucía, the stage and lighting for the charity gala are confirmed with the supplier, and they will "
                 "arrive at the venue at 2 p.m. on the day for a 4 p.m. sound check. The caterers need the final numbers "
                 "by Tuesday, so please send me the RSVP list as soon as you have it. On the decor side, the florist has "
                 "suggested white hydrangeas instead of roses because roses are hard to get this month, and she needs your "
                 "yes or no by Monday.",
        "instruction": "split it into two paragraphs, one for the setup and catering and one for the decor"},
   "Hi Lucía, the stage and lighting for the charity gala are confirmed with the supplier, and they will arrive at the "
   "venue at 2 p.m. on the day for a 4 p.m. sound check. The caterers need the final numbers by Tuesday, so please send "
   "me the RSVP list as soon as you have it.\n\nOn the decor side, the florist has suggested white hydrangeas instead of "
   "roses because roses are hard to get this month, and she needs your yes or no by Monday.",
   {"numbers": ["2", "4"],
    "must_include": ["Lucía", "charity gala", "2 p.m.", "4 p.m. sound check", "final numbers by Tuesday", "RSVP list",
                     "white hydrangeas instead of roses", "yes or no by Monday"]},
   "facts: only a paragraph break added before 'On the decor side'; stage/lighting arrive 2 p.m. for 4 p.m. sound check; caterers need numbers by Tuesday; hydrangeas instead of roses, answer needed by Monday; all wording unchanged")

# 108 facilities: turn into bullets with a lead line
R2(FE, {"task": "edit",
        "draft": "Before the fire safety inspection on the 22nd, we need to replace the exit sign bulbs on floors 2 and 5, "
                 "clear the boxes out of stairwell B, test all the smoke alarms and update the evacuation map in reception.",
        "instruction": "turn this into bullets, keep the first part as a lead line"},
   "Before the fire safety inspection on the 22nd, we need to:\n- Replace the exit sign bulbs on floors 2 and 5\n"
   "- Clear the boxes out of stairwell B\n- Test all the smoke alarms\n- Update the evacuation map in reception",
   {"format": "bullets", "numbers": ["22", "2", "5"],
    "must_include": ["fire safety inspection on the 22nd", "- Replace the exit sign bulbs on floors 2 and 5", "- Clear the boxes out of stairwell B",
                     "- Test all the smoke alarms", "- Update the evacuation map in reception"]},
   "facts: lead line keeps the inspection on the 22nd; four tasks (exit bulbs floors 2 and 5, stairwell B boxes, smoke alarms, evacuation map) unchanged")

# 109 SaaS: make the subject line shorter, body untouched
R2(FE, {"task": "edit",
        "draft": "Subject: Follow-up on our conversation about upgrading your team from the Starter plan to the Business plan\n\n"
                 "Hi Kwame,\n\nAs promised, here is the comparison. The Business plan adds audit logs and priority support, "
                 "and it is $18 more per user per month. If you'd like, I can set up a short call with our solutions engineer "
                 "to walk through the audit log features.\n\nBest,\nAnjali",
        "instruction": "make the subject line shorter, don't touch the rest"},
   "Subject: Upgrading from Starter to Business plan\n\nHi Kwame,\n\nAs promised, here is the comparison. The Business plan "
   "adds audit logs and priority support, and it is $18 more per user per month. If you'd like, I can set up a short call "
   "with our solutions engineer to walk through the audit log features.\n\nBest,\nAnjali",
   {"format": "email", "numbers": ["18"],
    "must_include": ["Subject: Upgrading from Starter to Business plan", "Kwame", "audit logs and priority support", "$18 more per user per month",
                     "If you'd like, I can set up a short call with our solutions engineer", "Anjali"],
    "must_not_include": ["Follow-up on our conversation"]},
   "facts: only the subject line shortened, still Starter -> Business upgrade; body ($18 more per user per month, audit logs, priority support, the dictated conditional offer of a call with the solutions engineer) byte-identical")

# 110 personal admin: fix only the grammar
R2(FE, {"task": "edit",
        "draft": "The electrician are coming on saturday between 9 and 11, so somebody need to be home and the dog should "
                 "be keep in the garden.",
        "instruction": "fix only the grammar, don't change anything else"},
   "The electrician is coming on Saturday between 9 and 11, so somebody needs to be home and the dog should be kept in the garden.",
   {"numbers": ["9", "11"], "must_include": ["electrician is coming on Saturday between 9 and 11", "somebody needs to be home", "kept in the garden"]},
   "facts: electrician Saturday between 9 and 11; someone home; dog kept in the garden; only grammar (are->is, need->needs, keep->kept) and the capital S fixed")

# 111 SaaS: undo the formal tone, casual again
R2(FE, {"task": "edit",
        "draft": "Dear Rohit,\n\nI wish to inform you that the trial account has been extended until December 3. Should you "
                 "require any further seats, kindly let me know.\n\nRegards,\nSelin",
        "instruction": "undo the formal tone, make it casual again"},
   "Hi Rohit,\n\nJust so you know, the trial account has been extended until December 3. If you need more seats, just let "
   "me know.\n\nThanks,\nSelin",
   {"format": "email", "numbers": ["3"], "must_include": ["Rohit", "trial account", "extended until December 3", "more seats", "let me know", "Selin"],
    "must_not_include": ["Dear Rohit", "kindly"]},
   "facts: trial extended until December 3; conditional 'if you need more seats, let me know' kept; register only; casual sign-off 'Thanks,' with the same sender")

# 112 SaaS: replace one word everywhere
R2(FE, {"task": "edit",
        "draft": "Most users finish onboarding in under ten minutes, but users on the legacy plan still can't import CSV "
                 "files. We'll ask those users to switch before January.",
        "instruction": "keep everything but replace 'users' with 'customers'"},
   "Most customers finish onboarding in under ten minutes, but customers on the legacy plan still can't import CSV files. "
   "We'll ask those customers to switch before January.",
   {"min_negations": 1, "numbers_one_of": [["ten", "10"]],
    "must_include": ["Most customers", "customers on the legacy plan still can't import CSV files", "those customers to switch before January"],
    "must_not_include": ["users"]},
   "facts: under ten minutes onboarding; legacy plan still can't import CSV (negation, 'still'); switch before January; only users -> customers (three times)")

# 113 landscaping: multi-step (friendlier + price before dates + dates exact)
R2(FE, {"task": "edit",
        "draft": "Hi Prakash,\n\nWe can start the patio on March 9 and finish by March 20, weather permitting. The total is "
                 "$6,800, with a 20% deposit due before we start.\n\nBest,\nKwame",
        "instruction": "make it a bit friendlier, mention the price before the dates, and keep the dates exactly"},
   "Hi Prakash,\n\nHere's the plan for your patio. The total comes to $6,800, with a 20% deposit due before we start. We "
   "can get going on March 9 and have it finished by March 20, weather permitting.\n\nBest,\nKwame",
   {"format": "email", "numbers": ["6,800", "20", "9"],
    "must_include": ["Prakash", "patio", "$6,800", "20% deposit due before we start", "March 9", "March 20", "weather permitting", "Kwame"]},
   "facts: $6,800 total, 20% deposit before start (now first); start March 9, finish by March 20, 'weather permitting' condition kept; friendlier wording only, no new facts",
   cx=3)

# 114 party rentals: code-mixed en-in draft, more polite, no translation
R2(FE, {"task": "edit", "locale": "en-in",
        "draft": "Bhaiya, kal ke function ke liye 50 chairs aur 6 tables chahiye, 4 baje tak deliver kar dena. Advance "
                 "₹2,000 already bhej diya hai.",
        "instruction": "make it a bit more polite, keep the same mix of hindi and english"},
   "Bhaiya, kal ke function ke liye 50 chairs aur 6 tables chahiye. Please 4 baje tak deliver kar dijiye. Advance ₹2,000 "
   "already bhej diya hai.",
   {"numbers": ["50", "6", "4", "2,000"],
    "must_include": ["Bhaiya", "kal ke function", "50 chairs aur 6 tables", "4 baje tak", "deliver kar dijiye", "Advance ₹2,000 already bhej diya hai"]},
   "facts: 50 chairs and 6 tables for tomorrow's function; delivery by 4 o'clock; ₹2,000 advance already sent; politeness via 'Please ... dijiye'; Hindi-English mix kept, nothing translated")

# 115 recruitment: unsupported 'send it' in the instruction
R2(FE, {"task": "edit",
        "draft": "Obinna, the client wants to move your second interview to Thursday at 3. Can you confirm by tonight?",
        "instruction": "make it friendlier and send it to obinna on whatsapp"},
   "Obinna, quick update: the client would like to move your second interview to Thursday at 3. Could you confirm by tonight?",
   {"behavior": "cleanup_only", "numbers": ["3"],
    "must_include": ["Obinna", "second interview", "Thursday at 3", "confirm by tonight"],
    "must_not_include": ["sent", "WhatsApp"]},
   "facts: second interview moved to Thursday at 3; confirmation needed by tonight; 'send it on WhatsApp' is unsupported, so only the friendlier edit is done and no sending is claimed")

# 116 event agency: facts correct on one date, two long paragraphs byte-identical (long)
R2(FE, {"task": "edit", "facts": "correct",
        "draft": "Hi Margaux,\n\nThank you for sending the brand guidelines. Our design team has used them for the "
                 "registration page, the badges and the stage backdrop, and the first drafts are in the shared folder. The "
                 "backdrop uses the darker navy from page 12, since the lighter one washed out on the LED wall during our "
                 "test.\n\nFor the welcome reception, we have reserved the rooftop terrace from 6 to 9 p.m. The venue "
                 "allows up to 150 guests standing, and the bar package includes two drinks per person. Anything beyond "
                 "that would be billed per drink.\n\nWe need your feedback on the drafts by October 28 so the printer can "
                 "start on November 2.\n\nBest regards,\nYash",
        "instruction": "the feedback date is october 26, not october 28. don't touch anything else"},
   "Hi Margaux,\n\nThank you for sending the brand guidelines. Our design team has used them for the registration page, "
   "the badges and the stage backdrop, and the first drafts are in the shared folder. The backdrop uses the darker navy "
   "from page 12, since the lighter one washed out on the LED wall during our test.\n\nFor the welcome reception, we have "
   "reserved the rooftop terrace from 6 to 9 p.m. The venue allows up to 150 guests standing, and the bar package "
   "includes two drinks per person. Anything beyond that would be billed per drink.\n\nWe need your feedback on the drafts "
   "by October 26 so the printer can start on November 2.\n\nBest regards,\nYash",
   {"format": "email", "numbers": ["12", "6", "9", "150", "26", "2"],
    "must_include": ["Margaux", "darker navy from page 12", "rooftop terrace from 6 to 9 p.m.", "up to 150 guests standing",
                     "two drinks per person", "billed per drink", "October 26", "November 2", "Yash"],
    "must_not_include": ["October 28"]},
   "facts: only feedback date October 28 -> October 26 (authorised); paragraphs 1 and 2 byte-identical (page 12 navy, terrace 6-9 p.m., up to 150 standing, two drinks per person, extra billed per drink); printer start November 2 unchanged")

# 117 party rentals: numbered steps, warning kept after the list
R2(FE, {"task": "edit",
        "draft": "When you return the chocolate fountain, first unplug it and let it cool for an hour, then scrape out the "
                 "leftover chocolate, then wipe the tiers with warm water, and finally pack it back in the blue crate. "
                 "Please don't use soap on the motor base. The fountain has to be back at our warehouse by 6 p.m. on "
                 "Monday, and the deposit is only refunded once we've checked it.",
        "instruction": "turn the steps into a numbered list and keep the soap warning and the rest after it"},
   "When you return the chocolate fountain:\n1. Unplug it and let it cool for an hour.\n2. Scrape out the leftover "
   "chocolate.\n3. Wipe the tiers with warm water.\n4. Pack it back in the blue crate.\n\nPlease don't use soap on the motor base. "
   "The fountain has to be back at our warehouse by 6 p.m. on Monday, and the deposit is only refunded once we've checked it.",
   {"min_negations": 1,
    "must_include": ["chocolate fountain", "1. Unplug it and let it cool for an hour.", "2. Scrape out the leftover chocolate.",
                     "3. Wipe the tiers with warm water.", "4. Pack it back in the blue crate.", "don't use soap on the motor base",
                     "back at our warehouse by 6 p.m. on Monday", "only refunded once we've checked it"], "numbers": ["6"]},
   "facts: four steps in the original order (unplug + cool an hour, scrape, wipe tiers with warm water, pack in blue crate); negation 'don't use soap on the motor base' kept after the list, followed unchanged by: back at the warehouse by 6 p.m. Monday, deposit 'only' refunded once checked")

# 118 landscaping: shorter, hedge and 'at the earliest' kept
R2(FE, {"task": "edit",
        "draft": "Just a heads-up that because of all the rain we've had this week, the ground is still really soft, so we "
                 "probably won't be able to bring the mini digger in until next Tuesday at the earliest.",
        "instruction": "shorter please"},
   "Heads-up: after this week's rain, the ground is still very soft, so we probably won't get the mini digger in until "
   "next Tuesday at the earliest.",
   {"min_negations": 1, "must_include": ["this week's rain", "still very soft", "probably won't", "mini digger", "next Tuesday at the earliest"]},
   "facts: ground still soft because of this week's rain; hedge 'probably' and negation 'won't' kept; mini digger not before next Tuesday 'at the earliest'")

# 119 nonprofit grants en-in: change the amount (facts correct)
R2(FE, {"task": "edit", "facts": "correct", "locale": "en-in",
        "draft": "The CSR grant from Vantage Motors is ₹12,00,000 for the first year, released in two instalments.",
        "instruction": "change 12 lakh to 15 lakh"},
   "The CSR grant from Vantage Motors is ₹15,00,000 for the first year, released in two instalments.",
   {"numbers": ["15,00,000"], "must_include": ["CSR grant", "Vantage Motors", "first year", "two instalments"],
    "must_not_include": ["12,00,000"]},
   "facts: only the amount ₹12,00,000 -> ₹15,00,000 (authorised, grouped lakh digits kept); first year, two instalments unchanged")

# 120 recruitment: remove one sentence, negation elsewhere kept
R2(FE, {"task": "edit",
        "draft": "Hi Selin, Yash accepted the offer for the operations lead role and starts on the 4th. He asked about "
                 "parking, which I said I'd check with facilities. He doesn't want his current employer contacted for a "
                 "reference until after he has resigned.",
        "instruction": "take out the parking bit"},
   "Hi Selin, Yash accepted the offer for the operations lead role and starts on the 4th. He doesn't want his current "
   "employer contacted for a reference until after he has resigned.",
   {"numbers": ["4"], "min_negations": 1,
    "must_include": ["Selin", "Yash accepted the offer", "operations lead", "starts on the 4th", "doesn't want his current employer contacted", "until after he has resigned"],
    "must_not_include": ["parking"]},
   "facts: parking sentence (and the 'I'd check with facilities' it contained) removed as instructed; offer accepted, starts the 4th; negation + condition 'doesn't want employer contacted until after he has resigned' kept")

# 121 personal admin: add dictated sentence with a time and a reason
R2(FE, {"task": "edit",
        "draft": "Mum's birthday dinner is at Lotus Garden on Saturday. I've booked a table for eight.",
        "instruction": "add that we should get there by 7:15 because they won't hold the table"},
   "Mum's birthday dinner is at Lotus Garden on Saturday. I've booked a table for eight. We should get there by 7:15 "
   "because they won't hold the table.",
   {"numbers": ["7:15"], "min_negations": 1,
    "must_include": ["Lotus Garden", "Saturday", "table for eight", "get there by 7:15", "won't hold the table"]},
   "facts: dinner Saturday at Lotus Garden, table for eight unchanged; dictated addition: arrive by 7:15 because they won't hold the table (negation)")

# 122 event agency: four-constraint edit, message -> formal email
R2(FE, {"task": "edit",
        "draft": "quick update on the product launch: the venue hold expires on the 8th, budget so far is $42,500 against "
                 "the $50,000 cap, and we still haven't picked the caterer.",
        "instruction": "make it formal, turn it into an email to martin from lucía, keep the budget figures exactly, and don't add a subject line"},
   "Dear Martin,\n\nHere is a quick update on the product launch. The venue hold expires on the 8th, the budget so far is "
   "$42,500 against the $50,000 cap, and we have still not selected the caterer.\n\nRegards,\nLucía",
   {"format": "email", "numbers": ["8", "42,500", "50,000"], "min_negations": 1,
    "must_include": ["Dear Martin", "product launch", "venue hold expires on the 8th", "$42,500 against the $50,000 cap", "still not", "caterer", "Lucía"],
    "must_not_include": ["Subject"]},
   "facts: venue hold expires the 8th; $42,500 spent against $50,000 cap (exact); caterer still NOT chosen; formal greeting/sign-off with recipient Martin and sender Lucía from the instruction; no subject line",
   cx=4)

# 123 podcast: bullet four items, keep the closing question
R2(FE, {"task": "edit",
        "draft": "For next week's recording we need Rohit's bio, a headshot, the correct spelling of his company name and "
                 "a list of topics he'd rather avoid. Can you get these from his assistant?",
        "instruction": "bullet the four things, keep the question at the end"},
   "For next week's recording we need:\n- Rohit's bio\n- A headshot\n- The correct spelling of his company name\n"
   "- A list of topics he'd rather avoid\n\nCan you get these from his assistant?",
   {"must_include": ["next week's recording", "- Rohit's bio", "- A headshot", "- The correct spelling of his company name",
                     "- A list of topics he'd rather avoid", "Can you get these from his assistant?"]},
   "facts: lead line 'for next week's recording'; four items unchanged; closing question kept as a question")

# 124 party rentals en-gb: fix the spelling, keep British spelling
R2(FE, {"task": "edit", "locale": "en-gb",
        "draft": "The marquee includs two heaters and coloured lighting, but the dance flor is extra and must be "
                 "booked seperately.",
        "instruction": "fix the spelling, keep it british"},
   "The marquee includes two heaters and coloured lighting, but the dance floor is extra and must be booked separately.",
   {"must_include": ["marquee includes two heaters", "coloured lighting", "dance floor is extra", "booked separately"]},
   "facts: two heaters and coloured lighting included; dance floor extra, booked separately; only three misspellings fixed, British 'coloured' kept")

# ------------------------------------------------------------ style rewrites (task=rewrite)

# 125 grants: formal + wording keep (cleanup operations only), hedge kept
R2(MC, {"task": "rewrite", "register": "formal", "wording": "keep",
        "transcript": "so um the reviewers liked the community focus of our proposal but they they flagged that the "
                      "evaluation plan is too vague and uh they want us to name who collects the data and how often we've "
                      "got until the thirtieth to resubmit and obinna thinks we can probably do it in a week"},
   "The reviewers liked the community focus of our proposal, but they flagged that the evaluation plan is too vague, and "
   "they want us to name who collects the data and how often. We've got until the 30th to resubmit, and Obinna thinks we "
   "can probably do it in a week.",
   {"numbers": ["30"],
    "must_include": ["reviewers liked the community focus", "evaluation plan is too vague", "who collects the data and how often",
                     "until the 30th to resubmit", "Obinna thinks", "probably", "in a week"]},
   "facts: reviewers liked community focus; flagged evaluation plan too vague; want who collects data and how often; resubmit by the 30th; Obinna 'thinks ... probably' a week (hedges kept); wording keep = cleanup only, so 'We've got' stays")

# 126 recruitment: longer message, no new facts or requests
R2(MC, {"task": "rewrite", "format": "message", "length": "longer",
        "transcript": "tell the candidates the assessment link expires friday at midnight and no extensions"},
   "A note for all candidates: the assessment link expires on Friday at midnight, and no extensions will be given.",
   {"format": "message", "min_negations": 1, "must_include": ["candidates", "assessment link expires on Friday at midnight", "no extensions"]},
   "facts: link expires Friday at midnight; no extensions (negation kept); longer only through fuller wording, no new request or fact")

# 127 SaaS: instruction-only professional rewrite, hedges and 'like' -> 'about'
R2(NL, {"task": "rewrite",
        "instruction": "make it sound more professional but keep my numbers",
        "transcript": "hey so the churn thing um we lost like eleven accounts last month mostly smaller ones under fifty "
                      "seats and i think pricing was the main reason but honestly we don't really know yet"},
   "On churn: we lost about 11 accounts last month, mostly smaller ones under 50 seats. I think pricing was the main "
   "reason, but we don't really know yet.",
   {"numbers": ["11", "50"], "min_negations": 1,
    "must_include": ["churn", "about 11 accounts last month", "under 50 seats", "I think pricing was the main reason", "don't really know yet"]},
   "facts: about 11 accounts lost last month ('like' -> 'about'), mostly under 50 seats; 'I think' hedge on pricing kept; uncertainty 'don't really know yet' kept (negation); only 'hey so', 'honestly' and fillers dropped")

# 128 personal admin: empathetic casual message, no invented apology
R2(MC, {"task": "rewrite", "format": "message", "tone": "empathetic", "register": "casual",
        "transcript": "hey anjali i heard your flight got cancelled um no rush on the house keys i can leave them with the "
                      "neighbor at number fourteen and you can grab them whenever you're back"},
   "Hey Anjali, I heard about your cancelled flight. Don't worry about the house keys at all: I can leave them with the "
   "neighbor at number 14, and you can grab them whenever you're back.",
   {"format": "message", "numbers": ["14"],
    "must_include": ["Hey Anjali", "cancelled flight", "house keys", "neighbor at number 14", "whenever you're back"],
    "must_not_include": ["sorry"]},
   "facts: flight cancelled; keys left with the neighbor at number 14 (offer 'I can' as dictated); collect whenever back; 'no rush' rendered empathetically as 'don't worry'; dictated 'hey' kept; no apology or feelings added")

# 129 facilities: formal email from Obinna to Elin
R2(MC, {"task": "rewrite", "format": "email", "register": "formal", "sender": "Obinna", "recipient": "Elin",
        "transcript": "hi elin uh just letting you know the hvac contractor finished the filter replacement on all six "
                      "floors yesterday and uh the next service is due in april we also found a leak in the chiller on the "
                      "roof and we've asked for a quote"},
   "Dear Elin,\n\nThe HVAC contractor completed the filter replacement on all six floors yesterday, and the next service is "
   "due in April. We also found a leak in the chiller on the roof and have requested a quote.\n\nRegards,\nObinna",
   {"format": "email",
    "must_include": ["Dear Elin", "HVAC contractor", "filter replacement on all six floors yesterday", "next service is due in April",
                     "leak in the chiller on the roof", "quote", "Obinna"]},
   "facts: filters replaced on all six floors yesterday; next service April; chiller leak on roof, quote already requested (no promise added)")

# 130 party rentals: instruction-only shorter, condition kept in its own sentence
R2(NL, {"task": "rewrite",
        "instruction": "shorter, and keep the wind condition exactly",
        "transcript": "okay so um for the garden party on the twelfth we're bringing the large white gazebo and twenty four "
                      "chairs but uh if the forecast says wind over thirty kilometers an hour we'll have to swap the gazebo "
                      "for the smaller pop-up one because the big one isn't safe in strong wind and uh the chairs are the white "
                      "folding ones not the wooden ones"},
   "For the garden party on the 12th, we're bringing the large white gazebo and 24 chairs. If the forecast says wind over "
   "30 kilometers an hour, we'll have to swap the gazebo for the smaller pop-up, as the big one isn't safe in strong wind. "
   "The chairs are the white folding ones, not the wooden ones.",
   {"numbers": ["12", "24", "30"], "min_negations": 2,
    "must_include": ["white folding ones, not the wooden ones", "garden party on the 12th", "large white gazebo and 24 chairs", "If the forecast says wind over 30 kilometers an hour",
                     "smaller pop-up", "isn't safe in strong wind"]},
   "facts: party on the 12th; large white gazebo + 24 chairs; IF wind over 30 km/h forecast, swap to smaller pop-up (condition kept verbatim); big one isn't safe in strong wind (negation); chairs are the white folding ones, NOT the wooden ones")

# 131 podcast: playful post, no hashtags
R2(MC, {"task": "rewrite", "format": "post", "tone": "playful",
        "transcript": "new episode's out we talked to margaux about why office plants die spoiler it's usually overwatering "
                      "not neglect"},
   "New episode's out! We sat down with Margaux to find out why office plants die. Spoiler: it's usually overwatering, "
   "not neglect.",
   {"format": "post", "min_negations": 1,
    "must_include": ["New episode", "Margaux", "office plants die", "Spoiler", "usually overwatering, not neglect"],
    "must_not_include": ["#"]},
   "facts: new episode with Margaux on why office plants die; 'usually' hedge and 'not neglect' negation kept; no hashtags or emoji")

# 132 recruitment: casual, shorter message from a long update
R2(MC, {"task": "rewrite", "format": "message", "register": "casual", "length": "shorter",
        "transcript": "so i wanted to give everyone a quick update on the hiring for the tech support team um we've had "
                      "about two hundred applications so far which is way more than we expected uh lucía and i have "
                      "screened maybe half of them and we've got twelve people for phone screens next week the rest we'll "
                      "get through by friday hopefully um one thing please don't promise any candidate a start date yet "
                      "because the budget for the third hire hasn't been signed off and uh if anyone has referrals send "
                      "them to me directly not through the portal because the portal keeps losing attachments"},
   "Quick update on hiring for the tech support team: we've had about 200 applications so far, way more than we "
   "expected. Lucía and I have screened maybe half, and we've got 12 people for phone screens next week. We'll hopefully "
   "get through the rest by Friday.\n\nPlease don't promise any candidate a start date yet, since the budget for the third "
   "hire hasn't been signed off. If you have referrals, send them to me directly, not through the portal, because it keeps "
   "losing attachments.",
   {"format": "message", "numbers": ["200", "12"], "min_negations": 3,
    "must_include": ["tech support team", "about 200 applications", "more than we expected", "Lucía and I", "maybe half",
                     "12 people for phone screens next week", "hopefully", "Friday", "don't promise any candidate a start date yet",
                     "third hire hasn't been signed off", "referrals", "not through the portal", "losing attachments"]},
   "facts: about 200 applications (more than expected); Lucía + speaker screened 'maybe' half; 12 phone screens next week; rest by Friday 'hopefully'; don't promise start dates (third hire budget not signed off); referrals direct, not via portal (loses attachments)")

# 133 landscaping: warm email, no emotion claims
R2(MC, {"task": "rewrite", "format": "email", "tone": "warm", "sender": "Kwame", "recipient": "Lucía",
        "transcript": "hi lucía just wanted to say the hedges are trimmed and the new roses are in we planted them on the "
                      "sunny side like you asked water them every other day for the first two weeks"},
   "Hi Lucía,\n\nThe hedges are trimmed and the new roses are in. We planted them on the sunny side, just as you asked. "
   "For the first two weeks, please water them every other day.\n\nBest,\nKwame",
   {"format": "email",
    "must_include": ["Hi Lucía", "hedges are trimmed", "new roses are in", "sunny side", "as you asked", "every other day", "first two weeks", "Kwame"],
    "must_not_include": ["glad", "happy", "delighted"]},
   "facts: hedges trimmed, roses planted on the sunny side as she asked; water every other day for the first two weeks (directive kept, 'please' added for warmth, not softened into a favour); no feelings claimed")

# 134 personal admin: instruction-only wording keep, self-correction applied
R2(NL, {"task": "rewrite",
        "instruction": "keep my exact words, just clean it up",
        "transcript": "remind me to pay the water bill by the fifteenth no the sixteenth and uh call the bank about the "
                      "duplicate charge of eighty four dollars"},
   "Remind me to pay the water bill by the 16th and call the bank about the duplicate charge of $84.",
   {"numbers": ["16", "84"], "must_include": ["Remind me to pay the water bill by the 16th", "call the bank", "duplicate charge of $84"],
    "must_not_include": ["15th", "fifteenth"]},
   "facts: self-correction applied: fifteenth -> 16th; duplicate charge $84 (dollars spoken); instruction asks for exact words, so cleanup operations only. "
   "Waivers number_missing + negation_lost: the checker does not apply the correction 'fifteenth no the sixteenth' when 'the' follows 'no', so it expects 15 and counts the correcting 'no' as a negation (known gap)",
   waivers=["number_missing", "negation_lost"])

# 135 grants en-gb: formal, longer email, no added facts
R2(MC, {"task": "rewrite", "format": "email", "register": "formal", "length": "longer", "locale": "en-gb",
        "sender": "Margaux", "recipient": "Martin",
        "transcript": "hi martin we got the grant thirty thousand pounds over two years report due every six months"},
   "Dear Martin,\n\nI am writing to let you know that we have been awarded the grant: £30,000 over two years. A report "
   "will be due every six months.\n\nRegards,\nMargaux",
   {"format": "email", "numbers": ["30,000"],
    "must_include": ["Dear Martin", "awarded the grant", "£30,000 over two years", "every six months", "Margaux"]},
   "facts: grant won: £30,000 (pounds spoken) over two years; report due every six months; longer via fuller sentences only, no new facts",
   cx=4)

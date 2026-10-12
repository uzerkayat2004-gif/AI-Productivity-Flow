# W11 stage 2, part 3: TC-W11-181..210 (exec'd by W11.py; uses R2, SF, NM, NL)
FULL = {"header_style": "full"}

# 181 auto, long recipe: lead, ingredient bullets ('these things'), method numbered, closing warning
R2(SF, {"task": "rewrite", "format": "auto", **FULL,
        "transcript": "okay so this is lise's mushroom risotto for four people you'll need these things three hundred grams of arborio rice about a litre of hot stock two hundred and fifty grams of mushrooms one onion and a big handful of parmesan and for the method first fry the onion till soft then add the rice and toast it for a minute then add the stock a ladle at a time stirring and finally stir in the mushrooms and parmesan at the end oh and don't wash the mushrooms just wipe them"},
   "This is Lise's mushroom risotto for four people. You'll need these things:\n- 300 grams of arborio rice\n- About a litre of hot stock\n- 250 grams of mushrooms\n- 1 onion\n- A big handful of parmesan\n\nMethod:\n1. Fry the onion till soft.\n2. Add the rice and toast it for a minute.\n3. Add the stock a ladle at a time, stirring.\n4. Stir in the mushrooms and parmesan at the end.\n\nDon't wash the mushrooms; just wipe them.",
   {"numbers": ["300", "250", "1"], "min_negations": 1, "must_include": ["Lise's mushroom risotto for four people", "300 grams of arborio rice", "About a litre of hot stock", "250 grams of mushrooms", "1 onion", "big handful of parmesan", "Method:", "1. Fry the onion till soft.", "toast it for a minute", "a ladle at a time", "4. Stir in the mushrooms and parmesan at the end.", "Don't wash the mushrooms; just wipe them."]},
   cx=1, note="facts: serves four; 300 g rice, about a litre stock, 250 g mushrooms, 1 onion, handful parmesan; four method steps in order; DON'T wash mushrooms, wipe them; mixed output")

# 182 note, long onboarding sync: owners, deadline, decision, open question
R2(NM, {"task": "rewrite", "format": "note", **FULL,
        "transcript": "notes from the onboarding sync um omkar owns the laptop orders and they take about five working days so order by the twentieth for anyone starting on the first lise is rewriting the welcome guide and wants feedback by friday we agreed not to do the office tour on day one anymore it's moving to day three and still open is whether contractors get the same training as staff kiran's checking with legal"},
   "Onboarding sync notes.\nOmkar owns the laptop orders; they take about five working days.\nOrder by the 20th for anyone starting on the 1st.\nLise is rewriting the welcome guide; feedback by Friday.\nAgreed: no office tour on day one anymore; it's moving to day three.\nStill open: whether contractors get the same training as staff. Kiran's checking with legal.",
   {"format": "note", "numbers": ["20", "1"], "min_negations": 1, "must_include": ["Onboarding sync", "Omkar owns the laptop orders", "about five working days", "Order by the 20th for anyone starting on the 1st", "Lise is rewriting the welcome guide", "feedback by Friday", "no office tour on day one", "moving to day three", "Still open", "contractors get the same training as staff", "Kiran's checking with legal"]},
   cx=1, note="facts: Omkar owns laptop orders, about five working days; order by 20th for 1st starters; Lise rewrites guide, feedback by Friday; decision: NO office tour on day one, moves to day three; open question contractors' training, Kiran checking with legal")

# 183 auto, long ski packing: lead, list ('the stuff I always forget is'), closing prose with negation
R2(SF, {"task": "rewrite", "format": "auto", **FULL,
        "transcript": "right packing for the ski trip so the stuff i always forget is goggles gloves the thermal leggings and the lip balm with spf and then separately birgit says the chalet has a hairdryer and towels so we don't need to pack those but we do need to bring our own slippers and um the lift passes are being collected on the morning of the eighteenth at the office by the gondola"},
   "Packing for the ski trip. The stuff I always forget is:\n- Goggles\n- Gloves\n- The thermal leggings\n- The lip balm with SPF\n\nSeparately, Birgit says the chalet has a hairdryer and towels, so we don't need to pack those, but we do need to bring our own slippers. The lift passes are being collected on the morning of the 18th at the office by the gondola.",
   {"numbers": ["18"], "min_negations": 1, "must_include": ["Packing for the ski trip", "- Goggles", "- Gloves", "- The thermal leggings", "- The lip balm with SPF", "Birgit says the chalet has a hairdryer and towels", "don't need to pack those", "bring our own slippers", "morning of the 18th", "office by the gondola"]},
   cx=1, note="facts: four forgotten items -> bullets; chalet has hairdryer + towels (per Birgit), so DON'T pack those; DO bring slippers; lift passes collected morning of the 18th at the gondola office; lead line kept")

# 184 auto, long numbered troubleshooting with stop/branch conditions inside steps
R2(SF, {"task": "rewrite", "format": "auto", **FULL,
        "transcript": "so this is how to fix the sync error on the shared calendar step one close outlook completely step two open the account settings and remove the shared calendar step three restart outlook and if the error is gone you can stop there step four if it's still there add the calendar back using the link in kiran's email step five if that fails too clear the offline cache and send hugo the error code"},
   "How to fix the sync error on the shared calendar:\n1. Close Outlook completely.\n2. Open the account settings and remove the shared calendar.\n3. Restart Outlook. If the error is gone, you can stop there.\n4. If it's still there, add the calendar back using the link in Kiran's email.\n5. If that fails too, clear the offline cache and send Hugo the error code.",
   {"format": "numbered", "must_include": ["How to fix the sync error on the shared calendar:", "Close Outlook completely", "remove the shared calendar", "If the error is gone, you can stop there", "If it's still there, add the calendar back", "link in Kiran's email", "If that fails too, clear the offline cache", "send Hugo the error code"]},
   cx=1, note="facts: five steps; stop at 3 IF error gone; step 4 only if still there (Kiran's link); step 5 only if that fails too (clear cache, send Hugo the code); every condition stays in its step")

# 185 markdown + instruction asks for a table; long itinerary with exact dates
R2(NM, {"task": "rewrite", "markup": "markdown", **FULL,
        "instruction": "make a table with the date, the city and where we're staying",
        "transcript": "so the euro trip is the second of may we fly into vienna and stay at the hotel by the opera for two nights then the fourth of may train to budapest and the riverside apartment for three nights and on the seventh of may we go to prague and stay at the small place near the old town until we fly home on the tenth"},
   "The Euro trip:\n\n| Date | City | Staying |\n|---|---|---|\n| May 2 | Vienna (fly in) | The hotel by the opera, two nights |\n| May 4 | Budapest (train) | The riverside apartment, three nights |\n| May 7 | Prague | The small place near the old town, until we fly home on May 10 |",
   {"numbers": ["2", "4", "7", "10"], "must_include": ["| Date | City | Staying |", "| May 2 | Vienna", "hotel by the opera, two nights", "| May 4 | Budapest", "riverside apartment, three nights", "| May 7 | Prague", "near the old town", "fly home on May 10"]},
   pos="after", cx=2, note="facts: May 2 fly into Vienna, opera hotel 2 nights; May 4 train to Budapest, riverside apt 3 nights; May 7 Prague, small place near old town until flying home May 10; dates exact; table only because markdown + instruction asks")

# 186 formal email: thanks, list of documents, firm condition, dictated 'let me know' (onboarding)
R2(SF, {"task": "rewrite", "format": "email", "register": "formal", "recipient": "Taro", "sender": "Devika", **FULL,
        "transcript": "dear taro thank you for accepting the offer um before your start date on the fourteenth of july we need the following documents a copy of your passport your signed contract proof of address from the last three months and your bank details please note that we cannot process your first salary until the bank details are received and if any of these are a problem just let me know and we can discuss"},
   "Dear Taro,\n\nThank you for accepting the offer. Before your start date on July 14, we need the following documents:\n- A copy of your passport\n- Your signed contract\n- Proof of address from the last three months\n- Your bank details\n\nPlease note that we cannot process your first salary until the bank details are received. If any of these are a problem, please let me know, and we can discuss.\n\nRegards,\nDevika",
   {"format": "email", "numbers": ["14"], "min_negations": 1, "must_include": ["Dear Taro,", "accepting the offer", "July 14", "- A copy of your passport", "- Your signed contract", "- Proof of address from the last three months", "- Your bank details", "cannot process your first salary until the bank details are received", "If any of these are a problem", "Regards,\nDevika"]},
   cx=2, note="facts: start date July 14; four documents; salary CANNOT be processed UNTIL bank details received; 'let me know and we can discuss' is dictated (formal 'please' added, no new request)")

# 187 auto, long beginner workout plan: list per day, restriction + separate condition sentence
R2(SF, {"task": "rewrite", "format": "auto", **FULL,
        "transcript": "okay so neel's beginner plan is three sessions a week monday is a thirty minute brisk walk wednesday is bodyweight stuff squats push ups against the wall and a plank for twenty seconds and saturday is a longer walk of about an hour and he should not run yet because of his ankle and if anything hurts he stops and tells me"},
   "Neel's beginner plan is three sessions a week:\n- Monday: a 30-minute brisk walk\n- Wednesday: bodyweight stuff (squats, push-ups against the wall and a plank for 20 seconds)\n- Saturday: a longer walk of about an hour\n\nHe should not run yet because of his ankle. If anything hurts, he stops and tells me.",
   {"numbers": ["30", "20"], "min_negations": 1, "must_include": ["Neel's beginner plan is three sessions a week:", "Monday: a 30-minute brisk walk", "squats, push-ups against the wall and a plank for 20 seconds", "Saturday: a longer walk of about an hour", "He should not run yet because of his ankle.", "If anything hurts, he stops and tells me."]},
   cx=1, note="facts: 3 sessions; Mon 30-min walk; Wed squats, wall push-ups, 20-second plank; Sat about an hour; must NOT run yet (ankle) is an unconditional rule in its own sentence; IF anything hurts -> stop and tell me")

# 188 note, long chem revision: list cue but note format -> terse lines, no bullets
R2(NM, {"task": "rewrite", "format": "note", **FULL,
        "transcript": "chem revision note um the three types of bonds are ionic covalent and metallic ionic is between metals and non metals covalent is between non metals and metallic is between metals the test is on the ninth and it's forty minutes long and calculators are allowed but not phones um and the practice questions are on page sixty three"},
   "Chem revision.\nThree types of bonds: ionic, covalent and metallic.\nIonic: between metals and non-metals.\nCovalent: between non-metals.\nMetallic: between metals.\nTest on the 9th, 40 minutes long.\nCalculators allowed, but not phones.\nPractice questions: page 63.",
   {"format": "note", "numbers": ["9", "40", "63"], "min_negations": 1, "must_include": ["Chem revision", "ionic, covalent and metallic", "Ionic: between metals and non-metals", "Covalent: between non-metals", "Metallic: between metals", "Test on the 9th", "40 minutes", "Calculators allowed, but not phones", "Practice questions: page 63"]},
   cx=1, note="facts: three bond types with definitions; test on the 9th, 40 minutes; calculators allowed, phones NOT; practice questions page 63; Format note -> terse lines, no '- ' bullets")

# 189 explicit prose beats order cues; long routine with an incident exception
R2(SF, {"task": "rewrite", "format": "prose", **FULL,
        "transcript": "so the way i do the morning routine is first i check the overnight alerts then i look at the ticket queue and assign anything urgent then i reply to the team chat and finally i update the status board before the standup at nine thirty and if there's a major incident i skip all that and go straight to the incident channel and taro covers the queue on those days"},
   "The way I do the morning routine is this: first, I check the overnight alerts, then I look at the ticket queue and assign anything urgent, then I reply to the team chat, and finally I update the status board before the standup at 9:30. If there's a major incident, I skip all that and go straight to the incident channel. Taro covers the queue on those days.",
   {"format": "prose", "numbers": ["9:30"], "must_include": ["overnight alerts", "assign anything urgent", "team chat", "status board before the standup at 9:30", "If there's a major incident, I skip all that", "incident channel", "Taro covers the queue on those days"], "must_not_include": ["1. "]},
   cx=1, note="facts: four routine steps in order, status board before 9:30 standup; IF major incident -> skip routine, go to incident channel; Taro covers the queue on those (incident) days; Format prose beats the first/then/finally cues")

# 190 nl_instruction: numbered steps, money kept on a separate closing line (en-in)
R2(NL, {"task": "rewrite", "locale": "en-in",
        "instruction": "turn it into numbered steps but keep the money stuff in a separate line at the end",
        "transcript": "for registering the scooter in the new state um first get the noc from the old rto then take the papers to the new rto with the insurance and pollution certificate then they inspect the scooter and finally you get the new number plate and the fees are around four thousand five hundred rupees plus the road tax which kiran thinks is about eight percent"},
   "For registering the scooter in the new state:\n1. Get the NOC from the old RTO.\n2. Take the papers to the new RTO with the insurance and pollution certificate.\n3. They inspect the scooter.\n4. You get the new number plate.\n\nThe fees are around ₹4,500, plus the road tax, which Kiran thinks is about 8%.",
   {"numbers": ["4,500", "8%"], "must_include": ["For registering the scooter in the new state:", "1. Get the NOC from the old RTO.", "insurance and pollution certificate", "They inspect the scooter", "4. You get the new number plate.", "around ₹4,500", "road tax", "Kiran thinks is about 8%"]},
   pos="after", cx=2, note="facts: four steps in order; fees AROUND ₹4,500 (rupees spoken) plus road tax that Kiran THINKS is about 8% (hedges kept); money on its own closing line as instructed")

# 191 auto, long study-group reflection, no list cue -> prose
R2(SF, {"task": "rewrite", "format": "auto", **FULL,
        "transcript": "honestly the study group isn't working the way we planned we meet every tuesday but half the time people haven't done the reading and we end up just chatting so rhea suggested we each take one chapter and present it for ten minutes which i like and we're going to try it for the next three weeks and see and if that doesn't help we'll probably just meet every two weeks instead"},
   "Honestly, the study group isn't working the way we planned. We meet every Tuesday, but half the time people haven't done the reading, and we end up just chatting. Rhea suggested we each take one chapter and present it for 10 minutes, which I like, and we're going to try it for the next three weeks and see. If that doesn't help, we'll probably just meet every two weeks instead.",
   {"format": "prose", "numbers": ["10"], "min_negations": 2, "must_include": ["Honestly", "isn't working the way we planned", "every Tuesday", "half the time people haven't done the reading", "Rhea suggested", "one chapter", "10 minutes", "which I like", "next three weeks and see", "If that doesn't help, we'll probably just meet every two weeks instead"]},
   cx=1, note="facts: meets every Tuesday; half the time reading NOT done; Rhea's suggestion one chapter each, 10 minutes; trial for the next three weeks; IF that doesn't help, PROBABLY every two weeks instead (condition + hedge); no list cue -> prose")

# 192 markdown + instruction: headings for ingredients and steps, bold the temperature (recipe)
R2(NM, {"task": "rewrite", "markup": "markdown",
        "instruction": "headings for the ingredients and the steps, and bold the oven temperature",
        "transcript": "this is how kiran makes his flatbread the ingredients are two cups of flour a cup of yoghurt a teaspoon of baking powder and a pinch of salt the steps are mix everything into a soft dough rest it for twenty minutes split it into six balls roll them thin and cook them in a hot pan or in the oven at two hundred and twenty for about five minutes"},
   "This is how Kiran makes his flatbread.\n\n## Ingredients\n\n- 2 cups of flour\n- A cup of yoghurt\n- A teaspoon of baking powder\n- A pinch of salt\n\n## Steps\n\n1. Mix everything into a soft dough.\n2. Rest it for 20 minutes.\n3. Split it into six balls.\n4. Roll them thin.\n5. Cook them in a hot pan or in the oven at **220** for about 5 minutes.",
   {"numbers": ["2", "20", "220", "5"], "must_include": ["Kiran makes his flatbread", "## Ingredients", "2 cups of flour", "A cup of yoghurt", "baking powder", "A pinch of salt", "## Steps", "Rest it for 20 minutes", "six balls", "Roll them thin", "hot pan or in the oven at **220** for about 5 minutes"], "must_not_include": ["# Kiran"]},
   pos="after", cx=3, note="facts: 2 cups flour, a cup yoghurt, a tsp baking powder, pinch salt; rest 20 min; six balls; pan OR oven at 220 (no unit spoken) for about 5 minutes, kept in the speaker's order; only the two requested headings (no invented title heading) and bold only on 220")

# 193 neutral email, 'two things' -> one sentence (no bullets), dictated closing request + condition
R2(SF, {"task": "rewrite", "format": "email", "recipient": "Neel", **FULL,
        "transcript": "hi neel thanks for covering the night shift handover last week um just two things for this week the server patch is now on thursday instead of wednesday and the backup check moved to friday morning and nothing else changes so the rest of the rota stays the same let me know if thursday doesn't work for you and if it doesn't we can ask omkar to swap"},
   "Hi Neel,\n\nThanks for covering the night shift handover last week. Just two things for this week: the server patch is now on Thursday instead of Wednesday, and the backup check moved to Friday morning. Nothing else changes, so the rest of the rota stays the same.\n\nLet me know if Thursday doesn't work for you. If it doesn't, we can ask Omkar to swap.",
   {"format": "email", "min_negations": 1, "must_include": ["Hi Neel,", "night shift handover last week", "two things", "server patch is now on Thursday instead of Wednesday", "backup check moved to Friday morning", "Nothing else changes", "rota stays the same", "Let me know if Thursday doesn't work for you", "If it doesn't, we can ask Omkar to swap"], "must_not_include": ["- "]},
   cx=1, note="facts: patch Thursday instead of Wednesday; backup check Friday morning; nothing else changes; IF Thursday doesn't work -> can ask Omkar to swap; only two items -> stays a sentence inside the email; no sender -> no sign-off")

# 194 note, long travel prep with exact date/time and a negation
R2(NM, {"task": "rewrite", "format": "note", **FULL,
        "transcript": "note for the trip to nairobi um flight's on the twenty third of august at six fifty am from terminal two yellow fever certificate is required so get that sorted this week the hotel is booked for five nights but the airport pickup isn't confirmed yet and remember to tell the bank about the travel dates and to download the offline maps"},
   "Nairobi trip.\nFlight: August 23, 6:50 a.m., Terminal 2.\nYellow fever certificate required: get it sorted this week.\nHotel booked for five nights.\nAirport pickup not confirmed yet.\nTell the bank about the travel dates.\nDownload the offline maps.",
   {"format": "note", "numbers": ["23", "6:50", "2"], "min_negations": 1, "must_include": ["Nairobi", "August 23, 6:50 a.m., Terminal 2", "Yellow fever certificate required", "this week", "five nights", "Airport pickup not confirmed yet", "Tell the bank about the travel dates", "offline maps"]},
   cx=1, note="facts: flight Aug 23 6:50 a.m. Terminal 2; yellow fever cert required, sort this week; hotel 5 nights; pickup NOT confirmed yet; tell bank; offline maps")

# 195 auto, long offboarding checklist: timing restriction, optional item with condition
R2(SF, {"task": "rewrite", "format": "auto", **FULL,
        "transcript": "offboarding checklist for when taro leaves on the thirtieth um disable his accounts at five pm on his last day not before collect the laptop and the badge forward his email to devika for a month and um remove him from the on call rota and also we should do an exit chat but that's optional if he doesn't want one"},
   "Offboarding checklist for when Taro leaves on the 30th:\n- Disable his accounts at 5 p.m. on his last day, not before\n- Collect the laptop and the badge\n- Forward his email to Devika for a month\n- Remove him from the on-call rota\n- Do an exit chat, but that's optional if he doesn't want one",
   {"format": "bullets", "numbers": ["30", "5"], "min_negations": 2, "must_include": ["Offboarding checklist for when Taro leaves on the 30th:", "Disable his accounts at 5 p.m. on his last day, not before", "Collect the laptop and the badge", "Forward his email to Devika for a month", "on-call rota", "exit chat", "optional if he doesn't want one"]},
   cx=1, note="facts: leaves the 30th; disable accounts at 5 p.m. last day, NOT before; laptop+badge; email to Devika for a month; off on-call rota; exit chat optional if he doesn't want one")

# 196 auto, long hotel-room workout: lead, numbered circuit, closing repeat + condition + hedge
R2(SF, {"task": "rewrite", "format": "auto", **FULL,
        "transcript": "the hotel room workout is um ten squats then ten push ups then fifteen lunges each leg then a thirty second plank then rest for a minute and do the whole thing four times and if your wrist is still sore swap the push ups for wall push ups and do this on the days you can't get to the gym which is probably tuesday and thursday this week"},
   "The hotel room workout:\n1. 10 squats\n2. 10 push-ups\n3. 15 lunges each leg\n4. A 30-second plank\n5. Rest for a minute\n\nDo the whole thing four times. If your wrist is still sore, swap the push-ups for wall push-ups. Do this on the days you can't get to the gym, which is probably Tuesday and Thursday this week.",
   {"numbers": ["10", "15", "30"], "min_negations": 1, "must_include": ["The hotel room workout:", "1. 10 squats", "2. 10 push-ups", "3. 15 lunges each leg", "4. A 30-second plank", "5. Rest for a minute", "whole thing four times", "If your wrist is still sore, swap the push-ups for wall push-ups", "days you can't get to the gym", "probably Tuesday and Thursday this week"]},
   cx=1, waivers=["number_missing", "number_invented"], note="facts: 10 squats, 10 push-ups, 15 lunges each leg, 30-second plank, rest a minute (order cue 'then'); four rounds; wall push-ups only IF wrist still sore; gym-less days PROBABLY Tue and Thu (hedge); waiver: checker reads 'thirty second plank' as 32 instead of a 30-second plank")

# 197 plain + instruction asks for headings -> label lines; long day plan with a condition
R2(NM, {"task": "rewrite", **FULL,
        "instruction": "use headings for the morning and the afternoon",
        "transcript": "so this is the plan for the day in the old city in the morning we do the walking tour at nine from the clock tower and then coffee at the square and um in the afternoon the boat trip at two thirty and after that if hugo's too tired we skip the castle and just go back to the hotel otherwise we walk up to the castle for sunset"},
   "Plan for the day in the old city.\n\nMorning:\nThe walking tour at 9 from the clock tower, then coffee at the square.\n\nAfternoon:\nThe boat trip at 2:30. After that, if Hugo's too tired, we skip the castle and just go back to the hotel; otherwise, we walk up to the castle for sunset.",
   {"numbers": ["9", "2:30"], "must_include": ["old city", "Morning:", "walking tour at 9 from the clock tower", "coffee at the square", "Afternoon:", "boat trip at 2:30", "if Hugo's too tired, we skip the castle", "back to the hotel", "otherwise, we walk up to the castle for sunset"], "must_not_include": ["#", "**"]},
   pos="after", cx=2, note="facts: walking tour 9 from the clock tower, then coffee; boat trip 2:30; IF Hugo too tired skip castle and go back, OTHERWISE castle for sunset; Markup plain -> 'Morning:'/'Afternoon:' label lines, no '#'")

# 198 auto, short list cue -> bullets (shopping)
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "shopping list onions garlic lemons and uh rice"},
   "Shopping list:\n- Onions\n- Garlic\n- Lemons\n- Rice",
   {"format": "bullets", "must_include": ["Shopping list:", "- Onions", "- Garlic", "- Lemons", "- Rice"]},
   cx=0, note="list cue 'shopping list' + four items -> bullets with the lead line")

# 199 auto, short, sequence of two plans -> sentence
R2(SF, {"task": "rewrite",
        "transcript": "gym at six then dinner with alma at eight"},
   "Gym at 6, then dinner with Alma at 8.",
   {"format": "prose", "numbers": ["6", "8"], "must_include": ["Gym at 6", "dinner with Alma at 8"], "must_not_include": ["1. ", "- "]},
   cx=0, note="facts: gym at 6, dinner with Alma at 8; two items -> one line, no list")

# 200 plain markup + instruction for a table -> label lines, no pipes (travel day)
R2(NM, {"task": "rewrite", "markup": "plain", **FULL,
        "instruction": "make it a table",
        "transcript": "flight's at noon hotel check in at three and dinner at seven thirty"},
   "Flight: noon\nHotel check-in: 3\nDinner: 7:30",
   {"numbers": ["3", "7:30"], "must_include": ["Flight: noon", "Hotel check-in: 3", "Dinner: 7:30"], "must_not_include": ["|", "**"]},
   pos="after", cx=1, note="facts: flight noon, check-in 3, dinner 7:30; Markup plain allows no tables -> one 'label: time' line each")

# 201 note, short
R2(SF, {"task": "rewrite", "format": "note",
        "transcript": "note buy stamps and post the forms by friday"},
   "Buy stamps and post the forms by Friday.",
   {"format": "note", "must_include": ["Buy stamps", "post the forms by Friday"]},
   cx=0, note="facts: forms posted by Friday; two items -> one terse line")

# 202 cleanup, dictated 'first item / second item / third item' -> numbered kept
R2(SF, {"task": "cleanup",
        "transcript": "first item passport second item tickets third item the plug adapter"},
   "1. Passport\n2. Tickets\n3. The plug adapter",
   {"format": "numbered", "must_include": ["1. Passport", "2. Tickets", "3. The plug adapter"], "must_not_include": ["item"]},
   cx=0, note="cleanup keeps the dictated ordered list ('first item / second item / third item') as numbering; cue words removed")

# 203 nl_instruction: explicit 'two bullet points' beats two-items-stay-a-sentence
R2(NL, {"task": "rewrite",
        "instruction": "as two bullet points",
        "transcript": "rhea's bringing plates and kiran's bringing cups"},
   "- Rhea's bringing plates.\n- Kiran's bringing cups.",
   {"format": "bullets", "must_include": ["- Rhea's bringing plates.", "- Kiran's bringing cups."]},
   pos="after", cx=1, note="facts: Rhea plates, Kiran cups; the instruction asks for bullets, which beats the two-items-stay-a-sentence default")

# 204 markdown + instruction: bold the deadline only (study)
R2(NM, {"task": "rewrite", "markup": "markdown",
        "instruction": "bold the deadline",
        "transcript": "submit the lab report by nine am monday"},
   "Submit the lab report by **9 a.m. Monday**.",
   {"numbers": ["9"], "must_include": ["Submit the lab report by **9 a.m. Monday**."]},
   pos="after", cx=1, note="facts: deadline 9 a.m. Monday, bolded as instructed; nothing else marked up")

# 205 auto, long study plan; nested sub-bullets only because dictated 'under that'
R2(SF, {"task": "rewrite", "format": "auto", "locale": "en-gb", **FULL,
        "transcript": "my study plan for the week has three subjects maths and under that it's the integration problems and the past paper from twenty nineteen then physics and under that it's the circuits chapter and the lab write up and then english and under that it's just finishing the essay draft and i'm doing maths every morning because that's when i'm sharpest"},
   "My study plan for the week has three subjects:\n- Maths\n\t- The integration problems\n\t- The past paper from 2019\n- Physics\n\t- The circuits chapter\n\t- The lab write-up\n- English\n\t- Finishing the essay draft\n\nI'm doing maths every morning because that's when I'm sharpest.",
   {"numbers": ["2019"], "must_include": ["My study plan for the week has three subjects:", "- Maths", "integration problems", "past paper from 2019", "- Physics", "circuits chapter", "lab write-up", "- English", "Finishing the essay draft", "maths every morning", "when I'm sharpest"]},
   cx=1, note="facts: maths (integration problems, 2019 past paper), physics (circuits chapter, lab write-up), English (finish essay draft); maths every morning; nested sub-bullets ONLY because dictated 'under that', indented with one tab (kit forbids double spaces); closing sentence stays prose")

# 206 note, long physio notes: measurements, date, two restrictions
R2(NM, {"task": "rewrite", "format": "note", **FULL,
        "transcript": "note from the physio session um left knee is improving range is up to one twenty degrees from ninety last month keep doing the band exercises twice a day no running until the next review on the fourth of november and cycling is fine but only on the flat and for no more than thirty minutes and uh bring the shorts again next time"},
   "Physio session.\nLeft knee improving: range up to 120 degrees, from 90 last month.\nKeep doing the band exercises twice a day.\nNo running until the next review on November 4.\nCycling is fine, but only on the flat and for no more than 30 minutes.\nBring the shorts again next time.",
   {"format": "note", "numbers": ["120", "90", "4", "30"], "min_negations": 2, "must_include": ["Physio session", "Left knee improving", "120 degrees", "from 90 last month", "band exercises twice a day", "No running until the next review on November 4", "only on the flat", "no more than 30 minutes", "Bring the shorts again next time"]},
   cx=1, note="facts: range 120 degrees, up from 90 last month; band exercises twice a day; NO running until review Nov 4; cycling only on the flat and NO more than 30 minutes")

# 207 message with a list ('can you grab these'), then a condition and a separate request
R2(SF, {"task": "rewrite", "format": "message", "context": "chat", **FULL,
        "transcript": "omkar since you're going to the big supermarket can you grab these for the party two bags of ice the paper plates a pack of lemons and the vegan sausages for lise and if they don't have the vegan ones get the halloumi instead and keep the receipt so i can pay you back i'll be home by six"},
   "Omkar, since you're going to the big supermarket, can you grab these for the party:\n- Two bags of ice\n- The paper plates\n- A pack of lemons\n- The vegan sausages for Lise\n\nIf they don't have the vegan ones, get the halloumi instead. Keep the receipt so I can pay you back. I'll be home by 6.",
   {"min_negations": 1, "numbers": ["6"], "must_include": ["Omkar, since you're going to the big supermarket", "for the party", "- Two bags of ice", "- The paper plates", "- A pack of lemons", "- The vegan sausages for Lise", "If they don't have the vegan ones, get the halloumi instead.", "Keep the receipt so I can pay you back.", "I'll be home by 6."]},
   cx=1, note="facts: four items (cue 'grab these'); halloumi only IF no vegan sausages; keeping the receipt is unconditional, so it gets its own sentence; speaker home by 6; vocative from the spoken name (format assertion omitted: checker forbids lists in messages)")

# 208 explicit prose + formal: dictated points become sentences (onboarding guide)
R2(SF, {"task": "rewrite", "format": "prose", "register": "formal", **FULL,
        "transcript": "for the new starters guide the main points are they must complete the security training before getting system access they should book a desk through the app and not just sit anywhere expense claims go through devika's team and have to be submitted within thirty days and the parking permit request goes to hugo at least a week in advance and um lunch on the first day is provided by the team"},
   "For the new starters' guide, the main points are as follows. New starters must complete the security training before getting system access. They should book a desk through the app and not simply sit anywhere. Expense claims go through Devika's team and must be submitted within 30 days. Parking permit requests go to Hugo at least a week in advance. Lunch on the first day is provided by the team.",
   {"format": "prose", "numbers": ["30"], "min_negations": 1, "must_include": ["new starters' guide", "must complete the security training before getting system access", "book a desk through the app and not simply sit anywhere", "Devika's team", "within 30 days", "Hugo at least a week in advance", "Lunch on the first day is provided by the team"], "must_not_include": ["- "]},
   cx=2, note="facts: security training BEFORE system access; desk via app, NOT anywhere; expenses via Devika's team within 30 days; parking permit to Hugo at least a week ahead; first-day lunch provided by the team; explicit prose beats the 'main points' list cue")

# 209 nl_instruction + Wording keep: only the item list becomes bullets
R2(NL, {"task": "rewrite", "format": "auto", "wording": "keep",
        "instruction": "keep my wording, just make the list a proper bulleted list and leave the rest as sentences",
        "transcript": "okay so for the study trip to the museum next friday um we meet at the main gate at eight fifteen and the coach leaves at eight thirty sharp so don't be late and you need to bring a few things your student id a packed lunch a notebook and a pencil not a pen because pens aren't allowed in the archive room and we'll be back by four"},
   "For the study trip to the museum next Friday, we meet at the main gate at 8:15, and the coach leaves at 8:30 sharp, so don't be late. You need to bring a few things:\n- Your student ID\n- A packed lunch\n- A notebook\n- A pencil, not a pen, because pens aren't allowed in the archive room\n\nWe'll be back by 4.",
   {"numbers": ["8:15", "8:30", "4"], "min_negations": 3, "must_include": ["study trip to the museum next Friday", "main gate at 8:15", "8:30 sharp", "don't be late", "You need to bring a few things:", "- Your student ID", "- A packed lunch", "- A notebook", "- A pencil, not a pen, because pens aren't allowed in the archive room", "We'll be back by 4."]},
   pos="after", cx=3, note="facts: meet 8:15 main gate; coach 8:30 sharp; pencil NOT pen (pens not allowed in archive room); back by 4; Wording keep: only fillers removed, words unchanged; only the item list becomes bullets")

# 210 explicit bullets beat a [Rules] 'never bullets' preference (printer known issues)
R2(SF, {"task": "rewrite", "format": "bullets", "rules": ["Never use bullet points; write everything as prose."], **FULL,
        "transcript": "known issues with the new printer the double sided setting resets after every job the scan to email only works on the office wifi not the guest network the colour toner shows empty even when it isn't and the touchscreen freezes if you press it too fast so press once and wait omkar has logged all of these with the supplier"},
   "Known issues with the new printer:\n- The double-sided setting resets after every job.\n- Scan to email only works on the office Wi-Fi, not the guest network.\n- The colour toner shows empty even when it isn't.\n- The touchscreen freezes if you press it too fast, so press once and wait.\n- Omkar has logged all of these with the supplier.",
   {"format": "bullets", "min_negations": 2, "must_include": ["Known issues with the new printer:", "resets after every job", "only works on the office Wi-Fi, not the guest network", "shows empty even when it isn't", "freezes if you press it too fast, so press once and wait", "Omkar has logged all of these with the supplier"]},
   cx=2, note="facts: four issues (scan only on office Wi-Fi, NOT guest; toner shows empty even when it ISN'T; freeze if pressed too fast); Omkar logged all with the supplier; this turn's Format bullets beats the saved 'never bullets' rule")

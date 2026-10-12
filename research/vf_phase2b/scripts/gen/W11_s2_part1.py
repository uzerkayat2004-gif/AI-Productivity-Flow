# W11 stage 2, part 1: TC-W11-101..140 (exec'd by W11.py; uses R2, SF, NM, NL)

# 101 auto, "the ingredients are" + 5 items -> bullets with lead line (recipe)
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "right the ingredients for omkar's tomato soup are um six ripe tomatoes one red onion two cloves of garlic half a litre of veg stock and a splash of cream"},
   "The ingredients for Omkar's tomato soup are:\n- 6 ripe tomatoes\n- 1 red onion\n- 2 cloves of garlic\n- Half a litre of veg stock\n- A splash of cream",
   {"format": "bullets", "numbers": ["6", "1", "2"], "must_include": ["Omkar's tomato soup", "ripe tomatoes", "red onion", "cloves of garlic", "Half a litre of veg stock", "splash of cream"]},
   cx=1, waivers=["number_invented"], note="facts: 6 tomatoes, 1 red onion, 2 garlic cloves, half a litre stock, a splash of cream; recipe quantities as digits; lead line kept; waiver: checker does not read spoken 'one' as 1")

# 102 auto, 2 items -> sentence (packing)
R2(SF, {"task": "rewrite",
        "transcript": "lise don't forget the passport and uh the charger for the camera"},
   "Lise, don't forget the passport and the charger for the camera.",
   {"format": "prose", "min_negations": 1, "must_include": ["Lise", "passport", "charger for the camera"], "must_not_include": ["- "]},
   cx=1, note="facts: two items only -> one sentence; negation 'don't forget' kept")

# 103 auto, order cues + embedded condition kept inside a step (troubleshooting)
R2(SF, {"task": "rewrite", "format": "auto", "header_style": "full",
        "transcript": "if the printer jams again first switch it off then open the back panel and pull the paper out slowly then check the roller and if the roller is torn don't use it just call omkar otherwise close the panel and switch it back on"},
   "If the printer jams again:\n1. Switch it off.\n2. Open the back panel and pull the paper out slowly.\n3. Check the roller. If the roller is torn, don't use it; just call Omkar.\n4. Otherwise, close the panel and switch it back on.",
   {"format": "numbered", "min_negations": 1, "must_include": ["If the printer jams again", "pull the paper out slowly", "If the roller is torn, don't use it", "call Omkar", "Otherwise, close the panel"]},
   cx=1, note="facts: whole list scoped by 'if the printer jams again'; torn roller -> don't use it, call Omkar; otherwise close panel and switch on; order cues first/then -> numbered")

# 104 note, workout (terse lines)
R2(NM, {"task": "rewrite", "format": "note",
        "transcript": "note to self monday leg day three sets of squats twelve reps uh lunges ten each side and skip the deadlifts until my back feels better"},
   "Monday: leg day.\nSquats: 3 sets of 12 reps.\nLunges: 10 each side.\nSkip the deadlifts until my back feels better.",
   {"format": "note", "numbers": ["3", "12", "10"], "must_include": ["Monday", "Squats", "Lunges", "each side", "Skip the deadlifts until my back feels better"]},
   cx=1, note="facts: Monday leg day; squats 3 sets of 12 reps; lunges 10 each side; skip deadlifts UNTIL back feels better (condition kept)")

# 105 auto, "step one..step five" with a jump condition (router troubleshooting)
R2(SF, {"task": "rewrite", "format": "auto", "header_style": "full",
        "transcript": "okay so the router steps step one check the lights on the front step two if the internet light is red go to step four step three if it's green restart your laptop and you're done step four unplug the router for thirty seconds and plug it back in step five wait two minutes and test again"},
   "Router steps:\n1. Check the lights on the front.\n2. If the internet light is red, go to step 4.\n3. If it's green, restart your laptop and you're done.\n4. Unplug the router for 30 seconds and plug it back in.\n5. Wait 2 minutes and test again.",
   {"format": "numbered", "numbers": ["4", "30", "2"], "must_include": ["If the internet light is red, go to step 4", "If it's green, restart your laptop", "you're done", "Unplug the router for 30 seconds", "test again"]},
   cx=1, note="facts: red light -> go to step 4 (jump kept, step number matches list); green -> restart laptop, done; unplug 30 seconds; wait 2 minutes; five steps in order")

# 106 bullets, plain, self-correction on a quantity (shopping)
R2(NM, {"task": "rewrite", "format": "bullets",
        "transcript": "shopping list um oat milk two cartons sorry three cartons bananas spinach and the big bag of rice"},
   "Shopping list:\n- Oat milk, 3 cartons\n- Bananas\n- Spinach\n- The big bag of rice",
   {"format": "bullets", "numbers": ["3"], "must_include": ["Shopping list:", "Oat milk", "Bananas", "Spinach", "big bag of rice"], "must_not_include": ["2 cartons", "two cartons"]},
   cx=1, note="facts: self-correction two -> 3 cartons of oat milk; bananas, spinach, big bag of rice; lead line kept")

# 107 auto, travel with dates, no list cue -> prose, hedge + both dates kept
R2(SF, {"task": "rewrite", "locale": "en-gb",
        "transcript": "so we land in lisbon on the ninth at like half seven in the evening and then we've got the train to porto on the eleventh but um kiran wants to stay an extra night in porto so we might come back on the fourteenth instead of the thirteenth"},
   "We land in Lisbon on the 9th at about 7:30 in the evening, and then we've got the train to Porto on the 11th. Kiran wants to stay an extra night in Porto, so we might come back on the 14th instead of the 13th.",
   {"format": "prose", "numbers": ["9", "7:30", "11", "14", "13"], "must_include": ["Lisbon", "Porto", "Kiran", "extra night", "might come back on the 14th instead of the 13th"]},
   cx=1, note="facts: land Lisbon 9th about 7:30 p.m. ('like' -> about); train to Porto 11th; Kiran wants an extra night; return MIGHT be 14th instead of 13th (hedge); no list cue -> prose")

# 108 markdown + instruction asks for a table (workout week)
R2(NM, {"task": "rewrite", "markup": "markdown",
        "instruction": "put it in a table with a day column and a workout column",
        "transcript": "this week's plan monday upper body tuesday a forty minute run wednesday rest thursday legs and friday yoga"},
   "This week's plan:\n\n| Day | Workout |\n|---|---|\n| Monday | Upper body |\n| Tuesday | 40-minute run |\n| Wednesday | Rest |\n| Thursday | Legs |\n| Friday | Yoga |",
   {"numbers": ["40"], "must_include": ["This week's plan", "| Day | Workout |", "| Monday | Upper body |", "40-minute run", "| Wednesday | Rest |", "| Friday | Yoga |"]},
   pos="after", cx=2, note="facts: five days Mon-Fri, Tuesday 40-minute run, Wednesday rest; table only because markup markdown AND the instruction asks for one; lead line kept")

# 109 plain markup + instruction asks for a table -> no table, one line per slot (study)
R2(NM, {"task": "rewrite", "markup": "plain", "header_style": "full", "locale": "en-gb",
        "instruction": "put this in a table",
        "transcript": "revision timetable um saturday morning chemistry saturday afternoon maths sunday morning physics and sunday afternoon past papers"},
   "Revision timetable:\nSaturday morning: chemistry\nSaturday afternoon: maths\nSunday morning: physics\nSunday afternoon: past papers",
   {"must_include": ["Revision timetable:", "Saturday morning: chemistry", "Saturday afternoon: maths", "Sunday morning: physics", "Sunday afternoon: past papers"], "must_not_include": ["|", "**"]},
   pos="after", cx=2, note="facts: four slots kept in order; Markup plain allows no tables, so the table request becomes one 'slot: subject' line each (no pipes)")

# 110 cleanup, speaker dictated 'number one/two/three' -> numbered kept (study notes)
R2(SF, {"task": "cleanup",
        "transcript": "study notes for thursday number one photosynthesis happens in the chloroplast number two it needs light water and carbon dioxide number three oxygen is the by-product"},
   "Study notes for Thursday:\n1. Photosynthesis happens in the chloroplast.\n2. It needs light, water and carbon dioxide.\n3. Oxygen is the by-product.",
   {"format": "numbered", "must_include": ["Study notes for Thursday", "chloroplast", "light, water and carbon dioxide", "Oxygen is the by-product"]},
   cx=0, note="cleanup keeps the dictated list form: speaker dictated 'number one/two/three' -> numbered; wording unchanged")

# 111 cleanup, items without cue -> stays prose (packing)
R2(SF, {"task": "cleanup",
        "transcript": "we need to pack the tent the the stove and the sleeping mats and uh hugo is bringing the cool box"},
   "We need to pack the tent, the stove and the sleeping mats, and Hugo is bringing the cool box.",
   {"format": "prose", "must_include": ["tent", "stove", "sleeping mats", "Hugo is bringing the cool box"], "must_not_include": ["- "]},
   cx=0, note="cleanup without dictated list cues keeps prose; Hugo brings the cool box")

# 112 email with a 3-item list cue inside the body (onboarding)
R2(SF, {"task": "rewrite", "format": "email", "recipient": "Devika",
        "transcript": "hi devika welcome to the team um before monday can you do a few things set up your laptop with the it desk read the handbook and send me your bank details for payroll and on monday we'll start at nine thirty in the main office"},
   "Hi Devika,\n\nWelcome to the team. Before Monday, can you do a few things:\n- Set up your laptop with the IT desk\n- Read the handbook\n- Send me your bank details for payroll\n\nOn Monday, we'll start at 9:30 in the main office.",
   {"format": "email", "numbers": ["9:30"], "must_include": ["Hi Devika,", "Welcome to the team", "IT desk", "handbook", "bank details for payroll", "main office"]},
   cx=1, note="facts: three tasks before Monday (list cue 'a few things' -> bullets inside the email); Monday start 9:30 in the main office; no sender -> no sign-off")

# 113 note, onboarding with a negation
R2(NM, {"task": "rewrite", "format": "note",
        "transcript": "note for the onboarding of taro he starts on the third um badge from reception laptop is ready but the vpn access isn't approved yet so chase alma about that"},
   "Onboarding for Taro: starts on the 3rd.\nBadge from reception.\nLaptop is ready.\nVPN access not approved yet: chase Alma about that.",
   {"format": "note", "numbers": ["3"], "min_negations": 1, "must_include": ["Taro", "Badge from reception", "Laptop is ready", "VPN access not approved yet", "chase Alma"]},
   cx=1, note="facts: Taro starts the 3rd; badge from reception; laptop ready; VPN NOT approved yet -> chase Alma")

# 114 auto, 3 parallel facts but no list cue -> prose (travel)
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "the hotel's near the station the museum's a ten minute walk and the market's open till six"},
   "The hotel's near the station, the museum's a 10-minute walk, and the market's open till 6.",
   {"format": "prose", "numbers": ["10", "6"], "must_include": ["near the station", "10-minute walk", "open till 6"], "must_not_include": ["- "]},
   cx=1, note="facts: 10-minute walk; market open till 6; three facts but no list cue -> prose")

# 115 auto, 'packing list' cue, conditional + negation on last item (trek)
R2(SF, {"task": "rewrite", "format": "auto", "header_style": "full",
        "transcript": "packing list for the trek um boots two pairs of wool socks a rain jacket the head torch and maybe the small stove if birgit isn't bringing hers"},
   "Packing list for the trek:\n- Boots\n- 2 pairs of wool socks\n- A rain jacket\n- The head torch\n- Maybe the small stove, if Birgit isn't bringing hers",
   {"format": "bullets", "numbers": ["2"], "min_negations": 1, "must_include": ["Packing list for the trek:", "Boots", "wool socks", "rain jacket", "head torch", "Maybe the small stove, if Birgit isn't bringing hers"]},
   cx=1, note="facts: 2 pairs of socks; stove is hedged 'maybe' AND conditional on Birgit NOT bringing hers")

# 116 markdown + instruction: bold only the times (itinerary)
R2(NM, {"task": "rewrite", "markup": "markdown",
        "instruction": "bold the times, nothing else",
        "transcript": "on the twelfth the coach leaves the hotel at seven fifteen we reach the lake around ten and lunch is at one at the boathouse"},
   "On the 12th, the coach leaves the hotel at **7:15**, we reach the lake around **10**, and lunch is at **1** at the boathouse.",
   {"numbers": ["12", "7:15", "10", "1"], "must_include": ["**7:15**", "around **10**", "**1**", "boathouse"], "must_not_include": ["**12", "**On", "**the"]},
   pos="after", cx=2, note="facts: the 12th; coach 7:15; lake AROUND 10 (hedge kept); lunch at 1 at the boathouse; only the three times are bold")

# 117 explicit prose beats the dictated step cues (recipe)
R2(SF, {"task": "rewrite", "format": "prose",
        "transcript": "first preheat the oven to two hundred then toss the potatoes in oil and salt then roast them for forty minutes turning once halfway"},
   "First, preheat the oven to 200, then toss the potatoes in oil and salt and roast them for 40 minutes, turning once halfway.",
   {"format": "prose", "numbers": ["200", "40"], "must_include": ["preheat the oven to 200", "oil and salt", "40 minutes", "turning once halfway"], "must_not_include": ["1. ", "degrees"]},
   cx=1, note="facts: oven to 200 (no unit spoken, none added); roast 40 minutes, turn once halfway; Format prose beats the order cues -> one sentence, no numbering")

# 118 auto + instruction 'number the steps' (onboarding)
R2(SF, {"task": "rewrite", "format": "auto",
        "instruction": "number the steps",
        "transcript": "for new starters on day one they get their badge from omkar then they sit with lise for the systems walkthrough and in the afternoon they shadow the support queue"},
   "For new starters on day one:\n1. They get their badge from Omkar.\n2. They sit with Lise for the systems walkthrough.\n3. In the afternoon, they shadow the support queue.",
   {"format": "numbered", "must_include": ["For new starters on day one:", "badge from Omkar", "Lise", "systems walkthrough", "In the afternoon", "shadow the support queue"]},
   pos="after", cx=1, note="facts: badge from Omkar, walkthrough with Lise, support queue in the afternoon; numbered because instructed; lead line kept")

# 119 bullets, nested detail only because dictated 'under that' (packing, plain)
R2(NM, {"task": "rewrite", "format": "bullets",
        "transcript": "packing list clothes and under that three t-shirts a jumper and swim shorts then toiletries and under that toothbrush sunscreen and the travel shampoo then documents and under that passport and the insurance printout"},
   "Packing list:\n- Clothes\n\t- Three T-shirts\n\t- A jumper\n\t- Swim shorts\n- Toiletries\n\t- Toothbrush\n\t- Sunscreen\n\t- The travel shampoo\n- Documents\n\t- Passport\n\t- The insurance printout",
   {"must_include": ["Packing list:", "- Clothes", "Three T-shirts", "Swim shorts", "- Toiletries", "travel shampoo", "- Documents", "insurance printout"], "must_not_include": ["**", "#"]},
   cx=1, note="facts: three groups with their items; nested sub-bullets ONLY because the speaker dictated 'under that'; sub-items indented with one tab (kit forbids double spaces); format assertion omitted because the checker reads indented lines as malformed bullets")

# 120 auto, 'couple of things' + 2 items -> sentence (study group)
R2(SF, {"task": "rewrite",
        "transcript": "couple of things for the study group neel's bringing the flashcards and we're doing chapter seven"},
   "Couple of things for the study group: Neel's bringing the flashcards, and we're doing chapter 7.",
   {"format": "prose", "numbers": ["7"], "must_include": ["study group", "Neel's bringing the flashcards", "chapter 7"], "must_not_include": ["- "]},
   cx=1, note="facts: Neel brings flashcards; chapter 7; only two items -> one sentence")

# 121 cleanup + bullets, en-in shopping, condition on last item
R2(SF, {"task": "cleanup", "format": "bullets", "locale": "en-in",
        "transcript": "um from the market we need uh coriander green chillies a kilo of onions and paneer if it's fresh"},
   "From the market we need:\n- Coriander\n- Green chillies\n- A kilo of onions\n- Paneer, if it's fresh",
   {"format": "bullets", "must_include": ["From the market we need:", "Coriander", "Green chillies", "A kilo of onions", "Paneer, if it's fresh"]},
   cx=1, note="facts: a kilo of onions; paneer only IF it's fresh; cleanup keeps wording")

# 122 nl_instruction: checklist + keep the deadline (onboarding/IT audit)
R2(NL, {"task": "rewrite",
        "instruction": "turn this into a short checklist and keep the deadline exactly",
        "transcript": "so before the audit on the twenty eighth we have to update the asset register get sign off from birgit on the access list and um archive last year's tickets"},
   "Before the audit on the 28th:\n- Update the asset register\n- Get sign-off from Birgit on the access list\n- Archive last year's tickets",
   {"format": "bullets", "numbers": ["28"], "must_include": ["Before the audit on the 28th:", "asset register", "sign-off from Birgit", "access list", "Archive last year's tickets"]},
   pos="after", cx=2, note="facts: deadline = before the audit on the 28th; three tasks; Birgit signs off the access list")

# 123 note, study notes with two negations and years
R2(NM, {"task": "rewrite", "format": "note", "header_style": "full",
        "transcript": "notes from the econ lecture um inflation is the general rise in prices not just one product the central bank targets around two percent and uh she said the exam will not cover the nineteen seventies case study only the two thousand eight one oh and the reading for next week is chapter four"},
   "Econ lecture notes.\nInflation is the general rise in prices, not just one product.\nThe central bank targets around 2%.\nShe said the exam will not cover the 1970s case study, only the 2008 one.\nReading for next week: chapter 4.",
   {"format": "note", "numbers": ["2%", "1970s", "2008", "4"], "min_negations": 2, "must_include": ["Econ lecture", "not just one product", "around 2%", "She said the exam will not cover the 1970s case study", "only the 2008 one", "chapter 4"]},
   cx=1, waivers=["number_missing", "number_invented"], note="facts: inflation = general rise, not just one product; target around 2%; exam will NOT cover the 1970s case, only 2008 (attributed to the lecturer); reading chapter 4; waiver: checker reads 'nineteen seventies' as 19 and 1 instead of 1970s")

# 124 auto, long reflective workout notes without a list cue -> prose
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "so the new plan is going okay i think um i'm doing three runs a week now one long one on sunday and two shorter ones midweek and my knee hasn't complained yet but taro said i should not up the distance by more than ten percent a week so i'm holding at fifteen k for the long run until the end of the month"},
   "The new plan is going okay, I think. I'm doing three runs a week now: one long one on Sunday and two shorter ones midweek. My knee hasn't complained yet, but Taro said I should not up the distance by more than 10% a week, so I'm holding at 15K for the long run until the end of the month.",
   {"format": "prose", "numbers": ["10%", "15"], "min_negations": 2, "must_include": ["I think", "three runs a week", "Sunday", "midweek", "knee hasn't complained yet", "Taro", "not up the distance by more than 10% a week", "15K", "until the end of the month"]},
   cx=1, note="facts: hedge 'I think'; three runs/week (one long Sunday, two shorter midweek); knee hasn't complained YET; Taro: NOT more than 10% a week; holding 15K until end of month; no list cue -> prose")

# 125 bullets + markdown + instruction bold the dates (itinerary, dates exact)
R2(NM, {"task": "rewrite", "format": "bullets", "markup": "markdown",
        "instruction": "bold each date",
        "transcript": "trip plan uh the fourteenth of june fly to oslo the fifteenth the fjord cruise the sixteenth free day and the seventeenth fly home"},
   "Trip plan:\n- **June 14:** fly to Oslo\n- **June 15:** the fjord cruise\n- **June 16:** free day\n- **June 17:** fly home",
   {"format": "bullets", "numbers": ["14", "15", "16", "17"], "must_include": ["Trip plan:", "**June 14:** fly to Oslo", "**June 15:** the fjord cruise", "**June 16:** free day", "**June 17:** fly home"]},
   pos="after", cx=2, note="facts: June 14 Oslo, 15 fjord cruise, 16 free day, 17 home (dates exact); bold only on dates as instructed")

# 126 numbered, alternative kept (recipe)
R2(SF, {"task": "rewrite", "format": "numbered",
        "transcript": "to make the dressing whisk three tablespoons of olive oil with one of vinegar or lemon juice add a teaspoon of mustard and season"},
   "To make the dressing:\n1. Whisk 3 tablespoons of olive oil with 1 of vinegar or lemon juice.\n2. Add a teaspoon of mustard.\n3. Season.",
   {"format": "numbered", "numbers": ["3", "1"], "must_include": ["3 tablespoons of olive oil", "vinegar or lemon juice", "teaspoon of mustard", "Season"]},
   cx=1, note="facts: 3 tbsp oil to 1 of vinegar OR lemon juice (alternative kept); a teaspoon of mustard")

# 127 plain + instruction asks for headings -> label lines, no '#' (workout split)
R2(NM, {"task": "rewrite", "header_style": "full",
        "instruction": "give each day its own heading",
        "transcript": "monday push day bench press and shoulder press wednesday pull day rows and pull ups friday legs squats and lunges"},
   "Monday: push day\nBench press and shoulder press\n\nWednesday: pull day\nRows and pull-ups\n\nFriday: legs\nSquats and lunges",
   {"must_include": ["Monday: push day", "Bench press and shoulder press", "Wednesday: pull day", "Rows and pull-ups", "Friday: legs", "Squats and lunges"], "must_not_include": ["#", "**"]},
   pos="after", cx=2, note="facts: Mon push (bench, shoulder press), Wed pull (rows, pull-ups), Fri legs (squats, lunges); Markup plain -> a label line per day, no '#' headings; two exercises each stay a phrase")

# 128 auto, message with 'three things' cue -> list inside the message
R2(SF, {"task": "rewrite", "format": "message", "context": "chat",
        "transcript": "tell hugo three things the van's booked for eight the keys are with the neighbour and nobody should park in the bay by the gate"},
   "Hugo, three things:\n- The van's booked for 8.\n- The keys are with the neighbour.\n- Nobody should park in the bay by the gate.",
   {"must_include": ["Hugo, three things:", "van's booked for 8", "keys are with the neighbour", "Nobody should park in the bay by the gate"], "min_negations": 1, "numbers": ["8"]},
   cx=1, note="facts: van booked for 8; keys with neighbour; nobody parks in the bay by the gate; 'tell hugo' licenses the vocative; list cue 'three things' -> bullets inside the message (format assertion omitted: checker forbids lists in messages)")

# 129 auto, first/second/third with a condition (laptop troubleshooting)
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "laptop running slow here's what to try first restart it second close the browser tabs you're not using and third if it's still slow after that run the disk cleanup tool"},
   "Laptop running slow? Here's what to try:\n1. Restart it.\n2. Close the browser tabs you're not using.\n3. If it's still slow after that, run the disk cleanup tool.",
   {"format": "numbered", "min_negations": 1, "must_include": ["Laptop running slow", "Restart it", "tabs you're not using", "If it's still slow after that, run the disk cleanup tool"]},
   cx=1, note="facts: three steps in order; disk cleanup only IF still slow after the first two")

# 130 note, en-in grocery budget with rupees and a negation
R2(NM, {"task": "rewrite", "format": "note", "locale": "en-in",
        "transcript": "note monthly groceries budget is eight thousand rupees um rice and atta from the wholesale shop vegetables from the sunday market and no more ordering snacks online"},
   "Monthly groceries budget: ₹8,000.\nRice and atta from the wholesale shop.\nVegetables from the Sunday market.\nNo more ordering snacks online.",
   {"format": "note", "numbers": ["8,000"], "min_negations": 1, "must_include": ["₹8,000", "Rice and atta", "wholesale shop", "Sunday market", "No more ordering snacks online"]},
   cx=1, note="facts: budget ₹8,000 (rupees spoken); rice/atta wholesale; veg Sunday market; NO more online snack orders")

# 131 auto, mixed output: lead sentence, list, closing sentence (recipe)
R2(SF, {"task": "rewrite", "format": "auto", "header_style": "full",
        "transcript": "this is the overnight oats thing i told you about you just need four things oats milk chia seeds and a spoon of honey mix it all in a jar the night before and it's ready in the morning"},
   "This is the overnight oats thing I told you about. You just need four things:\n- Oats\n- Milk\n- Chia seeds\n- A spoon of honey\n\nMix it all in a jar the night before, and it's ready in the morning.",
   {"must_include": ["overnight oats thing I told you about", "four things:", "- Oats", "- Milk", "- Chia seeds", "- A spoon of honey", "the night before", "ready in the morning"]},
   cx=1, note="facts: four ingredients (list cue 'four things'); mix the night before; mixed output: lead sentence, bullets, closing sentence")

# 132 bullets under markdown markup, nothing asks for emphasis -> plain bullets (exam)
R2(NM, {"task": "rewrite", "format": "bullets", "markup": "markdown",
        "transcript": "the things to bring to the exam are a black pen a calculator your student card and water in a clear bottle"},
   "Things to bring to the exam:\n- A black pen\n- A calculator\n- Your student card\n- Water in a clear bottle",
   {"format": "bullets", "no_markdown": True, "must_include": ["Things to bring to the exam:", "black pen", "calculator", "student card", "clear bottle"]},
   cx=1, note="markdown allowed but nothing asks for bold/headings -> plain '- ' bullets only")

# 133 auto, 'two options' + alternative -> one sentence (dinner)
R2(SF, {"task": "rewrite",
        "transcript": "for dinner two options either the lentil soup or uh the leftover pasta"},
   "For dinner, two options: either the lentil soup or the leftover pasta.",
   {"format": "prose", "must_include": ["two options", "either the lentil soup or the leftover pasta"], "must_not_include": ["- "]},
   cx=1, note="facts: alternative lentil soup OR leftover pasta, both kept; two items -> sentence")

# 134 nl_instruction: numbered list + warning kept as a separate closing line (troubleshooting)
R2(NL, {"task": "rewrite",
        "instruction": "make this a numbered list but keep the warning as its own line at the end",
        "transcript": "to replace the toner open the front cover pull the old cartridge out shake the new one gently and slide it in until it clicks and whatever you do don't touch the green drum"},
   "To replace the toner:\n1. Open the front cover.\n2. Pull the old cartridge out.\n3. Shake the new one gently.\n4. Slide it in until it clicks.\n\nWhatever you do, don't touch the green drum.",
   {"min_negations": 1, "must_include": ["To replace the toner:", "1. Open the front cover.", "Pull the old cartridge out", "Shake the new one gently", "until it clicks", "Whatever you do, don't touch the green drum."]},
   pos="after", cx=2, note="facts: four steps in order; warning 'don't touch the green drum' kept as a separate closing line as instructed")

# 135 auto, mixed: list + closing budget line, en-in rupees (shopping)
R2(SF, {"task": "rewrite", "format": "auto", "locale": "en-in",
        "transcript": "list for the kirana uh five kilos of rice two litres of oil one packet of tea and sugar if we're out and the total should be under twelve hundred rupees"},
   "List for the kirana:\n- 5 kilos of rice\n- 2 litres of oil\n- 1 packet of tea\n- Sugar, if we're out\n\nThe total should be under ₹1,200.",
   {"numbers": ["5", "2", "1", "1,200"], "must_include": ["List for the kirana:", "5 kilos of rice", "2 litres of oil", "1 packet of tea", "Sugar, if we're out", "under ₹1,200"]},
   cx=1, waivers=["number_invented"], note="facts: 5 kilos rice, 2 litres oil, 1 packet tea, sugar only IF we're out; total UNDER ₹1,200 (rupees spoken for the total only; item quantities are not money); waiver: checker does not read spoken 'one packet' as 1")

# 136 long prose under plain, items embedded, no list cue (onboarding feedback)
R2(NM, {"task": "rewrite",
        "transcript": "so the first week with devika went well she picked up the ticketing system really fast but she found the handover doc confusing so i think we should rewrite the access section and maybe record a short video um and she also asked if she can join the friday review which i said is fine from next month"},
   "The first week with Devika went well. She picked up the ticketing system really fast, but she found the handover doc confusing, so I think we should rewrite the access section and maybe record a short video. She also asked if she can join the Friday review, which I said is fine from next month.",
   {"format": "prose", "must_include": ["Devika", "ticketing system", "handover doc confusing", "I think we should rewrite the access section", "maybe record a short video", "Friday review", "fine from next month"]},
   cx=1, note="facts: hedge 'I think' + 'maybe' video kept; Friday review allowed FROM NEXT MONTH; no list cue -> prose, no Markdown")

# 137 note, itinerary with exact dates and a 'not the 6th'
R2(SF, {"task": "rewrite", "format": "note",
        "transcript": "note flight to bangkok on the second of december at eleven forty p m hotel check in on the third and the island ferry is on the fifth not the sixth"},
   "Flight to Bangkok: December 2, 11:40 p.m.\nHotel check-in: December 3.\nIsland ferry: December 5, not the 6th.",
   {"format": "note", "numbers": ["2", "11:40", "3", "5", "6"], "min_negations": 1, "must_include": ["Bangkok", "December 2, 11:40 p.m.", "December 3", "December 5, not the 6th"]},
   cx=1, note="facts: flight Dec 2 at 11:40 p.m.; check-in Dec 3; ferry Dec 5, NOT the 6th (speaker's own contrast, both kept as said)")

# 138 auto, 'the order is' -> numbered + closing repeat line (workout circuit)
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "the order for the circuit is um warm up then burpees then plank then jumping jacks then cool down and you repeat it three times"},
   "The order for the circuit:\n1. Warm-up\n2. Burpees\n3. Plank\n4. Jumping jacks\n5. Cool-down\n\nYou repeat it three times.",
   {"must_include": ["The order for the circuit:", "1. Warm-up", "2. Burpees", "3. Plank", "4. Jumping jacks", "5. Cool-down", "repeat it three times"]},
   cx=1, note="facts: five stages in spoken order; repeat three times kept as a closing sentence")

# 139 markdown + instruction: a heading on top, rest as bullets (packing, sales trip)
R2(NM, {"task": "rewrite", "markup": "markdown",
        "instruction": "add a heading that says packing list and keep the rest as bullets",
        "transcript": "for the sales trip laptop and charger business cards two shirts and the slides on a usb stick"},
   "## Packing list\n\nFor the sales trip:\n- Laptop and charger\n- Business cards\n- Two shirts\n- The slides on a USB stick",
   {"must_include": ["## Packing list", "For the sales trip:", "- Laptop and charger", "- Business cards", "- Two shirts", "- The slides on a USB stick"]},
   pos="after", cx=2, note="facts: four items for the sales trip (laptop+charger is one item); heading only because instructed; lead line kept under the heading")

# 140 cleanup, spoken 'new line' applied (workout schedule)
R2(SF, {"task": "cleanup",
        "transcript": "monday new line chest and triceps new line tuesday new line rest new line wednesday new line back and biceps"},
   "Monday\nChest and triceps\nTuesday\nRest\nWednesday\nBack and biceps",
   {"must_include": ["Monday\nChest and triceps", "Tuesday\nRest", "Wednesday\nBack and biceps"], "must_not_include": ["new line", "- "]},
   cx=0, note="spoken 'new line' applied as line breaks, not written out; cleanup adds no bullets")

# W11 stage 2, part 2: TC-W11-141..180 (exec'd by W11.py; uses R2, SF, NM, NL)

# 141 auto, 'day one/two/three/four' order cue, exact dates + condition (itinerary)
R2(SF, {"task": "rewrite", "format": "auto", "header_style": "full",
        "transcript": "here's the itinerary for kyoto day one which is the third of march we arrive around two and check in near the station day two the fourth temples in the east in the morning and the market in the afternoon day three the fifth a day trip to nara but only if the weather's okay otherwise the museum and day four the sixth we leave at ten for the airport"},
   "Here's the itinerary for Kyoto:\n1. Day one, March 3: we arrive around 2 and check in near the station.\n2. Day two, March 4: temples in the east in the morning and the market in the afternoon.\n3. Day three, March 5: a day trip to Nara, but only if the weather's okay; otherwise, the museum.\n4. Day four, March 6: we leave at 10 for the airport.",
   {"format": "numbered", "numbers": ["3", "4", "5", "6", "2", "10"], "must_include": ["Kyoto", "March 3", "around 2", "March 4", "temples in the east", "March 5", "Nara", "only if the weather's okay", "otherwise, the museum", "March 6", "leave at 10"]},
   cx=1, note="facts: Mar 3 arrive around 2; Mar 4 temples a.m., market p.m.; Mar 5 Nara ONLY IF weather okay, otherwise museum; Mar 6 leave at 10 for the airport; dates exact")

# 142 formal email with numbered steps and a closing condition (IT onboarding)
R2(NM, {"task": "rewrite", "format": "email", "register": "formal", "recipient": "Lise", "sender": "Omkar",
        "transcript": "hello lise regarding your access to the expense portal please follow these steps first log in with your staff id then go to settings and choose reset password and then enter the code we sent to your phone if the code doesn't arrive within five minutes please reply to this email"},
   "Dear Lise,\n\nRegarding your access to the expense portal, please follow these steps:\n1. Log in with your staff ID.\n2. Go to Settings and choose Reset password.\n3. Enter the code we sent to your phone.\n\nIf the code does not arrive within 5 minutes, please reply to this email.\n\nRegards,\nOmkar",
   {"format": "email", "numbers": ["5"], "min_negations": 1, "must_include": ["Dear Lise,", "expense portal", "1. Log in with your staff ID.", "Reset password", "code we sent to your phone", "If the code does not arrive within 5 minutes", "reply to this email", "Regards,\nOmkar"]},
   cx=2, note="facts: three steps in order; reply only IF code doesn't arrive within 5 minutes; formal -> 'Dear Lise,' and 'Regards,' + sender")

# 143 auto, 'two things' -> one sentence with a negation (workout)
R2(SF, {"task": "rewrite",
        "transcript": "two things to remember for tomorrow's session bring the resistance band and uh don't eat right before"},
   "Two things to remember for tomorrow's session: bring the resistance band, and don't eat right before.",
   {"format": "prose", "min_negations": 1, "must_include": ["tomorrow's session", "resistance band", "don't eat right before"], "must_not_include": ["- "]},
   cx=1, note="facts: two items only -> sentence; 'don't eat right before' negation kept")

# 144 explicit prose turns a dictated list into a sentence (packing)
R2(SF, {"task": "rewrite", "format": "prose",
        "transcript": "the packing list is um sunscreen hats a beach towel each and the snorkel set"},
   "The packing list is sunscreen, hats, a beach towel each and the snorkel set.",
   {"format": "prose", "must_include": ["packing list", "sunscreen", "hats", "a beach towel each", "snorkel set"], "must_not_include": ["- "]},
   cx=1, note="facts: four items incl. 'a beach towel each'; explicit Format prose beats the list cue -> one sentence")

# 145 markdown + instruction: checklist with tick boxes (onboarding)
R2(NM, {"task": "rewrite", "markup": "markdown",
        "instruction": "make it a checklist with tick boxes",
        "transcript": "first day checklist for neel collect the laptop sign the nda join the team channel and book the safety induction"},
   "First day checklist for Neel:\n- [ ] Collect the laptop\n- [ ] Sign the NDA\n- [ ] Join the team channel\n- [ ] Book the safety induction",
   {"format": "bullets", "must_include": ["First day checklist for Neel:", "- [ ] Collect the laptop", "- [ ] Sign the NDA", "- [ ] Join the team channel", "- [ ] Book the safety induction"]},
   pos="after", cx=2, note="tick boxes '- [ ]' only because markup markdown and the instruction asks for them; four tasks kept; lead line kept")

# 146 cleanup, speaker dictated 'bullet point / next bullet' (recipe)
R2(SF, {"task": "cleanup",
        "transcript": "bullet point preheat to one eighty next bullet grease the tin next bullet line it with paper"},
   "- Preheat to 180.\n- Grease the tin.\n- Line it with paper.",
   {"format": "bullets", "numbers": ["180"], "must_include": ["Preheat to 180", "Grease the tin", "Line it with paper"], "must_not_include": ["bullet"]},
   cx=0, note="facts: 180 (no unit spoken, none added); cleanup applies the dictated bullet commands as '- ' lines")

# 147 auto, mixed: lead line, numbered steps, closing condition (app troubleshooting)
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "if the app keeps crashing try this first update it from the store then clear the cache in settings and then log out and back in and if none of that works send me a screenshot of the error"},
   "If the app keeps crashing, try this:\n1. Update it from the store.\n2. Clear the cache in Settings.\n3. Log out and back in.\n\nIf none of that works, send me a screenshot of the error.",
   {"must_include": ["If the app keeps crashing, try this:", "1. Update it from the store.", "2. Clear the cache", "3. Log out and back in.", "If none of that works, send me a screenshot of the error."]},
   cx=1, note="facts: three steps in order; screenshot only IF none of that works (kept as its own closing line, outside the numbered steps)")

# 148 note, en-gb study note with a year and a negation
R2(NM, {"task": "rewrite", "format": "note", "locale": "en-gb",
        "transcript": "revision note the treaty was signed in nineteen nineteen um key terms were reparations and the war guilt clause and remember the us never ratified it"},
   "The treaty was signed in 1919.\nKey terms: reparations and the war guilt clause.\nRemember: the US never ratified it.",
   {"format": "note", "numbers": ["1919"], "min_negations": 1, "must_include": ["1919", "reparations", "war guilt clause", "the US never ratified it"]},
   cx=1, note="facts: signed 1919; key terms reparations + war guilt clause; US NEVER ratified it")

# 149 auto, items but no list cue -> prose (recipe tip)
R2(SF, {"task": "rewrite", "format": "auto", "locale": "en-in",
        "transcript": "my gran's trick for the dal is she never adds the salt until the lentils are soft and she always finishes it with a spoon of ghee and a pinch of hing"},
   "My gran's trick for the dal is that she never adds the salt until the lentils are soft, and she always finishes it with a spoon of ghee and a pinch of hing.",
   {"format": "prose", "min_negations": 1, "must_include": ["gran's trick", "never adds the salt until the lentils are soft", "always finishes it", "spoon of ghee", "pinch of hing"], "must_not_include": ["- "]},
   cx=1, note="facts: salt NEVER before lentils are soft; always ghee + hing at the end; no list cue -> prose")

# 150 nl_instruction: bullets + budget moved to the top (travel, en-in)
R2(NL, {"task": "rewrite", "locale": "en-in",
        "instruction": "bullets please, and put the budget at the top",
        "transcript": "for the goa trip we're booking the flights the guesthouse near the beach and a scooter for three days and the budget is forty thousand rupees for everything"},
   "Budget: ₹40,000 for everything.\n\nFor the Goa trip, we're booking:\n- The flights\n- The guesthouse near the beach\n- A scooter for three days",
   {"numbers": ["40,000"], "must_include": ["Budget: ₹40,000 for everything.", "For the Goa trip, we're booking:", "- The flights", "- The guesthouse near the beach", "- A scooter for three days"]},
   pos="after", cx=2, note="facts: ₹40,000 for everything (moved to the top as instructed); flights, guesthouse near the beach, scooter for three days")

# 151 auto, list cue 'here are the ... moves' -> bullets (workout)
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "here are the warm up moves arm circles leg swings hip openers and thirty seconds of skipping"},
   "Here are the warm-up moves:\n- Arm circles\n- Leg swings\n- Hip openers\n- 30 seconds of skipping",
   {"format": "bullets", "numbers": ["30"], "must_include": ["warm-up moves:", "Arm circles", "Leg swings", "Hip openers", "30 seconds of skipping"]},
   cx=1, note="facts: four moves, skipping for 30 seconds; list cue 'here are' -> bullets")

# 152 plain numbered; spoken emphasis stays words, never bold (fire drill steps)
R2(NM, {"task": "rewrite", "format": "numbered", "header_style": "full",
        "transcript": "steps for the fire drill um leave by the nearest exit do not use the lift and this is really important wait at the car park until rhea does the head count"},
   "Steps for the fire drill:\n1. Leave by the nearest exit.\n2. Do not use the lift.\n3. This is really important: wait at the car park until Rhea does the head count.",
   {"format": "numbered", "min_negations": 1, "must_include": ["Steps for the fire drill:", "nearest exit", "Do not use the lift", "really important", "until Rhea does the head count"], "must_not_include": ["**"]},
   cx=1, note="facts: do NOT use the lift; wait at the car park UNTIL Rhea does the head count; emphasis kept as the speaker's words, no bold under plain")

# 153 message, 2 items -> sentence (shopping, en-in)
R2(SF, {"task": "rewrite", "format": "message", "locale": "en-in",
        "transcript": "kiran pick up curd and bread on your way back"},
   "Kiran, pick up curd and bread on your way back.",
   {"format": "message", "must_include": ["Kiran", "curd and bread", "on your way back"]},
   cx=1, note="two items -> sentence; vocative from the spoken name; no greeting added")

# 154 formal numbered (onboarding policy)
R2(SF, {"task": "rewrite", "format": "numbered", "register": "formal",
        "transcript": "so for new hires um they should do the online training in the first week then meet their buddy and then hand the tax form to hr by the fifteenth"},
   "New hires should:\n1. Complete the online training in the first week.\n2. Meet their buddy.\n3. Submit the tax form to HR by the 15th.",
   {"format": "numbered", "numbers": ["15"], "must_include": ["New hires should:", "online training in the first week", "Meet their buddy", "tax form to HR by the 15th"]},
   cx=2, note="facts: training in the first week; tax form to HR by the 15th; formal register lifts wording only ('do' -> 'complete', 'hand' -> 'submit')")

# 155 note under markdown markup, nothing asks -> plain note (study)
R2(NM, {"task": "rewrite", "format": "note", "markup": "markdown",
        "transcript": "study note the mitochondria thing is on page forty two and the quiz is wednesday not tuesday"},
   "The mitochondria part is on page 42.\nQuiz is Wednesday, not Tuesday.",
   {"format": "note", "numbers": ["42"], "min_negations": 1, "no_markdown": True, "must_include": ["mitochondria", "page 42", "Wednesday, not Tuesday"], "must_not_include": ["Quiz is Tuesday"]},
   cx=1, note="facts: page 42; quiz is Wednesday, NOT Tuesday; markdown allowed but nothing asks -> no Markdown")

# 156 auto, long house-sitting notes: lead, list (cue comes after the items), closing (en-gb)
R2(SF, {"task": "rewrite", "format": "auto", "locale": "en-gb", "header_style": "full",
        "transcript": "for when birgit's house sitting while we're away um the plants need water every two days the cat gets fed twice a day morning and evening and the bins go out on tuesday night so that's the three main things and also the wifi password is on the fridge and the spare key is with the neighbour at number twelve if she gets locked out"},
   "For when Birgit's house-sitting while we're away, the three main things:\n- The plants need water every two days.\n- The cat gets fed twice a day, morning and evening.\n- The bins go out on Tuesday night.\n\nAlso, the Wi-Fi password is on the fridge, and the spare key is with the neighbour at number 12 if she gets locked out.",
   {"numbers": ["12"], "must_include": ["Birgit", "while we're away", "three main things", "water every two days", "twice a day, morning and evening", "Tuesday night", "Wi-Fi password is on the fridge", "neighbour at number 12", "if she gets locked out"]},
   cx=1, note="facts: plants every two days; cat twice a day (morning+evening); bins Tuesday night; Wi-Fi password on fridge; spare key with neighbour at number 12 for IF she gets locked out; mixed output: lead, three bullets, closing sentence")

# 157 explicit bullets with only 2 items (study)
R2(SF, {"task": "rewrite", "format": "bullets",
        "transcript": "the quiz covers chapters three and four"},
   "The quiz covers:\n- Chapter 3\n- Chapter 4",
   {"format": "bullets", "numbers": ["3", "4"], "must_include": ["The quiz covers:", "- Chapter 3", "- Chapter 4"]},
   cx=1, note="facts: chapters 3 and 4; explicit Format bullets beats the two-items-stay-a-sentence default")

# 158 markdown + instruction: bold the warnings only (recipe)
R2(NM, {"task": "rewrite", "markup": "markdown",
        "instruction": "bold the warnings",
        "transcript": "for the chilli oil heat the oil to about one twenty careful it spits then pour it over the flakes and never leave the pan alone"},
   "For the chilli oil, heat the oil to about 120. **Careful, it spits.** Then pour it over the flakes, and **never leave the pan alone**.",
   {"numbers": ["120"], "min_negations": 1, "must_include": ["about 120", "**Careful, it spits.**", "pour it over the flakes", "**never leave the pan alone**"]},
   pos="after", cx=1, note="facts: about 120 (no unit spoken); warnings 'careful it spits' and 'never leave the pan alone' bolded, nothing else")

# 159 auto, 'number one / number two' with 2 items -> numbered (house rules)
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "house rule number one shoes off at the door number two no phones at dinner"},
   "House rules:\n1. Shoes off at the door.\n2. No phones at dinner.",
   {"format": "numbered", "min_negations": 1, "must_include": ["House rules:", "1. Shoes off at the door.", "2. No phones at dinner."]},
   cx=1, note="explicit order cue 'number one / number two' -> numbered even with two items; 'no phones' kept")

# 160 note with a self-corrected date (travel visa)
R2(NM, {"task": "rewrite", "format": "note",
        "transcript": "note the visa appointment is on the eighth no wait the ninth at ten am bring two photos and the bank statement"},
   "Visa appointment: the 9th at 10 a.m.\nBring two photos and the bank statement.",
   {"format": "note", "numbers": ["9", "10"], "must_include": ["Visa appointment", "the 9th at 10 a.m.", "two photos", "bank statement"], "must_not_include": ["the 8th", "eighth"]},
   cx=1, note="facts: self-correction 8th -> the 9th at 10 a.m.; bring two photos and the bank statement")

# 161 auto, 'the steps to ... are' -> numbered (repotting)
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "the steps to repot it are take the plant out gently shake off the old soil trim any black roots and then pop it in the new pot with fresh compost"},
   "The steps to repot it:\n1. Take the plant out gently.\n2. Shake off the old soil.\n3. Trim any black roots.\n4. Pop it in the new pot with fresh compost.",
   {"format": "numbered", "must_include": ["The steps to repot it:", "Take the plant out gently", "Shake off the old soil", "Trim any black roots", "new pot with fresh compost"]},
   cx=1, note="order cue 'the steps' -> numbered; four steps in spoken order")

# 162 auto, long seminar notes, no list cue -> prose with a paragraph break at the topic change
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "so in today's seminar we mostly argued about whether the sample was biased um alma thinks it was because they only recruited online and i kind of agree but neel pointed out they weighted the results by age anyway oh and separately the essay deadline moved to the twentieth and it's now two thousand words not fifteen hundred"},
   "In today's seminar, we mostly argued about whether the sample was biased. Alma thinks it was because they only recruited online, and I kind of agree, but Neel pointed out they weighted the results by age anyway.\n\nSeparately, the essay deadline moved to the 20th, and it's now 2,000 words, not 1,500.",
   {"format": "prose", "numbers": ["20", "2,000", "1,500"], "min_negations": 1, "must_include": ["today's seminar", "Alma thinks", "only recruited online", "I kind of agree", "Neel pointed out", "weighted the results by age", "deadline moved to the 20th", "2,000 words, not 1,500"]},
   cx=1, note="facts: Alma's view (recruited only online); speaker 'kind of' agrees (hedge); Neel: weighted by age; deadline moved to the 20th; 2,000 words NOT 1,500; topic change -> new paragraph; no list cue -> prose")

# 163 casual email with a dictated list and sender (hike)
R2(NM, {"task": "rewrite", "format": "email", "register": "casual", "recipient": "Kiran", "sender": "Rhea",
        "transcript": "hey kiran so for saturday's hike could you bring these the first aid kit the map and some snacks for the group we're meeting at the car park at seven"},
   "Hey Kiran,\n\nFor Saturday's hike, could you bring these:\n- The first aid kit\n- The map\n- Some snacks for the group\n\nWe're meeting at the car park at 7.\n\nThanks,\nRhea",
   {"format": "email", "numbers": ["7"], "must_include": ["Hey Kiran,", "Saturday's hike", "- The first aid kit", "- The map", "- Some snacks for the group", "car park at 7", "Thanks,\nRhea"]},
   cx=2, note="facts: three items to bring (cue 'bring these'); meet at the car park at 7; casual register keeps the dictated 'hey'; sign-off from [Sender]")

# 164 auto, 'the options are' -> bullets of alternatives (team lunch)
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "for the team lunch the options are the thai place the pizza place or the salad bar near the station"},
   "For the team lunch, the options are:\n- The Thai place\n- The pizza place\n- The salad bar near the station",
   {"format": "bullets", "must_include": ["the options are:", "The Thai place", "The pizza place", "The salad bar near the station"]},
   cx=1, note="facts: three alternatives (one of them), introduced by 'the options are' so they read as choices; none dropped")

# 165 numbered under markdown markup, nothing asks for emphasis -> plain numbering
R2(NM, {"task": "rewrite", "format": "numbered", "markup": "markdown",
        "transcript": "how to book a meeting room open the calendar click new event add the room as a guest and check it shows accepted"},
   "How to book a meeting room:\n1. Open the calendar.\n2. Click New event.\n3. Add the room as a guest.\n4. Check it shows Accepted.",
   {"format": "numbered", "no_markdown": True, "must_include": ["How to book a meeting room:", "Open the calendar", "New event", "Add the room as a guest", "Accepted"]},
   cx=1, note="markdown allowed but nothing asks for headings or bold -> plain numbered list")

# 166 auto, short, two facts -> one sentence (school trip timing)
R2(SF, {"task": "rewrite",
        "transcript": "lunch is at one and the bus leaves at two thirty sharp"},
   "Lunch is at 1, and the bus leaves at 2:30 sharp.",
   {"format": "prose", "numbers": ["1", "2:30"], "must_include": ["Lunch is at 1", "2:30 sharp"], "must_not_include": ["- "]},
   cx=0, note="facts: lunch at 1; bus at 2:30 sharp")

# 167 nl_instruction: numbered plan, keep both dates (deep clean)
R2(NL, {"task": "rewrite",
        "instruction": "turn this into a numbered plan and keep both dates",
        "transcript": "we either do the deep clean on the fourth or the eleventh um first clear the cupboards then wash the shelves then put everything back and label the jars"},
   "We either do the deep clean on the 4th or the 11th:\n1. Clear the cupboards.\n2. Wash the shelves.\n3. Put everything back and label the jars.",
   {"format": "numbered", "numbers": ["4", "11"], "must_include": ["either do the deep clean on the 4th or the 11th", "Clear the cupboards", "Wash the shelves", "label the jars"]},
   pos="after", cx=2, note="facts: alternative dates 4th OR 11th both kept; three steps in order")

# 168 auto, first/then/after that/finally -> numbered (poha, en-in)
R2(SF, {"task": "rewrite", "format": "auto", "locale": "en-in",
        "transcript": "for the poha first rinse the poha and let it drain then fry mustard seeds curry leaves and onion after that add turmeric and the poha and finally squeeze lime and add coriander"},
   "For the poha:\n1. Rinse the poha and let it drain.\n2. Fry mustard seeds, curry leaves and onion.\n3. Add turmeric and the poha.\n4. Squeeze lime and add coriander.",
   {"format": "numbered", "must_include": ["For the poha:", "let it drain", "mustard seeds, curry leaves and onion", "turmeric", "Squeeze lime and add coriander"]},
   cx=1, note="order cues first/then/after that/finally -> four numbered steps in spoken order")

# 169 note, IT troubleshooting log with a negation
R2(NM, {"task": "rewrite", "format": "note", "header_style": "full",
        "transcript": "note tuesday the vpn dropped three times between two and four pm restarting the client fixed it each time but it's not a permanent fix so log a ticket"},
   "Tuesday: VPN dropped three times between 2 and 4 p.m.\nRestarting the client fixed it each time.\nNot a permanent fix: log a ticket.",
   {"format": "note", "numbers": ["2", "4"], "min_negations": 1, "must_include": ["Tuesday", "VPN dropped three times", "between 2 and 4 p.m.", "Restarting the client fixed it each time", "Not a permanent fix", "log a ticket"]},
   cx=1, note="facts: Tuesday, three drops between 2 and 4 p.m.; restart fixed it each time; NOT a permanent fix -> log a ticket")

# 170 auto, 'a few things' -> bullets with a size (gym shopping)
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "need to buy a few things for the gym a water bottle a lock for the locker and new trainers size nine"},
   "Need to buy a few things for the gym:\n- A water bottle\n- A lock for the locker\n- New trainers, size 9",
   {"format": "bullets", "numbers": ["9"], "must_include": ["a few things for the gym:", "A water bottle", "A lock for the locker", "New trainers, size 9"]},
   cx=1, note="facts: trainers size 9; three items with list cue -> bullets")

# 171 neutral email: lead, list, conditional closing, sender (moving day)
R2(SF, {"task": "rewrite", "format": "email", "recipient": "Hugo", "sender": "Alma", "header_style": "full",
        "transcript": "hi hugo just a heads up for the move on friday um the movers arrive at eight so please have the following ready the boxes in the hallway the fridge defrosted and the desk taken apart oh and if the lift is out of order call me straight away because they won't carry the sofa down six floors"},
   "Hi Hugo,\n\nJust a heads-up for the move on Friday: the movers arrive at 8, so please have the following ready:\n- The boxes in the hallway\n- The fridge defrosted\n- The desk taken apart\n\nIf the lift is out of order, call me straight away, because they won't carry the sofa down six floors.\n\nBest,\nAlma",
   {"format": "email", "numbers": ["8"], "min_negations": 1, "must_include": ["Hi Hugo,", "Friday", "movers arrive at 8", "- The boxes in the hallway", "- The fridge defrosted", "- The desk taken apart", "If the lift is out of order, call me straight away", "won't carry the sofa down six floors", "Best,\nAlma"]},
   cx=1, note="facts: move Friday, movers at 8; three things ready (cue 'the following'); call IF the lift is out of order; movers WON'T carry the sofa down six floors")

# 172 markdown + instruction: headings per section (study notes)
R2(NM, {"task": "rewrite", "markup": "markdown",
        "instruction": "use headings for each section",
        "transcript": "biology notes um section one cells they're the basic unit of life section two genetics dna carries the instructions and genes are segments of it"},
   "# Biology notes\n\n## Section 1: Cells\n\nThey're the basic unit of life.\n\n## Section 2: Genetics\n\nDNA carries the instructions, and genes are segments of it.",
   {"numbers": ["1", "2"], "must_include": ["# Biology notes", "## Section 1: Cells", "basic unit of life", "## Section 2: Genetics", "DNA carries the instructions", "genes are segments of it"]},
   pos="after", cx=1, note="headings only because markup markdown and the instruction asks; spoken lead 'biology notes' kept as the title; two sections with their content unchanged")

# 173 cleanup + numbered, self-correction on minutes (pasta)
R2(SF, {"task": "cleanup", "format": "numbered",
        "transcript": "first boil the water then add the pasta for nine no ten minutes then drain it but keep a cup of the water"},
   "1. First, boil the water.\n2. Then add the pasta for 10 minutes.\n3. Then drain it, but keep a cup of the water.",
   {"format": "numbered", "numbers": ["10"], "must_include": ["boil the water", "pasta for 10 minutes", "drain it, but keep a cup of the water"], "must_not_include": ["9 minutes", "nine"]},
   cx=1, note="facts: self-correction nine -> 10 minutes; keep a cup of the water; cleanup keeps 'first/then'")

# 174 message, weak order cue + condition -> stays prose (IT access)
R2(SF, {"task": "rewrite", "format": "message", "context": "work",
        "transcript": "devika to get into the shared drive open the portal and sign in with your email then click request access and if it says pending just wait for omkar to approve it"},
   "Devika, to get into the shared drive, open the portal and sign in with your email, then click Request access. If it says pending, just wait for Omkar to approve it.",
   {"format": "message", "must_include": ["Devika", "shared drive", "sign in with your email", "Request access", "If it says pending, just wait for Omkar to approve it"]},
   cx=1, note="facts: if pending -> wait for Omkar to approve (condition kept); a single 'then' is not a strong enough order cue in a short message -> prose")

# 175 bullets, en-in budget heads in rupees, hedge on travel
R2(NM, {"task": "rewrite", "format": "bullets", "locale": "en-in",
        "transcript": "budget heads for the offsite um venue one lakh twenty thousand rupees food sixty thousand and travel around forty thousand"},
   "Budget heads for the offsite:\n- Venue: ₹1,20,000\n- Food: ₹60,000\n- Travel: around ₹40,000",
   {"format": "bullets", "numbers": ["1,20,000", "60,000", "40,000"], "must_include": ["Budget heads for the offsite:", "Venue: ₹1,20,000", "Food: ₹60,000", "Travel: around ₹40,000"]},
   cx=1, note="facts: venue ₹1,20,000; food ₹60,000; travel AROUND ₹40,000 (hedge kept); rupees spoken in the list -> ₹ on every amount in it")

# 176 auto, 2 items, question -> sentence (road trip, en-gb)
R2(SF, {"task": "rewrite", "locale": "en-gb",
        "transcript": "can you check the oil and uh the tyre pressure before the road trip"},
   "Can you check the oil and the tyre pressure before the road trip?",
   {"format": "prose", "must_include": ["oil", "tyre pressure", "before the road trip"], "must_not_include": ["- "]},
   cx=0, note="two items -> one question sentence ending in '?'")

# 177 numbered, workout progression with distances and a date
R2(SF, {"task": "rewrite", "format": "numbered",
        "transcript": "week one three k runs week two five k week three seven k and week four the ten k race on the twenty sixth"},
   "1. Week one: 3K runs.\n2. Week two: 5K.\n3. Week three: 7K.\n4. Week four: the 10K race on the 26th.",
   {"format": "numbered", "numbers": ["26"], "must_include": ["Week one: 3K runs", "Week two: 5K", "Week three: 7K", "Week four: the 10K race on the 26th"]},
   cx=1, note="facts: 3K, 5K, 7K by week; 10K race on the 26th in week four")

# 178 note, recipe card with quantities, oven temp, negation
R2(NM, {"task": "rewrite", "format": "note",
        "transcript": "recipe note for alma's banana bread three ripe bananas two hundred grams of flour a hundred grams of sugar one egg and a teaspoon of baking soda in the oven at one seventy for fifty minutes and don't open the oven for the first half hour"},
   "Alma's banana bread.\n3 ripe bananas, 200 g flour, 100 g sugar, 1 egg, a teaspoon of baking soda.\nOven at 170 for 50 minutes.\nDon't open the oven for the first half hour.",
   {"format": "note", "numbers": ["3", "200", "100", "1", "170", "50"], "min_negations": 1, "must_include": ["Alma's banana bread", "3 ripe bananas", "200 g flour", "100 g sugar", "1 egg", "teaspoon of baking soda", "170 for 50 minutes", "Don't open the oven for the first half hour"]},
   cx=1, note="facts: 3 bananas, 200 g flour, 100 g sugar, 1 egg, a teaspoon of baking soda; 170 (no unit spoken) for 50 minutes; DON'T open the oven for the first half hour")

# 179 markdown + instruction: list with names in bold (cleaning rota)
R2(NM, {"task": "rewrite", "markup": "markdown",
        "instruction": "make it a list with the names in bold",
        "transcript": "rota for the clean up kiran does the kitchen birgit the lounge and taro the bathrooms"},
   "Rota for the clean-up:\n- **Kiran:** the kitchen\n- **Birgit:** the lounge\n- **Taro:** the bathrooms",
   {"format": "bullets", "must_include": ["Rota for the clean-up:", "**Kiran:** the kitchen", "**Birgit:** the lounge", "**Taro:** the bathrooms"]},
   pos="after", cx=2, note="facts: Kiran kitchen, Birgit lounge, Taro bathrooms; bold only on names as instructed; lead line kept")

# 180 auto, long travel update with a condition, no list cue -> two paragraphs
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "so the ferry to the island got cancelled because of the wind and we ended up staying an extra night in the port town which was actually lovely um the guesthouse owner cooked for us and tomorrow we're trying again at nine but if it's cancelled again we'll take the longer route by bus and lose a day"},
   "The ferry to the island got cancelled because of the wind, and we ended up staying an extra night in the port town, which was actually lovely. The guesthouse owner cooked for us.\n\nTomorrow we're trying again at 9, but if it's cancelled again, we'll take the longer route by bus and lose a day.",
   {"format": "prose", "numbers": ["9"], "must_include": ["cancelled because of the wind", "extra night in the port town", "actually lovely", "guesthouse owner cooked for us", "trying again at 9", "if it's cancelled again, we'll take the longer route by bus", "lose a day"]},
   cx=1, note="facts: ferry cancelled (wind); extra night in port town; tomorrow retry at 9; IF cancelled again -> bus, lose a day (condition kept); no list cue -> prose")

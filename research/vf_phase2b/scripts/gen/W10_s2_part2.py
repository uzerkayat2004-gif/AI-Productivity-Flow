# W10 stage 2, chunk 2: TC-W10-141..185 (exec'd by W10_s2.py)

# ---------------------------------------------------------------- messages (28)
# 141 condolence, pet
R("messages", {**P, "tone": "empathetic",
               "transcript": "simran i just heard about coco i'm really sorry she was such a sweet dog and you gave her the best life"},
  "Simran, I just heard about Coco. I'm really sorry. She was such a sweet dog, and you gave her the best life.",
  {"must_include": ["Simran", "Coco", "really sorry", "sweet dog", "best life"]},
  note="facts: condolence for Simran's dog Coco; only the dictated words (sweet dog, best life); no cause, date or offer added",
  length="medium")
# 142 congratulations, warm, no "!"
R("messages", {**P, "tone": "warm",
               "transcript": "ishita and karim congratulations on the engagement so happy for you both cannot wait to celebrate"},
  "Ishita and Karim, congratulations on the engagement. So happy for you both, and I cannot wait to celebrate.",
  {"must_include": ["Ishita and Karim", "congratulations", "engagement", "happy for you both", "celebrate"], "must_not_include": ["!"], "min_negations": 1},
  note="facts: congratulations to Ishita and Karim on the engagement; no date or event detail added; warm tone without exclamation marks (none dictated)",
  length="short")
# 143 dictated apology, "sincere", keep dictated reason only
R("messages", {**P,
               "instruction": "make the apology sound sincere but don't add any excuse I didn't give",
               "transcript": "callum sorry i missed your call last night my phone was on silent i'll call you after seven today"},
  "Callum, I'm really sorry I missed your call last night. My phone was on silent. I'll call you after 7 today.",
  {"numbers": ["7"], "must_include": ["Callum", "really sorry", "missed your call", "last night", "on silent", "after 7 today"]},
  note="facts: missed Callum's call last night; dictated reason only (phone on silent); speaker's own commitment: call after 7 today (dictated); 'really' is the visible sincerity change",
  pos="after", cx=2, length="short")
# 144 invitation, cricket screening, long
R("messages", {**CH, "locale": "en-in",
               "transcript": "match screening at my place on wednesday the india game starts at two thirty pm so come by two get your own snacks i've got the drinks covered uh my parents are out so we can be loud but the neighbours complain after ten so if it goes to a super over we'll keep it down and parking is tight so come by metro or share autos"},
  "Match screening at my place on Wednesday. The India game starts at 2:30 p.m., so come by 2. Get your own snacks; I've got the drinks covered. My parents are out, so we can be loud, but the neighbours complain after 10, so if it goes to a super over, we'll keep it down. Parking is tight, so come by metro or share autos.",
  {"numbers": ["2:30", "2", "10"], "must_include": ["Match screening", "my place", "Wednesday", "India game", "own snacks", "drinks covered", "parents are out", "neighbours complain after 10", "if it goes to a super over", "keep it down", "Parking is tight", "metro or share autos"]},
  note="facts: screening at speaker's place Wednesday; game 2:30 p.m.; come by 2; guests bring own snacks, speaker covers drinks; parents out; neighbours complain after 10, so IF super over, keep it down; parking tight: metro OR shared autos (both kept)")
# 145 polite decline, reunion
R("messages", {**CH, "tone": "friendly",
               "transcript": "hey guys i won't be able to make it to the reunion this time i've got my cousin's engagement in indore that weekend please send lots of photos"},
  "Hey guys, I won't be able to make it to the reunion this time. I've got my cousin's engagement in Indore that weekend. Please send lots of photos.",
  {"must_include": ["Hey guys", "reunion", "this time", "cousin's engagement", "Indore", "photos"], "min_negations": 1, "must_not_include": ["!"]},
  note="facts: can't make the reunion this time; reason cousin's engagement in Indore that weekend; greeting dictated; friendly tone, no exclamation marks added",
  length="medium")
# 146 reminder to family, safety
R("messages", {**CH, "locale": "en-in", **F,
               "transcript": "nani the electrician is coming tomorrow between ten and twelve please don't let him in without checking his id card he'll show the company id"},
  "Nani, the electrician is coming tomorrow between 10 and 12. Please don't let him in without checking his ID card. He'll show the company ID.",
  {"numbers": ["10", "12"], "must_include": ["Nani", "electrician", "tomorrow", "ID card", "company ID"], "min_negations": 1},
  note="facts: electrician tomorrow between 10 and 12; don't let him in WITHOUT checking ID (negated condition kept); he'll show the company ID",
  length="medium")
# 147 chess club group update, instruction
R("messages", {**CH,
               "instruction": "turn this into a clear update for the club group, no bullets, keep all the numbers",
               "transcript": "um so the rapid league results are out we finished third out of nine teams which is our best ever uh dev won all five of his games and karim drew two and won three the next league starts on the sixth of january and we need to register by the twentieth of december the fee is fifteen hundred per team so if you want to play this time tell me before the fifteenth"},
  "The rapid league results are out: we finished third out of nine teams, which is our best ever. Dev won all five of his games, and Karim drew two and won three.\n\nThe next league starts on January 6, and we need to register by December 20. The fee is 1,500 per team, so if you want to play this time, tell me before the 15th.",
  {"numbers": ["6", "20", "1,500", "15"], "numbers_one_of": [["nine", "9"], ["five", "5"], ["two", "2"], ["three", "3"]], "must_include": ["rapid league", "third", "best ever", "Dev", "Karim", "January 6", "December 20", "per team", "if you want to play", "before the 15th"], "must_not_include": ["₹", "- "]},
  note="facts: third of nine teams, best ever; Dev won all five; Karim drew two, won three; next league starts January 6; register by December 20; fee 1,500 per team (no currency spoken); condition: if you want to play, tell speaker before the 15th; prose, no bullets per instruction",
  pos="before", cx=3, length="long")
# 148 neighbour notice
R("messages", {**CH, "locale": "en-in",
               "transcript": "hi all a small request from flat c two the delivery boxes are piling up near the lift on our floor if they're yours please take them in by tonight otherwise the cleaners will clear them tomorrow morning"},
  "Hi all, a small request from flat C2: the delivery boxes are piling up near the lift on our floor. If they're yours, please take them in by tonight; otherwise the cleaners will clear them tomorrow morning.",
  {"must_include": ["Hi all", "flat C2", "delivery boxes", "lift", "If they're yours", "by tonight", "otherwise", "cleaners", "tomorrow morning"]},
  note="facts: flat C2; boxes near the lift on their floor; condition: if yours, take them in by tonight, otherwise cleaners clear them tomorrow morning; greeting dictated",
  length="medium")
# 149 Hinglish, gardening
R("messages", {**CH, "locale": "en-in", "register": "casual",
               "transcript": "bhaiya kal subah gamle mein paani daal dena only the ones on the balcony not the terrace ones those got rain"},
  "Bhaiya, kal subah gamle mein paani daal dena. Only the ones on the balcony, not the terrace ones; those got rain.",
  {"must_include": ["Bhaiya", "kal subah gamle mein paani daal dena", "balcony", "terrace ones", "got rain"], "min_negations": 1},
  note="facts: Hinglish kept as dictated (water the pots tomorrow morning); only the balcony ones, NOT the terrace ones, which got rain",
  length="short")
# 150 freelance client, friendlier
R("messages", {**CH,
               "instruction": "friendlier please",
               "transcript": "nora received the payment thanks the second draft of the brochure will be with you by friday evening"},
  "Nora, got the payment, thank you so much. The second draft of the brochure will be with you by Friday evening.",
  {"must_include": ["Nora", "payment", "thank you so much", "second draft", "brochure", "Friday evening"]},
  note="facts: payment received; second brochure draft by Friday evening (dictated commitment, unchanged); friendlier wording 'got' / 'thank you so much', nothing added",
  pos="after", cx=1, length="short")
# 151 hiking, third person, lowercase common nouns
R("messages", {**CH, **F,
               "transcript": "the trail's closed this weekend because of the landslide so we'll do it next month instead zoe's checking if the forest office gives a reopening date"},
  "The trail's closed this weekend because of the landslide, so we'll do it next month instead. Zoe's checking if the forest office gives a reopening date.",
  {"must_include": ["closed this weekend", "landslide", "next month", "Zoe's checking", "forest office", "reopening date"]},
  note="facts: trail closed this weekend (landslide); moved to next month; Zoe checking whether the forest office gives a reopening date (open, not answered); 'forest office' stays a common noun",
  length="medium")
# 152 pet care, long
R("messages", {**CH,
               "transcript": "biscuit's vaccination is due on the nineteenth don't let me forget uh the vet said to bring the old vaccination card and not to feed him for two hours before because he gets sick in the car also they've changed their timings so it's ten to one in the morning and four to seven in the evening and they're closed on wednesdays"},
  "Biscuit's vaccination is due on the 19th. Don't let me forget. The vet said to bring the old vaccination card and not to feed him for 2 hours before, because he gets sick in the car. Also, they've changed their timings: it's 10 to 1 in the morning and 4 to 7 in the evening, and they're closed on Wednesdays.",
  {"numbers": ["19", "2", "10", "1", "4", "7"], "must_include": ["Biscuit's vaccination", "19th", "Don't let me forget", "old vaccination card", "not to feed him", "sick in the car", "changed their timings", "closed on Wednesdays"], "min_negations": 2},
  note="facts: vaccination due the 19th; bring old card; no food for 2 hours before (gets car-sick); new timings 10 to 1 morning and 4 to 7 evening; closed Wednesdays")
# 153 Hinglish cricket
R("messages", {**CH, "locale": "en-in",
               "transcript": "bhai log kal ka match rain ki wajah se called off ho gaya refunds will come in five to seven working days"},
  "Bhai log, kal ka match rain ki wajah se called off ho gaya. Refunds will come in 5 to 7 working days.",
  {"numbers": ["5", "7"], "must_include": ["Bhai log", "kal ka match rain ki wajah se called off ho gaya", "Refunds", "working days"]},
  note="facts: Hinglish kept; match called off due to rain; refunds in 5 to 7 working days (range kept)",
  length="short")
# 154 congratulations, playful
R("messages", {**CH,
               "instruction": "make it playful",
               "transcript": "jasper congrats on hitting a hundred clients that's a proper milestone"},
  "Jasper, a whole hundred clients. That's a proper milestone, congrats.",
  {"numbers_one_of": [["hundred", "100"]], "must_include": ["Jasper", "hundred clients", "proper milestone", "congrats"], "must_not_include": ["!"]},
  note="facts: Jasper hit a hundred clients; playful rephrasing ('a whole hundred clients', congrats moved to the end) adds no fact and no exclamation mark",
  pos="after", cx=1, length="short")
# 155 family trip planning, long
R("messages", {**CH, "locale": "en-in",
               "transcript": "so for the goa trip in december here's what i've figured out um flights are booked for the twenty third returning on the twenty eighth we're staying at the same place in candolim as last time aarav and ishita share the sea facing room the rest of us are in the two cottages uh car rental is about eighteen hundred a day so i'm thinking we take one car not two and use scooters for short trips if anyone has dietary stuff tell nora she's sorting the christmas dinner"},
  "For the Goa trip in December, here's what I've figured out. Flights are booked for the 23rd, returning on the 28th. We're staying at the same place in Candolim as last time: Aarav and Ishita share the sea-facing room, and the rest of us are in the two cottages. Car rental is about 1,800 a day, so I'm thinking we take one car, not two, and use scooters for short trips. If anyone has dietary stuff, tell Nora; she's sorting the Christmas dinner.",
  {"numbers": ["23", "28", "1,800"], "must_include": ["Goa trip", "December", "Candolim", "same place", "Aarav and Ishita", "sea-facing room", "two cottages", "about 1,800 a day", "I'm thinking", "scooters", "Nora", "Christmas dinner"], "must_not_include": ["₹"], "min_negations": 1},
  note="facts: Goa trip in December; flights 23rd, return 28th; same place in Candolim; Aarav and Ishita sea-facing room, rest in the two cottages; car about 1,800 a day (no currency spoken); hedged proposal 'I'm thinking' one car NOT two plus scooters; if dietary needs, tell Nora (she's sorting Christmas dinner)",
  length="long")
# 156 neighbour, dictated apology, hedge
R("messages", {**CH,
               "transcript": "hi neighbours sorry about the barking last night our dog was scared of the fireworks we're trying a calming collar so it should be better tonight"},
  "Hi neighbours, sorry about the barking last night. Our dog was scared of the fireworks. We're trying a calming collar, so it should be better tonight.",
  {"must_include": ["Hi neighbours", "sorry about the barking", "last night", "fireworks", "calming collar", "should be better tonight"]},
  note="facts: dictated apology for last night's barking; dog scared of fireworks; trying a calming collar; hedge 'should be better tonight' kept (not a promise); greeting dictated",
  length="medium")
# 157 polite decline, "short and kind"
R("messages", {**CH,
               "instruction": "keep it short and kind",
               "length": "shorter",
               "transcript": "dev i really appreciate you asking me to captain the team for the league um but honestly i don't think i have the time this season with the new job and everything maybe ask karim he's been really keen"},
  "Dev, thanks so much for asking me to captain the league team, but honestly I don't think I have the time this season with the new job. Maybe ask Karim; he's been really keen.",
  {"must_include": ["Dev", "captain", "league", "I don't think I have the time", "this season", "new job", "Maybe ask Karim", "keen"], "min_negations": 1},
  note="facts: declines captaining the league team this season; hedge 'I don't think I have the time' kept; reason new job; suggestion hedged 'maybe ask Karim'; shorter by dropping 'and everything' and tightening, framing 'for the league' kept as 'league team'",
  pos="after", cx=2, length="medium")
# 158 reminder, plant care
R("messages", {**CH, **F,
               "transcript": "don't forget to water the curry leaf plant every other day it's in the pot by the window not the big one outside"},
  "Don't forget to water the curry leaf plant every other day. It's in the pot by the window, not the big one outside.",
  {"must_include": ["curry leaf plant", "every other day", "pot by the window", "big one outside"], "min_negations": 2},
  note="facts: water every other day; the pot by the window, NOT the big one outside",
  length="medium")
# 159 invitation, gardening club, long
R("messages", {**CH,
               "transcript": "the seed swap is happening on the first sunday of next month at the community garden from ten to one bring any extra seeds in labelled packets uh nora will have a table for cuttings too and kids are welcome but please keep them away from the seedling trays if it rains we'll move into the tool shed and it'll be a bit cramped"},
  "The seed swap is happening on the first Sunday of next month at the community garden, from 10 to 1. Bring any extra seeds in labelled packets. Nora will have a table for cuttings too. Kids are welcome, but please keep them away from the seedling trays. If it rains, we'll move into the tool shed, and it'll be a bit cramped.",
  {"numbers": ["10", "1"], "must_include": ["seed swap", "first Sunday of next month", "community garden", "labelled packets", "Nora", "table for cuttings", "Kids are welcome", "away from the seedling trays", "If it rains", "tool shed", "a bit cramped"]},
  note="facts: seed swap first Sunday of next month, community garden, 10 to 1; extra seeds in labelled packets; Nora has a cuttings table; kids welcome but kept away from seedling trays; condition: if it rains, move into the tool shed (a bit cramped)")
# 160 condolence, warmer
R("messages", {**CH,
               "instruction": "a bit warmer",
               "transcript": "rory heard about your grandad sorry mate thinking of you"},
  "Rory, I heard about your grandad, and I'm so sorry, mate. I'm thinking of you.",
  {"must_include": ["Rory", "grandad", "so sorry", "mate", "thinking of you"]},
  note="facts: condolence about Rory's grandad only; warmer wording ('I'm so sorry', full sentences); no offer, detail or family mention added",
  pos="after", cx=1, length="short")
# 161 society update, date correction stated as negation
R("messages", {**CH, "locale": "en-in", **F,
               "transcript": "the society's annual sports day is now on sunday the twenty fourth not the seventeenth because the ground was double booked registration forms are with saira and entry is free for kids under twelve"},
  "The society's annual sports day is now on Sunday the 24th, not the 17th, because the ground was double-booked. Registration forms are with Saira, and entry is free for kids under 12.",
  {"numbers": ["24", "17", "12"], "must_include": ["annual sports day", "Sunday the 24th", "double-booked", "Saira", "free for kids under 12"], "min_negations": 1},
  note="facts: sports day now Sunday the 24th, NOT the 17th (both dates kept as stated); ground double-booked; forms with Saira; free entry only for kids under 12",
  length="medium")
# 162 short
R("messages", {**CH, "register": "casual",
               "transcript": "running ten minutes late start without me"},
  "Running 10 minutes late, start without me.",
  {"numbers": ["10"], "must_include": ["late", "start without me"]},
  length="short")
# 163 third person stays third person
R("messages", {**CH,
               "transcript": "mehul's flight lands at six forty so he'll come straight to the venue he says don't wait for him for dinner"},
  "Mehul's flight lands at 6:40, so he'll come straight to the venue. He says don't wait for him for dinner.",
  {"numbers": ["6:40"], "must_include": ["Mehul's flight", "6:40", "straight to the venue", "don't wait for him"], "must_not_include": ["Mehul,"], "min_negations": 1},
  note="facts: Mehul (third person, not the addressee) lands 6:40, comes straight to the venue; his request: don't wait for him for dinner",
  length="medium")
# 164 freelance, "could you ask" kept
R("messages", {**CH,
               "transcript": "could you ask your accounts team to send the purchase order number before i raise the invoice"},
  "Could you ask your accounts team to send the purchase order number before I raise the invoice?",
  {"must_include": ["Could you ask your accounts team", "purchase order number", "before I raise the invoice"], "ends_with_question": True},
  note="facts: request goes to the recipient, who asks their accounts team; nothing addressed to the accounts team directly; order kept: PO number before invoice",
  length="short")
# 165 Hinglish hiking
R("messages", {**CH, "locale": "en-in",
               "transcript": "simran apne trekking poles le aana mere paas sirf ek extra hai and it's for zoe"},
  "Simran, apne trekking poles le aana. Mere paas sirf ek extra hai, and it's for Zoe.",
  {"must_include": ["Simran", "apne trekking poles le aana", "Mere paas sirf ek extra hai", "Zoe"]},
  note="facts: Hinglish kept; Simran to bring her own trekking poles; speaker has only one extra, and it's for Zoe",
  length="short")
# 166 reunion update, "more upbeat"
R("messages", {**CH,
               "instruction": "make it more upbeat but don't add anything",
               "transcript": "update on the reunion so far forty two people have confirmed out of the sixty we contacted um the hall is booked for the full evening from six to eleven inaya is handling the slideshow so send her old photos by the end of this week and we still haven't decided on the dj versus a playlist so vote on that if you haven't"},
  "Reunion update: 42 people have confirmed so far, out of the 60 we contacted! The hall is all booked for the full evening, from 6 to 11. Inaya is on the slideshow, so send her your old photos by the end of this week. We still haven't decided between a DJ and a playlist, so vote on that if you haven't yet.",
  {"numbers": ["42", "60", "6", "11"], "must_include": ["Reunion update", "so far", "full evening", "Inaya", "slideshow", "old photos", "end of this week", "still haven't decided", "DJ", "playlist", "if you haven't"], "min_negations": 2},
  note="facts: 42 of the 60 contacted confirmed so far; hall booked full evening 6 to 11; Inaya on slideshow, old photos to her by end of this week; DJ vs playlist still undecided, vote if you haven't; 'more upbeat' licenses one exclamation mark and livelier wording, nothing added",
  pos="before", cx=2, length="long")
# 167 pet care, long
R("messages", {**CH,
               "transcript": "the groomer moved bruno's appointment from eleven to two thirty same day so can you drop him instead i've got a call at two that i can't move he needs the short summer cut not the full shave and tell them he's scared of the dryer so towel dry is better i'll pick him up around four thirty after my call"},
  "The groomer moved Bruno's appointment from 11 to 2:30, same day, so can you drop him instead? I've got a call at 2 that I can't move. He needs the short summer cut, not the full shave, and tell them he's scared of the dryer, so towel dry is better. I'll pick him up around 4:30 after my call.",
  {"numbers": ["11", "2:30", "2", "4:30"], "must_include": ["groomer", "Bruno's appointment", "same day", "drop him", "call at 2", "short summer cut", "full shave", "scared of the dryer", "towel dry", "around 4:30"], "min_negations": 2},
  note="facts: Bruno's grooming moved from 11 to 2:30 same day (both times kept); request: recipient drops him; speaker's call at 2 can't move; short summer cut NOT full shave; tell the groomers he's scared of the dryer, towel dry better; speaker picks up around 4:30 (hedge kept)")
# 168 family trip reminder, condition
R("messages", {**CH,
               "transcript": "everyone please check your passports expire after june next year otherwise the visa won't go through"},
  "Everyone, please check that your passports expire after June next year; otherwise the visa won't go through.",
  {"must_include": ["Everyone", "passports", "after June next year", "otherwise", "visa"], "min_negations": 1},
  note="facts: passports must expire after June next year, otherwise the visa won't go through (condition and negation kept)",
  length="short")

# ---------------------------------------------------------------- style_rules (9)
# 169 excited tone + saved no-exclamation rule: excitement in wording only
R("style_rules", {**CH, "tone": "excited", "rules": ["Never use exclamation marks."],
                  "transcript": "we finally got the allotment plot after two years on the waiting list"},
  "We finally got the allotment plot, after two whole years on the waiting list.",
  {"numbers_one_of": [["two", "2"]], "must_include": ["finally", "allotment plot", "two whole years", "waiting list"], "must_not_include": ["!"]},
  note="facts: got the allotment plot after two years on the waiting list; Tone: excited shown in wording ('two whole years') because the saved rule forbids exclamation marks and excitement does not require them",
  length="short")
# 170 saved name for mom
R("style_rules", {**CH, "rules": ["Address my mom as 'Ammi'."],
                  "transcript": "mom i'll be home by nine don't wait up for dinner"},
  "Ammi, I'll be home by 9. Don't wait up for dinner.",
  {"numbers": ["9"], "must_include": ["Ammi", "home by 9", "Don't wait up"], "must_not_include": ["Mom"], "min_negations": 1},
  note="facts: home by 9 (dictated commitment); don't wait up for dinner; saved rule renders 'mom' as 'Ammi' (same person)",
  length="short")
# 171 Indian grouping, no currency spoken
R("style_rules", {**CH, "locale": "en-in", "rules": ["Use Indian number grouping (lakh, crore)."],
                  "transcript": "the reunion fund has collected one lakh twenty thousand so far and we need about fifty thousand more"},
  "The reunion fund has collected 1,20,000 so far, and we need about 50,000 more.",
  {"numbers": ["1,20,000", "50,000"], "must_include": ["reunion fund", "so far", "about 50,000 more"], "must_not_include": ["₹", "120,000"]},
  note="facts: reunion fund collected 1,20,000 (one lakh twenty thousand) so far; need about 50,000 more (hedge kept); no currency spoken, no ₹; waiver: checker reads 'one lakh twenty thousand' as 1, 100000, 20000",
  length="medium")
# 172 saved casual rule vs this turn's formal
R("style_rules", {**CH, "register": "formal", "locale": "en-in", "rules": ["Write in a casual tone.", "Never use emoji."],
                  "instruction": "make it formal, it's going to the society secretary",
                  "transcript": "hey so the leak in the terrace above flat d four is back after the rains can someone from the committee check it this week"},
  "Hello, the leak in the terrace above flat D4 has returned after the rains. Could someone from the committee please check it this week?",
  {"must_include": ["Hello", "leak", "terrace above flat D4", "after the rains", "committee", "this week"], "must_not_include": ["Hey"], "ends_with_question": True},
  note="this turn's formal request overrides the saved casual rule; the emoji rule still holds; dictated 'hey' adapted to formal 'Hello'; facts: leak above flat D4 back after the rains; committee check this week",
  pos="after", cx=1, length="medium")
# 173 saved digits + brevity
R("style_rules", {**CH, "rules": ["Write numbers as digits.", "Keep my messages short."],
                  "transcript": "so i checked the bus timings for the hill station the first one leaves at six ten and the next one is at eight forty and after that there's only one more in the afternoon at two so let's aim for the first one"},
  "I checked the bus timings for the hill station: first at 6:10, next at 8:40, then only 1 more in the afternoon at 2. Let's aim for the first one.",
  {"numbers": ["6:10", "8:40", "1", "2"], "must_include": ["bus timings", "hill station", "only 1 more", "afternoon", "first one"]},
  note="facts: buses at 6:10, 8:40, then only one more in the afternoon at 2; proposal to aim for the first; saved rules digits and short applied without dropping a time",
  length="medium")
# 174 saved "never start with Hey" + apologetic instruction
R("style_rules", {**P, "rules": ["Never start a message with 'Hey'."],
                  "instruction": "more apologetic, but no excuses I didn't give",
                  "transcript": "hey zoe i forgot to return your hiking poles i'll drop them at your place on saturday morning"},
  "Zoe, I'm really sorry, I completely forgot to return your hiking poles. I'll drop them at your place on Saturday morning.",
  {"must_include": ["Zoe", "really sorry", "forgot", "hiking poles", "your place", "Saturday morning"], "must_not_include": ["Hey"]},
  note="facts: forgot to return Zoe's hiking poles; dictated commitment: drop them at her place Saturday morning; apology wording added per instruction, no reason invented; saved rule removes the dictated 'Hey' opener, the name stays as a vocative",
  pos="before", cx=2, length="short")
# 175 saved 24-hour rule
R("style_rules", {**CH, "rules": ["Use 24-hour time."],
                  "transcript": "the plant nursery opens at nine thirty in the morning and closes at seven thirty pm on weekends"},
  "The plant nursery opens at 09:30 and closes at 19:30 on weekends.",
  {"numbers": ["09:30", "19:30"], "must_include": ["plant nursery", "weekends"]},
  note="facts: opens 9:30 a.m. = 09:30, closes 7:30 p.m. = 19:30, on weekends; 24-hour format is a saved style, not a fact change; waiver: checker reads 'seven thirty pm' as 7 and does not map it to 19:30",
  waivers=["number_missing"], length="short")
# 176 this turn's instruction beats saved no-exclamation rule
R("style_rules", {**CH, "rules": ["No exclamation marks.", "Keep messages under 20 words."],
                  "instruction": "make it sound excited",
                  "transcript": "aarav cleared his driving test on the first try"},
  "Aarav cleared his driving test on the very first try!",
  {"must_include": ["Aarav cleared his driving test", "very first try"], "max_words": 20},
  note="this turn's 'sound excited' instruction overrides the saved no-exclamation rule; the word limit still holds; Aarav is third person, not the addressee; facts: cleared driving test on the first try",
  pos="after", cx=1, length="short")
# 177 long, three saved rules
R("style_rules", {**CH, "locale": "en-gb", "rules": ["Use British spelling.", "Write numbers as digits.", "Never use emoji."],
                  "transcript": "okay so for the junior coaching program this term we have eighteen kids signed up split into two groups beginners on tuesdays and intermediates on thursdays both at five pm uh the fee is the same as last term and we're not changing the venue but we do need one more volunteer coach for the beginners because ishita is traveling for most of november if you can help even for two or three sessions let me know"},
  "For the junior coaching programme this term, we have 18 kids signed up, split into 2 groups: beginners on Tuesdays and intermediates on Thursdays, both at 5 p.m. The fee is the same as last term, and we're not changing the venue. We do need 1 more volunteer coach for the beginners, because Ishita is travelling for most of November. If you can help, even for 2 or 3 sessions, let me know.",
  {"numbers": ["18", "2", "5", "1", "3"], "must_include": ["junior coaching programme", "this term", "beginners", "Tuesdays", "intermediates", "Thursdays", "same as last term", "Ishita", "travelling", "most of November", "If you can help"], "must_not_include": ["program ", "traveling"], "min_negations": 1},
  note="facts: 18 kids in 2 groups (beginners Tue, intermediates Thu, both 5 p.m.); fee same as last term; venue NOT changing; need 1 more volunteer coach for beginners because Ishita travels most of November; 2 OR 3 sessions alternative kept; conditional 'if you can help'; British spelling programme/travelling; waiver: checker does not read spoken 'one more' as 1, so the digit required by the saved digits rule is flagged as invented",
  waivers=["number_invented"], length="long")

# ---------------------------------------------------------------- dev_custom_style (8)
# 178
R("dev_custom_style", {**CH, "rules": ["Refer to the app as 'GreenThumb'.", "House style: sentence case."],
                       "transcript": "i logged the tomato harvest in green thumb it was about four kilos this week"},
  "I logged the tomato harvest in GreenThumb. It was about 4 kilos this week.",
  {"numbers": ["4"], "must_include": ["GreenThumb", "tomato harvest", "about 4 kilos", "this week"], "must_not_include": ["green thumb"]},
  note="facts: about 4 kilos this week (hedge kept); app name in house form",
  length="short")
# 179 cricket score format
R("dev_custom_style", {**CH, "locale": "en-in", "rules": ["Write cricket scores as runs/wickets, e.g. '182/6'."],
                       "transcript": "india finished on one eighty two for six and the chase starts after the break"},
  "India finished on 182/6, and the chase starts after the break.",
  {"numbers": ["182/6"], "must_include": ["India", "182/6", "chase", "after the break"]},
  note="facts: India 182 for 6 written 182/6 per house style; chase after the break; waiver: checker reads 'one eighty two' as 1 and 82 and does not match 182/6",
  length="short")
# 180 house term that would change meaning is not applied
R("dev_custom_style", {**CH, "locale": "en-in", "rules": ["Use 'residents', not 'members'."], **F,
                       "transcript": "members of the managing committee will be at the gate on sunday morning to collect feedback from all members about the new parking rules"},
  "Members of the managing committee will be at the gate on Sunday morning to collect feedback from all residents about the new parking rules.",
  {"must_include": ["Members of the managing committee", "gate", "Sunday morning", "feedback from all residents", "new parking rules"], "must_not_include": ["residents of the managing committee"]},
  note="'members of the managing committee' is a committee role, so the house term is not applied there; 'all members' (the residents) becomes 'all residents'; facts: committee at the gate Sunday morning collecting feedback on the new parking rules",
  length="medium")
# 181 banned abbreviation
R("dev_custom_style", {**CH, "rules": ["Never write 'ASAP'; write 'as soon as possible'."],
                       "transcript": "can you send the final copy asap the client meeting got moved up to tomorrow morning"},
  "Can you send the final copy as soon as possible? The client meeting got moved up to tomorrow morning.",
  {"must_include": ["final copy", "as soon as possible", "client meeting", "moved up", "tomorrow morning"], "must_not_include": ["ASAP"]},
  note="facts: urgency kept ('as soon as possible'); client meeting moved up to tomorrow morning",
  length="short")
# 182 units and digits
R("dev_custom_style", {**CH, "rules": ["Use 'kg' for kilograms.", "Write numbers as digits."],
                       "transcript": "the vet said bruno needs to lose two kilograms so cut his food to one and a half cups a day"},
  "The vet said Bruno needs to lose 2 kg, so cut his food to 1.5 cups a day.",
  {"numbers": ["2", "1.5"], "must_include": ["vet", "Bruno", "2 kg", "1.5 cups a day"]},
  note="facts: Bruno to lose 2 kg; food cut to one and a half (1.5) cups a day; house unit and digit style; waiver: checker reads 'one and a half' as 1 and does not match 1.5",
  waivers=["number_missing"], length="short")
# 183 banned 'guys', long
R("dev_custom_style", {**CH, "rules": ["Don't use the word 'guys'; use 'everyone'."],
                       "transcript": "guys the bus for the stadium leaves at noon sharp and it won't wait uh it's from the club gate not the main road so don't go to the bus stop everyone needs their ticket on their phone and a photo id and the stadium doesn't allow bags bigger than a4 size so carry only small stuff we'll be back around eight depending on traffic"},
  "Everyone, the bus for the stadium leaves at noon sharp, and it won't wait. It's from the club gate, not the main road, so don't go to the bus stop. Everyone needs their ticket on their phone and a photo ID, and the stadium doesn't allow bags bigger than A4 size, so carry only small stuff. We'll be back around 8, depending on traffic.",
  {"numbers": ["8"], "must_include": ["Everyone", "noon sharp", "won't wait", "club gate", "main road", "bus stop", "ticket on their phone", "photo ID", "A4 size", "only small stuff", "around 8, depending on traffic"], "must_not_include": ["guys"], "min_negations": 4},
  note="facts: bus at noon sharp, won't wait; from the club gate NOT the main road, don't go to the bus stop; ticket on phone + photo ID; no bags bigger than A4; back around 8 depending on traffic (hedge kept); house word replaces the vocative")
# 184 currency style Rs
R("dev_custom_style", {**CH, "locale": "en-in", "rules": ["Write currency as 'Rs', not '₹'."],
                       "transcript": "the plant sale made six thousand four hundred rupees and the money goes to the new greenhouse"},
  "The plant sale made Rs 6,400, and the money goes to the new greenhouse.",
  {"numbers": ["6,400"], "must_include": ["plant sale", "Rs 6,400", "new greenhouse"], "must_not_include": ["₹"]},
  note="facts: plant sale made 6,400 rupees, written Rs per house style; money goes to the new greenhouse",
  length="short")
# 185 long, three house rules
R("dev_custom_style", {**CH, "rules": ["House style: sentence case.", "Use 'session' instead of 'class'.", "Write times like '4 pm', without periods."],
                       "transcript": "hi everyone so the composting class this saturday is moved from the community garden to nora's terrace because the garden is being fumigated the class starts at four pm and runs for about two hours um please bring gloves we'll provide the bins and the soil and uh you know if it rains we'll shift it to sunday at the same time"},
  "Hi everyone, the composting session this Saturday is moved from the community garden to Nora's terrace because the garden is being fumigated. The session starts at 4 pm and runs for about two hours. Please bring gloves; we'll provide the bins and the soil. If it rains, we'll shift it to Sunday at the same time.",
  {"numbers": ["4"], "numbers_one_of": [["two", "2"]], "must_include": ["Hi everyone", "composting session", "this Saturday", "community garden", "Nora's terrace", "fumigated", "4 pm", "about two hours", "gloves", "bins", "soil", "If it rains", "Sunday at the same time"], "must_not_include": ["class", "4 p.m."]},
  note="facts: composting session this Saturday moved from community garden to Nora's terrace (garden being fumigated); 4 pm, about two hours (hedge kept); bring gloves (unconditional); bins and soil provided; condition: if it rains, shift to Sunday same time; greeting dictated; house terms/time style applied",
  length="long")

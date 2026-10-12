# W10 stage 2, chunk 3: TC-W10-186..230 (exec'd by W10_s2.py)

# ---------------------------------------------------------------- messages (24)
# 186 condolence to a neighbour, offer dictated
R("messages", {**P, "tone": "empathetic", "locale": "en-in", **F,
               "transcript": "mrs kapoor we were so sorry to hear that uncle passed away um if you need help with anything at all over the next few days please just knock"},
  "Mrs. Kapoor, we were so sorry to hear that uncle passed away. If you need help with anything at all over the next few days, please just knock.",
  {"must_include": ["Mrs. Kapoor", "so sorry", "passed away", "If you need help", "next few days", "just knock"]},
  note="facts: condolence; the offer of help over the next few days is dictated and stays conditional ('if you need'); no funeral or other detail added",
  length="medium")
# 187 congratulations, warm
R("messages", {**P, "tone": "warm",
               "transcript": "saira congrats on the baby girl hope you're both doing well and getting some rest"},
  "Saira, congratulations on the baby girl. I hope you're both doing well and getting some rest.",
  {"must_include": ["Saira", "congratulations", "baby girl", "both doing well", "rest"], "must_not_include": ["!"]},
  note="facts: congratulations on the baby girl; hope both are well and resting; no name, weight or date of birth added; no exclamation marks",
  length="short")
# 188 dictated apology to a client, professional, self-stated correction kept
R("messages", {**CH,
               "instruction": "keep the apology but make it more professional, it's a client",
               "transcript": "sorry callum the invoice i sent had the wrong amount it should be thirty two thousand not twenty three thousand i'll send a corrected one tonight"},
  "Callum, my apologies: the invoice I sent had the wrong amount. It should be 32,000, not 23,000. I'll send a corrected one tonight.",
  {"numbers": ["32,000", "23,000"], "must_include": ["Callum", "apologies", "invoice", "wrong amount", "32,000", "not 23,000", "corrected one tonight"], "must_not_include": ["₹", "$"], "min_negations": 1},
  note="facts: invoice had the wrong amount; correct is 32,000, NOT 23,000 (both kept as the speaker contrasts them; no currency spoken); dictated commitment: corrected invoice tonight; 'sorry' made professional as 'my apologies'",
  pos="after", cx=2, length="medium")
# 189 invitation, chess, long
R("messages", {**CH,
               "transcript": "we're hosting a casual puzzle solving evening at my flat on friday from eight bring a board if you have one the first round starts at eight fifteen um it's not rated so beginners are totally welcome dev is setting the puzzles and there's a small prize for whoever solves the most by ten i'll order pizza so tell me by thursday if you're coming"},
  "We're hosting a casual puzzle-solving evening at my flat on Friday from 8. Bring a board if you have one; the first round starts at 8:15. It's not rated, so beginners are totally welcome. Dev is setting the puzzles, and there's a small prize for whoever solves the most by 10. I'll order pizza, so tell me by Thursday if you're coming.",
  {"numbers": ["8", "8:15", "10"], "must_include": ["puzzle-solving evening", "my flat", "Friday", "if you have one", "first round", "8:15", "not rated", "beginners", "Dev", "small prize", "solves the most by 10", "order pizza", "Thursday"], "min_negations": 1},
  note="facts: puzzle-solving evening at speaker's flat Friday from 8; bring a board only if you have one; first round 8:15; NOT rated, beginners welcome; Dev sets puzzles; small prize for most solved by 10; speaker orders pizza; RSVP by Thursday")
# 190 Hinglish decline, dictated apology and promise
R("messages", {**CH, "locale": "en-in", "register": "casual",
               "transcript": "sorry yaar sunday ko nahi ho payega i have a client deadline monday morning next weekend pakka"},
  "Sorry yaar, Sunday ko nahi ho payega. I have a client deadline Monday morning. Next weekend pakka.",
  {"must_include": ["Sorry yaar", "Sunday ko nahi ho payega", "client deadline", "Monday morning", "Next weekend pakka"]},
  note="facts: Hinglish kept; can't do Sunday ('nahi', negation kept); client deadline Monday morning; dictated promise 'next weekend pakka' kept as is",
  length="short")
# 191 reminder to family, speaker talking to Aarav
R("messages", {**CH,
               "transcript": "aarav pack your swimming stuff and a warm jacket the resort has a pool but the nights get cold up there"},
  "Aarav, pack your swimming stuff and a warm jacket. The resort has a pool, but the nights get cold up there.",
  {"must_include": ["Aarav", "swimming stuff", "warm jacket", "pool", "nights get cold"]},
  note="the speaker is clearly talking TO Aarav (imperative 'pack your'), so the vocative is right; facts: swimming stuff and warm jacket; pool at the resort; cold nights",
  length="short")
# 192 cricket fans group recap, long, instruction
R("messages", {**CH, "locale": "en-in",
               "instruction": "make it a clear recap for the group, keep the names and numbers, no bullets",
               "transcript": "so um quick recap of the fantasy league this season mehul topped it with fourteen hundred and twenty points jasper was second by just thirty points and rory finished last again so he's buying the first round at the season party which is on the twelfth at the usual place uh the entry for next season goes up to five hundred each because the app started charging us and we still need someone to run the league because i'm stepping down"},
  "Quick recap of the fantasy league this season: Mehul topped it with 1,420 points, Jasper was second by just 30 points, and Rory finished last again, so he's buying the first round at the season party on the 12th at the usual place.\n\nEntry for next season goes up to 500 each because the app started charging us. We still need someone to run the league, because I'm stepping down.",
  {"numbers": ["1,420", "30", "12", "500"], "must_include": ["fantasy league", "this season", "Mehul", "Jasper", "Rory", "last again", "first round", "season party", "usual place", "next season", "app started charging", "still need someone to run the league", "stepping down"], "must_not_include": ["₹", "- "]},
  note="facts: Mehul top with 1,420; Jasper second by just 30; Rory last AGAIN, buys first round at the season party on the 12th, usual place; next season entry up to 500 each (no currency spoken) because the app charges; still need someone to run the league; speaker stepping down",
  pos="before", cx=3, length="long")
# 193 neighbour notice
R("messages", {**CH, "locale": "en-in", **F,
               "transcript": "a parcel for flat b eleven was left with me by mistake it's a big box from an electronics store i'm home after six if you want to collect it"},
  "A parcel for flat B11 was left with me by mistake. It's a big box from an electronics store. I'm home after 6 if you want to collect it.",
  {"numbers": ["11", "6"], "must_include": ["parcel", "flat B11", "by mistake", "big box", "electronics store", "after 6", "collect"]},
  note="facts: parcel for flat B11 left with the speaker by mistake; big box from an electronics store; speaker home after 6 for collection",
  length="medium")
# 194 "more casual" visibly changes wording
R("messages", {**CH,
               "instruction": "more casual, it's our college group",
               "transcript": "dear all this is a gentle reminder that the contribution for the reunion dinner is two thousand per person and should be transferred to inaya by the end of the month"},
  "Hey all, quick reminder: the reunion dinner contribution is 2,000 per person, and it needs to go to Inaya by the end of the month.",
  {"numbers": ["2,000"], "must_include": ["reunion dinner", "2,000 per person", "Inaya", "end of the month"], "must_not_include": ["Dear all", "gentle reminder", "₹"]},
  note="facts: reunion dinner contribution 2,000 per person (no currency spoken) to Inaya by end of month; dictated 'dear all' adapted to casual 'Hey all'; casual wording ('quick reminder', 'needs to go to') is the visible change",
  pos="after", cx=1, length="medium")
# 195 third-person dictation
R("messages", {**CH,
               "transcript": "dev's mum called she said he left his charger at our place i'll drop it at the club on thursday"},
  "Dev's mum called. She said he left his charger at our place. I'll drop it at the club on Thursday.",
  {"must_include": ["Dev's mum called", "charger", "our place", "club", "Thursday"], "must_not_include": ["Dev,"]},
  note="facts: Dev's mum called (Dev is third person, not the addressee); charger left at speaker's place; speaker's own commitment: drop it at the club Thursday",
  length="short")
# 196 pet care
R("messages", {**CH,
               "transcript": "please don't give pepper any grapes they're toxic for dogs"},
  "Please don't give Pepper any grapes; they're toxic for dogs.",
  {"must_include": ["Pepper", "grapes", "toxic for dogs"], "min_negations": 1},
  length="short")
# 197 hedges kept
R("messages", {**CH, **F,
               "transcript": "i think the aphids are back on the roses near the gate maybe we should try neem spray before anything stronger"},
  "I think the aphids are back on the roses near the gate. Maybe we should try neem spray before anything stronger.",
  {"must_include": ["I think", "aphids", "roses near the gate", "Maybe", "neem spray", "before anything stronger"]},
  note="facts: hedges 'I think' (aphids back) and 'maybe' (neem spray first) both kept",
  length="medium")
# 198 freelance, dictated offer
R("messages", {**CH, "tone": "friendly",
               "transcript": "hey inaya loved working on the menu cards with you let me know if your cousin's shop needs anything similar"},
  "Hey Inaya, loved working on the menu cards with you. Let me know if your cousin's shop needs anything similar.",
  {"must_include": ["Hey Inaya", "menu cards", "cousin's shop", "anything similar"], "must_not_include": ["!"]},
  note="facts: greeting and the offer ('let me know if...') are dictated; nothing else added; friendly tone, no exclamation marks",
  length="medium")
# 199 invitation, hike, long, conditions
R("messages", {**CH, "locale": "en-in",
               "transcript": "planning a sunrise hike to the fort next sunday um we'd leave from the parking lot at four thirty a m it's about a ninety minute climb in the dark so headlamps are a must uh it's not for beginners honestly but if you've done the waterfall loop you'll be fine we'll have breakfast at the top so carry something to share max ten people so reply by wednesday to grab a spot"},
  "Planning a sunrise hike to the fort next Sunday. We'd leave from the parking lot at 4:30 a.m. It's about a 90-minute climb in the dark, so headlamps are a must. Honestly, it's not for beginners, but if you've done the waterfall loop, you'll be fine. We'll have breakfast at the top, so carry something to share. Max ten people, so reply by Wednesday to grab a spot.",
  {"numbers": ["4:30", "90"], "numbers_one_of": [["ten", "10"]], "must_include": ["sunrise hike", "fort", "next Sunday", "parking lot", "about a 90-minute climb", "headlamps are a must", "not for beginners", "if you've done the waterfall loop", "breakfast at the top", "something to share", "Max ten people", "Wednesday"], "min_negations": 1},
  note="facts: sunrise hike to the fort next Sunday; leave parking lot 4:30 a.m.; about 90-minute climb in the dark; headlamps required; NOT for beginners, but fine IF you've done the waterfall loop; breakfast at the top, carry something to share; max ten people; reply by Wednesday; 'waterfall loop' kept lowercase",
  length="long")
# 200 Hinglish question
R("messages", {**CH, "locale": "en-in", "register": "casual",
               "transcript": "inaya tu bhi aa rahi hai na reunion pe please bol de haan"},
  "Inaya, tu bhi aa rahi hai na reunion pe? Please bol de haan.",
  {"must_include": ["Inaya", "tu bhi aa rahi hai na reunion pe", "Please bol de haan"]},
  note="facts: Hinglish kept word for word; question about coming to the reunion stays a question, not answered",
  length="short")
# 201 condolence, gentler
R("messages", {**P,
               "instruction": "make it gentler",
               "transcript": "karim i'm so sorry about your mother she was always so kind to all of us when we came over after matches if you want company this week i'm around"},
  "Karim, I'm so very sorry about your mother. She was always so kind to all of us when we came over after matches. If you'd like some company this week, I'm around.",
  {"must_include": ["Karim", "so very sorry", "your mother", "so kind", "after matches", "If you'd like some company", "this week", "I'm around"]},
  note="facts: condolence; memory of her kindness after matches is dictated; offer of company this week stays conditional; gentler wording ('so very sorry', 'if you'd like some company'), no detail added",
  pos="after", cx=1, length="medium")
# 202 reminder to family
R("messages", {**CH, "locale": "en-in",
               "transcript": "dadi your eye check up is on thursday at eleven thirty i'll pick you up at eleven"},
  "Dadi, your eye check-up is on Thursday at 11:30. I'll pick you up at 11.",
  {"numbers": ["11:30", "11"], "must_include": ["Dadi", "eye check-up", "Thursday", "pick you up"]},
  note="facts: eye check-up Thursday 11:30; speaker's own commitment to pick her up at 11",
  length="short")
# 203 short society
R("messages", {**CH,
               "transcript": "lift in tower c is working again"},
  "The lift in Tower C is working again.",
  {"must_include": ["lift", "Tower C", "working again"]},
  length="short")
# 204 alternatives, hedge
R("messages", {**CH, "locale": "en-in",
               "transcript": "tickets are either fifteen hundred for the upper tier or thirty two hundred for the pavilion i'm leaning upper tier but tell me what you think"},
  "Tickets are either 1,500 for the upper tier or 3,200 for the pavilion. I'm leaning upper tier, but tell me what you think.",
  {"numbers": ["1,500", "3,200"], "must_include": ["upper tier", "pavilion", "leaning upper tier", "what you think"], "must_not_include": ["₹"]},
  note="facts: alternatives both kept: 1,500 upper tier OR 3,200 pavilion (no currency spoken); speaker only leaning upper tier, not decided",
  length="medium")
# 205 "ask nora" kept as dictated
R("messages", {**CH,
               "transcript": "could you ask nora if she can lend us her pressure washer for the terrace on saturday"},
  "Could you ask Nora if she can lend us her pressure washer for the terrace on Saturday?",
  {"must_include": ["Could you ask Nora", "pressure washer", "terrace", "Saturday"], "must_not_include": ["Nora,"], "ends_with_question": True},
  note="facts: the recipient is asked to check with Nora; Nora is NOT the addressee; request kept as a question, not answered",
  length="short")
# 206 more formal for a volunteers group
R("messages", {**CH,
               "instruction": "a bit more formal, it's going to the forest department volunteers group",
               "transcript": "hey folks so the cleanup drive collected thirty seven bags of plastic from the lower trail we're not doing the upper trail until the monsoon ends"},
  "Hello all, the clean-up drive collected 37 bags of plastic from the lower trail. We will not be doing the upper trail until the monsoon ends.",
  {"numbers": ["37"], "must_include": ["clean-up drive", "37 bags", "lower trail", "upper trail", "until the monsoon ends"], "must_not_include": ["Hey folks"], "min_negations": 1},
  note="facts: 37 bags of plastic from the lower trail; upper trail NOT until the monsoon ends; dictated 'hey folks' adapted to 'Hello all'; contractions expanded for the formal request",
  pos="after", cx=1, length="medium")
# 207 dictated apology, society, dictated promise
R("messages", {**CH, "locale": "en-in",
               "transcript": "really sorry about the noise from our flat on saturday it was my son's birthday and it went on later than planned it won't happen again"},
  "Really sorry about the noise from our flat on Saturday. It was my son's birthday, and it went on later than planned. It won't happen again.",
  {"must_include": ["Really sorry", "noise", "our flat", "Saturday", "son's birthday", "later than planned", "won't happen again"], "min_negations": 1},
  note="facts: apology and the promise 'it won't happen again' are both dictated; reason son's birthday on Saturday ran late",
  length="medium")
# 208 freelance call request
R("messages", {**CH, **F,
               "transcript": "can we do a quick call on tuesday at four ist to go over the feedback it should take twenty minutes max"},
  "Can we do a quick call on Tuesday at 4 IST to go over the feedback? It should take 20 minutes max.",
  {"numbers": ["4", "20"], "must_include": ["quick call", "Tuesday", "4 IST", "feedback", "should take 20 minutes max"]},
  note="facts: call Tuesday at 4 IST (no a.m./p.m. spoken, none added); hedge 'should' and 'max' kept",
  length="short")
# 209 congratulations, excited tone
R("messages", {**CH, "tone": "excited",
               "transcript": "nora your dahlias won first prize at the flower show"},
  "Nora, your dahlias won first prize at the flower show!",
  {"must_include": ["Nora", "dahlias", "first prize", "flower show"]},
  note="Tone: excited licenses the exclamation mark; no fact added",
  length="short")

# ---------------------------------------------------------------- style_rules (10)
# 210 banned 'lol'
R("style_rules", {**CH, "register": "casual", "rules": ["Never use 'lol'."],
                  "transcript": "lol the dog stole the whole paratha off my plate"},
  "The dog stole the whole paratha off my plate.",
  {"must_include": ["dog", "whole paratha", "my plate"], "must_not_include": ["lol"]},
  note="saved rule removes 'lol' (no fact); facts: dog stole the whole paratha",
  length="short")
# 211 British spelling, friendly tone, no "!"
R("style_rules", {**CH, "tone": "friendly", "locale": "en-gb", "rules": ["Use British spelling.", "No exclamation marks."],
                  "transcript": "the neighborhood kids organized a cleanup of the park and filled nine bags of trash"},
  "The neighbourhood kids organised a clean-up of the park and filled nine bags of trash.",
  {"numbers_one_of": [["nine", "9"]], "must_include": ["neighbourhood", "organised", "clean-up", "park", "nine bags"], "must_not_include": ["neighborhood", "organized", "!"]},
  note="facts: kids organised a park clean-up, nine bags; saved rules British spelling and no exclamation marks",
  length="short")
# 212 per cent rule, long
R("style_rules", {**CH, "locale": "en-gb", "rules": ["Write 'per cent', not '%'."],
                  "transcript": "turnout at the agm was only forty percent so the vote on the parking fee is postponed to next month um we need at least fifty percent for the vote to count so please please try to come next time or send a proxy um and the committee will also share the minutes on the notice board by friday okay so yeah"},
  "Turnout at the AGM was only 40 per cent, so the vote on the parking fee is postponed to next month. We need at least 50 per cent for the vote to count, so please try to come next time or send a proxy. The committee will also share the minutes on the notice board by Friday.",
  {"numbers": ["40", "50"], "must_include": ["AGM", "only 40 per cent", "parking fee", "postponed", "next month", "at least 50 per cent", "for the vote to count", "come next time or send a proxy", "minutes", "notice board", "Friday"], "must_not_include": ["%"]},
  note="facts: AGM turnout only 40 per cent; parking fee vote postponed to next month; at least 50 per cent needed for the vote to count; come next time OR send a proxy (both kept); minutes on the notice board by Friday")
# 213 saved client sign-off
R("style_rules", {**CH, "rules": ["End messages to clients with 'Thanks, Ishita'."],
                  "transcript": "the revised logo is uploaded to the shared folder and i've kept both the blue and the green versions so you can choose"},
  "The revised logo is uploaded to the shared folder, and I've kept both the blue and the green versions so you can choose.\n\nThanks, Ishita",
  {"must_include": ["revised logo", "shared folder", "blue", "green versions", "choose", "Thanks, Ishita"]},
  note="sign-off comes from the saved rule for client messages, not invented; facts: revised logo in the shared folder; both blue and green versions kept for the client to choose",
  length="medium")
# 214 saved word limit + warmer
R("style_rules", {**CH, "rules": ["Keep messages under 30 words."],
                  "instruction": "make it warmer",
                  "transcript": "hi rory the gardening club is meeting at the greenhouse on saturday at nine we're repotting the cacti would love to see you there"},
  "Hi Rory, the gardening club is meeting at the greenhouse on Saturday at 9 to repot the cacti. We'd really love to see you there.",
  {"numbers": ["9"], "max_words": 30, "must_include": ["Hi Rory", "gardening club", "greenhouse", "Saturday", "repot the cacti", "really love to see you"]},
  note="facts: club meets at the greenhouse Saturday at 9, repotting the cacti; invitation dictated; warmer wording ('We'd really love') within the saved 30-word limit; greeting dictated",
  pos="after", cx=1, length="medium")
# 215 Mum spelling; "tell" kept
R("style_rules", {**CH, "locale": "en-gb", "rules": ["Write 'Mum', never 'Mom'."],
                  "transcript": "tell mom i'll be late for dinner the train's delayed by forty minutes"},
  "Tell Mum I'll be late for dinner; the train's delayed by 40 minutes.",
  {"numbers": ["40"], "must_include": ["Tell Mum", "late for dinner", "delayed by 40 minutes"], "must_not_include": ["Mom"]},
  note="facts: the recipient is asked to tell Mum (Mum is not the addressee); late for dinner; train delayed 40 minutes",
  length="short")
# 216 digits + 12-hour time
R("style_rules", {**CH, "rules": ["Write numbers as digits.", "Use 12-hour time with a.m./p.m."],
                  "transcript": "the simul starts at eighteen hundred and each of the twenty boards gets a ten minute clock"},
  "The simul starts at 6 p.m., and each of the 20 boards gets a 10-minute clock.",
  {"numbers": ["6", "20", "10"], "must_include": ["simul", "6 p.m.", "20 boards", "10-minute clock"]},
  note="facts: simul at eighteen hundred = 6 p.m. (saved 12-hour rule); 20 boards; 10-minute clock each; waiver: checker reads 'eighteen hundred' as 1800 and does not map it to 6 p.m.",
  waivers=["number_missing", "number_invented"], length="short")
# 217 saved greeting for the cricket group, long
R("style_rules", {**CH, "rules": ["Start messages to the cricket group with 'Hi all'."],
                  "transcript": "practice is cancelled tomorrow the nets are being resurfaced um so we'll do the fielding session on thursday instead same time six to eight at the main ground and bring your own balls if you have them because the club ones are being replaced uh also the jerseys finally arrived saira will hand them out on thursday and it's six hundred fifty each so bring cash or pay her online"},
  "Hi all, practice is cancelled tomorrow. The nets are being resurfaced. We'll do the fielding session on Thursday instead, same time, 6 to 8, at the main ground. Bring your own balls if you have them, because the club ones are being replaced. Also, the jerseys finally arrived. Saira will hand them out on Thursday, and it's 650 each, so bring cash or pay her online.",
  {"numbers": ["6", "8", "650"], "must_include": ["Hi all", "practice is cancelled tomorrow", "nets", "resurfaced", "fielding session", "Thursday instead", "main ground", "if you have them", "club ones are being replaced", "jerseys", "Saira", "650 each", "cash or pay her online"], "must_not_include": ["₹"]},
  note="greeting comes from the saved rule, not invented; facts: practice cancelled tomorrow; nets being resurfaced (kept as its own sentence, no causal link added); fielding session Thursday instead, same time 6 to 8, main ground; own balls only if you have them; jerseys arrived, Saira hands out Thursday, 650 each (no currency spoken), cash OR online both kept")
# 218 banned word + two paragraphs, long
R("style_rules", {**CH, "rules": ["Never use the word 'basically'."],
                  "instruction": "make it clearer and split it into two short paragraphs",
                  "transcript": "so basically the cat sitter is coming twice a day morning around eight and evening around six she has the spare key and she knows mochi needs her thyroid pill in the morning only not in the evening and basically if anything seems off she'll call the vet first and then me the vet's number is on the fridge yeah okay"},
  "The cat sitter is coming twice a day: in the morning around 8 and in the evening around 6. She has the spare key, and she knows Mochi needs her thyroid pill in the morning only, not in the evening.\n\nIf anything seems off, she'll call the vet first and then me. The vet's number is on the fridge.",
  {"numbers": ["8", "6"], "must_include": ["cat sitter", "twice a day", "around 8", "around 6", "spare key", "Mochi", "thyroid pill", "morning only", "not in the evening", "If anything seems off", "vet first and then me", "fridge"], "must_not_include": ["basically"], "min_negations": 1},
  note="facts: sitter twice a day, around 8 and around 6 (hedges kept); has spare key; Mochi's thyroid pill morning only, NOT evening; if anything seems off, sitter calls the vet first, then the speaker (order kept); vet's number on the fridge; two paragraphs per instruction",
  pos="after", cx=2, length="long")
# 219 Facts: correct, only the named date
R("style_rules", {**CH, "facts": "correct", "rules": ["Write numbers as digits."],
                  "instruction": "it's the 9th, not the 8th, fix that",
                  "transcript": "the gardening club potluck is on saturday the eighth at five at simran's place bring a dish each"},
  "The gardening club potluck is on Saturday the 9th at 5 at Simran's place. Bring a dish each.",
  {"numbers": ["9", "5"], "must_include": ["gardening club potluck", "Saturday", "9th", "at 5", "Simran's place", "a dish each"], "must_not_include": ["8th"]},
  note="authorised correction: only the date 8th -> 9th (instruction names it); Saturday, 5, Simran's place and 'a dish each' unchanged; waiver: checker expects the dictated 8 and does not know the instruction replaced it",
  waivers=["number_missing"], pos="after", cx=1, length="medium")

# ---------------------------------------------------------------- dev_custom_style (11)
# 220 group name, long
R("dev_custom_style", {**CH, "rules": ["Refer to the group as 'Boundary Club', never 'the cricket group'."],
                       "transcript": "the cricket group's watch party is at karim's on saturday uh the match starts at seven thirty so come by seven karim says no more than fifteen people because his living room is small so um put your name on the list in the cricket group by thursday we're splitting the food bill equally and uh mehul is bringing the projector"},
  "Boundary Club's watch party is at Karim's on Saturday. The match starts at 7:30, so come by 7. Karim says no more than 15 people because his living room is small, so put your name on the list in Boundary Club by Thursday. We're splitting the food bill equally, and Mehul is bringing the projector.",
  {"numbers": ["7:30", "7", "15"], "must_include": ["Boundary Club", "watch party", "Karim's", "Saturday", "come by 7", "no more than 15 people", "living room is small", "list", "Thursday", "splitting the food bill equally", "Mehul", "projector"], "must_not_include": ["cricket group"], "min_negations": 1},
  note="facts: watch party at Karim's Saturday; match 7:30, come by 7; max 15 people (Karim, small living room); names on the list by Thursday; food bill split equally; Mehul brings the projector; both mentions of the group renamed per house rule")
# 221 term + negation
R("dev_custom_style", {**CH, "rules": ["Use 'client' instead of 'customer'."], **F,
                       "transcript": "the customer wants the deck in landscape not portrait and in two languages english and marathi"},
  "The client wants the deck in landscape, not portrait, and in two languages, English and Marathi.",
  {"numbers_one_of": [["two", "2"]], "must_include": ["client", "deck", "landscape", "portrait", "English and Marathi"], "must_not_include": ["customer"], "min_negations": 1},
  note="facts: deck in landscape, NOT portrait; two languages, English and Marathi; house term 'client'",
  length="short")
# 222 house term not applied to quoted template text
R("dev_custom_style", {**CH, "rules": ["Use 'client' instead of 'customer'."],
                       "transcript": "zoe the template still says dear valued customer at the top can you change it to just hi and the first name"},
  "Zoe, the template still says \"Dear valued customer\" at the top. Can you change it to just \"Hi\" and the first name?",
  {"must_include": ["Zoe", "template", "valued customer", "at the top", "first name"], "must_not_include": ["valued client"], "ends_with_question": True},
  note="'dear valued customer' is text quoted from the template, a literal; the house term must not rewrite it; facts: change it to just 'Hi' plus first name",
  length="medium")
# 223 versus, long
R("dev_custom_style", {**CH, "locale": "en-in", "rules": ["Write 'versus' in full, never 'vs'."],
                       "transcript": "india vs australia on the twenty ninth tickets go live at noon on monday and they sold out in like twenty minutes last time so be on the site early um we want eight seats together ideally in the upper tier and if we can't get eight together we'll split into two groups of four rory's buying with his card and we'll pay him back"},
  "India versus Australia on the 29th. Tickets go live at noon on Monday, and they sold out in like 20 minutes last time, so be on the site early. We want eight seats together, ideally in the upper tier, and if we can't get eight together, we'll split into two groups of four. Rory's buying with his card, and we'll pay him back.",
  {"numbers": ["29", "20"], "numbers_one_of": [["eight", "8"], ["four", "4"]], "must_include": ["India versus Australia", "29th", "noon on Monday", "like 20 minutes", "on the site early", "seats together", "ideally in the upper tier", "if we can't get eight together", "two groups of four", "Rory", "pay him back"], "must_not_include": ["vs"], "min_negations": 1},
  note="facts: match on the 29th; tickets live noon Monday; sold out in like 20 minutes last time ('like' = about, kept); eight seats together, upper tier only 'ideally'; condition: if not eight together, split into two groups of four; Rory buys, group pays him back")
# 224 flat/lift terms
R("dev_custom_style", {**CH, "locale": "en-in", "rules": ["Use 'flat', not 'apartment'.", "Use 'lift', not 'elevator'."],
                       "transcript": "the elevator in the apartment block near gate two will be shut on wednesday for the annual safety check"},
  "The lift in the block of flats near Gate 2 will be shut on Wednesday for the annual safety check.",
  {"numbers": ["2"], "must_include": ["lift", "block of flats", "Gate 2", "Wednesday", "annual safety check"], "must_not_include": ["elevator", "apartment"]},
  note="facts: lift near Gate 2 shut on Wednesday for the annual safety check; house terms applied",
  length="medium")
# 225 growers, long
R("dev_custom_style", {**CH, "rules": ["Refer to members as 'growers'."],
                       "transcript": "all members who signed up for the tomato challenge need to submit a photo by the thirtieth uh the photo should show the whole plant and a ruler next to it for scale members who joined late can still submit but they won't be eligible for the prize the winner gets a voucher for the nursery and will be announced at the december meeting"},
  "All growers who signed up for the tomato challenge need to submit a photo by the 30th. The photo should show the whole plant and a ruler next to it for scale. Growers who joined late can still submit, but they won't be eligible for the prize. The winner gets a voucher for the nursery and will be announced at the December meeting.",
  {"numbers": ["30"], "must_include": ["growers", "tomato challenge", "photo by the 30th", "whole plant", "ruler", "for scale", "joined late can still submit", "won't be eligible for the prize", "voucher for the nursery", "December meeting"], "must_not_include": ["members"], "min_negations": 1},
  note="facts: only those signed up; photo by the 30th showing the whole plant with a ruler for scale; late joiners may submit but are NOT eligible for the prize; winner gets a nursery voucher, announced at the December meeting")
# 226 trek/km, condition
R("dev_custom_style", {**CH, "rules": ["Use 'trek', not 'hike'.", "Write distances in km."],
                       "transcript": "next weekend's hike is about fourteen kilometres and we'll do it only if the weather clears up"},
  "Next weekend's trek is about 14 km, and we'll do it only if the weather clears up.",
  {"numbers": ["14"], "must_include": ["Next weekend's trek", "about 14 km", "only if the weather clears up"], "must_not_include": ["hike"]},
  note="facts: about 14 km (hedge kept); condition 'only if the weather clears up' kept",
  length="short")
# 227 Oxford comma, negation
R("dev_custom_style", {**CH, "rules": ["Use the Oxford comma."],
                       "transcript": "the package includes the logo the business cards and the letterhead but not the website"},
  "The package includes the logo, the business cards, and the letterhead, but not the website.",
  {"must_include": ["logo", "business cards", "and the letterhead", "not the website"], "min_negations": 1},
  note="facts: three included items; website NOT included",
  length="short")
# 228 pet-care term does not apply to a child's babysitter
R("dev_custom_style", {**CH, "rules": ["In pet care, say 'sitter', not 'babysitter'."],
                       "transcript": "the babysitter for my daughter can't come on friday so i can't do the evening dog walk can you swap with me"},
  "The babysitter for my daughter can't come on Friday, so I can't do the evening dog walk. Can you swap with me?",
  {"must_include": ["babysitter for my daughter", "Friday", "evening dog walk", "swap"], "must_not_include": ["The sitter for my daughter"], "min_negations": 2, "ends_with_question": True},
  note="the babysitter looks after the speaker's daughter, not a pet, so the pet-care term does not apply; facts: babysitter can't come Friday; speaker can't do the evening dog walk; asks for a swap",
  length="medium")
# 229 coordinator name + time style
R("dev_custom_style", {**CH, "rules": ["Write times like '6:30 pm' (lowercase, no periods).", "Refer to the coordinator as 'Simran', never 'Simmi'."],
                       "transcript": "simmi said the bus leaves at six thirty pm sharp from the club gate"},
  "Simran said the bus leaves at 6:30 pm sharp from the club gate.",
  {"numbers": ["6:30"], "must_include": ["Simran", "6:30 pm sharp", "club gate"], "must_not_include": ["Simmi", "p.m."]},
  note="'Simmi' is the coordinator's nickname; the developer rule names the same person 'Simran', so no fact changes; bus 6:30 pm sharp from the club gate",
  length="short")
# 230 long, society, three house rules
R("dev_custom_style", {**CH, "locale": "en-in", "rules": ["House style: sentence case.", "Use 'members', not 'residents'.", "Refer to the app as 'NestNote'."],
                       "transcript": "hi everyone the committee has posted the revised maintenance breakdown on nest note um the monthly charge stays at three thousand two hundred but the sinking fund contribution is going up from five hundred to seven fifty from january residents who pay the full year in advance before december thirty first get a five percent discount please raise any questions in the app not in this group"},
  "Hi everyone, the committee has posted the revised maintenance breakdown on NestNote. The monthly charge stays at 3,200, but the sinking fund contribution is going up from 500 to 750 from January. Members who pay the full year in advance before December 31 get a 5% discount. Please raise any questions in the app, not in this group.",
  {"numbers": ["3,200", "500", "750", "31", "5"], "must_include": ["Hi everyone", "NestNote", "revised maintenance breakdown", "monthly charge stays", "sinking fund", "from January", "Members who pay the full year in advance", "December 31", "5% discount", "in the app, not in this group"], "must_not_include": ["residents", "nest note", "₹"], "min_negations": 1},
  note="facts: monthly charge unchanged at 3,200; sinking fund 500 -> 750 from January (both kept, an increase, not a correction); 5% discount only for members paying the full year in advance before December 31; questions in the app, NOT this group; no currency spoken; greeting dictated",
  length="long")

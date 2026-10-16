# W10 stage 2, chunk 1: TC-W10-101..140 (exec'd by W10_s2.py)

# ---------------------------------------------------------------- messages (23)
# 101 condolence, nothing invented
R("messages", {**P, "tone": "empathetic",
               "transcript": "inaya i'm so sorry to hear about your dad um i don't really know what to say just know i'm here if you need anything"},
  "Inaya, I'm so sorry to hear about your dad. I don't really know what to say. Just know I'm here if you need anything.",
  {"must_include": ["Inaya", "your dad", "I'm here if you need anything"], "min_negations": 1},
  note="facts: condolence about Inaya's dad; 'don't really know what to say' negation kept; the offer 'I'm here if you need anything' is dictated, conditional kept; no details about the death or funeral added",
  length="medium")
# 102 congratulations, friendly tone, no "!"
R("messages", {**CH, "tone": "friendly", "register": "casual",
               "transcript": "mehul heard you got the job at the design studio congrats man that's huge we should celebrate when the reunion happens"},
  "Mehul, heard you got the job at the design studio. Congrats, man, that's huge. We should celebrate when the reunion happens.",
  {"must_include": ["Mehul", "design studio", "Congrats", "when the reunion happens"], "must_not_include": ["!"]},
  note="facts: Mehul got the job at the design studio; suggestion to celebrate 'when the reunion happens' (no date added); friendly tone but no exclamation marks since none were dictated",
  length="medium")
# 103 invitation with time and place, long
R("messages", {**CH, "locale": "en-in", **F,
               "transcript": "hey everyone so we're doing a small get together at my place on saturday the eighth from seven thirty onwards dinner is on me just bring yourselves and uh let me know by thursday if you're coming it's the flat above the pharmacy third floor and the lift is under repair so you'll have to take the stairs sorry about that and if anyone's vegetarian tell me so i order separately"},
  "Hey everyone, we're doing a small get-together at my place on Saturday the 8th from 7:30 onwards. Dinner is on me, just bring yourselves. Let me know by Thursday if you're coming. It's the flat above the pharmacy, third floor, and the lift is under repair, so you'll have to take the stairs. Sorry about that. If anyone's vegetarian, tell me so I order separately.",
  {"numbers": ["8", "7:30"], "must_include": ["Hey everyone", "my place", "Saturday", "Dinner is on me", "Thursday", "if you're coming", "flat above the pharmacy", "third floor", "lift is under repair", "stairs", "Sorry about that", "vegetarian", "order separately"]},
  note="facts: get-together at speaker's place, Saturday the 8th from 7:30 onwards (no a.m./p.m. spoken, none added); dinner on the speaker; RSVP by Thursday; flat above the pharmacy, third floor; lift under repair, take the stairs (dictated apology); if vegetarian, tell speaker; greeting 'hey everyone' dictated")
# 104 polite decline, gardening club, instruction
R("messages", {**P,
               "instruction": "make it a polite no, keep it warm, and don't make up a different excuse",
               "transcript": "nora thanks for the invite to the plant swap but i can't make it this sunday i've already got plans with my in laws hopefully next time"},
  "Nora, thank you so much for inviting me to the plant swap. I'm afraid I can't make it this Sunday, as I already have plans with my in-laws. Hopefully next time.",
  {"must_include": ["Nora", "plant swap", "Sunday", "in-laws", "Hopefully next time"], "min_negations": 1},
  note="facts: declines the plant swap this Sunday; reason is plans with in-laws (the only excuse given, kept); 'hopefully next time' stays a hope, not a promise; warmer/politer wording ('thank you so much', 'I'm afraid') changes no fact",
  pos="before", cx=3, length="medium")
# 105 reminder to family, long
R("messages", {**CH, "locale": "en-in",
               "transcript": "mummy don't forget your bp tablet after dinner the white one not the yellow one uh the yellow one is the old prescription and the doctor said to stop it last week also the sugar test is on saturday morning so no breakfast before that just water is fine and i'll come by at eight to take you papa said he can't because he has the bank thing"},
  "Mummy, don't forget your BP tablet after dinner. The white one, not the yellow one. The yellow one is the old prescription, and the doctor said to stop it last week. Also, the sugar test is on Saturday morning, so no breakfast before that; just water is fine. I'll come by at 8 to take you. Papa said he can't because he has the bank thing.",
  {"numbers": ["8"], "must_include": ["Mummy", "BP tablet", "after dinner", "white one", "old prescription", "stop it last week", "sugar test", "Saturday morning", "no breakfast", "just water is fine", "come by at 8", "Papa", "bank thing"], "min_negations": 4},
  note="facts: BP tablet after dinner, the white one NOT the yellow one; yellow = old prescription, doctor said stop it last week; sugar test Saturday morning, no breakfast before, water fine; speaker's own commitment to come by at 8; Papa can't (bank thing)")
# 106 cricket fans group update, long
R("messages", {**CH, "locale": "en-in", **F,
               "transcript": "okay guys update on the match plan so we got six tickets for the sunday game in the east stand not the north stand like we thought um gates open at one thirty and the match starts at three so let's meet at the metro station at one fifteen saira has the tickets on her phone so don't go in without her and uh the stadium doesn't allow power banks so leave them at home if anyone backs out tell me by friday night so i can give the ticket to rory's cousin"},
  "Guys, update on the match plan: we got six tickets for the Sunday game in the east stand, not the north stand like we thought. Gates open at 1:30 and the match starts at 3, so let's meet at the metro station at 1:15. Saira has the tickets on her phone, so don't go in without her. The stadium doesn't allow power banks, so leave them at home. If anyone backs out, tell me by Friday night so I can give the ticket to Rory's cousin.",
  {"numbers": ["1:30", "3", "1:15"], "numbers_one_of": [["six", "6"]], "must_include": ["Sunday game", "east stand", "north stand", "metro station", "Saira", "power banks", "Friday night", "Rory's cousin"], "min_negations": 3},
  note="facts: six tickets, Sunday game, east stand NOT north stand; gates 1:30, match 3, meet metro station 1:15; Saira has tickets, don't go in without her; stadium doesn't allow power banks (unconditional, own sentence); condition: if anyone backs out, tell speaker by Friday night so the ticket goes to Rory's cousin; stand names kept lowercase (not proper nouns)",
  length="long")
# 107 neighbour notice, rupees
R("messages", {**CH, "locale": "en-in",
               "transcript": "dear neighbours the water purifier service guy is coming to the fourth floor on tuesday between eleven and two he charges four hundred fifty rupees per unit so if anyone else wants their purifier serviced just leave your name with me by monday evening"},
  "Dear neighbours, the water purifier service guy is coming to the fourth floor on Tuesday between 11 and 2. He charges ₹450 per unit, so if anyone else wants their purifier serviced, just leave your name with me by Monday evening.",
  {"numbers": ["11", "2", "450"], "must_include": ["Dear neighbours", "fourth floor", "Tuesday", "₹", "per unit", "Monday evening"]},
  note="facts: service visit fourth floor, Tuesday between 11 and 2; ₹450 per unit (rupees spoken); condition: if anyone else wants a service, leave name with speaker by Monday evening; greeting dictated",
  length="medium")
# 108 dictated apology
R("messages", {**P, "register": "casual",
               "transcript": "karim sorry i snapped at you in the group yesterday that wasn't fair i was stressed about the move and took it out on you"},
  "Karim, sorry I snapped at you in the group yesterday. That wasn't fair. I was stressed about the move and took it out on you.",
  {"must_include": ["Karim", "sorry", "snapped", "yesterday", "the move"], "min_negations": 1},
  note="facts: the apology is dictated (snapped in the group yesterday); 'wasn't fair' kept; reason: stressed about the move; nothing promised",
  length="medium")
# 109 "more casual" must visibly change wording
R("messages", {**CH,
               "instruction": "make this more casual, like I'm texting a friend",
               "transcript": "hello jasper i wanted to let you know that the tomato seedlings you gave me have finally started flowering i will bring some cherry tomatoes to the club meeting next month if they ripen in time"},
  "Hey Jasper, just letting you know the tomato seedlings you gave me have finally started flowering. I'll bring some cherry tomatoes to the club meeting next month if they ripen in time.",
  {"must_include": ["Jasper", "tomato seedlings", "flowering", "cherry tomatoes", "club meeting", "next month", "if they ripen in time"], "must_not_include": ["I wanted to let you know", "I will"]},
  note="facts: Jasper's seedlings flowering; speaker will bring cherry tomatoes to next month's club meeting ONLY if they ripen in time; dictated 'hello' adapted to casual 'Hey'; casual wording ('just letting you know', 'I'll') is the visible change",
  pos="before", cx=1, length="medium")
# 110 "ask callum" kept as dictated (to the group)
R("messages", {**CH,
               "transcript": "can someone ask callum whether the cabin booking includes breakfast or if we have to pay extra for it"},
  "Can someone ask Callum whether the cabin booking includes breakfast or if we have to pay extra for it?",
  {"must_include": ["Can someone ask Callum", "cabin booking", "breakfast", "pay extra"], "must_not_include": ["Callum,"], "ends_with_question": True},
  note="facts: speaker asks the group to ask Callum; Callum is NOT the addressee, so no vocative and no direct question to him; both alternatives (included OR pay extra) kept; not answered",
  length="medium")
# 111 Hinglish, keep words
R("messages", {**CH, "locale": "en-in", "register": "casual",
               "transcript": "arre ishita kal ka plan cancel mat karna yaar i've already booked the cab for nine a m so be ready by eight forty five"},
  "Arre Ishita, kal ka plan cancel mat karna yaar. I've already booked the cab for 9 a.m., so be ready by 8:45.",
  {"numbers": ["9", "8:45"], "must_include": ["Ishita", "kal ka plan cancel mat karna yaar", "cab"]},
  note="facts: Hinglish kept word for word ('cancel mat karna' = don't cancel, negation kept); cab booked for 9 a.m.; be ready by 8:45",
  length="short")
# 112 Hinglish + "English only" -> no translation; excited tone allows "!"
R("messages", {**CH, "locale": "en-in", "tone": "excited",
               "instruction": "English only please, and make it sound excited",
               "transcript": "guys reunion ka venue final ho gaya it's the rooftop place near the old campus gate saturday the fifteenth at eight sab log aa jao"},
  "Guys, reunion ka venue final ho gaya! It's the rooftop place near the old campus gate, Saturday the 15th at 8. Sab log aa jao!",
  {"numbers": ["15", "8"], "must_include": ["reunion ka venue final ho gaya", "rooftop place", "old campus gate", "Saturday", "Sab log aa jao"]},
  note="'English only' would be translation, which the model never does: Hindi words kept; excited tone applied through exclamation marks only; facts: reunion venue final, rooftop place near the old campus gate, Saturday the 15th at 8",
  pos="after", cx=2, length="medium")
# 113 freelance client, personal tone, long
R("messages", {**CH,
               "transcript": "hi zoe just a heads up the logo files will be ready by wednesday not tuesday because the printer changed the size specs um the price stays the same i'll send you the png and the svg versions plus a one page usage guide and if you want the business cards redone with the new size too that'd be extra but i can quote it separately just let me know by friday"},
  "Hi Zoe, just a heads-up: the logo files will be ready by Wednesday, not Tuesday, because the printer changed the size specs. The price stays the same. I'll send you the PNG and the SVG versions plus a one-page usage guide. If you want the business cards redone with the new size too, that'd be extra, but I can quote it separately. Just let me know by Friday.",
  {"must_include": ["Hi Zoe", "logo files", "Wednesday", "size specs", "price stays the same", "PNG", "SVG", "one-page usage guide", "If you want the business cards redone", "extra", "quote it separately", "Friday"], "min_negations": 1},
  note="facts: logo files ready by Wednesday, NOT Tuesday (printer changed size specs); price unchanged; speaker sends PNG + SVG + one-page usage guide; conditional: business cards redone = extra, quoted separately, tell by Friday (dictated offer); greeting dictated")
# 114 invitation, "warmer"
R("messages", {**P,
               "instruction": "a bit warmer please",
               "transcript": "we're having a small housewarming on the twenty first from six pm it's at the new flat in baner would be nice if you and rory could come"},
  "We're having a small housewarming on the 21st from 6 p.m. at the new flat in Baner, and it would mean a lot to us if you and Rory could come.",
  {"numbers": ["21", "6"], "must_include": ["housewarming", "21st", "6 p.m.", "new flat", "Baner", "Rory"], "must_not_include": ["would be nice"]},
  note="facts: small housewarming on the 21st from 6 p.m. at the new flat in Baner; invitation to the recipient and Rory; warmer wording 'it would mean a lot to us' replaces 'would be nice', no new fact",
  pos="after", cx=1, length="medium")
# 115 hiking group update with self-correction, long
R("messages", {**CH, "locale": "en-in",
               "transcript": "quick update for saturday's trek uh the bus leaves from the usual spot at five forty five sorry five thirty and we'll stop for breakfast at the dhaba near the toll naka the trek itself is around eleven kilometres with about seven hundred metres of climb so it's harder than last time um if your knees have been bothering you maybe skip this one zoe and jasper are leading and the return bus should get us back by seven"},
  "Quick update for Saturday's trek: the bus leaves from the usual spot at 5:30, and we'll stop for breakfast at the dhaba near the toll naka. The trek itself is around 11 kilometres with about 700 metres of climb, so it's harder than last time. If your knees have been bothering you, maybe skip this one. Zoe and Jasper are leading, and the return bus should get us back by 7.",
  {"numbers": ["5:30", "11", "700", "7"], "must_include": ["Saturday's trek", "usual spot", "dhaba", "toll naka", "around 11", "about 700", "maybe skip", "Zoe", "Jasper", "should get us back"], "must_not_include": ["5:45"]},
  note="facts: self-correction 5:45 -> 5:30 applied; breakfast stop at the dhaba near the toll naka; around 11 km, about 700 m climb (hedges kept); harder than last time; conditional hedged advice: if knees bothering, maybe skip; Zoe and Jasper leading; return 'should' get back by 7; waiver: checker splits 'five forty five sorry five thirty' and expects 45/30 separately although the correction to 5:30 is applied",
  waivers=["number_missing"], length="long")
# 116 neighbour, short-ish
R("messages", {**CH, "register": "casual",
               "transcript": "whoever's cat keeps sleeping on my car bonnet it's fine honestly but please keep it off during the day the bonnet gets really hot"},
  "Whoever's cat keeps sleeping on my car bonnet: it's fine, honestly, but please keep it off during the day. The bonnet gets really hot.",
  {"must_include": ["cat", "car bonnet", "honestly", "during the day", "really hot"]},
  note="facts: cat sleeping on the bonnet is fine, but keep it off during the day (restriction kept); bonnet gets really hot",
  length="medium")
# 117 congratulations, excited tone
R("messages", {**CH, "tone": "excited",
               "transcript": "rory you got picked for the district under nineteen squad that's massive"},
  "Rory, you got picked for the district under-19 squad! That's massive!",
  {"numbers": ["19"], "must_include": ["Rory", "district", "under-19 squad", "massive"]},
  note="facts: Rory picked for the district under-19 squad; exclamation marks licensed by Tone: excited; nothing added",
  length="short")
# 118 reminder to family, trip, long
R("messages", {**CH, "locale": "en-in", **F,
               "transcript": "papa remember to carry the original aadhaar cards for everyone the hotel in udaipur won't accept photocopies um and the train is from platform four i think but check the board when you get there we have two lower berths and two upper ones so you and mummy take the lower ones the food is included so don't buy anything at the station"},
  "Papa, remember to carry the original Aadhaar cards for everyone. The hotel in Udaipur won't accept photocopies. The train is from platform 4, I think, but check the board when you get there. We have two lower berths and two upper ones, so you and Mummy take the lower ones. The food is included, so don't buy anything at the station.",
  {"numbers": ["4"], "numbers_one_of": [["two", "2"]], "must_include": ["Papa", "original Aadhaar cards", "Udaipur", "photocopies", "platform 4, I think", "check the board", "lower berths", "upper ones", "Mummy", "food is included"], "min_negations": 2},
  note="facts: original Aadhaar cards for everyone; Udaipur hotel won't accept photocopies; platform 4 hedged 'I think', check the board; two lower and two upper berths, Papa and Mummy take the lower; food included, don't buy at the station")
# 119 freelance decline, no promise of later
R("messages", {**CH,
               "instruction": "polite no, keep it friendly, and don't promise anything for later",
               "transcript": "saira thanks for thinking of me for the menu redesign but i'm fully booked till the end of november so i'll have to pass on this one"},
  "Saira, thank you so much for thinking of me for the menu redesign. I'm fully booked until the end of November, though, so I'll have to pass on this one.",
  {"must_include": ["Saira", "menu redesign", "fully booked", "end of November", "pass on this one"], "must_not_include": ["next time", "in the future", "after November", "happy to"]},
  note="facts: declines the menu redesign; fully booked until the end of November; no promise or offer for later added; friendlier wording ('thank you so much', 'though') is the visible change",
  pos="after", cx=3, length="medium")
# 120 third-person dictation stays third-person
R("messages", {**CH, "register": "casual",
               "transcript": "just so you know aarav got home safe around eleven he's asleep now"},
  "Just so you know, Aarav got home safe around 11. He's asleep now.",
  {"numbers": ["11"], "must_include": ["Aarav got home safe", "around 11", "asleep"], "must_not_include": ["Aarav,"]},
  note="facts: Aarav (third person, NOT the addressee) got home safe around 11 (hedge kept); asleep now",
  length="short")
# 121 college reunion planning, alternatives, long
R("messages", {**CH, "locale": "en-in",
               "transcript": "okay so for the reunion we have two options for the date either the last saturday of december or the first saturday of january mehul can't do december because of his sister's thing so january might be easier but inaya is flying back on the second so she'd be jetlagged um for the place we were thinking either the old canteen area if the college allows it or the banquet hall on fc road which is about eight hundred per head can everyone vote in the poll by sunday"},
  "For the reunion, we have two options for the date: either the last Saturday of December or the first Saturday of January. Mehul can't do December because of his sister's thing, so January might be easier, but Inaya is flying back on the 2nd, so she'd be jet-lagged. For the place, we were thinking either the old canteen area, if the college allows it, or the banquet hall on FC Road, which is about 800 per head. Can everyone vote in the poll by Sunday?",
  {"numbers": ["2", "800"], "must_include": ["reunion", "last Saturday of December", "first Saturday of January", "Mehul", "might be easier", "Inaya", "old canteen area", "if the college allows it", "banquet hall", "about 800 per head", "poll", "Sunday"], "must_not_include": ["₹"], "min_negations": 1, "ends_with_question": True},
  note="facts: date alternatives both kept (last Sat of Dec OR first Sat of Jan); Mehul can't do December; January hedged 'might be easier'; Inaya flying back on the 2nd; venue alternatives both kept: old canteen area only if the college allows it, OR banquet hall on FC Road about 800 per head (no currency spoken, no ₹); vote by Sunday",
  length="long")
# 122 pet care, short
R("messages", {**CH, "register": "casual",
               "transcript": "can you top up pip's water bowl before you leave i forgot"},
  "Can you top up Pip's water bowl before you leave? I forgot.",
  {"must_include": ["Pip's water bowl", "before you leave", "I forgot"]},
  length="short")
# 123 gardening club update
R("messages", {**CH, **F,
               "transcript": "the compost bins are finally here we've got three of them one near the shed and two by the back fence please don't throw any cooked food or citrus peels in them only raw veg scraps and dry leaves"},
  "The compost bins are finally here. We've got three of them, one near the shed and two by the back fence. Please don't throw any cooked food or citrus peels in them, only raw veg scraps and dry leaves.",
  {"numbers_one_of": [["three", "3"]], "must_include": ["compost bins", "shed", "back fence", "cooked food", "citrus peels", "raw veg scraps", "dry leaves"], "min_negations": 1},
  note="facts: three bins: one near the shed, two by the back fence; NO cooked food or citrus peels; only raw veg scraps and dry leaves",
  length="medium")

# ---------------------------------------------------------------- style_rules (9)
# 124 long, no-exclamation rule
R("style_rules", {**CH, "rules": ["No exclamation marks."],
                  "transcript": "guys guys we won the inter society cricket final by four wickets uh rory took three catches and mehul hit the winning six in the last over um the trophy is going to be kept in the clubhouse for now and um we're having a small celebration on sunday evening on the terrace everyone's welcome families too bring your own snacks so yeah"},
  "Guys, we won the inter-society cricket final by four wickets. Rory took three catches, and Mehul hit the winning six in the last over. The trophy is going to be kept in the clubhouse for now, and we're having a small celebration on Sunday evening on the terrace. Everyone's welcome, families too. Bring your own snacks.",
  {"numbers_one_of": [["four", "4"], ["three", "3"]], "must_include": ["inter-society cricket final", "wickets", "Rory", "catches", "Mehul", "winning six", "last over", "trophy", "clubhouse for now", "Sunday evening", "terrace", "families too", "own snacks"], "must_not_include": ["!"]},
  note="facts: won by four wickets; Rory three catches; Mehul winning six in the last over; trophy in the clubhouse for now; celebration Sunday evening on the terrace, families welcome, bring own snacks; saved rule: no exclamation marks; 'six' is a cricket term, not a count")
# 125 saved lowercase rule vs this turn's "more professional"
R("style_rules", {**CH, "rules": ["Always write in lowercase."],
                  "instruction": "make it a bit more professional",
                  "transcript": "hi mr thomas sending over the revised quote it's eighteen thousand for the full site including the blog section and uh the first round of changes is free"},
  "Hi Mr. Thomas, I'm sending over the revised quote. It's 18,000 for the full site, including the blog section, and the first round of changes is free of charge.",
  {"numbers": ["18,000"], "must_include": ["Mr. Thomas", "revised quote", "full site", "blog section", "first round of changes"], "must_not_include": ["₹", "$"]},
  note="this turn's instruction (more professional) overrides the saved lowercase rule, so normal capitalisation; facts: revised quote 18,000 (no currency spoken, none added) for the full site incl. blog section; first round of changes free; greeting dictated",
  pos="after", cx=1, length="medium")
# 126
R("style_rules", {**CH, "locale": "en-gb", "rules": ["Use British spelling.", "Write numbers as digits."],
                  "transcript": "the gardening club's fertilizer order arrived we've got twelve bags of organic fertilizer and two sprayers and the color coded labels are on the shed door"},
  "The gardening club's fertiliser order arrived. We've got 12 bags of organic fertiliser and 2 sprayers, and the colour-coded labels are on the shed door.",
  {"numbers": ["12", "2"], "must_include": ["fertiliser", "colour-coded", "sprayers", "shed door"], "must_not_include": ["fertilizer", "color"]},
  note="facts: 12 bags organic fertiliser, 2 sprayers; labels on the shed door; saved rules British spelling and digits",
  length="medium")
# 127 saved word limit
R("style_rules", {**CH, "rules": ["Keep messages under 35 words."],
                  "transcript": "hey dev so um the chess club is doing a simul on friday at six thirty with the new coach and i think it's free for members but uh you might need to register on the club page first so yeah"},
  "Hey Dev, the chess club's simul with the new coach is on Friday at 6:30. I think it's free for members, but you might need to register on the club page first.",
  {"numbers": ["6:30"], "max_words": 35, "must_include": ["Dev", "simul", "new coach", "Friday", "I think it's free for members", "might need to register", "club page"]},
  note="facts: simul with the new coach Friday 6:30; hedge 'I think' free for members and 'might need to register' first both kept; saved rule under 35 words met without dropping any fact",
  length="medium")
# 128 saved sign-off rule, long
R("style_rules", {**CH, "rules": ["End messages to family with 'Love, Simran'."],
                  "transcript": "mom we reached jodhpur um the hotel is nice we're going to the fort tomorrow morning and then the stepwell in the afternoon uh the kids are already asleep uh it was a long drive about seven hours but no problems on the way um i'll send photos tomorrow and uh don't worry about the money i've got enough cash okay"},
  "Mom, we reached Jodhpur. The hotel is nice, and we're going to the fort tomorrow morning and then the stepwell in the afternoon. The kids are already asleep; it was a long drive, about 7 hours, but no problems on the way. I'll send photos tomorrow, and don't worry about the money, I've got enough cash.\n\nLove, Simran",
  {"numbers": ["7"], "must_include": ["Mom", "Jodhpur", "fort tomorrow morning", "stepwell", "afternoon", "kids are already asleep", "about 7 hours", "no problems", "send photos tomorrow", "don't worry about the money", "enough cash", "Love, Simran"], "min_negations": 2},
  note="sign-off comes from the saved rule (message to family), not invented; facts: reached Jodhpur; fort tomorrow morning then stepwell in the afternoon; kids asleep; drive about 7 hours, no problems; speaker's own commitment to send photos tomorrow; don't worry about money, enough cash")
# 129 saved word choice, playful, 'like' = about kept
R("style_rules", {**CH, "tone": "playful", "rules": ["Write 'okay', never 'OK'.", "No exclamation marks."],
                  "transcript": "ok so the parrot learned to say good morning but only at like four am"},
  "Okay, so the parrot learned to say good morning, but only at like 4 a.m.",
  {"numbers": ["4"], "must_include": ["Okay", "parrot", "good morning", "like 4 a.m."], "must_not_include": ["OK,", "!"]},
  note="facts: parrot says good morning only at like 4 a.m. ('like' = about, kept); saved rules: 'okay' spelling, no exclamation marks even with playful tone",
  length="short")
# 130 banned word without losing meaning
R("style_rules", {**CH, "locale": "en-in", "rules": ["Don't use the word 'just'."], **F,
                  "transcript": "just wanted to remind you the society maintenance is due on the fifth and just so you know the late fee is two hundred rupees"},
  "Wanted to remind you that the society maintenance is due on the 5th. Also, the late fee is ₹200.",
  {"numbers": ["5", "200"], "must_include": ["society maintenance", "due", "late fee", "₹"], "must_not_include": ["just"]},
  note="facts: maintenance due on the 5th; late fee ₹200 (rupees spoken); saved rule bans 'just', removed with no meaning lost",
  length="medium")
# 131 instruction asks for excitement; British spelling rule
R("style_rules", {**P, "rules": ["Use British spelling."],
                  "instruction": "make it sound more excited",
                  "transcript": "my favorite rose finally bloomed after two years it's the apricot one jasper gave me"},
  "Guess what, my favourite rose finally bloomed after two years! It's the apricot one Jasper gave me!",
  {"numbers_one_of": [["two", "2"]], "must_include": ["favourite rose", "bloomed", "two years", "apricot", "Jasper"], "must_not_include": ["favorite"]},
  note="facts: favourite rose bloomed after two years; the apricot one from Jasper; 'more excited' licenses the exclamation marks and 'Guess what' (no fact added); saved rule British spelling",
  pos="after", cx=1, length="short")
# 132 saved list rule with a real list cue
R("style_rules", {"format": "auto", "context": "chat", "rules": ["Use bullet points for lists of three or more items.", "Never use emoji."],
                  "transcript": "for the trip to rishikesh this weekend everyone needs to bring three things a rain jacket a torch and a copy of your id and uh we'll sort out the food there so don't pack snacks the bus leaves at ten pm on friday from the main gate"},
  "For the trip to Rishikesh this weekend, everyone needs to bring three things:\n- a rain jacket\n- a torch\n- a copy of your ID\n\nWe'll sort out the food there, so don't pack snacks. The bus leaves at 10 p.m. on Friday from the main gate.",
  {"numbers": ["10"], "numbers_one_of": [["three", "3"]], "must_include": ["Rishikesh", "rain jacket", "torch", "copy of your ID", "don't pack snacks", "10 p.m.", "Friday", "main gate"], "min_negations": 1, "format": None},
  note="facts: Rishikesh trip this weekend; three items (rain jacket, torch, ID copy) as bullets per saved rule + list cue; format assertion left unset because the target mixes a short bullet list with prose sentences; food sorted there, don't pack snacks; bus 10 p.m. Friday from the main gate",
  length="long")

# ---------------------------------------------------------------- dev_custom_style (8)
# 133
R("dev_custom_style", {**CH, "rules": ["Write 'WhatsApp' with a capital W and A.", "House style: no Oxford comma."],
                       "transcript": "i'll share the whatsapp link for the cricket group with mehul saira and jasper tonight"},
  "I'll share the WhatsApp link for the cricket group with Mehul, Saira and Jasper tonight.",
  {"must_include": ["WhatsApp", "cricket group", "Mehul, Saira and Jasper", "tonight"], "must_not_include": ["Saira, and"]},
  note="facts: speaker's own commitment to share the link tonight (dictated); three names kept; house casing and no Oxford comma",
  length="short")
# 134 long, plot term
R("dev_custom_style", {**CH, "rules": ["Use 'plot' instead of 'garden bed'."], **F,
                       "transcript": "so nora's garden bed near the gate needs weeding before the inspection on saturday and the two garden beds behind the shed haven't been watered all week um if the plot holders can't manage it this week tell jasper and he'll arrange volunteers uh and the the inspector is coming at ten and will check the labels too so yeah okay"},
  "Nora's plot near the gate needs weeding before the inspection on Saturday, and the two plots behind the shed haven't been watered all week. If the plot holders can't manage it this week, tell Jasper and he'll arrange volunteers. The inspector is coming at 10 and will check the labels too.",
  {"numbers": ["10"], "numbers_one_of": [["two", "2"]], "must_include": ["Nora's plot", "near the gate", "weeding", "inspection on Saturday", "two plots behind the shed", "watered all week", "If the plot holders can't manage it", "Jasper", "volunteers", "inspector", "labels"], "must_not_include": ["garden bed"], "min_negations": 2},
  note="facts: Nora's plot near the gate needs weeding before Saturday's inspection; two plots behind the shed not watered all week; condition: if plot holders can't manage it this week, tell Jasper, he arranges volunteers; inspector at 10, checks labels; house term 'plot'")
# 135 house term would change who is meant -> not applied there
R("dev_custom_style", {**CH, "rules": ["Use 'members', not 'fans'."],
                       "transcript": "the players got stuck in traffic so the toss is delayed by half an hour fans can still enter the stadium from four"},
  "The players got stuck in traffic, so the toss is delayed by half an hour. Members can still enter the stadium from 4.",
  {"numbers": ["4"], "must_include": ["players", "traffic", "toss", "half an hour", "Members", "from 4"], "must_not_include": ["fans", "members got stuck"]},
  note="facts: players (the cricketers) stuck in traffic; toss delayed by half an hour; entry still from 4; house term replaces 'fans' (the group's audience) but 'players' is a different group and stays",
  length="medium")
# 136 number style house rule
R("dev_custom_style", {**CH, "rules": ["Spell out numbers under ten.", "Use numerals for 10 and above."],
                       "transcript": "we need two more volunteers for the potting workshop and like fifteen extra chairs"},
  "We need two more volunteers for the potting workshop and about 15 extra chairs.",
  {"numbers": ["15"], "must_include": ["two more volunteers", "potting workshop", "about 15", "extra chairs"], "must_not_include": ["2 more"]},
  note="facts: two more volunteers; 'like fifteen' = about 15 (approximation kept as 'about'); house number style applied",
  length="short")
# 137 official casing, long
R("dev_custom_style", {**CH, "rules": ["Write product names in their official casing, e.g. 'iPhone', 'GitHub', 'PayPal'."],
                       "transcript": "zoe the invoice link is on paypal and the source files are on github in the client folder um the invoice is for the second milestone so it's the forty percent part not the full amount and uh the iphone mockups are in a separate folder because they were too big for github let me know if any link doesn't open"},
  "Zoe, the invoice link is on PayPal and the source files are on GitHub in the client folder. The invoice is for the second milestone, so it's the 40% part, not the full amount. The iPhone mockups are in a separate folder because they were too big for GitHub. Let me know if any link doesn't open.",
  {"numbers": ["40"], "must_include": ["Zoe", "PayPal", "GitHub", "client folder", "second milestone", "40%", "not the full amount", "iPhone mockups", "separate folder", "too big", "if any link doesn't open"], "min_negations": 2},
  note="facts: invoice on PayPal; source files on GitHub, client folder; invoice is for the second milestone = 40% part, NOT the full amount; iPhone mockups separate (too big for GitHub); dictated 'let me know if any link doesn't open'")
# 138 banned word, price sense only
R("dev_custom_style", {**CH, "locale": "en-in", "rules": ["Avoid the word 'cheap' for prices; say 'lower-priced'."], **F,
                       "transcript": "the cheap tickets in the lower stand are sold out but the pavilion ones are still available at two thousand each"},
  "The lower-priced tickets in the lower stand are sold out, but the pavilion ones are still available at 2,000 each.",
  {"numbers": ["2,000"], "must_include": ["lower-priced tickets", "lower stand", "sold out", "pavilion", "still available", "each"], "must_not_include": ["cheap", "₹"]},
  note="facts: lower-priced tickets in the lower stand sold out; pavilion tickets still available at 2,000 each (no currency spoken, no ₹); house word applied",
  length="medium")
# 139 date house format
R("dev_custom_style", {**CH, "rules": ["Format dates as day then month, e.g. '14 October'."],
                       "transcript": "the reunion is on november twenty second at the old campus and registrations close on the tenth of november"},
  "The reunion is on 22 November at the old campus, and registrations close on 10 November.",
  {"numbers": ["22", "10"], "must_include": ["reunion", "22 November", "old campus", "registrations close", "10 November"]},
  note="facts: reunion 22 November at the old campus; registrations close 10 November; date order is house formatting only",
  length="medium")
# 140 pet terms; 'owner' of a pet -> pet parent; long
R("dev_custom_style", {"format": "message", "context": "work",
                       "rules": ["Use 'pet parent' instead of 'owner' when talking about pets.", "Use 'boarding' instead of 'kennel stay'."],
                       "transcript": "hi jasper so update on the weekend kennel stays um we have four dogs coming in friday evening and two cats on saturday morning the owner of the beagle said he's on a new diet so only the food she's sending nothing else and the cat owners want them kept in separate rooms because they don't get along if any of them doesn't eat by sunday call me not the owners"},
  "Hi Jasper, update on the weekend boarding: we have four dogs coming in Friday evening and two cats on Saturday morning. The beagle's pet parent said he's on a new diet, so only the food she's sending, nothing else. The cats' pet parents want them kept in separate rooms because they don't get along. If any of them doesn't eat by Sunday, call me, not the pet parents.",
  {"numbers_one_of": [["four", "4"], ["two", "2"]], "must_include": ["Hi Jasper", "weekend boarding", "Friday evening", "Saturday morning", "beagle", "new diet", "separate rooms", "Sunday", "call me"], "must_not_include": ["owner", "kennel stay"], "min_negations": 4},
  note="facts: four dogs Friday evening, two cats Saturday morning; beagle on new diet, only the food the pet parent sends, nothing else; cats in separate rooms, they don't get along; condition: if any doesn't eat by Sunday, call the speaker, NOT the pet parents; greeting dictated; house terms applied (pet owners -> pet parents)",
  length="long")

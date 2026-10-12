# W12 stage 2, part 3: TC-W12-181..210 (exec'd by W12.py; uses R2, SF, NM, NL)

# 181 long launch announcement, plain prose paragraphs (en-in)
R2(NM, {"task": "rewrite", "format": "prose", "locale": "en-in", "header_style": "full",
        "transcript": "big announcement for our users tallyroom is now available on android um it has everything the ios version has shared bills reminders and the monthly summary. if you were on the beta your data moves over automatically you don't need to do anything. the price is still ninety nine rupees a month per household and the first month is free for everyone who signs up before diwali"},
   "Big announcement for our users: Tallyroom is now available on Android. It has everything the iOS version has — shared bills, reminders and the monthly summary.\n\nIf you were on the beta, your data moves over automatically. You don't need to do anything.\n\nThe price is still ₹99 a month per household, and the first month is free for everyone who signs up before Diwali.",
   {"format": "prose", "numbers": ["99"], "min_negations": 1, "must_include": ["Tallyroom", "Android", "shared bills", "reminders", "monthly summary", "If you were on the beta", "don't need to do anything", "still ₹99 a month per household", "before Diwali"], "must_not_include": ["- ", "**", "#"]},
   cx=0, note="facts: now on Android with iOS parity (shared bills, reminders, monthly summary); IF on beta, data moves automatically, no action needed; price still ₹99 a month per household (rupees spoken); first month free only for sign-ups before Diwali (condition); plain paragraphs, features stay inline")

# 182 markdown allowed, message, nothing asked -> no emphasis
R2(NM, {"task": "rewrite", "format": "message", "markup": "markdown",
        "transcript": "ilse the new labels are in the drawer under the till"},
   "Ilse, the new labels are in the drawer under the till.",
   {"format": "message", "must_include": ["Ilse", "new labels", "drawer under the till"], "must_not_include": ["**", "#"]},
   cx=0, note="facts: labels are in the drawer under the till; vocative spoken; markdown allowed but nothing to emphasise -> plain sentence")

# 183 post with ordinal cues stays short paragraphs, no list syntax
R2(NM, {"task": "rewrite", "format": "post",
        "transcript": "three things i learned from running the station's first fundraiser first people give more when you say exactly what the money buys second thank donors on air by name if they agree and third never schedule it against a cricket final"},
   "Three things I learned from running the station's first fundraiser.\n\nFirst, people give more when you say exactly what the money buys.\n\nSecond, thank donors on air by name if they agree.\n\nThird, never schedule it against a cricket final.",
   {"format": "post", "min_negations": 1, "must_include": ["Three things I learned", "station's first fundraiser", "say exactly what the money buys", "by name if they agree", "never schedule it against a cricket final"], "must_not_include": ["- ", "1. ", "#", "**"]},
   cx=0, note="facts: three lessons; condition 'if they agree' kept on naming donors; negation 'never'; Format: post -> short paragraphs with the speaker's ordinals, no list syntax or hashtags")

# 184 markdown, only a title heading (instructed)
R2(NM, {"task": "rewrite", "markup": "markdown",
        "instruction": "add a heading at the top, nothing else",
        "transcript": "devlog fifteen the fishing minigame is in you cast with the left stick and reel with the trigger there are twelve fish so far and two of them only show up at night"},
   "# Devlog 15\n\nThe fishing minigame is in. You cast with the left stick and reel with the trigger. There are 12 fish so far, and two of them only show up at night.",
   {"numbers": ["15", "12"], "must_include": ["# Devlog 15", "fishing minigame", "left stick", "trigger", "12 fish so far", "only show up at night"], "must_not_include": ["## ", "**", "- "]},
   pos="after", cx=1, note="facts: devlog 15; fishing minigame in; cast left stick, reel trigger; 12 fish 'so far'; two only at night; one heading (from the dictated title) and nothing else, as instructed")

# 185 long family history, markdown allowed but not asked -> plain paragraphs
R2(NM, {"task": "rewrite", "format": "prose", "markup": "markdown",
        "transcript": "okay so writing up what we know about the house in bharuch um it was built by great grandfather around nineteen twenty and it had a courtyard with a well that's still there today. the family sold it in nineteen seventy eight after grandpa moved to bombay but nobody remembers who bought it. last month bhavesh went past and the current owner let him take photos of the front door which still has the original carvings"},
   "Writing up what we know about the house in Bharuch: it was built by Great-grandfather around 1920, and it had a courtyard with a well that's still there today.\n\nThe family sold it in 1978 after Grandpa moved to Bombay, but nobody remembers who bought it.\n\nLast month, Bhavesh went past, and the current owner let him take photos of the front door, which still has the original carvings.",
   {"format": "prose", "numbers": ["1920", "1978"], "min_negations": 1, "must_include": ["house in Bharuch", "around 1920", "courtyard with a well", "still there today", "1978", "Bombay", "nobody remembers who bought it", "Bhavesh", "original carvings"], "must_not_include": ["#", "**"]},
   cx=0, note="facts: built by Great-grandfather around 1920 (hedge kept); courtyard well still there; sold in 1978 after Grandpa moved to Bombay; nobody remembers the buyer (negation); last month Bhavesh photographed the door with original carvings; markdown allowed but not asked -> plain paragraphs")

# 186 short show note, negation
R2(NM, {"task": "rewrite", "format": "note",
        "transcript": "note for tomorrow's show no phone ins the line's broken"},
   "Note for tomorrow's show: no phone-ins; the line's broken.",
   {"format": "note", "min_negations": 1, "must_include": ["tomorrow's show", "no phone-ins", "line's broken"]},
   cx=0, note="facts: tomorrow's show; no phone-ins (negation) because the line is broken; terse line")

# 187 explicit bullets, lead line, exception kept outside the list
R2(NM, {"task": "rewrite", "format": "bullets",
        "transcript": "for the gift shop we need to reorder postcards of the clock tower the tote bags in navy and the kids' activity books but not the fridge magnets we've still got loads"},
   "For the gift shop, we need to reorder these, but not the fridge magnets, since we've still got loads:\n- Postcards of the clock tower\n- The tote bags in navy\n- The kids' activity books",
   {"format": "bullets", "min_negations": 1, "must_include": ["For the gift shop, we need to reorder", "but not the fridge magnets", "Postcards of the clock tower", "tote bags in navy", "kids' activity books", "still got loads"]},
   cx=0, note="facts: reorder clock-tower postcards, navy tote bags, kids' activity books; NOT fridge magnets (still got loads) moved into the lead line so it can't read as an item to reorder (a trailing non-bullet line would break the bullets form); plain '- ' bullets")

# 188 explicit prose with ordinal cues -> one sentence
R2(NM, {"task": "rewrite", "format": "prose",
        "transcript": "things that went well today first i finished the chapter second i didn't check my phone during the morning and third i actually cooked"},
   "Things that went well today: first, I finished the chapter; second, I didn't check my phone during the morning; and third, I actually cooked.",
   {"format": "prose", "min_negations": 1, "must_include": ["Things that went well today", "finished the chapter", "didn't check my phone during the morning", "actually cooked"], "must_not_include": ["- ", "1. ", "\n"]},
   cx=0, note="facts: finished the chapter; didn't check phone in the morning (negation); actually cooked; explicit Format: prose beats the ordinal cues -> one sentence, no numbering")

# 189 volunteer recruitment post (en-gb)
R2(NM, {"task": "rewrite", "format": "post", "locale": "en-gb",
        "transcript": "we're looking for two new volunteers to help on thursday afternoons no experience needed just a friendly face and about three hours a week if you're interested pop into the front desk"},
   "We're looking for two new volunteers to help on Thursday afternoons.\n\nNo experience needed, just a friendly face and about three hours a week.\n\nIf you're interested, pop into the front desk.",
   {"format": "post", "min_negations": 1, "must_include": ["two new volunteers", "Thursday afternoons", "No experience needed", "about three hours a week", "front desk"], "must_not_include": ["#", "!"]},
   cx=0, note="facts: two volunteers, Thursday afternoons; no experience needed (negation); about three hours a week ('about' kept); if interested, pop into front desk; no hashtags/emoji")

# 190 markdown heading per person (instructed), lead line kept
R2(NM, {"task": "rewrite", "markup": "markdown", "header_style": "full",
        "instruction": "use a markdown heading for each person's update",
        "transcript": "updates from the team yohan finished rewiring studio two and both mics are working now clem is recording the station idents this week and needs one more voice ilse has sorted the music archive up to nineteen ninety and is starting on the nineties next"},
   "Updates from the team:\n\n## Yohan\n\nFinished rewiring Studio 2, and both mics are working now.\n\n## Clem\n\nRecording the station idents this week; needs one more voice.\n\n## Ilse\n\nHas sorted the music archive up to 1990 and is starting on the nineties next.",
   {"numbers": ["2", "1990"], "must_include": ["## Yohan", "## Clem", "## Ilse", "Studio 2", "both mics are working", "idents this week", "one more voice", "up to 1990", "nineties next"]},
   pos="after", cx=1, note="facts: Yohan finished rewiring Studio 2, both mics work; Clem recording idents this week, needs one more voice; Ilse sorted archive up to 1990, nineties next; headings because markdown + instruction; lead line kept")

# 191 markdown note, bold the deadline only (instructed)
R2(NM, {"task": "rewrite", "format": "note", "markup": "markdown",
        "instruction": "bold the deadline only",
        "transcript": "abstract notes for lisbon ux day three hundred word limit submit through the portal by monday nine am lisbon time and mention the low bandwidth case study"},
   "Abstract notes for Lisbon UX Day\n300-word limit.\nSubmit through the portal by **Monday at 9 a.m. Lisbon time**.\nMention the low-bandwidth case study.",
   {"format": "note", "numbers": ["300", "9"], "must_include": ["Lisbon UX Day", "300-word limit", "**Monday at 9 a.m. Lisbon time**", "portal", "low-bandwidth case study"], "must_not_include": ["#"]},
   pos="after", cx=2, note="facts: 300-word limit; submit via portal by Monday 9 a.m. Lisbon time (zone kept); mention low-bandwidth case study; bold only the deadline as instructed; terse lines")

# 192 short post
R2(NM, {"task": "rewrite", "format": "post",
        "transcript": "back on air tonight at ten after the summer break"},
   "Back on air tonight at 10 after the summer break.",
   {"format": "post", "numbers": ["10"], "must_include": ["Back on air tonight at 10", "summer break"], "must_not_include": ["#", "!"]},
   cx=0, note="facts: back on air tonight at 10 after the summer break; no hashtags, emoji or exclamation added")

# 193 auto + list cue -> plain bullets with lead line
R2(NM, {"task": "rewrite", "format": "auto",
        "transcript": "packing list for the archive trip a few things the scanner the spare batteries the white gloves and the folder of family photos"},
   "Packing list for the archive trip:\n- The scanner\n- The spare batteries\n- The white gloves\n- The folder of family photos",
   {"format": "bullets", "must_include": ["Packing list for the archive trip:", "scanner", "spare batteries", "white gloves", "folder of family photos"], "must_not_include": ["* ", "**"]},
   cx=0, note="facts: four items (scanner, spare batteries, white gloves, family photo folder); auto + list cue ('packing list', 'a few things') -> '- ' bullets under plain; lead line kept")

# 194 long product update notes, format note (en-gb)
R2(NM, {"task": "rewrite", "format": "note", "locale": "en-gb", "header_style": "full",
        "transcript": "update notes for the december release um the big one is shared budgets you can now invite up to five people to one budget. we also changed the colour of overspent categories from orange to red because people kept missing it. and we've dropped support for ios fifteen so anyone on older phones stays on the current version which will keep working but won't get new features"},
   "December release update notes\nShared budgets: you can now invite up to five people to one budget.\nOverspent categories changed colour from orange to red because people kept missing it.\nDropped support for iOS 15; anyone on older phones stays on the current version, which will keep working but won't get new features.",
   {"format": "note", "numbers": ["15"], "min_negations": 1, "must_include": ["December release", "Shared budgets", "up to five people", "colour", "orange to red", "kept missing it", "iOS 15", "will keep working but won't get new features"], "must_not_include": ["color", "- "]},
   cx=0, note="facts: shared budgets, up to five people per budget; overspent colour orange -> red because people missed it; iOS 15 dropped; older phones stay on current version, which keeps working but won't get new features (negation); en-gb 'colour' consistent; terse lines")

# 195 cleanup under markdown, no emphasis added
R2(NM, {"task": "cleanup", "markup": "markdown",
        "transcript": "honestly the best part of the day was the kids at the museum asking if the mummy was real i said yes and one of them refused to go back in the room"},
   "Honestly, the best part of the day was the kids at the museum asking if the mummy was real. I said yes, and one of them refused to go back in the room.",
   {"format": "prose", "must_include": ["Honestly", "if the mummy was real", "I said yes", "refused to go back in the room"], "must_not_include": ["**", "#", "\n"]},
   cx=0, note="facts: kids asked if the mummy was real; speaker said yes; one child refused to go back in (negation-like 'refused'); cleanup keeps words; markdown allowed but no emphasis added")

# 196 markdown note, title as heading (instructed)
R2(NM, {"task": "rewrite", "format": "note", "markup": "markdown",
        "instruction": "make the title a heading",
        "transcript": "packing for edinburgh charger clicker printed notes"},
   "# Packing for Edinburgh\n\nCharger\nClicker\nPrinted notes",
   {"format": "note", "must_include": ["# Packing for Edinburgh", "Charger", "Clicker", "Printed notes"], "must_not_include": ["**", "- "]},
   pos="after", cx=1, note="facts: three items: charger, clicker, printed notes; only the title becomes a heading as instructed; items stay terse lines, no bullets added")

# 197 fundraiser thank-you post, exact amount (en-in)
R2(NM, {"task": "rewrite", "format": "post", "locale": "en-in",
        "transcript": "um we did it the ujala reading circles winter appeal closed at nine lakh twenty thousand rupees which is more than we've ever raised. that money keeps all five centres open through next year and pays for two new teachers. thank you to every donor big or small and to rukmini and bhavesh who made more phone calls this month than in their whole lives"},
   "We did it. The Ujala Reading Circles winter appeal closed at ₹9,20,000, which is more than we've ever raised.\n\nThat money keeps all five centres open through next year and pays for two new teachers.\n\nThank you to every donor, big or small, and to Rukmini and Bhavesh, who made more phone calls this month than in their whole lives.",
   {"format": "post", "numbers": ["9,20,000"], "must_include": ["Ujala Reading Circles", "winter appeal", "₹9,20,000", "more than we've ever raised", "all five centres", "next year", "two new teachers", "Rukmini", "Bhavesh"], "must_not_include": ["#", "center", "10,00,000"]},
   cx=0, note="facts: appeal closed at ₹9,20,000 (nine lakh twenty thousand, exact, rupees spoken); most ever raised; keeps all five centres open through next year + two new teachers; thanks every donor, Rukmini and Bhavesh; en-in 'centres'; no hashtags/emoji",
   waivers=None)

# 198 newsletter intro, two paragraphs, nothing added (en-gb)
R2(NL, {"task": "rewrite", "locale": "en-gb",
        "instruction": "turn this into a newsletter intro, two paragraphs, and don't add anything",
        "transcript": "hello listeners so it's been a busy autumn at the station we moved the studio into the old fire station in september and the new soundproofing has made a huge difference to the late night shows. we also started training six teenagers from the college as presenters and their first show goes out on the twentieth of november at seven pm"},
   "Hello, listeners. It's been a busy autumn at the station. We moved the studio into the old fire station in September, and the new soundproofing has made a huge difference to the late-night shows.\n\nWe also started training six teenagers from the college as presenters, and their first show goes out on 20 November at 7 p.m.",
   {"numbers": ["20", "7"], "must_include": ["Hello, listeners", "busy autumn", "old fire station", "September", "soundproofing", "late-night shows", "six teenagers", "college", "20 November at 7 p.m.", "\n\n"], "must_not_include": ["excited", "proud", "programme"]},
   pos="after", cx=2, note="facts: studio moved into old fire station in September; soundproofing helped late-night shows; six teenagers from the college training as presenters; first show 20 November at 7 p.m.; dictated greeting kept; nothing added; two paragraphs; en-gb date order")

# 199 shorter, essentials, names and time kept
R2(NL, {"task": "rewrite", "length": "shorter",
        "instruction": "cut it to the essentials but keep every name and the time",
        "transcript": "so on the day itself um i need to be at the venue by eight fifteen for the sound check freya is bringing the clicker and the backup laptop and pallavi will sit in the front row and give me the five minute signal and after the talk we're all going to lunch together at the thai place"},
   "On the day: be at the venue by 8:15 for the sound check. Freya brings the clicker and backup laptop. Pallavi sits in the front row and gives me the five-minute signal. After the talk, we're all going to lunch at the Thai place.",
   {"numbers": ["8:15"], "must_include": ["8:15", "sound check", "Freya", "clicker", "backup laptop", "Pallavi", "front row", "five-minute signal", "Thai place"], "must_not_include": ["\n"]},
   pos="after", cx=2, note="facts: at venue by 8:15 for sound check; Freya brings clicker + backup laptop; Pallavi in front row gives five-minute signal; lunch together at the Thai place after; visibly compressed, every name and the time kept")

# 200 anniversary speech, three short paragraphs, no invented history
R2(NL, {"task": "rewrite",
        "instruction": "make it a short speech I can give at the museum's tenth anniversary, three short paragraphs, and don't invent any history",
        "transcript": "um ten years ago this building was empty and the roof leaked today we have over two hundred objects on display and forty volunteers none of that happened without the people in this room so thank you and here's to the next ten"},
   "Ten years ago, this building was empty, and the roof leaked.\n\nToday we have over 200 objects on display and 40 volunteers. None of that happened without the people in this room.\n\nSo thank you, and here's to the next ten.",
   {"numbers": ["200", "40"], "min_negations": 1, "must_include": ["Ten years ago", "empty", "roof leaked", "over 200 objects", "40 volunteers", "None of that happened without the people in this room", "here's to the next ten"], "must_not_include": ["founded", "I remember"]},
   pos="after", cx=3, note="facts: ten years ago building empty, roof leaked; today over 200 objects ('over' kept) and 40 volunteers; none of it without the people in the room (negation); thanks + toast to the next ten; no invented history; three paragraphs")

# 201 longer journal, no feelings or details added (en-in)
R2(NL, {"task": "rewrite", "length": "longer", "locale": "en-in",
        "instruction": "make it a fuller journal entry but don't add feelings or details",
        "transcript": "visited nani today she didn't recognise me at first then she called me by my father's name"},
   "I went to visit Nani today. At first, she didn't recognise me. Then she called me by my father's name.",
   {"min_negations": 1, "must_include": ["Nani", "today", "didn't recognise me", "At first", "my father's name"], "must_not_include": ["sad", "heart", "hurt", "\n"]},
   pos="after", cx=2, note="facts: visited Nani today; she didn't recognise the speaker at first (negation, 'at first' kept); then called speaker by father's name; longer = fuller sentences only, no emotions or new details; en-in 'recognise'")

# 202 casual blog intro from devlog dictation, one paragraph (en-gb)
R2(NL, {"task": "rewrite", "register": "casual", "locale": "en-gb",
        "instruction": "write this as the intro paragraph of a blog post about the project, one paragraph",
        "transcript": "so i'm clem and for the last eighteen months i've been making a tiny farming game called mossgrove in my spare time evenings weekends the odd lunch break it's not finished it's not even close but i've decided to start writing about it because keeping it secret wasn't helping"},
   "I'm Clem, and for the last 18 months, I've been making a tiny farming game called Mossgrove in my spare time: evenings, weekends, the odd lunch break. It's not finished, not even close, but I've decided to start writing about it because keeping it secret wasn't helping.",
   {"numbers": ["18"], "min_negations": 3, "must_include": ["Clem", "18 months", "Mossgrove", "spare time", "the odd lunch break", "not finished, not even close", "keeping it secret wasn't helping"], "must_not_include": ["\n", "!"]},
   pos="after", cx=2, note="facts: Clem; 18 months; tiny farming game Mossgrove in spare time (evenings, weekends, odd lunch break); not finished, not even close; starting to write because secrecy wasn't helping (three negations); one paragraph, no hype")

# 203 formal website notice, dates kept, one paragraph (en-gb)
R2(NL, {"task": "rewrite", "locale": "en-gb",
        "instruction": "make this sound more formal for the website, keep the date and time, one paragraph",
        "transcript": "hey so the station's annual general meeting is happening on the eighth of december at the town hall it kicks off at seven and if you're a member you can vote on the new committee"},
   "The station's annual general meeting will take place on 8 December at the town hall, beginning at 7. Members may vote on the new committee.",
   {"numbers": ["8", "7"], "must_include": ["annual general meeting", "8 December", "town hall", "beginning at 7", "Members may vote on the new committee"], "must_not_include": ["Hey", "7 p.m.", "\n"]},
   pos="after", cx=3, note="facts: AGM 8 December at the town hall, starts at 7 (no a.m./p.m. added since not spoken); members can vote on the new committee (membership condition kept as 'Members'); casual 'hey' dropped for formal website text")

# 204 LinkedIn post, exact numbers, no impact claims (en-in)
R2(NL, {"task": "rewrite", "locale": "en-in",
        "instruction": "linkedin post, keep the numbers exact, no hashtags, and don't make claims about impact I didn't make",
        "transcript": "this weekend thirty two volunteers from our office spent saturday painting the walls at a children's shelter in vapi we finished eight rooms and ran out of yellow paint halfway through the last one"},
   "This weekend, 32 volunteers from our office spent Saturday painting the walls at a children's shelter in Vapi.\n\nWe finished eight rooms and ran out of yellow paint halfway through the last one.",
   {"format": "post", "numbers": ["32"], "must_include": ["32 volunteers", "Saturday", "children's shelter in Vapi", "eight rooms", "ran out of yellow paint halfway through the last one"], "must_not_include": ["#", "impact", "difference", "brighter"]},
   pos="after", cx=3, note="facts: 32 volunteers; Saturday this weekend; painting walls at a children's shelter in Vapi; eight rooms finished; ran out of yellow paint halfway through the last one; no hashtags, no impact claims")

# 205 changelog, paragraphs, wording kept
R2(NL, {"task": "rewrite", "wording": "keep",
        "instruction": "split this into paragraphs, it's for the changelog page",
        "transcript": "this release is mostly about speed the app now opens in under two seconds on most phones and syncing is about three times faster. there's one change you might notice the budget screen now starts on the current week instead of the current month you can switch it back in settings. and we fixed the bug where notifications showed up twice"},
   "This release is mostly about speed. The app now opens in under 2 seconds on most phones, and syncing is about three times faster.\n\nThere's one change you might notice: the budget screen now starts on the current week instead of the current month. You can switch it back in Settings.\n\nAnd we fixed the bug where notifications showed up twice.",
   {"format": "prose", "numbers": ["2"], "must_include": ["mostly about speed", "under 2 seconds on most phones", "about three times faster", "you might notice", "current week instead of the current month", "switch it back in Settings", "showed up twice", "\n\n"]},
   pos="after", cx=2, note="facts: opens in under 2 seconds on 'most' phones; sync 'about' three times faster; budget screen starts on current week instead of month, switchable in Settings; fixed double notifications; wording keep -> only punctuation and paragraph breaks")

# 206 long talk prep -> paragraphs (en-in)
R2(SF, {"task": "rewrite", "format": "auto", "locale": "en-in",
        "transcript": "so for the jaipur product meetup talk um the organisers want the deck by the twelfth and they've asked for no vendor pitches so i'll take out the slide about our pricing. the talk is fifteen minutes and then a fireside chat with pallavi for another fifteen. i'm also not sure yet whether to show the live dashboard it depends on the venue wifi so i'll ask them on monday"},
   "For the Jaipur product meetup talk, the organisers want the deck by the 12th, and they've asked for no vendor pitches, so I'll take out the slide about our pricing.\n\nThe talk is 15 minutes, and then there's a fireside chat with Pallavi for another 15.\n\nI'm also not sure yet whether to show the live dashboard. It depends on the venue Wi-Fi, so I'll ask them on Monday.",
   {"format": "prose", "numbers": ["12", "15"], "min_negations": 2, "must_include": ["Jaipur product meetup", "organisers", "by the 12th", "no vendor pitches", "slide about our pricing", "fireside chat with Pallavi", "not sure yet", "depends on the venue Wi-Fi", "Monday"], "must_not_include": ["organizers"]},
   cx=0, note="facts: deck due the 12th; no vendor pitches, so pricing slide removed; talk 15 minutes + 15-minute fireside chat with Pallavi; undecided on live dashboard, depends on venue Wi-Fi; will ask on Monday; en-in 'organisers'; three topics -> paragraphs")

# 207 short journal cleanup, hedge kept
R2(SF, {"task": "cleanup",
        "transcript": "didn't write anything today too tired maybe tomorrow"},
   "Didn't write anything today. Too tired. Maybe tomorrow.",
   {"format": "prose", "min_negations": 1, "must_include": ["Didn't write anything today", "Too tired", "Maybe tomorrow"], "must_not_include": ["\n"]},
   cx=0, note="facts: nothing written today (negation); too tired; 'maybe' tomorrow (hedge, not a commitment); cleanup keeps words")

# 208 two items stay in one sentence
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "for the open day we need someone on the door and someone running the kids' trail"},
   "For the open day, we need someone on the door and someone running the kids' trail.",
   {"must_include": ["open day", "someone on the door", "kids' trail"], "must_not_include": ["- ", "\n"]},
   cx=0, note="facts: two roles only (door, kids' trail) -> one sentence, no bullets; framing 'for the open day' kept")

# 209 family-history message with a correction of belief (both years kept)
R2(SF, {"task": "rewrite", "format": "message",
        "transcript": "yohan i found great grandpa's ship record he arrived in durban on the third of may nineteen oh four not nineteen oh six like we thought"},
   "Yohan, I found Great-grandpa's ship record. He arrived in Durban on May 3, 1904, not 1906 like we thought.",
   {"format": "message", "numbers": ["3", "1904", "1906"], "min_negations": 1, "must_include": ["Yohan", "ship record", "Durban", "May 3, 1904", "not 1906 like we thought"]},
   cx=0, waivers=["number_missing", "number_invented"], note="waiver: checker cannot read 'nineteen oh four'/'nineteen oh six' as 1904/1906 (splits into 19 and 4/6); both years are spoken. facts: arrived Durban May 3, 1904, NOT 1906 as the family thought; this is a factual contrast the speaker states, not a self-correction, so both years stay; vocative spoken")

# 210 long radio show opening cleanup -> paragraphs
R2(SF, {"task": "cleanup", "locale": "en-gb", "header_style": "full",
        "transcript": "good morning and welcome to the riverside breakfast show i'm clem and it's a grey one out there so grab a coffee. coming up after eight we've got the local news and the traffic and at half past bhavesh joins me to talk about the bonfire night plans. and a reminder that the phone lines are still down so if you want to request something send a text instead"},
   "Good morning, and welcome to the Riverside Breakfast Show. I'm Clem, and it's a grey one out there, so grab a coffee.\n\nComing up after 8, we've got the local news and the traffic, and at half past, Bhavesh joins me to talk about the Bonfire Night plans.\n\nAnd a reminder that the phone lines are still down, so if you want to request something, send a text instead.",
   {"format": "prose", "numbers": ["8"], "must_include": ["Riverside Breakfast Show", "Clem", "grey one", "after 8", "half past", "Bhavesh", "Bonfire Night", "phone lines are still down", "send a text instead", "\n\n"]},
   cx=0, note="facts: Clem presenting; after 8 local news and traffic; at half past Bhavesh on Bonfire Night plans; phone lines still down ('still' kept), so if requesting, text instead (condition); en-gb ('grey'); cleanup keeps words, paragraph breaks at topic changes")

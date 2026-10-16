# W12 stage 2, part 1: TC-W12-101..140 (exec'd by W12.py; uses R2, SF, NM, NL)

# 101 long community radio update, three topics -> three paragraphs (en-gb)
R2(SF, {"task": "rewrite", "format": "prose", "locale": "en-gb", "header_style": "full",
        "transcript": "okay so update for the volunteers at riverside community radio um the new studio desk finally arrived on monday and yohan has wired up two of the four mics so far the other two need a cable we're still waiting on. next thing the saturday morning show is moving from eight to nine starting the first of november because clem can't get in that early anymore. and um the licence renewal is due at the end of the month bhavesh is filling in the form but he needs everyone's volunteer hours for the year by friday otherwise we can't submit it"},
   "Update for the volunteers at Riverside Community Radio: the new studio desk finally arrived on Monday, and Yohan has wired up two of the four mics so far. The other two need a cable we're still waiting on.\n\nNext, the Saturday morning show is moving from 8 to 9 starting 1 November because Clem can't get in that early any more.\n\nThe licence renewal is due at the end of the month. Bhavesh is filling in the form, but he needs everyone's volunteer hours for the year by Friday; otherwise, we can't submit it.",
   {"format": "prose", "numbers": ["8", "9", "1"], "min_negations": 2, "must_include": ["Riverside Community Radio", "Yohan", "two of the four mics", "Clem", "Bhavesh", "licence renewal", "by Friday", "\n\n"]},
   cx=0, note="facts: desk arrived Monday; Yohan wired two of four mics, other two wait on a cable; Saturday show 8 -> 9 from 1 November because Clem can't come that early; licence renewal due end of month; Bhavesh needs volunteer hours by Friday, otherwise can't submit (condition kept). en-gb date order and 'licence'; three topics -> three paragraphs")

# 102 short museum cleanup
R2(SF, {"task": "cleanup",
        "transcript": "the costume room is locked on mondays so uh ask ilse for the key"},
   "The costume room is locked on Mondays, so ask Ilse for the key.",
   {"format": "prose", "must_include": ["costume room", "locked on Mondays", "Ilse"], "must_not_include": ["\n"]},
   cx=0, note="facts: locked on Mondays; ask Ilse for the key; cleanup keeps words, one sentence")

# 103 devlog blog intro paragraph, one paragraph, casual, no hype
R2(NL, {"task": "rewrite", "register": "casual",
        "instruction": "turn this into the intro paragraph for my devlog, one paragraph, and don't hype it up",
        "transcript": "so devlog number fourteen um this month was mostly about the lantern mechanic in hollow tide the player can now carry a lantern that slowly runs out of oil and when it's dark the fish behave differently i rewrote the lighting system twice because the first version tanked the frame rate on the steam deck and it's still not perfect but it holds around forty five fps now. leo did the new sound effects for the lantern flicker"},
   "Devlog 14: this month was mostly about the lantern mechanic in Hollow Tide. The player can now carry a lantern that slowly runs out of oil, and when it's dark, the fish behave differently. I rewrote the lighting system twice because the first version tanked the frame rate on the Steam Deck. It's still not perfect, but it holds around 45 fps now. Leo did the new sound effects for the lantern flicker.",
   {"numbers": ["14", "45"], "min_negations": 1, "must_include": ["Hollow Tide", "lantern", "runs out of oil", "twice", "Steam Deck", "still not perfect", "around 45 fps", "Leo"], "must_not_include": ["\n", "!", "#"]},
   pos="after", cx=3, note="facts: devlog 14; lantern runs out of oil; fish behave differently in the dark; lighting rewritten twice (first version tanked frame rate on Steam Deck); still not perfect (negation); 'around 45 fps' hedge kept; Leo did the flicker sound effects; one paragraph, no hype words or exclamations")

# 104 family history note, hedged year with alternative
R2(NM, {"task": "rewrite", "format": "note", "locale": "en-in",
        "transcript": "family history notes um great grandfather was born in eighteen ninety eight i think aunt pallavi says it might be nineteen hundred in a village near kutch he moved to mombasa around nineteen twenty two and ran a cloth shop there we don't know the shop's name yet"},
   "Family history notes\nGreat-grandfather born in 1898, I think; Aunt Pallavi says it might be 1900.\nBorn in a village near Kutch.\nMoved to Mombasa around 1922 and ran a cloth shop there.\nShop's name not known yet.",
   {"format": "note", "numbers": ["1898", "1900", "1922"], "min_negations": 1, "must_include": ["I think", "Aunt Pallavi", "might be 1900", "Kutch", "Mombasa", "around 1922", "cloth shop", "not known yet"]},
   cx=0, note="facts: born 1898 (hedged 'I think') OR 1900 per Aunt Pallavi ('might'), both kept; village near Kutch; moved to Mombasa around 1922 (hedge); cloth shop; shop's name not known yet (negation); terse lines, no bullets")

# 105 museum announcement, short, times exact
R2(NL, {"task": "rewrite",
        "instruction": "make it an announcement for the volunteer noticeboard and keep the times exactly",
        "transcript": "uh from next week the museum opens at ten thirty instead of ten on weekdays because of the new cleaning schedule weekends stay the same and the first tour still starts at eleven"},
   "From next week, the museum opens at 10:30 instead of 10 on weekdays because of the new cleaning schedule. Weekends stay the same, and the first tour still starts at 11.",
   {"numbers": ["10:30", "10", "11"], "must_include": ["next week", "weekdays", "cleaning schedule", "Weekends stay the same", "first tour still starts at 11"], "must_not_include": ["\n\n", "!"]},
   pos="after", cx=2, note="facts: from next week weekday opening 10:30 instead of 10, because of new cleaning schedule; weekends unchanged; first tour still at 11; short announcement, one paragraph")

# 106 LinkedIn-style launch post, no hashtags/claims
R2(SF, {"task": "rewrite", "format": "post",
        "transcript": "um so we just opened the waitlist for tallyroom it's a shared expense tracker for flatmates nothing fancy it splits bills and reminds people who owes what if you live with other people i'd love you to try the beta it's free while we're testing"},
   "We just opened the waitlist for Tallyroom.\n\nIt's a shared expense tracker for flatmates. Nothing fancy: it splits bills and reminds people who owes what.\n\nIf you live with other people, I'd love you to try the beta. It's free while we're testing.",
   {"format": "post", "must_include": ["Tallyroom", "waitlist", "flatmates", "Nothing fancy", "free while we're testing"], "must_not_include": ["#", "!"]},
   cx=0, note="facts: waitlist just opened; shared expense tracker for flatmates; 'nothing fancy' kept (negation-like modesty); free only while testing (condition kept); 'I'd love you to try' is the speaker's own; no hashtags, emoji or invented metrics")

# 107 markdown newsletter, headings requested
R2(NM, {"task": "rewrite", "markup": "markdown",
        "instruction": "format it as a newsletter with a markdown heading for each section",
        "transcript": "okay october newsletter the section on new shows we've got two new shows this month freya's folk hour on sundays at six and a kids' storytelling slot on wednesday afternoons then the thanks section a big thank you to everyone who helped at the open day we signed up eleven new volunteers and then help wanted we still need someone who can edit audio on weekday evenings"},
   "# October Newsletter\n\n## New Shows\n\nWe've got two new shows this month: Freya's Folk Hour on Sundays at 6 and a kids' storytelling slot on Wednesday afternoons.\n\n## Thanks\n\nA big thank you to everyone who helped at the open day. We signed up 11 new volunteers.\n\n## Help Wanted\n\nWe still need someone who can edit audio on weekday evenings.",
   {"numbers": ["6", "11"], "must_include": ["# October Newsletter", "## New Shows", "## Thanks", "## Help Wanted", "Freya", "Sundays at 6", "Wednesday afternoons", "11 new volunteers", "weekday evenings"]},
   pos="after", cx=2, note="facts: two new shows (Freya's folk hour Sundays at 6; kids' storytelling Wednesday afternoons); thanks for open day help; 11 new volunteers signed up; still need a weekday-evening audio editor; headings only because markup markdown AND instruction asks; section names are the speaker's")

# 108 museum volunteer newsletter, plain prose, paragraphs (en-gb)
R2(NM, {"task": "rewrite", "format": "prose", "locale": "en-gb",
        "transcript": "volunteer newsletter for november um the big news is the textile gallery reopens on the fourteenth after the roof repair and we need extra guides that first weekend. on training rukmini is running a refresher on handling objects on the sixth it's not mandatory but if you haven't done it in two years please come. and finally the christmas social is on the twelfth of december at the curator's house bring a plate if you can"},
   "Volunteer newsletter for November: the big news is the textile gallery reopens on the 14th after the roof repair, and we need extra guides that first weekend.\n\nOn training, Rukmini is running a refresher on handling objects on the 6th. It's not mandatory, but if you haven't done it in two years, please come.\n\nFinally, the Christmas social is on 12 December at the curator's house. Bring a plate if you can.",
   {"format": "prose", "numbers": ["14", "6", "12"], "min_negations": 2, "must_include": ["November", "textile gallery", "roof repair", "extra guides", "Rukmini", "not mandatory", "two years", "12 December", "curator's house"], "must_not_include": ["#", "- ", "**"]},
   cx=0, note="facts: textile gallery reopens on the 14th after roof repair; extra guides needed first weekend; Rukmini's handling refresher on the 6th, NOT mandatory; condition: if you haven't done it in two years, please come; Christmas social 12 December at curator's house; 'bring a plate if you can' (condition). Plain paragraphs, no headings; en-gb date order")

# 109 short journal cleanup, 'again' and 'third' are facts
R2(SF, {"task": "cleanup",
        "transcript": "slept badly again uh third night in a row i think it's the coffee after four"},
   "Slept badly again, third night in a row. I think it's the coffee after 4.",
   {"format": "prose", "numbers": ["4"], "must_include": ["again", "third night in a row", "I think", "coffee after 4"], "must_not_include": ["\n"]},
   cx=0, note="facts: 'again' and 'third night in a row' are facts; 'I think' hedge kept; coffee after 4; cleanup keeps words")

# 110 retirement toast, warm, no invented anecdotes (en-in)
R2(NL, {"task": "rewrite", "tone": "warm", "locale": "en-in",
        "instruction": "make it a short toast I can read out, and don't make up any stories about her",
        "transcript": "so we're here for mrs rukmini iyer who's retiring after thirty one years of teaching music at the community centre um she taught half this room how to play the harmonium including me and she never once raised her voice so please raise your glasses to rukmini"},
   "We're here for Mrs Rukmini Iyer, who's retiring after 31 years of teaching music at the community centre.\n\nShe taught half this room how to play the harmonium, me included, and she never once raised her voice.\n\nSo please raise your glasses to Rukmini.",
   {"numbers": ["31"], "min_negations": 1, "must_include": ["Rukmini Iyer", "31 years", "music", "harmonium", "never once raised her voice", "raise your glasses"], "must_not_include": ["I remember", "proud", "delighted"]},
   pos="after", cx=2, note="facts: Rukmini Iyer retiring after 31 years teaching music at the community centre; taught half the room harmonium incl. speaker; never once raised her voice (negation); no invented stories or emotions; warmth only in wording")

# 111 product update notes, format note
R2(SF, {"task": "rewrite", "format": "note",
        "transcript": "release notes for version two point three um dark mode is finally in the offline sync bug where edits got lost is fixed exports to csv now include the category column and we removed the old pdf export because almost nobody used it"},
   "Release notes for version 2.3\nDark mode is finally in.\nThe offline sync bug where edits got lost is fixed.\nExports to CSV now include the category column.\nRemoved the old PDF export because almost nobody used it.",
   {"format": "note", "numbers": ["2.3"], "min_negations": 1, "must_include": ["2.3", "Dark mode", "offline sync bug", "category column", "old PDF export", "almost nobody used it"]},
   cx=0, note="facts: version 2.3; dark mode in; offline sync bug (lost edits) fixed; CSV exports include category column; old PDF export removed because 'almost nobody' used it (hedge 'almost' kept); terse lines, no bullets")

# 112 longer donor update, fuller sentences, no new facts
R2(NL, {"task": "rewrite", "length": "longer",
        "instruction": "make it a bit longer for the donor update but don't add anything new",
        "transcript": "the new ramp at the museum entrance is done wheelchair users can now get into the main hall without help thanks to the grant from the rotary club"},
   "The new ramp at the museum entrance is done. This means wheelchair users can now get into the main hall without help. The work was made possible thanks to the grant from the Rotary Club.",
   {"min_negations": 0, "must_include": ["ramp at the museum entrance", "wheelchair users", "main hall without help", "Rotary Club"], "must_not_include": ["thrilled", "delighted", "grateful", "\n"]},
   cx=2, note="facts: ramp at museum entrance done; wheelchair users get into main hall without help; funded by Rotary Club grant; longer = fuller sentences only, no new facts, numbers or feelings")

# 113 long family-history journal cleanup -> paragraphs (en-in)
R2(SF, {"task": "cleanup", "locale": "en-in",
        "transcript": "journal sunday um spent the morning going through dadi's old letters with bhavesh most of them are in gujarati and he read them out to me there's one from nineteen sixty four where she talks about the flood in the village. in the afternoon i tried to scan them but the scanner kept jamming so i only got through about twenty. tomorrow i want to label the folders properly before i forget which box each letter came from"},
   "Journal, Sunday. Spent the morning going through Dadi's old letters with Bhavesh. Most of them are in Gujarati, and he read them out to me. There's one from 1964 where she talks about the flood in the village.\n\nIn the afternoon, I tried to scan them, but the scanner kept jamming, so I only got through about 20.\n\nTomorrow I want to label the folders properly before I forget which box each letter came from.",
   {"format": "prose", "numbers": ["1964", "20"], "must_include": ["Dadi's old letters", "Bhavesh", "Gujarati", "1964", "flood", "scanner kept jamming", "about 20", "\n\n"]},
   cx=0, note="facts: letters read with Bhavesh, mostly in Gujarati; one from 1964 about the flood; scanner jammed, only about 20 scanned ('about' kept); plan to label folders tomorrow; cleanup keeps words, paragraph breaks at topic changes")

# 114 radio programming meeting notes, format note (en-gb)
R2(NM, {"task": "rewrite", "format": "note", "locale": "en-gb", "header_style": "full",
        "transcript": "notes from the programming meeting we agreed the late night jazz show stays but moves to fridays clem will look into a second presenter for the breakfast show no decision on the podcast feed yet ilse thinks it costs too much and arnav disagrees next meeting is the third"},
   "Programming meeting notes\nAgreed: the late-night jazz show stays but moves to Fridays.\nClem will look into a second presenter for the breakfast show.\nNo decision on the podcast feed yet; Ilse thinks it costs too much, Arnav disagrees.\nNext meeting: the 3rd.",
   {"format": "note", "numbers": ["3"], "min_negations": 1, "must_include": ["late-night jazz show stays", "Fridays", "Clem will look into", "No decision on the podcast feed", "Ilse", "Arnav disagrees", "the 3rd"]},
   cx=0, note="facts: jazz show stays, moves to Fridays (agreed); Clem only 'looks into' a second breakfast presenter (no stronger commitment); NO decision on podcast feed, Ilse vs Arnav views kept as theirs; next meeting the 3rd; terse lines, no bullets")

# 115 LinkedIn post, no hashtags, hedge kept
R2(NL, {"task": "rewrite",
        "instruction": "linkedin post, no hashtags, and keep the bit where I say it might not work",
        "transcript": "um so i'm trying something new with hollow tide i'm releasing the first chapter for free on itch next month and if enough people play it i'll fund the rest through early access it might not work but i'd rather find out now than after two more years of building in private"},
   "I'm trying something new with Hollow Tide.\n\nI'm releasing the first chapter for free on itch next month. If enough people play it, I'll fund the rest through early access.\n\nIt might not work, but I'd rather find out now than after two more years of building in private.",
   {"format": "post", "min_negations": 1, "must_include": ["Hollow Tide", "first chapter", "free", "next month", "If enough people play it", "early access", "might not work", "two more years"], "must_not_include": ["#"]},
   pos="after", cx=3, note="facts: first chapter free on itch next month; condition: IF enough people play, fund the rest via early access; 'might not work' hedge+negation kept; two more years of building in private; no hashtags")

# 116 short radio message
R2(SF, {"task": "rewrite", "format": "message",
        "transcript": "clem the mic in studio two is buzzing again don't use it tonight"},
   "Clem, the mic in Studio 2 is buzzing again. Don't use it tonight.",
   {"format": "message", "numbers": ["2"], "min_negations": 1, "must_include": ["Clem", "Studio 2", "buzzing again", "Don't use it tonight"]},
   cx=0, note="facts: Studio 2 mic buzzing 'again' (fact); don't use it tonight (negation); vocative 'Clem' was spoken; message, no greeting")

# 117 shorter fundraiser update, all numbers and names kept (en-in)
R2(NL, {"task": "rewrite", "length": "shorter", "locale": "en-in",
        "instruction": "shorter, but keep all the numbers and names",
        "transcript": "so i just want to give everyone a quick rundown of where we are with the readathon fundraiser um so far we've had sixty two kids sign up and together they've pledged to read about nine hundred books by the end of november and the sponsorship side is going okay we've raised forty one thousand rupees so far against a target of seventy five thousand pallavi is chasing the last few sponsors and um mason said he'd sort out the certificates for every kid who finishes"},
   "Readathon fundraiser update: 62 kids have signed up and pledged to read about 900 books by the end of November. Sponsorship is going okay, with ₹41,000 raised so far against a ₹75,000 target. Pallavi is chasing the last few sponsors, and Mason said he'd sort out certificates for every kid who finishes.",
   {"numbers": ["62", "900", "41,000", "75,000"], "must_include": ["Readathon", "about 900 books", "end of November", "going okay", "so far", "Pallavi", "Mason said he'd", "every kid who finishes"], "must_not_include": ["\n"]},
   pos="after", cx=2, note="facts: 62 kids signed up; about 900 books pledged by end of November ('about' kept); sponsorship 'going okay'; ₹41,000 raised so far vs ₹75,000 target (rupees spoken for the first amount in the same sentence, so ₹ on both); Pallavi chasing sponsors; Mason 'said he'd' sort certificates for finishers (reported commitment, not firmed); visibly shorter")

# 118 museum group-visit briefing -> paragraphs (en-gb)
R2(SF, {"task": "rewrite", "locale": "en-gb", "header_style": "full",
        "transcript": "right so for the scout group visits next week um we've got three groups tuesday wednesday and thursday mornings each about thirty kids. freya is leading the egyptian room and ilse has the coins and medals room. please don't let the kids touch the glass cases the alarms are very sensitive and they go off at the slightest bump. and lunch for volunteers will be in the education room from twelve thirty"},
   "For the scout group visits next week, we've got three groups on Tuesday, Wednesday and Thursday mornings, each about 30 kids.\n\nFreya is leading the Egyptian room, and Ilse has the coins and medals room.\n\nPlease don't let the kids touch the glass cases. The alarms are very sensitive, and they go off at the slightest bump.\n\nLunch for volunteers will be in the education room from 12:30.",
   {"format": "prose", "numbers": ["30", "12:30"], "min_negations": 1, "must_include": ["scout group visits next week", "three groups", "about 30 kids", "Freya", "Egyptian room", "Ilse", "coins and medals", "don't let the kids touch the glass cases", "education room"], "must_not_include": ["- "]},
   cx=0, note="facts: three groups Tue/Wed/Thu mornings, each about 30 kids ('about' kept); Freya Egyptian room, Ilse coins and medals; don't let kids touch glass cases (negation), alarms sensitive; volunteer lunch from 12:30 in education room; topic changes -> paragraphs, no bullets")

# 119 post under plain, three items stay in a sentence
R2(NM, {"task": "rewrite", "format": "post",
        "transcript": "proud of the team this week we shipped dark mode fixed the sync bug and finally answered every support ticket in under a day"},
   "Proud of the team this week.\n\nWe shipped dark mode, fixed the sync bug, and finally answered every support ticket in under a day.",
   {"format": "post", "must_include": ["Proud of the team", "dark mode", "sync bug", "every support ticket in under a day"], "must_not_include": ["- ", "#", "**"]},
   cx=0, note="facts: this week; shipped dark mode, fixed sync bug, every ticket answered in under a day; 'proud' is the speaker's word; three items stay in one sentence (no list cue), no hashtags")

# 120 journal cleanup with paragraphs instructed, exact words
R2(NL, {"task": "cleanup",
        "instruction": "clean it up as a journal entry but keep my exact words, just add paragraphs",
        "transcript": "okay so today the game crashed live on stream in front of like two hundred people um i laughed it off but honestly i wanted to disappear. afterwards three people messaged to say they'd buy it anyway which i did not expect. tomorrow fix the save bug first before anything else"},
   "Today the game crashed live on stream in front of like 200 people. I laughed it off, but honestly, I wanted to disappear.\n\nAfterwards, three people messaged to say they'd buy it anyway, which I did not expect.\n\nTomorrow, fix the save bug first before anything else.",
   {"format": "prose", "numbers": ["200"], "min_negations": 1, "must_include": ["crashed live on stream", "like 200 people", "honestly", "three people", "did not expect", "save bug first"]},
   cx=2, note="facts: crash on stream in front of 'like 200' people ('like' = about, kept in cleanup); three people would buy anyway; 'did not expect' negation; save bug first tomorrow; exact words kept, paragraphs only")

# 121 curator meeting notes, condition kept
R2(SF, {"task": "rewrite", "format": "note",
        "transcript": "quick notes from the meeting with the curator um the loan of the two paintings from the city gallery is confirmed for january they arrive on the ninth we need to repaint the east wall before then bhavesh will get quotes but nothing gets ordered until the trustees sign off"},
   "Notes from the meeting with the curator\nLoan of the two paintings from the city gallery confirmed for January; they arrive on the 9th.\nEast wall needs repainting before then.\nBhavesh will get quotes.\nNothing gets ordered until the trustees sign off.",
   {"format": "note", "numbers": ["9"], "min_negations": 1, "must_include": ["curator", "two paintings", "city gallery", "January", "the 9th", "East wall", "Bhavesh will get quotes", "until the trustees sign off"]},
   cx=0, note="facts: loan of two paintings confirmed for January, arrive the 9th; repaint east wall before then; Bhavesh gets quotes; nothing ordered UNTIL trustees sign off (condition/negation); terse lines")

# 122 off-air announcement, no emoji or exclamations
R2(NL, {"task": "rewrite",
        "instruction": "turn this into a short announcement for the station's social page, no emoji and no exclamation marks",
        "transcript": "uh we're off air this sunday from midnight to six am for transmitter maintenance the stream online will keep running with repeats"},
   "We're off air this Sunday from midnight to 6 a.m. for transmitter maintenance. The online stream will keep running with repeats.",
   {"numbers": ["6"], "must_include": ["off air this Sunday", "midnight to 6 a.m.", "transmitter maintenance", "online stream", "repeats"], "must_not_include": ["!", "#"]},
   pos="after", cx=3, note="facts: off air this Sunday midnight to 6 a.m. for transmitter maintenance; online stream continues with repeats; no emoji/exclamation as instructed")

# 123 long devlog -> four paragraphs
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "devlog update so the big thing this week is that the demo is finally playable from start to finish it's about twenty minutes long if you don't get lost. art wise yohan redid all the cave backgrounds and they look so much better in the dark sections. on the not so fun side i had to cut the grappling hook it just wasn't working with the physics and i'd rather ship without it than ship it broken. next week is all about the steam page trailer"},
   "Devlog update: the big thing this week is that the demo is finally playable from start to finish. It's about 20 minutes long if you don't get lost.\n\nArt-wise, Yohan redid all the cave backgrounds, and they look so much better in the dark sections.\n\nOn the not-so-fun side, I had to cut the grappling hook. It just wasn't working with the physics, and I'd rather ship without it than ship it broken.\n\nNext week is all about the Steam page trailer.",
   {"format": "prose", "numbers": ["20"], "min_negations": 2, "must_include": ["playable from start to finish", "about 20 minutes", "if you don't get lost", "Yohan", "cave backgrounds", "grappling hook", "Steam page trailer", "\n\n"], "must_not_include": ["- "]},
   cx=0, note="facts: demo playable start to finish; about 20 minutes if you don't get lost (condition kept); Yohan redid cave backgrounds; grappling hook cut (wasn't working with physics); next week Steam page trailer; four topics -> four paragraphs")

# 124 markdown allowed, note format, not asked -> plain lines
R2(NM, {"task": "rewrite", "format": "note", "markup": "markdown",
        "transcript": "to do for the archive project scan the passports label the photo albums by decade and ask leo if he still has grandpa's army papers"},
   "To do for the archive project\nScan the passports.\nLabel the photo albums by decade.\nAsk Leo if he still has Grandpa's army papers.",
   {"format": "note", "must_include": ["archive project", "passports", "by decade", "Leo", "Grandpa's army papers"], "must_not_include": ["**", "#", "- "]},
   cx=0, note="facts: three to-dos: scan passports; label albums by decade; ask Leo IF he still has Grandpa's army papers (question kept, not answered); lead line kept; markup markdown but nothing asks for emphasis -> plain terse lines")

# 125 one paragraph newsletter item, every name (en-gb)
R2(NL, {"task": "rewrite", "locale": "en-gb",
        "instruction": "keep it as one paragraph, it's for the newsletter, and keep every name",
        "transcript": "we had a great turnout at the fundraising quiz night on saturday um about eighty people came and we raised just over two thousand pounds which pays for the new transmitter part. thanks to clem who wrote all the questions and bhavesh who did the sound and the pub that gave us the back room for free. the winning team was called the static and they've already asked about a rematch"},
   "We had a great turnout at the fundraising quiz night on Saturday. About 80 people came, and we raised just over £2,000, which pays for the new transmitter part. Thanks to Clem, who wrote all the questions; Bhavesh, who did the sound; and the pub that gave us the back room for free. The winning team was called The Static, and they've already asked about a rematch.",
   {"numbers": ["80", "2,000"], "must_include": ["quiz night on Saturday", "About 80 people", "just over £2,000", "transmitter part", "Clem", "Bhavesh", "back room for free", "The Static", "rematch"], "must_not_include": ["\n"]},
   pos="after", cx=3, note="facts: quiz night Saturday; about 80 people; just over £2,000 ('just over' kept) pays for transmitter part; thanks Clem (questions), Bhavesh (sound), the pub (free back room); winners The Static asked about a rematch; one paragraph")

# 126 short meeting note, negation + day
R2(SF, {"task": "rewrite", "format": "note",
        "transcript": "meeting notes nothing decided on the logo come back to it thursday"},
   "Meeting notes\nNothing decided on the logo; come back to it Thursday.",
   {"format": "note", "min_negations": 1, "must_include": ["Nothing decided on the logo", "Thursday"]},
   cx=0, note="facts: nothing decided on the logo (negation); revisit Thursday; terse lines")

# 127 open-day welcome speech, friendly, nothing added
R2(NL, {"task": "rewrite", "tone": "friendly",
        "instruction": "make it a short welcome speech for the open day and don't add anything I didn't say",
        "transcript": "hi everyone welcome to the hillside heritage museum open day um the volunteers are in the green t-shirts if you need anything the tea is in the courtyard and the guided tour starts at two from the front desk the upstairs gallery is closed today for repairs sorry about that"},
   "Hi everyone, and welcome to the Hillside Heritage Museum open day.\n\nIf you need anything, the volunteers are in the green T-shirts. The tea is in the courtyard, and the guided tour starts at 2 from the front desk.\n\nThe upstairs gallery is closed today for repairs. Sorry about that.",
   {"numbers": ["2"], "must_include": ["Hillside Heritage Museum", "green T-shirts", "courtyard", "guided tour starts at 2", "front desk", "upstairs gallery is closed today", "Sorry about that"], "must_not_include": ["enjoy", "delighted", "glad"]},
   pos="after", cx=2, note="facts: volunteers in green T-shirts; tea in courtyard; guided tour at 2 from front desk; upstairs gallery closed today for repairs; apology was dictated; greeting was dictated; no added wishes ('enjoy your day') or feelings")

# 128 medium pricing thought, one paragraph, hedge kept
R2(SF, {"task": "rewrite",
        "transcript": "so a quick thought on pricing for tallyroom we're thinking four dollars a month per household not per person because nobody wants to argue about who pays for the app that splits the bills"},
   "A quick thought on pricing for Tallyroom: we're thinking $4 a month per household, not per person, because nobody wants to argue about who pays for the app that splits the bills.",
   {"numbers": ["4"], "min_negations": 2, "must_include": ["Tallyroom", "we're thinking", "$4 a month per household", "not per person", "nobody wants to argue"], "must_not_include": ["\n"]},
   cx=0, note="facts: tentative ('we're thinking', not decided) $4 a month per household, NOT per person; reason kept; one paragraph")

# 129 bullets only because instructed, lead line kept
R2(NM, {"task": "rewrite",
        "instruction": "put the three dates as a bullet list under one lead line",
        "transcript": "important dates for the family reunion the hall booking deposit is due on the fifth the menu has to be final by the twentieth and the reunion itself is on the twenty seventh of december"},
   "Important dates for the family reunion:\n- The hall booking deposit is due on the 5th.\n- The menu has to be final by the 20th.\n- The reunion itself is on December 27.",
   {"format": "bullets", "numbers": ["5", "20", "27"], "must_include": ["Important dates for the family reunion:", "deposit is due on the 5th", "has to be final by the 20th", "December 27"]},
   pos="after", cx=2, note="facts: deposit due the 5th; menu must be final by the 20th (requirement); reunion December 27; bullets only because the instruction asks; lead line kept")

# 130 long family-history journal rewrite -> paragraphs (en-in)
R2(SF, {"task": "rewrite", "format": "prose", "locale": "en-in", "header_style": "full",
        "transcript": "so today i finally sat down with nani and recorded her talking about her childhood for almost an hour she grew up in a house in surat with eleven people under one roof and she remembers the day they got their first radio in nineteen fifty eight i think. she also told me her father didn't want her to study past class ten but her mother sold a pair of earrings to pay the college fees. i want to transcribe the recording this week before the details fade and maybe share it with the cousins"},
   "Today I finally sat down with Nani and recorded her talking about her childhood for almost an hour. She grew up in a house in Surat with 11 people under one roof, and she remembers the day they got their first radio, in 1958, I think.\n\nShe also told me her father didn't want her to study past Class 10, but her mother sold a pair of earrings to pay the college fees.\n\nI want to transcribe the recording this week before the details fade, and maybe share it with the cousins.",
   {"format": "prose", "numbers": ["11", "1958", "10"], "min_negations": 1, "must_include": ["Nani", "almost an hour", "Surat", "11 people", "1958, I think", "didn't want her to study past Class 10", "earrings", "this week", "maybe share it with the cousins"]},
   cx=0, note="facts: recorded almost an hour; Surat house with 11 people; first radio in 1958 (hedged 'I think'); father didn't want her to study past Class 10 (negation); mother sold earrings for college fees; transcribe this week; 'maybe' share with cousins (hedge); three topics -> paragraphs")

# 131 product update for users, no promised dates
R2(NL, {"task": "rewrite",
        "instruction": "make this a product update for our users, keep it plain and don't promise any dates",
        "transcript": "um the android widget is coming we're testing it internally now it shows your balance and the next bill due we don't have a release date yet and honestly it depends on how the testing goes"},
   "The Android widget is coming. We're testing it internally now, and it shows your balance and the next bill due.\n\nWe don't have a release date yet, and honestly, it depends on how the testing goes.",
   {"min_negations": 1, "must_include": ["Android widget", "testing it internally", "balance", "next bill due", "don't have a release date yet", "depends on how the testing goes"], "must_not_include": ["soon", "next month", "!"]},
   pos="after", cx=3, note="facts: Android widget coming, in internal testing; shows balance and next bill due; NO release date yet; release depends on testing (condition kept); no invented dates or 'soon'")

# 132 short reminder cleanup
R2(SF, {"task": "cleanup",
        "transcript": "remind me to ask mason about the frame rate on older laptops"},
   "Remind me to ask Mason about the frame rate on older laptops.",
   {"format": "prose", "must_include": ["Remind me to ask Mason", "frame rate on older laptops"], "must_not_include": ["\n"]},
   cx=0, note="facts: reminder text kept as dictated text (no action claimed, no reminder set); Mason; older laptops")

# 133 museum inventory note (en-in)
R2(NM, {"task": "rewrite", "format": "note", "locale": "en-in",
        "transcript": "inventory notes room three so in total we counted forty two items two are missing their labels one brass lamp has a crack on the base do not move it until ilse photographs it"},
   "Inventory notes, Room 3\nCounted 42 items in total.\nTwo are missing their labels.\nOne brass lamp has a crack on the base; do not move it until Ilse photographs it.",
   {"format": "note", "numbers": ["3", "42"], "min_negations": 1, "must_include": ["Room 3", "42 items in total", "missing their labels", "brass lamp", "crack on the base", "do not move it until Ilse photographs it"]},
   cx=0, note="facts: Room 3; 42 items counted; two missing labels; one brass lamp cracked at base; do NOT move it UNTIL Ilse photographs it; terse lines")

# 134 formal + shorter for trustees, condition kept (en-gb)
R2(NL, {"task": "rewrite", "register": "formal", "length": "shorter", "locale": "en-gb",
        "instruction": "this is for the trustees, keep the condition about the grant exactly",
        "transcript": "so basically the roof repair is going to cost more than we thought it was meant to be eighteen thousand pounds and now the builder says it's closer to twenty three thousand because of the rotten beams um we can cover it if the heritage grant comes through in december otherwise we'll need to delay the textile gallery reopening"},
   "The roof repair will cost more than expected. The original estimate was £18,000, but the builder now says it is closer to £23,000 because of the rotten beams. We can cover this if the heritage grant comes through in December; otherwise, we will need to delay the textile gallery reopening.",
   {"numbers": ["18,000", "23,000"], "must_include": ["roof repair", "£18,000", "closer to £23,000", "rotten beams", "if the heritage grant comes through in December", "otherwise", "delay the textile gallery reopening"], "must_not_include": ["\n"]},
   pos="after", cx=3, note="facts: estimate was £18,000, builder now says closer to £23,000 ('closer to' hedge kept; pounds spoken for the first amount in the same comparison, so £ on both); cause rotten beams; condition: cover it IF heritage grant comes through in December, otherwise delay textile gallery reopening; formal and visibly shorter")

# 135 devlog milestone post
R2(SF, {"task": "rewrite", "format": "post",
        "transcript": "we just hit one thousand wishlists on steam for hollow tide which is a number i genuinely didn't think we'd reach before the demo um thank you to everyone who shared the trailer"},
   "We just hit 1,000 wishlists on Steam for Hollow Tide, a number I genuinely didn't think we'd reach before the demo.\n\nThank you to everyone who shared the trailer.",
   {"format": "post", "numbers": ["1,000"], "min_negations": 1, "must_include": ["1,000 wishlists", "Steam", "Hollow Tide", "didn't think we'd reach before the demo", "shared the trailer"], "must_not_include": ["#", "!"]},
   cx=0, note="facts: 1,000 Steam wishlists; speaker didn't think they'd reach it before the demo (negation); thanks to trailer sharers; no hashtags/emoji")

# 136 engagement toast, short, no invented memories
R2(NL, {"task": "rewrite",
        "instruction": "turn this into a toast for my brother's engagement party, keep it short, and don't invent any memories",
        "transcript": "um so arnav is my little brother and for twenty six years he's been late to everything except today so freya clearly has a good influence on him um freya welcome to the family we're lucky to have you everyone please raise a glass to arnav and freya"},
   "Arnav is my little brother, and for 26 years he's been late to everything, except today. So Freya clearly has a good influence on him.\n\nFreya, welcome to the family. We're lucky to have you.\n\nEveryone, please raise a glass to Arnav and Freya.",
   {"numbers": ["26"], "must_include": ["Arnav", "little brother", "26 years", "late to everything, except today", "Freya", "welcome to the family", "lucky to have you", "raise a glass"], "must_not_include": ["I remember", "when we were kids"]},
   pos="after", cx=3, note="facts: Arnav is the little brother; late to everything for 26 years except today; Freya's good influence; welcome Freya; lucky to have her; toast to Arnav and Freya; no invented memories")

# 137 long clean-water appeal update -> paragraphs (en-in)
R2(SF, {"task": "rewrite", "locale": "en-in", "header_style": "full",
        "transcript": "okay so quick update on the clean water appeal um we've now funded four hand pumps out of the six we planned and the fifth is about halfway there. bhavesh visited the village last week and said the first two pumps are already in daily use but one of them needs a new washer which he's sorting out. the one thing i'd ask is if anyone has contacts at a local business who might match donations please send them to rukmini because the matching offer we had fell through"},
   "Quick update on the clean water appeal: we've now funded four hand pumps out of the six we planned, and the fifth is about halfway there.\n\nBhavesh visited the village last week and said the first two pumps are already in daily use, but one of them needs a new washer, which he's sorting out.\n\nThe one thing I'd ask: if anyone has contacts at a local business who might match donations, please send them to Rukmini, because the matching offer we had fell through.",
   {"format": "prose", "must_include": ["clean water appeal", "four hand pumps out of the six", "about halfway", "Bhavesh", "last week", "daily use", "new washer", "Rukmini", "fell through", "\n\n"]},
   cx=0, note="facts: four of six planned pumps funded; fifth about halfway; Bhavesh visited last week, first two in daily use, one needs a washer (he's sorting it); ask: IF anyone has contacts who 'might' match donations, send to Rukmini; previous matching offer fell through; three topics -> paragraphs")

# 138 markdown, bold only date and time (instructed)
R2(NM, {"task": "rewrite", "markup": "markdown",
        "instruction": "bold the date and time only",
        "transcript": "reminder for volunteers the annual general meeting is on thursday the twenty third at seven pm in the upstairs room please come if you can we need at least twenty members for it to count"},
   "Reminder for volunteers: the annual general meeting is on **Thursday the 23rd at 7 p.m.** in the upstairs room. Please come if you can. We need at least 20 members for it to count.",
   {"numbers": ["23", "7", "20"], "must_include": ["annual general meeting", "**Thursday the 23rd at 7 p.m.**", "upstairs room", "if you can", "at least 20 members"], "must_not_include": ["#", "\n"]},
   pos="after", cx=1, note="facts: AGM Thursday the 23rd at 7 p.m., upstairs room; please come if you can (condition, stays optional); need at least 20 members for it to count; bold only on date/time because instructed; no headings")

# 139 short message, condition kept
R2(SF, {"task": "rewrite", "format": "message",
        "transcript": "pallavi the trailer's uploaded but keep it private until friday"},
   "Pallavi, the trailer's uploaded, but keep it private until Friday.",
   {"format": "message", "must_include": ["Pallavi", "trailer's uploaded", "private until Friday"]},
   cx=0, note="facts: trailer uploaded; keep private UNTIL Friday; vocative spoken; no greeting")

# 140 longer devlog paragraph, keep the unsure parts
R2(NL, {"task": "rewrite", "length": "longer",
        "instruction": "make it a fuller paragraph for the devlog, no new details, and keep the parts where I'm unsure",
        "transcript": "the boss fight is maybe eighty percent done i think the second phase is too easy and i'm not sure the music fits yet"},
   "The boss fight is maybe 80 percent done. When it comes to the second phase, I think it's too easy, and as for the music, I'm not sure it fits yet.",
   {"numbers": ["80"], "min_negations": 1, "must_include": ["maybe 80 percent done", "second phase", "I think", "too easy", "not sure", "music"], "must_not_include": ["\n"]},
   pos="after", cx=3, note="facts: boss fight 'maybe' 80 percent done; 'I think' second phase too easy; not sure the music fits yet; hedges kept; longer = fuller sentence shapes only, no new details")

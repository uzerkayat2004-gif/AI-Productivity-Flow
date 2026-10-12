# W12 stage 2, part 2: TC-W12-141..180 (exec'd by W12.py; uses R2, SF, NM, NL)

# 141 talk prep, paragraphs + more concise, every number kept
R2(NL, {"task": "rewrite", "header_style": "full",
        "instruction": "split this into paragraphs by topic and make it more concise, but keep every number",
        "transcript": "okay notes on the talk for the indie dev meetup um so the slot is twenty five minutes plus five for questions and i keep going over in rehearsal i'm at about thirty one minutes right now so something has to go. i think the section on our old engine can be cut down to one slide nobody really needs the history. for the demo i'll play the first level live but i'll have a recorded backup in case the wifi dies. and mason offered to hold the mic during questions so i can use the controller"},
   "Talk for the indie dev meetup: the slot is 25 minutes plus 5 for questions, and I'm at about 31 minutes in rehearsal, so something has to go.\n\nI think the old engine section can be cut to one slide; nobody really needs the history.\n\nFor the demo, I'll play the first level live, with a recorded backup in case the Wi-Fi dies.\n\nMason offered to hold the mic during questions so I can use the controller.",
   {"format": "prose", "numbers": ["25", "5", "31"], "min_negations": 1, "must_include": ["indie dev meetup", "25 minutes plus 5", "about 31 minutes", "I think", "one slide", "nobody really needs the history", "recorded backup", "Mason offered", "\n\n"]},
   pos="after", cx=3, note="facts: slot 25 minutes + 5 for questions; rehearsal at about 31 minutes, something must go; 'I think' old-engine section cut to one slide; nobody needs the history (negation); first level live with recorded backup in case Wi-Fi dies (condition); Mason offered to hold mic; framing 'talk for the indie dev meetup' kept; visibly more concise, four paragraphs")

# 142 short question message
R2(SF, {"task": "rewrite", "format": "message",
        "transcript": "freya can you send me the stream key before seven"},
   "Freya, can you send me the stream key before 7?",
   {"format": "message", "numbers": ["7"], "must_include": ["Freya", "stream key", "before 7?"]},
   cx=0, note="facts: request for stream key before 7; stays a question (not answered); vocative spoken")

# 143 cousins call notes, format note (en-gb)
R2(NM, {"task": "rewrite", "format": "note", "locale": "en-gb", "header_style": "full",
        "transcript": "notes from the cousins call um we agreed to split the cost of the dna kits four ways yohan will order them ilse is digitising the photo albums but she needs the ones from aunty's flat first we didn't settle where to hold the reunion and the next call is in two weeks"},
   "Cousins call notes\nAgreed to split the cost of the DNA kits four ways.\nYohan will order them.\nIlse is digitising the photo albums, but she needs the ones from Aunty's flat first.\nDidn't settle where to hold the reunion.\nNext call in two weeks.",
   {"format": "note", "min_negations": 1, "must_include": ["four ways", "DNA kits", "Yohan will order", "Ilse", "digitising", "Aunty's flat first", "Didn't settle where to hold the reunion", "two weeks"]},
   cx=0, note="facts: DNA kit cost split four ways (agreed); Yohan orders; Ilse digitising albums, needs the ones from Aunty's flat first; reunion venue NOT settled; next call in two weeks; en-gb 'digitising'; terse lines")

# 144 in-app announcement, friendly, no exclamations
R2(NL, {"task": "rewrite", "tone": "friendly",
        "instruction": "write this as a short in-app announcement, no exclamation marks",
        "transcript": "starting today you can export your budget as a spreadsheet from the settings page um it works on ios and web the android version follows next week"},
   "Starting today, you can export your budget as a spreadsheet right from the Settings page. It works on iOS and web, and the Android version follows next week.",
   {"must_include": ["Starting today", "spreadsheet", "Settings page", "iOS and web", "Android version follows next week"], "must_not_include": ["!", "\n\n", "excited"]},
   pos="after", cx=2, note="facts: from today export budget as spreadsheet from Settings; iOS and web now; Android next week (speaker's own statement, not firmed or softened); friendly in wording only ('right from'), no exclamations or feelings")

# 145 diary cleanup with spoken paragraph commands
R2(SF, {"task": "cleanup",
        "transcript": "dear diary comma new paragraph the conference is in nine days and i still haven't finished the slides period the opening is fine but the middle drags period new paragraph arnav watched the run through tonight and said cut the second case study period i think he's right but i love that example period new paragraph tomorrow colon rewrite the middle and time it again period"},
   "Dear diary,\n\nThe conference is in nine days, and I still haven't finished the slides. The opening is fine, but the middle drags.\n\nArnav watched the run-through tonight and said cut the second case study. I think he's right, but I love that example.\n\nTomorrow: rewrite the middle and time it again.",
   {"format": "prose", "min_negations": 1, "must_include": ["Dear diary,", "nine days", "still haven't finished the slides", "Arnav", "second case study", "I think he's right", "Tomorrow:"]},
   cx=0, note="facts: conference in nine days; slides still not finished; middle drags; Arnav said cut second case study; 'I think he's right' hedge + 'I love that example' are the speaker's; spoken comma/period/colon/new paragraph applied; cleanup keeps words")

# 146 explicit prose beats list cue
R2(NM, {"task": "rewrite", "format": "prose",
        "transcript": "the devlog this month covers three things the new save system the fishing minigame and why the release moved to spring"},
   "The devlog this month covers three things: the new save system, the fishing minigame, and why the release moved to spring.",
   {"format": "prose", "must_include": ["three things", "save system", "fishing minigame", "release moved to spring"], "must_not_include": ["- ", "\n"]},
   cx=0, note="facts: three topics; release moved to spring; Format: prose beats the list cue -> one sentence, no bullets")

# 147 post with instructed hashtags only
R2(NL, {"task": "rewrite", "format": "post",
        "instruction": "add the hashtags gamedev and indiedev at the end, nothing else",
        "transcript": "two years ago i quit my job to make a game about a lighthouse keeper today hollow tide has a release date march twelfth on steam and i'm still a little terrified"},
   "Two years ago, I quit my job to make a game about a lighthouse keeper.\n\nToday, Hollow Tide has a release date: March 12, on Steam.\n\nI'm still a little terrified.\n\n#gamedev #indiedev",
   {"format": "post", "numbers": ["12"], "must_include": ["Two years ago", "lighthouse keeper", "Hollow Tide", "March 12", "Steam", "still a little terrified", "#gamedev #indiedev"], "must_not_include": ["!"]},
   pos="after", cx=2, note="facts: quit job two years ago; release date March 12 on Steam; 'still a little terrified' (speaker's feeling, hedge 'a little' kept); exactly the two instructed hashtags, no emoji")

# 148 museum group message, one paragraph
R2(SF, {"task": "rewrite",
        "transcript": "hey all the visitor count for october came in at three thousand four hundred which is our best month since we reopened thank you for covering all those extra saturdays"},
   "Hey all, the visitor count for October came in at 3,400, which is our best month since we reopened. Thank you for covering all those extra Saturdays.",
   {"numbers": ["3,400"], "must_include": ["Hey all", "October", "3,400", "best month since we reopened", "extra Saturdays"], "must_not_include": ["\n"]},
   cx=0, note="facts: October visitors 3,400; best month since reopening; thanks for extra Saturdays (dictated); 'Hey all' dictated; one paragraph")

# 149 formal awards-night speech, no added thank-yous (en-gb)
R2(NL, {"task": "rewrite", "register": "formal", "locale": "en-gb",
        "instruction": "turn this into a short speech for the volunteer awards night and don't add any thank-yous I didn't say",
        "transcript": "um good evening everyone tonight we're recognising the volunteers who kept the station on air this year we had three power cuts a flood in the basement and we still didn't miss a single scheduled broadcast that's down to people like yohan who drove in at two in the morning to restart the transmitter and bhavesh who rebuilt the archive after the flood thank you all"},
   "Good evening, everyone. Tonight we are recognising the volunteers who kept the station on air this year.\n\nWe had three power cuts and a flood in the basement, and we still did not miss a single scheduled broadcast. That is down to people like Yohan, who drove in at 2 in the morning to restart the transmitter, and Bhavesh, who rebuilt the archive after the flood.\n\nThank you all.",
   {"numbers": ["2"], "min_negations": 1, "must_include": ["recognising", "three power cuts", "flood in the basement", "did not miss a single scheduled broadcast", "Yohan", "2 in the morning", "Bhavesh", "rebuilt the archive", "Thank you all."], "must_not_include": ["grateful", "special thanks"]},
   pos="after", cx=2, note="facts: three power cuts + basement flood; still no missed scheduled broadcast (negation); Yohan drove in at 2 a.m. to restart transmitter; Bhavesh rebuilt archive after flood; only the dictated 'thank you all'; formal, en-gb 'recognising'")

# 150 short journal cleanup (en-gb)
R2(SF, {"task": "cleanup", "locale": "en-gb",
        "transcript": "finished the first draft of the family tree it goes back five generations on dad's side but only three on mum's"},
   "Finished the first draft of the family tree. It goes back five generations on Dad's side but only three on Mum's.",
   {"format": "prose", "must_include": ["first draft of the family tree", "five generations on Dad's side", "only three on Mum's"], "must_not_include": ["\n"]},
   cx=0, note="facts: first draft; five generations on Dad's side, only three on Mum's ('only' kept); cleanup keeps words")

# 151 markdown schedule, heading per day (instructed)
R2(NM, {"task": "rewrite", "markup": "markdown",
        "instruction": "give it a heading for each day",
        "transcript": "the weekend schedule saturday breakfast with clem from seven to ten then the local sports roundup with arnav till noon sunday is the folk hour at six and then the request show with ilse at eight"},
   "The weekend schedule:\n\n## Saturday\n\nBreakfast with Clem from 7 to 10, then the local sports roundup with Arnav till noon.\n\n## Sunday\n\nThe folk hour at 6, and then the request show with Ilse at 8.",
   {"numbers": ["7", "10", "6", "8"], "must_include": ["## Saturday", "## Sunday", "Clem from 7 to 10", "Arnav till noon", "folk hour at 6", "request show with Ilse at 8"], "must_not_include": ["- "]},
   pos="after", cx=1, note="facts: Saturday breakfast with Clem 7-10, sports roundup with Arnav till noon; Sunday folk hour at 6, request show with Ilse at 8; lead line kept; headings only because markdown + instruction; no bullets added")

# 152 more direct, reason and hedge kept
R2(NL, {"task": "rewrite", "format": "message",
        "instruction": "more direct, but keep why",
        "transcript": "so um i was kind of wondering if maybe we could move the playtest to saturday because i think more people can make it then"},
   "Can we move the playtest to Saturday? I think more people can make it then.",
   {"format": "message", "must_include": ["move the playtest to Saturday?", "I think more people can make it then"], "must_not_include": ["wondering", "maybe"]},
   pos="after", cx=2, note="facts: proposal to move playtest to Saturday (still a question, not a decision); reason kept with its 'I think' hedge; only the politeness softeners ('kind of wondering if maybe') removed, as instructed")

# 153 long family-history findings -> paragraphs
R2(SF, {"task": "rewrite", "format": "auto",
        "transcript": "notes on grandpa leo's navy years um he joined in nineteen fifty one when he was only seventeen which means he probably lied about his age. his service record says he was posted to cochin for three years and then to bombay. and the funny thing is nobody in the family knew he could swim until aunt rukmini found a medal for a swimming race in his tin box. i still need to request the full record from the archives it takes about six weeks"},
   "Notes on Grandpa Leo's Navy years: he joined in 1951, when he was only 17, which means he probably lied about his age.\n\nHis service record says he was posted to Cochin for three years and then to Bombay.\n\nThe funny thing is, nobody in the family knew he could swim until Aunt Rukmini found a medal for a swimming race in his tin box.\n\nI still need to request the full record from the archives. It takes about six weeks.",
   {"format": "prose", "numbers": ["1951", "17"], "min_negations": 1, "must_include": ["Grandpa Leo", "1951", "only 17", "probably lied about his age", "Cochin for three years", "Bombay", "nobody in the family knew", "Aunt Rukmini", "about six weeks"]},
   cx=0, note="facts: joined Navy 1951 at only 17; 'probably' lied about age (hedge); Cochin three years then Bombay (old city name kept as spoken); nobody knew he could swim until Aunt Rukmini found the medal; full record still to request, about six weeks; topic changes -> paragraphs")

# 154 launch sync notes, condition (en-in)
R2(NM, {"task": "rewrite", "format": "note", "locale": "en-in",
        "transcript": "launch sync notes landing page is live payment gateway approved on the sixth press kit still pending from arnav do not announce the price until pallavi confirms the gst calculation"},
   "Launch sync notes\nLanding page is live.\nPayment gateway approved on the 6th.\nPress kit still pending from Arnav.\nDo not announce the price until Pallavi confirms the GST calculation.",
   {"format": "note", "numbers": ["6"], "min_negations": 1, "must_include": ["Landing page is live", "approved on the 6th", "still pending from Arnav", "Do not announce the price until Pallavi confirms", "GST"]},
   cx=0, note="facts: landing page live; gateway approved on the 6th; press kit still pending (Arnav); do NOT announce price UNTIL Pallavi confirms GST calculation; terse lines")

# 155 blog opening paragraph, wording kept where possible
R2(NL, {"task": "rewrite",
        "instruction": "turn this into the opening paragraph for a blog post, keep my wording as much as possible, one paragraph",
        "transcript": "i've been volunteering at the hillside heritage museum every saturday for three years now and the question i get most is what do you actually do there the honest answer is a bit of everything i greet people i fix the label printer i polish the brass and sometimes i'm the only person who knows where the toilets are"},
   "I've been volunteering at the Hillside Heritage Museum every Saturday for three years now, and the question I get most is: what do you actually do there? The honest answer is a bit of everything. I greet people, I fix the label printer, I polish the brass, and sometimes I'm the only person who knows where the toilets are.",
   {"must_include": ["Hillside Heritage Museum", "every Saturday for three years", "what do you actually do there?", "a bit of everything", "label printer", "polish the brass", "where the toilets are"], "must_not_include": ["\n", "- "]},
   pos="after", cx=3, note="facts: volunteering every Saturday for three years; most common question kept as a question; tasks kept in the speaker's order and words; 'sometimes' hedge kept; one paragraph, no bullets")

# 156 short note with currency (en-gb)
R2(SF, {"task": "rewrite", "format": "note", "locale": "en-gb",
        "transcript": "note bhavesh owes the station forty pounds for the cables"},
   "Bhavesh owes the station £40 for the cables.",
   {"format": "note", "numbers": ["40"], "must_include": ["Bhavesh", "£40", "cables"]},
   cx=0, note="facts: Bhavesh owes the station £40 (pounds spoken) for cables; one terse line")

# 157 shorter, one paragraph, dates and condition kept (en-in)
R2(NL, {"task": "rewrite", "length": "shorter", "locale": "en-in",
        "instruction": "shorter and in one paragraph, keep the dates and the condition",
        "transcript": "hi everyone so the music fundraiser concert that we were planning for the twenty fifth of january is now going to be on the first of february because the auditorium had a double booking um tickets already bought for the old date are still valid so nobody needs to do anything and if someone can't come on the new date they can get a full refund by messaging rukmini before the twentieth of january"},
   "Hi everyone, the music fundraiser concert has moved from January 25 to February 1 because the auditorium had a double booking. Tickets bought for the old date are still valid, so nobody needs to do anything. If you can't come on the new date, you can get a full refund by messaging Rukmini before January 20.",
   {"numbers": ["25", "1", "20"], "min_negations": 2, "must_include": ["January 25", "February 1", "double booking", "still valid", "nobody needs to do anything", "If you can't come on the new date", "full refund", "Rukmini", "before January 20"], "must_not_include": ["\n"]},
   pos="after", cx=3, note="facts: concert moved January 25 -> February 1 (a real change, both dates kept) because of auditorium double booking; old tickets still valid, nobody needs to act; condition: IF you can't come, full refund by messaging Rukmini before January 20; dictated 'hi everyone' kept; visibly shorter")

# 158 playtest notes, counts
R2(SF, {"task": "rewrite", "format": "note",
        "transcript": "playtest notes six testers four finished the demo two got stuck at the bridge puzzle nobody found the secret room and three said the music was too quiet"},
   "Playtest notes\nSix testers; four finished the demo.\nTwo got stuck at the bridge puzzle.\nNobody found the secret room.\nThree said the music was too quiet.",
   {"format": "note", "min_negations": 1, "must_include": ["Six testers", "four finished the demo", "Two got stuck at the bridge puzzle", "Nobody found the secret room", "Three said the music was too quiet"]},
   cx=0, note="facts: six testers; four finished; two stuck at bridge puzzle; nobody found secret room (negation); three said music too quiet; small counts kept as words consistently; terse lines")

# 159 explicit prose, packing items in one sentence
R2(NM, {"task": "rewrite", "format": "prose",
        "transcript": "the things to pack for the archive visit are a pencil because pens aren't allowed the reader's ticket a laptop and the list of box numbers from ilse"},
   "The things to pack for the archive visit are a pencil (pens aren't allowed), the reader's ticket, a laptop, and the list of box numbers from Ilse.",
   {"format": "prose", "min_negations": 1, "must_include": ["archive visit", "pencil", "pens aren't allowed", "reader's ticket", "laptop", "box numbers from Ilse"], "must_not_include": ["- ", "\n"]},
   cx=0, note="facts: pencil because pens aren't allowed (negation kept); reader's ticket; laptop; box-number list from Ilse; explicit Format: prose beats the list cue -> one sentence")

# 160 longer rota notice, nothing new (en-gb)
R2(NL, {"task": "rewrite", "length": "longer", "locale": "en-gb",
        "instruction": "make this longer for the newsletter but keep it to what I said",
        "transcript": "the new volunteer rota is on the noticeboard swaps go through clem"},
   "The new volunteer rota has been put up on the noticeboard for everyone to see. Any swaps to the rota go through Clem.",
   {"must_include": ["new volunteer rota", "noticeboard", "swaps", "Clem"], "must_not_include": ["deadline", "by Friday", "\n"]},
   pos="after", cx=2, note="facts: new rota is on the noticeboard; swaps go through Clem; longer = fuller sentences only, no deadline, reason or feeling added")

# 161 long beta update -> paragraphs, hedges kept
R2(SF, {"task": "rewrite", "header_style": "full",
        "transcript": "so a week into the tallyroom beta here's where we are um about four hundred households signed up and roughly half of them added at least one bill. the biggest complaint is that you can't split a bill unevenly which yeah we know that's coming. the other surprise is how many people use it for trips not flats like a group of friends going to goa. so next sprint uneven splits first and then maybe a trip mode if leo has time"},
   "A week into the Tallyroom beta, here's where we are: about 400 households signed up, and roughly half of them added at least one bill.\n\nThe biggest complaint is that you can't split a bill unevenly. We know, and that's coming.\n\nThe other surprise is how many people use it for trips, not flats, like a group of friends going to Goa.\n\nNext sprint: uneven splits first, and then maybe a trip mode if Leo has time.",
   {"format": "prose", "numbers": ["400"], "min_negations": 2, "must_include": ["A week into the Tallyroom beta", "about 400 households", "roughly half", "at least one bill", "split a bill unevenly", "that's coming", "trips, not flats", "Goa", "maybe a trip mode if Leo has time", "\n\n"]},
   cx=0, note="facts: a week in; about 400 households; roughly half added at least one bill; complaint: can't split unevenly, 'that's coming' (speaker's statement, no date); trips not flats (example Goa friends); next sprint uneven splits first, 'maybe' trip mode IF Leo has time; four topics -> paragraphs")

# 162 markdown header, note, not asked -> plain lines
R2(NM, {"task": "rewrite", "format": "note", "markup": "markdown", "header_style": "full",
        "transcript": "slides to fix slide four has a typo in the title the chart on slide nine needs a source and swap the stock photo on the last slide for our own screenshot"},
   "Slides to fix\nSlide 4 has a typo in the title.\nThe chart on slide 9 needs a source.\nSwap the stock photo on the last slide for our own screenshot.",
   {"format": "note", "numbers": ["4", "9"], "must_include": ["Slides to fix", "Slide 4", "typo in the title", "slide 9 needs a source", "our own screenshot"], "must_not_include": ["**", "#", "- "]},
   cx=0, note="facts: slide 4 title typo; slide 9 chart needs a source; replace last-slide stock photo with own screenshot; markdown allowed but nothing asks for it -> plain terse lines, lead line kept")

# 163 cleanup, one paragraph, words unchanged
R2(NL, {"task": "cleanup",
        "instruction": "keep this as one paragraph and don't change anything I said, just clean it",
        "transcript": "today was quiet at the museum only about fifteen visitors all day but one old man stayed for an hour in the map room and told me his father drew one of the maps on the wall i didn't get his name and i wish i had"},
   "Today was quiet at the museum, only about 15 visitors all day, but one old man stayed for an hour in the map room and told me his father drew one of the maps on the wall. I didn't get his name, and I wish I had.",
   {"format": "prose", "numbers": ["15"], "min_negations": 1, "must_include": ["quiet at the museum", "only about 15 visitors", "an hour in the map room", "his father drew one of the maps", "I didn't get his name", "I wish I had"], "must_not_include": ["\n"]},
   cx=2, note="facts: only about 15 visitors; old man stayed an hour in map room; his father drew one of the maps; didn't get his name (negation); speaker's own regret kept, nothing added; cleanup, one paragraph")

# 164 short patch note
R2(SF, {"task": "rewrite", "format": "post",
        "transcript": "patch one point four is out it fixes the save bug on mac"},
   "Patch 1.4 is out. It fixes the save bug on Mac.",
   {"format": "post", "numbers": ["1.4"], "must_include": ["Patch 1.4", "save bug on Mac"], "must_not_include": ["#", "!"]},
   cx=0, note="facts: patch 1.4 out; fixes save bug on Mac only; no hashtags or added claims")

# 165 donor newsletter section, two short paragraphs (en-in)
R2(NL, {"task": "rewrite", "locale": "en-in",
        "instruction": "make it a newsletter section for our donors, two short paragraphs, keep it plain",
        "transcript": "um this quarter the evening reading classes grew from two centres to five and we now have about a hundred and forty children coming regularly. we're also starting a small lending shelf at each centre so kids can take books home over the weekend but we need donated books in marathi and english"},
   "This quarter, the evening reading classes grew from two centres to five, and we now have about 140 children coming regularly.\n\nWe're also starting a small lending shelf at each centre so kids can take books home over the weekend, but we need donated books in Marathi and English.",
   {"numbers": ["140"], "must_include": ["This quarter", "two centres to five", "about 140 children", "lending shelf", "over the weekend", "Marathi and English", "\n\n"], "must_not_include": ["center", "!"]},
   pos="after", cx=3, note="facts: classes grew from two centres to five this quarter; about 140 children regularly ('about' kept); lending shelf at each centre for weekend borrowing; need donated Marathi and English books; en-in 'centres' consistent; two paragraphs")

# 166 fire-alarm instruction, condition scope clear
R2(SF, {"task": "rewrite",
        "transcript": "if the fire alarm goes off during a tour don't stop to collect bags just take your group out the side door and meet by the bench at the front gate"},
   "If the fire alarm goes off during a tour, don't stop to collect bags; just take your group out the side door and meet by the bench at the front gate.",
   {"min_negations": 1, "must_include": ["If the fire alarm goes off during a tour", "don't stop to collect bags", "side door", "bench at the front gate"], "must_not_include": ["\n", "- "]},
   cx=0, note="facts: condition: if the alarm goes off during a tour -> don't collect bags (negation), take group out side door, meet at bench by front gate; all actions kept inside one sentence so the condition scopes them all")

# 167 excited post, no emoji
R2(NM, {"task": "rewrite", "format": "post", "tone": "excited",
        "transcript": "we're hosting our first ever live broadcast from the town square on the ninth from four till eight come and see the station in action"},
   "We're hosting our first-ever live broadcast from the town square on the 9th, from 4 till 8!\n\nCome and see the station in action.",
   {"format": "post", "numbers": ["9", "4", "8"], "must_include": ["first-ever live broadcast", "town square", "the 9th", "from 4 till 8", "station in action"], "must_not_include": ["#", "**"]},
   cx=0, note="facts: first-ever live broadcast from town square on the 9th, 4 till 8; invitation kept; excited tone allows one exclamation; no emoji/hashtags/added claims")

# 168 dinner speech under 80 words
R2(NL, {"task": "rewrite",
        "instruction": "make it a short speech for the start of the fundraiser dinner, and keep it under 80 words",
        "transcript": "good evening and thank you for coming um tonight's dinner is raising money for the shelter's new kitchen every plate tonight covers a week of breakfasts there's a raffle at nine and the bar is open till eleven please be generous"},
   "Good evening, and thank you for coming.\n\nTonight's dinner is raising money for the shelter's new kitchen, and every plate tonight covers a week of breakfasts.\n\nThere's a raffle at 9, and the bar is open till 11. Please be generous.",
   {"numbers": ["9", "11"], "max_words": 80, "must_include": ["thank you for coming", "shelter's new kitchen", "every plate tonight covers a week of breakfasts", "raffle at 9", "open till 11", "Please be generous"]},
   pos="after", cx=2, note="facts: dinner raises money for shelter's new kitchen; each plate covers a week of breakfasts; raffle at 9; bar till 11; dictated thanks and 'please be generous' only; under 80 words")

# 169 long casual journal -> paragraphs (en-gb)
R2(SF, {"task": "rewrite", "register": "casual", "locale": "en-gb",
        "transcript": "okay it's late but i want to get this down the call with mum went better than i expected we actually talked about the house for once without fighting. she's agreed to think about selling it next year not this year which is fine by me. the other thing is work i got the feedback on the talk and the main note was speak slower which honestly everyone has been telling me for years. tomorrow is a rest day no laptop"},
   "It's late, but I want to get this down. The call with Mum went better than I expected. We actually talked about the house for once without fighting.\n\nShe's agreed to think about selling it next year, not this year, which is fine by me.\n\nThe other thing is work. I got the feedback on the talk, and the main note was to speak slower, which, honestly, everyone has been telling me for years.\n\nTomorrow is a rest day. No laptop.",
   {"format": "prose", "min_negations": 2, "must_include": ["Mum", "better than I expected", "without fighting", "agreed to think about selling it next year, not this year", "speak slower", "for years", "rest day", "No laptop"]},
   cx=0, note="facts: call with Mum went better than expected; talked about the house without fighting; she agreed only to THINK ABOUT selling next year, not this year (not firmed into a decision); feedback: speak slower, heard for years; tomorrow rest day, no laptop; topic changes -> paragraphs")

# 170 markdown bold only the warning (instructed)
R2(NM, {"task": "rewrite", "markup": "markdown",
        "instruction": "bold just the warning",
        "transcript": "for anyone handling the textiles wear the cotton gloves every time do not use the nitrile ones they snag the threads and log every item you move in the blue book"},
   "For anyone handling the textiles: wear the cotton gloves every time. **Do not use the nitrile ones; they snag the threads.** Log every item you move in the blue book.",
   {"min_negations": 1, "must_include": ["handling the textiles", "cotton gloves every time", "**Do not use the nitrile ones", "snag the threads", "blue book"], "must_not_include": ["#", "\n"]},
   pos="after", cx=1, note="facts: cotton gloves every time; do NOT use nitrile (they snag threads); log every moved item in the blue book; bold only the warning because instructed, no headings")

# 171 short cleanup with self-correction
R2(SF, {"task": "cleanup",
        "transcript": "the quiz is on the fourteenth no wait fifteenth at the scout hut"},
   "The quiz is on the 15th at the scout hut.",
   {"format": "prose", "numbers": ["15"], "must_include": ["15th", "scout hut"], "must_not_include": ["14th", "fourteenth"]},
   cx=0, note="facts: self-correction applied: 14th -> 15th; scout hut")

# 172 markdown release notes, headings instructed, prose under them
R2(NL, {"task": "rewrite", "markup": "markdown",
        "instruction": "turn this into release notes with a heading for new, fixed and removed",
        "transcript": "for version three point one we added recurring bills and a search bar we fixed the currency symbol showing wrong for euro users and we removed the old onboarding tour"},
   "Release notes for version 3.1\n\n## New\n\nWe added recurring bills and a search bar.\n\n## Fixed\n\nWe fixed the currency symbol showing wrong for euro users.\n\n## Removed\n\nWe removed the old onboarding tour.",
   {"numbers": ["3.1"], "must_include": ["3.1", "## New", "## Fixed", "## Removed", "recurring bills", "search bar", "currency symbol", "euro users", "old onboarding tour"], "must_not_include": ["- "]},
   pos="after", cx=2, note="facts: version 3.1; new: recurring bills, search bar; fixed: wrong currency symbol for euro users; removed: old onboarding tour; three headings because markdown + instruction; no bullets since not asked")

# 173 alternatives kept, two opinions
R2(SF, {"task": "rewrite",
        "transcript": "for the charity auction on air we're thinking either the signed football or the weekend at the cottage as the top prize clem prefers the football i'm leaning towards the cottage"},
   "For the charity auction on air, we're thinking either the signed football or the weekend at the cottage as the top prize. Clem prefers the football; I'm leaning towards the cottage.",
   {"must_include": ["charity auction on air", "either the signed football or the weekend at the cottage", "top prize", "Clem prefers the football", "leaning towards the cottage"], "must_not_include": ["\n", "decided"]},
   cx=0, note="facts: alternative kept: signed football OR cottage weekend as top prize (undecided, 'we're thinking'); Clem prefers football; speaker 'leaning towards' cottage (hedge); framing 'charity auction on air' kept")

# 174 travel notes (en-gb)
R2(NM, {"task": "rewrite", "format": "note", "locale": "en-gb",
        "transcript": "travel notes for edinburgh train at six forty from kings cross seat booked coach c hotel is a ten minute walk from the venue check in after three expenses go to freya not finance"},
   "Travel notes for Edinburgh\nTrain at 6:40 from King's Cross; seat booked in coach C.\nHotel is a 10-minute walk from the venue; check-in after 3.\nExpenses go to Freya, not finance.",
   {"format": "note", "numbers": ["6:40", "10", "3"], "min_negations": 1, "must_include": ["Edinburgh", "6:40", "King's Cross", "coach C", "10-minute walk", "check-in after 3", "Freya, not finance"]},
   cx=0, note="facts: train 6:40 from King's Cross, seat in coach C; hotel 10-minute walk from venue; check-in after 3; expenses to Freya, NOT finance; framing 'travel notes for Edinburgh' kept; terse lines")

# 175 humble LinkedIn post, no hashtags
R2(NL, {"task": "rewrite",
        "instruction": "turn this into a linkedin post but keep it humble, don't make it sound like a big announcement, and no hashtags",
        "transcript": "small update i gave my first talk at the indie dev meetup last night about thirty people came the demo crashed once but i recovered and a couple of people asked for the slides so i'll put them up this week"},
   "Small update: I gave my first talk at the indie dev meetup last night.\n\nAbout 30 people came. The demo crashed once, but I recovered, and a couple of people asked for the slides, so I'll put them up this week.",
   {"format": "post", "numbers": ["30"], "must_include": ["Small update", "first talk", "indie dev meetup", "last night", "About 30 people", "crashed once", "a couple of people", "this week"], "must_not_include": ["#", "!", "thrilled", "honoured"]},
   pos="after", cx=3, note="facts: first talk, indie dev meetup, last night; about 30 people; demo crashed once, recovered; a couple asked for slides; speaker commits to post them this week (spoken); humble, no hashtags or added feelings")

# 176 short cleanup, dates (en-gb)
R2(SF, {"task": "cleanup", "locale": "en-gb",
        "transcript": "museum's closed on the twenty fifth and twenty sixth of december"},
   "Museum's closed on the 25th and 26th of December.",
   {"format": "prose", "numbers": ["25", "26"], "must_include": ["closed", "25th and 26th of December"], "must_not_include": ["\n"]},
   cx=0, note="facts: closed 25th and 26th of December; cleanup keeps the dictated word order")

# 177 formal family-history paragraph, uncertainty marked (en-gb)
R2(NL, {"task": "rewrite", "register": "formal", "locale": "en-gb",
        "instruction": "write this up as a paragraph for the family history booklet and keep anything uncertain marked as uncertain",
        "transcript": "so um great grandma ilse came over from hamburg in nineteen thirty six we think she was about nineteen she worked as a seamstress in leeds and married a man called clem walsh in nineteen forty though we've never found the marriage certificate"},
   "Great-grandmother Ilse came over from Hamburg in 1936. We think she was about 19 at the time. She worked as a seamstress in Leeds and married a man called Clem Walsh in 1940, although we have never found the marriage certificate.",
   {"numbers": ["1936", "19", "1940"], "min_negations": 1, "must_include": ["Ilse", "Hamburg", "1936", "We think she was about 19", "seamstress in Leeds", "Clem Walsh", "1940", "never found the marriage certificate"], "must_not_include": ["\n"]},
   pos="after", cx=3, note="facts: came from Hamburg in 1936; age hedged ('we think', 'about 19'); seamstress in Leeds; married Clem Walsh in 1940; marriage certificate never found (negation, uncertainty kept); formal, one paragraph")

# 178 running log note
R2(SF, {"task": "rewrite", "format": "note",
        "transcript": "week four of couch to 5k ran three times tuesday thursday and sunday knee felt okay except the last run"},
   "Week 4 of Couch to 5K\nRan three times: Tuesday, Thursday, and Sunday.\nKnee felt okay, except on the last run.",
   {"format": "note", "numbers": ["4"], "must_include": ["Week 4", "Couch to 5K", "three times", "Tuesday, Thursday, and Sunday", "except on the last run"]},
   cx=0, note="facts: week 4 of Couch to 5K; ran three times Tue/Thu/Sun; knee okay except the last run (exception kept); terse lines")

# 179 post under plain, how-to with restriction
R2(NM, {"task": "rewrite", "format": "post",
        "transcript": "how to request a song on the show text the word request and the song name to the studio number we read them out at quarter past each hour and we can't play anything with explicit lyrics before nine pm"},
   "How to request a song on the show: text the word \"request\" and the song name to the studio number.\n\nWe read them out at quarter past each hour, and we can't play anything with explicit lyrics before 9 p.m.",
   {"format": "post", "numbers": ["9"], "min_negations": 1, "must_include": ["request a song", "song name to the studio number", "quarter past each hour", "can't play anything with explicit lyrics before 9 p.m."], "must_not_include": ["#", "**", "1. "]},
   cx=0, note="facts: text 'request' + song name to studio number; read out at quarter past each hour; can't play explicit lyrics before 9 p.m. (restriction kept); no invented studio number; plain post, no numbering")

# 180 more polite for the board, one paragraph, consequence kept
R2(NL, {"task": "rewrite",
        "instruction": "make it more polite, it's going to the museum board, but keep it to one paragraph",
        "transcript": "we need a decision on the gift shop prices by the end of the month or we can't order the christmas stock in time"},
   "We need a decision on the gift shop prices by the end of the month, please. Otherwise, we won't be able to order the Christmas stock in time.",
   {"must_include": ["We need a decision on the gift shop prices", "by the end of the month, please", "Otherwise", "won't be able to order the Christmas stock in time"], "must_not_include": ["\n", "if possible"]},
   pos="after", cx=2, note="facts: decision needed by end of month (kept as a need, not softened into an optional favour; politeness via 'please'); otherwise can't order Christmas stock in time (consequence kept); visibly more polite; one paragraph")

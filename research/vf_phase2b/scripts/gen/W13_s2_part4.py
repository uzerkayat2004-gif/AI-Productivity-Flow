# W13 stage 2, part 4 (TC-W13-221..235). Executed by W13.py; uses R2.

# 221 concrete pour order, numbered format, medium, full header
R2({"format": "numbered", "header_style": "full",
    "transcript": "voice note for tomorrow's concrete pour at oak lane the order is pump arrives at six thirty then the first truck at seven then bashir checks the slump before anything's poured and the second truck comes at eight fifteen if the first goes fine"},
   "Tomorrow's concrete pour at Oak Lane:\n1. Pump arrives at 6:30.\n2. First truck at 7.\n3. Bashir checks the slump before anything is poured.\n4. Second truck at 8:15 if the first goes fine.",
   {"format": "numbered", "numbers": ["6:30", "7", "8:15"], "must_include": ["Tomorrow", "concrete pour", "Oak Lane", "Pump", "First truck", "Bashir checks the slump", "before anything is poured", "Second truck", "if the first goes fine"]},
   note="facts: frame = tomorrow's concrete pour at Oak Lane; speaker's order: pump 6:30, first truck 7, Bashir slump check before any pour, second truck 8:15 IF first goes fine")

# 222 festival board meeting, prose format overrides the list cue, en-gb, command after
R2({"format": "prose", "locale": "en-gb",
    "transcript": "so the festival board met yesterday evening rajat hana and ottilie plus me first the board approved the jury fee rise to two hundred and fifty euros which was pending second they turned down the fifth festival day for this year but said we could bring it back next year if a sponsor appears third the board wants a written safeguarding policy before anyone under eighteen volunteers and ottilie is drafting it by the end of january we also talked about moving the festival to april but that's for next year's board not now"},
   "At yesterday evening's festival board meeting (Rajat, Hana, Ottilie and me), the board approved the pending jury fee rise to €250. It turned down the fifth festival day for this year but said we could bring it back next year if a sponsor appears. The board wants a written safeguarding policy before anyone under 18 volunteers; Ottilie is drafting it by the end of January. Moving the festival to April came up, but that's for next year's board, not now.",
   {"format": "prose", "numbers": ["250", "18"], "must_include": ["yesterday evening", "festival board", "Rajat", "Hana", "Ottilie", "jury fee", "turned down the fifth festival day", "next year if a sponsor appears", "safeguarding policy", "end of January", "April", "next year's board, not now"],
    "min_negations": 1},
   pos="after",
   note="facts: frame = yesterday evening's festival board meeting, Rajat/Hana/Ottilie/speaker; approved pending jury fee rise to €250; fifth day turned down this year, could return next year IF sponsor appears; written safeguarding policy required before anyone under 18 volunteers, Ottilie drafts by end Jan; April move is for next year's board, not now. Format prose overrides the first/second/third list cue")

# 223 release readiness, numbered + instruction (speaker's order)
R2({"format": "numbered", "instruction": "numbered points, in the order I said them",
    "transcript": "recap of this afternoon's release readiness call for version four of the booking app with smita elise and gopal um smita confirmed all the critical bugs are closed the release notes are drafted but legal still has to check the refund wording elise will submit to the app store tomorrow morning if legal signs off tonight gopal says the android build is ready but he wants a staged rollout starting at ten percent and we agreed to that the marketing email goes out only after the rollout reaches fifty percent and nobody's sure yet whether we need to warn the bigger customers in advance"},
   "This afternoon's release readiness call for version 4 of the booking app (Smita, Elise, Gopal):\n1. Smita confirmed all the critical bugs are closed.\n2. Release notes are drafted, but legal still has to check the refund wording.\n3. Elise submits to the App Store tomorrow morning if legal signs off tonight.\n4. Gopal says the Android build is ready but wants a staged rollout starting at 10%; we agreed.\n5. The marketing email goes out only after the rollout reaches 50%.\n6. Nobody's sure yet whether we need to warn the bigger customers in advance.",
   {"format": "numbered", "numbers": ["4", "10", "50"], "must_include": ["This afternoon", "release readiness call", "version 4", "booking app", "Smita", "Elise", "Gopal", "critical bugs are closed", "legal still has to check the refund wording", "tomorrow morning if legal signs off tonight", "staged rollout", "we agreed", "only after the rollout reaches 50%", "Nobody's sure yet", "bigger customers"],
    "min_negations": 1},
   cx=2,
   note="facts: frame = this afternoon's release readiness call, booking app v4, Smita/Elise/Gopal; in spoken order: critical bugs closed; notes drafted, legal to check refund wording; Elise submits tomorrow morning IF legal signs off tonight; Android ready, staged rollout from 10% agreed; marketing email ONLY AFTER 50%; open: warn bigger customers in advance?")

# 224 home loan call, note, medium, command after
R2({"format": "note",
    "transcript": "note from the call with the bank this morning the home loan rate goes up to eight point nine percent from next month the emi stays the same but the tenure increases by about seven months and they need the updated salary slip by the fifteenth"},
   "This morning's call with the bank:\nHome loan rate goes up to 8.9% from next month.\nEMI stays the same; tenure increases by about seven months.\nThey need the updated salary slip by the 15th.",
   {"format": "note", "numbers": ["8.9", "15"], "must_include": ["This morning", "call with the bank", "Home loan rate", "next month", "EMI stays the same", "about seven months", "salary slip"]},
   pos="after",
   note="facts: frame = this morning's call with the bank; home loan rate up to 8.9% from next month; EMI same, tenure +~seven months; updated salary slip by 15th")

# 225 inspection prep, auto 'a few things' -> bullets, full header
R2({"header_style": "full",
    "transcript": "right a few things from today's prep meeting with mahima for the food safety inspection the inspection is on thursday the twentieth between ten and twelve we need the temperature logs for the last three months printed and signed mahima's doing that the hand wash sink by the tandoor needs a soap dispenser fitted gopal will do it tomorrow all staff need their food handler cards on them and two of the new people haven't done the course yet so they're not working thursday and we're deep cleaning the walk in on wednesday night after service"},
   "Today's prep meeting with Mahima for the food safety inspection:\n- The inspection is on Thursday the 20th, between 10 and 12.\n- Last three months of temperature logs printed and signed; Mahima is doing that.\n- Soap dispenser to be fitted at the hand wash sink by the tandoor; Gopal does it tomorrow.\n- All staff need their food handler cards on them. Two of the new people haven't done the course yet, so they're not working Thursday.\n- Deep clean of the walk-in on Wednesday night after service.",
   {"format": "bullets", "numbers": ["20", "10", "12"], "must_include": ["Today", "prep meeting", "Mahima", "food safety inspection", "Thursday", "temperature logs", "last three months", "soap dispenser", "Gopal", "tomorrow", "food handler cards", "haven't done the course", "not working Thursday", "walk-in", "Wednesday night"],
    "min_negations": 2},
   note="facts: frame = today's prep meeting with Mahima for food safety inspection; 'a few things' list cue -> bullets; inspection Thu 20th, 10-12; three months of temp logs printed + signed (Mahima); soap dispenser at tandoor sink, Gopal tomorrow; all staff carry food handler cards, two new people haven't done course -> not working Thursday; walk-in deep clean Wed night after service")

# 226 forge migration, deferred decision with three positions, prose
R2({"format": "prose", "header_style": "full",
    "transcript": "so the kestrel maintainers met on saturday to talk about moving from github to a self hosted forge astrid's for it because of the outages last month and wants full control viktor's against he says we'd lose most drive by contributors and he doesn't want to run servers chidi's on the fence we didn't decide we agreed to run a survey of contributors for two weeks and decide at the meeting on the fourteenth and whatever happens we're keeping github as a read only mirror for at least a year"},
   "On Saturday, the Kestrel maintainers met about moving from GitHub to a self-hosted forge. Astrid is for it, because of last month's outages, and wants full control. Viktor is against: he says we'd lose most drive-by contributors, and he doesn't want to run servers. Chidi is on the fence. We didn't decide; we agreed to survey contributors for two weeks and decide at the meeting on the 14th. Whatever happens, GitHub stays as a read-only mirror for at least a year.",
   {"format": "prose", "numbers": ["14"], "must_include": ["Saturday", "Kestrel maintainers", "self-hosted forge", "Astrid is for it", "last month's outages", "full control", "Viktor is against", "drive-by contributors", "doesn't want to run servers", "Chidi is on the fence", "didn't decide", "agreed to survey contributors for two weeks", "read-only mirror", "at least a year"],
    "min_negations": 2},
   note="facts: frame = Saturday's Kestrel maintainers meeting on GitHub -> self-hosted forge; Astrid for (last month's outages, full control); Viktor against (lose drive-by contributors, doesn't want servers); Chidi on fence; NOT decided; two-week contributor survey, decide on 14th; regardless, GitHub read-only mirror for at least a year")

# 227 tuition next-week plan, bullets, medium
R2({"format": "bullets",
    "transcript": "plan for next week at brightpath from today's chat with astrid the class nine science test moves to tuesday the lab session is cancelled because the kits haven't come back and astrid covers chidi's maths batch on thursday"},
   "Next week at Brightpath (today's chat with Astrid):\n- Class 9 science test moves to Tuesday.\n- Lab session cancelled; the kits haven't come back.\n- Astrid covers Chidi's maths batch on Thursday.",
   {"format": "bullets", "numbers": ["9"], "must_include": ["Next week", "Brightpath", "today's chat with Astrid", "science test", "Tuesday", "Lab session cancelled", "kits haven't come back", "Chidi's maths batch", "Thursday"],
    "min_negations": 1},
   note="facts: frame = next week at Brightpath, from today's chat with Astrid; Class 9 science test -> Tuesday; lab session cancelled (kits not back); Astrid covers Chidi's maths batch Thursday")

# 228 anaemia screening call, note + instruction, command after
R2({"format": "note", "instruction": "terse note, keep the conditions exactly",
    "transcript": "notes from the call with the district health officer's team this afternoon with faisal about the anaemia screening for adolescent girls they'll send two lab technicians for three days in january but only if we arrange transport from the block office and a room with electricity they need a list of names with ages by the twentieth we can screen about a hundred and fifty girls a day the iron tablets are free from the government but we have to collect them ourselves from the district store faisal wants a female volunteer at every session and nobody has told the anganwadi workers yet mahima will do that this week"},
   "This afternoon's call with the district health officer's team, with Faisal, on anaemia screening for adolescent girls:\nThey'll send two lab technicians for three days in January, but only if we arrange transport from the block office and a room with electricity.\nThey need a list of names with ages by the 20th.\nWe can screen about 150 girls a day.\nIron tablets are free from the government, but we collect them ourselves from the district store.\nFaisal wants a female volunteer at every session.\nAnganwadi workers not told yet; Mahima does that this week.",
   {"format": "note", "numbers": ["20", "150"], "must_include": ["This afternoon", "district health officer's team", "Faisal", "anaemia screening", "adolescent girls", "two lab technicians", "three days in January", "only if we arrange transport from the block office and a room with electricity", "names with ages", "Iron tablets are free", "collect them ourselves", "female volunteer at every session", "not told yet", "Mahima"],
    "min_negations": 1},
   cx=2, pos="after",
   note="facts: frame = this afternoon's call with district health officer's team, with Faisal, anaemia screening for adolescent girls; two lab techs, three days in Jan, ONLY IF we arrange transport from block office AND a room with electricity (both conditions kept); names with ages by 20th; ~150 girls/day; iron tablets free, we collect from district store; Faisal wants female volunteer every session; anganwadi workers not told, Mahima this week")

# 229 cricket treasurer update, prose, amount correction
R2({"transcript": "right so cricket league treasurer update from faisal at tonight's meeting we've got four thousand six hundred in the bank membership fees brought in two thousand eight hundred sorry three thousand two hundred this season the ground hire for the season is one thousand five hundred and we still owe the umpires six hundred for the last four matches the new nets cost nine hundred which we agreed to buy in march not now faisal wants to keep at least one thousand in reserve at all times and the club dinner is self funded at twenty five a head"},
   "At tonight's meeting, Faisal gave the cricket league treasurer update: we have 4,600 in the bank, and membership fees brought in 3,200 this season. Ground hire for the season is 1,500, and we still owe the umpires 600 for the last four matches. We agreed to buy the new nets, at 900, in March, not now. Faisal wants to keep at least 1,000 in reserve at all times. The club dinner is self-funded at 25 a head.",
   {"numbers": ["4,600", "3,200", "1,500", "600", "900", "1,000", "25"], "must_include": ["tonight's meeting", "Faisal", "cricket league treasurer update", "membership fees", "ground hire", "still owe the umpires", "last four matches", "new nets", "March, not now", "at least 1,000 in reserve", "self-funded"],
    "must_not_include": ["2,800"], "min_negations": 1},
   note="facts: frame = tonight's meeting, Faisal's cricket league treasurer update; 4,600 in bank; fees 3,200 (2,800 corrected away); ground hire 1,500; owe umpires 600 for last four matches; nets 900 agreed for March not now; Faisal wants >=1,000 reserve always; dinner self-funded 25/head; no currency spoken")

# 230 physio plan change, medium, full header
R2({"header_style": "full",
    "transcript": "hana changed my shoulder plan at today's session drop the pendulum swings add the heavier band rows twelve reps three sets and if i can lift my arm above my head without pain by the twentieth she'll sign me off"},
   "Today's session: Hana changed my shoulder plan. Drop the pendulum swings; add heavier band rows, 12 reps, 3 sets. If I can lift my arm above my head without pain by the 20th, she'll sign me off.",
   {"numbers": ["12", "3", "20"], "must_include": ["today's session", "Hana", "shoulder plan", "Drop the pendulum swings", "heavier band rows", "If I can lift my arm above my head without pain", "sign me off"],
    "min_negations": 1},
   note="facts: frame = today's physio session, Hana changed shoulder plan; drop pendulum swings; add heavier band rows 12 reps x 3 sets; IF arm overhead without pain by 20th -> she signs speaker off")

# 231 team offsite debrief, bullets, en-gb
R2({"format": "bullets", "locale": "en-gb",
    "transcript": "debrief of the team offsite in the lake district last week with rajat smita and elise the venue was great but the wifi was terrible so the planning session ran two hours over the total cost came to four thousand one hundred pounds which is three hundred over budget mostly because of the extra night smita booked for the people coming from aberdeen we agreed the q two goals are the payments launch and cutting support tickets by twenty percent rajat wants to do the next one in september but elise thinks a city venue would be cheaper and we haven't picked one and everyone has to submit receipts by friday"},
   "Last week's team offsite in the Lake District with Rajat, Smita and Elise:\n- The venue was great, but the wifi was terrible, so the planning session ran two hours over.\n- Total cost: £4,100, £300 over budget, mostly because of the extra night Smita booked for the people coming from Aberdeen.\n- Agreed Q2 goals: the payments launch and cutting support tickets by 20%.\n- Rajat wants the next one in September; Elise thinks a city venue would be cheaper. We haven't picked one.\n- Everyone submits receipts by Friday.",
   {"format": "bullets", "numbers": ["4,100", "300", "20"], "must_include": ["Last week", "team offsite", "Lake District", "Rajat", "Smita", "Elise", "wifi was terrible", "two hours over", "over budget", "extra night", "Aberdeen", "Q2 goals", "payments launch", "support tickets", "September", "city venue would be cheaper", "haven't picked", "receipts by Friday"],
    "min_negations": 1},
   note="facts: frame = last week's Lake District team offsite with Rajat/Smita/Elise; venue great, wifi terrible, planning ran two hours over; total £4,100, £300 over (mostly Smita's extra night for Aberdeen people; £ on both, same pounds sentence); agreed Q2 goals: payments launch + support tickets -20%; Rajat wants September, Elise thinks city venue cheaper, nothing picked; receipts by Friday")

# 232 service note, medium
R2({"format": "note",
    "transcript": "quick note from this evening's service at saffron lane table nine's birthday cake was forgotten mahima comped their desserts and we're adding cake orders to the pre service board from tomorrow"},
   "This evening's service at Saffron Lane:\nTable 9's birthday cake was forgotten; Mahima comped their desserts.\nFrom tomorrow, cake orders go on the pre-service board.",
   {"format": "note", "numbers": ["9"], "must_include": ["This evening", "Saffron Lane", "birthday cake was forgotten", "Mahima comped their desserts", "From tomorrow", "pre-service board"]},
   note="facts: frame = this evening's service at Saffron Lane; table 9's birthday cake forgotten; Mahima comped desserts; from tomorrow cake orders on pre-service board")

# 233 payment provider call, prose, contract-length correction
R2({"format": "prose",
    "transcript": "okay voice note after the call with our payment provider this morning the transaction fee drops from two point nine percent to two point five percent from january if we commit to a two year contract no wait they said eighteen months not two years the setup fee is waived and they'll move us to a dedicated account manager smita needs to review the contract before anything's signed and rajat wants to compare it with the other provider's quote first so we haven't agreed to anything yet"},
   "After this morning's call with our payment provider: the transaction fee drops from 2.9% to 2.5% from January if we commit to an 18-month contract. The setup fee is waived, and they'll move us to a dedicated account manager. Smita needs to review the contract before anything is signed, and Rajat wants to compare it with the other provider's quote first, so we haven't agreed to anything yet.",
   {"format": "prose", "numbers": ["2.9", "2.5", "18"], "must_include": ["this morning", "payment provider", "transaction fee", "from January", "if we commit", "18-month contract", "setup fee is waived", "dedicated account manager", "Smita", "before anything is signed", "Rajat", "other provider's quote", "haven't agreed to anything yet"],
    "must_not_include": ["two-year", "2-year", "two years"], "min_negations": 1},
   note="facts: frame = this morning's call with payment provider; fee 2.9% -> 2.5% from Jan IF 18-month commitment (two years corrected away); setup fee waived; dedicated account manager; Smita reviews before signing; Rajat compares other quote; nothing agreed yet")

# 234 crash course planning, markdown headings on request
R2({"markup": "markdown", "instruction": "headings for what we decided, who does what, and what's still open",
    "transcript": "summary of saturday's planning meeting for the brightpath summer crash course with chidi astrid and gopal we're running it for four weeks from the fifth of may for class ten students only maths and science three hours a day the fee is four thousand five hundred for the full course with ten percent off for current students we're capping it at forty students chidi does maths astrid does science gopal handles registrations and the poster which needs to be out by the first of april and we haven't decided whether to offer an online option or whether to hire an extra teacher if we go over thirty students"},
   "## What we decided\nSaturday's planning meeting for the Brightpath summer crash course, with Chidi, Astrid and Gopal: four weeks from May 5, Class 10 students only, maths and science, three hours a day. Fee 4,500 for the full course, 10% off for current students; capped at 40 students.\n\n## Who does what\n- Chidi: maths.\n- Astrid: science.\n- Gopal: registrations and the poster (out by April 1).\n\n## Still open\n- Online option?\n- Extra teacher if we go over 30 students?",
   {"numbers": ["5", "10", "4,500", "40", "1", "30"], "must_include": ["## What we decided", "## Who does what", "## Still open", "Saturday", "planning meeting", "Brightpath summer crash course", "Chidi", "Astrid", "Gopal", "four weeks", "Class 10 students only", "three hours a day", "current students", "registrations and the poster", "online option", "extra teacher", "over 30 students"]},
   cx=1,
   note="facts: frame = Saturday's Brightpath summer crash course planning meeting, Chidi/Astrid/Gopal; four weeks from May 5, Class 10 only, maths+science, three hours/day; fee 4,500, 10% off current students; cap 40; Chidi maths, Astrid science, Gopal registrations + poster out by Apr 1; open: online option? extra teacher IF over 30? No currency spoken. Headings asked by instruction")

# 235 cooperative visit, medium, command after
R2({"transcript": "debrief note after the visit to the vansda women's cooperative today with astrid they've sold three hundred and twenty jars of pickle this month up from two hundred they want help with labels and astrid might find a designer for free"},
   "After today's visit to the Vansda women's cooperative with Astrid: they've sold 320 jars of pickle this month, up from 200. They want help with labels, and Astrid might find a designer for free.",
   {"numbers": ["320", "200"], "must_include": ["today", "Vansda women's cooperative", "Astrid", "jars of pickle", "this month", "help with labels", "might find a designer for free"]},
   pos="after",
   note="facts: frame = today's visit to the Vansda women's cooperative with Astrid; 320 jars this month, up from 200; want label help; Astrid 'might' find a free designer (hedge)")

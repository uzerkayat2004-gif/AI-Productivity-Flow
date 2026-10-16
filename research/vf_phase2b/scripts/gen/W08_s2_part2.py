# W08 stage 2, chunk 2: TC-W08-141..180

# 141
E("multi_constraint",
  "so hollis your claim for the cancelled safari tour is almost done we just need the tour operator's cancellation letter on their letterhead by the twenty fifth of this month after that it goes to the claims committee",
  "Dear Hollis,\n\nYour claim for the cancelled safari tour is almost done. All we need now is the tour operator's cancellation letter on their letterhead by the 25th of this month. After that, it goes to the claims committee.",
  instruction="polished and professional, still warm, nothing promised that I didn't say, and the 25th stays exactly as it is",
  nums=["25"], inc=["Hollis", "safari tour", "cancellation letter", "letterhead", "25th of this month", "claims committee"],
  notinc=["approved", "will be paid"], cx=4,
  note="facts: claim almost done; need operator's cancellation letter on letterhead by the 25th of this month (exact); then goes to claims committee; no promise of approval or payment")

# 142
E("email",
  "hey team quick heads up the printer on level two is jammed again so use the one near the pantry until thursday",
  "Hi team,\n\nQuick heads-up: the printer on Level 2 is jammed again, so use the one near the pantry until Thursday.",
  register="casual",
  nums=["2"], inc=["Hi team", "Level 2", "jammed again", "pantry", "until Thursday"],
  note="facts: Level 2 printer jammed 'again' (fact kept); use the one near the pantry until Thursday")

# 143
E("multi_constraint",
  "hi saanvi we apologise for the slow speeds you've been seeing since last week our engineer checked the line and found a faulty splitter in the junction box it was replaced this morning your complaint ticket is c r m seven seven three zero two and it will stay open for forty eight hours so we can monitor the speed",
  "Hi Saanvi,\n\nRegarding the slow speeds since last week, our engineer found a faulty splitter in the junction box and replaced it this morning. Your complaint ticket CRM 77302 will stay open for 48 hours so we can monitor the speed.\n\nBest,\nAndre",
  sender="Andre", length="shorter",
  instruction="trim it, drop the apology, but the ticket number stays exactly",
  nums=["77302", "48"], inc=["Saanvi", "slow speeds", "since last week", "faulty splitter", "junction box", "this morning", "CRM 77302", "48 hours", "Andre"],
  notinc=["apolog", "sorry"], cx=3,
  note="facts: slow speeds since last week (context kept); faulty splitter in junction box, replaced this morning; ticket CRM 77302 stays open 48 hours to monitor speed; dictated apology removed per instruction")

# 144
E("email",
  "dear mr dimitri petrov thank you for your request to port your health policy uh the new insurer will continue your waiting period credit of two years for pre existing conditions but the room rent limit on the new plan is five thousand rupees per day not unlimited like your current plan um the porting form has to reach us at least forty five days before your renewal date which is the fifteenth of january so the last date is the first of december please don't let the current policy lapse in the meantime",
  "Dear Mr. Dimitri Petrov,\n\nThank you for your request to port your health policy. The new insurer will continue your waiting period credit of two years for pre-existing conditions, but the room rent limit on the new plan is ₹5,000 per day, not unlimited like your current plan.\n\nThe porting form has to reach us at least 45 days before your renewal date, which is January 15, so the last date is December 1. Please don't let the current policy lapse in the meantime.\n\nRegards,\nFarah Ali",
  register="formal", locale="en-in", sender="Farah Ali",
  nums=["5,000", "45", "15", "1"], inc=["Dimitri Petrov", "waiting period credit", "two years", "pre-existing", "not unlimited", "at least 45 days", "January 15", "December 1", "lapse", "Farah Ali"],
  neg=2,
  note="facts: 2-year waiting credit continues; room rent limit ₹5,000/day, NOT unlimited; form at least 45 days before renewal (January 15) so last date December 1; DON'T let current policy lapse")

# 145
E("multi_constraint",
  "subject line revised workshop agenda dear andre and lerato the client workshop on the seventeenth will now start at two pm instead of ten am because their cfo is travelling in the morning the venue stays the same",
  "Subject: Revised workshop agenda\n\nDear Andre and Lerato,\n\nThe client workshop on the 17th will now start at 2 p.m. instead of 10 a.m., because their CFO is travelling in the morning. The venue stays the same.\n\nRegards,\nGaurav Malhotra",
  register="formal", sender="Gaurav Malhotra",
  instruction="formal, keep the subject I gave, and don't add any reason beyond what I said",
  nums=["17", "2", "10"], inc=["Subject: Revised workshop agenda", "Andre and Lerato", "2 p.m. instead of 10 a.m.", "CFO is travelling", "venue stays the same", "Gaurav Malhotra"], cx=3,
  note="facts: dictated subject; two recipients; workshop on the 17th now 2 p.m. instead of 10 a.m. (CFO travelling in the morning); venue unchanged")

# 146
E("email",
  "hey vivek your bike's ready you can collect it anytime before eight",
  "Hi Vivek,\n\nYour bike's ready. You can collect it anytime before 8.",
  register="casual",
  nums=["8"], inc=["Hi Vivek", "ready", "before 8"],
  note="facts: bike ready; collect anytime before 8")

# 147
E("multi_constraint",
  "uh i think the final report won't be ready before the twenty eighth because the client still hasn't sent the store level sales data",
  "Hello,\n\nI think the final report won't be ready before the 28th, as the client still hasn't sent the store-level sales data.\n\nRegards,\nSophie Martin",
  register="formal", sender="Sophie Martin",
  instruction="make it more professional but keep the 'I think' and the 'won't be ready before'",
  nums=["28"], inc=["I think", "won't be ready before the 28th", "still hasn't sent", "store-level sales data", "Sophie Martin"], neg=2, cx=2,
  note="facts: hedge 'I think' kept; report won't be ready before the 28th; client 'still' hasn't sent store-level sales data")

# 148
E("email",
  "mrs uma pillai we're sorry to hear your father fell ill during the trip the emergency evacuation cost is covered up to fifty thousand dollars under your plan and our assistance team will call you within the hour",
  "Dear Mrs. Uma Pillai,\n\nWe're sorry to hear that your father fell ill during the trip. The emergency evacuation cost is covered up to $50,000 under your plan, and our assistance team will call you within the hour.",
  register="formal", tone="empathetic",
  nums=["50,000"], inc=["Uma Pillai", "sorry to hear", "father fell ill", "up to $50,000", "assistance team", "within the hour"],
  notinc=["get well", "speedy recovery", "thoughts are with"],
  note="facts: dictated sympathy kept (only that); evacuation covered up to $50,000; assistance team will call within the hour (dictated commitment); empathetic tone adds no wishes")

# 149
E("multi_constraint",
  "thanks for flagging the noise from the phone booth we've added soundproofing panels and moved the booth away from the quiet zone",
  "Hi Joaquín,\n\nThanks for flagging the noise from the phone booth. We've added soundproofing panels and moved the booth away from the quiet zone.\n\nCheers,\nUma",
  recipient="Joaquín", sender="Uma",
  rules=["Always include a subject line.", "Sign off with 'Cheers'."],
  instruction="no subject line this time, it's a reply",
  inc=["Joaquín", "phone booth", "soundproofing panels", "quiet zone", "Cheers", "Uma"], notinc=["Subject"], cx=1,
  note="facts: thanks for flagging booth noise (dictated); soundproofing panels added; booth moved away from quiet zone. Instruction overrides the subject-line rule; the 'Cheers' rule still applies")

# 150
E("email",
  "hello to all the saturday kitchen volunteers um we served two hundred and sixty meals last weekend uh the kitchen will be closed next saturday for a gas line inspection so please don't come in we'll resume on the twenty sixth",
  "Hi Saturday kitchen volunteers,\n\nWe served 260 meals last weekend. The kitchen will be closed next Saturday for a gas line inspection, so please don't come in. We'll resume on the 26th.\n\nBest,\nSaanvi",
  sender="Saanvi",
  nums=["260", "26"], inc=["Saturday kitchen volunteers", "260 meals", "closed next Saturday", "gas line inspection", "don't come in", "26th", "Saanvi"], neg=1,
  note="facts: named audience kept; 260 meals last weekend; closed next Saturday (gas line inspection), DON'T come in; resume on the 26th")

# 151
E("multi_constraint",
  "hi sophie your single trip policy for the japan trip is active the policy number is t r seven seven one three and it covers you from the third to the nineteenth of next month including adventure sports but excluding scuba diving",
  "Hi Sophie,\n\nYour single-trip policy for the Japan trip is active. The policy number is TR 7731, and it covers you from the 3rd to the 19th of next month, including adventure sports but excluding scuba diving.",
  facts="correct",
  instruction="the policy number ends in 7731, not 7713, fix that only",
  nums=["7731", "3", "19"], inc=["Sophie", "single-trip", "Japan", "TR 7731", "adventure sports", "excluding scuba diving"], notinc=["7713"], cx=2,
  note="Facts: correct authorised one change: policy number TR 7713 -> TR 7731. Kept: active; cover 3rd to 19th of next month; adventure sports included; scuba diving excluded")

# 152
E("email",
  "ms meenal our records show the outage in your sector may continue till tomorrow afternoon the fibre repair crew is working on it",
  "Dear Ms. Meenal,\n\nOur records show that the outage in your sector may continue until tomorrow afternoon. The fibre repair crew is working on it.",
  register="formal", locale="en-in",
  inc=["Ms. Meenal", "outage", "may continue", "tomorrow afternoon", "fibre repair crew"], notinc=["restored by"],
  note="facts: outage 'may' continue until tomorrow afternoon (hedge kept, no restore time promised); repair crew working on it")

# 153
E("multi_constraint",
  "hi mr andre just wanted to check in uh the denting and painting work is complete and the car will be handed over on saturday unless the insurance surveyor asks for a second inspection hope that's alright",
  "Hi Mr. Andre,\n\nThe denting and painting work is complete, and the car will be handed over on Saturday unless the insurance surveyor asks for a second inspection.",
  tone="confident",
  instruction="sound more sure of yourself, but the unless part has to stay exactly as I said it",
  inc=["Mr. Andre", "denting and painting", "complete", "Saturday", "unless the insurance surveyor asks for a second inspection"], cx=2,
  note="facts: work complete; handover Saturday UNLESS surveyor asks for a second inspection (kept verbatim); softeners 'just wanted to check in' / 'hope that's alright' removed for confidence")

# 154
E("email",
  "subject change in faculty for organic chemistry then dear students from next monday organic chemistry will be taken by dimitri sir instead of hollis sir the timings remain the same",
  "Subject: Change in faculty for organic chemistry\n\nDear students,\n\nFrom next Monday, organic chemistry will be taken by Dimitri Sir instead of Hollis Sir. The timings remain the same.\n\nRegards,\nSaanvi Kulkarni",
  register="formal", sender="Saanvi Kulkarni",
  inc=["Subject: Change in faculty for organic chemistry", "Dear students", "next Monday", "Dimitri", "instead of Hollis", "timings remain the same", "Saanvi Kulkarni"],
  note="facts: dictated subject; from next Monday organic chemistry by Dimitri Sir instead of Hollis Sir (both kept, it is a replacement); timings unchanged")

# 155
E("multi_constraint",
  "hi farah your dedicated desk renewal is due on the first the monthly charge is going up from nine thousand to nine thousand eight hundred rupees because of the new parking add on and the late fee is five hundred rupees if you pay after the fifth you can pay by upi or bank transfer",
  "Dear Farah,\n\nYour dedicated desk renewal is due on the 1st. The monthly charge is going up from ₹9,000 to ₹9,800 because of the new parking add-on. You can pay by UPI or bank transfer.",
  locale="en-in",
  instruction="professional, keep both monthly charges exactly, and leave out the late fee part",
  nums=["1", "9,000", "9,800"], inc=["Farah", "dedicated desk", "1st", "₹9,000 to ₹9,800", "parking add-on", "UPI or bank transfer"],
  notinc=["late fee", "500", "5th"], cx=3, waivers=["number_missing"],
  note="facts: renewal due the 1st; monthly charge ₹9,000 -> ₹9,800 (parking add-on), ₹ on both since rupees spoken for the pair; pay by UPI or bank transfer (alternative). Instruction drops the late fee sentence (₹500 after the 5th), so number_missing for 500/5 waived")

# 156
E("email",
  "dear donors thank you for helping us buy forty new sewing machines for the women's skills centre the first batch of twenty trainees starts on the eighth warm regards meenal",
  "Dear donors,\n\nThank you for helping us buy 40 new sewing machines for the women's skills centre. The first batch of 20 trainees starts on the 8th.\n\nWarm regards,\nMeenal",
  register="formal",
  nums=["40", "20", "8"], inc=["Dear donors", "40 new sewing machines", "women's skills centre", "20 trainees", "8th", "Warm regards", "Meenal"],
  note="facts: thanks for funding 40 sewing machines; first batch of 20 trainees starts on the 8th; speaker dictated own closing and name 'warm regards meenal' (no [Sender])")

# 157
E("multi_constraint",
  "the claim for the stolen laptop cannot be processed because the police report was not filed within the forty eight hour window and the laptop was not listed in the high value items schedule we will not be able to reopen this claim",
  "Dear Mr. Gaurav Tandon,\n\nThe claim for the stolen laptop cannot be processed because the police report was not filed within the 48-hour window, and the laptop was not listed in the high-value items schedule. We will not be able to reopen this claim.\n\nRegards,\nLerato Mokoena",
  register="formal", recipient="Mr. Gaurav Tandon", sender="Lerato Mokoena",
  instruction="formal, keep every negative, don't soften anything, and no apology",
  nums=["48"], inc=["Gaurav Tandon", "cannot be processed", "not filed within the 48-hour window", "not listed", "high-value items schedule", "will not be able to reopen", "Lerato Mokoena"],
  notinc=["sorry", "apolog", "regret", "unfortunately"], neg=4, cx=4,
  note="facts: 4 negations (cannot be processed; police report not filed within 48 hours; laptop not listed in high-value schedule; will not be able to reopen); no apology or softener added")

# 158
E("email",
  "can we push our sync to four thirty i'm stuck in the client workshop",
  "Hi Lerato,\n\nCan we push our sync to 4:30? I'm stuck in the client workshop.\n\nBest,\nVivek",
  recipient="Lerato", sender="Vivek",
  nums=["4:30"], inc=["Lerato", "sync", "4:30", "client workshop", "Vivek"],
  note="facts: request to push sync to 4:30 (question); stuck in client workshop")

# 159
E("multi_constraint",
  "hi ms saanvi joshi your car's insurance claim is with the surveyor and approval usually takes three to five working days so delivery might be around the twentieth but that's not confirmed yet",
  "Subject: Status of your car insurance claim\n\nDear Ms. Saanvi Joshi,\n\nYour car's insurance claim is with the surveyor, and approval usually takes 3 to 5 working days. Delivery might be around the 20th, but that is not confirmed yet.",
  locale="en-in",
  instruction="add a subject about the claim status, formal, and don't make the delivery date sound certain",
  nums=["3", "5", "20"], inc=["Subject:", "Saanvi Joshi", "surveyor", "usually", "might be around the 20th", "not confirmed yet"],
  notinc=["will be delivered on"], neg=1, cx=3, waivers=["invented_subject"],
  note="facts: claim with surveyor; approval 'usually' 3 to 5 working days; delivery 'might be around' the 20th, NOT confirmed yet. Subject requested by instruction (invented_subject waived)")

# 160
E("email",
  "hey gaurav and uma so for the clothes donation drive next weekend uh gaurav can you handle the pickup van it's booked from nine to one and uma can you set up the sorting tables at the community hall um we got about thirty bags from the housing society already and they're in the store room oh and we're not accepting shoes this time because we have no space so if people bring them please politely say no",
  "Hi Gaurav and Uma,\n\nFor the clothes donation drive next weekend, Gaurav, can you handle the pickup van? It's booked from 9 to 1. Uma, can you set up the sorting tables at the community hall?\n\nWe've already got about 30 bags from the housing society, and they're in the store room. We're not accepting shoes this time because we have no space, so if people bring them, please politely say no.",
  register="casual",
  nums=["9", "1", "30"], inc=["Gaurav and Uma", "pickup van", "sorting tables", "community hall", "about 30 bags", "store room", "not accepting shoes"], neg=2,
  note="facts: two recipients each with own task (Gaurav: pickup van booked 9 to 1; Uma: sorting tables at community hall); about 30 bags already in store room; NOT accepting shoes (no space), politely say no")

# 161
E("multi_constraint",
  "hey everyone so from november all members need to switch to the new access app uh the old cards will stop working on the fifteenth of november at midnight download link is in the welcome email you got last week",
  "Hello everyone,\n\nFrom November, all members need to switch to the new access app. The old cards will stop working at midnight on November 15. You'll find the download link in the welcome email you received last week.",
  instruction="make this a professional email but keep it friendly, don't add any promises, and preserve the exact deadline",
  nums=["15"], inc=["Hello everyone", "November", "new access app", "midnight on November 15", "welcome email", "last week"],
  notinc=["help you", "assist"], cx=4,
  note="facts: switch to new access app from November; old cards stop at midnight on November 15 (exact deadline); download link in last week's welcome email; professional -> 'Hello everyone,' (dictated audience kept); no promise added")

# 162
E("email",
  "this is to confirm that the policy for the group of twelve travellers to vietnam has been issued the premium of ninety six thousand rupees has been received in full",
  "Hello,\n\nThis is to confirm that the policy for the group of 12 travellers to Vietnam has been issued. The premium of ₹96,000 has been received in full.\n\nRegards,\nJoaquín Fernandes",
  register="formal", locale="en-in", sender="Joaquín Fernandes",
  nums=["12", "96,000"], inc=["12 travellers", "Vietnam", "issued", "₹96,000", "in full", "Joaquín Fernandes"],
  note="facts: group policy for 12 travellers to Vietnam issued; premium ₹96,000 received in full")

# 163
E("multi_constraint",
  "hi hollis the steering deck is in the shared folder i've marked the slides that need your input in yellow please don't edit the appendix it's locked for the client",
  "Hi Hollis,\n\nThe steering deck is in the shared folder. I've marked the slides that need your input in yellow. Please don't edit the appendix; it's locked for the client.",
  wording="keep",
  instruction="make it an email but don't change my words, just fix the punctuation",
  inc=["Hi Hollis", "steering deck", "shared folder", "in yellow", "don't edit the appendix", "locked for the client"], neg=1, cx=2,
  note="facts: deck in shared folder; slides needing input marked yellow; DON'T edit the appendix (locked for client); wording kept, only punctuation/capitals")

# 164
E("email",
  "your request to shift the connection to your new address in whitefield has been approved the shifting charge is five hundred rupees and the technician will visit on the twenty third between eleven and four",
  "Dear Mr. Vivek Iyer,\n\nYour request to shift the connection to your new address in Whitefield has been approved. The shifting charge is ₹500, and the technician will visit on the 23rd between 11 and 4.",
  register="formal", locale="en-in", recipient="Mr. Vivek Iyer",
  nums=["500", "23", "11", "4"], inc=["Vivek Iyer", "Whitefield", "approved", "₹500", "23rd", "between 11 and 4"],
  note="facts: shifting request to Whitefield approved; charge ₹500; technician visit on the 23rd between 11 and 4")

# 165
E("multi_constraint",
  "hi mrs farah the balance fee for ayaan is six thousand sorry sixteen thousand rupees and it's due before the mock test series starts on the tenth",
  "Dear Mrs. Farah,\n\nAyaan's balance fee of ₹16,000 is due before the mock test series starts on the 10th.",
  register="formal", locale="en-in", length="shorter",
  instruction="polite, keep it short, and use the corrected figure",
  nums=["16,000", "10"], inc=["Mrs. Farah", "Ayaan", "₹16,000", "before the mock test series", "10th"], notinc=["₹6,000"], cx=3,
  note="facts: self-correction six thousand -> ₹16,000 applied; due BEFORE the mock test series starts on the 10th")

# 166
E("email",
  "hi andre hi meenal both your cars are booked for the free monsoon check up on saturday andre at ten and meenal at eleven thirty",
  "Hi Andre and Meenal,\n\nBoth your cars are booked for the free monsoon check-up on Saturday: Andre at 10 and Meenal at 11:30.",
  nums=["10", "11:30"], inc=["Andre and Meenal", "free monsoon check-up", "Saturday", "Andre at 10", "Meenal at 11:30"],
  note="facts: two recipients; free monsoon check-up Saturday: Andre 10, Meenal 11:30 (times not swapped)")

# 167
E("multi_constraint",
  "the color scheme for the dashboard is finalized we're not changing the program names until the client signs off",
  "Hi,\n\nThe color scheme for the dashboard is finalized. We're not changing the program names until the client signs off.\n\nBest wishes,\nSophie",
  sender="Sophie",
  rules=["Use British spelling.", "Sign off with 'Best wishes'."],
  instruction="American spelling for this one since it's for the US office, and keep the not",
  inc=["color scheme", "finalized", "not changing the program names", "until the client signs off", "Best wishes", "Sophie"],
  notinc=["colour", "finalised", "programme"], neg=1, cx=2,
  note="facts: dashboard color scheme finalized; NOT changing program names until client signs off. Instruction overrides the British-spelling rule; the 'Best wishes' rule still applies")

# 168
E("email",
  "hey dimitri locker forty two is yours from tomorrow the key's at the front desk",
  "Hi Dimitri,\n\nLocker 42 is yours from tomorrow. The key's at the front desk.",
  register="casual",
  nums=["42"], inc=["Hi Dimitri", "Locker 42", "from tomorrow", "front desk"],
  note="facts: locker 42 from tomorrow; key at front desk")

# 169
E("multi_constraint",
  "okay reply to mr hollis grant about his trip interruption claim um he had to come back early from dubai because of a family medical emergency uh the policy covers the unused hotel nights and either the change fee on his original return ticket or a new one way ticket whichever is lower we need the treating doctor's letter and the hotel's cancellation confirmation and if the hotel refunded any nights those won't be paid again the claim form must reach us within thirty days of his return which was on the fourth so by the fourth of next month",
  "Dear Mr. Hollis Grant,\n\nRegarding your trip interruption claim for your early return from Dubai due to a family medical emergency, the policy covers the unused hotel nights and either the change fee on your original return ticket or a new one-way ticket, whichever is lower.\n\nWe need the treating doctor's letter and the hotel's cancellation confirmation. If the hotel refunded any nights, those won't be paid again.\n\nThe claim form must reach us within 30 days of your return, which was on the 4th, so by the 4th of next month.\n\nRegards,\nUma",
  register="formal", sender="Uma",
  instruction="formal, keep both ticket options and the condition, and don't add any apology",
  nums=["30", "4"], inc=["Hollis Grant", "Dubai", "unused hotel nights", "either the change fee", "one-way ticket", "whichever is lower", "treating doctor's letter", "If the hotel refunded", "4th of next month", "Uma"],
  notinc=["sorry", "apolog"], neg=1, cx=4,
  note="facts: early return from Dubai (family medical emergency); covers unused hotel nights + EITHER change fee OR new one-way ticket, whichever is lower; need doctor's letter + hotel cancellation; IF hotel refunded nights they won't be paid again; claim form within 30 days of return (the 4th) so by the 4th of next month; no apology")

# 170
E("email",
  "dear ms sophie roux we are pleased to confirm your booking of the conference room for twenty people on friday the ninth from two to six pm the projector and video conferencing kit are included",
  "Dear Ms. Sophie Roux,\n\nWe are pleased to confirm your booking of the conference room for 20 people on Friday the 9th, from 2 to 6 p.m. The projector and video conferencing kit are included.\n\nRegards,\nHollis",
  register="formal", tone="friendly", sender="Hollis",
  nums=["20", "9", "2", "6"], inc=["Sophie Roux", "pleased to confirm", "conference room", "20 people", "Friday the 9th", "projector", "Hollis"],
  note="facts: conference room for 20 people, Friday the 9th, 2 to 6 p.m.; projector + video conferencing kit included; formal + friendly adds nothing")

# 171
E("multi_constraint",
  "hi parents the summer olympiad prep camp runs from the second to the twentieth of may monday to friday four to six pm uh there's a ten percent discount for siblings and registration closes on the twenty fifth of april",
  "Dear parents,\n\nThe summer Olympiad prep camp runs from May 2 to May 20, Monday to Friday, 4 to 6 p.m. Registration closes on April 25.",
  instruction="leave out the sibling discount, keep the dates exact, professional",
  nums=["2", "20", "4", "6", "25"], inc=["Dear parents", "Olympiad prep camp", "May 2 to May 20", "Monday to Friday", "4 to 6 p.m.", "April 25"],
  notinc=["discount", "sibling", "10%"], cx=3, waivers=["number_missing"],
  note="facts: camp May 2 to May 20, Monday-Friday, 4 to 6 p.m.; registration closes April 25. Sibling discount (10%) dropped per instruction, so number_missing for 10 waived")

# 172
E("email",
  "hi uma your electricity bill of two thousand three hundred forty rupees is due on the twelfth you can pay online or at the nearest collection centre",
  "Hi Uma,\n\nYour electricity bill of ₹2,340 is due on the 12th. You can pay online or at the nearest collection centre.",
  locale="en-in",
  nums=["2,340", "12"], inc=["Hi Uma", "₹2,340", "12th", "online or at the nearest collection centre"],
  note="facts: bill ₹2,340 due on the 12th; pay online OR at collection centre")

# 173
E("multi_constraint",
  "um so i was thinking we might be able to bring the pilot forward to the first week of march if the vendor delivers the sensors early what do you think",
  "Hi Dimitri,\n\nWe might be able to bring the pilot forward to the first week of March if the vendor delivers the sensors early. What do you think?\n\nBest,\nFarah",
  tone="confident", recipient="Dimitri", sender="Farah",
  instruction="more confident, cut the filler, but keep the might and the if",
  inc=["Dimitri", "might", "first week of March", "if the vendor delivers the sensors early", "What do you think?", "Farah"], cx=3,
  note="facts: 'might' bring pilot forward to first week of March, ONLY if vendor delivers sensors early; question kept; 'I was thinking' filler-framing dropped")

# 174
E("email",
  "dear mr gaurav kapoor this is regarding your complaint about the vibration in the steering after the last service uh our workshop manager inspected the car yesterday and found that the wheel balancing was not done properly the rework will be done free of charge on monday and it should take about two hours um since the car is under the extended warranty the replacement of the front left tie rod is also covered but the alignment charge of eight hundred rupees is not part of the warranty so that will be billed separately",
  "Dear Mr. Gaurav Kapoor,\n\nThis is regarding your complaint about the vibration in the steering after the last service. Our workshop manager inspected the car yesterday and found that the wheel balancing was not done properly. The rework will be done free of charge on Monday, and it should take about 2 hours.\n\nSince the car is under the extended warranty, the replacement of the front left tie rod is also covered. However, the alignment charge of ₹800 is not part of the warranty, so it will be billed separately.\n\nRegards,\nAndre D'Souza",
  register="formal", locale="en-in", sender="Andre D'Souza",
  nums=["2", "800"], inc=["Gaurav Kapoor", "vibration in the steering", "wheel balancing was not done properly", "free of charge on Monday", "about 2 hours", "front left tie rod", "₹800", "billed separately", "Andre D'Souza"],
  neg=2,
  note="facts: inspected yesterday; wheel balancing NOT done properly; free rework Monday, 'should take about' 2 hours; front left tie rod covered (extended warranty); ₹800 alignment NOT under warranty, billed separately")

# 175
E("multi_constraint",
  "hey sorry to bug you but um could you maybe let the customers in block c know the fibre migration is probably happening around the end of the month and their old router won't work after that",
  "Hi customers in Block C,\n\nThe fibre migration is probably happening around the end of the month, and your old router won't work after that.",
  instruction="more direct, cut the politeness fluff, but keep 'probably' and 'around'",
  inc=["Block C", "probably", "around the end of the month", "old router won't work"], notinc=["sorry"], neg=1, cx=3,
  note="facts: named audience (customers in Block C) kept; migration 'probably' 'around' end of month (hedges kept); old router won't work after; speaker's 'sorry to bug you' was aimed at the colleague, not dictated content, and is removed")

# 176
E("email",
  "dear sir or madam we are writing to request a donation of fifty used laptops for our digital literacy centre in pune",
  "Dear Sir or Madam,\n\nWe are writing to request a donation of 50 used laptops for our digital literacy centre in Pune.\n\nRegards,\nMeenal Rao",
  register="formal", sender="Meenal Rao",
  nums=["50"], inc=["Dear Sir or Madam", "50 used laptops", "digital literacy centre", "Pune", "Meenal Rao"],
  note="facts: request for 50 used laptops for digital literacy centre in Pune; dictated formal greeting kept")

# 177
E("multi_constraint",
  "hi vivek the weekend spoken english batch starts on the seventeenth and the fee is twenty five thousand rupees for three months classes are on saturdays and sundays from ten to twelve",
  "Hi Vivek,\n\nThe weekend spoken English batch starts on the 7th, and the fee is ₹2,500 for three months. Classes are on Saturdays and Sundays from 10 to 12.",
  facts="correct", locale="en-in",
  instruction="two fixes: it starts on the 7th, not the 17th, and the fee is 2,500 rupees, not 25,000. Leave the rest",
  nums=["7", "2,500", "10", "12"], inc=["Vivek", "spoken English", "7th", "₹2,500", "three months", "Saturdays and Sundays", "10 to 12"],
  notinc=["17th", "25,000"], cx=2,
  note="Facts: correct authorised exactly two named changes: 17th -> 7th and ₹25,000 -> ₹2,500. Kept: three months; Saturdays and Sundays 10 to 12")

# 178
E("email",
  "hi farah quick question about your claim did you pay the clinic in euros or with your indian card because we need the bank statement showing the conversion rate",
  "Hi Farah,\n\nA quick question about your claim: did you pay the clinic in euros or with your Indian card? We need the bank statement showing the conversion rate.",
  inc=["Hi Farah", "in euros or with your Indian card", "bank statement", "conversion rate"],
  note="facts: question kept as a question with both alternatives (euros OR Indian card); need bank statement with conversion rate")

# 179
E("multi_constraint",
  "hey lerato the yoga session on the roof is at seven no wait at six thirty tomorrow morning mats are provided just bring water",
  "Hi Lerato,\n\nThe yoga session on the roof is at 6:30 tomorrow morning. Mats are provided, so all you need to bring is water.\n\nCheers,\nSaanvi",
  register="casual", tone="friendly",
  instruction="friendlier, and sign it from me, Saanvi",
  nums=["6:30"], inc=["Lerato", "roof", "6:30 tomorrow morning", "Mats are provided", "water", "Saanvi"], notinc=["at 7"], cx=2,
  note="facts: self-correction seven -> 6:30 applied; tomorrow morning on the roof; mats provided, bring water. Sign-off name authorised by the instruction")

# 180
E("email",
  "the client has asked us not to contact their regional managers directly all interview requests must go through their hr head ms uma sen",
  "Hi,\n\nThe client has asked us not to contact their regional managers directly. All interview requests must go through their HR head, Ms. Uma Sen.\n\nBest,\nJoaquín",
  sender="Joaquín",
  inc=["not to contact their regional managers directly", "All interview requests", "HR head", "Uma Sen", "Joaquín"], neg=1,
  note="facts: client asked us NOT to contact regional managers directly; ALL interview requests via HR head Ms. Uma Sen")

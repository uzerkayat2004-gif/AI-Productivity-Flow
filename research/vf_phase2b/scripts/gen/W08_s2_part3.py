# W08 stage 2, chunk 3: TC-W08-181..220

# 181
E("multi_constraint",
  "sorry about the wait your refund request r f nine zero four one is now being processed",
  "Hi,\n\nYour refund request RF 9041 is now being processed.",
  length="shorter",
  instruction="shorter, no apology, keep the reference number",
  nums=["9041"], inc=["RF 9041", "being processed"], notinc=["sorry", "apolog", "wait"], cx=3, pos="before",
  note="facts: refund request RF 9041 now being processed (no completion date promised); dictated apology removed per instruction")

# 182
E("email",
  "hi koramangala members so a few updates for november um first the new phone booths are installed on the ground floor and can be booked through the app for thirty minutes at a time second the terrace will be closed from the tenth to the fourteenth for waterproofing work and third we're starting a monthly founders breakfast on the first friday of every month it's free for members but guests pay three hundred rupees uh also please remember the building doesn't allow smoking anywhere including the parking",
  "Hi Koramangala members,\n\nA few updates for November. First, the new phone booths are installed on the ground floor and can be booked through the app for 30 minutes at a time. Second, the terrace will be closed from the 10th to the 14th for waterproofing work. Third, we're starting a monthly founders' breakfast on the first Friday of every month. It's free for members, but guests pay ₹300.\n\nAlso, please remember that the building doesn't allow smoking anywhere, including the parking.\n\nBest,\nDimitri",
  locale="en-in", sender="Dimitri",
  nums=["30", "10", "14", "300"], inc=["Koramangala members", "November", "phone booths", "30 minutes at a time", "terrace", "waterproofing", "founders' breakfast", "first Friday", "free for members", "₹300", "doesn't allow smoking", "Dimitri"],
  neg=1,
  note="facts: named audience; phone booths on ground floor, bookable via app 30 min at a time; terrace closed 10th to 14th (waterproofing); monthly founders' breakfast first Friday, free for members, guests ₹300; no smoking anywhere incl. parking. Kept as prose (format email, ordinal cues kept)")

# 183
E("multi_constraint",
  "only the account holder can request a sim swap",
  "Hello,\n\nOnly the account holder can request a SIM swap.",
  instruction="make it formal and keep the only",
  inc=["Hello", "Only the account holder", "SIM swap"], cx=2,
  note="facts: restriction kept: ONLY the account holder can request a SIM swap; formal, no name -> 'Hello,'")

# 184
E("multi_constraint",
  "okay so this is for the parents of the class twelve commerce batch um the board exam crash course will run from the third of january to the twenty eighth of february uh classes are monday wednesday friday from four to seven and saturday mornings are for mock tests uh we'll have three full length mock papers on the eleventh the eighteenth and the twenty fifth of february and the results will be shared on the parents' whatsapp group within two days of each test uh students who miss a mock test can't take it later because the papers are discussed in class the same week",
  "Dear parents of the Class 12 commerce batch,\n\nThe board exam crash course will run from January 3 to February 28. Classes are on Monday, Wednesday and Friday from 4 to 7, and Saturday mornings are for mock tests.\n\nThere will be three full-length mock papers, on February 11, 18 and 25, and the results will be shared on the parents' WhatsApp group within two days of each test.\n\nStudents who miss a mock test can't take it later, because the papers are discussed in class the same week.",
  locale="en-in",
  instruction="turn this into a formal email to the parents, keep it friendly, keep every date, and don't add anything about refunds",
  nums=["12", "3", "28", "4", "7", "11", "18", "25"], inc=["Class 12 commerce batch", "January 3", "February 28", "Monday, Wednesday and Friday", "Saturday mornings", "three full-length mock papers", "WhatsApp group", "within two days", "can't take it later"],
  notinc=["refund"], neg=1, cx=4, pos="before",
  note="facts: Class 12 commerce; course January 3 to February 28; Mon/Wed/Fri 4 to 7; Saturday mornings mock tests; three mocks February 11, 18, 25; results on parents' WhatsApp within two days; missed mock CAN'T be taken later (discussed in class same week); nothing about refunds")

# 185
E("email",
  "your car's due for its forty thousand kilometre service next week",
  "Hi Uma,\n\nYour car is due for its 40,000 km service next week.",
  recipient="Uma",
  nums=["40,000"], inc=["Hi Uma", "40,000 km service", "next week"],
  note="facts: 40,000 km service due next week")

# 186
E("multi_constraint",
  "the investor demo day is in hall d at five",
  "Hi,\n\nThe investor demo day is in Hall B at 5.",
  facts="correct",
  instruction="it's Hall B, not Hall D",
  nums=["5"], inc=["investor demo day", "Hall B", "at 5"], notinc=["Hall D"], cx=1,
  note="Facts: correct authorised one change: Hall D -> Hall B. Time 5 kept")

# 187
E("multi_constraint",
  "hi sophie and dimitri um so update from the client meeting this morning they've agreed to extend the project by four weeks but the budget stays at the original eighteen lakh so we need to reduce the number of site visits from twelve to eight uh sophie can you redo the visit plan by thursday and dimitri can you update the resourcing sheet um they also don't want any changes to the final presentation date which is still the ninth of december thanks andre",
  "Hi Sophie and Dimitri,\n\nAn update from the client meeting this morning: they've agreed to extend the project by four weeks, but the budget stays at the original 18 lakh, so we need to reduce the number of site visits from 12 to 8. Sophie, can you redo the visit plan by Thursday? Dimitri, can you update the resourcing sheet?\n\nThey also don't want any changes to the final presentation date, which is still December 9.\n\nThanks,\nAndre",
  locale="en-in",
  rules=["Use British spelling."],
  instruction="keep both names in the greeting, keep it neutral, and don't add any next steps I didn't say",
  nums=["18", "12", "8", "9"], inc=["Sophie and Dimitri", "this morning", "four weeks", "18 lakh", "from 12 to 8", "by Thursday", "resourcing sheet", "don't want any changes", "December 9", "Andre"],
  notinc=["₹"], neg=1, cx=3, waivers=["number_missing", "number_invented"],
  note="facts: client meeting this morning; project extended four weeks; budget stays at original 18 lakh (no currency spoken, so no ₹); site visits 12 -> 8; Sophie redoes visit plan by Thursday; Dimitri updates resourcing sheet; NO changes to final presentation date, still December 9; speaker dictated own sign-off 'thanks andre'. Waiver: checker reads spoken 'eighteen lakh' as 1800000 while the target writes '18 lakh' as spoken")

# 188
E("email",
  "kindly share your passport copy and ticket to process the claim",
  "Hello,\n\nKindly share your passport copy and ticket so that we can process the claim.\n\nRegards,\nFarah Siddiqui",
  register="formal", sender="Farah Siddiqui",
  inc=["Hello", "passport copy", "ticket", "process the claim", "Farah Siddiqui"],
  note="facts: request for passport copy + ticket to process the claim; formal, no recipient -> 'Hello,'")

# 189
E("multi_constraint",
  "the volunteer meetup is at six at the park gate bring a friend if you like",
  "Hi,\n\nThe volunteer meetup is at 6 at the park gate. You're welcome to bring a friend if you like.",
  tone="friendly",
  instruction="friendly, keep it under 25 words, keep the time",
  nums=["6"], inc=["volunteer meetup", "at 6", "park gate", "bring a friend if you like"], maxw=25, cx=3,
  note="facts: meetup at 6 at the park gate; bringing a friend is optional ('if you like')")

# 190
E("email",
  "dear mrs saanvi bhatt regarding your application for a new three phase connection for your shop um the site inspection was done on the second and the load requirement of fifteen kilowatts has been approved uh the security deposit is twelve thousand rupees and the connection charges are four thousand five hundred rupees both have to be paid before the meter can be installed uh once payment is received the meter will be installed within seven working days please note that the wiring inside the shop must be certified by a licensed electrician otherwise the meter cannot be energised",
  "Dear Mrs. Saanvi Bhatt,\n\nRegarding your application for a new three-phase connection for your shop, the site inspection was done on the 2nd, and the load requirement of 15 kW has been approved.\n\nThe security deposit is ₹12,000 and the connection charges are ₹4,500. Both have to be paid before the meter can be installed. Once payment is received, the meter will be installed within 7 working days.\n\nPlease note that the wiring inside the shop must be certified by a licensed electrician; otherwise, the meter cannot be energised.\n\nRegards,\nGaurav Singh",
  register="formal", locale="en-in", sender="Gaurav Singh",
  nums=["2", "15", "12,000", "4,500", "7"], inc=["Saanvi Bhatt", "three-phase", "15 kW", "₹12,000", "₹4,500", "before the meter can be installed", "Once payment is received", "licensed electrician", "otherwise", "cannot be energised", "Gaurav Singh"],
  neg=1,
  note="facts: three-phase connection; inspection on the 2nd; 15 kW load approved; deposit ₹12,000 + connection ₹4,500, both BEFORE installation; install within 7 working days ONCE paid; wiring must be certified, OTHERWISE meter cannot be energised.")

# 191
E("multi_constraint",
  "hopefully the replacement router reaches you by tuesday",
  "Hello,\n\nHopefully, the replacement router will reach you by Tuesday.",
  instruction="more formal, but keep the hopefully",
  inc=["Hello", "Hopefully", "replacement router", "Tuesday"], notinc=["will definitely"], cx=2,
  note="facts: hedge 'hopefully' kept; replacement router by Tuesday (not promised)")

# 192
E("multi_constraint",
  "so sorry but we don't have a loaner car free this week",
  "Hi,\n\nWe don't have a loaner car free this week.",
  length="shorter",
  instruction="shorter, take out the apology, and keep the don't",
  inc=["don't have a loaner car", "this week"], notinc=["sorry", "apolog", "unfortunately"], neg=1, cx=3, pos="before",
  note="facts: no loaner car free this week (negation kept); dictated apology removed per instruction")

# 193
E("email",
  "hi batch b students the doubt clearing session for trigonometry is moved from wednesday to thursday same time four pm in room six",
  "Hi Batch B students,\n\nThe doubt-clearing session for trigonometry has moved from Wednesday to Thursday, same time, 4 p.m., in Room 6.",
  nums=["4", "6"], inc=["Batch B students", "trigonometry", "from Wednesday to Thursday", "same time", "4 p.m.", "Room 6"],
  note="facts: named audience kept; trigonometry doubt session moved Wednesday -> Thursday (a move, both days kept); same time 4 p.m.; Room 6")

# 194
E("multi_constraint",
  "thank you for choosing our student travel plan for your masters in canada um the plan covers medical expenses up to one hundred thousand canadian dollars and study interruption if you have to return home for medical reasons um it does not cover routine eye tests or pre existing conditions unless they are declared and accepted at the time of purchase uh the cover starts only once you board your flight to canada not on the purchase date and you need to keep a copy of your university enrolment letter in case of a claim",
  "Dear Ms. Farah Mirza,\n\nThank you for choosing our student travel plan for your master's in Canada. The plan covers medical expenses up to 100,000 Canadian dollars, and study interruption if you have to return home for medical reasons.\n\nIt does not cover routine eye tests or pre-existing conditions unless they are declared and accepted at the time of purchase. The cover starts only once you board your flight to Canada, not on the purchase date.\n\nPlease keep a copy of your university enrolment letter in case of a claim.\n\nRegards,\nVivek Menon",
  register="formal", tone="friendly", recipient="Ms. Farah Mirza", sender="Vivek Menon",
  instruction="formal but friendly, keep every condition, and don't add an offer to help",
  nums=["100,000"], inc=["Farah Mirza", "student travel plan", "Canada", "100,000 Canadian dollars", "study interruption", "does not cover", "unless they are declared and accepted", "only once you board", "not on the purchase date", "enrolment letter", "Vivek Menon"],
  notinc=["happy to help", "feel free", "reach out"], neg=2, cx=3,
  note="facts: medical up to 100,000 Canadian dollars; study interruption IF return home for medical reasons; NOT covering eye tests or pre-existing UNLESS declared and accepted at purchase; cover starts ONLY once you board, NOT on purchase date; keep enrolment letter for claims; no offer added")

# 195
E("email",
  "tell joaquín the invoice he asked for is attached",
  "Hi Joaquín,\n\nThe invoice you asked for is attached.",
  inc=["Hi Joaquín", "invoice", "attached"],
  note="facts: recipient named in transcript; invoice he asked for is attached (dictated)")

# 196
E("multi_constraint",
  "your parking sticker for the basement is ready at reception",
  "Hi,\n\nYour parking sticker for the basement is ready at reception.\n\nBest,\nMeenal",
  sender="Meenal",
  rules=["Always end with 'Thanks in advance'.", "Keep emails short."],
  instruction="drop the thanks in advance line, I'm not asking for anything",
  inc=["parking sticker", "basement", "reception", "Meenal"], notinc=["Thanks in advance"], cx=1,
  note="facts: basement parking sticker ready at reception. Instruction overrides the 'Thanks in advance' rule; 'keep short' rule still applies; normal neutral sign-off with [Sender]")

# 197
E("multi_constraint",
  "hi mr hollis about your office broadband plan uh your current plan is one hundred mbps for two thousand four hundred rupees a month and you're using about eighty percent of it during peak hours so we suggest moving to the three hundred mbps plan at three thousand six hundred rupees a month um there's no installation charge for the upgrade but the static ip will cost an extra two hundred rupees a month oh and i heard your old router is giving trouble so we can swap it for free if you want",
  "Dear Mr. Hollis,\n\nRegarding your office broadband plan, your current plan is 100 Mbps for ₹2,400 a month, and you're using about 80% of it during peak hours. We suggest moving to the 300 Mbps plan at ₹3,600 a month.\n\nThere is no installation charge for the upgrade, but the static IP will cost an extra ₹200 a month.",
  locale="en-in",
  instruction="professional, keep all the prices, and leave out the router part",
  nums=["100", "2,400", "80", "300", "3,600", "200"], inc=["Mr. Hollis", "100 Mbps", "₹2,400", "about 80%", "300 Mbps", "₹3,600", "no installation charge", "static IP", "₹200"],
  notinc=["router", "swap"], neg=1, cx=3,
  note="facts: current 100 Mbps ₹2,400/month, using about 80% at peak; suggest 300 Mbps ₹3,600/month; NO installation charge; static IP extra ₹200/month. Router swap offer dropped per instruction")

# 198
E("email",
  "hey saanvi did you get the keys to cabin nine",
  "Hi Saanvi,\n\nDid you get the keys to Cabin 9?",
  register="casual",
  nums=["9"], inc=["Hi Saanvi", "keys", "Cabin 9"],
  note="facts: question kept as a question; Cabin 9")

# 199
E("multi_constraint",
  "if it's not too much trouble we can match the competitor's price if you share their written quote",
  "Hi,\n\nWe can match the competitor's price if you share their written quote.",
  tone="confident",
  instruction="rewrite it confidently but keep the condition",
  inc=["match the competitor's price", "if you share their written quote"], cx=2, waivers=["negation_lost"],
  note="facts: price match ONLY if customer shares the competitor's written quote; politeness softener 'if it's not too much trouble' removed for confidence (its 'not' is not a fact, so negation_lost waived)")

# 200
E("email",
  "subject line flood relief update um hi all supporters so our team reached two villages near the river yesterday and distributed about four hundred ration kits each kit has rice dal oil and salt for a family of four for a week uh we still need tarpaulin sheets and drinking water the road to the third village is still cut off so we might go by boat on saturday if the district office allows it um donations are being accepted only through the website not in cash",
  "Subject: Flood relief update\n\nHi supporters,\n\nOur team reached two villages near the river yesterday and distributed about 400 ration kits. Each kit has rice, dal, oil and salt for a family of four for a week.\n\nWe still need tarpaulin sheets and drinking water. The road to the third village is still cut off, so we might go by boat on Saturday if the district office allows it.\n\nDonations are being accepted only through the website, not in cash.",
  locale="en-in",
  nums=["400"], inc=["Subject: Flood relief update", "supporters", "two villages", "yesterday", "about 400 ration kits", "family of four", "tarpaulin sheets", "still cut off", "might go by boat", "if the district office allows it", "only through the website", "not in cash"],
  neg=1,
  note="facts: dictated subject; two villages yesterday, about 400 kits (rice, dal, oil, salt; family of four, one week); still need tarpaulins + water; third village road still cut off; 'might' go by boat Saturday IF district office allows; donations ONLY via website, NOT cash.")

# 201
E("multi_constraint",
  "the scholarship test fee is two hundred rupees",
  "Hi,\n\nThe scholarship test fee is ₹250.",
  facts="correct", locale="en-in",
  instruction="the fee is 250, not 200",
  nums=["250"], inc=["scholarship test fee", "₹250"], notinc=["₹200"], cx=1,
  note="Facts: correct authorised one change: ₹200 -> ₹250")

# 202
E("multi_constraint",
  "hello farah the inventory audit at the pune plant starts on tuesday no wait wednesday the fifth uh the team will be lerato vivek and hollis sorry not hollis uma because hollis is on leave um we'll need access to the warehouse from seven am and a meeting room for the full week uh please also arrange safety shoes in sizes eight nine and ten",
  "Subject: Inventory audit schedule\n\nDear Farah,\n\nThe inventory audit at the Pune plant starts on Wednesday the 5th. The team will be Lerato, Vivek and Uma, because Hollis is on leave.\n\nWe will need access to the warehouse from 7 a.m. and a meeting room for the full week. Please also arrange safety shoes in sizes 8, 9 and 10.",
  instruction="formal, apply my corrections, and add a subject line about the audit schedule",
  nums=["5", "7", "8", "9", "10"], inc=["Subject:", "Dear Farah", "Pune plant", "Wednesday the 5th", "Lerato, Vivek and Uma", "Hollis is on leave", "warehouse", "7 a.m.", "full week", "sizes 8, 9 and 10"],
  notinc=["Tuesday"], cx=3, waivers=["invented_subject", "negation_lost"],
  note="facts: self-corrections applied: Tuesday -> Wednesday the 5th; team member Hollis -> Uma (Hollis on leave, reason kept); warehouse access from 7 a.m.; meeting room for the full week; safety shoes sizes 8, 9, 10. Subject requested by instruction (invented_subject waived); the 'not' in 'sorry not hollis' is part of the self-correction, so negation_lost waived")

# 203
E("email",
  "your claim has been approved and the amount will be credited within five working days",
  "Dear Mr. Dimitri Volkov,\n\nYour claim has been approved, and the amount will be credited within 5 working days.",
  register="formal", recipient="Mr. Dimitri Volkov",
  nums=["5"], inc=["Dimitri Volkov", "approved", "within 5 working days"],
  note="facts: claim approved; credit within 5 working days (dictated)")

# 204
E("multi_constraint",
  "lunch order today is biryani or paneer wrap reply by twelve",
  "Hi,\n\nToday's lunch order is biryani or paneer wrap. Reply by 12.",
  register="casual",
  instruction="keep it casual and keep both options",
  nums=["12"], inc=["biryani or paneer wrap", "Reply by 12"], cx=2,
  note="facts: alternative kept: biryani OR paneer wrap; reply by 12")

# 205
E("email",
  "hi meenal um so regarding the accident repair on your suv uh the insurance company has approved the claim but there's a compulsory deductible of two thousand rupees plus the depreciation on plastic and rubber parts which comes to around six thousand seven hundred so your total out of pocket will be about eight thousand seven hundred rupees uh the parts are expected on friday and if they arrive on time the car should be ready by next tuesday we'll call you before final billing",
  "Hi Meenal,\n\nRegarding the accident repair on your SUV, the insurance company has approved the claim, but there's a compulsory deductible of ₹2,000 plus the depreciation on plastic and rubber parts, which comes to around ₹6,700. Your total out-of-pocket cost will be about ₹8,700.\n\nThe parts are expected on Friday, and if they arrive on time, the car should be ready by next Tuesday. We'll call you before final billing.\n\nBest,\nUma",
  locale="en-in", sender="Uma",
  nums=["2,000", "6,700", "8,700"], inc=["Meenal", "SUV", "approved", "compulsory deductible", "around ₹6,700", "about ₹8,700", "expected on Friday", "if they arrive on time", "should be ready by next Tuesday", "before final billing", "Uma"],
  note="facts: claim approved; deductible ₹2,000 + depreciation around ₹6,700 = about ₹8,700 out of pocket (₹ applied to all three, rupees spoken for the first and the total); parts expected Friday; car 'should' be ready by next Tuesday ONLY IF parts arrive on time; will call before final billing (dictated)")

# 206
E("multi_constraint",
  "please send me the latest attendance sheet by evening",
  "Hi,\n\nPlease send me the latest attendance sheet by evening.",
  sender="Vivek",
  instruction="don't sign it, I'll add my own signature",
  inc=["latest attendance sheet", "by evening"], notinc=["Vivek", "Best,"], cx=1,
  note="facts: request for latest attendance sheet by evening. Instruction overrides the [Sender] sign-off, so no closing or name")

# 207
E("email",
  "hi gaurav the annual maintenance contract for the ac units expires on the thirtieth",
  "Hi Gaurav,\n\nThe annual maintenance contract for the AC units expires on the 30th.",
  nums=["30"], inc=["Hi Gaurav", "annual maintenance contract", "AC units", "30th"],
  note="facts: AMC for AC units expires on the 30th")

# 208
E("multi_constraint",
  "um hi mr andre about your rooftop solar net metering application uh the bidirectional meter might take two to three weeks to arrive because there's a shortage from the supplier the inspection fee of one thousand five hundred rupees has been received um until the new meter is installed the units you export won't be credited so maybe keep the export limited for now uh we'll inform you as soon as the meter is dispatched",
  "Hi Mr. Andre,\n\nRegarding your rooftop solar net metering application, the bidirectional meter might take 2 to 3 weeks to arrive because of a shortage at the supplier. We have received the inspection fee of ₹1,500.\n\nUntil the new meter is installed, the units you export won't be credited, so maybe keep the export limited for now. We'll inform you as soon as the meter is dispatched.",
  locale="en-in", tone="confident",
  instruction="confident tone, don't drop any maybe or might, and keep the amounts",
  nums=["2", "3", "1,500"], inc=["Mr. Andre", "net metering", "bidirectional meter", "might take 2 to 3 weeks", "shortage", "₹1,500", "Until the new meter is installed", "won't be credited", "maybe keep the export limited", "as soon as the meter is dispatched"],
  neg=1, cx=3,
  note="facts: meter 'might' take 2 to 3 weeks (supplier shortage); ₹1,500 inspection fee received; exported units WON'T be credited until meter installed; 'maybe' keep export limited (hedged suggestion); will inform when dispatched (dictated)")

# 209
E("multi_constraint",
  "the client call is moved to friday please update the tracker",
  "Hi Uma and Hollis,\n\nThe client call is moved to Friday. Please update the tracker.",
  wording="keep",
  instruction="make it an email to Uma and Hollis but keep my words",
  inc=["Hi Uma and Hollis", "client call is moved to Friday", "update the tracker"], cx=2,
  note="facts: two recipients from the instruction; call moved to Friday; update the tracker; wording kept")

# 210
E("email",
  "dear ms lerato ngcobo we are happy to inform you that your daughter has qualified for a fifty percent scholarship in the foundation programme the offer letter will be emailed to you by the end of this week",
  "Dear Ms. Lerato Ngcobo,\n\nWe are happy to inform you that your daughter has qualified for a 50% scholarship in the Foundation Programme. The offer letter will be emailed to you by the end of this week.",
  register="formal",
  nums=["50"], inc=["Lerato Ngcobo", "happy to inform", "50% scholarship", "Foundation Programme", "offer letter", "end of this week"],
  note="facts: daughter qualified for 50% scholarship in Foundation Programme; offer letter by end of this week (dictated); 'happy to inform' dictated")

# 211
E("multi_constraint",
  "yo the new access cards should be ready by monday so hang tight",
  "Hello,\n\nThe new access cards should be ready by Monday, so please bear with us until then.",
  instruction="more formal, but keep the should",
  inc=["Hello", "new access cards", "should be ready by Monday"], notinc=["will be ready"], cx=2,
  note="facts: cards 'should' be ready by Monday (hedge kept); 'hang tight' rendered formally as a request to wait")

# 212
E("email",
  "hey hollis cabin keys are with security cheers saanvi",
  "Hi Hollis,\n\nThe cabin keys are with security.\n\nCheers,\nSaanvi",
  register="casual",
  inc=["Hi Hollis", "cabin keys", "security", "Cheers", "Saanvi"],
  note="facts: cabin keys with security; speaker dictated own sign-off 'cheers saanvi' (no [Sender])")

# 213
E("multi_constraint",
  "dear hr team um from the next policy year which starts on the first of april the group health cover will no longer include parents as dependants uh employees who want to cover their parents can buy a separate top up plan at their own cost um maternity cover stays the same at seventy five thousand rupees but the waiting period of nine months will not be waived for new joiners anymore uh enrolment changes have to be submitted by the fifteenth of march and no changes will be accepted after that",
  "Subject: Changes to the group health policy from April 1\n\nDear HR team,\n\nFrom the next policy year, which starts on April 1, the group health cover will no longer include parents as dependants. Employees who want to cover their parents can buy a separate top-up plan at their own cost.\n\nMaternity cover stays the same at ₹75,000, but the waiting period of 9 months will no longer be waived for new joiners.\n\nEnrolment changes have to be submitted by March 15, and no changes will be accepted after that.\n\nRegards,\nLerato Khumalo",
  locale="en-in", sender="Lerato Khumalo",
  instruction="formal, keep every negative, keep both dates, and add a subject line about the policy change",
  nums=["1", "75,000", "9", "15"], inc=["Subject:", "Dear HR team", "April 1", "no longer include parents", "top-up plan", "at their own cost", "₹75,000", "9 months", "no longer be waived", "March 15", "no changes will be accepted"],
  neg=3, cx=4, waivers=["invented_subject"],
  note="facts: from policy year starting April 1 parents NO LONGER covered; separate top-up at own cost; maternity unchanged ₹75,000; 9-month waiting period NO LONGER waived for new joiners; enrolment changes by March 15, NO changes after. Subject requested by instruction (invented_subject waived)")

# 214
E("multi_constraint",
  "reception closes at eight thirty tonight",
  "Hi,\n\nA quick note that reception closes at 8:30 tonight.",
  tone="friendly",
  instruction="make it friendlier and keep the exact time",
  nums=["8:30"], inc=["reception closes", "8:30 tonight"], cx=2,
  note="facts: reception closes at 8:30 tonight; friendlier framing only, no new facts")

# 215
E("email",
  "dear mr vivek anand um this email is to formally close the operating model project uh all four deliverables the current state assessment the target design the implementation roadmap and the training materials were accepted by your team on the twenty ninth of october uh the final invoice for the remaining twenty percent of fees will be sent separately by our finance team um the knowledge transfer sessions are complete but we have not handed over the raw interview notes because they contain personal information as agreed in the contract",
  "Dear Mr. Vivek Anand,\n\nThis email is to formally close the operating model project. All four deliverables, the current state assessment, the target design, the implementation roadmap and the training materials, were accepted by your team on October 29.\n\nThe final invoice for the remaining 20% of fees will be sent separately by our finance team.\n\nThe knowledge transfer sessions are complete, but we have not handed over the raw interview notes because they contain personal information, as agreed in the contract.\n\nRegards,\nLerato Ndlovu",
  register="formal", sender="Lerato Ndlovu",
  nums=["29", "20"], inc=["Vivek Anand", "operating model project", "All four deliverables", "current state assessment", "target design", "implementation roadmap", "training materials", "October 29", "remaining 20%", "finance team", "have not handed over the raw interview notes", "as agreed in the contract", "Lerato Ndlovu"],
  neg=1,
  note="facts: project formally closed; all four deliverables (current state assessment, target design, implementation roadmap, training materials) accepted October 29; final invoice for remaining 20% sent separately by finance; KT complete; raw interview notes NOT handed over (personal info, as agreed in contract)")

# 216
E("multi_constraint",
  "the car wash camp is on sunday from nine",
  "Hi,\n\nThe car wash camp is on Saturday from 9.",
  facts="correct",
  instruction="it's on Saturday, not Sunday",
  nums=["9"], inc=["car wash camp", "Saturday", "from 9"], notinc=["Sunday"], cx=1,
  note="Facts: correct authorised one change: Sunday -> Saturday; from 9 kept")

# 217
E("email",
  "hi andre the deposit for your desk has been refunded to your card",
  "Hi Andre,\n\nThe deposit for your desk has been refunded to your card.",
  inc=["Hi Andre", "deposit", "desk", "refunded to your card"],
  note="facts: desk deposit refunded to card")

# 218
E("multi_constraint",
  "hi farah welcome to the weekend coding club for kids um classes are every saturday from ten to twelve at the koramangala centre and kids need to bring their own laptop with at least eight gb ram uh there's a free trial class for siblings on the first saturday of every month um if your child misses two classes in a row we'll share the recordings but we can't hold makeup sessions uh and please make sure someone picks them up by twelve fifteen because we can't keep children after that",
  "Hi Farah,\n\nWelcome to the Weekend Coding Club for Kids. Classes are every Saturday from 10 to 12 at the Koramangala centre, and kids need to bring their own laptop with at least 8 GB RAM.\n\nIf your child misses two classes in a row, we'll share the recordings, but we can't hold make-up sessions. Please make sure someone picks them up by 12:15, as we can't keep children after that.",
  tone="warm",
  instruction="drop the part about the free trial, keep it warm, and keep the conditions",
  nums=["10", "12", "8", "12:15"], inc=["Farah", "Welcome", "Weekend Coding Club for Kids", "every Saturday from 10 to 12", "Koramangala", "at least 8 GB RAM", "If your child misses two classes in a row", "can't hold make-up sessions", "12:15", "can't keep children after that"],
  notinc=["free trial", "sibling"], neg=2, cx=3, waivers=["number_missing"],
  note="facts: Saturdays 10 to 12 at Koramangala centre; own laptop with at least 8 GB RAM; IF two classes missed in a row -> recordings, but CAN'T hold make-up sessions; pick up by 12:15, CAN'T keep children after. Sibling free-trial sentence dropped per instruction (its 'first Saturday' = 1 absent: number_missing waived)")

# 219
E("email",
  "dear sir please note our office will remain closed on the second of october for gandhi jayanti",
  "Dear Sir,\n\nPlease note that our office will remain closed on October 2 for Gandhi Jayanti.",
  register="formal", locale="en-in",
  nums=["2"], inc=["Dear Sir", "remain closed", "October 2", "Gandhi Jayanti"],
  note="facts: office closed October 2 for Gandhi Jayanti; dictated formal greeting kept")

# 220
E("multi_constraint",
  "i'm not sure if this helps but we can approve the extension of your policy for another two weeks provided you send the new return ticket before your current cover ends on the eighteenth",
  "Hi,\n\nWe can approve the extension of your policy for another two weeks, provided you send the new return ticket before your current cover ends on the 18th.",
  tone="confident",
  instruction="rewrite with a more confident tone but keep the conditional part word for word",
  nums=["18"], inc=["approve the extension", "another two weeks", "provided you send the new return ticket before your current cover ends on the 18th"], cx=2, waivers=["negation_lost"],
  note="facts: two-week extension approvable PROVIDED new return ticket arrives before cover ends on the 18th (condition kept word for word); speaker's 'I'm not sure if this helps' softener removed for confidence (it hedges the helpfulness of the note, not the fact; negation_lost waived)")

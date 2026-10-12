# W08 stage 2, chunk 1: TC-W08-101..140 (exec'd by W08.py; E() queues one record)

# 101
E("email",
  "let mr hollis know his travel insurance covers trip delays over six hours but not missed connections",
  "Hi Mr. Hollis,\n\nYour travel insurance covers trip delays over 6 hours but not missed connections.",
  nums=["6"], inc=["Mr. Hollis", "trip delays", "missed connections"], neg=1,
  note="facts: covers delays over 6 hours; NOT missed connections (negation kept); recipient named in transcript")

# 102
E("multi_constraint",
  "hi parents of the class ten maths batch um the fee for the december revision crash course is three thousand two hundred rupees and it has to be paid by the eighteenth of november uh seats are limited to twenty five per batch and we'll share the timetable once the batches are fixed",
  "Dear parents of the Class 10 maths batch,\n\nHere are the details for the December revision crash course. The fee is ₹3,200 and has to be paid by November 18. Seats are limited to 25 per batch, and we'll share the timetable once the batches are fixed.",
  locale="en-in",
  instruction="make this a professional email but keep it friendly, don't add any promises, and keep the exact deadline",
  nums=["10", "3,200", "18", "25"], inc=["Class 10 maths batch", "December revision crash course", "November 18", "once the batches are fixed"],
  notinc=["guarantee", "don't hesitate"], cx=4,
  note="facts: Class 10 maths batch; ₹3,200; deadline November 18 kept exactly; 25 seats per batch; timetable shared ONCE batches are fixed (dictated, conditional); professional -> 'Dear'; no added promise")

# 103
E("email",
  "um so this goes to all the hot desk members at the andheri hub the wifi upgrade is happening this saturday from eight am to noon so the internet will be patchy during that window uh the meeting rooms on the top floor are not affected and the coffee machine will be fixed by monday",
  "Hi hot desk members,\n\nThe Wi-Fi upgrade at the Andheri hub is happening this Saturday from 8 a.m. to noon, so the internet will be patchy during that window. The meeting rooms on the top floor are not affected, and the coffee machine will be fixed by Monday.\n\nBest,\nDimitri",
  sender="Dimitri",
  nums=["8"], inc=["hot desk members", "Andheri hub", "Saturday", "noon", "top floor", "coffee machine", "Monday", "Dimitri"], neg=1,
  note="facts: named audience 'hot desk members' kept in greeting; Wi-Fi upgrade Saturday 8 a.m. to noon; meeting rooms NOT affected; coffee machine fixed by Monday (dictated)")

# 104
E("multi_constraint",
  "hi mr vivek rao sorry for the delay uh your car's service job card number is j c four four nine one the brake pads have been replaced and we found the rear tyres are worn down to about two millimetres so we recommend replacing them but we haven't done that without your approval the car will be ready for pickup after five pm today",
  "Hi Mr. Vivek Rao,\n\nYour job card number is JC 4491. The brake pads have been replaced. The rear tyres are worn down to about 2 mm, so we recommend replacing them, but we haven't done that without your approval. The car will be ready for pickup after 5 p.m. today.",
  instruction="shorter, no apology, keep the reference number",
  length="shorter",
  nums=["4491", "2", "5"], inc=["JC 4491", "brake pads", "about 2 mm", "without your approval", "after 5 p.m. today"],
  notinc=["sorry", "apolog", "delay"], neg=1, cx=3,
  note="facts: job card JC 4491 kept; brake pads replaced; rear tyres about 2 mm, replacement recommended but NOT done without approval; ready after 5 p.m. today; dictated 'sorry for the delay' removed per instruction; 'shorter' drops 'we found' / 'car's service'")

# 105
E("email",
  "regarding the medical expenses claim from your bali trip uh we have received the clinic bills and the prescription but the passport copy with the entry stamp is still missing once that comes in the reimbursement of sixty two thousand rupees should probably reach you within ten working days",
  "Dear Ms. Saanvi Mehta,\n\nRegarding the medical expenses claim from your Bali trip, we have received the clinic bills and the prescription, but the passport copy with the entry stamp is still missing. Once that comes in, the reimbursement of ₹62,000 should probably reach you within 10 working days.\n\nRegards,\nLerato",
  register="formal", locale="en-in", recipient="Ms. Saanvi Mehta", sender="Lerato",
  nums=["62,000", "10"], inc=["Saanvi Mehta", "Bali", "clinic bills", "passport copy", "entry stamp", "still missing", "Once", "probably", "Lerato"],
  note="facts: received clinic bills + prescription; passport copy with entry stamp still missing; ₹62,000 'should probably' arrive within 10 working days ONCE passport copy comes in (condition + hedge kept)")

# 106
E("multi_constraint",
  "the board pack for the paper mill review goes out wednesday noon not tuesday please send your section to hollis by monday six pm",
  "Hello,\n\nThe board pack for the paper mill review goes out at noon on Wednesday, not Tuesday. Please send your section to Hollis by 6 p.m. on Monday.\n\nRegards,\nJoaquín",
  register="formal", sender="Joaquín",
  rules=["Always sign off with 'Cheers'.", "Never use exclamation marks."],
  instruction="formal this time, sign off with Regards",
  nums=["6"], inc=["paper mill review", "Wednesday", "not Tuesday", "Hollis", "Monday", "Regards", "Joaquín"], notinc=["Cheers", "!"], neg=1, cx=2,
  note="facts: board pack goes out Wednesday noon, NOT Tuesday; section to Hollis by 6 p.m. Monday. Instruction 'Regards' overrides the 'Cheers' rule; the no-exclamation rule still applies")

# 107
E("email",
  "subject meeting room booking changes then hi all starting the first of next month meeting rooms can only be booked for two hours at a time and bookings must be made through the app not at the front desk",
  "Subject: Meeting room booking changes\n\nHi all,\n\nStarting the 1st of next month, meeting rooms can only be booked for 2 hours at a time, and bookings must be made through the app, not at the front desk.",
  nums=["1", "2"], inc=["Subject: Meeting room booking changes", "Hi all", "2 hours at a time", "through the app", "not at the front desk"], neg=1,
  note="facts: dictated subject; from the 1st of next month; max 2 hours per booking; book via app, NOT front desk")

# 108
E("multi_constraint",
  "i just wanted to let you know that um we plan to launch the weekend physics batch on the fifth if at least twelve students sign up by the thirtieth and vivek sir will be teaching it i hope that's okay",
  "Hi,\n\nWe plan to launch the weekend physics batch on the 5th if at least 12 students sign up by the 30th. Vivek Sir will be teaching it.",
  tone="confident",
  instruction="rewrite with a more confident tone but keep the conditional part word for word",
  nums=["5", "12", "30"], inc=["plan to launch", "weekend physics batch", "if at least 12 students sign up by the 30th", "Vivek"], notinc=["will launch", "hope"], cx=2,
  note="facts: launch on the 5th is a PLAN, conditional on at least 12 sign-ups by the 30th (kept word for word, numbers formatted); Vivek Sir teaches; politeness softeners ('just wanted to let you know', 'I hope that's okay') dropped for confidence")

# 109
E("email",
  "hey uma can you swap my thursday hot desk booking to friday thanks",
  "Hi Uma,\n\nCan you swap my Thursday hot desk booking to Friday? Thanks.",
  register="casual",
  inc=["Hi Uma", "Thursday", "Friday", "hot desk"],
  note="facts: request to move hot desk booking Thursday -> Friday (both days kept, it is a swap, not a correction); dictated 'thanks' kept, no name")

# 110
E("multi_constraint",
  "hi dimitri the estimate for the clutch plate replacement is five thousand four hundred rupees including labour and the work takes one full day please confirm by tomorrow if you'd like us to go ahead",
  "Hi Dimitri,\n\nThe estimate for the clutch plate replacement is ₹4,500, including labour, and the work takes one full day. Please confirm by tomorrow if you'd like us to go ahead.",
  facts="correct", locale="en-in",
  instruction="the estimate is 4,500 not 5,400, keep everything else as is",
  nums=["4,500"], inc=["Dimitri", "clutch plate", "including labour", "one full day", "by tomorrow"], notinc=["5,400"], cx=2,
  note="Facts: correct authorised one change: ₹5,400 -> ₹4,500. Everything else kept: includes labour; one full day; confirm by tomorrow if they want to go ahead")

# 111
E("email",
  "okay this is to mr andre lobo and ms farah sheikh from the group booking um their trip cancellation claim for the goa trip uh the policy covers cancellation due to illness only if a doctor's certificate is submitted within fourteen days of the cancelled departure date their departure was on the second of september so the deadline is the sixteenth uh so far we have the cancellation invoice from the airline but not the certificate if it arrives after the sixteenth the claim cannot be considered also the non refundable hotel deposit of eight thousand rupees is covered but the visa fee is not",
  "Dear Mr. Andre Lobo and Ms. Farah Sheikh,\n\nRegarding your trip cancellation claim for the Goa trip, the policy covers cancellation due to illness only if a doctor's certificate is submitted within 14 days of the cancelled departure date. Your departure was on September 2, so the deadline is the 16th.\n\nSo far, we have the cancellation invoice from the airline, but not the certificate. If it arrives after the 16th, the claim cannot be considered.\n\nThe non-refundable hotel deposit of ₹8,000 is covered, but the visa fee is not.\n\nRegards,\nUma Krishnan",
  register="formal", locale="en-in", sender="Uma Krishnan",
  nums=["14", "2", "16", "8,000"], inc=["Andre Lobo", "Farah Sheikh", "Goa", "only if", "doctor's certificate", "cancellation invoice", "visa fee", "Uma Krishnan"],
  neg=3,
  note="facts: two recipients both greeted; illness cover ONLY IF certificate within 14 days of departure; departure September 2, deadline the 16th; have airline invoice but NOT certificate; after the 16th claim cannot be considered; ₹8,000 non-refundable hotel deposit covered, visa fee NOT")

# 112
E("multi_constraint",
  "hi mrs kapoor uh saanvi missed three classes this month because of her exams that's totally fine we'll share the recorded sessions on the portal and about the refund for the missed classes we don't give refunds for absences but we can adjust one class next month uh also her mock test is on the twenty second",
  "Hi Mrs. Kapoor,\n\nSaanvi missed three classes this month because of her exams, and that's completely fine. We'll share the recorded sessions on the portal. Her mock test is on the 22nd.",
  tone="warm",
  instruction="leave out the bit about the refund and keep it warm",
  nums=["22"], inc=["Mrs. Kapoor", "Saanvi", "three classes", "exams", "recorded sessions", "portal", "mock test"], notinc=["refund", "adjust"], cx=2,
  waivers=["negation_lost"],
  note="facts kept: Saanvi missed three classes this month (exams), fine; recorded sessions shared on portal (dictated); mock test on the 22nd. Instruction drops the whole refund part ('we don't give refunds for absences but we can adjust one class next month'), so its negation is intentionally gone: negation_lost waived")

# 113
E("email",
  "the client moved the readout to the ninth not the seventh",
  "Hi Gaurav,\n\nThe client moved the readout to the 9th, not the 7th.\n\nBest,\nSophie",
  recipient="Gaurav", sender="Sophie",
  nums=["9", "7"], inc=["Gaurav", "readout", "Sophie"], neg=1,
  note="facts: readout moved to the 9th, NOT the 7th (contrast stated by speaker, both dates kept)")

# 114
E("multi_constraint",
  "welcome lerato your private cabin number fourteen is ready from monday your access card is at reception and the cabin includes two parking spots in the basement visitors must be registered at reception before twelve noon on the day",
  "Dear Ms. Lerato Dlamini,\n\nWelcome. Your private cabin, number 14, is ready from Monday, and your access card is waiting at reception. The cabin includes two parking spots in the basement. Visitors must be registered at reception before 12 noon on the day of their visit.\n\nRegards,\nHollis Grant",
  register="formal", tone="friendly", recipient="Ms. Lerato Dlamini", sender="Hollis Grant",
  instruction="keep it formal yet friendly and don't add any offers",
  nums=["14", "12"], inc=["Lerato Dlamini", "Welcome", "cabin", "Monday", "access card", "two parking spots", "before 12 noon", "Hollis Grant"],
  notinc=["happy to help", "feel free", "let us know"], cx=3,
  note="facts: welcome; cabin 14 ready from Monday; access card at reception; two basement parking spots; visitors registered before 12 noon on the day; formal greeting 'Dear'; no offers added")

# 115
E("email",
  "hi green team volunteers so the tree planting drive might move to the following sunday if it rains uh we'll confirm by friday evening",
  "Hi Green Team volunteers,\n\nThe tree planting drive might move to the following Sunday if it rains. We'll confirm by Friday evening.",
  inc=["Green Team volunteers", "might", "following Sunday", "if it rains", "Friday evening"],
  note="facts: named audience kept; move to the following Sunday is hedged ('might') AND conditional ('if it rains'); confirmation by Friday evening (dictated)")

# 116
E("multi_constraint",
  "um so i was wondering if maybe you could let the customer know that we cannot change the static ip on their plan and port forwarding is not supported on the basic router uh they'd need the business plan which isn't available in their area yet",
  "Hi,\n\nWe cannot change the static IP on your plan, and port forwarding is not supported on the basic router. You would need the business plan, which isn't available in your area yet.",
  instruction="more direct, keep all the nots",
  inc=["static IP", "port forwarding", "basic router", "business plan", "yet"], neg=3, cx=2,
  note="facts: 3 negations (cannot change static IP; port forwarding not supported on basic router; business plan isn't available in area 'yet'); request softener 'I was wondering if maybe' removed")

# 117
E("email",
  "your policy document and the emergency helpline card are attached the helpline number works in all schengen countries",
  "Hi Andre,\n\nYour policy document and the emergency helpline card are attached. The helpline number works in all Schengen countries.",
  recipient="Andre",
  inc=["Andre", "policy document", "emergency helpline card", "attached", "Schengen"],
  note="facts: policy document + helpline card attached (dictated); helpline works in all Schengen countries; no sender so no sign-off")

# 118
E("multi_constraint",
  "so for the jee foundation batch parents can choose either the morning slot seven to nine or the evening slot five thirty to seven thirty uh whichever suits the kid please fill the google form with your choice we'll allot slots on a first come basis",
  "Dear parents,\n\nFor the JEE Foundation batch, you can choose either the morning slot from 7 to 9 or the evening slot from 5:30 to 7:30, whichever suits your child. Please fill in the Google Form with your choice. We will allot slots on a first-come basis.",
  register="formal", locale="en-in",
  instruction="polite email to the parents, keep both batch timing options exactly, and don't add a deadline",
  nums=["7", "9", "5:30", "7:30"], inc=["Dear parents", "JEE Foundation", "either", "morning slot", "evening slot", "Google Form", "first-come"], notinc=["deadline"], cx=3,
  note="facts: alternative kept: morning 7 to 9 OR evening 5:30 to 7:30; fill the Google Form; allotment first-come; no deadline invented")

# 119
E("email",
  "tell mr hollis his car's annual service is booked for wednesday at eleven sorry at eleven thirty and the courtesy car is not available that day",
  "Hi Mr. Hollis,\n\nYour car's annual service is booked for Wednesday at 11:30, and the courtesy car is not available that day.",
  nums=["11:30"], inc=["Mr. Hollis", "annual service", "Wednesday", "courtesy car"], notinc=["at 11,", "at 11 and"], neg=1,
  note="facts: self-correction eleven -> 11:30 applied; Wednesday; courtesy car NOT available that day")

# 120
E("multi_constraint",
  "hi dimitri so the procurement diagnostic found that thirty eight percent of spend goes to vendors without a contract and the top fifteen suppliers account for about seventy percent of the total uh we'd like thirty minutes on thursday to walk your team through it",
  "Subject: Procurement diagnostic findings\n\nDear Dimitri,\n\nThe procurement diagnostic found that 38% of spend goes to vendors without a contract, and the top 15 suppliers account for about 70% of the total. We would like 30 minutes on Thursday to walk your team through it.",
  instruction="add a subject line, keep it formal, and don't change the numbers",
  nums=["38", "15", "70", "30"], inc=["Subject:", "Dimitri", "without a contract", "about 70%", "Thursday"], cx=3,
  waivers=["invented_subject"],
  note="facts: 38% of spend with vendors without contract; top 15 suppliers about 70% ('about' kept); request for 30 minutes on Thursday. Subject requested by instruction (contract 7.3), so invented_subject waived; formal -> 'Dear Dimitri'")

# 121
E("email",
  "hey all so quick recap of sunday's beach cleanup we collected around one hundred and ten bags of waste mostly plastic and the municipal truck picked them up at two uh huge thanks to the college volunteers who stayed back um next cleanup is on the twentieth same spot same time but we need someone to bring the first aid kit since meenal won't be there okay cheers vivek",
  "Hi all,\n\nQuick recap of Sunday's beach cleanup: we collected around 110 bags of waste, mostly plastic, and the municipal truck picked them up at 2. Huge thanks to the college volunteers who stayed back.\n\nThe next cleanup is on the 20th, same spot, same time, but we need someone to bring the first aid kit since Meenal won't be there.\n\nCheers,\nVivek",
  register="casual",
  nums=["110", "2", "20"], inc=["around 110 bags", "mostly plastic", "college volunteers", "first aid kit", "Meenal", "Cheers", "Vivek"], neg=1,
  note="facts: around 110 bags, mostly plastic; truck pickup at 2; thanks to college volunteers; next cleanup the 20th same spot/time; need someone for first aid kit, Meenal won't be there. Speaker dictated own sign-off 'cheers vivek' (no [Sender])")

# 122
E("multi_constraint",
  "hi joaquín uh first of all we're so sorry about your lost suitcase on the lisbon flight um we've registered the claim under reference t i two zero eight eight seven the airline has forty eight hours to trace it and if it's not found we'll need the property irregularity report and receipts for anything you had to buy",
  "Hi Joaquín,\n\nWe're so sorry about your lost suitcase on the Lisbon flight. We've registered the claim under reference TI 20887. The airline has 48 hours to trace it. If it's not found, we'll need the property irregularity report and receipts for anything you had to buy.",
  instruction="keep it under 60 words and don't promise a date",
  nums=["20887", "48"], inc=["Joaquín", "sorry", "Lisbon", "TI 20887", "48 hours", "If it's not found", "property irregularity report", "receipts"],
  notinc=["by Monday", "within a week"], neg=1, maxw=60, cx=2, waivers=["number_missing"],
  note="facts: dictated apology kept (instruction does not forbid it); claim reference TI 20887; airline has 48 hours to trace; IF not found -> property irregularity report + receipts needed. Waiver: checker reads 'first of all' as the number 1")

# 123
E("email",
  "dear sir this is to inform mr gaurav bansal that his new prepaid meter will be installed on the fourteenth between ten and two um the old meter's final reading will be adjusted in the first prepaid recharge",
  "Dear Mr. Gaurav Bansal,\n\nYour new prepaid meter will be installed on the 14th between 10 and 2. The old meter's final reading will be adjusted in the first prepaid recharge.",
  register="formal", locale="en-in",
  nums=["14", "10", "2"], inc=["Gaurav Bansal", "prepaid meter", "final reading", "first prepaid recharge"],
  note="facts: dictated 'dear sir' adapted to the named recipient (formal); installation on the 14th between 10 and 2; old meter's final reading adjusted in first prepaid recharge")

# 124
E("multi_constraint",
  "uh hi hollis the invoice for october is ready it's for twelve thousand five hundred rupees for the dedicated desk plus gst please pay by the tenth to avoid the late fee",
  "Hi Hollis,\n\nThe invoice for October is ready. It is ₹12,500 for the dedicated desk, plus GST. Please pay by the 10th to avoid the late fee.",
  locale="en-in",
  rules=["Write everything in lowercase.", "Keep emails under 80 words."],
  instruction="proper capitals please, this one's going to a client",
  nums=["12,500", "10"], inc=["Hollis", "October", "dedicated desk", "GST", "10th", "late fee"], maxw=80, cx=1,
  note="facts: October invoice ₹12,500 for dedicated desk plus GST; pay by the 10th to avoid late fee. Instruction overrides the lowercase rule only; the under-80-words rule still applies")

# 125
E("email",
  "hi members we're sorry the air conditioning on the third floor was off yesterday afternoon the technician has replaced the compressor and it's working now",
  "Hi members,\n\nWe're sorry the air conditioning on the third floor was off yesterday afternoon. The technician has replaced the compressor, and it's working now.",
  inc=["Hi members", "sorry", "third floor", "yesterday afternoon", "compressor", "working now"], notinc=["inconvenience", "won't happen again"],
  note="facts: dictated apology kept (only that one); AC off on third floor yesterday afternoon; compressor replaced, working now")

# 126
E("multi_constraint",
  "so basically the pricing tool should go live around the twentieth assuming the it team finishes the data migration and uh we've actually already trained all forty store managers so that part's done",
  "Dear Uma,\n\nAll 40 store managers have already been trained. The pricing tool should go live around the 20th, assuming the IT team finishes the data migration.\n\nRegards,\nAndre",
  register="formal", tone="confident", recipient="Uma", sender="Andre",
  instruction="confident, but the go-live date isn't confirmed so keep it tentative",
  nums=["40", "20"], inc=["Uma", "40 store managers", "should go live", "around the 20th", "assuming", "data migration", "Andre"],
  notinc=["will go live"], cx=2,
  note="facts: go-live 'should' be 'around' the 20th, ASSUMING IT finishes data migration (hedge + condition kept); all 40 store managers already trained")

# 127
E("email",
  "your car passed the emission test but the pollution certificate can't be printed until the server is back up so please don't drive outside city limits without it",
  "Hi Farah,\n\nYour car passed the emission test, but the pollution certificate can't be printed until the server is back up, so please don't drive outside city limits without it.\n\nBest,\nDimitri",
  recipient="Farah", sender="Dimitri",
  inc=["Farah", "emission test", "pollution certificate", "server is back up", "outside city limits", "Dimitri"], neg=2,
  note="facts: passed emission test; certificate CAN'T be printed until server is back; DON'T drive outside city limits without it")

# 128
E("multi_constraint",
  "okay so for the parents of the new neet batch um the total fee is one lakh twenty thousand rupees for the full year and you can pay it in two instalments the first instalment of seventy thousand is due on the fifth of june and the second of fifty thousand is due on the fifth of december uh if you pay the full amount upfront there's a discount of five thousand and books and test series are included so there's nothing extra to pay for material uh the fee is not refundable after the first month",
  "Hi parents of the new NEET batch,\n\nThe total fee is ₹1,20,000 for the full year, payable in two instalments: ₹70,000 due on June 5 and ₹50,000 due on December 5. Paying the full amount upfront gets a ₹5,000 discount. Books and the test series are included, so there is nothing extra to pay for material. The fee is not refundable after the first month.",
  locale="en-in", length="shorter",
  instruction="shorter please, but keep every amount and both dates",
  nums=["1,20,000", "70,000", "5", "50,000", "5,000"], inc=["NEET batch", "two instalments", "June 5", "December 5", "upfront", "nothing extra", "not refundable after the first month"],
  neg=1, cx=2,
  note="facts: ₹1,20,000/year in two instalments: ₹70,000 due June 5, ₹50,000 due December 5; ₹5,000 discount if paid upfront; books + test series included, nothing extra; not refundable after first month. ₹ applied to all amounts in the list (rupees spoken once for the total)")

# 129
E("email",
  "please find attached the signed agreement amendment for the co working cabin",
  "Hello,\n\nPlease find attached the signed agreement amendment for the co-working cabin.\n\nRegards,\nSaanvi Rao",
  register="formal", sender="Saanvi Rao",
  inc=["Hello", "signed agreement amendment", "co-working cabin", "Regards", "Saanvi Rao"],
  note="facts: signed agreement amendment for the co-working cabin attached (dictated); formal, no recipient -> 'Hello,'")

# 130
E("multi_constraint",
  "we'll run the saturday resume workshop for the trainees only if at least ten people register by thursday so please share the link with your batch",
  "Subject: Weekend workshop\n\nHi,\n\nWe'll run the Saturday resume workshop for the trainees only if at least ten people register by Thursday, so please do share the link with your batch.",
  tone="friendly",
  instruction="keep the condition, make it friendly, and add a subject line saying Weekend workshop",
  inc=["Subject: Weekend workshop", "Saturday", "only if at least ten people register by Thursday", "share the link"], cx=3,
  waivers=["invented_subject"],
  note="facts: Saturday workshop runs ONLY IF at least ten register by Thursday (condition kept); request to share the link. Subject text given in the instruction, so invented_subject waived")

# 131
E("email",
  "this is regarding the recall for the fuel pump on twenty twenty two hatchbacks ms saanvi desai's car is one of the affected vehicles the replacement is free of cost and takes about three hours uh she can bring the car any weekday between nine am and six pm but she must book a slot first on the toll free number eighteen hundred two zero nine forty four fifty five because walk ins won't be accepted for recall work and please tell her the offer is valid only until the thirty first of march",
  "Dear Ms. Saanvi Desai,\n\nThis is regarding the recall for the fuel pump on 2022 hatchbacks. Your car is one of the affected vehicles. The replacement is free of cost and takes about 3 hours.\n\nYou can bring the car any weekday between 9 a.m. and 6 p.m., but you must book a slot first on the toll-free number 1800 209 4455, because walk-ins won't be accepted for recall work. The offer is valid only until March 31.\n\nRegards,\nVivek Shah",
  register="formal", locale="en-in", sender="Vivek Shah",
  nums=["2022", "3", "9", "6", "31"], inc=["Saanvi Desai", "fuel pump", "free of cost", "about 3 hours", "book a slot first", "1800 209 4455", "only until March 31", "Vivek Shah"],
  neg=1, waivers=["number_missing", "number_invented"],
  note="facts: fuel pump recall, 2022 hatchbacks; her car affected; free, about 3 hours; any weekday 9 a.m.-6 p.m. but MUST book first on 1800 209 4455; walk-ins won't be accepted; valid only until March 31. Waiver: phone number spoken in mixed groups, checker splits it")

# 132
E("multi_constraint",
  "hey sophie and andre if the client signs off on the wireframes tomorrow we can start the usability tests on monday otherwise we'll use the time to fix the navigation",
  "Hi Sophie and Andre,\n\nIf the client signs off on the wireframes tomorrow, we can start the usability tests on Monday. Otherwise, we'll use the time to fix the navigation.",
  register="casual",
  instruction="address both of them, keep it casual, and keep the if exactly",
  inc=["Sophie and Andre", "If the client signs off on the wireframes tomorrow", "Monday", "Otherwise", "navigation"], cx=3,
  note="facts: two recipients; Monday usability tests ONLY if client signs off on wireframes tomorrow; otherwise fix navigation")

# 133
E("email",
  "your annual multi trip policy renews on the first and covers trips of up to forty five days each",
  "Hi Meenal,\n\nYour annual multi-trip policy renews on the 1st and covers trips of up to 45 days each.\n\nBest,\nGaurav",
  recipient="Meenal", sender="Gaurav",
  nums=["1", "45"], inc=["Meenal", "multi-trip", "renews", "up to 45 days each", "Gaurav"],
  note="facts: annual multi-trip policy renews on the 1st; covers trips up to 45 days each")

# 134
E("multi_constraint",
  "hi everyone the members networking evening is on the twelfth at seven pm on the terrace snacks are on us and please rsvp in the slack channel by wednesday",
  "Hi everyone,\n\nThe members' networking evening is on the 21st at 7 p.m. on the terrace. Snacks are on us, and please RSVP in the Slack channel by Wednesday.",
  facts="correct",
  instruction="change the date to the 21st, it's not the 12th, everything else stays",
  nums=["21", "7"], inc=["networking evening", "21st", "terrace", "Snacks are on us", "RSVP", "Slack", "Wednesday"], notinc=["12th"], cx=2,
  note="Facts: correct authorised one change: the 12th -> the 21st. Kept: 7 p.m., terrace, snacks on us, RSVP in Slack by Wednesday")

# 135
E("email",
  "hi lerato can you print forty name tags for the donor meet on friday and leave them at the front office thanks a lot uma",
  "Hi Lerato,\n\nCan you print 40 name tags for the donor meet on Friday and leave them at the front office?\n\nThanks a lot,\nUma",
  register="casual",
  nums=["40"], inc=["Lerato", "40 name tags", "donor meet", "Friday", "front office", "Thanks a lot", "Uma"],
  note="facts: request: print 40 name tags for Friday's donor meet, leave at front office; speaker dictated own closing and name 'thanks a lot uma' (no [Sender])")

# 136
E("multi_constraint",
  "we are not able to share the competitor benchmarks with the client because they come from a paid database we can only share the summary charts",
  "Dear Hollis,\n\nWe cannot share the competitor benchmarks with the client, as they come from a paid database; only the summary charts can be shared.\n\nRegards,\nMeenal Sharma",
  register="formal", length="shorter", recipient="Hollis", sender="Meenal Sharma",
  instruction="formal and short, and keep the negation",
  inc=["Hollis", "cannot share", "competitor benchmarks", "paid database", "only the summary charts", "Meenal Sharma"], neg=1, cx=3,
  note="facts: cannot share competitor benchmarks (paid database) - negation kept; ONLY summary charts can be shared")

# 137
E("email",
  "can you tell the customer that their new connection installation is scheduled between twelve and three on saturday and ask whether someone will be home to let the technician in",
  "Hi,\n\nYour new connection installation is scheduled between 12 and 3 on Saturday. Will someone be home to let the technician in?",
  nums=["12", "3"], inc=["installation", "between 12 and 3", "Saturday", "technician"],
  note="facts: installation Saturday between 12 and 3; the speaker's question (will someone be home) kept as a question, not answered")

# 138
E("multi_constraint",
  "um sorry mr gaurav but the spare part for the ac compressor hasn't arrived from the warehouse yet it's expected by tuesday so the car will be ready on wednesday at the earliest",
  "Dear Mr. Gaurav,\n\nThe spare part for the AC compressor has not arrived from the warehouse yet. It is expected by Tuesday, so the car will be ready on Wednesday at the earliest.",
  register="formal",
  instruction="take out the sorry, keep 'at the earliest', and make it formal",
  inc=["Mr. Gaurav", "AC compressor", "not arrived", "yet", "expected by Tuesday", "Wednesday at the earliest"], notinc=["sorry", "apolog", "regret"], neg=1, cx=3,
  note="facts: part NOT arrived yet; 'expected' by Tuesday (hedged); ready Wednesday AT THE EARLIEST; dictated apology removed by instruction")

# 139
E("email",
  "hello mr vivek nair your son's monthly test report is ready he scored sixty eight out of hundred in chemistry and eighty one in physics the parent meeting with the faculty is on saturday at four",
  "Dear Mr. Vivek Nair,\n\nYour son's monthly test report is ready. He scored 68 out of 100 in chemistry and 81 in physics. The parent meeting with the faculty is on Saturday at 4.",
  register="formal", locale="en-in",
  nums=["68", "100", "81", "4"], inc=["Vivek Nair", "monthly test report", "chemistry", "physics", "Saturday"],
  note="facts: 68/100 chemistry, 81 physics; parent meeting with faculty Saturday at 4; formal -> 'Dear'")

# 140
E("multi_constraint",
  "hi residents of shanti nagar um so the scheduled power shutdown for the substation upgrade is on sunday the eighth from six am to probably around four pm we'll try to finish earlier but no guarantees uh water pumps in the society won't work during this time so please store water the night before uh lifts in buildings without a generator will also be off and if the work gets delayed we'll send an sms update by two pm",
  "Subject: Scheduled power shutdown on Sunday the 8th\n\nDear residents of Shanti Nagar,\n\nThe scheduled power shutdown for the substation upgrade is on Sunday the 8th, from 6 a.m. to probably around 4 p.m. We'll try to finish earlier, but there are no guarantees.\n\nThe water pumps in the society won't work during this time, so please store water the night before. Lifts in buildings without a generator will also be off.\n\nIf the work gets delayed, we'll send an SMS update by 2 p.m.",
  locale="en-in",
  instruction="professional but friendly, keep the probably, don't promise compensation, and add a subject line about the outage",
  nums=["8", "6", "4", "2"], inc=["Subject:", "Shanti Nagar", "substation upgrade", "probably around 4 p.m.", "no guarantees", "store water", "without a generator", "If the work gets delayed"],
  notinc=["compensation", "rebate"], neg=3, cx=4, waivers=["invented_subject"],
  note="facts: shutdown Sunday the 8th, 6 a.m. to PROBABLY around 4 p.m.; will try to finish earlier, no guarantees; pumps won't work, store water night before; lifts off in buildings without generator; IF delayed, SMS by 2 p.m. Subject requested by instruction (invented_subject waived)")

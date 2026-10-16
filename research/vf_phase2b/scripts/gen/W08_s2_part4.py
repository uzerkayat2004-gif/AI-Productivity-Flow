# W08 stage 2, chunk 4: TC-W08-221..240

# 221
E("multi_constraint",
  "really sorry for the mix up your meeting room booking m r five five two is now confirmed for ten am",
  "Hi,\n\nYour meeting room booking MR 552 is now confirmed for 10 a.m.",
  instruction="under 20 words, keep the booking ID, no apology",
  nums=["552", "10"], inc=["MR 552", "confirmed", "10 a.m."], notinc=["sorry", "apolog", "mix-up", "mix up"], maxw=20, cx=3, pos="before",
  note="facts: booking MR 552 confirmed for 10 a.m.; dictated apology for the mix-up removed per instruction")

# 222
E("multi_constraint",
  "hi mr gaurav mehra about your flight delay claim um your flight from delhi to singapore was delayed by about nine hours and the policy pays five thousand rupees for every six hour block of delay so it looks like you'd probably get five thousand for the first six hours uh but the remaining three hours don't make another full block so they won't count we still need the airline's delay certificate showing the actual departure time and once we have that the claim usually gets settled in about a week",
  "Dear Mr. Gaurav Mehra,\n\nRegarding your flight delay claim, your flight from Delhi to Singapore was delayed by about 9 hours, and the policy pays ₹5,000 for every 6-hour block of delay. So it looks like you would probably get ₹5,000 for the first 6 hours, but the remaining 3 hours don't make another full block, so they won't count.\n\nWe still need the airline's delay certificate showing the actual departure time. Once we have that, the claim usually gets settled in about a week.",
  locale="en-in",
  instruction="professional but friendly, keep the hedges, don't promise approval, and keep the amounts",
  nums=["9", "5,000", "6", "3"], inc=["Gaurav Mehra", "Delhi to Singapore", "about 9 hours", "every 6-hour block", "probably", "remaining 3 hours", "won't count", "delay certificate", "Once we have that", "usually", "about a week"],
  notinc=["approved", "guarantee"], neg=2, cx=4, pos="before",
  note="facts: delay about 9 hours; ₹5,000 per full 6-hour block; 'looks like' 'probably' ₹5,000 for first 6 hours; remaining 3 hours DON'T make a block, WON'T count; still need airline delay certificate; ONCE received, 'usually' settled in 'about' a week; no approval promised")

# 223
E("multi_constraint",
  "the workshop isn't on friday anymore it's on monday",
  "Hi Vivek and Saanvi,\n\nThe workshop isn't on Friday anymore; it's on Monday.",
  register="casual", recipient="Vivek and Saanvi",
  instruction="casual, and keep the not",
  inc=["Vivek and Saanvi", "isn't on Friday anymore", "Monday"], neg=1, cx=2,
  note="facts: two recipients from [Recipient]; workshop NOT on Friday anymore, now Monday (both days kept, it is a stated change)")

# 224
E("email",
  "dear mr joaquín ortiz we're sorry that your car was returned with grease marks on the driver's seat after the service on monday uh the service advisor has confirmed that the seat cover was not used during the job which is against our process um we have arranged a professional interior cleaning at no cost and a pickup driver will collect the car from your home on thursday at ten am if that time doesn't work please reply with another slot this week",
  "Dear Mr. Joaquín Ortiz,\n\nWe're sorry that your car was returned with grease marks on the driver's seat after the service on Monday. The service advisor has confirmed that the seat cover was not used during the job, which is against our process.\n\nWe have arranged a professional interior cleaning at no cost, and a pickup driver will collect the car from your home on Thursday at 10 a.m. If that time doesn't work, please reply with another slot this week.\n\nRegards,\nSaanvi Pillai",
  register="formal", sender="Saanvi Pillai",
  nums=["10"], inc=["Joaquín Ortiz", "sorry", "grease marks", "driver's seat", "Monday", "seat cover was not used", "against our process", "at no cost", "Thursday at 10 a.m.", "If that time doesn't work", "this week", "Saanvi Pillai"],
  notinc=["will not happen again", "voucher", "discount"], neg=2,
  note="facts: dictated apology kept (only that one); grease marks after Monday's service; seat cover NOT used (against process); free interior cleaning arranged (dictated); pickup Thursday 10 a.m.; IF that doesn't work, reply with another slot this week; no extra compensation added")

# 225
E("multi_constraint",
  "you need to arrive at least fifteen minutes before the test starts",
  "Hello,\n\nYou need to arrive at least 15 minutes before the test starts.",
  instruction="formal, and keep the at least",
  nums=["15"], inc=["Hello", "at least 15 minutes", "before the test starts"], cx=2, pos="before",
  note="facts: requirement: arrive AT LEAST 15 minutes before the test starts")

# 226
E("multi_constraint",
  "hi lerato thanks for choosing the private office on the fourth floor um the security deposit is fifty thousand rupees refundable when you move out and the monthly rent of thirty five thousand is payable by the fifth of every month uh the lock in period is six months and if you leave before that the deposit is not refunded electricity is billed separately based on the sub meter",
  "Dear Lerato,\n\nThank you for choosing the private office on the fourth floor. The security deposit is ₹15,000, refundable when you move out, and the monthly rent of ₹35,000 is payable by the 5th of every month.\n\nThe lock-in period is 6 months, and if you leave before that, the deposit is not refunded. Electricity is billed separately based on the sub-meter.",
  facts="correct", locale="en-in",
  instruction="the deposit is 15,000, not 50,000; make it formal; nothing else changes",
  nums=["15,000", "35,000", "5", "6"], inc=["Lerato", "fourth floor", "₹15,000", "refundable when you move out", "₹35,000", "5th of every month", "lock-in period is 6 months", "if you leave before that", "not refunded", "sub-meter"],
  notinc=["50,000"], neg=1, cx=3,
  note="Facts: correct authorised one change: deposit ₹50,000 -> ₹15,000. Kept: refundable on move-out; rent ₹35,000 by the 5th (₹ on both amounts, rupees spoken once in the list); 6-month lock-in, deposit NOT refunded IF leaving before; electricity billed separately via sub-meter")

# 227
E("email",
  "the vendor shortlist is ready for your review",
  "Hi Sophie,\n\nThe vendor shortlist is ready for your review.\n\nBest,\nAndre",
  recipient="Sophie", sender="Andre",
  inc=["Hi Sophie", "vendor shortlist", "ready for your review", "Andre"],
  note="facts: vendor shortlist ready for review")

# 228
E("multi_constraint",
  "no class this saturday because of the elections",
  "Hi Saturday batch parents,\n\nThere is no class this Saturday because of the elections.",
  instruction="make it an email to the Saturday batch parents, keep it short",
  inc=["Saturday batch parents", "no class this Saturday", "elections"], neg=1, cx=2,
  note="facts: NO class this Saturday (elections); audience named in the instruction used in the greeting")

# 229
E("multi_constraint",
  "subject line service restored um hi all we're really sorry for yesterday's outage in sector nine uh the fibre was damaged during metro construction and service was fully restored at eleven forty pm um affected customers will get a one day credit automatically on the next bill there's no need to call us but if your connection is still down please restart the router and if that doesn't work raise a ticket in the app",
  "Subject: Service restored\n\nHello all,\n\nWe are really sorry for yesterday's outage in Sector 9. The fibre was damaged during metro construction, and service was fully restored at 11:40 p.m.\n\nAffected customers will get a one-day credit automatically on the next bill. There is no need to call us, but if your connection is still down, please restart the router, and if that doesn't work, raise a ticket in the app.",
  register="formal",
  instruction="keep my subject and the apology, formal, and don't add any extra compensation",
  nums=["9", "11:40"], inc=["Subject: Service restored", "Hello all", "really sorry", "yesterday's outage", "Sector 9", "metro construction", "11:40 p.m.", "one-day credit", "no need to call us", "if your connection is still down", "raise a ticket in the app"],
  notinc=["voucher", "discount", "free month"], neg=2, cx=3,
  note="facts: dictated subject + dictated apology kept (instruction asks for both); outage yesterday in Sector 9 (fibre damaged, metro construction); fully restored 11:40 p.m.; affected customers get one-day credit automatically; NO need to call; IF still down restart router, IF that doesn't work raise ticket; no extra compensation")

# 230
E("multi_constraint",
  "your certificate is ready collect it thursday",
  "Hi,\n\nYour certificate is ready, and you're welcome to collect it on Thursday.",
  tone="warm",
  instruction="warmer, and keep the Thursday",
  inc=["certificate is ready", "Thursday"], cx=2,
  note="facts: certificate ready; collect on Thursday; warmth through wording only")

# 231
E("email",
  "this goes to mr dimitri rao and mrs saanvi rao the joint holders of the connection um the meter at your flat was tested at our lab on the ninth and was found to be running about four percent fast so your bills from june to september will be revised uh the excess amount of one thousand nine hundred and twenty rupees will be adjusted against your next two bills and not paid out in cash a new meter has already been installed so there's nothing you need to do",
  "Dear Mr. Dimitri Rao and Mrs. Saanvi Rao,\n\nThe meter at your flat was tested at our lab on the 9th and was found to be running about 4% fast, so your bills from June to September will be revised.\n\nThe excess amount of ₹1,920 will be adjusted against your next two bills and not paid out in cash. A new meter has already been installed, so there is nothing you need to do.\n\nRegards,\nFarah Khan",
  register="formal", locale="en-in", sender="Farah Khan",
  nums=["9", "4", "1,920"], inc=["Dimitri Rao", "Saanvi Rao", "9th", "about 4% fast", "June to September", "₹1,920", "next two bills", "not paid out in cash", "nothing you need to do", "Farah Khan"],
  neg=2,
  note="facts: two recipients (joint holders); meter tested on the 9th, about 4% fast; bills June-September revised; excess ₹1,920 adjusted against next two bills, NOT paid in cash; new meter already installed, nothing to do")

# 232
E("multi_constraint",
  "your accessory order ships tomorrow unless the payment fails",
  "Hello,\n\nYour accessory order will ship tomorrow unless the payment fails.",
  instruction="professional, and keep the unless",
  inc=["accessory order", "tomorrow", "unless the payment fails"], cx=2,
  note="facts: ships tomorrow UNLESS payment fails (condition kept)")

# 233
E("multi_constraint",
  "the bus pickup for the science trip is at seven fifteen at the main gate",
  "Hi,\n\nThe bus pickup for the science trip is at 7:45 at the main gate.",
  facts="correct",
  instruction="pickup is 7:45, not 7:15",
  nums=["7:45"], inc=["bus pickup", "science trip", "7:45", "main gate"], notinc=["7:15"], cx=1,
  note="Facts: correct authorised one change: 7:15 -> 7:45; main gate kept")

# 234
E("email",
  "hey uma the projector in room b is fixed",
  "Hi Uma,\n\nThe projector in Room B is fixed.",
  register="casual",
  inc=["Hi Uma", "projector", "Room B", "fixed"],
  note="facts: Room B projector fixed")

# 235
E("multi_constraint",
  "hi team so for the strategy offsite on the twenty first we have two venue options the lakeside resort at four thousand two hundred per head or the city hotel at three thousand six hundred per head both include lunch and the meeting room uh please vote in the poll by wednesday evening um the resort has more parking but it's an hour away so we'd need a shared bus",
  "Hi team,\n\nFor the strategy offsite on the 21st, we have two venue options: the lakeside resort at 4,200 per head or the city hotel at 3,600 per head. Both include lunch and the meeting room. Please vote in the poll by Wednesday evening.\n\nThe resort is an hour away, so we'd need a shared bus.\n\nBest,\nHollis",
  sender="Hollis",
  instruction="leave out the bit about the parking, keep both prices, neutral tone",
  nums=["21", "4,200", "3,600"], inc=["Hi team", "strategy offsite", "21st", "lakeside resort at 4,200 per head", "city hotel at 3,600 per head", "lunch and the meeting room", "Wednesday evening", "an hour away", "shared bus", "Hollis"],
  notinc=["parking", "₹"], cx=3,
  note="facts: offsite on the 21st; alternative kept: lakeside resort 4,200/head OR city hotel 3,600/head (no currency spoken, no symbol); both include lunch + meeting room; vote by Wednesday evening. Only the parking clause is dropped; 'an hour away, so shared bus' is a separate fact and stays")

# 236
E("multi_constraint",
  "the premium will probably go up by eight percent at renewal",
  "Hello,\n\nThe premium will probably go up by 8% at renewal.",
  instruction="formal, keep the probably",
  nums=["8"], inc=["Hello", "probably", "8%", "renewal"], cx=2, pos="before",
  note="facts: premium 'probably' rises 8% at renewal (hedge kept)")

# 237
E("email",
  "hi mentors so the career day at the community centre is on saturday the twelfth no sorry the nineteenth from ten to one uh we're expecting around sixty students each mentor will get a table and about twenty minutes per group uh please bring a few printouts about your field and don't bring any paid course brochures because the organisers have asked us not to promote anything lunch will be provided thanks a lot farah",
  "Hi mentors,\n\nThe career day at the community centre is on Saturday the 19th, from 10 to 1. We're expecting around 60 students. Each mentor will get a table and about 20 minutes per group.\n\nPlease bring a few printouts about your field, and don't bring any paid course brochures, because the organisers have asked us not to promote anything. Lunch will be provided.\n\nThanks a lot,\nFarah",
  locale="en-gb",
  nums=["19", "10", "1", "60", "20"], inc=["Hi mentors", "community centre", "Saturday the 19th", "from 10 to 1", "around 60 students", "about 20 minutes per group", "don't bring any paid course brochures", "not to promote anything", "Lunch will be provided", "Thanks a lot", "Farah"],
  notinc=["12th"], neg=2, waivers=["number_missing", "negation_lost"],
  note="checker gap: 'the twelfth no sorry the nineteenth' correction not applied when 'the' follows 'sorry', and the corrective 'no' is counted as a negation, so number_missing:12 and negation_lost waived. facts: self-correction twelfth -> 19th applied; 10 to 1; around 60 students; a table + about 20 min per group; bring printouts; DON'T bring paid course brochures (organisers asked not to promote); lunch provided (dictated); speaker dictated own sign-off 'thanks a lot farah'")

# 238
E("multi_constraint",
  "your cabin agreement ends on the thirty first do you want to renew",
  "Subject: Cabin renewal\n\nHi,\n\nYour cabin agreement ends on the 31st. Do you want to renew?",
  instruction="add a subject line 'Cabin renewal' and keep it brief",
  nums=["31"], inc=["Subject: Cabin renewal", "31st", "Do you want to renew?"], cx=2, waivers=["invented_subject"],
  note="facts: agreement ends on the 31st; question kept as a question. Subject text given by the instruction (invented_subject waived)")

# 239
E("multi_constraint",
  "hi dr meenal sethi um we'd love to have you take the weekend biology masterclasses for our neet batch from the first week of december uh the fee would be two thousand five hundred rupees per hour and we're looking at about six hours each weekend um sessions are offline at the andheri centre we can't offer online sessions for this batch because the students need the lab demonstrations uh if the dates work for you please confirm by the twentieth so we can announce the schedule",
  "Dear Dr. Meenal Sethi,\n\nWe would love to have you take the weekend biology masterclasses for our NEET batch from the first week of December. The fee would be ₹2,500 per hour, and we are looking at about 6 hours each weekend.\n\nThe sessions are offline at the Andheri centre. We can't offer online sessions for this batch, because the students need the lab demonstrations.\n\nIf the dates work for you, please confirm by the 20th so that we can announce the schedule.\n\nRegards,\nVivek",
  register="formal", tone="friendly", locale="en-in", sender="Vivek",
  instruction="formal but friendly, keep the conditions, and don't add a thank-you or any offer",
  nums=["2,500", "6", "20"], inc=["Dr. Meenal Sethi", "weekend biology masterclasses", "NEET batch", "first week of December", "₹2,500 per hour", "about 6 hours each weekend", "offline at the Andheri centre", "can't offer online sessions", "lab demonstrations", "If the dates work for you", "20th"],
  notinc=["Thank you", "thanks", "happy to"], neg=1, cx=3,
  note="facts: weekend biology masterclasses for NEET batch from first week of December; ₹2,500/hour, about 6 hours each weekend; offline at Andheri centre, CAN'T offer online (lab demonstrations); IF dates work, confirm by the 20th; no thank-you or offer added")

# 240
E("email",
  "the travel insurance for the conference trip to berlin has been arranged for all eight delegates uh the policy documents should reach you by tomorrow but the cover does not include the extra days anyone adds for personal travel",
  "Hi Uma,\n\nThe travel insurance for the conference trip to Berlin has been arranged for all eight delegates. The policy documents should reach you by tomorrow, but the cover does not include the extra days anyone adds for personal travel.\n\nBest,\nGaurav",
  recipient="Uma", sender="Gaurav",
  inc=["Uma", "conference trip", "Berlin", "all eight delegates", "should reach you by tomorrow", "does not include the extra days", "personal travel", "Gaurav"],
  neg=1,
  note="facts: framing 'for the conference trip' kept; insurance for all eight delegates; documents 'should' arrive by tomorrow (hedged); cover does NOT include extra personal-travel days")

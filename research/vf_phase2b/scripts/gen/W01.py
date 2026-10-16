"""W01 stage 1 + stage 2 generator: bucket=cleanup_facts (slices cleanup_ordinary, facts_numbers_negation).

Domains: auto repair garage, software sprint/standups, farming co-op, community theatre.
Stage 2 adds: home renovation, gym physio appointments, weekend sports, small online shop.
Re-running reproduces research/vf_phase2b/data/batches/W01_s1.jsonl and W01_s2.jsonl exactly.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from p2b_kit import rec, save  # noqa: E402

WID = "W01"
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s1.jsonl"))

rows = []
ORD = "cleanup_ordinary"
FACT = "facts_numbers_negation"


def length_class(t):
    n = len(t.split())
    return "short" if n < 20 else ("medium" if n <= 60 else "long")


def add(slice_, request, target, assertions, *, pos="structured", cx=0, note=None, waivers=None):
    n = len(rows) + 1
    req = dict(task="cleanup")
    req.update(request)
    a = dict(assertions)
    a.setdefault("format", req.get("format", "prose"))
    meta = {"command_position": pos, "instruction_complexity": cx, "length_class": length_class(req["transcript"])}
    rows.append(rec(f"TC-{WID}-{n:03d}", "cleanup_facts", slice_, req, target, a, f"w01-sc-{n:03d}",
                    author=WID, note=note, waivers=waivers, meta=meta))


F = dict(header_style="full")

# ------------------------------------------------------------------ short (<20 words)

add(ORD, dict(transcript="uh the alternator on the swift is shot so it needs replacing"),
    "The alternator on the Swift is shot, so it needs replacing.",
    {"must_include": ["alternator", "Swift", "needs replacing"]})

add(ORD, dict(F, transcript="kabir can you can you push the hotfix before lunch"),
    "Kabir, can you push the hotfix before lunch?",
    {"must_include": ["Kabir", "hotfix", "before lunch"], "behavior": "not_answer", "ends_with_question": True})

add(ORD, dict(transcript="mei's update uh she's still blocked on the login bug"),
    "Mei's update: she's still blocked on the login bug.",
    {"must_include": ["Mei", "still blocked", "login bug"]})

add(FACT, dict(F, transcript="the costumes for act two might not be ready by friday"),
    "The costumes for Act 2 might not be ready by Friday.",
    {"must_include": ["might not", "Friday"], "numbers": ["2"], "min_negations": 1},
    note="facts: hedge 'might' + negation kept; Act 2; by Friday")

add(ORD, dict(transcript="so the the sprint review moved to thursday"),
    "The sprint review moved to Thursday.",
    {"must_include": ["sprint review", "Thursday"]},
    note="facts: sprint review moved to Thursday")

add(FACT, dict(register="casual", transcript="basically tanvi's playing the lead unless rohan's voice is back"),
    "Tanvi's playing the lead unless Rohan's voice is back.",
    {"must_include": ["Tanvi", "Rohan", "unless"]},
    note="facts: condition 'unless Rohan's voice is back' kept; Tanvi plays the lead")

add(FACT, dict(wording="keep", transcript="don't merge anything into main until the tests are green"),
    "Don't merge anything into main until the tests are green.",
    {"must_include": ["main", "until the tests are green"], "min_negations": 1},
    note="facts: restriction 'don't merge into main' + condition 'until tests are green' kept")

add(ORD, dict(transcript="amara is uh is bringing the seed catalogues tomorrow"),
    "Amara is bringing the seed catalogues tomorrow.",
    {"must_include": ["Amara", "seed catalogues", "tomorrow"]},
    note="facts: Amara brings seed catalogues tomorrow")

add(ORD, dict(transcript="greta did you did you save the lighting cues question mark"),
    "Greta, did you save the lighting cues?",
    {"must_include": ["Greta", "lighting cues"], "behavior": "not_answer", "ends_with_question": True})

add(FACT, dict(locale="en-in", transcript="the quote for the clutch is twelve thousand rupees sorry fourteen thousand"),
    "The quote for the clutch is ₹14,000.",
    {"must_include": ["clutch"], "numbers_one_of": [["14,000", "14000"]], "must_not_include": ["12,000", "12000", "twelve"]},
    note="facts: self-correction applied: 12,000 -> 14,000 (14,000 only)")

# ------------------------------------------------------------------ medium (20-60 words)

add(ORD, dict(transcript="okay so yesterday i finished the um the export feature and today i'm gonna start on the uh the notifications ticket no blockers"),
    "Yesterday I finished the export feature, and today I'm gonna start on the notifications ticket. No blockers.",
    {"must_include": ["export feature", "notifications ticket", "No blockers"], "min_negations": 1},
    note="facts: done export (yesterday); starting notifications today; no blockers (negation)")

add(ORD, dict(transcript="the customer with the white hatchback called again uh she wants to know if the ac can be looked at today, like, she's fine leaving it here overnight"),
    "The customer with the white hatchback called again. She wants to know if the AC can be looked at today. She's fine leaving it here overnight.",
    {"must_include": ["white hatchback", "AC", "today", "overnight"]},
    note="facts: asks if AC can be looked at today (question reported, condition kept); fine leaving it overnight")

add(ORD, dict(F, transcript="so the co-op meeting is uh is in the community hall this time not the barn, and bilal is bringing tea"),
    "The co-op meeting is in the community hall this time, not the barn, and Bilal is bringing tea.",
    {"must_include": ["community hall", "barn", "Bilal", "tea"], "min_negations": 1},
    note="facts: meeting in community hall, NOT the barn; Bilal brings tea")

add(ORD, dict(register="casual", transcript="hey everyone um quick reminder that the set build is this saturday, wear old clothes because uh we're painting the backdrop"),
    "Hey everyone, quick reminder that the set build is this Saturday. Wear old clothes because we're painting the backdrop.",
    {"must_include": ["set build", "Saturday", "old clothes", "backdrop"]},
    note="facts: set build this Saturday; wear old clothes; painting backdrop")

add(FACT, dict(F, transcript="the sprint has um forty two story points committed and we've closed only eighteen so far, so we probably won't finish the reporting epic"),
    "The sprint has 42 story points committed, and we've closed only 18 so far, so we probably won't finish the reporting epic.",
    {"numbers": ["42", "18"], "must_include": ["probably won't", "reporting epic"], "min_negations": 1},
    note="facts: 42 committed, only 18 closed; hedge 'probably' + negation 'won't finish' kept")

add(FACT, dict(F, locale="en-gb", transcript="front tyres are at uh two millimetres tread so they need replacing, the rear ones are at five so they're fine for now"),
    "Front tyres are at 2 millimetres tread, so they need replacing. The rear ones are at 5, so they're fine for now.",
    {"numbers": ["2", "5"], "must_include": ["millimetres", "need replacing", "fine for now"]},
    note="facts: front 2 mm -> replace; rear 5 -> fine for now")

add(FACT, dict(locale="en-in", transcript="the co-op will pay eighteen rupees a kilo for the tomatoes, uh, but only if they're graded a"),
    "The co-op will pay ₹18 a kilo for the tomatoes, but only if they're graded A.",
    {"numbers": ["18"], "must_include": ["a kilo", "only if", "graded A"]},
    note="facts: ₹18 per kilo; condition 'only if graded A' kept")

add(FACT, dict(locale="en-in", transcript="tickets are three hundred and fifty rupees for adults and um two hundred for kids under twelve, seniors get in free on the sunday matinee"),
    "Tickets are ₹350 for adults and ₹200 for kids under 12. Seniors get in free on the Sunday matinee.",
    {"numbers": ["350", "200", "12"], "must_include": ["adults", "kids under", "Seniors", "free", "Sunday matinee"]},
    note="facts: adults ₹350, kids under 12 ₹200 (same rupee price list), seniors free on Sunday matinee only")

add(FACT, dict(instruction="just clean it up, keep the dates exactly",
               transcript="the release is on the uh the fourteenth of november but marketing doesn't want any announcement before the sixteenth"),
    "The release is on the 14th of November, but marketing doesn't want any announcement before the 16th.",
    {"numbers": ["14", "16"], "must_include": ["November", "marketing", "before the 16th"], "min_negations": 1},
    pos="after", cx=2,
    note="facts: release 14th of November; no announcement before the 16th (negation + restriction)")

add(ORD, dict(F, register="formal", transcript="we've completed the um the annual service on your vehicle and uh the only thing we noticed is that the wiper blades are getting worn"),
    "We've completed the annual service on your vehicle, and the only thing we noticed is that the wiper blades are getting worn.",
    {"must_include": ["annual service", "only thing", "wiper blades", "getting worn"]})

add(ORD, dict(transcript="for the market stall we need bullet point the folding tables bullet point price cards bullet point um the cash box and next bullet the shade umbrella"),
    "For the market stall we need:\n- The folding tables\n- Price cards\n- The cash box\n- The shade umbrella",
    {"must_include": ["market stall", "folding tables", "Price cards", "cash box", "shade umbrella"], "format": "bullets"},
    note="facts: four items dictated with explicit 'bullet point' cues; nothing added")

add(ORD, dict(format="numbered", transcript="first everyone warms up on stage, then we run act one from the top, and finally um notes in the green room"),
    "1. Everyone warms up on stage.\n2. We run Act 1 from the top.\n3. Notes in the green room.",
    {"must_include": ["warms up on stage", "from the top", "green room"], "numbers": ["1"]},
    note="facts: order warm-up -> run Act 1 from the top -> notes in green room")

add(FACT, dict(transcript="tell mr rohan that sorry tell kabir that the car will be ready by five"),
    "Tell Kabir that the car will be ready by 5.",
    {"must_include": ["Kabir", "ready by 5"], "numbers": ["5"], "must_not_include": ["Rohan"]},
    note="facts: self-correction applied, recipient Kabir (not Rohan); ready by 5 (no a.m./p.m. added)")

add(FACT, dict(F, transcript="we've got fifteen or maybe twenty bags of feed left, which uh should last until the end of the month if we don't add more goats"),
    "We've got 15 or maybe 20 bags of feed left, which should last until the end of the month if we don't add more goats.",
    {"numbers": ["15", "20"], "must_include": ["or maybe", "should last", "end of the month", "if we don't"], "min_negations": 1},
    note="facts: genuine alternative 15 OR maybe 20 bags (both kept); 'should' hedge; condition 'if we don't add more goats'")

add(ORD, dict(register="casual", transcript="rohan you know the staging server is down again, can you uh can you restart it when you get a sec"),
    "Rohan, the staging server is down again. Can you restart it when you get a sec?",
    {"must_include": ["Rohan", "staging server", "restart"], "ends_with_question": True, "behavior": "not_answer"})

add(ORD, dict(transcript="hmm i think the curtain call feels too long, maybe we cut the second bow"),
    "I think the curtain call feels too long. Maybe we cut the second bow.",
    {"must_include": ["I think", "curtain call", "Maybe", "second bow"]},
    note="facts: hedges 'I think' and 'maybe' kept; suggestion, not a decision")

add(FACT, dict(F, context="code", transcript="the api rate limit is a hundred requests per minute per user, not per account, so don't change the config"),
    "The API rate limit is 100 requests per minute per user, not per account, so don't change the config.",
    {"numbers": ["100"], "must_include": ["per user", "per account", "config"], "min_negations": 2},
    note="facts: 100 requests/min per user, NOT per account; restriction 'don't change the config'")

add(ORD, dict(F, transcript="uh mei mei says the irrigation pump is making that grinding noise again so she switched it off for now"),
    "Mei says the irrigation pump is making that grinding noise again, so she switched it off for now.",
    {"must_include": ["Mei", "irrigation pump", "grinding noise", "switched it off for now"]})

add(FACT, dict(transcript="retro action items number one we stop merging on friday afternoons number two uh rohan sets up the flaky test dashboard by next sprint number three everyone updates their tickets before standup not after"),
    "Retro action items:\n1. We stop merging on Friday afternoons.\n2. Rohan sets up the flaky test dashboard by next sprint.\n3. Everyone updates their tickets before standup, not after.",
    {"must_include": ["Friday afternoons", "Rohan", "flaky test dashboard", "next sprint", "before standup"], "format": "numbered", "min_negations": 1},
    note="facts: dictated numbered list (number one/two/three); Rohan owns dashboard by next sprint; tickets before standup NOT after")

# ------------------------------------------------------------------ long (60-220 words)

add(ORD, dict(context="work", transcript="okay so um this is jonas for standup. yesterday i was mostly on the uh the payment retry logic, i got the happy path working but the edge case where the card expires mid retry is still uh still failing in tests. today i'm gonna pair with amara on that because she wrote the original webhook handler. um the other thing is the design review, i think it moved to wednesday but i'm not a hundred percent sure so someone please check the calendar. no blockers apart from that, oh and i'm out on friday afternoon for a family thing"),
    "This is Jonas for standup. Yesterday I was mostly on the payment retry logic. I got the happy path working, but the edge case where the card expires mid-retry is still failing in tests. Today I'm gonna pair with Amara on that because she wrote the original webhook handler.\n\nThe other thing is the design review. I think it moved to Wednesday, but I'm not 100% sure, so someone please check the calendar. No blockers apart from that. Oh, and I'm out on Friday afternoon for a family thing.",
    {"must_include": ["Jonas", "Amara", "payment retry", "webhook handler", "I think", "Wednesday", "Friday afternoon"], "numbers": ["100"], "min_negations": 2},
    note="facts: happy path works, expiry edge case still failing; pairing with Amara today; design review hedged 'I think' Wednesday, not 100% sure; no blockers; out Friday afternoon")

add(FACT, dict(locale="en-in", transcript="so for the blue innova, um, the customer approved the brake job but not the suspension work. brake pads and discs come to eighteen thousand five hundred rupees including labour. uh the suspension quote was twenty two thousand and he said he'll think about it, so don't order those parts yet. he needs the car back by thursday evening because he's driving to pune on friday. if the discs aren't in stock locally then call bilal at the parts shop, he usually has them, but uh don't pay more than four thousand per disc"),
    "For the blue Innova, the customer approved the brake job but not the suspension work. Brake pads and discs come to ₹18,500 including labour. The suspension quote was 22,000, and he said he'll think about it, so don't order those parts yet.\n\nHe needs the car back by Thursday evening because he's driving to Pune on Friday. If the discs aren't in stock locally, then call Bilal at the parts shop. He usually has them, but don't pay more than 4,000 per disc.",
    {"numbers": ["18,500", "22,000", "4,000"], "must_include": ["Innova", "not the suspension", "Thursday evening", "Pune", "Friday", "Bilal", "If the discs"], "min_negations": 4},
    note="facts: brakes approved, suspension NOT; ₹18,500 incl labour; suspension 22,000 undecided -> don't order yet; car back Thursday evening; condition: if discs not in stock call Bilal; cap: don't pay more than 4,000 per disc")

add(ORD, dict(F, transcript="so um a few updates from the co-op meeting. greta's taking over the seed orders from next month because uh tanvi is stepping back for a while. we agreed to try the new organic fertiliser on two plots first, just the east field and the small plot by the pond, and if it works we'll use it everywhere next season. the cold storage unit is still making that noise, the repair guy is coming back on tuesday. and uh the harvest festival, we're thinking of moving it to the last weekend of october but nothing's decided yet"),
    "A few updates from the co-op meeting. Greta's taking over the seed orders from next month because Tanvi is stepping back for a while. We agreed to try the new organic fertiliser on two plots first, just the east field and the small plot by the pond, and if it works, we'll use it everywhere next season.\n\nThe cold storage unit is still making that noise. The repair guy is coming back on Tuesday. And the harvest festival, we're thinking of moving it to the last weekend of October, but nothing's decided yet.",
    {"must_include": ["Greta", "Tanvi", "seed orders", "two plots", "east field", "if it works", "Tuesday", "October", "nothing's decided"], "min_negations": 1},
    note="facts: Greta takes seed orders from next month; fertiliser trial on two plots (east field + pond plot), condition 'if it works'; repair Tuesday; festival move to last weekend of October only being considered, nothing decided")

add(FACT, dict(transcript="okay notes from tonight's run. um the scene change into act two took almost two minutes which is way too long, we need it under forty five seconds. rohan, your entrance in the market scene was early again, wait for the bell. uh mei and jonas, the duet was lovely but you're drifting off your marks downstage, so stay on the tape. props, the letter in scene four went missing again, can someone uh please make a backup. and everyone, call time on saturday is five thirty not six, the photographer is coming"),
    "Notes from tonight's run. The scene change into Act 2 took almost 2 minutes, which is way too long. We need it under 45 seconds.\n\nRohan, your entrance in the market scene was early again. Wait for the bell. Mei and Jonas, the duet was lovely, but you're drifting off your marks downstage, so stay on the tape.\n\nProps, the letter in Scene 4 went missing again. Can someone please make a backup?\n\nAnd everyone, call time on Saturday is 5:30, not 6. The photographer is coming.",
    {"numbers": ["2", "45", "4", "5:30", "6"], "must_include": ["Rohan", "Mei", "Jonas", "almost", "under 45 seconds", "Saturday"], "min_negations": 1},
    note="facts: Act 2 change took almost 2 min, target under 45 s; Rohan early; Mei+Jonas off marks; Scene 4 letter missing, backup asked; Saturday call 5:30 NOT 6")

add(FACT, dict(instruction="tidy it up but keep the hedges and the conditions exactly as I said them",
               transcript="for sprint planning um we have capacity for about sixty points this time because kabir is on leave for three days. the top priority is the checkout redesign, that's thirty two points. then uh the search bug fixes, maybe twelve points. we should not pull in the analytics dashboard unless the product team signs off on the new metrics by tuesday. and uh one more thing, please don't delete the old feature flags yet, we might need to roll back"),
    "For sprint planning, we have capacity for about 60 points this time because Kabir is on leave for 3 days. The top priority is the checkout redesign, that's 32 points. Then the search bug fixes, maybe 12 points.\n\nWe should not pull in the analytics dashboard unless the product team signs off on the new metrics by Tuesday. And one more thing, please don't delete the old feature flags yet. We might need to roll back.",
    {"numbers": ["60", "3", "32", "12"], "must_include": ["about 60", "Kabir", "checkout redesign", "maybe 12", "unless", "Tuesday", "might need to roll back"], "min_negations": 2},
    pos="before", cx=2,
    note="facts: capacity about 60 (Kabir on leave 3 days); checkout 32 pts top priority; search fixes 'maybe' 12; analytics dashboard NOT pulled in unless product signs off by Tuesday; don't delete old flags; 'might' roll back")

add(ORD, dict(register="casual", transcript="hey guys just um a heads up for tomorrow, we've got six cars booked in and the hoist on bay two still isn't fixed so we're down to two bays. jonas can you take the early ones, the first customer's dropping off at like seven forty five. uh i'll be in late because i'm picking up the diagnostic scanner from the supplier. and please please keep the waiting area tidy, we had a complaint last week"),
    "Hey guys, just a heads up for tomorrow. We've got 6 cars booked in, and the hoist on Bay 2 still isn't fixed, so we're down to 2 bays. Jonas, can you take the early ones? The first customer's dropping off at like 7:45. I'll be in late because I'm picking up the diagnostic scanner from the supplier. And please keep the waiting area tidy. We had a complaint last week.",
    {"numbers": ["6", "2", "7:45"], "must_include": ["Jonas", "hoist", "Bay 2", "diagnostic scanner", "waiting area"], "min_negations": 1},
    note="facts: 6 cars tomorrow; Bay 2 hoist NOT fixed -> 2 bays; Jonas asked to take early ones; first drop-off at like 7:45 (approximate, no a.m./p.m. added); speaker in late")

add(FACT, dict(F, locale="en-in", transcript="um treasurer's update. this quarter the co-op sold produce worth four point two lakh rupees, which is up from three point six lakh last quarter. the loan repayment of fifty thousand is due on the tenth of december, and we can't miss it or the bank adds a two percent penalty. members who haven't paid the annual fee of one thousand two hundred rupees, uh, please pay before the next meeting. we probably won't be able to buy the second tractor this year unless the grant comes through"),
    "Treasurer's update. This quarter the co-op sold produce worth ₹4.2 lakh, which is up from 3.6 lakh last quarter. The loan repayment of 50,000 is due on the 10th of December, and we can't miss it, or the bank adds a 2% penalty. Members who haven't paid the annual fee of ₹1,200, please pay before the next meeting. We probably won't be able to buy the second tractor this year unless the grant comes through.",
    {"numbers": ["4.2", "3.6", "50,000", "10", "2", "1,200"], "must_include": ["lakh", "December", "penalty", "probably won't", "unless the grant"], "min_negations": 3},
    note="facts: sales ₹4.2 lakh up from 3.6 lakh; loan 50,000 due 10th December, can't miss or 2% penalty; unpaid ₹1,200 annual fee due before next meeting; second tractor 'probably' not this year unless grant comes through")

add(ORD, dict(F, register="formal", transcript="good evening everyone. um this season we staged three productions and sold out the closing night of the musical, which hasn't happened before. our volunteers put in uh well over two thousand hours, and i want to thank them personally. the roof of the rehearsal space still leaks, and we haven't found the money to repair it yet. next season, uh, we'd like to try a children's workshop, but only if we can find at least two trained facilitators"),
    "Good evening, everyone. This season we staged three productions and sold out the closing night of the musical, which hasn't happened before. Our volunteers put in well over 2,000 hours, and I want to thank them personally.\n\nThe roof of the rehearsal space still leaks, and we haven't found the money to repair it yet. Next season, we'd like to try a children's workshop, but only if we can find at least two trained facilitators.",
    {"numbers": ["2,000"], "must_include": ["three productions", "closing night", "well over", "still leaks", "only if", "at least two"], "min_negations": 2},
    note="facts: three productions; closing night sold out (first time); well over 2,000 volunteer hours; roof still leaks, no money yet; workshop only if at least two trained facilitators")

add(FACT, dict(locale="en-in", transcript="so the customer's booking is for wednesday no wait thursday at ten thirty, it's a full service plus the timing belt. the timing belt is overdue, it was supposed to be changed at sixty thousand kilometres and the car's at seventy two thousand. the quote we gave was nine thousand eight hundred rupees but that doesn't include the water pump, if the water pump needs doing it's another three thousand. uh he asked for the old parts back so please don't throw them away"),
    "The customer's booking is for Thursday at 10:30. It's a full service plus the timing belt. The timing belt is overdue. It was supposed to be changed at 60,000 kilometres, and the car's at 72,000.\n\nThe quote we gave was ₹9,800, but that doesn't include the water pump. If the water pump needs doing, it's another 3,000. He asked for the old parts back, so please don't throw them away.",
    {"numbers": ["10:30", "60,000", "72,000", "9,800", "3,000"], "must_include": ["Thursday", "timing belt", "water pump", "If the water pump", "old parts"],
     "must_not_include": ["Wednesday"], "min_negations": 2},
    note="facts: self-correction Wednesday -> Thursday at 10:30; belt due at 60,000 km, car at 72,000; quote ₹9,800 excludes water pump; condition: if pump needed, another 3,000; don't throw old parts away")

add(FACT, dict(locale="en-in", instruction="clean this up but don't touch any of the amounts",
               transcript="for the spring show the budget is um eighty five thousand rupees total. sets get thirty thousand, costumes twenty thousand, and the rest is for the hall rental and publicity. the hall rental might go up by five thousand if we book the extra matinee. tanvi wants to rent the moving lights but we can't afford them unless a sponsor comes in. please don't book anything over ten thousand without checking with me first"),
    "For the spring show, the budget is ₹85,000 total. Sets get 30,000, costumes 20,000, and the rest is for the hall rental and publicity. The hall rental might go up by 5,000 if we book the extra matinee.\n\nTanvi wants to rent the moving lights, but we can't afford them unless a sponsor comes in. Please don't book anything over 10,000 without checking with me first.",
    {"numbers": ["85,000", "30,000", "20,000", "5,000", "10,000"], "must_include": ["Tanvi", "might go up", "if we book", "unless a sponsor", "without checking"], "min_negations": 3},
    pos="after", cx=2,
    note="facts: budget ₹85,000; sets 30,000; costumes 20,000; rest hall + publicity; hall 'might' rise 5,000 if extra matinee; lights unaffordable unless sponsor; no booking over 10,000 without checking")

# ------------------------------------------------------------------ extra mixed lengths

add(ORD, dict(F, transcript="bilal says the uh the seedlings in tray three look a bit yellow"),
    "Bilal says the seedlings in Tray 3 look a bit yellow.",
    {"must_include": ["Bilal", "seedlings", "a bit yellow"], "numbers": ["3"]})

add(ORD, dict(F, register="casual", transcript="tanvi um the pr looks good to me, just just rename that helper function before you merge"),
    "Tanvi, the PR looks good to me. Just rename that helper function before you merge.",
    {"must_include": ["Tanvi", "PR", "rename that helper function", "before you merge"]},
    note="facts: PR approved by speaker, condition: rename helper before merging")

add(ORD, dict(transcript="so greta found a second hand fog machine online, uh, it's in decent shape and the seller is like twenty minutes from the theatre"),
    "Greta found a second-hand fog machine online. It's in decent shape, and the seller is like 20 minutes from the theatre.",
    {"must_include": ["Greta", "fog machine", "decent shape", "like 20 minutes", "theatre"], "numbers": ["20"]},
    note="facts: seller like ('about') 20 minutes from the theatre; approximation kept")

add(ORD, dict(context="work", transcript="um rohan finished the the wheel alignment on the red pickup, uh, and the customer's picking it up after lunch, so can someone move it out front"),
    "Rohan finished the wheel alignment on the red pickup, and the customer's picking it up after lunch, so can someone move it out front?",
    {"must_include": ["Rohan", "wheel alignment", "red pickup", "after lunch", "out front"], "ends_with_question": True, "behavior": "not_answer"})

add(FACT, dict(transcript="the scanner says it's an o two sensor fault but it could also be a wiring issue, so don't replace the sensor until kabir checks the harness"),
    "The scanner says it's an O2 sensor fault, but it could also be a wiring issue, so don't replace the sensor until Kabir checks the harness.",
    {"must_include": ["O2 sensor", "could also be", "wiring issue", "Kabir", "harness"], "min_negations": 1},
    note="facts: two possible causes kept (O2 sensor OR wiring, hedge 'could'); restriction: don't replace until Kabir checks the harness")

add(ORD, dict(register="formal", transcript="uh amara and i have reviewed the um the membership applications and we recommend accepting all four of the new families"),
    "Amara and I have reviewed the membership applications, and we recommend accepting all four of the new families.",
    {"must_include": ["Amara", "membership applications", "recommend", "all four"]},
    note="facts: recommendation (not a decision) to accept all four new families")

save(OUT, rows)
print(f"wrote {len(rows)} records to {OUT}")


# ================================================================== STAGE 2 (ids 101-225)
# Conventions used throughout stage 2 (stated per record in `note` where relevant):
# - plain counts one-ten as words, counts over ten as digits; amounts, times, dates, ages,
#   durations, percentages and measurements always digits.
# - ₹ only on amounts where the speaker said "rupees"; other amounts in the record stay bare digits.
# - "like" before a number is kept in cleanup and becomes "about" in rewrite.
# - units stay as spoken in cleanup ("kg" if dictated as kg, "degrees Celsius" stays words).

OUT2 = os.path.abspath(os.path.join(HERE, "..", "..", "data", "batches", f"{WID}_s2.jsonl"))
rows2 = []


def add2(slice_, request, target, assertions, *, pos="structured", cx=0, note=None, waivers=None):
    n = 100 + len(rows2) + 1
    req = dict(task="cleanup")
    req.update(request)
    a = dict(assertions)
    a.setdefault("format", req.get("format", "prose" if req["task"] == "cleanup" else None) or "prose")
    meta = {"command_position": pos, "instruction_complexity": cx, "length_class": length_class(req["transcript"])}
    rows2.append(rec(f"TC-{WID}-{n:03d}", "cleanup_facts", slice_, req, target, a, f"w01-sc-{n:03d}",
                     author=WID, note=note, waivers=waivers, meta=meta))


EIN = dict(locale="en-in")
EGB = dict(locale="en-gb")

# ------------------------------------------------------------------ s2 chunk 1 (101-140)

add2(ORD, dict(transcript="uh the tiler said the bathroom floor needs to dry overnight before grouting"),
     "The tiler said the bathroom floor needs to dry overnight before grouting.",
     {"must_include": ["tiler", "bathroom floor", "overnight", "before grouting"]},
     note="facts: floor dries overnight before grouting")

add2(FACT, dict(F, **EGB, transcript="make sure the north wall gets at least two coats uh the old colour shows through otherwise"),
     "Make sure the north wall gets at least two coats. The old colour shows through otherwise.",
     {"must_include": ["Make sure", "north wall", "at least two coats", "otherwise"]},
     note="facts: requirement 'make sure' + minimum 'at least two coats' kept; reason (old colour shows through) kept")

add2(ORD, dict(transcript="lin's physio session got moved to um wednesday at four"),
     "Lin's physio session got moved to Wednesday at 4.",
     {"must_include": ["Lin", "physio session", "Wednesday"], "numbers": ["4"]},
     note="facts: moved to Wednesday at 4 (no a.m./p.m. added)")

add2(FACT, dict(context="work", transcript="the parcel must not go out without the invoice inside"),
     "The parcel must not go out without the invoice inside.",
     {"must_include": ["must not", "without the invoice"], "min_negations": 2},
     note="facts: restriction 'must not go out without the invoice' (two negation words) kept")

add2(ORD, dict(F, register="casual", transcript="freddie are we are we still playing five a side on sunday"),
     "Freddie, are we still playing five-a-side on Sunday?",
     {"must_include": ["Freddie", "still", "five-a-side", "Sunday"], "behavior": "not_answer", "ends_with_question": True},
     note="facts: question kept as question; 'still' kept; Sunday")

add2(FACT, dict(transcript="we only accept returns within seven days of delivery"),
     "We only accept returns within 7 days of delivery.",
     {"must_include": ["only accept returns", "within 7 days", "delivery"], "numbers": ["7"]},
     note="facts: restriction 'only' + window 7 days (duration -> digits)")

add2(ORD, dict(transcript="kabir says the uh the kitchen cabinets arrive tomorrow morning"),
     "Kabir says the kitchen cabinets arrive tomorrow morning.",
     {"must_include": ["Kabir", "kitchen cabinets", "tomorrow morning"]},
     note="facts: cabinets arrive tomorrow morning (reported by Kabir)")

add2(FACT, dict(transcript="the gym's open from six am to ten pm on weekdays"),
     "The gym's open from 6 a.m. to 10 p.m. on weekdays.",
     {"numbers": ["6", "10"], "must_include": ["a.m.", "p.m.", "weekdays"]},
     note="facts: hours 6 a.m. to 10 p.m., weekdays only")

add2(FACT, dict(context="work", transcript="the standup with the us team is at nine thirty pm ist that's eight am pst"),
     "The standup with the US team is at 9:30 p.m. IST. That's 8 a.m. PST.",
     {"numbers": ["9:30", "8"], "must_include": ["US team", "IST", "PST"]},
     note="facts: 9:30 p.m. IST = 8 a.m. PST; both times and both zones kept")

add2(ORD, dict(transcript="tanvi wrapped up the uh the code review for the search page"),
     "Tanvi wrapped up the code review for the search page.",
     {"must_include": ["Tanvi", "code review", "search page"]})

add2(FACT, dict(transcript="the order is twelve kg so it has to go by surface not air"),
     "The order is 12 kg, so it has to go by surface, not air.",
     {"numbers": ["12"], "must_include": ["kg", "surface", "not air"], "min_negations": 1},
     note="facts: 12 kg; requirement surface shipping, NOT air")

add2(ORD, dict(register="casual", transcript="um bring your own water bottles the pavilion tap isn't working"),
     "Bring your own water bottles. The pavilion tap isn't working.",
     {"must_include": ["water bottles", "pavilion tap", "isn't working"], "min_negations": 1},
     note="facts: tap not working (negation kept)")

add2(FACT, dict(F, transcript="the discount code gives fifteen percent off but not on sale items"),
     "The discount code gives 15% off, but not on sale items.",
     {"numbers": ["15"], "must_include": ["discount code", "not on sale items"], "min_negations": 1},
     note="facts: 15% off; exclusion 'not on sale items' kept")

add2(ORD, dict(transcript="greta wants the um the egg crates stacked by size"),
     "Greta wants the egg crates stacked by size.",
     {"must_include": ["Greta", "egg crates", "by size"]})

add2(FACT, dict(transcript="the electrician is definitely coming monday uh the carpenter maybe tuesday"),
     "The electrician is definitely coming Monday, the carpenter maybe Tuesday.",
     {"must_include": ["definitely", "Monday", "maybe Tuesday", "carpenter"]},
     note="facts: certainty vs hedge kept apart: electrician 'definitely' Monday; carpenter only 'maybe' Tuesday")

add2(ORD, dict(transcript="jonas lost his script again uh can someone print him a copy"),
     "Jonas lost his script again. Can someone print him a copy?",
     {"must_include": ["Jonas", "script again", "print him a copy"], "behavior": "not_answer", "ends_with_question": True},
     note="facts: 'again' kept; request stays a question")

add2(ORD, dict(F, transcript="so the the plasterer finished the living room yesterday uh it looks great but he left a lot of dust everywhere so we'll need a proper clean before the painters come in"),
     "The plasterer finished the living room yesterday. It looks great, but he left a lot of dust everywhere, so we'll need a proper clean before the painters come in.",
     {"must_include": ["plasterer", "living room", "yesterday", "dust", "before the painters"]},
     note="facts: plastering done yesterday; dust left; clean needed before painters")

add2(FACT, dict(transcript="hi it's amara um i need to move my physio appointment from thursday to friday if possible my number is nine eight two two five four one zero seven three"),
     "Hi, it's Amara. I need to move my physio appointment from Thursday to Friday if possible. My number is 9822541073.",
     {"must_include": ["Amara", "physio appointment", "Thursday to Friday", "if possible"], "numbers": ["9822541073"]},
     note="facts: move Thursday -> Friday (request, hedged 'if possible'); phone digits 9-8-2-2-5-4-1-0-7-3 kept in order (spoken without a pause, so written ungrouped)")

add2(FACT, dict(context="code", transcript="test coverage on the payments module dropped to sixty two percent we need it back above eighty before we release uh and that's not optional"),
     "Test coverage on the payments module dropped to 62%. We need it back above 80 before we release, and that's not optional.",
     {"numbers": ["62", "80"], "must_include": ["payments module", "above 80", "before we release", "not optional"], "min_negations": 1},
     note="facts: coverage 62%; requirement above 80 (percent not repeated by speaker, so no % added) before release; 'not optional'")

add2(ORD, dict(transcript="okay so today we got um fourteen orders most of them for the uh the small candles and two people asked if we do gift wrapping which we don't yet"),
     "Today we got 14 orders, most of them for the small candles, and two people asked if we do gift wrapping, which we don't yet.",
     {"numbers": ["14"], "must_include": ["small candles", "two people", "gift wrapping", "don't yet"], "min_negations": 1},
     note="facts: 14 orders (>10 digits), two people (count <=10 words); no gift wrapping yet")

add2(FACT, dict(transcript="the cricket camp runs from the third to the seventh of november um kids have to be at least eight years old and it's capped at twenty per batch"),
     "The cricket camp runs from the 3rd to the 7th of November. Kids have to be at least 8 years old, and it's capped at 20 per batch.",
     {"numbers": ["3", "7", "8", "20"], "must_include": ["November", "at least 8 years", "capped at 20"]},
     note="facts: date range 3rd-7th November; minimum age at least 8 (age -> digits); cap 20 per batch")

add2(ORD, dict(transcript="the lady with the grey scooter says it's uh it's making a ticking sound when she brakes she's dropping it off after work around six"),
     "The lady with the grey scooter says it's making a ticking sound when she brakes. She's dropping it off after work, around 6.",
     {"numbers": ["6"], "must_include": ["grey scooter", "ticking sound", "after work", "around 6"]},
     note="facts: drop-off after work, 'around' 6 (approximate, no a.m./p.m. added)")

add2(FACT, dict(**EGB, transcript="the cold room has to stay between two and four degrees celsius if it goes over six for more than an hour call bilal straight away"),
     "The cold room has to stay between 2 and 4 degrees Celsius. If it goes over 6 for more than an hour, call Bilal straight away.",
     {"numbers": ["2", "4", "6"], "must_include": ["degrees Celsius", "If it goes over 6", "more than an hour", "Bilal"]},
     note="facts: standing rule 2-4 degrees Celsius (own sentence, unconditional); condition: over 6 for more than an hour -> call Bilal")

add2(ORD, dict(register="casual", transcript="hey so um marta can't make tuesday's rehearsal she's got an exam so ishaan's gonna read her lines just just so everyone knows"),
     "Hey, Marta can't make Tuesday's rehearsal. She's got an exam, so Ishaan's gonna read her lines, just so everyone knows.",
     {"must_include": ["Marta", "can't make", "Tuesday", "exam", "Ishaan"], "min_negations": 1},
     note="facts: Marta absent Tuesday (exam); Ishaan reads her lines; dictated 'hey' kept")

add2(FACT, dict(transcript="when you pack the glass jars no more than six to a box and make sure there's bubble wrap between every layer uh we had two breakages last week"),
     "When you pack the glass jars, no more than six to a box, and make sure there's bubble wrap between every layer. We had two breakages last week.",
     {"must_include": ["no more than six", "make sure", "bubble wrap", "every layer", "two breakages", "last week"], "min_negations": 1},
     note="facts: cap 'no more than six' jars per box; requirement bubble wrap between every layer; two breakages last week (counts <=10 as words)")

add2(FACT, dict(instruction="clean it up, keep the dates and the word only exactly",
                transcript="so the code freeze is from the eighteenth to the twenty second uh only critical bug fixes go in during that window and they need two approvals"),
     "The code freeze is from the 18th to the 22nd. Only critical bug fixes go in during that window, and they need two approvals.",
     {"numbers": ["18", "22"], "must_include": ["code freeze", "Only critical bug fixes", "two approvals"]},
     pos="before", cx=2,
     note="facts: freeze 18th-22nd; restriction 'only critical bug fixes'; requirement two approvals")

add2(ORD, dict(transcript="freddie told me the uh the physio wants him doing the knee exercises twice a day um morning and evening and he's not supposed to run until the swelling goes down"),
     "Freddie told me the physio wants him doing the knee exercises twice a day, morning and evening, and he's not supposed to run until the swelling goes down.",
     {"must_include": ["Freddie", "physio", "twice a day", "morning and evening", "not supposed to run", "until the swelling goes down"], "min_negations": 1},
     note="facts: exercises twice a day (morning + evening); no running until swelling goes down")

add2(FACT, dict(**EIN, transcript="the carpenter quoted forty five thousand rupees for the wardrobe uh that's with the laminate if we want veneer it goes up to sixty thousand"),
     "The carpenter quoted ₹45,000 for the wardrobe. That's with the laminate. If we want veneer, it goes up to 60,000.",
     {"numbers": ["45,000", "60,000"], "must_include": ["carpenter", "wardrobe", "laminate", "If we want veneer"]},
     note="facts: ₹45,000 with laminate (₹ only where rupees spoken); condition: veneer -> 60,000")

add2(ORD, dict(task="rewrite", format="message", context="chat", **EGB,
               transcript="tell the team uh match is on saturday at the riverside ground warm up starts at eight thirty and bring both kits because we don't know the other team's colours"),
     "Match is on Saturday at the Riverside ground. Warm-up starts at 8:30, and bring both kits because we don't know the other team's colours.",
     {"numbers": ["8:30"], "must_include": ["Saturday", "Riverside", "both kits", "don't know"], "min_negations": 1, "format": "message"},
     note="facts: Saturday at Riverside ground; warm-up 8:30 (no a.m./p.m. added); bring both kits, other team's colours unknown; no greeting added")

add2(FACT, dict(task="rewrite", instruction="make it shorter and clearer, keep the hedge",
                transcript="so basically what happened is the courier picked up the parcel on monday and it was supposed to arrive in two to three days but it's now friday and the tracking still says in transit so um i think it's stuck somewhere"),
     "The courier collected the parcel on Monday, and it should have arrived in 2 to 3 days. It's now Friday, tracking still shows it in transit, and I think it's stuck somewhere.",
     {"numbers": ["2", "3"], "must_include": ["Monday", "Friday", "in transit", "I think"]},
     pos="after", cx=2,
     note="facts: picked up Monday; expected 2-3 days; now Friday, still in transit; hedge 'I think' it's stuck kept")

add2(ORD, dict(transcript="um lin's dropping off the the tile samples at noon"),
     "Lin's dropping off the tile samples at noon.",
     {"must_include": ["Lin", "tile samples", "noon"]})

add2(FACT, dict(transcript="rohan scored two goals not three the third was an own goal"),
     "Rohan scored two goals, not three. The third was an own goal.",
     {"must_include": ["Rohan", "two goals", "not three", "own goal"], "must_not_include": ["three goals"], "min_negations": 1},
     note="facts: two goals, NOT three; third was an own goal")

add2(ORD, dict(transcript="okay the new seed drill is uh is in the shed"),
     "The new seed drill is in the shed.",
     {"must_include": ["seed drill", "shed"]})

add2(FACT, dict(**EIN, transcript="the courier charges ninety rupees per kg comma minimum two kg"),
     "The courier charges ₹90 per kg, minimum 2 kg.",
     {"numbers": ["90", "2"], "must_include": ["per kg", "minimum 2 kg"]},
     note="facts: ₹90 per kg; minimum 2 kg; spoken 'comma' applied")

add2(ORD, dict(F, transcript="ishaan did the um did the client sign off on the mockups"),
     "Ishaan, did the client sign off on the mockups?",
     {"must_include": ["Ishaan", "client", "mockups"], "behavior": "not_answer", "ends_with_question": True})

add2(FACT, dict(transcript="if it rains the match is off either way training is at nine"),
     "If it rains, the match is off. Either way, training is at 9.",
     {"numbers": ["9"], "must_include": ["If it rains", "match is off", "Either way", "training"]},
     note="facts: conditional (match off if rain) vs unconditional (training at 9 either way) kept in separate sentences")

add2(FACT, dict(transcript="you must not lift more than ten kg for six weeks after the surgery"),
     "You must not lift more than 10 kg for 6 weeks after the surgery.",
     {"numbers": ["10", "6"], "must_include": ["must not lift", "more than 10 kg", "6 weeks", "after the surgery"], "min_negations": 1},
     note="facts: restriction must not lift more than 10 kg; duration 6 weeks after surgery")

add2(ORD, dict(F, register="formal", transcript="uh we've replaced the battery and the um the starter motor is fine so the car should start normally now but please let us know if the problem comes back"),
     "We've replaced the battery, and the starter motor is fine, so the car should start normally now, but please let us know if the problem comes back.",
     {"must_include": ["replaced the battery", "starter motor is fine", "should start normally", "if the problem comes back"]},
     note="facts: battery replaced; starter fine; 'should' hedge; request conditional on problem returning")

add2(FACT, dict(context="work", transcript="the new bottles are two hundred and fifty ml not five hundred so update the listing and uh the price should be three hundred and forty nine not five ninety nine"),
     "The new bottles are 250 ml, not 500, so update the listing, and the price should be 349, not 599.",
     {"numbers": ["250", "500", "349", "599"], "must_include": ["ml", "update the listing"], "min_negations": 2},
     note="facts: 250 ml NOT 500; price 349 NOT 599 (no currency spoken, none added); these are contrasts, not self-corrections, so both values stay")

add2(FACT, dict(transcript="the van can do the market run it's about thirty five km each way but only if someone fills the tank because it's almost empty"),
     "The van can do the market run. It's about 35 km each way, but only if someone fills the tank because it's almost empty.",
     {"numbers": ["35"], "must_include": ["market run", "about 35 km", "only if", "fills the tank", "almost empty"]},
     note="facts: about 35 km each way; condition 'only if someone fills the tank'; tank almost empty")

# ------------------------------------------------------------------ s2 chunk 2 (141-180)

add2(ORD, dict(context="personal", transcript="okay so um update on the house. the kitchen's basically done uh the countertops went in on tuesday and they look really good. the only thing left there is the backsplash which the tiler is doing next week. upstairs is a different story uh the bathroom is still a mess because the shower tray they delivered was the wrong size so we're waiting for a replacement. kabir thinks it'll take another ten days but honestly i'll believe it when i see it. oh and the electrician wants to know if we want the dimmer switches in the bedroom or just the living room"),
     "Update on the house. The kitchen's basically done. The countertops went in on Tuesday, and they look really good. The only thing left there is the backsplash, which the tiler is doing next week.\n\nUpstairs is a different story. The bathroom is still a mess because the shower tray they delivered was the wrong size, so we're waiting for a replacement. Kabir thinks it'll take another 10 days, but honestly, I'll believe it when I see it.\n\nOh, and the electrician wants to know if we want the dimmer switches in the bedroom or just the living room.",
     {"numbers": ["10"], "must_include": ["basically done", "Tuesday", "backsplash", "next week", "wrong size", "Kabir thinks", "dimmer switches", "bedroom or just the living room"]},
     note="facts: kitchen 'basically done' (meaning 'almost', kept); countertops in Tuesday; backsplash next week; shower tray wrong size, waiting for replacement; Kabir's estimate hedged 'thinks' another 10 days; electrician's question (bedroom or just living room) kept as indirect question; breaks at topic changes")

add2(FACT, dict(**EGB, transcript="right so notes from my physio appointment. uh she said the shoulder is improving but i'm still not allowed to do overhead presses for at least another three weeks. i can do the resistance band work three sets of fifteen every other day not every day because the tendon needs rest. if the pain goes above a four out of ten i have to stop and ice it for like twenty minutes. next appointment is on the fourteenth at eleven fifteen and she said if things keep improving that might be the last one"),
     "Notes from my physio appointment. She said the shoulder is improving, but I'm still not allowed to do overhead presses for at least another 3 weeks. I can do the resistance band work, 3 sets of 15, every other day, not every day, because the tendon needs rest. If the pain goes above a 4 out of 10, I have to stop and ice it for like 20 minutes.\n\nNext appointment is on the 14th at 11:15, and she said if things keep improving, that might be the last one.",
     {"numbers": ["3", "15", "4", "10", "20", "14", "11:15"], "must_include": ["still not allowed", "overhead presses", "at least another 3 weeks", "every other day, not every day", "If the pain", "like 20 minutes", "might be the last one"], "min_negations": 2},
     note="facts: no overhead presses for at least another 3 weeks; bands 3 sets of 15 every other day NOT every day; condition pain above 4/10 -> stop and ice like 20 min ('like' kept); next 14th at 11:15; 'might' be last only if things keep improving. Sets/reps/durations/pain scale as digits")

add2(ORD, dict(transcript="so um weekly recap for the shop. sales were steady nothing crazy. the lavender soap sold out again on wednesday uh so we really need to make a bigger batch next time. lin finished photographing the new mug range and the photos look great she's uploading them tonight. uh the one problem is that two customers said their parcels arrived with the box crushed so i've emailed the courier about it. marta wants to try a newsletter next month i'm not sure yet we can talk about it on friday"),
     "Weekly recap for the shop. Sales were steady, nothing crazy. The lavender soap sold out again on Wednesday, so we really need to make a bigger batch next time. Lin finished photographing the new mug range, and the photos look great. She's uploading them tonight.\n\nThe one problem is that two customers said their parcels arrived with the box crushed, so I've emailed the courier about it.\n\nMarta wants to try a newsletter next month. I'm not sure yet. We can talk about it on Friday.",
     {"must_include": ["lavender soap", "sold out again", "Wednesday", "Lin", "tonight", "two customers", "courier", "Marta", "not sure yet", "Friday"], "min_negations": 2},
     note="facts: soap sold out again Wednesday; Lin uploading photos tonight; two customers got crushed boxes, courier emailed (already done); Marta's newsletter idea undecided ('not sure yet'), discuss Friday")

add2(FACT, dict(F, transcript="okay listen up for the tournament on sunday. um we need to be at the ground by seven forty five the first match starts at eight thirty sharp and if we're not registered by eight we forfeit. uh bring your id because they're checking ages this year under sixteens only. the entry fee is twenty five dollars per player and i still haven't got it from ishaan or freddie. and for lunch um there's no food at the venue so pack something"),
     "Listen up for the tournament on Sunday. We need to be at the ground by 7:45. The first match starts at 8:30 sharp, and if we're not registered by 8, we forfeit. Bring your ID because they're checking ages this year, under-16s only.\n\nThe entry fee is $25 per player, and I still haven't got it from Ishaan or Freddie. And for lunch, there's no food at the venue, so pack something.",
     {"numbers": ["7:45", "8:30", "8", "16", "25"], "must_include": ["Sunday", "sharp", "if we're not registered by 8", "forfeit", "ID", "only", "Ishaan", "Freddie", "no food"], "min_negations": 3},
     waivers=["number_invented"],
     note="checker does not read spoken 'sixteens' as 16, so '16' in 'under-16s' is flagged invented (waived). facts: at ground by 7:45; first match 8:30 sharp; condition: not registered by 8 -> forfeit; ID needed, under-16s only; $25 per player, still missing from Ishaan and Freddie; no food at venue")

add2(FACT, dict(context="work", instruction="clean this up but don't change any numbers or percentages",
                transcript="for the incident review um the outage lasted forty seven minutes from two ten to two fifty seven utc. about eighteen percent of requests failed during that window. root cause was the certificate on the load balancer expiring uh nobody got the renewal alert because it was going to an old email list. action items um rohan is moving the alerts to the on call channel by friday and mei is adding a check that warns us thirty days before any cert expires. we're not doing a full postmortem meeting unless the customer asks for one"),
     "For the incident review, the outage lasted 47 minutes, from 2:10 to 2:57 UTC. About 18% of requests failed during that window. Root cause was the certificate on the load balancer expiring. Nobody got the renewal alert because it was going to an old email list.\n\nAction items: Rohan is moving the alerts to the on-call channel by Friday, and Mei is adding a check that warns us 30 days before any cert expires. We're not doing a full postmortem meeting unless the customer asks for one.",
     {"numbers": ["47", "2:10", "2:57", "18", "30"], "must_include": ["UTC", "About 18%", "Nobody", "Rohan", "Friday", "Mei", "30 days", "unless the customer asks"], "min_negations": 2},
     pos="after", cx=2,
     note="facts: outage 47 min, 2:10-2:57 UTC; about 18% failed; cert expiry root cause; nobody got alert (old list); Rohan moves alerts by Friday; Mei adds 30-day warning; no full postmortem unless customer asks")

add2(ORD, dict(**EIN, transcript="good morning everyone um just a few things before we start. the new members ishaan and marta are joining us today so please make them feel welcome. uh the rainwater tank by the south field has been cleaned and it's ready to use again. we're still waiting on the soil test results they should come next week. and um the composting workshop is happening on saturday morning greta's running it anyone who wants to learn is welcome"),
     "Good morning, everyone. Just a few things before we start. The new members, Ishaan and Marta, are joining us today, so please make them feel welcome. The rainwater tank by the south field has been cleaned, and it's ready to use again. We're still waiting on the soil test results. They should come next week.\n\nAnd the composting workshop is happening on Saturday morning. Greta's running it. Anyone who wants to learn is welcome.",
     {"must_include": ["Ishaan", "Marta", "rainwater tank", "south field", "still waiting", "should come next week", "Saturday morning", "Greta"]},
     note="facts: Ishaan and Marta new members today; tank cleaned and usable; soil results 'should' come next week (hedge); composting workshop Saturday morning run by Greta")

add2(FACT, dict(**EIN, transcript="so the customer for the silver city is mr bilal his number is nine eight seven six five, zero one two three four. he's coming at four thirty today to collect it. the bill is six thousand two hundred rupees for the service plus eight hundred for the wiper blades he okayed both on the phone. uh he wants to pay by upi not card. and make sure you mention the rear tyre it's got a nail in it we didn't fix it because he said he'll get it done at his usual place"),
     "The customer for the silver City is Mr Bilal. His number is 98765 01234. He's coming at 4:30 today to collect it. The bill is ₹6,200 for the service, plus 800 for the wiper blades. He okayed both on the phone. He wants to pay by UPI, not card.\n\nAnd make sure you mention the rear tyre. It's got a nail in it. We didn't fix it because he said he'll get it done at his usual place.",
     {"numbers": ["98765 01234", "4:30", "6,200", "800"], "must_include": ["Bilal", "today", "UPI, not card", "make sure", "rear tyre", "nail", "didn't fix"], "min_negations": 2},
     waivers=["number_missing", "number_invented"],
     note="facts: phone 9876501234 written 98765 01234 following the speaker's pause (checker reads the digit groups as different numbers: waived number_missing/number_invented); pick-up 4:30 today; ₹6,200 service (₹ only where rupees spoken) + 800 wipers, both approved; pay by UPI NOT card; rear tyre nail NOT fixed, customer handles it")

add2(ORD, dict(register="casual", transcript="hey everyone so um the cast party is at amara's place after the closing show on saturday. it's potluck so bring a dish if you can nothing with nuts please because jonas is allergic. uh partners are welcome. i'll send the address in the group chat later. also really important we need volunteers to help strike the set on sunday morning from ten it usually takes about three hours with enough people"),
     "Hey everyone, the cast party is at Amara's place after the closing show on Saturday. It's potluck, so bring a dish if you can. Nothing with nuts, please, because Jonas is allergic. Partners are welcome. I'll send the address in the group chat later.\n\nAlso, really important, we need volunteers to help strike the set on Sunday morning from 10. It usually takes about 3 hours with enough people.",
     {"numbers": ["10", "3"], "must_include": ["Amara", "Saturday", "if you can", "Nothing with nuts", "Jonas is allergic", "Sunday morning", "about 3 hours"], "min_negations": 1},
     note="facts: party at Amara's after Saturday closing show; bring a dish if you can; NO nuts (Jonas allergic); speaker will send address later (dictated); strike Sunday from 10, usually about 3 hours")

add2(FACT, dict(**EIN, transcript="for the balcony we measured it again it's three point two metres by one point eight so roughly six square metres. the tiles come in boxes that cover one point five square metres each so we need four boxes but uh order five because some will break. the anti skid ones are eight hundred and fifty rupees a box. don't order the glossy ones they get slippery when wet. tanvi wants to know if we can get them by the twentieth because the railing guy is coming on the twenty second"),
     "For the balcony, we measured it again. It's 3.2 metres by 1.8, so roughly 6 square metres. The tiles come in boxes that cover 1.5 square metres each, so we need four boxes, but order five because some will break. The anti-skid ones are ₹850 a box. Don't order the glossy ones. They get slippery when wet.\n\nTanvi wants to know if we can get them by the 20th because the railing guy is coming on the 22nd.",
     {"numbers": ["3.2", "1.8", "6", "1.5", "850", "20", "22"], "must_include": ["roughly 6 square metres", "four boxes", "order five", "anti-skid", "Don't order the glossy", "Tanvi", "by the 20th"], "min_negations": 1},
     note="facts: 3.2 m by 1.8, roughly 6 sq m; boxes cover 1.5 sq m; need four boxes, order five; anti-skid ₹850/box; don't order glossy; Tanvi asks about delivery by the 20th (railing 22nd). Measurements digits, box counts words")

add2(ORD, dict(F, context="work", transcript="um so for the onboarding of the new joiner freddie starts on monday. tanvi can you be his buddy for the first two weeks. he'll need access to github jira and the staging environment uh i've already requested the laptop. on day one let's keep it light just setup and the architecture walkthrough with jonas. and uh please nobody give him a production ticket in the first sprint"),
     "For the onboarding of the new joiner, Freddie starts on Monday. Tanvi, can you be his buddy for the first 2 weeks? He'll need access to GitHub, Jira and the staging environment. I've already requested the laptop. On day one, let's keep it light, just setup and the architecture walkthrough with Jonas. And please, nobody give him a production ticket in the first sprint.",
     {"numbers": ["2"], "must_include": ["Freddie", "Monday", "Tanvi", "GitHub", "Jira", "staging", "already requested the laptop", "Jonas", "nobody", "first sprint"], "min_negations": 1},
     note="facts: Freddie starts Monday; Tanvi asked to buddy first 2 weeks (duration digits); access GitHub/Jira/staging; laptop already requested; day one setup + walkthrough with Jonas; nobody gives him a production ticket in the first sprint")

add2(FACT, dict(transcript="the pool lanes are booked from six to seven thirty uh but lane four is for the kids' squad only so adults use one to three"),
     "The pool lanes are booked from 6 to 7:30, but Lane 4 is for the kids' squad only, so adults use 1 to 3.",
     {"numbers": ["6", "7:30", "4", "1", "3"], "must_include": ["Lane 4", "kids' squad only", "adults use 1 to 3"]},
     waivers=["number_invented"],
     note="checker does not count the bare spoken 'one' in 'one to three', so lane '1' is flagged invented (waived). facts: booked 6-7:30; Lane 4 kids' squad only; adults lanes 1-3 (lane labels as digits)")

add2(ORD, dict(task="rewrite", format="message", register="casual",
               transcript="tell marta uh the etsy listing for the blue scarf has the wrong photo it's showing the green one can she swap it when she gets a chance"),
     "Marta, the Etsy listing for the blue scarf has the wrong photo. It's showing the green one. Can you swap it when you get a chance?",
     {"must_include": ["Marta", "Etsy", "blue scarf", "wrong photo", "green one"], "format": "message"},
     note="facts: blue scarf listing shows green photo; ask Marta to swap it when she gets a chance; vocative 'Marta,' (speaker addressed her), no greeting/sign-off")

add2(FACT, dict(**EIN, transcript="your appointment is confirmed for saturday the ninth at ten am ist please arrive fifteen minutes early and uh bring your previous x-rays if you have them"),
     "Your appointment is confirmed for Saturday the 9th at 10 a.m. IST. Please arrive 15 minutes early, and bring your previous X-rays if you have them.",
     {"numbers": ["9", "10", "15"], "must_include": ["Saturday the 9th", "IST", "15 minutes early", "X-rays if you have them"]},
     note="facts: Saturday the 9th at 10 a.m. IST; arrive 15 min early; X-rays only if you have them")

add2(ORD, dict(transcript="so jonas reckons the noise is coming from the exhaust bracket um not the exhaust itself which is good news because that's a cheap fix"),
     "Jonas reckons the noise is coming from the exhaust bracket, not the exhaust itself, which is good news because that's a cheap fix.",
     {"must_include": ["Jonas reckons", "exhaust bracket", "not the exhaust itself", "cheap fix"], "min_negations": 1},
     note="facts: hedge 'reckons'; bracket, NOT the exhaust itself")

add2(FACT, dict(transcript="i'm pretty sure the mango harvest will be early this year maybe the second week of may but don't book the trucks until we've checked the orchard"),
     "I'm pretty sure the mango harvest will be early this year, maybe the second week of May, but don't book the trucks until we've checked the orchard.",
     {"must_include": ["pretty sure", "early", "maybe the second week of May", "don't book the trucks", "until we've checked"], "min_negations": 1},
     note="facts: hedges 'pretty sure' and 'maybe' kept; restriction don't book trucks until orchard checked")

add2(ORD, dict(transcript="the lighting desk keeps crashing um greta thinks it's the old firmware so she's gonna update it tomorrow before the tech run"),
     "The lighting desk keeps crashing. Greta thinks it's the old firmware, so she's gonna update it tomorrow before the tech run.",
     {"must_include": ["lighting desk", "Greta thinks", "firmware", "tomorrow", "tech run"]},
     note="facts: Greta's cause is a guess ('thinks'); update tomorrow before tech run")

add2(FACT, dict(F, transcript="the contractor wants thirty percent upfront forty percent when the walls are done and the rest after the final inspection not before"),
     "The contractor wants 30% upfront, 40% when the walls are done, and the rest after the final inspection, not before.",
     {"numbers": ["30", "40"], "must_include": ["upfront", "walls are done", "after the final inspection, not before"], "min_negations": 1},
     note="facts: 30% upfront; 40% when walls done; rest after final inspection, NOT before")

add2(ORD, dict(wording="keep", context="work", transcript="i i think we should split the ticket into two one for the api changes and one for the ui otherwise it's just too big to review"),
     "I think we should split the ticket into two, one for the API changes and one for the UI. Otherwise it's just too big to review.",
     {"must_include": ["I think", "split the ticket into two", "API changes", "UI", "Otherwise", "too big to review"]},
     note="facts: suggestion hedged 'I think'; split into two (API / UI); wording keep: only punctuation/capitals/stutter changed")

add2(FACT, dict(transcript="free shipping is only for orders over fifty dollars and only within the us everything else is a flat eight ninety nine"),
     "Free shipping is only for orders over $50 and only within the US. Everything else is a flat 8.99.",
     {"numbers": ["50", "8.99"], "must_include": ["only for orders over $50", "only within the US", "flat 8.99"]},
     waivers=["number_missing"],
     note="checker reads 'eight ninety nine' as a separate 8 (same gap as 'point two'; waived number_missing). facts: free shipping only over $50 AND only within US; otherwise flat 8.99 (dollars spoken only for 50, so no $ added to 8.99)")

add2(ORD, dict(F, transcript="um rohan's bringing the cones and the bibs mei's got the first aid kit and i'll bring the balls so we're all set for saturday"),
     "Rohan's bringing the cones and the bibs, Mei's got the first aid kit, and I'll bring the balls, so we're all set for Saturday.",
     {"must_include": ["Rohan", "cones", "bibs", "Mei", "first aid kit", "balls", "Saturday"]},
     note="facts: Rohan cones + bibs; Mei first aid kit; speaker balls; Saturday; prose kept (no list cue)")

add2(FACT, dict(transcript="the car's done a hundred and twelve thousand km so the gearbox oil is due we usually do it every sixty thousand but this one was never changed"),
     "The car's done 112,000 km, so the gearbox oil is due. We usually do it every 60,000, but this one was never changed.",
     {"numbers": ["112,000", "60,000"], "must_include": ["km", "gearbox oil is due", "usually", "never changed"], "min_negations": 1},
     note="facts: 112,000 km; gearbox oil due; usual interval 60,000; never changed")

add2(ORD, dict(transcript="hi um this is greta i had a session with the physio last week and she said i should book a follow up is there anything available next tuesday or wednesday afternoon question mark"),
     "Hi, this is Greta. I had a session with the physio last week, and she said I should book a follow-up. Is there anything available next Tuesday or Wednesday afternoon?",
     {"must_include": ["Greta", "physio", "last week", "follow-up", "next Tuesday or Wednesday afternoon"], "behavior": "not_answer", "ends_with_question": True},
     note="facts: both options Tuesday OR Wednesday afternoon kept; spoken 'question mark' applied; not answered")

add2(FACT, dict(transcript="we harvested about two hundred kg of potatoes maybe two hundred and fifty uh i didn't weigh the last crates so call it two hundred to two hundred and fifty for now"),
     "We harvested about 200 kg of potatoes, maybe 250. I didn't weigh the last crates, so call it 200 to 250 for now.",
     {"numbers": ["200", "250"], "must_include": ["about 200 kg", "maybe 250", "didn't weigh", "200 to 250 for now"], "min_negations": 1},
     note="facts: estimate about 200 kg, maybe 250 (range, not a correction: both kept); last crates not weighed")

add2(ORD, dict(task="rewrite", register="formal",
               transcript="so the painters are done but uh there's a couple of spots on the ceiling where the paint is patchy can you send someone to fix it before we move the furniture back in"),
     "The painters have finished, but there are a couple of spots on the ceiling where the paint is patchy. Could you send someone to fix them before we move the furniture back in?",
     {"must_include": ["painters", "couple of spots", "ceiling", "patchy", "before we move the furniture back in"], "format": "prose"},
     note="facts: painters done; a couple of patchy spots on ceiling; request a fix before furniture goes back; formal wording, nothing added")

add2(FACT, dict(context="code", transcript="the release window is ten pm to midnight ist which is four thirty to six thirty pm utc uh don't deploy outside that window"),
     "The release window is 10 p.m. to midnight IST, which is 4:30 to 6:30 p.m. UTC. Don't deploy outside that window.",
     {"numbers": ["10", "4:30", "6:30"], "must_include": ["midnight IST", "UTC", "Don't deploy outside"], "min_negations": 1},
     note="facts: window 10 p.m.-midnight IST = 4:30-6:30 p.m. UTC; restriction don't deploy outside it")

add2(ORD, dict(transcript="marta and ishaan um can you two run the blocking for scene six during lunch i'll join you after my call"),
     "Marta and Ishaan, can you two run the blocking for Scene 6 during lunch? I'll join you after my call.",
     {"numbers": ["6"], "must_include": ["Marta", "Ishaan", "Scene 6", "during lunch", "after my call"], "behavior": "not_answer"},
     note="facts: request to Marta + Ishaan, Scene 6 at lunch; speaker joins after call (dictated)")

add2(FACT, dict(**EGB, transcript="no refunds on personalised items unless they arrive damaged"),
     "No refunds on personalised items unless they arrive damaged.",
     {"must_include": ["No refunds", "personalised items", "unless they arrive damaged"], "min_negations": 1},
     note="facts: rule no refunds on personalised items; exception unless damaged")

add2(ORD, dict(transcript="uh kabir's bringing the the scorebook"),
     "Kabir's bringing the scorebook.",
     {"must_include": ["Kabir", "scorebook"]})

add2(FACT, dict(transcript="ice it for fifteen minutes three times a day"),
     "Ice it for 15 minutes three times a day.",
     {"numbers": ["15"], "must_include": ["15 minutes", "three times a day"]},
     note="facts: 15 minutes (duration digits), three times a day (frequency count <=10 words)")

add2(FACT, dict(**EGB, transcript="the skip's getting collected friday um not thursday"),
     "The skip's getting collected Friday, not Thursday.",
     {"must_include": ["skip", "Friday, not Thursday"], "min_negations": 1},
     note="facts: Friday, NOT Thursday (contrast, both days stay)")

add2(ORD, dict(transcript="bilal the new apprentice starts today"),
     "Bilal, the new apprentice, starts today.",
     {"must_include": ["Bilal", "new apprentice", "today"]})

add2(FACT, dict(F, transcript="the milk price is up two percent from next month"),
     "The milk price is up 2% from next month.",
     {"numbers": ["2"], "must_include": ["milk price", "from next month"]},
     note="facts: up 2% from next month")

add2(ORD, dict(context="work", transcript="can someone can someone review my pr before standup"),
     "Can someone review my PR before standup?",
     {"must_include": ["review my PR", "before standup"], "behavior": "not_answer", "ends_with_question": True})

add2(FACT, dict(transcript="doors open at seven not seven thirty"),
     "Doors open at 7, not 7:30.",
     {"numbers": ["7", "7:30"], "must_include": ["Doors open"], "min_negations": 1},
     note="facts: 7, NOT 7:30")

add2(FACT, dict(**EIN, instruction="tidy this up, keep every price and the conditions word for word",
                transcript="so for the diwali sale um everything in the candles section is twenty percent off and the gift boxes are thirty percent off but only the ones over fifteen hundred rupees. the sale runs from the twenty eighth of october to the second of november. uh we're not discounting the new arrivals at all. if we run out of a candle during the sale don't restock it at the sale price put it back at full price. and lin make sure the banner goes up on the homepage by the twenty seventh"),
     "For the Diwali sale, everything in the candles section is 20% off, and the gift boxes are 30% off, but only the ones over ₹1,500. The sale runs from the 28th of October to the 2nd of November. We're not discounting the new arrivals at all.\n\nIf we run out of a candle during the sale, don't restock it at the sale price; put it back at full price. And Lin, make sure the banner goes up on the homepage by the 27th.",
     {"numbers": ["20", "30", "1,500", "28", "2", "27"], "must_include": ["candles", "gift boxes", "only the ones over", "October", "November", "not discounting the new arrivals", "If we run out", "full price", "Lin", "make sure", "by the 27th"], "min_negations": 2},
     pos="before", cx=2,
     note="facts: candles 20% off; gift boxes 30% off only those over ₹1,500; sale 28th Oct-2nd Nov; new arrivals NOT discounted; condition: if a candle runs out, don't restock at sale price, put back at full price (kept in one sentence so both halves stay conditional); Lin: banner up by the 27th")

add2(ORD, dict(F, register="casual", transcript="okay so i went to the gym physio today um and it's not as bad as i thought. she said my lower back is just tight from sitting all day not a disc thing. so the plan is stretching every morning uh the cat cow one and the child's pose and walking at least thirty minutes a day. she also said i should get a better chair for work honestly i've been meaning to do that for ages. i'm going back in two weeks so she can check how it's going"),
     "I went to the gym physio today, and it's not as bad as I thought. She said my lower back is just tight from sitting all day, not a disc thing. So the plan is stretching every morning, the cat-cow one and the child's pose, and walking at least 30 minutes a day.\n\nShe also said I should get a better chair for work. Honestly, I've been meaning to do that for ages. I'm going back in 2 weeks so she can check how it's going.",
     {"numbers": ["30", "2"], "must_include": ["not as bad", "lower back", "not a disc thing", "every morning", "at least 30 minutes", "better chair", "Honestly", "2 weeks"], "min_negations": 2},
     note="facts: not as bad as thought; tight back, NOT a disc thing; stretches every morning + walk at least 30 min a day; better chair advised; back in 2 weeks (durations digits); 'Honestly' kept (meaning)")

add2(FACT, dict(**EGB, transcript="um quick update on the five a side league. we won on saturday four two freddie got a hat trick. uh we're now third in the table two points behind the leaders. next game is on the eighteenth against the rovers kick off at ten fifteen not ten. we're short of a keeper because bilal's hurt his wrist so if anyone knows someone let me know. subs for the season are forty pounds and need to be in by the end of the month"),
     "Quick update on the five-a-side league. We won on Saturday 4-2. Freddie got a hat-trick. We're now third in the table, two points behind the leaders.\n\nNext game is on the 18th against the Rovers, kick-off at 10:15, not 10. We're short of a keeper because Bilal's hurt his wrist, so if anyone knows someone, let me know.\n\nSubs for the season are £40 and need to be in by the end of the month.",
     {"numbers": ["4-2", "18", "10:15", "10", "40"], "must_include": ["five-a-side", "Saturday", "Freddie", "hat-trick", "third", "two points behind", "Rovers", "not 10", "Bilal", "if anyone knows", "£40", "end of the month"], "min_negations": 1},
     note="facts: won 4-2 Saturday; Freddie hat-trick; third, two points behind (count words); next 18th v Rovers, kick-off 10:15 NOT 10; no keeper (Bilal's wrist), ask if anyone knows someone; subs £40 (pounds spoken) by end of month")

add2(ORD, dict(F, **EGB, register="formal", transcript="dear mr kabir um thank you for the quote for the kitchen renovation. we've looked through it and we're happy with most of it. uh we'd like to go ahead with the cabinets and the countertops as quoted. we're not sure about the flooring yet because we're still comparing options. could you also confirm whether the price includes removing the old units. we'd like work to start in the first week of january if that's possible for you"),
     "Dear Mr Kabir,\n\nThank you for the quote for the kitchen renovation. We've looked through it, and we're happy with most of it. We'd like to go ahead with the cabinets and the countertops as quoted. We're not sure about the flooring yet because we're still comparing options.\n\nCould you also confirm whether the price includes removing the old units? We'd like work to start in the first week of January if that's possible for you.",
     {"must_include": ["Dear Mr Kabir", "most of it", "cabinets and the countertops", "not sure about the flooring", "removing the old units", "first week of January", "if that's possible"], "min_negations": 1},
     note="facts: happy with most of quote; go ahead with cabinets + countertops only; flooring undecided; asks whether price includes removing old units; start first week of January only if possible for him; dictated greeting kept, no sign-off invented")

add2(FACT, dict(**EIN, transcript="okay about the water schedule. from monday every plot gets water only on alternate days that's fixed no exceptions. the morning slot is six to eight and the evening slot is five thirty to seven thirty. uh if the canal level drops below the marker then we go down to one slot a day but that hasn't happened yet. the pump room key is with amara now not greta. and please nobody runs the pump for more than two hours at a stretch the motor overheats"),
     "About the water schedule. From Monday, every plot gets water only on alternate days. That's fixed, no exceptions. The morning slot is 6 to 8, and the evening slot is 5:30 to 7:30.\n\nIf the canal level drops below the marker, then we go down to one slot a day, but that hasn't happened yet. The pump room key is with Amara now, not Greta. And please, nobody runs the pump for more than 2 hours at a stretch. The motor overheats.",
     {"numbers": ["6", "8", "5:30", "7:30", "2"], "must_include": ["From Monday", "only on alternate days", "no exceptions", "If the canal level drops", "one slot a day", "hasn't happened yet", "Amara now, not Greta", "nobody", "more than 2 hours"], "min_negations": 4},
     note="facts: unconditional rule from Monday: water only on alternate days, no exceptions (own sentences); slots 6-8 and 5:30-7:30; condition: canal below marker -> one slot a day (not yet happened); key with Amara NOT Greta; nobody runs pump more than 2 hours at a stretch")

add2(ORD, dict(**EGB, context="work", transcript="so a couple of things from the design sync. first um the new dashboard layout got approved mei's going to share the final figma file today. second the colour contrast on the buttons failed the accessibility check so ishaan is fixing that before anything ships. and uh totally unrelated the office aircon is getting serviced on thursday so the third floor will be warm maybe work from home if you can"),
     "A couple of things from the design sync. First, the new dashboard layout got approved. Mei's going to share the final Figma file today. Second, the colour contrast on the buttons failed the accessibility check, so Ishaan is fixing that before anything ships.\n\nAnd totally unrelated, the office aircon is getting serviced on Thursday, so the third floor will be warm. Maybe work from home if you can.",
     {"must_include": ["dashboard layout got approved", "Mei", "Figma", "today", "colour contrast", "Ishaan", "before anything ships", "Thursday", "Maybe work from home if you can"]},
     note="facts: layout approved, Mei shares Figma today; contrast failed, Ishaan fixes before anything ships; aircon service Thursday, third floor warm; suggestion hedged 'maybe'; paragraph break only at the 'totally unrelated' topic change; prose kept (spoken first/second, not dictated as a list)")

# ------------------------------------------------------------------ s2 chunk 3 (181-225)

add2(ORD, dict(F, **EGB, transcript="um the grout colour we picked is uh is called pebble grey"),
     "The grout colour we picked is called Pebble Grey.",
     {"must_include": ["grout colour", "Pebble Grey"]})

add2(ORD, dict(F, context="work", transcript="mei's on leave all next week back on the twentieth"),
     "Mei's on leave all next week, back on the 20th.",
     {"numbers": ["20"], "must_include": ["Mei", "all next week", "back on the 20th"]},
     note="facts: on leave all next week; back on the 20th")

add2(ORD, dict(transcript="the hens laid uh laid really well this week"),
     "The hens laid really well this week.",
     {"must_include": ["hens", "really well", "this week"]})

add2(ORD, dict(F, transcript="jonas where did we put the the spare torque wrench"),
     "Jonas, where did we put the spare torque wrench?",
     {"must_include": ["Jonas", "spare torque wrench"], "behavior": "not_answer", "ends_with_question": True})

add2(ORD, dict(task="rewrite", format="message", register="casual", transcript="let lin know the grout's dry so she can seal it tonight"),
     "Lin, the grout's dry, so you can seal it tonight.",
     {"must_include": ["Lin", "grout's dry", "seal it tonight"], "format": "message"},
     note="facts: grout dry; Lin can seal it tonight (permission, not an order); addressed to Lin directly, nothing added")

add2(ORD, dict(F, transcript="okay costume fittings are in the green room after warm up"),
     "Costume fittings are in the green room after warm-up.",
     {"must_include": ["Costume fittings", "green room", "after warm-up"]})

add2(ORD, dict(transcript="um the order for the um the walnut chopping boards shipped this morning"),
     "The order for the walnut chopping boards shipped this morning.",
     {"must_include": ["walnut chopping boards", "shipped this morning"]})

add2(FACT, dict(F, context="work", transcript="please don't schedule anything before ten am pst on mondays"),
     "Please don't schedule anything before 10 a.m. PST on Mondays.",
     {"numbers": ["10"], "must_include": ["don't schedule", "before 10 a.m. PST", "Mondays"], "min_negations": 1},
     note="facts: restriction: nothing before 10 a.m. PST, Mondays only; zone kept")

add2(ORD, dict(F, transcript="kabir uh kabir played really well in the trial game"),
     "Kabir played really well in the trial game.",
     {"must_include": ["Kabir", "really well", "trial game"]})

add2(ORD, dict(task="rewrite", format="message", transcript="let amara know the physio can see her at three tomorrow"),
     "Amara, the physio can see you at 3 tomorrow.",
     {"numbers": ["3"], "must_include": ["Amara", "physio", "3 tomorrow"], "format": "message"},
     note="facts: physio can see Amara at 3 tomorrow (no a.m./p.m. added); addressed to her directly, no greeting")

add2(FACT, dict(F, **EGB, transcript="the fertiliser goes on at fifty ml per ten litres of water no stronger"),
     "The fertiliser goes on at 50 ml per 10 litres of water, no stronger.",
     {"numbers": ["50", "10"], "must_include": ["50 ml", "10 litres", "no stronger"], "min_negations": 1},
     note="facts: dilution 50 ml per 10 litres; limit 'no stronger'")

add2(ORD, dict(context="work", transcript="tanvi's fixed the the flaky login test finally"),
     "Tanvi's fixed the flaky login test, finally.",
     {"must_include": ["Tanvi", "flaky login test", "finally"]})

add2(ORD, dict(F, register="casual", transcript="uh does anyone have a spare racket for sunday"),
     "Does anyone have a spare racket for Sunday?",
     {"must_include": ["spare racket", "Sunday"], "behavior": "not_answer", "ends_with_question": True})

add2(ORD, dict(F, **EIN, task="rewrite", format="message", register="casual",
               transcript="tell rohan uh the badminton court is booked for saturday from four to six and we're splitting the cost four ways so it's like three hundred each"),
     "Rohan, the badminton court is booked for Saturday from 4 to 6, and we're splitting the cost four ways, so it's about 300 each.",
     {"numbers": ["4", "6", "300"], "must_include": ["Rohan", "Saturday", "four ways", "about 300 each"], "must_not_include": ["₹"], "format": "message"},
     note="facts: court Saturday 4-6; cost split four ways; 'like three hundred' -> 'about 300' in rewrite (approximation kept); no rupees spoken, so no ₹")

add2(ORD, dict(F, transcript="so the new shelving unit for the stock room arrived um but two of the brackets are missing so we can't put it up until the replacements come"),
     "The new shelving unit for the stock room arrived, but two of the brackets are missing, so we can't put it up until the replacements come.",
     {"must_include": ["shelving unit", "stock room", "two of the brackets are missing", "can't put it up", "until the replacements come"], "min_negations": 1},
     note="facts: unit arrived; two brackets missing; can't assemble until replacements come")

add2(ORD, dict(F, task="rewrite", instruction="make it a bit more polished but keep it short",
               transcript="the garage called the car's ready uh they also checked the brakes and they're fine so it's just the oil change on the bill"),
     "The garage called to say the car's ready. They also checked the brakes, which are fine, so only the oil change is on the bill.",
     {"must_include": ["garage", "car's ready", "brakes", "fine", "only the oil change"], "format": "prose"},
     pos="before", cx=2,
     note="facts: car ready; brakes checked and fine; bill is only the oil change; no new facts")

add2(ORD, dict(F, **EGB, transcript="um greta's daughter is doing the programme design this year she's really good with that stuff and she's doing it for free"),
     "Greta's daughter is doing the programme design this year. She's really good with that stuff, and she's doing it for free.",
     {"must_include": ["Greta's daughter", "programme design", "this year", "for free"]},
     note="facts: Greta's daughter designs the programme this year, for free")

add2(ORD, dict(transcript="okay so i checked with the supplier and the uh the oak flooring is back in stock but the walnut won't be until february"),
     "I checked with the supplier, and the oak flooring is back in stock, but the walnut won't be until February.",
     {"must_include": ["supplier", "oak flooring is back in stock", "walnut won't be until February"], "min_negations": 1},
     note="facts: oak in stock now; walnut NOT until February")

add2(ORD, dict(F, context="work", transcript="hey team um retro is moved to four today because half of us are in the client workshop until three thirty"),
     "Hey team, retro is moved to 4 today because half of us are in the client workshop until 3:30.",
     {"numbers": ["4", "3:30"], "must_include": ["Hey team", "retro", "4 today", "half of us", "client workshop", "until 3:30"]},
     note="facts: retro moved to 4 today; workshop until 3:30; dictated 'hey team' kept")

add2(ORD, dict(task="rewrite", format="message",
               transcript="can you let ishaan know his physio report is ready and he can pick it up from reception any time after two"),
     "Ishaan, your physio report is ready, and you can pick it up from reception any time after 2.",
     {"numbers": ["2"], "must_include": ["Ishaan", "physio report is ready", "reception", "any time after 2"], "format": "message"},
     note="facts: report ready; pick up from reception any time after 2 (no a.m./p.m. added); addressed to Ishaan directly")

add2(ORD, dict(F, **EGB, register="casual", transcript="so the parcel for the customer in leeds came back uh the address was missing a house number so i've messaged her to check it"),
     "The parcel for the customer in Leeds came back. The address was missing a house number, so I've messaged her to check it.",
     {"must_include": ["parcel", "Leeds", "came back", "missing a house number", "messaged her"]},
     note="facts: parcel to Leeds returned; address missing house number; customer already messaged")

add2(ORD, dict(F, transcript="bilal fixed the gate on the goat pen um so they shouldn't get out again but keep an eye on it for a few days"),
     "Bilal fixed the gate on the goat pen, so they shouldn't get out again, but keep an eye on it for a few days.",
     {"must_include": ["Bilal", "goat pen", "shouldn't get out again", "keep an eye on it", "a few days"], "min_negations": 1},
     note="facts: gate fixed by Bilal; hedge 'shouldn't' (not a guarantee); watch it for a few days")

add2(ORD, dict(instruction="just tidy it, don't reword anything",
               transcript="the dress rehearsal went fine um apart from the sound cue in act three which came in way too late"),
     "The dress rehearsal went fine, apart from the sound cue in Act 3, which came in way too late.",
     {"numbers": ["3"], "must_include": ["dress rehearsal went fine", "apart from", "sound cue", "Act 3", "way too late"]},
     pos="after", cx=2,
     note="facts: rehearsal fine except Act 3 sound cue too late; wording untouched")

add2(FACT, dict(F, transcript="for bookings call the front desk on zero two six one two three four five six seven eight between nine and five"),
     "For bookings, call the front desk on 02612345678 between 9 and 5.",
     {"numbers": ["02612345678", "9", "5"], "must_include": ["bookings", "front desk", "between 9 and 5"]},
     note="facts: phone digits 0-2-6-1-2-3-4-5-6-7-8 kept in order including the leading zero (spoken without pauses, so ungrouped); hours 9 to 5")

add2(ORD, dict(task="rewrite", format="message", register="casual", transcript="tell everyone the tractor's back from the garage and it's running fine now"),
     "The tractor's back from the garage, and it's running fine now.",
     {"must_include": ["tractor's back", "garage", "running fine now"], "format": "message"},
     note="facts: tractor back, running fine now; no greeting or vocative invented")

add2(FACT, dict(transcript="it should be ready by thursday but i can't promise that it depends on whether the part arrives tomorrow"),
     "It should be ready by Thursday, but I can't promise that. It depends on whether the part arrives tomorrow.",
     {"must_include": ["should be ready by Thursday", "can't promise", "depends on whether the part arrives tomorrow"], "min_negations": 1},
     note="facts: hedge 'should' Thursday; explicitly no promise; dependency on part arriving tomorrow")

add2(ORD, dict(task="rewrite", length="shorter",
               transcript="so basically the meeting was about the uh new pricing and in the end we decided to keep the current prices for now and look at it again in january"),
     "We discussed the new pricing and decided to keep the current prices for now and revisit them in January.",
     {"must_include": ["new pricing", "keep the current prices for now", "January"], "format": "prose"},
     note="facts: decision: keep current prices for now; revisit in January")

add2(ORD, dict(F, register="casual", transcript="um we've got a new sponsor for the club shirts it's the sports shop on main road they're printing their logo on the back"),
     "We've got a new sponsor for the club shirts. It's the sports shop on Main Road. They're printing their logo on the back.",
     {"must_include": ["new sponsor", "club shirts", "sports shop", "Main Road", "logo on the back"]},
     note="facts: sponsor is the sports shop on Main Road; logo on the back of shirts")

add2(ORD, dict(F, instruction="fix the punctuation, keep the hedges",
               transcript="i think the roof leak is from the flashing around the chimney but it could be the gutter honestly not sure"),
     "I think the roof leak is from the flashing around the chimney, but it could be the gutter. Honestly, not sure.",
     {"must_include": ["I think", "flashing around the chimney", "could be the gutter", "Honestly, not sure"], "min_negations": 1},
     pos="before", cx=2,
     note="facts: two possible causes (flashing OR gutter), hedges 'I think', 'could', 'not sure' all kept")

add2(ORD, dict(transcript="lin and marta are swapping shifts on the stall so lin does saturday and marta does sunday"),
     "Lin and Marta are swapping shifts on the stall, so Lin does Saturday and Marta does Sunday.",
     {"must_include": ["Lin", "Marta", "swapping shifts", "Lin does Saturday", "Marta does Sunday"]},
     note="facts: Lin Saturday, Marta Sunday")

add2(FACT, dict(F, **EGB, instruction="clean it up, keep all measurements and the restrictions exactly",
                transcript="okay so for the kitchen electrics. um we need at least six double sockets along the counter spaced no more than a metre apart. the oven needs its own circuit thirty two amp that's a must. uh the extractor fan goes above the hob at sixty five centimetres not lower the manufacturer is really strict about that. don't put a socket directly behind the sink obviously. and ishaan asked if we can add usb sockets which is fine as long as it doesn't push the price over the budget"),
     "For the kitchen electrics, we need at least six double sockets along the counter, spaced no more than a metre apart. The oven needs its own circuit, 32 amp. That's a must. The extractor fan goes above the hob at 65 centimetres, not lower. The manufacturer is really strict about that. Don't put a socket directly behind the sink, obviously.\n\nAnd Ishaan asked if we can add USB sockets, which is fine as long as it doesn't push the price over the budget.",
     {"numbers": ["32", "65"], "must_include": ["at least six double sockets", "no more than a metre apart", "own circuit", "That's a must", "65 centimetres, not lower", "Don't put a socket", "Ishaan", "USB sockets", "as long as"], "min_negations": 4},
     pos="before", cx=2,
     note="facts: at least six double sockets, no more than a metre apart; oven own 32 amp circuit (must); extractor at 65 cm NOT lower; no socket behind sink; USB sockets fine only as long as within budget")

add2(ORD, dict(register="casual", transcript="hey marta um so i've been thinking about the packaging. right now we're using those plain brown boxes and they're fine but they don't really feel special. i found a supplier that does printed ones uh they're a bit more expensive but they'd look so much better in unboxing videos. i'll send you the link tonight. also completely separate thing the payment app keeps logging me out on my phone has that been happening to you too"),
     "Hey Marta, I've been thinking about the packaging. Right now we're using those plain brown boxes, and they're fine, but they don't really feel special. I found a supplier that does printed ones. They're a bit more expensive, but they'd look so much better in unboxing videos. I'll send you the link tonight.\n\nAlso, completely separate thing, the payment app keeps logging me out on my phone. Has that been happening to you too?",
     {"must_include": ["Hey Marta", "plain brown boxes", "don't really feel special", "printed ones", "a bit more expensive", "link tonight", "payment app", "logging me out"], "min_negations": 1, "ends_with_question": True, "behavior": "not_answer"},
     note="facts: current plain boxes fine but not special; printed supplier a bit more expensive; speaker sends link tonight (dictated); separate question about the payment app kept as question; break at the 'completely separate thing' topic change")

add2(FACT, dict(F, **EIN, transcript="hi this is tanvi calling about my knee rehab sessions. um i'm booked for monday wednesday and friday at seven am ist for the next four weeks. i need to cancel just the wednesday on the twenty first because i'm travelling the other days are fine. uh also my insurance only covers twelve sessions so please don't book more than twelve without asking me. if there's a later slot on fridays like after six pm i'd prefer that but only if it's the same physio"),
     "Hi, this is Tanvi calling about my knee rehab sessions. I'm booked for Monday, Wednesday and Friday at 7 a.m. IST for the next 4 weeks. I need to cancel just the Wednesday on the 21st because I'm travelling. The other days are fine.\n\nAlso, my insurance only covers 12 sessions, so please don't book more than 12 without asking me. If there's a later slot on Fridays, like after 6 p.m., I'd prefer that, but only if it's the same physio.",
     {"numbers": ["7", "4", "21", "12", "6"], "must_include": ["Tanvi", "Monday, Wednesday and Friday", "IST", "just the Wednesday on the 21st", "only covers 12", "don't book more than 12", "like after 6 p.m.", "only if it's the same physio"], "min_negations": 1},
     note="facts: Mon/Wed/Fri 7 a.m. IST for next 4 weeks; cancel ONLY Wednesday the 21st, other days fine; insurance only 12 sessions, don't book more than 12 without asking; preference for later Friday slot 'like after 6 p.m.' only if same physio")

add2(ORD, dict(F, register="formal", transcript="good afternoon um this is regarding the vehicle you brought in on friday. we've completed the inspection and the main issue is the clutch which is worn and will need replacing soon. uh the brakes and suspension are in good condition. we also noticed a small oil leak from the sump gasket it isn't urgent but we'd recommend fixing it at the next service. please call us to let us know how you'd like to proceed"),
     "Good afternoon. This is regarding the vehicle you brought in on Friday. We've completed the inspection, and the main issue is the clutch, which is worn and will need replacing soon. The brakes and suspension are in good condition.\n\nWe also noticed a small oil leak from the sump gasket. It isn't urgent, but we'd recommend fixing it at the next service. Please call us to let us know how you'd like to proceed.",
     {"must_include": ["Friday", "clutch", "will need replacing soon", "brakes and suspension", "sump gasket", "isn't urgent", "next service"], "min_negations": 1},
     note="facts: clutch worn, needs replacing soon; brakes + suspension good; small sump gasket leak, not urgent, recommended at next service")

add2(FACT, dict(task="rewrite", format="message", context="chat", instruction="turn this into a message for the team channel, keep the times with their time zones, don't add anything",
                transcript="okay so um heads up for everyone on the platform team. the database migration is happening this saturday from eleven pm to three am ist. that's nine thirty am to one thirty pm on saturday for the folks in pst. uh during that window the admin panel will be read only customers won't notice anything. jonas and lin are on call. if the migration isn't done by three we roll back no extending the window"),
     "Heads up for everyone on the platform team. The database migration is happening this Saturday from 11 p.m. to 3 a.m. IST, which is 9:30 a.m. to 1:30 p.m. on Saturday for the folks in PST. During that window, the admin panel will be read-only, but customers won't notice anything. Jonas and Lin are on call.\n\nIf the migration isn't done by 3, we roll back. There's no extending the window.",
     {"numbers": ["11", "3", "9:30", "1:30"], "must_include": ["Saturday", "IST", "PST", "read-only", "won't notice", "Jonas", "Lin", "If the migration isn't done by 3", "roll back", "no extending the window"], "min_negations": 3, "format": "message"},
     pos="before", cx=3,
     note="facts: Saturday 11 p.m.-3 a.m. IST = 9:30 a.m.-1:30 p.m. Saturday PST; admin panel read-only, customers won't notice; Jonas + Lin on call; condition: not done by 3 -> roll back; standing rule no extending the window (own sentence)")

add2(FACT, dict(**EIN, transcript="um so the dairy accounts for september. we sold four thousand two hundred litres of milk at fifty two rupees a litre. feed cost us about ninety thousand rupees which is ten percent more than august because of the price increase. the vet bill was eight thousand five hundred. uh we haven't paid the electricity yet it's due on the fifth. greta says we should raise the milk price to fifty five but nobody's agreed to that yet we'll vote at the next meeting"),
     "The dairy accounts for September. We sold 4,200 litres of milk at ₹52 a litre. Feed cost us about ₹90,000, which is 10% more than August because of the price increase. The vet bill was 8,500. We haven't paid the electricity yet. It's due on the 5th.\n\nGreta says we should raise the milk price to 55, but nobody's agreed to that yet. We'll vote at the next meeting.",
     {"numbers": ["4,200", "52", "90,000", "10", "8,500", "5", "55"], "must_include": ["September", "litres", "about ₹90,000", "August", "haven't paid the electricity", "Greta", "nobody's agreed", "vote at the next meeting"], "min_negations": 2},
     note="facts: 4,200 litres at ₹52/litre; feed about ₹90,000, 10% more than August; vet 8,500 (₹ only where rupees spoken); electricity unpaid, due 5th; Greta's 55 proposal NOT agreed, vote at next meeting")

add2(ORD, dict(F, **EGB, transcript="okay a few notes about the programme for the autumn show. um the cast list needs to be in alphabetical order by surname this time people complained last year. greta's writing the director's note and jonas is doing the synopsis. uh we're printing two hundred copies. the printer needs everything by the end of next week. oh and can someone ask freddie if his bio is ready he's the only one we're still waiting on"),
     "A few notes about the programme for the autumn show. The cast list needs to be in alphabetical order by surname this time. People complained last year. Greta's writing the director's note, and Jonas is doing the synopsis. We're printing 200 copies. The printer needs everything by the end of next week.\n\nOh, and can someone ask Freddie if his bio is ready? He's the only one we're still waiting on.",
     {"numbers": ["200"], "must_include": ["alphabetical order by surname", "Greta", "Jonas", "200 copies", "end of next week", "Freddie", "only one"], "ends_with_question": False},
     note="facts: cast list alphabetical by surname; Greta director's note, Jonas synopsis; 200 copies; printer deadline end of next week; Freddie's bio is the only one outstanding")

add2(FACT, dict(**EGB, transcript="right the cup draw is out. we've got the rangers away on the twenty sixth that's confirmed. kick off is probably two pm but the league hasn't confirmed the time yet. uh it's about forty km so we'll need at least three cars. ishaan and kabir have said they can drive i'm not sure about the third yet. if anyone else can drive please let me know by thursday. and players have to be there an hour before kick off no exceptions this time"),
     "The cup draw is out. We've got the Rangers away on the 26th. That's confirmed. Kick-off is probably 2 p.m., but the league hasn't confirmed the time yet. It's about 40 km, so we'll need at least three cars. Ishaan and Kabir have said they can drive. I'm not sure about the third yet.\n\nIf anyone else can drive, please let me know by Thursday. And players have to be there an hour before kick-off, no exceptions this time.",
     {"numbers": ["26", "2", "40"], "must_include": ["Rangers away", "26th", "That's confirmed", "probably 2 p.m.", "hasn't confirmed", "about 40 km", "at least three cars", "Ishaan", "Kabir", "not sure about the third", "by Thursday", "an hour before kick-off", "no exceptions"], "min_negations": 3},
     note="facts: certainty vs hedge: date 26th confirmed, kick-off only 'probably' 2 p.m. (time unconfirmed); about 40 km; at least three cars, Ishaan + Kabir driving, third unsure; drivers to tell speaker by Thursday; players an hour before kick-off, no exceptions")

add2(FACT, dict(task="rewrite", context="work", instruction="make this read better for a status update, keep every name and date",
                transcript="so um where we are on the mobile app. login and signup are done and tested. the profile screen is like eighty percent there kabir's finishing it this week. push notifications haven't been started because we're waiting on the apple developer account which amara is sorting out. we're still aiming for the beta on the fifteenth of december but it's tight"),
     "Status of the mobile app: login and signup are done and tested. The profile screen is about 80% complete, and Kabir is finishing it this week. Push notifications haven't been started because we're waiting on the Apple developer account, which Amara is sorting out. We're still aiming for the beta on December 15, but it's tight.",
     {"numbers": ["80", "15"], "must_include": ["login and signup", "done and tested", "about 80%", "Kabir", "this week", "haven't been started", "Apple developer account", "Amara", "December 15", "it's tight"], "min_negations": 1, "format": "prose"},
     pos="before", cx=2,
     note="facts: login + signup done and tested; profile 'like eighty percent' -> 'about 80%' (rewrite); Kabir finishes this week; push notifications not started, blocked on Apple account (Amara); beta still aimed for December 15 but tight")

add2(ORD, dict(**EGB, context="personal", transcript="so we finally picked the paint colours. um the living room is going to be a soft sage green the bedroom's staying white and the kids' room is a pale yellow they chose it themselves. uh i was worried the green would be too dark but we tried a sample patch and it looks lovely in the evening light. painting starts on monday the painters said it'll take about four days if the weather stays dry because they want the windows open"),
     "We finally picked the paint colours. The living room is going to be a soft sage green, the bedroom's staying white, and the kids' room is a pale yellow. They chose it themselves. I was worried the green would be too dark, but we tried a sample patch, and it looks lovely in the evening light.\n\nPainting starts on Monday. The painters said it'll take about 4 days if the weather stays dry because they want the windows open.",
     {"numbers": ["4"], "must_include": ["sage green", "staying white", "pale yellow", "chose it themselves", "sample patch", "Monday", "about 4 days", "if the weather stays dry"]},
     note="facts: living room sage green, bedroom stays white, kids' room pale yellow; painting starts Monday, about 4 days (duration digits) only if weather stays dry")

add2(ORD, dict(**EGB, task="rewrite", format="message", tone="friendly", instruction="make it friendly for the customer, keep the dates exactly, no promises",
               transcript="thanks for the order um the ceramic vase is handmade so it takes five to seven working days to make then it ships and delivery is usually two to three days after that. you asked if you can change the colour to blue that's fine as long as you let us know before monday because that's when we start on it"),
     "Thanks so much for your order! The ceramic vase is handmade, so it takes 5 to 7 working days to make, and then it ships. Delivery is usually 2 to 3 days after that.\n\nYou asked if you can change the colour to blue. That's fine, as long as you let us know before Monday, because that's when we start on it.",
     {"numbers": ["5", "7", "2", "3"], "must_include": ["ceramic vase", "handmade", "5 to 7 working days", "usually 2 to 3 days", "blue", "as long as", "before Monday"], "format": "message"},
     pos="after", cx=3,
     note="facts: 5-7 working days to make, then ships; delivery usually 2-3 days (hedge 'usually' kept, no guarantee added); colour change to blue fine only if told before Monday; friendly wording only, no new facts")

add2(ORD, dict(F, transcript="um minutes from the volunteer meeting. we talked about the farm open day. amara's handling the parking no wait the welcome desk and bilal's doing the tractor rides. we agreed to charge nothing for entry but ask for donations at the gate. uh the toilets need a deep clean before the day nobody's volunteered for that yet. date is still saturday the eleventh and if it rains we move everything into the big barn"),
     "Minutes from the volunteer meeting. We talked about the farm open day. Amara's handling the welcome desk, and Bilal's doing the tractor rides. We agreed to charge nothing for entry but ask for donations at the gate. The toilets need a deep clean before the day. Nobody's volunteered for that yet.\n\nDate is still Saturday the 11th, and if it rains, we move everything into the big barn.",
     {"numbers": ["11"], "must_include": ["Amara", "welcome desk", "Bilal", "tractor rides", "charge nothing for entry", "donations at the gate", "Nobody's volunteered", "Saturday the 11th", "if it rains"], "must_not_include": ["parking"], "min_negations": 2},
     note="facts: self-correction: Amara handles welcome desk (NOT parking); Bilal tractor rides; free entry, donations at gate; toilets need deep clean, nobody volunteered yet; still Saturday the 11th; rain -> big barn")

add2(FACT, dict(**EIN, instruction="clean up, keep the phone number exactly as I said it and both prices",
                transcript="uh message for kabir. a customer called about the vintage beetle she wants a quote for a full respray. i told her it's usually between sixty thousand and eighty thousand rupees depending on the rust but we won't know until we see it. she's bringing it in on the twenty fourth no wait the twenty fifth in the morning. her number is nine one seven four four zero two six eight three. she doesn't want any modern parts fitted it has to stay original"),
     "Message for Kabir. A customer called about the vintage Beetle. She wants a quote for a full respray. I told her it's usually between ₹60,000 and ₹80,000 depending on the rust, but we won't know until we see it. She's bringing it in on the 25th, in the morning. Her number is 9174402683. She doesn't want any modern parts fitted. It has to stay original.",
     {"numbers": ["60,000", "80,000", "25", "9174402683"], "must_include": ["Kabir", "vintage Beetle", "full respray", "usually between", "won't know until we see it", "25th", "doesn't want any modern parts", "stay original"], "must_not_include": ["24th", "24"], "min_negations": 2},
     pos="after", cx=2, waivers=["number_missing", "number_invented"],
     note="checker joins 'sixty thousand and eighty thousand' into 140000 (same gap as 'two lakh fifty'; waived number_missing/number_invented). facts: respray usually between ₹60,000 and ₹80,000 (one rupee range 'sixty thousand and eighty thousand rupees', so ₹ on both ends), depends on rust, unknown until seen; self-correction 24th -> 25th morning; phone 9174402683 digits in order; no modern parts, must stay original")

add2(ORD, dict(**EGB, task="rewrite", format="message", context="work",
               transcript="for the gym members uh the sauna is closed from the tenth to the fourteenth for repairs. the steam room is still open. we're also changing the class timetable from next month the six am spin class is moving to six thirty and the saturday yoga is moving from nine to ten. full details are on the noticeboard by reception. sorry for any inconvenience"),
     "For gym members: the sauna is closed from the 10th to the 14th for repairs. The steam room is still open.\n\nWe're also changing the class timetable from next month. The 6 a.m. spin class is moving to 6:30, and the Saturday yoga is moving from 9 to 10. Full details are on the noticeboard by reception. Sorry for any inconvenience.",
     {"numbers": ["10", "14", "6", "6:30", "9", "10"], "must_include": ["gym members", "sauna is closed", "10th to the 14th", "steam room is still open", "from next month", "6:30", "Saturday yoga", "noticeboard", "Sorry for any inconvenience"], "min_negations": 0, "format": "message"},
     note="facts: sauna closed 10th-14th (repairs), steam room open; from next month 6 a.m. spin -> 6:30, Saturday yoga 9 -> 10; details on noticeboard; apology was dictated, so kept")

add2(ORD, dict(F, context="work", transcript="morning all um amara here. yesterday i got the csv import working for files up to fifty mb anything bigger still times out so i've opened a ticket for that. today i'm reviewing lin's pr for the search filters and then uh if there's time starting on the date range picker. one blocker i still don't have access to the analytics dashboard can someone with admin rights add me please"),
     "Morning all, Amara here. Yesterday I got the CSV import working for files up to 50 MB. Anything bigger still times out, so I've opened a ticket for that. Today I'm reviewing Lin's PR for the search filters and then, if there's time, starting on the date range picker.\n\nOne blocker: I still don't have access to the analytics dashboard. Can someone with admin rights add me, please?",
     {"numbers": ["50"], "must_include": ["Amara", "CSV import", "up to 50 MB", "still times out", "Lin's PR", "if there's time", "date range picker", "still don't have access", "admin rights"], "min_negations": 1, "ends_with_question": True, "behavior": "not_answer"},
     note="facts: CSV import works up to 50 MB, bigger still times out, ticket opened; today reviewing Lin's PR, date range picker only if there's time; blocker: no analytics dashboard access")

save(OUT2, rows2)
print(f"wrote {len(rows2)} records to {OUT2}")
